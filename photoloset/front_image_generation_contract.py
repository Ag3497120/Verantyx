# -*- coding: utf-8 -*-
"""Deterministic orchestration contract for one front garment image.

This module is deliberately an orchestration boundary, not a vision model.  It
accepts structured front observations and proposals from an upstream vision
system, binds every derived artifact to one explicit candidate, and decides
which deterministic or human action may happen next.

A single front image cannot observe the rear, material mechanics, wearer
measurements, or manufacturing fitness.  Those boundaries are enforced here:
rear and material alternatives remain PROPOSED, wearer measurements must come
from a person or measurement process, approvals are digest-bound human acts,
and no result from this contract is manufacturing certification.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Tuple


REQUEST_SCHEMA = "garment.front-image-generation.request.v1"
SCHEMA = "garment.front-image-generation-contract.v1"

OBSERVED = "OBSERVED"
PROPOSED = "PROPOSED"
REVIEW = "REVIEW"
APPROVE = "APPROVE"
STOP = "STOP"
CONTINUE = "CONTINUE"

ARTIFACT_KINDS = ("preview_3d", "pattern", "manufacturing")
APPROVAL_GATES = ("candidate", "pattern", "manufacturing_review")
REQUIRED_WEARER_MEASUREMENTS = (
    "chest_circumference_cm",
    "waist_circumference_cm",
    "hip_circumference_cm",
    "body_length_cm",
)
_MEASUREMENT_AUTHORITIES = {"MEASURED", "USER_PROVIDED"}
_REAR_TOKENS = {"back", "rear", "backside", "背面", "後身頃"}
_MATERIAL_TOKENS = {
    "material", "fabric", "textile", "fiber", "fibre", "素材", "生地",
}
_CERTIFICATION_KEYS = {
    "manufacturing_certified", "certified_for_manufacture",
    "industrial_certified",
}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not canonical JSON")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    raise TypeError(f"value is not canonical JSON: {type(value).__name__}")


def stable_digest(value: Any) -> str:
    """Return a SHA-256 digest of canonical JSON without trusting input order."""

    encoded = json.dumps(
        _plain(value), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _request_digest(request: Mapping[str, Any]) -> str:
    """Digest a request while ignoring order in explicitly set-like inputs."""

    canonical = copy.deepcopy(dict(request))
    vision = canonical.get("vision")
    if isinstance(vision, Mapping):
        vision = copy.deepcopy(dict(vision))
        for group in ("observations", "proposals"):
            rows = vision.get(group)
            if (isinstance(rows, Sequence)
                    and not isinstance(rows, (str, bytes))
                    and all(isinstance(row, Mapping) for row in rows)):
                vision[group] = _sorted_rows(rows, "claim_id")
        canonical["vision"] = vision
    candidates = canonical.get("candidates")
    if (isinstance(candidates, Sequence)
            and not isinstance(candidates, (str, bytes))
            and all(isinstance(row, Mapping) for row in candidates)):
        canonical["candidates"] = _sorted_rows(candidates, "candidate_id")
    return stable_digest(canonical)


def _sorted_rows(rows: Iterable[Mapping[str, Any]], key: str) -> List[Dict[str, Any]]:
    return sorted(
        (copy.deepcopy(dict(row)) for row in rows),
        key=lambda row: (str(row.get(key, "")), stable_digest(row)),
    )


def _result(*, decision: str, reason_code: str, why: str,
            request: Mapping[str, Any], **fields: Any) -> Dict[str, Any]:
    result = {
        "schema": SCHEMA,
        "decision": decision,
        "reason_code": reason_code,
        "why": why,
        "input_digest": _request_digest(request),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "claims": {
            "vision_or_ml_executed_here": False,
            "rear_observed_from_front_image": False,
            "material_observed_from_front_image": False,
            "wearer_measured_from_front_image": False,
            "manufacturing_certification_created": False,
        },
        **copy.deepcopy(fields),
    }
    result["contract_digest"] = stable_digest(result)
    return result


def _refusal(request: Mapping[str, Any], code: str, why: str,
             **detail: Any) -> Dict[str, Any]:
    return _result(
        decision=STOP, reason_code=code, why=why, request=request,
        state="REFUSED", requires_human_approval=False,
        stop_reason=code, continue_reason=None, **detail,
    )


def _path_tokens(path: Any) -> set[str]:
    text = str(path).lower()
    for separator in ("/", ".", "-", "_", "[", "]"):
        text = text.replace(separator, " ")
    tokens = set(text.split())
    # Japanese field names do not have whitespace boundaries.
    tokens.update(token for token in _REAR_TOKENS | _MATERIAL_TOKENS
                  if token in text)
    return tokens


def _is_unobserved_front_only_field(field: Any) -> bool:
    tokens = _path_tokens(field)
    return bool(tokens & (_REAR_TOKENS | _MATERIAL_TOKENS))


def _normalize_vision(request: Mapping[str, Any]) -> Tuple[
        Optional[Dict[str, Any]], Optional[Tuple[str, str, Dict[str, Any]]]]:
    vision = request.get("vision")
    if not isinstance(vision, Mapping):
        return None, (
            "UNKNOWN_STRUCTURED_VISION_REQUIRED",
            "the contract accepts structured upstream vision output, not raw ML work",
            {},
        )
    normalized: Dict[str, Any] = {"observations": [], "proposals": []}
    for group, required_authority in (("observations", OBSERVED),
                                      ("proposals", PROPOSED)):
        rows = vision.get(group, [])
        if (not isinstance(rows, Sequence)
                or isinstance(rows, (str, bytes))
                or any(not isinstance(row, Mapping) for row in rows)):
            return None, (
                "UNKNOWN_TYPED_VISION_CLAIMS_REQUIRED",
                f"vision.{group} must be a list of typed claim objects",
                {"group": group},
            )
        seen: set[str] = set()
        for index, source in enumerate(rows):
            row = copy.deepcopy(dict(source))
            claim_id = str(row.get("claim_id", "")).strip()
            field = str(row.get("field", "")).strip()
            authority = str(row.get("authority", "")).upper()
            if not claim_id or claim_id in seen or not field or "value" not in row:
                return None, (
                    "UNKNOWN_TYPED_VISION_CLAIM",
                    "each vision claim needs a unique claim_id, field, and value",
                    {"group": group, "index": index},
                )
            if authority != required_authority:
                return None, (
                    "UNKNOWN_VISION_AUTHORITY_MISMATCH",
                    f"vision.{group} claims must have {required_authority} authority",
                    {"claim_id": claim_id, "claimed": authority,
                     "required": required_authority},
                )
            if group == "observations" and _is_unobserved_front_only_field(field):
                return None, (
                    "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
                    "one front image cannot make rear or material claims observed facts",
                    {"claim_id": claim_id, "field": field,
                     "required_authority": PROPOSED},
                )
            if not isinstance(row.get("basis"), str) or not row["basis"].strip():
                return None, (
                    "UNKNOWN_VISION_CLAIM_BASIS_REQUIRED",
                    "every observation and proposal needs an inspectable basis",
                    {"claim_id": claim_id},
                )
            if "structural_element_id" in row:
                element_id = row.get("structural_element_id")
                if not isinstance(element_id, str) or not element_id.strip():
                    return None, (
                        "UNKNOWN_STRUCTURAL_ELEMENT_ID",
                        "a typed structural image claim needs a non-empty structural_element_id",
                        {"claim_id": claim_id},
                    )
                row["structural_element_id"] = element_id.strip()
            seen.add(claim_id)
            row["claim_id"] = claim_id
            row["field"] = field
            row["authority"] = required_authority
            normalized[group].append(row)
        normalized[group] = _sorted_rows(normalized[group], "claim_id")
    normalized["source_digest"] = stable_digest(normalized)
    return normalized, None


def _structural_element_requirements(
        vision: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Collect explicitly typed front elements that every candidate must retain.

    Not every vision claim is structural.  Upstream interpretation opts into
    this fail-closed coverage check with ``structural_element_id``; this avoids
    guessing from free-form field names while preserving both OBSERVED and
    PROPOSED authority in the lineage record.
    """

    requirements: Dict[str, Dict[str, Any]] = {}
    for group in ("observations", "proposals"):
        for claim in vision.get(group, []):
            element_id = claim.get("structural_element_id")
            if element_id is None:
                continue
            row = requirements.setdefault(str(element_id), {
                "element_id": str(element_id),
                "claim_ids": [],
                "authorities": [],
            })
            row["claim_ids"].append(str(claim["claim_id"]))
            row["authorities"].append(str(claim["authority"]))
    for row in requirements.values():
        row["claim_ids"] = sorted(set(row["claim_ids"]))
        row["authorities"] = sorted(set(row["authorities"]))
    return {key: requirements[key] for key in sorted(requirements)}


def _normalize_measurements(request: Mapping[str, Any]) -> Tuple[
        Dict[str, Dict[str, Any]], List[str], Optional[Tuple[str, str, Dict[str, Any]]]]:
    supplied = request.get("wearer_measurements", {})
    if not isinstance(supplied, Mapping):
        return {}, list(REQUIRED_WEARER_MEASUREMENTS), (
            "UNKNOWN_WEARER_MEASUREMENTS_FORMAT",
            "wearer_measurements must be a field-keyed object",
            {},
        )
    normalized: Dict[str, Dict[str, Any]] = {}
    for name in sorted(supplied):
        raw = supplied[name]
        if not isinstance(raw, Mapping):
            return {}, [], (
                "UNKNOWN_WEARER_MEASUREMENT",
                "every wearer measurement needs value_cm and authority",
                {"measurement": str(name)},
            )
        value = raw.get("value_cm")
        authority = str(raw.get("authority", "")).upper()
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value)) or float(value) <= 0.0):
            return {}, [], (
                "UNKNOWN_WEARER_MEASUREMENT",
                "wearer measurements must be finite positive centimetre values",
                {"measurement": str(name)},
            )
        if authority not in _MEASUREMENT_AUTHORITIES:
            return {}, [], (
                "UNKNOWN_WEARER_MEASUREMENT_AUTHORITY",
                "image-derived or proposed dimensions cannot replace wearer measurements",
                {"measurement": str(name), "claimed": authority,
                 "allowed": sorted(_MEASUREMENT_AUTHORITIES)},
            )
        normalized[str(name)] = {
            "value_cm": float(value),
            "authority": authority,
            "source": str(raw.get("source", "human measurement")),
        }
    missing = [name for name in REQUIRED_WEARER_MEASUREMENTS
               if name not in normalized]
    return normalized, missing, None


def _authority(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("authority", value.get("state", ""))).upper()
    return ""


def _certification_violations(value: Any, path: Tuple[str, ...] = ()) -> List[str]:
    violations: List[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = path + (str(key),)
            if str(key).lower() in _CERTIFICATION_KEYS and child is not False:
                violations.append("/".join(child_path))
            violations.extend(_certification_violations(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            violations.extend(_certification_violations(child, path + (str(index),)))
    return sorted(set(violations))


def _front_only_authority_violations(
        value: Any, path: Tuple[str, ...] = ()) -> List[Dict[str, Any]]:
    """Find rear/material claims that acquired fact-like authority."""

    violations: List[Dict[str, Any]] = []
    if isinstance(value, Mapping):
        sensitive = any(_is_unobserved_front_only_field(segment)
                        for segment in path)
        if sensitive:
            claimed = value.get("authority", value.get("state"))
            if claimed is not None and str(claimed).upper() != PROPOSED:
                violations.append({
                    "path": "/".join(path),
                    "claimed": copy.deepcopy(claimed),
                    "required": PROPOSED,
                })
        for key, child in value.items():
            name = str(key)
            lower = name.lower()
            child_path = path + (name,)
            if (lower in {"back_observed", "rear_observed", "material_observed"}
                    and child is not False):
                violations.append({
                    "path": "/".join(child_path),
                    "claimed": copy.deepcopy(child),
                    "required": False,
                })
            if (_is_unobserved_front_only_field(name)
                    and lower.endswith(("authority", "state"))
                    and str(child).upper() != PROPOSED):
                violations.append({
                    "path": "/".join(child_path),
                    "claimed": copy.deepcopy(child),
                    "required": PROPOSED,
                })
            violations.extend(_front_only_authority_violations(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            violations.extend(
                _front_only_authority_violations(child, path + (str(index),)))
    unique = {stable_digest(row): row for row in violations}
    return [unique[digest] for digest in sorted(unique)]


def _normalize_candidates(
        request: Mapping[str, Any],
        required_elements: Mapping[str, Mapping[str, Any]],
) -> Tuple[
        List[Dict[str, Any]], Optional[Tuple[str, str, Dict[str, Any]]]]:
    raw_candidates = request.get("candidates", [])
    if (not isinstance(raw_candidates, Sequence)
            or isinstance(raw_candidates, (str, bytes))
            or any(not isinstance(row, Mapping) for row in raw_candidates)):
        return [], (
            "UNKNOWN_FRONT_CANDIDATES_FORMAT",
            "candidates must be a list of structured proposal objects",
            {},
        )
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, source in enumerate(raw_candidates):
        row = copy.deepcopy(dict(source))
        candidate_id = str(row.get("candidate_id", "")).strip()
        if not candidate_id or candidate_id in seen:
            return [], (
                "UNKNOWN_FRONT_CANDIDATE_ID",
                "candidate ids must be non-empty and unique",
                {"index": index, "candidate_id": candidate_id},
            )
        if _authority(row) != PROPOSED:
            return [], (
                "UNKNOWN_FRONT_CANDIDATE_AUTHORITY",
                "a front-only structure candidate must remain PROPOSED",
                {"candidate_id": candidate_id, "claimed": _authority(row)},
            )
        for field in ("rear_hypothesis", "material_hypothesis"):
            hypothesis = row.get(field)
            if not isinstance(hypothesis, Mapping):
                return [], (
                    "UNKNOWN_CANDIDATE_HYPOTHESIS_REQUIRED",
                    "every candidate needs explicit rear and material hypotheses",
                    {"candidate_id": candidate_id, "missing": field},
                )
            if _authority(hypothesis) != PROPOSED:
                return [], (
                    "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
                    "unobserved rear and material hypotheses must remain PROPOSED",
                    {"candidate_id": candidate_id, "field": field,
                     "claimed": _authority(hypothesis), "required": PROPOSED},
                )
            if "value" not in hypothesis or not str(hypothesis.get("basis", "")).strip():
                return [], (
                    "UNKNOWN_CANDIDATE_HYPOTHESIS_INCOMPLETE",
                    "rear and material hypotheses need value and falsifiable basis",
                    {"candidate_id": candidate_id, "field": field},
                )
        authority_violations = _front_only_authority_violations(row)
        if authority_violations:
            return [], (
                "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
                "unobserved rear and material claims must remain PROPOSED",
                {"candidate_id": candidate_id,
                 "violations": authority_violations},
            )
        if required_elements:
            structure = row.get("structure")
            if not isinstance(structure, Mapping):
                return [], (
                    "UNKNOWN_CANDIDATE_STRUCTURE_REQUIRED",
                    "typed front structural elements require a candidate structure",
                    {"candidate_id": candidate_id,
                     "required_element_ids": sorted(required_elements)},
                )
            preserved = structure.get("preserved_element_ids")
            if (not isinstance(preserved, Sequence)
                    or isinstance(preserved, (str, bytes))
                    or any(not isinstance(value, str) or not value.strip()
                           for value in preserved)):
                return [], (
                    "UNKNOWN_CANDIDATE_STRUCTURE_ELEMENT_COVERAGE",
                    "candidate.structure.preserved_element_ids must explicitly bind typed front elements",
                    {"candidate_id": candidate_id,
                     "required_element_ids": sorted(required_elements)},
                )
            preserved_ids = {value.strip() for value in preserved}
            missing = sorted(set(required_elements) - preserved_ids)
            if missing:
                return [], (
                    "UNKNOWN_CANDIDATE_STRUCTURE_ELEMENT_DROPPED",
                    "a candidate may not silently drop an observed or proposed typed front element",
                    {"candidate_id": candidate_id,
                     "missing_element_ids": missing,
                     "required_elements": [
                         copy.deepcopy(required_elements[element_id])
                         for element_id in missing
                     ]},
                )
            normalized_structure = copy.deepcopy(dict(structure))
            normalized_structure["preserved_element_ids"] = sorted(preserved_ids)
            row["structure"] = normalized_structure
        violations = _certification_violations(row)
        if violations:
            return [], (
                "UNKNOWN_MANUFACTURING_CERTIFICATION_CLAIM",
                "candidate proposals may not claim manufacturing certification",
                {"candidate_id": candidate_id, "paths": violations},
            )
        row["candidate_id"] = candidate_id
        row["state"] = PROPOSED
        row["rear_hypothesis"]["state"] = PROPOSED
        row["material_hypothesis"]["state"] = PROPOSED
        row["candidate_digest"] = stable_digest(
            {key: value for key, value in row.items()
             if key not in {"candidate_digest", "approval_target_digest"}})
        seen.add(candidate_id)
        candidates.append(row)
    return _sorted_rows(candidates, "candidate_id"), None


def _normalize_artifacts(
        request: Mapping[str, Any],
        candidate_digests: Mapping[str, str],
) -> Tuple[
        Dict[str, Dict[str, Dict[str, Any]]],
        Optional[Tuple[str, str, Dict[str, Any]]]]:
    candidate_ids = set(candidate_digests)
    supplied = request.get("artifacts", {})
    if not isinstance(supplied, Mapping):
        return {}, (
            "UNKNOWN_ARTIFACTS_FORMAT", "artifacts must be keyed by candidate id", {},
        )
    normalized: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for map_candidate_id in sorted(supplied):
        bundle = supplied[map_candidate_id]
        if map_candidate_id not in candidate_ids:
            return {}, (
                "UNKNOWN_ARTIFACT_CANDIDATE_ID",
                "artifacts may only address a declared candidate",
                {"candidate_id": map_candidate_id},
            )
        if not isinstance(bundle, Mapping):
            return {}, (
                "UNKNOWN_ARTIFACT_BUNDLE", "candidate artifact bundle must be an object",
                {"candidate_id": map_candidate_id},
            )
        normalized[map_candidate_id] = {}
        for kind in sorted(bundle):
            artifact = bundle[kind]
            if kind not in ARTIFACT_KINDS or not isinstance(artifact, Mapping):
                return {}, (
                    "UNKNOWN_CANDIDATE_ARTIFACT",
                    "artifact kind must be preview_3d, pattern, or manufacturing",
                    {"candidate_id": map_candidate_id, "kind": str(kind)},
                )
            row = copy.deepcopy(dict(artifact))
            if row.get("candidate_id") != map_candidate_id:
                return {}, (
                    "UNKNOWN_ARTIFACT_CANDIDATE_ID_MISMATCH",
                    "an artifact must be bound to its exact candidate id",
                    {"map_candidate_id": map_candidate_id,
                     "artifact_candidate_id": row.get("candidate_id"),
                     "kind": kind},
                )
            if row.get("kind", kind) != kind:
                return {}, (
                    "UNKNOWN_ARTIFACT_KIND_MISMATCH",
                    "artifact kind does not match its bundle slot",
                    {"candidate_id": map_candidate_id, "kind": kind,
                     "artifact_kind": row.get("kind")},
                )
            expected_candidate_digest = candidate_digests[map_candidate_id]
            supplied_candidate_digest = row.get("candidate_digest")
            if supplied_candidate_digest not in (
                    None, "", expected_candidate_digest):
                return {}, (
                    "UNKNOWN_ARTIFACT_CANDIDATE_DIGEST_MISMATCH",
                    "an artifact must be bound to the current exact candidate digest",
                    {"candidate_id": map_candidate_id, "kind": kind,
                     "claimed": supplied_candidate_digest,
                     "expected": expected_candidate_digest},
                )
            violations = _certification_violations(row)
            if violations:
                return {}, (
                    "UNKNOWN_MANUFACTURING_CERTIFICATION_CLAIM",
                    "front-image artifacts may not claim manufacturing certification",
                    {"candidate_id": map_candidate_id, "kind": kind,
                     "paths": violations},
                )
            payload = {key: value for key, value in row.items()
                       if key not in {"digest", "artifact_digest", "binding_digest",
                                      "candidate_digest"}}
            binding_digest = stable_digest({
                "candidate_id": map_candidate_id,
                "candidate_digest": expected_candidate_digest,
                "kind": kind,
                "payload": payload,
            })
            supplied_digest = row.get("binding_digest")
            if supplied_digest not in (None, "", binding_digest):
                return {}, (
                    "UNKNOWN_STALE_OR_TAMPERED_ARTIFACT_DIGEST",
                    "the supplied binding_digest does not match canonical artifact content",
                    {"candidate_id": map_candidate_id, "kind": kind,
                     "claimed": supplied_digest, "expected": binding_digest},
                )
            row["kind"] = kind
            row["candidate_digest"] = expected_candidate_digest
            row["binding_digest"] = binding_digest
            row["manufacturing_certified"] = False
            normalized[map_candidate_id][kind] = row
    return normalized, None


def _normalize_rounds(request: Mapping[str, Any], max_rounds: int) -> Tuple[
        List[Dict[str, Any]], Optional[Tuple[str, str, Dict[str, Any]]]]:
    supplied = request.get("rounds", [])
    if (not isinstance(supplied, Sequence) or isinstance(supplied, (str, bytes))
            or any(not isinstance(row, Mapping) for row in supplied)):
        return [], (
            "UNKNOWN_REACT_ROUNDS_FORMAT", "rounds must be a list of typed records", {},
        )
    if len(supplied) > max_rounds:
        return [], (
            "UNKNOWN_REACT_ROUND_BUDGET_EXCEEDED",
            "recorded rounds exceed max_rounds",
            {"round_count": len(supplied), "max_rounds": max_rounds},
        )
    normalized: List[Dict[str, Any]] = []
    for expected, source in enumerate(supplied, start=1):
        row = copy.deepcopy(dict(source))
        if row.get("round") != expected:
            return [], (
                "UNKNOWN_REACT_ROUND_SEQUENCE",
                "Vera ReAct rounds must be consecutive and append-only",
                {"expected": expected, "received": row.get("round")},
            )
        if not all(name in row for name in ("observation", "action", "result")):
            return [], (
                "UNKNOWN_REACT_ROUND_RECORD",
                "every completed round needs observation, action, and result",
                {"round": expected},
            )
        payload = {key: value for key, value in row.items()
                   if key != "round_digest"}
        digest = stable_digest(payload)
        if row.get("round_digest") not in (None, "", digest):
            return [], (
                "UNKNOWN_STALE_REACT_ROUND_DIGEST",
                "round_digest does not match canonical round content",
                {"round": expected, "expected": digest,
                 "claimed": row.get("round_digest")},
            )
        row["round_digest"] = digest
        normalized.append(row)
    return normalized, None


def _approval_for(request: Mapping[str, Any], gate: str, *,
                  candidate_id: str, target_digest: str) -> Tuple[
        bool, Optional[Tuple[str, str, Dict[str, Any]]]]:
    approvals = request.get("approvals", {})
    if not isinstance(approvals, Mapping):
        return False, (
            "UNKNOWN_APPROVALS_FORMAT", "approvals must be keyed by gate", {},
        )
    raw = approvals.get(gate)
    if raw is None:
        return False, None
    if not isinstance(raw, Mapping):
        return False, (
            "UNKNOWN_HUMAN_APPROVAL", "approval must be a typed object",
            {"gate": gate},
        )
    by = str(raw.get("by", "")).strip()
    role = str(raw.get("actor_type", "")).upper()
    decision = str(raw.get("decision", "")).upper()
    if role != "HUMAN" or not by or decision != APPROVE:
        return False, (
            "UNKNOWN_NAMED_HUMAN_APPROVAL_REQUIRED",
            "only a named human may approve an exact contract target",
            {"gate": gate, "actor_type": role,
             "claimed_decision": decision},
        )
    if raw.get("candidate_id") != candidate_id:
        return False, (
            "UNKNOWN_APPROVAL_CANDIDATE_ID_MISMATCH",
            "approval candidate_id does not match the selected candidate",
            {"gate": gate, "expected": candidate_id,
             "received": raw.get("candidate_id")},
        )
    if raw.get("target_digest") != target_digest:
        return False, (
            "UNKNOWN_STALE_HUMAN_APPROVAL",
            "approval is stale because its target digest changed",
            {"gate": gate, "expected": target_digest,
             "received": raw.get("target_digest")},
        )
    return True, None


def _react(*, rounds: Sequence[Mapping[str, Any]], max_rounds: int,
           phase: str, observation: str, action: Optional[str],
           allowed_actions: Sequence[str]) -> Dict[str, Any]:
    return {
        "controller": "VERA_DETERMINISTIC_REACT_HARNESS",
        "llm_role": "PROPOSE_ONLY",
        "state_mutation_authority": "VALIDATED_CONTRACT_ACTIONS_ONLY",
        "completed_rounds": copy.deepcopy(list(rounds)),
        "next_round": len(rounds) + 1,
        "max_rounds": max_rounds,
        "phase": phase,
        "observation": observation,
        "next_action": action,
        "allowed_actions": list(allowed_actions),
        "chain_of_thought_required": False,
    }


def _transition(request: Mapping[str, Any], *, decision: str, reason_code: str,
                why: str, state: str, rounds: Sequence[Mapping[str, Any]],
                max_rounds: int, phase: str, action: Optional[str],
                allowed_actions: Sequence[str], requires_human: bool,
                **fields: Any) -> Dict[str, Any]:
    return _result(
        decision=decision, reason_code=reason_code, why=why, request=request,
        state=state, requires_human_approval=requires_human,
        stop_reason=reason_code if decision == STOP else None,
        continue_reason=reason_code if decision == CONTINUE else None,
        react=_react(
            rounds=rounds, max_rounds=max_rounds, phase=phase,
            observation=why, action=action, allowed_actions=allowed_actions,
        ),
        **fields,
    )


def orchestrate(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Compose one front-image job and return its deterministic next decision.

    The function is pure.  It does not call an LLM, inspect pixels, mutate an
    external job, choose among ambiguous candidates, or certify manufacture.
    Callers append a completed ReAct round and resubmit the resulting artifacts
    or digest-bound human approval to advance the contract.
    """

    if not isinstance(request, Mapping):
        request = {"invalid_request": repr(request)}
        return _refusal(
            request, "UNKNOWN_FRONT_IMAGE_REQUEST",
            "request must be a structured mapping",
        )
    try:
        canonical_request = _plain(request)
        stable_digest(canonical_request)
    except (TypeError, ValueError) as exc:
        safe_request = {"schema": str(request.get("schema", ""))}
        return _refusal(
            safe_request, "UNKNOWN_NON_CANONICAL_REQUEST",
            "the request must contain finite canonical JSON values",
            exception_type=type(exc).__name__,
        )
    if canonical_request.get("schema") not in (None, "", REQUEST_SCHEMA):
        return _refusal(
            canonical_request, "UNKNOWN_FRONT_IMAGE_REQUEST_SCHEMA",
            f"expected {REQUEST_SCHEMA}",
        )
    source = canonical_request.get("source")
    if (not isinstance(source, Mapping)
            or not str(source.get("image_id", "")).strip()
            or str(source.get("view", "")).lower() != "front"):
        return _refusal(
            canonical_request, "UNKNOWN_SINGLE_FRONT_IMAGE_REQUIRED",
            "source must identify exactly one front-view garment image",
        )

    max_rounds = canonical_request.get("max_rounds", 8)
    if (isinstance(max_rounds, bool) or not isinstance(max_rounds, int)
            or max_rounds <= 0):
        return _refusal(
            canonical_request, "UNKNOWN_REACT_ROUND_BUDGET",
            "max_rounds must be a positive integer",
        )
    vision, error = _normalize_vision(canonical_request)
    if error:
        code, why, detail = error
        return _refusal(canonical_request, code, why, **detail)
    structural_requirements = _structural_element_requirements(vision)
    measurements, missing_measurements, error = _normalize_measurements(
        canonical_request)
    if error:
        code, why, detail = error
        return _refusal(canonical_request, code, why, **detail)
    candidates, error = _normalize_candidates(
        canonical_request, structural_requirements)
    if error:
        code, why, detail = error
        return _refusal(canonical_request, code, why, **detail)
    candidate_ids = {row["candidate_id"] for row in candidates}
    candidate_digests = {
        row["candidate_id"]: row["candidate_digest"] for row in candidates
    }
    artifacts, error = _normalize_artifacts(
        canonical_request, candidate_digests)
    if error:
        code, why, detail = error
        return _refusal(canonical_request, code, why, **detail)
    rounds, error = _normalize_rounds(canonical_request, max_rounds)
    if error:
        code, why, detail = error
        return _refusal(canonical_request, code, why, **detail)

    common = {
        "source": copy.deepcopy(dict(source)),
        "vision": vision,
        "wearer_measurements": measurements,
        "required_wearer_measurements": list(REQUIRED_WEARER_MEASUREMENTS),
        "candidates": candidates,
        "artifacts": artifacts,
        "required_structure_elements": [
            structural_requirements[element_id]
            for element_id in sorted(structural_requirements)
        ],
        "rear_authority": PROPOSED,
        "material_authority": PROPOSED,
    }
    if missing_measurements:
        return _transition(
            canonical_request, decision=STOP,
            reason_code="STOP_WEARER_MEASUREMENTS_REQUIRED",
            why="target-wearer measurements are required and cannot be inferred as facts from the image",
            state="WAITING_FOR_WEARER_MEASUREMENTS", rounds=rounds,
            max_rounds=max_rounds, phase="MEASUREMENTS",
            action=None, allowed_actions=["SUPPLY_WEARER_MEASUREMENTS"],
            requires_human=True, missing_measurements=missing_measurements,
            **common,
        )
    if len(candidates) < 2:
        if len(rounds) >= max_rounds:
            return _transition(
                canonical_request, decision=STOP,
                reason_code="STOP_REACT_ROUND_BUDGET_EXHAUSTED",
                why="candidate ambiguity is unresolved and no deterministic rounds remain",
                state="ROUND_BUDGET_EXHAUSTED", rounds=rounds,
                max_rounds=max_rounds, phase="CANDIDATE_HYPOTHESES",
                action=None, allowed_actions=["HUMAN_REVIEW"],
                requires_human=True, **common,
            )
        return _transition(
            canonical_request, decision=CONTINUE,
            reason_code="CONTINUE_FRONT_STRUCTURE_ALTERNATIVES_REQUIRED",
            why="one front view requires at least two explicit rear/structure alternatives",
            state="GENERATING_CANDIDATES", rounds=rounds,
            max_rounds=max_rounds, phase="CANDIDATE_HYPOTHESES",
            action="PROPOSE_DISTINCT_STRUCTURE_CANDIDATES",
            allowed_actions=["PROPOSE_DISTINCT_STRUCTURE_CANDIDATES"],
            requires_human=False, **common,
        )

    missing_previews = [candidate_id for candidate_id in sorted(candidate_ids)
                        if "preview_3d" not in artifacts.get(candidate_id, {})]
    if missing_previews:
        if len(rounds) >= max_rounds:
            return _transition(
                canonical_request, decision=STOP,
                reason_code="STOP_REACT_ROUND_BUDGET_EXHAUSTED",
                why="candidate-specific 3D remains missing and no deterministic rounds remain",
                state="ROUND_BUDGET_EXHAUSTED", rounds=rounds,
                max_rounds=max_rounds, phase="CANDIDATE_PREVIEW",
                action=None, allowed_actions=["HUMAN_REVIEW"],
                requires_human=True, missing_candidate_ids=missing_previews,
                **common,
            )
        return _transition(
            canonical_request, decision=CONTINUE,
            reason_code="CONTINUE_CANDIDATE_SPECIFIC_3D_REQUIRED",
            why="every ambiguous candidate needs its own digest-bound 3D preview before selection",
            state="GENERATING_CANDIDATE_PREVIEWS", rounds=rounds,
            max_rounds=max_rounds, phase="CANDIDATE_PREVIEW",
            action="GENERATE_CANDIDATE_SPECIFIC_3D",
            allowed_actions=["GENERATE_CANDIDATE_SPECIFIC_3D"],
            requires_human=False, missing_candidate_ids=missing_previews,
            **common,
        )

    approval_targets: Dict[str, str] = {}
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        approval_targets[candidate_id] = stable_digest({
            "gate": "candidate",
            "candidate_digest": candidate["candidate_digest"],
            "preview_3d_digest": artifacts[candidate_id]["preview_3d"]["binding_digest"],
        })
        candidate["approval_target_digest"] = approval_targets[candidate_id]

    approvals = canonical_request.get("approvals", {})
    candidate_approval = approvals.get("candidate") if isinstance(approvals, Mapping) else None
    if candidate_approval is None:
        return _transition(
            canonical_request, decision=STOP,
            reason_code="STOP_HUMAN_CANDIDATE_APPROVAL_REQUIRED",
            why="Vera may compare proposals, but a human must select an exact candidate and 3D digest",
            state="WAITING_FOR_CANDIDATE_APPROVAL", rounds=rounds,
            max_rounds=max_rounds, phase="CANDIDATE_APPROVAL",
            action=None, allowed_actions=["APPROVE_CANDIDATE", "REVISE_CANDIDATES"],
            requires_human=True, approval_targets=approval_targets,
            **common,
        )
    selected_id = str(candidate_approval.get("candidate_id", "")) \
        if isinstance(candidate_approval, Mapping) else ""
    if selected_id not in candidate_ids:
        return _refusal(
            canonical_request, "UNKNOWN_APPROVAL_CANDIDATE_ID_MISMATCH",
            "candidate approval does not address a declared candidate",
            selected_candidate_id=selected_id,
        )
    approved, error = _approval_for(
        canonical_request, "candidate", candidate_id=selected_id,
        target_digest=approval_targets[selected_id],
    )
    if error or not approved:
        code, why, detail = error or (
            "UNKNOWN_NAMED_HUMAN_APPROVAL_REQUIRED",
            "candidate approval is required", {},
        )
        return _refusal(canonical_request, code, why, **detail)

    selected_artifacts = artifacts.get(selected_id, {})
    pattern = selected_artifacts.get("pattern")
    if pattern is None:
        if len(rounds) >= max_rounds:
            return _transition(
                canonical_request, decision=STOP,
                reason_code="STOP_REACT_ROUND_BUDGET_EXHAUSTED",
                why="the approved candidate has no pattern and no deterministic rounds remain",
                state="ROUND_BUDGET_EXHAUSTED", rounds=rounds,
                max_rounds=max_rounds, phase="PATTERN",
                action=None, allowed_actions=["HUMAN_REVIEW"],
                requires_human=True, selected_candidate_id=selected_id, **common,
            )
        return _transition(
            canonical_request, decision=CONTINUE,
            reason_code="CONTINUE_APPROVED_CANDIDATE_PATTERN_REQUIRED",
            why="the approved candidate must lower to its own geometric pattern",
            state="GENERATING_PATTERN", rounds=rounds, max_rounds=max_rounds,
            phase="PATTERN", action="GENERATE_CANDIDATE_PATTERN",
            allowed_actions=["GENERATE_CANDIDATE_PATTERN"],
            requires_human=False, selected_candidate_id=selected_id, **common,
        )

    pattern_digest = pattern["binding_digest"]
    approved, error = _approval_for(
        canonical_request, "pattern", candidate_id=selected_id,
        target_digest=pattern_digest,
    )
    if error:
        code, why, detail = error
        return _refusal(canonical_request, code, why, **detail)
    if not approved:
        return _transition(
            canonical_request, decision=STOP,
            reason_code="STOP_HUMAN_PATTERN_APPROVAL_REQUIRED",
            why="a human must inspect and approve the exact candidate-specific pattern digest",
            state="WAITING_FOR_PATTERN_APPROVAL", rounds=rounds,
            max_rounds=max_rounds, phase="PATTERN_APPROVAL", action=None,
            allowed_actions=["APPROVE_PATTERN", "REVISE_PATTERN"],
            requires_human=True, selected_candidate_id=selected_id,
            approval_target_digest=pattern_digest, **common,
        )

    manufacturing = selected_artifacts.get("manufacturing")
    if manufacturing is None:
        if len(rounds) >= max_rounds:
            return _transition(
                canonical_request, decision=STOP,
                reason_code="STOP_REACT_ROUND_BUDGET_EXHAUSTED",
                why="manufacturing review is missing and no deterministic rounds remain",
                state="ROUND_BUDGET_EXHAUSTED", rounds=rounds,
                max_rounds=max_rounds, phase="MANUFACTURING_REVIEW",
                action=None, allowed_actions=["HUMAN_REVIEW"],
                requires_human=True, selected_candidate_id=selected_id, **common,
            )
        return _transition(
            canonical_request, decision=CONTINUE,
            reason_code="CONTINUE_MANUFACTURING_REVIEW_REQUIRED",
            why="the approved pattern needs deterministic geometry, sewing, strength, comfort, and donning review",
            state="RUNNING_MANUFACTURING_REVIEW", rounds=rounds,
            max_rounds=max_rounds, phase="MANUFACTURING_REVIEW",
            action="RUN_CANDIDATE_MANUFACTURING_REVIEW",
            allowed_actions=["RUN_CANDIDATE_MANUFACTURING_REVIEW"],
            requires_human=False, selected_candidate_id=selected_id, **common,
        )

    blockers = manufacturing.get("blocking_issues", [])
    if not isinstance(blockers, Sequence) or isinstance(blockers, (str, bytes)):
        return _refusal(
            canonical_request, "UNKNOWN_MANUFACTURING_REVIEW_FORMAT",
            "manufacturing.blocking_issues must be a list",
            selected_candidate_id=selected_id,
        )
    if blockers:
        if len(rounds) >= max_rounds:
            return _transition(
                canonical_request, decision=STOP,
                reason_code="STOP_REACT_ROUND_BUDGET_EXHAUSTED",
                why="manufacturing blockers remain after the bounded Vera ReAct budget",
                state="ROUND_BUDGET_EXHAUSTED", rounds=rounds,
                max_rounds=max_rounds, phase="REPAIR",
                action=None, allowed_actions=["HUMAN_REVIEW", "INCREASE_ROUND_BUDGET"],
                requires_human=True, selected_candidate_id=selected_id,
                blocking_issues=copy.deepcopy(list(blockers)), **common,
            )
        return _transition(
            canonical_request, decision=CONTINUE,
            reason_code="CONTINUE_VERA_REPAIR_ROUND",
            why="typed manufacturing blockers remain; Vera may run one bounded repair and revalidation round",
            state="REPAIRING", rounds=rounds, max_rounds=max_rounds,
            phase="REPAIR", action="REPAIR_AND_REVALIDATE",
            allowed_actions=["REPAIR_AND_REVALIDATE", "REQUEST_HUMAN_REVIEW"],
            requires_human=False, selected_candidate_id=selected_id,
            blocking_issues=copy.deepcopy(list(blockers)), **common,
        )

    manufacturing_digest = manufacturing["binding_digest"]
    approved, error = _approval_for(
        canonical_request, "manufacturing_review", candidate_id=selected_id,
        target_digest=manufacturing_digest,
    )
    if error:
        code, why, detail = error
        return _refusal(canonical_request, code, why, **detail)
    if not approved:
        return _transition(
            canonical_request, decision=STOP,
            reason_code="STOP_HUMAN_MANUFACTURING_REVIEW_REQUIRED",
            why="a blocker-free engineering review still requires human review and physical validation",
            state="WAITING_FOR_MANUFACTURING_REVIEW", rounds=rounds,
            max_rounds=max_rounds, phase="MANUFACTURING_APPROVAL",
            action=None, allowed_actions=["APPROVE_MANUFACTURING_REVIEW", "REVISE_PATTERN"],
            requires_human=True, selected_candidate_id=selected_id,
            approval_target_digest=manufacturing_digest, **common,
        )

    return _transition(
        canonical_request, decision=STOP,
        reason_code="STOP_READY_FOR_PHYSICAL_PROTOTYPE_REVIEW",
        why="the approved proposal bundle is ready for physical prototyping and expert review, not certified manufacture",
        state="READY_FOR_PHYSICAL_PROTOTYPE_REVIEW", rounds=rounds,
        max_rounds=max_rounds, phase="PROTOTYPE_REVIEW", action=None,
        allowed_actions=["BUILD_PHYSICAL_PROTOTYPE", "REVISE_PATTERN"],
        requires_human=True, selected_candidate_id=selected_id,
        approved_artifact_digests={
            "preview_3d": selected_artifacts["preview_3d"]["binding_digest"],
            "pattern": pattern_digest,
            "manufacturing": manufacturing_digest,
        },
        **common,
    )


compose = orchestrate
build_contract = orchestrate


__all__ = [
    "APPROVAL_GATES", "ARTIFACT_KINDS", "REQUEST_SCHEMA",
    "REQUIRED_WEARER_MEASUREMENTS", "SCHEMA", "build_contract", "compose",
    "orchestrate", "stable_digest",
]
