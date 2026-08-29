#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import garment_structure
from photoloset.parts_ir_completion import (
    bounded_preview_profile,
    complete_parts_ir,
)
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline
from photoloset.parts_ir_topology import apply_parts_ir_topology


def visible(basis="front image proposal"):
    return {
        "state": "PROPOSED",
        "basis": basis,
        "breaks_when": "another view or construction review contradicts it",
    }


def body(part_id):
    return {
        "part_id": part_id,
        "kind": "BODY_SHELL",
        "layer": 0,
        "placement": "torso",
        "visible_basis": visible("front image suggests a torso shell"),
        "dimensions": {"height_cm": 44.0, "circumference_cm": 92.0},
        "garment_unit": "look",
    }


ORNAMENTS = (
    ("bow", "BOW", {
        "body_length_cm": 24.0, "body_width_cm": 8.0,
        "knot_length_cm": 7.0, "knot_width_cm": 3.0,
    }, {}),
    ("ribbon", "RIBBON", {
        "length_cm": 52.0, "width_cm": 4.0,
    }, {"attachment_mode": "END"}),
    ("rosette", "ROSETTE", {
        "strip_length_cm": 72.0, "strip_width_cm": 4.0,
        "finished_inner_length_cm": 18.0,
    }, {}),
    ("tie", "TIE", {
        "length_cm": 35.0, "top_width_cm": 7.0,
        "tip_width_cm": 2.0,
    }, {}),
    ("flap", "FLAP", {
        "attachment_width_cm": 12.0, "depth_cm": 8.0,
        "outer_width_cm": 9.0,
    }, {}),
)


def ornament(part_id, kind, dimensions, target_id, **extra):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": 2,
        "placement": "front decoration",
        "visible_basis": visible(f"front image suggests {kind.lower()}"),
        "dimensions": copy.deepcopy(dimensions),
        "quantity": 1,
        "grain_direction": "BIAS_45",
        "seam_allowance_cm": 0.8,
        "attached_to": target_id,
        "target_port_id": "center-front",
    }
    row.update(extra)
    return row


def candidate(suffix):
    body_id = f"body-{suffix}"
    parts = [body(body_id)]
    parts.extend(
        ornament(f"{name}-{suffix}", kind, dimensions, body_id, **extra)
        for name, kind, dimensions, extra in ORNAMENTS
    )
    return {"candidate_id": f"ornament-{suffix}", "parts": parts}


def two_candidates():
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [candidate("a"), candidate("b")],
    }


class OrnamentPipelineIntegrationTests(unittest.TestCase):
    def test_all_ornaments_survive_completion_as_real_proposed_artifacts(self):
        request = two_candidates()
        frozen = copy.deepcopy(request)
        result = complete_parts_ir(request)
        self.assertEqual(result["verdict"], "PROPOSED", result)
        self.assertEqual(request, frozen)
        self.assertTrue(result["provenance"]["ornament_route_used"])
        self.assertFalse(result["provenance"]["ornaments_silently_dropped"])

        for completed in result["candidates"]:
            self.assertEqual([node["kind"] for node in completed["nodes"]],
                             ["BODY_SHELL"])
            artifacts = completed["ornament_artifacts"]
            self.assertEqual(artifacts["state"], "PROPOSED")
            self.assertEqual(artifacts["readiness"], "MATERIALIZED")
            self.assertEqual(artifacts["ornament_count"], 5)
            self.assertEqual(artifacts["materialized_ornament_count"], 5)
            self.assertEqual(
                {row["kind"] for row in artifacts["result_manifest"]},
                {"BOW", "RIBBON", "ROSETTE", "TIE", "FLAP"},
            )
            self.assertEqual(
                {piece["role"] for piece in artifacts["pattern_pieces"]},
                {"bow_body", "bow_center_wrap", "ribbon_strip",
                 "rosette_gather_strip", "tapered_tie", "flap"},
            )
            self.assertEqual(len(artifacts["attachment_ports"]), 5)
            self.assertTrue(artifacts["seam_intents"])
            self.assertEqual(
                [row["order"] for row in artifacts["seam_intents"]],
                list(range(1, len(artifacts["seam_intents"]) + 1)),
            )
            self.assertTrue(all(
                piece["state"] == "PROPOSED"
                and piece["geometry_authority"]["observed"] is False
                for piece in artifacts["pattern_pieces"]
            ))
            self.assertTrue(all(
                port["state"] == "PROPOSED" and port["observed"] is False
                for port in artifacts["attachment_ports"]
            ))
            self.assertTrue(all(
                intent["state"] == "PROPOSED"
                for intent in artifacts["seam_intents"]
            ))
            self.assertFalse(artifacts["authority"]["observed"])
            self.assertFalse(artifacts["authority"]["approved"])

    def test_topology_binds_targets_and_preserves_pieces_ports_and_intents(self):
        completed = complete_parts_ir(two_candidates())
        before = copy.deepcopy(completed)
        result = apply_parts_ir_topology(completed)
        self.assertEqual(result["verdict"], "PROPOSED", result)
        self.assertEqual(completed, before)

        for source, topologized in zip(completed["candidates"],
                                       result["candidates"]):
            self.assertEqual(garment_structure.validate(topologized)["verdict"],
                             "ANSWER")
            old = source["ornament_artifacts"]
            new = topologized["ornament_artifacts"]
            self.assertEqual(new["pattern_pieces"], old["pattern_pieces"])
            self.assertEqual(
                [row["intent_id"] for row in new["seam_intents"]],
                [row["intent_id"] for row in old["seam_intents"]],
            )
            self.assertTrue(new["topology_binding"]["all_targets_resolved"])
            self.assertEqual(len(new["topology_binding"]["resolved"]), 5)
            self.assertEqual(new["topology_binding"]["unresolved"], [])
            body_id = topologized["nodes"][0]["node_id"]
            for port in new["attachment_ports"]:
                binding = port["topology_binding"]
                self.assertEqual(binding["state"], "PROPOSED")
                self.assertEqual(binding["target_node_id"], body_id)
                self.assertTrue(binding["target_node_resolved"])
                self.assertFalse(binding["observed"])
            attach_intents = [
                row for row in new["seam_intents"]
                if row["kind"] == "ATTACH_TO_GARMENT"
            ]
            self.assertEqual(len(attach_intents), 5)
            self.assertTrue(all(
                row["topology_binding"]["target_node_id"] == body_id
                for row in attach_intents
            ))

    def test_existing_pipeline_keeps_candidate_bound_ornament_extension(self):
        result = run_parts_ir_pipeline(
            two_candidates(), preview_profile=bounded_preview_profile())
        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])
        self.assertEqual(result["successful_candidate_count"], 2)
        for row in result["candidates"]:
            self.assertEqual(row["execution_status"], "SUCCEEDED")
            completed = row["completion_candidate"]["ornament_artifacts"]
            topologized = row["structure"]["ornament_artifacts"]
            self.assertEqual(completed["ornament_count"], 5)
            self.assertEqual(len(topologized["pattern_pieces"]), 6)
            self.assertEqual(len(topologized["attachment_ports"]), 5)
            self.assertEqual(len(topologized["seam_intents"]), 15)
            self.assertEqual(topologized["candidate_id"], row["candidate_id"])
            self.assertEqual(
                topologized["topology_structure_digest"],
                row["structure_digest"],
            )

    def test_unattached_geometry_is_retained_as_review_not_guessed(self):
        request = two_candidates()
        for row in request["candidates"]:
            flap = next(part for part in row["parts"] if part["kind"] == "FLAP")
            flap.pop("attached_to")
            flap.pop("target_port_id")
        completed = complete_parts_ir(request)
        self.assertEqual(completed["verdict"], "PROPOSED", completed)
        for row in completed["candidates"]:
            artifacts = row["ornament_artifacts"]
            self.assertEqual(artifacts["readiness"], "REVIEW")
            self.assertTrue(any(piece["role"] == "flap"
                                for piece in artifacts["pattern_pieces"]))
            self.assertTrue(any(item["kind"] == "FLAP"
                                for item in artifacts["unresolved"]))

        topologized = apply_parts_ir_topology(completed)
        self.assertEqual(topologized["verdict"], "PROPOSED", topologized)
        for row in topologized["candidates"]:
            binding = row["ornament_artifacts"]["topology_binding"]
            self.assertFalse(binding["all_targets_resolved"])
            self.assertEqual(len(binding["unresolved"]), 1)
            self.assertEqual(binding["unresolved"][0]["state"], "REVIEW")
            self.assertFalse(binding["image_attachment_inference"])

    def test_unknown_target_and_image_authority_escalation_fail_explicitly(self):
        missing_target_request = two_candidates()
        for row in missing_target_request["candidates"]:
            bow = next(part for part in row["parts"] if part["kind"] == "BOW")
            bow["attached_to"] = "not-a-node"
        completed = complete_parts_ir(missing_target_request)
        self.assertEqual(completed["verdict"], "PROPOSED", completed)
        refused = apply_parts_ir_topology(completed)
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_TARGET_MISSING")
        self.assertIn("ornament port", refused["why"])

        promoted = two_candidates()
        promoted["candidates"][0]["parts"][1]["visible_basis"]["state"] = (
            "OBSERVED")
        authority = complete_parts_ir(promoted)
        self.assertEqual(authority["verdict"],
                         "UNKNOWN_ORNAMENT_AUTHORITY_ESCALATION")
        self.assertIn("ornament_routing", authority)

        tampered = complete_parts_ir(two_candidates())
        tampered["candidates"][0]["ornament_artifacts"]["pattern_pieces"][0][
            "state"] = "OBSERVED"
        topological_authority = apply_parts_ir_topology(tampered)
        self.assertEqual(
            topological_authority["verdict"],
            "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_AUTHORITY_ESCALATION",
        )


if __name__ == "__main__":
    unittest.main()
