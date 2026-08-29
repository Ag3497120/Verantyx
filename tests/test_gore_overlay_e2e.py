#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end contract for a proposal-only asymmetric GORE overlay.

A front image cannot establish the rear construction, the attachment method,
or manufacturing fitness.  The proposed GORE therefore remains an independent
cut piece and a non-structural LAYER relation throughout the pipeline.
"""
from __future__ import annotations

import copy
import unittest

from photoloset import structure_preview
from photoloset import structure_sewing_plan
from photoloset import structure_to_pattern
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


GARMENT_UNIT = "asymmetric-gore-overlay-dress"
CANDIDATE_GORE_X = {
    "gore-overlay-left": -14.0,
    "gore-overlay-right": 14.0,
}


def _part(part_id, kind, dimensions, *, layer, placement, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": layer,
        "placement": placement,
        "garment_unit": GARMENT_UNIT,
        "dimensions": dimensions,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front-only structural proposal for {part_id}",
            "breaks_when": (
                "a rear view, wearer measurement, or construction review "
                "rejects this proposed geometry"
            ),
        },
    }
    row.update(semantics)
    return row


def _overlay_parts(gore_x_cm):
    return [
        _part(
            "body", "BODY_SHELL",
            {
                "height_cm": 42.0,
                "circumference_cm": 92.0,
                "bottom_circumference_cm": 76.0,
            },
            layer=0, placement="upper body", quantity=1,
        ),
        _part(
            "skirt", "FLARE",
            {
                "height_cm": 62.0,
                "top_circumference_cm": 76.0,
                "bottom_circumference_cm": 168.0,
            },
            layer=0, placement="lower body", attached_to="body",
            detail_role="base_skirt", quantity=1,
        ),
        _part(
            "asymmetric-gore", "GORE",
            {
                "length_cm": 56.0,
                "top_width_cm": 12.0,
                "bottom_width_cm": 42.0,
                "x_cm": gore_x_cm,
            },
            layer=2,
            placement="asymmetric front decorative skirt overlay",
            attached_to="skirt",
            attachment_relation="LAYER",
            detail_role=["decorative", "asymmetric_overlay"],
            quantity=1,
        ),
    ]


def _completed_overlay_candidates():
    return complete_parts_ir({
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {
                "candidate_id": candidate_id,
                "state": "PROPOSED",
                "parts": _overlay_parts(gore_x_cm),
            }
            for candidate_id, gore_x_cm in CANDIDATE_GORE_X.items()
        ],
    })


class GoreOverlayE2ETests(unittest.TestCase):
    maxDiff = None

    def test_proposed_asymmetric_gore_stays_a_layer_through_all_stages(self):
        completion = _completed_overlay_candidates()
        self.assertEqual(completion["verdict"], "PROPOSED", completion)

        topology = apply_parts_ir_topology(completion)
        self.assertEqual(topology["verdict"], "PROPOSED", topology)
        self.assertEqual(
            {row["candidate_id"] for row in topology["candidates"]},
            set(CANDIDATE_GORE_X),
        )

        preview_digests = set()
        for candidate in topology["candidates"]:
            candidate_id = candidate["candidate_id"]
            with self.subTest(candidate_id=candidate_id):
                gore_relation = next(
                    row for row in candidate["operations"]
                    if row["source"]["node_id"] == "asymmetric-gore"
                )
                self.assertEqual(gore_relation["kind"], "LAYER")
                self.assertEqual(gore_relation["target"]["node_id"], "skirt")
                self.assertEqual(
                    gore_relation["parameters"]["construction_role"],
                    "PROPOSED_GORE_OVERLAY",
                )
                self.assertFalse(
                    gore_relation["parameters"]["seam_join_created"])

                pattern = structure_to_pattern.compile(
                    candidate, candidate_id=candidate_id)
                preview = structure_preview.generate_preview(
                    candidate, candidate_id=candidate_id)
                sewing = structure_sewing_plan.plan(pattern)

                self.assertEqual(pattern["verdict"], "ANSWER", pattern)
                pieces = {row["piece_id"]: row for row in pattern["pieces"]}
                self.assertIn("asymmetric-gore", pieces)
                gore_piece = pieces["asymmetric-gore"]
                self.assertEqual(gore_piece["primitive_kind"], "GORE")
                self.assertEqual(gore_piece["cut_count"], 1)
                self.assertGreater(gore_piece["area_cm2"], 0.0)
                self.assertGreaterEqual(len(gore_piece["outline"]), 4)

                layer_relation = next(
                    row for row in pattern["layers"]
                    if row["operation_id"] == gore_relation["operation_id"]
                )
                self.assertEqual(layer_relation["kind"], "LAYER")
                self.assertEqual(
                    layer_relation["construction_role"],
                    "PROPOSED_GORE_OVERLAY",
                )
                self.assertEqual(layer_relation["a"]["piece_id"],
                                 "asymmetric-gore")
                self.assertEqual(layer_relation["b"]["piece_id"], "skirt")
                self.assertFalse(any(
                    "asymmetric-gore" in {
                        seam["a"]["piece_id"], seam["b"]["piece_id"]
                    }
                    for seam in pattern["seams"]
                ), pattern["seams"])

                self.assertEqual(preview["verdict"], "ANSWER", preview)
                self.assertEqual(preview["candidate_id"], candidate_id)
                self.assertEqual(preview["structure_digest"],
                                 candidate["structure_digest"])
                self.assertTrue(preview["provenance"]["candidate_specific"])
                preview_digests.add(preview["preview_digest"])
                preview_part = next(
                    row for row in preview["parts"]
                    if row["node_id"] == "asymmetric-gore"
                )
                self.assertEqual(preview_part["source_node_id"],
                                 "asymmetric-gore")
                self.assertEqual(preview_part["piece_id"], "asymmetric-gore")
                self.assertEqual(preview_part["layer"], 2)
                self.assertTrue(preview_part["face_indices"])
                self.assertTrue(all(
                    preview["mesh"]["face_node_ids"][face_index]
                    == "asymmetric-gore"
                    for face_index in preview_part["face_indices"]
                ))
                preview_relation = next(
                    row for row in preview["layer_relations"]
                    if row["operation_id"] == gore_relation["operation_id"]
                )
                self.assertEqual(preview_relation, {
                    "operation_id": gore_relation["operation_id"],
                    "source_node_id": "asymmetric-gore",
                    "source_layer": 2,
                    "target_node_id": "skirt",
                    "target_layer": 0,
                })

                self.assertEqual(sewing["order_verdict"], "ANSWER", sewing)
                gore_steps = [
                    row for row in sewing["steps"]
                    if "asymmetric-gore" in row.get("pieces", [])
                ]
                self.assertEqual(
                    [row["action"] for row in gore_steps],
                    ["apply_outer_layer"],
                )
                self.assertFalse(any(
                    row["action"] in {"join_pieces", "join_waist"}
                    for row in gore_steps
                ), gore_steps)

                self.assertFalse(pattern["manufacturing_ready"])
                self.assertIsNot(pattern.get("manufacturing_certified"), True)
                self.assertFalse(preview["claims"]["manufacturing_ready"])
                self.assertIsNot(
                    preview["claims"].get("manufacturing_certified"), True)
                self.assertFalse(sewing["manufacturing_ready"])
                self.assertFalse(sewing["manufacturing_certified"])

        self.assertEqual(len(preview_digests), len(CANDIDATE_GORE_X))

    def test_structural_gore_attachment_fails_closed_without_panel_topology(self):
        structural_parts = _overlay_parts(0.0)
        structural_gore = next(
            row for row in structural_parts
            if row["part_id"] == "asymmetric-gore"
        )
        structural_gore.update({
            "layer": 0,
            "placement": "structural skirt panel",
            "attachment_relation": "JOIN",
            "detail_role": "structural_gore_panel",
        })
        completion = complete_parts_ir({
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "candidates": [
                {
                    "candidate_id": f"structural-gore-{index}",
                    "state": "PROPOSED",
                    "parts": copy.deepcopy(structural_parts),
                }
                for index in (1, 2)
            ],
        })
        self.assertEqual(completion["verdict"], "PROPOSED", completion)

        topology = apply_parts_ir_topology(completion)
        self.assertEqual(
            topology["verdict"],
            "UNKNOWN_PARTS_TOPOLOGY_GORE_ATTACHMENT_ROLE",
            topology,
        )
        self.assertEqual(topology["state"], "UNRESOLVED")
        self.assertNotIn("candidates", topology)
        self.assertIn("complete panel topology", topology["why"])


if __name__ == "__main__":
    unittest.main()
