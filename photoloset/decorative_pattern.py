# -*- coding: utf-8 -*-
"""Corpus-free decorative and layer pattern operations.

Ruffles, frills and overlays are construction geometry, not garment-class
labels.  This module therefore requires their measurements explicitly and
uses :mod:`pattern_transforms` for gathered-edge validation.  A result keeps
the finished (sew) boundary separate from the cut boundary so that seam
allowance is never silently lost or invented.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Mapping, Optional, Sequence

from . import pattern_transforms
from .garment_marks import LAYER_CUT, LAYER_SEW, offset_outline


ANSWER = "ANSWER"
SCHEMA = "garment.decorative-pattern.v1"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "schema": SCHEMA,
        "why": why,
        "how_to_close": "provide every named dimension and an explicit geometrically valid value",
        **detail,
    }


def _positive(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and float(value) > 0.0)


def _piece_id(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _layer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _provenance(operation: str, inputs: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "method": "deterministic compositional pattern geometry",
        "operation": operation,
        "corpus_used": False,
        "source_kind": "explicit_dimensions",
        "input_digest": _digest(inputs),
    }


def _boundaries(outline: Sequence[Sequence[float]], allowance_cm: Any,
                piece_id: str) -> Dict[str, Any]:
    if allowance_cm is None:
        return _unknown("UNKNOWN_SEAM_ALLOWANCE_MISSING",
                        f"{piece_id} needs seam_allowance_cm to derive a cut boundary")
    if not _positive(allowance_cm):
        return _unknown("UNKNOWN_SEAM_ALLOWANCE_INVALID",
                        "seam_allowance_cm must be finite and positive")
    closed = [list(point) for point in outline] + [list(outline[0])]
    edge_name = "decorative boundary"
    marked = offset_outline(
        outline,
        {edge_name: {"points": closed}},
        allowance={edge_name: float(allowance_cm)},
        piece_name=piece_id,
    )
    if marked.get("verdict") != ANSWER:
        return {
            **marked,
            "schema": SCHEMA,
            "how_to_close": marked.get(
                "how_to_close", "change the explicit outline or seam allowance"),
        }
    sew = copy.deepcopy(marked["sew_line"])
    cut = copy.deepcopy(marked["cut_line"])
    return {
        "verdict": ANSWER,
        "sew_boundary": sew,
        "cut_boundary": cut,
        # Keep the established names available to DXF/marking consumers.
        "sew_line": copy.deepcopy(sew),
        "cut_line": copy.deepcopy(cut),
        "boundary_layers": {"sew_line": LAYER_SEW, "cut_line": LAYER_CUT},
        "seam_allowance_cm": float(allowance_cm),
        "sew_area_cm2": marked["sew_area_cm2"],
        "cut_area_cm2": marked["cut_area_cm2"],
    }


def _attachment(value: Any) -> tuple[Optional[Dict[str, str]], Optional[Dict[str, Any]]]:
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        return None, _unknown("UNKNOWN_DECORATIVE_ATTACHMENT",
                              "attach_to must name a piece_id and edge")
    target_id = _piece_id(value.get("piece_id"))
    edge = value.get("edge")
    valid_edge = ((isinstance(edge, str) and edge.startswith("e") and edge[1:].isdigit())
                  or (isinstance(edge, int) and not isinstance(edge, bool) and edge >= 0))
    if target_id is None or not valid_edge:
        return None, _unknown("UNKNOWN_DECORATIVE_ATTACHMENT",
                              "attach_to must name a non-empty piece_id and an eN edge")
    address = edge if isinstance(edge, str) else f"e{edge}"
    return {"piece_id": target_id, "edge": address}, None


def ruffle(piece_id: Any = None, *, finished_length_cm: Any = None,
           depth_cm: Any = None, gather_ratio: Any = None,
           seam_allowance_cm: Any = None, layer: Any = 0,
           attach_to: Any = None, kind: str = "RUFFLE") -> Dict[str, Any]:
    """Create one measured gathered strip.

    ``finished_length_cm`` is the length after gathering.  The pattern's
    attachment edge is ``finished_length_cm * gather_ratio`` and is checked by
    ``pattern_transforms.apply_gather`` rather than trusted independently.
    """
    identity = _piece_id(piece_id)
    if identity is None:
        return _unknown("UNKNOWN_DECORATIVE_PIECE_ID", "piece_id is required")
    missing = [name for name, value in (
        ("finished_length_cm", finished_length_cm), ("depth_cm", depth_cm),
        ("gather_ratio", gather_ratio)) if value is None]
    if missing:
        return _unknown("UNKNOWN_DECORATIVE_DIMENSION_MISSING",
                        "ruffle dimensions and gather ratio are required", missing=missing)
    if not _positive(finished_length_cm) or not _positive(depth_cm):
        return _unknown("UNKNOWN_DECORATIVE_DIMENSION_INVALID",
                        "finished_length_cm and depth_cm must be finite and positive")
    if not _positive(gather_ratio) or float(gather_ratio) <= 1.0:
        return _unknown("UNKNOWN_GATHER_RATIO_INVALID",
                        "gather_ratio must be finite and greater than 1")
    if not _layer(layer):
        return _unknown("UNKNOWN_LAYER_VALUE", "layer must be a non-negative integer")
    attachment, error = _attachment(attach_to)
    if error:
        return error

    finished = float(finished_length_cm)
    depth = float(depth_cm)
    ratio = float(gather_ratio)
    cut_length = finished * ratio
    if not math.isfinite(cut_length):
        return _unknown("UNKNOWN_DECORATIVE_DIMENSION_INVALID",
                        "finished length multiplied by gather ratio is not finite")
    outline = [[0.0, 0.0], [cut_length, 0.0],
               [cut_length, depth], [0.0, depth]]
    base = {"piece_id": identity, "outline": outline, "layer": layer,
            "decorative_kind": kind}
    gathered = pattern_transforms.apply_gather(
        base, "e0", finished_length_cm=finished, ratio=ratio)
    if gathered.get("verdict") != ANSWER:
        return {**gathered, "schema": SCHEMA}
    marked = _boundaries(gathered["after"]["outline"], seam_allowance_cm, identity)
    if marked.get("verdict") != ANSWER:
        return marked

    piece = copy.deepcopy(gathered["after"])
    piece.update({
        "kind": kind,
        "finished_length_cm": finished,
        "depth_cm": depth,
        "gather_ratio": ratio,
        "attachment_edge": {
            "address": "e0", "cut_length_cm": cut_length,
            "finished_length_cm": finished, "distribution": "uniform",
            "attach_to": attachment,
        },
        "free_edge": {"address": "e2", "length_cm": cut_length},
        "side_edges": ["e1", "e3"],
        **{key: value for key, value in marked.items() if key != "verdict"},
    })
    inputs = {
        "piece_id": identity, "finished_length_cm": finished,
        "depth_cm": depth, "gather_ratio": ratio,
        "seam_allowance_cm": float(seam_allowance_cm), "layer": layer,
        "attach_to": attachment, "kind": kind,
    }
    provenance = _provenance(kind, inputs)
    piece["provenance"] = copy.deepcopy(provenance)
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "piece": piece,
        "pieces": [copy.deepcopy(piece)],
        "operation": copy.deepcopy(gathered["transform"]),
        "digest": _digest(piece),
        "validation": {
            "geometry": ANSWER,
            "gather_ratio": ANSWER,
            "cut_contains_sew": marked["cut_area_cm2"] > marked["sew_area_cm2"],
        },
        "provenance": provenance,
    }


def frill(piece_id: Any = None, **kwargs: Any) -> Dict[str, Any]:
    """A frill is represented by the same measured gathered-strip geometry."""
    kwargs.pop("kind", None)
    return ruffle(piece_id, kind="FRILL", **kwargs)


def tiered_ruffles(assembly_id: Any = None, *, tiers: Any = None,
                   seam_allowance_cm: Any = None) -> Dict[str, Any]:
    """Build a top-to-bottom sequence of independently measured ruffles."""
    identity = _piece_id(assembly_id)
    if identity is None:
        return _unknown("UNKNOWN_DECORATIVE_ASSEMBLY_ID", "assembly_id is required")
    if not isinstance(tiers, Sequence) or isinstance(tiers, (str, bytes)) or not tiers:
        return _unknown("UNKNOWN_TIER_SPECIFICATION", "tiers must be a non-empty sequence")
    pieces = []
    tier_order = []
    for index, spec in enumerate(tiers):
        if not isinstance(spec, Mapping):
            return _unknown("UNKNOWN_TIER_SPECIFICATION",
                            f"tier {index + 1} must be an object", tier=index + 1)
        tier_id = spec.get("piece_id", f"{identity}:tier:{index + 1}")
        allowance = spec.get("seam_allowance_cm", seam_allowance_cm)
        result = ruffle(
            tier_id,
            finished_length_cm=spec.get("finished_length_cm"),
            depth_cm=spec.get("depth_cm"),
            gather_ratio=spec.get("gather_ratio"),
            seam_allowance_cm=allowance,
            layer=spec.get("layer", 0),
            attach_to=spec.get("attach_to"),
            kind="TIERED_RUFFLE",
        )
        if result.get("verdict") != ANSWER:
            return {**result, "tier": index + 1, "assembly_id": identity}
        piece = result["piece"]
        pieces.append(piece)
        tier_order.append({
            "tier": index + 1,
            "piece_id": piece["piece_id"],
            "position": "top_to_bottom",
        })
    inputs = {"assembly_id": identity, "tiers": copy.deepcopy(list(tiers)),
              "seam_allowance_cm": seam_allowance_cm}
    provenance = _provenance("TIERED_RUFFLES", inputs)
    assembly = {
        "assembly_id": identity,
        "kind": "TIERED_RUFFLES",
        "pieces": pieces,
        "tier_order": tier_order,
    }
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        **assembly,
        "digest": _digest(assembly),
        "provenance": provenance,
    }


def overlay(piece_id: Any = None, *, width_cm: Any = None,
            height_cm: Any = None, seam_allowance_cm: Any = None,
            layer: Any = None, attach_edges: Any = None) -> Dict[str, Any]:
    """Create a rectangular overlay piece from explicit dimensions."""
    identity = _piece_id(piece_id)
    if identity is None:
        return _unknown("UNKNOWN_DECORATIVE_PIECE_ID", "piece_id is required")
    missing = [name for name, value in (("width_cm", width_cm),
                                        ("height_cm", height_cm),
                                        ("layer", layer)) if value is None]
    if missing:
        return _unknown("UNKNOWN_DECORATIVE_DIMENSION_MISSING",
                        "overlay dimensions and layer are required", missing=missing)
    if not _positive(width_cm) or not _positive(height_cm):
        return _unknown("UNKNOWN_DECORATIVE_DIMENSION_INVALID",
                        "width_cm and height_cm must be finite and positive")
    if not _layer(layer):
        return _unknown("UNKNOWN_LAYER_VALUE", "layer must be a non-negative integer")
    if attach_edges is None:
        attachments = []
    elif (not isinstance(attach_edges, Sequence)
          or isinstance(attach_edges, (str, bytes))):
        return _unknown("UNKNOWN_OVERLAY_ATTACHMENTS", "attach_edges must be a sequence of eN addresses")
    else:
        attachments = []
        for edge in attach_edges:
            valid = ((isinstance(edge, str) and edge.startswith("e") and edge[1:].isdigit()
                      and int(edge[1:]) < 4)
                     or (isinstance(edge, int) and not isinstance(edge, bool)
                         and 0 <= edge < 4))
            if not valid:
                return _unknown("UNKNOWN_OVERLAY_ATTACHMENTS",
                                "overlay attachment edges must exist on the rectangular piece")
            address = edge if isinstance(edge, str) else f"e{edge}"
            if address not in attachments:
                attachments.append(address)

    width, height = float(width_cm), float(height_cm)
    outline = [[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]]
    marked = _boundaries(outline, seam_allowance_cm, identity)
    if marked.get("verdict") != ANSWER:
        return marked
    record = {
        "kind": "OVERLAY", "address": "piece", "width_cm": width,
        "height_cm": height, "attach_edges": attachments, "layer": layer,
    }
    piece = {
        "piece_id": identity,
        "kind": "OVERLAY",
        "outline": copy.deepcopy(marked["sew_boundary"]),
        "layer": layer,
        "transforms": [copy.deepcopy(record)],
        "attach_edges": attachments,
        **{key: value for key, value in marked.items() if key != "verdict"},
    }
    inputs = {"piece_id": identity, "width_cm": width, "height_cm": height,
              "seam_allowance_cm": float(seam_allowance_cm), "layer": layer,
              "attach_edges": attachments}
    provenance = _provenance("OVERLAY", inputs)
    piece["provenance"] = copy.deepcopy(provenance)
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "piece": piece,
        "pieces": [copy.deepcopy(piece)],
        "operation": record,
        "digest": _digest(piece),
        "validation": {
            "geometry": ANSWER,
            "cut_contains_sew": marked["cut_area_cm2"] > marked["sew_area_cm2"],
        },
        "provenance": provenance,
    }


def order_layers(pieces: Any = None, *, order: Any = None) -> Dict[str, Any]:
    """Validate an explicit inner-to-outer ordering without inferring one."""
    if not isinstance(pieces, Sequence) or isinstance(pieces, (str, bytes)) or not pieces:
        return _unknown("UNKNOWN_LAYER_PIECES", "pieces must be a non-empty sequence")
    copied = []
    ids = []
    for index, piece in enumerate(pieces):
        if not isinstance(piece, Mapping):
            return _unknown("UNKNOWN_LAYER_PIECES", f"piece {index} must be an object")
        identity = _piece_id(piece.get("piece_id", piece.get("name")))
        if identity is None:
            return _unknown("UNKNOWN_LAYER_PIECES", f"piece {index} needs piece_id or name")
        ids.append(identity)
        copied.append(copy.deepcopy(dict(piece)))
    if len(ids) != len(set(ids)):
        return _unknown("UNKNOWN_LAYER_DUPLICATE_PIECE", "piece ids must be unique")

    if order is None:
        explicit = []
        for identity, piece in zip(ids, copied):
            value = piece.get("layer")
            if not _layer(value):
                return _unknown("UNKNOWN_LAYER_ORDER_MISSING",
                                "provide order or a non-negative integer layer on every piece")
            explicit.append((value, identity))
        if len({value for value, _identity in explicit}) != len(explicit):
            return _unknown("UNKNOWN_LAYER_ORDER_AMBIGUOUS",
                            "two pieces share a layer; provide an explicit inner-to-outer order")
        ordered_ids = [identity for _value, identity in sorted(explicit)]
    else:
        if (not isinstance(order, Sequence) or isinstance(order, (str, bytes))
                or any(_piece_id(value) is None for value in order)):
            return _unknown("UNKNOWN_LAYER_ORDER_INVALID",
                            "order must be a sequence of piece ids from inner to outer")
        ordered_ids = [str(value).strip() for value in order]
        if len(ordered_ids) != len(set(ordered_ids)):
            return _unknown("UNKNOWN_LAYER_ORDER_INVALID", "order contains a duplicate piece id")
        missing = sorted(set(ids) - set(ordered_ids))
        extra = sorted(set(ordered_ids) - set(ids))
        if missing or extra:
            return _unknown("UNKNOWN_LAYER_ORDER_INCOMPLETE",
                            "order must contain every piece exactly once", missing=missing, extra=extra)

    by_id = {identity: piece for identity, piece in zip(ids, copied)}
    ordered_pieces = [by_id[identity] for identity in ordered_ids]
    relations = []
    for inner_index, inner in enumerate(ordered_ids):
        for outer in ordered_ids[inner_index + 1:]:
            relations.append({"inner": inner, "outer": outer,
                              "relation": "inside_before_outside"})
    inputs = {"piece_ids": ids, "inner_to_outer": ordered_ids}
    provenance = _provenance("LAYER_ORDER", inputs)
    value = {"inner_to_outer": ordered_ids, "relations": relations,
             "pieces": ordered_pieces}
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        **value,
        "digest": _digest(value),
        "provenance": provenance,
    }


def apply(operation: Any) -> Dict[str, Any]:
    """JSON dispatcher following the fail-closed ``pattern_transforms`` style."""
    if not isinstance(operation, Mapping):
        return _unknown("UNKNOWN_DECORATIVE_OPERATION", "operation must be an object")
    kind = str(operation.get("kind", operation.get("type", ""))).upper()
    values = dict(operation)
    values.pop("kind", None)
    values.pop("type", None)
    try:
        if kind == "RUFFLE":
            return ruffle(**values)
        if kind == "FRILL":
            return frill(**values)
        if kind in ("TIERED_RUFFLE", "TIERED_RUFFLES"):
            return tiered_ruffles(**values)
        if kind == "OVERLAY":
            return overlay(**values)
        if kind in ("LAYER", "LAYER_ORDER"):
            return order_layers(**values)
    except TypeError as exc:
        return _unknown("UNKNOWN_DECORATIVE_OPERATION", str(exc))
    return _unknown("UNKNOWN_DECORATIVE_OPERATION", f"unsupported operation {kind!r}")


# Readable aliases for callers that name construction rather than geometry.
create_ruffle = ruffle
create_frill = frill
create_tiered_ruffles = tiered_ruffles
create_overlay = overlay
explicit_layer_order = order_layers
compose_layers = order_layers
