#!/usr/bin/env python3
import copy
import json
import math
import unittest

from photoloset import structure_preview


def all_supported_structure():
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {"node_id": "shell", "kind": "BODY_SHELL", "layer": 0,
             "dimensions": {"height_cm": 62.0, "circumference_cm": 88.0}},
            {"node_id": "tube", "kind": "TUBE", "layer": 0,
             "dimensions": {"length_cm": 30.0, "circumference_cm": 70.0,
                            "x_cm": 32.0}},
            {"node_id": "frustum", "kind": "FRUSTUM", "layer": 0,
             "dimensions": {"height_cm": 45.0, "top_circumference_cm": 72.0,
                            "bottom_circumference_cm": 110.0}},
            {"node_id": "flare", "kind": "FLARE", "layer": 1,
             "dimensions": {"height_cm": 55.0, "top_circumference_cm": 70.0,
                            "bottom_circumference_cm": 180.0}},
            {"node_id": "gore", "kind": "GORE", "layer": 1,
             "dimensions": {"length_cm": 48.0, "top_width_cm": 8.0,
                            "bottom_width_cm": 28.0, "x_cm": -18.0}},
            {"node_id": "sleeves", "kind": "SLEEVE", "layer": 0,
             "dimensions": {"length_cm": 54.0,
                            "upper_circumference_cm": 34.0,
                            "cuff_circumference_cm": 20.0},
             "attributes": {"bilateral": True}},
            {"node_id": "band", "kind": "BAND", "layer": 1,
             "dimensions": {"length_cm": 74.0, "width_cm": 5.0}},
            {"node_id": "overlay", "kind": "OVERLAY", "layer": 2,
             "dimensions": {"height_cm": 52.0, "width_cm": 78.0}},
            {"node_id": "gusset", "kind": "GUSSET", "layer": 0,
             "dimensions": {"length_cm": 12.0, "width_cm": 8.0}},
            {"node_id": "yoke", "kind": "YOKE", "layer": 1,
             "dimensions": {"height_cm": 14.0, "width_cm": 38.0}},
            {"node_id": "collar", "kind": "COLLAR", "layer": 1,
             "dimensions": {"length_cm": 42.0, "width_cm": 7.0}},
            {"node_id": "hood", "kind": "HOOD", "layer": 2,
             "dimensions": {"height_cm": 38.0, "width_cm": 32.0,
                            "depth_cm": 28.0}},
            {"node_id": "opening", "kind": "OPENING", "layer": 0,
             "dimensions": {"length_cm": 48.0}},
            {"node_id": "anchor", "kind": "DRAPE_ANCHOR", "layer": 2,
             "dimensions": {}},
        ],
        "operations": [],
    }


def layered_segmented_sleeve_structure():
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {"node_id": "shell", "kind": "BODY_SHELL", "layer": 0,
             "dimensions": {"height_cm": 60.0, "circumference_cm": 88.0}},
            {"node_id": "upper", "kind": "SLEEVE", "layer": 0,
             "dimensions": {"length_cm": 40.0,
                            "upper_circumference_cm": 34.0,
                            "cuff_circumference_cm": 20.0},
             "ports": [
                 {"port_id": "cuff", "length_cm": 20.0,
                  "interface": "sleeve-extension", "role": "edge"},
                 {"port_id": "layer-from-outer", "length_cm": 1.0,
                  "interface": "sleeve-layer-anchor", "role": "point"},
             ],
             "attributes": {"side": "bilateral", "quantity": 2,
                            "attached_to": "shell"}},
            {"node_id": "lower", "kind": "SLEEVE", "layer": 0,
             "dimensions": {"length_cm": 24.0,
                            "upper_circumference_cm": 20.0,
                            "cuff_circumference_cm": 16.0},
             "ports": [{"port_id": "upper", "length_cm": 20.0,
                        "interface": "sleeve-extension", "role": "edge"}],
             "attributes": {"side": "bilateral", "quantity": 2,
                            "attached_to": "upper",
                            "placement": "lower sleeve extension"}},
            {"node_id": "outer", "kind": "SLEEVE", "layer": 2,
             "dimensions": {"length_cm": 32.0,
                            "upper_circumference_cm": 36.0,
                            "cuff_circumference_cm": 22.0},
             "ports": [{"port_id": "layer-to-upper", "length_cm": 1.0,
                        "interface": "sleeve-layer-anchor", "role": "point"}],
             "attributes": {"side": "bilateral", "quantity": 2,
                            "attached_to": "upper",
                            "detail_role": "oversleeve"}},
        ],
        "operations": [
            {"operation_id": "join-lower-to-upper", "kind": "JOIN",
             "source": {"node_id": "lower", "port_id": "upper"},
             "target": {"node_id": "upper", "port_id": "cuff"}},
            {"operation_id": "layer-outer-on-upper", "kind": "LAYER",
             "source": {"node_id": "outer", "port_id": "layer-to-upper"},
             "target": {"node_id": "upper", "port_id": "layer-from-outer"}},
        ],
    }


def gathered_segmented_sleeve_structure():
    structure = layered_segmented_sleeve_structure()
    structure["nodes"] = [node for node in structure["nodes"]
                          if node["node_id"] != "outer"]
    lower = next(node for node in structure["nodes"]
                 if node["node_id"] == "lower")
    lower["dimensions"]["upper_circumference_cm"] = 32.0
    lower["ports"][0]["length_cm"] = 32.0
    lower["attributes"]["sleeve_parent_relation"] = "GATHER"
    structure["operations"] = [{
        "operation_id": "gather-lower-to-upper",
        "kind": "GATHER",
        "source": {"node_id": "lower", "port_id": "upper"},
        "target": {"node_id": "upper", "port_id": "cuff"},
        "parameters": {
            "ratio": 1.6,
            "construction_role": "GATHER_SLEEVE_SEGMENTS",
        },
    }]
    return structure


def triangle_area(vertices, face):
    a, b, c = (vertices[index] for index in face)
    ab = [b[index] - a[index] for index in range(3)]
    ac = [c[index] - a[index] for index in range(3)]
    cross = [ab[1]*ac[2]-ab[2]*ac[1],
             ab[2]*ac[0]-ab[0]*ac[2],
             ab[0]*ac[1]-ab[1]*ac[0]]
    return 0.5 * math.sqrt(sum(value*value for value in cross))


class StructurePreviewTests(unittest.TestCase):
    def test_all_supported_primitives_have_deterministic_valid_topology(self):
        candidate = {"candidate_id": "anime-layered-a",
                     "structure": all_supported_structure()}
        first = structure_preview.generate_candidate_preview(candidate)
        second = structure_preview.generate_candidate_preview(copy.deepcopy(candidate))
        self.assertEqual(first, second)
        self.assertEqual(first["verdict"], "ANSWER")
        self.assertEqual(first["state"], "PROPOSED")
        self.assertEqual(first["schema"], "garment.structure.preview.v1")
        self.assertEqual({part["kind"] for part in first["parts"]}, {
            "BODY_SHELL", "TUBE", "FRUSTUM", "FLARE", "GORE", "SLEEVE",
            "BAND", "OVERLAY", "GUSSET", "YOKE", "COLLAR", "HOOD",
            "OPENING", "DRAPE_ANCHOR",
        })
        mesh = first["mesh"]
        self.assertTrue(mesh["vertices"])
        self.assertTrue(mesh["faces"])
        self.assertTrue(all(len(face) == 3 and len(set(face)) == 3
                            and min(face) >= 0 and max(face) < len(mesh["vertices"])
                            for face in mesh["faces"]))
        self.assertTrue(all(triangle_area(mesh["vertices"], face) > 1.0e-10
                            for face in mesh["faces"]))
        self.assertEqual(first["topology"]["degenerate_face_indices"], [])
        self.assertEqual(first["topology"]["nonmanifold_edges"], [])
        self.assertFalse(first["claims"]["manufacturing_ready"])
        self.assertFalse(first["claims"]["sewable_pattern"])
        json.dumps(first, allow_nan=False)

    def test_layers_and_layer_operation_are_explicit(self):
        structure = {
            "schema": "garment.structure.v1",
            "nodes": [
                {"node_id": "shell", "kind": "BODY_SHELL", "layer": 0,
                 "dimensions": {"height_cm": 60.0, "circumference_cm": 88.0},
                 "ports": [{"port_id": "surface", "length_cm": 10.0,
                            "interface": "layer", "role": "edge"}]},
                {"node_id": "cape", "kind": "OVERLAY", "layer": 3,
                 "dimensions": {"height_cm": 50.0, "width_cm": 90.0},
                 "ports": [{"port_id": "inside", "length_cm": 10.0,
                            "interface": "layer", "role": "edge"}]},
            ],
            "operations": [{
                "operation_id": "cape-over-shell", "kind": "LAYER",
                "source": {"node_id": "cape", "port_id": "inside"},
                "target": {"node_id": "shell", "port_id": "surface"},
            }],
        }
        result = structure_preview.generate_preview(
            structure, candidate_id="cape-back-option")
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([row["layer"] for row in result["layers"]], [0, 3])
        self.assertEqual(result["layers"][1]["node_ids"], ["cape"])
        self.assertEqual(result["layer_relations"], [{
            "operation_id": "cape-over-shell",
            "source_node_id": "cape", "source_layer": 3,
            "target_node_id": "shell", "target_layer": 0,
        }])
        for face_index in result["layers"][1]["face_indices"]:
            self.assertEqual(result["mesh"]["face_layers"][face_index], 3)
            self.assertEqual(result["mesh"]["face_node_ids"][face_index], "cape")

    def test_unknown_primitive_fails_closed_without_partial_mesh(self):
        structure = all_supported_structure()
        structure["nodes"].append({
            "node_id": "unknown", "kind": "TORUS_TRIM", "layer": 0,
            "dimensions": {"length_cm": 12.0, "width_cm": 8.0},
        })
        result = structure_preview.generate_preview(
            structure, candidate_id="candidate-with-gusset")
        self.assertTrue(result["verdict"].startswith("UNKNOWN_"))
        self.assertNotIn("mesh", result)
        self.assertFalse(result["claims"]["manufacturing_ready"])

    def test_candidate_identity_and_structure_change_preview_digest(self):
        first_structure = all_supported_structure()
        second_structure = copy.deepcopy(first_structure)
        second_structure["nodes"][3]["dimensions"]["bottom_circumference_cm"] = 230.0
        first = structure_preview.generate_preview(
            first_structure, candidate_id="narrow-back")
        second = structure_preview.generate_preview(
            second_structure, candidate_id="wide-back")
        self.assertEqual(first["verdict"], "ANSWER")
        self.assertEqual(second["verdict"], "ANSWER")
        self.assertNotEqual(first["structure_digest"], second["structure_digest"])
        self.assertNotEqual(first["preview_digest"], second["preview_digest"])
        self.assertNotEqual(first["mesh"]["vertices"], second["mesh"]["vertices"])
        self.assertTrue(first["provenance"]["candidate_specific"])

    def test_bilateral_segmented_and_layered_sleeves_preserve_instances(self):
        result = structure_preview.generate_preview(
            layered_segmented_sleeve_structure(),
            candidate_id="layered-segmented-sleeves")
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["state"], "PROPOSED")
        self.assertFalse(result["claims"]["material_simulated"])
        self.assertFalse(result["claims"]["mannequin_certified"])

        parts = {part["node_id"]: part for part in result["parts"]}
        for node_id in ("upper", "lower", "outer"):
            instances = parts[node_id]["instances"]
            self.assertEqual([row["side"] for row in instances],
                             ["left", "right"])
            self.assertEqual([row["instance_id"] for row in instances],
                             [f"{node_id}:left", f"{node_id}:right"])
            left_vertices = set(range(*instances[0]["vertex_range"]))
            right_vertices = set(range(*instances[1]["vertex_range"]))
            left_faces = set(instances[0]["face_indices"])
            right_faces = set(instances[1]["face_indices"])
            self.assertTrue(left_vertices.isdisjoint(right_vertices))
            self.assertTrue(left_faces.isdisjoint(right_faces))
            vertices = result["mesh"]["vertices"]
            self.assertLess(sum(vertices[index][0] for index in left_vertices)
                            / len(left_vertices), 0.0)
            self.assertGreater(sum(vertices[index][0] for index in right_vertices)
                               / len(right_vertices), 0.0)

        coverage = result["sleeve_relation_coverage"]
        for operation_id in ("join-lower-to-upper", "layer-outer-on-upper"):
            rows = [row for row in coverage
                    if row["operation_id"] == operation_id]
            self.assertEqual({row["side"] for row in rows}, {"left", "right"})
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["authority"] == "PROPOSED"
                                and row["preview_only"] for row in rows))

    def test_lower_join_starts_at_each_parent_cuff_boundary(self):
        segments = 12
        result = structure_preview.generate_preview(
            layered_segmented_sleeve_structure(),
            candidate_id="cuff-boundary", radial_segments=segments)
        self.assertEqual(result["verdict"], "ANSWER")
        parts = {part["node_id"]: part for part in result["parts"]}
        vertices = result["mesh"]["vertices"]
        parent_by_side = {row["side"]: row for row in parts["upper"]["instances"]}
        child_by_side = {row["side"]: row for row in parts["lower"]["instances"]}
        for side in ("left", "right"):
            parent = parent_by_side[side]
            child = child_by_side[side]
            parent_cuff = {
                tuple(vertices[index])
                for index in range(parent["vertex_range"][1] - segments,
                                   parent["vertex_range"][1])
            }
            child_upper = {
                tuple(vertices[index])
                for index in range(child["vertex_range"][0],
                                   child["vertex_range"][0] + segments)
            }
            self.assertEqual(child_upper, parent_cuff)
            self.assertEqual(child["parent_instance_id"], f"upper:{side}")
            self.assertEqual(child["attached_to_node_id"], "upper")
            self.assertEqual(child["relation_kind"], "JOIN")

    def test_gathered_lower_sleeve_uses_parent_cuff_envelope_and_keeps_fullness(self):
        segments = 12
        result = structure_preview.generate_preview(
            gathered_segmented_sleeve_structure(),
            candidate_id="gathered-cuff-boundary", radial_segments=segments)
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertFalse(result["claims"]["physical_gathered_folds_resolved"])
        parts = {part["node_id"]: part for part in result["parts"]}
        vertices = result["mesh"]["vertices"]
        parent_by_side = {row["side"]: row
                          for row in parts["upper"]["instances"]}
        child_by_side = {row["side"]: row
                         for row in parts["lower"]["instances"]}
        for side in ("left", "right"):
            parent = parent_by_side[side]
            child = child_by_side[side]
            parent_cuff = {
                tuple(vertices[index])
                for index in range(parent["vertex_range"][1] - segments,
                                   parent["vertex_range"][1])
            }
            child_upper = {
                tuple(vertices[index])
                for index in range(child["vertex_range"][0],
                                   child["vertex_range"][0] + segments)
            }
            self.assertEqual(child_upper, parent_cuff)
            self.assertEqual(child["relation_kind"], "GATHER")
            self.assertEqual(child["parent_instance_id"], f"upper:{side}")
            lineage = child["lineage"]["gather_lineage"]
            self.assertEqual(lineage["construction_role"],
                             "GATHER_SLEEVE_SEGMENTS")
            self.assertAlmostEqual(lineage["source_cut_length_cm"], 32.0)
            self.assertAlmostEqual(lineage["target_finished_length_cm"], 20.0)
            self.assertAlmostEqual(lineage["source_fullness_cm"], 12.0)
            self.assertAlmostEqual(lineage["ratio"], 1.6)
            self.assertEqual(lineage["mesh_representation"],
                             "PARENT_CUFF_ENVELOPE_ONLY")
            self.assertFalse(lineage["physical_gathered_folds_resolved"])
        coverage = [row for row in result["sleeve_relation_coverage"]
                    if row["operation_id"] == "gather-lower-to-upper"]
        self.assertEqual({row["side"] for row in coverage},
                         {"left", "right"})
        self.assertTrue(all(row["kind"] == "GATHER"
                            and row["source_boundary"] == "upper"
                            and row["target_boundary"] == "cuff"
                            and not row["gather_lineage"][
                                "physical_gathered_folds_resolved"]
                            for row in coverage))

    def test_oversleeve_layer_has_strict_radial_clearance_and_lineage(self):
        result = structure_preview.generate_preview(
            layered_segmented_sleeve_structure(),
            candidate_id="oversleeve-clearance", layer_spacing_cm=0.75)
        self.assertEqual(result["verdict"], "ANSWER")
        parts = {part["node_id"]: part for part in result["parts"]}
        parent_by_side = {row["side"]: row for row in parts["upper"]["instances"]}
        outer_by_side = {row["side"]: row for row in parts["outer"]["instances"]}
        for side in ("left", "right"):
            parent = parent_by_side[side]
            outer = outer_by_side[side]
            self.assertEqual(outer["axis_origin_cm"], parent["axis_origin_cm"])
            self.assertGreater(outer["upper_radius_cm"],
                               parent["upper_radius_cm"])
            self.assertGreaterEqual(outer["radial_clearance_cm"], 0.75)
            self.assertEqual(outer["attached_to_node_id"], "upper")
            self.assertEqual(outer["parent_instance_id"], f"upper:{side}")
            self.assertEqual(outer["relation_kind"], "LAYER")
            self.assertEqual(outer["state"], "PROPOSED")
        layer_row = next(row for row in result["layer_relations"]
                         if row["operation_id"] == "layer-outer-on-upper")
        self.assertEqual({row["side"] for row in layer_row["instance_coverage"]},
                         {"left", "right"})

    def test_unilateral_sleeve_stays_unilateral(self):
        structure = all_supported_structure()
        sleeve = next(node for node in structure["nodes"]
                      if node["kind"] == "SLEEVE")
        sleeve["attributes"] = {"side": "left", "quantity": 1}
        result = structure_preview.generate_preview(
            structure, candidate_id="left-only")
        self.assertEqual(result["verdict"], "ANSWER")
        part = next(part for part in result["parts"]
                    if part["kind"] == "SLEEVE")
        self.assertEqual(len(part["instances"]), 1)
        self.assertEqual(part["instances"][0]["side"], "left")

    def test_sleeve_side_mismatch_and_unresolved_parent_fail_closed(self):
        mismatch = layered_segmented_sleeve_structure()
        mismatch["nodes"][1]["attributes"] = {
            "side": "left", "quantity": 1, "attached_to": "shell"}
        result = structure_preview.generate_preview(
            mismatch, candidate_id="side-mismatch")
        self.assertEqual(result["verdict"],
                         "UNKNOWN_STRUCTURE_PREVIEW_SLEEVE_SIDE_MISMATCH")
        self.assertNotIn("mesh", result)

        unresolved = all_supported_structure()
        sleeve = next(node for node in unresolved["nodes"]
                      if node["kind"] == "SLEEVE")
        sleeve["attributes"] = {
            "side": "left", "quantity": 1, "attached_to": "missing-parent"}
        result = structure_preview.generate_preview(
            unresolved, candidate_id="unresolved-parent")
        self.assertEqual(result["verdict"],
                         "UNKNOWN_STRUCTURE_PREVIEW_SLEEVE_ATTACHMENT")
        self.assertNotIn("mesh", result)

        bad_quantity = all_supported_structure()
        sleeve = next(node for node in bad_quantity["nodes"]
                      if node["kind"] == "SLEEVE")
        sleeve["attributes"] = {"side": "bilateral", "quantity": 1}
        result = structure_preview.generate_preview(
            bad_quantity, candidate_id="bad-bilateral-quantity")
        self.assertEqual(result["verdict"],
                         "UNKNOWN_STRUCTURE_PREVIEW_SLEEVE_SIDE_MISMATCH")
        self.assertNotIn("mesh", result)


if __name__ == "__main__":
    unittest.main()
