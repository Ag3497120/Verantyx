#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E contract for two explicitly addressed skirt layers on one waist.

The contract is intentionally proposal-only: a front image cannot observe the
rear construction, certify the dimensions, or make the generated pattern
manufacturing-ready.  Every parallel child therefore carries the complete
typed ``waist_stack_*`` proposal contract through topology, pattern and sewing
planning.
"""

import copy
import unittest

from photoloset import structure_sewing_plan
from photoloset import structure_to_pattern
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


CANDIDATE_IDS = ("layered-waist-stack-a", "layered-waist-stack-b")
GARMENT_UNIT = "layered-dress"


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
            "basis": f"front-image structural proposal for {part_id}",
            "breaks_when": (
                "another view, wearer dimensions, or construction review "
                "rejects this proposed waist stack"
            ),
        },
    }
    row.update(semantics)
    return row


def _waist_stack_parts():
    return [
        _part(
            "body", "BODY_SHELL",
            {
                "height_cm": 42.0,
                "circumference_cm": 72.0,
                "bottom_circumference_cm": 72.0,
            },
            layer=0, placement="upper body", quantity=1,
        ),
        _part(
            "skirt-inner", "FLARE",
            {
                "height_cm": 58.0,
                "top_circumference_cm": 72.0,
                "bottom_circumference_cm": 144.0,
            },
            layer=0, placement="inner lower body", attached_to="body",
            detail_role="inner_skirt", quantity=1,
            waist_join_provenance={
                "state": "PROPOSED",
                "basis": "the inner skirt directly shares the proposed waist",
                "breaks_when": (
                    "review selects a separate waistband or different "
                    "calibrated dimensions"
                ),
                "waist_stack_state": "PROPOSED",
                "waist_stack_parent": "body",
                "waist_stack_id": "main-waist-stack",
                "waist_stack_order": 1,
                "waist_stack_construction_mode": "JOIN",
                "not_observed_from_front": True,
                "dimensions_changed": False,
            },
        ),
        _part(
            "skirt-outer", "FLARE",
            {
                "height_cm": 66.0,
                "top_circumference_cm": 108.0,
                "bottom_circumference_cm": 216.0,
            },
            layer=1, placement="outer lower body", attached_to="body",
            detail_role="outer_gathered_skirt", quantity=1,
            waist_join_mode="GATHER",
            waist_join_state="PROPOSED",
            waist_join_provenance={
                "state": "PROPOSED",
                "basis": (
                    "the proposed outer waist is 108 cm and the proposed "
                    "shared finished waist is 72 cm"
                ),
                "breaks_when": (
                    "review selects pleats, ease, a separate waistband, or "
                    "different calibrated dimensions"
                ),
                "source_length_cm": 108.0,
                "target_length_cm": 72.0,
                "waist_stack_state": "PROPOSED",
                "waist_stack_parent": "body",
                "waist_stack_id": "main-waist-stack",
                "waist_stack_order": 2,
                "waist_stack_construction_mode": "GATHER",
                "not_observed_from_front": True,
                "dimensions_changed": False,
            },
        ),
    ]


def _completed_candidates():
    parts = _waist_stack_parts()
    return complete_parts_ir({
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {
                "candidate_id": candidate_id,
                "state": "PROPOSED",
                "parts": copy.deepcopy(parts),
            }
            for candidate_id in CANDIDATE_IDS
        ],
    })


class LayeredWaistStackE2ETests(unittest.TestCase):
    def test_layered_waist_stack_reaches_unique_pattern_and_deterministic_plan(self):
        completion = _completed_candidates()
        topology = apply_parts_ir_topology(completion)
        self.assertEqual("PROPOSED", topology["verdict"], topology)
        self.assertEqual(set(CANDIDATE_IDS), {
            row["candidate_id"] for row in topology["candidates"]
        })

        completed_by_id = {
            row["candidate_id"]: row for row in completion["candidates"]
        }
        topology_by_id = {
            row["candidate_id"]: row for row in topology["candidates"]
        }
        expected_piece_ids = {"body", "skirt-inner", "skirt-outer"}
        expected_waist_operations = {
            "join-waist-body-skirt-inner": "JOIN",
            "gather-waist-skirt-outer-to-body": "GATHER",
        }

        for candidate_id in CANDIDATE_IDS:
            with self.subTest(candidate_id=candidate_id):
                completed = completed_by_id[candidate_id]
                candidate = topology_by_id[candidate_id]
                self.assertEqual("garment.structure.v1", candidate["schema"])
                self.assertEqual("PROPOSED", candidate["state"])
                self.assertEqual(
                    completed["structure_digest"],
                    candidate["source_structure_digest"],
                )

                operations = {
                    row["operation_id"]: row for row in candidate["operations"]
                }
                self.assertEqual(
                    expected_waist_operations,
                    {
                        operation_id: operations[operation_id]["kind"]
                        for operation_id in expected_waist_operations
                    },
                )
                gather = operations["gather-waist-skirt-outer-to-body"]
                self.assertAlmostEqual(1.5, gather["parameters"]["ratio"])
                self.assertEqual("PROPOSED", gather["parameters"]["state"])
                stack_by_operation = {
                    operation_id: operations[operation_id]["parameters"][
                        "waist_stack"
                    ]
                    for operation_id in expected_waist_operations
                }
                self.assertEqual(
                    {"main-waist-stack"},
                    {
                        stack["stack_id"]
                        for stack in stack_by_operation.values()
                    },
                )
                self.assertEqual(
                    {"body"},
                    {
                        stack["parent_node_id"]
                        for stack in stack_by_operation.values()
                    },
                )
                self.assertEqual(
                    {1, 2},
                    {stack["order"] for stack in stack_by_operation.values()},
                )
                self.assertEqual(
                    {"JOIN", "GATHER"},
                    {
                        stack["construction_mode"]
                        for stack in stack_by_operation.values()
                    },
                )
                self.assertTrue(all(
                    stack["state"] == "PROPOSED"
                    and not stack["authority_granted"]
                    and not stack["dimensions_changed"]
                    for stack in stack_by_operation.values()
                ))

                compiled = structure_to_pattern.compile(
                    candidate, candidate_id=candidate_id)
                self.assertEqual("ANSWER", compiled["verdict"], compiled)
                self.assertEqual(candidate_id, compiled["candidate_id"])
                self.assertEqual("PROPOSED", compiled["candidate_state"])
                self.assertEqual(
                    candidate["structure_digest"], compiled["structure_digest"])

                pieces = compiled["pieces"]
                piece_ids = [piece["piece_id"] for piece in pieces]
                self.assertEqual(expected_piece_ids, set(piece_ids))
                self.assertEqual(len(piece_ids), len(set(piece_ids)))
                pieces_by_id = {piece["piece_id"]: piece for piece in pieces}
                self.assertEqual(0, pieces_by_id["skirt-inner"]["layer"])
                self.assertEqual(1, pieces_by_id["skirt-outer"]["layer"])
                self.assertEqual(
                    GARMENT_UNIT,
                    pieces_by_id["skirt-inner"]["attributes"]["garment_unit"],
                )
                self.assertEqual(
                    GARMENT_UNIT,
                    pieces_by_id["skirt-outer"]["attributes"]["garment_unit"],
                )

                seams = compiled["seams"]
                seam_ids = [seam["operation_id"] for seam in seams]
                self.assertEqual(len(seam_ids), len(set(seam_ids)))
                for operation_id, kind in expected_waist_operations.items():
                    seam = next(
                        row for row in seams
                        if row["operation_id"] == operation_id
                    )
                    self.assertEqual(kind, seam["kind"])

                # The only intended inter-piece relations are body-to-inner
                # and body-to-outer.  No seam may connect the two skirt layers
                # directly or cross-address one skirt's operation to the other.
                allowed_pairs = {
                    frozenset(("body", "skirt-inner")),
                    frozenset(("body", "skirt-outer")),
                }
                for seam in seams:
                    if seam["kind"] == "PROCEDURAL_CLOSURE":
                        continue
                    pair = frozenset((
                        seam["a"]["piece_id"], seam["b"]["piece_id"]
                    ))
                    self.assertIn(pair, allowed_pairs, seam)

                first_plan = structure_sewing_plan.plan(compiled)
                second_plan = structure_sewing_plan.plan(compiled)
                self.assertEqual("ANSWER", first_plan["order_verdict"], first_plan)
                self.assertEqual(first_plan["steps"], second_plan["steps"])
                self.assertEqual(
                    [step["step_id"] for step in first_plan["steps"]],
                    [step["step_id"] for step in second_plan["steps"]],
                )
                self.assertEqual(candidate_id, first_plan["candidate_id"])
                self.assertEqual("PROPOSED", first_plan["candidate_state"])
                self.assertEqual(
                    compiled["structure_digest"], first_plan["structure_digest"])
                self.assertEqual(
                    compiled["digest"], first_plan["source_pattern_digest"])
                self.assertEqual(
                    candidate_id, first_plan["provenance"]["candidate_id"])
                self.assertEqual(
                    compiled["digest"],
                    first_plan["provenance"]["source_pattern_digest"],
                )

                self.assertFalse(compiled["manufacturing_ready"])
                self.assertIsNot(compiled.get("manufacturing_certified"), True)
                self.assertFalse(first_plan["manufacturing_ready"])
                self.assertFalse(first_plan["manufacturing_certified"])
                self.assertFalse(first_plan["claims"]["seam_strength_proven"])


if __name__ == "__main__":
    unittest.main()
