# -*- coding: utf-8 -*-
"""Deterministic avatar clearance for an editable fused target surface.

This is deliberately narrower than cloth simulation.  It projects target
vertices that penetrate a measurement-bound elliptical avatar envelope to
the outside of that envelope plus the requested cloth thickness.  It does
not predict drape, ease, stretch, pressure, material behaviour, or sewing
fitness.  The output therefore remains a PROPOSED geometric preview even
after a person edits the target surface.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Set, Tuple


REQUEST_SCHEMA = "garment.target-sculpt-clearance.request.v1"
SCHEMA = "garment.target-sculpt-clearance.v1"


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray))


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _unknown(code: str, why: str) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verdict": code,
        "why": why,
        "state": "UNKNOWN",
        "manufacturing_ready": False,
        "fact_promotions": [],
    }


def _measurements(value: Any) -> Dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    result: Dict[str, float] = {}
    for key in ("height", "chest_bust", "waist", "hip"):
        number = _finite(value.get(key))
        if number is None or number <= 0:
            return None
        result[key] = number
    return result


def _profile_circumference(
        t: float, chest: float, waist: float, hip: float) -> float:
    """Piecewise-linear body envelope from target bottom to target top.

    The vertical registration is intentionally inspectable and conservative;
    it is not an anatomical population model.  The selected avatar remains
    the only source of circumferences.
    """
    knots: List[Tuple[float, float]] = [
        (0.00, hip * 0.34),
        (0.20, hip * 0.46),
        (0.42, hip * 0.70),
        (0.54, hip),
        (0.66, waist),
        (0.84, chest),
        (0.93, chest * 0.82),
        (1.00, chest * 0.46),
    ]
    bounded = min(1.0, max(0.0, t))
    for index in range(len(knots) - 1):
        left_t, left_value = knots[index]
        right_t, right_value = knots[index + 1]
        if bounded <= right_t:
            fraction = (bounded - left_t) / max(right_t - left_t, 1.0e-12)
            return left_value + (right_value - left_value) * fraction
    return knots[-1][1]


def solve_target_sculpt_clearance(request: Mapping[str, Any]) -> Dict[str, Any]:
    if request.get("schema") != REQUEST_SCHEMA:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_CLEARANCE_SCHEMA",
            f"request schema must be {REQUEST_SCHEMA}",
        )
    surface = request.get("sculpt_surface")
    if not isinstance(surface, Mapping):
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_SURFACE_REQUIRED",
            "sculpt_surface must contain vertices_cm and faces",
        )
    raw_vertices, raw_faces = surface.get("vertices_cm"), surface.get("faces")
    surface_mode = str(surface.get("surface_mode", "AVATAR_ENVELOPE")).upper()
    if surface_mode not in {"AVATAR_ENVELOPE", "FRONT_CONFORMAL_SHELL"}:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_SURFACE_MODE",
            "surface_mode must be AVATAR_ENVELOPE or FRONT_CONFORMAL_SHELL",
        )
    if not _sequence(raw_vertices) or not raw_vertices:
        return _unknown("UNKNOWN_TARGET_SCULPT_VERTICES", "vertices_cm is required")
    vertices: List[List[float]] = []
    for row in raw_vertices:
        if not _sequence(row) or len(row) < 3:
            return _unknown("UNKNOWN_TARGET_SCULPT_VERTICES", "every vertex needs xyz")
        point = [_finite(row[0]), _finite(row[1]), _finite(row[2])]
        if any(value is None for value in point):
            return _unknown("UNKNOWN_TARGET_SCULPT_VERTICES", "vertices must be finite")
        vertices.append([float(value) for value in point])
    if not _sequence(raw_faces) or not raw_faces:
        return _unknown("UNKNOWN_TARGET_SCULPT_FACES", "faces is required")
    faces: List[List[int]] = []
    for row in raw_faces:
        if (not _sequence(row) or len(row) < 3
                or any(isinstance(value, bool) or not isinstance(value, int)
                       for value in row)):
            return _unknown("UNKNOWN_TARGET_SCULPT_FACES", "faces need integer indices")
        face = [int(value) for value in row]
        if any(index < 0 or index >= len(vertices) for index in face):
            return _unknown("UNKNOWN_TARGET_SCULPT_FACES", "face index is out of range")
        faces.append(face)
    measurements = _measurements(request.get("avatar_measurements_cm"))
    if measurements is None:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_AVATAR_MEASUREMENTS",
            "height, chest_bust, waist and hip are required",
        )
    thickness_mm = _finite(request.get("cloth_thickness_mm"))
    if thickness_mm is None or not 0.1 <= thickness_mm <= 12.0:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_THICKNESS",
            "cloth_thickness_mm must be within 0.1..12.0",
        )
    removed_raw = request.get("removed_face_indices", [])
    if not _sequence(removed_raw) or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in removed_raw):
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_REMOVED_FACES",
            "removed_face_indices must be integer face ids",
        )
    removed: Set[int] = {int(value) for value in removed_raw}
    if any(index < 0 or index >= len(faces) for index in removed):
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_REMOVED_FACES",
            "removed face index is out of range",
        )

    active_faces = [face for index, face in enumerate(faces) if index not in removed]
    if not active_faces:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_EMPTY_AFTER_EDIT",
            "all target faces were removed",
        )
    active_vertices = sorted({index for face in active_faces for index in face})
    xs = [vertices[index][0] for index in active_vertices]
    ys = [vertices[index][1] for index in active_vertices]
    zs = [vertices[index][2] for index in active_vertices]
    min_y, max_y = min(ys), max(ys)
    height = max_y - min_y
    if height <= 1.0e-9:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_DEGENERATE_BOUNDS",
            "active target has no vertical extent",
        )
    # The legacy closed envelope is centred from its own symmetric bounds.
    # A source-camera conformal shell exists only on the visible/front side;
    # centring the avatar inside that thin shell would reinterpret the photo
    # plane as the body centre and explode it into the cyan cage.  Its
    # coordinates are already registered to the selected avatar origin.
    center_x = (min(xs) + max(xs)) * 0.5 if surface_mode == "AVATAR_ENVELOPE" else 0.0
    center_z = (min(zs) + max(zs)) * 0.5 if surface_mode == "AVATAR_ENVELOPE" else 0.0
    thickness_cm = thickness_mm / 10.0
    result = [list(point) for point in vertices]
    moved: Set[int] = set()
    minimum_before_mm = math.inf
    minimum_after_mm = math.inf
    clearance_before_by_vertex: Dict[int, float] = {}
    clearance_after_by_vertex: Dict[int, float] = {}

    for index in active_vertices:
        x, y, z = vertices[index]
        t = (y - min_y) / height
        circumference = _profile_circumference(
            t, measurements["chest_bust"],
            measurements["waist"], measurements["hip"],
        )
        circular_radius = circumference / (2.0 * math.pi)
        radius_x = max(0.5, circular_radius * 1.18)
        radius_z = max(0.5, circular_radius * 0.82)
        dx, dz = x - center_x, z - center_z
        q = math.sqrt((dx / radius_x) ** 2 + (dz / radius_z) ** 2)
        local_radius = math.sqrt(dx * dx + dz * dz)
        angle = math.atan2(dz / radius_z, dx / radius_x) if q > 1.0e-12 else 0.0
        surface_x = radius_x * math.cos(angle)
        surface_z = radius_z * math.sin(angle)
        surface_radius = math.sqrt(surface_x * surface_x + surface_z * surface_z)
        before = local_radius - surface_radius
        before_mm = before * 10.0
        minimum_before_mm = min(minimum_before_mm, before_mm)
        required_radius = surface_radius + thickness_cm
        if local_radius < required_radius:
            if local_radius <= 1.0e-12:
                direction_x, direction_z = 1.0, 0.0
            else:
                direction_x, direction_z = dx / local_radius, dz / local_radius
            result[index][0] = center_x + direction_x * required_radius
            result[index][2] = center_z + direction_z * required_radius
            moved.add(index)
            after = thickness_cm
        else:
            after = before
        after_mm = after * 10.0
        minimum_after_mm = min(minimum_after_mm, after_mm)
        clearance_before_by_vertex[index] = before_mm
        clearance_after_by_vertex[index] = after_mm

    collision_faces = [
        face_id for face_id, face in enumerate(faces)
        if face_id not in removed and any(index in moved for index in face)
    ]

    # A thermography-like UI needs more than a binary collision overlay, but
    # this solver still has no pressure or material model.  Publish the exact
    # geometric clearance used by the projection, per stable face address, and
    # classify it relative to the requested cloth-thickness shell.  Consumers
    # can colour these bands without pretending that colour is measured fit,
    # comfort, temperature, stress, or contact pressure.
    face_clearances: List[Dict[str, Any]] = []
    band_counts: Dict[str, int] = {}
    for face_id, face in enumerate(faces):
        if face_id in removed:
            continue
        before_values = [clearance_before_by_vertex[index] for index in face]
        after_values = [clearance_after_by_vertex[index] for index in face]
        minimum_face_before = min(before_values)
        minimum_face_after = min(after_values)
        mean_face_after = sum(after_values) / len(after_values)
        if minimum_face_before < 0.0:
            band = "PENETRATION_CORRECTED"
        elif minimum_face_before < thickness_mm:
            band = "THICKNESS_CLEARANCE_CORRECTED"
        elif minimum_face_after <= thickness_mm + 3.0:
            band = "LOW_CLEARANCE"
        elif minimum_face_after <= thickness_mm + 10.0:
            band = "MODERATE_CLEARANCE"
        else:
            band = "HIGH_CLEARANCE"
        band_counts[band] = band_counts.get(band, 0) + 1
        face_clearances.append({
            "face_index": face_id,
            "minimum_before_mm": round(minimum_face_before, 6),
            "minimum_after_mm": round(minimum_face_after, 6),
            "mean_after_mm": round(mean_face_after, 6),
            "band": band,
        })
    payload = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_GEOMETRIC_CLEARANCE",
        "state": "PROPOSED",
        "authority": "DETERMINISTIC_GEOMETRIC_PREVIEW",
        "method": "AVATAR_ELLIPTIC_CLEARANCE_V1",
        "surface_mode": surface_mode,
        "resolved_vertices_cm": [
            [round(value, 8) for value in point] for point in result
        ],
        "moved_vertex_indices": sorted(moved),
        "collision_face_indices": collision_faces,
        "face_clearances": face_clearances,
        "clearance_scale": {
            "kind": "GEOMETRIC_CLEARANCE_NOT_PRESSURE",
            "requested_shell_mm": round(thickness_mm, 6),
            "low_clearance_upper_mm": round(thickness_mm + 3.0, 6),
            "moderate_clearance_upper_mm": round(thickness_mm + 10.0, 6),
            "band_counts": dict(sorted(band_counts.items())),
        },
        "statistics": {
            "active_face_count": len(active_faces),
            "active_vertex_count": len(active_vertices),
            "moved_vertex_count": len(moved),
            "collision_face_count": len(collision_faces),
            "minimum_clearance_before_mm": round(minimum_before_mm, 6),
            "minimum_clearance_after_mm": round(minimum_after_mm, 6),
            "requested_cloth_thickness_mm": round(thickness_mm, 6),
        },
        "limitations": [
            "elliptical avatar envelope normalised to active target bounds",
            ("front-conformal shells use the selected avatar origin; they do not invent a rear"
             if surface_mode == "FRONT_CONFORMAL_SHELL"
             else "closed target envelope is centred from its active bounds"),
            "no drape, ease, stretch, pressure, seam or material prediction",
            "per-face colours describe geometric clearance, not thermography or pressure",
            "not a manufacturing, comfort or fit certification",
        ],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "human_approval_required": True,
        "fact_promotions": [],
    }
    payload["clearance_digest"] = _digest(payload)
    return payload
