# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import second_skin_triangle_engine as engine


def body_proxy():
    return {
        "verdict": "ANSWER",
        "_levels": [
            (0.0, 9.0, 6.0),
            (50.0, 10.0, 7.0),
            (100.0, 8.5, 6.0),
        ],
    }


def one_component(component_id="shell", *, coverage=None):
    component = {
        "component_id": component_id,
        "center_ratio": [0.0, 0.0],
        "radius_ratio": [1.0, 1.0],
    }
    if coverage is not None:
        component["angular_coverage_deg"] = coverage
    return component


def request(surfaces, *, relations=None, cues=None):
    return {
        "body_proxy": body_proxy(),
        "surfaces": surfaces,
        "relations": relations or [],
        "front_cues": cues or [],
        "layer_gap_cm": 0.3,
        "resolution": {"angular_segments": 8, "height_steps": 4},
    }


def layered_request():
    surfaces = [
        {
            "surface_id": "upper-domain",
            "y_range_cm": [50.0, 100.0],
            "layer": 0,
            "ease_cm": 0.5,
            "components": [one_component("upper-shell")],
        },
        {
            "surface_id": "lower-domain",
            "y_range_cm": [0.0, 50.0],
            "layer": 0,
            "ease_cm": 0.8,
            "components": [one_component("lower-shell")],
        },
        {
            "surface_id": "outer-patch",
            "y_range_cm": [0.0, 50.0],
            "layer": 1,
            "ease_cm": 0.8,
            "components": [one_component("right-front", coverage=[0.0, 90.0])],
        },
    ]
    relations = [
        {
            "relation_id": "waist-join",
            "kind": "JOIN",
            "parent_id": "upper-domain",
            "child_id": "lower-domain",
            "attachment_port": "waist",
            "attachment_side": "FULL",
            "ownership": "upper-domain",
            "layer": 0,
        },
        {
            "relation_id": "right-overlay",
            "kind": "LAYER",
            "parent_id": "lower-domain",
            "child_id": "outer-patch",
            "attachment_port": "right-waist-anchor",
            "attachment_side": "RIGHT",
            "ownership": {
                "owner_id": "lower-domain",
                "state": "PROPOSED",
            },
            "layer": 1,
        },
    ]
    cues = [
        {
            "cue_id": "right-front-triangle",
            "surface_id": "outer-patch",
            "kind": "TRIANGLE",
            "points_cm": [[0.0, 0.0], [14.0, 0.0], [7.0, 50.0]],
            "coordinate_space": "BODY_CM_FRONT",
            "state": "OBSERVED",
            "offset_cm": 1.5,
            "weight": 1.0,
            "source_id": "front-frame/triangle-7",
        },
        {
            "cue_id": "upper-front-polygon",
            "surface_id": "upper-domain",
            "kind": "POLYGON",
            "points_cm": [[-7.0, 55.0], [7.0, 55.0],
                          [7.0, 90.0], [-7.0, 90.0]],
            "coordinate_space": "BODY_CM_FRONT",
            "state": "PROPOSED",
            "offset_cm": 0.4,
        },
    ]
    return request(surfaces, relations=relations, cues=cues)


class SecondSkinTriangleEngineTests(unittest.TestCase):
    def test_triangle_supported_front_deformation_is_jacobi_and_bounded(self):
        silhouette = [[-4.0, 0.0], [4.0, 0.0],
                      [12.0, 100.0], [-12.0, 100.0]]
        result = engine.build(request([{
            "surface_id": "unnamed-visible-domain",
            "y_range_cm": [0.0, 100.0],
            "layer": 0,
            "components": [one_component("unnamed-shell")],
        }], cues=[{
            "cue_id": "front-ledger-polygon",
            "surface_id": "unnamed-visible-domain",
            "kind": "POLYGON",
            "points_cm": silhouette,
            "coordinate_space": "BODY_CM_FRONT",
            "state": "OBSERVED",
            "offset_cm": 0.0,
            "weight": 1.0,
        }]))

        self.assertEqual(engine.PROPOSED, result["verdict"])
        projection = result["front_cue_projections"][0]
        self.assertEqual(2, projection["support_triangle_count"])
        self.assertGreater(projection["matched_front_vertex_count"], 0)
        self.assertEqual(0, projection["matched_rear_vertex_count"])
        self.assertGreater(len(projection["matched_triangle_ids"]), 0)
        right_edge = []
        for state in result["vertex_states"]:
            if (state["surface_id"] == "unnamed-visible-domain"
                    and state["angular_index"] == 0
                    and state["matched_triangle_ids"]):
                vertex = result["mesh"]["vertices_cm"][state["vertex_id"]]
                right_edge.append((vertex[1], vertex[0]))
        self.assertGreaterEqual(len(right_edge), 3)
        right_edge.sort()
        self.assertLess(right_edge[0][1], right_edge[-1][1])
        self.assertAlmostEqual(6.0, dict(right_edge)[25.0], places=6)
        self.assertAlmostEqual(10.0, dict(right_edge)[75.0], places=6)
        self.assertTrue(result["jacobi_reduction"]
                        ["all_proposals_read_same_old_state"])
        self.assertFalse(result["jacobi_reduction"]["in_place_updates"])
        self.assertEqual("X_ONLY", result["jacobi_reduction"]
                         ["front_silhouette_axis_observed"])
        self.assertEqual(["OBSERVED"], result["jacobi_reduction"]
                         ["front_silhouette_support_states"])
        self.assertTrue(result["cross_lattice_provenance"]["same_old_state"])
        self.assertTrue(result["cross_lattice_provenance"]
                        ["deterministic_reduction"])
        self.assertEqual(result["source_front_contract"]["digest"],
                         result["cross_lattice_provenance"]
                         ["source_front_digest"])
        self.assertFalse(result["rear"]["observed"])
        self.assertFalse(result["material"]["observed"])
        self.assertEqual("UNKNOWN_UNOBSERVED", result["material"]["state"])

    def test_two_component_lower_skin_differs_from_single_shell_topology(self):
        paired = request([{
            "surface_id": "neutral-lower-paired",
            "y_range_cm": [0.0, 55.0],
            "layer": 0,
            "components": [
                {
                    "component_id": "component-a",
                    "center_ratio": [-0.48, 0.0],
                    "radius_ratio": [0.42, 0.55],
                },
                {
                    "component_id": "component-b",
                    "center_ratio": [0.48, 0.0],
                    "radius_ratio": [0.42, 0.55],
                },
            ],
        }])
        single = request([{
            "surface_id": "neutral-lower-single",
            "y_range_cm": [0.0, 55.0],
            "layer": 0,
            "components": [one_component("component-only")],
        }])

        paired_result = engine.build(paired)
        single_result = engine.build(single)

        self.assertEqual(engine.PROPOSED, paired_result["verdict"])
        self.assertEqual(engine.PROPOSED, single_result["verdict"])
        self.assertEqual(2, paired_result["topology"]["topological_component_count"])
        self.assertEqual(1, single_result["topology"]["topological_component_count"])
        self.assertEqual(2, len(paired_result["topology"]["components"]))
        self.assertEqual(1, len(single_result["topology"]["components"]))
        self.assertTrue(all(len(face) == 3
                            for face in paired_result["mesh"]["triangles"]))
        self.assertFalse(paired_result["topology"]["name_based_branching"])
        ranges = [component["vertex_range"]
                  for component in paired_result["topology"]["components"]]
        self.assertLessEqual(ranges[0][1], ranges[1][0])

    def test_layered_top_bottom_and_overlay_have_explicit_graph_and_cross(self):
        result = engine.build(layered_request())

        self.assertEqual(engine.PROPOSED, result["verdict"])
        self.assertEqual("ANSWER", result["geometry_verdict"])
        self.assertEqual(3, result["topology"]["surface_count"])
        relations = {row["relation_id"]: row
                     for row in result["topology"]["relations"]}
        self.assertEqual("upper-domain", relations["waist-join"]["parent_id"])
        self.assertEqual("lower-domain", relations["waist-join"]["child_id"])
        self.assertEqual("lower-domain",
                         relations["right-overlay"]["ownership"]["owner_id"])
        self.assertEqual(1, relations["right-overlay"]["child_layer"])
        self.assertFalse(relations["right-overlay"]["seam_join_created"])
        self.assertTrue(result["jacobi_reduction"][
            "all_proposals_read_same_old_state"])
        first_cross_vertex = result["cross_lattice"]["vertices"][0]
        self.assertEqual(
            ["+warp", "-warp", "+weft", "-weft", "+normal", "-normal"],
            [arm["name"] for arm in first_cross_vertex["arms"]],
        )
        self.assertEqual("NOT_EVALUATED",
                         result["pattern_interface"]["sewability"])
        self.assertFalse(result["pattern_interface"]["sewability_claimed"])
        self.assertFalse(result["authority"]["sewability_claimed"])
        self.assertGreater(
            len(result["pattern_interface"]["pattern_boundary_candidates"]), 0)

    def test_asymmetric_front_attachment_offsets_only_proposed_front_support(self):
        result = engine.build(layered_request())
        relation = next(row for row in result["topology"]["relations"]
                        if row["relation_id"] == "right-overlay")
        projection = next(row for row in result["front_cue_projections"]
                          if row["cue_id"] == "right-front-triangle")

        self.assertEqual("RIGHT", relation["attachment_side"])
        self.assertEqual("right-waist-anchor", relation["attachment_port"])
        self.assertGreater(projection["matched_front_vertex_count"], 0)
        self.assertEqual(0, projection["matched_rear_vertex_count"])
        self.assertEqual("PROPOSED", projection["offset_state"])
        self.assertFalse(projection["depth_observed"])
        self.assertEqual("PROPOSED", result["rear"]["state"])
        self.assertFalse(result["rear"]["observed"])
        rear_states = [row for row in result["vertex_states"]
                       if row["evidence_state"] == "PROPOSED_UNOBSERVED_REAR"]
        self.assertGreater(len(rear_states), 0)
        relation_boundary = next(
            row for row in result["pattern_interface"][
                "attachment_boundary_candidates"]
            if row["relation_id"] == "right-overlay")
        self.assertEqual("RIGHT", relation_boundary["attachment_side"])
        self.assertTrue(relation_boundary["pattern_ready_geometry"])
        self.assertFalse(relation_boundary["sewability_claimed"])
        patch_boundaries = [
            row for row in result["pattern_interface"][
                "pattern_boundary_candidates"]
            if row["surface_id"] == "outer-patch"
        ]
        self.assertTrue(any(row["kind"] == "OPEN_SIDE_BOUNDARY"
                            and not row["closed_loop"]
                            for row in patch_boundaries))

    def test_digest_and_mesh_are_deterministic_across_input_order(self):
        first_request = layered_request()
        second_request = copy.deepcopy(first_request)
        second_request["surfaces"].reverse()
        second_request["relations"].reverse()
        second_request["front_cues"].reverse()

        first = engine.build(first_request)
        second = engine.build(second_request)

        self.assertEqual(engine.PROPOSED, first["verdict"])
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(first["mesh"], second["mesh"])
        self.assertEqual(first["cross_lattice_digest"],
                         second["cross_lattice_digest"])
        self.assertEqual(first["jacobi_reduction"]["old_state_digest"],
                         second["jacobi_reduction"]["old_state_digest"])
        self.assertEqual(first_request, layered_request(),
                         "build must not mutate its request")

    def test_invalid_relations_fail_closed_with_stable_type(self):
        base_surface = {
            "surface_id": "base",
            "y_range_cm": [0.0, 50.0],
            "layer": 0,
            "components": [one_component("base-shell")],
        }
        child_surface = {
            "surface_id": "child",
            "y_range_cm": [0.0, 50.0],
            "layer": 1,
            "components": [one_component("child-shell")],
        }
        valid_relation = {
            "kind": "LAYER",
            "parent_id": "base",
            "child_id": "child",
            "attachment_port": "front-anchor",
            "ownership": "base",
            "layer": 1,
        }
        cases = []

        unknown_parent = copy.deepcopy(valid_relation)
        unknown_parent["parent_id"] = "missing"
        unknown_parent["ownership"] = "missing"
        cases.append(unknown_parent)

        wrong_owner = copy.deepcopy(valid_relation)
        wrong_owner["ownership"] = "child"
        cases.append(wrong_owner)

        wrong_layer = copy.deepcopy(valid_relation)
        wrong_layer["layer"] = 0
        cases.append(wrong_layer)

        elevated_authority = copy.deepcopy(valid_relation)
        elevated_authority["state"] = "OBSERVED"
        cases.append(elevated_authority)

        for relation in cases:
            with self.subTest(relation=relation):
                result = engine.build(request(
                    [base_surface, child_surface], relations=[relation]))
                self.assertEqual(engine.UNKNOWN_RELATION, result["verdict"])
                self.assertEqual("UNRESOLVED", result["state"])
                self.assertNotIn("mesh", result)


if __name__ == "__main__":
    unittest.main()
