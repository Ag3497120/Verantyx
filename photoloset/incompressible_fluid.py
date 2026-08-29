# -*- coding: utf-8 -*-
"""Deterministic small-grid incompressible-flow reference implementation.

Velocity tuples use a compact MAC-equivalent convention: component ``a`` in
cell ``(i,j,k)`` is the flux velocity through that cell's positive ``a`` face;
the negative-face value comes from the preceding cell.  A solid lower-domain
face is implicit zero.  This makes divergence, pressure gradient, and the
Poisson operator an exact discrete D/G pair without external dependencies.

Advection is semi-Lagrangian on the packed velocity field and viscosity is an
explicit same-old-state stencil.  This is a small deterministic reference,
not DNS, a production CFD solver, or a validated turbulence prediction tool.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Mapping, Sequence, Tuple


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_INCOMPRESSIBLE_INVALID_INPUT"
CFL_UNSAFE = "UNKNOWN_INCOMPRESSIBLE_CFL_UNSAFE"
DIFFUSION_UNSAFE = "UNKNOWN_INCOMPRESSIBLE_DIFFUSION_UNSAFE"
_AXES = ("x", "y", "z")
_EPS = 1.0e-14


class _Invalid(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Return typed features and explicit validation limits."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python_stdlib",
        "deterministic": True,
        "randomness": {"used": False, "seed_required": False},
        "discretization": "compact MAC-equivalent positive-face flux grid",
        "features": {
            "semi_lagrangian_advection": True,
            "explicit_viscosity": True,
            "pressure_poisson_jacobi": True,
            "pressure_projection": True,
            "periodic_boundary": True,
            "solid_free_slip_boundary": True,
            "solid_no_slip_boundary": True,
            "cfl_gate": True,
            "mass_ledger": True,
            "optional_smagorinsky_les": True,
            "variable_density": False,
            "compressible_flow": False,
            "dns": False,
            "complete_cfd": False,
        },
        "verification": {
            "laminar_core": "verified against uniform flow, projection, and viscous decay cases",
            "pressure_projection": "discrete residual and divergence regression tested",
            "smagorinsky_les": "IMPLEMENTED_UNCALIBRATED_NOT_VALIDATED",
        },
    }


def _unknown(code: str, reason: str, snapshot: Any, **extra: Any) -> Dict[str, Any]:
    result = {
        "verdict": code,
        "reasons": [reason],
        "backend": capabilities(),
        "immutable_input_snapshot": snapshot,
    }
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
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must contain three finite components")
    return tuple(_number(component, f"{name}[{axis}]")
                 for axis, component in enumerate(value))  # type: ignore[return-value]


def _shape(value: Any) -> Tuple[int, int, int]:
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(isinstance(component, bool) or not isinstance(component, int)
                   or component < 2 for component in value)):
        raise _Invalid("shape must contain three integers >= 2")
    return int(value[0]), int(value[1]), int(value[2])


def _flat(index: Tuple[int, int, int], shape: Tuple[int, int, int]) -> int:
    return (index[2] * shape[1] + index[1]) * shape[0] + index[0]


def _index(flat_index: int, shape: Tuple[int, int, int]) -> Tuple[int, int, int]:
    plane = shape[0] * shape[1]
    k, remainder = divmod(flat_index, plane)
    j, i = divmod(remainder, shape[0])
    return i, j, k


def _boundary(raw: Any) -> Tuple[str, str, str]:
    allowed = {"periodic", "solid_free_slip", "solid_no_slip"}
    if raw is None:
        result = ("solid_free_slip",) * 3
    elif isinstance(raw, str):
        result = (raw,) * 3
    elif isinstance(raw, Mapping):
        result = tuple(raw.get(axis) for axis in _AXES)
    else:
        raise _Invalid("boundary must be a mode string or x/y/z mapping")
    if any(mode not in allowed for mode in result):
        raise _Invalid("boundary modes are periodic, solid_free_slip, or solid_no_slip")
    return result  # type: ignore[return-value]


def _neighbor(index: Tuple[int, int, int], axis: int, offset: int,
              shape: Tuple[int, int, int], boundary: Tuple[str, str, str]
              ) -> Tuple[int, int, int] | None:
    candidate = list(index)
    candidate[axis] += offset
    if 0 <= candidate[axis] < shape[axis]:
        return tuple(candidate)  # type: ignore[return-value]
    if boundary[axis] == "periodic":
        candidate[axis] %= shape[axis]
        return tuple(candidate)  # type: ignore[return-value]
    return None


def _apply_boundary(velocity: Sequence[Vec3], shape: Tuple[int, int, int],
                    boundary: Tuple[str, str, str]) -> Tuple[Vec3, ...]:
    output = [list(value) for value in velocity]
    for flat_index in range(len(output)):
        index = _index(flat_index, shape)
        for axis, mode in enumerate(boundary):
            if mode != "periodic" and index[axis] == shape[axis] - 1:
                # Stored positive face is the upper domain face.
                output[flat_index][axis] = 0.0
            # Tangential no-slip is represented by the anti-symmetric ghost
            # value in _velocity_neighbor. Clamping the whole adjacent cell
            # here would overwrite interior faces after pressure projection
            # and manufacture divergence.
    return tuple(tuple(value) for value in output)  # type: ignore[return-value]


def _sample_component(field: Sequence[Vec3], point: Vec3, component: int,
                      shape: Tuple[int, int, int], boundary: Tuple[str, str, str]
                      ) -> float:
    axes: List[Tuple[Tuple[int, float], ...]] = []
    for axis in range(3):
        coordinate = point[axis] - 0.5
        if boundary[axis] == "periodic":
            coordinate %= shape[axis]
        else:
            coordinate = min(shape[axis] - 1.0, max(0.0, coordinate))
        lower = int(math.floor(coordinate))
        fraction = coordinate - lower
        upper = lower + 1
        if boundary[axis] == "periodic":
            upper %= shape[axis]
        else:
            upper = min(shape[axis] - 1, upper)
        axes.append(((lower, 1.0 - fraction), (upper, fraction)))
    terms = []
    for i, wi in axes[0]:
        for j, wj in axes[1]:
            for k, wk in axes[2]:
                terms.append(field[_flat((i, j, k), shape)][component] * wi * wj * wk)
    return math.fsum(terms)


def _advect(old: Sequence[Vec3], shape: Tuple[int, int, int],
            boundary: Tuple[str, str, str], dt: float, spacing: float) -> Tuple[Vec3, ...]:
    output = []
    for flat_index, velocity in enumerate(old):
        index = _index(flat_index, shape)
        centre = tuple(component + 0.5 for component in index)
        back = tuple(centre[axis] - dt * velocity[axis] / spacing for axis in range(3))
        output.append(tuple(_sample_component(old, back, component, shape, boundary)
                            for component in range(3)))
    return tuple(output)  # type: ignore[return-value]


def _scalar_neighbor(values: Sequence[float], index: Tuple[int, int, int],
                     axis: int, offset: int, shape: Tuple[int, int, int],
                     boundary: Tuple[str, str, str], centre: float) -> float:
    neighbor = _neighbor(index, axis, offset, shape, boundary)
    return centre if neighbor is None else values[_flat(neighbor, shape)]


def _velocity_neighbor(values: Sequence[Vec3], index: Tuple[int, int, int],
                       axis: int, offset: int, shape: Tuple[int, int, int],
                       boundary: Tuple[str, str, str], component: int) -> float:
    neighbor = _neighbor(index, axis, offset, shape, boundary)
    if neighbor is not None:
        return values[_flat(neighbor, shape)][component]
    mode = boundary[axis]
    if mode == "solid_no_slip":
        return -values[_flat(index, shape)][component]
    return values[_flat(index, shape)][component]


def _strain_magnitude(values: Sequence[Vec3], flat_index: int,
                      shape: Tuple[int, int, int], boundary: Tuple[str, str, str],
                      spacing: float) -> float:
    index = _index(flat_index, shape)
    gradient = [[0.0] * 3 for _ in range(3)]
    for component in range(3):
        for axis in range(3):
            plus = _velocity_neighbor(values, index, axis, 1, shape, boundary, component)
            minus = _velocity_neighbor(values, index, axis, -1, shape, boundary, component)
            gradient[component][axis] = (plus - minus) / (2.0 * spacing)
    strain_squared = 0.0
    for row in range(3):
        for column in range(3):
            symmetric = 0.5 * (gradient[row][column] + gradient[column][row])
            strain_squared += symmetric * symmetric
    return math.sqrt(2.0 * strain_squared)


def _viscosity(old: Sequence[Vec3], shape: Tuple[int, int, int],
               boundary: Tuple[str, str, str], dt: float, spacing: float,
               molecular_nu: float, les_coefficient: float | None
               ) -> Tuple[Tuple[Vec3, ...], Tuple[float, ...]]:
    effective = []
    for flat_index in range(len(old)):
        eddy = (0.0 if les_coefficient is None else
                (les_coefficient * spacing)**2
                * _strain_magnitude(old, flat_index, shape, boundary, spacing))
        effective.append(molecular_nu + eddy)
    output = []
    inverse_h2 = 1.0 / (spacing * spacing)
    for flat_index, centre in enumerate(old):
        index = _index(flat_index, shape)
        components = []
        for component in range(3):
            differences = []
            for axis in range(3):
                plus = _velocity_neighbor(old, index, axis, 1, shape, boundary, component)
                minus = _velocity_neighbor(old, index, axis, -1, shape, boundary, component)
                differences.append(plus - 2.0 * centre[component] + minus)
            components.append(centre[component] + dt * effective[flat_index]
                              * math.fsum(differences) * inverse_h2)
        output.append(tuple(components))
    return tuple(output), tuple(effective)  # type: ignore[return-value]


def _divergence(velocity: Sequence[Vec3], shape: Tuple[int, int, int],
                boundary: Tuple[str, str, str], spacing: float) -> Tuple[float, ...]:
    output = []
    for flat_index, positive in enumerate(velocity):
        index = _index(flat_index, shape)
        terms = []
        for axis in range(3):
            negative_index = _neighbor(index, axis, -1, shape, boundary)
            negative = (0.0 if negative_index is None else
                        velocity[_flat(negative_index, shape)][axis])
            terms.append((positive[axis] - negative) / spacing)
        output.append(math.fsum(terms))
    return tuple(output)


def _pressure_laplacian(pressure: Sequence[float], shape: Tuple[int, int, int],
                        boundary: Tuple[str, str, str], spacing: float
                        ) -> Tuple[float, ...]:
    result = []
    inverse_h2 = 1.0 / (spacing * spacing)
    for flat_index, centre in enumerate(pressure):
        index = _index(flat_index, shape)
        terms = []
        for axis in range(3):
            plus = _scalar_neighbor(pressure, index, axis, 1, shape, boundary, centre)
            minus = _scalar_neighbor(pressure, index, axis, -1, shape, boundary, centre)
            terms.append(plus - 2.0 * centre + minus)
        result.append(math.fsum(terms) * inverse_h2)
    return tuple(result)


def _poisson(rhs: Sequence[float], shape: Tuple[int, int, int],
             boundary: Tuple[str, str, str], spacing: float,
             iterations: int, tolerance: float) -> Tuple[Tuple[float, ...], int, float, List[float]]:
    pressure = tuple(0.0 for _ in rhs)
    history: List[float] = []
    used = 0
    for iteration in range(iterations):
        updated = []
        for flat_index, centre in enumerate(pressure):
            index = _index(flat_index, shape)
            neighbors = []
            for axis in range(3):
                neighbors.append(_scalar_neighbor(
                    pressure, index, axis, 1, shape, boundary, centre))
                neighbors.append(_scalar_neighbor(
                    pressure, index, axis, -1, shape, boundary, centre))
            updated.append((math.fsum(neighbors) - rhs[flat_index] * spacing**2) / 6.0)
        mean = math.fsum(updated) / len(updated)
        pressure = tuple(value - mean for value in updated)
        residuals = tuple(laplace - target for laplace, target in
                          zip(_pressure_laplacian(pressure, shape, boundary, spacing), rhs))
        residual = math.sqrt(math.fsum(value * value for value in residuals) / len(rhs))
        history.append(residual)
        used = iteration + 1
        if residual <= tolerance:
            break
    return pressure, used, history[-1], history


def _project(velocity: Sequence[Vec3], pressure: Sequence[float],
             shape: Tuple[int, int, int], boundary: Tuple[str, str, str],
             dt: float, spacing: float, density: float) -> Tuple[Vec3, ...]:
    output = []
    scale = dt / (density * spacing)
    for flat_index, old in enumerate(velocity):
        index = _index(flat_index, shape)
        components = []
        for axis in range(3):
            plus = _neighbor(index, axis, 1, shape, boundary)
            gradient = (0.0 if plus is None else
                        pressure[_flat(plus, shape)] - pressure[flat_index])
            components.append(old[axis] - scale * gradient)
        output.append(tuple(components))
    return _apply_boundary(tuple(output), shape, boundary)


def _norms(values: Sequence[float]) -> Dict[str, float]:
    return {
        "l1_mean_s_inv": math.fsum(abs(value) for value in values) / len(values),
        "l2_rms_s_inv": math.sqrt(math.fsum(value * value for value in values)
                                  / len(values)),
        "linf_s_inv": max((abs(value) for value in values), default=0.0),
        "signed_sum_s_inv": math.fsum(values),
    }


def step(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Advance one deterministic incompressible reference-grid interval."""
    snapshot = copy.deepcopy(request)
    try:
        if not isinstance(request, Mapping):
            raise _Invalid("request must be a mapping")
        shape = _shape(request.get("shape"))
        count = shape[0] * shape[1] * shape[2]
        raw_velocity = request.get("velocities_m_s")
        if not isinstance(raw_velocity, (list, tuple)) or len(raw_velocity) != count:
            raise _Invalid(f"velocities_m_s must contain {count} packed cells")
        velocity = tuple(_vec(value, f"velocities_m_s[{index}]")
                         for index, value in enumerate(raw_velocity))
        spacing = _number(request.get("cell_size_m"), "cell_size_m", low=0.0, strict=True)
        density = _number(request.get("density_kg_m3"), "density_kg_m3", low=0.0,
                          strict=True)
        viscosity = _number(request.get("kinematic_viscosity_m2_s", 0.0),
                            "kinematic_viscosity_m2_s", low=0.0)
        dt = _number(request.get("time_step_s"), "time_step_s", low=0.0, strict=True)
        safety = _number(request.get("cfl_safety", 0.8), "cfl_safety", low=0.0,
                         strict=True)
        if safety > 1.0:
            raise _Invalid("cfl_safety must be <= 1")
        boundary = _boundary(request.get("boundary"))
        iterations = request.get("pressure_iterations", 200)
        if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
            raise _Invalid("pressure_iterations must be a positive integer")
        tolerance = _number(request.get("pressure_tolerance_s_inv", 1.0e-8),
                            "pressure_tolerance_s_inv", low=0.0)
        acceleration = _vec(request.get("external_acceleration_m_s2", (0.0, 0.0, 0.0)),
                            "external_acceleration_m_s2")
        les = request.get("les", {"model": "none"})
        if not isinstance(les, Mapping):
            raise _Invalid("les must be a mapping")
        les_model = les.get("model", "none")
        if les_model not in ("none", "smagorinsky"):
            raise _Invalid("les.model must be none or smagorinsky")
        les_coefficient = None
        if les_model == "smagorinsky":
            les_coefficient = _number(les.get("coefficient"), "les.coefficient",
                                      low=0.0, strict=True)
            if les_coefficient > 0.3:
                raise _Invalid("les.coefficient must be <= 0.3")

        velocity = _apply_boundary(velocity, shape, boundary)
        max_speed = max(math.sqrt(math.fsum(component * component for component in value))
                        for value in velocity)
        courant = max_speed * dt / spacing
        required_substeps = max(1, int(math.ceil(courant / safety)))
        cfl = {"courant": courant, "safety_limit": safety,
               "maximum_speed_m_s": max_speed, "cell_size_m": spacing,
               "required_substeps": required_substeps}
        if courant > safety + _EPS:
            return _unknown(CFL_UNSAFE,
                            f"advection CFL requires {required_substeps} substeps",
                            snapshot, cfl=cfl)

        advected = _advect(velocity, shape, boundary, dt, spacing)
        forced = tuple(tuple(advected[index][axis] + dt * acceleration[axis]
                             for axis in range(3)) for index in range(count))
        # Estimate LES viscosity from exactly this immutable old diffusion stage.
        _preview, effective = _viscosity(forced, shape, boundary, 0.0, spacing,
                                         viscosity, les_coefficient)
        max_effective = max(effective, default=viscosity)
        diffusion_number = max_effective * dt / (spacing * spacing)
        if diffusion_number > 1.0 / 6.0 + _EPS:
            required = max(1, int(math.ceil(diffusion_number / (1.0 / 6.0))))
            return _unknown(
                DIFFUSION_UNSAFE,
                f"explicit viscosity requires {required} substeps",
                snapshot,
                diffusion={"maximum_effective_viscosity_m2_s": max_effective,
                           "diffusion_number": diffusion_number,
                           "safety_limit": 1.0 / 6.0,
                           "required_substeps": required})
        diffused, effective = _viscosity(forced, shape, boundary, dt, spacing,
                                         viscosity, les_coefficient)
        provisional = _apply_boundary(diffused, shape, boundary)
        divergence_before = _divergence(provisional, shape, boundary, spacing)
        # Remove only round-off compatibility error from the singular Neumann/
        # periodic Poisson system and report it rather than hiding it.
        mean_divergence = math.fsum(divergence_before) / count
        compatible_divergence = tuple(value - mean_divergence
                                      for value in divergence_before)
        rhs = tuple(density * value / dt for value in compatible_divergence)
        pressure, used, pressure_residual, residual_history = _poisson(
            rhs, shape, boundary, spacing, iterations,
            density * tolerance / dt)
        projected = _project(provisional, pressure, shape, boundary, dt, spacing, density)
        divergence_after = _divergence(projected, shape, boundary, spacing)
        before_norms = _norms(divergence_before)
        after_norms = _norms(divergence_after)
        volume = count * spacing**3
        mass = density * volume
        boundary_volume_rate_before = math.fsum(divergence_before) * spacing**3
        boundary_volume_rate_after = math.fsum(divergence_after) * spacing**3
        return {
            "verdict": ANSWER,
            "terminal_verdict": ("PRESSURE_TOLERANCE_MET" if pressure_residual
                                 <= density * tolerance / dt else "PRESSURE_ITERATION_LIMIT"),
            "state": {
                "shape": list(shape), "cell_size_m": spacing,
                "velocities_m_s": [list(value) for value in projected],
                "pressure_pa": list(pressure), "density_kg_m3": density,
                "boundary": dict(zip(_AXES, boundary)),
            },
            "diagnostics": {
                "advection": "SEMI_LAGRANGIAN_PACKED_VELOCITY",
                "diffusion": "EXPLICIT_SAME_OLD_STATE",
                "projection": "POISSON_JACOBI_DISCRETE_DG_PAIR",
                "cfl": cfl,
                "diffusion_number": diffusion_number,
                "effective_viscosity_m2_s": {
                    "minimum": min(effective), "maximum": max(effective),
                    "molecular": viscosity,
                    "les_model": les_model,
                    "les_verification": ("NOT_APPLICABLE" if les_model == "none"
                                         else "IMPLEMENTED_UNCALIBRATED_NOT_VALIDATED"),
                },
                "divergence_before_projection": before_norms,
                "divergence_after_projection": after_norms,
                "pressure_poisson": {
                    "iterations": used,
                    "requested_iterations": iterations,
                    "residual_rms_kg_m3_s2": pressure_residual,
                    "residual_history_rms_kg_m3_s2": residual_history,
                    "tolerance_rms_kg_m3_s2": density * tolerance / dt,
                    "removed_rhs_mean_s_inv": mean_divergence,
                },
                "mass_ledger": {
                    "initial_mass_kg": mass, "final_mass_kg": mass,
                    "mass_change_kg": 0.0,
                    "constant_density_assumption": True,
                    "boundary_volume_flow_before_m3_s": boundary_volume_rate_before,
                    "boundary_volume_flow_after_m3_s": boundary_volume_rate_after,
                    "projection_volume_balance_residual_m3_s": boundary_volume_rate_after,
                },
            },
            "cross_contract": {
                "representation": "compact six-face flux signals per cell",
                "stages": ["advection", "body_force", "viscosity", "divergence",
                           "pressure_poisson", "pressure_projection"],
                "same_old_state_stages": ["advection", "viscosity", "poisson_jacobi"],
                "not_dns_or_complete_cfd": True,
            },
            "backend": capabilities(),
        }
    except (KeyError, TypeError, ValueError, IndexError, _Invalid) as error:
        return _unknown(INVALID_INPUT, str(error), snapshot)


__all__ = [
    "ANSWER", "CFL_UNSAFE", "DIFFUSION_UNSAFE", "INVALID_INPUT",
    "capabilities", "step",
]
