#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest

from photoloset.manufacturing_finish_contract import (
    ALLOW_ONE_TIME_LLM_PROPOSAL,
    CANDIDATES_READY,
    CONNECT_PROVIDER,
    CONTESTED,
    ENTER_REQUESTED_VALUE,
    MODEL_PROPOSED,
    PROVIDER_SUPPORTED,
    REQUESTED,
    RESOLUTION_REQUIRED,
    TYPED_STOP,
    UNKNOWN_UNOBSERVED,
    USER_APPROVED,
    approve_manufacturing_finish_candidate,
    build_manufacturing_finish_decision,
)


SUBJECT = "sha256:approved-garment-fixture"
TOPOLOGY = {
    "seams": [
        {"seam_id": "side-seam", "joins": ["front", "back"]},
    ]
}
ORDER = ["join side-seam"]


def requested(field, value, target="garment", by="Pattern Maker"):
    return {
        "field": field,
        "target": target,
        "value": value,
        "requested_by": by,
        "provenance": {"actor": by, "request_id": f"request-{field}-{target}"},
    }


def provider_claim(field, value, target="garment", *, record="record-1"):
    return {
        "field": field,
        "target": target,
        "value": value,
        "authority": "OBSERVED",
        "rights_review": {"commercial_use": "allowed"},
        "provenance": {
            "source_id": "fixture-sewing-corpus",
            "record_id": record,
            "evidence_digest": f"sha256:{record}",
        },
    }


def complete_requested(seam_finish="FRENCH"):
    return [
        requested("seam_finish", seam_finish, "side-seam"),
        requested("interfacing", "NONE"),
        requested("lining", "NONE"),
    ]


class ManufacturingFinishContractTests(unittest.TestCase):
    maxDiff = None

    def test_geometry_never_hallucinates_finish_interfacing_or_lining(self):
        result = build_manufacturing_finish_decision(
            subject_digest=SUBJECT,
            seam_topology=TOPOLOGY,
            sewing_order=ORDER,
        )

        self.assertEqual(RESOLUTION_REQUIRED, result["verdict"])
        self.assertEqual([], result["candidates"])
        self.assertEqual([], result["accepted_claims"])
        self.assertFalse(result["geometry_context"]["can_select_seam_finish"])
        self.assertFalse(result["geometry_context"]["can_select_interfacing"])
        self.assertFalse(result["geometry_context"]["can_select_lining"])
        self.assertEqual({
            ("seam_finish", "side-seam"),
            ("interfacing", "garment"),
            ("lining", "garment"),
        }, {
            (row["field"], row["target"])
            for row in result["missing_decisions"]
        })
        rendered = repr(result).upper()
        self.assertNotIn("FRENCH", rendered)
        self.assertNotIn("FELLED", rendered)
        self.assertNotIn("OVERLOCK", rendered)

    def test_model_and_provider_cannot_promote_their_own_authority(self):
        model_rows = [
            {
                "field": "seam_finish", "target": "side-seam",
                "value": "FELLED", "state": "OBSERVED",
                "model_id": "fixture-model",
            },
            {
                "field": "interfacing", "value": "FUSIBLE_WOVEN",
                "authority": "MEASURED", "model_id": "fixture-model",
            },
            {
                "field": "lining", "value": "FULL",
                "authority": "MANUFACTURING_CERTIFIED",
                "model_id": "fixture-model",
            },
        ]
        provider_rows = [provider_claim(
            "seam_finish", "OVERLOCK", "side-seam", record="provider-seam")]
        result = build_manufacturing_finish_decision(
            subject_digest=SUBJECT, seam_topology=TOPOLOGY,
            sewing_order=ORDER, model_proposed=model_rows,
            provider_supported=provider_rows,
            provider={"provider_id": "fixture-sewing-corpus", "available": True},
        )

        self.assertEqual(CANDIDATES_READY, result["verdict"])
        model_claims = result["evidence_lanes"][MODEL_PROPOSED]
        self.assertTrue(model_claims)
        self.assertTrue(all(row["state"] == MODEL_PROPOSED for row in model_claims))
        self.assertTrue(all(row["observed"] is False for row in model_claims))
        self.assertTrue(all(
            row["observation_state"] == UNKNOWN_UNOBSERVED
            for row in model_claims
        ))
        self.assertTrue(all(
            row["authority_promotion_refused"] for row in model_claims
        ))
        provider_row = result["evidence_lanes"][PROVIDER_SUPPORTED][0]
        self.assertEqual(PROVIDER_SUPPORTED, provider_row["state"])
        self.assertFalse(provider_row["observed"])
        self.assertTrue(provider_row["authority_promotion_refused"])
        self.assertEqual([], result["fact_promotions"])

    def test_candidates_and_digest_are_deterministic_across_input_order(self):
        rows = complete_requested()
        providers = [
            provider_claim("seam_finish", "OVERLOCK", "side-seam", record="s1"),
            provider_claim("lining", "HALF", record="l1"),
            provider_claim("interfacing", "SEW_IN", record="i1"),
        ]
        first = build_manufacturing_finish_decision(
            subject_digest=SUBJECT, seam_topology=TOPOLOGY,
            sewing_order=ORDER, requested=rows,
            provider_supported=providers,
            provider={"provider_id": "fixture-sewing-corpus", "available": True},
            max_candidates=5,
        )
        second = build_manufacturing_finish_decision(
            subject_digest=SUBJECT,
            seam_topology={"seams": list(reversed(TOPOLOGY["seams"]))},
            sewing_order=ORDER, requested=list(reversed(rows)),
            provider_supported=list(reversed(providers)),
            provider={"available": True, "provider_id": "fixture-sewing-corpus"},
            max_candidates=5,
        )

        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertEqual(
            [row["candidate_digest"] for row in first["candidates"]],
            [row["candidate_digest"] for row in second["candidates"]],
        )
        self.assertLessEqual(len(first["candidates"]), 5)
        self.assertEqual(list(range(1, len(first["candidates"]) + 1)),
                         [row["rank"] for row in first["candidates"]])

    def test_conflicting_values_remain_contested_and_are_not_averaged(self):
        result = build_manufacturing_finish_decision(
            subject_digest=SUBJECT, seam_topology=TOPOLOGY,
            sewing_order=ORDER,
            requested=complete_requested("FRENCH"),
            provider_supported=[provider_claim(
                "seam_finish", "OVERLOCK", "side-seam", record="s1")],
            model_proposed=[{
                "field": "seam_finish", "target": "side-seam",
                "value": "FELLED", "model_id": "fixture-model",
            }],
            provider={"provider_id": "fixture-sewing-corpus", "available": True},
        )

        contest = next(row for row in result["contested"]
                       if row["field"] == "seam_finish")
        self.assertEqual(CONTESTED, contest["state"])
        self.assertTrue(contest["no_averaging"])
        self.assertFalse(contest["auto_resolution"])
        self.assertEqual(
            {"FRENCH", "OVERLOCK", "FELLED"},
            {row["value"] for row in contest["alternatives"]},
        )
        self.assertIsNone(result["selected_candidate"])
        self.assertFalse(result["automatic_selection_allowed"])
        best = result["candidates"][0]["selections"]["seam_finish:side-seam"]
        self.assertEqual("FRENCH", best["value"])
        self.assertIn(REQUESTED, best["supporting_states"])

    def test_absent_provider_returns_actionable_typed_resolution(self):
        result = build_manufacturing_finish_decision(
            subject_digest=SUBJECT, seam_topology=TOPOLOGY,
            sewing_order=ORDER,
        )

        request = result["resolution_request"]
        self.assertEqual("UNAVAILABLE", result["provider_state"])
        self.assertTrue(request["actionable"])
        self.assertEqual("AWAITING_HUMAN_OR_PROVIDER", request["state"])
        actions = {row["action"] for row in request["resolution_options"]}
        self.assertTrue({
            CONNECT_PROVIDER,
            ENTER_REQUESTED_VALUE,
            ALLOW_ONE_TIME_LLM_PROPOSAL,
            TYPED_STOP,
        }.issubset(actions))
        llm = next(row for row in request["resolution_options"]
                   if row["action"] == ALLOW_ONE_TIME_LLM_PROPOSAL)
        self.assertEqual(MODEL_PROPOSED, llm["result_authority"])
        self.assertIn("OBSERVED", llm["cannot_promote_to"])

    def test_provider_evidence_fails_closed_without_rights_or_provenance(self):
        no_rights = provider_claim(
            "seam_finish", "OVERLOCK", "side-seam", record="no-rights")
        no_rights.pop("rights_review")
        no_provenance = provider_claim("lining", "FULL", record="no-prov")
        no_provenance.pop("provenance")
        result = build_manufacturing_finish_decision(
            subject_digest=SUBJECT, seam_topology=TOPOLOGY,
            sewing_order=ORDER,
            provider_supported=[no_rights, no_provenance],
            provider={"provider_id": "fixture-sewing-corpus", "available": True},
        )

        self.assertEqual(RESOLUTION_REQUIRED, result["verdict"])
        self.assertEqual([], result["evidence_lanes"][PROVIDER_SUPPORTED])
        self.assertEqual("RIGHTS_OR_PROVENANCE_REFUSED", result["provider_state"])
        self.assertEqual({
            "PROVIDER_RIGHTS_REQUIRED", "PROVIDER_PROVENANCE_REQUIRED",
        }, {row["code"] for row in result["rejected_claims"]})
        self.assertEqual([], result["candidates"])

    def test_human_approval_is_user_approved_not_observed(self):
        decision = build_manufacturing_finish_decision(
            subject_digest=SUBJECT, seam_topology=TOPOLOGY,
            sewing_order=ORDER, requested=complete_requested(),
        )
        candidate = decision["candidates"][0]
        original = copy.deepcopy(decision)
        approval = approve_manufacturing_finish_candidate(
            decision,
            candidate_digest=candidate["candidate_digest"],
            approved_by="Named Pattern Maker",
            provenance={"review_session": "review-1"},
        )

        self.assertEqual(USER_APPROVED, approval["verdict"])
        self.assertEqual(USER_APPROVED, approval["state"])
        self.assertFalse(approval["observed"])
        self.assertEqual(UNKNOWN_UNOBSERVED, approval["observation_state"])
        self.assertFalse(approval["manufacturing_certified"])
        self.assertFalse(approval["strength_validated"])
        self.assertEqual([], approval["fact_promotions"])
        self.assertEqual(original, decision)

    def test_explicit_unsupported_requirement_returns_typed_stop(self):
        unsupported = complete_requested()
        unsupported[0] = {
            **unsupported[0],
            "value": "LASER-WELDED-UNKNOWN-FINISH",
            "supported": False,
            "why": "no compiler or validated process supports this finish",
        }
        result = build_manufacturing_finish_decision(
            subject_digest=SUBJECT, seam_topology=TOPOLOGY,
            sewing_order=ORDER, requested=unsupported,
        )

        self.assertEqual(TYPED_STOP, result["verdict"])
        self.assertIsNotNone(result["typed_stop"])
        self.assertTrue(result["typed_stop"]["terminal_for_this_attempt"])
        self.assertFalse(result["typed_stop"]["state_mutation_allowed"])
        self.assertIn("REPLACE_UNSUPPORTED_REQUIREMENT",
                      result["typed_stop"]["resumable_by"])
        self.assertEqual([], result["candidates"])


if __name__ == "__main__":
    unittest.main()
