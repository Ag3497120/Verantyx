# -*- coding: utf-8 -*-
"""Lower validated chat requirements to proposal-only preview geometry.

The beginner LLM may preserve an explicit request such as ``waist 72 cm`` or
``waist ease 4 cm`` in ``GarmentCommandIR``.  This module is the deterministic
boundary after that language step.  It normalizes units, keeps standard-size
labels separate from measurements, and emits only the primitive dimensions
that follow unambiguously from a specifically named target.

The result is deliberately *not* a wearer-measurement certificate.  A number
typed by a user can drive a clearly labelled preview, but manufacturing still
needs the measurement-source contract and the remaining body dimensions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple


REQUEST_SCHEMA = "garment.design-requirement-profile.request.v1"
SCHEMA = "garment.design-requirement-profile.v1"

_KINDS = {
    "STANDARD_SIZE", "BODY_MEASUREMENT", "GARMENT_MEASUREMENT", "EASE",
    "LENGTH", "FIT", "MATERIAL", "STRUCTURE", "DETAIL", "CONSTRUCTION",
    "COMFORT",
}
_DIMENSION_KINDS = {
    "BODY_MEASUREMENT", "GARMENT_MEASUREMENT", "EASE", "LENGTH",
}
_UNITS_TO_CM = {"mm": 0.1, "cm": 1.0, "m": 100.0}

_TARGET_ALIASES = {
    "chest_bust": ("chest", "bust", "chest bust", "胸囲", "バスト"),
    "waist": ("waist", "waist circumference", "ウエスト", "胴囲"),
    "hip": ("hip", "hips", "hip circumference", "ヒップ", "腰回り"),
    "body_length": ("body length", "torso length", "背丈", "身頃丈"),
    "inseam": ("inseam", "inside leg", "股下"),
    "shoulder": ("shoulder", "shoulder width", "肩幅"),
    "sleeve_length": ("sleeve length", "sleeve", "袖丈"),
    "height": ("height", "stature", "身長"),
    "skirt_length": ("skirt length", "スカート丈"),
    "garment_length": ("garment length", "dress length", "coat length", "着丈"),
    "hem_circumference": ("hem circumference", "hem width", "裾周り", "裾幅"),
    "overlay_height": ("overlay height", "cape length", "オーバーレイ丈", "ケープ丈"),
}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite number")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    raise TypeError(f"non-canonical value: {type(value).__name__}")


def stable_digest(value: Any) -> str:
    payload = json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stop(request: Any, code: str, why: str, **detail: Any) -> Dict[str, Any]:
    result = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "STOPPED",
        "reason_code": code,
        "why": why,
        "how_to_close": "supply typed requirements with explicit units and specific targets",
        "primitive_overrides": {},
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        **copy.deepcopy(detail),
    }
    try:
        result["input_digest"] = stable_digest(request)
    except (TypeError, ValueError):
        result["input_digest"] = None
    result["digest"] = stable_digest(result)
    return result


def _normalized_text(value: str) -> str:
    return re.sub(r"[\s_\-:/]+", " ", value.strip().lower())


def _target(raw: str) -> Optional[str]:
    text = _normalized_text(raw)
    matches: List[Tuple[int, str]] = []
    for canonical, aliases in _TARGET_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalized_text(alias)
            if normalized_alias == text or normalized_alias in text:
                matches.append((len(normalized_alias), canonical))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


def _number_cm(row: Mapping[str, Any], location: str) -> float:
    value = row.get("value")
    unit = row.get("unit")
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value))):
        raise ValueError(f"{location}.value must be finite")
    if unit not in _UNITS_TO_CM:
        raise ValueError(f"{location}.unit must be mm, cm, or m")
    value_cm = round(float(value) * _UNITS_TO_CM[str(unit)], 9)
    if value_cm <= 0.0:
        raise ValueError(f"{location}.value must be positive")
    return value_cm


def _dimension(value_cm: float, *sources: str) -> Dict[str, Any]:
    return {
        "value_cm": round(value_cm, 9),
        "unit": "cm",
        "state": "REQUESTED",
        "authority": "USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE",
        "source_requirement_targets": sorted(set(sources)),
        "not_measured_from_image": True,
        "preview_only": True,
    }


def _put(overrides: Dict[str, Dict[str, Any]], primitive: str, field: str,
         record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fields = overrides.setdefault(primitive, {})
    existing = fields.get(field)
    if existing is not None and existing["value_cm"] != record["value_cm"]:
        return {
            "code": "UNKNOWN_CONFLICTING_REQUIREMENT_DIMENSIONS",
            "primitive": primitive,
            "field": field,
            "existing": existing,
            "supplied": record,
        }
    fields[field] = record
    return None


def compile_profile(request: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(request, Mapping):
        return _stop(request, "UNKNOWN_REQUIREMENT_PROFILE_REQUEST",
                     "request must be an object")
    try:
        canonical = _plain(request)
        input_digest = stable_digest(canonical)
    except (TypeError, ValueError) as exc:
        return _stop({}, "UNKNOWN_NON_CANONICAL_REQUIREMENTS", str(exc))
    if canonical.get("schema") != REQUEST_SCHEMA:
        return _stop(canonical, "UNKNOWN_REQUIREMENT_PROFILE_SCHEMA",
                     f"expected {REQUEST_SCHEMA}")
    rows = canonical.get("requirements")
    if (not isinstance(rows, list) or not rows or len(rows) > 24
            or any(not isinstance(row, Mapping) for row in rows)):
        return _stop(canonical, "UNKNOWN_TYPED_REQUIREMENTS_REQUIRED",
                     "requirements must contain 1-24 typed objects")

    normalized: List[Dict[str, Any]] = []
    body: Dict[str, Dict[str, Any]] = {}
    ease: Dict[str, Dict[str, Any]] = {}
    direct: List[Tuple[str, float, str]] = []
    review: List[Dict[str, Any]] = []
    controls: List[Dict[str, Any]] = []

    for index, source in enumerate(rows):
        row = copy.deepcopy(dict(source))
        kind = str(row.get("kind", "")).upper()
        target_text = str(row.get("target", "")).strip()
        if kind not in _KINDS or not target_text:
            return _stop(canonical, "UNKNOWN_TYPED_REQUIREMENT",
                         "each requirement needs a supported kind and target",
                         index=index, supplied_kind=kind)
        has_value = row.get("value") is not None
        has_text = isinstance(row.get("text"), str) and bool(row["text"].strip())
        if not has_value and not has_text:
            return _stop(canonical, "UNKNOWN_REQUIREMENT_VALUE",
                         "each requirement needs text or a numeric value", index=index)
        if has_value and kind not in _DIMENSION_KINDS:
            return _stop(canonical, "UNKNOWN_NUMERIC_NON_DIMENSION_REQUIREMENT",
                         "numeric values are allowed only for typed dimensions",
                         index=index, kind=kind)
        canonical_target = _target(target_text)
        item = {
            "kind": kind,
            "target": target_text,
            "canonical_target": canonical_target,
            "text": row.get("text"),
            "note": row.get("note"),
            "state": "REQUESTED",
        }
        if has_value:
            try:
                item["value_cm"] = _number_cm(row, f"requirements[{index}]")
            except ValueError as exc:
                return _stop(canonical, "UNKNOWN_EXPLICIT_DIMENSION_REQUIRED",
                             str(exc), index=index)
        normalized.append(item)

        if kind == "BODY_MEASUREMENT":
            if canonical_target not in {
                    "chest_bust", "waist", "hip", "body_length", "inseam",
                    "shoulder", "sleeve_length", "height"}:
                review.append({
                    "code": "UNKNOWN_BODY_MEASUREMENT_TARGET",
                    "target": target_text,
                    "why": "the dimension is preserved but cannot address a body field",
                })
            else:
                body[canonical_target] = _dimension(item["value_cm"], target_text)
        elif kind == "EASE":
            if canonical_target not in {"chest_bust", "waist", "hip"}:
                review.append({
                    "code": "UNKNOWN_EASE_TARGET_REQUIRED",
                    "target": target_text,
                    "why": "generic ease is not spread across body regions automatically",
                })
            else:
                ease[canonical_target] = _dimension(item["value_cm"], target_text)
        elif kind in {"GARMENT_MEASUREMENT", "LENGTH"}:
            if canonical_target is None:
                review.append({
                    "code": "UNKNOWN_GARMENT_DIMENSION_TARGET",
                    "target": target_text,
                    "why": "the number is preserved but has no unambiguous primitive field",
                })
            else:
                direct.append((canonical_target, item["value_cm"], target_text))
        else:
            controls.append(item)

    overrides: Dict[str, Dict[str, Any]] = {}
    conflicts: List[Dict[str, Any]] = []

    if "chest_bust" in body:
        value = body["chest_bust"]["value_cm"]
        sources = list(body["chest_bust"]["source_requirement_targets"])
        if "chest_bust" in ease:
            value += ease["chest_bust"]["value_cm"]
            sources += ease["chest_bust"]["source_requirement_targets"]
        conflict = _put(overrides, "BODY_SHELL", "circumference_cm",
                        _dimension(value, *sources))
        if conflict:
            conflicts.append(conflict)
    if "body_length" in body:
        conflict = _put(overrides, "BODY_SHELL", "height_cm",
                        copy.deepcopy(body["body_length"]))
        if conflict:
            conflicts.append(conflict)
    if "sleeve_length" in body:
        conflict = _put(overrides, "SLEEVE", "length_cm",
                        copy.deepcopy(body["sleeve_length"]))
        if conflict:
            conflicts.append(conflict)
    if "inseam" in body:
        conflict = _put(overrides, "TUBE", "length_cm",
                        copy.deepcopy(body["inseam"]))
        if conflict:
            conflicts.append(conflict)
    if "waist" in body:
        value = body["waist"]["value_cm"]
        sources = list(body["waist"]["source_requirement_targets"])
        if "waist" in ease:
            value += ease["waist"]["value_cm"]
            sources += ease["waist"]["source_requirement_targets"]
        for primitive, field in (("FLARE", "top_circumference_cm"),
                                 ("FRUSTUM", "top_circumference_cm"),
                                 ("BAND", "length_cm")):
            conflict = _put(overrides, primitive, field,
                            _dimension(value, *sources))
            if conflict:
                conflicts.append(conflict)

    direct_map = {
        "body_length": (("BODY_SHELL", "height_cm"),),
        "sleeve_length": (("SLEEVE", "length_cm"),),
        "inseam": (("TUBE", "length_cm"),),
        "skirt_length": (("FLARE", "height_cm"), ("FRUSTUM", "height_cm")),
        "garment_length": (("BODY_SHELL", "height_cm"),),
        "hem_circumference": (("FLARE", "bottom_circumference_cm"),
                              ("FRUSTUM", "bottom_circumference_cm")),
        "overlay_height": (("OVERLAY", "height_cm"),),
    }
    for target_name, value, source_target in direct:
        addresses = direct_map.get(target_name)
        if not addresses:
            review.append({
                "code": "UNKNOWN_GARMENT_DIMENSION_TARGET",
                "target": source_target,
                "why": "the target has no safe direct primitive address",
            })
            continue
        for primitive, field in addresses:
            conflict = _put(overrides, primitive, field,
                            _dimension(value, source_target))
            if conflict:
                conflicts.append(conflict)
    if conflicts:
        return _stop(canonical, "UNKNOWN_CONFLICTING_REQUIREMENT_DIMENSIONS",
                     "two requirements assign different values to one primitive field",
                     conflicts=conflicts)

    standard_sizes = [row for row in controls if row["kind"] == "STANDARD_SIZE"]
    if standard_sizes:
        review.append({
            "code": "UNKNOWN_STANDARD_SIZE_CHART_REQUIRED",
            "targets": [row["target"] for row in standard_sizes],
            "why": "a label such as M cannot create body dimensions until a named size chart is selected",
        })

    result = {
        "schema": SCHEMA,
        "verdict": "REVIEW" if review else "PROPOSED",
        "state": "PREVIEW_PROFILE_READY",
        "input_digest": input_digest,
        "requirements": normalized,
        "body_measurement_requests": body,
        "ease_requests": ease,
        "non_geometric_controls": controls,
        "primitive_overrides": {
            primitive: {field: fields[field] for field in sorted(fields)}
            for primitive, fields in sorted(overrides.items())
        },
        "review_items": review,
        "claims": {
            "natural_language_parsed_here": False,
            "front_image_measured": False,
            "standard_size_expanded_without_chart": False,
            "generic_ease_auto_distributed": False,
            "user_dimension_treated_as_measured_fact": False,
        },
        "preview_only": True,
        "requires_measurement_source_before_manufacturing": bool(body),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["profile_digest"] = stable_digest(result)
    return result


__all__ = ["REQUEST_SCHEMA", "SCHEMA", "compile_profile", "stable_digest"]
