#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import garment_structure
from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def _visible(label):
    return {
        "state": "PROPOSED",
        "basis": f"front image proposes {label}",
        "breaks_when": "another view or construction review contradicts it",
    }


def _body(suffix):
    return {
        "part_id": f"body-{suffix}",
        "kind": "BODY_SHELL",
        "layer": 0,
        "placement": "torso",
        "visible_basis": _visible("a torso shell"),
        "dimensions": {"height_cm": 44.0, "circumference_cm": 92.0},
        "garment_unit": "look",
    }


_SPECS = (
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


def _ornament(name, kind, dimensions, suffix, **extra):
    row = {
        "part_id": f"{name}-{suffix}",
        "kind": kind,
        "layer": 2,
        "placement": "front decoration",
        "visible_basis": _visible(kind.lower()),
        "dimensions": copy.deepcopy(dimensions),
        "quantity": 1,
        "grain_direction": "BIAS_45",
        "seam_allowance_cm": 0.8,
        "attached_to": f"body-{suffix}",
        # BODY_SHELL has no exact semantic ornament port yet.  Keeping this
        # explicit proposal exercises the required REVIEW path without any
        # name/proximity inference by the pipeline.
        "target_port_id": "center-front",
    }
    row.update(extra)
    return row


def _candidate(suffix, *, missing_target=False, invalid_target=False):
    parts = [_body(suffix)]
    for name, kind, dimensions, extra in _SPECS:
        row = _ornament(name, kind, dimensions, suffix, **extra)
        if name == "flap" and missing_target:
            row.pop("attached_to")
            row.pop("target_port_id")
        if name == "bow" and invalid_target:
            row["attached_to"] = "not-a-candidate-node"
        parts.append(row)
    return {"candidate_id": f"candidate-{suffix}", "parts": parts}


def _request(first=None, second=None):
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [first or _candidate("a"), second or _candidate("b")],
    }


def _run(request):
    return run_parts_ir_pipeline(
        request, preview_profile=bounded_preview_profile(), radial_segments=8)


class PartsIRPipelineOrnamentOutputsTests(unittest.TestCase):
    maxDiff = None

    def test_all_materialized_ornaments_reach_every_final_artifact(self):
        result = _run(_request())
        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])
        self.assertEqual(result["successful_candidate_count"], 2)

        for row in result["candidates"]:
            self.assertEqual(row["execution_status"], "SUCCEEDED")
            source = row["structure"]["ornament_artifacts"]
            expected_piece_ids = {
                piece["piece_id"] for piece in source["pattern_pieces"]
            }
            expected_intent_ids = {
                intent["intent_id"] for intent in source["seam_intents"]
            }
            expected_port_ids = {
                port["port_id"] for port in source["attachment_ports"]
            }

            flat = row["flat_pattern"]
            manufacturing = row["manufacturing_preview"]
            sewing = row["sewing_plan"]
            flat_ids = {piece["piece_id"] for piece in flat["pieces"]}
            manufacturing_ids = {
                piece["piece_id"] for piece in manufacturing["pieces"]
            }
            sewing_intent_ids = {
                step.get("operation_id") for step in sewing["steps"]
            }
            self.assertTrue(expected_piece_ids <= flat_ids)
            self.assertTrue(expected_piece_ids <= manufacturing_ids)
            self.assertTrue(expected_intent_ids <= sewing_intent_ids)
            self.assertEqual(
                {port["port_id"] for port in
                 flat["ornament_artifacts"]["attachment_ports"]},
                expected_port_ids)
            self.assertEqual(
                {port["port_id"] for port in
                 manufacturing["ornament_artifacts"]["attachment_ports"]},
                expected_port_ids)
            self.assertEqual(
                {port["port_id"] for port in
                 sewing["ornament_artifacts"]["attachment_ports"]},
                expected_port_ids)
            self.assertEqual(
                {piece["primitive_kind"] for piece in flat["pieces"]
                 if piece["piece_id"] in expected_piece_ids},
                {"BOW", "RIBBON", "ROSETTE", "TIE", "FLAP"})

            binding = row["artifact_binding"]
            self.assertTrue(binding["same_structure_digest"])
            self.assertTrue(binding["all_downstream_artifacts_bound"])
            self.assertEqual(binding["pattern_digest"], flat["digest"])
            self.assertEqual(
                binding["ornament_topology_digest"],
                source["topology_digest"])
            self.assertEqual(
                binding["manufacturing_source_pattern_digest"],
                flat["digest"])
            self.assertEqual(
                binding["sewing_source_pattern_digest"], flat["digest"])
            self.assertEqual(
                manufacturing["ornament_artifacts"]["candidate_id"],
                row["candidate_id"])
            self.assertEqual(
                sewing["ornament_artifacts"]["candidate_id"],
                row["candidate_id"])
            self.assertEqual(flat["candidate_digest"],
                             row["candidate_digest"])
            self.assertEqual(
                flat["ornament_artifacts"]["candidate_digest"],
                row["candidate_digest"])
            self.assertEqual(
                manufacturing["ornament_artifacts"]["candidate_digest"],
                row["candidate_digest"])
            self.assertEqual(
                sewing["ornament_artifacts"]["candidate_digest"],
                row["candidate_digest"])

            for artifact in (flat, manufacturing, sewing):
                self.assertIs(artifact["manufacturing_ready"], False)
                self.assertIs(artifact["manufacturing_certified"], False)
                authority = artifact["ornament_artifacts"]["authority"]
                self.assertEqual(authority["highest_state"], "PROPOSED")
                self.assertIs(authority["approved"], False)
                self.assertIs(authority["observed"], False)

            digest_payload = copy.deepcopy(flat)
            digest = digest_payload.pop("digest")
            self.assertEqual(digest, garment_structure.semantic_digest(
                digest_payload))
            sewing_payload = copy.deepcopy(sewing)
            sewing_digest = sewing_payload.pop("digest")
            self.assertEqual(sewing_digest,
                             garment_structure.semantic_digest(sewing_payload))

    def test_unresolved_attachment_is_review_and_never_guessed(self):
        result = _run(_request(_candidate("a", missing_target=True),
                               _candidate("b", missing_target=True)))
        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])
        for row in result["candidates"]:
            flat = row["flat_pattern"]
            self.assertEqual(flat["ornament_artifacts"]["readiness"],
                             "REVIEW")
            self.assertTrue(
                flat["ornament_artifacts"]["reviews"]
                ["unresolved_attachments"])
            flap_id = f"flap-{row['candidate_id'].removeprefix('candidate-')}"
            self.assertIn(flap_id,
                          {piece["piece_id"] for piece in flat["pieces"]})
            attach = next(
                step for step in row["sewing_plan"]["steps"]
                if step.get("operation_id") == f"{flap_id}:attach")
            self.assertEqual(attach["state"], "REVIEW")
            self.assertFalse(attach["attachment_target_inferred"])
            self.assertNotIn("topology_binding", attach)
            self.assertIsNone(attach["detail"]["target"])
            review_codes = {
                review["verdict"] for review in row["sewing_plan"]["reviews"]
            }
            self.assertIn("REVIEW_ORNAMENT_ATTACHMENT_REQUIRED", review_codes)

    def test_candidate_digests_are_repeatable(self):
        first = _run(_request())
        second = _run(_request())
        first_by_id = {row["candidate_id"]: row for row in first["candidates"]}
        second_by_id = {row["candidate_id"]: row for row in second["candidates"]}
        self.assertEqual(set(first_by_id), set(second_by_id))
        for candidate_id in sorted(first_by_id):
            before, after = first_by_id[candidate_id], second_by_id[candidate_id]
            self.assertEqual(before["completion_structure_digest"],
                             after["completion_structure_digest"])
            self.assertEqual(before["topology_digest"], after["topology_digest"])
            self.assertEqual(before["flat_pattern"]["digest"],
                             after["flat_pattern"]["digest"])
            self.assertEqual(before["candidate_digest"],
                             after["candidate_digest"])
            self.assertEqual(before["sewing_plan"]["digest"],
                             after["sewing_plan"]["digest"])

    def test_invalid_target_refuses_only_that_candidate(self):
        request = _request(_candidate("good"),
                           _candidate("bad", invalid_target=True))
        result = _run(request)
        self.assertEqual(result["verdict"], "UNRESOLVED")
        self.assertEqual(result["successful_candidate_count"], 1)
        self.assertEqual(result["failed_candidate_count"], 1)
        rows = {row["candidate_id"]: row for row in result["candidates"]}
        self.assertEqual(rows["candidate-good"]["execution_status"],
                         "SUCCEEDED")
        self.assertTrue(rows["candidate-good"]["flat_pattern"]["pieces"])
        self.assertTrue(rows["candidate-good"]["manufacturing_preview"]
                        ["pieces"])
        self.assertEqual(rows["candidate-bad"]["execution_status"],
                         "REFUSED")
        self.assertEqual(rows["candidate-bad"]["verdict"],
                         "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_TARGET_MISSING")
        self.assertIsNone(rows["candidate-bad"]["flat_pattern"])
        self.assertIsNone(rows["candidate-bad"]["manufacturing_preview"])
        self.assertIsNone(rows["candidate-bad"]["sewing_plan"])


if __name__ == "__main__":
    unittest.main()
