#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression contract for side-addressed decorative GORE children."""
from __future__ import annotations

import copy
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def _part(part_id, kind, dimensions, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": semantics.pop("layer", 0),
        "placement": semantics.pop("placement", "visible surface"),
        "garment_unit": "unit-00",
        "dimensions": dimensions,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": "model-supplied typed proposal",
            "breaks_when": "reviewed evidence or construction analysis rejects it",
        },
    }
    row.update(semantics)
    return row


def _base_parts():
    return [
        _part(
            "p-00",
            "BODY_SHELL",
            {
                "height_cm": 42.0,
                "circumference_cm": 92.0,
                "bottom_circumference_cm": 76.0,
            },
        ),
        _part(
            "p-01",
            "FLARE",
            {
                "height_cm": 62.0,
                "top_circumference_cm": 76.0,
                "bottom_circumference_cm": 168.0,
            },
            attached_to="p-00",
            detail_role="base_lower_layer",
        ),
    ]


def _decorative_parts(side):
    return _base_parts() + [
        _part(
            "p-02",
            "GORE",
            {
                "length_cm": 56.0,
                "top_width_cm": 12.0,
                "bottom_width_cm": 42.0,
            },
            layer=2,
            placement=f"{side} decorative layered overlay lower body",
            attached_to="p-01",
            side=side,
            attachment_relation="LAYER",
            detail_role=["decorative", "layered", "overlay", "overskirt"],
            quantity=1,
        ),
    ]


def _structural_parts():
    return _base_parts() + [
        _part(
            "p-02",
            "GORE",
            {
                "length_cm": 56.0,
                "top_width_cm": 12.0,
                "bottom_width_cm": 42.0,
            },
            placement="left structural lower panel",
            attached_to="p-01",
            side="left",
            attachment_relation="JOIN",
            detail_role="structural_gore_panel",
            quantity=1,
        ),
    ]


def _source(parts):
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {
                "candidate_id": f"candidate-{index:02d}",
                "state": "PROPOSED",
                "parts": copy.deepcopy(parts),
            }
            for index in range(2)
        ],
    }


def _run(parts):
    return run_parts_ir_pipeline(
        _source(parts),
        preview_profile=bounded_preview_profile(),
        radial_segments=8,
    )


class SideSpecificGoreOverlayRegressionTests(unittest.TestCase):
    maxDiff = None

    def test_decorative_gore_is_a_separate_cuttable_child_bound_to_parent_side(self):
        for side in ("left", "right"):
            result = _run(_decorative_parts(side))
            self.assertEqual("PROPOSED", result["verdict"], result)

            for candidate in result["candidates"]:
                with self.subTest(
                    side=side,
                    candidate_id=candidate["candidate_id"],
                    contract="separate-child",
                ):
                    self.assertEqual("SUCCEEDED", candidate["execution_status"])

                    operation = next(
                        row for row in candidate["structure"]["operations"]
                        if row["source"]["node_id"] == "p-02"
                    )
                    self.assertEqual("LAYER", operation["kind"])
                    self.assertEqual("p-01", operation["target"]["node_id"])
                    self.assertEqual(
                        "PROPOSED_GORE_OVERLAY",
                        operation["parameters"]["construction_role"],
                    )
                    self.assertFalse(
                        operation["parameters"]["seam_join_created"])

                    pattern_piece = next(
                        row for row in candidate["flat_pattern"]["pieces"]
                        if row["piece_id"] == "p-02"
                    )
                    self.assertEqual("p-02", pattern_piece["source_node_id"])
                    self.assertEqual("GORE", pattern_piece["primitive_kind"])
                    self.assertEqual(1, pattern_piece["cut_count"])
                    self.assertGreater(pattern_piece["area_cm2"], 0.0)

                    manufacturing_piece = next(
                        row
                        for row in candidate["manufacturing_preview"]["pieces"]
                        if row["piece_id"] == "p-02"
                    )
                    self.assertTrue(
                        candidate["manufacturing_preview"][
                            "manufacturing_preview_ready"
                        ]
                    )
                    self.assertEqual("p-02", manufacturing_piece["source_node_id"])
                    self.assertEqual("GORE", manufacturing_piece["primitive_kind"])
                    self.assertEqual(
                        side, manufacturing_piece["attributes"]["side"]
                    )
                    self.assertIn(
                        "overlay",
                        " ".join(
                            manufacturing_piece["attributes"]["detail_role"]
                        ).lower(),
                    )
                    self.assertTrue(manufacturing_piece["sew_line"])
                    self.assertTrue(manufacturing_piece["cut_line"])
                    self.assertFalse(
                        candidate["manufacturing_preview"]["manufacturing_ready"]
                    )
                    self.assertFalse(
                        candidate["manufacturing_preview"]
                        ["manufacturing_certified"]
                    )

                pattern_layer = next(
                    row for row in candidate["flat_pattern"]["layers"]
                    if row["operation_id"] == operation["operation_id"]
                )
                preview_layer = next(
                    row for row in candidate["preview"]["layer_relations"]
                    if row["operation_id"] == operation["operation_id"]
                )
                sewing_step = next(
                    row for row in candidate["sewing_plan"]["steps"]
                    if row.get("operation_id") == operation["operation_id"]
                )
                stage_relations = {
                    "topology": {
                        "parent": operation["target"]["node_id"],
                        "side": operation["parameters"].get("relation_side"),
                    },
                    "flat-pattern": {
                        "parent": pattern_layer["b"]["piece_id"],
                        "side": pattern_layer.get("relation_side"),
                    },
                    "preview": {
                        "parent": preview_layer["target_node_id"],
                        "side": preview_layer.get("relation_side"),
                    },
                    "sewing-plan": {
                        "parent": sewing_step["detail"]["inner_piece"],
                        "side": sewing_step["detail"].get("relation_side"),
                    },
                }
                for stage, relation in stage_relations.items():
                    with self.subTest(
                        side=side,
                        candidate_id=candidate["candidate_id"],
                        stage=stage,
                        contract="parent-side-binding",
                    ):
                        self.assertEqual("p-01", relation["parent"])
                        self.assertEqual(side, relation["side"])

    def test_structural_gore_without_complete_panel_topology_fails_closed(self):
        result = _run(_structural_parts())

        self.assertEqual("UNRESOLVED", result["verdict"], result)
        self.assertEqual(0, result["successful_candidate_count"])
        self.assertEqual(2, result["failed_candidate_count"])
        for candidate in result["candidates"]:
            with self.subTest(candidate_id=candidate["candidate_id"]):
                self.assertEqual("REFUSED", candidate["execution_status"])
                self.assertEqual(
                    ["UNKNOWN_PARTS_TOPOLOGY_GORE_ATTACHMENT_ROLE"],
                    [failure["code"] for failure in candidate["failures"]],
                )
                self.assertTrue(all(
                    failure["stage"] == "parts_ir_topology"
                    for failure in candidate["failures"]
                ))


if __name__ == "__main__":
    unittest.main()
