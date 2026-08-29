#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline, filename-neutral E2E evaluation for front fashion crops.

This harness deliberately evaluates geometry, not garment-name accuracy.  It
uses no network and loads no ML model.  For each readable image it records:

* frame readability and orientation;
* a foreground principal-axis proxy (never asserted as camera viewpoint);
* one or more border-contrast foreground candidates;
* geometry-only part partitions;
* a fused editable target 3-D proposal;
* multiple existing Photoloset structure hypotheses, each compiled to its own
  3-D preview and flat pattern or retained as a typed stop.

Basenames, filename labels, and particular RGB values are never passed to the
inference stages.  The semantic result identifies an input by content digest.
No woman/man/female/male label is inferred from appearance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from photoloset import construction_regime  # noqa: E402
from photoloset import front_geometry_cues  # noqa: E402
from photoloset import front_region_structure_cues  # noqa: E402
from photoloset import parts_ir_completion  # noqa: E402
from photoloset import parts_ir_pipeline  # noqa: E402
from photoloset import structure_preview  # noqa: E402
from photoloset import structure_to_pattern  # noqa: E402
from photoloset.target_reconstruction import (  # noqa: E402
    prepare_target_reconstruction,
    stable_digest as target_digest,
)


SCHEMA = "photoloset.fashion-crops-e2e-evaluation.v1"
ITEM_SCHEMA = "photoloset.fashion-crop-e2e-item.v1"
DEFAULT_INPUT_DIR = Path("/Users/motonishikoudai/Desktop/vera_fashion_crops_20")
DEFAULT_MANIFEST = REPO_ROOT / "tests/fixtures/fashion_crops_20_manifest.json"
PROPOSED = "PROPOSED"
UNKNOWN = "UNKNOWN"
AUTO_PROPOSED = "AUTO_PROPOSED"
HUMAN_AUDIT = "HUMAN_AUDIT"


class ImageReadStop(Exception):
    def __init__(self, code: str, why: str):
        super().__init__(why)
        self.code = code
        self.why = why


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def _digest(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    else:
        payload = _canonical(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _typed_stop(code: str, why: str, *, stage: str,
                how_to_close: str) -> Dict[str, Any]:
    return {
        "verdict": code,
        "state": UNKNOWN,
        "typed_stop": True,
        "stage": stage,
        "why": why,
        "how_to_close": how_to_close,
    }


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (
        (abs(estimate - left), left),
        (abs(estimate - above), above),
        (abs(estimate - upper_left), upper_left),
    )
    return min(distances, key=lambda row: row[0])[1]


def _read_png(path: Path) -> Dict[str, Any]:
    """Read common 8-bit, non-interlaced PNGs using only the stdlib."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ImageReadStop("UNKNOWN_INPUT_UNREADABLE", str(exc)) from exc
    content_digest = _digest(payload)
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ImageReadStop(
            "UNKNOWN_INPUT_FORMAT", "input is not a PNG byte stream")
    position = 8
    width = height = bit_depth = colour_type = interlace = None
    compressed: List[bytes] = []
    while position + 12 <= len(payload):
        length = struct.unpack(">I", payload[position:position + 4])[0]
        end = position + 12 + length
        if end > len(payload):
            raise ImageReadStop(
                "UNKNOWN_INPUT_TRUNCATED", "PNG chunk extends past end of file")
        chunk_type = payload[position + 4:position + 8]
        chunk = payload[position + 8:position + 8 + length]
        position = end
        if chunk_type == b"IHDR":
            if length != 13:
                raise ImageReadStop(
                    "UNKNOWN_INPUT_PNG_HEADER", "PNG IHDR has an invalid length")
            (width, height, bit_depth, colour_type, compression,
             filtering, interlace) = struct.unpack(">IIBBBBB", chunk)
            if compression != 0 or filtering != 0:
                raise ImageReadStop(
                    "UNKNOWN_INPUT_PNG_ENCODING", "unsupported PNG compression/filter method")
        elif chunk_type == b"IDAT":
            compressed.append(chunk)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or not compressed:
        raise ImageReadStop(
            "UNKNOWN_INPUT_PNG_PAYLOAD", "PNG has no usable IHDR/IDAT payload")
    if width <= 0 or height <= 0 or width * height > 80_000_000:
        raise ImageReadStop(
            "UNKNOWN_INPUT_DIMENSIONS", "PNG dimensions are empty or exceed the evaluation bound")
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    channels = channels_by_type.get(colour_type)
    if bit_depth != 8 or channels is None or interlace != 0:
        raise ImageReadStop(
            "UNKNOWN_INPUT_PNG_ENCODING",
            "evaluation supports 8-bit non-interlaced grayscale/RGB/RGBA PNGs",
        )
    try:
        raw = zlib.decompress(b"".join(compressed))
    except zlib.error as exc:
        raise ImageReadStop("UNKNOWN_INPUT_PNG_DEFLATE", str(exc)) from exc
    stride = width * channels
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ImageReadStop(
            "UNKNOWN_INPUT_PNG_SCANLINES",
            f"decoded scanline bytes {len(raw)} do not match expected {expected}",
        )
    rows: List[List[Tuple[int, int, int, int]]] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scanline = bytearray(raw[offset:offset + stride])
        offset += stride
        for index in range(stride):
            left = scanline[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                scanline[index] = (scanline[index] + left) & 0xFF
            elif filter_type == 2:
                scanline[index] = (scanline[index] + above) & 0xFF
            elif filter_type == 3:
                scanline[index] = (scanline[index] + (left + above) // 2) & 0xFF
            elif filter_type == 4:
                scanline[index] = (
                    scanline[index] + _paeth(left, above, upper_left)) & 0xFF
            elif filter_type != 0:
                raise ImageReadStop(
                    "UNKNOWN_INPUT_PNG_FILTER", f"unsupported PNG filter {filter_type}")
        pixels: List[Tuple[int, int, int, int]] = []
        for x in range(width):
            start = x * channels
            if colour_type == 0:
                value = scanline[start]
                pixels.append((value, value, value, 255))
            elif colour_type == 2:
                pixels.append((scanline[start], scanline[start + 1],
                               scanline[start + 2], 255))
            elif colour_type == 4:
                value = scanline[start]
                pixels.append((value, value, value, scanline[start + 1]))
            else:
                pixels.append(tuple(scanline[start:start + 4]))  # type: ignore[arg-type]
        rows.append(pixels)
        previous = scanline
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "colour_type": colour_type,
        "rows": rows,
        "content_digest": content_digest,
        "bytes": len(payload),
    }


def _frame_orientation(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if ratio <= 0.90:
        return "PORTRAIT"
    if ratio >= 1.10:
        return "LANDSCAPE"
    return "SQUARE"


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(
        quantile * (len(ordered) - 1)))))
    return float(ordered[index])


def _mean_colour(values: Sequence[Tuple[int, int, int, int]]) -> Tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    return tuple(sum(row[channel] for row in values) / len(values)
                 for channel in range(3))  # type: ignore[return-value]


def _colour_distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _foreground_mask(image: Mapping[str, Any]) -> Tuple[List[List[bool]], Dict[str, Any]]:
    width, height = int(image["width"]), int(image["height"])
    rows = image["rows"]
    edge = max(1, min(6, width // 14))
    backgrounds: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = []
    border_residuals: List[float] = []
    for row in rows:
        left = _mean_colour(row[:edge])
        right = _mean_colour(row[-edge:])
        backgrounds.append((left, right))
        border_residuals.extend(_colour_distance(pixel, left) for pixel in row[:edge])
        border_residuals.extend(_colour_distance(pixel, right) for pixel in row[-edge:])
    threshold = min(96.0, max(22.0, _percentile(border_residuals, 0.95) + 14.0))
    mask: List[List[bool]] = []
    opaque_count = 0
    for y, row in enumerate(rows):
        left, right = backgrounds[y]
        output_row: List[bool] = []
        for x, pixel in enumerate(row):
            amount = x / max(width - 1, 1)
            background = tuple(
                left[channel] * (1.0 - amount) + right[channel] * amount
                for channel in range(3)
            )
            alpha_salient = pixel[3] >= 32
            if alpha_salient:
                opaque_count += 1
            output_row.append(
                alpha_salient and _colour_distance(pixel, background) >= threshold)
        mask.append(output_row)
    return mask, {
        "method": "ROW_BORDER_INTERPOLATED_RGB_DISTANCE",
        "state": PROPOSED,
        "threshold": round(threshold, 6),
        "edge_sample_width_px": edge,
        "opaque_fraction": round(opaque_count / max(width * height, 1), 6),
        "uses_filename": False,
        "uses_named_colour": False,
        "uses_garment_class": False,
    }


Point = Tuple[int, int]


def _components(mask: Sequence[Sequence[bool]]) -> List[List[Point]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    visited = bytearray(width * height)
    components: List[List[Point]] = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if visited[index] or not mask[y][x]:
                continue
            visited[index] = 1
            queue = deque([(x, y)])
            points: List[Point] = []
            while queue:
                px, py = queue.popleft()
                points.append((px, py))
                for ny in range(max(0, py - 1), min(height, py + 2)):
                    for nx in range(max(0, px - 1), min(width, px + 2)):
                        child = ny * width + nx
                        if not visited[child] and mask[ny][nx]:
                            visited[child] = 1
                            queue.append((nx, ny))
            components.append(points)
    components.sort(key=lambda row: (-len(row), min(row) if row else (0, 0)))
    return components


def _cross(origin: Point, left: Point, right: Point) -> int:
    return ((left[0] - origin[0]) * (right[1] - origin[1])
            - (left[1] - origin[1]) * (right[0] - origin[0]))


def _convex_hull(points: Iterable[Point]) -> List[Point]:
    unique = sorted(set(points))
    if len(unique) < 3:
        return []
    lower: List[Point] = []
    for point in unique:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: List[Point] = []
    for point in reversed(unique):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _bbox(points: Sequence[Point]) -> List[int]:
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _normalised_bbox(box: Sequence[int], width: int, height: int) -> List[float]:
    return [
        round(box[0] / max(width, 1), 6),
        round(box[1] / max(height, 1), 6),
        round((box[2] + 1) / max(width, 1), 6),
        round((box[3] + 1) / max(height, 1), 6),
    ]


def _candidate_from_components(
    components: Sequence[Sequence[Point]], *, width: int, height: int,
    role: str,
) -> Optional[Dict[str, Any]]:
    points = [point for component in components for point in component]
    hull = _convex_hull(points)
    if len(hull) < 3:
        return None
    identity = {
        "role": role,
        "outline": hull,
        "component_sizes": sorted((len(row) for row in components), reverse=True),
    }
    return {
        "candidate_id": "foreground-" + _digest(identity)[:16],
        "state": PROPOSED,
        "authority": "PROPOSED_PIXEL_FOREGROUND",
        "role": role,
        "point_count": len(points),
        "component_count": len(components),
        "coverage_fraction": round(len(points) / max(width * height, 1), 6),
        "bbox_normalized": _normalised_bbox(_bbox(points), width, height),
        "outline_digest": _digest(hull),
        "outline_px": [[float(x), float(y)] for x, y in hull],
        "_points": points,
        "_components": [list(row) for row in components],
    }


def _foreground_candidates(image: Mapping[str, Any]) -> Dict[str, Any]:
    width, height = int(image["width"]), int(image["height"])
    mask, method = _foreground_mask(image)
    raw_components = _components(mask)
    minimum = max(8, int(width * height * 0.0015))
    components = [row for row in raw_components if len(row) >= minimum]
    if not components:
        return {
            **_typed_stop(
                "UNKNOWN_FOREGROUND_NOT_SEPARABLE",
                "border-relative segmentation produced no salient connected component",
                stage="FOREGROUND_CANDIDATES",
                how_to_close="supply a human-corrected mask or a more separable crop",
            ),
            "method": method,
            "candidates": [],
        }
    if len(components[0]) / max(width * height, 1) >= 0.92:
        return {
            **_typed_stop(
                "UNKNOWN_FOREGROUND_BACKGROUND_AMBIGUOUS",
                "the largest proposed component covers nearly the entire frame",
                stage="FOREGROUND_CANDIDATES",
                how_to_close="provide a foreground mask or confirm the full-frame subject",
            ),
            "method": method,
            "candidates": [],
        }
    significant = [row for row in components[:12]
                   if len(row) >= max(minimum, int(len(components[0]) * 0.02))]
    candidates: List[Dict[str, Any]] = []
    primary = _candidate_from_components(
        [components[0]], width=width, height=height, role="LARGEST_COMPONENT")
    if primary is not None:
        candidates.append(primary)
    union = _candidate_from_components(
        significant, width=width, height=height, role="SALIENT_COMPONENT_UNION")
    if union is not None and all(
            row["outline_digest"] != union["outline_digest"] for row in candidates):
        candidates.append(union)
    return {
        "verdict": "PROPOSED_FOREGROUND_CANDIDATES",
        "state": PROPOSED,
        "typed_stop": False,
        "method": method,
        "raw_component_count": len(raw_components),
        "salient_component_count": len(components),
        "candidate_count": len(candidates),
        "auto_selected_candidate_id": None,
        "human_review_required": True,
        "candidates": candidates,
    }


def _axis_orientation(points: Sequence[Point]) -> Dict[str, Any]:
    if len(points) < 3:
        return {
            "state": UNKNOWN,
            "verdict": "UNKNOWN_FOREGROUND_AXIS",
            "axis_orientation": "UNKNOWN",
            "camera_viewpoint": "UNKNOWN_SINGLE_VIEW_CAMERA_VIEWPOINT",
        }
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    xx = sum((point[0] - mean_x) ** 2 for point in points) / len(points)
    yy = sum((point[1] - mean_y) ** 2 for point in points) / len(points)
    xy = sum((point[0] - mean_x) * (point[1] - mean_y)
             for point in points) / len(points)
    angle = 0.5 * math.degrees(math.atan2(2.0 * xy, xx - yy))
    if angle < 0.0:
        angle += 180.0
    horizontal_distance = min(angle, abs(180.0 - angle))
    vertical_distance = abs(90.0 - angle)
    if vertical_distance <= 22.5:
        orientation = "VERTICAL"
    elif horizontal_distance <= 22.5:
        orientation = "HORIZONTAL"
    else:
        orientation = "DIAGONAL"
    return {
        "state": PROPOSED,
        "authority": "PROPOSED_FOREGROUND_PRINCIPAL_AXIS",
        "axis_orientation": orientation,
        "principal_axis_degrees_from_positive_x": round(angle, 6),
        "tilt_from_vertical_degrees": round(vertical_distance, 6),
        "camera_viewpoint": "UNKNOWN_SINGLE_VIEW_CAMERA_VIEWPOINT",
        "axis_is_not_camera_pose": True,
    }


def _viewpoint_proxy(points: Sequence[Point]) -> Dict[str, Any]:
    """Classify only silhouette symmetry; never claim an observed camera pose."""
    if len(points) < 3:
        return {
            "state": UNKNOWN,
            "view_bucket": "UNKNOWN_FRONT_OR_OBLIQUE",
            "camera_viewpoint_observed": False,
        }
    left, _, right, _ = _bbox(points)
    occupied = set(points)
    mirrored = {(left + right - x, y) for x, y in occupied}
    union = occupied | mirrored
    mirror_iou = len(occupied & mirrored) / max(len(union), 1)
    asymmetry = 1.0 - mirror_iou
    bucket = "FRONT_LIKE" if asymmetry <= 0.34 else "OBLIQUE_LIKE"
    return {
        "state": PROPOSED,
        "authority": "AUTO_PROPOSED_GEOMETRIC_SYMMETRY_PROXY",
        "view_bucket": bucket,
        "mirror_iou": round(mirror_iou, 6),
        "asymmetry": round(asymmetry, 6),
        "camera_viewpoint_observed": False,
        "limitation": (
            "pose, asymmetric clothing, hair, props, and segmentation errors can "
            "change this front-like/oblique-like silhouette proxy"
        ),
    }


def _region_summary(points: Sequence[Point], width: int, height: int,
                    region_id: str) -> Dict[str, Any]:
    return {
        "region_id": region_id,
        "state": PROPOSED,
        "role": "GEOMETRIC_VISIBLE_REGION",
        "point_count": len(points),
        "bbox_normalized": _normalised_bbox(_bbox(points), width, height),
    }


def _region_wire(part_candidate: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for region in part_candidate.get("regions", []):
        if not isinstance(region, Mapping):
            continue
        box = region.get("bbox_normalized")
        if (not isinstance(box, Sequence) or isinstance(box, (str, bytes))
                or len(box) != 4):
            continue
        x0, y0, x1, y1 = (float(value) for value in box)
        rows.append({
            "region_id": str(region.get("region_id", f"region-{len(rows)}")),
            "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            "coordinate_space": "normalized",
            "labels": ["geometric visible region"],
            "confidence": "unknown",
            "provenance": {"kind": PROPOSED},
        })
    return rows


def _part_candidates(candidate: Mapping[str, Any], *, width: int,
                     height: int) -> Dict[str, Any]:
    points: List[Point] = list(candidate.get("_points", []))
    if len(points) < 3:
        return {
            **_typed_stop(
                "UNKNOWN_PART_CANDIDATES_FOREGROUND_REQUIRED",
                "part partitioning requires a non-degenerate foreground",
                stage="PART_CANDIDATES",
                how_to_close="approve or correct one foreground candidate",
            ),
            "candidates": [],
        }
    box = _bbox(points)
    top, bottom = box[1], box[3]
    span_y = max(1, bottom - top + 1)
    rows = Counter(y for _, y in points)
    occupancy = [rows.get(y, 0) / max(box[2] - box[0] + 1, 1)
                 for y in range(top, bottom + 1)]
    smooth = []
    for index in range(len(occupancy)):
        window = occupancy[max(0, index - 2):min(len(occupancy), index + 3)]
        smooth.append(sum(window) / len(window))
    start, end = int(span_y * 0.25), int(span_y * 0.76)
    trough_index = min(range(start, max(start + 1, end)),
                       key=lambda index: (smooth[index], index))
    left_window = smooth[max(0, trough_index - max(3, span_y // 10)):trough_index]
    right_window = smooth[trough_index + 1:min(
        len(smooth), trough_index + 1 + max(3, span_y // 10))]
    shoulders = ((sum(left_window) / len(left_window)) if left_window else 0.0,
                 (sum(right_window) / len(right_window)) if right_window else 0.0)
    contrast = min(shoulders) - smooth[trough_index]
    partitions: List[Dict[str, Any]] = [{
        "part_candidate_id": "parts-" + _digest({
            "foreground": candidate["candidate_id"], "partition": "whole",
        })[:16],
        "state": PROPOSED,
        "partition_basis": "UNPARTITIONED_FOREGROUND",
        "regions": [_region_summary(points, width, height, "region-0")],
        "semantic_classification": "NOT_PERFORMED",
    }]
    split_y = top + trough_index
    upper = [point for point in points if point[1] <= split_y]
    lower = [point for point in points if point[1] > split_y]
    if contrast >= 0.10 and len(upper) >= len(points) * 0.12 and len(lower) >= len(points) * 0.12:
        partitions.append({
            "part_candidate_id": "parts-" + _digest({
                "foreground": candidate["candidate_id"], "split_y": split_y,
            })[:16],
            "state": PROPOSED,
            "partition_basis": "ROW_OCCUPANCY_TROUGH",
            "split_y_normalized": round(split_y / max(height, 1), 6),
            "trough_contrast": round(contrast, 6),
            "regions": [
                _region_summary(upper, width, height, "region-0"),
                _region_summary(lower, width, height, "region-1"),
            ],
            "semantic_classification": "NOT_PERFORMED",
        })
    components: List[List[Point]] = list(candidate.get("_components", []))
    if len(components) > 1:
        partitions.append({
            "part_candidate_id": "parts-" + _digest({
                "foreground": candidate["candidate_id"],
                "components": [len(row) for row in components],
            })[:16],
            "state": PROPOSED,
            "partition_basis": "DISCONNECTED_VISIBLE_COMPONENTS",
            "regions": [
                _region_summary(row, width, height, f"region-{index}")
                for index, row in enumerate(components)
            ],
            "semantic_classification": "NOT_PERFORMED",
        })
    return {
        "verdict": "PROPOSED_GEOMETRIC_PART_CANDIDATES",
        "state": PROPOSED,
        "candidate_count": len(partitions),
        "auto_selected_candidate_id": None,
        "human_review_required": True,
        "candidates": partitions,
    }


def _front_region_probe(
    foreground: Mapping[str, Any], parts: Mapping[str, Any],
) -> Dict[str, Any]:
    candidates = [row for row in parts.get("candidates", [])
                  if isinstance(row, Mapping)]
    selected = max(candidates, key=lambda row: len(row.get("regions", [])),
                   default=None)
    regions = _region_wire(selected) if selected is not None else []
    result = front_region_structure_cues.hypothesize(
        {
            "outline": foreground.get("outline_px", []),
            "provenance": {"kind": PROPOSED},
        },
        regions=regions,
        source_id=str(foreground.get("candidate_id", "offline-front")),
    )
    if result.get("verdict") != PROPOSED:
        return _typed_stop(
            str(result.get("verdict", "UNKNOWN_FRONT_REGION_PIPELINE")),
            str(result.get("why", "front-region pipeline did not produce candidates")),
            stage="FRONT_REGION_STRUCTURE_CUES",
            how_to_close=str(result.get(
                "how_to_close", "supply a corrected foreground and region audit")),
        )
    return {
        "verdict": PROPOSED,
        "state": PROPOSED,
        "region_count": len(result.get("regions", [])),
        "rejected_region_count": int(result.get("rejected_region_count", 0)),
        "hypothesis_count": len(result.get("hypotheses", [])),
        "typed_cues": result.get("typed_cues"),
        "cue_evidence": result.get("cue_evidence"),
        "claims": result.get("claims"),
        "front_geometry_digest": result.get("front_geometry_digest"),
        "fact_promotions": [],
    }


def _parts_ir_probe(parts: Mapping[str, Any]) -> Dict[str, Any]:
    candidates = [row for row in parts.get("candidates", [])
                  if isinstance(row, Mapping)]
    selected = max(candidates, key=lambda row: len(row.get("regions", [])),
                   default=None)
    if selected is None:
        return _typed_stop(
            "UNKNOWN_PARTS_IR_GEOMETRIC_PARTS_REQUIRED",
            "no geometric part proposal is available for the existing parts pipeline",
            stage="PARTS_IR_PIPELINE",
            how_to_close="approve or correct one visible-region partition",
        )
    regions = sorted(
        (row for row in selected.get("regions", []) if isinstance(row, Mapping)),
        key=lambda row: (float(row.get("bbox_normalized", [0, 0, 0, 0])[1]),
                         str(row.get("region_id", ""))),
    )
    proposed_parts: List[Dict[str, Any]] = []
    for index, region in enumerate(regions):
        proposed_parts.append({
            "part_id": f"visible-region-{index}",
            "kind": "BODY_SHELL" if index == 0 else "FLARE",
            "layer": index,
            "placement": "visible geometry partition",
            "visible_basis": {
                "state": PROPOSED,
                "basis": "deterministic foreground geometry partition",
                "breaks_when": "a human region audit changes this partition",
            },
            "garment_unit": "evaluation-proposal",
        })
    request = {
        "schema": "garment.parts-ir.v1",
        "state": PROPOSED,
        "candidate_count": 2,
        "parts": proposed_parts,
    }
    result = parts_ir_pipeline.run_parts_ir_pipeline(
        request,
        preview_profile=parts_ir_completion.bounded_preview_profile(),
        candidate_count=2,
    )
    candidate_rows = [row for row in result.get("candidates", [])
                      if isinstance(row, Mapping)]
    return {
        "verdict": result.get("verdict", "UNKNOWN_PARTS_IR_PIPELINE"),
        "state": result.get("state", UNKNOWN),
        "input_part_count": len(proposed_parts),
        "candidate_count": int(result.get("candidate_count", 0) or 0),
        "successful_candidate_count": int(
            result.get("successful_candidate_count", 0) or 0),
        "failed_candidate_count": int(result.get("failed_candidate_count", 0) or 0),
        "candidate_results": [{
            "candidate_id": row.get("candidate_id"),
            "verdict": row.get("verdict"),
            "execution_status": row.get("execution_status"),
            "preview_verdict": row.get("preview", {}).get("verdict")
                if isinstance(row.get("preview"), Mapping) else None,
            "pattern_verdict": row.get("flat_pattern", {}).get("verdict")
                if isinstance(row.get("flat_pattern"), Mapping) else None,
        } for row in candidate_rows],
        "failures": result.get("failures", []),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }


def _target_request(image: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, Any]:
    outline = candidate["outline_px"]
    candidate_id = str(candidate["candidate_id"])
    return {
        "schema": "garment.target-reconstruction.request.v1",
        "source": {"image_digest": image["content_digest"]},
        "camera_digest": "offline-uncalibrated-source-view",
        "base_avatar": {
            "avatar_id": "neutral-preview-avatar",
            "kind": "PARAMETRIC_GAME_AVATAR",
            "authority": "PROPOSED_PREVIEW",
            "geometry_digest": "neutral-preview-avatar-v1",
            "measurements_cm": {
                "height": 170.0,
                "chest_bust": 92.0,
                "waist": 76.0,
                "hip": 98.0,
            },
        },
        "reconstruction": {"fallback": {
            "silhouette_digest": target_digest(outline),
            "point_count": len(outline),
            "outline": outline,
            "width_px": image["width"],
            "height_px": image["height"],
            "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
            "selection_mode": "OFFLINE_BORDER_CONTRAST_PROPOSAL",
            "source": {"foreground_candidate_id": candidate_id},
        }},
        "regions": [{
            "id": candidate_id,
            "class": "UNKNOWN",
            "state": PROPOSED,
            "outline": outline,
            "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
            "selection_mode": "OFFLINE_BORDER_CONTRAST_PROPOSAL",
            "provenance": {
                "state": PROPOSED,
                "source_image_digest": image["content_digest"],
            },
        }],
        "edits": {"remove_region_ids": []},
    }


def _target_3d(image: Mapping[str, Any],
               candidate: Mapping[str, Any]) -> Dict[str, Any]:
    result = prepare_target_reconstruction(_target_request(image, candidate))
    surface = result.get("sculpt_surface")
    if result.get("verdict") != "PROPOSED_TARGET_RECONSTRUCTION" or not isinstance(surface, Mapping):
        code = str(result.get("verdict", "UNKNOWN_TARGET_3D"))
        return _typed_stop(
            code, str(result.get("why", "target reconstruction produced no surface")),
            stage="TARGET_3D",
            how_to_close="correct the foreground outline or target reconstruction input",
        )
    vertices = surface.get("vertices_cm", [])
    faces = surface.get("faces", [])
    return {
        "verdict": "PROPOSED_TARGET_3D",
        "state": PROPOSED,
        "target_digest": result.get("target_digest"),
        "surface_source": surface.get("source"),
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "component_count": surface.get("component_count"),
        "rear_state": result.get("rear_state"),
        "human_cleanup_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _preview_summary(result: Mapping[str, Any]) -> Dict[str, Any]:
    if result.get("verdict") != "ANSWER":
        return _typed_stop(
            str(result.get("verdict", "UNKNOWN_STRUCTURE_PREVIEW")),
            str(result.get("why", "candidate preview did not complete")),
            stage="CANDIDATE_3D",
            how_to_close=str(result.get(
                "how_to_close", "supply supported typed structure geometry")),
        )
    mesh = result.get("mesh", {})
    return {
        "verdict": "ANSWER",
        "state": PROPOSED,
        "preview_digest": result.get("preview_digest"),
        "structure_digest": result.get("structure_digest"),
        "vertex_count": len(mesh.get("vertices", [])) if isinstance(mesh, Mapping) else 0,
        "face_count": len(mesh.get("faces", [])) if isinstance(mesh, Mapping) else 0,
        "part_count": len(result.get("parts", [])),
        "manufacturing_ready": False,
    }


def _pattern_summary(result: Mapping[str, Any]) -> Dict[str, Any]:
    if result.get("verdict") != "ANSWER":
        return _typed_stop(
            str(result.get("verdict", "UNKNOWN_PATTERN_COMPILATION")),
            str(result.get("why", "candidate pattern did not compile")),
            stage="CANDIDATE_PATTERN",
            how_to_close=str(result.get(
                "how_to_close", "supply missing typed construction geometry")),
        )
    pieces = result.get("pieces", [])
    seams = result.get("seams", [])
    return {
        "verdict": "ANSWER",
        "state": PROPOSED,
        "pattern_digest": result.get("digest"),
        "piece_count": len(pieces),
        "seam_count": len(seams),
        "cuttable_geometric_prototype": bool(
            pieces and all(isinstance(row, Mapping) and row.get("outline")
                           for row in pieces)),
        "remaining_gate_count": len(result.get("remaining_gates", [])),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _structure_family(structure: Mapping[str, Any]) -> str:
    node_kinds = sorted(str(row.get("kind", "UNKNOWN")).upper()
                        for row in structure.get("nodes", [])
                        if isinstance(row, Mapping))
    operation_kinds = sorted(str(row.get("kind", "UNKNOWN")).upper()
                             for row in structure.get("operations", [])
                             if isinstance(row, Mapping))
    return "+".join(node_kinds) + "|" + "+".join(operation_kinds)


def _instance_graph(structure: Mapping[str, Any], candidate_id: str) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    for raw in structure.get("nodes", []):
        if not isinstance(raw, Mapping):
            continue
        dimensions = raw.get("dimensions", {})
        dimensions_cm = {
            str(key).removesuffix("_cm"): float(value)
            for key, value in dimensions.items()
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)) and float(value) > 0.0)
        } if isinstance(dimensions, Mapping) else {}
        nodes.append({
            "node_id": str(raw.get("node_id", f"node-{len(nodes)}")),
            "primitive_kind": str(raw.get("kind", "UNKNOWN")).upper(),
            "layer": int(raw.get("layer", 0) or 0),
            "state": PROPOSED,
            "dimensions_cm": dimensions_cm,
            "construction": {
                "method": "SEWN",
                "cut_geometry": "FITTED_PANEL",
                "fit": "FITTED",
                "shaping": [],
                "knit": {},
            },
        })
    relations: List[Dict[str, Any]] = []
    for raw in structure.get("operations", []):
        if not isinstance(raw, Mapping):
            continue
        source = raw.get("source")
        target = raw.get("target")
        source_id = source.get("node_id") if isinstance(source, Mapping) else source
        target_id = target.get("node_id") if isinstance(target, Mapping) else target
        kind = str(raw.get("kind", "UNKNOWN")).upper()
        relations.append({
            "relation_id": str(raw.get("operation_id", f"relation-{len(relations)}")),
            "kind": kind,
            "connection": "LAYER" if kind == "LAYER" else "UNKNOWN",
            "source": source_id,
            "target": target_id,
            "parameters": raw.get("parameters", {}),
            "state": PROPOSED,
        })
    return {
        "schema": "garment.instance-graph.v1",
        "graph_id": "evaluation-" + _digest({
            "candidate_id": candidate_id,
            "structure": structure,
        })[:16],
        "garment_name": None,
        "source": {"kind": "MODEL_PROPOSAL", "front_only": True},
        "nodes": nodes,
        "relations": relations,
        "rear": {"state": "UNKNOWN"},
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _construction_summary(structure: Mapping[str, Any], candidate_id: str) -> Dict[str, Any]:
    result = construction_regime.route_construction(
        _instance_graph(structure, candidate_id))
    regime = result.get("construction_regime", {})
    representation = result.get("manufacturing_representation", {})
    authority = result.get("authority", {})
    return {
        "verdict": result.get("verdict", "UNKNOWN_CONSTRUCTION"),
        "state": result.get("state", UNKNOWN),
        "construction_regime": regime.get("value")
            if isinstance(regime, Mapping) else None,
        "construction_authority": regime.get("state")
            if isinstance(regime, Mapping) else None,
        "target_representation": result.get("target_representation", {}).get("kind")
            if isinstance(result.get("target_representation"), Mapping) else None,
        "manufacturing_representation": representation.get("kind")
            if isinstance(representation, Mapping) else None,
        "rear_authority": authority.get("rear", {}).get("state")
            if isinstance(authority.get("rear"), Mapping) else None,
        "review_codes": sorted({str(row.get("code"))
                                for row in result.get("review_items", [])
                                if isinstance(row, Mapping) and row.get("code")}),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }


def _paths_with_true_claim(value: Any, path: str = "$") -> List[str]:
    paths: List[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in {"manufacturing_ready", "manufacturing_certified"} and child is True:
                paths.append(child_path)
            paths.extend(_paths_with_true_claim(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            paths.extend(_paths_with_true_claim(child, f"{path}[{index}]"))
    return paths


def _generic_trapezoid_fallback_paths(value: Any, path: str = "$") -> List[str]:
    evidence: List[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            token = str(child).upper() if isinstance(child, str) else ""
            if ("GENERIC_TRAPEZOID_FALLBACK" in token
                    or "GEOMETRIC_FRONT_FALLBACK" in token):
                evidence.append(child_path)
            evidence.extend(_generic_trapezoid_fallback_paths(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            evidence.extend(_generic_trapezoid_fallback_paths(
                child, f"{path}[{index}]"))
    return evidence


def _structure_artifacts(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    front = front_geometry_cues.hypothesize({
        "outline": candidate["outline_px"],
        "provenance": {
            "kind": PROPOSED,
            "source": "offline geometry-only foreground candidate",
        },
    }, source_id=str(candidate["candidate_id"]))
    hypotheses = front.get("hypotheses")
    if front.get("verdict") != PROPOSED or not isinstance(hypotheses, Sequence):
        return {
            **_typed_stop(
                str(front.get("verdict", "UNKNOWN_FRONT_STRUCTURE_HYPOTHESES")),
                str(front.get("why", "front geometry produced no structure hypotheses")),
                stage="STRUCTURE_HYPOTHESES",
                how_to_close=str(front.get(
                    "how_to_close", "correct and confirm a non-degenerate front outline")),
            ),
            "candidates": [],
        }
    artifacts: List[Dict[str, Any]] = []
    for hypothesis in hypotheses:
        if not isinstance(hypothesis, Mapping):
            continue
        structure = hypothesis.get("structure", {})
        preview = structure_preview.generate_candidate_preview(hypothesis)
        pattern = structure_to_pattern.compile(
            structure,
            candidate_state=PROPOSED,
            candidate_id=str(hypothesis.get("candidate_id", "")),
        )
        artifacts.append({
            "candidate_id": hypothesis.get("candidate_id"),
            "state": PROPOSED,
            "back_design": hypothesis.get("back_design"),
            "back_authority": PROPOSED,
            "assumption_count": len(hypothesis.get("assumptions", [])),
            "structure_family": _structure_family(structure),
            "construction_route": _construction_summary(
                structure, str(hypothesis.get("candidate_id", ""))),
            "candidate_3d": _preview_summary(preview),
            "pattern": _pattern_summary(pattern),
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        })
    if not artifacts:
        return {
            **_typed_stop(
                "UNKNOWN_STRUCTURE_HYPOTHESES_EMPTY",
                "no structure candidate survived the deterministic hypothesis boundary",
                stage="STRUCTURE_HYPOTHESES",
                how_to_close="provide human-reviewed geometric regions",
            ),
            "candidates": [],
        }
    return {
        "verdict": "PROPOSED_STRUCTURE_ARTIFACTS",
        "state": PROPOSED,
        "front_geometry_digest": front.get("front_geometry_digest"),
        "typed_cues": front.get("typed_cues"),
        "candidate_count": len(artifacts),
        "auto_selected_candidate_id": None,
        "human_review_required": True,
        "candidates": artifacts,
    }


def _public_foreground(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = {key: child for key, child in value.items() if key != "candidates"}
    result["candidates"] = [
        {key: child for key, child in row.items()
         if not str(key).startswith("_")}
        for row in value.get("candidates", [])
    ]
    return result


def _stop_codes(value: Any) -> List[str]:
    codes: List[str] = []
    if isinstance(value, Mapping):
        if value.get("typed_stop") is True and isinstance(value.get("verdict"), str):
            codes.append(value["verdict"])
        for child in value.values():
            codes.extend(_stop_codes(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            codes.extend(_stop_codes(child))
    return codes


def evaluate_image(path: Path, *, source_slot: int = 0) -> Dict[str, Any]:
    try:
        image = _read_png(path)
    except ImageReadStop as exc:
        try:
            digest = _digest(path.read_bytes())
        except OSError:
            digest = _digest({"unreadable_slot": source_slot})
        stop = _typed_stop(
            exc.code, exc.why, stage="INPUT_READABILITY",
            how_to_close="supply a readable supported PNG without changing its semantic filename",
        )
        return {
            "schema": ITEM_SCHEMA,
            "image_id": "image-" + digest[:16],
            "source_slot": source_slot,
            "input": stop,
            "terminal": {
                "state": "TYPED_STOP",
                "typed_stop_codes": [exc.code],
            },
            "evaluation_modes": {
                AUTO_PROPOSED: stop,
                HUMAN_AUDIT: stop,
            },
            "person_attribute_inference": "NOT_PERFORMED",
            "gender_inference": "NOT_PERFORMED",
            "source_filename_used_for_inference": False,
        }

    image_id = "image-" + image["content_digest"][:16]
    foreground = _foreground_candidates(image)
    candidates = foreground.get("candidates", [])
    if candidates:
        axis = _axis_orientation(candidates[-1]["_points"])
        viewpoint = _viewpoint_proxy(candidates[-1]["_points"])
    else:
        axis = _axis_orientation([])
        viewpoint = _viewpoint_proxy([])
    candidate_runs: List[Dict[str, Any]] = []
    for candidate in candidates:
        parts = _part_candidates(
            candidate, width=image["width"], height=image["height"])
        run = {
            "foreground_candidate_id": candidate["candidate_id"],
            "state": PROPOSED,
            "part_candidates": parts,
            "front_region_pipeline": _front_region_probe(candidate, parts),
            "parts_ir_pipeline": _parts_ir_probe(parts),
            "target_3d": _target_3d(image, candidate),
            "structure_artifacts": _structure_artifacts(candidate),
            "human_review_required": True,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        }
        candidate_runs.append(run)
    input_summary = {
        "verdict": "ANSWER_READABLE_IMAGE",
        "state": "OBSERVED_FILE_PROPERTIES",
        "content_digest": image["content_digest"],
        "bytes": image["bytes"],
        "width_px": image["width"],
        "height_px": image["height"],
        "bit_depth": image["bit_depth"],
        "png_colour_type": image["colour_type"],
        "frame_orientation": _frame_orientation(image["width"], image["height"]),
        "source_filename_used_for_inference": False,
    }
    result: Dict[str, Any] = {
        "schema": ITEM_SCHEMA,
        "image_id": image_id,
        "source_slot": source_slot,
        "input": input_summary,
        "orientation": axis,
        "front_or_oblique_proxy": viewpoint,
        "foreground": _public_foreground(foreground),
        "candidate_runs": candidate_runs,
        "person_attribute_inference": "NOT_PERFORMED",
        "gender_inference": "NOT_PERFORMED",
        "rear_observed": False,
        "material_observed": False,
        "source_filename_used_for_inference": False,
        "network_used": False,
        "model_download_attempted": False,
    }
    codes = sorted(set(_stop_codes(result)))
    successful_pairs = sum(
        artifact.get("candidate_3d", {}).get("verdict") == "ANSWER"
        and artifact.get("pattern", {}).get("verdict") == "ANSWER"
        for run in candidate_runs
        for artifact in run.get("structure_artifacts", {}).get("candidates", [])
        if isinstance(artifact, Mapping)
    )
    result["terminal"] = {
        "state": (
            "PROPOSED_3D_AND_PATTERN_CANDIDATES"
            if successful_pairs else "TYPED_STOP"
        ),
        "successful_3d_pattern_pair_count": successful_pairs,
        "typed_stop_codes": codes,
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["evaluation_modes"] = {
        AUTO_PROPOSED: {
            "verdict": result["terminal"]["state"],
            "state": PROPOSED,
            "foreground_candidate_count": len(candidates),
            "successful_3d_pattern_pair_count": successful_pairs,
            "typed_stop_codes": codes,
            "candidate_auto_selected": False,
            "fact_promotions": [],
        },
        HUMAN_AUDIT: {
            **_typed_stop(
                "UNKNOWN_HUMAN_AUDIT_CONFIRMATION_REQUIRED",
                "no reviewer-confirmed foreground/part mask accompanies this offline crop",
                stage="HUMAN_AUDIT_GATE",
                how_to_close="attach a reviewer-confirmed mask/region audit and rerun",
            ),
            "exploratory_proposals_retained": True,
            "exploratory_foreground_candidate_count": len(candidates),
            "fact_promotions": [],
        },
    }
    overclaims = _paths_with_true_claim(result)
    fallback_paths = _generic_trapezoid_fallback_paths(result)
    rear_states = Counter(
        str(artifact.get("back_authority", UNKNOWN))
        for run in candidate_runs
        for artifact in run.get("structure_artifacts", {}).get("candidates", [])
        if isinstance(artifact, Mapping)
    )
    result["authority_audit"] = {
        "rear_observed": False,
        "rear_authority_counts": dict(sorted(rear_states.items())),
        "manufacturing_ready_overclaim": bool(overclaims),
        "manufacturing_ready_overclaim_paths": overclaims,
        "generic_trapezoid_fallback_used": bool(fallback_paths),
        "generic_trapezoid_fallback_evidence_paths": fallback_paths,
    }
    result["semantic_digest"] = _digest({
        key: value for key, value in result.items()
        if key not in {"source_slot", "semantic_digest"}
    })
    return result


def _discover(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    paths = [path for path in directory.iterdir() if path.is_file()]
    # Content order prevents a class-like basename from affecting even the
    # evaluation sequence.  A path is used only to read bytes.
    return sorted(paths, key=lambda path: (_digest(path.read_bytes()), len(path.read_bytes())))


def _load_manifest(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("images", []) if isinstance(payload, Mapping) else []
    return {
        str(row["file"]): dict(row)
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("file"), str)
    }


def _summary(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    readable = sum(row.get("input", {}).get("verdict") == "ANSWER_READABLE_IMAGE"
                   for row in items)
    foreground_candidates = sum(
        int(row.get("foreground", {}).get("candidate_count", 0) or 0)
        for row in items
    )
    part_candidates = sum(
        int(run.get("part_candidates", {}).get("candidate_count", 0) or 0)
        for row in items for run in row.get("candidate_runs", [])
    )
    structure_candidates = sum(
        int(run.get("structure_artifacts", {}).get("candidate_count", 0) or 0)
        for row in items for run in row.get("candidate_runs", [])
    )
    target_3d = sum(
        run.get("target_3d", {}).get("verdict") == "PROPOSED_TARGET_3D"
        for row in items for run in row.get("candidate_runs", [])
    )
    preview_3d = sum(
        artifact.get("candidate_3d", {}).get("verdict") == "ANSWER"
        for row in items for run in row.get("candidate_runs", [])
        for artifact in run.get("structure_artifacts", {}).get("candidates", [])
    )
    patterns = sum(
        artifact.get("pattern", {}).get("verdict") == "ANSWER"
        for row in items for run in row.get("candidate_runs", [])
        for artifact in run.get("structure_artifacts", {}).get("candidates", [])
    )
    axis = Counter(str(row.get("orientation", {}).get(
        "axis_orientation", "UNKNOWN")) for row in items)
    stop_codes = Counter(
        code for row in items for code in row.get("terminal", {}).get(
            "typed_stop_codes", []))
    completed = sum(row.get("terminal", {}).get("state") ==
                    "PROPOSED_3D_AND_PATTERN_CANDIDATES" for row in items)
    viewpoints = Counter(str(row.get("front_or_oblique_proxy", {}).get(
        "view_bucket", "UNKNOWN_FRONT_OR_OBLIQUE")) for row in items)
    provided_groups = Counter(
        str(row.get("dataset_record", {}).get("provided_file_group"))
        for row in items if row.get("dataset_record", {}).get("provided_file_group")
    )
    structure_families = Counter(
        str(artifact.get("structure_family", "UNKNOWN"))
        for row in items for run in row.get("candidate_runs", [])
        for artifact in run.get("structure_artifacts", {}).get("candidates", [])
        if isinstance(artifact, Mapping)
    )
    construction_routes = Counter(
        str(artifact.get("construction_route", {}).get(
            "construction_regime", "UNKNOWN_CONSTRUCTION"))
        for row in items for run in row.get("candidate_runs", [])
        for artifact in run.get("structure_artifacts", {}).get("candidates", [])
        if isinstance(artifact, Mapping)
    )
    parts_pipeline = Counter(
        str(run.get("parts_ir_pipeline", {}).get("verdict", "UNKNOWN"))
        for row in items for run in row.get("candidate_runs", [])
    )
    front_region_pipeline = Counter(
        str(run.get("front_region_pipeline", {}).get("verdict", "UNKNOWN"))
        for row in items for run in row.get("candidate_runs", [])
    )
    mode_stops = Counter(
        str(mode.get("verdict"))
        for row in items
        for mode in row.get("evaluation_modes", {}).values()
        if isinstance(mode, Mapping) and mode.get("typed_stop") is True
    )
    rear_authority = Counter(
        state for row in items
        for state, count in row.get("authority_audit", {}).get(
            "rear_authority_counts", {}).items()
        for _ in range(int(count))
    )
    return {
        "input_count": len(items),
        "readable_input_count": readable,
        "typed_input_stop_count": len(items) - readable,
        "foreground_candidate_count": foreground_candidates,
        "geometric_part_candidate_count": part_candidates,
        "structure_candidate_count": structure_candidates,
        "target_3d_proposal_count": target_3d,
        "candidate_3d_success_count": preview_3d,
        "pattern_success_count": patterns,
        "items_reaching_3d_and_pattern_count": completed,
        "foreground_axis_counts": dict(sorted(axis.items())),
        "front_or_oblique_proxy_counts": dict(sorted(viewpoints.items())),
        "provided_file_group_counts": dict(sorted(provided_groups.items())),
        "provided_file_groups_are_not_appearance_inference": True,
        "structure_family_counts": dict(sorted(structure_families.items())),
        "structure_family_count": len(structure_families),
        "construction_regime_counts": dict(sorted(construction_routes.items())),
        "front_region_pipeline_verdict_counts": dict(
            sorted(front_region_pipeline.items())),
        "parts_ir_pipeline_verdict_counts": dict(sorted(parts_pipeline.items())),
        "mode_typed_stop_counts": dict(sorted(mode_stops.items())),
        "generic_trapezoid_fallback_item_count": sum(
            bool(row.get("authority_audit", {}).get(
                "generic_trapezoid_fallback_used")) for row in items),
        "manufacturing_ready_overclaim_item_count": sum(
            bool(row.get("authority_audit", {}).get(
                "manufacturing_ready_overclaim")) for row in items),
        "rear_authority_counts": dict(sorted(rear_authority.items())),
        "typed_stop_counts": dict(sorted(stop_codes.items())),
    }


def evaluate_paths(
    paths: Sequence[Path], *, manifest_path: Optional[Path] = DEFAULT_MANIFEST,
) -> Dict[str, Any]:
    paths = sorted((Path(path) for path in paths), key=lambda path: (
        _digest(path.read_bytes()), len(path.read_bytes())))
    if not paths:
        return {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_EVALUATION_INPUT_DIRECTORY",
            "state": UNKNOWN,
            "why": "input directory is missing or contains no files",
            "items": [],
            "summary": _summary([]),
            "network_used": False,
            "model_download_attempted": False,
        }
    manifest = _load_manifest(manifest_path)
    items: List[Dict[str, Any]] = []
    enumerated_inputs: List[Dict[str, Any]] = []
    for index, path in enumerate(paths):
        item = evaluate_image(path, source_slot=index)
        record = manifest.get(path.name)
        if record is not None:
            item["dataset_record"] = {
                "file": path.name,
                "provided_file_group": record.get("provided_file_group"),
                "group_authority": (
                    "DATASET_FILENAME_METADATA_NOT_APPEARANCE_INFERENCE"),
                "used_for_inference": False,
            }
        items.append(item)
        enumerated_inputs.append({
            "file": path.name,
            "image_id": item.get("image_id"),
            "content_digest": item.get("input", {}).get("content_digest"),
            "provided_file_group": record.get("provided_file_group")
                if record is not None else None,
            "used_for_inference": False,
        })
    summary = _summary(items)
    evaluation_digest = _digest({
        "item_semantic_digests": sorted(str(row.get(
            "semantic_digest", _digest(row))) for row in items),
        "policy_version": SCHEMA,
    })
    return {
        "schema": SCHEMA,
        "verdict": (
            "ANSWER" if summary["typed_input_stop_count"] == 0
            else "ANSWER_WITH_TYPED_STOPS"
        ),
        "state": "EVALUATION_COMPLETE",
        "policy": {
            "network_allowed": False,
            "model_download_allowed": False,
            "filename_used_for_inference": False,
            "named_colour_rules": False,
            "garment_class_rules": False,
            "person_attribute_inference": False,
            "gender_inference": False,
            "rear_from_front_observed": False,
            "candidate_auto_selection": False,
            "manufacturing_certification": False,
        },
        "items": items,
        "enumerated_inputs": sorted(
            enumerated_inputs,
            key=lambda row: (str(row.get("content_digest")), str(row.get("file"))),
        ),
        "summary": summary,
        "evaluation_digest": evaluation_digest,
        "network_used": False,
        "model_download_attempted": False,
    }


def evaluate_directory(
    directory: Path, *, manifest_path: Optional[Path] = DEFAULT_MANIFEST,
) -> Dict[str, Any]:
    directory = Path(directory)
    return evaluate_paths(_discover(directory), manifest_path=manifest_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", nargs="?", type=Path,
                        default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate_directory(args.input_dir)
    text = json.dumps(
        result, ensure_ascii=False, sort_keys=True,
        indent=2 if args.pretty else None, allow_nan=False,
    )
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if result.get("state") == "EVALUATION_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
