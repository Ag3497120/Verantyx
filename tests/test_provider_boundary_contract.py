#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import unittest

from photoloset import corpus_manifest
from photoloset.garment_analysis_ensemble import (
    analyze_garment_image,
    analyze_garment_image_async,
)
from photoloset.marqo_fashion_siglip_adapter import run_retrieval
from photoloset.rear_candidate_ensemble import (
    UNKNOWN_UNOBSERVED,
    generate_rear_candidates,
    proposal_use_gate,
)
from photoloset.sewing_search import (
    SEAM_FINISHING_CORPUS_REQUIRED,
    _consented_seam_finishing,
    _geometric_sewing_order,
)


def _request(*sources):
    return {
        "schema": "garment.image-analysis-ensemble.request.v1",
        "analysis_id": "provider-contract-fixture",
        "image": {"reference": "fixture://front.png", "front_only": True},
        "multimodal_sources": list(sources),
    }


def _vision(label: str, *, material: str = ""):
    instance = {
        "instance_id": "lower",
        "layer": 0,
        "garment_name": label,
        "parts": [{"part_id": "lower-body", "name": "lower body"}],
    }
    if material:
        instance["material"] = {"family": material}
    return {"garment_instances": [instance]}


def _consent(scope: str, subject_digest: str):
    return {
        "schema": corpus_manifest.PROVIDER_CONSENT_SCHEMA,
        "action": corpus_manifest.CONSENTED_LLM_PROPOSAL,
        "by": "Fixture Reviewer",
        "scopes": [scope],
        "subject_digest": subject_digest,
    }


def _visible_graph():
    return {
        "graph_id": "provider-contract-visible-front",
        "parts": [{
            "part_id": "body",
            "kind": "BODY_SHELL",
            "garment_unit": "unknown-garment",
            "layer": 0,
        }],
    }


class ProviderBoundaryContractTests(unittest.TestCase):
    maxDiff = None

    def test_absent_providers_offer_connection_or_scoped_llm_consent(self):
        analysis = analyze_garment_image(_request())
        self.assertEqual(
            "UNKNOWN_GARMENT_ANALYSIS_PROVIDERS_UNAVAILABLE",
            analysis["verdict"],
        )
        self.assertEqual("AWAITING_PROVIDER_OR_CONSENT", analysis["state"])
        actions = {row["action"] for row in analysis["resolution_options"]}
        self.assertEqual({
            corpus_manifest.CONNECT_PROVIDER,
            corpus_manifest.CONSENTED_LLM_PROPOSAL,
            corpus_manifest.TYPED_STOP,
        }, actions)
        llm_option = next(
            row for row in analysis["resolution_options"]
            if row["action"] == corpus_manifest.CONSENTED_LLM_PROPOSAL
        )
        self.assertEqual({
            "OBSERVED", "MEASURED", "CALIBRATED", "VALIDATED",
            "MANUFACTURING_CERTIFIED",
        }, set(llm_option["cannot_promote_to"]))
        self.assertTrue(all(
            row["provider_boundary"]["schema"]
            == corpus_manifest.PROVIDER_BOUNDARY_SCHEMA
            for row in analysis["capabilities"]["sources"]
        ))

        retrieval = run_retrieval({"config": {"mode": "precomputed"}})
        self.assertEqual(
            "UNKNOWN_NO_FASHION_RETRIEVAL_INDEX", retrieval["verdict"])
        self.assertEqual(
            "AWAITING_PROVIDER_OR_CONSENT", retrieval["state"])
        self.assertEqual({
            corpus_manifest.CONNECT_PROVIDER,
            corpus_manifest.CONSENTED_LLM_PROPOSAL,
            corpus_manifest.TYPED_STOP,
        }, {row["action"] for row in retrieval["resolution_options"]})
        self.assertEqual(
            corpus_manifest.PROVIDER_RESULT_SCHEMA,
            retrieval["provider_result"]["schema"],
        )

    def test_one_multimodal_provider_failure_does_not_erase_the_other(self):
        async def api_provider(_request_value):
            await asyncio.sleep(0)
            return _vision("wide-leg trousers")

        def local_provider(_request_value):
            raise RuntimeError("local runtime unavailable")

        result = asyncio.run(analyze_garment_image_async(
            _request(
                {"source_id": "local-vlm", "provider_kind": "LOCAL"},
                {"source_id": "api-vlm", "provider_kind": "API"},
            ),
            multimodal_providers={
                "local-vlm": local_provider,
                "api-vlm": api_provider,
            },
        ))

        sources = {
            row["source_id"]: row
            for row in result["capabilities"]["sources"]
        }
        self.assertEqual("ANSWER_PARTIAL", result["verdict"])
        self.assertEqual("FAILED", sources["local-vlm"]
                         ["provider_boundary"]["health"])
        self.assertEqual("READY", sources["api-vlm"]
                         ["provider_boundary"]["health"])
        self.assertEqual(
            "UNKNOWN_VISION_PROVIDER_FAILED",
            sources["local-vlm"]["provider_result"]["failure"]["verdict"],
        )
        self.assertTrue(any(
            row["source"].endswith("api-vlm")
            for row in result["claims"]
        ))
        self.assertFalse(any(
            row["source"].endswith("local-vlm")
            for row in result["claims"]
        ))

    def test_conflicting_provider_proposals_remain_contested(self):
        result = analyze_garment_image(_request(
            {
                "source_id": "local-vlm", "provider_kind": "LOCAL",
                "result": _vision("long skirt"),
            },
            {
                "source_id": "api-vlm", "provider_kind": "API",
                "result": _vision("wide-leg trousers"),
            },
        ))

        contests = [
            row for row in result["contested"]
            if row["category"] == "GARMENT_NAME"
        ]
        self.assertEqual(1, len(contests))
        self.assertTrue(contests[0]["no_averaging"])
        self.assertEqual(
            {"long skirt", "wide-leg trousers"},
            {row["value"] for row in contests[0]["alternatives"]},
        )
        self.assertEqual(2, len({
            row["source"] for row in contests[0]["alternatives"]
        }))
        self.assertEqual([], result["fact_promotions"])
        self.assertTrue(result["claims"])
        self.assertTrue(all(
            row["observation_state"] == "UNKNOWN_UNOBSERVED"
            and row["observed"] is False
            and row["source_origin"] == "FRONT_IMAGE_DERIVED_PROPOSAL"
            for row in result["claims"]
        ))

    def test_consent_is_exactly_scope_and_subject_bound(self):
        ensemble = generate_rear_candidates(
            _visible_graph(),
            multimodal_proposals={"proposals": [{
                "proposal_id": "rear-model-1",
                "rear_structure": {"configuration": "center-back opening"},
                "material": {"family": "woven-like"},
            }]},
        )
        candidate = ensemble["candidates"][0]
        digest = candidate["candidate_digest"]

        wrong_scope = proposal_use_gate(
            candidate, _consent("MATERIAL_HYPOTHESIS", digest),
            scope="REAR_HYPOTHESIS",
        )
        self.assertFalse(wrong_scope["allowed"])
        self.assertEqual("UNKNOWN_PROVIDER_CONSENT_SCOPE",
                         wrong_scope["verdict"])

        stale = proposal_use_gate(
            candidate, _consent("REAR_HYPOTHESIS", "stale-digest"),
            scope="REAR_HYPOTHESIS",
        )
        self.assertFalse(stale["allowed"])
        self.assertEqual("UNKNOWN_PROVIDER_CONSENT_STALE", stale["verdict"])

        accepted = proposal_use_gate(
            candidate, _consent("REAR_HYPOTHESIS", digest),
            scope="REAR_HYPOTHESIS",
        )
        self.assertTrue(accepted["allowed"])
        self.assertEqual(UNKNOWN_UNOBSERVED,
                         accepted["observation_state"])
        self.assertFalse(accepted["automatic_observed_promotion"])
        self.assertFalse(accepted["sewing_search_allowed"])

    def test_commercial_rights_refusal_is_fail_closed(self):
        conflict = corpus_manifest.commercial_rights_status({
            "rights_review": {"commercial_use": "allowed"},
            "license": {"commercial_use": "denied"},
        })
        self.assertEqual("DENIED", conflict["state"])
        self.assertFalse(conflict["allowed"])

        result = run_retrieval({
            "config": {
                "mode": "precomputed",
                "require_commercial_rights": True,
            },
            "precomputed_result": {"matches": [{
                "item_id": "unknown-rights-item",
                "score": 0.9,
                "license": {"commercial_use": "unknown"},
            }]},
        })
        self.assertEqual(
            "UNKNOWN_FASHION_RETRIEVAL_COMMERCIAL_RIGHTS",
            result["verdict"],
        )
        self.assertEqual("RIGHTS_REFUSED",
                         result["provider_boundary"]["health"])
        self.assertEqual([], result["matches"])
        self.assertEqual(1, result["commercial_rights_gate"]
                         ["refused_match_count"])
        self.assertIn(
            corpus_manifest.CONNECT_PROVIDER,
            {row["action"] for row in result["resolution_options"]},
        )

    def test_rear_retrieval_requires_explicit_rights_in_commercial_mode(self):
        request = {
            "schema": "garment.rear-candidate-ensemble.request.v1",
            "visible_part_graph": _visible_graph(),
            "require_commercial_rights": True,
        }
        unknown_rights = generate_rear_candidates(
            request,
            fashion_siglip_hits={"matches": [{
                "item_id": "rear-reference-without-rights",
                "rear_structure": {"configuration": "closed back"},
            }]},
        )
        status = unknown_rights["provider_status"]["fashion_siglip"]
        self.assertFalse(status["available"])
        self.assertEqual("RIGHTS_REFUSED",
                         status["provider_boundary"]["health"])
        self.assertEqual(1, status["rights_unknown_rows"])
        self.assertFalse(any(
            row["provenance"]["source_kind"]
            == "FASHION_SIGLIP_RETRIEVAL"
            for row in unknown_rights["source_claims"]
        ))

        allowed = generate_rear_candidates(
            request,
            fashion_siglip_hits={"matches": [{
                "item_id": "rights-cleared-rear-reference",
                "rear_structure": {"configuration": "closed back"},
                "rights_review": {"commercial_use": "allowed"},
            }]},
        )
        allowed_status = allowed["provider_status"]["fashion_siglip"]
        self.assertTrue(allowed_status["available"])
        self.assertEqual("ALLOWED", allowed_status["provider_boundary"]
                         ["commercial_rights_gate"]["state"])
        self.assertIn(
            "REAR_REFERENCE_RETRIEVAL",
            allowed["provider_capability_report"]["ready"],
        )
        self.assertTrue(all(
            row["observation_state"] == UNKNOWN_UNOBSERVED
            and row["observed"] is False
            for row in allowed["source_claims"]
        ))

    def test_rear_and_material_never_become_observed(self):
        ensemble = generate_rear_candidates(
            _visible_graph(),
            multimodal_proposals={"proposals": [{
                "proposal_id": "authority-stripping-fixture",
                "rear_structure": {
                    "state": "OBSERVED",
                    "configuration": "closed back",
                },
                "material": {
                    "state": "OBSERVED",
                    "family": "acrylic-like",
                },
            }]},
        )

        self.assertEqual(UNKNOWN_UNOBSERVED,
                         ensemble["authority"]["observation_state"])
        self.assertFalse(ensemble["authority"]
                         ["automatic_observed_promotion"])
        self.assertTrue(ensemble["source_claims"])
        self.assertTrue(all(
            row["state"] == "PROPOSED"
            and row["observation_state"] == UNKNOWN_UNOBSERVED
            and row["observed"] is False
            for row in ensemble["source_claims"]
        ))
        self.assertTrue(all(
            row["downstream_use_contract"]
            ["scoped_human_consent_or_approval_required"]
            for row in ensemble["candidates"]
        ))
        self.assertFalse(ensemble["manufacturing_ready"])
        for capability in (
            "REAR_REFERENCE_RETRIEVAL",
            "MATERIAL_PROPERTY_MEASUREMENT",
            "MATERIAL_PROPERTY_CALIBRATION",
            "BODY_MEASUREMENT",
            "WIND_TUNNEL_VALIDATION",
            "SEAM_STRENGTH_TEST",
        ):
            row = ensemble["provider_capability_report"][
                "capabilities"][capability]
            self.assertEqual(
                corpus_manifest.PROVIDER_BOUNDARY_SCHEMA,
                row["provider_boundary"]["schema"],
            )
            self.assertEqual([], row["provider_result"]["proposals"])

    def test_expanded_provider_catalog_is_fail_closed(self):
        required = {
            "REAR_REFERENCE_RETRIEVAL",
            "MATERIAL_PROPERTY_MEASUREMENT",
            "MATERIAL_PROPERTY_CALIBRATION",
            "BODY_MEASUREMENT",
            "FASHION_SIMILARITY_RETRIEVAL",
            "SEWING_CONSTRUCTION_CORPUS",
            "SEAM_FINISHING_HYPOTHESIS",
            "WIND_TUNNEL_VALIDATION",
            "SEAM_STRENGTH_TEST",
        }
        report = corpus_manifest.provider_capability_report()
        self.assertTrue(required.issubset(report["capabilities"]))
        self.assertFalse(report["fabricated_results"])
        self.assertFalse(report["front_image_can_be_observed"])
        self.assertTrue(required.issubset(set(report["unresolved"])))
        for capability in required:
            row = report["capabilities"][capability]
            self.assertFalse(row["provider_boundary"]["available"])
            self.assertEqual([], row["provider_result"]["proposals"])
            self.assertEqual(
                corpus_manifest.TYPED_STOP,
                row["provider_result"]["result_action"],
            )
            actions = {
                option["action"]
                for option in row["provider_boundary"]["resolution_options"]
            }
            self.assertIn(corpus_manifest.CONNECT_PROVIDER, actions)
            self.assertIn(corpus_manifest.TYPED_STOP, actions)

        for capability in (
            "WIND_TUNNEL_VALIDATION", "SEAM_STRENGTH_TEST"):
            actions = {
                option["action"]
                for option in report["capabilities"][capability]
                ["provider_boundary"]["resolution_options"]
            }
            self.assertNotIn(
                corpus_manifest.CONSENTED_LLM_PROPOSAL, actions)

    def test_front_image_cannot_satisfy_measurement_authority(self):
        boundary = corpus_manifest.provider_capability(
            "fixture-body-model", "BODY_MEASUREMENT",
            health="READY", available=True,
        )
        refused = corpus_manifest.provider_result(
            boundary,
            proposals=[{"height_cm": 170}],
            provenance=[{"image": "fixture://front.png"}],
            result_authority="MEASURED",
            source_origin="FRONT_IMAGE_MULTIMODAL_ANALYSIS",
            direct_observation=True,
        )
        self.assertEqual(corpus_manifest.TYPED_STOP,
                         refused["result_action"])
        self.assertEqual(corpus_manifest.PROPOSED_UNOBSERVED,
                         refused["accepted_authority"])
        self.assertEqual("UNKNOWN_UNOBSERVED",
                         refused["observation_state"])
        self.assertFalse(refused["observed"])
        self.assertFalse(refused["requested_authority_satisfied"])
        self.assertTrue(refused["authority_refusal"]
                        ["front_image_cannot_be_observed"])

        measured = corpus_manifest.provider_result(
            boundary,
            proposals=[{"height_cm": 170}],
            provenance=[{"measurement": "named tape measurement"}],
            result_authority="MEASURED",
            source_origin="TAPE_MEASUREMENT",
            direct_observation=True,
        )
        self.assertEqual(corpus_manifest.PROVIDER_RESULT,
                         measured["result_action"])
        self.assertEqual("MEASURED", measured["accepted_authority"])
        self.assertTrue(measured["observed"])

    def test_geometry_orders_joins_but_does_not_invent_seam_finishing(self):
        order = _geometric_sewing_order(
            {
                "structure": {
                    "nodes": [
                        {"node_id": "body", "kind": "BODY_SHELL", "layer": 0},
                        {"node_id": "overlay", "kind": "OVERLAY", "layer": 1},
                    ],
                    "operations": [{
                        "kind": "JOIN", "source": "body", "target": "overlay",
                    }],
                },
            },
            "shape-approval",
            {"verdict": "ANSWER", "candidate_3d_digest": "candidate-3d"},
        )
        self.assertEqual("ANSWER", order["verdict"])
        self.assertFalse(order["corpus_used"])
        self.assertTrue(order["steps"])
        self.assertEqual(SEAM_FINISHING_CORPUS_REQUIRED,
                         order["seam_finishing"]["verdict"])

        proposal = {
            "subject_digest": "candidate-3d",
            "provider_id": "fixture-llm",
            "proposal": {"seam_finish": "bound edge"},
        }
        wrong = _consented_seam_finishing({
            "seam_finishing_llm_proposal": proposal,
            "seam_finishing_llm_consent": _consent(
                "MATERIAL_HYPOTHESIS", "candidate-3d"),
        }, "candidate-3d")
        self.assertFalse(wrong["accepted"])
        self.assertEqual("UNKNOWN_PROVIDER_CONSENT_SCOPE",
                         wrong["consent_check"]["verdict"])
        self.assertEqual(corpus_manifest.TYPED_STOP,
                         wrong["provider_result"]["result_action"])

        accepted = _consented_seam_finishing({
            "seam_finishing_llm_proposal": proposal,
            "seam_finishing_llm_consent": _consent(
                "SEAM_FINISH_HYPOTHESIS", "candidate-3d"),
        }, "candidate-3d")
        self.assertTrue(accepted["accepted"])
        self.assertEqual("PROPOSED_CONSENTED_LLM",
                         accepted["record"]["state"])
        self.assertEqual(UNKNOWN_UNOBSERVED,
                         accepted["record"]["observation_state"])
        self.assertFalse(accepted["record"]["manufacturing_validated"])
        self.assertFalse(accepted["record"]["strength_evidence"])

        strict_without_rights = _consented_seam_finishing({
            "seam_finishing_llm_proposal": proposal,
            "seam_finishing_llm_consent": _consent(
                "SEAM_FINISH_HYPOTHESIS", "candidate-3d"),
        }, "candidate-3d", require_commercial=True)
        self.assertFalse(strict_without_rights["accepted"])
        self.assertEqual(
            "UNKNOWN_SEAM_FINISHING_COMMERCIAL_RIGHTS",
            strict_without_rights["consent_check"]["verdict"],
        )

        rights_cleared_proposal = {
            **proposal,
            "rights_review": {"commercial_use": "allowed"},
        }
        strict_accepted = _consented_seam_finishing({
            "seam_finishing_llm_proposal": rights_cleared_proposal,
            "seam_finishing_llm_consent": _consent(
                "SEAM_FINISH_HYPOTHESIS", "candidate-3d"),
        }, "candidate-3d", require_commercial=True)
        self.assertTrue(strict_accepted["accepted"])
        self.assertEqual(
            "ALLOWED", strict_accepted["provider_boundary"]
            ["commercial_rights_gate"]["state"],
        )


if __name__ == "__main__":
    unittest.main()
