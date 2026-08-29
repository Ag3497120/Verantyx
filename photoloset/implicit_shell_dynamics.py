# -*- coding: utf-8 -*-
"""Deterministic implicit Newmark dynamics for ``cross_shell`` meshes.

The displacement at the end of each time step is solved by Newton iterations
on the complete dynamic residual (internal + external - inertia - damping).
A finite-difference derivative of that exact residual supplies a numerical
residual-consistent tangent.  It is not an analytic material consistent
tangent and this CPU reference is not an industrial-certified dynamics code.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from photoloset import cross_shell, nonlinear_shell_fem


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_REQUEST = "UNKNOWN_IMPLICIT_SHELL_INVALID_REQUEST"
NONCONVERGENCE = "UNKNOWN_IMPLICIT_SHELL_NONCONVERGENCE"
_EPS = 1.0e-15

__all__ = ("capabilities", "solve")


class _Invalid(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Describe implemented behavior without claiming production fidelity."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python_standard_library",
        "solver": "implicit_newmark_numerical_tangent_newton",
        "constitutive_backend": "photoloset.cross_shell",
        "static_solver_lineage": nonlinear_shell_fem.capabilities()["solver"],
        "features": {
            "implicit_newmark": True,
            "newton_iterations": True,
            "numerical_residual_consistent_tangent": True,
            "residual_line_search": True,
            "fixed_vertices": True,
            "load_stepping": True,
            "explicit_load_factors": True,
            "energy_ledger": True,
            "residual_ledger": True,
            "typed_nonconvergence": True,
            "deterministic": True,
            "analytic_consistent_material_tangent": False,
            "contact_or_ccd": False,
            "fluid_structure_coupling": False,
            "adaptive_time_stepping": False,
            "industrial_certification": False,
            "gpu": False,
        },
        "limitations": [
            "finite-difference tangent is residual-consistent only to the selected perturbation",
            "material history is frozen during Newton and committed after a converged time step",
            "fixed boundaries are time-invariant; prescribed trajectories are not implemented",
            "energy balance is a diagnostic ledger, not an exact conservation guarantee",
            "no contact, CCD, adaptive stepping, fracture, or industrial validation",
        ],
    }


def _number(value: Any, name: str, *, low: Optional[float] = None,
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


def _integer(value: Any, name: str, *, low: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise _Invalid(f"{name} must be an integer >= {low}")
    return value


def _vec3(value: Any, name: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must contain three finite SI components")
    return tuple(_number(component, f"{name}[{axis}]")
                 for axis, component in enumerate(value))  # type: ignore[return-value]


def _vectors(value: Any, name: str, length: Optional[int] = None) -> Tuple[Vec3, ...]:
    if not isinstance(value, (list, tuple)):
        raise _Invalid(f"{name} must be a sequence")
    result = tuple(_vec3(item, f"{name}[{index}]")
                   for index, item in enumerate(value))
    if length is not None and len(result) != length:
        raise _Invalid(f"{name} must contain {length} vectors")
    return result


def _faces(value: Any, vertices: int) -> Tuple[Tuple[int, int, int], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise _Invalid("faces must be a nonempty sequence")
    parsed = []
    for index, face in enumerate(value):
        if (not isinstance(face, (list, tuple)) or len(face) != 3
                or any(isinstance(node, bool) or not isinstance(node, int)
                       or not 0 <= node < vertices for node in face)
                or len(set(face)) != 3):
            raise _Invalid(f"faces[{index}] must contain three distinct valid indices")
        parsed.append(tuple(int(node) for node in face))
    return tuple(parsed)


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(a: Vec3, scale: float) -> Vec3:
    return a[0]*scale, a[1]*scale, a[2]*scale


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _norm(rows: Sequence[Vec3], free: Sequence[int]) -> Tuple[float, float]:
    norms = [math.sqrt(_dot(rows[index], rows[index])) for index in free]
    return math.sqrt(sum(value*value for value in norms)), max(norms, default=0.0)


def _flatten(rows: Sequence[Vec3], free: Sequence[int]) -> List[float]:
    return [rows[index][axis] for index in free for axis in range(3)]


def _parse(request: Any) -> Dict[str, Any]:
    if not isinstance(request, Mapping):
        raise _Invalid("request must be a mapping")
    rest = _vectors(request.get("rest_positions"), "rest_positions")
    if not rest:
        raise _Invalid("rest_positions must not be empty")
    count = len(rest)
    positions = _vectors(request.get("initial_positions", rest),
                         "initial_positions", count)
    zero = [(0.0, 0.0, 0.0)]*count
    velocities = _vectors(request.get("initial_velocities_m_s", zero),
                          "initial_velocities_m_s", count)
    accelerations = _vectors(request.get("initial_accelerations_m_s2", zero),
                             "initial_accelerations_m_s2", count)
    faces = _faces(request.get("faces"), count)
    material_ids = request.get("face_material_ids")
    if (not isinstance(material_ids, (list, tuple))
            or len(material_ids) != len(faces)
            or any(not isinstance(value, str) or not value for value in material_ids)):
        raise _Invalid("face_material_ids must contain one nonempty string per face")
    materials = request.get("materials")
    if not isinstance(materials, Mapping) or not materials:
        raise _Invalid("materials must be a nonempty mapping")
    history = request.get("history")
    if history is not None:
        if (not isinstance(history, (list, tuple)) or len(history) != len(faces)
                or any(not isinstance(entry, Mapping) for entry in history)):
            raise _Invalid("history must contain one mapping per face")
        history = copy.deepcopy(list(history))
    masses_raw = request.get("nodal_masses_kg")
    if not isinstance(masses_raw, (list, tuple)) or len(masses_raw) != count:
        raise _Invalid("nodal_masses_kg must contain one positive mass per vertex")
    masses = tuple(_number(value, f"nodal_masses_kg[{index}]", low=0.0,
                           strict=True) for index, value in enumerate(masses_raw))
    dt = _number(request.get("time_step_s"), "time_step_s", low=0.0, strict=True)
    steps = _integer(request.get("steps"), "steps", low=1)

    boundary = request.get("boundary_conditions", {})
    if not isinstance(boundary, Mapping):
        raise _Invalid("boundary_conditions must be a mapping")
    fixed_raw = boundary.get("fixed_vertices", ())
    if not isinstance(fixed_raw, (list, tuple)):
        raise _Invalid("fixed_vertices must be a sequence")
    fixed_set = set()
    for index in fixed_raw:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
            raise _Invalid("fixed_vertices contains an invalid index")
        fixed_set.add(index)
    if len(fixed_set) == count:
        raise _Invalid("at least one free vertex is required")
    fixed = tuple(sorted(fixed_set))
    free = tuple(index for index in range(count) if index not in fixed_set)
    fixed_positions = {index: positions[index] for index in fixed}

    loads = request.get("loads", {})
    if not isinstance(loads, Mapping):
        raise _Invalid("loads must be a mapping")
    forces = _vectors(loads.get("nodal_forces_n", zero),
                      "loads.nodal_forces_n", count)
    factors_raw = loads.get("load_factors")
    if factors_raw is None:
        factors = tuple((index + 1)/steps for index in range(steps))
    else:
        if not isinstance(factors_raw, (list, tuple)) or len(factors_raw) != steps:
            raise _Invalid("loads.load_factors must contain one value per time step")
        factors = tuple(_number(value, f"loads.load_factors[{index}]", low=0.0)
                        for index, value in enumerate(factors_raw))

    newmark = request.get("newmark", {})
    if not isinstance(newmark, Mapping):
        raise _Invalid("newmark must be a mapping")
    beta = _number(newmark.get("beta", 0.25), "newmark.beta", low=0.0, strict=True)
    gamma = _number(newmark.get("gamma", 0.5), "newmark.gamma", low=0.0,
                    strict=True)
    damping = _number(newmark.get("mass_damping_per_s", 0.0),
                      "newmark.mass_damping_per_s", low=0.0)

    solver = request.get("solver", {})
    if not isinstance(solver, Mapping):
        raise _Invalid("solver must be a mapping")
    max_iterations = _integer(solver.get("max_iterations", 30),
                              "solver.max_iterations", low=1)
    absolute_tolerance = _number(solver.get("absolute_residual_tolerance_n", 1.0e-7),
                                 "solver.absolute_residual_tolerance_n", low=0.0,
                                 strict=True)
    relative_tolerance = _number(solver.get("relative_residual_tolerance", 1.0e-8),
                                 "solver.relative_residual_tolerance", low=0.0)
    displacement_tolerance = _number(solver.get("displacement_tolerance_m", 1.0e-12),
                                     "solver.displacement_tolerance_m", low=0.0,
                                     strict=True)
    tangent_step = _number(solver.get("tangent_difference_step_m", 1.0e-7),
                           "solver.tangent_difference_step_m", low=0.0, strict=True)
    reductions = _integer(solver.get("line_search_reductions", 12),
                          "solver.line_search_reductions", low=0)
    contraction = _number(solver.get("line_search_contraction", 0.5),
                          "solver.line_search_contraction", low=0.0, strict=True)
    armijo = _number(solver.get("line_search_armijo", 1.0e-4),
                     "solver.line_search_armijo", low=0.0, strict=True)
    if contraction >= 1.0 or armijo >= 1.0:
        raise _Invalid("line search contraction and Armijo coefficient must be < 1")
    regularization = _number(solver.get("tangent_regularization_n_m", 1.0e-10),
                             "solver.tangent_regularization_n_m", low=0.0)
    return {
        "rest": rest, "positions": positions, "velocities": velocities,
        "accelerations": accelerations, "faces": faces,
        "material_ids": tuple(material_ids), "materials": copy.deepcopy(dict(materials)),
        "history": history, "masses": masses, "dt": dt, "steps": steps,
        "fixed": fixed, "free": free, "fixed_positions": fixed_positions,
        "forces": forces, "factors": factors, "beta": beta, "gamma": gamma,
        "damping": damping, "max_iterations": max_iterations,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "displacement_tolerance": displacement_tolerance,
        "tangent_step": tangent_step, "reductions": reductions,
        "contraction": contraction, "armijo": armijo,
        "regularization": regularization,
    }


def _shell(data: Mapping[str, Any], positions: Sequence[Vec3], history: Any) -> Dict[str, Any]:
    return cross_shell.solve(
        data["rest"], positions, data["faces"],
        face_material_ids=data["material_ids"], materials=data["materials"],
        history=history, time_step_s=data["dt"])


def _predict(data: Mapping[str, Any], positions: Sequence[Vec3],
             velocities: Sequence[Vec3], accelerations: Sequence[Vec3]) -> Tuple[Tuple[Vec3, ...], Tuple[Vec3, ...]]:
    dt, beta, gamma = data["dt"], data["beta"], data["gamma"]
    x_predictor = tuple(_add(_add(positions[index], _mul(velocities[index], dt)),
                             _mul(accelerations[index], dt*dt*(0.5-beta)))
                        for index in range(len(positions)))
    v_predictor = tuple(_add(velocities[index],
                             _mul(accelerations[index], dt*(1.0-gamma)))
                        for index in range(len(positions)))
    return x_predictor, v_predictor


def _kinematics(data: Mapping[str, Any], positions: Sequence[Vec3],
                x_predictor: Sequence[Vec3], v_predictor: Sequence[Vec3]) -> Tuple[Tuple[Vec3, ...], Tuple[Vec3, ...]]:
    acceleration_scale = 1.0/(data["beta"]*data["dt"]*data["dt"])
    accelerations = tuple(_mul(_sub(positions[index], x_predictor[index]),
                               acceleration_scale)
                          for index in range(len(positions)))
    velocities = tuple(_add(v_predictor[index],
                            _mul(accelerations[index], data["gamma"]*data["dt"]))
                       for index in range(len(positions)))
    return velocities, accelerations


def _evaluate(data: Mapping[str, Any], positions: Sequence[Vec3], history: Any,
              x_predictor: Sequence[Vec3], v_predictor: Sequence[Vec3],
              factor: float) -> Tuple[Dict[str, Any], Tuple[Vec3, ...], Tuple[Vec3, ...], Tuple[Vec3, ...]]:
    shell = _shell(data, positions, history)
    if shell.get("verdict") != ANSWER:
        return shell, (), (), ()
    velocities, accelerations = _kinematics(data, positions, x_predictor, v_predictor)
    fixed = set(data["fixed"])
    residual = []
    for index, internal_raw in enumerate(shell["residuals_n"]):
        internal = _vec3(internal_raw, f"cross_shell.residuals_n[{index}]")
        total = _add(internal, _mul(data["forces"][index], factor))
        total = _sub(total, _mul(accelerations[index], data["masses"][index]))
        total = _sub(total, _mul(velocities[index],
                                 data["masses"][index]*data["damping"]))
        residual.append((0.0, 0.0, 0.0) if index in fixed else total)
    return shell, tuple(residual), velocities, accelerations


def _dense_solve(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> List[float]:
    size = len(rhs)
    augmented = [list(matrix[row]) + [float(rhs[row])] for row in range(size)]
    scale = max((abs(value) for row in matrix for value in row), default=0.0)
    threshold = max(_EPS, scale*1.0e-14)
    for column in range(size):
        pivot = max(range(column, size),
                    key=lambda row: (abs(augmented[row][column]), -row))
        if abs(augmented[pivot][column]) <= threshold:
            raise _Invalid("numerical dynamic tangent is singular")
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for entry in range(column, size + 1):
            augmented[column][entry] /= divisor
        for row in range(column + 1, size):
            multiplier = augmented[row][column]
            for entry in range(column, size + 1):
                augmented[row][entry] -= multiplier*augmented[column][entry]
    result = [0.0]*size
    for row in range(size - 1, -1, -1):
        result[row] = augmented[row][size] - sum(
            augmented[row][column]*result[column]
            for column in range(row + 1, size))
    if not all(math.isfinite(value) for value in result):
        raise _Invalid("dynamic tangent solution is non-finite")
    return result


def _direction(data: Mapping[str, Any], positions: Sequence[Vec3], history: Any,
               x_predictor: Sequence[Vec3], v_predictor: Sequence[Vec3],
               factor: float, residual: Sequence[Vec3]) -> Tuple[Vec3, ...]:
    free = data["free"]
    dofs = [(vertex, axis) for vertex in free for axis in range(3)]
    base = _flatten(residual, free)
    size = len(base)
    tangent = [[0.0]*size for _ in range(size)]
    for column, (vertex, axis) in enumerate(dofs):
        step = data["tangent_step"]*max(1.0, abs(positions[vertex][axis]))
        trial = [list(row) for row in positions]
        trial[vertex][axis] += step
        trial_result = _evaluate(data, tuple(tuple(row) for row in trial), history,
                                 x_predictor, v_predictor, factor)
        sign = 1.0
        if trial_result[0].get("verdict") != ANSWER:
            trial[vertex][axis] -= 2.0*step
            trial_result = _evaluate(data, tuple(tuple(row) for row in trial), history,
                                     x_predictor, v_predictor, factor)
            sign = -1.0
        if trial_result[0].get("verdict") != ANSWER:
            raise _Invalid(f"cannot differentiate dynamic residual at vertex {vertex} axis {axis}")
        sampled = _flatten(trial_result[1], free)
        for row in range(size):
            derivative = ((sampled[row]-base[row])/step if sign > 0.0
                          else (base[row]-sampled[row])/step)
            tangent[row][column] = -derivative
    for index in range(size):
        tangent[index][index] += data["regularization"]
    values = _dense_solve(tangent, base)
    direction = [(0.0, 0.0, 0.0) for _ in positions]
    for value, (vertex, axis) in zip(values, dofs):
        row = list(direction[vertex])
        row[axis] = value
        direction[vertex] = tuple(row)
    return tuple(direction)


def _trial(positions: Sequence[Vec3], direction: Sequence[Vec3], scale: float,
           fixed_positions: Mapping[int, Vec3]) -> Tuple[Vec3, ...]:
    rows = [_add(positions[index], _mul(direction[index], scale))
            for index in range(len(positions))]
    for index, value in fixed_positions.items():
        rows[index] = value
    return tuple(rows)


def _kinetic(masses: Sequence[float], velocities: Sequence[Vec3]) -> float:
    return 0.5*sum(masses[index]*_dot(velocity, velocity)
                   for index, velocity in enumerate(velocities))


def _refusal(verdict: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": verdict, "reasons": [reason], **extra}


def solve(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Advance a shell through deterministic implicit Newmark time steps."""
    try:
        data = _parse(request)
    except _Invalid as error:
        return _refusal(INVALID_REQUEST, str(error), stage="VALIDATION")

    positions = list(data["positions"])
    velocities = list(data["velocities"])
    accelerations = list(data["accelerations"])
    for index, value in data["fixed_positions"].items():
        positions[index] = value
        velocities[index] = (0.0, 0.0, 0.0)
        accelerations[index] = (0.0, 0.0, 0.0)
    positions, velocities, accelerations = (tuple(positions), tuple(velocities),
                                             tuple(accelerations))
    history = copy.deepcopy(data["history"])
    initial_shell = _shell(data, positions, history)
    if initial_shell.get("verdict") != ANSWER:
        return {"verdict": initial_shell.get("verdict"),
                "reasons": list(initial_shell.get("reasons", ["initial shell refusal"])),
                "stage": "INITIAL_CONSTITUTIVE_EVALUATION"}
    initial_energy = (_kinetic(data["masses"], velocities)
                      + initial_shell["diagnostics"]["energy_j"]["total"])
    external_work = 0.0
    damping_dissipation = 0.0
    previous_factor = 0.0
    residual_ledger: List[Dict[str, Any]] = []
    energy_ledger: List[Dict[str, Any]] = []
    state_ledger: List[Dict[str, Any]] = []

    for step_index, factor in enumerate(data["factors"], 1):
        old_positions, old_velocities = positions, velocities
        x_predictor, v_predictor = _predict(data, positions, velocities, accelerations)
        candidate = list(x_predictor)
        for index, value in data["fixed_positions"].items():
            candidate[index] = value
        candidate = tuple(candidate)
        converged = False
        accepted_shell = None
        accepted_velocities = None
        accepted_accelerations = None
        last_reason = "maximum Newton iterations reached"
        target_force_norm, _ = _norm(tuple(_mul(force, factor)
                                           for force in data["forces"]), data["free"])
        tolerance = (data["absolute_tolerance"]
                     + data["relative_tolerance"]*target_force_norm)

        for iteration in range(data["max_iterations"] + 1):
            shell, residual, trial_velocities, trial_accelerations = _evaluate(
                data, candidate, history, x_predictor, v_predictor, factor)
            if shell.get("verdict") != ANSWER:
                return {"verdict": shell.get("verdict"),
                        "reasons": list(shell.get("reasons", ["shell refusal"])),
                        "stage": "DYNAMIC_CONSTITUTIVE_EVALUATION",
                        "failed_step": step_index, "failed_iteration": iteration,
                        "residual_ledger": residual_ledger,
                        "energy_ledger": energy_ledger}
            residual_l2, residual_max = _norm(residual, data["free"])
            record = {
                "step": step_index, "iteration": iteration,
                "time_s": step_index*data["dt"], "load_factor": factor,
                "residual_l2_n": residual_l2, "residual_max_n": residual_max,
                "tolerance_n": tolerance, "line_search_scale": 0.0,
                "accepted_displacement_l2_m": 0.0, "status": "EVALUATED",
            }
            residual_ledger.append(record)
            if residual_l2 <= tolerance:
                record["status"] = "CONVERGED"
                converged = True
                accepted_shell = shell
                accepted_velocities = trial_velocities
                accepted_accelerations = trial_accelerations
                break
            if iteration == data["max_iterations"]:
                last_reason = "maximum Newton iterations reached above residual tolerance"
                break
            try:
                direction = _direction(data, candidate, history, x_predictor,
                                       v_predictor, factor, residual)
            except _Invalid as error:
                last_reason = str(error)
                record["status"] = "TANGENT_FAILED"
                break
            direction_norm = math.sqrt(sum(value*value for index in data["free"]
                                           for value in direction[index]))
            if direction_norm <= data["displacement_tolerance"]:
                last_reason = "Newton displacement stagnated above residual tolerance"
                record["status"] = "STAGNATED"
                break
            accepted_trial = None
            scale = 1.0
            for reduction in range(data["reductions"] + 1):
                trial_positions = _trial(candidate, direction, scale,
                                         data["fixed_positions"])
                trial_result = _evaluate(data, trial_positions, history, x_predictor,
                                         v_predictor, factor)
                if trial_result[0].get("verdict") == ANSWER:
                    trial_l2, _ = _norm(trial_result[1], data["free"])
                    if trial_l2 <= (1.0-data["armijo"]*scale)*residual_l2:
                        accepted_trial = (trial_positions, scale, reduction, trial_l2)
                        break
                scale *= data["contraction"]
            if accepted_trial is None:
                last_reason = "line search found no admissible residual-decreasing step"
                record["status"] = "LINE_SEARCH_FAILED"
                break
            candidate, accepted_scale, reductions, _ = accepted_trial
            displacement = direction_norm*accepted_scale
            record.update({"line_search_scale": accepted_scale,
                           "line_search_reductions": reductions,
                           "accepted_displacement_l2_m": displacement,
                           "status": "STEP_ACCEPTED"})

        if not converged:
            return _refusal(
                NONCONVERGENCE, last_reason, stage="IMPLICIT_NEWMARK_NEWTON",
                failed_step=step_index, time_s=step_index*data["dt"],
                load_factor=factor, positions_m=[list(row) for row in positions],
                committed_history=copy.deepcopy(history),
                residual_ledger=residual_ledger, energy_ledger=energy_ledger,
                state_ledger=state_ledger,
                diagnostics={"numerical_residual_consistent_tangent": True,
                             "analytic_consistent_material_tangent": False,
                             "industrial_certification": False})

        assert accepted_shell is not None
        assert accepted_velocities is not None and accepted_accelerations is not None
        positions = candidate
        velocities = accepted_velocities
        accelerations = accepted_accelerations
        history = copy.deepcopy(accepted_shell["next_history"])
        current_force = tuple(_mul(force, factor) for force in data["forces"])
        old_force = tuple(_mul(force, previous_factor) for force in data["forces"])
        work_increment = 0.5*sum(
            _dot(_add(old_force[index], current_force[index]),
                 _sub(positions[index], old_positions[index]))
            for index in data["free"])
        external_work += work_increment
        damping_increment = data["dt"]*data["damping"]*sum(
            data["masses"][index]*0.5*(_dot(old_velocities[index], old_velocities[index])
                                      + _dot(velocities[index], velocities[index]))
            for index in data["free"])
        damping_dissipation += damping_increment
        kinetic = _kinetic(data["masses"], velocities)
        strain = accepted_shell["diagnostics"]["energy_j"]["total"]
        balance = kinetic + strain + damping_dissipation - initial_energy - external_work
        final_record = residual_ledger[-1]
        energy_ledger.append({
            "step": step_index, "time_s": step_index*data["dt"],
            "load_factor": factor, "kinetic_energy_j": kinetic,
            "strain_energy_j": strain, "external_work_increment_j": work_increment,
            "external_work_cumulative_j": external_work,
            "damping_dissipation_increment_j": damping_increment,
            "damping_dissipation_cumulative_j": damping_dissipation,
            "algorithmic_energy_balance_j": balance,
            "residual_l2_n": final_record["residual_l2_n"],
        })
        state_ledger.append({
            "step": step_index, "time_s": step_index*data["dt"],
            "load_factor": factor,
            "positions_m": [list(row) for row in positions],
            "velocities_m_s": [list(row) for row in velocities],
            "accelerations_m_s2": [list(row) for row in accelerations],
        })
        previous_factor = factor

    return {
        "verdict": ANSWER, "terminal_verdict": "CONVERGED",
        "solver": "IMPLICIT_NEWMARK_NUMERICAL_TANGENT_NEWTON",
        "tangent": "FINITE_DIFFERENCE_COMPLETE_DYNAMIC_RESIDUAL_CONSISTENT_NOT_ANALYTIC_MATERIAL_TANGENT",
        "time_s": data["steps"]*data["dt"],
        "positions_m": [list(row) for row in positions],
        "velocities_m_s": [list(row) for row in velocities],
        "accelerations_m_s2": [list(row) for row in accelerations],
        "history": copy.deepcopy(history),
        "residual_ledger": residual_ledger,
        "energy_ledger": energy_ledger,
        "state_ledger": state_ledger,
        "diagnostics": {
            "steps": data["steps"], "time_step_s": data["dt"],
            "newmark_beta": data["beta"], "newmark_gamma": data["gamma"],
            "mass_damping_per_s": data["damping"],
            "numerical_residual_consistent_tangent": True,
            "analytic_consistent_material_tangent": False,
            "industrial_certification": False,
        },
    }
