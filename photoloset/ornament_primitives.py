# -*- coding: utf-8 -*-
"""Deterministic, corpus-free 2D construction for garment ornaments.

``BOW``/``RIBBON``/``ROSETTE``/``TIE``/``FLAP`` are treated as geometric
assemblies, not garment classes.  The public :func:`expand` function consumes
explicit centimetre dimensions and returns actual sew/cut pattern pieces,
attachment ports and ordered seam intents.  It does not inspect pixels, choose
a nearby style, or supply missing dimensions.

An image or vision-model proposal is allowed only at ``PROPOSED`` authority.
The polygon calculations can be deterministically validated, but that does not
promote the proposed ornament, its dimensions or its attachment to OBSERVED.
Stitch/material choices remain REVIEW because geometry alone cannot select
them safely.

The optional :func:`route_parts_ir` adapter is deliberately one-way and
non-destructive.  It extracts supported ornaments from raw ``parts-ir`` input
before ``PrimitiveKind`` parsing, while returning every other part unchanged
in ``passthrough_parts``.  Existing completion/topology modules therefore do
not need a new garment-class enum merely to retain an ornament proposal.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .garment_marks import LAYER_CUT, LAYER_GRAIN, LAYER_SEW, offset_outline


SCHEMA = "garment.ornament-primitives.v1"
ROUTING_SCHEMA = "garment.parts-ir.ornament-routing.v1"
PROPOSED = "PROPOSED"
REVIEW = "REVIEW"
ANSWER = "ANSWER"

SUPPORTED_KINDS = frozenset({"BOW", "RIBBON", "ROSETTE", "TIE", "FLAP"})

_REQUIRED_DIMENSIONS: Dict[str, Tuple[str, ...]] = {
    "BOW": (
        "body_length_cm", "body_width_cm",
        "knot_length_cm", "knot_width_cm",
    ),
    "RIBBON": ("length_cm", "width_cm"),
    "ROSETTE": (
        "strip_length_cm", "strip_width_cm", "finished_inner_length_cm",
    ),
    "TIE": ("length_cm", "top_width_cm", "tip_width_cm"),
    "FLAP": ("attachment_width_cm", "depth_cm", "outer_width_cm"),
}

_IMAGE_ORIGINS = {
    "IMAGE", "FRONT_IMAGE", "IMAGE_INTERPRETATION", "VISION_MODEL",
    "MODEL_PROPOSAL", "MULTIMODAL_MODEL",
}
_GRAIN_DIRECTIONS = {
    "LENGTHWISE", "CROSSWISE", "BIAS_45", "BIAS_-45", "NO_GRAIN",
}
_RIBBON_ATTACHMENT_MODES = {"END", "CENTER", "LONG_EDGE"}


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
        "state": "UNKNOWN",
        "why": why,
        "how_to_close": (
            "supply the named centimetre dimensions and explicit construction "
            "choices; do not infer them from a front image"
        ),
        **detail,
    }


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_NOT_JSON",
            f"{field} must contain finite JSON values",
            field=field, error=str(exc),
        ) from exc
    return copy.deepcopy(value)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _Refusal(
            "UNKNOWN_ORNAMENT_TEXT_REQUIRED",
            f"{field} must be a non-empty string", field=field,
        )
    return value.strip()


def _positive(value: Any, *, field: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) <= 0.0):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_DIMENSION_INVALID",
            f"{field} must be a finite positive centimetre value", field=field,
        )
    number = float(value)
    if number > 1000.0:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_DIMENSION_OUT_OF_RANGE",
            f"{field} exceeds the bounded 1000cm construction range",
            field=field, value=number,
        )
    return number


def _proposal_claim(value: Any, *, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or value.upper() != PROPOSED:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_AUTHORITY_ESCALATION",
            f"{field} may only claim PROPOSED authority",
            field=field, claimed_state=value,
        )


def _source(spec: Mapping[str, Any]) -> Dict[str, Any]:
    raw = spec.get("source")
    if not isinstance(raw, Mapping):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_SOURCE_REQUIRED",
            "source must identify the origin, state, basis and break condition",
        )
    origin = _text(raw.get("origin"), field="source.origin").upper()
    state = _text(raw.get("state"), field="source.state").upper()
    if origin in _IMAGE_ORIGINS and state != PROPOSED:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_AUTHORITY_ESCALATION",
            "image/model-derived ornament evidence must remain PROPOSED",
            origin=origin, claimed_state=state,
        )
    if state not in {PROPOSED, "OBSERVED", "MEASURED"}:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_SOURCE_STATE",
            "source.state must be PROPOSED, OBSERVED or MEASURED",
            claimed_state=state,
        )
    basis = _text(raw.get("basis"), field="source.basis")
    breaks_when = _text(raw.get("breaks_when"), field="source.breaks_when")
    result = _json_copy(dict(raw), field="source")
    result.update({
        "origin": origin,
        "state": state,
        "basis": basis,
        "breaks_when": breaks_when,
    })
    if origin in _IMAGE_ORIGINS:
        result.update({
            "state": PROPOSED,
            "not_observed_from_image": True,
            "observation_authority_granted": False,
        })
    return result


def _dimensions(spec: Mapping[str, Any], kind: str,
                source: Mapping[str, Any]) -> Tuple[Dict[str, float], Dict[str, Any]]:
    raw = spec.get("dimensions")
    if not isinstance(raw, Mapping):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_DIMENSIONS_REQUIRED",
            "dimensions must be an object of named centimetre values",
            kind=kind,
        )
    missing = [name for name in _REQUIRED_DIMENSIONS[kind] if name not in raw]
    if missing:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_DIMENSIONS_MISSING",
            f"{kind} lacks required dimensions",
            kind=kind, missing=missing,
        )
    values: Dict[str, float] = {}
    evidence: Dict[str, Any] = {}
    image_derived = source["origin"] in _IMAGE_ORIGINS
    for name in _REQUIRED_DIMENSIONS[kind]:
        entry = raw[name]
        if isinstance(entry, Mapping):
            claimed = entry.get("state", source["state"])
            if image_derived:
                _proposal_claim(claimed, field=f"dimensions.{name}.state")
            raw_value = entry.get("value_cm", entry.get("value"))
            basis = entry.get("basis", source["basis"])
            breaks_when = entry.get("breaks_when", source["breaks_when"])
            if not isinstance(basis, str) or not basis.strip():
                raise _Refusal(
                    "UNKNOWN_ORNAMENT_DIMENSION_BASIS",
                    f"dimensions.{name}.basis must be a non-empty string",
                    dimension=name,
                )
            if not isinstance(breaks_when, str) or not breaks_when.strip():
                raise _Refusal(
                    "UNKNOWN_ORNAMENT_DIMENSION_BASIS",
                    f"dimensions.{name}.breaks_when must be a non-empty string",
                    dimension=name,
                )
            input_state = str(claimed).upper()
        else:
            raw_value = entry
            basis = source["basis"]
            breaks_when = source["breaks_when"]
            input_state = source["state"]
        value = _positive(raw_value, field=f"dimensions.{name}")
        values[name] = value
        evidence[name] = {
            "value_cm": value,
            "input_state": PROPOSED if image_derived else input_state,
            "output_state": PROPOSED,
            "basis": basis.strip(),
            "breaks_when": breaks_when.strip(),
            "not_observed_from_image": image_derived,
        }
    unused = sorted(str(name) for name in raw if name not in values)
    return values, {"dimensions": evidence, "unused_dimensions": unused}


def _quantity(spec: Mapping[str, Any]) -> int:
    if "quantity" not in spec:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_QUANTITY_REQUIRED",
            "quantity must be explicit; a front image cannot decide hidden copies",
        )
    value = spec["quantity"]
    if (isinstance(value, bool) or not isinstance(value, int)
            or not 1 <= value <= 32):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_QUANTITY_INVALID",
            "quantity must be an integer from 1 through 32",
            quantity=value,
        )
    return value


def _layer(spec: Mapping[str, Any]) -> int:
    if "layer" not in spec:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_LAYER_REQUIRED",
            "layer must be explicit so stacked ornaments are not reordered",
        )
    value = spec["layer"]
    if (isinstance(value, bool) or not isinstance(value, int)
            or not 0 <= value <= 31):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_LAYER_INVALID",
            "layer must be an integer from 0 through 31", layer=value,
        )
    return value


def _grain(spec: Mapping[str, Any]) -> str:
    if "grain_direction" not in spec:
        raise _Refusal(
            "REVIEW_ORNAMENT_GRAIN_REQUIRED",
            "grain_direction is required before the piece is presented for cutting",
            choices=sorted(_GRAIN_DIRECTIONS), state=REVIEW,
        )
    value = _text(spec["grain_direction"], field="grain_direction").upper()
    if value not in _GRAIN_DIRECTIONS:
        raise _Refusal(
            "REVIEW_ORNAMENT_GRAIN_AMBIGUOUS",
            "grain_direction is not one of the typed construction choices",
            choices=sorted(_GRAIN_DIRECTIONS), claimed=value, state=REVIEW,
        )
    return value


def _allowance(spec: Mapping[str, Any]) -> float:
    if "seam_allowance_cm" not in spec:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_SEAM_ALLOWANCE_REQUIRED",
            "seam_allowance_cm is required to derive a cut boundary",
        )
    return _positive(spec["seam_allowance_cm"], field="seam_allowance_cm")


def _attachment(value: Any) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if value is None:
        return None, [{
            "code": "REVIEW_ORNAMENT_ATTACHMENT_REQUIRED",
            "why": "the ornament geometry exists but its garment attachment port is unknown",
            "how_to_close": "choose one target_piece_id and target_port_id",
        }]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, Mapping)):
        return None, [{
            "code": "REVIEW_ORNAMENT_ATTACHMENT_AMBIGUOUS",
            "why": "multiple attachment candidates were supplied without a selection",
            "candidates": _json_copy(list(value), field="attachment"),
            "how_to_close": "select exactly one attachment candidate",
        }]
    if not isinstance(value, Mapping):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_ATTACHMENT",
            "attachment must be an object or a list of review candidates",
        )
    for authority_field in ("state", "authority", "verdict"):
        if authority_field in value:
            _proposal_claim(
                value[authority_field], field=f"attachment.{authority_field}")
    target_piece_id = value.get("target_piece_id", value.get("piece_id"))
    target_port_id = value.get(
        "target_port_id", value.get("port_id", value.get("edge")))
    if not isinstance(target_piece_id, str) or not target_piece_id.strip():
        return None, [{
            "code": "REVIEW_ORNAMENT_ATTACHMENT_REQUIRED",
            "why": "attachment lacks target_piece_id",
            "how_to_close": "select the garment pattern piece that receives the ornament",
        }]
    if not isinstance(target_port_id, str) or not target_port_id.strip():
        return None, [{
            "code": "REVIEW_ORNAMENT_ATTACHMENT_REQUIRED",
            "why": "attachment lacks target_port_id",
            "target_piece_id": target_piece_id.strip(),
            "how_to_close": "select a semantic edge or point port on the target piece",
        }]
    return {
        "target_piece_id": target_piece_id.strip(),
        "target_port_id": target_port_id.strip(),
        "state": PROPOSED,
        "observed": False,
    }, []


def _edge_table(outline: Sequence[Sequence[float]]) -> List[Dict[str, Any]]:
    result = []
    for index, (a, b) in enumerate(zip(outline, outline[1:] + outline[:1])):
        result.append({
            "address": f"e{index}",
            "points": [list(a), list(b)],
            "length_cm": round(math.hypot(b[0] - a[0], b[1] - a[1]), 6),
            "state": PROPOSED,
        })
    return result


def _grainline(outline: Sequence[Sequence[float]], direction: str) -> Dict[str, Any]:
    xs = [point[0] for point in outline]
    ys = [point[1] for point in outline]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    span = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.4
    vectors = {
        "LENGTHWISE": (1.0, 0.0),
        "CROSSWISE": (0.0, 1.0),
        "BIAS_45": (math.sqrt(0.5), math.sqrt(0.5)),
        "BIAS_-45": (math.sqrt(0.5), -math.sqrt(0.5)),
        "NO_GRAIN": (0.0, 0.0),
    }
    dx, dy = vectors[direction]
    return {
        "direction": direction,
        "state": PROPOSED,
        "layer": LAYER_GRAIN,
        "points": ([[round(cx - dx * span, 6), round(cy - dy * span, 6)],
                    [round(cx + dx * span, 6), round(cy + dy * span, 6)]]
                   if direction != "NO_GRAIN" else []),
    }


def _piece(piece_id: str, role: str, outline: List[List[float]], *,
           allowance_cm: float, layer: int, grain_direction: str,
           copy_index: int) -> Dict[str, Any]:
    boundary_name = "ornament boundary"
    marked = offset_outline(
        outline,
        {boundary_name: {"points": copy.deepcopy(outline) + [outline[0]]}},
        allowance={boundary_name: allowance_cm},
        piece_name=piece_id,
    )
    if marked.get("verdict") != ANSWER:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_CUT_BOUNDARY",
            f"{piece_id} could not derive a non-self-intersecting cut boundary",
            piece_id=piece_id,
            geometry_code=marked.get("verdict"),
            geometry_detail=_json_copy(marked, field="cut_boundary_error"),
        )
    sew_line = copy.deepcopy(marked["sew_line"])
    return {
        "piece_id": piece_id,
        "role": role,
        "state": PROPOSED,
        "proposal_only": True,
        "copy_index": copy_index,
        "cut_quantity": 1,
        "layer": layer,
        "outline": copy.deepcopy(sew_line),
        "sew_line": sew_line,
        "cut_line": copy.deepcopy(marked["cut_line"]),
        "edges": _edge_table(sew_line),
        "grainline": _grainline(sew_line, grain_direction),
        "boundary_layers": {"sew_line": LAYER_SEW, "cut_line": LAYER_CUT},
        "seam_allowance_cm": allowance_cm,
        "sew_area_cm2": marked["sew_area_cm2"],
        "cut_area_cm2": marked["cut_area_cm2"],
        "geometry_authority": {
            "state": PROPOSED,
            "deterministically_derived": True,
            "observed": False,
        },
    }


def _rectangle(length: float, width: float) -> List[List[float]]:
    return [[0.0, 0.0], [length, 0.0], [length, width], [0.0, width]]


def _trapezoid(top: float, bottom: float, depth: float) -> List[List[float]]:
    inset = (top - bottom) / 2.0
    return [[0.0, 0.0], [top, 0.0], [top - inset, depth], [inset, depth]]


def _piece_id(base: str, role: str, index: int, quantity: int) -> str:
    prefix = base if quantity == 1 else f"{base}:{index}"
    return prefix if role == "piece" else f"{prefix}:{role}"


def _edge_ref(piece_id: str, edge: str) -> Dict[str, str]:
    return {"piece_id": piece_id, "address": edge}


def _intent(intent_id: str, order: int, kind: str, *,
            source: Optional[Mapping[str, Any]] = None,
            target: Optional[Mapping[str, Any]] = None,
            parameters: Optional[Mapping[str, Any]] = None,
            stitch_required: bool = True) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "intent_id": intent_id,
        "order": order,
        "kind": kind,
        "state": PROPOSED,
        "source": None if source is None else copy.deepcopy(dict(source)),
        "target": None if target is None else copy.deepcopy(dict(target)),
        "parameters": copy.deepcopy(dict(parameters or {})),
        "topology_determined": True,
    }
    if stitch_required:
        result["stitch_choice"] = {
            "state": REVIEW,
            "code": "REVIEW_STITCH_AND_MATERIAL_REQUIRED",
            "why": "geometry does not determine thread, stitch class or reinforcement",
        }
    return result


def _point_port(port_id: str, piece_id: str, point: Sequence[float],
                attachment: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "port_id": port_id,
        "owner_piece_id": piece_id,
        "geometry": {"kind": "POINT", "point_cm": list(point)},
        "interface": "ornament-to-garment",
        "role": "attachment",
        "state": PROPOSED,
        "target": None if attachment is None else copy.deepcopy(dict(attachment)),
        "observed": False,
    }


def _edge_port(port_id: str, piece: Mapping[str, Any], edge: str,
               attachment: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    edge_row = next(row for row in piece["edges"] if row["address"] == edge)
    return {
        "port_id": port_id,
        "owner_piece_id": piece["piece_id"],
        "geometry": {
            "kind": "EDGE", "address": edge,
            "length_cm": edge_row["length_cm"],
        },
        "interface": "ornament-to-garment",
        "role": "attachment",
        "state": PROPOSED,
        "target": None if attachment is None else copy.deepcopy(dict(attachment)),
        "observed": False,
    }


def _attachment_intent(base: str, order: int, port: Mapping[str, Any]) -> Dict[str, Any]:
    return _intent(
        f"{base}:attach", order, "ATTACH_TO_GARMENT",
        source={"port_id": port["port_id"]}, target=port.get("target"),
        parameters={
            "interface": port["interface"],
            "attachment_geometry": copy.deepcopy(port["geometry"]),
        },
    )


def _expand_bow(base: str, dimensions: Mapping[str, float], *, quantity: int,
                allowance: float, layer: int, grain: str,
                attachment: Optional[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    pieces: List[Dict[str, Any]] = []
    ports: List[Dict[str, Any]] = []
    intents: List[Dict[str, Any]] = []
    for index in range(1, quantity + 1):
        body_id = _piece_id(base, "body", index, quantity)
        knot_id = _piece_id(base, "knot", index, quantity)
        body = _piece(
            body_id, "bow_body",
            _rectangle(dimensions["body_length_cm"], dimensions["body_width_cm"]),
            allowance_cm=allowance, layer=layer, grain_direction=grain,
            copy_index=index,
        )
        knot = _piece(
            knot_id, "bow_center_wrap",
            _rectangle(dimensions["knot_length_cm"], dimensions["knot_width_cm"]),
            allowance_cm=allowance, layer=layer + 1, grain_direction=grain,
            copy_index=index,
        )
        pieces.extend((body, knot))
        prefix = base if quantity == 1 else f"{base}:{index}"
        order = len(intents) + 1
        intents.extend([
            _intent(f"{prefix}:body-long-seam", order, "JOIN",
                    source=_edge_ref(body_id, "e0"),
                    target=_edge_ref(body_id, "e2"),
                    parameters={"turn_after_join": True,
                                "matched_length_cm": dimensions["body_length_cm"]}),
            _intent(f"{prefix}:body-loop-seam", order + 1, "JOIN",
                    source=_edge_ref(body_id, "e1"),
                    target=_edge_ref(body_id, "e3"),
                    parameters={"matched_length_cm": dimensions["body_width_cm"]}),
            _intent(f"{prefix}:center-compress", order + 2, "FOLD_AND_TACK",
                    source={"piece_id": body_id, "address": "center"},
                    stitch_required=True),
            _intent(f"{prefix}:wrap-knot", order + 3, "WRAP",
                    source={"piece_id": knot_id, "address": "piece"},
                    target={"piece_id": body_id, "address": "center"},
                    stitch_required=False),
            _intent(f"{prefix}:close-knot", order + 4, "JOIN",
                    source=_edge_ref(knot_id, "e1"),
                    target=_edge_ref(knot_id, "e3"),
                    parameters={"matched_length_cm": dimensions["knot_width_cm"]}),
        ])
        port = _point_port(
            f"{prefix}:garment-attach", knot_id,
            [dimensions["knot_length_cm"] / 2.0,
             dimensions["knot_width_cm"] / 2.0], attachment,
        )
        ports.append(port)
        intents.append(_attachment_intent(prefix, order + 5, port))
    return pieces, ports, intents


def _expand_ribbon(base: str, dimensions: Mapping[str, float], *, quantity: int,
                   allowance: float, layer: int, grain: str,
                   attachment: Optional[Mapping[str, Any]],
                   attachment_mode: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    pieces, ports, intents = [], [], []
    for index in range(1, quantity + 1):
        piece_id = _piece_id(base, "piece", index, quantity)
        piece = _piece(
            piece_id, "ribbon_strip",
            _rectangle(dimensions["length_cm"], dimensions["width_cm"]),
            allowance_cm=allowance, layer=layer, grain_direction=grain,
            copy_index=index,
        )
        pieces.append(piece)
        prefix = piece_id
        if attachment_mode == "END":
            port = _edge_port(f"{prefix}:garment-attach", piece, "e3", attachment)
        elif attachment_mode == "LONG_EDGE":
            port = _edge_port(f"{prefix}:garment-attach", piece, "e0", attachment)
        else:
            port = _point_port(
                f"{prefix}:garment-attach", piece_id,
                [dimensions["length_cm"] / 2.0, dimensions["width_cm"] / 2.0],
                attachment,
            )
        ports.append(port)
        order = len(intents) + 1
        intents.extend([
            _intent(f"{prefix}:finish-boundary", order, "FINISH_RAW_EDGES",
                    source={"piece_id": piece_id, "address": "all_edges"}),
            _attachment_intent(prefix, order + 1, port),
        ])
    return pieces, ports, intents


def _expand_rosette(base: str, dimensions: Mapping[str, float], *, quantity: int,
                    allowance: float, layer: int, grain: str,
                    attachment: Optional[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    strip_length = dimensions["strip_length_cm"]
    finished = dimensions["finished_inner_length_cm"]
    if strip_length <= finished:
        raise _Refusal(
            "UNKNOWN_ORNAMENT_GATHER_RATIO_INVALID",
            "ROSETTE strip_length_cm must exceed finished_inner_length_cm",
            strip_length_cm=strip_length, finished_inner_length_cm=finished,
        )
    pieces, ports, intents = [], [], []
    ratio = strip_length / finished
    for index in range(1, quantity + 1):
        piece_id = _piece_id(base, "piece", index, quantity)
        piece = _piece(
            piece_id, "rosette_gather_strip",
            _rectangle(strip_length, dimensions["strip_width_cm"]),
            allowance_cm=allowance, layer=layer, grain_direction=grain,
            copy_index=index,
        )
        pieces.append(piece)
        prefix = piece_id
        port = _point_port(
            f"{prefix}:garment-attach", piece_id,
            [strip_length / 2.0, dimensions["strip_width_cm"] / 2.0],
            attachment,
        )
        ports.append(port)
        order = len(intents) + 1
        intents.extend([
            _intent(f"{prefix}:gather", order, "GATHER",
                    source=_edge_ref(piece_id, "e0"),
                    parameters={
                        "cut_length_cm": strip_length,
                        "finished_length_cm": finished,
                        "ratio": ratio,
                    }),
            _intent(f"{prefix}:form-rosette", order + 1, "FORM_SPIRAL_AND_TACK",
                    source={"piece_id": piece_id, "address": "gathered_e0"}),
            _attachment_intent(prefix, order + 2, port),
        ])
    return pieces, ports, intents


def _expand_tie(base: str, dimensions: Mapping[str, float], *, quantity: int,
                allowance: float, layer: int, grain: str,
                attachment: Optional[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    pieces, ports, intents = [], [], []
    for index in range(1, quantity + 1):
        piece_id = _piece_id(base, "piece", index, quantity)
        piece = _piece(
            piece_id, "tapered_tie",
            _trapezoid(dimensions["top_width_cm"], dimensions["tip_width_cm"],
                       dimensions["length_cm"]),
            allowance_cm=allowance, layer=layer, grain_direction=grain,
            copy_index=index,
        )
        pieces.append(piece)
        port = _edge_port(f"{piece_id}:garment-attach", piece, "e0", attachment)
        ports.append(port)
        order = len(intents) + 1
        intents.extend([
            _intent(f"{piece_id}:finish-boundary", order, "FINISH_RAW_EDGES",
                    source={"piece_id": piece_id, "address": "e1,e2,e3"}),
            _attachment_intent(piece_id, order + 1, port),
        ])
    return pieces, ports, intents


def _expand_flap(base: str, dimensions: Mapping[str, float], *, quantity: int,
                 allowance: float, layer: int, grain: str,
                 attachment: Optional[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    pieces, ports, intents = [], [], []
    for index in range(1, quantity + 1):
        piece_id = _piece_id(base, "piece", index, quantity)
        piece = _piece(
            piece_id, "flap",
            _trapezoid(dimensions["attachment_width_cm"],
                       dimensions["outer_width_cm"], dimensions["depth_cm"]),
            allowance_cm=allowance, layer=layer, grain_direction=grain,
            copy_index=index,
        )
        pieces.append(piece)
        port = _edge_port(f"{piece_id}:garment-attach", piece, "e0", attachment)
        ports.append(port)
        order = len(intents) + 1
        intents.extend([
            _intent(f"{piece_id}:finish-outer-edge", order, "FINISH_RAW_EDGES",
                    source={"piece_id": piece_id, "address": "e1,e2,e3"}),
            _attachment_intent(piece_id, order + 1, port),
        ])
    return pieces, ports, intents


def _validate_artifacts(pieces: Sequence[Mapping[str, Any]],
                        ports: Sequence[Mapping[str, Any]],
                        intents: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    piece_ids = [piece["piece_id"] for piece in pieces]
    port_ids = [port["port_id"] for port in ports]
    intent_ids = [intent["intent_id"] for intent in intents]
    if len(piece_ids) != len(set(piece_ids)):
        raise _Refusal("UNKNOWN_ORNAMENT_DUPLICATE_PIECE", "piece ids are not unique")
    if len(port_ids) != len(set(port_ids)):
        raise _Refusal("UNKNOWN_ORNAMENT_DUPLICATE_PORT", "attachment port ids are not unique")
    if len(intent_ids) != len(set(intent_ids)):
        raise _Refusal("UNKNOWN_ORNAMENT_DUPLICATE_SEAM_INTENT", "seam intent ids are not unique")
    if any(piece["cut_area_cm2"] <= piece["sew_area_cm2"] for piece in pieces):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_CUT_BOUNDARY",
            "every cut line must strictly contain its sew line",
        )
    if any(port["owner_piece_id"] not in set(piece_ids) for port in ports):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_PORT_OWNER", "an attachment port has no pattern piece",
        )
    orders = [intent["order"] for intent in intents]
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        raise _Refusal(
            "UNKNOWN_ORNAMENT_SEAM_ORDER", "seam intent order must be unique and monotonic",
        )
    return {
        "verdict": ANSWER,
        "piece_count": len(pieces),
        "attachment_port_count": len(ports),
        "seam_intent_count": len(intents),
        "cut_contains_sew": True,
        "authority_granted": False,
    }


def expand(spec: Mapping[str, Any]) -> Dict[str, Any]:
    """Expand one typed ornament proposal into 2D construction artifacts.

    Missing physical dimensions fail closed.  A missing or ambiguous garment
    attachment keeps the locally complete pattern pieces and returns REVIEW;
    it never chooses an attachment from names or image proximity.
    """
    try:
        if not isinstance(spec, Mapping):
            raise _Refusal("UNKNOWN_ORNAMENT_SPEC", "spec must be an object")
        frozen = _json_copy(dict(spec), field="spec")
        _proposal_claim(spec.get("state"), field="state")
        ornament_id = _text(spec.get("ornament_id", spec.get("part_id")),
                            field="ornament_id")
        kind = _text(spec.get("kind"), field="kind").upper()
        if kind not in SUPPORTED_KINDS:
            raise _Refusal(
                "UNKNOWN_ORNAMENT_KIND",
                f"{kind} has no deterministic ornament expander",
                kind=kind, supported=sorted(SUPPORTED_KINDS),
            )
        source = _source(spec)
        dimensions, evidence = _dimensions(spec, kind, source)
        quantity = _quantity(spec)
        layer = _layer(spec)
        grain = _grain(spec)
        allowance = _allowance(spec)
        attachment, reviews = _attachment(spec.get("attachment"))

        if kind == "RIBBON":
            raw_mode = spec.get("attachment_mode")
            if raw_mode is None:
                return {
                    "schema": SCHEMA,
                    "verdict": "REVIEW_ORNAMENT_CONSTRUCTION_REQUIRED",
                    "state": REVIEW,
                    "why": "RIBBON needs an explicit END, CENTER or LONG_EDGE attachment_mode",
                    "choices": sorted(_RIBBON_ATTACHMENT_MODES),
                    "input_preserved": frozen,
                }
            mode = _text(raw_mode, field="attachment_mode").upper()
            if mode not in _RIBBON_ATTACHMENT_MODES:
                return {
                    "schema": SCHEMA,
                    "verdict": "REVIEW_ORNAMENT_CONSTRUCTION_AMBIGUOUS",
                    "state": REVIEW,
                    "why": "RIBBON attachment_mode is outside the typed choices",
                    "choices": sorted(_RIBBON_ATTACHMENT_MODES),
                    "claimed": mode,
                    "input_preserved": frozen,
                }
            pieces, ports, intents = _expand_ribbon(
                ornament_id, dimensions, quantity=quantity, allowance=allowance,
                layer=layer, grain=grain, attachment=attachment,
                attachment_mode=mode,
            )
        elif kind == "BOW":
            pieces, ports, intents = _expand_bow(
                ornament_id, dimensions, quantity=quantity, allowance=allowance,
                layer=layer, grain=grain, attachment=attachment,
            )
        elif kind == "ROSETTE":
            pieces, ports, intents = _expand_rosette(
                ornament_id, dimensions, quantity=quantity, allowance=allowance,
                layer=layer, grain=grain, attachment=attachment,
            )
        elif kind == "TIE":
            pieces, ports, intents = _expand_tie(
                ornament_id, dimensions, quantity=quantity, allowance=allowance,
                layer=layer, grain=grain, attachment=attachment,
            )
        else:
            pieces, ports, intents = _expand_flap(
                ornament_id, dimensions, quantity=quantity, allowance=allowance,
                layer=layer, grain=grain, attachment=attachment,
            )

        validation = _validate_artifacts(pieces, ports, intents)
        payload = {
            "ornament_id": ornament_id,
            "kind": kind,
            "pattern_pieces": pieces,
            "attachment_ports": ports,
            "seam_intents": intents,
            "construction_order": [intent["intent_id"] for intent in intents],
            "dimension_evidence": evidence["dimensions"],
            "unused_dimensions": evidence["unused_dimensions"],
            "geometry_validation": validation,
            "reviews": reviews + [{
                "code": "REVIEW_STITCH_AND_MATERIAL_REQUIRED",
                "why": "thread, stitch, interfacing and reinforcement depend on material and use",
            }],
            "authority": {
                "output_state": PROPOSED,
                "observed": False,
                "approved": False,
                "image_promoted_to_observed": False,
            },
            "provenance": {
                "method": "deterministic ornament primitive expansion",
                "source": source,
                "corpus_used": False,
                "image_pixels_consumed": False,
                "garment_class_added": False,
            },
        }
        payload_digest = _digest(payload)
        if reviews:
            verdict = reviews[0]["code"]
            state = REVIEW
        else:
            verdict = PROPOSED
            state = PROPOSED
        return {
            "schema": SCHEMA,
            "verdict": verdict,
            "state": state,
            **payload,
            "digest": payload_digest,
        }
    except _Refusal as refusal:
        detail = dict(refusal.detail)
        state = detail.pop("state", None)
        if state == REVIEW or refusal.code.startswith("REVIEW_"):
            return {
                "schema": SCHEMA,
                "verdict": refusal.code,
                "state": REVIEW,
                "why": refusal.why,
                "how_to_close": detail.pop(
                    "how_to_close", "select one explicit construction value"),
                **detail,
            }
        return _unknown(refusal.code, refusal.why, **detail)
    except (TypeError, ValueError, OverflowError, StopIteration) as exc:
        return _unknown("UNKNOWN_ORNAMENT_MALFORMED", str(exc))


def _part_source(part: Mapping[str, Any]) -> Dict[str, Any]:
    visible = part.get("visible_basis")
    if isinstance(visible, Mapping):
        basis = visible.get("basis", visible.get("description", visible.get("source")))
        breaks_when = visible.get(
            "breaks_when", "another view or construction review contradicts it")
        claimed = visible.get("state", PROPOSED)
    elif isinstance(visible, str):
        basis = visible
        breaks_when = "another view or construction review contradicts it"
        claimed = PROPOSED
    else:
        basis = "model-proposed ornament in raw parts IR"
        breaks_when = "another view or construction review contradicts it"
        claimed = PROPOSED
    return {
        "origin": "IMAGE_INTERPRETATION",
        "state": claimed,
        "basis": basis,
        "breaks_when": breaks_when,
    }


def _part_attachment(part: Mapping[str, Any]) -> Any:
    if "attachment" in part:
        return copy.deepcopy(part["attachment"])
    if "attachment_port" in part:
        return copy.deepcopy(part["attachment_port"])
    attached = part.get("attached_to")
    if isinstance(attached, str) and attached.strip():
        result: Dict[str, Any] = {
            "target_piece_id": attached.strip(),
            "state": PROPOSED,
        }
        target_port = part.get("target_port_id", part.get("target_edge"))
        if isinstance(target_port, str) and target_port.strip():
            result["target_port_id"] = target_port.strip()
        return result
    if (isinstance(attached, Sequence)
            and not isinstance(attached, (str, bytes))):
        return [
            {"target_piece_id": item, "state": PROPOSED}
            for item in attached if isinstance(item, str) and item.strip()
        ]
    return None


def _part_spec(part: Mapping[str, Any]) -> Dict[str, Any]:
    spec = {
        "ornament_id": part.get("ornament_id", part.get("part_id")),
        "kind": part.get("kind"),
        "state": PROPOSED,
        "dimensions": copy.deepcopy(part.get("dimensions")),
        "quantity": part.get("quantity"),
        "layer": part.get("layer"),
        "grain_direction": part.get("grain_direction"),
        "seam_allowance_cm": part.get("seam_allowance_cm"),
        "attachment": _part_attachment(part),
        "source": _part_source(part),
    }
    if "attachment_mode" in part:
        spec["attachment_mode"] = part["attachment_mode"]
    return spec


def route_parts_ir(parts_ir: Mapping[str, Any]) -> Dict[str, Any]:
    """Route raw parts-IR ornaments without dropping unsupported/base parts.

    This adapter intentionally runs *before* ``parts_ir_completion``.  It does
    not modify that module, does not mutate the input and does not claim that
    passthrough parts are valid ``PrimitiveKind`` values.
    """
    try:
        if not isinstance(parts_ir, Mapping):
            raise _Refusal("UNKNOWN_ORNAMENT_ROUTING_SCHEMA", "parts_ir must be an object")
        frozen = _json_copy(dict(parts_ir), field="parts_ir")
        raw_candidates = parts_ir.get("candidates")
        if raw_candidates is None:
            raw_parts = parts_ir.get("parts")
            raw_candidates = [{"candidate_id": "parts-ir", "parts": raw_parts}]
        if (not isinstance(raw_candidates, Sequence)
                or isinstance(raw_candidates, (str, bytes)) or not raw_candidates):
            raise _Refusal(
                "UNKNOWN_ORNAMENT_ROUTING_CANDIDATES",
                "parts_ir needs a non-empty parts or candidates array",
            )
        routed = []
        statuses: List[str] = []
        for index, candidate in enumerate(raw_candidates):
            if not isinstance(candidate, Mapping):
                raise _Refusal(
                    "UNKNOWN_ORNAMENT_ROUTING_CANDIDATE",
                    f"candidate {index} must be an object",
                )
            parts = candidate.get("parts")
            if (not isinstance(parts, Sequence)
                    or isinstance(parts, (str, bytes)) or not parts
                    or any(not isinstance(part, Mapping) for part in parts)):
                raise _Refusal(
                    "UNKNOWN_ORNAMENT_ROUTING_PARTS",
                    f"candidate {index} needs a non-empty parts array",
                )
            passthrough, ornament_inputs, ornament_results, manifest = [], [], [], []
            for part_index, part in enumerate(parts):
                copied = copy.deepcopy(dict(part))
                kind = str(part.get("kind", "")).upper()
                part_id = part.get("part_id", f"part-{part_index}")
                if kind not in SUPPORTED_KINDS:
                    passthrough.append(copied)
                    manifest.append({
                        "part_id": part_id,
                        "kind": part.get("kind"),
                        "route": "PASSTHROUGH_UNCHANGED",
                    })
                    continue
                ornament_spec = _part_spec(part)
                result = expand(ornament_spec)
                ornament_inputs.append(ornament_spec)
                ornament_results.append(result)
                statuses.append(str(result.get("verdict", "UNKNOWN_ORNAMENT_RESULT")))
                manifest.append({
                    "part_id": part_id,
                    "kind": kind,
                    "route": "ORNAMENT_PRIMITIVE_EXPANDER",
                    "result": result.get("verdict"),
                })
            routed.append({
                "candidate_id": candidate.get("candidate_id", f"candidate-{index + 1}"),
                "passthrough_parts": passthrough,
                "ornament_inputs": ornament_inputs,
                "ornament_results": ornament_results,
                "routing_manifest": manifest,
                "input_part_count": len(parts),
                "preserved_part_count": len(passthrough) + len(ornament_inputs),
                "all_parts_preserved": len(parts) == len(passthrough) + len(ornament_inputs),
            })
        unknown = next((status for status in statuses if status.startswith("UNKNOWN_")), None)
        review = next((status for status in statuses if status.startswith("REVIEW_")), None)
        verdict = unknown or review or PROPOSED
        return {
            "schema": ROUTING_SCHEMA,
            "verdict": verdict,
            "state": ("UNKNOWN" if unknown else REVIEW if review else PROPOSED),
            "candidates": routed,
            "input_preserved": frozen,
            "provenance": {
                "method": "non-destructive raw parts-IR ornament routing",
                "corpus_used": False,
                "primitive_kind_enum_modified": False,
            },
        }
    except _Refusal as refusal:
        return {
            **_unknown(refusal.code, refusal.why, **refusal.detail),
            "schema": ROUTING_SCHEMA,
        }


expand_ornament = expand
expand_parts_ir_ornaments = route_parts_ir


__all__ = [
    "SCHEMA", "ROUTING_SCHEMA", "SUPPORTED_KINDS", "expand",
    "expand_ornament", "route_parts_ir", "expand_parts_ir_ornaments",
]
