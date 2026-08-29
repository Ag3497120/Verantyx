# -*- coding: utf-8 -*-
"""Deterministic force kernels for a cloth cross lattice.

The public API accepts and returns plain JSON-like mappings.  No model or
corpus is consulted.  Every physical input is named with its SI unit.

The *cross* is a data format and numerical stencil.  It is not asserted to be
an atom, molecule, or other literal microscopic object.  A six-section cross
may additionally be evaluated with :func:`jacobi_cross_update`: all six outer
sections read one identical old centre state, report separate energy terms,
and are reduced only after every independent contribution exists.  Mapping or
scan order therefore cannot create information.

Lattice schema::

    {
      "nodes": {id: {"position_m": [x,y,z], "velocity_m_s": [x,y,z],
                       "mass_kg": m, "fixed": false}},
      "links": [{"a": id, "b": id, "kind": "warp|weft|shear|bend",
                  "rest_length_m": l,
                  "material": {"warp_stiffness_n_m": k, ...,
                               "damping_n_s_m": c}}],
      "faces": [{"nodes": [a,b,c], "material": {
                  "drag_coefficient": cd, "lift_coefficient": cl}}]
    }

``bend`` links are the cross lattice's discrete curvature elements: they join
two-hop neighbours and penalise departure from their rest chord.  This is an
inspectable force kernel, not a collision or self-contact solver.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Dict, Mapping, Sequence, Tuple


Vec3 = Tuple[float, float, float]
_KINDS = ("warp", "weft", "shear", "bend")
_STIFFNESS_KEYS = {
    "warp": "warp_stiffness_n_m",
    "weft": "weft_stiffness_n_m",
    "shear": "shear_stiffness_n_m",
    "bend": "bending_stiffness_n_m",
}


class _Invalid(ValueError):
    pass


def _answer(value: Any, *reasons: str) -> Dict[str, Any]:
    return {"verdict": "ANSWER", "reasons": list(reasons), "value": value}


def _unknown(code: str, reason: str, value: Any = None) -> Dict[str, Any]:
    return {"verdict": code, "reasons": [reason], "value": value}


def _number(value: Any, name: str, *, minimum: float | None = None,
            positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a number in SI units")
    value = float(value)
    if not math.isfinite(value):
        raise _Invalid(f"{name} must be finite")
    if positive and value <= 0.0:
        raise _Invalid(f"{name} must be greater than zero")
    if minimum is not None and value < minimum:
        raise _Invalid(f"{name} must be at least {minimum}")
    return value


def _vec(value: Any, name: str) -> Vec3:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or len(value) != 3):
        raise _Invalid(f"{name} must contain three SI components")
    return tuple(_number(v, f"{name}[{i}]") for i, v in enumerate(value))  # type: ignore[return-value]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _normalised(a: Vec3) -> Vec3:
    length = _norm(a)
    if length <= 1.0e-15:
        raise _Invalid("zero-length direction is not physically defined")
    return _mul(a, 1.0 / length)


def _validated(lattice: Mapping[str, Any]) -> Tuple[Dict[str, Dict[str, Any]],
                                                    list[Dict[str, Any]],
                                                    list[Dict[str, Any]]]:
    if not isinstance(lattice, Mapping):
        raise _Invalid("lattice must be a mapping")
    raw_nodes = lattice.get("nodes")
    raw_links = lattice.get("links")
    raw_faces = lattice.get("faces", [])
    if not isinstance(raw_nodes, Mapping) or not raw_nodes:
        raise _Invalid("nodes must be a non-empty mapping")
    if not isinstance(raw_links, Sequence) or isinstance(raw_links, (str, bytes)):
        raise _Invalid("links must be a sequence")
    if not isinstance(raw_faces, Sequence) or isinstance(raw_faces, (str, bytes)):
        raise _Invalid("faces must be a sequence")

    nodes: Dict[str, Dict[str, Any]] = {}
    for node_id, raw in raw_nodes.items():
        if not isinstance(node_id, str) or not node_id or not isinstance(raw, Mapping):
            raise _Invalid("node ids must be non-empty strings with mappings")
        nodes[node_id] = {
            "position_m": _vec(raw.get("position_m"), f"nodes.{node_id}.position_m"),
            "velocity_m_s": _vec(raw.get("velocity_m_s"), f"nodes.{node_id}.velocity_m_s"),
            "mass_kg": _number(raw.get("mass_kg"), f"nodes.{node_id}.mass_kg", positive=True),
            "fixed": bool(raw.get("fixed", False)),
        }

    links: list[Dict[str, Any]] = []
    for index, raw in enumerate(raw_links):
        if not isinstance(raw, Mapping):
            raise _Invalid(f"links[{index}] must be a mapping")
        a, b, kind = raw.get("a"), raw.get("b"), raw.get("kind")
        if a not in nodes or b not in nodes or a == b:
            raise _Invalid(f"links[{index}] has invalid node endpoints")
        if kind not in _KINDS:
            raise _Invalid(f"links[{index}].kind must be one of {_KINDS}")
        material = raw.get("material")
        if not isinstance(material, Mapping):
            raise _Invalid(f"links[{index}].material is required")
        stiffness_key = _STIFFNESS_KEYS[kind]
        links.append({
            "a": a, "b": b, "kind": kind,
            "rest_length_m": _number(raw.get("rest_length_m"),
                                     f"links[{index}].rest_length_m", positive=True),
            "stiffness_n_m": _number(material.get(stiffness_key),
                                      f"links[{index}].material.{stiffness_key}", minimum=0.0),
            "damping_n_s_m": _number(material.get("damping_n_s_m"),
                                      f"links[{index}].material.damping_n_s_m", minimum=0.0),
        })

    faces: list[Dict[str, Any]] = []
    for index, raw in enumerate(raw_faces):
        if not isinstance(raw, Mapping):
            raise _Invalid(f"faces[{index}] must be a mapping")
        ids = raw.get("nodes")
        if (not isinstance(ids, Sequence) or isinstance(ids, (str, bytes))
                or len(ids) != 3 or len(set(ids)) != 3
                or any(node_id not in nodes for node_id in ids)):
            raise _Invalid(f"faces[{index}].nodes must name three distinct nodes")
        material = raw.get("material")
        if not isinstance(material, Mapping):
            raise _Invalid(f"faces[{index}].material is required")
        faces.append({
            "nodes": tuple(ids),
            "drag_coefficient": _number(material.get("drag_coefficient"),
                                        f"faces[{index}].material.drag_coefficient", minimum=0.0),
            "lift_coefficient": _number(material.get("lift_coefficient"),
                                        f"faces[{index}].material.lift_coefficient", minimum=0.0),
        })
    return nodes, links, faces


def _environment(environment: Mapping[str, Any] | None) -> Dict[str, Any]:
    env = {} if environment is None else environment
    if not isinstance(env, Mapping):
        raise _Invalid("environment must be a mapping")
    return {
        "gravity_m_s2": _vec(env.get("gravity_m_s2", (0.0, -9.80665, 0.0)),
                              "environment.gravity_m_s2"),
        "wind_velocity_m_s": _vec(env.get("wind_velocity_m_s", (0.0, 0.0, 0.0)),
                                   "environment.wind_velocity_m_s"),
        "air_density_kg_m3": _number(env.get("air_density_kg_m3", 1.225),
                                     "environment.air_density_kg_m3", minimum=0.0),
        "linear_damping_n_s_m": _number(env.get("linear_damping_n_s_m", 0.0),
                                         "environment.linear_damping_n_s_m", minimum=0.0),
    }


def _force_value(lattice: Mapping[str, Any], environment: Mapping[str, Any] | None
                 ) -> Dict[str, Any]:
    nodes, links, faces = _validated(lattice)
    env = _environment(environment)
    forces: Dict[str, Vec3] = {
        node_id: _mul(env["gravity_m_s2"], node["mass_kg"])
        for node_id, node in nodes.items()
    }
    elastic_energy = 0.0
    dissipation_power = 0.0

    for link in links:
        a, b = link["a"], link["b"]
        delta = _sub(nodes[b]["position_m"], nodes[a]["position_m"])
        length = _norm(delta)
        if length <= 1.0e-15:
            raise _Invalid(f"link {a}-{b} has coincident endpoints")
        direction = _mul(delta, 1.0 / length)
        extension = length - link["rest_length_m"]
        relative_speed = _dot(_sub(nodes[b]["velocity_m_s"],
                                  nodes[a]["velocity_m_s"]), direction)
        magnitude = (link["stiffness_n_m"] * extension
                     + link["damping_n_s_m"] * relative_speed)
        force = _mul(direction, magnitude)
        forces[a] = _add(forces[a], force)
        forces[b] = _sub(forces[b], force)
        elastic_energy += 0.5 * link["stiffness_n_m"] * extension * extension
        dissipation_power += link["damping_n_s_m"] * relative_speed**2

    for face in faces:
        a, b, c = face["nodes"]
        pa, pb, pc = (nodes[a]["position_m"], nodes[b]["position_m"],
                      nodes[c]["position_m"])
        area_vector = _cross(_sub(pb, pa), _sub(pc, pa))
        double_area = _norm(area_vector)
        if double_area <= 1.0e-15:
            raise _Invalid(f"face {a}-{b}-{c} has zero area")
        normal = _mul(area_vector, 1.0 / double_area)
        area_m2 = 0.5 * double_area
        mean_velocity = _mul(_add(_add(nodes[a]["velocity_m_s"],
                                           nodes[b]["velocity_m_s"]),
                                      nodes[c]["velocity_m_s"]), 1.0 / 3.0)
        relative_wind = _sub(env["wind_velocity_m_s"], mean_velocity)
        speed = _norm(relative_wind)
        if speed > 1.0e-15 and env["air_density_kg_m3"] > 0.0:
            flow = _mul(relative_wind, 1.0 / speed)
            dynamic = 0.5 * env["air_density_kg_m3"] * area_m2 * speed**2
            drag = _mul(flow, dynamic * face["drag_coefficient"])
            # Signed normal force.  Reversing flow reverses its incidence and
            # therefore this lift term as well as the drag term.
            lift = _mul(normal, dynamic * face["lift_coefficient"]
                        * _dot(flow, normal))
            share = _mul(_add(drag, lift), 1.0 / 3.0)
            for node_id in (a, b, c):
                forces[node_id] = _add(forces[node_id], share)

    linear_damping = env["linear_damping_n_s_m"]
    for node_id, node in nodes.items():
        damping = _mul(node["velocity_m_s"], -linear_damping)
        forces[node_id] = _add(forces[node_id], damping)
        dissipation_power += linear_damping * _dot(node["velocity_m_s"],
                                                   node["velocity_m_s"])
        if node["fixed"]:
            forces[node_id] = (0.0, 0.0, 0.0)
    return {
        "forces_n": {key: list(value) for key, value in forces.items()},
        "elastic_energy_j": elastic_energy,
        "dissipation_power_w": dissipation_power,
    }


def compute_forces(lattice: Mapping[str, Any],
                   environment: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Return gravity, elastic, damping and aerodynamic forces in newtons."""
    try:
        return _answer(_force_value(lattice, environment),
                       "deterministic cross-lattice force evaluation")
    except (KeyError, TypeError, _Invalid) as exc:
        return _unknown("UNKNOWN_INVALID_INPUT", str(exc))


def total_energy(lattice: Mapping[str, Any],
                 environment: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Return kinetic + elastic + gravity-potential mechanical energy in J."""
    try:
        nodes, _, _ = _validated(lattice)
        env = _environment(environment)
        force_data = _force_value(lattice, environment)
        kinetic = sum(0.5 * node["mass_kg"]
                      * _dot(node["velocity_m_s"], node["velocity_m_s"])
                      for node in nodes.values())
        gravitational = sum(-node["mass_kg"]
                            * _dot(env["gravity_m_s2"], node["position_m"])
                            for node in nodes.values())
        elastic = force_data["elastic_energy_j"]
        return _answer({
            "kinetic_energy_j": kinetic,
            "elastic_energy_j": elastic,
            "gravitational_energy_j": gravitational,
            "total_energy_j": kinetic + elastic + gravitational,
            "dissipation_power_w": force_data["dissipation_power_w"],
        }, "mechanical energy excludes non-conservative wind work")
    except (KeyError, TypeError, _Invalid) as exc:
        return _unknown("UNKNOWN_INVALID_INPUT", str(exc))


def _stable_step_bound(nodes: Mapping[str, Mapping[str, Any]],
                       links: Sequence[Mapping[str, Any]], safety: float) -> float:
    stiffness_by_node = {node_id: 0.0 for node_id in nodes}
    for link in links:
        stiffness_by_node[link["a"]] += link["stiffness_n_m"]
        stiffness_by_node[link["b"]] += link["stiffness_n_m"]
    frequencies = [math.sqrt(k / nodes[node_id]["mass_kg"])
                   for node_id, k in stiffness_by_node.items()
                   if k > 0.0 and not nodes[node_id]["fixed"]]
    return math.inf if not frequencies else safety / max(frequencies)


def integrate_semi_implicit(
        lattice: Mapping[str, Any], time_step_s: float,
        environment: Mapping[str, Any] | None = None, *,
        cfl_safety: float = 0.25, max_substeps: int = 4096) -> Dict[str, Any]:
    """Advance one interval with adaptive semi-implicit Euler substeps.

    The CFL-like bound is ``safety / max(sqrt(sum(k)/mass))``.  A request that
    would exceed ``max_substeps`` is refused rather than silently destabilised.
    """
    try:
        dt = _number(time_step_s, "time_step_s", positive=True)
        safety = _number(cfl_safety, "cfl_safety", positive=True)
        if safety > 1.0:
            raise _Invalid("cfl_safety must not exceed 1")
        if isinstance(max_substeps, bool) or not isinstance(max_substeps, int) or max_substeps < 1:
            raise _Invalid("max_substeps must be a positive integer")
        nodes, links, _ = _validated(lattice)
        bound = _stable_step_bound(nodes, links, safety)
        substeps = 1 if math.isinf(bound) else max(1, int(math.ceil(dt / bound)))
        if substeps > max_substeps:
            return _unknown("UNKNOWN_TIMESTEP_TOO_LARGE",
                            f"stable integration requires {substeps} substeps; limit is {max_substeps}")
        sub_dt = dt / substeps
        state = deepcopy(dict(lattice))
        for _ in range(substeps):
            current_nodes, _, _ = _validated(state)
            force_data = _force_value(state, environment)
            for node_id, node in current_nodes.items():
                if node["fixed"]:
                    state["nodes"][node_id]["velocity_m_s"] = [0.0, 0.0, 0.0]
                    continue
                acceleration = _mul(tuple(force_data["forces_n"][node_id]),
                                    1.0 / node["mass_kg"])
                velocity = _add(node["velocity_m_s"], _mul(acceleration, sub_dt))
                position = _add(node["position_m"], _mul(velocity, sub_dt))
                if not all(math.isfinite(v) for v in velocity + position):
                    raise _Invalid("integration produced a non-finite state")
                state["nodes"][node_id]["velocity_m_s"] = list(velocity)
                state["nodes"][node_id]["position_m"] = list(position)
        return _answer({
            "lattice": state,
            "substeps": substeps,
            "substep_s": sub_dt,
            "cfl_bound_s": None if math.isinf(bound) else bound,
        }, "stable semi-implicit integration", "adaptive cross-lattice CFL bound")
    except (KeyError, TypeError, _Invalid) as exc:
        return _unknown("UNKNOWN_INVALID_INPUT", str(exc))


# Short aliases for callers that name the two operations by role.
forces = compute_forces
integrate = integrate_semi_implicit


# Canonical labels identify geometry, never processing order.
SIX_DIRECTIONS = ("x-", "x+", "y-", "y+", "z-", "z+")
LAYER_SCALES = ("coarse", "medium", "fine")
FACETS_PER_ARM = 4


def _cross_section_value(cross: Mapping[str, Any], agreement_tolerance: float,
                         stability_tolerance: float) -> Tuple[str, Dict[str, Any], str]:
    """Evaluate one six-section Jacobi stencil and retain its audit data."""
    if not isinstance(cross, Mapping):
        raise _Invalid("cross must be a mapping")
    old = cross.get("old_center_state")
    if (not isinstance(old, Sequence) or isinstance(old, (str, bytes))
            or not old):
        raise _Invalid("old_center_state must be a non-empty numeric sequence")
    old_state = tuple(_number(v, f"old_center_state[{i}]")
                      for i, v in enumerate(old))
    sections = cross.get("sections")
    if not isinstance(sections, Mapping) or set(sections) != set(SIX_DIRECTIONS):
        raise _Invalid("sections must contain exactly x-, x+, y-, y+, z-, z+")

    reports: Dict[str, Dict[str, Any]] = {}
    signal_kind: str | None = None
    # Canonical iteration makes floating reduction reproducible.  More
    # importantly, every candidate reads old_state, never a prior candidate.
    for direction in SIX_DIRECTIONS:
        section = sections[direction]
        if not isinstance(section, Mapping):
            raise _Invalid(f"sections.{direction} must be a mapping")
        kind = section.get("signal_kind")
        if not isinstance(kind, str) or not kind.strip():
            raise _Invalid(f"sections.{direction}.signal_kind is required")
        if signal_kind is None:
            signal_kind = kind
        elif kind != signal_kind:
            raise _Invalid("different signal meanings cannot be bundled into one vote")
        outer = section.get("outer_state")
        if (not isinstance(outer, Sequence) or isinstance(outer, (str, bytes))
                or len(outer) != len(old_state)):
            raise _Invalid(f"sections.{direction}.outer_state has the wrong dimension")
        outer_state = tuple(_number(v, f"sections.{direction}.outer_state[{i}]")
                            for i, v in enumerate(outer))
        material = section.get("material")
        if not isinstance(material, Mapping):
            raise _Invalid(f"sections.{direction}.material is required")
        coupling = _number(material.get("coupling_j_per_unit2"),
                           f"sections.{direction}.material.coupling_j_per_unit2",
                           minimum=0.0)
        gain = _number(material.get("transfer_gain"),
                       f"sections.{direction}.material.transfer_gain",
                       minimum=0.0)
        if gain > 1.0:
            raise _Invalid(f"sections.{direction}.material.transfer_gain must not exceed 1")
        delta = tuple(outer_state[i] - old_state[i] for i in range(len(old_state)))
        candidate = tuple(old_state[i] + gain * delta[i]
                          for i in range(len(old_state)))
        energy = 0.5 * coupling * sum(component * component for component in delta)
        reports[direction] = {
            "candidate_center_state": list(candidate),
            "contribution_from_old_state": [candidate[i] - old_state[i]
                                            for i in range(len(old_state))],
            "energy_j": energy,
            "signal_kind": kind,
        }

    candidates = [reports[d]["candidate_center_state"] for d in SIX_DIRECTIONS]
    proposed = [math.fsum(candidate[i] for candidate in candidates) / 6.0
                for i in range(len(old_state))]
    spread = max(max(candidate[i] for candidate in candidates)
                 - min(candidate[i] for candidate in candidates)
                 for i in range(len(old_state)))
    update_norm = math.sqrt(sum((proposed[i] - old_state[i])**2
                                for i in range(len(old_state))))
    energy_by_section = {direction: reports[direction]["energy_j"]
                         for direction in SIX_DIRECTIONS}
    value = {
        "old_center_state": list(old_state),
        "proposed_center_state": proposed,
        "committed_center_state": None,
        "signal_kind": signal_kind,
        "sections": reports,
        "energy_by_section_j": energy_by_section,
        "total_energy_j": math.fsum(energy_by_section[d] for d in SIX_DIRECTIONS),
        "maximum_section_spread": spread,
        "center_update_norm": update_norm,
        "agreement_tolerance": agreement_tolerance,
        "stability_tolerance": stability_tolerance,
        "update_scheme": "JACOBI_SAME_OLD_STATE",
    }
    if spread > agreement_tolerance:
        return ("CONTESTED_SECTION_DISAGREEMENT", value,
                "six section candidates disagree; no candidate was selected")
    if update_norm > stability_tolerance:
        return ("UNKNOWN_NOT_STABLE", value,
                "sections agree but the center update is not yet stable")
    value["committed_center_state"] = proposed
    return ("ANSWER", value, "all six sections agree and the center is stable")


def jacobi_cross_update(cross: Mapping[str, Any], *,
                        agreement_tolerance: float = 1.0e-6,
                        stability_tolerance: float = 1.0e-6) -> Dict[str, Any]:
    """Reduce six independent outer-section estimates into one centre update.

    A split, tie, or tolerance violation is never resolved by winner selection.
    Its proposed aggregate is retained only for diagnosis and is not committed.
    """
    try:
        agreement = _number(agreement_tolerance, "agreement_tolerance", minimum=0.0)
        stability = _number(stability_tolerance, "stability_tolerance", minimum=0.0)
        verdict, value, reason = _cross_section_value(cross, agreement, stability)
        return {"verdict": verdict, "reasons": [reason], "value": value}
    except (KeyError, TypeError, _Invalid) as exc:
        code = ("UNKNOWN_MIXED_SIGNAL_MEANING" if "signal meanings" in str(exc)
                else "UNKNOWN_INVALID_INPUT")
        return _unknown(code, str(exc))


def solve_cross_layers(layers: Sequence[Mapping[str, Any]], *,
                       agreement_tolerance: float = 1.0e-6,
                       stability_tolerance: float = 1.0e-6) -> Dict[str, Any]:
    """Run typed coarse -> medium -> fine Jacobi layers without vote fusion.

    Each layer declares ``scale``, ``target_id``, ``resolution_m``,
    ``input_signal_kind``, and a ``cross``.
    A successful layer's committed centre is copied into the next layer's old
    state.  The layers observe the same target at progressively finer
    resolution; they are not partitions or votes.  An exact copied identity
    layer is rejected because it contributes no new information.  Any
    non-ANSWER verdict stops the pipeline with all prior reports.
    """
    try:
        if (not isinstance(layers, Sequence) or isinstance(layers, (str, bytes))
                or len(layers) != 3):
            raise _Invalid("layers must contain exactly coarse, medium, fine")
        reports = []
        previous_state = None
        previous_signal = None
        target_id = None
        previous_resolution = None
        for index, expected_scale in enumerate(LAYER_SCALES):
            layer = layers[index]
            if not isinstance(layer, Mapping) or layer.get("scale") != expected_scale:
                raise _Invalid(f"layer {index} must have scale {expected_scale}")
            declared_input = layer.get("input_signal_kind")
            if not isinstance(declared_input, str) or not declared_input:
                raise _Invalid(f"{expected_scale}.input_signal_kind is required")
            if previous_signal is not None and declared_input != previous_signal:
                raise _Invalid("a layer cannot reinterpret the previous typed signal")
            current_target = layer.get("target_id")
            if not isinstance(current_target, str) or not current_target:
                raise _Invalid(f"{expected_scale}.target_id is required")
            if target_id is None:
                target_id = current_target
            elif current_target != target_id:
                raise _Invalid("coarse, medium, and fine must observe the same target")
            resolution = _number(layer.get("resolution_m"),
                                 f"{expected_scale}.resolution_m", positive=True)
            if previous_resolution is not None and resolution >= previous_resolution:
                raise _Invalid("layer resolution_m must become strictly finer")
            raw_cross = layer.get("cross")
            if not isinstance(raw_cross, Mapping):
                raise _Invalid(f"{expected_scale}.cross must be a mapping")
            stage_cross = deepcopy(dict(raw_cross))
            if previous_state is not None:
                stage_cross["old_center_state"] = list(previous_state)
            result = jacobi_cross_update(
                stage_cross, agreement_tolerance=agreement_tolerance,
                stability_tolerance=stability_tolerance)
            reports.append({"scale": expected_scale, "result": result})
            if result["verdict"] != "ANSWER":
                return {"verdict": result["verdict"],
                        "reasons": [f"{expected_scale} layer did not converge"],
                        "value": {"layers": reports, "completed_scale": None}}
            value = result["value"]
            if value["signal_kind"] != declared_input:
                raise _Invalid(f"{expected_scale} layer signal does not match its typed input")
            if (previous_state is not None
                    and value["committed_center_state"] == list(previous_state)):
                return _unknown(
                    "UNKNOWN_IDENTITY_LAYER",
                    f"{expected_scale} exactly copied its input and adds no information",
                    {"layers": reports, "completed_scale": None})
            previous_state = value["committed_center_state"]
            previous_signal = value["signal_kind"]
            previous_resolution = resolution
        return _answer({"layers": reports, "completed_scale": "fine",
                        "center_state": previous_state,
                        "signal_kind": previous_signal,
                        "target_id": target_id},
                       "coarse, medium, and fine layers converged in typed order")
    except (KeyError, TypeError, _Invalid) as exc:
        if "same target" in str(exc):
            code = "UNKNOWN_TARGET_MISMATCH"
        elif "signal" in str(exc):
            code = "UNKNOWN_MIXED_SIGNAL_MEANING"
        else:
            code = "UNKNOWN_INVALID_INPUT"
        return _unknown(code, str(exc))


def build_facet_diagnostics(contributions: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a bounded 6-arm x 4-facet explanatory table.

    Each contribution declares ``id``, ``arm``, ``force_n``, ``energy_j`` and
    ``signal_kind``.  More than four contributions on an arm require explicit
    non-empty ``refinement_cell`` labels; each child cell is itself limited to
    four facets.  Physical force and energy are accumulated from *all* inputs
    before capacity is checked, so an explanatory overflow cannot alter the
    physics.  No alphabetical or first-four winner is ever selected.
    """
    try:
        if (not isinstance(contributions, Sequence)
                or isinstance(contributions, (str, bytes))):
            raise _Invalid("contributions must be a sequence")
        by_arm: Dict[str, list[Dict[str, Any]]] = {arm: [] for arm in SIX_DIRECTIONS}
        seen = set()
        signal_kind = None
        for index, raw in enumerate(contributions):
            if not isinstance(raw, Mapping):
                raise _Invalid(f"contributions[{index}] must be a mapping")
            contribution_id = raw.get("id")
            if not isinstance(contribution_id, str) or not contribution_id:
                raise _Invalid(f"contributions[{index}].id is required")
            if contribution_id in seen:
                raise _Invalid(f"duplicate contribution id {contribution_id}")
            seen.add(contribution_id)
            arm = raw.get("arm")
            if arm not in SIX_DIRECTIONS:
                raise _Invalid(f"contributions[{index}].arm is invalid")
            kind = raw.get("signal_kind")
            if not isinstance(kind, str) or not kind:
                raise _Invalid(f"contributions[{index}].signal_kind is required")
            if signal_kind is None:
                signal_kind = kind
            elif kind != signal_kind:
                raise _Invalid("different signal meanings cannot share one facet table")
            refinement = raw.get("refinement_cell")
            if refinement is not None and (not isinstance(refinement, str) or not refinement):
                raise _Invalid("refinement_cell must be a non-empty string when provided")
            by_arm[arm].append({
                "id": contribution_id,
                "force_n": list(_vec(raw.get("force_n"),
                                     f"contributions[{index}].force_n")),
                "energy_j": _number(raw.get("energy_j"),
                                    f"contributions[{index}].energy_j", minimum=0.0),
                "signal_kind": kind,
                "refinement_cell": refinement,
            })

        accumulation = {}
        for arm in SIX_DIRECTIONS:
            items = by_arm[arm]
            accumulation[arm] = {
                "force_n": [math.fsum(item["force_n"][axis] for item in items)
                            for axis in range(3)],
                "energy_j": math.fsum(item["energy_j"] for item in items),
                "contribution_count": len(items),
            }
        physical = {
            "by_arm": accumulation,
            "total_force_n": [math.fsum(accumulation[arm]["force_n"][axis]
                                        for arm in SIX_DIRECTIONS)
                              for axis in range(3)],
            "total_energy_j": math.fsum(accumulation[arm]["energy_j"]
                                        for arm in SIX_DIRECTIONS),
            "input_contribution_count": len(contributions),
        }

        table: Dict[str, Any] = {}
        overflow = []
        for arm in SIX_DIRECTIONS:
            items = by_arm[arm]
            if len(items) <= FACETS_PER_ARM:
                table[arm] = {"facets": items, "refined": False}
                continue
            if any(item["refinement_cell"] is None for item in items):
                overflow.append(arm)
                table[arm] = {"facets": None, "refined": False,
                              "required_contributions": len(items)}
                continue
            cells: Dict[str, list[Dict[str, Any]]] = {}
            for item in items:
                cells.setdefault(item["refinement_cell"], []).append(item)
            if any(len(cell_items) > FACETS_PER_ARM for cell_items in cells.values()):
                overflow.append(arm)
                table[arm] = {"facets": None, "refined": False,
                              "required_contributions": len(items)}
                continue
            table[arm] = {"refined": True, "cells": cells}
        value = {
            "physical_accumulation": physical,
            "facet_table": table,
            "capacity": {"arms": 6, "facets_per_arm": 4,
                         "visible_facet_slots": 24},
            "signal_kind": signal_kind,
        }
        if overflow:
            return _unknown(
                "UNKNOWN_REFINEMENT_REQUIRED",
                "facet capacity exceeded on arms " + ", ".join(overflow)
                + "; no contributions were dropped or selected",
                value)
        return _answer(value, "all contributions retained in bounded or nested facets")
    except (KeyError, TypeError, _Invalid) as exc:
        code = ("UNKNOWN_MIXED_SIGNAL_MEANING" if "signal meanings" in str(exc)
                else "UNKNOWN_INVALID_INPUT")
        return _unknown(code, str(exc))
