#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end regression for a rich front-only, multi-sleeve proposal.

The fixture deliberately keeps every front-visible part identical across the
three candidates.  Only the unobserved rear opening/closure hypothesis varies.
All geometry remains proposal-only; this test does not promote a front image,
preview mannequin, or deterministic sewing order to manufacturing approval.
"""
from __future__ import annotations

import copy
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


PROPOSED = "PROPOSED"
SIDES = {"left", "right"}
SLEEVE_IDS = {"sleeve-upper", "sleeve-lower", "sleeve-outer"}
ORNAMENT_IDS = {"front-bow", "front-rosette", "front-tie"}


def _basis(part_id: str, *, rear: bool = False) -> dict:
    return {
        "state": PROPOSED,
        "basis": (
            f"front image does not observe {part_id}; this is one rear proposal"
            if rear else f"front image proposes visible part {part_id}"
        ),
        "breaks_when": (
            "a rear or inside view contradicts this alternative"
            if rear else "another view or construction review contradicts it"
        ),
    }


def _part(part_id: str, kind: str, dimensions: dict, *, layer: int = 0,
          placement="front", rear: bool = False, **semantics) -> dict:
    return {
        "part_id": part_id,
        "kind": kind,
        "layer": layer,
        "placement": copy.deepcopy(placement),
        "visible_basis": _basis(part_id, rear=rear),
        "dimensions": copy.deepcopy(dimensions),
        **copy.deepcopy(semantics),
    }


def _ornament(part_id: str, kind: str, dimensions: dict) -> dict:
    return _part(
        part_id, kind, dimensions, layer=3,
        placement="visible center-front decoration",
        garment_unit="front-image-look", attached_to="bodice",
        target_port_id="center-front", quantity=1,
        grain_direction="BIAS_45", seam_allowance_cm=0.8,
    )


def _visible_parts() -> list[dict]:
    return [
        _part("bodice", "BODY_SHELL", {
            "height_cm": 44.0,
            "circumference_cm": 96.0,
            "bottom_circumference_cm": 80.0,
            "neck_circumference_cm": 38.0,
        }, garment_unit="front-image-look", quantity=1),
        _part("sleeve-upper", "SLEEVE", {
            "length_cm": 31.0,
            "upper_circumference_cm": 34.0,
            "cuff_circumference_cm": 22.0,
        }, placement="both upper arms", garment_unit="front-image-look",
              attached_to="bodice", side="bilateral", quantity=2,
              shape="set_in"),
        _part("sleeve-lower", "SLEEVE", {
            "length_cm": 27.0,
            "upper_circumference_cm": 22.0,
            "cuff_circumference_cm": 16.0,
        }, placement="bilateral lower sleeve extension",
              garment_unit="front-image-look", attached_to="sleeve-upper",
              attachment_relation="JOIN", side="bilateral", quantity=2,
              shape="lower sleeve extension"),
        _part("sleeve-outer", "SLEEVE", {
            "length_cm": 46.0,
            "upper_circumference_cm": 42.0,
            "cuff_circumference_cm": 30.0,
        }, layer=2, placement="bilateral floating oversleeve",
              garment_unit="front-image-look", attached_to="sleeve-upper",
              attachment_relation="LAYER", side="bilateral", quantity=2,
              shape="oversleeve", detail_role="decorative sleeve"),
        _part("collar", "COLLAR", {
            "length_cm": 38.0,
            "width_cm": 6.0,
        }, layer=1, placement="neckline", garment_unit="front-image-look",
              attached_to="bodice", quantity=1, shape="standing collar"),
        _part("skirt", "FLARE", {
            "height_cm": 66.0,
            "top_circumference_cm": 80.0,
            "bottom_circumference_cm": 196.0,
        }, placement="lower body flared skirt",
              garment_unit="front-image-look", attached_to="bodice",
              quantity=1),
        _part("front-overlay", "OVERLAY", {
            "height_cm": 38.0,
            "width_cm": 54.0,
        }, layer=2, placement="asymmetric front skirt overlay",
              garment_unit="front-image-look", attached_to="skirt",
              quantity=1, detail_role="overlay"),
        _ornament("front-bow", "BOW", {
            "body_length_cm": 24.0,
            "body_width_cm": 8.0,
            "knot_length_cm": 7.0,
            "knot_width_cm": 3.0,
        }),
        _ornament("front-rosette", "ROSETTE", {
            "strip_length_cm": 56.0,
            "strip_width_cm": 4.0,
            "finished_inner_length_cm": 16.0,
        }),
        _ornament("front-tie", "TIE", {
            "length_cm": 36.0,
            "top_width_cm": 7.0,
            "tip_width_cm": 2.0,
        }),
    ]


def _candidate(candidate_id: str, *, rear_design: str, closure_type: str,
               opening_kind: str) -> dict:
    parts = _visible_parts()
    parts.append(_part(
        "rear-opening", "OPENING", {"length_cm": 36.0},
        placement={"region": rear_design, "starts_at": "neck"}, rear=True,
        garment_unit="front-image-look", attached_to="bodice", quantity=1,
        closure_detail={
            "type": closure_type,
            "state": PROPOSED,
            "not_observed_from_front": True,
        },
        opening_topology={
            "kind": opening_kind,
            "state": PROPOSED,
            "not_observed_from_front": True,
        },
    ))
    return {
        "candidate_id": candidate_id,
        "state": PROPOSED,
        "rear_hypothesis": {
            "state": PROPOSED,
            "value": rear_design,
            "basis": "the single front image does not observe the rear",
            "breaks_when": "a rear or side image is supplied",
        },
        "parts": parts,
    }


def _source() -> dict:
    return {
        "schema": "garment.parts-ir.v1",
        "state": PROPOSED,
        "candidates": [
            _candidate(
                "rear-center-zip", rear_design="center_back",
                closure_type="center_back_zip",
                opening_kind="center_back_slit",
            ),
            _candidate(
                "rear-side-zip", rear_design="left_back_side",
                closure_type="concealed_side_zip",
                opening_kind="side_seam_opening",
            ),
            _candidate(
                "rear-keyhole-buttons", rear_design="center_back_keyhole",
                closure_type="button_and_loop",
                opening_kind="keyhole_opening",
            ),
        ],
    }


def _visible_signature(candidate: dict) -> tuple[tuple, ...]:
    """Exclude the deliberately hidden rear OPENING from the front signature."""
    return tuple(sorted(
        (
            part["part_id"], part["kind"], part["layer"],
            repr(part["placement"]), repr(part["dimensions"]),
            part.get("attached_to"), part.get("attachment_relation"),
            part.get("side"), part.get("quantity"),
        )
        for part in candidate["parts"] if part["kind"] != "OPENING"
    ))


class FrontMultilayerSleeveE2ETests(unittest.TestCase):
    maxDiff = None

    def test_front_visible_structure_survives_three_rear_candidates(self):
        source = _source()
        signatures = {_visible_signature(row) for row in source["candidates"]}
        self.assertEqual(len(signatures), 1)
        self.assertTrue(all(
            row["rear_hypothesis"]["state"] == PROPOSED
            for row in source["candidates"]
        ))

        result = run_parts_ir_pipeline(
            source,
            preview_profile=bounded_preview_profile(),
            radial_segments=8,
        )

        self.assertFalse(result["claims"]["manufacturing_ready"])
        self.assertFalse(result["claims"]["manufacturing_certified"])
        self.assertEqual(
            len({row["candidate_digest"] for row in result["candidates"]}),
            3,
        )
        self.assertEqual(
            len({row["structure_digest"] for row in result["candidates"]}),
            3,
        )

        for row in result["candidates"]:
            with self.subTest(candidate_id=row["candidate_id"]):
                self.assertEqual(row["structure_digest"],
                                 row["preview"]["structure_digest"])
                self.assertEqual(row["structure_digest"],
                                 row["flat_pattern"]["structure_digest"])
                self.assertTrue(row["artifact_binding"][
                    "same_structure_digest"])

                opening = next(
                    node for node in row["completion_candidate"]["nodes"]
                    if node["kind"] == "OPENING"
                )
                self.assertEqual(opening["attributes"]["state"], PROPOSED)
                self.assertEqual(
                    opening["attributes"]["closure_detail"]["state"],
                    PROPOSED,
                )
                self.assertEqual(
                    opening["attributes"]["opening_topology"]["state"],
                    PROPOSED,
                )

                sleeve_pieces = [
                    piece for piece in row["flat_pattern"]["pieces"]
                    if piece.get("source_node_id") in SLEEVE_IDS
                ]
                self.assertEqual(
                    {(piece["source_node_id"],
                      piece["attributes"]["derived_side"])
                     for piece in sleeve_pieces},
                    {(node_id, side) for node_id in SLEEVE_IDS
                     for side in SIDES},
                )
                self.assertTrue(all(piece["cut_count"] == 1
                                    for piece in sleeve_pieces))

                preview_parts = {
                    part["source_node_id"]: part
                    for part in row["preview"]["parts"]
                    if part.get("source_node_id") in SLEEVE_IDS
                }
                self.assertEqual(set(preview_parts), SLEEVE_IDS)
                for node_id, part in preview_parts.items():
                    self.assertEqual(
                        {instance["side"] for instance in part["instances"]},
                        SIDES,
                        node_id,
                    )
                relation_coverage = row["preview"][
                    "sleeve_relation_coverage"]
                self.assertEqual(
                    {(item["operation_id"], item["side"])
                     for item in relation_coverage},
                    {(operation_id, side)
                     for operation_id in (
                         "join-sleeve-extension-sleeve-upper-sleeve-lower",
                         "layer-sleeve-outer-on-sleeve-upper",
                     ) for side in SIDES},
                )

                ornament_bundle = row["structure"]["ornament_artifacts"]
                self.assertEqual(
                    {item["ornament_id"]
                     for item in ornament_bundle["result_manifest"]},
                    ORNAMENT_IDS,
                )
                self.assertTrue(row["part_preservation"][
                    "source_node_set_preserved"])
                self.assertEqual(
                    row["part_preservation"]["missing_part_ids"], [])
                self.assertEqual(
                    {part["source_ornament_id"]
                     for part in row["preview"]["parts"]
                     if part.get("geometry_role")
                     == "ORNAMENT_CONSTRUCTION_PROXY"},
                    ORNAMENT_IDS,
                )
                self.assertTrue(
                    {piece["source_ornament_id"]
                     for piece in row["flat_pattern"]["pieces"]
                     if piece.get("source_ornament_id")} >= ORNAMENT_IDS
                )

                for artifact in (
                        row["flat_pattern"], row["manufacturing_preview"],
                        row["sewing_plan"]):
                    self.assertFalse(artifact["manufacturing_ready"])
                    self.assertFalse(artifact["manufacturing_certified"])
                self.assertFalse(
                    row["preview"]["claims"]["manufacturing_ready"])

        self.assertEqual(result["verdict"], PROPOSED, result["failures"])
        self.assertEqual(result["successful_candidate_count"], 3)
        self.assertEqual(result["failed_candidate_count"], 0)
        for row in result["candidates"]:
            with self.subTest(candidate_id=row["candidate_id"]):
                self.assertEqual(row["execution_status"], "SUCCEEDED")
                self.assertTrue(row["artifact_binding"][
                    "all_downstream_artifacts_bound"])
                self.assertTrue(row["part_preservation"][
                    "all_visible_input_parts_preserved"])
                actions = {
                    action: {
                        step["detail"]["relation_side"]
                        for step in row["sewing_plan"]["steps"]
                        if step["action"] == action
                    }
                    for action in (
                        "join_sleeve_segments",
                        "attach_sleeve_layer",
                        "set_root_sleeve",
                    )
                }
                self.assertEqual(actions, {
                    "join_sleeve_segments": SIDES,
                    "attach_sleeve_layer": SIDES,
                    "set_root_sleeve": SIDES,
                })


if __name__ == "__main__":
    unittest.main()
