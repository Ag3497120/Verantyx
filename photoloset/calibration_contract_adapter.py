# -*- coding: utf-8 -*-
"""Strict JSON boundary for :mod:`physical_calibration_contract`.

The calibration contract deliberately accepts dataclasses rather than loose
dictionaries.  MCP, however, receives untrusted JSON.  This module is the
single decoder between those two worlds: every object has an explicit field
set, every nested record is converted to its contract dataclass, and malformed
input becomes a typed ``CLAIM_BLOCKED`` decision rather than an exception.

No decoder rule raises an evidence authority.  In particular, a MODEL or
SIMULATION producer that asks for ``MEASURED`` is still reduced to
``PROPOSED`` by the underlying contract.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Optional, Tuple

from . import physical_calibration_contract as _contract


REQUEST_SCHEMA = _contract.SCHEMA


class PhysicalCalibrationDecodeError(ValueError):
    """A path-addressed request decoding failure."""

    def __init__(self, path: str, why: str, *, code: str = "UNKNOWN_BAD_ARGUMENTS"):
        super().__init__(why)
        self.path = path
        self.why = why
        self.code = code


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PhysicalCalibrationDecodeError(path, "must be a JSON object")
    return value


def _array(value: Any, path: str) -> Sequence[Any]:
    if (not isinstance(value, Sequence)
            or isinstance(value, (str, bytes, bytearray))):
        raise PhysicalCalibrationDecodeError(path, "must be a JSON array")
    return value


def _fields(
    value: Any,
    path: str,
    *,
    required: Sequence[str],
    optional: Sequence[str] = (),
) -> Mapping[str, Any]:
    row = _object(value, path)
    allowed = set(required) | set(optional)
    unknown = sorted(str(key) for key in row if key not in allowed)
    if unknown:
        raise PhysicalCalibrationDecodeError(
            path, "contains unsupported fields: " + ", ".join(unknown))
    missing = [name for name in required if name not in row]
    if missing:
        raise PhysicalCalibrationDecodeError(
            path, "is missing required fields: " + ", ".join(missing))
    return row


def _tuple(value: Any, path: str, decoder) -> tuple:
    return tuple(decoder(item, f"{path}[{index}]")
                 for index, item in enumerate(_array(value, path)))


def _rights(value: Any, path: str) -> _contract.RightsRecord:
    row = _fields(
        value, path,
        required=("license_id", "holder", "permitted_uses"),
        optional=("source_uri",),
    )
    uses = _array(row["permitted_uses"], f"{path}.permitted_uses")
    return _contract.RightsRecord(
        license_id=row["license_id"],
        holder=row["holder"],
        permitted_uses=tuple(uses),
        source_uri=row.get("source_uri", ""),
    )


def _provenance(value: Any, path: str) -> _contract.ProvenanceRecord:
    row = _fields(
        value, path,
        required=(
            "source_id", "source_digest", "method", "revision",
            "producer_kind", "rights",
        ),
        optional=("recorded_at",),
    )
    return _contract.ProvenanceRecord(
        source_id=row["source_id"],
        source_digest=row["source_digest"],
        method=row["method"],
        revision=row["revision"],
        producer_kind=_contract.ProducerKind(row["producer_kind"]),
        rights=_rights(row["rights"], f"{path}.rights"),
        recorded_at=row.get("recorded_at", ""),
    )


def _material(value: Any, path: str) -> _contract.MaterialPropertyInput:
    row = _fields(
        value, path,
        required=(
            "property_name", "value", "unit", "authority", "provenance",
        ),
        optional=("uncertainty", "conditions"),
    )
    conditions = row.get("conditions", {})
    _object(conditions, f"{path}.conditions")
    return _contract.MaterialPropertyInput(
        property_name=row["property_name"],
        value=row["value"],
        unit=row["unit"],
        authority=_contract.EvidenceAuthority(row["authority"]),
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
        uncertainty=row.get("uncertainty"),
        conditions=conditions,
    )


def _observation(value: Any, path: str) -> _contract.CalibrationObservation:
    row = _fields(
        value, path,
        required=(
            "observation_id", "domain", "test_kind", "metric", "sample_id",
            "value", "unit", "authority", "provenance",
        ),
        optional=("conditions",),
    )
    conditions = row.get("conditions", {})
    _object(conditions, f"{path}.conditions")
    return _contract.CalibrationObservation(
        observation_id=row["observation_id"],
        domain=_contract.CalibrationDomain(row["domain"]),
        test_kind=row["test_kind"],
        metric=row["metric"],
        sample_id=row["sample_id"],
        value=row["value"],
        unit=row["unit"],
        authority=_contract.EvidenceAuthority(row["authority"]),
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
        conditions=conditions,
    )


def _test(value: Any, path: str) -> _contract.CalibrationTest:
    row = _fields(
        value, path,
        required=("test_id", "domain", "test_kind", "observations", "provenance"),
    )
    return _contract.CalibrationTest(
        test_id=row["test_id"],
        domain=_contract.CalibrationDomain(row["domain"]),
        test_kind=row["test_kind"],
        observations=_tuple(
            row["observations"], f"{path}.observations", _observation),
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
    )


def _dataset(value: Any, path: str) -> _contract.CalibrationDataset:
    row = _fields(
        value, path,
        required=("dataset_id", "domain", "tests", "provenance"),
    )
    return _contract.CalibrationDataset(
        dataset_id=row["dataset_id"],
        domain=_contract.CalibrationDomain(row["domain"]),
        tests=_tuple(row["tests"], f"{path}.tests", _test),
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
    )


def _threshold(value: Any, path: str) -> _contract.AcceptanceThreshold:
    row = _fields(
        value, path,
        required=(
            "threshold_id", "domain", "metric", "operator", "value", "unit",
            "minimum_samples", "approved_by", "provenance",
        ),
    )
    return _contract.AcceptanceThreshold(
        threshold_id=row["threshold_id"],
        domain=_contract.CalibrationDomain(row["domain"]),
        metric=row["metric"],
        operator=_contract.ThresholdOperator(row["operator"]),
        value=row["value"],
        unit=row["unit"],
        minimum_samples=row["minimum_samples"],
        approved_by=row["approved_by"],
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
    )


def _requirement(value: Any, path: str) -> _contract.ValidationRequirement:
    row = _fields(
        value, path,
        required=("test_kind", "metric", "unit", "minimum_samples"),
    )
    return _contract.ValidationRequirement(
        test_kind=row["test_kind"],
        metric=row["metric"],
        unit=row["unit"],
        minimum_samples=row["minimum_samples"],
    )


def _plan(value: Any, path: str) -> _contract.ValidationPlan:
    row = _fields(
        value, path,
        required=(
            "plan_id", "domain", "required_material_properties",
            "requirements", "description",
        ),
    )
    properties = _array(
        row["required_material_properties"],
        f"{path}.required_material_properties",
    )
    return _contract.ValidationPlan(
        plan_id=row["plan_id"],
        domain=_contract.CalibrationDomain(row["domain"]),
        required_material_properties=tuple(properties),
        requirements=_tuple(
            row["requirements"], f"{path}.requirements", _requirement),
        description=row["description"],
    )


def decode_claim_request(value: Any) -> _contract.ClaimRequest:
    """Decode one strict JSON object into a :class:`ClaimRequest`."""
    row = _fields(
        value, "$",
        required=(
            "schema", "claim_id", "subject_id", "claim_kind",
            "material_properties", "datasets", "thresholds",
        ),
        optional=("domain", "requested_error_percent", "plan"),
    )
    if row["schema"] != REQUEST_SCHEMA:
        raise PhysicalCalibrationDecodeError(
            "$.schema", f"must be exactly {REQUEST_SCHEMA}")
    plan = None
    if row.get("plan") is not None:
        plan = _plan(row["plan"], "$.plan")
    request = _contract.ClaimRequest(
        claim_id=row["claim_id"],
        subject_id=row["subject_id"],
        claim_kind=_contract.ClaimKind(row["claim_kind"]),
        material_properties=_tuple(
            row["material_properties"], "$.material_properties", _material),
        datasets=_tuple(row["datasets"], "$.datasets", _dataset),
        thresholds=_tuple(row["thresholds"], "$.thresholds", _threshold),
        requested_error_percent=row.get("requested_error_percent"),
        plan=plan,
    )
    supplied_domain = row.get("domain")
    if supplied_domain is not None and supplied_domain != request.domain.value:
        raise PhysicalCalibrationDecodeError(
            "$.domain",
            f"must match claim_kind-derived domain {request.domain.value}",
        )
    return request


def blocked_decision(
    issue: PhysicalCalibrationDecodeError,
    *,
    claim_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the contract-shaped refusal used at the MCP trust boundary."""
    reason = {
        "code": issue.code,
        "target": issue.path,
        "detail": issue.why,
    }
    options = [
        {
            "kind": _contract.ResolutionKind.MEASURE.value,
            "can_satisfy_claim": True,
            "description": "Correct and supply the strict typed measurement request.",
        },
        {
            "kind": _contract.ResolutionKind.CONNECT_PROVIDER.value,
            "can_satisfy_claim": True,
            "description": "Connect a rights-cleared measurement provider.",
        },
        {
            "kind": _contract.ResolutionKind.BOUNDED_ALTERNATIVES.value,
            "can_satisfy_claim": False,
            "description": "Compare proposals without authorizing calibration.",
        },
        {
            "kind": _contract.ResolutionKind.TYPED_STOP.value,
            "can_satisfy_claim": False,
            "description": "Stop without making the requested physical claim.",
        },
    ]
    resolution = {
        "schema": _contract.RESOLUTION_SCHEMA,
        "request_id": _contract.stable_digest({"reason": reason, "options": options}),
        "claim_id": None,
        "claim_kind": claim_kind,
        "blocking_reason_codes": [issue.code],
        "options": options,
        "recommended": _contract.ResolutionKind.MEASURE.value,
        "model_may_author_measurements": False,
        "bounded_alternatives_are_calibration": False,
    }
    resolution["resolution_digest"] = _contract.stable_digest(resolution)
    result: Dict[str, Any] = {
        "schema": _contract.DECISION_SCHEMA,
        "verdict": _contract.CLAIM_BLOCKED,
        "claim_authorized": False,
        "claim_authority": "NONE",
        "claim_request_digest": None,
        "claim_kind": claim_kind,
        "domain": None,
        "validation_plan": None,
        "property_reduction": None,
        "observation_conflicts": [],
        "validation_checks": [],
        "blocking_reasons": [reason],
        "authorized_claim": None,
        "truth_contract": {
            "model_authority_ceiling": _contract.EvidenceAuthority.PROPOSED.value,
            "simulation_is_measurement": False,
            "conflicts_are_averaged": False,
            "bounded_alternatives_authorize_claim": False,
            "few_percent_claim_requires_non_model_measurements": True,
            "few_percent_claim_requires_explicit_thresholds": True,
        },
        "resolution_request": resolution,
    }
    result["decision_digest"] = _contract.stable_digest(result)
    return result


def decode_claim_request_json(
    json_text: str,
) -> Tuple[Optional[_contract.ClaimRequest], Optional[Dict[str, Any]]]:
    """Decode MCP text and contain every malformed-input failure as data."""
    try:
        value = json.loads(json_text) if json_text.strip() else {}
    except (AttributeError, json.JSONDecodeError) as exc:
        issue = PhysicalCalibrationDecodeError(
            "$", f"must be valid JSON: {exc}", code="UNKNOWN_BAD_ARGUMENTS")
        return None, blocked_decision(issue)
    try:
        return decode_claim_request(value), None
    except PhysicalCalibrationDecodeError as exc:
        claim_kind = value.get("claim_kind") if isinstance(value, Mapping) else None
        return None, blocked_decision(exc, claim_kind=claim_kind)
    except (TypeError, ValueError) as exc:
        issue = PhysicalCalibrationDecodeError(
            "$", str(exc), code="UNKNOWN_TYPED_CALIBRATION_INPUT")
        claim_kind = value.get("claim_kind") if isinstance(value, Mapping) else None
        return None, blocked_decision(issue, claim_kind=claim_kind)


__all__ = [
    "PhysicalCalibrationDecodeError", "REQUEST_SCHEMA", "blocked_decision",
    "decode_claim_request", "decode_claim_request_json",
]
