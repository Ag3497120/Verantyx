# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset import sewing_topology


def make_request(**updates):
    result = {
        "yarn": {
            "rest_positions_m": [[-0.3, 0.0, 0.002], [-0.1, 0.0, 0.002],
                                 [0.1, 0.0, 0.002], [0.3, 0.0, 0.002]],
            "initial_positions_m": [[-0.3, 0.0, 0.002], [-0.1, 0.0, 0.002],
                                    [0.1, 0.0, 0.002], [0.3, 0.0, 0.002]],
            "stretch_stiffness_n_m": 500.0,
            "bend_stiffness_n_m": 20.0,
            "torsional_stiffness_n_m2": 8.0,
            "initial_twist_angles_rad": [0.0, 1.2, -0.4],
            "rest_twist_angles_rad": [0.0, 0.0, 0.0],
            "twist_regularization": 0.25,
            "radius_m": 0.002,
            "breaking_strain": 1.0,
        },
        "needle": {
            "path_m": [[-0.1, 0.0, 0.1], [-0.1, 0.0, -0.1],
                       [0.1, 0.0, -0.1], [0.1, 0.0, 0.1]],
            "radius_m": 0.001,
            "eye_yarn_node": 3,
        },
        "cloth": {
            "vertices_m": [[-0.5, -0.5, 0.0], [0.5, -0.5, 0.0],
                           [0.5, 0.5, 0.0], [-0.5, 0.5, 0.0]],
            "faces": [[0, 1, 2], [0, 2, 3]],
            "thickness_m": 0.001,
        },
        "friction": {
            "coefficient": 0.4,
            "normal_stiffness_n_m": 100.0,
            "regularization_speed_m_s": 0.01,
            "relative_velocity_m_s": [0.2, 0.0, 0.0],
        },
        "time_step_s": 1.0/120.0,
        "solver_iterations": 20,
        "torsion_iterations": 30,
    }
    result.update(updates)
    return result


class SewingTopologyTests(unittest.TestCase):
    def test_capabilities_are_explicitly_reference_level(self):
        caps = sewing_topology.capabilities()
        self.assertEqual(caps["level"], "reference")
        self.assertTrue(caps["features"]["yarn_twist_torsion"])
        self.assertFalse(caps["features"]["non_manifold_changes"])
        self.assertFalse(caps["features"]["industrial_sewing_machine"])

    def test_twist_torsion_is_deterministic_and_reduced(self):
        source = make_request()
        snapshot = copy.deepcopy(source)
        first = sewing_topology.simulate(source)
        second = sewing_topology.simulate(source)
        self.assertEqual(first, second)
        self.assertEqual(source, snapshot)
        torsion = first["diagnostics"]["torsion"]
        self.assertLess(torsion["maximum_torsion_rad_m"],
                        torsion["initial_maximum_torsion_rad_m"])
        self.assertGreaterEqual(torsion["torsional_energy_j"], 0.0)
        self.assertTrue(first["claims"]["reference_level"])

    def test_regularized_friction_is_finite_and_bounded(self):
        result = sewing_topology.simulate(make_request())
        self.assertGreater(len(result["friction_candidates"]), 0)
        for candidate in result["friction_candidates"]:
            self.assertTrue(all(math.isfinite(x)
                                for x in candidate["friction_force_n"]))
            self.assertLessEqual(candidate["friction_magnitude_n"],
                                 candidate["coulomb_bound_n"] + 1.0e-12)
        self.assertFalse(result["diagnostics"]["friction"]["coupled_impulse_solve"])

    def test_cut_edge_detaches_one_face_and_logs_inverse(self):
        source = make_request(topology_operations=[
            {"op": "CUT_EDGE", "edge": [0, 2], "detach_face": 1}
        ])
        result = sewing_topology.simulate(source)
        self.assertEqual(result["verdict"], sewing_topology.ANSWER)
        mesh = result["state"]["cloth_mesh"]
        self.assertEqual(len(mesh["vertices_m"]), 6)
        self.assertTrue(set(mesh["faces"][0]).isdisjoint(set(mesh["faces"][1])))
        event = result["event_log"]["cloth_topology"][0]
        self.assertEqual(event["kind"], "CUT_EDGE")
        self.assertEqual(event["inverse"]["op"], "RESTORE_MESH")

    def test_triangle_remeshing_preserves_area_topology(self):
        source = make_request(topology_operations=[
            {"op": "REMESH_TRIANGLE", "face": 0,
             "barycentric": [0.2, 0.3, 0.5]}
        ])
        result = sewing_topology.simulate(source)
        mesh = result["state"]["cloth_mesh"]
        self.assertEqual(len(mesh["vertices_m"]), 5)
        self.assertEqual(len(mesh["faces"]), 4)
        self.assertEqual(result["event_log"]["cloth_topology"][0]["kind"],
                         "REMESH_TRIANGLE")

    def test_suffix_undo_restores_exact_mesh(self):
        source = make_request(
            topology_operations=[{"op": "REMESH_TRIANGLE", "face": 0}],
            undo_topology_events=1)
        result = sewing_topology.simulate(source)
        mesh = result["state"]["cloth_mesh"]
        self.assertEqual(mesh["vertices_m"], source["cloth"]["vertices_m"])
        self.assertEqual(mesh["faces"], source["cloth"]["faces"])
        log = result["event_log"]["cloth_topology"]
        self.assertFalse(log[0]["active"])
        self.assertEqual(log[-1]["kind"], "UNDO_TOPOLOGY")

    def test_non_manifold_input_is_refused(self):
        source = make_request()
        source["cloth"] = {
            "vertices_m": [[0, 0, 0], [1, 0, 0], [0, 1, 0],
                           [0, -1, 0], [0, 0, 1]],
            "faces": [[0, 1, 2], [1, 0, 3], [0, 1, 4]],
            "thickness_m": 0.001,
        }
        result = sewing_topology.simulate(source)
        self.assertEqual(result["verdict"], sewing_topology.INVALID_TOPOLOGY)

    def test_unsupported_boundary_cut_is_refused(self):
        source = make_request(topology_operations=[
            {"op": "CUT_EDGE", "edge": [0, 1]}
        ])
        result = sewing_topology.simulate(source)
        self.assertEqual(result["verdict"], sewing_topology.UNSUPPORTED_CHANGE)

    def test_base_yarn_breakage_refusal_is_preserved(self):
        source = make_request()
        source["yarn"]["breaking_strain"] = 0.01
        source["yarn"]["initial_positions_m"][1][0] = 0.0
        result = sewing_topology.simulate(source)
        self.assertEqual(result["verdict"], yarn_breakage_code())


def yarn_breakage_code():
    return "UNKNOWN_YARN_BREAKAGE"


if __name__ == "__main__":
    unittest.main()
