# -*- coding: utf-8 -*-
"""Offline adapter for precomputed body/garment/hair/background evidence.

The adapter does not run or download a model.  It accepts either typed polygon
masks, or a local indexed/colour PNG produced by macOS Vision + a local
semantic stage, a local CoreML model, a VLM, or a human labelling tool.  It
normalises that evidence into ``body_image_separation``'s provider boundary.

Semantic masks and 2-D pose remain MODEL_PROPOSED.  A BODY mask is visible
image support, not a measurement of the body hidden by clothing.  Missing
channels are emitted as UNKNOWN and a front image never observes the rear.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .body_image_separation import separate_body_image, stable_digest


REQUEST_SCHEMA = "garment.body-image-separation.precomputed-adapter.request.v1"
SCHEMA = "garment.body-image-separation.precomputed-adapter.v1"
MASK_CLASSES = ("BODY", "GARMENT", "HAIR", "BACKGROUND")
PROVIDER_KINDS = {
    "MACOS_VISION_PRECOMPUTED",
    "LOCAL_COREML_PRECOMPUTED",
    "LOCAL_PYTHON_PRECOMPUTED",
    "LOCAL_VLM_PRECOMPUTED",
    "HUMAN_TOOL_PRECOMPUTED",
    "EXTERNAL_PRECOMPUTED_VISION",
}

Pixel = Union[int, Tuple[int, ...]]
RasterLoader = Callable[[Path], Tuple[int, int, Sequence[Pixel]]]


class _AdapterError(ValueError):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _refusal(request: Any, code: str, why: str, **detail: Any) -> Dict[str, Any]:
    result = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNKNOWN",
        "why": why,
        "rear_state": "UNKNOWN_UNOBSERVED",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        **copy.deepcopy(detail),
    }
    try:
        result["input_digest"] = stable_digest(request)
    except (TypeError, ValueError):
        result["input_digest"] = None
    result["adapter_digest"] = stable_digest(result)
    return result


def capability_probe(*, segmentation_path: Optional[str] = None) -> Dict[str, Any]:
    """Report local readiness without opening a network connection."""
    path = Path(segmentation_path).expanduser() if segmentation_path else None
    pillow_present = importlib.util.find_spec("PIL") is not None
    result = {
        "schema": SCHEMA,
        "verdict": "ANSWER",
        "state": "CAPABILITY_REPORT",
        "selected_route": "PRECOMPUTED_TYPED_MASK_AND_POSE",
        "routes": {
            "typed_polygon_bundle": {"ready": True, "dependency": None},
            "local_png_class_mask": {
                "ready": pillow_present and (path is None or path.is_file()),
                "dependency": "Pillow",
                "dependency_present": pillow_present,
                "configured_path_exists": None if path is None else path.is_file(),
            },
            "macos_vision": {
                "ready_as_precomputed_input": True,
                "direct_python_runtime": False,
                "existing_asset": "GarmentOutline.swift person/foreground segmentation",
                "semantic_gap": "Vision alone does not classify GARMENT or HAIR",
            },
            "local_coreml_or_vlm": {
                "ready_as_precomputed_input": True,
                "model_execution_owned_by_adapter": False,
            },
        },
        "network_used": False,
        "model_download_attempted": False,
        "rear_state": "UNKNOWN_UNOBSERVED",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["adapter_digest"] = stable_digest(result)
    return result


def _number(value: Any, *, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_NUMBER",
            "numeric values must be finite", location=location)
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_NUMBER",
            "numeric values must be finite", location=location)
    return parsed


def _source(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_SOURCE",
            "source must contain image_digest and positive dimensions")
    digest = value.get("image_digest")
    if not isinstance(digest, str) or not digest.strip():
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_SOURCE",
            "source.image_digest is required")
    width = _number(value.get("width"), location="source.width")
    height = _number(value.get("height"), location="source.height")
    if (width <= 0 or height <= 0
            or not width.is_integer() or not height.is_integer()):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_SOURCE",
            "source pixel dimensions must be positive integers")
    orientation = str(value.get("orientation", "UP")).upper()
    if orientation != "UP":
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_ORIENTATION",
            "precomputed mask and pose coordinates must be converted to upright image space",
            supplied_orientation=orientation)
    return {
        "image_digest": digest.strip(),
        "width": int(width),
        "height": int(height),
        "orientation": "UP",
    }


def _provenance(value: Any, *, provider_id: str,
                provider_kind: str) -> Dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_PROVENANCE",
            "provenance must be a typed object")
    result: Dict[str, Any] = {
        "provider_id": provider_id,
        "provider_kind": provider_kind,
        "authority": "PROPOSED_METADATA_NOT_CORRECTNESS_EVIDENCE",
        "is_correctness_evidence": False,
    }
    for key in (
        "producer", "model_id", "model_revision", "artifact_digest",
        "source_artifact", "generated_at", "license", "notes",
    ):
        if key not in value:
            continue
        raw = value[key]
        if not isinstance(raw, str) or not raw.strip():
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_PROVENANCE",
                "provenance string fields must be non-empty",
                location=f"provenance.{key}")
        result[key] = raw.strip()
    return result


def _pixel(value: Any, *, location: str) -> Pixel:
    if isinstance(value, bool):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_PIXEL",
            "class-map pixels must be an integer or an RGB/RGBA array",
            location=location)
    if isinstance(value, int) and 0 <= value <= 65535:
        return value
    if (isinstance(value, Sequence) and not isinstance(value, (str, bytes))
            and len(value) in {3, 4}):
        if any(isinstance(component, bool)
               or not isinstance(component, (int, float))
               or not math.isfinite(float(component))
               or not float(component).is_integer()
               for component in value):
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_PIXEL",
                "RGB/RGBA class-map components must be integer values",
                location=location)
        output = tuple(int(component) for component in value)
        if all(0 <= component <= 255 for component in output):
            return output
    raise _AdapterError(
        "UNKNOWN_PRECOMPUTED_SEPARATION_PIXEL",
        "class-map pixels must be an integer or an RGB/RGBA array",
        location=location)


def _default_raster_loader(path: Path) -> Tuple[int, int, Sequence[Pixel]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_PILLOW_REQUIRED",
            "Pillow is required only for local PNG class masks; polygon input remains available",
        ) from exc
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            if image.mode in {"1", "L", "P", "I", "I;16"}:
                pixels: Sequence[Pixel] = [int(value) for value in image.getdata()]
            else:
                converted = image.convert("RGBA")
                pixels = [tuple(int(component) for component in value)
                          for value in converted.getdata()]
    except (OSError, ValueError) as exc:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_UNREADABLE",
            f"could not decode local segmentation PNG: {exc}") from exc
    return width, height, pixels


def _components(selected: Sequence[bool], width: int, height: int) -> List[List[int]]:
    visited = bytearray(width * height)
    output: List[List[int]] = []
    for start in range(width * height):
        if visited[start] or not selected[start]:
            continue
        visited[start] = 1
        queue = deque([start])
        component: List[int] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            x, y = current % width, current // width
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    index = ny * width + nx
                    if not visited[index] and selected[index]:
                        visited[index] = 1
                        queue.append(index)
        output.append(component)
    output.sort(key=lambda row: (-len(row), row[0]))
    return output


def _distance(point: Tuple[float, float], start: Tuple[float, float],
              end: Tuple[float, float]) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0.0 and dy == 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs(dy * point[0] - dx * point[1]
               + end[0] * start[1] - end[1] * start[0]) / math.hypot(dx, dy)


def _rdp(points: Sequence[Tuple[float, float]], epsilon: float) -> List[Tuple[float, float]]:
    if len(points) <= 2:
        return list(points)
    distances = [(_distance(point, points[0], points[-1]), index)
                 for index, point in enumerate(points[1:-1], start=1)]
    maximum, index = max(distances, default=(0.0, 0))
    if maximum <= epsilon:
        return [points[0], points[-1]]
    return _rdp(points[:index + 1], epsilon)[:-1] + _rdp(points[index:], epsilon)


def _scanline_outline(component: Sequence[int], width: int,
                      height: int) -> List[List[float]]:
    rows: Dict[int, Tuple[int, int]] = {}
    for index in component:
        x, y = index % width, index // width
        if y not in rows:
            rows[y] = (x, x)
        else:
            rows[y] = (min(rows[y][0], x), max(rows[y][1], x))
    left = [(float(x0), float(y)) for y, (x0, _) in sorted(rows.items())]
    right = [(float(x1 + 1), float(y + 1))
             for y, (_, x1) in reversed(sorted(rows.items()))]
    polygon = _rdp(left, 0.75) + _rdp(right, 0.75)
    unique: List[Tuple[float, float]] = []
    for point in polygon:
        if not unique or point != unique[-1]:
            unique.append(point)
    return [[round(x / max(width, 1), 8), round(y / max(height, 1), 8)]
            for x, y in unique]


def _mask_digest(component: Sequence[int], width: int, height: int) -> str:
    encoded = json.dumps(
        {"width": width, "height": height, "pixels": list(component)},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _direct_masks(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_MASKS",
            "masks must be an array of typed polygon or digest records")
    output: List[Dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_MASKS",
                "every direct mask must be an object", location=f"masks[{index}]")
        mask_class = str(raw.get("class", "")).upper()
        if mask_class not in MASK_CLASSES:
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_CLASS",
                "mask class must be BODY, GARMENT, HAIR, or BACKGROUND",
                location=f"masks[{index}]")
        outline = raw.get("outline", [])
        if not isinstance(outline, Sequence) or isinstance(outline, (str, bytes)):
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_MASKS",
                "mask outline must be an array", location=f"masks[{index}].outline")
        points: List[List[float]] = []
        for point_index, point in enumerate(outline):
            if (not isinstance(point, Sequence)
                    or isinstance(point, (str, bytes)) or len(point) < 2):
                raise _AdapterError(
                    "UNKNOWN_PRECOMPUTED_SEPARATION_MASKS",
                    "every outline point must contain normalised x and y",
                    location=f"masks[{index}].outline[{point_index}]",
                )
            x = _number(point[0], location=f"masks[{index}].outline[{point_index}].x")
            y = _number(point[1], location=f"masks[{index}].outline[{point_index}].y")
            if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                raise _AdapterError(
                    "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_RANGE",
                    "direct polygon coordinates must be normalised to 0..1",
                    location=f"masks[{index}].outline[{point_index}]",
                )
            points.append([round(x, 8), round(y, 8)])
        digest = raw.get("mask_digest")
        if not isinstance(digest, str) or not digest.strip():
            digest = "sha256:" + stable_digest(points) if len(points) >= 3 else None
        supplied_mask_id = raw.get("mask_id")
        if supplied_mask_id is None:
            mask_id = f"direct:{mask_class.lower()}:{index}"
        elif isinstance(supplied_mask_id, str) and supplied_mask_id.strip():
            mask_id = supplied_mask_id.strip()
        else:
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_ID",
                "mask_id must be a non-empty string",
                location=f"masks[{index}].mask_id")
        record = {
            "mask_id": mask_id,
            "class": mask_class,
            "garment_unit_id": raw.get("garment_unit_id"),
            "layer": raw.get("layer"),
            "confidence": round(max(0.0, min(1.0, _number(
                raw.get("confidence", 1.0), location=f"masks[{index}].confidence"))), 8),
            "authority": "MODEL_PROPOSED" if digest or points else "UNKNOWN",
            "mask_digest": digest,
        }
        if points:
            record["outline"] = points
        output.append(record)
    return output


def _raster_masks(value: Any, *, source: Mapping[str, Any],
                  raster_loader: Optional[RasterLoader]) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Mapping):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_SEGMENTATION",
            "segmentation must be a typed local PNG class-mask object")
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_PATH",
            "segmentation.path is required")
    if "://" in raw_path:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_LOCAL_ONLY",
            "segmentation masks must be local files; URL schemes are refused")
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_PATH",
            "configured segmentation path does not exist", path=str(path))
    loader = raster_loader or _default_raster_loader
    width, height, pixels = loader(path)
    if width <= 0 or height <= 0 or len(pixels) != width * height:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_DIMENSIONS",
            "segmentation raster dimensions and pixel count disagree")
    if width != source["width"] or height != source["height"]:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_ALIGNMENT",
            "segmentation raster must already be aligned to upright source pixels",
            source_dimensions=[source["width"], source["height"]],
            mask_dimensions=[width, height])
    class_map = value.get("class_map")
    if not isinstance(class_map, Sequence) or isinstance(class_map, (str, bytes)):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_CLASS_MAP",
            "segmentation.class_map must be an array")
    minimum_value = _number(
        value.get("min_component_pixels", 4),
        location="segmentation.min_component_pixels")
    maximum_value = _number(
        value.get("max_components_per_label", 8),
        location="segmentation.max_components_per_label")
    if not minimum_value.is_integer() or not maximum_value.is_integer():
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_COMPONENT_BOUND",
            "component bounds must be integer values")
    minimum, maximum = int(minimum_value), int(maximum_value)
    if minimum < 1 or maximum < 1 or maximum > 64:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_COMPONENT_BOUND",
            "component bounds must be positive and max_components_per_label <= 64")
    output: List[Dict[str, Any]] = []
    claimed_pixels: Dict[Pixel, str] = {}
    for label_index, raw in enumerate(class_map):
        if not isinstance(raw, Mapping):
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_CLASS_MAP",
                "every class-map row must be an object")
        mask_class = str(raw.get("class", "")).upper()
        if mask_class not in MASK_CLASSES:
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_CLASS",
                "class-map class must be BODY, GARMENT, HAIR, or BACKGROUND")
        target = _pixel(raw.get("pixel"), location=f"class_map[{label_index}].pixel")
        if target in claimed_pixels:
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_CLASS_MAP_OVERLAP",
                "one raster value cannot assert more than one semantic class",
                pixel=list(target) if isinstance(target, tuple) else target,
                first_class=claimed_pixels[target],
                second_class=mask_class,
            )
        claimed_pixels[target] = mask_class
        selected = [pixel == target for pixel in pixels]
        components = [row for row in _components(selected, width, height)
                      if len(row) >= minimum][:maximum]
        for component_index, component in enumerate(components):
            outline = _scanline_outline(component, width, height)
            base_mask_id = raw.get("mask_id")
            if base_mask_id is not None and (
                    not isinstance(base_mask_id, str) or not base_mask_id.strip()):
                raise _AdapterError(
                    "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_ID",
                    "class-map mask_id must be a non-empty string",
                    location=f"class_map[{label_index}].mask_id")
            mask_id = (f"{base_mask_id.strip()}:{component_index}"
                       if base_mask_id is not None
                       else f"raster:{label_index}:{component_index}")
            output.append({
                "mask_id": str(mask_id),
                "class": mask_class,
                "garment_unit_id": raw.get("garment_unit_id"),
                "layer": raw.get("layer"),
                "confidence": round(max(0.0, min(1.0, _number(
                    raw.get("confidence", 1.0),
                    location=f"class_map[{label_index}].confidence"))), 8),
                "authority": "MODEL_PROPOSED",
                "mask_digest": _mask_digest(component, width, height),
                "outline": outline,
            })
    return output


def _pose(value: Any, *, source: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Mapping):
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_POSE",
            "pose must contain coordinate_space, origin and keypoints")
    points = value.get("keypoints")
    if isinstance(points, Mapping):
        rows = [(str(name), raw) for name, raw in points.items()]
    elif isinstance(points, Sequence) and not isinstance(points, (str, bytes)):
        rows = [(str(raw.get("name", raw.get("id", ""))), raw)
                for raw in points if isinstance(raw, Mapping)]
    else:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_POSE",
            "pose.keypoints must be a mapping or array")
    coordinate_space = str(value.get("coordinate_space", "NORMALIZED")).upper()
    origin = str(value.get("origin", "TOP_LEFT")).upper()
    if coordinate_space not in {"NORMALIZED", "PIXELS"} or origin not in {
            "TOP_LEFT", "BOTTOM_LEFT"}:
        raise _AdapterError(
            "UNKNOWN_PRECOMPUTED_SEPARATION_POSE_COORDINATES",
            "pose coordinates require NORMALIZED|PIXELS and TOP_LEFT|BOTTOM_LEFT")
    output: List[Dict[str, Any]] = []
    for name, raw in sorted(rows):
        if not name or not isinstance(raw, Mapping):
            continue
        x = _number(raw.get("x"), location=f"pose.{name}.x")
        y = _number(raw.get("y"), location=f"pose.{name}.y")
        if coordinate_space == "PIXELS":
            x /= source["width"]
            y /= source["height"]
        if origin == "BOTTOM_LEFT":
            y = 1.0 - y
        confidence = _number(raw.get("confidence", 1.0),
                             location=f"pose.{name}.confidence")
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0 or not 0.0 <= confidence <= 1.0:
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_POSE_RANGE",
                "normalised pose coordinates and confidence must be within 0..1",
                keypoint=name)
        output.append({
            "name": name,
            "x": round(x, 8),
            "y": round(y, 8),
            "confidence": round(confidence, 8),
            "authority": "MODEL_PROPOSED",
        })
    return output


def build_provider_output(
    request: Mapping[str, Any], *, raster_loader: Optional[RasterLoader] = None,
) -> Dict[str, Any]:
    """Build one provider output accepted by ``separate_body_image``."""
    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            request, "UNKNOWN_PRECOMPUTED_SEPARATION_SCHEMA",
            f"request schema must be {REQUEST_SCHEMA}")
    try:
        source = _source(request.get("source"))
        provider_id = request.get("provider_id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_PROVIDER_ID",
                "provider_id is required")
        provider_kind = str(
            request.get("provider_kind", "EXTERNAL_PRECOMPUTED_VISION")).upper()
        if provider_kind not in PROVIDER_KINDS:
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_PROVIDER_KIND",
                "provider_kind is outside the closed precomputed vocabulary",
                provider_kind=provider_kind)
        provenance = _provenance(
            request.get("provenance"), provider_id=provider_id.strip(),
            provider_kind=provider_kind)
        masks = _direct_masks(request.get("masks"))
        masks.extend(_raster_masks(
            request.get("segmentation"), source=source,
            raster_loader=raster_loader))
        mask_ids = [row["mask_id"] for row in masks]
        if len(mask_ids) != len(set(mask_ids)):
            raise _AdapterError(
                "UNKNOWN_PRECOMPUTED_SEPARATION_DUPLICATE_MASK_ID",
                "precomputed mask ids must be unique")
        pose = _pose(request.get("pose"), source=source)
    except _AdapterError as exc:
        return _refusal(request, exc.code, exc.why, **exc.detail)

    present = {row["class"] for row in masks}
    for mask_class in MASK_CLASSES:
        if mask_class not in present:
            masks.append({
                "mask_id": f"missing:{mask_class.lower()}",
                "class": mask_class,
                "garment_unit_id": None,
                "layer": None,
                "confidence": 0.0,
                "authority": "UNKNOWN",
                "mask_digest": None,
            })
    masks.sort(key=lambda row: (
        MASK_CLASSES.index(row["class"]), str(row["mask_id"])))
    provider = {
        "provider_id": provider_id.strip(),
        "provider_kind": provider_kind,
        "authority": "MODEL_PROPOSED",
        "provenance": copy.deepcopy(provenance),
        "pose_keypoints": pose,
        "masks": masks,
        "camera": {
            "view": str(request.get("camera", {}).get("view", "UNKNOWN")).upper()
                if isinstance(request.get("camera"), Mapping) else "UNKNOWN",
            "orientation": "UP",
            "width_px": source["width"],
            "height_px": source["height"],
            "authority": "MODEL_PROPOSED",
        },
        "body_dimension_ranges_cm": {},
        "shape_coefficients": {"values": [], "authority": "UNKNOWN"},
    }
    result = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_PRECOMPUTED_PROVIDER_OUTPUT",
        "state": "PROPOSED",
        "source": source,
        "provider_provenance": provenance,
        "provider_output": provider,
        "channel_availability": {
            mask_class: {
                "available": any(
                    row["class"] == mask_class
                    and (row.get("mask_digest") or len(row.get("outline", [])) >= 3)
                    for row in masks),
                "authority": "MODEL_PROPOSED" if mask_class in present else "UNKNOWN",
            }
            for mask_class in MASK_CLASSES
        },
        "limitations": [
            "BODY is visible semantic image support, not the body surface hidden by clothing",
            "class semantics remain MODEL_PROPOSED until a human audit confirms them",
            "scanline outlines preserve outer row envelopes, not holes or all concavities",
            "a front mask and front pose do not observe any rear surface",
        ],
        "network_used": False,
        "model_download_attempted": False,
        "rear_state": "UNKNOWN_UNOBSERVED",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["adapter_digest"] = stable_digest(result)
    return result


def adapt_and_separate(
    request: Mapping[str, Any], *, raster_loader: Optional[RasterLoader] = None,
) -> Dict[str, Any]:
    """Build provider evidence and execute the existing typed boundary."""
    adapted = build_provider_output(request, raster_loader=raster_loader)
    if adapted.get("verdict") != "PROPOSED_PRECOMPUTED_PROVIDER_OUTPUT":
        return adapted
    separation_request = {
        "schema": "garment.body-image-separation.request.v1",
        "source": copy.deepcopy(adapted["source"]),
        "selection_mode": str(
            request.get("selection_mode", "HUMAN_APPROVAL")).upper(),
        "provider_outputs": [copy.deepcopy(adapted["provider_output"])],
    }
    separation = separate_body_image(separation_request)
    result = {
        "schema": SCHEMA,
        "verdict": separation.get("verdict"),
        "state": separation.get("state", "UNKNOWN"),
        "adapter": adapted,
        "separation": separation,
        "network_used": False,
        "model_download_attempted": False,
        "rear_state": "UNKNOWN_UNOBSERVED",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["adapter_digest"] = stable_digest(result)
    return result


run = adapt_and_separate
probe = capability_probe
