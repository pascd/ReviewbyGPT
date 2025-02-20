import os
import time
import pandas as pd
import logging
import shutil
import random
from pathlib import Path
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from reviewbygpt.lib.excel_data_parser import ExcelDataParser
from reviewbygpt.lib.response_handler import ResponseHandler
from reviewbygpt.lib.review_data_parser import ReviewDataParser

from webgpthandler.scripts.chatgpt_interaction_manager import ChatGPTInteractionManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFToExcelProcessor:
    def __init__(self, pdf_folder_path, review_config, qa_sheet_name, de_sheet_name, max_questions):
        self.pdf_folder_path = pdf_folder_path
        
        self.analysed_folder_path = os.path.join(pdf_folder_path, "analysed")
        self.excel_file_path = os.path.join(pdf_folder_path, "sheet")
        self.rejected_file_path = os.path.join(pdf_folder_path, "rejected")
        self.folder_pths = [self.analysed_folder_path, self.excel_file_path, self.rejected_file_path]

        self.qa_sheet_name = qa_sheet_name
        self.de_sheet_name = de_sheet_name
        self.chatgpt_manager = ChatGPTInteractionManager()
        self.response_handler = ResponseHandler()
        self.excel_parser = ExcelDataParser(self.excel_file_path)
        self.review_parser = ReviewDataParser(review_config)
        self.folder_names = ["accepted", "rejected", "sheet"]
        self.max_questions = max_questions

        # Load quality assessment and data extraction fields
        self.qa_fields = self.review_parser.get_all_quality_assessment_fields()
        self.data_extraction_fields = self.review_parser.get_all_data_extraction_fields()
        self.cutoff_score = self.review_parser.get_cutoff_score()
        self.excluding_questions = self.review_parser.get_all_excluding_questions()

    def initiate_chatgpt_manager(self):
        try:
            self.chatgpt_manager.launch_chatpgt_page()
            self.chatgpt_manager.login()
            pass
        except Exception as e:
            print(f"Error initiating chatgpt manager: {e}")
            return False
        
        return True

    def get_pdf_paths(self):
        if not os.path.exists(self.pdf_folder_path):
            raise FileNotFoundError(f"The folder '{self.pdf_folder_path}' does not exist.")
        return [os.path.join(self.pdf_folder_path, f) for f in os.listdir(self.pdf_folder_path) if f.lower().endswith(".pdf")]

    def send_pdf_to_analysis(self, pdf_file):
        try:
            return self.chatgpt_manager.send_and_receive(pdf_file)
        except Exception as e:
            logger.error(f"Error sending PDF for analysis: {e}")
            return None

    def move_analysed_file(self, file_path):
        if not os.path.exists(self.analysed_folder_path):
            os.makedirs(self.analysed_folder_path, exist_ok=True)
        try:
            shutil.move(file_path, self.analysed_folder_path)
            logger.info(f"Moved '{file_path}' to '{self.analysed_folder_path}'.")
        except Exception as e:
            logger.error(f"Error moving file '{file_path}': {e}")
            
    def move_rejected_file(self, file_path):
        if not os.path.exists(self.rejected_file_path):
            os.makedirs(self.rejected_file_path, exist_ok=True)
        try:
            shutil.move(file_path, self.rejected_file_path)
            logger.info(f"Moved '{file_path}' to '{self.rejected_file_path}'.")
        except Exception as e:
            logger.error(f"Error moving file '{file_path}': {e}")
            
    def create_folders(self):
            
        for folder in self.folder_pths:
        
            try:
                # Check if folder exists, and if not, create
                Path(folder).mkdir(parents=True, exist_ok=True)
                print(f"Created folder {folder}.")
            
            except Exception as e:
                print(f"Unable to create folder: {folder}.")
                self.delete_folders()
                
    def delete_folders(self):
            
        for folder in self.folder_pths:
        
            try:
                # Check if folder exists, and if true, remove it
                if os.path.exists(folder) and os.path.isdir(folder):
                    shutil.rmtree(folder)
            
            except Exception as e:
                print(f"Unable to create folder: {folder}.")

    def run(self):
        
        # Create folder for analysis
        self.create_folders()
        
        # Initialize the Excel sheets
        self.excel_parser.create_excel_file()
        qa_identifiers = [qa["id"] for qa in self.qa_fields]
        self.excel_parser.apply_excel_template(self.qa_sheet_name, qa_identifiers + ["Average Score"])
        de_identifiers = [de["key"] for de in self.data_extraction_fields]
        self.excel_parser.apply_excel_template(self.de_sheet_name, de_identifiers)

        # Initialize ChatGPT manager
        if self.initiate_chatgpt_manager(): 
            pass 
        else: 
            return False

        # Number of questions made
        num_question = 0
        
        for pdf_path in self.get_pdf_paths():
            
            if num_question == self.max_questions:
                self.chatgpt_manager.new_chat()
                num_question = 0
            
            try:
                logger.info(f"Processing file: {pdf_path}")
                self.chatgpt_manager.input_external_file(pdf_path)
                
                time.sleep(random.randint(2, 5))
                
                num_question += 1

                # Send analysis prompt and get response
                prompt = self.review_parser.get_analysis_prompt()
                response = self.send_pdf_to_analysis(prompt)

                if not response:
                    logger.warning(f"No response for file: {pdf_path}")
                    continue

                # Extract QA data and calculate average score
                qa_data = self.review_parser.get_quality_assessment_text(response)
                paper_score = qa_data.pop("Total Score", 0)  # Extract average score for logging
                if qa_data:
                    self.excel_parser.fill_excel_with_data(self.qa_sheet_name, {**qa_data, "Total Score": paper_score})
                    logger.info(f"Total QA Score: {paper_score}")
                else:
                    logger.warning(f"No QA data found for file: {pdf_path}")
                    
                # Check if any of the excluding questions have a score equal to "0"
                check_e_question = 0
                for e_question in self.excluding_questions:
                    if qa_data[f"{e_question} Score"] == 0:
                        print(f"Paper does not match the score needed for excluding question: {e_question}")
                        self.move_rejected_file(pdf_path)
                        check_e_question += 1
                
                if check_e_question != 0:
                    continue
                        
                # Extract and write DE data only if the score meets the cutoff
                if paper_score and paper_score >= self.cutoff_score:
                    logger.info(f"Paper score ({paper_score}) meets the cutoff ({self.cutoff_score}). Extracting DE data...")
                    de_data = self.review_parser.get_data_extraction_text(response)
                    if de_data:
                        self.excel_parser.fill_excel_with_data(self.de_sheet_name, de_data)
                    else:
                        logger.warning(f"No DE data found for file: {pdf_path}")
                else:
                    logger.info(f"Paper score ({paper_score}) does not meet the cutoff ({self.cutoff_score}). Skipping DE data extraction.")
                    self.move_rejected_file(pdf_path)
                    continue

                time.sleep(random.randint(2, 7))
                
            except Exception as e:
                logger.error(f"Error processing file '{pdf_path}': {e}")
        
        # End connection
        logging.info("Ending connection with ChatGPT.")
        self.chatgpt_manager.end()
        
        return True