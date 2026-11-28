"""Shared constants and thread-safe helper utilities used across backend modules."""
import os
import threading
from typing import Any

REPO_URL = "https://github.com/Naveen230497/clean-air-assistant"
LANGS = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil",
    "bn": "Bengali",
    "mr": "Marathi",
}


def osm_user_agent() -> str:
    """Return the OpenStreetMap User-Agent identifying the app and optional contact."""
    contact = (os.environ.get("CONTACT_EMAIL") or REPO_URL).strip()
    return f"CleanAirAssistant/1.0 ({contact})"


def round_coords(lat: float, lon: float, digits: int = 2) -> tuple[float, float]:
    """Round latitude and longitude coordinates to the requested decimal places."""
    return round(float(lat), digits), round(float(lon), digits)


def cache_get(
    cache: dict[Any, tuple[float, Any]],
    key: Any,
    ttl: float,
    lock: threading.Lock,
    now: float,
) -> Any:
    """Return an unexpired cached entry under lock, or None if absent/stale."""
    with lock:
        hit = cache.get(key)
        if hit and (now - hit[0] < ttl):
            return hit[1]
        return None


def cache_store_bounded(
    cache: dict[Any, Any],
    key: Any,
    value: Any,
    max_entries: int,
    lock: threading.Lock,
) -> None:
    """Store key/value in cache under lock, evicting oldest entries when full."""
    with lock:
        if key in cache:
            del cache[key]
        while len(cache) >= max_entries and cache:
            cache.pop(next(iter(cache)))
        if max_entries > 0:
            cache[key] = value
