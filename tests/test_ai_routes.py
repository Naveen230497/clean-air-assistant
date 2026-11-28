"""Tests for AI-backed Flask routes (/api/image-aqi, /api/advisory, /api/chat, and plan metadata privacy)."""
import base64
import json
import unittest
from unittest.mock import patch

from app import ai
from app.air_data import Reading
from app.gemini import GeminiError
from tests.helpers import PNG, ApiTestCase, make_gemini_resp


class AiRouteTests(ApiTestCase):
    """Integration tests for AI HTTP routes, key gating, size caps, and error responses."""

    def setUp(self) -> None:
        """Enable a synthetic test API key for route tests."""
        super().setUp()
        patcher = patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("app.gemini.generate")
    def test_image_reading(self, gen) -> None:
        gen.return_value = make_gemini_resp(json.dumps({
            "aqi": 412, "image_kind": "aqi_screenshot", "visibility": "n/a", "note": "read",
        }))
        r = self.client.post("/api/image-aqi", json={"image": PNG, "mime": "image/png"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["aqi"], 412)

    def test_image_validation(self) -> None:
        bad = [
            {"image": PNG, "mime": "image/gif"},
            {"image": "!!!", "mime": "image/png"},
            {"image": base64.b64encode(b"notpng").decode(), "mime": "image/png"},
        ]
        for b in bad:
            self.assertEqual(self.client.post("/api/image-aqi", json=b).status_code, 400)

    def test_image_aqi_route_errors_and_limits(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            r_503 = self.client.post("/api/image-aqi", json={"image": PNG, "mime": "image/png"})
        self.assertEqual(r_503.status_code, 503)
        self.assertEqual(r_503.get_json(), {"error": "This AI feature needs a Gemini API key on the server."})

        with patch("app.gemini.generate", side_effect=GeminiError("fail")):
            r_502 = self.client.post("/api/image-aqi", json={"image": PNG, "mime": "image/png"})
        self.assertEqual(r_502.status_code, 502)
        self.assertEqual(r_502.get_json(), {"error": "Could not read that image."})

        err_429 = GeminiError("limit", status_code=429, error_status="RESOURCE_EXHAUSTED")
        with patch("app.gemini.generate", side_effect=err_429):
            r_429 = self.client.post("/api/image-aqi", json={"image": PNG, "mime": "image/png"})
        self.assertEqual(r_429.status_code, 502)
        self.assertEqual(
            r_429.get_json(),
            {"error": "AI features are temporarily unavailable. The rule-based plan is still shown."},
        )

        r_413 = self.client.post("/api/image-aqi", json={"image": "A" * (5 * 1024 * 1024 + 64), "mime": "image/png"})
        self.assertEqual(r_413.status_code, 413)
        self.assertEqual(r_413.get_json(), {"error": "Request too large"})

        bad_sig = {"image": base64.b64encode(b"notpng").decode(), "mime": "image/png"}
        r_400 = self.client.post("/api/image-aqi", json=bad_sig)
        self.assertEqual(r_400.status_code, 400)
        self.assertEqual(r_400.get_json(), {"error": "Image content does not match its type"})

    @patch("app.gemini.generate")
    def test_screenshot_aqi_flow_sets_source_and_null_observed_at(self, gen) -> None:
        gen.side_effect = [
            make_gemini_resp(json.dumps({
                "aqi": 310, "image_kind": "aqi_screenshot", "visibility": "n/a", "note": "ok",
            })),
            make_gemini_resp(json.dumps({
                "headline": "Very unhealthy", "summary": "Stay in.", "top_three": ["N95"], "myth_buster": "m",
            })),
        ]
        r_img = self.client.post("/api/image-aqi", json={"image": PNG, "mime": "image/png"})
        self.assertEqual(r_img.status_code, 200)
        aqi = r_img.get_json()["aqi"]
        r_plan = self.client.post("/api/plan", json={"aqi": aqi, "aqi_source": "image"})
        self.assertEqual(r_plan.status_code, 200)
        body = r_plan.get_json()
        self.assertEqual(body["source"], "Read from your screenshot")
        self.assertIsNone(body["observed_at"])

    @patch("app.gemini.generate", return_value=make_gemini_resp("Yes, with a mask."))
    def test_chat(self, gen) -> None:
        body = {
            "question": "Can I jog?", "aqi": 250, "place": "Delhi", "lang": "en",
            "history": [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}],
        }
        r = self.client.post("/api/chat", json=body)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["answer"], "Yes, with a mask.")
        self.assertIn("250", gen.call_args.kwargs["system"])

    @patch("app.gemini.generate", return_value=make_gemini_resp("Yes, with a mask."))
    def test_chat_returns_200_with_coordinate_place_format(self, _) -> None:
        body = {"question": "Can I jog?", "history": [], "aqi": 110, "place": "Lat 16.30, Lon 80.45", "lang": "en"}
        r = self.client.post("/api/chat", json=body)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["answer"], "Yes, with a mask.")

    def test_chat_validation(self) -> None:
        base = {"question": "ok", "aqi": 100, "place": "Delhi"}
        for patch_ in (
            {"question": ""}, {"question": "x" * 501}, {"aqi": 800},
            {"history": [{"role": "system", "text": "x"}]}, {"history": [{}] * 7},
        ):
            r = self.client.post("/api/chat", json={**base, **patch_})
            self.assertEqual(r.status_code, 400, patch_)

    def test_ai_endpoints_need_key(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            self.assertEqual(self.client.post("/api/chat", json={"question": "hi", "aqi": 50}).status_code, 503)
            self.assertEqual(self.client.post("/api/advisory", json={"city": "Delhi"}).status_code, 503)

    def test_oversized_json_rejected(self) -> None:
        r = self.client.post("/api/chat", json={"question": "x", "aqi": 1, "pad": "z" * 9000})
        self.assertEqual(r.status_code, 413)

    def test_routes_429_returns_exact_friendly_message(self) -> None:
        err = GeminiError("Rate limited", status_code=429, error_status="RESOURCE_EXHAUSTED")
        with patch("app.gemini.generate", side_effect=err):
            r = self.client.post("/api/chat", json={"question": "Can I jog?", "aqi": 150, "place": "Delhi"})
            self.assertEqual(r.status_code, 502)
            self.assertEqual(
                r.get_json(),
                {"error": "AI features are temporarily unavailable. The rule-based plan is still shown."},
            )

    def test_advisory_route_success_error_and_429(self) -> None:
        meta = {"groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://cpcb.nic.in/", "title": "CPCB"}}]}}
        with patch("app.gemini.generate", return_value=make_gemini_resp("GRAP stage 2 active.", extra=meta)):
            r_ok = self.client.post("/api/advisory", json={"city": "Delhi", "lang": "en"})
        self.assertEqual(r_ok.status_code, 200)
        self.assertEqual(r_ok.get_json()["text"], "GRAP stage 2 active.")
        self.assertEqual(r_ok.get_json()["sources"], [{"title": "CPCB", "url": "https://cpcb.nic.in/"}])

        with patch("app.gemini.generate", side_effect=GeminiError("boom")):
            r_err = self.client.post("/api/advisory", json={"city": "Delhi", "lang": "en"})
        self.assertEqual(r_err.status_code, 502)
        self.assertEqual(r_err.get_json(), {"error": "Could not fetch advisories right now."})

        err_429 = GeminiError("Rate limited", status_code=429, error_status="RESOURCE_EXHAUSTED")
        with patch("app.gemini.generate", side_effect=err_429):
            r_429 = self.client.post("/api/advisory", json={"city": "Delhi", "lang": "en"})
        self.assertEqual(r_429.status_code, 502)
        self.assertEqual(
            r_429.get_json(),
            {"error": "AI features are temporarily unavailable. The rule-based plan is still shown."},
        )

    @patch("app.ai.fetch_reading", return_value=Reading("Delhi, India", 210, 55.3, 88.1, "2026-11-25T18:00:00Z"))
    @patch("app.gemini.generate")
    def test_plan_gemini_prompt_excludes_observed_at_and_pm(self, gen, _) -> None:
        gen.side_effect = [
            make_gemini_resp(parts=[{"functionCall": {"name": "get_air_quality", "args": {"city": "Delhi"}}}]),
            make_gemini_resp(json.dumps({
                "headline": "Unhealthy", "summary": "Mask up.", "top_three": ["N95"], "myth_buster": "m",
            })),
        ]
        r = self.client.post("/api/plan", json={"city": "Delhi", "lang": "en"})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["observed_at"], "2026-11-25T18:00:00Z")
        self.assertEqual(d["source"], "Open-Meteo")
        briefing_prompt = gen.call_args_list[1].args[0][0]["parts"][0]["text"]
        for omitted in ("2026-11-25", "18:00:00", "55.3", "88.1", "Open-Meteo"):
            self.assertNotIn(omitted, briefing_prompt)

    @patch("app.gemini.generate")
    def test_image_non_dict_and_bad_json_raise_gemini_error(self, gen) -> None:
        gen.return_value = make_gemini_resp("[1, 2]")
        with self.assertRaises(GeminiError):
            ai.read_image(PNG, "image/png")
        r = self.client.post("/api/image-aqi", json={"image": PNG, "mime": "image/png"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.get_json(), {"error": "Could not read that image."})

        gen.return_value = make_gemini_resp("{not-json")
        with self.assertRaises(GeminiError):
            ai.read_image(PNG, "image/png")


if __name__ == "__main__":
    unittest.main()
