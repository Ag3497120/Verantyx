#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def part(part_id, kind, dimensions, *, attached_to=None,
         placement="garment", layer=0, **semantics):
    row = {
        "part_id": part_id, "kind": kind, "dimensions": dimensions,
        "layer": layer, "placement": placement,
        "visible_basis": {
            "state": "PROPOSED", "basis": "visible front region",
            "breaks_when": "rear, side or inside construction contradicts it",
        },
        **semantics,
    }
    if attached_to is not None:
        row["attached_to"] = attached_to
    return row


def candidates(parts):
    rows = []
    for suffix in ("a", "b"):
        copied = []
        for source in parts:
            row = copy.deepcopy(source)
            row["part_id"] += f"-{suffix}"
            attached = row.get("attached_to")
            if isinstance(attached, str):
                row["attached_to"] = attached + f"-{suffix}"
            copied.append(row)
        rows.append({"candidate_id": f"accessory-{suffix}", "parts": copied})
    return {"schema": "garment.parts-ir.v1", "state": "PROPOSED",
            "candidates": rows}


def base_parts():
    unit = "look"
    body = part("body", "BODY_SHELL", {
        "height_cm": 44.0, "circumference_cm": 92.0,
        "bottom_circumference_cm": 76.0,
        "neck_circumference_cm": 40.0,
    }, garment_unit=unit)
    sleeve = part("sleeve", "SLEEVE", {
        "length_cm": 58.0, "upper_circumference_cm": 34.0,
        "cuff_circumference_cm": 20.0,
    }, attached_to="body", placement="arms", garment_unit=unit,
       side="bilateral", shape="set_in", quantity=2)
    return unit, body, sleeve


class PartsIRPipelineAccessoryTests(unittest.TestCase):
    def assert_resolved(self, parts, required_roles):
        result = run_parts_ir_pipeline(
            candidates(parts), preview_profile=bounded_preview_profile())
        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])
        for row in result["candidates"]:
            self.assertEqual(row["execution_status"], "SUCCEEDED")
            self.assertTrue(row["artifact_binding"][
                "all_downstream_artifacts_bound"])
            pattern = row["flat_pattern"]
            self.assertTrue(all(check["geometrically_sewable"]
                                for check in pattern["seam_checks"]))
            self.assertTrue(required_roles.issubset(
                {piece["role"] for piece in pattern["pieces"]}))
            self.assertTrue(row["manufacturing_preview"][
                "manufacturing_preview_ready"])
            self.assertEqual(row["sewing_plan"]["order_verdict"], "ANSWER")

    def test_sleeved_hood_and_waist_band_expand_to_real_bodice_edges(self):
        unit, body, sleeve = base_parts()
        hood = part("hood", "HOOD", {
            "height_cm": 38.0, "width_cm": 40.0, "depth_cm": 28.0,
        }, attached_to="body", placement="neck", garment_unit=unit)
        waist = part("waist-band", "BAND", {
            "length_cm": 76.0, "width_cm": 6.0,
        }, attached_to="body", placement="waist", garment_unit=unit,
           detail_role="waistband")
        self.assert_resolved(
            [body, sleeve, hood, waist],
            {"segmented_hood_panel", "fitted_band_segment"})

    def test_bilateral_cuff_uses_expanded_sleeve_cuff_boundary(self):
        unit, body, sleeve = base_parts()
        cuff = part("cuff", "BAND", {
            "length_cm": 20.0, "width_cm": 6.0,
        }, attached_to="sleeve", placement="cuff", garment_unit=unit,
           detail_role="cuff", quantity=2)
        self.assert_resolved([body, sleeve, cuff], {"band"})

    def test_yoke_and_opening_remain_explicit_proposed_features(self):
        unit, body, _ = base_parts()
        yoke = part("yoke", "YOKE", {
            "height_cm": 14.0, "width_cm": 46.0,
        }, attached_to="body", placement="shoulder yoke",
           garment_unit=unit)
        opening = part("opening", "OPENING", {"length_cm": 35.0},
                       attached_to="body", placement="center back",
                       garment_unit=unit)
        result = run_parts_ir_pipeline(
            candidates([body, yoke, opening]),
            preview_profile=bounded_preview_profile())
        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])
        for row in result["candidates"]:
            pattern = row["flat_pattern"]
            self.assertIn("yoke", {piece["role"] for piece in pattern["pieces"]})
            self.assertEqual(pattern["layers"][0]["kind"], "LAYER")
            feature = pattern["features"][0]
            self.assertEqual(feature["kind"], "OPENING")
            self.assertEqual(feature["opening_topology"]["state"], "PROPOSED")
            self.assertFalse(feature["opening_topology"]["geometry_cut_created"])
            self.assertTrue(feature["target_piece_id"])


if __name__ == "__main__":
    unittest.main()
