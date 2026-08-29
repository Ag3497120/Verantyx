# -*- coding: utf-8 -*-
"""Compile ``garment.structure.v1`` into an auditable pattern baseline.

This is the missing boundary between a selected structure hypothesis and the
existing pattern/repair/export stack.  It is deliberately a *compiler*, not a
garment classifier: nodes with geometric dimensions become pieces and graph
operations become seams, layers, or address-preserving pattern transforms.

The output can be cut as a geometric prototype, but is never labelled
manufacturing-ready merely because the polygons are valid.  Body dimensions,
material, closure details, seam allowance and construction validation remain
separate gates.  A front-only candidate therefore stays ``PROPOSED`` even
when deterministic geometry compilation itself returns ``ANSWER``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import garment_parts as _garment_parts
from . import garment_structure as _structure
from . import bodice_attachment_block as _bodice_attachments
from . import pattern_transforms as _transforms
from . import surface_modifier_ir as _surface_modifiers
from . import trouser_block as _trouser_block
from .outline_topology import repair_polygon


ANSWER = "ANSWER"
SCHEMA = "garment.compiled-pattern.v1"
Point = Tuple[float, float]
MIN_CUTOUT_CLEARANCE_CM = 0.5
_GEOMETRY_EPSILON = 1.0e-8
_ARMHOLE_SEGMENTS_PER_HALF = 8


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "why": why,
        "how_to_close": "supply or approve the missing typed construction geometry",
        **detail,
    }


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _positive(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and float(value) > 0.0)


def _finite(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)))


def _area(points: Sequence[Point]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2.0


def _signed_area(points: Sequence[Point]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(points, points[1:] + points[:1])) / 2.0


def _cross(a: Point, b: Point, c: Point) -> float:
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def _point_segment_distance(point: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    if denominator <= _GEOMETRY_EPSILON ** 2:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = max(0.0, min(1.0, ((point[0] - a[0]) * dx
                           + (point[1] - a[1]) * dy) / denominator))
    return math.hypot(point[0] - (a[0] + t * dx),
                      point[1] - (a[1] + t * dy))


def _point_on_boundary(point: Point, polygon: Sequence[Point]) -> bool:
    return any(_point_segment_distance(point, a, b) <= _GEOMETRY_EPSILON
               for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def _strictly_inside(point: Point, polygon: Sequence[Point]) -> bool:
    if _point_on_boundary(point, polygon):
        return False
    inside = False
    x, y = point
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) == (b[1] > y):
            continue
        crossing_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        if crossing_x > x:
            inside = not inside
    return inside


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if ((ab_c > _GEOMETRY_EPSILON and ab_d < -_GEOMETRY_EPSILON)
            or (ab_c < -_GEOMETRY_EPSILON and ab_d > _GEOMETRY_EPSILON)):
        if ((cd_a > _GEOMETRY_EPSILON and cd_b < -_GEOMETRY_EPSILON)
                or (cd_a < -_GEOMETRY_EPSILON and cd_b > _GEOMETRY_EPSILON)):
            return True
    return any(
        abs(value) <= _GEOMETRY_EPSILON
        and _point_segment_distance(point, p, q) <= _GEOMETRY_EPSILON
        for value, point, p, q in (
            (ab_c, c, a, b), (ab_d, d, a, b),
            (cd_a, a, c, d), (cd_b, b, c, d)))


def _simple_polygon(points: Sequence[Point]) -> bool:
    count = len(points)
    if count < 3 or abs(_signed_area(points)) <= _GEOMETRY_EPSILON:
        return False
    if len(set(points)) != count:
        return False
    edges = list(zip(points, points[1:] + points[:1]))
    for index, (a, b) in enumerate(edges):
        if math.hypot(b[0] - a[0], b[1] - a[1]) <= _GEOMETRY_EPSILON:
            return False
        for other, (c, d) in enumerate(edges[index + 1:], index + 1):
            if other == index + 1 or (index == 0 and other == count - 1):
                continue
            if _segments_intersect(a, b, c, d):
                return False
    return True


def _boundary_distance(a: Sequence[Point], b: Sequence[Point]) -> float:
    return min(
        min(_point_segment_distance(point, c, d) for c, d in
            zip(b, b[1:] + b[:1]))
        for point in a)


def _polygons_intersect(a: Sequence[Point], b: Sequence[Point]) -> bool:
    return any(_segments_intersect(p, q, r, s)
               for p, q in zip(a, a[1:] + a[:1])
               for r, s in zip(b, b[1:] + b[:1]))


def _cutout_points(value: Any, operation_id: str) -> Tuple[Optional[List[Point]], Optional[Dict[str, Any]]]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or len(value) < 3):
        return None, _unknown(
            "UNKNOWN_CUTOUT_POLYGON",
            f"{operation_id} needs a closed_polygon with at least three coordinate pairs")
    points: List[Point] = []
    try:
        for raw in value:
            if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
                    or len(raw) != 2 or not _finite(raw[0]) or not _finite(raw[1])):
                raise ValueError("non-finite coordinate pair")
            points.append((float(raw[0]), float(raw[1])))
    except (TypeError, ValueError, OverflowError):
        return None, _unknown(
            "UNKNOWN_CUTOUT_NONFINITE",
            f"{operation_id} closed_polygon must contain only finite [x,y] pairs")
    if points[0] == points[-1]:
        return None, _unknown(
            "UNKNOWN_CUTOUT_DUPLICATE_CLOSURE_VERTEX",
            f"{operation_id} must imply closure; repeating the first vertex creates a degenerate edge")
    if not _simple_polygon(points):
        return None, _unknown(
            "UNKNOWN_CUTOUT_SELF_INTERSECTION",
            f"{operation_id} closed_polygon must be simple, non-degenerate and non-self-intersecting")
    return points, None


def _trapezoid(height: float, top: float, bottom: float) -> List[Point]:
    """A wrap panel: e0=bottom, e1/e3=closure sides, e2=top."""
    return [(-bottom / 2.0, 0.0), (bottom / 2.0, 0.0),
            (top / 2.0, height), (-top / 2.0, height)]


def _rectangle(height: float, width: float) -> List[Point]:
    return _trapezoid(height, width, width)


def _hood(height: float, width: float, depth: float) -> List[Point]:
    # One side hood panel.  The curved crown is a deterministic four-segment
    # approximation; a pair is cut and joined around the crown/back edge.
    return [(0.0, 0.0), (width, 0.0),
            (width + depth * 0.18, height * 0.58),
            (width * 0.78, height), (width * 0.22, height),
            (-depth * 0.12, height * 0.58)]


def _edge_table(points: Sequence[Point]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for index, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        out[f"e{index}"] = {
            "points": [[round(a[0], 6), round(a[1], 6)],
                       [round(b[0], 6), round(b[1], 6)]],
            "length": round(math.hypot(b[0] - a[0], b[1] - a[1]), 6),
        }
    return out


def _resample_polyline(points: Sequence[Point], segments: int) -> List[Point]:
    """Return equal-arc segments on the exact input polyline.

    The operation inserts points on the existing drafted segments; it does not
    smooth, fit, or otherwise invent a new armhole/cap curve.  Equal segment
    counts let the compiled seam topology address every physical boundary
    segment with the established ``eN`` contract.
    """
    if segments <= 0 or len(points) < 2:
        raise ValueError("a polyline needs two points and a positive segment count")
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + math.hypot(
            b[0] - a[0], b[1] - a[1]))
    total = cumulative[-1]
    if total <= _GEOMETRY_EPSILON:
        raise ValueError("cannot resample a zero-length polyline")
    result: List[Point] = []
    edge_index = 0
    for index in range(segments + 1):
        distance = total * index / segments
        while (edge_index + 1 < len(cumulative) - 1
               and cumulative[edge_index + 1] < distance - _GEOMETRY_EPSILON):
            edge_index += 1
        a, b = points[edge_index], points[edge_index + 1]
        span = cumulative[edge_index + 1] - cumulative[edge_index]
        t = 0.0 if span <= _GEOMETRY_EPSILON else (
            distance - cumulative[edge_index]) / span
        result.append((a[0] + (b[0] - a[0]) * t,
                       a[1] + (b[1] - a[1]) * t))
    return result


def _edge_groups(labels: Sequence[str]) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for index, label in enumerate(labels):
        groups.setdefault(label, []).append(f"e{index}")
    return groups


def _expanded_piece(node: Mapping[str, Any], piece_id: str,
                    outline: Sequence[Point], labels: Sequence[str], *,
                    role: str, source_draft_piece: str,
                    garment_unit: str) -> Dict[str, Any]:
    if len(labels) != len(outline):
        raise ValueError("one boundary label is required per closed-outline segment")
    piece = _piece(node, outline, role=role)
    piece.update({"piece_id": piece_id, "name": piece_id,
                  "node_id": piece_id, "cut_count": 1})
    attributes = copy.deepcopy(dict(node.get("attributes", {})))
    attributes.update({
        "garment_unit": garment_unit,
        "source_node_id": str(node["node_id"]),
        "expanded_from_primitive": True,
        "dimension_authority": "PROPOSED_PREVIEW_MANNEQUIN",
        "target_wearer_measurement": False,
    })
    piece["attributes"] = attributes
    piece["boundary_edge_groups"] = _edge_groups(labels)
    piece["edge_semantics"] = {
        f"e{index}": label for index, label in enumerate(labels)}
    piece["provenance"] = {
        "method": "garment_parts draft + deterministic full-piece expansion",
        "source_node": str(node["node_id"]),
        "source_draft_piece": source_draft_piece,
        "state": "PROPOSED",
        "dimension_authority": "PROPOSED_PREVIEW_MANNEQUIN",
        "target_wearer_measurement": False,
        "corpus_used": False,
    }
    return piece


def _full_bodice_piece(node: Mapping[str, Any], drafted: Mapping[str, Any], *,
                       piece_id: str, role: str, garment_unit: str) -> Dict[str, Any]:
    """Unfold one half/fold bodice draft into a full front or back piece."""
    named = drafted["edges"]
    centre_neck = tuple(float(v) for v in named["襟ぐり"]["points"][0])
    neck = tuple(float(v) for v in named["襟ぐり"]["points"][-1])
    shoulder = tuple(float(v) for v in named["肩線"]["points"][-1])
    armhole = _resample_polyline(
        [tuple(float(v) for v in point)
         for point in named["袖ぐり"]["points"]],
        _ARMHOLE_SEGMENTS_PER_HALF)
    waist_side = tuple(float(v) for v in named["ウエスト"]["points"][0])
    centre_bottom = tuple(float(v) for v in named["ウエスト"]["points"][-1])
    right_path = [centre_neck, neck, shoulder, *armhole[1:],
                  waist_side, centre_bottom]
    left_return = [(-point[0], point[1])
                   for point in reversed(right_path[1:-1])]
    outline = right_path + left_return
    arm = _ARMHOLE_SEGMENTS_PER_HALF
    labels = (["neckline:right", "shoulder:right"]
              + ["armhole:right"] * arm
              + ["side:right", "waist:right", "waist:left", "side:left"]
              + ["armhole:left"] * arm
              + ["shoulder:left", "neckline:left"])
    return _expanded_piece(
        node, piece_id, outline, labels, role=role,
        source_draft_piece=str(drafted["name"]), garment_unit=garment_unit)


def _sleeve_piece(node: Mapping[str, Any], drafted: Mapping[str, Any], *,
                  piece_id: str, side: str, garment_unit: str) -> Dict[str, Any]:
    named = drafted["edges"]
    front = _resample_polyline(
        [tuple(float(v) for v in point)
         for point in named["袖山(前半)"]["points"]],
        _ARMHOLE_SEGMENTS_PER_HALF)
    back = _resample_polyline(
        [tuple(float(v) for v in point)
         for point in named["袖山(後半)"]["points"]],
        _ARMHOLE_SEGMENTS_PER_HALF)
    cuff_right = tuple(float(v) for v in named["袖口"]["points"][0])
    cuff_left = tuple(float(v) for v in named["袖口"]["points"][-1])
    outline = front + back[1:] + [cuff_right, cuff_left]
    arm = _ARMHOLE_SEGMENTS_PER_HALF
    labels = (["sleeve_cap:front"] * arm
              + ["sleeve_cap:back"] * arm
              + ["underarm:front", "cuff", "underarm:back"])
    return _expanded_piece(
        node, piece_id, outline, labels, role=f"set_in_sleeve_{side}",
        source_draft_piece=str(drafted["name"]), garment_unit=garment_unit)


def _group(piece: Mapping[str, Any], name: str) -> List[str]:
    return list(piece["boundary_edge_groups"][name])


def _one_group_edge(piece: Mapping[str, Any], name: str, *,
                    operation_id: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Resolve one semantic boundary without falling back to port-name words."""
    groups = piece.get("boundary_edge_groups", {})
    edges = groups.get(name) if isinstance(groups, Mapping) else None
    if (not isinstance(edges, Sequence) or isinstance(edges, (str, bytes))
            or len(edges) != 1 or not isinstance(edges[0], str)):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_RELATION_BOUNDARY",
            f"{operation_id} requires exactly one {name} boundary",
            operation_id=operation_id, piece_id=piece.get("piece_id"),
            semantic_boundary=name,
            resolved_edges=(list(edges) if isinstance(edges, Sequence)
                            and not isinstance(edges, (str, bytes)) else None))
    return str(edges[0]), None


def _bridge_seam(operation_id: str, a_piece: Mapping[str, Any], a_edge: str,
                 b_piece: Mapping[str, Any], b_edge: str, *,
                 role: str, group_id: str) -> Dict[str, Any]:
    return {
        "operation_id": operation_id,
        "kind": "JOIN",
        "construction_role": role,
        "seam_group_id": group_id,
        "a": {"piece_id": a_piece["piece_id"], "edge": a_edge},
        "b": {"piece_id": b_piece["piece_id"], "edge": b_edge},
        "state": "PROPOSED",
        "dimension_authority": "PROPOSED_PREVIEW_MANNEQUIN",
        "manufacturing_validated": False,
    }


def _sleeve_instance_sides(
    node: Mapping[str, Any],
) -> Tuple[Optional[Tuple[str, ...]], Optional[Dict[str, Any]]]:
    """Resolve physical sleeve instances without guessing a missing side.

    The historical one-sleeve bridge treated an omitted side/quantity as a
    conventional bilateral pair.  Keep that compatibility default, but make
    every explicit side, ``bilateral`` flag and quantity agree.  In
    particular, quantity=1 without left/right is not enough information to
    choose a body side.
    """
    attributes = node.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    node_id = str(node.get("node_id", ""))
    raw_side = attributes.get("side")
    side = str(raw_side).strip().lower() if raw_side is not None else ""
    aliases = {"both": "bilateral", "pair": "bilateral"}
    side = aliases.get(side, side)
    if side and side not in {"left", "right", "bilateral"}:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_SIDE",
            f"{node_id} side must be left, right, or bilateral",
            node_id=node_id, side=raw_side)

    raw_quantity = attributes.get("quantity")
    if raw_quantity is not None and (
            isinstance(raw_quantity, bool)
            or not isinstance(raw_quantity, int)
            or raw_quantity not in (1, 2)):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_QUANTITY",
            f"{node_id} sleeve quantity must be exactly 1 or 2",
            node_id=node_id, quantity=raw_quantity)
    quantity = raw_quantity
    bilateral = attributes.get("bilateral")
    if bilateral is not None and not isinstance(bilateral, bool):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_BILATERAL_FLAG",
            f"{node_id} bilateral must be a boolean",
            node_id=node_id, bilateral=bilateral)

    if side in {"left", "right"}:
        if quantity not in (None, 1) or bilateral is True:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_SIDE_QUANTITY_MISMATCH",
                f"{node_id} declares one side but also declares a pair",
                node_id=node_id, side=side, quantity=quantity,
                bilateral=bilateral)
        return (side,), None
    if side == "bilateral":
        if quantity not in (None, 2) or bilateral is False:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_SIDE_QUANTITY_MISMATCH",
                f"{node_id} declares bilateral but its quantity/flag disagrees",
                node_id=node_id, side=side, quantity=quantity,
                bilateral=bilateral)
        return ("left", "right"), None

    if bilateral is True or quantity == 2:
        if bilateral is False:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_SIDE_QUANTITY_MISMATCH",
                f"{node_id} quantity=2 conflicts with bilateral=false",
                node_id=node_id, quantity=quantity, bilateral=bilateral)
        return ("left", "right"), None
    if quantity == 1 or bilateral is False:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_SIDE_AMBIGUOUS",
            f"{node_id} has one sleeve but does not say left or right",
            node_id=node_id, quantity=quantity, bilateral=bilateral)
    # Backwards compatibility for the original bridge input, whose absence of
    # all instance fields meant the conventional left/right pair.
    return ("left", "right"), None


def _bodice_sleeve_bridge(body: Mapping[str, Any], sleeve: Mapping[str, Any],
                          *, candidate_state: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Expand one BODY_SHELL and one root SLEEVE into side-specific pieces."""
    body_attributes = body.get("attributes", {})
    sleeve_attributes = sleeve.get("attributes", {})
    body_attributes = body_attributes if isinstance(body_attributes, Mapping) else {}
    sleeve_attributes = sleeve_attributes if isinstance(sleeve_attributes, Mapping) else {}
    if (str(sleeve_attributes.get("shape", "")).lower() == "detached"
            or sleeve_attributes.get("attached") is False):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_BRIDGE_DETACHED",
            "a detached sleeve needs an explicit anchor topology, not a set-in armhole bridge")
    body_unit = str(body_attributes.get("garment_unit", "candidate")).strip()
    sleeve_unit_raw = sleeve_attributes.get("garment_unit")
    if (sleeve_unit_raw is not None
            and str(sleeve_unit_raw).strip() != body_unit):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_GARMENT_UNIT_MISMATCH",
            "an attached sleeve and its bodice must name the same garment_unit",
            body_garment_unit=body_unit,
            sleeve_garment_unit=str(sleeve_unit_raw).strip())
    sleeve_sides, side_error = _sleeve_instance_sides(sleeve)
    if side_error or sleeve_sides is None:
        return None, side_error

    bd = body["dimensions"]
    sd = sleeve["dimensions"]
    chest = float(bd.get("chest_cm", bd["circumference_cm"]))
    waist_ports = [
        float(port["length_cm"])
        for port in body.get("ports", [])
        if isinstance(port, Mapping)
        and str(port.get("interface", "")).lower() == "waist"
        and _positive(port.get("length_cm"))
    ]
    if waist_ports:
        waist = sum(waist_ports)
        waist_source = "sum of typed BODY_SHELL waist ports"
    else:
        waist_source = ("waist_cm" if "waist_cm" in bd else
                        "bottom_circumference_cm" if "bottom_circumference_cm" in bd
                        else "derived_preview_ratio")
        waist = float(bd.get("waist_cm", bd.get(
            "bottom_circumference_cm", chest * 0.82)))
    shoulder_source = ("shoulder_cm" if "shoulder_cm" in bd
                       else "derived_preview_ratio")
    shoulder = float(bd.get("shoulder_cm", chest * 0.40))
    measures = {
        "chest": chest,
        "shoulder": shoulder,
        "waist": waist,
        "bodice_length": float(bd["height_cm"]),
        "sleeve_length": float(sd["length_cm"]),
    }
    if not all(_positive(value) for value in measures.values()):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_PREVIEW_DIMENSIONS",
            "derived bodice/sleeve preview dimensions must be finite and positive",
            values=measures)

    body_params = body_attributes.get("draft_parameters", {})
    sleeve_params = sleeve_attributes.get("draft_parameters", {})
    if not isinstance(body_params, Mapping) or not isinstance(sleeve_params, Mapping):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_DRAFT_PARAMETERS",
            "draft_parameters must be typed objects when supplied")
    try:
        body_params = {str(key): float(value) for key, value in body_params.items()}
        sleeve_params = {str(key): float(value) for key, value in sleeve_params.items()}
    except (TypeError, ValueError, OverflowError):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_DRAFT_PARAMETERS",
            "draft_parameters must contain finite numeric values")
    if not all(math.isfinite(value) for value in list(body_params.values())
               + list(sleeve_params.values())):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_DRAFT_PARAMETERS",
            "draft_parameters must contain finite numeric values")
    # Typed BODY_SHELL waist values denote the actual proposed sewing loop.
    # The older garment_parts default adds design ease on top, which makes an
    # already matched skirt/trouser port geometrically unequal after drafting.
    # Keep caller-supplied draft_parameters authoritative, otherwise consume
    # the exact proposal loop and record it as preview geometry only.
    body_params.setdefault("waist_ease", 0.0)
    sleeve_params["cuff_add"] = float(sd["cuff_circumference_cm"]) / 2.0 - chest / 8.0
    sleeve_params.setdefault("ease_in", float(
        sleeve_attributes.get("cap_ease_cm", 2.0)))
    if not _finite(sleeve_params["ease_in"]) or sleeve_params["ease_in"] < 0.0:
        return None, _unknown(
            "UNKNOWN_SLEEVE_CAP_EASE",
            "cap_ease_cm must be finite and non-negative")

    def get_measure(name: str) -> float:
        return measures[name]

    bodice_draft = _garment_parts.draft_bodice(get_measure, dict(body_params))
    armhole_total = sum(float(piece["edges"]["袖ぐり"]["length"])
                        for piece in bodice_draft["pieces"])
    sleeve_drafts = {
        side: _garment_parts.draft_sleeve(
            get_measure, {**sleeve_params, "side": japanese}, armhole_total)
        for side, japanese in (("left", "左"), ("right", "右"))
    }
    front_draft, back_draft = bodice_draft["pieces"]
    body_id, sleeve_id = str(body["node_id"]), str(sleeve["node_id"])
    front = _full_bodice_piece(
        body, front_draft, piece_id=f"{body_id}:front",
        role="front_bodice", garment_unit=body_unit)
    back = _full_bodice_piece(
        body, back_draft, piece_id=f"{body_id}:back",
        role="back_bodice", garment_unit=body_unit)
    sleeve_pieces = {
        side: _sleeve_piece(
            sleeve, sleeve_drafts[side]["pieces"][0],
            piece_id=f"{sleeve_id}:{side}", side=side,
            garment_unit=body_unit)
        for side in sleeve_sides
    }
    for side, generated in sleeve_pieces.items():
        generated["attributes"].update({
            "derived_side": side,
            "physical_instance": f"{sleeve_id}:{side}",
            "source_quantity_expanded": True,
        })
        generated["provenance"]["instance_lineage"] = {
            "source_node_id": sleeve_id,
            "side": side,
            "cut_count": 1,
        }
    drafted_waist = sum(
        float(piece["edges"][edge]["length"])
        for piece in (front, back)
        for group, edge_names in piece["boundary_edge_groups"].items()
        if str(group).startswith("waist")
        for edge in edge_names)
    if abs(drafted_waist - waist) > 0.05:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_WAIST_BALANCE",
            "drafted front/back waist does not match the typed BODY_SHELL waist loop",
            typed_waist_cm=waist, drafted_waist_cm=round(drafted_waist, 6),
            difference_cm=round(drafted_waist - waist, 6))
    for generated in (front, back, *sleeve_pieces.values()):
        polygon = [tuple(float(value) for value in point)
                   for point in generated["outline"]]
        if not _simple_polygon(polygon):
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_DRAFT_TOPOLOGY",
                f"{generated['piece_id']} did not produce one simple non-zero outline",
                piece_id=generated["piece_id"])

    seams: List[Dict[str, Any]] = []
    for side in ("left", "right"):
        seams.append(_bridge_seam(
            f"bridge-shoulder-{side}", front, _group(front, f"shoulder:{side}")[0],
            back, _group(back, f"shoulder:{side}")[0],
            role="SHOULDER", group_id=f"shoulder:{side}"))
        seams.append(_bridge_seam(
            f"bridge-side-{side}", front, _group(front, f"side:{side}")[0],
            back, _group(back, f"side:{side}")[0],
            role="SIDE_SEAM", group_id=f"side:{side}"))
        sleeve_piece = sleeve_pieces.get(side)
        if sleeve_piece is None:
            continue
        seams.append(_bridge_seam(
            f"bridge-underarm-{side}", sleeve_piece,
            _group(sleeve_piece, "underarm:front")[0], sleeve_piece,
            _group(sleeve_piece, "underarm:back")[0],
            role="SLEEVE_UNDERARM", group_id=f"underarm:{side}"))

        # Both curves are equal-arc segmented.  Reverse whichever bodily side
        # runs in the opposite boundary direction; topology remains explicit
        # eN-to-eN and no composite/virtual edge is invented.
        for half, bodice_piece in (("front", front), ("back", back)):
            cap_edges = _group(sleeve_piece, f"sleeve_cap:{half}")
            arm_edges = _group(bodice_piece, f"armhole:{side}")
            if ((half == "front" and side == "right")
                    or (half == "back" and side == "left")):
                arm_edges = list(reversed(arm_edges))
            for index, (cap_edge, arm_edge) in enumerate(
                    zip(cap_edges, arm_edges), 1):
                seams.append(_bridge_seam(
                    f"bridge-armhole-{side}-{half}-{index:02d}",
                    sleeve_piece, cap_edge, bodice_piece, arm_edge,
                    role="SET_IN_SLEEVE",
                    group_id=f"armhole:{side}:{half}"))

    balance = []
    for side, sleeve_piece in sleeve_pieces.items():
        cap = sum(float(sleeve_piece["edges"][edge]["length"])
                  for half in ("front", "back")
                  for edge in _group(sleeve_piece, f"sleeve_cap:{half}"))
        armhole = sum(float(piece["edges"][edge]["length"])
                      for piece in (front, back)
                      for edge in _group(piece, f"armhole:{side}"))
        balance.append({
            "side": side,
            "sleeve_cap_cm": round(cap, 6),
            "armhole_cm": round(armhole, 6),
            "difference_cm": round(cap - armhole, 6),
            "intended_cap_ease_cm": round(float(sleeve_params["ease_in"]), 6),
            "difference_from_intended_ease_cm": round(
                (cap - armhole) - float(sleeve_params["ease_in"]), 6),
            "state": "PROPOSED",
            "manufacturing_guarantee": False,
        })

    dimension_records = {
        "chest": {"value_cm": chest, "source": "BODY_SHELL.circumference_cm",
                  "state": "PROPOSED_PREVIEW_MANNEQUIN"},
        "waist": {"value_cm": waist, "source": waist_source,
                  "state": "PROPOSED_PREVIEW_MANNEQUIN"},
        "shoulder": {"value_cm": shoulder, "source": shoulder_source,
                     "state": "PROPOSED_PREVIEW_MANNEQUIN"},
        "bodice_length": {"value_cm": measures["bodice_length"],
                          "source": "BODY_SHELL.height_cm",
                          "state": "PROPOSED_PREVIEW_MANNEQUIN"},
        "sleeve_length": {"value_cm": measures["sleeve_length"],
                          "source": "SLEEVE.length_cm",
                          "state": "PROPOSED_PREVIEW_MANNEQUIN"},
    }
    expansion = {
        "kind": "BODICE_SET_IN_SLEEVE_BRIDGE",
        "state": "PROPOSED",
        "candidate_state_does_not_promote_dimensions": candidate_state,
        "source_nodes": [body_id, sleeve_id],
        "generated_pieces": [piece["piece_id"]
                             for piece in (front, back,
                                           *sleeve_pieces.values())],
        "garment_unit": body_unit,
        "method": "garment_parts.draft_bodice + garment_parts.draft_sleeve",
        "armhole_segmentation": {
            "segments_per_half": _ARMHOLE_SEGMENTS_PER_HALF,
            "method": "equal arc-length insertion on existing drafted polylines",
        },
        "preview_dimensions": dimension_records,
        "sleeve_balance": copy.deepcopy(balance),
        "declared_upper_sleeve_circumference_cm": float(
            sd["upper_circumference_cm"]),
        "dimension_limitations": [
            "SLEEVE.upper_circumference_cm is retained as a PROPOSED input; draft_sleeve solves cap width from the armhole and does not independently fit that circumference",
            "candidate approval does not convert preview mannequin dimensions into target wearer measurements",
        ],
        "target_wearer_measurements_used": False,
        "manufacturing_guarantee": False,
        "lineage": [
            {"source": f"node/{body_id}", "target": front["piece_id"],
             "relation": "EXPANDED_FRONT_BODICE"},
            {"source": f"node/{body_id}", "target": back["piece_id"],
             "relation": "EXPANDED_BACK_BODICE"},
        ] + [
            {"source": f"node/{sleeve_id}",
             "target": sleeve_pieces[side]["piece_id"],
             "relation": f"EXPANDED_{side.upper()}_SLEEVE",
             "side": side, "cut_count": 1}
            for side in sleeve_sides
        ],
    }
    return {
        "pieces_by_node": {
            body_id: [front, back],
            sleeve_id: [sleeve_pieces[side] for side in sleeve_sides],
        },
        "seams": seams,
        "layers": [],
        "sleeve_balance": balance,
        "expansion": expansion,
        "canonical_port_piece": {
            body_id: front,
            sleeve_id: sleeve_pieces[sleeve_sides[0]],
        },
        "side_piece_map": {
            sleeve_id: {side: sleeve_pieces[side] for side in sleeve_sides},
        },
    }, None


def _piece(node: Mapping[str, Any], points: Sequence[Point], *,
           cut_count: int = 1, role: str = "wrap_panel") -> Dict[str, Any]:
    rounded = [[round(x, 6), round(y, 6)] for x, y in points]
    piece_id = str(node["node_id"])
    attributes = copy.deepcopy(dict(node.get("attributes", {})))
    return {
        "piece_id": piece_id,
        "name": piece_id,
        "node_id": piece_id,
        "source_node_id": piece_id,
        "primitive_kind": str(node["kind"]),
        "layer": int(node.get("layer", 0)),
        "role": role,
        "outline": rounded,
        "edges": _edge_table(list(points)),
        "area_cm2": round(_area(list(points)), 6),
        "cut_count": cut_count,
        "grain": {"direction": "parallel_to_height", "state": "PROPOSED"},
        "transforms": [],
        "attributes": attributes,
        "provenance": {
            "method": "deterministic primitive projection",
            "source_node": piece_id,
            "corpus_used": False,
        },
    }


def _node_piece(node: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    kind = str(node.get("kind", ""))
    d = node.get("dimensions", {})
    if not isinstance(d, Mapping):
        return None, _unknown("UNKNOWN_PRIMITIVE_DIMENSIONS", f"{node.get('node_id')} dimensions are not an object")
    try:
        if kind == "BODY_SHELL":
            h, circumference = float(d["height_cm"]), float(d["circumference_cm"])
            top = float(d.get("top_circumference_cm", circumference))
            bottom = float(d.get("bottom_circumference_cm", circumference))
            return _piece(node, _trapezoid(h, top, bottom), role="body_wrap"), None
        if kind == "TUBE":
            return _piece(node, _rectangle(float(d["length_cm"]),
                                           float(d["circumference_cm"])), role="tube_wrap"), None
        if kind in ("FRUSTUM", "FLARE"):
            return _piece(node, _trapezoid(float(d["height_cm"]),
                                           float(d["top_circumference_cm"]),
                                           float(d["bottom_circumference_cm"])),
                          role="flared_wrap"), None
        if kind == "GORE":
            return _piece(node, _trapezoid(float(d["length_cm"]),
                                           float(d["top_width_cm"]),
                                           float(d["bottom_width_cm"])), role="gore"), None
        if kind == "GUSSET":
            return _piece(node, _rectangle(float(d["length_cm"]),
                                           float(d["width_cm"])), role="gusset"), None
        if kind == "YOKE":
            quantity = int(node.get("attributes", {}).get("quantity", 1))
            if quantity <= 0:
                return None, _unknown("UNKNOWN_INVALID_CUT_COUNT", f"{node.get('node_id')} quantity must be positive")
            return _piece(node, _rectangle(float(d["height_cm"]),
                                           float(d["width_cm"])),
                          cut_count=quantity, role="yoke"), None
        if kind == "COLLAR":
            return _piece(node, _rectangle(float(d["width_cm"]),
                                           float(d["length_cm"])), role="collar"), None
        if kind == "HOOD":
            return _piece(node, _hood(float(d["height_cm"]), float(d["width_cm"]),
                                      float(d["depth_cm"])), cut_count=2, role="hood_side"), None
        if kind == "SLEEVE":
            points = _trapezoid(float(d["length_cm"]),
                                float(d["upper_circumference_cm"]),
                                float(d["cuff_circumference_cm"]))
            quantity = int(node.get("attributes", {}).get("quantity", 2))
            if quantity <= 0:
                return None, _unknown("UNKNOWN_INVALID_CUT_COUNT", f"{node.get('node_id')} quantity must be positive")
            return _piece(node, points, cut_count=quantity, role="sleeve_wrap"), None
        if kind == "BAND":
            quantity = int(node.get("attributes", {}).get("quantity", 1))
            if quantity <= 0:
                return None, _unknown("UNKNOWN_INVALID_CUT_COUNT", f"{node.get('node_id')} quantity must be positive")
            return _piece(node, _rectangle(float(d["width_cm"]),
                                           float(d["length_cm"])),
                          cut_count=quantity, role="band"), None
        if kind == "OVERLAY":
            return _piece(node, _rectangle(float(d["height_cm"]),
                                           float(d["width_cm"])), role="overlay"), None
        if kind in ("OPENING", "DRAPE_ANCHOR"):
            return None, None
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return None, _unknown("UNKNOWN_PRIMITIVE_COMPILE", f"{node.get('node_id')}: {exc}")
    return None, _unknown("UNKNOWN_PRIMITIVE_COMPILE", f"unsupported primitive {kind!r}")


def _semantic_tokens(value: Any) -> set[str]:
    """Return explicit semantic tokens without inferring from node names."""
    if isinstance(value, str):
        text = value.lower()
        for separator in ("-", "_", "/", ",", ";", ":"):
            text = text.replace(separator, " ")
        return {token for token in text.split()
                if token}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        tokens: set[str] = set()
        for item in value:
            tokens.update(_semantic_tokens(item))
        return tokens
    return set()


def _gore_panel_layout(graph: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Validate only explicitly addressed gore repetition and order.

    Two representations are accepted deliberately:

    * one template GORE whose ``panel_order`` is an ordered list with exactly
      ``panel_count`` entries; the compiler materialises one addressable cut
      piece per entry, or
    * one GORE per panel, all sharing ``gore_group_id`` and ``panel_count``,
      with each node carrying one integer ``panel_order``.

    A completely absent declaration remains an inspectable REVIEW.  A partial
    declaration is an UNKNOWN because filling it would invent rear topology.
    """
    gore_nodes = [node for node in graph.get("nodes", [])
                  if str(node.get("kind", "")) == "GORE"]
    reviews: List[Dict[str, Any]] = []
    if not gore_nodes:
        return {"pieces_by_node": {}, "groups": [], "reviews": reviews}, None

    explicit_names = {"gore_group_id", "panel_count", "panel_order"}
    declared: List[Mapping[str, Any]] = []
    undeclared: List[Mapping[str, Any]] = []
    for node in gore_nodes:
        attributes = node.get("attributes", {})
        attributes = attributes if isinstance(attributes, Mapping) else {}
        present = explicit_names & set(attributes)
        if not present:
            undeclared.append(node)
            continue
        if present != explicit_names:
            return None, _unknown(
                "UNKNOWN_GORE_PANEL_TOPOLOGY_INCOMPLETE",
                f"{node.get('node_id')} partially declares gore panel topology",
                node_id=node.get("node_id"), present=sorted(present),
                required=sorted(explicit_names))
        declared.append(node)

    if undeclared:
        reviews.append({
            "verdict": "REVIEW_GORE_PANEL_ORDER_REQUIRED",
            "state": "REVIEW",
            "node_ids": sorted(str(node.get("node_id", ""))
                               for node in undeclared),
            "why": (
                "GORE geometry is cuttable as isolated panels, but the front "
                "image does not establish their complete circular sewing order"
            ),
            "how_to_close": (
                "supply attributes.gore_group_id, panel_count, and panel_order; "
                "panel_order may be one integer per explicit panel or one ordered "
                "list on a repeated-panel template"
            ),
            "manufacturing_ready": False,
        })
    if not declared:
        return {"pieces_by_node": {}, "groups": [], "reviews": reviews}, None

    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for node in declared:
        attributes = node["attributes"]
        group_id = attributes.get("gore_group_id")
        panel_count = attributes.get("panel_count")
        if (not isinstance(group_id, str) or not group_id.strip()
                or isinstance(panel_count, bool)
                or not isinstance(panel_count, int) or panel_count < 2):
            return None, _unknown(
                "UNKNOWN_GORE_PANEL_TOPOLOGY_VALUE",
                f"{node.get('node_id')} needs a non-empty gore_group_id and panel_count >= 2",
                node_id=node.get("node_id"))
        grouped.setdefault(group_id.strip(), []).append(node)

    pieces_by_node: Dict[str, List[Dict[str, Any]]] = {}
    groups: List[Dict[str, Any]] = []
    for group_id in sorted(grouped):
        nodes = grouped[group_id]
        counts = {node["attributes"]["panel_count"] for node in nodes}
        if len(counts) != 1:
            return None, _unknown(
                "UNKNOWN_GORE_PANEL_COUNT_CONFLICT",
                f"{group_id} declares inconsistent panel_count values",
                group_id=group_id, panel_counts=sorted(counts))
        panel_count = int(next(iter(counts)))
        ordered_pieces: List[Dict[str, Any]] = []
        source_node_ids: List[str] = []

        if len(nodes) == 1 and isinstance(
                nodes[0]["attributes"].get("panel_order"), Sequence
        ) and not isinstance(nodes[0]["attributes"].get("panel_order"), (str, bytes)):
            node = nodes[0]
            order = list(node["attributes"]["panel_order"])
            if len(order) != panel_count or any(
                    isinstance(label, (Mapping, Sequence))
                    and not isinstance(label, (str, bytes)) for label in order):
                return None, _unknown(
                    "UNKNOWN_GORE_PANEL_ORDER_COUNT_MISMATCH",
                    f"{node.get('node_id')} panel_order must contain exactly panel_count scalar labels",
                    node_id=node.get("node_id"), panel_count=panel_count,
                    order_count=len(order))
            normalized_labels = [str(label).strip() for label in order]
            if (any(not label for label in normalized_labels)
                    or len(set(normalized_labels)) != panel_count):
                return None, _unknown(
                    "UNKNOWN_GORE_PANEL_ORDER_DUPLICATE",
                    f"{node.get('node_id')} panel_order labels must be unique and non-empty",
                    node_id=node.get("node_id"))
            template, error = _node_piece(node)
            if error:
                return None, error
            assert template is not None
            source_id = str(node["node_id"])
            source_node_ids.append(source_id)
            expanded: List[Dict[str, Any]] = []
            for index, label in enumerate(normalized_labels, 1):
                piece = copy.deepcopy(template)
                piece_id = f"{source_id}:panel-{index:02d}"
                piece.update({
                    "piece_id": piece_id,
                    "name": piece_id,
                    "cut_count": 1,
                    "role": "ordered_gore_panel",
                })
                piece["attributes"].update({
                    "gore_group_id": group_id,
                    "panel_count": panel_count,
                    "panel_order": index,
                    "panel_label": label,
                })
                piece["provenance"].update({
                    "method": "explicit ordered repeated GORE template",
                    "source_node": source_id,
                    "panel_order": index,
                    "panel_label": label,
                    "authority": "PROPOSED_EXPLICIT_IR",
                })
                expanded.append(piece)
            pieces_by_node[source_id] = expanded
            ordered_pieces.extend(expanded)
        else:
            if len(nodes) != panel_count:
                return None, _unknown(
                    "UNKNOWN_GORE_PANEL_COUNT_MISMATCH",
                    f"{group_id} declares {panel_count} panels but provides {len(nodes)}",
                    group_id=group_id, panel_count=panel_count,
                    supplied_node_count=len(nodes))
            by_order: Dict[int, Mapping[str, Any]] = {}
            for node in nodes:
                order = node["attributes"].get("panel_order")
                if (isinstance(order, bool) or not isinstance(order, int)
                        or order < 1 or order > panel_count or order in by_order):
                    return None, _unknown(
                        "UNKNOWN_GORE_PANEL_ORDER",
                        f"{group_id} needs unique integer panel_order values 1..panel_count",
                        group_id=group_id, node_id=node.get("node_id"),
                        panel_order=order)
                by_order[order] = node
            if set(by_order) != set(range(1, panel_count + 1)):
                return None, _unknown(
                    "UNKNOWN_GORE_PANEL_ORDER_GAP",
                    f"{group_id} panel_order must cover 1..panel_count without gaps",
                    group_id=group_id, known_orders=sorted(by_order))
            for order in range(1, panel_count + 1):
                node = by_order[order]
                piece, error = _node_piece(node)
                if error:
                    return None, error
                assert piece is not None
                piece["role"] = "ordered_gore_panel"
                piece["attributes"].update({
                    "gore_group_id": group_id,
                    "panel_count": panel_count,
                    "panel_order": order,
                })
                piece["provenance"].update({
                    "method": "explicit ordered GORE panel set",
                    "panel_order": order,
                    "authority": "PROPOSED_EXPLICIT_IR",
                })
                node_id = str(node["node_id"])
                source_node_ids.append(node_id)
                pieces_by_node[node_id] = [piece]
                ordered_pieces.append(piece)

        groups.append({
            "group_id": group_id,
            "panel_count": panel_count,
            "source_node_ids": source_node_ids,
            "ordered_piece_ids": [piece["piece_id"] for piece in ordered_pieces],
            "state": "PROPOSED",
            "order_source": "EXPLICIT_TYPED_IR",
            "rear_observed": False,
            "manufacturing_ready": False,
        })
    return {"pieces_by_node": pieces_by_node, "groups": groups,
            "reviews": reviews}, None


def _port_edge(port: Mapping[str, Any], piece: Optional[Mapping[str, Any]] = None,
               used: Iterable[str] = ()) -> str:
    text = (str(port.get("port_id", "")) + " " + str(port.get("interface", ""))).lower()
    if piece is not None:
        groups = piece.get("boundary_edge_groups", {})
        if isinstance(groups, Mapping):
            preferred: List[str] = []
            if any(word in text for word in ("cuff", "wrist")):
                preferred = ["cuff"]
            elif any(word in text for word in ("neck", "collar")):
                preferred = [name for name in groups
                             if str(name).startswith("neckline")]
            elif "waist" in text:
                preferred = [name for name in groups
                             if str(name).startswith("waist")]
            for name in preferred:
                edges = groups.get(name)
                if (isinstance(edges, Sequence)
                        and not isinstance(edges, (str, bytes))):
                    available = [str(edge) for edge in edges
                                 if str(edge) not in set(used)]
                    if len(available) == 1:
                        return available[0]
    if any(word in text for word in ("top", "upper", "neck", "waist_in", "waist_top")):
        return "e2"
    if any(word in text for word in ("bottom", "lower", "hem", "cuff", "waist_out", "waist_bottom")):
        return "e0"
    occupied = set(used)
    if piece is not None and _positive(port.get("length_cm")):
        declared = float(port["length_cm"])
        ranked = sorted(piece.get("edges", {}),
                        key=lambda edge: (abs(float(piece["edges"][edge]["length"]) - declared), edge))
        available = [edge for edge in ranked if edge not in occupied]
        if available:
            return available[0]
    return "e1" if "e1" not in occupied else "e3"


def _refresh_piece(piece: Dict[str, Any]) -> None:
    points = [tuple(p) for p in piece["outline"]]
    piece["edges"] = _edge_table(points)
    piece["area_cm2"] = round(_area(points), 6)


def _find_piece(pieces: List[Dict[str, Any]], node_id: str) -> Optional[Dict[str, Any]]:
    return next((piece for piece in pieces if piece.get("node_id") == node_id), None)


def _find_piece_id(pieces: List[Dict[str, Any]], piece_id: str) -> Optional[Dict[str, Any]]:
    return next((piece for piece in pieces if piece.get("piece_id") == piece_id), None)


def _stable_polygon(points: Sequence[Point], operation_id: str) -> Optional[Dict[str, Any]]:
    """Reject geometry whose validation would silently renumber its edges."""
    checked = repair_polygon(points)
    if checked.get("verdict") != ANSWER:
        return _unknown(
            "UNKNOWN_OPERATION_POLYGON",
            f"{operation_id} does not produce one simple non-zero polygon",
            topology=checked)
    provenance = checked.get("provenance", {})
    if (provenance.get("consecutive_duplicates_removed", 0)
            or provenance.get("collinear_points_removed", 0)
            or provenance.get("winding_reversed", False)):
        return _unknown(
            "UNKNOWN_OPERATION_ADDRESS_UNSTABLE",
            f"{operation_id} would renumber edges during polygon normalisation",
            topology=checked)
    return None


def _cut_counts(parameters: Mapping[str, Any], operation_id: str,
                source_count: int) -> Tuple[Optional[Tuple[int, int]], Optional[Dict[str, Any]]]:
    source_after = parameters.get("source_cut_count")
    generated = parameters.get("new_cut_count")
    if (isinstance(source_after, bool) or not isinstance(source_after, int)
            or source_after <= 0 or isinstance(generated, bool)
            or not isinstance(generated, int) or generated <= 0):
        return None, _unknown(
            "UNKNOWN_DERIVED_PIECE_CUT_COUNT",
            f"{operation_id} needs explicit positive source_cut_count and new_cut_count",
            current_source_cut_count=source_count)
    return (source_after, generated), None


def _declared_lineage(parameters: Mapping[str, Any], expected: Mapping[str, str],
                      operation_id: str) -> Optional[Dict[str, Any]]:
    declared = parameters.get("source_edge_lineage")
    if not isinstance(declared, Mapping):
        return _unknown(
            "UNKNOWN_SOURCE_EDGE_LINEAGE_REQUIRED",
            f"{operation_id} needs source_edge_lineage for every source edge",
            expected=copy.deepcopy(dict(expected)))
    normalised = {str(key): str(value) for key, value in declared.items()}
    if normalised != dict(expected):
        return _unknown(
            "UNKNOWN_SOURCE_EDGE_LINEAGE_MISMATCH",
            f"{operation_id} source_edge_lineage disagrees with generated geometry",
            expected=copy.deepcopy(dict(expected)), declared=normalised)
    return None


def _apply_cutout(piece: Dict[str, Any], operation: Mapping[str, Any],
                  source: Mapping[str, Any], source_edge: str, *,
                  candidate_state: str,
                  approval: Optional[Mapping[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Attach one validated subtractive contour without changing outer addresses."""
    operation_id = str(operation.get("operation_id", ""))
    parameters = operation.get("parameters", {})
    assert isinstance(parameters, Mapping)
    points, error = _cutout_points(parameters.get("closed_polygon"), operation_id)
    if error:
        return None, error
    assert points is not None
    clearance_raw = parameters.get("minimum_clearance_cm",
                                   MIN_CUTOUT_CLEARANCE_CM)
    if not _positive(clearance_raw):
        return None, _unknown(
            "UNKNOWN_CUTOUT_CLEARANCE",
            f"{operation_id} minimum_clearance_cm must be finite and positive")
    required_clearance = float(clearance_raw)
    contour_id = parameters.get("contour_id", f"{operation_id}:inner-0")
    if not isinstance(contour_id, str) or not contour_id.strip():
        return None, _unknown(
            "UNKNOWN_CUTOUT_ID",
            f"{operation_id} contour_id must be a non-empty string")
    contour_id = contour_id.strip()
    front_boundary_digest = parameters.get("source_front_boundary_digest")
    if (front_boundary_digest is not None
            and (not isinstance(front_boundary_digest, str)
                 or not front_boundary_digest.strip())):
        return None, _unknown(
            "UNKNOWN_CUTOUT_FRONT_BOUNDARY_DIGEST",
            f"{operation_id} source_front_boundary_digest must be a non-empty string when supplied")
    if isinstance(front_boundary_digest, str):
        front_boundary_digest = front_boundary_digest.strip()
    existing = piece.get("inner_cutouts", [])
    if not isinstance(existing, list):
        return None, _unknown(
            "UNKNOWN_CUTOUT_EXISTING_CONTRACT",
            f"{piece['piece_id']} inner_cutouts is not a typed list")
    if any(row.get("contour_id") == contour_id for row in existing
           if isinstance(row, Mapping)):
        return None, _unknown(
            "UNKNOWN_CUTOUT_DUPLICATE_ID",
            f"{piece['piece_id']} already has contour_id {contour_id}")

    outer = [(float(point[0]), float(point[1])) for point in piece["outline"]]
    if (not all(_strictly_inside(point, outer) for point in points)
            or _polygons_intersect(points, outer)):
        return None, _unknown(
            "UNKNOWN_CUTOUT_NOT_STRICTLY_INSIDE",
            f"{operation_id} must stay strictly inside {piece['piece_id']} outer boundary")
    outer_clearance = min(_boundary_distance(points, outer),
                          _boundary_distance(outer, points))
    if outer_clearance + _GEOMETRY_EPSILON < required_clearance:
        return None, _unknown(
            "UNKNOWN_CUTOUT_OUTER_CLEARANCE",
            f"{operation_id} is too close to the outer boundary",
            required_clearance_cm=required_clearance,
            measured_clearance_cm=round(outer_clearance, 6))

    peer_clearances: List[Dict[str, Any]] = []
    for prior in existing:
        if not isinstance(prior, Mapping):
            return None, _unknown(
                "UNKNOWN_CUTOUT_EXISTING_CONTRACT",
                f"{piece['piece_id']} contains an untyped inner contour")
        prior_points, prior_error = _cutout_points(
            prior.get("points"), str(prior.get("operation_id", "existing-cutout")))
        if prior_error:
            return None, _unknown(
                "UNKNOWN_CUTOUT_EXISTING_GEOMETRY",
                f"{piece['piece_id']} contains invalid existing inner geometry",
                detail=prior_error)
        assert prior_points is not None
        if (_polygons_intersect(points, prior_points)
                or _strictly_inside(points[0], prior_points)
                or _strictly_inside(prior_points[0], points)):
            return None, _unknown(
                "UNKNOWN_CUTOUT_CONTOUR_INTERSECTION",
                f"{operation_id} intersects or nests another inner contour",
                other_contour_id=prior.get("contour_id"))
        distance = min(_boundary_distance(points, prior_points),
                       _boundary_distance(prior_points, points))
        required = max(required_clearance,
                       float(prior.get("minimum_clearance_cm",
                                       MIN_CUTOUT_CLEARANCE_CM)))
        if distance + _GEOMETRY_EPSILON < required:
            return None, _unknown(
                "UNKNOWN_CUTOUT_PEER_CLEARANCE",
                f"{operation_id} is too close to another inner contour",
                other_contour_id=prior.get("contour_id"),
                required_clearance_cm=required,
                measured_clearance_cm=round(distance, 6))
        peer_clearances.append({
            "contour_id": prior.get("contour_id"),
            "clearance_cm": round(distance, 6),
        })

    input_clockwise = _signed_area(points) < 0.0
    count = len(points)
    if input_clockwise:
        normalised = list(points)
        edge_map = {f"e{index}": f"i{index}" for index in range(count)}
    else:
        normalised = list(reversed(points))
        edge_map = {f"e{index}": f"i{(count - 2 - index) % count}"
                    for index in range(count)}
    rounded = [[round(x, 6), round(y, 6)] for x, y in normalised]
    approval_binding = {
        "candidate_state": candidate_state,
        "approval_digest": (str(approval.get("digest"))
                            if isinstance(approval, Mapping) else None),
        "approved_by": (str(approval.get("by"))
                        if isinstance(approval, Mapping) else None),
        "cutout_authority": "PROPOSED",
    }
    operation_binding = {
        "operation_id": operation_id,
        "kind": "CUTOUT",
        "source": copy.deepcopy(dict(source)),
        "parameters": copy.deepcopy(dict(parameters)),
    }
    lineage = [
        {
            "source": f"operation/{operation_id}/closed_polygon/{old}",
            "target": f"piece/{piece['piece_id']}/inner/{contour_id}/{new}",
            "relation": "GENERATED_INNER_CUT_EDGE",
        }
        for old, new in sorted(edge_map.items())
    ]
    record: Dict[str, Any] = {
        "operation_id": operation_id,
        "kind": "CUTOUT",
        "state": "PROPOSED",
        "piece_id": piece["piece_id"],
        "contour_id": contour_id,
        "points": rounded,
        "edges": _edge_table(normalised),
        "area_cm2": round(_area(normalised), 6),
        "minimum_clearance_cm": required_clearance,
        "minimum_clearance_state": (
            "PROPOSED_DEFAULT" if "minimum_clearance_cm" not in parameters
            else "EXPLICIT_INPUT"),
        "measured_outer_clearance_cm": round(outer_clearance, 6),
        "peer_clearances": peer_clearances,
        "source_binding": {
            "node_id": str(source.get("node_id", "")),
            "port_id": str(source.get("port_id", "")),
            "piece_id": piece["piece_id"],
            "edge": source_edge,
        },
        "operation_digest": _digest(operation_binding),
        "contour_edge_lineage": lineage,
        "approval_binding": approval_binding,
        **({
            "source_front_boundary_digest": front_boundary_digest,
            "source_front_boundary_digest_state": "PROPOSED_LINEAGE_ONLY",
            "source_front_boundary_semantics_observed": False,
        } if front_boundary_digest is not None else {}),
        "provenance": {
            "method": "validated nested subtractive contour",
            "input_winding": "CLOCKWISE" if input_clockwise else "COUNTERCLOCKWISE",
            "output_winding": "CLOCKWISE",
            "outer_boundary_changed": False,
            "outer_edge_addresses_changed": False,
            "corpus_used": False,
            "front_boundary_lineage_is_semantic_observation": False,
        },
    }
    digest_payload = copy.deepcopy(record)
    record["digest"] = _digest(digest_payload)
    piece.setdefault("inner_cutouts", []).append(copy.deepcopy(record))
    gross_area = float(piece.get("gross_area_cm2", piece["area_cm2"]))
    piece["gross_area_cm2"] = round(gross_area, 6)
    piece["inner_cut_area_cm2"] = round(sum(
        float(row["area_cm2"]) for row in piece["inner_cutouts"]), 6)
    piece["net_area_cm2"] = round(
        gross_area - float(piece["inner_cut_area_cm2"]), 6)
    if piece["net_area_cm2"] <= _GEOMETRY_EPSILON:
        return None, _unknown(
            "UNKNOWN_CUTOUT_NET_AREA",
            f"{operation_id} leaves no positive material area")
    return record, None


def _derived_piece(source: Mapping[str, Any], new_piece_id: str,
                   points: Sequence[Point], *, operation_id: str,
                   method: str, cut_count: int, side: str,
                   detail: Mapping[str, Any]) -> Dict[str, Any]:
    piece = copy.deepcopy(dict(source))
    piece.update({
        "piece_id": new_piece_id,
        "name": new_piece_id,
        "node_id": new_piece_id,
        "outline": [[round(x, 6), round(y, 6)] for x, y in points],
        "cut_count": cut_count,
    })
    attributes = copy.deepcopy(dict(piece.get("attributes", {})))
    attributes.update({"derived_side": side, "state": "PROPOSED"})
    piece["attributes"] = attributes
    piece["provenance"] = {
        "method": method,
        "source_piece": source["piece_id"],
        "source_node": source.get("node_id"),
        "operation_id": operation_id,
        "state": "PROPOSED",
        "corpus_used": False,
        **copy.deepcopy(dict(detail)),
    }
    _refresh_piece(piece)
    return piece


def _mirror_piece(source: Dict[str, Any], parameters: Mapping[str, Any],
                  operation_id: str, known_ids: Iterable[str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if source.get("inner_cutouts"):
        return None, None, _unknown(
            "UNKNOWN_DERIVED_PIECE_INNER_CONTOUR_LINEAGE",
            f"{operation_id} cannot mirror an existing inner contour until its transformed lineage is explicit")
    if source.get("transforms"):
        return None, None, _unknown(
            "UNKNOWN_DERIVED_PIECE_TRANSFORM_LINEAGE",
            f"{operation_id} cannot duplicate prior sewing transforms without explicit transformed-operation lineage")
    axis = parameters.get("axis")
    offset = parameters.get("offset_cm")
    side = parameters.get("side")
    new_piece_id = parameters.get("new_piece_id")
    if axis not in ("x", "y") or not _finite(offset):
        return None, None, _unknown(
            "UNKNOWN_MIRROR_AXIS",
            f"{operation_id} needs axis 'x' or 'y' and a finite offset_cm")
    if side not in ("negative_to_positive", "positive_to_negative"):
        return None, None, _unknown(
            "UNKNOWN_MIRROR_SIDE",
            f"{operation_id} needs an explicit source-to-target side")
    if (not isinstance(new_piece_id, str) or not new_piece_id.strip()
            or new_piece_id in set(known_ids)):
        return None, None, _unknown(
            "UNKNOWN_DERIVED_PIECE_ID",
            f"{operation_id} needs a new unique piece_id")
    counts, error = _cut_counts(parameters, operation_id, source["cut_count"])
    if error:
        return None, None, error
    assert counts is not None
    coordinate = 0 if axis == "x" else 1
    values = [float(point[coordinate]) for point in source["outline"]]
    position = float(offset)
    epsilon = 1.0e-9
    if side == "negative_to_positive":
        valid_side = all(value <= position + epsilon for value in values) and any(
            value < position - epsilon for value in values)
    else:
        valid_side = all(value >= position - epsilon for value in values) and any(
            value > position + epsilon for value in values)
    if not valid_side:
        return None, None, _unknown(
            "UNKNOWN_MIRROR_SOURCE_CROSSES_AXIS",
            f"{operation_id} source geometry is not wholly on the declared source side",
            axis=axis, offset_cm=position, side=side)
    reflected: List[Point] = []
    for raw in source["outline"]:
        point = [float(raw[0]), float(raw[1])]
        point[coordinate] = 2.0 * position - point[coordinate]
        reflected.append((point[0], point[1]))
    # Reflection reverses winding.  Reverse the vertex order explicitly and
    # expose the corresponding edge renumbering instead of pretending eN was
    # preserved.
    reflected.reverse()
    polygon_error = _stable_polygon(reflected, operation_id)
    if polygon_error:
        return None, None, polygon_error
    count = len(source["outline"])
    expected = {f"e{index}": f"e{(count - 2 - index) % count}"
                for index in range(count)}
    lineage_error = _declared_lineage(parameters, expected, operation_id)
    if lineage_error:
        return None, None, lineage_error
    source_before = copy.deepcopy(source)
    source["cut_count"] = counts[0]
    generated = _derived_piece(
        source_before, new_piece_id, reflected, operation_id=operation_id,
        method="explicit axis reflection", cut_count=counts[1], side=str(side),
        detail={"axis": axis, "offset_cm": position})
    lineage = [
        {"source": f"{source_before['piece_id']}/{old}",
         "target": f"{new_piece_id}/{new}",
         "relation": "MIRRORED_REVERSED_WINDING_REMAP"}
        for old, new in sorted(expected.items())
    ]
    record = {
        "operation_id": operation_id,
        "kind": "MIRROR",
        "state": "PROPOSED",
        "source_piece_id": source_before["piece_id"],
        "new_piece_id": new_piece_id,
        "axis": axis,
        "offset_cm": position,
        "side": side,
        "source_cut_count_before": source_before["cut_count"],
        "source_cut_count_after": counts[0],
        "new_cut_count": counts[1],
        "source_edge_lineage": lineage,
        "before_digest": _digest(source_before),
        "after_digest": _digest(generated),
    }
    return generated, record, None


def _asymmetric_piece(source: Dict[str, Any], parameters: Mapping[str, Any],
                      operation_id: str, known_ids: Iterable[str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if source.get("inner_cutouts"):
        return None, None, _unknown(
            "UNKNOWN_DERIVED_PIECE_INNER_CONTOUR_LINEAGE",
            f"{operation_id} cannot deform an existing inner contour until its transformed lineage is explicit")
    if source.get("transforms"):
        return None, None, _unknown(
            "UNKNOWN_DERIVED_PIECE_TRANSFORM_LINEAGE",
            f"{operation_id} cannot duplicate prior sewing transforms without explicit transformed-operation lineage")
    new_piece_id = parameters.get("new_piece_id")
    side = parameters.get("side")
    offsets = parameters.get("vertex_offsets_cm")
    if side not in ("left", "right", "front", "back"):
        return None, None, _unknown(
            "UNKNOWN_ASYMMETRY_SIDE",
            f"{operation_id} needs side left/right/front/back")
    if (not isinstance(new_piece_id, str) or not new_piece_id.strip()
            or new_piece_id in set(known_ids)):
        return None, None, _unknown(
            "UNKNOWN_DERIVED_PIECE_ID",
            f"{operation_id} needs a new unique piece_id")
    if (not isinstance(offsets, Sequence) or isinstance(offsets, (str, bytes))
            or len(offsets) != len(source["outline"])):
        return None, None, _unknown(
            "UNKNOWN_ASYMMETRY_OFFSETS",
            f"{operation_id} needs one [dx,dy] vertex_offsets_cm pair per source vertex")
    parsed: List[Point] = []
    try:
        for value in offsets:
            if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
                    or len(value) != 2 or not _finite(value[0]) or not _finite(value[1])):
                raise ValueError("offsets must be finite pairs")
            parsed.append((float(value[0]), float(value[1])))
    except (TypeError, ValueError, OverflowError):
        return None, None, _unknown(
            "UNKNOWN_ASYMMETRY_OFFSETS",
            f"{operation_id} vertex_offsets_cm must contain finite numeric pairs")
    if not any(abs(x) > 1.0e-12 or abs(y) > 1.0e-12 for x, y in parsed):
        return None, None, _unknown(
            "UNKNOWN_ASYMMETRY_NO_CHANGE",
            f"{operation_id} does not change any vertex")
    counts, error = _cut_counts(parameters, operation_id, source["cut_count"])
    if error:
        return None, None, error
    assert counts is not None
    outline = [(float(point[0]) + delta[0], float(point[1]) + delta[1])
               for point, delta in zip(source["outline"], parsed)]
    polygon_error = _stable_polygon(outline, operation_id)
    if polygon_error:
        return None, None, polygon_error
    expected = {edge: edge for edge in source["edges"]}
    lineage_error = _declared_lineage(parameters, expected, operation_id)
    if lineage_error:
        return None, None, lineage_error
    source_before = copy.deepcopy(source)
    source["cut_count"] = counts[0]
    generated = _derived_piece(
        source_before, new_piece_id, outline, operation_id=operation_id,
        method="explicit per-vertex asymmetric displacement",
        cut_count=counts[1], side=str(side),
        detail={"vertex_offsets_cm": [[x, y] for x, y in parsed]})
    lineage = [
        {"source": f"{source_before['piece_id']}/{edge}",
         "target": f"{new_piece_id}/{edge}",
         "relation": "EXPLICIT_VERTEX_DEFORMATION"}
        for edge in sorted(expected)
    ]
    record = {
        "operation_id": operation_id,
        "kind": "ASYMMETRY",
        "state": "PROPOSED",
        "source_piece_id": source_before["piece_id"],
        "new_piece_id": new_piece_id,
        "side": side,
        "vertex_offsets_cm": [[x, y] for x, y in parsed],
        "source_cut_count_before": source_before["cut_count"],
        "source_cut_count_after": counts[0],
        "new_cut_count": counts[1],
        "source_edge_lineage": lineage,
        "before_digest": _digest(source_before),
        "after_digest": _digest(generated),
    }
    return generated, record, None


def _line_side(a: Point, b: Point, point: Point) -> float:
    return ((b[0] - a[0]) * (point[1] - a[1])
            - (b[1] - a[1]) * (point[0] - a[0]))


def _clip_half_plane(points: Sequence[Point], line_a: Point, line_b: Point,
                     keep_positive: bool) -> List[Point]:
    output: List[Point] = []
    epsilon = 1.0e-9
    for current, following in zip(points, points[1:] + points[:1]):
        current_side = _line_side(line_a, line_b, current)
        following_side = _line_side(line_a, line_b, following)
        current_inside = current_side >= -epsilon if keep_positive else current_side <= epsilon
        following_inside = following_side >= -epsilon if keep_positive else following_side <= epsilon
        if current_inside:
            output.append(current)
        if current_inside != following_inside:
            denominator = current_side - following_side
            if abs(denominator) <= epsilon:
                continue
            t = current_side / denominator
            output.append((current[0] + (following[0] - current[0]) * t,
                           current[1] + (following[1] - current[1]) * t))
    return output


def _is_convex(points: Sequence[Point]) -> bool:
    signs = []
    for before, current, after in zip(points, points[1:] + points[:1],
                                      points[2:] + points[:2]):
        value = ((current[0] - before[0]) * (after[1] - current[1])
                 - (current[1] - before[1]) * (after[0] - current[0]))
        if abs(value) > 1.0e-9:
            signs.append(value > 0.0)
    return bool(signs) and all(value == signs[0] for value in signs)


def _point_on_segment(point: Point, a: Point, b: Point) -> Optional[float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 1.0e-18:
        return None
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length_squared
    projected = (a[0] + t * dx, a[1] + t * dy)
    if (-1.0e-8 <= t <= 1.0 + 1.0e-8
            and math.hypot(point[0] - projected[0], point[1] - projected[1]) <= 1.0e-7):
        return min(1.0, max(0.0, t))
    return None


def _split_lineage(source: Mapping[str, Any], children: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for source_edge, source_record in sorted(source["edges"].items()):
        a = tuple(float(value) for value in source_record["points"][0])
        b = tuple(float(value) for value in source_record["points"][1])
        targets = []
        for child in children:
            for target_edge, target_record in sorted(child["edges"].items()):
                p = tuple(float(value) for value in target_record["points"][0])
                q = tuple(float(value) for value in target_record["points"][1])
                t0, t1 = _point_on_segment(p, a, b), _point_on_segment(q, a, b)
                if t0 is None or t1 is None or abs(t0 - t1) <= 1.0e-9:
                    continue
                lo, hi = sorted((t0, t1))
                targets.append({
                    "target": f"{child['piece_id']}/{target_edge}",
                    "source_t_range": [round(lo, 9), round(hi, 9)],
                    "relation": ("FULL_EDGE_PRESERVED"
                                 if lo <= 1.0e-8 and hi >= 1.0 - 1.0e-8
                                 else "PARTIAL_EDGE_REMAP"),
                })
        rows.append({
            "source": f"{source['piece_id']}/{source_edge}",
            "targets": sorted(targets, key=lambda row: (row["source_t_range"], row["target"])),
        })
    return rows


def _full_remap(lineage: Sequence[Mapping[str, Any]], source_address: str) -> Optional[str]:
    row = next((value for value in lineage if value.get("source") == source_address), None)
    if row is None:
        return None
    full = [target.get("target") for target in row.get("targets", [])
            if target.get("relation") == "FULL_EDGE_PRESERVED"]
    return str(full[0]) if len(full) == 1 else None


def _split_piece(source: Mapping[str, Any], parameters: Mapping[str, Any],
                 operation_id: str, known_ids: Iterable[str]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if source.get("inner_cutouts"):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_INNER_CONTOUR_LINEAGE",
            f"{operation_id} cannot split a piece with inner contours until each contour is assigned to one child")
    if source.get("transforms"):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_TRANSFORM_ADDRESS_REMAP",
            f"{operation_id} cannot split a piece with prior transforms until their interior/edge addresses are remapped")
    line = parameters.get("line")
    piece_ids = parameters.get("new_piece_ids")
    try:
        if (not isinstance(line, Sequence) or isinstance(line, (str, bytes))
                or len(line) != 2):
            raise ValueError("line must contain two points")
        line_a = (float(line[0][0]), float(line[0][1]))
        line_b = (float(line[1][0]), float(line[1][1]))
    except (TypeError, ValueError, IndexError, OverflowError):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_LINE",
            f"{operation_id} needs line [[x1,y1],[x2,y2]] with finite coordinates")
    if (not all(math.isfinite(value) for value in line_a + line_b)
            or math.hypot(line_b[0] - line_a[0], line_b[1] - line_a[1]) <= 1.0e-9):
        return None, None, _unknown("UNKNOWN_SPLIT_LINE", f"{operation_id} split line is degenerate")
    if (not isinstance(piece_ids, Mapping)
            or set(piece_ids) != {"negative", "positive"}):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_PIECE_IDS",
            f"{operation_id} needs new_piece_ids with negative and positive names")
    negative_id, positive_id = piece_ids.get("negative"), piece_ids.get("positive")
    known = set(known_ids)
    if (not isinstance(negative_id, str) or not negative_id.strip()
            or not isinstance(positive_id, str) or not positive_id.strip()
            or negative_id == positive_id or negative_id in known or positive_id in known):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_PIECE_IDS",
            f"{operation_id} split piece ids must be new, unique, non-empty strings")
    source_points = [tuple(float(value) for value in point) for point in source["outline"]]
    if not _is_convex(source_points):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_NONCONVEX_PANEL",
            f"{operation_id} only compiles a single straight split of a convex panel")
    sides = [_line_side(line_a, line_b, point) for point in source_points]
    if any(abs(value) <= 1.0e-9 for value in sides):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_THROUGH_VERTEX",
            f"{operation_id} line touches an existing vertex and would make edge identity ambiguous")
    if not any(value < 0.0 for value in sides) or not any(value > 0.0 for value in sides):
        return None, None, _unknown(
            "UNKNOWN_SPLIT_DOES_NOT_CROSS_PANEL",
            f"{operation_id} line must cross the panel interior")
    negative_points = _clip_half_plane(source_points, line_a, line_b, False)
    positive_points = _clip_half_plane(source_points, line_a, line_b, True)
    for points in (negative_points, positive_points):
        polygon_error = _stable_polygon(points, operation_id)
        if polygon_error:
            return None, None, polygon_error
    negative = _derived_piece(
        source, str(negative_id), negative_points, operation_id=operation_id,
        method="explicit straight-line convex split", cut_count=source["cut_count"],
        side="negative", detail={"line": [list(line_a), list(line_b)]})
    positive = _derived_piece(
        source, str(positive_id), positive_points, operation_id=operation_id,
        method="explicit straight-line convex split", cut_count=source["cut_count"],
        side="positive", detail={"line": [list(line_a), list(line_b)]})
    children = [negative, positive]
    lineage = _split_lineage(source, children)
    split_edges = []
    for child in children:
        matches = []
        for edge, record in child["edges"].items():
            p = tuple(float(value) for value in record["points"][0])
            q = tuple(float(value) for value in record["points"][1])
            if (abs(_line_side(line_a, line_b, p)) <= 1.0e-7
                    and abs(_line_side(line_a, line_b, q)) <= 1.0e-7):
                matches.append(edge)
        if len(matches) != 1:
            return None, None, _unknown(
                "UNKNOWN_SPLIT_EDGE_IDENTITY",
                f"{operation_id} did not produce one unambiguous split edge per child")
        split_edges.append(matches[0])
    record = {
        "operation_id": operation_id,
        "kind": "SPLIT",
        "state": "PROPOSED",
        "source_piece_id": source["piece_id"],
        "new_piece_ids": {"negative": negative_id, "positive": positive_id},
        "line": [list(line_a), list(line_b)],
        "source_edge_lineage": lineage,
        "address_remap": copy.deepcopy(lineage),
        "generated_join": {
            "a": {"piece_id": negative_id, "edge": split_edges[0]},
            "b": {"piece_id": positive_id, "edge": split_edges[1]},
        },
        "before_digest": _digest(source),
        "after_digests": [_digest(child) for child in children],
    }
    return children, record, None


def _apply_unary(piece: Dict[str, Any], edge: str,
                 operation: Mapping[str, Any]) -> Dict[str, Any]:
    kind = str(operation.get("kind", ""))
    p = operation.get("parameters", {})
    request: Dict[str, Any] = {"kind": kind, "edge": edge}
    if isinstance(p, Mapping):
        request.update(copy.deepcopy(dict(p)))
    result = _transforms.apply(piece, request)
    if result.get("verdict") != ANSWER:
        return result
    after = copy.deepcopy(result["after"])
    # Keep compiler identity fields that the transform intentionally ignores.
    for name in ("node_id", "primitive_kind", "layer", "role", "cut_count",
                 "grain", "attributes", "provenance"):
        after[name] = copy.deepcopy(piece[name])
    _refresh_piece(after)
    piece.clear()
    piece.update(after)
    return {"verdict": ANSWER, "record": result["transform"]}


def _attached_to_ids(node: Mapping[str, Any]) -> Tuple[str, ...]:
    attributes = node.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    raw = attributes.get("attached_to")
    if isinstance(raw, str) and raw.strip():
        values = (raw.strip(),)
    elif (isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
          and all(isinstance(value, str) and value.strip() for value in raw)):
        values = tuple(str(value).strip() for value in raw)
    else:
        values = ()
    return values


def _sleeve_parent_ids(node: Mapping[str, Any],
                       sleeve_ids: set[str]) -> Tuple[str, ...]:
    return tuple(value for value in _attached_to_ids(node)
                 if value in sleeve_ids)


def _select_bodice_for_sleeves(
    bodies: Sequence[Mapping[str, Any]],
    sleeves: Sequence[Mapping[str, Any]],
) -> Tuple[Optional[Mapping[str, Any]], Optional[Dict[str, Any]]]:
    """Select one layered BODY_SHELL without guessing across graph addresses.

    A layered look may legitimately contain an under-bodice and an outer
    bodice.  The set-in sleeve bridge operates on one physical armhole set, so
    the root sleeve must either name that body explicitly or resolve to exactly
    one body by the typed ``garment_unit`` + ``layer`` address.  Merely taking
    the first BODY_SHELL made results depend on model/list order.
    """
    if len(bodies) == 1:
        return bodies[0], None

    body_by_id = {str(node["node_id"]): node for node in bodies}
    body_ids = set(body_by_id)
    sleeve_ids = {str(node["node_id"]) for node in sleeves}
    explicit: List[Tuple[str, str]] = []
    unknown: List[Tuple[str, str]] = []
    for sleeve in sleeves:
        sleeve_id = str(sleeve["node_id"])
        parents = _attached_to_ids(sleeve)
        body_parents = [value for value in parents if value in body_ids]
        sleeve_parents = [value for value in parents if value in sleeve_ids]
        if len(body_parents) > 1 or (body_parents and sleeve_parents):
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_AMBIGUOUS",
                "a sleeve may name one BODY_SHELL parent or one sleeve parent, not both",
                sleeve_node_id=sleeve_id,
                attached_to=list(parents),
                body_shell_nodes=sorted(body_ids))
        if body_parents:
            explicit.append((sleeve_id, body_parents[0]))
        elif parents and not sleeve_parents:
            unknown.extend((sleeve_id, value) for value in parents)

    if unknown:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_UNKNOWN",
            "a root sleeve names an attached_to target that is not a BODY_SHELL or sleeve node",
            unknown_parent_addresses=[
                {"sleeve_node_id": sleeve_id, "parent_node_id": parent_id}
                for sleeve_id, parent_id in sorted(unknown)
            ],
            body_shell_nodes=sorted(body_ids))

    explicit_body_ids = sorted({body_id for _, body_id in explicit})
    if len(explicit_body_ids) > 1:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_AMBIGUOUS",
            "root sleeves name more than one BODY_SHELL parent",
            explicit_body_parents=[
                {"sleeve_node_id": sleeve_id, "body_node_id": body_id}
                for sleeve_id, body_id in sorted(explicit)
            ],
            body_shell_nodes=sorted(body_ids))
    if len(explicit_body_ids) == 1:
        selected = body_by_id[explicit_body_ids[0]]
        selected_attributes = selected.get("attributes", {})
        selected_attributes = (selected_attributes
                               if isinstance(selected_attributes, Mapping) else {})
        selected_unit = str(selected_attributes.get("garment_unit", "")).strip()
        selected_layer = int(selected.get("layer", 0))
        for sleeve_id, body_id in explicit:
            sleeve = next(row for row in sleeves
                          if str(row["node_id"]) == sleeve_id)
            attributes = sleeve.get("attributes", {})
            attributes = attributes if isinstance(attributes, Mapping) else {}
            sleeve_unit = str(attributes.get("garment_unit", "")).strip()
            if selected_unit and sleeve_unit and selected_unit != sleeve_unit:
                return None, _unknown(
                    "UNKNOWN_BODICE_SLEEVE_GARMENT_UNIT_MISMATCH",
                    "an explicitly attached sleeve and BODY_SHELL have different garment_unit values",
                    sleeve_node_id=sleeve_id, body_node_id=body_id,
                    sleeve_garment_unit=sleeve_unit,
                    body_garment_unit=selected_unit)
            sleeve_layer = int(sleeve.get("layer", 0))
            if sleeve_layer != selected_layer:
                return None, _unknown(
                    "UNKNOWN_BODICE_SLEEVE_BODY_LAYER_MISMATCH",
                    "an attached sleeve and its selected BODY_SHELL must share one construction layer",
                    sleeve_node_id=sleeve_id, body_node_id=body_id,
                    sleeve_layer=sleeve_layer, body_layer=selected_layer)
        return selected, None

    # No explicit body edge exists.  Only an exact typed address shared by all
    # declaration-level root sleeves may select the body.  Descendant sleeves
    # (attached to another sleeve) do not vote on the bodice address.
    roots = [node for node in sleeves
             if not _sleeve_parent_ids(node, sleeve_ids)]
    eligible = set(body_ids)
    for sleeve in roots:
        attributes = sleeve.get("attributes", {})
        attributes = attributes if isinstance(attributes, Mapping) else {}
        unit = str(attributes.get("garment_unit", "")).strip()
        layer = int(sleeve.get("layer", 0))
        matches = {
            body_id for body_id, body in body_by_id.items()
            if int(body.get("layer", 0)) == layer
            and (not unit or str((body.get("attributes", {})
                                  if isinstance(body.get("attributes", {}), Mapping)
                                  else {}).get("garment_unit", "")).strip() == unit)
        }
        eligible &= matches
    if len(eligible) == 1:
        return body_by_id[next(iter(eligible))], None
    return None, _unknown(
        "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_AMBIGUOUS",
        "multiple BODY_SHELL nodes require one explicit sleeve attached_to address or one exact garment_unit/layer match",
        body_shell_nodes=sorted(body_ids),
        root_sleeve_nodes=sorted(str(node["node_id"]) for node in roots),
        candidate_body_nodes=sorted(eligible),
        required_address_fields=["attached_to", "garment_unit", "layer"])


def _sleeve_port(node: Mapping[str, Any], port_id: str) -> Optional[Mapping[str, Any]]:
    return next((port for port in node.get("ports", [])
                 if isinstance(port, Mapping)
                 and str(port.get("port_id", "")) == port_id), None)


def _descendant_sleeve_piece(
    node: Mapping[str, Any], *, side: str, garment_unit: str,
    relation_kind: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    dimensions = node.get("dimensions", {})
    try:
        length = float(dimensions["length_cm"])
        upper = float(dimensions["upper_circumference_cm"])
        cuff = float(dimensions["cuff_circumference_cm"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_DESCENDANT_DIMENSIONS",
            f"{node.get('node_id')} cannot produce a side-specific sleeve piece: {exc}")
    if not all(_positive(value) for value in (length, upper, cuff)):
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_DESCENDANT_DIMENSIONS",
            f"{node.get('node_id')} sleeve dimensions must be finite and positive")
    node_id = str(node["node_id"])
    outline = _trapezoid(length, upper, cuff)
    piece = _expanded_piece(
        node, f"{node_id}:{side}", outline,
        ["cuff", "underarm:front", "upper", "underarm:back"],
        role=("joined_sleeve_segment_" if relation_kind == "JOIN"
              else "layered_sleeve_") + side,
        source_draft_piece="deterministic sleeve descendant trapezoid",
        garment_unit=garment_unit)
    piece["attributes"].update({
        "derived_side": side,
        "physical_instance": f"{node_id}:{side}",
        "source_quantity_expanded": True,
        "sleeve_parent_relation": relation_kind,
    })
    piece["provenance"]["instance_lineage"] = {
        "source_node_id": node_id,
        "side": side,
        "cut_count": 1,
        "parent_relation_kind": relation_kind,
    }
    return piece, None


def _extend_bodice_sleeve_bridge(
    graph: Mapping[str, Any], body: Mapping[str, Any],
    sleeves: Sequence[Mapping[str, Any]], root: Mapping[str, Any],
    relations: Mapping[str, Mapping[str, Any]], bridge: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Add descendant sleeve instances and expand every relation by side."""
    sleeve_by_id = {str(node["node_id"]): node for node in sleeves}
    side_map: Dict[str, Dict[str, Dict[str, Any]]] = {
        str(node_id): {str(side): piece for side, piece in pieces.items()}
        for node_id, pieces in bridge.get("side_piece_map", {}).items()
        if isinstance(pieces, Mapping)
    }
    sides_by_node: Dict[str, Tuple[str, ...]] = {}
    for node in sleeves:
        sides, error = _sleeve_instance_sides(node)
        if error or sides is None:
            return error
        sides_by_node[str(node["node_id"])] = sides

    body_attributes = body.get("attributes", {})
    body_attributes = body_attributes if isinstance(body_attributes, Mapping) else {}
    garment_unit = str(body_attributes.get("garment_unit", "candidate")).strip()
    for node in sleeves:
        attributes = node.get("attributes", {})
        attributes = attributes if isinstance(attributes, Mapping) else {}
        node_unit = attributes.get("garment_unit")
        if node_unit is not None and str(node_unit).strip() != garment_unit:
            return _unknown(
                "UNKNOWN_BODICE_SLEEVE_GARMENT_UNIT_MISMATCH",
                "all sleeves in one attachment chain must name the bodice garment_unit",
                body_garment_unit=garment_unit,
                sleeve_node_id=node.get("node_id"),
                sleeve_garment_unit=str(node_unit).strip())

    pending = set(relations)
    ordered_children: List[str] = []
    while pending:
        ready = sorted(
            child_id for child_id in pending
            if str(relations[child_id]["parent_id"]) in side_map)
        if not ready:
            return _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_CYCLE",
                "descendant sleeves do not form one acyclic chain rooted at the bodice sleeve",
                root_sleeve_node_id=root.get("node_id"),
                unresolved_sleeve_nodes=sorted(pending))
        for child_id in ready:
            relation = relations[child_id]
            parent_id = str(relation["parent_id"])
            child_sides = sides_by_node[child_id]
            parent_sides = sides_by_node[parent_id]
            missing_sides = sorted(set(child_sides) - set(parent_sides))
            if missing_sides:
                return _unknown(
                    "UNKNOWN_BODICE_SLEEVE_RELATION_SIDE_MISMATCH",
                    "a sleeve relation cannot select a side absent from its parent",
                    child_node_id=child_id, parent_node_id=parent_id,
                    child_sides=list(child_sides),
                    parent_sides=list(parent_sides),
                    missing_sides=missing_sides,
                    operation_id=relation["operation"]["operation_id"])
            relation_kind = str(relation["operation"]["kind"])
            generated: Dict[str, Dict[str, Any]] = {}
            for side in child_sides:
                piece, error = _descendant_sleeve_piece(
                    sleeve_by_id[child_id], side=side,
                    garment_unit=garment_unit, relation_kind=relation_kind)
                if error or piece is None:
                    return error
                generated[side] = piece
            side_map[child_id] = generated
            bridge["pieces_by_node"][child_id] = [
                generated[side] for side in child_sides]
            bridge["canonical_port_piece"][child_id] = generated[child_sides[0]]
            ordered_children.append(child_id)
            pending.remove(child_id)

    relation_lineage: List[Dict[str, Any]] = []
    for child_id in ordered_children:
        relation = relations[child_id]
        operation = relation["operation"]
        parent_id = str(relation["parent_id"])
        source = operation["source"]
        target = operation["target"]
        source_id, target_id = str(source["node_id"]), str(target["node_id"])
        source_port = _sleeve_port(
            sleeve_by_id[source_id], str(source["port_id"]))
        target_port = _sleeve_port(
            sleeve_by_id[target_id], str(target["port_id"]))
        if source_port is None or target_port is None:
            return _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_PORT",
                f"{operation['operation_id']} does not resolve to two sleeve ports",
                operation_id=operation["operation_id"])
        relation_kind = str(operation["kind"])
        for side in sides_by_node[child_id]:
            source_piece = side_map[source_id].get(side)
            target_piece = side_map[target_id].get(side)
            if source_piece is None or target_piece is None:
                return _unknown(
                    "UNKNOWN_BODICE_SLEEVE_RELATION_SIDE_MISMATCH",
                    f"{operation['operation_id']} cannot resolve side {side}",
                    operation_id=operation["operation_id"], side=side,
                    source_node_id=source_id, target_node_id=target_id)
            if relation_kind == "JOIN":
                # The child upper boundary is sewn to the parent cuff.  Port
                # ids include the other node id (for example
                # ``...-sleeve-lower``), so word-based routing can mistake
                # that name for a "lower" edge and select a sleeve-cap segment
                # on the parent. Address the compiled semantic groups instead.
                source_boundary = ("upper" if source_id == child_id else "cuff")
                target_boundary = ("upper" if target_id == child_id else "cuff")
                source_edge, source_error = _one_group_edge(
                    source_piece, source_boundary,
                    operation_id=str(operation["operation_id"]))
                target_edge, target_error = _one_group_edge(
                    target_piece, target_boundary,
                    operation_id=str(operation["operation_id"]))
                if source_error is not None:
                    return source_error
                if target_error is not None:
                    return target_error
                assert source_edge is not None and target_edge is not None
            else:
                source_edge = _port_edge(source_port, source_piece)
                target_edge = _port_edge(target_port, target_piece)
            instance_id = f"{operation['operation_id']}:{side}"
            lineage = {
                "source_operation_id": operation["operation_id"],
                "relation_kind": relation_kind,
                "side": side,
                "source": {
                    "node_id": source_id, "port_id": source["port_id"],
                    "piece_id": source_piece["piece_id"], "edge": source_edge,
                },
                "target": {
                    "node_id": target_id, "port_id": target["port_id"],
                    "piece_id": target_piece["piece_id"], "edge": target_edge,
                },
                "state": "PROPOSED",
            }
            row = {
                "operation_id": instance_id,
                "source_operation_id": operation["operation_id"],
                "kind": relation_kind,
                "construction_role": (
                    "JOIN_SLEEVE_SEGMENTS" if relation_kind == "JOIN"
                    else "LAYER_SLEEVE_INSTANCE"),
                "relation_side": side,
                "a": {"piece_id": source_piece["piece_id"],
                      "edge": source_edge},
                "b": {"piece_id": target_piece["piece_id"],
                      "edge": target_edge},
                "declared_a_cm": float(source_port["length_cm"]),
                "declared_b_cm": float(target_port["length_cm"]),
                "pattern_lineage": copy.deepcopy(lineage),
                "state": "PROPOSED",
                "manufacturing_validated": False,
            }
            if relation_kind == "JOIN":
                bridge["seams"].append(row)
            else:
                row.update({
                    "seam_join_created": False,
                    "address_semantics": "NON_SEWING_LAYER_ANCHOR",
                })
                bridge.setdefault("layers", []).append(row)
            relation_lineage.append(lineage)

    bridge["side_piece_map"] = side_map
    bridge["consumed_operation_ids"] = {
        str(relation["operation"]["operation_id"])
        for relation in relations.values()
    }
    expansion = bridge["expansion"]
    expansion["source_nodes"] = [str(body["node_id"])] + [
        str(root["node_id"]), *ordered_children]
    expansion["generated_pieces"] = [
        piece["piece_id"]
        for node_id in expansion["source_nodes"]
        for piece in bridge["pieces_by_node"].get(node_id, [])]
    expansion["lineage"].extend({
        "source": f"node/{child_id}",
        "target": side_map[child_id][side]["piece_id"],
        "relation": f"EXPANDED_{side.upper()}_SLEEVE_DESCENDANT",
        "side": side,
        "cut_count": 1,
    } for child_id in ordered_children for side in sides_by_node[child_id])
    expansion["sleeve_relation_lineage"] = relation_lineage
    expansion["consumed_structure_operations"] = sorted(
        bridge["consumed_operation_ids"])
    expansion["multi_sleeve_compilation"] = True
    return None


def _bridge_candidates(graph: Mapping[str, Any], *,
                       candidate_state: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    bodies = [node for node in graph["nodes"] if node["kind"] == "BODY_SHELL"]
    sleeves = [node for node in graph["nodes"] if node["kind"] == "SLEEVE"]
    if not bodies or not sleeves:
        return None, None
    body, body_error = _select_bodice_for_sleeves(bodies, sleeves)
    if body_error or body is None:
        return None, body_error or _unknown(
            "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_AMBIGUOUS",
            "the set-in sleeve bridge could not select one BODY_SHELL")
    # Downstream bridge code intentionally operates on one physical armhole
    # owner.  Other BODY_SHELL nodes remain ordinary independent/layered pieces
    # and are compiled later; they are not dropped from the candidate.
    bodies = [body]
    sleeve_by_id = {str(node["node_id"]): node for node in sleeves}
    sleeve_ids = set(sleeve_by_id)
    # A typed gather between two sleeve segments has one cut-length source
    # boundary and one shorter, finished parent boundary.  The set-in bridge
    # expands sleeves by physical side before the generic transform compiler
    # runs, but it does not yet transform two side-specific source outlines in
    # one operation.  Deliberately defer the complete bridge so the legacy
    # compiler can retain the bilateral cut-count representation, apply the
    # addressed GATHER once to the source pattern, and let the sewing planner
    # expand the resulting construction operation by side.  This is explicit
    # REVIEW provenance, not a silent fallback to an ordinary LAYER.
    sleeve_segment_gathers: List[Mapping[str, Any]] = []
    for operation in graph.get("operations", []):
        source = operation.get("source", {})
        target = operation.get("target", {})
        if not isinstance(source, Mapping) or not isinstance(target, Mapping):
            continue
        source_id = str(source.get("node_id", ""))
        target_id = str(target.get("node_id", ""))
        if (source_id not in sleeve_ids or target_id not in sleeve_ids
                or str(operation.get("kind", "")) != "GATHER"):
            continue
        parameters = operation.get("parameters", {})
        parameters = parameters if isinstance(parameters, Mapping) else {}
        role = str(parameters.get(
            "construction_role", operation.get("construction_role", ""),
        )).strip().upper()
        if role != "GATHER_SLEEVE_SEGMENTS":
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_KIND",
                "SLEEVE-to-SLEEVE GATHER must be typed GATHER_SLEEVE_SEGMENTS",
                operation_id=operation.get("operation_id"),
                operation_kind=operation.get("kind"),
                construction_role=role,
                required_construction_role="GATHER_SLEEVE_SEGMENTS")
        source_parents = _sleeve_parent_ids(sleeve_by_id[source_id], sleeve_ids)
        if source_parents and target_id not in source_parents:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_PARENT_MISMATCH",
                "the gathered source sleeve does not name the target sleeve as its parent",
                operation_id=operation.get("operation_id"),
                child_node_id=source_id, parent_node_id=target_id,
                source_attached_to=list(source_parents))
        sleeve_segment_gathers.append(operation)
    if sleeve_segment_gathers:
        operation_ids = sorted(str(operation["operation_id"])
                               for operation in sleeve_segment_gathers)
        return {
            "deferred": True,
            "pieces_by_node": {},
            "seams": [],
            "layers": [],
            "sleeve_balance": [],
            "canonical_port_piece": {},
            "consumed_operation_ids": set(),
            "expansion": {
                "kind": "BODICE_SET_IN_SLEEVE_BRIDGE",
                "state": "REVIEW_DEFERRED",
                "source_nodes": sorted({str(bodies[0]["node_id"]), *sleeve_ids}),
                "generated_pieces": [],
                "blocking_operations": operation_ids,
                "why": (
                    "typed sleeve-segment GATHER is compiled by the address-preserving "
                    "legacy pattern transform and expanded by physical side in the sewing plan"
                ),
                "legacy_wrap_compiler_used": True,
                "typed_sleeve_segment_gather_preserved": True,
                "target_wearer_measurements_used": False,
                "manufacturing_guarantee": False,
            },
        }, None
    relations: Dict[str, Dict[str, Any]] = {}
    for operation in graph.get("operations", []):
        source = operation.get("source", {})
        target = operation.get("target", {})
        if not isinstance(source, Mapping) or not isinstance(target, Mapping):
            continue
        source_id = str(source.get("node_id", ""))
        target_id = str(target.get("node_id", ""))
        if source_id not in sleeve_ids or target_id not in sleeve_ids:
            continue
        if str(operation.get("kind", "")) not in {"JOIN", "LAYER"}:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_KIND",
                "SLEEVE-to-SLEEVE relations must be explicit JOIN or LAYER operations",
                operation_id=operation.get("operation_id"),
                operation_kind=operation.get("kind"))
        source_parents = _sleeve_parent_ids(sleeve_by_id[source_id], sleeve_ids)
        target_parents = _sleeve_parent_ids(sleeve_by_id[target_id], sleeve_ids)
        if target_id in source_parents and source_id in target_parents:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_CYCLE",
                "two sleeves declare each other as parent",
                sleeve_nodes=sorted((source_id, target_id)))
        if target_id in source_parents:
            child_id, parent_id = source_id, target_id
        elif source_id in target_parents:
            child_id, parent_id = target_id, source_id
        elif source_parents or target_parents:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_PARENT_MISMATCH",
                "operation endpoints disagree with the sleeve attached_to address",
                operation_id=operation.get("operation_id"),
                source_attached_to=list(source_parents),
                target_attached_to=list(target_parents))
        else:
            # garment.structure.v1 uses source=child, target=parent for the
            # topology-generated sleeve relation.  Without attached_to this
            # explicit operation direction is the only available authority.
            child_id, parent_id = source_id, target_id
        if child_id in relations:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_CARDINALITY",
                "a descendant sleeve must have exactly one parent relation",
                child_node_id=child_id,
                operation_ids=[relations[child_id]["operation"]["operation_id"],
                               operation.get("operation_id")])
        relations[child_id] = {
            "child_id": child_id, "parent_id": parent_id,
            "operation": operation,
        }

    for node_id, node in sleeve_by_id.items():
        declared = _sleeve_parent_ids(node, sleeve_ids)
        if len(declared) > 1:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_CARDINALITY",
                "a descendant sleeve may name only one sleeve parent",
                child_node_id=node_id, parent_node_ids=list(declared))
        if declared and (node_id not in relations
                         or relations[node_id]["parent_id"] != declared[0]):
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_RELATION_MISSING",
                "attached_to names a sleeve parent but no exact JOIN/LAYER operation binds it",
                child_node_id=node_id, parent_node_id=declared[0])
    roots = sorted(sleeve_ids - set(relations))
    if len(roots) != 1:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_BRIDGE_CARDINALITY",
            "one BODY_SHELL may have exactly one root SLEEVE source plus descendants",
            body_shell_nodes=[bodies[0]["node_id"]],
            root_sleeve_nodes=roots,
            sleeve_nodes=sorted(sleeve_ids))
    root = sleeve_by_id[roots[0]]
    special_ids = {str(bodies[0]["node_id"]), *sleeve_ids}
    incompatible = {"SPLIT", "MIRROR", "ASYMMETRY", "CUTOUT",
                    "PLEAT", "DART", "FOLD", "GATHER"}
    # A GATHER ending on a primitive-level body port denotes one continuous
    # circumference, while the bridge would replace it with front/back edge
    # sets.  A sleeve target is different when the source part carries an
    # explicit left/right instance address: the bridge has an exact matching
    # sleeve piece and can preserve that side through its port remap.  Defer
    # only body gathers and sleeve gathers without one unambiguous physical
    # side.  This prevents a left cuff ruffle from forcing the entire bodice
    # and sleeve back to the lineage-losing legacy wrap compiler.
    nodes_by_id = {str(node["node_id"]): node for node in graph["nodes"]}
    unresolved_external_gathers: List[Mapping[str, Any]] = []
    side_bound_external_gathers: List[Dict[str, str]] = []
    for operation in graph.get("operations", []):
        source = operation.get("source", {})
        target = operation.get("target", {})
        if (str(operation.get("kind", "")) != "GATHER"
                or not isinstance(source, Mapping)
                or not isinstance(target, Mapping)):
            continue
        source_id = str(source.get("node_id", ""))
        target_id = str(target.get("node_id", ""))
        if target_id not in special_ids or source_id in special_ids:
            continue
        source_node = nodes_by_id.get(source_id, {})
        source_attributes = source_node.get("attributes", {})
        source_attributes = (source_attributes
                             if isinstance(source_attributes, Mapping) else {})
        side = str(source_attributes.get("side", "")).strip().lower()
        parameters = operation.get("parameters", {})
        parameters = parameters if isinstance(parameters, Mapping) else {}
        parameter_side = str(parameters.get("relation_side", "")).strip().lower()
        if parameter_side in {"left", "right"}:
            side = parameter_side
        if target_id in sleeve_ids and side in {"left", "right"}:
            side_bound_external_gathers.append({
                "operation_id": str(operation.get("operation_id", "")),
                "source_node_id": source_id,
                "target_node_id": target_id,
                "side": side,
            })
            continue
        unresolved_external_gathers.append(operation)
    if unresolved_external_gathers:
        operation_ids = sorted(str(operation["operation_id"])
                               for operation in unresolved_external_gathers)
        return {
            "deferred": True,
            "pieces_by_node": {},
            "seams": [],
            "sleeve_balance": [],
            "canonical_port_piece": {},
            "expansion": {
                "kind": "BODICE_SET_IN_SLEEVE_BRIDGE",
                "state": "REVIEW_DEFERRED",
                "source_nodes": sorted(special_ids),
                "generated_pieces": [],
                "blocking_operations": operation_ids,
                "why": (
                    "GATHER targets one circumference port; garment.structure.v1 "
                    "cannot yet bind it to an ordered front/back edge set"),
                "legacy_wrap_compiler_used": True,
                "target_wearer_measurements_used": False,
                "manufacturing_guarantee": False,
            },
        }, None
    for operation in graph.get("operations", []):
        source = operation.get("source", {})
        target = operation.get("target", {})
        operation_kind = str(operation.get("kind", ""))
        parameters = operation.get("parameters", {})
        # The image bridge supplies an exact front-boundary digest and an
        # already projected polygon.  That is sufficient to address the front
        # bodice specifically without claiming that the line's cutout meaning
        # was observed.  Other primitive-level CUTOUTs remain ambiguous.
        explicit_front_cutout = (
            operation_kind == "CUTOUT"
            and str(source.get("node_id", "")) == str(bodies[0]["node_id"])
            and isinstance(parameters, Mapping)
            and isinstance(parameters.get("source_front_boundary_digest"), str)
            and bool(parameters.get("source_front_boundary_digest", "").strip())
            and parameters.get("state") == "PROPOSED")
        explicit_surface_modifier = _surface_modifiers.has_surface_target(
            operation)
        source_conflict = (str(source.get("node_id", "")) in special_ids
                           and operation_kind in incompatible
                           and not explicit_front_cutout
                           and not explicit_surface_modifier)
        if source_conflict:
            return None, _unknown(
                "UNKNOWN_BODICE_SLEEVE_BRIDGE_OPERATION_CONFLICT",
                f"{operation['operation_id']} addresses a primitive that expands to multiple real pieces",
                operation_id=operation["operation_id"],
                operation_kind=operation["kind"],
                source_node_id=source.get("node_id"),
                target_node_id=(target.get("node_id")
                                if isinstance(target, Mapping) else None),
                why_typed=(
                    "the operation must name an expanded piece and remapped eN boundary; "
                    "silently choosing front/back or left/right would break lineage"))
    bridge, error = _bodice_sleeve_bridge(
        bodies[0], root, candidate_state=candidate_state)
    if error or bridge is None:
        return bridge, error
    if side_bound_external_gathers:
        bridge["expansion"]["side_bound_external_gathers"] = copy.deepcopy(
            side_bound_external_gathers)
        bridge["expansion"]["external_gather_side_inferred"] = False
    extension_error = _extend_bodice_sleeve_bridge(
        graph, bodies[0], sleeves, root, relations, bridge)
    if extension_error:
        return None, extension_error
    declared_ids = {str(operation["operation_id"])
                    for operation in graph.get("operations", [])}
    generated_ids = {
        str(row["operation_id"])
        for row in list(bridge["seams"]) + list(bridge.get("layers", []))}
    collisions = sorted(declared_ids & generated_ids)
    if collisions:
        return None, _unknown(
            "UNKNOWN_BODICE_SLEEVE_BRIDGE_OPERATION_ID_COLLISION",
            "generated bridge seam ids collide with declared structure operations",
            operation_ids=collisions)
    return bridge, None


def _trouser_attached_to(node: Mapping[str, Any]) -> Tuple[str, ...]:
    attributes = node.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    value = attributes.get("attached_to")
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if (isinstance(value, Sequence) and not isinstance(value, (str, bytes))
            and all(isinstance(item, str) and item.strip() for item in value)):
        return tuple(str(item).strip() for item in value)
    return ()


def _trouser_side(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    return str(attributes.get("side", "")).strip().lower()


def _trouser_unit(node: Mapping[str, Any]) -> Optional[str]:
    attributes = node.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    value = attributes.get("garment_unit")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _trouser_signal(node: Mapping[str, Any]) -> bool:
    kind = str(node.get("kind", ""))
    if kind not in {"TUBE", "GUSSET"}:
        return False
    attributes = node.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    tokens = {
        str(attributes.get("shape", "")).strip().lower(),
        str(attributes.get("detail_role", "")).strip().lower(),
    }
    if kind == "GUSSET":
        return bool(tokens & {"trouser", "trousers", "trouser_gusset",
                              "crotch_gusset"})
    return (_trouser_side(node) in {"left", "right"}
            and bool(tokens & {"trouser", "trousers", "trouser_leg",
                               "pants_leg"}))


def _trouser_body_piece(body: Mapping[str, Any], segment_lengths: Sequence[float],
                        garment_unit: str) -> Dict[str, Any]:
    dimensions = body["dimensions"]
    height = float(dimensions["height_cm"])
    bottom = sum(segment_lengths)
    top = float(dimensions.get("top_circumference_cm",
                               dimensions["circumference_cm"]))
    x = -bottom / 2.0
    points: List[Point] = [(x, 0.0)]
    for length in segment_lengths:
        x += float(length)
        points.append((x, 0.0))
    points.extend(((top / 2.0, height), (-top / 2.0, height)))
    piece = _piece(body, points, role="body_wrap")
    piece_id = f"{body['node_id']}:trouser-waist"
    piece.update({"piece_id": piece_id, "name": piece_id,
                  "node_id": piece_id, "cut_count": 1})
    labels = [f"waist:{index + 1}" for index in range(len(segment_lengths))]
    labels.extend(("closure:right", "upper", "closure:left"))
    piece["edge_semantics"] = {
        f"e{index}": label for index, label in enumerate(labels)}
    piece["boundary_edge_groups"] = _edge_groups(labels)
    attributes = copy.deepcopy(dict(body.get("attributes", {})))
    attributes.update({
        "garment_unit": garment_unit,
        "source_node_id": str(body["node_id"]),
        "expanded_from_primitive": True,
        "state": "PROPOSED",
        "dimension_authority": "PROPOSED_INPUT_STRUCTURE",
        "target_wearer_measurement": False,
    })
    piece["attributes"] = attributes
    piece["provenance"] = {
        "method": "segmented BODY_SHELL waist for trouser_block bridge",
        "source_node": str(body["node_id"]),
        "state": "PROPOSED",
        "image_measurements_claimed": False,
        "corpus_used": False,
    }
    return piece


def _normalise_trouser_piece(piece: Mapping[str, Any],
                             source_node: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(piece))
    result["node_id"] = str(result["piece_id"])
    result["source_node_id"] = str(source_node["node_id"])
    result["layer"] = int(source_node.get("layer", 0))
    result["grain"] = {"direction": "parallel_to_height", "state": "PROPOSED"}
    result["transforms"] = []
    attributes = copy.deepcopy(dict(result.get("attributes", {})))
    attributes.update({
        "source_node_id": str(source_node["node_id"]),
        "candidate_specific_trouser_bridge": True,
    })
    result["attributes"] = attributes
    return result


def _rebalance_trouser_waist(piece: Dict[str, Any]) -> None:
    """Make each front/back waist edge exactly half its TUBE circumference."""
    points = [list(point) for point in piece["outline"]]
    if len(points) != 6:
        raise ValueError("trouser_block leg panel no longer has six addressed edges")
    points[3][0] = 0.0
    piece["outline"] = [[round(float(x), 6), round(float(y), 6)]
                        for x, y in points]
    semantics = copy.deepcopy(piece.get("edge_semantics", {}))
    _refresh_piece(piece)
    piece["edge_semantics"] = semantics
    for edge, semantic in semantics.items():
        if edge in piece["edges"]:
            piece["edges"][edge]["semantic"] = semantic


def _single_trouser_bridge_candidates(
    graph: Mapping[str, Any], *, candidate_state: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    nodes = list(graph.get("nodes", []))
    if not any(_trouser_signal(node) for node in nodes):
        return None, None
    drafted = _trouser_block.find_and_draft(
        graph, candidate_state="PROPOSED")
    if drafted.get("verdict") != ANSWER:
        return None, copy.deepcopy(drafted)

    tubes = [node for node in nodes if str(node.get("kind", "")) == "TUBE"]
    left = [node for node in tubes if _trouser_side(node) == "left"]
    right = [node for node in tubes if _trouser_side(node) == "right"]
    gussets = [node for node in nodes if str(node.get("kind", "")) == "GUSSET"]
    bodies = [node for node in nodes if str(node.get("kind", "")) == "BODY_SHELL"]
    if len(left) != 1 or len(right) != 1 or len(gussets) != 1:
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_CARDINALITY",
            "trouser bridge needs exactly one left leg, one right leg and one centre gusset",
            left_count=len(left), right_count=len(right),
            gusset_count=len(gussets))
    left_node, right_node, gusset = left[0], right[0], gussets[0]
    left_parents = _trouser_attached_to(left_node)
    right_parents = _trouser_attached_to(right_node)
    if not left_parents and not right_parents:
        # A candidate may contain a separate upper garment.  An unrelated
        # BODY_SHELL is not the parent of standalone trousers merely because
        # both units occur in one outfit structure graph.
        body = None
    elif (len(left_parents) == 1 and left_parents == right_parents):
        parent_id = left_parents[0]
        matches = [node for node in bodies
                   if str(node.get("node_id", "")) == parent_id]
        if len(matches) != 1:
            return None, _unknown(
                "UNKNOWN_TROUSER_BRIDGE_BODY_CARDINALITY",
                "attached trouser legs must name exactly one existing BODY_SHELL",
                parent_id=parent_id,
                body_node_ids=[node.get("node_id") for node in bodies])
        body = matches[0]
    else:
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_ATTACHMENT",
            "trouser legs must both be standalone or both name the same BODY_SHELL",
            left_attached_to=list(left_parents),
            right_attached_to=list(right_parents))
    if _trouser_side(gusset) not in {"center", "centre"}:
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_GUSSET_SIDE",
            "the trouser GUSSET must explicitly declare side=center",
            gusset_node_id=gusset.get("node_id"), side=_trouser_side(gusset))
    unit_nodes = [left_node, right_node, gusset]
    if body is not None:
        unit_nodes.insert(0, body)
    units = [_trouser_unit(node) for node in unit_nodes]
    if any(unit is None for unit in units) or len(set(units)) != 1:
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_GARMENT_UNIT",
            "both legs and GUSSET (plus BODY_SHELL when attached) must share one explicit garment_unit",
            garment_units=units)
    garment_unit = str(units[0])
    body_id = str(body["node_id"]) if body is not None else None
    left_id, right_id, gusset_id = (str(left_node["node_id"]),
                                    str(right_node["node_id"]),
                                    str(gusset["node_id"]))
    expected_leg_attachment = (body_id,) if body_id is not None else ()
    if (_trouser_attached_to(left_node) != expected_leg_attachment
            or _trouser_attached_to(right_node) != expected_leg_attachment
            or set(_trouser_attached_to(gusset)) != {left_id, right_id}):
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_ATTACHMENT",
            "attached legs must both target BODY_SHELL; standalone legs must both leave attached_to empty; GUSSET must attach to both legs",
            body_node_id=body_id,
            left_attached_to=list(_trouser_attached_to(left_node)),
            right_attached_to=list(_trouser_attached_to(right_node)),
            gusset_attached_to=list(_trouser_attached_to(gusset)))

    expected = {
        frozenset((left_id, gusset_id)): "LEFT_GUSSET",
        frozenset((right_id, gusset_id)): "RIGHT_GUSSET",
    }
    if body_id is not None:
        expected.update({
            frozenset((body_id, left_id)): "BODY_LEFT_WAIST",
            frozenset((body_id, right_id)): "BODY_RIGHT_WAIST",
        })
    special_ids = {left_id, right_id, gusset_id}
    if body_id is not None:
        special_ids.add(body_id)
    consumed: Dict[frozenset[str], str] = {}
    for operation in graph.get("operations", []):
        source = operation.get("source", {})
        target = operation.get("target", {})
        source_id = str(source.get("node_id", "")) if isinstance(source, Mapping) else ""
        target_id = str(target.get("node_id", "")) if isinstance(target, Mapping) else ""
        touches = source_id in special_ids or target_id in special_ids
        if not touches:
            continue
        # A typed surface target binds after the trouser/body primitives have
        # expanded into real pieces.  It is not one of the topology JOINs
        # consumed by this bridge and must survive to the compiler operation
        # loop below.
        if _surface_modifiers.has_surface_target(operation):
            continue
        pair = frozenset((source_id, target_id))
        if str(operation.get("kind", "")) != "JOIN" or pair not in expected:
            return None, _unknown(
                "UNKNOWN_TROUSER_BRIDGE_OPERATION_CONFLICT",
                f"{operation.get('operation_id')} ambiguously addresses an expanded trouser node",
                operation_id=operation.get("operation_id"),
                operation_kind=operation.get("kind"),
                source_node_id=source_id, target_node_id=target_id)
        if pair in consumed:
            return None, _unknown(
                "UNKNOWN_TROUSER_BRIDGE_DUPLICATE_JOIN",
                "one primitive trouser relation is declared more than once",
                relation=expected[pair],
                operation_ids=[consumed[pair], operation.get("operation_id")])
        consumed[pair] = str(operation.get("operation_id", ""))
    missing = [name for pair, name in expected.items() if pair not in consumed]
    if missing:
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_JOIN_UNRESOLVED",
            "trouser bridge requires every explicit body/leg/gusset JOIN relation",
            missing_relations=missing)

    left_circumference = float(left_node["dimensions"]["circumference_cm"])
    right_circumference = float(right_node["dimensions"]["circumference_cm"])
    leg_waist = left_circumference + right_circumference
    if body is not None:
        body_dimensions = body.get("dimensions", {})
        body_waist = float(body_dimensions.get(
            "bottom_circumference_cm",
            body_dimensions.get("waist_circumference_cm",
                                body_dimensions["circumference_cm"])))
        if abs(body_waist - leg_waist) > 0.05:
            return None, _unknown(
                "UNKNOWN_TROUSER_BRIDGE_WAIST_MISMATCH",
                "BODY_SHELL waist must equal the sum of left/right TUBE circumferences",
                body_waist_cm=body_waist, leg_waist_cm=leg_waist,
                difference_cm=round(body_waist - leg_waist, 6))

    source_nodes = {str(node["node_id"]): node
                    for node in (left_node, right_node, gusset)}
    pieces = [_normalise_trouser_piece(piece, source_nodes[str(
        piece["source_node_id"])]) for piece in drafted["pieces"]]
    pieces_by_id = {str(piece["piece_id"]): piece for piece in pieces}
    for piece in pieces:
        if piece.get("panel") in {"front", "back"}:
            try:
                _rebalance_trouser_waist(piece)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                return None, _unknown(
                    "UNKNOWN_TROUSER_BRIDGE_WAIST_GEOMETRY",
                    f"cannot address trouser waist geometry: {exc}")

    waist_targets = [
        pieces_by_id[f"{left_id}:front"],
        pieces_by_id[f"{left_id}:back"],
        pieces_by_id[f"{right_id}:front"],
        pieces_by_id[f"{right_id}:back"],
    ]
    segment_lengths = [left_circumference / 2.0,
                       left_circumference / 2.0,
                       right_circumference / 2.0,
                       right_circumference / 2.0]
    seams = copy.deepcopy(drafted["seams"])
    body_piece: Optional[Dict[str, Any]] = None
    if body is not None:
        body_piece = _trouser_body_piece(body, segment_lengths, garment_unit)
        seams.append(_bridge_seam(
            "trouser-body-closure", body_piece, "e4", body_piece, "e6",
            role="BODY_CLOSURE", group_id="trouser-body-closure"))
        for index, (target, length) in enumerate(zip(waist_targets, segment_lengths)):
            actual = float(target["edges"]["e2"]["length"])
            if abs(actual - length) > 1.0e-5:
                return None, _unknown(
                    "UNKNOWN_TROUSER_BRIDGE_PANEL_WAIST_BALANCE",
                    "expanded leg panel waist does not match its BODY segment",
                    piece_id=target["piece_id"], expected_cm=length,
                    actual_cm=actual)
            seams.append(_bridge_seam(
                f"trouser-waist-{index + 1}", body_piece, f"e{index}",
                target, "e2", role="WAIST_JOIN",
                group_id="trouser-waist"))

    declared_ids = {str(operation["operation_id"])
                    for operation in graph.get("operations", [])}
    generated_ids = {str(seam["operation_id"]) for seam in seams}
    collisions = sorted(declared_ids & generated_ids)
    if collisions:
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_OPERATION_ID_COLLISION",
            "generated trouser seam ids collide with structure operations",
            operation_ids=collisions)

    all_pieces = ([body_piece] if body_piece is not None else []) + pieces
    pieces_by_node = {
        left_id: [pieces_by_id[f"{left_id}:front"],
                  pieces_by_id[f"{left_id}:back"]],
        right_id: [pieces_by_id[f"{right_id}:front"],
                   pieces_by_id[f"{right_id}:back"]],
        gusset_id: [pieces_by_id[gusset_id]],
    }
    if body_id is not None and body_piece is not None:
        pieces_by_node[body_id] = [body_piece]
    expansion = {
        "kind": "TROUSER_BLOCK_BRIDGE",
        "state": "PROPOSED",
        "candidate_state_does_not_promote_dimensions": candidate_state,
        "method": ("trouser_block.find_and_draft + segmented BODY waist bridge"
                   if body_id is not None
                   else "trouser_block.find_and_draft standalone open waist"),
        "source_nodes": (([body_id] if body_id is not None else [])
                         + [left_id, right_id, gusset_id]),
        "generated_pieces": [piece["piece_id"] for piece in all_pieces],
        "generated_seams": [seam["operation_id"] for seam in seams],
        "consumed_structure_operations": [
            consumed[pair] for pair in expected],
        "trouser_block_digest": drafted["digest"],
        "geometry_records": copy.deepcopy(drafted["geometry_records"]),
        "limitations": copy.deepcopy(drafted["limitations"]),
        "target_wearer_measurements_used": False,
        "manufacturing_guarantee": False,
    }
    canonical = {
        left_id: pieces_by_id[f"{left_id}:front"],
        right_id: pieces_by_id[f"{right_id}:front"],
        gusset_id: pieces_by_id[gusset_id],
    }
    if body_id is not None and body_piece is not None:
        canonical[body_id] = body_piece
    return {
        "pieces_by_node": pieces_by_node,
        "seams": seams,
        "sleeve_balance": [],
        "canonical_port_piece": canonical,
        "consumed_operation_ids": set(consumed.values()),
        "geometry_records": copy.deepcopy(drafted["geometry_records"]),
        "expansion": expansion,
    }, None


def _trouser_bridge_candidates(
    graph: Mapping[str, Any], *, candidate_state: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Expand each explicitly addressed physical trouser layer separately.

    A candidate may contain outer trousers plus leggings, shorts over tights,
    or other independent leg garments.  Treating every left/right TUBE in the
    outfit as one global trouser block creates a false four-leg cardinality
    error.  ``garment_unit`` and primitive ``layer`` are the deterministic
    address; exact GUSSET attachments bind the third piece.  No grouping is
    inferred from a part name, image proximity, or visual similarity.
    """
    nodes = [node for node in graph.get("nodes", [])
             if isinstance(node, Mapping)]
    signalled = [node for node in nodes if _trouser_signal(node)]
    if not signalled:
        return None, None

    legs = [node for node in nodes
            if str(node.get("kind", "")) == "TUBE"
            and _trouser_signal(node)]
    all_gussets = [node for node in nodes
                   if str(node.get("kind", "")) == "GUSSET"]
    typed_gussets = [node for node in all_gussets
                     if _trouser_signal(node)]

    def group_key(node: Mapping[str, Any]) -> Tuple[Optional[str], int]:
        raw_layer = node.get("layer", 0)
        layer = (raw_layer if isinstance(raw_layer, int)
                 and not isinstance(raw_layer, bool) else 0)
        return (_trouser_unit(node), layer)

    grouped: Dict[Tuple[Optional[str], int], List[Mapping[str, Any]]] = {}
    for leg in legs:
        grouped.setdefault(group_key(leg), []).append(leg)
    if not grouped:
        return None, _unknown(
            "UNKNOWN_TROUSER_TOPOLOGY_CARDINALITY",
            "a typed trouser GUSSET has no explicitly paired left/right TUBE nodes",
            left_count=0, right_count=0,
            gusset_count=len(typed_gussets))

    node_by_id = {str(node.get("node_id", "")): node for node in nodes}
    operation_rows = [operation for operation in graph.get("operations", [])
                      if isinstance(operation, Mapping)]
    group_graphs: List[Tuple[Tuple[Optional[str], int], Dict[str, Any]]] = []
    used_gusset_ids: set[str] = set()
    body_owners: Dict[str, Tuple[Optional[str], int]] = {}
    for key in sorted(grouped, key=lambda value: (str(value[0]), value[1])):
        group_legs = grouped[key]
        left = [node for node in group_legs
                if _trouser_side(node) == "left"]
        right = [node for node in group_legs
                 if _trouser_side(node) == "right"]
        if len(left) != 1 or len(right) != 1 or len(group_legs) != 2:
            return None, _unknown(
                "UNKNOWN_TROUSER_TOPOLOGY_CARDINALITY",
                "each garment_unit/layer trouser block needs exactly one left and one right TUBE",
                garment_unit=key[0], layer=key[1],
                left_count=len(left), right_count=len(right),
                leg_node_ids=[node.get("node_id") for node in group_legs])
        leg_ids = {str(left[0]["node_id"]), str(right[0]["node_id"])}
        exact = [gusset for gusset in all_gussets
                 if set(_trouser_attached_to(gusset)) == leg_ids]
        candidates = exact or [gusset for gusset in typed_gussets
                               if group_key(gusset) == key]
        if len(candidates) != 1:
            return None, _unknown(
                "UNKNOWN_TROUSER_BRIDGE_CARDINALITY",
                "each garment_unit/layer trouser block needs exactly one explicitly bound centre GUSSET",
                garment_unit=key[0], layer=key[1],
                leg_node_ids=sorted(leg_ids),
                gusset_node_ids=[node.get("node_id") for node in candidates])
        gusset = candidates[0]
        used_gusset_ids.add(str(gusset["node_id"]))

        trouser_piece_ids = set(leg_ids) | {str(gusset["node_id"])}
        selected_ids = set(trouser_piece_ids)
        parent_ids = {
            parent for leg in group_legs
            for parent in _trouser_attached_to(leg)
        }
        selected_ids.update(parent_ids)
        for parent_id in parent_ids:
            owner = body_owners.get(parent_id)
            if owner is not None and owner != key:
                return None, _unknown(
                    "UNKNOWN_MULTI_TROUSER_SHARED_BODY",
                    "two trouser garment_unit/layer groups cannot consume the same BODY_SHELL waist",
                    body_node_id=parent_id,
                    first_group={"garment_unit": owner[0], "layer": owner[1]},
                    second_group={"garment_unit": key[0], "layer": key[1]})
            body_owners[parent_id] = key

        selected_nodes = [node_by_id[node_id] for node_id in selected_ids
                          if node_id in node_by_id]

        def relevant(operation: Mapping[str, Any]) -> bool:
            source = operation.get("source", {})
            target = operation.get("target", {})
            source_id = (str(source.get("node_id", ""))
                         if isinstance(source, Mapping) else "")
            target_id = (str(target.get("node_id", ""))
                         if isinstance(target, Mapping) else "")
            if source_id in selected_ids and target_id in selected_ids:
                return True
            # A non-surface operation that directly addresses an expanded leg
            # or gusset must be reviewed by the bridge.  BODY_SHELL may have
            # valid independent collar/overlay relations, so a one-ended body
            # touch alone is intentionally left to the generic compiler.
            if source_id in trouser_piece_ids or target_id in trouser_piece_ids:
                return True
            return (_surface_modifiers.has_surface_target(operation)
                    and (source_id in selected_ids or target_id in selected_ids))

        group_graphs.append((key, {
            "schema": graph.get("schema"),
            "nodes": selected_nodes,
            "operations": [copy.deepcopy(operation)
                           for operation in operation_rows
                           if relevant(operation)],
        }))

    orphan_typed = [gusset for gusset in typed_gussets
                    if str(gusset.get("node_id", "")) not in used_gusset_ids]
    if orphan_typed:
        return None, _unknown(
            "UNKNOWN_TROUSER_BRIDGE_CARDINALITY",
            "a typed trouser GUSSET is not bound to one garment_unit/layer leg pair",
            orphan_gusset_node_ids=[node.get("node_id")
                                    for node in orphan_typed])

    bridges: List[Tuple[Tuple[Optional[str], int], Dict[str, Any]]] = []
    for key, group_graph in group_graphs:
        bridge, error = _single_trouser_bridge_candidates(
            group_graph, candidate_state=candidate_state)
        if error or bridge is None:
            return None, error or _unknown(
                "UNKNOWN_TROUSER_BRIDGE_RESULT",
                "a grouped trouser bridge produced no result",
                garment_unit=key[0], layer=key[1])
        bridges.append((key, bridge))
    if len(bridges) == 1:
        bridge = bridges[0][1]
        declared_ids = {str(operation.get("operation_id", ""))
                        for operation in operation_rows}
        generated_ids = {str(seam.get("operation_id", ""))
                         for seam in bridge.get("seams", [])}
        collisions = sorted(declared_ids & generated_ids)
        if collisions:
            return None, _unknown(
                "UNKNOWN_TROUSER_BRIDGE_OPERATION_ID_COLLISION",
                "generated trouser seam ids collide with structure operations",
                operation_ids=collisions)
        return bridge, None

    pieces_by_node: Dict[str, List[Dict[str, Any]]] = {}
    canonical: Dict[str, Dict[str, Any]] = {}
    seams: List[Dict[str, Any]] = []
    consumed_operation_ids: set[str] = set()
    geometry_records: List[Dict[str, Any]] = []
    individual_expansions: List[Dict[str, Any]] = []
    for index, (key, raw_bridge) in enumerate(bridges, 1):
        bridge = copy.deepcopy(raw_bridge)
        collisions = sorted(set(pieces_by_node) & set(bridge["pieces_by_node"]))
        if collisions:
            return None, _unknown(
                "UNKNOWN_MULTI_TROUSER_NODE_COLLISION",
                "two trouser blocks cannot own the same source node",
                node_ids=collisions)
        pieces_by_node.update(bridge["pieces_by_node"])
        canonical.update(bridge["canonical_port_piece"])
        prefix = f"trouser-group-{index:02d}-"
        renamed: Dict[str, str] = {}
        for seam in bridge.get("seams", []):
            old = str(seam.get("operation_id", ""))
            new = prefix + old
            seam["operation_id"] = new
            renamed[old] = new
            seams.append(seam)
        expansion = copy.deepcopy(bridge["expansion"])
        expansion["generated_seams"] = [
            renamed.get(str(operation_id), str(operation_id))
            for operation_id in expansion.get("generated_seams", [])]
        expansion["physical_group"] = {
            "garment_unit": key[0], "layer": key[1],
        }
        individual_expansions.append(expansion)
        consumed_operation_ids.update(
            bridge.get("consumed_operation_ids", set()))
        for record in bridge.get("geometry_records", []):
            row = copy.deepcopy(record)
            row["garment_unit"] = key[0]
            row["layer"] = key[1]
            geometry_records.append(row)

    declared_ids = {str(operation.get("operation_id", ""))
                    for operation in operation_rows}
    generated_ids = {str(seam.get("operation_id", "")) for seam in seams}
    collisions = sorted(declared_ids & generated_ids)
    if collisions or len(generated_ids) != len(seams):
        return None, _unknown(
            "UNKNOWN_MULTI_TROUSER_OPERATION_ID_COLLISION",
            "multi-trouser generated seam ids must be unique and must not collide with structure operations",
            operation_ids=(collisions if collisions else
                           [str(seam.get("operation_id", ""))
                            for seam in seams]))

    expansion = {
        "kind": "MULTI_TROUSER_BLOCK_BRIDGE",
        "state": "PROPOSED",
        "candidate_state_does_not_promote_dimensions": candidate_state,
        "physical_group_count": len(bridges),
        "physical_groups": [row["physical_group"]
                            for row in individual_expansions],
        "source_nodes": sorted(pieces_by_node),
        "generated_pieces": [
            str(piece.get("piece_id"))
            for rows in pieces_by_node.values() for piece in rows],
        "generated_seams": sorted(generated_ids),
        "method": "independent garment_unit/layer trouser_block expansion",
        "target_wearer_measurements_used": False,
        "manufacturing_guarantee": False,
    }
    return {
        "pieces_by_node": pieces_by_node,
        "seams": seams,
        "sleeve_balance": [],
        "canonical_port_piece": canonical,
        "consumed_operation_ids": consumed_operation_ids,
        "geometry_records": geometry_records,
        "expansion": expansion,
        "additional_expansions": individual_expansions,
    }, None


def _bridge_boundary_addresses(
    pieces: Sequence[Mapping[str, Any]], prefix: str,
) -> Tuple[Optional[List[Tuple[Mapping[str, Any], str]]], Optional[Dict[str, Any]]]:
    addresses: List[Tuple[Mapping[str, Any], str]] = []
    for role in ("front_bodice", "back_bodice"):
        piece = next((row for row in pieces if row.get("role") == role), None)
        if piece is None:
            return None, _unknown(
                "UNKNOWN_COMBINED_BODY_BRIDGE_PIECES",
                f"combined bridge lacks {role}")
        groups = piece.get("boundary_edge_groups", {})
        if not isinstance(groups, Mapping):
            return None, _unknown(
                "UNKNOWN_COMBINED_BODY_BRIDGE_BOUNDARY",
                f"{piece.get('piece_id')} lacks boundary edge groups")
        names = [name for name in groups if str(name).startswith(prefix)]
        names.sort(key=lambda name: ("right" not in str(name), str(name)))
        if not names:
            return None, _unknown(
                "UNKNOWN_COMBINED_BODY_BRIDGE_BOUNDARY",
                f"{piece.get('piece_id')} lacks {prefix} edges")
        for name in names:
            for edge in groups[name]:
                addresses.append((piece, str(edge)))
    return addresses, None


def _combine_sleeve_trouser_bridges(
    sleeve: Mapping[str, Any], trouser: Mapping[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Share the real front/back bodice between sleeve and trouser bridges."""
    sleeve_pieces = sleeve.get("pieces_by_node", {})
    trouser_pieces = trouser.get("pieces_by_node", {})
    if not isinstance(sleeve_pieces, Mapping) or not isinstance(trouser_pieces, Mapping):
        return None, _unknown(
            "UNKNOWN_COMBINED_BODY_BRIDGE_RESULT",
            "both bridges must expose pieces_by_node")
    sleeve_body_ids = [
        str(node_id) for node_id, pieces in sleeve_pieces.items()
        if isinstance(pieces, Sequence)
        and any(isinstance(piece, Mapping)
                and piece.get("role") == "front_bodice" for piece in pieces)
    ]
    trouser_body_ids = [
        str(node_id) for node_id, pieces in trouser_pieces.items()
        if isinstance(pieces, Sequence)
        and any(isinstance(piece, Mapping)
                and piece.get("primitive_kind") == "BODY_SHELL" for piece in pieces)
    ]
    if (len(sleeve_body_ids) != 1 or len(trouser_body_ids) != 1
            or sleeve_body_ids[0] != trouser_body_ids[0]):
        return None, _unknown(
            "UNKNOWN_COMBINED_BODY_BRIDGE_IDENTITY",
            "sleeve and trouser bridges must expand the same BODY_SHELL",
            sleeve_body_ids=sleeve_body_ids,
            trouser_body_ids=trouser_body_ids)
    body_id = sleeve_body_ids[0]
    body_pieces = list(sleeve_pieces[body_id])
    body_addresses, error = _bridge_boundary_addresses(body_pieces, "waist")
    if error or body_addresses is None:
        return None, error
    target_roles = (
        "left_front_leg_panel", "left_back_leg_panel",
        "right_front_leg_panel", "right_back_leg_panel",
    )
    all_trouser_pieces = [
        piece for node_id, rows in trouser_pieces.items()
        if str(node_id) != body_id
        for piece in rows
        if isinstance(piece, Mapping)
    ]
    targets = [next((piece for piece in all_trouser_pieces
                     if piece.get("role") == role), None)
               for role in target_roles]
    if len(body_addresses) != 4 or any(piece is None for piece in targets):
        return None, _unknown(
            "UNKNOWN_COMBINED_BODY_BRIDGE_WAIST_CARDINALITY",
            "combined jumpsuit needs four bodice waist edges and four trouser panels",
            body_edge_count=len(body_addresses), target_roles=list(target_roles))
    waist_seams: List[Dict[str, Any]] = []
    for index, ((body_piece, body_edge), target) in enumerate(
            zip(body_addresses, targets), 1):
        assert target is not None
        body_length = float(body_piece["edges"][body_edge]["length"])
        target_length = float(target["edges"]["e2"]["length"])
        if abs(body_length - target_length) > 0.05:
            return None, _unknown(
                "UNKNOWN_COMBINED_BODY_BRIDGE_WAIST_BALANCE",
                "bodice waist edge and trouser panel waist are not equal",
                body_address=f"{body_piece['piece_id']}/{body_edge}",
                trouser_address=f"{target['piece_id']}/e2",
                body_length_cm=body_length, trouser_length_cm=target_length,
                difference_cm=round(body_length - target_length, 6))
        waist_seams.append(_bridge_seam(
            f"combined-trouser-waist-{index}", body_piece, body_edge,
            target, "e2", role="WAIST_JOIN",
            group_id="combined-trouser-waist"))

    old_body_piece_ids = {
        str(piece["piece_id"]) for piece in trouser_pieces[body_id]}
    internal_trouser_seams = [
        copy.deepcopy(seam) for seam in trouser.get("seams", [])
        if str(seam.get("a", {}).get("piece_id")) not in old_body_piece_ids
        and str(seam.get("b", {}).get("piece_id")) not in old_body_piece_ids
    ]
    combined_pieces = copy.deepcopy(dict(sleeve_pieces))
    for node_id, rows in trouser_pieces.items():
        if str(node_id) != body_id:
            combined_pieces[str(node_id)] = copy.deepcopy(list(rows))
    canonical = copy.deepcopy(dict(sleeve.get("canonical_port_piece", {})))
    for node_id, piece in trouser.get("canonical_port_piece", {}).items():
        if str(node_id) != body_id:
            canonical[str(node_id)] = copy.deepcopy(piece)
    generated_ids = {
        str(seam["operation_id"])
        for seam in list(sleeve.get("seams", []))
        + internal_trouser_seams + waist_seams
    }
    if len(generated_ids) != (len(sleeve.get("seams", []))
                              + len(internal_trouser_seams)
                              + len(waist_seams)):
        return None, _unknown(
            "UNKNOWN_COMBINED_BODY_BRIDGE_OPERATION_ID_COLLISION",
            "combined generated seam ids are not unique")
    trouser_expansion = copy.deepcopy(trouser["expansion"])
    trouser_expansion["body_piece_replaced_by_bodice_bridge"] = True
    trouser_expansion["generated_pieces"] = [
        piece["piece_id"] for piece in all_trouser_pieces]
    trouser_expansion["generated_seams"] = [
        seam["operation_id"] for seam in internal_trouser_seams + waist_seams]
    combination = {
        "kind": "COMBINED_BODICE_SLEEVE_TROUSER_BRIDGE",
        "state": "PROPOSED",
        "source_nodes": copy.deepcopy(trouser_expansion["source_nodes"]),
        "shared_body_node": body_id,
        "generated_waist_seams": [row["operation_id"] for row in waist_seams],
        "method": "replace generic trouser torso with drafted front/back bodice waist edges",
        "target_wearer_measurements_used": False,
        "manufacturing_guarantee": False,
    }
    return {
        "pieces_by_node": combined_pieces,
        "seams": (copy.deepcopy(list(sleeve.get("seams", [])))
                  + internal_trouser_seams + waist_seams),
        "layers": copy.deepcopy(list(sleeve.get("layers", []))),
        "sleeve_balance": copy.deepcopy(sleeve.get("sleeve_balance", [])),
        "canonical_port_piece": canonical,
        "side_piece_map": copy.deepcopy(sleeve.get("side_piece_map", {})),
        "consumed_operation_ids": (
            set(sleeve.get("consumed_operation_ids", set()))
            | set(trouser.get("consumed_operation_ids", set()))),
        "geometry_records": copy.deepcopy(trouser.get("geometry_records", [])),
        "expansion": copy.deepcopy(sleeve["expansion"]),
        "additional_expansions": [trouser_expansion, combination],
    }, None


def _combine_independent_sleeve_trouser_bridges(
    sleeve: Mapping[str, Any], trouser: Mapping[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Merge an upper/sleeve bridge with a separate standalone trouser unit.

    A single outfit candidate may contain two garment units.  The absence of a
    BODY_SHELL inside the trouser expansion is therefore meaningful: it says
    the trousers are not a jumpsuit lower.  Keep both connected components as
    independently wearable units instead of forcing a fictitious waist seam.
    """
    sleeve_pieces = sleeve.get("pieces_by_node", {})
    trouser_pieces = trouser.get("pieces_by_node", {})
    sleeve_canonical = sleeve.get("canonical_port_piece", {})
    trouser_canonical = trouser.get("canonical_port_piece", {})
    if not all(isinstance(value, Mapping) for value in (
            sleeve_pieces, trouser_pieces, sleeve_canonical,
            trouser_canonical)):
        return None, _unknown(
            "UNKNOWN_INDEPENDENT_BRIDGE_RESULT",
            "independent bridges must expose piece and port-address maps")
    collisions = sorted(set(sleeve_pieces) & set(trouser_pieces))
    if collisions:
        return None, _unknown(
            "UNKNOWN_INDEPENDENT_BRIDGE_COLLISION",
            "separate garment bridges cannot own the same source node",
            node_ids=collisions)
    if any(
            isinstance(piece, Mapping)
            and piece.get("primitive_kind") == "BODY_SHELL"
            for rows in trouser_pieces.values()
            if isinstance(rows, Sequence)
            for piece in rows):
        return None, _unknown(
            "UNKNOWN_INDEPENDENT_BRIDGE_BODY",
            "a trouser bridge containing BODY_SHELL must use the joined jumpsuit combiner")
    combined_pieces = copy.deepcopy(dict(sleeve_pieces))
    combined_pieces.update(copy.deepcopy(dict(trouser_pieces)))
    canonical = copy.deepcopy(dict(sleeve_canonical))
    canonical.update(copy.deepcopy(dict(trouser_canonical)))
    return {
        "pieces_by_node": combined_pieces,
        "seams": (copy.deepcopy(list(sleeve.get("seams", [])))
                  + copy.deepcopy(list(trouser.get("seams", [])))),
        "layers": copy.deepcopy(list(sleeve.get("layers", []))),
        "sleeve_balance": copy.deepcopy(sleeve.get("sleeve_balance", [])),
        "canonical_port_piece": canonical,
        "side_piece_map": copy.deepcopy(sleeve.get("side_piece_map", {})),
        "consumed_operation_ids": (
            set(sleeve.get("consumed_operation_ids", set()))
            | set(trouser.get("consumed_operation_ids", set()))),
        "geometry_records": copy.deepcopy(trouser.get("geometry_records", [])),
        "expansion": copy.deepcopy(sleeve["expansion"]),
        "additional_expansions": [
            copy.deepcopy(trouser.get("expansion", {})),
            {
                "kind": "INDEPENDENT_UPPER_AND_TROUSER_UNITS",
                "state": "PROPOSED",
                "source_nodes": sorted(combined_pieces),
                "generated_pieces": [
                    str(piece.get("piece_id"))
                    for rows in combined_pieces.values()
                    for piece in rows
                    if isinstance(piece, Mapping)
                ],
                "method": "merge two internally connected garment units without inventing a waist join",
                "manufacturing_guarantee": False,
            },
        ],
    }, None


def compile_structure(structure: Mapping[str, Any], *,
                      candidate_state: str = "PROPOSED",
                      candidate_id: str = "",
                      approval: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Compile one structure candidate without raising its authority level."""
    if candidate_state not in ("PROPOSED", "APPROVED"):
        return _unknown("UNKNOWN_CANDIDATE_STATE", "candidate_state must be PROPOSED or APPROVED")
    if candidate_state == "APPROVED" and (
            not isinstance(approval, Mapping)
            or not str(approval.get("by", "")).strip()
            or not str(approval.get("digest", "")).strip()):
        return _unknown(
            "UNKNOWN_PATTERN_APPROVAL_REQUIRED",
            "APPROVED compilation requires a named human and exact candidate digest")
    checked = _structure.validate(structure)
    if checked.get("verdict") != ANSWER:
        return checked
    graph = checked["graph"]
    gore_layout, gore_error = _gore_panel_layout(graph)
    if gore_error:
        return gore_error
    assert gore_layout is not None
    sleeve_bridge, bridge_error = _bridge_candidates(
        graph, candidate_state=candidate_state)
    if bridge_error:
        return bridge_error
    trouser_bridge, bridge_error = _trouser_bridge_candidates(
        graph, candidate_state=candidate_state)
    if bridge_error:
        return bridge_error
    if sleeve_bridge is not None and trouser_bridge is not None:
        trouser_rows = trouser_bridge.get("pieces_by_node", {})
        trouser_has_body = (
            isinstance(trouser_rows, Mapping)
            and any(
                isinstance(piece, Mapping)
                and piece.get("primitive_kind") == "BODY_SHELL"
                for rows in trouser_rows.values()
                if isinstance(rows, Sequence)
                for piece in rows))
        combine = (_combine_sleeve_trouser_bridges if trouser_has_body
                   else _combine_independent_sleeve_trouser_bridges)
        bridge, bridge_error = combine(sleeve_bridge, trouser_bridge)
        if bridge_error or bridge is None:
            return bridge_error or _unknown(
                "UNKNOWN_MULTIPLE_BODY_BRIDGES",
                "bodice/sleeve and trouser bridges could not share one body edge map")
    else:
        bridge = trouser_bridge if trouser_bridge is not None else sleeve_bridge
    if (sleeve_bridge is not None and isinstance(bridge, dict)
            and bridge.get("deferred") is not True):
        attachments = _bodice_attachments.expand(
            graph, bridge, candidate_state=candidate_state)
        if attachments.get("verdict") != ANSWER:
            return copy.deepcopy(attachments)
        generated = attachments.get("pieces_by_node", {})
        if not isinstance(generated, Mapping):
            return _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_RESULT",
                "bodice attachment block did not return pieces_by_node")
        collisions = sorted(set(bridge["pieces_by_node"]) & set(generated))
        if collisions:
            return _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_NODE_COLLISION",
                "bodice attachment expansion collided with an existing bridge node",
                node_ids=collisions)
        for node_id, expanded_pieces in generated.items():
            if (not isinstance(expanded_pieces, Sequence)
                    or isinstance(expanded_pieces, (str, bytes))
                    or not expanded_pieces):
                return _unknown(
                    "UNKNOWN_BODICE_ATTACHMENT_RESULT",
                    f"{node_id} has no generated attachment pieces")
            bridge["pieces_by_node"][str(node_id)] = list(expanded_pieces)
            bridge["canonical_port_piece"][str(node_id)] = expanded_pieces[0]
        bridge["seams"].extend(
            copy.deepcopy(attachments.get("seams", [])))
        bridge["consumed_operation_ids"] = (
            set(bridge.get("consumed_operation_ids", set()))
            | set(attachments.get("consumed_operation_ids", [])))
        bridge["additional_expansions"] = (
            copy.deepcopy(bridge.get("additional_expansions", []))
            + copy.deepcopy(attachments.get("expansions", [])))
        bridge["attachment_digest"] = attachments.get("digest")
    bridge_pieces = (bridge.get("pieces_by_node", {})
                     if isinstance(bridge, Mapping) else {})
    gore_pieces = gore_layout["pieces_by_node"]
    pieces: List[Dict[str, Any]] = []
    features: List[Dict[str, Any]] = []
    anchors: List[Dict[str, Any]] = []
    port_addresses: Dict[Tuple[str, str], Tuple[str, str]] = {}
    closure_groups: List[Dict[str, Any]] = []
    # Map each external side-specific operation's target port to the exact
    # expanded sleeve instance.  Topology gives every child its own target
    # port id, so left and right decorations can coexist without colliding.
    port_side_overrides: Dict[Tuple[str, str], str] = {}
    if (isinstance(bridge, Mapping)
            and bridge.get("deferred") is not True):
        side_piece_map = bridge.get("side_piece_map", {})
        side_piece_map = (side_piece_map
                          if isinstance(side_piece_map, Mapping) else {})
        nodes_by_id = {str(node["node_id"]): node for node in graph["nodes"]}
        for operation in graph.get("operations", []):
            if str(operation.get("kind", "")) != "GATHER":
                continue
            source = operation.get("source", {})
            target = operation.get("target", {})
            if not isinstance(source, Mapping) or not isinstance(target, Mapping):
                continue
            target_id = str(target.get("node_id", ""))
            target_port = str(target.get("port_id", ""))
            source_node = nodes_by_id.get(str(source.get("node_id", "")), {})
            source_attributes = source_node.get("attributes", {})
            source_attributes = (source_attributes
                                 if isinstance(source_attributes, Mapping) else {})
            parameters = operation.get("parameters", {})
            parameters = parameters if isinstance(parameters, Mapping) else {}
            side = str(parameters.get(
                "relation_side", source_attributes.get("side", ""))).strip().lower()
            target_sides = side_piece_map.get(target_id, {})
            if (side not in {"left", "right"}
                    or not isinstance(target_sides, Mapping)
                    or side not in target_sides):
                continue
            key = (target_id, target_port)
            previous = port_side_overrides.get(key)
            if previous is not None and previous != side:
                return _unknown(
                    "UNKNOWN_BODICE_SLEEVE_EXTERNAL_GATHER_SIDE_CONFLICT",
                    "one expanded sleeve port was addressed by conflicting physical sides",
                    target_node_id=target_id, target_port_id=target_port,
                    sides=sorted({previous, side}))
            port_side_overrides[key] = side
    for node in graph["nodes"]:
        node_id = str(node["node_id"])
        bridge_expanded = bridge_pieces.get(node_id, [])
        gore_expanded = gore_pieces.get(node_id, [])
        if bridge_expanded and gore_expanded:
            return _unknown(
                "UNKNOWN_GORE_EXPANSION_COLLISION",
                f"{node_id} was expanded by two independent geometry bridges")
        expanded = bridge_expanded or gore_expanded
        if expanded:
            piece, error = None, None
        else:
            piece, error = _node_piece(node)
            if error:
                return error
        kind = str(node["kind"])
        if kind == "OPENING":
            attributes = copy.deepcopy(node.get("attributes", {}))
            semantic_authority = attributes.get(
                "opening_semantic_authority", {})
            semantic_authority = (semantic_authority
                                  if isinstance(semantic_authority, Mapping)
                                  else {})
            semantic_state = semantic_authority.get(
                "state", attributes.get("state", candidate_state))
            if semantic_state != "APPROVED":
                semantic_state = "PROPOSED"
            features.append({"kind": "OPENING", "node_id": node["node_id"],
                             "dimensions": copy.deepcopy(node["dimensions"]),
                             "target_node_id": attributes.get("opening_target_id"),
                             "placement": attributes.get("placement"),
                             "closure_detail": attributes.get("closure_detail"),
                             "opening_topology": attributes.get("opening_topology"),
                             "semantic_evidence": copy.deepcopy(
                                 attributes.get("parts_ir_semantics", {})),
                             "semantic_authority": copy.deepcopy(
                                 semantic_authority),
                             "state": semantic_state,
                             "observed": False})
        elif kind == "DRAPE_ANCHOR":
            anchors.append({"node_id": node["node_id"],
                            "dimensions": copy.deepcopy(node["dimensions"]),
                            "state": candidate_state})
        elif expanded:
            back = str(node.get("attributes", {}).get("back_design", ""))
            for expanded_piece in expanded:
                if back:
                    expanded_piece["construction_features"] = [{
                        "kind": "BACK_HYPOTHESIS", "value": back,
                        "state": "PROPOSED",
                        "basis": "selected structure candidate; the back was not observed from a front-only image",
                    }]
                pieces.append(expanded_piece)
        elif piece is not None:
            back = str(node.get("attributes", {}).get("back_design", ""))
            if back:
                piece["construction_features"] = [{
                    "kind": "BACK_HYPOTHESIS", "value": back,
                    "state": candidate_state,
                    "basis": "selected structure candidate; the back was not observed from a front-only image",
                }]
            pieces.append(piece)
            if piece["role"] in ("body_wrap", "tube_wrap", "flared_wrap", "sleeve_wrap"):
                closure_groups.append({
                    "operation_id": f"procedural-close-{piece['piece_id']}",
                    "a": {"piece_id": piece["piece_id"], "edge": "e1"},
                    "b": {"piece_id": piece["piece_id"], "edge": "e3"},
                })
        node_attributes = node.get("attributes", {})
        node_attributes = (node_attributes
                           if isinstance(node_attributes, Mapping) else {})
        declared_roles = (_semantic_tokens(node_attributes.get("detail_role"))
                          | _semantic_tokens(node_attributes.get("construction_role")))
        proposal_roles = declared_roles & {
            "pleat", "pleated", "gather", "gathered", "ruffle", "frill"
        }
        if proposal_roles:
            for generated_piece in (expanded or ([piece] if piece is not None else [])):
                generated_piece.setdefault("construction_features", []).append({
                    "kind": "SURFACE_SEMANTIC_PROPOSAL",
                    "value": sorted(proposal_roles),
                    "state": "PROPOSED",
                    "basis": (
                        "typed image-IR role; geometry is validated separately "
                        "and the front view does not certify construction"
                    ),
                    "manufacturing_ready": False,
                })
        # ``role=point`` ports describe a visual/non-sewing anchor.  They may
        # be represented by a boundary edge in the flat-pattern schema, but
        # they do not own that edge.  Reserving it here can displace a later
        # waist/cuff/neck JOIN onto an unrelated side edge, depending only on
        # the order in which topology rules happened to add the ports.
        used: List[str] = []
        for port in node.get("ports", []):
            address_piece = piece
            if expanded:
                if bridge_expanded:
                    override_side = port_side_overrides.get(
                        (node_id, str(port.get("port_id", ""))))
                    side_rows = bridge.get("side_piece_map", {}).get(
                        node_id, {})
                    if (override_side is not None
                            and isinstance(side_rows, Mapping)
                            and isinstance(side_rows.get(override_side), Mapping)):
                        address_piece = side_rows[override_side]
                    else:
                        address_piece = bridge["canonical_port_piece"][node_id]
                else:
                    address_piece = gore_expanded[0]
            edge = _port_edge(port, address_piece, used)
            if address_piece is not None:
                port_addresses[(str(node["node_id"]), str(port["port_id"]))] = (
                    address_piece["piece_id"], edge)
            if str(port.get("role", "edge")).strip().lower() != "point":
                used.append(edge)

    # Expose one uniform source-node lineage field for every cuttable piece.
    # Expansion helpers already keep this information in attributes or
    # provenance, but downstream UI/binding code should not need to know which
    # compiler branch produced the piece in order to preserve a visible part.
    graph_node_ids = {str(node["node_id"]) for node in graph["nodes"]}
    for generated_piece in pieces:
        if isinstance(generated_piece.get("source_node_id"), str):
            continue
        attributes = generated_piece.get("attributes", {})
        attributes = attributes if isinstance(attributes, Mapping) else {}
        provenance = generated_piece.get("provenance", {})
        provenance = provenance if isinstance(provenance, Mapping) else {}
        candidates = (
            attributes.get("source_node_id"),
            provenance.get("source_node"),
            generated_piece.get("node_id"),
        )
        source_node_id = next(
            (str(value) for value in candidates
             if isinstance(value, str) and value in graph_node_ids),
            None,
        )
        if source_node_id is not None:
            generated_piece["source_node_id"] = source_node_id

    # Resolve non-piece OPENING features to the exact generated target piece.
    # The feature remains proposed and does not create a slit/cutout by itself.
    for feature in features:
        target_node_id = feature.get("target_node_id")
        if not isinstance(target_node_id, str) or not target_node_id:
            continue
        if isinstance(bridge, Mapping):
            target_piece = bridge.get("canonical_port_piece", {}).get(target_node_id)
            if isinstance(target_piece, Mapping):
                feature["target_piece_id"] = target_piece.get("piece_id")
                continue
        target_piece = next((row for row in pieces
                             if row.get("node_id") == target_node_id), None)
        if target_piece is not None:
            feature["target_piece_id"] = target_piece.get("piece_id")

    seams: List[Dict[str, Any]] = (copy.deepcopy(bridge["seams"])
                                   if isinstance(bridge, Mapping) else [])
    # Ordered gore panel joins come only from the explicit circular order
    # validated above.  Every adjacent pair, including last-to-first, remains
    # PROPOSED because a front-only source cannot observe the rear seams.
    for group_index, group in enumerate(gore_layout["groups"], 1):
        ordered_ids = list(group["ordered_piece_ids"])
        group_token = _digest({"group_id": group["group_id"],
                               "ordered_piece_ids": ordered_ids})[:12]
        for order, (current, following) in enumerate(
                zip(ordered_ids, ordered_ids[1:] + ordered_ids[:1]), 1):
            seams.append({
                "operation_id": f"procedural-gore-{group_token}-{order:02d}",
                "kind": "JOIN",
                "construction_role": "ORDERED_GORE_PANEL_ASSEMBLY",
                "a": {"piece_id": current, "edge": "e1"},
                "b": {"piece_id": following, "edge": "e3"},
                "state": "PROPOSED",
                "order_source": "EXPLICIT_TYPED_IR",
                "gore_group_id": group["group_id"],
                "panel_order": order,
                "manufacturing_validated": False,
                "manufacturing_ready": False,
            })
    layers: List[Dict[str, Any]] = (
        copy.deepcopy(bridge.get("layers", []))
        if isinstance(bridge, Mapping) else [])
    transform_records: List[Dict[str, Any]] = []
    surface_modifier_bindings: List[Dict[str, Any]] = []
    geometry_records: List[Dict[str, Any]] = (
        copy.deepcopy(bridge.get("geometry_records", []))
        if isinstance(bridge, Mapping) else [])
    address_remaps: List[Dict[str, Any]] = []
    consumed_operation_ids = (
        set(bridge.get("consumed_operation_ids", set()))
        if isinstance(bridge, Mapping) else set())
    for operation in graph.get("operations", []):
        if str(operation.get("operation_id", "")) in consumed_operation_ids:
            continue
        kind = str(operation["kind"])
        source = operation["source"]
        target = operation.get("target")
        source_address = port_addresses.get(
            (str(source["node_id"]), str(source["port_id"])))
        source_piece = (_find_piece_id(pieces, source_address[0])
                        if source_address is not None else None)
        source_edge = source_address[1] if source_address is not None else None
        parameters = operation.get("parameters", {})
        if not isinstance(parameters, Mapping):
            return _unknown("UNKNOWN_PATTERN_OPERATION_PARAMETERS",
                            f"{operation['operation_id']} parameters must be an object")
        if kind == "CUTOUT":
            if source_piece is None or source_edge is None:
                return _unknown("UNKNOWN_OPERATION_PATTERN_ADDRESS",
                                f"{operation['operation_id']} has no generated source piece")
            record, error = _apply_cutout(
                source_piece, operation, source, source_edge,
                candidate_state=candidate_state, approval=approval)
            if error:
                return error
            assert record is not None
            geometry_records.append(copy.deepcopy(record))
            address_remaps.append({
                "operation_id": operation["operation_id"],
                "kind": "CUTOUT",
                "outer_edge_addresses_changed": False,
                "contour_edge_lineage": copy.deepcopy(
                    record["contour_edge_lineage"]),
            })
            continue
        if kind in ("MIRROR", "ASYMMETRY"):
            if source_piece is None or source_edge is None:
                return _unknown("UNKNOWN_OPERATION_PATTERN_ADDRESS",
                                f"{operation['operation_id']} has no generated source edge")
            known_ids = [piece["piece_id"] for piece in pieces]
            if kind == "MIRROR":
                generated, record, error = _mirror_piece(
                    source_piece, parameters, str(operation["operation_id"]), known_ids)
            else:
                generated, record, error = _asymmetric_piece(
                    source_piece, parameters, str(operation["operation_id"]), known_ids)
            if error:
                return error
            assert generated is not None and record is not None
            pieces.append(generated)
            geometry_records.append(record)
            address_remaps.append({
                "operation_id": operation["operation_id"],
                "kind": kind,
                "source_edge_lineage": copy.deepcopy(record["source_edge_lineage"]),
            })
            if generated["role"] in ("body_wrap", "tube_wrap", "flared_wrap", "sleeve_wrap"):
                edge_map = {
                    str(row["source"]).rsplit("/", 1)[1]: str(row["target"]).rsplit("/", 1)[1]
                    for row in record["source_edge_lineage"]
                }
                if "e1" not in edge_map or "e3" not in edge_map:
                    return _unknown(
                        "UNKNOWN_DERIVED_CLOSURE_LINEAGE",
                        f"{operation['operation_id']} does not preserve both wrap closure edges")
                closure_groups.append({
                    "operation_id": f"procedural-close-{generated['piece_id']}",
                    "a": {"piece_id": generated["piece_id"], "edge": edge_map["e1"]},
                    "b": {"piece_id": generated["piece_id"], "edge": edge_map["e3"]},
                })
            continue
        if kind == "SPLIT":
            if source_piece is None or source_edge is None:
                return _unknown("UNKNOWN_OPERATION_PATTERN_ADDRESS",
                                f"{operation['operation_id']} has no generated source edge")
            children, record, error = _split_piece(
                source_piece, parameters, str(operation["operation_id"]),
                [piece["piece_id"] for piece in pieces])
            if error:
                return error
            assert children is not None and record is not None
            lineage = record["source_edge_lineage"]
            source_piece_id = source_piece["piece_id"]

            # Resolve every live address before mutating anything.  A partial
            # old edge is deliberately not treated as the same edge.
            port_updates: Dict[Tuple[str, str], Tuple[str, str]] = {}
            for key, address in port_addresses.items():
                if address[0] != source_piece_id:
                    continue
                remapped = _full_remap(lineage, f"{address[0]}/{address[1]}")
                if remapped is None:
                    return _unknown(
                        "UNKNOWN_SPLIT_PORT_ADDRESS_PARTIAL",
                        f"{operation['operation_id']} splits a live port edge; no full-edge address exists",
                        port={"node_id": key[0], "port_id": key[1]},
                        source_address=f"{address[0]}/{address[1]}",
                        address_remap=copy.deepcopy(lineage))
                port_updates[key] = tuple(remapped.rsplit("/", 1))  # type: ignore[assignment]

            relation_updates: List[Tuple[Dict[str, Any], str, Dict[str, str]]] = []
            for relation in seams + layers + closure_groups:
                for side_name in ("a", "b"):
                    address = relation.get(side_name)
                    if not isinstance(address, Mapping) or address.get("piece_id") != source_piece_id:
                        continue
                    source_name = f"{source_piece_id}/{address.get('edge')}"
                    remapped = _full_remap(lineage, source_name)
                    if remapped is None:
                        return _unknown(
                            "UNKNOWN_SPLIT_LIVE_ADDRESS_PARTIAL",
                            f"{operation['operation_id']} splits an edge already used by a seam, layer, or closure",
                            source_address=source_name,
                            address_remap=copy.deepcopy(lineage))
                    piece_id, edge = remapped.rsplit("/", 1)
                    relation_updates.append((relation, side_name,
                                             {"piece_id": piece_id, "edge": edge}))

            source_index = pieces.index(source_piece)
            pieces[source_index:source_index + 1] = children
            port_addresses.update(port_updates)
            for relation, side_name, remapped in relation_updates:
                relation[side_name] = remapped
            join = copy.deepcopy(record["generated_join"])
            seams.append({
                "operation_id": operation["operation_id"],
                "kind": "JOIN",
                "construction_role": "SPLIT_REJOIN",
                "source_operation_kind": "SPLIT",
                "a": join["a"],
                "b": join["b"],
                "state": candidate_state,
                "manufacturing_validated": False,
            })
            geometry_records.append(record)
            address_remaps.append({
                "operation_id": operation["operation_id"],
                "kind": "SPLIT",
                "source_edge_lineage": copy.deepcopy(lineage),
            })
            continue
        if kind in ("PLEAT", "DART", "FOLD"):
            surface_resolution: Optional[Dict[str, Any]] = None
            if _surface_modifiers.has_surface_target(operation):
                surface_resolution = _surface_modifiers.resolve(
                    operation, pieces)
                if surface_resolution.get("verdict") != ANSWER:
                    surface_resolution["operation_id"] = operation["operation_id"]
                    surface_resolution["structure_digest"] = checked["digest"]
                    return surface_resolution
                source_piece = _find_piece_id(
                    pieces, str(surface_resolution["piece_id"]))
                source_edge = str(surface_resolution["edge"])
            else:
                source_node = next(
                    (node for node in graph["nodes"]
                     if str(node.get("node_id", ""))
                     == str(source.get("node_id", ""))), None)
                if (isinstance(source_node, Mapping)
                        and str(source_node.get("kind", "")) == "BODY_SHELL"):
                    return _unknown(
                        "REVIEW_SURFACE_MODIFIER_TARGET_REQUIRED",
                        f"{operation['operation_id']} cannot map a BODY_SHELL port to an arbitrary eN edge",
                        state="REVIEW",
                        operation_id=operation["operation_id"],
                        required=(
                            "parameters.surface_target with a unique compiled "
                            "piece and semantic_edge_group"))
            if source_piece is None or source_edge is None:
                return _unknown("UNKNOWN_OPERATION_PATTERN_ADDRESS",
                                f"{operation['operation_id']} has no generated source edge")
            repeated_gore_pieces = (
                gore_pieces.get(str(source.get("node_id", "")), [])
                if kind == "PLEAT" else [])
            if len(repeated_gore_pieces) > 1:
                for panel_index, panel_piece in enumerate(
                        repeated_gore_pieces, 1):
                    if panel_piece.get("inner_cutouts"):
                        return _unknown(
                            "UNKNOWN_TRANSFORM_INNER_CONTOUR_LINEAGE",
                            f"{operation['operation_id']} cannot transform a repeated gore panel with inner contours")
                    changed = _apply_unary(panel_piece, source_edge, operation)
                    if changed.get("verdict") != ANSWER:
                        changed["operation_id"] = operation["operation_id"]
                        changed["panel_piece_id"] = panel_piece["piece_id"]
                        return changed
                    repeated_operation_id = (
                        f"{operation['operation_id']}:panel-{panel_index:02d}")
                    proposal = {
                        "operation_id": repeated_operation_id,
                        "source_operation_id": operation["operation_id"],
                        "piece_id": panel_piece["piece_id"],
                        **changed["record"],
                        "state": "PROPOSED",
                        "manufacturing_validated": False,
                        "manufacturing_ready": False,
                    }
                    if panel_piece.get("transforms"):
                        panel_piece["transforms"][-1].update({
                            "operation_id": repeated_operation_id,
                            "source_operation_id": operation["operation_id"],
                            "piece_id": panel_piece["piece_id"],
                            "state": "PROPOSED",
                            "manufacturing_validated": False,
                            "manufacturing_ready": False,
                        })
                    transform_records.append(proposal)
                continue
            if source_piece.get("inner_cutouts"):
                return _unknown(
                    "UNKNOWN_TRANSFORM_INNER_CONTOUR_LINEAGE",
                    f"{operation['operation_id']} cannot transform a piece with inner contours without transforming their coordinates")
            changed = _apply_unary(source_piece, source_edge, operation)
            if changed.get("verdict") != ANSWER:
                changed["operation_id"] = operation["operation_id"]
                return changed
            record = {"operation_id": operation["operation_id"],
                      "piece_id": source_piece["piece_id"],
                      **changed["record"]}
            if kind == "PLEAT":
                record.update({
                    "state": "PROPOSED",
                    "manufacturing_validated": False,
                    "manufacturing_ready": False,
                })
                if source_piece.get("transforms"):
                    source_piece["transforms"][-1].update({
                        "operation_id": operation["operation_id"],
                        "piece_id": source_piece["piece_id"],
                        "state": "PROPOSED",
                        "manufacturing_validated": False,
                        "manufacturing_ready": False,
                    })
            if surface_resolution is not None:
                binding = copy.deepcopy(surface_resolution["binding"])
                record.update({
                    "state": "PROPOSED",
                    "surface_binding": binding,
                    "surface_modifier_digest": surface_resolution["digest"],
                })
                if source_piece.get("transforms"):
                    source_piece["transforms"][-1].update({
                        "operation_id": operation["operation_id"],
                        "piece_id": source_piece["piece_id"],
                        "state": "PROPOSED",
                        "surface_binding": copy.deepcopy(binding),
                        "surface_modifier_digest": surface_resolution["digest"],
                    })
                surface_modifier_bindings.append(binding)
            transform_records.append(record)
            continue
        if kind in ("JOIN", "GATHER", "OVERLAP", "LAYER"):
            if not isinstance(target, Mapping):
                return _unknown("UNKNOWN_OPERATION_TARGET", f"{operation['operation_id']} needs a target")
            target_address = port_addresses.get(
                (str(target["node_id"]), str(target["port_id"])))
            target_piece = (_find_piece_id(pieces, target_address[0])
                            if target_address is not None else None)
            target_edge = target_address[1] if target_address is not None else None
            if source_piece is None or target_piece is None or source_edge is None or target_edge is None:
                return _unknown("UNKNOWN_OPERATION_PATTERN_ADDRESS",
                                f"{operation['operation_id']} does not resolve to two generated edges")
            construction_role = str(parameters.get(
                "construction_role", operation.get("construction_role", ""),
            )).strip().upper()
            relation_side = parameters.get(
                "relation_side", operation.get("relation_side"))
            pattern_lineage = {
                "source_operation_id": operation["operation_id"],
                "relation_kind": kind,
                "source": {
                    "node_id": str(source["node_id"]),
                    "port_id": str(source["port_id"]),
                    "piece_id": source_piece["piece_id"],
                    "edge": source_edge,
                },
                "target": {
                    "node_id": str(target["node_id"]),
                    "port_id": str(target["port_id"]),
                    "piece_id": target_piece["piece_id"],
                    "edge": target_edge,
                },
                "state": "PROPOSED" if kind == "GATHER" else candidate_state,
            }
            if relation_side not in (None, ""):
                pattern_lineage["side"] = str(relation_side)
            if kind == "GATHER":
                if source_piece.get("inner_cutouts"):
                    return _unknown(
                        "UNKNOWN_TRANSFORM_INNER_CONTOUR_LINEAGE",
                        f"{operation['operation_id']} cannot gather a piece with inner contours without transforming their coordinates")
                finished = float(target_piece["edges"][target_edge]["length"])
                transformed = _transforms.apply_gather(
                    source_piece, source_edge, finished_length_cm=finished,
                    ratio=operation.get("parameters", {}).get("ratio"))
                if transformed.get("verdict") != ANSWER:
                    transformed["operation_id"] = operation["operation_id"]
                    return transformed
                source_piece.update(copy.deepcopy(transformed["after"]))
                _refresh_piece(source_piece)
                if source_piece.get("transforms"):
                    source_piece["transforms"][-1].update({
                        "operation_id": operation["operation_id"],
                        "piece_id": source_piece["piece_id"],
                        "state": "PROPOSED",
                        "semantic_authority": "PROPOSED_EXPLICIT_IR",
                        "manufacturing_validated": False,
                        "manufacturing_ready": False,
                    })
                transform_records.append({
                    "operation_id": operation["operation_id"],
                    "piece_id": source_piece["piece_id"],
                    **transformed["transform"],
                    **({"construction_role": construction_role}
                       if construction_role else {}),
                    **({"pattern_lineage": copy.deepcopy(pattern_lineage)}
                       if construction_role == "GATHER_SLEEVE_SEGMENTS"
                       else {}),
                    "state": "PROPOSED",
                    "semantic_authority": "PROPOSED_EXPLICIT_IR",
                    "manufacturing_validated": False,
                    "manufacturing_ready": False,
                })
            row = {
                "operation_id": operation["operation_id"], "kind": kind,
                "source_operation_id": operation["operation_id"],
                "a": {"piece_id": source_piece["piece_id"], "edge": source_edge},
                "b": {"piece_id": target_piece["piece_id"], "edge": target_edge},
                "declared_a_cm": next(p["length_cm"] for p in
                                      next(n for n in graph["nodes"] if n["node_id"] == source["node_id"])["ports"]
                                      if p["port_id"] == source["port_id"]),
                "declared_b_cm": next(p["length_cm"] for p in
                                      next(n for n in graph["nodes"] if n["node_id"] == target["node_id"])["ports"]
                                      if p["port_id"] == target["port_id"]),
                "state": candidate_state,
            }
            if construction_role:
                row["construction_role"] = construction_role
            if construction_role == "GATHER_SLEEVE_SEGMENTS":
                row["pattern_lineage"] = copy.deepcopy(pattern_lineage)
            if relation_side not in (None, ""):
                row["relation_side"] = str(relation_side)
            if kind == "GATHER":
                row.update({
                    "state": "PROPOSED",
                    "semantic_authority": "PROPOSED_EXPLICIT_IR",
                    "manufacturing_validated": False,
                    "manufacturing_ready": False,
                })
            if kind == "LAYER":
                layers.append(row)
            else:
                seams.append(row)
            continue
        return _unknown("UNKNOWN_PATTERN_OPERATION_UNSUPPORTED",
                        f"{operation['operation_id']} uses unsupported {kind}",
                        supported=["SPLIT", "CUTOUT", "JOIN", "GATHER", "OVERLAP", "LAYER",
                                   "PLEAT", "DART", "FOLD", "MIRROR", "ASYMMETRY"])

    construction_reviews = copy.deepcopy(gore_layout["reviews"])
    operation_kinds_by_source: Dict[str, set[str]] = {}
    for operation in graph.get("operations", []):
        source = operation.get("source", {})
        if isinstance(source, Mapping):
            operation_kinds_by_source.setdefault(
                str(source.get("node_id", "")), set()).add(
                    str(operation.get("kind", "")))
    for node in graph.get("nodes", []):
        if str(node.get("kind", "")) != "GORE":
            continue
        attributes = node.get("attributes", {})
        attributes = attributes if isinstance(attributes, Mapping) else {}
        roles = (_semantic_tokens(attributes.get("detail_role"))
                 | _semantic_tokens(attributes.get("construction_role")))
        operation_kinds = operation_kinds_by_source.get(
            str(node.get("node_id", "")), set())
        if roles & {"pleat", "pleated", "knife", "box"} and "PLEAT" not in operation_kinds:
            construction_reviews.append({
                "verdict": "REVIEW_GORE_PLEAT_GEOMETRY_REQUIRED",
                "state": "REVIEW",
                "node_id": node.get("node_id"),
                "why": (
                    "the explicit role proposes pleating, but no typed PLEAT "
                    "operation supplies count and depth_cm"
                ),
                "how_to_close": (
                    "add a PLEAT operation addressed to this GORE port with "
                    "positive count and depth_cm"
                ),
                "manufacturing_ready": False,
            })
        if roles & {"gather", "gathered", "ruffle", "frill"} and "GATHER" not in operation_kinds:
            construction_reviews.append({
                "verdict": "REVIEW_GORE_GATHER_GEOMETRY_REQUIRED",
                "state": "REVIEW",
                "node_id": node.get("node_id"),
                "why": (
                    "the explicit role proposes gathering, but no typed GATHER "
                    "operation supplies a target edge and ratio"
                ),
                "how_to_close": (
                    "add a GATHER operation with explicit source/target ports "
                    "and a ratio consistent with their lengths"
                ),
                "manufacturing_ready": False,
            })

    # Every wrap-type piece has a necessary closure seam even when the graph
    # only describes inter-piece joins.  This is procedural geometry, not a
    # claim about whether the reference used a centre-back or side closure.
    for closure in closure_groups:
        seams.append({
            **copy.deepcopy(closure),
            "kind": "PROCEDURAL_CLOSURE",
            "state": "PROPOSED",
            "manufacturing_validated": False,
        })

    seam_checks = []
    for seam in seams:
        a = _find_piece_id(pieces, seam["a"]["piece_id"])
        b = _find_piece_id(pieces, seam["b"]["piece_id"])
        if a is None or b is None:
            return _unknown(
                "UNKNOWN_COMPILED_SEAM_PIECE_ADDRESS",
                f"{seam['operation_id']} points to a missing compiled piece")
        la = a["edges"][seam["a"]["edge"]]["length"]
        lb = b["edges"][seam["b"]["edge"]]["length"]
        gathered = seam["kind"] == "GATHER"
        difference = round(la - lb, 6)
        sewable = gathered or abs(difference) <= 0.3
        a_address = f"{seam['a']['piece_id']}/{seam['a']['edge']}"
        b_address = f"{seam['b']['piece_id']}/{seam['b']['edge']}"
        seam_checks.append({
            "operation_id": seam["operation_id"],
            # Keep the established garment_pattern/repairs.py seam-check
            # contract as well as the compiler's explicit centimetre keys.
            # This prevents the repair loop from treating a missing boolean
            # field as a failed seam.
            "label": f"{a_address} <-> {b_address}",
            "a": a_address, "b": b_address,
            "length_a": la, "length_b": lb,
            "difference": difference, "tolerance": 0.3,
            "sewable": sewable, "structural": False,
            "length_a_cm": la, "length_b_cm": lb,
            "difference_cm": difference,
            "requires_ease_or_gather": gathered or abs(difference) > 0.05,
            "geometrically_sewable": sewable,
            "why": ("GATHER explicitly consumes the length difference"
                    if gathered else "deterministic edge-length comparison"),
        })

    approved = candidate_state == "APPROVED"
    artifact = {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "candidate_state": candidate_state,
        "structure_digest": checked["digest"],
        "pieces": pieces,
        "seams": seams,
        "layers": layers,
        "features": features,
        "drape_anchors": anchors,
        "transforms": transform_records,
        "surface_modifiers": surface_modifier_bindings,
        "geometry_operations": geometry_records,
        "gore_panel_groups": copy.deepcopy(gore_layout["groups"]),
        "construction_reviews": construction_reviews,
        "candidate_specific_expansions": (
            ([copy.deepcopy(bridge["expansion"])]
             + copy.deepcopy(bridge.get("additional_expansions", [])))
            if isinstance(bridge, Mapping) else []),
        "sleeve_balance_checks": (
            copy.deepcopy(bridge["sleeve_balance"])
            if isinstance(bridge, Mapping) else []),
        "address_remap": address_remaps,
        "seam_checks": seam_checks,
        "total_area_cm2": round(sum(float(p.get("net_area_cm2", p["area_cm2"]))
                                    * p["cut_count"] for p in pieces), 6),
        "units": "cm",
        "seam_allowance": "not added; outlines are sewing lines",
        "not_a_published_system": "Procedural geometric baseline, not a published drafting system.",
        "note": "Front-only unseen construction remains a candidate hypothesis.",
        "approval": copy.deepcopy(dict(approval)) if approved else None,
        "cuttable_geometric_prototype": bool(pieces),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "remaining_gates": [
            "replace proposed body dimensions with wearer measurements",
            "choose and validate closure/donning topology",
            "add seam allowance, notches, grain and construction method",
            "validate material, strength, comfort and sewing sequence",
        ],
        "provenance": {
            "method": "garment.structure.v1 deterministic compiler",
            "corpus_used": False,
            "front_only_unknowns_promoted": False,
            "preview_dimensions_not_wearer_measurements": bool(bridge),
        },
    }
    artifact["digest"] = _digest(artifact)
    return {"verdict": ANSWER, **artifact}


compile = compile_structure
