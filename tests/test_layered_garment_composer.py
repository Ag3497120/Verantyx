#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import garment_structure
from photoloset.layered_garment_composer import (
    REQUEST_SCHEMA,
    compose,
)


def boundary(boundary_id, length_cm, interface, *, visibility="FRONT_VISIBLE",
             state="PROPOSED", role="loop"):
    return {
        "boundary_id": boundary_id,
        "length_cm": length_cm,
        "interface": interface,
        "role": role,
        "visibility": visibility,
        "state": state,
        "basis": f"typed boundary proposal for {boundary_id}",
        "breaks_when": f"another view changes {boundary_id}",
    }


def component(component_id, primitive_kind, dimensions, *, boundaries=(),
              layer=0, zones=(), role="geometric component", unit=None,
              rear=None, material=None):
    row = {
        "component_id": component_id,
        "primitive_kind": primitive_kind,
        "dimensions": dimensions,
        "boundaries": list(boundaries),
        "layer": layer,
        "coverage_zones": list(zones),
        "semantic_role": role,
        "garment_unit": unit or component_id,
    }
    if rear is not None:
        row["rear"] = rear
    if material is not None:
        row["material"] = material
    return row


def alternative(alternative_id, relation, source_component, source_boundary,
                target_component, target_boundary, *, zone="waist"):
    return {
        "alternative_id": alternative_id,
        "relation": relation,
        "source": {"component_id": source_component,
                   "boundary_id": source_boundary},
        "target": {"component_id": target_component,
                   "boundary_id": target_boundary},
        "state": "PROPOSED",
        "contact_zone": zone,
        "basis": f"{alternative_id} is a feasible front-preserving topology",
        "breaks_when": "a rear view or construction review rejects it",
    }


def request(components, choices=(), source_id="fixture:front"):
    return {
        "schema": REQUEST_SCHEMA,
        "source_id": source_id,
        "front_only": True,
        "components": list(components),
        "attachment_choices": list(choices),
    }


class LayeredGarmentComposerTests(unittest.TestCase):
    def assert_valid_candidate(self, candidate):
        checked = garment_structure.validate(candidate["structure_graph"])
        self.assertEqual(checked["verdict"], "ANSWER", checked)
        self.assertFalse(candidate["manufacturing_ready"])
        self.assertFalse(candidate["manufacturing_certified"])

    def test_top_and_skirt_can_remain_separate_without_a_garment_class(self):
        upper = component(
            "upper-shell", "BODY_SHELL",
            {"height_cm": 42, "circumference_cm": 92},
            boundaries=[boundary("waist", 74, "waist")],
            zones=["torso"], role="upper volume", unit="upper-unit")
        lower = component(
            "lower-flare", "FLARE",
            {"height_cm": 61, "top_circumference_cm": 74,
             "bottom_circumference_cm": 160},
            boundaries=[boundary("waist", 74, "waist")],
            zones=["lower-body"], role="single lower volume", unit="lower-unit")
        choices = [{
            "choice_id": "waist-topology",
            "alternatives": [alternative(
                "independent-units", "SEPARATE", "upper-shell", "waist",
                "lower-flare", "waist")],
        }]
        result = compose(request([upper, lower], choices))
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["candidate_count"], 1)
        candidate = result["candidates"][0]
        self.assert_valid_candidate(candidate)
        self.assertEqual(candidate["structure_graph"]["operations"], [])
        self.assertEqual(candidate["constraints"]["attachment"][0]["relation"],
                         "SEPARATE")
        self.assertFalse(result["claims"]["garment_name_classification_used"])

    def test_single_lower_volume_joins_to_upper_as_one_piece(self):
        upper = component(
            "upper", "BODY_SHELL", {"height_cm": 44, "circumference_cm": 94},
            boundaries=[boundary("lower-loop", 76, "waist")], zones=["torso"])
        lower = component(
            "lower", "FLARE",
            {"height_cm": 70, "top_circumference_cm": 76,
             "bottom_circumference_cm": 190},
            boundaries=[boundary("upper-loop", 76, "waist")], zones=["lower-body"])
        choices = [{"choice_id": "continuous-waist", "alternatives": [
            alternative("sewn-waist", "JOIN", "upper", "lower-loop",
                        "lower", "upper-loop")]}]
        result = compose(request([upper, lower], choices, "fixture:one-piece"))
        self.assertEqual(result["verdict"], "PROPOSED")
        graph = result["candidates"][0]["structure_graph"]
        self.assertEqual([row["kind"] for row in graph["operations"]], ["JOIN"])
        self.assert_valid_candidate(result["candidates"][0])

    def test_two_tubes_and_gusset_compose_a_split_lower_one_piece(self):
        upper = component(
            "upper", "BODY_SHELL", {"height_cm": 43, "circumference_cm": 92},
            boundaries=[boundary("waist-left", 37, "waist-half", role="edge"),
                        boundary("waist-right", 37, "waist-half", role="edge")])
        left = component(
            "left-volume", "TUBE", {"length_cm": 101, "circumference_cm": 58},
            boundaries=[boundary("waist", 37, "waist-half", role="edge"),
                        boundary("crotch", 18, "crotch", role="edge")],
            zones=["left-lower"])
        right = component(
            "right-volume", "TUBE", {"length_cm": 101, "circumference_cm": 58},
            boundaries=[boundary("waist", 37, "waist-half", role="edge"),
                        boundary("crotch", 18, "crotch", role="edge")],
            zones=["right-lower"])
        gusset = component(
            "center-gusset", "GUSSET", {"length_cm": 18, "width_cm": 8},
            boundaries=[boundary("left", 18, "crotch", role="edge"),
                        boundary("right", 18, "crotch", role="edge")],
            zones=["crotch"])
        joins = [
            ("upper-left", "upper", "waist-left", "left-volume", "waist"),
            ("upper-right", "upper", "waist-right", "right-volume", "waist"),
            ("gusset-left", "center-gusset", "left", "left-volume", "crotch"),
            ("gusset-right", "center-gusset", "right", "right-volume", "crotch"),
        ]
        choices = [{"choice_id": name, "alternatives": [alternative(
            "joined", "JOIN", source, source_port, target, target_port,
            zone="lower-assembly")]} for name, source, source_port, target,
            target_port in joins]
        result = compose(request(
            [upper, left, right, gusset], choices, "fixture:split-lower"))
        candidate = result["candidates"][0]
        self.assert_valid_candidate(candidate)
        self.assertEqual(
            {row["kind"] for row in candidate["structure_graph"]["nodes"]},
            {"BODY_SHELL", "TUBE", "GUSSET"})
        self.assertEqual(len(candidate["structure_graph"]["operations"]), 4)

    def test_underlayer_and_overlay_emit_layer_and_contact_constraints(self):
        inner = component(
            "inner-shell", "BODY_SHELL", {"height_cm": 50, "circumference_cm": 88},
            boundaries=[boundary("anchor", 1, "layer-anchor", role="point")],
            layer=0, zones=["torso"], role="underlayer")
        outer = component(
            "outer-panel", "OVERLAY", {"height_cm": 46, "width_cm": 54},
            boundaries=[boundary("anchor", 1, "layer-anchor", role="point")],
            layer=1, zones=["torso"], role="overlay")
        choices = [{"choice_id": "overlay-order", "alternatives": [
            alternative("outer-over-inner", "LAYER", "outer-panel", "anchor",
                        "inner-shell", "anchor", zone="torso")]}]
        result = compose(request([inner, outer], choices, "fixture:layered"))
        candidate = result["candidates"][0]
        self.assert_valid_candidate(candidate)
        self.assertEqual(candidate["structure_graph"]["operations"][0]["kind"],
                         "LAYER")
        self.assertEqual(candidate["constraints"]["layer_order"][0][
            "outer_component_id"], "outer-panel")
        self.assertTrue(all(row["friction"] == "UNKNOWN_MATERIAL_REQUIRED"
                            for row in candidate["constraints"]["contact"]))

    def test_multiple_feasible_waist_topologies_require_human_choice(self):
        upper = component(
            "upper", "BODY_SHELL", {"height_cm": 42, "circumference_cm": 90},
            boundaries=[boundary("waist", 74, "waist")])
        lower = component(
            "lower", "FLARE",
            {"height_cm": 64, "top_circumference_cm": 74,
             "bottom_circumference_cm": 170},
            boundaries=[boundary("waist", 74, "waist")])
        choices = [{"choice_id": "waist-topology", "alternatives": [
            alternative("one-piece", "JOIN", "upper", "waist", "lower", "waist"),
            alternative("separates", "SEPARATE", "upper", "waist", "lower", "waist"),
        ]}]
        result = compose(request([upper, lower], choices, "fixture:ambiguous"))
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertEqual(result["reason_code"],
                         "REVIEW_JOIN_TOPOLOGY_CHOICE_REQUIRED")
        self.assertEqual(result["candidate_count"], 2)
        self.assertTrue(result["human_choice"]["required"])
        self.assertIsNone(result["human_choice"]["selected_candidate_id"])
        self.assertTrue(result["claims"]["candidate_auto_selected"] is False)

    def test_opposite_layer_orders_remain_separate_human_choices(self):
        first = component(
            "panel-a", "OVERLAY", {"height_cm": 45, "width_cm": 52},
            boundaries=[boundary("anchor", 1, "layer-anchor", role="point")],
            zones=["torso"])
        second = component(
            "panel-b", "OVERLAY", {"height_cm": 43, "width_cm": 50},
            boundaries=[boundary("anchor", 1, "layer-anchor", role="point")],
            zones=["torso"])
        choices = [{"choice_id": "inside-outside", "alternatives": [
            alternative("a-over-b", "LAYER", "panel-a", "anchor",
                        "panel-b", "anchor", zone="torso"),
            alternative("b-over-a", "LAYER", "panel-b", "anchor",
                        "panel-a", "anchor", zone="torso"),
        ]}]
        result = compose(request([first, second], choices, "fixture:layer-order"))
        self.assertEqual(result["candidate_count"], 2)
        orders = {(row["constraints"]["layer_order"][0]["outer_component_id"],
                   row["constraints"]["layer_order"][0]["inner_component_id"])
                  for row in result["candidates"]}
        self.assertEqual(orders, {("panel-a", "panel-b"),
                                  ("panel-b", "panel-a")})
        self.assertTrue(result["human_choice"]["required"])

    def test_rear_material_and_occluded_boundaries_cannot_be_observed(self):
        base = component(
            "shell", "BODY_SHELL", {"height_cm": 42, "circumference_cm": 90},
            boundaries=[boundary("hidden", 40, "rear-seam",
                                 visibility="OCCLUDED", state="OBSERVED")])
        result = compose(request([base]))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_OCCLUDED_BOUNDARY_AUTHORITY_ESCALATION")

        base = component(
            "shell", "BODY_SHELL", {"height_cm": 42, "circumference_cm": 90},
            rear={"state": "OBSERVED", "basis": "model guess",
                  "breaks_when": "rear image arrives"})
        self.assertEqual(compose(request([base]))["verdict"],
                         "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION")

        base = component(
            "shell", "BODY_SHELL", {"height_cm": 42, "circumference_cm": 90},
            material={"state": "OBSERVED", "basis": "appearance",
                      "breaks_when": "material is measured"})
        self.assertEqual(compose(request([base]))["verdict"],
                         "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION")

    def test_component_and_choice_order_do_not_change_digest(self):
        upper = component(
            "upper", "BODY_SHELL", {"height_cm": 42, "circumference_cm": 90},
            boundaries=[boundary("waist", 74, "waist")])
        lower = component(
            "lower", "FLARE",
            {"height_cm": 64, "top_circumference_cm": 74,
             "bottom_circumference_cm": 170},
            boundaries=[boundary("waist", 74, "waist")])
        overlay = component(
            "overlay", "OVERLAY", {"height_cm": 40, "width_cm": 50},
            boundaries=[boundary("anchor", 1, "layer-anchor", role="point")],
            layer=1)
        upper["boundaries"].append(
            boundary("anchor", 1, "layer-anchor", role="point"))
        waist_choice = {"choice_id": "waist", "alternatives": [
            alternative("joined", "JOIN", "upper", "waist", "lower", "waist")]}
        layer_choice = {"choice_id": "layer", "alternatives": [
            alternative("outer", "LAYER", "overlay", "anchor", "upper", "anchor",
                        zone="torso")]}
        first_request = request(
            [upper, lower, overlay], [waist_choice, layer_choice], "fixture:stable")
        second_request = request(
            [copy.deepcopy(overlay), copy.deepcopy(lower), copy.deepcopy(upper)],
            [copy.deepcopy(layer_choice), copy.deepcopy(waist_choice)],
            "fixture:stable")
        first = compose(first_request)
        second = compose(second_request)
        self.assertEqual(first, second)
        self.assertEqual(first["digest"], second["digest"])
        self.assertFalse(first["manufacturing_ready"])


if __name__ == "__main__":
    unittest.main()
