#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import pattern_manufacturing_bundle
from photoloset import structure_sewing_plan
from photoloset import structure_to_pattern as compiler


def band(operation):
    return {
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
        "operations": [operation],
    }


class StructureToPatternGeometricOperationTests(unittest.TestCase):
    def test_split_emits_real_children_join_and_partial_edge_remap(self):
        spec = band({
            "operation_id": "panel-split",
            "kind": "SPLIT",
            "source": {"node_id": "base", "port_id": "right"},
            "parameters": {
                "line": [[0.0, -1.0], [0.0, 5.0]],
                "new_piece_ids": {"negative": "right-panel",
                                  "positive": "left-panel"},
            },
        })
        result = compiler.compile(spec, candidate_id="split-a")
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual({piece["piece_id"] for piece in result["pieces"]},
                         {"left-panel", "right-panel"})
        operation = result["geometry_operations"][0]
        self.assertEqual(operation["kind"], "SPLIT")
        e0 = next(row for row in operation["source_edge_lineage"]
                  if row["source"] == "base/e0")
        self.assertEqual(len(e0["targets"]), 2)
        self.assertTrue(all(row["relation"] == "PARTIAL_EDGE_REMAP"
                            for row in e0["targets"]))
        e1 = next(row for row in operation["source_edge_lineage"]
                  if row["source"] == "base/e1")
        self.assertEqual(e1["targets"][0]["relation"],
                         "FULL_EDGE_PRESERVED")
        seam = next(row for row in result["seams"]
                    if row["operation_id"] == "panel-split")
        self.assertEqual(seam["kind"], "JOIN")
        self.assertEqual(seam["construction_role"], "SPLIT_REJOIN")
        self.assertTrue(next(row for row in result["seam_checks"]
                             if row["operation_id"] == "panel-split")[
                                 "geometrically_sewable"])

        manufacturing = pattern_manufacturing_bundle.build(
            result, seam_allowance_cm=1.0)
        self.assertEqual(manufacturing["verdict"], "ANSWER")
        sewing = structure_sewing_plan.plan(result)
        self.assertIn(sewing["verdict"],
                      ("ANSWER", "REVIEW_MANUFACTURING_CHOICES_REQUIRED"))

    def test_split_refuses_when_a_live_port_becomes_only_partial_edges(self):
        spec = band({
            "operation_id": "horizontal-split",
            "kind": "SPLIT",
            "source": {"node_id": "base", "port_id": "right"},
            "parameters": {
                "line": [[-6.0, 2.0], [6.0, 2.0]],
                "new_piece_ids": {"negative": "lower", "positive": "upper"},
            },
        })
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_SPLIT_PORT_ADDRESS_PARTIAL")
        self.assertTrue(result["address_remap"])

    def test_mirror_requires_numeric_axis_side_counts_id_and_exact_lineage(self):
        operation = {
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
        result = compiler.compile(band(operation), candidate_id="mirror-a")
        self.assertEqual(result["verdict"], "ANSWER")
        mirrored = next(piece for piece in result["pieces"]
                        if piece["piece_id"] == "mirrored")
        self.assertGreaterEqual(min(point[0] for point in mirrored["outline"]), 5.0)
        record = result["geometry_operations"][0]
        self.assertEqual(record["state"], "PROPOSED")
        self.assertEqual(len(record["source_edge_lineage"]), 4)

        missing = copy.deepcopy(operation)
        del missing["parameters"]["source_edge_lineage"]
        self.assertEqual(compiler.compile(band(missing))["verdict"],
                         "UNKNOWN_SOURCE_EDGE_LINEAGE_REQUIRED")
        wrong = copy.deepcopy(operation)
        wrong["parameters"]["source_edge_lineage"]["e0"] = "e0"
        self.assertEqual(compiler.compile(band(wrong))["verdict"],
                         "UNKNOWN_SOURCE_EDGE_LINEAGE_MISMATCH")

    def test_asymmetry_generates_explicit_deformed_piece_without_relabelling(self):
        operation = {
            "operation_id": "asymmetric-right",
            "kind": "ASYMMETRY",
            "source": {"node_id": "base", "port_id": "right"},
            "parameters": {
                "side": "right",
                "new_piece_id": "right-asymmetric",
                "source_cut_count": 1,
                "new_cut_count": 1,
                "vertex_offsets_cm": [[0.0, 0.0], [2.0, 0.0],
                                      [1.0, 1.0], [0.0, 1.0]],
                "source_edge_lineage": {
                    "e0": "e0", "e1": "e1", "e2": "e2", "e3": "e3",
                },
            },
        }
        result = compiler.compile(band(operation), candidate_id="asym-a")
        self.assertEqual(result["verdict"], "ANSWER")
        source = next(piece for piece in result["pieces"]
                      if piece["piece_id"] == "base")
        derived = next(piece for piece in result["pieces"]
                       if piece["piece_id"] == "right-asymmetric")
        self.assertNotEqual(source["outline"], derived["outline"])
        self.assertEqual(derived["provenance"]["method"],
                         "explicit per-vertex asymmetric displacement")
        self.assertEqual(result["geometry_operations"][0]["state"], "PROPOSED")

        no_change = copy.deepcopy(operation)
        no_change["parameters"]["vertex_offsets_cm"] = [[0.0, 0.0]] * 4
        self.assertEqual(compiler.compile(band(no_change))["verdict"],
                         "UNKNOWN_ASYMMETRY_NO_CHANGE")

    def test_cutout_becomes_a_proposed_nested_contour_with_lineage(self):
        spec = band({
            "operation_id": "neck-cutout",
            "kind": "CUTOUT",
            "source": {"node_id": "base", "port_id": "right"},
            "parameters": {"closed_polygon": [[-1, 1], [1, 1], [1, 2], [-1, 2]]},
        })
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"], "ANSWER")
        cutout = result["pieces"][0]["inner_cutouts"][0]
        self.assertEqual(cutout["state"], "PROPOSED")
        self.assertEqual(cutout["piece_id"], "base")
        self.assertEqual(cutout["operation_id"], "neck-cutout")
        self.assertTrue(cutout["contour_edge_lineage"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["address_remap"][0][
            "outer_edge_addresses_changed"])

    def test_derived_piece_refuses_unmapped_prior_sewing_transform(self):
        spec = band({
            "operation_id": "fold-first",
            "kind": "FOLD",
            "source": {"node_id": "base", "port_id": "right"},
            "parameters": {
                "start": [-2.0, 1.0], "end": [2.0, 1.0],
                "direction": "valley",
            },
        })
        spec["operations"].append({
            "operation_id": "mirror-after-fold",
            "kind": "MIRROR",
            "source": {"node_id": "base", "port_id": "right"},
            "prerequisites": ["fold-first"],
            "parameters": {
                "axis": "x", "offset_cm": 5.0,
                "side": "negative_to_positive",
                "new_piece_id": "mirrored",
                "source_cut_count": 1, "new_cut_count": 1,
                "source_edge_lineage": {
                    "e0": "e2", "e1": "e1", "e2": "e0", "e3": "e3",
                },
            },
        })
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_DERIVED_PIECE_TRANSFORM_LINEAGE")


if __name__ == "__main__":
    unittest.main()
