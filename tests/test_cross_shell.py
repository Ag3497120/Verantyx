# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset.cross_shell import (
    ANSWER,
    ILL_CONDITIONED,
    INVERTED,
    INVALID_INPUT,
    UNCALIBRATED,
    capabilities,
    solve,
)


REST = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0), (0.0, 1.0, 0.0))
FACES = ((0, 1, 2), (0, 2, 3))
MATERIAL = {
    "calibration": {"status": "CALIBRATED", "id": "coupon-2026-08"},
    "thickness_m": 0.001,
    "young_warp_pa": 2.0e6,
    "young_weft_pa": 4.0e5,
    "shear_pa": 1.0e5,
    "poisson_warp_weft": 0.2,
    "bending_stiffness_n_m": 0.02,
    "plasticity": {
        "yield_strain": 0.03,
        "hardening_pa": 1.0e5,
        "max_plastic_strain": 0.25,
        "hysteresis_ratio": 0.15,
        "bending_yield_rad": 0.1,
        "max_plastic_bending_rad": 0.8,
    },
}


def run(old=REST, **overrides):
    options = dict(face_material_ids=("cloth", "cloth"),
                   materials={"cloth": MATERIAL}, time_step_s=1.0/60.0)
    options.update(overrides)
    return solve(REST, old, FACES, **options)


class CrossShellTests(unittest.TestCase):
    def test_capabilities_are_explicit_and_not_fem_complete(self):
        report = capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["features"]["orthotropic_membrane"])
        self.assertTrue(report["features"]["same_old_state_residual"])
        self.assertFalse(report["features"]["global_fem_solve"])
        self.assertFalse(report["features"]["validated_industrial_accuracy"])
        self.assertFalse(report["features"]["consistent_tangent_matrix"])

    def test_rest_state_has_zero_residual_and_immutable_inputs(self):
        rest = [list(v) for v in REST]
        old = [list(v) for v in REST]
        faces = [list(v) for v in FACES]
        material = copy.deepcopy(MATERIAL)
        snapshot = copy.deepcopy((rest, old, faces, material))
        result = solve(rest, old, faces,
                       face_material_ids=("cloth", "cloth"),
                       materials={"cloth": material}, time_step_s=1.0/60.0)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual((rest, old, faces, material), snapshot)
        self.assertLess(max(abs(v) for row in result["residuals_n"] for v in row), 1e-7)
        self.assertEqual(result["assembly"], "SAME_OLD_STATE_JACOBI")

    def test_stretched_membrane_returns_restoring_jacobi_correction(self):
        stretched = ((0.0, 0.0, 0.0), (1.1, 0.0, 0.0),
                     (1.1, 1.0, 0.0), (0.0, 1.0, 0.0))
        result = run(stretched)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertLess(result["residuals_n"][1][0], 0.0)
        self.assertLess(result["jacobi_corrections_m"][1][0], 0.0)
        self.assertGreater(result["diagnostics"]["energy_j"]["membrane"], 0.0)

    def test_anisotropy_changes_residual(self):
        warp_stretch = ((0.0, 0.0, 0.0), (1.1, 0.0, 0.0),
                        (1.1, 1.0, 0.0), (0.0, 1.0, 0.0))
        weft_stretch = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                        (1.0, 1.1, 0.0), (0.0, 1.1, 0.0))
        warp = run(warp_stretch)
        weft = run(weft_stretch)
        warp_force = max(math.dist(row, (0.0, 0.0, 0.0)) for row in warp["residuals_n"])
        weft_force = max(math.dist(row, (0.0, 0.0, 0.0)) for row in weft["residuals_n"])
        self.assertGreater(warp_force, weft_force)

    def test_thickness_scales_membrane_response(self):
        stretched = ((0.0, 0.0, 0.0), (1.05, 0.0, 0.0),
                     (1.05, 1.0, 0.0), (0.0, 1.0, 0.0))
        thin = run(stretched)
        thick_material = copy.deepcopy(MATERIAL)
        thick_material["thickness_m"] *= 2.0
        thick = run(stretched, materials={"cloth": thick_material})
        thin_force = max(abs(v) for row in thin["residuals_n"] for v in row)
        thick_force = max(abs(v) for row in thick["residuals_n"] for v in row)
        self.assertAlmostEqual(thick_force/thin_force, 2.0, places=7)

    def test_history_is_caller_owned_and_affects_constitutive_response(self):
        stretched = ((0.0, 0.0, 0.0), (1.05, 0.0, 0.0),
                     (1.05, 1.0, 0.0), (0.0, 1.0, 0.0))
        history = [{"plastic_strain": [0.02, 0.0, 0.0],
                    "hysteresis_memory": [0.01, 0.0, 0.0]},
                   {"plastic_strain": [0.02, 0.0, 0.0],
                    "hysteresis_memory": [0.01, 0.0, 0.0]}]
        snapshot = copy.deepcopy(history)
        virgin = run(stretched)
        experienced = run(stretched, history=history)
        self.assertEqual(history, snapshot)
        self.assertNotEqual(virgin["residuals_n"], experienced["residuals_n"])
        self.assertEqual(experienced["time_step_s"], 1.0/60.0)
        self.assertFalse(experienced["diagnostics"]["time_integration_performed"])

    def test_discrete_bending_and_plastic_hysteresis_state_are_explicit(self):
        bent = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.4), (0.0, 1.0, -0.2))
        result = run(bent)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["diagnostics"]["interior_hinges"], 1)
        self.assertGreater(result["diagnostics"]["energy_j"]["bending"], 0.0)
        state = result["next_history"]
        self.assertTrue(any(abs(v) > 0.0 for entry in state
                            for v in entry["plastic_strain"]))
        self.assertTrue(any(abs(entry["plastic_bending_rad"]) > 0.0
                            for entry in state))
        self.assertIn("hysteresis_memory", state[0])

    def test_face_order_does_not_change_assembled_vertex_result(self):
        stretched = ((0.0, 0.0, 0.0), (1.05, 0.0, 0.0),
                     (1.05, 1.0, 0.1), (0.0, 1.0, 0.0))
        forward = run(stretched)
        reverse = solve(REST, stretched, tuple(reversed(FACES)),
                        face_material_ids=("cloth", "cloth"),
                        materials={"cloth": MATERIAL}, time_step_s=1.0/60.0)
        self.assertEqual(forward["verdict"], ANSWER)
        self.assertEqual(reverse["verdict"], ANSWER)
        for a, b in zip(forward["residuals_n"], reverse["residuals_n"]):
            for av, bv in zip(a, b):
                self.assertAlmostEqual(av, bv, places=7)

    def test_uncalibrated_material_is_typed_refusal(self):
        material = copy.deepcopy(MATERIAL)
        material["calibration"]["status"] = "ESTIMATED"
        result = run(materials={"cloth": material})
        self.assertEqual(result["verdict"], UNCALIBRATED)

    def test_inverted_element_is_typed_refusal(self):
        inverted = (REST[0], REST[2], REST[1], REST[3])
        result = run(inverted)
        self.assertEqual(result["verdict"], INVERTED)

    def test_ill_conditioned_rest_and_current_elements_are_typed(self):
        bad_rest = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                    (1.0e-10, 1.0e-12, 0.0))
        result = solve(bad_rest, bad_rest, ((0, 1, 2),),
                       face_material_ids=("cloth",),
                       materials={"cloth": MATERIAL}, time_step_s=1.0/60.0)
        self.assertEqual(result["verdict"], ILL_CONDITIONED)
        collapsed = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                     (2.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        self.assertEqual(run(collapsed)["verdict"], ILL_CONDITIONED)

    def test_invalid_topology_and_parameters_are_typed(self):
        bad = solve(REST, REST, ((0, 1, 99),),
                    face_material_ids=("cloth",), materials={"cloth": MATERIAL},
                    time_step_s=1.0/60.0)
        self.assertEqual(bad["verdict"], INVALID_INPUT)
        self.assertEqual(run(time_step_s=0.0)["verdict"], INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
