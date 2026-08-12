"""Tests for LLMClient: no live network access, `requests.post` is mocked.

Covers the OpenAI-compatible request/response shape, the auth-header
behavior, the retry-vs-fail-fast split between 5xx and 4xx responses, and
the constructor's config precedence (explicit arg > env var > config file).
"""

import json as jsonlib
from unittest.mock import MagicMock, patch

import pytest

from reviewbygpt.lib.llm_client import LLMClient


def _fake_response(status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


@patch("reviewbygpt.lib.llm_client.requests.post")
def test_send_prompt_returns_assistant_text(mock_post):
    mock_post.return_value = _fake_response(200, {"choices": [{"message": {"content": "the answer"}}]})

    client = LLMClient(api_url="http://example.test/v1/chat/completions", model="test-model")
    result = client.send_prompt("What is 2+2?")

    assert result == "the answer"
    mock_post.assert_called_once()


@patch("reviewbygpt.lib.llm_client.requests.post")
def test_send_prompt_payload_shape(mock_post):
    mock_post.return_value = _fake_response(200, {"choices": [{"message": {"content": "ok"}}]})

    client = LLMClient(api_url="http://example.test/v1/chat/completions", model="test-model")
    client.send_prompt("hello", pdf_content="pdf text here")

    _, kwargs = mock_post.call_args
    payload = jsonlib.loads(kwargs["data"])
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert "pdf text here" in payload["messages"][1]["content"]
    assert "hello" in payload["messages"][1]["content"]


@patch("reviewbygpt.lib.llm_client.requests.post")
def test_authorization_header_only_when_api_key_set(mock_post):
    mock_post.return_value = _fake_response(200, {"choices": [{"message": {"content": "ok"}}]})

    client = LLMClient(api_url="http://example.test/v1/chat/completions", model="test-model")
    client.send_prompt("hello")
    _, kwargs = mock_post.call_args
    assert "Authorization" not in kwargs["headers"]

    client_with_key = LLMClient(
        api_url="http://example.test/v1/chat/completions", model="test-model", api_key="secret"
    )
    client_with_key.send_prompt("hello")
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer secret"


@patch("reviewbygpt.lib.llm_client.requests.post")
def test_send_prompt_returns_none_on_client_error(mock_post):
    mock_post.return_value = _fake_response(400, text="bad request")

    client = LLMClient(api_url="http://example.test/v1/chat/completions", model="test-model")
    assert client.send_prompt("hello") is None
    # 4xx is a client-side problem -- retrying can't fix it, so only one attempt is made.
    assert mock_post.call_count == 1


@patch("reviewbygpt.lib.llm_client.requests.post")
def test_send_prompt_retries_on_server_error(mock_post):
    mock_post.return_value = _fake_response(503, text="overloaded")

    client = LLMClient(
        api_url="http://example.test/v1/chat/completions",
        model="test-model",
        max_retries=2,
        retry_backoff=0,  # avoid real sleeping in the test
    )
    assert client.send_prompt("hello") is None
    assert mock_post.call_count == 2


def test_missing_api_url_raises(monkeypatch):
    monkeypatch.delenv("LLM_API_URL", raising=False)
    with pytest.raises(ValueError):
        LLMClient(model="test-model")


def test_missing_model_raises(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(ValueError):
        LLMClient(api_url="http://example.test/v1/chat/completions")


def test_config_precedence_env_var_over_file(tmp_path, monkeypatch):
    config_file = tmp_path / "llm_api_config.json"
    config_file.write_text(
        jsonlib.dumps({"api_url": "http://from-file/v1/chat/completions", "model": "from-file-model"})
    )

    monkeypatch.setenv("LLM_API_URL", "http://from-env/v1/chat/completions")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    client = LLMClient(config_path=str(config_file))
    assert client.api_url == "http://from-env/v1/chat/completions"
    # No LLM_MODEL env var set, so this falls back to the config file's value.
    assert client.model == "from-file-model"


def test_config_precedence_explicit_arg_over_env_var(monkeypatch):
    monkeypatch.setenv("LLM_API_URL", "http://from-env/v1/chat/completions")
    client = LLMClient(api_url="http://explicit/v1/chat/completions", model="m")
    assert client.api_url == "http://explicit/v1/chat/completions"
