import copy
import unittest

from photoloset.cross_ccd import (
    ANSWER, INITIAL_INTERSECTION, INVALID_INPUT, capabilities,
    edge_edge_toi, evaluate_seams, project_contacts, solve, vertex_triangle_toi,
)


class ContinuousCollisionTests(unittest.TestCase):
    def test_capabilities_are_honest(self):
        report = capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["features"]["linear_trajectory_ccd"])
        self.assertFalse(report["features"]["exact_symbolic_toi"])
        self.assertFalse(report["features"]["shell_fem"])

    def test_vertex_triangle_toi_with_thickness(self):
        result = vertex_triangle_toi(
            [0.25, 0.25, 1.0], [0.25, 0.25, -1.0],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]], thickness_m=0.1)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertTrue(result["hit"])
        self.assertAlmostEqual(result["toi"], 0.45, places=6)
        self.assertAlmostEqual(sum(result["contact"]["barycentric"]), 1.0)

    def test_edge_edge_toi(self):
        result = edge_edge_toi(
            [[-1, 0, 0], [1, 0, 0]], [[-1, 0, 0], [1, 0, 0]],
            [[0, -1, 1], [0, 1, 1]], [[0, -1, -1], [0, 1, -1]],
            thickness_m=0.05)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertTrue(result["hit"])
        self.assertAlmostEqual(result["toi"], 0.475, places=6)

    def test_degenerate_and_initial_intersection_fail_closed(self):
        degenerate = vertex_triangle_toi([0, 0, 1], [0, 0, -1],
            [[0, 0, 0], [1, 0, 0], [2, 0, 0]],
            [[0, 0, 0], [1, 0, 0], [2, 0, 0]])
        self.assertEqual(degenerate["verdict"], INVALID_INPUT)
        initial = edge_edge_toi(
            [[-1, 0, 0], [1, 0, 0]], [[-1, 0, 0], [1, 0, 0]],
            [[0, -1, 0], [0, 1, 0]], [[0, -1, 1], [0, 1, 1]])
        self.assertEqual(initial["verdict"], INITIAL_INTERSECTION)

    def test_contact_projection_is_jacobi_and_immutable(self):
        old = [[0.25, 0.25, 0.2], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        predicted = [[0.25, 0.25, 0.02], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        frozen = copy.deepcopy((old, predicted))
        result = project_contacts(old, predicted, [[1, 2, 3]], thickness_m=0.05,
                                  friction_coefficient=0.2,
                                  inverse_masses=[1, 0, 0, 0])
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["projection"], "same-old-state Jacobi")
        self.assertGreaterEqual(result["positions"][0][2], 0.05-1e-9)
        self.assertEqual((old, predicted), frozen)

    def test_contact_projection_rejects_old_self_intersection(self):
        points = [[0.25, 0.25, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        result = project_contacts(points, points, [[1, 2, 3]], thickness_m=0.01)
        self.assertEqual(result["verdict"], INITIAL_INTERSECTION)

    def test_public_solve_combines_layers_from_same_old_state(self):
        previous = [[0.25, 0.25, 0.2], [0, 0, 0], [1, 0, 0],
                    [0, 1, 0], [2, 0, 0], [3, 0, 0]]
        proposed = [[0.25, 0.25, 0.02], [0, 0, 0], [1, 0, 0],
                    [0, 1, 0], [2, 0, 0], [3.2, 0, 0]]
        result = solve(previous, proposed, [[1, 2, 3]],
            edges=(), seams=[{"a": 4, "b": 5, "rest_length_m": 1.0,
                              "damage_onset_strain": 0.1, "break_strain": 0.5}],
            thickness_m=0.05, friction_static=0.5,
            friction_dynamic=0.3, time_step_s=0.01)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["projection"], "same-old-state Jacobi")
        self.assertEqual(result["parameters"]["friction_static"], 0.5)
        self.assertEqual(len(result["seams"]), 1)

    def test_public_solve_rejects_invalid_friction_order(self):
        result = solve([[0, 0, 1], [0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, 1], [0, 0, 0], [1, 0, 0], [0, 1, 0]], [[1, 2, 3]],
            thickness_m=0.01, friction_static=0.1,
            friction_dynamic=0.2, time_step_s=0.01)
        self.assertEqual(result["verdict"], INVALID_INPUT)


class SeamTests(unittest.TestCase):
    def test_slip_damage_puckering_and_projection(self):
        old = [[0, 0, 0], [1, 0, 0]]
        predicted = [[0, 0, 0], [1.15, 0.1, 0]]
        result = evaluate_seams(old, predicted, [{
            "a": 0, "b": 1, "rest_length_m": 1.0,
            "damage_onset_strain": 0.05, "break_strain": 0.30,
            "compliance_m_n": 0.0, "previous_damage": 0.1,
            "feed_mismatch_ratio": 0.08,
        }], dt_s=0.01)
        self.assertEqual(result["verdict"], ANSWER)
        seam = result["seams"][0]
        self.assertGreater(seam["slip_m"], 0.09)
        self.assertGreater(seam["damage_index"], 0.1)
        self.assertEqual(seam["damage_state"], "PRE_BREAK_DAMAGE")
        self.assertGreater(seam["puckering_index"], 0.08)
        self.assertEqual(result["projection"], "same-old-state Jacobi")

    def test_damage_is_monotone_and_break_disables_correction(self):
        result = evaluate_seams([[0, 0, 0], [1, 0, 0]],
            [[0, 0, 0], [1.5, 0, 0]], [{
                "a": 0, "b": 1, "rest_length_m": 1,
                "damage_onset_strain": 0.1, "break_strain": 0.3,
                "previous_damage": 0.8,
            }], dt_s=0.02)
        self.assertEqual(result["seams"][0]["damage_state"], "BROKEN")
        self.assertEqual(result["positions"], [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]])

    def test_invalid_seam_fails_closed(self):
        result = evaluate_seams([[0, 0, 0], [1, 0, 0]],
            [[0, 0, 0], [1, 0, 0]], [{
                "a": 0, "b": 0, "rest_length_m": 1,
                "damage_onset_strain": 0.1, "break_strain": 0.2,
            }], dt_s=0.01)
        self.assertEqual(result["verdict"], INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
