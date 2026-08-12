"""Tests for PDFToExcelProcessor's folder management and PDF discovery.

These exercise the real class end-to-end for the parts of the pipeline that
don't require an LLM call (folder creation/cleanup, listing PDFs), using
`tmp_path` so nothing touches the real filesystem outside pytest's sandbox.
"""

from pathlib import Path

import pytest

from reviewbygpt.scripts.pdf_to_excel import PDFToExcelProcessor

REVIEW_CONFIG = Path(__file__).parent.parent / "config" / "review_data.yaml"


def _make_processor(pdf_folder_path):
    # api_url/model are never actually called by the tests below -- they're
    # only needed to satisfy LLMClient's constructor validation.
    return PDFToExcelProcessor(
        pdf_folder_path=str(pdf_folder_path),
        review_config=str(REVIEW_CONFIG),
        qa_sheet_name="qa_sheet",
        de_sheet_name="de_sheet",
        api_url="http://localhost:11434/v1/chat/completions",
        model="test-model",
    )


def test_create_and_delete_folders(tmp_path):
    processor = _make_processor(tmp_path)

    processor.create_folders()
    assert (tmp_path / "analysed").is_dir()
    assert (tmp_path / "sheet").is_dir()
    assert (tmp_path / "rejected").is_dir()

    processor.delete_folders()
    assert not (tmp_path / "analysed").exists()
    assert not (tmp_path / "sheet").exists()
    assert not (tmp_path / "rejected").exists()


def test_get_pdf_paths_lists_only_pdfs(tmp_path):
    (tmp_path / "paper1.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "notes.txt").write_text("not a pdf")

    processor = _make_processor(tmp_path)
    pdf_paths = processor.get_pdf_paths()

    assert len(pdf_paths) == 1
    assert pdf_paths[0].endswith("paper1.pdf")


def test_get_pdf_paths_raises_for_missing_folder(tmp_path):
    processor = _make_processor(tmp_path / "does-not-exist")
    with pytest.raises(FileNotFoundError):
        processor.get_pdf_paths()


def test_move_analysed_and_rejected_file(tmp_path):
    processor = _make_processor(tmp_path)
    processor.create_folders()

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    processor.move_analysed_file(str(pdf_path))

    assert (tmp_path / "analysed" / "paper.pdf").exists()
    assert not pdf_path.exists()
