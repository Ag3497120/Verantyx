#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest

from photoloset.front_image_generation_contract import (
    REQUEST_SCHEMA,
    REQUIRED_WEARER_MEASUREMENTS,
    orchestrate,
)


def _measurements():
    return {
        name: {
            "value_cm": 80.0 + index,
            "authority": "USER_PROVIDED",
            "source": "named target wearer",
        }
        for index, name in enumerate(REQUIRED_WEARER_MEASUREMENTS)
    }


def _candidate(candidate_id, rear, material):
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "structure": {"nodes": [candidate_id], "operations": []},
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": rear,
            "basis": "the rear is absent; this alternative is falsified by a rear view",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": material,
            "basis": "appearance suggests a bounded alternative; swatch testing may falsify it",
        },
        "manufacturing_certified": False,
    }


def _artifact(candidate_id, kind, **extra):
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "state": "PROPOSED" if kind != "manufacturing" else "REVIEW",
        "payload": {"fixture": kind, **extra},
        "manufacturing_certified": False,
        **extra,
    }


def _request():
    return {
        "schema": REQUEST_SCHEMA,
        "source": {"image_id": "sha256:front-fixture", "view": "front"},
        "vision": {
            "observations": [{
                "claim_id": "front-outline",
                "field": "front.silhouette",
                "value": "flared",
                "authority": "OBSERVED",
                "basis": "visible corrected front boundary",
            }],
            "proposals": [{
                "claim_id": "front-layer-interpretation",
                "field": "front.layer_count",
                "value": 2,
                "authority": "PROPOSED",
                "basis": "occlusion may be a layer or decoration",
            }],
        },
        "wearer_measurements": _measurements(),
        "candidates": [
            _candidate("candidate-a", "center_back_opening", "woven-light"),
            _candidate("candidate-b", "closed_back_side_opening", "knit-medium"),
        ],
        "artifacts": {},
        "approvals": {},
        "rounds": [],
        "max_rounds": 8,
    }


def _with_previews(request):
    request = copy.deepcopy(request)
    request["artifacts"] = {
        candidate_id: {
            "preview_3d": _artifact(candidate_id, "preview_3d", mesh_faces=32),
        }
        for candidate_id in ("candidate-a", "candidate-b")
    }
    return request


def _approve(request, gate, candidate_id, target_digest):
    request = copy.deepcopy(request)
    request.setdefault("approvals", {})[gate] = {
        "decision": "APPROVE",
        "actor_type": "HUMAN",
        "by": "pattern reviewer",
        "candidate_id": candidate_id,
        "target_digest": target_digest,
    }
    return request


class FrontImageGenerationContractTests(unittest.TestCase):
    maxDiff = None

    def test_contract_does_not_run_ml_and_requires_real_wearer_measurements(self):
        request = _request()
        request["wearer_measurements"] = {}
        result = orchestrate(request)

        self.assertEqual(result["decision"], "STOP")
        self.assertEqual(result["reason_code"],
                         "STOP_WEARER_MEASUREMENTS_REQUIRED")
        self.assertEqual(result["missing_measurements"],
                         list(REQUIRED_WEARER_MEASUREMENTS))
        self.assertFalse(result["claims"]["vision_or_ml_executed_here"])
        self.assertFalse(result["claims"]["wearer_measured_from_front_image"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])

    def test_rear_and_material_cannot_be_promoted_to_front_observations(self):
        for field in ("rear.closure", "material.fabric_family"):
            with self.subTest(field=field):
                request = _request()
                request["vision"]["observations"].append({
                    "claim_id": "illegal-fact",
                    "field": field,
                    "value": "zip",
                    "authority": "OBSERVED",
                    "basis": "model guess",
                })
                result = orchestrate(request)
                self.assertEqual(result["decision"], "STOP")
                self.assertEqual(result["reason_code"],
                                 "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION")
                self.assertFalse(result["manufacturing_certified"])

        request = _request()
        request["candidates"][0]["rear_hypothesis"]["state"] = "OBSERVED"
        result = orchestrate(request)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION")

        request = _request()
        request["candidates"][0]["extra"] = {
            "material_observed": True,
            "material_state": "OBSERVED",
        }
        result = orchestrate(request)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION")

    def test_ambiguous_candidates_get_candidate_specific_3d_gate_and_stable_digest(self):
        request = _request()
        first = orchestrate(request)
        reordered = copy.deepcopy(request)
        reordered["candidates"].reverse()
        reordered["vision"]["observations"].reverse()
        second = orchestrate(reordered)

        self.assertEqual(first["decision"], "CONTINUE")
        self.assertEqual(first["reason_code"],
                         "CONTINUE_CANDIDATE_SPECIFIC_3D_REQUIRED")
        self.assertEqual(first["missing_candidate_ids"],
                         ["candidate-a", "candidate-b"])
        self.assertEqual(first["contract_digest"], second["contract_digest"])
        self.assertEqual(first["input_digest"], second["input_digest"])
        self.assertEqual(first["react"]["controller"],
                         "VERA_DETERMINISTIC_REACT_HARNESS")
        self.assertEqual(first["react"]["llm_role"], "PROPOSE_ONLY")

    def test_artifact_identity_and_certification_claims_fail_closed(self):
        request = _with_previews(_request())
        request["artifacts"]["candidate-a"]["preview_3d"]["candidate_id"] = "candidate-b"
        result = orchestrate(request)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_ARTIFACT_CANDIDATE_ID_MISMATCH")

        request = _with_previews(_request())
        request["artifacts"]["candidate-a"]["preview_3d"][
            "manufacturing_certified"] = True
        result = orchestrate(request)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_MANUFACTURING_CERTIFICATION_CLAIM")
        self.assertFalse(result["manufacturing_certified"])

    def test_human_candidate_and_pattern_approvals_are_exact_digest_bound(self):
        request = _with_previews(_request())
        candidate_gate = orchestrate(request)
        self.assertEqual(candidate_gate["reason_code"],
                         "STOP_HUMAN_CANDIDATE_APPROVAL_REQUIRED")
        target = candidate_gate["approval_targets"]["candidate-a"]

        stale = _approve(request, "candidate", "candidate-a", "stale")
        self.assertEqual(orchestrate(stale)["reason_code"],
                         "UNKNOWN_STALE_HUMAN_APPROVAL")

        request = _approve(request, "candidate", "candidate-a", target)
        pattern_step = orchestrate(request)
        self.assertEqual(pattern_step["reason_code"],
                         "CONTINUE_APPROVED_CANDIDATE_PATTERN_REQUIRED")

        request["artifacts"]["candidate-a"]["pattern"] = _artifact(
            "candidate-a", "pattern", piece_count=8)
        pattern_gate = orchestrate(request)
        self.assertEqual(pattern_gate["reason_code"],
                         "STOP_HUMAN_PATTERN_APPROVAL_REQUIRED")
        self.assertTrue(pattern_gate["requires_human_approval"])

        machine = copy.deepcopy(request)
        machine["approvals"]["pattern"] = {
            "decision": "APPROVE", "actor_type": "LLM", "by": "model",
            "candidate_id": "candidate-a",
            "target_digest": pattern_gate["approval_target_digest"],
        }
        self.assertEqual(orchestrate(machine)["reason_code"],
                         "UNKNOWN_NAMED_HUMAN_APPROVAL_REQUIRED")

    def test_bounded_repair_rounds_and_final_state_never_certify(self):
        request = _with_previews(_request())
        candidate_gate = orchestrate(request)
        request = _approve(
            request, "candidate", "candidate-a",
            candidate_gate["approval_targets"]["candidate-a"])
        request["artifacts"]["candidate-a"]["pattern"] = _artifact(
            "candidate-a", "pattern", piece_count=8)
        pattern_gate = orchestrate(request)
        request = _approve(
            request, "pattern", "candidate-a",
            pattern_gate["approval_target_digest"])

        request["artifacts"]["candidate-a"]["manufacturing"] = _artifact(
            "candidate-a", "manufacturing",
            blocking_issues=[{"code": "SEAM_STRESS", "panel": "back"}])
        repair = orchestrate(request)
        self.assertEqual(repair["decision"], "CONTINUE")
        self.assertEqual(repair["reason_code"], "CONTINUE_VERA_REPAIR_ROUND")
        self.assertEqual(repair["react"]["next_action"],
                         "REPAIR_AND_REVALIDATE")

        exhausted = copy.deepcopy(request)
        exhausted["max_rounds"] = 1
        exhausted["rounds"] = [{
            "round": 1,
            "observation": "seam stress",
            "action": "repair seam allowance",
            "result": "stress remains",
        }]
        stopped = orchestrate(exhausted)
        self.assertEqual(stopped["reason_code"],
                         "STOP_REACT_ROUND_BUDGET_EXHAUSTED")

        request["artifacts"]["candidate-a"]["manufacturing"] = _artifact(
            "candidate-a", "manufacturing", blocking_issues=[])
        manufacturing_gate = orchestrate(request)
        self.assertEqual(manufacturing_gate["reason_code"],
                         "STOP_HUMAN_MANUFACTURING_REVIEW_REQUIRED")
        request = _approve(
            request, "manufacturing_review", "candidate-a",
            manufacturing_gate["approval_target_digest"])
        final = orchestrate(request)
        self.assertEqual(final["decision"], "STOP")
        self.assertEqual(final["reason_code"],
                         "STOP_READY_FOR_PHYSICAL_PROTOTYPE_REVIEW")
        self.assertEqual(final["state"],
                         "READY_FOR_PHYSICAL_PROTOTYPE_REVIEW")
        self.assertFalse(final["manufacturing_ready"])
        self.assertFalse(final["manufacturing_certified"])
        self.assertFalse(final["claims"]["manufacturing_certification_created"])
        json.dumps(final, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
