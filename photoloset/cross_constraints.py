# -*- coding: utf-8 -*-
"""Deterministic projection constraints for cross-structured cloth states.

The solver intentionally operates on plain dictionaries, lists and numbers so
that a state can be recorded by Vera without serialising solver objects.  The
only exception is an optional signed-distance callable.  It is a constraint
projection kernel, not a time integrator: callers supply current and previous
positions and may run their own force/integration step before projection.

Supported constraints are mannequin contact (sphere, capsule, or SDF),
Coulomb friction, compliant/breakable seam pairs, conservative vertex
self-collision through a spatial hash, and explicit inner/outer layer order.
No failed or under-converged solve is promoted to an answer.

Here, a *spatial cross* is only a data format: six labelled outer arms
contribute toward a shared centre. It is not asserted to be a physical atom or
molecule. Each arm has four bounded explanatory facet slots (24 per node),
while physical accumulation remains unbounded and separate. Section updates
are Jacobi-style: every contribution reads the same old centre and all are
combined at once. A scan order therefore cannot manufacture information.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]

ANSWER = "ANSWER"
UNKNOWN_INVALID_CONSTRAINTS = "UNKNOWN_INVALID_CONSTRAINTS"
UNKNOWN_INFEASIBLE_CONSTRAINTS = "UNKNOWN_INFEASIBLE_CONSTRAINTS"
UNKNOWN_NOT_STABLE = "UNKNOWN_NOT_STABLE"
UNKNOWN_REFINEMENT_REQUIRED = "UNKNOWN_REFINEMENT_REQUIRED"
CONTESTED = "CONTESTED"

CROSS_SECTION_DIRECTIONS: Dict[str, Vec3] = {
    "+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0), "-y": (0.0, -1.0, 0.0),
    "+z": (0.0, 0.0, 1.0), "-z": (0.0, 0.0, -1.0),
}


class ConstraintInputError(ValueError):
    """Internal validation error converted to a typed public verdict."""


def _vec(value: Any, name: str) -> Vec3:
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(isinstance(x, bool) or not isinstance(x, (int, float))
                   or not math.isfinite(float(x)) for x in value)):
        raise ConstraintInputError(f"{name} must contain three finite numbers")
    return float(value[0]), float(value[1]), float(value[2])


def _number(value: Any, name: str, *, low: Optional[float] = None,
            strict: bool = False) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value))):
        raise ConstraintInputError(f"{name} must be finite")
    out = float(value)
    if low is not None and (out <= low if strict else out < low):
        op = ">" if strict else ">="
        raise ConstraintInputError(f"{name} must be {op} {low}")
    return out


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(a: Vec3, scale: float) -> Vec3:
    return a[0] * scale, a[1] * scale, a[2] * scale


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _normalise(a: Vec3, fallback: Vec3 = (1.0, 0.0, 0.0)) -> Vec3:
    length = _length(a)
    return fallback if length <= 1.0e-15 else _mul(a, 1.0 / length)


def _stable_axis(a: int, b: int = 0) -> Vec3:
    """Return a repeatable separation direction for coincident samples."""
    axis = (a * 73856093 + b * 19349663) % 3
    sign = -1.0 if ((a + b) & 1) else 1.0
    values = [0.0, 0.0, 0.0]
    values[axis] = sign
    return values[0], values[1], values[2]


def _closest_on_segment(point: Vec3, a: Vec3, b: Vec3) -> Vec3:
    ab = _sub(b, a)
    denominator = _dot(ab, ab)
    if denominator <= 1.0e-30:
        return a
    t = max(0.0, min(1.0, _dot(_sub(point, a), ab) / denominator))
    return _add(a, _mul(ab, t))


def sphere_signed_distance(center: Sequence[float], radius: float
                           ) -> Callable[[Sequence[float]], float]:
    """Build a signed-distance callable; negative values are inside."""
    c = _vec(center, "center")
    r = _number(radius, "radius", low=0.0, strict=True)

    def distance(point: Sequence[float]) -> float:
        return _length(_sub(_vec(point, "point"), c)) - r
    return distance


def capsule_signed_distance(a: Sequence[float], b: Sequence[float],
                            radius: float) -> Callable[[Sequence[float]], float]:
    """Build an SDF for a capsule around line segment ``a``--``b``."""
    va, vb = _vec(a, "a"), _vec(b, "b")
    r = _number(radius, "radius", low=0.0, strict=True)

    def distance(point: Sequence[float]) -> float:
        p = _vec(point, "point")
        return _length(_sub(p, _closest_on_segment(p, va, vb))) - r
    return distance


def _contact_sample(contact: Mapping[str, Any], point: Vec3,
                    vertex_index: int) -> Tuple[float, Vec3]:
    kind = contact.get("type")
    if kind == "sphere":
        center = _vec(contact.get("center"), "contact.center")
        radius = _number(contact.get("radius"), "contact.radius", low=0.0,
                         strict=True)
        delta = _sub(point, center)
        return _length(delta) - radius, _normalise(delta, _stable_axis(vertex_index))
    if kind == "capsule":
        a = _vec(contact.get("a"), "contact.a")
        b = _vec(contact.get("b"), "contact.b")
        radius = _number(contact.get("radius"), "contact.radius", low=0.0,
                         strict=True)
        closest = _closest_on_segment(point, a, b)
        delta = _sub(point, closest)
        return _length(delta) - radius, _normalise(delta, _stable_axis(vertex_index))
    if kind == "sdf":
        distance = contact.get("distance")
        if not callable(distance):
            raise ConstraintInputError("sdf contact.distance must be callable")
        signed = _number(distance(point), "signed distance")
        gradient = contact.get("gradient")
        if gradient is not None:
            if not callable(gradient):
                raise ConstraintInputError("sdf contact.gradient must be callable")
            normal = _normalise(_vec(gradient(point), "sdf gradient"),
                                _stable_axis(vertex_index))
        else:
            epsilon = _number(contact.get("gradient_epsilon", 1.0e-6),
                              "gradient_epsilon", low=0.0, strict=True)
            samples = []
            for axis in range(3):
                plus, minus = list(point), list(point)
                plus[axis] += epsilon
                minus[axis] -= epsilon
                samples.append((_number(distance(tuple(plus)), "sdf sample")
                                - _number(distance(tuple(minus)), "sdf sample"))
                               / (2.0 * epsilon))
            normal = _normalise((samples[0], samples[1], samples[2]),
                                _stable_axis(vertex_index))
        return signed, normal
    raise ConstraintInputError("contact.type must be sphere, capsule, or sdf")


def _indices(spec: Mapping[str, Any], count: int, name: str) -> Tuple[int, ...]:
    raw = spec.get("vertices", range(count))
    if not isinstance(raw, (list, tuple, range)):
        raise ConstraintInputError(f"{name}.vertices must be an index list")
    result = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < count:
            raise ConstraintInputError(f"{name} contains an invalid vertex index")
        result.append(value)
    return tuple(sorted(set(result)))


def _validate_state(state: Mapping[str, Any]) -> Tuple[List[List[float]], List[Vec3],
                                                       List[float], List[int],
                                                       Tuple[Tuple[int, int, int], ...]]:
    if not isinstance(state, Mapping):
        raise ConstraintInputError("state must be a mapping")
    raw_vertices = state.get("vertices")
    if not isinstance(raw_vertices, list) or not raw_vertices:
        raise ConstraintInputError("state.vertices must be a non-empty list")
    positions: List[List[float]] = []
    previous: List[Vec3] = []
    inverse_masses: List[float] = []
    layers: List[int] = []
    for index, vertex in enumerate(raw_vertices):
        if not isinstance(vertex, Mapping):
            raise ConstraintInputError(f"vertex {index} must be a mapping")
        position = _vec(vertex.get("position"), f"vertex {index}.position")
        prior = _vec(vertex.get("previous_position", position),
                     f"vertex {index}.previous_position")
        inverse_mass = _number(vertex.get("inverse_mass", 1.0),
                               f"vertex {index}.inverse_mass", low=0.0)
        layer = vertex.get("layer", 0)
        if isinstance(layer, bool) or not isinstance(layer, int):
            raise ConstraintInputError(f"vertex {index}.layer must be an integer")
        positions.append(list(position))
        previous.append(prior)
        inverse_masses.append(inverse_mass)
        layers.append(layer)
    triangles = []
    raw_triangles = state.get("triangles", [])
    if not isinstance(raw_triangles, list):
        raise ConstraintInputError("state.triangles must be a list")
    for triangle in raw_triangles:
        if (not isinstance(triangle, (list, tuple)) or len(triangle) != 3
                or any(isinstance(i, bool) or not isinstance(i, int)
                       or not 0 <= i < len(positions) for i in triangle)
                or len(set(triangle)) != 3):
            raise ConstraintInputError("every triangle needs three distinct valid indices")
        triangles.append((triangle[0], triangle[1], triangle[2]))
    return positions, previous, inverse_masses, layers, tuple(triangles)


def _validate_constraints(constraints: Mapping[str, Any], count: int
                          ) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]],
                                     List[Mapping[str, Any]], Mapping[str, Any]]:
    if not isinstance(constraints, Mapping):
        raise ConstraintInputError("constraints must be a mapping")
    groups = []
    for name in ("contacts", "seams", "layer_order"):
        group = constraints.get(name, [])
        if not isinstance(group, list) or any(not isinstance(x, Mapping) for x in group):
            raise ConstraintInputError(f"constraints.{name} must be a list of mappings")
        groups.append(group)
    collision = constraints.get("self_collision", {})
    if not isinstance(collision, Mapping):
        raise ConstraintInputError("constraints.self_collision must be a mapping")
    # Force early validation even when there are zero projection iterations.
    for contact in groups[0]:
        _indices(contact, count, "contact")
        _contact_sample(contact, (0.123, 0.234, 0.345), 0)
        clearance = _number(contact.get("clearance", 0.0), "clearance", low=0.0)
        static = _number(contact.get("friction_static", 0.0), "friction_static", low=0.0)
        dynamic = _number(contact.get("friction_dynamic", 0.0), "friction_dynamic", low=0.0)
        if dynamic > static:
            raise ConstraintInputError("friction_dynamic cannot exceed friction_static")
        del clearance
    for seam in groups[1]:
        for endpoint in ("a", "b"):
            value = seam.get(endpoint)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < count:
                raise ConstraintInputError(f"seam.{endpoint} is invalid")
        if seam["a"] == seam["b"]:
            raise ConstraintInputError("a seam cannot pair a vertex with itself")
        _number(seam.get("rest_gap", 0.0), "rest_gap", low=0.0)
        _number(seam.get("compliance", 0.0), "compliance", low=0.0)
        threshold = seam.get("break_threshold", math.inf)
        if threshold != math.inf:
            _number(threshold, "break_threshold", low=0.0, strict=True)
    for order in groups[2]:
        for endpoint in ("inner", "outer"):
            value = order.get(endpoint)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < count:
                raise ConstraintInputError(f"layer_order.{endpoint} is invalid")
        if order["inner"] == order["outer"]:
            raise ConstraintInputError("layer order needs two distinct vertices")
        _vec(order.get("normal"), "layer_order.normal")
        _number(order.get("gap", 0.0), "layer_order.gap", low=0.0)
    if collision:
        _number(collision.get("distance", 0.0), "self_collision.distance",
                low=0.0, strict=True)
        _number(collision.get("cell_size", collision.get("distance", 0.0)),
                "self_collision.cell_size", low=0.0, strict=True)
    return groups[0], groups[1], groups[2], collision


def _move(positions: List[List[float]], index: int, delta: Vec3) -> None:
    positions[index][0] += delta[0]
    positions[index][1] += delta[1]
    positions[index][2] += delta[2]


def _project_pair(positions: List[List[float]], inverse_masses: Sequence[float],
                  a: int, b: int, direction: Vec3, error: float,
                  compliance: float = 0.0) -> bool:
    wa, wb = inverse_masses[a], inverse_masses[b]
    denominator = wa + wb + compliance
    if denominator <= 1.0e-30:
        return False
    correction = error / denominator
    _move(positions, a, _mul(direction, correction * wa))
    _move(positions, b, _mul(direction, -correction * wb))
    return True


def _contact_projection(positions: List[List[float]], previous: Sequence[Vec3],
                        inverse_masses: Sequence[float],
                        contacts: Sequence[Mapping[str, Any]]) -> int:
    active = 0
    for contact in contacts:
        clearance = float(contact.get("clearance", 0.0))
        mu_static = float(contact.get("friction_static", 0.0))
        mu_dynamic = float(contact.get("friction_dynamic", 0.0))
        for index in _indices(contact, len(positions), "contact"):
            point = tuple(positions[index])
            signed, normal = _contact_sample(contact, point, index)
            penetration = clearance - signed
            if penetration <= 0.0:
                continue
            active += 1
            if inverse_masses[index] <= 0.0:
                continue
            _move(positions, index, _mul(normal, penetration))
            # Coulomb projection: static friction cancels tangential travel up
            # to mu_s*N; dynamic friction removes a fixed mu_d*N magnitude.
            displacement = _sub(tuple(positions[index]), previous[index])
            tangential = _sub(displacement, _mul(normal, _dot(displacement, normal)))
            tangent_length = _length(tangential)
            normal_impulse = penetration
            if tangent_length <= mu_static * normal_impulse + 1.0e-15:
                friction = _mul(tangential, -1.0)
            elif tangent_length > 0.0:
                friction = _mul(tangential,
                                -min(tangent_length, mu_dynamic * normal_impulse)
                                / tangent_length)
            else:
                friction = (0.0, 0.0, 0.0)
            _move(positions, index, friction)
    return active


def _seam_projection(positions: List[List[float]], inverse_masses: Sequence[float],
                     seams: Sequence[Mapping[str, Any]], broken: set[int]) -> None:
    for seam_index, seam in enumerate(seams):
        if seam_index in broken:
            continue
        a, b = int(seam["a"]), int(seam["b"])
        delta = _sub(tuple(positions[b]), tuple(positions[a]))
        distance = _length(delta)
        rest = float(seam.get("rest_gap", 0.0))
        threshold = seam.get("break_threshold", math.inf)
        if abs(distance - rest) > threshold:
            broken.add(seam_index)
            continue
        direction = _normalise(delta, _stable_axis(a, b))
        # Positive error pulls a toward b; negative error pushes them apart.
        _project_pair(positions, inverse_masses, a, b, direction,
                      distance - rest, float(seam.get("compliance", 0.0)))


def _layer_projection(positions: List[List[float]], inverse_masses: Sequence[float],
                      orders: Sequence[Mapping[str, Any]]) -> None:
    for order in orders:
        inner, outer = int(order["inner"]), int(order["outer"])
        normal = _normalise(_vec(order["normal"], "layer_order.normal"))
        gap = float(order.get("gap", 0.0))
        separation = _dot(_sub(tuple(positions[outer]), tuple(positions[inner])), normal)
        if separation < gap:
            # Move outer along +normal and inner along -normal.
            _project_pair(positions, inverse_masses, outer, inner, normal,
                          gap - separation)


def _excluded_pairs(triangles: Iterable[Tuple[int, int, int]]) -> set[Tuple[int, int]]:
    excluded = set()
    for triangle in triangles:
        for a, b in ((triangle[0], triangle[1]), (triangle[1], triangle[2]),
                     (triangle[2], triangle[0])):
            excluded.add((min(a, b), max(a, b)))
    return excluded


def _collision_pairs(positions: Sequence[Sequence[float]], distance: float,
                     cell_size: float, excluded: set[Tuple[int, int]]
                     ) -> List[Tuple[int, int]]:
    cells: Dict[Tuple[int, int, int], List[int]] = {}
    for index, point in enumerate(positions):
        key = tuple(math.floor(value / cell_size) for value in point)
        cells.setdefault(key, []).append(index)
    radius = max(1, int(math.ceil(distance / cell_size)))
    pairs = set()
    offsets = range(-radius, radius + 1)
    for cell in sorted(cells):
        for dx in offsets:
            for dy in offsets:
                for dz in offsets:
                    other = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
                    if other not in cells:
                        continue
                    for a in cells[cell]:
                        for b in cells[other]:
                            pair = (min(a, b), max(a, b))
                            if a != b and pair not in excluded:
                                pairs.add(pair)
    return sorted(pairs)


def _collision_projection(positions: List[List[float]], inverse_masses: Sequence[float],
                          layers: Sequence[int], triangles: Iterable[Tuple[int, int, int]],
                          collision: Mapping[str, Any]) -> int:
    if not collision:
        return 0
    distance = float(collision["distance"])
    cell_size = float(collision.get("cell_size", distance))
    excluded = _excluded_pairs(triangles)
    count = 0
    for a, b in _collision_pairs(positions, distance, cell_size, excluded):
        delta = _sub(tuple(positions[b]), tuple(positions[a]))
        actual = _length(delta)
        if actual >= distance:
            continue
        count += 1
        if actual <= 1.0e-15:
            # For layers, increasing layer number is deterministically placed
            # in the positive stable direction. Equal layers use index order.
            direction = _stable_axis(a, b)
            if layers[b] < layers[a]:
                direction = _mul(direction, -1.0)
        else:
            direction = _mul(delta, 1.0 / actual)
        _project_pair(positions, inverse_masses, b, a, direction,
                      distance - actual)
    return count


def _diagnostics(positions: List[List[float]], inverse_masses: Sequence[float],
                 layers: Sequence[int], triangles: Tuple[Tuple[int, int, int], ...],
                 contacts: Sequence[Mapping[str, Any]], seams: Sequence[Mapping[str, Any]],
                 orders: Sequence[Mapping[str, Any]], collision: Mapping[str, Any],
                 broken: set[int], iterations: int) -> Dict[str, Any]:
    max_penetration = 0.0
    contact_violations = 0
    for contact in contacts:
        clearance = float(contact.get("clearance", 0.0))
        for index in _indices(contact, len(positions), "contact"):
            signed, _ = _contact_sample(contact, tuple(positions[index]), index)
            penetration = max(0.0, clearance - signed)
            max_penetration = max(max_penetration, penetration)
            contact_violations += penetration > 0.0
    max_seam_gap = 0.0
    seam_violations = 0
    seam_errors = []
    for seam_index, seam in enumerate(seams):
        a, b = int(seam["a"]), int(seam["b"])
        error = abs(_length(_sub(tuple(positions[b]), tuple(positions[a])))
                    - float(seam.get("rest_gap", 0.0)))
        seam_errors.append(error)
        if seam_index not in broken:
            max_seam_gap = max(max_seam_gap, error)
            seam_violations += error > 0.0
    max_layer_violation = 0.0
    for order in orders:
        normal = _normalise(_vec(order["normal"], "layer_order.normal"))
        separation = _dot(_sub(tuple(positions[int(order["outer"])]),
                               tuple(positions[int(order["inner"])])), normal)
        max_layer_violation = max(max_layer_violation,
                                  max(0.0, float(order.get("gap", 0.0)) - separation))
    collision_count = 0
    min_collision_distance: Optional[float] = None
    if collision:
        target = float(collision["distance"])
        cell_size = float(collision.get("cell_size", target))
        excluded = _excluded_pairs(triangles)
        for a, b in _collision_pairs(positions, target, cell_size, excluded):
            distance = _length(_sub(tuple(positions[b]), tuple(positions[a])))
            if distance < target:
                collision_count += 1
                min_collision_distance = (distance if min_collision_distance is None
                                          else min(min_collision_distance, distance))
    pinned_contact_violations = 0
    for contact in contacts:
        clearance = float(contact.get("clearance", 0.0))
        for index in _indices(contact, len(positions), "contact"):
            if inverse_masses[index] == 0.0:
                signed, _ = _contact_sample(contact, tuple(positions[index]), index)
                pinned_contact_violations += clearance - signed > 0.0
    return {
        "iterations": iterations,
        "max_penetration": max_penetration,
        "contact_violations": contact_violations,
        "max_seam_gap": max_seam_gap,
        "seam_errors": seam_errors,
        "seam_violations": seam_violations,
        "broken_seams": sorted(broken),
        "collision_count": collision_count,
        "min_collision_distance": min_collision_distance,
        "max_layer_violation": max_layer_violation,
        "pinned_contact_violations": pinned_contact_violations,
    }


def solve_cross_constraints(state: Mapping[str, Any],
                            constraints: Mapping[str, Any], *,
                            iterations: int = 12,
                            tolerance: float = 1.0e-7) -> Dict[str, Any]:
    """Project a cloth state and return a typed verdict plus diagnostics.

    Vertex dictionaries require ``position`` and may include
    ``previous_position``, ``inverse_mass`` (zero pins a vertex), and ``layer``.
    The returned state is a deep copy; inputs are never mutated.
    """
    try:
        if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations <= 0:
            raise ConstraintInputError("iterations must be a positive integer")
        tolerance = _number(tolerance, "tolerance", low=0.0, strict=True)
        positions, previous, inverse_masses, layers, triangles = _validate_state(state)
        contacts, seams, orders, collision = _validate_constraints(
            constraints, len(positions))
    except (ConstraintInputError, TypeError, KeyError, ValueError) as error:
        return {
            "verdict": UNKNOWN_INVALID_CONSTRAINTS,
            "reasons": [str(error)],
            "state": copy.deepcopy(state),
            "diagnostics": {},
        }

    broken: set[int] = set()
    for _ in range(iterations):
        _seam_projection(positions, inverse_masses, seams, broken)
        _contact_projection(positions, previous, inverse_masses, contacts)
        _layer_projection(positions, inverse_masses, orders)
        _collision_projection(positions, inverse_masses, layers, triangles, collision)

    diagnostics = _diagnostics(positions, inverse_masses, layers, triangles,
                               contacts, seams, orders, collision, broken, iterations)
    unresolved = []
    if diagnostics["max_penetration"] > tolerance:
        unresolved.append("mannequin contact remains penetrated")
    if diagnostics["max_seam_gap"] > tolerance:
        unresolved.append("seam rest gap did not converge")
    if diagnostics["collision_count"]:
        unresolved.append("self-collisions remain")
    if diagnostics["max_layer_violation"] > tolerance:
        unresolved.append("layer ordering remains violated")

    output = copy.deepcopy(state)
    for vertex, position in zip(output["vertices"], positions):
        vertex["position"] = position
    output["triangles"] = [list(triangle) for triangle in triangles]
    return {
        "verdict": UNKNOWN_INFEASIBLE_CONSTRAINTS if unresolved else ANSWER,
        "reasons": unresolved or ["all active cross constraints satisfy tolerance"],
        "state": output,
        "diagnostics": diagnostics,
    }


def _physical_contributions(section: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    raw = section.get("contributions")
    if raw is None:
        raw = [{key: section[key] for key in
                ("target_center", "weight", "stiffness", "signal_kind")
                if key in section}]
    if not isinstance(raw, list) or not raw or any(not isinstance(x, Mapping) for x in raw):
        raise ConstraintInputError("section.contributions must be a non-empty list")
    return raw


def _validate_contribution(value: Mapping[str, Any], arm: str) -> str:
    _vec(value.get("target_center"), f"{arm}.target_center")
    _number(value.get("weight", 1.0), f"{arm}.weight", low=0.0, strict=True)
    _number(value.get("stiffness", 1.0), f"{arm}.stiffness", low=0.0, strict=True)
    kind = value.get("signal_kind", "geometry")
    if not isinstance(kind, str) or not kind.strip():
        raise ConstraintInputError("signal_kind must be a non-empty string")
    return kind


def _cross_sections(cross: Mapping[str, Any]
                    ) -> Tuple[Vec3, List[Mapping[str, Any]], str, bool]:
    if not isinstance(cross, Mapping):
        raise ConstraintInputError("cross must be a mapping")
    center = _vec(cross.get("center"), "cross.center")
    sections = cross.get("sections")
    if not isinstance(sections, list) or len(sections) != 6:
        raise ConstraintInputError("cross.sections must contain exactly six arms")
    by_id: Dict[str, Mapping[str, Any]] = {}
    kinds, needs_refinement = set(), False
    for section in sections:
        if not isinstance(section, Mapping):
            raise ConstraintInputError("every cross arm must be a mapping")
        arm = section.get("id")
        if arm not in CROSS_SECTION_DIRECTIONS or arm in by_id:
            raise ConstraintInputError("arm ids must be unique ±x, ±y, ±z")
        if "direction" in section:
            actual = _normalise(_vec(section["direction"], "section.direction"))
            if _length(_sub(actual, CROSS_SECTION_DIRECTIONS[arm])) > 1.0e-12:
                raise ConstraintInputError(f"arm {arm} direction contradicts its id")
        contributions = _physical_contributions(section)
        kinds.update(_validate_contribution(item, str(arm)) for item in contributions)
        if len(contributions) > 4:
            cells = section.get("refinement_cells")
            if cells is None:
                needs_refinement = True
            elif (not isinstance(cells, list) or not cells or len(cells) > 4
                  or any(not isinstance(cell, list) or not cell or len(cell) > 4
                         for cell in cells)):
                raise ConstraintInputError(
                    "refinement_cells must have at most four cells of at most four indices")
            else:
                flattened = [index for cell in cells for index in cell]
                if (sorted(flattened) != list(range(len(contributions)))
                        or len(flattened) != len(set(flattened))):
                    raise ConstraintInputError(
                        "refinement_cells must cover every contribution exactly once")
        by_id[str(arm)] = section
    if set(by_id) != set(CROSS_SECTION_DIRECTIONS):
        raise ConstraintInputError("cross requires all six signed axis arms")
    if len(kinds) != 1:
        raise ConstraintInputError(
            "different signal meanings require separate layers; they cannot share one vote")
    return center, [by_id[key] for key in sorted(by_id)], kinds.pop(), needs_refinement


def _energy(center: Vec3, contribution: Mapping[str, Any]) -> float:
    error = _sub(center, _vec(contribution["target_center"], "target_center"))
    return 0.5 * float(contribution.get("stiffness", 1.0)) * _dot(error, error)


def _facet_table(sections: Sequence[Mapping[str, Any]], center: Vec3
                 ) -> Dict[str, List[Dict[str, Any]]]:
    """Bound explanations to four slots without dropping physical inputs."""
    table: Dict[str, List[Dict[str, Any]]] = {}
    for section in sections:
        arm = str(section["id"])
        contributions = _physical_contributions(section)
        cells = section.get("refinement_cells")
        if cells is None:
            if len(contributions) > 4:
                table[arm] = []  # never pick an arbitrary four
                continue
            cells = [[index] for index in range(len(contributions))]
        table[arm] = [
            {"slot": slot, "contribution_indices": list(indices),
             "energy": math.fsum(_energy(center, contributions[i]) for i in indices),
             "nested": len(indices) > 1}
            for slot, indices in enumerate(cells)
        ]
    return table


def solve_cross_sections(cross: Mapping[str, Any], *, max_iterations: int = 32,
                         agreement_tolerance: float = 1.0e-6,
                         stability_tolerance: float = 1.0e-7,
                         relaxation: float = 0.5) -> Dict[str, Any]:
    """Jacobi-aggregate six arms; converge only on agreement and stability."""
    try:
        if (isinstance(max_iterations, bool) or not isinstance(max_iterations, int)
                or max_iterations <= 0):
            raise ConstraintInputError("max_iterations must be a positive integer")
        agreement_tolerance = _number(agreement_tolerance, "agreement_tolerance",
                                      low=0.0, strict=True)
        stability_tolerance = _number(stability_tolerance, "stability_tolerance",
                                      low=0.0, strict=True)
        relaxation = _number(relaxation, "relaxation", low=0.0, strict=True)
        if relaxation > 1.0:
            raise ConstraintInputError("relaxation must not exceed 1")
        center, sections, signal_kind, needs_refinement = _cross_sections(cross)
    except (ConstraintInputError, TypeError, KeyError, ValueError) as error:
        return {"verdict": UNKNOWN_INVALID_CONSTRAINTS, "reasons": [str(error)],
                "cross": copy.deepcopy(cross), "diagnostics": {}}

    arm_candidates: Dict[str, Vec3] = {}
    agreement = update_norm = math.inf
    performed = 0
    for performed in range(1, max_iterations + 1):
        old_center = center
        physical: List[Tuple[str, int, float, Vec3]] = []
        arm_candidates = {}
        for section in sections:  # canonical arm order; declared order is semantic
            arm, local = str(section["id"]), []
            for index, contribution in enumerate(_physical_contributions(section)):
                target = _vec(contribution["target_center"], "target_center")
                candidate = _add(old_center, _mul(_sub(target, old_center), relaxation))
                weight = float(contribution.get("weight", 1.0))
                physical.append((arm, index, weight, candidate))
                local.append((weight, candidate))
            denominator = math.fsum(weight for weight, _ in local)
            arm_candidates[arm] = tuple(
                math.fsum(weight * point[axis] for weight, point in local) / denominator
                for axis in range(3))
        denominator = math.fsum(item[2] for item in physical)
        center = tuple(math.fsum(weight * point[axis]
                                 for _arm, _index, weight, point in physical) / denominator
                       for axis in range(3))
        values = [arm_candidates[key] for key in sorted(arm_candidates)]
        agreement = max((_length(_sub(a, b)) for index, a in enumerate(values)
                         for b in values[index + 1:]), default=0.0)
        update_norm = _length(_sub(center, old_center))
        if agreement <= agreement_tolerance and update_norm <= stability_tolerance:
            break

    contribution_energy, energy_by_arm, physical_count = {}, {}, 0
    for section in sections:
        arm = str(section["id"])
        values = [_energy(center, item) for item in _physical_contributions(section)]
        contribution_energy[arm], energy_by_arm[arm] = values, math.fsum(values)
        physical_count += len(values)
    total_energy = math.fsum(energy_by_arm[key] for key in sorted(energy_by_arm))
    stable, agreed = update_norm <= stability_tolerance, agreement <= agreement_tolerance
    if needs_refinement:
        verdict, reasons = UNKNOWN_REFINEMENT_REQUIRED, [
            "an arm exceeds four facet slots; add explicit nested refinement_cells"]
    elif agreed and stable:
        verdict, reasons = ANSWER, ["all six arms agree and the center is stable"]
    elif not agreed:
        verdict, reasons = CONTESTED, [
            "arm candidates disagree; no tied alternative was selected"]
    else:
        verdict, reasons = UNKNOWN_NOT_STABLE, ["arms agree but center is not stable"]
    output = copy.deepcopy(cross)
    output["center"] = list(center)
    return {
        "verdict": verdict, "reasons": reasons, "cross": output,
        "diagnostics": {
            "aggregation": "JACOBI_SAME_OLD_CENTER", "signal_kind": signal_kind,
            "iterations": performed, "agreement": agreement, "update_norm": update_norm,
            "stable": stable, "agreed": agreed,
            "arm_candidates": {key: list(arm_candidates[key])
                               for key in sorted(arm_candidates)},
            "physical_contribution_count": physical_count,
            "contribution_energy_by_arm": contribution_energy,
            "energy_by_arm": energy_by_arm, "total_energy": total_energy,
            "facet_capacity": {"arms": 6, "slots_per_arm": 4, "total_slots": 24},
            "facet_table": _facet_table(sections, center),
        },
    }


def _layer_signature(cross: Mapping[str, Any]) -> Tuple[Any, ...]:
    sections = cross.get("sections", [])
    if not isinstance(sections, list):
        return ()
    return tuple(
        (section.get("id"),
         tuple(tuple(item.get("target_center", ()))
               for item in _physical_contributions(section)),
         tuple(item.get("signal_kind", "geometry")
               for item in _physical_contributions(section)))
        for section in sorted(sections, key=lambda item: item.get("id", "")))


def solve_cross_layers(layers: Sequence[Mapping[str, Any]], **solver_options: Any
                       ) -> Dict[str, Any]:
    """Overlay typed rough→medium→fine views; stop on abstention/unknown."""
    expected = ("rough", "medium", "fine")
    if (not isinstance(layers, (list, tuple)) or len(layers) != 3
            or any(not isinstance(stage, Mapping) for stage in layers)
            or tuple(stage.get("name") for stage in layers) != expected):
        return {"verdict": UNKNOWN_INVALID_CONSTRAINTS,
                "reasons": ["layers must be ordered rough, medium, fine"], "stages": []}
    subject_ids = [stage.get("cross", {}).get("subject_id")
                   if isinstance(stage.get("cross"), Mapping) else None
                   for stage in layers]
    if (any(not isinstance(value, str) or not value.strip() for value in subject_ids)
            or len(set(subject_ids)) != 1):
        return {"verdict": UNKNOWN_INVALID_CONSTRAINTS,
                "reasons": ["all resolution layers must name the same subject_id"],
                "stages": []}
    reports, prior_center, prior_signature = [], None, None
    for stage in layers:
        raw_cross = stage.get("cross")
        if not isinstance(raw_cross, Mapping):
            return {"verdict": UNKNOWN_INVALID_CONSTRAINTS,
                    "reasons": [f"{stage['name']}.cross must be a mapping"],
                    "stages": reports}
        cross, signature = copy.deepcopy(raw_cross), _layer_signature(raw_cross)
        if prior_signature is not None and signature == prior_signature:
            return {"verdict": UNKNOWN_INVALID_CONSTRAINTS,
                    "reasons": [f"{stage['name']} is an identity copy, not a finer view"],
                    "stages": reports}
        if prior_center is not None:
            cross["center"] = prior_center
        result = solve_cross_sections(cross, **solver_options)
        reports.append({"name": stage["name"],
                        "input_verdict": ANSWER if prior_center is not None else "ROOT_INPUT",
                        "result": result})
        if result["verdict"] != ANSWER:
            return {"verdict": result["verdict"],
                    "reasons": [f"pipeline stopped at {stage['name']}"] + result["reasons"],
                    "stages": reports}
        prior_center, prior_signature = result["cross"]["center"], signature
    return {"verdict": ANSWER,
            "reasons": ["rough, medium, and fine views converged in typed order"],
            "stages": reports, "cross": reports[-1]["result"]["cross"]}


# A short alias is useful to callers that already name the operation "project".
project_constraints = solve_cross_constraints


__all__ = [
    "ANSWER", "CONTESTED", "CROSS_SECTION_DIRECTIONS",
    "UNKNOWN_INVALID_CONSTRAINTS", "UNKNOWN_INFEASIBLE_CONSTRAINTS",
    "UNKNOWN_NOT_STABLE", "UNKNOWN_REFINEMENT_REQUIRED",
    "capsule_signed_distance", "project_constraints", "solve_cross_constraints",
    "solve_cross_layers", "solve_cross_sections", "sphere_signed_distance",
]
