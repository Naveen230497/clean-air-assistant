"""Shared offline test helpers, socket-level network guard, and base Flask client."""
import base64
import unittest
from typing import Any
from unittest.mock import patch

import requests

from app import ai, create_app, gemini, rate_limit


def _block_network(*_args: Any, **_kwargs: Any) -> None:
    """Abort any accidental live network connection inside tests."""
    raise RuntimeError("Real network calls are forbidden in tests")


class NoNetworkTestCase(unittest.TestCase):
    """Base TestCase that resets shared state and blocks outbound sockets."""

    def setUp(self) -> None:
        """Reset Gemini/briefing caches and block socket connections."""
        super().setUp()
        gemini._breaker_until = 0.0
        ai._briefing_cache.clear()
        p1 = patch("socket.socket.connect", side_effect=_block_network)
        p2 = patch("socket.create_connection", side_effect=_block_network)
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)


class ApiTestCase(NoNetworkTestCase):
    """Base TestCase providing an isolated Flask test client with cleared rate limits."""

    def setUp(self) -> None:
        """Create a Flask test client and reset rate-limit hits before and after each test."""
        super().setUp()
        self.client = create_app().test_client()
        rate_limit._hits.clear()
        self.addCleanup(rate_limit._hits.clear)


class FakeResp:
    """Minimal requests.Response stand-in for offline unit tests."""

    def __init__(self, data: Any, status_code: int = 200) -> None:
        """Store synthetic JSON payload and HTTP status code."""
        self.data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """Raise requests.HTTPError when status_code indicates failure."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self) -> Any:
        """Return synthetic decoded JSON payload."""
        return self.data


def make_gemini_resp(text: str | None = None, parts: list[dict[str, Any]] | None = None,
                     extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a synthetic Gemini API candidate response dictionary."""
    cand: dict[str, Any] = {"content": {"parts": parts or [{"text": text}]}}
    cand.update(extra or {})
    return {"candidates": [cand]}


PNG = base64.b64encode(b"\x89PNG" + b"0" * 20).decode()
