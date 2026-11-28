"""Tests for AQI band classification and deterministic action recommender."""
import unittest

from app.aqi import classify
from app.recommender import Profile, build_plan
from tests.helpers import NoNetworkTestCase


class AqiTests(NoNetworkTestCase):
    """Tests for US AQI band boundaries and out-of-range errors."""

    def test_bands(self) -> None:
        self.assertEqual(classify(0).label, "Good")
        self.assertEqual(classify(50).level, 0)
        self.assertEqual(classify(51).level, 1)
        self.assertEqual(classify(320).label, "Hazardous")

    def test_out_of_range(self) -> None:
        for bad in (-1, 501):
            with self.assertRaises(ValueError):
                classify(bad)

    def test_aqi_band_boundaries(self) -> None:
        self.assertEqual(classify(0).label, "Good")
        self.assertEqual(classify(50).label, "Good")
        self.assertEqual(classify(51).label, "Moderate")
        self.assertEqual(classify(100).label, "Moderate")
        self.assertEqual(classify(101).label, "Unhealthy for sensitive groups")
        self.assertEqual(classify(150).label, "Unhealthy for sensitive groups")
        self.assertEqual(classify(151).label, "Unhealthy")
        self.assertEqual(classify(200).label, "Unhealthy")
        self.assertEqual(classify(201).label, "Very unhealthy")
        self.assertEqual(classify(300).label, "Very unhealthy")
        self.assertEqual(classify(301).label, "Hazardous")
        self.assertEqual(classify(500).label, "Hazardous")


class RecommenderTests(NoNetworkTestCase):
    """Tests for deterministic household action selection and safety notes."""

    def test_good_air_is_light(self) -> None:
        plan = build_plan(30, Profile())
        self.assertLess(plan.est_reduction_pct, 10)
        self.assertFalse(any(a.category == "alternative" for a in plan.actions))

    def test_severe_smog_has_mask_and_indoor_actions(self) -> None:
        plan = build_plan(380, Profile(commute="car", children=True))
        titles = " ".join(a.title for a in plan.actions)
        self.assertIn("N95", titles)
        self.assertIn("Corsi-Rosenthal", titles)
        self.assertIn("Carpool", titles)
        self.assertGreater(plan.est_reduction_pct, 40)
        self.assertLessEqual(plan.est_reduction_pct, 85)

    def test_purifier_changes_advice(self) -> None:
        a = " ".join(x.title for x in build_plan(250, Profile(has_purifier=True)).actions)
        self.assertIn("purifier", a)
        self.assertNotIn("Corsi", a)

    def test_respiratory_note_only_when_relevant(self) -> None:
        note = build_plan(200, Profile(respiratory=True)).safety_note
        self.assertIn("doctor", note)
        self.assertIn("not medical advice", note)
        self.assertEqual(build_plan(40, Profile(respiratory=True)).safety_note, "")

    def test_biomass_cooking_alternative(self) -> None:
        plan = build_plan(180, Profile(cooking="biomass"))
        self.assertTrue(any("LPG" in a.title for a in plan.actions))


if __name__ == "__main__":
    unittest.main()
