"""Milestone O extension — structural similarity between GapNodes.

Core idea (design discussion): two problems can look nothing alike as text
("profile save doesn't work" vs "3D export doesn't work") while sharing
the same underlying shape (trigger -> expected state transition -> no
observed transition). Comparing that shape lets a resolution strategy
learned for one gap transfer to a structurally similar one, without
pretending the two are the same *topic*.

Deliberately NOT a single similarity scalar, matching the rest of this
codebase's own style (boundary.py, consensus.py's lexicographic move
acceptance): each dimension is scored separately, then combined via an
explicit, ordered rule set instead of a weighted average -- so "same
failure shape, different data dependency" and "same failure shape, same
evidence pattern" are visibly different verdicts, not collapsed into one
number.

Vector embeddings (JGEN or otherwise) are NOT used here at all in this
pass -- this module is pure structural comparison over GapNode's typed
fields. The design discussion's own framing applies: structure is the
judge, embeddings would only ever be an assistant for the semantic
"is 'save' close enough to 'export'" gap, and that assistant isn't wired
up yet (deliberately out of scope for this pass -- would need a JGEN
model loaded, which isn't guaranteed to be true when this runs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Literal, Optional

from .gap_graph import GapNode

MatchLevel = Literal["NOT_COMPARABLE", "STRUCTURAL_CANDIDATE", "HIGH_CONFIDENCE", "SKILL_REUSE_CANDIDATE"]


@dataclass(frozen=True)
class StructuralSignature:
    gap_id: str
    node_type: str
    role: Optional[str] = None
    relation_types: FrozenSet[str] = field(default_factory=frozenset)
    failure_type: Optional[str] = None
    input_type: Optional[str] = None
    output_type: Optional[str] = None
    expected_transition: Optional[str] = None
    observed_transition: Optional[str] = None
    has_resolution: bool = False


def from_gap_node(node: GapNode) -> StructuralSignature:
    relations = set()
    if node.caused_by:
        relations.add("caused_by")
    if node.blocks:
        relations.add("blocks")
    return StructuralSignature(
        gap_id=node.gap_id, node_type=node.gap_type, role=node.role,
        relation_types=frozenset(relations), failure_type=node.failure_type,
        input_type=node.input_type, output_type=node.output_type,
        expected_transition=node.expected_transition, observed_transition=node.observed_transition,
        has_resolution=node.status == "RESOLVED" and node.resolution is not None,
    )


def _jaccard(a: FrozenSet[str], b: FrozenSet[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _eq_score(a: Optional[str], b: Optional[str]) -> float:
    if a is None or b is None:
        return 0.0
    return 1.0 if a == b else 0.0


def structural_similarity(a: StructuralSignature, b: StructuralSignature) -> Dict[str, float]:
    return {
        "role": _eq_score(a.role, b.role),
        "relations": _jaccard(a.relation_types, b.relation_types),
        "failure_type": _eq_score(a.failure_type, b.failure_type),
        "input_type": _eq_score(a.input_type, b.input_type),
        "output_type": _eq_score(a.output_type, b.output_type),
        "expected_transition": _eq_score(a.expected_transition, b.expected_transition),
        "observed_transition": _eq_score(a.observed_transition, b.observed_transition),
    }


@dataclass
class StructuralMatch:
    gap_id: str
    level: MatchLevel
    scores: Dict[str, float]
    matched_dimensions: List[str]
    different_dimensions: List[str]


def classify_match(a: StructuralSignature, b: StructuralSignature) -> StructuralMatch:
    """Ordered/lexicographic rule, not a weighted sum (see module
    docstring): a role mismatch disqualifies regardless of how well
    everything else scores, matching the design discussion's explicit
    "重大な矛盾がある→非類似 / 必須役割が一致しない→非類似" rule."""
    scores = structural_similarity(a, b)
    matched = [dim for dim, s in scores.items() if s >= 0.999]
    different = [dim for dim, s in scores.items() if s < 0.999]

    # A node with no role/failure_type set at all can't be meaningfully
    # compared -- fail closed rather than treat "unset" as "equal".
    if a.role is None or b.role is None or a.failure_type is None or b.failure_type is None:
        return StructuralMatch(b.gap_id, "NOT_COMPARABLE", scores, matched, different)

    if a.role != b.role:
        return StructuralMatch(b.gap_id, "NOT_COMPARABLE", scores, matched, different)

    if a.failure_type != b.failure_type:
        return StructuralMatch(b.gap_id, "NOT_COMPARABLE", scores, matched, different)

    # role + failure_type match: at least a structural candidate.
    transition_match = (
        scores["expected_transition"] >= 0.999 and scores["observed_transition"] >= 0.999
    )
    if not transition_match:
        return StructuralMatch(b.gap_id, "STRUCTURAL_CANDIDATE", scores, matched, different)

    evidence_match = scores["input_type"] >= 0.999 and scores["output_type"] >= 0.999
    if not evidence_match:
        return StructuralMatch(b.gap_id, "STRUCTURAL_CANDIDATE", scores, matched, different)

    if b.has_resolution:
        return StructuralMatch(b.gap_id, "SKILL_REUSE_CANDIDATE", scores, matched, different)

    return StructuralMatch(b.gap_id, "HIGH_CONFIDENCE", scores, matched, different)


def find_structural_matches(
    target: GapNode, candidates: List[GapNode], *, limit: int = 5,
) -> List[StructuralMatch]:
    """Ranked matches against `candidates` (typically GapGraph.nodes.values(),
    excluding `target` itself), best (SKILL_REUSE_CANDIDATE > HIGH_CONFIDENCE
    > STRUCTURAL_CANDIDATE) first. NOT_COMPARABLE nodes are dropped, not
    ranked last -- they're not matches at all."""
    order = {"SKILL_REUSE_CANDIDATE": 0, "HIGH_CONFIDENCE": 1, "STRUCTURAL_CANDIDATE": 2}
    sig_a = from_gap_node(target)
    results = []
    for node in candidates:
        if node.gap_id == target.gap_id:
            continue
        sig_b = from_gap_node(node)
        match = classify_match(sig_a, sig_b)
        if match.level == "NOT_COMPARABLE":
            continue
        results.append(match)
    results.sort(key=lambda m: order[m.level])
    return results[:limit]
