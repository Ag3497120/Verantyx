# -*- coding: utf-8 -*-
"""Persistable, fail-closed agent loop for image-to-garment work.

The module deliberately does not own an embedding model or an LLM.  Their
outputs cross this boundary as typed proposals.  Only deterministic geometry
checks and digest-bound named-human approvals can open later manufacturing
stages.  The returned state is JSON serialisable so MCP and the app can resume
the same loop without relying on callback or model memory.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from . import (corpus_manifest, cross_workflow_harness,
               garment_structure)


SCHEMA = "garment.factory.v1"
PROPOSED = "PROPOSED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
ANSWER = "ANSWER"
HUMAN_AUDIT = "HUMAN_AUDIT"
AUTO_PROPOSED = "AUTO_PROPOSED"
AUTO_ACCEPTED_FOR_PREVIEW = "AUTO_ACCEPTED_FOR_PREVIEW"

Runner = Callable[[Dict[str, Any], Dict[str, Any]], Mapping[str, Any]]

_PER_PART_MODALITIES = {"region_embedding", "part_embedding", "structure_embedding"}
_CONSTRUCTION_KEYS = {
    "geometry", "panel", "panels", "pattern", "patterns", "pattern_pieces",
    "seam", "seams", "seam_topology", "construction", "construction_claims",
    "construction_method", "construction_rank", "stitch_order", "stitches",
    "sewing_method", "sewing_order",
}
_AUTHORITY_KEYS = {"approval_id", "approver", "selected", "approved_by"}
_VISIBLE_FRONT_SCOPES = {
    "VISIBLE_FRONT", "FRONT_VISIBLE", "OBSERVED_FRONT", "VISIBLE",
    "VISIBLE_OBLIQUE", "OBLIQUE_VISIBLE", "OBSERVED_OBLIQUE",
}
_HUMAN_AUDIT_ACTIONS = {"ACCEPT", "REJECT", "EDIT"}
_AUDIT_MODES = {HUMAN_AUDIT, AUTO_PROPOSED}


def _audit_mode(value: Any) -> str:
    mode = str(value or HUMAN_AUDIT).strip().upper()
    if mode not in _AUDIT_MODES:
        raise ValueError(
            f"audit_mode must be {HUMAN_AUDIT!r} or {AUTO_PROPOSED!r}")
    return mode


def _source_view(event: Mapping[str, Any]) -> tuple[str, str]:
    """Normalise a declared camera view without treating it as garment fact."""
    source = event.get("source")
    source = source if isinstance(source, Mapping) else {}
    declared = str(event.get(
        "source_view", event.get(
            "view", source.get("source_view", source.get("view", "FRONT"))))
    ).strip().upper().replace("-", "_").replace(" ", "_")
    if any(token in declared for token in (
            "OBLIQUE", "THREE_QUARTER", "3/4", "DIAGONAL")):
        return "OBLIQUE", declared
    return "FRONT", declared or "FRONT"


def _view_authority(mode: str, evidence_state: str,
                    source_view: str, declared_view: str) -> Dict[str, Any]:
    automatic = mode == AUTO_PROPOSED
    return {
        "view": source_view,
        "declared_view": declared_view,
        "state": PROPOSED if automatic else evidence_state,
        "authority": (AUTO_ACCEPTED_FOR_PREVIEW if automatic else
                      ("OBSERVED_SOURCE_IMAGE" if evidence_state == "OBSERVED"
                       else "PROPOSED_SOURCE_IMAGE")),
        "front_visible": True,
        "oblique_visible": source_view == "OBLIQUE",
        "manufacturing_ready": False,
        "industrial_strength_guarantee": False,
    }


def _apply_audit_mode(state: Dict[str, Any], mode: str) -> None:
    state["audit_mode"] = mode
    contract = state.setdefault("truth_contract", {})
    contract["audit_mode"] = mode
    # Candidate/material approvals retain their existing named-human contract;
    # only the initial visible-part audit and cleanup adoption vary by mode.
    contract["approval"] = "named human + exact semantic digest"
    contract["initial_review"] = (
        "named human + exact analysis/target digest"
        if mode == HUMAN_AUDIT else AUTO_ACCEPTED_FOR_PREVIEW)
    contract["automatic_authority_ceiling"] = (
        AUTO_ACCEPTED_FOR_PREVIEW if mode == AUTO_PROPOSED else None)
    contract["model_and_retrieval_outputs"] = PROPOSED
    contract["scores_are_not_facts"] = True
    contract["manufacturing_certification"] = False
    contract["industrial_strength_guarantee"] = False


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "as_dict"):
        return _plain(value.as_dict())
    raise TypeError(f"value is not JSON serialisable: {type(value).__name__}")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _proposal_safe(value: Any) -> Any:
    """Keep model claims inspectable while removing authority vocabulary."""
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            name = "claimed_evidence" if str(key) == "evidence" else str(key)
            if name in _AUTHORITY_KEYS:
                name = "claimed_" + name
            if name in ("state", "kind", "verdict") and str(item).upper() in {
                    "OBSERVED", "ANSWER", "APPROVED", "PASS", "CONVERGED"}:
                out[name] = PROPOSED
            else:
                out[name] = _proposal_safe(item)
        return out
    if isinstance(value, (tuple, list)):
        return [_proposal_safe(v) for v in value]
    return copy.deepcopy(value)


def _unknown(state: Mapping[str, Any], code: str, why: str, **detail: Any) -> Dict[str, Any]:
    current = copy.deepcopy(dict(state))
    owner = str(current.get("job_id", "factory-job"))
    workflow = cross_workflow_harness.migrate_workflow(
        current.get("cross_workflow"), owner,
        source_schema=str(current.get("schema", SCHEMA)))
    recorded = cross_workflow_harness.record_stage(
        workflow, stage=str(current.get("phase", "FACTORY")),
        outcome={"verdict": code, "why": why, **_plain(detail)},
        provenance={"component": "garment_factory"})
    current["cross_workflow"] = recorded["workflow"]
    result = {"verdict": code, "why": why, "state": current, **detail}
    result["resolution_request"] = recorded["resolution_request"]
    result["resolution_requests"] = recorded["resolution_requests"]
    if (recorded["resolution_request"] is not None
            and "typed_stop" in recorded["resolution_request"]):
        result["typed_stop"] = recorded["resolution_request"]["typed_stop"]
    return result


def _accepted(state: Dict[str, Any], event: Mapping[str, Any],
              verdict: str = ANSWER, *, record_cross: bool = True,
              **detail: Any) -> Dict[str, Any]:
    recorded = None
    if record_cross:
        owner = str(state.get("job_id", "factory-job"))
        workflow = cross_workflow_harness.migrate_workflow(
            state.get("cross_workflow"), owner,
            source_schema=str(state.get("schema", SCHEMA)))
        recorded = cross_workflow_harness.record_stage(
            workflow, stage=str(state.get("phase", "FACTORY")),
            event=event, outcome={"verdict": verdict, **_plain(detail)},
            provenance={"component": "garment_factory"})
        state["cross_workflow"] = recorded["workflow"]
    state["events"].append({
        "sequence": len(state["events"]) + 1,
        "type": str(event.get("type", "")),
        "phase": state["phase"],
        "state_digest": _digest({k: v for k, v in state.items() if k != "events"}),
    })
    result = {"verdict": verdict, "state": state, **detail}
    if recorded is not None:
        result["cross_stage_record"] = recorded["stage_record"]
        if recorded["resolution_request"] is not None:
            result["resolution_request"] = recorded["resolution_request"]
            result["resolution_requests"] = recorded["resolution_requests"]
    return result


def _approval_candidate(state: Mapping[str, Any], *, material: bool = False) -> Optional[Mapping[str, Any]]:
    sheet_name = "material_sheet" if material else "hypothesis_sheet"
    approval_name = "material_approval" if material else "shape_approval"
    sheet = state.get(sheet_name)
    approval = state.get(approval_name)
    if not isinstance(sheet, Mapping) or not isinstance(approval, Mapping):
        return None
    if approval.get("state") != APPROVED or approval.get("comparison_digest") != sheet.get("comparison_digest"):
        return None
    candidate = next((row for row in sheet.get("candidates", ())
                      if row.get("candidate_id") == approval.get("candidate_id")), None)
    if not isinstance(candidate, Mapping) or candidate.get("digest") != approval.get("candidate_digest"):
        return None
    expected = {"state": APPROVED, "by": approval.get("by"),
                "candidate_id": approval.get("candidate_id"),
                "candidate_digest": approval.get("candidate_digest"),
                "comparison_digest": approval.get("comparison_digest")}
    return candidate if approval.get("approval_id") == _digest(expected) else None


def _clear_downstream(state: Dict[str, Any], *, from_retrieval: bool = False) -> None:
    if from_retrieval:
        state["hypothesis_sheet"] = None
        state["hybrid_retrieval"] = None
    for key in ("shape_approval", "pattern", "repair", "material_sheet",
                "material_approval", "simulation", "sewing"):
        state[key] = None


def _cad_target_iteration_binding(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Bind a derived pattern to one adopted CAD target revision.

    The current deterministic compiler consumes the reviewed structure graph;
    it does not prove an arbitrary sculpted 3D surface can be flattened into a
    manufacturing-grade 2D pattern.  Keeping that limitation inside the
    artifact prevents a later agent or UI from mistaking revision lineage for
    a certified inverse solve.
    """
    cleanup = state.get("foreground_cleanup")
    if not isinstance(cleanup, Mapping):
        return {
            "schema": "garment.cad-target-iteration-binding.v1",
            "state": "UNKNOWN",
            "verdict": "UNKNOWN_CAD_TARGET_NOT_ADOPTED",
            "why": "this compatibility job has no adopted CAD target revision",
            "target_geometry_compiled_into_pattern": False,
            "inverse_flattening": {
                "verdict": "UNKNOWN_NOT_PROVEN",
                "manufacturing_certified": False,
            },
        }
    binding = {
        "schema": "garment.cad-target-iteration-binding.v1",
        "state": (APPROVED if cleanup.get("state") == APPROVED else PROPOSED),
        "authority": cleanup.get("authority"),
        "target_digest": cleanup.get("target_digest"),
        "target_revision": cleanup.get("target_revision"),
        "cleanup_digest": cleanup.get("cleanup_digest"),
        "supersedes_cleanup_digest": cleanup.get(
            "supersedes_cleanup_digest"),
        "source_front_audit_digest": cleanup.get("audit_digest"),
        "front_compilation_digest": (
            state.get("front_compilation", {}).get("compiled_front_digest")
            if isinstance(state.get("front_compilation"), Mapping) else None),
        "target_geometry_compiled_into_pattern": False,
        "recompile_and_redress_required_for_new_revision": True,
        "inverse_flattening": {
            "verdict": "UNKNOWN_NOT_PROVEN",
            "why": ("arbitrary edited 3D surface to manufacturing-grade 2D "
                    "pattern inversion is not implemented or certified"),
            "manufacturing_certified": False,
        },
    }
    binding["binding_digest"] = _digest(binding)
    return binding


def _archive_active_foreground_cleanup(state: Dict[str, Any]) -> None:
    """Move an active cleanup into the append-only history before a restart."""
    active = state.get("foreground_cleanup")
    history = state.setdefault("foreground_cleanup_history", [])
    if not isinstance(active, Mapping) or not isinstance(history, list):
        return
    digest = active.get("cleanup_digest")
    if not any(isinstance(row, Mapping)
               and row.get("cleanup_digest") == digest for row in history):
        history.append(copy.deepcopy(dict(active)))


def _front_observable(assertion: Mapping[str, Any]) -> bool:
    """Whether a named front reviewer may promote this one visible claim."""
    scope = str(assertion.get(
        "evidence_scope", assertion.get("visibility", "VISIBLE_FRONT"))).upper()
    field = str(assertion.get(
        "field", assertion.get("predicate", assertion.get("kind", "")))).lower()
    category = str(assertion.get("category", "")).lower()
    if scope not in _VISIBLE_FRONT_SCOPES:
        return False
    blocked = ("rear", "back_", "hidden", "occluded", "material", "fabric",
               "fiber", "fibre", "sewing", "stitch", "manufactur", "comfort",
               "pressure", "strength")
    return (not any(token in field for token in blocked)
            and category not in {"rear", "hidden", "material", "material_identity",
                                 "sewing", "manufacturing", "physical_fit"})


def _analysis_assertion_id(row: Mapping[str, Any], index: int) -> str:
    for key in ("assertion_id", "inventory_part_id", "part_id", "region_id", "node_id"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return f"visible-front-{index + 1}-{_digest(row)[:12]}"


def _auto_accept_visible_analysis(state: Dict[str, Any],
                                  event: Mapping[str, Any]) -> Dict[str, Any]:
    """Adopt AI rows for preview without promoting a single row to fact."""
    analysis = state.get("visible_ai_analysis")
    if not isinstance(analysis, Mapping):
        return _unknown(state, "UNKNOWN_AI_VISIBLE_ANALYSIS_REQUIRED",
                        "record the AI proposal before automatic audit")
    if state.get("audit_mode") != AUTO_PROPOSED:
        return _unknown(state, "UNKNOWN_FACTORY_EVENT",
                        "automatic audit is only available in AUTO_PROPOSED mode")
    rows = []
    for raw in analysis.get("assertions", ()):
        if not isinstance(raw, Mapping):
            continue
        row = copy.deepcopy(dict(raw))
        row["review_action"] = "AUTO_ACCEPT_FOR_PREVIEW"
        row["auto_actor"] = str(event.get("actor", "VERA_AUTO_AUDIT"))
        row["authority"] = AUTO_ACCEPTED_FOR_PREVIEW
        row["evidence_state"] = AUTO_ACCEPTED_FOR_PREVIEW
        row["state"] = PROPOSED
        row["fact"] = False
        rows.append(row)
    audit = {
        "state": PROPOSED,
        "audit_mode": AUTO_PROPOSED,
        "authority": AUTO_ACCEPTED_FOR_PREVIEW,
        "actor": str(event.get("actor", "VERA_AUTO_AUDIT")),
        "analysis_digest": analysis.get("analysis_digest"),
        "assertions": rows,
        "view_authority": copy.deepcopy(analysis.get("view_authority")),
        "fact_promotions": [],
        "rear_inference_performed": False,
        "material_identity_confirmed": False,
        "manufacturing_ready": False,
        "manufacturing_certification": False,
        "industrial_strength_guarantee": False,
    }
    audit["audit_digest"] = _digest(audit)
    state["auto_visible_audit"] = audit
    state["visible_audit"] = audit
    state["human_visible_audit"] = None
    state["front_facts"] = {
        "state": PROPOSED,
        "audit_mode": AUTO_PROPOSED,
        "authority": AUTO_ACCEPTED_FOR_PREVIEW,
        "audit_digest": audit["audit_digest"],
        "view_authority": copy.deepcopy(audit.get("view_authority")),
        "observed_assertions": [],
        "proposed_assertions": rows,
        "rejected_assertions": [],
        "fact_promotions": [],
        "rear_inference_performed": False,
        "material_identity_confirmed": False,
        "manufacturing_ready": False,
        "manufacturing_certification": False,
        "industrial_strength_guarantee": False,
    }
    state["foreground_cleanup"] = None
    state["phase"] = "FOREGROUND_CLEANUP_REQUIRED"
    return _accepted(state, event, verdict=PROPOSED, audit=audit,
                     front_facts=state["front_facts"])


def _record_ai_visible_analysis(state: Dict[str, Any],
                                event: Mapping[str, Any]) -> Dict[str, Any]:
    """Persist the VLM/retrieval interpretation as proposals before geometry."""
    if state.get("image_evidence") is None:
        return _unknown(state, "UNKNOWN_IMAGE_CONFIRMATION_REQUIRED",
                        "confirm the source image before recording AI analysis")
    rows = event.get("assertions", event.get("inventory"))
    if (not isinstance(rows, Sequence) or isinstance(rows, (str, bytes))
            or not rows):
        return _unknown(state, "UNKNOWN_AI_VISIBLE_ANALYSIS_REQUIRED",
                        "a non-empty visible-front assertion list is required")
    source_view = str(state["image_evidence"].get("source_view", "FRONT"))
    default_scope = ("VISIBLE_OBLIQUE" if source_view == "OBLIQUE"
                     else "VISIBLE_FRONT")
    assertions = []
    ids = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            return _unknown(state, "UNKNOWN_AI_VISIBLE_ASSERTION",
                            f"assertion {index} is not an object")
        safe = _proposal_safe(raw)
        assertion_id = _analysis_assertion_id(safe, index)
        if assertion_id in ids:
            return _unknown(state, "UNKNOWN_AI_VISIBLE_ASSERTION_ID",
                            "AI assertion ids must be unique", assertion_id=assertion_id)
        ids.add(assertion_id)
        safe["assertion_id"] = assertion_id
        safe["state"] = PROPOSED
        safe["evidence_scope"] = str(
            safe.get("evidence_scope", default_scope)).upper()
        safe["fact"] = False
        assertions.append(safe)
    analysis = {
        "state": PROPOSED,
        "authority": "AI_GENERATED_PROPOSAL",
        "audit_mode": state.get("audit_mode", HUMAN_AUDIT),
        "assertions": assertions,
        "source_image_digest": _digest(state["image_evidence"]),
        "view_authority": copy.deepcopy(
            state["image_evidence"].get("view_authority")),
        "model": _proposal_safe(event.get("model", {})),
        "retrieval": _proposal_safe(event.get("retrieval", {})),
        "rear_inference_performed": False,
        "material_identity_observed": False,
        "fact_promotions": [],
    }
    cleanup_proposal = event.get(
        "foreground_cleanup", event.get("cleanup_proposal"))
    if isinstance(cleanup_proposal, Mapping):
        analysis["foreground_cleanup_proposal"] = _proposal_safe(
            cleanup_proposal)
    analysis["analysis_digest"] = _digest(analysis)
    state["visible_ai_analysis"] = analysis
    state["human_visible_audit"] = None
    state["auto_visible_audit"] = None
    state["visible_audit"] = None
    state["front_facts"] = None
    _archive_active_foreground_cleanup(state)
    state["foreground_cleanup"] = None
    state["front_compilation"] = None
    state["retrieval_batches"] = []
    _clear_downstream(state, from_retrieval=True)
    state["phase"] = "HUMAN_GARMENT_AUDIT_REQUIRED"
    recorded = _accepted(state, event, verdict=PROPOSED, analysis=analysis)
    if state.get("audit_mode") != AUTO_PROPOSED:
        return recorded
    audited = _auto_accept_visible_analysis(recorded["state"], {
        "type": "AUTO_ACCEPT_VISIBLE_AUDIT",
        "actor": "VERA_AUTO_AUDIT",
        "analysis_digest": analysis["analysis_digest"],
    })
    audited["analysis"] = analysis
    if not isinstance(cleanup_proposal, Mapping):
        return audited
    cleanup_event = {**_plain(cleanup_proposal),
                     "type": "SUBMIT_FOREGROUND_CLEANUP",
                     "actor": "VERA_AUTO_AUDIT"}
    cleaned = _submit_auto_foreground_cleanup(audited["state"], cleanup_event)
    cleaned["analysis"] = analysis
    cleaned["audit"] = audited.get("audit")
    return cleaned


def _submit_human_visible_audit(state: Dict[str, Any],
                                event: Mapping[str, Any]) -> Dict[str, Any]:
    analysis = state.get("visible_ai_analysis")
    if not isinstance(analysis, Mapping):
        return _unknown(state, "UNKNOWN_AI_VISIBLE_ANALYSIS_REQUIRED",
                        "record the AI proposal before human audit")
    reviewer = str(event.get("reviewer", event.get("by", ""))).strip()
    if not reviewer:
        return _unknown(state, "UNKNOWN_NAMED_HUMAN_REVIEWER_REQUIRED",
                        "visible-front audit requires a named human")
    received_digest = str(event.get("analysis_digest", ""))
    if received_digest != analysis.get("analysis_digest"):
        return _unknown(state, "UNKNOWN_HUMAN_GARMENT_AUDIT_STALE",
                        "the audited AI analysis digest changed",
                        expected=analysis.get("analysis_digest"),
                        received=received_digest)
    decisions = event.get("decisions")
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
        return _unknown(state, "UNKNOWN_INVALID_HUMAN_GARMENT_AUDIT",
                        "decisions must audit every AI assertion")
    proposals = {str(row["assertion_id"]): row
                 for row in analysis.get("assertions", ())
                 if isinstance(row, Mapping) and row.get("assertion_id")}
    audited = {}
    for index, decision in enumerate(decisions):
        if not isinstance(decision, Mapping):
            return _unknown(state, "UNKNOWN_INVALID_HUMAN_GARMENT_AUDIT",
                            f"decision {index} is not an object")
        assertion_id = str(decision.get("assertion_id", "")).strip()
        action = str(decision.get("action", "")).upper()
        if assertion_id not in proposals or assertion_id in audited or action not in _HUMAN_AUDIT_ACTIONS:
            return _unknown(state, "UNKNOWN_INVALID_HUMAN_GARMENT_AUDIT",
                            "every known assertion needs one ACCEPT, REJECT, or EDIT decision",
                            assertion_id=assertion_id, action=action)
        row = copy.deepcopy(dict(proposals[assertion_id]))
        ai_proposal = copy.deepcopy(row)
        if action == "EDIT":
            edits = decision.get("edits")
            if not isinstance(edits, Mapping) or not edits:
                return _unknown(state, "UNKNOWN_INVALID_HUMAN_GARMENT_AUDIT",
                                "EDIT requires a non-empty edits object",
                                assertion_id=assertion_id)
            edits = _proposal_safe(edits)
            edits.pop("assertion_id", None)
            row.update(edits)
        row["assertion_id"] = assertion_id
        row["review_action"] = action
        row["reviewer"] = reviewer
        row["ai_proposal"] = ai_proposal
        if action == "REJECT":
            row["evidence_state"] = "REJECTED_BY_HUMAN_REVIEW"
            row["fact"] = False
        elif _front_observable(row):
            row["evidence_state"] = "OBSERVED_BY_HUMAN_REVIEW"
            row["fact"] = True
        else:
            row["evidence_state"] = "PROPOSED_AFTER_HUMAN_REVIEW"
            row["fact"] = False
        audited[assertion_id] = row
    if set(audited) != set(proposals):
        return _unknown(state, "UNKNOWN_INVALID_HUMAN_GARMENT_AUDIT",
                        "every AI assertion must be explicitly audited",
                        missing=sorted(set(proposals) - set(audited)))
    audited_rows = [audited[str(row["assertion_id"])]
                    for row in analysis["assertions"]]
    audit = {
        "state": APPROVED,
        "audit_mode": HUMAN_AUDIT,
        "authority": "HUMAN_REVIEWED_VISIBLE_SOURCE",
        "reviewer": reviewer,
        "analysis_digest": received_digest,
        "assertions": audited_rows,
        "view_authority": copy.deepcopy(analysis.get("view_authority")),
        "rear_inference_performed": False,
        "material_identity_confirmed": False,
        "manufacturing_ready": False,
    }
    audit["audit_digest"] = _digest(audit)
    state["human_visible_audit"] = audit
    state["auto_visible_audit"] = None
    state["visible_audit"] = audit
    state["front_facts"] = {
        "state": "OBSERVED_BY_HUMAN_REVIEW",
        "audit_mode": HUMAN_AUDIT,
        "authority": "HUMAN_REVIEWED_VISIBLE_SOURCE",
        "audit_digest": audit["audit_digest"],
        "view_authority": copy.deepcopy(analysis.get("view_authority")),
        "observed_assertions": [row for row in audited_rows if row.get("fact") is True],
        "proposed_assertions": [row for row in audited_rows
                                if row.get("evidence_state") == "PROPOSED_AFTER_HUMAN_REVIEW"],
        "rejected_assertions": [row for row in audited_rows
                                if row.get("evidence_state") == "REJECTED_BY_HUMAN_REVIEW"],
        "rear_inference_performed": False,
        "material_identity_confirmed": False,
        "manufacturing_ready": False,
    }
    state["foreground_cleanup"] = None
    state["phase"] = "FOREGROUND_CLEANUP_REQUIRED"
    return _accepted(state, event, verdict=APPROVED, audit=audit,
                     front_facts=state["front_facts"])


def _submit_auto_foreground_cleanup(state: Dict[str, Any],
                                    event: Mapping[str, Any]) -> Dict[str, Any]:
    """Adopt a model mask for comparison only, never as observed geometry."""
    audit = state.get("auto_visible_audit")
    if state.get("audit_mode") != AUTO_PROPOSED:
        return _unknown(state, "UNKNOWN_FACTORY_EVENT",
                        "automatic cleanup is only available in AUTO_PROPOSED mode")
    if not isinstance(audit, Mapping):
        return _unknown(state, "UNKNOWN_HUMAN_GARMENT_AUDIT_REQUIRED",
                        "complete visible-part audit before target cleanup")
    target_digest = str(event.get("target_digest", "")).strip()
    target_revision = event.get("target_revision")
    if (not target_digest or isinstance(target_revision, bool)
            or not isinstance(target_revision, int) or target_revision < 0):
        return _unknown(state, "UNKNOWN_INVALID_FOREGROUND_CLEANUP_RECORD",
                        "target_digest and a non-negative integer target_revision are required")
    removed_regions = event.get("removed_region_ids", ())
    removed_faces = event.get("removed_face_indices", ())
    undo_lineage = event.get("undo_parent_digests", ())
    if (not isinstance(removed_regions, Sequence) or isinstance(removed_regions, (str, bytes))
            or any(not str(value).strip() for value in removed_regions)
            or not isinstance(removed_faces, Sequence) or isinstance(removed_faces, (str, bytes))
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0
                   for value in removed_faces)
            or not isinstance(undo_lineage, Sequence) or isinstance(undo_lineage, (str, bytes))
            or any(not str(value).strip() for value in undo_lineage)):
        return _unknown(state, "UNKNOWN_INVALID_FOREGROUND_CLEANUP_RECORD",
                        "cleanup selections and undo lineage must be typed arrays")
    previous = state.get("foreground_cleanup")
    if isinstance(previous, Mapping):
        previous_revision = previous.get("target_revision")
        previous_target_digest = str(previous.get("target_digest", ""))
        if (isinstance(previous_revision, bool)
                or not isinstance(previous_revision, int)):
            return _unknown(
                state, "UNKNOWN_FACTORY_STATE",
                "the persisted foreground cleanup has no integer revision")
        if target_revision < previous_revision:
            return _unknown(
                state, "UNKNOWN_FOREGROUND_CLEANUP_STALE_REVISION",
                "a CAD target revision cannot move backwards",
                expected_minimum=previous_revision,
                received=target_revision)
        if target_revision == previous_revision:
            if target_digest == previous_target_digest:
                return {
                    "verdict": PROPOSED,
                    "state": state,
                    "cleanup": copy.deepcopy(dict(previous)),
                    "front_facts": copy.deepcopy(state.get("front_facts")),
                    "idempotent": True,
                }
            return _unknown(
                state, "UNKNOWN_FOREGROUND_CLEANUP_STALE_REVISION",
                "one CAD target revision cannot name two different digests",
                expected_digest=previous_target_digest,
                received_digest=target_digest)
    cleanup = {
        "state": PROPOSED,
        "audit_mode": AUTO_PROPOSED,
        "authority": AUTO_ACCEPTED_FOR_PREVIEW,
        "actor": str(event.get("actor", "VERA_AUTO_AUDIT")),
        "target_digest": target_digest,
        "target_revision": target_revision,
        "removed_region_ids": sorted(set(map(str, removed_regions))),
        "removed_face_indices": sorted(set(removed_faces)),
        "undo_parent_digests": list(map(str, undo_lineage)),
        "audit_digest": audit.get("audit_digest"),
        "view_authority": copy.deepcopy(audit.get("view_authority")),
        "rear_inference_performed": False,
        "accepted_for_front_comparison": True,
        "fact_promotions": [],
        "manufacturing_ready": False,
        "manufacturing_certification": False,
        "industrial_strength_guarantee": False,
    }
    history = state.setdefault("foreground_cleanup_history", [])
    if not isinstance(history, list):
        return _unknown(
            state, "UNKNOWN_FACTORY_STATE",
            "foreground_cleanup_history must be an append-only list")
    cleanup["iteration"] = len(history) + (2 if isinstance(previous, Mapping) else 1)
    if isinstance(previous, Mapping):
        cleanup["supersedes_cleanup_digest"] = previous.get(
            "cleanup_digest")
    cleanup["cleanup_digest"] = _digest(cleanup)
    if isinstance(previous, Mapping):
        history.append(copy.deepcopy(dict(previous)))
        # A newly adopted CAD target invalidates every artifact that was
        # derived from the earlier surface. Keep the reviewed visible facts,
        # then reopen compilation/retrieval so 3D, pattern, simulation and
        # sewing are regenerated and redressed against this exact digest.
        state["front_compilation"] = None
        state["retrieval_batches"] = []
        _clear_downstream(state, from_retrieval=True)
        state["iteration"] = 0
    state["foreground_cleanup"] = cleanup
    state["phase"] = "FRONT_FACTS_RECORDED"
    return _accepted(state, event, verdict=PROPOSED, cleanup=cleanup,
                     front_facts=state.get("front_facts"))


def _submit_foreground_cleanup(state: Dict[str, Any],
                               event: Mapping[str, Any]) -> Dict[str, Any]:
    audit = state.get("human_visible_audit")
    if not isinstance(audit, Mapping):
        return _unknown(state, "UNKNOWN_HUMAN_GARMENT_AUDIT_REQUIRED",
                        "complete visible-front audit before target cleanup")
    reviewer = str(event.get("reviewer", event.get("by", ""))).strip()
    target_digest = str(event.get("target_digest", "")).strip()
    target_revision = event.get("target_revision")
    if not reviewer:
        return _unknown(state, "UNKNOWN_NAMED_HUMAN_REVIEWER_REQUIRED",
                        "foreground cleanup adoption requires a named human")
    if (not target_digest or isinstance(target_revision, bool)
            or not isinstance(target_revision, int) or target_revision < 0):
        return _unknown(state, "UNKNOWN_INVALID_FOREGROUND_CLEANUP_RECORD",
                        "target_digest and a non-negative integer target_revision are required")
    removed_regions = event.get("removed_region_ids", ())
    removed_faces = event.get("removed_face_indices", ())
    undo_lineage = event.get("undo_parent_digests", ())
    if (not isinstance(removed_regions, Sequence) or isinstance(removed_regions, (str, bytes))
            or any(not str(value).strip() for value in removed_regions)
            or not isinstance(removed_faces, Sequence) or isinstance(removed_faces, (str, bytes))
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0
                   for value in removed_faces)
            or not isinstance(undo_lineage, Sequence) or isinstance(undo_lineage, (str, bytes))
            or any(not str(value).strip() for value in undo_lineage)):
        return _unknown(state, "UNKNOWN_INVALID_FOREGROUND_CLEANUP_RECORD",
                        "cleanup selections and undo lineage must be typed arrays")
    previous = state.get("foreground_cleanup")
    if isinstance(previous, Mapping):
        previous_revision = previous.get("target_revision")
        previous_target_digest = str(previous.get("target_digest", ""))
        if (isinstance(previous_revision, bool)
                or not isinstance(previous_revision, int)):
            return _unknown(
                state, "UNKNOWN_FACTORY_STATE",
                "the persisted foreground cleanup has no integer revision")
        if target_revision < previous_revision:
            return _unknown(
                state, "UNKNOWN_FOREGROUND_CLEANUP_STALE_REVISION",
                "a CAD target revision cannot move backwards",
                expected_minimum=previous_revision,
                received=target_revision)
        if target_revision == previous_revision:
            if target_digest == previous_target_digest:
                return {
                    "verdict": APPROVED,
                    "state": state,
                    "cleanup": copy.deepcopy(dict(previous)),
                    "front_facts": copy.deepcopy(state.get("front_facts")),
                    "idempotent": True,
                }
            return _unknown(
                state, "UNKNOWN_FOREGROUND_CLEANUP_STALE_REVISION",
                "one CAD target revision cannot name two different digests",
                expected_digest=previous_target_digest,
                received_digest=target_digest)
    cleanup = {
        "state": APPROVED,
        "audit_mode": HUMAN_AUDIT,
        "authority": "HUMAN_APPROVED_FOR_FRONT_COMPARISON",
        "reviewer": reviewer,
        "target_digest": target_digest,
        "target_revision": target_revision,
        "removed_region_ids": sorted(set(map(str, removed_regions))),
        "removed_face_indices": sorted(set(removed_faces)),
        "undo_parent_digests": list(map(str, undo_lineage)),
        "audit_digest": audit.get("audit_digest"),
        "view_authority": copy.deepcopy(audit.get("view_authority")),
        "rear_inference_performed": False,
        "accepted_for_front_comparison": True,
        "manufacturing_ready": False,
        "manufacturing_certification": False,
        "industrial_strength_guarantee": False,
    }
    history = state.setdefault("foreground_cleanup_history", [])
    if not isinstance(history, list):
        return _unknown(
            state, "UNKNOWN_FACTORY_STATE",
            "foreground_cleanup_history must be an append-only list")
    cleanup["iteration"] = len(history) + (2 if isinstance(previous, Mapping) else 1)
    if isinstance(previous, Mapping):
        cleanup["supersedes_cleanup_digest"] = previous.get(
            "cleanup_digest")
    cleanup["cleanup_digest"] = _digest(cleanup)
    if isinstance(previous, Mapping):
        history.append(copy.deepcopy(dict(previous)))
        # A newly adopted CAD target invalidates every artifact that was
        # derived from the earlier surface. Keep the reviewed visible facts,
        # then reopen compilation/retrieval so 3D, pattern, simulation and
        # sewing are regenerated and redressed against this exact digest.
        state["front_compilation"] = None
        state["retrieval_batches"] = []
        _clear_downstream(state, from_retrieval=True)
        state["iteration"] = 0
    state["foreground_cleanup"] = cleanup
    state["phase"] = "FRONT_FACTS_RECORDED"
    return _accepted(state, event, verdict=APPROVED, cleanup=cleanup,
                     front_facts=state.get("front_facts"))


def _open_retrieval_after_front_review(state: Dict[str, Any],
                                       event: Mapping[str, Any]) -> Dict[str, Any]:
    if (state.get("phase") != "FRONT_FACTS_RECORDED"
            or not isinstance(state.get("front_facts"), Mapping)
            or not isinstance(state.get("foreground_cleanup"), Mapping)):
        return _unknown(state, "UNKNOWN_REVIEWED_FRONT_FACTS_REQUIRED",
                        "mode-audited front claims and adopted cleanup are required")
    compilation_digest = str(event.get("compiled_front_digest", "")).strip()
    candidate_count = event.get("candidate_count")
    if (not compilation_digest or isinstance(candidate_count, bool)
            or not isinstance(candidate_count, int) or candidate_count < 2):
        return _unknown(state, "UNKNOWN_REVIEWED_FRONT_COMPILATION_REQUIRED",
                        "at least two compiled proposal candidates and their digest are required")
    state["front_compilation"] = {
        "state": PROPOSED,
        "audit_mode": state.get("audit_mode", HUMAN_AUDIT),
        "authority": state["front_facts"].get(
            "authority", "HUMAN_REVIEWED_VISIBLE_SOURCE"),
        "compiled_front_digest": compilation_digest,
        "candidate_count": candidate_count,
        "audit_digest": state["front_facts"].get("audit_digest"),
        "cleanup_digest": state["foreground_cleanup"].get("cleanup_digest"),
        "rear_inference_performed": False,
        "manufacturing_ready": False,
        "manufacturing_certification": False,
        "industrial_strength_guarantee": False,
    }
    state["phase"] = "REGIONS_CONFIRMED"
    return _accepted(state, event, verdict=PROPOSED,
                     front_compilation=state["front_compilation"])


def _candidate_ready_phase(state: Mapping[str, Any]) -> str:
    sheet = state.get("hypothesis_sheet")
    return ("BACK_CANDIDATES_READY"
            if isinstance(sheet, Mapping) and bool(sheet.get("front_only", True))
            else "STRUCTURE_CANDIDATES_READY")


def _shape_decisions(state: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    rows = state.get("shape_decisions", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _compensated_shape_decisions(state: Mapping[str, Any]) -> set[str]:
    return {
        str(row.get("compensates_decision_id"))
        for row in _shape_decisions(state)
        if row.get("action") == "UNDO" and row.get("compensates_decision_id")
    }


def _active_shape_decisions(state: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    sheet = state.get("hypothesis_sheet")
    comparison_digest = (sheet.get("comparison_digest")
                         if isinstance(sheet, Mapping) else None)
    compensated = _compensated_shape_decisions(state)
    return tuple(
        row for row in _shape_decisions(state)
        if row.get("action") in {"APPROVE", "REJECT"}
        and row.get("decision_id") not in compensated
        and row.get("comparison_digest") == comparison_digest
    )


def _active_shape_rejection(state: Mapping[str, Any], candidate_id: str,
                            candidate_digest: str) -> Optional[Mapping[str, Any]]:
    return next((row for row in reversed(_active_shape_decisions(state))
                 if row.get("action") == "REJECT"
                 and row.get("candidate_id") == candidate_id
                 and row.get("candidate_digest") == candidate_digest), None)


def _append_shape_decision(state: Dict[str, Any], action: str,
                           payload: Mapping[str, Any]) -> Dict[str, Any]:
    ordinal = len(state["shape_decisions"]) + 1
    decision = {"action": action, "ordinal": ordinal, **_plain(payload)}
    decision["decision_id"] = _digest(decision)
    state["shape_decisions"].append(decision)
    return decision


def new_job(job_id: str, max_iterations: int = 8,
            audit_mode: str = HUMAN_AUDIT) -> Dict[str, Any]:
    """Create a factory job.

    ``HUMAN_AUDIT`` preserves the digest-bound human gates.  In
    ``AUTO_PROPOSED`` the same phases are traversed automatically when AI
    proposals are supplied, but their maximum authority remains
    ``AUTO_ACCEPTED_FOR_PREVIEW``.
    """
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job_id must be a non-empty string")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ValueError("max_iterations must be a positive integer")
    mode = _audit_mode(audit_mode)
    return {
        "schema": SCHEMA,
        "job_id": job_id.strip(),
        "audit_mode": mode,
        "phase": "EMPTY",
        "iteration": 0,
        "max_iterations": max_iterations,
        "image_evidence": None,
        "visible_ai_analysis": None,
        "visible_audit": None,
        "human_visible_audit": None,
        "auto_visible_audit": None,
        "front_facts": None,
        "foreground_cleanup": None,
        "foreground_cleanup_history": [],
        "front_compilation": None,
        "retrieval_batches": [],
        "hybrid_retrieval": None,
        "hypothesis_sheet": None,
        "shape_approval": None,
        "shape_decisions": [],
        "pattern": None,
        "repair": None,
        "material_sheet": None,
        "material_approval": None,
        "simulation": None,
        "sewing": None,
        "events": [],
        "cross_workflow": cross_workflow_harness.new_workflow(
            job_id.strip(), source_schema=SCHEMA),
        "truth_contract": {
            "model_and_retrieval_outputs": PROPOSED,
            "audit_mode": mode,
            "approval": "named human + exact semantic digest",
            "initial_review": (
                "named human + exact analysis/target digest"
                if mode == HUMAN_AUDIT else AUTO_ACCEPTED_FOR_PREVIEW),
            "automatic_authority_ceiling": (
                AUTO_ACCEPTED_FOR_PREVIEW if mode == AUTO_PROPOSED else None),
            "scores_are_not_facts": True,
            "manufacturing_certification": False,
            "industrial_strength_guarantee": False,
        },
    }


def _validate_state(state: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(state, Mapping) or state.get("schema") != SCHEMA:
        return {"verdict": "UNKNOWN_FACTORY_STATE", "why": f"expected {SCHEMA}"}
    if not isinstance(state.get("events"), list):
        return {"verdict": "UNKNOWN_FACTORY_STATE", "why": "events must be a list"}
    if "shape_decisions" in state and not isinstance(state.get("shape_decisions"), list):
        return {"verdict": "UNKNOWN_FACTORY_STATE",
                "why": "shape_decisions must be an append-only list"}
    if ("foreground_cleanup_history" in state
            and not isinstance(state.get("foreground_cleanup_history"), list)):
        return {"verdict": "UNKNOWN_FACTORY_STATE",
                "why": "foreground_cleanup_history must be an append-only list"}
    if state.get("cross_workflow") is not None:
        try:
            cross_workflow_harness.migrate_workflow(
                state.get("cross_workflow"), str(state.get("job_id", "factory-job")),
                source_schema=str(state.get("schema", SCHEMA)))
        except (TypeError, ValueError) as exc:
            return {"verdict": "UNKNOWN_CROSS_WORKFLOW_DOCUMENT",
                    "why": str(exc)}
    return None


def _source(source: Any) -> Optional[str]:
    if not isinstance(source, Mapping):
        return "source manifest is required"
    required = ("name", "modality", "license", "lineage", "rights")
    missing = [name for name in required if not source.get(name)]
    if missing:
        return "source manifest lacks " + ", ".join(missing)
    if source.get("modality") not in _PER_PART_MODALITIES:
        return "per-part retrieval requires region/part/structure embedding, not a global image embedding"
    if not isinstance(source.get("rights"), Mapping):
        return "source rights must be an explicit object"
    return None


def _has_construction_claim(value: Any, path: str = "$") -> Sequence[str]:
    found = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key).lower() in _CONSTRUCTION_KEYS:
                found.append(child)
            found.extend(_has_construction_claim(item, child))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            found.extend(_has_construction_claim(item, f"{path}[{index}]"))
    return sorted(found)


def _submit_retrieval(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    if state.get("image_evidence") is None:
        return _unknown(state, "UNKNOWN_IMAGE_CONFIRMATION_REQUIRED", "confirm image regions first")
    source = event.get("source")
    source_error = _source(source)
    if source_error:
        return _unknown(state, "UNKNOWN_RETRIEVAL_SOURCE", source_error)
    hits = event.get("hits")
    if not isinstance(hits, Sequence) or isinstance(hits, (str, bytes)) or not hits:
        return _unknown(state, "UNKNOWN_RETRIEVAL_HITS", "at least one typed hit is required")
    proposed = []
    for index, hit in enumerate(hits):
        if not isinstance(hit, Mapping):
            return _unknown(state, "UNKNOWN_RETRIEVAL_HIT", f"hit {index} is not an object")
        forbidden = _has_construction_claim(hit)
        if forbidden:
            return _unknown(state, "UNKNOWN_RETRIEVAL_CONSTRUCTION_CLAIM",
                            "embedding similarity cannot claim sewing or pattern construction",
                            hit=index, forbidden=forbidden)
        missing = [name for name in ("part_id", "region_id", "reference", "score")
                   if name not in hit or hit.get(name) in (None, "")]
        score = hit.get("score")
        if (missing or isinstance(score, bool) or not isinstance(score, (int, float))
                or not math.isfinite(float(score))):
            return _unknown(state, "UNKNOWN_RETRIEVAL_HIT",
                            f"hit {index} needs part_id, region_id, reference and a finite score",
                            missing=missing)
        row = _proposal_safe(hit)
        row["state"] = PROPOSED
        row["score_is_evidence"] = False
        row["source_name"] = source["name"]
        proposed.append(row)
    batch = {
        "batch_id": _digest({"source": source, "hits": proposed}),
        "state": PROPOSED,
        "source": _plain(source),
        "hits": proposed,
    }
    state["retrieval_batches"].append(batch)
    _clear_downstream(state, from_retrieval=True)
    state["phase"] = "RETRIEVAL_READY"
    return _accepted(state, event, batch=batch)


def _submit_hypotheses(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    if not state.get("retrieval_batches"):
        return _unknown(state, "UNKNOWN_RETRIEVAL_REQUIRED", "submit typed per-part retrieval first")
    rows = event.get("hypotheses")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        return _unknown(state, "UNKNOWN_HYPOTHESES", "hypotheses must be a non-empty list")
    front_only = bool(event.get("front_only", True))
    if front_only and len(rows) < 2:
        return _unknown(state, "UNKNOWN_BACK_ALTERNATIVES_REQUIRED",
                        "a front-only image needs at least two explicit back alternatives")
    candidates = []
    ids = set()
    backs = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            return _unknown(state, "UNKNOWN_HYPOTHESIS", f"hypothesis {index} is not an object")
        candidate_id = str(raw.get("candidate_id", "")).strip()
        back_design = str(raw.get("back_design", "")).strip()
        structure = raw.get("structure")
        if not candidate_id or candidate_id in ids or (front_only and not back_design):
            return _unknown(state, "UNKNOWN_HYPOTHESIS",
                            "candidate ids must be unique and every front-only candidate needs a named back design")
        if front_only and back_design in backs:
            return _unknown(state, "UNKNOWN_BACK_ALTERNATIVES_REQUIRED",
                            "back alternatives must be structurally distinct and named")
        ids.add(candidate_id)
        backs.add(back_design)
        validation = (garment_structure.build(structure) if isinstance(structure, Mapping)
                      else {"verdict": "UNKNOWN_STRUCTURE_MISSING"})
        safe = _proposal_safe(raw)
        safe["candidate_id"] = candidate_id
        safe["back_design"] = back_design
        safe["state"] = PROPOSED
        safe["geometry_validation"] = validation
        safe["eligible_for_approval"] = validation.get("verdict") == ANSWER
        safe["digest"] = _digest({k: v for k, v in safe.items() if k != "digest"})
        candidates.append(safe)
    if len([row for row in candidates if row["eligible_for_approval"]]) < (2 if front_only else 1):
        return _unknown(state, "UNKNOWN_GEOMETRIC_HYPOTHESES_REQUIRED",
                        "not enough alternatives passed deterministic structure validation",
                        candidates=candidates)
    sheet = {
        "state": PROPOSED,
        "front_only": front_only,
        "criteria": ["front_consistency", "geometric_feasibility", "dressability"],
        "candidates": candidates,
        "retrieval_digest": _digest(state["retrieval_batches"]),
    }
    sheet["comparison_digest"] = _digest(sheet)
    state["hypothesis_sheet"] = sheet
    _clear_downstream(state)
    state["phase"] = "BACK_CANDIDATES_READY" if front_only else "STRUCTURE_CANDIDATES_READY"
    return _accepted(state, event, verdict=PROPOSED, sheet=sheet)


def _approve_shape(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    sheet = state.get("hypothesis_sheet")
    if not isinstance(sheet, Mapping):
        return _unknown(state, "UNKNOWN_HYPOTHESIS_SHEET_REQUIRED", "submit hypotheses first")
    by = str(event.get("by", "")).strip()
    if not by:
        return _unknown(state, "UNKNOWN_NAMED_HUMAN_APPROVER_REQUIRED", "a model cannot approve its own proposal")
    candidate_id = str(event.get("candidate_id", ""))
    candidate = next((row for row in sheet["candidates"] if row["candidate_id"] == candidate_id), None)
    if candidate is None:
        return _unknown(state, "UNKNOWN_CANDIDATE_NOT_IN_COMPARISON", candidate_id)
    if not candidate.get("eligible_for_approval"):
        return _unknown(state, "UNKNOWN_INVALID_GEOMETRY_CANNOT_BE_APPROVED", candidate_id)
    received = str(event.get("digest", ""))
    if received != candidate["digest"]:
        return _unknown(state, "UNKNOWN_CANDIDATE_APPROVAL_STALE", "candidate digest changed",
                        expected=candidate["digest"], received=received)
    rejection = _active_shape_rejection(state, candidate_id,
                                        candidate["digest"])
    if rejection is not None:
        return _unknown(state, "UNKNOWN_CANDIDATE_REJECTED",
                        "undo the digest-bound rejection before approving this candidate",
                        rejection=copy.deepcopy(dict(rejection)))
    approval = {
        "state": APPROVED, "by": by, "candidate_id": candidate_id,
        "candidate_digest": candidate["digest"],
        "comparison_digest": sheet["comparison_digest"],
    }
    approval["approval_id"] = _digest(approval)
    existing = state.get("shape_approval")
    if isinstance(existing, Mapping) and existing.get("approval_id") == approval["approval_id"]:
        # A repeated UI delivery is idempotent.  In particular it must not add
        # a second approval event or restart the downstream factory loop.
        return {"verdict": APPROVED, "state": state,
                "approval": copy.deepcopy(dict(existing)), "idempotent": True}
    if isinstance(existing, Mapping):
        return _unknown(state, "UNKNOWN_SHAPE_DECISION_UNDO_REQUIRED",
                        "undo the current shape approval before selecting another candidate",
                        current_approval=copy.deepcopy(dict(existing)))
    state["shape_approval"] = approval
    decision = _append_shape_decision(state, "APPROVE", {
        "candidate_id": candidate_id,
        "candidate_digest": candidate["digest"],
        "comparison_digest": sheet["comparison_digest"],
        "approval_id": approval["approval_id"],
        "by": by,
    })
    state["phase"] = "STRUCTURE_APPROVED"
    return _accepted(state, event, verdict=APPROVED, approval=approval,
                     decision=decision,
                     note="the proposal remains PROPOSED; approval is a separate record")


def _reject_shape(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    sheet = state.get("hypothesis_sheet")
    if not isinstance(sheet, Mapping):
        return _unknown(state, "UNKNOWN_HYPOTHESIS_SHEET_REQUIRED",
                        "submit hypotheses first")
    by = str(event.get("by", "")).strip()
    if not by:
        return _unknown(state, "UNKNOWN_NAMED_HUMAN_REJECTOR_REQUIRED",
                        "a model cannot reject a candidate for the human")
    reason = str(event.get("reason", "")).strip()
    if not reason:
        return _unknown(state, "UNKNOWN_REJECTION_REASON_REQUIRED",
                        "candidate rejection requires an auditable reason")
    candidate_id = str(event.get("candidate_id", "")).strip()
    candidate = next((row for row in sheet.get("candidates", ())
                      if row.get("candidate_id") == candidate_id), None)
    if not isinstance(candidate, Mapping):
        return _unknown(state, "UNKNOWN_CANDIDATE_NOT_IN_COMPARISON",
                        candidate_id)
    received = str(event.get("digest", ""))
    if received != candidate.get("digest"):
        return _unknown(state, "UNKNOWN_CANDIDATE_REJECTION_STALE",
                        "candidate digest changed",
                        expected=candidate.get("digest"), received=received)
    existing_approval = state.get("shape_approval")
    if isinstance(existing_approval, Mapping):
        return _unknown(state, "UNKNOWN_SHAPE_DECISION_UNDO_REQUIRED",
                        "undo the current shape approval before rejecting a candidate",
                        current_approval=copy.deepcopy(dict(existing_approval)))
    active = _active_shape_rejection(state, candidate_id,
                                     str(candidate.get("digest", "")))
    if active is not None:
        same = (active.get("by") == by and active.get("reason") == reason
                and active.get("comparison_digest") == sheet.get("comparison_digest"))
        if same:
            return {"verdict": REJECTED, "state": state,
                    "rejection": copy.deepcopy(dict(active)),
                    "idempotent": True}
        return _unknown(state, "UNKNOWN_CANDIDATE_ALREADY_REJECTED",
                        "undo the active rejection before replacing its reason or reviewer",
                        rejection=copy.deepcopy(dict(active)))
    rejection = _append_shape_decision(state, "REJECT", {
        "candidate_id": candidate_id,
        "candidate_digest": candidate["digest"],
        "comparison_digest": sheet["comparison_digest"],
        "by": by,
        "reason": reason,
    })
    state["phase"] = _candidate_ready_phase(state)
    return _accepted(state, event, verdict=REJECTED, rejection=rejection)


def _undo_shape_decision(state: Dict[str, Any],
                         event: Mapping[str, Any]) -> Dict[str, Any]:
    sheet = state.get("hypothesis_sheet")
    if not isinstance(sheet, Mapping):
        return _unknown(state, "UNKNOWN_HYPOTHESIS_SHEET_REQUIRED",
                        "submit hypotheses first")
    by = str(event.get("by", "")).strip()
    if not by:
        return _unknown(state, "UNKNOWN_NAMED_HUMAN_UNDO_REQUIRED",
                        "candidate decision undo requires a named human")
    command_id = str(event.get("command_id", "")).strip()
    if not command_id:
        return _unknown(state, "UNKNOWN_UNDO_COMMAND_ID_REQUIRED",
                        "undo requires a stable command_id for idempotent delivery")
    previous_undo = next((row for row in _shape_decisions(state)
                          if row.get("action") == "UNDO"
                          and row.get("command_id") == command_id), None)
    if previous_undo is not None:
        return {"verdict": ANSWER, "state": state,
                "undo": copy.deepcopy(dict(previous_undo)),
                "undone_decision_id": previous_undo.get(
                    "compensates_decision_id"),
                "idempotent": True}
    active = list(_active_shape_decisions(state))
    requested = str(event.get("decision_id", "")).strip()
    target = (next((row for row in reversed(active)
                    if row.get("decision_id") == requested), None)
              if requested else (active[-1] if active else None))
    if target is None:
        return _unknown(state, "UNKNOWN_NOTHING_TO_UNDO",
                        "there is no active candidate decision in this comparison",
                        decision_id=requested or None)
    if target.get("action") == "APPROVE":
        approval = state.get("shape_approval")
        if (not isinstance(approval, Mapping)
                or approval.get("approval_id") != target.get("approval_id")):
            return _unknown(state, "UNKNOWN_SHAPE_DECISION_STALE",
                            "the active approval no longer matches the decision to undo",
                            decision=copy.deepcopy(dict(target)))
        # Every later artifact is bound to this exact approval.  Compensation
        # invalidates all of them instead of retaining a stale pattern or run.
        _clear_downstream(state)
        state["phase"] = _candidate_ready_phase(state)
    undo = _append_shape_decision(state, "UNDO", {
        "command_id": command_id,
        "compensates_decision_id": target["decision_id"],
        "comparison_digest": sheet["comparison_digest"],
        "by": by,
    })
    return _accepted(state, event, verdict=ANSWER, undo=undo,
                     undone_decision_id=target["decision_id"])


def _run_stage(state: Dict[str, Any], event: Mapping[str, Any], runner: Optional[Runner],
               *, field: str, ready_phase: str, missing_code: str) -> Dict[str, Any]:
    if _approval_candidate(state) is None:
        return _unknown(state, "UNKNOWN_SHAPE_APPROVAL_REQUIRED", "approve an exact candidate digest first")
    if runner is None:
        return _unknown(state, missing_code, "this runtime has no deterministic stage runner")
    result = runner(copy.deepcopy(state), copy.deepcopy(dict(event)))
    if not isinstance(result, Mapping):
        return _unknown(state, "UNKNOWN_STAGE_RESULT", "runner must return an object")
    result = _plain(result)
    if field in {"pattern", "repair"}:
        result["cad_target_iteration"] = _cad_target_iteration_binding(state)
    state[field] = result
    if result.get("verdict") != ANSWER:
        return _accepted(state, event, verdict=str(result.get("verdict", "UNKNOWN_STAGE_RESULT")), result=result)
    state["phase"] = ready_phase
    return _accepted(state, event, result=result)


def _material_candidates(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    if _approval_candidate(state) is None:
        return _unknown(state, "UNKNOWN_SHAPE_APPROVAL_REQUIRED", "approve shape before material comparison")
    rows = event.get("candidates")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) < 2:
        return _unknown(state, "UNKNOWN_MATERIAL_ALTERNATIVES_REQUIRED", "at least two material candidates are required")
    candidates = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping) or not str(raw.get("candidate_id", "")).strip():
            return _unknown(state, "UNKNOWN_MATERIAL_CANDIDATE", f"candidate {index} is malformed")
        safe = _proposal_safe(raw)
        safe["state"] = PROPOSED
        safe["digest"] = _digest({k: v for k, v in safe.items() if k != "digest"})
        candidates.append(safe)
    sheet = {"state": PROPOSED, "candidates": candidates,
             "criteria": ["drape", "stretch", "bending", "mass", "comfort_scope"]}
    sheet["comparison_digest"] = _digest(sheet)
    state["material_sheet"] = sheet
    state["material_approval"] = None
    state["phase"] = "MATERIAL_CANDIDATES_READY"
    return _accepted(state, event, verdict=PROPOSED, sheet=sheet)


def _approve_material(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    sheet = state.get("material_sheet")
    if not isinstance(sheet, Mapping):
        return _unknown(state, "UNKNOWN_MATERIAL_SHEET_REQUIRED", "submit material alternatives first")
    by = str(event.get("by", "")).strip()
    if not by:
        return _unknown(state, "UNKNOWN_NAMED_HUMAN_APPROVER_REQUIRED", "material choice needs a named human")
    candidate = next((row for row in sheet["candidates"]
                      if row.get("candidate_id") == event.get("candidate_id")), None)
    if candidate is None:
        return _unknown(state, "UNKNOWN_CANDIDATE_NOT_IN_COMPARISON", "material candidate not found")
    if str(event.get("digest", "")) != candidate["digest"]:
        return _unknown(state, "UNKNOWN_CANDIDATE_APPROVAL_STALE", "material candidate digest changed",
                        expected=candidate["digest"], received=event.get("digest", ""))
    approval = {"state": APPROVED, "by": by, "candidate_id": candidate["candidate_id"],
                "candidate_digest": candidate["digest"],
                "comparison_digest": sheet["comparison_digest"]}
    approval["approval_id"] = _digest(approval)
    state["material_approval"] = approval
    state["phase"] = "MATERIAL_APPROVED"
    return _accepted(state, event, verdict=APPROVED, approval=approval)


def _simulate(state: Dict[str, Any], event: Mapping[str, Any], runner: Optional[Runner]) -> Dict[str, Any]:
    if state.get("pattern") is None:
        return _unknown(state, "UNKNOWN_PATTERN_REQUIRED", "generate a pattern before simulation")
    if _approval_candidate(state, material=True) is None:
        return _unknown(state, "UNKNOWN_MATERIAL_APPROVAL_REQUIRED", "approve material parameters before simulation")
    return _run_stage(state, event, runner, field="simulation", ready_phase="SIMULATION_READY",
                      missing_code="UNKNOWN_SIMULATION_RUNNER")


def _sewing(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    if _approval_candidate(state) is None or state.get("pattern") is None:
        return _unknown(state, "UNKNOWN_APPROVED_PATTERN_REQUIRED", "approve shape and generate pattern first")
    manifest = event.get("manifest")
    check = corpus_manifest.validate(manifest if isinstance(manifest, Mapping) else {},
                                     require_commercial=bool(event.get("require_commercial", True)),
                                     purpose="sewing")
    if check.get("verdict") != ANSWER:
        return _unknown(state, "UNKNOWN_NO_SEWING_CORPUS", "no eligible sewing corpus is attached",
                        manifest_check=check)
    methods = event.get("methods")
    if not isinstance(methods, Sequence) or isinstance(methods, (str, bytes)) or not methods:
        return _unknown(state, "UNKNOWN_NO_SEWING_METHOD_HITS", "the eligible corpus returned no typed methods")
    state["sewing"] = {
        "state": PROPOSED,
        "methods": _proposal_safe(methods),
        "manifest_digest": _digest(manifest),
        "shape_approval_id": state["shape_approval"]["approval_id"],
        "requires_human_and_deterministic_validation": True,
    }
    state["phase"] = "SEWING_CANDIDATES_READY"
    return _accepted(state, event, verdict=PROPOSED, sewing=state["sewing"])


def _hybrid_retrieve(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    """Run rights-gated retrieval and install both typed factory events."""
    if state.get("image_evidence") is None:
        return _unknown(state, "UNKNOWN_IMAGE_CONFIRMATION_REQUIRED",
                        "confirm image regions before hybrid retrieval")
    from . import retrieval_hypothesis

    payload = event.get("request", {})
    payload = copy.deepcopy(dict(payload)) if isinstance(payload, Mapping) else {}
    payload["image_evidence"] = copy.deepcopy(state["image_evidence"])
    if "corpora" in event:
        payload["corpora"] = copy.deepcopy(event.get("corpora"))
    if "require_commercial" in event:
        payload["require_commercial"] = bool(event.get("require_commercial"))
    bundle = retrieval_hypothesis.multi_stage_retrieve(payload)
    if bundle.get("verdict") != PROPOSED:
        return _unknown(state, str(bundle.get("verdict", "UNKNOWN_HYBRID_RETRIEVAL")),
                        str(bundle.get("why", "hybrid retrieval did not produce proposals")),
                        retrieval=bundle)
    events = (bundle.get("route", {}) or {}).get("factory_events")
    if (not isinstance(events, Sequence) or isinstance(events, (str, bytes))
            or len(events) != 2):
        return _unknown(state, "UNKNOWN_HYBRID_RETRIEVAL_ROUTE",
                        "hybrid retrieval must produce retrieval and hypothesis events")
    first = _submit_retrieval(state, events[0])
    if first.get("verdict") != ANSWER:
        return first
    intermediate = first["state"]
    intermediate["hybrid_retrieval"] = {
        "verdict": PROPOSED, "source": copy.deepcopy(bundle["source"]),
        "corpus_status": copy.deepcopy(bundle["corpus_status"]),
        "route_digest": _digest(bundle["route"]),
    }
    second = _submit_hypotheses(intermediate, events[1])
    if second.get("verdict") == PROPOSED:
        second["hybrid_retrieval"] = bundle
    return second


def _hybrid_sewing(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    """Search from the verified approved candidate, never from image text."""
    if _approval_candidate(state) is None:
        return _unknown(state, "UNKNOWN_SHAPE_APPROVAL_REQUIRED",
                        "approve an exact 3D candidate digest before sewing search")
    from . import sewing_search

    result = sewing_search._hybrid_search_factory_state(
        state, event.get("corpora", ()),
        require_commercial=bool(event.get("require_commercial", True)))
    if result.get("verdict") != PROPOSED:
        return _unknown(state, str(result.get("verdict", "UNKNOWN_HYBRID_SEWING_SEARCH")),
                        str(result.get("why", "sewing search did not produce proposals")),
                        sewing_search=result)
    if result.get("route", {}).get("shape_approval_id") != state["shape_approval"]["approval_id"]:
        return _unknown(state, "UNKNOWN_SEWING_APPROVAL_BINDING",
                        "sewing result is not bound to the current approval")
    state["sewing"] = copy.deepcopy(result)
    state["phase"] = "SEWING_CANDIDATES_READY"
    return _accepted(state, event, verdict=PROPOSED, sewing=result)


def _procedural_sewing(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    """Install a topology-derived order without posing as corpus evidence.

    This route lets the factory continue while an optional rights-cleared
    precedent corpus is absent.  It cannot supply stitch class, machine setup,
    seam finish or industrial validation; those remain explicit review items.
    """
    approved = _approval_candidate(state)
    pattern = state.get("pattern")
    if approved is None or not isinstance(pattern, Mapping):
        return _unknown(state, "UNKNOWN_APPROVED_PATTERN_REQUIRED",
                        "approve shape and generate its exact pattern first")
    plan = event.get("plan")
    if not isinstance(plan, Mapping):
        for owner in (state.get("repair"), state.get("pattern")):
            if isinstance(owner, Mapping) and isinstance(
                    owner.get("topology_sewing_plan"), Mapping):
                plan = owner["topology_sewing_plan"]
                break
    if not isinstance(plan, Mapping):
        return _unknown(state, "UNKNOWN_PROCEDURAL_SEWING_PLAN_REQUIRED",
                        "no topology sewing plan is attached to this pattern")
    steps = plan.get("steps")
    if (plan.get("order_verdict", plan.get("verdict")) != ANSWER
            or not isinstance(steps, Sequence)
            or isinstance(steps, (str, bytes)) or not steps
            or any(not isinstance(row, Mapping) for row in steps)):
        return _unknown(state, "UNKNOWN_PROCEDURAL_SEWING_PLAN_INVALID",
                        "the plan must have an ANSWER order and typed non-empty steps",
                        plan_verdict=plan.get("verdict"),
                        order_verdict=plan.get("order_verdict"))
    candidate_id = str(approved.get("candidate_id", ""))
    plan_candidate = str(plan.get("candidate_id", candidate_id))
    if plan_candidate != candidate_id:
        return _unknown(state, "UNKNOWN_SEWING_APPROVAL_BINDING",
                        "the topology plan belongs to another structure candidate",
                        expected=candidate_id, received=plan_candidate)
    result = {
        "verdict": PROPOSED,
        "route": "PROCEDURAL_TOPOLOGY",
        "state": PROPOSED,
        "plan": _plain(plan),
        "plan_digest": _digest(plan),
        "shape_approval_id": state["shape_approval"]["approval_id"],
        "candidate_id": candidate_id,
        "source_pattern_digest": plan.get("source_pattern_digest",
                                           pattern.get("digest")),
        "corpus_used": False,
        "corpus_evidence": False,
        "corpus_gap": "UNKNOWN_NO_SEWING_CORPUS",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "scope": ("dependency order derived from approved pattern topology; "
                  "not stitch, seam-finish, machine or industrial precedent evidence"),
    }
    state["sewing"] = result
    state["phase"] = "SEWING_CANDIDATES_READY"
    return _accepted(state, event, verdict=PROPOSED, sewing=result)


def _iterate(state: Dict[str, Any], event: Mapping[str, Any]) -> Dict[str, Any]:
    if state["iteration"] >= state["max_iterations"]:
        return _unknown(state, "ESCALATE_HUMAN_ITERATION_BUDGET", "Vera closed the loop at its hard budget")
    state["iteration"] += 1
    missing = []
    if _approval_candidate(state) is None:
        missing.append("human shape approval")
    if state.get("pattern") is None:
        missing.append("deterministic pattern")
    if state.get("repair") is None or not bool(state.get("repair", {}).get("sewable")):
        missing.append("sewability repair/validation")
    if state.get("simulation") is None:
        missing.append("material simulation")
    if state.get("sewing") is None:
        missing.append("eligible sewing-method evidence")
    engineering = None
    if isinstance(state.get("simulation"), Mapping):
        engineering = state["simulation"].get("engineering_review")
    if not isinstance(engineering, Mapping) and isinstance(state.get("repair"), Mapping):
        engineering = state["repair"].get("engineering_review")
    if isinstance(engineering, Mapping):
        for gate in engineering.get("actionable_gates", ()):
            item = f"engineering gate: {gate}"
            if item not in missing:
                missing.append(item)
    if not missing:
        state["phase"] = "CONVERGED_REVIEW"
        return _accepted(state, event, verdict="CONVERGED",
                         scope="engineering review only; not manufacturing certification")
    state["phase"] = "ITERATING"
    return _accepted(state, event, verdict="CONTINUE", missing=missing,
                     model_role="may propose alternatives only")


def advance(state: Mapping[str, Any], event: Mapping[str, Any], *,
            pattern_runner: Optional[Runner] = None,
            repair_runner: Optional[Runner] = None,
            simulation_runner: Optional[Runner] = None) -> Dict[str, Any]:
    """Apply one typed event and return a new JSON state plus its verdict."""
    error = _validate_state(state)
    if error:
        preserved = (copy.deepcopy(dict(state))
                     if isinstance(state, Mapping) else state)
        workflow = cross_workflow_harness.new_workflow(
            str(state.get("job_id", "factory-job"))
            if isinstance(state, Mapping) else "factory-job",
            source_schema=str(state.get("schema", "invalid"))
            if isinstance(state, Mapping) else "invalid")
        recorded = cross_workflow_harness.record_stage(
            workflow, stage="FACTORY_DOCUMENT_LOAD", outcome=error,
            provenance={"component": "garment_factory"})
        return {**error, "state": preserved,
                "resolution_request": recorded["resolution_request"],
                "resolution_requests": recorded["resolution_requests"],
                "typed_stop": (recorded["resolution_request"] or {}).get(
                    "typed_stop")}
    current = copy.deepcopy(dict(state))
    # Older persisted garment.factory.v1 documents predate reversible shape
    # decisions.  An empty journal is a lossless migration while no decision
    # has yet been recorded through this contract.
    current.setdefault("shape_decisions", [])
    current.setdefault("audit_mode", HUMAN_AUDIT)
    current.setdefault("visible_ai_analysis", None)
    current.setdefault("visible_audit", None)
    current.setdefault("human_visible_audit", None)
    current.setdefault("auto_visible_audit", None)
    current.setdefault("front_facts", None)
    current.setdefault("foreground_cleanup", None)
    current.setdefault("foreground_cleanup_history", [])
    current.setdefault("front_compilation", None)
    current["cross_workflow"] = cross_workflow_harness.migrate_workflow(
        current.get("cross_workflow"), str(current.get("job_id", "factory-job")),
        source_schema=str(current.get("schema", SCHEMA)))
    if not isinstance(event, Mapping):
        return _unknown(current, "UNKNOWN_FACTORY_EVENT", "event must be an object")
    try:
        mode = _audit_mode(current.get("audit_mode"))
    except ValueError as exc:
        return _unknown(current, "UNKNOWN_FACTORY_STATE", str(exc))
    _apply_audit_mode(current, mode)
    kind = str(event.get("type", "")).upper()
    if kind == "GRANT_LLM_PROPOSAL_CONSENT":
        granted = cross_workflow_harness.grant_model_consent(
            current["cross_workflow"], scope=str(event.get("scope", "")),
            fields=event.get("fields", ()),
            granted_by=str(event.get("granted_by", event.get("by", ""))),
            expires_after_revision=event.get("expires_after_revision"),
            request_id=event.get("request_id"))
        current["cross_workflow"] = granted["workflow"]
        if granted["verdict"] != ANSWER:
            request = granted.get("resolution_request", {})
            return {"verdict": str(granted["verdict"]),
                    "why": str(request.get(
                        "reason", "invalid model consent")),
                    "state": current, "resolution_request": request,
                    "resolution_requests": [request]}
        return _accepted(current, event, verdict="CONSENT_RECORDED",
                         record_cross=False,
                         consent_artifact=granted["consent_artifact"])
    if kind == "RESOLVE_CROSS_OBLIGATION":
        resolved = cross_workflow_harness.resolve_request(
            current["cross_workflow"],
            request_id=str(event.get("request_id", "")),
            choice=str(event.get("choice", "")),
            values=event.get("values"),
            actor=str(event.get("actor", event.get("by", ""))),
            consent_digest=event.get("consent_digest"),
            provenance=event.get("provenance")
            if isinstance(event.get("provenance"), Mapping) else None)
        current["cross_workflow"] = resolved["workflow"]
        if str(resolved["verdict"]).startswith("UNKNOWN_"):
            request = resolved.get("resolution_request", {})
            return {"verdict": str(resolved["verdict"]),
                    "why": str(request.get("reason", "invalid resolution")),
                    "state": current, "resolution_request": request,
                    "resolution_requests": [request]}
        return _accepted(current, event, verdict=str(resolved["verdict"]),
                         record_cross=False,
                         resolution=resolved.get("resolution"))
    contract_events = {
        "SUBMIT_PHYSICAL_CALIBRATION_DECISION": "PHYSICAL_CALIBRATION",
        "SUBMIT_RECONSTRUCTION_CLAIM_DECISION": "RECONSTRUCTION_CLAIM",
        "SUBMIT_MANUFACTURING_FINISH_DECISION": "MANUFACTURING_FINISH",
    }
    if kind in contract_events:
        admitted = cross_workflow_harness.admit_authoritative_contract(
            current["cross_workflow"],
            contract_kind=contract_events[kind],
            decision=event.get("decision"),
            approval=event.get("approval"),
            provenance=(event.get("provenance")
                        if isinstance(event.get("provenance"), Mapping)
                        else None))
        current["cross_workflow"] = admitted["workflow"]
        if str(admitted["verdict"]).startswith("UNKNOWN_"):
            request = admitted.get("resolution_request") or {}
            return {
                "verdict": str(admitted["verdict"]),
                "why": str(admitted.get(
                    "why", request.get("reason", "contract admission failed"))),
                "state": current,
                "contract_admission": _plain({
                    key: value for key, value in admitted.items()
                    if key != "workflow"}),
                "resolution_request": request,
                "resolution_requests": admitted.get("resolution_requests", ()),
            }
        return _accepted(
            current, event, verdict="CONTRACT_ADMITTED", record_cross=False,
            contract_admission=_plain({
                key: value for key, value in admitted.items()
                if key not in {"workflow", "resolution_request",
                               "resolution_requests"}}),
            resolution_request=admitted.get("resolution_request"),
            resolution_requests=admitted.get("resolution_requests", ()))
    if kind == "CONFIRM_IMAGE":
        if "audit_mode" in event:
            try:
                mode = _audit_mode(event.get("audit_mode"))
            except ValueError as exc:
                return _unknown(current, "UNKNOWN_FACTORY_EVENT", str(exc))
            _apply_audit_mode(current, mode)
        outline = event.get("outline")
        regions = event.get("regions")
        if not isinstance(outline, Mapping) or not outline.get("outline") or not isinstance(regions, Sequence):
            return _unknown(current, "UNKNOWN_IMAGE_EVIDENCE", "outline contract and confirmed regions are required")
        evidence_state = str(event.get("evidence_state", "OBSERVED")).upper()
        if evidence_state not in {"OBSERVED", PROPOSED}:
            return _unknown(current, "UNKNOWN_IMAGE_EVIDENCE_STATE",
                            "evidence_state must be OBSERVED or PROPOSED",
                            received=event.get("evidence_state"))
        source_view, declared_view = _source_view(event)
        effective_evidence_state = (
            PROPOSED if mode == AUTO_PROPOSED else evidence_state)
        sanitise = _proposal_safe if mode == AUTO_PROPOSED else _plain
        _archive_active_foreground_cleanup(current)
        current["image_evidence"] = {
            "state": effective_evidence_state,
            "declared_evidence_state": evidence_state,
            "outline": sanitise(outline),
            "regions": sanitise(regions),
            "front_only": bool(event.get("front_only", True)),
            "source_view": source_view,
            "view_authority": _view_authority(
                mode, evidence_state, source_view, declared_view),
            "source": sanitise(event.get("source", {})),
        }
        current["retrieval_batches"] = []
        current["visible_ai_analysis"] = None
        current["visible_audit"] = None
        current["human_visible_audit"] = None
        current["auto_visible_audit"] = None
        current["front_facts"] = None
        current["foreground_cleanup"] = None
        current["front_compilation"] = None
        _clear_downstream(current, from_retrieval=True)
        current["iteration"] = 0
        current["phase"] = "REGIONS_CONFIRMED"
        return _accepted(current, event)
    if kind == "RECORD_AI_VISIBLE_ANALYSIS":
        return _record_ai_visible_analysis(current, event)
    if kind == "SUBMIT_HUMAN_VISIBLE_AUDIT":
        if mode == AUTO_PROPOSED:
            return _unknown(
                current, "UNKNOWN_FACTORY_EVENT",
                "AUTO_PROPOSED jobs cannot promote proposals through a human-audit event; start a HUMAN_AUDIT job instead")
        return _submit_human_visible_audit(current, event)
    if kind == "SUBMIT_FOREGROUND_CLEANUP":
        if (mode == AUTO_PROPOSED
                and current.get("phase") == "HUMAN_GARMENT_AUDIT_REQUIRED"
                and isinstance(current.get("visible_ai_analysis"), Mapping)):
            current = _auto_accept_visible_analysis(current, {
                "type": "AUTO_ACCEPT_VISIBLE_AUDIT",
                "actor": "VERA_AUTO_AUDIT",
                "analysis_digest": current["visible_ai_analysis"].get(
                    "analysis_digest"),
            })["state"]
        return (_submit_auto_foreground_cleanup(current, event)
                if mode == AUTO_PROPOSED
                else _submit_foreground_cleanup(current, event))
    if kind == "OPEN_RETRIEVAL_AFTER_FRONT_REVIEW":
        return _open_retrieval_after_front_review(current, event)
    if current.get("phase") == "HUMAN_GARMENT_AUDIT_REQUIRED":
        return _unknown(current, "UNKNOWN_HUMAN_GARMENT_AUDIT_REQUIRED",
                        "AI garment analysis must be audited before retrieval or geometry")
    if current.get("phase") == "FOREGROUND_CLEANUP_REQUIRED":
        return _unknown(current, "UNKNOWN_FOREGROUND_CLEANUP_REQUIRED",
                        "adopt the edited front target before retrieval or geometry")
    if kind == "SUBMIT_RETRIEVAL":
        return _submit_retrieval(current, event)
    if kind == "HYBRID_RETRIEVE":
        return _hybrid_retrieve(current, event)
    if kind == "SUBMIT_HYPOTHESES":
        return _submit_hypotheses(current, event)
    if kind == "APPROVE_HYPOTHESIS":
        return _approve_shape(current, event)
    if kind == "REJECT_HYPOTHESIS":
        return _reject_shape(current, event)
    if kind in {"UNDO_HYPOTHESIS_DECISION", "UNDO_SHAPE_DECISION"}:
        return _undo_shape_decision(current, event)
    if kind == "GENERATE_PATTERN":
        return _run_stage(current, event, pattern_runner, field="pattern",
                          ready_phase="PATTERN_READY", missing_code="UNKNOWN_PATTERN_RUNNER")
    if kind == "REPAIR_PATTERN":
        if current.get("pattern") is None:
            return _unknown(current, "UNKNOWN_PATTERN_REQUIRED", "generate a pattern before repair")
        return _run_stage(current, event, repair_runner, field="repair",
                          ready_phase="PATTERN_REPAIRED", missing_code="UNKNOWN_REPAIR_RUNNER")
    if kind == "SUBMIT_MATERIAL_CANDIDATES":
        return _material_candidates(current, event)
    if kind == "APPROVE_MATERIAL":
        return _approve_material(current, event)
    if kind == "SIMULATE":
        return _simulate(current, event, simulation_runner)
    if kind == "SUBMIT_SEWING_METHODS":
        return _sewing(current, event)
    if kind == "HYBRID_SEWING_SEARCH":
        return _hybrid_sewing(current, event)
    if kind == "USE_PROCEDURAL_SEWING_PLAN":
        return _procedural_sewing(current, event)
    if kind == "ITERATE":
        return _iterate(current, event)
    return _unknown(current, "UNKNOWN_FACTORY_EVENT", f"unsupported event {kind!r}")
