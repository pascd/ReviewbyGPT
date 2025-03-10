import sys
import os
import time

# Dynamically add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from reviewbygpt.scripts.pdf_to_excel import PDFToExcelProcessor

if __name__ == "__main__":

    pdf_to_excel_processor = PDFToExcelProcessor(pdf_folder_path="./pdf-files/",
                                                 qa_sheet_name="qa_sheet",
                                                 de_sheet_name="de_sheet",
                                                 review_config="./review_data.yaml")

    pdf_to_excel_processor.run()