# -*- coding: utf-8 -*-
"""Deterministic global quasi-Newton driver for ``cross_shell``.

The implementation solves static force balance using the constitutive
module's same-old-state residual and positive Jacobi diagonal.  It provides
load increments, fixed/prescribed vertices, residual line search, convergence
history, and typed non-convergence.  The diagonal is *not* a consistent
tangent, so this is a reference nonlinear shell driver rather than an
industrial-certified FEM package.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from photoloset import cross_shell


Vec3 = Tuple[float, float, float]
ANSWER = "ANSWER"
INVALID_REQUEST = "UNKNOWN_NONLINEAR_SHELL_INVALID_REQUEST"
NONCONVERGENCE = "UNKNOWN_NONLINEAR_SHELL_NONCONVERGENCE"
_EPS = 1.0e-15

__all__ = ("capabilities", "solve")


class _Invalid(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Return an honest declaration of this global solver's scope."""
    return {
        "verdict": ANSWER,
        "backend": "cpu_reference_python_standard_library",
        "solver": "numerical_tangent_quasi_newton_with_residual_line_search",
        "constitutive_backend": "photoloset.cross_shell",
        "features": {
            "global_static_equilibrium": True,
            "nonlinear_iterations": True,
            "deterministic": True,
            "same_old_state_constitutive_evaluation": True,
            "numerical_residual_tangent": True,
            "jacobi_diagonal_regularization": True,
            "residual_line_search": True,
            "fixed_vertices": True,
            "prescribed_positions": True,
            "load_increments": True,
            "convergence_history": True,
            "typed_nonconvergence": True,
            "plastic_history_commit_after_increment": True,
            "consistent_tangent_matrix": False,
            "full_newton": False,
            "dynamic_time_integration": False,
            "contact_or_ccd": False,
            "arc_length_or_buckling_continuation": False,
            "industrial_certification": False,
            "gpu": False,
        },
        "limitations": [
            "uses a finite-difference residual tangent regularized by cross_shell's Jacobi diagonal",
            "the numerical tangent is not an analytic consistent material tangent",
            "line search minimizes equilibrium residual rather than an exact global potential",
            "force-controlled load scaling only; no arc-length continuation",
            "material history is committed only after each converged load increment",
            "no industrial validation or certification is claimed",
        ],
    }


def _number(value: Any, name: str, *, low: Optional[float] = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a finite number in SI units")
    result = float(value)
    if not math.isfinite(result):
        raise _Invalid(f"{name} must be finite")
    if low is not None and (result <= low if strict else result < low):
        relation = ">" if strict else ">="
        raise _Invalid(f"{name} must be {relation} {low}")
    return result


def _integer(value: Any, name: str, *, low: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise _Invalid(f"{name} must be an integer >= {low}")
    return value


def _vec3(value: Any, name: str) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must contain three finite SI components")
    return tuple(_number(v, f"{name}[{axis}]")
                 for axis, v in enumerate(value))  # type: ignore[return-value]


def _vectors(value: Any, name: str, *, length: Optional[int] = None) -> Tuple[Vec3, ...]:
    if not isinstance(value, (list, tuple)):
        raise _Invalid(f"{name} must be a sequence")
    result = tuple(_vec3(item, f"{name}[{i}]") for i, item in enumerate(value))
    if length is not None and len(result) != length:
        raise _Invalid(f"{name} must contain {length} vectors")
    return result


def _faces(value: Any, vertex_count: int) -> Tuple[Tuple[int, int, int], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise _Invalid("faces must be a nonempty sequence")
    result = []
    for index, face in enumerate(value):
        if (not isinstance(face, (list, tuple)) or len(face) != 3
                or any(isinstance(v, bool) or not isinstance(v, int)
                       or not 0 <= v < vertex_count for v in face)
                or len(set(face)) != 3):
            raise _Invalid(f"faces[{index}] must contain three distinct valid indices")
        result.append(tuple(int(v) for v in face))
    return tuple(result)


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _mul(a: Vec3, scale: float) -> Vec3:
    return a[0]*scale, a[1]*scale, a[2]*scale


def _norm(rows: Sequence[Vec3], free: Sequence[int]) -> Tuple[float, float]:
    squares = 0.0
    maximum = 0.0
    for index in free:
        row_norm = math.sqrt(sum(value*value for value in rows[index]))
        squares += row_norm*row_norm
        maximum = max(maximum, row_norm)
    return math.sqrt(squares), maximum


def _displacement_norm(direction: Sequence[Vec3], free: Sequence[int],
                       scale: float) -> float:
    return math.sqrt(sum((scale*value)**2
                         for index in free for value in direction[index]))


def _parse_boundary(raw: Any, vertex_count: int,
                    initial: Sequence[Vec3]) -> Tuple[Tuple[int, ...], Dict[int, Vec3]]:
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise _Invalid("boundary_conditions must be a mapping")
    fixed_raw = raw.get("fixed_vertices", ())
    if not isinstance(fixed_raw, (list, tuple)):
        raise _Invalid("boundary_conditions.fixed_vertices must be a sequence")
    fixed = set()
    for value in fixed_raw:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < vertex_count:
            raise _Invalid("fixed_vertices contains an invalid vertex index")
        fixed.add(value)
    prescribed_raw = raw.get("prescribed_positions_m", {})
    if not isinstance(prescribed_raw, Mapping):
        raise _Invalid("prescribed_positions_m must be a mapping of vertex index to position")
    prescribed: Dict[int, Vec3] = {}
    for raw_index, position in prescribed_raw.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            raise _Invalid("prescribed_positions_m keys must be vertex indices")
        if isinstance(raw_index, bool) or not 0 <= index < vertex_count:
            raise _Invalid("prescribed_positions_m contains an invalid vertex index")
        prescribed[index] = _vec3(position, f"prescribed_positions_m[{index}]")
        fixed.add(index)
    for index in fixed:
        prescribed.setdefault(index, initial[index])
    return tuple(sorted(fixed)), prescribed


def _parse_request(request: Any) -> Dict[str, Any]:
    if not isinstance(request, Mapping):
        raise _Invalid("request must be a mapping")
    rest = _vectors(request.get("rest_positions"), "rest_positions")
    if not rest:
        raise _Invalid("rest_positions must not be empty")
    initial = _vectors(request.get("initial_positions", rest), "initial_positions",
                       length=len(rest))
    faces = _faces(request.get("faces"), len(rest))
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
        if not isinstance(history, (list, tuple)) or len(history) != len(faces):
            raise _Invalid("history must contain one mapping per face")
        if any(not isinstance(entry, Mapping) for entry in history):
            raise _Invalid("each history entry must be a mapping")
        history = copy.deepcopy(list(history))
    time_step = _number(request.get("time_step_s"), "time_step_s",
                        low=0.0, strict=True)

    loads_raw = request.get("loads", {})
    if not isinstance(loads_raw, Mapping):
        raise _Invalid("loads must be a mapping")
    forces = _vectors(loads_raw.get("nodal_forces_n", [(0.0, 0.0, 0.0)]*len(rest)),
                      "loads.nodal_forces_n", length=len(rest))
    increments = _integer(loads_raw.get("increments", 1), "loads.increments", low=1)

    fixed, prescribed = _parse_boundary(request.get("boundary_conditions"), len(rest), initial)
    free = tuple(index for index in range(len(rest)) if index not in set(fixed))
    if not free:
        raise _Invalid("at least one free vertex is required for a global solve")

    solver_raw = request.get("solver", {})
    if not isinstance(solver_raw, Mapping):
        raise _Invalid("solver must be a mapping")
    max_iterations = _integer(solver_raw.get("max_iterations", 80),
                              "solver.max_iterations", low=1)
    absolute_tolerance = _number(solver_raw.get("absolute_residual_tolerance_n", 1.0e-6),
                                 "solver.absolute_residual_tolerance_n", low=0.0,
                                 strict=True)
    relative_tolerance = _number(solver_raw.get("relative_residual_tolerance", 1.0e-8),
                                 "solver.relative_residual_tolerance", low=0.0)
    displacement_tolerance = _number(solver_raw.get("displacement_tolerance_m", 1.0e-10),
                                     "solver.displacement_tolerance_m", low=0.0,
                                     strict=True)
    relaxation = _number(solver_raw.get("relaxation", 0.8),
                         "solver.relaxation", low=0.0, strict=True)
    if relaxation > 1.0:
        raise _Invalid("solver.relaxation must be <= 1")
    reductions = _integer(solver_raw.get("line_search_reductions", 14),
                          "solver.line_search_reductions", low=0)
    contraction = _number(solver_raw.get("line_search_contraction", 0.5),
                          "solver.line_search_contraction", low=0.0, strict=True)
    if contraction >= 1.0:
        raise _Invalid("solver.line_search_contraction must be < 1")
    armijo = _number(solver_raw.get("line_search_armijo", 1.0e-4),
                     "solver.line_search_armijo", low=0.0, strict=True)
    if armijo >= 1.0:
        raise _Invalid("solver.line_search_armijo must be < 1")
    tangent_step = _number(solver_raw.get("tangent_difference_step_m", 1.0e-7),
                           "solver.tangent_difference_step_m", low=0.0,
                           strict=True)
    regularization = _number(solver_raw.get("jacobi_regularization_ratio", 1.0e-10),
                             "solver.jacobi_regularization_ratio", low=0.0,
                             strict=True)

    return {
        "rest": rest, "initial": initial, "faces": faces,
        "material_ids": tuple(material_ids), "materials": copy.deepcopy(dict(materials)),
        "history": history, "time_step": time_step, "forces": forces,
        "increments": increments, "fixed": fixed, "prescribed": prescribed,
        "free": free, "max_iterations": max_iterations,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "displacement_tolerance": displacement_tolerance,
        "relaxation": relaxation, "reductions": reductions,
        "contraction": contraction, "armijo": armijo,
        "tangent_step": tangent_step, "regularization": regularization,
    }


def _constitutive(data: Mapping[str, Any], positions: Sequence[Vec3],
                  history: Any) -> Dict[str, Any]:
    return cross_shell.solve(
        data["rest"], positions, data["faces"],
        face_material_ids=data["material_ids"], materials=data["materials"],
        history=history, time_step_s=data["time_step"])


def _equilibrium(shell: Mapping[str, Any], forces: Sequence[Vec3],
                 load_factor: float, fixed: Sequence[int]) -> Tuple[Vec3, ...]:
    fixed_set = set(fixed)
    rows = []
    for index, internal in enumerate(shell["residuals_n"]):
        value = _add(_vec3(internal, f"cross_shell.residuals_n[{index}]"),
                     _mul(forces[index], load_factor))
        rows.append((0.0, 0.0, 0.0) if index in fixed_set else value)
    return tuple(rows)


def _trial_positions(positions: Sequence[Vec3], direction: Sequence[Vec3],
                     scale: float, prescribed: Mapping[int, Vec3]) -> Tuple[Vec3, ...]:
    trial = [_add(position, _mul(direction[index], scale))
             for index, position in enumerate(positions)]
    for index, value in prescribed.items():
        trial[index] = value
    return tuple(trial)


def _refusal(verdict: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": verdict, "reasons": [reason], **extra}


def _dof_rows(rows: Sequence[Vec3], free: Sequence[int]) -> List[float]:
    return [rows[index][axis] for index in free for axis in range(3)]


def _solve_dense(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> List[float]:
    """Deterministic partial-pivot Gaussian elimination."""
    size = len(rhs)
    augmented = [list(matrix[row]) + [float(rhs[row])] for row in range(size)]
    scale = max((abs(value) for row in matrix for value in row), default=0.0)
    threshold = max(_EPS, scale*1.0e-14)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: (abs(augmented[row][column]), -row))
        if abs(augmented[pivot][column]) <= threshold:
            raise _Invalid("numerical tangent is singular after Jacobi regularization")
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for entry in range(column, size + 1):
            augmented[column][entry] /= divisor
        for row in range(column + 1, size):
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for entry in range(column, size + 1):
                augmented[row][entry] -= factor*augmented[column][entry]
    solution = [0.0]*size
    for row in range(size - 1, -1, -1):
        solution[row] = augmented[row][size] - sum(
            augmented[row][column]*solution[column]
            for column in range(row + 1, size))
    if not all(math.isfinite(value) for value in solution):
        raise _Invalid("numerical tangent solve produced a non-finite direction")
    return solution


def _quasi_newton_direction(data: Mapping[str, Any], positions: Sequence[Vec3],
                            history: Any, shell: Mapping[str, Any],
                            total: Sequence[Vec3], load_factor: float) -> Tuple[Vec3, ...]:
    """Finite-difference ``-d(residual)/dx`` and solve ``K dx = residual``."""
    free = data["free"]
    base = _dof_rows(total, free)
    size = len(base)
    tangent = [[0.0]*size for _ in range(size)]
    dofs = [(vertex, axis) for vertex in free for axis in range(3)]
    for column, (vertex, axis) in enumerate(dofs):
        step = data["tangent_step"]*max(1.0, abs(positions[vertex][axis]))
        trial = [list(row) for row in positions]
        trial[vertex][axis] += step
        trial_positions = tuple(tuple(row) for row in trial)
        trial_shell = _constitutive(data, trial_positions, history)
        sign = 1.0
        if trial_shell.get("verdict") != ANSWER:
            trial[vertex][axis] -= 2.0*step
            trial_positions = tuple(tuple(row) for row in trial)
            trial_shell = _constitutive(data, trial_positions, history)
            sign = -1.0
        if trial_shell.get("verdict") != ANSWER:
            raise _Invalid(f"cannot differentiate residual at vertex {vertex} axis {axis}")
        trial_total = _equilibrium(trial_shell, data["forces"], load_factor,
                                   data["fixed"])
        sampled = _dof_rows(trial_total, free)
        for row in range(size):
            derivative = ((sampled[row] - base[row])/step if sign > 0.0
                          else (base[row] - sampled[row])/step)
            tangent[row][column] = -derivative
    diagonals = shell["jacobi_diagonal_n_m"]
    for diagonal_index, (vertex, _axis) in enumerate(dofs):
        jacobi = _number(diagonals[vertex], f"jacobi_diagonal_n_m[{vertex}]",
                          low=0.0, strict=True)
        tangent[diagonal_index][diagonal_index] += data["regularization"]*jacobi
    solution = _solve_dense(tangent, base)
    direction = [(0.0, 0.0, 0.0) for _ in positions]
    for value, (vertex, axis) in zip(solution, dofs):
        row = list(direction[vertex])
        row[axis] = data["relaxation"]*value
        direction[vertex] = tuple(row)
    return tuple(direction)


def solve(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Solve deterministic static shell equilibrium for a typed request.

    Request fields are ``rest_positions``, optional ``initial_positions``,
    ``faces``, ``face_material_ids``, ``materials``, optional ``history``,
    ``time_step_s``, ``loads``, ``boundary_conditions``, and ``solver``.
    Inputs are copied and never mutated.
    """
    try:
        data = _parse_request(request)
    except _Invalid as error:
        return _refusal(INVALID_REQUEST, str(error), stage="VALIDATION")

    positions = list(data["initial"])
    for index, value in data["prescribed"].items():
        positions[index] = value
    positions = tuple(positions)
    committed_history = copy.deepcopy(data["history"])
    convergence_history: List[Dict[str, Any]] = []
    increment_summaries: List[Dict[str, Any]] = []
    final_shell: Optional[Dict[str, Any]] = None
    last_total: Optional[Tuple[Vec3, ...]] = None
    previous_step_norm = 0.0

    for increment in range(1, data["increments"] + 1):
        load_factor = increment / data["increments"]
        target_force_norm, _ = _norm(
            tuple(_mul(force, load_factor) for force in data["forces"]), data["free"])
        tolerance = data["absolute_tolerance"] + data["relative_tolerance"]*target_force_norm
        increment_start = positions
        converged = False
        accepted_steps = 0
        last_reason = "maximum iterations reached"

        for iteration in range(data["max_iterations"] + 1):
            shell = _constitutive(data, positions, committed_history)
            if shell.get("verdict") != ANSWER:
                return {
                    "verdict": shell.get("verdict", INVALID_REQUEST),
                    "reasons": list(shell.get("reasons", ["cross_shell refused evaluation"])),
                    "stage": "CONSTITUTIVE_EVALUATION",
                    "failed_increment": increment,
                    "failed_iteration": iteration,
                    "positions_m": [list(row) for row in positions],
                    "convergence_history": convergence_history,
                }
            try:
                total = _equilibrium(shell, data["forces"], load_factor, data["fixed"])
            except _Invalid as error:
                return _refusal(INVALID_REQUEST, str(error), stage="CONSTITUTIVE_OUTPUT")
            residual_l2, residual_max = _norm(total, data["free"])
            record = {
                "increment": increment,
                "iteration": iteration,
                "load_factor": load_factor,
                "residual_l2_n": residual_l2,
                "residual_max_n": residual_max,
                "accepted_step_l2_m": 0.0,
                "line_search_scale": 0.0,
                "status": "EVALUATED",
            }
            convergence_history.append(record)
            final_shell = shell
            last_total = total
            if residual_l2 <= tolerance:
                record["status"] = "CONVERGED"
                converged = True
                committed_history = copy.deepcopy(shell["next_history"])
                increment_summaries.append({
                    "increment": increment,
                    "load_factor": load_factor,
                    "iterations": iteration,
                    "accepted_steps": accepted_steps,
                    "residual_l2_n": residual_l2,
                    "tolerance_n": tolerance,
                    "displacement_from_increment_start_m": math.sqrt(sum(
                        (positions[i][axis] - increment_start[i][axis])**2
                        for i in data["free"] for axis in range(3))),
                })
                break
            if iteration == data["max_iterations"]:
                last_reason = "maximum iterations reached before residual tolerance"
                break

            try:
                direction = _quasi_newton_direction(
                    data, positions, committed_history, shell, total, load_factor)
            except (IndexError, _Invalid) as error:
                last_reason = str(error)
                record["status"] = "TANGENT_FAILED"
                break

            full_step_norm = _displacement_norm(direction, data["free"], 1.0)
            if full_step_norm <= data["displacement_tolerance"]:
                last_reason = "quasi-Newton step stagnated above residual tolerance"
                record["status"] = "STAGNATED"
                previous_step_norm = full_step_norm
                break

            accepted = None
            scale = 1.0
            for reduction in range(data["reductions"] + 1):
                trial_positions = _trial_positions(positions, direction, scale,
                                                   data["prescribed"])
                trial_shell = _constitutive(data, trial_positions, committed_history)
                if trial_shell.get("verdict") == ANSWER:
                    trial_total = _equilibrium(trial_shell, data["forces"],
                                               load_factor, data["fixed"])
                    trial_l2, _ = _norm(trial_total, data["free"])
                    if trial_l2 <= (1.0 - data["armijo"]*scale)*residual_l2:
                        accepted = (trial_positions, trial_shell, trial_total,
                                    trial_l2, scale, reduction)
                        break
                scale *= data["contraction"]
            if accepted is None:
                last_reason = "residual line search found no admissible decreasing step"
                record["status"] = "LINE_SEARCH_FAILED"
                break
            positions, final_shell, last_total, _, accepted_scale, reductions = accepted
            step_norm = _displacement_norm(direction, data["free"], accepted_scale)
            previous_step_norm = step_norm
            accepted_steps += 1
            record.update({
                "accepted_step_l2_m": step_norm,
                "line_search_scale": accepted_scale,
                "line_search_reductions": reductions,
                "status": "STEP_ACCEPTED",
            })

        if not converged:
            return _refusal(
                NONCONVERGENCE, last_reason,
                stage="GLOBAL_EQUILIBRIUM",
                failed_increment=increment,
                load_factor=load_factor,
                positions_m=[list(row) for row in positions],
                committed_history=copy.deepcopy(committed_history),
                convergence_history=convergence_history,
                increment_summaries=increment_summaries,
                diagnostics={
                    "last_step_l2_m": previous_step_norm,
                    "consistent_tangent_matrix": False,
                    "industrial_certification": False,
                },
            )

    assert final_shell is not None and last_total is not None
    reactions = []
    fixed_set = set(data["fixed"])
    # Re-evaluate full equilibrium force because free-only helper zeroed fixed rows.
    for index, internal in enumerate(final_shell["residuals_n"]):
        total = _add(_vec3(internal, f"residuals_n[{index}]"), data["forces"][index])
        reactions.append(list(_mul(total, -1.0)) if index in fixed_set
                         else [0.0, 0.0, 0.0])
    final_l2, final_max = _norm(last_total, data["free"])
    return {
        "verdict": ANSWER,
        "terminal_verdict": "CONVERGED",
        "solver": "NUMERICAL_TANGENT_QUASI_NEWTON",
        "tangent": "FINITE_DIFFERENCE_RESIDUAL_REGULARIZED_BY_JACOBI_NOT_ANALYTIC_CONSISTENT",
        "positions_m": [list(row) for row in positions],
        "history": copy.deepcopy(committed_history),
        "reaction_forces_n": reactions,
        "convergence_history": convergence_history,
        "increment_summaries": increment_summaries,
        "diagnostics": {
            "load_increments": data["increments"],
            "final_residual_l2_n": final_l2,
            "final_residual_max_n": final_max,
            "fixed_vertices": list(data["fixed"]),
            "constitutive_model": final_shell.get("model"),
            "consistent_tangent_matrix": False,
            "industrial_certification": False,
        },
    }
