# -*- coding: utf-8 -*-
"""Deterministic yarn/needle reference simulation.

Yarn is a discrete elastic rod with separate stretch and bending projections.
The needle is a moving rigid path.  Triangle crossings create typed penetration
events and, in pairs, stitch/loop graph updates.  This is a geometric CPU
reference for verification; it is not an industrial sewing-machine simulator.
All geometry uses SI units.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_YARN_NEEDLE_INVALID_INPUT"
BREAKAGE = "UNKNOWN_YARN_BREAKAGE"
INVALID_TOPOLOGY = "UNKNOWN_STITCH_TOPOLOGY"
_EPS = 1.0e-12


class _Invalid(ValueError):
    pass


class _TopologyInvalid(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Return an honest declaration of this reference backend."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python",
        "deterministic": True,
        "units": "SI",
        "features": {
            "discrete_elastic_rod": True,
            "stretch": True,
            "bending": True,
            "yarn_cloth_contact_candidates": True,
            "moving_rigid_needle_path": True,
            "needle_penetration_events": True,
            "stitch_and_loop_graph": True,
            "undoable_event_log": True,
            "same_old_state_jacobi": True,
            "continuous_collision": False,
            "frictional_contact_solve": False,
            "thread_twist_and_torsion": False,
            "industrial_sewing_machine": False,
        },
        "limitations": [
            "needle/cloth intersections are piecewise-linear and discrete",
            "contact output is candidate geometry, not an impulse solve",
            "stitch topology does not model lockstitch/bobbin mechanics",
        ],
    }


def _refusal(code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "reasons": [reason], **extra}


def _number(value: Any, name: str, *, low: Optional[float] = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a finite SI number")
    result = float(value)
    if not math.isfinite(result):
        raise _Invalid(f"{name} must be finite")
    if low is not None and (result <= low if strict else result < low):
        raise _Invalid(f"{name} must be {'>' if strict else '>='} {low}")
    return result


def _integer(value: Any, name: str, *, low: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise _Invalid(f"{name} must be an integer >= {low}")
    return value


def _vec(value: Any, name: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must have three components")
    return tuple(_number(x, f"{name}[{i}]") for i, x in enumerate(value))  # type: ignore[return-value]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(a: Vec3, scale: float) -> Vec3:
    return a[0] * scale, a[1] * scale, a[2] * scale


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _triangle_closest(point: Vec3, a: Vec3, b: Vec3, c: Vec3) -> Tuple[Vec3, Tuple[float, float, float]]:
    """Closest point and barycentrics (Ericson region tests)."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, (1.0, 0.0, 0.0)
    bp = _sub(point, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1*d4 - d3*d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return _add(a, _mul(ab, v)), (1.0-v, v, 0.0)
    cp = _sub(point, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5*d2 - d1*d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return _add(a, _mul(ac, w)), (1.0-w, 0.0, w)
    va = d3*d6 - d5*d4
    if va <= 0.0 and (d4-d3) >= 0.0 and (d5-d6) >= 0.0:
        w = (d4-d3) / ((d4-d3) + (d5-d6))
        return _add(b, _mul(_sub(c, b), w)), (0.0, 1.0-w, w)
    denominator = va + vb + vc
    if abs(denominator) <= _EPS:
        raise _Invalid("cloth contains a degenerate triangle")
    v, w = vb/denominator, vc/denominator
    return _add(a, _add(_mul(ab, v), _mul(ac, w))), (1.0-v-w, v, w)


def _segment_triangle(start: Vec3, end: Vec3, a: Vec3, b: Vec3,
                      c: Vec3) -> Optional[Tuple[float, Vec3, Tuple[float, float, float], int]]:
    direction = _sub(end, start)
    edge1, edge2 = _sub(b, a), _sub(c, a)
    normal = _cross(edge1, edge2)
    if _length(normal) <= _EPS:
        raise _Invalid("cloth contains a degenerate triangle")
    h = _cross(direction, edge2)
    determinant = _dot(edge1, h)
    if abs(determinant) <= _EPS:
        return None
    inverse = 1.0 / determinant
    s = _sub(start, a)
    u = inverse * _dot(s, h)
    if u < -_EPS or u > 1.0 + _EPS:
        return None
    q = _cross(s, edge1)
    v = inverse * _dot(direction, q)
    if v < -_EPS or u + v > 1.0 + _EPS:
        return None
    t = inverse * _dot(edge2, q)
    if t <= _EPS or t > 1.0 + _EPS:
        return None
    point = _add(start, _mul(direction, t))
    orientation = 1 if _dot(direction, normal) > 0.0 else -1
    return t, point, (1.0-u-v, u, v), orientation


def _parse_topology(raw: Any) -> Dict[str, List[Dict[str, Any]]]:
    if raw is None:
        return {"anchors": [], "stitch_edges": [], "loops": []}
    if not isinstance(raw, Mapping):
        raise _TopologyInvalid("initial_topology must be an object")
    topology: Dict[str, List[Dict[str, Any]]] = {}
    for key in ("anchors", "stitch_edges", "loops"):
        values = raw.get(key, [])
        if not isinstance(values, list) or any(not isinstance(x, Mapping) for x in values):
            raise _TopologyInvalid(f"initial_topology.{key} must be an object list")
        topology[key] = [copy.deepcopy(dict(x)) for x in values]
    _validate_topology(topology)
    return topology


def _validate_topology(topology: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    def ids(key: str) -> List[str]:
        result = [x.get("id") for x in topology[key]]
        if any(not isinstance(x, str) or not x for x in result) or len(set(result)) != len(result):
            raise _TopologyInvalid(f"{key} ids must be nonempty and unique")
        return result  # type: ignore[return-value]
    anchors = set(ids("anchors"))
    edges = ids("stitch_edges")
    loops = ids("loops")
    for edge in topology["stitch_edges"]:
        endpoints = edge.get("anchors")
        if (not isinstance(endpoints, list) or len(endpoints) != 2
                or endpoints[0] == endpoints[1]
                or any(x not in anchors for x in endpoints)):
            raise _TopologyInvalid("stitch edge must join two distinct existing anchors")
    edge_set = set(edges)
    for loop in topology["loops"]:
        members = loop.get("stitch_edges")
        if not isinstance(members, list) or not members or any(x not in edge_set for x in members):
            raise _TopologyInvalid("loop must reference existing stitch edges")
    if len(set(loops)) != len(loops):
        raise _TopologyInvalid("loop ids must be unique")


def _rod_projection(rest: Sequence[Vec3], initial: Sequence[Vec3], rest_lengths: Sequence[float],
                    stretch_stiffness: float, bend_stiffness: float,
                    time_step: float, iterations: int, pinned: set[int]) -> Tuple[List[Vec3], Dict[str, float]]:
    positions = list(initial)
    rest_curvature = [_add(_sub(rest[i-1], _mul(rest[i], 2.0)), rest[i+1])
                      for i in range(1, len(rest)-1)]
    stretch_factor = 1.0 / (1.0 + 1.0/(stretch_stiffness*time_step*time_step))
    bend_factor = 1.0 / (1.0 + 1.0/(bend_stiffness*time_step*time_step))
    for _ in range(iterations):
        old = tuple(positions)
        corrections = [(0.0, 0.0, 0.0) for _ in old]
        weights = [0.0 for _ in old]
        for i, length0 in enumerate(rest_lengths):
            edge = _sub(old[i+1], old[i])
            length = _length(edge)
            if length <= _EPS:
                raise _Invalid("a yarn segment collapsed to zero length")
            delta = _mul(edge, stretch_factor*(length-length0)/length)
            if i not in pinned:
                corrections[i] = _add(corrections[i], _mul(delta, 0.5))
                weights[i] += 1.0
            if i+1 not in pinned:
                corrections[i+1] = _sub(corrections[i+1], _mul(delta, 0.5))
                weights[i+1] += 1.0
        for i in range(1, len(old)-1):
            current = _add(_sub(old[i-1], _mul(old[i], 2.0)), old[i+1])
            error = _sub(current, rest_curvature[i-1])
            for node, scale in ((i-1, -1.0/6.0), (i, 1.0/3.0), (i+1, -1.0/6.0)):
                if node not in pinned:
                    corrections[node] = _add(corrections[node], _mul(error, bend_factor*scale))
                    weights[node] += 1.0
        positions = [old[i] if i in pinned or weights[i] == 0.0
                     else _add(old[i], _mul(corrections[i], 1.0/weights[i]))
                     for i in range(len(old))]
    strains = [abs(_distance(positions[i], positions[i+1])-length0)/length0
               for i, length0 in enumerate(rest_lengths)]
    bend_errors = [_length(_sub(
        _add(_sub(positions[i-1], _mul(positions[i], 2.0)), positions[i+1]),
        rest_curvature[i-1])) for i in range(1, len(positions)-1)]
    stretch_energy = sum(0.5*stretch_stiffness*(s*l)**2
                         for s, l in zip(strains, rest_lengths))
    bend_energy = sum(0.5*bend_stiffness*x*x for x in bend_errors)
    return positions, {"maximum_stretch_strain": max(strains, default=0.0),
                       "maximum_bend_error_m": max(bend_errors, default=0.0),
                       "stretch_energy_j": stretch_energy,
                       "bending_energy_j": bend_energy}


def _contact_candidates(positions: Sequence[Vec3], faces: Sequence[Tuple[int, int, int]],
                        cloth: Sequence[Vec3], threshold: float) -> List[Dict[str, Any]]:
    contacts = []
    for segment in range(len(positions)-1):
        samples = (("start", positions[segment]), ("end", positions[segment+1]))
        for face_index, face in enumerate(faces):
            a, b, c = (cloth[i] for i in face)
            crossing = _segment_triangle(positions[segment], positions[segment+1], a, b, c)
            best = None
            for label, point in samples:
                closest, bary = _triangle_closest(point, a, b, c)
                candidate = (_distance(point, closest), label, closest, bary)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
            assert best is not None
            if crossing is not None or best[0] <= threshold:
                if crossing is not None:
                    _, point, bary, _ = crossing
                    distance, sample = 0.0, "intersection"
                else:
                    distance, sample, point, bary = best
                contacts.append({"segment": segment, "face": face_index,
                                 "distance_m": distance, "sample": sample,
                                 "point_m": list(point), "barycentric": list(bary)})
    return sorted(contacts, key=lambda x: (x["segment"], x["face"], x["distance_m"], x["sample"]))


def _apply_event(topology: Dict[str, List[Dict[str, Any]]], event: Mapping[str, Any]) -> None:
    if event["kind"] == "NEEDLE_PENETRATION":
        topology["anchors"].append(copy.deepcopy(event["effect"]["anchor"]))
    elif event["kind"] == "STITCH_FORMED":
        topology["stitch_edges"].append(copy.deepcopy(event["effect"]["stitch_edge"]))
        topology["loops"].append(copy.deepcopy(event["effect"]["loop"]))


def simulate(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run a deterministic discrete-rod and needle-path reference simulation."""
    try:
        if not isinstance(request, Mapping):
            raise _Invalid("request must be an object")
        yarn, needle, cloth_raw = request.get("yarn"), request.get("needle"), request.get("cloth")
        if not all(isinstance(x, Mapping) for x in (yarn, needle, cloth_raw)):
            raise _Invalid("request requires yarn, needle, and cloth objects")

        rest = tuple(_vec(x, f"yarn.rest_positions_m[{i}]")
                     for i, x in enumerate(yarn.get("rest_positions_m", [])))
        if len(rest) < 2:
            raise _Invalid("yarn needs at least two rest positions")
        initial_raw = yarn.get("initial_positions_m", rest)
        initial = tuple(_vec(x, f"yarn.initial_positions_m[{i}]")
                        for i, x in enumerate(initial_raw))
        if len(initial) != len(rest):
            raise _Invalid("initial and rest yarn node counts differ")
        rest_lengths = tuple(_distance(rest[i], rest[i+1]) for i in range(len(rest)-1))
        if any(x <= _EPS for x in rest_lengths):
            raise _Invalid("rest yarn segments must have positive length")
        stretch = _number(yarn.get("stretch_stiffness_n_m"), "stretch_stiffness_n_m", low=0.0, strict=True)
        bend = _number(yarn.get("bend_stiffness_n_m"), "bend_stiffness_n_m", low=0.0, strict=True)
        radius = _number(yarn.get("radius_m"), "yarn.radius_m", low=0.0, strict=True)
        breaking = _number(yarn.get("breaking_strain"), "yarn.breaking_strain", low=0.0, strict=True)
        pinned_raw = yarn.get("pinned_nodes", [])
        if (not isinstance(pinned_raw, list) or any(isinstance(i, bool) or not isinstance(i, int)
                or not 0 <= i < len(rest) for i in pinned_raw)):
            raise _Invalid("pinned_nodes contains an invalid yarn index")
        pinned = set(pinned_raw)
        initial_strains = [abs(_distance(initial[i], initial[i+1])-length)/length
                           for i, length in enumerate(rest_lengths)]
        max_initial = max(initial_strains, default=0.0)
        if max_initial > breaking:
            return _refusal(BREAKAGE, "initial yarn strain exceeds breaking_strain",
                            maximum_strain=max_initial, breaking_strain=breaking)

        cloth = tuple(_vec(x, f"cloth.vertices_m[{i}]")
                      for i, x in enumerate(cloth_raw.get("vertices_m", [])))
        faces_list = []
        for i, raw in enumerate(cloth_raw.get("faces", [])):
            if (not isinstance(raw, (list, tuple)) or len(raw) != 3
                    or any(isinstance(v, bool) or not isinstance(v, int)
                           or not 0 <= v < len(cloth) for v in raw)
                    or len(set(raw)) != 3):
                raise _Invalid(f"cloth.faces[{i}] is invalid")
            face = tuple(raw)
            if _length(_cross(_sub(cloth[face[1]], cloth[face[0]]),
                              _sub(cloth[face[2]], cloth[face[0]]))) <= _EPS:
                raise _Invalid(f"cloth.faces[{i}] is degenerate")
            faces_list.append(face)
        faces = tuple(faces_list)
        if not faces:
            raise _Invalid("cloth needs at least one triangle")
        thickness = _number(cloth_raw.get("thickness_m", 0.0), "cloth.thickness_m", low=0.0)

        path = tuple(_vec(x, f"needle.path_m[{i}]")
                     for i, x in enumerate(needle.get("path_m", [])))
        if len(path) < 2 or any(_distance(path[i], path[i+1]) <= _EPS for i in range(len(path)-1)):
            raise _Invalid("needle.path_m needs at least one nonzero segment")
        needle_radius = _number(needle.get("radius_m"), "needle.radius_m", low=0.0, strict=True)
        eye_node = _integer(needle.get("eye_yarn_node", len(rest)-1), "needle.eye_yarn_node")
        if eye_node >= len(rest):
            raise _Invalid("needle.eye_yarn_node is outside the yarn")

        time_step = _number(request.get("time_step_s", 1.0/120.0), "time_step_s", low=0.0, strict=True)
        iterations = _integer(request.get("solver_iterations", 20), "solver_iterations", low=1)
        undo_count = _integer(request.get("undo_events", 0), "undo_events")
        initial_topology = _parse_topology(request.get("initial_topology"))

        positions, rod = _rod_projection(rest, initial, rest_lengths, stretch,
                                         bend, time_step, iterations, pinned)
        if rod["maximum_stretch_strain"] > breaking:
            return _refusal(BREAKAGE, "projected yarn strain exceeds breaking_strain",
                            maximum_strain=rod["maximum_stretch_strain"], breaking_strain=breaking)
        contacts = _contact_candidates(positions, faces, cloth,
                                       radius + thickness)

        crossings = []
        for path_index in range(len(path)-1):
            for face_index, face in enumerate(faces):
                hit = _segment_triangle(path[path_index], path[path_index+1],
                                        cloth[face[0]], cloth[face[1]], cloth[face[2]])
                if hit is not None:
                    t, point, bary, orientation = hit
                    crossings.append((path_index, t, face_index, point, bary, orientation))
        crossings.sort(key=lambda x: (x[0], x[1], x[2]))

        topology = copy.deepcopy(initial_topology)
        journal: List[Dict[str, Any]] = []
        pending_anchor: Optional[str] = None
        for path_index, t, face_index, point, bary, orientation in crossings:
            anchor_id = f"anchor-{len(topology['anchors']):06d}"
            anchor = {"id": anchor_id, "cloth_face": face_index,
                      "barycentric": list(bary), "position_m": list(point),
                      "orientation": orientation, "yarn_node": eye_node}
            before = _digest(topology)
            event = {"id": f"event-{len(journal):06d}", "kind": "NEEDLE_PENETRATION",
                     "path_segment": path_index, "path_fraction": t,
                     "effect": {"anchor": anchor},
                     "inverse": {"remove_anchor": anchor_id}, "before_digest": before}
            _apply_event(topology, event)
            event["after_digest"] = _digest(topology)
            journal.append(event)
            if pending_anchor is None:
                pending_anchor = anchor_id
            else:
                edge_id = f"stitch-{len(topology['stitch_edges']):06d}"
                loop_id = f"loop-{len(topology['loops']):06d}"
                edge = {"id": edge_id, "anchors": [pending_anchor, anchor_id],
                        "yarn_node": eye_node}
                loop = {"id": loop_id, "stitch_edges": [edge_id],
                        "closure": "reference_pair"}
                before = _digest(topology)
                formed = {"id": f"event-{len(journal):06d}", "kind": "STITCH_FORMED",
                          "effect": {"stitch_edge": edge, "loop": loop},
                          "inverse": {"remove_loop": loop_id, "remove_stitch_edge": edge_id},
                          "before_digest": before}
                _apply_event(topology, formed)
                formed["after_digest"] = _digest(topology)
                journal.append(formed)
                pending_anchor = None

        if undo_count > len(journal):
            raise _Invalid("undo_events exceeds the generated event count")
        undone_ids = {event["id"] for event in journal[-undo_count:]} if undo_count else set()
        rebuilt = copy.deepcopy(initial_topology)
        event_log = []
        for event in journal:
            logged = copy.deepcopy(event)
            logged["active"] = event["id"] not in undone_ids
            if logged["active"]:
                _apply_event(rebuilt, event)
            event_log.append(logged)
        for event in reversed(journal[-undo_count:] if undo_count else []):
            event_log.append({"id": f"undo-{event['id']}", "kind": "UNDO",
                              "target_event": event["id"], "inverse": event["inverse"],
                              "active": True})
        _validate_topology(rebuilt)

        return {
            "verdict": ANSWER,
            "terminal_verdict": "REFERENCE_STEP_COMPLETE",
            "state": {"yarn_positions_m": [list(x) for x in positions],
                      "needle_position_m": list(path[-1]),
                      "topology": rebuilt},
            "contacts": contacts,
            "event_log": event_log,
            "diagnostics": {
                **rod,
                "initial_maximum_stretch_strain": max_initial,
                "constraint_projection": "JACOBI_SAME_OLD_STATE",
                "needle_penetrations_detected": len(crossings),
                "active_events": len(journal)-undo_count,
                "undone_events": undo_count,
                "topology_digest": _digest(rebuilt),
            },
            "claims": {"industrial_sewing_machine": False,
                       "reference_model_only": True},
        }
    except _TopologyInvalid as exc:
        return _refusal(INVALID_TOPOLOGY, str(exc))
    except (_Invalid, TypeError, ValueError) as exc:
        return _refusal(INVALID_INPUT, str(exc))
