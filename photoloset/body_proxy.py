# -*- coding: utf-8 -*-
"""Typed, deterministic body-proxy proposals for one clothed photograph.

The proxy is a visual separation and rear-generation constraint, not a body
measurement system.  Direct user measurements and requested target dimensions
remain distinct; pose, exposed skin, masks, and clothed-image estimates never
turn chest or waist values into measured facts.  With no external model this
module emits bounded parametric fallback candidates and explicit uncertainty.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple


REQUEST_SCHEMA = "garment.body-proxy.request.v1"
SCHEMA = "garment.body-proxy.v1"
CANDIDATE_SCHEMA = "garment.body-proxy-candidate.v1"
AUTHORITY = "PROPOSED_BODY_PROXY"

_DIMENSIONS = (
    "height", "chest_bust", "waist", "hip", "shoulder",
    "body_length", "inseam",
)
_ALIASES = {"chest": "chest_bust", "bust": "chest_bust", **{
    name: name for name in _DIMENSIONS
}}
_FALLBACK_RANGES_CM = {
    # Deliberately broad preview bounds, not population norms or predictions.
    "height": (155.0, 185.0),
    "chest_bust": (80.0, 110.0),
    "waist": (64.0, 96.0),
    "hip": (86.0, 116.0),
    "shoulder": (34.0, 48.0),
    "body_length": (38.0, 54.0),
    "inseam": (68.0, 90.0),
}
_SANITY_LIMITS_CM = {
    "height": (30.0, 300.0),
    "chest_bust": (20.0, 300.0),
    "waist": (20.0, 300.0),
    "hip": (20.0, 350.0),
    "shoulder": (5.0, 100.0),
    "body_length": (10.0, 250.0),
    "inseam": (5.0, 180.0),
}
_DIRECT_MEASUREMENT_SOURCES = {
    "TAPE_MEASURE", "BODY_SCAN", "USER_ENTERED_MEASURED",
    "MANUAL_PATTERN_MEASURE", "CLINICAL_MEASURE",
}
_CLOTHED_IMAGE_SOURCES = {
    "CLOTHED_PHOTO", "GARMENT_PHOTO", "FRONT_IMAGE_ESTIMATE",
    "POSE_ESTIMATE", "MODEL_ESTIMATE", "MASK_ESTIMATE",
}
_MODES = {"HUMAN_APPROVAL", "AUTO_PROPOSED"}
_MASK_KINDS = {"BODY", "GARMENT"}
_OBSERVED_STATES = {"OBSERVED", "HUMAN_CONFIRMED"}
_PROPOSED_STATES = {"PROPOSED", "MODEL_PROPOSED", "UNKNOWN"}
_EPSILON = 1.0e-12


class _BodyProxyError(ValueError):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray))


def _finite(value: Any, *, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_NON_FINITE",
            "body proxy numeric values must be finite numbers",
            location=location,
        )
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_NON_FINITE",
            "body proxy numeric values must be finite numbers",
            location=location,
        )
    return parsed


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
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        **copy.deepcopy(detail),
    }
    try:
        result["input_digest"] = stable_digest(request)
    except (TypeError, ValueError):
        result["input_digest"] = None
    result["contract_digest"] = stable_digest(result)
    return result


def _string(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_IDENTIFIER_REQUIRED",
            "typed identifiers must be non-empty strings",
            location=location,
        )
    return value.strip()


def _point2(value: Any, *, location: str) -> List[float]:
    if not _sequence(value) or len(value) < 2:
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_2D_POINT",
            "2D points must contain finite x and y values",
            location=location,
        )
    return [
        round(_finite(value[0], location=location + ".x"), 8),
        round(_finite(value[1], location=location + ".y"), 8),
    ]


def _source_digest(request: Mapping[str, Any]) -> str:
    source = request.get("source")
    if not isinstance(source, Mapping):
        source = {}
    supplied = source.get("image_digest", request.get("source_image_digest"))
    if isinstance(supplied, str) and supplied.strip():
        return supplied.strip()
    metadata = {
        key: source[key]
        for key in ("image_id", "width", "height", "orientation")
        if key in source
    }
    if not metadata:
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_SOURCE_REQUIRED",
            "source.image_digest or stable image metadata is required",
        )
    return stable_digest(metadata)


def _camera(value: Any) -> Dict[str, Any]:
    if value is None:
        return {
            "state": "UNKNOWN",
            "authority": "UNKNOWN",
            "camera_digest": None,
            "absolute_scale_observed": False,
        }
    if not isinstance(value, Mapping):
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_CAMERA",
            "camera must be a typed object when supplied",
        )
    numeric: Dict[str, float] = {}
    for key in ("width_px", "height_px", "focal_length_px", "focal_length_mm",
                "subject_distance_cm", "scale_cm_per_px"):
        if key not in value:
            continue
        parsed = _finite(value[key], location=f"camera.{key}")
        if parsed <= 0.0:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_CAMERA",
                "camera dimensions and scale values must be positive",
                location=f"camera.{key}",
            )
        numeric[key] = round(parsed, 8)
    orientation = str(value.get("orientation", "UNKNOWN")).upper()
    normalised = {
        "state": str(value.get("state", "PROPOSED")).upper(),
        "authority": str(value.get("authority", "PROPOSED")).upper(),
        "orientation": orientation,
        **numeric,
    }
    normalised["camera_digest"] = stable_digest(normalised)
    normalised["absolute_scale_observed"] = (
        "scale_cm_per_px" in numeric
        and normalised["authority"] in _OBSERVED_STATES
    )
    return normalised


def _pose_keypoints(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    rows: List[Tuple[str, Any]] = []
    if isinstance(value, Mapping):
        rows = [(str(name), record) for name, record in value.items()]
    elif _sequence(value):
        for index, record in enumerate(value):
            if not isinstance(record, Mapping):
                raise _BodyProxyError(
                    "UNKNOWN_BODY_PROXY_POSE_KEYPOINT",
                    "pose_keypoints entries must be typed objects",
                    location=f"pose_keypoints[{index}]",
                )
            rows.append((_string(
                record.get("name", record.get("id")),
                location=f"pose_keypoints[{index}].name",
            ), record))
    else:
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_POSE_KEYPOINT",
            "pose_keypoints must be a mapping or array",
        )
    result: List[Dict[str, Any]] = []
    for name, raw in sorted(rows, key=lambda row: row[0]):
        location = f"pose_keypoints.{name}"
        if isinstance(raw, Mapping):
            if "point" in raw:
                point = _point2(raw["point"], location=location)
            else:
                point = _point2([raw.get("x"), raw.get("y")], location=location)
            confidence = _finite(raw.get("confidence", 1.0),
                                 location=location + ".confidence")
            state = str(raw.get("state", "PROPOSED")).upper()
        else:
            point = _point2(raw, location=location)
            confidence = 1.0
            state = "PROPOSED"
        if not 0.0 <= confidence <= 1.0:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_CONFIDENCE",
                "pose confidence must be within 0..1",
                location=location,
            )
        if state not in _OBSERVED_STATES | _PROPOSED_STATES:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_AUTHORITY",
                "pose state must remain OBSERVED, HUMAN_CONFIRMED, PROPOSED or UNKNOWN",
                location=location,
            )
        result.append({
            "name": name, "point": point,
            "confidence": round(confidence, 8), "state": state,
        })
    return result


def _skin_contours(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not _sequence(value):
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_SKIN_CONTOUR",
            "exposed_skin_contours must be an array",
        )
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_SKIN_CONTOUR",
                "every exposed-skin contour must be a typed object",
                location=f"exposed_skin_contours[{index}]",
            )
        contour_id = _string(
            raw.get("contour_id", raw.get("id")),
            location=f"exposed_skin_contours[{index}].id",
        )
        if contour_id in seen:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_DUPLICATE_ID",
                "exposed-skin contour ids must be unique",
                contour_id=contour_id,
            )
        seen.add(contour_id)
        points_raw = raw.get("points")
        if not _sequence(points_raw) or len(points_raw) < 2:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_SKIN_CONTOUR",
                "each exposed-skin contour needs at least two 2D points",
                contour_id=contour_id,
            )
        state = str(raw.get("state", "PROPOSED")).upper()
        if state not in _OBSERVED_STATES | _PROPOSED_STATES:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_AUTHORITY",
                "skin contour state is outside the typed evidence vocabulary",
                contour_id=contour_id,
            )
        result.append({
            "contour_id": contour_id,
            "body_region": str(raw.get("body_region", "UNKNOWN")).upper(),
            "points": [
                _point2(point, location=f"skin.{contour_id}[{point_index}]")
                for point_index, point in enumerate(points_raw)
            ],
            "state": state,
        })
    return sorted(result, key=lambda row: row["contour_id"])


def _mask_candidates(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not _sequence(value):
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_MASK",
            "mask_candidates must be an array",
        )
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_MASK",
                "every mask candidate must be a typed object",
                location=f"mask_candidates[{index}]",
            )
        candidate_id = _string(
            raw.get("candidate_id", raw.get("id")),
            location=f"mask_candidates[{index}].id",
        )
        if candidate_id in seen:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_DUPLICATE_ID",
                "mask candidate ids must be unique",
                candidate_id=candidate_id,
            )
        seen.add(candidate_id)
        kind = str(raw.get("kind", "")).upper()
        if kind not in _MASK_KINDS:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_MASK_KIND",
                "mask candidate kind must be BODY or GARMENT",
                candidate_id=candidate_id,
            )
        mask_digest = raw.get("mask_digest", raw.get("artifact_digest"))
        outline_raw = raw.get("outline")
        outline = []
        if outline_raw is not None:
            if not _sequence(outline_raw) or len(outline_raw) < 3:
                raise _BodyProxyError(
                    "UNKNOWN_BODY_PROXY_MASK",
                    "mask outline must contain at least three points",
                    candidate_id=candidate_id,
                )
            outline = [
                _point2(point, location=f"mask.{candidate_id}[{point_index}]")
                for point_index, point in enumerate(outline_raw)
            ]
        if (not isinstance(mask_digest, str) or not mask_digest.strip()) and not outline:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_MASK",
                "mask candidate needs mask_digest or an inspectable outline",
                candidate_id=candidate_id,
            )
        confidence = _finite(raw.get("confidence", 1.0),
                             location=f"mask.{candidate_id}.confidence")
        if not 0.0 <= confidence <= 1.0:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_CONFIDENCE",
                "mask confidence must be within 0..1",
                candidate_id=candidate_id,
            )
        state = str(raw.get("state", "PROPOSED")).upper()
        if state not in _OBSERVED_STATES | _PROPOSED_STATES:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_AUTHORITY",
                "mask state is outside the typed evidence vocabulary",
                candidate_id=candidate_id,
            )
        result.append({
            "candidate_id": candidate_id,
            "kind": kind,
            "mask_digest": mask_digest.strip()
                if isinstance(mask_digest, str) and mask_digest.strip() else None,
            "outline": outline,
            "confidence": round(confidence, 8),
            "state": state,
        })
    return sorted(result, key=lambda row: (row["kind"], row["candidate_id"]))


def _to_cm(record: Mapping[str, Any], *, location: str) -> Tuple[float, float]:
    unit = record.get("unit")
    if unit not in {"cm", "m"}:
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_DIMENSION_UNIT",
            "body dimensions require an explicit cm or m unit",
            location=location,
        )
    factor = 100.0 if unit == "m" else 1.0
    if "value" in record:
        value = _finite(record["value"], location=location + ".value") * factor
        return round(value, 8), round(value, 8)
    minimum = _finite(record.get("minimum"),
                      location=location + ".minimum") * factor
    maximum = _finite(record.get("maximum"),
                      location=location + ".maximum") * factor
    if minimum > maximum:
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_DIMENSION_RANGE",
            "dimension minimum cannot exceed maximum",
            location=location,
        )
    return round(minimum, 8), round(maximum, 8)


def _dimensions(value: Any) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    if value is None:
        return {}, []
    if not isinstance(value, Mapping):
        raise _BodyProxyError(
            "UNKNOWN_BODY_PROXY_DIMENSIONS",
            "dimensions must be a field-keyed typed object",
        )
    result: Dict[str, Dict[str, Any]] = {}
    review: List[Dict[str, Any]] = []
    for raw_name in sorted(value, key=str):
        if raw_name not in _ALIASES:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_DIMENSION_NAME",
                "dimension name is outside the body-proxy vocabulary",
                supplied=raw_name, supported=sorted(_ALIASES),
            )
        name = _ALIASES[raw_name]
        raw = value[raw_name]
        location = f"dimensions.{raw_name}"
        if not isinstance(raw, Mapping):
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_TYPED_DIMENSION_REQUIRED",
                "every dimension must be a typed object",
                location=location,
            )
        minimum, maximum = _to_cm(raw, location=location)
        low, high = _SANITY_LIMITS_CM[name]
        if minimum < low or maximum > high:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_DIMENSION_OUT_OF_BOUNDS",
                "dimension is outside broad physical sanity limits",
                location=location, allowed_range_cm=[low, high],
            )
        authority = str(raw.get("authority", "")).upper()
        source = raw.get("source")
        if not isinstance(source, Mapping):
            source = {}
        source_kind = str(source.get("kind", "UNKNOWN")).upper()
        supplied_authority = authority
        if source_kind in _CLOTHED_IMAGE_SOURCES:
            # Especially for chest/waist, the visible garment envelope is not
            # a tape or body scan.  Preserve the value only as a broad proposal.
            authority = "INFERRED"
            uncertainty = max(4.0, max(abs(minimum), abs(maximum)) * 0.07)
            center = (minimum + maximum) * 0.5
            minimum, maximum = round(center - uncertainty, 8), round(center + uncertainty, 8)
            review.append({
                "code": "REVIEW_CLOTHED_DIMENSION_DOWNGRADED",
                "dimension": name,
                "supplied_authority": supplied_authority or "UNKNOWN",
                "result_authority": "INFERRED",
                "why": "a clothed-image envelope is not a body measurement",
            })
        elif authority == "MEASURED":
            if source_kind not in _DIRECT_MEASUREMENT_SOURCES:
                raise _BodyProxyError(
                    "UNKNOWN_BODY_PROXY_MEASUREMENT_SOURCE",
                    "MEASURED dimensions require tape, scan, clinical, manual-pattern, or user-measured evidence",
                    location=location, supplied_source_kind=source_kind,
                )
            if (not isinstance(source.get("reference"), str)
                    or not source["reference"].strip()):
                raise _BodyProxyError(
                    "UNKNOWN_BODY_PROXY_MEASUREMENT_SOURCE",
                    "MEASURED dimensions require a non-empty source.reference",
                    location=location,
                )
        elif authority == "REQUESTED":
            source_kind = source_kind if source_kind != "UNKNOWN" else "USER_REQUEST"
        elif authority == "INFERRED":
            pass
        else:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_DIMENSION_AUTHORITY",
                "dimension authority must be MEASURED, REQUESTED, or INFERRED",
                location=location,
            )
        record = {
            "dimension": name,
            "range_cm": {"minimum": minimum, "maximum": maximum},
            "authority": authority,
            "source": {
                "kind": source_kind,
                "reference": source.get("reference"),
            },
            "exact": abs(maximum - minimum) <= _EPSILON,
        }
        existing = result.get(name)
        if existing is not None and existing != record:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_CONFLICTING_DIMENSIONS",
                "dimension aliases resolve to conflicting typed values",
                dimension=name,
            )
        result[name] = record
    return {name: result[name] for name in sorted(result)}, review


def _partition(
    dimensions: Mapping[str, Mapping[str, Any]],
    pose: Sequence[Mapping[str, Any]],
    skin: Sequence[Mapping[str, Any]],
    masks: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    partition: Dict[str, List[Dict[str, Any]]] = {
        "OBSERVED": [], "MEASURED": [], "REQUESTED": [],
        "INFERRED": [], "PROPOSED": [],
    }
    for name in sorted(dimensions):
        record = copy.deepcopy(dict(dimensions[name]))
        partition[record["authority"]].append(record)
    for point in pose:
        bucket = "OBSERVED" if point["state"] in _OBSERVED_STATES else "PROPOSED"
        partition[bucket].append({
            "kind": "POSE_KEYPOINT", **copy.deepcopy(dict(point)),
        })
    for contour in skin:
        bucket = "OBSERVED" if contour["state"] in _OBSERVED_STATES else "PROPOSED"
        partition[bucket].append({
            "kind": "EXPOSED_SKIN_CONTOUR", **copy.deepcopy(dict(contour)),
        })
    for mask in masks:
        bucket = "OBSERVED" if mask["state"] in _OBSERVED_STATES else "PROPOSED"
        partition[bucket].append({
            "kind": "MASK_CANDIDATE", **copy.deepcopy(dict(mask)),
        })
    return partition


def _ranges(
    dimensions: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for name in _DIMENSIONS:
        supplied = dimensions.get(name)
        if supplied is not None:
            result[name] = {
                **copy.deepcopy(dict(supplied["range_cm"])),
                "authority": supplied["authority"],
                "basis": supplied["source"]["kind"],
            }
        else:
            minimum, maximum = _FALLBACK_RANGES_CM[name]
            result[name] = {
                "minimum": minimum, "maximum": maximum,
                "authority": "INFERRED",
                "basis": "BOUNDED_PARAMETRIC_FALLBACK",
            }
    return result


def _at(bounds: Mapping[str, Any], fraction: float) -> float:
    return round(
        float(bounds["minimum"])
        + (float(bounds["maximum"]) - float(bounds["minimum"])) * fraction,
        6,
    )


def _confidence_basis(
    dimensions: Mapping[str, Mapping[str, Any]],
    pose: Sequence[Mapping[str, Any]], skin: Sequence[Mapping[str, Any]],
    masks: Sequence[Mapping[str, Any]], camera: Mapping[str, Any],
) -> Tuple[float, List[str]]:
    measured = sum(row["authority"] == "MEASURED" for row in dimensions.values())
    requested = sum(row["authority"] == "REQUESTED" for row in dimensions.values())
    body_masks = sum(row["kind"] == "BODY" for row in masks)
    garment_masks = sum(row["kind"] == "GARMENT" for row in masks)
    score = min(0.92, 0.18 + min(measured, 4) * 0.12
                + min(requested, 4) * 0.05
                + min(len(pose), 12) * 0.012
                + min(len(skin), 4) * 0.025
                + min(body_masks, 2) * 0.04
                + min(garment_masks, 2) * 0.03
                + (0.05 if camera.get("absolute_scale_observed") else 0.0))
    basis = [
        f"{measured} direct measured dimensions",
        f"{requested} requested target dimensions",
        f"{len(pose)} typed 2D pose keypoints",
        f"{len(skin)} exposed-skin contours",
        f"{body_masks} body and {garment_masks} garment mask candidates",
        "score is evidence completeness, not probability of anatomical correctness",
    ]
    return round(score, 6), basis


def _candidate(
    *, source_digest: str, index: int, label: str, fraction: float,
    depth_share: float, ranges: Mapping[str, Mapping[str, Any]],
    partition: Mapping[str, List[Dict[str, Any]]],
    pose: Sequence[Mapping[str, Any]], skin: Sequence[Mapping[str, Any]],
    masks: Sequence[Mapping[str, Any]], camera: Mapping[str, Any],
    confidence_score: float, confidence_basis: Sequence[str],
) -> Dict[str, Any]:
    values = {name: _at(ranges[name], fraction) for name in _DIMENSIONS}
    candidate_partition = copy.deepcopy(dict(partition))
    candidate_partition["INFERRED"].append({
        "kind": "REAR_DEPTH_DISTRIBUTION",
        "rear_depth_share": depth_share,
        "authority": "INFERRED",
        "rear_observed": False,
    })
    candidate_seed = {
        "source_image_digest": source_digest,
        "label": label,
        "fraction": fraction,
        "depth_share": depth_share,
        "values_cm": values,
        "mask_ids": [row["candidate_id"] for row in masks],
    }
    candidate_id = "body-proxy:" + stable_digest(candidate_seed)[:16]
    avatar_payload = {
        "avatar_id": "avatar:" + candidate_id,
        "kind": "PARAMETRIC_GAME_AVATAR",
        "authority": "PROPOSED_PREVIEW",
        "measurements_cm": {
            name: values[name]
            for name in ("height", "chest_bust", "waist", "hip")
        },
        "measurement_ranges_cm": {
            name: copy.deepcopy(dict(ranges[name]))
            for name in ("height", "chest_bust", "waist", "hip")
        },
        "rear_depth_share": depth_share,
        "not_a_target_wearer_measurement": True,
    }
    avatar_payload["geometry_digest"] = stable_digest(avatar_payload)
    result: Dict[str, Any] = {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "rank": index + 1,
        "label": label,
        "state": AUTHORITY,
        "authority": AUTHORITY,
        "body_proxy_parameters": {
            "dimensions_cm": values,
            "rear_depth_share": depth_share,
            "pose_keypoint_names": [row["name"] for row in pose],
            "skin_contour_ids": [row["contour_id"] for row in skin],
            "body_mask_candidate_ids": [
                row["candidate_id"] for row in masks if row["kind"] == "BODY"
            ],
            "garment_mask_candidate_ids": [
                row["candidate_id"] for row in masks if row["kind"] == "GARMENT"
            ],
            "camera_digest": camera.get("camera_digest"),
        },
        "claim_partitions": candidate_partition,
        "confidence": {
            "score": confidence_score,
            "basis": list(confidence_basis),
            "is_correctness_probability": False,
        },
        "rear_generation_constraints": {
            "state": AUTHORITY,
            "rear_surface_observed": False,
            "dimensions_cm": {
                name: copy.deepcopy(dict(ranges[name]))
                for name in ("height", "chest_bust", "waist", "hip",
                             "shoulder", "body_length")
            },
            "rear_depth_share": depth_share,
            "human_review_required": True,
        },
        "avatar_binding": avatar_payload,
        "limitations": [
            "single clothed image does not observe the rear body",
            "garment silhouette is not a measured chest or waist",
            "proxy supports visual separation and candidate generation only",
            "not fit, health, identity, anatomy, or manufacturing certification",
        ],
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["candidate_digest"] = stable_digest(result)
    return result


def propose_body_proxy(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Return deterministic, typed body proxy alternatives for human audit."""
    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            request, "UNKNOWN_BODY_PROXY_SCHEMA",
            f"request schema must be {REQUEST_SCHEMA}",
        )
    try:
        source_digest = _source_digest(request)
        mode = str(request.get("selection_mode", "HUMAN_APPROVAL")).upper()
        if mode not in _MODES:
            raise _BodyProxyError(
                "UNKNOWN_BODY_PROXY_SELECTION_MODE",
                "selection_mode must be HUMAN_APPROVAL or AUTO_PROPOSED",
            )
        camera = _camera(request.get("camera"))
        pose = _pose_keypoints(request.get("pose_keypoints_2d"))
        skin = _skin_contours(request.get("exposed_skin_contours"))
        masks = _mask_candidates(request.get("mask_candidates"))
        dimension_input = request.get(
            "dimensions", request.get("user_dimensions"))
        dimensions, review_items = _dimensions(dimension_input)
    except _BodyProxyError as exc:
        return _refusal(request, exc.code, exc.why, **exc.detail)

    partition = _partition(dimensions, pose, skin, masks)
    ranges = _ranges(dimensions)
    for name in _DIMENSIONS:
        if name not in dimensions:
            partition["INFERRED"].append({
                "kind": "BODY_PROXY_DIMENSION_RANGE",
                "dimension": name,
                "range_cm": {
                    "minimum": ranges[name]["minimum"],
                    "maximum": ranges[name]["maximum"],
                },
                "authority": "INFERRED",
                "basis": ranges[name]["basis"],
            })
    # Rear shape remains an alternative even when circumference is measured:
    # one front image does not determine front/back depth distribution.
    variants = [
        ("BALANCED_DEPTH", 0.50, 0.50),
        ("SHALLOWER_REAR", 0.35, 0.46),
        ("DEEPER_REAR", 0.65, 0.54),
    ]
    confidence_score, confidence_basis = _confidence_basis(
        dimensions, pose, skin, masks, camera)
    candidates = [
        _candidate(
            source_digest=source_digest, index=index, label=label,
            fraction=fraction, depth_share=depth_share, ranges=ranges,
            partition=partition, pose=pose, skin=skin, masks=masks,
            camera=camera, confidence_score=confidence_score,
            confidence_basis=confidence_basis,
        )
        for index, (label, fraction, depth_share) in enumerate(variants)
    ]
    selected = candidates[0]["candidate_id"] if mode == "AUTO_PROPOSED" else None
    if not any(row["kind"] == "BODY" for row in masks):
        review_items.append({
            "code": "REVIEW_BODY_MASK_REQUIRED",
            "why": "no body-mask candidate was supplied; fallback proxy remains coarse",
        })
    if not any(row["kind"] == "GARMENT" for row in masks):
        review_items.append({
            "code": "REVIEW_GARMENT_MASK_REQUIRED",
            "why": "no garment-mask candidate was supplied; body/garment boundary is unresolved",
        })
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_BODY_PROXY_CANDIDATES",
        "state": AUTHORITY,
        "authority": AUTHORITY,
        "source_image_digest": source_digest,
        "provider": {
            "external_model_used": False,
            "fallback_used": True,
            "fallback_method": "BOUNDED_PARAMETRIC_BODY_PROXY_V1",
        },
        "camera": camera,
        "evidence": {
            "pose_keypoints_2d": pose,
            "exposed_skin_contours": skin,
            "mask_candidates": masks,
        },
        "claim_partitions": partition,
        "dimension_ranges_cm": ranges,
        "candidates": candidates,
        "selection": {
            "mode": mode,
            "status": ("AUTO_PROPOSED_SELECTED"
                       if selected else "HUMAN_APPROVAL_REQUIRED"),
            "selected_candidate_id": selected,
            "authority": AUTHORITY if selected else "UNSELECTED",
            "may_open_manufacturing_gate": False,
            "human_can_override": True,
        },
        "review_items": review_items + [{
            "code": "REVIEW_REAR_BODY_UNOBSERVED",
            "why": "rear depth and hidden body surface remain proposed alternatives",
        }],
        "human_approval_required": mode == "HUMAN_APPROVAL",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    digest_payload = copy.deepcopy(result)
    result["contract_digest"] = stable_digest(digest_payload)
    return result


build_body_proxy = propose_body_proxy
