#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused contracts for the engine-side Cross workflow harness."""
from __future__ import annotations

import copy
import unittest

from photoloset import cross_workflow_harness as harness
from photoloset import garment_factory, generation_job


class CrossWorkflowHarnessTests(unittest.TestCase):
    def assert_typed_request(self, request):
        self.assertIsInstance(request, dict)
        self.assertEqual(request["schema"], harness.RESOLUTION_SCHEMA)
        self.assertTrue(request["request_id"])
        self.assertTrue(request["stage"])
        self.assertTrue(request["missing_fields"])
        self.assertTrue(request["acceptable_evidence"])
        self.assertEqual(
            {row["choice"] for row in request["choices"]},
            set(harness.RESOLUTION_CHOICES),
        )
        self.assertTrue(request["resolution_paths"])
        self.assertTrue(
            {row["path"] for row in request["resolution_paths"]}.issubset(
                set(harness.RESOLUTION_PATHS)))

    def test_no_silent_unknown_through_both_engine_boundaries(self):
        factory = garment_factory.advance(
            garment_factory.new_job("factory-cross"),
            {"type": "NOT_A_FACTORY_EVENT"},
        )
        self.assertEqual(factory["verdict"], "UNKNOWN_FACTORY_EVENT")
        self.assert_typed_request(factory["resolution_request"])
        self.assertEqual(
            factory["state"]["cross_workflow"]["obligations"][-1][
                "request_id"],
            factory["resolution_request"]["request_id"],
        )

        job = generation_job.apply(
            generation_job.new_job("job-cross"),
            {"kind": "NOT_A_JOB_EVENT"},
        )
        self.assertEqual(job["verdict"], "UNKNOWN_INVALID_JOB_EVENT")
        self.assert_typed_request(job["resolution_request"])
        self.assertEqual(
            job["cross_workflow"]["obligations"][-1]["request_id"],
            job["resolution_request"]["request_id"],
        )

    def test_all_cross_unknowns_become_separate_typed_requests(self):
        result = harness.record_stage(
            harness.new_workflow("multi-obligation"),
            stage="REAR_INFERENCE",
            event={
                "evidence_cross": {
                    "schema": "example.evidence-cross.v1",
                    "arms": {
                        "support-": [
                            {"path": "rear.closure",
                             "state": "UNKNOWN_UNOBSERVED"},
                        ],
                    },
                },
                "proof_cross": {
                    "verdict": "UNKNOWN_PROOF_OBLIGATION",
                    "proof_digest": "sha256:upstream",
                },
            },
            outcome={
                "verdict": "UNKNOWN_REAR_REQUIRED",
                "reason": "the front image does not observe the rear",
                "details": {"missing_fields": ["rear.surface"]},
            },
        )
        requests = result["resolution_requests"]
        self.assertEqual(len(requests), 3)
        self.assertEqual(
            {row["verdict"] for row in requests},
            {"UNKNOWN_REAR_REQUIRED",
             "UNKNOWN_CROSS_EVIDENCE_OBLIGATION",
             "UNKNOWN_PROOF_OBLIGATION"},
        )
        for request in requests:
            self.assert_typed_request(request)
        self.assertEqual(len(result["workflow"]["obligations"]), 3)

    def test_model_never_escalates_to_observed_even_with_consent(self):
        staged = harness.record_stage(
            harness.new_workflow("authority"), stage="REAR",
            event={"cross_claims": [{
                "address": "rear.opening",
                "value": "zipper",
                "state": "OBSERVED",
                "source": "qwen3.6-35b-a3b",
            }]},
            outcome={"verdict": "UNKNOWN_REAR_CONFIRMATION",
                     "reason": "rear is unobserved",
                     "details": {"missing_fields": ["rear.opening"]}},
        )
        before = staged["workflow"]
        self.assertEqual(
            before["evidence"]["resolutions"]["rear.opening"]["state"],
            harness.PROPOSED,
        )
        request = staged["resolution_request"]
        consent = harness.grant_model_consent(
            before, scope="REAR", fields=["rear.opening"],
            granted_by="Mina", expires_after_revision=before["revision"] + 2,
            request_id=request["request_id"],
        )
        artifact = consent["consent_artifact"]
        self.assertEqual(artifact["authority_ceiling"], harness.PROPOSED)
        self.assertEqual(artifact["fields"], ["rear.opening"])
        self.assertIn("expiry", artifact)
        self.assertTrue(artifact["consent_digest"])

        resolved = harness.resolve_request(
            consent["workflow"], request_id=request["request_id"],
            choice=harness.LLM_PROPOSAL_WITH_CONSENT,
            values={"rear.opening": "buttons"}, actor="qwen3.6-35b-a3b",
            consent_digest=artifact["consent_digest"],
        )
        self.assertEqual(resolved["verdict"], "ANSWER")
        evidence = resolved["workflow"]["evidence"]["resolutions"][
            "rear.opening"]
        self.assertEqual(evidence["state"], harness.PROPOSED)
        self.assertFalse(any(
            row["evidence_state"] == harness.OBSERVED
            for row in evidence["alternatives"]
        ))

    def test_model_resolution_without_consent_remains_unresolved(self):
        staged = harness.record_stage(
            harness.new_workflow("no-consent"), stage="MATERIAL",
            outcome={"verdict": "UNKNOWN_MATERIAL_VALUE_REQUIRED",
                     "reason": "material was not measured",
                     "details": {"missing_fields": ["material.bending"]}},
        )
        result = harness.resolve_request(
            staged["workflow"],
            request_id=staged["resolution_request"]["request_id"],
            choice=harness.LLM_PROPOSAL_WITH_CONSENT,
            values={"material.bending": 0.004}, actor="model",
        )
        self.assertEqual(result["verdict"],
                         "UNKNOWN_MODEL_CONSENT_REQUIRED")
        self.assert_typed_request(result["resolution_request"])
        self.assertNotIn(
            "material.bending", result["workflow"]["evidence"][
                "resolutions"])

    def test_disagreement_is_preserved_without_average_or_winner(self):
        result = harness.record_stage(
            harness.new_workflow("disagreement"), stage="CALIBRATION",
            event={"cross_claims": [
                {"address": "material.bending", "value": 0.004,
                 "state": "OBSERVED", "source": "lab-a",
                 "source_type": "MEASUREMENT"},
                {"address": "material.bending", "value": 0.009,
                 "state": "INFERRED", "source": "inverse-solver",
                 "source_type": "DERIVED"},
            ]},
            outcome={"verdict": "ANSWER"},
        )
        resolution = result["workflow"]["evidence"]["resolutions"][
            "material.bending"]
        self.assertEqual(resolution["state"], harness.CONTESTED)
        self.assertEqual({row["value"] for row in resolution["alternatives"]},
                         {0.004, 0.009})
        self.assertFalse(resolution["averaged"])
        self.assertIsNone(resolution["selected_value"])

    def test_ingest_order_and_mapping_order_have_identical_digests(self):
        claims = [
            {"address": "front.length", "value": 100,
             "state": "OBSERVED", "source": "human"},
            {"address": "rear.length", "value": 102,
             "state": "PROPOSED", "source": "model",
             "source_type": "LLM"},
        ]
        first_workflow = harness.new_workflow("deterministic")
        second_workflow = harness.new_workflow("deterministic")
        first = harness.record_stage(
            first_workflow, stage="SHAPE",
            event={"kind": "RUN", "cross_claims": claims,
                   "input_workflow_digest": first_workflow["workflow_digest"],
                   "physical_cross": {"state": "INFERRED", "b": 2, "a": 1}},
            outcome={"verdict": "ANSWER"},
        )
        second = harness.record_stage(
            second_workflow, stage="SHAPE",
            event={"physical_cross": {"a": 1, "b": 2,
                                       "state": "INFERRED"},
                   "input_workflow_digest": second_workflow["workflow_digest"],
                   "cross_claims": list(reversed(claims)), "kind": "RUN"},
            outcome={"verdict": "ANSWER"},
        )
        self.assertEqual(first["workflow"]["workflow_digest"],
                         second["workflow"]["workflow_digest"])
        self.assertEqual(first["workflow"]["semantic_digest"],
                         second["workflow"]["semantic_digest"])
        record = first["stage_record"]
        self.assertTrue(record["same_old_state"])
        self.assertEqual(record["reduction"],
                         "CANONICAL_ORDER_DETERMINISTIC_REDUCE")
        self.assertEqual(first["workflow"]["proof"]["reports"][-1][
            "report"]["verdict"], "ANSWER")

    def test_unsolvable_obligation_has_complete_typed_stop(self):
        result = harness.record_stage(
            harness.new_workflow("typed-stop"), stage="SHELL_SOLVER",
            outcome={
                "verdict": "UNKNOWN_NOT_IMPLEMENTED_SOLVER",
                "reason": "the required solver is unavailable",
                "details": {"missing_fields": ["shell.tangent"],
                            "acceptable_evidence": ["solver artifact"]},
            },
            provenance={"engine": "reference"},
        )
        request = result["resolution_request"]
        self.assertEqual(request["recommended_choice"], harness.TYPED_STOP)
        stop = request["typed_stop"]
        self.assertEqual(stop["schema"], harness.STOP_SCHEMA)
        self.assertEqual(stop["stage"], "SHELL_SOLVER")
        self.assertEqual(stop["missing_fields"], ["shell.tangent"])
        self.assertTrue(stop["acceptable_evidence"])
        self.assertEqual(stop["provenance"]["engine"], "reference")
        self.assertFalse(stop["fabricated_values"])

    def test_all_capability_gates_are_typed_and_deterministic(self):
        gate_ids = list(reversed(sorted(harness.CAPABILITY_GATES)))
        first = harness.evaluate_capability_gates(
            harness.new_workflow("capability-all"), gate_ids)
        second = harness.evaluate_capability_gates(
            harness.new_workflow("capability-all"), sorted(gate_ids))

        self.assertEqual(first["verdict"], "UNKNOWN_CAPABILITY_GATES")
        self.assertEqual(len(first["gates"]), 9)
        self.assertEqual(
            {row["gate"] for row in first["gates"]},
            set(harness.CAPABILITY_GATES),
        )
        self.assertEqual(len(first["resolution_requests"]), 9)
        self.assertEqual(first["workflow"]["workflow_digest"],
                         second["workflow"]["workflow_digest"])
        self.assertEqual(first["workflow"]["semantic_digest"],
                         second["workflow"]["semantic_digest"])
        for gate in first["gates"]:
            self.assertNotEqual(gate["verdict"], "ANSWER")
            self.assertTrue(gate["same_old_state"])
            self.assertFalse(gate["averaged"])
            self.assertEqual(gate["model_authority_ceiling"],
                             harness.PROPOSED)
        for request in first["resolution_requests"]:
            self.assert_typed_request(request)
            self.assertIn(request["capability_gate"],
                          harness.CAPABILITY_GATES)
            expected = set(harness.CAPABILITY_GATES[
                request["capability_gate"]]["paths"])
            self.assertEqual(
                {row["path"] for row in request["resolution_paths"]},
                expected,
            )

    def test_capability_gate_closes_only_with_non_model_observation(self):
        model = harness.evaluate_capability_gates(
            harness.new_workflow("capability-model"),
            ["MEASURED_MATERIAL"],
            evidence={"MEASURED_MATERIAL": [{
                "evidence_type": "MATERIAL_LAB_MEASUREMENT",
                "state": "OBSERVED",
                "source": "qwen3.6-35b-a3b",
                "source_type": "LLM",
                "value": {"bending": 0.004},
            }]},
        )
        self.assertEqual(model["gates"][0]["state"], harness.PROPOSED)
        self.assertEqual(model["gates"][0]["alternatives"][0][
            "evidence_state"], harness.PROPOSED)
        self.assertFalse(model["gates"][0]["alternatives"][0][
            "accepted_for_gate"])
        self.assertIsNotNone(model["resolution_request"])

        calibration_decision = {
            "schema": "garment.physical-calibration-decision.v1",
            "verdict": "CLAIM_AUTHORIZED",
            "claim_authorized": True,
            "claim_kind": "MATERIAL_CALIBRATED",
            "authorized_claim": {
                "claim_kind": "MATERIAL_CALIBRATED",
                "authority": "MEASURED",
            },
            "validation_checks": [{
                "counted_measurement_digests": ["fixture-measurement"],
                "threshold": {"is_non_model_approved": True},
                "outside_threshold_digests": [],
            }],
        }
        calibration_decision["decision_digest"] = harness.stable_digest(
            calibration_decision)
        measured = harness.evaluate_capability_gates(
            harness.new_workflow("capability-measured"),
            ["MEASURED_MATERIAL"],
            evidence={"MEASURED_MATERIAL": [{
                "evidence_type": "MATERIAL_LAB_MEASUREMENT",
                "state": "OBSERVED",
                "source": "lab-a",
                "source_type": "MEASUREMENT",
                "value": {
                    "composition": "acrylic",
                    "thickness_mm": 1.2,
                    "stretch": {"warp": 0.10, "weft": 0.20},
                    "friction": 0.35,
                    "bending": 0.004,
                },
                "provenance": {
                    "calibration_decision": calibration_decision,
                },
            }]},
        )
        self.assertEqual(measured["verdict"], "ANSWER")
        self.assertEqual(measured["gates"][0]["state"], harness.OBSERVED)
        self.assertIsNone(measured["resolution_request"])

    def test_model_cannot_take_measured_or_human_authority(self):
        staged = harness.evaluate_capability_gates(
            harness.new_workflow("capability-authority"),
            ["MEASURED_MATERIAL"],
        )
        result = harness.resolve_request(
            staged["workflow"],
            request_id=staged["resolution_request"]["request_id"],
            choice=harness.MEASURED_INPUT,
            values={"material.bending": 0.004},
            actor="qwen3.6-35b-a3b",
            provenance={"source_type": "LLM"},
        )
        self.assertEqual(result["verdict"],
                         "UNKNOWN_MODEL_AUTHORITY_ESCALATION")
        self.assertEqual(result["resolution_request"]["recommended_path"],
                         harness.TYPED_STOP)
        self.assertIn("typed_stop", result["resolution_request"])
        self.assertNotIn("material.bending", result["workflow"][
            "evidence"]["resolutions"])

    def test_model_cannot_grant_its_own_consent(self):
        staged = harness.record_stage(
            harness.new_workflow("self-consent"), stage="REAR",
            outcome={"verdict": "UNKNOWN_REAR_REQUIRED",
                     "details": {"missing_fields": ["rear.surface"]}},
        )
        result = harness.grant_model_consent(
            staged["workflow"], scope="REAR", fields=["rear.surface"],
            granted_by="qwen3.6-35b-a3b",
            expires_after_revision=staged["workflow"]["revision"] + 2,
            request_id=staged["resolution_request"]["request_id"],
        )
        self.assertEqual(result["verdict"],
                         "UNKNOWN_INVALID_MODEL_CONSENT")
        self.assertEqual(result["workflow"]["consents"], [])
        self.assert_typed_request(result["resolution_request"])

    def test_bounded_alternatives_remain_separate_proposals(self):
        staged = harness.evaluate_capability_gates(
            harness.new_workflow("bounded-rear"),
            ["REAR_FROM_SINGLE_FRONT"],
        )
        result = harness.resolve_request(
            staged["workflow"],
            request_id=staged["resolution_request"]["request_id"],
            choice=harness.BOUNDED_ALTERNATIVES,
            values={
                "rear.surface": ["plain-back", "center-opening"],
                "rear.construction": ["center-seam", "side-seam"],
            },
            actor="deterministic-rear-enumerator",
        )
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["resolution"]["resolution_path"],
                         harness.BOUNDED_ALTERNATIVES)
        evidence = result["workflow"]["evidence"]["resolutions"][
            "rear.surface"]
        self.assertEqual(evidence["state"], harness.PROPOSED)
        self.assertTrue(evidence["proposal_disagreement"])
        self.assertEqual(
            {row["value"] for row in evidence["alternatives"]},
            {"plain-back", "center-opening"},
        )
        self.assertFalse(evidence["averaged"])
        self.assertIsNone(evidence["selected_value"])

    def test_record_stage_runs_explicit_capability_gates(self):
        result = harness.record_stage(
            harness.new_workflow("stage-gate"), stage="RETRIEVAL",
            event={"required_capabilities": [
                "CONNECTED_FASHION_SEARCH"]},
            outcome={"verdict": "ANSWER"},
        )
        self.assertEqual(len(result["resolution_requests"]), 1)
        request = result["resolution_request"]
        self.assertEqual(request["capability_gate"],
                         "CONNECTED_FASHION_SEARCH")
        self.assertEqual(
            result["stage_record"]["capability_gate_digests"],
            [result["workflow"]["capability_gate_history"][-1][
                "gate_digest"]],
        )

    def test_current_document_without_gate_history_migrates_add_only(self):
        old = harness.new_workflow("minor-migration")
        old.pop("capability_gate_history")
        old["workflow_digest"] = harness.stable_digest(
            harness._without_digest(old))
        migrated = harness.migrate_workflow(old, "minor-migration")
        self.assertEqual(migrated["capability_gate_history"], [])
        self.assertEqual(migrated["evidence"], old["evidence"])

    def test_legacy_documents_migrate_without_mutating_domain_state(self):
        old_factory = garment_factory.new_job("legacy-factory")
        old_factory.pop("cross_workflow")
        original_factory = copy.deepcopy(old_factory)
        refused = garment_factory.advance(
            old_factory, {"type": "NOT_A_FACTORY_EVENT"})
        self.assertEqual(old_factory, original_factory)
        self.assertEqual(refused["state"]["job_id"], "legacy-factory")
        self.assertEqual(refused["state"]["cross_workflow"]["migration"][
            "source_schema"], garment_factory.SCHEMA)

        old_job = generation_job.new_job("legacy-job")
        old_job.pop("cross_workflow")
        original_job = copy.deepcopy(old_job)
        advanced = generation_job.apply(old_job, {
            "kind": "TRANSITION", "state": "IMAGE_RECEIVED",
            "artifacts": {"image": "sha256:image"},
        })
        self.assertEqual(old_job, original_job)
        self.assertEqual(advanced["snapshot"]["state"], "IMAGE_RECEIVED")
        self.assertEqual(advanced["cross_workflow"]["schema"], harness.SCHEMA)

        migrated = harness.migrate_workflow({
            "schema": "legacy.cross.v0",
            "claims": [{"address": "front.length", "value": 98,
                        "state": "INFERRED", "source": "legacy-rule"}],
            "custom_field": {"must": "survive"},
        }, "legacy-harness")
        self.assertEqual(migrated["migration"]["legacy_payload"][
            "custom_field"], {"must": "survive"})
        self.assertEqual(migrated["evidence"]["resolutions"][
            "front.length"]["state"], harness.INFERRED)


if __name__ == "__main__":
    unittest.main()
