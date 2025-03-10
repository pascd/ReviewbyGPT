import sys, os

# Dynamically add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from reviewbygpt.scripts.pdf_to_excel import PDFToExcelProcessor
from reviewbygpt.lib.review_data_parser import ReviewDataParser
from reviewbygpt.lib.excel_data_parser import ExcelDataParser

import logging
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    review_parser = ReviewDataParser(config="/home/pedrodias/Documents/git-repos/ReviewbyGPT/config/review_data.yaml")
    excel_parser = ExcelDataParser(excel_file_path="/home/pedrodias/Documents/git-repos/ReviewbyGPT/config/")

    response = """
    ==QUALITY_ASSESSMENT_START== QE1: The methodology focuses on a hybrid disassembly line balancing problem using an improved tabu search algorithm. The approach is well-structured for addressing multi-robot task allocation and optimization. However, while the algorithm is well detailed, it lacks specific discussion on the physical challenges of disassembly tasks, such as force dynamics and uncertainties in real-world robotic disassembly. QE1_SCORE: 0.5
QE2: The paper provides a mathematical model of the hybrid disassembly line and describes the use of tabu search for task allocation. However, details on the physical robotic cell setup, including actual hardware implementation, are sparse. QE2_SCORE: 1.0
QE3: The results are supported by experimental validation using real-world examples (washing machines and table lamps). Performance comparisons between different configurations and optimization strategies are discussed, but further comparison with state-of-the-art techniques could enhance credibility. QE3_SCORE: 1.0
QE4: The study primarily focuses on simulation-based research, employing a mathematical model and optimization algorithm for solving disassembly line balancing problems. This is clearly stated in the paper. QE4_SCORE: 1.0
QE5: There is no mention of publicly available datasets or open-source implementation of the tabu search algorithm. The work appears to be conducted in a closed experimental environment. QE5_SCORE: 0.0
QE6: The proposed solution is directly aimed at disassembly tasks, specifically focusing on hybrid disassembly lines with multi-robot coordination. QE6_SCORE: 1.0
QE7: The paper presents comparative results using different configurations of the proposed algorithm. However, comparisons with other existing disassembly methods or ground-truth datasets are lacking. QE7_SCORE: 0.5
QE8: The literature review covers various prior works on disassembly line balancing and optimization methods. However, while relevant references are included, the paper does not provide a comprehensive, up-to-date review of the state-of-the-art in robotic disassembly. QE8_SCORE: 0.5 ==QUALITY_ASSESSMENT_END==
==DATA_EXTRACTION_START== AUTHOR: Shiqi Zhang, Peisheng Liu, XiWang Guo, Jiacun Wang, Shujin Qin, Ying Tang YEAR: 2022 TITLE: An Improved Tabu Search Algorithm for Multi-robot Hybrid Disassembly Line Balancing Problems PUBLISHER: IEEE NUMBER OF MANIPULATORS: N/S MANIPULATOR: N/S DOF OF MANIPULATOR: N/S HARDWARE CELL COMPONENTS: N/S SOFTWARE ARCHITECTURE COMPONENTS: Tabu search algorithm, greedy algorithm, AND/OR graph representation VISION SYSTEM: N/S USE OF CAD MODEL: N/S LEVEL OF IMPLEMENTATION: Simulation-based (Conceptual/Experimental) LEVEL OF AUTOMATION: Fully automated PROCESS STEPS: Task allocation, disassembly sequence optimization, hybrid disassembly line balancing EFFICIENCY CONSIDERATIONS: Cost, time, and optimization of workstation and robot usage OPTIMIZATION OF DISASSEMBLY TASKS: Yes, optimization of cost and efficiency in hybrid disassembly lines CHALLENGES: Multi-product disassembly, cost-effective task allocation, balancing between different disassembly line types HOW TO: Implemented an improved tabu search algorithm with two neighborhood structures for optimizing the disassembly sequence RESULTS: Improved disassembly profit, better performance compared to initial feasible solutions, validation through simulation experiments ==DATA_EXTRACTION_END==
    """

    qa_sheet_name = "qa_sheet"
    de_sheet_name = "de_sheet"
    cutoff_score = 2.5

    # Initialize the Excel sheets
    excel_parser.create_excel_file()
    qa_fields = review_parser.get_all_quality_assessment_fields()
    qa_identifiers = []
    for qa in qa_fields:
        qa_identifiers.append(f"{qa["id"]}")
        qa_identifiers.append(f"{qa["id"]}_SCORE")

    #qa_identifiers = [qa["id"] for qa in qa_fields]
    excel_parser.apply_excel_template(qa_sheet_name, qa_identifiers + ["TOTAL_SCORE"])
    data_extraction_fields = review_parser.get_all_data_extraction_fields()

    de_identifiers = [de["key"] for de in data_extraction_fields]
    excel_parser.apply_excel_template(de_sheet_name, de_identifiers)
    print(de_identifiers)

    # Extract QA data and calculate average score
    qa_data = review_parser.get_quality_assessment_text(response)
    de_data = review_parser.get_data_extraction_text(response)
    paper_score = qa_data.pop("TOTAL_SCORE", 0)

    for title_key in ["TITLE", "Title", "title"]:
            if title_key in de_data:
                paper_title = de_data[title_key]
                logger.info(f"Found title: {paper_title}")
                break

    # Add title to QA data
    qa_data["Title"] = paper_title

    if qa_data:
        print(qa_data)
        excel_parser.fill_excel_with_data(qa_sheet_name, {**qa_data, "TOTAL_SCORE": paper_score})
        print(f"Total QA Score: {paper_score}")

    # Extract and write DE data only if the score meets the cutoff
    if paper_score and paper_score >= cutoff_score:
        print(f"Paper score ({paper_score}) meets the cutoff ({cutoff_score}). Extracting DE data...")

        if de_data:
            # Make sure the title in DE data matches what we used in QA data
            if "TITLE" in de_data and paper_title:
                de_data["TITLE"] = paper_title
                
            excel_parser.fill_excel_with_data(de_sheet_name, de_data)
        else:
            print(f"No DE data found for response.")
    else:
        print(f"No QA data found for response")