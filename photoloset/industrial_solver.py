# -*- coding: utf-8 -*-
"""Typed orchestration for the cross-structured cloth reference kernels.

This module connects numerical kernels; it does not turn their union into an
industrially validated solver.  Each stage keeps its own verdict and the
epistemic/provenance layer remains separate from numerical state.  Optional
shell corrections are proposals unless the caller explicitly commits them.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, Mapping, Sequence

from . import comfort_model
from . import cross_ccd
from . import cross_fluid
from . import cross_shell
from . import cross_xpbd
from . import material_calibration


ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_INDUSTRIAL_SOLVER_INPUT"
FAILED_STAGE = "UNKNOWN_INDUSTRIAL_SOLVER_STAGE"
SCHEMA = "garment.industrial-cloth-step.v1"


class _Invalid(ValueError):
    pass


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a finite SI number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise _Invalid(f"{name} must be finite" + (" and positive" if positive else ""))
    return result


def _vec3(value: Any, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must contain three SI components")
    return [_number(component, f"{name}[{axis}]")
            for axis, component in enumerate(value)]


def _area(points: Sequence[Sequence[float]], face: Sequence[int]) -> float:
    a, b, c = (points[int(index)] for index in face)
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    cross = (ab[1]*ac[2] - ab[2]*ac[1],
             ab[2]*ac[0] - ab[0]*ac[2],
             ab[0]*ac[1] - ab[1]*ac[0])
    return 0.5 * math.sqrt(math.fsum(value*value for value in cross))


def _masses(rest: Sequence[Sequence[float]], faces: Sequence[Sequence[int]],
            material_ids: Sequence[str], materials: Mapping[str, Mapping[str, Any]]) -> list[float]:
    masses = [0.0] * len(rest)
    if len(faces) != len(material_ids):
        raise _Invalid("one face_material_id is required per face")
    for face_index, (face, material_id) in enumerate(zip(faces, material_ids)):
        if (not isinstance(face, (list, tuple)) or len(face) != 3
                or any(isinstance(index, bool) or not isinstance(index, int)
                       or not 0 <= index < len(rest) for index in face)
                or len(set(face)) != 3):
            raise _Invalid(f"faces[{face_index}] is not a valid triangle")
        profile = materials.get(str(material_id))
        if not isinstance(profile, Mapping):
            raise _Invalid(f"XPBD material {material_id!r} is missing")
        density = _number(profile.get("areal_density_kg_m2"),
                          f"materials.xpbd.{material_id}.areal_density_kg_m2",
                          positive=True)
        share = _area(rest, face) * density / 3.0
        if share <= 0.0:
            raise _Invalid(f"faces[{face_index}] has zero rest area")
        for index in face:
            masses[index] += share
    if not masses or any(value <= 0.0 for value in masses):
        raise _Invalid("mesh has an isolated or massless vertex")
    return masses


def _mesh_edges(faces: Sequence[Sequence[int]]) -> list[list[int]]:
    edges = set()
    for face in faces:
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edges.add(tuple(sorted((int(a), int(b)))))
    return [list(edge) for edge in sorted(edges)]


def capabilities() -> Dict[str, Any]:
    """Describe implemented composition and the remaining industrial gaps."""
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "deterministic": True,
        "pipeline": ["material_calibration", "fluid_impulse", "xpbd_step",
                     "shell_residual", "ccd_contact_and_seam", "comfort_review"],
        "kernels": {
            "xpbd": cross_xpbd.capabilities(),
            "ccd": cross_ccd.capabilities(),
            "shell": cross_shell.capabilities(),
            "fluid": cross_fluid.capabilities(),
            "material_calibration": material_calibration.capabilities(),
            "comfort": comfort_model.capabilities(),
        },
        "industrial_completion": False,
        "not_implemented": [
            "global nonlinear shell FEM with consistent tangent",
            "production broad phase and exact symbolic CCD",
            "Navier-Stokes pressure projection or turbulence validation",
            "yarn, thread, needle and topology-changing stitch simulation",
            "experimentally validated seam failure and puckering",
            "medical or wearer-specific comfort prediction",
            "GPU execution of this integrated Python workflow",
        ],
        "cross_role": {
            "numerical": "typed local basis, state and same-old-state reduction",
            "epistemic": "measured, derived and proposed records remain separate",
            "solves_equations_by_itself": False,
        },
    }


def simulate(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run one explicitly configured integrated reference step.

    Required material layers are separate: ``materials.xpbd`` drives time
    integration, while optional ``materials.shell`` and ``materials.fluid``
    drive their own kernels.  No coefficient is copied between layers because
    those quantities have different dimensions and calibration contracts.
    """
    snapshot = copy.deepcopy(request)
    try:
        if not isinstance(request, Mapping):
            raise _Invalid("request must be an object")
        if request.get("schema") != SCHEMA:
            raise _Invalid(f"schema must be {SCHEMA}")
        rest_raw = request.get("rest_positions")
        faces = request.get("faces")
        material_ids = request.get("face_material_ids")
        layers = request.get("materials")
        if (not isinstance(rest_raw, (list, tuple)) or not rest_raw
                or not isinstance(faces, (list, tuple)) or not faces
                or not isinstance(material_ids, (list, tuple))
                or not isinstance(layers, Mapping)
                or not isinstance(layers.get("xpbd"), Mapping)):
            raise _Invalid("rest_positions, faces, face_material_ids and materials.xpbd are required")
        rest = [_vec3(value, f"rest_positions[{index}]")
                for index, value in enumerate(rest_raw)]
        state = request.get("state", {})
        if not isinstance(state, Mapping):
            raise _Invalid("state must be an object")
        positions_raw = state.get("positions", rest)
        velocities_raw = state.get("velocities", [[0.0, 0.0, 0.0] for _ in rest])
        if (not isinstance(positions_raw, (list, tuple))
                or not isinstance(velocities_raw, (list, tuple))
                or len(positions_raw) != len(rest) or len(velocities_raw) != len(rest)):
            raise _Invalid("state positions and velocities must match rest_positions")
        positions = [_vec3(value, f"state.positions[{index}]")
                     for index, value in enumerate(positions_raw)]
        velocities = [_vec3(value, f"state.velocities[{index}]")
                      for index, value in enumerate(velocities_raw)]
        dt = _number(request.get("time_step_s"), "time_step_s", positive=True)
        fixed_raw = request.get("fixed_vertices", [])
        if not isinstance(fixed_raw, (list, tuple)):
            raise _Invalid("fixed_vertices must be a sequence")
        fixed = set()
        for value in fixed_raw:
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 0 <= value < len(rest)):
                raise _Invalid("fixed_vertices contains an invalid index")
            fixed.add(value)
        xpbd_materials = layers["xpbd"]
        masses = _masses(rest, faces, material_ids, xpbd_materials)
        stages: Dict[str, Any] = {}

        calibration = None
        if "material_measurements" in request:
            calibration = material_calibration.calibrate(request["material_measurements"])
            stages["material_calibration"] = calibration
            if calibration.get("verdict") != ANSWER:
                return _refusal(FAILED_STAGE, "material calibration refused",
                                failed_stage="material_calibration", stages=stages,
                                upstream=calibration, immutable_input_snapshot=snapshot)
        else:
            stages["material_calibration"] = {"verdict": "SKIPPED_NOT_REQUESTED"}

        coupled_velocities = copy.deepcopy(velocities)
        if "fluid" in request:
            fluid_materials = layers.get("fluid")
            if not isinstance(fluid_materials, Mapping):
                raise _Invalid("materials.fluid is required when fluid is requested")
            fluid = cross_fluid.couple(
                positions, velocities, faces, face_material_ids=material_ids,
                materials=fluid_materials, fluid=request["fluid"], time_step_s=dt)
            stages["fluid"] = fluid
            if fluid.get("verdict") != ANSWER:
                return _refusal(FAILED_STAGE, "fluid coupling refused",
                                failed_stage="fluid", stages=stages, upstream=fluid,
                                immutable_input_snapshot=snapshot)
            for index, impulse in enumerate(fluid["cloth"]["vertex_impulses_n_s"]):
                if index not in fixed:
                    coupled_velocities[index] = [
                        velocities[index][axis] + float(impulse[axis]) / masses[index]
                        for axis in range(3)]
        else:
            stages["fluid"] = {"verdict": "SKIPPED_NOT_REQUESTED"}

        xpbd_options = request.get("xpbd", {})
        if not isinstance(xpbd_options, Mapping):
            raise _Invalid("xpbd must be an object")
        allowed_xpbd = {
            "face_warp_directions", "gravity_m_s2", "steps", "solver_iterations",
            "jacobi_relaxation", "max_displacement_fraction", "max_substeps",
            "convergence_tolerance", "speed_tolerance_m_s", "stable_steps_required",
        }
        unknown_xpbd = sorted(set(xpbd_options) - allowed_xpbd)
        if unknown_xpbd:
            raise _Invalid(f"unsupported xpbd settings: {unknown_xpbd}")
        xpbd = cross_xpbd.simulate(
            rest, faces, face_material_ids=material_ids, materials=xpbd_materials,
            initial_positions=positions, initial_velocities=coupled_velocities,
            fixed_vertices=sorted(fixed), seams=request.get("xpbd_seams", ()),
            time_step_s=dt, **dict(xpbd_options))
        stages["xpbd"] = xpbd
        if xpbd.get("verdict") != ANSWER:
            return _refusal(FAILED_STAGE, "XPBD integration refused",
                            failed_stage="xpbd", stages=stages, upstream=xpbd,
                            immutable_input_snapshot=snapshot)
        proposed = [list(vertex["position_m"]) for vertex in xpbd["state"]["vertices"]]
        proposed_velocities = [list(vertex["velocity_m_s"])
                               for vertex in xpbd["state"]["vertices"]]

        shell_request = request.get("shell")
        shell_history = state.get("shell_history")
        if shell_request is not None:
            if not isinstance(shell_request, Mapping):
                raise _Invalid("shell must be an object")
            shell_materials = layers.get("shell")
            if not isinstance(shell_materials, Mapping):
                raise _Invalid("materials.shell is required when shell is requested")
            shell = cross_shell.solve(
                rest, proposed, faces, face_material_ids=material_ids,
                materials=shell_materials, history=shell_history, time_step_s=dt)
            stages["shell"] = shell
            if shell.get("verdict") != ANSWER:
                return _refusal(FAILED_STAGE, "shell assembly refused",
                                failed_stage="shell", stages=stages, upstream=shell,
                                immutable_input_snapshot=snapshot)
            apply_shell = shell_request.get("apply_correction", False)
            if not isinstance(apply_shell, bool):
                raise _Invalid("shell.apply_correction must be boolean")
            shell["correction_committed"] = apply_shell
            if apply_shell:
                for index, correction in enumerate(shell["jacobi_corrections_m"]):
                    if index not in fixed:
                        proposed[index] = [proposed[index][axis] + float(correction[axis])
                                           for axis in range(3)]
        else:
            stages["shell"] = {"verdict": "SKIPPED_NOT_REQUESTED"}

        ccd_request = request.get("ccd")
        if ccd_request is not None:
            if not isinstance(ccd_request, Mapping):
                raise _Invalid("ccd must be an object")
            required_ccd = ("thickness_m", "friction_static", "friction_dynamic")
            missing_ccd = [key for key in required_ccd if key not in ccd_request]
            if missing_ccd:
                raise _Invalid(f"ccd settings are missing {missing_ccd}")
            edges = ccd_request.get("edges", _mesh_edges(faces))
            ccd = cross_ccd.solve(
                positions, proposed, faces, edges=edges,
                seams=ccd_request.get("seams", ()),
                thickness_m=ccd_request["thickness_m"],
                friction_static=ccd_request["friction_static"],
                friction_dynamic=ccd_request["friction_dynamic"], time_step_s=dt)
            stages["ccd"] = ccd
            if ccd.get("verdict") != ANSWER:
                return _refusal(FAILED_STAGE, "continuous contact/seam solve refused",
                                failed_stage="ccd", stages=stages, upstream=ccd,
                                immutable_input_snapshot=snapshot)
            before_contact = proposed
            proposed = [list(value) for value in ccd["positions"]]
            proposed_velocities = [
                ([0.0, 0.0, 0.0] if index in fixed else [
                    proposed_velocities[index][axis]
                    + (proposed[index][axis] - before_contact[index][axis]) / dt
                    for axis in range(3)])
                for index in range(len(proposed))]
        else:
            stages["ccd"] = {"verdict": "SKIPPED_NOT_REQUESTED"}

        if "comfort_observations" in request:
            record = request["comfort_observations"]
            if (calibration is not None and isinstance(record, Mapping)
                    and record.get("calibration_digest") != calibration.get("calibration_digest")):
                return _refusal(FAILED_STAGE,
                                "comfort observations are not bound to this calibration",
                                failed_stage="comfort", stages=stages,
                                expected_calibration_digest=calibration.get("calibration_digest"),
                                immutable_input_snapshot=snapshot)
            comfort = comfort_model.evaluate(record)
            stages["comfort"] = comfort
            if comfort.get("verdict") != comfort_model.REVIEW:
                return _refusal(FAILED_STAGE, "comfort screening refused",
                                failed_stage="comfort", stages=stages, upstream=comfort,
                                immutable_input_snapshot=snapshot)
        else:
            stages["comfort"] = {"verdict": "SKIPPED_NOT_REQUESTED"}

        return {
            "verdict": ANSWER,
            "schema": "garment.industrial-cloth-result.v1",
            "state": {
                "positions": proposed,
                "velocities": proposed_velocities,
                "shell_history": (stages["shell"].get("next_history")
                                  if stages["shell"].get("verdict") == ANSWER
                                  else shell_history),
            },
            "stages": stages,
            "stage_order": ["material_calibration", "fluid", "xpbd", "shell",
                            "ccd", "comfort"],
            "truth_contract": {
                "numerical_results_are_measurements": False,
                "derived_and_measured_are_averaged": False,
                "shell_correction_requires_explicit_commit": True,
                "comfort_success_requires_review": True,
            },
            "industrial_completion": False,
            "capabilities": capabilities(),
            "immutable_input_snapshot": snapshot,
        }
    except (KeyError, TypeError, ValueError, IndexError, _Invalid) as error:
        return _refusal(INVALID_INPUT, str(error),
                        immutable_input_snapshot=snapshot,
                        capabilities=capabilities())


__all__ = ["ANSWER", "FAILED_STAGE", "INVALID_INPUT", "SCHEMA",
           "capabilities", "simulate"]
