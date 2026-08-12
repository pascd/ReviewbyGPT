"""Manual/integration example -- NOT collected by pytest.

This script runs the real pipeline end-to-end against a real LLM backend and
real PDFs, so it can't be part of the automated test suite (see
tests/test_llm_client.py for the mocked, CI-safe equivalent).

Usage:
    Put some PDFs in ./pdf-files/ next to this script, make sure an
    OpenAI-compatible LLM backend is reachable (e.g. `ollama serve`
    running locally), then run:

        python tests/run_pdf_review.py
"""

import os
import sys

# Allow running this script directly (`python tests/run_pdf_review.py`)
# without having installed the package first.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from reviewbygpt.scripts.pdf_to_excel import PDFToExcelProcessor

if __name__ == "__main__":
    pdf_to_excel_processor = PDFToExcelProcessor(
        pdf_folder_path="./pdf-files/",
        review_config="../config/review_data.yaml",
        qa_sheet_name="qa_sheet",
        de_sheet_name="de_sheet",
        # LLM backend settings can also come from $LLM_API_URL/$LLM_API_KEY/
        # $LLM_MODEL or config/llm_api_config.json -- set explicitly here
        # just to make this example self-contained.
        api_url="http://localhost:11434/v1/chat/completions",
        model="gemma2:latest",
    )

    pdf_to_excel_processor.run()
