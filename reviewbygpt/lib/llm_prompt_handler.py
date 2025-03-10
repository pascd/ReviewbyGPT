import requests
import logging
from typing import Dict, Any, Optional
import json
import os
import base64
import PyPDF2

class LLMPromptHandler:

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text content from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            str: Extracted text from the PDF
        """
        text = ""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n\n"
            return text
        except Exception as e:
            self.logger.error(f"Error extracting text from PDF: {str(e)}")
            return f"[Error extracting PDF content: {str(e)}]"
    
    def send_to_llm(self, content: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a prompt to the LLM API and get the response.

        Args:
            content: Content for the LLM (the prompt)
            file_path: Optional path of file (PDF or text) to be added to prompt

        Returns:
            Dict[str, Any]: Parsed response from LLM
        """
        try:
            # Prepare the prompt payload
            messages = [
                {"role": "system", "content": "Be precise in your answers and follow the given instructions."},
                {"role": "user", "content": content}
            ]
            
            # If file is provided, extract and add its contents to the user message
            if file_path and os.path.exists(file_path):
                self.logger.info(f"Processing file at path: {file_path}")
                
                if file_path.lower().endswith('.pdf'):
                    # Extract text from PDF
                    pdf_text = self.extract_text_from_pdf(file_path)
                    messages[1]["content"] += f"\n\nPDF Content:\n{pdf_text}"
                else:
                    # For non-PDF files, read as text if possible
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        messages[1]["content"] += f"\n\nFile Content:\n{file_content}"
                    except UnicodeDecodeError:
                        # If the file is not text-readable, encode it as base64
                        with open(file_path, 'rb') as f:
                            file_content = base64.b64encode(f.read()).decode('utf-8')
                        messages[1]["content"] += f"\n\nFile is binary. Base64 encoded content: {file_content[:100]}..."
                
            # Prepare the request payload according to the API format
            payload = {
                "model": "deepseek-r1-distill-qwen-7b",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": -1,
                "stream": False
            }

            # Make the API request
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                url="http://127.0.0.1:8000/v1/chat/completions",
                headers=headers,
                data=json.dumps(payload)  # Convert payload to JSON string
            )
            
            # Raise an exception if the response was not successful
            response.raise_for_status()

            # Parse the response from the API
            result = response.json()

            self.logger.info("Received response from LLM")

            # Check if the response contains the expected 'choices' and extract the assistant's message
            if "choices" in result and result["choices"]:
                assistant_message = result["choices"][0]["message"]["content"]
                self.logger.info(f"Assistant's response: {assistant_message}")

                return {"response": assistant_message}

            return {"error": "No valid response from assistant."}

        except requests.exceptions.RequestException as e:
            # Enhanced logging for API errors
            if e.response:
                self.logger.error(f"API request failed: {e.response.status_code} {e.response.text}")
            else:
                self.logger.error(f"API request failed: {str(e)}")
            return {"error": f"Failed to communicate with LLM: {str(e)}"}
        except Exception as e:
            self.logger.error(f"Error processing LLM response: {str(e)}")
            return {"error": f"Error processing response: {str(e)}"}