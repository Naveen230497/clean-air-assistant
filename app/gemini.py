"""Thin AI REST client shared by every feature (one place for keys, safety, timeouts)."""
import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
HARM = ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")

BREAKER_SECONDS = 60.0
_breaker_lock = threading.Lock()
_breaker_until: float = 0.0


class GeminiError(Exception):
    """AI provider is unavailable, blocked or returned something unusable."""

    def __init__(self, message: str = "AI request failed", status_code: int | None = None,
                 error_status: str | None = None) -> None:
        """Initialize GeminiError with optional upstream HTTP code and API status."""
        super().__init__(message)
        self.status_code = status_code
        self.error_status = error_status


def get_key() -> str:
    """Return the configured Gemini API key, or an empty string if unset."""
    return (os.environ.get("GEMINI_API_KEY", "") or os.environ.get("API_KEY", "")).strip()


def enabled() -> bool:
    """Return True when a Gemini API key is configured."""
    return bool(get_key())


def breaker_open() -> bool:
    """Return True when Gemini calls are temporarily paused after a 429 rate limit."""
    with _breaker_lock:
        return time.time() < _breaker_until


def _trip_breaker() -> None:
    """Pause subsequent Gemini calls for BREAKER_SECONDS after rate exhaustion."""
    global _breaker_until
    with _breaker_lock:
        _breaker_until = time.time() + BREAKER_SECONDS


def _thinking_config(model: str) -> dict[str, int] | None:
    """Only send thinkingBudget on 2.5 models; omit on newer models to avoid INVALID_ARGUMENT."""
    if (model or "").startswith("gemini-2.5"):
        return {"thinkingBudget": 0}
    return None


def _uses_search(tools: list[dict[str, Any]] | None) -> bool:
    """Return True when tool declarations include Google Search grounding."""
    if not tools:
        return False
    return any(isinstance(t, dict) and ("google_search" in t or "googleSearch" in t) for t in tools)


def _build_request_body(
    contents: list[dict[str, Any]],
    target_model: str,
    *,
    system: str | None = None,
    schema: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_config: dict[str, Any] | None = None,
    max_tokens: int = 600,
    temperature: float = 0.4,
) -> dict[str, Any]:
    """Assemble the Gemini generateContent JSON request body."""
    cfg: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": temperature}
    if (tc := _thinking_config(target_model)) is not None:
        cfg["thinkingConfig"] = tc
    if schema:
        cfg.update(responseMimeType="application/json", responseSchema=schema)
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": cfg,
        "safetySettings": [{"category": c, "threshold": "BLOCK_MEDIUM_AND_ABOVE"} for c in HARM],
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = tools
    if tool_config:
        body["toolConfig"] = tool_config
    return body


def _extract_error_status(response: requests.Response | None, status_code: int | None) -> str | None:
    """Extract optional API error status from a failed HTTP response without raising."""
    if response is None:
        return None
    try:
        data = response.json()
        return data.get("error", {}).get("status") if isinstance(data, dict) else None
    except (ValueError, TypeError, AttributeError):
        # Non-JSON error bodies still surface the HTTP status via GeminiError.
        logger.warning("Could not parse Gemini error response for status=%s", status_code)
        return None


def _call_once(
    target_model: str,
    key: str,
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Execute one REST generateContent call against target_model."""
    try:
        r = requests.post(
            URL.format(model=target_model),
            json=body,
            timeout=timeout,
            headers={"x-goog-api-key": key},
        )
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        error_status = _extract_error_status(exc.response, status_code)
        reason = f"{status_code} {error_status}".strip() if (status_code or error_status) else "AI request failed"
        raise GeminiError(
            f"AI request failed ({reason})", status_code=status_code, error_status=error_status
        ) from exc
    except (requests.RequestException, ValueError) as exc:
        raise GeminiError("AI request failed") from exc


def _configured_models() -> tuple[str, str]:
    """Return primary and optional fallback Gemini model IDs from environment."""
    model = (os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    fallback = (os.environ.get("GEMINI_FALLBACK_MODEL") or "").strip()
    return model, fallback


def _can_fallback(exc: GeminiError, model: str, fallback: str, tools: list[dict[str, Any]] | None) -> bool:
    """Return True when transient failure qualifies for a non-grounded fallback model call."""
    # Search grounding is restricted on some fallback models; only retry non-grounded calls.
    return exc.status_code in (429, 503) and bool(fallback) and fallback != model and not _uses_search(tools)


def generate(contents: list[dict[str, Any]], *, system: str | None = None,
             schema: dict[str, Any] | None = None, tools: list[dict[str, Any]] | None = None,
             tool_config: dict[str, Any] | None = None, max_tokens: int = 600,
             temperature: float = 0.4, timeout: float = 12) -> dict[str, Any]:
    """Call Gemini generateContent with safety settings, fallback model, and 429 breaker."""
    key = get_key()
    if not key:
        raise GeminiError("API key not configured")
    if breaker_open():
        raise GeminiError("AI service temporarily paused after rate limit",
                          status_code=429, error_status="RESOURCE_EXHAUSTED")

    model, fallback = _configured_models()
    req_kwargs: dict[str, Any] = {
        "system": system, "schema": schema, "tools": tools, "tool_config": tool_config,
        "max_tokens": max_tokens, "temperature": temperature,
    }
    try:
        return _call_once(model, key, _build_request_body(contents, model, **req_kwargs), timeout)
    except GeminiError as exc:
        if _can_fallback(exc, model, fallback, tools):
            try:
                return _call_once(fallback, key, _build_request_body(contents, fallback, **req_kwargs), timeout)
            except GeminiError as fb_exc:
                if fb_exc.status_code == 429:
                    _trip_breaker()
                raise
        if exc.status_code == 429:
            _trip_breaker()
        raise


def parts_of(resp: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract candidate content parts from a Gemini response or raise GeminiError."""
    try:
        return resp["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError("Empty or blocked response") from exc


def text_of(resp: dict[str, Any]) -> str:
    """Concatenate and validate non-empty text parts from a Gemini response."""
    text = "".join(p.get("text", "") for p in parts_of(resp)).strip()
    if not text:
        raise GeminiError("No text in response")
    return text
