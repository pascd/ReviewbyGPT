# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-08-12

### Added
- Initial public open-source release.
- Unified `LLMClient` supporting any OpenAI-chat-completions-compatible
  backend (OpenAI, Ollama, LM Studio, vLLM, text-generation-webui, ...).
- Argparse-based CLI (`reviewbygpt` console script, or
  `python -m reviewbygpt.scripts.main --help`).
- A real `pytest` test suite covering response parsing, Excel writing, and
  the LLM client (with `requests` mocked, so no live backend is needed).
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CITATION.cff`,
  and this changelog.
- A Mermaid architecture diagram and expanded, structured `README.md`
  (project status, tech stack, dependency table, known issues, community
  standards, credits).

### Changed
- Consolidated three separate, inconsistent LLM code paths (a browser
  automation handler, an Ollama-specific client, and an unused generic
  client) into a single, well-documented, generic HTTP client.
- Rewrote `README.md` to accurately describe installation, CLI usage, the
  programmatic API, and configuration.
- Cleaned up `requirements.txt` to list only the packages the code
  actually imports, and consolidated all packaging metadata into
  `pyproject.toml` (removing the now-redundant `setup.py`).
- Fixed two silent scoring bugs in `PDFToExcelProcessor` where a
  mismatched dictionary key meant the total score and excluding-question
  checks never actually matched the data they were checking against.

### Removed
- The browser-automation ChatGPT integration and its undeclared
  `webgpthandler` dependency, which previously made the package
  impossible to import without a private, unpublished sibling package.
- Hardcoded personal file paths and placeholder login credentials.
- Dead code (`ResponseHandler`, an Ollama-specific GPU/CUDA diagnostic
  class, several unused imports).
