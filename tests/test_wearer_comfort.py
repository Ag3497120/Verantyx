#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import unittest

from photoloset import wearer_comfort


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _trial(name: str, pressure: float):
    return {
        "trial_id": name,
        "activity": {"activity_type": "walking",
                     "metabolic_rate_w_m2": 120.0, "duration_s": 600.0},
        "environment": {"air_temperature_k": 296.0,
                        "radiant_temperature_k": 296.0,
                        "relative_humidity": 0.55,
                        "air_velocity_m_s": 0.20},
        "contact_observations": [
            {"region": "waist", "pressure_pa": pressure,
             "contact_time_s": 600.0, "skin_temperature_k": 306.0,
             "microclimate_temperature_k": 303.0,
             "microclimate_relative_humidity": 0.65,
             "heat_flux_w_m2": 40.0},
            {"region": "hip", "pressure_pa": pressure * 0.8,
             "contact_time_s": 600.0, "skin_temperature_k": 306.0,
             "microclimate_temperature_k": 302.0,
             "microclimate_relative_humidity": 0.60,
             "heat_flux_w_m2": 35.0},
        ],
    }


def fixture():
    return {
        "schema": wearer_comfort.SCHEMA,
        "wearer_id": "wearer-consented-7",
        "material_calibration_digest": _sha("material-7"),
        "anthropometry": {"stature_m": 1.70, "mass_kg": 65.0,
                          "chest_circumference_m": 0.90,
                          "waist_circumference_m": 0.72,
                          "hip_circumference_m": 0.94},
        "provenance": {
            "source": "wear trial 7", "method": "instrumented comparison",
            "revision": "1",
            "lineage": [{"source": "sensor export", "digest": _sha("trial-7")}],
        },
        "trials": [_trial("fit-a", 1800.0), _trial("fit-b", 1200.0)],
    }


class WearerComfortTests(unittest.TestCase):
    def test_returns_person_bound_review_only(self):
        source = fixture(); before = copy.deepcopy(source)
        got = wearer_comfort.evaluate(source)
        self.assertEqual(got["verdict"], wearer_comfort.REVIEW)
        self.assertEqual(source, before)
        self.assertFalse(got["medical_safety_claim"])
        self.assertFalse(got["population_generalization"])
        self.assertTrue(got["comparison_controls_match"])
        self.assertEqual(len(got["comparisons"]), 1)
        self.assertEqual(len(got["evaluation_digest"]), 64)

    def test_is_deterministic_and_material_bound(self):
        first = wearer_comfort.evaluate(fixture())
        self.assertEqual(first, wearer_comfort.evaluate(fixture()))
        changed = fixture(); changed["material_calibration_digest"] = _sha("other")
        self.assertNotEqual(first["evaluation_digest"],
                            wearer_comfort.evaluate(changed)["evaluation_digest"])

    def test_refuses_missing_anthropometry_and_contact_observation(self):
        source = fixture(); del source["anthropometry"]["waist_circumference_m"]
        self.assertEqual(wearer_comfort.evaluate(source)["verdict"],
                         wearer_comfort.MISSING_OBSERVATION)
        source = fixture()
        del source["trials"][0]["contact_observations"][0]["heat_flux_w_m2"]
        self.assertEqual(wearer_comfort.evaluate(source)["verdict"],
                         wearer_comfort.MISSING_OBSERVATION)

    def test_requires_two_trials_calibration_and_lineage(self):
        source = fixture(); source["trials"] = source["trials"][:1]
        self.assertEqual(wearer_comfort.evaluate(source)["verdict"],
                         wearer_comfort.INSUFFICIENT_COMPARISON)
        source = fixture(); source["material_calibration_digest"] = "bad"
        self.assertEqual(wearer_comfort.evaluate(source)["verdict"],
                         wearer_comfort.MISSING_CALIBRATION)
        source = fixture(); source["provenance"]["lineage"] = []
        self.assertEqual(wearer_comfort.evaluate(source)["verdict"],
                         wearer_comfort.MISSING_PROVENANCE)

    def test_capabilities_never_claim_safety_or_population_result(self):
        got = wearer_comfort.capabilities()
        self.assertEqual(got["possible_success_verdicts"], ["REVIEW"])
        self.assertFalse(got["medical_safety_claim"])
        self.assertFalse(got["population_generalization"])


if __name__ == "__main__":
    unittest.main()
