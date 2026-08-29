# -*- coding: utf-8 -*-
"""Deterministic, revision-bound modifiers for the fused-target CAD surface.

These operations are deliberately visual editing aids, not a cloth solver.
They create a new mesh revision and never promote pressure, material, drape,
seam, fit, or manufacturing claims to facts.  The input surface is treated as
immutable; every accepted operation returns an undo-linked child surface.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Set, Tuple


REQUEST_SCHEMA = "garment.target-sculpt-modifier.request.v1"
SCHEMA = "garment.target-sculpt-modifier.v1"
SURFACE_SCHEMA = "garment.target-sculpt-surface.v1"
AUTHORITY = "PROPOSED_CAD_MODIFIER"

_KINDS = frozenset({"PULL", "STRETCH", "WIND_PREVIEW"})
_MAX_VERTICES = 250_000
_MAX_FACES = 500_000
_MAX_PULL_CM = 10.0
_MAX_STRETCH_DISPLACEMENT_CM = 10.0
_MAX_WIND_SPEED_M_S = 50.0
_MAX_WIND_DISPLACEMENT_CM = 5.0
_MAX_COORDINATE_CM = 1_000_000.0
_EPSILON = 1.0e-12


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray))


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_modifier(value: Any, key: str = "") -> Any:
    """Canonicalise semantically unordered selections for stable operation IDs."""
    if isinstance(value, Mapping):
        return {
            str(name): _canonical_modifier(value[name], str(name))
            for name in sorted(value)
        }
    if _sequence(value):
        rows = [_canonical_modifier(item) for item in value]
        if key in {"vertex_indices", "face_indices", "anchor_vertex_indices"}:
            return sorted(set(rows))
        return rows
    return value


def surface_digest(
    vertices_cm: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    revision: int,
) -> str:
    """Return the canonical digest used to bind one immutable surface revision."""
    # JSON distinguishes ``2`` from ``2.0`` even though they are the same CAD
    # coordinate.  Canonicalise here so callers and the validator bind the
    # same geometry regardless of the numeric spelling used on the wire.
    canonical_vertices = [
        [float(component) for component in point]
        for point in vertices_cm
    ]
    canonical_faces = [
        [int(index) for index in face]
        for face in faces
    ]
    return _digest({
        "schema": SURFACE_SCHEMA,
        "revision": int(revision),
        "vertices_cm": canonical_vertices,
        "faces": canonical_faces,
    })


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNKNOWN",
        "authority": AUTHORITY,
        "why": why,
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result.update(detail)
    return result


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _vector3(value: Any) -> List[float] | None:
    if not _sequence(value) or len(value) != 3:
        return None
    parsed = [_finite(component) for component in value]
    if any(component is None for component in parsed):
        return None
    return [float(component) for component in parsed]


def _length(vector: Sequence[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def _unit(vector: Sequence[float]) -> List[float] | None:
    length = _length(vector)
    if length <= _EPSILON:
        return None
    return [component / length for component in vector]


def _normalise_mesh(
    surface: Any,
) -> Tuple[List[List[float]], List[List[int]], int, str] | Dict[str, Any]:
    if not isinstance(surface, Mapping):
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_SURFACE_REQUIRED",
            "sculpt_surface must contain vertices_cm, faces, and revision",
        )
    raw_vertices = surface.get("vertices_cm")
    if not _sequence(raw_vertices) or not raw_vertices:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_VERTICES",
            "vertices_cm must be a non-empty array",
        )
    if len(raw_vertices) > _MAX_VERTICES:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_MESH_TOO_LARGE",
            f"vertices exceed the bounded limit of {_MAX_VERTICES}",
        )
    vertices: List[List[float]] = []
    for row in raw_vertices:
        point = _vector3(row)
        if point is None:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
                "every vertex must contain three finite numeric coordinates",
            )
        if any(abs(component) > _MAX_COORDINATE_CM for component in point):
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
                "vertex coordinate exceeds the bounded CAD workspace",
            )
        vertices.append(point)

    raw_faces = surface.get("faces")
    if not _sequence(raw_faces) or not raw_faces:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_FACES",
            "faces must be a non-empty array",
        )
    if len(raw_faces) > _MAX_FACES:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_MESH_TOO_LARGE",
            f"faces exceed the bounded limit of {_MAX_FACES}",
        )
    faces: List[List[int]] = []
    for row in raw_faces:
        if (not _sequence(row) or len(row) < 3
                or any(_integer(index) is None for index in row)):
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_FACES",
                "every face must contain at least three integer indices",
            )
        face = [int(index) for index in row]
        if any(index < 0 or index >= len(vertices) for index in face):
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_FACE_OUT_OF_RANGE",
                "face topology contains a vertex index outside vertices_cm",
            )
        faces.append(face)

    revision = _integer(surface.get("revision"))
    if revision is None or revision < 0:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_REVISION_REQUIRED",
            "sculpt_surface.revision must be a non-negative integer",
        )
    digest = surface_digest(vertices, faces, revision)
    supplied_digest = surface.get("digest")
    if supplied_digest is not None and supplied_digest != digest:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_DIGEST_MISMATCH",
            "sculpt_surface.digest does not bind the supplied mesh revision",
            computed_digest=digest,
        )
    return vertices, faces, revision, digest


def _indices(value: Any, limit: int, kind: str) -> List[int] | Dict[str, Any]:
    if value is None:
        return []
    if not _sequence(value) or any(_integer(index) is None for index in value):
        return _unknown(
            f"UNKNOWN_TARGET_SCULPT_MODIFIER_{kind}_INDICES",
            f"{kind.lower()}_indices must be an array of integers",
        )
    normalised = sorted({int(index) for index in value})
    if any(index < 0 or index >= limit for index in normalised):
        return _unknown(
            f"UNKNOWN_TARGET_SCULPT_MODIFIER_{kind}_OUT_OF_RANGE",
            f"{kind.lower()} selection is outside the mesh",
        )
    return normalised


def _selection(
    modifier: Mapping[str, Any], faces: Sequence[Sequence[int]],
    vertex_count: int, *, default_all: bool = False,
) -> Tuple[List[int], List[int]] | Dict[str, Any]:
    nested = modifier.get("selection")
    selection = nested if isinstance(nested, Mapping) else modifier
    vertices = _indices(selection.get("vertex_indices"), vertex_count, "VERTEX")
    if isinstance(vertices, dict):
        return vertices
    face_ids = _indices(selection.get("face_indices"), len(faces), "FACE")
    if isinstance(face_ids, dict):
        return face_ids
    selected: Set[int] = set(vertices)
    for face_id in face_ids:
        selected.update(faces[face_id])
    if not selected and default_all:
        selected.update(index for face in faces for index in face)
    if not selected:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_EMPTY_SELECTION",
            "modifier must select at least one face or vertex",
        )
    return sorted(selected), face_ids


def _face_normal(
    vertices: Sequence[Sequence[float]], face: Sequence[int],
) -> List[float] | None:
    # Newell's method supports triangles and ordered polygons with one stable
    # summation order.  Face winding intentionally determines normal sign.
    normal = [0.0, 0.0, 0.0]
    for position, index in enumerate(face):
        point = vertices[index]
        nxt = vertices[face[(position + 1) % len(face)]]
        normal[0] += (point[1] - nxt[1]) * (point[2] + nxt[2])
        normal[1] += (point[2] - nxt[2]) * (point[0] + nxt[0])
        normal[2] += (point[0] - nxt[0]) * (point[1] + nxt[1])
    return _unit(normal)


def _vertex_normals(
    vertices: Sequence[Sequence[float]], faces: Sequence[Sequence[int]],
    selected_vertices: Sequence[int], selected_faces: Sequence[int],
) -> List[List[float]] | Dict[str, Any]:
    selected_set = set(selected_vertices)
    restricted_faces = set(selected_faces)
    sums = {index: [0.0, 0.0, 0.0] for index in selected_vertices}
    counts = {index: 0 for index in selected_vertices}
    for face_id, face in enumerate(faces):
        normal = _face_normal(vertices, face)
        if normal is None:
            continue
        for index in face:
            if index not in selected_set:
                continue
            # Vertices selected directly use every incident face.  A face-only
            # selection still receives normals from the selected face set.
            if restricted_faces and face_id not in restricted_faces:
                continue
            for axis in range(3):
                sums[index][axis] += normal[axis]
            counts[index] += 1
    result: List[List[float]] = []
    for index in selected_vertices:
        normal = _unit(sums[index]) if counts[index] else None
        if normal is None:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_DEGENERATE_NORMAL",
                f"selected vertex {index} has no deterministic finite normal",
            )
        result.append(normal)
    return result


def _bounded_displacements(
    before: Sequence[Sequence[float]], after: Sequence[Sequence[float]],
    selected: Iterable[int], maximum_cm: float,
) -> Tuple[float, float] | Dict[str, Any]:
    lengths: List[float] = []
    for index in sorted(selected):
        delta = [after[index][axis] - before[index][axis] for axis in range(3)]
        length = _length(delta)
        if not math.isfinite(length):
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
                "modifier produced a non-finite displacement",
            )
        if length > maximum_cm + 1.0e-9:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
                f"per-vertex displacement exceeds {maximum_cm:g} cm",
                maximum_displacement_cm=maximum_cm,
                attempted_displacement_cm=round(length, 8),
            )
        lengths.append(length)
    return (max(lengths, default=0.0), sum(lengths))


def _pull(
    modifier: Mapping[str, Any], vertices: List[List[float]],
    faces: List[List[int]],
) -> Tuple[List[List[float]], List[int], Dict[str, Any]] | Dict[str, Any]:
    selected = _selection(modifier, faces, len(vertices))
    if isinstance(selected, dict):
        return selected
    vertex_ids, face_ids = selected
    result = [list(point) for point in vertices]

    raw_vector = modifier.get(
        "vector_cm", modifier.get("displacement_vector_cm"))
    if raw_vector is not None:
        vector = _vector3(raw_vector)
        if vector is None:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
                "PULL vector_cm must contain three finite numbers",
            )
        if _length(vector) <= _EPSILON:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_ZERO_VECTOR",
                "PULL vector_cm must be non-zero",
            )
        directions = [vector for _ in vertex_ids]
        method = "EXPLICIT_DISPLACEMENT_VECTOR"
    else:
        distance = _finite(modifier.get("distance_cm"))
        if distance is None:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
                "PULL distance_cm must be finite",
            )
        if abs(distance) <= _EPSILON:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_ZERO_VECTOR",
                "PULL distance_cm must be non-zero",
            )
        if abs(distance) > _MAX_PULL_CM:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
                f"PULL distance_cm must be within ±{_MAX_PULL_CM:g} cm",
            )
        raw_direction = modifier.get(
            "direction_vector", modifier.get("direction"))
        if raw_direction is None or (
                isinstance(raw_direction, str)
                and raw_direction.upper() == "LOCAL_NORMAL"):
            normals = _vertex_normals(
                vertices, faces, vertex_ids, face_ids)
            if isinstance(normals, dict):
                return normals
            directions = [
                [distance * component for component in normal]
                for normal in normals
            ]
            method = "LOCAL_VERTEX_NORMAL"
        else:
            direction = _vector3(raw_direction)
            unit = _unit(direction) if direction is not None else None
            if unit is None:
                return _unknown(
                    "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
                    "PULL direction_vector must be a finite non-zero vector",
                )
            vector = [distance * component for component in unit]
            directions = [vector for _ in vertex_ids]
            method = "EXPLICIT_DIRECTION_VECTOR"

    for index, vector in zip(vertex_ids, directions):
        result[index] = [vertices[index][axis] + vector[axis] for axis in range(3)]
    bounded = _bounded_displacements(
        vertices, result, vertex_ids, _MAX_PULL_CM)
    if isinstance(bounded, dict):
        return bounded
    return result, vertex_ids, {
        "method": method,
        "selected_face_indices": face_ids,
        "maximum_displacement_cm": round(bounded[0], 8),
    }


def _stretch(
    modifier: Mapping[str, Any], vertices: List[List[float]],
    faces: List[List[int]],
) -> Tuple[List[List[float]], List[int], Dict[str, Any]] | Dict[str, Any]:
    selected = _selection(modifier, faces, len(vertices))
    if isinstance(selected, dict):
        return selected
    vertex_ids, face_ids = selected
    axis = _vector3(modifier.get("axis_vector", modifier.get("axis")))
    unit_axis = _unit(axis) if axis is not None else None
    if unit_axis is None:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
            "STRETCH axis_vector must be a finite non-zero vector",
        )
    anchor_index_raw = modifier.get("anchor_vertex_index")
    if anchor_index_raw is not None:
        anchor_index = _integer(anchor_index_raw)
        if anchor_index is None or not 0 <= anchor_index < len(vertices):
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_VERTEX_OUT_OF_RANGE",
                "anchor_vertex_index is outside the mesh",
            )
        anchor = list(vertices[anchor_index])
        anchor_source = "VERTEX"
    else:
        anchor = _vector3(modifier.get("anchor_cm"))
        if anchor is None:
            return _unknown(
                "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
                "STRETCH anchor_cm must contain three finite numbers",
            )
        anchor_source = "EXPLICIT_POINT"
    scale = _finite(modifier.get("scale_factor", modifier.get("scale")))
    if scale is None:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
            "STRETCH scale_factor must be finite",
        )
    if not 0.5 <= scale <= 1.5:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
            "STRETCH scale_factor must be within 0.5..1.5",
        )
    if abs(scale - 1.0) <= _EPSILON:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_NO_OP",
            "STRETCH scale_factor must change the selected surface",
        )

    result = [list(point) for point in vertices]
    for index in vertex_ids:
        relative = [vertices[index][axis_id] - anchor[axis_id]
                    for axis_id in range(3)]
        axial = sum(relative[axis_id] * unit_axis[axis_id]
                    for axis_id in range(3))
        displacement = axial * (scale - 1.0)
        result[index] = [
            vertices[index][axis_id] + displacement * unit_axis[axis_id]
            for axis_id in range(3)
        ]
    moved = [
        index for index in vertex_ids
        if _length([result[index][axis] - vertices[index][axis]
                    for axis in range(3)]) > _EPSILON
    ]
    if not moved:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_NO_OP",
            "STRETCH selection has no axial distance from its anchor",
        )
    bounded = _bounded_displacements(
        vertices, result, moved, _MAX_STRETCH_DISPLACEMENT_CM)
    if isinstance(bounded, dict):
        return bounded
    return result, moved, {
        "method": "LOCAL_AXIAL_SCALE",
        "anchor_source": anchor_source,
        "selected_face_indices": face_ids,
        "maximum_displacement_cm": round(bounded[0], 8),
    }


def _wind_preview(
    modifier: Mapping[str, Any], vertices: List[List[float]],
    faces: List[List[int]],
) -> Tuple[List[List[float]], List[int], Dict[str, Any]] | Dict[str, Any]:
    selected = _selection(modifier, faces, len(vertices), default_all=True)
    if isinstance(selected, dict):
        return selected
    vertex_ids, face_ids = selected
    wind = _vector3(modifier.get("wind_vector_m_s", modifier.get("wind_vector")))
    if wind is None:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
            "WIND_PREVIEW wind_vector_m_s must contain three finite numbers",
        )
    speed = _length(wind)
    if speed <= _EPSILON:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_ZERO_VECTOR",
            "WIND_PREVIEW wind vector must be non-zero",
        )
    if speed > _MAX_WIND_SPEED_M_S:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
            f"wind speed exceeds the {_MAX_WIND_SPEED_M_S:g} m/s preview bound",
        )
    gain = _finite(modifier.get("preview_gain_cm_per_m_s", 0.08))
    if gain is None or not 0.0 < gain <= 0.25:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
            "preview_gain_cm_per_m_s must be within (0, 0.25]",
        )
    displacement = [component * gain for component in wind]
    if _length(displacement) > _MAX_WIND_DISPLACEMENT_CM + 1.0e-9:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
            f"wind preview displacement exceeds {_MAX_WIND_DISPLACEMENT_CM:g} cm",
        )
    anchors = _indices(
        modifier.get("anchor_vertex_indices", []), len(vertices), "VERTEX")
    if isinstance(anchors, dict):
        return anchors
    anchor_set = set(anchors)
    moved = [index for index in vertex_ids if index not in anchor_set]
    if not moved:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_EMPTY_SELECTION",
            "all selected WIND_PREVIEW vertices are fixed anchors",
        )
    result = [list(point) for point in vertices]
    for index in moved:
        result[index] = [vertices[index][axis] + displacement[axis]
                         for axis in range(3)]
    bounded = _bounded_displacements(
        vertices, result, moved, _MAX_WIND_DISPLACEMENT_CM)
    if isinstance(bounded, dict):
        return bounded
    return result, moved, {
        "method": "UNIFORM_LOW_FIDELITY_WIND_DISPLACEMENT",
        "selected_face_indices": face_ids,
        "anchor_vertex_indices": anchors,
        "wind_speed_m_s": round(speed, 8),
        "preview_gain_cm_per_m_s": round(gain, 8),
        "maximum_displacement_cm": round(bounded[0], 8),
    }


def apply_target_sculpt_modifier(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply one bounded modifier and return an immutable child revision."""
    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_SCHEMA",
            f"request schema must be {REQUEST_SCHEMA}",
        )
    mesh = _normalise_mesh(request.get("sculpt_surface"))
    if isinstance(mesh, dict):
        return mesh
    vertices, faces, revision, parent_digest = mesh
    expected_revision = _integer(request.get("expected_revision"))
    if expected_revision is None or expected_revision < 0:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_REVISION_REQUIRED",
            "expected_revision must be a non-negative integer",
        )
    if expected_revision != revision:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_STALE_REVISION",
            "expected_revision does not match sculpt_surface.revision",
            expected_revision=expected_revision,
            current_revision=revision,
        )
    expected_digest = request.get("expected_digest")
    if expected_digest is not None and expected_digest != parent_digest:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_STALE_REVISION",
            "expected_digest does not match the current immutable surface",
            expected_digest=expected_digest,
            current_digest=parent_digest,
        )
    modifier = request.get("modifier")
    if not isinstance(modifier, Mapping):
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_REQUIRED",
            "modifier must be an object",
        )
    kind = str(modifier.get("kind", "")).upper()
    if kind not in _KINDS:
        return _unknown(
            "UNKNOWN_TARGET_SCULPT_MODIFIER_KIND",
            f"modifier.kind must be one of {', '.join(sorted(_KINDS))}",
        )

    if kind == "PULL":
        modified = _pull(modifier, vertices, faces)
    elif kind == "STRETCH":
        modified = _stretch(modifier, vertices, faces)
    else:
        modified = _wind_preview(modifier, vertices, faces)
    if isinstance(modified, dict):
        return modified
    result_vertices, moved_indices, detail = modified
    rounded_vertices = [
        [round(component, 8) for component in point]
        for point in result_vertices
    ]
    child_revision = revision + 1
    child_digest = surface_digest(rounded_vertices, faces, child_revision)
    normalised_modifier = _canonical_modifier(modifier)
    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": AUTHORITY,
        "state": "PROPOSED",
        "authority": AUTHORITY,
        "modifier_kind": kind,
        "revision": child_revision,
        "digest": child_digest,
        "undo_parent_digest": parent_digest,
        "sculpt_surface": {
            "schema": SURFACE_SCHEMA,
            "vertices_cm": rounded_vertices,
            "faces": [list(face) for face in faces],
            "revision": child_revision,
            "digest": child_digest,
            "undo_parent_digest": parent_digest,
        },
        "moved_vertex_indices": sorted(moved_indices),
        "statistics": {
            "moved_vertex_count": len(moved_indices),
            **detail,
        },
        "modifier_digest": _digest({
            "kind": kind,
            "modifier": normalised_modifier,
            "parent_digest": parent_digest,
            "child_digest": child_digest,
        }),
        "limitations": [
            "visual CAD proposal only",
            "no pressure, material, cloth, seam, fit or manufacturing fact",
            ("uniform low-fidelity comparison displacement; not fluid or cloth physics"
             if kind == "WIND_PREVIEW"
             else "bounded geometric surface edit; not physical simulation"),
        ],
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    return payload


solve_target_sculpt_modifier = apply_target_sculpt_modifier
