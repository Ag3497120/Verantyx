# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import industrial_solver


REST = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
FACES = [[0, 1, 2], [0, 2, 3]]
XPBD = {
    "areal_density_kg_m2": 0.2,
    "warp_stiffness_n_m": 800.0,
    "weft_stiffness_n_m": 80.0,
    "shear_stiffness_n_m": 40.0,
    "bending_stiffness_n_m": 0.02,
    "damping_ratio": 0.02,
}
SHELL = {
    "calibration": {"status": "CALIBRATED", "id": "coupon-1"},
    "thickness_m": 0.001,
    "young_warp_pa": 2.0e6,
    "young_weft_pa": 4.0e5,
    "shear_pa": 1.0e5,
    "poisson_warp_weft": 0.2,
    "bending_stiffness_n_m": 0.02,
    "plasticity": {
        "yield_strain": 0.03, "hardening_pa": 1.0e5,
        "max_plastic_strain": 0.25, "hysteresis_ratio": 0.15,
        "bending_yield_rad": 0.1, "max_plastic_bending_rad": 0.8,
    },
}
FLUID_MATERIAL = {"drag_coefficient": 1.2, "lift_coefficient": 0.0,
                  "permeability": 0.0}


def request(**overrides):
    value = {
        "schema": industrial_solver.SCHEMA,
        "rest_positions": REST,
        "faces": FACES,
        "face_material_ids": ["cloth", "cloth"],
        "materials": {"xpbd": {"cloth": XPBD}},
        "time_step_s": 1.0 / 60.0,
        "xpbd": {"gravity_m_s2": [0.0, 0.0, 0.0],
                 "steps": 1, "solver_iterations": 4},
    }
    value.update(overrides)
    return value


class IndustrialSolverTests(unittest.TestCase):
    def test_capabilities_do_not_claim_industrial_completion(self):
        report = industrial_solver.capabilities()
        self.assertEqual(report["verdict"], "ANSWER")
        self.assertFalse(report["industrial_completion"])
        self.assertFalse(report["cross_role"]["solves_equations_by_itself"])
        self.assertFalse(report["kernels"]["fluid"]["features"]["complete_cfd"])

    def test_minimal_pipeline_is_deterministic_and_immutable(self):
        value = request()
        frozen = copy.deepcopy(value)
        first = industrial_solver.simulate(value)
        second = industrial_solver.simulate(value)
        self.assertEqual(first, second)
        self.assertEqual(value, frozen)
        self.assertEqual(first["verdict"], "ANSWER")
        self.assertEqual(first["stages"]["xpbd"]["verdict"], "ANSWER")
        self.assertEqual(first["stages"]["shell"]["verdict"],
                         "SKIPPED_NOT_REQUESTED")

    def test_fluid_shell_and_ccd_are_typed_handoffs(self):
        value = request(
            materials={"xpbd": {"cloth": XPBD},
                       "shell": {"cloth": SHELL},
                       "fluid": {"cloth": FLUID_MATERIAL}},
            fluid={"density_kg_m3": 1.2, "cell_size_m": 1.0,
                   "cfl_safety": 1.0, "base_velocity_m_s": [0.0, 0.0, 0.0]},
            shell={"apply_correction": True},
            ccd={"thickness_m": 0.001, "friction_static": 0.5,
                 "friction_dynamic": 0.3, "edges": []},
        )
        result = industrial_solver.simulate(value)
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual(result["stages"]["fluid"]["verdict"], "ANSWER")
        self.assertTrue(result["stages"]["shell"]["correction_committed"])
        self.assertEqual(result["stages"]["ccd"]["verdict"], "ANSWER")
        self.assertFalse(result["industrial_completion"])

    def test_shell_correction_is_a_proposal_by_default(self):
        value = request(materials={"xpbd": {"cloth": XPBD},
                                   "shell": {"cloth": SHELL}}, shell={})
        result = industrial_solver.simulate(value)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertFalse(result["stages"]["shell"]["correction_committed"])
        self.assertEqual(result["state"]["positions"],
                         [row["position_m"] for row in
                          result["stages"]["xpbd"]["state"]["vertices"]])

    def test_uncalibrated_shell_fails_at_named_stage(self):
        shell = copy.deepcopy(SHELL)
        shell["calibration"]["status"] = "ESTIMATED"
        result = industrial_solver.simulate(request(
            materials={"xpbd": {"cloth": XPBD}, "shell": {"cloth": shell}},
            shell={}))
        self.assertEqual(result["verdict"], industrial_solver.FAILED_STAGE)
        self.assertEqual(result["failed_stage"], "shell")
        self.assertEqual(result["upstream"]["verdict"],
                         "UNKNOWN_CROSS_SHELL_UNCALIBRATED_MATERIAL")

    def test_unknown_xpbd_option_is_not_silently_ignored(self):
        result = industrial_solver.simulate(request(xpbd={"magic": True}))
        self.assertEqual(result["verdict"], industrial_solver.INVALID_INPUT)
        self.assertIn("unsupported xpbd", result["why"])


if __name__ == "__main__":
    unittest.main()
