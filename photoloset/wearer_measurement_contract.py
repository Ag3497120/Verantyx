# -*- coding: utf-8 -*-
"""Deterministic target-wearer measurement gate.

The contract consumes typed measurements proposed by a caller (for example an
LLM tool call), but it does not parse natural language and never measures a
person from a garment photograph.  Target-wearer dimensions must be MEASURED
and tied to an explicit measurement method.  A preview mannequin is a separate
PROPOSED, bounded object and cannot satisfy the real-wearer gate.

All lengths are normalized to centimetres.  The semantic digest is therefore
stable across mapping order, ``chest``/``bust`` aliases, and equivalent metre
or centimetre inputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Tuple


REQUEST_SCHEMA = "garment.wearer-measurement.request.v1"
SCHEMA = "garment.wearer-measurement-contract.v1"

MEASURED = "MEASURED"
PROPOSED = "PROPOSED"
REQUESTED = "REQUESTED"
READY = "READY"
STOP = "STOP"

MEASUREMENT_NAMES = (
    "chest_bust",
    "waist",
    "hip",
    "body_length",
    "inseam",
    "shoulder",
    "sleeve_length",
    "height",
)
DEFAULT_REQUIRED_MEASUREMENTS = MEASUREMENT_NAMES

_ALIASES = {
    "chest": "chest_bust",
    "bust": "chest_bust",
    "chest_bust": "chest_bust",
    "waist": "waist",
    "hip": "hip",
    "body_length": "body_length",
    "inseam": "inseam",
    "shoulder": "shoulder",
    "sleeve_length": "sleeve_length",
    "height": "height",
}

# Broad human sanity limits.  They reject unit mistakes and impossible values;
# they are not population norms and must never be used to infer a missing body.
_LIMITS_CM = {
    "chest_bust": (20.0, 300.0),
    "waist": (20.0, 300.0),
    "hip": (20.0, 350.0),
    "body_length": (10.0, 250.0),
    "inseam": (5.0, 180.0),
    "shoulder": (5.0, 100.0),
    "sleeve_length": (5.0, 150.0),
    "height": (30.0, 300.0),
}
_EASE_LIMIT_CM = (-100.0, 200.0)

_TARGET_SOURCE_KINDS = {
    "TAPE_MEASURE",
    "BODY_SCAN",
    "CLINICAL_MEASURE",
    "MANUAL_PATTERN_MEASURE",
    "USER_ENTERED_MEASURED",
}
_PREVIEW_SOURCE_KIND = "BOUNDED_PREVIEW_MANNEQUIN"
_FIT_VALUES = {"CLOSE", "REGULAR", "RELAXED", "OVERSIZED", "CUSTOM"}


class _ContractError(ValueError):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not canonical JSON")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    raise TypeError(f"value is not canonical JSON: {type(value).__name__}")


def stable_digest(value: Any) -> str:
    """Return a SHA-256 digest of canonical JSON."""

    payload = json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _refusal(request: Any, code: str, why: str, **detail: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "decision": STOP,
        "gate_status": STOP,
        "reason_code": code,
        "why": why,
        "manufacturing_ready": False,
        "claims": {
            "natural_language_parsed_here": False,
            "body_measurements_inferred_from_front_photo": False,
            "preview_mannequin_satisfies_target_wearer_gate": False,
        },
        **copy.deepcopy(detail),
    }
    try:
        result["input_digest"] = stable_digest(request)
    except (TypeError, ValueError):
        result["input_digest"] = None
    result["contract_digest"] = stable_digest(result)
    return result


def _canonical_name(raw: Any, *, location: str) -> str:
    if not isinstance(raw, str) or raw not in _ALIASES:
        raise _ContractError(
            "UNKNOWN_MEASUREMENT_NAME",
            "measurement names must be typed members of the contract vocabulary",
            location=location, supplied=copy.deepcopy(raw),
            supported=sorted(_ALIASES),
        )
    return _ALIASES[raw]


def _number(raw: Any, *, location: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise _ContractError(
            "UNKNOWN_INVALID_MEASUREMENT_VALUE",
            "measurement values must be finite numbers",
            location=location,
        )
    value = float(raw)
    if not math.isfinite(value):
        raise _ContractError(
            "UNKNOWN_INVALID_MEASUREMENT_VALUE",
            "measurement values must be finite numbers",
            location=location,
        )
    return value


def _to_cm(raw: Any, unit: Any, *, location: str) -> float:
    if unit not in {"m", "cm"}:
        raise _ContractError(
            "UNKNOWN_EXPLICIT_LENGTH_UNIT_REQUIRED",
            "every body or ease dimension must explicitly use m or cm",
            location=location, supplied_unit=copy.deepcopy(unit),
        )
    value = _number(raw, location=location)
    converted = value * 100.0 if unit == "m" else value
    # Rounding makes semantically equivalent 0.92 m / 92 cm inputs identical.
    return round(converted, 9)


def _source(record: Mapping[str, Any], *, target: bool,
            location: str) -> Dict[str, Any]:
    source = record.get("source")
    if not isinstance(source, Mapping):
        raise _ContractError(
            "UNKNOWN_MEASUREMENT_SOURCE_REQUIRED",
            "each measurement needs a typed, inspectable source",
            location=location,
        )
    kind = source.get("kind")
    allowed = _TARGET_SOURCE_KINDS if target else {_PREVIEW_SOURCE_KIND}
    if kind not in allowed:
        raise _ContractError(
            "UNKNOWN_MEASUREMENT_SOURCE_KIND",
            ("target-wearer measurements cannot come from a front photo"
             if target else
             "preview dimensions must come from a bounded preview mannequin"),
            location=location, supplied_kind=copy.deepcopy(kind),
            allowed_kinds=sorted(allowed),
        )
    reference = source.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        raise _ContractError(
            "UNKNOWN_MEASUREMENT_SOURCE_REQUIRED",
            "measurement source.reference must be non-empty",
            location=location,
        )
    return {"kind": str(kind), "reference": reference.strip()}


def _same(left: Mapping[str, Any], right: Mapping[str, Any],
          keys: Iterable[str]) -> bool:
    return all(left.get(key) == right.get(key) for key in keys)


def _insert_unique(destination: Dict[str, Dict[str, Any]], name: str,
                   record: Dict[str, Any], *, keys: Iterable[str],
                   location: str) -> None:
    existing = destination.get(name)
    if existing is not None and not _same(existing, record, keys):
        raise _ContractError(
            "UNKNOWN_CONFLICTING_MEASUREMENTS",
            "aliases or duplicate records resolve to conflicting dimensions",
            measurement=name, location=location,
            existing=copy.deepcopy(existing), supplied=copy.deepcopy(record),
        )
    if existing is None:
        destination[name] = record


def _mapping(value: Any, *, code: str, why: str,
             location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _ContractError(code, why, location=location)
    return value


def _parse_target(value: Any) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    target = _mapping(
        value, code="UNKNOWN_TARGET_WEARER_REQUIRED",
        why="target_wearer must be a typed object", location="target_wearer",
    )
    wearer_id = target.get("wearer_id")
    if not isinstance(wearer_id, str) or not wearer_id.strip():
        raise _ContractError(
            "UNKNOWN_TARGET_WEARER_REQUIRED",
            "target_wearer.wearer_id must be non-empty",
            location="target_wearer.wearer_id",
        )
    supplied = _mapping(
        target.get("measurements"),
        code="UNKNOWN_TARGET_MEASUREMENTS_REQUIRED",
        why="target_wearer.measurements must be a field-keyed object",
        location="target_wearer.measurements",
    )
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_name in sorted(supplied, key=str):
        location = f"target_wearer.measurements.{raw_name}"
        name = _canonical_name(raw_name, location=location)
        record = _mapping(
            supplied[raw_name], code="UNKNOWN_TYPED_MEASUREMENT_REQUIRED",
            why="each target measurement must be a typed object",
            location=location,
        )
        if record.get("authority") != MEASURED:
            raise _ContractError(
                "UNKNOWN_TARGET_MEASUREMENT_NOT_MEASURED",
                "target-wearer values must have MEASURED authority",
                location=location, supplied_authority=record.get("authority"),
            )
        value_cm = _to_cm(record.get("value"), record.get("unit"),
                          location=location)
        low, high = _LIMITS_CM[name]
        if not low <= value_cm <= high:
            raise _ContractError(
                "UNKNOWN_MEASUREMENT_OUT_OF_BOUNDS",
                "measurement is outside the contract's broad physical sanity bounds",
                location=location, value_cm=value_cm,
                allowed_range_cm={"minimum": low, "maximum": high},
            )
        normalized_record = {
            "measurement": name,
            "value_cm": value_cm,
            "unit": "cm",
            "authority": MEASURED,
            "source": _source(record, target=True, location=location),
        }
        _insert_unique(
            normalized, name, normalized_record,
            keys=("value_cm", "authority"), location=location,
        )
    return wearer_id.strip(), {name: normalized[name] for name in sorted(normalized)}


def _parse_preview(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    preview = _mapping(
        value, code="UNKNOWN_PREVIEW_MANNEQUIN_FORMAT",
        why="preview_mannequin must be a typed object",
        location="preview_mannequin",
    )
    preview_id = preview.get("preview_id")
    if not isinstance(preview_id, str) or not preview_id.strip():
        raise _ContractError(
            "UNKNOWN_PREVIEW_MANNEQUIN_FORMAT",
            "preview_mannequin.preview_id must be non-empty",
            location="preview_mannequin.preview_id",
        )
    supplied = _mapping(
        preview.get("measurements"),
        code="UNKNOWN_PREVIEW_MANNEQUIN_FORMAT",
        why="preview_mannequin.measurements must be a field-keyed object",
        location="preview_mannequin.measurements",
    )
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_name in sorted(supplied, key=str):
        location = f"preview_mannequin.measurements.{raw_name}"
        name = _canonical_name(raw_name, location=location)
        record = _mapping(
            supplied[raw_name], code="UNKNOWN_TYPED_MEASUREMENT_REQUIRED",
            why="each preview measurement must be a typed object",
            location=location,
        )
        if record.get("authority") != PROPOSED:
            raise _ContractError(
                "UNKNOWN_PREVIEW_MEASUREMENT_NOT_PROPOSED",
                "preview-mannequin values must remain PROPOSED",
                location=location, supplied_authority=record.get("authority"),
            )
        unit = record.get("unit")
        minimum_cm = _to_cm(record.get("minimum"), unit, location=location)
        maximum_cm = _to_cm(record.get("maximum"), unit, location=location)
        if minimum_cm > maximum_cm:
            raise _ContractError(
                "UNKNOWN_INVALID_MEASUREMENT_RANGE",
                "preview measurement minimum must not exceed maximum",
                location=location, minimum_cm=minimum_cm,
                maximum_cm=maximum_cm,
            )
        low, high = _LIMITS_CM[name]
        if minimum_cm < low or maximum_cm > high:
            raise _ContractError(
                "UNKNOWN_MEASUREMENT_OUT_OF_BOUNDS",
                "preview bounds are outside broad physical sanity bounds",
                location=location,
                supplied_range_cm={"minimum": minimum_cm, "maximum": maximum_cm},
                allowed_range_cm={"minimum": low, "maximum": high},
            )
        normalized_record = {
            "measurement": name,
            "minimum_cm": minimum_cm,
            "maximum_cm": maximum_cm,
            "unit": "cm",
            "authority": PROPOSED,
            "source": _source(record, target=False, location=location),
        }
        _insert_unique(
            normalized, name, normalized_record,
            keys=("minimum_cm", "maximum_cm", "authority"), location=location,
        )
    return {
        "preview_id": preview_id.strip(),
        "authority": PROPOSED,
        "bounded": True,
        "measurements": {name: normalized[name] for name in sorted(normalized)},
        "satisfies_target_wearer_gate": False,
    }


def _parse_required(value: Any) -> List[str]:
    if value is None:
        return list(DEFAULT_REQUIRED_MEASUREMENTS)
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or not value):
        raise _ContractError(
            "UNKNOWN_REQUIRED_MEASUREMENTS_FORMAT",
            "required_measurements must be a non-empty list of typed names",
            location="required_measurements",
        )
    result = [_canonical_name(item, location="required_measurements")
              for item in value]
    return sorted(set(result))


def _parse_fit(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    fit = _mapping(
        value, code="UNKNOWN_FIT_REQUEST_FORMAT",
        why="fit must be a typed object", location="fit",
    )
    kind = fit.get("kind")
    if kind not in _FIT_VALUES or fit.get("authority") != REQUESTED:
        raise _ContractError(
            "UNKNOWN_FIT_REQUEST_FORMAT",
            "fit.kind must be typed and fit.authority must be REQUESTED",
            location="fit", supported=sorted(_FIT_VALUES),
        )
    return {"kind": str(kind), "authority": REQUESTED,
            "creates_numeric_ease": False}


def _parse_ease(value: Any) -> Dict[str, Dict[str, Any]]:
    if value is None:
        return {}
    supplied = _mapping(
        value, code="UNKNOWN_EASE_REQUEST_FORMAT",
        why="ease must be a field-keyed object", location="ease",
    )
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_name in sorted(supplied, key=str):
        location = f"ease.{raw_name}"
        name = _canonical_name(raw_name, location=location)
        record = _mapping(
            supplied[raw_name], code="UNKNOWN_EASE_REQUEST_FORMAT",
            why="each ease request must be a typed object", location=location,
        )
        if record.get("authority") != REQUESTED:
            raise _ContractError(
                "UNKNOWN_EASE_NOT_EXPLICITLY_REQUESTED",
                "ease values must have REQUESTED authority",
                location=location, supplied_authority=record.get("authority"),
            )
        exact = "delta" in record
        ranged = "minimum" in record or "maximum" in record
        if exact == ranged or (ranged and not {"minimum", "maximum"} <= set(record)):
            raise _ContractError(
                "UNKNOWN_EXPLICIT_EASE_DELTA_OR_RANGE_REQUIRED",
                "ease must contain either delta or both minimum and maximum",
                location=location,
            )
        unit = record.get("unit")
        if exact:
            minimum_cm = maximum_cm = _to_cm(
                record.get("delta"), unit, location=location)
            mode = "EXACT_DELTA"
        else:
            minimum_cm = _to_cm(record.get("minimum"), unit, location=location)
            maximum_cm = _to_cm(record.get("maximum"), unit, location=location)
            mode = "DELTA_RANGE"
        if minimum_cm > maximum_cm:
            raise _ContractError(
                "UNKNOWN_INVALID_EASE_RANGE",
                "ease minimum must not exceed maximum",
                location=location, minimum_cm=minimum_cm,
                maximum_cm=maximum_cm,
            )
        if (minimum_cm < _EASE_LIMIT_CM[0]
                or maximum_cm > _EASE_LIMIT_CM[1]):
            raise _ContractError(
                "UNKNOWN_EASE_OUT_OF_BOUNDS",
                "ease is outside the broad engineering sanity bounds",
                location=location,
                allowed_range_cm={"minimum": _EASE_LIMIT_CM[0],
                                  "maximum": _EASE_LIMIT_CM[1]},
            )
        normalized_record = {
            "measurement": name,
            "mode": mode,
            "minimum_delta_cm": minimum_cm,
            "maximum_delta_cm": maximum_cm,
            "unit": "cm",
            "authority": REQUESTED,
        }
        _insert_unique(
            normalized, name, normalized_record,
            keys=("minimum_delta_cm", "maximum_delta_cm", "authority"),
            location=location,
        )
    return {name: normalized[name] for name in sorted(normalized)}


def compile_contract(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the deterministic wearer-measurement target IR.

    A successful result only means the requested real-wearer measurements are
    present and well typed.  It is not evidence that a pattern fits, is
    comfortable, or is ready for manufacture.
    """

    if not isinstance(request, Mapping):
        return _refusal(
            request, "UNKNOWN_WEARER_MEASUREMENT_REQUEST",
            "request must be an object",
        )
    if request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            request, "UNKNOWN_WEARER_MEASUREMENT_SCHEMA",
            f"schema must be {REQUEST_SCHEMA}",
        )
    try:
        # Canonicalize early so unsupported objects and NaN fail closed.
        input_digest = stable_digest(request)
        wearer_id, target = _parse_target(request.get("target_wearer"))
        preview = _parse_preview(request.get("preview_mannequin"))
        required = _parse_required(request.get("required_measurements"))
        fit = _parse_fit(request.get("fit"))
        ease = _parse_ease(request.get("ease"))
    except _ContractError as exc:
        return _refusal(request, exc.code, exc.why, **exc.detail)
    except (TypeError, ValueError) as exc:
        return _refusal(
            request, "UNKNOWN_NON_CANONICAL_MEASUREMENT_REQUEST",
            f"request must be canonical JSON: {exc}",
        )

    missing = [name for name in required if name not in target]
    if missing:
        return _refusal(
            request, "STOP_TARGET_WEARER_MEASUREMENTS_REQUIRED",
            "bounded preview values cannot replace missing target-wearer measurements",
            wearer_id=wearer_id, missing_measurements=missing,
            preview_mannequin=preview,
        )

    semantic = {
        "schema": SCHEMA,
        "decision": READY,
        "gate_status": READY,
        "reason_code": "READY_TARGET_WEARER_MEASUREMENTS_MEASURED",
        "target_wearer": {
            "wearer_id": wearer_id,
            "authority": MEASURED,
            "measurements": target,
        },
        "preview_mannequin": preview,
        "required_measurements": required,
        "fit": fit,
        "ease": ease,
        "missing_measurements": [],
        "manufacturing_ready": False,
        "claims": {
            "natural_language_parsed_here": False,
            "body_measurements_inferred_from_front_photo": False,
            "preview_mannequin_satisfies_target_wearer_gate": False,
            "fit_or_comfort_proven": False,
        },
    }
    result = copy.deepcopy(semantic)
    result["input_digest"] = input_digest
    result["contract_digest"] = stable_digest(semantic)
    return result


# A concise public verb for callers that treat this module as a gate.
evaluate = compile_contract
