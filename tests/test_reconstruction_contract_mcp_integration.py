#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from photoloset import reconstruction_claim_contract as contract
from photoloset import reconstruction_contract_adapter as adapter
from photoloset import mcp
from photoloset import garment_factory, generation_job


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def provenance(label: str) -> dict:
    return {
        "source_id": label,
        "source_digest": digest(label),
        "method": "adapter-integration-fixture",
        "revision": "1",
    }


def rights() -> dict:
    return {
        "license_id": "adapter-fixture-license",
        "holder": "adapter-fixture-owner",
        "commercial_use": True,
        "source_uri": "fixture://reconstruction-adapter",
    }


def thresholds() -> list[dict]:
    return [
        {
            "category": "SOURCE_VIEW",
            "metric": "source_view_coverage",
            "operator": "MINIMUM",
            "value": 0.95,
            "unit": "ratio",
            "minimum_samples": 1,
            "approved_by": "Named reviewer",
            "provenance": provenance("threshold-source-view"),
        },
        {
            "category": "MEASUREMENT",
            "metric": "dimension_error_mm",
            "operator": "MAXIMUM",
            "value": 5.0,
            "unit": "mm",
            "minimum_samples": 2,
            "approved_by": "Named reviewer",
            "provenance": provenance("threshold-measurement"),
        },
        {
            "category": "MANUFACTURABILITY",
            "metric": "sewability_failures",
            "operator": "EXACT",
            "value": 0.0,
            "unit": "count",
            "minimum_samples": 1,
            "approved_by": "Named reviewer",
            "provenance": provenance("threshold-manufacturability"),
        },
    ]


def evidence(
    *,
    metric: str = "body_dimensions",
    authority: str = "MEASURED",
    producer: str = "MEASUREMENT_DEVICE",
    value=None,
) -> dict:
    return {
        "evidence_id": "evidence-1",
        "metric": metric,
        "value": (
            {"height_cm": 170.0, "waist_cm": 72.0}
            if value is None else value
        ),
        "authority": authority,
        "producer": producer,
        "project_id": "project-a",
        "request_id": "request-a",
        "provenance": provenance("evidence-1"),
        "rights": rights(),
    }


def validation(evidence_id: str = "evidence-1") -> dict:
    return {
        "case_id": "case-item-1",
        "scope_item_id": "item-1",
        "metrics": {
            "source_view_coverage": [0.99],
            "dimension_error_mm": [2.0, 3.0],
            "sewability_failures": [0.0],
        },
        "evidence_ids": [evidence_id],
        "provenance": provenance("case-item-1"),
        "rights": rights(),
    }


def request(
    claim_kind: str = "EXACT_BODY_MEASUREMENTS",
    *,
    evidence_row: dict | None = None,
    scope_mode: str = "FINITE_DECLARED",
    item_ids: list[str] | None = None,
) -> dict:
    row = evidence_row or evidence()
    return {
        "schema": contract.SCHEMA,
        "project_id": "project-a",
        "request_id": "request-a",
        "claim_kind": claim_kind,
        "scope": {
            "mode": scope_mode,
            "item_ids": ["item-1"] if item_ids is None else item_ids,
        },
        "evidence": [row],
        "thresholds": thresholds(),
        "validations": [validation(row["evidence_id"])],
        "commercial_use": True,
    }


def assess(payload: dict) -> dict:
    return adapter.assess(json.dumps(payload, ensure_ascii=False))


class ReconstructionContractAdapterIntegrationTests(unittest.TestCase):
    maxDiff = None

    def test_capabilities_are_deterministic_and_mcp_ready(self):
        first = adapter.capabilities("{}")
        second = adapter.capabilities("")
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], contract.SCHEMA)
        self.assertFalse(first["universal_guarantee_supported"])
        self.assertEqual(first["conflict_policy"], "PRESERVE_NO_AVERAGING")

    def test_exact_body_measurements_decode_and_authorize_finite_scope(self):
        result = assess(request())
        self.assertEqual(result["status"], contract.CLAIM_AUTHORIZED_SCOPED)
        self.assertEqual(result["claim_kind"], "EXACT_BODY_MEASUREMENTS")
        self.assertEqual(result["hypotheses"][0]["effective_authority"],
                         "MEASURED")
        self.assertEqual(result["authorized_claim"]["scope_item_ids"],
                         ["item-1"])

    def test_arbitrary_garment_fidelity_accepts_human_observed_target(self):
        row = evidence(
            metric="approved_target_surface",
            authority="OBSERVED",
            producer="HUMAN",
            value={"layers": 4, "frills": 2, "pleats": 18},
        )
        result = assess(request(
            "ARBITRARY_GARMENT_FIDELITY", evidence_row=row))
        self.assertEqual(result["status"], contract.CLAIM_AUTHORIZED_SCOPED)
        self.assertIn(
            "OUT_OF_SCOPE_GARMENTS",
            result["authorized_claim"]["does_not_authorize"],
        )

    def test_universal_automatic_pattern_is_a_typed_stop(self):
        row = evidence(
            metric="physical_toile_review",
            authority="PROVIDER_SUPPORTED",
            producer="PROVIDER",
            value={"sewability_failures": 0},
        )
        result = assess(request(
            "UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN",
            evidence_row=row,
            scope_mode="UNIVERSAL_ANY_IMAGE",
            item_ids=[],
        ))
        self.assertEqual(result["status"], contract.UNSUPPORTED_TYPED_STOP)
        self.assertEqual(
            result["typed_stop"]["code"],
            "UNSUPPORTED_ANY_IMAGE_ALWAYS_SUCCEEDS",
        )
        self.assertIsNone(result["authorized_claim"])

    def test_missing_extra_and_malformed_authority_are_typed_unknown(self):
        cases = []

        missing = request()
        del missing["evidence"][0]["provenance"]
        cases.append((missing, "UNKNOWN_BAD_ARGUMENTS"))

        extra = request()
        extra["evidence"][0]["invented_authority"] = "MEASURED"
        cases.append((extra, "UNKNOWN_BAD_ARGUMENTS"))

        malformed = request()
        malformed["evidence"][0]["authority"] = "CERTAINLY_TRUE"
        cases.append((malformed, "UNKNOWN_AUTHORITY_OR_ENUM_VALUE"))

        for payload, code in cases:
            with self.subTest(code=code):
                result = assess(payload)
                self.assertEqual(result["status"],
                                 contract.RESOLUTION_REQUIRED)
                self.assertEqual(result["typed_unknown"]["code"], code)
                self.assertIsNone(result["authorized_claim"])

    def test_malformed_provenance_digest_is_typed_unknown(self):
        payload = request()
        payload["evidence"][0]["provenance"]["source_digest"] = "not-sha256"
        result = assess(payload)
        self.assertEqual(result["status"], contract.RESOLUTION_REQUIRED)
        self.assertEqual(
            result["typed_unknown"]["code"],
            "UNKNOWN_MALFORMED_PROVENANCE",
        )
        self.assertIn("SHA-256", result["typed_unknown"]["why"])

    def test_model_or_reconstruction_evidence_is_never_promoted(self):
        for producer in ("MODEL", "RECONSTRUCTION"):
            with self.subTest(producer=producer):
                row = evidence(
                    authority="MEASURED",
                    producer=producer,
                )
                result = assess(request(evidence_row=row))
                self.assertEqual(result["status"],
                                 contract.RESOLUTION_REQUIRED)
                self.assertEqual(
                    result["typed_unknown"]["code"],
                    adapter.UNKNOWN_MODEL_ONLY_EVIDENCE,
                )
                self.assertEqual(result["hypotheses"][0]["authority"],
                                 "MEASURED")
                self.assertEqual(
                    result["hypotheses"][0]["effective_authority"],
                    "MODEL_PROPOSED",
                )
                self.assertIsNone(result["authorized_claim"])

    def test_decoder_does_not_fill_missing_outer_or_nested_values(self):
        for path in (
            ("commercial_use",),
            ("evidence", 0, "project_id"),
            ("validations", 0, "rights"),
        ):
            payload = copy.deepcopy(request())
            target = payload
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
            with self.subTest(path=path):
                result = assess(payload)
                self.assertEqual(result["status"],
                                 contract.RESOLUTION_REQUIRED)
                self.assertEqual(result["typed_unknown"]["code"],
                                 "UNKNOWN_BAD_ARGUMENTS")

    def test_public_mcp_tools_use_the_same_strict_boundary(self):
        capabilities = json.loads(mcp.TOOLS[
            "garment_reconstruction_claim_capabilities"
        ]("{}"))
        self.assertEqual(contract.SCHEMA, capabilities["schema"])
        self.assertFalse(capabilities["universal_guarantee_supported"])

        decision = json.loads(mcp.TOOLS[
            "garment_reconstruction_claim_assess"
        ](json.dumps(request(), ensure_ascii=False)))
        self.assertEqual(contract.CLAIM_AUTHORIZED_SCOPED,
                         decision["status"])
        self.assertEqual("MEASURED",
                         decision["hypotheses"][0]["effective_authority"])

        audit = json.loads(mcp.TOOLS["garment_connection_audit"](
            '{"component":"finite reconstruction claim gate"}'))
        self.assertEqual(1, len(audit["components"]))
        self.assertEqual(mcp.CONNECTED, audit["components"][0]["status"])
        self.assertEqual(
            ["SUBMIT_RECONSTRUCTION_CLAIM_DECISION"],
            audit["components"][0]["factory_events"],
        )

    def test_authorized_decision_reaches_both_orchestration_boundaries(self):
        decision = json.loads(mcp.TOOLS[
            "garment_reconstruction_claim_assess"
        ](json.dumps(request(), ensure_ascii=False)))

        factory = garment_factory.advance(
            garment_factory.new_job("reconstruction-contract-factory"),
            {
                "type": "SUBMIT_RECONSTRUCTION_CLAIM_DECISION",
                "decision": decision,
            },
        )
        self.assertEqual("CONTRACT_ADMITTED", factory["verdict"])
        self.assertEqual(
            "BODY_DIMENSIONS_FROM_IMAGE",
            factory["contract_admission"]["capability_gate"],
        )
        # The fixture measures height and waist only.  The contract is kept,
        # while the wider exact-body gate correctly remains unresolved.
        self.assertEqual(
            "UNKNOWN_BODY_DIMENSIONS_NOT_MEASURED_FROM_IMAGE",
            factory["resolution_request"]["verdict"],
        )

        job = generation_job.apply(
            generation_job.new_job("reconstruction-contract-job"),
            {
                "kind": "SUBMIT_RECONSTRUCTION_CLAIM_DECISION",
                "decision": decision,
            },
        )
        self.assertEqual(
            "AUTHORITATIVE_CONTRACT_ADMITTED",
            job["events"][-1]["kind"],
        )
        self.assertEqual(
            "UNKNOWN_BODY_DIMENSIONS_NOT_MEASURED_FROM_IMAGE",
            job["resolution_request"]["verdict"],
        )


if __name__ == "__main__":
    unittest.main()
