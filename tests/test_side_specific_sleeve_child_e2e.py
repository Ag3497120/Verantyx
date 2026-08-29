#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exact-side child attachments must survive bilateral sleeve expansion."""
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def _part(part_id, kind, dimensions, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": semantics.pop("layer", 0),
        "placement": semantics.pop("placement", "visible front"),
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front image proposes {part_id}",
            "breaks_when": "another view or construction review rejects it",
        },
        "dimensions": dimensions,
    }
    row.update(semantics)
    return row


def _candidate(candidate_id, side="left"):
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": [
            _part("p-00", "BODY_SHELL", {
                "height_cm": 44.0,
                "circumference_cm": 94.0,
            }, garment_unit="unit-00"),
            _part("p-01", "SLEEVE", {
                "length_cm": 58.0,
                "upper_circumference_cm": 34.0,
                "cuff_circumference_cm": 20.0,
            }, layer=1, placement="bilateral arms", garment_unit="unit-00",
                  attached_to="p-00", side="bilateral", quantity=2,
                  detail_role="bilateral_set_in_sleeve"),
            _part("p-02", "BAND", {
                "length_cm": 48.0,
                "width_cm": 7.0,
            }, layer=2, placement=f"{side} cuff lower edge",
                  garment_unit="unit-00", attached_to="p-01", side=side,
                  quantity=1, detail_role="ruffle"),
        ],
    }


def _run(side="left"):
    source = {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            _candidate("candidate-00", side),
            _candidate("candidate-01", side),
        ],
    }
    return run_parts_ir_pipeline(
        source, preview_profile=bounded_preview_profile(), radial_segments=8)


class SideSpecificSleeveChildE2ETests(unittest.TestCase):
    def test_left_and_right_children_bind_to_the_exact_expanded_sleeve(self):
        for side in ("left", "right"):
            with self.subTest(side=side):
                result = _run(side)
                self.assertEqual("PROPOSED", result["verdict"], result)
                for candidate in result["candidates"]:
                    self.assertEqual("SUCCEEDED", candidate["execution_status"])
                    pattern = candidate["flat_pattern"]
                    sleeve_pieces = {
                        piece["piece_id"] for piece in pattern["pieces"]
                        if piece.get("source_node_id") == "p-01"
                    }
                    self.assertEqual({"p-01:left", "p-01:right"}, sleeve_pieces)
                    gather = next(
                        seam for seam in pattern["seams"]
                        if seam["operation_id"] == "gather-p-02-to-p-01")
                    self.assertEqual("p-02", gather["a"]["piece_id"])
                    self.assertEqual(f"p-01:{side}", gather["b"]["piece_id"])
                    self.assertEqual(side, gather["relation_side"])
                    expansion = next(
                        row for row in pattern["candidate_specific_expansions"]
                        if row["kind"] == "BODICE_SET_IN_SLEEVE_BRIDGE")
                    self.assertEqual(
                        side,
                        expansion["side_bound_external_gathers"][0]["side"])
                    self.assertFalse(
                        expansion["external_gather_side_inferred"])

    def test_unaddressed_side_remains_a_typed_refusal(self):
        source = {
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "candidates": [
                _candidate("candidate-00", "left"),
                _candidate("candidate-01", "left"),
            ],
        }
        for candidate in source["candidates"]:
            candidate["parts"][2].pop("side")
        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile(), radial_segments=8)
        self.assertEqual("UNRESOLVED", result["verdict"])
        self.assertTrue(all(
            row["execution_status"] == "REFUSED"
            for row in result["candidates"]))
        self.assertTrue(all(
            any(failure["code"].startswith("UNKNOWN_")
                for failure in row["failures"])
            for row in result["candidates"]))


if __name__ == "__main__":
    unittest.main()
