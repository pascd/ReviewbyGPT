from reviewbygpt.lib.excel_data_parser import ExcelDataParser

if __name__ == "__main__":
    module = ExcelDataParser(excel_file_path="/home/pedrodias/Documents/git-repos/ReviewbyGPT/tests/test_dir")
    module.create_excel_file()