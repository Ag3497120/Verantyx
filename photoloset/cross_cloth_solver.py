# -*- coding: utf-8 -*-
"""Integrated cloth stepping over the mesoscopic six-arm cross data format.

This module stacks three independently testable stages; it never blends their
verdicts into a vote::

    indexed mesh -> cross_lattice -> cross_forces -> cross_constraints

The cross is a numerical/data structure, not a claim about atoms.  SI units
are required throughout.  Material and aerodynamic values are explicit so an
uncalibrated coefficient cannot acquire the appearance of a measurement.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence

from . import cross_constraints as _constraints
from . import cross_forces as _forces
from . import cross_lattice as _lattice


ANSWER = "ANSWER"
BAD_INPUT = "UNKNOWN_CROSS_SOLVER_INPUT"
NO_MATERIAL = "UNKNOWN_CROSS_SOLVER_MATERIAL"


def _unknown(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def _finite(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number in SI units")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return result


def _profile(value: Mapping[str, Any], name: str) -> Dict[str, float]:
    required = (
        "areal_density_kg_m2", "warp_stiffness_n_m",
        "weft_stiffness_n_m", "shear_stiffness_n_m",
        "bending_stiffness_n_m", "damping_ratio",
        "drag_coefficient", "lift_coefficient",
    )
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError(f"material {name} lacks {missing}")
    out = {key: _finite(value[key], f"materials.{name}.{key}")
           for key in required}
    if out["areal_density_kg_m2"] <= 0.0:
        raise ValueError(f"materials.{name}.areal_density_kg_m2 must be positive")
    if not 0.0 <= out["damping_ratio"] <= 1.0:
        raise ValueError(f"materials.{name}.damping_ratio must be in [0,1]")
    if any(out[key] < 0.0 for key in required if key != "areal_density_kg_m2"):
        raise ValueError(f"material {name} contains a negative coefficient")
    return out


def _triangle_area(vertices: Sequence[Sequence[float]], face: Sequence[int]) -> float:
    a, b, c = (vertices[int(index)] for index in face)
    ab = tuple(float(b[i]) - float(a[i]) for i in range(3))
    ac = tuple(float(c[i]) - float(a[i]) for i in range(3))
    cross = (ab[1]*ac[2] - ab[2]*ac[1],
             ab[2]*ac[0] - ab[0]*ac[2],
             ab[0]*ac[1] - ab[1]*ac[0])
    return 0.5 * math.sqrt(sum(component * component for component in cross))


def _force_lattice(lattice: Mapping[str, Any], profiles: Mapping[str, Dict[str, float]],
                   fixed: set[int]) -> Dict[str, Any]:
    nodes = {
        str(vertex["vertex_id"]): {
            "position_m": list(vertex["position_m"]),
            "velocity_m_s": list(vertex["velocity_m_s"]),
            "mass_kg": float(vertex["mass_kg"]),
            "fixed": int(vertex["vertex_id"]) in fixed,
        }
        for vertex in lattice["vertices"]
    }
    links = []
    for link in lattice["links"]:
        ids = list(link["material_ids"])
        if len(ids) != 1:
            raise ValueError(
                "a force link crosses material ids; represent that interface as a seam")
        profile = profiles[ids[0]]
        kind = {"bias": "shear", "bending": "bend"}.get(link["kind"], link["kind"])
        stiffness_key = {
            "warp": "warp_stiffness_n_m", "weft": "weft_stiffness_n_m",
            "shear": "shear_stiffness_n_m", "bend": "bending_stiffness_n_m",
        }[kind]
        stiffness = profile[stiffness_key]
        if kind == "bend":
            stiffness /= max(float(link["rest_length_m"]) ** 2, 1.0e-12)
        a, b = (str(index) for index in link["vertices"])
        ma, mb = nodes[a]["mass_kg"], nodes[b]["mass_kg"]
        reduced_mass = ma * mb / (ma + mb)
        damping = 2.0 * profile["damping_ratio"] * math.sqrt(
            max(stiffness, 0.0) * reduced_mass)
        links.append({
            "a": a, "b": b, "kind": kind,
            "rest_length_m": float(link["rest_length_m"]),
            "material": {stiffness_key: stiffness,
                         "damping_n_s_m": damping},
        })
    faces = []
    for face in lattice["faces"]:
        profile = profiles[face["material_id"]]
        faces.append({
            "nodes": [str(index) for index in face["vertices"]],
            "material": {"drag_coefficient": profile["drag_coefficient"],
                         "lift_coefficient": profile["lift_coefficient"]},
        })
    return {"nodes": nodes, "links": links, "faces": faces}


def _constraint_state(force_lattice: Mapping[str, Any],
                      faces: Sequence[Sequence[int]], layers: Sequence[int]) -> Dict[str, Any]:
    return {
        "vertices": [{
            "position": list(force_lattice["nodes"][str(index)]["position_m"]),
            "previous_position": list(force_lattice["nodes"][str(index)]["position_m"]),
            "inverse_mass": (0.0 if force_lattice["nodes"][str(index)]["fixed"]
                             else 1.0 / force_lattice["nodes"][str(index)]["mass_kg"]),
            "layer": int(layers[index]),
        } for index in range(len(force_lattice["nodes"]))],
        "triangles": [list(face) for face in faces],
    }


def simulate(vertices: Sequence[Sequence[float]], faces: Sequence[Sequence[int]], *,
             face_material_ids: Sequence[str],
             materials: Mapping[str, Mapping[str, Any]],
             fixed_vertices: Sequence[int] = (),
             vertex_layers: Optional[Sequence[int]] = None,
             constraints: Optional[Mapping[str, Any]] = None,
             environment: Optional[Mapping[str, Any]] = None,
             time_step_s: float = 1.0 / 120.0, steps: int = 120,
             constraint_iterations: int = 12,
             speed_tolerance_m_s: float = 1.0e-3,
             stable_steps_required: int = 5) -> Dict[str, Any]:
    """Advance a cross cloth under forces, wind, contact, seams and layers.

    ``ANSWER`` means the requested finite trajectory was computed.  Equilibrium
    is reported separately as ``terminal_verdict=CONVERGED`` or ``IN_PROGRESS``;
    an animation need not be at rest to be a valid simulation result.
    """
    try:
        if (not isinstance(steps, int) or isinstance(steps, bool) or steps < 1
                or not isinstance(stable_steps_required, int)
                or stable_steps_required < 1):
            raise ValueError("steps and stable_steps_required must be positive integers")
        dt = _finite(time_step_s, "time_step_s", positive=True)
        speed_tolerance = _finite(speed_tolerance_m_s,
                                  "speed_tolerance_m_s", positive=True)
        if len(face_material_ids) != len(faces):
            raise ValueError("one material id is required per face")
        parsed_profiles = {str(name): _profile(value, str(name))
                           for name, value in materials.items()}
        missing = sorted(set(str(value) for value in face_material_ids)
                         - set(parsed_profiles))
        if missing:
            return _unknown(NO_MATERIAL, "material profiles are missing",
                            missing=missing)
        masses = [0.0] * len(vertices)
        for face, material_id in zip(faces, face_material_ids):
            area = _triangle_area(vertices, face)
            share = area * parsed_profiles[str(material_id)]["areal_density_kg_m2"] / 3.0
            for index in face:
                masses[int(index)] += share
        built = _lattice.mesh_to_cross_lattice(
            vertices, faces, face_material_ids=face_material_ids,
            vertex_masses=masses, areal_density_kg_m2=1.0)
        if built.get("verdict") != ANSWER:
            return {"verdict": built.get("code", BAD_INPUT),
                    "failed_stage": "cross_lattice", "upstream": built}
        physical = _force_lattice(built["lattice"], parsed_profiles,
                                  {int(value) for value in fixed_vertices})
        layers = list(vertex_layers or [0] * len(vertices))
        if len(layers) != len(vertices):
            raise ValueError("one layer is required per vertex")
        active_constraints = dict(constraints or {})
        history = []
        stable_count = 0
        last_diagnostics: Dict[str, Any] = {}
        for step_index in range(steps):
            before = {key: list(value["position_m"])
                      for key, value in physical["nodes"].items()}
            advanced = _forces.integrate_semi_implicit(physical, dt, environment)
            if advanced.get("verdict") != ANSWER:
                return {"verdict": advanced.get("verdict"),
                        "failed_stage": "cross_forces", "upstream": advanced,
                        "history": history}
            physical = advanced["value"]["lattice"]
            if active_constraints:
                state = _constraint_state(physical, faces, layers)
                for index, vertex in enumerate(state["vertices"]):
                    vertex["previous_position"] = before[str(index)]
                projected = _constraints.solve_cross_constraints(
                    state, active_constraints, iterations=constraint_iterations)
                if projected.get("verdict") not in (ANSWER,):
                    return {"verdict": projected.get("verdict"),
                            "failed_stage": "cross_constraints",
                            "upstream": projected, "history": history}
                last_diagnostics = projected["diagnostics"]
                for index, vertex in enumerate(projected["state"]["vertices"]):
                    node = physical["nodes"][str(index)]
                    position = list(vertex["position"])
                    node["velocity_m_s"] = [
                        (position[axis] - before[str(index)][axis]) / dt
                        for axis in range(3)]
                    node["position_m"] = position
            max_speed = max(math.sqrt(sum(component * component
                                          for component in node["velocity_m_s"]))
                            for node in physical["nodes"].values())
            energy = _forces.total_energy(physical, environment)
            if energy.get("verdict") != ANSWER:
                return {"verdict": energy.get("verdict"),
                        "failed_stage": "cross_energy", "upstream": energy,
                        "history": history}
            stable_count = stable_count + 1 if max_speed <= speed_tolerance else 0
            history.append({"step": step_index + 1, "max_speed_m_s": max_speed,
                            "total_energy_j": energy["value"]["total_energy_j"],
                            "substeps": advanced["value"]["substeps"]})
            if stable_count >= stable_steps_required:
                break
        return {
            "verdict": ANSWER,
            "terminal_verdict": ("CONVERGED" if stable_count >= stable_steps_required
                                 else "IN_PROGRESS"),
            "lattice": physical,
            "history": history,
            "constraint_diagnostics": last_diagnostics,
            "cross_contract": {
                "representation": "mesoscopic six-arm data structure",
                "arms": 6, "visible_facets_per_arm": 4,
                "update": "force stage then constraint stage; typed outputs stacked",
                "not_atoms_or_molecules": True,
            },
        }
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return _unknown(BAD_INPUT, str(error))


__all__ = ["ANSWER", "BAD_INPUT", "NO_MATERIAL", "simulate"]
