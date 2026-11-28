# Security Policy

## Implemented Controls

- **HTTP Security Headers (`app/__init__.py`):** Every response sets `Content-Security-Policy` (`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, and `Permissions-Policy: geolocation=(self), camera=(), microphone=()`.
- **Request Size & Input Validation (`app/routes.py`, `app/validation.py`):** JSON routes enforce `SMALL_BODY` (`8192` bytes) and `/api/image-aqi` enforces `MAX_UPLOAD_BYTES` (`5 MB`), checking actual body length even when `Content-Length` is absent. City names match `CITY_RE`, AQI rejects booleans and out-of-range numbers, and images require valid base64, `MAX_IMAGE_BYTES` (`3 MB`), and matching `PNG`/`JPEG`/`RIFF....WEBP` file headers.
- **Rate Limiting & Upstream Guards (`app/rate_limit.py`, `app/gemini.py`, `app/nearby.py`):** Per-IP sliding-window limiting (`30` requests per `60` s, resolved through `ProxyFix(x_for=1)`), sanitized warnings (logging error type or status only), `x-goog-api-key` header transport, `60.0` s Gemini 429 circuit breaker, `1`-req/`2` s Overpass throttle + UTC daily cap, and strict `node`/`way`/`relation` ID validation on OSM links.
- **DOM & Secret Hygiene (`app/static/`, `tests/test_hygiene.py`):** First-party JS renders via `textContent` and `createElement`/`createElementNS` rather than raw HTML sinks, `index.html` has no inline scripts or styles, and automated hygiene checks reject known API key prefixes.

## Current Limitations

- **No HSTS Header:** Flask does not send `Strict-Transport-Security`; HTTPS enforcement relies on the hosting proxy (such as Cloud Run).
- **No Explicit CORS Policy:** No `Access-Control-*` headers are returned; browser cross-origin API access relies on default same-origin restrictions.
- **Single-Instance Rate & Cache State:** `rate_limit._hits`, Overpass counters, and response caches live in process memory (`Dockerfile` runs `--workers 1`) and are not shared across multiple replicas.
- **Geolocation Precision & Map Tiles:** `fetch_reading_coords` and `/api/nearby` round coordinates to `0.01` degrees, whereas `GET /api/locate` (and the `"Your location"` display fallback) sends exact query coordinates to BigDataCloud; browser Leaflet map loads request tiles directly from `tile.openstreetmap.org`.

## Reporting Issues

To report a security concern or misconfiguration, please contact the maintainer via the repository: <https://github.com/Naveen230497/clean-air-assistant>.
