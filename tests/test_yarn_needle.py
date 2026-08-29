# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset import yarn_needle


def request(**updates):
    value = {
        "yarn": {
            "rest_positions_m": [[-0.2, 0.0, 0.08], [0.0, 0.0, 0.08],
                                 [0.2, 0.0, 0.08]],
            "initial_positions_m": [[-0.2, 0.0, 0.08], [0.0, 0.08, 0.08],
                                    [0.24, 0.0, 0.08]],
            "stretch_stiffness_n_m": 500.0,
            "bend_stiffness_n_m": 20.0,
            "radius_m": 0.002,
            "breaking_strain": 1.0,
        },
        "needle": {
            "path_m": [[-0.1, 0.0, 0.1], [-0.1, 0.0, -0.1],
                       [0.1, 0.0, -0.1], [0.1, 0.0, 0.1]],
            "radius_m": 0.001,
            "eye_yarn_node": 2,
        },
        "cloth": {
            "vertices_m": [[-0.5, -0.5, 0.0], [0.5, -0.5, 0.0],
                           [0.5, 0.5, 0.0], [-0.5, 0.5, 0.0]],
            "faces": [[0, 1, 2], [0, 2, 3]],
            "thickness_m": 0.001,
        },
        "time_step_s": 1.0/120.0,
        "solver_iterations": 30,
    }
    value.update(updates)
    return value


class YarnNeedleTests(unittest.TestCase):
    def test_capabilities_are_honest(self):
        caps = yarn_needle.capabilities()
        self.assertEqual(caps["verdict"], yarn_needle.ANSWER)
        self.assertTrue(caps["features"]["discrete_elastic_rod"])
        self.assertTrue(caps["features"]["undoable_event_log"])
        self.assertFalse(caps["features"]["industrial_sewing_machine"])
        self.assertFalse(caps["features"]["continuous_collision"])

    def test_simulation_is_deterministic_immutable_and_finite(self):
        source = request()
        snapshot = copy.deepcopy(source)
        first = yarn_needle.simulate(source)
        second = yarn_needle.simulate(source)
        self.assertEqual(first, second)
        self.assertEqual(source, snapshot)
        self.assertEqual(first["verdict"], yarn_needle.ANSWER)
        self.assertTrue(all(math.isfinite(x)
                            for p in first["state"]["yarn_positions_m"] for x in p))
        self.assertFalse(first["claims"]["industrial_sewing_machine"])

    def test_stretch_and_bending_are_reduced(self):
        source = request()
        initial = yarn_needle.simulate({**source, "solver_iterations": 1})
        solved = yarn_needle.simulate({**source, "solver_iterations": 60})
        self.assertLessEqual(solved["diagnostics"]["maximum_stretch_strain"],
                             initial["diagnostics"]["maximum_stretch_strain"])
        self.assertLessEqual(solved["diagnostics"]["maximum_bend_error_m"],
                             initial["diagnostics"]["maximum_bend_error_m"])
        self.assertEqual(solved["diagnostics"]["constraint_projection"],
                         "JACOBI_SAME_OLD_STATE")

    def test_yarn_cloth_contact_candidates_are_reported(self):
        source = request()
        source["yarn"]["rest_positions_m"] = [[-0.2, 0.0, 0.002],
                                                [0.0, 0.0, 0.002],
                                                [0.2, 0.0, 0.002]]
        source["yarn"]["initial_positions_m"] = copy.deepcopy(
            source["yarn"]["rest_positions_m"])
        result = yarn_needle.simulate(source)
        self.assertEqual(result["verdict"], yarn_needle.ANSWER)
        self.assertGreater(len(result["contacts"]), 0)
        self.assertTrue(all(c["distance_m"] <= 0.003 for c in result["contacts"]))

    def test_penetrations_form_stitch_and_loop_graph(self):
        result = yarn_needle.simulate(request())
        topology = result["state"]["topology"]
        self.assertEqual(result["diagnostics"]["needle_penetrations_detected"], 2)
        self.assertEqual(len(topology["anchors"]), 2)
        self.assertEqual(len(topology["stitch_edges"]), 1)
        self.assertEqual(len(topology["loops"]), 1)
        self.assertEqual([e["kind"] for e in result["event_log"]],
                         ["NEEDLE_PENETRATION", "NEEDLE_PENETRATION", "STITCH_FORMED"])

    def test_event_log_can_undo_stitch_topology(self):
        source = request(undo_events=1)
        result = yarn_needle.simulate(source)
        topology = result["state"]["topology"]
        self.assertEqual(len(topology["anchors"]), 2)
        self.assertEqual(topology["stitch_edges"], [])
        self.assertEqual(topology["loops"], [])
        self.assertEqual(result["event_log"][-1]["kind"], "UNDO")
        self.assertEqual(result["diagnostics"]["undone_events"], 1)

    def test_breakage_is_typed_and_refused(self):
        source = request()
        source["yarn"]["breaking_strain"] = 0.01
        result = yarn_needle.simulate(source)
        self.assertEqual(result["verdict"], yarn_needle.BREAKAGE)
        self.assertNotIn("state", result)

    def test_invalid_topology_is_typed_and_refused(self):
        source = request(initial_topology={
            "anchors": [{"id": "a"}],
            "stitch_edges": [{"id": "s", "anchors": ["a", "missing"]}],
            "loops": [],
        })
        result = yarn_needle.simulate(source)
        self.assertEqual(result["verdict"], yarn_needle.INVALID_TOPOLOGY)

    def test_invalid_geometry_and_impossible_undo_are_refused(self):
        source = request(undo_events=99)
        result = yarn_needle.simulate(source)
        self.assertEqual(result["verdict"], yarn_needle.INVALID_INPUT)
        bad = request()
        bad["cloth"]["faces"] = [[0, 1, 1]]
        self.assertEqual(yarn_needle.simulate(bad)["verdict"],
                         yarn_needle.INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
