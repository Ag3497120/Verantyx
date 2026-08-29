# -*- coding: utf-8 -*-
"""Reference-level sewing topology, yarn torsion, and friction extensions.

This module composes :mod:`photoloset.yarn_needle`.  Cloth edits are discrete,
auditable mesh operations; friction is a smooth regularized candidate force;
and yarn twist is a one-dimensional material-frame reference model.  It does
not claim production remeshing, robust cutting, or industrial sewing fidelity.
All geometry uses SI units.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import yarn_needle


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_SEWING_TOPOLOGY_INVALID_INPUT"
INVALID_TOPOLOGY = "UNKNOWN_SEWING_TOPOLOGY_INVALID_MESH"
UNSUPPORTED_CHANGE = "UNKNOWN_UNSUPPORTED_NON_MANIFOLD_CHANGE"
_EPS = 1.0e-12


class _Invalid(ValueError):
    pass


class _MeshInvalid(ValueError):
    pass


class _Unsupported(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Declare the reference boundary without promoting candidates to solves."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python",
        "level": "reference",
        "deterministic": True,
        "units": "SI",
        "features": {
            "yarn_twist_torsion": True,
            "regularized_friction_candidates": True,
            "cloth_cut_edge_detach": True,
            "triangle_barycentric_remesh": True,
            "topology_event_log": True,
            "reversible_suffix_undo": True,
            "non_manifold_changes": False,
            "continuous_cutting": False,
            "frictional_contact_impulse_solve": False,
            "industrial_sewing_machine": False,
        },
        "limitations": [
            "cut_edge detaches one incident triangle and is not a fracture solver",
            "remeshing splits one triangle and performs no quality optimization",
            "friction values are regularized candidate forces, not coupled impulses",
            "twist omits full rod-frame transport, writhe, and self-contact",
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
        raise _Invalid(f"{name} must contain three components")
    return tuple(_number(x, f"{name}[{i}]") for i, x in enumerate(value))  # type: ignore[return-value]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0]+b[0], a[1]+b[1], a[2]+b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _mul(a: Vec3, scale: float) -> Vec3:
    return a[0]*scale, a[1]*scale, a[2]*scale


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _mesh(vertices: Any, faces: Any) -> Dict[str, Any]:
    if not isinstance(vertices, (list, tuple)) or not isinstance(faces, (list, tuple)):
        raise _MeshInvalid("cloth vertices_m and faces must be lists")
    parsed_vertices = [list(_vec(value, f"cloth.vertices_m[{i}]"))
                       for i, value in enumerate(vertices)]
    parsed_faces = []
    for i, face in enumerate(faces):
        if (not isinstance(face, (list, tuple)) or len(face) != 3
                or any(isinstance(v, bool) or not isinstance(v, int)
                       or not 0 <= v < len(parsed_vertices) for v in face)
                or len(set(face)) != 3):
            raise _MeshInvalid(f"cloth.faces[{i}] must contain three distinct valid indices")
        a, b, c = (tuple(parsed_vertices[v]) for v in face)
        if _length(_cross(_sub(b, a), _sub(c, a))) <= _EPS:
            raise _MeshInvalid(f"cloth.faces[{i}] is degenerate")
        parsed_faces.append(list(face))
    if not parsed_faces:
        raise _MeshInvalid("cloth needs at least one triangle")
    result = {"vertices_m": parsed_vertices, "faces": parsed_faces}
    _validate_manifold(result)
    return result


def _edge_incidence(mesh: Mapping[str, Any]) -> Dict[Tuple[int, int], List[int]]:
    incidence: Dict[Tuple[int, int], List[int]] = {}
    for face_index, face in enumerate(mesh["faces"]):
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            incidence.setdefault(tuple(sorted((a, b))), []).append(face_index)
    return incidence


def _validate_manifold(mesh: Mapping[str, Any]) -> None:
    duplicate_faces = [tuple(sorted(face)) for face in mesh["faces"]]
    if len(set(duplicate_faces)) != len(duplicate_faces):
        raise _MeshInvalid("duplicate triangles are not supported")
    for edge, uses in _edge_incidence(mesh).items():
        if len(uses) > 2:
            raise _MeshInvalid(f"non-manifold edge {edge} has {len(uses)} incident faces")


def _cut_edge(mesh: Dict[str, Any], operation: Mapping[str, Any]) -> Dict[str, Any]:
    edge = operation.get("edge")
    if (not isinstance(edge, (list, tuple)) or len(edge) != 2
            or any(isinstance(v, bool) or not isinstance(v, int)
                   or not 0 <= v < len(mesh["vertices_m"]) for v in edge)
            or edge[0] == edge[1]):
        raise _Invalid("CUT_EDGE.edge must contain two distinct valid vertex indices")
    key = tuple(sorted(edge))
    uses = _edge_incidence(mesh).get(key, [])
    if len(uses) != 2:
        raise _Unsupported("CUT_EDGE currently supports only a two-face interior edge")
    detach_face = operation.get("detach_face", max(uses))
    if isinstance(detach_face, bool) or not isinstance(detach_face, int) or detach_face not in uses:
        raise _Invalid("CUT_EDGE.detach_face must be one of the edge's incident faces")
    replacements = {}
    for old in key:
        replacements[old] = len(mesh["vertices_m"])
        mesh["vertices_m"].append(list(mesh["vertices_m"][old]))
    mesh["faces"][detach_face] = [replacements.get(v, v)
                                  for v in mesh["faces"][detach_face]]
    _validate_manifold(mesh)
    return {"edge": list(key), "detached_face": detach_face,
            "duplicated_vertices": [{"source": old, "created": new}
                                    for old, new in sorted(replacements.items())]}


def _remesh_triangle(mesh: Dict[str, Any], operation: Mapping[str, Any]) -> Dict[str, Any]:
    face_index = operation.get("face")
    if (isinstance(face_index, bool) or not isinstance(face_index, int)
            or not 0 <= face_index < len(mesh["faces"])):
        raise _Invalid("REMESH_TRIANGLE.face must be a valid face index")
    bary_raw = operation.get("barycentric", [1.0/3.0]*3)
    if not isinstance(bary_raw, (list, tuple)) or len(bary_raw) != 3:
        raise _Invalid("REMESH_TRIANGLE.barycentric must have three values")
    bary = tuple(_number(x, f"barycentric[{i}]", low=0.0, strict=True)
                 for i, x in enumerate(bary_raw))
    if abs(sum(bary)-1.0) > 1.0e-9:
        raise _Invalid("REMESH_TRIANGLE.barycentric must sum to one")
    old_face = list(mesh["faces"][face_index])
    point = [sum(bary[j]*mesh["vertices_m"][old_face[j]][axis]
                 for j in range(3)) for axis in range(3)]
    created = len(mesh["vertices_m"])
    mesh["vertices_m"].append(point)
    triangles = [[old_face[0], old_face[1], created],
                 [old_face[1], old_face[2], created],
                 [old_face[2], old_face[0], created]]
    mesh["faces"][face_index] = triangles[0]
    mesh["faces"].extend(triangles[1:])
    _validate_manifold(mesh)
    return {"source_face": face_index, "source_vertices": old_face,
            "created_vertex": created, "created_faces":
            [face_index, len(mesh["faces"])-2, len(mesh["faces"])-1]}


def _topology_events(initial: Dict[str, Any], operations: Any,
                     undo_count: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(operations, list) or any(not isinstance(x, Mapping) for x in operations):
        raise _Invalid("topology_operations must be an object list")
    mesh = copy.deepcopy(initial)
    events = []
    for index, operation in enumerate(operations):
        kind = operation.get("op")
        before = copy.deepcopy(mesh)
        before_digest = _digest(before)
        if kind == "CUT_EDGE":
            effect = _cut_edge(mesh, operation)
        elif kind == "REMESH_TRIANGLE":
            effect = _remesh_triangle(mesh, operation)
        else:
            raise _Invalid(f"unsupported topology operation {kind!r}")
        event = {"id": f"topology-event-{index:06d}", "kind": kind,
                 "effect": effect, "before_digest": before_digest,
                 "after_digest": _digest(mesh),
                 "inverse": {"op": "RESTORE_MESH", "mesh": before},
                 "active": True}
        events.append(event)
    if undo_count > len(events):
        raise _Invalid("undo_topology_events exceeds the topology event count")
    for event in reversed(events[-undo_count:] if undo_count else []):
        mesh = copy.deepcopy(event["inverse"]["mesh"])
        event["active"] = False
        events.append({"id": f"undo-{event['id']}", "kind": "UNDO_TOPOLOGY",
                       "target_event": event["id"], "restored_digest": _digest(mesh),
                       "active": True})
    _validate_manifold(mesh)
    return mesh, events


def _torsion(request: Mapping[str, Any], segment_lengths: Sequence[float],
             time_step: float, iterations: int) -> Tuple[List[float], Dict[str, float]]:
    yarn = request["yarn"]
    count = len(segment_lengths)
    initial_raw = yarn.get("initial_twist_angles_rad", [0.0]*count)
    rest_raw = yarn.get("rest_twist_angles_rad", [0.0]*count)
    if (not isinstance(initial_raw, (list, tuple)) or len(initial_raw) != count
            or not isinstance(rest_raw, (list, tuple)) or len(rest_raw) != count):
        raise _Invalid("twist angle arrays require one value per yarn segment")
    angles = [_number(x, f"initial_twist_angles_rad[{i}]")
              for i, x in enumerate(initial_raw)]
    rest = [_number(x, f"rest_twist_angles_rad[{i}]")
            for i, x in enumerate(rest_raw)]
    stiffness = _number(yarn.get("torsional_stiffness_n_m2"),
                        "torsional_stiffness_n_m2", low=0.0, strict=True)
    regularizer = _number(yarn.get("twist_regularization", 0.25),
                          "twist_regularization", low=0.0)
    if regularizer > 1.0:
        raise _Invalid("twist_regularization must be <= 1")
    alpha = stiffness*time_step*time_step/(1.0 + stiffness*time_step*time_step)
    for _ in range(iterations):
        old = tuple(angles)
        updated = []
        for i, value in enumerate(old):
            target = rest[i]
            neighbour_targets = []
            if i > 0:
                neighbour_targets.append(old[i-1] + rest[i]-rest[i-1])
            if i+1 < count:
                neighbour_targets.append(old[i+1] + rest[i]-rest[i+1])
            smooth = sum(neighbour_targets)/len(neighbour_targets) if neighbour_targets else target
            desired = (1.0-regularizer)*target + regularizer*smooth
            updated.append(value + alpha*(desired-value))
        angles = updated
    strains = [(angles[i]-rest[i])/segment_lengths[i] for i in range(count)]
    initial_strains = [(_number(initial_raw[i], f"initial_twist_angles_rad[{i}]")-rest[i])
                       / segment_lengths[i] for i in range(count)]
    energy = sum(0.5*stiffness*strain*strain*length
                 for strain, length in zip(strains, segment_lengths))
    return angles, {"maximum_torsion_rad_m": max((abs(x) for x in strains), default=0.0),
                    "initial_maximum_torsion_rad_m":
                    max((abs(x) for x in initial_strains), default=0.0),
                    "torsional_energy_j": energy,
                    "twist_projection": "JACOBI_REFERENCE"}


def _friction(request: Mapping[str, Any], base: Mapping[str, Any],
              mesh: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = request.get("friction", {})
    if not isinstance(raw, Mapping):
        raise _Invalid("friction must be an object")
    coefficient = _number(raw.get("coefficient", 0.3), "friction.coefficient", low=0.0)
    epsilon = _number(raw.get("regularization_speed_m_s", 1.0e-3),
                      "friction.regularization_speed_m_s", low=0.0, strict=True)
    stiffness = _number(raw.get("normal_stiffness_n_m", 100.0),
                        "friction.normal_stiffness_n_m", low=0.0, strict=True)
    velocity = _vec(raw.get("relative_velocity_m_s", [0.0, 0.0, 0.0]),
                    "friction.relative_velocity_m_s")
    radius = _number(request["yarn"].get("radius_m"), "yarn.radius_m", low=0.0, strict=True)
    thickness = _number(request["cloth"].get("thickness_m", 0.0),
                        "cloth.thickness_m", low=0.0)
    threshold = radius + thickness
    results = []
    for contact in base.get("contacts", []):
        face = mesh["faces"][contact["face"]]
        a, b, c = (tuple(mesh["vertices_m"][i]) for i in face)
        normal_raw = _cross(_sub(b, a), _sub(c, a))
        normal_length = _length(normal_raw)
        if normal_length <= _EPS:
            raise _MeshInvalid("contact references a degenerate face")
        normal = _mul(normal_raw, 1.0/normal_length)
        tangent = _sub(velocity, _mul(normal, _dot(velocity, normal)))
        speed = _length(tangent)
        normal_force = stiffness*max(0.0, threshold-contact["distance_m"])
        scale = (-coefficient*normal_force/math.sqrt(speed*speed + epsilon*epsilon)
                 if speed > 0.0 else 0.0)
        force = _mul(tangent, scale)
        results.append({"segment": contact["segment"], "face": contact["face"],
                        "normal_force_n": normal_force,
                        "friction_force_n": list(force),
                        "friction_magnitude_n": _length(force),
                        "coulomb_bound_n": coefficient*normal_force,
                        "regularization_speed_m_s": epsilon})
    return results, {"model": "SMOOTH_COULOMB_CANDIDATE",
                     "coupled_impulse_solve": False,
                     "candidate_count": len(results)}


def simulate(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply reversible cloth edits, then evaluate yarn, torsion and friction."""
    try:
        if not isinstance(request, Mapping):
            raise _Invalid("request must be an object")
        cloth = request.get("cloth")
        yarn = request.get("yarn")
        if not isinstance(cloth, Mapping) or not isinstance(yarn, Mapping):
            raise _Invalid("request requires cloth and yarn objects")
        initial_mesh = _mesh(cloth.get("vertices_m"), cloth.get("faces"))
        undo_count = _integer(request.get("undo_topology_events", 0),
                              "undo_topology_events")
        mesh, topology_log = _topology_events(
            initial_mesh, request.get("topology_operations", []), undo_count)

        composed = copy.deepcopy(dict(request))
        composed_cloth = copy.deepcopy(dict(cloth))
        composed_cloth["vertices_m"] = mesh["vertices_m"]
        composed_cloth["faces"] = mesh["faces"]
        composed["cloth"] = composed_cloth
        base = yarn_needle.simulate(composed)
        if base.get("verdict") != ANSWER:
            return base

        rest = [_vec(x, f"yarn.rest_positions_m[{i}]")
                for i, x in enumerate(yarn.get("rest_positions_m", []))]
        segment_lengths = [_length(_sub(rest[i+1], rest[i]))
                           for i in range(len(rest)-1)]
        time_step = _number(request.get("time_step_s", 1.0/120.0),
                            "time_step_s", low=0.0, strict=True)
        iterations = _integer(request.get("torsion_iterations", 20),
                              "torsion_iterations", low=1)
        twist, torsion = _torsion(request, segment_lengths, time_step, iterations)
        friction, friction_diagnostics = _friction(request, base, mesh)

        return {
            "verdict": ANSWER,
            "terminal_verdict": "REFERENCE_STEP_COMPLETE",
            "state": {**base["state"], "cloth_mesh": mesh,
                      "yarn_twist_angles_rad": twist},
            "contacts": base["contacts"],
            "friction_candidates": friction,
            "event_log": {"cloth_topology": topology_log,
                          "yarn_needle": base["event_log"]},
            "diagnostics": {"yarn_needle": base["diagnostics"],
                            "torsion": torsion,
                            "friction": friction_diagnostics,
                            "cloth_topology_digest": _digest(mesh),
                            "topology_events_undone": undo_count},
            "claims": {"reference_level": True,
                       "industrial_sewing_machine": False,
                       "production_remeshing": False},
        }
    except _Unsupported as exc:
        return _refusal(UNSUPPORTED_CHANGE, str(exc))
    except _MeshInvalid as exc:
        return _refusal(INVALID_TOPOLOGY, str(exc))
    except (_Invalid, TypeError, ValueError) as exc:
        return _refusal(INVALID_INPUT, str(exc))
