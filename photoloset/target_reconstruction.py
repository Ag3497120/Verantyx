# -*- coding: utf-8 -*-
"""Provider-neutral fused target reconstruction and cleanup contract.

The object produced here is a *visual target* for a garment reconstruction
loop.  It is not a pattern, a body measurement, or evidence that an inferred
rear/occluded surface exists.  A single-view 3D provider may supply a fused
person-and-clothing mesh envelope; when it does not, the same contract carries
the deterministic front silhouette fallback already available in Photoloset.

User cleanup is expressed as reversible region exclusion.  Removing a
background region never changes garment geometry.  Removing hair or another
occluder creates an UNKNOWN hole and, when a garment target is named, a
separate PROPOSED completion.  Removing a body from a fused mesh is display
only until the body/garment boundary has been supplied explicitly.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Set


REQUEST_SCHEMA = "garment.target-reconstruction.request.v1"
SCHEMA = "garment.target-reconstruction.v1"
TARGET_BOUND_PREVIEW_REQUEST_SCHEMA = (
    "garment.target-bound-candidate-preview.request.v1"
)
TARGET_BOUND_PREVIEW_SCHEMA = "garment.target-bound-candidate-preview.v1"

_REGION_CLASSES = {
    "BACKGROUND", "HAIR", "BODY", "SKIN", "GARMENT", "ACCESSORY", "UNKNOWN",
}
_REMOVABLE_CLASSES = {"BACKGROUND", "HAIR", "BODY", "SKIN", "ACCESSORY"}
_OCCLUDER_CLASSES = {"HAIR", "BODY", "SKIN", "ACCESSORY"}
_AVATAR_AUTHORITIES = {"PROPOSED_PREVIEW", "REQUESTED", "MEASURED_TARGET"}
_AVATAR_KINDS = {"PARAMETRIC_GAME_AVATAR", "EXTERNAL_RIGGED_AVATAR"}
_AVATAR_MEASUREMENTS = {"height", "chest_bust", "waist", "hip"}
_FUSED_TARGET_ROLES = {
    "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
    "FUSED_PERSON_AND_CLOTHING_FOREGROUND",  # v1 app compatibility
}


def stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _nonempty(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _camera_digest(request: Mapping[str, Any]) -> Optional[str]:
    supplied = _nonempty(request.get("camera_digest"))
    if supplied:
        return supplied
    camera = request.get("camera")
    if isinstance(camera, Mapping) and camera:
        return stable_digest(camera)
    return None


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNKNOWN",
        "why": why,
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result.update(extra)
    return result


def _source_digest(source: Any) -> Optional[str]:
    if not isinstance(source, Mapping):
        return None
    supplied = _nonempty(source.get("image_digest"))
    if supplied:
        return supplied
    # Metadata is useful for binding a process run without claiming that a
    # path or URL itself proves image bytes.  Callers should prefer a digest.
    metadata = {
        key: source[key]
        for key in ("image_id", "width", "height", "orientation")
        if key in source
    }
    return stable_digest(metadata) if metadata else None


def _base_avatar(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("base_avatar must be selected before reconstruction")
    avatar_id = _nonempty(value.get("avatar_id"))
    kind = str(value.get("kind", "")).upper()
    authority = str(value.get("authority", "")).upper()
    geometry_digest = _nonempty(value.get("geometry_digest"))
    if not avatar_id or kind not in _AVATAR_KINDS or authority not in _AVATAR_AUTHORITIES:
        raise ValueError(
            "base_avatar needs avatar_id, a supported kind, and typed authority")
    if not geometry_digest:
        raise ValueError("base_avatar.geometry_digest is required")
    raw_measurements = value.get("measurements_cm")
    if not isinstance(raw_measurements, Mapping):
        raise ValueError("base_avatar.measurements_cm is required")
    missing = sorted(_AVATAR_MEASUREMENTS - set(raw_measurements))
    if missing:
        raise ValueError(
            "base_avatar is missing required measurements: " + ", ".join(missing))
    measurements: Dict[str, float] = {}
    for name in sorted(_AVATAR_MEASUREMENTS):
        raw = raw_measurements[name]
        if (isinstance(raw, bool) or not isinstance(raw, (int, float))
                or not math.isfinite(float(raw)) or float(raw) <= 0.0):
            raise ValueError(f"base_avatar measurement {name} must be positive cm")
        measurements[name] = round(float(raw), 6)
    return {
        "avatar_id": avatar_id,
        "kind": kind,
        "authority": authority,
        "geometry_digest": geometry_digest,
        "measurements_cm": measurements,
        "render_lod": str(value.get("render_lod", "HIGH")).upper(),
        "rig_digest": _nonempty(value.get("rig_digest")),
        "not_inferred_from_garment_photo": True,
    }


def _normalise_regions(value: Any) -> List[Dict[str, Any]]:
    if not _sequence(value) or not value:
        raise ValueError("regions must be a non-empty array")
    seen: Set[str] = set()
    rows: List[Dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ValueError("every region must be an object")
        region_id = _nonempty(raw.get("id")) or _nonempty(raw.get("region_id"))
        if not region_id:
            raise ValueError(f"region {index} needs id")
        if region_id in seen:
            raise ValueError(f"duplicate region id {region_id!r}")
        seen.add(region_id)
        region_class = str(raw.get("class", raw.get("kind", "UNKNOWN"))).upper()
        if region_class not in _REGION_CLASSES:
            raise ValueError(f"unsupported region class {region_class!r}")
        target_ids = raw.get("overlap_part_ids", raw.get("garment_target_ids", []))
        if target_ids is None:
            target_ids = []
        if not _sequence(target_ids) or any(not _nonempty(v) for v in target_ids):
            raise ValueError(f"region {region_id!r} has invalid overlap_part_ids")
        state = str(raw.get("state", "PROPOSED")).upper()
        if state not in {"OBSERVED", "PROPOSED", "UNKNOWN", "UNOBSERVED"}:
            raise ValueError(f"region {region_id!r} has invalid state")
        outline: List[List[float]] = []
        raw_outline = raw.get("outline")
        if raw_outline is not None:
            if not _sequence(raw_outline):
                raise ValueError(f"region {region_id!r} has invalid outline")
            for point in raw_outline:
                if not _sequence(point) or len(point) < 2:
                    raise ValueError(f"region {region_id!r} has invalid outline")
                x, y = _finite(point[0]), _finite(point[1])
                if x is None or y is None:
                    raise ValueError(f"region {region_id!r} has invalid outline")
                outline.append([x, y])
            if outline and (len(outline) < 3
                            or abs(_polygon_area(outline)) <= 1.0e-9):
                raise ValueError(f"region {region_id!r} has degenerate outline")
        rows.append({
            "id": region_id,
            "label": _nonempty(raw.get("label")) or region_id,
            "class": region_class,
            "state": state,
            "removable": region_class in _REMOVABLE_CLASSES,
            "removed": False,
            "occludes_garment": bool(raw.get("occludes_garment", False)),
            "overlap_part_ids": sorted({_nonempty(v) for v in target_ids if _nonempty(v)}),
            "mesh_part_ids": sorted({
                token for token in (
                    _nonempty(v) for v in (raw.get("mesh_part_ids") or [])
                ) if token
            }) if _sequence(raw.get("mesh_part_ids", [])) else [],
            # Component-local image geometry is still only evidence for a
            # front visual target.  It does not establish a garment part,
            # seam, layer or rear surface.
            "outline": outline,
            "target_role": str(raw.get("target_role", "")).upper(),
            "selection_mode": str(raw.get("selection_mode", "")).upper(),
            # These fields describe the model/human proposed *visible image
            # component*.  Keeping them here lets a later candidate preview
            # preserve left/right, layering and separated garment units
            # without treating any of those labels as a seam or rear fact.
            "part_id": _nonempty(raw.get("part_id")) or region_id,
            "side": (_nonempty(raw.get("side")) or "unspecified").lower(),
            "layer": (int(raw.get("layer"))
                      if isinstance(raw.get("layer"), int)
                      and not isinstance(raw.get("layer"), bool) else 0),
            "garment_unit": _nonempty(raw.get("garment_unit")),
            "semantic_role": (
                _nonempty(raw.get("semantic_role"))
                or _nonempty(raw.get("detail_role"))
                or _nonempty(raw.get("construction_role"))
            ),
            "average_rgba": copy.deepcopy(raw.get("average_rgba"))
                if isinstance(raw.get("average_rgba"), Mapping) else None,
            "provenance": copy.deepcopy(raw.get("provenance"))
                if isinstance(raw.get("provenance"), Mapping) else {},
        })
    return rows


def _reconstruction_envelope(request: Mapping[str, Any]) -> Dict[str, Any]:
    reconstruction = request.get("reconstruction")
    if not isinstance(reconstruction, Mapping):
        reconstruction = {}
    mesh = reconstruction.get("mesh")
    if isinstance(mesh, Mapping) and _nonempty(mesh.get("artifact_digest")):
        return {
            "source_kind": "EXTERNAL_SINGLE_VIEW_3D",
            "provider": _nonempty(reconstruction.get("provider")) or "external",
            "provider_connected": True,
            "mesh": {
                "artifact_digest": _nonempty(mesh.get("artifact_digest")),
                "format": _nonempty(mesh.get("format")) or "UNKNOWN",
                "vertex_count": mesh.get("vertex_count"),
                "face_count": mesh.get("face_count"),
                "fused_person_and_clothing": True,
            },
            "fallback": None,
        }
    fallback = reconstruction.get("fallback")
    if not isinstance(fallback, Mapping):
        fallback = request.get("fallback")
    if not isinstance(fallback, Mapping):
        fallback = {}
    silhouette_digest = _nonempty(fallback.get("silhouette_digest"))
    if not silhouette_digest and fallback:
        silhouette_digest = stable_digest(fallback)
    target_role = str(
        fallback.get("target_role", "GARMENT_COMPONENT_PROPOSAL")
    ).upper()
    return {
        "source_kind": ("FUSED_FOREGROUND_2_5D_FALLBACK"
                        if target_role in _FUSED_TARGET_ROLES
                        else "GEOMETRIC_FRONT_FALLBACK"),
        "provider": None,
        "provider_connected": False,
        "mesh": None,
        "fallback": {
            "silhouette_digest": silhouette_digest,
            "point_count": fallback.get("point_count"),
            "outline": copy.deepcopy(fallback.get("outline")),
            "width_px": fallback.get("width_px"),
            "height_px": fallback.get("height_px"),
            "target_role": target_role,
            "authority": str(fallback.get("authority", "PROPOSED")).upper(),
            "source": copy.deepcopy(fallback.get("source")),
            "selection_mode": str(
                fallback.get("selection_mode", "FOREGROUND_SUBJECT_MASK")
            ).upper(),
            "front_only": True,
        },
    }


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _resample_closed_polyline(
        points: Sequence[Sequence[float]], count: int) -> List[List[float]]:
    segments: List[float] = []
    perimeter = 0.0
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        length = math.hypot(nxt[0] - point[0], nxt[1] - point[1])
        segments.append(length)
        perimeter += length
    if perimeter <= 1.0e-9:
        raise ValueError("fallback outline perimeter is degenerate")
    result: List[List[float]] = []
    segment_index = 0
    segment_start = 0.0
    for sample in range(count):
        distance = perimeter * sample / count
        while (segment_index < len(segments) - 1
               and segment_start + segments[segment_index] < distance):
            segment_start += segments[segment_index]
            segment_index += 1
        start = points[segment_index]
        end = points[(segment_index + 1) % len(points)]
        length = max(segments[segment_index], 1.0e-12)
        fraction = (distance - segment_start) / length
        result.append([
            start[0] + (end[0] - start[0]) * fraction,
            start[1] + (end[1] - start[1]) * fraction,
        ])
    return result


def _polygon_area(points: Sequence[Sequence[float]]) -> float:
    return 0.5 * sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def _point_in_triangle(
        point: Sequence[float], a: Sequence[float], b: Sequence[float],
        c: Sequence[float]) -> bool:
    def cross(p: Sequence[float], q: Sequence[float], r: Sequence[float]) -> float:
        return ((q[0] - p[0]) * (r[1] - p[1])
                - (q[1] - p[1]) * (r[0] - p[0]))
    c1, c2, c3 = cross(a, b, point), cross(b, c, point), cross(c, a, point)
    return c1 >= -1.0e-9 and c2 >= -1.0e-9 and c3 >= -1.0e-9


def _triangulate_simple_polygon(points: Sequence[Sequence[float]]) -> List[List[int]]:
    """Triangulate locally so one brush hit never deletes a global fan wedge."""
    if len(points) < 3:
        return []
    order = list(range(len(points)))
    if _polygon_area(points) < 0:
        order.reverse()
    triangles: List[List[int]] = []
    guard = len(order) * len(order)
    while len(order) > 3 and guard > 0:
        clipped = False
        for slot in range(len(order)):
            previous = order[(slot - 1) % len(order)]
            current = order[slot]
            following = order[(slot + 1) % len(order)]
            a, b, c = points[previous], points[current], points[following]
            cross = ((b[0] - a[0]) * (c[1] - a[1])
                     - (b[1] - a[1]) * (c[0] - a[0]))
            if cross <= 1.0e-9:
                continue
            if any(
                index not in {previous, current, following}
                and _point_in_triangle(points[index], a, b, c)
                for index in order
            ):
                continue
            triangles.append([previous, current, following])
            del order[slot]
            clipped = True
            break
        if not clipped:
            return []
        guard -= 1
    if len(order) == 3:
        triangles.append([order[0], order[1], order[2]])
    return triangles


def _subdivide_triangle_mesh(
        vertices: Sequence[Sequence[float]],
        texture_coordinates: Sequence[Sequence[float]],
        triangles: Sequence[Sequence[int]], levels: int
        ) -> tuple[List[List[float]], List[List[float]], List[List[int]]]:
    """Deterministically refine a front target for a local CAD brush.

    Ear clipping only places vertices on the silhouette boundary.  A brush
    hit could therefore remove one triangle spanning most of a torso.  Two
    midpoint passes keep the same geometry while giving the erase/restore
    tool a bounded local tessellation.  Midpoints are cached by undirected
    edge so adjacent triangles remain watertight.
    """
    refined_vertices = [list(point) for point in vertices]
    refined_uv = [list(point) for point in texture_coordinates]
    refined_triangles = [list(face) for face in triangles]
    for _ in range(max(0, levels)):
        midpoint_cache: Dict[tuple[int, int], int] = {}

        def midpoint(left: int, right: int) -> int:
            key = (min(left, right), max(left, right))
            cached = midpoint_cache.get(key)
            if cached is not None:
                return cached
            point = [
                (refined_vertices[left][axis]
                 + refined_vertices[right][axis]) * 0.5
                for axis in range(3)
            ]
            uv = [
                (refined_uv[left][axis] + refined_uv[right][axis]) * 0.5
                for axis in range(2)
            ]
            index = len(refined_vertices)
            refined_vertices.append(point)
            refined_uv.append(uv)
            midpoint_cache[key] = index
            return index

        next_triangles: List[List[int]] = []
        for a, b, c in refined_triangles:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            next_triangles.extend([
                [a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca],
            ])
        refined_triangles = next_triangles
    return refined_vertices, refined_uv, refined_triangles


def _fallback_sculpt_surface(
        reconstruction: Mapping[str, Any], avatar: Mapping[str, Any],
        regions: Sequence[Mapping[str, Any]], *,
        garment_components_only: bool = False,
        ) -> Optional[Dict[str, Any]]:
    fallback = reconstruction.get("fallback")
    if not isinstance(fallback, Mapping):
        return None
    width = _finite(fallback.get("width_px"))
    height = _finite(fallback.get("height_px"))
    if width is None or height is None or width <= 0 or height <= 0:
        return None

    target_role = str(fallback.get(
        "target_role", "GARMENT_COMPONENT_PROPOSAL")).upper()
    fused_foreground = target_role in _FUSED_TARGET_ROLES
    component_outlines: List[Dict[str, Any]] = []
    if garment_components_only:
        for region in regions:
            outline = region.get("outline")
            if (region.get("class") != "GARMENT" or not _sequence(outline)
                    or len(outline) < 3):
                continue
            points = [[float(point[0]), float(point[1])] for point in outline]
            if abs(_polygon_area(points)) <= 1.0e-9:
                continue
            component_outlines.append({
                "id": str(region.get("id")),
                "part_id": str(region.get("part_id") or region.get("id")),
                "state": str(region.get("state", "PROPOSED")),
                "side": str(region.get("side", "unspecified")),
                "layer": int(region.get("layer", 0)),
                "garment_unit": region.get("garment_unit"),
                "semantic_role": region.get("semantic_role"),
                "average_rgba": copy.deepcopy(region.get("average_rgba")),
                "points": points,
            })
    elif fused_foreground:
        for region in regions:
            outline = region.get("outline")
            region_role = str(region.get("target_role", "")).upper()
            if (not region_role.startswith("FUSED_PERSON_AND_")
                    or not _sequence(outline) or len(outline) < 3):
                continue
            points = [[float(point[0]), float(point[1])] for point in outline]
            if abs(_polygon_area(points)) <= 1.0e-9:
                continue
            component_outlines.append({
                "id": str(region.get("id")),
                "part_id": str(region.get("part_id") or region.get("id")),
                "state": str(region.get("state", "PROPOSED")),
                "side": str(region.get("side", "unspecified")),
                "layer": int(region.get("layer", 0)),
                "garment_unit": region.get("garment_unit"),
                "semantic_role": region.get("semantic_role"),
                "average_rgba": copy.deepcopy(region.get("average_rgba")),
                "points": points,
            })
    else:
        for region in regions:
            outline = region.get("outline")
            if (region.get("class") != "GARMENT" or not _sequence(outline)
                    or len(outline) < 3):
                continue
            points = [[float(point[0]), float(point[1])] for point in outline]
            if abs(_polygon_area(points)) <= 1.0e-9:
                continue
            component_outlines.append({
                "id": str(region.get("id")),
                "part_id": str(region.get("part_id") or region.get("id")),
                "state": str(region.get("state", "PROPOSED")),
                "side": str(region.get("side", "unspecified")),
                "layer": int(region.get("layer", 0)),
                "garment_unit": region.get("garment_unit"),
                "semantic_role": region.get("semantic_role"),
                "average_rgba": copy.deepcopy(region.get("average_rgba")),
                "points": points,
            })

    # Compatibility for callers that only carry the historical combined
    # silhouette.  New app requests provide component-local garment loops so
    # disconnected tops, trouser legs and overlays are never bridged through
    # empty image pixels merely to make one closed polygon.
    if not component_outlines and not garment_components_only:
        raw_outline = fallback.get("outline")
        if not _sequence(raw_outline) or len(raw_outline) < 3:
            return None
        outline: List[List[float]] = []
        for point in raw_outline:
            if not _sequence(point) or len(point) < 2:
                return None
            x, y = _finite(point[0]), _finite(point[1])
            if x is None or y is None:
                return None
            outline.append([x, y])
        if abs(_polygon_area(outline)) <= 1.0e-9:
            return None
        component_outlines.append({
            "id": ("fused-person-and-garment-foreground"
                   if fused_foreground else "combined-front-fallback"),
            "part_id": ("fused-person-and-garment-foreground"
                        if fused_foreground else "combined-front-fallback"),
            "state": "PROPOSED",
            "side": "unspecified",
            "layer": 0,
            "garment_unit": None,
            "semantic_role": None,
            "average_rgba": None,
            "points": outline,
        })
    if not component_outlines:
        return None

    # Bound pathological segmentation output without selecting by a filename
    # or garment class.  Largest area is a deterministic geometry-only order.
    component_outlines = sorted(
        component_outlines,
        key=lambda item: (
            int(item.get("layer", 0)),
            -abs(_polygon_area(item["points"])), item["id"]),
    )[:32]
    all_points = [point for item in component_outlines
                  for point in item["points"]]
    alignment_points = all_points
    # Component-only garment surfaces must retain their position on the
    # selected full-height avatar.  Scaling a cropped top or two trouser legs
    # by their own bounds moves the garment to the head and destroys the
    # source-view proportions.  A fused subject outline is only an alignment
    # frame here; none of its body/hair pixels become garment geometry.
    raw_alignment = fallback.get("outline")
    if (garment_components_only and fused_foreground
            and _sequence(raw_alignment) and len(raw_alignment) >= 3):
        parsed_alignment = []
        for point in raw_alignment:
            if not _sequence(point) or len(point) < 2:
                parsed_alignment = []
                break
            x, y = _finite(point[0]), _finite(point[1])
            if x is None or y is None:
                parsed_alignment = []
                break
            parsed_alignment.append([x, y])
        if (len(parsed_alignment) >= 3
                and abs(_polygon_area(parsed_alignment)) > 1.0e-9):
            alignment_points = parsed_alignment
    xs = [point[0] for point in alignment_points]
    ys = [point[1] for point in alignment_points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x, span_y = max_x - min_x, max_y - min_y
    if span_x <= 1.0e-9 or span_y <= 1.0e-9:
        return None
    # A bounded, inspectable CAD envelope. It is intentionally dense enough
    # for brush editing but remains a front-silhouette proposal rather than a
    # claimed single-view reconstruction.
    measurements = avatar["measurements_cm"]
    avatar_height = float(measurements["height"])
    # A fused foreground contains the photographed subject from head to foot,
    # unlike the historical garment-only silhouette.  Use the user-selected
    # height only as the preview world scale and align the complete image
    # subject to it.  This is not a height measurement recovered from one
    # image; the normalised image proportions remain proposal-only below.
    target_height = (avatar_height if (fused_foreground
                                       or garment_components_only)
                     else avatar_height * 0.78)
    scale = target_height / span_y
    center_x = (min_x + max_x) * 0.5
    top_y = max_y
    chest_radius = float(measurements["chest_bust"]) / (2.0 * math.pi)
    hip_radius = float(measurements["hip"]) / (2.0 * math.pi)
    # The former 0.72 * chest radius put the target inside the rendered body;
    # the mannequin then hid the projected front and left only the cyan depth
    # wall visible.  Keep this visual target outside the selected avatar.  The
    # real clearance solver remains the authority for thickness/penetration.
    depth = max(3.0, chest_radius * 1.10, hip_radius * 1.06) + 0.4
    vertices: List[List[float]] = []
    texture_coordinates: List[List[float]] = []
    faces: List[List[int]] = []
    face_regions: List[str] = []
    face_component_ids: List[str] = []
    component_ids: List[str] = []
    component_records: List[Dict[str, Any]] = []
    front_face_count = 0
    rear_face_count = 0
    for component_index, item in enumerate(component_outlines):
        raw_points = item["points"]
        sample_count = max(48, min(128, len(raw_points)))
        boundary = _resample_closed_polyline(raw_points, sample_count)
        front_triangles = _triangulate_simple_polygon(boundary)
        if len(front_triangles) != sample_count - 2:
            continue
        component_ids.append(item["id"])
        component_records.append({
            "component_id": item["id"],
            "part_id": item.get("part_id", item["id"]),
            "state": item.get("state", "PROPOSED"),
            "side": item.get("side", "unspecified"),
            "layer": int(item.get("layer", 0)),
            "garment_unit": item.get("garment_unit"),
            "semantic_role": item.get("semantic_role"),
            "average_rgba": copy.deepcopy(item.get("average_rgba")),
            "outline_digest": stable_digest(item["points"]),
        })
        offset = len(vertices)
        # A tiny deterministic separation prevents coincident disconnected
        # colour components from z-fighting; it is not treated as layer truth.
        component_depth = (depth + int(item.get("layer", 0)) * 0.24
                           + component_index * 0.035)
        if fused_foreground or garment_components_only:
            # A missing external single-view provider must not be imitated by
            # a torso-wide front/back box.  Project the complete foreground
            # onto a thin, gently curved front shell instead.  It is faithful
            # in the source camera, editable from nearby angles, and its thin
            # edge makes the single-view limitation visible rather than
            # presenting an invented back as a volumetric reconstruction.
            half_span = max(span_x * 0.5, 1.0e-9)
            shell_thickness_cm = 0.12
            front = []
            back = []
            for point in boundary:
                x_cm = (point[0] - center_x) * scale
                y_cm = ((top_y - point[1]) * scale
                        - target_height * 0.52)
                normalised_x = max(
                    -1.0, min(1.0, (point[0] - center_x) / half_span))
                curvature = math.sqrt(max(
                    0.08, 1.0 - normalised_x * normalised_x))
                front_z = component_depth * curvature
                front.append([x_cm, y_cm, front_z])
                back.append([x_cm, y_cm,
                             max(0.0, front_z - shell_thickness_cm)])
        else:
            front = [[(point[0] - center_x) * scale,
                      (top_y - point[1]) * scale - target_height * 0.52,
                      component_depth] for point in boundary]
            back = [[point[0], point[1], -component_depth] for point in front]
        # RegionPicker/GarmentOutline points use image coordinates whose
        # origin is the top-left.  SceneKit's NSImage-backed material also
        # presents the image top at V=0 for this geometry source.  Preserve
        # that convention here.  Using ``1 - y`` turns only the texture
        # upside-down while the reconstructed geometry itself stays upright.
        front_uv = [[min(1.0, max(0.0, point[0] / width)),
                     min(1.0, max(0.0, point[1] / height))]
                    for point in boundary]
        # The fused cleanup surface is subdivided for brush editing.  The
        # garment-component surface is a candidate-rendering boundary: extra
        # interior subdivision does not improve its image silhouette and
        # multiplies every later candidate binding cost, so retain the exact
        # resampled boundary with the simpler triangulation there.
        if fused_foreground and not garment_components_only:
            front, front_uv, front_triangles = _subdivide_triangle_mesh(
                front, front_uv, front_triangles, levels=2)
            back = [[point[0], point[1], max(0.0, point[2] - 0.12)]
                    for point in front]
        front_vertex_count = len(front)
        vertices.extend(front)
        vertices.extend(back)
        texture_coordinates.extend(front_uv)
        texture_coordinates.extend(copy.deepcopy(front_uv))
        rear_offset = offset + front_vertex_count
        for triangle in front_triangles:
            # Triangulation runs in image coordinates (Y points down), while
            # the 3-D conversion above makes Y point up.  That reflection
            # reverses winding.  Reverse the visible/front triangle here so
            # the +Z camera sees its front face instead of SceneKit showing a
            # double-sided, horizontally reversed back face.
            faces.append([offset + triangle[0],
                          offset + triangle[2],
                          offset + triangle[1]])
            face_regions.append("front-visible-surface")
            face_component_ids.append(item["id"])
            front_face_count += 1
            # Rear outward normals point toward -Z, so retain the reflected
            # image-coordinate winding there.
            faces.append([rear_offset + triangle[0],
                          rear_offset + triangle[1],
                          rear_offset + triangle[2]])
            face_regions.append("rear-proposed-surface")
            face_component_ids.append(item["id"])
            rear_face_count += 1
        # The first sample_count vertices remain the original ordered outer
        # boundary even after subdivision, so only those form the thin rim.
        for index in range(sample_count):
            nxt = (index + 1) % sample_count
            faces.append([offset + index, rear_offset + index,
                          rear_offset + nxt])
            face_regions.append("edge-proposed-surface")
            face_component_ids.append(item["id"])
            faces.append([offset + index, rear_offset + nxt, offset + nxt])
            face_regions.append("edge-proposed-surface")
            face_component_ids.append(item["id"])
    if not vertices or not faces:
        return None
    if fused_foreground and not garment_components_only:
        # Closed-polyline resampling does not guarantee that an original
        # topmost or bottommost vertex is one of its equally spaced samples.
        # Renormalise the completed mesh so the preview subject is exactly
        # head-to-foot aligned to the *selected* height scale. UVs remain in
        # source-image coordinates and are deliberately untouched.
        mesh_floor = min(point[1] for point in vertices)
        mesh_top = max(point[1] for point in vertices)
        mesh_height = mesh_top - mesh_floor
        if mesh_height > 1.0e-9:
            for point in vertices:
                point[1] = ((point[1] - mesh_floor) / mesh_height
                            * target_height - target_height * 0.52)
    image_proportion_fit: Optional[Dict[str, Any]] = None
    if fused_foreground:
        mesh_x = [point[0] for point in vertices]
        mesh_y = [point[1] for point in vertices]
        image_proportion_fit = {
            "schema": "garment.image-proportion-fit.v1",
            "state": "PROPOSED",
            "authority": "PROPOSED_IMAGE_PROPORTION_FIT",
            "basis": "FUSED_SUBJECT_OUTLINE_AND_MESH_BOUNDS",
            "subject_bounds_px": {
                "min_x": round(min_x, 8),
                "max_x": round(max_x, 8),
                "top_y": round(min_y, 8),
                "bottom_y": round(max_y, 8),
                "width": round(span_x, 8),
                "head_to_foot_height": round(span_y, 8),
            },
            "subject_mesh_bounds_cm": {
                "min_x": round(min(mesh_x), 8),
                "max_x": round(max(mesh_x), 8),
                "floor_y": round(min(mesh_y), 8),
                "top_y": round(max(mesh_y), 8),
                "head_to_foot_height": round(max(mesh_y) - min(mesh_y), 8),
            },
            "selected_avatar_inputs": {
                "state": "SELECTED",
                "authority": "REQUESTED_OR_SELECTED",
                "height_cm": round(float(measurements["height"]), 8),
                "chest_bust_cm": round(float(measurements["chest_bust"]), 8),
                "waist_cm": round(float(measurements["waist"]), 8),
                "hip_cm": round(float(measurements["hip"]), 8),
            },
            "visual_fit_does_not_change_selected_measurements": True,
            "texture_convention": "IMAGE_TOP_IS_TEXTURE_V_0",
            "does_not_observe": [
                "actual wearer height",
                "actual wearer chest circumference",
                "actual wearer waist circumference",
                "actual wearer hip circumference",
                "depth", "rear body shape",
            ],
        }
    result = {
        "schema": "garment.target-sculpt-surface.v1",
        "source": (
            "IMAGE_GARMENT_COMPONENT_FRONT_TARGET"
            if garment_components_only else
            ("FUSED_FOREGROUND_FRONT_CONFORMAL_FALLBACK"
             if fused_foreground else "GEOMETRIC_FRONT_FALLBACK")
        ),
        "surface_mode": (
            "GARMENT_COMPONENT_FRONT_SHELL"
            if garment_components_only else
            ("FRONT_CONFORMAL_SHELL" if fused_foreground
             else "AVATAR_ENVELOPE")
        ),
        "target_role": ("GARMENT_COMPONENT_CANDIDATE_FRONT"
                        if garment_components_only else target_role),
        "state": "PROPOSED",
        "authority": "PROPOSED_PREVIEW",
        "vertices_cm": [[round(value, 8) for value in point]
                        for point in vertices],
        "texture_coordinates": [
            [round(value, 8) for value in point]
            for point in texture_coordinates
        ],
        "faces": faces,
        "face_region_ids": face_regions,
        "face_component_ids": face_component_ids,
        "editable_face_count": len(faces),
        "front_face_count": front_face_count,
        "rear_face_count": rear_face_count,
        "component_count": len(component_ids),
        "component_region_ids": component_ids,
        "component_records": component_records,
        "avatar_inside": not (fused_foreground or garment_components_only),
        "image_proportion_fit": image_proportion_fit,
        "default_cloth_thickness_mm": 1.0,
        "limitations": ([
            "visible garment-component outlines are image/model proposals, not seam observations",
            "component front positions use the fused subject only as an avatar-alignment frame",
            "rear, depth, layer ownership and hidden joins remain proposed",
            "surface is for candidate comparison, not manufacturing",
        ] if garment_components_only else [
            "complete salient foreground, not a garment-only segmentation",
            "thin front-conformal 2.5D shell; no rear geometry was observed or invented",
            "human must erase body, hair, skin, background and unrelated garments",
            "surface is for CAD cleanup and same-camera comparison, not manufacturing",
        ] if fused_foreground else [
            "component-local front outline loft; not an external single-view 3D reconstruction",
            "rear depth is a proposed avatar-relative envelope",
            "surface is for CAD cleanup and comparison targeting, not manufacturing",
        ]),
    }
    result["digest"] = stable_digest(result)
    return result


def _external_sculpt_surface(
        reconstruction: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    mesh = reconstruction.get("mesh")
    if not isinstance(mesh, Mapping):
        return None
    vertices = mesh.get("vertices_cm")
    faces = mesh.get("faces")
    if not _sequence(vertices) or not _sequence(faces):
        return None
    return {
        "schema": "garment.target-sculpt-surface.v1",
        "source": "EXTERNAL_SINGLE_VIEW_3D",
        "state": "PROPOSED",
        "authority": "PROPOSED_PREVIEW",
        "vertices_cm": copy.deepcopy(vertices),
        "texture_coordinates": copy.deepcopy(
            mesh.get("texture_coordinates", [])),
        "faces": copy.deepcopy(faces),
        "face_region_ids": copy.deepcopy(mesh.get("face_region_ids", [])),
        "editable_face_count": len(faces),
        "avatar_inside": True,
        "default_cloth_thickness_mm": 1.0,
        "limitations": [
            "provider mesh remains AI-generated until a person edits and adopts it",
            "single-view rear and occluded geometry remain proposed",
        ],
    }


def _target_bound_refusal(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    result = {
        "schema": TARGET_BOUND_PREVIEW_SCHEMA,
        "verdict": code,
        "state": "UNKNOWN",
        "why": why,
        "authority": {
            "front": "UNKNOWN",
            "rear": "PROPOSED",
            "depth": "PROPOSED",
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        **detail,
    }
    result["digest"] = stable_digest(result)
    return result


def _mesh_points(value: Any, *, field: str) -> List[List[float]]:
    if not _sequence(value) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    result: List[List[float]] = []
    for index, point in enumerate(value):
        if not _sequence(point) or len(point) < 3:
            raise ValueError(f"{field}[{index}] must contain x/y/z")
        parsed = [_finite(point[axis]) for axis in range(3)]
        if any(component is None for component in parsed):
            raise ValueError(f"{field}[{index}] contains a non-finite value")
        result.append([float(component) for component in parsed])
    return result


def _mesh_faces(value: Any, *, vertex_count: int,
                field: str) -> List[List[int]]:
    if not _sequence(value) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    result: List[List[int]] = []
    for index, face in enumerate(value):
        if (not _sequence(face) or len(face) < 3
                or any(isinstance(item, bool) or not isinstance(item, int)
                       for item in face)):
            raise ValueError(f"{field}[{index}] must contain integer indices")
        parsed = [int(item) for item in face]
        if any(item < 0 or item >= vertex_count for item in parsed):
            raise ValueError(f"{field}[{index}] references an absent vertex")
        if len(set(parsed)) < 3:
            raise ValueError(f"{field}[{index}] is degenerate")
        result.append(parsed)
    return result


def _dominant(values: Sequence[Any], fallback: Any) -> Any:
    counts: Dict[Any, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return fallback
    return sorted(counts, key=lambda value: (-counts[value], str(value)))[0]


def build_target_bound_candidate_preview(
        request: Mapping[str, Any]) -> Dict[str, Any]:
    """Bind an exact source-view front to one typed candidate's proposed rear.

    The front vertices and front triangles are copied byte-for-byte (after
    JSON number normalisation) from the selected target surface.  Candidate
    geometry is used only as a deterministic depth/width field for newly
    generated rear and rim vertices.  Consequently a one-view model can vary
    candidate backs without erasing a photographed asymmetric front, joining
    separated upper/lower components, or promoting hidden geometry to fact.
    """
    if not isinstance(request, Mapping):
        return _target_bound_refusal(
            "UNKNOWN_TARGET_BOUND_PREVIEW_REQUEST",
            "request must be an object")
    if request.get("schema") != TARGET_BOUND_PREVIEW_REQUEST_SCHEMA:
        return _target_bound_refusal(
            "UNKNOWN_TARGET_BOUND_PREVIEW_SCHEMA",
            f"schema must be exactly {TARGET_BOUND_PREVIEW_REQUEST_SCHEMA}")
    candidate_id = _nonempty(request.get("candidate_id"))
    if not candidate_id:
        return _target_bound_refusal(
            "UNKNOWN_TARGET_BOUND_PREVIEW_CANDIDATE_ID",
            "candidate_id is required")
    try:
        avatar = _base_avatar(request.get("base_avatar"))
        target = request.get("front_target")
        candidate = request.get("candidate_preview")
        if not isinstance(target, Mapping):
            raise ValueError("front_target must be an object")
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate_preview must be an object")
        if candidate.get("verdict") != "ANSWER":
            raise ValueError("candidate_preview must have verdict ANSWER")
        if str(candidate.get("candidate_id", "")) != candidate_id:
            raise ValueError("candidate_preview candidate_id does not match")

        target_points = _mesh_points(
            target.get("vertices_cm"), field="front_target.vertices_cm")
        target_faces = _mesh_faces(
            target.get("faces"), vertex_count=len(target_points),
            field="front_target.faces")
        face_regions = target.get("face_region_ids")
        if (not _sequence(face_regions)
                or len(face_regions) != len(target_faces)
                or any(not isinstance(value, str) for value in face_regions)):
            raise ValueError(
                "front_target.face_region_ids must align with its faces")
        raw_components = target.get("face_component_ids", [])
        if raw_components in (None, []):
            face_components = ["source-front"] * len(target_faces)
        elif (_sequence(raw_components)
              and len(raw_components) == len(target_faces)
              and all(isinstance(value, str) for value in raw_components)):
            face_components = list(raw_components)
        else:
            raise ValueError(
                "front_target.face_component_ids must align with its faces")
        raw_removed = target.get("removed_face_indices", [])
        if (not _sequence(raw_removed)
                or any(isinstance(value, bool) or not isinstance(value, int)
                       or value < 0 or value >= len(target_faces)
                       for value in raw_removed)):
            raise ValueError(
                "front_target.removed_face_indices contains an invalid face")
        removed = set(int(value) for value in raw_removed)

        mesh = candidate.get("mesh")
        if not isinstance(mesh, Mapping):
            raise ValueError("candidate_preview.mesh must be an object")
        candidate_points = _mesh_points(
            mesh.get("vertices"), field="candidate_preview.mesh.vertices")
        candidate_faces = _mesh_faces(
            mesh.get("faces"), vertex_count=len(candidate_points),
            field="candidate_preview.mesh.faces")
        structure_digest = _nonempty(candidate.get("structure_digest"))
        if not structure_digest:
            raise ValueError("candidate_preview.structure_digest is required")
    except (TypeError, ValueError, OverflowError) as exc:
        return _target_bound_refusal(
            "UNKNOWN_TARGET_BOUND_PREVIEW_GEOMETRY", str(exc),
            candidate_id=candidate_id)

    front_source_indices = [
        index for index, region in enumerate(face_regions)
        if index not in removed and region == "front-visible-surface"
    ]
    if not front_source_indices:
        return _target_bound_refusal(
            "UNKNOWN_TARGET_BOUND_PREVIEW_FRONT_REQUIRED",
            "the cleaned target has no front-visible-surface triangles",
            candidate_id=candidate_id)
    source_vertex_ids = sorted({
        vertex for face_index in front_source_indices
        for vertex in target_faces[face_index]
    })
    remap = {source: index for index, source in enumerate(source_vertex_ids)}
    front_vertices = [copy.deepcopy(target_points[index])
                      for index in source_vertex_ids]
    front_faces = [[remap[index] for index in target_faces[face_index]]
                   for face_index in front_source_indices]

    raw_uv = target.get("texture_coordinates", [])
    if (_sequence(raw_uv) and len(raw_uv) == len(target_points)
            and all(_sequence(point) and len(point) >= 2 for point in raw_uv)):
        front_uv = [[float(raw_uv[index][0]), float(raw_uv[index][1])]
                    for index in source_vertex_ids]
    else:
        front_uv = []

    target_x = [point[0] for point in front_vertices]
    target_y = [point[1] for point in front_vertices]
    candidate_x = [point[0] for point in candidate_points]
    candidate_y = [point[1] for point in candidate_points]
    candidate_z = [point[2] for point in candidate_points]
    tx0, tx1, ty0, ty1 = min(target_x), max(target_x), min(target_y), max(target_y)
    cx0, cx1, cy0, cy1 = (min(candidate_x), max(candidate_x),
                          min(candidate_y), max(candidate_y))
    tz_span = max(ty1 - ty0, 1.0e-9)
    tx_span = max(tx1 - tx0, 1.0e-9)
    cy_span = max(cy1 - cy0, 1.0e-9)
    cx_span = max(cx1 - cx0, 1.0e-9)
    cz0, cz1 = min(candidate_z), max(candidate_z)
    cz_center = (cz0 + cz1) * 0.5
    cz_half = max((cz1 - cz0) * 0.5, 1.0e-6)

    candidate_vertex_nodes: List[str] = ["candidate-surface"] * len(candidate_points)
    candidate_vertex_layers: List[int] = [0] * len(candidate_points)
    raw_node_ids = mesh.get("face_node_ids", [])
    raw_face_layers = mesh.get("face_layers", [])
    node_votes: List[List[str]] = [[] for _ in candidate_points]
    layer_votes: List[List[int]] = [[] for _ in candidate_points]
    if (_sequence(raw_node_ids) and len(raw_node_ids) == len(candidate_faces)):
        for face, node_id in zip(candidate_faces, raw_node_ids):
            if not isinstance(node_id, str):
                continue
            for vertex in face:
                node_votes[vertex].append(node_id)
    if (_sequence(raw_face_layers)
            and len(raw_face_layers) == len(candidate_faces)):
        for face, layer in zip(candidate_faces, raw_face_layers):
            if isinstance(layer, int) and not isinstance(layer, bool):
                for vertex in face:
                    layer_votes[vertex].append(layer)
    for index in range(len(candidate_points)):
        candidate_vertex_nodes[index] = _dominant(
            node_votes[index], "candidate-surface")
        candidate_vertex_layers[index] = int(_dominant(layer_votes[index], 0))

    normalised_candidate = [
        ((point[0] - cx0) / cx_span, (point[1] - cy0) / cy_span)
        for point in candidate_points
    ]
    nearest_candidate_ids: List[int] = []
    local_back_z: List[float] = []
    local_width_ratio: List[float] = []
    for point in front_vertices:
        u = (point[0] - tx0) / tx_span
        v = (point[1] - ty0) / tz_span
        ranked = sorted(
            range(len(candidate_points)),
            key=lambda index: (
                (normalised_candidate[index][0] - u) ** 2
                + (normalised_candidate[index][1] - v) ** 2,
                index),
        )[:min(12, len(candidate_points))]
        nearest_candidate_ids.append(ranked[0])
        local_back_z.append(min(candidate_points[index][2] for index in ranked))
        local_width_ratio.append(min(
            1.0,
            max(abs(candidate_points[index][0] - (cx0 + cx1) * 0.5)
                for index in ranked) / max(cx_span * 0.5, 1.0e-9),
        ))

    measurements = avatar["measurements_cm"]
    rear_vertices: List[List[float]] = []
    vertex_node_ids: List[str] = []
    vertex_layers: List[int] = []
    for index, point in enumerate(front_vertices):
        vertical = (point[1] - ty0) / tz_span
        if vertical >= 0.56:
            circumference = float(measurements["chest_bust"])
        elif vertical >= 0.36:
            circumference = float(measurements["waist"])
        else:
            circumference = float(measurements["hip"])
        body_half_depth = max(5.0, circumference / (2.0 * math.pi) * 0.88)
        depth_ratio = max(
            0.45, min(1.25, (cz_center - local_back_z[index]) / cz_half))
        candidate_vertex = nearest_candidate_ids[index]
        layer = candidate_vertex_layers[candidate_vertex]
        width_scale = 0.90 + 0.08 * local_width_ratio[index]
        rear_vertices.append([
            round(point[0] * width_scale, 8),
            round(point[1], 8),
            round(-body_half_depth * depth_ratio - max(0, layer) * 0.18, 8),
        ])
        vertex_node_ids.append(candidate_vertex_nodes[candidate_vertex])
        vertex_layers.append(layer)

    vertex_count = len(front_vertices)
    output_vertices = front_vertices + rear_vertices
    output_faces: List[List[int]] = []
    output_regions: List[str] = []
    output_components: List[str] = []
    output_node_ids: List[str] = []
    output_layers: List[int] = []
    edge_counts: Dict[tuple[int, int], int] = {}
    edge_face: Dict[tuple[int, int], int] = {}
    for local_face_index, face in enumerate(front_faces):
        source_face_index = front_source_indices[local_face_index]
        nodes = [vertex_node_ids[index] for index in face]
        layers = [vertex_layers[index] for index in face]
        node_id = str(_dominant(nodes, "candidate-surface"))
        layer = int(_dominant(layers, 0))
        component_id = face_components[source_face_index]
        output_faces.append(face)
        output_regions.append("front-visible-surface")
        output_components.append(component_id)
        output_node_ids.append(node_id)
        output_layers.append(layer)
        output_faces.append([index + vertex_count for index in reversed(face)])
        output_regions.append("rear-proposed-surface")
        output_components.append(component_id)
        output_node_ids.append(node_id)
        output_layers.append(layer)
        for position, first in enumerate(face):
            second = face[(position + 1) % len(face)]
            edge = (min(first, second), max(first, second))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            edge_face.setdefault(edge, local_face_index)
    for edge in sorted(edge for edge, count in edge_counts.items() if count == 1):
        first, second = edge
        local_face_index = edge_face[edge]
        source_face_index = front_source_indices[local_face_index]
        component_id = face_components[source_face_index]
        node_id = str(_dominant(
            [vertex_node_ids[first], vertex_node_ids[second]],
            "candidate-surface"))
        layer = int(_dominant(
            [vertex_layers[first], vertex_layers[second]], 0))
        output_faces.extend([
            [first, second + vertex_count, second],
            [first, first + vertex_count, second + vertex_count],
        ])
        output_regions.extend(["edge-proposed-surface"] * 2)
        output_components.extend([component_id] * 2)
        output_node_ids.extend([node_id] * 2)
        output_layers.extend([layer] * 2)

    component_ids = sorted(set(output_components))
    result = {
        "schema": TARGET_BOUND_PREVIEW_SCHEMA,
        "verdict": "ANSWER",
        "state": "PROPOSED",
        "candidate_id": candidate_id,
        "structure_digest": structure_digest,
        "mesh": {
            "units": "cm",
            "vertices": output_vertices,
            "faces": output_faces,
            "face_region_ids": output_regions,
            "face_component_ids": output_components,
            "face_node_ids": output_node_ids,
            "face_layers": output_layers,
            "texture_coordinates": front_uv + copy.deepcopy(front_uv)
                if front_uv else [],
        },
        "binding": {
            "front_target_digest": (
                _nonempty(target.get("digest"))
                or stable_digest({
                    "vertices_cm": target_points,
                    "faces": target_faces,
                    "removed_face_indices": sorted(removed),
                })
            ),
            "candidate_preview_digest": candidate.get("preview_digest"),
            "body_proxy_id": avatar["avatar_id"],
            "body_proxy_authority": avatar["authority"],
            "front_fixed": True,
            "front_authority": str(
                target.get("authority", "PROPOSED_IMAGE_FRONT")),
            "rear_observed": False,
            "rear_method": "CANDIDATE_GEOMETRY_DEPTH_FIELD_ON_SELECTED_BODY",
            "source_front_face_indices": front_source_indices,
        },
        "preservation": {
            "front_vertices_preserved_exactly": True,
            "front_faces_preserved_exactly": True,
            "front_component_count": len(component_ids),
            "front_component_ids": component_ids,
            "disconnected_components_not_bridged": True,
            "left_right_image_asymmetry_preserved": True,
            "upper_lower_image_separation_preserved": True,
            "typed_candidate_node_ids_on_proposed_rear": sorted(
                set(output_node_ids)),
            "typed_candidate_layers_on_proposed_rear": sorted(
                set(output_layers)),
        },
        "authority": {
            "front": str(target.get("authority", "PROPOSED_IMAGE_FRONT")),
            "rear": "PROPOSED",
            "depth": "PROPOSED",
            "body": avatar["authority"],
            "material": "UNKNOWN",
            "seams": "UNKNOWN",
        },
        "claims": {
            "image_specific_front": True,
            "candidate_specific_rear": True,
            "rear_observed": False,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        },
        "limitations": [
            "front is a selected image target, not a measured garment surface",
            "rear and depth are candidate/body-constrained proposals",
            "layer labels do not prove seam ownership or hidden construction",
            "no material, fit, strength or manufacturing guarantee is created",
        ],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["preview_digest"] = stable_digest({
        "candidate_id": candidate_id,
        "structure_digest": structure_digest,
        "mesh": result["mesh"],
        "binding": result["binding"],
        "preservation": result["preservation"],
    })
    result["digest"] = stable_digest(result)
    return result


def prepare_target_reconstruction(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Build one deterministic, reversible cleanup state."""

    if request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            "UNKNOWN_TARGET_RECONSTRUCTION_SCHEMA",
            f"schema must be exactly {REQUEST_SCHEMA}",
            received_schema=request.get("schema"),
        )
    camera_digest = _camera_digest(request)
    if not camera_digest:
        return _refusal(
            "UNKNOWN_TARGET_RECONSTRUCTION_CAMERA_REQUIRED",
            "camera_digest or a typed camera object is required for same-camera comparison",
        )
    image_digest = _source_digest(request.get("source"))
    if not image_digest:
        return _refusal(
            "UNKNOWN_TARGET_RECONSTRUCTION_SOURCE_REQUIRED",
            "source.image_digest or stable source metadata is required",
            camera_digest=camera_digest,
        )
    try:
        base_avatar = _base_avatar(request.get("base_avatar"))
    except ValueError as exc:
        return _refusal(
            "UNKNOWN_TARGET_RECONSTRUCTION_AVATAR_REQUIRED",
            str(exc), camera_digest=camera_digest, source_image_digest=image_digest,
        )
    try:
        regions = _normalise_regions(request.get("regions"))
    except ValueError as exc:
        return _refusal(
            "UNKNOWN_TARGET_RECONSTRUCTION_REGIONS",
            str(exc), camera_digest=camera_digest, source_image_digest=image_digest,
        )

    edits = request.get("edits")
    if not isinstance(edits, Mapping):
        edits = {}
    remove_ids = edits.get("remove_region_ids", [])
    if not _sequence(remove_ids) or any(not _nonempty(v) for v in remove_ids):
        return _refusal(
            "UNKNOWN_TARGET_RECONSTRUCTION_EDITS",
            "edits.remove_region_ids must be an array of region ids",
            camera_digest=camera_digest, source_image_digest=image_digest,
        )
    requested_removals = {_nonempty(v) for v in remove_ids if _nonempty(v)}
    known_ids = {region["id"] for region in regions}
    unknown_ids = sorted(requested_removals - known_ids)
    if unknown_ids:
        return _refusal(
            "UNKNOWN_TARGET_RECONSTRUCTION_REGION_ID",
            "cleanup cannot remove an unbound region",
            unknown_region_ids=unknown_ids,
            camera_digest=camera_digest,
            source_image_digest=image_digest,
        )

    reconstruction = _reconstruction_envelope(request)
    sculpt_surface = (_external_sculpt_surface(
        request.get("reconstruction") if isinstance(
            request.get("reconstruction"), Mapping) else {})
        if reconstruction["source_kind"] == "EXTERNAL_SINGLE_VIEW_3D"
        else _fallback_sculpt_surface(reconstruction, base_avatar, regions))
    # Keep the editable fused person+clothing target and the garment-only
    # candidate front as two different artifacts.  The former is appropriate
    # for the human erase/restore tool; the latter prevents the later 3-D
    # candidate from regressing to a full-person cardboard shell or a generic
    # BODY_SHELL primitive.  This surface is still only PROPOSED image
    # component geometry and cannot establish seams, depth or construction.
    garment_component_surface = (
        None if reconstruction["source_kind"] == "EXTERNAL_SINGLE_VIEW_3D"
        else _fallback_sculpt_surface(
            reconstruction, base_avatar, regions,
            garment_components_only=True)
    )
    holes: List[Dict[str, Any]] = []
    completions: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []
    for region in regions:
        if region["id"] not in requested_removals:
            continue
        if not region["removable"]:
            review.append({
                "code": "REVIEW_GARMENT_TARGET_REGION_PRESERVED",
                "region_id": region["id"],
                "state": "REVIEW",
                "why": "garment target regions cannot be removed by cleanup",
            })
            continue
        region["removed"] = True
        if region["class"] in {"BODY", "SKIN"}:
            boundary_state = str(
                request.get("body_garment_boundary_state", "UNKNOWN")
            ).upper()
            if boundary_state not in {"OBSERVED", "CONFIRMED"}:
                review.append({
                    "code": "REVIEW_BODY_GARMENT_BOUNDARY_REQUIRED",
                    "region_id": region["id"],
                    "state": "REVIEW",
                    "why": (
                        "body exclusion is display-only until a body/garment "
                        "boundary is explicitly supplied"
                    ),
                })
        if (region["class"] in _OCCLUDER_CLASSES
                and (region["occludes_garment"] or region["overlap_part_ids"])):
            hole_id = "hole:" + region["id"]
            holes.append({
                "id": hole_id,
                "removed_region_id": region["id"],
                "state": "UNKNOWN_OCCLUDED_SURFACE",
                "target_part_ids": region["overlap_part_ids"],
                "camera_digest": camera_digest,
            })
            if region["overlap_part_ids"]:
                completions.append({
                    "id": "completion:" + region["id"],
                    "hole_id": hole_id,
                    "target_part_ids": region["overlap_part_ids"],
                    "state": "PROPOSED_OCCLUSION_BACKFILL",
                    "method": "LOCAL_BOUNDARY_AND_STRUCTURE_CONTINUATION",
                    "observed": False,
                    "human_approval_required": True,
                })
            else:
                review.append({
                    "code": "REVIEW_OCCLUSION_TARGET_REQUIRED",
                    "region_id": region["id"],
                    "state": "REVIEW",
                    "why": "the removed occluder has no typed garment target",
                })

    if any(item["code"] == "REVIEW_BODY_GARMENT_BOUNDARY_REQUIRED" for item in review):
        stage = "REVIEW_BODY_GARMENT_BOUNDARY"
    elif holes:
        stage = "REVIEW_OCCLUSION_COMPLETION"
    elif requested_removals:
        stage = "CLEANED_TARGET_READY"
    else:
        stage = "FUSED_TARGET_READY"

    fallback_meta = (reconstruction.get("fallback")
                     if isinstance(reconstruction.get("fallback"), Mapping)
                     else {})
    raw_target_role = str(fallback_meta.get(
        "target_role", "SAME_CAMERA_VISUAL_GEOMETRY_TARGET")).upper()
    canonical_target_role = (
        "FUSED_PERSON_AND_GARMENT_CAD_TARGET"
        if raw_target_role in _FUSED_TARGET_ROLES else raw_target_role
    )
    fused_source_region_ids = sorted(
        region["id"] for region in regions
        if str(region.get("target_role", "")).startswith("FUSED_PERSON_AND_")
    )
    target_provenance = {
        "authority": "PROPOSED",
        "selection_mode": str(fallback_meta.get(
            "selection_mode", "FOREGROUND_SUBJECT_MASK")).upper(),
        "source_region_ids": fused_source_region_ids,
        "source": copy.deepcopy(fallback_meta.get("source")),
        "does_not_observe": [
            "rear", "depth", "seams", "material", "manufacturing_method",
        ],
    }

    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_TARGET_RECONSTRUCTION",
        "state": "PROPOSED",
        "stage": stage,
        "source_image_digest": image_digest,
        "camera_digest": camera_digest,
        "base_avatar": base_avatar,
        "base_avatar_locked_for_loop": True,
        "composition_order": [
            "SELECT_BASE_AVATAR",
            "ALIGN_SINGLE_VIEW_TARGET",
            "FUSE_PERSON_AND_CLOTHING_SURFACE",
            "USER_CLEANUP",
            "PROPOSE_OCCLUDED_GARMENT_SURFACE",
            "PATTERN_DRESS_AND_REPROJECT",
        ],
        "reconstruction": reconstruction,
        "sculpt_surface": sculpt_surface,
        "sculpt_ready": sculpt_surface is not None,
        "garment_component_surface": garment_component_surface,
        "garment_component_surface_ready": (
            garment_component_surface is not None),
        "regions": regions,
        "removed_region_ids": sorted(
            region["id"] for region in regions if region["removed"]
        ),
        "remaining_region_ids": sorted(
            region["id"] for region in regions if not region["removed"]
        ),
        "occlusion_holes": holes,
        "completion_proposals": completions,
        "review_items": review,
        "target_role": canonical_target_role,
        "target_provenance": target_provenance,
        "garment_extraction_ready": not review and bool(
            any(region["class"] == "GARMENT" and not region["removed"]
                for region in regions)
        ),
        "rear_state": "UNKNOWN_OR_PROPOSED",
        "material_state": "UNKNOWN",
        "sewing_state": "UNKNOWN",
        "human_approval_required": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    digest_payload = copy.deepcopy(result)
    result["target_digest"] = stable_digest(digest_payload)
    return result
