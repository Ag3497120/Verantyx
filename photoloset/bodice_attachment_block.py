# -*- coding: utf-8 -*-
"""Expand circumference-level bodice attachments into addressable pieces.

``garment.structure.v1`` deliberately lets a proposal say that one lower
volume or collar meets one whole waist/neck loop.  A drafted bodice, however,
has separate front/back boundary edges.  Mapping that loop to an arbitrary
single ``eN`` edge creates a pattern that looks connected in the graph while
being impossible to sew geometrically.

This module performs the missing deterministic lowering step.  It consumes
only an already drafted BODY_SHELL bridge and explicit JOIN operations.  A
lower volume becomes one panel per real waist edge; a collar becomes one
segment per real neckline edge.  Every generated dimension remains PROPOSED,
and any reconciliation against a model-supplied circumference is reported as
an approval-required adjustment rather than hidden.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


ANSWER = "ANSWER"
SCHEMA = "garment.bodice-attachment-block.v1"
Point = Tuple[float, float]
_TOLERANCE_CM = 0.3


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "why": why,
        "how_to_close": (
            "supply one explicit waist/neck JOIN whose drafted boundary can "
            "be expanded into finite positive front/back segments"
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


def _area(points: Sequence[Point]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2.0


def _edges(points: Sequence[Point]) -> Dict[str, Dict[str, Any]]:
    return {
        f"e{index}": {
            "points": [[round(a[0], 6), round(a[1], 6)],
                       [round(b[0], 6), round(b[1], 6)]],
            "length": round(math.hypot(b[0] - a[0], b[1] - a[1]), 6),
        }
        for index, (a, b) in enumerate(zip(points, points[1:] + points[:1]))
    }


def _unit(node: Mapping[str, Any]) -> Optional[str]:
    attributes = node.get("attributes", {})
    value = attributes.get("garment_unit") if isinstance(attributes, Mapping) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _piece(node: Mapping[str, Any], piece_id: str, points: Sequence[Point], *,
           role: str, segment: str, garment_unit: str) -> Dict[str, Any]:
    attributes = copy.deepcopy(dict(node.get("attributes", {})))
    attributes.update({
        "garment_unit": garment_unit,
        "source_node_id": str(node["node_id"]),
        "expanded_from_circumference_port": True,
        "segment": segment,
        "dimension_authority": "PROPOSED_INPUT_STRUCTURE",
        "target_wearer_measurement": False,
    })
    rounded = [[round(x, 6), round(y, 6)] for x, y in points]
    return {
        "piece_id": piece_id,
        "name": piece_id,
        "node_id": piece_id,
        "source_node_id": str(node["node_id"]),
        "primitive_kind": str(node["kind"]),
        "layer": int(node.get("layer", 0)),
        "role": role,
        "segment": segment,
        "outline": rounded,
        "edges": _edges(points),
        "area_cm2": round(_area(points), 6),
        "cut_count": 1,
        "grain": {"direction": "parallel_to_height", "state": "PROPOSED"},
        "transforms": [],
        "attributes": attributes,
        "provenance": {
            "method": "deterministic circumference-to-real-edge expansion",
            "source_node": str(node["node_id"]),
            "state": "PROPOSED",
            "corpus_used": False,
            "image_measurements_claimed": False,
        },
    }


def _seam(operation_id: str, a_piece: Mapping[str, Any], a_edge: str,
          b_piece: Mapping[str, Any], b_edge: str, role: str, *,
          source_operation_id: str) -> Dict[str, Any]:
    return {
        "operation_id": operation_id,
        "source_operation_id": source_operation_id,
        "kind": "JOIN",
        "construction_role": role,
        "a": {"piece_id": a_piece["piece_id"], "edge": a_edge},
        "b": {"piece_id": b_piece["piece_id"], "edge": b_edge},
        "state": "PROPOSED",
        "manufacturing_validated": False,
    }


def _body_boundaries(body_pieces: Sequence[Mapping[str, Any]],
                     prefix: str) -> Tuple[Optional[List[Tuple[Mapping[str, Any], str, float, str]]],
                                           Optional[Dict[str, Any]]]:
    ordered: List[Tuple[Mapping[str, Any], str, float, str]] = []
    role_order = ("front_bodice", "back_bodice")
    for role in role_order:
        piece = next((row for row in body_pieces if row.get("role") == role), None)
        if piece is None:
            return None, _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_BODY_PIECES",
                f"drafted body lacks {role}")
        groups = piece.get("boundary_edge_groups", {})
        edges = piece.get("edges", {})
        if not isinstance(groups, Mapping) or not isinstance(edges, Mapping):
            return None, _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_BOUNDARY_GROUPS",
                f"{piece.get('piece_id')} lacks typed boundary edge groups")
        names = sorted(name for name in groups if str(name).startswith(prefix))
        if not names:
            return None, _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_BOUNDARY_MISSING",
                f"{piece.get('piece_id')} has no {prefix} boundary")
        # right before left keeps the same deterministic order as the full
        # bodice expansion.  A future curved-edge compiler may provide more
        # than one eN per named group; all remain independently addressable.
        names.sort(key=lambda name: ("right" not in str(name), str(name)))
        for name in names:
            raw_edge_names = groups[name]
            if not isinstance(raw_edge_names, Sequence):
                return None, _unknown(
                    "UNKNOWN_BODICE_ATTACHMENT_BOUNDARY_GROUPS",
                    f"{piece.get('piece_id')}/{name} is not an edge list")
            for edge_name in raw_edge_names:
                record = edges.get(edge_name)
                length = record.get("length") if isinstance(record, Mapping) else None
                if not _positive(length):
                    return None, _unknown(
                        "UNKNOWN_BODICE_ATTACHMENT_EDGE_LENGTH",
                        f"{piece.get('piece_id')}/{edge_name} has no positive length")
                ordered.append((piece, str(edge_name), float(length), str(name)))
    return ordered, None


def _node_by_id(graph: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    nodes = graph.get("nodes", [])
    if not isinstance(nodes, Sequence) or isinstance(nodes, (str, bytes)):
        return {}
    return {str(node["node_id"]): node for node in nodes
            if isinstance(node, Mapping) and isinstance(node.get("node_id"), str)}


def _port_interface(node: Mapping[str, Any], port_id: str) -> Optional[str]:
    ports = node.get("ports", [])
    if not isinstance(ports, Sequence):
        return None
    for port in ports:
        if isinstance(port, Mapping) and port.get("port_id") == port_id:
            value = port.get("interface")
            return str(value) if isinstance(value, str) else None
    return None


def _relation_other(operation: Mapping[str, Any], body_id: str,
                    nodes: Mapping[str, Mapping[str, Any]]) -> Optional[Tuple[Mapping[str, Any], str]]:
    if operation.get("kind") != "JOIN":
        return None
    source = operation.get("source")
    target = operation.get("target")
    if not isinstance(source, Mapping) or not isinstance(target, Mapping):
        return None
    source_id, target_id = str(source.get("node_id", "")), str(target.get("node_id", ""))
    if source_id == body_id and target_id in nodes:
        interface = _port_interface(nodes[source_id], str(source.get("port_id", "")))
        return nodes[target_id], interface or ""
    if target_id == body_id and source_id in nodes:
        interface = _port_interface(nodes[target_id], str(target.get("port_id", "")))
        return nodes[source_id], interface or ""
    return None


def _lower_expansion(node: Mapping[str, Any], boundaries: Sequence[Tuple[Mapping[str, Any], str, float, str]],
                     *, operation_id: str, garment_unit: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    dimensions = node.get("dimensions", {})
    kind = str(node.get("kind", ""))
    if not isinstance(dimensions, Mapping) or kind not in {"FLARE", "FRUSTUM", "TUBE"}:
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_LOWER_KIND",
            f"{node.get('node_id')} is not a supported lower volume")
    height_name = "length_cm" if kind == "TUBE" else "height_cm"
    bottom_name = "circumference_cm" if kind == "TUBE" else "bottom_circumference_cm"
    if not _positive(dimensions.get(height_name)) or not _positive(dimensions.get(bottom_name)):
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_LOWER_DIMENSIONS",
            f"{node.get('node_id')} lacks finite lower dimensions")
    height = float(dimensions[height_name])
    total_top = sum(row[2] for row in boundaries)
    total_bottom = float(dimensions[bottom_name])
    delta = (total_bottom - total_top) / len(boundaries)
    bottom_lengths = [row[2] + delta for row in boundaries]
    if any(length <= 0.0 for length in bottom_lengths):
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_LOWER_GEOMETRY",
            "bottom circumference cannot be distributed across waist segments",
            total_top_cm=total_top, total_bottom_cm=total_bottom)
    pieces: List[Dict[str, Any]] = []
    seams: List[Dict[str, Any]] = []
    for index, ((body_piece, body_edge, top, semantic), bottom) in enumerate(
            zip(boundaries, bottom_lengths), 1):
        points = [(-bottom / 2.0, 0.0), (bottom / 2.0, 0.0),
                  (top / 2.0, height), (-top / 2.0, height)]
        piece = _piece(
            node, f"{node['node_id']}:waist-{index:02d}", points,
            role="lower_waist_segment", segment=semantic,
            garment_unit=garment_unit)
        pieces.append(piece)
        seams.append(_seam(
            f"{operation_id}:waist-{index:02d}", piece, "e2",
            body_piece, body_edge, "WAIST_JOIN",
            source_operation_id=operation_id))
    for index, piece in enumerate(pieces):
        other = pieces[(index + 1) % len(pieces)]
        seams.append(_seam(
            f"{operation_id}:lower-side-{index + 1:02d}", piece, "e1",
            other, "e3", "LOWER_SIDE_SEAM",
            source_operation_id=operation_id))
    declared_top_name = ("circumference_cm" if kind == "TUBE"
                         else "top_circumference_cm")
    declared_top = dimensions.get(declared_top_name)
    adjustment = None
    if _positive(declared_top):
        adjustment = {
            "dimension": declared_top_name,
            "declared_cm": float(declared_top),
            "drafted_from_body_edges_cm": round(total_top, 6),
            "delta_cm": round(total_top - float(declared_top), 6),
            "state": "PROPOSED_RECONCILIATION",
            "requires_human_approval": abs(total_top - float(declared_top)) > _TOLERANCE_CM,
        }
    return {
        "pieces": pieces,
        "seams": seams,
        "adjustments": [adjustment] if adjustment else [],
        "method": "one lower panel per drafted bodice waist edge",
    }, None


def _collar_expansion(node: Mapping[str, Any], boundaries: Sequence[Tuple[Mapping[str, Any], str, float, str]],
                      *, operation_id: str, garment_unit: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    dimensions = node.get("dimensions", {})
    if (node.get("kind") != "COLLAR" or not isinstance(dimensions, Mapping)
            or not _positive(dimensions.get("length_cm"))
            or not _positive(dimensions.get("width_cm"))):
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_COLLAR_DIMENSIONS",
            f"{node.get('node_id')} lacks finite collar dimensions")
    width = float(dimensions["width_cm"])
    pieces: List[Dict[str, Any]] = []
    seams: List[Dict[str, Any]] = []
    for index, (body_piece, body_edge, length, semantic) in enumerate(boundaries, 1):
        points = [(-length / 2.0, 0.0), (length / 2.0, 0.0),
                  (length / 2.0, width), (-length / 2.0, width)]
        piece = _piece(
            node, f"{node['node_id']}:neck-{index:02d}", points,
            role="collar_segment", segment=semantic,
            garment_unit=garment_unit)
        pieces.append(piece)
        seams.append(_seam(
            f"{operation_id}:neck-{index:02d}", piece, "e0",
            body_piece, body_edge, "NECKLINE_JOIN",
            source_operation_id=operation_id))
    # Join the four sections at front centre and both shoulders; leave centre
    # back open because the rear closure is unseen in a front-only image.
    for index in range(len(pieces) - 1):
        seams.append(_seam(
            f"{operation_id}:collar-section-{index + 1:02d}",
            pieces[index], "e1", pieces[index + 1], "e3",
            "COLLAR_SECTION_JOIN", source_operation_id=operation_id))
    drafted = sum(row[2] for row in boundaries)
    declared = float(dimensions["length_cm"])
    return {
        "pieces": pieces,
        "seams": seams,
        "adjustments": [{
            "dimension": "length_cm",
            "declared_cm": declared,
            "drafted_from_body_edges_cm": round(drafted, 6),
            "delta_cm": round(drafted - declared, 6),
            "state": "PROPOSED_RECONCILIATION",
            "requires_human_approval": abs(drafted - declared) > _TOLERANCE_CM,
        }],
        "centre_back_opening": {
            "state": "PROPOSED",
            "basis": "front-only rear closure is unobserved; open edge retained",
        },
        "method": "one collar section per drafted bodice neckline edge",
    }, None


def _band_expansion(node: Mapping[str, Any], boundaries: Sequence[Tuple[Mapping[str, Any], str, float, str]],
                    *, operation_id: str, garment_unit: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Segment one loop band across the bodice's real boundary edges."""
    dimensions = node.get("dimensions", {})
    if (node.get("kind") != "BAND" or not isinstance(dimensions, Mapping)
            or not _positive(dimensions.get("length_cm"))
            or not _positive(dimensions.get("width_cm"))):
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_BAND_DIMENSIONS",
            f"{node.get('node_id')} lacks finite band dimensions")
    width = float(dimensions["width_cm"])
    pieces: List[Dict[str, Any]] = []
    seams: List[Dict[str, Any]] = []
    for index, (body_piece, body_edge, length, semantic) in enumerate(boundaries, 1):
        points = [(-length / 2.0, 0.0), (length / 2.0, 0.0),
                  (length / 2.0, width), (-length / 2.0, width)]
        piece = _piece(
            node, f"{node['node_id']}:band-{index:02d}", points,
            role="fitted_band_segment", segment=semantic,
            garment_unit=garment_unit)
        pieces.append(piece)
        seams.append(_seam(
            f"{operation_id}:band-{index:02d}", piece, "e0",
            body_piece, body_edge, "BAND_JOIN",
            source_operation_id=operation_id))
    for index in range(len(pieces) - 1):
        seams.append(_seam(
            f"{operation_id}:band-section-{index + 1:02d}",
            pieces[index], "e1", pieces[index + 1], "e3",
            "BAND_SECTION_JOIN", source_operation_id=operation_id))
    drafted = sum(row[2] for row in boundaries)
    declared = float(dimensions["length_cm"])
    return {
        "pieces": pieces,
        "seams": seams,
        "adjustments": [{
            "dimension": "length_cm", "declared_cm": declared,
            "drafted_from_body_edges_cm": round(drafted, 6),
            "delta_cm": round(drafted - declared, 6),
            "state": "PROPOSED_RECONCILIATION",
            "requires_human_approval": abs(drafted - declared) > _TOLERANCE_CM,
        }],
        "centre_back_opening": {
            "state": "PROPOSED",
            "basis": "front-only closure location is unobserved; one band edge remains open",
        },
        "method": "one fitted BAND section per drafted bodice boundary edge",
    }, None


def _hood_expansion(node: Mapping[str, Any], boundaries: Sequence[Tuple[Mapping[str, Any], str, float, str]],
                    *, operation_id: str, garment_unit: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Create a seam-balanced segmented hood proposal for a front-only view.

    A single image does not identify the actual hood dart/centre seam.  Four
    rectangular panels are therefore an explicit candidate, not a copied
    manufacturing method: every neckline edge is exact, adjacent panel seams
    are equal, and the unresolved centre-front opening stays visible.
    """
    dimensions = node.get("dimensions", {})
    if (node.get("kind") != "HOOD" or not isinstance(dimensions, Mapping)
            or not all(_positive(dimensions.get(name))
                       for name in ("height_cm", "width_cm", "depth_cm"))):
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_HOOD_DIMENSIONS",
            f"{node.get('node_id')} lacks finite hood dimensions")
    panel_height = float(dimensions["height_cm"])
    pieces: List[Dict[str, Any]] = []
    seams: List[Dict[str, Any]] = []
    for index, (body_piece, body_edge, length, semantic) in enumerate(boundaries, 1):
        points = [(-length / 2.0, 0.0), (length / 2.0, 0.0),
                  (length / 2.0, panel_height), (-length / 2.0, panel_height)]
        piece = _piece(
            node, f"{node['node_id']}:hood-{index:02d}", points,
            role="segmented_hood_panel", segment=semantic,
            garment_unit=garment_unit)
        pieces.append(piece)
        seams.append(_seam(
            f"{operation_id}:neck-{index:02d}", piece, "e0",
            body_piece, body_edge, "HOOD_NECKLINE_JOIN",
            source_operation_id=operation_id))
    for index in range(len(pieces) - 1):
        seams.append(_seam(
            f"{operation_id}:hood-panel-{index + 1:02d}",
            pieces[index], "e1", pieces[index + 1], "e3",
            "HOOD_PANEL_JOIN", source_operation_id=operation_id))
    drafted = sum(row[2] for row in boundaries)
    declared = float(dimensions["width_cm"])
    return {
        "pieces": pieces,
        "seams": seams,
        "adjustments": [{
            "dimension": "width_cm_as_preview_neck_edge",
            "declared_cm": declared,
            "drafted_from_body_edges_cm": round(drafted, 6),
            "delta_cm": round(drafted - declared, 6),
            "state": "PROPOSED_RECONCILIATION",
            "requires_human_approval": abs(drafted - declared) > _TOLERANCE_CM,
        }],
        "centre_front_opening": {
            "state": "PROPOSED",
            "basis": "front-only image does not establish hood opening/closure construction",
        },
        "method": "four seam-balanced hood panels; explicit front-only construction candidate",
    }, None


def _gather_expansion(node: Mapping[str, Any], target_pieces: Sequence[Mapping[str, Any]],
                      operation: Mapping[str, Any], *,
                      garment_unit: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    dimensions = node.get("dimensions", {})
    if (node.get("kind") != "BAND" or not isinstance(dimensions, Mapping)
            or not _positive(dimensions.get("length_cm"))
            or not _positive(dimensions.get("width_cm"))):
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_GATHER_SOURCE",
            f"{node.get('node_id')} is not a finite BAND ruffle")
    target_lengths: List[float] = []
    for piece in target_pieces:
        edges = piece.get("edges", {})
        record = edges.get("e0") if isinstance(edges, Mapping) else None
        length = record.get("length") if isinstance(record, Mapping) else None
        if not _positive(length):
            return None, _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_GATHER_TARGET",
                f"{piece.get('piece_id')} has no addressable hem edge")
        target_lengths.append(float(length))
    target_total = sum(target_lengths)
    parameters = operation.get("parameters", {})
    parameters = parameters if isinstance(parameters, Mapping) else {}
    declared_source = float(dimensions["length_cm"])
    raw_ratio = parameters.get("ratio")
    ratio = float(raw_ratio) if _positive(raw_ratio) else declared_source / target_total
    if not math.isfinite(ratio) or ratio <= 1.0:
        return None, _unknown(
            "UNKNOWN_BODICE_ATTACHMENT_GATHER_RATIO",
            "ruffle source must be longer than the assembled target hem",
            ratio=ratio, source_cm=declared_source, target_cm=target_total)
    width = float(dimensions["width_cm"])
    operation_id = str(operation.get("operation_id", ""))
    pieces: List[Dict[str, Any]] = []
    seams: List[Dict[str, Any]] = []
    for index, (target, target_length) in enumerate(
            zip(target_pieces, target_lengths), 1):
        source_length = target_length * ratio
        points = [(-source_length / 2.0, 0.0), (source_length / 2.0, 0.0),
                  (source_length / 2.0, width), (-source_length / 2.0, width)]
        piece = _piece(
            node, f"{node['node_id']}:gather-{index:02d}", points,
            role="gathered_ruffle_segment",
            segment=str(target.get("segment", f"segment-{index:02d}")),
            garment_unit=garment_unit)
        pieces.append(piece)
        row = _seam(
            f"{operation_id}:gather-{index:02d}", piece, "e0",
            target, "e0", "GATHERED_HEM",
            source_operation_id=operation_id)
        row["kind"] = "GATHER"
        row["gather_ratio"] = round(ratio, 6)
        seams.append(row)
    for index, piece in enumerate(pieces):
        other = pieces[(index + 1) % len(pieces)]
        seams.append(_seam(
            f"{operation_id}:ruffle-side-{index + 1:02d}", piece, "e1",
            other, "e3", "RUFFLE_SIDE_SEAM",
            source_operation_id=operation_id))
    drafted_source = target_total * ratio
    return {
        "pieces": pieces,
        "seams": seams,
        "adjustments": [{
            "dimension": "length_cm",
            "declared_cm": declared_source,
            "drafted_from_target_and_ratio_cm": round(drafted_source, 6),
            "delta_cm": round(drafted_source - declared_source, 6),
            "state": "PROPOSED_RECONCILIATION",
            "requires_human_approval": abs(drafted_source - declared_source) > _TOLERANCE_CM,
        }],
        "method": "one gathered BAND segment per expanded lower hem edge",
        "ratio": ratio,
    }, None


def expand(graph: Mapping[str, Any], body_bridge: Mapping[str, Any], *,
           candidate_state: str = "PROPOSED") -> Dict[str, Any]:
    """Expand direct BODY_SHELL waist/neck JOINs without raising authority."""
    if candidate_state not in {"PROPOSED", "APPROVED"}:
        return _unknown("UNKNOWN_BODICE_ATTACHMENT_CANDIDATE_STATE",
                        "candidate_state must be PROPOSED or APPROVED")
    nodes = _node_by_id(graph)
    expansion = body_bridge.get("expansion", {})
    source_nodes = expansion.get("source_nodes", []) if isinstance(expansion, Mapping) else []
    body_ids = [node_id for node_id in source_nodes
                if node_id in nodes and nodes[node_id].get("kind") == "BODY_SHELL"]
    if len(body_ids) != 1:
        return _unknown("UNKNOWN_BODICE_ATTACHMENT_BODY",
                        "body bridge must identify exactly one BODY_SHELL")
    body_id = body_ids[0]
    pieces_by_node = body_bridge.get("pieces_by_node", {})
    body_pieces = pieces_by_node.get(body_id, []) if isinstance(pieces_by_node, Mapping) else []
    if not isinstance(body_pieces, Sequence) or len(body_pieces) != 2:
        return _unknown("UNKNOWN_BODICE_ATTACHMENT_BODY_PIECES",
                        "body bridge must contain drafted front/back pieces")
    body_unit = _unit(nodes[body_id]) or "candidate"
    generated: Dict[str, List[Dict[str, Any]]] = {}
    seams: List[Dict[str, Any]] = []
    consumed: List[str] = []
    records: List[Dict[str, Any]] = []
    seen_interfaces: Dict[str, str] = {}
    operations = graph.get("operations", [])
    if not isinstance(operations, Sequence):
        return _unknown("UNKNOWN_BODICE_ATTACHMENT_OPERATIONS",
                        "graph operations must be an array")
    for operation in operations:
        if not isinstance(operation, Mapping):
            continue
        relation = _relation_other(operation, body_id, nodes)
        if relation is None:
            continue
        child, interface = relation
        kind = str(child.get("kind", ""))
        if interface == "waist" and kind in {"FLARE", "FRUSTUM", "TUBE"}:
            attributes = child.get("attributes", {})
            shape = str(attributes.get("shape", "")).lower() if isinstance(attributes, Mapping) else ""
            side = str(attributes.get("side", "")).lower() if isinstance(attributes, Mapping) else ""
            if "trouser" in shape or side in {"left", "right"}:
                continue
            prefix = "waist"
            maker = _lower_expansion
        elif interface == "neck" and kind == "COLLAR":
            prefix = "neckline"
            maker = _collar_expansion
        elif interface == "neck" and kind == "HOOD":
            prefix = "neckline"
            maker = _hood_expansion
        elif interface == "band-waist" and kind == "BAND":
            prefix = "waist"
            maker = _band_expansion
        elif interface == "band-neck" and kind == "BAND":
            prefix = "neckline"
            maker = _band_expansion
        else:
            continue
        if interface in seen_interfaces:
            return _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_MULTIPLE_CHILDREN",
                f"multiple {interface} attachments need an ordered composite rule",
                first_operation_id=seen_interfaces[interface],
                second_operation_id=operation.get("operation_id"))
        child_unit = _unit(child)
        if child_unit is not None and child_unit != body_unit:
            return _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_GARMENT_UNIT",
                f"{child.get('node_id')} and {body_id} have different garment_unit values")
        boundaries, error = _body_boundaries(body_pieces, prefix)
        if error or boundaries is None:
            return error or _unknown("UNKNOWN_BODICE_ATTACHMENT_BOUNDARY", prefix)
        operation_id = str(operation.get("operation_id", ""))
        result, error = maker(child, boundaries, operation_id=operation_id,
                              garment_unit=body_unit)
        if error or result is None:
            return error or _unknown("UNKNOWN_BODICE_ATTACHMENT_EXPANSION", operation_id)
        child_id = str(child["node_id"])
        generated[child_id] = result["pieces"]
        seams.extend(result["seams"])
        consumed.append(operation_id)
        seen_interfaces[interface] = operation_id
        records.append({
            "kind": f"BODICE_{interface.upper()}_ATTACHMENT",
            "state": "PROPOSED",
            "source_operation_id": operation_id,
            "source_nodes": [body_id, child_id],
            "generated_pieces": [piece["piece_id"] for piece in result["pieces"]],
            "adjustments": result.get("adjustments", []),
            "method": result["method"],
            "manufacturing_guarantee": False,
            **({"centre_back_opening": result["centre_back_opening"]}
               if "centre_back_opening" in result else {}),
            **({"centre_front_opening": result["centre_front_opening"]}
               if "centre_front_opening" in result else {}),
        })
    # A ruffle attached to an expanded lower loop must be lowered to the same
    # physical segmentation.  Otherwise the generic compiler maps the whole
    # gathered circumference to one arbitrary panel edge.
    for operation in operations:
        if not isinstance(operation, Mapping) or operation.get("kind") != "GATHER":
            continue
        source = operation.get("source")
        target = operation.get("target")
        if not isinstance(source, Mapping) or not isinstance(target, Mapping):
            continue
        source_id, target_id = str(source.get("node_id", "")), str(target.get("node_id", ""))
        if target_id not in generated or source_id not in nodes:
            continue
        source_node = nodes[source_id]
        if source_node.get("kind") != "BAND":
            continue
        if source_id in generated:
            return _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_MULTIPLE_GATHER_TARGETS",
                f"{source_id} is already expanded by another relation")
        source_unit = _unit(source_node)
        if source_unit is not None and source_unit != body_unit:
            return _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_GARMENT_UNIT",
                f"{source_id} and {target_id} have different garment_unit values")
        result, error = _gather_expansion(
            source_node, generated[target_id], operation,
            garment_unit=body_unit)
        if error or result is None:
            return error or _unknown(
                "UNKNOWN_BODICE_ATTACHMENT_GATHER", str(operation.get("operation_id")))
        operation_id = str(operation.get("operation_id", ""))
        generated[source_id] = result["pieces"]
        seams.extend(result["seams"])
        consumed.append(operation_id)
        records.append({
            "kind": "SEGMENTED_GATHER_ATTACHMENT",
            "state": "PROPOSED",
            "source_operation_id": operation_id,
            "source_nodes": [source_id, target_id],
            "generated_pieces": [piece["piece_id"] for piece in result["pieces"]],
            "adjustments": result["adjustments"],
            "gather_ratio": round(float(result["ratio"]), 6),
            "method": result["method"],
            "manufacturing_guarantee": False,
        })
    output = {
        "schema": SCHEMA,
        "verdict": ANSWER,
        "state": "PROPOSED",
        "candidate_state": candidate_state,
        "pieces_by_node": generated,
        "seams": seams,
        "consumed_operation_ids": consumed,
        "expansions": records,
        "authority": {
            "observed": False,
            "approved_dimensions": False,
            "manufacturing_validated": False,
        },
    }
    output["digest"] = _digest(output)
    return output


__all__ = ["ANSWER", "SCHEMA", "expand"]
