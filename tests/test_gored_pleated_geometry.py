#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused audits for explicit gored/pleated construction geometry."""
from __future__ import annotations

import copy
import unittest

from photoloset import structure_sewing_plan, structure_to_pattern


def gore(node_id: str = "skirt-gore", *, attributes=None) -> dict:
    return {
        "node_id": node_id,
        "kind": "GORE",
        "dimensions": {
            "length_cm": 64.0,
            "top_width_cm": 12.0,
            "bottom_width_cm": 30.0,
        },
        "attributes": copy.deepcopy(attributes or {}),
        "ports": [{
            "port_id": "top-pleat",
            "length_cm": 12.0,
            "interface": "gore-top",
            "role": "edge",
        }],
    }


def pleat(node_id: str, operation_id: str, *, depth_cm=1.0) -> dict:
    parameters = {"count": 1, "style": "knife"}
    if depth_cm is not None:
        parameters["depth_cm"] = depth_cm
    return {
        "operation_id": operation_id,
        "kind": "PLEAT",
        "source": {"node_id": node_id, "port_id": "top-pleat"},
        "parameters": parameters,
    }


class GoredPleatedGeometryTests(unittest.TestCase):
    def test_ordered_template_materialises_cuttable_repeated_panels(self):
        spec = {
            "schema": "garment.structure.v1",
            "nodes": [gore(attributes={
                "gore_group_id": "lower-skirt",
                "panel_count": 4,
                "panel_order": ["front", "right", "back", "left"],
                "detail_role": "pleated",
            })],
            "operations": [pleat("skirt-gore", "pleat-each-gore")],
        }

        result = structure_to_pattern.compile(spec, candidate_id="front-a")

        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertTrue(result["cuttable_geometric_prototype"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(
            [piece["piece_id"] for piece in result["pieces"]],
            [f"skirt-gore:panel-{index:02d}" for index in range(1, 5)],
        )
        self.assertEqual(
            result["gore_panel_groups"][0]["ordered_piece_ids"],
            [f"skirt-gore:panel-{index:02d}" for index in range(1, 5)],
        )
        joins = [row for row in result["seams"]
                 if row.get("construction_role") == "ORDERED_GORE_PANEL_ASSEMBLY"]
        self.assertEqual(len(joins), 4)
        self.assertTrue(all(row["state"] == "PROPOSED" for row in joins))
        self.assertTrue(all(row["manufacturing_ready"] is False for row in joins))
        self.assertEqual(len(result["transforms"]), 4)
        self.assertTrue(all(row["kind"] == "PLEAT" for row in result["transforms"]))
        self.assertTrue(all(row["depth_cm"] == 1.0 for row in result["transforms"]))
        self.assertTrue(all(row["state"] == "PROPOSED" for row in result["transforms"]))
        self.assertEqual(result["construction_reviews"], [])
        sewing = structure_sewing_plan.plan(result)
        self.assertEqual(sewing["order_verdict"], "ANSWER", sewing)
        self.assertEqual(
            [step["action"] for step in sewing["steps"]].count("form_pleat"),
            4,
        )
        self.assertEqual(
            [step["action"] for step in sewing["steps"]].count("join_pieces"),
            4,
        )
        self.assertFalse(sewing["manufacturing_ready"])

    def test_explicit_per_panel_order_controls_assembly_not_input_order(self):
        nodes = []
        operations = []
        for order in (3, 1, 4, 2):
            node_id = f"gore-{order}"
            nodes.append(gore(node_id, attributes={
                "gore_group_id": "skirt",
                "panel_count": 4,
                "panel_order": order,
                "detail_role": ["pleated"],
            }))
            operations.append(pleat(node_id, f"pleat-{order}", depth_cm=0.75))
        result = structure_to_pattern.compile({
            "schema": "garment.structure.v1",
            "nodes": nodes,
            "operations": operations,
        })

        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual(result["gore_panel_groups"][0]["ordered_piece_ids"],
                         ["gore-1", "gore-2", "gore-3", "gore-4"])
        joins = [row for row in result["seams"]
                 if row.get("construction_role") == "ORDERED_GORE_PANEL_ASSEMBLY"]
        self.assertEqual(
            [(row["a"]["piece_id"], row["b"]["piece_id"]) for row in joins],
            [("gore-1", "gore-2"), ("gore-2", "gore-3"),
             ("gore-3", "gore-4"), ("gore-4", "gore-1")],
        )
        self.assertFalse(result["manufacturing_ready"])

    def test_absent_order_and_pleat_depth_are_never_guessed(self):
        absent = structure_to_pattern.compile({
            "schema": "garment.structure.v1",
            "nodes": [gore(attributes={"detail_role": "pleated"})],
            "operations": [],
        })
        self.assertEqual(absent["verdict"], "ANSWER", absent)
        self.assertEqual(
            {row["verdict"] for row in absent["construction_reviews"]},
            {"REVIEW_GORE_PANEL_ORDER_REQUIRED",
             "REVIEW_GORE_PLEAT_GEOMETRY_REQUIRED"},
        )
        self.assertFalse(any(
            row.get("construction_role") == "ORDERED_GORE_PANEL_ASSEMBLY"
            for row in absent["seams"]))
        self.assertEqual(absent["transforms"], [])

        missing_depth_spec = {
            "schema": "garment.structure.v1",
            "nodes": [gore(attributes={
                "gore_group_id": "skirt",
                "panel_count": 2,
                "panel_order": ["front", "back"],
                "detail_role": "pleated",
            })],
            "operations": [pleat("skirt-gore", "missing-depth", depth_cm=None)],
        }
        missing_depth = structure_to_pattern.compile(missing_depth_spec)
        self.assertEqual(missing_depth["verdict"], "UNKNOWN_PLEAT_PARAMETERS")

    def test_partial_or_conflicting_topology_fails_closed(self):
        partial = gore(attributes={"panel_count": 4})
        result = structure_to_pattern.compile({
            "schema": "garment.structure.v1",
            "nodes": [partial],
            "operations": [],
        })
        self.assertEqual(result["verdict"],
                         "UNKNOWN_GORE_PANEL_TOPOLOGY_INCOMPLETE")

        mismatch = gore(attributes={
            "gore_group_id": "skirt",
            "panel_count": 4,
            "panel_order": ["front", "back"],
        })
        result = structure_to_pattern.compile({
            "schema": "garment.structure.v1",
            "nodes": [mismatch],
            "operations": [],
        })
        self.assertEqual(result["verdict"],
                         "UNKNOWN_GORE_PANEL_ORDER_COUNT_MISMATCH")

    def test_each_ordered_gore_can_use_an_explicit_gather_ratio(self):
        nodes = []
        operations = []
        for order in (1, 2):
            gore_id = f"gore-{order}"
            target_id = f"waist-segment-{order}"
            nodes.append(gore(gore_id, attributes={
                "gore_group_id": "gathered-skirt",
                "panel_count": 2,
                "panel_order": order,
                "detail_role": "gathered",
            }))
            nodes.append({
                "node_id": target_id,
                "kind": "BAND",
                "dimensions": {"length_cm": 8.0, "width_cm": 2.0},
                "ports": [{"port_id": "join", "length_cm": 8.0,
                           "interface": "gore-top", "role": "edge"}],
            })
            operations.append({
                "operation_id": f"gather-{order}",
                "kind": "GATHER",
                "source": {"node_id": gore_id, "port_id": "top-pleat"},
                "target": {"node_id": target_id, "port_id": "join"},
                "parameters": {"ratio": 1.5},
            })
        result = structure_to_pattern.compile({
            "schema": "garment.structure.v1",
            "nodes": nodes,
            "operations": operations,
        })

        self.assertEqual(result["verdict"], "ANSWER", result)
        gathers = [row for row in result["transforms"]
                   if row["kind"] == "GATHER"]
        self.assertEqual(len(gathers), 2)
        self.assertTrue(all(row["ratio"] == 1.5 for row in gathers))
        self.assertTrue(all(row["state"] == "PROPOSED" for row in gathers))
        self.assertEqual(result["construction_reviews"], [])
        self.assertFalse(result["manufacturing_ready"])

    def test_gather_and_frill_semantics_remain_proposed_after_approval(self):
        spec = {
            "schema": "garment.structure.v1",
            "nodes": [
                {
                    "node_id": "frill",
                    "kind": "BAND",
                    "dimensions": {"length_cm": 150.0, "width_cm": 8.0},
                    "attributes": {"detail_role": "frill"},
                    "ports": [{"port_id": "long", "length_cm": 150.0,
                               "interface": "hem-frill", "role": "edge"}],
                },
                {
                    "node_id": "hem",
                    "kind": "BAND",
                    "dimensions": {"length_cm": 100.0, "width_cm": 2.0},
                    "ports": [{"port_id": "join", "length_cm": 100.0,
                               "interface": "hem-frill", "role": "edge"}],
                },
            ],
            "operations": [{
                "operation_id": "gather-frill",
                "kind": "GATHER",
                "source": {"node_id": "frill", "port_id": "long"},
                "target": {"node_id": "hem", "port_id": "join"},
                "parameters": {"ratio": 1.5},
            }],
        }
        result = structure_to_pattern.compile(
            spec, candidate_state="APPROVED",
            approval={"by": "reviewer", "digest": "sha256:candidate"})

        self.assertEqual(result["verdict"], "ANSWER", result)
        gather = next(row for row in result["transforms"]
                      if row["kind"] == "GATHER")
        seam = next(row for row in result["seams"]
                    if row["operation_id"] == "gather-frill")
        frill = next(row for row in result["pieces"]
                     if row["piece_id"] == "frill")
        self.assertEqual(gather["state"], "PROPOSED")
        self.assertIs(gather["manufacturing_ready"], False)
        self.assertEqual(seam["state"], "PROPOSED")
        self.assertIs(seam["manufacturing_ready"], False)
        self.assertEqual(frill["construction_features"][-1]["state"],
                         "PROPOSED")
        self.assertIs(result["manufacturing_ready"], False)


if __name__ == "__main__":
    unittest.main()
