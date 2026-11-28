"""Tests for core HTTP routes (/ , /health, /api/plan, /api/places, /api/locate) and rate limiting."""
import io
import json
import unittest
from unittest.mock import patch

from app import rate_limit
from app.air_data import AirDataError, Reading
from app.rate_limit import is_rate_limited
from tests.helpers import ApiTestCase


class ApiTests(ApiTestCase):
    """HTTP route integration tests for index, health, plans, headers, and rate limits."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_manual_aqi(self) -> None:
        r = self.client.post("/api/plan", json={"aqi": 260, "city": "Delhi"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["band"], "Very unhealthy")
        self.assertEqual(body["briefing"]["source"], "rules")

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    @patch("app.ai.fetch_reading", return_value=Reading("Pune, India", 120, 40, 60))
    def test_city_lookup(self, _) -> None:
        r = self.client.post("/api/plan", json={"city": "Pune"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["place"], "Pune, India")

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    @patch("app.routes.place_name", return_value="Hyderabad, India")
    @patch("app.ai.fetch_reading_coords", return_value=Reading("Your location", 175, 80, 120))
    def test_geolocation_lookup(self, fetch, _place_mock) -> None:
        r = self.client.post("/api/plan", json={"lat": 17.385, "lon": 78.4867})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["band"], "Unhealthy")
        fetch.assert_called_once_with(17.385, 78.4867, label=None)

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    @patch("app.ai.fetch_reading", side_effect=AirDataError("Air quality service unavailable"))
    def test_upstream_failure(self, _) -> None:
        r = self.client.post("/api/plan", json={"city": "Pune"})
        self.assertEqual(r.status_code, 502)

    def test_bad_request_and_headers(self) -> None:
        r = self.client.post("/api/plan", json={"aqi": -5})
        self.assertEqual(r.status_code, 400)
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")

    def test_index_and_health(self) -> None:
        with self.client.get("/") as r:
            self.assertEqual(r.status_code, 200)
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ok")

    def test_csp_allows_openstreetmap_tiles(self) -> None:
        with self.client.get("/") as r:
            self.assertEqual(r.status_code, 200)
            csp = r.headers.get("Content-Security-Policy", "")
        self.assertIn("https://tile.openstreetmap.org", csp)

    def test_rate_limiter_blocks_at_30_requests(self) -> None:
        ip = "192.0.2.1"
        for _ in range(30):
            self.assertFalse(is_rate_limited(ip))
        self.assertTrue(is_rate_limited(ip))

    def test_plan_rejects_invalid_place_label(self) -> None:
        r = self.client.post("/api/plan", json={"aqi": 100, "place": "<script>bad</script>"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Place name is invalid", r.get_json()["error"])

    def test_plan_oversized_payload_returns_413(self) -> None:
        r = self.client.post("/api/plan", json={"aqi": 150, "city": "Delhi", "pad": "z" * 9000})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.get_json(), {"error": "Request too large"})

    @patch("app.routes.search_places", side_effect=AirDataError("Upstream down"))
    def test_places_route_handles_air_data_error(self, _) -> None:
        r = self.client.get("/api/places?q=Delhi&explicit=1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"results": []})

    def test_rate_limiter_prunes_expired_ips(self) -> None:
        now = [1000.0]
        with patch("app.rate_limit.time.time", side_effect=lambda: now[0]):
            self.assertFalse(is_rate_limited("192.0.2.10"))
            now[0] = 1000.0 + rate_limit.WINDOW + 5.0
            self.assertFalse(is_rate_limited("192.0.2.11"))
        self.assertNotIn("192.0.2.10", rate_limit._hits)
        self.assertIn("192.0.2.11", rate_limit._hits)

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_plan_chunked_without_content_length_enforces_limit(self) -> None:
        small = json.dumps({"aqi": 150}).encode()
        r_ok = self.client.post(
            "/api/plan", input_stream=io.BytesIO(small), content_type="application/json",
            headers={"Transfer-Encoding": "chunked"},
            environ_base={"wsgi.input_terminated": True, "CONTENT_LENGTH": ""},
        )
        self.assertEqual(r_ok.status_code, 200)

        large = json.dumps({"aqi": 150, "pad": "z" * 9000}).encode()
        r_413 = self.client.post(
            "/api/plan", input_stream=io.BytesIO(large), content_type="application/json",
            headers={"Transfer-Encoding": "chunked"},
            environ_base={"wsgi.input_terminated": True, "CONTENT_LENGTH": ""},
        )
        self.assertEqual(r_413.status_code, 413)
        self.assertEqual(r_413.get_json(), {"error": "Request too large"})


if __name__ == "__main__":
    unittest.main()
