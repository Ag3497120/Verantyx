#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile, complete_parts_ir
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline
from photoloset.parts_ir_topology import apply_parts_ir_topology


def _visible(label):
    return {
        "state": "PROPOSED",
        "basis": f"front image model proposed {label}",
        "breaks_when": "another view or construction review contradicts it",
    }


def _belt(part_id="belt", *, length=95.0, attached_to=None,
          garment_unit="belt-unit"):
    row = {
        "part_id": part_id,
        "kind": "BAND",
        "layer": 2,
        "placement": "waist belt",
        "visible_basis": _visible(part_id),
        "dimensions": {"length_cm": length, "width_cm": 6.0},
        "detail_role": "standalone_belt",
        "quantity": 1,
    }
    if garment_unit is not None:
        row["garment_unit"] = garment_unit
    if attached_to is not None:
        row["attached_to"] = attached_to
    return row


def _body():
    return {
        "part_id": "body",
        "kind": "BODY_SHELL",
        "layer": 0,
        "placement": "torso",
        "visible_basis": _visible("body"),
        "dimensions": {"height_cm": 44.0, "circumference_cm": 90.0},
        "garment_unit": "dress",
    }


def _request(parts):
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {"candidate_id": "candidate-a", "state": "PROPOSED",
             "parts": copy.deepcopy(parts)},
            {"candidate_id": "candidate-b", "state": "PROPOSED",
             "parts": copy.deepcopy(parts)},
        ],
    }


class StandaloneBandTopologyTests(unittest.TestCase):
    def test_standalone_belt_keeps_geometry_and_defers_closure(self):
        request = _request([_body(), _belt()])
        result = run_parts_ir_pipeline(
            request, preview_profile=bounded_preview_profile())
        self.assertEqual(result["verdict"], "PROPOSED", result.get("failures"))
        for row in result["candidates"]:
            self.assertEqual(row["execution_status"], "SUCCEEDED")
            structure = row["structure"]
            belt = next(node for node in structure["nodes"]
                        if node["node_id"] == "belt")
            review = belt["attributes"]["standalone_band_topology"]
            self.assertEqual(review["state"], "REVIEW")
            self.assertEqual(review["length_cm_preserved"], 95.0)
            self.assertFalse(review["closure_selected"])
            self.assertFalse(any(
                op["source"]["node_id"] == "belt"
                or op["target"]["node_id"] == "belt"
                for op in structure["operations"]
            ))
            pattern_piece = next(
                piece for piece in row["flat_pattern"]["pieces"]
                if piece["node_id"] == "belt")
            xs = [point[0] for point in pattern_piece["outline"]]
            ys = [point[1] for point in pattern_piece["outline"]]
            self.assertAlmostEqual(max(xs) - min(xs), 95.0)
            self.assertAlmostEqual(max(ys) - min(ys), 6.0)
            self.assertFalse(row["manufacturing_preview"]["manufacturing_ready"])

    def test_mismatched_attached_belt_still_fails_closed(self):
        parts = [_body(), _belt(length=95.0, attached_to="body",
                                garment_unit="dress")]
        completed = complete_parts_ir(_request(parts))
        result = apply_parts_ir_topology(completed)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_JOIN_LENGTH_MISMATCH")

    def test_standalone_garter_is_a_review_accessory_not_an_invented_leg_seam(self):
        garter = _belt(part_id="garter", length=44.0,
                       garment_unit="standalone-contact-garter")
        garter["placement"] = "left thigh garter strap"
        garter["detail_role"] = "standalone_garter"
        garter["dimensions"]["width_cm"] = 3.0
        result = run_parts_ir_pipeline(
            _request([_body(), garter]),
            preview_profile=bounded_preview_profile())
        self.assertEqual(result["verdict"], "PROPOSED", result.get("failures"))
        for row in result["candidates"]:
            structure = row["structure"]
            node = next(node for node in structure["nodes"]
                        if node["node_id"] == "garter")
            review = node["attributes"]["standalone_band_topology"]
            self.assertEqual(review["state"], "REVIEW")
            self.assertFalse(review["closure_selected"])
            self.assertFalse(any(
                operation["source"]["node_id"] == "garter"
                or operation["target"]["node_id"] == "garter"
                for operation in structure["operations"]
            ))
            self.assertFalse(row["manufacturing_preview"]["manufacturing_ready"])
            self.assertFalse(row["manufacturing_preview"]["manufacturing_certified"])

    def test_missing_explicit_role_or_unit_does_not_become_loose_belt(self):
        ambiguous = _belt()
        ambiguous.pop("detail_role")
        ambiguous["placement"] = "front decoration"
        completed = complete_parts_ir(_request([_body(), ambiguous]))
        result = apply_parts_ir_topology(completed)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS")

        no_unit = _belt(garment_unit=None)
        completed = complete_parts_ir(_request([_body(), no_unit]))
        result = apply_parts_ir_topology(completed)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS")

    def test_missing_band_dimension_fails_before_topology(self):
        belt = _belt()
        del belt["dimensions"]["width_cm"]
        result = complete_parts_ir(_request([_body(), belt]))
        self.assertNotEqual(result["verdict"], "PROPOSED")


if __name__ == "__main__":
    unittest.main()
