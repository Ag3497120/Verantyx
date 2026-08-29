import math
import unittest

from photoloset.cross_constraints import (
    ANSWER,
    CONTESTED,
    CROSS_SECTION_DIRECTIONS,
    UNKNOWN_INFEASIBLE_CONSTRAINTS,
    UNKNOWN_INVALID_CONSTRAINTS,
    UNKNOWN_NOT_STABLE,
    UNKNOWN_REFINEMENT_REQUIRED,
    solve_cross_constraints,
    solve_cross_layers,
    solve_cross_sections,
)


def state(*points, inverse_masses=None, previous=None, layers=None, triangles=None):
    inverse_masses = inverse_masses or [1.0] * len(points)
    previous = previous or points
    layers = layers or [0] * len(points)
    return {
        "vertices": [
            {
                "position": list(point),
                "previous_position": list(prior),
                "inverse_mass": mass,
                "layer": layer,
            }
            for point, prior, mass, layer in zip(
                points, previous, inverse_masses, layers)
        ],
        "triangles": triangles or [],
    }


def cross(target=(1.0, -2.0, 0.5), order=None):
    order = order or list(CROSS_SECTION_DIRECTIONS)
    return {
        "subject_id": "garment-1",
        "center": [0.0, 0.0, 0.0],
        "sections": [
            {"id": arm, "direction": list(CROSS_SECTION_DIRECTIONS[arm]),
             "target_center": list(target), "weight": 1.0,
             "stiffness": index + 1.0, "signal_kind": "geometry"}
            for index, arm in enumerate(order)
        ],
    }


class CrossConstraintTests(unittest.TestCase):
    def test_sphere_contact_projects_outside(self):
        cloth = state((0.25, 0.0, 0.0), (0.0, 0.0, 0.0))
        constraints = {"contacts": [{
            "type": "sphere", "center": [0, 0, 0], "radius": 1.0,
            "vertices": [0, 1],
        }]}
        result = solve_cross_constraints(cloth, constraints)
        self.assertEqual(result["verdict"], ANSWER)
        for vertex in result["state"]["vertices"]:
            self.assertAlmostEqual(math.dist(vertex["position"], [0, 0, 0]), 1.0)
        self.assertLessEqual(result["diagnostics"]["max_penetration"], 1e-7)
        self.assertEqual(cloth["vertices"][0]["position"], [0.25, 0.0, 0.0])

    def test_capsule_and_callable_sdf_are_supported(self):
        cloth = state((0.1, 0.0, 0.0), (0.0, 0.2, 0.0))
        constraints = {"contacts": [
            {"type": "capsule", "a": [0, -1, 0], "b": [0, 1, 0],
             "radius": 0.5, "vertices": [0]},
            {"type": "sdf", "distance": lambda p: p[1],
             "gradient": lambda _p: (0, 1, 0), "vertices": [1]},
        ]}
        result = solve_cross_constraints(cloth, constraints)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertAlmostEqual(result["state"]["vertices"][0]["position"][0], 0.5)
        self.assertGreaterEqual(result["state"]["vertices"][1]["position"][1], 0.0)

    def test_compliant_seam_closes_to_rest_gap(self):
        cloth = state((0.0, 0.0, 0.0), (2.0, 0.0, 0.0))
        result = solve_cross_constraints(cloth, {"seams": [{
            "a": 0, "b": 1, "rest_gap": 0.2, "compliance": 0.0,
            "break_threshold": 3.0,
        }]})
        self.assertEqual(result["verdict"], ANSWER)
        points = [v["position"] for v in result["state"]["vertices"]]
        self.assertAlmostEqual(math.dist(*points), 0.2)
        self.assertLessEqual(result["diagnostics"]["max_seam_gap"], 1e-7)

    def test_coulomb_static_and_dynamic_friction(self):
        base = state((0.5, 0.15, 0.0), previous=[(1.0, 0.0, 0.0)])
        no_friction = solve_cross_constraints(base, {"contacts": [{
            "type": "sphere", "center": [0, 0, 0], "radius": 1,
            "friction_static": 0.0, "friction_dynamic": 0.0,
        }]}, iterations=1)
        dynamic = solve_cross_constraints(base, {"contacts": [{
            "type": "sphere", "center": [0, 0, 0], "radius": 1,
            "friction_static": 0.5, "friction_dynamic": 0.25,
        }]}, iterations=1)
        sticky = solve_cross_constraints(base, {"contacts": [{
            "type": "sphere", "center": [0, 0, 0], "radius": 1,
            "friction_static": 10.0, "friction_dynamic": 0.25,
        }]}, iterations=1)
        prior = base["vertices"][0]["previous_position"]
        def travel(result):
            return math.dist(result["state"]["vertices"][0]["position"], prior)
        self.assertLess(travel(dynamic), travel(no_friction))
        self.assertLessEqual(travel(sticky), travel(dynamic))

    def test_spatial_hash_self_collision_separates_vertices(self):
        cloth = state((0.0, 0.0, 0.0), (0.01, 0.0, 0.0),
                      layers=[0, 1])
        result = solve_cross_constraints(cloth, {"self_collision": {
            "distance": 0.2, "cell_size": 0.1,
        }})
        self.assertEqual(result["verdict"], ANSWER)
        points = [v["position"] for v in result["state"]["vertices"]]
        self.assertGreaterEqual(math.dist(*points), 0.2 - 1e-7)
        self.assertEqual(result["diagnostics"]["collision_count"], 0)

    def test_explicit_layer_ordering(self):
        cloth = state((0.0, 0.2, 0.0), (0.0, 0.0, 0.0), layers=[0, 1])
        result = solve_cross_constraints(cloth, {"layer_order": [{
            "inner": 0, "outer": 1, "normal": [0, 1, 0], "gap": 0.1,
        }]})
        self.assertEqual(result["verdict"], ANSWER)
        inner, outer = [v["position"] for v in result["state"]["vertices"]]
        self.assertGreaterEqual(outer[1] - inner[1], 0.1 - 1e-7)

    def test_pinned_penetration_is_typed_infeasible(self):
        cloth = state((0.0, 0.0, 0.0), inverse_masses=[0.0])
        result = solve_cross_constraints(cloth, {"contacts": [{
            "type": "sphere", "center": [0, 0, 0], "radius": 1.0,
        }]})
        self.assertEqual(result["verdict"], UNKNOWN_INFEASIBLE_CONSTRAINTS)
        self.assertGreater(result["diagnostics"]["max_penetration"], 0.9)
        self.assertEqual(result["diagnostics"]["pinned_contact_violations"], 1)

    def test_invalid_constraints_return_typed_unknown(self):
        cloth = state((0.0, 0.0, 0.0))
        invalid_cases = [
            {"contacts": [{"type": "sphere", "center": [0, 0], "radius": 1}]},
            {"seams": [{"a": 0, "b": 3}]},
            {"self_collision": {"distance": -1}},
            {"contacts": [{"type": "sphere", "center": [0, 0, 0],
                            "radius": 1, "friction_static": 0.1,
                            "friction_dynamic": 0.2}]},
        ]
        for constraints in invalid_cases:
            with self.subTest(constraints=constraints):
                result = solve_cross_constraints(cloth, constraints)
                self.assertEqual(result["verdict"], UNKNOWN_INVALID_CONSTRAINTS)
                self.assertTrue(result["reasons"])


class SpatialCrossContractTests(unittest.TestCase):
    def test_jacobi_and_energy_are_scan_order_invariant(self):
        forward = solve_cross_sections(cross(), relaxation=1.0)
        reverse = solve_cross_sections(
            cross(order=list(reversed(list(CROSS_SECTION_DIRECTIONS)))),
            relaxation=1.0)
        self.assertEqual(forward["verdict"], ANSWER)
        self.assertEqual(forward["cross"]["center"], reverse["cross"]["center"])
        self.assertEqual(forward["diagnostics"]["energy_by_arm"],
                         reverse["diagnostics"]["energy_by_arm"])
        self.assertAlmostEqual(
            forward["diagnostics"]["total_energy"],
            sum(forward["diagnostics"]["energy_by_arm"].values()))
        self.assertEqual(forward["diagnostics"]["aggregation"],
                         "JACOBI_SAME_OLD_CENTER")

    def test_disagreement_abstains_instead_of_selecting_tie(self):
        specimen = cross(target=(0.0, 0.0, 0.0))
        specimen["sections"][0]["target_center"] = [1.0, 0.0, 0.0]
        specimen["sections"][1]["target_center"] = [-1.0, 0.0, 0.0]
        result = solve_cross_sections(specimen, relaxation=1.0)
        self.assertEqual(result["verdict"], CONTESTED)
        self.assertFalse(result["diagnostics"]["agreed"])
        self.assertIn("no tied alternative", result["reasons"][0])

    def test_agreement_without_stability_is_unknown(self):
        result = solve_cross_sections(cross(), max_iterations=1, relaxation=0.5)
        self.assertEqual(result["verdict"], UNKNOWN_NOT_STABLE)
        self.assertTrue(result["diagnostics"]["agreed"])
        self.assertFalse(result["diagnostics"]["stable"])

    def test_different_signal_meanings_are_not_bundled(self):
        specimen = cross()
        specimen["sections"][0]["signal_kind"] = "temperature"
        result = solve_cross_sections(specimen)
        self.assertEqual(result["verdict"], UNKNOWN_INVALID_CONSTRAINTS)
        self.assertIn("separate layers", result["reasons"][0])

    def test_fifth_facet_requires_refinement_without_dropping_physics(self):
        specimen = cross(target=(0.0, 0.0, 0.0))
        specimen["sections"][0].pop("target_center")
        specimen["sections"][0]["contributions"] = [
            {"target_center": [float(i), 0, 0], "signal_kind": "geometry"}
            for i in range(5)
        ]
        result = solve_cross_sections(specimen, relaxation=1.0)
        self.assertEqual(result["verdict"], UNKNOWN_REFINEMENT_REQUIRED)
        self.assertEqual(result["diagnostics"]["physical_contribution_count"], 10)
        self.assertEqual(result["diagnostics"]["facet_capacity"]["total_slots"], 24)
        self.assertEqual(result["diagnostics"]["facet_table"]["+x"], [])
        self.assertEqual(len(result["diagnostics"]["contribution_energy_by_arm"]["+x"]), 5)

    def test_independent_contribution_scan_order_does_not_change_physics(self):
        specimen = cross(target=(0.0, 0.0, 0.0))
        arm = specimen["sections"][0]
        arm.pop("target_center")
        arm["contributions"] = [
            {"target_center": [value, 0, 0], "weight": weight,
             "signal_kind": "geometry"}
            for value, weight in ((1.0, 1.0), (3.0, 2.0), (-2.0, 4.0))
        ]
        reversed_specimen = {
            **specimen,
            "sections": [dict(section) for section in specimen["sections"]],
        }
        reversed_specimen["sections"][0]["contributions"] = list(
            reversed(arm["contributions"]))
        forward = solve_cross_sections(specimen, relaxation=1.0)
        reverse = solve_cross_sections(reversed_specimen, relaxation=1.0)
        self.assertEqual(forward["cross"]["center"], reverse["cross"]["center"])
        self.assertAlmostEqual(forward["diagnostics"]["total_energy"],
                               reverse["diagnostics"]["total_energy"])

    def test_nested_refinement_preserves_all_contributions(self):
        specimen = cross(target=(0.0, 0.0, 0.0))
        arm = specimen["sections"][0]
        arm.pop("target_center")
        arm["contributions"] = [
            {"target_center": [0, 0, 0], "signal_kind": "geometry"}
            for _ in range(5)
        ]
        arm["refinement_cells"] = [[0, 1], [2], [3], [4]]
        result = solve_cross_sections(specimen, relaxation=1.0)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(len(result["diagnostics"]["facet_table"]["+x"]), 4)
        self.assertTrue(result["diagnostics"]["facet_table"]["+x"][0]["nested"])

    def test_layers_overlay_coarse_medium_fine_and_reject_identity_copy(self):
        stages = [
            {"name": "rough", "cross": cross((0.0, 0.0, 0.0))},
            {"name": "medium", "cross": cross((0.5, 0.0, 0.0))},
            {"name": "fine", "cross": cross((0.75, 0.0, 0.0))},
        ]
        result = solve_cross_layers(stages, relaxation=1.0)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["cross"]["center"], [0.75, 0.0, 0.0])
        self.assertEqual(result["stages"][1]["input_verdict"], ANSWER)

        copied = [
            {"name": "rough", "cross": cross((0.0, 0.0, 0.0))},
            {"name": "medium", "cross": cross((0.0, 0.0, 0.0))},
            {"name": "fine", "cross": cross((1.0, 0.0, 0.0))},
        ]
        rejected = solve_cross_layers(copied, relaxation=1.0)
        self.assertEqual(rejected["verdict"], UNKNOWN_INVALID_CONSTRAINTS)
        self.assertIn("identity copy", rejected["reasons"][0])

        different_subject = [dict(stage) for stage in stages]
        different_subject[1] = {
            **different_subject[1],
            "cross": {**different_subject[1]["cross"], "subject_id": "garment-2"},
        }
        rejected = solve_cross_layers(different_subject, relaxation=1.0)
        self.assertEqual(rejected["verdict"], UNKNOWN_INVALID_CONSTRAINTS)
        self.assertIn("same subject_id", rejected["reasons"][0])

    def test_contested_coarse_stage_stops_later_resolutions(self):
        disputed = cross((0.0, 0.0, 0.0))
        disputed["sections"][0]["target_center"] = [0.0, 0.0, 1.0]
        stages = [
            {"name": "rough", "cross": disputed},
            {"name": "medium", "cross": cross((0.5, 0.0, 0.0))},
            {"name": "fine", "cross": cross((0.75, 0.0, 0.0))},
        ]
        result = solve_cross_layers(stages, relaxation=1.0)
        self.assertEqual(result["verdict"], CONTESTED)
        self.assertEqual(len(result["stages"]), 1)


if __name__ == "__main__":
    unittest.main()
