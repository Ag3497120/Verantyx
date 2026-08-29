# -*- coding: utf-8 -*-
"""Build an inspectable manufacturing *preview* from a compiled pattern.

The input contract is ``garment.compiled-pattern.v1``.  Its outlines are sew
lines, not cut lines.  This adapter therefore refuses to invent seam
allowance.  A caller may either supply it explicitly or deliberately opt into
a documented ``PROPOSED`` default; the latter never makes an artifact
manufacturing-ready.

The output is deliberately useful without overstating its authority:

* every piece carries separate ``sew_line`` and ``cut_line`` geometry;
* cut quantity, grain state, seam-end notches and layer order remain visible;
* an SVG string can be inspected directly;
* the same marked draft is offered to the existing DXF R12 writer, while a
  typed refusal is preserved if that writer cannot consume it.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import html
import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import dxf as _dxf
from . import garment_marks as _marks
from . import garment_pattern as _pattern


ANSWER = "ANSWER"
INPUT_SCHEMA = "garment.compiled-pattern.v1"
SCHEMA = "garment.manufacturing-preview-bundle.v1"
PROPOSED_DEFAULT_CM = 1.0
INNER_CUT_LAYER = "INNER_CUT"
_GEOMETRY_EPSILON = 1.0e-8

_VALUE_KEYS = ("value_cm", "value", "cm")
_EXPLICIT_STATES = {"EXPLICIT", "OBSERVED", "MEASURED", "APPROVED"}
_PROPOSED_STATES = {"PROPOSED", "INFERRED"}


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "schema": SCHEMA,
        "why": why,
        "how_to_close": "supply the missing manufacturing field explicitly or approve a typed proposal",
        **detail,
    }


def _positive(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and float(value) > 0.0)


def _point_list(value: Any) -> Optional[List[List[float]]]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or len(value) < 3):
        return None
    points: List[List[float]] = []
    for point in value:
        if (not isinstance(point, Sequence) or isinstance(point, (str, bytes))
                or len(point) != 2):
            return None
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        points.append([x, y])
    return points


def _polygon_area(points: Sequence[Sequence[float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2.0


def _signed_area(points: Sequence[Sequence[float]]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(points, points[1:] + points[:1])) / 2.0


def _cross(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def _point_segment_distance(point: Sequence[float], a: Sequence[float],
                            b: Sequence[float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    if denominator <= _GEOMETRY_EPSILON ** 2:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = max(0.0, min(1.0, ((point[0] - a[0]) * dx
                           + (point[1] - a[1]) * dy) / denominator))
    return math.hypot(point[0] - (a[0] + t * dx),
                      point[1] - (a[1] + t * dy))


def _segments_intersect(a: Sequence[float], b: Sequence[float],
                        c: Sequence[float], d: Sequence[float]) -> bool:
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


def _simple_polygon(points: Sequence[Sequence[float]]) -> bool:
    count = len(points)
    tuples = [tuple(point) for point in points]
    if (count < 3 or len(set(tuples)) != count
            or _polygon_area(points) <= _GEOMETRY_EPSILON):
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


def _on_boundary(point: Sequence[float], polygon: Sequence[Sequence[float]]) -> bool:
    return any(_point_segment_distance(point, a, b) <= _GEOMETRY_EPSILON
               for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def _inside(point: Sequence[float], polygon: Sequence[Sequence[float]]) -> bool:
    if _on_boundary(point, polygon):
        return False
    inside = False
    x, y = point
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) == (b[1] > y):
            continue
        if a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]) > x:
            inside = not inside
    return inside


def _boundary_distance(a: Sequence[Sequence[float]],
                       b: Sequence[Sequence[float]]) -> float:
    return min(_point_segment_distance(point, c, d)
               for point in a for c, d in zip(b, b[1:] + b[:1]))


def _intersect(a: Sequence[Sequence[float]],
               b: Sequence[Sequence[float]]) -> bool:
    return any(_segments_intersect(p, q, r, s)
               for p, q in zip(a, a[1:] + a[:1])
               for r, s in zip(b, b[1:] + b[:1]))


def _validated_inner_cutouts(piece_id: str, outline: Sequence[Sequence[float]],
                             value: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, _unknown("UNKNOWN_INNER_CUT_CONTRACT",
                              f"{piece_id} inner_cutouts must be a list")
    result: List[Dict[str, Any]] = []
    ids = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            return None, _unknown("UNKNOWN_INNER_CUT_CONTRACT",
                                  f"{piece_id} inner cut must be an object")
        operation_id = str(raw.get("operation_id", "")).strip()
        contour_id = str(raw.get("contour_id", "")).strip()
        if not operation_id or not contour_id or contour_id in ids:
            return None, _unknown("UNKNOWN_INNER_CUT_ID",
                                  f"{piece_id} inner cut ids must be non-empty and unique")
        ids.add(contour_id)
        if raw.get("piece_id") != piece_id or raw.get("kind") != "CUTOUT":
            return None, _unknown("UNKNOWN_INNER_CUT_BINDING",
                                  f"{piece_id}/{contour_id} piece/kind binding differs")
        points = _point_list(raw.get("points"))
        if points is None or not _simple_polygon(points) or _signed_area(points) >= 0:
            return None, _unknown("UNKNOWN_INNER_CUT_GEOMETRY",
                                  f"{piece_id}/{contour_id} must be a finite simple clockwise contour")
        if (not all(_inside(point, outline) for point in points)
                or _intersect(points, outline)):
            return None, _unknown("UNKNOWN_INNER_CUT_OUTSIDE",
                                  f"{piece_id}/{contour_id} is not strictly inside its outer boundary")
        required = raw.get("minimum_clearance_cm")
        if not _positive(required):
            return None, _unknown("UNKNOWN_INNER_CUT_CLEARANCE",
                                  f"{piece_id}/{contour_id} needs positive minimum_clearance_cm")
        measured = min(_boundary_distance(points, outline),
                       _boundary_distance(outline, points))
        if measured + _GEOMETRY_EPSILON < float(required):
            return None, _unknown("UNKNOWN_INNER_CUT_CLEARANCE",
                                  f"{piece_id}/{contour_id} violates outer clearance")
        if not isinstance(raw.get("contour_edge_lineage"), list):
            return None, _unknown("UNKNOWN_INNER_CUT_LINEAGE",
                                  f"{piece_id}/{contour_id} lacks contour edge lineage")
        if not isinstance(raw.get("approval_binding"), Mapping):
            return None, _unknown("UNKNOWN_INNER_CUT_APPROVAL_BINDING",
                                  f"{piece_id}/{contour_id} lacks approval binding")
        front_digest = raw.get("source_front_boundary_digest")
        if front_digest is not None and (
                not isinstance(front_digest, str) or not front_digest.strip()
                or raw.get("source_front_boundary_digest_state")
                != "PROPOSED_LINEAGE_ONLY"
                or raw.get("source_front_boundary_semantics_observed") is not False):
            return None, _unknown(
                "UNKNOWN_INNER_CUT_FRONT_BOUNDARY_LINEAGE",
                f"{piece_id}/{contour_id} front-boundary digest must remain non-semantic PROPOSED lineage")
        expected_digest = raw.get("digest")
        payload = copy.deepcopy(dict(raw))
        payload.pop("digest", None)
        if expected_digest != _digest(payload):
            return None, _unknown("UNKNOWN_INNER_CUT_DIGEST",
                                  f"{piece_id}/{contour_id} digest does not match geometry and lineage")
        result.append(copy.deepcopy(dict(raw)))
    for index, first in enumerate(result):
        for second in result[index + 1:]:
            a, b = first["points"], second["points"]
            if _intersect(a, b) or _inside(a[0], b) or _inside(b[0], a):
                return None, _unknown("UNKNOWN_INNER_CUT_INTERSECTION",
                                      f"{piece_id} inner contours intersect or nest")
            required = max(float(first["minimum_clearance_cm"]),
                           float(second["minimum_clearance_cm"]))
            measured = min(_boundary_distance(a, b), _boundary_distance(b, a))
            if measured + _GEOMETRY_EPSILON < required:
                return None, _unknown("UNKNOWN_INNER_CUT_CLEARANCE",
                                      f"{piece_id} inner contours lack required clearance")
    return result, None


def _edges(points: Sequence[Sequence[float]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for index, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        result[f"e{index}"] = {
            "points": [[float(a[0]), float(a[1])],
                       [float(b[0]), float(b[1])]],
            "length": round(math.hypot(b[0] - a[0], b[1] - a[1]), 6),
        }
    return result


def _descriptor(value: Any, *, source: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Normalize one allowance value without erasing its evidence state."""
    if _positive(value):
        return {
            "value_cm": float(value),
            "state": "EXPLICIT",
            "basis": source,
            "assumption_breaks_when": None,
        }, None
    if not isinstance(value, Mapping):
        return None, _unknown("UNKNOWN_SEAM_ALLOWANCE_INVALID",
                              "seam_allowance_cm must be a positive number or typed object")
    raw = next((value[key] for key in _VALUE_KEYS if key in value), None)
    if not _positive(raw):
        return None, _unknown("UNKNOWN_SEAM_ALLOWANCE_INVALID",
                              "typed seam_allowance_cm needs a positive value_cm")
    state = str(value.get("state", "")).strip().upper()
    if state not in _EXPLICIT_STATES | _PROPOSED_STATES:
        return None, _unknown("UNKNOWN_SEAM_ALLOWANCE_STATE",
                              "typed seam allowance needs EXPLICIT/OBSERVED/MEASURED/APPROVED or PROPOSED/INFERRED state")
    basis = str(value.get("basis", "")).strip()
    breaks = str(value.get("assumption_breaks_when",
                           value.get("breaks_when", ""))).strip()
    if state in _PROPOSED_STATES and (not basis or not breaks):
        return None, _unknown(
            "UNKNOWN_PROPOSED_SEAM_ALLOWANCE_UNEXPLAINED",
            "a PROPOSED seam allowance must state its basis and when the assumption breaks")
    return {
        "value_cm": float(raw),
        "state": state,
        "basis": basis or source,
        "assumption_breaks_when": breaks or None,
    }, None


def _allowance_for_piece(raw: Any, piece_id: str,
                         edge_names: Sequence[str], *,
                         allow_proposed_default: bool,
                         proposed_default_cm: Any) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    selected = raw
    # A mapping can be either one typed descriptor, a piece map, or an edge map.
    if isinstance(raw, Mapping) and not any(key in raw for key in _VALUE_KEYS):
        if piece_id in raw:
            selected = raw[piece_id]
        elif "default" in raw:
            selected = raw["default"]

    if selected is None:
        if not allow_proposed_default:
            return None, _unknown(
                "UNKNOWN_SEAM_ALLOWANCE_MISSING",
                f"{piece_id} has no seam_allowance_cm; no cut line was generated",
                piece_id=piece_id)
        if not _positive(proposed_default_cm):
            return None, _unknown("UNKNOWN_PROPOSED_SEAM_ALLOWANCE_INVALID",
                                  "proposed_default_cm must be finite and positive")
        selected = {
            "value_cm": float(proposed_default_cm),
            "state": "PROPOSED",
            "basis": "caller explicitly enabled allow_proposed_default",
            "assumption_breaks_when": (
                "the seam type, material, finish, factory process or strength requirement needs a different allowance"),
        }

    edge_values: Dict[str, Dict[str, Any]] = {}
    is_edge_map = (isinstance(selected, Mapping)
                   and not any(key in selected for key in _VALUE_KEYS)
                   and any(key in selected for key in edge_names))
    for edge_name in edge_names:
        candidate = selected.get(edge_name) if is_edge_map else selected
        if candidate is None and allow_proposed_default:
            candidate = {
                "value_cm": float(proposed_default_cm),
                "state": "PROPOSED",
                "basis": f"missing {piece_id}/{edge_name}; caller explicitly enabled allow_proposed_default",
                "assumption_breaks_when": "this edge uses a construction-specific allowance",
            }
        if candidate is None:
            return None, _unknown(
                "UNKNOWN_SEAM_ALLOWANCE_MISSING",
                f"{piece_id}/{edge_name} has no seam_allowance_cm; no cut line was generated",
                piece_id=piece_id, edge=edge_name)
        descriptor, error = _descriptor(candidate, source=f"explicit {piece_id}/{edge_name} input")
        if error:
            error.update({"piece_id": piece_id, "edge": edge_name})
            return None, error
        edge_values[edge_name] = descriptor

    values = {record["value_cm"] for record in edge_values.values()}
    states = {record["state"] for record in edge_values.values()}
    state = "PROPOSED" if states & _PROPOSED_STATES else "EXPLICIT"
    record: Dict[str, Any] = {"state": state, "edges": edge_values}
    if len(values) == 1:
        record["value_cm"] = next(iter(values))
    return record, None


def _grain(piece: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    raw = piece.get("grain")
    if not isinstance(raw, Mapping):
        return None, _unknown("UNKNOWN_GRAIN_STATE_MISSING",
                              f"{piece['name']} needs a typed grain state")
    state = str(raw.get("state", "")).strip().upper()
    if state not in _EXPLICIT_STATES | _PROPOSED_STATES:
        return None, _unknown("UNKNOWN_GRAIN_STATE_MISSING",
                              f"{piece['name']} grain needs an explicit evidence state")
    direction = str(raw.get("direction", "")).strip()
    angle = raw.get("angle_deg")
    if angle is None:
        if direction == "parallel_to_height":
            angle = 90.0
        elif direction == "parallel_to_width":
            angle = 0.0
        else:
            return None, _unknown("UNKNOWN_GRAIN_DIRECTION",
                                  f"{piece['name']} grain direction cannot be converted to an angle")
    if (isinstance(angle, bool) or not isinstance(angle, (int, float))
            or not math.isfinite(float(angle))):
        return None, _unknown("UNKNOWN_GRAIN_DIRECTION",
                              f"{piece['name']} grain angle must be finite")
    record = _marks.grain_line(dict(piece), float(angle), raw.get("orientation"))
    record.update({
        "state": state,
        "source": copy.deepcopy(dict(raw)),
        "manufacturing_confirmed": state in _EXPLICIT_STATES,
    })
    return record, None


def _seam_endpoint_notches(seams: Sequence[Mapping[str, Any]],
                           pieces: Mapping[str, Mapping[str, Any]],
                           allowance: Mapping[str, Mapping[str, Any]]) -> Tuple[Optional[Dict[str, List[Dict[str, Any]]]], Optional[Dict[str, Any]]]:
    notches: Dict[str, List[Dict[str, Any]]] = {name: [] for name in pieces}
    seen = set()
    for index, seam in enumerate(seams):
        operation_id = str(seam.get("operation_id", f"seam-{index}"))
        for side in ("a", "b"):
            address = seam.get(side)
            if not isinstance(address, Mapping):
                return None, _unknown("UNKNOWN_SEAM_ADDRESS",
                                      f"{operation_id}/{side} does not name a piece and edge")
            piece_id = str(address.get("piece_id", ""))
            edge_name = str(address.get("edge", ""))
            piece = pieces.get(piece_id)
            if piece is None or edge_name not in piece["edges"]:
                return None, _unknown("UNKNOWN_SEAM_ADDRESS",
                                      f"{operation_id}/{side} points to unknown {piece_id}/{edge_name}")
            length = float(piece["edges"][edge_name]["length"])
            width = float(allowance[piece_id]["edges"][edge_name]["value_cm"])
            depth = round(min(_marks.NOTCH_DEPTH_CM, width / 2.0), 3)
            for endpoint, arc_cm in (("start", 0.0), ("end", length)):
                key = (piece_id, edge_name, round(arc_cm, 6), operation_id)
                if key in seen:
                    continue
                seen.add(key)
                notches[piece_id].append({
                    "edge": edge_name,
                    "arc_cm": round(arc_cm, 6),
                    "t": 0.0 if endpoint == "start" else 1.0,
                    "kind": "single",
                    "role": f"{operation_id}:{endpoint}",
                    "depth_cm": depth,
                    "layer": _marks.LAYER_NOTCH,
                    "basis": "deterministic seam endpoint",
                    "state": seam.get("state", "PROPOSED"),
                })
    return notches, None


def _notch_layer_records(piece: Mapping[str, Any],
                          notches: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for notch in notches:
        edge = piece["edges"][notch["edge"]]
        points = edge["points"]
        total = _marks.arc_lengths(points)[-1]
        base = _marks.at_arc(points, float(notch["arc_cm"]))
        ahead = _marks.at_arc(points, min(float(notch["arc_cm"]) + 0.5, total))
        back = _marks.at_arc(points, max(float(notch["arc_cm"]) - 0.5, 0.0))
        tx, ty = ahead[0] - back[0], ahead[1] - back[1]
        length = math.hypot(tx, ty) or 1.0
        nx, ny = ty / length, -tx / length
        end = [round(base[0] + nx * float(notch["depth_cm"]), 6),
               round(base[1] + ny * float(notch["depth_cm"]), 6)]
        records.append({
            "entity": "LINE", "layer": _dxf.LAYER_NOTCH,
            "piece_id": piece["name"],
            "start": [round(base[0], 6), round(base[1], 6)],
            "end": end, "role": notch["role"],
        })
    return records


def _layer_records(pieces: Sequence[Mapping[str, Any]],
                   notches: Mapping[str, Sequence[Mapping[str, Any]]],
                   grains: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for piece in pieces:
        piece_id = piece["name"]
        common = {"piece_id": piece_id, "cut_count": piece["cut_count"],
                  "garment_layer": piece["layer"]}
        records.extend([
            {"entity": "CLOSED_POLYLINE", "layer": _dxf.LAYER_SEW,
             "points": copy.deepcopy(piece["sew_line"]), **common},
            {"entity": "CLOSED_POLYLINE", "layer": _dxf.LAYER_CUT,
             "points": copy.deepcopy(piece["cut_line"]), **common},
        ])
        for cutout in piece.get("inner_cutouts", []):
            records.append({
                "entity": "CLOSED_POLYLINE",
                "layer": INNER_CUT_LAYER,
                "piece_id": piece_id,
                "operation_id": cutout["operation_id"],
                "contour_id": cutout["contour_id"],
                "contour_digest": cutout["digest"],
                "state": cutout["state"],
                "points": copy.deepcopy(cutout["points"]),
                **{key: value for key, value in common.items()
                   if key != "piece_id"},
            })
        records.extend(_notch_layer_records(piece, notches.get(piece_id, [])))
        grain = grains[piece_id]
        records.append({
            "entity": "LINE", "layer": _dxf.LAYER_GRAIN,
            "piece_id": piece_id,
            "start": copy.deepcopy(grain["line"][0]),
            "end": copy.deepcopy(grain["line"][1]),
            "state": grain["state"],
        })
        records.append({
            "entity": "TEXT", "layer": _dxf.LAYER_LABEL,
            "piece_id": piece_id,
            "text": f"{piece_id} x{piece['cut_count']}",
        })
    return records


def _svg_points(pieces: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, str], List[List[float]]]:
    """Reproduce garment_pattern.to_svg's translation without changing geometry."""
    x_cursor = 30.0
    result: Dict[Tuple[str, str], List[List[float]]] = {}
    for piece in pieces:
        outline_x = [float(point[0]) for point in piece["outline"]]
        shift = x_cursor - min(outline_x)
        xs = list(outline_x)
        xs.extend(float(point[0]) for point in piece["cut_line"])
        width = max(xs) - min(xs)
        for cutout in piece.get("inner_cutouts", []):
            result[(piece["name"], cutout["contour_id"])] = [
                [round(float(point[0]) + shift, 6),
                 round(float(point[1]) + 30.0, 6)]
                for point in cutout["points"]
            ]
        x_cursor += width + 20.0
    return result


def _inner_cut_manifest(pieces: Sequence[Mapping[str, Any]],
                        dxf_result: Mapping[str, Any]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    placement = dxf_result.get("placement")
    if not isinstance(placement, Mapping):
        return None, _unknown("UNKNOWN_INNER_CUT_DXF_PLACEMENT",
                              "DXF placement is required to bind inner cuts")
    svg = _svg_points(pieces)
    records: List[Dict[str, Any]] = []
    for piece in pieces:
        shift = placement.get(piece["name"])
        try:
            valid_shift = (isinstance(shift, Sequence)
                           and not isinstance(shift, (str, bytes))
                           and len(shift) == 2
                           and all(not isinstance(value, bool)
                                   and math.isfinite(float(value))
                                   for value in shift))
        except (TypeError, ValueError, OverflowError):
            valid_shift = False
        if not valid_shift:
            return None, _unknown("UNKNOWN_INNER_CUT_DXF_PLACEMENT",
                                  f"{piece['name']} has invalid DXF placement")
        dx, dy = float(shift[0]), float(shift[1])
        for cutout in piece.get("inner_cutouts", []):
            record = copy.deepcopy(dict(cutout))
            record["source_contour_digest"] = record.pop("digest")
            record["svg_points"] = copy.deepcopy(
                svg[(piece["name"], cutout["contour_id"])])
            record["dxf_points"] = [
                [round(float(point[0]) + dx, 4),
                 round(float(point[1]) + dy, 4)]
                for point in cutout["points"]
            ]
            record["svg_layer"] = INNER_CUT_LAYER
            record["dxf_layer"] = INNER_CUT_LAYER
            record["digest"] = _digest(record)
            records.append(record)
    return records, None


def _augment_svg(svg: str, records: Sequence[Mapping[str, Any]]) -> str:
    if not records:
        return svg
    nodes = []
    for row in records:
        points = " ".join(f"{float(x):.6f},{float(y):.6f}"
                          for x, y in row["svg_points"])
        attrs = {
            "data-layer": INNER_CUT_LAYER,
            "data-piece": row["piece_id"],
            "data-operation-id": row["operation_id"],
            "data-contour-id": row["contour_id"],
            "data-contour-digest": row["digest"],
            "data-state": row["state"],
            **({"data-source-front-boundary-digest":
                row["source_front_boundary_digest"]}
               if row.get("source_front_boundary_digest") else {}),
        }
        encoded = " ".join(
            f'{name}="{html.escape(str(value), quote=True)}"'
            for name, value in attrs.items())
        nodes.append(
            f'<polygon points="{points}" fill="none" stroke="#c50" '
            f'stroke-width="0.55" stroke-dasharray="1.5 1" {encoded}/>')
    marker = "</svg>"
    return svg.replace(marker, "\n" + "\n".join(nodes) + "\n" + marker, 1)


def _dxf_num(value: float) -> str:
    value = round(float(value), 4)
    if value == 0.0:
        value = 0.0
    return f"{value:.4f}"


def _dxf_inner_polyline(row: Mapping[str, Any]) -> str:
    metadata = {
        "piece_id": row["piece_id"],
        "operation_id": row["operation_id"],
        "contour_id": row["contour_id"],
        "digest": row["digest"],
        **({"source_front_boundary_digest":
            row["source_front_boundary_digest"]}
           if row.get("source_front_boundary_digest") else {}),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(metadata, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).decode("ascii")
    out = [f"999\ninner_cut_record_b64={encoded}\n",
           f"0\nPOLYLINE\n8\n{INNER_CUT_LAYER}\n66\n1\n70\n1\n"]
    for x, y in row["dxf_points"]:
        out.append(f"0\nVERTEX\n8\n{INNER_CUT_LAYER}\n10\n{_dxf_num(x)}\n"
                   f"20\n{_dxf_num(y)}\n30\n0.0\n")
    out.append("0\nSEQEND\n")
    return "".join(out)


def _augment_dxf(payload: Mapping[str, Any],
                 records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(payload))
    if not records or result.get("verdict") != ANSWER:
        return result
    text = result.get("text")
    if not isinstance(text, str):
        return {**result, "verdict": "UNKNOWN_INNER_CUT_DXF_TEXT"}
    table_pattern = r"(0\nTABLE\n2\nLAYER\n70\n)(\d+)(\n)"
    match = re.search(table_pattern, text)
    if match is None:
        return {**result, "verdict": "UNKNOWN_INNER_CUT_DXF_LAYER_TABLE"}
    text = re.sub(
        table_pattern,
        lambda found: found.group(1) + str(int(found.group(2)) + 1) + found.group(3),
        text, count=1)
    layer_end = text.find("0\nENDTAB\n", match.end())
    if layer_end < 0:
        return {**result, "verdict": "UNKNOWN_INNER_CUT_DXF_LAYER_TABLE"}
    declaration = (f"0\nLAYER\n2\n{INNER_CUT_LAYER}\n70\n0\n"
                   "62\n6\n6\nCONTINUOUS\n")
    text = text[:layer_end] + declaration + text[layer_end:]
    entity_marker = "0\nSECTION\n2\nENTITIES\n"
    entity_at = text.find(entity_marker)
    if entity_at < 0:
        return {**result, "verdict": "UNKNOWN_INNER_CUT_DXF_ENTITIES"}
    entity_at += len(entity_marker)
    entities = "".join(_dxf_inner_polyline(row) for row in records)
    text = text[:entity_at] + entities + text[entity_at:]
    layers = copy.deepcopy(dict(result.get("layers", {})))
    layers["inner_cut"] = INNER_CUT_LAYER
    result.update({
        "text": text,
        "layers": layers,
        "inner_cut_contours": len(records),
        "inner_cut_digest": _digest(list(records)),
    })
    return result


def build(compiled_pattern: Mapping[str, Any], *,
          seam_allowance_cm: Any = None,
          allow_proposed_default: bool = False,
          proposed_default_cm: Any = PROPOSED_DEFAULT_CM) -> Dict[str, Any]:
    """Create a deterministic, fail-closed manufacturing preview bundle."""
    if not isinstance(compiled_pattern, Mapping):
        return _unknown("UNKNOWN_COMPILED_PATTERN", "compiled pattern must be an object")
    if compiled_pattern.get("verdict") != ANSWER or compiled_pattern.get("schema") != INPUT_SCHEMA:
        return _unknown("UNKNOWN_COMPILED_PATTERN_SCHEMA",
                        f"expected an ANSWER with schema {INPUT_SCHEMA}")
    raw_pieces = compiled_pattern.get("pieces")
    if not isinstance(raw_pieces, list) or not raw_pieces:
        return _unknown("UNKNOWN_PATTERN_PIECES", "compiled pattern needs at least one piece")

    global_allowance = (seam_allowance_cm if seam_allowance_cm is not None
                        else compiled_pattern.get("seam_allowance_cm"))
    pieces: List[Dict[str, Any]] = []
    allowance_records: Dict[str, Dict[str, Any]] = {}
    grain_records: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}

    for raw_piece in raw_pieces:
        if not isinstance(raw_piece, Mapping):
            return _unknown("UNKNOWN_PATTERN_PIECE", "every piece must be an object")
        piece_id = str(raw_piece.get("piece_id", raw_piece.get("name", ""))).strip()
        if not piece_id or piece_id in by_name:
            return _unknown("UNKNOWN_PATTERN_PIECE_ID",
                            "piece_id/name must be non-empty and unique", piece_id=piece_id)
        outline = _point_list(raw_piece.get("outline"))
        if outline is None or _polygon_area(outline) <= 0.0:
            return _unknown("UNKNOWN_PATTERN_OUTLINE",
                            f"{piece_id} needs a finite non-zero polygon")
        cut_count = raw_piece.get("cut_count")
        if (isinstance(cut_count, bool) or not isinstance(cut_count, int)
                or cut_count <= 0):
            return _unknown("UNKNOWN_CUT_COUNT_MISSING",
                            f"{piece_id} needs an explicit positive cut_count")
        layer = raw_piece.get("layer", 0)
        if isinstance(layer, bool) or not isinstance(layer, int) or layer < 0:
            return _unknown("UNKNOWN_GARMENT_LAYER", f"{piece_id} layer must be a non-negative integer")

        piece = copy.deepcopy(dict(raw_piece))
        piece.update({
            "piece_id": piece_id, "name": piece_id, "outline": outline,
            "edges": _edges(outline), "area_cm2": round(_polygon_area(outline), 6),
            "cut_count": cut_count, "layer": layer,
        })
        inner_cutouts, error = _validated_inner_cutouts(
            piece_id, outline, piece.get("inner_cutouts"))
        if error:
            return error
        assert inner_cutouts is not None
        piece["inner_cutouts"] = inner_cutouts
        allowance_input = piece.get("seam_allowance_cm", global_allowance)
        allowance, error = _allowance_for_piece(
            allowance_input, piece_id, list(piece["edges"]),
            allow_proposed_default=allow_proposed_default,
            proposed_default_cm=proposed_default_cm)
        if error:
            return error
        widths = {edge: record["value_cm"] for edge, record in allowance["edges"].items()}
        offset = _marks.offset_outline(piece["outline"], piece["edges"],
                                       allowance=widths, piece_name=piece_id)
        if offset.get("verdict") != ANSWER:
            return _unknown(offset.get("verdict", "UNKNOWN_SEAM_ALLOWANCE_GEOMETRY"),
                            offset.get("why", f"cannot offset {piece_id}"),
                            piece_id=piece_id, offset_result=offset)
        piece.update({
            "sew_line": copy.deepcopy(offset["sew_line"]),
            "cut_line": copy.deepcopy(offset["cut_line"]),
            "boundary_layers": {"sew_line": _marks.LAYER_SEW,
                                "cut_line": _marks.LAYER_CUT},
            "seam_allowance_cm": copy.deepcopy(allowance),
            "cut_area_cm2": round(
                float(offset["cut_area_cm2"])
                - sum(float(row["area_cm2"]) for row in inner_cutouts), 6),
        })
        if piece["cut_area_cm2"] <= 0.0:
            return _unknown("UNKNOWN_INNER_CUT_NET_AREA",
                            f"{piece_id} inner cuts leave no positive cut area")
        grain, error = _grain(piece)
        if error:
            return error
        piece["grain"] = copy.deepcopy(grain)
        pieces.append(piece)
        by_name[piece_id] = piece
        allowance_records[piece_id] = allowance
        grain_records[piece_id] = grain

    seams = compiled_pattern.get("seams", [])
    if not isinstance(seams, list):
        return _unknown("UNKNOWN_SEAMS", "seams must be a list")
    notches, error = _seam_endpoint_notches(seams, by_name, allowance_records)
    if error:
        return error

    # The existing SVG/DXF APIs consume this exact marked-draft shape.
    marked = {
        **copy.deepcopy(dict(compiled_pattern)),
        "verdict": ANSWER,
        "pieces": pieces,
        "notches": notches,
        "notch_pairs": [],
        "notch_unpaired": [],
        "seam_allowance": {
            piece["name"]: {
                "verdict": ANSWER,
                "sew_line": copy.deepcopy(piece["sew_line"]),
                "cut_line": copy.deepcopy(piece["cut_line"]),
                "sew_area_cm2": piece["area_cm2"],
                "cut_area_cm2": piece["cut_area_cm2"],
                "layers": {"sew_line": _marks.LAYER_SEW,
                           "cut_line": _marks.LAYER_CUT},
                "segment_allowance": [
                    {"edge": edge, "cm": record["value_cm"],
                     "state": record["state"]}
                    for edge, record in allowance_records[piece["name"]]["edges"].items()
                ],
            } for piece in pieces
        },
        "grain": [copy.deepcopy(grain_records[piece["name"]]) for piece in pieces],
        "not_a_published_system": compiled_pattern.get(
            "not_a_published_system",
            "Procedural manufacturing preview, not a published drafting system."),
        "note": compiled_pattern.get(
            "note", "Front-only and proposed construction remain explicitly uncertain."),
        "standard_note": (
            "Layer names are exchange labels; no current DXF-AAMA standard conformance is claimed."),
    }
    base_svg = _pattern.to_svg(marked)
    if not base_svg.startswith("<svg"):
        return _unknown("UNKNOWN_SVG_PREVIEW", "existing SVG API could not render the marked pattern")
    base_dxf_result = _dxf.to_dxf(marked)
    inner_cut_manifest, error = _inner_cut_manifest(pieces, base_dxf_result)
    if error:
        return error
    assert inner_cut_manifest is not None
    svg = _augment_svg(base_svg, inner_cut_manifest)
    dxf_result = _augment_dxf(base_dxf_result, inner_cut_manifest)
    dxf_compatible = (dxf_result.get("verdict") == ANSWER
                      and not dxf_result.get("cut_line_missing"))
    if not dxf_compatible:
        dxf_result = {
            **copy.deepcopy(dxf_result),
            "typed_refusal": True,
            "why_not_claimed": "the existing DXF API did not accept every marked cut line",
        }

    records = _layer_records(pieces, notches, grain_records)
    layer_order = [{
        "piece_id": piece["name"], "layer": piece["layer"],
        "role": piece.get("role", piece.get("primitive_kind", "piece")),
        "cut_count": piece["cut_count"],
    } for piece in sorted(pieces, key=lambda item: (item["layer"], item["name"]))]
    all_allowance_explicit = all(
        record["state"] == "EXPLICIT" for record in allowance_records.values())
    all_grain_explicit = all(
        record["state"] in _EXPLICIT_STATES for record in grain_records.values())
    all_inner_cuts_approved = all(
        record.get("state") == "APPROVED" for record in inner_cut_manifest)
    manufacturing_ready = bool(
        compiled_pattern.get("manufacturing_ready") is True
        and all_allowance_explicit and all_grain_explicit and dxf_compatible
        and all_inner_cuts_approved)
    remaining_gates = list(compiled_pattern.get("remaining_gates", []))
    if not all_allowance_explicit:
        remaining_gates.append("approve or measure every proposed seam allowance")
    if not all_grain_explicit:
        remaining_gates.append("approve or measure every proposed grain direction")
    if compiled_pattern.get("manufacturing_ready") is not True:
        remaining_gates.append("source compiled pattern has not passed its manufacturing gates")
    if not dxf_compatible:
        remaining_gates.append("resolve the typed DXF refusal")
    if inner_cut_manifest and not all_inner_cuts_approved:
        remaining_gates.append(
            "approve each proposed inner cut and validate its edge finish, reinforcement and construction allowance")
    remaining_gates = list(dict.fromkeys(remaining_gates))

    source_digest = str(compiled_pattern.get("digest") or _digest(compiled_pattern))
    artifact: Dict[str, Any] = {
        "schema": SCHEMA,
        "source_schema": INPUT_SCHEMA,
        "source_digest": source_digest,
        "structure_digest": compiled_pattern.get("structure_digest"),
        "candidate_id": compiled_pattern.get("candidate_id", ""),
        "candidate_state": compiled_pattern.get("candidate_state", "PROPOSED"),
        "units": "cm",
        "pieces": pieces,
        "cut_manifest": [
            {"piece_id": p["name"], "cut_count": p["cut_count"],
             **({"inner_cut_count": len(p.get("inner_cutouts", []))}
                if p.get("inner_cutouts") else {})}
            for p in pieces],
        "seams": copy.deepcopy(seams),
        "layers": copy.deepcopy(compiled_pattern.get("layers", [])),
        "layer_order": layer_order,
        "seam_allowance_cm": allowance_records,
        "notches": notches,
        "grain": [grain_records[p["name"]] for p in pieces],
        "svg": svg,
        "inner_cut_manifest": inner_cut_manifest,
        "inner_cut_digest": _digest(inner_cut_manifest),
        "dxf_layer_records": records,
        "dxf_export": dxf_result,
        "dxf_compatible": dxf_compatible,
        "manufacturing_preview_ready": True,
        "manufacturing_ready": manufacturing_ready,
        "manufacturing_certified": False,
        "remaining_gates": remaining_gates,
        "provenance": {
            "method": "garment.compiled-pattern.v1 manufacturing preview adapter",
            "source_digest": source_digest,
            "source_provenance": copy.deepcopy(compiled_pattern.get("provenance")),
            "geometry_changed": False,
            "corpus_used": False,
        },
        "geometry_operations": copy.deepcopy(
            compiled_pattern.get("geometry_operations", [])),
        "approval": copy.deepcopy(compiled_pattern.get("approval")),
        "candidate_digest": (
            compiled_pattern.get("approval", {}).get("digest")
            if isinstance(compiled_pattern.get("approval"), Mapping) else None),
    }
    artifact["digest"] = _digest(artifact)
    return {"verdict": ANSWER, **artifact}


bundle = build
compile = build
