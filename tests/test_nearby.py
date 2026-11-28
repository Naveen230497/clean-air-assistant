"""Tests for OpenStreetMap Overpass nearby clean-air help and caches."""
import time
import unittest
from unittest.mock import patch

import requests

from app import nearby
from app.nearby import OverpassError, haversine, nearby_places, parse_overpass_elements
from tests.helpers import ApiTestCase, FakeResp


class NearbyOverpassTests(ApiTestCase):
    """Tests for Overpass parsing, caching, mirror failover, daily caps, and /api/nearby."""

    def setUp(self) -> None:
        """Reset Overpass caches, rate-limit timestamp, and daily counters."""
        super().setUp()
        nearby._cache.clear()
        nearby._stale_cache.clear()
        nearby._last_request_time = None
        nearby._daily_count = 0
        nearby._daily_date = None
        self.addCleanup(nearby._cache.clear)
        self.addCleanup(nearby._stale_cache.clear)

    def test_haversine_known_guntur_distance(self) -> None:
        d = haversine(16.3067, 80.4423, 16.2980, 80.4450)
        expected = 1009.4
        self.assertAlmostEqual(d, expected, delta=expected * 0.01)

    def test_parse_overpass_elements(self) -> None:
        sample_elements = [
            {"type": "node", "id": 101, "lat": 16.3001, "lon": 80.4401,
             "tags": {"name": "<General> Hospital", "amenity": "hospital"}},
            {"type": "node", "id": 102, "lat": 16.3010, "lon": 80.4410,
             "tags": {"name": "City Clinic", "amenity": "clinic"}},
            {"type": "node", "id": 103, "lat": 16.3020, "lon": 80.4420,
             "tags": {"name": "Care Hospital", "amenity": "hospital"}},
            {"type": "node", "id": 104, "lat": 16.3030, "lon": 80.4430,
             "tags": {"name": "Far Hospital", "amenity": "hospital"}},
            {"type": "way", "id": 201, "center": {"lat": 16.3005, "lon": 80.4405},
             "tags": {"name": "Apollo Pharmacy", "amenity": "pharmacy"}},
            {"type": "node", "id": 105, "lat": 16.3015, "lon": 80.4415,
             "tags": {"name": "City Library", "amenity": "library"}},
            {"type": "relation", "id": 301, "center": {"lat": 16.3025, "lon": 80.4425},
             "tags": {"name": "Metro Mall", "shop": "mall"}},
            {"type": "node", "id": 106, "lat": 16.3000, "lon": 80.4400, "tags": {"amenity": "hospital"}},
            {"type": "node", "id": 107, "lat": 16.3000, "lon": 80.4400, "tags": {"name": "Bakery", "shop": "bakery"}},
        ]
        parsed = parse_overpass_elements(sample_elements, 16.30, 80.44)
        names = [p["name"] for p in parsed]
        self.assertIn("General Hospital", names)
        self.assertNotIn("<General> Hospital", names)
        self.assertNotIn("Far Hospital", names)
        self.assertEqual(len([p for p in parsed if p["category"] == "Hospital or clinic"]), 3)
        self.assertEqual(len(parsed), 6)
        self.assertTrue(parsed[0]["url"].startswith("https://www.openstreetmap.org/"))
        distances = [p["distance_m"] for p in parsed]
        self.assertEqual(distances, sorted(distances))

    def test_nearby_route_validation_rejections(self) -> None:
        bad_payloads = [{}, {"lat": 16.3}, {"lat": 95, "lon": 1}, {"lat": True, "lon": 1}]
        for p in bad_payloads:
            r = self.client.post("/api/nearby", json=p)
            self.assertEqual(r.status_code, 400, f"Expected 400 for payload: {p}")

    @patch(
        "app.routes.nearby_places",
        return_value=[{"name": "Gov Hospital", "category": "Hospital or clinic",
                       "distance_m": 250, "url": "https://www.openstreetmap.org/node/10"}],
    )
    def test_nearby_route_success(self, _) -> None:
        r = self.client.post("/api/nearby", json={"lat": 16.30, "lon": 80.44})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(len(d["places"]), 1)
        self.assertEqual(d["attribution"], "Data © OpenStreetMap contributors (ODbL)")

    @patch("app.routes.nearby_places", side_effect=OverpassError("Overpass failed"))
    def test_nearby_route_error_returns_502_with_map_url(self, _) -> None:
        r = self.client.post("/api/nearby", json={"lat": 16.304, "lon": 80.444})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(
            r.get_json(),
            {
                "error": "Public OpenStreetMap servers are busy right now. You can open this area on the map instead.",
                "map_url": "https://www.openstreetmap.org/#map=15/16.3/80.44",
            },
        )

    @patch("app.routes.nearby_places", return_value=[])
    def test_nearby_route_rounds_coordinates(self, mock_nearby) -> None:
        r = self.client.post("/api/nearby", json={"lat": 16.30491, "lon": 80.45523})
        self.assertEqual(r.status_code, 200)
        mock_nearby.assert_called_once_with(16.30, 80.46)

    @patch("app.nearby.requests.post")
    def test_nearby_cache_avoids_duplicate_upstream_call(self, mock_post) -> None:
        mock_post.return_value = FakeResp({
            "elements": [
                {"type": "node", "id": 1, "lat": 16.301, "lon": 80.441,
                 "tags": {"name": "Test Clinic", "amenity": "clinic"}}
            ]
        })

        res1 = nearby_places(16.30, 80.44)
        self.assertEqual(len(res1), 1)
        self.assertEqual(mock_post.call_count, 1)

        res2 = nearby_places(16.30, 80.44)
        self.assertEqual(len(res2), 1)
        self.assertEqual(mock_post.call_count, 1)

    def test_nearby_rate_limit_returns_friendly_message(self) -> None:
        nearby._last_request_time = time.time()
        r = self.client.post("/api/nearby", json={"lat": 16.99, "lon": 80.99})
        self.assertEqual(r.status_code, 429)
        self.assertIn("wait a moment", r.get_json().get("error", "").lower())

    @patch("app.nearby.requests.post")
    def test_mirror_fallback_main_fails_mirror_succeeds(self, mock_post) -> None:
        mirror_resp = FakeResp({
            "elements": [
                {"type": "node", "id": 55, "lat": 16.302, "lon": 80.442,
                 "tags": {"name": "Mirror Clinic", "amenity": "clinic"}}
            ]
        })
        mock_post.side_effect = [requests.Timeout("Main server timeout"), mirror_resp]
        places = nearby_places(16.30, 80.44)
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["name"], "Mirror Clinic")
        self.assertEqual(mock_post.call_count, 2)

    @patch("app.nearby.requests.post")
    def test_all_servers_fail_returns_502_with_map_url(self, mock_post) -> None:
        mock_post.side_effect = requests.Timeout("All servers down")
        r = self.client.post("/api/nearby", json={"lat": 16.304, "lon": 80.444})
        self.assertEqual(r.status_code, 502)
        d = r.get_json()
        self.assertEqual(
            d["error"],
            "Public OpenStreetMap servers are busy right now. You can open this area on the map instead.",
        )
        self.assertEqual(d["map_url"], "https://www.openstreetmap.org/#map=15/16.3/80.44")

    @patch.dict("os.environ", {"NEARBY_DAILY_CAP": "2"})
    @patch("app.nearby.requests.post")
    def test_daily_cap_returns_429(self, mock_post) -> None:
        mock_post.return_value = FakeResp({"elements": []})

        current_t = [1000.0]
        with patch("app.nearby.time.time", side_effect=lambda: current_t[0]):
            r1 = self.client.post("/api/nearby", json={"lat": 16.31, "lon": 80.41})
            self.assertEqual(r1.status_code, 200)
            current_t[0] = 1005.0
            r2 = self.client.post("/api/nearby", json={"lat": 16.32, "lon": 80.42})
            self.assertEqual(r2.status_code, 200)
            current_t[0] = 1010.0
            r3 = self.client.post("/api/nearby", json={"lat": 16.33, "lon": 80.43})
            self.assertEqual(r3.status_code, 429)
            self.assertEqual(r3.get_json(), {"error": "Daily limit for nearby places reached."})

    @patch.dict("os.environ", {"NEARBY_DAILY_CAP": "1"})
    @patch("app.nearby.requests.post")
    def test_daily_cap_resets_after_midnight_utc(self, mock_post) -> None:
        mock_post.return_value = FakeResp({"elements": []})

        current_t = [867600.0]
        with patch("app.nearby.time.time", side_effect=lambda: current_t[0]):
            r1 = self.client.post("/api/nearby", json={"lat": 16.31, "lon": 80.41})
            self.assertEqual(r1.status_code, 200)
            current_t[0] = 867605.0
            r2 = self.client.post("/api/nearby", json={"lat": 16.32, "lon": 80.42})
            self.assertEqual(r2.status_code, 429)
            self.assertEqual(r2.get_json(), {"error": "Daily limit for nearby places reached."})
            current_t[0] = 950460.0
            r3 = self.client.post("/api/nearby", json={"lat": 16.33, "lon": 80.43})
            self.assertEqual(r3.status_code, 200)

    def test_slow_first_server_then_success_on_second(self) -> None:
        now = [1000.0]
        mirror_resp = FakeResp({
            "elements": [
                {"type": "node", "id": 88, "lat": 16.301, "lon": 80.441,
                 "tags": {"name": "Second Server Clinic", "amenity": "clinic"}}
            ]
        })

        def slow_then_fast(*_args, **_kwargs):
            if now[0] == 1000.0:
                now[0] += 14.0
                raise requests.Timeout("First server slow timeout")
            return mirror_resp

        with patch("app.nearby.time.time", side_effect=lambda: now[0]), \
             patch("app.nearby.requests.post", side_effect=slow_then_fast) as mock_post:
            places = nearby_places(16.30, 80.44)
            self.assertEqual(len(places), 1)
            self.assertEqual(places[0]["name"], "Second Server Clinic")
            self.assertFalse(places.stale)
            self.assertEqual(mock_post.call_count, 2)

    def test_overall_deadline_stops_loop(self) -> None:
        now = [1000.0]

        def exceed_deadline(*_args, **_kwargs):
            now[0] += 35.0
            raise requests.Timeout("Slow fail beyond deadline")

        with patch("app.nearby.time.time", side_effect=lambda: now[0]), \
             patch("app.nearby.requests.post", side_effect=exceed_deadline) as mock_post:
            r = self.client.post("/api/nearby", json={"lat": 16.30, "lon": 80.44})
            self.assertEqual(r.status_code, 502)
            self.assertEqual(mock_post.call_count, 1)

    def test_stale_result_served_when_all_servers_fail_with_stale_flag(self) -> None:
        now = [1000.0]
        ok_resp = FakeResp({
            "elements": [
                {"type": "node", "id": 99, "lat": 16.301, "lon": 80.441,
                 "tags": {"name": "Cached Hospital", "amenity": "hospital"}}
            ]
        })
        with patch("app.nearby.time.time", side_effect=lambda: now[0]), \
             patch("app.nearby.requests.post", return_value=ok_resp):
            r1 = self.client.post("/api/nearby", json={"lat": 16.30, "lon": 80.44})
            self.assertEqual(r1.status_code, 200)
            self.assertNotIn("stale", r1.get_json())

        now[0] = 1900.0
        with patch("app.nearby.time.time", side_effect=lambda: now[0]), \
             patch("app.nearby.requests.post", side_effect=requests.Timeout("All busy")):
            r2 = self.client.post("/api/nearby", json={"lat": 16.30, "lon": 80.44})
            self.assertEqual(r2.status_code, 200)
            data = r2.get_json()
            self.assertTrue(data["stale"])
            self.assertEqual(data["places"][0]["name"], "Cached Hospital")

    def test_empty_results_not_stored_in_fresh_or_stale_cache(self) -> None:
        now = [1000.0]
        empty_resp = FakeResp({"elements": []})

        with patch("app.nearby.time.time", side_effect=lambda: now[0]), \
             patch("app.nearby.requests.post", return_value=empty_resp):
            r1 = self.client.post("/api/nearby", json={"lat": 16.30, "lon": 80.44})
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r1.get_json()["places"], [])
            self.assertEqual(len(nearby._cache), 0)
            self.assertEqual(len(nearby._stale_cache), 0)

        now[0] = 1005.0
        with patch("app.nearby.time.time", side_effect=lambda: now[0]), \
             patch("app.nearby.requests.post", side_effect=requests.Timeout("Down")):
            r2 = self.client.post("/api/nearby", json={"lat": 16.30, "lon": 80.44})
            self.assertEqual(r2.status_code, 502)

    def test_parse_skips_non_dict_tags(self) -> None:
        elements = [
            {"type": "node", "id": 1, "lat": 16.301, "lon": 80.441, "tags": ["bad"]},
            {"type": "node", "id": 2, "lat": 16.301, "lon": 80.441,
             "tags": {"name": "Good Clinic", "amenity": "clinic"}},
        ]
        places = parse_overpass_elements(elements, 16.30, 80.44)
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["name"], "Good Clinic")

    def test_parse_skips_invalid_type_or_id(self) -> None:
        elements = [
            {"type": "node", "id": None, "lat": 16.301, "lon": 80.441,
             "tags": {"name": "No ID Clinic", "amenity": "clinic"}},
            {"type": "node", "id": True, "lat": 16.301, "lon": 80.441,
             "tags": {"name": "Bool ID Clinic", "amenity": "clinic"}},
            {"type": "evil/path", "id": 10, "center": {"lat": 16.301, "lon": 80.441},
             "tags": {"name": "Bad Type Clinic", "amenity": "clinic"}},
            {"type": "node", "id": 42, "lat": 16.301, "lon": 80.441,
             "tags": {"name": "Valid Clinic", "amenity": "clinic"}},
        ]
        places = parse_overpass_elements(elements, 16.30, 80.44)
        self.assertEqual([p["name"] for p in places], ["Valid Clinic"])
        self.assertEqual(places[0]["url"], "https://www.openstreetmap.org/node/42")


if __name__ == "__main__":
    unittest.main()
