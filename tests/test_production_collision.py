import copy
import unittest

from photoloset.production_collision import (
    ANSWER, INVALID_INPUT, NON_CONVERGENCE, UNCERTAIN, capabilities, solve,
)


def request_for(points0, points1, faces, **extra):
    request = {
        "previous_positions": points0,
        "proposed_positions": points1,
        "faces": faces,
        "thickness_m": 0.05,
        "time_step_s": 0.02,
        "toi_tolerance_s": 1.0e-7,
    }
    request.update(extra)
    return request


class ProductionCollisionTests(unittest.TestCase):
    def test_capabilities_do_not_claim_exact_or_industrial_completion(self):
        report = capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["features"]["sweep_and_prune"])
        self.assertTrue(report["features"]["cross_ccd_narrow_phase"])
        self.assertFalse(report["features"]["exact_symbolic_toi"])
        self.assertFalse(report["features"]["industrial_certification"])

    def test_vertex_triangle_hit_has_bracket_and_seconds_error(self):
        old = [[0.25, 0.25, 1], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        new = [[0.25, 0.25, -1], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        result = solve(request_for(old, new, [[1, 2, 3]]))
        self.assertEqual(result["verdict"], ANSWER)
        event = result["events"][0]
        self.assertEqual(event["kind"], "VERTEX_TRIANGLE")
        self.assertLessEqual(event["error_bound_s"], 1.0e-7)
        lo, hi = event["toi_normalized_bracket"]
        self.assertLessEqual(lo, 0.475)
        self.assertGreaterEqual(hi, 0.475)

    def test_swept_aabb_rejects_far_primitives(self):
        old = [[10, 10, 10], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        result = solve(request_for(old, old, [[1, 2, 3]]))
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["broad_phase"]["vertex_triangle_candidates"], 0)

    def test_edge_edge_hit_and_shared_vertex_exclusion(self):
        old = [[-1, 0, 0], [1, 0, 0], [0, -1, 1], [0, 1, 1], [2, 0, 0]]
        new = [[-1, 0, 0], [1, 0, 0], [0, -1, -1], [0, 1, -1], [2, 0, 0]]
        result = solve(request_for(old, new, [],
            edges=[[0, 1], [2, 3], [1, 4]]))
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual([event["kind"] for event in result["events"]], ["EDGE_EDGE"])
        self.assertGreaterEqual(result["broad_phase"]["edge_edge_adjacency_excluded"], 1)

    def test_candidate_results_are_input_order_invariant(self):
        old = [[0.2, 0.2, 1], [3.2, 0.2, 1],
               [0, 0, 0], [1, 0, 0], [0, 1, 0],
               [3, 0, 0], [4, 0, 0], [3, 1, 0]]
        new = [[0.2, 0.2, -1], [3.2, 0.2, -1]] + old[2:]
        first = solve(request_for(old, new, [[2, 3, 4], [5, 6, 7]],
                                            edges=[]))
        second = solve(request_for(old, new, [[7, 6, 5], [4, 3, 2]],
                                             edges=[]))
        self.assertEqual(first["verdict"], ANSWER)
        self.assertEqual(first["events"], second["events"])
        self.assertEqual(first["broad_phase"], second["broad_phase"])

    def test_incident_vertex_face_is_excluded(self):
        points = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
        result = solve(request_for(points, points, [[0, 1, 2]], edges=[]))
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["broad_phase"]["vertex_triangle_adjacency_excluded"], 3)

    def test_refinement_budget_returns_typed_non_convergence(self):
        old = [[0.25, 0.25, 1], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        new = [[0.25, 0.25, -3], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        result = solve(request_for(old, new, [[1, 2, 3]],
                    max_refinement_nodes=1))
        self.assertEqual(result["verdict"], NON_CONVERGENCE)
        self.assertIn("error_normalized", result)

    def test_unsampled_tangential_touch_remains_typed_uncertain(self):
        old = [[-1, 0, 0], [1, 0, 0],
               [-1, -0.3, 0.05], [1, -0.3, 0.05]]
        new = [[-1, 0, 0], [1, 0, 0],
               [-1, 0.7, 0.05], [1, 0.7, 0.05]]
        result = solve(request_for(old, new, [], edges=[[0, 1], [2, 3]],
                                   toi_tolerance_s=1.0e-5))
        self.assertEqual(result["verdict"], UNCERTAIN)
        self.assertIn("unresolved", result)
        self.assertEqual(result["candidate"]["kind"], "EDGE_EDGE")

    def test_invalid_and_degenerate_input_fail_closed_without_mutation(self):
        request = request_for([[0, 0, 0], [1, 0, 0], [2, 0, 0]],
                              [[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 1, 2]])
        frozen = copy.deepcopy(request)
        result = solve(request)
        self.assertEqual(result["verdict"], INVALID_INPUT)
        self.assertEqual(request, frozen)


if __name__ == "__main__":
    unittest.main()
