"""HTTP routes bound cleanly to validation, rules, AI, and OpenStreetMap services."""
from typing import Any

import requests
from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue

from . import ai, gemini, i18n, rate_limit
from .air_data import AirDataError, place_name, search_places
from .nearby import OverpassDailyCapError, OverpassError, OverpassRateLimitError, nearby_places
from .recommender import build_plan
from .shared import round_coords
from .validation import (
    MAX_UPLOAD_BYTES,
    ValidationError,
    parse_advisory,
    parse_aqi_source,
    parse_chat,
    parse_image,
    parse_locate,
    parse_nearby,
    parse_request,
    valid_city,
)

bp = Blueprint("main", __name__)

SMALL_BODY = 8 * 1024
_SOURCE_KEYS = {"Entered by you": "source.manual", "Read from your screenshot": "source.image"}


def _guard(max_bytes: int = SMALL_BODY) -> tuple[Response, int] | None:
    """Return an error response if the request is rate limited or too large, else None."""
    if rate_limit.is_rate_limited(request.remote_addr or "?"):
        return jsonify(error="Too many requests, please wait a minute"), 429
    size = request.content_length
    if size is None:
        size = len(request.get_data(cache=True))
    if size > max_bytes:
        return jsonify(error="Request too large"), 413
    return None


def _ai_unavailable() -> tuple[Response, int]:
    """Return the standard 503 JSON response when Gemini is unconfigured."""
    return jsonify(error="This AI feature needs a Gemini API key on the server."), 503


@bp.get("/")
def index() -> Response:
    """Serve the single-page web UI entrypoint."""
    return send_from_directory(bp.root_path + "/static", "index.html")


@bp.get("/health")
def health() -> dict[str, Any]:
    """Return service liveness status and whether Gemini is enabled."""
    return {"status": "ok", "gemini": gemini.enabled()}


def _resolve_plan_reading(
    city: str | None,
    aqi: float | None,
    aqi_source: str,
    coords: tuple[float, float] | None,
    label: str | None,
) -> tuple[float, str, str, str | None, float | None, float | None, list[str]]:
    """Resolve live or manual AQI, place label, source tag, timestamps, and AI trace flags."""
    if aqi is None:
        reading, how = ai.agent_reading(city, coords, label)
        features = ["function_calling"] if how == "gemini_function_call" else []
        return reading.aqi, reading.place, "Open-Meteo", reading.observed_at, reading.pm25, reading.pm10, features
    source = "Read from your screenshot" if aqi_source == "image" else "Entered by you"
    return aqi, (city or "your location"), source, None, None, None, []


def _resolve_display_place(
    place: str, city: str | None, coords: tuple[float, float] | None, label: str | None
) -> str:
    """Return a readable display place, reverse-geocoding coordinates when needed."""
    if place and place.lower() not in ("your location", "your area", ""):
        return place
    if coords:
        return label or place_name(*coords) or f"Lat {coords[0]:.2f}, Lon {coords[1]:.2f}"
    return city or "your location"


@bp.post("/api/plan")
def plan() -> ResponseReturnValue:
    """Build and return an AQI action plan with briefing and reading metadata."""
    if (blocked := _guard()):
        return blocked
    raw_json = request.get_json(silent=True)
    try:
        city, aqi, profile, lang, coords, label = parse_request(raw_json)
        aqi_source = parse_aqi_source(raw_json)
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    try:
        aqi, place, source, observed_at, pm25, pm10, features = _resolve_plan_reading(
            city, aqi, aqi_source, coords, label
        )
    except AirDataError as exc:
        return jsonify(error=i18n.t("err.plan_air", lang, error=exc)), 502
    place = _resolve_display_place(place, city, coords, label)
    if source in _SOURCE_KEYS:
        source = i18n.t(_SOURCE_KEYS[source], lang)
    result = build_plan(aqi, profile, lang).to_dict()
    result["place"], result["lang"] = place, lang
    result["briefing"] = ai.briefing(result, place, lang)
    result["source"], result["observed_at"] = source, observed_at
    result["pm2_5"], result["pm10"] = pm25, pm10
    if result["briefing"]["source"] == "gemini":
        features += ["structured_output", "multilingual", "system_instructions", "safety_settings"]
    result["ai_features"] = features
    return jsonify(result)


@bp.get("/api/places")
def places() -> ResponseReturnValue:
    """Return autocomplete place suggestions for the query parameter q."""
    if (blocked := _guard()):
        return blocked
    q = request.args.get("q", "").strip()
    explicit = request.args.get("explicit", "0") in ("1", "true")
    if not valid_city(q):
        return jsonify(results=[])
    try:
        return jsonify(results=search_places(q, is_explicit=explicit))
    except AirDataError:
        return jsonify(results=[])


@bp.get("/api/locate")
def locate() -> ResponseReturnValue:
    """Reverse-geocode lat/lon query coordinates into city and place labels."""
    if (blocked := _guard()):
        return blocked
    try:
        lat_f, lon_f = parse_locate(request.args.get("lat"), request.args.get("lon"))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    place = place_name(lat_f, lon_f)
    city = place.split(",")[0].strip() if place and place.lower() != "your location" else ""
    return jsonify(lat=lat_f, lon=lon_f, city=city, place=place)


def _handle_gemini_error(exc: gemini.GeminiError | None, default_msg: str, lang: str = "en") -> tuple[Response, int]:
    """Log sanitized Gemini failure details and return a user-safe 502 error response."""
    status_code = getattr(exc, "status_code", None)
    error_status = getattr(exc, "error_status", None)
    current_app.logger.warning("Gemini request failed: status=%s error_status=%s", status_code, error_status)
    msg = (
        i18n.t("err.rate_limit_ai", lang)
        if status_code == 429
        else (i18n.t(default_msg, lang) or default_msg)
    )
    return jsonify(error=msg), 502


@bp.post("/api/advisory")
def advisory() -> ResponseReturnValue:
    """Return Google Search grounded local air-pollution advisories for a city."""
    if (blocked := _guard()):
        return blocked
    try:
        city, lang = parse_advisory(request.get_json(silent=True))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    if not gemini.enabled():
        return _ai_unavailable()
    try:
        return jsonify(ai.local_advisory(city, lang))
    except gemini.GeminiError as exc:
        return _handle_gemini_error(exc, "err.advisory", lang)


@bp.post("/api/image-aqi")
def image_aqi() -> ResponseReturnValue:
    """Read AQI or sky visibility from an uploaded PNG/JPEG/WebP image."""
    if (blocked := _guard(MAX_UPLOAD_BYTES)):
        return blocked
    try:
        b64, mime = parse_image(request.get_json(silent=True))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    if not gemini.enabled():
        return _ai_unavailable()
    try:
        return jsonify(ai.read_image(b64, mime))
    except gemini.GeminiError as exc:
        return _handle_gemini_error(exc, "Could not read that image.")


@bp.post("/api/chat")
def chat() -> ResponseReturnValue:
    """Answer a contextual follow-up question about the current air plan."""
    if (blocked := _guard()):
        return blocked
    try:
        q, history, aqi, place, lang = parse_chat(request.get_json(silent=True))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    if not gemini.enabled():
        return _ai_unavailable()
    try:
        return jsonify(answer=ai.chat(q, history, aqi, place, lang))
    except gemini.GeminiError as exc:
        return _handle_gemini_error(exc, "err.chat", lang)


@bp.post("/api/nearby")
def nearby() -> ResponseReturnValue:
    """Return nearby healthcare, pharmacy, library, or mall venues via OpenStreetMap."""
    if (blocked := _guard()):
        return blocked
    try:
        lat, lon, lang = parse_nearby(request.get_json(silent=True))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    r_lat, r_lon = round_coords(lat, lon)
    try:
        found = nearby_places(r_lat, r_lon)
        payload = {"places": list(found), "attribution": "Data © OpenStreetMap contributors (ODbL)"}
        if getattr(found, "stale", False):
            payload["stale"] = True
        return jsonify(payload)
    except (OverpassDailyCapError, OverpassRateLimitError) as exc:
        return jsonify(error=str(exc)), 429
    except (OverpassError, requests.RequestException, ValueError, TypeError, KeyError) as exc:
        current_app.logger.warning("Nearby lookup failed (%s)", type(exc).__name__)
        return jsonify(
            error=i18n.t("err.nearby_busy", lang),
            map_url=f"https://www.openstreetmap.org/#map=15/{r_lat}/{r_lon}",
        ), 502
