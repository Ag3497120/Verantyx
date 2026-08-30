# -*- coding: utf-8 -*-
"""Proposal-only rear/hidden construction ensemble.

The front image analysis path can tell us which garment parts are visible.  It
cannot observe the rear, hidden joins, seam topology, or material mechanics.
This module therefore does not choose a back and does not call
``sewing_search``.  It combines four independent proposal/evidence channels:

* FashionSigLIP retrieval hits, treated as visually similar references;
* multimodal model proposals, treated as model-authored hypotheses;
* deterministic geometric-rule evidence; and
* named user-audit evidence.

Their claims are normalized independently and retained independently.  Rear
candidates are ranked on four inspectable axes (structure, parts, seams, and
material), never on one embedding score.  Deterministic geometry-only
alternatives are always available, including when no corpus/backend exists.
Every hidden and material value remains ``PROPOSED`` and
``UNKNOWN_UNOBSERVED`` until a named person approves an exact candidate
digest.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import corpus_manifest


REQUEST_SCHEMA = "garment.rear-candidate-ensemble.request.v1"
SCHEMA = "garment.rear-candidate-ensemble.v1"
PROPOSED = "PROPOSED"
UNKNOWN_UNOBSERVED = "UNKNOWN_UNOBSERVED"
CONTESTED = "CONTESTED"
SHAPE_NOT_APPROVED = "UNKNOWN_SHAPE_NOT_APPROVED"
APPROVAL_STALE = "UNKNOWN_GEOMETRY_APPROVAL_STALE"
ASPECTS = ("structure", "parts", "seams", "material")
HYPOTHESIS_SCHEMA = "garment.typed-rear-hypothesis.v1"
HYPOTHESIS_AXES = (
    "closure", "back_volume", "layer_continuation", "attachment_topology",
)
CLAIM_FIELDS = ASPECTS + HYPOTHESIS_AXES

_AUTHORITY_KEYS = {
    "approval", "approved", "authority", "fact", "manufacturing_certified",
    "manufacturing_ready", "observed", "state", "verdict",
}
_MODEL_PROSE_KEYS = {
    "analysis", "answer", "content", "message", "narrative", "reasoning",
    "response", "text", "thinking",
}
_REAR_KEYS = (
    "rear_structure", "hidden_structure", "rear", "back",
    "structure", "structure_graph",
)
_PART_KEYS = ("parts", "components", "rear_parts", "hidden_parts", "nodes")
_SEAM_KEYS = (
    "seam_topology", "seams", "rear_seams", "hidden_seams", "operations",
    "relations",
)
_MATERIAL_KEYS = ("material", "materials", "material_ranges")
_HYPOTHESIS_KEYS = {
    "closure": (
        "closure", "back_closure", "rear_closure", "opening",
        "opening_topology", "fastener", "configuration",
    ),
    "back_volume": (
        "back_volume", "rear_volume", "volume", "volume_profile",
        "back_ease", "rear_ease", "ease",
    ),
    "layer_continuation": (
        "layer_continuation", "rear_layer_continuation",
        "back_layer_continuation", "layer_order", "rear_layer_order",
    ),
    "attachment_topology": (
        "attachment_topology", "rear_attachment_topology", "attachments",
        "attachment", "anchor_topology", "joins",
    ),
}


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _plain(value: Any) -> Any:
    """Return canonical-JSON-compatible data and reject non-finite numbers."""
    if isinstance(value, Mapping):
        return {
            str(key): _plain(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if _sequence(value):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not valid ensemble input")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    return str(value)


def stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _token(value: Any, default: str = "unspecified") -> str:
    text = _text(value).lower()
    text = re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE).strip("-")
    return text or default


def _proposal_value(value: Any) -> Any:
    """Remove source-declared authority while preserving semantic content."""
    if isinstance(value, Mapping):
        return {
            str(key): _proposal_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key).lower() not in _AUTHORITY_KEYS
            and str(key).lower() not in _MODEL_PROSE_KEYS
        }
    if _sequence(value):
        rows = [_proposal_value(child) for child in value]
        return sorted(rows, key=stable_digest)
    return _plain(value)


def _finite_score(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _source_provenance(
    source_kind: str, source_id: str, row: Mapping[str, Any], index: int,
) -> Dict[str, Any]:
    native = row.get("provenance")
    provenance = {
        "source_kind": source_kind,
        "source_id": source_id,
        "source_index": index,
        "source_payload_digest": stable_digest(_proposal_value(row)),
        "corpus": None,
        "real_corpus_record": source_kind == "FASHION_SIGLIP_RETRIEVAL",
        "network_used_by_this_module": False,
    }
    if source_kind == "FASHION_SIGLIP_RETRIEVAL":
        provenance["adapter"] = "Marqo/marqo-fashionSigLIP"
        provenance["corpus"] = _proposal_value(
            row.get("source", row.get("asset", {})))
    elif source_kind == "MULTIMODAL_MODEL_PROPOSAL":
        provenance["adapter"] = _text(row.get("model_id")) or "multimodal-model"
    elif source_kind == "GEOMETRIC_RULE_EVIDENCE":
        provenance["adapter"] = (
            _text(row.get("rule_set_id")) or "deterministic-geometric-rules")
        provenance["rule_evidence_is_not_rear_observation"] = True
    elif source_kind == "USER_AUDIT_EVIDENCE":
        provenance["adapter"] = "named-user-audit"
        provenance["auditor"] = (
            _text(row.get("auditor")) or _text(row.get("by")) or None)
        provenance["visible_audit_does_not_observe_hidden_rear"] = True
    else:
        provenance["adapter"] = "unknown-proposal-source"
    if native is not None:
        provenance["source_provenance"] = _proposal_value(native)
    score = _finite_score(row.get("score", row.get("similarity")))
    if score is not None:
        provenance["source_score"] = score
        provenance["source_score_is_not_authority"] = True
    return provenance


def _unobserved_record(
    value: Any, *, basis: str, breaks_when: str,
    provenance: Mapping[str, Any], field: str,
    preserve_typed_children: bool = False,
) -> Dict[str, Any]:
    record = {
        "field": field,
        "state": PROPOSED,
        "observation_state": UNKNOWN_UNOBSERVED,
        "visibility": UNKNOWN_UNOBSERVED,
        "observed": False,
        "value": (_plain(value) if preserve_typed_children
                  else _proposal_value(value)),
        "basis": basis,
        "breaks_when": breaks_when,
        "provenance": _plain(provenance),
        "fact_promotions": [],
    }
    record["digest"] = stable_digest(record)
    return record


def _first(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "", [], {}):
            return row[key]
    return None


def _embedded_values(value: Any, keys: Iterable[str]) -> List[Any]:
    if not isinstance(value, Mapping):
        return []
    rows: List[Any] = []
    for key in keys:
        child = value.get(key)
        if child not in (None, "", [], {}):
            rows.append(child)
    return rows


def _rows(value: Any, keys: Iterable[str]) -> List[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in keys:
            child = value.get(key)
            if _sequence(child):
                return [dict(row) for row in child if isinstance(row, Mapping)]
        return [dict(value)]
    if _sequence(value):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _normalise_part(
    raw: Mapping[str, Any], *, fallback_id: str, garment_unit: str,
    inherited_layer: int = 0, parent: str = "",
) -> Dict[str, Any]:
    name = (_text(raw.get("name")) or _text(raw.get("label"))
            or _text(raw.get("semantic_role")) or _text(raw.get("kind"))
            or _text(raw.get("primitive_kind")) or fallback_id)
    part_id = (_text(raw.get("part_id")) or _text(raw.get("node_id"))
               or _text(raw.get("component_id")) or _text(raw.get("id"))
               or fallback_id)
    kind = (_text(raw.get("kind")) or _text(raw.get("primitive_kind"))
            or _text(raw.get("geometry_role")) or name)
    layer = raw.get("layer", inherited_layer)
    if isinstance(layer, bool) or not isinstance(layer, int):
        layer = inherited_layer
    unit = (_text(raw.get("garment_unit")) or _text(raw.get("instance_id"))
            or garment_unit or "visible-unit")
    parent_id = _text(raw.get("parent_part_id")) or parent
    return {
        "part_id": _token(part_id),
        "display_name": name,
        "kind": kind.upper().replace(" ", "_"),
        "layer": layer,
        "garment_unit": _token(unit),
        "parent_part_id": _token(parent_id, "") if parent_id else "",
        "laterality": _text(raw.get("laterality", raw.get("side"))).upper(),
        "dimensions": _proposal_value(raw.get(
            "dimensions", raw.get("dimensions_cm", {}))),
        "visible_material_cues": _proposal_value(_first(raw, _MATERIAL_KEYS)),
        "placement": _text(raw.get("placement")),
        "visible_source_state": _text(raw.get("state")) or "UNSPECIFIED",
    }


def _walk_parts(
    value: Any, *, garment_unit: str, inherited_layer: int = 0,
    parent: str = "", path: str = "part",
) -> List[Dict[str, Any]]:
    if not _sequence(value):
        return []
    out: List[Dict[str, Any]] = []
    for index, child in enumerate(value):
        if isinstance(child, str):
            child = {"name": child}
        if not isinstance(child, Mapping):
            continue
        fallback = f"{path}-{index + 1}"
        part = _normalise_part(
            child, fallback_id=fallback, garment_unit=garment_unit,
            inherited_layer=inherited_layer, parent=parent,
        )
        out.append(part)
        nested = child.get("children", child.get("parts"))
        out.extend(_walk_parts(
            nested, garment_unit=part["garment_unit"],
            inherited_layer=part["layer"], parent=part["part_id"],
            path=part["part_id"],
        ))
    return out


def _normalise_visible_graph(graph: Mapping[str, Any]) -> Dict[str, Any]:
    parts: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []

    containers: List[Mapping[str, Any]] = [graph]
    for key in ("structure_graph", "structure", "graph"):
        child = graph.get(key)
        if isinstance(child, Mapping):
            containers.append(child)

    for container in containers:
        direct = container.get("parts")
        if direct is None:
            direct = container.get("nodes")
        parts.extend(_walk_parts(
            direct, garment_unit=_text(container.get("garment_unit"))
            or _text(container.get("graph_id")) or "visible-unit",
        ))
        for key in ("relations", "operations"):
            values = container.get(key)
            if not _sequence(values):
                continue
            for index, raw in enumerate(values):
                if not isinstance(raw, Mapping):
                    continue
                relations.append({
                    "relation_id": _text(raw.get("relation_id"))
                    or _text(raw.get("operation_id")) or f"relation-{index + 1}",
                    "kind": _text(raw.get("kind")) or "UNSPECIFIED",
                    "source": _proposal_value(raw.get("source", raw.get("a"))),
                    "target": _proposal_value(raw.get("target", raw.get("b"))),
                    "connection": _text(raw.get("connection", raw.get("label"))),
                })

    instances = graph.get("garment_instances", graph.get("instances"))
    if _sequence(instances):
        for index, instance in enumerate(instances):
            if not isinstance(instance, Mapping):
                continue
            unit = (_text(instance.get("instance_id"))
                    or _text(instance.get("garment_id"))
                    or f"instance-{index + 1}")
            layer = instance.get("layer", 0)
            if isinstance(layer, bool) or not isinstance(layer, int):
                layer = 0
            nested = instance.get("parts", instance.get("components"))
            parts.extend(_walk_parts(
                nested, garment_unit=unit, inherited_layer=layer,
                path=_token(unit),
            ))

    visible_parts = graph.get("visible_parts")
    if _sequence(visible_parts):
        for index, row in enumerate(visible_parts):
            if not isinstance(row, Mapping):
                continue
            value = row.get("value", row)
            if not isinstance(value, Mapping):
                value = {"name": value}
            subject = _text(row.get("subject"))
            unit = subject.split(":", 1)[-1] if subject else "visible-unit"
            parts.extend(_walk_parts(
                [value], garment_unit=unit, path=f"visible-{index + 1}",
            ))

    claims = graph.get("claims")
    if _sequence(claims):
        for index, claim in enumerate(claims):
            if (not isinstance(claim, Mapping)
                    or claim.get("category") != "VISIBLE_COMPONENT"):
                continue
            value = claim.get("value")
            if not isinstance(value, Mapping):
                continue
            subject = _text(claim.get("subject"))
            unit = subject.split(":", 1)[-1] if subject else "visible-unit"
            parts.extend(_walk_parts(
                [value], garment_unit=unit, path=f"claim-{index + 1}",
            ))

    # Dedupe exact repetitions from graph aliases, but retain distinct parts
    # that happen to share a display name.
    exact: Dict[str, Dict[str, Any]] = {}
    for part in parts:
        exact.setdefault(stable_digest(part), part)
    parts = list(exact.values())
    parts.sort(key=lambda row: (
        row["garment_unit"], row["layer"], row["part_id"], stable_digest(row),
    ))
    seen_ids: Dict[str, int] = defaultdict(int)
    for part in parts:
        seen_ids[part["part_id"]] += 1
        if seen_ids[part["part_id"]] > 1:
            part["part_id"] += "-" + stable_digest(part)[:8]
    relations = sorted(
        {stable_digest(row): row for row in relations}.values(),
        key=lambda row: (row["relation_id"], stable_digest(row)),
    )
    return {
        "parts": parts,
        "relations": relations,
        "garment_name": _text(graph.get("garment_name")),
        "source_digest": stable_digest(_proposal_value(graph)),
    }


def _tokens(value: Any) -> Tuple[str, ...]:
    ignored = _AUTHORITY_KEYS | _MODEL_PROSE_KEYS | {
        "digest", "provenance", "score", "similarity",
    }
    out: List[str] = []
    if isinstance(value, Mapping):
        for key, child in sorted(value.items(), key=lambda item: str(item[0])):
            if str(key).lower() in ignored:
                continue
            child_tokens = _tokens(child)
            out.extend(child_tokens)
            out.extend(f"{str(key).lower()}:{token}" for token in child_tokens)
    elif _sequence(value):
        for child in value:
            out.extend(_tokens(child))
    elif value is not None:
        out.extend(token.lower() for token in re.findall(
            r"[\w-]+", str(value), flags=re.UNICODE) if token.strip())
    return tuple(sorted(set(out)))


def _visible_aspects(graph: Mapping[str, Any]) -> Dict[str, Any]:
    parts = graph["parts"]
    return {
        "structure": [
            {
                "kind": row["kind"], "layer": row["layer"],
                "garment_unit": row["garment_unit"],
                "parent_part_id": row["parent_part_id"],
            }
            for row in parts
        ] + list(graph["relations"]),
        "parts": [
            {"part_id": row["part_id"], "kind": row["kind"],
             "name": row["display_name"], "laterality": row["laterality"]}
            for row in parts
        ],
        "seams": list(graph["relations"]),
        "material": [row["visible_material_cues"] for row in parts
                     if row["visible_material_cues"] not in (None, "", [], {})],
    }


def _source_aspects(row: Mapping[str, Any]) -> Dict[str, Any]:
    structure = _first(row, _REAR_KEYS)
    parts = _first(row, _PART_KEYS)
    seams = _first(row, _SEAM_KEYS)
    material = _first(row, _MATERIAL_KEYS)
    if isinstance(structure, Mapping):
        if parts is None:
            parts = _first(structure, _PART_KEYS)
        if seams is None:
            seams = _first(structure, _SEAM_KEYS)
    result = {
        "structure": _proposal_value(structure),
        "parts": _proposal_value(parts),
        "seams": _proposal_value(seams),
        "material": _proposal_value(material),
    }
    containers = [row]
    if isinstance(structure, Mapping):
        containers.append(structure)
    for axis, keys in _HYPOTHESIS_KEYS.items():
        value = None
        for container in containers:
            value = _first(container, keys)
            if value not in (None, "", [], {}):
                break
        result[axis] = _proposal_value(value)
    return result


def _set_match(observed: Any, candidate: Any) -> Tuple[Optional[float], List[str]]:
    left, right = set(_tokens(observed)), set(_tokens(candidate))
    if not left:
        return None, []
    if not right:
        return 0.0, ["candidate omitted this observed aspect"]
    overlap = left & right
    score = len(overlap) / len(left | right)
    conflict = [] if overlap else ["no canonical tokens overlap"]
    return round(score, 6), conflict


def _score_aspects(observed: Mapping[str, Any], candidate: Mapping[str, Any]
                   ) -> Dict[str, Any]:
    axis_scores: Dict[str, Optional[float]] = {}
    contradictions: Dict[str, List[str]] = {}
    supplied: List[str] = []
    for aspect in ASPECTS:
        value = candidate.get(aspect)
        if _tokens(value):
            supplied.append(aspect)
        score, conflicts = _set_match(observed.get(aspect), value)
        axis_scores[aspect] = score
        if conflicts:
            contradictions[aspect] = conflicts
    matched = sum(1 for score in axis_scores.values()
                  if score is not None and score > 0.0)
    return {
        "axis_scores": axis_scores,
        "supplied_axes": supplied,
        "coverage_count": len(supplied),
        "matched_axis_count": matched,
        "contradictions": contradictions,
        "single_embedding_winner": False,
        "scalar_embedding_score_used_for_authority": False,
    }


def _expand_alternatives(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    direct = row.get("rear_candidates")
    if _sequence(direct):
        expanded: List[Dict[str, Any]] = []
        for alternative in direct:
            child = dict(row)
            child.pop("rear_candidates", None)
            child["rear_structure"] = alternative
            expanded.append(child)
        return expanded
    rear = _first(row, ("rear_structure", "hidden_structure", "rear", "back"))
    if isinstance(rear, Mapping) and _sequence(rear.get("alternatives")):
        expanded = []
        for alternative in rear["alternatives"]:
            child = dict(row)
            inherited = {key: value for key, value in rear.items()
                         if key != "alternatives"}
            if isinstance(alternative, Mapping):
                inherited.update(alternative)
                child["rear_structure"] = inherited
            else:
                child["rear_structure"] = {
                    **inherited, "configuration": alternative,
                }
            expanded.append(child)
        return expanded
    return [dict(row)]


def _normalise_sources(
    fashion_hits: Any, multimodal_proposals: Any,
    geometric_rule_evidence: Any = None, user_audit_evidence: Any = None,
    *, require_commercial: bool = False,
) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    configurations = (
        ("FASHION_SIGLIP_RETRIEVAL", fashion_hits,
         ("matches", "hits", "nearest_items", "items")),
        ("MULTIMODAL_MODEL_PROPOSAL", multimodal_proposals,
         ("proposals", "rear_candidates", "candidates", "instances")),
        ("GEOMETRIC_RULE_EVIDENCE", geometric_rule_evidence,
         ("rules", "evidence", "proposals", "candidates")),
        ("USER_AUDIT_EVIDENCE", user_audit_evidence,
         ("audits", "evidence", "decisions", "proposals")),
    )
    for source_kind, value, keys in configurations:
        native_rows = _rows(value, keys)
        expanded = [child for row in native_rows
                    for child in _expand_alternatives(row)]
        expanded.sort(key=lambda row: stable_digest(_proposal_value(row)))
        for index, row in enumerate(expanded):
            if source_kind == "FASHION_SIGLIP_RETRIEVAL":
                gate = row.get("commercial_rights_gate")
                upstream_refused = (
                    isinstance(gate, Mapping)
                    and gate.get("required") is True
                    and gate.get("allowed") is not True
                )
                explicit_rights = corpus_manifest.commercial_rights_status(
                    row, require_commercial=True)
                # Preserve an upstream strict refusal.  When this request is
                # commercial, an absent/ambiguous rights record also fails
                # closed instead of silently becoming a usable rear source.
                if upstream_refused or (
                        require_commercial and not explicit_rights["allowed"]):
                    continue
            source_id = (
                _text(row.get("item_id")) or _text(row.get("proposal_id"))
                or _text(row.get("candidate_id")) or _text(row.get("id"))
                or f"{source_kind.lower()}-{index + 1}"
            )
            provenance = _source_provenance(
                source_kind, source_id, row, index)
            sources.append({
                "source_kind": source_kind,
                "source_id": source_id,
                "row": _proposal_value(row),
                "aspects": _source_aspects(row),
                "provenance": provenance,
            })
    return sorted(sources, key=lambda row: (
        row["source_kind"], row["source_id"], stable_digest(row["row"]),
    ))


def _source_claims(sources: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    for source in sources:
        for aspect in CLAIM_FIELDS:
            value = source["aspects"].get(aspect)
            if value in (None, "", [], {}):
                continue
            breaks = (
                "a rear/side image, approved 3D comparison, or topology test contradicts it"
                if aspect != "material" else
                "a swatch, material measurement, or motion test contradicts it"
            )
            basis = (
                f"{source['source_kind']} {source['source_id']} proposed the "
                f"{aspect} aspect; it is not direct rear evidence"
            )
            typed = _unobserved_record(
                value, basis=basis, breaks_when=breaks,
                provenance=source["provenance"], field=aspect,
            )
            typed["claim_id"] = "rear-claim-" + stable_digest({
                "source": source["source_kind"],
                "source_id": source["source_id"],
                "aspect": aspect, "value": typed["value"],
            })[:18]
            # claim_id is part of the sealed claim.
            typed["digest"] = stable_digest({
                key: value for key, value in typed.items() if key != "digest"
            })
            claims.append(typed)
    return sorted(claims, key=lambda row: (
        row["field"], row["provenance"]["source_kind"],
        row["provenance"]["source_id"], row["claim_id"],
    ))


def _contested(claims: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for claim in claims:
        grouped[str(claim["field"])].append(claim)
    out: List[Dict[str, Any]] = []
    for aspect in CLAIM_FIELDS:
        rows = grouped.get(aspect, [])
        values = {stable_digest(row["value"]) for row in rows}
        sources = {
            (row["provenance"]["source_kind"],
             row["provenance"]["source_id"])
            for row in rows
        }
        if len(values) < 2 or len(sources) < 2:
            continue
        record = {
            "contest_id": "rear-contest-" + stable_digest({
                "aspect": aspect, "values": sorted(values),
            })[:16],
            "aspect": aspect,
            "state": CONTESTED,
            "observation_state": UNKNOWN_UNOBSERVED,
            "alternatives": [
                {
                    "claim_id": row["claim_id"],
                    "source_kind": row["provenance"]["source_kind"],
                    "source_id": row["provenance"]["source_id"],
                    "value": copy.deepcopy(row["value"]),
                    "state": PROPOSED,
                }
                for row in rows
            ],
            "no_averaging": True,
            "resolution": "HUMAN_REVIEW_OR_NEW_REAR_EVIDENCE_REQUIRED",
            "basis": "independent proposal sources supplied incompatible values",
            "breaks_when": "a named human resolves the alternatives or new rear evidence removes the conflict",
            "provenance": {
                "claim_ids": sorted(row["claim_id"] for row in rows),
                "independent_claims_preserved": True,
            },
        }
        record["digest"] = stable_digest(record)
        out.append(record)
    return out


def _has_token(tokens: Iterable[str], *needles: str) -> bool:
    return any(any(needle in token for needle in needles) for token in tokens)


def _hypothesis_profile(strategy: str, source_payload: Any) -> Dict[str, str]:
    """Map arbitrary source vocabulary onto four construction coordinates.

    The mapping is intentionally name-independent: it describes how a hidden
    surface could close, carry volume, continue layers, and attach.  It never
    turns a garment label into geometry and it never blends two sources.
    """
    all_tokens = set(_tokens({
        "strategy": strategy, "source_payload": source_payload,
    }))

    if _has_token(all_tokens, "center", "centre") and _has_token(
            all_tokens, "zip", "open", "fasten"):
        closure = "CENTER_BACK_OPENING"
    elif _has_token(all_tokens, "side") and _has_token(
            all_tokens, "zip", "open", "fasten"):
        closure = "SIDE_OPENING"
    elif (_has_token(all_tokens, "split", "center-join", "centre-join")
          or (_has_token(all_tokens, "center", "centre")
              and _has_token(all_tokens, "join"))):
        closure = "CENTER_BACK_JOIN"
    elif _has_token(all_tokens, "wrap", "overlap"):
        closure = "OVERLAPPED_WRAP_CLOSURE"
    else:
        closure = "CLOSED_OR_UNSEEN"

    if _has_token(all_tokens, "pleat", "gather", "controlled-fullness"):
        back_volume = "CONTROLLED_FULLNESS"
    elif _has_token(all_tokens, "flare", "bell", "wide"):
        back_volume = "FLARED_VOLUME"
    elif _has_token(all_tokens, "drape", "asym", "wrap"):
        back_volume = "ASYMMETRIC_DRAPED_VOLUME"
    elif _has_token(all_tokens, "ease", "loose", "volume", "relaxed"):
        back_volume = "EASED_VOLUME"
    else:
        back_volume = "FITTED_CONTINUATION"

    if _has_token(all_tokens, "terminate", "front-only"):
        layer_continuation = "TERMINATE_AT_SIDE_OR_ANCHOR"
    elif _has_token(all_tokens, "detached", "independent-layer"):
        layer_continuation = "INDEPENDENT_REAR_LAYER"
    elif _has_token(all_tokens, "asym", "cross-body", "wrap"):
        layer_continuation = "ASYMMETRIC_REAR_CONTINUATION"
    else:
        layer_continuation = "CONTINUE_EACH_VISIBLE_LAYER"

    if _has_token(all_tokens, "waist", "waistband"):
        attachment = "WAIST_ANCHORED"
    elif _has_token(all_tokens, "shoulder", "yoke"):
        attachment = "SHOULDER_OR_YOKE_ANCHORED"
    elif _has_token(all_tokens, "side-seam", "side seam"):
        attachment = "SIDE_SEAM_ANCHORED"
    elif _has_token(all_tokens, "detached", "independent"):
        attachment = "INDEPENDENT_COMPONENT"
    else:
        attachment = "MATCHING_BOUNDARY_SEAM"

    return {
        "closure": closure,
        "back_volume": back_volume,
        "layer_continuation": layer_continuation,
        "attachment_topology": attachment,
    }


def _typed_rear_hypothesis(
    *, strategy: str, source_payload: Any, provenance: Mapping[str, Any],
    basis: str,
) -> Dict[str, Any]:
    profile = _hypothesis_profile(strategy, source_payload)
    axes = {
        axis: _unobserved_record(
            profile[axis], basis=basis,
            breaks_when=(
                "rear/side evidence, a named human decision, or a failed "
                "candidate-specific 3D reconstruction contradicts this axis"
            ),
            provenance=provenance, field=axis,
        )
        for axis in HYPOTHESIS_AXES
    }
    result = {
        "schema": HYPOTHESIS_SCHEMA,
        "state": PROPOSED,
        "observation_state": UNKNOWN_UNOBSERVED,
        "strategy": strategy,
        "axes": axes,
        "axis_values": {axis: axes[axis]["value"]
                        for axis in HYPOTHESIS_AXES},
        "axes_are_independent": True,
        "conflicts_are_not_averaged": True,
        "front_mutation_allowed": False,
        "fact_promotions": [],
    }
    result["hypothesis_digest"] = stable_digest(result)
    return result


def _strategy(value: Any, fallback: str) -> str:
    words = set(_tokens(value))
    if any("center" in word or "centre" in word for word in words) and any(
            "open" in word or "zip" in word or "split" in word
            for word in words):
        return "CENTER_BACK_OPENING"
    if any("side" in word for word in words) and any(
            "open" in word or "zip" in word for word in words):
        return "CLOSED_BACK_SIDE_OPENING"
    if any("split" in word or "seam" in word for word in words):
        return "SPLIT_REAR_WITH_CENTER_JOIN"
    if any("layer" in word or "cape" in word or "overlay" in word
           for word in words):
        return "LAYERED_REAR_CONTINUATION"
    return fallback


def _hidden_geometry(
    visible: Mapping[str, Any], *, strategy: str,
    hypothesis: Mapping[str, Any], source_payload: Any,
    provenance: Mapping[str, Any], basis: str,
) -> Dict[str, Any]:
    axis_values = hypothesis["axis_values"]
    closure = str(axis_values["closure"])
    back_volume = str(axis_values["back_volume"])
    layer_continuation = str(axis_values["layer_continuation"])
    attachment_topology = str(axis_values["attachment_topology"])
    split = closure in {"CENTER_BACK_OPENING", "CENTER_BACK_JOIN"}
    rear_parts: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    for part in visible["parts"]:
        sides = ("left", "right") if split else ("whole",)
        rear_ids = []
        for side in sides:
            rear_id = f"rear-{part['part_id']}-{side}"
            rear_ids.append(rear_id)
            rear_parts.append(_unobserved_record(
                {
                    "rear_part_id": rear_id,
                    "continues_visible_part_id": part["part_id"],
                    "kind": part["kind"],
                    "side": side,
                    "layer": part["layer"],
                    "garment_unit": part["garment_unit"],
                    "back_volume": back_volume,
                    "layer_continuation": layer_continuation,
                    "attachment_topology": attachment_topology,
                    "geometry_operation": (
                        "split geodesic continuation from the visible boundary"
                        if split else
                        "continuous geodesic continuation from the visible boundary"
                    ),
                    "front_visible_vertices_mutated": False,
                },
                basis=basis,
                breaks_when="rear/side evidence or the 3D comparison rejects this surface",
                provenance=provenance, field="rear_part",
            ))
            relations.append(_unobserved_record(
                {
                    "kind": ("INDEPENDENT_ATTACHMENT" if
                             layer_continuation == "INDEPENDENT_REAR_LAYER"
                             else "CONTINUATION"),
                    "source": part["part_id"], "target": rear_id,
                    "garment_unit": part["garment_unit"],
                    "attachment_topology": attachment_topology,
                    "layer_continuation": layer_continuation,
                },
                basis=basis,
                breaks_when="a boundary, occlusion, or separate garment is confirmed",
                provenance=provenance, field="hidden_relation",
            ))
        if closure != "CLOSED_OR_UNSEEN":
            source = rear_ids[0]
            target = rear_ids[1] if len(rear_ids) > 1 else rear_ids[0]
            relations.append(_unobserved_record(
                {
                    "kind": ("PROPOSED_JOIN" if closure
                             == "CENTER_BACK_JOIN" else "PROPOSED_OPENING"),
                    "source": source, "target": target,
                    "garment_unit": part["garment_unit"],
                    "location": closure.lower().replace("_", "-"),
                    "closure": closure,
                },
                basis=basis,
                breaks_when="rear evidence or dressability review selects another closure",
                provenance=provenance, field="hidden_seam",
            ))
    payload = {
        "strategy": strategy,
        "rear_hypothesis_digest": hypothesis["hypothesis_digest"],
        "rear_hypothesis_axes": copy.deepcopy(axis_values),
        "rear_parts": rear_parts,
        "hidden_relations": relations,
        "source_proposal": _proposal_value(source_payload),
        "visible_graph_digest": visible["source_digest"],
        "garment_units": sorted({row["garment_unit"] for row in visible["parts"]}),
        "layers": sorted({row["layer"] for row in visible["parts"]}),
        "cross_garment_unit_joins_added": False,
        "garment_name_used_for_geometry": False,
        "generic_cape_fallback_used": False,
        "front_preservation": {
            "visible_graph_digest": visible["source_digest"],
            "visible_part_ids": sorted(row["part_id"] for row in visible["parts"]),
            "visible_front_is_immutable_across_rear_alternatives": True,
            "allowed_mutation_domain": "UNOBSERVED_REAR_ONLY",
        },
    }
    return _unobserved_record(
        payload, basis=basis,
        breaks_when="rear/side evidence, human 3D review, or manufacturability testing rejects it",
        provenance=provenance, field="rear_structure",
        preserve_typed_children=True,
    )


def _unknown_material(provenance: Mapping[str, Any], basis: str) -> Dict[str, Any]:
    return _unobserved_record(
        {"mechanics": "unknown", "candidate_ranges": {}},
        basis=basis,
        breaks_when="a swatch, material measurement, or approved motion comparison is supplied",
        provenance=provenance, field="material",
    )


def _candidate(
    visible: Mapping[str, Any], observed_aspects: Mapping[str, Any], *,
    strategy: str, source_payload: Any, supporting_sources: Sequence[Mapping[str, Any]],
    supporting_claims: Sequence[Mapping[str, Any]], origin: str,
) -> Dict[str, Any]:
    if supporting_sources:
        provenance = {
            "origin": origin,
            "engine": "photoloset.rear-candidate-ensemble.v1",
            "sources": [copy.deepcopy(row["provenance"])
                        for row in supporting_sources],
            "corpus_used": any(row["source_kind"]
                               == "FASHION_SIGLIP_RETRIEVAL"
                               for row in supporting_sources),
            "network_used_by_this_module": False,
        }
        source_label = ", ".join(
            f"{row['source_kind']}:{row['source_id']}"
            for row in supporting_sources)
        basis = (f"{source_label} proposed this unobserved rear; independent "
                 "claims remain inspectable and unmerged")
    else:
        provenance = {
            "origin": "DETERMINISTIC_GEOMETRY_ONLY_FALLBACK",
            "engine": "photoloset.rear-candidate-ensemble.v1",
            "sources": [], "corpus": None, "corpus_used": False,
            "network_used_by_this_module": False,
        }
        basis = ("deterministic continuation of each typed visible part around "
                 "its own garment unit; no corpus or class lookup")

    rear_hypothesis = _typed_rear_hypothesis(
        strategy=strategy, source_payload=source_payload,
        provenance=provenance, basis=basis,
    )
    rear = _hidden_geometry(
        visible, strategy=strategy, hypothesis=rear_hypothesis,
        source_payload=source_payload, provenance=provenance, basis=basis,
    )
    source_aspects = {
        aspect: [row["aspects"].get(aspect) for row in supporting_sources
                 if row["aspects"].get(aspect) not in (None, "", [], {})]
        for aspect in ASPECTS
    }
    if not source_aspects["structure"]:
        source_aspects["structure"] = rear["value"]
    if not source_aspects["parts"]:
        source_aspects["parts"] = [
            record["value"] for record in rear["value"]["rear_parts"]
        ]
    if not source_aspects["seams"]:
        source_aspects["seams"] = [
            record["value"] for record in rear["value"]["hidden_relations"]
        ]
    fit = _score_aspects(observed_aspects, source_aspects)

    material_claims = [
        copy.deepcopy(claim) for claim in supporting_claims
        if claim["field"] == "material"
    ]
    if not material_claims:
        material_claims = [_unknown_material(provenance, basis)]
    structure_signature = stable_digest({
        "strategy": strategy,
        "rear_hypothesis": rear_hypothesis,
        "rear_geometry": rear["value"],
    })
    candidate_id = "rear-candidate-" + structure_signature[:18]
    candidate: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "state": PROPOSED,
        "observation_state": UNKNOWN_UNOBSERVED,
        "observed": False,
        "origin": origin,
        "strategy": strategy,
        "structure_signature": structure_signature,
        "rear_hypothesis": rear_hypothesis,
        "rear_structure": rear,
        "material_hypotheses": material_claims,
        "supporting_claim_ids": sorted(
            claim["claim_id"] for claim in supporting_claims),
        "aspect_fit": fit,
        "basis": basis,
        "breaks_when": rear["breaks_when"],
        "provenance": provenance,
        "rank_only_not_authority": True,
        "front_preservation_contract": copy.deepcopy(
            rear["value"]["front_preservation"]),
        "candidate_specific_3d_required": True,
        "generic_fallback_used": False,
        "auto_approved": False,
        "human_approval_required": True,
        "downstream_use_contract": {
            "rear_scope": "REAR_HYPOTHESIS",
            "material_scope": "MATERIAL_HYPOTHESIS",
            "state": PROPOSED,
            "observation_state": UNKNOWN_UNOBSERVED,
            "scoped_human_consent_or_approval_required": True,
            "candidate_digest_bound_approval_required_for_sewing": True,
            "consent_does_not_promote_to_observed": True,
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    candidate["candidate_digest"] = stable_digest(candidate)
    return candidate


def _ranking_key(candidate: Mapping[str, Any]) -> Tuple[Any, ...]:
    fit = candidate["aspect_fit"]
    scores = fit["axis_scores"]
    numeric = [scores.get(axis) if scores.get(axis) is not None else -1.0
               for axis in ASPECTS]
    # Explicit source proposals sort before fallback only after the inspectable
    # axis vector.  No FashionSigLIP scalar selects the winner.
    source_priority = 0 if candidate["origin"] != "GEOMETRY_ONLY_FALLBACK" else 1
    return (
        -fit["matched_axis_count"], -fit["coverage_count"],
        *(-value for value in numeric), source_priority,
        candidate["candidate_id"],
    )


def _blocked_sewing_gate() -> Dict[str, Any]:
    return {
        "verdict": SHAPE_NOT_APPROVED,
        "allowed": False,
        "sewing_search_invoked": False,
        "why": "rear candidates are ranked proposals, not an approved construction",
        "how_to_close": (
            "a named human must approve one exact candidate_id and candidate_digest; "
            "only then may the existing sewing_search boundary be invoked"
        ),
        "required_approval_kind": "HUMAN_APPROVAL",
        "auto_approval": False,
    }


def proposal_use_gate(
    candidate: Mapping[str, Any], consent: Any, *, scope: str,
) -> Dict[str, Any]:
    """Gate a rear/material proposal for scoped review use.

    This does not replace :func:`sewing_search_gate`; even valid consent only
    permits the unobserved proposal to enter the requested review path.
    """
    if scope not in {"REAR_HYPOTHESIS", "MATERIAL_HYPOTHESIS"}:
        return {
            "verdict": "UNKNOWN_REAR_PROPOSAL_CONSENT_SCOPE",
            "allowed": False, "required_scopes": [
                "REAR_HYPOTHESIS", "MATERIAL_HYPOTHESIS"],
        }
    digest = candidate.get("candidate_digest")
    if not isinstance(digest, str) or not digest:
        return {
            "verdict": "UNKNOWN_REAR_PROPOSAL_DIGEST_REQUIRED",
            "allowed": False, "required_scope": scope,
        }
    checked = corpus_manifest.validate_provider_consent(
        consent, required_scope=scope, subject_digest=digest)
    if checked.get("verdict") != "ANSWER":
        return {**checked, "allowed": False,
                "candidate_digest": digest}
    return {
        "verdict": "PROPOSED", "allowed": True,
        "state": PROPOSED, "observation_state": UNKNOWN_UNOBSERVED,
        "candidate_digest": digest, "scope": scope,
        "consent": checked,
        "automatic_observed_promotion": False,
        "sewing_search_allowed": False,
    }


def _provider_status_record(
    provider_id: str, capability: str, source_kind: str,
    sources: Sequence[Mapping[str, Any]], raw: Any, *, consent_scope: str,
    allow_llm_proposal: bool = True,
    require_commercial: bool = False,
) -> Dict[str, Any]:
    available = any(row.get("source_kind") == source_kind for row in sources)
    supplied_rows = _rows(raw, (
        "matches", "hits", "nearest_items", "items", "proposals",
        "rear_candidates", "candidates", "instances", "rules", "evidence",
        "audits", "decisions",
    ))
    rights_refused = 0
    rights_unknown = 0
    if source_kind == "FASHION_SIGLIP_RETRIEVAL":
        for row in supplied_rows:
            upstream = row.get("commercial_rights_gate")
            upstream_blocked = (
                isinstance(upstream, Mapping)
                and upstream.get("required") is True
                and upstream.get("allowed") is not True
            )
            rights = corpus_manifest.commercial_rights_status(
                row, require_commercial=True)
            if upstream_blocked or (
                    require_commercial and not rights["allowed"]):
                if rights["state"] == "DENIED":
                    rights_refused += 1
                else:
                    rights_unknown += 1
    rights_blocked = rights_refused + rights_unknown
    health = ("READY" if available else
              "RIGHTS_REFUSED" if rights_blocked else "UNAVAILABLE")
    reason = ("" if available else
              "no supplied retrieval asset carries usable commercial rights"
              if rights_blocked else "no provider proposals were supplied")
    # In strict mode, availability above can only be true after at least one
    # source row passed an explicit rights record.  This is a typed summary of
    # that completed gate, not a new asset licence claim.
    rights_summary = ({
        "rights_review": {
            "commercial_use": "allowed",
            "basis": "accepted source row passed explicit commercial-rights gate",
        },
    } if require_commercial and available else None)
    boundary = corpus_manifest.provider_capability(
        provider_id, capability, health=health, available=available,
        reason=reason, consent_scope=consent_scope,
        allow_llm_proposal=allow_llm_proposal,
        require_commercial=require_commercial, rights=rights_summary,
        details={"supplied_rows": len(supplied_rows),
                 "rights_refused_rows": rights_refused,
                 "rights_unknown_rows": rights_unknown},
    )
    return {
        "available": available,
        "supplied": bool(supplied_rows),
        "rights_refused_rows": rights_refused,
        "rights_unknown_rows": rights_unknown,
        "provider_boundary": boundary,
        "provider_result": corpus_manifest.provider_result(
            boundary, failure=({"verdict": "UNKNOWN_PROVIDER_UNAVAILABLE",
                                "why": reason} if not available else None),
            source_origin=("FRONT_IMAGE_RETRIEVAL_QUERY"
                           if source_kind == "FASHION_SIGLIP_RETRIEVAL"
                           else "FRONT_IMAGE_DERIVED_PROPOSAL")),
        "resolution_options": boundary["resolution_options"],
    }


def sewing_search_gate(
    ensemble_result: Mapping[str, Any], approval: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate authority without importing or invoking ``sewing_search``."""
    blocked = _blocked_sewing_gate()
    if not isinstance(approval, Mapping):
        return blocked
    if approval.get("kind") != "HUMAN_APPROVAL" or not _text(
            approval.get("approver")):
        return blocked
    candidates = {
        row.get("candidate_id"): row
        for row in ensemble_result.get("candidates", [])
        if isinstance(row, Mapping)
    }
    candidate = candidates.get(approval.get("candidate_id"))
    if candidate is None:
        return {**blocked, "verdict": APPROVAL_STALE,
                "why": "the approved candidate is not in this ensemble result"}
    if approval.get("candidate_digest") != candidate.get("candidate_digest"):
        return {**blocked, "verdict": APPROVAL_STALE,
                "why": "the approved candidate digest is stale or mismatched"}
    return {
        "verdict": "APPROVED",
        "allowed": True,
        "sewing_search_invoked": False,
        "approval": {
            "kind": "HUMAN_APPROVAL",
            "approver": _text(approval.get("approver")),
            "candidate_id": candidate["candidate_id"],
            "candidate_digest": candidate["candidate_digest"],
        },
        "next": "invoke the existing digest-bound sewing_search boundary",
        "automatic_invocation": False,
    }


def _unknown(request: Any, code: str, why: str) -> Dict[str, Any]:
    result = {
        "schema": SCHEMA,
        "verdict": code,
        "state": UNKNOWN_UNOBSERVED,
        "typed_stop": True,
        "why": why,
        "candidates": [],
        "selected_candidate_id": None,
        "auto_approved": False,
        "sewing_search_gate": _blocked_sewing_gate(),
        "manufacturing_ready": False,
        "fact_promotions": [],
    }
    try:
        result["input_digest"] = stable_digest(request)
        result["digest"] = stable_digest(result)
    except (TypeError, ValueError, OverflowError):
        pass
    return result


def generate_rear_candidates(
    request_or_graph: Mapping[str, Any], *, fashion_siglip_hits: Any = None,
    multimodal_proposals: Any = None, geometric_rule_evidence: Any = None,
    user_audit_evidence: Any = None,
) -> Dict[str, Any]:
    """Generate ranked, unapproved rear candidates from independent sources.

    ``request_or_graph`` can be a request envelope containing
    ``visible_part_graph`` or the visible graph itself.  Optional source values
    may likewise be passed as keyword arguments or embedded under their
    FashionSigLIP, multimodal, geometric-rule, and user-audit request fields.
    """
    if not isinstance(request_or_graph, Mapping):
        return _unknown(
            request_or_graph, "UNKNOWN_REAR_CANDIDATE_INPUT",
            "request or visible part graph must be an object",
        )
    request = dict(request_or_graph)
    require_commercial = bool(request.get(
        "require_commercial_rights", request.get("require_commercial", False)))
    raw_provider_states = request.get("provider_states", {})
    provider_states = (copy.deepcopy(dict(raw_provider_states))
                       if isinstance(raw_provider_states, Mapping) else {})
    if "visible_part_graph" in request:
        if request.get("schema") not in (None, REQUEST_SCHEMA):
            return _unknown(
                request, "UNKNOWN_REAR_CANDIDATE_SCHEMA",
                f"schema must be exactly {REQUEST_SCHEMA}",
            )
        graph = request.get("visible_part_graph")
        if fashion_siglip_hits is None:
            fashion_siglip_hits = request.get(
                "fashion_siglip_hits", request.get("retrieval_hits"))
        if multimodal_proposals is None:
            multimodal_proposals = request.get(
                "multimodal_proposals", request.get("model_proposals"))
        if geometric_rule_evidence is None:
            geometric_rule_evidence = request.get(
                "geometric_rule_evidence", request.get("geometric_evidence"))
        if user_audit_evidence is None:
            user_audit_evidence = request.get(
                "user_audit_evidence", request.get("human_audit_evidence"))
    else:
        graph = request
    if not isinstance(graph, Mapping):
        return _unknown(
            request, "UNKNOWN_VISIBLE_PART_GRAPH_REQUIRED",
            "visible_part_graph must be an object",
        )
    try:
        visible = _normalise_visible_graph(graph)
        if not visible["parts"]:
            return _unknown(
                request, "UNKNOWN_VISIBLE_PART_GRAPH_REQUIRED",
                "at least one typed visible part is required",
            )
        observed_aspects = _visible_aspects(visible)
        sources = _normalise_sources(
            fashion_siglip_hits, multimodal_proposals,
            geometric_rule_evidence, user_audit_evidence,
            require_commercial=require_commercial)
        claims = _source_claims(sources)
        claims_by_source: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for claim in claims:
            key = (claim["provenance"]["source_kind"],
                   claim["provenance"]["source_id"])
            claims_by_source[key].append(claim)

        structural: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
        payloads: Dict[str, Any] = {}
        for source in sources:
            payload = {
                field: source["aspects"].get(field)
                for field in ("structure", "parts", "seams") + HYPOTHESIS_AXES
                if source["aspects"].get(field) not in (None, "", [], {})
            }
            if not payload:
                continue
            signature = stable_digest(_proposal_value(payload))
            structural[signature].append(source)
            payloads[signature] = payload

        candidates: List[Dict[str, Any]] = []
        for signature in sorted(structural):
            support = structural[signature]
            source_claim_rows = [
                claim
                for source in support
                for claim in claims_by_source[(source["source_kind"],
                                               source["source_id"])]
            ]
            kinds = {row["source_kind"] for row in support}
            origin = ("FUSED_RETRIEVAL_MULTIMODAL_PROPOSAL"
                      if len(kinds) > 1 else next(iter(kinds)))
            strategy = _strategy(payloads[signature], "SOURCE_REAR_PROPOSAL")
            candidates.append(_candidate(
                visible, observed_aspects, strategy=strategy,
                source_payload=payloads[signature],
                supporting_sources=support,
                supporting_claims=source_claim_rows, origin=origin,
            ))

        # These two alternatives are geometry-derived and class-independent.
        # They remain present even when retrieval/model sources are available,
        # so absence of a corpus never closes the workflow.
        for strategy in (
            "CONTINUOUS_REAR_SURFACE",
            "SPLIT_REAR_WITH_CENTER_JOIN",
        ):
            fallback_payload = ({
                "strategy": strategy,
                "closure": "CLOSED_OR_UNSEEN",
                "back_volume": "FITTED_CONTINUATION",
                "layer_continuation": "CONTINUE_EACH_VISIBLE_LAYER",
                "attachment_topology": "MATCHING_BOUNDARY_SEAM",
            } if strategy == "CONTINUOUS_REAR_SURFACE" else {
                "strategy": strategy,
                "closure": "CENTER_BACK_JOIN",
                "back_volume": "EASED_VOLUME",
                "layer_continuation": "CONTINUE_EACH_VISIBLE_LAYER",
                "attachment_topology": "MATCHING_BOUNDARY_SEAM",
            })
            candidates.append(_candidate(
                visible, observed_aspects, strategy=strategy,
                source_payload=fallback_payload,
                supporting_sources=[], supporting_claims=[],
                origin="GEOMETRY_ONLY_FALLBACK",
            ))

        # Dedupe exact structures while preserving independently normalized
        # claims in source_claims and contested.
        distinct: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            distinct.setdefault(candidate["structure_signature"], candidate)
        candidates = sorted(distinct.values(), key=_ranking_key)
        for rank, candidate in enumerate(candidates, 1):
            candidate["rank"] = rank
            candidate["ranking_vector"] = {
                "matched_axis_count": candidate["aspect_fit"]["matched_axis_count"],
                "coverage_count": candidate["aspect_fit"]["coverage_count"],
                "axis_scores": copy.deepcopy(
                    candidate["aspect_fit"]["axis_scores"]),
                "source_score_used": False,
            }
            candidate["candidate_digest"] = stable_digest({
                key: value for key, value in candidate.items()
                if key != "candidate_digest"
            })

        fashion_status = _provider_status_record(
            "fashion-siglip", "FASHION_SIMILARITY_RETRIEVAL",
            "FASHION_SIGLIP_RETRIEVAL", sources, fashion_siglip_hits,
            consent_scope="RETRIEVAL_HYPOTHESIS",
            require_commercial=require_commercial)
        multimodal_status = _provider_status_record(
            "multimodal-rear", "MULTIMODAL_REAR_HYPOTHESIS",
            "MULTIMODAL_MODEL_PROPOSAL", sources, multimodal_proposals,
            consent_scope="REAR_HYPOTHESIS")
        geometric_status = _provider_status_record(
            "geometric-rear-rules", "GEOMETRIC_REAR_EVIDENCE",
            "GEOMETRIC_RULE_EVIDENCE", sources, geometric_rule_evidence,
            consent_scope="REAR_HYPOTHESIS", allow_llm_proposal=False)
        user_status = _provider_status_record(
            "named-user-audit", "NAMED_USER_AUDIT_EVIDENCE",
            "USER_AUDIT_EVIDENCE", sources, user_audit_evidence,
            consent_scope="REAR_HYPOTHESIS", allow_llm_proposal=False)
        material_available = any(
            row.get("field") == "material" for row in claims)
        material_boundary = corpus_manifest.provider_capability(
            "material-hypothesis-ensemble", "MATERIAL_HYPOTHESIS",
            health="READY" if material_available else "UNAVAILABLE",
            available=material_available,
            reason="" if material_available else
            "no material evidence or proposal source is connected",
            consent_scope="MATERIAL_HYPOTHESIS",
            details={"material_claim_count": sum(
                1 for row in claims if row.get("field") == "material")},
        )
        material_status = {
            "available": material_available,
            "provider_boundary": material_boundary,
            "provider_result": corpus_manifest.provider_result(
                material_boundary,
                source_origin="FRONT_IMAGE_VISIBLE_MATERIAL_CUE"),
            "resolution_options": material_boundary["resolution_options"],
        }
        deterministic_boundary = corpus_manifest.provider_capability(
            "deterministic-rear-geometry", "REAR_GEOMETRY_ALTERNATIVES",
            health="READY", available=True,
            consent_scope="REAR_HYPOTHESIS", allow_llm_proposal=False,
            details={"candidate_count": len(candidates)},
        )

        # Connected physical/search capabilities are reported independently
        # from front-image proposals.  In particular, visible material cues do
        # not make a material-measurement provider available, and a similarity
        # hit is a rear reference only when it actually carries rear structure.
        rear_reference_available = any(
            row.get("source_kind") == "FASHION_SIGLIP_RETRIEVAL"
            and any(row.get("aspects", {}).get(axis) not in (
                None, "", [], {}) for axis in ("structure", "parts", "seams"))
            for row in sources
        )
        provider_states.setdefault("FASHION_SIMILARITY_RETRIEVAL", {
            "provider_id": "fashion-siglip",
            "available": fashion_status["available"],
            "health": fashion_status["provider_boundary"]["health"],
            "source_origin": "FRONT_IMAGE_RETRIEVAL_QUERY",
            **({"rights_review": {"commercial_use": "allowed"}}
               if require_commercial and fashion_status["available"] else {}),
        })
        provider_states.setdefault("REAR_REFERENCE_RETRIEVAL", {
            "provider_id": "rear-reference-retrieval",
            "available": rear_reference_available,
            "health": "READY" if rear_reference_available else "UNAVAILABLE",
            "source_origin": "FRONT_IMAGE_TO_REAR_REFERENCE_RETRIEVAL",
            "reason": ("a rights-gated reference supplied rear structure"
                       if rear_reference_available else
                       "no connected reference supplied rear structure"),
            **({"rights_review": {"commercial_use": "allowed"}}
               if require_commercial and rear_reference_available else {}),
        })
        provider_states.setdefault("MULTIMODAL_REAR_HYPOTHESIS", {
            "provider_id": "multimodal-rear",
            "available": multimodal_status["available"],
            "health": multimodal_status["provider_boundary"]["health"],
            "source_origin": "FRONT_IMAGE_MULTIMODAL_ANALYSIS",
        })
        provider_states.setdefault("MATERIAL_HYPOTHESIS", {
            "provider_id": "material-hypothesis-ensemble",
            "available": material_available,
            "health": "READY" if material_available else "UNAVAILABLE",
            "source_origin": "FRONT_IMAGE_VISIBLE_MATERIAL_CUE",
        })
        provider_report = corpus_manifest.provider_capability_report(
            provider_states, require_commercial=require_commercial)

        def reported_status(capability_name: str) -> Dict[str, Any]:
            row = copy.deepcopy(
                provider_report["capabilities"][capability_name])
            row["available"] = row["provider_boundary"]["available"]
            row["resolution_options"] = row[
                "provider_boundary"]["resolution_options"]
            return row

        provider_status = {
            "fashion_siglip": fashion_status,
            "rear_reference_retrieval": reported_status(
                "REAR_REFERENCE_RETRIEVAL"),
            "multimodal": multimodal_status,
            "geometric_rules": geometric_status,
            "user_audit": user_status,
            "material": material_status,
            "material_property_measurement": reported_status(
                "MATERIAL_PROPERTY_MEASUREMENT"),
            "material_property_calibration": reported_status(
                "MATERIAL_PROPERTY_CALIBRATION"),
            "body_measurement": reported_status("BODY_MEASUREMENT"),
            "wind_tunnel_validation": reported_status(
                "WIND_TUNNEL_VALIDATION"),
            "seam_strength_test": reported_status("SEAM_STRENGTH_TEST"),
            "deterministic_rear_geometry": {
                "available": True,
                "provider_boundary": deterministic_boundary,
                "provider_result": corpus_manifest.provider_result(
                    deterministic_boundary),
                "resolution_options": [],
            },
            "mode": ("FUSED_PROPOSAL_ENSEMBLE" if sources
                     else "DETERMINISTIC_GEOMETRY_ONLY"),
        }
        resolution_options = [
            option
            for key, row in provider_status.items()
            if key != "mode" and isinstance(row, Mapping)
            for option in row.get("resolution_options", [])
        ]

        result: Dict[str, Any] = {
            "schema": SCHEMA,
            "verdict": PROPOSED,
            "state": "PROPOSED_HUMAN_REVIEW_REQUIRED",
            "typed_stop": False,
            "visible_part_graph": visible,
            "visible_part_graph_digest": visible["source_digest"],
            "source_claims": claims,
            "contested": _contested(claims),
            "candidates": candidates,
            "candidate_count": len(candidates),
            "selected_candidate_id": None,
            "auto_approved": False,
            "ranking": {
                "method": "LEXICOGRAPHIC_MULTI_ASPECT_REVIEW_ORDER",
                "aspects": list(ASPECTS),
                "single_embedding_winner": False,
                "fashion_siglip_score_is_not_construction_authority": True,
                "rank_is_not_approval": True,
            },
            "provider_status": provider_status,
            "provider_capability_report": provider_report,
            "resolution_options": resolution_options,
            "authority": {
                "rear": PROPOSED,
                "hidden": PROPOSED,
                "material": PROPOSED,
                "observation_state": UNKNOWN_UNOBSERVED,
                "automatic_observed_promotion": False,
                "automatic_candidate_approval": False,
                "garment_name_used_as_geometry_enum": False,
            },
            "sewing_search_before_human_approval": False,
            "sewing_search_gate": _blocked_sewing_gate(),
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "fact_promotions": [],
        }
        result["digest"] = stable_digest(result)
        return result
    except (TypeError, ValueError, OverflowError) as exc:
        return _unknown(
            request, "UNKNOWN_REAR_CANDIDATE_INPUT", str(exc))


# Conventional aliases used by the repository's small pipeline modules.
propose = generate_rear_candidates
generate = generate_rear_candidates
assemble = generate_rear_candidates
authorize_sewing_search = sewing_search_gate


__all__ = [
    "REQUEST_SCHEMA", "SCHEMA", "HYPOTHESIS_SCHEMA", "HYPOTHESIS_AXES",
    "PROPOSED", "UNKNOWN_UNOBSERVED",
    "CONTESTED", "SHAPE_NOT_APPROVED", "APPROVAL_STALE", "ASPECTS",
    "stable_digest", "generate_rear_candidates", "propose", "generate",
    "assemble", "proposal_use_gate", "sewing_search_gate",
    "authorize_sewing_search",
]
