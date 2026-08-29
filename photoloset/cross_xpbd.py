# -*- coding: utf-8 -*-
"""Deterministic cross-structured XPBD cloth solver.

The cross is a mesoscopic data/compute structure, not a molecular claim.  The
solver keeps membrane, shear, bending and seam meanings in separate typed
constraint layers.  During one projection iteration every constraint reads
the same immutable old position array; corrections are reduced and applied
once (Jacobi), so constraint scan order cannot manufacture state.

Inputs and outputs use SI units.  This CPU reference backend deliberately does
not claim GPU, continuous collision, or production-shell-FEM capability.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_XPBD_INVALID_INPUT"
TIMESTEP_TOO_LARGE = "UNKNOWN_XPBD_TIMESTEP_TOO_LARGE"
INFEASIBLE = "UNKNOWN_XPBD_INFEASIBLE_CONSTRAINTS"
_EPS = 1.0e-12


class _Invalid(ValueError):
    pass


def backend_capabilities() -> Dict[str, Any]:
    """Return an honest, deterministic capability declaration."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python",
        "cpu": {"available": True, "parallel": False},
        "gpu": {
            "available": False,
            "backend": None,
            "reason": "no GPU XPBD kernel is implemented in this module",
        },
        "features": {
            "xpbd": True,
            "same_old_state_jacobi": True,
            "orthotropic_membrane": True,
            "dihedral_bending": True,
            "compliant_seams": True,
            "adaptive_substeps": True,
            "continuous_collision": False,
            "shell_fem": False,
        },
    }


def capabilities() -> Dict[str, Any]:
    """MCP-facing capability report; no runtime capability is inferred."""
    return backend_capabilities()


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
    if (not isinstance(value, (list, tuple)) or len(value) != 3):
        raise _Invalid(f"{name} must contain three finite SI components")
    return tuple(_number(component, f"{name}[{axis}]")
                 for axis, component in enumerate(value))  # type: ignore[return-value]


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


def _unit(a: Vec3) -> Vec3:
    length = _length(a)
    if length <= _EPS:
        raise _Invalid("a zero-length geometric direction is undefined")
    return _mul(a, 1.0 / length)


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _wrap_angle(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True)
class _Material:
    density: float
    compliance: Tuple[float, float, float, float]
    stiffness: Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]
    damping: float


@dataclass(frozen=True)
class _Constraint:
    kind: str
    nodes: Tuple[int, ...]
    data: Tuple[Any, ...]
    compliance: float
    stiffness: Optional[float]
    key: Tuple[Any, ...]


def _coefficient(raw: Mapping[str, Any], kind: str,
                 compliance_key: str, stiffness_key: str) -> Tuple[float, Optional[float]]:
    has_c, has_k = compliance_key in raw, stiffness_key in raw
    if has_c and has_k:
        raise _Invalid(f"material supplies both {compliance_key} and {stiffness_key}")
    if not has_c and not has_k:
        raise _Invalid(f"material lacks {compliance_key} or {stiffness_key}")
    if has_c:
        compliance = _number(raw[compliance_key], compliance_key, low=0.0)
        return compliance, (None if compliance == 0.0 else 1.0 / compliance)
    stiffness = _number(raw[stiffness_key], stiffness_key, low=0.0, strict=True)
    return 1.0 / stiffness, stiffness


def _material(raw: Mapping[str, Any], name: str) -> _Material:
    if not isinstance(raw, Mapping):
        raise _Invalid(f"materials.{name} must be a mapping")
    pairs = (
        _coefficient(raw, "warp", "warp_compliance_m_n", "warp_stiffness_n_m"),
        _coefficient(raw, "weft", "weft_compliance_m_n", "weft_stiffness_n_m"),
        _coefficient(raw, "shear", "shear_compliance_m_n", "shear_stiffness_n_m"),
        _coefficient(raw, "bending", "bending_compliance_rad_n_m",
                     "bending_stiffness_n_m"),
    )
    density = _number(raw.get("areal_density_kg_m2"),
                      f"materials.{name}.areal_density_kg_m2", low=0.0, strict=True)
    damping = _number(raw.get("damping_ratio", 0.0),
                      f"materials.{name}.damping_ratio", low=0.0)
    if damping > 1.0:
        raise _Invalid(f"materials.{name}.damping_ratio must be <= 1")
    return _Material(density, tuple(pair[0] for pair in pairs),
                     tuple(pair[1] for pair in pairs), damping)


def _triangle_area(points: Sequence[Vec3], face: Tuple[int, int, int]) -> float:
    return 0.5 * _length(_cross(_sub(points[face[1]], points[face[0]]),
                                _sub(points[face[2]], points[face[0]])))


def _shape_gradients(points: Sequence[Vec3], face: Tuple[int, int, int],
                     supplied_warp: Optional[Vec3]) -> Tuple[Tuple[float, float], ...]:
    p0, p1, p2 = (points[index] for index in face)
    normal = _unit(_cross(_sub(p1, p0), _sub(p2, p0)))
    if supplied_warp is None:
        warp = _unit(_sub(p1, p0))
    else:
        tangent = _sub(supplied_warp, _mul(normal, _dot(supplied_warp, normal)))
        warp = _unit(tangent)
    weft = _unit(_cross(normal, warp))
    d1, d2 = _sub(p1, p0), _sub(p2, p0)
    u1, v1 = _dot(d1, warp), _dot(d1, weft)
    u2, v2 = _dot(d2, warp), _dot(d2, weft)
    determinant = u1*v2 - v1*u2
    if abs(determinant) <= _EPS:
        raise _Invalid("triangle rest coordinates are degenerate")
    g1 = (v2 / determinant, -u2 / determinant)
    g2 = (-v1 / determinant, u1 / determinant)
    return ((-g1[0] - g2[0], -g1[1] - g2[1]), g1, g2)


def _dihedral(points: Sequence[Vec3], nodes: Tuple[int, int, int, int]) -> float:
    a, b, c, d = (points[index] for index in nodes)
    edge = _unit(_sub(b, a))
    n1 = _unit(_cross(_sub(b, a), _sub(c, a)))
    n2 = _unit(_cross(_sub(d, a), _sub(b, a)))
    return math.atan2(_dot(_cross(n1, n2), edge),
                      max(-1.0, min(1.0, _dot(n1, n2))))


def _build(rest: Tuple[Vec3, ...], faces_raw: Sequence[Sequence[int]],
           material_ids: Sequence[str], materials: Mapping[str, _Material],
           warp_directions: Optional[Sequence[Sequence[float]]],
           seams_raw: Sequence[Mapping[str, Any]]) -> Tuple[
               Tuple[Tuple[int, int, int], ...], Tuple[float, ...], Tuple[_Constraint, ...], float]:
    if len(faces_raw) != len(material_ids):
        raise _Invalid("one material id is required per face")
    if warp_directions is not None and len(warp_directions) != len(faces_raw):
        raise _Invalid("one face warp direction is required per face")
    records = []
    masses = [0.0] * len(rest)
    edges: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    min_edge = math.inf
    for face_index, (raw_face, material_id) in enumerate(zip(faces_raw, material_ids)):
        if (not isinstance(raw_face, (list, tuple)) or len(raw_face) != 3
                or any(isinstance(i, bool) or not isinstance(i, int)
                       or not 0 <= i < len(rest) for i in raw_face)
                or len(set(raw_face)) != 3):
            raise _Invalid(f"faces[{face_index}] must contain three distinct valid indices")
        if material_id not in materials:
            raise _Invalid(f"face material {material_id!r} is not defined")
        face = tuple(int(i) for i in raw_face)
        area = _triangle_area(rest, face)
        if area <= _EPS:
            raise _Invalid(f"faces[{face_index}] has zero rest area")
        warp = None if warp_directions is None else _vec(
            warp_directions[face_index], f"face_warp_directions[{face_index}]")
        gradients = _shape_gradients(rest, face, warp)
        material = materials[material_id]
        share = area * material.density / 3.0
        for node in face:
            masses[node] += share
        for a, b, opposite in ((face[0], face[1], face[2]),
                               (face[1], face[2], face[0]),
                               (face[2], face[0], face[1])):
            edge = tuple(sorted((a, b)))
            edges.setdefault(edge, []).append((face_index, opposite))
            min_edge = min(min_edge, _distance(rest[a], rest[b]))
        records.append((face, str(material_id), gradients, material, area))
    if not records or any(mass <= 0.0 for mass in masses):
        raise _Invalid("mesh must contain faces and no isolated vertices")
    constraints: List[_Constraint] = []
    for face, material_id, gradients, material, _area in records:
        canonical = tuple(sorted(face))
        for offset, kind in enumerate(("warp", "weft", "shear")):
            constraints.append(_Constraint(
                kind, face, (gradients,), material.compliance[offset],
                material.stiffness[offset], (kind, canonical, material_id)))
    for edge, uses in sorted(edges.items()):
        if len(uses) > 2:
            raise _Invalid(f"non-manifold edge {edge} belongs to {len(uses)} faces")
        if len(uses) != 2:
            continue
        left, right = uses
        ml = records[left[0]][3]
        mr = records[right[0]][3]
        nodes = (edge[0], edge[1], left[1], right[1])
        rest_angle = _dihedral(rest, nodes)
        compliance = 0.5 * (ml.compliance[3] + mr.compliance[3])
        stiffness_values = (ml.stiffness[3], mr.stiffness[3])
        stiffness = (None if any(value is None for value in stiffness_values)
                     else 2.0 / sum(1.0 / float(value) for value in stiffness_values))
        constraints.append(_Constraint(
            "bending", nodes, (rest_angle,), compliance, stiffness,
            ("bending", edge, min(left[1], right[1]), max(left[1], right[1]))))
    for index, seam in enumerate(seams_raw):
        if not isinstance(seam, Mapping):
            raise _Invalid(f"seams[{index}] must be a mapping")
        a, b = seam.get("a"), seam.get("b")
        if (isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int)
                or not isinstance(b, int) or not 0 <= a < len(rest)
                or not 0 <= b < len(rest) or a == b):
            raise _Invalid(f"seams[{index}] has invalid endpoints")
        rest_gap = _number(seam.get("rest_gap_m", seam.get("rest_gap", 0.0)),
                           f"seams[{index}].rest_gap_m", low=0.0)
        compliance = _number(seam.get("compliance_m_n", seam.get("compliance", 0.0)),
                             f"seams[{index}].compliance_m_n", low=0.0)
        stiffness = None if compliance == 0.0 else 1.0 / compliance
        constraints.append(_Constraint(
            "seam", (a, b), (rest_gap,), compliance, stiffness,
            ("seam", min(a, b), max(a, b), index)))
    constraints.sort(key=lambda value: value.key)
    return tuple(record[0] for record in records), tuple(masses), tuple(constraints), min_edge


def _membrane(constraint: _Constraint, positions: Sequence[Vec3]
              ) -> Tuple[float, Dict[int, Vec3]]:
    gradients = constraint.data[0]
    fu = (0.0, 0.0, 0.0)
    fv = (0.0, 0.0, 0.0)
    for node, (gu, gv) in zip(constraint.nodes, gradients):
        fu = _add(fu, _mul(positions[node], gu))
        fv = _add(fv, _mul(positions[node], gv))
    if constraint.kind == "warp":
        return (0.5 * (_dot(fu, fu) - 1.0),
                {node: _mul(fu, gradients[i][0])
                 for i, node in enumerate(constraint.nodes)})
    if constraint.kind == "weft":
        return (0.5 * (_dot(fv, fv) - 1.0),
                {node: _mul(fv, gradients[i][1])
                 for i, node in enumerate(constraint.nodes)})
    return (_dot(fu, fv),
            {node: _add(_mul(fv, gradients[i][0]), _mul(fu, gradients[i][1]))
             for i, node in enumerate(constraint.nodes)})


def _bending(constraint: _Constraint, positions: Sequence[Vec3]
             ) -> Tuple[float, Dict[int, Vec3]]:
    current = _dihedral(positions, constraint.nodes)
    value = _wrap_angle(current - float(constraint.data[0]))
    scale = max((_distance(positions[constraint.nodes[0]],
                           positions[constraint.nodes[1]])), 1.0e-6)
    epsilon = max(1.0e-8, scale * 1.0e-6)
    gradients: Dict[int, Vec3] = {}
    for node in constraint.nodes:
        components = []
        for axis in range(3):
            plus, minus = list(positions), list(positions)
            vp, vm = list(plus[node]), list(minus[node])
            vp[axis] += epsilon
            vm[axis] -= epsilon
            plus[node], minus[node] = tuple(vp), tuple(vm)
            difference = _wrap_angle(_dihedral(plus, constraint.nodes)
                                     - _dihedral(minus, constraint.nodes))
            components.append(difference / (2.0 * epsilon))
        gradients[node] = tuple(components)  # type: ignore[assignment]
    return value, gradients


def _seam(constraint: _Constraint, positions: Sequence[Vec3]
          ) -> Tuple[float, Dict[int, Vec3]]:
    a, b = constraint.nodes
    delta = _sub(positions[b], positions[a])
    length = _length(delta)
    if length <= _EPS:
        axis = (a * 73856093 + b * 19349663) % 3
        direction = tuple(1.0 if i == axis else 0.0 for i in range(3))
    else:
        direction = _mul(delta, 1.0 / length)
    return length - float(constraint.data[0]), {a: _mul(direction, -1.0), b: direction}


def _evaluate(constraint: _Constraint, positions: Sequence[Vec3]
              ) -> Tuple[float, Dict[int, Vec3]]:
    if constraint.kind in ("warp", "weft", "shear"):
        return _membrane(constraint, positions)
    if constraint.kind == "bending":
        return _bending(constraint, positions)
    return _seam(constraint, positions)


def _project_jacobi(positions: Sequence[Vec3], inverse_masses: Sequence[float],
                    constraints: Sequence[_Constraint], lambdas: List[float],
                    substep_s: float, relaxation: float
                    ) -> Tuple[List[Vec3], float, bool]:
    old = tuple(positions)
    deltas = [(0.0, 0.0, 0.0) for _ in old]
    counts = [0] * len(old)
    max_violation, infeasible = 0.0, False
    for index, constraint in enumerate(constraints):
        value, gradients = _evaluate(constraint, old)
        max_violation = max(max_violation, abs(value))
        alpha = constraint.compliance / (substep_s * substep_s)
        denominator = alpha + math.fsum(
            inverse_masses[node] * _dot(gradient, gradient)
            for node, gradient in gradients.items())
        if denominator <= _EPS:
            infeasible = infeasible or abs(value) > 1.0e-9
            continue
        delta_lambda = (-value - alpha * lambdas[index]) / denominator
        lambdas[index] += delta_lambda
        for node, gradient in gradients.items():
            if inverse_masses[node] <= 0.0:
                continue
            correction = _mul(gradient, inverse_masses[node] * delta_lambda)
            deltas[node] = _add(deltas[node], correction)
            counts[node] += 1
    output = []
    for index, point in enumerate(old):
        scale = relaxation / max(1, counts[index])
        output.append(_add(point, _mul(deltas[index], scale)))
    return output, max_violation, infeasible


def _diagnostics(positions: Sequence[Vec3], velocities: Sequence[Vec3],
                 masses: Sequence[float], constraints: Sequence[_Constraint],
                 gravity: Vec3, iterations: int, substeps: int,
                 max_update: float) -> Dict[str, Any]:
    by_kind: Dict[str, List[float]] = {kind: [] for kind in
                                       ("warp", "weft", "shear", "bending", "seam")}
    energy = {kind: 0.0 for kind in by_kind}
    excluded_hard = 0
    for constraint in constraints:
        value, _ = _evaluate(constraint, positions)
        by_kind[constraint.kind].append(abs(value))
        if constraint.stiffness is None:
            excluded_hard += 1
        else:
            energy[constraint.kind] += 0.5 * constraint.stiffness * value * value
    kinetic = math.fsum(0.5 * mass * _dot(velocity, velocity)
                        for mass, velocity in zip(masses, velocities))
    gravitational = math.fsum(-mass * _dot(gravity, point)
                              for mass, point in zip(masses, positions))
    max_speed = max((_length(value) for value in velocities), default=0.0)
    return {
        "projection": "XPBD_JACOBI_SAME_OLD_STATE",
        "iterations_per_substep": iterations,
        "substeps": substeps,
        "max_position_update_m": max_update,
        "max_speed_m_s": max_speed,
        "strain": {
            kind: {"maximum": max(values, default=0.0),
                   "rms": math.sqrt(math.fsum(v*v for v in values) / len(values))
                   if values else 0.0}
            for kind, values in by_kind.items()
        },
        "energy_j": {
            "kinetic": kinetic, "gravitational": gravitational,
            "constraint_by_kind": energy,
            "total_reported": kinetic + gravitational + math.fsum(energy.values()),
            "hard_constraints_excluded": excluded_hard,
            "model": "quadratic finite-stiffness constraints; hard constraints excluded",
        },
    }


def simulate_xpbd(
        vertices: Sequence[Sequence[float]], faces: Sequence[Sequence[int]], *,
        face_material_ids: Sequence[str], materials: Mapping[str, Mapping[str, Any]],
        face_warp_directions: Optional[Sequence[Sequence[float]]] = None,
        initial_positions: Optional[Sequence[Sequence[float]]] = None,
        initial_velocities: Optional[Sequence[Sequence[float]]] = None,
        fixed_vertices: Sequence[int] = (), seams: Sequence[Mapping[str, Any]] = (),
        gravity_m_s2: Sequence[float] = (0.0, -9.80665, 0.0),
        time_step_s: float = 1.0 / 60.0, steps: int = 1,
        solver_iterations: int = 16, jacobi_relaxation: float = 0.9,
        max_displacement_fraction: float = 0.2, max_substeps: int = 256,
        convergence_tolerance: float = 1.0e-5,
        speed_tolerance_m_s: float = 1.0e-3,
        stable_steps_required: int = 3) -> Dict[str, Any]:
    """Advance an orthotropic cloth using deterministic CPU XPBD.

    ``vertices`` are the immutable rest positions.  ``initial_positions`` may
    supply a deformed starting state.  A successful finite trajectory is an
    ``ANSWER`` even when its separate ``terminal_verdict`` is ``IN_PROGRESS``.
    """
    original_snapshot = copy.deepcopy({
        "vertices": vertices, "faces": faces, "face_material_ids": face_material_ids,
        "materials": materials, "face_warp_directions": face_warp_directions,
        "initial_positions": initial_positions, "initial_velocities": initial_velocities,
        "fixed_vertices": fixed_vertices, "seams": seams,
    })
    try:
        rest = tuple(_vec(value, f"vertices[{index}]")
                     for index, value in enumerate(vertices))
        if not rest:
            raise _Invalid("vertices must be non-empty")
        positions = list(rest if initial_positions is None else tuple(
            _vec(value, f"initial_positions[{index}]")
            for index, value in enumerate(initial_positions)))
        velocities = [(0.0, 0.0, 0.0) for _ in rest] if initial_velocities is None else [
            _vec(value, f"initial_velocities[{index}]")
            for index, value in enumerate(initial_velocities)]
        if len(positions) != len(rest) or len(velocities) != len(rest):
            raise _Invalid("initial state must have one position and velocity per vertex")
        if not isinstance(materials, Mapping) or not materials:
            raise _Invalid("materials must be a non-empty mapping")
        parsed_materials = {str(name): _material(value, str(name))
                            for name, value in materials.items()}
        triangles, masses, constraints, min_edge = _build(
            rest, faces, tuple(str(value) for value in face_material_ids),
            parsed_materials, face_warp_directions, seams)
        fixed = set()
        for value in fixed_vertices:
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 0 <= value < len(rest)):
                raise _Invalid("fixed_vertices contains an invalid index")
            fixed.add(value)
        inverse_masses = [0.0 if index in fixed else 1.0 / masses[index]
                          for index in range(len(rest))]
        gravity = _vec(gravity_m_s2, "gravity_m_s2")
        dt = _number(time_step_s, "time_step_s", low=0.0, strict=True)
        relaxation = _number(jacobi_relaxation, "jacobi_relaxation", low=0.0,
                             strict=True)
        fraction = _number(max_displacement_fraction, "max_displacement_fraction",
                           low=0.0, strict=True)
        tolerance = _number(convergence_tolerance, "convergence_tolerance", low=0.0)
        speed_tolerance = _number(speed_tolerance_m_s, "speed_tolerance_m_s", low=0.0)
        for value, name in ((steps, "steps"), (solver_iterations, "solver_iterations"),
                            (max_substeps, "max_substeps"),
                            (stable_steps_required, "stable_steps_required")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise _Invalid(f"{name} must be a positive integer")
        if relaxation > 1.0:
            raise _Invalid("jacobi_relaxation must be <= 1")
        max_speed = max((_length(value) for value in velocities), default=0.0)
        predicted = max_speed * dt + 0.5 * _length(gravity) * dt * dt
        substeps = max(1, int(math.ceil(predicted / (fraction * min_edge))))
        if substeps > max_substeps:
            return _unknown(
                TIMESTEP_TOO_LARGE,
                f"adaptive accuracy requires {substeps} substeps; limit is {max_substeps}",
                required_substeps=substeps, backend=backend_capabilities(),
                immutable_input_snapshot=original_snapshot)
        h = dt / substeps
        damping = math.fsum(material.damping for material in parsed_materials.values()) \
            / len(parsed_materials)
        history, stable_count, max_update = [], 0, 0.0
        for step_index in range(steps):
            step_max_violation = 0.0
            for _substep in range(substeps):
                previous = tuple(positions)
                predicted_positions = []
                for index, (point, velocity) in enumerate(zip(positions, velocities)):
                    if index in fixed:
                        predicted_positions.append(rest[index])
                    else:
                        predicted_positions.append(_add(point, _add(
                            _mul(velocity, h), _mul(gravity, h*h))))
                lambdas = [0.0] * len(constraints)
                infeasible = False
                for _iteration in range(solver_iterations):
                    prior_projection = predicted_positions
                    predicted_positions, violation, blocked = _project_jacobi(
                        predicted_positions, inverse_masses, constraints, lambdas,
                        h, relaxation)
                    step_max_violation = max(step_max_violation, violation)
                    infeasible = infeasible or blocked
                    max_update = max(max_update, max(
                        (_distance(a, b) for a, b in
                         zip(predicted_positions, prior_projection)), default=0.0))
                if infeasible:
                    return _unknown(
                        INFEASIBLE, "a violated hard constraint has no movable endpoint",
                        backend=backend_capabilities(), immutable_input_snapshot=original_snapshot)
                positions = predicted_positions
                velocities = [
                    ((0.0, 0.0, 0.0) if index in fixed else
                     _mul(_sub(point, previous[index]), (1.0 - damping) / h))
                    for index, point in enumerate(positions)]
            diagnostics = _diagnostics(positions, velocities, masses, constraints,
                                       gravity, solver_iterations, substeps, max_update)
            maximum = max(value["maximum"]
                          for value in diagnostics["strain"].values())
            converged_now = (maximum <= tolerance
                             and diagnostics["max_speed_m_s"] <= speed_tolerance)
            stable_count = stable_count + 1 if converged_now else 0
            history.append({
                "step": step_index + 1, "substeps": substeps,
                "max_constraint_violation": maximum,
                "max_speed_m_s": diagnostics["max_speed_m_s"],
                "total_reported_energy_j": diagnostics["energy_j"]["total_reported"],
            })
            if stable_count >= stable_steps_required:
                break
        diagnostics = _diagnostics(positions, velocities, masses, constraints,
                                   gravity, solver_iterations, substeps, max_update)
        diagnostics["convergence"] = {
            "terminal_verdict": ("CONVERGED" if stable_count >= stable_steps_required
                                  else "IN_PROGRESS"),
            "stable_steps": stable_count, "stable_steps_required": stable_steps_required,
            "constraint_tolerance": tolerance,
            "speed_tolerance_m_s": speed_tolerance,
        }
        return {
            "verdict": ANSWER,
            "terminal_verdict": diagnostics["convergence"]["terminal_verdict"],
            "state": {
                "vertices": [{"position_m": list(point),
                              "velocity_m_s": list(velocity),
                              "mass_kg": masses[index], "fixed": index in fixed}
                             for index, (point, velocity) in
                             enumerate(zip(positions, velocities))],
                "triangles": [list(face) for face in triangles],
            },
            "history": history,
            "diagnostics": diagnostics,
            "backend": backend_capabilities(),
            "cross_contract": {
                "representation": "mesoscopic six-arm typed constraint stack",
                "projection": "same-old-state Jacobi",
                "typed_layers": ["warp", "weft", "shear", "bending", "seam"],
                "not_atoms_or_molecules": True,
            },
        }
    except (KeyError, TypeError, ValueError, IndexError, _Invalid) as error:
        return _unknown(INVALID_INPUT, str(error), backend=backend_capabilities(),
                        immutable_input_snapshot=original_snapshot)


simulate = simulate_xpbd

__all__ = [
    "ANSWER", "INFEASIBLE", "INVALID_INPUT", "TIMESTEP_TOO_LARGE",
    "backend_capabilities", "capabilities", "simulate", "simulate_xpbd",
]
