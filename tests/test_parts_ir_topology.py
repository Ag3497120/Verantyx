#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest
from typing import Mapping

from photoloset import garment_structure
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


def part(part_id, kind, dimensions, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": semantics.pop("layer", 0),
        "placement": semantics.pop("placement", "front torso"),
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"vision model proposed {part_id}",
            "breaks_when": f"another view rejects {part_id}",
        },
        "dimensions": dimensions,
    }
    row.update(semantics)
    return row


def completion(parts_a, parts_b=None):
    parts_b = copy.deepcopy(parts_a if parts_b is None else parts_b)
    return complete_parts_ir({
        "candidates": [
            {"candidate_id": "candidate-a", "state": "PROPOSED",
             "parts": copy.deepcopy(parts_a)},
            {"candidate_id": "candidate-b", "state": "PROPOSED",
             "parts": parts_b},
        ]
    })


def completed_sleeve_gather(*, child_upper=30.0,
                            state="PROPOSED", provenance=None,
                            lower_extension=True):
    """Build completion output, then inject the topology-layer contract.

    Python parts completion intentionally still limits its input grammar to
    JOIN/LAYER.  These tests exercise the requested topology boundary without
    widening that separate module's write scope.
    """
    body = part(
        "body", "BODY_SHELL",
        {"height_cm": 42.0, "circumference_cm": 82.0},
        garment_unit="look")
    parent = part(
        "inner-sleeve", "SLEEVE",
        {"length_cm": 36.0, "upper_circumference_cm": 34.0,
         "cuff_circumference_cm": 20.0},
        layer=1, placement="arms", garment_unit="look",
        attached_to="body", side="bilateral", shape="set_in",
        quantity=2)
    child = part(
        "lower-sleeve", "SLEEVE",
        {"length_cm": 28.0, "upper_circumference_cm": child_upper,
         "cuff_circumference_cm": 16.0},
        layer=1,
        placement=("lower sleeve extension" if lower_extension else "arms"),
        garment_unit="look", attached_to="inner-sleeve",
        side="bilateral",
        shape=("gauntlet" if lower_extension else "set_in"),
        attachment_relation="JOIN", quantity=2)
    completed = completion([body, parent, child])
    if provenance is None:
        provenance = {
            "state": "PROPOSED",
            "authority": "PROPOSED_RELATION_DERIVED",
            "basis": "model proposes fullness between two sleeve segments",
            "breaks_when": "construction review selects pleats or a plain join",
            "observed": False,
            "approved": False,
            "dimensions_changed": False,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        }
    for candidate in completed["candidates"]:
        sleeve = next(node for node in candidate["nodes"]
                      if node["node_id"] == "lower-sleeve")
        sleeve["attributes"]["attachment_relation"] = "GATHER"
        sleeve["attributes"]["sleeve_join_state"] = state
        if provenance is not ...:
            sleeve["attributes"]["sleeve_join_provenance"] = copy.deepcopy(
                provenance)
        semantics = sleeve["attributes"].get("parts_ir_semantics", {})
        if "attachment_relation" in semantics:
            semantics["attachment_relation"]["value"] = "GATHER"
        checked = garment_structure.validate(candidate)
        if checked["verdict"] == "ANSWER":
            candidate["structure_digest"] = checked["digest"]
    return completed


def dress_parts():
    return [
        part("body", "BODY_SHELL",
             {"height_cm": 42.0, "circumference_cm": 80.0,
              "neck_circumference_cm": 38.0},
             garment_unit="dress", quantity=1),
        part("skirt", "FLARE",
             {"height_cm": 65.0, "top_circumference_cm": 80.0,
              "bottom_circumference_cm": 80.0},
             placement="lower body", garment_unit="dress",
             attached_to="body", shape="flared"),
        part("collar", "COLLAR", {"length_cm": 38.0, "width_cm": 7.0},
             placement="neck", garment_unit="dress", attached_to="body",
             detail_role="collar"),
        part("cape", "OVERLAY", {"height_cm": 45.0, "width_cm": 95.0},
             layer=1, placement="upper back", garment_unit="dress",
             attached_to="body", detail_role="overlay"),
        part("ruffle", "BAND", {"length_cm": 120.0, "width_cm": 10.0},
             layer=1, placement="hem", garment_unit="dress",
             attached_to="skirt", detail_role="ruffle"),
        part("sleeve", "SLEEVE",
             {"length_cm": 58.0, "upper_circumference_cm": 34.0,
              "cuff_circumference_cm": 20.0},
             placement="arms", garment_unit="dress", attached_to="body",
             side="bilateral", shape="set_in", quantity=2),
    ]


def gore_overlay_parts():
    """A front-only decorative gore layered over one structural skirt."""
    return [
        part("body", "BODY_SHELL",
             {"height_cm": 42.0, "circumference_cm": 80.0},
             garment_unit="layered-look", quantity=1),
        part("base-skirt", "FLARE",
             {"height_cm": 62.0, "top_circumference_cm": 80.0,
              "bottom_circumference_cm": 132.0},
             layer=1, placement="lower body", garment_unit="layered-look",
             attached_to="body", shape="structural skirt"),
        part("front-gore-overlay", "GORE",
             {"length_cm": 58.0, "top_width_cm": 16.0,
              "bottom_width_cm": 38.0},
             layer=2, placement="front",
             garment_unit="layered-look", attached_to="base-skirt",
             shape="asymmetric", detail_role="overlay"),
    ]


def waist_stack_provenance(order, construction_mode):
    return {
        "state": "PROPOSED",
        "basis": "front model proposes two independently constructed layers",
        "breaks_when": "rear view or construction review rejects the stack",
        "waist_stack_state": "PROPOSED",
        "waist_stack_parent": "body",
        "waist_stack_id": "body-lower-stack",
        "waist_stack_order": order,
        "waist_stack_construction_mode": construction_mode,
        "not_observed_from_front": True,
        "dimensions_changed": False,
    }


def layered_waist_parts():
    return [
        part("body", "BODY_SHELL",
             {"height_cm": 42.0, "circumference_cm": 80.0},
             garment_unit="layered-dress", quantity=1),
        part("inner-skirt", "FRUSTUM",
             {"height_cm": 56.0, "top_circumference_cm": 80.0,
              "bottom_circumference_cm": 96.0},
             layer=1, placement="inner lower body",
             garment_unit="layered-dress", attached_to="body",
             shape="straight_skirt", waist_join_provenance=(
                 waist_stack_provenance(1, "JOIN"))),
        part("outer-skirt", "FLARE",
             {"height_cm": 42.0, "top_circumference_cm": 120.0,
              "bottom_circumference_cm": 180.0},
             layer=2, placement="outer lower body",
             garment_unit="layered-dress", attached_to="body",
             shape="overskirt", waist_join_mode="GATHER",
             waist_join_state="PROPOSED", waist_join_provenance=(
                 waist_stack_provenance(2, "GATHER"))),
    ]


class PartsIRTopologyTests(unittest.TestCase):
    def test_typed_rules_create_valid_operations_without_sleeve_join(self):
        completed = completion(dress_parts())
        self.assertEqual(completed["verdict"], "PROPOSED")
        before = copy.deepcopy(completed)
        result = apply_parts_ir_topology(completed)
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(completed, before)
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["authority"]["approved"])
        self.assertFalse(result["authority"]["observed"])
        self.assertFalse(result["authority"]["answer"])

        for candidate in result["candidates"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(garment_structure.validate(candidate)["verdict"],
                             "ANSWER")
            kinds = [row["kind"] for row in candidate["operations"]]
            self.assertEqual(kinds.count("JOIN"), 2)
            self.assertEqual(kinds.count("LAYER"), 1)
            self.assertEqual(kinds.count("GATHER"), 1)
            self.assertFalse(any(
                op["kind"] == "JOIN" and
                (op["source"]["node_id"] == "sleeve"
                 or op["target"]["node_id"] == "sleeve")
                for op in candidate["operations"]
            ))
            delegated = candidate["topology"]["delegated_relations"]
            self.assertEqual(delegated[0]["rule"],
                             "DELEGATED_BODICE_SET_IN_SLEEVE_BRIDGE")
            gather = next(op for op in candidate["operations"]
                          if op["kind"] == "GATHER")
            self.assertAlmostEqual(gather["parameters"]["ratio"], 1.5)
            self.assertTrue(all(op["parameters"]["state"] == "PROPOSED"
                                for op in candidate["operations"]))
            json.dumps(candidate, allow_nan=False)

    def test_candidate_geometry_identity_keeps_repeated_surface_copies_distinct(self):
        structural = [
            part("body", "BODY_SHELL",
                 {"height_cm": 42.0, "circumference_cm": 80.0},
                 garment_unit="look", quantity=1),
            part("asymmetric-cape", "OVERLAY",
                 {"height_cm": 38.0, "width_cm": 72.0},
                 layer=2, placement="asymmetric front",
                 garment_unit="look", attached_to="body",
                 side="asymmetric", shape="asymmetric overlay",
                 detail_role="overlay", quantity=1),
        ]

        def rosettes(quantity):
            return part(
                "front-rosettes", "ROSETTE",
                {"strip_length_cm": 72.0, "strip_width_cm": 4.0,
                 "finished_inner_length_cm": 18.0},
                layer=3, placement="front decoration",
                garment_unit="look", attached_to="asymmetric-cape",
                target_port_id="decorative-front", quantity=quantity,
                grain_direction="BIAS_45", seam_allowance_cm=0.8,
            )

        completed = completion(
            structural + [rosettes(2)],
            structural + [rosettes(3)],
        )
        # Completion intentionally assigns different rear/opening hypotheses
        # to candidate A/B.  Freeze candidate B to A's structural graph here
        # so this regression isolates the previously unaddressed case: equal
        # structural geometry with a different repeated ornament count.
        source_candidate, repeated_candidate = completed["candidates"]
        repeated_candidate["nodes"] = copy.deepcopy(
            source_candidate["nodes"])
        repeated_candidate["structure_digest"] = (
            source_candidate["structure_digest"])
        repeated_candidate["ornament_artifacts"][
            "source_structure_digest"] = source_candidate["structure_digest"]
        result = apply_parts_ir_topology(completed)
        self.assertEqual("PROPOSED", result["verdict"], result)
        candidate_a, candidate_b = result["candidates"]

        # The structural primitive graph is intentionally identical; only the
        # explicitly proposed number of materialized surface copies differs.
        self.assertEqual(candidate_a["structure_digest"],
                         candidate_b["structure_digest"])
        self.assertNotEqual(candidate_a["candidate_geometry_digest"],
                            candidate_b["candidate_geometry_digest"])
        self.assertEqual(
            candidate_a["candidate_geometry_digest"],
            candidate_a["candidate_geometry"]["digest"],
        )

        for candidate, expected_copies in ((candidate_a, 2),
                                           (candidate_b, 3)):
            geometry = candidate["candidate_geometry"]
            self.assertEqual("PROPOSED", geometry["state"])
            self.assertEqual(
                ["layer-asymmetric-cape-on-body"],
                geometry["layer_operation_ids"],
            )
            self.assertEqual(["asymmetric-cape"],
                             geometry["overlay_node_ids"])
            self.assertEqual(["asymmetric-cape"],
                             geometry["asymmetric_attachment_node_ids"])
            instances = geometry["decorative_surface_instances"]
            self.assertEqual(expected_copies, len(instances))
            self.assertEqual(
                list(range(1, expected_copies + 1)),
                [instance["copy_index"] for instance in instances],
            )
            self.assertTrue(all(instance["state"] == "PROPOSED"
                                for instance in instances))
            self.assertFalse(geometry["formed_3d_geometry_claimed"])
            self.assertFalse(geometry["rear_geometry_observed"])
            self.assertFalse(geometry["material_observed"])
            self.assertFalse(geometry["authority_granted"])

    def test_layered_body_shell_owns_outer_sleeve_without_inventing_seam(self):
        parts = [
            part("second-skin", "BODY_SHELL",
                 {"height_cm": 44.0, "circumference_cm": 78.0},
                 layer=0, garment_unit="layered-look", quantity=1),
            part("outer-bodice", "BODY_SHELL",
                 {"height_cm": 46.0, "circumference_cm": 88.0},
                 layer=2, garment_unit="layered-look", quantity=1,
                 attached_to="second-skin", detail_role="outer bodice"),
            part("outer-sleeves", "SLEEVE",
                 {"length_cm": 58.0, "upper_circumference_cm": 38.0,
                  "cuff_circumference_cm": 22.0},
                 layer=2, placement="arms", garment_unit="layered-look",
                 attached_to="outer-bodice", side="bilateral",
                 shape="set_in", quantity=2),
        ]
        result = apply_parts_ir_topology(completion(parts))
        self.assertEqual("PROPOSED", result["verdict"], result)
        for candidate in result["candidates"]:
            layer = next(
                operation for operation in candidate["operations"]
                if operation["operation_id"] ==
                "layer-body-outer-bodice-on-second-skin")
            self.assertEqual("LAYER", layer["kind"])
            self.assertEqual("outer-bodice", layer["source"]["node_id"])
            self.assertEqual("second-skin", layer["target"]["node_id"])
            self.assertEqual(
                "PROPOSED_LAYERED_BODY_SHELL",
                layer["parameters"]["construction_role"])
            self.assertFalse(layer["parameters"]["seam_join_created"])
            self.assertFalse(layer["parameters"]["manufacturing_ready"])
            self.assertFalse(
                layer["parameters"]["truth"]
                ["rear_or_inside_construction_observed"])
            sleeve = next(
                relation for relation in
                candidate["topology"]["delegated_relations"]
                if relation["node_id"] == "outer-sleeves")
            self.assertEqual("outer-bodice", sleeve["target_node_id"])
            self.assertEqual(
                "DELEGATED_BODICE_SET_IN_SLEEVE_BRIDGE",
                sleeve["rule"])
            self.assertEqual(
                "ANSWER", garment_structure.validate(candidate)["verdict"])

    def test_layered_body_shell_refuses_non_higher_layer(self):
        parts = [
            part("inner-body", "BODY_SHELL",
                 {"height_cm": 44.0, "circumference_cm": 78.0},
                 layer=1, garment_unit="layered-look", quantity=1),
            part("outer-body", "BODY_SHELL",
                 {"height_cm": 46.0, "circumference_cm": 88.0},
                 layer=1, garment_unit="layered-look", quantity=1,
                 attached_to="inner-body", detail_role="outer bodice"),
        ]
        result = apply_parts_ir_topology(completion(parts))
        self.assertEqual("UNKNOWN_PARTS_TOPOLOGY_BODY_LAYER_ORDER",
                         result["verdict"])
        self.assertEqual("outer-body", result["node_id"])
        self.assertEqual("inner-body", result["target_id"])
        self.assertEqual(1, result["child_layer"])
        self.assertEqual(1, result["parent_layer"])

    def test_body_tube_and_hood_rules_are_supported(self):
        parts = [
            part("body", "BODY_SHELL",
                 {"height_cm": 42.0, "circumference_cm": 80.0,
                  "neck_circumference_cm": 36.0}, garment_unit="look"),
            part("tube", "TUBE", {"length_cm": 60.0,
                                    "circumference_cm": 80.0},
                 placement="lower body", garment_unit="look",
                 attached_to="body", shape="straight_skirt"),
            part("hood", "HOOD", {"height_cm": 38.0, "width_cm": 36.0,
                                    "depth_cm": 28.0},
                 placement="neck", garment_unit="look", attached_to="body"),
        ]
        result = apply_parts_ir_topology(completion(parts))
        self.assertEqual(result["verdict"], "PROPOSED")
        for candidate in result["candidates"]:
            operations = candidate["operations"]
            self.assertEqual({op["kind"] for op in operations}, {"JOIN"})
            self.assertEqual({
                op["source"]["node_id"] for op in operations
            }, {"tube", "hood"})
            hood = next(node for node in candidate["nodes"]
                        if node["node_id"] == "hood")
            self.assertTrue(hood["attributes"][
                "topology_neck_boundary_approximation"]["used"])

    def test_explicit_front_asymmetric_gore_overlay_is_proposal_only_layer(self):
        completed = completion(gore_overlay_parts())
        self.assertEqual("PROPOSED", completed["verdict"], completed)
        before = copy.deepcopy(completed)

        result = apply_parts_ir_topology(completed)

        self.assertEqual("PROPOSED", result["verdict"], result)
        self.assertEqual(before, completed)
        self.assertFalse(result["authority"]["approved"])
        self.assertFalse(result["authority"]["observed"])
        self.assertFalse(result["authority"]["answer"])
        for candidate in result["candidates"]:
            nodes = {node["node_id"]: node for node in candidate["nodes"]}
            self.assertEqual(
                {"length_cm": 58.0, "top_width_cm": 16.0,
                 "bottom_width_cm": 38.0},
                nodes["front-gore-overlay"]["dimensions"],
            )
            gore_operations = [
                operation for operation in candidate["operations"]
                if "front-gore-overlay" in {
                    operation["source"]["node_id"],
                    operation["target"]["node_id"],
                }
            ]
            self.assertEqual(1, len(gore_operations), gore_operations)
            layer = gore_operations[0]
            self.assertEqual("LAYER", layer["kind"])
            self.assertEqual("front-gore-overlay",
                             layer["source"]["node_id"])
            self.assertEqual("base-skirt", layer["target"]["node_id"])
            parameters = layer["parameters"]
            self.assertEqual("PROPOSED_GORE_OVERLAY",
                             parameters["construction_role"])
            self.assertEqual(2, parameters["source_layer"])
            self.assertEqual(1, parameters["target_layer"])
            self.assertFalse(parameters["seam_join_created"])
            self.assertFalse(parameters["dimensions_changed"])
            self.assertFalse(parameters["manufacturing_ready"])
            self.assertFalse(parameters["manufacturing_certified"])
            self.assertEqual("PROPOSED", parameters["state"])
            self.assertEqual("PROPOSED", parameters["authority"])
            self.assertEqual("PROPOSED", parameters["truth"]["state"])
            self.assertFalse(parameters["truth"]["observed"])
            self.assertFalse(parameters["truth"]["approved"])
            self.assertFalse(parameters["truth"]["authority_granted"])
            self.assertFalse(any(
                operation["kind"] == "JOIN"
                and "front-gore-overlay" in {
                    operation["source"]["node_id"],
                    operation["target"]["node_id"],
                }
                for operation in candidate["operations"]
            ))
            self.assertEqual(
                "ANSWER", garment_structure.validate(candidate)["verdict"])

    def test_gore_visible_basis_can_supply_explicit_asymmetric_overlay_role(self):
        parts = gore_overlay_parts()
        gore = parts[2]
        gore["placement"] = "front skirt panel"
        gore["shape"] = "trapezoid"
        gore.pop("detail_role")
        gore["attachment_relation"] = "LAYER"
        gore["visible_basis"] = {
            "state": "PROPOSED",
            "basis": "pixel-visible asymmetric front panel layered above the base skirt",
            "breaks_when": "another view shows this is a structural gore seam",
        }

        result = apply_parts_ir_topology(completion(parts))

        self.assertEqual("PROPOSED", result["verdict"], result)
        for candidate in result["candidates"]:
            operation = next(
                row for row in candidate["operations"]
                if row["operation_id"]
                == "layer-gore-front-gore-overlay-on-base-skirt")
            self.assertEqual("LAYER", operation["kind"])
            self.assertEqual(
                "PROPOSED_GORE_OVERLAY",
                operation["parameters"]["construction_role"],
            )
            self.assertFalse(operation["parameters"]["seam_join_created"])
            self.assertFalse(operation["parameters"]["truth"]["observed"])

    def test_gore_overlay_contract_failures_are_typed_and_fail_closed(self):
        cases = []

        structural = gore_overlay_parts()
        structural[2]["placement"] = "front skirt panel"
        structural[2]["shape"] = "trapezoid gore"
        structural[2]["detail_role"] = "structural skirt panel"
        cases.append((
            "structural gore is not an overlay",
            structural,
            "UNKNOWN_PARTS_TOPOLOGY_GORE_ATTACHMENT_ROLE",
        ))

        same_layer = gore_overlay_parts()
        same_layer[2]["layer"] = 1
        cases.append((
            "source and target share a layer",
            same_layer,
            "UNKNOWN_PARTS_TOPOLOGY_GORE_OVERLAY_LAYER",
        ))

        target_above = gore_overlay_parts()
        target_above[1]["layer"] = 3
        cases.append((
            "target layer is above the source",
            target_above,
            "UNKNOWN_PARTS_TOPOLOGY_GORE_OVERLAY_LAYER",
        ))

        incompatible_unit = gore_overlay_parts()
        incompatible_unit[2]["garment_unit"] = "separate-accessory"
        cases.append((
            "garment units differ",
            incompatible_unit,
            "UNKNOWN_PARTS_TOPOLOGY_GARMENT_UNIT_MISMATCH",
        ))

        no_parent = gore_overlay_parts()
        no_parent[2].pop("attached_to")
        cases.append((
            "attached_to is absent",
            no_parent,
            "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS",
        ))

        ambiguous_parent = gore_overlay_parts()
        ambiguous_parent[2]["attached_to"] = ["base-skirt", "body"]
        cases.append((
            "more than one parent is supplied",
            ambiguous_parent,
            "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS",
        ))

        missing_parent = gore_overlay_parts()
        missing_parent[2]["attached_to"] = "not-a-node"
        cases.append((
            "the addressed parent does not exist",
            missing_parent,
            "UNKNOWN_PARTS_TOPOLOGY_TARGET_MISSING",
        ))

        for label, parts, expected_verdict in cases:
            with self.subTest(label=label):
                completed = completion(parts)
                self.assertEqual("PROPOSED", completed["verdict"], completed)
                before = copy.deepcopy(completed)
                result = apply_parts_ir_topology(completed)
                self.assertEqual(expected_verdict, result["verdict"], result)
                self.assertEqual("UNRESOLVED", result["state"])
                self.assertEqual(before, completed)
                self.assertNotIn("candidates", result)

    def test_join_mismatch_missing_target_and_ambiguous_gather_fail_closed(self):
        mismatched = dress_parts()
        mismatched[1]["dimensions"]["top_circumference_cm"] = 90.0
        result = apply_parts_ir_topology(completion(mismatched))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_JOIN_LENGTH_MISMATCH")
        self.assertEqual(result["state"], "UNRESOLVED")

        unaddressed = dress_parts()
        del unaddressed[1]["attached_to"]
        result = apply_parts_ir_topology(completion(unaddressed))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_WAIST_TARGET_UNRESOLVED")

        ambiguous = dress_parts()
        ambiguous[4]["placement"] = "decorative edge"
        result = apply_parts_ir_topology(completion(ambiguous))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_GATHER_TARGET_AMBIGUOUS")

    def test_explicit_proposed_skirt_fullness_compiles_as_gather_without_resizing(self):
        gathered = dress_parts()
        gathered[0]["dimensions"]["circumference_cm"] = 72.0
        gathered[1]["dimensions"]["top_circumference_cm"] = 90.0
        gathered[1]["waist_join_mode"] = "GATHER"
        gathered[1]["waist_join_state"] = "PROPOSED"
        gathered[1]["waist_join_provenance"] = {
            "state": "PROPOSED",
            "basis": "front-model boundary proposals differ",
            "breaks_when": "review selects pleats or a separate waistband",
            "source_length_cm": 90.0,
            "target_length_cm": 72.0,
            "not_observed_from_front": True,
            "dimensions_changed": False,
        }
        result = apply_parts_ir_topology(completion(gathered))
        self.assertEqual("PROPOSED", result["verdict"])
        for candidate in result["candidates"]:
            skirt = next(node for node in candidate["nodes"]
                         if node["node_id"] == "skirt")
            self.assertEqual(90.0,
                             skirt["dimensions"]["top_circumference_cm"])
            gather = next(op for op in candidate["operations"]
                          if op["operation_id"] ==
                          "gather-waist-skirt-to-body")
            self.assertEqual("GATHER", gather["kind"])
            self.assertAlmostEqual(1.25, gather["parameters"]["ratio"])
            self.assertEqual(90.0, gather["parameters"]["source_length_cm"])
            self.assertEqual(72.0, gather["parameters"]["target_length_cm"])
            self.assertEqual("ANSWER",
                             garment_structure.validate(candidate)["verdict"])

        escalated = copy.deepcopy(gathered)
        escalated[1]["waist_join_state"] = "OBSERVED"
        result = complete_parts_ir({
            "candidates": [
                {"candidate_id": "candidate-a", "state": "PROPOSED",
                 "parts": escalated},
                {"candidate_id": "candidate-b", "state": "PROPOSED",
                 "parts": copy.deepcopy(escalated)},
            ]
        })
        self.assertEqual("UNKNOWN_PARTS_IR_AUTHORITY_ESCALATION",
                         result["verdict"])

    def test_explicit_two_layer_waist_stack_compiles_independent_join_and_gather(self):
        parts = layered_waist_parts()
        completed = completion(parts)
        before = copy.deepcopy(completed)
        result = apply_parts_ir_topology(completed)
        self.assertEqual("PROPOSED", result["verdict"], result)
        self.assertEqual(before, completed)

        for candidate in result["candidates"]:
            operations = {row["source"]["node_id"]: row
                          for row in candidate["operations"]}
            self.assertEqual({"inner-skirt", "outer-skirt"},
                             set(operations))
            self.assertEqual("JOIN", operations["inner-skirt"]["kind"])
            self.assertEqual("GATHER", operations["outer-skirt"]["kind"])
            self.assertAlmostEqual(
                1.5, operations["outer-skirt"]["parameters"]["ratio"])
            self.assertEqual(
                {
                    "state": "PROPOSED",
                    "parent_node_id": "body",
                    "stack_id": "body-lower-stack",
                    "order": 1,
                    "construction_mode": "JOIN",
                    "dimensions_changed": False,
                    "authority_granted": False,
                },
                operations["inner-skirt"]["parameters"]["waist_stack"],
            )
            self.assertEqual(
                2,
                operations["outer-skirt"]["parameters"]["waist_stack"][
                    "order"],
            )
            nodes = {node["node_id"]: node for node in candidate["nodes"]}
            self.assertEqual(
                80.0, nodes["inner-skirt"]["dimensions"][
                    "top_circumference_cm"])
            self.assertEqual(
                120.0, nodes["outer-skirt"]["dimensions"][
                    "top_circumference_cm"])
            self.assertEqual("PROPOSED", candidate["state"])
            self.assertEqual("ANSWER",
                             garment_structure.validate(candidate)["verdict"])

    def test_parallel_waist_stack_refuses_duplicate_order_with_relations(self):
        parts = layered_waist_parts()
        parts[2]["waist_join_provenance"]["waist_stack_order"] = 1
        result = apply_parts_ir_topology(completion(parts))
        self.assertEqual("UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_ORDER",
                         result["verdict"])
        self.assertEqual("waist_stack_order", result["field"])
        self.assertEqual({"body": ["inner-skirt", "outer-skirt"]},
                         result["relations"])
        self.assertEqual([1, 1], result["waist_stack_orders"])

    def test_parallel_waist_stack_refuses_missing_child_metadata(self):
        parts = layered_waist_parts()
        del parts[2]["waist_join_provenance"]["waist_stack_parent"]
        result = apply_parts_ir_topology(completion(parts))
        self.assertEqual("UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_METADATA",
                         result["verdict"])
        self.assertEqual("waist_stack_contract", result["field"])
        self.assertEqual("outer-skirt", result["node_id"])
        self.assertIn("waist_stack_parent", result["missing"])
        self.assertEqual({"body": ["inner-skirt", "outer-skirt"]},
                         result["relations"])

        arbitrary = layered_waist_parts()
        for child in arbitrary[1:]:
            child.pop("waist_join_provenance", None)
            child.pop("waist_join_mode", None)
            child.pop("waist_join_state", None)
        result = apply_parts_ir_topology(completion(arbitrary))
        self.assertEqual("UNKNOWN_PARTS_TOPOLOGY_MULTIPLE_WAIST_CHILDREN",
                         result["verdict"])
        self.assertEqual({"body": ["inner-skirt", "outer-skirt"]},
                         result["relations"])

    def test_parallel_waist_stack_never_claims_manufacturing_readiness(self):
        result = apply_parts_ir_topology(completion(layered_waist_parts()))
        self.assertEqual("PROPOSED", result["verdict"], result)
        self.assertFalse(result["authority"]["approved"])
        self.assertFalse(result["authority"]["observed"])
        self.assertFalse(result["authority"]["answer"])

        def asserted_product_claims(value):
            if isinstance(value, Mapping):
                for key, child in value.items():
                    if key in {"manufacturing_ready",
                               "manufacturing_certified"} and child is True:
                        yield key
                    yield from asserted_product_claims(child)
            elif isinstance(value, list):
                for child in value:
                    yield from asserted_product_claims(child)

        self.assertEqual([], list(asserted_product_claims(result)))
        self.assertTrue(all(
            operation["parameters"]["state"] == "PROPOSED"
            and operation["parameters"]["authority"] == "PROPOSED"
            for candidate in result["candidates"]
            for operation in candidate["operations"]
        ))

    def test_two_layered_trouser_units_compile_as_two_physical_pairs(self):
        parts = []
        for unit, layer, circumference in (
                ("outer-pants", 1, 44.0), ("legging-underlayer", 0, 38.0)):
            left_id, right_id = f"{unit}-left", f"{unit}-right"
            parts.extend([
                part(left_id, "TUBE",
                     {"length_cm": 90.0, "circumference_cm": circumference},
                     layer=layer, placement="left leg", garment_unit=unit,
                     side="left", shape="trouser_leg",
                     detail_role="trouser_leg", quantity=1),
                part(right_id, "TUBE",
                     {"length_cm": 90.0, "circumference_cm": circumference},
                     layer=layer, placement="right leg", garment_unit=unit,
                     side="right", shape="trouser_leg",
                     detail_role="trouser_leg", quantity=1),
                part(f"{unit}-gusset", "GUSSET",
                     {"length_cm": 16.0, "width_cm": 8.0},
                     layer=layer, placement="center crotch", garment_unit=unit,
                     attached_to=[left_id, right_id], side="center",
                     shape="trousers", detail_role="trouser_gusset",
                     quantity=1),
            ])
        result = apply_parts_ir_topology(completion(parts))
        self.assertEqual("PROPOSED", result["verdict"])
        for candidate in result["candidates"]:
            crotch = [operation for operation in candidate["operations"]
                      if operation["kind"] == "JOIN"]
            self.assertEqual(4, len(crotch))
            self.assertEqual({
                frozenset(("outer-pants-left", "outer-pants-gusset")),
                frozenset(("outer-pants-right", "outer-pants-gusset")),
                frozenset(("legging-underlayer-left",
                           "legging-underlayer-gusset")),
                frozenset(("legging-underlayer-right",
                           "legging-underlayer-gusset")),
            }, {
                frozenset((operation["source"]["node_id"],
                           operation["target"]["node_id"]))
                for operation in crotch
            })
            self.assertEqual("ANSWER",
                             garment_structure.validate(candidate)["verdict"])

    def test_complete_trousers_require_two_sides_gusset_and_shared_unit(self):
        trousers = [
            part("body", "BODY_SHELL",
                 {"height_cm": 42.0, "circumference_cm": 90.0,
                  "bottom_circumference_cm": 80.0},
                 garment_unit="jumpsuit"),
            part("leg-left", "TUBE",
                 {"length_cm": 100.0, "circumference_cm": 40.0},
                 placement="lower left", garment_unit="jumpsuit",
                 attached_to="body", side="left", shape="trouser_leg",
                 quantity=1),
            part("leg-right", "TUBE",
                 {"length_cm": 100.0, "circumference_cm": 40.0},
                 placement="lower right", garment_unit="jumpsuit",
                 attached_to="body", side="right", shape="trouser_leg",
                 quantity=1),
            part("crotch", "GUSSET", {"length_cm": 18.0, "width_cm": 8.0},
                 placement="crotch", garment_unit="jumpsuit",
                 attached_to=["leg-left", "leg-right"], side="center",
                 detail_role="trouser_gusset", quantity=1),
        ]
        result = apply_parts_ir_topology(completion(trousers))
        self.assertEqual(result["verdict"], "PROPOSED")
        for candidate in result["candidates"]:
            joins = [op for op in candidate["operations"]
                     if op["kind"] == "JOIN"]
            self.assertEqual(len(joins), 4)
            self.assertEqual(garment_structure.validate(candidate)["verdict"],
                             "ANSWER")

        incomplete = [row for row in trousers if row["part_id"] != "leg-right"]
        result = apply_parts_ir_topology(completion(incomplete))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_INCOMPLETE")

        bad_side = copy.deepcopy(trousers)
        bad_side[2]["side"] = "left"
        result = apply_parts_ir_topology(completion(bad_side))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_SIDE")

        no_role = copy.deepcopy(trousers)
        del no_role[3]["detail_role"]
        result = apply_parts_ir_topology(completion(no_role))
        self.assertEqual(result["verdict"], "PROPOSED")

    def test_standalone_trousers_do_not_require_a_fake_upper_body(self):
        trousers = [
            part("leg-left", "TUBE",
                 {"length_cm": 100.0, "circumference_cm": 40.0},
                 placement="lower left", garment_unit="trousers",
                 side="left", shape="trouser_leg", quantity=1),
            part("leg-right", "TUBE",
                 {"length_cm": 100.0, "circumference_cm": 40.0},
                 placement="lower right", garment_unit="trousers",
                 side="right", shape="trouser_leg", quantity=1),
            part("crotch", "GUSSET", {"length_cm": 18.0, "width_cm": 8.0},
                 placement="crotch", garment_unit="trousers",
                 attached_to=["leg-left", "leg-right"], side="center",
                 detail_role="trouser_gusset", quantity=1),
        ]
        result = apply_parts_ir_topology(completion(trousers))
        self.assertEqual(result["verdict"], "PROPOSED")
        for candidate in result["candidates"]:
            self.assertEqual(len(candidate["operations"]), 2)
            self.assertEqual({
                frozenset((op["source"]["node_id"],
                           op["target"]["node_id"]))
                for op in candidate["operations"]
            }, {
                frozenset(("crotch", "leg-left")),
                frozenset(("crotch", "leg-right")),
            })
            self.assertFalse(any(node["kind"] == "BODY_SHELL"
                                 for node in candidate["nodes"]))

        half_attached = copy.deepcopy(trousers)
        half_attached[0]["attached_to"] = "body"
        result = apply_parts_ir_topology(completion(half_attached))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_PARENT")

    def test_detached_sleeve_without_anchor_rule_is_unresolved(self):
        parts = [
            part("body", "BODY_SHELL",
                 {"height_cm": 42.0, "circumference_cm": 80.0},
                 garment_unit="look"),
            part("sleeve", "SLEEVE",
                 {"length_cm": 55.0, "upper_circumference_cm": 34.0,
                  "cuff_circumference_cm": 20.0},
                 placement="arms", garment_unit="look", side="bilateral",
                 shape="detached", quantity=2),
        ]
        result = apply_parts_ir_topology(completion(parts))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_DETACHED_SLEEVE_UNRESOLVED")

    def test_sleeve_to_sleeve_requires_typed_layer_or_extension_relation(self):
        body = part(
            "body", "BODY_SHELL",
            {"height_cm": 42.0, "circumference_cm": 82.0},
            garment_unit="look")
        inner = part(
            "inner-sleeve", "SLEEVE",
            {"length_cm": 36.0, "upper_circumference_cm": 34.0,
             "cuff_circumference_cm": 20.0},
            layer=1, placement="arms", garment_unit="look",
            attached_to="body", side="bilateral", shape="set_in",
            quantity=2)

        oversleeve = part(
            "outer-sleeve", "SLEEVE",
            {"length_cm": 52.0, "upper_circumference_cm": 40.0,
             "cuff_circumference_cm": 28.0},
            layer=2, placement="outer arm", garment_unit="look",
            attached_to="inner-sleeve", side="bilateral",
            detail_role="oversleeve", attachment_relation="LAYER",
            quantity=2)
        layered = apply_parts_ir_topology(completion(
            [body, inner, oversleeve]))
        self.assertEqual(layered["verdict"], "PROPOSED", layered)
        for candidate in layered["candidates"]:
            layer_op = next(
                op for op in candidate["operations"]
                if op["operation_id"]
                == "layer-outer-sleeve-on-inner-sleeve")
            self.assertEqual(layer_op["kind"], "LAYER")
            self.assertFalse(layer_op["parameters"]["seam_join_created"])
            self.assertEqual(
                layer_op["parameters"]["attachment_relation"], "LAYER")
            delegated = candidate["topology"]["delegated_relations"]
            self.assertTrue(any(
                row["node_id"] == "outer-sleeve"
                and row["rule"]
                == "DELEGATED_EXPLICIT_OVERSLEEVE_LAYER_ANCHOR"
                and not row["primitive_join_created"]
                for row in delegated))

        extension = part(
            "lower-sleeve", "SLEEVE",
            {"length_cm": 28.0, "upper_circumference_cm": 20.0,
             "cuff_circumference_cm": 16.0},
            layer=1, placement="lower sleeve extension", garment_unit="look",
            attached_to="inner-sleeve", side="bilateral",
            shape="gauntlet", attachment_relation="JOIN", quantity=2)
        joined = apply_parts_ir_topology(completion(
            [body, inner, extension]))
        self.assertEqual(joined["verdict"], "PROPOSED", joined)
        for candidate in joined["candidates"]:
            join = next(
                op for op in candidate["operations"]
                if op["operation_id"].startswith(
                    "join-sleeve-extension-inner-sleeve-lower-sleeve"))
            self.assertEqual(join["kind"], "JOIN")
            nodes = {node["node_id"]: node for node in candidate["nodes"]}
            for endpoint in ("source", "target"):
                address = join[endpoint]
                port = next(
                    row for row in nodes[address["node_id"]]["ports"]
                    if row["port_id"] == address["port_id"])
                self.assertAlmostEqual(port["length_cm"], 20.0)

        ambiguous = copy.deepcopy(oversleeve)
        ambiguous["layer"] = 1
        ambiguous.pop("detail_role")
        ambiguous.pop("attachment_relation")
        ambiguous["placement"] = "arms"
        refused = apply_parts_ir_topology(completion([body, inner, ambiguous]))
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_TARGET")

        inverted = copy.deepcopy(oversleeve)
        inverted["layer"] = 1
        refused = apply_parts_ir_topology(completion([body, inner, inverted]))
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_LAYER_ORDER")

        invalid_relation = copy.deepcopy(oversleeve)
        invalid_relation["attachment_relation"] = "SEW_SOMEHOW"
        refused_completion = completion([body, inner, invalid_relation])
        self.assertEqual(refused_completion["verdict"],
                         "UNKNOWN_PARTS_IR_INVALID_ATTACHMENT_RELATION")

        mismatched = copy.deepcopy(extension)
        mismatched["dimensions"]["upper_circumference_cm"] = 23.0
        refused = apply_parts_ir_topology(completion([body, inner, mismatched]))
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_JOIN_LENGTH_MISMATCH")

    def test_explicit_proposed_lower_sleeve_gather_preserves_dimensions(self):
        completed = completed_sleeve_gather()
        before = copy.deepcopy(completed)
        result = apply_parts_ir_topology(completed)
        self.assertEqual("PROPOSED", result["verdict"], result)
        self.assertEqual(before, completed)

        for candidate in result["candidates"]:
            nodes = {node["node_id"]: node for node in candidate["nodes"]}
            self.assertEqual(
                30.0,
                nodes["lower-sleeve"]["dimensions"][
                    "upper_circumference_cm"],
            )
            self.assertEqual(
                20.0,
                nodes["inner-sleeve"]["dimensions"][
                    "cuff_circumference_cm"],
            )
            gather = next(
                operation for operation in candidate["operations"]
                if operation["operation_id"] ==
                "gather-sleeve-extension-inner-sleeve-lower-sleeve")
            self.assertEqual("GATHER", gather["kind"])
            self.assertEqual("lower-sleeve", gather["source"]["node_id"])
            self.assertEqual("inner-sleeve", gather["target"]["node_id"])
            parameters = gather["parameters"]
            self.assertEqual(
                "GATHER_SLEEVE_SEGMENTS",
                parameters["construction_role"],
            )
            self.assertAlmostEqual(1.5, parameters["ratio"])
            self.assertEqual(30.0, parameters["source_length_cm"])
            self.assertEqual(20.0, parameters["target_length_cm"])
            self.assertFalse(parameters["dimensions_changed"])
            self.assertFalse(parameters["manufacturing_ready"])
            self.assertFalse(parameters["manufacturing_certified"])
            self.assertEqual("PROPOSED", parameters["truth"]["state"])
            self.assertFalse(parameters["truth"]["observed"])
            self.assertIsInstance(
                parameters["sleeve_join_provenance"], Mapping)
            self.assertEqual(
                "PROPOSED_RELATION_DERIVED",
                parameters["sleeve_join_provenance"]["authority"],
            )
            for endpoint, expected_length in (("source", 30.0),
                                              ("target", 20.0)):
                address = gather[endpoint]
                port = next(
                    row for row in nodes[address["node_id"]]["ports"]
                    if row["port_id"] == address["port_id"])
                self.assertEqual("edge", port["role"])
                self.assertEqual(expected_length, port["length_cm"])
            delegated = candidate["topology"]["delegated_relations"]
            self.assertTrue(any(
                row["node_id"] == "lower-sleeve"
                and row["rule"] ==
                "TYPED_LOWER_SLEEVE_EXTENSION_GATHER"
                and row["construction_role"] ==
                "GATHER_SLEEVE_SEGMENTS"
                and row["dimensions_changed"] is False
                and row["manufacturing_ready"] is False
                for row in delegated))
            self.assertEqual(
                "ANSWER", garment_structure.validate(candidate)["verdict"])

    def test_lower_sleeve_gather_refuses_authority_and_provenance_errors(self):
        observed = apply_parts_ir_topology(completed_sleeve_gather(
            state="OBSERVED"))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_AUTHORITY",
            observed["verdict"],
        )
        self.assertEqual("sleeve_join_state", observed["field"])

        missing = apply_parts_ir_topology(completed_sleeve_gather(
            provenance=...))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_PROVENANCE",
            missing["verdict"],
        )
        self.assertEqual("sleeve_join_provenance", missing["field"])

        malformed = apply_parts_ir_topology(completed_sleeve_gather(
            provenance=["not", "a", "mapping"]))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_PROVENANCE",
            malformed["verdict"],
        )

        elevated = apply_parts_ir_topology(completed_sleeve_gather(
            provenance={"state": "OBSERVED"}))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_AUTHORITY",
            elevated["verdict"],
        )
        self.assertEqual(
            "sleeve_join_provenance.state", elevated["field"])

        for authority in ("OBSERVED", "ANSWER", "APPROVED"):
            with self.subTest(authority=authority):
                elevated_authority = apply_parts_ir_topology(
                    completed_sleeve_gather(provenance={
                        "state": "PROPOSED",
                        "authority": authority,
                    }))
                self.assertEqual(
                    "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_AUTHORITY",
                    elevated_authority["verdict"],
                )
                self.assertEqual(
                    "sleeve_join_provenance.authority",
                    elevated_authority["field"],
                )

        edited = apply_parts_ir_topology(completed_sleeve_gather(
            provenance={"state": "PROPOSED", "dimensions_changed": True}))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_PROVENANCE",
            edited["verdict"],
        )

    def test_lower_sleeve_gather_refuses_unbounded_or_nonreducing_geometry(self):
        bounded = apply_parts_ir_topology(completed_sleeve_gather(
            child_upper=60.0))
        self.assertEqual("PROPOSED", bounded["verdict"], bounded)
        for candidate in bounded["candidates"]:
            gather = next(operation for operation in candidate["operations"]
                          if operation["kind"] == "GATHER")
            self.assertEqual(3.0, gather["parameters"]["ratio"])

        too_large = apply_parts_ir_topology(completed_sleeve_gather(
            child_upper=60.01))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_RATIO",
            too_large["verdict"],
        )
        self.assertGreater(too_large["ratio"], 3.0)
        self.assertEqual(3.0, too_large["maximum"])

        equal = apply_parts_ir_topology(completed_sleeve_gather(
            child_upper=20.0))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_NOT_LONGER",
            equal["verdict"],
        )

        untyped = apply_parts_ir_topology(completed_sleeve_gather(
            lower_extension=False))
        self.assertEqual(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_SEMANTICS",
            untyped["verdict"],
        )

    def test_missing_candidate_and_unknown_attachment_are_typed(self):
        completed = completion(dress_parts())
        completed["candidates"] = completed["candidates"][:1]
        result = apply_parts_ir_topology(completed)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_CANDIDATES_INSUFFICIENT")

        missing = dress_parts()
        missing[2]["attached_to"] = "not-a-node"
        result = apply_parts_ir_topology(completion(missing))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_TARGET_MISSING")

    def test_output_and_digests_are_deterministic_and_never_elevated(self):
        completed = completion(dress_parts())
        first = apply_parts_ir_topology(completed)
        second = apply_parts_ir_topology(completed)
        self.assertEqual(first, second)
        self.assertEqual(len({row["structure_digest"]
                              for row in first["candidates"]}), 2)

        def scalar_values(value):
            if isinstance(value, Mapping):
                for child in value.values():
                    yield from scalar_values(child)
            elif isinstance(value, list):
                for child in value:
                    yield from scalar_values(child)
            else:
                yield value

        authority_values = {value for value in scalar_values(first)
                            if isinstance(value, str)
                            and value in {"ANSWER", "OBSERVED", "APPROVED"}}
        self.assertEqual(authority_values, set())


if __name__ == "__main__":
    unittest.main()
