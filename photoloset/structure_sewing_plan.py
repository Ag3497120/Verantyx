# -*- coding: utf-8 -*-
"""Deterministic construction ordering for compiled structure patterns.

This module answers a deliberately narrow question: given the pieces and
topological relations emitted by :mod:`structure_to_pattern`, which operations
must precede which other operations?  It does not invent a stitch class,
fastener, seam finish, interfacing, machine setting, or operator technique.
Those unresolved manufacturing choices are returned as typed ``REVIEW_*``
records while the topology-derived order remains inspectable.

The result is never a manufacturing certificate.  It is a corpus-free and
LLM-free dependency plan for a geometric prototype.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


ANSWER = "ANSWER"
REVIEW_REQUIRED = "REVIEW_MANUFACTURING_CHOICES_REQUIRED"
SOURCE_SCHEMA = "garment.compiled-pattern.v1"
SCHEMA = "garment.structure-sewing-plan.v1"

_SEAM_KINDS = {"JOIN", "GATHER", "OVERLAP", "PROCEDURAL_CLOSURE"}
_TRANSFORM_KINDS = {"DART", "PLEAT", "FOLD", "GATHER"}


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "order_verdict": code,
        "why": why,
        "how_to_close": "supply a valid garment.compiled-pattern.v1 topology",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        **detail,
    }


def _rows(value: Any, name: str) -> Tuple[Optional[List[Mapping[str, Any]]], Optional[Dict[str, Any]]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None, _unknown("UNKNOWN_SEWING_PLAN_INPUT", f"{name} must be a sequence")
    if any(not isinstance(row, Mapping) for row in value):
        return None, _unknown("UNKNOWN_SEWING_PLAN_INPUT", f"every {name} row must be an object")
    return list(value), None


def _piece_id(ref: Any) -> Optional[str]:
    if not isinstance(ref, Mapping):
        return None
    value = ref.get("piece_id")
    return value if isinstance(value, str) and value else None


def _primitive(piece: Mapping[str, Any]) -> str:
    return str(piece.get("primitive_kind", "")).strip().upper()


def _source_node_id(piece: Mapping[str, Any]) -> str:
    value = piece.get("source_node_id")
    if isinstance(value, str) and value:
        return value
    attributes = piece.get("attributes", {})
    if isinstance(attributes, Mapping):
        value = attributes.get("source_node_id")
        if isinstance(value, str) and value:
            return value
    return str(piece.get("piece_id", ""))


def _piece_sleeve_sides(
    piece: Mapping[str, Any], cut_count: int,
) -> Tuple[Optional[Tuple[str, ...]], Optional[Dict[str, Any]]]:
    """Resolve physical sleeve instances without inventing a side.

    Expanded compiler output carries ``derived_side``/instance lineage and a
    cut count of one.  Older compiled patterns may retain one bilateral piece
    with ``cut_count == 2``; that representation is expanded here into two
    planning tasks.  A lone, unaddressed sleeve is not silently called left or
    right.
    """
    if _primitive(piece) != "SLEEVE":
        return (), None
    piece_id = str(piece.get("piece_id", ""))
    attributes = piece.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    provenance = piece.get("provenance", {})
    provenance = provenance if isinstance(provenance, Mapping) else {}
    lineage = provenance.get("instance_lineage", {})
    lineage = lineage if isinstance(lineage, Mapping) else {}

    explicit: List[str] = []
    for value in (attributes.get("derived_side"), lineage.get("side")):
        if isinstance(value, str) and value.strip().lower() in {"left", "right"}:
            explicit.append(value.strip().lower())
    role = str(piece.get("role", "")).strip().lower()
    for side in ("left", "right"):
        if piece_id.lower().endswith(f":{side}") or role.endswith(f"_{side}"):
            explicit.append(side)
    if len(set(explicit)) > 1:
        return None, _unknown(
            "UNKNOWN_SLEEVE_SIDE_AMBIGUOUS",
            f"{piece_id} carries conflicting physical side addresses",
            piece_id=piece_id, side_addresses=sorted(set(explicit)))

    raw_side = attributes.get("side")
    declared_side = str(raw_side).strip().lower() if raw_side is not None else ""
    aliases = {"both": "bilateral", "pair": "bilateral", "左右": "bilateral",
               "左": "left", "右": "right"}
    declared_side = aliases.get(declared_side, declared_side)
    if declared_side and declared_side not in {"left", "right", "bilateral"}:
        return None, _unknown(
            "UNKNOWN_SLEEVE_SIDE_AMBIGUOUS",
            f"{piece_id} has an unsupported sleeve side",
            piece_id=piece_id, side=raw_side)
    quantity = attributes.get("quantity")
    if (quantity is not None
            and (isinstance(quantity, bool) or not isinstance(quantity, int)
                 or quantity not in (1, 2))):
        return None, _unknown(
            "UNKNOWN_SLEEVE_CARDINALITY",
            f"{piece_id} sleeve quantity must be exactly 1 or 2",
            piece_id=piece_id, quantity=quantity)

    if explicit:
        side = explicit[0]
        if declared_side in {"left", "right"} and declared_side != side:
            return None, _unknown(
                "UNKNOWN_SLEEVE_SIDE_AMBIGUOUS",
                f"{piece_id} physical side disagrees with its declared side",
                piece_id=piece_id, physical_side=side,
                declared_side=declared_side)
        if cut_count != 1:
            return None, _unknown(
                "UNKNOWN_SLEEVE_CARDINALITY",
                f"{piece_id} is side-specific and therefore must have cut_count 1",
                piece_id=piece_id, side=side, cut_count=cut_count)
        if quantity == 2 and attributes.get("source_quantity_expanded") is not True:
            return None, _unknown(
                "UNKNOWN_SLEEVE_CARDINALITY",
                f"{piece_id} names one side but still claims two physical instances",
                piece_id=piece_id, side=side, quantity=quantity)
        return (side,), None

    bilateral = (declared_side == "bilateral"
                 or attributes.get("bilateral") is True
                 or quantity == 2 or cut_count == 2)
    if bilateral:
        if cut_count != 2:
            return None, _unknown(
                "UNKNOWN_SLEEVE_CARDINALITY",
                f"{piece_id} is bilateral but its unexpanded cut_count is not 2",
                piece_id=piece_id, cut_count=cut_count, quantity=quantity)
        return ("left", "right"), None
    if declared_side in {"left", "right"}:
        if cut_count != 1 or quantity not in (None, 1):
            return None, _unknown(
                "UNKNOWN_SLEEVE_CARDINALITY",
                f"{piece_id} has inconsistent side and quantity",
                piece_id=piece_id, side=declared_side,
                cut_count=cut_count, quantity=quantity)
        return (declared_side,), None
    return None, _unknown(
        "UNKNOWN_SLEEVE_SIDE_AMBIGUOUS",
        f"{piece_id} is one physical sleeve but does not say left or right",
        piece_id=piece_id, cut_count=cut_count, quantity=quantity)


def _declared_relation_side(row: Mapping[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    values: List[str] = []
    for value in (row.get("relation_side"), row.get("side")):
        if value not in (None, ""):
            values.append(str(value).strip().lower())
    lineage = row.get("pattern_lineage", {})
    if isinstance(lineage, Mapping) and lineage.get("side") not in (None, ""):
        values.append(str(lineage["side"]).strip().lower())
    group = str(row.get("seam_group_id", "")).strip().lower().split(":")
    values.extend(value for value in group if value in {"left", "right"})
    invalid = sorted({value for value in values if value not in {"left", "right"}})
    if invalid or len(set(values)) > 1:
        return None, _unknown(
            "UNKNOWN_SLEEVE_SIDE_AMBIGUOUS",
            "a sleeve relation carries conflicting or unsupported side addresses",
            operation_id=row.get("operation_id"), side_addresses=sorted(set(values)))
    return (values[0] if values else None), None


def _sleeve_relation_sides(
    row: Mapping[str, Any], sleeve_piece_ids: Sequence[str],
    sides_by_piece: Mapping[str, Tuple[str, ...]],
) -> Tuple[Optional[Tuple[str, ...]], Optional[Dict[str, Any]]]:
    declared, error = _declared_relation_side(row)
    if error:
        return None, error
    if not sleeve_piece_ids:
        return (), None
    available = set(sides_by_piece[sleeve_piece_ids[0]])
    for piece_id in sleeve_piece_ids[1:]:
        available.intersection_update(sides_by_piece[piece_id])
    if declared is not None:
        missing = [piece_id for piece_id in sleeve_piece_ids
                   if declared not in sides_by_piece[piece_id]]
        if missing:
            return None, _unknown(
                "UNKNOWN_SLEEVE_RELATION_SIDE_MISMATCH",
                "a sleeve relation selects a side absent from its parent or child",
                operation_id=row.get("operation_id"), side=declared,
                missing_side_piece_ids=missing)
        return (declared,), None
    if not available:
        return None, _unknown(
            "UNKNOWN_SLEEVE_RELATION_SIDE_MISMATCH",
            "a sleeve parent and child have no corresponding physical side",
            operation_id=row.get("operation_id"),
            sleeve_piece_ids=list(sleeve_piece_ids))
    if available == {"left", "right"}:
        return ("left", "right"), None
    if len(available) == 1:
        return (next(iter(available)),), None
    return None, _unknown(
        "UNKNOWN_SLEEVE_SIDE_AMBIGUOUS",
        "a sleeve relation cannot be assigned to one physical side",
        operation_id=row.get("operation_id"), available_sides=sorted(available))


def _sleeve_parent_child(
    row: Mapping[str, Any], a: str, b: str,
    by_piece: Mapping[str, Mapping[str, Any]], expected: str,
) -> Tuple[Optional[Tuple[str, str]], Optional[Dict[str, Any]]]:
    """Resolve child/parent from preserved lineage, never list order alone."""
    lineage = row.get("pattern_lineage", {})
    if isinstance(lineage, Mapping):
        source = _piece_id(lineage.get("source"))
        target = _piece_id(lineage.get("target"))
        relation = str(lineage.get("relation_kind", expected)).upper()
        if source in by_piece and target in by_piece and {source, target} == {a, b}:
            if relation != expected:
                return None, _unknown(
                    "UNKNOWN_SLEEVE_RELATION_UNRESOLVED",
                    "sleeve relation lineage disagrees with the compiled relation kind",
                    operation_id=row.get("operation_id"), expected=expected,
                    lineage_relation=relation)
            return (source, target), None

    candidates: List[Tuple[str, str]] = []
    for child, parent in ((a, b), (b, a)):
        attributes = by_piece[child].get("attributes", {})
        attributes = attributes if isinstance(attributes, Mapping) else {}
        relation = str(attributes.get("sleeve_parent_relation", "")).upper()
        attached_to = attributes.get("attached_to")
        if relation == expected and attached_to == _source_node_id(by_piece[parent]):
            candidates.append((child, parent))
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, _unknown(
            "UNKNOWN_SLEEVE_RELATION_PARENT_AMBIGUOUS",
            "both sleeve pieces claim to be the child in one relation",
            operation_id=row.get("operation_id"), piece_ids=sorted((a, b)))
    return None, _unknown(
        "UNKNOWN_SLEEVE_RELATION_PARENT_REQUIRED",
        "a sleeve segment/layer relation has no exact child-to-parent lineage",
        operation_id=row.get("operation_id"), relation_kind=expected,
        piece_ids=sorted((a, b)))


def _method(row: Mapping[str, Any]) -> Optional[Any]:
    for name in ("construction_method", "seam_method", "method", "stitch_spec"):
        value = row.get(name)
        if value not in (None, "", {}, []):
            return copy.deepcopy(value)
    return None


def _closure_detail(seam: Mapping[str, Any], piece: Mapping[str, Any],
                    features: Sequence[Mapping[str, Any]]) -> Optional[Any]:
    for source in (seam, piece.get("attributes", {})):
        if isinstance(source, Mapping):
            for name in ("closure_detail", "closure_type", "closure", "opening_method"):
                value = source.get(name)
                if value not in (None, "", {}, []):
                    return copy.deepcopy(value)
    piece_id = str(piece.get("piece_id", ""))
    for feature in features:
        if str(feature.get("kind", "")).upper() != "OPENING":
            continue
        target = feature.get("piece_id", feature.get("target_piece_id"))
        if target not in (None, "", piece_id):
            continue
        for name in ("closure_detail", "closure_type", "closure", "method"):
            value = feature.get(name)
            if value not in (None, "", {}, []):
                return copy.deepcopy(value)
    return None


def _review(code: str, scope: str, why: str, how_to_close: str) -> Dict[str, str]:
    return {"verdict": code, "scope": scope, "why": why,
            "how_to_close": how_to_close}


def _task(step_id: str, action: str, *, pieces: Iterable[str] = (),
          operation_id: Optional[str] = None, kind: Optional[str] = None,
          quantity: int = 1, detail: Optional[Mapping[str, Any]] = None,
          phase: int = 30) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "step_id": step_id,
        "action": action,
        "pieces": sorted(set(pieces)),
        "quantity": quantity,
        "depends_on": [],
        "authority": "DERIVED_FROM_COMPILED_TOPOLOGY",
        "manufacturing_validated": False,
        "_phase": phase,
    }
    if operation_id is not None:
        row["operation_id"] = operation_id
    if kind is not None:
        row["kind"] = kind
    if detail:
        row["detail"] = copy.deepcopy(dict(detail))
    return row


def _add_dependency(tasks: Dict[str, Dict[str, Any]], step_id: str,
                    dependencies: Iterable[str]) -> None:
    if step_id not in tasks:
        return
    known = set(tasks[step_id]["depends_on"])
    known.update(name for name in dependencies if name in tasks and name != step_id)
    tasks[step_id]["depends_on"] = sorted(known)


def _topological(tasks: Dict[str, Dict[str, Any]]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    incoming = {name: set(row["depends_on"]) for name, row in tasks.items()}
    missing = {name: sorted(deps - set(tasks)) for name, deps in incoming.items()
               if deps - set(tasks)}
    if missing:
        return None, _unknown("UNKNOWN_SEWING_DEPENDENCY", "a step names an unknown dependency",
                              missing=missing)
    ready = sorted((name for name, deps in incoming.items() if not deps),
                   key=lambda name: (tasks[name]["_phase"], name))
    ordered: List[Dict[str, Any]] = []
    visited: Set[str] = set()
    while ready:
        current = ready.pop(0)
        if current in visited:
            continue
        visited.add(current)
        ordered.append(copy.deepcopy(tasks[current]))
        for name in sorted(incoming):
            incoming[name].discard(current)
            if not incoming[name] and name not in visited and name not in ready:
                ready.append(name)
        ready.sort(key=lambda name: (tasks[name]["_phase"], name))
    if len(visited) != len(tasks):
        return None, _unknown("UNKNOWN_CYCLIC_SEWING_PLAN",
                              "construction dependencies contain a cycle",
                              blocked=sorted(set(tasks) - visited))
    for number, row in enumerate(ordered, 1):
        row.pop("_phase", None)
        row["step"] = number
    return ordered, None


def plan(pattern: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a dependency-safe construction order without sewing claims.

    A successful topology plan has ``order_verdict == ANSWER``.  The top-level
    verdict is ``REVIEW_MANUFACTURING_CHOICES_REQUIRED`` when the order is
    usable but the compiled input does not specify a manufacturing choice.
    """
    if not isinstance(pattern, Mapping) or pattern.get("schema") != SOURCE_SCHEMA:
        return _unknown("UNKNOWN_COMPILED_PATTERN_SCHEMA", f"expected {SOURCE_SCHEMA}")
    if pattern.get("verdict") not in (None, ANSWER):
        return _unknown(str(pattern.get("verdict")),
                        "the source compiler did not produce an answer")
    source_digest = pattern.get("digest")
    if not isinstance(source_digest, str) or not source_digest:
        return _unknown("UNKNOWN_PATTERN_DIGEST_REQUIRED",
                        "the compiled pattern needs its source digest")

    pieces, error = _rows(pattern.get("pieces"), "pieces")
    if error:
        return error
    seams, error = _rows(pattern.get("seams", []), "seams")
    if error:
        return error
    layers, error = _rows(pattern.get("layers", []), "layers")
    if error:
        return error
    features, error = _rows(pattern.get("features", []), "features")
    if error:
        return error
    transforms, error = _rows(pattern.get("transforms", []), "transforms")
    if error:
        return error
    assert pieces is not None and seams is not None and layers is not None
    assert features is not None and transforms is not None

    ids = [row.get("piece_id") for row in pieces]
    if (not ids or any(not isinstance(identity, str) or not identity for identity in ids)
            or len(ids) != len(set(ids))):
        return _unknown("UNKNOWN_PATTERN_PIECES",
                        "piece_id values must be unique, non-empty strings")
    by_piece = {str(row["piece_id"]): row for row in pieces}
    cut_counts: Dict[str, int] = {}
    for identity, piece in by_piece.items():
        count = piece.get("cut_count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            return _unknown("UNKNOWN_PATTERN_CUT_COUNT",
                            f"{identity}.cut_count must be a positive integer")
        cut_counts[identity] = count

    sleeve_sides: Dict[str, Tuple[str, ...]] = {}
    for identity, piece in by_piece.items():
        if _primitive(piece) != "SLEEVE":
            continue
        sides, side_error = _piece_sleeve_sides(piece, cut_counts[identity])
        if side_error or sides is None:
            return side_error  # type: ignore[return-value]
        sleeve_sides[identity] = sides

    # A failed geometric seam cannot be turned into a valid order.
    bad_checks = [row.get("operation_id") for row in pattern.get("seam_checks", [])
                  if isinstance(row, Mapping)
                  and row.get("geometrically_sewable", row.get("sewable")) is False]
    if bad_checks:
        return _unknown("UNKNOWN_GEOMETRIC_SEAM_MISMATCH",
                        "at least one compiled edge pair is not geometrically sewable",
                        operations=sorted(str(value) for value in bad_checks))

    tasks: Dict[str, Dict[str, Any]] = {}
    reviews: List[Dict[str, str]] = []
    prep_for_piece: Dict[str, List[str]] = {identity: [] for identity in by_piece}
    gather_prep: Dict[str, str] = {}

    for index, transform in enumerate(sorted(transforms,
                                              key=lambda row: (str(row.get("operation_id", "")),
                                                               str(row.get("kind", "")),
                                                               str(row.get("address", ""))))):
        kind = str(transform.get("kind", "")).upper()
        if kind not in _TRANSFORM_KINDS:
            return _unknown("UNKNOWN_UNSUPPORTED_SEWING_TRANSFORM",
                            f"unsupported transform {kind!r}")
        operation_id = str(transform.get("operation_id", f"transform-{index + 1}"))
        if kind == "GATHER":
            step_id = f"prepare:gather:{operation_id}"
            gather_prep[operation_id] = step_id
            action = "mark_and_form_gathers"
        else:
            step_id = f"prepare:{kind.lower()}:{operation_id}"
            action = {"DART": "sew_dart", "PLEAT": "form_pleat",
                      "FOLD": "form_fold"}[kind]
        piece_id = transform.get("piece_id", transform.get("node_id"))
        transform_pieces = [str(piece_id)] if piece_id in by_piece else []
        tasks[step_id] = _task(step_id, action, pieces=transform_pieces,
                               operation_id=operation_id, kind=kind,
                               detail=transform, phase=10)
        if transform_pieces:
            prep_for_piece[transform_pieces[0]].append(step_id)
        elif kind != "GATHER":
            reviews.append(_review(
                "REVIEW_TRANSFORM_PIECE_ADDRESS_REQUIRED", operation_id,
                "the compiled transform has no owning piece address",
                "bind the transform to piece_id before using it as shop-floor instruction"))

    seam_tasks: Dict[str, List[str]] = {}
    seam_pieces: Dict[str, Tuple[str, str]] = {}
    intrinsic_by_piece: Dict[str, List[str]] = {identity: [] for identity in by_piece}
    nonclosure_by_piece: Dict[str, List[str]] = {identity: [] for identity in by_piece}
    sleeve_construction: Dict[Tuple[str, str], List[str]] = {}
    sleeve_relations: List[Dict[str, str]] = []
    root_sleeve_tasks: List[Dict[str, str]] = []

    ordered_seams = sorted(seams, key=lambda row: str(row.get("operation_id", "")))
    seen_operations: Set[str] = set()
    for index, seam in enumerate(ordered_seams):
        operation_id = seam.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id or operation_id in seen_operations:
            return _unknown("UNKNOWN_SEAM_OPERATION_ID",
                            "seam operation ids must be unique and non-empty")
        seen_operations.add(operation_id)
        kind = str(seam.get("kind", "")).upper()
        if kind not in _SEAM_KINDS:
            return _unknown("UNKNOWN_UNSUPPORTED_SEAM_KIND",
                            f"{operation_id} uses unsupported seam kind {kind!r}")
        a, b = _piece_id(seam.get("a")), _piece_id(seam.get("b"))
        if a not in by_piece or b not in by_piece:
            return _unknown("UNKNOWN_SEAM_PIECE_ADDRESS",
                            f"{operation_id} does not resolve to compiled pieces")
        assert a is not None and b is not None
        seam_pieces[operation_id] = (a, b)
        primitives = {_primitive(by_piece[a]), _primitive(by_piece[b])}
        sleeve_piece_ids = [piece_id for piece_id in dict.fromkeys((a, b))
                            if piece_id in sleeve_sides]
        relation_type: Optional[str] = None
        child_piece: Optional[str] = None
        parent_piece: Optional[str] = None
        action, phase = "join_pieces", 30
        task_detail: Dict[str, Any] = {}

        if kind == "PROCEDURAL_CLOSURE":
            action, phase = "close_intrinsic_wrap", 50
            detail = _closure_detail(seam, by_piece[a], features)
            if detail is None:
                reviews.append(_review(
                    "REVIEW_CLOSURE_DETAIL_REQUIRED", a,
                    "topology requires a closure seam but placement, fastener/pullover choice, and finish are unspecified",
                    "approve a typed closure detail for this piece"))
            task_detail = {"closure_detail": detail} if detail is not None else {}
            if sleeve_piece_ids:
                relation_type = "SLEEVE_CONSTRUCTION"
        elif sleeve_piece_ids:
            role = str(seam.get("construction_role", "")).strip().upper()
            if len(sleeve_piece_ids) == 1 and a == b:
                if role not in ("", "SLEEVE_UNDERARM"):
                    return _unknown(
                        "UNKNOWN_SLEEVE_RELATION_UNRESOLVED",
                        "an intrinsic sleeve seam has an incompatible construction role",
                        operation_id=operation_id, construction_role=role)
                relation_type = "SLEEVE_CONSTRUCTION"
                action, phase = "construct_sleeve_tube", 20
            elif len(sleeve_piece_ids) == 2:
                segment_contracts = {
                    ("JOIN", "JOIN_SLEEVE_SEGMENTS"): (
                        "LOWER_JOIN", "join_sleeve_segments"),
                    ("GATHER", "GATHER_SLEEVE_SEGMENTS"): (
                        "LOWER_GATHER", "gather_and_join_sleeve_segments"),
                }
                contract = segment_contracts.get((kind, role))
                if contract is None:
                    return _unknown(
                        "UNKNOWN_SLEEVE_RELATION_UNRESOLVED",
                        "a seam between different sleeves must be typed JOIN_SLEEVE_SEGMENTS or GATHER_SLEEVE_SEGMENTS",
                        operation_id=operation_id, kind=kind,
                        construction_role=role)
                resolved, relation_error = _sleeve_parent_child(
                    seam, a, b, by_piece, kind)
                if relation_error or resolved is None:
                    return relation_error  # type: ignore[return-value]
                child_piece, parent_piece = resolved
                relation_type, action = contract
                phase = 28
            elif len(sleeve_piece_ids) == 1:
                sleeve_piece = sleeve_piece_ids[0]
                other_piece = b if sleeve_piece == a else a
                other_primitive = _primitive(by_piece[other_piece])
                if other_primitive == "BODY_SHELL":
                    if kind != "JOIN" or role not in ("", "SET_IN_SLEEVE"):
                        return _unknown(
                            "UNKNOWN_SLEEVE_RELATION_UNRESOLVED",
                            "a root sleeve attachment must be a SET_IN_SLEEVE JOIN to BODY_SHELL",
                            operation_id=operation_id, kind=kind,
                            construction_role=role,
                            other_primitive=other_primitive)
                    relation_type = "ROOT_ATTACHMENT"
                    child_piece, parent_piece = sleeve_piece, other_piece
                    action, phase = "set_root_sleeve", 38
                elif role in {"SET_IN_SLEEVE", "JOIN_SLEEVE_SEGMENTS",
                              "GATHER_SLEEVE_SEGMENTS"}:
                    return _unknown(
                        "UNKNOWN_SLEEVE_RELATION_UNRESOLVED",
                        "a typed root/segment sleeve relation names an incompatible parent primitive",
                        operation_id=operation_id, kind=kind,
                        construction_role=role,
                        other_primitive=other_primitive)
                # Cuff bands, ruffles, tabs and other ordinary pieces may join
                # one sleeve without becoming its structural parent. They keep
                # the generic seam action and still expand over explicit sides.
        elif "HOOD" in primitives:
            action, phase = "attach_hood", 35
        elif "COLLAR" in primitives:
            action, phase = "attach_collar", 35
        elif kind == "GATHER":
            action = "attach_gathered_section"
        elif kind == "OVERLAP":
            action, phase = "secure_overlap", 32

        if sleeve_piece_ids:
            physical_sides, relation_error = _sleeve_relation_sides(
                seam, sleeve_piece_ids, sleeve_sides)
            if relation_error or physical_sides is None:
                return relation_error  # type: ignore[return-value]
        else:
            physical_sides = ()
        expanded_sides: Tuple[Optional[str], ...] = (
            tuple(physical_sides) if physical_sides else (None,))
        generated_steps: List[str] = []
        for side in expanded_sides:
            suffix = (f":{side}" if side is not None and len(physical_sides) > 1
                      else "")
            step_id = f"seam:{operation_id}{suffix}"
            generated_steps.append(step_id)
            detail_for_step = copy.deepcopy(task_detail)
            if relation_type is not None:
                detail_for_step.update({
                    "sleeve_relation_type": relation_type,
                    "relation_side": side,
                    "child_piece": child_piece,
                    "parent_piece": parent_piece,
                    "planning_state": "PROPOSED",
                    "manufacturing_certified": False,
                })
            tasks[step_id] = _task(
                step_id, action, pieces=(a, b), operation_id=operation_id,
                kind=kind, quantity=(1 if side is not None
                                     else max(cut_counts[a], cut_counts[b])),
                detail=detail_for_step, phase=phase)
            _add_dependency(tasks, step_id, prep_for_piece[a] + prep_for_piece[b])
            if kind == "PROCEDURAL_CLOSURE":
                intrinsic_by_piece[a].append(step_id)
            else:
                nonclosure_by_piece[a].append(step_id)
                nonclosure_by_piece[b].append(step_id)
            if relation_type == "SLEEVE_CONSTRUCTION" and side is not None:
                sleeve_construction.setdefault((sleeve_piece_ids[0], side), []).append(step_id)
            elif relation_type in {"LOWER_JOIN", "LOWER_GATHER"}:
                assert child_piece is not None and parent_piece is not None and side is not None
                sleeve_relations.append({
                    "step_id": step_id, "kind": kind, "side": side,
                    "child_piece": child_piece, "parent_piece": parent_piece,
                })
            elif relation_type == "ROOT_ATTACHMENT":
                assert child_piece is not None and parent_piece is not None and side is not None
                root_sleeve_tasks.append({
                    "step_id": step_id, "side": side,
                    "child_piece": child_piece, "parent_piece": parent_piece,
                })
        seam_tasks[operation_id] = generated_steps

        if kind != "PROCEDURAL_CLOSURE" and _method(seam) is None:
            if relation_type in {"ROOT_ATTACHMENT", "LOWER_JOIN",
                                  "LOWER_GATHER", "SLEEVE_CONSTRUCTION"}:
                code = "REVIEW_SLEEVE_CONSTRUCTION_METHOD_REQUIRED"
            else:
                code = ("REVIEW_OVERLAP_FIXING_REQUIRED" if kind == "OVERLAP"
                        else "REVIEW_SEAM_METHOD_REQUIRED")
            reviews.append(_review(
                code, operation_id,
                "edge topology does not specify stitch class, seam finish, or machine operation",
                "choose and verify a construction method for this operation"))
        if kind == "GATHER":
            gather = gather_prep.get(operation_id)
            if gather is None:
                reviews.append(_review(
                    "REVIEW_GATHER_PREPARATION_REQUIRED", operation_id,
                    "the seam is marked GATHER but no measured gather transform is present",
                    "compile a GATHER transform with ratio and finished length"))
            else:
                for step_id in generated_steps:
                    _add_dependency(tasks, step_id, [gather])

    # Sleeve tubes are closed before insertion; other wraps stay open until
    # joins and layer attachments are complete.  This is a deterministic
    # accessibility policy, not a claim that every factory uses it.
    for piece_id, closures in intrinsic_by_piece.items():
        if _primitive(by_piece[piece_id]) == "SLEEVE":
            for attach in nonclosure_by_piece[piece_id]:
                attach_side = tasks[attach].get("detail", {}).get("relation_side")
                matching = [closure for closure in closures
                            if tasks[closure].get("detail", {}).get("relation_side")
                            in (None, attach_side)]
                _add_dependency(tasks, attach, matching)
        else:
            for closure in closures:
                _add_dependency(tasks, closure, nonclosure_by_piece[piece_id])

    # Hood pairs and collar units need preparation before attachment.  Exact
    # crown/fold/interfacing choices are not present in compiled geometry.
    for piece_id in sorted(by_piece):
        piece = by_piece[piece_id]
        primitive = str(piece.get("primitive_kind", "")).upper()
        if primitive not in ("HOOD", "COLLAR"):
            continue
        step_id = f"prepare:{primitive.lower()}:{piece_id}"
        action = "join_hood_pair" if primitive == "HOOD" else "prepare_collar_unit"
        tasks[step_id] = _task(step_id, action, pieces=(piece_id,),
                               quantity=cut_counts[piece_id], phase=15)
        for operation_id, pair in seam_pieces.items():
            if piece_id in pair:
                for seam_step in seam_tasks[operation_id]:
                    _add_dependency(tasks, seam_step, [step_id])
        reviews.append(_review(
            f"REVIEW_{primitive}_CONSTRUCTION_REQUIRED", piece_id,
            f"the {primitive.lower()} geometry does not specify internal seam/fold, stabilization, or edge finish",
            f"approve the {primitive.lower()} construction details"))

    layer_tasks: Dict[str, List[str]] = {}
    sleeve_layer_tasks: List[Dict[str, str]] = []
    seen_layer_operations: Set[str] = set()
    for index, relation in enumerate(sorted(layers,
                                             key=lambda row: (str(row.get("operation_id", "")),
                                                              str(_piece_id(row.get("a")) or "")))):
        operation_id = relation.get("operation_id")
        if (not isinstance(operation_id, str) or not operation_id
                or operation_id in seen_layer_operations):
            return _unknown("UNKNOWN_LAYER_OPERATION_ID",
                            "layer operation ids must be unique and non-empty")
        seen_layer_operations.add(operation_id)
        if str(relation.get("kind", "LAYER")).upper() != "LAYER":
            return _unknown("UNKNOWN_UNSUPPORTED_LAYER_KIND",
                            f"{operation_id} is not a LAYER relation")
        a, b = _piece_id(relation.get("a")), _piece_id(relation.get("b"))
        if a not in by_piece or b not in by_piece:
            code = ("UNKNOWN_SLEEVE_RELATION_PARENT_REQUIRED"
                    if any(piece_id in sleeve_sides for piece_id in (a, b)
                           if piece_id is not None)
                    else "UNKNOWN_LAYER_PIECE_ADDRESS")
            return _unknown(code,
                            f"{operation_id} does not resolve to compiled pieces",
                            operation_id=operation_id)
        assert a is not None and b is not None
        sleeve_piece_ids = [piece_id for piece_id in dict.fromkeys((a, b))
                            if piece_id in sleeve_sides]
        is_sleeve_layer = bool(sleeve_piece_ids)
        child_piece: Optional[str] = None
        parent_piece: Optional[str] = None
        if is_sleeve_layer:
            role = str(relation.get("construction_role", "")).strip().upper()
            if len(sleeve_piece_ids) != 2 or role != "LAYER_SLEEVE_INSTANCE":
                return _unknown(
                    "UNKNOWN_SLEEVE_RELATION_UNRESOLVED",
                    "a sleeve layer must bind two sleeves as LAYER_SLEEVE_INSTANCE",
                    operation_id=operation_id, construction_role=role,
                    sleeve_piece_ids=sleeve_piece_ids)
            resolved, relation_error = _sleeve_parent_child(
                relation, a, b, by_piece, "LAYER")
            if relation_error or resolved is None:
                return relation_error  # type: ignore[return-value]
            child_piece, parent_piece = resolved
            physical_sides, relation_error = _sleeve_relation_sides(
                relation, sleeve_piece_ids, sleeve_sides)
            if relation_error or physical_sides is None:
                return relation_error  # type: ignore[return-value]
        else:
            physical_sides = ()
            declared_side, relation_error = _declared_relation_side(relation)
            if relation_error is not None:
                return relation_error

        generated_steps: List[str] = []
        expanded_sides: Tuple[Optional[str], ...] = (
            tuple(physical_sides) if physical_sides
            else ((declared_side,) if declared_side is not None else (None,)))
        for side in expanded_sides:
            suffix = (f":{side}" if side is not None and len(physical_sides) > 1
                      else "")
            step_id = f"layer:{operation_id}{suffix}"
            generated_steps.append(step_id)
            action = "attach_sleeve_layer" if is_sleeve_layer else "apply_outer_layer"
            detail = {
                "inner_piece": parent_piece if is_sleeve_layer else b,
                "outer_piece": child_piece if is_sleeve_layer else a,
                "planning_state": "PROPOSED",
                "manufacturing_certified": False,
            }
            if side is not None:
                detail["relation_side"] = side
                if is_sleeve_layer:
                    detail["sleeve_relation_type"] = "LAYER"
            tasks[step_id] = _task(
                step_id, action, pieces=(a, b), operation_id=operation_id,
                kind="LAYER", quantity=1 if side is not None else 1,
                detail=detail, phase=34 if is_sleeve_layer else 40)
            _add_dependency(tasks, step_id, prep_for_piece[a])
            if is_sleeve_layer:
                assert child_piece is not None and parent_piece is not None and side is not None
                sleeve_layer_tasks.append({
                    "step_id": step_id, "side": side,
                    "child_piece": child_piece, "parent_piece": parent_piece,
                })
            else:
                _add_dependency(tasks, step_id,
                                nonclosure_by_piece[a] + nonclosure_by_piece[b])
                for closure in intrinsic_by_piece[a] + intrinsic_by_piece[b]:
                    _add_dependency(tasks, closure, [step_id])
        layer_tasks[operation_id] = generated_steps
        if _method(relation) is None:
            reviews.append(_review(
                ("REVIEW_SLEEVE_LAYER_METHOD_REQUIRED" if is_sleeve_layer
                 else "REVIEW_LAYER_ATTACHMENT_REQUIRED"), operation_id,
                "inside/outside topology is known but attachment points and method are not",
                "specify the layer attachment edges, method, and removable/permanent choice"))

    # Resolve the physical sleeve assembly graph before ordering attachment to
    # the bodice.  Every edge is side-specific: a left child can never inherit
    # a right-side parent task merely because both came from one bilateral
    # source primitive.
    join_by_child: Dict[Tuple[str, str], Dict[str, str]] = {}
    for relation in sleeve_relations:
        key = (relation["child_piece"], relation["side"])
        if key in join_by_child:
            return _unknown(
                "UNKNOWN_SLEEVE_RELATION_CARDINALITY",
                "one physical sleeve segment has more than one JOIN parent",
                child_piece=key[0], side=key[1],
                step_ids=sorted((join_by_child[key]["step_id"],
                                 relation["step_id"])))
        join_by_child[key] = relation

    def sleeve_ancestor(piece_id: str, side: str) -> Tuple[Optional[List[str]], Optional[Dict[str, Any]]]:
        chain = [piece_id]
        seen = {piece_id}
        current = piece_id
        while (current, side) in join_by_child:
            parent = join_by_child[(current, side)]["parent_piece"]
            if parent in seen:
                return None, _unknown(
                    "UNKNOWN_CYCLIC_SEWING_PLAN",
                    "the side-specific sleeve parent graph contains a cycle",
                    side=side, sleeve_chain=chain + [parent])
            if side not in sleeve_sides.get(parent, ()):
                return None, _unknown(
                    "UNKNOWN_SLEEVE_RELATION_SIDE_MISMATCH",
                    "a sleeve JOIN parent does not contain the child's physical side",
                    side=side, child_piece=current, parent_piece=parent)
            chain.append(parent)
            seen.add(parent)
            current = parent
        return chain, None

    for relation in sleeve_relations:
        side = relation["side"]
        child = relation["child_piece"]
        parent = relation["parent_piece"]
        dependencies = (
            sleeve_construction.get((parent, side), [])
            + sleeve_construction.get((child, side), []))
        prior = join_by_child.get((parent, side))
        if prior is not None:
            dependencies.append(prior["step_id"])
        _add_dependency(tasks, relation["step_id"], dependencies)

    layer_by_child: Dict[Tuple[str, str], Dict[str, str]] = {}
    for relation in sleeve_layer_tasks:
        key = (relation["child_piece"], relation["side"])
        if key in layer_by_child:
            return _unknown(
                "UNKNOWN_SLEEVE_RELATION_CARDINALITY",
                "one physical oversleeve has more than one layer parent",
                child_piece=key[0], side=key[1],
                step_ids=sorted((layer_by_child[key]["step_id"],
                                 relation["step_id"])))
        layer_by_child[key] = relation
        side = relation["side"]
        parent = relation["parent_piece"]
        child = relation["child_piece"]
        chain, chain_error = sleeve_ancestor(parent, side)
        if chain_error or chain is None:
            return chain_error  # type: ignore[return-value]
        dependencies = (sleeve_construction.get((parent, side), [])
                        + sleeve_construction.get((child, side), []))
        dependencies.extend(
            join["step_id"] for join in sleeve_relations
            if join["side"] == side
            and (join["child_piece"] in chain or join["parent_piece"] in chain))
        _add_dependency(tasks, relation["step_id"], dependencies)

    for root in root_sleeve_tasks:
        side = root["side"]
        root_piece = root["child_piece"]
        dependencies = list(sleeve_construction.get((root_piece, side), []))
        for relation in sleeve_relations:
            if relation["side"] != side:
                continue
            chain, chain_error = sleeve_ancestor(relation["child_piece"], side)
            if chain_error or chain is None:
                return chain_error  # type: ignore[return-value]
            if root_piece in chain:
                dependencies.append(relation["step_id"])
        for relation in sleeve_layer_tasks:
            if relation["side"] != side:
                continue
            chain, chain_error = sleeve_ancestor(relation["parent_piece"], side)
            if chain_error or chain is None:
                return chain_error  # type: ignore[return-value]
            if root_piece in chain:
                dependencies.append(relation["step_id"])
        _add_dependency(tasks, root["step_id"], dependencies)

    # When multiple outer layers share a base, apply lower numbered layers
    # first.  Ties remain deterministic by operation id and are flagged.
    layer_rows = []
    for relation in layers:
        operation_id = str(relation["operation_id"])
        outer = _piece_id(relation.get("a"))
        inner = _piece_id(relation.get("b"))
        layer_rows.append((int(by_piece[str(outer)].get("layer", 0)), operation_id,
                           str(outer), str(inner)))
    for current, later in zip(sorted(layer_rows), sorted(layer_rows)[1:]):
        if current[3] == later[3]:
            for later_step in layer_tasks[later[1]]:
                later_side = tasks[later_step].get("detail", {}).get("relation_side")
                matching = [current_step for current_step in layer_tasks[current[1]]
                            if tasks[current_step].get("detail", {}).get("relation_side")
                            in (None, later_side)]
                _add_dependency(tasks, later_step, matching)
            if current[0] == later[0]:
                reviews.append(_review(
                    "REVIEW_LAYER_ORDER_TIE", f"{current[1]},{later[1]}",
                    "two outer pieces share a base and the same numeric layer",
                    "approve an explicit inner-to-outer order"))

    opening_tasks: List[str] = []
    for index, feature in enumerate(sorted(features,
                                            key=lambda row: (str(row.get("kind", "")),
                                                             str(row.get("node_id", ""))))):
        kind = str(feature.get("kind", "")).upper()
        if kind != "OPENING":
            reviews.append(_review(
                "REVIEW_UNSUPPORTED_FEATURE", str(feature.get("node_id", index)),
                f"feature {kind!r} has no deterministic sewing-order rule",
                "provide a typed construction rule for this feature"))
            continue
        node_id = str(feature.get("node_id", f"opening-{index + 1}"))
        target = feature.get("piece_id", feature.get("target_piece_id"))
        target_id = target if isinstance(target, str) and target in by_piece else None
        step_id = f"opening:{node_id}"
        opening_tasks.append(step_id)
        pieces_for_step = [target_id] if target_id is not None else []
        tasks[step_id] = _task(step_id, "finish_opening", pieces=pieces_for_step,
                               operation_id=node_id, kind="OPENING",
                               detail=feature, phase=45)
        if target_id is not None:
            _add_dependency(tasks, step_id, nonclosure_by_piece[target_id])
            for closure in intrinsic_by_piece[target_id]:
                _add_dependency(tasks, closure, [step_id])
            missing_method = _closure_detail({}, by_piece[target_id], [feature]) is None
        else:
            missing_method = all(feature.get(name) in (None, "", {}, [])
                                 for name in ("closure_detail", "closure_type",
                                              "closure", "method"))
        if missing_method:
            reviews.append(_review(
                "REVIEW_OPENING_METHOD_REQUIRED", node_id,
                "opening length alone does not determine placement, fastener, facing, or finish",
                "bind the opening to a piece and approve its construction detail"))
        if target_id is None:
            reviews.append(_review(
                "REVIEW_OPENING_PIECE_ADDRESS_REQUIRED", node_id,
                "the opening is not bound to a compiled piece",
                "set piece_id or target_piece_id on the opening feature"))

    if not tasks:
        reviews.append(_review(
            "REVIEW_NO_CONSTRUCTION_OPERATIONS", "pattern",
            "the compiled pattern contains pieces but no seam, layer, transform, or opening operation",
            "confirm that the item is intentionally unsewn or compile its construction topology"))

    ordered, error = _topological(tasks)
    if error:
        return error
    assert ordered is not None

    # Stable de-duplication keeps one typed record per choice and scope.
    review_table = {(row["verdict"], row["scope"]): row for row in reviews}
    reviews = [review_table[key] for key in sorted(review_table)]
    approval = copy.deepcopy(pattern.get("approval"))
    approval_digest = None
    approval_id = None
    if isinstance(approval, Mapping):
        approval_digest = approval.get("digest", approval.get("candidate_digest"))
        approval_id = approval.get("approval_id")
    provenance = {
        "method": "deterministic dependency planning from compiled topology",
        "corpus_used": False,
        "llm_used": False,
        "source_schema": SOURCE_SCHEMA,
        "source_pattern_digest": source_digest,
        "structure_digest": pattern.get("structure_digest"),
        "candidate_id": pattern.get("candidate_id"),
        "candidate_state": pattern.get("candidate_state"),
        "approval_digest": approval_digest,
        "approval_id": approval_id,
        "digest_is_preserved_not_recertified": True,
    }
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": REVIEW_REQUIRED if reviews else ANSWER,
        "order_verdict": ANSWER,
        "candidate_id": pattern.get("candidate_id"),
        "candidate_state": pattern.get("candidate_state"),
        "structure_digest": pattern.get("structure_digest"),
        "source_pattern_digest": source_digest,
        "approval": approval,
        "steps": ordered,
        "dependency_graph": {row["step_id"]: list(row["depends_on"])
                             for row in ordered},
        "reviews": reviews,
        "unknowns": [],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "claims": {
            "deterministic_topology_order": True,
            "operator_reachability_proven": False,
            "seam_strength_proven": False,
            "industrial_standard_conformance": False,
        },
        "provenance": provenance,
        "not_a_certificate": (
            "This dependency order is not a manufacturing, strength, safety, "
            "fit, comfort, or industrial sewing certification."),
    }
    result["digest"] = _digest(result)
    return result


build = plan
