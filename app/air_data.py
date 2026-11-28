"""Live air-quality lookup using the free Open-Meteo APIs (no key required)."""
import logging
import math
import re
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import requests

from .shared import cache_get, cache_store_bounded, osm_user_agent, round_coords
from .validation import valid_city

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
REVERSE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"  # free, no key
TIMEOUT = 10
TTL = 600  # seconds; air quality changes slowly, cache to save calls
MAX_ENTRIES = 2000

_cache: dict = {}
_names: dict = {}
_cache_lock = threading.Lock()
_nom_lock = threading.Lock()
_last_nominatim = 0.0


def _store(cache: dict[Any, Any], key: Any, value: Any) -> None:
    """Store a value in a bounded cache dictionary, clearing when full."""
    cache_store_bounded(cache, key, value, MAX_ENTRIES, _cache_lock)


class AirDataError(Exception):
    """Raised when location or air data cannot be fetched."""


@dataclass(frozen=True)
class Reading:
    """Normalized current AQI and particulate observation for one location."""

    place: str
    aqi: float
    pm25: float | None
    pm10: float | None
    observed_at: str | None = None


def _cached(key: str | tuple[Any, ...], cache: dict[Any, Any] | None = None) -> Any:
    """Return an unexpired cached entry from cache (defaults to air reading cache)."""
    target = _cache if cache is None else cache
    return cache_get(target, key, TTL, _cache_lock, time.time())


def _parse_observed_at(raw: Any) -> str | None:
    """Parse an Open-Meteo timestamp (GMT when no timezone set) into UTC ISO 8601."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or ("T" not in s and " " not in s and ":" not in s):
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.isoformat().replace("+00:00", "Z")


def _opt_num(val: Any) -> float | None:
    """Return a non-negative 1-decimal finite float, or None for invalid inputs."""
    if isinstance(val, bool) or not isinstance(val, int | float):
        return None
    f = float(val)
    return round(f, 1) if math.isfinite(f) and f >= 0 else None


def _air(lat: float, lon: float, place: str) -> Reading:
    """Fetch current US AQI, PM2.5, and PM10 from Open-Meteo for coordinates."""
    r = requests.get(AIR_URL, params={"latitude": lat, "longitude": lon,
                                      "current": "us_aqi,pm2_5,pm10"}, timeout=TIMEOUT)
    r.raise_for_status()
    cur = r.json().get("current") or {}
    if cur.get("us_aqi") is None:
        raise AirDataError("No air quality data for this location")
    return Reading(place, float(cur["us_aqi"]), _opt_num(cur.get("pm2_5")),
                   _opt_num(cur.get("pm10")), _parse_observed_at(cur.get("time")))


def _first_field(mapping: dict[str, Any], *keys: str, fallback: Any = None) -> Any:
    """Return the first truthy field in mapping from keys, or fallback."""
    for k in keys:
        if val := mapping.get(k):
            return val
    return fallback


def _format_reverse_label(data: dict[str, Any]) -> str | None:
    """Build a valid city label from reverse-geocode fields, or None if unusable."""
    city = _first_field(data, "city", "locality", "principalSubdivision")
    locality = data.get("locality")
    country = data.get("countryName") or ""
    parts = [p for p in (city, country) if p]
    base = ", ".join(parts)
    if locality and city and locality != city:
        options: tuple[str, ...] = (f"{locality}, {base}".strip(", "), base)
    else:
        options = (base,)
    for label in options:
        if valid_city(label):
            return label
    return None


def place_name(lat: float, lon: float) -> str:
    """Turn rounded coordinates into 'City, Country'; never fails the request."""
    key = (lat, lon)
    if (hit := _cached(key, _names)) is not None:
        return hit
    try:
        r = requests.get(REVERSE_URL, params={"latitude": lat, "longitude": lon,
                                              "localityLanguage": "en"}, timeout=TIMEOUT)
        r.raise_for_status()
        label = _format_reverse_label(r.json())
        if not label:
            return "Your location"
        _store(_names, key, (time.time(), label))
        return label
    except (requests.RequestException, ValueError, AttributeError):
        return "Your location"


PINCODE_RE = re.compile(r"^\d{6}$")


def fetch_reading(city: str) -> Reading:
    """Geocode city and return its current AQI Reading (cached per city)."""
    key = "c:" + city.strip().lower()
    if (hit := _cached(key)):
        return hit
    try:
        g = requests.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=TIMEOUT)
        g.raise_for_status()
        results = g.json().get("results") or []
        if not results:
            raise AirDataError("Location not found")
        loc = results[0]
        reading = _air(loc["latitude"], loc["longitude"],
                       f"{loc['name']}, {loc.get('country', '')}".strip(", "))
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AirDataError("Air quality service unavailable") from exc
    _store(_cache, key, (time.time(), reading))
    return reading


def fetch_reading_coords(lat: float, lon: float, label: str | None = None) -> Reading:
    """Coordinates are rounded to ~1 km: enough for air data, better for privacy.

    `label` is a place name the user picked from search; otherwise the name is looked up.
    """
    lat, lon = round_coords(lat, lon)
    key = f"g:{lat},{lon}"
    base = _cached(key)
    if base is None:
        try:
            base = _air(lat, lon, "")
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise AirDataError("Air quality service unavailable") from exc
        _store(_cache, key, (time.time(), base))
    return replace(base, place=label or place_name(lat, lon))


def _nominatim_label(entry: dict[str, Any]) -> str:
    """Build the most specific valid label from a Nominatim address dict."""
    addr = entry.get("address", {})
    city = _first_field(addr, "city", "town", "county", "state_district")
    local = _first_field(addr, "suburb", "village", "neighbourhood", "postcode", fallback=entry.get("name"))
    state, country = addr.get("state"), addr.get("country")
    for parts in ((local, city, state, country), (local, city, country), (city, country)):
        label = ", ".join(p for p in parts if p)
        if valid_city(label):
            return label
    return ""


def _nominatim_search(q: str, limit: int) -> list[dict[str, Any]]:
    """Query Nominatim for Indian PIN codes / explicit searches under 1 req/s throttle."""
    global _last_nominatim
    acquired = False
    with _nom_lock:
        now = time.time()
        if now - _last_nominatim >= 1.0:
            _last_nominatim = now
            acquired = True
    if not acquired:
        return []
    out = []
    try:
        r2 = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": limit, "addressdetails": 1, "countrycodes": "in"},
            headers={"User-Agent": osm_user_agent()},
            timeout=TIMEOUT,
        )
        r2.raise_for_status()
        for x in r2.json() or []:
            try:
                if (label := _nominatim_label(x)):
                    out.append({"label": label, "lat": float(x["lat"]), "lon": float(x["lon"])})
            except (KeyError, TypeError, ValueError):
                continue
    except (requests.RequestException, ValueError, AttributeError) as exc:
        logger.warning("Nominatim search failed (%s)", type(exc).__name__)
    return out


def _open_meteo_search(q: str, limit: int) -> list[dict[str, Any]]:
    """Fallback/typeahead geocoding query via Open-Meteo."""
    out = []
    try:
        r = requests.get(GEOCODE_URL, params={"name": q, "count": limit, "language": "en"}, timeout=TIMEOUT)
        r.raise_for_status()
        res_json = r.json()
        raw = (res_json.get("results") or []) if isinstance(res_json, dict) else []
        for x in raw:
            try:
                label = ", ".join(v for v in (x["name"], x.get("admin1"), x.get("country")) if v)
                if valid_city(label):
                    out.append({"label": label, "lat": float(x["latitude"]), "lon": float(x["longitude"])})
            except (KeyError, TypeError, ValueError):
                continue
    except (requests.RequestException, ValueError, AttributeError) as exc:
        logger.warning("Open-Meteo search failed (%s)", type(exc).__name__)
    return out


def search_places(query: str, limit: int = 5, is_explicit: bool = False) -> list[dict[str, Any]]:
    """City, neighborhood or pincode suggestions for the search box."""
    q = (query or "").strip()
    if not q:
        return []
    key = f"s:{int(is_explicit)}:{q.lower()}"
    if (hit := _cached(key)) is not None:
        return hit
    out = _nominatim_search(q, limit) if (PINCODE_RE.match(q) or is_explicit) else []
    if not out:
        out = _open_meteo_search(q, limit)
    if out:
        _store(_cache, key, (time.time(), out))
    return out
