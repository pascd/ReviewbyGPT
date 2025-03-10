# 🚀 ReviewbyGPT

ReviewbyGPT is a powerful tool designed to assist researchers in reviewing PDF papers and filling out Excel sheets with relevant information. This package leverages AI to provide insightful reviews and streamline the data extraction process.

## ✨ Features

- **🚀 Automated Paper Reviews**: Get instant feedback on your PDF papers.
- **📊 Data Extraction**: Automatically extract key information from papers.
- **📈 Excel Integration**: Fill out Excel sheets with extracted data.
- **🔍 Error Detection**: Identify potential issues in your data extraction process.

## 📥 Installation

To install ReviewbyGPT, use the following command:

```bash
pip install reviewbygpt
```

## 🛠️ Usage

Here's a basic example of how to use ReviewbyGPT:

```python
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
```

## 🤝 Contributing

We welcome contributions! Please read our [contributing guidelines](CONTRIBUTING.md) for more details.

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.

## 📧 Contact

For any questions or feedback, please contact me at pedro.afonso.cardoso.dias@gmail.com
