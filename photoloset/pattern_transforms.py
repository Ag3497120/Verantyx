# -*- coding: utf-8 -*-
"""Deterministic, address-preserving pattern transforms.

Pleats, gathers, darts and folds are recorded as typed construction geometry.
The polygon outline is never silently renumbered.  Every transform validates
its declared measurements and returns a before/after digest.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from . import darts
from .outline_topology import repair_polygon

Point = Tuple[float, float]
SCHEMA = "garment.pattern-transform.v1"
ANSWER = "ANSWER"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _finite_positive(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and float(value) > 0.0)


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why,
            "how_to_close": "provide explicit dimensions that pass polygon geometry checks",
            **detail}


def _piece(value: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    identity = value.get("piece_id", value.get("name", "")) if isinstance(value, Mapping) else ""
    if not isinstance(value, Mapping) or not isinstance(identity, str) or not identity.strip():
        return None, _unknown("UNKNOWN_PATTERN_PIECE", "piece_id or name is required")
    raw = value.get("outline")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None, _unknown("UNKNOWN_PATTERN_OUTLINE", "outline must be a point sequence")
    try:
        points = [(float(p[0]), float(p[1])) for p in raw
                  if isinstance(p, Sequence) and not isinstance(p, (str, bytes)) and len(p) == 2]
    except (TypeError, ValueError, OverflowError):
        return None, _unknown("UNKNOWN_PATTERN_OUTLINE", "outline coordinates must be finite numbers")
    if len(points) != len(raw) or any(not math.isfinite(x) or not math.isfinite(y) for x, y in points):
        return None, _unknown("UNKNOWN_PATTERN_OUTLINE", "outline coordinates must be finite numbers")
    repaired = repair_polygon(points)
    if repaired.get("verdict") != ANSWER:
        return None, _unknown(repaired.get("verdict", "UNKNOWN_PATTERN_OUTLINE"),
                              repaired.get("why", "invalid polygon"), topology=repaired)
    # Repairing would invalidate eN addresses. Refuse instead of changing it.
    # Candidate-specific expansion can deliberately retain several collinear
    # boundary segments because each segment has a distinct sewing semantic
    # (for example a resampled armhole).  Those segments are safe to keep when
    # every original eN address is covered by an explicit semantic group; the
    # transform still operates on the unmodified outline and never applies the
    # repairer's simplification.
    provenance = repaired.get("provenance", {})
    groups = value.get("boundary_edge_groups", {})
    semantic_addresses = set()
    if isinstance(groups, Mapping):
        for raw_addresses in groups.values():
            if (isinstance(raw_addresses, Sequence)
                    and not isinstance(raw_addresses, (str, bytes))):
                semantic_addresses.update(str(address)
                                          for address in raw_addresses)
    all_addresses = {f"e{index}" for index in range(len(points))}
    semantic_collinear_outline = (
        bool(provenance.get("collinear_points_removed", 0))
        and semantic_addresses == all_addresses)
    if (provenance.get("consecutive_duplicates_removed", 0)
            or (provenance.get("collinear_points_removed", 0)
                and not semantic_collinear_outline)):
        return None, _unknown("UNKNOWN_PATTERN_ADDRESS_UNSTABLE",
                              "repair would remove vertices and renumber edges")
    out = copy.deepcopy(dict(value))
    out["outline"] = [[x, y] for x, y in points]
    out.setdefault("transforms", [])
    if not isinstance(out["transforms"], list):
        return None, _unknown("UNKNOWN_PATTERN_TRANSFORM_HISTORY", "transforms must be a list")
    return out, None


def _edge(piece: Mapping[str, Any], edge: Any) -> Tuple[Optional[Tuple[int, Point, Point, float]], Optional[Dict[str, Any]]]:
    if isinstance(edge, str) and edge.startswith("e") and edge[1:].isdigit():
        index = int(edge[1:])
    elif isinstance(edge, int) and not isinstance(edge, bool):
        index = edge
    else:
        return None, _unknown("UNKNOWN_PATTERN_EDGE", "edge must be eN or an integer index")
    points = piece["outline"]
    if index < 0 or index >= len(points):
        return None, _unknown("UNKNOWN_PATTERN_EDGE", f"edge e{index} does not exist",
                              known=[f"e{i}" for i in range(len(points))])
    a, b = tuple(points[index]), tuple(points[(index + 1) % len(points)])
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length <= 0.0:
        return None, _unknown("UNKNOWN_ZERO_LENGTH_EDGE", f"edge e{index} has zero length")
    return (index, a, b, length), None


def _at(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _answer(before: Mapping[str, Any], after: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
    before_digest = _digest(before)
    after["transforms"].append(record)
    return {"verdict": ANSWER, "schema": SCHEMA, "before_digest": before_digest,
            "after_digest": _digest(after), "changed_addresses": [record["address"]],
            "transform": copy.deepcopy(record), "after": after,
            "validation": {"geometry": ANSWER, "address_preserved": True},
            "provenance": {"method": "deterministic pattern geometry", "corpus_used": False}}


def apply_pleat(piece: Mapping[str, Any], edge: Any, *, count: int,
                depth_cm: float, finished_length_cm: Optional[float] = None,
                style: str = "knife") -> Dict[str, Any]:
    current, error = _piece(piece)
    if error:
        return error
    measured, error = _edge(current, edge)
    if error:
        return error
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0 or not _finite_positive(depth_cm):
        return _unknown("UNKNOWN_PLEAT_PARAMETERS", "count and depth_cm must be positive")
    index, a, b, cut_length = measured
    consumed = 2.0 * float(depth_cm) * count
    computed_finished = cut_length - consumed
    if computed_finished <= 0.0:
        return _unknown("UNKNOWN_PLEAT_EXCEEDS_EDGE", "pleat take-up consumes the complete edge",
                        cut_length_cm=cut_length, consumed_cm=consumed)
    if finished_length_cm is not None:
        if not _finite_positive(finished_length_cm) or abs(float(finished_length_cm) - computed_finished) > 1e-6:
            return _unknown("UNKNOWN_PLEAT_LENGTH_MISMATCH", "declared finished length disagrees with edge geometry",
                            computed_finished_cm=computed_finished)
    if style not in ("knife", "box", "inverted_box"):
        return _unknown("UNKNOWN_PLEAT_STYLE", "unsupported deterministic pleat style")
    marks = []
    allocation = cut_length / count
    if consumed / count >= allocation:
        return _unknown("UNKNOWN_PLEAT_OVERLAP", "adjacent pleat allocations overlap")
    for number in range(count):
        center = (number + 0.5) / count
        dt = float(depth_cm) / cut_length
        marks.append({"number": number + 1, "valley_t": center - dt,
                      "mountain_t": center, "return_t": center + dt,
                      "points": [list(_at(a, b, center - dt)), list(_at(a, b, center)),
                                 list(_at(a, b, center + dt))]})
    record = {"kind": "PLEAT", "address": f"e{index}", "style": style,
              "count": count, "depth_cm": float(depth_cm), "cut_length_cm": cut_length,
              "finished_length_cm": computed_finished, "take_up_cm": consumed, "marks": marks}
    return _answer(piece, current, record)


def apply_gather(piece: Mapping[str, Any], edge: Any, *, finished_length_cm: float,
                 ratio: Optional[float] = None) -> Dict[str, Any]:
    current, error = _piece(piece)
    if error:
        return error
    measured, error = _edge(current, edge)
    if error:
        return error
    if not _finite_positive(finished_length_cm):
        return _unknown("UNKNOWN_GATHER_LENGTH", "finished_length_cm must be positive")
    index, _a, _b, cut_length = measured
    if float(finished_length_cm) >= cut_length:
        return _unknown("UNKNOWN_GATHER_DOES_NOT_REDUCE", "gathered edge must finish shorter than its cut edge")
    measured_ratio = cut_length / float(finished_length_cm)
    if ratio is not None and (not _finite_positive(ratio) or abs(float(ratio) - measured_ratio) > 1e-9):
        return _unknown("UNKNOWN_GATHER_RATIO_MISMATCH", "declared ratio disagrees with measured lengths",
                        measured_ratio=measured_ratio)
    record = {"kind": "GATHER", "address": f"e{index}", "cut_length_cm": cut_length,
              "finished_length_cm": float(finished_length_cm), "ratio": measured_ratio,
              "distribution": "uniform", "end_anchors_t": [0.0, 1.0]}
    return _answer(piece, current, record)


def apply_dart(piece: Mapping[str, Any], edge: Any, *, t: float,
               intake_cm: float, depth_cm: float = 0.0,
               toward: Optional[Sequence[float]] = None, role: str = "dart") -> Dict[str, Any]:
    current, error = _piece(piece)
    if error:
        return error
    measured, error = _edge(current, edge)
    if error:
        return error
    index, _a, _b, _length = measured
    if (isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(float(t))
            or not 0.0 < float(t) < 1.0 or not _finite_positive(intake_cm)):
        return _unknown("UNKNOWN_DART_PARAMETERS", "t must be inside the edge and intake_cm positive")
    if toward is None and not _finite_positive(depth_cm):
        return _unknown("UNKNOWN_DART_DEPTH", "depth_cm is required without an explicit apex")
    if toward is not None:
        if (not isinstance(toward, Sequence) or len(toward) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in toward)):
            return _unknown("UNKNOWN_DART_APEX", "toward must be a finite 2D point")
        apex = (float(toward[0]), float(toward[1]))
    else:
        apex = None
    declaration = darts.dart(str(current.get("piece_id", current.get("name"))), f"e{index}",
                             float(t), float(intake_cm), float(depth_cm), role=role, toward=apex)
    opened = darts.open_one(current["outline"], declaration)
    if opened.get("verdict") != ANSWER:
        return {**opened, "how_to_close": opened.get("how_to_close", "change explicit dart geometry")}
    record = {"kind": "DART", "address": f"e{index}", "t": float(t),
              "intake_cm": float(intake_cm), "depth_cm": float(depth_cm),
              "role": role, "geometry": copy.deepcopy(opened)}
    return _answer(piece, current, record)


def _point_on_or_inside(poly: Sequence[Sequence[float]], point: Point) -> bool:
    # Boundary is allowed for fold endpoints.
    inside = False
    for index, a in enumerate(poly):
        b = poly[(index + 1) % len(poly)]
        ax, ay, bx, by = float(a[0]), float(a[1]), float(b[0]), float(b[1])
        cross = (point[0] - ax) * (by - ay) - (point[1] - ay) * (bx - ax)
        if abs(cross) <= 1e-9 and min(ax, bx) - 1e-9 <= point[0] <= max(ax, bx) + 1e-9 and min(ay, by) - 1e-9 <= point[1] <= max(ay, by) + 1e-9:
            return True
        if (ay > point[1]) != (by > point[1]):
            x = ax + (point[1] - ay) * (bx - ax) / (by - ay)
            if x > point[0]:
                inside = not inside
    return inside


def apply_fold(piece: Mapping[str, Any], start: Sequence[float], end: Sequence[float], *,
               direction: str) -> Dict[str, Any]:
    current, error = _piece(piece)
    if error:
        return error
    try:
        a, b = (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))
    except (TypeError, ValueError, IndexError):
        return _unknown("UNKNOWN_FOLD_LINE", "fold endpoints must be finite 2D points")
    if (not all(math.isfinite(v) for v in a + b) or a == b
            or direction not in ("mountain", "valley", "either")):
        return _unknown("UNKNOWN_FOLD_LINE", "fold line and direction are invalid")
    if not _point_on_or_inside(current["outline"], a) or not _point_on_or_inside(current["outline"], b):
        return _unknown("UNKNOWN_FOLD_OUTSIDE_PANEL", "the complete fold line must begin and end on or inside the panel")
    record = {"kind": "FOLD", "address": "interior", "start": list(a), "end": list(b),
              "direction": direction, "length_cm": math.hypot(b[0] - a[0], b[1] - a[1])}
    return _answer(piece, current, record)


pleat = apply_pleat
gather = apply_gather
dart = apply_dart
fold = apply_fold


def apply(pattern: Mapping[str, Any], operation: Mapping[str, Any]) -> Dict[str, Any]:
    """JSON dispatcher for one typed deterministic pattern operation."""
    if not isinstance(operation, Mapping):
        return _unknown("UNKNOWN_PATTERN_OPERATION", "operation must be an object")
    kind = str(operation.get("kind", operation.get("type", ""))).upper()
    edge = operation.get("edge")
    try:
        if kind == "PLEAT":
            return apply_pleat(pattern, edge, count=operation.get("count"),
                               depth_cm=operation.get("depth_cm"),
                               finished_length_cm=operation.get("finished_length_cm"),
                               style=operation.get("style", "knife"))
        if kind == "GATHER":
            return apply_gather(pattern, edge,
                                finished_length_cm=operation.get("finished_length_cm"),
                                ratio=operation.get("ratio"))
        if kind == "DART":
            return apply_dart(pattern, edge, t=operation.get("t"),
                              intake_cm=operation.get("intake_cm"),
                              depth_cm=operation.get("depth_cm", 0.0),
                              toward=operation.get("toward"),
                              role=operation.get("role", "dart"))
        if kind == "FOLD":
            return apply_fold(pattern, operation.get("start"), operation.get("end"),
                              direction=operation.get("direction"))
    except (TypeError, ValueError, OverflowError) as exc:
        return _unknown("UNKNOWN_PATTERN_OPERATION", str(exc))
    return _unknown("UNKNOWN_PATTERN_OPERATION", f"unsupported operation {kind!r}")
