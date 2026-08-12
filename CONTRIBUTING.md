# Contributing to ReviewbyGPT

Thanks for considering a contribution! This is a small project, so the process is simple.

## Reporting issues

Please use the GitHub issue tracker. Include:
- What you ran (CLI flags or the Python snippet you used)
- What you expected vs. what happened
- Relevant log output (from the console, `llm_responses.log`, or
  `debug_logs/`) -- redact anything sensitive first

## Development setup

```bash
git clone https://github.com/pascd/ReviewbyGPT.git
cd ReviewbyGPT
pip install -e .[test]
```

## Running the tests

```bash
pytest tests/ -v
```

The automated test suite never calls a real LLM endpoint -- `LLMClient`'s
HTTP calls are mocked in `tests/test_llm_client.py`. If you change the
prompt/response format, also run a manual end-to-end check against a real
backend (e.g. a local Ollama server) with a couple of real PDFs; that kind
of live check isn't covered by CI.

## Code style

- Docstrings follow the Google style (`Args:`, `Returns:`, `Raises:`).
- Every module fetches its own logger with `logging.getLogger(__name__)`.
  `logging.basicConfig(...)` is only ever called once, in
  `reviewbygpt/scripts/main.py` -- library modules should never call it,
  since doing so would reconfigure logging for whatever program imports them.
- Prefer adding a fallback/edge case as a documented branch with a comment
  explaining *why* it exists, matching the layered-fallback style already
  used in `reviewbygpt/lib/review_data_parser.py`.

## Extending the review schema

`config/review_data.yaml` defines the quality-assessment questions,
data-extraction fields, cutoff score, and excluding questions for one
specific review (see `README.md`'s Configuration section for the full
schema). To use ReviewbyGPT for a different review, copy that file, edit
the questions/fields to match your review, and pass the new path via
`--review-config`.

## Pointing at a different LLM backend

Any OpenAI-chat-completions-compatible backend works -- see
`reviewbygpt/lib/llm_client.py`'s module docstring for known-compatible
options and `.env.example` for the environment variables that configure it.

## Submitting changes

1. Fork the repository and create a feature branch.
2. Make your change, add/update tests, and run `pytest tests/ -v`.
3. Open a pull request describing what changed and why.
