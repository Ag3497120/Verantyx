#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import hashlib
import unittest

from photoloset import reconstruction_claim_contract as contract


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _provenance(label: str) -> contract.ProvenanceRecord:
    return contract.ProvenanceRecord(
        source_id=label,
        source_digest=_sha(label),
        method="adversarial-fixture",
        revision="1",
    )


def _rights(commercial=True) -> contract.RightsRecord:
    return contract.RightsRecord(
        license_id="fixture-license",
        holder="fixture-owner",
        commercial_use=commercial,
        source_uri="fixture://reconstruction-claim",
    )


def _evidence(
    evidence_id="evidence-1",
    *,
    metric="body_dimensions",
    value=None,
    authority=contract.EvidenceAuthority.MEASURED,
    producer=contract.ProducerKind.MEASUREMENT_DEVICE,
    project_id="project-a",
    request_id="request-a",
    commercial=True,
):
    return contract.EvidenceRecord(
        evidence_id=evidence_id,
        metric=metric,
        value=({"height_cm": 170.0, "waist_cm": 72.0}
               if value is None else value),
        authority=authority,
        producer=producer,
        project_id=project_id,
        request_id=request_id,
        provenance=_provenance(evidence_id),
        rights=_rights(commercial),
    )


def _thresholds(reverse=False):
    rows = [
        contract.ValidationThreshold(
            category=contract.SOURCE_VIEW,
            metric="source_view_coverage",
            operator=contract.ThresholdOperator.MINIMUM,
            value=0.95,
            unit="ratio",
            minimum_samples=1,
            approved_by="reviewer",
            provenance=_provenance("threshold-source-view"),
        ),
        contract.ValidationThreshold(
            category=contract.MEASUREMENT,
            metric="dimension_error_mm",
            operator=contract.ThresholdOperator.MAXIMUM,
            value=5.0,
            unit="mm",
            minimum_samples=2,
            approved_by="reviewer",
            provenance=_provenance("threshold-measurement"),
        ),
        contract.ValidationThreshold(
            category=contract.MANUFACTURABILITY,
            metric="sewability_failures",
            operator=contract.ThresholdOperator.EXACT,
            value=0.0,
            unit="count",
            minimum_samples=1,
            approved_by="reviewer",
            provenance=_provenance("threshold-manufacturability"),
        ),
    ]
    if reverse:
        rows.reverse()
    return tuple(rows)


def _validation(item_id="item-1", evidence_ids=("evidence-1",), *,
                commercial=True):
    return contract.ValidationCase(
        case_id="case-%s" % item_id,
        scope_item_id=item_id,
        metrics={
            "source_view_coverage": (0.99,),
            "dimension_error_mm": (2.0, 3.0),
            "sewability_failures": (0.0,),
        },
        evidence_ids=tuple(evidence_ids),
        provenance=_provenance("case-%s" % item_id),
        rights=_rights(commercial),
    )


def _request(
    kind=contract.ClaimKind.EXACT_BODY_MEASUREMENTS,
    *,
    project_id="project-a",
    request_id="request-a",
    evidence=None,
    thresholds=None,
    validations=None,
    scope_items=("item-1",),
    mode=contract.ScopeMode.FINITE_DECLARED,
    commercial_use=True,
):
    rows = (_evidence(project_id=project_id, request_id=request_id),)
    if evidence is not None:
        rows = tuple(evidence)
    cases = (_validation(evidence_ids=tuple(
        item.evidence_id for item in rows)),) if rows else ()
    if validations is not None:
        cases = tuple(validations)
    return contract.ClaimRequest(
        project_id=project_id,
        request_id=request_id,
        claim_kind=kind,
        scope=contract.ClaimScope(mode, tuple(scope_items)),
        evidence=rows,
        thresholds=_thresholds() if thresholds is None else tuple(thresholds),
        validations=cases,
        commercial_use=commercial_use,
    )


class AuthorityBoundaryTests(unittest.TestCase):
    def test_front_image_cannot_silently_become_measured(self):
        row = _evidence(
            authority=contract.EvidenceAuthority.MEASURED,
            producer=contract.ProducerKind.FRONT_IMAGE,
        )
        self.assertEqual(row.authority.value, "MEASURED")
        self.assertEqual(row.effective_authority.value, "OBSERVED")

    def test_reconstruction_and_model_have_proposed_ceiling(self):
        for producer in (contract.ProducerKind.RECONSTRUCTION,
                         contract.ProducerKind.MODEL):
            row = _evidence(
                authority=contract.EvidenceAuthority.MEASURED,
                producer=producer,
            )
            self.assertEqual(row.effective_authority.value,
                             "MODEL_PROPOSED")

    def test_front_only_exact_body_claim_remains_blocked(self):
        row = _evidence(
            authority=contract.EvidenceAuthority.MEASURED,
            producer=contract.ProducerKind.FRONT_IMAGE,
        )
        request = _request(
            evidence=(row,),
            validations=(_validation(evidence_ids=(row.evidence_id,)),),
        )
        decision = contract.assess_claim(request)
        self.assertEqual(decision["status"], contract.RESOLUTION_REQUIRED)
        self.assertIn(
            "BODY_MEASUREMENTS_NOT_MEASURED",
            decision["resolution"]["reason_codes"],
        )

    def test_model_only_validation_does_not_authorize_fidelity(self):
        row = _evidence(
            metric="target_surface",
            authority=contract.EvidenceAuthority.OBSERVED,
            producer=contract.ProducerKind.MODEL,
            commercial=None,
        )
        request = _request(
            contract.ClaimKind.ARBITRARY_GARMENT_FIDELITY,
            evidence=(row,),
            validations=(_validation(
                evidence_ids=(row.evidence_id,), commercial=None),),
        )
        decision = contract.assess_claim(request)
        reasons = decision["resolution"]["reason_codes"]
        self.assertIn("MODEL_ONLY_VALIDATION", reasons)
        self.assertIn("GARMENT_FIDELITY_MODEL_ONLY", reasons)


class ConsentTests(unittest.TestCase):
    def test_consent_is_project_request_and_digest_bound(self):
        request = _request()
        consent = contract.issue_one_shot_consent(
            request, ("rear_shape",), granted_by="human-a")

        other_project = _request(project_id="project-b")
        with self.assertRaisesRegex(ValueError, "PROJECT_MISMATCH"):
            contract.submit_consented_model_proposal(
                other_project, consent, {"rear_shape": "closed"},
                model_id="model-a")

        other_request = _request(request_id="request-b")
        with self.assertRaisesRegex(ValueError, "REQUEST_MISMATCH"):
            contract.submit_consented_model_proposal(
                other_request, consent, {"rear_shape": "closed"},
                model_id="model-a")

    def test_changed_claim_makes_consent_stale(self):
        request = _request()
        consent = contract.issue_one_shot_consent(
            request, ("rear_shape",), granted_by="human-a")
        changed = dataclasses.replace(
            request,
            evidence=request.evidence + (_evidence(
                "evidence-2", metric="rear_shape", value="closed"),),
        )
        with self.assertRaisesRegex(ValueError, "STALE_CLAIM_DIGEST"):
            contract.submit_consented_model_proposal(
                changed, consent, {"rear_shape": "closed"},
                model_id="model-a")

    def test_one_shot_consent_is_consumed_and_never_promotes(self):
        request = _request(commercial_use=False)
        consent = contract.issue_one_shot_consent(
            request, ("body_dimensions",), granted_by="human-a")
        rows = contract.submit_consented_model_proposal(
            request, consent,
            {"body_dimensions": {
                "authority": "MEASURED", "height_cm": 170.0}},
            model_id="model-a",
        )
        self.assertEqual(rows[0].authority.value, "MODEL_PROPOSED")
        self.assertEqual(rows[0].effective_authority.value,
                         "MODEL_PROPOSED")
        with self.assertRaisesRegex(ValueError, "ALREADY_USED"):
            contract.submit_consented_model_proposal(
                request, consent,
                {"body_dimensions": {"height_cm": 171.0}},
                model_id="model-a",
            )

    def test_consent_rejects_unlisted_field(self):
        request = _request()
        consent = contract.issue_one_shot_consent(
            request, ("rear_shape",), granted_by="human-a")
        with self.assertRaisesRegex(ValueError, "FIELD_MISMATCH"):
            contract.submit_consented_model_proposal(
                request, consent, {"material": "wool"},
                model_id="model-a")


class ThresholdAndRightsTests(unittest.TestCase):
    def test_all_three_threshold_categories_are_mandatory(self):
        thresholds = tuple(
            item for item in _thresholds()
            if item.category != contract.MANUFACTURABILITY)
        decision = contract.assess_claim(_request(thresholds=thresholds))
        self.assertEqual(decision["status"], contract.RESOLUTION_REQUIRED)
        self.assertIn(
            "MISSING_MANUFACTURABILITY_THRESHOLD",
            decision["resolution"]["reason_codes"],
        )

    def test_validation_must_pass_each_explicit_threshold(self):
        row = _evidence()
        failed = dataclasses.replace(
            _validation(evidence_ids=(row.evidence_id,)),
            metrics={
                "source_view_coverage": (0.80,),
                "dimension_error_mm": (2.0, 3.0),
                "sewability_failures": (0.0,),
            },
        )
        decision = contract.assess_claim(_request(
            evidence=(row,), validations=(failed,)))
        self.assertIn(
            "THRESHOLD_FAILED:source_view_coverage",
            decision["resolution"]["reason_codes"],
        )

    def test_commercial_rights_are_fail_closed(self):
        row = _evidence(
            authority=contract.EvidenceAuthority.PROVIDER_SUPPORTED,
            producer=contract.ProducerKind.PROVIDER,
            commercial=None,
        )
        case = _validation(evidence_ids=(row.evidence_id,), commercial=None)
        decision = contract.assess_claim(_request(
            evidence=(row,), validations=(case,)))
        self.assertIn(
            "COMMERCIAL_RIGHTS_UNKNOWN_OR_DENIED",
            decision["resolution"]["reason_codes"],
        )
        self.assertEqual(
            decision["resolution"]["recommended_route"],
            contract.CONNECT_PROVIDER,
        )


class ScopeAndGuaranteeTests(unittest.TestCase):
    def test_universal_any_image_claim_is_an_explicit_typed_stop(self):
        request = _request(
            contract.ClaimKind.UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN,
            mode=contract.ScopeMode.UNIVERSAL_ANY_IMAGE,
            scope_items=(),
        )
        decision = contract.assess_claim(request)
        self.assertEqual(decision["status"],
                         contract.UNSUPPORTED_TYPED_STOP)
        self.assertEqual(
            decision["typed_stop"]["code"],
            "UNSUPPORTED_ANY_IMAGE_ALWAYS_SUCCEEDS",
        )
        self.assertEqual(
            tuple(item["kind"] for item in decision["resolution"]["routes"]),
            contract.ACTIONABLE_ROUTES,
        )

    def test_finite_body_claim_can_be_authorized_without_universal_language(self):
        decision = contract.assess_claim(_request())
        self.assertEqual(decision["status"],
                         contract.CLAIM_AUTHORIZED_SCOPED)
        claim = decision["authorized_claim"]
        self.assertEqual(claim["scope_item_ids"], ["item-1"])
        self.assertIn("ANY_IMAGE_ALWAYS_SUCCEEDS",
                      claim["does_not_authorize"])

    def test_finite_complex_garment_fidelity_can_be_validated(self):
        row = _evidence(
            metric="approved_target_surface",
            value={"layers": 4, "frills": 2, "pleats": 18},
            authority=contract.EvidenceAuthority.OBSERVED,
            producer=contract.ProducerKind.HUMAN,
        )
        decision = contract.assess_claim(_request(
            contract.ClaimKind.ARBITRARY_GARMENT_FIDELITY,
            evidence=(row,),
            validations=(_validation(evidence_ids=(row.evidence_id,)),),
        ))
        self.assertEqual(decision["status"],
                         contract.CLAIM_AUTHORIZED_SCOPED)
        self.assertIn("OUT_OF_SCOPE_GARMENTS",
                      decision["authorized_claim"]["does_not_authorize"])

    def test_finite_sewable_pattern_claim_needs_complete_validation(self):
        row = _evidence(
            metric="physical_toile_review",
            value={"sewability_failures": 0},
            authority=contract.EvidenceAuthority.PROVIDER_SUPPORTED,
            producer=contract.ProducerKind.PROVIDER,
        )
        missing = contract.assess_claim(_request(
            contract.ClaimKind.UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN,
            evidence=(row,), validations=(),
            scope_items=("garment-a", "garment-b"),
        ))
        self.assertIn("INCOMPLETE_FINITE_VALIDATION_SET",
                      missing["resolution"]["reason_codes"])

        complete = contract.assess_claim(_request(
            contract.ClaimKind.UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN,
            evidence=(row,),
            validations=(
                _validation("garment-a", (row.evidence_id,)),
                _validation("garment-b", (row.evidence_id,)),
            ),
            scope_items=("garment-a", "garment-b"),
        ))
        self.assertEqual(complete["status"],
                         contract.CLAIM_AUTHORIZED_SCOPED)
        self.assertIn("ANY_IMAGE_ALWAYS_SUCCEEDS",
                      complete["authorized_claim"]["does_not_authorize"])


class ConflictAndDeterminismTests(unittest.TestCase):
    def test_conflicting_hypotheses_are_preserved_not_averaged(self):
        first = _evidence("evidence-1", value={"waist_cm": 72.0})
        second = _evidence("evidence-2", value={"waist_cm": 75.0})
        decision = contract.assess_claim(_request(
            evidence=(first, second),
            validations=(_validation(
                evidence_ids=(first.evidence_id, second.evidence_id)),),
        ))
        self.assertEqual(len(decision["conflicts"]), 1)
        conflict = decision["conflicts"][0]
        self.assertEqual(conflict["state"], "CONTESTED")
        self.assertEqual(conflict["reduction"], "PRESERVE_NO_AVERAGING")
        self.assertEqual(len(conflict["hypotheses"]), 2)

    def test_digest_is_independent_of_input_order(self):
        first = _evidence("evidence-1", value={"waist_cm": 72.0})
        second = _evidence("evidence-2", value={"waist_cm": 72.0})
        case_a = _validation("item-a", (first.evidence_id,))
        case_b = _validation("item-b", (second.evidence_id,))
        forward = _request(
            evidence=(first, second),
            thresholds=_thresholds(),
            validations=(case_a, case_b),
            scope_items=("item-a", "item-b"),
        )
        reverse = _request(
            evidence=(second, first),
            thresholds=_thresholds(reverse=True),
            validations=(case_b, case_a),
            scope_items=("item-b", "item-a"),
        )
        self.assertEqual(forward.claim_digest, reverse.claim_digest)
        self.assertEqual(
            contract.assess_claim(forward)["decision_digest"],
            contract.assess_claim(reverse)["decision_digest"],
        )

    def test_capability_statement_is_deterministic_and_truthful(self):
        first = contract.capabilities()
        second = contract.capabilities()
        self.assertEqual(first, second)
        self.assertFalse(first["universal_guarantee_supported"])
        self.assertTrue(first["finite_scope_validation_supported"])


if __name__ == "__main__":
    unittest.main()
