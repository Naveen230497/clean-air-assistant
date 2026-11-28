"""Tests for request payload and city-name validation."""
import base64
import unittest

from app.air_data import valid_city
from app.validation import ValidationError, parse_image, parse_request
from tests.helpers import NoNetworkTestCase


class ValidationTests(NoNetworkTestCase):
    """Unit tests for request schema, profile field bounds, and city-name whitelist."""

    def test_valid(self) -> None:
        city, aqi, p, lang, _, _ = parse_request(
            {"city": "Delhi", "commute": "car", "children": True, "lang": "hi"}
        )
        self.assertEqual((city, aqi, p.commute, p.children, lang), ("Delhi", None, "car", True, "hi"))

    def test_rejects_bad_input(self) -> None:
        bad = [None, [], {}, {"aqi": 900}, {"aqi": "x"}, {"city": "<script>"},
               {"aqi": 50, "commute": "rocket"}, {"aqi": 50, "children": "yes"}, {"aqi": 50, "lang": "xx"},
               {"lat": 95, "lon": 10}, {"lat": 10}, {"lat": True, "lon": 1}, {"lat": 1, "lon": 1, "place": "<b>"}]
        for b in bad:
            with self.assertRaises(ValidationError, msg=str(b)):
                parse_request(b)

    def test_rejects_bool_aqi(self) -> None:
        for val in (True, False):
            with self.assertRaises(ValidationError, msg=str(val)):
                parse_request({"aqi": val})

    def test_parse_image_requires_webp_header(self) -> None:
        fake_wav = base64.b64encode(b"RIFF\x00\x00\x00\x00WAVE").decode()
        with self.assertRaises(ValidationError):
            parse_image({"mime": "image/webp", "image": fake_wav})
        valid_webp = base64.b64encode(b"RIFF\x00\x00\x00\x00WEBP").decode()
        _, mime = parse_image({"mime": "image/webp", "image": valid_webp})
        self.assertEqual(mime, "image/webp")

    def test_city_regex(self) -> None:
        self.assertTrue(valid_city("São Paulo"))
        self.assertFalse(valid_city("a;drop table"))

    def test_valid_city_rules(self) -> None:
        self.assertTrue(valid_city("Guntur, Andhra Pradesh"))
        self.assertTrue(valid_city("Lat 16.30, Lon 80.45"))
        self.assertFalse(valid_city("x" * 61))
        self.assertFalse(valid_city("<script>alert(1)</script>"))
        self.assertFalse(valid_city(""))
        self.assertFalse(valid_city(None))


if __name__ == "__main__":
    unittest.main()
