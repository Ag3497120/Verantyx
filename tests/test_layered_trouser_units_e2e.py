#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused lineage regression for two independent trouser layers."""

import copy
import unittest

from photoloset import garment_engineering_review
from photoloset import structure_sewing_plan
from photoloset import structure_to_pattern
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


UNITS = (("leggings", 0, 38.0), ("outer-pants", 1, 44.0))


def _part(part_id, kind, dimensions, *, unit, layer, placement, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": layer,
        "placement": placement,
        "garment_unit": unit,
        "dimensions": dimensions,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front image proposal for {part_id}",
            "breaks_when": "another view or user review rejects this structure",
        },
    }
    row.update(semantics)
    return row


def _layered_trouser_parts():
    parts = []
    for unit, layer, circumference in UNITS:
        left = f"{unit}-left"
        right = f"{unit}-right"
        parts.extend([
            _part(
                left, "TUBE",
                {"length_cm": 90.0,
                 "circumference_cm": circumference},
                unit=unit, layer=layer, placement="left leg",
                side="left", shape="trouser_leg",
                detail_role="trouser_leg", quantity=1),
            _part(
                right, "TUBE",
                {"length_cm": 90.0,
                 "circumference_cm": circumference},
                unit=unit, layer=layer, placement="right leg",
                side="right", shape="trouser_leg",
                detail_role="trouser_leg", quantity=1),
            _part(
                f"{unit}-gusset", "GUSSET",
                {"length_cm": 16.0, "width_cm": 8.0},
                unit=unit, layer=layer, placement="centre crotch",
                attached_to=[left, right], side="center", shape="trousers",
                detail_role="trouser_gusset", quantity=1),
        ])
    return parts


class LayeredTrouserUnitsE2ETests(unittest.TestCase):
    def test_two_independent_layers_reach_cut_and_sewing_plan_with_lineage(self):
        parts = _layered_trouser_parts()
        requested_ids = ("layered-trousers-a", "layered-trousers-b")
        completion = complete_parts_ir({
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "candidates": [
                {"candidate_id": candidate_id, "state": "PROPOSED",
                 "parts": copy.deepcopy(parts)}
                for candidate_id in requested_ids
            ],
        })
        self.assertEqual("PROPOSED", completion["verdict"], completion)
        self.assertEqual(set(requested_ids), {
            row["candidate_id"] for row in completion["candidates"]})
        self.assertFalse(completion["authority"]["observed"])
        self.assertFalse(completion["authority"]["approved"])
        self.assertIsNot(completion.get("manufacturing_ready"), True)

        topology = apply_parts_ir_topology(completion)
        self.assertEqual("PROPOSED", topology["verdict"], topology)
        self.assertEqual(completion["candidate_count"],
                         topology["candidate_count"])
        self.assertFalse(topology["authority"]["observed"])
        self.assertFalse(topology["authority"]["approved"])
        self.assertIsNot(topology.get("manufacturing_ready"), True)

        completed_by_id = {
            row["candidate_id"]: row for row in completion["candidates"]}
        topology_by_id = {
            row["candidate_id"]: row for row in topology["candidates"]}
        for candidate_id in requested_ids:
            with self.subTest(candidate_id=candidate_id):
                completed = completed_by_id[candidate_id]
                topologized = topology_by_id[candidate_id]
                self.assertEqual(completed["structure_digest"],
                                 topologized["source_structure_digest"])

                compiled = structure_to_pattern.compile(
                    topologized, candidate_id=candidate_id)
                self.assertEqual("ANSWER", compiled["verdict"], compiled)
                self.assertEqual(candidate_id, compiled["candidate_id"])
                self.assertEqual("PROPOSED", compiled["candidate_state"])
                self.assertEqual(topologized["structure_digest"],
                                 compiled["structure_digest"])

                pieces = compiled["pieces"]
                piece_ids = [piece["piece_id"] for piece in pieces]
                self.assertEqual(10, len(piece_ids))
                self.assertEqual(10, len(set(piece_ids)))
                self.assertTrue(all(piece["cut_count"] == 1
                                    for piece in pieces))

                unit_for_piece = {
                    piece["piece_id"]:
                    piece["attributes"]["garment_unit"]
                    for piece in pieces
                }
                layer_for_unit = {unit: layer for unit, layer, _ in UNITS}
                for piece in pieces:
                    unit = unit_for_piece[piece["piece_id"]]
                    self.assertEqual(layer_for_unit[unit], piece["layer"])
                self.assertEqual({unit: 5 for unit, _, _ in UNITS}, {
                    unit: sum(value == unit
                              for value in unit_for_piece.values())
                    for unit, _, _ in UNITS
                })

                seams = compiled["seams"]
                seam_ids = [seam["operation_id"] for seam in seams]
                self.assertEqual(20, len(seam_ids))
                self.assertEqual(20, len(set(seam_ids)))
                for seam in seams:
                    joined_units = {
                        unit_for_piece[seam[side]["piece_id"]]
                        for side in ("a", "b")
                    }
                    self.assertEqual(1, len(joined_units), seam)

                connectivity = garment_engineering_review.assembly_connectivity(
                    compiled)
                self.assertEqual("ANSWER", connectivity["verdict"])
                self.assertEqual(2, len(connectivity["components"]))
                component_units = {
                    frozenset(unit_for_piece[piece_id]
                              for piece_id in component)
                    for component in connectivity["components"]
                }
                self.assertEqual({frozenset({"leggings"}),
                                  frozenset({"outer-pants"})},
                                 component_units)

                sewing = structure_sewing_plan.plan(compiled)
                self.assertEqual("ANSWER", sewing["order_verdict"], sewing)
                self.assertEqual("REVIEW_MANUFACTURING_CHOICES_REQUIRED",
                                 sewing["verdict"])
                self.assertEqual(candidate_id, sewing["candidate_id"])
                self.assertEqual("PROPOSED", sewing["candidate_state"])
                self.assertEqual(compiled["structure_digest"],
                                 sewing["structure_digest"])
                self.assertEqual(compiled["digest"],
                                 sewing["source_pattern_digest"])
                self.assertEqual(candidate_id,
                                 sewing["provenance"]["candidate_id"])
                self.assertEqual(compiled["digest"], sewing["provenance"]
                                 ["source_pattern_digest"])
                self.assertEqual(len(sewing["steps"]),
                                 len({step["step_id"]
                                      for step in sewing["steps"]}))

                self.assertFalse(compiled["manufacturing_ready"])
                self.assertFalse(sewing["manufacturing_ready"])
                self.assertFalse(sewing["manufacturing_certified"])
                self.assertFalse(sewing["claims"]["seam_strength_proven"])
                self.assertIn("not a manufacturing", sewing["not_a_certificate"])


if __name__ == "__main__":
    unittest.main()
