# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset.cross_xpbd import (
    ANSWER,
    INFEASIBLE,
    INVALID_INPUT,
    TIMESTEP_TOO_LARGE,
    backend_capabilities,
    capabilities,
    simulate,
    simulate_xpbd,
)


REST = ((0.0, 1.0, 0.0), (1.0, 1.0, 0.0),
        (1.0, 0.0, 0.0), (0.0, 0.0, 0.0))
FACES = ((0, 1, 2), (0, 2, 3))
MATERIAL = {
    "areal_density_kg_m2": 0.2,
    "warp_stiffness_n_m": 800.0,
    "weft_stiffness_n_m": 80.0,
    "shear_stiffness_n_m": 40.0,
    "bending_stiffness_n_m": 0.02,
    "damping_ratio": 0.02,
}


def solve(**overrides):
    options = dict(
        face_material_ids=("cloth", "cloth"), materials={"cloth": MATERIAL},
        gravity_m_s2=(0.0, 0.0, 0.0), time_step_s=1/60,
        steps=1, solver_iterations=30,
    )
    options.update(overrides)
    return simulate_xpbd(REST, FACES, **options)


class CrossXPBDTests(unittest.TestCase):
    def test_backend_report_is_honest(self):
        report = backend_capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["cpu"]["available"])
        self.assertFalse(report["gpu"]["available"])
        self.assertFalse(report["features"]["continuous_collision"])
        self.assertFalse(report["features"]["shell_fem"])
        self.assertEqual(capabilities(), report)
        self.assertIs(simulate, simulate_xpbd)

    def test_inputs_are_immutable_and_output_is_finite(self):
        vertices = [list(point) for point in REST]
        faces = [list(face) for face in FACES]
        material = copy.deepcopy(MATERIAL)
        snapshot = copy.deepcopy((vertices, faces, material))
        result = simulate_xpbd(
            vertices, faces, face_material_ids=("cloth", "cloth"),
            materials={"cloth": material}, fixed_vertices=(0, 1), steps=2)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual((vertices, faces, material), snapshot)
        self.assertTrue(all(math.isfinite(component)
                            for vertex in result["state"]["vertices"]
                            for component in vertex["position_m"]))
        self.assertEqual(result["diagnostics"]["projection"],
                         "XPBD_JACOBI_SAME_OLD_STATE")

    def test_orthotropic_warp_corrects_more_than_soft_weft(self):
        deformed = ((0.0, 1.0, 0.0), (1.5, 1.0, 0.0),
                    (1.5, -0.5, 0.0), (0.0, -0.5, 0.0))
        result = solve(initial_positions=deformed)
        self.assertEqual(result["verdict"], ANSWER)
        strain = result["diagnostics"]["strain"]
        self.assertLess(strain["warp"]["maximum"], strain["weft"]["maximum"])

    def test_dihedral_bending_reduces_fold(self):
        bent = ((0.0, 1.0, 0.0), (1.0, 1.0, 0.0),
                (1.0, 0.0, 0.5), (0.0, 0.0, -0.5))
        before = solve(initial_positions=bent, solver_iterations=1)
        after = solve(initial_positions=bent, solver_iterations=40)
        self.assertLessEqual(
            after["diagnostics"]["strain"]["bending"]["maximum"],
            before["diagnostics"]["strain"]["bending"]["maximum"])

    def test_compliant_seam_closes_and_reports_energy(self):
        result = solve(seams=({"a": 1, "b": 3, "rest_gap_m": 0.2,
                              "compliance_m_n": 1.0e-5},))
        self.assertEqual(result["verdict"], ANSWER)
        self.assertLess(result["diagnostics"]["strain"]["seam"]["maximum"], 0.8)
        self.assertGreaterEqual(
            result["diagnostics"]["energy_j"]["constraint_by_kind"]["seam"], 0.0)

    def test_adaptive_substeps_and_timestep_refusal(self):
        moving = [(0.0, 0.0, 0.0)] * 4
        moving[2] = (100.0, 0.0, 0.0)
        accepted = solve(initial_velocities=moving, max_substeps=100)
        self.assertEqual(accepted["verdict"], ANSWER)
        self.assertGreater(accepted["diagnostics"]["substeps"], 1)
        refused = solve(initial_velocities=moving, max_substeps=1)
        self.assertEqual(refused["verdict"], TIMESTEP_TOO_LARGE)
        self.assertGreater(refused["required_substeps"], 1)

    def test_constraint_order_does_not_change_jacobi_result(self):
        seams = ({"a": 0, "b": 2, "rest_gap_m": 0.5,
                  "compliance_m_n": 1.0e-4},
                 {"a": 1, "b": 3, "rest_gap_m": 0.5,
                  "compliance_m_n": 1.0e-4})
        forward = solve(seams=seams)
        reverse = solve(seams=tuple(reversed(seams)))
        self.assertEqual(forward["state"], reverse["state"])

    def test_invalid_and_infeasible_inputs_are_typed(self):
        bad = solve(seams=({"a": 0, "b": 99},))
        self.assertEqual(bad["verdict"], INVALID_INPUT)
        blocked = solve(
            fixed_vertices=(0, 1, 2, 3),
            seams=({"a": 0, "b": 2, "rest_gap_m": 0.1,
                    "compliance_m_n": 0.0},))
        self.assertEqual(blocked["verdict"], INFEASIBLE)

    def test_convergence_and_energy_diagnostics_are_present(self):
        result = solve()
        diagnostics = result["diagnostics"]
        self.assertIn(result["terminal_verdict"], ("CONVERGED", "IN_PROGRESS"))
        self.assertIn("convergence", diagnostics)
        self.assertIn("strain", diagnostics)
        self.assertIn("energy_j", diagnostics)
        self.assertEqual(set(diagnostics["strain"]),
                         {"warp", "weft", "shear", "bending", "seam"})


if __name__ == "__main__":
    unittest.main()
