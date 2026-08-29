#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset import garment_structure
from photoloset.front_layered_composition import (
    REQUEST_SCHEMA,
    compose,
)


def visible(part_id, *, state="PROPOSED"):
    return {
        "state": state,
        "basis": f"front geometry supports {part_id}",
        "breaks_when": f"another view or reviewer rejects {part_id}",
    }


def part(part_id, kind, dimensions, *, placement, unit="look", layer=0,
         **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "dimensions": copy.deepcopy(dimensions),
        "placement": placement,
        "garment_unit": unit,
        "layer": layer,
        "visible_basis": visible(part_id),
    }
    row.update(semantics)
    return row


def candidate(parts, candidate_id="front-a", **extra):
    row = {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": copy.deepcopy(parts),
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": "center-back opening alternative",
            "basis": "the rear is absent from the front image",
            "breaks_when": "a rear or side view is supplied",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": "medium drape range",
            "basis": "appearance only bounds a material range",
            "breaks_when": "a swatch or material test is supplied",
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    row.update(extra)
    return row


def request(*candidates):
    return {
        "schema": REQUEST_SCHEMA,
        "front_only": True,
        "source": {"image_id": "fixture:front", "view": "front"},
        "candidates": list(candidates),
    }


def body(part_id="body", *, unit="look", layer=0, **extra):
    return part(
        part_id, "BODY_SHELL",
        {"height_cm": 43.0, "circumference_cm": 90.0},
        placement="front torso", unit=unit, layer=layer, **extra,
    )


def skirt(part_id="skirt", *, unit="look", **extra):
    return part(
        part_id, "FLARE",
        {"height_cm": 64.0, "top_circumference_cm": 76.0,
         "bottom_circumference_cm": 172.0},
        placement="lower body", unit=unit, **extra,
    )


class FrontLayeredCompositionTests(unittest.TestCase):
    def assert_candidate_valid_and_bound(self, row, source_id, source_digest):
        checked = garment_structure.validate(row["structure_graph"])
        self.assertEqual(checked["verdict"], "ANSWER", checked)
        self.assertEqual(row["structure_graph"]["schema"],
                         "garment.structure.v1")
        self.assertEqual(row["source_candidate_id"], source_id)
        self.assertEqual(row["source_candidate_digest"], source_digest)
        self.assertEqual(row["source_binding"]["source_candidate_id"],
                         source_id)
        self.assertEqual(row["source_binding"]["source_candidate_digest"],
                         source_digest)
        self.assertFalse(row["manufacturing_ready"])
        self.assertFalse(row["manufacturing_certified"])

    def test_separated_top_and_bottom_remain_two_geometric_units(self):
        source = candidate([
            body(unit="upper-unit"),
            skirt(unit="lower-unit"),
        ])
        result = compose(request(source))
        self.assertEqual(result["verdict"], "PROPOSED", result)
        self.assertEqual(result["candidate_count"], 1)
        output = result["candidates"][0]
        source_digest = result["source_results"][0]["source_candidate_digest"]
        self.assert_candidate_valid_and_bound(output, "front-a", source_digest)
        self.assertEqual(output["structure_graph"]["operations"], [])
        self.assertEqual(output["constraints"]["attachment"][0]["relation"],
                         "SEPARATE")
        self.assertFalse(result["claims"]["garment_class_enum_added"])

    def test_one_piece_emits_a_join_without_a_garment_class(self):
        source = candidate([
            body(),
            skirt(attached_to="body", attachment_relation="JOIN"),
        ])
        result = compose(request(source))
        self.assertEqual(result["candidate_count"], 1)
        output = result["candidates"][0]
        self.assertEqual([operation["kind"]
                          for operation in output["structure_graph"]["operations"]],
                         ["JOIN"])
        self.assert_candidate_valid_and_bound(
            output, "front-a",
            result["source_results"][0]["source_candidate_digest"],
        )

    def test_two_legs_and_gusset_form_a_split_lower_structure(self):
        source = candidate([
            body(),
            part("leg-left", "TUBE",
                 {"length_cm": 99.0, "circumference_cm": 57.0},
                 placement="left lower leg", side="left"),
            part("leg-right", "TUBE",
                 {"length_cm": 99.0, "circumference_cm": 57.0},
                 placement="right lower leg", side="right"),
            part("crotch-gusset", "GUSSET",
                 {"length_cm": 18.0, "width_cm": 8.0},
                 placement="crotch"),
        ])
        result = compose(request(source))
        self.assertEqual(result["candidate_count"], 1, result)
        output = result["candidates"][0]
        kinds = {node["kind"] for node in output["structure_graph"]["nodes"]}
        self.assertEqual(kinds, {"BODY_SHELL", "TUBE", "GUSSET"})
        operations = output["structure_graph"]["operations"]
        self.assertEqual(len(operations), 4)
        self.assertTrue(all(row["kind"] == "JOIN" for row in operations))
        self.assert_candidate_valid_and_bound(
            output, "front-a",
            result["source_results"][0]["source_candidate_digest"],
        )

    def test_underlayer_and_overlay_emit_explicit_layer_and_contact(self):
        source = candidate([
            body("underlayer", layer=0,
                 semantic_role="close underlayer"),
            part("outer-panel", "OVERLAY",
                 {"height_cm": 46.0, "width_cm": 55.0},
                 placement="front torso overlay", layer=1,
                 semantic_role="overlay", attached_to="underlayer"),
        ])
        result = compose(request(source))
        output = result["candidates"][0]
        self.assertEqual(output["structure_graph"]["operations"][0]["kind"],
                         "LAYER")
        order = output["constraints"]["layer_order"][0]
        self.assertEqual(order["outer_component_id"], "outer-panel")
        self.assertEqual(order["inner_component_id"], "underlayer")
        self.assertTrue(output["constraints"]["contact"])
        self.assertTrue(all(row["state"] == "PROPOSED"
                            for row in output["constraints"]["attachment"]))

    def test_ornament_is_mapped_to_existing_geometry_and_attached_as_proposal(self):
        bow = part(
            "front-bow", "BOW",
            {"body_length_cm": 24.0, "body_width_cm": 8.0,
             "knot_length_cm": 7.0, "knot_width_cm": 3.0},
            placement="front torso decoration", layer=2,
            attached_to="body", detail_role="bow ornament",
        )
        result = compose(request(candidate([body(), bow])))
        output = result["candidates"][0]
        nodes = {node["node_id"]: node for node in output["structure_graph"]["nodes"]}
        self.assertEqual(nodes["front-bow"]["kind"], "OVERLAY")
        self.assertIn("source kind BOW",
                      nodes["front-bow"]["attributes"]["semantic_role"])
        attachment = output["constraints"]["attachment"][0]
        self.assertEqual(attachment["relation"], "JOIN")
        self.assertEqual(attachment["state"], "PROPOSED")
        self.assertFalse(result["claims"]["attachment_observed_from_front"])

    def test_ambiguous_waist_join_emits_join_and_separate_alternatives(self):
        source = candidate([body(), skirt()])
        result = compose(request(source))
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertEqual(result["candidate_count"], 2)
        self.assertTrue(result["human_choice"]["required"])
        operation_sets = {
            tuple(operation["kind"] for operation
                  in row["structure_graph"]["operations"])
            for row in result["candidates"]
        }
        self.assertEqual(operation_sets, {(), ("JOIN",)})
        self.assertIsNone(result["human_choice"]["selected_candidate_id"])
        self.assertFalse(result["claims"]["candidate_auto_selected"])

    def test_hidden_rear_material_and_attachment_cannot_be_observed(self):
        cases = []
        observed_rear = candidate([body()])
        observed_rear["rear_hypothesis"]["state"] = "OBSERVED"
        cases.append((observed_rear, "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION"))

        observed_material = candidate([body()])
        observed_material["material_hypothesis"]["state"] = "OBSERVED"
        cases.append((observed_material,
                      "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION"))

        hidden = body()
        hidden["placement"] = "rear hidden torso"
        hidden["visible_basis"]["state"] = "OBSERVED"
        cases.append((candidate([hidden]),
                      "UNKNOWN_HIDDEN_PART_AUTHORITY_ESCALATION"))

        observed_attachment = skirt(attached_to="body")
        observed_attachment["attachment_state"] = "OBSERVED"
        cases.append((candidate([body(), observed_attachment]),
                      "UNKNOWN_ATTACHMENT_AUTHORITY_ESCALATION"))

        for source, expected in cases:
            with self.subTest(expected=expected):
                result = compose(request(source))
                self.assertEqual(
                    result["verdict"],
                    "UNKNOWN_NO_LAYERED_STRUCTURE_ALTERNATIVE",
                )
                self.assertEqual(
                    result["source_candidate_failures"][0]["verdict"], expected)
                self.assertFalse(result["manufacturing_ready"])
                self.assertFalse(result["manufacturing_certified"])

    def test_part_order_is_deterministic_and_supplied_digest_is_preserved(self):
        parts = [body(), skirt(assembly="SEPARATE")]
        first = compose(request(candidate(parts)))
        second = compose(request(candidate(list(reversed(parts)))))
        self.assertEqual(first, second)

        supplied = candidate(parts, candidate_id="front-bound",
                             candidate_digest="sha256:upstream-candidate")
        result = compose(request(supplied))
        output = result["candidates"][0]
        self.assertEqual(output["source_candidate_id"], "front-bound")
        self.assertEqual(output["source_candidate_digest"],
                         "sha256:upstream-candidate")
        self.assertTrue(result["source_results"][0][
            "source_candidate_digest_supplied"])
        json.dumps(result, ensure_ascii=False, allow_nan=False)

    def test_explicit_attachment_choice_is_candidate_specific(self):
        base_parts = [body(), skirt()]
        choice = [{
            "choice_id": "waist-construction",
            "alternatives": [
                {
                    "alternative_id": "joined",
                    "relation": "JOIN",
                    "source": {"part_id": "body"},
                    "target": {"part_id": "skirt"},
                    "state": "PROPOSED",
                    "basis": "one-piece construction hypothesis",
                    "breaks_when": "construction review finds separate units",
                },
                {
                    "alternative_id": "separate",
                    "relation": "SEPARATE",
                    "source": {"part_id": "body"},
                    "target": {"part_id": "skirt"},
                    "state": "PROPOSED",
                    "basis": "two-piece construction hypothesis",
                    "breaks_when": "construction review finds a waist seam",
                },
            ],
        }]
        result = compose(request(
            candidate(base_parts, "candidate-a", attachment_choices=choice),
            candidate(base_parts, "candidate-b", attachment_choices=choice),
        ))
        self.assertEqual(result["candidate_count"], 4)
        by_source = {}
        for output in result["candidates"]:
            by_source.setdefault(output["source_candidate_id"], []).append(output)
        self.assertEqual(set(by_source), {"candidate-a", "candidate-b"})
        self.assertEqual({len(rows) for rows in by_source.values()}, {2})
        self.assertEqual(len({row["candidate_id"]
                              for row in result["candidates"]}), 4)
        self.assertTrue(all(not row["manufacturing_ready"]
                            for row in result["candidates"]))


if __name__ == "__main__":
    unittest.main()
