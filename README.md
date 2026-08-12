# ReviewbyGPT

ReviewbyGPT automates the tedious part of a literature review: for every PDF in a folder, it
extracts the text, sends it to an LLM along with a set of quality-assessment questions and
data-extraction fields you define, parses the structured answer back out, and records it in an
Excel workbook — sorting each paper into `analysed/` or `rejected/` based on a score cutoff you
configure. No browser automation, no vendor lock-in: it talks to any LLM that exposes an
OpenAI-compatible chat API.

## Features

- **Automatic PDF review**: extracts text and sends it, with your review questions, to an LLM.
- **Works with any OpenAI-compatible backend**: OpenAI, a local [Ollama](https://ollama.com)
  server, [LM Studio](https://lmstudio.ai), vLLM, text-generation-webui, or anything else that
  speaks the `/v1/chat/completions` protocol — just point `--api-url` at it.
- **Structured Excel output**: quality-assessment scores and extracted data fields are written
  to separate sheets, styled and ready to skim.
- **Configurable accept/reject logic**: a cutoff score plus "excluding questions" (any one of
  which scoring 0 rejects the paper outright) automatically sort PDFs into `analysed/`/`rejected/`.
- **Full audit trail**: every prompt sent and response received is saved under `debug_logs/`,
  plus a single running `llm_responses.log`, so you can see exactly what the LLM was asked and said.

## Installation

```bash
git clone https://github.com/pascd/ReviewbyGPT.git
cd ReviewbyGPT
pip install -e .
```

Requires Python 3.9+. This installs a `reviewbygpt` console command as well as the
`reviewbygpt` Python package.

## Usage

### Command line

```bash
reviewbygpt \
  --pdf-folder ./papers \
  --review-config ./config/review_data.yaml \
  --api-url http://localhost:11434/v1/chat/completions \
  --model gemma2:latest
```

Run `reviewbygpt --help` for the full list of flags (Excel sheet names, `--max-questions`,
`--max-content-length`, `--timeout`, `--log-level`, etc.). LLM backend settings can also be
supplied via a JSON file (`--llm-config`) or environment variables — see Configuration below.

### Programmatic

```python
from reviewbygpt import PDFToExcelProcessor

processor = PDFToExcelProcessor(
    pdf_folder_path="./papers",
    review_config="./config/review_data.yaml",
    qa_sheet_name="qa_sheet",
    de_sheet_name="de_sheet",
    max_questions=10,
    api_url="http://localhost:11434/v1/chat/completions",
    model="gemma2:latest",
)
processor.run()
```

## Configuration

### Review schema (`review_data.yaml`)

Defines what the LLM is asked to evaluate/extract. See `config/review_data.yaml` for a full
example (a robotic-disassembly literature review); the schema is:

```yaml
quality_assessment_questions:
  - id: QE1
    question: "Is the methodology appropriate for the task?"
    scores: [0.0, 0.5, 1.0]   # possible scores the LLM can assign

cutoff_score: 6.5             # total QA score a paper needs to be "accepted"
excluding_questions: [QE1]    # any of these scoring 0 rejects the paper outright

data_extraction_fields:
  - key: TITLE
    description: "Title of the paper."
```

Copy and edit this file for your own review, then pass it via `--review-config`.

### LLM backend (`llm_api_config.json` and environment variables)

Configuration is resolved with this precedence (highest wins): **CLI flag** →
**environment variable** → **JSON config file** → built-in default.

`config/llm_api_config.json`:

```json
{
    "api_url": "http://localhost:11434/v1/chat/completions",
    "api_key": "",
    "model": "gemma2:latest",
    "temperature": 0.1,
    "max_tokens": 1024,
    "timeout": 600,
    "max_content_length": null
}
```

Or via environment variables (see `.env.example`): `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`.
Prefer environment variables (or a local, untracked config file) over CLI flags or committing a
real value into `llm_api_config.json` for anything that requires an API key.

**Using a hosted provider (e.g. OpenAI)** instead of a local server: set `LLM_API_URL` to
`https://api.openai.com/v1/chat/completions`, `LLM_MODEL` to a model you have access to, and
`LLM_API_KEY` to your API key.

## Output layout

Inside `--pdf-folder`, ReviewbyGPT creates:

- `sheet/analysed.xlsx` — the Excel workbook (QA sheet + DE sheet).
- `analysed/` — PDFs that passed the cutoff and excluding-question checks.
- `rejected/` — PDFs that didn't.
- `debug_logs/` — per-PDF prompt/extracted-text/response `.txt` files.
- `llm_responses.log` — a single running log of every response, in order.

## Troubleshooting

Running a local Ollama backend and hitting GPU/CUDA issues? `reviewbygpt/scripts/ollama_diagnose.sh`
and `reviewbygpt/scripts/intall_cuda.sh` are optional helper scripts for diagnosing and setting up
GPU-accelerated Ollama inference. They're unrelated to ReviewbyGPT itself — useful only if you've
chosen to self-host via Ollama.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) and our
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Contact

Questions or feedback: pedro.afonso.cardoso.dias@gmail.com
