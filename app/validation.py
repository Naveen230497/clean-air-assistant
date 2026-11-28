"""Strict request validation: whitelist every field, reject the rest."""
import base64
import binascii
import re
from typing import Any

from .recommender import COMMUTES, COOKING, Profile
from .shared import LANGS

BOOLS = ("has_purifier", "children", "elderly", "respiratory", "outdoor_exercise")
CITY_RE = re.compile(r"^[\w .,'\-]{2,60}$", re.UNICODE)
IMAGE_MAGIC = {"image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def valid_city(name: str | None) -> bool:
    """Return True if a city or place string matches the allowed character whitelist."""
    return bool(CITY_RE.match(name or ""))


class ValidationError(ValueError):
    """Raised when incoming request fields fail schema, range, or file validation."""


def _city(value: Any) -> str | None:
    """Validate optional city name against allowed characters."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not valid_city(value):
        raise ValidationError("City name is invalid")
    return value


def _lang(data: dict[str, Any]) -> str:
    """Validate and return the requested ISO language code."""
    lang = data.get("lang", "en")
    if lang not in LANGS:
        raise ValidationError("Unsupported language")
    return lang


def _aqi(value: Any) -> float | None:
    """Validate optional numeric US AQI between 0 and 500."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValidationError("AQI must be a number")
    try:
        aqi = float(value)
    except (TypeError, ValueError):
        raise ValidationError("AQI must be a number") from None
    if not 0 <= aqi <= 500:
        raise ValidationError("AQI must be between 0 and 500")
    return aqi


def _coords(data: dict[str, Any]) -> tuple[float, float] | None:
    """Validate optional latitude (-90..90) and longitude (-180..180) pair."""
    lat, lon = data.get("lat"), data.get("lon")
    if lat is None and lon is None:
        return None
    for v, lim in ((lat, 90), (lon, 180)):
        if isinstance(v, bool) or not isinstance(v, int | float) or not -lim <= v <= lim:
            raise ValidationError("Location coordinates are invalid")
    return float(lat), float(lon)


def _place(data: dict[str, Any]) -> str | None:
    """Optional label for picked coordinates or location."""
    place = data.get("place")
    if place in (None, ""):
        return None
    if not isinstance(place, str) or not valid_city(place):
        raise ValidationError("Place name is invalid")
    return place


def _obj(data: Any) -> dict[str, Any]:
    """Ensure the decoded JSON body is a dictionary object."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")
    return data


def parse_request(data: Any) -> tuple[str | None, float | None, Profile, str, tuple[float, float] | None, str | None]:
    """Return (city_or_None, manual_aqi_or_None, Profile, lang, coords_or_None, place_label_or_None)."""
    data = _obj(data)
    city, aqi = _city(data.get("city")), _aqi(data.get("aqi"))
    coords = _coords(data)
    if city is None and aqi is None and coords is None:
        raise ValidationError("Provide a city, your location or an AQI value")
    commute, cooking = data.get("commute", "public_transit"), data.get("cooking", "gas")
    if commute not in COMMUTES:
        raise ValidationError("Unknown commute type")
    if cooking not in COOKING:
        raise ValidationError("Unknown cooking type")
    flags = {}
    for k in BOOLS:
        v = data.get(k, False)
        if not isinstance(v, bool):
            raise ValidationError(f"{k} must be true or false")
        flags[k] = v
    return city, aqi, Profile(commute=commute, cooking=cooking, **flags), _lang(data), coords, _place(data)


def parse_aqi_source(data: Any) -> str:
    """Return validated manual-entry source ('manual' or 'image')."""
    src = _obj(data).get("aqi_source", "manual")
    if src not in ("manual", "image"):
        raise ValidationError("Unknown AQI source")
    return src


def parse_advisory(data: Any) -> tuple[str, str]:
    """Validate and return (city, lang) for local advisory lookup."""
    data = _obj(data)
    city = _city(data.get("city"))
    if not city:
        raise ValidationError("City is required")
    return city, _lang(data)


def _validate_history(hist: Any) -> list[dict[str, str]]:
    """Validate and sanitize at most 6 prior chat turns."""
    if not isinstance(hist, list) or len(hist) > 6:
        raise ValidationError("History must be a list of at most 6 turns")
    clean = []
    for h in hist:
        if (not isinstance(h, dict) or h.get("role") not in ("user", "assistant")
                or not isinstance(h.get("text"), str) or len(h["text"]) > 1200):
            raise ValidationError("Invalid history entry")
        clean.append({"role": h["role"], "text": h["text"]})
    return clean


def parse_chat(data: Any) -> tuple[str, list[dict[str, str]], float, str, str]:
    """Return (question, history, aqi, place, lang)."""
    data = _obj(data)
    q = data.get("question")
    if not isinstance(q, str) or not 1 <= len(q.strip()) <= 500:
        raise ValidationError("Question must be 1-500 characters")
    aqi = _aqi(data.get("aqi"))
    if aqi is None:
        raise ValidationError("AQI is required")
    place = data.get("place") or "your area"
    if not isinstance(place, str) or not valid_city(place):
        raise ValidationError("Place is invalid")
    return q.strip(), _validate_history(data.get("history", [])), aqi, place, _lang(data)


def parse_locate(lat_raw: Any, lon_raw: Any) -> tuple[float, float]:
    """Validate string query parameters lat and lon for /api/locate."""
    if not lat_raw or not lon_raw:
        raise ValidationError("Valid lat and lon are required")
    try:
        lat_f, lon_f = float(lat_raw), float(lon_raw)
    except (ValueError, TypeError):
        raise ValidationError("Valid lat and lon are required") from None
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        raise ValidationError("Coordinates out of range")
    return lat_f, lon_f


def parse_image(data: Any) -> tuple[str, str]:
    """Return (base64_string, mime). Verifies mime, size and file signature."""
    data = _obj(data)
    mime, b64 = data.get("mime"), data.get("image")
    if mime not in IMAGE_MAGIC or not isinstance(b64, str):
        raise ValidationError("Upload a PNG, JPEG or WebP image")
    try:
        # validate=True rejects corrupted padding or non-base64 characters cleanly.
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError("Image data is invalid") from None
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValidationError("Image must be under 3 MB")
    # Magic-byte verification prevents mislabelled or spoofed MIME uploads.
    if not raw.startswith(IMAGE_MAGIC[mime]) or (mime == "image/webp" and raw[8:12] != b"WEBP"):
        raise ValidationError("Image content does not match its type")
    return b64, mime


def parse_nearby(data: Any) -> tuple[float, float, str]:
    """Return (lat, lon, lang). Coordinates are required."""
    data = _obj(data)
    coords = _coords(data)
    if coords is None:
        raise ValidationError("Location coordinates are required")
    return coords[0], coords[1], _lang(data)
