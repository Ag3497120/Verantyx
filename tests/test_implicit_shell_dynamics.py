# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset.implicit_shell_dynamics import (
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
    "calibration": {"status": "CALIBRATED", "id": "dynamic-coupon-a"},
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


def request(force=0.0, steps=3, **solver_overrides):
    solver = {
        "max_iterations": 20,
        "absolute_residual_tolerance_n": 1.0e-8,
        "relative_residual_tolerance": 1.0e-9,
        "line_search_reductions": 12,
    }
    solver.update(solver_overrides)
    return {
        "rest_positions": REST,
        "faces": FACES,
        "face_material_ids": ("cloth", "cloth"),
        "materials": {"cloth": copy.deepcopy(MATERIAL)},
        "nodal_masses_kg": (1.0, 1.0, 1.0, 1.0),
        "time_step_s": 0.02,
        "steps": steps,
        "loads": {
            "nodal_forces_n": ((0.0, 0.0, 0.0), (force, 0.0, 0.0),
                                (force, 0.0, 0.0), (0.0, 0.0, 0.0)),
        },
        "boundary_conditions": {"fixed_vertices": (0, 3)},
        "newmark": {"beta": 0.25, "gamma": 0.5,
                    "mass_damping_per_s": 0.02},
        "solver": solver,
    }


class ImplicitShellDynamicsTests(unittest.TestCase):
    def test_capabilities_are_honest(self):
        report = capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["features"]["implicit_newmark"])
        self.assertTrue(report["features"]["numerical_residual_consistent_tangent"])
        self.assertFalse(report["features"]["analytic_consistent_material_tangent"])
        self.assertFalse(report["features"]["industrial_certification"])
        self.assertFalse(report["features"]["contact_or_ccd"])

    def test_unloaded_rest_state_remains_at_rest(self):
        result = solve(request())
        self.assertEqual(result["verdict"], ANSWER, result)
        self.assertEqual(result["positions_m"], [list(row) for row in REST])
        self.assertTrue(all(value == 0.0 for row in result["velocities_m_s"] for value in row))
        self.assertEqual(len(result["energy_ledger"]), 3)
        self.assertTrue(all(abs(entry["algorithmic_energy_balance_j"]) < 1.0e-20
                            for entry in result["energy_ledger"]))

    def test_implicit_force_response_moves_only_free_vertices(self):
        result = solve(request(10.0))
        self.assertEqual(result["verdict"], ANSWER, result)
        self.assertEqual(result["positions_m"][0], list(REST[0]))
        self.assertEqual(result["positions_m"][3], list(REST[3]))
        self.assertGreater(result["positions_m"][1][0], REST[1][0])
        self.assertGreater(result["positions_m"][2][0], REST[2][0])
        self.assertTrue(all(math.isfinite(value)
                            for row in result["positions_m"] for value in row))

    def test_explicit_load_steps_and_ledgers(self):
        value = request(5.0)
        value["loads"]["load_factors"] = (0.1, 0.4, 1.0)
        result = solve(value)
        self.assertEqual(result["verdict"], ANSWER, result)
        self.assertEqual([entry["load_factor"] for entry in result["energy_ledger"]],
                         [0.1, 0.4, 1.0])
        self.assertEqual(len(result["state_ledger"]), 3)
        self.assertTrue(any(entry["status"] == "STEP_ACCEPTED"
                            for entry in result["residual_ledger"]))
        required = {"kinetic_energy_j", "strain_energy_j",
                    "external_work_cumulative_j", "algorithmic_energy_balance_j",
                    "residual_l2_n"}
        self.assertTrue(all(required <= set(entry) for entry in result["energy_ledger"]))

    def test_initial_velocity_uses_newmark_kinematics(self):
        value = request(steps=1)
        value["initial_velocities_m_s"] = (
            (0.0, 0.0, 0.0), (0.1, 0.0, 0.0),
            (0.1, 0.0, 0.0), (0.0, 0.0, 0.0))
        result = solve(value)
        self.assertEqual(result["verdict"], ANSWER, result)
        self.assertGreater(result["positions_m"][1][0], REST[1][0])
        self.assertEqual(result["diagnostics"]["newmark_beta"], 0.25)
        self.assertEqual(result["diagnostics"]["newmark_gamma"], 0.5)

    def test_request_is_immutable_and_solution_is_deterministic(self):
        value = request(2.0, steps=2)
        snapshot = copy.deepcopy(value)
        first = solve(value)
        second = solve(value)
        self.assertEqual(value, snapshot)
        self.assertEqual(first, second)

    def test_typed_nonconvergence_keeps_committed_state(self):
        value = request(100.0, steps=1, max_iterations=1,
                        absolute_residual_tolerance_n=1.0e-16,
                        relative_residual_tolerance=0.0)
        result = solve(value)
        self.assertEqual(result["verdict"], NONCONVERGENCE)
        self.assertEqual(result["stage"], "IMPLICIT_NEWMARK_NEWTON")
        self.assertEqual(result["failed_step"], 1)
        self.assertIsNone(result["committed_history"])
        self.assertIn("residual_ledger", result)

    def test_cross_shell_refusal_is_propagated(self):
        value = request()
        value["materials"]["cloth"]["calibration"]["status"] = "ESTIMATED"
        result = solve(value)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_CROSS_SHELL_UNCALIBRATED_MATERIAL")
        self.assertEqual(result["stage"], "INITIAL_CONSTITUTIVE_EVALUATION")

    def test_invalid_requests_are_typed(self):
        self.assertEqual(solve({})["verdict"], INVALID_REQUEST)
        value = request()
        value["nodal_masses_kg"] = (1.0, 0.0, 1.0, 1.0)
        self.assertEqual(solve(value)["verdict"], INVALID_REQUEST)
        value = request()
        value["newmark"]["beta"] = 0.0
        self.assertEqual(solve(value)["verdict"], INVALID_REQUEST)
        value = request()
        value["loads"]["load_factors"] = (1.0,)
        self.assertEqual(solve(value)["verdict"], INVALID_REQUEST)


if __name__ == "__main__":
    unittest.main()
