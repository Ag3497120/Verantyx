#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import unittest

from photoloset import material_calibration as calibration


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture():
    linear = lambda xs, slope, x, y: [{x: v, y: slope * v} for v in xs]
    return {
        "schema": calibration.SCHEMA,
        "material_id": "measured-roll-7",
        "provenance": {
            "source": "lab run 7", "method": "declared fixture", "revision": "1",
            "lineage": [{"source": "instrument export", "digest": _sha("raw-7")}],
        },
        "measurements": {
            "tension": {
                "warp": linear([0.01, 0.02, 0.03], 200.0,
                               "strain", "force_per_width_n_m"),
                "weft": linear([0.01, 0.02, 0.03], 100.0,
                               "strain", "force_per_width_n_m"),
            },
            "shear": linear([0.01, 0.02, 0.03], 50.0,
                            "shear_strain", "force_per_width_n_m"),
            "bending": {
                "warp": linear([1.0, 2.0], 0.002, "curvature_1_m", "moment_n"),
                "weft": linear([1.0, 2.0], 0.001, "curvature_1_m", "moment_n"),
            },
            "friction": [
                {"normal_force_n": 10.0, "static_force_n": 5.0,
                 "dynamic_force_n": 4.0},
                {"normal_force_n": 20.0, "static_force_n": 10.0,
                 "dynamic_force_n": 8.0},
            ],
            "damping": [
                {"cycle_index": 0, "amplitude": 1.0},
                {"cycle_index": 1, "amplitude": 0.8},
                {"cycle_index": 2, "amplitude": 0.64},
            ],
            "permeability": [
                {"pressure_difference_pa": 100.0, "flow_velocity_m_s": 0.01,
                 "thickness_m": 0.001, "dynamic_viscosity_pa_s": 1.8e-5},
                {"pressure_difference_pa": 200.0, "flow_velocity_m_s": 0.02,
                 "thickness_m": 0.001, "dynamic_viscosity_pa_s": 1.8e-5},
            ],
        },
    }


class MaterialCalibrationTests(unittest.TestCase):
    def test_fits_si_coefficients_and_digest_deterministically(self):
        source = fixture(); before = copy.deepcopy(source)
        first = calibration.calibrate(source)
        second = calibration.calibrate(source)
        self.assertEqual(first, second)
        self.assertEqual(source, before)
        self.assertEqual(first["verdict"], calibration.ANSWER)
        self.assertAlmostEqual(first["coefficients"]["tension_modulus_n_m"]
                               ["warp"]["value"], 200.0)
        self.assertAlmostEqual(first["coefficients"]["friction_coefficient"]
                               ["dynamic"]["value"], 0.4)
        self.assertAlmostEqual(first["coefficients"]["permeability_m2"]
                               ["value"], 1.8e-12)
        self.assertEqual(len(first["calibration_digest"]), 64)
        changed = fixture()
        changed["measurements"]["tension"]["warp"][0]["force_per_width_n_m"] += 1
        self.assertNotEqual(first["calibration_digest"],
                            calibration.calibrate(changed)["calibration_digest"])

    def test_refuses_every_unobserved_channel_and_direction(self):
        source = fixture(); del source["measurements"]["permeability"]
        got = calibration.calibrate(source)
        self.assertEqual(got["verdict"], calibration.MISSING_OBSERVATION)
        self.assertIn("permeability", got["missing"])
        source = fixture(); del source["measurements"]["tension"]["weft"]
        self.assertEqual(calibration.calibrate(source)["verdict"],
                         calibration.MISSING_OBSERVATION)

    def test_refuses_missing_lineage_and_insufficient_series(self):
        source = fixture(); source["provenance"]["lineage"] = []
        self.assertEqual(calibration.calibrate(source)["verdict"],
                         calibration.MISSING_PROVENANCE)
        source = fixture(); source["measurements"]["shear"] = source["measurements"]["shear"][:1]
        self.assertEqual(calibration.calibrate(source)["verdict"],
                         calibration.INSUFFICIENT_SERIES)

    def test_invalid_physics_is_not_silently_fitted(self):
        source = fixture()
        source["measurements"]["friction"][0]["dynamic_force_n"] = 6.0
        self.assertEqual(calibration.calibrate(source)["verdict"],
                         calibration.BAD_RECORD)

    def test_capabilities_are_explicit(self):
        got = calibration.capabilities()
        self.assertFalse(got["fills_unobserved_channels"])
        self.assertIn("permeability", got["required_channels"])
        self.assertTrue(got["standard_library_only"])


if __name__ == "__main__":
    unittest.main()
