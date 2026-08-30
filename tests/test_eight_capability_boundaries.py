#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adversarial integration checks for the advertised garment boundaries.

This file intentionally states the *safe* contract.  A failing assertion is a
boundary that the shared-tree implementation currently permits callers to
cross.  The tests use only public orchestration entry points except for
``_seal`` in the consent-replay test: resealing simulates loading an otherwise
well-formed destination document containing a foreign consent artifact, so the
test isolates consent binding from the already-working outer document digest.
"""
from __future__ import annotations

import copy
import inspect
import json
import unittest

from photoloset import corpus_manifest
from photoloset import cross as tagged_record_store
from photoloset import cross_workflow_harness as harness
from photoloset import garment_factory
from photoloset import generation_job
from photoloset import mcp
from photoloset.marqo_fashion_siglip_adapter import run_retrieval


EXPECTED_GATES = {
    "REAR_FROM_SINGLE_FRONT",
    "MEASURED_MATERIAL",
    "BODY_DIMENSIONS_FROM_IMAGE",
    "ARBITRARY_GARMENT_FIDELITY",
    "COMPLETE_PATTERN_GUARANTEE",
    "SEAM_FINISH_CONSTRUCTION",
    "REAL_CLOTH_ERROR_GUARANTEE",
    "WIND_TUNNEL_CALIBRATION",
    "CONNECTED_FASHION_SEARCH",
}

EXPECTED_LIMITATIONS = {
    "rear-not-observed-from-front",
    "material-properties-not-measured-from-image",
    "wearer-body-not-measured-from-image",
    "arbitrary-garment-fidelity-not-guaranteed",
    "finished-pattern-not-guaranteed",
    "seam-finishes-undetermined",
    "real-cloth-error-not-calibrated",
    "wind-tunnel-validation-not-connected",
    "fashion-siglip-index-not-connected",
    "sewing-corpus-not-connected",
}

ACTIONABLE_PATHS = {
    harness.MEASURED_INPUT,
    harness.HUMAN_EDIT,
    harness.CONNECT_PROVIDER,
    harness.CONSENTED_LLM_PROPOSAL,
    harness.BOUNDED_ALTERNATIVES,
}


def _gate(gate_id: str, evidence: dict) -> dict:
    return harness.evaluate_capability_gates(
        harness.new_workflow("adversarial-" + gate_id.lower()),
        [gate_id],
        evidence={gate_id: [evidence]},
        provenance={"test": "eight-capability-boundaries"},
    )


def _assert_gate_refused(testcase: unittest.TestCase, result: dict) -> None:
    gate = result["gates"][0]
    testcase.assertNotEqual(
        "ANSWER",
        gate["verdict"],
        msg=(f"{gate['gate']} was closed by evidence that does not establish "
             "the complete/scoped capability"),
    )
    testcase.assertIsNotNone(result["resolution_request"])


class EstablishedIntegrationBoundaryTests(unittest.TestCase):
    """Contracts that already fail closed in the current shared tree."""

    maxDiff = None

    def test_all_unresolved_gates_have_actionable_or_terminal_continuation(self):
        result = harness.evaluate_capability_gates(
            harness.new_workflow("all-unresolved-boundaries"),
            list(reversed(sorted(EXPECTED_GATES))),
        )

        self.assertEqual(EXPECTED_GATES, set(harness.CAPABILITY_GATES))
        self.assertEqual("UNKNOWN_CAPABILITY_GATES", result["verdict"])
        self.assertEqual(len(EXPECTED_GATES), len(result["gates"]))
        self.assertEqual(len(EXPECTED_GATES),
                         len(result["resolution_requests"]))
        for request in result["resolution_requests"]:
            paths = {
                row["path"] for row in request.get("resolution_paths", [])
            }
            with self.subTest(gate=request.get("capability_gate")):
                self.assertTrue(request["request_id"])
                self.assertTrue(request["missing_fields"])
                self.assertTrue(request["acceptable_evidence"])
                self.assertTrue(paths & ACTIONABLE_PATHS
                                or harness.TYPED_STOP in paths)
                if not paths & ACTIONABLE_PATHS:
                    self.assertEqual(harness.TYPED_STOP,
                                     request["recommended_path"])
                    self.assertIn("typed_stop", request)

    def test_mcp_audit_exposes_every_limit_without_plain_dead_end(self):
        audit = json.loads(mcp.TOOLS["garment_connection_audit"]("{}"))
        limitations = {
            row["limitation_id"]: row for row in audit["known_limitations"]
        }

        self.assertEqual(EXPECTED_LIMITATIONS, set(limitations))
        self.assertEqual(0, audit["summary"]["plain_dead_end_count"])
        self.assertEqual(0,
                         audit["summary"]["limitation_plain_dead_end_count"])
        for limitation_id, row in limitations.items():
            route = row["resolution_route"]
            with self.subTest(limitation=limitation_id):
                self.assertTrue(row["accepted_evidence"])
                self.assertTrue(row["next_action"])
                self.assertTrue(row["terminal_claim"])
                self.assertIn(row["status"], {
                    mcp.HUMAN_RESOLUTION,
                    mcp.OPTIONAL_PROVIDER,
                    mcp.TYPED_STOP,
                })
                self.assertTrue(route["retrievable"])
                self.assertTrue(route["resumable"])
                self.assertTrue(route["event_types"])

    def test_model_claims_and_front_image_measurements_are_not_promoted(self):
        model = _gate("MEASURED_MATERIAL", {
            "evidence_type": "MATERIAL_LAB_MEASUREMENT",
            "state": "OBSERVED",
            "source": "qwen3.6-35b-a3b",
            "source_type": "LLM",
            "value": {
                "composition": "acrylic",
                "thickness_mm": 1.2,
                "stretch": {"warp": 0.1, "weft": 0.2},
                "friction": 0.35,
                "bending": 0.004,
            },
        })
        row = model["gates"][0]["alternatives"][0]
        self.assertEqual(harness.PROPOSED, row["evidence_state"])
        self.assertFalse(row["accepted_for_gate"])
        self.assertNotEqual("ANSWER", model["gates"][0]["verdict"])

        body_boundary = corpus_manifest.provider_capability(
            "front-body-model",
            "BODY_MEASUREMENT",
            health="READY",
            available=True,
        )
        front = corpus_manifest.provider_result(
            body_boundary,
            proposals=[{"height_cm": 170}],
            provenance=[{"image": "fixture://front.png"}],
            result_authority="MEASURED",
            source_origin="FRONT_IMAGE_MULTIMODAL_ANALYSIS",
            direct_observation=True,
        )
        self.assertEqual(corpus_manifest.TYPED_STOP,
                         front["result_action"])
        self.assertFalse(front["observed"])
        self.assertEqual(corpus_manifest.PROPOSED_UNOBSERVED,
                         front["accepted_authority"])

    def test_owner_outer_digest_and_factory_job_boundaries_are_typed(self):
        owned = harness.new_workflow("project-a")
        with self.assertRaises(ValueError):
            harness.migrate_workflow(owned, "project-b")

        tampered = copy.deepcopy(owned)
        tampered["revision"] += 1
        with self.assertRaises(ValueError):
            harness.migrate_workflow(tampered, "project-a")

        factory = garment_factory.advance(
            garment_factory.new_job("factory-boundary"),
            {"type": "NOT_A_FACTORY_EVENT"},
        )
        self.assertEqual("UNKNOWN_FACTORY_EVENT", factory["verdict"])
        self.assertTrue(factory["resolution_request"]["request_id"])

        job = generation_job.apply(
            generation_job.new_job("generation-boundary"),
            {"kind": "NOT_A_GENERATION_EVENT"},
        )
        self.assertEqual("UNKNOWN_INVALID_JOB_EVENT", job["verdict"])
        self.assertTrue(job["resolution_request"]["request_id"])

    def test_gate_and_provider_reports_are_deterministic(self):
        evidence = [
            {
                "evidence_type": "MATERIAL_LAB_MEASUREMENT",
                "state": "OBSERVED",
                "source": "lab-b",
                "source_type": "LAB",
                "value": {"bending": 0.009},
            },
            {
                "evidence_type": "MATERIAL_LAB_MEASUREMENT",
                "state": "OBSERVED",
                "source": "lab-a",
                "source_type": "LAB",
                "value": {"bending": 0.004},
            },
        ]
        first = harness.evaluate_capability_gates(
            harness.new_workflow("deterministic-boundary"),
            ["MEASURED_MATERIAL"],
            evidence={"MEASURED_MATERIAL": evidence},
        )
        second = harness.evaluate_capability_gates(
            harness.new_workflow("deterministic-boundary"),
            ["MEASURED_MATERIAL"],
            evidence={"MEASURED_MATERIAL": list(reversed(evidence))},
        )
        self.assertEqual(first["workflow"]["workflow_digest"],
                         second["workflow"]["workflow_digest"])
        self.assertEqual(first["gates"][0]["gate_digest"],
                         second["gates"][0]["gate_digest"])
        self.assertEqual(harness.CONTESTED, first["gates"][0]["state"])
        self.assertFalse(first["gates"][0]["averaged"])

        self.assertEqual(corpus_manifest.provider_capability_report(),
                         corpus_manifest.provider_capability_report())

    def test_disconnected_search_and_corpus_and_denied_rights_fail_closed(self):
        retrieval = run_retrieval({"config": {"mode": "precomputed"}})
        self.assertEqual("UNKNOWN_NO_FASHION_RETRIEVAL_INDEX",
                         retrieval["verdict"])
        self.assertEqual("AWAITING_PROVIDER_OR_CONSENT", retrieval["state"])
        self.assertIn(corpus_manifest.CONNECT_PROVIDER, {
            row["action"] for row in retrieval["resolution_options"]
        })

        report = corpus_manifest.provider_capability_report()
        for capability in (
                "FASHION_SIMILARITY_RETRIEVAL",
                "SEWING_CONSTRUCTION_CORPUS"):
            row = report["capabilities"][capability]
            with self.subTest(capability=capability):
                self.assertFalse(row["provider_boundary"]["available"])
                self.assertTrue(row["provider_result"]["typed_stop"])
                self.assertEqual([], row["provider_result"]["proposals"])

        denied = corpus_manifest.provider_capability(
            "rights-denied-index",
            "FASHION_SIMILARITY_RETRIEVAL",
            health="READY",
            available=True,
            require_commercial=True,
            rights={"rights_review": {"commercial_use": "denied"}},
        )
        self.assertFalse(denied["available"])
        self.assertEqual("RIGHTS_REFUSED", denied["health"])
        denied_result = corpus_manifest.provider_result(
            denied, proposals=[{"item_id": "must-not-escape"}])
        self.assertTrue(denied_result["typed_stop"])
        self.assertEqual([], denied_result["proposals"])


class CrossSemanticsAuditTests(unittest.TestCase):
    """Measure current tagged-record semantics without relying on its name.

    These checks deliberately distinguish an evidence ledger from a physical
    local-basis artifact.  They do not treat either representation as a solver,
    and they do not infer causal power from the ``cause`` labels alone.
    """

    maxDiff = None

    def test_cause_tag_is_ignored_by_capability_gate_semantics(self):
        base = {
            "evidence_type": "MATERIAL_LAB_MEASUREMENT",
            "state": "OBSERVED",
            "source": "named-lab",
            "source_type": "LAB",
            "value": {
                "composition": {"acrylic": 1.0},
                "thickness_mm": 1.0,
                "stretch": {"warp": 0.1, "weft": 0.2},
                "friction": 0.3,
                "bending": 0.004,
            },
        }
        cause_plus = _gate("MEASURED_MATERIAL",
                           dict(base, arm="cause+"))
        cause_minus = _gate("MEASURED_MATERIAL",
                            dict(base, arm="cause-"))

        plus_gate = cause_plus["gates"][0]
        minus_gate = cause_minus["gates"][0]
        self.assertEqual(plus_gate["verdict"], minus_gate["verdict"])
        self.assertEqual(plus_gate["selected_value"],
                         minus_gate["selected_value"])
        self.assertEqual(plus_gate["gate_digest"], minus_gate["gate_digest"])
        self.assertNotIn("arm", plus_gate["alternatives"][0])
        self.assertNotIn("arm", minus_gate["alternatives"][0])

    def test_cause_arm_changes_ledger_metadata_not_resolved_value(self):
        resolved = {}
        for kind, expected_arm in (("derived", "cause+"),
                                   ("feeds", "cause-")):
            store = tagged_record_store.CrossStore()
            placed = store.put("subject", "parameter", 42, kind,
                               "named-source")
            self.assertEqual("ANSWER", placed["verdict"])
            row = store.resolve("subject", "parameter")
            self.assertEqual("ANSWER", row["verdict"])
            self.assertEqual(42, row["value"])
            self.assertEqual(expected_arm, row["arm"])
            self.assertEqual([expected_arm], row["arms"])
            resolved[kind] = row

        self.assertEqual(resolved["derived"]["verdict"],
                         resolved["feeds"]["verdict"])
        self.assertEqual(resolved["derived"]["value"],
                         resolved["feeds"]["value"])
        self.assertEqual(resolved["derived"]["weight"],
                         resolved["feeds"]["weight"])
        self.assertNotEqual(resolved["derived"]["arm"],
                            resolved["feeds"]["arm"])

    def test_permutation_is_invariant_or_explicitly_order_dependent(self):
        independent = [
            ("subject", "a", 1, "derived", "solver-a"),
            ("subject", "b", 2, "feeds", "consumer-b"),
            ("subject", "c", 3, "specific", "reviewer-c"),
        ]
        stable = tagged_record_store.ingest_order_check(independent)
        self.assertEqual("ANSWER", stable["verdict"])
        self.assertEqual([], stable["differences"])
        self.assertEqual(0, stable["budget_arm_differences"])

        shared_address = [
            ("subject", "shared", 42, "derived", "solver"),
            ("subject", "shared", 42, "feeds", "consumer"),
        ]
        surfaced = tagged_record_store.ingest_order_check(shared_address)
        self.assertEqual(tagged_record_store.ORDER_DEPENDENT,
                         surfaced["verdict"])
        self.assertGreater(surfaced["budget_arm_differences"], 0)
        self.assertTrue(surfaced["differences"])
        self.assertEqual("first_kind_seated",
                         surfaced["budget_arm_rule"])
        self.assertIn("格納順", surfaced["why_it_matters"])

    def test_evidence_and_physical_channels_remain_separate(self):
        result = harness.record_stage(
            harness.new_workflow("channel-separation"),
            stage="SIMULATION",
            event={
                "evidence_cross": {
                    "schema": "tagged-evidence-ledger.v1",
                    "arms": {
                        "cause+": [{
                            "path": "fit.waist_residual",
                            "value": 0.2,
                            "state": "INFERRED",
                            "source": "geometry-check",
                        }],
                    },
                },
                "physical_cross": {
                    "schema": "physical-local-basis.v1",
                    "state": "INFERRED",
                    "local_basis": {
                        "warp": [1, 0, 0],
                        "weft": [0, 1, 0],
                        "normal": [0, 0, 1],
                    },
                    "forces": {"warp": 1.5},
                },
            },
            outcome={"verdict": "ANSWER"},
        )
        workflow = result["workflow"]
        evidence_claim = next(
            row for row in workflow["evidence"]["claims"]
            if row["address"] == "fit.waist_residual"
        )
        physical_layer = workflow["physical"]["layers"][0]

        self.assertNotEqual(workflow["evidence"]["schema"],
                            workflow["physical"]["schema"])
        self.assertEqual("cause+", evidence_claim["provenance"]
                         ["evidence_cross_arm"])
        self.assertNotIn("local_basis", evidence_claim)
        self.assertEqual("physical-local-basis.v1",
                         physical_layer["artifact"]["schema"])
        self.assertIn("local_basis", physical_layer["artifact"])
        self.assertNotEqual(evidence_claim["claim_digest"],
                            physical_layer["artifact_digest"])


class AdversarialGapTests(unittest.TestCase):
    """Safe assertions expected to expose current integration gaps."""

    maxDiff = None

    def test_rear_evidence_type_does_not_override_front_view_provenance(self):
        result = _gate("REAR_FROM_SINGLE_FRONT", {
            "evidence_type": "REAR_IMAGE",
            "state": "OBSERVED",
            "source": "camera-a",
            "source_type": "CAMERA",
            "value": {"surface_digest": "front-surface"},
            "provenance": {"view": "FRONT", "rear_visible": False},
        })
        _assert_gate_refused(self, result)

    def test_exact_material_requires_all_requested_measured_channels(self):
        result = _gate("MEASURED_MATERIAL", {
            "evidence_type": "MATERIAL_LAB_MEASUREMENT",
            "state": "OBSERVED",
            "source": "lab-a",
            "source_type": "LAB",
            "value": {"bending": 0.004},
        })
        _assert_gate_refused(self, result)

    def test_exact_body_dimensions_require_complete_measurement_set(self):
        result = _gate("BODY_DIMENSIONS_FROM_IMAGE", {
            "evidence_type": "TAPE_MEASUREMENT",
            "state": "OBSERVED",
            "source": "named-measurer",
            "source_type": "MEASUREMENT",
            "value": {"height_cm": 170},
        })
        _assert_gate_refused(self, result)

    def test_one_approved_target_cannot_prove_arbitrary_garment_fidelity(self):
        result = _gate("ARBITRARY_GARMENT_FIDELITY", {
            "evidence_type": "HUMAN_APPROVED_TARGET",
            "state": "OBSERVED",
            "source": "reviewer-a",
            "source_type": "HUMAN_REVIEW",
            "value": {"candidate_digest": "one-garment"},
        })
        _assert_gate_refused(self, result)

    def test_one_toile_cannot_prove_universal_sewable_pattern_guarantee(self):
        result = _gate("COMPLETE_PATTERN_GUARANTEE", {
            "evidence_type": "PHYSICAL_TOILE_VALIDATION",
            "state": "OBSERVED",
            "source": "pattern-reviewer-a",
            "source_type": "PHYSICAL_REVIEW",
            "value": {"pattern_digest": "one-pattern", "toile": "one"},
        })
        _assert_gate_refused(self, result)

    def test_exact_finish_requires_finish_lining_interfacing_and_machine_setup(self):
        result = _gate("SEAM_FINISH_CONSTRUCTION", {
            "evidence_type": "APPROVED_SEWING_SPEC",
            "state": "OBSERVED",
            "source": "sewing-reviewer-a",
            "source_type": "HUMAN_REVIEW",
            "value": {"seam_finish": "overlock"},
        })
        _assert_gate_refused(self, result)

    def test_one_trial_cannot_prove_few_percent_real_cloth_accuracy(self):
        result = _gate("REAL_CLOTH_ERROR_GUARANTEE", {
            "evidence_type": "CALIBRATED_REAL_CLOTH_TRIAL",
            "state": "OBSERVED",
            "source": "lab-trial-a",
            "source_type": "LAB",
            "value": {"error_percent": 2.0, "sample_count": 1},
        })
        _assert_gate_refused(self, result)

    def test_wind_calibration_requires_conditions_and_calibration_digest(self):
        result = _gate("WIND_TUNNEL_CALIBRATION", {
            "evidence_type": "WIND_TUNNEL_MEASUREMENT",
            "state": "OBSERVED",
            "source": "wind-lab-a",
            "source_type": "LAB",
            "value": {"drag_n": 1.2},
        })
        _assert_gate_refused(self, result)

    def test_cross_search_gate_honours_explicit_rights_denial(self):
        result = _gate("CONNECTED_FASHION_SEARCH", {
            "evidence_type": "CONNECTED_SEARCH_PROVIDER",
            "state": "OBSERVED",
            "source": "fashion-index-a",
            "source_type": "INDEX_PROVIDER",
            "value": {"provider": "fashion-index-a", "index_digest": "idx"},
            "provenance": {
                "rights_review": {"commercial_use": "denied"},
            },
        })
        _assert_gate_refused(self, result)

    def test_direct_provider_authority_requires_typed_evidence_payload(self):
        boundary = corpus_manifest.provider_capability(
            "empty-body-provider",
            "BODY_MEASUREMENT",
            health="READY",
            available=True,
        )
        result = corpus_manifest.provider_result(
            boundary,
            proposals=[],
            provenance=[],
            result_authority="MEASURED",
            source_origin="TAPE_MEASUREMENT",
            direct_observation=True,
        )
        self.assertEqual(corpus_manifest.TYPED_STOP,
                         result["result_action"])
        self.assertFalse(result["observed"])

    def test_provider_consent_cannot_be_granted_by_a_model(self):
        consent = corpus_manifest.validate_provider_consent(
            {
                "schema": corpus_manifest.PROVIDER_CONSENT_SCHEMA,
                "action": corpus_manifest.CONSENTED_LLM_PROPOSAL,
                "by": "qwen3.6-35b-a3b",
                "scopes": ["REAR_HYPOTHESIS"],
            },
            required_scope="REAR_HYPOTHESIS",
        )
        self.assertNotEqual(corpus_manifest.ANSWER, consent["verdict"])

    def test_cross_consent_is_not_replayable_across_projects(self):
        source = harness.new_workflow("consent-project-a")
        granted = harness.grant_model_consent(
            source,
            scope="MATERIAL_CALIBRATION",
            fields=["material.bending"],
            granted_by="Reviewer A",
            expires_after_revision=100,
        )
        artifact = granted["consent_artifact"]

        destination = harness.evaluate_capability_gates(
            harness.new_workflow("consent-project-b"),
            ["MEASURED_MATERIAL"],
        )
        request = destination["resolution_request"]
        forged_destination = copy.deepcopy(destination["workflow"])
        forged_destination["consents"].append(copy.deepcopy(artifact))
        harness._seal(forged_destination)

        resolved = harness.resolve_request(
            forged_destination,
            request_id=request["request_id"],
            choice=harness.CONSENTED_LLM_PROPOSAL,
            values={"material.bending": 0.004},
            actor="qwen3.6-35b-a3b",
            consent_digest=artifact["consent_digest"],
        )
        self.assertNotEqual("ANSWER", resolved["verdict"])
        self.assertNotIn("material.bending",
                         resolved["workflow"]["evidence"]["resolutions"])

    def test_cross_consent_rejects_a_rehashed_bound_digest_tamper(self):
        staged = harness.evaluate_capability_gates(
            harness.new_workflow("consent-digest-binding"),
            ["MEASURED_MATERIAL"],
        )
        request = staged["resolution_request"]
        granted = harness.grant_model_consent(
            staged["workflow"],
            scope=request["stage"],
            fields=request["missing_fields"],
            granted_by="Reviewer Digest",
            expires_after_revision=100,
            request_id=request["request_id"],
        )
        forged = copy.deepcopy(granted["workflow"])
        consent = forged["consents"][0]
        consent["bound_workflow_digest"] = "0" * 64
        consent["consent_digest"] = harness.stable_digest({
            key: copy.deepcopy(value) for key, value in consent.items()
            if key != "consent_digest"
        })
        harness._seal(forged)

        resolved = harness.resolve_request(
            forged,
            request_id=request["request_id"],
            choice=harness.CONSENTED_LLM_PROPOSAL,
            values={field: "proposed-value"
                    for field in request["missing_fields"]},
            actor="qwen3.6-35b-a3b",
            consent_digest=consent["consent_digest"],
        )
        obligation = next(
            row for row in resolved["workflow"]["obligations"]
            if row["request_id"] == request["request_id"]
        )
        self.assertNotEqual("ANSWER", resolved["verdict"])
        self.assertEqual("OPEN", obligation["status"])

    def test_resolution_values_must_match_the_request_fields(self):
        staged = harness.evaluate_capability_gates(
            harness.new_workflow("request-field-binding"),
            ["MEASURED_MATERIAL"],
        )
        request = staged["resolution_request"]
        granted = harness.grant_model_consent(
            staged["workflow"],
            scope=request["stage"],
            fields=["rear.surface"],
            granted_by="Reviewer B",
            expires_after_revision=100,
            request_id=request["request_id"],
        )
        resolved = harness.resolve_request(
            granted["workflow"],
            request_id=request["request_id"],
            choice=harness.CONSENTED_LLM_PROPOSAL,
            values={"rear.surface": "closed-back"},
            actor="qwen3.6-35b-a3b",
            consent_digest=granted["consent_artifact"]["consent_digest"],
        )
        self.assertNotEqual("ANSWER", resolved["verdict"])
        self.assertEqual("OPEN", next(
            row for row in resolved["workflow"]["obligations"]
            if row["request_id"] == request["request_id"]
        )["status"])

    def test_partial_measurement_does_not_close_a_multi_field_obligation(self):
        staged = harness.evaluate_capability_gates(
            harness.new_workflow("partial-material-resolution"),
            ["MEASURED_MATERIAL"],
        )
        request = staged["resolution_request"]
        resolved = harness.resolve_request(
            staged["workflow"],
            request_id=request["request_id"],
            choice=harness.MEASURED_INPUT,
            values={"material.bending": 0.004},
            actor="Named Lab Technician",
            provenance={"source_type": "LAB_MEASUREMENT"},
        )
        obligation = next(
            row for row in resolved["workflow"]["obligations"]
            if row["request_id"] == request["request_id"]
        )
        self.assertNotEqual("ANSWER", resolved["verdict"])
        self.assertEqual("OPEN", obligation["status"])

    def test_untrusted_automation_identity_cannot_claim_measured_authority(self):
        staged = harness.evaluate_capability_gates(
            harness.new_workflow("automation-authority"),
            ["BODY_DIMENSIONS_FROM_IMAGE"],
        )
        request = staged["resolution_request"]
        resolved = harness.resolve_request(
            staged["workflow"],
            request_id=request["request_id"],
            choice=harness.MEASURED_INPUT,
            values={"body.height": 170},
            actor="analysis-worker-7",
            provenance={"source_type": "AUTOMATION"},
        )
        self.assertNotEqual("ANSWER", resolved["verdict"])
        height = resolved["workflow"]["evidence"]["resolutions"].get(
            "body.height")
        if height is not None:
            self.assertNotEqual(harness.OBSERVED, height["state"])


class AdversarialContractBindingGapTests(unittest.TestCase):
    """Complete-looking dictionaries must not bypass authoritative contracts.

    The generic workflow gate is a public boundary.  A caller therefore must
    not be able to obtain ``ANSWER`` merely by spelling every expected key;
    domain-contract admission, source binding, and verification must still be
    established.
    """

    def test_rear_requires_registered_view_evidence_not_a_view_label(self):
        result = _gate("REAR_FROM_SINGLE_FRONT", {
            "evidence_type": "REAR_IMAGE",
            "state": "OBSERVED",
            "source": "camera-a",
            "source_type": "CAMERA",
            "value": {
                "surface_digest": "claimed-rear-surface",
                "construction_digest": "claimed-rear-construction",
            },
            "provenance": {
                "view": "REAR",
                "rear_visible": True,
                "registered": False,
            },
        })
        _assert_gate_refused(self, result)

    def test_material_requires_authorized_calibration_decision(self):
        result = _gate("MEASURED_MATERIAL", {
            "evidence_type": "MATERIAL_LAB_MEASUREMENT",
            "state": "OBSERVED",
            "source": "lab-a",
            "source_type": "LAB",
            "value": {
                "composition": {"acrylic": 1.0},
                "thickness_mm": 1.0,
                "stretch": {"warp": 0.1, "weft": 0.2},
                "friction": 0.3,
                "bending": 0.004,
            },
            "provenance": {"calibration_decision_digest": ""},
        })
        _assert_gate_refused(self, result)

    def test_body_requires_units_method_and_measurement_contract(self):
        result = _gate("BODY_DIMENSIONS_FROM_IMAGE", {
            "evidence_type": "TAPE_MEASUREMENT",
            "state": "OBSERVED",
            "source": "clipboard-import",
            "source_type": "MEASUREMENT",
            "value": {
                "height": 170,
                "chest": 92,
                "waist": 76,
                "hip": 98,
                "body_length": 62,
            },
            "provenance": {"measurement_method": "UNSPECIFIED"},
        })
        _assert_gate_refused(self, result)

    def test_fidelity_requires_bound_validation_not_self_declared_coverage(self):
        result = _gate("ARBITRARY_GARMENT_FIDELITY", {
            "evidence_type": "HUMAN_APPROVED_TARGET",
            "state": "OBSERVED",
            "source": "self-report",
            "source_type": "REVIEW",
            "value": {
                "scope_kind": "FINITE_DECLARED",
                "coverage_complete": True,
                "validation_set": ["one-unverified-case"],
                "fidelity_threshold": 0.99,
            },
            "provenance": {},
        })
        _assert_gate_refused(self, result)

    def test_pattern_requires_verified_package_not_digest_shaped_strings(self):
        result = _gate("COMPLETE_PATTERN_GUARANTEE", {
            "evidence_type": "PHYSICAL_TOILE_VALIDATION",
            "state": "OBSERVED",
            "source": "self-report",
            "source_type": "REVIEW",
            "value": {
                "scope_kind": "FINITE_DECLARED",
                "coverage_complete": True,
                "pattern_digest": "not-a-verified-package",
                "validation_set_digest": "not-a-validation-set",
                "manufacturability_checks": ["claimed-pass"],
            },
            "provenance": {},
        })
        _assert_gate_refused(self, result)

    def test_finish_requires_approved_finish_contract_decision(self):
        result = _gate("SEAM_FINISH_CONSTRUCTION", {
            "evidence_type": "APPROVED_SEWING_SPEC",
            "state": "OBSERVED",
            "source": "self-report",
            "source_type": "REVIEW",
            "value": {
                "seam_finish": "french",
                "interfacing": "fusible",
                "lining": "full",
                "machine_setup": "needle-80",
            },
            "provenance": {"finish_decision_digest": ""},
        })
        _assert_gate_refused(self, result)

    def test_real_cloth_claim_requires_authorized_calibration_decision(self):
        result = _gate("REAL_CLOTH_ERROR_GUARANTEE", {
            "evidence_type": "CALIBRATED_REAL_CLOTH_TRIAL",
            "state": "OBSERVED",
            "source": "self-report",
            "source_type": "LAB",
            "value": {
                "error_percent": 2.0,
                "sample_count": 2,
                "test_population": ["a", "b"],
                "threshold_percent": 3.0,
                "calibration_digest": "not-an-authorized-decision",
            },
            "provenance": {},
        })
        _assert_gate_refused(self, result)

    def test_wind_claim_requires_authorized_calibration_decision(self):
        result = _gate("WIND_TUNNEL_CALIBRATION", {
            "evidence_type": "WIND_TUNNEL_MEASUREMENT",
            "state": "OBSERVED",
            "source": "self-report",
            "source_type": "LAB",
            "value": {
                "measurements": [1.0],
                "boundary_conditions": {"wind_mps": 5.0},
                "calibration_digest": "not-an-authorized-decision",
            },
            "provenance": {},
        })
        _assert_gate_refused(self, result)

    def test_search_requires_bound_provider_result_not_names_and_rights_flag(self):
        result = _gate("CONNECTED_FASHION_SEARCH", {
            "evidence_type": "CONNECTED_SEARCH_PROVIDER",
            "state": "OBSERVED",
            "source": "self-report",
            "source_type": "PROVIDER",
            "value": {
                "provider_id": "made-up-provider",
                "index_digest": "made-up-index",
            },
            "provenance": {
                "rights_review": {"commercial_use": "allowed"},
            },
        })
        _assert_gate_refused(self, result)

    def test_direct_provider_needs_contract_typed_payload_not_nonempty_lists(self):
        capability = corpus_manifest.provider_capability(
            "body-provider", "BODY_MEASUREMENT",
            health="READY", available=True,
        )
        result = corpus_manifest.provider_result(
            capability,
            proposals=[{"anything": "looks nonempty"}],
            provenance=[{"anything": "also nonempty"}],
            result_authority="MEASURED",
            source_origin="REGISTERED_TAPE_PROVIDER",
            direct_observation=True,
        )
        self.assertEqual(corpus_manifest.TYPED_STOP,
                         result["result_action"])
        self.assertFalse(result["observed"])


class AdversarialRouteBindingGapTests(unittest.TestCase):
    """Published contract tools must expose a real factory/job resume route."""

    def test_connected_contract_rows_have_a_factory_resume_event(self):
        audit = json.loads(mcp.TOOLS["garment_connection_audit"]("{}"))
        rows = {
            row["component"]: row for row in audit["components"]
        }
        for component in (
                "physical calibration claim gate",
                "manufacturing finish decision gate"):
            row = rows[component]
            with self.subTest(component=component):
                self.assertEqual(mcp.CONNECTED, row["status"])
                self.assertTrue(
                    row["factory_events"],
                    msg=(f"{component} is reported CONNECTED even though its "
                         "factory_events route is empty"),
                )

    def test_factory_generation_and_harness_bind_authoritative_contracts(self):
        orchestration_source = "\n".join((
            inspect.getsource(garment_factory),
            inspect.getsource(generation_job),
            inspect.getsource(harness),
        ))
        missing = [
            module_name for module_name in (
                "physical_calibration_contract",
                "manufacturing_finish_contract",
                "reconstruction_claim_contract",
            ) if module_name not in orchestration_source
        ]
        self.assertEqual(
            [], missing,
            msg=("authoritative contracts exist but are not referenced by the "
                 f"factory/generation/harness route: {missing}"),
        )


if __name__ == "__main__":
    unittest.main()
