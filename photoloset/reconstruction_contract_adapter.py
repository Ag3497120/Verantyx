# -*- coding: utf-8 -*-
"""Strict JSON boundary for :mod:`reconstruction_claim_contract`.

The reconstruction claim contract intentionally accepts typed dataclasses,
while MCP receives untrusted JSON.  This module is the only decoder between
those two representations.  It rejects unknown or missing fields, decodes
every nested record explicitly, and contains malformed requests as typed
``UNKNOWN`` decisions instead of exceptions.

No boundary rule raises evidence authority.  In particular, MODEL and
RECONSTRUCTION producers remain ``MODEL_PROPOSED`` even when their submitted
``authority`` field says ``MEASURED``.  Model-only requests remain visible as
hypotheses, but are rejected with a typed unresolved reason.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Type, TypeVar

from . import reconstruction_claim_contract as _contract


REQUEST_SCHEMA = _contract.SCHEMA
UNKNOWN_MODEL_ONLY_EVIDENCE = "UNKNOWN_MODEL_ONLY_EVIDENCE"

_EnumT = TypeVar("_EnumT", bound=Enum)


class ReconstructionClaimDecodeError(ValueError):
    """A path-addressed reconstruction request decoding failure."""

    def __init__(
        self,
        path: str,
        why: str,
        *,
        code: str = "UNKNOWN_BAD_ARGUMENTS",
    ) -> None:
        super().__init__(why)
        self.path = path
        self.why = why
        self.code = code


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReconstructionClaimDecodeError(path, "must be a JSON object")
    return value


def _array(value: Any, path: str) -> Sequence[Any]:
    if (not isinstance(value, Sequence)
            or isinstance(value, (str, bytes, bytearray))):
        raise ReconstructionClaimDecodeError(path, "must be a JSON array")
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
        raise ReconstructionClaimDecodeError(
            path, "contains unsupported fields: " + ", ".join(unknown))
    missing = [name for name in required if name not in row]
    if missing:
        raise ReconstructionClaimDecodeError(
            path, "is missing required fields: " + ", ".join(missing))
    return row


def _tuple(value: Any, path: str, decoder) -> tuple:
    return tuple(
        decoder(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _enum(
    enum_type: Type[_EnumT], value: Any, path: str,
) -> _EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        allowed = ", ".join(item.value for item in enum_type)
        raise ReconstructionClaimDecodeError(
            path,
            "must be one of: " + allowed,
            code="UNKNOWN_AUTHORITY_OR_ENUM_VALUE",
        ) from None


def _rights(value: Any, path: str) -> _contract.RightsRecord:
    row = _fields(
        value,
        path,
        required=("license_id", "holder", "commercial_use"),
        optional=("source_uri",),
    )
    return _contract.RightsRecord(
        license_id=row["license_id"],
        holder=row["holder"],
        commercial_use=row["commercial_use"],
        source_uri=row.get("source_uri", ""),
    )


def _provenance(value: Any, path: str) -> _contract.ProvenanceRecord:
    row = _fields(
        value,
        path,
        required=("source_id", "source_digest", "method", "revision"),
    )
    try:
        return _contract.ProvenanceRecord(
            source_id=row["source_id"],
            source_digest=row["source_digest"],
            method=row["method"],
            revision=row["revision"],
        )
    except (TypeError, ValueError) as exc:
        raise ReconstructionClaimDecodeError(
            path,
            str(exc),
            code="UNKNOWN_MALFORMED_PROVENANCE",
        ) from None


def _evidence(value: Any, path: str) -> _contract.EvidenceRecord:
    row = _fields(
        value,
        path,
        required=(
            "evidence_id", "metric", "value", "authority", "producer",
            "project_id", "request_id", "provenance", "rights",
        ),
    )
    return _contract.EvidenceRecord(
        evidence_id=row["evidence_id"],
        metric=row["metric"],
        value=row["value"],
        authority=_enum(
            _contract.EvidenceAuthority,
            row["authority"],
            f"{path}.authority",
        ),
        producer=_enum(
            _contract.ProducerKind,
            row["producer"],
            f"{path}.producer",
        ),
        project_id=row["project_id"],
        request_id=row["request_id"],
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
        rights=_rights(row["rights"], f"{path}.rights"),
    )


def _threshold(value: Any, path: str) -> _contract.ValidationThreshold:
    row = _fields(
        value,
        path,
        required=(
            "category", "metric", "operator", "value", "unit",
            "minimum_samples", "approved_by", "provenance",
        ),
    )
    return _contract.ValidationThreshold(
        category=row["category"],
        metric=row["metric"],
        operator=_enum(
            _contract.ThresholdOperator,
            row["operator"],
            f"{path}.operator",
        ),
        value=row["value"],
        unit=row["unit"],
        minimum_samples=row["minimum_samples"],
        approved_by=row["approved_by"],
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
    )


def _validation(value: Any, path: str) -> _contract.ValidationCase:
    row = _fields(
        value,
        path,
        required=(
            "case_id", "scope_item_id", "metrics", "evidence_ids",
            "provenance", "rights",
        ),
    )
    metrics = _object(row["metrics"], f"{path}.metrics")
    evidence_ids = _array(row["evidence_ids"], f"{path}.evidence_ids")
    return _contract.ValidationCase(
        case_id=row["case_id"],
        scope_item_id=row["scope_item_id"],
        metrics=metrics,
        evidence_ids=tuple(evidence_ids),
        provenance=_provenance(row["provenance"], f"{path}.provenance"),
        rights=_rights(row["rights"], f"{path}.rights"),
    )


def _scope(value: Any, path: str) -> _contract.ClaimScope:
    row = _fields(value, path, required=("mode", "item_ids"))
    item_ids = _array(row["item_ids"], f"{path}.item_ids")
    return _contract.ClaimScope(
        mode=_enum(_contract.ScopeMode, row["mode"], f"{path}.mode"),
        item_ids=tuple(item_ids),
    )


def decode_claim_request(value: Any) -> _contract.ClaimRequest:
    """Decode one strict JSON object into a typed ``ClaimRequest``."""
    row = _fields(
        value,
        "$",
        required=(
            "schema", "project_id", "request_id", "claim_kind", "scope",
            "evidence", "thresholds", "validations", "commercial_use",
        ),
    )
    if row["schema"] != REQUEST_SCHEMA:
        raise ReconstructionClaimDecodeError(
            "$.schema", f"must be exactly {REQUEST_SCHEMA}")
    return _contract.ClaimRequest(
        project_id=row["project_id"],
        request_id=row["request_id"],
        claim_kind=_enum(
            _contract.ClaimKind,
            row["claim_kind"],
            "$.claim_kind",
        ),
        scope=_scope(row["scope"], "$.scope"),
        evidence=_tuple(row["evidence"], "$.evidence", _evidence),
        thresholds=_tuple(
            row["thresholds"], "$.thresholds", _threshold),
        validations=_tuple(
            row["validations"], "$.validations", _validation),
        commercial_use=row["commercial_use"],
    )


def _routes() -> list[Dict[str, Any]]:
    return [
        {"kind": route, "does_not_promote_model_output": True}
        for route in _contract.ACTIONABLE_ROUTES
    ]


def unknown_decision(
    issue: ReconstructionClaimDecodeError,
    *,
    claim_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a deterministic, contract-shaped typed boundary refusal."""
    resolution = {
        "schema": _contract.RESOLUTION_SCHEMA,
        "reason_codes": [issue.code],
        "recommended_route": _contract.TYPED_STOP,
        "routes": _routes(),
    }
    result: Dict[str, Any] = {
        "schema": _contract.DECISION_SCHEMA,
        "project_id": None,
        "request_id": None,
        "claim_kind": claim_kind,
        "claim_digest": None,
        "scope": None,
        "hypotheses": [],
        "conflicts": [],
        "authority_policy": {
            "lanes": [item.value for item in _contract.EvidenceAuthority],
            "front_image_ceiling": (
                _contract.EvidenceAuthority.OBSERVED.value),
            "reconstruction_ceiling": (
                _contract.EvidenceAuthority.MODEL_PROPOSED.value),
            "model_ceiling": (
                _contract.EvidenceAuthority.MODEL_PROPOSED.value),
        },
        "validation": [],
        "status": _contract.RESOLUTION_REQUIRED,
        "authorized_claim": None,
        "typed_unknown": {
            "code": issue.code,
            "target": issue.path,
            "why": issue.why,
        },
        "resolution": resolution,
    }
    result["decision_digest"] = _contract.stable_digest(result)
    return result


def decode_claim_request_json(
    json_text: str,
) -> Tuple[Optional[_contract.ClaimRequest], Optional[Dict[str, Any]]]:
    """Decode MCP text and contain malformed-input failures as typed data."""
    try:
        value = json.loads(json_text) if json_text.strip() else {}
    except (AttributeError, TypeError, json.JSONDecodeError) as exc:
        issue = ReconstructionClaimDecodeError(
            "$", f"must be valid JSON: {exc}")
        return None, unknown_decision(issue)
    try:
        return decode_claim_request(value), None
    except ReconstructionClaimDecodeError as exc:
        claim_kind = value.get("claim_kind") if isinstance(value, Mapping) else None
        return None, unknown_decision(exc, claim_kind=claim_kind)
    except (TypeError, ValueError) as exc:
        issue = ReconstructionClaimDecodeError(
            "$",
            str(exc),
            code="UNKNOWN_TYPED_RECONSTRUCTION_INPUT",
        )
        claim_kind = value.get("claim_kind") if isinstance(value, Mapping) else None
        return None, unknown_decision(issue, claim_kind=claim_kind)


def _mark_model_only(decision: Mapping[str, Any]) -> Dict[str, Any]:
    """Add the explicit typed boundary reason without discarding hypotheses."""
    result = copy.deepcopy(dict(decision))
    resolution = dict(result.get("resolution") or {})
    reason_codes = set(resolution.get("reason_codes") or ())
    reason_codes.add(UNKNOWN_MODEL_ONLY_EVIDENCE)
    resolution.update({
        "schema": _contract.RESOLUTION_SCHEMA,
        "reason_codes": sorted(reason_codes),
        "recommended_route": _contract.CONNECT_PROVIDER,
        "routes": resolution.get("routes") or _routes(),
    })
    result["status"] = _contract.RESOLUTION_REQUIRED
    result["authorized_claim"] = None
    result.pop("typed_stop", None)
    result["typed_unknown"] = {
        "code": UNKNOWN_MODEL_ONLY_EVIDENCE,
        "target": "$.evidence",
        "why": (
            "model or reconstruction evidence may remain as a proposal, "
            "but cannot authorize the requested reconstruction claim"
        ),
    }
    result["resolution"] = resolution
    result.pop("decision_digest", None)
    result["decision_digest"] = _contract.stable_digest(result)
    return result


def capabilities(json_text: str = "") -> Dict[str, Any]:
    """Return deterministic capabilities for an empty MCP JSON request."""
    try:
        value = json.loads(json_text) if json_text.strip() else {}
    except (AttributeError, TypeError, json.JSONDecodeError) as exc:
        return unknown_decision(ReconstructionClaimDecodeError(
            "$", f"must be valid JSON: {exc}"))
    if not isinstance(value, Mapping) or value:
        return unknown_decision(ReconstructionClaimDecodeError(
            "$", "capabilities accepts only an empty JSON object"))
    return _contract.capabilities()


def assess(json_text: str = "") -> Dict[str, Any]:
    """Strictly decode and assess one JSON-safe reconstruction claim."""
    request, refusal = decode_claim_request_json(json_text)
    if refusal is not None:
        return refusal
    assert request is not None
    try:
        decision = _contract.assess_claim(request)
    except (TypeError, ValueError) as exc:
        return unknown_decision(
            ReconstructionClaimDecodeError(
                "$",
                str(exc),
                code="UNKNOWN_TYPED_RECONSTRUCTION_INPUT",
            ),
            claim_kind=request.claim_kind.value,
        )
    effective = {item.effective_authority for item in request.evidence}
    if effective and effective == {
            _contract.EvidenceAuthority.MODEL_PROPOSED}:
        return _mark_model_only(decision)
    return decision


__all__ = [
    "REQUEST_SCHEMA",
    "UNKNOWN_MODEL_ONLY_EVIDENCE",
    "ReconstructionClaimDecodeError",
    "assess",
    "capabilities",
    "decode_claim_request",
    "decode_claim_request_json",
    "unknown_decision",
]
