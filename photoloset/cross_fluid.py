# -*- coding: utf-8 -*-
"""Deterministic mesoscopic cloth/fluid coupling for the cross solver.

This module is a deliberately bounded engineering approximation.  Triangle
faces sample an immutable old fluid state, produce typed drag/lift signals,
and reduce their vertex and fluid-cell impulses once (Jacobi/same-old-state).
It is not DNS, a Navier--Stokes solver, or a validated wind-tunnel model.

All public inputs and outputs use SI units.  ``fluid`` accepts an optional
uniform cell-centred velocity grid and/or deterministic analytic vortex modes.
The two velocity fields are additive.  The reaction impulse is deposited into
the grid when one exists; otherwise it is retained in a typed external-fluid
reservoir ledger rather than silently discarded.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Mapping, Sequence, Tuple


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_FLUID_INVALID_INPUT"
CFL_UNSAFE = "UNKNOWN_FLUID_CFL_UNSAFE"
DOMAIN_MISS = "UNKNOWN_FLUID_DOMAIN_MISS"
_EPS = 1.0e-12


class _Invalid(ValueError):
    pass


class _DomainMiss(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Return an honest typed declaration of this approximation's limits."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python_stdlib",
        "deterministic": True,
        "randomness": {"used": False, "seed_required": False},
        "features": {
            "uniform_cell_centered_grid": True,
            "analytic_vortex_modes": True,
            "per_face_drag_lift_permeability": True,
            "two_way_momentum_bookkeeping": True,
            "same_old_state_jacobi_reduction": True,
            "cfl_safety_gate": True,
            "compressible_flow": False,
            "viscosity_transport": False,
            "pressure_projection": False,
            "free_surface": False,
            "dns": False,
            "complete_cfd": False,
        },
        "model": (
            "mesoscopic one-step aerodynamic force coupling; additive uniform "
            "grid and regularized line-vortex velocity modes"
        ),
    }


def _unknown(code: str, reason: str, snapshot: Any = None, **extra: Any) -> Dict[str, Any]:
    result = {"verdict": code, "reasons": [reason], "backend": capabilities()}
    if snapshot is not None:
        result["immutable_input_snapshot"] = snapshot
    result.update(extra)
    return result


def _number(value: Any, name: str, *, low: float | None = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a finite SI number")
    result = float(value)
    if not math.isfinite(result):
        raise _Invalid(f"{name} must be finite")
    if low is not None and (result <= low if strict else result < low):
        relation = ">" if strict else ">="
        raise _Invalid(f"{name} must be {relation} {low}")
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
    return (a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec3, name: str) -> Vec3:
    length = _length(a)
    if length <= _EPS:
        raise _Invalid(f"{name} has zero length")
    return _mul(a, 1.0 / length)


def _sum_vectors(values: Sequence[Vec3]) -> Vec3:
    return tuple(math.fsum(value[axis] for value in values)
                 for axis in range(3))  # type: ignore[return-value]


def _shape(value: Any) -> Tuple[int, int, int]:
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 1
                   for v in value)):
        raise _Invalid("fluid.grid.shape must contain three positive integers")
    return int(value[0]), int(value[1]), int(value[2])


def _flat_index(index: Tuple[int, int, int], shape: Tuple[int, int, int]) -> int:
    i, j, k = index
    return (k * shape[1] + j) * shape[0] + i


def _grid_weights(point: Vec3, origin: Vec3, shape: Tuple[int, int, int],
                  spacing: float) -> Tuple[Tuple[int, float], ...]:
    """Trilinear weights for cell-centred data, clamped on domain faces."""
    axes: List[Tuple[Tuple[int, float], ...]] = []
    for axis, count in enumerate(shape):
        coordinate = (point[axis] - origin[axis]) / spacing - 0.5
        if coordinate < -0.5 - _EPS or coordinate > count - 0.5 + _EPS:
            raise _DomainMiss("a cloth face centroid lies outside fluid.grid")
        coordinate = min(float(count - 1), max(0.0, coordinate))
        lower = int(math.floor(coordinate))
        upper = min(count - 1, lower + 1)
        fraction = coordinate - lower
        if upper == lower:
            axes.append(((lower, 1.0),))
        else:
            axes.append(((lower, 1.0 - fraction), (upper, fraction)))
    weights = []
    for i, wi in axes[0]:
        for j, wj in axes[1]:
            for k, wk in axes[2]:
                weight = wi * wj * wk
                if weight > 0.0:
                    weights.append((_flat_index((i, j, k), shape), weight))
    return tuple(weights)


def _parse_grid(raw: Any, spacing: float) -> Dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise _Invalid("fluid.grid must be a mapping")
    origin = _vec(raw.get("origin_m"), "fluid.grid.origin_m")
    shape = _shape(raw.get("shape"))
    velocities_raw = raw.get("velocities_m_s")
    count = shape[0] * shape[1] * shape[2]
    if (not isinstance(velocities_raw, (list, tuple))
            or len(velocities_raw) != count):
        raise _Invalid(f"fluid.grid.velocities_m_s must contain {count} cells")
    velocities = tuple(_vec(value, f"fluid.grid.velocities_m_s[{index}]")
                       for index, value in enumerate(velocities_raw))
    return {"origin": origin, "shape": shape, "spacing": spacing,
            "velocities": velocities}


def _parse_vortices(raw: Any) -> Tuple[Dict[str, Any], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise _Invalid("fluid.vortex_modes must be a sequence")
    modes = []
    seen = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise _Invalid(f"fluid.vortex_modes[{index}] must be a mapping")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise _Invalid("each vortex mode requires a unique non-empty id")
        seen.add(identifier)
        modes.append({
            "id": identifier,
            "center": _vec(item.get("center_m"), f"vortex {identifier}.center_m"),
            "axis": _unit(_vec(item.get("axis"), f"vortex {identifier}.axis"),
                          f"vortex {identifier}.axis"),
            "circulation": _number(item.get("circulation_m2_s"),
                                   f"vortex {identifier}.circulation_m2_s"),
            "core": _number(item.get("core_radius_m"),
                            f"vortex {identifier}.core_radius_m", low=0.0,
                            strict=True),
        })
    return tuple(sorted(modes, key=lambda mode: mode["id"]))


def _vortex_velocity(point: Vec3, mode: Mapping[str, Any]) -> Vec3:
    displacement = _sub(point, mode["center"])
    axial = _mul(mode["axis"], _dot(displacement, mode["axis"]))
    radial = _sub(displacement, axial)
    radius_squared = _dot(radial, radial)
    # Rosenhead regularisation: finite at the centre and deterministic.
    scale = (mode["circulation"] /
             (2.0 * math.pi * (radius_squared + mode["core"]**2)))
    return _mul(_cross(mode["axis"], radial), scale)


def _fluid_velocity(point: Vec3, base: Vec3, grid: Dict[str, Any] | None,
                    modes: Sequence[Mapping[str, Any]]) -> Tuple[Vec3, Tuple[Tuple[int, float], ...]]:
    value = base
    weights: Tuple[Tuple[int, float], ...] = ()
    if grid is not None:
        weights = _grid_weights(point, grid["origin"], grid["shape"], grid["spacing"])
        sampled = _sum_vectors(tuple(_mul(grid["velocities"][index], weight)
                                     for index, weight in weights))
        value = _add(value, sampled)
    for mode in modes:
        value = _add(value, _vortex_velocity(point, mode))
    return value, weights


def _material(raw: Any, name: str) -> Dict[str, float]:
    if not isinstance(raw, Mapping):
        raise _Invalid(f"materials.{name} must be a mapping")
    drag = _number(raw.get("drag_coefficient"),
                   f"materials.{name}.drag_coefficient", low=0.0)
    lift = _number(raw.get("lift_coefficient"),
                   f"materials.{name}.lift_coefficient", low=0.0)
    permeability = _number(raw.get("permeability"),
                           f"materials.{name}.permeability", low=0.0)
    if permeability > 1.0:
        raise _Invalid(f"materials.{name}.permeability must be <= 1")
    return {"drag": drag, "lift": lift, "permeability": permeability}


def couple(positions: Sequence[Sequence[float]],
           velocities: Sequence[Sequence[float]],
           faces: Sequence[Sequence[int]], *,
           face_material_ids: Sequence[str],
           materials: Mapping[str, Mapping[str, Any]],
           fluid: Mapping[str, Any], time_step_s: float) -> Dict[str, Any]:
    """Couple one immutable cloth/fluid state and return forces plus reaction.

    No cloth velocity is integrated because vertex masses are intentionally not
    part of this API.  The returned vertex impulses can be handed to XPBD.  A
    supplied fluid grid *is* momentum-updated from its old cell velocities.
    Every face reads those old velocities, so face traversal cannot feed back
    into another face during this call.
    """
    snapshot = copy.deepcopy({
        "positions": positions, "velocities": velocities, "faces": faces,
        "face_material_ids": face_material_ids, "materials": materials,
        "fluid": fluid, "time_step_s": time_step_s,
    })
    try:
        points = tuple(_vec(value, f"positions[{index}]")
                       for index, value in enumerate(positions))
        speeds = tuple(_vec(value, f"velocities[{index}]")
                       for index, value in enumerate(velocities))
        if not points or len(speeds) != len(points):
            raise _Invalid("positions and velocities must have the same non-zero length")
        if not isinstance(faces, (list, tuple)) or len(faces) != len(face_material_ids):
            raise _Invalid("one face_material_id is required per face")
        if not isinstance(materials, Mapping) or not materials:
            raise _Invalid("materials must be a non-empty mapping")
        parsed_materials = {str(key): _material(value, str(key))
                            for key, value in materials.items()}
        if not isinstance(fluid, Mapping):
            raise _Invalid("fluid must be a mapping")
        density = _number(fluid.get("density_kg_m3"), "fluid.density_kg_m3",
                          low=0.0, strict=True)
        spacing = _number(fluid.get("cell_size_m"), "fluid.cell_size_m",
                          low=0.0, strict=True)
        safety = _number(fluid.get("cfl_safety", 0.5), "fluid.cfl_safety",
                         low=0.0, strict=True)
        if safety > 1.0:
            raise _Invalid("fluid.cfl_safety must be <= 1")
        dt = _number(time_step_s, "time_step_s", low=0.0, strict=True)
        base = _vec(fluid.get("base_velocity_m_s", (0.0, 0.0, 0.0)),
                    "fluid.base_velocity_m_s")
        grid = _parse_grid(fluid.get("grid"), spacing)
        modes = _parse_vortices(fluid.get("vortex_modes"))
        if grid is None and not modes and _length(base) <= _EPS:
            # Still air is valid; requiring a source would make zero-load tests
            # and explicit calm boundary conditions needlessly untyped.
            pass

        records = []
        seen_faces = set()
        max_fluid_speed = _length(base)
        for face_index, raw_face in enumerate(faces):
            if (not isinstance(raw_face, (list, tuple)) or len(raw_face) != 3
                    or any(isinstance(node, bool) or not isinstance(node, int)
                           or not 0 <= node < len(points) for node in raw_face)
                    or len(set(raw_face)) != 3):
                raise _Invalid(f"faces[{face_index}] must contain three distinct valid indices")
            face = tuple(int(node) for node in raw_face)
            canonical = tuple(sorted(face))
            if canonical in seen_faces:
                raise _Invalid("duplicate cloth faces are not allowed")
            seen_faces.add(canonical)
            material_id = str(face_material_ids[face_index])
            if material_id not in parsed_materials:
                raise _Invalid(f"face material {material_id!r} is not defined")
            p0, p1, p2 = (points[node] for node in face)
            area_vector = _mul(_cross(_sub(p1, p0), _sub(p2, p0)), 0.5)
            area = _length(area_vector)
            if area <= _EPS:
                raise _Invalid(f"faces[{face_index}] has zero area")
            normal = _mul(area_vector, 1.0 / area)
            centroid = _mul(_sum_vectors((p0, p1, p2)), 1.0 / 3.0)
            cloth_velocity = _mul(_sum_vectors(tuple(speeds[node] for node in face)), 1.0 / 3.0)
            fluid_velocity, weights = _fluid_velocity(centroid, base, grid, modes)
            max_fluid_speed = max(max_fluid_speed, _length(fluid_velocity))
            relative = _sub(fluid_velocity, cloth_velocity)
            relative_speed = _length(relative)
            material = parsed_materials[material_id]
            transmission = 1.0 - material["permeability"]
            drag = (0.0, 0.0, 0.0)
            lift = (0.0, 0.0, 0.0)
            if relative_speed > _EPS and transmission > 0.0:
                flow_direction = _mul(relative, 1.0 / relative_speed)
                normal_cosine = _dot(flow_direction, normal)
                projected_area = area * abs(normal_cosine)
                dynamic = 0.5 * density * relative_speed * relative_speed * transmission
                drag = _mul(flow_direction, dynamic * material["drag"] * projected_area)
                lift_axis = _sub(normal, _mul(flow_direction, normal_cosine))
                lift_length = _length(lift_axis)
                if lift_length > _EPS and material["lift"] > 0.0:
                    orientation = 1.0 if normal_cosine >= 0.0 else -1.0
                    lift = _mul(lift_axis, orientation * dynamic * material["lift"]
                                * area / lift_length)
            force = _add(drag, lift)
            records.append({
                "key": canonical, "input_index": face_index, "nodes": face,
                "material_id": material_id, "area_m2": area,
                "centroid_m": centroid, "normal": normal,
                "cloth_velocity_m_s": cloth_velocity,
                "fluid_velocity_m_s": fluid_velocity,
                "relative_velocity_m_s": relative, "drag_n": drag,
                "lift_n": lift, "force_n": force, "grid_weights": weights,
            })

        max_cloth_speed = max((_length(value) for value in speeds), default=0.0)
        characteristic_speed = max(max_fluid_speed, max_cloth_speed)
        courant = characteristic_speed * dt / spacing
        required_substeps = max(1, int(math.ceil(courant / safety)))
        if courant > safety + _EPS:
            return _unknown(
                CFL_UNSAFE,
                f"CFL safety requires {required_substeps} substeps for this interval",
                snapshot, cfl={"courant": courant, "safety_limit": safety,
                               "cell_size_m": spacing,
                               "characteristic_speed_m_s": characteristic_speed,
                               "required_substeps": required_substeps})

        # Canonical ordering and fsum make reduction independent of face scan
        # order.  Crucially, no old position/velocity/grid value was mutated.
        records.sort(key=lambda record: record["key"])
        vertex_terms: List[List[Tuple[Tuple[int, int, int], Vec3]]] = [
            [] for _ in points]
        cell_terms: List[List[Tuple[Tuple[int, int, int], Vec3]]] = (
            [[] for _ in grid["velocities"]] if grid is not None else [])
        face_reports = []
        for record in records:
            vertex_impulse = _mul(record["force_n"], dt / 3.0)
            for node in record["nodes"]:
                vertex_terms[node].append((record["key"], vertex_impulse))
            reaction = _mul(record["force_n"], -dt)
            for cell, weight in record["grid_weights"]:
                cell_terms[cell].append((record["key"], _mul(reaction, weight)))
            face_reports.append({
                "face": list(record["nodes"]),
                "material_id": record["material_id"],
                "area_m2": record["area_m2"],
                "centroid_m": list(record["centroid_m"]),
                "normal": list(record["normal"]),
                "old_cloth_velocity_m_s": list(record["cloth_velocity_m_s"]),
                "old_fluid_velocity_m_s": list(record["fluid_velocity_m_s"]),
                "relative_velocity_m_s": list(record["relative_velocity_m_s"]),
                "drag_force_n": list(record["drag_n"]),
                "lift_force_n": list(record["lift_n"]),
                "total_force_n": list(record["force_n"]),
            })
        vertex_impulses = []
        for terms in vertex_terms:
            terms.sort(key=lambda item: item[0])
            vertex_impulses.append(_sum_vectors(tuple(value for _key, value in terms)))
        cloth_impulse = _sum_vectors(tuple(vertex_impulses))
        reaction_impulse = _mul(cloth_impulse, -1.0)

        grid_output = None
        deposited = (0.0, 0.0, 0.0)
        if grid is not None:
            cell_mass = density * spacing**3
            new_velocities = []
            cell_impulses = []
            for old_velocity, terms in zip(grid["velocities"], cell_terms):
                terms.sort(key=lambda item: item[0])
                impulse = _sum_vectors(tuple(value for _key, value in terms))
                cell_impulses.append(impulse)
                new_velocities.append(_add(old_velocity, _mul(impulse, 1.0 / cell_mass)))
            deposited = _sum_vectors(tuple(cell_impulses))
            grid_output = {
                "origin_m": list(grid["origin"]), "shape": list(grid["shape"]),
                "cell_size_m": spacing, "cell_mass_kg": cell_mass,
                "old_velocities_m_s": [list(value) for value in grid["velocities"]],
                "new_velocities_m_s": [list(value) for value in new_velocities],
                "cell_reaction_impulses_n_s": [list(value) for value in cell_impulses],
            }
        reservoir = _sub(reaction_impulse, deposited)
        balance = _add(cloth_impulse, _add(deposited, reservoir))
        return {
            "verdict": ANSWER,
            "cloth": {
                "vertex_forces_n": [list(_mul(value, 1.0 / dt))
                                    for value in vertex_impulses],
                "vertex_impulses_n_s": [list(value) for value in vertex_impulses],
                "total_impulse_n_s": list(cloth_impulse),
            },
            "fluid": {
                "grid": grid_output,
                "grid_reaction_impulse_n_s": list(deposited),
                "external_reservoir_reaction_impulse_n_s": list(reservoir),
                "total_reaction_impulse_n_s": list(reaction_impulse),
            },
            "faces": face_reports,
            "momentum_bookkeeping": {
                "cloth_impulse_n_s": list(cloth_impulse),
                "fluid_reaction_impulse_n_s": list(reaction_impulse),
                "balance_residual_n_s": list(balance),
                "balanced": _length(balance) <= 1.0e-12,
            },
            "cfl": {"courant": courant, "safety_limit": safety,
                    "cell_size_m": spacing,
                    "characteristic_speed_m_s": characteristic_speed,
                    "required_substeps": required_substeps},
            "update_scheme": "JACOBI_SAME_OLD_STATE",
            "cross_contract": {
                "representation": "typed cloth-face/fluid-cell cross signals",
                "aggregation": "same-old-state canonical Jacobi reduction",
                "typed_layers": ["grid_velocity", "vortex_velocity", "drag",
                                 "lift", "permeability", "reaction_impulse"],
                "not_dns_or_complete_cfd": True,
            },
            "backend": capabilities(),
        }
    except _DomainMiss as error:
        return _unknown(DOMAIN_MISS, str(error), snapshot)
    except (KeyError, TypeError, ValueError, IndexError, _Invalid) as error:
        return _unknown(INVALID_INPUT, str(error), snapshot)


__all__ = [
    "ANSWER", "CFL_UNSAFE", "DOMAIN_MISS", "INVALID_INPUT",
    "capabilities", "couple",
]
