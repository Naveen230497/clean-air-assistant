"""Localization helpers and error-message mapping with English fallback."""
from typing import Any

from .locales import LANG_PACKS

_BOOL_SUFFIX = " must be true or false"

_ERROR_KEYS = {
    "Daily limit for nearby places reached.": "err.nearby_daily_cap",
    "Please wait a moment before searching nearby places again.": "err.nearby_wait",
    "No air quality data for this location": "air.no_data",
    "Location not found": "air.not_found",
    "Air quality service unavailable": "air.unavailable",
    "Provide a city or coordinates": "air.need_loc",
    "City name is invalid": "val.city",
    "Unsupported language": "val.lang",
    "AQI must be a number": "val.aqi_num",
    "AQI must be between 0 and 500": "val.aqi_range",
    "Location coordinates are invalid": "val.coords",
    "Place name is invalid": "val.place_invalid",
    "Request body must be a JSON object": "val.obj",
    "Provide a city, your location or an AQI value": "val.need_loc",
    "Unknown commute type": "val.commute",
    "Unknown cooking type": "val.cooking",
    "Unknown AQI source": "val.aqi_src",
    "City is required": "val.city_req",
    "History must be a list of at most 6 turns": "val.hist_list",
    "Invalid history entry": "val.hist_item",
    "Question must be 1-500 characters": "val.q_len",
    "AQI is required": "val.aqi_req",
    "Place is invalid": "val.place",
    "Valid lat and lon are required": "val.latlon_req",
    "Coordinates out of range": "val.latlon_range",
    "Upload a PNG, JPEG or WebP image": "val.img_type",
    "Image data is invalid": "val.img_data",
    "Image must be under 3 MB": "val.img_size",
    "Image content does not match its type": "val.img_sig",
    "Location coordinates are required": "val.coords_req",
}


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


def localize_error(message: str, lang: str = "en") -> str:
    """Translate a known English validation, air-data, or Overpass message into lang."""
    if lang == "en" or lang not in LANG_PACKS:
        return message
    if message in _ERROR_KEYS:
        return t(_ERROR_KEYS[message], lang)
    if message.endswith(_BOOL_SUFFIX):
        return t("val.bool", lang, field=message[:-len(_BOOL_SUFFIX)])
    return message
