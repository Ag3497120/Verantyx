# -*- coding: utf-8 -*-
"""Deterministic comparison and digest-bound approval of garment candidates.

Back and material candidates are alternatives, never inferred facts.  An
approval is a separate immutable record; it does not mutate a candidate's
``PROPOSED`` state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


PROPOSED = "PROPOSED"
APPROVED = "APPROVED"


class CandidateDomain(str, Enum):
    BACK = "BACK_STRUCTURE"
    MATERIAL = "MATERIAL"


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_plain(value), sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> bool:
    try:
        json.dumps(_plain(value), allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class CandidateProposal:
    candidate_id: str
    domain: CandidateDomain
    payload: Mapping[str, Any]
    constraints: Tuple[Mapping[str, Any], ...]
    assumptions: Tuple[str, ...]
    source_evidence: Tuple[Mapping[str, Any], ...]
    state: str = PROPOSED

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", CandidateDomain(self.domain))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "source_evidence", tuple(self.source_evidence))
        if self.state != PROPOSED:
            raise ValueError("candidates may only be PROPOSED")

    def digest_payload(self) -> Dict[str, Any]:
        return {"candidate_id": self.candidate_id, "domain": self.domain.value,
                "payload": _plain(self.payload), "constraints": _plain(self.constraints),
                "assumptions": list(self.assumptions),
                "source_evidence": _plain(self.source_evidence), "state": PROPOSED}

    @property
    def digest(self) -> str:
        return _digest(self.digest_payload())

    def as_dict(self) -> Dict[str, Any]:
        return {**copy.deepcopy(self.digest_payload()), "digest": self.digest}


@dataclass(frozen=True)
class CandidateComparison:
    domain: CandidateDomain
    candidates: Tuple[CandidateProposal, ...]
    criteria: Tuple[str, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", CandidateDomain(self.domain))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "criteria", tuple(self.criteria))

    @property
    def digest(self) -> str:
        return _digest({"domain": self.domain.value,
                        "candidate_digests": [c.digest for c in self.candidates],
                        "criteria": list(self.criteria),
                        "evidence_digest": self.evidence_digest})

    def as_dict(self) -> Dict[str, Any]:
        return {"verdict": PROPOSED, "domain": self.domain.value,
                "candidates": [c.as_dict() for c in self.candidates],
                "criteria": list(self.criteria), "evidence_digest": self.evidence_digest,
                "comparison_digest": self.digest, "selected_candidate": None,
                "requires_human_approval": True}


@dataclass(frozen=True)
class CandidateApproval:
    approval_id: str
    approver: str
    candidate_id: str
    candidate_digest: str
    comparison_digest: str
    state: str = APPROVED

    def as_dict(self) -> Dict[str, str]:
        return _plain(self.__dict__)


def propose_candidate(candidate_id: str, domain: Any, payload: Mapping[str, Any], *,
                      constraints: Sequence[Mapping[str, Any]], assumptions: Sequence[str],
                      source_evidence: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Create a proposal only when every uncertainty and source is explicit."""
    try:
        typed_domain = CandidateDomain(domain)
    except (TypeError, ValueError):
        return {"verdict": "UNKNOWN_CANDIDATE_DOMAIN"}
    if (not isinstance(candidate_id, str) or not candidate_id.strip()
            or not isinstance(payload, Mapping)
            or not payload or not _json_safe(payload)):
        return {"verdict": "UNKNOWN_MALFORMED_CANDIDATE", "why": "id and JSON-safe payload are required"}
    if not constraints or not all(isinstance(row, Mapping) for row in constraints):
        return {"verdict": "UNKNOWN_CANDIDATE_CONSTRAINTS", "why": "at least one explicit constraint is required"}
    if not source_evidence or not all(isinstance(row, Mapping) and row for row in source_evidence):
        return {"verdict": "UNKNOWN_CANDIDATE_EVIDENCE", "why": "source evidence is required"}
    if not all(isinstance(value, str) and value.strip() for value in assumptions):
        return {"verdict": "UNKNOWN_CANDIDATE_ASSUMPTION", "why": "assumptions must be explicit strings"}
    candidate = CandidateProposal(candidate_id.strip(), typed_domain,
                                  copy.deepcopy(dict(payload)), tuple(copy.deepcopy(constraints)),
                                  tuple(assumptions), tuple(copy.deepcopy(source_evidence)))
    return {"verdict": PROPOSED, "candidate": candidate,
            "digest": candidate.digest, "requires_human_approval": True}


def compare_candidates(candidates: Iterable[CandidateProposal], *, criteria: Sequence[str],
                       evidence: Mapping[str, Any]) -> Dict[str, Any]:
    """Preserve alternatives and bind the whole comparison context by digest."""
    values = tuple(candidates)
    if len(values) < 2:
        return {"verdict": "UNKNOWN_INSUFFICIENT_CANDIDATES", "why": "comparison needs at least two alternatives"}
    if not all(isinstance(c, CandidateProposal) and c.state == PROPOSED for c in values):
        return {"verdict": "UNKNOWN_NON_PROPOSED_CANDIDATE"}
    domains = {c.domain for c in values}
    if len(domains) != 1:
        return {"verdict": "UNKNOWN_MIXED_CANDIDATE_DOMAINS"}
    ids = [c.candidate_id for c in values]
    if len(ids) != len(set(ids)):
        return {"verdict": "UNKNOWN_DUPLICATE_CANDIDATE"}
    if not criteria or not all(isinstance(x, str) and x.strip() for x in criteria):
        return {"verdict": "UNKNOWN_COMPARISON_CRITERIA"}
    if not isinstance(evidence, Mapping) or not evidence or not _json_safe(evidence):
        return {"verdict": "UNKNOWN_COMPARISON_EVIDENCE"}
    comparison = CandidateComparison(next(iter(domains)), values, tuple(criteria), _digest(evidence))
    return {**comparison.as_dict(), "comparison": comparison}


def compare_back_candidates(candidates: Iterable[CandidateProposal], *,
                            evidence: Mapping[str, Any],
                            criteria: Sequence[str] = ("front_consistency", "geometric_feasibility", "dressability")) -> Dict[str, Any]:
    result = compare_candidates(candidates, criteria=criteria, evidence=evidence)
    if result.get("verdict") == PROPOSED and result["comparison"].domain is not CandidateDomain.BACK:
        return {"verdict": "UNKNOWN_CANDIDATE_DOMAIN", "why": "back comparison accepts BACK_STRUCTURE only"}
    return result


def compare_material_candidates(candidates: Iterable[CandidateProposal], *,
                                evidence: Mapping[str, Any],
                                criteria: Sequence[str] = ("drape", "stretch", "bending", "mass")) -> Dict[str, Any]:
    result = compare_candidates(candidates, criteria=criteria, evidence=evidence)
    if result.get("verdict") == PROPOSED and result["comparison"].domain is not CandidateDomain.MATERIAL:
        return {"verdict": "UNKNOWN_CANDIDATE_DOMAIN", "why": "material comparison accepts MATERIAL only"}
    return result


class CandidateApprovalGate:
    """In-memory gate binding approval to candidate and comparison digests."""

    def __init__(self) -> None:
        self._comparisons: Dict[str, CandidateComparison] = {}
        self._approvals: Dict[str, CandidateApproval] = {}

    def register(self, comparison: CandidateComparison) -> Dict[str, Any]:
        if not isinstance(comparison, CandidateComparison):
            return {"verdict": "UNKNOWN_MALFORMED_COMPARISON"}
        self._comparisons[comparison.digest] = comparison
        return {"verdict": PROPOSED, "comparison_digest": comparison.digest}

    def approve(self, comparison_digest: str, candidate_id: str, *,
                expected_candidate_digest: str, approver: str) -> Dict[str, Any]:
        comparison = self._comparisons.get(comparison_digest)
        if comparison is None:
            return {"verdict": "UNKNOWN_COMPARISON_APPROVAL_REQUIRED"}
        if not str(approver).strip():
            return {"verdict": "UNKNOWN_NAMED_HUMAN_APPROVER_REQUIRED"}
        candidate = next((c for c in comparison.candidates if c.candidate_id == candidate_id), None)
        if candidate is None:
            return {"verdict": "UNKNOWN_CANDIDATE_NOT_IN_COMPARISON"}
        if candidate.digest != expected_candidate_digest:
            return {"verdict": "UNKNOWN_CANDIDATE_APPROVAL_STALE",
                    "expected": candidate.digest, "received": expected_candidate_digest}
        approval_id = _digest({"comparison_digest": comparison.digest,
                               "candidate_digest": candidate.digest,
                               "approver": approver.strip()})
        approval = CandidateApproval(approval_id, approver.strip(), candidate.candidate_id,
                                     candidate.digest, comparison.digest)
        self._approvals[approval_id] = approval
        return {"verdict": APPROVED, "approval": approval,
                "candidate": candidate.as_dict(),
                "note": "candidate remains PROPOSED; approval is a separate human record"}

    def approval(self, approval_id: str) -> Optional[CandidateApproval]:
        return self._approvals.get(approval_id)


def propose(kind: Any, evidence: Mapping[str, Any],
            candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """JSON API returning an immutable comparison sheet of proposals.

    Each input candidate must explicitly carry ``candidate_id``, ``payload``,
    ``constraints``, ``assumptions`` and ``source_evidence``.  Shared evidence
    is bound into the sheet digest but is not copied into candidate claims.
    """
    try:
        domain = CandidateDomain(kind)
    except (TypeError, ValueError):
        aliases = {"back": CandidateDomain.BACK, "material": CandidateDomain.MATERIAL}
        domain = aliases.get(str(kind).lower())
        if domain is None:
            return {"verdict": "UNKNOWN_CANDIDATE_DOMAIN"}
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return {"verdict": "UNKNOWN_MALFORMED_CANDIDATE"}
    made = []
    for row in candidates:
        if not isinstance(row, Mapping):
            return {"verdict": "UNKNOWN_MALFORMED_CANDIDATE"}
        sources = row.get("source_evidence")
        if sources is None:
            sources = (dict(evidence),) if isinstance(evidence, Mapping) and evidence else ()
        result = propose_candidate(
            row.get("candidate_id", row.get("id", "")), domain, row.get("payload", {}),
            constraints=row.get("constraints", ()), assumptions=row.get("assumptions", ()),
            source_evidence=sources)
        if result.get("verdict") != PROPOSED:
            return result
        made.append(result["candidate"])
    criteria = ("front_consistency", "geometric_feasibility", "dressability") if domain is CandidateDomain.BACK else ("drape", "stretch", "bending", "mass")
    result = compare_candidates(made, criteria=criteria, evidence=evidence)
    if result.get("verdict") != PROPOSED:
        return result
    # Public sheet contains no Python objects.
    sheet = result["comparison"].as_dict()
    sheet["schema"] = "garment.candidate-sheet.v1"
    return sheet


def approve(sheet: Mapping[str, Any], digest: str, by: str) -> Dict[str, Any]:
    """Approve one candidate digest on a JSON comparison sheet.

    ``digest`` is the selected candidate digest, not a score or list index.
    Rebuilding or editing any candidate invalidates it.
    """
    if (not isinstance(sheet, Mapping)
            or sheet.get("schema") != "garment.candidate-sheet.v1"
            or sheet.get("verdict") != PROPOSED):
        return {"verdict": "UNKNOWN_MALFORMED_COMPARISON"}
    if not str(by).strip():
        return {"verdict": "UNKNOWN_NAMED_HUMAN_APPROVER_REQUIRED"}
    rows = sheet.get("candidates")
    if not isinstance(rows, list):
        return {"verdict": "UNKNOWN_MALFORMED_COMPARISON"}
    selected = next((row for row in rows
                     if isinstance(row, Mapping) and row.get("digest") == digest), None)
    if selected is None:
        return {"verdict": "UNKNOWN_CANDIDATE_APPROVAL_STALE"}
    # Recompute every candidate digest: approval is bound to the complete
    # comparison context, not only to the row selected by the human.
    digest_keys = ("candidate_id", "domain", "payload", "constraints",
                   "assumptions", "source_evidence", "state")
    recomputed = [_digest({k: row.get(k) for k in digest_keys})
                  for row in rows if isinstance(row, Mapping)]
    if len(recomputed) != len(rows) or any(
            recomputed[index] != row.get("digest")
            for index, row in enumerate(rows)):
        return {"verdict": "UNKNOWN_CANDIDATE_APPROVAL_STALE"}
    comparison_payload = {
        "domain": sheet.get("domain"),
        "candidate_digests": recomputed,
        "criteria": sheet.get("criteria"),
        "evidence_digest": sheet.get("evidence_digest"),
    }
    current_comparison_digest = _digest(comparison_payload)
    if current_comparison_digest != sheet.get("comparison_digest"):
        return {"verdict": "UNKNOWN_COMPARISON_APPROVAL_STALE"}
    approval_id = _digest({"comparison_digest": current_comparison_digest,
                           "candidate_digest": digest, "approver": by.strip()})
    return {"verdict": APPROVED,
            "approval": {"approval_id": approval_id, "approver": by.strip(),
                         "candidate_id": selected["candidate_id"],
                         "candidate_digest": digest,
                         "comparison_digest": current_comparison_digest,
                         "state": APPROVED},
            "candidate": copy.deepcopy(dict(selected)),
            "note": "candidate remains PROPOSED; approval is a separate human record"}
