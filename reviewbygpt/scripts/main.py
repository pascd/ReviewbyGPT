"""Command-line entry point for ReviewbyGPT.

Runs :class:`~reviewbygpt.scripts.pdf_to_excel.PDFToExcelProcessor` over a
folder of PDFs, using any OpenAI-chat-completions-compatible LLM backend
(OpenAI, a local Ollama server, LM Studio, vLLM, ...).

Usage:
    python -m reviewbygpt.scripts.main --pdf-folder ./papers --review-config ./config/review_data.yaml
    reviewbygpt --pdf-folder ./papers --review-config ./config/review_data.yaml --api-url https://api.openai.com/v1/chat/completions --model gpt-4o-mini

LLM backend settings (api url/key/model) can be supplied via CLI flags, the
``LLM_API_URL``/``LLM_API_KEY``/``LLM_MODEL`` environment variables, or a
JSON file passed via ``--llm-config`` -- see
:class:`~reviewbygpt.lib.llm_client.LLMClient` for the exact precedence.
"""

import argparse
import logging
from typing import List, Optional

from reviewbygpt.scripts.pdf_to_excel import PDFToExcelProcessor


def build_parser() -> argparse.ArgumentParser:
    """Build the ``argparse`` parser for the ReviewbyGPT CLI.

    Returns:
        A configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="reviewbygpt",
        description=(
            "Automate literature-review quality assessment and data extraction "
            "from PDFs into an Excel report, using any OpenAI-compatible LLM backend."
        ),
    )

    parser.add_argument(
        "--pdf-folder",
        required=True,
        help="Folder containing the PDFs to review. 'analysed/', 'rejected/', and "
        "'sheet/' subfolders are created inside it.",
    )
    # No default is provided for --review-config: the schema in
    # config/review_data.yaml encodes one specific domain's review
    # questions, so it must not silently become every user's default.
    parser.add_argument(
        "--review-config",
        required=True,
        help="Path to a YAML file defining quality-assessment questions, cutoff "
        "score, excluding questions, and data-extraction fields.",
    )
    parser.add_argument(
        "--qa-sheet-name",
        default="qa_sheet",
        help="Excel sheet name for quality-assessment results (default: %(default)s).",
    )
    parser.add_argument(
        "--de-sheet-name",
        default="de_sheet",
        help="Excel sheet name for data-extraction results (default: %(default)s).",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=10,
        help="Number of PDFs processed before starting a new logical conversation "
        "with the LLM (default: %(default)s).",
    )
    parser.add_argument(
        "--llm-config",
        help="Path to a JSON file with LLM backend settings (api_url/api_key/model/...). "
        "Falls back to environment variables / the flags below if omitted.",
    )
    parser.add_argument(
        "--api-url",
        help="LLM API URL (an OpenAI-compatible /v1/chat/completions endpoint). "
        "Overrides --llm-config and $LLM_API_URL.",
    )
    parser.add_argument(
        "--api-key",
        help="API key/bearer token, if required by the backend. Overrides "
        "--llm-config and $LLM_API_KEY. Prefer the environment variable over "
        "this flag to avoid leaking secrets into shell history.",
    )
    parser.add_argument(
        "--model",
        help="Model name to request from the backend. Overrides --llm-config and $LLM_MODEL.",
    )
    parser.add_argument(
        "--max-content-length",
        type=int,
        default=None,
        help="Truncate extracted PDF text to this many characters before sending it "
        "to the LLM (default: no truncation).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-request HTTP timeout, in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: %(default)s).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Parse CLI arguments and run the PDF review pipeline.

    Args:
        argv: Argument list to parse instead of ``sys.argv[1:]``. Mainly
            useful for testing.

    Returns:
        0 on success, 1 if the pipeline reported failure.
    """
    args = build_parser().parse_args(argv)

    # This is the only place in the whole package that calls
    # logging.basicConfig() -- library modules only fetch a logger via
    # logging.getLogger(__name__), so importing them never has the side
    # effect of configuring logging for whatever program imports them.
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    processor = PDFToExcelProcessor(
        pdf_folder_path=args.pdf_folder,
        review_config=args.review_config,
        qa_sheet_name=args.qa_sheet_name,
        de_sheet_name=args.de_sheet_name,
        max_questions=args.max_questions,
        llm_config_path=args.llm_config,
        api_url=args.api_url,
        api_key=args.api_key,
        model=args.model,
        max_content_length=args.max_content_length,
        timeout=args.timeout,
    )
    return 0 if processor.run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
