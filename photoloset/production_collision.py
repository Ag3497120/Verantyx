# -*- coding: utf-8 -*-
"""Deterministic swept broad phase and bounded TOI refinement for cloth.

This module is a production *candidate* layer, not a claim of a completed
industrial collision system.  Swept AABBs are paired by sweep-and-prune,
topological neighbours are excluded, and each surviving linear-trajectory
candidate is checked with interval distance bounds.  ``cross_ccd`` supplies
the reference narrow phase/contact witness.

All distances are SI metres and returned TOI errors are SI seconds.  The
interval method can certify separation or enclose a sampled threshold crossing;
when it cannot do either inside the requested budget it returns typed UNKNOWN.
It is not exact symbolic CCD.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import heapq
import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import cross_ccd


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_PRODUCTION_COLLISION_INVALID_INPUT"
UNCERTAIN = "UNKNOWN_PRODUCTION_COLLISION_NUMERICAL_UNCERTAINTY"
NON_CONVERGENCE = "UNKNOWN_PRODUCTION_COLLISION_NON_CONVERGENCE"
NARROW_DISAGREEMENT = "UNKNOWN_PRODUCTION_COLLISION_NARROW_DISAGREEMENT"
_EPS = 1.0e-12


class _Invalid(ValueError):
    pass


@dataclass(frozen=True)
class _AABB:
    kind: str
    key: Tuple[int, ...]
    lower: Vec3
    upper: Vec3


def capabilities() -> Dict[str, Any]:
    """Return explicit implemented features and non-claims."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python",
        "features": {
            "swept_aabb": True,
            "sweep_and_prune": True,
            "vertex_triangle_candidates": True,
            "edge_edge_candidates": True,
            "topological_adjacency_exclusion": True,
            "candidate_order_invariant": True,
            "linear_trajectory_toi": True,
            "interval_distance_enclosure": True,
            "root_bracket_with_error_bound": True,
            "cross_ccd_narrow_phase": True,
            "exact_symbolic_toi": False,
            "curved_trajectory_ccd": False,
            "parallel_bvh": False,
            "industrial_certification": False,
        },
        "guarantee": {
            "separation": "certified only when the Lipschitz lower bound exceeds thickness",
            "hit": "bounded threshold-crossing bracket corroborated by cross_ccd",
            "unresolved": "typed UNKNOWN; never promoted to a collision or no-collision answer",
        },
        "limits": [
            "linear vertex trajectories only",
            "floating-point interval bounds, not directed-rounding interval arithmetic",
            "no exact symbolic polynomial roots",
            "quadratic worst case after sweep-and-prune",
        ],
    }


def _unknown(code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "reasons": [reason], **extra}


def _number(value: Any, name: str, *, low: Optional[float] = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise _Invalid(f"{name} must be finite")
    if low is not None and (result <= low if strict else result < low):
        raise _Invalid(f"{name} must be {'>' if strict else '>='} {low}")
    return result


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _Invalid(f"{name} must be a positive integer")
    return value


def _vec(value: Any, name: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must contain three finite SI components")
    return tuple(_number(v, f"{name}[{i}]") for i, v in enumerate(value))  # type: ignore[return-value]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0]+b[0], a[1]+b[1], a[2]+b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _mul(a: Vec3, scalar: float) -> Vec3:
    return a[0]*scalar, a[1]*scalar, a[2]*scalar


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return _add(a, _mul(_sub(b, a), t))


def _closest_triangle_distance(p: Vec3, a: Vec3, b: Vec3, c: Vec3) -> float:
    """Point-triangle distance using deterministic Voronoi region tests."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
    if _length(_cross(ab, ac)) <= _EPS:
        raise _Invalid("triangle becomes degenerate during its trajectory")
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return _length(ap)
    bp = _sub(p, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return _length(bp)
    vc = d1*d4-d3*d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1/(d1-d3)
        return _length(_sub(p, _add(a, _mul(ab, v))))
    cp = _sub(p, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return _length(cp)
    vb = d5*d2-d1*d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2/(d2-d6)
        return _length(_sub(p, _add(a, _mul(ac, w))))
    va = d3*d6-d5*d4
    if va <= 0.0 and d4-d3 >= 0.0 and d5-d6 >= 0.0:
        w = (d4-d3)/((d4-d3)+(d5-d6))
        return _length(_sub(p, _add(b, _mul(_sub(c, b), w))))
    normal = _cross(ab, ac)
    return abs(_dot(ap, normal))/_length(normal)


def _closest_segment_distance(p1: Vec3, q1: Vec3, p2: Vec3, q2: Vec3) -> float:
    d1, d2, r = _sub(q1, p1), _sub(q2, p2), _sub(p1, p2)
    a, e = _dot(d1, d1), _dot(d2, d2)
    if a <= _EPS or e <= _EPS:
        raise _Invalid("edge becomes degenerate during its trajectory")
    b, c, f = _dot(d1, d2), _dot(d1, r), _dot(d2, r)
    denominator = a*e-b*b
    s = 0.0 if abs(denominator) <= _EPS else max(0.0, min(1.0, (b*f-c*e)/denominator))
    t = (b*s+f)/e
    if t < 0.0:
        t, s = 0.0, max(0.0, min(1.0, -c/a))
    elif t > 1.0:
        t, s = 1.0, max(0.0, min(1.0, (b-c)/a))
    return _length(_sub(_lerp(p1, q1, s), _lerp(p2, q2, t)))


def _swept_aabb(kind: str, key: Tuple[int, ...], previous: Sequence[Vec3],
                proposed: Sequence[Vec3], padding: float) -> _AABB:
    points = [previous[i] for i in key] + [proposed[i] for i in key]
    lower = tuple(min(point[axis] for point in points)-padding for axis in range(3))
    upper = tuple(max(point[axis] for point in points)+padding for axis in range(3))
    return _AABB(kind, key, lower, upper)  # type: ignore[arg-type]


def _overlap(a: _AABB, b: _AABB) -> bool:
    return all(a.lower[axis] <= b.upper[axis] and
               b.lower[axis] <= a.upper[axis] for axis in range(3))


def _sweep_pairs(left: Sequence[_AABB], right: Sequence[_AABB]) -> List[Tuple[_AABB, _AABB]]:
    """Cross-set sweep-and-prune; output is canonical and order invariant."""
    combined = sorted([(box.lower[0], box.upper[0], 0, box.key, box) for box in left] +
                      [(box.lower[0], box.upper[0], 1, box.key, box) for box in right])
    active: List[List[_AABB]] = [[], []]
    pairs = set()
    for lower, _upper, side, _key, box in combined:
        for group in active:
            group[:] = [candidate for candidate in group if candidate.upper[0] >= lower]
        for other in active[1-side]:
            if _overlap(box, other):
                first, second = (box, other) if side == 0 else (other, box)
                pairs.add((first.key, second.key))
        active[side].append(box)
    left_by_key = {box.key: box for box in left}
    right_by_key = {box.key: box for box in right}
    return [(left_by_key[a], right_by_key[b]) for a, b in sorted(pairs)]


def _self_sweep_pairs(boxes: Sequence[_AABB]) -> List[Tuple[_AABB, _AABB]]:
    ordered = sorted(boxes, key=lambda box: (box.lower[0], box.upper[0], box.key))
    active: List[_AABB] = []
    pairs = set()
    for box in ordered:
        active = [candidate for candidate in active if candidate.upper[0] >= box.lower[0]]
        for other in active:
            if _overlap(box, other):
                pairs.add(tuple(sorted((other.key, box.key))))
        active.append(box)
    by_key = {box.key: box for box in boxes}
    return [(by_key[a], by_key[b]) for a, b in sorted(pairs)]


def _refine_toi(distance_at: Callable[[float], float], speed_bound: float,
                thickness: float, tolerance_normalized: float,
                max_nodes: int) -> Dict[str, Any]:
    """Certify separation or bracket a sampled threshold crossing.

    For interval ``[a,b]``, distance is bounded below by
    ``d(mid)-L*(b-a)/2``.  An interval is discarded only if that lower bound is
    strictly above thickness.  Ambiguous leaf intervals become UNKNOWN.
    """
    d0 = distance_at(0.0)
    if d0 <= _EPS:
        return {"verdict": cross_ccd.INITIAL_INTERSECTION,
                "reasons": ["primitives intersect at t=0"]}
    if d0 <= thickness:
        return {"verdict": ANSWER, "hit": True, "bracket": [0.0, 0.0],
                "error_normalized": 0.0, "evaluations": 1}
    evaluations = 1
    queue: List[Tuple[float, float]] = [(0.0, 1.0)]
    unresolved = []
    nodes = 0
    while queue:
        lo, hi = heapq.heappop(queue)
        nodes += 1
        if nodes > max_nodes:
            return _unknown(NON_CONVERGENCE,
                "interval refinement exceeded max_refinement_nodes",
                unresolved_interval=[lo, hi], evaluations=evaluations,
                error_normalized=hi-lo)
        mid = 0.5*(lo+hi)
        dlo, dmid, dhi = distance_at(lo), distance_at(mid), distance_at(hi)
        evaluations += 3
        radius = 0.5*(hi-lo)
        lower_bound = max(0.0, dmid-speed_bound*radius)
        if lower_bound > thickness:
            continue
        inside = [(t, d) for t, d in ((lo, dlo), (mid, dmid), (hi, dhi))
                  if d <= thickness]
        if inside:
            inside_t = min(inside)[0]
            outside_t = lo
            if dlo <= thickness:
                # The parent subdivision supplies at most this leaf's width as
                # the left uncertainty; do not invent an earlier exact root.
                bracket_lo = max(0.0, lo-(hi-lo))
                return {"verdict": ANSWER, "hit": True,
                        "bracket": [bracket_lo, lo],
                        "error_normalized": lo-bracket_lo,
                        "evaluations": evaluations}
            for _ in range(80):
                if inside_t-outside_t <= tolerance_normalized:
                    break
                probe = 0.5*(outside_t+inside_t)
                evaluations += 1
                if distance_at(probe) <= thickness:
                    inside_t = probe
                else:
                    outside_t = probe
            return {"verdict": ANSWER, "hit": True,
                    "bracket": [outside_t, inside_t],
                    "error_normalized": inside_t-outside_t,
                    "evaluations": evaluations}
        if hi-lo <= tolerance_normalized:
            unresolved.append({"interval": [lo, hi],
                               "distance_lower_bound_m": lower_bound,
                               "sample_minimum_m": min(dlo, dmid, dhi)})
            continue
        heapq.heappush(queue, (lo, mid))
        heapq.heappush(queue, (mid, hi))
    if unresolved:
        first = min(unresolved, key=lambda item: item["interval"])
        return _unknown(UNCERTAIN,
            "distance enclosure overlaps thickness without a sampled crossing",
            unresolved=unresolved, error_normalized=(first["interval"][1]-first["interval"][0]),
            evaluations=evaluations)
    return {"verdict": ANSWER, "hit": False, "bracket": None,
            "error_normalized": tolerance_normalized,
            "evaluations": evaluations,
            "separation_certificate": "all interval Lipschitz lower bounds exceed thickness"}


def _parse_request(request: Mapping[str, Any]) -> Tuple[
        Tuple[Vec3, ...], Tuple[Vec3, ...], Tuple[Tuple[int, int, int], ...],
        Tuple[Tuple[int, int], ...], float, float, int, float, bool]:
    if not isinstance(request, Mapping):
        raise _Invalid("request must be a mapping")
    previous_raw = request.get("previous_positions")
    proposed_raw = request.get("proposed_positions")
    if not isinstance(previous_raw, (list, tuple)) or not isinstance(proposed_raw, (list, tuple)):
        raise _Invalid("position arrays are required")
    previous = tuple(_vec(v, f"previous_positions[{i}]") for i, v in enumerate(previous_raw))
    proposed = tuple(_vec(v, f"proposed_positions[{i}]") for i, v in enumerate(proposed_raw))
    if not previous or len(previous) != len(proposed):
        raise _Invalid("position arrays must have equal non-zero length")
    faces_raw = request.get("faces")
    if not isinstance(faces_raw, (list, tuple)):
        raise _Invalid("faces must be a sequence")
    faces = set()
    for fi, raw in enumerate(faces_raw):
        if (not isinstance(raw, (list, tuple)) or len(raw) != 3 or
                any(isinstance(i, bool) or not isinstance(i, int) or
                    not 0 <= i < len(previous) for i in raw) or len(set(raw)) != 3):
            raise _Invalid(f"faces[{fi}] must contain three distinct valid indices")
        face = tuple(sorted(int(i) for i in raw))
        for positions in (previous, proposed):
            if _length(_cross(_sub(positions[face[1]], positions[face[0]]),
                              _sub(positions[face[2]], positions[face[0]]))) <= _EPS:
                raise _Invalid(f"faces[{fi}] is degenerate")
        if face in faces:
            raise _Invalid("duplicate faces are not allowed")
        faces.add(face)
    edges = set()
    edges_raw = request.get("edges")
    if edges_raw is None:
        for face in faces:
            edges.update(tuple(sorted(pair)) for pair in
                         ((face[0], face[1]), (face[1], face[2]), (face[0], face[2])))
    else:
        if not isinstance(edges_raw, (list, tuple)):
            raise _Invalid("edges must be a sequence")
        for ei, raw in enumerate(edges_raw):
            if (not isinstance(raw, (list, tuple)) or len(raw) != 2 or
                    any(isinstance(i, bool) or not isinstance(i, int) or
                        not 0 <= i < len(previous) for i in raw) or raw[0] == raw[1]):
                raise _Invalid(f"edges[{ei}] must contain two distinct valid indices")
            edge = tuple(sorted((int(raw[0]), int(raw[1]))))
            for positions in (previous, proposed):
                if _length(_sub(positions[edge[1]], positions[edge[0]])) <= _EPS:
                    raise _Invalid(f"edges[{ei}] is degenerate")
            if edge in edges:
                raise _Invalid("duplicate edges are not allowed")
            edges.add(edge)
    thickness = _number(request.get("thickness_m"), "thickness_m", low=0.0, strict=True)
    dt = _number(request.get("time_step_s"), "time_step_s", low=0.0, strict=True)
    tolerance_s = _number(request.get("toi_tolerance_s", 1.0e-7),
                          "toi_tolerance_s", low=0.0, strict=True)
    if tolerance_s > dt:
        raise _Invalid("toi_tolerance_s must be <= time_step_s")
    max_nodes = _positive_int(request.get("max_refinement_nodes", 65536),
                              "max_refinement_nodes")
    one_ring = request.get("exclude_one_ring", False)
    if not isinstance(one_ring, bool):
        raise _Invalid("exclude_one_ring must be boolean")
    return (previous, proposed, tuple(sorted(faces)), tuple(sorted(edges)),
            thickness, dt, max_nodes, tolerance_s/dt, one_ring)


def solve(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Enumerate and certify collision candidates for one linear time step."""
    snapshot = copy.deepcopy(request)
    try:
        (previous, proposed, faces, edges, thickness, dt, max_nodes,
         tolerance, exclude_one_ring) = _parse_request(request)
        half_padding = 0.5*thickness
        vertices = [_swept_aabb("VERTEX", (i,), previous, proposed, half_padding)
                    for i in range(len(previous))]
        triangles = [_swept_aabb("TRIANGLE", face, previous, proposed, half_padding)
                     for face in faces]
        edge_boxes = [_swept_aabb("EDGE", edge, previous, proposed, half_padding)
                      for edge in edges]

        neighbours = {i: set() for i in range(len(previous))}
        edge_to_faces = {edge: set() for edge in edges}
        for face in faces:
            face_edges = (tuple(sorted((face[0], face[1]))),
                          tuple(sorted((face[1], face[2]))),
                          tuple(sorted((face[0], face[2]))))
            for a, b in face_edges:
                neighbours[a].add(b)
                neighbours[b].add(a)
                if (a, b) in edge_to_faces:
                    edge_to_faces[(a, b)].add(face)

        vf_candidates = []
        vf_excluded = 0
        for vertex_box, face_box in _sweep_pairs(vertices, triangles):
            vertex, face = vertex_box.key[0], face_box.key
            adjacent = vertex in face or (exclude_one_ring and any(
                member in neighbours[vertex] for member in face))
            if adjacent:
                vf_excluded += 1
            else:
                vf_candidates.append((vertex, face))

        ee_candidates = []
        ee_excluded = 0
        for first_box, second_box in _self_sweep_pairs(edge_boxes):
            first, second = first_box.key, second_box.key
            shared_vertex = bool(set(first) & set(second))
            shared_face = bool(edge_to_faces.get(first, set()) &
                               edge_to_faces.get(second, set()))
            if shared_vertex or shared_face:
                ee_excluded += 1
            else:
                ee_candidates.append((first, second))
        vf_candidates.sort()
        ee_candidates.sort()

        events = []
        certified_misses = 0
        total_evaluations = 0
        for vertex, face in vf_candidates:
            velocity_vertex = _sub(proposed[vertex], previous[vertex])
            face_velocities = [_sub(proposed[i], previous[i]) for i in face]
            speed_bound = _length(velocity_vertex)+max(_length(v) for v in face_velocities)

            def vf_distance(t: float, vertex: int = vertex,
                            face: Tuple[int, ...] = face) -> float:
                point = _lerp(previous[vertex], proposed[vertex], t)
                triangle = tuple(_lerp(previous[i], proposed[i], t) for i in face)
                return _closest_triangle_distance(point, *triangle)

            bounded = _refine_toi(vf_distance, speed_bound, thickness,
                                  tolerance, max_nodes)
            total_evaluations += bounded.get("evaluations", 0)
            narrow = cross_ccd.vertex_triangle_toi(
                previous[vertex], proposed[vertex], [previous[i] for i in face],
                [proposed[i] for i in face], thickness_m=thickness)
            if bounded["verdict"] != ANSWER:
                return dict(bounded, candidate={"kind": "VERTEX_TRIANGLE",
                    "vertex": vertex, "face": list(face)},
                    cross_ccd=narrow, immutable_input_snapshot=snapshot,
                    backend=capabilities())
            if narrow["verdict"] != cross_ccd.ANSWER or bool(narrow.get("hit")) != bounded["hit"]:
                return _unknown(NARROW_DISAGREEMENT,
                    "bounded refinement and cross_ccd narrow phase disagree",
                    candidate={"kind": "VERTEX_TRIANGLE", "vertex": vertex,
                               "face": list(face)}, bounded=bounded,
                    cross_ccd=narrow, immutable_input_snapshot=snapshot,
                    backend=capabilities())
            if bounded["hit"]:
                bracket = bounded["bracket"]
                events.append({"kind": "VERTEX_TRIANGLE", "vertex": vertex,
                    "face": list(face), "toi_normalized_bracket": bracket,
                    "toi_seconds_bracket": [value*dt for value in bracket],
                    "error_bound_s": bounded["error_normalized"]*dt,
                    "witness": narrow.get("contact")})
            else:
                certified_misses += 1

        for first, second in ee_candidates:
            first_velocities = [_sub(proposed[i], previous[i]) for i in first]
            second_velocities = [_sub(proposed[i], previous[i]) for i in second]
            speed_bound = max(_length(v) for v in first_velocities)+max(
                _length(v) for v in second_velocities)

            def ee_distance(t: float, first: Tuple[int, ...] = first,
                            second: Tuple[int, ...] = second) -> float:
                edge_a = tuple(_lerp(previous[i], proposed[i], t) for i in first)
                edge_b = tuple(_lerp(previous[i], proposed[i], t) for i in second)
                return _closest_segment_distance(*edge_a, *edge_b)

            bounded = _refine_toi(ee_distance, speed_bound, thickness,
                                  tolerance, max_nodes)
            total_evaluations += bounded.get("evaluations", 0)
            narrow = cross_ccd.edge_edge_toi(
                [previous[i] for i in first], [proposed[i] for i in first],
                [previous[i] for i in second], [proposed[i] for i in second],
                thickness_m=thickness)
            if bounded["verdict"] != ANSWER:
                return dict(bounded, candidate={"kind": "EDGE_EDGE",
                    "edge_a": list(first), "edge_b": list(second)},
                    cross_ccd=narrow, immutable_input_snapshot=snapshot,
                    backend=capabilities())
            if narrow["verdict"] != cross_ccd.ANSWER or bool(narrow.get("hit")) != bounded["hit"]:
                return _unknown(NARROW_DISAGREEMENT,
                    "bounded refinement and cross_ccd narrow phase disagree",
                    candidate={"kind": "EDGE_EDGE", "edge_a": list(first),
                               "edge_b": list(second)}, bounded=bounded,
                    cross_ccd=narrow, immutable_input_snapshot=snapshot,
                    backend=capabilities())
            if bounded["hit"]:
                bracket = bounded["bracket"]
                events.append({"kind": "EDGE_EDGE", "edge_a": list(first),
                    "edge_b": list(second), "toi_normalized_bracket": bracket,
                    "toi_seconds_bracket": [value*dt for value in bracket],
                    "error_bound_s": bounded["error_normalized"]*dt,
                    "witness": narrow.get("contact")})
            else:
                certified_misses += 1

        events.sort(key=lambda event: (event["toi_normalized_bracket"][1],
                    event["kind"], tuple(event.get("face", ())),
                    tuple(event.get("edge_a", ())), event.get("vertex", -1)))
        return {
            "verdict": ANSWER,
            "events": events,
            "broad_phase": {
                "algorithm": "swept AABB sweep-and-prune",
                "vertex_triangle_candidates": len(vf_candidates),
                "edge_edge_candidates": len(ee_candidates),
                "vertex_triangle_adjacency_excluded": vf_excluded,
                "edge_edge_adjacency_excluded": ee_excluded,
                "certified_misses": certified_misses,
            },
            "refinement": {"method": "Lipschitz interval enclosure plus root bracket",
                           "toi_tolerance_s": tolerance*dt,
                           "distance_evaluations": total_evaluations,
                           "exact_symbolic": False},
            "candidate_order": "canonical topology keys; independent of face/edge input order",
            "backend": capabilities(),
            "immutable_input_snapshot": snapshot,
        }
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error),
                        immutable_input_snapshot=snapshot, backend=capabilities())
