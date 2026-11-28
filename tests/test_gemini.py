"""Tests for Gemini client, thinkingConfig, circuit breaker, fallback model, and briefing/function calling."""
import json
import unittest
from unittest.mock import patch

from app import ai, gemini
from app.air_data import AirDataError, Reading
from app.gemini import GeminiError
from app.recommender import Profile, build_plan
from tests.helpers import PNG, ApiTestCase, FakeResp, make_gemini_resp


class GeminiCoreTests(ApiTestCase):
    """Tests for Gemini REST behavior, safety payloads, fallback, breaker, and core AI helpers."""

    def setUp(self) -> None:
        """Enable a synthetic test API key cleanly per test."""
        super().setUp()
        patcher = patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("app.gemini.generate")
    def test_structured_briefing(self, gen) -> None:
        gen.return_value = make_gemini_resp(json.dumps({
            "headline": "Smoggy day", "summary": "Stay in.", "top_three": ["a", "b", "c", "d"], "myth_buster": "m",
        }))
        plan = build_plan(300, Profile()).to_dict()
        out = ai.briefing(plan, "Delhi", "hi")
        self.assertEqual(out["source"], "gemini")
        self.assertEqual(len(out["top_three"]), 3)
        self.assertEqual(gen.call_args.kwargs["schema"], ai.BRIEFING_SCHEMA)

    @patch("app.gemini.generate", side_effect=GeminiError("x"))
    def test_briefing_falls_back(self, _) -> None:
        out = ai.briefing(build_plan(300, Profile()).to_dict(), "Delhi")
        self.assertEqual(out["source"], "rules")

    @patch("app.ai.fetch_reading", return_value=Reading("Delhi, India", 310, 200, 300))
    @patch("app.gemini.generate")
    def test_function_calling_flow(self, gen, fetch) -> None:
        gen.return_value = make_gemini_resp(
            parts=[{"functionCall": {"name": "get_air_quality", "args": {"city": "Delhi"}}}]
        )
        reading, how = ai.agent_reading("Delhi")
        self.assertEqual(how, "gemini_function_call")
        self.assertEqual(reading.aqi, 310)
        fetch.assert_called_once_with("Delhi")
        gen.assert_called_once()

    @patch("app.ai.fetch_reading", return_value=Reading("Delhi, India", 310, 200, 300))
    @patch("app.gemini.generate")
    def test_function_call_rejects_unsafe_model_args(self, gen, fetch) -> None:
        gen.return_value = make_gemini_resp(
            parts=[{"functionCall": {"name": "get_air_quality", "args": {"city": "x;DROP"}}}]
        )
        reading, how = ai.agent_reading("Delhi")
        self.assertEqual(how, "gemini_function_call")
        self.assertEqual(reading.aqi, 310)
        fetch.assert_called_once_with("Delhi")
        gen.assert_called_once()

    @patch("app.gemini.generate")
    def test_grounded_advisory_sources(self, gen) -> None:
        meta = {"groundingMetadata": {"groundingChunks": [
            {"web": {"uri": "https://example.gov/a", "title": "Gov"}},
            {"web": {"uri": "javascript:alert(1)", "title": "Bad"}},
        ]}}
        gen.return_value = make_gemini_resp("GRAP stage 3 active.", extra=meta)
        out = ai.local_advisory("Delhi")
        self.assertEqual(out["sources"], [{"title": "Gov", "url": "https://example.gov/a"}])
        self.assertEqual(gen.call_args.kwargs["tools"], [{"google_search": {}}])

    @patch("app.gemini.generate")
    def test_local_advisory_prompt_forbids_aqi_numbers(self, gen) -> None:
        gen.return_value = make_gemini_resp("No official restrictions found.")
        ai.local_advisory("Guntur", "en")
        prompt = gen.call_args[0][0][0]["parts"][0]["text"]
        self.assertIn("Do not state any AQI number or health category", prompt)

    @patch("app.gemini.generate")
    def test_image_out_of_range_ignored(self, gen) -> None:
        gen.return_value = make_gemini_resp(json.dumps({
            "aqi": 9999, "image_kind": "other", "visibility": "", "note": "",
        }))
        self.assertIsNone(ai.read_image(PNG, "image/png")["aqi"])

    def test_thinking_config_model_aware(self) -> None:
        self.assertEqual(gemini._thinking_config("gemini-2.5-flash"), {"thinkingBudget": 0})
        self.assertEqual(gemini._thinking_config("gemini-2.5-flash-lite"), {"thinkingBudget": 0})
        self.assertIsNone(gemini._thinking_config("gemini-3.5-flash-lite"))
        self.assertIsNone(gemini._thinking_config("gemini-3.8-flash"))

        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-3.5-flash-lite", "GEMINI_FALLBACK_MODEL": ""}), \
             patch("app.gemini.requests.post", return_value=FakeResp(make_gemini_resp("OK"))) as mock_post:
            gemini.generate([{"role": "user", "parts": [{"text": "Say OK"}]}])
            sent_cfg = mock_post.call_args.kwargs["json"]["generationConfig"]
            self.assertNotIn("thinkingConfig", sent_cfg)

    def test_circuit_breaker_skips_gemini_for_60s(self) -> None:
        plan = build_plan(200, Profile()).to_dict()
        now = [1000.0]
        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-2.5-flash", "GEMINI_FALLBACK_MODEL": ""}), \
             patch("app.gemini.time.time", side_effect=lambda: now[0]), \
             patch("app.gemini.requests.post", side_effect=[
                 FakeResp({"error": {"status": "RESOURCE_EXHAUSTED"}}, status_code=429),
                 FakeResp(make_gemini_resp(json.dumps({
                     "headline": "Recovered", "summary": "Ok.", "top_three": ["a"], "myth_buster": "m",
                 }))),
             ]) as mock_post:
            out1 = ai.briefing(plan, "Delhi", "en")
            self.assertEqual(out1["source"], "rules")
            self.assertEqual(mock_post.call_count, 1)

            now[0] = 1030.0
            out2 = ai.briefing(plan, "Delhi", "hi")
            self.assertEqual(out2["source"], "rules")
            self.assertEqual(mock_post.call_count, 1)

            now[0] = 1061.0
            out3 = ai.briefing(plan, "Delhi", "hi")
            self.assertEqual(out3["source"], "gemini")
            self.assertEqual(mock_post.call_count, 2)

    @patch("app.ai.fetch_reading", return_value=Reading("Delhi, India", 210, 100, 150))
    @patch("app.gemini.generate")
    def test_breaker_open_skips_gemini_in_agent_reading(self, gen, fetch) -> None:
        now = [1000.0]
        gemini._breaker_until = 1060.0
        with patch("app.gemini.time.time", side_effect=lambda: now[0]):
            reading, how = ai.agent_reading("Delhi")
            self.assertEqual(how, "direct")
            self.assertEqual(reading.aqi, 210)
            gen.assert_not_called()
            fetch.assert_called_once_with("Delhi")

    @patch("app.gemini.generate")
    def test_briefing_cache_hit_ttl_and_max_bound(self, gen) -> None:
        gen.return_value = make_gemini_resp(json.dumps({
            "headline": "Smoggy", "summary": "Use N95.", "top_three": ["a", "b"], "myth_buster": "m",
        }))
        plan = build_plan(220, Profile()).to_dict()
        now = [5000.0]
        with patch("app.ai.time.time", side_effect=lambda: now[0]):
            out1 = ai.briefing(plan, "Delhi", "en")
            out2 = ai.briefing(plan, "  delhi  ", "en")
            self.assertEqual(out1["headline"], "Smoggy")
            self.assertEqual(out2["headline"], "Smoggy")
            self.assertEqual(gen.call_count, 1)

            ai.briefing(plan, "Guntur", "en")
            self.assertEqual(gen.call_count, 2)

            ai.briefing(plan, "Delhi", "hi")
            self.assertEqual(gen.call_count, 3)

            now[0] = 5601.0
            ai.briefing(plan, "Delhi", "en")
            self.assertEqual(gen.call_count, 4)

        ai._briefing_cache.clear()
        for i in range(ai.BRIEFING_CACHE_MAX):
            ai._store_briefing(("city", i, "Good", "en", "h"), out1)
        self.assertEqual(len(ai._briefing_cache), ai.BRIEFING_CACHE_MAX)
        ai._store_briefing(("city", "overflow", "Good", "en", "h"), out1)
        self.assertLessEqual(len(ai._briefing_cache), ai.BRIEFING_CACHE_MAX)

    def test_fallback_model_used_on_429_for_chat(self) -> None:
        env = {"GEMINI_MODEL": "gemini-2.5-flash", "GEMINI_FALLBACK_MODEL": "gemini-3.5-flash-lite"}
        with patch.dict("os.environ", env), \
             patch("app.gemini.requests.post", side_effect=[
                 FakeResp({"error": {"status": "RESOURCE_EXHAUSTED"}}, status_code=429),
                 FakeResp(make_gemini_resp("Mask up today.")),
             ]) as mock_post:
            ans = ai.chat("Safe to jog?", [], 180, "Delhi", "en")
            self.assertEqual(ans, "Mask up today.")
            self.assertEqual(mock_post.call_count, 2)
            self.assertIn("gemini-2.5-flash", mock_post.call_args_list[0].args[0])
            self.assertIn("thinkingConfig", mock_post.call_args_list[0].kwargs["json"]["generationConfig"])
            self.assertIn("gemini-3.5-flash-lite", mock_post.call_args_list[1].args[0])
            self.assertNotIn("thinkingConfig", mock_post.call_args_list[1].kwargs["json"]["generationConfig"])
            self.assertFalse(gemini.breaker_open())

    def test_fallback_model_not_used_for_advisory(self) -> None:
        env = {"GEMINI_MODEL": "gemini-2.5-flash", "GEMINI_FALLBACK_MODEL": "gemini-3.5-flash-lite"}
        err_resp = FakeResp({"error": {"status": "RESOURCE_EXHAUSTED"}}, status_code=429)
        with patch.dict("os.environ", env), \
             patch("app.gemini.requests.post", return_value=err_resp) as mock_post:
            with self.assertRaises(GeminiError) as ctx:
                ai.local_advisory("Delhi", "en")
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertEqual(mock_post.call_count, 1)

    def test_fallback_model_not_used_when_empty(self) -> None:
        env = {"GEMINI_MODEL": "gemini-2.5-flash", "GEMINI_FALLBACK_MODEL": ""}
        err_resp = FakeResp({"error": {"status": "RESOURCE_EXHAUSTED"}}, status_code=429)
        with patch.dict("os.environ", env), \
             patch("app.gemini.requests.post", return_value=err_resp) as mock_post:
            with self.assertRaises(GeminiError) as ctx:
                ai.chat("Safe to jog?", [], 180, "Delhi", "en")
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertEqual(mock_post.call_count, 1)

    def test_gemini_payload_includes_safety_and_system_instruction(self) -> None:
        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-2.5-flash", "GEMINI_FALLBACK_MODEL": ""}), \
             patch("app.gemini.requests.post", return_value=FakeResp(make_gemini_resp("OK"))) as mock_post:
            gemini.generate([{"role": "user", "parts": [{"text": "Hi"}]}], system="Stay safe.")
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "Stay safe."}]})
        self.assertEqual(
            body["safetySettings"],
            [{"category": c, "threshold": "BLOCK_MEDIUM_AND_ABOVE"} for c in gemini.HARM],
        )

    @patch("app.gemini.generate")
    def test_briefing_handles_null_top_three_and_non_dict_json(self, gen) -> None:
        self.assertIsNone(ai._parse_briefing_json(make_gemini_resp("[1, 2]")))
        gen.return_value = make_gemini_resp(json.dumps({
            "headline": "High smog", "summary": "Mask outdoors.", "top_three": None, "myth_buster": "m",
        }))
        out = ai.briefing(build_plan(220, Profile()).to_dict(), "Delhi", "en")
        self.assertEqual(out["source"], "gemini")
        self.assertEqual(out["top_three"], [])

    def test_agent_reading_requires_city_or_coords(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}), self.assertRaises(AirDataError):
            ai.agent_reading(None, coords=None)


if __name__ == "__main__":
    unittest.main()
