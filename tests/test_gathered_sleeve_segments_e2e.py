#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E contract for bilateral gathered lower-sleeve extensions.

The source is an explicit PROPOSED construction hypothesis.  Passing this
test proves deterministic address and dependency preservation only; it never
promotes image inference or prototype geometry to manufacturing approval.
"""
from __future__ import annotations

import unittest

from photoloset import structure_sewing_plan
from photoloset import structure_to_pattern


def gathered_sleeve_candidate() -> dict:
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {
                "node_id": "bodice",
                "kind": "BODY_SHELL",
                "dimensions": {
                    "height_cm": 42.0,
                    "circumference_cm": 92.0,
                    "bottom_circumference_cm": 76.0,
                },
                "attributes": {
                    "garment_unit": "gathered-sleeve-look",
                    "proposal_only": True,
                },
                "ports": [],
            },
            {
                "node_id": "upper-sleeve",
                "kind": "SLEEVE",
                "dimensions": {
                    "length_cm": 31.0,
                    "upper_circumference_cm": 34.0,
                    "cuff_circumference_cm": 20.0,
                },
                "attributes": {
                    "garment_unit": "gathered-sleeve-look",
                    "attached_to": "bodice",
                    "side": "bilateral",
                    "quantity": 2,
                    "proposal_only": True,
                },
                "ports": [{
                    "port_id": "cuff-to-lower",
                    "length_cm": 20.0,
                    "interface": "sleeve-segment",
                    "role": "edge",
                }],
            },
            {
                "node_id": "lower-sleeve",
                "kind": "SLEEVE",
                "dimensions": {
                    "length_cm": 27.0,
                    "upper_circumference_cm": 32.0,
                    "cuff_circumference_cm": 16.0,
                },
                "attributes": {
                    "garment_unit": "gathered-sleeve-look",
                    "attached_to": "upper-sleeve",
                    "sleeve_parent_relation": "GATHER",
                    "placement": "bilateral lower sleeve extension",
                    "side": "bilateral",
                    "quantity": 2,
                    "proposal_only": True,
                },
                "ports": [{
                    "port_id": "upper-to-upper-sleeve",
                    "length_cm": 32.0,
                    "interface": "sleeve-segment",
                    "role": "edge",
                }],
            },
        ],
        "operations": [{
            "operation_id": "gather-lower-to-upper",
            "kind": "GATHER",
            "source": {
                "node_id": "lower-sleeve",
                "port_id": "upper-to-upper-sleeve",
            },
            "target": {
                "node_id": "upper-sleeve",
                "port_id": "cuff-to-lower",
            },
            "parameters": {
                "ratio": 1.6,
                "construction_role": "GATHER_SLEEVE_SEGMENTS",
            },
        }],
    }


class GatheredSleeveSegmentsE2ETests(unittest.TestCase):
    maxDiff = None

    def test_typed_gather_compiles_and_orders_bilateral_segments(self):
        pattern = structure_to_pattern.compile(
            gathered_sleeve_candidate(),
            candidate_id="front-only-gathered-sleeves",
        )
        self.assertEqual(pattern["verdict"], "ANSWER", pattern)
        self.assertEqual(pattern["candidate_state"], "PROPOSED")
        self.assertFalse(pattern["manufacturing_ready"])
        self.assertFalse(pattern["manufacturing_certified"])

        piece_ids = [piece["piece_id"] for piece in pattern["pieces"]]
        seam_ids = [seam["operation_id"] for seam in pattern["seams"]]
        self.assertEqual(len(piece_ids), len(set(piece_ids)))
        self.assertEqual(len(seam_ids), len(set(seam_ids)))
        self.assertIn("upper-sleeve", piece_ids)
        self.assertIn("lower-sleeve", piece_ids)

        expansion = pattern["candidate_specific_expansions"][0]
        self.assertEqual(expansion["state"], "REVIEW_DEFERRED")
        self.assertEqual(expansion["blocking_operations"],
                         ["gather-lower-to-upper"])
        self.assertTrue(expansion[
            "typed_sleeve_segment_gather_preserved"])

        gathered = next(
            seam for seam in pattern["seams"]
            if seam["operation_id"] == "gather-lower-to-upper"
        )
        self.assertEqual(gathered["kind"], "GATHER")
        self.assertEqual(gathered["construction_role"],
                         "GATHER_SLEEVE_SEGMENTS")
        self.assertEqual(gathered["a"],
                         {"piece_id": "lower-sleeve", "edge": "e2"})
        self.assertEqual(gathered["b"],
                         {"piece_id": "upper-sleeve", "edge": "e0"})
        self.assertEqual(gathered["pattern_lineage"]["source"], {
            "node_id": "lower-sleeve",
            "port_id": "upper-to-upper-sleeve",
            "piece_id": "lower-sleeve",
            "edge": "e2",
        })
        self.assertEqual(gathered["pattern_lineage"]["target"], {
            "node_id": "upper-sleeve",
            "port_id": "cuff-to-lower",
            "piece_id": "upper-sleeve",
            "edge": "e0",
        })
        self.assertNotIn("gather-lower-to-upper",
                         {row["operation_id"] for row in pattern["layers"]})

        transform = next(
            row for row in pattern["transforms"]
            if row["operation_id"] == "gather-lower-to-upper"
        )
        self.assertEqual(transform["piece_id"], "lower-sleeve")
        self.assertEqual(transform["address"], "e2")
        self.assertAlmostEqual(transform["cut_length_cm"], 32.0)
        self.assertAlmostEqual(transform["finished_length_cm"], 20.0)
        self.assertAlmostEqual(transform["ratio"], 1.6)
        self.assertEqual(transform["construction_role"],
                         "GATHER_SLEEVE_SEGMENTS")
        check = next(
            row for row in pattern["seam_checks"]
            if row["operation_id"] == "gather-lower-to-upper"
        )
        self.assertTrue(check["geometrically_sewable"])
        self.assertTrue(check["requires_ease_or_gather"])

        plan = structure_sewing_plan.plan(pattern)
        self.assertEqual(plan["order_verdict"], "ANSWER", plan)
        self.assertEqual(plan["verdict"],
                         "REVIEW_MANUFACTURING_CHOICES_REQUIRED")
        self.assertFalse(plan["manufacturing_ready"])
        self.assertFalse(plan["manufacturing_certified"])

        by_id = {step["step_id"]: step for step in plan["steps"]}
        prepare = "prepare:gather:gather-lower-to-upper"
        self.assertIn(prepare, by_id)
        self.assertEqual(by_id[prepare]["action"], "mark_and_form_gathers")
        for side in ("left", "right"):
            step_id = f"seam:gather-lower-to-upper:{side}"
            self.assertIn(step_id, by_id)
            step = by_id[step_id]
            self.assertEqual(step["action"],
                             "gather_and_join_sleeve_segments")
            self.assertEqual(step["detail"]["child_piece"], "lower-sleeve")
            self.assertEqual(step["detail"]["parent_piece"], "upper-sleeve")
            self.assertEqual(step["detail"]["relation_side"], side)
            self.assertEqual(step["detail"]["sleeve_relation_type"],
                             "LOWER_GATHER")
            self.assertIn(prepare, step["depends_on"])
            self.assertLess(by_id[prepare]["step"], step["step"])
            self.assertFalse(step["detail"]["manufacturing_certified"])
        self.assertFalse(any(
            step["action"] in {"apply_outer_layer", "attach_sleeve_layer"}
            for step in plan["steps"]
        ))
        self.assertEqual(
            len([step["step_id"] for step in plan["steps"]]),
            len({step["step_id"] for step in plan["steps"]}),
        )


if __name__ == "__main__":
    unittest.main()
