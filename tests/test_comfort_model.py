#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import unittest

from photoloset import comfort_model


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture():
    return {
        "schema": comfort_model.SCHEMA,
        "calibration_digest": _sha("material-calibration"),
        "provenance": {
            "source": "sim run 12", "method": "contact/environment sensors",
            "revision": "1",
            "lineage": [{"source": "solver output", "digest": _sha("solver-12")}],
        },
        "observations": [
            {"pressure_pa": 1200.0, "contact_time_s": 60.0,
             "air_velocity_m_s": 0.10, "temperature_k": 296.0,
             "relative_humidity": 0.55},
            {"pressure_pa": 1800.0, "contact_time_s": 120.0,
             "air_velocity_m_s": 0.20, "temperature_k": 298.0,
             "relative_humidity": 0.65},
        ],
    }


class ComfortModelTests(unittest.TestCase):
    def test_returns_review_ranges_without_medical_claim(self):
        source = fixture(); before = copy.deepcopy(source)
        got = comfort_model.evaluate(source)
        self.assertEqual(got["verdict"], comfort_model.REVIEW)
        self.assertEqual(source, before)
        self.assertEqual(got["ranges"]["pressure"]["minimum"], 1200.0)
        self.assertEqual(got["ranges"]["pressure"]["maximum"], 1800.0)
        self.assertFalse(got["medical_safety_claim"])
        self.assertTrue(got["assumptions"]["proxy_is_not_a_clinical_threshold"])
        self.assertEqual(len(got["evaluation_digest"]), 64)

    def test_evaluation_is_deterministic_and_calibration_bound(self):
        first = comfort_model.evaluate(fixture())
        self.assertEqual(first, comfort_model.evaluate(fixture()))
        changed = fixture(); changed["calibration_digest"] = _sha("other")
        self.assertNotEqual(first["evaluation_digest"],
                            comfort_model.evaluate(changed)["evaluation_digest"])

    def test_refuses_missing_observations(self):
        source = fixture(); del source["observations"][0]["relative_humidity"]
        got = comfort_model.evaluate(source)
        self.assertEqual(got["verdict"], comfort_model.MISSING_OBSERVATION)
        self.assertIn("relative_humidity", got["missing"])

    def test_requires_calibration_digest_and_lineage(self):
        source = fixture(); source["calibration_digest"] = "not-a-digest"
        self.assertEqual(comfort_model.evaluate(source)["verdict"],
                         comfort_model.MISSING_CALIBRATION)
        source = fixture(); source["provenance"]["lineage"] = []
        self.assertEqual(comfort_model.evaluate(source)["verdict"],
                         comfort_model.MISSING_PROVENANCE)

    def test_capabilities_never_promise_pass_or_safety(self):
        got = comfort_model.capabilities()
        self.assertEqual(got["possible_success_verdicts"], ["REVIEW"])
        self.assertFalse(got["medical_safety_claim"])
        self.assertIn("calibration_digest", got["required_binding"])


if __name__ == "__main__":
    unittest.main()
