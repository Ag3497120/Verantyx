# -*- coding: utf-8 -*-
"""Append-only garment-generation jobs with digest-bound preview approval."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from . import cross_workflow_harness


class JobState(str, Enum):
    IMAGE_RECEIVED = "IMAGE_RECEIVED"
    AI_ANALYSIS_PROPOSED = "AI_ANALYSIS_PROPOSED"
    HUMAN_GARMENT_AUDIT_REQUIRED = "HUMAN_GARMENT_AUDIT_REQUIRED"
    FOREGROUND_CLEANUP_REQUIRED = "FOREGROUND_CLEANUP_REQUIRED"
    CLEANUP_REVIEW_REQUIRED = "CLEANUP_REVIEW_REQUIRED"
    FRONT_FACTS_RECORDED = "FRONT_FACTS_RECORDED"
    TARGET_2_5D_READY = "TARGET_2_5D_READY"
    PART_SEGMENTATION_REQUIRED = "PART_SEGMENTATION_REQUIRED"
    REAR_CANDIDATES_REQUIRED = "REAR_CANDIDATES_REQUIRED"
    CAD_SCULPT_REQUIRED = "CAD_SCULPT_REQUIRED"
    TARGET_APPROVAL_REQUIRED = "TARGET_APPROVAL_REQUIRED"
    PATTERN_INVERSE_REQUIRED = "PATTERN_INVERSE_REQUIRED"
    REDRESS_COMPARISON_REQUIRED = "REDRESS_COMPARISON_REQUIRED"
    REGIONS_CONFIRMED = "REGIONS_CONFIRMED"
    GEOMETRY_CONTESTED = "GEOMETRY_CONTESTED"
    BACK_CANDIDATES_READY = "BACK_CANDIDATES_READY"
    STRUCTURE_APPROVED = "STRUCTURE_APPROVED"
    MATERIAL_CONTESTED = "MATERIAL_CONTESTED"
    SIMULATION_READY = "SIMULATION_READY"
    SHAPE_APPROVED = "SHAPE_APPROVED"
    PATTERN_VALIDATED = "PATTERN_VALIDATED"
    SEWING_BLOCKED_NO_CORPUS = "SEWING_BLOCKED_NO_CORPUS"
    COMPLETE = "COMPLETE"


INVALID_TRANSITION = "UNKNOWN_INVALID_JOB_TRANSITION"
MISSING_DIGEST = "UNKNOWN_REQUIRED_ARTIFACT_DIGEST"
PREVIEW_NOT_FOUND = "UNKNOWN_PREVIEW_NOT_FOUND"
APPROVAL_STALE = "UNKNOWN_PREVIEW_APPROVAL_STALE"
APPROVER_REQUIRED = "UNKNOWN_NAMED_HUMAN_APPROVER_REQUIRED"
UNDO_EMPTY = "UNKNOWN_NOTHING_TO_UNDO"
STAGE_CONTRACT_REQUIRED = "UNKNOWN_JOB_STAGE_CONTRACT_REQUIRED"
STALE_ARTIFACT_REVISION = "UNKNOWN_ARTIFACT_REVISION_STALE"
REVIEWER_REQUIRED = "UNKNOWN_NAMED_HUMAN_REVIEWER_REQUIRED"
INVALID_HUMAN_AUDIT = "UNKNOWN_INVALID_HUMAN_GARMENT_AUDIT"
INVALID_CLEANUP_RECORD = "UNKNOWN_INVALID_FOREGROUND_CLEANUP_RECORD"
FUTURE_STAGE_NOT_IMPLEMENTED = "UNKNOWN_FUTURE_JOB_STAGE_REQUIREMENT"


FUTURE_STAGE_REQUIREMENTS = MappingProxyType({
    JobState.PART_SEGMENTATION_REQUIRED: (
        "approved front facts", "typed visible-part segmentation artifact"),
    JobState.REAR_CANDIDATES_REQUIRED: (
        "front-only part graph", "multiple explicitly PROPOSED rear candidates"),
    JobState.CAD_SCULPT_REQUIRED: (
        "selected body", "editable target surface", "deterministic edit lineage"),
    JobState.TARGET_APPROVAL_REQUIRED: (
        "named human reviewer", "digest-bound target preview"),
    JobState.PATTERN_INVERSE_REQUIRED: (
        "approved target", "construction regime", "manufacturability checks"),
    JobState.REDRESS_COMPARISON_REQUIRED: (
        "pattern artifact", "redressed 3D artifact", "source-view difference report"),
})


_VISIBLE_FRONT_SCOPES = frozenset({
    "VISIBLE_FRONT", "FRONT_VISIBLE", "OBSERVED_FRONT", "VISIBLE",
})
_REMOVABLE_CLASSES = frozenset({
    "BACKGROUND", "HAIR", "BODY", "OTHER_GARMENT",
})


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v) for v in value)
    return copy.deepcopy(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw(v) for v in value]
    return copy.deepcopy(value)


def stable_digest(value: Any) -> str:
    payload = json.dumps(_thaw(value), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JobSnapshot:
    state: Optional[JobState]
    artifacts: Mapping[str, str]
    data: Mapping[str, Any]
    revision: int
    digest: str = ""

    def __post_init__(self) -> None:
        if self.state is not None:
            object.__setattr__(self, "state", JobState(self.state))
        object.__setattr__(self, "artifacts", _freeze(self.artifacts))
        object.__setattr__(self, "data", _freeze(self.data))
        canonical = {"state": self.state.value if self.state else None,
                     "artifacts": _thaw(self.artifacts),
                     "data": _thaw(self.data), "revision": self.revision}
        object.__setattr__(self, "digest", stable_digest(canonical))

    def as_dict(self) -> Dict[str, Any]:
        return {"state": self.state.value if self.state else None,
                "artifacts": _thaw(self.artifacts), "data": _thaw(self.data),
                "revision": self.revision, "digest": self.digest}


@dataclass(frozen=True)
class JobEvent:
    sequence: int
    kind: str
    before_digest: str
    after_digest: str
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    def as_dict(self) -> Dict[str, Any]:
        return {"sequence": self.sequence, "kind": self.kind,
                "before_digest": self.before_digest,
                "after_digest": self.after_digest,
                "payload": _thaw(self.payload),
                "provenance": _thaw(self.provenance)}


@dataclass(frozen=True)
class Preview:
    preview_id: str
    before: JobSnapshot
    after: JobSnapshot
    changed_addresses: Tuple[str, ...]
    validation_results: Tuple[Mapping[str, Any], ...]
    command_id: str
    provenance: Mapping[str, Any]
    digest: str = ""
    schema: str = "garment.preview.v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_addresses",
                           tuple(str(x) for x in self.changed_addresses))
        object.__setattr__(self, "validation_results",
                           tuple(_freeze(x) for x in self.validation_results))
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        canonical = {"schema": self.schema, "preview_id": self.preview_id,
                     "before": self.before.as_dict(),
                     "after": self.after.as_dict(),
                     "changed_addresses": list(self.changed_addresses),
                     "validation_results": _thaw(self.validation_results),
                     "command_id": self.command_id,
                     "provenance": _thaw(self.provenance)}
        object.__setattr__(self, "digest", stable_digest(canonical))

    def as_dict(self) -> Dict[str, Any]:
        return {"schema": self.schema, "preview_id": self.preview_id,
                "before": self.before.as_dict(), "after": self.after.as_dict(),
                "changed_addresses": list(self.changed_addresses),
                "validation_results": _thaw(self.validation_results),
                "command_id": self.command_id,
                "provenance": _thaw(self.provenance), "digest": self.digest}


@dataclass(frozen=True)
class JobRefusal:
    verdict: str
    reason: str
    details: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", _freeze(self.details))

    def as_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict, "reason": self.reason,
                "details": _thaw(self.details)}


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _artifact_ref_matches(actual: Mapping[str, Any], artifact_id: Any,
                          revision: Any) -> bool:
    return (str(actual.get("artifact_id", "")) == str(artifact_id)
            and str(actual.get("revision", "")) == str(revision))


def _assertion_is_front_observable(assertion: Mapping[str, Any]) -> bool:
    """Return whether front review is allowed to promote this assertion.

    Human confirmation is evidence for what is visibly present in the reviewed
    front artifact.  It is not evidence for a rear/hidden construction or for
    fibre/material identity, even when the reviewer accepts it as a useful
    proposal.
    """
    scope = str(assertion.get(
        "evidence_scope", assertion.get("visibility", ""))).upper()
    field = str(assertion.get(
        "field", assertion.get("predicate", assertion.get("kind", "")))).lower()
    category = str(assertion.get("category", "")).lower()
    if scope not in _VISIBLE_FRONT_SCOPES:
        return False
    if any(token in field for token in ("rear", "back_", "hidden", "occluded")):
        return False
    if category in {"rear", "hidden", "material", "material_identity"}:
        return False
    if field in {"material", "material_identity", "fabric_identity",
                 "fiber", "fibre", "composition"}:
        return False
    return True


def _stage_contract_refusal(destination: JobState,
                            data: Mapping[str, Any]) -> Optional[JobRefusal]:
    required = {
        JobState.AI_ANALYSIS_PROPOSED: "ai_analysis",
        JobState.HUMAN_GARMENT_AUDIT_REQUIRED: "ai_analysis",
        JobState.FOREGROUND_CLEANUP_REQUIRED: "human_garment_audit",
        JobState.CLEANUP_REVIEW_REQUIRED: "foreground_cleanup",
        JobState.FRONT_FACTS_RECORDED: "front_facts",
        JobState.TARGET_2_5D_READY: "target_2_5d",
    }.get(destination)
    if required is None:
        return None
    contract = data.get(required)
    if not isinstance(contract, Mapping):
        return JobRefusal(
            STAGE_CONTRACT_REQUIRED,
            "destination requires its typed stage contract",
            {"state": destination.value, "required": required})
    return None


_NEXT = {
    None: {JobState.IMAGE_RECEIVED},
    # Keep the original IMAGE_RECEIVED -> REGIONS_CONFIRMED edge for existing
    # non-audited callers.  Once a job enters AI_ANALYSIS_PROPOSED, however,
    # there is deliberately no edge to geometry or the legacy region path.
    JobState.IMAGE_RECEIVED: {JobState.REGIONS_CONFIRMED,
                              JobState.AI_ANALYSIS_PROPOSED},
    JobState.AI_ANALYSIS_PROPOSED: {
        JobState.HUMAN_GARMENT_AUDIT_REQUIRED},
    JobState.HUMAN_GARMENT_AUDIT_REQUIRED: {
        JobState.FOREGROUND_CLEANUP_REQUIRED},
    JobState.FOREGROUND_CLEANUP_REQUIRED: {
        JobState.CLEANUP_REVIEW_REQUIRED},
    JobState.CLEANUP_REVIEW_REQUIRED: {
        JobState.FOREGROUND_CLEANUP_REQUIRED,
        JobState.FRONT_FACTS_RECORDED},
    JobState.FRONT_FACTS_RECORDED: {JobState.TARGET_2_5D_READY},
    JobState.TARGET_2_5D_READY: {JobState.REGIONS_CONFIRMED},
    JobState.PART_SEGMENTATION_REQUIRED: set(),
    JobState.REAR_CANDIDATES_REQUIRED: set(),
    JobState.CAD_SCULPT_REQUIRED: set(),
    JobState.TARGET_APPROVAL_REQUIRED: set(),
    JobState.PATTERN_INVERSE_REQUIRED: set(),
    JobState.REDRESS_COMPARISON_REQUIRED: set(),
    JobState.REGIONS_CONFIRMED: {JobState.GEOMETRY_CONTESTED,
                                 JobState.BACK_CANDIDATES_READY},
    JobState.GEOMETRY_CONTESTED: {JobState.BACK_CANDIDATES_READY},
    JobState.BACK_CANDIDATES_READY: {JobState.STRUCTURE_APPROVED},
    JobState.STRUCTURE_APPROVED: {JobState.MATERIAL_CONTESTED,
                                  JobState.SIMULATION_READY},
    JobState.MATERIAL_CONTESTED: {JobState.SIMULATION_READY},
    JobState.SIMULATION_READY: {JobState.SHAPE_APPROVED},
    JobState.SHAPE_APPROVED: {JobState.PATTERN_VALIDATED},
    JobState.PATTERN_VALIDATED: {JobState.SEWING_BLOCKED_NO_CORPUS,
                                 JobState.COMPLETE},
    JobState.SEWING_BLOCKED_NO_CORPUS: {JobState.COMPLETE},
    JobState.COMPLETE: set(),
}


class GarmentGenerationJob:
    """Mutable head over immutable snapshots and an append-only event tuple."""

    def __init__(self, job_id: str,
                 provenance: Optional[Mapping[str, Any]] = None) -> None:
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("job_id must be non-empty")
        self.job_id = job_id
        self._provenance = _freeze(provenance or {"source": "HUMAN_INPUT"})
        self._snapshot = JobSnapshot(None, {}, {}, 0)
        self._events: Tuple[JobEvent, ...] = ()
        self._previews: Dict[str, Preview] = {}
        self._applied: Tuple[JobSnapshot, ...] = ()
        self._cross_workflow = cross_workflow_harness.new_workflow(
            job_id, source_schema="garment.job.v1")

    @property
    def snapshot(self) -> JobSnapshot:
        return self._snapshot

    @property
    def events(self) -> Tuple[JobEvent, ...]:
        return self._events

    @property
    def history(self) -> Tuple[JobEvent, ...]:
        return self._events

    def _append(self, kind: str, before: JobSnapshot, after: JobSnapshot,
                payload: Mapping[str, Any],
                provenance: Optional[Mapping[str, Any]] = None) -> JobEvent:
        event = JobEvent(len(self._events) + 1, kind, before.digest,
                         after.digest, payload, provenance or self._provenance)
        self._events = self._events + (event,)
        self._snapshot = after
        return event

    def transition(self, state: JobState,
                   artifacts: Mapping[str, str], *,
                   data: Optional[Mapping[str, Any]] = None,
                   provenance: Optional[Mapping[str, Any]] = None):
        try:
            destination = JobState(state)
        except (ValueError, TypeError):
            return JobRefusal(INVALID_TRANSITION, "unknown job state",
                              {"requested": str(state)})
        if destination not in _NEXT[self._snapshot.state]:
            return JobRefusal(INVALID_TRANSITION,
                              "state transition is not an allowed next edge",
                              {"from": self._snapshot.state.value
                               if self._snapshot.state else None,
                               "to": destination.value})
        if not isinstance(artifacts, Mapping) or not artifacts:
            return JobRefusal(MISSING_DIGEST,
                              "transition requires named evidence/artifact digests")
        bad = sorted(str(k) for k, v in artifacts.items()
                     if not isinstance(k, str) or not k.strip()
                     or not isinstance(v, str) or not v.strip())
        if bad:
            return JobRefusal(MISSING_DIGEST,
                              "each transition artifact requires a name and digest",
                              {"invalid": bad})
        before = self._snapshot
        effective_data = (data if data is not None else _thaw(before.data))
        if not isinstance(effective_data, Mapping):
            return JobRefusal(STAGE_CONTRACT_REQUIRED,
                              "transition data must be an object")
        contract_refusal = _stage_contract_refusal(destination, effective_data)
        if contract_refusal is not None:
            return contract_refusal
        merged = dict(_thaw(before.artifacts))
        merged.update(dict(artifacts))
        after = JobSnapshot(destination, merged,
                            effective_data,
                            before.revision + 1)
        self._applied = self._applied + (before,)
        return self._append("STATE_TRANSITION", before, after,
                            {"state": destination.value,
                             "artifacts": dict(artifacts)}, provenance)

    def record_ai_analysis(self, *, source_artifact_id: str,
                           source_revision: Any,
                           analysis_artifact_id: str,
                           analysis_revision: Any,
                           analysis_digest: str,
                           assertions: Sequence[Mapping[str, Any]],
                           provenance: Optional[Mapping[str, Any]] = None):
        """Record model inventory/layer claims strictly as proposals."""
        if self._snapshot.state != JobState.IMAGE_RECEIVED:
            return JobRefusal(INVALID_TRANSITION,
                              "AI analysis requires IMAGE_RECEIVED",
                              {"from": self._snapshot.state.value
                               if self._snapshot.state else None})
        required_strings = (source_artifact_id, analysis_artifact_id,
                            analysis_digest)
        if (any(not _non_empty_string(value) for value in required_strings)
                or source_revision is None or analysis_revision is None):
            return JobRefusal(MISSING_DIGEST,
                              "AI analysis requires source and analysis refs")
        if (not isinstance(assertions, Sequence)
                or isinstance(assertions, (str, bytes))):
            return JobRefusal(INVALID_HUMAN_AUDIT,
                              "AI assertions must be an ordered array")

        current_data = _thaw(self._snapshot.data)
        existing_source = current_data.get("front_source")
        if (isinstance(existing_source, Mapping)
                and not _artifact_ref_matches(existing_source,
                                              source_artifact_id,
                                              source_revision)):
            return JobRefusal(
                STALE_ARTIFACT_REVISION,
                "AI analysis references a stale front artifact/revision",
                {"expected": _thaw(existing_source),
                 "supplied": {"artifact_id": source_artifact_id,
                              "revision": source_revision}})

        proposed = []
        seen = set()
        for ordinal, raw in enumerate(assertions):
            if not isinstance(raw, Mapping):
                return JobRefusal(INVALID_HUMAN_AUDIT,
                                  "each AI assertion must be an object",
                                  {"index": ordinal})
            assertion = _thaw(raw)
            assertion_id = assertion.get("assertion_id", assertion.get("id"))
            if not _non_empty_string(assertion_id) or assertion_id in seen:
                return JobRefusal(INVALID_HUMAN_AUDIT,
                                  "assertions require unique assertion_id values",
                                  {"index": ordinal,
                                   "assertion_id": assertion_id})
            seen.add(assertion_id)
            assertion["assertion_id"] = assertion_id
            assertion["evidence_state"] = "PROPOSED_BY_AI"
            assertion["proposal_ordinal"] = ordinal
            proposed.append(assertion)

        model_provenance = _thaw(provenance or {"source": "AI_MODEL"})
        current_data["front_source"] = {
            "artifact_id": source_artifact_id, "revision": source_revision}
        current_data["ai_analysis"] = {
            "artifact_id": analysis_artifact_id,
            "revision": analysis_revision,
            "source": {"artifact_id": source_artifact_id,
                       "revision": source_revision},
            "assertions": proposed,
            "evidence_state": "PROPOSED_BY_AI",
            "provenance": model_provenance,
        }
        return self.transition(
            JobState.AI_ANALYSIS_PROPOSED,
            {"ai_analysis": analysis_digest}, data=current_data,
            provenance=provenance)

    def require_human_garment_audit(self, *, analysis_artifact_id: str,
                                    analysis_revision: Any,
                                    provenance: Optional[Mapping[str, Any]] = None):
        analysis = self._snapshot.data.get("ai_analysis", {})
        if not isinstance(analysis, Mapping) or not _artifact_ref_matches(
                analysis, analysis_artifact_id, analysis_revision):
            return JobRefusal(
                STALE_ARTIFACT_REVISION,
                "human audit request references a stale AI analysis",
                {"expected": _thaw(analysis),
                 "supplied": {"artifact_id": analysis_artifact_id,
                              "revision": analysis_revision}})
        request = {"analysis_artifact_id": analysis_artifact_id,
                   "analysis_revision": analysis_revision}
        return self.transition(
            JobState.HUMAN_GARMENT_AUDIT_REQUIRED,
            {"human_audit_request": stable_digest(request)},
            data=_thaw(self._snapshot.data), provenance=provenance)

    def submit_human_garment_audit(
            self, *, analysis_artifact_id: str, analysis_revision: Any,
            reviewer: str, decisions: Sequence[Mapping[str, Any]],
            provenance: Optional[Mapping[str, Any]] = None):
        """Apply accept/reject/edit decisions without promoting hidden claims."""
        if not _non_empty_string(reviewer):
            return JobRefusal(REVIEWER_REQUIRED,
                              "garment audit requires a named human reviewer")
        if self._snapshot.state != JobState.HUMAN_GARMENT_AUDIT_REQUIRED:
            return JobRefusal(INVALID_TRANSITION,
                              "garment audit is not the active review stage")
        analysis = self._snapshot.data.get("ai_analysis", {})
        if not isinstance(analysis, Mapping) or not _artifact_ref_matches(
                analysis, analysis_artifact_id, analysis_revision):
            return JobRefusal(
                STALE_ARTIFACT_REVISION,
                "garment audit references a stale AI analysis",
                {"expected": _thaw(analysis),
                 "supplied": {"artifact_id": analysis_artifact_id,
                              "revision": analysis_revision}})
        if (not isinstance(decisions, Sequence)
                or isinstance(decisions, (str, bytes))):
            return JobRefusal(INVALID_HUMAN_AUDIT,
                              "audit decisions must be an ordered array")

        proposed = [_thaw(item) for item in analysis.get("assertions", ())]
        by_id = {item.get("assertion_id"): item for item in proposed}
        normalized_decisions: Dict[str, Dict[str, Any]] = {}
        for ordinal, raw in enumerate(decisions):
            if not isinstance(raw, Mapping):
                return JobRefusal(INVALID_HUMAN_AUDIT,
                                  "each audit decision must be an object",
                                  {"index": ordinal})
            assertion_id = raw.get("assertion_id", raw.get("id"))
            action = str(raw.get("action", "")).upper()
            if assertion_id not in by_id:
                return JobRefusal(INVALID_HUMAN_AUDIT,
                                  "audit decision names an unknown assertion",
                                  {"assertion_id": assertion_id})
            if assertion_id in normalized_decisions:
                return JobRefusal(INVALID_HUMAN_AUDIT,
                                  "an assertion may be reviewed only once",
                                  {"assertion_id": assertion_id})
            if action not in {"ACCEPT", "REJECT", "EDIT"}:
                return JobRefusal(INVALID_HUMAN_AUDIT,
                                  "audit action must be ACCEPT, REJECT, or EDIT",
                                  {"assertion_id": assertion_id,
                                   "action": action})
            edits = raw.get("edits", {})
            if action == "EDIT" and not isinstance(edits, Mapping):
                return JobRefusal(INVALID_HUMAN_AUDIT,
                                  "EDIT requires an edits object",
                                  {"assertion_id": assertion_id})
            normalized_decisions[assertion_id] = {
                "action": action, "edits": _thaw(edits),
                "reason": str(raw.get("reason", "")),
            }

        audited = []
        for assertion in proposed:
            assertion_id = assertion["assertion_id"]
            decision = normalized_decisions.get(assertion_id)
            if decision is None:
                audited.append(assertion)
                continue
            reviewed = copy.deepcopy(assertion)
            reviewed["ai_proposal"] = copy.deepcopy(assertion)
            if decision["action"] == "EDIT":
                # Identity and immutable audit metadata remain bound to the
                # original proposal; the human may edit its semantic content.
                for key, value in decision["edits"].items():
                    if key not in {"assertion_id", "proposal_ordinal",
                                   "ai_proposal", "reviewed_by"}:
                        reviewed[str(key)] = copy.deepcopy(value)
            reviewed["review_action"] = decision["action"]
            reviewed["reviewed_by"] = reviewer
            if decision["reason"]:
                reviewed["review_reason"] = decision["reason"]
            if decision["action"] == "REJECT":
                reviewed["evidence_state"] = "REJECTED_BY_HUMAN_REVIEW"
            elif _assertion_is_front_observable(reviewed):
                reviewed["evidence_state"] = "OBSERVED_BY_HUMAN_REVIEW"
            else:
                reviewed["evidence_state"] = "PROPOSED_AFTER_HUMAN_REVIEW"
            audited.append(reviewed)

        data = _thaw(self._snapshot.data)
        audit_contract = {
            "analysis_artifact_id": analysis_artifact_id,
            "analysis_revision": analysis_revision,
            "reviewer": reviewer,
            "decisions": [
                {"assertion_id": key, **value}
                for key, value in normalized_decisions.items()],
            "assertions": audited,
            "provenance": _thaw(provenance or {"source": "HUMAN_REVIEW"}),
        }
        data["human_garment_audit"] = audit_contract
        digest = stable_digest(audit_contract)
        return self.transition(
            JobState.FOREGROUND_CLEANUP_REQUIRED,
            {"human_garment_audit": digest}, data=data,
            provenance=provenance)

    def submit_foreground_cleanup(
            self, *, source_artifact_id: str, source_revision: Any,
            mask_artifact_id: str, mask_revision: Any, mask_digest: str,
            removed_classes: Sequence[str], undo_lineage: Sequence[str],
            reviewer: str,
            provenance: Optional[Mapping[str, Any]] = None):
        """Record cleanup references and lineage, never invented mask pixels."""
        if not _non_empty_string(reviewer):
            return JobRefusal(REVIEWER_REQUIRED,
                              "foreground cleanup requires a named reviewer")
        if self._snapshot.state != JobState.FOREGROUND_CLEANUP_REQUIRED:
            return JobRefusal(INVALID_TRANSITION,
                              "foreground cleanup is not the active stage")
        source = self._snapshot.data.get("front_source", {})
        if not isinstance(source, Mapping) or not _artifact_ref_matches(
                source, source_artifact_id, source_revision):
            return JobRefusal(
                STALE_ARTIFACT_REVISION,
                "cleanup references a stale front artifact/revision",
                {"expected": _thaw(source),
                 "supplied": {"artifact_id": source_artifact_id,
                              "revision": source_revision}})
        if (not _non_empty_string(mask_artifact_id)
                or not _non_empty_string(mask_digest)
                or mask_revision is None):
            return JobRefusal(INVALID_CLEANUP_RECORD,
                              "cleanup requires a mask artifact id, revision, and digest")
        if (not isinstance(removed_classes, Sequence)
                or isinstance(removed_classes, (str, bytes))):
            return JobRefusal(INVALID_CLEANUP_RECORD,
                              "removed_classes must be an ordered array")
        normalized_classes = tuple(
            str(value).strip().upper().replace(" ", "_").replace("-", "_")
            for value in removed_classes)
        invalid_classes = sorted(set(normalized_classes) - _REMOVABLE_CLASSES)
        if invalid_classes:
            return JobRefusal(INVALID_CLEANUP_RECORD,
                              "cleanup class is outside the closed vocabulary",
                              {"invalid": invalid_classes,
                               "allowed": sorted(_REMOVABLE_CLASSES)})
        if (not isinstance(undo_lineage, Sequence)
                or isinstance(undo_lineage, (str, bytes))
                or not undo_lineage
                or any(not _non_empty_string(value) for value in undo_lineage)):
            return JobRefusal(INVALID_CLEANUP_RECORD,
                              "cleanup requires non-empty artifact undo lineage")

        cleanup = {
            "source": {"artifact_id": source_artifact_id,
                       "revision": source_revision},
            "mask": {"artifact_id": mask_artifact_id,
                     "revision": mask_revision,
                     "digest": mask_digest},
            "removed_classes": list(normalized_classes),
            "undo_lineage": list(undo_lineage),
            "reviewer": reviewer,
            "provenance": _thaw(provenance or {"source": "HUMAN_CLEANUP"}),
            "pixel_geometry_recorded": False,
        }
        data = _thaw(self._snapshot.data)
        data["foreground_cleanup"] = cleanup
        return self.transition(
            JobState.CLEANUP_REVIEW_REQUIRED,
            {"foreground_mask": mask_digest}, data=data,
            provenance=provenance)

    def review_foreground_cleanup(
            self, *, mask_artifact_id: str, mask_revision: Any,
            reviewer: str, decision: str,
            provenance: Optional[Mapping[str, Any]] = None):
        if not _non_empty_string(reviewer):
            return JobRefusal(REVIEWER_REQUIRED,
                              "cleanup review requires a named human reviewer")
        if self._snapshot.state != JobState.CLEANUP_REVIEW_REQUIRED:
            return JobRefusal(INVALID_TRANSITION,
                              "cleanup review is not the active stage")
        cleanup = self._snapshot.data.get("foreground_cleanup", {})
        mask = cleanup.get("mask", {}) if isinstance(cleanup, Mapping) else {}
        if not isinstance(mask, Mapping) or not _artifact_ref_matches(
                mask, mask_artifact_id, mask_revision):
            return JobRefusal(
                STALE_ARTIFACT_REVISION,
                "cleanup review references a stale mask artifact/revision",
                {"expected": _thaw(mask),
                 "supplied": {"artifact_id": mask_artifact_id,
                              "revision": mask_revision}})
        normalized = str(decision).upper()
        if normalized not in {"APPROVE", "REJECT"}:
            return JobRefusal(INVALID_CLEANUP_RECORD,
                              "cleanup review decision must be APPROVE or REJECT")

        data = _thaw(self._snapshot.data)
        review = {"decision": normalized, "reviewer": reviewer,
                  "mask_artifact_id": mask_artifact_id,
                  "mask_revision": mask_revision,
                  "provenance": _thaw(
                      provenance or {"source": "HUMAN_REVIEW"})}
        data.setdefault("cleanup_reviews", []).append(review)
        if normalized == "REJECT":
            data.pop("foreground_cleanup", None)
            return self.transition(
                JobState.FOREGROUND_CLEANUP_REQUIRED,
                {"cleanup_rejection": stable_digest(review)}, data=data,
                provenance=provenance)

        audited = data["human_garment_audit"]["assertions"]
        front_facts = {
            "source": copy.deepcopy(data["front_source"]),
            "foreground_mask": _thaw(mask),
            "observed_assertions": [copy.deepcopy(item) for item in audited
                                    if item.get("evidence_state")
                                    == "OBSERVED_BY_HUMAN_REVIEW"],
            "proposed_assertions": [copy.deepcopy(item) for item in audited
                                    if str(item.get("evidence_state", ""))
                                    .startswith("PROPOSED")],
            "rejected_assertions": [copy.deepcopy(item) for item in audited
                                    if item.get("evidence_state")
                                    == "REJECTED_BY_HUMAN_REVIEW"],
            "reviewer": reviewer,
            "evidence_state": "OBSERVED_BY_HUMAN_REVIEW",
            "rear_inference_performed": False,
            "material_identity_confirmed": False,
        }
        data["front_facts"] = front_facts
        return self.transition(
            JobState.FRONT_FACTS_RECORDED,
            {"front_facts": stable_digest(front_facts)}, data=data,
            provenance=provenance)

    def prepare_target_2_5d(
            self, *, artifact_id: str, artifact_revision: Any,
            artifact_digest: str,
            provenance: Optional[Mapping[str, Any]] = None):
        """Bind a front-only target; rear generation remains a future stage."""
        if (not _non_empty_string(artifact_id)
                or not _non_empty_string(artifact_digest)
                or artifact_revision is None):
            return JobRefusal(MISSING_DIGEST,
                              "target 2.5D requires artifact id, revision, and digest")
        if self._snapshot.state != JobState.FRONT_FACTS_RECORDED:
            return JobRefusal(INVALID_TRANSITION,
                              "target 2.5D requires recorded front facts")
        data = _thaw(self._snapshot.data)
        data["target_2_5d"] = {
            "artifact_id": artifact_id, "revision": artifact_revision,
            "digest": artifact_digest,
            "source_front_facts_digest": stable_digest(data["front_facts"]),
            "evidence_state": "PROPOSED_FROM_APPROVED_FRONT",
            "rear_inference_performed": False,
            "provenance": _thaw(provenance or {"source": "GEOMETRY_ENGINE"}),
        }
        return self.transition(JobState.TARGET_2_5D_READY,
                               {"target_2_5d": artifact_digest}, data=data,
                               provenance=provenance)

    def future_stage_requirement(self, stage: JobState) -> JobRefusal:
        """Return the typed boundary for an intentionally future operation."""
        try:
            requested = JobState(stage)
        except (ValueError, TypeError):
            return JobRefusal(INVALID_TRANSITION, "unknown future stage",
                              {"requested": str(stage)})
        requirements = FUTURE_STAGE_REQUIREMENTS.get(requested)
        if requirements is None:
            return JobRefusal(INVALID_TRANSITION,
                              "state is not a declared future boundary",
                              {"requested": requested.value})
        return JobRefusal(
            FUTURE_STAGE_NOT_IMPLEMENTED,
            "future stage is declared but cannot be skipped or fabricated",
            {"stage": requested.value,
             "requirements": list(requirements),
             "from": self._snapshot.state.value
             if self._snapshot.state else None})

    def create_preview(self, command_id: str, after_data: Mapping[str, Any],
                       changed_addresses: Iterable[str],
                       validation_results: Iterable[Mapping[str, Any]], *,
                       provenance: Optional[Mapping[str, Any]] = None) -> Preview:
        if not command_id or not isinstance(after_data, Mapping):
            raise ValueError("preview requires command_id and mapping after_data")
        addresses = tuple(str(x) for x in changed_addresses)
        if not addresses or any(not x for x in addresses):
            raise ValueError("preview requires changed addresses")
        validations = tuple(validation_results)
        if not validations or any(not isinstance(x, Mapping) for x in validations):
            raise ValueError("preview requires validation results")
        before = self._snapshot
        after = JobSnapshot(before.state, _thaw(before.artifacts), after_data,
                            before.revision + 1)
        preview_id = stable_digest({"job_id": self.job_id,
                                    "command_id": command_id,
                                    "before": before.digest,
                                    "ordinal": len(self._previews) + 1})[:24]
        preview = Preview(preview_id, before, after, addresses, validations,
                          command_id, provenance or self._provenance)
        self._previews[preview_id] = preview
        return preview

    def approve_preview(self, preview_id: str, digest: str, *,
                        approver: str,
                        provenance: Optional[Mapping[str, Any]] = None):
        if not isinstance(approver, str) or not approver.strip():
            return JobRefusal(APPROVER_REQUIRED,
                              "approval requires a named human approver")
        preview = self._previews.get(preview_id)
        if preview is None:
            return JobRefusal(PREVIEW_NOT_FOUND, "preview id is not present",
                              {"preview_id": preview_id})
        if digest != preview.digest or self._snapshot.digest != preview.before.digest:
            return JobRefusal(APPROVAL_STALE,
                              "preview digest or active before-snapshot is stale",
                              {"supplied": digest, "expected": preview.digest,
                               "active": self._snapshot.digest,
                               "preview_before": preview.before.digest})
        failed = [v for v in preview.validation_results
                  if str(v.get("verdict", v.get("status", ""))).upper()
                  not in {"ANSWER", "PASS", "VALID", "OK"}]
        if failed:
            return JobRefusal("UNKNOWN_PREVIEW_VALIDATION_FAILED",
                              "failed validation cannot be approved",
                              {"failed": _thaw(failed)})
        before = self._snapshot
        self._applied = self._applied + (before,)
        event = self._append("PREVIEW_APPROVED", before, preview.after,
                             {"preview_id": preview_id,
                              "preview_digest": digest,
                              "approved_by": approver}, provenance)
        return event

    def reject_preview(self, preview_id: str, *, reason: str,
                       provenance: Optional[Mapping[str, Any]] = None):
        preview = self._previews.get(preview_id)
        if preview is None:
            return JobRefusal(PREVIEW_NOT_FOUND, "preview id is not present")
        before = self._snapshot
        return self._append("PREVIEW_REJECTED", before, before,
                            {"preview_id": preview_id, "reason": reason},
                            provenance)

    def undo(self, *, command_id: str,
             provenance: Optional[Mapping[str, Any]] = None):
        """Append a compensation restoring the prior applied snapshot."""
        if not self._applied:
            return JobRefusal(UNDO_EMPTY, "there is no applied change to undo")
        before = self._snapshot
        restored_source = self._applied[-1]
        self._applied = self._applied[:-1]
        restored = JobSnapshot(restored_source.state,
                               _thaw(restored_source.artifacts),
                               _thaw(restored_source.data),
                               before.revision + 1)
        return self._append("COMPENSATING_UNDO", before, restored,
                            {"command_id": command_id,
                             "restores_snapshot_digest": restored_source.digest,
                             "compensates_event_sequence": len(self._events)},
                            provenance)

    def as_dict(self) -> Dict[str, Any]:
        return {"schema": "garment.job.v1", "job_id": self.job_id,
                "snapshot": self._snapshot.as_dict(),
                "events": [e.as_dict() for e in self._events],
                "provenance": _thaw(self._provenance),
                "cross_workflow": copy.deepcopy(self._cross_workflow),
                "pending_previews": {key: value.as_dict()
                                     for key, value in sorted(self._previews.items())},
                "undo_stack": [snapshot.as_dict()
                               for snapshot in self._applied]}


# Compatibility spelling for callers that prefer the noun used by the contract.
GenerationJob = GarmentGenerationJob


def _snapshot_from_dict(value: Mapping[str, Any]) -> JobSnapshot:
    snapshot = JobSnapshot(
        JobState(value["state"]) if value.get("state") is not None else None,
        value.get("artifacts", {}), value.get("data", {}),
        int(value.get("revision", 0)))
    supplied = value.get("digest")
    if supplied is not None and supplied != snapshot.digest:
        raise ValueError("snapshot digest does not match its contents")
    return snapshot


def _preview_from_dict(value: Mapping[str, Any]) -> Preview:
    preview = Preview(
        str(value["preview_id"]), _snapshot_from_dict(value["before"]),
        _snapshot_from_dict(value["after"]),
        tuple(value.get("changed_addresses", ())),
        tuple(value.get("validation_results", ())),
        str(value["command_id"]), value.get("provenance", {}),
        schema=value.get("schema", "garment.preview.v1"))
    if value.get("digest") != preview.digest:
        raise ValueError("preview digest does not match its contents")
    return preview


def _job_from_dict(value: Mapping[str, Any]) -> GarmentGenerationJob:
    if not isinstance(value, Mapping) or value.get("schema") != "garment.job.v1":
        raise ValueError("job must be a garment.job.v1 object")
    job = GarmentGenerationJob(str(value.get("job_id", "")),
                               value.get("provenance", {}))
    job._cross_workflow = cross_workflow_harness.migrate_workflow(
        value.get("cross_workflow"), job.job_id,
        source_schema=str(value.get("schema", "garment.job.v1")))
    job._snapshot = _snapshot_from_dict(value.get("snapshot", {}))
    events = []
    for raw in value.get("events", ()):
        events.append(JobEvent(int(raw["sequence"]), str(raw["kind"]),
                               str(raw["before_digest"]),
                               str(raw["after_digest"]), raw.get("payload", {}),
                               raw.get("provenance", {})))
    if any(event.sequence != index for index, event in enumerate(events, 1)):
        raise ValueError("job event sequence is not append-only")
    if events and events[-1].after_digest != job._snapshot.digest:
        raise ValueError("job head does not match final event")
    job._events = tuple(events)
    job._previews = {str(key): _preview_from_dict(raw)
                     for key, raw in value.get("pending_previews", {}).items()}
    job._applied = tuple(_snapshot_from_dict(raw)
                         for raw in value.get("undo_stack", ()))
    return job


def new_job(job_id: Optional[str] = None) -> Dict[str, Any]:
    """Return a new JSON-serializable append-only job document."""
    identifier = job_id or ("job-" + uuid.uuid4().hex)
    return GarmentGenerationJob(identifier,
                                {"source": "HUMAN_INPUT"}).as_dict()


def _result(job: GarmentGenerationJob, outcome: Any,
            event: Optional[Mapping[str, Any]] = None, *,
            record_cross: bool = True,
            resolution_request: Optional[Mapping[str, Any]] = None
            ) -> Dict[str, Any]:
    payload = (outcome.as_dict() if hasattr(outcome, "as_dict")
               else _plain_result(outcome))
    recorded = None
    if record_cross:
        stage = (job.snapshot.state.value if job.snapshot.state is not None
                 else str((event or {}).get("kind", (event or {}).get(
                     "type", "JOB"))).upper())
        recorded = cross_workflow_harness.record_stage(
            job._cross_workflow, stage=stage, event=event or {},
            outcome=payload, provenance={"component": "generation_job"})
        job._cross_workflow = recorded["workflow"]
    out = job.as_dict()
    if isinstance(outcome, JobRefusal):
        refusal = payload
        request = (dict(resolution_request)
                   if isinstance(resolution_request, Mapping)
                   else (recorded["resolution_request"]
                         if recorded is not None else None))
        refusal["resolution_request"] = request
        out.update(refusal)
        out["result"] = refusal
        out["resolution_request"] = request
        out["resolution_requests"] = (recorded["resolution_requests"]
                                      if recorded is not None
                                      else ([request] if request else []))
        if request is not None and "typed_stop" in request:
            out["typed_stop"] = request["typed_stop"]
        elif payload.get("verdict") == "TYPED_STOP" and out[
                "cross_workflow"].get("typed_stops"):
            out["typed_stop"] = copy.deepcopy(
                out["cross_workflow"]["typed_stops"][-1])
    else:
        out["verdict"] = "ANSWER"
        out["result"] = payload
        if recorded is not None:
            out["cross_stage_record"] = recorded["stage_record"]
            if recorded["resolution_request"] is not None:
                out["resolution_request"] = recorded["resolution_request"]
                out["resolution_requests"] = recorded[
                    "resolution_requests"]
        elif isinstance(resolution_request, Mapping):
            out["resolution_request"] = dict(resolution_request)
            out["resolution_requests"] = [dict(resolution_request)]
    return out


def _plain_result(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return _thaw(value)
    return {"verdict": "UNKNOWN_UNTYPED_JOB_RESULT",
            "reason": "job result has no serialisable contract",
            "details": {"type": type(value).__name__}}


def apply(job: Mapping[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply one JSON event and return a new JSON job document.

    Supported event kinds include the original transition/preview operations
    plus the typed front-image human-audit and cleanup boundary operations.
    The input mapping is never modified.
    """
    try:
        current = _job_from_dict(job)
    except (ValueError, TypeError, KeyError) as exc:
        owner = (str(job.get("job_id", "invalid-job"))
                 if isinstance(job, Mapping) else "invalid-job")
        recorded = cross_workflow_harness.record_stage(
            cross_workflow_harness.new_workflow(
                owner or "invalid-job", source_schema="invalid-job-document"),
            stage="JOB_DOCUMENT_LOAD",
            outcome={"verdict": "UNKNOWN_INVALID_JOB_DOCUMENT",
                     "reason": str(exc), "details": {}},
            provenance={"component": "generation_job"})
        return {"schema": "garment.job.refusal.v1",
                "verdict": "UNKNOWN_INVALID_JOB_DOCUMENT",
                "reason": str(exc), "details": {},
                "cross_workflow": recorded["workflow"],
                "resolution_request": recorded["resolution_request"],
                "resolution_requests": recorded["resolution_requests"],
                "typed_stop": (recorded["resolution_request"] or {}).get(
                    "typed_stop")}
    if not isinstance(event, Mapping):
        return _result(current, JobRefusal("UNKNOWN_INVALID_JOB_EVENT",
                                           "event must be an object"), {})
    kind = str(event.get("kind", event.get("type", ""))).upper()
    provenance = event.get("provenance")
    if provenance is not None and not isinstance(provenance, Mapping):
        return _result(current, JobRefusal("UNKNOWN_INVALID_JOB_EVENT",
                                           "event provenance must be an object"),
                       event)
    cross_already_recorded = False
    request_from_cross = None
    if kind == "GRANT_LLM_PROPOSAL_CONSENT":
        granted = cross_workflow_harness.grant_model_consent(
            current._cross_workflow, scope=str(event.get("scope", "")),
            fields=event.get("fields", ()),
            granted_by=str(event.get("granted_by", event.get("by", ""))),
            expires_after_revision=event.get("expires_after_revision"),
            request_id=event.get("request_id"))
        current._cross_workflow = granted["workflow"]
        cross_already_recorded = True
        if granted["verdict"] != "ANSWER":
            request = granted.get("resolution_request", {})
            request_from_cross = request
            outcome = JobRefusal(
                str(granted["verdict"]),
                str(request.get("reason", "invalid model consent")),
                {"missing_fields": request.get("missing_fields", ())})
        else:
            before = current.snapshot
            outcome = current._append(
                "MODEL_CONSENT_RECORDED", before, before,
                {"consent_digest": granted["consent_artifact"][
                    "consent_digest"],
                 "scope": granted["consent_artifact"]["scope"]},
                provenance)
    elif kind == "RESOLVE_CROSS_OBLIGATION":
        resolved = cross_workflow_harness.resolve_request(
            current._cross_workflow,
            request_id=str(event.get("request_id", "")),
            choice=str(event.get("choice", "")),
            values=event.get("values"),
            actor=str(event.get("actor", event.get("by", ""))),
            consent_digest=event.get("consent_digest"),
            provenance=provenance)
        current._cross_workflow = resolved["workflow"]
        cross_already_recorded = True
        if str(resolved["verdict"]).startswith("UNKNOWN_"):
            request = resolved.get("resolution_request", {})
            request_from_cross = request
            outcome = JobRefusal(
                str(resolved["verdict"]),
                str(request.get("reason", "invalid Cross resolution")),
                {"missing_fields": request.get("missing_fields", ())})
        elif resolved["verdict"] == "TYPED_STOP":
            outcome = JobRefusal(
                "TYPED_STOP", "Cross obligation was explicitly stopped",
                {"resolution": resolved.get("resolution")})
        else:
            before = current.snapshot
            outcome = current._append(
                "CROSS_OBLIGATION_RESOLVED", before, before,
                {"resolution": resolved.get("resolution")}, provenance)
    elif kind in {
            "SUBMIT_PHYSICAL_CALIBRATION_DECISION",
            "SUBMIT_RECONSTRUCTION_CLAIM_DECISION",
            "SUBMIT_MANUFACTURING_FINISH_DECISION"}:
        contract_kind = {
            "SUBMIT_PHYSICAL_CALIBRATION_DECISION": "PHYSICAL_CALIBRATION",
            "SUBMIT_RECONSTRUCTION_CLAIM_DECISION": "RECONSTRUCTION_CLAIM",
            "SUBMIT_MANUFACTURING_FINISH_DECISION": "MANUFACTURING_FINISH",
        }[kind]
        admitted = cross_workflow_harness.admit_authoritative_contract(
            current._cross_workflow, contract_kind=contract_kind,
            decision=event.get("decision"), approval=event.get("approval"),
            provenance=provenance)
        current._cross_workflow = admitted["workflow"]
        cross_already_recorded = True
        request_from_cross = admitted.get("resolution_request")
        if str(admitted["verdict"]).startswith("UNKNOWN_"):
            outcome = JobRefusal(
                str(admitted["verdict"]),
                str(admitted.get("why", "contract admission failed")),
                {"contract_kind": contract_kind})
        else:
            before = current.snapshot
            outcome = current._append(
                "AUTHORITATIVE_CONTRACT_ADMITTED", before, before,
                {key: _thaw(value) for key, value in admitted.items()
                 if key not in {"workflow", "resolution_request",
                                "resolution_requests"}},
                provenance)
    elif kind in {"TRANSITION", "STATE_TRANSITION"}:
        outcome = current.transition(event.get("state"),
                                     event.get("artifacts", {}),
                                     data=event.get("data"),
                                     provenance=provenance)
    elif kind in {"AI_ANALYSIS", "AI_ANALYSIS_PROPOSED"}:
        outcome = current.record_ai_analysis(
            source_artifact_id=str(event.get("source_artifact_id", "")),
            source_revision=event.get("source_revision"),
            analysis_artifact_id=str(event.get("analysis_artifact_id", "")),
            analysis_revision=event.get("analysis_revision"),
            analysis_digest=str(event.get("analysis_digest", "")),
            assertions=event.get("assertions", ()), provenance=provenance)
    elif kind in {"REQUIRE_HUMAN_GARMENT_AUDIT",
                  "HUMAN_GARMENT_AUDIT_REQUIRED"}:
        outcome = current.require_human_garment_audit(
            analysis_artifact_id=str(event.get("analysis_artifact_id", "")),
            analysis_revision=event.get("analysis_revision"),
            provenance=provenance)
    elif kind in {"HUMAN_GARMENT_AUDIT", "SUBMIT_HUMAN_GARMENT_AUDIT"}:
        outcome = current.submit_human_garment_audit(
            analysis_artifact_id=str(event.get("analysis_artifact_id", "")),
            analysis_revision=event.get("analysis_revision"),
            reviewer=str(event.get("reviewer", "")),
            decisions=event.get("decisions", ()), provenance=provenance)
    elif kind in {"FOREGROUND_CLEANUP", "SUBMIT_FOREGROUND_CLEANUP"}:
        outcome = current.submit_foreground_cleanup(
            source_artifact_id=str(event.get("source_artifact_id", "")),
            source_revision=event.get("source_revision"),
            mask_artifact_id=str(event.get("mask_artifact_id", "")),
            mask_revision=event.get("mask_revision"),
            mask_digest=str(event.get("mask_digest", "")),
            removed_classes=event.get("removed_classes", ()),
            undo_lineage=event.get("undo_lineage", ()),
            reviewer=str(event.get("reviewer", "")), provenance=provenance)
    elif kind in {"CLEANUP_REVIEW", "REVIEW_FOREGROUND_CLEANUP"}:
        outcome = current.review_foreground_cleanup(
            mask_artifact_id=str(event.get("mask_artifact_id", "")),
            mask_revision=event.get("mask_revision"),
            reviewer=str(event.get("reviewer", "")),
            decision=str(event.get("decision", "")), provenance=provenance)
    elif kind in {"PREPARE_TARGET_2_5D", "TARGET_2_5D_READY"}:
        outcome = current.prepare_target_2_5d(
            artifact_id=str(event.get("artifact_id", "")),
            artifact_revision=event.get("artifact_revision"),
            artifact_digest=str(event.get("artifact_digest", "")),
            provenance=provenance)
    elif kind in {"FUTURE_STAGE_REQUIREMENT", "REQUIRE_FUTURE_STAGE"}:
        outcome = current.future_stage_requirement(event.get("stage"))
    elif kind in {"PREVIEW", "CREATE_PREVIEW"}:
        try:
            outcome = current.create_preview(
                str(event.get("command_id", "")),
                event.get("after_data", event.get("after", {})),
                event.get("changed_addresses", ()),
                event.get("validation_results", ()),
                provenance=provenance)
        except (ValueError, TypeError) as exc:
            outcome = JobRefusal("UNKNOWN_INVALID_PREVIEW", str(exc))
    elif kind in {"APPROVE", "PREVIEW_APPROVED"}:
        outcome = current.approve_preview(
            str(event.get("preview_id", "")), str(event.get("digest", "")),
            approver=str(event.get("approver", "")), provenance=provenance)
    elif kind in {"REJECT", "PREVIEW_REJECTED"}:
        outcome = current.reject_preview(
            str(event.get("preview_id", "")),
            reason=str(event.get("reason", "")), provenance=provenance)
    elif kind in {"UNDO", "COMPENSATING_UNDO"}:
        outcome = current.undo(command_id=str(event.get("command_id", "")),
                               provenance=provenance)
    else:
        outcome = JobRefusal("UNKNOWN_INVALID_JOB_EVENT",
                             "event kind is outside the closed vocabulary",
                             {"kind": kind})
    return _result(current, outcome, event,
                   record_cross=not cross_already_recorded,
                   resolution_request=request_from_cross)
