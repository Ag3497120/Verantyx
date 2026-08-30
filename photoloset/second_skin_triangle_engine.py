# -*- coding: utf-8 -*-
"""Primitive-neutral triangulated second-skin candidate geometry.

This module is deliberately a geometry boundary, not a garment classifier or
sewing authority.  A caller describes surfaces using only:

* a vertical range;
* one or more independent radial components;
* optional angular coverage;
* a numeric layer; and
* explicit parent/child/port/ownership relations.

Consequently, one lower component can express a skirt-like shell, two lower
components can express trouser-like shells, and one upper/full component can
express a top or body shell without branching on garment names.  An overlay is
the same surface representation at a higher layer with an explicit relation.

Typed front polygons/triangles constrain only the visible front support.  Their
requested depth is always a ``PROPOSED`` candidate offset; no front cue can
observe or confirm the rear.  Every vertex proposal reads the same immutable
old mesh and is reduced once in a deterministic Jacobi-style step.

The result includes six-arm :mod:`photoloset.cross_lattice` data and candidate
mesh boundaries suitable for a later pattern stage.  It does *not* claim that
those boundaries are seams, that the surface is flattenable, or that anything
is sewable.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .cross_lattice import (
    Provenance,
    lattice_from_result,
    mesh_to_cross_lattice,
    typed_result_digest,
)


Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
Triangle = Tuple[int, int, int]
RadiusFn = Callable[[Mapping[str, Any], float, float], Optional[float]]

SCHEMA = "garment.second-skin-triangle-engine.v1"
PROPOSED = "PROPOSED"
UNRESOLVED = "UNRESOLVED"
ANSWER = "ANSWER"
UNKNOWN_INPUT = "UNKNOWN_SECOND_SKIN_TRIANGLE_INPUT"
UNKNOWN_BODY = "UNKNOWN_SECOND_SKIN_TRIANGLE_BODY"
UNKNOWN_SURFACE = "UNKNOWN_SECOND_SKIN_TRIANGLE_SURFACE"
UNKNOWN_CUE = "UNKNOWN_SECOND_SKIN_TRIANGLE_CUE"
UNKNOWN_RELATION = "UNKNOWN_SECOND_SKIN_TRIANGLE_RELATION"
UNKNOWN_LATTICE = "UNKNOWN_SECOND_SKIN_TRIANGLE_CROSS_LATTICE"

_EPS = 1.0e-10
_RELATION_KINDS = {"JOIN", "LAYER", "ATTACH"}
_ATTACHMENT_SIDES = {"LEFT", "RIGHT", "CENTER", "BILATERAL", "FULL"}
_CUE_STATES = {
    "OBSERVED", "PROPOSED", "GENERATED_FROM_OBSERVED_OUTLINE",
    "OBSERVED_THEN_TOPOLOGY_REPAIRED",
}


class _Refusal(Exception):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verdict": code,
        "state": UNRESOLVED,
        "why": why,
        "how_to_close": (
            "supply a finite body proxy, primitive-neutral surface domains, "
            "and explicit proposal-only relations/cues"
        ),
        **detail,
    }


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _number(value: Any, field: str, *, minimum: Optional[float] = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Refusal(UNKNOWN_INPUT, f"{field} must be a finite number", field=field)
    result = float(value)
    if not math.isfinite(result):
        raise _Refusal(UNKNOWN_INPUT, f"{field} must be finite", field=field)
    if minimum is not None and (result <= minimum if strict else result < minimum):
        operator = ">" if strict else ">="
        raise _Refusal(
            UNKNOWN_INPUT, f"{field} must be {operator} {minimum}", field=field,
            value=result,
        )
    return result


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _Refusal(
            UNKNOWN_INPUT, f"{field} must be an integer >= {minimum}", field=field,
        )
    return value


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec3, scale: float) -> Vec3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _unit(a: Vec3) -> Vec3:
    length = _norm(a)
    if length <= _EPS:
        return (0.0, 0.0, 1.0)
    return _mul(a, 1.0 / length)


def _pchip_slopes(xs: Sequence[float], values: Sequence[float]) -> Tuple[float, ...]:
    """Shape-preserving slopes for smooth body-section interpolation."""
    count = len(xs)
    if count == 2:
        slope = (values[1] - values[0]) / (xs[1] - xs[0])
        return (slope, slope)
    widths = [xs[i + 1] - xs[i] for i in range(count - 1)]
    deltas = [(values[i + 1] - values[i]) / widths[i]
              for i in range(count - 1)]
    slopes = [0.0] * count
    for index in range(1, count - 1):
        left, right = deltas[index - 1], deltas[index]
        if left == 0.0 or right == 0.0 or left * right < 0.0:
            slopes[index] = 0.0
        else:
            w1 = 2.0 * widths[index] + widths[index - 1]
            w2 = widths[index] + 2.0 * widths[index - 1]
            slopes[index] = (w1 + w2) / (w1 / left + w2 / right)

    def endpoint(h0: float, h1: float, d0: float, d1: float) -> float:
        result = ((2.0 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if result * d0 <= 0.0:
            return 0.0
        if d0 * d1 < 0.0 and abs(result) > abs(3.0 * d0):
            return 3.0 * d0
        return result

    slopes[0] = endpoint(widths[0], widths[1], deltas[0], deltas[1])
    slopes[-1] = endpoint(widths[-1], widths[-2], deltas[-1], deltas[-2])
    return tuple(slopes)


def _hermite(xs: Sequence[float], values: Sequence[float],
             slopes: Sequence[float], x: float) -> float:
    if x <= xs[0]:
        return values[0]
    if x >= xs[-1]:
        return values[-1]
    index = next(i for i in range(len(xs) - 1) if xs[i] <= x <= xs[i + 1])
    width = xs[index + 1] - xs[index]
    t = (x - xs[index]) / width
    h00 = 2.0 * t ** 3 - 3.0 * t ** 2 + 1.0
    h10 = t ** 3 - 2.0 * t ** 2 + t
    h01 = -2.0 * t ** 3 + 3.0 * t ** 2
    h11 = t ** 3 - t ** 2
    return (h00 * values[index] + h10 * width * slopes[index]
            + h01 * values[index + 1] + h11 * width * slopes[index + 1])


@dataclass(frozen=True)
class _BodyProxy:
    source: Mapping[str, Any]
    heights: Tuple[float, ...]
    radii_x: Tuple[float, ...]
    radii_z: Tuple[float, ...]
    slopes_x: Tuple[float, ...]
    slopes_z: Tuple[float, ...]
    radius_at: Optional[RadiusFn] = None

    def axes_at(self, y: float) -> Tuple[float, float]:
        if self.radius_at is not None:
            x = self.radius_at(self.source, y, 0.0)
            z = self.radius_at(self.source, y, math.pi / 2.0)
            if x is None or z is None:
                raise _Refusal(
                    UNKNOWN_BODY, f"body radius is unavailable at y={y}", y_cm=y,
                )
            rx = _number(x, "radius_at.x", minimum=0.0, strict=True)
            rz = _number(z, "radius_at.z", minimum=0.0, strict=True)
            return rx, rz
        return (
            _hermite(self.heights, self.radii_x, self.slopes_x, y),
            _hermite(self.heights, self.radii_z, self.slopes_z, y),
        )

    def normalized(self) -> Dict[str, Any]:
        return {
            "sections": [[y, x, z] for y, x, z in
                         zip(self.heights, self.radii_x, self.radii_z)],
            "interpolation": ("CALLABLE_RADIUS_AT" if self.radius_at is not None
                              else "MONOTONE_CUBIC_HERMITE"),
        }


def _body_proxy(raw: Any, radius_at: Optional[RadiusFn]) -> _BodyProxy:
    if not isinstance(raw, Mapping):
        raise _Refusal(UNKNOWN_BODY, "body_proxy must be a mapping")
    verdict = raw.get("verdict")
    if verdict is not None and verdict != ANSWER:
        raise _Refusal(
            UNKNOWN_BODY, "body_proxy upstream verdict is not ANSWER",
            upstream_verdict=verdict,
        )
    source_sections = raw.get("sections", raw.get("_levels"))
    if (not isinstance(source_sections, Sequence)
            or isinstance(source_sections, (str, bytes))
            or len(source_sections) < 2):
        raise _Refusal(
            UNKNOWN_BODY,
            "body_proxy needs at least two sections or mannequin _levels",
        )
    sections: List[Tuple[float, float, float]] = []
    for index, item in enumerate(source_sections):
        if isinstance(item, Mapping):
            y = _number(item.get("y_cm"), f"sections[{index}].y_cm")
            rx = _number(item.get("radius_x_cm"),
                         f"sections[{index}].radius_x_cm", minimum=0.0, strict=True)
            rz = _number(item.get("radius_z_cm"),
                         f"sections[{index}].radius_z_cm", minimum=0.0, strict=True)
        elif (isinstance(item, Sequence) and not isinstance(item, (str, bytes))
              and len(item) >= 3):
            y = _number(item[0], f"_levels[{index}][0]")
            rx = _number(item[1], f"_levels[{index}][1]", minimum=0.0, strict=True)
            rz = _number(item[2], f"_levels[{index}][2]", minimum=0.0, strict=True)
        else:
            raise _Refusal(UNKNOWN_BODY, f"body section {index} is malformed")
        sections.append((y, rx, rz))
    sections.sort()
    heights = tuple(row[0] for row in sections)
    if len(set(heights)) != len(heights):
        raise _Refusal(UNKNOWN_BODY, "body section heights must be unique")
    radii_x = tuple(row[1] for row in sections)
    radii_z = tuple(row[2] for row in sections)
    return _BodyProxy(
        copy.deepcopy(dict(raw)), heights, radii_x, radii_z,
        _pchip_slopes(heights, radii_x), _pchip_slopes(heights, radii_z),
        radius_at,
    )


@dataclass(frozen=True)
class _Component:
    component_id: str
    center_x_ratio: float
    center_z_ratio: float
    radius_x_ratio: float
    radius_z_ratio: float
    angle_start_deg: float
    angle_span_deg: float
    closed: bool

    def normalized(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "center_ratio": [self.center_x_ratio, self.center_z_ratio],
            "radius_ratio": [self.radius_x_ratio, self.radius_z_ratio],
            "angular_coverage_deg": [self.angle_start_deg,
                                     self.angle_start_deg + self.angle_span_deg],
            "closed": self.closed,
        }


@dataclass(frozen=True)
class _Surface:
    surface_id: str
    y_bottom: float
    y_top: float
    layer: int
    ease_cm: float
    material_id: str
    components: Tuple[_Component, ...]

    def normalized(self) -> Dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "y_range_cm": [self.y_bottom, self.y_top],
            "layer": self.layer,
            "ease_cm": self.ease_cm,
            "material_id": self.material_id,
            "components": [component.normalized() for component in self.components],
        }


def _coverage(raw: Mapping[str, Any], field: str) -> Tuple[float, float, bool]:
    value = raw.get("angular_coverage_deg", raw.get("azimuth_range_deg"))
    if value is None:
        return 0.0, 360.0, True
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or len(value) != 2):
        raise _Refusal(UNKNOWN_SURFACE, f"{field} must contain [start, end]")
    start = _number(value[0], f"{field}[0]")
    end = _number(value[1], f"{field}[1]")
    span = end - start
    if span <= 0.0 or span > 360.0 + _EPS:
        raise _Refusal(
            UNKNOWN_SURFACE, f"{field} must have 0 < span <= 360 degrees",
            angular_coverage_deg=[start, end],
        )
    closed = span >= 360.0 - _EPS
    return start, 360.0 if closed else span, closed


def _surfaces(raw: Any, body: _BodyProxy) -> Tuple[_Surface, ...]:
    if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw):
        raise _Refusal(UNKNOWN_SURFACE, "surfaces must be a non-empty sequence")
    parsed: List[_Surface] = []
    seen = set()
    for surface_index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise _Refusal(UNKNOWN_SURFACE, f"surfaces[{surface_index}] is not a mapping")
        surface_id = value.get("surface_id")
        if (not isinstance(surface_id, str) or not surface_id.strip()
                or surface_id in seen):
            raise _Refusal(
                UNKNOWN_SURFACE, "surface ids must be unique and non-empty",
                surface_id=surface_id,
            )
        seen.add(surface_id)
        y_range = value.get("y_range_cm")
        if (not isinstance(y_range, Sequence) or isinstance(y_range, (str, bytes))
                or len(y_range) != 2):
            raise _Refusal(UNKNOWN_SURFACE, f"{surface_id}.y_range_cm is malformed")
        lo = _number(y_range[0], f"{surface_id}.y_range_cm[0]")
        hi = _number(y_range[1], f"{surface_id}.y_range_cm[1]")
        if hi <= lo or lo < body.heights[0] - _EPS or hi > body.heights[-1] + _EPS:
            raise _Refusal(
                UNKNOWN_SURFACE, f"{surface_id} height range is outside the body proxy",
                y_range_cm=[lo, hi], body_range_cm=[body.heights[0], body.heights[-1]],
            )
        layer = _integer(value.get("layer", 0), f"{surface_id}.layer")
        ease = _number(value.get("ease_cm", 0.0), f"{surface_id}.ease_cm", minimum=0.0)
        material_id = value.get("material_id", "unmeasured")
        if not isinstance(material_id, str) or not material_id.strip():
            raise _Refusal(UNKNOWN_SURFACE, f"{surface_id}.material_id is invalid")
        raw_components = value.get("components")
        if (not isinstance(raw_components, Sequence)
                or isinstance(raw_components, (str, bytes)) or not raw_components):
            raise _Refusal(
                UNKNOWN_SURFACE,
                f"{surface_id} needs one or more explicit radial components",
            )
        components: List[_Component] = []
        component_ids = set()
        for component_index, component in enumerate(raw_components):
            if not isinstance(component, Mapping):
                raise _Refusal(UNKNOWN_SURFACE, f"{surface_id}.components is malformed")
            component_id = component.get("component_id")
            if (not isinstance(component_id, str) or not component_id.strip()
                    or component_id in component_ids):
                raise _Refusal(
                    UNKNOWN_SURFACE,
                    f"{surface_id} component ids must be unique and non-empty",
                )
            component_ids.add(component_id)
            center = component.get("center_ratio", [0.0, 0.0])
            radius = component.get("radius_ratio", [1.0, 1.0])
            if (not isinstance(center, Sequence) or isinstance(center, (str, bytes))
                    or len(center) != 2 or not isinstance(radius, Sequence)
                    or isinstance(radius, (str, bytes)) or len(radius) != 2):
                raise _Refusal(
                    UNKNOWN_SURFACE, f"{surface_id}/{component_id} ratios are malformed",
                )
            cx = _number(center[0], f"{surface_id}/{component_id}.center_ratio[0]")
            cz = _number(center[1], f"{surface_id}/{component_id}.center_ratio[1]")
            rx = _number(radius[0], f"{surface_id}/{component_id}.radius_ratio[0]",
                         minimum=0.0, strict=True)
            rz = _number(radius[1], f"{surface_id}/{component_id}.radius_ratio[1]",
                         minimum=0.0, strict=True)
            start, span, closed = _coverage(
                component if ("angular_coverage_deg" in component
                              or "azimuth_range_deg" in component) else value,
                f"{surface_id}/{component_id}.angular_coverage_deg",
            )
            components.append(_Component(
                component_id, cx, cz, rx, rz, start, span, closed,
            ))
        components.sort(key=lambda item: item.component_id)
        parsed.append(_Surface(
            surface_id, lo, hi, layer, ease, material_id, tuple(components),
        ))
    parsed.sort(key=lambda item: item.surface_id)
    return tuple(parsed)


def _relations(raw: Any, surfaces: Sequence[_Surface]) -> Tuple[Dict[str, Any], ...]:
    if raw is None:
        raw = []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise _Refusal(UNKNOWN_RELATION, "relations must be a sequence")
    by_id = {surface.surface_id: surface for surface in surfaces}
    parsed: List[Dict[str, Any]] = []
    child_owner: Dict[str, str] = {}
    relation_ids = set()
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise _Refusal(UNKNOWN_RELATION, f"relations[{index}] is not a mapping")
        parent = value.get("parent_id")
        child = value.get("child_id")
        if parent not in by_id or child not in by_id:
            raise _Refusal(
                UNKNOWN_RELATION, "relation references an unknown surface",
                parent_id=parent, child_id=child,
            )
        if parent == child:
            raise _Refusal(UNKNOWN_RELATION, "a surface cannot own itself", child_id=child)
        if child in child_owner:
            raise _Refusal(
                UNKNOWN_RELATION, "a child surface must have exactly one owner",
                child_id=child, owners=sorted((child_owner[child], str(parent))),
            )
        kind = value.get("kind")
        normalized_kind = kind.strip().upper() if isinstance(kind, str) else ""
        if normalized_kind not in _RELATION_KINDS:
            raise _Refusal(
                UNKNOWN_RELATION, "relation kind must be JOIN, LAYER, or ATTACH",
                relation_kind=kind,
            )
        relation_state = value.get("state", PROPOSED)
        if (not isinstance(relation_state, str)
                or relation_state.strip().upper() != PROPOSED):
            raise _Refusal(
                UNKNOWN_RELATION,
                "relation authority must remain explicitly PROPOSED",
                relation_state=relation_state,
            )
        port = value.get("attachment_port")
        if not isinstance(port, str) or not port.strip():
            raise _Refusal(UNKNOWN_RELATION, "attachment_port must be explicit")
        ownership = value.get("ownership")
        if isinstance(ownership, Mapping):
            owner_id = ownership.get("owner_id")
            ownership_state = ownership.get("state", PROPOSED)
        else:
            owner_id = ownership
            ownership_state = value.get("ownership_state", PROPOSED)
        if owner_id != parent:
            raise _Refusal(
                UNKNOWN_RELATION, "ownership must exactly name parent_id",
                parent_id=parent, owner_id=owner_id,
            )
        if (not isinstance(ownership_state, str)
                or ownership_state.strip().upper() != PROPOSED):
            raise _Refusal(
                UNKNOWN_RELATION, "ownership authority must remain PROPOSED",
                ownership_state=ownership_state,
            )
        child_layer = by_id[str(child)].layer
        parent_layer = by_id[str(parent)].layer
        declared_layer = value.get("layer")
        if declared_layer != child_layer:
            raise _Refusal(
                UNKNOWN_RELATION, "relation layer must equal the child surface layer",
                child_id=child, relation_layer=declared_layer,
                child_layer=child_layer,
            )
        if normalized_kind == "LAYER" and child_layer <= parent_layer:
            raise _Refusal(
                UNKNOWN_RELATION, "LAYER child must be strictly outside its parent",
                parent_layer=parent_layer, child_layer=child_layer,
            )
        if normalized_kind == "JOIN" and child_layer != parent_layer:
            raise _Refusal(
                UNKNOWN_RELATION, "JOIN requires parent and child on the same layer",
                parent_layer=parent_layer, child_layer=child_layer,
            )
        if normalized_kind == "ATTACH" and child_layer < parent_layer:
            raise _Refusal(
                UNKNOWN_RELATION, "ATTACH child cannot be inside its parent layer",
                parent_layer=parent_layer, child_layer=child_layer,
            )
        side = value.get("attachment_side", "FULL")
        normalized_side = side.strip().upper() if isinstance(side, str) else ""
        if normalized_side not in _ATTACHMENT_SIDES:
            raise _Refusal(
                UNKNOWN_RELATION, "attachment_side is not a typed side",
                attachment_side=side,
            )
        relation_id = value.get(
            "relation_id", f"{normalized_kind.lower()}:{parent}->{child}:{port}")
        if (not isinstance(relation_id, str) or not relation_id.strip()
                or relation_id in relation_ids):
            raise _Refusal(UNKNOWN_RELATION, "relation ids must be unique and non-empty")
        relation_ids.add(relation_id)
        child_owner[str(child)] = str(parent)
        parsed.append({
            "relation_id": relation_id,
            "kind": normalized_kind,
            "state": PROPOSED,
            "parent_id": parent,
            "child_id": child,
            "attachment_port": port,
            "attachment_side": normalized_side,
            "ownership": {
                "owner_id": parent,
                "state": PROPOSED,
                "observed": False,
                "approved": False,
                "authority_granted": False,
            },
            "parent_layer": parent_layer,
            "child_layer": child_layer,
            "seam_join_created": False,
            "rear_observed": False,
        })

    # Every non-root outer layer must declare who owns it.
    missing = sorted(surface.surface_id for surface in surfaces
                     if surface.layer > 0 and surface.surface_id not in child_owner)
    if missing:
        raise _Refusal(
            UNKNOWN_RELATION, "every surface above layer zero needs an explicit owner",
            missing_child_ids=missing,
        )

    # Parent pointers form a forest.  A deterministic walk rejects cycles.
    for child in sorted(child_owner):
        visited = set()
        current = child
        while current in child_owner:
            if current in visited:
                raise _Refusal(
                    UNKNOWN_RELATION, "surface ownership contains a cycle",
                    cycle_start=current,
                )
            visited.add(current)
            current = child_owner[current]
    parsed.sort(key=lambda item: item["relation_id"])
    return tuple(parsed)


def _points(raw: Any, cue_id: str, kind: str) -> Tuple[Vec2, ...]:
    if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
            or len(raw) < 3):
        raise _Refusal(UNKNOWN_CUE, f"{cue_id} needs at least three points")
    result: List[Vec2] = []
    for index, point in enumerate(raw):
        if (not isinstance(point, Sequence) or isinstance(point, (str, bytes))
                or len(point) != 2):
            raise _Refusal(UNKNOWN_CUE, f"{cue_id}.points[{index}] is malformed")
        result.append((_number(point[0], f"{cue_id}.points[{index}].x"),
                       _number(point[1], f"{cue_id}.points[{index}].y")))
    if kind == "TRIANGLE" and len(result) != 3:
        raise _Refusal(UNKNOWN_CUE, f"{cue_id} TRIANGLE must contain exactly 3 points")
    area = 0.5 * math.fsum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(result, result[1:] + result[:1])
    )
    if abs(area) <= _EPS:
        raise _Refusal(UNKNOWN_CUE, f"{cue_id} polygon has zero area")
    return tuple(result)


def _cues(raw: Any, surfaces: Sequence[_Surface]) -> Tuple[Dict[str, Any], ...]:
    if raw is None:
        raw = []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise _Refusal(UNKNOWN_CUE, "front_cues must be a sequence")
    surface_ids = {surface.surface_id for surface in surfaces}
    parsed: List[Dict[str, Any]] = []
    seen = set()
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise _Refusal(UNKNOWN_CUE, f"front_cues[{index}] is not a mapping")
        cue_id = value.get("cue_id", value.get("id"))
        if not isinstance(cue_id, str) or not cue_id.strip() or cue_id in seen:
            raise _Refusal(UNKNOWN_CUE, "cue ids must be unique and non-empty")
        seen.add(cue_id)
        surface_id = value.get("surface_id")
        if surface_id not in surface_ids:
            raise _Refusal(
                UNKNOWN_CUE, f"{cue_id} targets an unknown surface",
                surface_id=surface_id,
            )
        kind = value.get("kind", value.get("type", "POLYGON"))
        normalized_kind = kind.strip().upper() if isinstance(kind, str) else ""
        if normalized_kind not in {"POLYGON", "TRIANGLE"}:
            raise _Refusal(UNKNOWN_CUE, f"{cue_id} must be POLYGON or TRIANGLE")
        state = value.get("state", PROPOSED)
        normalized_state = state.strip().upper() if isinstance(state, str) else ""
        if normalized_state not in _CUE_STATES:
            raise _Refusal(
                UNKNOWN_CUE, f"{cue_id} has unsupported evidence state", state=state,
            )
        coordinate_space = value.get("coordinate_space", "BODY_CM_FRONT")
        if coordinate_space != "BODY_CM_FRONT":
            raise _Refusal(
                UNKNOWN_CUE,
                f"{cue_id} coordinate_space must be BODY_CM_FRONT",
                coordinate_space=coordinate_space,
            )
        points = _points(value.get("points_cm", value.get("points")),
                         cue_id, normalized_kind)
        offset = _number(value.get("offset_cm"), f"{cue_id}.offset_cm", minimum=0.0)
        weight = _number(value.get("weight", 1.0), f"{cue_id}.weight",
                         minimum=0.0, strict=True)
        parsed.append({
            "cue_id": cue_id,
            "surface_id": surface_id,
            "kind": normalized_kind,
            "points_cm": [list(point) for point in points],
            "support_state": normalized_state,
            "geometry_state": PROPOSED,
            "coordinate_space": coordinate_space,
            "offset_cm": offset,
            "offset_state": PROPOSED,
            "weight": weight,
            "front_only": True,
            "rear_observed": False,
            "source_id": value.get("source_id"),
        })
    parsed.sort(key=lambda item: item["cue_id"])
    return tuple(parsed)


def _point_on_segment(point: Vec2, a: Vec2, b: Vec2) -> bool:
    cross = ((b[0] - a[0]) * (point[1] - a[1])
             - (b[1] - a[1]) * (point[0] - a[0]))
    if abs(cross) > _EPS:
        return False
    dot = ((point[0] - a[0]) * (point[0] - b[0])
           + (point[1] - a[1]) * (point[1] - b[1]))
    return dot <= _EPS


def _inside_polygon(point: Vec2, points: Sequence[Sequence[float]]) -> bool:
    polygon = [(float(item[0]), float(item[1])) for item in points]
    if any(_point_on_segment(point, a, b)
           for a, b in zip(polygon, polygon[1:] + polygon[:1])):
        return True
    inside = False
    x, y = point
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) == (b[1] > y):
            continue
        crossing_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        if x < crossing_x:
            inside = not inside
    return inside


def _boundary_record(boundary_id: str, surface_id: str, component_id: str,
                     kind: str, vertex_ids: Sequence[int], *, mesh_boundary: bool,
                     closed_loop: bool,
                     relation_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "boundary_id": boundary_id,
        "surface_id": surface_id,
        "component_id": component_id,
        "kind": kind,
        "state": PROPOSED,
        "vertex_ids": list(vertex_ids),
        "closed_loop": closed_loop,
        "is_mesh_boundary": mesh_boundary,
        "pattern_boundary_candidate": True,
        "pattern_ready_geometry": True,
        "downstream_stage": "PATTERN_FLATTENING_INPUT",
        "relation_id": relation_id,
        "observed_as_seam": False,
        "sewability_evaluated": False,
        "sewability_claimed": False,
    }


def _nearest_endpoint_loops(
        surface_components: Mapping[str, List[Dict[str, Any]]], surface_id: str,
        other: _Surface) -> List[List[int]]:
    surface_entries = surface_components[surface_id]
    surface = surface_entries[0]["surface"]
    choices = (
        (abs(surface.y_bottom - other.y_bottom), "lower_loop"),
        (abs(surface.y_bottom - other.y_top), "lower_loop"),
        (abs(surface.y_top - other.y_bottom), "upper_loop"),
        (abs(surface.y_top - other.y_top), "upper_loop"),
    )
    field = min(choices, key=lambda item: (item[0], item[1]))[1]
    return [list(entry[field]) for entry in surface_entries]


def build(request: Mapping[str, Any], *, radius_at: Optional[RadiusFn] = None
          ) -> Dict[str, Any]:
    """Build proposal-only triangulated surfaces from typed geometric inputs."""
    try:
        if not isinstance(request, Mapping):
            raise _Refusal(UNKNOWN_INPUT, "request must be a mapping")
        raw_body = request.get("body_proxy", request.get("mannequin"))
        body = _body_proxy(raw_body, radius_at)
        surfaces = _surfaces(request.get("surfaces"), body)
        relations = _relations(request.get("relations", []), surfaces)
        cues = _cues(request.get("front_cues", []), surfaces)
        resolution = request.get("resolution", {})
        if not isinstance(resolution, Mapping):
            raise _Refusal(UNKNOWN_INPUT, "resolution must be a mapping")
        segments = _integer(resolution.get("angular_segments", 24),
                            "resolution.angular_segments", minimum=6)
        height_steps = _integer(resolution.get("height_steps", 12),
                                "resolution.height_steps", minimum=2)
        layer_gap = _number(request.get("layer_gap_cm", 0.25),
                            "layer_gap_cm", minimum=0.0, strict=True)

        normalized_input = {
            "body_proxy": body.normalized(),
            "surfaces": [surface.normalized() for surface in surfaces],
            "relations": list(relations),
            "front_cues": list(cues),
            "resolution": {"angular_segments": segments,
                           "height_steps": height_steps},
            "layer_gap_cm": layer_gap,
        }
        input_digest = _digest(normalized_input)

        vertices_old: List[Vec3] = []
        vertex_meta: List[Dict[str, Any]] = []
        triangles: List[Triangle] = []
        triangle_surface_ids: List[str] = []
        surface_components: Dict[str, List[Dict[str, Any]]] = {
            surface.surface_id: [] for surface in surfaces}
        component_reports: List[Dict[str, Any]] = []

        for surface in surfaces:
            ys = [surface.y_bottom + (surface.y_top - surface.y_bottom) * row
                  / height_steps for row in range(height_steps + 1)]
            for component in surface.components:
                vertex_start = len(vertices_old)
                angular_count = segments if component.closed else segments + 1
                ring_loops: List[List[int]] = []
                for ring_index, y in enumerate(ys):
                    body_x, body_z = body.axes_at(y)
                    center_x = component.center_x_ratio * body_x
                    center_z = component.center_z_ratio * body_z
                    radius_x = component.radius_x_ratio * body_x + surface.ease_cm
                    radius_z = component.radius_z_ratio * body_z + surface.ease_cm
                    ring: List[int] = []
                    for angular_index in range(angular_count):
                        denominator = segments
                        angle_deg = (component.angle_start_deg
                                     + component.angle_span_deg * angular_index / denominator)
                        theta = math.radians(angle_deg)
                        position = (
                            center_x + radius_x * math.cos(theta),
                            y,
                            center_z + radius_z * math.sin(theta),
                        )
                        vertex_id = len(vertices_old)
                        vertices_old.append(position)
                        ring.append(vertex_id)
                        vertex_meta.append({
                            "vertex_id": vertex_id,
                            "surface_id": surface.surface_id,
                            "component_id": component.component_id,
                            "ring_index": ring_index,
                            "angular_index": angular_index,
                            "theta_deg": angle_deg,
                            "center_x_cm": center_x,
                            "center_z_cm": center_z,
                            "layer": surface.layer,
                            "front_hemisphere": math.sin(theta) >= -_EPS,
                        })
                    ring_loops.append(ring)
                for ring_index in range(height_steps):
                    lower, upper = ring_loops[ring_index], ring_loops[ring_index + 1]
                    span_count = segments
                    for angular_index in range(span_count):
                        nxt = ((angular_index + 1) % angular_count
                               if component.closed else angular_index + 1)
                        # Outward-oriented deterministic split of each grid cell.
                        triangles.extend((
                            (lower[angular_index], upper[nxt], lower[nxt]),
                            (lower[angular_index], upper[angular_index], upper[nxt]),
                        ))
                        triangle_surface_ids.extend((surface.surface_id,
                                                     surface.surface_id))
                entry = {
                    "surface": surface,
                    "component": component,
                    "lower_loop": tuple(ring_loops[0]),
                    "upper_loop": tuple(ring_loops[-1]),
                    "rings": tuple(tuple(ring) for ring in ring_loops),
                    "vertex_range": [vertex_start, len(vertices_old)],
                }
                surface_components[surface.surface_id].append(entry)
                component_reports.append({
                    "surface_id": surface.surface_id,
                    "component_id": component.component_id,
                    "closed_radial_shell": component.closed,
                    "vertex_range": [vertex_start, len(vertices_old)],
                    "vertex_count": len(vertices_old) - vertex_start,
                    "triangle_count": height_steps * segments * 2,
                    "topological_component": (
                        f"{surface.surface_id}/{component.component_id}"),
                })

        old_state_digest = _digest([[round(value, 12) for value in vertex]
                                    for vertex in vertices_old])
        cues_by_surface: Dict[str, List[Mapping[str, Any]]] = {}
        for cue in cues:
            cues_by_surface.setdefault(str(cue["surface_id"]), []).append(cue)
        cue_matches: Dict[str, List[int]] = {str(cue["cue_id"]): [] for cue in cues}
        vertices: List[Vec3] = []
        vertex_states: List[Dict[str, Any]] = []
        proposal_rows: List[Dict[str, Any]] = []

        # Proposal phase: every row reads vertices_old; no proposal sees a peer.
        for old, meta in zip(vertices_old, vertex_meta):
            radial_normal = _unit((old[0] - float(meta["center_x_cm"]), 0.0,
                                   old[2] - float(meta["center_z_cm"])))
            layer_offset = int(meta["layer"]) * layer_gap
            matches: List[Mapping[str, Any]] = []
            if bool(meta["front_hemisphere"]):
                for cue in cues_by_surface.get(str(meta["surface_id"]), []):
                    if _inside_polygon((old[0], old[1]), cue["points_cm"]):
                        matches.append(cue)
                        cue_matches[str(cue["cue_id"])].append(int(meta["vertex_id"]))
            cue_offset = 0.0
            if matches:
                denominator = math.fsum(float(cue["weight"]) for cue in matches)
                cue_offset = math.fsum(
                    float(cue["weight"]) * float(cue["offset_cm"])
                    for cue in matches) / denominator
            total_offset = layer_offset + cue_offset
            final = _add(old, _mul(radial_normal, total_offset))
            vertices.append(final)
            proposal_rows.append({
                "vertex_id": meta["vertex_id"],
                "read_position_cm": list(old),
                "read_state_digest": old_state_digest,
                "layer_offset_cm": layer_offset,
                "front_cue_offset_cm": cue_offset,
                "matched_cue_ids": sorted(str(cue["cue_id"]) for cue in matches),
                "reduced_position_cm": list(final),
            })
            if not bool(meta["front_hemisphere"]):
                evidence_state = "PROPOSED_UNOBSERVED_REAR"
            elif matches:
                evidence_state = "PROPOSED_FROM_TYPED_FRONT_SUPPORT"
            else:
                evidence_state = "PROPOSED_UNCONSTRAINED_FRONT"
            vertex_states.append({
                **meta,
                "evidence_state": evidence_state,
                "geometry_state": PROPOSED,
                "rear_observed": False,
                "matched_cue_ids": sorted(str(cue["cue_id"]) for cue in matches),
            })

        proposal_digest = _digest(proposal_rows)
        jacobi = {
            "aggregation": "JACOBI_SAME_OLD_STATE_THEN_DETERMINISTIC_REDUCE",
            "old_state_digest": old_state_digest,
            "all_proposals_read_same_old_state": all(
                row["read_state_digest"] == old_state_digest for row in proposal_rows),
            "proposal_count": len(proposal_rows),
            "proposal_digest": proposal_digest,
            "reducer": (
                "add explicit layer clearance and weighted-mean overlapping "
                "front cue offsets after all proposals are formed"
            ),
            "in_place_updates": False,
        }

        cue_projection = []
        for cue in cues:
            matched = sorted(cue_matches[str(cue["cue_id"])])
            cue_projection.append({
                **copy.deepcopy(dict(cue)),
                "matched_vertex_ids": matched,
                "matched_front_vertex_count": len(matched),
                "matched_rear_vertex_count": 0,
                "projection_state": PROPOSED,
                "depth_observed": False,
            })

        boundaries: List[Dict[str, Any]] = []
        for surface_id in sorted(surface_components):
            for entry in surface_components[surface_id]:
                component = entry["component"]
                component_id = component.component_id
                boundaries.extend((
                    _boundary_record(
                        f"{surface_id}/{component_id}:lower", surface_id,
                        component_id, "OPEN_LOWER_BOUNDARY",
                        entry["lower_loop"], mesh_boundary=True,
                        closed_loop=component.closed,
                    ),
                    _boundary_record(
                        f"{surface_id}/{component_id}:upper", surface_id,
                        component_id, "OPEN_UPPER_BOUNDARY",
                        entry["upper_loop"], mesh_boundary=True,
                        closed_loop=component.closed,
                    ),
                ))
                rings = entry["rings"]
                if component.closed:
                    # A closed shell needs a release path before flattening.  It
                    # is a candidate only; the rear location is not observed.
                    release_index = min(
                        range(len(rings[0])),
                        key=lambda index: (
                            vertices_old[rings[0][index]][2]
                            - float(vertex_meta[rings[0][index]]["center_z_cm"]),
                            index,
                        ),
                    )
                    release = [ring[release_index] for ring in rings]
                    boundaries.append(_boundary_record(
                        f"{surface_id}/{component_id}:release", surface_id,
                        component_id, "RELEASE_SEAM_CANDIDATE", release,
                        mesh_boundary=False, closed_loop=False,
                    ))
                else:
                    boundaries.extend((
                        _boundary_record(
                            f"{surface_id}/{component_id}:side-a", surface_id,
                            component_id, "OPEN_SIDE_BOUNDARY",
                            [ring[0] for ring in rings], mesh_boundary=True,
                            closed_loop=False,
                        ),
                        _boundary_record(
                            f"{surface_id}/{component_id}:side-b", surface_id,
                            component_id, "OPEN_SIDE_BOUNDARY",
                            [ring[-1] for ring in rings], mesh_boundary=True,
                            closed_loop=False,
                        ),
                    ))

        by_surface = {surface.surface_id: surface for surface in surfaces}
        relation_boundaries = []
        for relation in relations:
            parent = by_surface[str(relation["parent_id"])]
            child = by_surface[str(relation["child_id"])]
            parent_loops = _nearest_endpoint_loops(
                surface_components, parent.surface_id, child)
            child_loops = _nearest_endpoint_loops(
                surface_components, child.surface_id, parent)
            relation_boundaries.append({
                "boundary_id": f"relation:{relation['relation_id']}",
                "relation_id": relation["relation_id"],
                "kind": "ATTACHMENT_PORT_BOUNDARY_CANDIDATE",
                "state": PROPOSED,
                "attachment_port": relation["attachment_port"],
                "attachment_side": relation["attachment_side"],
                "parent_surface_id": parent.surface_id,
                "child_surface_id": child.surface_id,
                "parent_vertex_loops": parent_loops,
                "child_vertex_loops": child_loops,
                "pattern_boundary_candidate": True,
                "pattern_ready_geometry": True,
                "downstream_stage": "PATTERN_FLATTENING_INPUT",
                "length_match_evaluated": False,
                "observed_as_seam": False,
                "sewability_evaluated": False,
                "sewability_claimed": False,
            })
        boundaries.sort(key=lambda item: item["boundary_id"])
        relation_boundaries.sort(key=lambda item: item["boundary_id"])

        lattice_result = mesh_to_cross_lattice(
            [[coordinate / 100.0 for coordinate in vertex] for vertex in vertices],
            triangles,
            face_material_ids=[by_surface[surface_id].material_id
                               for surface_id in triangle_surface_ids],
            provenance=Provenance(
                "second-skin-triangle-engine",
                "primitive-neutral candidate mesh to six-arm cross lattice",
                "1",
                (
                    "centimetre candidate geometry converted to metres",
                    "rear geometry remains proposed",
                    "material ids are labels, not calibrated constitutive laws",
                ),
            ),
        )
        if lattice_result.get("verdict") != ANSWER:
            raise _Refusal(
                UNKNOWN_LATTICE, "generated triangles did not form a valid cross lattice",
                cross_lattice=lattice_result,
            )
        lattice = lattice_from_result(lattice_result)
        cross_lattice_digest = lattice.semantic_digest()

        mesh_payload = {
            "vertices_cm": [[round(value, 12) for value in vertex]
                            for vertex in vertices],
            "triangles": [list(face) for face in triangles],
            "triangle_surface_ids": triangle_surface_ids,
        }
        topology = {
            "surface_count": len(surfaces),
            "surfaces": [surface.normalized() for surface in surfaces],
            "topological_component_count": sum(len(surface.components)
                                               for surface in surfaces),
            "components": component_reports,
            "relations": list(relations),
            "relation_digest": _digest(relations),
            "name_based_branching": False,
            "topology_basis": (
                "explicit component domains and explicit ownership relations"
            ),
        }
        manufacturing_boundary = {
            "pattern_boundary_candidates": boundaries,
            "attachment_boundary_candidates": relation_boundaries,
            "digest": _digest({"mesh": boundaries,
                               "relations": relation_boundaries}),
            "state": PROPOSED,
            "flattenability_evaluated": False,
            "sewability": "NOT_EVALUATED",
            "sewability_claimed": False,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "seam_allowance_defined": False,
            "sewing_order_defined": False,
        }
        provenance = {
            "method": "primitive-neutral smooth second-skin triangulation",
            "body_interpolation": body.normalized()["interpolation"],
            "cross_architecture": (
                "six local arms plus same-old-state deterministic reduction"
            ),
            "raw_garment_name_consumed": False,
            "image_name_based_branching": False,
            "front_depth_observed": False,
            "rear_observed": False,
            "generated_geometry_state": PROPOSED,
            "input_digest": input_digest,
            "mesh_digest": _digest(mesh_payload),
            "cue_digest": _digest(cue_projection),
            "cross_lattice_digest": cross_lattice_digest,
            "proposal_digest": proposal_digest,
        }
        result: Dict[str, Any] = {
            "schema": SCHEMA,
            "verdict": PROPOSED,
            "state": PROPOSED,
            "geometry_verdict": ANSWER,
            "what": "primitive-neutral triangulated second-skin candidate",
            "mesh": mesh_payload,
            "vertex_states": vertex_states,
            "topology": topology,
            "front_cue_projections": cue_projection,
            "rear": {
                "state": PROPOSED,
                "observed": False,
                "basis": "body proxy plus generated continuation; no rear pixels",
            },
            "jacobi_reduction": jacobi,
            "cross_lattice": lattice_result["lattice"],
            "cross_lattice_digest": cross_lattice_digest,
            "pattern_interface": manufacturing_boundary,
            "authority": {
                "highest_state": PROPOSED,
                "observed_geometry": False,
                "approved": False,
                "sewability_claimed": False,
            },
            "provenance": provenance,
            "limitations": [
                "front polygons constrain support only; their 3D depth is proposed",
                "unobserved rear surfaces remain proposed",
                "boundary loops are candidates, not confirmed seams",
                "flattenability, seam allowance, construction method and sewability are not evaluated",
            ],
        }
        result["digest"] = typed_result_digest(result)
        return result
    except _Refusal as refusal:
        return _unknown(refusal.code, refusal.why, **refusal.detail)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _unknown(UNKNOWN_INPUT, str(exc))


generate = build
build_second_skin_triangles = build


__all__ = [
    "ANSWER", "PROPOSED", "SCHEMA", "UNKNOWN_BODY", "UNKNOWN_CUE",
    "UNKNOWN_INPUT", "UNKNOWN_LATTICE", "UNKNOWN_RELATION", "UNKNOWN_SURFACE",
    "build", "build_second_skin_triangles", "generate",
]
