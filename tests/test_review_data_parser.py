"""Tests for ReviewDataParser: prompt building and response parsing.

These tests never call a live LLM -- they feed a hand-written response
string (shaped exactly like what get_analysis_prompt() asks a model to
produce) into the parsing methods and check the result. This exercises the
same code path a real run takes after receiving an LLM response, without
needing network access or a running backend.
"""

from pathlib import Path

import pytest

from reviewbygpt.lib.review_data_parser import ReviewDataParser

REVIEW_CONFIG = Path(__file__).parent.parent / "config" / "review_data.yaml"

# A response shaped exactly like the format get_analysis_prompt() requests:
# ==QUALITY_ASSESSMENT_START/END== and ==DATA_EXTRACTION_START/END== marker
# blocks, with "QEn: <text> QEn_SCORE: <score>" items and "KEY: value" fields.
SAMPLE_RESPONSE = """
==QUALITY_ASSESSMENT_START== QE1: Methodology description. QE1_SCORE: 0.5
QE2: Solution description. QE2_SCORE: 1.0
QE3: Discussion description. QE3_SCORE: 1.0
QE4: Research type description. QE4_SCORE: 1.0
QE5: Availability description. QE5_SCORE: 0.0
QE6: Disassembly focus description. QE6_SCORE: 1.0
QE7: Comparative results description. QE7_SCORE: 0.5
QE8: State of the art description. QE8_SCORE: 0.5 ==QUALITY_ASSESSMENT_END==
==DATA_EXTRACTION_START== AUTHOR: Jane Doe, John Smith YEAR: 2022 TITLE: An Example Paper Title PUBLISHER: IEEE NUMBER OF MANIPULATORS: N/S MANIPULATOR: N/S DOF OF MANIPULATOR: N/S HARDWARE CELL COMPONENTS: N/S SOFTWARE ARCHITECTURE COMPONENTS: Tabu search algorithm VISION SYSTEM: N/S USE OF CAD MODEL: N/S LEVEL OF IMPLEMENTATION: Simulation-based LEVEL OF AUTOMATION: Fully automated PROCESS STEPS: Task allocation EFFICIENCY CONSIDERATIONS: Cost and time OPTIMIZATION OF DISASSEMBLY TASKS: Yes CHALLENGES: Multi-product disassembly HOW TO: Implemented an improved algorithm RESULTS: Improved disassembly profit ==DATA_EXTRACTION_END==
"""


@pytest.fixture
def review_parser():
    return ReviewDataParser(config=str(REVIEW_CONFIG))


def test_get_all_quality_assessment_fields(review_parser):
    fields = review_parser.get_all_quality_assessment_fields()
    assert len(fields) == 8
    assert {f["id"] for f in fields} == {f"QE{i}" for i in range(1, 9)}


def test_get_all_data_extraction_fields(review_parser):
    fields = review_parser.get_all_data_extraction_fields()
    assert {f["key"] for f in fields} >= {"TITLE", "AUTHOR", "YEAR"}


def test_get_cutoff_score_and_excluding_questions(review_parser):
    assert review_parser.get_cutoff_score() == 6.5
    assert review_parser.get_all_excluding_questions() == ["QE1", "QE7", "QE8"]


def test_get_analysis_prompt_contains_section_markers(review_parser):
    prompt = review_parser.get_analysis_prompt()
    assert "==QUALITY_ASSESSMENT_START==" in prompt
    assert "==DATA_EXTRACTION_START==" in prompt
    assert "QE1" in prompt


def test_get_quality_assessment_text_extracts_scores(review_parser):
    qa_data = review_parser.get_quality_assessment_text(SAMPLE_RESPONSE)

    assert qa_data["QE1_SCORE"] == 0.5
    assert qa_data["QE5_SCORE"] == 0.0
    # 0.5 + 1.0 + 1.0 + 1.0 + 0.0 + 1.0 + 0.5 + 0.5
    assert qa_data["TOTAL_SCORE"] == pytest.approx(5.5)


def test_get_data_extraction_text_extracts_fields(review_parser):
    de_data = review_parser.get_data_extraction_text(SAMPLE_RESPONSE)

    assert de_data["TITLE"] == "An Example Paper Title"
    assert de_data["AUTHOR"] == "Jane Doe, John Smith"
    assert de_data["YEAR"] == "2022"
    assert de_data["PUBLISHER"] == "IEEE"


def test_get_quality_assessment_text_without_markers_falls_back(review_parser):
    # No ==QUALITY_ASSESSMENT_START/END== markers -- exercises the legacy
    # fallback path (_legacy_get_quality_assessment_text).
    unmarked_response = "QE1: Some description QE1_SCORE: 1.0"
    qa_data = review_parser.get_quality_assessment_text(unmarked_response)
    assert qa_data["QE1_SCORE"] == 1.0
