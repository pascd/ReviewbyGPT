"""Core pipeline: turn a folder of PDFs into a scored, filled-in Excel report.

:class:`PDFToExcelProcessor` is the main entry point of ReviewbyGPT. For each
PDF found in a folder, it:

1. Extracts the PDF's text and sends it, together with a prompt built from
   ``config/review_data.yaml``, to an LLM via :class:`~reviewbygpt.lib.
   llm_client.LLMClient` (any OpenAI-chat-completions-compatible backend).
2. Parses the quality-assessment (QA) scores and data-extraction (DE) fields
   out of the LLM's response via :class:`~reviewbygpt.lib.review_data_parser.
   ReviewDataParser`.
3. Writes the QA/DE results into an Excel workbook via
   :class:`~reviewbygpt.lib.excel_data_parser.ExcelDataParser`.
4. Moves the PDF into an ``analysed/`` or ``rejected/`` subfolder depending
   on whether its score meets the configured cutoff and excluding-question
   rules.
"""

import logging
import os
import random
import shutil
import time
from pathlib import Path
from typing import Optional

from reviewbygpt.lib.excel_data_parser import ExcelDataParser
from reviewbygpt.lib.llm_client import LLMClient
from reviewbygpt.lib.review_data_parser import ReviewDataParser

logger = logging.getLogger(__name__)


class PDFToExcelProcessor:
    """Reviews every PDF in a folder and records the results in Excel.

    Folder layout created inside ``pdf_folder_path``:

    - ``sheet/analysed.xlsx``: the Excel workbook, with one sheet for
      quality-assessment scores and one for extracted data fields.
    - ``analysed/``: PDFs that passed the cutoff/excluding-question checks.
    - ``rejected/``: PDFs that did not.
    - ``debug_logs/``: per-PDF text files with the exact prompt sent and
      response received, for troubleshooting parsing issues.
    - ``llm_responses.log``: a single running log of every LLM response,
      in processing order.
    """

    def __init__(
        self,
        pdf_folder_path: str,
        review_config: str,
        qa_sheet_name: str,
        de_sheet_name: str,
        max_questions: int = 10,
        llm_config_path: Optional[str] = None,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_content_length: Optional[int] = None,
        timeout: int = 600,
    ) -> None:
        """Set up folders, the LLM client, and the review configuration.

        Args:
            pdf_folder_path: Folder containing the PDFs to review. The
                ``analysed/``, ``rejected/``, and ``sheet/`` subfolders are
                created inside it.
            review_config: Path to a YAML file defining the quality
                -assessment questions, cutoff score, excluding questions,
                and data-extraction fields (see ``config/review_data.yaml``
                for the expected schema).
            qa_sheet_name: Name of the Excel sheet for QA results.
            de_sheet_name: Name of the Excel sheet for DE results.
            max_questions: Number of PDFs to process before starting a new
                logical conversation with the LLM (see
                :meth:`~reviewbygpt.lib.llm_client.LLMClient.new_conversation`).
            llm_config_path: Optional path to a JSON file with LLM backend
                settings. See :class:`~reviewbygpt.lib.llm_client.LLMClient`
                for the full configuration precedence rules.
            api_url: LLM API URL, overriding ``llm_config_path``/env vars.
            api_key: LLM API key, overriding ``llm_config_path``/env vars.
            model: LLM model name, overriding ``llm_config_path``/env vars.
            max_content_length: Optional cap on extracted PDF text length
                before it's sent to the LLM.
            timeout: Per-request HTTP timeout, in seconds, for LLM calls.
        """
        self.pdf_folder_path = pdf_folder_path
        self.analysed_folder_path = os.path.join(pdf_folder_path, "analysed")
        self.excel_file_path = os.path.join(pdf_folder_path, "sheet")
        self.rejected_file_path = os.path.join(pdf_folder_path, "rejected")
        self.folder_pths = [self.analysed_folder_path, self.excel_file_path, self.rejected_file_path]

        self.qa_sheet_name = qa_sheet_name
        self.de_sheet_name = de_sheet_name
        self.max_questions = max_questions

        self.llm_client = LLMClient(
            config_path=llm_config_path,
            api_url=api_url,
            api_key=api_key,
            model=model,
            max_content_length=max_content_length,
            timeout=timeout,
        )

        self.excel_parser = ExcelDataParser(self.excel_file_path)
        self.review_parser = ReviewDataParser(review_config)

        # Load the review schema once up front so it doesn't need to be
        # re-read from disk for every PDF processed.
        self.qa_fields = self.review_parser.get_all_quality_assessment_fields()
        self.data_extraction_fields = self.review_parser.get_all_data_extraction_fields()
        self.cutoff_score = self.review_parser.get_cutoff_score()
        self.excluding_questions = self.review_parser.get_all_excluding_questions()

    def initiate_llm_client(self) -> bool:
        """Best-effort check that the configured LLM backend is reachable.

        A False return is logged as a warning, not treated as fatal --
        see :meth:`~reviewbygpt.lib.llm_client.LLMClient.verify_connection`
        for why some backends can't be probed ahead of time.

        Returns:
            Whatever :meth:`LLMClient.verify_connection` returned.
        """
        try:
            if self.llm_client.verify_connection():
                logger.info("Successfully connected to the LLM backend")
                return True
            logger.warning("Could not verify LLM backend connectivity; continuing anyway")
            return False
        except Exception as e:
            logger.warning(f"Error verifying LLM backend connection: {e}")
            return False

    def get_pdf_paths(self):
        """List the full paths of every PDF directly inside ``pdf_folder_path``.

        Returns:
            list[str]: Paths of files ending in ``.pdf`` (case-insensitive).

        Raises:
            FileNotFoundError: If ``pdf_folder_path`` does not exist.
        """
        if not os.path.exists(self.pdf_folder_path):
            raise FileNotFoundError(f"The folder '{self.pdf_folder_path}' does not exist.")
        return [
            os.path.join(self.pdf_folder_path, f)
            for f in os.listdir(self.pdf_folder_path)
            if f.lower().endswith(".pdf")
        ]

    def _write_debug_file(self, pdf_path: str, suffix: str, content: str) -> str:
        """Write a troubleshooting artifact for a PDF into its ``debug_logs/`` folder.

        Every PDF processed gets one ``<pdf-stem>_<suffix>.txt`` file per
        artifact (prompt sent, raw extracted text, raw response) so that a
        response that doesn't parse the way :class:`ReviewDataParser` expects
        can be inspected after the fact.

        Args:
            pdf_path: Path to the PDF being processed.
            suffix: Short label identifying the artifact, e.g. ``"prompt"``.
            content: The text to write.

        Returns:
            The full path of the debug file that was written.
        """
        debug_dir = os.path.join(os.path.dirname(pdf_path), "debug_logs")
        os.makedirs(debug_dir, exist_ok=True)

        pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
        debug_path = os.path.join(debug_dir, f"{pdf_stem}_{suffix}.txt")

        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Saved {suffix} debug file to {debug_path}")
        return debug_path

    def send_pdf_to_analysis(self, pdf_path: str, prompt: str) -> Optional[str]:
        """Extract a PDF's text and send it, with the prompt, to the LLM.

        Args:
            pdf_path: Path to the PDF to analyse.
            prompt: The analysis prompt to send alongside the PDF text.

        Returns:
            The LLM's response text, or None if PDF extraction or the LLM
            call failed.
        """
        pdf_content = self.llm_client.extract_text_from_pdf(pdf_path)
        if not pdf_content:
            logger.error(f"Could not extract text from PDF: {pdf_path}")
            return None

        # Only the first 5000 characters are kept in the debug file -- the
        # full text is already what gets sent to the LLM; the debug copy is
        # just a sanity-check sample, not meant to duplicate the whole PDF.
        preview = pdf_content[:5000]
        if len(pdf_content) > 5000:
            preview += "\n\n... [content truncated for debug file only] ..."
        self._write_debug_file(pdf_path, "pdf_extract", preview)

        response = self.llm_client.send_prompt(prompt, pdf_content)

        if response:
            self._write_debug_file(pdf_path, "response", response)
        else:
            logger.error("No response received from the LLM")

        return response

    def move_analysed_file(self, file_path: str) -> None:
        """Move a PDF into ``analysed/`` (i.e. it passed the review checks).

        Args:
            file_path: Path to the PDF to move.
        """
        os.makedirs(self.analysed_folder_path, exist_ok=True)
        try:
            shutil.move(file_path, self.analysed_folder_path)
            logger.info(f"Moved '{file_path}' to '{self.analysed_folder_path}'.")
        except Exception as e:
            logger.error(f"Error moving file '{file_path}': {e}")

    def move_rejected_file(self, file_path: str) -> None:
        """Move a PDF into ``rejected/`` (i.e. it failed the review checks).

        Args:
            file_path: Path to the PDF to move.
        """
        os.makedirs(self.rejected_file_path, exist_ok=True)
        try:
            shutil.move(file_path, self.rejected_file_path)
            logger.info(f"Moved '{file_path}' to '{self.rejected_file_path}'.")
        except Exception as e:
            logger.error(f"Error moving file '{file_path}': {e}")

    def create_folders(self) -> None:
        """Create the ``analysed/``, ``sheet/``, and ``rejected/`` folders.

        If any folder fails to be created, all of them are torn down again
        via :meth:`delete_folders` to avoid leaving a half-initialized
        working directory behind.
        """
        for folder in self.folder_pths:
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
                logger.info(f"Created folder {folder}.")
            except Exception:
                logger.error(f"Unable to create folder: {folder}.")
                self.delete_folders()

    def delete_folders(self) -> None:
        """Remove the ``analysed/``, ``sheet/``, and ``rejected/`` folders, if present."""
        for folder in self.folder_pths:
            try:
                if os.path.exists(folder) and os.path.isdir(folder):
                    shutil.rmtree(folder)
            except Exception:
                logger.error(f"Unable to delete folder: {folder}.")

    def _process_single_pdf(self, pdf_path: str, response_log_file: str) -> None:
        """Run the full review pipeline for one PDF.

        Builds the prompt, calls the LLM, parses QA/DE data out of the
        response, writes it to Excel, and moves the PDF to ``analysed/`` or
        ``rejected/``. Any exception raised while processing this single
        file is caught and logged here so that one bad PDF doesn't abort
        the whole batch in :meth:`run`.

        Args:
            pdf_path: Path to the PDF to process.
            response_log_file: Path to the consolidated log file that every
                PDF's raw LLM response gets appended to.
        """
        try:
            prompt = self.review_parser.get_analysis_prompt()
            self._write_debug_file(pdf_path, "prompt", prompt)

            response = self.send_pdf_to_analysis(pdf_path, prompt)

            # Record the outcome (even a missing response) to the
            # consolidated log so the full run can be reviewed afterwards.
            with open(response_log_file, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n\n{'=' * 80}\n")
                log_file.write(f"PDF: {os.path.basename(pdf_path)}\n")
                log_file.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"{'=' * 80}\n\n")
                log_file.write(response if response else "*** NO RESPONSE RECEIVED ***")

            if not response:
                logger.warning(f"No response for file: {pdf_path}")
                return

            # Data extraction is parsed first purely so its TITLE field can
            # be reused as the paper's display title in the QA sheet too.
            de_data = self.review_parser.get_data_extraction_text(response)

            paper_title = None
            for title_key in ("TITLE", "Title", "title"):
                if title_key in de_data:
                    paper_title = de_data[title_key]
                    logger.info(f"Found title: {paper_title}")
                    break
            if not paper_title:
                paper_title = os.path.splitext(os.path.basename(pdf_path))[0]
                logger.warning(f"No title found in data extraction, using filename: {paper_title}")

            qa_data = self.review_parser.get_quality_assessment_text(response)
            # "TOTAL_SCORE" is the exact key ReviewDataParser.preprocess_qa_data
            # stores the aggregate score under -- must match here and in the
            # Excel header below, or the score silently reads back as 0.
            paper_score = qa_data.pop("TOTAL_SCORE", 0)
            # "TITLE" (not "Title") matches the header ExcelDataParser
            # auto-prepends for QA sheets in apply_excel_template().
            qa_data["TITLE"] = paper_title

            if qa_data:
                self.excel_parser.fill_excel_with_data(self.qa_sheet_name, {**qa_data, "TOTAL_SCORE": paper_score})
                logger.info(f"Total QA Score: {paper_score}")
            else:
                logger.warning(f"No QA data found for file: {pdf_path}")

            # Excluding questions: if any of them scored 0, the paper is
            # rejected outright regardless of its total score. Stored score
            # keys are "<question_id>_SCORE" (e.g. "QE1_SCORE").
            for e_question in self.excluding_questions:
                if qa_data.get(f"{e_question}_SCORE", 1) == 0:
                    logger.info(f"Paper does not meet the score needed for excluding question: {e_question}")
                    self.move_rejected_file(pdf_path)
                    return

            if paper_score and paper_score >= self.cutoff_score:
                logger.info(f"Paper score ({paper_score}) meets the cutoff ({self.cutoff_score}). Extracting DE data...")
                if de_data:
                    # Keep the DE sheet's title consistent with the QA sheet's.
                    if "TITLE" in de_data and paper_title:
                        de_data["TITLE"] = paper_title
                    self.excel_parser.fill_excel_with_data(self.de_sheet_name, de_data)
                else:
                    logger.warning(f"No DE data found for file: {pdf_path}")
            else:
                logger.info(
                    f"Paper score ({paper_score}) does not meet the cutoff ({self.cutoff_score}). "
                    "Skipping DE data extraction."
                )
                self.move_rejected_file(pdf_path)
                return

            self.move_analysed_file(pdf_path)
        except Exception as e:
            logger.error(f"Error processing file '{pdf_path}': {e}")

    def run(self) -> bool:
        """Run the full pipeline over every PDF in ``pdf_folder_path``.

        Sets up the working folders and Excel template, then processes each
        PDF in turn via :meth:`_process_single_pdf`. Per-file failures are
        logged and skipped rather than aborting the whole batch.

        Returns:
            True once every PDF has been processed.
        """
        self.create_folders()

        self.excel_parser.create_excel_file()

        qa_identifiers = []
        for qa in self.qa_fields:
            qa_identifiers.append(qa["id"])
            qa_identifiers.append(f"{qa['id']}_SCORE")
        self.excel_parser.apply_excel_template(self.qa_sheet_name, ["TITLE"] + qa_identifiers + ["TOTAL_SCORE"])

        de_identifiers = [de["key"] for de in self.data_extraction_fields]
        self.excel_parser.apply_excel_template(self.de_sheet_name, de_identifiers)

        # Best-effort connectivity check; a failure here is logged but does
        # not stop the run (see initiate_llm_client's docstring).
        self.initiate_llm_client()

        response_log_file = os.path.join(self.pdf_folder_path, "llm_responses.log")
        with open(response_log_file, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== LLM Response Log - Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
            log_file.write(f"Using LLM backend at {self.llm_client.api_url} (model: {self.llm_client.model})\n")
        logger.info(f"Created LLM response log file at: {response_log_file}")

        num_processed = 0
        for pdf_path in self.get_pdf_paths():
            if not pdf_path.lower().endswith(".pdf"):
                logger.info(f"Skipping non-PDF file: {pdf_path}")
                continue

            # Start a new logical conversation every `max_questions` PDFs.
            if num_processed == self.max_questions:
                self.llm_client.new_conversation()
                num_processed = 0

            logger.info(f"Processing file: {pdf_path}")
            self._process_single_pdf(pdf_path, response_log_file)
            num_processed += 1

            # A small, randomized delay between requests as a courtesy to
            # rate-limited or shared backends.
            time.sleep(random.randint(1, 3))

        logger.info("Completed PDF processing")
        return True
