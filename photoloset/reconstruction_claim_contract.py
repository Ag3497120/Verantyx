# -*- coding: utf-8 -*-
"""Bounded claim contract for garment reconstruction and guarantees.

This module does not reconstruct a hidden back, measure a body from pixels, or
promise that every image can become a sewable pattern.  It controls the much
narrower boundary between evidence and a product claim.

Three claims are covered:

* exact body measurements;
* fidelity for layered, frilled, pleated, or otherwise unusual garments; and
* automatic production of a sewable pattern.

Every claim needs explicit source-view, measurement, and manufacturability
thresholds.  A universal "any image always succeeds" claim is never emitted.
It can only be replaced by a separately named, finite-scope validation claim
when every declared item has a complete validation case.

Direct observations, measurements, rights-cleared provider records, and model
proposals remain separate.  Front images, reconstructions, and language or
vision models have an authority ceiling below ``MEASURED``.  Disagreement is
preserved as a typed conflict instead of being averaged.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


SCHEMA = "garment.reconstruction-claim-contract.v1"
DECISION_SCHEMA = "garment.reconstruction-claim-decision.v1"
CONSENT_SCHEMA = "garment.reconstruction-one-shot-consent.v1"
RESOLUTION_SCHEMA = "garment.reconstruction-resolution.v1"

CLAIM_AUTHORIZED_SCOPED = "CLAIM_AUTHORIZED_SCOPED"
RESOLUTION_REQUIRED = "RESOLUTION_REQUIRED"
UNSUPPORTED_TYPED_STOP = "UNSUPPORTED_TYPED_STOP"

HUMAN_MEASURE = "HUMAN_MEASURE"
EDIT_TARGET_GEOMETRY = "EDIT_TARGET_GEOMETRY"
CONNECT_PROVIDER = "CONNECT_PROVIDER"
CONSENTED_LLM_PROPOSAL = "CONSENTED_LLM_PROPOSAL"
BOUNDED_ALTERNATIVES = "BOUNDED_ALTERNATIVES"
TYPED_STOP = "TYPED_STOP"
ACTIONABLE_ROUTES = (
    HUMAN_MEASURE,
    EDIT_TARGET_GEOMETRY,
    CONNECT_PROVIDER,
    CONSENTED_LLM_PROPOSAL,
    BOUNDED_ALTERNATIVES,
    TYPED_STOP,
)

SOURCE_VIEW = "SOURCE_VIEW"
MEASUREMENT = "MEASUREMENT"
MANUFACTURABILITY = "MANUFACTURABILITY"
REQUIRED_THRESHOLD_CATEGORIES = (
    SOURCE_VIEW, MEASUREMENT, MANUFACTURABILITY,
)


class ClaimKind(str, Enum):
    EXACT_BODY_MEASUREMENTS = "EXACT_BODY_MEASUREMENTS"
    ARBITRARY_GARMENT_FIDELITY = "ARBITRARY_GARMENT_FIDELITY"
    UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN = (
        "UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN"
    )


class EvidenceAuthority(str, Enum):
    OBSERVED = "OBSERVED"
    MEASURED = "MEASURED"
    PROVIDER_SUPPORTED = "PROVIDER_SUPPORTED"
    MODEL_PROPOSED = "MODEL_PROPOSED"


class ProducerKind(str, Enum):
    HUMAN = "HUMAN"
    MEASUREMENT_DEVICE = "MEASUREMENT_DEVICE"
    PROVIDER = "PROVIDER"
    FRONT_IMAGE = "FRONT_IMAGE"
    RECONSTRUCTION = "RECONSTRUCTION"
    MODEL = "MODEL"


class ScopeMode(str, Enum):
    UNIVERSAL_ANY_IMAGE = "UNIVERSAL_ANY_IMAGE"
    FINITE_DECLARED = "FINITE_DECLARED"


class ThresholdOperator(str, Enum):
    MINIMUM = "MINIMUM"
    MAXIMUM = "MAXIMUM"
    EXACT = "EXACT"


_MODEL_LIKE_PRODUCERS = frozenset({
    ProducerKind.RECONSTRUCTION,
    ProducerKind.MODEL,
})
_NON_MEASURING_PRODUCERS = frozenset({
    ProducerKind.FRONT_IMAGE,
    ProducerKind.RECONSTRUCTION,
    ProducerKind.MODEL,
})
_AUTHORITATIVE_VALIDATION = frozenset({
    EvidenceAuthority.OBSERVED,
    EvidenceAuthority.MEASURED,
    EvidenceAuthority.PROVIDER_SUPPORTED,
})


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % name)
    return value.strip()


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be numeric" % name)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % name)
    return result


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef"
                for character in value.lower())
    )


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return {
            item.name: _canonical(getattr(value, item.name))
            for item in dataclasses.fields(value)
            if item.name != "used"
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(child)
            for key, child in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(child) for child in value]
    if isinstance(value, (set, frozenset)):
        rows = [_canonical(child) for child in value]
        return sorted(rows, key=lambda child: json.dumps(
            child, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON cannot contain non-finite values")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return copy.deepcopy(value)
    raise TypeError("unsupported canonical value: %s" % type(value).__name__)


def stable_digest(value: Any) -> str:
    payload = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RightsRecord:
    """Commercial-use authority.  ``None`` deliberately means unknown."""

    license_id: str
    holder: str
    commercial_use: Optional[bool]
    source_uri: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "license_id", _text(
            self.license_id, "rights.license_id"))
        object.__setattr__(self, "holder", _text(
            self.holder, "rights.holder"))
        if self.commercial_use not in (True, False, None):
            raise ValueError("rights.commercial_use must be true, false, or null")
        if self.source_uri and not isinstance(self.source_uri, str):
            raise ValueError("rights.source_uri must be a string")


@dataclass(frozen=True)
class ProvenanceRecord:
    source_id: str
    source_digest: str
    method: str
    revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(
            self.source_id, "provenance.source_id"))
        if not _is_sha256(self.source_digest):
            raise ValueError("provenance.source_digest must be SHA-256")
        object.__setattr__(self, "source_digest", self.source_digest.lower())
        object.__setattr__(self, "method", _text(
            self.method, "provenance.method"))
        object.__setattr__(self, "revision", _text(
            self.revision, "provenance.revision"))


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    metric: str
    value: Any
    authority: EvidenceAuthority
    producer: ProducerKind
    project_id: str
    request_id: str
    provenance: ProvenanceRecord
    rights: RightsRecord

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text(
            self.evidence_id, "evidence.evidence_id"))
        object.__setattr__(self, "metric", _text(
            self.metric, "evidence.metric"))
        object.__setattr__(self, "project_id", _text(
            self.project_id, "evidence.project_id"))
        object.__setattr__(self, "request_id", _text(
            self.request_id, "evidence.request_id"))
        if not isinstance(self.authority, EvidenceAuthority):
            object.__setattr__(self, "authority",
                               EvidenceAuthority(self.authority))
        if not isinstance(self.producer, ProducerKind):
            object.__setattr__(self, "producer", ProducerKind(self.producer))
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("evidence.provenance must be a ProvenanceRecord")
        if not isinstance(self.rights, RightsRecord):
            raise ValueError("evidence.rights must be a RightsRecord")
        _canonical(self.value)

    @property
    def effective_authority(self) -> EvidenceAuthority:
        """Apply producer ceilings without rewriting the submitted record."""
        if self.producer in _MODEL_LIKE_PRODUCERS:
            return EvidenceAuthority.MODEL_PROPOSED
        if self.producer == ProducerKind.FRONT_IMAGE:
            if self.authority == EvidenceAuthority.MODEL_PROPOSED:
                return self.authority
            return EvidenceAuthority.OBSERVED
        if self.producer == ProducerKind.PROVIDER:
            if self.authority == EvidenceAuthority.PROVIDER_SUPPORTED:
                return self.authority
            return EvidenceAuthority.MODEL_PROPOSED
        if self.producer == ProducerKind.MEASUREMENT_DEVICE:
            if self.authority == EvidenceAuthority.MEASURED:
                return self.authority
            return EvidenceAuthority.MODEL_PROPOSED
        return self.authority

    @property
    def evidence_digest(self) -> str:
        return stable_digest(self)

    def to_dict(self) -> Dict[str, Any]:
        row = _canonical(self)
        row["effective_authority"] = self.effective_authority.value
        row["evidence_digest"] = self.evidence_digest
        return row


@dataclass(frozen=True)
class ValidationThreshold:
    category: str
    metric: str
    operator: ThresholdOperator
    value: float
    unit: str
    minimum_samples: int
    approved_by: str
    provenance: ProvenanceRecord

    def __post_init__(self) -> None:
        category = _text(self.category, "threshold.category").upper()
        if category not in REQUIRED_THRESHOLD_CATEGORIES:
            raise ValueError("unsupported threshold category: %s" % category)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "metric", _text(
            self.metric, "threshold.metric"))
        if not isinstance(self.operator, ThresholdOperator):
            object.__setattr__(self, "operator",
                               ThresholdOperator(self.operator))
        object.__setattr__(self, "value", _finite(
            self.value, "threshold.value"))
        object.__setattr__(self, "unit", _text(
            self.unit, "threshold.unit"))
        if isinstance(self.minimum_samples, bool) or self.minimum_samples < 1:
            raise ValueError("threshold.minimum_samples must be a positive integer")
        object.__setattr__(self, "approved_by", _text(
            self.approved_by, "threshold.approved_by"))
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("threshold.provenance must be a ProvenanceRecord")

    def passes(self, candidate: float) -> bool:
        value = _finite(candidate, "validation metric")
        if self.operator == ThresholdOperator.MINIMUM:
            return value >= self.value
        if self.operator == ThresholdOperator.MAXIMUM:
            return value <= self.value
        return value == self.value


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    scope_item_id: str
    metrics: Mapping[str, Sequence[float]]
    evidence_ids: Tuple[str, ...]
    provenance: ProvenanceRecord
    rights: RightsRecord

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _text(
            self.case_id, "validation.case_id"))
        object.__setattr__(self, "scope_item_id", _text(
            self.scope_item_id, "validation.scope_item_id"))
        if not isinstance(self.metrics, Mapping):
            raise ValueError("validation.metrics must be a mapping")
        normalised: Dict[str, Tuple[float, ...]] = {}
        for metric, values in self.metrics.items():
            name = _text(metric, "validation.metric")
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise ValueError("validation metric values must be a sequence")
            numbers = tuple(_finite(value, "validation.%s" % name)
                            for value in values)
            if not numbers:
                raise ValueError("validation metric values must not be empty")
            normalised[name] = numbers
        object.__setattr__(self, "metrics", normalised)
        object.__setattr__(self, "evidence_ids", tuple(sorted({
            _text(value, "validation.evidence_id")
            for value in self.evidence_ids
        })))
        if not self.evidence_ids:
            raise ValueError("validation.evidence_ids must not be empty")
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("validation.provenance must be a ProvenanceRecord")
        if not isinstance(self.rights, RightsRecord):
            raise ValueError("validation.rights must be a RightsRecord")


@dataclass(frozen=True)
class ClaimScope:
    mode: ScopeMode
    item_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ScopeMode):
            object.__setattr__(self, "mode", ScopeMode(self.mode))
        items = tuple(sorted({_text(item, "scope.item_id")
                              for item in self.item_ids}))
        object.__setattr__(self, "item_ids", items)
        if self.mode == ScopeMode.FINITE_DECLARED and not items:
            raise ValueError("finite scope needs at least one declared item")
        if self.mode == ScopeMode.UNIVERSAL_ANY_IMAGE and items:
            raise ValueError("universal scope cannot declare a finite item list")


@dataclass(frozen=True)
class ClaimRequest:
    project_id: str
    request_id: str
    claim_kind: ClaimKind
    scope: ClaimScope
    evidence: Tuple[EvidenceRecord, ...]
    thresholds: Tuple[ValidationThreshold, ...]
    validations: Tuple[ValidationCase, ...]
    commercial_use: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _text(
            self.project_id, "claim.project_id"))
        object.__setattr__(self, "request_id", _text(
            self.request_id, "claim.request_id"))
        if not isinstance(self.claim_kind, ClaimKind):
            object.__setattr__(self, "claim_kind", ClaimKind(self.claim_kind))
        if not isinstance(self.scope, ClaimScope):
            raise ValueError("claim.scope must be a ClaimScope")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "thresholds", tuple(self.thresholds))
        object.__setattr__(self, "validations", tuple(self.validations))
        for item in self.evidence:
            if not isinstance(item, EvidenceRecord):
                raise ValueError("claim evidence must contain EvidenceRecord values")
        for item in self.thresholds:
            if not isinstance(item, ValidationThreshold):
                raise ValueError("claim thresholds must contain ValidationThreshold values")
        for item in self.validations:
            if not isinstance(item, ValidationCase):
                raise ValueError("claim validations must contain ValidationCase values")
        if not isinstance(self.commercial_use, bool):
            raise ValueError("claim.commercial_use must be boolean")

    @property
    def claim_digest(self) -> str:
        """Order-independent digest of the exact claim under review."""
        return stable_digest({
            "schema": SCHEMA,
            "project_id": self.project_id,
            "request_id": self.request_id,
            "claim_kind": self.claim_kind,
            "scope": self.scope,
            "evidence": sorted(
                (item.to_dict() for item in self.evidence),
                key=lambda row: row["evidence_digest"]),
            "thresholds": sorted(
                (_canonical(item) for item in self.thresholds),
                key=stable_digest),
            "validations": sorted(
                (_canonical(item) for item in self.validations),
                key=stable_digest),
            "commercial_use": self.commercial_use,
        })


@dataclass
class OneShotConsent:
    project_id: str
    request_id: str
    claim_digest: str
    fields: Tuple[str, ...]
    granted_by: str
    used: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.project_id = _text(self.project_id, "consent.project_id")
        self.request_id = _text(self.request_id, "consent.request_id")
        if not _is_sha256(self.claim_digest):
            raise ValueError("consent.claim_digest must be SHA-256")
        self.claim_digest = self.claim_digest.lower()
        self.fields = tuple(sorted({_text(item, "consent.field")
                                    for item in self.fields}))
        if not self.fields:
            raise ValueError("consent.fields must not be empty")
        self.granted_by = _text(self.granted_by, "consent.granted_by")

    @property
    def consent_digest(self) -> str:
        return stable_digest({
            "schema": CONSENT_SCHEMA,
            "project_id": self.project_id,
            "request_id": self.request_id,
            "claim_digest": self.claim_digest,
            "fields": self.fields,
            "granted_by": self.granted_by,
        })


def issue_one_shot_consent(
    request: ClaimRequest, fields: Sequence[str], *, granted_by: str,
) -> OneShotConsent:
    return OneShotConsent(
        project_id=request.project_id,
        request_id=request.request_id,
        claim_digest=request.claim_digest,
        fields=tuple(fields),
        granted_by=granted_by,
    )


def submit_consented_model_proposal(
    request: ClaimRequest,
    consent: OneShotConsent,
    values: Mapping[str, Any],
    *,
    model_id: str,
) -> Tuple[EvidenceRecord, ...]:
    """Consume exact consent and return proposals with a fixed authority ceiling."""
    if not isinstance(consent, OneShotConsent):
        raise ValueError("a OneShotConsent is required")
    if consent.used:
        raise ValueError("CONSENT_ALREADY_USED")
    if consent.project_id != request.project_id:
        raise ValueError("CONSENT_PROJECT_MISMATCH")
    if consent.request_id != request.request_id:
        raise ValueError("CONSENT_REQUEST_MISMATCH")
    if consent.claim_digest != request.claim_digest:
        raise ValueError("CONSENT_STALE_CLAIM_DIGEST")
    if not isinstance(values, Mapping) or not values:
        raise ValueError("model proposal values must be a non-empty mapping")
    unknown = sorted(set(values) - set(consent.fields))
    if unknown:
        raise ValueError("CONSENT_FIELD_MISMATCH: " + ", ".join(unknown))
    model = _text(model_id, "model_id")
    consent.used = True
    rights = RightsRecord(
        license_id="model-output-unverified-rights",
        holder=model,
        commercial_use=None,
        source_uri="model://%s" % model,
    )
    rows = []
    for name in sorted(values):
        payload = _canonical(values[name])
        source_digest = stable_digest({
            "consent_digest": consent.consent_digest,
            "metric": name,
            "value": payload,
            "model_id": model,
        })
        rows.append(EvidenceRecord(
            evidence_id="proposal-%s-%s" % (
                name, source_digest[:12]),
            metric=name,
            value=payload,
            authority=EvidenceAuthority.MODEL_PROPOSED,
            producer=ProducerKind.MODEL,
            project_id=request.project_id,
            request_id=request.request_id,
            provenance=ProvenanceRecord(
                source_id=model,
                source_digest=source_digest,
                method="CONSENTED_MODEL_PROPOSAL",
                revision=consent.consent_digest,
            ),
            rights=rights,
        ))
    return tuple(rows)


def _resolution(reason_codes: Sequence[str], *, recommended: str) -> Dict[str, Any]:
    return {
        "schema": RESOLUTION_SCHEMA,
        "reason_codes": sorted(set(reason_codes)),
        "recommended_route": recommended,
        "routes": [
            {
                "kind": route,
                "does_not_promote_model_output": True,
            }
            for route in ACTIONABLE_ROUTES
        ],
    }


def _conflicts(evidence: Sequence[EvidenceRecord]) -> Tuple[Dict[str, Any], ...]:
    by_metric: Dict[str, list] = {}
    for item in evidence:
        by_metric.setdefault(item.metric, []).append(item)
    conflicts = []
    for metric in sorted(by_metric):
        rows = sorted(by_metric[metric], key=lambda item: item.evidence_digest)
        values: Dict[str, Dict[str, Any]] = {}
        for item in rows:
            key = stable_digest(item.value)
            values.setdefault(key, {
                "value": _canonical(item.value),
                "evidence_ids": [],
                "authorities": [],
            })
            values[key]["evidence_ids"].append(item.evidence_id)
            values[key]["authorities"].append(item.effective_authority.value)
        if len(values) > 1:
            hypotheses = []
            for key in sorted(values):
                row = values[key]
                row["evidence_ids"] = sorted(set(row["evidence_ids"]))
                row["authorities"] = sorted(set(row["authorities"]))
                hypotheses.append(row)
            conflicts.append({
                "metric": metric,
                "state": "CONTESTED",
                "hypotheses": hypotheses,
                "reduction": "PRESERVE_NO_AVERAGING",
            })
    return tuple(conflicts)


def _rights_allowed(rights: RightsRecord, commercial_use: bool) -> bool:
    return (not commercial_use) or rights.commercial_use is True


def _threshold_map(
    thresholds: Sequence[ValidationThreshold],
) -> Tuple[Dict[str, ValidationThreshold], Tuple[str, ...]]:
    by_metric: Dict[str, ValidationThreshold] = {}
    duplicates = []
    for item in sorted(thresholds, key=stable_digest):
        if item.metric in by_metric:
            duplicates.append(item.metric)
        else:
            by_metric[item.metric] = item
    return by_metric, tuple(sorted(set(duplicates)))


def assess_claim(request: ClaimRequest) -> Dict[str, Any]:
    """Assess only the bounded claim represented by ``request``."""
    if not isinstance(request, ClaimRequest):
        raise ValueError("request must be a ClaimRequest")

    evidence = tuple(sorted(request.evidence,
                            key=lambda item: item.evidence_digest))
    hypotheses = tuple(item.to_dict() for item in evidence)
    conflicts = _conflicts(evidence)
    base = {
        "schema": DECISION_SCHEMA,
        "project_id": request.project_id,
        "request_id": request.request_id,
        "claim_kind": request.claim_kind.value,
        "claim_digest": request.claim_digest,
        "scope": _canonical(request.scope),
        "hypotheses": hypotheses,
        "conflicts": conflicts,
        "authority_policy": {
            "lanes": [item.value for item in EvidenceAuthority],
            "front_image_ceiling": EvidenceAuthority.OBSERVED.value,
            "reconstruction_ceiling": EvidenceAuthority.MODEL_PROPOSED.value,
            "model_ceiling": EvidenceAuthority.MODEL_PROPOSED.value,
        },
    }

    if request.scope.mode == ScopeMode.UNIVERSAL_ANY_IMAGE:
        reasons = ["UNSUPPORTED_UNBOUNDED_UNIVERSAL_CLAIM"]
        decision = dict(base)
        decision.update({
            "status": UNSUPPORTED_TYPED_STOP,
            "authorized_claim": None,
            "typed_stop": {
                "code": "UNSUPPORTED_ANY_IMAGE_ALWAYS_SUCCEEDS",
                "why": (
                    "an infinite image/garment domain cannot be completely "
                    "validated; declare a finite scope and validate every item"
                ),
            },
            "resolution": _resolution(reasons,
                                      recommended=BOUNDED_ALTERNATIVES),
        })
        decision["decision_digest"] = stable_digest(decision)
        return decision

    reasons = []
    threshold_map, duplicates = _threshold_map(request.thresholds)
    if duplicates:
        reasons.append("DUPLICATE_THRESHOLD_METRIC")
    categories = {item.category for item in request.thresholds}
    for category in REQUIRED_THRESHOLD_CATEGORIES:
        if category not in categories:
            reasons.append("MISSING_%s_THRESHOLD" % category)

    evidence_by_id = {item.evidence_id: item for item in evidence}
    foreign_evidence = [item.evidence_id for item in evidence
                        if item.project_id != request.project_id
                        or item.request_id != request.request_id]
    if foreign_evidence:
        reasons.append("EVIDENCE_SCOPE_MISMATCH")

    if request.commercial_use:
        denied = [item.evidence_id for item in evidence
                  if not _rights_allowed(item.rights, True)]
        denied += [item.case_id for item in request.validations
                   if not _rights_allowed(item.rights, True)]
        if denied:
            reasons.append("COMMERCIAL_RIGHTS_UNKNOWN_OR_DENIED")

    scope_ids = set(request.scope.item_ids)
    case_ids = {item.scope_item_id for item in request.validations}
    if not scope_ids.issubset(case_ids):
        reasons.append("INCOMPLETE_FINITE_VALIDATION_SET")
    if case_ids - scope_ids:
        reasons.append("VALIDATION_OUTSIDE_DECLARED_SCOPE")

    validation_rows = []
    for case in sorted(request.validations, key=lambda item: stable_digest(item)):
        case_reasons = []
        referenced = [evidence_by_id.get(item) for item in case.evidence_ids]
        if any(item is None for item in referenced):
            case_reasons.append("UNKNOWN_VALIDATION_EVIDENCE")
        valid_referenced = [item for item in referenced if item is not None]
        if not any(item.effective_authority in _AUTHORITATIVE_VALIDATION
                   for item in valid_referenced):
            case_reasons.append("MODEL_ONLY_VALIDATION")
        for metric, threshold in sorted(threshold_map.items()):
            values = case.metrics.get(metric, ())
            if len(values) < threshold.minimum_samples:
                case_reasons.append("INSUFFICIENT_SAMPLES:%s" % metric)
                continue
            failures = [value for value in values
                        if not threshold.passes(value)]
            if failures:
                case_reasons.append("THRESHOLD_FAILED:%s" % metric)
        validation_rows.append({
            "case_id": case.case_id,
            "scope_item_id": case.scope_item_id,
            "passed": not case_reasons,
            "reason_codes": sorted(set(case_reasons)),
            "case_digest": stable_digest(case),
        })
        reasons.extend(case_reasons)

    effective = {item.effective_authority for item in evidence
                 if item.project_id == request.project_id
                 and item.request_id == request.request_id}
    if request.claim_kind == ClaimKind.EXACT_BODY_MEASUREMENTS:
        if not effective.intersection({
                EvidenceAuthority.MEASURED,
                EvidenceAuthority.PROVIDER_SUPPORTED}):
            reasons.append("BODY_MEASUREMENTS_NOT_MEASURED")
    elif request.claim_kind == ClaimKind.ARBITRARY_GARMENT_FIDELITY:
        if not effective.intersection(_AUTHORITATIVE_VALIDATION):
            reasons.append("GARMENT_FIDELITY_MODEL_ONLY")
    elif request.claim_kind == ClaimKind.UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN:
        if not effective.intersection({
                EvidenceAuthority.MEASURED,
                EvidenceAuthority.PROVIDER_SUPPORTED}):
            reasons.append("SEWABILITY_NOT_PHYSICALLY_OR_PROVIDER_VALIDATED")

    reasons = sorted(set(reasons))
    decision = dict(base)
    decision["validation"] = validation_rows
    if reasons:
        recommended = (
            CONNECT_PROVIDER
            if "COMMERCIAL_RIGHTS_UNKNOWN_OR_DENIED" in reasons
            else HUMAN_MEASURE
            if request.claim_kind == ClaimKind.EXACT_BODY_MEASUREMENTS
            else EDIT_TARGET_GEOMETRY
            if request.claim_kind == ClaimKind.ARBITRARY_GARMENT_FIDELITY
            else BOUNDED_ALTERNATIVES
        )
        decision.update({
            "status": RESOLUTION_REQUIRED,
            "authorized_claim": None,
            "resolution": _resolution(reasons, recommended=recommended),
        })
    else:
        decision.update({
            "status": CLAIM_AUTHORIZED_SCOPED,
            "authorized_claim": {
                "kind": "FINITE_SCOPE_VALIDATED_%s" % request.claim_kind.value,
                "scope_item_ids": sorted(scope_ids),
                "does_not_authorize": [
                    "ANY_IMAGE_ALWAYS_SUCCEEDS",
                    "UNOBSERVED_REAR_IS_TRUE",
                    "MODEL_OUTPUT_IS_MEASURED",
                    "OUT_OF_SCOPE_GARMENTS",
                ],
                "threshold_digests": sorted(
                    stable_digest(item) for item in request.thresholds),
                "validation_case_digests": sorted(
                    stable_digest(item) for item in request.validations),
            },
            "resolution": None,
        })
    decision["decision_digest"] = stable_digest(decision)
    return decision


def capabilities() -> Dict[str, Any]:
    """Machine-readable statement of what this contract can and cannot claim."""
    payload = {
        "schema": SCHEMA,
        "claim_kinds": [item.value for item in ClaimKind],
        "authority_lanes": [item.value for item in EvidenceAuthority],
        "required_threshold_categories": list(REQUIRED_THRESHOLD_CATEGORIES),
        "actionable_routes": list(ACTIONABLE_ROUTES),
        "universal_guarantee_supported": False,
        "finite_scope_validation_supported": True,
        "conflict_policy": "PRESERVE_NO_AVERAGING",
        "commercial_rights_policy": "FAIL_CLOSED",
    }
    payload["capability_digest"] = stable_digest(payload)
    return payload
