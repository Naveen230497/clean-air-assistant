"""Localization helpers with deterministic English fallback."""
from typing import Any

from .locales import LANG_PACKS


def t(key: str, lang: str = "en", **params: Any) -> str:
    """Return a localized formatted string, falling back cleanly to English."""
    pack = LANG_PACKS.get(lang, LANG_PACKS["en"])
    tmpl = pack.get(key) or LANG_PACKS["en"].get(key)
    if not tmpl:
        return ""
    if not params:
        return tmpl
    try:
        return tmpl.format(**params)
    except (KeyError, ValueError, TypeError):
        return tmpl


def band_label(level: int, lang: str = "en") -> str:
    """Return the localized EPA US AQI severity band label for a numeric level."""
    return t(f"band.{level}", lang)
