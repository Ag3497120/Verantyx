#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest
from collections.abc import Mapping

from photoloset.parts_ir_completion import (
    bounded_preview_profile,
    complete_parts_ir,
)
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline
from photoloset.parts_ir_topology import apply_parts_ir_topology


def _body():
    return {
        "part_id": "body",
        "kind": "BODY_SHELL",
        "layer": 0,
        "placement": "front torso",
        "visible_basis": {
            "state": "PROPOSED",
            "basis": "front body region proposed by the vision model",
            "breaks_when": "another view rejects the proposed body region",
        },
        "dimensions": {"height_cm": 44.0, "circumference_cm": 92.0},
        "garment_unit": "look",
    }


def _opening(closure_detail, opening_topology):
    return {
        "part_id": "opening",
        "kind": "OPENING",
        "layer": 0,
        "placement": {"region": "center_back", "starts_at": "neck"},
        "visible_basis": {
            "state": "PROPOSED",
            "basis": "vision model proposed an unseen rear construction candidate",
            "breaks_when": "a rear or inside view contradicts the proposal",
        },
        "dimensions": {"length_cm": 35.0},
        "garment_unit": "look",
        "attached_to": "body",
        "closure_detail": closure_detail,
        "opening_topology": opening_topology,
    }


def _candidates(opening):
    rows = []
    for suffix in ("a", "b"):
        parts = copy.deepcopy([_body(), opening])
        for part in parts:
            part["part_id"] += f"-{suffix}"
        parts[1]["attached_to"] = f"body-{suffix}"
        rows.append({"candidate_id": f"opening-{suffix}", "parts": parts})
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": rows,
    }


def _authority_words(value):
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _authority_words(child)
    elif isinstance(value, list):
        for child in value:
            yield from _authority_words(child)
    elif isinstance(value, str) and value in {
            "PROPOSED", "OBSERVED", "APPROVED"}:
        yield value


class PartsIROpeningSemanticsTests(unittest.TestCase):
    def test_mapping_semantics_reach_feature_and_sewing_plan_as_proposed(self):
        opening = _opening(
            {"type": "center_back_zip", "finish": "facing",
             "state": "PROPOSED"},
            {"kind": "center_back_slit", "state": "PROPOSED"},
        )
        source = _candidates(opening)
        before = copy.deepcopy(source)
        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile())

        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])
        self.assertEqual(source, before)
        for candidate in result["candidates"]:
            with self.subTest(candidate_id=candidate["candidate_id"]):
                completed_opening = next(
                    node for node in candidate["completion_candidate"]["nodes"]
                    if node["kind"] == "OPENING")
                completed_attributes = completed_opening["attributes"]
                self.assertEqual(completed_attributes["closure_detail"]["type"],
                                 "center_back_zip")
                self.assertEqual(completed_attributes["closure_detail"]["state"],
                                 "PROPOSED")
                self.assertEqual(
                    completed_attributes["parts_ir_semantics"]["placement"]["state"],
                    "PROPOSED")
                self.assertEqual(
                    completed_attributes["parts_ir_semantics"]["closure_detail"]["state"],
                    "PROPOSED")

                feature = candidate["flat_pattern"]["features"][0]
                self.assertEqual(feature["kind"], "OPENING")
                self.assertEqual(feature["state"], "PROPOSED")
                self.assertFalse(feature["observed"])
                self.assertEqual(feature["placement"],
                                 {"region": "center_back",
                                  "starts_at": "neck"})
                self.assertEqual(feature["closure_detail"]["type"],
                                 "center_back_zip")
                self.assertEqual(feature["closure_detail"]["state"],
                                 "PROPOSED")
                self.assertEqual(feature["opening_topology"]["kind"],
                                 "center_back_slit")
                self.assertEqual(feature["opening_topology"]["state"],
                                 "PROPOSED")
                self.assertFalse(
                    feature["opening_topology"]["geometry_cut_created"])
                self.assertEqual(
                    feature["opening_topology"]["topology_resolution"]["state"],
                    "PROPOSED")
                self.assertTrue(feature["target_piece_id"])
                self.assertEqual(feature["semantic_authority"]["state"],
                                 "PROPOSED")
                self.assertFalse(feature["semantic_authority"]["observed"])
                self.assertNotIn("OBSERVED", set(_authority_words(feature)))
                self.assertNotIn("APPROVED", set(_authority_words(feature)))

                plan = candidate["sewing_plan"]
                self.assertEqual(plan["order_verdict"], "ANSWER")
                opening_step = next(
                    step for step in plan["steps"]
                    if step["action"] == "finish_opening")
                closure_step = next(
                    step for step in plan["steps"]
                    if step["action"] == "close_intrinsic_wrap")
                self.assertEqual(opening_step["detail"]["closure_detail"]["type"],
                                 "center_back_zip")
                self.assertEqual(opening_step["detail"]["state"], "PROPOSED")
                self.assertIn(opening_step["step_id"],
                              closure_step["depends_on"])
                self.assertEqual(
                    closure_step["detail"]["closure_detail"]["state"],
                    "PROPOSED")
                review_codes = {row["verdict"] for row in plan["reviews"]}
                self.assertNotIn("REVIEW_OPENING_METHOD_REQUIRED", review_codes)
                self.assertNotIn("REVIEW_OPENING_PIECE_ADDRESS_REQUIRED",
                                 review_codes)
                self.assertFalse(plan["manufacturing_ready"])
                self.assertFalse(plan["manufacturing_certified"])

    def test_string_semantics_are_preserved_inside_typed_proposal_topology(self):
        source = _candidates(_opening(
            "proposed side zip",
            "proposed center-back slit",
        ))
        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile())
        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])
        for candidate in result["candidates"]:
            feature = candidate["flat_pattern"]["features"][0]
            self.assertEqual(feature["closure_detail"], "proposed side zip")
            self.assertEqual(feature["opening_topology"]["proposal"],
                             "proposed center-back slit")
            self.assertEqual(feature["opening_topology"]["state"], "PROPOSED")
            self.assertFalse(feature["opening_topology"]["geometry_cut_created"])
            self.assertEqual(
                feature["semantic_evidence"]["closure_detail"]["state"],
                "PROPOSED")

    def test_observed_or_approved_model_semantics_are_refused(self):
        for field, state in (("closure_detail", "OBSERVED"),
                             ("opening_topology", "APPROVED")):
            with self.subTest(field=field, state=state):
                opening = _opening(
                    {"type": "zip", "state": "PROPOSED"},
                    {"kind": "slit", "state": "PROPOSED"},
                )
                opening[field]["state"] = state
                result = complete_parts_ir(
                    _candidates(opening),
                    preview_profile=bounded_preview_profile())
                self.assertEqual(
                    result["verdict"],
                    "UNKNOWN_PARTS_IR_AUTHORITY_ESCALATION")

    def test_topology_rejects_tampered_completed_semantic_authority(self):
        completed = complete_parts_ir(
            _candidates(_opening(
                {"type": "zip", "state": "PROPOSED"},
                {"kind": "slit", "state": "PROPOSED"},
            )),
            preview_profile=bounded_preview_profile())
        self.assertEqual(completed["verdict"], "PROPOSED")
        opening = next(node for node in completed["candidates"][0]["nodes"]
                       if node["kind"] == "OPENING")
        opening["attributes"]["closure_detail"]["state"] = "OBSERVED"
        result = apply_parts_ir_topology(completed)
        self.assertEqual(
            result["verdict"],
            "UNKNOWN_PARTS_TOPOLOGY_AUTHORITY_ESCALATION")


if __name__ == "__main__":
    unittest.main()
