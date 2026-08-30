# -*- coding: utf-8 -*-
"""Deterministic image-relative preview-avatar fitting.

This module bridges the typed output of :mod:`body_image_separation` to the
``base_avatar`` and front target required by :mod:`same_camera_projection`.
It deliberately solves only a bounded preview problem:

* image pixels choose a 2D scale, translation, and pose-anchor placement;
* user-requested or independently measured values may rank ten fixed preview
  profiles;
* a dimension changes between profiles only when the request explicitly lists
  that dimension in ``interpolation.allowed_dimensions``;
* hidden body shape and every rear surface stay UNKNOWN/PROPOSED.

No silhouette width, pose distance, or pixel scale is converted into a body
measurement.  The selected avatar is a rendering/control surface, not an
assertion about the photographed person and not a manufacturing gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Tuple


REQUEST_SCHEMA = "garment.body-avatar-fit.request.v1"
SCHEMA = "garment.body-avatar-fit.v1"
PROFILE_SCHEMA = "garment.preview-avatar-profile.v1"
SAME_CAMERA_REQUEST_SCHEMA = "garment.same-camera-projection.request.v1"

_DIMENSIONS = (
    "height", "chest_bust", "waist", "hip", "shoulder",
    "body_length", "inseam",
)
_ALIASES = {
    "height": "height",
    "chest": "chest_bust",
    "bust": "chest_bust",
    "chest_bust": "chest_bust",
    "waist": "waist",
    "hip": "hip",
    "shoulder": "shoulder",
    "body_length": "body_length",
    "inseam": "inseam",
}
_SANITY_LIMITS_CM = {
    "height": (120.0, 220.0),
    "chest_bust": (50.0, 160.0),
    "waist": (45.0, 150.0),
    "hip": (55.0, 170.0),
    "shoulder": (25.0, 65.0),
    "body_length": (25.0, 80.0),
    "inseam": (45.0, 120.0),
}
_DIRECT_MEASUREMENT_SOURCES = {
    "TAPE_MEASURE", "BODY_SCAN", "CLINICAL_MEASURE",
    "MANUAL_PATTERN_MEASURE", "USER_ENTERED_MEASURED",
}
_IMAGE_DERIVED_SOURCES = {
    "CLOTHED_PHOTO", "GARMENT_PHOTO", "FRONT_IMAGE_ESTIMATE",
    "POSE_ESTIMATE", "MASK_ESTIMATE", "MODEL_ESTIMATE", "PIXELS",
}
_EVIDENCE_AUTHORITIES = {
    "UNKNOWN", "UNOBSERVED", "PROPOSED", "MODEL_PROPOSED", "INFERRED",
    "OBSERVED", "HUMAN_CONFIRMED",
}
_FOREGROUND_CLASSES = {"BODY", "GARMENT", "HAIR"}
_EPSILON = 1.0e-9


# These are bounded preview controls, not demographic classes or population
# estimates.  Their values intentionally cover a compact, inspectable set.
_PROFILE_ROWS: Tuple[Tuple[str, str, Tuple[float, ...]], ...] = (
    ("preview-balanced-170", "BALANCED_170",
     (170.0, 92.0, 76.0, 98.0, 41.0, 45.0, 79.0)),
    ("preview-compact-narrow-158", "COMPACT_NARROW_158",
     (158.0, 82.0, 66.0, 88.0, 37.0, 40.0, 72.0)),
    ("preview-compact-balanced-162", "COMPACT_BALANCED_162",
     (162.0, 88.0, 72.0, 94.0, 39.0, 42.0, 74.0)),
    ("preview-compact-broad-164", "COMPACT_BROAD_164",
     (164.0, 100.0, 84.0, 106.0, 43.0, 43.0, 75.0)),
    ("preview-standard-narrow-168", "STANDARD_NARROW_168",
     (168.0, 84.0, 68.0, 90.0, 38.0, 44.0, 78.0)),
    ("preview-standard-broad-172", "STANDARD_BROAD_172",
     (172.0, 104.0, 88.0, 110.0, 45.0, 46.0, 80.0)),
    ("preview-long-torso-174", "LONG_TORSO_174",
     (174.0, 94.0, 78.0, 100.0, 42.0, 51.0, 78.0)),
    ("preview-tall-narrow-178", "TALL_NARROW_178",
     (178.0, 88.0, 72.0, 94.0, 40.0, 47.0, 84.0)),
    ("preview-tall-balanced-180", "TALL_BALANCED_180",
     (180.0, 98.0, 80.0, 104.0, 43.0, 49.0, 85.0)),
    ("preview-tall-broad-182", "TALL_BROAD_182",
     (182.0, 110.0, 94.0, 116.0, 47.0, 50.0, 86.0)),
)


class _FitError(ValueError):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if _sequence(value):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def stable_digest(value: Any) -> str:
    payload = json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _refusal(request: Any, code: str, why: str, **detail: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNKNOWN",
        "why": why,
        "hidden_body_state": "UNKNOWN_UNOBSERVED",
        "rear_state": "UNKNOWN_UNOBSERVED",
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        "claims": {
            "body_measurements_inferred_from_pixels": False,
            "rear_observed": False,
        },
        **copy.deepcopy(detail),
    }
    try:
        result["input_digest"] = stable_digest(request)
    except (TypeError, ValueError):
        result["input_digest"] = None
    result["contract_digest"] = stable_digest(result)
    return result


def _finite(value: Any, *, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_NON_FINITE",
            "numeric evidence must contain finite numbers",
            location=location,
        )
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_NON_FINITE",
            "numeric evidence must contain finite numbers",
            location=location,
        )
    return parsed


def _nonempty(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_IDENTIFIER",
            "typed identifiers must be non-empty strings",
            location=location,
        )
    return value.strip()


def _profiles() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for priority, (profile_id, label, values) in enumerate(_PROFILE_ROWS):
        dimensions = {
            name: values[index] for index, name in enumerate(_DIMENSIONS)
        }
        profile = {
            "schema": PROFILE_SCHEMA,
            "profile_id": profile_id,
            "label": label,
            "catalog_priority": priority,
            "authority": "PROPOSED_PREVIEW",
            "dimensions_cm": dimensions,
            "bounded_preview_only": True,
            "not_a_target_wearer_measurement": True,
        }
        profile["profile_digest"] = stable_digest(profile)
        result.append(profile)
    return result


PREVIEW_AVATAR_PROFILES = tuple(_profiles())
PROFILE_CATALOG_DIGEST = stable_digest(PREVIEW_AVATAR_PROFILES)


def _canonical_dimension(raw: Any, *, location: str) -> str:
    if not isinstance(raw, str) or raw not in _ALIASES:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_DIMENSION",
            "requested dimensions must use the closed preview vocabulary",
            location=location, supplied=copy.deepcopy(raw),
            supported=sorted(_ALIASES),
        )
    return _ALIASES[raw]


def _insert_requested(
    destination: Dict[str, Dict[str, Any]], name: str, record: Dict[str, Any],
) -> None:
    existing = destination.get(name)
    if existing is not None and existing != record:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_CONFLICTING_DIMENSIONS",
            "duplicate or aliased requested dimensions conflict",
            dimension=name,
        )
    destination[name] = record


def _requested_record(raw: Any, *, name: str, location: str) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        unit = raw.get("unit", "cm" if "value_cm" in raw else None)
        value = raw.get("value_cm", raw.get("value"))
        authority = str(raw.get("authority", "REQUESTED")).upper()
        source_raw = raw.get("source")
        source = dict(source_raw) if isinstance(source_raw, Mapping) else {}
    else:
        unit, value, authority, source = "cm", raw, "REQUESTED", {}
    if unit not in {"cm", "m"}:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_DIMENSION_UNIT",
            "requested dimensions require an explicit cm or m unit",
            location=location,
        )
    parsed = _finite(value, location=location + ".value")
    value_cm = parsed * 100.0 if unit == "m" else parsed
    value_cm = round(value_cm, 8)
    low, high = _SANITY_LIMITS_CM[name]
    if not low <= value_cm <= high:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_DIMENSION_OUT_OF_BOUNDS",
            "requested dimension is outside broad preview sanity bounds",
            location=location, value_cm=value_cm,
            allowed_range_cm=[low, high],
        )
    if authority not in {"REQUESTED", "MEASURED"}:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_DIMENSION_AUTHORITY",
            "dimension authority must be REQUESTED or independently MEASURED",
            location=location, supplied_authority=authority,
        )
    source_kind = str(source.get(
        "kind", "USER_REQUEST" if authority == "REQUESTED" else "UNKNOWN"
    )).upper()
    if source_kind in _IMAGE_DERIVED_SOURCES:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_PIXEL_MEASUREMENT_REFUSED",
            "a front image may position a preview but cannot supply body measurements",
            location=location, supplied_source_kind=source_kind,
        )
    if authority == "MEASURED" and source_kind not in _DIRECT_MEASUREMENT_SOURCES:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_MEASUREMENT_SOURCE",
            "MEASURED values require an independent tape, scan, clinical, pattern, or user-measured source",
            location=location, supplied_source_kind=source_kind,
        )
    reference = source.get("reference")
    if authority == "MEASURED" and (
            not isinstance(reference, str) or not reference.strip()):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_MEASUREMENT_SOURCE",
            "MEASURED values require source.reference",
            location=location,
        )
    return {
        "dimension": name,
        "value_cm": value_cm,
        "authority": authority,
        "source": {
            "kind": source_kind,
            "reference": reference.strip()
                if isinstance(reference, str) and reference.strip() else None,
        },
        "pixel_derived": False,
    }


def _requested_dimensions(request: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    supplied = request.get("requested_measurements")
    if supplied is None:
        supplied = request.get("requested_dimensions")
    if supplied is None:
        supplied = request.get("measurements")
    if supplied is not None:
        if not isinstance(supplied, Mapping):
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_DIMENSIONS",
                "requested_measurements must be a field-keyed object",
            )
        for raw_name in sorted(supplied, key=str):
            name = _canonical_dimension(
                raw_name, location=f"requested_measurements.{raw_name}")
            record = _requested_record(
                supplied[raw_name], name=name,
                location=f"requested_measurements.{raw_name}",
            )
            _insert_requested(result, name, record)

    if "requested_height_cm" in request:
        record = _requested_record(
            request["requested_height_cm"], name="height",
            location="requested_height_cm",
        )
        _insert_requested(result, "height", record)
    if "requested_height" in request:
        record = _requested_record(
            request["requested_height"], name="height",
            location="requested_height",
        )
        _insert_requested(result, "height", record)

    wearer = request.get("wearer_measurement_contract")
    if wearer is not None:
        if not isinstance(wearer, Mapping):
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_WEARER_CONTRACT",
                "wearer_measurement_contract must be a typed object",
            )
        target = wearer.get("target_wearer")
        measurements = target.get("measurements") if isinstance(target, Mapping) else None
        if wearer.get("gate_status") == "READY" and isinstance(measurements, Mapping):
            for raw_name in sorted(measurements, key=str):
                # The wearer contract also carries dimensions (for example
                # sleeve length) that this bounded torso/leg preview catalog
                # does not control.  They remain in the wearer contract for
                # downstream pattern work and are not silently mapped here.
                if raw_name not in _ALIASES:
                    continue
                name = _canonical_dimension(
                    raw_name,
                    location=f"wearer_measurement_contract.{raw_name}",
                )
                record = _requested_record(
                    measurements[raw_name], name=name,
                    location=f"wearer_measurement_contract.{raw_name}",
                )
                _insert_requested(result, name, record)
    return {name: result[name] for name in sorted(result)}


def _allowed_interpolation(request: Mapping[str, Any]) -> List[str]:
    raw = request.get("interpolation")
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_INTERPOLATION",
            "interpolation must be a typed object",
        )
    method = str(raw.get("method", "LINEAR_BOUNDED")).upper()
    if method != "LINEAR_BOUNDED":
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_INTERPOLATION",
            "only LINEAR_BOUNDED interpolation is supported",
            supplied_method=method,
        )
    supplied = raw.get("allowed_dimensions", [])
    if not _sequence(supplied):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_INTERPOLATION",
            "interpolation.allowed_dimensions must be an array",
        )
    return sorted(set(
        _canonical_dimension(
            item, location="interpolation.allowed_dimensions")
        for item in supplied
    ))


def _rank_profiles(
    requested: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    catalog_ranges = {
        name: (
            min(row["dimensions_cm"][name] for row in PREVIEW_AVATAR_PROFILES),
            max(row["dimensions_cm"][name] for row in PREVIEW_AVATAR_PROFILES),
        )
        for name in _DIMENSIONS
    }
    ranked: List[Dict[str, Any]] = []
    for profile in PREVIEW_AVATAR_PROFILES:
        terms: List[Dict[str, Any]] = []
        for name in sorted(requested):
            minimum, maximum = catalog_ranges[name]
            span = max(maximum - minimum, 1.0)
            difference = abs(
                profile["dimensions_cm"][name] - requested[name]["value_cm"])
            terms.append({
                "dimension": name,
                "absolute_difference_cm": round(difference, 8),
                "catalog_normalized_difference": round(difference / span, 12),
            })
        distance = (
            sum(row["catalog_normalized_difference"] for row in terms)
            / len(terms) if terms else float(profile["catalog_priority"])
        )
        ranked.append({
            "profile_id": profile["profile_id"],
            "profile_digest": profile["profile_digest"],
            "label": profile["label"],
            "authority": "PROPOSED_PREVIEW",
            "dimensions_cm": copy.deepcopy(profile["dimensions_cm"]),
            "ranking_distance": round(distance, 12),
            "ranking_terms": terms,
            "ranking_is_correctness_probability": False,
        })
    ranked.sort(key=lambda row: (
        row["ranking_distance"], row["profile_id"]))
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked


def _interpolate_selected(
    selected: Mapping[str, Any], requested: Mapping[str, Mapping[str, Any]],
    allowed: Sequence[str],
) -> Tuple[Dict[str, float], List[Dict[str, Any]], List[str]]:
    dimensions = copy.deepcopy(dict(selected["dimensions_cm"]))
    operations: List[Dict[str, Any]] = []
    for name in allowed:
        if name not in requested:
            continue
        value = requested[name]["value_cm"]
        values = sorted(set(
            float(row["dimensions_cm"][name])
            for row in PREVIEW_AVATAR_PROFILES
        ))
        if value < values[0] - _EPSILON or value > values[-1] + _EPSILON:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_INTERPOLATION_OUT_OF_BOUNDS",
                "explicit interpolation stays within the preview profile catalog",
                dimension=name, requested_value_cm=value,
                catalog_range_cm=[values[0], values[-1]],
            )
        lower = max(item for item in values if item <= value + _EPSILON)
        upper = min(item for item in values if item >= value - _EPSILON)
        fraction = 0.0 if abs(upper - lower) <= _EPSILON else (
            (value - lower) / (upper - lower))
        dimensions[name] = round(value, 8)
        operations.append({
            "dimension": name,
            "lower_cm": lower,
            "upper_cm": upper,
            "fraction": round(fraction, 12),
            "result_cm": round(value, 8),
            "input_authority": requested[name]["authority"],
            "authority": "PROPOSED_PREVIEW_GEOMETRY_CONTROL",
            "explicitly_allowed": True,
        })
    unapplied = sorted(set(requested) - set(allowed))
    return dimensions, operations, unapplied


def _unwrap_separation(
    request: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    raw = request.get("separation", request.get("front_evidence"))
    if not isinstance(raw, Mapping):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_SEPARATION_REQUIRED",
            "typed front separation evidence is required",
        )
    outer = raw
    if isinstance(raw.get("separation"), Mapping):
        raw = raw["separation"]
    candidates = raw.get("candidates")
    if _sequence(candidates) and candidates:
        if any(not isinstance(row, Mapping) for row in candidates):
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_SEPARATION",
                "separation candidates must be typed objects",
            )
        requested_id = request.get(
            "separation_candidate_id", request.get("selected_candidate_id"))
        if requested_id is None and isinstance(raw.get("selection"), Mapping):
            requested_id = raw["selection"].get("selected_candidate_id")
        ordered = sorted(candidates, key=lambda row: (
            int(row.get("policy_rank", 0))
                if isinstance(row.get("policy_rank", 0), int) else 0,
            str(row.get("candidate_id", "")),
        ))
        if requested_id is None:
            candidate = ordered[0]
        else:
            matches = [row for row in ordered
                       if row.get("candidate_id") == requested_id]
            if not matches:
                raise _FitError(
                    "UNKNOWN_BODY_AVATAR_FIT_SEPARATION_CANDIDATE",
                    "selected separation candidate id was not found",
                    selected_candidate_id=requested_id,
                )
            candidate = matches[0]
    elif any(key in raw for key in ("pose_keypoints", "masks", "camera")):
        candidate = raw
    else:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_SEPARATION",
            "separation must contain candidates or typed front evidence",
        )
    return candidate, raw, outer


def _source(
    request: Mapping[str, Any], separation: Mapping[str, Any],
    outer: Mapping[str, Any], candidate: Mapping[str, Any],
) -> Dict[str, Any]:
    possibilities: List[Any] = [request.get("source"), separation.get("source")]
    adapter = outer.get("adapter")
    if isinstance(adapter, Mapping):
        possibilities.append(adapter.get("source"))
    selected = next((row for row in possibilities if isinstance(row, Mapping)), None)
    selected = dict(selected or {})
    camera = candidate.get("camera")
    camera = camera if isinstance(camera, Mapping) else {}
    digest = selected.get("image_digest", request.get("source_image_digest"))
    if not isinstance(digest, str) or not digest.strip():
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_SOURCE_REQUIRED",
            "source.image_digest is required",
        )
    width_raw = selected.get("width", selected.get(
        "width_px", camera.get("width_px")))
    height_raw = selected.get("height", selected.get(
        "height_px", camera.get("height_px")))
    width = _finite(width_raw, location="source.width")
    height = _finite(height_raw, location="source.height")
    if width <= 0.0 or height <= 0.0:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_SOURCE_REQUIRED",
            "source image dimensions must be positive",
        )
    return {
        "image_digest": digest.strip(),
        "width_px": round(width, 8),
        "height_px": round(height, 8),
        "orientation": str(selected.get("orientation", "UP")).upper(),
        "aspect": (
            "PORTRAIT" if height > width else
            "LANDSCAPE" if width > height else "SQUARE"
        ),
    }


def _coordinate_space(
    request: Mapping[str, Any], candidate: Mapping[str, Any],
) -> str:
    raw = request.get(
        "evidence_coordinate_space", candidate.get("coordinate_space", "NORMALIZED"))
    result = str(raw).upper()
    aliases = {
        "NORMALIZED_IMAGE": "NORMALIZED",
        "NORMALISED": "NORMALIZED",
        "PIXEL": "PIXELS",
    }
    result = aliases.get(result, result)
    if result not in {"NORMALIZED", "PIXELS"}:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_COORDINATE_SPACE",
            "front evidence coordinate space must be NORMALIZED or PIXELS",
            supplied=result,
        )
    return result


def _point_xy(raw: Any, *, location: str) -> Tuple[float, float]:
    if isinstance(raw, Mapping):
        if "point" in raw:
            return _point_xy(raw["point"], location=location)
        x, y = raw.get("x"), raw.get("y")
    elif _sequence(raw) and len(raw) >= 2:
        x, y = raw[0], raw[1]
    else:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_POINT",
            "2D evidence points need x and y",
            location=location,
        )
    return (
        _finite(x, location=location + ".x"),
        _finite(y, location=location + ".y"),
    )


def _to_pixels(
    raw: Any, *, location: str, coordinate_space: str,
    source: Mapping[str, Any],
) -> List[float]:
    x, y = _point_xy(raw, location=location)
    if coordinate_space == "NORMALIZED":
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_POINT_RANGE",
                "normalised points must be within 0..1",
                location=location,
            )
        x *= source["width_px"]
        y *= source["height_px"]
    elif (not 0.0 <= x <= source["width_px"]
          or not 0.0 <= y <= source["height_px"]):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_POINT_RANGE",
            "pixel points must lie within the source frame",
            location=location,
        )
    return [round(x, 8), round(y, 8)]


def _authority(raw: Any) -> str:
    result = str(raw if raw is not None else "PROPOSED").upper()
    if result not in _EVIDENCE_AUTHORITIES:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_EVIDENCE_AUTHORITY",
            "front evidence authority is outside the typed vocabulary",
            supplied=result,
        )
    return result


def _pose(
    candidate: Mapping[str, Any], *, coordinate_space: str,
    source: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    raw = candidate.get("pose_keypoints", candidate.get("pose_keypoints_2d", []))
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        rows = [(str(name), value) for name, value in raw.items()]
    elif _sequence(raw):
        rows = []
        for index, value in enumerate(raw):
            if not isinstance(value, Mapping):
                raise _FitError(
                    "UNKNOWN_BODY_AVATAR_FIT_POSE",
                    "pose entries must be typed objects",
                    location=f"pose[{index}]",
                )
            rows.append((_nonempty(
                value.get("name", value.get("id")),
                location=f"pose[{index}].name",
            ), value))
    else:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_POSE",
            "pose_keypoints must be a mapping or array",
        )
    result: List[Dict[str, Any]] = []
    seen = set()
    for name, value in sorted(rows, key=lambda row: row[0]):
        canonical = name.strip().lower().replace("-", "_").replace(" ", "_")
        if canonical in seen:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_DUPLICATE_POSE",
                "pose keypoint names must be unique",
                keypoint=canonical,
            )
        seen.add(canonical)
        confidence = _finite(
            value.get("confidence", 1.0) if isinstance(value, Mapping) else 1.0,
            location=f"pose.{canonical}.confidence",
        )
        if not 0.0 <= confidence <= 1.0:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_CONFIDENCE",
                "pose confidence must be within 0..1",
                keypoint=canonical,
            )
        result.append({
            "name": canonical,
            "point_px": _to_pixels(
                value, location=f"pose.{canonical}",
                coordinate_space=coordinate_space, source=source,
            ),
            "confidence": round(confidence, 8),
            "input_authority": _authority(
                value.get("authority", value.get("state", "PROPOSED"))
                if isinstance(value, Mapping) else "PROPOSED"),
            "fit_authority": "PROPOSED_IMAGE_RELATIVE_ANCHOR",
        })
    return result


def _masks(
    candidate: Mapping[str, Any], *, coordinate_space: str,
    source: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    raw = candidate.get("masks", candidate.get("mask_candidates", []))
    if raw is None:
        return []
    if not _sequence(raw):
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_MASKS",
            "masks must be an array",
        )
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_MASKS",
                "mask entries must be typed objects",
                location=f"masks[{index}]",
            )
        mask_id = _nonempty(
            value.get("mask_id", value.get("candidate_id", value.get("id"))),
            location=f"masks[{index}].mask_id",
        )
        if mask_id in seen:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_DUPLICATE_MASK",
                "mask ids must be unique",
                mask_id=mask_id,
            )
        seen.add(mask_id)
        mask_class = str(value.get("class", value.get("kind", ""))).upper()
        if mask_class not in {"BODY", "GARMENT", "HAIR", "BACKGROUND"}:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_MASK_CLASS",
                "mask class must be BODY, GARMENT, HAIR, or BACKGROUND",
                mask_id=mask_id,
            )
        outline_raw = value.get("outline", [])
        if outline_raw is None:
            outline_raw = []
        if not _sequence(outline_raw):
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_MASKS",
                "mask outline must be an array",
                mask_id=mask_id,
            )
        outline = [
            _to_pixels(
                point, location=f"masks.{mask_id}[{point_index}]",
                coordinate_space=coordinate_space, source=source,
            )
            for point_index, point in enumerate(outline_raw)
        ]
        if outline and len(outline) < 3:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_MASKS",
                "a non-empty mask outline needs at least three points",
                mask_id=mask_id,
            )
        layer = value.get("layer")
        if layer is not None and (
                isinstance(layer, bool) or not isinstance(layer, int)):
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_LAYER",
                "garment mask layer must be an integer or null",
                mask_id=mask_id,
            )
        confidence = _finite(
            value.get("confidence", 1.0),
            location=f"masks.{mask_id}.confidence",
        )
        if not 0.0 <= confidence <= 1.0:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_CONFIDENCE",
                "mask confidence must be within 0..1",
                mask_id=mask_id,
            )
        result.append({
            "mask_id": mask_id,
            "class": mask_class,
            "garment_unit_id": value.get("garment_unit_id"),
            "layer": layer,
            "confidence": round(confidence, 8),
            "authority": _authority(
                value.get("authority", value.get("state", "PROPOSED"))),
            "mask_digest": value.get("mask_digest"),
            "outline_px": outline,
        })
    return sorted(result, key=lambda row: (
        row["class"],
        row["layer"] if isinstance(row["layer"], int) else -1,
        str(row["garment_unit_id"] or ""), row["mask_id"],
    ))


def _cross(origin: Tuple[float, float], left: Tuple[float, float],
           right: Tuple[float, float]) -> float:
    return ((left[0] - origin[0]) * (right[1] - origin[1])
            - (left[1] - origin[1]) * (right[0] - origin[0]))


def _convex_hull(points: Iterable[Sequence[float]]) -> List[List[float]]:
    unique = sorted(set((round(float(row[0]), 8), round(float(row[1]), 8))
                        for row in points))
    if len(unique) < 3:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_SILHOUETTE",
            "front silhouette needs at least three distinct points",
        )
    lower: List[Tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: List[Tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_SILHOUETTE",
            "front silhouette is degenerate",
        )
    return [[point[0], point[1]] for point in hull]


def _bbox(points: Sequence[Sequence[float]]) -> Dict[str, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    result = {
        "minimum_x": round(min(xs), 8),
        "minimum_y": round(min(ys), 8),
        "maximum_x": round(max(xs), 8),
        "maximum_y": round(max(ys), 8),
    }
    result["width"] = round(result["maximum_x"] - result["minimum_x"], 8)
    result["height"] = round(result["maximum_y"] - result["minimum_y"], 8)
    if result["width"] <= _EPSILON or result["height"] <= _EPSILON:
        raise _FitError(
            "UNKNOWN_BODY_AVATAR_FIT_SILHOUETTE",
            "front evidence has a degenerate image-relative extent",
        )
    return result


def _subject_envelope(
    masks: Sequence[Mapping[str, Any]], pose: Sequence[Mapping[str, Any]],
    source: Mapping[str, Any],
) -> Tuple[List[List[float]], Dict[str, float], str, List[str]]:
    contributing = [row for row in masks
                    if row["class"] in _FOREGROUND_CLASSES
                    and len(row["outline_px"]) >= 3]
    if contributing:
        hull = _convex_hull(
            point for row in contributing for point in row["outline_px"])
        return (
            hull, _bbox(hull), "VISIBLE_FOREGROUND_SILHOUETTE_ENVELOPE",
            [row["mask_id"] for row in contributing],
        )
    if len(pose) >= 3:
        points = [row["point_px"] for row in pose]
        bounds = _bbox(points)
        pad_x = max(bounds["width"] * 0.12, bounds["height"] * 0.04)
        pad_y = bounds["height"] * 0.04
        rectangle = [
            [max(0.0, bounds["minimum_x"] - pad_x),
             max(0.0, bounds["minimum_y"] - pad_y)],
            [min(source["width_px"], bounds["maximum_x"] + pad_x),
             max(0.0, bounds["minimum_y"] - pad_y)],
            [min(source["width_px"], bounds["maximum_x"] + pad_x),
             min(source["height_px"], bounds["maximum_y"] + pad_y)],
            [max(0.0, bounds["minimum_x"] - pad_x),
             min(source["height_px"], bounds["maximum_y"] + pad_y)],
        ]
        return rectangle, _bbox(rectangle), "POSE_ANCHOR_BOUNDS_ONLY", []
    raise _FitError(
        "UNKNOWN_BODY_AVATAR_FIT_EVIDENCE_REQUIRED",
        "a front silhouette outline or at least three non-degenerate pose anchors is required",
    )


def _midpoint(
    indexed: Mapping[str, Mapping[str, Any]], names: Sequence[str],
) -> Optional[List[float]]:
    points = [indexed[name]["point_px"] for name in names if name in indexed]
    if not points:
        return None
    return [
        round(sum(point[0] for point in points) / len(points), 8),
        round(sum(point[1] for point in points) / len(points), 8),
    ]


def _camera_rotation(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    camera = candidate.get("camera")
    camera = camera if isinstance(camera, Mapping) else {}
    view = str(camera.get("view", camera.get("viewpoint", "UNKNOWN"))).upper()
    yaw_raw = camera.get("yaw_deg")
    if yaw_raw is not None:
        yaw = _finite(yaw_raw, location="camera.yaw_deg")
        basis = "TYPED_CAMERA_YAW"
    else:
        bounded = {
            "FRONT": 0.0,
            "OBLIQUE_LEFT": -30.0,
            "OBLIQUE_RIGHT": 30.0,
            "THREE_QUARTER_LEFT": -35.0,
            "THREE_QUARTER_RIGHT": 35.0,
        }
        yaw = bounded.get(view, 0.0)
        basis = "BOUNDED_VIEW_LABEL_PREVIEW_ASSUMPTION"
    pitch = (_finite(camera["pitch_deg"], location="camera.pitch_deg")
             if "pitch_deg" in camera else 0.0)
    roll = (_finite(camera["roll_deg"], location="camera.roll_deg")
            if "roll_deg" in camera else 0.0)
    return {
        "view": view,
        "yaw_deg": round(yaw, 8),
        "pitch_deg": round(pitch, 8),
        "roll_deg": round(roll, 8),
        "basis": basis,
        "authority": "PROPOSED_IMAGE_RELATIVE_POSE",
        "does_not_observe_rear": True,
    }


def _image_fit(
    selected_avatar: Mapping[str, Any], subject_outline: Sequence[Sequence[float]],
    subject_bbox: Mapping[str, float], pose: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any], source: Mapping[str, Any], basis: str,
    mask_ids: Sequence[str],
) -> Dict[str, Any]:
    indexed = {row["name"]: row for row in pose}
    shoulder = _midpoint(indexed, ("left_shoulder", "right_shoulder"))
    pelvis = _midpoint(indexed, ("left_hip", "right_hip"))
    ankles = _midpoint(indexed, (
        "left_ankle", "right_ankle", "left_foot", "right_foot"))
    center_x = (
        shoulder[0] if shoulder is not None else
        pelvis[0] if pelvis is not None else
        (subject_bbox["minimum_x"] + subject_bbox["maximum_x"]) * 0.5
    )
    root_y = (ankles[1] if ankles is not None
              else subject_bbox["maximum_y"])
    top_y = subject_bbox["minimum_y"]
    fitted_height_px = max(root_y - top_y, subject_bbox["height"])
    avatar_height_cm = selected_avatar["dimensions_cm"]["height"]
    scale = fitted_height_px / avatar_height_cm
    translation = [round(center_x, 8), round(root_y, 8)]
    anchors = [{
        "name": row["name"],
        "image_point_px": copy.deepcopy(row["point_px"]),
        "offset_from_avatar_root_px": [
            round(row["point_px"][0] - translation[0], 8),
            round(row["point_px"][1] - translation[1], 8),
        ],
        "confidence": row["confidence"],
        "input_authority": row["input_authority"],
        "authority": "PROPOSED_IMAGE_RELATIVE_ANCHOR",
    } for row in pose]
    result: Dict[str, Any] = {
        "state": "PROPOSED_IMAGE_RELATIVE_AVATAR_FIT",
        "authority": "PROPOSED_PREVIEW",
        "basis": basis,
        "source_foreground_mask_ids": list(mask_ids),
        "subject_outline_px": copy.deepcopy(list(subject_outline)),
        "subject_bbox_px": copy.deepcopy(dict(subject_bbox)),
        "pose_anchors": anchors,
        "semantic_anchors_px": {
            "shoulder_center": shoulder,
            "pelvis_center": pelvis,
            "ankle_or_foot_center": ankles,
        },
        "world_to_image": {
            "avatar_axes": "X_RIGHT_Y_UP_Z_TOWARD_CAMERA",
            "image_axes": "X_RIGHT_Y_DOWN",
            "uniform_scale_px_per_preview_cm": round(scale, 12),
            "translation_px_for_avatar_origin": translation,
            "formula": {
                "x_px": "translation_x + x_cm * scale",
                "y_px": "translation_y - y_cm * scale",
            },
            "uniform_scale_preserves_preview_profile": True,
        },
        "preview_rotation": _camera_rotation(candidate),
        "source_frame": copy.deepcopy(dict(source)),
        "does_not_observe": [
            "actual wearer height or circumference",
            "body surface hidden by clothing",
            "body depth",
            "rear body or rear garment",
        ],
        "pixel_fit_changes_avatar_measurements": False,
    }
    result["fit_digest"] = stable_digest(result)
    return result


def _projection_state(authorities: Sequence[str], human_edit_digest: Any) -> str:
    if authorities and all(value == "OBSERVED" for value in authorities):
        return "OBSERVED"
    if (authorities
            and all(value in {"OBSERVED", "HUMAN_CONFIRMED"}
                    for value in authorities)
            and isinstance(human_edit_digest, str)
            and human_edit_digest.strip()):
        return "HUMAN_CONFIRMED_TARGET"
    return "PROPOSED"


def _projection_targets(
    masks: Sequence[Mapping[str, Any]], request: Mapping[str, Any],
    source: Mapping[str, Any], camera_digest: str,
    selected_avatar: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
    garments = [row for row in masks
                if row["class"] == "GARMENT" and len(row["outline_px"]) >= 3]
    components: List[Dict[str, Any]] = []
    human_edit_digest = request.get("human_edit_digest")
    for row in garments:
        state = _projection_state([row["authority"]], human_edit_digest)
        target: Dict[str, Any] = {
            "target_digest": stable_digest({
                "mask_id": row["mask_id"],
                "outline_px": row["outline_px"],
                "source": source["image_digest"],
            }),
            "state": state,
            "width_px": source["width_px"],
            "height_px": source["height_px"],
            "outline": copy.deepcopy(row["outline_px"]),
            "mask_id": row["mask_id"],
            "garment_unit_id": row["garment_unit_id"],
            "layer": row["layer"],
            "input_authority": row["authority"],
        }
        if state == "HUMAN_CONFIRMED_TARGET":
            target["human_edit_digest"] = human_edit_digest.strip()
        components.append(target)

    selected_ids_raw = request.get("projection_target_mask_ids")
    if selected_ids_raw is None:
        selected_ids = [row["mask_id"] for row in garments]
    else:
        if not _sequence(selected_ids_raw) or not selected_ids_raw:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_PROJECTION_TARGET",
                "projection_target_mask_ids must be a non-empty array",
            )
        selected_ids = sorted(set(
            _nonempty(item, location="projection_target_mask_ids")
            for item in selected_ids_raw
        ))
        available = {row["mask_id"] for row in garments}
        missing = sorted(set(selected_ids) - available)
        if missing:
            raise _FitError(
                "UNKNOWN_BODY_AVATAR_FIT_PROJECTION_TARGET",
                "selected garment mask has no front outline",
                missing_mask_ids=missing,
            )
    selected_rows = [row for row in garments if row["mask_id"] in selected_ids]
    target: Optional[Dict[str, Any]] = None
    ready = False
    if selected_rows:
        hull = _convex_hull(
            point for row in selected_rows for point in row["outline_px"])
        state = _projection_state(
            [row["authority"] for row in selected_rows], human_edit_digest)
        target = {
            "target_digest": stable_digest({
                "mask_ids": selected_ids,
                "outline_px": hull,
                "source": source["image_digest"],
            }),
            "state": state,
            "width_px": source["width_px"],
            "height_px": source["height_px"],
            "outline": hull,
            "component_mask_ids": selected_ids,
            "target_role": "VISIBLE_FRONT_GARMENT_ENSEMBLE",
            "convex_envelope_is_not_part_segmentation": True,
        }
        if state == "HUMAN_CONFIRMED_TARGET":
            target["human_edit_digest"] = human_edit_digest.strip()
        ready = state in {"OBSERVED", "HUMAN_CONFIRMED_TARGET"}

    projection: Dict[str, Any] = {
        "schema": SAME_CAMERA_REQUEST_SCHEMA,
        "camera_digest": camera_digest,
        "base_avatar": {
            "avatar_id": selected_avatar["avatar_id"],
            "geometry_digest": selected_avatar["geometry_digest"],
        },
        "projection_contract_status": (
            "READY_FOR_CANDIDATE" if ready else
            "HUMAN_CONFIRMATION_REQUIRED" if target is not None else
            "GARMENT_SILHOUETTE_REQUIRED"
        ),
        "candidate_required": True,
    }
    if target is not None:
        projection["target"] = target
    return components, projection, ready


def fit_body_avatar(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Fit one bounded preview avatar to typed front-image evidence."""
    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            request, "UNKNOWN_BODY_AVATAR_FIT_SCHEMA",
            f"request schema must be {REQUEST_SCHEMA}",
        )
    try:
        candidate, separation, outer = _unwrap_separation(request)
        source = _source(request, separation, outer, candidate)
        coordinate_space = _coordinate_space(request, candidate)
        pose = _pose(
            candidate, coordinate_space=coordinate_space, source=source)
        masks = _masks(
            candidate, coordinate_space=coordinate_space, source=source)
        requested = _requested_dimensions(request)
        allowed = _allowed_interpolation(request)
        ranked = _rank_profiles(requested)
        explicit_profile = request.get("preview_profile_id")
        if explicit_profile is None:
            selected_rank = ranked[0]
            selection_authority = "PROPOSED_PREVIEW"
        else:
            explicit_profile = _nonempty(
                explicit_profile, location="preview_profile_id")
            matches = [row for row in ranked
                       if row["profile_id"] == explicit_profile]
            if not matches:
                raise _FitError(
                    "UNKNOWN_BODY_AVATAR_FIT_PROFILE",
                    "preview_profile_id is outside the bounded catalog",
                    supplied_profile_id=explicit_profile,
                )
            selected_rank = matches[0]
            selection_authority = "REQUESTED_PREVIEW_PROFILE"
        dimensions, interpolation, unapplied = _interpolate_selected(
            selected_rank, requested, allowed)
        avatar_seed = {
            "profile_id": selected_rank["profile_id"],
            "profile_digest": selected_rank["profile_digest"],
            "dimensions_cm": dimensions,
            "interpolation": interpolation,
        }
        geometry_digest = stable_digest(avatar_seed)
        selected_avatar: Dict[str, Any] = {
            "avatar_id": "preview-avatar:" + geometry_digest[:20],
            "geometry_digest": geometry_digest,
            "profile_id": selected_rank["profile_id"],
            "profile_digest": selected_rank["profile_digest"],
            "kind": "BOUNDED_PARAMETRIC_PREVIEW_AVATAR",
            "authority": "PROPOSED_PREVIEW",
            "selection_authority": selection_authority,
            "dimensions_cm": dimensions,
            "dimensions_are_profile_controls": True,
            "not_a_target_wearer_measurement": True,
        }
        subject_outline, subject_bbox, fit_basis, fit_mask_ids = _subject_envelope(
            masks, pose, source)
        image_fit = _image_fit(
            selected_avatar, subject_outline, subject_bbox, pose,
            candidate, source, fit_basis, fit_mask_ids)
        camera = candidate.get("camera")
        camera = camera if isinstance(camera, Mapping) else {}
        supplied_camera_digest = camera.get("camera_digest")
        camera_digest = (
            supplied_camera_digest.strip()
            if isinstance(supplied_camera_digest, str)
            and supplied_camera_digest.strip()
            else "image-frame-camera:" + stable_digest({
                "source": source,
                "view": camera.get("view", camera.get("viewpoint", "UNKNOWN")),
                "orientation": camera.get("orientation", source["orientation"]),
            })
        )
        projection_targets, projection_contract, projection_ready = (
            _projection_targets(
                masks, request, source, camera_digest, selected_avatar))
    except _FitError as exc:
        return _refusal(request, exc.code, exc.why, **exc.detail)
    except (TypeError, ValueError) as exc:
        return _refusal(
            request, "UNKNOWN_BODY_AVATAR_FIT_NON_CANONICAL",
            f"request must contain canonical typed evidence: {exc}",
        )

    selected_candidate_id = candidate.get("candidate_id")
    normalized_evidence = {
        "source": source,
        "coordinate_space": "PIXELS_AFTER_NORMALISATION",
        "pose": pose,
        "masks": masks,
        "camera": copy.deepcopy(candidate.get("camera")),
        "requested_dimensions": requested,
        "allowed_interpolation": allowed,
        "selected_profile_id": selected_rank["profile_id"],
        "projection_target_mask_ids": sorted(
            set(request.get("projection_target_mask_ids", [])))
            if _sequence(request.get("projection_target_mask_ids")) else None,
        "human_edit_digest": request.get("human_edit_digest"),
    }
    input_digest = stable_digest(normalized_evidence)
    separation_digest = separation.get("contract_digest")
    if not isinstance(separation_digest, str) or not separation_digest:
        separation_digest = stable_digest({
            "candidate_id": selected_candidate_id,
            "pose": pose,
            "masks": masks,
            "camera": candidate.get("camera"),
        })
    review_items: List[Dict[str, Any]] = [{
        "code": "REVIEW_HIDDEN_BODY_UNKNOWN",
        "why": "visible front support does not reveal the body under clothing",
    }, {
        "code": "REVIEW_REAR_UNKNOWN",
        "why": "the photographed rear and rear garment structure are unobserved",
    }]
    if image_fit["basis"] == "POSE_ANCHOR_BOUNDS_ONLY":
        review_items.append({
            "code": "REVIEW_SILHOUETTE_REQUIRED",
            "why": "avatar placement used padded pose bounds because no foreground outline was supplied",
        })
    if not projection_ready:
        review_items.append({
            "code": "REVIEW_FRONT_GARMENT_TARGET_CONFIRMATION_REQUIRED",
            "why": "same-camera comparison stays closed until a garment outline is observed or human-confirmed",
        })
    if unapplied:
        review_items.append({
            "code": "REVIEW_REQUESTED_DIMENSIONS_USED_FOR_RANKING_ONLY",
            "dimensions": unapplied,
            "why": "these dimensions were not explicitly allowed to interpolate preview geometry",
        })

    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_IMAGE_RELATIVE_BODY_AVATAR_FIT",
        "state": "PROPOSED",
        "source": source,
        "profile_catalog": {
            "count": len(PREVIEW_AVATAR_PROFILES),
            "catalog_digest": PROFILE_CATALOG_DIGEST,
            "profiles": copy.deepcopy(list(PREVIEW_AVATAR_PROFILES)),
        },
        "profile_ranking": ranked,
        "selection": {
            "selected_profile_id": selected_rank["profile_id"],
            "selected_rank": selected_rank["rank"],
            "authority": selection_authority,
            "human_can_override": True,
            "may_open_manufacturing_gate": False,
        },
        "requested_dimensions": requested,
        "interpolation": {
            "method": "LINEAR_BOUNDED",
            "allowed_dimensions": allowed,
            "operations": interpolation,
            "unapplied_requested_dimensions": unapplied,
            "only_explicit_dimensions_changed": True,
        },
        "selected_avatar": selected_avatar,
        "image_relative_fit": image_fit,
        "garment_projection_targets": projection_targets,
        "front_projection_contract": projection_contract,
        "front_projection_ready": projection_ready,
        "hidden_body": {
            "state": "UNKNOWN_UNOBSERVED",
            "preview_surface_state": "PROPOSED_ONLY",
            "measurements_from_pixels": False,
        },
        "rear": {
            "body_state": "UNKNOWN_UNOBSERVED",
            "garment_state": "UNKNOWN_UNOBSERVED",
            "preview_avatar_rear_state": "PROPOSED_PARAMETRIC",
            "rear_observed": False,
        },
        "provenance": {
            "source_image_digest": source["image_digest"],
            "separation_schema": separation.get("schema"),
            "separation_contract_digest": separation_digest,
            "selected_separation_candidate_id": selected_candidate_id,
            "selected_separation_candidate_digest": candidate.get(
                "candidate_digest"),
            "provider_id": candidate.get("provider_id"),
            "provider_result_digest": candidate.get("provider_result_digest"),
            "profile_catalog_digest": PROFILE_CATALOG_DIGEST,
            "normalised_input_digest": input_digest,
            "image_evidence_used_for": [
                "2D scale", "2D translation", "pose anchors",
                "front projection target",
            ],
            "image_evidence_not_used_for": [
                "body measurements", "hidden body", "rear observation",
            ],
        },
        "review_items": review_items,
        "claims": {
            "body_measurements_inferred_from_pixels": False,
            "selected_profile_is_photographed_body": False,
            "rear_observed": False,
            "fit_or_comfort_proven": False,
        },
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        "input_digest": input_digest,
    }
    result["contract_digest"] = stable_digest(result)
    return result


prepare_body_avatar_fit = fit_body_avatar
fit = fit_body_avatar


__all__ = [
    "REQUEST_SCHEMA", "SCHEMA", "PROFILE_SCHEMA",
    "SAME_CAMERA_REQUEST_SCHEMA", "PREVIEW_AVATAR_PROFILES",
    "PROFILE_CATALOG_DIGEST", "stable_digest", "fit_body_avatar",
    "prepare_body_avatar_fit", "fit",
]
