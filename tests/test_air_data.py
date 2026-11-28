"""Tests for place search, Nominatim throttling, reverse geocoding, UTC timestamps, and plan reading metadata."""
import threading
import unittest
from unittest.mock import patch

import requests

from app import air_data
from app.air_data import Reading
from tests.helpers import ApiTestCase, FakeResp


def _reset_air_data() -> None:
    """Reset shared air_data caches and Nominatim timestamp."""
    air_data._cache.clear()
    air_data._names.clear()
    air_data._last_nominatim = 0.0


class _AirDataApiTestCase(ApiTestCase):
    """ApiTestCase subclass that isolates air_data cache state per test."""

    def setUp(self) -> None:
        """Reset air_data caches and Nominatim state before and after each test."""
        super().setUp()
        _reset_air_data()
        self.addCleanup(_reset_air_data)


class PlaceSearchTests(_AirDataApiTestCase):
    """Tests for /api/places, /api/locate, search caching, and Nominatim rate limiting."""

    def test_search_places_parses_results(self) -> None:
        data = {"results": [
            {"name": "Guntur", "admin1": "Andhra Pradesh", "country": "India", "latitude": 16.3, "longitude": 80.45},
            {"name": "bad"},
        ]}
        with patch("app.air_data.requests.get", return_value=FakeResp(data)):
            out = air_data.search_places("Guntur")
        self.assertEqual(out, [{"label": "Guntur, Andhra Pradesh, India", "lat": 16.3, "lon": 80.45}])

    @patch("app.routes.search_places", return_value=[{"label": "Guntur, India", "lat": 16.3, "lon": 80.4}])
    def test_places_route(self, _) -> None:
        r = self.client.get("/api/places?q=Gun")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"][0]["label"], "Guntur, India")
        bad_r = self.client.get("/api/places?q=%3Cb%3E")
        self.assertEqual(bad_r.status_code, 200)
        self.assertEqual(bad_r.get_json(), {"results": []})

    def test_locate_route_requires_coordinates(self) -> None:
        r = self.client.get("/api/locate")
        self.assertEqual(r.status_code, 400)

    def test_locate_route_with_coordinates(self) -> None:
        with patch("app.routes.place_name", return_value="Guntur, India"):
            r = self.client.get("/api/locate?lat=16.3049&lon=80.4552")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["city"], "Guntur")
            self.assertEqual(r.get_json()["place"], "Guntur, India")

    def test_geolocation_fetch_reading_coords_guntur(self) -> None:
        with patch("app.air_data.requests.get", return_value=FakeResp({
            "current": {"us_aqi": 160, "pm2_5": 55.3, "pm10": 57.9}
        })):
            reading = air_data.fetch_reading_coords(16.3067, 80.4365, label="Guntur, India")
            self.assertEqual(reading.place, "Guntur, India")
            self.assertEqual(reading.aqi, 160.0)
            self.assertAlmostEqual(reading.pm25, 55.3)

    def test_search_places_pincode_fallback(self) -> None:
        nominatim_data = [{
            "address": {"postcode": "522001", "city": "Guntur", "state": "Andhra Pradesh", "country": "India"},
            "lat": "16.2995", "lon": "80.4508",
        }]
        with patch("app.air_data.requests.get", side_effect=[FakeResp(nominatim_data), FakeResp({"results": []})]):
            out = air_data.search_places("522001", is_explicit=True)
        self.assertEqual(len(out), 1)
        self.assertIn("522001", out[0]["label"])
        self.assertAlmostEqual(out[0]["lat"], 16.2995)

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    @patch("app.ai.fetch_reading_coords", return_value=Reading("Guntur, Andhra Pradesh, India", 140, 50, 90))
    def test_plan_uses_picked_place(self, _) -> None:
        r = self.client.post("/api/plan", json={"lat": 16.3, "lon": 80.45, "place": "Guntur, Andhra Pradesh, India"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["place"], "Guntur, Andhra Pradesh, India")

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    @patch("app.ai.fetch_reading_coords", return_value=Reading("Guntur, Andhra Pradesh, India", 160, 55.3, 57.9))
    def test_plan_with_guntur_geolocation_coords(self, _) -> None:
        r = self.client.post("/api/plan", json={"lat": 16.3067, "lon": 80.4365})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["place"], "Guntur, Andhra Pradesh, India")
        self.assertEqual(r.get_json()["aqi"], 160)

    def test_label_overrides_name_lookup(self) -> None:
        with patch("app.air_data._air", return_value=Reading("", 90, 1, 2)) as air, \
             patch("app.air_data.place_name") as name:
            out = air_data.fetch_reading_coords(16.3, 80.45, label="Guntur, India")
        self.assertEqual(out.place, "Guntur, India")
        name.assert_not_called()
        air.assert_called_once()

    def test_nominatim_rate_limit_throttle(self) -> None:
        data = [{"address": {"postcode": "522001", "country": "India"}, "lat": "16.3", "lon": "80.4"}]
        now = [1000.0]
        with patch("app.air_data.time.time", side_effect=lambda: now[0]):
            with patch("app.air_data.requests.get", return_value=FakeResp(data)) as mock1:
                res1 = air_data.search_places("522001", is_explicit=True)
                self.assertEqual(len(res1), 1)
                self.assertEqual(mock1.call_count, 1)
                self.assertIn("nominatim", mock1.call_args.args[0])
            now[0] = 1000.5
            with patch("app.air_data.requests.get", return_value=FakeResp({"results": []})) as mock2:
                res2 = air_data.search_places("522002", is_explicit=True)
                self.assertEqual(len(res2), 0)
                self.assertEqual(mock2.call_count, 1)
                self.assertNotIn("nominatim", mock2.call_args.args[0])
            now[0] = 1001.1
            with patch("app.air_data.requests.get", return_value=FakeResp(data)) as mock3:
                res3 = air_data.search_places("522003", is_explicit=True)
                self.assertEqual(len(res3), 1)
                self.assertEqual(mock3.call_count, 1)
                self.assertIn("nominatim", mock3.call_args.args[0])

    def test_nominatim_thread_safe_throttle(self) -> None:
        data = [{"address": {"postcode": "522001", "country": "India"}, "lat": "16.3", "lon": "80.4"}]
        results = []
        barrier = threading.Barrier(2)

        def worker(q: str) -> None:
            barrier.wait()
            results.append(len(air_data.search_places(q, is_explicit=True)))

        with patch("app.air_data.time.time", return_value=1000.0), \
             patch("app.air_data.requests.get", return_value=FakeResp(data)) as mock_get:
            ts = [threading.Thread(target=worker, args=(q,)) for q in ("522001", "522002")]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(sorted(results), [0, 1])
        nom_calls = [c for c in mock_get.call_args_list if "nominatim" in c.args[0]]
        self.assertEqual(len(nom_calls), 1)

    def test_empty_search_result_is_not_cached(self) -> None:
        with patch("app.air_data.requests.get", return_value=FakeResp({"results": []})):
            air_data.search_places("UnknownXYZPlace99")
        self.assertNotIn("s:0:unknownxyzplace99", air_data._cache)


class PlaceNameTests(_AirDataApiTestCase):
    """Tests for reverse geocoding, cache bounds, timestamp parsing, and reading metadata."""

    def test_reverse_geocode_names_the_place(self) -> None:
        with patch("app.air_data.requests.get", return_value=FakeResp({"city": "Hyderabad", "countryName": "India"})):
            self.assertEqual(air_data.place_name(17.38, 78.49), "Hyderabad, India")

    def test_reverse_geocode_names_guntur(self) -> None:
        with patch("app.air_data.requests.get", return_value=FakeResp({"city": "Guntur", "countryName": "India"})):
            self.assertEqual(air_data.place_name(16.31, 80.44), "Guntur, India")

    def test_air_data_passes_timeout_to_requests(self) -> None:
        with patch("app.air_data.requests.get", side_effect=[
            FakeResp({"results": [{"name": "Delhi", "country": "India", "latitude": 28.6, "longitude": 77.2}]}),
            FakeResp({"current": {"us_aqi": 190, "pm2_5": 70.0, "pm10": 110.0}}),
        ]) as mock_get:
            reading = air_data.fetch_reading("Delhi")
        self.assertEqual(reading.aqi, 190.0)
        self.assertEqual(mock_get.call_count, 2)
        for call in mock_get.call_args_list:
            self.assertEqual(call.kwargs["timeout"], air_data.TIMEOUT)

    def test_reverse_geocode_failure_falls_back(self) -> None:
        with patch("app.air_data.requests.get", side_effect=requests.Timeout()):
            self.assertEqual(air_data.place_name(17.38, 78.49), "Your location")

    def test_locate_endpoint_out_of_bounds_returns_400(self) -> None:
        r = self.client.get("/api/locate?lat=95.0&lon=80.0")
        self.assertEqual(r.status_code, 400)

    def test_cache_is_bounded(self) -> None:
        cache: dict[str, str] = {}
        for i in range(air_data.MAX_ENTRIES + 10):
            air_data._store(cache, f"key_{i}", f"val_{i}")
        self.assertLessEqual(len(cache), air_data.MAX_ENTRIES)

    def test_cache_evicts_oldest_without_clearing_warm_entries(self) -> None:
        cache: dict[str, str] = {}
        for i in range(air_data.MAX_ENTRIES + 1):
            air_data._store(cache, f"key_{i}", f"val_{i}")
        self.assertEqual(len(cache), air_data.MAX_ENTRIES)
        self.assertNotIn("key_0", cache)
        self.assertIn("key_1", cache)
        self.assertIn(f"key_{air_data.MAX_ENTRIES}", cache)

    def test_names_cache_ttl_and_bound(self) -> None:
        now = [1000.0]
        resp = FakeResp({"city": "Guntur", "countryName": "India"})
        with patch("app.air_data.time.time", side_effect=lambda: now[0]), \
             patch("app.air_data.requests.get", return_value=resp) as mock_get:
            self.assertEqual(air_data.place_name(16.31, 80.44), "Guntur, India")
            self.assertEqual(air_data.place_name(16.31, 80.44), "Guntur, India")
            self.assertEqual(mock_get.call_count, 1)

            now[0] = 1000.0 + air_data.TTL + 1.0
            self.assertEqual(air_data.place_name(16.31, 80.44), "Guntur, India")
            self.assertEqual(mock_get.call_count, 2)

        air_data._names.clear()
        for i in range(air_data.MAX_ENTRIES + 5):
            air_data._store(air_data._names, (16.0, float(i)), (now[0], f"Place {i}"))
        self.assertLessEqual(len(air_data._names), air_data.MAX_ENTRIES)

    def test_observed_at_parsed_to_utc_and_pm_rounded(self) -> None:
        now = [1000.0]
        with patch("app.air_data.time.time", side_effect=lambda: now[0]), \
             patch("app.air_data.requests.get", side_effect=[
                 FakeResp({"results": [{"name": "Delhi", "country": "India", "latitude": 28.6, "longitude": 77.2}]}),
                 FakeResp({"current": {"time": "2026-11-25T18:00", "us_aqi": 180, "pm2_5": 12.34, "pm10": 40.16}}),
             ]) as mock_get:
            r1 = air_data.fetch_reading("Delhi")
            now[0] = 1120.0
            r2 = air_data.fetch_reading("Delhi")
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(r1.observed_at, "2026-11-25T18:00:00Z")
        self.assertEqual(r2.observed_at, "2026-11-25T18:00:00Z")
        self.assertEqual(r1.pm25, 12.3)
        self.assertEqual(r1.pm10, 40.2)

        with patch("app.air_data.requests.get", return_value=FakeResp({
            "current": {"time": "2026-11-25T23:30:00+05:30", "us_aqi": 100, "pm2_5": 5, "pm10": 10}
        })):
            r3 = air_data._air(28.6, 77.2, "Delhi")
        self.assertEqual(r3.observed_at, "2026-11-25T18:00:00Z")
        self.assertEqual(r3.pm25, 5.0)

    def test_invalid_time_and_non_numeric_pm_give_none(self) -> None:
        for bad_time in (None, "", "not-a-time", "2026-11-25", 12345):
            with patch("app.air_data.requests.get", return_value=FakeResp({
                "current": {"time": bad_time, "us_aqi": 90, "pm2_5": "bad", "pm10": True}
            })):
                reading = air_data._air(16.3, 80.4, "Guntur")
            self.assertIsNone(reading.observed_at, f"Expected None for {bad_time!r}")
            self.assertIsNone(reading.pm25)
            self.assertIsNone(reading.pm10)

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    @patch("app.ai.fetch_reading", return_value=Reading("Delhi, India", 210, 55.3, 88.1, "2026-11-25T18:00:00Z"))
    def test_plan_returns_reading_meta_for_city_manual_and_image(self, _) -> None:
        r_city = self.client.post("/api/plan", json={"city": "Delhi"})
        self.assertEqual(r_city.status_code, 200)
        d_city = r_city.get_json()
        self.assertEqual(d_city["source"], "Open-Meteo")
        self.assertEqual(d_city["observed_at"], "2026-11-25T18:00:00Z")
        self.assertEqual(d_city["pm2_5"], 55.3)
        self.assertEqual(d_city["pm10"], 88.1)

        r_manual = self.client.post("/api/plan", json={"aqi": 150, "city": "Delhi"})
        self.assertEqual(r_manual.status_code, 200)
        d_manual = r_manual.get_json()
        self.assertEqual(d_manual["source"], "Entered by you")
        self.assertIsNone(d_manual["observed_at"])
        self.assertIsNone(d_manual["pm2_5"])
        self.assertIsNone(d_manual["pm10"])

        r_img = self.client.post("/api/plan", json={"aqi": 150, "aqi_source": "image"})
        self.assertEqual(r_img.status_code, 200)
        d_img = r_img.get_json()
        self.assertEqual(d_img["source"], "Read from your screenshot")
        self.assertIsNone(d_img["observed_at"])
        self.assertIsNone(d_img["pm2_5"])
        self.assertIsNone(d_img["pm10"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_malformed_open_meteo_payload_returns_502(self) -> None:
        with patch("app.air_data.requests.get", return_value=FakeResp({"results": [None]})):
            with self.assertRaises(air_data.AirDataError):
                air_data.fetch_reading("Delhi")
            r = self.client.post("/api/plan", json={"city": "Delhi"})
        self.assertEqual(r.status_code, 502)

        with patch("app.air_data.requests.get", return_value=FakeResp({"current": "bad"})), \
             self.assertRaises(air_data.AirDataError):
            air_data.fetch_reading_coords(16.3, 80.4, label="Guntur")


if __name__ == "__main__":
    unittest.main()
