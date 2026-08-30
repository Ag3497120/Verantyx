# -*- coding: utf-8 -*-
"""Disjoint decision contract for garment manufacturing finishes.

Geometry is authoritative only about geometry: it may provide seam topology
and an assembly order, but neither fact says whether a seam is French, felled,
overlocked, or otherwise finished.  The same boundary applies to interfacing
and lining.  This module therefore keeps four evidence lanes separate:

* ``OBSERVED`` -- directly inspected and digest-backed evidence;
* ``REQUESTED`` -- an explicit user/manufacturing requirement;
* ``PROVIDER_SUPPORTED`` -- a rights- and provenance-gated corpus record; and
* ``MODEL_PROPOSED`` -- an unobserved model hypothesis.

Candidates are deterministic and bounded, but never auto-selected.  A named
human may approve an exact candidate digest; that produces ``USER_APPROVED``,
not ``OBSERVED`` and not a manufacturing certification.

The module is intentionally standalone.  It can be connected to the factory
without making an optional corpus, model, or network client a dependency of
the geometric sewing-order path.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCHEMA = "garment.manufacturing-finish-decision.v1"
CANDIDATE_SCHEMA = "garment.manufacturing-finish-candidate.v1"
APPROVAL_SCHEMA = "garment.manufacturing-finish-approval.v1"
RESOLUTION_SCHEMA = "garment.manufacturing-finish-resolution.v1"
TYPED_STOP_SCHEMA = "garment.manufacturing-finish-typed-stop.v1"

CANDIDATES_READY = "CANDIDATES_READY"
RESOLUTION_REQUIRED = "RESOLUTION_REQUIRED"
TYPED_STOP = "TYPED_STOP"
USER_APPROVED = "USER_APPROVED"
CONTESTED = "CONTESTED"

OBSERVED = "OBSERVED"
REQUESTED = "REQUESTED"
PROVIDER_SUPPORTED = "PROVIDER_SUPPORTED"
MODEL_PROPOSED = "MODEL_PROPOSED"
UNKNOWN_UNOBSERVED = "UNKNOWN_UNOBSERVED"

CONNECT_PROVIDER = "CONNECT_PROVIDER"
RECORD_DIRECT_OBSERVATION = "RECORD_DIRECT_OBSERVATION"
ENTER_REQUESTED_VALUE = "ENTER_REQUESTED_VALUE"
ALLOW_ONE_TIME_LLM_PROPOSAL = "ALLOW_ONE_TIME_LLM_PROPOSAL"
KEEP_UNKNOWN = "KEEP_UNKNOWN"

DECISION_FIELDS = ("seam_finish", "interfacing", "lining")
_FIELD_ALIASES = {
    "seam_finish": "seam_finish",
    "seam_finishing": "seam_finish",
    "edge_finish": "seam_finish",
    "finish": "seam_finish",
    "interfacing": "interfacing",
    "interlining": "interfacing",
    "lining": "lining",
}
_DIRECT_AUTHORITY_WORDS = {
    "OBSERVED", "MEASURED", "CALIBRATED", "VALIDATED",
    "MANUFACTURING_CERTIFIED", "FACT",
}
_CHANNEL_WEIGHT = {
    OBSERVED: 10000,
    REQUESTED: 1000,
    PROVIDER_SUPPORTED: 100,
    MODEL_PROPOSED: 10,
}


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _plain(value: Any) -> Any:
    """Copy as canonical JSON data, rejecting non-finite numbers."""
    if isinstance(value, Mapping):
        return {
            str(key): _plain(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if _is_sequence(value):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite values are not valid finish evidence")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    return str(value)


def stable_digest(value: Any) -> str:
    body = json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _token(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_.:-]+", "-", text).strip("-")


def _rows(value: Any) -> List[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if _is_sequence(value):
        return [row for row in value if isinstance(row, Mapping)]
    raise TypeError("finish evidence must be a mapping or a sequence of mappings")


def _normalise_topology(value: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return sorted seam records and typed topology problems.

    The function extracts IDs only.  It deliberately does not inspect seam
    geometry to infer a finishing method.
    """
    if value is None:
        raw: Iterable[Any] = ()
    elif isinstance(value, Mapping):
        raw = value.get("seams", value.get("connections", ()))
    elif _is_sequence(value):
        raw = value
    else:
        return [], [{
            "code": "UNRESOLVABLE_SEAM_TOPOLOGY",
            "why": "seam_topology must be a sequence or an object containing seams",
        }]
    if not _is_sequence(raw):
        return [], [{
            "code": "UNRESOLVABLE_SEAM_TOPOLOGY",
            "why": "the seam collection is not a sequence",
        }]

    seams: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []
    seen = set()
    for index, row in enumerate(raw):
        if isinstance(row, str):
            seam_id = _token(row)
            record = {"seam_id": seam_id, "source": row}
        elif isinstance(row, Mapping):
            seam_id = _token(
                row.get("seam_id", row.get("connection_id", row.get("id"))))
            record = {"seam_id": seam_id, "source": _plain(row)}
        else:
            seam_id = ""
            record = {}
        if not seam_id:
            problems.append({
                "code": "UNRESOLVABLE_SEAM_ID",
                "index": index,
                "why": "every geometric seam needs a stable seam_id",
            })
            continue
        if seam_id in seen:
            continue
        seen.add(seam_id)
        seams.append(record)
    seams.sort(key=lambda row: row["seam_id"])
    problems.sort(key=stable_digest)
    return seams, problems


def _rights_records(row: Mapping[str, Any], provider: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    records: List[Mapping[str, Any]] = []
    for source in (provider, row):
        for key in ("rights", "rights_review"):
            child = source.get(key)
            if isinstance(child, Mapping):
                records.append(child)
        licence = source.get("license", source.get("licence"))
        if isinstance(licence, Mapping):
            records.append(licence)
            child = licence.get("rights")
            if isinstance(child, Mapping):
                records.append(child)
    return records


def _rights_gate(
    row: Mapping[str, Any], provider: Mapping[str, Any], *,
    require_commercial: bool,
) -> Dict[str, Any]:
    if not require_commercial:
        return {
            "required": False, "allowed": True, "state": "NOT_REQUIRED",
            "legal_opinion": False,
        }
    allowed = False
    denied = False
    for rights in _rights_records(row, provider):
        use_authorized = rights.get("use_authorized")
        commercial = rights.get("commercial_use", rights.get("commercial"))
        if use_authorized is False or commercial is False or commercial in {
                "denied", "restricted"}:
            denied = True
        if use_authorized is True or commercial is True or commercial == "allowed":
            allowed = True
    state = "DENIED" if denied else "ALLOWED" if allowed else "UNKNOWN"
    return {
        "required": True,
        "allowed": state == "ALLOWED",
        "state": state,
        "legal_opinion": False,
        "why": (
            "at least one supplied rights record refuses this use" if denied else
            "explicit commercial-use permission was supplied" if allowed else
            "no explicit commercial-use permission was supplied"
        ),
    }


def _provider_provenance_gate(
    row: Mapping[str, Any], provider: Mapping[str, Any],
) -> Dict[str, Any]:
    provenance = row.get("provenance")
    if not isinstance(provenance, Mapping):
        return {
            "allowed": False,
            "missing": ["provenance"],
            "why": "provider support needs a source record and digest",
        }
    source_id = str(
        provenance.get("source_id", provenance.get("provider_id",
            provider.get("provider_id", ""))) or ""
    ).strip()
    record_id = str(
        provenance.get("record_id", provenance.get("asset_id", "")) or ""
    ).strip()
    evidence_digest = str(
        provenance.get("evidence_digest", provenance.get("digest", "")) or ""
    ).strip()
    missing = []
    if not source_id:
        missing.append("source_id")
    if not record_id:
        missing.append("record_id")
    if not evidence_digest:
        missing.append("evidence_digest")
    return {
        "allowed": not missing,
        "missing": missing,
        "source_id": source_id,
        "record_id": record_id,
        "evidence_digest": evidence_digest,
        "why": ("" if not missing else
                "provider evidence is missing lineage fields: " + ", ".join(missing)),
    }


def _direct_observation_gate(row: Mapping[str, Any]) -> Dict[str, Any]:
    provenance = row.get("provenance")
    if not isinstance(provenance, Mapping):
        return {"allowed": False, "why": "direct observation needs provenance"}
    source = str(provenance.get("source_id", provenance.get("source", "")) or "").strip()
    digest = str(provenance.get(
        "evidence_digest", provenance.get("digest", "")) or "").strip()
    method = str(provenance.get("observation_method", "") or "").strip()
    direct = provenance.get("direct_observation") is True
    missing = [name for name, value in (
        ("source", source), ("evidence_digest", digest),
        ("observation_method", method),
    ) if not value]
    if not direct:
        missing.append("direct_observation=true")
    return {
        "allowed": not missing,
        "missing": missing,
        "why": ("" if not missing else
                "observed authority requires direct digest-backed inspection"),
    }


def _normalise_claim(
    row: Mapping[str, Any], channel: str, *, seam_ids: set[str],
    provider: Mapping[str, Any], require_commercial: bool,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return ``(accepted, rejected, terminal_problem)`` for one claim."""
    raw_field = _token(row.get("field", row.get("aspect")))
    field = _FIELD_ALIASES.get(raw_field)
    claimed_authority = str(
        row.get("authority", row.get("state", "")) or ""
    ).upper()
    if field is None:
        problem = {
            "code": "UNSUPPORTED_MANUFACTURING_FINISH_FIELD",
            "field": raw_field or None,
            "channel": channel,
            "why": f"supported fields are {list(DECISION_FIELDS)}",
        }
        if channel in {OBSERVED, REQUESTED}:
            return None, None, problem
        return None, problem, None

    target = _token(row.get("target", row.get("seam_id", "garment")))
    if not target:
        target = "garment"
    value = row.get("value")
    if value in (None, "", [], {}):
        rejected = {
            "code": "EMPTY_MANUFACTURING_FINISH_VALUE",
            "field": field, "target": target, "channel": channel,
        }
        return None, rejected, None
    if row.get("supported") is False or row.get("unresolvable") is True:
        problem = {
            "code": "UNSUPPORTED_MANUFACTURING_FINISH_VALUE",
            "field": field, "target": target, "channel": channel,
            "value": _plain(value),
            "why": str(row.get("why") or "the requested finish is unsupported"),
        }
        if channel in {OBSERVED, REQUESTED}:
            return None, None, problem
        return None, problem, None
    if field == "seam_finish" and target not in seam_ids:
        problem = {
            "code": "UNRESOLVABLE_FINISH_TARGET",
            "field": field, "target": target, "channel": channel,
            "known_seams": sorted(seam_ids),
            "why": "a seam finish cannot bind to a seam absent from topology",
        }
        if channel in {OBSERVED, REQUESTED}:
            return None, None, problem
        return None, problem, None

    rights_gate: Optional[Dict[str, Any]] = None
    evidence_gate: Optional[Dict[str, Any]] = None
    if channel == OBSERVED:
        evidence_gate = _direct_observation_gate(row)
        if not evidence_gate["allowed"]:
            return None, {
                "code": "OBSERVATION_PROVENANCE_REQUIRED",
                "field": field, "target": target, "channel": channel,
                "gate": evidence_gate,
            }, None
    elif channel == REQUESTED:
        provenance = row.get("provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        actor = str(row.get(
            "requested_by", row.get("by", provenance.get("actor", ""))) or ""
        ).strip()
        if not actor:
            return None, {
                "code": "REQUESTING_ACTOR_REQUIRED",
                "field": field, "target": target, "channel": channel,
            }, None
    elif channel == PROVIDER_SUPPORTED:
        if not bool(provider.get("available")):
            return None, {
                "code": "PROVIDER_UNAVAILABLE",
                "field": field, "target": target, "channel": channel,
            }, None
        rights_gate = _rights_gate(
            row, provider, require_commercial=require_commercial)
        evidence_gate = _provider_provenance_gate(row, provider)
        if not rights_gate["allowed"] or not evidence_gate["allowed"]:
            return None, {
                "code": ("PROVIDER_RIGHTS_REQUIRED"
                         if not rights_gate["allowed"]
                         else "PROVIDER_PROVENANCE_REQUIRED"),
                "field": field, "target": target, "channel": channel,
                "rights_gate": rights_gate,
                "provenance_gate": evidence_gate,
            }, None

    accepted_authority = channel
    direct_claim_refused = (
        claimed_authority in _DIRECT_AUTHORITY_WORDS
        and claimed_authority != accepted_authority
    )
    provenance = row.get("provenance")
    provenance = _plain(provenance) if isinstance(provenance, Mapping) else {}
    if channel == MODEL_PROPOSED:
        provenance.setdefault("model_id", str(row.get("model_id") or "unspecified-model"))
        provenance.setdefault("output_digest", stable_digest(_plain(row)))
    source_id = str(
        provenance.get("source_id", provenance.get("provider_id",
            provenance.get("model_id", row.get("requested_by", row.get("by", channel)))))
        or channel
    )
    source_record = str(
        provenance.get("record_id", provenance.get("asset_id",
            provenance.get("evidence_digest", provenance.get("output_digest", ""))))
        or stable_digest(_plain(row))
    )
    claim = {
        "field": field,
        "target": target,
        "value": _plain(value),
        "value_digest": stable_digest(_plain(value)),
        "channel": channel,
        "state": accepted_authority,
        "accepted_authority": accepted_authority,
        "claimed_authority": claimed_authority or None,
        "authority_promotion_refused": direct_claim_refused,
        "observed": channel == OBSERVED,
        "observation_state": OBSERVED if channel == OBSERVED else UNKNOWN_UNOBSERVED,
        "provenance": provenance,
        "source_key": f"{channel}:{source_id}:{source_record}",
        "rights_gate": rights_gate,
        "evidence_gate": evidence_gate,
        "fact_promotions": [],
    }
    claim["claim_digest"] = stable_digest(claim)
    claim["claim_id"] = str(row.get("claim_id") or claim["claim_digest"][:16])
    return claim, None, None


def _required_keys(
    seams: Sequence[Mapping[str, Any]], claims: Sequence[Mapping[str, Any]],
) -> List[Tuple[str, str]]:
    keys = {("seam_finish", str(row["seam_id"])) for row in seams}
    keys.update({("interfacing", "garment"), ("lining", "garment")})
    keys.update((str(row["field"]), str(row["target"])) for row in claims)
    return sorted(keys)


def _alternatives(
    claims: Sequence[Mapping[str, Any]], required: Sequence[Tuple[str, str]],
) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    grouped: Dict[Tuple[str, str], Dict[str, List[Mapping[str, Any]]]] = {
        key: {} for key in required
    }
    for claim in claims:
        key = (str(claim["field"]), str(claim["target"]))
        grouped.setdefault(key, {}).setdefault(
            str(claim["value_digest"]), []).append(claim)

    output: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for key in required:
        rows: List[Dict[str, Any]] = []
        for value_digest, support in grouped.get(key, {}).items():
            ordered = sorted(support, key=lambda row: str(row["claim_digest"]))
            states = sorted({str(row["state"]) for row in ordered})
            source_keys = sorted({str(row["source_key"]) for row in ordered})
            score = sum(
                _CHANNEL_WEIGHT[state]
                for state in _CHANNEL_WEIGHT if state in states
            ) + min(len(source_keys), 9)
            record = {
                "field": key[0], "target": key[1],
                "value": _plain(ordered[0]["value"]),
                "value_digest": value_digest,
                "supporting_states": states,
                "supporting_claim_ids": [str(row["claim_id"]) for row in ordered],
                "supporting_claim_digests": [
                    str(row["claim_digest"]) for row in ordered
                ],
                "independent_source_keys": source_keys,
                "rank_score": score,
                "observed_support_present": OBSERVED in states,
                "automatic_selection_allowed": False,
            }
            record["alternative_digest"] = stable_digest(record)
            rows.append(record)
        rows.sort(key=lambda row: (-int(row["rank_score"]),
                                  str(row["alternative_digest"])))
        output[key] = rows
    return output


def _contests(
    alternatives: Mapping[Tuple[str, str], Sequence[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    contested = []
    for key in sorted(alternatives):
        rows = alternatives[key]
        if len(rows) <= 1:
            continue
        record = {
            "state": CONTESTED,
            "field": key[0], "target": key[1],
            "alternatives": [_plain(row) for row in rows],
            "no_averaging": True,
            "auto_resolution": False,
        }
        record["contest_digest"] = stable_digest(record)
        contested.append(record)
    return contested


def _bounded_candidates(
    alternatives: Mapping[Tuple[str, str], Sequence[Mapping[str, Any]]],
    required: Sequence[Tuple[str, str]], *, subject_digest: str,
    max_candidates: int,
) -> List[Dict[str, Any]]:
    if any(not alternatives.get(key) for key in required):
        return []
    beam: List[Tuple[int, Dict[str, Any]]] = [(0, {})]
    for field, target in required:
        decision_key = f"{field}:{target}"
        expanded: List[Tuple[int, Dict[str, Any]]] = []
        for score, selections in beam:
            for option in alternatives[(field, target)]:
                selected = dict(selections)
                selected[decision_key] = {
                    key: _plain(option[key]) for key in (
                        "field", "target", "value", "value_digest",
                        "supporting_states", "supporting_claim_ids",
                        "supporting_claim_digests", "alternative_digest",
                    )
                }
                expanded.append((score + int(option["rank_score"]), selected))
        expanded.sort(key=lambda item: (-item[0], stable_digest(item[1])))
        beam = expanded[:max(max_candidates * 4, max_candidates)]

    candidates = []
    seen = set()
    for score, selections in beam:
        candidate_core = {
            "schema": CANDIDATE_SCHEMA,
            "subject_digest": subject_digest,
            "state": "BOUNDED_CANDIDATE",
            "selections": _plain(selections),
            "rank_score": score,
            "observed": False,
            "observation_state": UNKNOWN_UNOBSERVED,
            "auto_selected": False,
            "requires_human_approval": True,
            "manufacturing_certified": False,
        }
        digest = stable_digest(candidate_core)
        if digest in seen:
            continue
        seen.add(digest)
        candidate_core["candidate_digest"] = digest
        candidates.append(candidate_core)
    candidates.sort(key=lambda row: (-int(row["rank_score"]),
                                     str(row["candidate_digest"])))
    candidates = candidates[:max_candidates]
    for index, row in enumerate(candidates, start=1):
        row["rank"] = index
    return candidates


def _resolution_request(
    missing: Sequence[Tuple[str, str]], provider_state: str,
) -> Dict[str, Any]:
    fields = [{"field": field, "target": target} for field, target in missing]
    options = [
        {
            "action": CONNECT_PROVIDER,
            "capability": "SEAM_FINISHING_CONSTRUCTION",
            "result_authority": PROVIDER_SUPPORTED,
            "requires_rights_and_provenance_gate": True,
        },
        {
            "action": RECORD_DIRECT_OBSERVATION,
            "result_authority": OBSERVED,
            "requires_digest_backed_direct_inspection": True,
        },
        {
            "action": ENTER_REQUESTED_VALUE,
            "result_authority": REQUESTED,
            "requires_named_human": True,
        },
        {
            "action": ALLOW_ONE_TIME_LLM_PROPOSAL,
            "result_authority": MODEL_PROPOSED,
            "requires_explicit_consent": True,
            "cannot_promote_to": sorted(_DIRECT_AUTHORITY_WORDS),
        },
        {
            "action": KEEP_UNKNOWN,
            "result_authority": UNKNOWN_UNOBSERVED,
            "can_produce_complete_manufacturing_plan": False,
        },
        {
            "action": TYPED_STOP,
            "terminal_for_this_attempt": True,
            "state_mutation_allowed": False,
        },
    ]
    request = {
        "schema": RESOLUTION_SCHEMA,
        "verdict": "UNKNOWN_MANUFACTURING_FINISH_DECISION_REQUIRED",
        "state": "AWAITING_HUMAN_OR_PROVIDER",
        "provider_state": provider_state,
        "missing_decisions": fields,
        "resolution_options": options,
        "actionable": True,
    }
    request["request_digest"] = stable_digest(request)
    return request


def _typed_stop(problems: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    stop = {
        "schema": TYPED_STOP_SCHEMA,
        "verdict": TYPED_STOP,
        "code": "TYPED_STOP_UNSUPPORTED_MANUFACTURING_FINISH",
        "problems": sorted((_plain(row) for row in problems), key=stable_digest),
        "terminal_for_this_attempt": True,
        "state_mutation_allowed": False,
        "resumable_by": [
            "SUPPLY_TYPED_SEAM_TOPOLOGY",
            "REPLACE_UNSUPPORTED_REQUIREMENT",
            CONNECT_PROVIDER,
        ],
    }
    stop["stop_digest"] = stable_digest(stop)
    return stop


def build_manufacturing_finish_decision(
    *, subject_digest: str, seam_topology: Any, sewing_order: Any,
    observed: Any = (), requested: Any = (), provider_supported: Any = (),
    model_proposed: Any = (), provider: Optional[Mapping[str, Any]] = None,
    max_candidates: int = 8, require_commercial_rights: bool = True,
) -> Dict[str, Any]:
    """Build a deterministic, proposal-only finishing decision.

    ``seam_topology`` and ``sewing_order`` are retained as geometric context.
    They are never interpreted as evidence for a finish, interfacing, or
    lining choice.  Complete candidates are emitted only when every geometric
    seam plus garment-level interfacing and lining has an explicit value from
    one of the four evidence lanes.
    """
    subject_digest = str(subject_digest or "").strip()
    if not subject_digest:
        raise ValueError("subject_digest must be non-empty")
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int):
        raise TypeError("max_candidates must be an integer")
    if not 1 <= max_candidates <= 32:
        raise ValueError("max_candidates must be between 1 and 32")
    provider_record = _plain(dict(provider or {}))
    seams, terminal_problems = _normalise_topology(seam_topology)
    seam_ids = {str(row["seam_id"]) for row in seams}

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    lanes = (
        (OBSERVED, observed),
        (REQUESTED, requested),
        (PROVIDER_SUPPORTED, provider_supported),
        (MODEL_PROPOSED, model_proposed),
    )
    for channel, values in lanes:
        for row in _rows(values):
            claim, refusal, terminal = _normalise_claim(
                row, channel, seam_ids=seam_ids, provider=provider_record,
                require_commercial=bool(require_commercial_rights),
            )
            if claim is not None:
                accepted.append(claim)
            if refusal is not None:
                rejected.append(refusal)
            if terminal is not None:
                terminal_problems.append(terminal)
    accepted.sort(key=lambda row: str(row["claim_digest"]))
    rejected.sort(key=stable_digest)
    terminal_problems.sort(key=stable_digest)

    required = _required_keys(seams, accepted)
    alternatives = _alternatives(accepted, required)
    missing = [key for key in required if not alternatives.get(key)]
    contested = _contests(alternatives)
    candidates = ([] if terminal_problems else _bounded_candidates(
        alternatives, required, subject_digest=subject_digest,
        max_candidates=max_candidates,
    ))

    valid_provider_claims = [
        row for row in accepted if row["channel"] == PROVIDER_SUPPORTED
    ]
    rejected_provider = [
        row for row in rejected if row.get("channel") == PROVIDER_SUPPORTED
    ]
    if valid_provider_claims:
        provider_state = "READY_WITH_RIGHTS_GATED_EVIDENCE"
    elif rejected_provider:
        provider_state = "RIGHTS_OR_PROVENANCE_REFUSED"
    elif provider_record.get("available"):
        provider_state = "READY_NO_FINISH_EVIDENCE"
    else:
        provider_state = "UNAVAILABLE"

    typed_stop = _typed_stop(terminal_problems) if terminal_problems else None
    resolution = (
        None if typed_stop or not missing else
        _resolution_request(missing, provider_state)
    )
    verdict = (
        TYPED_STOP if typed_stop else
        RESOLUTION_REQUIRED if missing else
        CANDIDATES_READY
    )
    geometry_context = {
        "seam_topology": seams,
        "sewing_order": _plain(sewing_order),
        "authority_scope": "SEAM_TOPOLOGY_AND_ASSEMBLY_ORDER_ONLY",
        "can_select_seam_finish": False,
        "can_select_interfacing": False,
        "can_select_lining": False,
    }
    alternatives_json = {
        f"{field}:{target}": [_plain(row) for row in alternatives[(field, target)]]
        for field, target in sorted(alternatives)
    }
    decision = {
        "schema": SCHEMA,
        "verdict": verdict,
        "subject_digest": subject_digest,
        "geometry_context": geometry_context,
        "evidence_lanes": {
            channel: [
                _plain(row) for row in accepted if row["channel"] == channel
            ] for channel, _ in lanes
        },
        "accepted_claims": [_plain(row) for row in accepted],
        "rejected_claims": [_plain(row) for row in rejected],
        "required_decisions": [
            {"field": field, "target": target} for field, target in required
        ],
        "missing_decisions": [
            {"field": field, "target": target} for field, target in missing
        ],
        "alternatives": alternatives_json,
        "contested": contested,
        "conflicts_preserved": True,
        "no_averaging": True,
        "candidates": candidates,
        "candidate_limit": max_candidates,
        "selected_candidate": None,
        "automatic_selection_allowed": False,
        "provider_state": provider_state,
        "resolution_request": resolution,
        "typed_stop": typed_stop,
        "fact_promotions": [],
    }
    decision["decision_digest"] = stable_digest(decision)
    return decision


def approve_manufacturing_finish_candidate(
    decision: Mapping[str, Any], *, candidate_digest: str,
    approved_by: str, provenance: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Approve one exact candidate without promoting it to observation."""
    if decision.get("schema") != SCHEMA:
        return _typed_stop([{
            "code": "UNRESOLVABLE_FINISH_DECISION_SCHEMA",
            "why": "approval requires a manufacturing finish decision",
        }])
    approved_by = str(approved_by or "").strip()
    if not approved_by:
        return _typed_stop([{
            "code": "UNRESOLVABLE_FINISH_APPROVER",
            "why": "a named human approver is required",
        }])
    if decision.get("verdict") != CANDIDATES_READY:
        return _typed_stop([{
            "code": "UNRESOLVABLE_FINISH_DECISION",
            "why": "all required finishing decisions must have bounded candidates",
            "decision_verdict": decision.get("verdict"),
        }])
    wanted = str(candidate_digest or "")
    candidate = next((
        row for row in decision.get("candidates", ())
        if isinstance(row, Mapping) and row.get("candidate_digest") == wanted
    ), None)
    if candidate is None:
        return _typed_stop([{
            "code": "UNRESOLVABLE_FINISH_CANDIDATE",
            "why": "the candidate digest is absent from this decision",
            "candidate_digest": wanted,
        }])
    approval = {
        "schema": APPROVAL_SCHEMA,
        "verdict": USER_APPROVED,
        "state": USER_APPROVED,
        "subject_digest": decision.get("subject_digest"),
        "decision_digest": decision.get("decision_digest"),
        "candidate_digest": wanted,
        "selections": _plain(candidate.get("selections", {})),
        "approved_by": approved_by,
        "provenance": _plain(dict(provenance or {})),
        "observed": False,
        "observation_state": UNKNOWN_UNOBSERVED,
        "manufacturing_certified": False,
        "strength_validated": False,
        "conflicts_at_approval": _plain(decision.get("contested", [])),
        "authority_note": (
            "human approval selects a manufacturing instruction; it does not "
            "turn the instruction into an observation"
        ),
        "fact_promotions": [],
    }
    approval["approval_digest"] = stable_digest(approval)
    return approval


__all__ = [
    "ALLOW_ONE_TIME_LLM_PROPOSAL", "CANDIDATES_READY", "CONNECT_PROVIDER",
    "CONTESTED", "DECISION_FIELDS", "ENTER_REQUESTED_VALUE", "KEEP_UNKNOWN",
    "MODEL_PROPOSED", "OBSERVED", "PROVIDER_SUPPORTED",
    "RECORD_DIRECT_OBSERVATION", "REQUESTED", "RESOLUTION_REQUIRED", "SCHEMA",
    "TYPED_STOP", "UNKNOWN_UNOBSERVED", "USER_APPROVED",
    "approve_manufacturing_finish_candidate",
    "build_manufacturing_finish_decision", "stable_digest",
]
