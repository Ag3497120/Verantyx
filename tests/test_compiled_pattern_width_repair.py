#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

from photoloset import repair_width


def rectangle(piece_id, width, height, *, layer=0, transforms=None):
    points = [[0.0, 0.0], [width, 0.0],
              [width, height], [0.0, height]]
    edges = {}
    for index, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        edges[f"e{index}"] = {
            "points": [a, b],
            "length": ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5,
        }
    return {
        "piece_id": piece_id,
        "name": piece_id,
        "node_id": piece_id,
        "primitive_kind": "BODY_SHELL",
        "role": "body_wrap",
        "layer": layer,
        "outline": points,
        "edges": edges,
        "area_cm2": width * height,
        "cut_count": 1,
        "grain": {"direction": "parallel_to_height", "state": "PROPOSED"},
        "transforms": list(transforms or []),
        "provenance": {"source_node": piece_id},
    }


class CompiledPatternWidthRepairTests(unittest.TestCase):
    def pattern(self):
        side_fold = {"kind": "FOLD", "address": "e1", "direction": "in"}
        hem_pleat = {"kind": "PLEAT", "address": "e0", "count": 2}
        return {
            "verdict": "ANSWER",
            "schema": "garment.compiled-pattern.v1",
            "candidate_id": "candidate-a",
            "candidate_state": "PROPOSED",
            "structure_digest": "structure-digest",
            "digest": "old-pattern-digest",
            "pieces": [
                rectangle("bodice", 120.0, 60.0,
                          transforms=[side_fold, hem_pleat]),
                rectangle("overlay", 30.0, 40.0, layer=1),
            ],
            "seams": [
                {"operation_id": "close-bodice", "kind": "PROCEDURAL_CLOSURE",
                 "a": {"piece_id": "bodice", "edge": "e1"},
                 "b": {"piece_id": "bodice", "edge": "e3"},
                 "state": "PROPOSED"},
                {"operation_id": "join-hem", "kind": "JOIN",
                 "a": {"piece_id": "bodice", "edge": "e0"},
                 "b": {"piece_id": "overlay", "edge": "e2"},
                 "state": "PROPOSED"},
            ],
            "layers": [
                {"operation_id": "side-overlay", "kind": "LAYER",
                 "a": {"piece_id": "bodice", "edge": "e1"},
                 "b": {"piece_id": "overlay", "edge": "e1"},
                 "state": "PROPOSED"},
                {"piece_id": "bodice", "layer": 0},
            ],
            "transforms": [
                {"operation_id": "side-fold", "piece_id": "bodice",
                 **side_fold},
                {"operation_id": "hem-pleat", "piece_id": "bodice",
                 **hem_pleat},
            ],
            "features": [
                {"feature_id": "side-pocket", "kind": "POCKET",
                 "piece_id": "bodice", "edge": "e1", "state": "PROPOSED"},
                {"feature_id": "opening", "kind": "OPENING",
                 "piece_id": "bodice", "state": "PROPOSED"},
            ],
            "seam_checks": [
                {"operation_id": "close-bodice", "sewable": True},
                {"operation_id": "join-hem", "sewable": True},
            ],
            "manufacturing_ready": True,
            "remaining_gates": [],
            "provenance": {"method": "fixture"},
        }

    def repair(self):
        return repair_width.repair(
            self.pattern(), fabric_width_cm=90.0,
            cut={"bodice": 1, "overlay": 1}, seam_allowance_cm=0.0)

    def test_split_uses_stable_ids_and_rewires_resolvable_topology(self):
        first = self.repair()
        second = self.repair()
        self.assertEqual(first["verdict"], "ANSWER")
        self.assertEqual(first["after"]["verdict"], "ANSWER")
        pattern = first["pattern"]
        children = [piece for piece in pattern["pieces"]
                    if piece.get("split_from_piece_id") == "bodice"]
        self.assertEqual(
            [piece["piece_id"] for piece in children],
            ["bodice::width-split:right", "bodice::width-split:left"])
        self.assertEqual(
            [piece["piece_id"] for piece in children],
            [piece["piece_id"] for piece in second["pattern"]["pieces"]
             if piece.get("split_from_piece_id") == "bodice"])
        self.assertEqual(pattern["digest"], second["pattern"]["digest"])
        self.assertNotEqual(pattern["digest"], "old-pattern-digest")
        self.assertEqual(children[0]["grain"]["direction"],
                         "parallel_to_height")
        self.assertEqual(children[0]["role"], "body_wrap")
        self.assertEqual(children[0]["source_node_id"], "bodice")

        closure = next(row for row in pattern["seams"]
                       if row["operation_id"] == "close-bodice")
        self.assertEqual(closure["a"]["piece_id"],
                         "bodice::width-split:right")
        self.assertEqual(closure["b"]["piece_id"],
                         "bodice::width-split:left")
        self.assertEqual(closure.get("active", True), True)

        layer = next(row for row in pattern["layers"]
                     if row.get("operation_id") == "side-overlay")
        self.assertEqual(layer["a"]["piece_id"],
                         "bodice::width-split:right")
        direct_layers = [row for row in pattern["layers"]
                         if row.get("layer") == 0 and "operation_id" not in row]
        self.assertEqual({row["piece_id"] for row in direct_layers},
                         {"bodice::width-split:right",
                          "bodice::width-split:left"})

        fold = next(row for row in pattern["transforms"]
                    if row["operation_id"] == "side-fold")
        self.assertEqual(fold["piece_id"], "bodice::width-split:right")
        pocket = next(row for row in pattern["features"]
                      if row["feature_id"] == "side-pocket")
        self.assertEqual(pocket["piece_id"], "bodice::width-split:right")

        split_seam = next(row for row in pattern["seams"]
                          if row["kind"] == "WIDTH_SPLIT_JOIN")
        self.assertEqual(
            {split_seam["a"]["piece_id"], split_seam["b"]["piece_id"]},
            {"bodice::width-split:right", "bodice::width-split:left"})
        self.assertEqual(split_seam["a"]["edge"], repair_width.SPLIT_EDGE)
        rewire = pattern["piece_id_rewire"]["bodice"]
        self.assertEqual(rewire["edge_rewire"]["e1"]["piece_id"],
                         "bodice::width-split:right")
        self.assertEqual(rewire["edge_rewire"]["e0"]["status"],
                         "UNKNOWN_EDGE_REWIRE_REQUIRED")

    def test_unrewirable_edges_remain_typed_review_and_never_ready(self):
        pattern = self.repair()["pattern"]
        hem = next(row for row in pattern["seams"]
                   if row["operation_id"] == "join-hem")
        self.assertEqual(hem["state"], "REVIEW")
        self.assertFalse(hem["active"])
        self.assertEqual(hem["topology_status"],
                         "UNKNOWN_EDGE_REWIRE_REQUIRED")
        self.assertNotIn("piece_id", hem["a"])
        self.assertEqual(hem["a"]["source_piece_id"], "bodice")

        pleat = next(row for row in pattern["transforms"]
                     if row["operation_id"] == "hem-pleat")
        self.assertEqual(pleat["rewire_status"],
                         "UNKNOWN_EDGE_REWIRE_REQUIRED")
        self.assertFalse(pleat["active"])
        opening = next(row for row in pattern["features"]
                       if row["feature_id"] == "opening")
        self.assertEqual(opening["rewire_status"],
                         "REVIEW_PIECE_SCOPE_AFTER_SPLIT")
        self.assertFalse(opening["active"])

        review_check = next(row for row in pattern["seam_checks"]
                            if row["operation_id"] == "join-hem")
        self.assertFalse(review_check["sewable"])
        self.assertEqual(review_check["state"], "REVIEW")
        self.assertEqual(pattern["topology_status"], "REVIEW")
        self.assertGreaterEqual(len(pattern["unresolved_topology"]), 3)
        self.assertFalse(pattern["manufacturing_ready"])
        self.assertIn("review width-split seam placement",
                      pattern["remaining_gates"][-1])


if __name__ == "__main__":
    unittest.main()
