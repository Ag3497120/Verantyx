#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def _part(part_id, kind, dimensions, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": semantics.pop("layer", 0),
        "placement": semantics.pop("placement", "front view proposal"),
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"image model proposed {part_id} from the visible front",
            "breaks_when": f"another view or reviewer rejects {part_id}",
        },
        "dimensions": dimensions,
    }
    row.update(semantics)
    return row


def _candidate(candidate_id, parts):
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": parts,
    }


def _complex_dress_parts(*, body_circumference, waist, neck, hem,
                         sleeve_upper, overlay_width, ruffle_length):
    unit = "complex-dress"
    return [
        _part("body", "BODY_SHELL", {
            "height_cm": 43.0,
            "circumference_cm": body_circumference,
            "bottom_circumference_cm": waist,
            "neck_circumference_cm": neck,
        }, garment_unit=unit, quantity=1),
        _part("sleeve", "SLEEVE", {
            "length_cm": 58.0,
            "upper_circumference_cm": sleeve_upper,
            "cuff_circumference_cm": 20.0,
        }, placement="arms", garment_unit=unit, attached_to="body",
              side="bilateral", shape="set_in", quantity=2),
        _part("skirt", "FLARE", {
            "height_cm": 67.0,
            "top_circumference_cm": waist,
            "bottom_circumference_cm": hem,
        }, placement="lower body", garment_unit=unit, attached_to="body",
              shape="flared", quantity=1),
        _part("collar", "COLLAR", {
            "length_cm": neck,
            "width_cm": 7.0,
        }, placement="neck", garment_unit=unit, attached_to="body",
              detail_role="collar", quantity=1),
        _part("overlay", "OVERLAY", {
            "height_cm": 48.0,
            "width_cm": overlay_width,
        }, layer=1, placement="upper back", garment_unit=unit,
              attached_to="body", detail_role="overlay", quantity=1),
        _part("ruffle", "BAND", {
            "length_cm": ruffle_length,
            "width_cm": 10.0,
        }, layer=1, placement="skirt hem", garment_unit=unit,
              attached_to="skirt", detail_role="ruffle", quantity=1),
    ]


def _sleeved_jumpsuit_parts(*, body_circumference, waist,
                            leg_circumference, sleeve_upper):
    unit = "sleeved-jumpsuit"
    return [
        _part("body", "BODY_SHELL", {
            "height_cm": 44.0,
            "circumference_cm": body_circumference,
            "bottom_circumference_cm": waist,
        }, garment_unit=unit, quantity=1),
        _part("sleeve", "SLEEVE", {
            "length_cm": 59.0,
            "upper_circumference_cm": sleeve_upper,
            "cuff_circumference_cm": 21.0,
        }, placement="arms", garment_unit=unit, attached_to="body",
              side="bilateral", shape="set_in", quantity=2),
        _part("leg-left", "TUBE", {
            "length_cm": 101.0,
            "circumference_cm": leg_circumference,
        }, placement="lower left", garment_unit=unit, attached_to="body",
              side="left", shape="trouser_leg", quantity=1),
        _part("leg-right", "TUBE", {
            "length_cm": 101.0,
            "circumference_cm": leg_circumference,
        }, placement="lower right", garment_unit=unit, attached_to="body",
              side="right", shape="trouser_leg", quantity=1),
        _part("crotch", "GUSSET", {
            "length_cm": 18.0,
            "width_cm": 8.0,
        }, placement="crotch", garment_unit=unit,
              attached_to=["leg-left", "leg-right"], side="center",
              detail_role="trouser_gusset", quantity=1),
    ]


def _separate_top_and_skirt_parts(*, body_circumference, top_waist,
                                  skirt_waist, skirt_hem, sleeve_upper, neck):
    return [
        _part("top-body", "BODY_SHELL", {
            "height_cm": 42.0,
            "circumference_cm": body_circumference,
            "bottom_circumference_cm": top_waist,
            "neck_circumference_cm": neck,
        }, garment_unit="separate-top", quantity=1),
        _part("top-sleeve", "SLEEVE", {
            "length_cm": 56.0,
            "upper_circumference_cm": sleeve_upper,
            "cuff_circumference_cm": 20.0,
        }, placement="arms", garment_unit="separate-top",
              attached_to="top-body", side="bilateral", shape="set_in",
              quantity=2),
        _part("top-collar", "COLLAR", {
            "length_cm": neck,
            "width_cm": 6.0,
        }, placement="neck", garment_unit="separate-top",
              attached_to="top-body", detail_role="collar", quantity=1),
        _part("separate-skirt", "FLARE", {
            "height_cm": 61.0,
            "top_circumference_cm": skirt_waist,
            "bottom_circumference_cm": skirt_hem,
        }, placement="separate lower garment", garment_unit="separate-skirt",
              shape="flared", quantity=1),
    ]


class PartsIRPipelineComplexGarmentTests(unittest.TestCase):
    def _run_and_assert(self, candidates, *, expected_piece_count,
                        required_roles):
        source = {
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "candidates": copy.deepcopy(candidates),
        }
        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile())
        self.assertEqual(result["verdict"], "PROPOSED", result.get("failures"))
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["successful_candidate_count"], 2)
        self.assertEqual(result["failed_candidate_count"], 0)
        self.assertEqual(len({row["candidate_id"]
                              for row in result["candidates"]}), 2)
        self.assertEqual(len({row["candidate_digest"]
                              for row in result["candidates"]}), 2)
        self.assertEqual(len({row["structure_digest"]
                              for row in result["candidates"]}), 2)
        self.assertEqual(len({row["preview"]["preview_digest"]
                              for row in result["candidates"]}), 2)
        self.assertEqual(len({row["flat_pattern"]["digest"]
                              for row in result["candidates"]}), 2)

        for row in result["candidates"]:
            with self.subTest(candidate_id=row["candidate_id"]):
                preview = row["preview"]
                pattern = row["flat_pattern"]
                self.assertEqual(row["state"], "PROPOSED")
                self.assertEqual(preview["state"], "PROPOSED")
                self.assertEqual(pattern["candidate_state"], "PROPOSED")
                self.assertTrue(row["artifact_binding"][
                    "same_structure_digest"])
                self.assertEqual(row["structure_digest"],
                                 preview["structure_digest"])
                self.assertEqual(row["structure_digest"],
                                 pattern["structure_digest"])
                self.assertEqual(len(pattern["pieces"]), expected_piece_count)
                self.assertTrue(required_roles.issubset({
                    piece["role"] for piece in pattern["pieces"]
                }))
                self.assertTrue(pattern["seam_checks"])
                self.assertEqual(len(pattern["seam_checks"]),
                                 len(pattern["seams"]))
                self.assertTrue(all(check["geometrically_sewable"]
                                    for check in pattern["seam_checks"]))
                self.assertFalse(preview["claims"]["manufacturing_ready"])
                self.assertFalse(pattern["manufacturing_ready"])
                self.assertFalse(result["claims"]["manufacturing_ready"])
        return result

    def test_complex_layered_ruffled_dress_runs_end_to_end(self):
        candidates = [
            _candidate("complex-dress-a", _complex_dress_parts(
                body_circumference=90.0, waist=78.0, neck=38.0, hem=190.0,
                sleeve_upper=34.0, overlay_width=94.0,
                ruffle_length=250.0)),
            _candidate("complex-dress-b", _complex_dress_parts(
                body_circumference=98.0, waist=84.0, neck=40.0, hem=210.0,
                sleeve_upper=37.0, overlay_width=104.0,
                ruffle_length=276.0)),
        ]
        self._run_and_assert(
            candidates, expected_piece_count=17,
            required_roles={
                "front_bodice", "back_bodice", "set_in_sleeve_left",
                "set_in_sleeve_right", "lower_waist_segment",
                "collar_segment", "gathered_ruffle_segment", "overlay",
            })

    def test_sleeved_jumpsuit_combines_bodice_and_trouser_candidates(self):
        candidates = [
            _candidate("jumpsuit-a", _sleeved_jumpsuit_parts(
                body_circumference=92.0, waist=80.0,
                leg_circumference=40.0, sleeve_upper=34.0)),
            _candidate("jumpsuit-b", _sleeved_jumpsuit_parts(
                body_circumference=100.0, waist=88.0,
                leg_circumference=44.0, sleeve_upper=38.0)),
        ]
        self._run_and_assert(
            candidates, expected_piece_count=9,
            required_roles={
                "front_bodice", "back_bodice", "set_in_sleeve_left",
                "set_in_sleeve_right", "left_front_leg_panel",
                "left_back_leg_panel", "right_front_leg_panel",
                "right_back_leg_panel", "crotch_gusset",
            })

    def test_separate_top_and_skirt_remain_distinct_garment_units(self):
        candidates = [
            _candidate("separates-a", _separate_top_and_skirt_parts(
                body_circumference=90.0, top_waist=78.0,
                skirt_waist=74.0, skirt_hem=150.0,
                sleeve_upper=34.0, neck=38.0)),
            _candidate("separates-b", _separate_top_and_skirt_parts(
                body_circumference=98.0, top_waist=84.0,
                skirt_waist=80.0, skirt_hem=174.0,
                sleeve_upper=37.0, neck=40.0)),
        ]
        result = self._run_and_assert(
            candidates, expected_piece_count=9,
            required_roles={
                "front_bodice", "back_bodice", "set_in_sleeve_left",
                "set_in_sleeve_right", "collar_segment", "flared_wrap",
            })
        for row in result["candidates"]:
            units = {
                piece.get("attributes", {}).get("garment_unit")
                for piece in row["flat_pattern"]["pieces"]
            }
            self.assertEqual(units, {"separate-top", "separate-skirt"})


if __name__ == "__main__":
    unittest.main()
