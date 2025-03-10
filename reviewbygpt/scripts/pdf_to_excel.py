import os
import time
import pandas as pd
import logging
import shutil
import random
import requests
import json
from pathlib import Path
import PyPDF2
import base64
import subprocess

from reviewbygpt.lib.excel_data_parser import ExcelDataParser
from reviewbygpt.lib.response_handler import ResponseHandler
from reviewbygpt.lib.review_data_parser import ReviewDataParser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaInteractionManager:
    """Class to manage interactions with Ollama API"""
    
    def __init__(self, base_url="http://localhost:11434", model="mistral:latest", use_gpu=True, max_content_length=None):
        self.base_url = base_url
        self.model = model
        self.use_gpu = use_gpu
        self.max_content_length = max_content_length  # Set to None for no truncation
        self.api_endpoint = f"{self.base_url}/api/generate"
        logger.info(f"Initialized Ollama interaction manager with model: {model} (GPU: {'enabled' if use_gpu else 'disabled'})")
        logger.info(f"PDF content truncation: {'disabled' if max_content_length is None else f'limited to {max_content_length} chars'}")
        
        # Check if CUDA is available when GPU is requested
        if use_gpu:
            self._check_cuda_availability()
            
        # Check installed Ollama version
        try:
            import subprocess
            result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Ollama version: {result.stdout.strip()}")
            else:
                logger.warning("Unable to determine Ollama version")
        except Exception as e:
            logger.warning(f"Error checking Ollama version: {e}")
            
    def _check_cuda_availability(self):
        """Check if CUDA is available for GPU inference"""
        try:
            # Check if the CUDA libraries are available
            result = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True)
            cuda_libs = [line for line in result.stdout.split('\n') if 'libcudart.so' in line]
            
            if cuda_libs:
                logger.info(f"CUDA libraries found: {cuda_libs}")
            else:
                logger.warning("CUDA libraries not found in system paths. GPU acceleration may not work.")
                logger.warning("Consider installing CUDA libraries: sudo apt install nvidia-cuda-toolkit")
                
            # Check if nvidia-smi command works
            nvidia_result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
            if nvidia_result.returncode == 0:
                logger.info("NVIDIA GPU detected and working")
                # Extract useful GPU info
                gpu_info = nvidia_result.stdout.split('\n')
                for line in gpu_info[:15]:  # Get just the important first few lines
                    if line.strip():
                        logger.info(f"GPU info: {line.strip()}")
            else:
                logger.warning("nvidia-smi command failed. NVIDIA drivers may not be properly installed.")
                
        except Exception as e:
            logger.warning(f"Error checking CUDA availability: {e}")
            
    def verify_connection(self):
        """Verify the connection to the Ollama API"""
        try:
            logger.info(f"Attempting to connect to Ollama API at {self.base_url}")
            
            # Detailed connection attempt with timeout
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            
            # Log full response for debugging
            logger.info(f"Ollama API response status: {response.status_code}")
            logger.info(f"Ollama API response: {response.text[:500]}...")  # Truncated for readability
            
            if response.status_code == 200:
                available_models = response.json().get("models", [])
                model_names = [model.get("name") for model in available_models]
                
                logger.info(f"Available models: {model_names}")
                
                if self.model in model_names:
                    logger.info(f"Successfully connected to Ollama API. Model '{self.model}' is available.")
                    return True
                else:
                    logger.error(f"Model '{self.model}' not found. Available models: {model_names}")
                    # If model is not found but others are available, suggest them
                    if model_names:
                        logger.info(f"Consider using one of these available models instead: {model_names}")
                    return False
            else:
                logger.error(f"Failed to connect to Ollama API. Status code: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            logger.info("Ollama may not be running. Try starting it with 'ollama serve'")
            return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Connection timeout: {e}")
            logger.info("The connection to Ollama timed out. Check if the service is overloaded.")
            return False
        except Exception as e:
            logger.error(f"Error connecting to Ollama API: {e}")
            return False
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract text content from a PDF file"""
        try:
            text = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                logger.info(f"Extracting text from PDF: {pdf_path} ({num_pages} pages)")
                
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    text += page_text
                    
                    # Log progress for large PDFs
                    if num_pages > 10 and page_num % 5 == 0:
                        logger.info(f"Extracted {page_num+1}/{num_pages} pages...")
            
            # Log info about extracted content
            text_length = len(text)
            logger.info(f"Successfully extracted {text_length} characters from PDF")
            
            # Log a sample of the content to verify extraction
            sample_length = min(200, text_length)
            logger.info(f"Sample of extracted text: {text[:sample_length]}...")
            
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF '{pdf_path}': {e}")
            return None
    
    def send_prompt(self, prompt, pdf_content=None):
        """Send a prompt to the Ollama API and get the response"""
        try:
            # Combine PDF content with prompt if provided
            if pdf_content:
                # Only truncate if max_content_length is specified
                if self.max_content_length and len(pdf_content) > self.max_content_length:
                    logger.warning(f"PDF content length ({len(pdf_content)} chars) exceeds limit ({self.max_content_length}), truncating")
                    pdf_content = pdf_content[:self.max_content_length] + "... [Content truncated due to length]"
                else:
                    logger.info(f"Using full PDF content ({len(pdf_content)} chars)")
                
                # Simplify prompt structure for better compatibility
                full_prompt = f"PDF CONTENT:\n{pdf_content}\n\nTASK:\n{prompt}"
            else:
                full_prompt = prompt
            
            # Log payload size for debugging
            prompt_size = len(full_prompt)
            logger.info(f"Sending prompt to Ollama (size: {prompt_size} chars)")
            
            # Set GPU options based on configuration
            gpu_options = {}
            if not self.use_gpu:
                gpu_options["num_gpu"] = 0  # Force CPU-only mode
                logger.info("Using CPU-only mode for inference")
            else:
                # For GPU mode, we might want to specify all layers on GPU
                gpu_options["num_gpu"] = 100  # Setting a high number ensures all compatible layers use GPU
                logger.info("Using GPU acceleration for inference")
            
            # First try the chat API which often works better with longer contexts
            try:
                chat_endpoint = f"{self.base_url}/api/chat"
                logger.info(f"Trying Ollama chat API at {chat_endpoint}")
                
                chat_payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": full_prompt}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        **gpu_options
                    }
                }
                
                # Log that we're sending the request
                logger.info(f"Sending request to Ollama chat API with {'GPU' if self.use_gpu else 'CPU'} mode")
                logger.info(f"Request timeout set to 600 seconds (10 minutes)")
                
                # Increased timeout for very large documents
                response = requests.post(chat_endpoint, json=chat_payload, timeout=600)
                
                if response.status_code == 200:
                    logger.info("Successfully received response from chat API")
                    chat_response = response.json()
                    return chat_response.get("message", {}).get("content", "")
                else:
                    logger.warning(f"Chat API failed with status {response.status_code}, falling back to generate API")
            except Exception as e:
                logger.warning(f"Error using chat API, falling back to generate API: {e}")
            
            # Fall back to the standard generate API
            logger.info(f"Sending request to Ollama generate API at {self.api_endpoint}")
            
            # Use more compatible API parameters
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 1024,  # Increased for more comprehensive responses
                    **gpu_options
                }
            }
            
            response = requests.post(self.api_endpoint, json=payload, timeout=600)  # 10 minute timeout
            
            if response.status_code == 200:
                response_data = response.json()
                response_text = response_data.get("response", "")
                logger.info(f"Received response from Ollama (length: {len(response_text)} chars)")
                return response_text
            else:
                logger.error(f"Error from Ollama API: {response.status_code} - {response.text}")
                
                # Provide specific troubleshooting advice based on error
                if "exit status 127" in response.text:
                    if "libcudart" in response.text:
                        logger.error("CUDA libraries are missing. Try installing with: sudo apt install nvidia-cuda-toolkit")
                        logger.error("Or switch to CPU-only mode by setting use_gpu=False")
                    else:
                        logger.error("Error 127 typically means the model executable wasn't found.")
                        logger.error("Try pulling the model again with: ollama pull " + self.model)
                return None
        except requests.exceptions.Timeout:
            logger.error("Request to Ollama API timed out. The model may be taking too long to process the PDF.")
            return None
        except Exception as e:
            logger.error(f"Error sending prompt to Ollama API: {e}")
            return None
            
    def new_conversation(self):
        """Reset the conversation context by creating a new one"""
        logger.info("Starting a new conversation with Ollama")
        # No actual API call needed as Ollama doesn't maintain conversation state in this implementation
        return True


class PDFToExcelProcessor:
    def __init__(self, pdf_folder_path, review_config, qa_sheet_name, de_sheet_name, max_questions, 
                 ollama_url="http://localhost:11434", ollama_model="mistral:latest", 
                 use_gpu=True, max_content_length=None):
        self.pdf_folder_path = pdf_folder_path
        
        self.analysed_folder_path = os.path.join(pdf_folder_path, "analysed")
        self.excel_file_path = os.path.join(pdf_folder_path, "sheet")
        self.rejected_file_path = os.path.join(pdf_folder_path, "rejected")
        self.folder_pths = [self.analysed_folder_path, self.excel_file_path, self.rejected_file_path]

        self.qa_sheet_name = qa_sheet_name
        self.de_sheet_name = de_sheet_name
        self.use_gpu = use_gpu
        
        # Initialize Ollama manager with GPU support and no content truncation
        self.ollama_manager = OllamaInteractionManager(
            base_url=ollama_url, 
            model=ollama_model, 
            use_gpu=use_gpu,
            max_content_length=max_content_length
        )
        
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

    def initiate_ollama_manager(self):
        """Initialize connection to Ollama"""
        try:
            if self.ollama_manager.verify_connection():
                logger.info("Successfully connected to Ollama")
                return True
            else:
                logger.error("Failed to connect to Ollama")
                return False
        except Exception as e:
            logger.error(f"Error initiating Ollama manager: {e}")
            return False

    def get_pdf_paths(self):
        if not os.path.exists(self.pdf_folder_path):
            raise FileNotFoundError(f"The folder '{self.pdf_folder_path}' does not exist.")
        return [os.path.join(self.pdf_folder_path, f) for f in os.listdir(self.pdf_folder_path) if f.lower().endswith(".pdf")]

    def send_pdf_to_analysis(self, pdf_path, prompt):
        """Send PDF content and analysis prompt to Ollama"""
        try:
            # Extract text from PDF
            pdf_content = self.ollama_manager.extract_text_from_pdf(pdf_path)
            if not pdf_content:
                logger.error(f"Could not extract text from PDF: {pdf_path}")
                return None
            
            # Log information about the content and prompt being sent
            pdf_content_length = len(pdf_content)
            prompt_length = len(prompt)
            logger.info(f"Preparing to send PDF content ({pdf_content_length} chars) and prompt ({prompt_length} chars) to Ollama")
            
            # Create a debug file with the exact content being sent
            debug_dir = os.path.join(os.path.dirname(pdf_path), "debug_logs")
            os.makedirs(debug_dir, exist_ok=True)
            
            pdf_filename = os.path.basename(pdf_path)
            debug_filename = os.path.join(debug_dir, f"{os.path.splitext(pdf_filename)[0]}_debug.txt")
            
            with open(debug_filename, 'w', encoding='utf-8') as f:
                f.write("===== PDF CONTENT =====\n\n")
                f.write(pdf_content[:5000])  # First 5000 chars for the debug file
                f.write("\n\n... [content truncated for debug file only] ...\n\n")
                f.write("===== PROMPT =====\n\n")
                f.write(prompt)
            
            logger.info(f"Saved debug content to {debug_filename}")
                
            # Send prompt and PDF content to Ollama
            response = self.ollama_manager.send_prompt(prompt, pdf_content)
            
            # Log information about the response
            if response:
                response_length = len(response)
                logger.info(f"Received response from Ollama: {response_length} characters")
                
                # Log the full response text
                logger.info("===== LLM RESPONSE BEGIN =====")
                logger.info(response[:1000] + "..." if len(response) > 1000 else response)  # Truncate in logs only
                logger.info("===== LLM RESPONSE END =====")
                
                # Save the response to a debug file
                response_filename = os.path.join(debug_dir, f"{os.path.splitext(pdf_filename)[0]}_response.txt")
                with open(response_filename, 'w', encoding='utf-8') as f:
                    f.write(response)
                logger.info(f"Saved response to {response_filename}")
            else:
                logger.error("No response received from Ollama")
                
            return response
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
                print(f"Unable to delete folder: {folder}.")

    def run(self):
        # Create folder for analysis
        self.create_folders()
        
        # Initialize the Excel sheets
        self.excel_parser.create_excel_file()
        qa_identifiers = [qa["id"] for qa in self.qa_fields]
        self.excel_parser.apply_excel_template(self.qa_sheet_name, qa_identifiers + ["Average Score"])
        de_identifiers = [de["key"] for de in self.data_extraction_fields]
        self.excel_parser.apply_excel_template(self.de_sheet_name, de_identifiers)

        # Initialize Ollama manager
        if not self.initiate_ollama_manager():
            logger.error("Failed to initialize Ollama connection. Exiting.")
            return False

        # Number of questions made
        num_question = 0
        
        # Configure log file for responses
        response_log_file = os.path.join(self.pdf_folder_path, "llm_responses.log")
        with open(response_log_file, 'w', encoding='utf-8') as log_file:
            log_file.write(f"=== LLM Response Log - Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
            log_file.write(f"Using model: {self.ollama_manager.model}\n")
            log_file.write(f"GPU acceleration: {'enabled' if self.use_gpu else 'disabled'}\n")
            log_file.write(f"Content truncation: {'disabled' if self.ollama_manager.max_content_length is None else 'enabled'}\n\n")
        
        logger.info(f"Created LLM response log file at: {response_log_file}")
        
        for pdf_path in self.get_pdf_paths():
            if pdf_path.lower().endswith(".pdf"):
                if num_question == self.max_questions:
                    self.ollama_manager.new_conversation()
                    num_question = 0
                
                try:
                    logger.info(f"Processing file: {pdf_path}")
                    
                    # Get the analysis prompt
                    prompt = self.review_parser.get_analysis_prompt()
                    
                    # Send PDF and prompt for analysis
                    response = self.send_pdf_to_analysis(pdf_path, prompt)
                    num_question += 1
                    
                    # Write the response to the consolidated log file
                    with open(response_log_file, 'a', encoding='utf-8') as log_file:
                        log_file.write(f"\n\n{'='*80}\n")
                        log_file.write(f"PDF: {os.path.basename(pdf_path)}\n")
                        log_file.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                        log_file.write(f"{'='*80}\n\n")
                        
                        if response:
                            log_file.write(response)
                        else:
                            log_file.write("*** NO RESPONSE RECEIVED ***")
                    
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
                        if qa_data.get(f"{e_question} Score", 1) == 0:  # Default to 1 if key not found
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

                    # Move the processed file to analysed folder
                    self.move_analysed_file(pdf_path)
                    
                    # Add a small delay between processing files
                    time.sleep(random.randint(1, 3))
                    
                except Exception as e:
                    logger.error(f"Error processing file '{pdf_path}': {e}")
            else:
                logger.info(f"Skipping non-PDF file: {pdf_path}")
        
        logger.info("Completed PDF processing with Ollama LLM.")
        return True