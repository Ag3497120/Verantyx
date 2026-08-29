#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Combination regression for front-image garment geometry proposals.

The matrix deliberately describes outfits as existing parts-IR primitives and
relations.  The human-readable case names are test labels only; they are not
added to the production IR as garment classes.

The test also records current, typed product gaps.  A candidate is not counted
as fully routed merely because its preview mesh exists: flat-pattern and
topology sewing artifacts must be bound to the same structure, or the exact
STOP/REVIEW condition is asserted instead.
"""
from __future__ import annotations

import copy
import json
import unittest

from photoloset.garment_structure import PrimitiveKind
from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


SOURCE_ID = "fixture:front-garment-family-matrix"
SOURCE_DIGEST = "sha256:front-garment-family-matrix"


def _visible(part_id: str) -> dict:
    return {
        "state": "PROPOSED",
        "basis": f"the corrected front boundary proposes {part_id}",
        "breaks_when": "a rear/side view or construction review contradicts it",
        "source_id": SOURCE_ID,
        "source_digest": SOURCE_DIGEST,
        "view": "front",
    }


def _part(part_id: str, kind: str, dimensions: dict, placement: str, *,
          unit: str = "look", layer: int = 0, **semantics) -> dict:
    row = {
        "part_id": part_id,
        "kind": kind,
        "dimensions": copy.deepcopy(dimensions),
        "placement": placement,
        "garment_unit": unit,
        "layer": layer,
        "visible_basis": _visible(part_id),
    }
    row.update(semantics)
    return row


def _body(part_id: str = "body", *, circumference: float = 76.0,
          unit: str = "look", layer: int = 0, **semantics) -> dict:
    return _part(
        part_id, "BODY_SHELL",
        {"height_cm": 44.0, "circumference_cm": circumference},
        "front torso", unit=unit, layer=layer, **semantics,
    )


def _flare(part_id: str = "skirt", *, top: float = 76.0,
           bottom: float = 172.0, unit: str = "look", layer: int = 0,
           **semantics) -> dict:
    return _part(
        part_id, "FLARE",
        {"height_cm": 64.0, "top_circumference_cm": top,
         "bottom_circumference_cm": bottom},
        "lower body", unit=unit, layer=layer, **semantics,
    )


def _leg(part_id: str, side: str, *, unit: str,
         attached_to: str | None = None) -> dict:
    semantics = {"side": side, "shape": "trouser_leg"}
    if attached_to is not None:
        semantics["attached_to"] = attached_to
    return _part(
        part_id, "TUBE",
        {"length_cm": 99.0, "circumference_cm": 57.0},
        f"{side} lower leg", unit=unit, **semantics,
    )


def _gusset(*, unit: str) -> dict:
    # length_cm is the explicitly addressed crotch join length for both legs.
    return _part(
        "crotch-gusset", "GUSSET",
        {"length_cm": 57.0, "width_cm": 8.0},
        "centre crotch", unit=unit, side="center", shape="crotch_gusset",
        attached_to=["leg-left", "leg-right"],
    )


def _candidate(candidate_id: str, parts: list[dict]) -> dict:
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": copy.deepcopy(parts),
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": "unobserved rear construction alternative",
            "basis": "one front image does not observe the rear",
            "breaks_when": "a rear or side view is supplied",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": "bounded material-property range",
            "basis": "appearance does not measure material mechanics",
            "breaks_when": "a swatch or calibrated material test is supplied",
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _request(case_id: str, parts: list[dict]) -> dict:
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            _candidate(f"{case_id}-a", parts),
            _candidate(f"{case_id}-b", parts),
        ],
    }


def _ornament(part_id: str, kind: str, dimensions: dict) -> dict:
    return _part(
        part_id, kind, dimensions, "front ornament", layer=2,
        quantity=1, grain_direction="BIAS_45", seam_allowance_cm=0.8,
        attached_to="body", target_port_id="center-front",
    )


def _cases() -> dict[str, dict]:
    return {
        "plain-dress": {
            "outcome": "PASS",
            "parts": [_body(), _flare(attached_to="body")],
            "operations": {"JOIN"},
        },
        "separated-top-skirt": {
            "outcome": "PASS",
            "parts": [
                _body(circumference=90.0, unit="upper-unit"),
                _flare(unit="lower-unit"),
            ],
            "operations": set(),
        },
        "two-tube-gusset-trousers": {
            "outcome": "PASS",
            "parts": [
                _leg("leg-left", "left", unit="lower-unit"),
                _leg("leg-right", "right", unit="lower-unit"),
                _gusset(unit="lower-unit"),
            ],
            "operations": {"JOIN"},
        },
        "body-two-tube-gusset-jumpsuit": {
            "outcome": "PASS",
            "parts": [
                _body(circumference=114.0),
                _leg("leg-left", "left", unit="look", attached_to="body"),
                _leg("leg-right", "right", unit="look", attached_to="body"),
                _gusset(unit="look"),
            ],
            "operations": {"JOIN"},
        },
        "top-two-sleeves-collar-opening": {
            "outcome": "STOP",
            "reason": "UNKNOWN_BODICE_SLEEVE_BRIDGE_CARDINALITY",
            "stage": "structure_to_pattern",
            "parts": [
                _body(circumference=96.0),
                _part(
                    "sleeve-left", "SLEEVE",
                    {"length_cm": 58.0, "upper_circumference_cm": 36.0,
                     "cuff_circumference_cm": 22.0},
                    "left arm", side="left", attached_to="body",
                ),
                _part(
                    "sleeve-right", "SLEEVE",
                    {"length_cm": 58.0, "upper_circumference_cm": 36.0,
                     "cuff_circumference_cm": 22.0},
                    "right arm", side="right", attached_to="body",
                ),
                _part(
                    "collar", "COLLAR",
                    {"length_cm": 38.0, "width_cm": 8.0},
                    "neck", attached_to="body",
                ),
                _part(
                    "front-opening", "OPENING", {"length_cm": 40.0},
                    "centre front", attached_to="body",
                    opening_topology={
                        "state": "PROPOSED", "position": "center-front",
                    },
                ),
            ],
        },
        "layered-underdress-overlay-cape": {
            "outcome": "PASS",
            "parts": [
                _body("under-body", unit="under-unit"),
                _flare("under-skirt", unit="under-unit",
                       attached_to="under-body"),
                _part(
                    "cape-overlay", "OVERLAY",
                    {"height_cm": 48.0, "width_cm": 64.0},
                    "shoulder cape overlay", unit="outer-unit", layer=1,
                    attached_to="under-body",
                ),
            ],
            "operations": {"JOIN", "LAYER"},
        },
        "ruffle-gather-band": {
            "outcome": "PASS",
            "parts": [
                _body(), _flare(attached_to="body"),
                _part(
                    "hem-ruffle", "BAND",
                    {"length_cm": 210.0, "width_cm": 12.0},
                    "hem lower edge", layer=1, attached_to="skirt",
                    detail_role="ruffle",
                ),
            ],
            "operations": {"JOIN", "GATHER"},
        },
        "pleated-gored-skirt": {
            "outcome": "REVIEW_PLEAT_GORE_TOPOLOGY",
            "parts": [
                _part(
                    f"gore-{index}", "GORE",
                    {"length_cm": 64.0, "top_width_cm": 10.0,
                     "bottom_width_cm": 28.0},
                    f"gore panel {index}", unit="lower-unit",
                    detail_role="pleated",
                )
                for index in range(1, 5)
            ],
        },
        "bow-rosette-tie-flap-ornaments": {
            "outcome": "PASS_ORNAMENT_DOWNSTREAM",
            "parts": [
                _body(circumference=92.0),
                _ornament("bow", "BOW", {
                    "body_length_cm": 24.0, "body_width_cm": 8.0,
                    "knot_length_cm": 7.0, "knot_width_cm": 3.0,
                }),
                _ornament("rosette", "ROSETTE", {
                    "strip_length_cm": 72.0, "strip_width_cm": 4.0,
                    "finished_inner_length_cm": 18.0,
                }),
                _ornament("tie", "TIE", {
                    "length_cm": 35.0, "top_width_cm": 7.0,
                    "tip_width_cm": 2.0,
                }),
                _ornament("flap", "FLAP", {
                    "attachment_width_cm": 12.0, "depth_cm": 8.0,
                    "outer_width_cm": 9.0,
                }),
            ],
        },
    }


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


class FrontGarmentFamilyMatrixTests(unittest.TestCase):
    maxDiff = None

    def _run(self, case_id: str, parts: list[dict]) -> tuple[dict, dict]:
        source = _request(case_id, parts)
        frozen = copy.deepcopy(source)
        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile(),
            radial_segments=8,
        )
        self.assertEqual(source, frozen)
        self.assertFalse(result["provenance"]["input_mutated"])
        return source, result

    def _assert_source_proposals(self, source: dict, row: dict) -> None:
        candidate = next(item for item in source["candidates"]
                         if item["candidate_id"] == row["candidate_id"])
        self.assertEqual(candidate["rear_hypothesis"]["state"], "PROPOSED")
        self.assertEqual(candidate["material_hypothesis"]["state"], "PROPOSED")
        self.assertFalse(candidate["manufacturing_ready"])
        structure = row.get("structure")
        if not isinstance(structure, dict):
            return
        for node in structure["nodes"]:
            visible = node["attributes"]["visible_basis"]
            self.assertEqual(visible["state"], "PROPOSED")
            self.assertEqual(visible["source_id"], SOURCE_ID)
            self.assertEqual(visible["source_digest"], SOURCE_DIGEST)
            self.assertTrue(visible["not_measured_from_image"])

    def _assert_no_class_enum(self, row: dict) -> None:
        for value in _walk(row):
            if isinstance(value, dict):
                self.assertNotIn("garment_class", value)
                self.assertNotIn("garment_type", value)
        structure = row.get("structure")
        if isinstance(structure, dict):
            primitive_values = {kind.value for kind in PrimitiveKind}
            self.assertTrue(all(node["kind"] in primitive_values
                                for node in structure["nodes"]))

    def _assert_mesh_and_bound_artifacts(self, row: dict) -> None:
        preview = row["preview"]
        pattern = row["flat_pattern"]
        self.assertEqual(preview["verdict"], "ANSWER", preview)
        self.assertTrue(preview["mesh"]["vertices"])
        self.assertTrue(preview["mesh"]["faces"])
        self.assertEqual(pattern["verdict"], "ANSWER", pattern)
        self.assertTrue(pattern["pieces"])
        self.assertTrue(all(piece["outline"] for piece in pattern["pieces"]))
        self.assertTrue(row["manufacturing_preview"]["pieces"])
        self.assertEqual(row["sewing_plan"]["order_verdict"], "ANSWER")
        binding = row["artifact_binding"]
        self.assertTrue(binding["same_structure_digest"])
        self.assertTrue(binding["all_downstream_artifacts_bound"])
        self.assertEqual(row["structure_digest"], preview["structure_digest"])
        self.assertEqual(row["structure_digest"], pattern["structure_digest"])

    def _assert_never_manufacturing_ready(self, value) -> None:
        for item in _walk(value):
            if not isinstance(item, dict):
                continue
            if "manufacturing_ready" in item:
                self.assertIs(item["manufacturing_ready"], False)
            if "manufacturing_certified" in item:
                self.assertIs(item["manufacturing_certified"], False)

    def test_existing_primitive_combinations_reach_artifacts_or_typed_gap(self):
        for case_id, spec in _cases().items():
            with self.subTest(case_id=case_id, outcome=spec["outcome"]):
                source, result = self._run(case_id, spec["parts"])
                self.assertEqual(result["candidate_count"], 2)
                self.assertEqual(
                    len({row["candidate_digest"]
                         for row in result["candidates"]}), 2,
                )
                self._assert_never_manufacturing_ready(result)

                for row in result["candidates"]:
                    self._assert_source_proposals(source, row)
                    self._assert_no_class_enum(row)
                    outcome = spec["outcome"]

                    if outcome == "STOP":
                        self.assertEqual(row["execution_status"], "REFUSED")
                        self.assertEqual(row["verdict"], spec["reason"])
                        self.assertEqual(row["failures"][0]["stage"],
                                         spec["stage"])
                        # The 3D combination exists, but no absent flat pattern
                        # or sewing topology is disguised as a usable artifact.
                        self.assertEqual(row["preview"]["verdict"], "ANSWER")
                        self.assertTrue(row["preview"]["mesh"]["faces"])
                        self.assertEqual(row["flat_pattern"]["verdict"],
                                         spec["reason"])
                        self.assertNotIn("pieces", row["flat_pattern"])
                        self.assertIsNone(row["manufacturing_preview"])
                        self.assertIsNone(row["sewing_plan"])
                        continue

                    self.assertEqual(row["execution_status"], "SUCCEEDED")
                    self._assert_mesh_and_bound_artifacts(row)

                    if outcome == "PASS":
                        operation_kinds = {
                            operation["kind"]
                            for operation in row["structure"]["operations"]
                        }
                        self.assertEqual(operation_kinds, spec["operations"])
                        if "GATHER" in operation_kinds:
                            actions = {step["action"]
                                       for step in row["sewing_plan"]["steps"]}
                            self.assertIn("mark_and_form_gathers", actions)
                            self.assertIn("attach_gathered_section", actions)
                        continue

                    if outcome == "REVIEW_PLEAT_GORE_TOPOLOGY":
                        # detail_role is preserved, but it is not silently
                        # treated as a PLEAT transform or a sewn gore assembly.
                        self.assertEqual(row["structure"]["operations"], [])
                        self.assertFalse(any(
                            transform.get("kind") == "PLEAT"
                            for piece in row["flat_pattern"]["pieces"]
                            for transform in piece.get("transforms", [])
                        ))
                        review_codes = {
                            review["verdict"]
                            for review in row["sewing_plan"]["reviews"]
                        }
                        self.assertIn("REVIEW_NO_CONSTRUCTION_OPERATIONS",
                                      review_codes)
                        self.assertEqual(row["sewing_plan"]["steps"], [])
                        continue

                    self.assertEqual(outcome,
                                     "PASS_ORNAMENT_DOWNSTREAM")
                    ornaments = row["structure"]["ornament_artifacts"]
                    self.assertEqual(ornaments["readiness"], "MATERIALIZED")
                    self.assertEqual(
                        {item["kind"] for item in ornaments["result_manifest"]},
                        {"BOW", "ROSETTE", "TIE", "FLAP"},
                    )
                    self.assertTrue(ornaments["pattern_pieces"])
                    flat_ids = {piece["piece_id"]
                                for piece in row["flat_pattern"]["pieces"]}
                    ornament_ids = {piece["piece_id"]
                                    for piece in ornaments["pattern_pieces"]}
                    self.assertTrue(ornament_ids <= flat_ids)
                    manufacturing_ids = {
                        piece["piece_id"]
                        for piece in row["manufacturing_preview"]["pieces"]
                    }
                    self.assertTrue(ornament_ids <= manufacturing_ids)
                    sewing_operations = {
                        step.get("operation_id")
                        for step in row["sewing_plan"]["steps"]
                    }
                    self.assertTrue({
                        intent["intent_id"]
                        for intent in ornaments["seam_intents"]
                    } <= sewing_operations)
                    self.assertEqual(
                        row["flat_pattern"]["ornament_artifacts"]
                        ["candidate_digest"],
                        row["candidate_digest"],
                    )

                json.dumps(result, ensure_ascii=False, allow_nan=False)

    def test_part_input_order_does_not_change_candidate_artifacts(self):
        spec = _cases()["ruffle-gather-band"]
        _, first = self._run("order-stability", spec["parts"])
        _, second = self._run(
            "order-stability", list(reversed(spec["parts"])))
        first_by_id = {row["candidate_id"]: row for row in first["candidates"]}
        second_by_id = {row["candidate_id"]: row
                        for row in second["candidates"]}
        self.assertEqual(set(first_by_id), set(second_by_id))
        for candidate_id in sorted(first_by_id):
            before, after = first_by_id[candidate_id], second_by_id[candidate_id]
            self.assertEqual(before["candidate_digest"],
                             after["candidate_digest"])
            self.assertEqual(before["structure_digest"],
                             after["structure_digest"])
            self.assertEqual(before["preview"]["preview_digest"],
                             after["preview"]["preview_digest"])
            self.assertEqual(before["flat_pattern"]["digest"],
                             after["flat_pattern"]["digest"])
            self.assertEqual(before["sewing_plan"]["digest"],
                             after["sewing_plan"]["digest"])

    def test_one_failed_candidate_does_not_erase_a_successful_sibling(self):
        good = _candidate(
            "sibling-good", [_body(), _flare(attached_to="body")])
        bad_parts = [_body(circumference=-1.0)]
        bad = _candidate("sibling-bad", bad_parts)
        request = {
            "schema": "garment.parts-ir.v1", "state": "PROPOSED",
            "candidates": [good, bad],
        }
        result = run_parts_ir_pipeline(
            request, preview_profile=bounded_preview_profile(),
            radial_segments=8,
        )
        self.assertEqual(result["verdict"], "UNRESOLVED")
        self.assertEqual(result["successful_candidate_count"], 1)
        self.assertEqual(result["failed_candidate_count"], 1)
        by_id = {row["candidate_id"]: row for row in result["candidates"]}
        self.assertEqual(by_id["sibling-good"]["execution_status"],
                         "SUCCEEDED")
        self._assert_mesh_and_bound_artifacts(by_id["sibling-good"])
        self.assertEqual(by_id["sibling-bad"]["execution_status"],
                         "REFUSED")
        self.assertEqual(by_id["sibling-bad"]["verdict"],
                         "UNKNOWN_PARTS_IR_INVALID_DIMENSION")
        self.assertIsNone(by_id["sibling-bad"]["preview"])
        self.assertFalse(result["provenance"]["candidate_failures_hidden"])

    def test_candidate_batch_order_does_not_change_named_candidate_geometry(self):
        # Explicit vision candidates have semantic ids. Completion variants
        # are bound by a stable id rank, so JSON row ordering cannot change a
        # candidate's geometry or downstream artifacts.
        parts = [_body(circumference=92.0)]
        request = _request("candidate-order", parts)
        first = run_parts_ir_pipeline(
            request, preview_profile=bounded_preview_profile(),
            radial_segments=8,
        )
        swapped = copy.deepcopy(request)
        swapped["candidates"].reverse()
        second = run_parts_ir_pipeline(
            swapped, preview_profile=bounded_preview_profile(),
            radial_segments=8,
        )
        first_by_id = {row["candidate_id"]: row for row in first["candidates"]}
        second_by_id = {row["candidate_id"]: row
                        for row in second["candidates"]}
        for candidate_id in first_by_id:
            before, after = first_by_id[candidate_id], second_by_id[candidate_id]
            self.assertEqual(
                before["completion_candidate"]["completion_variant"],
                after["completion_candidate"]["completion_variant"],
            )
            self.assertEqual(before["candidate_digest"],
                             after["candidate_digest"])
            self.assertEqual(before["structure_digest"],
                             after["structure_digest"])
            self.assertEqual(before["flat_pattern"]["digest"],
                             after["flat_pattern"]["digest"])


if __name__ == "__main__":
    unittest.main()
