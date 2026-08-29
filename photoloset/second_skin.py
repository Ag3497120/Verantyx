# -*- coding: utf-8 -*-
"""Model-free second-skin garment scaffolds.

This module deliberately answers a smaller question than a sewing model: given
a mannequin radial cross-section, what deterministic surface lies immediately
outside it, and what unstretched surface would produce it?  It does not name a
fashion style, infer an invisible back, choose seams, or claim cloth physics.

``radius_at`` follows :mod:`photoloset.mannequin`'s contract::

    radius_at(mannequin, height_cm, azimuth_radians) -> radius_cm | None

Dress and skirt scaffolds are closed rings about the mannequin axis.  Trousers
and leggings are represented as two independently closed leg shells; their
join is intentionally left to a later seam/boolean stage.  Per-height ease is
the worn clearance from the form.  Stretch is engineering strain, so the rest
radius is ``worn_radius / (1 + stretch)``.

Calibrated view overlays may contain an ``outline`` or triangle/polygon/
rectangle primitives.  At shared heights their projected half-widths constrain
an axis-aligned section by

    h(t)^2 = a^2 cos(t)^2 + b^2 sin(t)^2.

One view cannot determine both ``a`` and ``b`` and is therefore a typed
refusal, not a plausible-number fallback.  No third-party dependency is used.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
Face = Tuple[int, int, int, int]
RadiusFn = Callable[[Dict[str, Any], float, float], Optional[float]]
Field = Any

ANSWER = "ANSWER"
NO_MANNEQUIN = "UNKNOWN_NO_MANNEQUIN"
BAD_GARMENT = "UNKNOWN_SECOND_SKIN_GARMENT"
BAD_RANGE = "UNKNOWN_SECOND_SKIN_HEIGHT_RANGE"
BAD_RESOLUTION = "UNKNOWN_SECOND_SKIN_RESOLUTION"
BAD_FIELD = "UNKNOWN_SECOND_SKIN_FIELD"
NO_GEOMETRY = "UNKNOWN_INSUFFICIENT_GEOMETRY"
SINGLE_VIEW = "UNKNOWN_SINGLE_VIEW_DEPTH_AMBIGUOUS"
INSUFFICIENT_PARALLAX = "UNKNOWN_INSUFFICIENT_VIEW_PARALLAX"
BAD_VIEW = "UNKNOWN_MALFORMED_CALIBRATED_VIEW"
NO_COMMON_CONSTRAINT = "UNKNOWN_NO_COMMON_OVERLAY_COVERAGE"
INSIDE_FORM = "UNKNOWN_OVERLAY_INSIDE_MANNEQUIN"

_KINDS = {
    "dress": "dress", "torso_dress": "dress", "one_piece": "dress",
    "skirt": "skirt",
    "trousers": "trousers", "trouser": "trousers",
    "pants": "trousers", "leggings": "trousers", "legging": "trousers",
}


def _refuse(verdict: str, why: str, how: str,
            provenance: Optional[Dict[str, Any]] = None,
            **detail: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "verdict": verdict, "why": why, "how_to_close": how,
        "provenance": provenance or {"method": "model-free geometry"},
    }
    result.update(detail)
    return result


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _field_points(field: Field) -> Optional[List[Tuple[float, float]]]:
    if isinstance(field, Mapping):
        raw = list(field.items())
    elif (isinstance(field, Sequence)
          and not isinstance(field, (str, bytes))):
        raw = list(field)
    else:
        return None
    points: List[Tuple[float, float]] = []
    for item in raw:
        if (not isinstance(item, Sequence) or isinstance(item, (str, bytes))
                or len(item) != 2):
            return None
        y, value = _finite(item[0]), _finite(item[1])
        if y is None or value is None:
            return None
        points.append((y, value))
    points.sort()
    if not points or len({y for y, _ in points}) != len(points):
        return None
    return points


def _field_at(field: Field, y: float) -> Optional[float]:
    number = _finite(field)
    if number is not None:
        return number
    if callable(field):
        try:
            return _finite(field(y))
        except Exception:
            return None
    points = _field_points(field)
    if not points:
        return None
    if y <= points[0][0]:
        return points[0][1]
    if y >= points[-1][0]:
        return points[-1][1]
    for (y0, v0), (y1, v1) in zip(points, points[1:]):
        if y0 <= y <= y1:
            u = (y - y0) / (y1 - y0)
            return v0 + (v1 - v0) * u
    return None


def _field_source(field: Field) -> Dict[str, Any]:
    number = _finite(field)
    if number is not None:
        return {"kind": "constant", "value": number}
    if callable(field):
        return {"kind": "callable",
                "name": getattr(field, "__name__", type(field).__name__)}
    points = _field_points(field)
    return {"kind": "piecewise_linear", "points": points}


def _polygon(value: Any, scale: float) -> Optional[List[Vec2]]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or len(value) < 3):
        return None
    out: List[Vec2] = []
    for point in value:
        if (not isinstance(point, Sequence) or isinstance(point, (str, bytes))
                or len(point) != 2):
            return None
        x, y = _finite(point[0]), _finite(point[1])
        if x is None or y is None:
            return None
        out.append((x * scale, y * scale))
    return out if len(set(out)) >= 3 else None


def _view_polygons(view: Mapping[str, Any], scale: float
                   ) -> Optional[List[List[Vec2]]]:
    polygons: List[List[Vec2]] = []
    if "outline" in view:
        outline = _polygon(view["outline"], scale)
        if outline is None:
            return None
        polygons.append(outline)
    raw_primitives = view.get("primitives", view.get("overlays", []))
    if "triangles" in view:
        raw_primitives = list(raw_primitives) + [
            {"type": "triangle", "points": triangle}
            for triangle in view["triangles"]
        ]
    if not isinstance(raw_primitives, Sequence) or isinstance(raw_primitives, (str, bytes)):
        return None
    for primitive in raw_primitives:
        if not isinstance(primitive, Mapping):
            return None
        kind = str(primitive.get("type", "polygon")).lower()
        if kind in ("triangle", "polygon"):
            polygon = _polygon(primitive.get("points"), scale)
        elif kind in ("rectangle", "rect"):
            center = primitive.get("center")
            width, height = _finite(primitive.get("width")), _finite(primitive.get("height"))
            if (not isinstance(center, Sequence) or isinstance(center, (str, bytes))
                    or len(center) != 2 or width is None or height is None
                    or width <= 0.0 or height <= 0.0):
                return None
            cx, cy = _finite(center[0]), _finite(center[1])
            if cx is None or cy is None:
                return None
            polygon = _polygon([
                (cx - width / 2, cy - height / 2),
                (cx + width / 2, cy - height / 2),
                (cx + width / 2, cy + height / 2),
                (cx - width / 2, cy + height / 2),
            ], scale)
        else:
            return None
        if polygon is None:
            return None
        polygons.append(polygon)
    return polygons if polygons else None


def _span_at(polygons: Sequence[Sequence[Vec2]], y: float) -> Optional[float]:
    xs: List[float] = []
    for polygon in polygons:
        for x, py in polygon:
            if abs(py - y) <= 1e-9:
                xs.append(x)
        for index, (x0, y0) in enumerate(polygon):
            x1, y1 = polygon[(index + 1) % len(polygon)]
            if abs(y1 - y0) <= 1e-12:
                continue
            lo, hi = sorted((y0, y1))
            if lo <= y < hi:
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
    return max(xs) - min(xs) if len(xs) >= 2 and max(xs) > min(xs) else None


def _parse_views(views: Sequence[Mapping[str, Any]]) -> Tuple[
        Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    provenance: Dict[str, Any] = {"method": "calibrated primitive projections",
                                  "views": []}
    if len(views) == 1:
        raw = views[0] if isinstance(views[0], Mapping) else {}
        provenance["views"].append({"frame_id": raw.get("frame_id"),
                                    "kind": "OBSERVED"})
        return None, _refuse(
            SINGLE_VIEW,
            "1つの投影幅からは、直交する奥行き半径を決められません",
            "方位角が異なる較正ビューを追加するか、完全なradius_atを使ってください",
            provenance, constrained_axes=1, unknown_axes=1)
    parsed: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(views):
        if not isinstance(raw, Mapping):
            return None, _refuse(BAD_VIEW, f"view {index} がmappingではありません",
                                 "各viewにframe_id, azimuth_deg, cm_per_unitとprimitiveを渡してください",
                                 provenance)
        frame_id = raw.get("frame_id", raw.get("view_id"))
        angle = _finite(raw.get("azimuth_deg"))
        scale = _finite(raw.get("cm_per_unit", raw.get("cm_per_pixel")))
        if (not isinstance(frame_id, str) or not frame_id or frame_id in seen
                or angle is None or scale is None or scale <= 0.0):
            return None, _refuse(BAD_VIEW, f"view {index} の較正情報が不正です",
                                 "一意なframe_id、有限なazimuth_deg、正のcm_per_unitが必要です",
                                 provenance, frame_index=index)
        polygons = _view_polygons(raw, scale)
        if polygons is None:
            return None, _refuse(BAD_VIEW, f"{frame_id} に有効なprimitiveがありません",
                                 "outline、triangle、polygon、rectangleのいずれかを渡してください",
                                 provenance, frame_id=frame_id)
        seen.add(frame_id)
        angle %= 180.0
        parsed.append({"frame_id": frame_id, "source": raw.get("source"),
                       "angle": angle, "polygons": polygons})
        provenance["views"].append({
            "frame_id": frame_id, "source": raw.get("source"),
            "azimuth_deg": round(angle, 6), "cm_per_unit": scale,
            "primitive_count": len(polygons), "kind": "OBSERVED",
        })
    max_gap = max(min(abs(a["angle"] - b["angle"]),
                      180.0 - abs(a["angle"] - b["angle"]))
                  for i, a in enumerate(parsed) for b in parsed[i + 1:])
    if max_gap < 20.0:
        return None, _refuse(
            INSUFFICIENT_PARALLAX,
            f"最大方位角差{max_gap:.3f}°では2軸を安定して分離できません",
            "20°以上離れた較正ビューを追加してください", provenance,
            max_parallax_deg=round(max_gap, 6), minimum_parallax_deg=20.0)
    return parsed, None


def _solve_projection(angles: Sequence[float], half_widths: Sequence[float]
                      ) -> Optional[Tuple[float, float, float, float]]:
    rows = []
    for angle, width in zip(angles, half_widths):
        radians = math.radians(angle)
        rows.append((math.cos(radians) ** 2, math.sin(radians) ** 2, width ** 2))
    cc = sum(c * c for c, _, _ in rows)
    ss = sum(s * s for _, s, _ in rows)
    cs = sum(c * s for c, s, _ in rows)
    cy = sum(c * h for c, _, h in rows)
    sy = sum(s * h for _, s, h in rows)
    determinant = cc * ss - cs * cs
    if determinant <= 1e-12:
        return None
    a2 = (cy * ss - sy * cs) / determinant
    b2 = (sy * cc - cy * cs) / determinant
    if a2 <= 0.0 or b2 <= 0.0:
        return None
    a, b = math.sqrt(a2), math.sqrt(b2)
    before = sum((width - sum(half_widths) / len(half_widths)) ** 2
                 for width in half_widths)
    after = sum((math.sqrt(a2 * c + b2 * s) - width) ** 2
                for (c, s, _), width in zip(rows, half_widths))
    return a, b, math.sqrt(before / len(rows)), math.sqrt(after / len(rows))


def _ellipse_radius(a: float, b: float, theta: float) -> float:
    return a * b / math.sqrt((b * math.cos(theta)) ** 2
                             + (a * math.sin(theta)) ** 2)


def build(man: Dict[str, Any], garment: str = "dress", *,
          radius_at: Optional[RadiusFn] = None,
          y_bottom: Optional[float] = None, y_top: Optional[float] = None,
          ease: Field = 0.0, stretch: Field = 0.0,
          ease_field: Field = None, stretch_field: Field = None,
          segments: int = 24, height_steps: int = 16,
          calibrated_views: Optional[Sequence[Mapping[str, Any]]] = None,
          views: Optional[Sequence[Mapping[str, Any]]] = None,
          overlays: Optional[Sequence[Mapping[str, Any]]] = None,
          leg_radius_ratio: float = 0.42,
          leg_center_ratio: float = 0.48) -> Dict[str, Any]:
    """Build a deterministic worn/rest second-skin shell.

    ``ease_field`` and ``stretch_field`` are aliases that take precedence over
    ``ease`` and ``stretch``.  Each accepts a constant, ``f(y)``, a mapping of
    height to value, or sorted/unsorted ``(height, value)`` pairs.  View input
    may be supplied through any one of ``calibrated_views``, ``views`` or
    ``overlays``; these names are aliases, not independent evidence sets.
    """
    provenance: Dict[str, Any] = {
        "method": "model-free second-skin radial geometry",
        "mannequin_contract": "radius_at(man, y_cm, theta_rad) -> radius_cm | None",
        "generated_not_observed": True,
    }
    if not isinstance(man, Mapping) or man.get("verdict") != ANSWER:
        return _refuse(NO_MANNEQUIN, "有効な人台がありません",
                       "verdict=ANSWERで高さ範囲を持つ人台を渡してください",
                       provenance, upstream_verdict=(man.get("verdict")
                                                     if isinstance(man, Mapping) else None))
    kind = _KINDS.get(str(garment).lower())
    if kind is None:
        return _refuse(BAD_GARMENT, f"未対応のsecond-skin種別: {garment}",
                       "dress, skirt, trousers, leggingsのいずれかを指定してください",
                       provenance)
    if (not isinstance(segments, int) or isinstance(segments, bool) or segments < 3
            or not isinstance(height_steps, int) or isinstance(height_steps, bool)
            or height_steps < 1):
        return _refuse(BAD_RESOLUTION, "閉じた面を作れない解像度です",
                       "segmentsを3以上、height_stepsを1以上にしてください",
                       provenance, segments=segments, height_steps=height_steps)
    levels = man.get("_levels")
    if (not isinstance(levels, Sequence) or len(levels) < 2
            or any(not isinstance(level, Sequence) or len(level) < 1
                   or _finite(level[0]) is None for level in levels)):
        return _refuse(NO_GEOMETRY, "人台の高さ範囲がありません",
                       "_levelsまたは明示的な幾何範囲を持つ人台を渡してください",
                       provenance)
    body_lo, body_hi = float(levels[0][0]), float(levels[-1][0])
    lo = body_lo if y_bottom is None else float(y_bottom)
    hi = body_hi if y_top is None else float(y_top)
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return _refuse(BAD_RANGE, "高さ範囲が空または不正です",
                       "y_bottom < y_topとなる有限なcm値を渡してください",
                       provenance, requested=[lo, hi])
    rf = radius_at
    if rf is None:
        try:
            from . import mannequin as _mannequin
            rf = _mannequin.radius_at
        except ImportError:
            return _refuse(NO_GEOMETRY, "radius_atを解決できません",
                           "人台断面を返すradius_at callableを渡してください", provenance)
    ease_spec = ease if ease_field is None else ease_field
    stretch_spec = stretch if stretch_field is None else stretch_field
    ring_ys = [lo + (hi - lo) * index / height_steps
               for index in range(height_steps + 1)]
    field_samples: List[Tuple[float, float, float]] = []
    for y in ring_ys:
        e, s = _field_at(ease_spec, y), _field_at(stretch_spec, y)
        if e is None or s is None or e < 0.0 or s <= -1.0:
            return _refuse(
                BAD_FIELD, f"高さ{y:.4f}cmのease/stretchが不正です",
                "easeは0以上、stretchは-1より大きい有限値にしてください",
                provenance, height_cm=round(y, 6), ease=e, stretch=s)
        field_samples.append((y, e, s))
    provenance["fields"] = {"ease_cm": _field_source(ease_spec),
                             "stretch_strain": _field_source(stretch_spec)}

    selected = [value for value in (calibrated_views, views, overlays)
                if value is not None]
    if len(selected) > 1:
        return _refuse(BAD_VIEW, "viewの別名が複数同時に指定されました",
                       "calibrated_views, views, overlaysのどれか1つだけを使ってください",
                       provenance)
    raw_views = list(selected[0]) if selected else []
    parsed_views: Optional[List[Dict[str, Any]]] = None
    if raw_views:
        parsed_views, refusal = _parse_views(raw_views)
        if refusal is not None:
            return refusal
        provenance["views"] = [dict(record, kind="OBSERVED") for record in
                               refusal.get("provenance", {}).get("views", [])] if refusal else [
            {"frame_id": view["frame_id"], "source": view["source"],
             "azimuth_deg": view["angle"], "kind": "OBSERVED"}
            for view in parsed_views or []]

    constraints: Dict[float, Tuple[float, float, float, float]] = {}
    if parsed_views:
        for y in ring_ys:
            spans = [_span_at(view["polygons"], y) for view in parsed_views]
            if all(span is not None for span in spans):
                solved = _solve_projection(
                    [view["angle"] for view in parsed_views],
                    [float(span) / 2.0 for span in spans if span is not None])
                if solved is not None:
                    constraints[y] = solved
        if not constraints:
            return _refuse(
                NO_COMMON_CONSTRAINT,
                "全ビューが同じ高さで服を拘束する領域がありません",
                "較正ビューの縦座標を揃え、重なる高さにprimitiveを置いてください",
                provenance)

    verts: List[Vec3] = []
    rest_verts: List[Vec3] = []
    faces: List[Face] = []
    rings: List[Dict[str, Any]] = []
    components = 2 if kind == "trousers" else 1
    for component in range(components):
        base_index = len(verts)
        for ring_index, (y, e, s) in enumerate(field_samples):
            body_a = rf(man, y, 0.0)
            body_b = rf(man, y, math.pi / 2.0)
            if body_a is None or body_b is None:
                return _refuse(
                    NO_GEOMETRY, f"高さ{y:.4f}cmに人台断面がありません",
                    "要求範囲全域で正の半径を返すradius_atを渡すか、高さ範囲を縮めてください",
                    provenance, height_cm=round(y, 6))
            body_a, body_b = float(body_a), float(body_b)
            if body_a <= 0.0 or body_b <= 0.0:
                return _refuse(NO_GEOMETRY, "人台半径が正ではありません",
                               "全方向で正の有限半径を返してください", provenance,
                               height_cm=round(y, 6))
            target_a, target_b = body_a + e, body_b + e
            constraint = constraints.get(y)
            if constraint is not None:
                target_a, target_b = constraint[0], constraint[1]
                if target_a + 1e-9 < body_a + e or target_b + 1e-9 < body_b + e:
                    return _refuse(
                        INSIDE_FORM,
                        f"高さ{y:.4f}cmの観測シェルが人台+easeの内側です",
                        "較正、画像座標、または人台寸法を確認してください",
                        provenance, height_cm=round(y, 6),
                        observed_axes_cm=[target_a, target_b],
                        minimum_axes_cm=[body_a + e, body_b + e])
            if kind == "trousers":
                local_a, local_b = target_a * leg_radius_ratio, target_b * leg_radius_ratio
                center_x = (-1.0 if component == 0 else 1.0) * target_a * leg_center_ratio
            else:
                local_a, local_b, center_x = target_a, target_b, 0.0
            for index in range(segments):
                theta = 2.0 * math.pi * index / segments
                worn_radius = _ellipse_radius(local_a, local_b, theta)
                rest_radius = worn_radius / (1.0 + s)
                verts.append((center_x + worn_radius * math.cos(theta), y,
                              worn_radius * math.sin(theta)))
                rest_center = center_x / (1.0 + s) if kind == "trousers" else center_x
                rest_verts.append((rest_center + rest_radius * math.cos(theta), y,
                                   rest_radius * math.sin(theta)))
            if component == 0:
                rings.append({
                    "height_cm": round(y, 6), "ease_cm": round(e, 6),
                    "stretch_strain": round(s, 6),
                    "worn_width_radius_cm": round(target_a, 6),
                    "worn_depth_radius_cm": round(target_b, 6),
                    "rest_scale": round(1.0 / (1.0 + s), 8),
                    "constraint": "MULTI_VIEW_OBSERVED" if constraint else "MANNEQUIN_DERIVED",
                })
        for ring_index in range(height_steps):
            lower = base_index + ring_index * segments
            upper = lower + segments
            for index in range(segments):
                nxt = (index + 1) % segments
                faces.append((lower + index, lower + nxt,
                              upper + nxt, upper + index))

    before_sq = sum(value[2] ** 2 for value in constraints.values())
    after_sq = sum(value[3] ** 2 for value in constraints.values())
    constraint_report = {
        "view_count": len(parsed_views or []),
        "independent_axes": 2 if parsed_views else 0,
        "constrained_ring_count": len(constraints),
        "unconstrained_ring_count": len(ring_ys) - len(constraints),
        "projection_rmse_before_cm": (round(math.sqrt(before_sq / len(constraints)), 8)
                                       if constraints else None),
        "projection_rmse_after_cm": (round(math.sqrt(after_sq / len(constraints)), 8)
                                      if constraints else None),
        "improved": bool(constraints and after_sq <= before_sq + 1e-12),
    }
    provenance["output"] = "GENERATED"
    provenance["assumptions"] = [
        "worn surface follows mannequin radius plus non-negative ease",
        "stretch is uniform around each ring at a given height",
        "projection-constrained sections are axis-aligned ellipses",
    ]
    if kind == "trousers":
        provenance["assumptions"].append(
            "two leg centers/radii are deterministic ratios, not observed anatomy")
    return {
        "verdict": ANSWER,
        "what": "model-free second-skin geometric scaffold",
        "garment": kind, "shell_count": components,
        "components": (["left_leg", "right_leg"] if kind == "trousers"
                       else [kind]),
        "verts": verts, "rest_verts": rest_verts, "faces": faces,
        "vertices": len(verts), "faces_count": len(faces),
        "segments": segments, "height_steps": height_steps,
        "y_range_used": [round(lo, 6), round(hi, 6)],
        "rings": rings, "constraints": constraint_report,
        "provenance": provenance,
        "not_sewing_pattern": (
            "これは密着幾何の土台です。縫い代、縫い順、素材物理、"
            "ズボン股上の接合はまだ決めていません"),
    }


build_second_skin = build
generate = build
