# Architecture Decisions

## 1. Direct Gemini REST Client Over SDK (`app/gemini.py`)
Calls `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` directly over `requests`. This keeps runtime dependencies minimal (`requirements.txt`: `Flask`, `requests`, `gunicorn`) while centralizing `x-goog-api-key` headers, `gemini-2.5` thinking config, model fallback, and a thread-safe `60.0` s 429 circuit breaker.

## 2. Deterministic Rules First, AI Optional (`app/recommender.py`, `app/ai.py`)
`recommender.build_plan()` deterministically calculates EPA AQI bands, tailored actions, and `est_reduction_pct`. Gemini enriches copy (`briefing`), handles `get_air_quality` lookup, reads uploaded images, grounds advisories, and powers chat; `template_briefing()` guarantees `/api/plan` still works with no API key or open breaker.

## 3. Keyless Public APIs With Throttles & Caches (`app/air_data.py`, `app/nearby.py`)
Sensor readings and venue lookups use keyless Open-Meteo, BigDataCloud, Nominatim, and OpenStreetMap Overpass mirrors (`ovp.dresel.systems`, `maps.mail.ru`). Lock-guarded throttles (Nominatim 1 req/s; Overpass 1 req/2 s + UTC daily cap), FIFO-bounded caches (`cache_store_bounded`), and stale-if-error/map-link fallbacks absorb upstream rate limits.

## 4. Zero-Build Vanilla JS IIFEs Under Strict CSP (`app/__init__.py`, `app/static/`)
The frontend loads vendored Leaflet (`leaflet.js`, `leaflet.css`, `pin.svg`) and 8 deferred IIFE modules with no transpiler or inline scripts/styles, constructing DOM nodes solely via `textContent` and `createElement`/`createElementNS` under `script-src 'self'`.

## 5. Proxy-Aware Limiting & Per-Route Body Caps (`app/routes.py`, `app/rate_limit.py`)
`ProxyFix(x_for=1)` resolves client IPs behind Cloud Run, `_guard()` enforces a `30`-req/`60` s sliding window with stale-entry pruning before measuring body bytes (`8192` bytes JSON; `MAX_UPLOAD_BYTES = 5 MB` image upload), and `Dockerfile` runs single-process `--workers 1 --threads 4` so in-memory limiters and caches stay consistent per instance.

## 6. Machine-Assisted 6-Language Outputs With English Form Labels (`app/i18n.py`, `app/locales/`, `app/static/i18n.js`)
Generated plans, EPA bands, safety disclaimers, fallback briefings, reading metadata, dynamic card labels, nearby venue categories, `m`/`km` distance units, and `lang`-aware route errors use machine-assisted translations (not guaranteed expert-reviewed) across `en`, `hi`, `te`, `ta`, `bn`, and `mr` with English fallback — not full UI localization. Returned OpenStreetMap venue names, static form labels, geolocation/search status text, rate-limit (`429`) and `400` error messages, and `/api/image-aqi` error text stay English so `"Answer language"` translates generated outputs cleanly without full-page layout shifts.
