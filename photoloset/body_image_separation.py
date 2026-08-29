# -*- coding: utf-8 -*-
"""Typed body/garment separation proposals for one clothed-person image.

This module normalises already-produced vision/SMPL-like evidence or emits a
local typed fallback.  It never calls a provider, downloads a model, measures
a body through clothing, or invents an observed rear surface.  All semantic
separations are candidates for human review and remain outside manufacturing
approval gates.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple


REQUEST_SCHEMA = "garment.body-image-separation.request.v1"
SCHEMA = "garment.body-image-separation.v1"
CANDIDATE_SCHEMA = "garment.body-image-separation-candidate.v1"
CANDIDATE_STATE = "PROPOSED_BODY_GARMENT_SEPARATION"

_SELECTION_MODES = {"HUMAN_APPROVAL", "AUTO_PROPOSED"}
_MASK_CLASSES = ("BODY", "GARMENT", "HAIR", "BACKGROUND")
_KNOWN_AUTHORITIES = {
    "UNKNOWN", "UNOBSERVED", "PROPOSED", "MODEL_PROPOSED", "INFERRED",
    "INFERRED_RANGE", "OBSERVED", "HUMAN_CONFIRMED", "REQUESTED", "MEASURED",
}
_BODY_DIMENSION_NAMES = {
    "height", "chest_bust", "chest", "bust", "waist", "hip", "shoulder",
    "body_length", "inseam",
}
_MAX_PROVIDERS = 8


class _SeparationError(ValueError):
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
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_NON_FINITE",
            "numeric provider output must be finite",
            location=location,
        )
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_NON_FINITE",
            "numeric provider output must be finite",
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
        "rear_state": "UNKNOWN_UNOBSERVED",
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


def _nonempty(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_IDENTIFIER",
            "typed identifiers must be non-empty strings",
            location=location,
        )
    return value.strip()


def _authority(value: Any, *, default: str = "PROPOSED") -> str:
    """Preserve or lower authority; never promote unknown/model evidence."""
    raw = str(value if value is not None else default).upper()
    if raw not in _KNOWN_AUTHORITIES:
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_AUTHORITY",
            "provider authority is outside the typed vocabulary",
            supplied_authority=raw,
        )
    if raw in {"UNKNOWN", "UNOBSERVED"}:
        return raw
    if raw in {"MODEL_PROPOSED", "PROPOSED"}:
        return "PROPOSED"
    if raw in {"INFERRED", "INFERRED_RANGE", "MEASURED", "REQUESTED"}:
        # Image/SMPL semantics cannot become a direct body measurement here.
        return "INFERRED"
    return raw  # OBSERVED or HUMAN_CONFIRMED remains exactly as supplied.


def _point2(value: Any, *, location: str) -> List[float]:
    if not _sequence(value) or len(value) < 2:
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_POINT",
            "2D points must contain finite x and y",
            location=location,
        )
    return [
        round(_finite(value[0], location=location + ".x"), 8),
        round(_finite(value[1], location=location + ".y"), 8),
    ]


def _source(request: Mapping[str, Any]) -> Dict[str, Any]:
    raw = request.get("source")
    if not isinstance(raw, Mapping):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_SOURCE",
            "source must contain an image digest or stable anonymous metadata",
        )
    supplied_digest = raw.get("image_digest")
    if isinstance(supplied_digest, str) and supplied_digest.strip():
        image_digest = supplied_digest.strip()
    else:
        metadata = {
            key: raw[key]
            for key in ("image_id", "width", "height", "orientation")
            if key in raw
        }
        if not metadata:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_SOURCE",
                "source.image_digest or stable anonymous metadata is required",
            )
        image_digest = stable_digest(metadata)
    result: Dict[str, Any] = {"image_digest": image_digest}
    for key in ("width", "height"):
        if key in raw:
            value = _finite(raw[key], location=f"source.{key}")
            if value <= 0:
                raise _SeparationError(
                    "UNKNOWN_BODY_IMAGE_SEPARATION_SOURCE",
                    "source image dimensions must be positive",
                    location=f"source.{key}",
                )
            result[key] = int(value) if value.is_integer() else round(value, 8)
    result["orientation"] = str(raw.get("orientation", "UNKNOWN")).upper()
    return result


def _camera(value: Any, *, default_authority: str) -> Dict[str, Any]:
    if value is None:
        return {
            "state": "UNKNOWN",
            "authority": "UNKNOWN",
            "view": "UNKNOWN",
            "camera_digest": None,
        }
    if not isinstance(value, Mapping):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_CAMERA",
            "camera must be a typed object",
        )
    result: Dict[str, Any] = {
        "state": _authority(value.get("state", default_authority)),
        "authority": _authority(value.get("authority", default_authority)),
        "view": str(value.get("view", value.get("viewpoint", "UNKNOWN"))).upper(),
        "orientation": str(value.get("orientation", "UNKNOWN")).upper(),
    }
    for key in (
        "width_px", "height_px", "focal_length_px", "focal_length_mm",
        "subject_distance_cm", "scale_cm_per_px", "yaw_deg", "pitch_deg",
        "roll_deg",
    ):
        if key not in value:
            continue
        parsed = _finite(value[key], location=f"camera.{key}")
        if key in {"width_px", "height_px", "focal_length_px", "focal_length_mm",
                   "subject_distance_cm", "scale_cm_per_px"} and parsed <= 0:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_CAMERA",
                "camera dimensions, focal values, distance and scale must be positive",
                location=f"camera.{key}",
            )
        result[key] = round(parsed, 8)
    result["camera_digest"] = stable_digest(result)
    return result


def _pose(value: Any, *, default_authority: str) -> List[Dict[str, Any]]:
    if value is None:
        return []
    rows: List[Tuple[str, Any]] = []
    if isinstance(value, Mapping):
        rows = [(str(name), record) for name, record in value.items()]
    elif _sequence(value):
        for index, record in enumerate(value):
            if not isinstance(record, Mapping):
                raise _SeparationError(
                    "UNKNOWN_BODY_IMAGE_SEPARATION_POSE",
                    "pose keypoints must be typed objects",
                    location=f"pose_keypoints[{index}]",
                )
            name = _nonempty(
                record.get("name", record.get("id")),
                location=f"pose_keypoints[{index}].name",
            )
            rows.append((name, record))
    else:
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_POSE",
            "pose_keypoints must be a mapping or array",
        )
    result: List[Dict[str, Any]] = []
    for name, raw in sorted(rows, key=lambda row: row[0]):
        location = f"pose_keypoints.{name}"
        if isinstance(raw, Mapping):
            point = (_point2(raw["point"], location=location)
                     if "point" in raw else
                     _point2([raw.get("x"), raw.get("y")], location=location))
            confidence = _finite(
                raw.get("confidence", 1.0), location=location + ".confidence")
            authority = _authority(
                raw.get("authority", raw.get("state", default_authority)))
        else:
            point = _point2(raw, location=location)
            confidence = 1.0
            authority = _authority(default_authority)
        if not 0.0 <= confidence <= 1.0:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_CONFIDENCE",
                "pose confidence must be within 0..1",
                location=location,
            )
        result.append({
            "name": name, "point": point,
            "confidence": round(confidence, 8), "authority": authority,
        })
    return result


def _skin_contours(value: Any, *, default_authority: str) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not _sequence(value):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_SKIN_CONTOUR",
            "exposed_skin_contours must be an array",
        )
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_SKIN_CONTOUR",
                "each exposed-skin contour must be a typed object",
                location=f"exposed_skin_contours[{index}]",
            )
        contour_id = _nonempty(
            raw.get("contour_id", raw.get("id")),
            location=f"exposed_skin_contours[{index}].id",
        )
        if contour_id in seen:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_DUPLICATE_ID",
                "contour ids must be unique",
                contour_id=contour_id,
            )
        seen.add(contour_id)
        points = raw.get("points")
        if not _sequence(points) or len(points) < 2:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_SKIN_CONTOUR",
                "each contour needs at least two points",
                contour_id=contour_id,
            )
        result.append({
            "contour_id": contour_id,
            "body_region": str(raw.get("body_region", "UNKNOWN")).upper(),
            "points": [
                _point2(point, location=f"skin.{contour_id}[{point_index}]")
                for point_index, point in enumerate(points)
            ],
            "authority": _authority(
                raw.get("authority", raw.get("state", default_authority))),
        })
    return sorted(result, key=lambda row: row["contour_id"])


def _mask_geometry(raw: Mapping[str, Any], *, mask_id: str) -> Dict[str, Any]:
    digest = raw.get("mask_digest", raw.get("artifact_digest"))
    outline_raw = raw.get("outline")
    outline: List[List[float]] = []
    if outline_raw is not None:
        if not _sequence(outline_raw) or len(outline_raw) < 3:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_MASK",
                "mask outline must contain at least three points",
                mask_id=mask_id,
            )
        outline = [
            _point2(point, location=f"mask.{mask_id}[{index}]")
            for index, point in enumerate(outline_raw)
        ]
    if isinstance(digest, str) and digest.strip():
        digest = digest.strip()
    else:
        digest = stable_digest(outline) if outline else None
    return {"mask_digest": digest, "outline": outline}


def _masks(value: Any, *, default_authority: str) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not _sequence(value):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_MASK",
            "masks must be an array",
        )
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_MASK",
                "each mask must be a typed object",
                location=f"masks[{index}]",
            )
        mask_id = _nonempty(
            raw.get("mask_id", raw.get("candidate_id", raw.get("id"))),
            location=f"masks[{index}].id",
        )
        if mask_id in seen:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_DUPLICATE_ID",
                "mask ids must be unique within one provider result",
                mask_id=mask_id,
            )
        seen.add(mask_id)
        mask_class = str(raw.get("class", raw.get("kind", ""))).upper()
        if mask_class not in _MASK_CLASSES:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_MASK_CLASS",
                "mask class must be BODY, GARMENT, HAIR, or BACKGROUND",
                mask_id=mask_id, supplied_class=mask_class,
            )
        confidence = _finite(
            raw.get("confidence", 1.0), location=f"masks.{mask_id}.confidence")
        if not 0.0 <= confidence <= 1.0:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_CONFIDENCE",
                "mask confidence must be within 0..1",
                mask_id=mask_id,
            )
        geometry = _mask_geometry(raw, mask_id=mask_id)
        result.append({
            "mask_id": mask_id,
            "class": mask_class,
            "garment_unit_id": raw.get("garment_unit_id"),
            "layer": raw.get("layer"),
            "confidence": round(confidence, 8),
            "authority": _authority(
                raw.get("authority", raw.get("state", default_authority))),
            **geometry,
        })
    return sorted(result, key=lambda row: (
        row["class"], str(row.get("garment_unit_id") or ""),
        row["layer"] if isinstance(row.get("layer"), int) else -1,
        row["mask_id"],
    ))


def _occlusions(value: Any, *, default_authority: str) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not _sequence(value):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_OCCLUSION",
            "occlusions must be an array",
        )
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_OCCLUSION",
                "each occlusion must be a typed object",
                location=f"occlusions[{index}]",
            )
        occlusion_id = _nonempty(
            raw.get("occlusion_id", raw.get("id")),
            location=f"occlusions[{index}].id",
        )
        if occlusion_id in seen:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_DUPLICATE_ID",
                "occlusion ids must be unique",
                occlusion_id=occlusion_id,
            )
        seen.add(occlusion_id)
        result.append({
            "occlusion_id": occlusion_id,
            "occluder_mask_id": raw.get("occluder_mask_id"),
            "occluded_mask_id": raw.get("occluded_mask_id"),
            "relation": str(raw.get("relation", "OCCLUDES")).upper(),
            "authority": _authority(
                raw.get("authority", raw.get("state", default_authority))),
            "rear_implication": "NONE_OBSERVED",
        })
    return sorted(result, key=lambda row: row["occlusion_id"])


def _body_ranges(value: Any, *, default_authority: str) -> Dict[str, Dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_BODY_RANGE",
            "body_dimension_ranges_cm must be a field-keyed object",
        )
    result: Dict[str, Dict[str, Any]] = {}
    for raw_name in sorted(value, key=str):
        name = str(raw_name)
        if name not in _BODY_DIMENSION_NAMES:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_BODY_RANGE_NAME",
                "body range name is outside the typed vocabulary",
                dimension=name,
            )
        canonical = "chest_bust" if name in {"chest", "bust"} else name
        raw = value[raw_name]
        if not isinstance(raw, Mapping):
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_BODY_RANGE",
                "each body range must contain minimum and maximum",
                dimension=canonical,
            )
        minimum = _finite(raw.get("minimum"),
                          location=f"body_range.{canonical}.minimum")
        maximum = _finite(raw.get("maximum"),
                          location=f"body_range.{canonical}.maximum")
        unit = raw.get("unit", "cm")
        if unit not in {"cm", "m"}:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_BODY_RANGE_UNIT",
                "body ranges require cm or m",
                dimension=canonical,
            )
        factor = 100.0 if unit == "m" else 1.0
        minimum, maximum = minimum * factor, maximum * factor
        if minimum <= 0 or maximum <= 0 or minimum > maximum:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_BODY_RANGE",
                "body range must be positive and ordered",
                dimension=canonical,
            )
        record = {
            "minimum": round(minimum, 8),
            "maximum": round(maximum, 8),
            "unit": "cm",
            "authority": "INFERRED_RANGE",
            "input_authority": _authority(
                raw.get("authority", default_authority)),
            "measured_from_clothed_image": False,
        }
        existing = result.get(canonical)
        if existing is not None and existing != record:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_CONFLICTING_RANGE",
                "dimension aliases resolve to conflicting ranges",
                dimension=canonical,
            )
        result[canonical] = record
    return result


def _shape_coefficients(value: Any, *, default_authority: str) -> Dict[str, Any]:
    if value is None:
        return {
            "values": [], "authority": "UNKNOWN",
            "not_body_measurements": True,
        }
    if isinstance(value, Mapping):
        raw_values = value.get("values", value.get("betas"))
        supplied = value.get("authority", default_authority)
    else:
        raw_values, supplied = value, default_authority
    if not _sequence(raw_values):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_SHAPE",
            "shape coefficients must be an array",
        )
    values = [
        round(_finite(component, location=f"shape_coefficients[{index}]"), 8)
        for index, component in enumerate(raw_values)
    ]
    return {
        "values": values,
        "authority": _authority(supplied),
        "not_body_measurements": True,
    }


def _normalise_provider(raw: Mapping[str, Any], *, fallback: bool) -> Dict[str, Any]:
    provider_id = _nonempty(
        raw.get("provider_id", raw.get("id")), location="provider.provider_id")
    provider_authority = _authority(raw.get("authority", "PROPOSED"))
    body_shape = raw.get("body_shape")
    if not isinstance(body_shape, Mapping):
        body_shape = {}
    ranges_raw = raw.get(
        "body_dimension_ranges_cm", body_shape.get("dimension_ranges_cm"))
    masks_raw = raw.get("masks", raw.get("mask_candidates"))
    normalised = {
        "provider_id": provider_id,
        "provider_kind": str(raw.get(
            "provider_kind", "LOCAL_TYPED_FALLBACK" if fallback else "EXTERNAL_PRECOMPUTED"
        )).upper(),
        "provider_available": not fallback,
        "provider_authority": provider_authority,
        "pose_keypoints": _pose(
            raw.get("pose_keypoints", raw.get("pose_keypoints_2d")),
            default_authority=provider_authority,
        ),
        "exposed_skin_contours": _skin_contours(
            raw.get("exposed_skin_contours"),
            default_authority=provider_authority,
        ),
        "masks": _masks(masks_raw, default_authority=provider_authority),
        "camera": _camera(raw.get("camera"), default_authority=provider_authority),
        "occlusions": _occlusions(
            raw.get("occlusions"), default_authority=provider_authority),
        "body_dimension_ranges_cm": _body_ranges(
            ranges_raw, default_authority=provider_authority),
        "shape_coefficients": _shape_coefficients(
            raw.get("shape_coefficients", body_shape.get("shape_coefficients")),
            default_authority=provider_authority,
        ),
    }
    normalised["provider_result_digest"] = stable_digest(normalised)
    return normalised


def _provider_inputs(request: Mapping[str, Any], source: Mapping[str, Any]) -> List[Dict[str, Any]]:
    supplied = request.get("provider_outputs")
    if supplied is None and request.get("provider_output") is not None:
        supplied = [request.get("provider_output")]
    if supplied is not None:
        if not _sequence(supplied) or not supplied:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_PROVIDER",
                "provider_outputs must be a non-empty array when supplied",
            )
        if len(supplied) > _MAX_PROVIDERS:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_PROVIDER_LIMIT",
                f"at most {_MAX_PROVIDERS} provider outputs are accepted",
            )
        if any(not isinstance(row, Mapping) for row in supplied):
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_PROVIDER",
                "every provider output must be a typed object",
            )
        providers = [
            _normalise_provider(row, fallback=False) for row in supplied
        ]
        ids = [row["provider_id"] for row in providers]
        if len(ids) != len(set(ids)):
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_DUPLICATE_ID",
                "provider ids must be unique",
            )
        return sorted(providers, key=lambda row: row["provider_id"])

    fallback_raw = request.get("local_fallback")
    if fallback_raw is not None and not isinstance(fallback_raw, Mapping):
        raise _SeparationError(
            "UNKNOWN_BODY_IMAGE_SEPARATION_FALLBACK",
            "local_fallback must be a typed object",
        )
    fallback: Dict[str, Any] = copy.deepcopy(dict(fallback_raw or {}))
    fallback.setdefault(
        "provider_id", "local-fallback:" + source["image_digest"][:16])
    fallback.setdefault("provider_kind", "LOCAL_TYPED_FALLBACK")
    fallback.setdefault("authority", "PROPOSED")
    if "camera" not in fallback and request.get("camera") is not None:
        fallback["camera"] = copy.deepcopy(request.get("camera"))
    provider = _normalise_provider(fallback, fallback=True)
    if not provider["masks"]:
        provider["masks"] = [
            {
                "mask_id": f"fallback:{mask_class.lower()}",
                "class": mask_class,
                "garment_unit_id": None,
                "layer": None,
                "confidence": 0.0,
                "authority": "UNKNOWN",
                "mask_digest": None,
                "outline": [],
                "availability": "MISSING_REQUIRES_HUMAN_OR_PROVIDER",
            }
            for mask_class in _MASK_CLASSES
        ]
        digest_payload = copy.deepcopy(provider)
        digest_payload.pop("provider_result_digest", None)
        provider["provider_result_digest"] = stable_digest(digest_payload)
    return [provider]


def _confidence(provider: Mapping[str, Any]) -> Dict[str, Any]:
    pose_count = len(provider["pose_keypoints"])
    skin_count = len(provider["exposed_skin_contours"])
    available_masks = sum(
        row.get("mask_digest") is not None or bool(row.get("outline"))
        for row in provider["masks"]
    )
    occlusion_count = len(provider["occlusions"])
    camera_known = provider["camera"]["state"] != "UNKNOWN"
    score = min(
        0.9,
        0.1 + min(pose_count, 20) * 0.015
        + min(skin_count, 6) * 0.025
        + min(available_masks, 6) * 0.07
        + min(occlusion_count, 6) * 0.025
        + (0.05 if camera_known else 0.0),
    )
    return {
        "score": round(score, 6),
        "basis": [
            f"{pose_count} typed pose keypoints",
            f"{skin_count} exposed-skin contours",
            f"{available_masks} masks with geometry or artifact digest",
            f"{occlusion_count} typed occlusion relations",
            "camera metadata present" if camera_known else "camera metadata unknown",
            "score is evidence completeness, not body-measurement accuracy",
        ],
        "is_correctness_probability": False,
    }


def _candidate(
    provider: Mapping[str, Any], *, policy: str, policy_rank: int,
) -> Dict[str, Any]:
    seed = {
        "provider_result_digest": provider["provider_result_digest"],
        "boundary_policy": policy,
    }
    candidate_id = "separation:" + stable_digest(seed)[:20]
    body_ranges = copy.deepcopy(provider["body_dimension_ranges_cm"])
    result: Dict[str, Any] = {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "state": CANDIDATE_STATE,
        "authority": CANDIDATE_STATE,
        "provider_id": provider["provider_id"],
        "provider_result_digest": provider["provider_result_digest"],
        "boundary_policy": policy,
        "policy_rank": policy_rank,
        "pose_keypoints": copy.deepcopy(provider["pose_keypoints"]),
        "exposed_skin_contours": copy.deepcopy(
            provider["exposed_skin_contours"]),
        "masks": copy.deepcopy(provider["masks"]),
        "camera": copy.deepcopy(provider["camera"]),
        "occlusions": copy.deepcopy(provider["occlusions"]),
        "body_shape": {
            "state": "INFERRED_RANGE",
            "dimension_ranges_cm": body_ranges,
            "shape_coefficients": copy.deepcopy(
                provider["shape_coefficients"]),
            "clothed_silhouette_measured_as_body": False,
            "absolute_dimensions_available": bool(body_ranges),
        },
        "back_generation_conditioning": {
            "state": "PROPOSED_BACK_CONDITIONING",
            "rear_state": "UNKNOWN_UNOBSERVED",
            "front_pose_keypoints": copy.deepcopy(provider["pose_keypoints"]),
            "front_masks": copy.deepcopy(provider["masks"]),
            "front_occlusions": copy.deepcopy(provider["occlusions"]),
            "body_dimension_ranges_cm": body_ranges,
            "shape_coefficients": copy.deepcopy(
                provider["shape_coefficients"]),
            "must_not_claim_rear_observation": True,
            "requires_body_proxy_or_human_dimensions": not bool(body_ranges),
        },
        "confidence_rationale": _confidence(provider),
        "limitations": [
            "single-view clothing does not expose the underlying body surface",
            "body dimension output is an inferred range, never a photo measurement",
            "rear geometry and rear garment layering are UNKNOWN_UNOBSERVED",
            "mask and pose semantics retain or lower their input authority",
        ],
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["candidate_digest"] = stable_digest(result)
    return result


def separate_body_image(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalise provider/fallback evidence into reviewable separation candidates."""
    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            request, "UNKNOWN_BODY_IMAGE_SEPARATION_SCHEMA",
            f"request schema must be {REQUEST_SCHEMA}",
        )
    try:
        source = _source(request)
        mode = str(request.get("selection_mode", "HUMAN_APPROVAL")).upper()
        if mode not in _SELECTION_MODES:
            raise _SeparationError(
                "UNKNOWN_BODY_IMAGE_SEPARATION_SELECTION_MODE",
                "selection_mode must be HUMAN_APPROVAL or AUTO_PROPOSED",
            )
        providers = _provider_inputs(request, source)
    except _SeparationError as exc:
        return _refusal(request, exc.code, exc.why, **exc.detail)

    policies = (
        "AMBIGUOUS_PIXELS_UNKNOWN",
        "BODY_CONSERVATIVE",
        "GARMENT_CONSERVATIVE",
    )
    candidates = [
        _candidate(provider, policy=policy, policy_rank=rank)
        for provider in providers
        for rank, policy in enumerate(policies, start=1)
    ]
    candidates.sort(key=lambda row: (
        row["provider_id"], row["policy_rank"], row["candidate_id"]))
    selected = candidates[0]["candidate_id"] if mode == "AUTO_PROPOSED" else None
    fallback_used = all(not provider["provider_available"] for provider in providers)
    review_items: List[Dict[str, Any]] = [{
        "code": "REVIEW_REAR_UNKNOWN_UNOBSERVED",
        "why": "one image cannot observe the body or garment rear",
    }]
    if fallback_used:
        review_items.append({
            "code": "REVIEW_PROVIDER_ABSENT_TYPED_FALLBACK",
            "why": "no external provider result was supplied; missing channels remain UNKNOWN",
        })
    if any(not provider["body_dimension_ranges_cm"] for provider in providers):
        review_items.append({
            "code": "REVIEW_BODY_DIMENSION_RANGE_REQUIRED",
            "why": "no absolute body range was accepted; bind a body proxy or human dimensions",
        })

    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
        "state": CANDIDATE_STATE,
        "source": source,
        "providers": providers,
        "provider_fallback_used": fallback_used,
        "candidates": candidates,
        "selection": {
            "mode": mode,
            "status": ("AUTO_PROPOSED_SELECTED"
                       if selected else "HUMAN_APPROVAL_REQUIRED"),
            "selected_candidate_id": selected,
            "authority": CANDIDATE_STATE if selected else "UNSELECTED",
            "may_open_manufacturing_gate": False,
            "human_can_override": True,
        },
        "rear_state": "UNKNOWN_UNOBSERVED",
        "review_items": review_items,
        "human_approval_required": mode == "HUMAN_APPROVAL",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["contract_digest"] = stable_digest(result)
    return result


normalise_body_image_separation = separate_body_image
