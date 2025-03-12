#!/usr/bin/env python3
import os
import sys
import logging
import argparse
import tkinter as tk
from tkinter import scrolledtext, messagebox, StringVar, OptionMenu, Frame, Label, Button
import pyperclip

from reviewbygpt.lib.excel_data_parser import ExcelDataParser
from reviewbygpt.lib.review_data_parser import ReviewDataParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('response_processor.log')
    ]
)
logger = logging.getLogger(__name__)

class ResponseProcessor:
    def __init__(self, excel_dir, review_config, qa_sheet_name="qa_sheet", de_sheet_name="de_sheet"):
        """
        Initialize the response processor
        
        Args:
            excel_dir (str): Directory containing the Excel file
            review_config (str): Path to the review configuration file
            qa_sheet_name (str): Name of the quality assessment sheet
            de_sheet_name (str): Name of the data extraction sheet
        """
        self.excel_dir = excel_dir
        self.review_config = review_config
        self.qa_sheet_name = qa_sheet_name
        self.de_sheet_name = de_sheet_name
        
        # Initialize parsers
        self.review_parser = ReviewDataParser(review_config)
        self.excel_parser = ExcelDataParser(excel_dir, review_config)
        
        # Get cutoff score
        self.cutoff_score = self.review_parser.get_cutoff_score()
        self.excluding_questions = self.review_parser.get_all_excluding_questions()
        
        # Check if Excel file exists, create if not
        self._ensure_excel_file_exists()
        
    def _ensure_excel_file_exists(self):
        """Ensure the Excel file exists with proper sheets and headers"""
        try:
            # Create Excel file if it doesn't exist
            if not os.path.exists(os.path.join(self.excel_dir, "analysed.xlsx")):
                logger.info("Creating new Excel file")
                self.excel_parser.create_excel_file()
            
            # Set up QA sheet
            qa_fields = self.review_parser.get_all_quality_assessment_fields()
            qa_identifiers = []
            for qa in qa_fields:
                qa_identifiers.append(f"{qa['id']}")
                qa_identifiers.append(f"{qa['id']}_SCORE")
            
            self.excel_parser.apply_excel_template(
                self.qa_sheet_name, 
                ["TITLE"] + qa_identifiers + ["TOTAL_SCORE"]
            )
            
            # Set up DE sheet
            de_fields = self.review_parser.get_all_data_extraction_fields()
            de_identifiers = [de["key"] for de in de_fields]
            self.excel_parser.apply_excel_template(self.de_sheet_name, de_identifiers)
            
            logger.info("Excel file and sheets are ready")
            return True
        except Exception as e:
            logger.error(f"Error ensuring Excel file exists: {e}")
            return False
    
    def process_response(self, response_text):
        """
        Process a response text and insert into Excel sheets
        
        Args:
            response_text (str): The LLM response text
            
        Returns:
            dict: Results of processing with keys 'success', 'title', 'score', 'qa_added', 'de_added'
        """
        result = {
            'success': False,
            'title': None,
            'score': 0,
            'qa_added': False,
            'de_added': False,
            'rejected': False,
            'reason': None
        }
        
        try:
            # First extract the data extraction text to get the title
            de_data = self.review_parser.get_data_extraction_text(response_text)
            
            # Try to get the title
            paper_title = None
            for title_key in ["TITLE", "Title", "title"]:
                if title_key in de_data:
                    paper_title = de_data[title_key]
                    logger.info(f"Found title: {paper_title}")
                    result['title'] = paper_title
                    break
            
            # If no title found, use a generic one
            if not paper_title:
                paper_title = f"Untitled Paper {__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}"
                logger.warning(f"No title found, using generic title: {paper_title}")
                result['title'] = paper_title
            
            # Extract QA data and calculate score
            qa_data = self.review_parser.get_quality_assessment_text(response_text)
            paper_score = qa_data.pop("TOTAL_SCORE", 0)
            result['score'] = paper_score
            
            # Add title to QA data
            qa_data["TITLE"] = paper_title
            
            # Check if any excluding questions have a score of 0
            for e_question in self.excluding_questions:
                if qa_data.get(f"{e_question}_SCORE", -1) == 0:
                    logger.info(f"Paper rejected due to zero score on excluding question: {e_question}")
                    result['rejected'] = True
                    result['reason'] = f"Zero score on excluding question: {e_question}"
                    break
            
            # Add QA data to Excel sheet
            if qa_data:
                self.excel_parser.fill_excel_with_data(
                    self.qa_sheet_name, 
                    {**qa_data, "TOTAL_SCORE": paper_score}
                )
                logger.info(f"Added QA data for '{paper_title}' with score {paper_score}")
                result['qa_added'] = True
            else:
                logger.warning("No QA data found in response")
            
            # Check if score meets cutoff and not rejected by excluding questions
            if paper_score >= self.cutoff_score and not result['rejected']:
                # Add DE data to Excel sheet
                if de_data:
                    # Make sure the title matches what we used in QA
                    de_data["TITLE"] = paper_title
                    self.excel_parser.fill_excel_with_data(self.de_sheet_name, de_data)
                    logger.info(f"Added DE data for '{paper_title}'")
                    result['de_added'] = True
                else:
                    logger.warning("No DE data found in response")
            else:
                if not result['rejected']:
                    logger.info(f"Paper score ({paper_score}) below cutoff ({self.cutoff_score}), skipping DE data")
                    result['reason'] = f"Score ({paper_score}) below cutoff ({self.cutoff_score})"
                    result['rejected'] = True
            
            result['success'] = True
            return result
        
        except Exception as e:
            logger.error(f"Error processing response: {e}")
            result['reason'] = str(e)
            return result

    def save_response_to_file(self, response_text, title=None, custom_dir=None):
        """
        Save the response text to a file for reference
        
        Args:
            response_text (str): The LLM response text to save
            title (str, optional): Title of the paper for filename generation
            custom_dir (str, optional): Custom directory to save response file
            
        Returns:
            str: Path to saved file or None if failed
        """
        try:
            # Determine the directory to save to
            if custom_dir:
                responses_dir = custom_dir
            else:
                responses_dir = os.path.join(self.excel_dir, "responses")
            
            # Create directory if it doesn't exist
            os.makedirs(responses_dir, exist_ok=True)
            
            # Generate filename from title or timestamp
            if title:
                # Clean up title for use as filename
                filename = "".join(c if c.isalnum() or c in [' ', '_', '-'] else '_' for c in title)
                filename = filename.replace(' ', '_')[:50]  # Limit length
            else:
                filename = f"response_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            filepath = os.path.join(responses_dir, f"{filename}_response.txt")
            
            # Save the response
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(response_text)
            
            logger.info(f"Saved response to file: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error saving response to file: {e}")
            return None


class ResponseProcessorGUI:
    def __init__(self, excel_dir=None, config_file=None, save_dir=None):
        self.root = tk.Tk()
        self.root.title("Response Processor")
        
        # Set default paths if not provided
        self.excel_dir = excel_dir or os.path.join(os.getcwd(), "data", "excel")
        self.config_file = config_file or os.path.join(os.getcwd(), "config", "review_config.yaml")
        self.save_dir = save_dir  # Custom directory to save response files
        
        # Initialize processor with default values
        self.processor = None
        self.setup_processor()
        
        # Create GUI elements
        self.create_widgets()
        
        # Set window size
        self.root.geometry("800x700")
        self.root.minsize(600, 500)
        
    def setup_processor(self):
        """Initialize the response processor"""
        try:
            self.processor = ResponseProcessor(
                excel_dir=self.excel_dir,
                review_config=self.config_file
            )
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialize processor: {e}")
            return False
        
    def create_widgets(self):
        """Create all GUI elements"""
        # Main frame
        main_frame = Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configuration section
        config_frame = Frame(main_frame)
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        Label(config_frame, text="Excel Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.excel_dir_var = StringVar(value=self.excel_dir)
        Label(config_frame, textvariable=self.excel_dir_var, width=50, 
              anchor='w', bg='white', relief='sunken').grid(row=0, column=1, sticky=tk.W, pady=2)
        Button(config_frame, text="Browse", command=self.browse_excel_dir).grid(row=0, column=2, padx=5)
        
        Label(config_frame, text="Config File:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.config_file_var = StringVar(value=self.config_file)
        Label(config_frame, textvariable=self.config_file_var, width=50,
              anchor='w', bg='white', relief='sunken').grid(row=1, column=1, sticky=tk.W, pady=2)
        Button(config_frame, text="Browse", command=self.browse_config_file).grid(row=1, column=2, padx=5)
        
        Label(config_frame, text="Save Responses To:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.save_dir_var = StringVar(value=self.save_dir if self.save_dir else "")
        Label(config_frame, textvariable=self.save_dir_var, width=50,
              anchor='w', bg='white', relief='sunken').grid(row=2, column=1, sticky=tk.W, pady=2)
        Button(config_frame, text="Browse", command=self.browse_save_dir).grid(row=2, column=2, padx=5)
        
        Button(config_frame, text="Reload Configuration", command=self.reload_config).grid(
            row=3, column=0, columnspan=3, pady=(10, 0))
        
        # Response text area
        Label(main_frame, text="Paste Response Text:").pack(anchor=tk.W)
        self.response_text = scrolledtext.ScrolledText(main_frame, height=25)
        self.response_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Buttons frame
        button_frame = Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        Button(button_frame, text="Paste from Clipboard", 
               command=self.paste_from_clipboard).pack(side=tk.LEFT, padx=5)
        Button(button_frame, text="Clear Text", 
               command=self.clear_text).pack(side=tk.LEFT, padx=5)
        Button(button_frame, text="Process Response", 
               command=self.process_response, bg="#a0c8f0").pack(side=tk.RIGHT, padx=5)
        
        # Status frame
        status_frame = Frame(main_frame, relief=tk.SUNKEN, bd=1)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_var = StringVar(value="Ready")
        self.status_label = Label(status_frame, textvariable=self.status_var, 
                                  anchor=tk.W, padx=5, pady=5)
        self.status_label.pack(fill=tk.X)
        
    def browse_excel_dir(self):
        """Open directory browser for Excel directory"""
        from tkinter import filedialog
        dir_path = filedialog.askdirectory(title="Select Excel Directory")
        if dir_path:
            self.excel_dir = dir_path
            self.excel_dir_var.set(dir_path)
    
    def browse_config_file(self):
        """Open file browser for config file"""
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(
            title="Select Config File",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")]
        )
        if file_path:
            self.config_file = file_path
            self.config_file_var.set(file_path)
            
    def browse_save_dir(self):
        """Open directory browser for response save directory"""
        from tkinter import filedialog
        dir_path = filedialog.askdirectory(title="Select Directory to Save Responses")
        if dir_path:
            self.save_dir = dir_path
            self.save_dir_var.set(dir_path)
    
    def reload_config(self):
        """Reload the processor with current paths"""
        self.excel_dir = self.excel_dir_var.get()
        self.config_file = self.config_file_var.get()
        self.save_dir = self.save_dir_var.get() if self.save_dir_var.get() else None
        
        if self.setup_processor():
            self.status_var.set("Configuration reloaded successfully")
            self.status_label.config(fg="green")
        else:
            self.status_var.set("Failed to reload configuration")
            self.status_label.config(fg="red")
    
    def paste_from_clipboard(self):
        """Paste clipboard content into the text area"""
        try:
            self.response_text.delete(1.0, tk.END)
            clipboard_text = pyperclip.paste()
            self.response_text.insert(tk.END, clipboard_text)
            self.status_var.set("Pasted from clipboard")
            self.status_label.config(fg="black")
        except Exception as e:
            self.status_var.set(f"Error pasting from clipboard: {e}")
            self.status_label.config(fg="red")
    
    def clear_text(self):
        """Clear the text area"""
        self.response_text.delete(1.0, tk.END)
        self.status_var.set("Text cleared")
        self.status_label.config(fg="black")
    
    def process_response(self):
        """Process the response text and update Excel"""
        # Get the response text
        response_text = self.response_text.get(1.0, tk.END)
        
        if not response_text.strip():
            messagebox.showwarning("Warning", "Please paste response text first")
            return
        
        try:
            # Process the response
            result = self.processor.process_response(response_text)
            
            # Save the response to file (using custom directory if specified)
            filepath = self.processor.save_response_to_file(
                response_text, 
                result.get('title'),
                self.save_dir
            )
            
            # Show result
            if result['success']:
                status_color = "green"
                
                if result['rejected']:
                    status_text = f"Paper rejected: {result['reason']}"
                    status_color = "orange"
                    messagebox.showinfo("Paper Rejected", 
                                       f"Paper '{result['title']}' was rejected.\n\n"
                                       f"Reason: {result['reason']}\n\n"
                                       f"QA data was still added to the Excel file.")
                else:
                    if result['qa_added'] and result['de_added']:
                        status_text = f"Successfully added '{result['title']}' to QA and DE sheets"
                    elif result['qa_added']:
                        status_text = f"Added '{result['title']}' to QA sheet only"
                        status_color = "blue"
                    else:
                        status_text = f"No data added for '{result['title']}'"
                        status_color = "red"
                    
                    messagebox.showinfo("Success", 
                                       f"Processed paper: {result['title']}\n"
                                       f"Score: {result['score']}\n"
                                       f"Added to QA sheet: {'Yes' if result['qa_added'] else 'No'}\n"
                                       f"Added to DE sheet: {'Yes' if result['de_added'] else 'No'}\n\n"
                                       f"Response saved to: {os.path.basename(filepath) if filepath else 'N/A'}")
            else:
                status_text = f"Processing failed: {result.get('reason', 'Unknown error')}"
                status_color = "red"
                messagebox.showerror("Error", 
                                    f"Failed to process response.\n\n"
                                    f"Error: {result.get('reason', 'Unknown error')}")
            
            self.status_var.set(status_text)
            self.status_label.config(fg=status_color)
            
        except Exception as e:
            logger.error(f"Error processing response: {e}")
            self.status_var.set(f"Error: {str(e)}")
            self.status_label.config(fg="red")
            messagebox.showerror("Error", f"Failed to process response: {e}")
    
    def run(self):
        """Start the GUI main loop"""
        self.root.mainloop()


def main():
    """Main function to run the application"""
    parser = argparse.ArgumentParser(description="Process LLM responses and update Excel sheets")
    
    parser.add_argument("--excel-dir", help="Directory containing the Excel file")
    parser.add_argument("--config", help="Path to review configuration file")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode instead of GUI")
    parser.add_argument("--response-file", help="Path to response file (CLI mode only)")
    parser.add_argument("--save-dir", help="Custom directory to save response files")
    
    args = parser.parse_args()
    
    if args.cli:
        # CLI mode
        if not args.excel_dir or not args.config:
            print("Error: --excel-dir and --config are required in CLI mode")
            return 1
            
        processor = ResponseProcessor(args.excel_dir, args.config)
        
        if args.response_file:
            # Process from file
            try:
                with open(args.response_file, 'r', encoding='utf-8') as f:
                    response_text = f.read()
                result = processor.process_response(response_text)
                
                # Save a copy of the response
                if args.save_dir:
                    saved_path = processor.save_response_to_file(
                        response_text,
                        result.get('title'),
                        args.save_dir
                    )
                    if saved_path:
                        print(f"Saved response to: {saved_path}")
                
                print(f"Processing result:")
                print(f"Title: {result.get('title', 'Unknown')}")
                print(f"Score: {result.get('score', 0)}")
                print(f"QA data added: {'Yes' if result.get('qa_added') else 'No'}")
                print(f"DE data added: {'Yes' if result.get('de_added') else 'No'}")
                
                if result.get('rejected'):
                    print(f"Paper rejected: {result.get('reason')}")
                
                return 0 if result.get('success') else 1
            except Exception as e:
                print(f"Error processing response file: {e}")
                return 1
        else:
            # Read from stdin
            print("Paste response text (press Ctrl+D when finished):")
            response_text = sys.stdin.read()
            result = processor.process_response(response_text)
            
            # Save a copy of the response
            if args.save_dir:
                saved_path = processor.save_response_to_file(
                    response_text,
                    result.get('title'),
                    args.save_dir
                )
                if saved_path:
                    print(f"Saved response to: {saved_path}")
            
            print(f"\nProcessing result:")
            print(f"Title: {result.get('title', 'Unknown')}")
            print(f"Score: {result.get('score', 0)}")
            print(f"QA data added: {'Yes' if result.get('qa_added') else 'No'}")
            print(f"DE data added: {'Yes' if result.get('de_added') else 'No'}")
            
            if result.get('rejected'):
                print(f"Paper rejected: {result.get('reason')}")
            
            return 0 if result.get('success') else 1
    else:
        # GUI mode
        app = ResponseProcessorGUI(args.excel_dir, args.config, args.save_dir)
        app.run()
        return 0

if __name__ == "__main__":
    sys.exit(main())