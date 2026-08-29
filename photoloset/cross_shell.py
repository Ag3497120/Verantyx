# -*- coding: utf-8 -*-
"""Deterministic CPU reference for a cross-structured thin-shell law.

This module assembles forces and a diagonal Jacobi correction from one
immutable old state.  It is a constitutive/assembly reference, not a complete
FEM solver: it has no time integrator, global Newton solve, contact, remeshing,
or production calibration pipeline.

SI units are required.  Membrane forces use an orthotropic StVK law on linear
triangles.  Interior edges use a discrete dihedral hinge.  Plastic strain and
hysteresis memory are explicit, caller-owned element state; proposed updates
are returned separately and never mutate the supplied state.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
Face = Tuple[int, int, int]

ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_CROSS_SHELL_INVALID_INPUT"
UNCALIBRATED = "UNKNOWN_CROSS_SHELL_UNCALIBRATED_MATERIAL"
INVERTED = "UNKNOWN_CROSS_SHELL_INVERTED_ELEMENT"
ILL_CONDITIONED = "UNKNOWN_CROSS_SHELL_ILL_CONDITIONED"
_EPS = 1.0e-12

__all__ = ("capabilities", "solve")


class _Refusal(ValueError):
    code = INVALID_INPUT


class _Uncalibrated(_Refusal):
    code = UNCALIBRATED


class _Inverted(_Refusal):
    code = INVERTED


class _IllConditioned(_Refusal):
    code = ILL_CONDITIONED


def capabilities() -> Dict[str, Any]:
    """Declare implemented and deliberately absent capabilities."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python_standard_library",
        "model": "orthotropic_stvk_triangle_plus_discrete_dihedral_hinge",
        "features": {
            "same_old_state_residual": True,
            "jacobi_diagonal_correction": True,
            "orthotropic_membrane": True,
            "thickness": True,
            "discrete_bending": True,
            "plastic_internal_state": True,
            "hysteresis_internal_state": True,
            "typed_inversion_refusal": True,
            "typed_conditioning_refusal": True,
            "typed_uncalibrated_refusal": True,
            "global_fem_solve": False,
            "consistent_tangent_matrix": False,
            "contact_or_ccd": False,
            "seam_process_model": False,
            "fluid_structure_coupling": False,
            "validated_industrial_accuracy": False,
            "gpu": False,
        },
        "limitations": [
            "Jacobi diagonal is a positive local approximation, not a consistent Hessian",
            "bending derivatives are deterministic finite-difference reference derivatives",
            "public solve tests inversion against rest reference directors",
            "material calibration status is asserted by the caller and not measured here",
        ],
    }


def _unknown(error: _Refusal) -> Dict[str, Any]:
    return {"verdict": error.code, "reasons": [str(error)]}


def _number(value: Any, name: str, *, low: Optional[float] = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Refusal(f"{name} must be a finite SI number")
    result = float(value)
    if not math.isfinite(result):
        raise _Refusal(f"{name} must be finite")
    if low is not None and (result <= low if strict else result < low):
        relation = ">" if strict else ">="
        raise _Refusal(f"{name} must be {relation} {low}")
    return result


def _vec3(value: Any, name: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Refusal(f"{name} must contain three finite SI components")
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
    return (a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec3, name: str) -> Vec3:
    size = _length(a)
    if size <= _EPS:
        raise _IllConditioned(f"{name} has zero length")
    return _mul(a, 1.0 / size)


def _wrap_angle(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True)
class _Plastic:
    yield_strain: float
    hardening_pa: float
    max_strain: float
    hysteresis: float
    bending_yield_rad: float
    max_bending_rad: float


@dataclass(frozen=True)
class _Material:
    thickness: float
    e_warp: float
    e_weft: float
    shear: float
    poisson: float
    bending: float
    plastic: _Plastic
    calibration_id: str


def _material(raw: Any, name: str) -> _Material:
    if not isinstance(raw, Mapping):
        raise _Refusal(f"materials.{name} must be a mapping")
    calibration = raw.get("calibration")
    if not isinstance(calibration, Mapping):
        raise _Uncalibrated(f"materials.{name}.calibration is required")
    if calibration.get("status") != "CALIBRATED":
        raise _Uncalibrated(f"materials.{name} is not CALIBRATED")
    calibration_id = calibration.get("id")
    if not isinstance(calibration_id, str) or not calibration_id.strip():
        raise _Uncalibrated(f"materials.{name}.calibration.id is required")
    thickness = _number(raw.get("thickness_m"), f"materials.{name}.thickness_m",
                        low=0.0, strict=True)
    e_warp = _number(raw.get("young_warp_pa"), f"materials.{name}.young_warp_pa",
                     low=0.0, strict=True)
    e_weft = _number(raw.get("young_weft_pa"), f"materials.{name}.young_weft_pa",
                     low=0.0, strict=True)
    shear = _number(raw.get("shear_pa"), f"materials.{name}.shear_pa",
                    low=0.0, strict=True)
    poisson = _number(raw.get("poisson_warp_weft"),
                      f"materials.{name}.poisson_warp_weft", low=0.0)
    if poisson >= 0.5 or 1.0 - poisson*poisson <= _EPS:
        raise _Refusal(f"materials.{name}.poisson_warp_weft must be < 0.5")
    equivalent_e = math.sqrt(e_warp * e_weft)
    bending = _number(
        raw.get("bending_stiffness_n_m",
                equivalent_e * thickness**3 / (12.0 * (1.0 - poisson**2))),
        f"materials.{name}.bending_stiffness_n_m", low=0.0, strict=True)
    plastic_raw = raw.get("plasticity")
    if not isinstance(plastic_raw, Mapping):
        raise _Uncalibrated(f"materials.{name}.plasticity calibration is required")
    plastic = _Plastic(
        _number(plastic_raw.get("yield_strain"), "plasticity.yield_strain",
                low=0.0, strict=True),
        _number(plastic_raw.get("hardening_pa"), "plasticity.hardening_pa", low=0.0),
        _number(plastic_raw.get("max_plastic_strain"),
                "plasticity.max_plastic_strain", low=0.0, strict=True),
        _number(plastic_raw.get("hysteresis_ratio"),
                "plasticity.hysteresis_ratio", low=0.0),
        _number(plastic_raw.get("bending_yield_rad"),
                "plasticity.bending_yield_rad", low=0.0, strict=True),
        _number(plastic_raw.get("max_plastic_bending_rad"),
                "plasticity.max_plastic_bending_rad", low=0.0, strict=True),
    )
    if plastic.hysteresis > 1.0:
        raise _Refusal("plasticity.hysteresis_ratio must be <= 1")
    return _Material(thickness, e_warp, e_weft, shear, poisson, bending,
                     plastic, calibration_id)


@dataclass(frozen=True)
class _RestElement:
    face: Face
    area: float
    gradients: Tuple[Vec2, Vec2, Vec2]
    normal: Vec3
    condition: float


def _rest_element(points: Sequence[Vec3], face: Face, limit: float) -> _RestElement:
    p0, p1, p2 = (points[i] for i in face)
    e1, e2 = _sub(p1, p0), _sub(p2, p0)
    normal_raw = _cross(e1, e2)
    area = 0.5 * _length(normal_raw)
    if area <= _EPS:
        raise _IllConditioned(f"face {face} has zero rest area")
    normal = _unit(normal_raw, "rest normal")
    warp = _unit(e1, "rest warp edge")
    weft = _unit(_cross(normal, warp), "rest weft")
    a, b = _length(e1), _dot(e2, warp)
    c = _dot(e2, weft)
    if abs(a*c) <= _EPS:
        raise _IllConditioned(f"face {face} has singular rest coordinates")
    # Singular-value condition number of the 2x2 rest edge matrix.
    trace = a*a + b*b + c*c
    determinant = (a*c)**2
    disc = max(0.0, trace*trace - 4.0*determinant)
    high = 0.5 * (trace + math.sqrt(disc))
    low = 0.5 * (trace - math.sqrt(disc))
    condition = math.sqrt(high / low) if low > _EPS else math.inf
    if condition > limit:
        raise _IllConditioned(
            f"face {face} rest condition {condition:.6g} exceeds {limit:.6g}")
    # Dm=[[a,b],[0,c]], columns are rest edges.
    inv00, inv01, inv10, inv11 = 1.0/a, -b/(a*c), 0.0, 1.0/c
    g1 = (inv00, inv01)
    g2 = (inv10, inv11)
    g0 = (-g1[0] - g2[0], -g1[1] - g2[1])
    return _RestElement(face, area, (g0, g1, g2), normal, condition)


def _state(raw: Any, index: int) -> Tuple[List[float], List[float], float, float]:
    if raw is None:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0.0, 0.0
    if not isinstance(raw, Mapping):
        raise _Refusal(f"element_state[{index}] must be a mapping")
    plastic = raw.get("plastic_strain", (0.0, 0.0, 0.0))
    memory = raw.get("hysteresis_memory", (0.0, 0.0, 0.0))
    if not isinstance(plastic, (list, tuple)) or len(plastic) != 3:
        raise _Refusal(f"element_state[{index}].plastic_strain must have 3 values")
    if not isinstance(memory, (list, tuple)) or len(memory) != 3:
        raise _Refusal(f"element_state[{index}].hysteresis_memory must have 3 values")
    return ([ _number(v, f"element_state[{index}].plastic_strain") for v in plastic ],
            [ _number(v, f"element_state[{index}].hysteresis_memory") for v in memory ],
            _number(raw.get("plastic_bending_rad", 0.0), "plastic_bending_rad"),
            _number(raw.get("bending_memory_rad", 0.0), "bending_memory_rad"))


def _clamp(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))


def _plastic_update(strain: Sequence[float], old: Sequence[float],
                    memory: Sequence[float], material: _Material) -> Tuple[List[float], List[float]]:
    proposed, proposed_memory = list(old), list(memory)
    moduli = (material.e_warp, material.e_weft, 2.0*material.shear)
    for i in range(3):
        effective = strain[i] - old[i] - material.plastic.hysteresis*memory[i]
        excess = abs(effective) - material.plastic.yield_strain
        if excess > 0.0:
            denominator = moduli[i] + material.plastic.hardening_pa
            increment = math.copysign(excess * moduli[i] / denominator, effective)
            proposed[i] = _clamp(old[i] + increment, material.plastic.max_strain)
        proposed_memory[i] = strain[i] - proposed[i]
    return proposed, proposed_memory


def _membrane(element: _RestElement, points: Sequence[Vec3], material: _Material,
              old_plastic: Sequence[float], memory: Sequence[float],
              director: Vec3, condition_limit: float) -> Tuple[List[Vec3], List[float], List[float], float, float]:
    face, gradients = element.face, element.gradients
    current = [points[i] for i in face]
    normal_raw = _cross(_sub(current[1], current[0]), _sub(current[2], current[0]))
    current_area2 = _length(normal_raw)
    if current_area2 <= _EPS:
        raise _IllConditioned(f"face {face} collapsed in old state")
    if _dot(normal_raw, director) <= _EPS:
        raise _Inverted(f"face {face} is inverted against its reference director")
    # F columns are sums x_i (grad N_i)_column.
    f0 = (0.0, 0.0, 0.0)
    f1 = (0.0, 0.0, 0.0)
    for point, gradient in zip(current, gradients):
        f0 = _add(f0, _mul(point, gradient[0]))
        f1 = _add(f1, _mul(point, gradient[1]))
    c00, c01, c11 = _dot(f0, f0), _dot(f0, f1), _dot(f1, f1)
    determinant = c00*c11 - c01*c01
    if determinant <= _EPS:
        raise _IllConditioned(f"face {face} deformation gradient is singular")
    trace = c00 + c11
    disc = max(0.0, trace*trace - 4.0*determinant)
    high, low = 0.5*(trace + math.sqrt(disc)), 0.5*(trace - math.sqrt(disc))
    condition = math.sqrt(high/low) if low > _EPS else math.inf
    if condition > condition_limit:
        raise _IllConditioned(
            f"face {face} current condition {condition:.6g} exceeds {condition_limit:.6g}")
    strain = [0.5*(c00 - 1.0), 0.5*(c11 - 1.0), c01]
    effective = [strain[i] - old_plastic[i] - material.plastic.hysteresis*memory[i]
                 for i in range(3)]
    denominator = 1.0 - material.poisson**2
    c11m = material.e_warp / denominator
    c22m = material.e_weft / denominator
    coupling = material.poisson * math.sqrt(material.e_warp*material.e_weft) / denominator
    s00 = c11m*effective[0] + coupling*effective[1]
    s11 = coupling*effective[0] + c22m*effective[1]
    s01 = material.shear*effective[2]
    p0 = _add(_mul(f0, s00), _mul(f1, s01))
    p1 = _add(_mul(f0, s01), _mul(f1, s11))
    scale = element.area * material.thickness
    forces = []
    for gradient in gradients:
        forces.append(_mul(_add(_mul(p0, gradient[0]), _mul(p1, gradient[1])), -scale))
    max_modulus = max(c11m, c22m, material.shear)
    diagonal = [max(_EPS, scale*max_modulus*(g[0]*g[0] + g[1]*g[1])
                    * max(1.0, high)) for g in gradients]
    energy_density = 0.5*(effective[0]*s00 + effective[1]*s11
                          + effective[2]*s01)
    proposed, proposed_memory = _plastic_update(strain, old_plastic, memory, material)
    return forces, diagonal, proposed, proposed_memory, max(0.0, scale*energy_density)


def _dihedral(points: Sequence[Vec3], nodes: Tuple[int, int, int, int]) -> float:
    a, b, c, d = (points[i] for i in nodes)
    edge = _unit(_sub(b, a), "hinge edge")
    n1 = _unit(_cross(_sub(b, a), _sub(c, a)), "hinge left normal")
    n2 = _unit(_cross(_sub(d, a), _sub(b, a)), "hinge right normal")
    return math.atan2(_dot(_cross(n1, n2), edge),
                      max(-1.0, min(1.0, _dot(n1, n2))))


def _hinge_energy(points: Sequence[Vec3], nodes: Tuple[int, int, int, int],
                  rest_angle: float, plastic_angle: float, memory: float,
                  hysteresis: float, stiffness: float, edge_length: float) -> float:
    angle = _dihedral(points, nodes)
    delta = _wrap_angle(angle - rest_angle - plastic_angle - hysteresis*memory)
    return 0.5*stiffness*edge_length*delta*delta


def _bending(points: Sequence[Vec3], nodes: Tuple[int, int, int, int],
             rest_angle: float, material: _Material, other: _Material,
             plastic_angle: float, memory: float, step: float) -> Tuple[List[Vec3], List[float], float, float, float]:
    stiffness = 0.5*(material.bending + other.bending)
    hysteresis = 0.5*(material.plastic.hysteresis + other.plastic.hysteresis)
    edge_length = _length(_sub(points[nodes[1]], points[nodes[0]]))
    base = _hinge_energy(points, nodes, rest_angle, plastic_angle, memory,
                         hysteresis, stiffness, edge_length)
    forces = [[0.0, 0.0, 0.0] for _ in nodes]
    diagonal = [0.0] * len(nodes)
    mutable = [list(point) for point in points]
    for local, vertex in enumerate(nodes):
        for axis in range(3):
            mutable[vertex][axis] += step
            plus_points = [tuple(p) for p in mutable]
            plus = _hinge_energy(plus_points, nodes, rest_angle, plastic_angle,
                                 memory, hysteresis, stiffness, edge_length)
            mutable[vertex][axis] -= 2.0*step
            minus_points = [tuple(p) for p in mutable]
            minus = _hinge_energy(minus_points, nodes, rest_angle, plastic_angle,
                                  memory, hysteresis, stiffness, edge_length)
            mutable[vertex][axis] += step
            forces[local][axis] = -(plus - minus)/(2.0*step)
            diagonal[local] += abs((plus - 2.0*base + minus)/(step*step))
    angle_delta = _wrap_angle(_dihedral(points, nodes) - rest_angle)
    yield_angle = 0.5*(material.plastic.bending_yield_rad
                       + other.plastic.bending_yield_rad)
    max_angle = min(material.plastic.max_bending_rad,
                    other.plastic.max_bending_rad)
    effective = angle_delta - plastic_angle - hysteresis*memory
    proposed = plastic_angle
    if abs(effective) > yield_angle:
        proposed = _clamp(plastic_angle + math.copysign(abs(effective)-yield_angle,
                                                        effective), max_angle)
    proposed_memory = angle_delta - proposed
    return ([tuple(force) for force in forces],
            [max(_EPS, value) for value in diagonal], proposed,
            proposed_memory, base)


def assemble(rest_vertices: Sequence[Sequence[float]],
             old_positions: Sequence[Sequence[float]],
             faces: Sequence[Sequence[int]], *,
             face_material_ids: Sequence[str],
             materials: Mapping[str, Mapping[str, Any]],
             element_state: Optional[Sequence[Mapping[str, Any]]] = None,
             reference_directors: Optional[Sequence[Sequence[float]]] = None,
             fixed_vertices: Sequence[int] = (),
             jacobi_relaxation: float = 0.5,
             condition_limit: float = 1.0e6,
             bending_difference_step_m: float = 1.0e-6) -> Dict[str, Any]:
    """Assemble same-old-state residual and one diagonal Jacobi correction.

    No supplied object is mutated.  ``next_element_state`` is merely a
    constitutive proposal; a caller must accept it when advancing its state.
    """
    try:
        rest = tuple(_vec3(v, f"rest_vertices[{i}]") for i, v in enumerate(rest_vertices))
        old = tuple(_vec3(v, f"old_positions[{i}]") for i, v in enumerate(old_positions))
        if len(rest) != len(old) or not rest:
            raise _Refusal("rest_vertices and old_positions must have equal nonzero length")
        if len(faces) != len(face_material_ids) or not faces:
            raise _Refusal("one face material id is required per nonempty face list")
        if element_state is not None and len(element_state) != len(faces):
            raise _Refusal("element_state must contain one entry per face")
        if reference_directors is not None and len(reference_directors) != len(faces):
            raise _Refusal("reference_directors must contain one direction per face")
        relaxation = _number(jacobi_relaxation, "jacobi_relaxation", low=0.0,
                             strict=True)
        if relaxation > 1.0:
            raise _Refusal("jacobi_relaxation must be <= 1")
        limit = _number(condition_limit, "condition_limit", low=1.0, strict=True)
        difference_step = _number(bending_difference_step_m,
                                  "bending_difference_step_m", low=0.0, strict=True)
        parsed_materials = {str(k): _material(v, str(k)) for k, v in materials.items()}
        parsed_faces: List[Face] = []
        elements: List[_RestElement] = []
        directors: List[Vec3] = []
        states = []
        for i, raw_face in enumerate(faces):
            if (not isinstance(raw_face, (list, tuple)) or len(raw_face) != 3
                    or any(isinstance(v, bool) or not isinstance(v, int)
                           or not 0 <= v < len(rest) for v in raw_face)
                    or len(set(raw_face)) != 3):
                raise _Refusal(f"faces[{i}] must contain three distinct valid indices")
            face = tuple(int(v) for v in raw_face)
            material_id = str(face_material_ids[i])
            if material_id not in parsed_materials:
                raise _Refusal(f"face material {material_id!r} is not defined")
            element = _rest_element(rest, face, limit)
            director = (element.normal if reference_directors is None else
                        _unit(_vec3(reference_directors[i], f"reference_directors[{i}]"),
                              f"reference_directors[{i}]"))
            parsed_faces.append(face)
            elements.append(element)
            directors.append(director)
            states.append(_state(None if element_state is None else element_state[i], i))
        fixed = set()
        for value in fixed_vertices:
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(rest):
                raise _Refusal("fixed_vertices contains an invalid index")
            fixed.add(value)

        residual = [(0.0, 0.0, 0.0) for _ in rest]
        diagonal = [0.0 for _ in rest]
        next_states: List[Dict[str, Any]] = []
        membrane_energy = 0.0
        max_condition = 0.0
        for i, element in enumerate(elements):
            material = parsed_materials[str(face_material_ids[i])]
            plastic, memory, plastic_bend, bend_memory = states[i]
            forces, local_diagonal, proposed, proposed_memory, energy = _membrane(
                element, old, material, plastic, memory, directors[i], limit)
            for local, vertex in enumerate(element.face):
                residual[vertex] = _add(residual[vertex], forces[local])
                diagonal[vertex] += local_diagonal[local]
            next_states.append({
                "plastic_strain": proposed,
                "hysteresis_memory": proposed_memory,
                "plastic_bending_rad": plastic_bend,
                "bending_memory_rad": bend_memory,
            })
            membrane_energy += energy
            max_condition = max(max_condition, element.condition)

        edge_uses: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        for face_index, face in enumerate(parsed_faces):
            for a, b, opposite in ((face[0], face[1], face[2]),
                                   (face[1], face[2], face[0]),
                                   (face[2], face[0], face[1])):
                edge_uses.setdefault(tuple(sorted((a, b))), []).append((face_index, opposite))
        bending_energy = 0.0
        hinge_count = 0
        for edge, uses in sorted(edge_uses.items()):
            if len(uses) > 2:
                raise _Refusal(f"non-manifold edge {edge} has {len(uses)} incident faces")
            if len(uses) != 2:
                continue
            left, right = uses
            nodes = (edge[0], edge[1], left[1], right[1])
            rest_angle = _dihedral(rest, nodes)
            left_state, right_state = states[left[0]], states[right[0]]
            old_plastic_bend = 0.5*(left_state[2] + right_state[2])
            old_bend_memory = 0.5*(left_state[3] + right_state[3])
            left_material = parsed_materials[str(face_material_ids[left[0]])]
            right_material = parsed_materials[str(face_material_ids[right[0]])]
            forces, local_diagonal, proposed_bend, proposed_memory, energy = _bending(
                old, nodes, rest_angle, left_material, right_material,
                old_plastic_bend, old_bend_memory, difference_step)
            for local, vertex in enumerate(nodes):
                residual[vertex] = _add(residual[vertex], forces[local])
                diagonal[vertex] += local_diagonal[local]
            for face_index in (left[0], right[0]):
                next_states[face_index]["plastic_bending_rad"] = proposed_bend
                next_states[face_index]["bending_memory_rad"] = proposed_memory
            bending_energy += energy
            hinge_count += 1

        corrections = []
        residual_records = []
        diagonal_records = []
        for index, force in enumerate(residual):
            if index in fixed:
                correction = (0.0, 0.0, 0.0)
                force = (0.0, 0.0, 0.0)
            else:
                if diagonal[index] <= _EPS:
                    raise _IllConditioned(f"vertex {index} has no positive Jacobi diagonal")
                correction = _mul(force, relaxation/diagonal[index])
            residual_records.append(list(force))
            diagonal_records.append(diagonal[index])
            corrections.append(list(correction))
        if not all(math.isfinite(v) for row in residual_records + corrections for v in row):
            raise _IllConditioned("assembled output is not finite")
        return {
            "verdict": ANSWER,
            "model": "ORTHOTROPIC_STVK_DISCRETE_HINGE",
            "assembly": "SAME_OLD_STATE_JACOBI",
            "units": {"residual": "N", "jacobi_diagonal": "N/m",
                      "correction": "m", "energy": "J"},
            "residuals_n": residual_records,
            "jacobi_diagonal_n_m": diagonal_records,
            "jacobi_corrections_m": corrections,
            "next_element_state": copy.deepcopy(next_states),
            "diagnostics": {
                "faces": len(parsed_faces),
                "interior_hinges": hinge_count,
                "energy_j": {"membrane": membrane_energy,
                             "bending": bending_energy,
                             "total": membrane_energy + bending_energy},
                "maximum_rest_condition": max_condition,
                "calibration_ids": sorted({m.calibration_id
                                           for m in parsed_materials.values()}),
            },
        }
    except _Refusal as error:
        return _unknown(error)


def solve(rest_positions: Sequence[Sequence[float]],
          positions: Sequence[Sequence[float]],
          faces: Sequence[Sequence[int]], *,
          face_material_ids: Sequence[str],
          materials: Mapping[str, Mapping[str, Any]],
          history: Optional[Sequence[Mapping[str, Any]]] = None,
          time_step_s: float) -> Dict[str, Any]:
    """Evaluate the shell law from one old state using the public API.

    ``time_step_s`` identifies the state transition interval and is validated,
    but this constitutive reference does not perform time integration.  The
    caller owns whether and when ``next_history`` is committed.
    """
    try:
        step = _number(time_step_s, "time_step_s", low=0.0, strict=True)
    except _Refusal as error:
        return _unknown(error)
    result = assemble(
        rest_positions, positions, faces,
        face_material_ids=face_material_ids,
        materials=materials,
        element_state=history,
    )
    if result.get("verdict") == ANSWER:
        result["time_step_s"] = step
        result["next_history"] = result.pop("next_element_state")
        result["diagnostics"]["time_integration_performed"] = False
    return result
