# -*- coding: utf-8 -*-
"""Resolve proposed surface modifiers against compiled pattern semantics.

``garment.structure.v1`` operations historically address primitive ports.  A
primitive port is not a safe pattern address after one BODY_SHELL expands into
front/back pieces (and one semantic curve may itself contain several ``eN``
segments).  This module defines the stricter, proposal-only binding carried in
``operation.parameters.surface_target``::

    {
      "piece_id": "shell:front",
      "semantic_edge_group": "waist:right",
      "edge_index": 0                 # only needed for a multi-edge group
    }

``piece_id`` may be replaced by selectors (``source_node_id``, ``role``,
``side`` and ``panel``), but those selectors must identify exactly one real
compiled piece.  Likewise, a semantic group must identify exactly one edge,
unless an explicit ``edge_index`` selects one member.  The resolver never
guesses an ``eN`` address from primitive dimensions, port order, or names.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple


ANSWER = "ANSWER"
SCHEMA = "garment.surface-modifier.v1"
BINDING_SCHEMA = "garment.surface-modifier-binding.v1"
KINDS = frozenset({"PLEAT", "DART", "FOLD"})


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _result(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "why": why,
        "state": "REVIEW" if code.startswith("REVIEW_") else "PROPOSED",
        "how_to_close": (
            "name one compiled piece_id and one semantic_edge_group; add an "
            "explicit edge_index when that group contains multiple segments"
        ),
        **detail,
    }


def has_surface_target(operation: Mapping[str, Any]) -> bool:
    """Return whether an operation requests the post-expansion binding path."""
    if not isinstance(operation, Mapping):
        return False
    parameters = operation.get("parameters")
    return (str(operation.get("kind", "")).upper() in KINDS
            and isinstance(parameters, Mapping)
            and "surface_target" in parameters)


def _source_ids(piece: Mapping[str, Any]) -> Set[str]:
    values: Set[str] = set()
    for value in (piece.get("source_node_id"), piece.get("node_id")):
        if isinstance(value, str) and value:
            values.add(value)
    for container_name in ("attributes", "provenance"):
        container = piece.get(container_name)
        if not isinstance(container, Mapping):
            continue
        for key in ("source_node_id", "source_node"):
            value = container.get(key)
            if isinstance(value, str) and value:
                values.add(value)
    return values


def _selector_value(piece: Mapping[str, Any], name: str) -> Any:
    if name in piece:
        return piece.get(name)
    attributes = piece.get("attributes")
    if isinstance(attributes, Mapping):
        return attributes.get(name)
    return None


def _candidate_pieces(operation: Mapping[str, Any], target: Mapping[str, Any],
                      pieces: Sequence[Mapping[str, Any]]) -> Tuple[List[Mapping[str, Any]], Optional[Dict[str, Any]]]:
    piece_id = target.get("piece_id")
    if piece_id is not None and (not isinstance(piece_id, str) or not piece_id.strip()):
        return [], _result(
            "UNKNOWN_SURFACE_MODIFIER_PIECE_SELECTOR",
            "surface_target.piece_id must be a non-empty string")

    source = operation.get("source")
    operation_source = (source.get("node_id")
                        if isinstance(source, Mapping) else None)
    target_source = target.get("source_node_id", operation_source)
    if (target_source is not None
            and (not isinstance(target_source, str) or not target_source.strip())):
        return [], _result(
            "UNKNOWN_SURFACE_MODIFIER_PIECE_SELECTOR",
            "surface_target.source_node_id must be a non-empty string")
    if (isinstance(operation_source, str) and operation_source
            and isinstance(target.get("source_node_id"), str)
            and target["source_node_id"] != operation_source):
        return [], _result(
            "UNKNOWN_SURFACE_MODIFIER_SOURCE_MISMATCH",
            "surface_target.source_node_id must agree with the operation source",
            operation_source_node_id=operation_source,
            target_source_node_id=target.get("source_node_id"))

    candidates = list(pieces)
    if isinstance(piece_id, str):
        candidates = [piece for piece in candidates
                      if piece.get("piece_id") == piece_id]
    if isinstance(target_source, str):
        candidates = [piece for piece in candidates
                      if target_source in _source_ids(piece)]
    for selector in ("role", "side", "panel"):
        expected = target.get(selector)
        if expected is None:
            continue
        if not isinstance(expected, str) or not expected.strip():
            return [], _result(
                "UNKNOWN_SURFACE_MODIFIER_PIECE_SELECTOR",
                f"surface_target.{selector} must be a non-empty string")
        candidates = [piece for piece in candidates
                      if _selector_value(piece, selector) == expected]
    return candidates, None


def _semantic_groups(piece: Mapping[str, Any]) -> Tuple[Optional[Dict[str, List[str]]], Optional[Dict[str, Any]]]:
    edges = piece.get("edges")
    if not isinstance(edges, Mapping):
        return None, _result(
            "UNKNOWN_SURFACE_MODIFIER_PATTERN_EDGES",
            f"{piece.get('piece_id')} has no compiled edge table")
    groups: Dict[str, List[str]] = {}
    declared = piece.get("boundary_edge_groups")
    if isinstance(declared, Mapping):
        for name, raw_edges in declared.items():
            if (not isinstance(name, str) or not name
                    or not isinstance(raw_edges, Sequence)
                    or isinstance(raw_edges, (str, bytes))):
                return None, _result(
                    "UNKNOWN_SURFACE_MODIFIER_EDGE_GROUP_SCHEMA",
                    f"{piece.get('piece_id')} has a malformed boundary edge group")
            groups[name] = [str(edge) for edge in raw_edges]
    semantics = piece.get("edge_semantics")
    if isinstance(semantics, Mapping):
        for edge, semantic in semantics.items():
            if isinstance(semantic, str) and semantic:
                groups.setdefault(semantic, []).append(str(edge))
    for name, addresses in list(groups.items()):
        # Keep declaration order, but remove duplicate addresses introduced by
        # the boundary-group + edge-semantics compatibility views.
        unique = list(dict.fromkeys(addresses))
        missing = [address for address in unique if address not in edges]
        if missing:
            return None, _result(
                "UNKNOWN_SURFACE_MODIFIER_EDGE_LINEAGE",
                f"{piece.get('piece_id')}/{name} references missing compiled edges",
                missing_edges=missing)
        groups[name] = unique
    return groups, None


def resolve(operation: Mapping[str, Any],
            pieces: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Resolve one typed modifier to one real piece and one semantic edge."""
    if not isinstance(operation, Mapping):
        return _result("UNKNOWN_SURFACE_MODIFIER_IR",
                       "surface modifier operation must be an object")
    kind = str(operation.get("kind", "")).upper()
    if kind not in KINDS:
        return _result("UNKNOWN_SURFACE_MODIFIER_KIND",
                       f"unsupported surface modifier {kind!r}",
                       supported=sorted(KINDS))
    modifier_id = operation.get("operation_id")
    if not isinstance(modifier_id, str) or not modifier_id.strip():
        return _result("UNKNOWN_SURFACE_MODIFIER_ID",
                       "operation_id must be a non-empty string")
    parameters = operation.get("parameters")
    if not isinstance(parameters, Mapping):
        return _result("UNKNOWN_SURFACE_MODIFIER_IR",
                       "surface modifier parameters must be an object")
    target = parameters.get("surface_target")
    if not isinstance(target, Mapping):
        return _result("UNKNOWN_SURFACE_MODIFIER_TARGET",
                       "parameters.surface_target must be an object")
    authority = target.get("state", parameters.get("state", "PROPOSED"))
    if authority != "PROPOSED":
        return _result(
            "UNKNOWN_SURFACE_MODIFIER_AUTHORITY",
            "surface modifiers inferred before pattern review must remain PROPOSED",
            requested_state=authority)
    if "edge" in target:
        return _result(
            "UNKNOWN_SURFACE_MODIFIER_RAW_EDGE_FORBIDDEN",
            "surface_target cannot name a raw eN edge; bind through a semantic edge group")

    candidates, error = _candidate_pieces(operation, target, pieces)
    if error:
        return error
    if not candidates:
        return _result(
            "UNKNOWN_SURFACE_MODIFIER_PIECE_NOT_FOUND",
            "surface target selectors do not match a compiled pattern piece",
            selectors=copy.deepcopy(dict(target)),
            known_piece_ids=sorted(str(piece.get("piece_id", ""))
                                   for piece in pieces))
    if len(candidates) != 1:
        return _result(
            "REVIEW_SURFACE_MODIFIER_PIECE_AMBIGUOUS",
            "surface target selectors match more than one compiled pattern piece",
            selectors=copy.deepcopy(dict(target)),
            candidate_piece_ids=sorted(str(piece.get("piece_id", ""))
                                       for piece in candidates))
    piece = candidates[0]

    group_name = target.get("semantic_edge_group", target.get("edge_group"))
    if not isinstance(group_name, str) or not group_name.strip():
        return _result(
            "UNKNOWN_SURFACE_MODIFIER_EDGE_GROUP_REQUIRED",
            "surface_target.semantic_edge_group is required")
    if (target.get("semantic_edge_group") is not None
            and target.get("edge_group") is not None
            and target.get("semantic_edge_group") != target.get("edge_group")):
        return _result(
            "UNKNOWN_SURFACE_MODIFIER_EDGE_GROUP_CONFLICT",
            "semantic_edge_group and edge_group aliases disagree")
    groups, error = _semantic_groups(piece)
    if error:
        return error
    assert groups is not None
    addresses = groups.get(group_name)
    if not addresses:
        return _result(
            "UNKNOWN_SURFACE_MODIFIER_EDGE_GROUP",
            f"{piece.get('piece_id')} has no exact semantic group {group_name!r}",
            known_groups=sorted(groups))
    edge_index = target.get("edge_index")
    if edge_index is None:
        if len(addresses) != 1:
            return _result(
                "REVIEW_SURFACE_MODIFIER_EDGE_AMBIGUOUS",
                "semantic edge group contains multiple real pattern segments",
                piece_id=piece.get("piece_id"),
                semantic_edge_group=group_name,
                candidate_edges=copy.deepcopy(addresses))
        selected = addresses[0]
    else:
        if (isinstance(edge_index, bool) or not isinstance(edge_index, int)
                or edge_index < 0 or edge_index >= len(addresses)):
            return _result(
                "UNKNOWN_SURFACE_MODIFIER_EDGE_INDEX",
                "edge_index must address one member of the semantic edge group",
                semantic_edge_group=group_name,
                group_size=len(addresses))
        selected = addresses[edge_index]

    binding = {
        "schema": BINDING_SCHEMA,
        "modifier_schema": SCHEMA,
        "modifier_id": modifier_id,
        "kind": kind,
        "state": "PROPOSED",
        "source_node_id": operation.get("source", {}).get("node_id"),
        "parameters": {
            str(name): copy.deepcopy(value)
            for name, value in parameters.items()
            if name not in ("surface_target", "state")
        },
        "target": {
            "piece_id": piece.get("piece_id"),
            "semantic_edge_group": group_name,
            "edge": selected,
            "edge_index": addresses.index(selected),
            "group_edges": copy.deepcopy(addresses),
        },
        "resolution": {
            "piece_selection": "EXACT_UNIQUE",
            "edge_selection": ("EXPLICIT_GROUP_INDEX"
                               if edge_index is not None
                               else "UNIQUE_SEMANTIC_GROUP_MEMBER"),
            "primitive_port_edge_used": False,
            "authority_promoted": False,
        },
    }
    binding["digest"] = _digest(binding)
    return {
        "verdict": ANSWER,
        "schema": BINDING_SCHEMA,
        "state": "PROPOSED",
        "piece_id": piece.get("piece_id"),
        "edge": selected,
        "binding": binding,
        "digest": binding["digest"],
    }


resolve_surface_modifier = resolve
