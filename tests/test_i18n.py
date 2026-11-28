"""Tests for backend 6-language message catalogs, fallbacks, rules, briefings, and routes."""
import re
import unittest
from unittest.mock import patch

from app import ai
from app.gemini import GeminiError
from app.i18n import band_label, t
from app.locales import LANG_PACKS
from app.nearby import OverpassError
from app.recommender import Profile, build_plan
from app.shared import LANGS
from tests.helpers import ApiTestCase, NoNetworkTestCase, make_gemini_resp

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


class CatalogTests(NoNetworkTestCase):
    """Verify catalog completeness, placeholder parity, and safe English fallbacks."""

    def test_all_six_languages_cover_all_keys_without_english_copies(self) -> None:
        self.assertEqual(set(LANG_PACKS), set(LANGS))
        en_keys = set(LANG_PACKS["en"])
        for lang, pack in LANG_PACKS.items():
            self.assertEqual(set(pack), en_keys, f"Key mismatch in {lang}")
            for key, val in pack.items():
                self.assertTrue(val.strip(), f"Empty string for {lang}.{key}")
                if lang != "en":
                    self.assertNotEqual(val, LANG_PACKS["en"][key], f"Untranslated {lang}.{key}")

    def test_placeholders_match_english_across_all_languages(self) -> None:
        en_pack = LANG_PACKS["en"]
        for key, en_val in en_pack.items():
            expected = sorted(PLACEHOLDER_RE.findall(en_val))
            for lang, pack in LANG_PACKS.items():
                actual = sorted(PLACEHOLDER_RE.findall(pack[key]))
                self.assertEqual(actual, expected, f"Placeholder mismatch in {lang}.{key}")

    def test_t_falls_back_to_english_and_never_returns_raw_key(self) -> None:
        self.assertEqual(t("band.3", "xx"), "Unhealthy")
        self.assertEqual(band_label(4, "xx"), "Very unhealthy")
        self.assertEqual(t("nonexistent.message.key", "te"), "")
        self.assertEqual(t("briefing.headline", "en"), "Air quality: {band}")


class LocalizedPlanTests(ApiTestCase):
    """Verify end-to-end offline localization across rules, template briefings, and routes."""

    def test_build_plan_and_template_briefing_for_all_languages(self) -> None:
        profile = Profile(commute="car", cooking="biomass", respiratory=True, children=True)
        en_plan = build_plan(220, profile, "en").to_dict()
        en_brief = ai.template_briefing(en_plan, "Delhi", "en")

        for lang in LANGS:
            plan = build_plan(220, profile, lang).to_dict()
            brief = ai.template_briefing(plan, "Delhi", lang)
            self.assertEqual(plan["level"], en_plan["level"])
            self.assertEqual(plan["est_reduction_pct"], en_plan["est_reduction_pct"])
            self.assertEqual([a["category"] for a in plan["actions"]], [a["category"] for a in en_plan["actions"]])
            self.assertTrue(plan["safety_note"])
            self.assertTrue(brief["headline"])
            self.assertTrue(brief["summary"])
            if lang != "en":
                self.assertNotEqual(plan["band"], en_plan["band"])
                self.assertNotEqual(plan["safety_note"], en_plan["safety_note"])
                self.assertNotEqual(brief["headline"], en_brief["headline"])
                self.assertNotEqual(brief["summary"], en_brief["summary"])
                self.assertNotEqual(brief["myth_buster"], en_brief["myth_buster"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_api_plan_localized_and_english_contract_stable(self) -> None:
        r_en = self.client.post("/api/plan", json={"aqi": 180, "commute": "car", "children": True, "lang": "en"})
        r_default = self.client.post("/api/plan", json={"aqi": 180, "commute": "car", "children": True})
        self.assertEqual(r_en.status_code, 200)
        self.assertEqual(r_default.status_code, 200)
        self.assertEqual(r_en.get_data(as_text=True), r_default.get_data(as_text=True))
        en_body = r_en.get_json()

        for lang in ("hi", "te", "ta", "bn", "mr"):
            res = self.client.post("/api/plan", json={"aqi": 180, "commute": "car", "children": True, "lang": lang})
            self.assertEqual(res.status_code, 200)
            body = res.get_json()
            self.assertEqual(body["lang"], lang)
            self.assertEqual(body["est_reduction_pct"], en_body["est_reduction_pct"])
            self.assertNotEqual(body["band"], en_body["band"])
            self.assertNotEqual(body["actions"][0]["title"], en_body["actions"][0]["title"])
            self.assertNotEqual(body["source"], en_body["source"])

        bad = self.client.post("/api/plan", json={"aqi": 180, "lang": "xx"})
        self.assertEqual(bad.status_code, 400)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_localized_route_fallbacks_and_prompt_language_guard(self) -> None:
        with patch("app.gemini.generate", side_effect=GeminiError("down")):
            r_adv = self.client.post("/api/advisory", json={"city": "Guntur", "lang": "te"})
        self.assertEqual(r_adv.status_code, 502)
        self.assertEqual(r_adv.get_json()["error"], t("err.advisory", "te"))

        err_429 = GeminiError("limit", status_code=429, error_status="RESOURCE_EXHAUSTED")
        with patch("app.gemini.generate", side_effect=err_429):
            r_chat = self.client.post("/api/chat", json={"question": "Mask?", "aqi": 200, "lang": "hi"})
        self.assertEqual(r_chat.status_code, 502)
        self.assertEqual(r_chat.get_json()["error"], t("err.rate_limit_ai", "hi"))

        with patch("app.routes.nearby_places", side_effect=OverpassError("busy")):
            r_near = self.client.post("/api/nearby", json={"lat": 16.3, "lon": 80.4, "lang": "mr"})
        self.assertEqual(r_near.status_code, 502)
        self.assertEqual(r_near.get_json()["error"], t("err.nearby_busy", "mr"))

        with patch("app.gemini.generate", return_value=make_gemini_resp("Ok.")) as gen:
            ai.local_advisory("Delhi", "xx")
            self.assertIn("In English:", gen.call_args[0][0][0]["parts"][0]["text"])

    def test_sentence_punctuation_and_sensitive_wording_consistent(self) -> None:
        sentence_keys = [
            key for key in LANG_PACKS["en"]
            if key.endswith((".why", ".impact", "safety.respiratory", "briefing.summary", "briefing.myth"))
            or key.startswith("err.")
        ]
        expected_end = {"en": ".", "hi": "।", "te": ".", "ta": ".", "bn": "।", "mr": "."}
        for lang, end in expected_end.items():
            for key in sentence_keys:
                text = LANG_PACKS[lang][key]
                self.assertTrue(text.endswith(end), f"{lang}.{key} ended with {text[-1]!r}")
                if end == "।":
                    self.assertNotIn(". ", text, f"Stray period in {lang}.{key}")
                else:
                    self.assertNotIn("।", text, f"Stray danda in {lang}.{key}")

        te_titles = " ".join(a.title for a in build_plan(180, Profile(children=True), "te").actions)
        bn_titles = " ".join(a.title for a in build_plan(180, Profile(children=True), "bn").actions)
        mr_titles = " ".join(a.title for a in build_plan(180, Profile(children=True), "mr").actions)
        self.assertIn("పిల్లల కోసం", te_titles)
        self.assertIn("শিশুদের", bn_titles)
        self.assertNotIn("-দের", bn_titles)
        self.assertIn("मुलांसाठी", mr_titles)
        self.assertNotIn("मुले यांच्यासाठी", mr_titles)

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_non_english_summaries_never_leak_your_location(self) -> None:
        r_en = self.client.post("/api/plan", json={"aqi": 180, "lang": "en"}).get_json()
        self.assertEqual(r_en["place"], "your location")
        self.assertIn("your location", r_en["briefing"]["summary"])

        for lang in ("hi", "te", "ta", "bn", "mr"):
            body = self.client.post("/api/plan", json={"aqi": 180, "lang": lang}).get_json()
            self.assertEqual(body["place"], t("place.default", lang))
            self.assertNotIn("your location", body["place"].lower())
            self.assertNotIn("your location", body["briefing"]["summary"].lower())

        with patch("app.routes.place_name", return_value="Your location"):
            for lang in ("hi", "te", "ta", "bn", "mr"):
                geo = self.client.post(
                    "/api/plan", json={"lat": 17.4, "lon": 78.4, "aqi": 180, "lang": lang}
                ).get_json()
                self.assertEqual(geo["place"], t("place.default", lang))
                self.assertNotIn("your location", geo["briefing"]["summary"].lower())

    def test_nearby_route_localizes_categories_keeping_place_names(self) -> None:
        sample = [
            {"name": "Apollo Hospital", "category": "Hospital or clinic", "distance_m": 250,
             "url": "https://www.openstreetmap.org/node/1"},
            {"name": "MedPlus", "category": "Pharmacy", "distance_m": 400,
             "url": "https://www.openstreetmap.org/node/2"},
            {"name": "Central Library", "category": "Library", "distance_m": 900,
             "url": "https://www.openstreetmap.org/node/3"},
            {"name": "City Mall", "category": "Mall", "distance_m": 1500,
             "url": "https://www.openstreetmap.org/node/4"},
        ]
        cat_keys = ("nearby.hospital", "nearby.pharmacy", "nearby.library", "nearby.mall")
        with patch("app.routes.nearby_places", return_value=sample):
            r_en = self.client.post("/api/nearby", json={"lat": 16.3, "lon": 80.4, "lang": "en"}).get_json()
            r_def = self.client.post("/api/nearby", json={"lat": 16.3, "lon": 80.4}).get_json()
            self.assertEqual(r_en, r_def)
            self.assertEqual([p["category"] for p in r_en["places"]], [t(k, "en") for k in cat_keys])

            for lang in ("hi", "te", "ta", "bn", "mr"):
                res = self.client.post("/api/nearby", json={"lat": 16.3, "lon": 80.4, "lang": lang}).get_json()
                self.assertEqual([p["name"] for p in res["places"]], [p["name"] for p in sample])
                self.assertEqual([p["category"] for p in res["places"]], [t(k, lang) for k in cat_keys])
        self.assertEqual(sample[0]["category"], "Hospital or clinic")


if __name__ == "__main__":
    unittest.main()
