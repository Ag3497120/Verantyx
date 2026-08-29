# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset.cross_cloth_solver import simulate


VERTICES = ((-0.5, 1.0, 0.0), (0.5, 1.0, 0.0),
            (0.5, 0.0, 0.0), (-0.5, 0.0, 0.0))
FACES = ((0, 1, 2), (0, 2, 3))
PROFILE = {
    "areal_density_kg_m2": 0.2,
    "warp_stiffness_n_m": 180.0,
    "weft_stiffness_n_m": 120.0,
    "shear_stiffness_n_m": 40.0,
    "bending_stiffness_n_m": 1.0e-4,
    "damping_ratio": 0.2,
    "drag_coefficient": 1.1,
    "lift_coefficient": 0.05,
}


class CrossClothSolverTests(unittest.TestCase):
    def test_force_and_constraint_stages_are_integrated(self):
        result = simulate(
            VERTICES, FACES, face_material_ids=("cloth", "cloth"),
            materials={"cloth": PROFILE}, fixed_vertices=(0, 1),
            constraints={"contacts": [{"type": "sphere", "center": [0, -0.5, 0],
                                        "radius": 0.35}]},
            time_step_s=1/240, steps=4)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertIn(result["terminal_verdict"], ("CONVERGED", "IN_PROGRESS"))
        self.assertEqual(len(result["history"]), 4)
        self.assertTrue(result["cross_contract"]["not_atoms_or_molecules"])
        self.assertTrue(all(row["substeps"] >= 1 for row in result["history"]))

    def test_wind_changes_the_trajectory_without_mutating_inputs(self):
        vertices = copy.deepcopy(VERTICES)
        calm = simulate(vertices, FACES, face_material_ids=("cloth", "cloth"),
                        materials={"cloth": PROFILE}, fixed_vertices=(0, 1),
                        environment={"wind_velocity_m_s": [0, 0, 0]}, steps=3)
        wind = simulate(vertices, FACES, face_material_ids=("cloth", "cloth"),
                        materials={"cloth": PROFILE}, fixed_vertices=(0, 1),
                        environment={"wind_velocity_m_s": [0, 0, 8]}, steps=3)
        self.assertEqual(vertices, VERTICES)
        self.assertNotEqual(calm["lattice"]["nodes"]["2"]["position_m"],
                            wind["lattice"]["nodes"]["2"]["position_m"])

    def test_material_interface_requires_an_explicit_seam(self):
        result = simulate(VERTICES, FACES, face_material_ids=("a", "b"),
                          materials={"a": PROFILE, "b": PROFILE}, steps=1)
        self.assertEqual(result["verdict"], "UNKNOWN_CROSS_SOLVER_INPUT")
        self.assertIn("interface", result["why"])

    def test_missing_coefficients_are_typed(self):
        result = simulate(VERTICES, FACES, face_material_ids=("cloth", "cloth"),
                          materials={"cloth": {"areal_density_kg_m2": 0.2}})
        self.assertEqual(result["verdict"], "UNKNOWN_CROSS_SOLVER_INPUT")
        self.assertIn("lacks", result["why"])


if __name__ == "__main__":
    unittest.main()
