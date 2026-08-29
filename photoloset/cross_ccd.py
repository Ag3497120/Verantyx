# -*- coding: utf-8 -*-
"""Continuous contact and seam response for the cross-cloth CPU reference.

All geometry is expressed in SI units.  Collision candidates read one
immutable predicted state and their corrections are accumulated once, i.e.
same-old-state Jacobi projection.  The routines are deliberately conservative
about invalid geometry: degenerate primitives and initial self-intersections
produce typed UNKNOWN results instead of guessed contact normals.

This is a deterministic narrow-phase/reference implementation.  It does not
claim a production broad phase, exact symbolic CCD, shell FEM, yarn contact,
or experimentally calibrated seam failure.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_CCD_INVALID_INPUT"
INITIAL_INTERSECTION = "UNKNOWN_CCD_INITIAL_SELF_INTERSECTION"
NO_CONVERGENCE = "UNKNOWN_CCD_NO_CONVERGENCE"
_EPS = 1.0e-12
_TIME_EPS = 1.0e-9


class _Invalid(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Return an honest capability declaration for orchestration/UI use."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python",
        "features": {
            "linear_trajectory_ccd": True,
            "vertex_triangle_toi": True,
            "edge_edge_toi": True,
            "finite_thickness": True,
            "coulomb_friction_projection": True,
            "same_old_state_jacobi": True,
            "seam_slip": True,
            "pre_break_damage_index": True,
            "puckering_index": True,
            "broad_phase": False,
            "exact_symbolic_toi": False,
            "shell_fem": False,
            "yarn_needle_contact": False,
            "experimentally_calibrated_failure": False,
        },
        "limits": [
            "deterministic CPU narrow phase; candidate enumeration is quadratic",
            "TOI uses conservative advancement plus bisection, not symbolic roots",
            "seam damage and puckering are engineering indicators, not certification",
        ],
    }


def _unknown(code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "reasons": [reason], **extra}


def _number(value: Any, name: str, *, low: Optional[float] = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a finite number in SI units")
    result = float(value)
    if not math.isfinite(result):
        raise _Invalid(f"{name} must be finite")
    if low is not None and (result <= low if strict else result < low):
        raise _Invalid(f"{name} must be {'>' if strict else '>='} {low}")
    return result


def _vec(value: Any, name: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must contain three finite SI components")
    return tuple(_number(v, f"{name}[{i}]") for i, v in enumerate(value))  # type: ignore[return-value]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(a: Vec3, s: float) -> Vec3:
    return a[0] * s, a[1] * s, a[2] * s


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec3) -> Vec3:
    length = _length(a)
    if length <= _EPS:
        raise _Invalid("contact direction is undefined for coincident geometry")
    return _mul(a, 1.0 / length)


def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return _add(a, _mul(_sub(b, a), t))


def _closest_triangle(p: Vec3, a: Vec3, b: Vec3, c: Vec3) -> Tuple[Vec3, Tuple[float, float, float]]:
    """Closest point and barycentrics; Ericson's region tests."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
    if _length(_cross(ab, ac)) <= _EPS:
        raise _Invalid("triangle is degenerate during its linear trajectory")
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, (1.0, 0.0, 0.0)
    bp = _sub(p, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1*d4 - d3*d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return _add(a, _mul(ab, v)), (1.0-v, v, 0.0)
    cp = _sub(p, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5*d2 - d1*d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return _add(a, _mul(ac, w)), (1.0-w, 0.0, w)
    va = d3*d6 - d5*d4
    if va <= 0.0 and d4-d3 >= 0.0 and d5-d6 >= 0.0:
        w = (d4-d3) / ((d4-d3) + (d5-d6))
        return _add(b, _mul(_sub(c, b), w)), (0.0, 1.0-w, w)
    denom = va + vb + vc
    if abs(denom) <= _EPS:
        raise _Invalid("triangle closest-point solve is singular")
    v, w = vb/denom, vc/denom
    return _add(a, _add(_mul(ab, v), _mul(ac, w))), (1.0-v-w, v, w)


def _closest_segments(p1: Vec3, q1: Vec3, p2: Vec3, q2: Vec3) -> Tuple[Vec3, Vec3, float, float]:
    d1, d2, r = _sub(q1, p1), _sub(q2, p2), _sub(p1, p2)
    a, e = _dot(d1, d1), _dot(d2, d2)
    if a <= _EPS or e <= _EPS:
        raise _Invalid("edge is degenerate during its linear trajectory")
    b, c, f = _dot(d1, d2), _dot(d1, r), _dot(d2, r)
    denom = a*e - b*b
    s = 0.0 if abs(denom) <= _EPS else max(0.0, min(1.0, (b*f-c*e)/denom))
    t = (b*s + f) / e
    if t < 0.0:
        t, s = 0.0, max(0.0, min(1.0, -c/a))
    elif t > 1.0:
        t, s = 1.0, max(0.0, min(1.0, (b-c)/a))
    return _lerp(p1, q1, s), _lerp(p2, q2, t), s, t


def _toi(distance_at: Any, speed_bound: float, thickness: float,
         max_iterations: int) -> Dict[str, Any]:
    d0, data0 = distance_at(0.0)
    if d0 <= _EPS:
        return _unknown(INITIAL_INTERSECTION, "primitives intersect at t=0")
    if d0 <= thickness + _EPS:
        return {"verdict": ANSWER, "hit": True, "toi": 0.0,
                "distance_m": d0, "contact": data0, "initially_within_thickness": True}
    if speed_bound <= _EPS:
        return {"verdict": ANSWER, "hit": False, "toi": None,
                "minimum_distance_lower_bound_m": d0}
    t, previous_t = 0.0, 0.0
    for _ in range(max_iterations):
        distance, data = distance_at(t)
        if distance <= thickness + _EPS:
            lo, hi = previous_t, t
            for _bisect in range(60):
                mid = 0.5*(lo+hi)
                if distance_at(mid)[0] <= thickness:
                    hi = mid
                else:
                    lo = mid
                if hi-lo <= _TIME_EPS:
                    break
            hit_distance, hit_data = distance_at(hi)
            return {"verdict": ANSWER, "hit": True, "toi": hi,
                    "distance_m": hit_distance, "contact": hit_data,
                    "initially_within_thickness": False}
        if t >= 1.0:
            return {"verdict": ANSWER, "hit": False, "toi": None,
                    "distance_at_end_m": distance}
        previous_t = t
        step = max(_TIME_EPS, 0.9*(distance-thickness)/speed_bound)
        t = min(1.0, t+step)
    return _unknown(NO_CONVERGENCE, "conservative advancement exceeded max_iterations")


def vertex_triangle_toi(vertex_start: Sequence[float], vertex_end: Sequence[float],
                        triangle_start: Sequence[Sequence[float]],
                        triangle_end: Sequence[Sequence[float]], *,
                        thickness_m: float = 0.0,
                        max_iterations: int = 256) -> Dict[str, Any]:
    """First contact time in normalized ``[0,1]`` for linear trajectories."""
    try:
        p0, p1 = _vec(vertex_start, "vertex_start"), _vec(vertex_end, "vertex_end")
        if len(triangle_start) != 3 or len(triangle_end) != 3:
            raise _Invalid("triangle_start and triangle_end must contain three vertices")
        a0 = tuple(_vec(v, f"triangle_start[{i}]") for i, v in enumerate(triangle_start))
        a1 = tuple(_vec(v, f"triangle_end[{i}]") for i, v in enumerate(triangle_end))
        thickness = _number(thickness_m, "thickness_m", low=0.0)
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
            raise _Invalid("max_iterations must be a positive integer")
        for endpoint in (a0, a1):
            if _length(_cross(_sub(endpoint[1], endpoint[0]), _sub(endpoint[2], endpoint[0]))) <= _EPS:
                raise _Invalid("triangle endpoint geometry is degenerate")
        velocities = [_sub(p1, p0)] + [_sub(a1[i], a0[i]) for i in range(3)]
        bound = _length(velocities[0]) + max(_length(v) for v in velocities[1:])

        def distance_at(t: float) -> Tuple[float, Dict[str, Any]]:
            p = _lerp(p0, p1, t)
            tri = tuple(_lerp(a0[i], a1[i], t) for i in range(3))
            closest, bary = _closest_triangle(p, *tri)
            delta = _sub(p, closest)
            distance = _length(delta)
            normal = _unit(delta) if distance > _EPS else _unit(
                _cross(_sub(tri[1], tri[0]), _sub(tri[2], tri[0])))
            return distance, {"point": list(p), "triangle_point": list(closest),
                              "barycentric": list(bary), "normal": list(normal)}
        return _toi(distance_at, bound, thickness, max_iterations)
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error))


def edge_edge_toi(edge_a_start: Sequence[Sequence[float]], edge_a_end: Sequence[Sequence[float]],
                  edge_b_start: Sequence[Sequence[float]], edge_b_end: Sequence[Sequence[float]], *,
                  thickness_m: float = 0.0, max_iterations: int = 256) -> Dict[str, Any]:
    """First finite-thickness contact time for two linearly moving edges."""
    try:
        groups = (edge_a_start, edge_a_end, edge_b_start, edge_b_end)
        if any(len(group) != 2 for group in groups):
            raise _Invalid("each edge endpoint state must contain two vertices")
        ea0, ea1, eb0, eb1 = (tuple(_vec(v, "edge vertex") for v in group) for group in groups)
        for edge in (ea0, ea1, eb0, eb1):
            if _length(_sub(edge[1], edge[0])) <= _EPS:
                raise _Invalid("edge endpoint geometry is degenerate")
        thickness = _number(thickness_m, "thickness_m", low=0.0)
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
            raise _Invalid("max_iterations must be a positive integer")
        va = [_sub(ea1[i], ea0[i]) for i in range(2)]
        vb = [_sub(eb1[i], eb0[i]) for i in range(2)]
        bound = max(_length(v) for v in va) + max(_length(v) for v in vb)

        def distance_at(t: float) -> Tuple[float, Dict[str, Any]]:
            a = tuple(_lerp(ea0[i], ea1[i], t) for i in range(2))
            b = tuple(_lerp(eb0[i], eb1[i], t) for i in range(2))
            pa, pb, sa, sb = _closest_segments(*a, *b)
            delta, distance = _sub(pa, pb), _length(_sub(pa, pb))
            if distance > _EPS:
                normal = _unit(delta)
            else:
                normal = _unit(_cross(_sub(a[1], a[0]), _sub(b[1], b[0])))
            return distance, {"edge_a_point": list(pa), "edge_b_point": list(pb),
                              "edge_a_parameter": sa, "edge_b_parameter": sb,
                              "normal": list(normal)}
        return _toi(distance_at, bound, thickness, max_iterations)
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error))


def project_contacts(old_positions: Sequence[Sequence[float]],
                     predicted_positions: Sequence[Sequence[float]],
                     faces: Sequence[Sequence[int]], *, thickness_m: float,
                     friction_coefficient: float = 0.0,
                     inverse_masses: Optional[Sequence[float]] = None,
                     _friction_static: Optional[float] = None) -> Dict[str, Any]:
    """Enumerate VT contacts and apply one immutable-state Jacobi correction.

    Incident vertex/face pairs are excluded.  Edge-edge TOI remains available
    as a narrow-phase query; it is not duplicated here because cloth mesh edges
    need topology-aware candidate filtering supplied by a broad phase.
    """
    snapshot = copy.deepcopy({"old_positions": old_positions,
                              "predicted_positions": predicted_positions,
                              "faces": faces})
    try:
        old = tuple(_vec(v, f"old_positions[{i}]") for i, v in enumerate(old_positions))
        predicted = tuple(_vec(v, f"predicted_positions[{i}]") for i, v in enumerate(predicted_positions))
        if len(old) != len(predicted) or not old:
            raise _Invalid("old_positions and predicted_positions must have the same non-zero length")
        thickness = _number(thickness_m, "thickness_m", low=0.0, strict=True)
        friction = _number(friction_coefficient, "friction_coefficient", low=0.0)
        static_friction = friction if _friction_static is None else _number(
            _friction_static, "friction_static", low=friction)
        masses = ([1.0]*len(old) if inverse_masses is None else
                  [_number(v, f"inverse_masses[{i}]", low=0.0) for i, v in enumerate(inverse_masses)])
        if len(masses) != len(old):
            raise _Invalid("inverse_masses must contain one value per vertex")
        parsed_faces = []
        for fi, face in enumerate(faces):
            if (not isinstance(face, (list, tuple)) or len(face) != 3 or
                    any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(old) for i in face) or
                    len(set(face)) != 3):
                raise _Invalid(f"faces[{fi}] must contain three distinct valid indices")
            tri = tuple(int(i) for i in face)
            for positions in (old, predicted):
                if _length(_cross(_sub(positions[tri[1]], positions[tri[0]]),
                                  _sub(positions[tri[2]], positions[tri[0]]))) <= _EPS:
                    raise _Invalid(f"faces[{fi}] is degenerate")
            parsed_faces.append(tri)
        corrections: List[Vec3] = [(0.0, 0.0, 0.0) for _ in old]
        weights = [0.0]*len(old)
        contacts = []
        for vi in range(len(old)):
            for fi, face in enumerate(parsed_faces):
                if vi in face:
                    continue
                query = vertex_triangle_toi(old[vi], predicted[vi],
                    [old[i] for i in face], [predicted[i] for i in face], thickness_m=thickness)
                if query["verdict"] == INITIAL_INTERSECTION:
                    return _unknown(INITIAL_INTERSECTION,
                        f"vertex {vi} and face {fi} intersect at the old state",
                        immutable_input_snapshot=snapshot, backend=capabilities())
                if query["verdict"] != ANSWER:
                    return dict(query, immutable_input_snapshot=snapshot, backend=capabilities())
                if not query["hit"]:
                    continue
                contact = query["contact"]
                normal = tuple(contact["normal"])
                bary = tuple(contact["barycentric"])
                closest, _ = _closest_triangle(predicted[vi], *(predicted[i] for i in face))
                gap = _dot(_sub(predicted[vi], closest), normal)
                penetration = max(0.0, thickness-gap)
                if penetration <= _EPS:
                    continue
                coefficients = [(vi, 1.0)] + [(face[j], -bary[j]) for j in range(3)]
                denominator = sum(masses[index]*coefficient*coefficient for index, coefficient in coefficients)
                if denominator <= _EPS:
                    raise _Invalid("contact has no movable mass")
                lam = penetration/denominator
                for index, coefficient in coefficients:
                    normal_delta = _mul(normal, masses[index]*coefficient*lam)
                    displacement = _sub(predicted[index], old[index])
                    tangent = _sub(displacement, _mul(normal, _dot(displacement, normal)))
                    tangent_length = _length(tangent)
                    friction_delta = (0.0, 0.0, 0.0)
                    if tangent_length > _EPS and friction > 0.0:
                        friction_limit = static_friction*penetration
                        if tangent_length <= friction_limit:
                            friction_delta = _mul(tangent, -1.0)
                        else:
                            friction_delta = _mul(tangent, -min(
                                1.0, friction*penetration/tangent_length))
                    corrections[index] = _add(corrections[index], _add(normal_delta, friction_delta))
                    weights[index] += 1.0
                contacts.append({"kind": "VERTEX_TRIANGLE", "vertex": vi, "face": fi,
                                 "toi": query["toi"], "penetration_m": penetration,
                                 "normal": list(normal), "barycentric": list(bary)})
        result = []
        for i, position in enumerate(predicted):
            delta = corrections[i] if weights[i] == 0.0 else _mul(corrections[i], 1.0/weights[i])
            result.append(list(_add(position, delta)))
        return {"verdict": ANSWER, "positions": result, "contacts": contacts,
                "projection": "same-old-state Jacobi", "thickness_m": thickness,
                "friction_static": static_friction,
                "friction_dynamic": friction, "backend": capabilities(),
                "immutable_input_snapshot": snapshot}
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error), immutable_input_snapshot=snapshot,
                        backend=capabilities())


def evaluate_seams(old_positions: Sequence[Sequence[float]],
                   predicted_positions: Sequence[Sequence[float]],
                   seams: Sequence[Mapping[str, Any]], *, dt_s: float) -> Dict[str, Any]:
    """Project seam extension and report slip, damage, and puckering indicators.

    Required seam fields are ``a``, ``b``, ``rest_length_m``,
    ``damage_onset_strain`` and ``break_strain``.  Optional values are
    ``compliance_m_n`` (default 0), ``previous_damage`` (default 0), and
    ``feed_mismatch_ratio`` (default 0).  Damage is monotone and reaches one at
    the declared break strain; this is a typed phenomenological law only.
    """
    snapshot = copy.deepcopy({"old_positions": old_positions,
                              "predicted_positions": predicted_positions,
                              "seams": seams})
    try:
        old = tuple(_vec(v, f"old_positions[{i}]") for i, v in enumerate(old_positions))
        predicted = tuple(_vec(v, f"predicted_positions[{i}]") for i, v in enumerate(predicted_positions))
        if len(old) != len(predicted) or not old:
            raise _Invalid("position arrays must have equal non-zero length")
        dt = _number(dt_s, "dt_s", low=0.0, strict=True)
        corrections: List[Vec3] = [(0.0, 0.0, 0.0) for _ in old]
        counts = [0]*len(old)
        reports = []
        for si, raw in enumerate(seams):
            if not isinstance(raw, Mapping):
                raise _Invalid(f"seams[{si}] must be a mapping")
            a, b = raw.get("a"), raw.get("b")
            if (isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or
                    not isinstance(b, int) or a == b or not 0 <= a < len(old) or not 0 <= b < len(old)):
                raise _Invalid(f"seams[{si}] has invalid endpoint indices")
            rest = _number(raw.get("rest_length_m"), f"seams[{si}].rest_length_m", low=0.0, strict=True)
            onset = _number(raw.get("damage_onset_strain"), f"seams[{si}].damage_onset_strain", low=0.0)
            breaking = _number(raw.get("break_strain"), f"seams[{si}].break_strain", low=onset, strict=True)
            compliance = _number(raw.get("compliance_m_n", 0.0), f"seams[{si}].compliance_m_n", low=0.0)
            previous_damage = _number(raw.get("previous_damage", 0.0), f"seams[{si}].previous_damage", low=0.0)
            mismatch = _number(raw.get("feed_mismatch_ratio", 0.0), f"seams[{si}].feed_mismatch_ratio")
            if previous_damage > 1.0:
                raise _Invalid(f"seams[{si}].previous_damage must be <= 1")
            delta = _sub(predicted[b], predicted[a])
            length = _length(delta)
            if length <= _EPS:
                raise _Invalid(f"seams[{si}] endpoints coincide")
            strain = (length-rest)/rest
            old_axis = _unit(_sub(old[b], old[a]))
            relative_motion = _sub(_sub(predicted[b], old[b]), _sub(predicted[a], old[a]))
            tangential = _sub(relative_motion, _mul(old_axis, _dot(relative_motion, old_axis)))
            slip_m = _length(tangential)
            trial_damage = max(0.0, min(1.0, (strain-onset)/(breaking-onset)))
            damage = max(previous_damage, trial_damage)
            broken = damage >= 1.0
            extension = max(0.0, length-rest)
            alpha = compliance/(dt*dt)
            correction_magnitude = 0.0 if broken else extension/(2.0+alpha)
            direction = _unit(delta)
            correction = _mul(direction, correction_magnitude)
            corrections[a] = _add(corrections[a], correction)
            corrections[b] = _sub(corrections[b], correction)
            counts[a] += 1
            counts[b] += 1
            compression = max(0.0, -strain)
            puckering = max(0.0, min(1.0, abs(mismatch) + compression + 0.5*damage))
            reports.append({
                "seam_index": si, "strain": strain, "slip_m": slip_m,
                "damage_index": damage, "damage_state": ("BROKEN" if broken else
                    "PRE_BREAK_DAMAGE" if damage > 0.0 else "INTACT"),
                "puckering_index": puckering,
                "puckering_components": {"feed_mismatch": abs(mismatch),
                                          "compression": compression,
                                          "damage_coupling": 0.5*damage},
            })
        positions = []
        for i, position in enumerate(predicted):
            delta = corrections[i] if counts[i] == 0 else _mul(corrections[i], 1.0/counts[i])
            positions.append(list(_add(position, delta)))
        return {"verdict": ANSWER, "positions": positions, "seams": reports,
                "projection": "same-old-state Jacobi", "dt_s": dt,
                "model": "phenomenological_reference_not_material_calibration",
                "backend": capabilities(), "immutable_input_snapshot": snapshot}
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error), immutable_input_snapshot=snapshot,
                        backend=capabilities())


def solve(previous_positions: Sequence[Sequence[float]],
          proposed_positions: Sequence[Sequence[float]],
          faces: Sequence[Sequence[int]], *,
          edges: Sequence[Sequence[int]] = (),
          seams: Sequence[Mapping[str, Any]] = (),
          thickness_m: float,
          friction_static: float,
          friction_dynamic: float,
          time_step_s: float) -> Dict[str, Any]:
    """Solve one deterministic CCD/contact/seam projection boundary.

    Every contact and seam layer reads ``proposed_positions`` unchanged.  Each
    layer returns a correction relative to that same state; this function then
    reduces those corrections once.  ``edges`` are explicit broad-phase
    candidates represented by vertex-index pairs.  Pairs sharing a vertex are
    topological neighbours and are skipped.
    """
    snapshot = copy.deepcopy({
        "previous_positions": previous_positions,
        "proposed_positions": proposed_positions,
        "faces": faces, "edges": edges, "seams": seams,
    })
    try:
        previous = tuple(_vec(v, f"previous_positions[{i}]")
                         for i, v in enumerate(previous_positions))
        proposed = tuple(_vec(v, f"proposed_positions[{i}]")
                         for i, v in enumerate(proposed_positions))
        if len(previous) != len(proposed) or not previous:
            raise _Invalid("previous_positions and proposed_positions must have equal non-zero length")
        thickness = _number(thickness_m, "thickness_m", low=0.0, strict=True)
        dynamic = _number(friction_dynamic, "friction_dynamic", low=0.0)
        static = _number(friction_static, "friction_static", low=dynamic)
        dt = _number(time_step_s, "time_step_s", low=0.0, strict=True)

        vertex_face = project_contacts(
            previous, proposed, faces, thickness_m=thickness,
            friction_coefficient=dynamic, _friction_static=static)
        if vertex_face["verdict"] != ANSWER:
            return dict(vertex_face, immutable_input_snapshot=snapshot)

        parsed_edges: List[Tuple[int, int]] = []
        for ei, edge in enumerate(edges):
            if (not isinstance(edge, (list, tuple)) or len(edge) != 2 or
                    any(isinstance(i, bool) or not isinstance(i, int) or
                        not 0 <= i < len(previous) for i in edge) or edge[0] == edge[1]):
                raise _Invalid(f"edges[{ei}] must contain two distinct valid indices")
            pair = int(edge[0]), int(edge[1])
            for positions in (previous, proposed):
                if _length(_sub(positions[pair[1]], positions[pair[0]])) <= _EPS:
                    raise _Invalid(f"edges[{ei}] is degenerate")
            parsed_edges.append(pair)

        edge_corrections: List[Vec3] = [(0.0, 0.0, 0.0) for _ in proposed]
        edge_counts = [0]*len(proposed)
        edge_contacts = []
        for ai, edge_a in enumerate(parsed_edges):
            for bi in range(ai+1, len(parsed_edges)):
                edge_b = parsed_edges[bi]
                if set(edge_a) & set(edge_b):
                    continue
                query = edge_edge_toi(
                    [previous[i] for i in edge_a], [proposed[i] for i in edge_a],
                    [previous[i] for i in edge_b], [proposed[i] for i in edge_b],
                    thickness_m=thickness)
                if query["verdict"] == INITIAL_INTERSECTION:
                    return _unknown(INITIAL_INTERSECTION,
                        f"edges {ai} and {bi} intersect at the old state",
                        immutable_input_snapshot=snapshot, backend=capabilities())
                if query["verdict"] != ANSWER:
                    return dict(query, immutable_input_snapshot=snapshot,
                                backend=capabilities())
                if not query["hit"]:
                    continue
                pa, pb, sa, sb = _closest_segments(
                    proposed[edge_a[0]], proposed[edge_a[1]],
                    proposed[edge_b[0]], proposed[edge_b[1]])
                normal = tuple(query["contact"]["normal"])
                gap = _dot(_sub(pa, pb), normal)
                penetration = max(0.0, thickness-gap)
                if penetration <= _EPS:
                    continue
                coefficients = ((edge_a[0], 1.0-sa), (edge_a[1], sa),
                                (edge_b[0], -(1.0-sb)), (edge_b[1], -sb))
                denominator = sum(coefficient*coefficient for _, coefficient in coefficients)
                if denominator <= _EPS:
                    raise _Invalid("edge contact correction is singular")
                lam = penetration/denominator
                motion_a = _lerp(_sub(proposed[edge_a[0]], previous[edge_a[0]]),
                                 _sub(proposed[edge_a[1]], previous[edge_a[1]]), sa)
                motion_b = _lerp(_sub(proposed[edge_b[0]], previous[edge_b[0]]),
                                 _sub(proposed[edge_b[1]], previous[edge_b[1]]), sb)
                relative_motion = _sub(motion_a, motion_b)
                tangent = _sub(relative_motion, _mul(normal, _dot(relative_motion, normal)))
                tangent_length = _length(tangent)
                if tangent_length <= static*penetration:
                    friction_delta = _mul(tangent, -1.0)
                    regime = "STATIC"
                elif tangent_length > _EPS:
                    friction_delta = _mul(tangent, -min(1.0, dynamic*penetration/tangent_length))
                    regime = "DYNAMIC"
                else:
                    friction_delta, regime = (0.0, 0.0, 0.0), "NONE"
                for index, coefficient in coefficients:
                    delta = _add(_mul(normal, coefficient*lam),
                                 _mul(friction_delta, abs(coefficient)/2.0))
                    edge_corrections[index] = _add(edge_corrections[index], delta)
                    edge_counts[index] += 1
                edge_contacts.append({"kind": "EDGE_EDGE", "edge_a": ai,
                    "edge_b": bi, "toi": query["toi"],
                    "penetration_m": penetration, "friction_regime": regime,
                    "edge_a_parameter": sa, "edge_b_parameter": sb})

        seam_result = evaluate_seams(previous, proposed, seams, dt_s=dt)
        if seam_result["verdict"] != ANSWER:
            return dict(seam_result, immutable_input_snapshot=snapshot)

        final_positions = []
        for i, base in enumerate(proposed):
            vertex_delta = _sub(tuple(vertex_face["positions"][i]), base)
            edge_delta = (edge_corrections[i] if edge_counts[i] == 0 else
                          _mul(edge_corrections[i], 1.0/edge_counts[i]))
            seam_delta = _sub(tuple(seam_result["positions"][i]), base)
            final_positions.append(list(_add(base, _add(vertex_delta,
                _add(edge_delta, seam_delta)))))
        return {
            "verdict": ANSWER,
            "positions": final_positions,
            "contacts": vertex_face["contacts"] + edge_contacts,
            "seams": seam_result["seams"],
            "projection": "same-old-state Jacobi",
            "parameters": {"thickness_m": thickness,
                           "friction_static": static,
                           "friction_dynamic": dynamic,
                           "time_step_s": dt},
            "backend": capabilities(),
            "immutable_input_snapshot": snapshot,
        }
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error),
                        immutable_input_snapshot=snapshot, backend=capabilities())
