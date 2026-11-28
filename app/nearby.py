"""Nearby clean-air help places using OpenStreetMap Overpass API (no API key required)."""
import math
import os
import re
import threading
import time
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

import requests

from .shared import cache_get, cache_store_bounded, osm_user_agent, round_coords

OVERPASS_URLS = (
    "https://ovp.dresel.systems/api-as/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
TIMEOUT = 14
DEADLINE = 30.0
TTL = 600  # 10 minutes
MAX_ENTRIES = 500
STALE_TTL = 86400  # 24 hours
STALE_MAX_ENTRIES = 300
EARTH_RADIUS_M = 6371000.0
ASIA_LAT_BOUNDS = (-10.0, 80.0)
ASIA_LON_BOUNDS = (25.0, 180.0)
MAX_NAME_LEN = 80
SEARCH_RADIUS_M = 4000
MAX_OVERPASS_ELEMENTS = 40

_cache: dict = {}
_stale_cache: dict = {}
_cache_lock = threading.Lock()
_rate_lock = threading.Lock()
_last_request_time: float | None = None
_daily_count: int = 0
_daily_date: int | None = None


class NearbyResult(list):
    """List of place dicts carrying a stale flag for 24-hour fallback responses."""

    def __init__(self, items: Iterable[dict[str, Any]] = (), *, stale: bool = False) -> None:
        """Initialize a NearbyResult list with optional stale-cache indicator."""
        super().__init__(items)
        self.stale = stale


class OverpassError(Exception):
    """Raised when Overpass API query fails or is unreachable."""


class OverpassRateLimitError(OverpassError):
    """Raised when 1 request per 2 seconds rate limit is exceeded."""


class OverpassDailyCapError(OverpassError):
    """Raised when the global daily cap for Overpass queries is reached."""


def _get_daily_cap() -> int:
    """Return the configured UTC daily Overpass query limit."""
    try:
        return max(0, int(os.environ.get("NEARBY_DAILY_CAP", "80")))
    except (ValueError, TypeError):
        return 80


def _servers_for(lat: float, lon: float) -> tuple[str, ...]:
    """Select Overpass mirrors ordered for Asian vs global coordinates."""
    if ASIA_LAT_BOUNDS[0] <= lat <= ASIA_LAT_BOUNDS[1] and ASIA_LON_BOUNDS[0] <= lon <= ASIA_LON_BOUNDS[1]:
        return OVERPASS_URLS
    return ("https://maps.mail.ru/osm/tools/overpass/api/interpreter",)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in metres between two points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def sanitize_name(raw: str) -> str:
    """Clip to 80 chars and strip control characters and any '<' or '>' characters."""
    if not raw:
        return ""
    clean = re.sub(r'[\x00-\x1f\x7f-\x9f<>]', '', str(raw))
    return clean[:MAX_NAME_LEN].strip()


def _get_from_cache(cache: dict[Any, Any], key: tuple[float, float], ttl: int) -> list[dict[str, Any]] | None:
    """Return cached nearby places if still within TTL, else None."""
    hit = cache_get(cache, key, ttl, _cache_lock, time.time())
    return list(hit) if hit is not None else None


def _store_in_cache(
    cache: dict[Any, Any], key: tuple[float, float], value: list[dict[str, Any]], max_entries: int
) -> None:
    """Cache non-empty nearby places under max_entries bound."""
    if value:
        cache_store_bounded(cache, key, (time.time(), list(value)), max_entries, _cache_lock)


def _element_category(tags: dict[str, Any]) -> str | None:
    """Map OSM tags to a display category, or None if not relevant."""
    amenity, shop = tags.get("amenity"), tags.get("shop")
    if amenity in ("hospital", "clinic"):
        return "Hospital or clinic"
    if amenity == "pharmacy":
        return "Pharmacy"
    if amenity == "library":
        return "Library"
    if shop == "mall":
        return "Mall"
    return None


def _element_coords(el: dict[str, Any], el_type: str) -> tuple[float, float] | None:
    """Extract numeric (lat, lon) from a node or way/relation center, else None."""
    loc = el if el_type == "node" else (el.get("center") or {})
    lat, lon = loc.get("lat"), loc.get("lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (ValueError, TypeError):
        return None


def _osm_url(el_type: Any, el_id: Any) -> str | None:
    """Return a canonical OpenStreetMap entity URL for valid node, way, or relation IDs."""
    if el_type not in ("node", "way", "relation"):
        return None
    if not isinstance(el_id, int) or isinstance(el_id, bool) or el_id <= 0:
        return None
    return f"https://www.openstreetmap.org/{el_type}/{el_id}"


def _element_to_place(el: dict[str, Any], origin_lat: float, origin_lon: float) -> dict[str, Any] | None:
    """Convert a raw Overpass element dict into a sanitized place dict."""
    if not isinstance(el, dict):
        return None
    raw_tags = el.get("tags")
    tags = raw_tags if isinstance(raw_tags, dict) else {}
    name = sanitize_name(tags.get("name") or "")
    category = _element_category(tags) if name else None
    el_type = el.get("type", "node")
    url = _osm_url(el_type, el.get("id")) if category else None
    coords = _element_coords(el, el_type) if url else None
    if not category or not url or coords is None:
        return None
    lat_f, lon_f = coords
    return {
        "name": name,
        "category": category,
        "distance_m": round(haversine(origin_lat, origin_lon, lat_f, lon_f)),
        "url": url,
    }


def parse_overpass_elements(
    elements: list[dict[str, Any]], origin_lat: float, origin_lon: float
) -> list[dict[str, Any]]:
    """Parse raw elements from Overpass, group by category, keep nearest 3 per category, sort by distance."""
    cat_items = defaultdict(list)
    for el in elements:
        if (place := _element_to_place(el, origin_lat, origin_lon)) is not None:
            cat_items[place["category"]].append(place)

    selected = []
    for cat in ("Hospital or clinic", "Pharmacy", "Library", "Mall"):
        items = cat_items.get(cat, [])
        items.sort(key=lambda x: x["distance_m"])
        selected.extend(items[:3])
    selected.sort(key=lambda x: x["distance_m"])
    return selected


def _check_nearby_quota() -> None:
    """Enforce daily UTC cap and 1 req / 2s rate limit before hitting Overpass."""
    global _last_request_time, _daily_count, _daily_date
    with _rate_lock:
        now = time.time()
        utc_day = int(now // 86400)
        if _daily_date != utc_day:
            _daily_date = utc_day
            _daily_count = 0
        if _daily_count >= _get_daily_cap():
            raise OverpassDailyCapError("Daily limit for nearby places reached.")
        if _last_request_time is not None and (now - _last_request_time < 2.0):
            raise OverpassRateLimitError("Please wait a moment before searching nearby places again.")
        _last_request_time = now
        _daily_count += 1


def _overpass_query(lat: float, lon: float) -> str:
    """Build Overpass QL query for nearby health and clean-air venues."""
    clauses = []
    for key, val in (("amenity", "hospital"), ("amenity", "clinic"), ("amenity", "pharmacy"),
                     ("amenity", "library"), ("shop", "mall")):
        for kind in ("node", "way"):
            clauses.append(f'  {kind}["{key}"="{val}"](around:{SEARCH_RADIUS_M},{lat},{lon});')
    return "[out:json][timeout:12];\n(\n" + "\n".join(clauses) + f"\n);\nout center tags {MAX_OVERPASS_ELEMENTS};"


def _fetch_overpass(lat: float, lon: float, ql: str) -> dict[str, Any] | None:
    """Query Overpass mirrors sequentially until valid elements arrive or DEADLINE expires."""
    headers = {"User-Agent": osm_user_agent()}
    deadline = time.time() + DEADLINE
    for url in _servers_for(lat, lon):
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            resp = requests.post(url, data={"data": ql}, headers=headers, timeout=min(TIMEOUT, remaining))
            resp.raise_for_status()
            parsed = resp.json()
            if isinstance(parsed, dict) and isinstance(parsed.get("elements"), list):
                return parsed
        except (requests.RequestException, ValueError):
            continue
    return None


def nearby_places(lat: float, lon: float) -> NearbyResult:
    """Search for nearby hospitals, clinics, pharmacies, libraries, and malls within 4000m using Overpass API."""
    lat, lon = round_coords(lat, lon)
    cache_key = (lat, lon)
    if (cached := _get_from_cache(_cache, cache_key, TTL)) is not None:
        return NearbyResult(cached, stale=False)

    _check_nearby_quota()
    data = _fetch_overpass(lat, lon, _overpass_query(lat, lon))
    if data is None:
        stale_places = _get_from_cache(_stale_cache, cache_key, STALE_TTL)
        if stale_places is not None:
            return NearbyResult(stale_places, stale=True)
        raise OverpassError("Overpass API request failed")

    places = parse_overpass_elements(data["elements"], lat, lon)
    if places:
        _store_in_cache(_cache, cache_key, places, MAX_ENTRIES)
        _store_in_cache(_stale_cache, cache_key, places, STALE_MAX_ENTRIES)
    return NearbyResult(places, stale=False)
