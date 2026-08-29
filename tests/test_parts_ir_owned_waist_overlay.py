#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""General typed ownership regression for a lower unit plus waist overlay.

No fixture or garment name selects the topology.  The graph is accepted only
because the proposal explicitly supplies parent, owner, layer, attachment and
waist-stack addresses.
"""

import copy
import unittest

from photoloset import garment_structure
from photoloset import structure_to_pattern
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


def _part(part_id, kind, dimensions, *, layer, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": layer,
        "placement": semantics.pop("placement", "lower body"),
        "garment_unit": "lower-unit",
        "dimensions": dimensions,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": "front-view model proposal",
            "breaks_when": "another view or construction review rejects it",
        },
    }
    row.update(semantics)
    return row


def _parts(outer_kind="FLARE"):
    owner_id = "waist-carrier"
    left_id = "limb-left"
    right_id = "limb-right"
    outer_dimensions = {
        "FLARE": {
            "height_cm": 72.0,
            "top_circumference_cm": 92.0,
            "bottom_circumference_cm": 156.0,
        },
        "FRUSTUM": {
            "height_cm": 72.0,
            "top_circumference_cm": 92.0,
            "bottom_circumference_cm": 116.0,
        },
        "GORE": {
            "length_cm": 72.0,
            "top_width_cm": 24.0,
            "bottom_width_cm": 54.0,
        },
        "OVERLAY": {"height_cm": 72.0, "width_cm": 54.0},
    }[outer_kind]
    return [
        _part(
            owner_id,
            "BODY_SHELL",
            {"height_cm": 18.0, "circumference_cm": 80.0},
            layer=1,
            placement="waist carrier",
            quantity=1,
        ),
        _part(
            left_id,
            "TUBE",
            {"length_cm": 96.0, "circumference_cm": 40.0},
            layer=1,
            attached_to=owner_id,
            owner_node_id=owner_id,
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
            right_id,
            "TUBE",
            {"length_cm": 96.0, "circumference_cm": 40.0},
            layer=1,
            attached_to=owner_id,
            owner_node_id=owner_id,
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
            "center-bridge",
            "GUSSET",
            {"length_cm": 17.0, "width_cm": 8.0},
            layer=1,
            placement="center crotch",
            attached_to=[left_id, right_id],
            side="center",
            shape="trousers",
            detail_role="trouser_gusset",
            quantity=1,
        ),
        _part(
            "surface-outer",
            outer_kind,
            outer_dimensions,
            layer=2,
            placement="asymmetric outer lower surface",
            attached_to=owner_id,
            owner_node_id=owner_id,
            ownership_state="PROPOSED",
            layer_role="OUTER_OVERLAY",
            attachment_relation="LAYER",
            attachment_port="WAIST_STACK",
            waist_stack_state="PROPOSED",
            waist_stack_parent=owner_id,
            waist_stack_id="lower-stack-01",
            waist_stack_order=2,
            waist_stack_construction_mode="LAYER",
            waist_stack_role="OUTER_OVERLAY",
            detail_role="asymmetric_overlay",
            quantity=1,
        ),
    ]


def _completion(parts):
    return complete_parts_ir({
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {
                "candidate_id": candidate_id,
                "state": "PROPOSED",
                "parts": copy.deepcopy(parts),
            }
            for candidate_id in ("proposal-1", "proposal-2")
        ],
    })


class OwnedWaistOverlayTopologyTests(unittest.TestCase):
    def test_owned_legs_and_outer_overlay_share_one_explicit_waist_owner(self):
        for outer_kind in ("FLARE", "FRUSTUM", "GORE", "OVERLAY"):
            with self.subTest(outer_kind=outer_kind):
                completed = _completion(_parts(outer_kind))
                self.assertEqual("PROPOSED", completed["verdict"], completed)
                before = copy.deepcopy(completed)

                result = apply_parts_ir_topology(completed)

                self.assertEqual("PROPOSED", result["verdict"], result)
                self.assertEqual(before, completed)
                self.assertFalse(result["authority"]["observed"])
                self.assertFalse(result["authority"]["approved"])
                self.assertFalse(result["authority"]["answer"])
                for candidate in result["candidates"]:
                    operations = {
                        operation["operation_id"]: operation
                        for operation in candidate["operations"]
                    }
                    leg_joins = [
                        operation for operation in operations.values()
                        if operation["operation_id"].startswith(
                            "join-waist-waist-carrier-limb-")
                    ]
                    self.assertEqual(2, len(leg_joins))
                    self.assertTrue(all(
                        operation["parameters"]["ownership"] == {
                            "state": "PROPOSED",
                            "parent_node_id": "waist-carrier",
                            "owner_node_id": "waist-carrier",
                            "layer_role": "OWNED_LEG",
                            "attachment_relation": "JOIN",
                            "attachment_port": "WAIST",
                            "authority_granted": False,
                            "observed": False,
                            "approved": False,
                        }
                        for operation in leg_joins
                    ))

                    overlay = operations[
                        "layer-waist-overlay-surface-outer-on-waist-carrier"]
                    self.assertEqual("LAYER", overlay["kind"])
                    self.assertEqual(
                        "PROPOSED_WAIST_OUTER_OVERLAY",
                        overlay["parameters"]["construction_role"],
                    )
                    self.assertEqual(
                        "lower-stack-01",
                        overlay["parameters"]["waist_stack"]["stack_id"],
                    )
                    self.assertEqual(
                        "OUTER_OVERLAY",
                        overlay["parameters"]["waist_stack"]["role"],
                    )
                    self.assertFalse(
                        overlay["parameters"]["seam_join_created"])
                    self.assertFalse(
                        overlay["parameters"]["truth"]["authority_granted"])
                    self.assertEqual(
                        "ANSWER",
                        garment_structure.validate(candidate)["verdict"],
                    )
                    compiled = structure_to_pattern.compile(
                        candidate, candidate_id=candidate["candidate_id"])
                    self.assertEqual(
                        "ANSWER", compiled["verdict"], compiled)
                    self.assertEqual(
                        "PROPOSED", compiled["candidate_state"])
                    self.assertFalse(compiled["manufacturing_ready"])

    def test_outer_layer_contract_does_not_guess_a_missing_owner(self):
        parts = _parts()
        outer = parts[-1]
        outer.pop("owner_node_id")

        result = apply_parts_ir_topology(_completion(parts))

        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_OWNERSHIP_CONTRACT",
            result["verdict"],
        )
        self.assertEqual("UNRESOLVED", result["state"])
        self.assertIn("owner_node_id", result["missing"])
        self.assertNotIn("candidates", result)

    def test_conflicting_owner_is_not_promoted_from_an_id_guess(self):
        parts = _parts()
        parts[-1]["owner_node_id"] = "unrelated-node"

        result = apply_parts_ir_topology(_completion(parts))

        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_OWNER_MISMATCH", result["verdict"])
        self.assertEqual("waist-carrier", result["expected_owner"])
        self.assertEqual("unrelated-node", result["owner_node_id"])

    def test_observed_ownership_claim_is_rejected_before_topology(self):
        parts = _parts()
        parts[1]["ownership_state"] = "OBSERVED"

        result = _completion(parts)

        self.assertEqual(
            "UNKNOWN_PARTS_IR_AUTHORITY_ESCALATION", result["verdict"])
        self.assertEqual("ownership_state", result["field"])

    def test_both_legs_need_the_same_explicit_ownership_shape(self):
        parts = _parts()
        for field in (
                "owner_node_id", "ownership_state", "layer_role",
                "attachment_relation", "attachment_port"):
            parts[2].pop(field)

        result = apply_parts_ir_topology(_completion(parts))

        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSER_OWNERSHIP_INCOMPLETE",
            result["verdict"],
        )
        self.assertEqual(["right"], result["missing_sides"])


if __name__ == "__main__":
    unittest.main()
