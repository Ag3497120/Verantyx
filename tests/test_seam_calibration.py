#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import unittest

from photoloset import seam_calibration


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture():
    return {
        "schema": seam_calibration.SCHEMA,
        "seam_id": "lockstitch-7",
        "provenance": {
            "source": "seam lab run 7", "method": "instrument fixture",
            "revision": "1",
            "lineage": [{"source": "raw export", "digest": _sha("raw-7")}],
        },
        "measurements": {
            "tension": [
                {"strain": 0.01, "line_force_n_m": 20.0},
                {"strain": 0.02, "line_force_n_m": 40.0},
            ],
            "slippage": [
                {"opening_m": 0.001, "line_force_n_m": 10.0},
                {"opening_m": 0.002, "line_force_n_m": 20.0},
            ],
            "puckering": [
                {"seam_length_m": 1.0, "excess_path_length_m": 0.01,
                 "rms_height_m": 0.002},
                {"seam_length_m": 2.0, "excess_path_length_m": 0.02,
                 "rms_height_m": 0.002},
            ],
            "fatigue": [
                {"cycle_count": 0, "retained_strength_ratio": 1.0},
                {"cycle_count": 100, "retained_strength_ratio": 0.9},
                {"cycle_count": 200, "retained_strength_ratio": 0.8},
            ],
            "breakage": [
                {"line_force_n_m": 100.0, "cycles_to_failure": 10000},
                {"line_force_n_m": 200.0, "cycles_to_failure": 2500},
                {"line_force_n_m": 400.0, "cycles_to_failure": 625},
            ],
        },
    }


class SeamCalibrationTests(unittest.TestCase):
    def test_calibrates_si_coefficients_uncertainty_and_digest(self):
        source = fixture(); before = copy.deepcopy(source)
        first = seam_calibration.calibrate(source)
        self.assertEqual(first, seam_calibration.calibrate(source))
        self.assertEqual(source, before)
        self.assertEqual(first["verdict"], seam_calibration.ANSWER)
        self.assertAlmostEqual(first["coefficients"]
                               ["line_tensile_stiffness_n_m"]["value"], 2000.0)
        self.assertAlmostEqual(first["coefficients"]
                               ["slippage_stiffness_n_m2"]["value"], 10000.0)
        self.assertAlmostEqual(first["coefficients"]["puckering"]
                               ["excess_length_ratio"]["value"], 0.01)
        self.assertEqual(len(first["calibration_digest"]), 64)
        changed = fixture(); changed["measurements"]["tension"][0]["line_force_n_m"] += 1
        self.assertNotEqual(first["calibration_digest"],
                            seam_calibration.calibrate(changed)["calibration_digest"])

    def test_refuses_missing_and_short_series(self):
        source = fixture(); del source["measurements"]["puckering"]
        got = seam_calibration.calibrate(source)
        self.assertEqual(got["verdict"], seam_calibration.MISSING_OBSERVATION)
        self.assertIn("puckering", got["missing"])
        source = fixture(); source["measurements"]["breakage"] = source["measurements"]["breakage"][:2]
        self.assertEqual(seam_calibration.calibrate(source)["verdict"],
                         seam_calibration.INSUFFICIENT_SERIES)

    def test_refuses_invalid_lineage_and_nonphysical_fatigue(self):
        source = fixture(); source["provenance"]["lineage"] = []
        self.assertEqual(seam_calibration.calibrate(source)["verdict"],
                         seam_calibration.MISSING_PROVENANCE)
        source = fixture()
        source["measurements"]["fatigue"][1]["retained_strength_ratio"] = 1.1
        self.assertEqual(seam_calibration.calibrate(source)["verdict"],
                         seam_calibration.BAD_RECORD)

    def test_capabilities_refuse_imputation(self):
        got = seam_calibration.capabilities()
        self.assertFalse(got["fills_unobserved_channels"])
        self.assertEqual(got["minimum_samples"]["breakage"], 3)
        self.assertTrue(got["standard_library_only"])


if __name__ == "__main__":
    unittest.main()
