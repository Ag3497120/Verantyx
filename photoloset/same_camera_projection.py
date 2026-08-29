# -*- coding: utf-8 -*-
"""Bind a front-image target and one proposed garment mesh to one camera.

This is the deterministic bridge between the interactive fused-target cleanup
and :mod:`photoloset.front_projection_compare`.  It deliberately does *not*
claim that fitting one single-view mesh bounding box recovers depth, the rear,
or wearer measurements.  The alignment is a ``PROPOSED_PREVIEW`` transform
locked to the user-selected avatar and target camera.  The evaluator keeps its
independent axes and still requires a human design decision.

The first bridge rasterises the observed/proposed clothing outline and the
front projection of the candidate triangles.  More detailed image models may
later supply typed per-part masks without changing this boundary.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple

from .front_projection_compare import compare_front_projection, stable_digest


REQUEST_SCHEMA = "garment.same-camera-projection.request.v1"
SCHEMA = "garment.same-camera-projection.v1"


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNKNOWN",
        "why": why,
        "human_approval_required": True,
        "fact_promotions": [],
        "manufacturing_ready": False,
    }
    result.update(extra)
    return result


def _points(value: Any, *, dimensions: int, name: str) -> List[List[float]]:
    if not _sequence(value) or len(value) < 3:
        raise ValueError(f"{name} needs at least three points")
    result: List[List[float]] = []
    for index, raw in enumerate(value):
        if not _sequence(raw) or len(raw) < dimensions:
            raise ValueError(f"{name}[{index}] needs {dimensions} coordinates")
        point: List[float] = []
        for coordinate in list(raw)[:dimensions]:
            parsed = _finite_number(coordinate)
            if parsed is None:
                raise ValueError(f"{name}[{index}] contains a non-finite coordinate")
            point.append(parsed)
        result.append(point)
    return result


def _faces(value: Any, vertex_count: int) -> List[List[int]]:
    if not _sequence(value) or not value:
        raise ValueError("candidate faces are required for a filled front projection")
    result: List[List[int]] = []
    for index, raw in enumerate(value):
        if not _sequence(raw) or len(raw) < 3:
            raise ValueError(f"face {index} needs at least three vertex indices")
        face: List[int] = []
        for token in raw:
            if isinstance(token, bool) or not isinstance(token, int):
                raise ValueError(f"face {index} has a non-integer index")
            if token < 0 or token >= vertex_count:
                raise ValueError(f"face {index} index is outside candidate vertices")
            face.append(token)
        result.append(face)
    return result


def _point_in_polygon(x: float, y: float, polygon: Sequence[Sequence[float]]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous[0], previous[1]
        x2, y2 = current[0], current[1]
        crosses = ((y1 > y) != (y2 > y))
        if crosses:
            intersection = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection:
                inside = not inside
        previous = current
    return inside


def _rasterise_polygons(
    polygons: Sequence[Sequence[Sequence[float]]], size: int,
) -> List[List[int]]:
    mask = [[0 for _ in range(size)] for _ in range(size)]
    for row in range(size):
        y = row + 0.5
        for column in range(size):
            x = column + 0.5
            if any(_point_in_polygon(x, y, polygon) for polygon in polygons):
                mask[row][column] = 1
    return mask


def _bbox(points: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    result = min(xs), min(ys), max(xs), max(ys)
    if result[2] - result[0] <= 1.0e-9 or result[3] - result[1] <= 1.0e-9:
        raise ValueError("projection points have a degenerate bounding box")
    return result


def _target_grid_polygon(
    outline: Sequence[Sequence[float]], width: float, height: float, size: int,
) -> List[List[float]]:
    if width <= 0 or height <= 0:
        raise ValueError("target width_px and height_px must be positive")
    scale = float(size - 1)
    return [[point[0] / width * scale, point[1] / height * scale]
            for point in outline]


def _aligned_candidate(
    vertices: Sequence[Sequence[float]], target_bbox: Tuple[float, float, float, float],
) -> Tuple[List[List[float]], Dict[str, Any]]:
    # Front projection is x/y. Image y grows downwards, so candidate y is
    # flipped. A single uniform scale preserves the candidate aspect ratio.
    source = [[point[0], -point[1]] for point in vertices]
    source_bbox = _bbox(source)
    source_width = source_bbox[2] - source_bbox[0]
    source_height = source_bbox[3] - source_bbox[1]
    target_width = target_bbox[2] - target_bbox[0]
    target_height = target_bbox[3] - target_bbox[1]
    scale = min(target_width / source_width, target_height / source_height)
    source_cx = (source_bbox[0] + source_bbox[2]) * 0.5
    source_cy = (source_bbox[1] + source_bbox[3]) * 0.5
    target_cx = (target_bbox[0] + target_bbox[2]) * 0.5
    target_cy = (target_bbox[1] + target_bbox[3]) * 0.5
    aligned = [[(point[0] - source_cx) * scale + target_cx,
                (point[1] - source_cy) * scale + target_cy]
               for point in source]
    return aligned, {
        "method": "UNIFORM_FRONT_FIT_TO_TARGET_BBOX",
        "authority": "PROPOSED_PREVIEW",
        "candidate_front_bbox": [round(value, 8) for value in source_bbox],
        "target_bbox": [round(value, 8) for value in target_bbox],
        "uniform_scale": round(scale, 12),
        "does_not_measure_body_or_depth": True,
    }


def _triangles(
    points: Sequence[Sequence[float]], faces: Sequence[Sequence[int]],
) -> List[List[List[float]]]:
    result: List[List[List[float]]] = []
    for face in faces:
        for index in range(1, len(face) - 1):
            result.append([
                list(points[face[0]]), list(points[face[index]]),
                list(points[face[index + 1]]),
            ])
    return result


def prepare_same_camera_projection(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Rasterise one bounded front target/candidate pair and compare it."""

    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            "UNKNOWN_SAME_CAMERA_PROJECTION_SCHEMA",
            f"schema must be exactly {REQUEST_SCHEMA}",
            received_schema=request.get("schema") if isinstance(request, Mapping) else None,
        )
    camera_digest = request.get("camera_digest")
    if not isinstance(camera_digest, str) or not camera_digest.strip():
        return _refusal(
            "UNKNOWN_SAME_CAMERA_PROJECTION_CAMERA_REQUIRED",
            "camera_digest from the selected visual target is required",
        )
    avatar = request.get("base_avatar")
    if (not isinstance(avatar, Mapping)
            or not isinstance(avatar.get("avatar_id"), str)
            or not isinstance(avatar.get("geometry_digest"), str)):
        return _refusal(
            "UNKNOWN_SAME_CAMERA_PROJECTION_AVATAR_REQUIRED",
            "the user-selected avatar id and geometry digest must be locked first",
            camera_digest=camera_digest,
        )
    target = request.get("target")
    candidate = request.get("candidate")
    if not isinstance(target, Mapping) or not isinstance(candidate, Mapping):
        return _refusal(
            "UNKNOWN_SAME_CAMERA_PROJECTION_INPUT_REQUIRED",
            "target and candidate objects are required",
            camera_digest=camera_digest,
        )
    target_state = str(target.get("state", "PROPOSED")).upper()
    if target_state not in {"OBSERVED", "HUMAN_CONFIRMED_TARGET"}:
        return _refusal(
            "UNKNOWN_SAME_CAMERA_TARGET_CONFIRMATION_REQUIRED",
            "same-camera iteration needs an observed image target or a digest-bound human CAD edit",
            camera_digest=camera_digest,
        )
    human_edit_digest = target.get("human_edit_digest")
    if (target_state == "HUMAN_CONFIRMED_TARGET"
            and (not isinstance(human_edit_digest, str) or not human_edit_digest)):
        return _refusal(
            "UNKNOWN_SAME_CAMERA_HUMAN_EDIT_DIGEST_REQUIRED",
            "a human-confirmed CAD target must carry its edit digest",
            camera_digest=camera_digest,
        )
    try:
        outline = _points(target.get("outline"), dimensions=2, name="target.outline")
        width = _finite_number(target.get("width_px"))
        height = _finite_number(target.get("height_px"))
        if width is None or height is None:
            raise ValueError("target width_px and height_px must be finite numbers")
        vertices = _points(candidate.get("vertices"), dimensions=3,
                           name="candidate.vertices")
        faces = _faces(candidate.get("faces"), len(vertices))
        size_raw = request.get("raster_size", 64)
        if isinstance(size_raw, bool) or not isinstance(size_raw, int) or not 24 <= size_raw <= 256:
            raise ValueError("raster_size must be an integer in [24, 256]")
        grid_outline = _target_grid_polygon(outline, width, height, size_raw)
        target_bbox = _bbox(grid_outline)
        aligned, alignment = _aligned_candidate(vertices, target_bbox)
    except ValueError as exc:
        return _refusal(
            "UNKNOWN_SAME_CAMERA_PROJECTION_INPUT",
            str(exc), camera_digest=camera_digest,
        )

    target_mask = _rasterise_polygons([grid_outline], size_raw)
    candidate_triangles = _triangles(aligned, faces)
    candidate_mask = _rasterise_polygons(candidate_triangles, size_raw)
    unknown_mask = [[0 for _ in range(size_raw)] for _ in range(size_raw)]
    part_id = "front-garment-surface"
    observation = {
        "camera_digest": camera_digest,
        "reference_authority": target_state,
        "human_edit_digest": human_edit_digest,
        "silhouette_mask": {"mask": target_mask,
                            "state": target_state},
        "typed_part_masks": {
            part_id: {"mask": copy.deepcopy(target_mask),
                      "state": target_state,
                      "layer": 0},
        },
        "occlusion_unknown_mask": unknown_mask,
    }
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        candidate_id = "candidate-preview"
    projection = {
        "candidate_id": candidate_id,
        "camera_digest": camera_digest,
        "silhouette_mask": {"mask": candidate_mask, "state": "PROPOSED"},
        "typed_part_masks": {
            part_id: {"mask": copy.deepcopy(candidate_mask),
                      "state": "PROPOSED", "layer": 0},
        },
        "occlusion_unknown_mask": copy.deepcopy(unknown_mask),
    }
    round_index = request.get("round_index", 1)
    if isinstance(round_index, bool) or not isinstance(round_index, int):
        return _refusal(
            "UNKNOWN_SAME_CAMERA_PROJECTION_ROUND",
            "round_index must be an integer",
            camera_digest=camera_digest,
        )
    previous = request.get("previous")
    config = request.get("config")
    evaluation = compare_front_projection(
        observation, projection, round_index=round_index,
        previous=previous if isinstance(previous, Mapping) else None,
        config=config if isinstance(config, Mapping) else None,
    )
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_SAME_CAMERA_COMPARISON",
        "state": "PROPOSED",
        "camera_digest": camera_digest,
        "base_avatar": {
            "avatar_id": avatar["avatar_id"],
            "geometry_digest": avatar["geometry_digest"],
            "locked_for_loop": True,
        },
        "alignment": alignment,
        "observation": observation,
        "candidate_projection": projection,
        "evaluation": evaluation,
        "target_digest": target.get("target_digest"),
        "human_edit_digest": human_edit_digest,
        "candidate_digest": stable_digest(candidate),
        "human_approval_required": True,
        "design_decision_owner": "HUMAN",
        "fact_promotions": [],
        "manufacturing_ready": False,
        "limitations": [
            "front-only raster alignment does not recover rear geometry or depth",
            "the first bridge compares one whole visible garment surface; per-part masks remain a separate extension",
            "metric convergence never adopts a design candidate automatically",
        ],
    }
    result["comparison_digest"] = stable_digest(copy.deepcopy(result))
    return result


prepare = prepare_same_camera_projection


__all__ = [
    "REQUEST_SCHEMA", "SCHEMA", "prepare_same_camera_projection", "prepare",
]
