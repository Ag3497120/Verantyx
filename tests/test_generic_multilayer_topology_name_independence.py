#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Name-independent regression for one generic multilayer outfit topology.

The public boundary under test is deliberately the same one used after a
vision/LLM parts proposal: ``complete_parts_ir`` followed by
``apply_parts_ir_topology``.  All semantic decisions are supplied through
typed fields.  Node ids, candidate ids, garment-unit ids, and source prose are
opaque and must not select a topology.

The extra BODY_SHELL in each lower unit is an explicit waist owner.  Without
it, a separate pair of legs correctly remains an open standalone lower unit
and cannot claim ownership or host an owned waist overlay.
"""
from __future__ import annotations

import copy
import unittest

from photoloset import garment_structure
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


def _part(part_id, kind, dimensions, *, layer, unit, **typed_fields):
    row = {
        "part_id": part_id,
        "kind": kind,
        "dimensions": copy.deepcopy(dimensions),
        "layer": layer,
        "garment_unit": unit,
        "placement": "typed front region",
        "visible_basis": {
            "state": "PROPOSED",
            "basis": "a bounded front-region proposal",
            "breaks_when": "another view or human review rejects the region",
        },
    }
    row.update(copy.deepcopy(typed_fields))
    return row


def _parts(ids, *, upper_unit, lower_unit, stack_id):
    """Build topology only from typed roles in ``ids``, never their spelling."""
    inner = ids["inner"]
    outer = ids["outer"]
    waist = ids["waist"]
    left = ids["left"]
    right = ids["right"]
    bridge = ids["bridge"]
    overlay = ids["overlay"]
    return [
        _part(
            inner,
            "BODY_SHELL",
            {
                "height_cm": 43.0,
                "circumference_cm": 90.0,
                "bottom_circumference_cm": 78.0,
            },
            layer=0,
            unit=upper_unit,
            quantity=1,
        ),
        _part(
            outer,
            "BODY_SHELL",
            {
                "height_cm": 40.0,
                "circumference_cm": 98.0,
                "bottom_circumference_cm": 84.0,
            },
            layer=1,
            unit=upper_unit,
            attached_to=inner,
            attachment_relation="LAYER",
            quantity=1,
        ),
        _part(
            waist,
            "BODY_SHELL",
            {
                "height_cm": 16.0,
                "circumference_cm": 80.0,
                "bottom_circumference_cm": 80.0,
            },
            layer=2,
            unit=lower_unit,
            quantity=1,
        ),
        _part(
            left,
            "TUBE",
            {"length_cm": 98.0, "circumference_cm": 40.0},
            layer=2,
            unit=lower_unit,
            attached_to=waist,
            owner_node_id=waist,
            ownership_state="PROPOSED",
            layer_role="OWNED_LEG",
            attachment_relation="JOIN",
            attachment_port="WAIST",
            side="left",
            shape="trouser_leg",
            detail_role="trouser_leg",
            quantity=1,
        ),
        _part(
            right,
            "TUBE",
            {"length_cm": 98.0, "circumference_cm": 40.0},
            layer=2,
            unit=lower_unit,
            attached_to=waist,
            owner_node_id=waist,
            ownership_state="PROPOSED",
            layer_role="OWNED_LEG",
            attachment_relation="JOIN",
            attachment_port="WAIST",
            side="right",
            shape="trouser_leg",
            detail_role="trouser_leg",
            quantity=1,
        ),
        _part(
            bridge,
            "GUSSET",
            {"length_cm": 18.0, "width_cm": 8.0},
            layer=2,
            unit=lower_unit,
            attached_to=[left, right],
            side="center",
            shape="trousers",
            detail_role="trouser_gusset",
            quantity=1,
        ),
        _part(
            overlay,
            "OVERLAY",
            {"height_cm": 72.0, "width_cm": 54.0},
            layer=3,
            unit=lower_unit,
            attached_to=waist,
            owner_node_id=waist,
            ownership_state="PROPOSED",
            layer_role="OUTER_OVERLAY",
            attachment_relation="LAYER",
            attachment_port="WAIST_STACK",
            waist_stack_state="PROPOSED",
            waist_stack_parent=waist,
            waist_stack_id=stack_id,
            waist_stack_order=2,
            waist_stack_construction_mode="LAYER",
            waist_stack_role="OUTER_OVERLAY",
            detail_role="asymmetric_overlay",
            side="right",
            quantity=1,
        ),
    ]


def _candidate(candidate_id, ids, *, upper_unit, lower_unit, stack_id):
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": _parts(
            ids,
            upper_unit=upper_unit,
            lower_unit=lower_unit,
            stack_id=stack_id,
        ),
    }


def _relation_signature(candidate, ids):
    """Replace opaque node ids with test roles before comparing topology."""
    role_by_id = {node_id: role for role, node_id in ids.items()}
    signature = []
    for operation in candidate["operations"]:
        parameters = operation["parameters"]
        ownership = parameters.get("ownership", {})
        signature.append((
            operation["kind"],
            role_by_id[operation["source"]["node_id"]],
            role_by_id[operation["target"]["node_id"]],
            parameters.get("construction_role"),
            ownership.get("layer_role"),
            ownership.get("attachment_relation"),
            ownership.get("attachment_port"),
            parameters.get("source_layer"),
            parameters.get("target_layer"),
        ))
    return sorted(signature, key=repr)


class GenericMultilayerTopologyNameIndependenceTests(unittest.TestCase):
    maxDiff = None

    def test_typed_relations_are_unique_and_invariant_under_neutral_renaming(self):
        naming_sets = (
            {
                "inner": "piece-10",
                "outer": "piece-47",
                "waist": "piece-23",
                "left": "piece-81",
                "right": "piece-06",
                "bridge": "piece-64",
                "overlay": "piece-35",
            },
            {
                "inner": "node-zeta",
                "outer": "node-beta",
                "waist": "node-kappa",
                "left": "node-delta",
                "right": "node-theta",
                "bridge": "node-iota",
                "overlay": "node-alpha",
            },
        )
        request = {
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "candidates": [
                _candidate(
                    "candidate-17",
                    naming_sets[0],
                    upper_unit="unit-03",
                    lower_unit="unit-29",
                    stack_id="stack-41",
                ),
                _candidate(
                    "candidate-58",
                    naming_sets[1],
                    upper_unit="unit-71",
                    lower_unit="unit-12",
                    stack_id="stack-86",
                ),
            ],
        }

        completed = complete_parts_ir(copy.deepcopy(request))
        self.assertEqual("PROPOSED", completed["verdict"], completed)
        completed_before_topology = copy.deepcopy(completed)

        result = apply_parts_ir_topology(completed)

        self.assertEqual("PROPOSED", result["verdict"], result)
        self.assertEqual(2, result["candidate_count"])
        self.assertEqual(completed_before_topology, completed)
        signatures = []
        for candidate, ids in zip(result["candidates"], naming_sets):
            with self.subTest(candidate_id=candidate["candidate_id"]):
                self.assertEqual(
                    "ANSWER",
                    garment_structure.validate(candidate)["verdict"],
                )
                nodes = {node["node_id"]: node for node in candidate["nodes"]}
                self.assertEqual("BODY_SHELL", nodes[ids["inner"]]["kind"])
                self.assertEqual("BODY_SHELL", nodes[ids["outer"]]["kind"])
                self.assertEqual("TUBE", nodes[ids["left"]]["kind"])
                self.assertEqual("TUBE", nodes[ids["right"]]["kind"])
                self.assertEqual("OVERLAY", nodes[ids["overlay"]]["kind"])

                operations = candidate["operations"]
                signatures.append(_relation_signature(candidate, ids))
                operation_ids = [row["operation_id"] for row in operations]
                self.assertEqual(len(operation_ids), len(set(operation_ids)))
                edge_addresses = [
                    (
                        row["kind"],
                        row["source"]["node_id"],
                        row["source"]["port_id"],
                        row["target"]["node_id"],
                        row["target"]["port_id"],
                    )
                    for row in operations
                ]
                self.assertEqual(
                    len(edge_addresses), len(set(edge_addresses)), operations)
                self.assertTrue(all(
                    row["parameters"]["state"] == "PROPOSED"
                    and row["parameters"]["not_observed_from_image"] is True
                    for row in operations
                ))

                body_layers = [
                    row for row in operations
                    if row["parameters"].get("construction_role")
                    == "PROPOSED_LAYERED_BODY_SHELL"
                ]
                self.assertEqual(1, len(body_layers), operations)
                body_layer = body_layers[0]
                self.assertEqual("LAYER", body_layer["kind"])
                self.assertEqual(ids["outer"], body_layer["source"]["node_id"])
                self.assertEqual(ids["inner"], body_layer["target"]["node_id"])
                self.assertEqual(
                    ids["inner"],
                    body_layer["parameters"]["owner_node_id"],
                )
                self.assertEqual(1, body_layer["parameters"]["source_layer"])
                self.assertEqual(0, body_layer["parameters"]["target_layer"])
                self.assertFalse(body_layer["parameters"]["seam_join_created"])

                leg_joins = [
                    row for row in operations
                    if row["parameters"].get("ownership", {}).get(
                        "layer_role") == "OWNED_LEG"
                ]
                self.assertEqual(2, len(leg_joins), operations)
                self.assertEqual(
                    {ids["left"], ids["right"]},
                    {row["source"]["node_id"] for row in leg_joins},
                )
                self.assertEqual(
                    {ids["waist"]},
                    {row["target"]["node_id"] for row in leg_joins},
                )
                for leg_join in leg_joins:
                    ownership = leg_join["parameters"]["ownership"]
                    self.assertEqual(ids["waist"], ownership["parent_node_id"])
                    self.assertEqual(ids["waist"], ownership["owner_node_id"])
                    self.assertEqual("JOIN", ownership["attachment_relation"])
                    self.assertEqual("WAIST", ownership["attachment_port"])
                    self.assertEqual("PROPOSED", ownership["state"])
                    self.assertFalse(ownership["authority_granted"])

                overlay_layers = [
                    row for row in operations
                    if row["parameters"].get("construction_role")
                    == "PROPOSED_WAIST_OUTER_OVERLAY"
                ]
                self.assertEqual(1, len(overlay_layers), operations)
                overlay_layer = overlay_layers[0]
                self.assertEqual("LAYER", overlay_layer["kind"])
                self.assertEqual(
                    ids["overlay"], overlay_layer["source"]["node_id"])
                self.assertEqual(
                    ids["waist"], overlay_layer["target"]["node_id"])
                overlay_ownership = overlay_layer["parameters"]["ownership"]
                self.assertEqual(
                    ids["waist"], overlay_ownership["parent_node_id"])
                self.assertEqual(
                    ids["waist"], overlay_ownership["owner_node_id"])
                self.assertEqual(
                    "OUTER_OVERLAY", overlay_ownership["layer_role"])
                self.assertEqual(
                    "WAIST_STACK", overlay_ownership["attachment_port"])
                self.assertEqual(
                    3, overlay_layer["parameters"]["source_layer"])
                self.assertEqual(
                    2, overlay_layer["parameters"]["target_layer"])
                self.assertFalse(
                    overlay_layer["parameters"]["seam_join_created"])

        self.assertEqual(signatures[0], signatures[1])


if __name__ == "__main__":
    unittest.main()
