# -*- coding: utf-8 -*-
"""Second-skin to image-overlay to structural-candidate workflow.

The workflow deliberately separates generated geometry, observed outlines,
inferred multi-view dimensions, and proposed garment structure.  A successful
multi-view solve still does not confirm a seam layout or an invisible back.
Single-view and quality failures retain useful deterministic artifacts while
returning the original typed UNKNOWN verdict.

Only standard-library geometry is added here.  Existing :mod:`second_skin`,
:mod:`outline_topology`, :mod:`multi_view`, and :mod:`generation_routes`
contracts remain the authority for their respective stages.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple

from . import multi_view, outline_topology, second_skin
from .generation_routes import Stage


Point = Tuple[float, float]
ANSWER = "ANSWER"
PROPOSED = "PROPOSED"
BAD_REQUEST = "UNKNOWN_GEOMETRIC_OVERLAY_BAD_REQUEST"
NO_VIEWS = "UNKNOWN_GEOMETRIC_OVERLAY_NO_VIEWS"
TRIANGULATION_FAILED = "UNKNOWN_GEOMETRIC_OVERLAY_TRIANGULATION_FAILED"
_EPS = 1.0e-12


def capabilities() -> Dict[str, Any]:
    """Return implemented stages and explicit non-claims."""
    return {
        "verdict": ANSWER,
        "features": {
            "second_skin_scaffold": True,
            "outline_topology_repair": True,
            "deterministic_triangle_overlay": True,
            "single_view_candidates": True,
            "multi_view_candidate_support": True,
            "structure_proposals": True,
            "unknown_preservation": True,
            "automatic_back_confirmation": False,
            "automatic_seam_confirmation": False,
            "automatic_pattern_confirmation": False,
        },
        "candidate_policy": (
            "image-derived and multi-view structures remain PROPOSED until a "
            "separate explicit approval stage"
        ),
    }


def _unknown(code: str, why: str, snapshot: Any, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "terminal_verdict": code, "why": why,
            "confirmed_structure": None,
            "immutable_input_snapshot": snapshot, **extra}


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _area(points: Sequence[Point]) -> float:
    return 0.5*sum(a[0]*b[1]-b[0]*a[1]
                   for a, b in zip(points, points[1:]+points[:1]))


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _inside_triangle(point: Point, a: Point, b: Point, c: Point) -> bool:
    signs = (_cross(a, b, point), _cross(b, c, point), _cross(c, a, point))
    return all(value >= -_EPS for value in signs)


def _triangulate(points: Sequence[Point]) -> Optional[List[Tuple[Point, Point, Point]]]:
    """Deterministic ear clipping of a canonical CCW simple polygon."""
    if len(points) < 3 or _area(points) <= _EPS:
        return None
    remaining = list(range(len(points)))
    triangles: List[Tuple[Point, Point, Point]] = []
    budget = len(points)*len(points)
    while len(remaining) > 3 and budget > 0:
        budget -= 1
        ears = []
        for position, current in enumerate(remaining):
            previous = remaining[position-1]
            following = remaining[(position+1) % len(remaining)]
            triangle = points[previous], points[current], points[following]
            if _cross(*triangle) <= _EPS:
                continue
            others = (index for index in remaining
                      if index not in (previous, current, following))
            if any(_inside_triangle(points[index], *triangle) for index in others):
                continue
            # Geometry key, not scan order, determines the selected ear.
            ears.append((tuple(triangle), position, triangle))
        if not ears:
            return None
        _key, position, triangle = min(ears, key=lambda item: item[0])
        triangles.append(triangle)
        del remaining[position]
    if len(remaining) != 3:
        return None
    final = tuple(points[index] for index in remaining)
    if _cross(*final) <= _EPS:
        return None
    triangles.append(final)  # type: ignore[arg-type]
    triangles.sort()
    return triangles


def _canonical_edge(a: Point, b: Point) -> Tuple[Point, Point]:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=repr)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _repair_views(raw_views: Sequence[Any]) -> Tuple[
        Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    prepared = []
    seen = set()
    for index, raw in enumerate(raw_views):
        if not isinstance(raw, Mapping):
            return None, {"verdict": BAD_REQUEST,
                          "why": f"views[{index}] must be a mapping"}
        frame_id = raw.get("frame_id")
        if not isinstance(frame_id, str) or not frame_id or frame_id in seen:
            return None, {"verdict": BAD_REQUEST,
                          "why": "each view requires a unique non-empty frame_id"}
        seen.add(frame_id)
        if "outline" not in raw:
            return None, {"verdict": BAD_REQUEST,
                          "why": f"{frame_id} has no outline"}
        repaired = outline_topology.repair_outline(raw["outline"], kind="polygon")
        if repaired.get("verdict") != ANSWER:
            return None, {"verdict": repaired.get("verdict", BAD_REQUEST),
                          "why": repaired.get("why", "outline repair failed"),
                          "frame_id": frame_id, "outline_result": repaired}
        normalized = copy.deepcopy(dict(raw))
        normalized["outline"] = repaired["outline"]
        normalized["outline_provenance"] = repaired["provenance"]
        prepared.append(normalized)
    prepared.sort(key=lambda view: view["frame_id"])
    return prepared, None


def _overlay_for_view(view: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    points = [(_number(point[0], "outline.x"),
               _number(point[1], "outline.y")) for point in view["outline"]]
    triangles = _triangulate(points)
    if triangles is None:
        return None
    edge_uses: Dict[Tuple[Point, Point], List[int]] = {}
    primitives = []
    for index, triangle in enumerate(triangles):
        primitive_id = f"{view['frame_id']}:triangle:{index:04d}"
        area = abs(_area(list(triangle)))
        centroid = [sum(point[axis] for point in triangle)/3.0 for axis in range(2)]
        primitives.append({
            "id": primitive_id, "type": "triangle",
            "points": [list(point) for point in triangle],
            "area_units2": round(area, 12),
            "centroid": [round(value, 12) for value in centroid],
            "state": "GENERATED_FROM_OBSERVED_OUTLINE",
        })
        for a, b in zip(triangle, triangle[1:]+triangle[:1]):
            edge_uses.setdefault(_canonical_edge(a, b), []).append(index)
    adjacency = []
    boundary = []
    for edge, uses in sorted(edge_uses.items()):
        if len(uses) == 2:
            adjacency.append({"triangles": sorted(uses),
                              "shared_edge": [list(edge[0]), list(edge[1])]})
        elif len(uses) == 1:
            boundary.append([list(edge[0]), list(edge[1])])
        else:
            return None
    polygon_area = abs(_area(points))
    triangle_area = sum(primitive["area_units2"] for primitive in primitives)
    return {
        "frame_id": view["frame_id"],
        "source": view.get("source"),
        "azimuth_deg": view.get("azimuth_deg"),
        "outline": [list(point) for point in points],
        "outline_state": "OBSERVED_THEN_TOPOLOGY_REPAIRED",
        "primitives": primitives,
        "triangle_adjacency": adjacency,
        "boundary_edges": boundary,
        "coverage": {"polygon_area_units2": round(polygon_area, 12),
                     "triangle_area_units2": round(triangle_area, 12),
                     "absolute_error_units2": round(abs(polygon_area-triangle_area), 12)},
    }


def _graph(overlays: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    nodes, edges = [], []
    for overlay in overlays:
        frame_id = str(overlay["frame_id"])
        for primitive in overlay["primitives"]:
            nodes.append({"id": primitive["id"], "kind": "TRIANGLE_PATCH",
                          "frame_id": frame_id,
                          "evidence_state": "GENERATED_FROM_OBSERVED_OUTLINE",
                          "area_units2": primitive["area_units2"]})
        for adjacency in overlay["triangle_adjacency"]:
            first, second = adjacency["triangles"]
            edges.append({"kind": "SAME_VIEW_ADJACENCY",
                          "nodes": [f"{frame_id}:triangle:{first:04d}",
                                    f"{frame_id}:triangle:{second:04d}"],
                          "state": "DETERMINISTIC"})
    nodes.sort(key=lambda node: node["id"])
    edges.sort(key=lambda edge: edge["nodes"])
    return {"nodes": nodes, "edges": edges,
            "cross_view_correspondence": "UNKNOWN_NOT_ESTABLISHED"}


def _candidate(identifier: str, mode: str, graph: Mapping[str, Any],
               assumptions: Sequence[str], unresolved: Sequence[str],
               support: Mapping[str, Any]) -> Dict[str, Any]:
    body = {"mode": mode, "graph": graph, "assumptions": list(assumptions),
            "unresolved": list(unresolved), "support": support}
    return {"id": identifier+"-"+_fingerprint(body)[:12],
            "verdict": PROPOSED, "state": PROPOSED,
            "may_become_evidence": False, **copy.deepcopy(body)}


def _structure_candidates(overlays: Sequence[Mapping[str, Any]],
                          view_analysis: Mapping[str, Any]) -> List[Dict[str, Any]]:
    graph = _graph(overlays)
    observed_support = {"frame_ids": [overlay["frame_id"] for overlay in overlays],
                        "overlay_digest": _fingerprint(overlays)}
    if view_analysis.get("verdict") == ANSWER:
        ratio = view_analysis["front_back_ratio"]
        support = {**observed_support, "front_back_ratio": copy.deepcopy(ratio),
                   "support_state": "INFERRED_FROM_CALIBRATED_MULTI_VIEW"}
        candidates = [
            _candidate("elliptic-shell", "ELLIPTIC_SECTION_SHELL", graph,
                ["horizontal sections use the supported multi-view ellipse ratio"],
                ["back_surface_detail", "seams", "material", "sewing_order"], support),
            _candidate("view-patched", "VIEW_PATCH_GRAPH", graph,
                ["view patches describe projections, not direct 3D correspondence"],
                ["cross_view_correspondence", "occluded_regions", "seams",
                 "material", "sewing_order"], support),
        ]
    else:
        support = {**observed_support,
                   "support_state": str(view_analysis.get("verdict", "UNKNOWN")),
                   "upstream_unknown": copy.deepcopy(dict(view_analysis))}
        candidates = [
            _candidate("open-back", "FRONT_PATCH_WITH_UNKNOWN_BACK", graph,
                ["only supplied projections constrain visible patches"],
                ["depth", "back", "cross_view_correspondence", "seams",
                 "material", "sewing_order"], support),
            _candidate("mirror-proposal", "MIRRORED_BACK_HYPOTHESIS", graph,
                ["mirroring is a reviewable proposal and is not observed"],
                ["depth", "back_confirmation", "seams", "material",
                 "sewing_order"], support),
        ]
    return sorted(candidates, key=lambda candidate: candidate["id"])


def _second_skin_options(request: Mapping[str, Any]) -> Dict[str, Any]:
    names = ("radius_at", "y_bottom", "y_top", "ease", "stretch",
             "ease_field", "stretch_field", "segments", "height_steps",
             "leg_radius_ratio", "leg_center_ratio")
    return {name: request[name] for name in names if name in request}


def build(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run second skin -> overlay -> view candidates -> structure candidates."""
    snapshot = copy.deepcopy(request)
    if not isinstance(request, Mapping):
        return _unknown(BAD_REQUEST, "request must be a mapping", snapshot)
    mannequin = request.get("mannequin")
    garment = request.get("garment", "dress")
    raw_views = request.get("views")
    if not isinstance(raw_views, Sequence) or isinstance(raw_views, (str, bytes)):
        return _unknown(NO_VIEWS, "views must be a non-empty sequence", snapshot)
    if not raw_views:
        return _unknown(NO_VIEWS, "at least one calibrated outline is required", snapshot)

    trace = []
    base = second_skin.build(mannequin, garment, **_second_skin_options(request))
    trace.append({"stage": Stage.GEOMETRIC_CONSTRUCTION.value,
                  "step": "second_skin", "verdict": base.get("verdict")})
    if base.get("verdict") != ANSWER:
        return _unknown(str(base.get("verdict", BAD_REQUEST)),
                        "second-skin scaffold is unresolved", snapshot,
                        second_skin=base, stage_trace=trace)

    views, refusal = _repair_views(raw_views)
    trace.append({"stage": Stage.IMAGE_EVIDENCE.value,
                  "step": "outline_topology", "verdict": (ANSWER if refusal is None
                                                             else refusal["verdict"])})
    if refusal is not None or views is None:
        return _unknown(str((refusal or {}).get("verdict", BAD_REQUEST)),
                        str((refusal or {}).get("why", "outline repair failed")),
                        snapshot, second_skin=base, outline_failure=refusal,
                        stage_trace=trace)

    overlays = []
    for view in views:
        overlay = _overlay_for_view(view)
        if overlay is None:
            return _unknown(TRIANGULATION_FAILED,
                            f"{view['frame_id']} could not be triangulated", snapshot,
                            second_skin=base, overlays=overlays, stage_trace=trace)
        overlays.append(overlay)
    overlays.sort(key=lambda overlay: overlay["frame_id"])
    trace.append({"stage": Stage.GEOMETRIC_CONSTRUCTION.value,
                  "step": "triangle_overlay", "verdict": ANSWER,
                  "primitive_count": sum(len(item["primitives"]) for item in overlays)})

    analysis = multi_view.analyze(views)
    trace.append({"stage": Stage.IMAGE_EVIDENCE.value,
                  "step": "single_or_multi_view", "verdict": analysis.get("verdict")})
    constrained = None
    if analysis.get("verdict") == ANSWER:
        constrained_views = []
        by_id = {overlay["frame_id"]: overlay for overlay in overlays}
        for view in views:
            enriched = copy.deepcopy(view)
            enriched["primitives"] = copy.deepcopy(by_id[view["frame_id"]]["primitives"])
            constrained_views.append(enriched)
        constrained = second_skin.build(
            mannequin, garment, calibrated_views=constrained_views,
            **_second_skin_options(request))
        trace.append({"stage": Stage.GEOMETRIC_CONSTRUCTION.value,
                      "step": "multi_view_second_skin_constraint",
                      "verdict": constrained.get("verdict")})

    candidates = _structure_candidates(overlays, analysis)
    trace.append({"stage": Stage.GEOMETRIC_CONSTRUCTION.value,
                  "step": "structure_candidates", "verdict": PROPOSED,
                  "candidate_count": len(candidates)})

    terminal = str(analysis.get("verdict", BAD_REQUEST))
    if terminal == ANSWER and constrained is not None and constrained.get("verdict") != ANSWER:
        terminal = str(constrained.get("verdict"))
    return {
        "verdict": ANSWER if terminal == ANSWER else terminal,
        "terminal_verdict": terminal,
        "what": "second-skin to geometric-overlay candidate workflow",
        "second_skin": base,
        "overlays": overlays,
        "view_analysis": analysis,
        "constrained_second_skin": constrained,
        "structure_candidates": candidates,
        "confirmed_structure": None,
        "confirmation_required": True,
        "unknown_promoted_to_fact": False,
        "stage_trace": trace,
        "capabilities": capabilities(),
        "immutable_input_snapshot": snapshot,
    }


generate = build


__all__ = [
    "ANSWER", "PROPOSED", "BAD_REQUEST", "NO_VIEWS",
    "TRIANGULATION_FAILED", "capabilities", "build", "generate",
]
