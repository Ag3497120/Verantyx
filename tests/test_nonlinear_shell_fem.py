# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset.nonlinear_shell_fem import (
    ANSWER,
    INVALID_REQUEST,
    NONCONVERGENCE,
    capabilities,
    solve,
)


REST = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0), (0.0, 1.0, 0.0))
FACES = ((0, 1, 2), (0, 2, 3))
MATERIAL = {
    "calibration": {"status": "CALIBRATED", "id": "shell-coupon-a"},
    "thickness_m": 0.001,
    "young_warp_pa": 2.0e5,
    "young_weft_pa": 1.0e5,
    "shear_pa": 5.0e4,
    "poisson_warp_weft": 0.2,
    "bending_stiffness_n_m": 0.02,
    "plasticity": {
        "yield_strain": 0.2,
        "hardening_pa": 1.0e4,
        "max_plastic_strain": 0.5,
        "hysteresis_ratio": 0.1,
        "bending_yield_rad": 0.5,
        "max_plastic_bending_rad": 1.0,
    },
}


def request(force=0.0, **solver_overrides):
    solver_options = {
        "max_iterations": 120,
        "absolute_residual_tolerance_n": 1.0e-6,
        "relative_residual_tolerance": 1.0e-8,
        "relaxation": 0.8,
        "line_search_reductions": 18,
    }
    solver_options.update(solver_overrides)
    return {
        "rest_positions": REST,
        "faces": FACES,
        "face_material_ids": ("cloth", "cloth"),
        "materials": {"cloth": copy.deepcopy(MATERIAL)},
        "time_step_s": 1.0/60.0,
        "loads": {
            "nodal_forces_n": ((0.0, 0.0, 0.0), (force, 0.0, 0.0),
                                (force, 0.0, 0.0), (0.0, 0.0, 0.0)),
            "increments": 2,
        },
        "boundary_conditions": {"fixed_vertices": (0, 3)},
        "solver": solver_options,
    }


class NonlinearShellFEMTests(unittest.TestCase):
    def test_capabilities_do_not_claim_consistent_tangent_or_certification(self):
        report = capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["features"]["global_static_equilibrium"])
        self.assertTrue(report["features"]["load_increments"])
        self.assertFalse(report["features"]["consistent_tangent_matrix"])
        self.assertFalse(report["features"]["industrial_certification"])

    def test_zero_load_converges_without_moving_fixed_boundary(self):
        result = solve(request())
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["terminal_verdict"], "CONVERGED")
        self.assertEqual(result["positions_m"], [list(row) for row in REST])
        self.assertEqual(len(result["increment_summaries"]), 2)
        self.assertTrue(all(item["iterations"] == 0
                            for item in result["increment_summaries"]))

    def test_force_load_moves_free_vertices_and_preserves_fixed_vertices(self):
        result = solve(request(1.0))
        self.assertEqual(result["verdict"], ANSWER, result)
        self.assertEqual(result["positions_m"][0], list(REST[0]))
        self.assertEqual(result["positions_m"][3], list(REST[3]))
        self.assertGreater(result["positions_m"][1][0], REST[1][0])
        self.assertGreater(result["positions_m"][2][0], REST[2][0])
        self.assertLessEqual(result["diagnostics"]["final_residual_l2_n"], 2.0e-6)
        self.assertEqual(result["tangent"],
                         "FINITE_DIFFERENCE_RESIDUAL_REGULARIZED_BY_JACOBI_NOT_ANALYTIC_CONSISTENT")

    def test_load_increments_and_line_search_are_recorded(self):
        result = solve(request(1.0))
        self.assertEqual(result["verdict"], ANSWER, result)
        factors = [item["load_factor"] for item in result["increment_summaries"]]
        self.assertEqual(factors, [0.5, 1.0])
        self.assertTrue(any(item["status"] == "STEP_ACCEPTED"
                            for item in result["convergence_history"]))
        self.assertTrue(all("line_search_scale" in item
                            for item in result["convergence_history"]))

    def test_request_is_immutable_and_result_is_deterministic(self):
        first_request = request(0.5)
        snapshot = copy.deepcopy(first_request)
        first = solve(first_request)
        second = solve(first_request)
        self.assertEqual(first_request, snapshot)
        self.assertEqual(first, second)

    def test_prescribed_position_is_enforced(self):
        value = request()
        value["boundary_conditions"] = {
            "fixed_vertices": (0,),
            "prescribed_positions_m": {3: (0.0, 1.05, 0.0)},
        }
        result = solve(value)
        self.assertEqual(result["verdict"], ANSWER, result)
        self.assertEqual(result["positions_m"][3], [0.0, 1.05, 0.0])

    def test_typed_nonconvergence_preserves_committed_history(self):
        value = request(5.0, max_iterations=1,
                        absolute_residual_tolerance_n=1.0e-14,
                        relative_residual_tolerance=0.0)
        result = solve(value)
        self.assertEqual(result["verdict"], NONCONVERGENCE)
        self.assertEqual(result["stage"], "GLOBAL_EQUILIBRIUM")
        self.assertEqual(result["failed_increment"], 1)
        self.assertIn("convergence_history", result)
        self.assertIsNone(result["committed_history"])

    def test_constitutive_refusal_is_propagated_with_stage(self):
        value = request()
        value["materials"]["cloth"]["calibration"]["status"] = "ESTIMATED"
        result = solve(value)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_CROSS_SHELL_UNCALIBRATED_MATERIAL")
        self.assertEqual(result["stage"], "CONSTITUTIVE_EVALUATION")

    def test_invalid_requests_are_typed(self):
        self.assertEqual(solve({})["verdict"], INVALID_REQUEST)
        value = request()
        value["boundary_conditions"] = {"fixed_vertices": (0, 1, 2, 3)}
        self.assertEqual(solve(value)["verdict"], INVALID_REQUEST)
        value = request()
        value["solver"]["line_search_contraction"] = 1.0
        self.assertEqual(solve(value)["verdict"], INVALID_REQUEST)


if __name__ == "__main__":
    unittest.main()
