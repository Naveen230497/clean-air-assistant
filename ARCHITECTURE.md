# Architecture

Clean Air Assistant is a Flask + Vanilla JS single-page web application run in production behind Gunicorn (`Dockerfile`: `--workers 1 --threads 4 --timeout 60`).

## Backend Modules (`app/`)

- `app/__init__.py`: Application factory (`create_app`), `ProxyFix(x_for=1)`, `MAX_CONTENT_LENGTH` (`5 MB`), blueprint registration, and `after_request` security headers (`CSP`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`).
- `app/routes.py`: HTTP endpoints (`/`, `/health`, `/api/plan`, `/api/places`, `/api/locate`, `/api/advisory`, `/api/image-aqi`, `/api/chat`, `/api/nearby`), `_guard()` request checks, and sanitized error responses.
- `app/validation.py`: Strict field whitelists, regex checks (`CITY_RE`), coordinate/AQI bounds, base64 decoding, and image magic-byte validation (`MAX_IMAGE_BYTES = 3 MB`, `MAX_UPLOAD_BYTES = 5 MB`).
- `app/rate_limit.py`: Thread-safe in-memory per-IP sliding-window limiter (`LIMIT = 30` per `WINDOW = 60` s) with stale-IP pruning.
- `app/shared.py`: Shared thread-safe FIFO-bounded cache helpers (`cache_get`, `cache_store_bounded`), `0.01`-degree coordinate rounding (`round_coords`), language list, and `osm_user_agent`.
- `app/air_data.py`: Open-Meteo geocoding and air-quality client, BigDataCloud reverse geocoding, and 1-req/s throttled Nominatim place search with `600` s cache (`MAX_ENTRIES = 2000`).
- `app/aqi.py` & `app/recommender.py`: Deterministic EPA US AQI scale (`0-500`) and personalized household exposure-reduction rule engine.
- `app/i18n.py` & `app/locales/`: Machine-assisted translations, not guaranteed expert-reviewed, across 6 languages (`en`, `hi`, `te`, `ta`, `bn`, `mr`) with English fallback (`t()`, `band_label()`, `localize_error()`), covering rule plans, template briefings, nearby categories, validation (`400`), rate-limit (`429`), AI availability (`503`), image-read (`502`), air-data (`502`), and `locate` fallback messages. Oversized `413` responses above `32 KB` without `?lang=` fall back to English.
- `app/gemini.py` & `app/ai.py`: Direct Gemini REST client (`x-goog-api-key` header, `60.0` s 429 circuit breaker, model fallback) powering briefings, `get_air_quality` tool calling, Google Search advisories, image AQI extraction, and chat, with localized rule-based fallback.
- `app/nearby.py`: Keyless OpenStreetMap Overpass client (`ovp.dresel.systems`, `maps.mail.ru`) with `30.0` s deadline, 1-req/2 s throttle, UTC daily cap, and `600` s fresh / `86400` s stale caches.

## Frontend Modules (`app/static/`)

- `index.html` & `style.css`: Semantic single-page UI with a top `🌐` `#lang` selector (`English, हिन्दी, తెలుగు, தமிழ், বাংলা, मराठी`, `localStorage`-backed in `try/catch`), declarative `data-i18n*` attributes, dark/light theme variables, wrapping-safe controls, and `.sr`/`.sr-only` screen-reader text.
- Deferred IIFE modules (no build pipeline, zero raw HTML injection): `locales/{en,hi,te,ta,bn,mr}.js` -> `i18n.js` -> `locate.js`, `reading.js`, `dom.js` -> `plan_view.js`, `map_location.js`, `search_box.js`, `extras.js` -> `app.js`.
- `app/static/i18n.js` & `app/static/locales/*.js`: Machine-assisted translations, not guaranteed expert-reviewed, applying live full-page text/attributes/`<html lang>` (`applyPage`, `initPageI18n`), dynamic cards, geolocation/search statuses, nearby categories, and `m`/`km` units via `textContent`; third-party OpenStreetMap place names, vendored Leaflet controls/attribution, numeric `Lat/Lon` coordinates, and brand names (`Open-Meteo`, `Google Search`, `OpenStreetMap`) remain English.
- Self-hosted map assets: vendored `leaflet.js`, `leaflet.css`, and `pin.svg`.

## Primary Request Flow (`POST /api/plan`)

1. `app.js` triggers `plan_view.buildPayload()` with `AQI > coords > city` priority and sends JSON via `Dom.postJson`.
2. `routes.plan()` runs `_guard(8192)` (rate limit + payload cap) and `validation.parse_request()`.
3. Manual or screenshot AQI skips Open-Meteo; otherwise `ai.agent_reading()` returns a cached/live `Reading` (via Gemini `get_air_quality` tool call with re-validated city/coords or direct `air_data`).
4. `recommender.build_plan()` deterministically builds actions and `est_reduction_pct`, `ai.briefing()` adds Gemini or template copy, and JSON returns to `plan_view.renderPlan()`.
