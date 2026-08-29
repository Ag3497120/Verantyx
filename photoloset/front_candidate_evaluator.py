# -*- coding: utf-8 -*-
"""Deterministic, multi-axis evaluation of front-only garment candidates.

The evaluator deliberately does not produce a weighted or aggregate score.
Each candidate is checked on seven independently reported axes and candidates
are compared only by Pareto dominance over the typed axis dispositions.

A successful geometric check is not evidence for an unseen back, material,
fit, or manufacturing process.  Rear and material authority therefore remain
``PROPOSED`` and every surviving front-only candidate still requires review.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from . import garment_structure
from . import structure_preview
from . import structure_to_pattern


SCHEMA = "garment.front-candidate-evaluation.v1"
PROPOSED = "PROPOSED"
ANSWER = "ANSWER"

AXES = (
    "front_silhouette_consistency",
    "layer_order_consistency",
    "topology_validity",
    "closure_donning_plausibility",
    "pattern_lowerability",
    "candidate_specific_3d_availability",
    "evidence_authority",
)


class Disposition(str, Enum):
    """Ordinal values used only for Pareto comparison, never aggregation."""

    UNSATISFIED = "UNSATISFIED"
    REVIEW = "REVIEW"
    SATISFIED = "SATISFIED"


_PARETO_ORDER = {
    Disposition.UNSATISFIED.value: 0,
    Disposition.REVIEW.value: 1,
    Disposition.SATISFIED.value: 2,
}


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _axis(disposition: Disposition, verdict: str, why: str,
          **observations: Any) -> Dict[str, Any]:
    result = {
        "disposition": disposition.value,
        "verdict": verdict,
        "why": why,
    }
    if observations:
        result["observations"] = copy.deepcopy(observations)
    return result


def _candidate_id(candidate: Mapping[str, Any]) -> Optional[str]:
    value = candidate.get("candidate_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _structure(candidate: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    nested = candidate.get("structure")
    if isinstance(nested, Mapping):
        return copy.deepcopy(dict(nested))
    if (candidate.get("schema") == garment_structure.SCHEMA
            and isinstance(candidate.get("nodes"), Sequence)
            and isinstance(candidate.get("operations"), Sequence)):
        return {
            "schema": candidate["schema"],
            "nodes": copy.deepcopy(candidate["nodes"]),
            "operations": copy.deepcopy(candidate["operations"]),
        }
    return None


def _cue(candidate: Mapping[str, Any], front_evidence: Mapping[str, Any],
         name: str) -> Optional[Mapping[str, Any]]:
    sources: List[Any] = [candidate.get("front_cues")]
    typed = front_evidence.get("typed_cues")
    if isinstance(typed, Mapping):
        sources.append(typed)
    sources.append(front_evidence)
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        value = source.get(name)
        if isinstance(value, Mapping):
            return value
    return None


def _nodes(structure: Optional[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    if not isinstance(structure, Mapping):
        return []
    values = structure.get("nodes", [])
    if (not isinstance(values, Sequence)
            or isinstance(values, (str, bytes))):
        return []
    return [row for row in values if isinstance(row, Mapping)]


def _operations(structure: Optional[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    if not isinstance(structure, Mapping):
        return []
    values = structure.get("operations", [])
    if (not isinstance(values, Sequence)
            or isinstance(values, (str, bytes))):
        return []
    return [row for row in values if isinstance(row, Mapping)]


def _front_silhouette_axis(candidate: Mapping[str, Any],
                           structure: Optional[Mapping[str, Any]],
                           front_evidence: Mapping[str, Any]) -> Dict[str, Any]:
    cue = _cue(candidate, front_evidence, "silhouette")
    expected = cue.get("value") if isinstance(cue, Mapping) else None
    cue_state = str(cue.get("state", PROPOSED)).upper() if cue else None
    declared: Set[str] = set()
    for node in _nodes(structure):
        attributes = node.get("attributes", {})
        if not isinstance(attributes, Mapping):
            continue
        value = attributes.get("front_silhouette")
        if isinstance(value, str) and value.strip():
            declared.add(value.strip())
    if not isinstance(expected, str) or not expected.strip():
        return _axis(
            Disposition.REVIEW,
            "REVIEW_FRONT_SILHOUETTE_EVIDENCE_REQUIRED",
            "no typed front-silhouette cue is bound to this comparison",
            declared=sorted(declared),
        )
    if not declared:
        return _axis(
            Disposition.REVIEW,
            "REVIEW_FRONT_SILHOUETTE_BINDING_REQUIRED",
            "the structure does not declare which typed front silhouette it preserves",
            expected=expected, cue_state=cue_state,
        )
    if declared != {expected}:
        disposition = (Disposition.UNSATISFIED
                       if cue_state == "OBSERVED" else Disposition.REVIEW)
        verdict = ("UNKNOWN_FRONT_SILHOUETTE_CONFLICT"
                   if disposition is Disposition.UNSATISFIED
                   else "REVIEW_PROPOSED_FRONT_SILHOUETTE_CONFLICT")
        return _axis(
            disposition, verdict,
            "the candidate structure does not preserve the typed front silhouette",
            expected=expected, declared=sorted(declared), cue_state=cue_state,
        )
    return _axis(
        Disposition.SATISFIED,
        "ANSWER_FRONT_SILHOUETTE_CONSISTENT",
        "the structure explicitly preserves the typed front-silhouette cue",
        expected=expected, declared=sorted(declared), cue_state=cue_state,
    )


def _has_cycle(edges: Iterable[Tuple[str, str]]) -> bool:
    graph: Dict[str, Set[str]] = {}
    for source, target in edges:
        graph.setdefault(source, set()).add(target)
        graph.setdefault(target, set())
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in sorted(graph.get(node, set()))):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in sorted(graph))


def _layer_axis(candidate: Mapping[str, Any],
                structure: Optional[Mapping[str, Any]],
                front_evidence: Mapping[str, Any]) -> Dict[str, Any]:
    nodes = _nodes(structure)
    node_layers: Dict[str, int] = {}
    malformed: List[str] = []
    for node in nodes:
        node_id = node.get("node_id")
        layer = node.get("layer", 0)
        if (not isinstance(node_id, str) or not node_id
                or isinstance(layer, bool) or not isinstance(layer, int)
                or layer < 0):
            malformed.append(str(node_id))
            continue
        node_layers[node_id] = layer
    relations: List[Tuple[str, str]] = []
    order_conflicts: List[str] = []
    visible_layers: Set[int] = {0} if nodes else set()
    for operation in _operations(structure):
        if operation.get("kind") != "LAYER":
            continue
        source = operation.get("source", {})
        target = operation.get("target", {})
        source_id = source.get("node_id") if isinstance(source, Mapping) else None
        target_id = target.get("node_id") if isinstance(target, Mapping) else None
        operation_id = str(operation.get("operation_id", ""))
        if source_id not in node_layers or target_id not in node_layers:
            order_conflicts.append(operation_id or "unnamed-layer-operation")
            continue
        relations.append((str(source_id), str(target_id)))
        visible_layers.add(node_layers[str(source_id)])
        visible_layers.add(node_layers[str(target_id)])
        if node_layers[str(source_id)] <= node_layers[str(target_id)]:
            order_conflicts.append(operation_id or "unnamed-layer-operation")
    if malformed or order_conflicts or _has_cycle(relations):
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_LAYER_ORDER_INVALID",
            "layer relations must address nodes, move from a higher layer to a lower layer, and remain acyclic",
            malformed_nodes=sorted(malformed),
            order_conflicts=sorted(order_conflicts),
            cyclic=_has_cycle(relations),
        )

    cue = _cue(candidate, front_evidence, "layer_count")
    expected = cue.get("value") if isinstance(cue, Mapping) else None
    cue_state = str(cue.get("state", PROPOSED)).upper() if cue else None
    actual = len(visible_layers) if visible_layers else 0
    if isinstance(expected, bool) or not isinstance(expected, int):
        return _axis(
            Disposition.REVIEW,
            "REVIEW_FRONT_LAYER_EVIDENCE_REQUIRED",
            "no typed visible-layer count is bound to this comparison",
            structural_layer_count=actual,
            layer_relations=[list(row) for row in relations],
        )
    if expected != actual:
        disposition = (Disposition.UNSATISFIED
                       if cue_state == "OBSERVED" else Disposition.REVIEW)
        verdict = ("UNKNOWN_FRONT_LAYER_COUNT_CONFLICT"
                   if disposition is Disposition.UNSATISFIED
                   else "REVIEW_PROPOSED_LAYER_COUNT_CONFLICT")
        return _axis(
            disposition, verdict,
            "the candidate's explicit layer graph differs from the typed visible-layer count",
            expected=expected, structural_layer_count=actual,
            cue_state=cue_state, layer_relations=[list(row) for row in relations],
        )
    return _axis(
        Disposition.SATISFIED,
        "ANSWER_LAYER_ORDER_CONSISTENT",
        "the explicit acyclic layer graph preserves the typed visible-layer count",
        expected=expected, structural_layer_count=actual,
        cue_state=cue_state, layer_relations=[list(row) for row in relations],
    )


def _topology_axis(structure: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if structure is None:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_CANDIDATE_STRUCTURE_REQUIRED",
            "candidate has no garment.structure.v1 payload",
        )
    result = garment_structure.validate(structure)
    if result.get("verdict") != ANSWER:
        return _axis(
            Disposition.UNSATISFIED,
            str(result.get("verdict", "UNKNOWN_STRUCTURE_TOPOLOGY")),
            str(result.get("why", "structure topology did not validate")),
        )
    return _axis(
        Disposition.SATISFIED,
        "ANSWER_TOPOLOGY_VALID",
        "ports, joins, gathers, operation dependencies, and layer references validate deterministically",
        structure_digest=result.get("digest"), checks=result.get("checks", []),
    )


def _back_proposal(candidate: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    back = candidate.get("back_alternative")
    if isinstance(back, Mapping):
        value = back.get("value", {})
        closure = value.get("closure") if isinstance(value, Mapping) else None
        alternative = back.get("alternative_id")
        return (str(alternative) if isinstance(alternative, str) else None,
                str(closure) if isinstance(closure, str) else None)
    alternative = candidate.get("back_design")
    if isinstance(alternative, str):
        closures = {
            "center_back_opening": "center_back_opening",
            "side_opening_closed_back": "side_opening",
            "closed_back_stretch": "pull_on_stretch",
        }
        return alternative, closures.get(alternative)
    return None, None


def _closure_axis(candidate: Mapping[str, Any],
                  structure: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    alternative, closure = _back_proposal(candidate)
    opening_nodes = [node for node in _nodes(structure)
                     if node.get("kind") == "OPENING"]
    placements = sorted({
        str(attributes.get("placement"))
        for node in opening_nodes
        for attributes in [node.get("attributes", {})]
        if isinstance(attributes, Mapping)
        and isinstance(attributes.get("placement"), str)
    })
    if closure is None:
        return _axis(
            Disposition.REVIEW,
            "REVIEW_CLOSURE_TOPOLOGY_REQUIRED",
            "a front view does not establish an opening or pull-on construction",
            back_alternative=alternative, opening_placements=placements,
        )
    if closure == "pull_on_stretch":
        if opening_nodes:
            return _axis(
                Disposition.UNSATISFIED,
                "UNKNOWN_PULL_ON_OPENING_CONFLICT",
                "the pull-on alternative conflicts with an explicit opening node",
                back_alternative=alternative, opening_placements=placements,
            )
        return _axis(
            Disposition.REVIEW,
            "REVIEW_PULL_ON_STRETCH_AND_CLEARANCE_REQUIRED",
            "pull-on dressability requires proposed material stretch and wearer clearance to be tested",
            back_alternative=alternative,
            rear_authority=PROPOSED, material_authority=PROPOSED,
        )
    if closure not in {"center_back_opening", "side_opening"}:
        return _axis(
            Disposition.REVIEW,
            "REVIEW_UNSUPPORTED_CLOSURE_PROPOSAL",
            "the closure proposal needs a typed construction and donning check",
            back_alternative=alternative, closure=closure,
            opening_placements=placements,
        )
    if closure not in placements:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_CLOSURE_STRUCTURE_MISMATCH",
            "the named back alternative is not represented by a matching OPENING node",
            back_alternative=alternative, closure=closure,
            opening_placements=placements,
        )
    return _axis(
        Disposition.REVIEW,
        "REVIEW_DONNING_CLEARANCE_REQUIRED",
        "the proposed opening is structurally represented, but unseen rear construction and wearer clearance are unvalidated",
        back_alternative=alternative, closure=closure,
        opening_placements=placements, rear_authority=PROPOSED,
    )


def _artifact_for(artifacts: Optional[Mapping[str, Mapping[str, Any]]],
                  candidate_id: str) -> Optional[Mapping[str, Any]]:
    if not isinstance(artifacts, Mapping):
        return None
    value = artifacts.get(candidate_id)
    return value if isinstance(value, Mapping) else None


def _pattern_axis(candidate_id: str, structure: Optional[Mapping[str, Any]],
                  patterns: Optional[Mapping[str, Mapping[str, Any]]]) -> Dict[str, Any]:
    supplied = _artifact_for(patterns, candidate_id)
    if supplied is not None:
        result = copy.deepcopy(dict(supplied))
        origin = "supplied"
    elif structure is not None:
        try:
            result = structure_to_pattern.compile(
                structure, candidate_state=PROPOSED, candidate_id=candidate_id)
        except Exception as exc:  # fail closed at the candidate boundary
            return _axis(
                Disposition.UNSATISFIED,
                "UNKNOWN_PATTERN_LOWERING_EXCEPTION",
                "the deterministic pattern compiler raised an exception",
                exception_type=type(exc).__name__,
            )
        origin = "generated"
    else:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_PATTERN_STRUCTURE_REQUIRED",
            "pattern lowering requires a candidate structure",
        )
    verdict = str(result.get("verdict", "UNKNOWN_PATTERN_LOWERING"))
    if result.get("manufacturing_ready") is True or result.get("manufacturing_certified") is True:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_MANUFACTURING_AUTHORITY_ESCALATION",
            "a front-only candidate artifact may not claim manufacturing readiness or certification",
            artifact_origin=origin,
        )
    if verdict != ANSWER:
        disposition = (Disposition.REVIEW if verdict.startswith("REVIEW_")
                       else Disposition.UNSATISFIED)
        return _axis(
            disposition, verdict,
            str(result.get("why", "candidate did not lower into a typed geometric pattern")),
            artifact_origin=origin,
        )
    if result.get("candidate_id") not in (None, "", candidate_id):
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_PATTERN_CANDIDATE_ID_MISMATCH",
            "the pattern artifact belongs to another candidate",
            artifact_candidate_id=result.get("candidate_id"),
        )
    pieces = result.get("pieces")
    usable = (isinstance(pieces, Sequence)
              and not isinstance(pieces, (str, bytes)) and bool(pieces)
              and all(isinstance(piece, Mapping)
                      and bool(piece.get("outline")) and bool(piece.get("edges"))
                      for piece in pieces))
    if not usable or result.get("cuttable_geometric_prototype") is not True:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_PATTERN_GEOMETRY_INCOMPLETE",
            "lowering returned no complete cuttable geometric prototype",
            artifact_origin=origin,
        )
    return _axis(
        Disposition.SATISFIED,
        "ANSWER_PATTERN_LOWERABLE",
        "the candidate deterministically lowers to addressed sewing-line polygons",
        artifact_origin=origin, piece_count=len(pieces),
        candidate_state=result.get("candidate_state"),
        cuttable_geometric_prototype=True,
        manufacturing_ready=False, manufacturing_certified=False,
        remaining_gates=copy.deepcopy(result.get("remaining_gates", [])),
    )


def _preview_axis(candidate_id: str, structure: Optional[Mapping[str, Any]],
                  previews: Optional[Mapping[str, Mapping[str, Any]]]) -> Dict[str, Any]:
    supplied = _artifact_for(previews, candidate_id)
    if supplied is not None:
        result = copy.deepcopy(dict(supplied))
        origin = "supplied"
    elif structure is not None:
        try:
            result = structure_preview.generate_preview(
                structure, candidate_id=candidate_id)
        except Exception as exc:  # fail closed at the candidate boundary
            return _axis(
                Disposition.UNSATISFIED,
                "UNKNOWN_CANDIDATE_3D_EXCEPTION",
                "the deterministic candidate preview raised an exception",
                exception_type=type(exc).__name__,
            )
        origin = "generated"
    else:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_CANDIDATE_3D_STRUCTURE_REQUIRED",
            "candidate-specific 3D requires a candidate structure",
        )
    verdict = str(result.get("verdict", "UNKNOWN_CANDIDATE_3D"))
    if verdict != ANSWER:
        disposition = (Disposition.REVIEW if verdict.startswith("REVIEW_")
                       else Disposition.UNSATISFIED)
        return _axis(
            disposition, verdict,
            str(result.get("why", "candidate-specific 3D is unavailable")),
            artifact_origin=origin,
        )
    if result.get("candidate_id") != candidate_id:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_CANDIDATE_3D_ID_MISMATCH",
            "the preview artifact is not bound to this candidate id",
            artifact_candidate_id=result.get("candidate_id"),
        )
    mesh = result.get("mesh", {})
    claims = result.get("claims", {})
    available = (isinstance(mesh, Mapping) and bool(mesh.get("vertices"))
                 and bool(mesh.get("faces")))
    safe_claims = (isinstance(claims, Mapping)
                   and claims.get("preview_only") is True
                   and claims.get("manufacturing_ready") is False)
    if not available or not safe_claims or result.get("state") != PROPOSED:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_CANDIDATE_3D_AUTHORITY_OR_GEOMETRY",
            "3D must contain geometry, be candidate-bound, and remain a PROPOSED preview only",
            artifact_origin=origin,
        )
    return _axis(
        Disposition.SATISFIED,
        "ANSWER_CANDIDATE_SPECIFIC_3D_AVAILABLE",
        "a non-empty deterministic 3D preview is bound to this exact candidate",
        artifact_origin=origin, preview_digest=result.get("preview_digest"),
        preview_only=True, manufacturing_ready=False,
    )


def _authority_violations(candidate: Mapping[str, Any]) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []

    def walk(value: Any, path: Tuple[str, ...] = ()) -> None:
        if isinstance(value, Mapping):
            sensitive = any(
                any(token in segment.lower() for token in ("back", "rear", "material"))
                for segment in path
            )
            state = value.get("state")
            if sensitive and state is not None and str(state).upper() != PROPOSED:
                violations.append({
                    "path": "/".join(path + ("state",)),
                    "claimed": copy.deepcopy(state),
                    "required": PROPOSED,
                })
            for key, child in value.items():
                lower = str(key).lower()
                if (any(token in lower for token in ("back", "rear", "material"))
                        and lower.endswith(("state", "authority"))
                        and str(child).upper() != PROPOSED):
                    violations.append({
                        "path": "/".join(path + (str(key),)),
                        "claimed": copy.deepcopy(child),
                        "required": PROPOSED,
                    })
                if (lower in {"back_observed", "rear_observed", "material_observed"}
                        and child is not False):
                    violations.append({
                        "path": "/".join(path + (str(key),)),
                        "claimed": copy.deepcopy(child),
                        "required": False,
                    })
                walk(child, path + (str(key),))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, child in enumerate(value):
                walk(child, path + (str(index),))

    walk(candidate)
    if candidate.get("state", PROPOSED) != PROPOSED:
        violations.append({
            "path": "state", "claimed": candidate.get("state"),
            "required": PROPOSED,
        })
    unobserved = candidate.get("unobserved")
    if isinstance(unobserved, Mapping) and unobserved.get("back") != PROPOSED:
        violations.append({
            "path": "unobserved/back", "claimed": unobserved.get("back"),
            "required": PROPOSED,
        })
    # Stable de-duplication keeps the report deterministic when a scalar is
    # caught by both the generic and the explicit authority checks.
    unique = {
        json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False): row
        for row in violations
    }
    return [unique[key] for key in sorted(unique)]


def _evidence_authority_axis(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    violations = _authority_violations(candidate)
    if violations:
        return _axis(
            Disposition.UNSATISFIED,
            "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
            "front-only data may not promote rear or material claims to observed, approved, or certified facts",
            violations=violations,
        )
    return _axis(
        Disposition.SATISFIED,
        "ANSWER_EVIDENCE_AUTHORITY_PRESERVED",
        "observed front evidence is separated from proposed rear and material hypotheses",
        rear_authority=PROPOSED, material_authority=PROPOSED,
        candidate_state=PROPOSED,
    )


def _candidate_verdict(axes: Mapping[str, Mapping[str, Any]]) -> str:
    dispositions = {str(value.get("disposition")) for value in axes.values()}
    if Disposition.UNSATISFIED.value in dispositions:
        return "UNKNOWN_FRONT_CANDIDATE_REJECTED"
    return "REVIEW_FRONT_CANDIDATE_APPROVAL_REQUIRED"


def _review_reasons(axes: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, str]]:
    reasons = [
        {
            "axis": name,
            "verdict": str(result["verdict"]),
            "why": str(result["why"]),
        }
        for name, result in axes.items()
        if result.get("disposition") != Disposition.SATISFIED.value
    ]
    reasons.extend((
        {
            "axis": "front_only_boundary",
            "verdict": "REVIEW_REAR_STRUCTURE_PROPOSED",
            "why": "the rear is unseen and remains a falsifiable proposal",
        },
        {
            "axis": "front_only_boundary",
            "verdict": "REVIEW_MATERIAL_PROPOSED",
            "why": "material identity and mechanical properties are not established by one front image",
        },
        {
            "axis": "front_only_boundary",
            "verdict": "REVIEW_MANUFACTURING_CERTIFICATION_NOT_CREATED",
            "why": "geometric lowering and preview generation do not certify manufacture",
        },
    ))
    return reasons


def _dominance(reports: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]],
                                                               List[str]]:
    edges: List[Dict[str, Any]] = []
    dominated: Set[str] = set()
    for left in reports:
        for right in reports:
            if left["candidate_id"] == right["candidate_id"]:
                continue
            weakly_better = True
            strictly_better: List[str] = []
            for name in AXES:
                left_value = _PARETO_ORDER[left["axes"][name]["disposition"]]
                right_value = _PARETO_ORDER[right["axes"][name]["disposition"]]
                if left_value < right_value:
                    weakly_better = False
                    break
                if left_value > right_value:
                    strictly_better.append(name)
            if weakly_better and strictly_better:
                edges.append({
                    "dominant_candidate_id": left["candidate_id"],
                    "dominated_candidate_id": right["candidate_id"],
                    "strictly_better_axes": strictly_better,
                    "equal_or_better_on_all_axes": True,
                })
                dominated.add(str(right["candidate_id"]))
    edges.sort(key=lambda row: (
        row["dominant_candidate_id"], row["dominated_candidate_id"]))
    frontier = sorted(
        str(row["candidate_id"]) for row in reports
        if str(row["candidate_id"]) not in dominated)
    return edges, frontier


def evaluate_candidates(
    candidates: Sequence[Mapping[str, Any]], *,
    front_evidence: Optional[Mapping[str, Any]] = None,
    previews: Optional[Mapping[str, Mapping[str, Any]]] = None,
    patterns: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate and Pareto-compare front-only structure candidates.

    ``previews`` and ``patterns`` may supply candidate-id keyed artifacts.  If
    omitted, the existing deterministic preview and pattern engines are run.
    Supplied artifacts are never accepted by list position: candidate identity
    must match exactly.
    """
    if (not isinstance(candidates, Sequence)
            or isinstance(candidates, (str, bytes)) or not candidates
            or any(not isinstance(row, Mapping) for row in candidates)):
        return {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_FRONT_CANDIDATES_REQUIRED",
            "why": "one or more candidate mappings are required",
            "manufacturing_certified": False,
        }
    front = front_evidence if isinstance(front_evidence, Mapping) else {}
    ids = [_candidate_id(row) for row in candidates]
    if any(value is None for value in ids):
        return {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_FRONT_CANDIDATE_ID_REQUIRED",
            "why": "every candidate needs a stable non-empty candidate_id",
            "manufacturing_certified": False,
        }
    if len(ids) != len(set(ids)):
        return {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_DUPLICATE_FRONT_CANDIDATE_ID",
            "why": "candidate ids must be unique",
            "manufacturing_certified": False,
        }

    reports: List[Dict[str, Any]] = []
    by_id = sorted(zip(ids, candidates), key=lambda row: str(row[0]))
    for candidate_id_value, candidate in by_id:
        assert candidate_id_value is not None
        graph = _structure(candidate)
        axes = {
            "front_silhouette_consistency": _front_silhouette_axis(
                candidate, graph, front),
            "layer_order_consistency": _layer_axis(candidate, graph, front),
            "topology_validity": _topology_axis(graph),
            "closure_donning_plausibility": _closure_axis(candidate, graph),
            "pattern_lowerability": _pattern_axis(
                candidate_id_value, graph, patterns),
            "candidate_specific_3d_availability": _preview_axis(
                candidate_id_value, graph, previews),
            "evidence_authority": _evidence_authority_axis(candidate),
        }
        report = {
            "candidate_id": candidate_id_value,
            "candidate_state": PROPOSED,
            "verdict": _candidate_verdict(axes),
            "axes": axes,
            "review_reasons": _review_reasons(axes),
            "rear_authority": PROPOSED,
            "material_authority": PROPOSED,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        }
        report["evaluation_digest"] = _digest(report)
        reports.append(report)

    dominance, frontier = _dominance(reports)
    verdict = ("REVIEW_FRONT_CANDIDATE_APPROVAL_REQUIRED"
               if len(frontier) == 1
               else "REVIEW_FRONT_CANDIDATE_SELECTION_REQUIRED")
    result = {
        "schema": SCHEMA,
        "verdict": verdict,
        "state": "REVIEW",
        "axes": list(AXES),
        "candidates": reports,
        "pareto_frontier": frontier,
        "dominance": dominance,
        "selected_candidate_id": None,
        "requires_human_approval": True,
        "rear_authority": PROPOSED,
        "material_authority": PROPOSED,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "claims": {
            "single_aggregate_used": False,
            "pareto_only": True,
            "rear_observed": False,
            "material_observed": False,
            "manufacturing_certification_created": False,
        },
    }
    result["evaluation_digest"] = _digest(result)
    return result


evaluate = evaluate_candidates
