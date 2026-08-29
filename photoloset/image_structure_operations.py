# -*- coding: utf-8 -*-
"""Map visible front geometry into optional pattern operations.

A closed line inside a confirmed clothing mask is observable geometry, but its
meaning is not observable: it may be a cutout, print, fold, opening, applique,
shadow or an occluding object.  This adapter therefore changes exactly one of
the already-open structure alternatives.  It projects the line onto the front
half of a candidate wrap panel and adds a ``PROPOSED`` ``CUTOUT`` operation;
the other candidates remain untouched alternatives.

The adapter validates both ``garment.structure.v1`` and the compiled pattern
before returning the modified graph.  A failed projection is an audit record,
not a malformed candidate and never an invented inner cut.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple

from . import garment_structure, structure_to_pattern


PROPOSED = "PROPOSED"
SCHEMA = "garment.image-structure-operations.v1"
Point = Tuple[float, float]


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


def _points(value: Any) -> List[Point]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    result: List[Point] = []
    for row in value:
        if (not isinstance(row, Sequence) or isinstance(row, (str, bytes))
                or len(row) < 2 or isinstance(row[0], bool)
                or isinstance(row[1], bool)):
            return []
        try:
            point = (float(row[0]), float(row[1]))
        except (TypeError, ValueError):
            return []
        if not all(math.isfinite(coordinate) for coordinate in point):
            return []
        result.append(point)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result


def _area(points: Sequence[Point]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) * 0.5


def _boundaries(outline: Any) -> Tuple[List[Point], List[List[Point]]]:
    if not isinstance(outline, Mapping):
        return _points(outline), []
    outer = _points(outline.get("outline"))
    raw = outline.get("internal_boundaries", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return outer, []
    boundaries = []
    for row in raw:
        points = _points(row)
        if len(points) >= 3 and _area(points) > 1.0e-9:
            boundaries.append(points)
    return outer, boundaries


def _envelope(node: Mapping[str, Any]) -> Optional[Tuple[float, float, float, bool]]:
    """Return height, top width, bottom width and whether it is a wrap."""
    kind = str(node.get("kind", ""))
    dimensions = node.get("dimensions")
    if not isinstance(dimensions, Mapping):
        return None
    try:
        if kind == "BODY_SHELL":
            width = float(dimensions["circumference_cm"])
            return (float(dimensions["height_cm"]),
                    float(dimensions.get("top_circumference_cm", width)),
                    float(dimensions.get("bottom_circumference_cm", width)), True)
        if kind == "TUBE":
            width = float(dimensions["circumference_cm"])
            return float(dimensions["length_cm"]), width, width, True
        if kind in {"FRUSTUM", "FLARE"}:
            return (float(dimensions["height_cm"]),
                    float(dimensions["top_circumference_cm"]),
                    float(dimensions["bottom_circumference_cm"]), True)
        if kind == "OVERLAY":
            width = float(dimensions["width_cm"])
            return float(dimensions["height_cm"]), width, width, False
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return None


def _target(nodes: Sequence[Mapping[str, Any]], top: float, bottom: float
            ) -> Tuple[Optional[Mapping[str, Any]], Optional[Tuple[float, float]], str]:
    lower = [node for node in nodes
             if str(node.get("kind")) in {"TUBE", "FRUSTUM", "FLARE"}
             and str(node.get("node_id", "")).startswith("lower-")]
    upper = next((node for node in nodes
                  if str(node.get("node_id")) == "upper-shell"), None)
    if lower:
        if bottom <= 0.50 and upper is not None:
            return upper, (0.0, 0.50), "upper-front projection"
        if top >= 0.38 and len(lower) == 1:
            return lower[0], (0.38, 1.0), "lower-front projection"
        return None, None, "boundary crosses an ambiguous upper/lower or split-leg address"
    if upper is not None:
        return upper, (0.0, 1.0), "whole-front projection"
    overlay = next((node for node in nodes
                    if str(node.get("kind")) == "OVERLAY"), None)
    if overlay is not None:
        return overlay, (0.0, 1.0), "front overlay projection"
    return None, None, "no front-addressable panel exists"


def _project(boundary: Sequence[Point], outer_bounds: Tuple[float, float, float, float],
             node: Mapping[str, Any], section: Tuple[float, float]
             ) -> Optional[List[List[float]]]:
    envelope = _envelope(node)
    if envelope is None:
        return None
    height_cm, top_width, bottom_width, wrap = envelope
    left, top, width, height = outer_bounds
    start, end = section
    if min(width, height, height_cm, top_width, bottom_width) <= 0.0:
        return None
    mapped: List[List[float]] = []
    for x, y in boundary:
        normal_y = (y - top) / height
        local = (normal_y - start) / (end - start)
        if not 0.0 < local < 1.0:
            return None
        pattern_y = height_cm * (1.0 - local)
        width_here = bottom_width + (top_width - bottom_width) * (
            pattern_y / height_cm)
        horizontal = (x - (left + width * 0.5)) / (width * 0.5)
        if not -1.0 < horizontal < 1.0:
            return None
        # A wrap piece contains the full circumference while one photograph
        # sees only its front projection.  Place observed geometry on the
        # central front half rather than stretching it around the side/back.
        half_span = width_here * (0.25 if wrap else 0.5)
        mapped.append([round(horizontal * half_span, 6),
                       round(pattern_y, 6)])
    return mapped if _area([tuple(point) for point in mapped]) > 1.0e-6 else None


def apply_cutout_alternative(outline: Any, candidates: Sequence[Mapping[str, Any]]
                             ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Add image-derived CUTOUT operations to only the last alternative."""
    copied = [copy.deepcopy(dict(candidate)) for candidate in candidates]
    outer, boundaries = _boundaries(outline)
    audit: Dict[str, Any] = {
        "schema": SCHEMA, "state": PROPOSED,
        "semantics_observed": False, "candidate_selected": None,
        "operations": [], "skipped": [],
    }
    if len(outer) < 3 or not boundaries or not copied:
        audit["verdict"] = "UNKNOWN_NO_INTERNAL_BOUNDARY"
        return copied, audit
    xs, ys = [point[0] for point in outer], [point[1] for point in outer]
    bounds = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    if bounds[2] <= 0.0 or bounds[3] <= 0.0:
        audit["verdict"] = "UNKNOWN_FRONT_OUTLINE_DEGENERATE"
        return copied, audit

    index = len(copied) - 1
    selected = copied[index]
    wrapped = isinstance(selected.get("structure"), Mapping)
    graph = (copy.deepcopy(dict(selected["structure"])) if wrapped else
             {key: copy.deepcopy(selected.get(key))
              for key in ("schema", "nodes", "operations")})
    nodes = graph.get("nodes")
    operations = graph.get("operations")
    if not isinstance(nodes, list) or not isinstance(operations, list):
        audit["verdict"] = "UNKNOWN_STRUCTURE_MISSING"
        return copied, audit

    for boundary_index, boundary in enumerate(boundaries[:4]):
        normal_ys = [(point[1] - bounds[1]) / bounds[3] for point in boundary]
        node, section, basis = _target(nodes, min(normal_ys), max(normal_ys))
        if node is None or section is None:
            audit["skipped"].append({
                "boundary_index": boundary_index,
                "verdict": "UNKNOWN_INTERNAL_BOUNDARY_ADDRESS", "why": basis})
            continue
        mapped = _project(boundary, bounds, node, section)
        if mapped is None:
            audit["skipped"].append({
                "boundary_index": boundary_index,
                "verdict": "UNKNOWN_INTERNAL_BOUNDARY_PROJECTION",
                "why": "boundary cannot be placed strictly inside one candidate panel"})
            continue
        node_id = str(node.get("node_id"))
        port_id = f"image-cutout-anchor-{boundary_index + 1}"
        ports = node.setdefault("ports", [])
        if not isinstance(ports, list):
            audit["skipped"].append({
                "boundary_index": boundary_index,
                "verdict": "UNKNOWN_INTERNAL_BOUNDARY_PORTS"})
            continue
        ports.append({"port_id": port_id, "length_cm": 1.0,
                      "interface": "image-cutout-anchor", "role": "point"})
        boundary_digest = _digest([[round(x, 6), round(y, 6)]
                                   for x, y in boundary])
        operation_id = f"image-cutout-{boundary_digest[:12]}"
        operations.append({
            "operation_id": operation_id, "kind": "CUTOUT",
            "source": {"node_id": node_id, "port_id": port_id},
            "target": None,
            "parameters": {
                "closed_polygon": mapped,
                "contour_id": f"front-boundary-{boundary_digest[:12]}",
                "minimum_clearance_cm": 0.5,
                "state": PROPOSED,
                "source_front_boundary_digest": boundary_digest,
                "projection": "visible front geometry to candidate 2D panel",
                "semantics": "cutout alternative; not observed",
            },
            "prerequisites": [],
        })
        audit["operations"].append({
            "operation_id": operation_id, "boundary_digest": boundary_digest,
            "target_node": node_id, "basis": basis, "state": PROPOSED})

    if not audit["operations"]:
        audit["verdict"] = "UNKNOWN_NO_VALID_CUTOUT_PROJECTION"
        return copied, audit
    built = garment_structure.build(graph)
    compiled = (structure_to_pattern.compile(
        graph, candidate_state=PROPOSED,
        candidate_id=str(selected.get("candidate_id", "image-cutout-alternative")))
        if built.get("verdict") == "ANSWER" else built)
    if compiled.get("verdict") != "ANSWER":
        audit.update({"verdict": str(compiled.get("verdict", "UNKNOWN_CUTOUT")),
                      "why": compiled.get("why"), "compiler": compiled})
        return copied, audit

    if wrapped:
        selected["structure"] = graph
        selected.setdefault("assumptions", []).append(
            "closed front geometry is tested as a CUTOUT alternative only; its semantics are not observed")
        selected.setdefault("breaks_when", []).append(
            "the visible closed line is print, fold, applique, shadow, occlusion or another non-cut construction")
    else:
        selected.update({key: graph[key] for key in
                         ("schema", "nodes", "operations")})
        selected.setdefault("basis", []).append(
            "closed front geometry is tested as a CUTOUT alternative only; its semantics are not observed")
        selected.setdefault("breaks_when", []).append(
            "the visible closed line is print, fold, applique, shadow, occlusion or another non-cut construction")
    selected["image_structure_operation_state"] = PROPOSED
    selected["image_structure_operation_digest"] = _digest(audit["operations"])
    copied[index] = selected
    audit.update({
        "verdict": PROPOSED,
        "candidate_selected": selected.get("candidate_id"),
        "compiled_pattern_digest": compiled.get("digest"),
        "claim": "one falsifiable cutout alternative; no semantic observation",
    })
    audit["digest"] = _digest(audit)
    return copied, audit


__all__ = ["SCHEMA", "PROPOSED", "apply_cutout_alternative"]
