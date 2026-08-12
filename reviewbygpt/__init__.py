"""ReviewbyGPT: automate PDF literature-review triage using any LLM API.

See :class:`~reviewbygpt.scripts.pdf_to_excel.PDFToExcelProcessor` for the
main entry point, or run ``python -m reviewbygpt.scripts.main --help`` for
the command-line interface.
"""

from .scripts.pdf_to_excel import PDFToExcelProcessor

__all__ = ["PDFToExcelProcessor"]
