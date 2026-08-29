#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import structure_preview
from photoloset import structure_to_pattern as compiler


def band(operation=None):
    structure = {
        "schema": "garment.structure.v1",
        "nodes": [{
            "node_id": "base",
            "kind": "BAND",
            "dimensions": {"length_cm": 10.0, "width_cm": 4.0},
            "ports": [{
                "port_id": "right",
                "length_cm": 4.0,
                "interface": "side",
                "role": "edge",
            }],
        }],
        "operations": [],
    }
    if operation is not None:
        structure["operations"] = [operation]
    return structure


def split_operation():
    return {
        "operation_id": "panel-split",
        "kind": "SPLIT",
        "source": {"node_id": "base", "port_id": "right"},
        "parameters": {
            "line": [[0.0, -1.0], [0.0, 5.0]],
            "new_piece_ids": {
                "negative": "right-panel",
                "positive": "left-panel",
            },
        },
    }


def mirror_operation():
    return {
        "operation_id": "mirror-right",
        "kind": "MIRROR",
        "source": {"node_id": "base", "port_id": "right"},
        "parameters": {
            "axis": "x",
            "offset_cm": 5.0,
            "side": "negative_to_positive",
            "new_piece_id": "mirrored",
            "source_cut_count": 1,
            "new_cut_count": 1,
            "source_edge_lineage": {
                "e0": "e2", "e1": "e1", "e2": "e0", "e3": "e3",
            },
        },
    }


def asymmetry_operation():
    return {
        "operation_id": "asymmetric-right",
        "kind": "ASYMMETRY",
        "source": {"node_id": "base", "port_id": "right"},
        "parameters": {
            "side": "right",
            "new_piece_id": "right-asymmetric",
            "source_cut_count": 1,
            "new_cut_count": 1,
            "vertex_offsets_cm": [
                [0.0, 0.0], [2.0, 0.0], [1.0, 1.0], [0.0, 1.0],
            ],
            "source_edge_lineage": {
                "e0": "e0", "e1": "e1", "e2": "e2", "e3": "e3",
            },
        },
    }


class StructurePreviewGeometricOperationTests(unittest.TestCase):
    def assert_pattern_identity(self, structure, candidate_id, preview):
        pattern = compiler.compile_structure(
            copy.deepcopy(structure), candidate_id=candidate_id,
            candidate_state="PROPOSED")
        self.assertEqual(pattern["verdict"], "ANSWER")
        self.assertEqual(preview["candidate_id"], pattern["candidate_id"])
        self.assertEqual(preview["structure_digest"],
                         pattern["structure_digest"])
        conformance = preview["pattern_conformance"]
        self.assertEqual(conformance["candidate_id"], pattern["candidate_id"])
        self.assertEqual(conformance["structure_digest"],
                         pattern["structure_digest"])
        self.assertEqual(conformance["pattern_digest"], pattern["digest"])
        self.assertEqual(
            conformance["operation_identity"],
            [{"operation_id": row["operation_id"], "kind": row["kind"]}
             for row in pattern["geometry_operations"]])
        self.assertEqual(
            [row["pattern_operation"] for row in preview["geometry_operations"]],
            pattern["geometry_operations"])
        self.assertTrue(preview["claims"]["pattern_geometry_identity_checked"])
        self.assertTrue(all(row["state"] == "PROPOSED"
                            for row in preview["geometry_operations"]))
        return pattern

    def test_split_partitions_existing_faces_and_exposes_rejoin_boundary(self):
        structure = band(split_operation())
        baseline = structure_preview.generate_preview(
            band(), candidate_id="split-candidate")
        preview = structure_preview.generate_preview(
            structure, candidate_id="split-candidate")
        self.assertEqual(preview["verdict"], "ANSWER")
        pattern = self.assert_pattern_identity(
            structure, "split-candidate", preview)

        # SPLIT changes ownership and the sewing boundary, not the garment's
        # outer preview surface.  No second copy of the original shell exists.
        self.assertEqual(preview["topology"]["vertex_count"],
                         baseline["topology"]["vertex_count"])
        self.assertEqual(preview["topology"]["triangle_count"],
                         baseline["topology"]["triangle_count"])
        children = {part["piece_id"]: set(part["face_indices"])
                    for part in preview["parts"]}
        self.assertEqual(set(children), {"right-panel", "left-panel"})
        self.assertFalse(children["right-panel"] & children["left-panel"])
        self.assertEqual(children["right-panel"] | children["left-panel"],
                         set(range(len(preview["mesh"]["faces"]))))
        self.assertEqual(set(preview["mesh"]["face_piece_ids"]), set(children))

        boundary = preview["construction_boundaries"]
        self.assertEqual(len(boundary), 1)
        self.assertEqual(boundary[0]["operation_id"], "panel-split")
        self.assertEqual(boundary[0]["kind"], "SPLIT_REJOIN")
        self.assertTrue(boundary[0]["mesh_edges"])
        self.assertEqual(
            boundary[0]["generated_join"],
            pattern["geometry_operations"][0]["generated_join"])

    def test_mirror_reflects_real_mesh_and_derived_piece_identity(self):
        structure = band(mirror_operation())
        preview = structure_preview.generate_preview(
            structure, candidate_id="mirror-candidate")
        self.assertEqual(preview["verdict"], "ANSWER")
        pattern = self.assert_pattern_identity(
            structure, "mirror-candidate", preview)
        parts = {part["piece_id"]: part for part in preview["parts"]}
        self.assertEqual(set(parts), {"base", "mirrored"})
        self.assertEqual(parts["mirrored"]["operation_id"], "mirror-right")
        self.assertEqual(parts["mirrored"]["source_node_id"], "base")
        source = preview["mesh"]["vertices"][slice(*parts["base"]["vertex_range"])]
        derived = preview["mesh"]["vertices"][slice(*parts["mirrored"]["vertex_range"])]
        self.assertEqual(len(source), len(derived))
        for before, after in zip(source, derived):
            self.assertAlmostEqual(before[0] + after[0], 10.0)
            self.assertEqual(before[1:], after[1:])
        operation = preview["geometry_operations"][0]
        self.assertEqual(operation["derived_piece_ids"], ["mirrored"])
        self.assertEqual(operation["axis"], "x")
        self.assertEqual(operation["offset_cm"], 5.0)
        self.assertEqual(operation["side"], "negative_to_positive")
        self.assertEqual(operation["pattern_operation"]["axis"], "x")
        self.assertEqual(operation["pattern_operation"]["side"],
                         "negative_to_positive")
        self.assertEqual({piece["piece_id"] for piece in pattern["pieces"]},
                         {"base", "mirrored"})

    def test_asymmetry_deforms_real_mesh_and_changes_preview_geometry(self):
        structure = band(asymmetry_operation())
        preview = structure_preview.generate_preview(
            structure, candidate_id="asymmetric-candidate")
        repeat = structure_preview.generate_preview(
            copy.deepcopy(structure), candidate_id="asymmetric-candidate")
        self.assertEqual(preview, repeat)
        self.assertEqual(preview["verdict"], "ANSWER")
        self.assert_pattern_identity(
            structure, "asymmetric-candidate", preview)
        parts = {part["piece_id"]: part for part in preview["parts"]}
        source = preview["mesh"]["vertices"][slice(*parts["base"]["vertex_range"])]
        derived = preview["mesh"]["vertices"][
            slice(*parts["right-asymmetric"]["vertex_range"])]
        self.assertEqual(len(source), len(derived))
        self.assertTrue(any(before != after
                            for before, after in zip(source, derived)))
        self.assertEqual(
            preview["geometry_operations"][0]["derived_piece_ids"],
            ["right-asymmetric"])
        self.assertNotEqual(
            preview["preview_digest"],
            structure_preview.generate_preview(
                band(), candidate_id="asymmetric-candidate")["preview_digest"])

    def test_cutout_removes_faces_and_matches_2d_hole_lineage(self):
        structure = band({
            "operation_id": "neck-cutout",
            "kind": "CUTOUT",
            "source": {"node_id": "base", "port_id": "right"},
            "parameters": {
                "closed_polygon": [[-1.0, 1.0], [1.0, 1.0],
                                   [1.0, 2.0], [-1.0, 2.0]],
            },
        })
        preview = structure_preview.generate_preview(
            structure, candidate_id="cutout-candidate")
        self.assertEqual(preview["verdict"], "ANSWER")
        pattern = self.assert_pattern_identity(
            structure, "cutout-candidate", preview)
        cutout = pattern["geometry_operations"][0]
        operation = preview["geometry_operations"][0]
        self.assertEqual(operation["operation_id"], "neck-cutout")
        self.assertEqual(operation["kind"], "CUTOUT")
        self.assertEqual(operation["piece_id"], "base")
        self.assertEqual(operation["hole_digest"], cutout["digest"])
        self.assertEqual(operation["hole_points_cm"], cutout["points"])
        self.assertEqual(operation["contour_edge_lineage"],
                         cutout["contour_edge_lineage"])
        self.assertEqual(operation["state"], "PROPOSED")

        baseline = structure_preview.generate_preview(
            band(), candidate_id="cutout-candidate")
        self.assertNotEqual(preview["mesh"]["faces"],
                            baseline["mesh"]["faces"])
        self.assertNotEqual(preview["preview_digest"],
                            baseline["preview_digest"])
        self.assertEqual(preview["topology"]["nonmanifold_edges"], [])
        self.assertEqual(preview["topology"]["degenerate_face_indices"], [])

        boundary = preview["construction_boundaries"][0]
        self.assertEqual(boundary["kind"], "CUTOUT_INNER_BOUNDARY")
        self.assertEqual(boundary["piece_id"], "base")
        self.assertEqual(boundary["state"], "PROPOSED")
        self.assertEqual(boundary["contour_edge_lineage"],
                         cutout["contour_edge_lineage"])
        self.assertTrue(boundary["mesh_edges"])
        degree = {}
        mesh_edge_uses = {}
        for face in preview["mesh"]["faces"]:
            for first, second in ((face[0], face[1]), (face[1], face[2]),
                                  (face[2], face[0])):
                edge = tuple(sorted((first, second)))
                mesh_edge_uses[edge] = mesh_edge_uses.get(edge, 0) + 1
        for first, second in boundary["mesh_edges"]:
            degree[first] = degree.get(first, 0) + 1
            degree[second] = degree.get(second, 0) + 1
            self.assertEqual(mesh_edge_uses[tuple(sorted((first, second)))], 1)
        self.assertTrue(all(value == 2 for value in degree.values()))
        approximation = boundary["approximation"]
        self.assertTrue(approximation["conservative"])
        self.assertGreater(approximation["removed_triangle_count"], 0)
        self.assertGreater(approximation["retained_triangle_count"], 0)
        self.assertGreater(approximation["error_upper_bound_cm"], 0.0)
        self.assertTrue(approximation["limits"])
        piece_cutout = preview["parts"][0]["inner_cutouts"][0]
        self.assertEqual(piece_cutout["pattern_cutout_digest"], cutout["digest"])
        self.assertEqual(piece_cutout["state"], "PROPOSED")
        self.assertFalse(preview["claims"]["manufacturing_ready"])

    def test_cutout_outside_and_degenerate_polygons_remain_typed_refusals(self):
        cases = [
            ([[-6.0, 1.0], [-4.0, 1.0], [-4.0, 2.0], [-6.0, 2.0]],
             "UNKNOWN_CUTOUT_NOT_STRICTLY_INSIDE"),
            ([[-1.0, 1.0], [0.0, 1.0], [1.0, 1.0]],
             "UNKNOWN_CUTOUT_SELF_INTERSECTION"),
        ]
        for polygon, verdict in cases:
            with self.subTest(verdict=verdict):
                structure = band({
                    "operation_id": "invalid-cutout",
                    "kind": "CUTOUT",
                    "source": {"node_id": "base", "port_id": "right"},
                    "parameters": {"closed_polygon": polygon},
                })
                preview = structure_preview.generate_preview(
                    structure, candidate_id="invalid-cutout-candidate")
                self.assertEqual(preview["verdict"], verdict)
                self.assertEqual(preview["candidate_id"],
                                 "invalid-cutout-candidate")
                self.assertEqual(preview["state"], "PROPOSED")
                self.assertNotIn("mesh", preview)

    def test_cutout_after_split_keeps_disjoint_piece_ownership(self):
        structure = band(split_operation())
        structure["operations"].append({
            "operation_id": "right-hole",
            "kind": "CUTOUT",
            "source": {"node_id": "base", "port_id": "right"},
            "prerequisites": ["panel-split"],
            "parameters": {
                "closed_polygon": [[1.0, 1.0], [2.0, 1.0],
                                   [2.0, 2.0], [1.0, 2.0]],
            },
        })
        preview = structure_preview.generate_preview(
            structure, candidate_id="split-cutout-candidate")
        self.assertEqual(preview["verdict"], "ANSWER")
        self.assert_pattern_identity(
            structure, "split-cutout-candidate", preview)
        parts = {part["piece_id"]: part for part in preview["parts"]}
        self.assertEqual(set(parts), {"right-panel", "left-panel"})
        self.assertEqual(len(parts["right-panel"]["inner_cutouts"]), 1)
        self.assertNotIn("inner_cutouts", parts["left-panel"])
        right_faces = set(parts["right-panel"]["face_indices"])
        left_faces = set(parts["left-panel"]["face_indices"])
        self.assertFalse(right_faces & left_faces)
        self.assertEqual(right_faces | left_faces,
                         set(range(len(preview["mesh"]["faces"]))))
        self.assertEqual(
            [row["kind"] for row in preview["geometry_operations"]],
            ["SPLIT", "CUTOUT"])
        self.assertEqual(
            preview["construction_boundaries"][1]["piece_id"],
            "right-panel")

    def test_cutout_mesh_empty_projection_and_open_boundary_are_typed(self):
        part = {
            "node_id": "panel", "source_node_id": "panel",
            "piece_id": "panel", "kind": "GORE", "layer": 0,
            "vertex_range": [0, 3], "face_range": [0, 1],
            "face_indices": [0], "state": "PROPOSED",
        }
        record = {
            "operation_id": "all", "kind": "CUTOUT", "state": "PROPOSED",
            "piece_id": "panel", "contour_id": "all:inner-0",
            "points": [[-1.0, -1.0], [2.0, -1.0], [2.0, 2.0], [-1.0, 2.0]],
            "contour_edge_lineage": [{"source": "a", "target": "b"}] * 4,
            "digest": "pattern-cutout",
        }

        def invoke(outline):
            vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0)]
            faces = [(0, 1, 2)]
            vertex_layers = [0, 0, 0]
            face_layers = [0]
            face_nodes = ["panel"]
            face_pieces = ["panel"]
            parts = [copy.deepcopy(part)]
            return structure_preview._apply_cutout_mesh(
                vertices=vertices, faces=faces,
                vertex_layers=vertex_layers, face_layers=face_layers,
                face_node_ids=face_nodes, face_piece_ids=face_pieces,
                parts=parts, source_part=parts[0], source_outline=outline,
                record=record)

        _, empty_error = invoke([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(empty_error,
                         "UNKNOWN_STRUCTURE_PREVIEW_CUTOUT_REMOVES_ALL_FACES")
        _, projection_error = invoke([[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]])
        self.assertEqual(projection_error,
                         "UNKNOWN_STRUCTURE_PREVIEW_CUTOUT_PROJECTION")

        structure = band({
            "operation_id": "too-wide-for-preview",
            "kind": "CUTOUT",
            "source": {"node_id": "base", "port_id": "right"},
            "parameters": {
                "closed_polygon": [[-4.4, 0.6], [4.4, 0.6],
                                   [4.4, 3.4], [-4.4, 3.4]],
                "minimum_clearance_cm": 0.3,
            },
        })
        boundary_failure = structure_preview.generate_preview(
            structure, candidate_id="boundary-refusal", radial_segments=3)
        self.assertEqual(boundary_failure["verdict"],
                         "UNKNOWN_STRUCTURE_PREVIEW_CUTOUT_BOUNDARY")
        self.assertNotIn("mesh", boundary_failure)


if __name__ == "__main__":
    unittest.main()
