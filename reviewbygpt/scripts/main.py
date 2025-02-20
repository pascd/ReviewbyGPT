from pdf_to_excel import PDFToExcelProcessor

def main():
    
    module = PDFToExcelProcessor(pdf_folder_path="/home/pedrodias/Documents/phd/systematic-review-disassebly",
                                 review_config="/home/pedrodias/Documents/git-repos/ReviewbyGPT/config/review_data.yaml",
                                 qa_sheet_name="qa_sheet",
                                 de_sheet_name="de_sheet",
                                 max_questions=10)
    
    module.run()


if __name__ == "__main__":
    
    main()