#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from photoloset import garment_factory, generation_job, mcp


PHYSICAL_CAPABILITIES = "garment_physical_calibration_capabilities"
PHYSICAL_ASSESS = "garment_physical_calibration_assess"
FINISH_DECISION = "garment_manufacturing_finish_decision"
FINISH_APPROVE = "garment_manufacturing_finish_approve"


def call(name: str, payload: dict | None = None) -> dict:
    return json.loads(mcp.TOOLS[name](
        json.dumps(payload or {}, ensure_ascii=False)))


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def rights() -> dict:
    return {
        "license_id": "integration-fixture-license",
        "holder": "integration-fixture-owner",
        "permitted_uses": ["CALIBRATION", "CLAIM_VALIDATION"],
        "source_uri": "fixture://contract-mcp-integration",
    }


def provenance(label: str, producer_kind: str) -> dict:
    return {
        "source_id": label,
        "source_digest": digest(label),
        "method": "integration-fixture-method",
        "revision": "1",
        "producer_kind": producer_kind,
        "rights": rights(),
    }


def real_cloth_claim() -> dict:
    domain = "REAL_CLOTH"
    test_kind = "static_drape"
    metric = "shape_relative_error_percent"
    observation = {
        "observation_id": "cloth-observation-1",
        "domain": domain,
        "test_kind": test_kind,
        "metric": metric,
        "sample_id": "cloth-sample-1",
        "value": 2.0,
        "unit": "%",
        "authority": "MEASURED",
        "provenance": provenance("cloth-observation", "LAB"),
        "conditions": {"same_specimen": True},
    }
    return {
        "schema": "garment.physical-calibration-contract.v1",
        "claim_id": "real-cloth-three-percent",
        "subject_id": "garment-integration-fixture",
        "claim_kind": "REAL_CLOTH_ERROR_BOUND",
        "domain": domain,
        "material_properties": [{
            "property_name": "thickness",
            "value": 0.001,
            "unit": "m",
            "authority": "MEASURED",
            "provenance": provenance("cloth-thickness", "LAB"),
            "conditions": {"temperature_c": 20.0},
        }],
        "datasets": [{
            "dataset_id": "cloth-dataset-1",
            "domain": domain,
            "tests": [{
                "test_id": "cloth-test-1",
                "domain": domain,
                "test_kind": test_kind,
                "observations": [observation],
                "provenance": provenance("cloth-test", "LAB"),
            }],
            "provenance": provenance("cloth-dataset", "LAB"),
        }],
        "thresholds": [{
            "threshold_id": "cloth-threshold-1",
            "domain": domain,
            "metric": metric,
            "operator": "MAXIMUM",
            "value": 3.0,
            "unit": "%",
            "minimum_samples": 1,
            "approved_by": "Named physical reviewer",
            "provenance": provenance("cloth-threshold", "HUMAN"),
        }],
        "requested_error_percent": 3.0,
        "plan": {
            "plan_id": "integration-real-cloth-plan",
            "domain": domain,
            "required_material_properties": ["thickness"],
            "requirements": [{
                "test_kind": test_kind,
                "metric": metric,
                "unit": "%",
                "minimum_samples": 1,
            }],
            "description": "One explicitly measured integration fixture.",
        },
    }


def finish_request(*, model: bool = False) -> dict:
    rows = [
        {"field": "seam_finish", "target": "side-seam", "value": "FRENCH"},
        {"field": "interfacing", "target": "garment", "value": "NONE"},
        {"field": "lining", "target": "garment", "value": "NONE"},
    ]
    if model:
        for row in rows:
            row.update({
                "state": "OBSERVED",
                "authority": "MEASURED",
                "model_id": "integration-model",
            })
        lanes = {"model_proposed": rows}
    else:
        for row in rows:
            row.update({
                "requested_by": "Named pattern maker",
                "provenance": {"actor": "Named pattern maker"},
            })
        lanes = {"requested": rows}
    return {
        "schema": "garment.manufacturing-finish-decision.request.v1",
        "subject_digest": "sha256:integration-approved-garment",
        "seam_topology": {"seams": [{"seam_id": "side-seam"}]},
        "sewing_order": ["join side-seam"],
        **lanes,
    }


def approved_finish_contract() -> tuple[dict, dict]:
    decision = call(FINISH_DECISION, finish_request())
    candidate = decision["candidates"][0]
    approval = call(FINISH_APPROVE, {
        "schema": "garment.manufacturing-finish-approval.request.v1",
        "decision": decision,
        "candidate_digest": candidate["candidate_digest"],
        "approved_by": "Named pattern maker",
        "provenance": {"review_session": "integration-review"},
    })
    return decision, approval


class ContractMCPIntegrationTests(unittest.TestCase):
    maxDiff = None

    def test_tools_are_published_and_capabilities_preserve_truth_boundary(self):
        expected = {
            PHYSICAL_CAPABILITIES, PHYSICAL_ASSESS,
            FINISH_DECISION, FINISH_APPROVE,
        }
        self.assertTrue(expected.issubset(mcp.TOOLS))
        listed = {row["name"] for row in mcp.handle({"method": "tools/list"})["tools"]}
        self.assertTrue(expected.issubset(listed))

        result = call(PHYSICAL_CAPABILITIES)
        self.assertEqual(result["authority"]["model_ceiling"], "PROPOSED")
        self.assertEqual(result["authority"]["simulation_ceiling"], "PROPOSED")
        self.assertFalse(result["reduction"]["averaging_performed"])
        self.assertFalse(result["unobserved_is_imputed"])

    def test_strict_decoder_authorizes_only_complete_non_model_evidence(self):
        result = call(PHYSICAL_ASSESS, real_cloth_claim())
        self.assertEqual(result["verdict"], "CLAIM_AUTHORIZED")
        self.assertEqual(result["claim_authority"], "MEASURED")
        self.assertEqual(result["authorized_claim"]["maximum_error_percent"], 3.0)
        self.assertTrue(result["authorized_claim"]["few_percent_claim"])

        model_claim = copy.deepcopy(real_cloth_claim())
        model_claim["material_properties"][0]["provenance"]["producer_kind"] = "MODEL"
        blocked = call(PHYSICAL_ASSESS, model_claim)
        self.assertEqual(blocked["verdict"], "CLAIM_BLOCKED")
        self.assertFalse(blocked["claim_authorized"])
        property_row = blocked["property_reduction"]["entries"][0]
        self.assertEqual(property_row["evidence"][0]["effective_authority"], "PROPOSED")
        self.assertIn(
            "PROPOSED_MATERIAL_PROPERTY",
            {row["code"] for row in blocked["blocking_reasons"]},
        )

    def test_malformed_physical_input_is_typed_claim_blocked_not_error(self):
        malformed = real_cloth_claim()
        malformed["material_properties"][0]["unexpected"] = "must-not-be-ignored"
        result = call(PHYSICAL_ASSESS, malformed)
        self.assertEqual(result["verdict"], "CLAIM_BLOCKED")
        self.assertNotEqual(result["verdict"], "ERROR")
        self.assertEqual(result["claim_authority"], "NONE")
        self.assertIn("unsupported fields", result["blocking_reasons"][0]["detail"])
        self.assertFalse(result["resolution_request"]["model_may_author_measurements"])

        bad_json = json.loads(mcp.TOOLS[PHYSICAL_ASSESS]("{not-json"))
        self.assertEqual(bad_json["verdict"], "CLAIM_BLOCKED")
        self.assertEqual(bad_json["blocking_reasons"][0]["code"],
                         "UNKNOWN_BAD_ARGUMENTS")

    def test_finish_decision_never_silently_selects_or_promotes_model(self):
        unknown = call(FINISH_DECISION, {
            "subject_digest": "sha256:no-finish-evidence",
            "seam_topology": {"seams": [{"seam_id": "side-seam"}]},
            "sewing_order": ["join side-seam"],
        })
        self.assertEqual(unknown["verdict"], "RESOLUTION_REQUIRED")
        self.assertEqual(unknown["candidates"], [])
        self.assertIsNone(unknown["selected_candidate"])
        self.assertFalse(unknown["automatic_selection_allowed"])

        model = call(FINISH_DECISION, finish_request(model=True))
        self.assertEqual(model["verdict"], "CANDIDATES_READY")
        self.assertIsNone(model["selected_candidate"])
        self.assertTrue(model["evidence_lanes"]["MODEL_PROPOSED"])
        for row in model["evidence_lanes"]["MODEL_PROPOSED"]:
            self.assertEqual(row["state"], "MODEL_PROPOSED")
            self.assertFalse(row["observed"])
            self.assertTrue(row["authority_promotion_refused"])

    def test_finish_approval_is_user_approved_not_observed(self):
        decision, approval = approved_finish_contract()
        self.assertEqual(decision["verdict"], "CANDIDATES_READY")
        self.assertEqual(approval["verdict"], "USER_APPROVED")
        self.assertFalse(approval["observed"])
        self.assertEqual(approval["observation_state"], "UNKNOWN_UNOBSERVED")
        self.assertFalse(approval["manufacturing_certified"])
        self.assertEqual(approval["fact_promotions"], [])

    def test_connection_audit_shows_gates_connected_but_providers_optional(self):
        audit = call("garment_connection_audit")
        components = {row["component"]: row for row in audit["components"]}
        for name in (
            "physical calibration claim gate",
            "manufacturing finish decision gate",
        ):
            self.assertEqual(components[name]["status"], "CONNECTED")
            self.assertFalse(components[name]["tools_missing"])

        limits = {row["limitation_id"]: row for row in audit["known_limitations"]}
        self.assertEqual(
            limits["material-properties-not-measured-from-image"]["status"],
            "HUMAN_RESOLUTION",
        )
        for limitation_id in (
            "seam-finishes-undetermined",
            "real-cloth-error-not-calibrated",
            "wind-tunnel-validation-not-connected",
        ):
            self.assertEqual(limits[limitation_id]["status"], "OPTIONAL_PROVIDER")
        self.assertIn(
            PHYSICAL_ASSESS,
            limits["real-cloth-error-not-calibrated"]["tools_available"],
        )
        self.assertIn(
            FINISH_DECISION,
            limits["seam-finishes-undetermined"]["tools_available"],
        )

    def test_real_stdio_lists_and_calls_contract_tool(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {
                    "name": PHYSICAL_CAPABILITIES,
                    "arguments": {"json_text": "{}"},
                },
            },
        ]
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "-m", "photoloset.mcp"],
            input="".join(json.dumps(row) + "\n" for row in requests),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=root,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        replies = [json.loads(line) for line in completed.stdout.splitlines() if line]
        self.assertEqual([row["id"] for row in replies], [1, 2])
        names = {row["name"] for row in replies[0]["result"]["tools"]}
        self.assertIn(PHYSICAL_CAPABILITIES, names)
        content = replies[1]["result"]["content"][0]
        self.assertEqual(content["type"], "text")
        result = json.loads(content["text"])
        self.assertEqual(result["schema"], "garment.physical-calibration-contract.v1")
        self.assertEqual(result["authority"]["model_ceiling"], "PROPOSED")

    def test_physical_contract_reaches_factory_and_job_without_overclaim(self):
        decision = call(PHYSICAL_ASSESS, real_cloth_claim())

        factory = garment_factory.advance(
            garment_factory.new_job("physical-contract-factory"),
            {
                "type": "SUBMIT_PHYSICAL_CALIBRATION_DECISION",
                "decision": decision,
            },
        )
        self.assertEqual(factory["verdict"], "CONTRACT_ADMITTED")
        admission = factory["contract_admission"]
        self.assertEqual(admission["contract_state"], "OBSERVED")
        self.assertEqual(
            admission["capability_gate"], "REAL_CLOTH_ERROR_GUARANTEE")
        # A scoped laboratory decision is retained, but it is not silently
        # promoted into the wider product guarantee.
        self.assertEqual(
            factory["resolution_request"]["verdict"],
            "UNKNOWN_REAL_CLOTH_ERROR_GUARANTEE",
        )

        job = generation_job.apply(
            generation_job.new_job("physical-contract-job"),
            {
                "kind": "SUBMIT_PHYSICAL_CALIBRATION_DECISION",
                "decision": decision,
            },
        )
        self.assertEqual(
            job["events"][-1]["kind"],
            "AUTHORITATIVE_CONTRACT_ADMITTED",
        )
        self.assertEqual(
            job["resolution_request"]["verdict"],
            "UNKNOWN_REAL_CLOTH_ERROR_GUARANTEE",
        )

    def test_finish_contract_reaches_factory_and_job_as_user_approved(self):
        decision, approval = approved_finish_contract()

        factory = garment_factory.advance(
            garment_factory.new_job("finish-contract-factory"),
            {
                "type": "SUBMIT_MANUFACTURING_FINISH_DECISION",
                "decision": decision,
                "approval": approval,
            },
        )
        self.assertEqual(factory["verdict"], "CONTRACT_ADMITTED")
        admission = factory["contract_admission"]
        self.assertEqual(admission["contract_state"], "USER_APPROVED")
        self.assertEqual(admission["capability_state"], "INFERRED")
        self.assertEqual(
            factory["resolution_request"]["verdict"],
            "UNKNOWN_SEAM_FINISH_CONSTRUCTION",
        )
        self.assertIn(
            "sewing.machine_setup",
            factory["resolution_request"]["missing_fields"],
        )

        job = generation_job.apply(
            generation_job.new_job("finish-contract-job"),
            {
                "kind": "SUBMIT_MANUFACTURING_FINISH_DECISION",
                "decision": decision,
                "approval": approval,
            },
        )
        self.assertEqual(
            job["events"][-1]["kind"],
            "AUTHORITATIVE_CONTRACT_ADMITTED",
        )
        self.assertEqual(
            job["resolution_request"]["verdict"],
            "UNKNOWN_SEAM_FINISH_CONSTRUCTION",
        )


if __name__ == "__main__":
    unittest.main()
