# Testing Guide

All automated tests run completely offline without live Gemini, Open-Meteo, Nominatim, BigDataCloud, or Overpass calls.

## Offline Guard (`tests/helpers.py`)

- `NoNetworkTestCase` resets `gemini._breaker_until` and `ai._briefing_cache`, then patches `socket.socket.connect` and `socket.create_connection` to raise `RuntimeError` if any code attempts a real socket connection.
- `ApiTestCase` builds an isolated Flask `test_client()` and clears `rate_limit._hits` before and after each test; `_AirDataApiTestCase` (`tests/test_air_data.py`) additionally resets `air_data._cache`, `air_data._names`, and `air_data._last_nominatim`.

## Test Suites (`109` Python + `26` Node)

```bash
# Python suite (109 tests, strict ResourceWarning visibility)
python -W default -m unittest discover -s tests -t .

# Coverage across app/ (94% measured: 1071 statements, 65 missed; CI min 90%)
python -W default -m coverage run --source=app -m unittest discover -s tests -t .
python -m coverage report --fail-under=90

# Frontend Node suites (26 tests)
node --test tests/
```

- **Python breakdown (`tests/`):** `test_air_data.py` (24), `test_nearby.py` (18), `test_gemini.py` (17), `test_ai_routes.py` (13), `test_routes.py` (13), `test_recommender.py` (8), `test_i18n.py` (6), `test_validation.py` (6), `test_hygiene.py` (4).
- **Frontend breakdown (`tests/`):** `locate.test.js` (11), `ui.test.js` (10), `reading.test.js` (5).
- **Hygiene (`tests/test_hygiene.py`):** Checks first-party `app/static/*.js` for DOM HTML-injection sinks, `index.html` for inline `<script>`/`<style>` blocks or attributes, all tracked files for API key prefixes, and total tracked repository size under `1 MB`.

## Static Analysis & CI Gates (`.github/workflows/ci.yml`)

```bash
ruff check app tests
flake8 app tests
interrogate -vv --fail-under=95 app
test -z "$(radon cc -n C app)"
pylint --fail-under=9.5 app
npx --yes eslint@9.39.5 app/static/
```

- Measured locally after final code edits: `ruff` (`0` findings), `flake8` (`0` findings), `interrogate` (`100.0%`), `radon` (`0` functions above CC `10`), `pylint` (`9.90/10`), and `eslint` (`0` errors).
