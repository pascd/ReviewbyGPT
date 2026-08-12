"""Generic HTTP client for OpenAI-chat-completions-compatible LLM backends.

"OpenAI-compatible" means the backend exposes a `/v1/chat/completions`-style
HTTP endpoint that accepts a JSON body of the form
``{"model": ..., "messages": [...], ...}`` and replies with
``{"choices": [{"message": {"content": "..."}}]}``. This is a de-facto
standard implemented by a wide range of providers and self-hosted servers,
including (non-exhaustive):

- OpenAI's own API (https://api.openai.com/v1/chat/completions)
- Ollama (https://github.com/ollama/ollama), which exposes this shape at
  ``http://localhost:11434/v1/chat/completions`` in addition to its native API
- LM Studio, vLLM, text-generation-webui, and most other local inference
  servers that advertise "OpenAI compatibility"

Using this single client, ReviewbyGPT can talk to any of the above (or any
future compatible backend) by simply pointing ``api_url`` at the right place
-- no code changes, no backend-specific classes.
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import PyPDF2
import requests

# Each module only grabs a logger; the application entry point
# (reviewbygpt/scripts/main.py) is responsible for calling
# logging.basicConfig() so importing this module never has the side effect
# of configuring the root logger for whatever program imports it.
logger = logging.getLogger(__name__)

# Environment variables that can supply configuration without editing any
# file on disk -- handy for CI, containers, and not committing API keys.
_ENV_API_URL = "LLM_API_URL"
_ENV_API_KEY = "LLM_API_KEY"
_ENV_MODEL = "LLM_MODEL"

# HTTP status codes worth retrying: connection hiccups and server-side
# overload/maintenance. 4xx errors (bad request, bad auth, unknown model)
# are never retried because a retry can't fix a client-side mistake.
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class LLMClient:
    """Talks to any OpenAI-chat-completions-compatible LLM API.

    Configuration can come from four places, in order of precedence
    (first one that provides a value wins):

        1. An explicit constructor argument (``api_url=...``, etc.)
        2. An environment variable (``LLM_API_URL``, ``LLM_API_KEY``,
           ``LLM_MODEL``)
        3. A JSON config file at ``config_path`` (see
           ``config/llm_api_config.json`` for the expected shape)
        4. A built-in default (only ``temperature``/``max_tokens``/etc. have
           safe defaults -- ``api_url`` and ``model`` do not, since there is
           no backend-agnostic "correct" value for either)

    Attributes:
        api_url: Full URL of the chat-completions endpoint to POST to.
        api_key: Bearer token sent as ``Authorization: Bearer <api_key>``.
            Left empty for backends that don't require authentication
            (e.g. a local Ollama/LM Studio server).
        model: Name of the model to request from the backend.
        temperature: Sampling temperature forwarded to the backend.
        max_tokens: Maximum tokens forwarded to the backend.
        timeout: Per-HTTP-request timeout, in seconds. Defaults to 600s
            (10 minutes) because analysing a full PDF can take a long time
            on slower local hardware.
        max_retries: How many times to retry a request after a transient
            failure (connection error, timeout, or 5xx response).
        retry_backoff: Base (seconds) for the exponential backoff between
            retries -- the Nth retry sleeps ``retry_backoff ** N`` seconds.
        max_content_length: If set, PDF text longer than this many characters
            is truncated before being sent to the LLM (useful for backends
            with a small context window). ``None`` disables truncation.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: int = 600,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        max_content_length: Optional[int] = None,
    ) -> None:
        """Resolve configuration and store it on the instance.

        Args:
            config_path: Optional path to a JSON file providing defaults for
                api_url/api_key/model/temperature/max_tokens/timeout/
                max_content_length (see ``config/llm_api_config.json``).
            api_url: OpenAI-compatible chat-completions endpoint. Takes
                precedence over ``$LLM_API_URL`` and the config file.
            api_key: Bearer token, if the backend needs one. Takes
                precedence over ``$LLM_API_KEY`` and the config file. Prefer
                the environment variable over passing this directly so keys
                don't end up in shell history or source control.
            model: Model name to request. Takes precedence over
                ``$LLM_MODEL`` and the config file.
            temperature: Sampling temperature (0 = deterministic, higher =
                more random). Defaults to a low value since this tool wants
                consistent, parseable review output rather than creativity.
            max_tokens: Maximum tokens the backend should generate.
            timeout: HTTP request timeout in seconds.
            max_retries: Number of retry attempts for transient failures.
            retry_backoff: Exponential backoff base, in seconds.
            max_content_length: Optional cap on extracted PDF text length.

        Raises:
            ValueError: If ``api_url`` or ``model`` cannot be resolved from
                any of the four configuration sources -- there is no safe
                default for either.
        """
        file_config = self._load_config_file(config_path)

        self.api_url = self._resolve(api_url, _ENV_API_URL, "api_url", file_config)
        self.model = self._resolve(model, _ENV_MODEL, "model", file_config)

        if not self.api_url:
            raise ValueError(
                "No LLM API URL configured. Pass api_url=..., set the "
                f"{_ENV_API_URL} environment variable, or add \"api_url\" to "
                "the JSON file passed as config_path."
            )
        if not self.model:
            raise ValueError(
                "No LLM model name configured. Pass model=..., set the "
                f"{_ENV_MODEL} environment variable, or add \"model\" to the "
                "JSON file passed as config_path."
            )

        # api_key legitimately resolves to "" for backends that don't
        # require authentication (e.g. a local Ollama server), so it is not
        # validated the way api_url/model are.
        self.api_key = self._resolve(api_key, _ENV_API_KEY, "api_key", file_config) or ""

        # Generation/transport parameters: explicit constructor args win,
        # otherwise fall back to whatever the config file specifies, otherwise
        # the function default already captured in the signature above.
        self.temperature = file_config.get("temperature", temperature) if file_config else temperature
        self.max_tokens = file_config.get("max_tokens", max_tokens) if file_config else max_tokens
        self.timeout = file_config.get("timeout", timeout) if file_config else timeout
        self.max_content_length = (
            file_config.get("max_content_length", max_content_length) if file_config else max_content_length
        )
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        logger.info(
            "Initialized LLMClient (api_url=%s, model=%s, timeout=%ss)",
            self.api_url,
            self.model,
            self.timeout,
        )

    @staticmethod
    def _load_config_file(config_path: Optional[str]) -> Optional[Dict[str, Any]]:
        """Load and parse the optional JSON config file.

        Returns:
            The parsed JSON object, or None if no path was given or the file
            could not be read/parsed (a warning is logged in that case, but
            this never raises -- a missing/broken config file should not
            prevent env vars or explicit arguments from being used instead).
        """
        if not config_path:
            return None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load LLM config file '{config_path}': {e}")
            return None

    @staticmethod
    def _resolve(
        explicit: Optional[str],
        env_var: str,
        config_key: str,
        file_config: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Apply the constructor-arg > env-var > config-file precedence rule.

        Args:
            explicit: The value passed directly to the constructor, if any.
            env_var: Name of the environment variable to check next.
            config_key: Key to look up in the parsed config file next.
            file_config: The parsed config file (or None if unavailable).

        Returns:
            The first non-empty value found, or None if none of the three
            sources provided one.
        """
        if explicit:
            return explicit
        if os.environ.get(env_var):
            return os.environ[env_var]
        if file_config and file_config.get(config_key):
            return file_config[config_key]
        return None

    def extract_text_from_pdf(self, pdf_path: str) -> Optional[str]:
        """Extract all text content from a PDF file, page by page.

        Args:
            pdf_path: Path to the PDF file on disk.

        Returns:
            The concatenated text of every page, or None if the file could
            not be read/parsed (the error is logged, not raised).
        """
        try:
            text = ""
            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                logger.info(f"Extracting text from PDF: {pdf_path} ({num_pages} pages)")

                for page_num in range(num_pages):
                    text += pdf_reader.pages[page_num].extract_text()
                    # Large PDFs can take a while to extract; a periodic
                    # progress log reassures anyone watching a long-running
                    # batch that it hasn't stalled.
                    if num_pages > 10 and page_num % 5 == 0:
                        logger.info(f"Extracted {page_num + 1}/{num_pages} pages...")

            logger.info(f"Successfully extracted {len(text)} characters from PDF")
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF '{pdf_path}': {e}")
            return None

    def send_prompt(self, prompt: str, pdf_content: Optional[str] = None) -> Optional[str]:
        """Send a prompt (optionally with PDF text prepended) to the LLM.

        Args:
            prompt: The instruction/question to send to the model.
            pdf_content: Optional extracted PDF text to include as context.
                Combined with ``prompt`` into a single user message, since
                this client targets stateless chat-completions APIs that
                don't support uploading a separate "file" attachment.

        Returns:
            The assistant's reply text, or None if the request ultimately
            failed after all retries (the error is logged, not raised).
        """
        full_prompt = self._build_full_prompt(prompt, pdf_content)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Be precise in your answers and follow the given instructions.",
                },
                {"role": "user", "content": full_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,  # This client parses one complete response, not a stream.
        }

        response_json = self._post_with_retries(payload)
        if response_json is None:
            return None

        choices = response_json.get("choices")
        if not choices:
            logger.error("LLM response contained no 'choices': %s", response_json)
            return None

        return choices[0].get("message", {}).get("content", "")

    def _build_full_prompt(self, prompt: str, pdf_content: Optional[str]) -> str:
        """Combine (and optionally truncate) PDF text with the instruction prompt.

        Args:
            prompt: The instruction/question text.
            pdf_content: Extracted PDF text, or None if there is none to add.

        Returns:
            The combined prompt string ready to send as the user message.
        """
        if not pdf_content:
            return prompt

        if self.max_content_length and len(pdf_content) > self.max_content_length:
            logger.warning(
                "PDF content length (%d chars) exceeds limit (%d), truncating",
                len(pdf_content),
                self.max_content_length,
            )
            pdf_content = pdf_content[: self.max_content_length] + "... [Content truncated due to length]"

        return f"PDF CONTENT:\n{pdf_content}\n\nTASK:\n{prompt}"

    def _post_with_retries(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """POST the payload to ``self.api_url``, retrying on transient failures.

        Retries connection errors, timeouts, and 5xx responses (the backend
        may just be briefly overloaded or restarting). Does NOT retry 4xx
        responses -- those indicate a client-side problem (bad model name,
        bad auth, malformed request) that a retry cannot fix.

        Args:
            payload: The JSON-serializable request body.

        Returns:
            The parsed JSON response body, or None if every attempt failed.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    url=self.api_url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    return response.json()

                last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    logger.error(f"LLM API request failed (not retrying): {last_error}")
                    return None
                logger.warning(f"LLM API request failed (attempt {attempt}/{self.max_retries}): {last_error}")

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = str(e)
                logger.warning(f"LLM API request failed (attempt {attempt}/{self.max_retries}): {last_error}")
            except Exception as e:
                # Anything else (e.g. a malformed payload) is not transient --
                # retrying won't help, so fail fast.
                logger.error(f"Unexpected error calling LLM API: {e}")
                return None

            if attempt < self.max_retries:
                sleep_seconds = self.retry_backoff**attempt
                time.sleep(sleep_seconds)

        logger.error(f"LLM API request failed after {self.max_retries} attempts: {last_error}")
        return None

    def verify_connection(self) -> bool:
        """Best-effort check that the configured backend is reachable.

        Not all OpenAI-compatible backends expose a lightweight health/list
        endpoint, so this simply issues a minimal chat request. Callers
        should treat a False return as a warning, not a fatal error --
        a backend that fails this check might still work for real requests
        (or might genuinely be down, in which case the real request will
        fail too and be logged then).

        Returns:
            True if a minimal request succeeded, False otherwise.
        """
        result = self.send_prompt("Respond with the single word: OK")
        return result is not None

    def new_conversation(self) -> bool:
        """No-op reset hook, kept for interface symmetry.

        This client is stateless -- each ``send_prompt`` call is an
        independent HTTP request with no server-side session -- so there is
        nothing to actually reset. The method exists so callers (like
        ``PDFToExcelProcessor``, which starts a "new conversation" every
        ``max_questions`` PDFs) don't need special-case logic if a future
        backend does maintain server-side state.

        Returns:
            Always True.
        """
        logger.info("Starting a new logical conversation (no-op for a stateless HTTP backend)")
        return True
