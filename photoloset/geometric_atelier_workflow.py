#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geometry-first image-to-garment orchestration.

The module deliberately does not classify garment names into generators.  It
compiles typed front regions, layer/side/component relations and a bounded body
avatar into a smooth second-skin mesh.  Rear alternatives remain PROPOSED and
are compared in the same front camera before any pattern hand-off is opened.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import body_avatar_fit
from . import candidate_3d_repair_loop
from . import rear_candidate_ensemble
from . import second_skin_triangle_engine


REQUEST_SCHEMA = "garment.geometric-atelier-workflow.request.v1"
SCHEMA = "garment.geometric-atelier-workflow.v1"
PROPOSED = "PROPOSED"
UNKNOWN = "UNKNOWN"
ANSWER = "ANSWER"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _finite(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    result = float(value)
    return result if math.isfinite(result) else default


def _refusal(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": code,
        "state": UNKNOWN,
        "phase": code,
        "why": why,
        "detail": detail,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["digest"] = stable_digest(result)
    return result


def _part_id(part: Mapping[str, Any], index: int) -> str:
    for key in ("part_id", "node_id", "mask_id", "id"):
        value = part.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "visible-part-%03d" % index


def _garment_unit(part: Mapping[str, Any], part_id: str) -> str:
    for key in ("garment_unit", "garment_unit_id", "unit_id"):
        value = part.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return part_id


def _side(part: Mapping[str, Any]) -> str:
    value = str(part.get("side", part.get("attachment_side", "CENTER"))).upper()
    if "LEFT" in value:
        return "LEFT"
    if "RIGHT" in value:
        return "RIGHT"
    if value in {"BILATERAL", "PAIR", "PAIRED"}:
        return "BILATERAL"
    return "CENTER"


def _source_dimensions(fit: Mapping[str, Any]) -> Tuple[float, float]:
    source = fit.get("source") if isinstance(fit.get("source"), Mapping) else {}
    width = _finite(source.get("width_px", source.get("width")), 0.0)
    height = _finite(source.get("height_px", source.get("height")), 0.0)
    if width <= 0.0 or height <= 0.0:
        raise ValueError("body avatar fit did not preserve source dimensions")
    return width, height


def _normalise_outline(
    raw: Any, *, width: float, height: float, coordinate_space: str = "",
) -> List[List[float]]:
    if not _sequence(raw) or len(raw) < 3:
        return []
    points: List[List[float]] = []
    for item in raw:
        if not _sequence(item) or len(item) < 2:
            return []
        x, y = _finite(item[0], math.nan), _finite(item[1], math.nan)
        if not math.isfinite(x) or not math.isfinite(y):
            return []
        points.append([x, y])
    token = coordinate_space.upper()
    normalized = "NORMAL" in token or (
        token not in {"PIXEL", "PIXELS", "IMAGE_PIXELS"}
        and max(max(abs(p[0]), abs(p[1])) for p in points) <= 1.5
    )
    if normalized:
        return [[round(p[0] * width, 8), round(p[1] * height, 8)]
                for p in points]
    return [[round(p[0], 8), round(p[1], 8)] for p in points]


def _graph_and_parts(
    request: Mapping[str, Any], fit: Mapping[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    raw_graph = request.get("visible_part_graph")
    graph = copy.deepcopy(dict(raw_graph)) if isinstance(raw_graph, Mapping) else {}
    raw_parts = graph.get("parts", request.get("visible_parts", []))
    if not _sequence(raw_parts):
        raw_parts = []
    width, height = _source_dimensions(fit)
    targets = fit.get("garment_projection_targets", [])
    targets = targets if _sequence(targets) else []
    by_mask = {str(row.get("mask_id")): row for row in targets
               if isinstance(row, Mapping) and row.get("mask_id")}
    by_unit: Dict[str, Mapping[str, Any]] = {}
    for row in targets:
        if isinstance(row, Mapping) and row.get("garment_unit_id"):
            by_unit.setdefault(str(row["garment_unit_id"]), row)

    # A VLM can produce a useful typed part/layer ledger before the image
    # segmenter has split the single audited garment silhouette into matching
    # masks. Reusing that one silhouette for every semantic part is only a
    # proposal-level visual scaffold; it is not part segmentation. Keeping
    # this explicit lets the app render candidate-specific geometry instead of
    # falling back to a generic cape while preserving the human audit gate.
    aggregate_target: Optional[Mapping[str, Any]] = None
    if targets:
        def target_area(candidate: Any) -> float:
            if not isinstance(candidate, Mapping):
                return -1.0
            outline = candidate.get("outline", [])
            if not _sequence(outline) or len(outline) < 3:
                return -1.0
            xs = [_finite(point[0], 0.0) for point in outline
                  if _sequence(point) and len(point) >= 2]
            ys = [_finite(point[1], 0.0) for point in outline
                  if _sequence(point) and len(point) >= 2]
            if len(xs) < 3 or len(ys) < 3:
                return -1.0
            return (max(xs) - min(xs)) * (max(ys) - min(ys))

        candidate = max(targets, key=target_area)
        if isinstance(candidate, Mapping) and target_area(candidate) >= 0.0:
            aggregate_target = candidate

    if not raw_parts:
        raw_parts = [{
            "part_id": str(row.get("mask_id", "front-region-%03d" % index)),
            "garment_unit": str(row.get(
                "garment_unit_id", row.get("mask_id", "unit-%03d" % index))),
            "layer": int(row.get("layer", 0) or 0),
            "outline_px": copy.deepcopy(row.get("outline", [])),
            "kind": "VISIBLE_REGION",
        } for index, row in enumerate(targets) if isinstance(row, Mapping)]

    parts: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(raw_parts):
        if not isinstance(raw, Mapping):
            continue
        row = copy.deepcopy(dict(raw))
        part_id = _part_id(row, index)
        if part_id in seen:
            raise ValueError("visible part ids must be unique")
        seen.add(part_id)
        unit = _garment_unit(row, part_id)
        target = by_mask.get(str(row.get("mask_id", part_id))) or by_unit.get(unit)
        raw_outline = row.get("outline_px", row.get(
            "outline", row.get("points", row.get("polygon"))))
        outline_binding = "PART_SPECIFIC_FRONT_REGION"
        if (not _sequence(raw_outline) or len(raw_outline) < 3) and target:
            raw_outline = target.get("outline", [])
            outline_binding = "MATCHED_TYPED_FRONT_MASK"
        if ((not _sequence(raw_outline) or len(raw_outline) < 3)
                and aggregate_target is not None):
            raw_outline = aggregate_target.get("outline", [])
            outline_binding = "SHARED_AGGREGATE_FRONT_MASK_PROPOSAL"
        outline = _normalise_outline(
            raw_outline, width=width, height=height,
            coordinate_space=str(row.get("coordinate_space", "")),
        )
        layer_raw = row.get("layer", target.get("layer", 0) if target else 0)
        layer = int(layer_raw) if isinstance(layer_raw, int) and not isinstance(
            layer_raw, bool) else 0
        parts.append({
            **row,
            "part_id": part_id,
            "garment_unit": unit,
            "layer": max(layer, 0),
            "side": _side(row),
            "outline_px": outline,
            "outline_binding": outline_binding,
            "part_boundary_observed": (
                outline_binding != "SHARED_AGGREGATE_FRONT_MASK_PROPOSAL"),
            "kind": str(row.get("kind", "UNKNOWN_VISIBLE_SURFACE")),
        })
    if not parts:
        raise ValueError("at least one typed visible garment region is required")
    parts.sort(key=lambda row: (int(row["layer"]), str(row["garment_unit"]),
                                str(row["part_id"])))
    graph["graph_id"] = str(graph.get("graph_id", "front:" + stable_digest(parts)[:16]))
    graph["parts"] = copy.deepcopy(parts)
    graph.setdefault("relations", [])
    return graph, parts


def _body_proxy(avatar: Mapping[str, Any]) -> Dict[str, Any]:
    dimensions = avatar.get("dimensions_cm")
    if not isinstance(dimensions, Mapping):
        raise ValueError("selected avatar dimensions are unavailable")
    height = _finite(dimensions.get("height"), 0.0)
    chest = _finite(dimensions.get("chest_bust"), 0.0)
    waist = _finite(dimensions.get("waist"), 0.0)
    hip = _finite(dimensions.get("hip"), 0.0)
    if min(height, chest, waist, hip) <= 0.0:
        raise ValueError("selected avatar needs height/chest_bust/waist/hip")

    def axes(circumference: float) -> Tuple[float, float]:
        mean = circumference / (2.0 * math.pi)
        return round(mean * 1.12, 8), round(mean * 0.88, 8)

    hip_x, hip_z = axes(hip)
    waist_x, waist_z = axes(waist)
    chest_x, chest_z = axes(chest)
    sections = [
        [0.0, max(2.8, hip_x * 0.22), max(2.2, hip_z * 0.22)],
        [height * 0.08, max(4.5, hip_x * 0.38), max(3.2, hip_z * 0.38)],
        [height * 0.30, max(5.8, hip_x * 0.55), max(4.0, hip_z * 0.55)],
        [height * 0.53, hip_x, hip_z],
        [height * 0.65, waist_x, waist_z],
        [height * 0.79, chest_x, chest_z],
        [height * 0.87, chest_x * 1.04, chest_z * 0.86],
        [height, max(3.8, chest_x * 0.34), max(3.2, chest_z * 0.34)],
    ]
    return {
        "verdict": ANSWER,
        "_levels": [[round(value, 8) for value in row] for row in sections],
        "avatar_id": avatar.get("avatar_id"),
        "geometry_digest": avatar.get("geometry_digest"),
        "state": PROPOSED,
        "not_measured_from_pixels": True,
    }


def _axes_at(body: Mapping[str, Any], y: float) -> Tuple[float, float]:
    levels = body["_levels"]
    if y <= levels[0][0]:
        return float(levels[0][1]), float(levels[0][2])
    if y >= levels[-1][0]:
        return float(levels[-1][1]), float(levels[-1][2])
    for left, right in zip(levels, levels[1:]):
        if left[0] <= y <= right[0]:
            ratio = (y - left[0]) / (right[0] - left[0])
            return (
                float(left[1]) + (float(right[1]) - float(left[1])) * ratio,
                float(left[2]) + (float(right[2]) - float(left[2])) * ratio,
            )
    raise ValueError("body section interpolation failed")


def _world_outline(
    part: Mapping[str, Any], fit: Mapping[str, Any], height: float,
) -> List[List[float]]:
    transform = fit["image_relative_fit"]["world_to_image"]
    scale = _finite(transform.get("uniform_scale_px_per_preview_cm"), 0.0)
    translation = transform.get("translation_px_for_avatar_origin")
    if scale <= 0.0 or not _sequence(translation) or len(translation) < 2:
        raise ValueError("body fit lacks an invertible image transform")
    points = part.get("outline_px", [])
    result = [[
        round((float(point[0]) - float(translation[0])) / scale, 8),
        round(max(0.0, min(height,
                          (float(translation[1]) - float(point[1])) / scale)), 8),
    ] for point in points]
    return result


def _bounded_range(values: Iterable[float], height: float) -> List[float]:
    rows = [max(0.0, min(height, float(value))) for value in values]
    if not rows:
        return [round(height * 0.22, 8), round(height * 0.82, 8)]
    lo, hi = min(rows), max(rows)
    minimum_span = max(2.0, height * 0.025)
    if hi - lo < minimum_span:
        center = (lo + hi) * 0.5
        lo = max(0.0, center - minimum_span * 0.5)
        hi = min(height, lo + minimum_span)
        lo = max(0.0, hi - minimum_span)
    return [round(lo, 8), round(hi, 8)]


def _declared_component_count(part: Mapping[str, Any]) -> Optional[int]:
    """Read topology, never a garment name, from the visible-part ledger."""
    topology = part.get("topology")
    sources = [part]
    if isinstance(topology, Mapping):
        sources.insert(0, topology)
    for source in sources:
        for key in (
            "independent_component_count", "radial_component_count",
            "component_count",
        ):
            value = source.get(key)
            if (isinstance(value, int) and not isinstance(value, bool)
                    and 1 <= value <= 4):
                return value
        domains = source.get("independent_domains", source.get("side_domains"))
        if _sequence(domains) and 1 <= len(domains) <= 4:
            return len(domains)
    return None


def _outline_component_count(
    world_outline: Sequence[Sequence[float]],
) -> Tuple[int, str]:
    """Detect lower split domains without confusing them with an upper cutout.

    Two interior intervals near the lower edge that merge into one interval
    near the upper edge describe two lower tubes joined by an upper bridge.
    The inverse shape (one lower interval, two upper intervals) stays one
    shell, so a neckline-like cutout is not mistaken for two components.  No
    colour, filename, garment label, resolution or absolute pixel threshold
    participates in this decision.
    """
    if len(world_outline) < 6:
        return 1, "CONTINUOUS_FRONT_BOUNDARY"
    xs = [float(point[0]) for point in world_outline]
    ys = [float(point[1]) for point in world_outline]
    left, right = min(xs), max(xs)
    lower, upper = min(ys), max(ys)
    width, span = right - left, upper - lower
    if width <= 0.0 or span <= 0.0:
        return 1, "DEGENERATE_FRONT_BOUNDARY"
    epsilon = max(width, span) * 1.0e-12

    def intervals(y: float) -> List[Tuple[float, float]]:
        intersections: List[float] = []
        polygon = [(float(point[0]), float(point[1]))
                   for point in world_outline]
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            if abs(b[1] - a[1]) <= epsilon:
                continue
            edge_lower, edge_upper = min(a[1], b[1]), max(a[1], b[1])
            if y < edge_lower or y >= edge_upper:
                continue
            ratio = (y - a[1]) / (b[1] - a[1])
            intersections.append(a[0] + ratio * (b[0] - a[0]))
        intersections.sort()
        if len(intersections) % 2:
            return []
        return [
            (intersections[index], intersections[index + 1])
            for index in range(0, len(intersections), 2)
            if intersections[index + 1] - intersections[index] > epsilon
        ]

    lower_intervals = intervals(lower + span * 0.08)
    upper_intervals = intervals(upper - span * 0.08)
    if len(lower_intervals) == 2 and len(upper_intervals) == 1:
        return 2, "SCALE_FREE_CENTRE_NOTCH_TWO_DOMAINS"
    return 1, "CONTINUOUS_FRONT_BOUNDARY"


def _component_plan(
    part: Mapping[str, Any], *, unit_size: int, layer: int,
    world_outline: Sequence[Sequence[float]],
) -> Tuple[List[Dict[str, Any]], str]:
    side = str(part["side"])
    declared = _declared_component_count(part)
    geometric_count, geometric_basis = _outline_component_count(world_outline)
    count = declared if declared is not None else geometric_count
    basis = ("TYPED_LEDGER_COMPONENT_COUNT" if declared is not None
             else geometric_basis)
    if count == 1 and side == "BILATERAL":
        count = 2
        basis = "TYPED_BILATERAL_DOMAIN"
    paired_side = unit_size >= 2 and side in {"LEFT", "RIGHT"}
    if count > 1 or paired_side:
        if count > 1:
            if count == 2:
                centers = [-0.48, 0.48]
                radius_x = 0.48
            else:
                centers = [-1.0 + (2.0 * index + 1.0) / count
                           for index in range(count)]
                radius_x = 1.0 / count
        else:
            centers = [-0.48] if side == "LEFT" else [0.48]
            radius_x = 0.48
        return [{
            "component_id": "%s/component-%d" % (part["part_id"], index),
            "center_ratio": [round(center, 8), 0.0],
            "radius_ratio": [round(radius_x, 8), 0.62],
        } for index, center in enumerate(centers)], basis
    component: Dict[str, Any] = {
        "component_id": "%s/component-0" % part["part_id"],
        "center_ratio": [0.0, 0.0],
        "radius_ratio": [1.0, 1.0],
    }
    # Geometry is selected from layer/side support, never from a garment name.
    if layer > 0 or side in {"LEFT", "RIGHT"}:
        component["angular_coverage_deg"] = (
            [90.0, 180.0] if side == "LEFT" else
            [0.0, 90.0] if side == "RIGHT" else [0.0, 180.0]
        )
    return [component], basis


def _typed_relation_rows(
    request: Mapping[str, Any], parts: Sequence[Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    graph = request.get("visible_part_graph")
    raw_rows = list(graph.get("relations", [])) if (
        isinstance(graph, Mapping) and _sequence(graph.get("relations", []))) else []
    for part in parts:
        owner = part.get("owner_id", part.get("owner_part_id"))
        if isinstance(owner, str) and owner:
            raw_rows.append({
                "parent_id": owner,
                "child_id": part["part_id"],
                "kind": part.get("relation_kind"),
                "attachment_port": part.get("attachment_port"),
                "attachment_side": part.get("attachment_side", part.get("side")),
                "relation_id": part.get("relation_id"),
                "source_state": part.get("ownership_state", PROPOSED),
            })
    result: List[Dict[str, Any]] = []
    children = set()
    relation_ids = set()
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            raise ValueError("visible relation %d must be a mapping" % index)
        parent = raw.get("parent_id", raw.get("owner_id"))
        child = raw.get("child_id", raw.get("owned_id"))
        if parent not in records or child not in records or parent == child:
            raise ValueError("visible relation references an unknown/cyclic part")
        if child in children:
            raise ValueError("a visible part cannot have multiple owners")
        parent_layer = int(records[str(parent)]["layer"])
        child_layer = int(records[str(child)]["layer"])
        default_kind = "LAYER" if child_layer > parent_layer else "JOIN"
        kind = str(raw.get("kind") or default_kind).upper()
        if kind not in {"JOIN", "LAYER", "ATTACH"}:
            raise ValueError("visible relation kind must be JOIN/LAYER/ATTACH")
        row = _relation(str(parent), str(child), kind, records[str(child)])
        relation_id = raw.get("relation_id") or row["relation_id"]
        if not isinstance(relation_id, str) or not relation_id or relation_id in relation_ids:
            raise ValueError("visible relation ids must be unique")
        port = raw.get("attachment_port") or row["attachment_port"]
        if not isinstance(port, str) or not port:
            raise ValueError("visible relation attachment_port must be explicit")
        side = str(raw.get("attachment_side") or row["attachment_side"]).upper()
        if side not in {"LEFT", "RIGHT", "CENTER", "BILATERAL", "FULL"}:
            side = "CENTER"
        row.update({
            "relation_id": relation_id,
            "attachment_port": port,
            "attachment_side": side,
            "source_relation_state": str(raw.get(
                "source_state", raw.get("state", PROPOSED))),
            "ledger_relation_preserved": True,
        })
        result.append(row)
        children.add(str(child))
        relation_ids.add(relation_id)
    result.sort(key=lambda row: row["relation_id"])
    return result


def _surface_plan(
    request: Mapping[str, Any], parts: Sequence[Mapping[str, Any]],
    fit: Mapping[str, Any], body: Mapping[str, Any],
) -> Dict[str, Any]:
    explicit = request.get("surface_plan")
    if isinstance(explicit, Mapping):
        result = copy.deepcopy(dict(explicit))
        result["source"] = "EXPLICIT_TYPED_SURFACE_PLAN"
        result["name_based_branching"] = False
        return result
    height = float(body["_levels"][-1][0])
    units: Dict[Tuple[str, int], int] = {}
    for part in parts:
        key = str(part["garment_unit"]), int(part["layer"])
        units[key] = units.get(key, 0) + 1
    surfaces: List[Dict[str, Any]] = []
    cues: List[Dict[str, Any]] = []
    records: Dict[str, Dict[str, Any]] = {}
    for part in parts:
        world = _world_outline(part, fit, height)
        y_range = _bounded_range((point[1] for point in world), height)
        mid_y = (y_range[0] + y_range[1]) * 0.5
        body_x, _ = _axes_at(body, mid_y)
        desired_half = ((max(point[0] for point in world)
                         - min(point[0] for point in world)) * 0.5
                        if world else body_x)
        ease = max(0.0, min(15.0, desired_half - body_x))
        surface_id = str(part["part_id"])
        components, component_basis = _component_plan(
            part, unit_size=units[(str(part["garment_unit"]), int(part["layer"]))],
            layer=int(part["layer"]),
            world_outline=world,
        )
        surface = {
            "surface_id": surface_id,
            "y_range_cm": y_range,
            "layer": int(part["layer"]),
            "ease_cm": round(ease, 8),
            "material_id": "unmeasured:%s" % part["garment_unit"],
            "components": components,
            "component_basis": component_basis,
        }
        surfaces.append(surface)
        area = ((max(p[0] for p in world) - min(p[0] for p in world))
                * (max(p[1] for p in world) - min(p[1] for p in world))) if world else 0.0
        records[surface_id] = {
            "unit": str(part["garment_unit"]), "layer": int(part["layer"]),
            "side": str(part["side"]), "area": area,
            "y_range": y_range,
            "component_basis": component_basis,
        }
        if len(world) >= 3:
            cues.append({
                "cue_id": "front:%s" % surface_id,
                "surface_id": surface_id,
                "kind": "POLYGON",
                "points_cm": world,
                "coordinate_space": "BODY_CM_FRONT",
                "state": PROPOSED,
                "offset_cm": round(max(0.15, ease), 8),
                "weight": 1.0,
            })

    surfaces.sort(key=lambda row: (int(row["layer"]), str(row["surface_id"])))
    relations = _typed_relation_rows(request, parts, records)
    owned = {str(row["child_id"]) for row in relations}
    grouped: Dict[Tuple[str, int], List[str]] = {}
    for surface_id, record in records.items():
        grouped.setdefault((record["unit"], record["layer"]), []).append(surface_id)

    roots: Dict[Tuple[str, int], str] = {}
    for key, surface_ids in sorted(grouped.items()):
        ordered = sorted(surface_ids, key=lambda item: (-records[item]["area"], item))
        roots[key] = ordered[0]
        for child in ordered[1:]:
            if child in owned:
                continue
            relations.append(_relation(ordered[0], child, "JOIN", records[child]))
            owned.add(child)

    for key, root in sorted(roots.items(), key=lambda item: (item[0][1], item[0][0])):
        unit, layer = key
        if layer <= 0 or root in owned:
            continue
        lower = [candidate for candidate, record in records.items()
                 if record["layer"] < layer]
        if not lower:
            raise ValueError("outer layer %s has no lower owner candidate" % root)

        def owner_score(candidate: str) -> Tuple[float, int, str]:
            a, b = records[candidate]["y_range"], records[root]["y_range"]
            overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
            same_unit = int(records[candidate]["unit"] == unit)
            return overlap, same_unit, candidate

        parent = max(lower, key=owner_score)
        relations.append(_relation(parent, root, "LAYER", records[root]))
        owned.add(root)

    return {
        "source": "VISIBLE_GEOMETRY_AND_TYPED_RELATIONS_ONLY",
        "surfaces": surfaces,
        "relations": sorted(relations, key=lambda row: row["relation_id"]),
        "front_cues": sorted(cues, key=lambda row: row["cue_id"]),
        "name_based_branching": False,
        "garment_names_consumed_for_geometry": False,
        "unresolved_component_count_is_not_inferred_from_name": True,
    }


def _relation(
    parent: str, child: str, kind: str, child_record: Mapping[str, Any],
) -> Dict[str, Any]:
    side = str(child_record.get("side", "CENTER"))
    return {
        "relation_id": "%s:%s->%s" % (kind.lower(), parent, child),
        "kind": kind,
        "state": PROPOSED,
        "parent_id": parent,
        "child_id": child,
        "attachment_port": "overlap-boundary:%s:%s" % (parent, child),
        "attachment_side": side if side in {
            "LEFT", "RIGHT", "CENTER", "BILATERAL", "FULL"} else "CENTER",
        "ownership": {"owner_id": parent, "state": PROPOSED},
        "layer": int(child_record["layer"]),
    }


def _raster_polygon(
    polygon: Sequence[Sequence[float]], rows: int, columns: int,
) -> List[List[int]]:
    mask = [[0 for _ in range(columns)] for _ in range(rows)]
    if len(polygon) < 3:
        return mask
    for row in range(rows):
        y = row + 0.5
        for column in range(columns):
            x = column + 0.5
            inside = False
            previous = polygon[-1]
            for current in polygon:
                x1, y1 = float(previous[0]), float(previous[1])
                x2, y2 = float(current[0]), float(current[1])
                if (y1 > y) != (y2 > y):
                    crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                    if x < crossing:
                        inside = not inside
                previous = current
            if inside:
                mask[row][column] = 1
    return mask


def _target_front(
    parts: Sequence[Mapping[str, Any]], fit: Mapping[str, Any], *, confirmed: bool,
    human_edit_digest: Optional[str] = None, size: int = 64,
) -> Dict[str, Any]:
    width, height = _source_dimensions(fit)
    part_masks: Dict[str, Any] = {}
    silhouette = [[0 for _ in range(size)] for _ in range(size)]
    projection_ready = bool(fit.get("front_projection_ready"))
    reference_authority = (
        "HUMAN_CONFIRMED_TARGET" if confirmed else
        "OBSERVED" if projection_ready else PROPOSED
    )
    part_state = ("OBSERVED" if reference_authority in {
        "OBSERVED", "HUMAN_CONFIRMED_TARGET"} else PROPOSED)
    for part in parts:
        polygon = [[point[0] / width * size, point[1] / height * size]
                   for point in part.get("outline_px", [])]
        mask = _raster_polygon(polygon, size, size)
        if not any(any(row) for row in mask):
            continue
        for row in range(size):
            for column in range(size):
                silhouette[row][column] = max(silhouette[row][column],
                                               mask[row][column])
        part_masks[str(part["part_id"])] = {
            "mask": mask, "state": part_state, "visibility": "FRONT",
            "layer": int(part["layer"]),
        }
    if not any(any(row) for row in silhouette):
        raise ValueError("visible front polygons produced an empty comparison target")
    contract = fit.get("front_projection_contract")
    camera_digest = (contract.get("camera_digest") if isinstance(contract, Mapping)
                     else None) or stable_digest({"source": fit.get("source")})
    result = {
        "camera_digest": str(camera_digest),
        "reference_authority": reference_authority,
        "silhouette_mask": {
            "mask": silhouette,
            "state": ("HUMAN_CONFIRMED_TARGET" if confirmed else part_state),
        },
        "typed_part_masks": part_masks,
        "occlusion_unknown_mask": [[0 for _ in range(size)] for _ in range(size)],
        "rear_state": "UNKNOWN_UNOBSERVED",
        "material_state": "UNKNOWN_UNOBSERVED",
    }
    if reference_authority == "HUMAN_CONFIRMED_TARGET":
        contract_target = (contract.get("target")
                           if isinstance(contract, Mapping) else None)
        human_digest = human_edit_digest or (
            contract_target.get("human_edit_digest")
            if isinstance(contract_target, Mapping) else None)
        if isinstance(human_digest, str) and human_digest:
            result["human_edit_digest"] = human_digest
    return result


def _preview_only_repair(
    candidates: Sequence[Mapping[str, Any]], target: Mapping[str, Any],
) -> Dict[str, Any]:
    rows = []
    for candidate in candidates:
        built = candidate_3d_repair_loop.build_candidate_geometry(candidate)
        rows.append({
            "candidate_id": candidate.get("candidate_id"),
            "verdict": "PROPOSED_CANDIDATE_PREVIEW_ONLY",
            "state": PROPOSED,
            "candidate_geometry": built.get("geometry"),
            "why": "front segmentation is proposed; same-camera scoring awaits observation or human confirmation",
            "pattern_handoff": None,
            "authority": {"front": PROPOSED, "rear": PROPOSED,
                          "material": "UNKNOWN"},
            "fact_promotions": [],
        })
    result: Dict[str, Any] = {
        "schema": candidate_3d_repair_loop.SCHEMA,
        "verdict": "PROPOSED_FRONT_AUDIT_REQUIRED_FOR_COMPARISON",
        "state": PROPOSED,
        "candidate_count": len(rows),
        "candidates": rows,
        "pattern_handoffs": [],
        "human_choice": {
            "required": True,
            "candidate_ids": [row["candidate_id"] for row in rows],
            "selected_candidate_id": None,
        },
        "authority": {"front": PROPOSED, "rear": PROPOSED,
                      "material": "UNKNOWN"},
        "fact_promotions": [],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "target_digest": stable_digest(target),
    }
    result["digest"] = stable_digest(result)
    return result


def _rear_variant_mesh(
    second_skin: Mapping[str, Any], rear_candidate: Mapping[str, Any], index: int,
) -> Dict[str, Any]:
    mesh = second_skin["mesh"]
    vertices = copy.deepcopy(mesh["vertices_cm"])
    states = second_skin["vertex_states"]
    strategy = str(rear_candidate.get("strategy", "GEOMETRY_REAR"))
    seed = int(stable_digest(strategy)[:8], 16)
    magnitude = 0.25 + index * 0.17 + (seed % 11) * 0.015
    for vertex, state in zip(vertices, states):
        if bool(state.get("front_hemisphere")):
            continue
        depth = abs(float(vertex[2]))
        vertex[2] = round(float(vertex[2]) - magnitude * (0.35 + depth * 0.03), 12)
        if "SPLIT" in strategy or "CENTER" in strategy:
            sign = -1.0 if float(vertex[0]) < 0.0 else 1.0
            vertex[0] = round(float(vertex[0]) + sign * magnitude * 0.12, 12)
        elif "SIDE" in strategy:
            vertex[0] = round(float(vertex[0]) + magnitude * 0.10, 12)
        else:
            vertex[2] = round(float(vertex[2]) - magnitude * 0.06, 12)
    layers = {row["surface_id"]: int(row["layer"])
              for row in second_skin["topology"]["surfaces"]}
    face_ids = list(mesh["triangle_surface_ids"])
    return {
        "units": "cm",
        "vertices": vertices,
        "faces": copy.deepcopy(mesh["triangles"]),
        "face_node_ids": face_ids,
        "face_layers": [layers.get(part_id, 0) for part_id in face_ids],
        "vertex_layers": [int(row.get("layer", 0)) for row in states],
        "geometry_source": "SECOND_SKIN_PLUS_CANDIDATE_REAR_PROPOSAL",
        "generic_cape_fallback": False,
    }


def _polyline_length(
    vertices: Sequence[Sequence[float]], vertex_ids: Sequence[int], *, closed: bool,
) -> float:
    if len(vertex_ids) < 2:
        return 0.0
    pairs = list(zip(vertex_ids, vertex_ids[1:]))
    if closed:
        pairs.append((vertex_ids[-1], vertex_ids[0]))
    return math.fsum(math.sqrt(math.fsum(
        (float(vertices[left][axis]) - float(vertices[right][axis])) ** 2
        for axis in range(3)
    )) for left, right in pairs)


def _candidate_pattern_interface(
    second_skin: Mapping[str, Any], mesh: Mapping[str, Any], candidate_id: str,
) -> Dict[str, Any]:
    """Bind proposed pattern boundaries to one exact rear-candidate mesh."""
    interface = copy.deepcopy(second_skin["pattern_interface"])
    vertices = mesh["vertices"]
    boundary_rows = interface.get("pattern_boundary_candidates", [])
    for boundary in boundary_rows:
        ids = [int(value) for value in boundary.get("vertex_ids", [])]
        positions = [copy.deepcopy(vertices[index]) for index in ids]
        boundary["candidate_id"] = candidate_id
        boundary["candidate_vertices_cm"] = positions
        boundary["candidate_polyline_length_cm"] = round(_polyline_length(
            vertices, ids, closed=bool(boundary.get("closed_loop"))), 12)
        boundary["candidate_geometry_digest"] = stable_digest({
            "candidate_id": candidate_id,
            "boundary_id": boundary.get("boundary_id"),
            "positions_cm": positions,
        })
        boundary["rear_observed"] = False
        boundary["material_observed"] = False
    component_rows = second_skin["topology"].get("components", [])
    component_ranges = [
        (int(row["vertex_range"][0]), int(row["vertex_range"][1]), row)
        for row in component_rows
    ]

    def loop_is_closed(ids: Sequence[int]) -> bool:
        matching = [row for start, end, row in component_ranges
                    if ids and all(start <= value < end for value in ids)]
        if len(matching) != 1:
            raise ValueError("pattern loop does not belong to one typed component")
        return bool(matching[0]["closed_radial_shell"])

    attachment_rows = interface.get("attachment_boundary_candidates", [])
    for boundary in attachment_rows:
        parent_loops = boundary.get("parent_vertex_loops", [])
        child_loops = boundary.get("child_vertex_loops", [])

        def bind(loops: Any) -> List[Dict[str, Any]]:
            if not _sequence(loops):
                return []
            rows = []
            for loop in loops:
                ids = [int(value) for value in loop]
                positions = [copy.deepcopy(vertices[index]) for index in ids]
                closed = loop_is_closed(ids)
                rows.append({
                    "vertex_ids": ids,
                    "vertices_cm": positions,
                    "closed_loop": closed,
                    "length_cm": round(_polyline_length(
                        vertices, ids, closed=closed), 12),
                })
            return rows

        boundary["candidate_id"] = candidate_id
        boundary["parent_candidate_loops"] = bind(parent_loops)
        boundary["child_candidate_loops"] = bind(child_loops)
        boundary["candidate_geometry_digest"] = stable_digest({
            "candidate_id": candidate_id,
            "parent": boundary["parent_candidate_loops"],
            "child": boundary["child_candidate_loops"],
        })
        boundary["rear_observed"] = False
        boundary["material_observed"] = False
    component_bindings = []
    surface_layers = {
        row["surface_id"]: int(row["layer"])
        for row in second_skin["topology"]["surfaces"]
    }
    for start, end, component in component_ranges:
        ids = list(range(start, end))
        positions = [copy.deepcopy(vertices[index]) for index in ids]
        component_bindings.append({
            "candidate_id": candidate_id,
            "surface_id": component["surface_id"],
            "component_id": component["component_id"],
            "layer": surface_layers[component["surface_id"]],
            "closed_radial_shell": bool(component["closed_radial_shell"]),
            "vertex_ids": ids,
            "candidate_geometry_digest": stable_digest({
                "candidate_id": candidate_id,
                "surface_id": component["surface_id"],
                "component_id": component["component_id"],
                "positions_cm": positions,
            }),
        })
    component_bindings.sort(key=lambda row: (
        row["layer"], row["surface_id"], row["component_id"]))
    interface.update({
        "candidate_id": candidate_id,
        "candidate_specific": True,
        "generic_cape_fallback": False,
        "source_mesh_digest": stable_digest(mesh),
        "source_topology_digest": stable_digest(second_skin["topology"]),
        "source_front_digest": second_skin["source_front_contract"]["digest"],
        "component_mesh_bindings": component_bindings,
        "rear_state": "PROPOSED_UNOBSERVED",
        "material_state": "UNKNOWN_UNOBSERVED",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    })
    interface["digest"] = stable_digest({
        key: value for key, value in interface.items() if key != "digest"
    })
    return interface


def _candidate_payloads(
    second_skin: Mapping[str, Any], rear: Mapping[str, Any],
    approvals: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    front_contract = second_skin.get("source_front_contract")
    if not isinstance(front_contract, Mapping):
        raise ValueError("second skin lacks a typed source-front contract")
    raw_front_ids = front_contract.get("vertex_ids")
    if not _sequence(raw_front_ids):
        raise ValueError("second skin source-front ids are unavailable")
    front_ids = [int(value) for value in raw_front_ids]
    source_front = [[index, second_skin["mesh"]["vertices_cm"][index]]
                    for index in front_ids]
    source_front_digest = stable_digest(source_front)
    if source_front_digest != front_contract.get("digest"):
        raise ValueError("second skin source-front contract digest changed")
    for index, rear_row in enumerate(rear.get("candidates", [])):
        candidate_id = str(rear_row["candidate_id"])
        candidate_mesh = _rear_variant_mesh(second_skin, rear_row, index)
        pattern_interface = _candidate_pattern_interface(
            second_skin, candidate_mesh, candidate_id)
        row: Dict[str, Any] = {
            "candidate_id": candidate_id,
            "candidate_digest": rear_row["candidate_digest"],
            "domain": "BACK_STRUCTURE",
            "authority": {
                "rear": PROPOSED,
                "rear_observed": False,
                "material": "UNKNOWN_UNOBSERVED",
                "material_observed": False,
            },
            "mesh": candidate_mesh,
            "part_bindings": {surface["surface_id"]: surface["surface_id"]
                              for surface in second_skin["topology"]["surfaces"]},
            "pattern_handoff": {
                "candidate_id": candidate_id,
                "state": PROPOSED,
                "boundary_candidates": pattern_interface,
                "sewing_order": [],
                "sewability": "NOT_EVALUATED",
            },
            "pattern_interface": pattern_interface,
            "rear_candidate": copy.deepcopy(rear_row),
            "source_front_digest": source_front_digest,
            "source_front_invariant": False,
            "generic_cape_fallback": False,
        }
        approval = approvals.get(candidate_id)
        if isinstance(approval, Mapping):
            row["human_approval"] = copy.deepcopy(dict(approval))
        rows.append(row)
    front_checks = []
    for row in rows:
        candidate_front = [[index, row["mesh"]["vertices"][index]]
                           for index in front_ids]
        identical = candidate_front == source_front
        row["source_front_invariant"] = identical
        front_checks.append({
            "candidate_id": row["candidate_id"],
            "front_digest": stable_digest(candidate_front),
            "identical_to_second_skin_front": identical,
            "pattern_interface_digest": row["pattern_interface"]["digest"],
        })
    return rows, {
        "source_front_digest": source_front_digest,
        "source_front_contract_digest": front_contract["digest"],
        "source_front_contract_verified": True,
        "front_vertex_count": len(front_ids),
        "candidates": front_checks,
        "all_candidates_preserve_identical_front": bool(front_checks) and all(
            row["identical_to_second_skin_front"] for row in front_checks),
    }


def _audit_status(request: Mapping[str, Any]) -> Tuple[str, bool, Optional[str]]:
    mode = str(request.get("audit_mode", "HUMAN_AUDIT")).upper()
    if mode not in {"HUMAN_AUDIT", "AUTO_PROPOSED"}:
        raise ValueError("audit_mode must be HUMAN_AUDIT or AUTO_PROPOSED")
    audit = request.get("front_audit")
    decision = str(audit.get("decision", "")).upper() if isinstance(
        audit, Mapping) else ""
    edit_digest = request.get("human_edit_digest")
    confirmed = (mode == "HUMAN_AUDIT" and decision == "ACCEPT"
                 and isinstance(edit_digest, str) and bool(edit_digest.strip()))
    return mode, confirmed, edit_digest.strip() if isinstance(
        edit_digest, str) and edit_digest.strip() else None


def run(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the bounded geometry-first Atelier flow."""
    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            "UNKNOWN_GEOMETRIC_ATELIER_SCHEMA",
            "request schema must be exactly %s" % REQUEST_SCHEMA,
        )
    try:
        mode, front_confirmed, edit_digest = _audit_status(request)
        separation = request.get("separation")
        fit_request: Dict[str, Any] = {
            "schema": body_avatar_fit.REQUEST_SCHEMA,
            "separation": separation,
        }
        for key in ("requested_measurements", "interpolation",
                    "preview_profile_id", "projection_target_mask_ids"):
            if key in request:
                fit_request[key] = copy.deepcopy(request[key])
        if edit_digest:
            fit_request["human_edit_digest"] = edit_digest
        fit = body_avatar_fit.fit_body_avatar(fit_request)
        if fit.get("verdict") != "PROPOSED_IMAGE_RELATIVE_BODY_AVATAR_FIT":
            return _refusal(
                "UNKNOWN_GEOMETRIC_ATELIER_BODY_FIT",
                "bounded image-relative body fitting stopped",
                upstream=fit,
            )
        graph, parts = _graph_and_parts(request, fit)
        body = _body_proxy(fit["selected_avatar"])
        plan = _surface_plan(request, parts, fit, body)
        skin = second_skin_triangle_engine.build({
            "body_proxy": body,
            "surfaces": plan["surfaces"],
            "relations": plan.get("relations", []),
            "front_cues": plan.get("front_cues", []),
            "layer_gap_cm": _finite(request.get("layer_gap_cm"), 0.3),
            "resolution": copy.deepcopy(request.get("resolution", {
                "angular_segments": 16, "height_steps": 8,
            })),
        })
        if skin.get("geometry_verdict") != ANSWER:
            return _refusal(
                "UNKNOWN_GEOMETRIC_ATELIER_SECOND_SKIN",
                "second-skin triangle compilation stopped",
                upstream=skin, surface_plan=plan,
            )
        rear_request = {
            "schema": rear_candidate_ensemble.REQUEST_SCHEMA,
            "visible_part_graph": graph,
        }
        if "fashion_siglip_hits" in request:
            rear_request["fashion_siglip_hits"] = copy.deepcopy(
                request["fashion_siglip_hits"])
        if "multimodal_proposals" in request:
            rear_request["multimodal_proposals"] = copy.deepcopy(
                request["multimodal_proposals"])
        rear = rear_candidate_ensemble.generate_rear_candidates(rear_request)
        if rear.get("verdict") != PROPOSED or rear.get("candidate_count", 0) < 2:
            return _refusal(
                "UNKNOWN_GEOMETRIC_ATELIER_REAR_ENSEMBLE",
                "at least two separate rear proposals are required",
                upstream=rear,
            )
        approvals = request.get("candidate_approvals", {})
        approvals = approvals if isinstance(approvals, Mapping) else {}
        candidates, front_invariant = _candidate_payloads(skin, rear, approvals)
        target = _target_front(
            parts, fit, confirmed=front_confirmed,
            human_edit_digest=edit_digest,
        )
        repair_request: Dict[str, Any] = {
            "schema": candidate_3d_repair_loop.REQUEST_SCHEMA,
            "target_front": target,
            "candidates": candidates,
            "config": copy.deepcopy(request.get("repair_config", {
                "max_rounds": 3, "repair_gain": 1.0,
            })),
        }
        if "projection_config" in request:
            repair_request["projection_config"] = copy.deepcopy(
                request["projection_config"])
        if "scenarios" in request:
            repair_request["scenarios"] = copy.deepcopy(request["scenarios"])
        if target["reference_authority"] in {
                "OBSERVED", "HUMAN_CONFIRMED_TARGET"}:
            repair = candidate_3d_repair_loop.run(repair_request)
        else:
            repair = _preview_only_repair(candidates, target)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _refusal(
            "UNKNOWN_GEOMETRIC_ATELIER_INPUT", str(exc),
        )

    handoffs = repair.get("pattern_handoffs", [])
    if mode == "HUMAN_AUDIT" and not front_confirmed:
        phase = "HUMAN_GARMENT_AUDIT_REQUIRED"
        next_action = "confirm visible parts and adopt a cleaned front target"
    elif handoffs:
        phase = "PATTERN_HANDOFF_READY"
        next_action = "run flattening, sewing and redress validation for the approved digest"
    elif mode == "AUTO_PROPOSED":
        phase = "AUTO_PROPOSED_3D_PREVIEW_READY"
        next_action = "optional human review; no manufacturing authority has been granted"
    else:
        phase = "REAR_CANDIDATE_3D_APPROVAL_REQUIRED"
        next_action = "compare candidate-specific 3D and approve one exact final digest"

    evidence_cross = {
        "schema": "garment.geometric-atelier-evidence-cross.v1",
        "arms": {
            "support+": [
                {"path": "front/typed-regions", "state": (
                    "OBSERVED" if front_confirmed else PROPOSED),
                 "digest": target["camera_digest"]},
                {"path": "body/bounded-avatar", "state": PROPOSED,
                 "digest": fit["selected_avatar"]["geometry_digest"]},
            ],
            "support-": [
                {"path": "rear/pixels", "state": "UNKNOWN_UNOBSERVED"},
                {"path": "material/measurement", "state": "UNKNOWN_UNOBSERVED"},
            ],
            "cause+": [
                {"path": "geometry/second-skin", "state": PROPOSED,
                 "digest": skin["digest"]},
                {"path": "geometry/candidate-repair", "state": PROPOSED,
                 "digest": repair["digest"]},
            ],
            "cause-": [
                {"path": "manufacturing/sewability", "state": "NOT_EVALUATED"},
            ],
            "kind+": [
                {"path": "front", "kind": "HUMAN_CONFIRMED_OR_PROPOSED"},
                {"path": "rear", "kind": PROPOSED},
            ],
            "kind-": [
                {"path": "body", "kind": "NOT_INFERRED_FROM_PIXELS"},
                {"path": "material", "kind": "NOT_MEASURED"},
            ],
        },
        "deterministic_reduction": True,
        "disagreement_preserved": True,
    }
    physical_cross = {
        "schema": "garment.geometric-atelier-physical-cross.v1",
        "second_skin_cross_lattice_digest": skin["cross_lattice_digest"],
        "candidate_physical_cross_digests": [
            row.get("physical_cross", {}).get("digest")
            for row in repair.get("candidates", [])
            if isinstance(row, Mapping)
        ],
        "same_old_state_jacobi": skin["jacobi_reduction"],
        "is_solver": False,
        "role": "typed local exchange frame and deterministic reduction boundary",
    }
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": PROPOSED,
        "state": PROPOSED,
        "phase": phase,
        "next_required_action": next_action,
        "audit_mode": mode,
        "front_confirmed": front_confirmed,
        "body_avatar_fit": fit,
        "body_proxy": body,
        "visible_part_graph": graph,
        "surface_plan": plan,
        "second_skin": skin,
        "rear_ensemble": rear,
        "candidate_inputs": candidates,
        "candidate_front_invariant": front_invariant,
        "candidate_3d_repair": repair,
        "pattern_handoffs": copy.deepcopy(handoffs),
        "evidence_cross": evidence_cross,
        "physical_cross": physical_cross,
        "authority": {
            "front": "OBSERVED" if front_confirmed else PROPOSED,
            "body": "PROPOSED_BOUNDED_PROFILE",
            "rear": PROPOSED,
            "material": "UNKNOWN",
            "sewing": "NOT_EVALUATED",
        },
        "model_policy": {
            "fashion_siglip_and_multimodal_kept_separate": True,
            "single_embedding_winner": False,
            "llm_may_propose_but_not_approve": True,
            "unknown_garment_names_supported": True,
            "garment_name_is_not_generator_enum": True,
        },
        "human_approval_required": mode == "HUMAN_AUDIT",
        "auto_mode_preview_only": mode == "AUTO_PROPOSED",
        # An exact-digest comparison can open the next pattern boundary, but
        # this orchestration has not flattened, repaired, re-dressed, or
        # validated sewing. A hand-off is not a manufacturing-ready garment.
        "pattern_handoff_ready": bool(handoffs),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        "limitations": [
            "a single image does not observe the rear, body depth or material law",
            "second-skin boundaries are flattening candidates, not proved seams",
            "candidate repair is bounded geometric comparison, not industrial cloth calibration",
            "sewing search remains closed until an exact candidate digest is approved",
        ],
    }
    result["input_digest"] = stable_digest({
        "body_fit_input": fit.get("input_digest"),
        "visible_part_graph": graph,
        "audit_mode": mode,
        "front_confirmed": front_confirmed,
        "human_edit_digest": edit_digest,
        "surface_plan": plan,
        "fashion_siglip_hits": request.get("fashion_siglip_hits"),
        "multimodal_proposals": request.get("multimodal_proposals"),
        "candidate_approvals": approvals,
        "repair_config": repair_request.get("config"),
        "projection_config": repair_request.get("projection_config"),
        "scenarios": repair_request.get("scenarios"),
    })
    result["digest"] = stable_digest(result)
    return result


execute = run
orchestrate = run


__all__ = [
    "REQUEST_SCHEMA", "SCHEMA", "stable_digest", "run", "execute",
    "orchestrate",
]
