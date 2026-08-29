# -*- coding: utf-8 -*-
"""Deterministic two-leg + gusset pattern topology.

This module does not recognise a garment class and does not infer body
measurements from an image.  It accepts the structural statement already made
by a proposal -- two ``TUBE`` nodes, one for each side, and one ``GUSSET`` --
and expands it into four leg panels plus a four-sided crotch gusset.  Every
result remains a preview proposal.  The geometry is useful for candidate
comparison and connectivity checks, but it is not a validated trouser block or
a manufacturing guarantee.

The expansion exists because compiling each leg as one closed rectangle loses
the rise and crotch topology entirely.  A whole pair of trousers must never be
reported as successfully represented by one generic tube.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


ANSWER = "ANSWER"
SCHEMA = "garment.trouser-block.v1"
Point = Tuple[float, float]


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "why": why,
        "how_to_close": (
            "supply exactly one left TUBE, one right TUBE and one GUSSET "
            "with the same explicit garment_unit and finite positive preview dimensions"
        ),
        **detail,
    }


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _positive(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and float(value) > 0.0)


def _length(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _area(points: Sequence[Point]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2.0


def _edge_table(points: Sequence[Point], labels: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    return {
        f"e{index}": {
            "points": [[round(a[0], 6), round(a[1], 6)],
                       [round(b[0], 6), round(b[1], 6)]],
            "length": round(_length(a, b), 6),
            "semantic": labels[index],
        }
        for index, (a, b) in enumerate(zip(points, points[1:] + points[:1]))
    }


def _attributes(node: Mapping[str, Any]) -> Mapping[str, Any]:
    value = node.get("attributes", {})
    return value if isinstance(value, Mapping) else {}


def _side(node: Mapping[str, Any]) -> Optional[str]:
    raw = str(_attributes(node).get("side", "")).strip().lower()
    aliases = {
        "left": "left", "l": "left", "左": "left",
        "right": "right", "r": "right", "右": "right",
    }
    return aliases.get(raw)


def _unit(node: Mapping[str, Any]) -> Optional[str]:
    value = _attributes(node).get("garment_unit")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _node_id(node: Mapping[str, Any]) -> Optional[str]:
    value = node.get("node_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _dimensions(node: Mapping[str, Any], names: Sequence[str], *,
                node_id: str) -> Tuple[Optional[Dict[str, float]], Optional[Dict[str, Any]]]:
    raw = node.get("dimensions")
    if not isinstance(raw, Mapping):
        return None, _unknown(
            "UNKNOWN_TROUSER_DIMENSIONS", f"{node_id}.dimensions must be an object")
    missing = [name for name in names if not _positive(raw.get(name))]
    if missing:
        return None, _unknown(
            "UNKNOWN_TROUSER_DIMENSIONS",
            f"{node_id} needs finite positive structural dimensions",
            node_id=node_id, missing=missing)
    return {name: float(raw[name]) for name in names}, None


def _piece(piece_id: str, source_node_id: str, side: str, panel: str,
           points: Sequence[Point], labels: Sequence[str], garment_unit: str,
           *, primitive_kind: str) -> Dict[str, Any]:
    rounded = [[round(x, 6), round(y, 6)] for x, y in points]
    return {
        "piece_id": piece_id,
        "name": piece_id,
        "source_node_id": source_node_id,
        "primitive_kind": primitive_kind,
        "role": "crotch_gusset" if panel == "gusset" else f"{side}_{panel}_leg_panel",
        "side": side,
        "panel": panel,
        "outline": rounded,
        "edges": _edge_table(points, labels),
        "edge_semantics": {f"e{index}": label
                           for index, label in enumerate(labels)},
        "area_cm2": round(_area(points), 6),
        "cut_count": 1,
        "layer": 0,
        "attributes": {
            "garment_unit": garment_unit,
            "expanded_from_primitive": True,
            "state": "PROPOSED",
            "dimension_authority": "PROPOSED_INPUT_STRUCTURE",
            "target_wearer_measurement": False,
        },
        "provenance": {
            "method": "deterministic two TUBE + GUSSET topology expansion",
            "source_node": source_node_id,
            "state": "PROPOSED",
            "image_measurements_claimed": False,
            "corpus_used": False,
        },
    }


def _seam(operation_id: str, a_piece: Mapping[str, Any], a_edge: str,
          b_piece: Mapping[str, Any], b_edge: str, role: str) -> Dict[str, Any]:
    return {
        "operation_id": operation_id,
        "kind": "JOIN",
        "construction_role": role,
        "a": {"piece_id": a_piece["piece_id"], "edge": a_edge},
        "b": {"piece_id": b_piece["piece_id"], "edge": b_edge},
        "state": "PROPOSED",
        "manufacturing_validated": False,
    }


def draft_pair(left: Mapping[str, Any], right: Mapping[str, Any],
               gusset: Mapping[str, Any], *,
               candidate_state: str = "PROPOSED") -> Dict[str, Any]:
    """Expand an explicit two-leg structural proposal into connected pieces."""
    if candidate_state not in ("PROPOSED", "APPROVED"):
        return _unknown(
            "UNKNOWN_TROUSER_CANDIDATE_STATE",
            "candidate_state must be PROPOSED or APPROVED")
    nodes = (left, right, gusset)
    if any(not isinstance(node, Mapping) for node in nodes):
        return _unknown("UNKNOWN_TROUSER_NODES", "all three nodes must be objects")
    if str(left.get("kind", "")) != "TUBE" or str(right.get("kind", "")) != "TUBE":
        return _unknown(
            "UNKNOWN_TROUSER_LEG_PRIMITIVES",
            "left and right structural nodes must both be TUBE")
    if str(gusset.get("kind", "")) != "GUSSET":
        return _unknown(
            "UNKNOWN_TROUSER_GUSSET_PRIMITIVE",
            "the crotch structural node must be GUSSET")
    if _side(left) != "left" or _side(right) != "right":
        return _unknown(
            "UNKNOWN_TROUSER_SIDES",
            "the two TUBE nodes must explicitly declare opposite left/right sides",
            left_side=_side(left), right_side=_side(right))
    ids = [_node_id(node) for node in nodes]
    if any(identity is None for identity in ids) or len(set(ids)) != 3:
        return _unknown(
            "UNKNOWN_TROUSER_NODE_IDS",
            "the three structural nodes need unique non-empty node_id values")
    units = [_unit(node) for node in nodes]
    if any(unit is None for unit in units) or len(set(units)) != 1:
        return _unknown(
            "UNKNOWN_TROUSER_GARMENT_UNIT",
            "both legs and the gusset must explicitly share one garment_unit",
            garment_units=units)
    garment_unit = str(units[0])
    left_dimensions, error = _dimensions(
        left, ("length_cm", "circumference_cm"), node_id=str(ids[0]))
    if error:
        return error
    right_dimensions, error = _dimensions(
        right, ("length_cm", "circumference_cm"), node_id=str(ids[1]))
    if error:
        return error
    gusset_dimensions, error = _dimensions(
        gusset, ("length_cm", "width_cm"), node_id=str(ids[2]))
    if error:
        return error
    assert left_dimensions and right_dimensions and gusset_dimensions

    # The diamond's four edges become the four explicit gusset seams.  No
    # body rise is claimed: a bounded geometric rise is derived solely so the
    # proposed pieces have non-degenerate addressable boundaries.
    gusset_edge = math.hypot(gusset_dimensions["length_cm"] / 2.0,
                             gusset_dimensions["width_cm"] / 2.0)

    pieces: List[Dict[str, Any]] = []
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    geometry_records: List[Dict[str, Any]] = []
    for side, node, dimensions in (
            ("left", left, left_dimensions),
            ("right", right, right_dimensions)):
        length = dimensions["length_cm"]
        circumference = dimensions["circumference_cm"]
        panel_width = circumference / 2.0
        hem_width = max(panel_width * 0.62, min(panel_width, 8.0))
        crotch_extension = min(panel_width * 0.30,
                               max(gusset_dimensions["width_cm"] / 2.0,
                                   panel_width * 0.12))
        rise = max(gusset_edge + max(3.0, length * 0.06),
                   min(length * 0.38, circumference * 0.62))
        if rise >= length * 0.72 or gusset_edge >= rise:
            return _unknown(
                "UNKNOWN_TROUSER_GUSSET_DOES_NOT_FIT",
                "the proposed gusset cannot fit inside the proposed leg rise",
                side=side, leg_length_cm=length, rise_cm=rise,
                gusset_edge_cm=gusset_edge)
        crotch_y = length - rise
        gusset_y = crotch_y - gusset_edge
        if gusset_y <= 0.0:
            return _unknown(
                "UNKNOWN_TROUSER_GUSSET_DOES_NOT_FIT",
                "the proposed gusset would consume the full inseam",
                side=side, gusset_join_y_cm=gusset_y)
        # Front and back are deliberately separate even when the preliminary
        # geometry is symmetric.  They may diverge in a later approved block;
        # collapsing them now would erase centre-front/centre-back topology.
        points: List[Point] = [
            (0.0, 0.0), (hem_width, 0.0), (panel_width, length),
            (crotch_extension, length), (0.0, crotch_y), (0.0, gusset_y),
        ]
        labels = ("hem", "outseam", "waist", "rise", "gusset", "inseam")
        for panel in ("front", "back"):
            piece = _piece(
                f"{node['node_id']}:{panel}", str(node["node_id"]), side,
                panel, points, labels, garment_unit, primitive_kind="TUBE")
            pieces.append(piece)
            by_key[(side, panel)] = piece
        geometry_records.append({
            "side": side,
            "state": "PROPOSED",
            "leg_length_cm": length,
            "declared_leg_circumference_cm": circumference,
            "derived_panel_width_cm": panel_width,
            "derived_hem_width_cm": hem_width,
            "derived_rise_cm": rise,
            "derived_crotch_extension_cm": crotch_extension,
            "basis": "bounded structural construction from TUBE and GUSSET dimensions",
            "breaks_when": "a target-wearer trouser block or approved rise/hip measurements are supplied",
            "not_measured_from_image": True,
        })

    half_length = gusset_dimensions["length_cm"] / 2.0
    half_width = gusset_dimensions["width_cm"] / 2.0
    gusset_points: List[Point] = [
        (0.0, -half_length), (half_width, 0.0),
        (0.0, half_length), (-half_width, 0.0),
    ]
    gusset_piece = _piece(
        str(gusset["node_id"]), str(gusset["node_id"]), "centre", "gusset",
        gusset_points, ("left_front", "right_front", "right_back", "left_back"),
        garment_unit, primitive_kind="GUSSET")
    pieces.append(gusset_piece)

    seams: List[Dict[str, Any]] = []
    for side in ("left", "right"):
        front, back = by_key[(side, "front")], by_key[(side, "back")]
        seams.append(_seam(f"trouser-outseam-{side}", front, "e1", back, "e1",
                           "LEG_OUTSEAM"))
        seams.append(_seam(f"trouser-inseam-{side}", front, "e5", back, "e5",
                           "LEG_INSEAM"))
    seams.extend([
        _seam("trouser-centre-front", by_key[("left", "front")], "e3",
              by_key[("right", "front")], "e3", "CENTRE_FRONT_RISE"),
        _seam("trouser-centre-back", by_key[("left", "back")], "e3",
              by_key[("right", "back")], "e3", "CENTRE_BACK_RISE"),
    ])
    gusset_targets = (
        ("e0", by_key[("left", "front")]),
        ("e1", by_key[("right", "front")]),
        ("e2", by_key[("right", "back")]),
        ("e3", by_key[("left", "back")]),
    )
    for index, (gusset_edge_name, target) in enumerate(gusset_targets, 1):
        seams.append(_seam(
            f"trouser-gusset-{index}", gusset_piece, gusset_edge_name,
            target, "e4", "CROTCH_GUSSET"))

    seam_balance = []
    piece_by_id = {piece["piece_id"]: piece for piece in pieces}
    for seam in seams:
        a = seam["a"]
        b = seam["b"]
        a_length = float(piece_by_id[a["piece_id"]]["edges"][a["edge"]]["length"])
        b_length = float(piece_by_id[b["piece_id"]]["edges"][b["edge"]]["length"])
        seam_balance.append({
            "operation_id": seam["operation_id"],
            "a_length_cm": a_length,
            "b_length_cm": b_length,
            "difference_cm": round(a_length - b_length, 6),
            "geometrically_equal": abs(a_length - b_length) <= 1.0e-5,
        })
    if not all(row["geometrically_equal"] for row in seam_balance):
        return _unknown(
            "UNKNOWN_TROUSER_SEAM_BALANCE",
            "the deterministic expansion produced unequal paired boundaries",
            seam_balance=seam_balance)

    result = {
        "schema": SCHEMA,
        "verdict": ANSWER,
        "state": "PROPOSED",
        "candidate_state": candidate_state,
        "garment_unit": garment_unit,
        "source_nodes": [str(value) for value in ids],
        "pieces": pieces,
        "seams": seams,
        "seam_balance": seam_balance,
        "geometry_records": geometry_records,
        "authority": {
            "observed": False,
            "approved_dimensions": False,
            "manufacturing_validated": False,
        },
        "limitations": [
            "rise, waist shaping and crotch extension are bounded structural proposals",
            "front and back panels are preliminary symmetric geometry",
            "target wearer measurements, closure, ease, seam allowance and construction method remain unresolved",
        ],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["digest"] = _digest(result)
    return result


def find_and_draft(structure: Mapping[str, Any], *,
                   candidate_state: str = "PROPOSED") -> Dict[str, Any]:
    """Find exactly one explicit pair in a structure or return typed UNKNOWN."""
    if not isinstance(structure, Mapping):
        return _unknown("UNKNOWN_TROUSER_STRUCTURE", "structure must be an object")
    raw_nodes = structure.get("nodes")
    if (not isinstance(raw_nodes, Sequence)
            or isinstance(raw_nodes, (str, bytes))):
        return _unknown("UNKNOWN_TROUSER_STRUCTURE", "structure.nodes must be an array")
    tubes = [node for node in raw_nodes
             if isinstance(node, Mapping) and str(node.get("kind", "")) == "TUBE"]
    gussets = [node for node in raw_nodes
               if isinstance(node, Mapping) and str(node.get("kind", "")) == "GUSSET"]
    left = [node for node in tubes if _side(node) == "left"]
    right = [node for node in tubes if _side(node) == "right"]
    if len(left) != 1 or len(right) != 1 or len(gussets) != 1:
        return _unknown(
            "UNKNOWN_TROUSER_TOPOLOGY_CARDINALITY",
            "the structural expansion requires exactly one left leg, one right leg and one gusset",
            left_count=len(left), right_count=len(right),
            gusset_count=len(gussets))
    return draft_pair(left[0], right[0], gussets[0],
                      candidate_state=candidate_state)


__all__ = ["ANSWER", "SCHEMA", "draft_pair", "find_and_draft"]
