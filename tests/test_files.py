import os
from pathlib import Path
import shutil
import time

def create_folders():
        
    for folder in folder_pths:
    
        try:
            # Check if folder exists, and if not, create
            Path(folder).mkdir(parents=True, exist_ok=True)
            print(f"Created folder: {folder}.")
        
        except Exception as e:
            print(f"Unable to create folder: {folder}.")
            
def delete_folders():
        
    for folder in folder_pths:
    
        try:
            # Check if folder exists, and if true, remove it
            if os.path.exists(folder) and os.path.isdir(folder):
                shutil.rmtree(folder)
                
            print(f"Deleted folder: {folder}.")
        
        except Exception as e:
            print(f"Unable to create folder: {folder}.")

if __name__ == "__main__":
    
    pdf_folder_path = "/home/pedrodias/Documents/git-repos/ReviewbyGPT/tests/test_dir"
    
    analysed_folder_path = os.path.join(pdf_folder_path, "analysed")
    excel_file_path = os.path.join(pdf_folder_path, "sheet")
    rejected_file_path = os.path.join(pdf_folder_path, "rejected")
    folder_pths = [analysed_folder_path, excel_file_path, rejected_file_path]
    
    create_folders()
    time.sleep(5)
    delete_folders()