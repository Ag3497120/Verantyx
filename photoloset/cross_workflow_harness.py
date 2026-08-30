# -*- coding: utf-8 -*-
"""Typed Cross harness shared by garment-generation state machines.

The harness is deliberately an orchestration boundary, not another solver.
It keeps evidence, directional/physical stage artifacts, and proof obligations
separate while binding them with deterministic digests.  Missing information
is never converted into a model-authored fact: callers receive a typed
resolution request, and model completion requires a digest-bound human consent
artifact whose authority ceiling remains ``PROPOSED``.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .cross import CrossStore
from .cross_lattice import typed_result_digest
from . import (manufacturing_finish_contract, physical_calibration_contract,
               physics_proof_cross, reconstruction_claim_contract)


SCHEMA = "garment.cross-workflow-harness.v1"
RESOLUTION_SCHEMA = "garment.cross-resolution-request.v1"
CONSENT_SCHEMA = "garment.model-proposal-consent.v1"
STOP_SCHEMA = "garment.typed-stop.v1"
CAPABILITY_GATE_SCHEMA = "garment.cross-capability-gate.v1"
CONTRACT_ADMISSION_SCHEMA = "garment.authoritative-contract-admission.v1"

OBSERVED = "OBSERVED"
PROPOSED = "PROPOSED"
INFERRED = "INFERRED"
CONTESTED = "CONTESTED"
UNKNOWN = "UNKNOWN"
EVIDENCE_STATES = frozenset({OBSERVED, PROPOSED, INFERRED,
                             CONTESTED, UNKNOWN})

HUMAN_INPUT = "HUMAN_INPUT"
HUMAN_GEOMETRY_EDIT = "HUMAN_GEOMETRY_EDIT"
LLM_PROPOSAL_WITH_CONSENT = "LLM_PROPOSAL_WITH_CONSENT"
PROVIDER_CONNECT = "PROVIDER_CONNECT"
TYPED_STOP = "TYPED_STOP"
RESOLUTION_CHOICES = (
    HUMAN_INPUT,
    HUMAN_GEOMETRY_EDIT,
    LLM_PROPOSAL_WITH_CONSENT,
    PROVIDER_CONNECT,
    TYPED_STOP,
)

MEASURED_INPUT = "MEASURED_INPUT"
HUMAN_EDIT = "HUMAN_EDIT"
CONNECT_PROVIDER = "CONNECT_PROVIDER"
CONSENTED_LLM_PROPOSAL = "CONSENTED_LLM_PROPOSAL"
BOUNDED_ALTERNATIVES = "BOUNDED_ALTERNATIVES"
RESOLUTION_PATHS = (
    MEASURED_INPUT,
    HUMAN_EDIT,
    CONNECT_PROVIDER,
    CONSENTED_LLM_PROPOSAL,
    BOUNDED_ALTERNATIVES,
    TYPED_STOP,
)
_PATH_TO_CHOICE = {
    MEASURED_INPUT: HUMAN_INPUT,
    HUMAN_EDIT: HUMAN_GEOMETRY_EDIT,
    CONNECT_PROVIDER: PROVIDER_CONNECT,
    CONSENTED_LLM_PROPOSAL: LLM_PROPOSAL_WITH_CONSENT,
    BOUNDED_ALTERNATIVES: BOUNDED_ALTERNATIVES,
    TYPED_STOP: TYPED_STOP,
}
_CHOICE_TO_PATH = {
    HUMAN_INPUT: MEASURED_INPUT,
    HUMAN_GEOMETRY_EDIT: HUMAN_EDIT,
    PROVIDER_CONNECT: CONNECT_PROVIDER,
    LLM_PROPOSAL_WITH_CONSENT: CONSENTED_LLM_PROPOSAL,
    TYPED_STOP: TYPED_STOP,
}
_PATH_ORDER = {path: index for index, path in enumerate(RESOLUTION_PATHS)}

CAPABILITY_GATES: Dict[str, Dict[str, Any]] = {
    "REAR_FROM_SINGLE_FRONT": {
        "verdict": "UNKNOWN_REAR_UNOBSERVED_FROM_SINGLE_FRONT",
        "stage": "REAR_RECONSTRUCTION",
        "missing_fields": ["rear.surface", "rear.construction"],
        "observed_evidence_types": ["REAR_IMAGE", "MULTIVIEW_SCAN"],
        "paths": [HUMAN_EDIT, CONNECT_PROVIDER, CONSENTED_LLM_PROPOSAL,
                  BOUNDED_ALTERNATIVES, TYPED_STOP],
        "recommended_path": BOUNDED_ALTERNATIVES,
    },
    "MEASURED_MATERIAL": {
        "verdict": "UNKNOWN_MEASURED_MATERIAL_PROPERTIES",
        "stage": "MATERIAL_CALIBRATION",
        "missing_fields": ["material.composition", "material.thickness",
                           "material.stretch", "material.friction",
                           "material.bending"],
        "observed_evidence_types": ["MATERIAL_LAB_MEASUREMENT",
                                    "NAMED_MATERIAL_DATASHEET"],
        "paths": [MEASURED_INPUT, CONNECT_PROVIDER,
                  CONSENTED_LLM_PROPOSAL, BOUNDED_ALTERNATIVES,
                  TYPED_STOP],
        "recommended_path": MEASURED_INPUT,
    },
    "BODY_DIMENSIONS_FROM_IMAGE": {
        "verdict": "UNKNOWN_BODY_DIMENSIONS_NOT_MEASURED_FROM_IMAGE",
        "stage": "BODY_FIT",
        "missing_fields": ["body.height", "body.chest", "body.waist",
                           "body.hip", "body.length"],
        "observed_evidence_types": ["TAPE_MEASUREMENT", "BODY_SCAN"],
        "paths": [MEASURED_INPUT, HUMAN_EDIT, CONNECT_PROVIDER,
                  CONSENTED_LLM_PROPOSAL, BOUNDED_ALTERNATIVES,
                  TYPED_STOP],
        "recommended_path": MEASURED_INPUT,
    },
    "ARBITRARY_GARMENT_FIDELITY": {
        "verdict": "UNKNOWN_ARBITRARY_GARMENT_FIDELITY_GUARANTEE",
        "stage": "FIDELITY_REVIEW",
        "missing_fields": ["fidelity.visible_parts", "fidelity.occlusions",
                           "fidelity.layer_topology"],
        "observed_evidence_types": ["MULTIVIEW_GARMENT_SCAN",
                                    "HUMAN_APPROVED_TARGET"],
        "paths": [HUMAN_EDIT, CONNECT_PROVIDER, BOUNDED_ALTERNATIVES,
                  TYPED_STOP],
        "recommended_path": HUMAN_EDIT,
    },
    "COMPLETE_PATTERN_GUARANTEE": {
        "verdict": "UNKNOWN_COMPLETE_PATTERN_GUARANTEE",
        "stage": "PATTERN_VALIDATION",
        "missing_fields": ["pattern.all_pieces", "pattern.seam_topology",
                           "pattern.donning_path", "pattern.sewability"],
        "observed_evidence_types": ["PHYSICAL_TOILE_VALIDATION",
                                    "QUALIFIED_PATTERN_REVIEW"],
        "paths": [HUMAN_EDIT, CONNECT_PROVIDER, BOUNDED_ALTERNATIVES,
                  TYPED_STOP],
        "recommended_path": HUMAN_EDIT,
    },
    "SEAM_FINISH_CONSTRUCTION": {
        "verdict": "UNKNOWN_SEAM_FINISH_CONSTRUCTION",
        "stage": "SEWING_METHOD",
        "missing_fields": ["sewing.seam_finish", "sewing.interfacing",
                           "sewing.lining", "sewing.machine_setup"],
        "observed_evidence_types": ["APPROVED_SEWING_SPEC",
                                    "RIGHTS_CLEARED_CONSTRUCTION_RECORD"],
        "paths": [MEASURED_INPUT, HUMAN_EDIT, CONNECT_PROVIDER,
                  CONSENTED_LLM_PROPOSAL, BOUNDED_ALTERNATIVES,
                  TYPED_STOP],
        "recommended_path": CONNECT_PROVIDER,
    },
    "REAL_CLOTH_ERROR_GUARANTEE": {
        "verdict": "UNKNOWN_REAL_CLOTH_ERROR_GUARANTEE",
        "stage": "PHYSICAL_VALIDATION",
        "missing_fields": ["validation.real_cloth_trials",
                           "validation.error_bound",
                           "validation.test_population"],
        "observed_evidence_types": ["CALIBRATED_REAL_CLOTH_TRIAL"],
        "paths": [MEASURED_INPUT, CONNECT_PROVIDER, TYPED_STOP],
        "recommended_path": TYPED_STOP,
    },
    "WIND_TUNNEL_CALIBRATION": {
        "verdict": "UNKNOWN_WIND_TUNNEL_CALIBRATION",
        "stage": "AERODYNAMIC_CALIBRATION",
        "missing_fields": ["wind_tunnel.measurements",
                           "wind_tunnel.boundary_conditions",
                           "wind_tunnel.calibration_digest"],
        "observed_evidence_types": ["WIND_TUNNEL_MEASUREMENT",
                                    "VALIDATED_DNS_DATASET"],
        "paths": [MEASURED_INPUT, CONNECT_PROVIDER, TYPED_STOP],
        "recommended_path": CONNECT_PROVIDER,
    },
    "CONNECTED_FASHION_SEARCH": {
        "verdict": "UNKNOWN_FASHION_SEARCH_PROVIDER_NOT_CONNECTED",
        "stage": "RETRIEVAL",
        "missing_fields": ["retrieval.provider", "retrieval.index_digest",
                           "retrieval.rights_provenance"],
        "observed_evidence_types": ["CONNECTED_SEARCH_PROVIDER",
                                    "LOCAL_RIGHTS_CLEARED_INDEX"],
        "paths": [CONNECT_PROVIDER, BOUNDED_ALTERNATIVES, TYPED_STOP],
        "recommended_path": CONNECT_PROVIDER,
    },
}

_MODEL_SOURCES = frozenset({
    "AI", "AI_MODEL", "LLM", "MODEL", "VLM", "VISION_MODEL",
    "RETRIEVAL_MODEL", "FASHION_SIGLIP", "MARQO_FASHION_SIGLIP",
    "QWEN", "GPT", "CLAUDE", "GEMINI", "MISTRAL", "LLAMA",
})
_STATE_KIND = {
    OBSERVED: "measured",
    INFERRED: "derived",
    PROPOSED: "proposed",
}
_STATE_ORDER = {OBSERVED: 0, INFERRED: 1, PROPOSED: 2,
                CONTESTED: 3, UNKNOWN: 4}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "as_dict"):
        return _plain(value.as_dict())
    raise TypeError("Cross workflow values must be JSON serialisable: "
                    + type(value).__name__)


def stable_digest(value: Any) -> str:
    encoded = json.dumps(_plain(value), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _without_digest(value: Mapping[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(dict(value))
    out.pop("workflow_digest", None)
    out.pop("semantic_digest", None)
    return out


def _semantic_payload(workflow: Mapping[str, Any]) -> Dict[str, Any]:
    """The order-independent meaning of a workflow.

    Event history remains order-sensitive in ``workflow_digest``.  Evidence
    claims, physical layers, and proof reports are separately sorted here so
    equivalent concurrent ingestion has a stable semantic identity.
    """
    return {
        "schema": workflow.get("schema"),
        "owner_id": workflow.get("owner_id"),
        "contract": workflow.get("reduction_contract"),
        "claims": sorted(
            copy.deepcopy(list(workflow.get("evidence", {}).get("claims", ()))),
            key=lambda row: str(row.get("claim_digest", ""))),
        "physical_layers": sorted(
            copy.deepcopy(list(workflow.get("physical", {}).get("layers", ()))),
            key=lambda row: str(row.get("layer_digest", ""))),
        "proof_reports": sorted(
            copy.deepcopy(list(workflow.get("proof", {}).get("reports", ()))),
            key=lambda row: str(row.get("proof_digest", ""))),
        "consents": sorted(
            copy.deepcopy(list(workflow.get("consents", ()))),
            key=lambda row: str(row.get("consent_digest", ""))),
        "claim_unknowns": sorted(
            copy.deepcopy(list(workflow.get("claim_unknowns", ()))),
            key=lambda row: str(row.get("unknown_digest", ""))),
        "obligations": sorted(
            copy.deepcopy(list(workflow.get("obligations", ()))),
            key=lambda row: str(row.get("request_id", ""))),
        "resolutions": sorted(
            copy.deepcopy(list(workflow.get("resolutions", ()))),
            key=lambda row: str(row.get("resolution_digest", ""))),
        "typed_stops": sorted(
            copy.deepcopy(list(workflow.get("typed_stops", ()))),
            key=lambda row: str(row.get("stop_digest", ""))),
        "capability_gate_history": sorted(
            copy.deepcopy(list(workflow.get("capability_gate_history", ()))),
            key=lambda row: str(row.get("gate_digest", ""))),
    }


def _seal(workflow: Dict[str, Any]) -> Dict[str, Any]:
    workflow["semantic_digest"] = stable_digest(_semantic_payload(workflow))
    workflow["workflow_digest"] = stable_digest(_without_digest(workflow))
    return workflow


def new_workflow(owner_id: str, *, source_schema: Optional[str] = None
                 ) -> Dict[str, Any]:
    owner = str(owner_id or "").strip()
    if not owner:
        raise ValueError("Cross workflow owner_id must be non-empty")
    workflow = {
        "schema": SCHEMA,
        "owner_id": owner,
        "revision": 0,
        "evidence": {
            "schema": "garment.evidence-cross-channel.v1",
            "claims": [],
            "resolutions": {},
            "cross": CrossStore().to_dict(),
            "cross_verification": {"verdict": "ANSWER"},
        },
        "physical": {
            "schema": "garment.physical-cross-channel.v1",
            "layers": [],
            "latest_layer_digest": None,
        },
        "proof": {
            "schema": "garment.proof-cross-channel.v1",
            "reports": [],
            "latest_proof_digest": None,
        },
        "obligations": [],
        "resolutions": [],
        "consents": [],
        "typed_stops": [],
        "claim_unknowns": [],
        "capability_gate_history": [],
        "stage_history": [],
        "reduction_contract": {
            "read_model": "SAME_OLD_STATE",
            "reduction": "CANONICAL_ORDER_DETERMINISTIC_REDUCE",
            "conflict_policy": "PRESERVE_DISAGREEMENT_NO_AVERAGING",
            "model_authority_ceiling": PROPOSED,
            "evidence_states": sorted(EVIDENCE_STATES),
        },
        "migration": {
            "source_schema": source_schema,
            "mode": "LOSSLESS_ADD_ONLY" if source_schema else "NATIVE",
        },
    }
    return _seal(workflow)


def _validate_current(workflow: Mapping[str, Any]) -> None:
    if workflow.get("schema") != SCHEMA:
        raise ValueError("Cross workflow schema is not supported")
    required = ("evidence", "physical", "proof", "obligations",
                "resolutions", "consents", "typed_stops", "stage_history")
    missing = [key for key in required if key not in workflow]
    if missing:
        raise ValueError("Cross workflow is missing: " + ", ".join(missing))
    supplied = workflow.get("workflow_digest")
    if supplied and supplied != stable_digest(_without_digest(workflow)):
        raise ValueError("Cross workflow digest does not match its contents")


def migrate_workflow(value: Any, owner_id: str, *,
                     source_schema: Optional[str] = None) -> Dict[str, Any]:
    """Load the current schema or losslessly wrap an older document.

    A missing harness is an expected legacy case.  A malformed current harness
    is refused instead of being silently repaired.  The only recognised legacy
    payload fields are append-only claims/obligations; unknown legacy fields are
    retained under ``migration.legacy_payload`` and never interpreted as facts.
    """
    if value is None:
        return new_workflow(owner_id, source_schema=source_schema)
    if not isinstance(value, Mapping):
        raise ValueError("Cross workflow must be an object")
    if value.get("schema") == SCHEMA:
        workflow = copy.deepcopy(dict(value))
        _validate_current(workflow)
        if str(workflow.get("owner_id", "")) != str(owner_id):
            raise ValueError("Cross workflow owner does not match its job")
        # ``claim_unknowns`` was added as an append-only minor field.  Validate
        # old digest before adding minor fields, then reseal the migrated
        # document.  Neither field reinterprets existing domain state.
        workflow.setdefault("claim_unknowns", [])
        workflow.setdefault("capability_gate_history", [])
        return _seal(workflow)

    workflow = new_workflow(owner_id,
                            source_schema=str(value.get("schema") or
                                              source_schema or "legacy"))
    workflow["migration"]["legacy_payload"] = _plain(value)
    legacy_claims = value.get("claims", ())
    if isinstance(legacy_claims, Sequence) and not isinstance(
            legacy_claims, (str, bytes)):
        workflow = _ingest_claims(workflow, legacy_claims,
                                  default_source="legacy-document")
    legacy_obligations = value.get("obligations", ())
    if isinstance(legacy_obligations, Sequence) and not isinstance(
            legacy_obligations, (str, bytes)):
        workflow["obligations"] = [_plain(row) for row in legacy_obligations
                                   if isinstance(row, Mapping)]
    workflow["revision"] = 0
    return _seal(workflow)


def migrate_document(document: Mapping[str, Any], *,
                     owner_id: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(document, Mapping):
        raise ValueError("document must be an object")
    out = copy.deepcopy(dict(document))
    owner = str(owner_id or out.get("job_id") or "legacy-job").strip()
    out["cross_workflow"] = migrate_workflow(
        out.get("cross_workflow"), owner,
        source_schema=str(out.get("schema") or "legacy-document"))
    return out


def _normal_state(value: Any) -> str:
    state = str(value or UNKNOWN).strip().upper()
    aliases = {
        "OBSERVED_BY_HUMAN_REVIEW": OBSERVED,
        "MEASURED": OBSERVED,
        "PROPOSED_BY_AI": PROPOSED,
        "AUTO_ACCEPTED_FOR_PREVIEW": PROPOSED,
        "DERIVED": INFERRED,
        "CONTESTED_IN_CROSS": CONTESTED,
        "UNKNOWN_UNOBSERVED": UNKNOWN,
    }
    state = aliases.get(state, state)
    return state if state in EVIDENCE_STATES else UNKNOWN


def _source_type(claim: Mapping[str, Any]) -> str:
    provenance = claim.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    declared = str(claim.get(
        "source_type", provenance.get(
            "source_type", provenance.get("source", "")))).strip()
    return (declared or str(claim.get("source", "")).strip()).upper()


def _is_model_source(claim: Mapping[str, Any]) -> bool:
    source_type = _source_type(claim)
    provenance = claim.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    combined = " ".join((source_type, str(claim.get("source", "")),
                         str(provenance.get("model", "")))).upper()
    return (source_type in _MODEL_SOURCES
            or any(token in combined for token in
                   ("MODEL", "LLM", "VLM", "SIGLIP", "QWEN", "GPT",
                    "CLAUDE", "GEMINI", "MISTRAL", "LLAMA")))


def _claim_address(claim: Mapping[str, Any], index: int) -> str:
    for key in ("address", "field", "key", "predicate", "claim_id"):
        value = str(claim.get(key, "")).strip()
        if value:
            return value
    return "claim." + str(index + 1)


def _normal_claim(raw: Mapping[str, Any], index: int,
                  default_source: str) -> Tuple[Optional[Dict[str, Any]],
                                                Optional[Dict[str, Any]]]:
    claim = _plain(raw)
    address = _claim_address(claim, index)
    state = _normal_state(claim.get(
        "evidence_state", claim.get("state", UNKNOWN)))
    source = str(claim.get("source", default_source) or default_source).strip()
    if _is_model_source(claim):
        state = PROPOSED
    if state == UNKNOWN:
        return None, {
            "address": address,
            "why": str(claim.get("why", "claim has no evidence state")),
        }
    if "value" not in claim:
        return None, {"address": address, "why": "claim value is missing"}
    normalized = {
        "address": address,
        "value": _plain(claim["value"]),
        "evidence_state": state,
        "source": source,
        "source_type": _source_type(claim) or "DECLARED_SOURCE",
        "provenance": _plain(claim.get("provenance", {})),
    }
    if state == CONTESTED:
        normalized["declared_contested"] = True
    normalized["claim_digest"] = stable_digest(normalized)
    return normalized, None


def _rebuild_evidence(workflow: Dict[str, Any]) -> None:
    claims = sorted(workflow["evidence"]["claims"], key=lambda row: (
        str(row.get("address", "")),
        _STATE_ORDER.get(str(row.get("evidence_state", UNKNOWN)), 9),
        stable_digest(row.get("value")), str(row.get("source", "")),
        str(row.get("claim_digest", ""))))
    workflow["evidence"]["claims"] = claims
    store = CrossStore()
    root = "workflow:" + workflow["owner_id"]
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for claim in claims:
        grouped.setdefault(claim["address"], []).append(claim)
        state = claim["evidence_state"]
        kind = _STATE_KIND.get(state, "derived")
        store.put(root, claim["address"], claim["value"], kind,
                  claim["source"])

    resolutions: Dict[str, Any] = {}
    for address, rows in sorted(grouped.items()):
        known = [row for row in rows
                 if row["evidence_state"] != PROPOSED]
        basis = known or rows
        distinct = {stable_digest(row["value"]) for row in basis}
        declared = any(row.get("declared_contested") for row in known)
        if not known:
            # Multiple model alternatives are still proposals.  Treating
            # their disagreement as a supported CONTESTED fact would be an
            # authority escalation.  The alternatives remain separate and no
            # value is selected or averaged.
            state = PROPOSED
        elif declared or len(distinct) > 1:
            state = CONTESTED
        elif any(row["evidence_state"] == OBSERVED for row in basis):
            state = OBSERVED
        elif any(row["evidence_state"] == INFERRED for row in basis):
            state = INFERRED
        else:
            state = PROPOSED
        proposed_values = {
            stable_digest(row["value"]) for row in rows
            if row["evidence_state"] == PROPOSED
        }
        resolutions[address] = {
            "state": state,
            "alternatives": [copy.deepcopy(row) for row in rows],
            "averaged": False,
            "selected_value": (copy.deepcopy(basis[0]["value"])
                               if len(distinct) == 1 else None),
            "proposal_disagreement": len(proposed_values) > 1,
        }
    workflow["evidence"]["resolutions"] = resolutions
    workflow["evidence"]["cross"] = store.to_dict()
    workflow["evidence"]["cross_verification"] = store.verify()


def _ingest_claims(workflow: Dict[str, Any], claims: Iterable[Any], *,
                   default_source: str) -> Dict[str, Any]:
    out = copy.deepcopy(workflow)
    existing = {row.get("claim_digest")
                for row in out["evidence"]["claims"]}
    unknowns = []
    for index, raw in enumerate(claims):
        if not isinstance(raw, Mapping):
            unknowns.append({"address": "claim." + str(index + 1),
                             "why": "claim must be an object"})
            continue
        claim, unknown = _normal_claim(raw, index, default_source)
        if unknown is not None:
            unknowns.append(unknown)
        elif claim is not None and claim["claim_digest"] not in existing:
            out["evidence"]["claims"].append(claim)
            existing.add(claim["claim_digest"])
    if unknowns:
        existing_unknowns = {
            row.get("unknown_digest") for row in out.get("claim_unknowns", ())
            if isinstance(row, Mapping)
        }
        for unknown in unknowns:
            unknown["unknown_digest"] = stable_digest(unknown)
            if unknown["unknown_digest"] not in existing_unknowns:
                out.setdefault("claim_unknowns", []).append(unknown)
                existing_unknowns.add(unknown["unknown_digest"])
        out["claim_unknowns"].sort(
            key=lambda row: (str(row.get("address", "")),
                             str(row.get("unknown_digest", ""))))
    _rebuild_evidence(out)
    return out


def _missing_fields(code: str, details: Mapping[str, Any]) -> List[str]:
    fields: List[str] = []
    for key in ("missing_fields", "missing", "required", "requirements",
                "invalid"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            fields.append(value.strip())
        elif isinstance(value, (list, tuple)):
            fields.extend(str(item).strip() for item in value
                          if str(item).strip())
    if not fields:
        fields.append("obligation:" + str(code).lower())
    return sorted(set(fields))


def _recommended_choice(code: str) -> str:
    upper = code.upper()
    if any(token in upper for token in ("AUTHORITY_ESCALATION",
                                         "NOT_IMPLEMENTED", "INTERNAL")):
        return TYPED_STOP
    if any(token in upper for token in ("GEOMETRY", "MASK", "CLEANUP",
                                         "FOREGROUND", "CAD", "SHAPE")):
        return HUMAN_GEOMETRY_EDIT
    if any(token in upper for token in ("PROVIDER", "CORPUS", "RETRIEVAL",
                                         "RUNNER", "INDEX")):
        return PROVIDER_CONNECT
    return HUMAN_INPUT


def _typed_stop(stage: str, code: str, missing_fields: Sequence[str],
                acceptable_evidence: Sequence[Mapping[str, Any]],
                provenance: Mapping[str, Any]) -> Dict[str, Any]:
    stop = {
        "schema": STOP_SCHEMA,
        "state": UNKNOWN,
        "verdict": code,
        "stage": stage,
        "missing_fields": list(missing_fields),
        "acceptable_evidence": _plain(acceptable_evidence),
        "provenance": _plain(provenance),
        "fabricated_values": False,
    }
    stop["stop_digest"] = stable_digest(stop)
    return stop


def _normal_resolution_paths(paths: Optional[Sequence[str]]) -> List[str]:
    if paths is None:
        return list(RESOLUTION_PATHS)
    if isinstance(paths, (str, bytes)):
        raise ValueError("resolution paths must be a sequence")
    names = {str(path).strip().upper() for path in paths
             if str(path).strip()}
    invalid = sorted(names.difference(RESOLUTION_PATHS))
    if invalid:
        raise ValueError("unknown resolution paths: " + ", ".join(invalid))
    if not names:
        raise ValueError("at least one resolution path is required")
    return sorted(names, key=lambda path: _PATH_ORDER[path])


def _legacy_choice_for_path(path: str, fallback: str) -> str:
    if path == BOUNDED_ALTERNATIVES:
        # Old consumers have no bounded-alternatives enum.  A proposal is the
        # closest authority ceiling, while the new field remains authoritative.
        return LLM_PROPOSAL_WITH_CONSENT
    return _PATH_TO_CHOICE.get(path, fallback)


def make_resolution_request(*, stage: str, code: str, reason: str,
                            details: Optional[Mapping[str, Any]] = None,
                            provenance: Optional[Mapping[str, Any]] = None,
                            unsolvable: bool = False,
                            resolution_paths: Optional[Sequence[str]] = None,
                            recommended_path: Optional[str] = None,
                            capability_gate: Optional[str] = None,
                            acceptable_evidence_types: Optional[
                                Sequence[str]] = None,
                            request_state: Optional[str] = None
                            ) -> Dict[str, Any]:
    detail = _plain(details or {})
    missing = _missing_fields(code, detail)
    paths = _normal_resolution_paths(resolution_paths)
    acceptable = [
        {"choice": HUMAN_INPUT,
         "evidence": "named human input bound to this request digest"},
        {"choice": HUMAN_GEOMETRY_EDIT,
         "evidence": "digest-bound geometry edit with undo lineage"},
        {"choice": LLM_PROPOSAL_WITH_CONSENT,
         "evidence": "unexpired scoped consent plus PROPOSED values only"},
        {"choice": PROVIDER_CONNECT,
         "evidence": "provider artifact with source, rights, and digest"},
        {"choice": TYPED_STOP,
         "evidence": "explicit stop preserving missing fields and provenance"},
    ]
    evidence_types = sorted({str(value).strip()
                             for value in (acceptable_evidence_types or ())
                             if str(value).strip()})
    if evidence_types:
        acceptable.insert(0, {
            "capability_gate": str(capability_gate or ""),
            "evidence_types": evidence_types,
            "evidence": "non-model OBSERVED artifact with typed provenance",
        })
    legacy_recommended = (TYPED_STOP if unsolvable
                          else _recommended_choice(code))
    path = str(recommended_path or _CHOICE_TO_PATH.get(
        legacy_recommended, TYPED_STOP)).strip().upper()
    if path not in paths:
        path = TYPED_STOP if TYPED_STOP in paths else paths[0]
    recommended = _legacy_choice_for_path(path, legacy_recommended)
    declared_request_state = request_state or detail.get("state")
    if declared_request_state is None:
        state = CONTESTED if "CONTESTED" in code.upper() else UNKNOWN
    else:
        state = _normal_state(declared_request_state)
        if state not in {UNKNOWN, CONTESTED}:
            state = CONTESTED if "CONTESTED" in code.upper() else UNKNOWN
    request = {
        "schema": RESOLUTION_SCHEMA,
        "state": state,
        "verdict": code,
        "stage": str(stage or "UNSPECIFIED"),
        "reason": str(reason),
        "missing_fields": missing,
        "acceptable_evidence": acceptable,
        "choices": [
            {"choice": choice,
             "requires_consent": choice == LLM_PROPOSAL_WITH_CONSENT,
             "authority_ceiling": PROPOSED
             if choice == LLM_PROPOSAL_WITH_CONSENT else None}
            for choice in RESOLUTION_CHOICES
        ],
        "recommended_choice": recommended,
        "resolution_paths": [
            {"path": candidate,
             "requires_consent": candidate == CONSENTED_LLM_PROPOSAL,
             "model_authored_requires_consent": candidate in {
                 CONSENTED_LLM_PROPOSAL, BOUNDED_ALTERNATIVES},
             "authority_ceiling": PROPOSED
             if candidate in {CONSENTED_LLM_PROPOSAL,
                              BOUNDED_ALTERNATIVES} else None,
             "may_promote_model_output_to_observed": False}
            for candidate in paths
        ],
        "recommended_path": path,
        "capability_gate": str(capability_gate or "") or None,
        "provenance": _plain(provenance or {}),
        "status": "OPEN",
    }
    request["request_id"] = stable_digest(request)[:32]
    if unsolvable or recommended == TYPED_STOP:
        request["typed_stop"] = _typed_stop(
            request["stage"], code, missing, acceptable,
            request["provenance"])
    return request


def _find_unknown(outcome: Mapping[str, Any]) -> Optional[Tuple[str, str,
                                                                  Dict[str, Any]]]:
    verdict = str(outcome.get("verdict", ""))
    if (verdict.startswith(("UNKNOWN_", "ESCALATE_", "TYPED_STOP"))
            or "CONTESTED" in verdict or "BLOCKED" in verdict):
        reason = str(outcome.get("reason", outcome.get("why", verdict)))
        details = outcome.get("details", {})
        details = dict(details) if isinstance(details, Mapping) else {}
        for key, value in outcome.items():
            if key not in {"state", "result", "cross_workflow"}:
                details.setdefault(str(key), _plain(value))
        return verdict, reason, details
    return None


def _claims_from(value: Mapping[str, Any]) -> List[Any]:
    claims = value.get("cross_claims")
    if isinstance(claims, Sequence) and not isinstance(claims, (str, bytes)):
        return list(claims)
    evidence = value.get("evidence_cross")
    if isinstance(evidence, Mapping):
        claims = evidence.get("claims")
        if isinstance(claims, Sequence) and not isinstance(claims, (str, bytes)):
            return list(claims)
        arms = evidence.get("arms")
        if isinstance(arms, Mapping):
            adapted: List[Dict[str, Any]] = []
            for arm in sorted(arms):
                rows = arms[arm]
                if not (isinstance(rows, Sequence)
                        and not isinstance(rows, (str, bytes))):
                    continue
                for index, row in enumerate(rows):
                    if not isinstance(row, Mapping):
                        adapted.append({
                            "address": "evidence.%s.%d" % (arm, index + 1),
                            "state": UNKNOWN,
                            "why": "EvidenceCross arm entry must be an object",
                        })
                        continue
                    authority = str(row.get(
                        "state", row.get("authority", UNKNOWN))).upper()
                    if ("UNKNOWN" in authority or "UNOBSERVED" in authority
                            or "NOT_OBSERVED" in authority):
                        state = UNKNOWN
                    elif "OBSERVED" in authority or "MEASURED" in authority:
                        state = OBSERVED
                    elif "PROPOSED" in authority or "MODEL" in authority:
                        state = PROPOSED
                    elif ("DERIVED" in authority or "INFERRED" in authority
                          or "COMPARISON" in authority):
                        state = INFERRED
                    elif "CONTESTED" in authority:
                        state = CONTESTED
                    else:
                        state = UNKNOWN
                    address = str(row.get(
                        "path", row.get("address",
                                        "evidence.%s.%d" % (arm, index + 1))))
                    if "value" in row:
                        claim_value = row["value"]
                    elif "residual" in row:
                        claim_value = row["residual"]
                    elif "digest" in row:
                        claim_value = row["digest"]
                    else:
                        claim_value = copy.deepcopy(dict(row))
                    adapted.append({
                        "address": address,
                        "value": claim_value,
                        "state": state,
                        "source": str(row.get(
                            "source", evidence.get("schema", "EvidenceCross"))),
                        "source_type": str(row.get("source_type", "")),
                        "why": str(row.get(
                            "meaning", "EvidenceCross entry is unresolved")),
                        "provenance": {
                            "evidence_cross_arm": str(arm),
                            "evidence_cross_digest": evidence.get("digest"),
                            "source_digest": row.get("source_digest"),
                        },
                    })
            return adapted
    return []


def _physical_from(event: Mapping[str, Any],
                   outcome: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    for value in (event.get("physical_cross"),
                  outcome.get("physical_cross")):
        if isinstance(value, Mapping):
            return value
    return None


def _proof_from(event: Mapping[str, Any],
                outcome: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    for value in (event.get("proof_cross"), outcome.get("proof_cross"),
                  event.get("automatic_proof_cross"),
                  outcome.get("automatic_proof_cross")):
        if isinstance(value, Mapping):
            return value
    return None


def _append_resolution_request(workflow: Dict[str, Any],
                               request: Mapping[str, Any]) -> None:
    known = {row.get("request_id") for row in workflow["obligations"]}
    if request.get("request_id") not in known:
        workflow["obligations"].append(copy.deepcopy(dict(request)))
    stop = request.get("typed_stop")
    if isinstance(stop, Mapping):
        stops = {row.get("stop_digest") for row in workflow["typed_stops"]}
        if stop.get("stop_digest") not in stops:
            workflow["typed_stops"].append(copy.deepcopy(dict(stop)))


def capability_catalog() -> Dict[str, Any]:
    """Return the closed capability-gate contract for engine/UI adapters."""
    return {
        "schema": CAPABILITY_GATE_SCHEMA,
        "gates": copy.deepcopy(CAPABILITY_GATES),
        "resolution_paths": list(RESOLUTION_PATHS),
        "truth_contract": {
            "model_authority_ceiling": PROPOSED,
            "model_may_promote_to_observed": False,
            "conflicts_are_averaged": False,
            "gate_closure_requires": "NON_MODEL_TYPED_OBSERVED_EVIDENCE",
        },
    }


def _is_model_actor(actor: str,
                    provenance: Optional[Mapping[str, Any]] = None) -> bool:
    return _is_model_source({
        "source": str(actor or ""),
        "source_type": str((provenance or {}).get("source_type", "")),
        "provenance": _plain(provenance or {}),
    })


def _capability_ids(*values: Mapping[str, Any]) -> List[str]:
    names = set()
    for value in values:
        if not isinstance(value, Mapping):
            continue
        for key in ("required_capabilities", "capability_gates"):
            raw = value.get(key, ())
            if isinstance(raw, str):
                raw = [raw]
            if isinstance(raw, Sequence) and not isinstance(raw, bytes):
                names.update(str(item).strip().upper() for item in raw
                             if str(item).strip())
    return sorted(names)


def _capability_evidence_for(value: Any, gate_id: str) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        if gate_id in value:
            selected = value[gate_id]
            if isinstance(selected, Sequence) and not isinstance(
                    selected, (str, bytes)):
                return list(selected)
            return [selected]
        if str(value.get("gate", "")).strip().upper() == gate_id:
            return [value]
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [row for row in value
                if isinstance(row, Mapping)
                and str(row.get("gate", "")).strip().upper() == gate_id]
    return [value]


def _normal_capability_evidence(raw: Any, gate_id: str,
                                index: int) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        row = {
            "gate": gate_id,
            "evidence_type": "INVALID_EVIDENCE",
            "declared_state": UNKNOWN,
            "evidence_state": UNKNOWN,
            "source": "",
            "source_type": "",
            "model_authored": False,
            "named_source": False,
            "has_payload": False,
            "value": {"invalid_type": type(raw).__name__},
            "provenance": {},
            "why": "capability evidence must be an object",
        }
        row["evidence_digest"] = stable_digest(row)
        return row
    item = _plain(raw)
    provenance = item.get("provenance", {})
    provenance = provenance if isinstance(provenance, Mapping) else {}
    declared = _normal_state(item.get(
        "evidence_state", item.get("state", UNKNOWN)))
    source = str(item.get(
        "source", provenance.get("source", ""))).strip()
    source_type = str(item.get(
        "source_type", provenance.get("source_type", ""))).strip().upper()
    model_authored = _is_model_source({
        "source": source,
        "source_type": source_type,
        "provenance": provenance,
    })
    state = PROPOSED if model_authored else declared
    payload_key = next((key for key in (
        "value", "artifact", "measurement", "digest", "source_digest")
        if key in item), None)
    value = (copy.deepcopy(item[payload_key]) if payload_key is not None
             else {"missing_payload_at": index + 1})
    row = {
        "gate": gate_id,
        "evidence_type": str(item.get("evidence_type", "")).strip().upper(),
        "declared_state": declared,
        "evidence_state": state,
        "source": source,
        "source_type": source_type,
        "model_authored": model_authored,
        "named_source": bool(source),
        "has_payload": payload_key is not None,
        "value": value,
        "provenance": _plain(provenance),
    }
    if model_authored and declared == OBSERVED:
        row["authority_correction"] = "MODEL_OBSERVED_DEMOTED_TO_PROPOSED"
    row["evidence_digest"] = stable_digest(row)
    return row


def _first_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _has_any(mapping: Mapping[str, Any], *keys: str) -> bool:
    return any(key in mapping and mapping.get(key) not in (None, "", [], {})
               for key in keys)


def _embedded_record(value: Mapping[str, Any],
                     provenance: Mapping[str, Any],
                     *keys: str) -> Mapping[str, Any]:
    for container in (provenance, value):
        for key in keys:
            candidate = container.get(key)
            if isinstance(candidate, Mapping):
                return candidate
    return {}


def _self_digest_valid(record: Mapping[str, Any], digest_key: str) -> bool:
    supplied = str(record.get(digest_key, "")).strip()
    if not supplied:
        return False
    body = copy.deepcopy(dict(record))
    body.pop(digest_key, None)
    return supplied == stable_digest(body)


def _physical_decision_rejections(
        value: Mapping[str, Any], provenance: Mapping[str, Any],
        expected_claim_kind: str) -> List[str]:
    decision = _embedded_record(
        value, provenance, "physical_calibration_decision",
        "calibration_decision")
    if not decision:
        return ["MISSING_AUTHORIZED_CALIBRATION_DECISION"]
    reasons = []
    if decision.get("schema") != physical_calibration_contract.DECISION_SCHEMA:
        reasons.append("INVALID_CALIBRATION_DECISION_SCHEMA")
    if not _self_digest_valid(decision, "decision_digest"):
        reasons.append("INVALID_CALIBRATION_DECISION_DIGEST")
    if (decision.get("verdict") != "CLAIM_AUTHORIZED"
            or decision.get("claim_authorized") is not True):
        reasons.append("CALIBRATION_CLAIM_NOT_AUTHORIZED")
    if decision.get("claim_kind") != expected_claim_kind:
        reasons.append("CALIBRATION_CLAIM_KIND_MISMATCH")
    authorized = _first_mapping(decision.get("authorized_claim"))
    if authorized.get("authority") != "MEASURED":
        reasons.append("CALIBRATION_AUTHORITY_NOT_MEASURED")
    if authorized.get("claim_kind") != expected_claim_kind:
        reasons.append("AUTHORIZED_CALIBRATION_KIND_MISMATCH")
    checks = decision.get("validation_checks", ())
    if (not isinstance(checks, Sequence)
            or isinstance(checks, (str, bytes)) or not checks):
        reasons.append("MISSING_CALIBRATION_VALIDATION_CHECKS")
    else:
        for check in checks:
            if not isinstance(check, Mapping):
                reasons.append("INVALID_CALIBRATION_VALIDATION_CHECK")
                continue
            counted = check.get("counted_measurement_digests", ())
            threshold = _first_mapping(check.get("threshold"))
            if not counted:
                reasons.append("CALIBRATION_CHECK_HAS_NO_MEASUREMENTS")
            if threshold.get("is_non_model_approved") is not True:
                reasons.append("CALIBRATION_THRESHOLD_NOT_HUMAN_APPROVED")
            if check.get("outside_threshold_digests"):
                reasons.append("CALIBRATION_CHECK_OUTSIDE_THRESHOLD")
    return reasons


def _reconstruction_decision_rejections(
        value: Mapping[str, Any], provenance: Mapping[str, Any],
        expected_claim_kind: str) -> List[str]:
    decision = _embedded_record(
        value, provenance, "reconstruction_claim_decision",
        "reconstruction_decision")
    if not decision:
        return ["MISSING_AUTHORIZED_RECONSTRUCTION_DECISION"]
    reasons = []
    if decision.get("schema") != reconstruction_claim_contract.DECISION_SCHEMA:
        reasons.append("INVALID_RECONSTRUCTION_DECISION_SCHEMA")
    if not _self_digest_valid(decision, "decision_digest"):
        reasons.append("INVALID_RECONSTRUCTION_DECISION_DIGEST")
    if decision.get("status") != "CLAIM_AUTHORIZED_SCOPED":
        reasons.append("RECONSTRUCTION_CLAIM_NOT_AUTHORIZED")
    if decision.get("claim_kind") != expected_claim_kind:
        reasons.append("RECONSTRUCTION_CLAIM_KIND_MISMATCH")
    authorized = _first_mapping(decision.get("authorized_claim"))
    if not authorized or not authorized.get("scope_item_ids"):
        reasons.append("RECONSTRUCTION_SCOPE_NOT_BOUND")
    validations = decision.get("validation", ())
    if (not isinstance(validations, Sequence)
            or isinstance(validations, (str, bytes)) or not validations
            or any(not isinstance(row, Mapping)
                   or row.get("passed") is not True for row in validations)):
        reasons.append("RECONSTRUCTION_VALIDATION_NOT_PASSED")
    return reasons


def _finish_decision_rejections(
        value: Mapping[str, Any],
        provenance: Mapping[str, Any]) -> List[str]:
    decision = _embedded_record(
        value, provenance, "manufacturing_finish_decision",
        "finish_decision")
    approval = _embedded_record(
        value, provenance, "manufacturing_finish_approval",
        "finish_approval")
    reasons = []
    if not decision:
        reasons.append("MISSING_MANUFACTURING_FINISH_DECISION")
    else:
        if decision.get("schema") != manufacturing_finish_contract.SCHEMA:
            reasons.append("INVALID_MANUFACTURING_FINISH_DECISION_SCHEMA")
        if not _self_digest_valid(decision, "decision_digest"):
            reasons.append("INVALID_MANUFACTURING_FINISH_DECISION_DIGEST")
        if decision.get("verdict") != "CANDIDATES_READY":
            reasons.append("MANUFACTURING_FINISH_CANDIDATES_NOT_READY")
    if not approval:
        reasons.append("MISSING_MANUFACTURING_FINISH_APPROVAL")
    else:
        if approval.get("schema") != manufacturing_finish_contract.APPROVAL_SCHEMA:
            reasons.append("INVALID_MANUFACTURING_FINISH_APPROVAL_SCHEMA")
        if not _self_digest_valid(approval, "approval_digest"):
            reasons.append("INVALID_MANUFACTURING_FINISH_APPROVAL_DIGEST")
        if approval.get("verdict") != "USER_APPROVED":
            reasons.append("MANUFACTURING_FINISH_NOT_USER_APPROVED")
        if decision and approval.get("decision_digest") != decision.get(
                "decision_digest"):
            reasons.append("MANUFACTURING_FINISH_DECISION_BINDING_MISMATCH")
        candidates = decision.get("candidates", ()) if decision else ()
        candidate_digests = {
            str(row.get("candidate_digest")) for row in candidates
            if isinstance(row, Mapping) and row.get("candidate_digest")
        }
        if approval.get("candidate_digest") not in candidate_digests:
            reasons.append("MANUFACTURING_FINISH_CANDIDATE_NOT_BOUND")
    return reasons


def _capability_semantic_rejections(
        gate_id: str, row: Mapping[str, Any]) -> List[str]:
    """Validate what an evidence payload actually establishes.

    Matching an evidence-type label is intentionally insufficient.  These
    checks prevent a front image labelled ``REAR_IMAGE``, one material scalar,
    one toile, or an unlicensed search index from closing a much broader gate.
    The checks are deliberately structural; domain-specific calibration is
    performed by the physical/manufacturing contracts before their evidence is
    admitted here.
    """
    value = _first_mapping(row.get("value"))
    provenance = _first_mapping(row.get("provenance"))
    reasons: List[str] = []

    if gate_id == "REAR_FROM_SINGLE_FRONT":
        view = str(provenance.get("view", "")).strip().upper()
        rear_visible = provenance.get("rear_visible") is True
        views = provenance.get("views", ())
        view_tokens = ({str(item).strip().upper() for item in views}
                       if isinstance(views, Sequence)
                       and not isinstance(views, (str, bytes)) else set())
        if not rear_visible and view not in {"REAR", "BACK", "MULTIVIEW"} \
                and not ({"REAR", "BACK"} & view_tokens):
            reasons.append("REAR_NOT_VISIBLE_IN_PROVENANCE")
        if provenance.get("registered") is not True:
            reasons.append("REAR_VIEW_NOT_REGISTERED")
        if not _has_any(provenance, "registration_digest"):
            reasons.append("MISSING_REAR_REGISTRATION_DIGEST")
        if not _has_any(provenance, "source_image_digest",
                        "multiview_capture_digest"):
            reasons.append("MISSING_REAR_SOURCE_IMAGE_DIGEST")
        if not _has_any(value, "surface_digest", "rear_surface",
                        "rear_surface_digest"):
            reasons.append("MISSING_REAR_SURFACE")
        if not _has_any(value, "construction", "rear_construction",
                        "construction_digest"):
            reasons.append("MISSING_REAR_CONSTRUCTION")

    elif gate_id == "MEASURED_MATERIAL":
        if not _has_any(value, "composition", "fiber_composition"):
            reasons.append("MISSING_MATERIAL_COMPOSITION")
        if not _has_any(value, "thickness", "thickness_mm", "thickness_m"):
            reasons.append("MISSING_MATERIAL_THICKNESS")
        stretch = _first_mapping(value.get("stretch"))
        if not ((_has_any(stretch, "warp") and _has_any(stretch, "weft"))
                or (_has_any(value, "stretch_warp")
                    and _has_any(value, "stretch_weft"))):
            reasons.append("MISSING_MATERIAL_STRETCH_AXES")
        friction = _first_mapping(value.get("friction"))
        if not (_has_any(value, "friction", "friction_static",
                         "friction_dynamic")
                or _has_any(friction, "static", "dynamic")):
            reasons.append("MISSING_MATERIAL_FRICTION")
        bending = _first_mapping(value.get("bending"))
        if not (_has_any(value, "bending", "bending_warp", "bending_weft")
                or _has_any(bending, "warp", "weft")):
            reasons.append("MISSING_MATERIAL_BENDING")
        reasons.extend(_physical_decision_rejections(
            value, provenance, "MATERIAL_CALIBRATED"))

    elif gate_id == "BODY_DIMENSIONS_FROM_IMAGE":
        aliases = {
            "height": ("height", "height_cm"),
            "chest": ("chest", "chest_cm", "bust", "bust_cm"),
            "waist": ("waist", "waist_cm"),
            "hip": ("hip", "hip_cm"),
            "body_length": ("body_length", "body_length_cm",
                            "torso_length", "torso_length_cm"),
        }
        for name, keys in aliases.items():
            if not _has_any(value, *keys):
                reasons.append("MISSING_BODY_" + name.upper())
        reasons.extend(_reconstruction_decision_rejections(
            value, provenance, "EXACT_BODY_MEASUREMENTS"))

    elif gate_id == "ARBITRARY_GARMENT_FIDELITY":
        validation_set = value.get("validation_set", ())
        finite_scope = str(value.get("scope_kind", "")).upper() in {
            "FINITE", "FINITE_DECLARED", "DECLARED_FINITE_SCOPE"}
        if not finite_scope:
            reasons.append("UNIVERSAL_FIDELITY_SCOPE_NOT_FINITE")
        if value.get("coverage_complete") is not True:
            reasons.append("FIDELITY_COVERAGE_NOT_COMPLETE")
        if (not isinstance(validation_set, Sequence)
                or isinstance(validation_set, (str, bytes))
                or not validation_set):
            reasons.append("MISSING_FIDELITY_VALIDATION_SET")
        if not _has_any(value, "fidelity_threshold",
                        "acceptance_threshold"):
            reasons.append("MISSING_FIDELITY_THRESHOLD")
        reasons.extend(_reconstruction_decision_rejections(
            value, provenance, "ARBITRARY_GARMENT_FIDELITY"))

    elif gate_id == "COMPLETE_PATTERN_GUARANTEE":
        finite_scope = str(value.get("scope_kind", "")).upper() in {
            "FINITE", "FINITE_DECLARED", "DECLARED_FINITE_SCOPE"}
        if not finite_scope:
            reasons.append("UNIVERSAL_PATTERN_SCOPE_NOT_FINITE")
        if value.get("coverage_complete") is not True:
            reasons.append("PATTERN_COVERAGE_NOT_COMPLETE")
        if not _has_any(value, "pattern_digest", "pattern_package_digest"):
            reasons.append("MISSING_PATTERN_DIGEST")
        if not _has_any(value, "validation_set_digest",
                        "physical_toile_validations"):
            reasons.append("MISSING_PATTERN_VALIDATION_SET")
        if not _has_any(value, "manufacturability_checks",
                        "qualified_review_digest"):
            reasons.append("MISSING_MANUFACTURABILITY_REVIEW")
        reasons.extend(_reconstruction_decision_rejections(
            value, provenance,
            "UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN"))

    elif gate_id == "SEAM_FINISH_CONSTRUCTION":
        for name in ("seam_finish", "interfacing", "lining",
                     "machine_setup"):
            if not _has_any(value, name):
                reasons.append("MISSING_" + name.upper())
        reasons.extend(_finish_decision_rejections(value, provenance))

    elif gate_id == "REAL_CLOTH_ERROR_GUARANTEE":
        if not _has_any(value, "error_percent", "error_metrics"):
            reasons.append("MISSING_REAL_CLOTH_ERROR_METRIC")
        sample_count = value.get("sample_count")
        if isinstance(sample_count, bool) or not isinstance(
                sample_count, (int, float)) or sample_count < 2:
            reasons.append("INSUFFICIENT_REAL_CLOTH_SAMPLE_COUNT")
        if not _has_any(value, "test_population", "validation_set_digest"):
            reasons.append("MISSING_REAL_CLOTH_TEST_POPULATION")
        if not _has_any(value, "threshold_percent", "acceptance_threshold"):
            reasons.append("MISSING_REAL_CLOTH_ACCEPTANCE_THRESHOLD")
        if not _has_any(value, "calibration_digest"):
            reasons.append("MISSING_REAL_CLOTH_CALIBRATION_DIGEST")
        reasons.extend(_physical_decision_rejections(
            value, provenance, "REAL_CLOTH_ERROR_BOUND"))

    elif gate_id == "WIND_TUNNEL_CALIBRATION":
        if not _has_any(value, "measurements", "measurement_digest"):
            reasons.append("MISSING_WIND_MEASUREMENTS")
        if not _has_any(value, "boundary_conditions",
                        "boundary_condition_digest"):
            reasons.append("MISSING_WIND_BOUNDARY_CONDITIONS")
        if not _has_any(value, "calibration_digest"):
            reasons.append("MISSING_WIND_CALIBRATION_DIGEST")
        reasons.extend(_physical_decision_rejections(
            value, provenance, "WIND_TUNNEL_CALIBRATED"))

    elif gate_id == "CONNECTED_FASHION_SEARCH":
        rights = _first_mapping(provenance.get("rights_review"))
        commercial = rights.get("commercial_use", rights.get("commercial"))
        if commercial is not True and str(commercial).lower() != "allowed":
            reasons.append("SEARCH_COMMERCIAL_RIGHTS_NOT_ALLOWED")
        if not _has_any(value, "provider", "provider_id"):
            reasons.append("MISSING_SEARCH_PROVIDER")
        if not _has_any(value, "index_digest"):
            reasons.append("MISSING_SEARCH_INDEX_DIGEST")
        provider_result = _embedded_record(
            value, provenance, "provider_result")
        if not provider_result:
            reasons.append("MISSING_BOUND_PROVIDER_RESULT")
        else:
            if provider_result.get("schema") != "garment.provider-result.v1":
                reasons.append("INVALID_PROVIDER_RESULT_SCHEMA")
            if not _self_digest_valid(provider_result, "result_digest"):
                reasons.append("INVALID_PROVIDER_RESULT_DIGEST")
            if (provider_result.get("result_action") != "PROVIDER_RESULT"
                    or provider_result.get("typed_stop") is not False):
                reasons.append("PROVIDER_RESULT_NOT_ADMITTED")
            provider = _first_mapping(provider_result.get("provider"))
            if provider.get("provider_id") not in {
                    value.get("provider"), value.get("provider_id")}:
                reasons.append("SEARCH_PROVIDER_BINDING_MISMATCH")

    return sorted(set(reasons))


def _evaluate_capability_gate(
        gate_id: str, evidence: Sequence[Any], *, input_digest: str,
        provenance: Optional[Mapping[str, Any]] = None
        ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    spec = CAPABILITY_GATES.get(gate_id)
    if spec is None:
        spec = {
            "verdict": "UNKNOWN_CAPABILITY_GATE",
            "stage": "CAPABILITY_GATE",
            "missing_fields": ["capability:" + gate_id.lower()],
            "observed_evidence_types": [],
            "paths": [TYPED_STOP],
            "recommended_path": TYPED_STOP,
        }
    rows = [_normal_capability_evidence(raw, gate_id, index)
            for index, raw in enumerate(evidence)]
    rows.sort(key=lambda row: str(row["evidence_digest"]))
    acceptable_types = set(spec["observed_evidence_types"])
    accepted = []
    authority_admissible = []
    for row in rows:
        reasons = []
        if row["evidence_state"] != OBSERVED:
            reasons.append("NOT_OBSERVED")
        if row["model_authored"]:
            reasons.append("MODEL_AUTHORITY_CEILING_PROPOSED")
        if not row["named_source"]:
            reasons.append("UNNAMED_SOURCE")
        if not row["has_payload"]:
            reasons.append("MISSING_PAYLOAD")
        if (acceptable_types
                and row["evidence_type"] not in acceptable_types):
            reasons.append("UNACCEPTABLE_EVIDENCE_TYPE")
        authority_reasons = list(reasons)
        if not authority_reasons:
            authority_admissible.append(row)
        reasons.extend(_capability_semantic_rejections(gate_id, row))
        row["accepted_for_gate"] = not reasons
        row["rejection_reasons"] = sorted(set(reasons))
        if row["accepted_for_gate"]:
            accepted.append(row)

    accepted_values = {stable_digest(row["value"]) for row in accepted}
    if accepted and len(accepted_values) == 1:
        state = OBSERVED
        verdict = "ANSWER"
        selected = copy.deepcopy(accepted[0]["value"])
    elif accepted:
        state = CONTESTED
        verdict = str(spec["verdict"])
        selected = None
    elif (len({stable_digest(row["value"])
               for row in authority_admissible}) > 1
          or any(row["evidence_state"] == CONTESTED for row in rows)):
        state = CONTESTED
        verdict = str(spec["verdict"])
        selected = None
    elif any(row["evidence_state"] == PROPOSED for row in rows):
        state = PROPOSED
        verdict = str(spec["verdict"])
        selected = None
    elif any(row["evidence_state"] == INFERRED for row in rows):
        state = INFERRED
        verdict = str(spec["verdict"])
        selected = None
    else:
        state = UNKNOWN
        verdict = str(spec["verdict"])
        selected = None

    gate = {
        "schema": CAPABILITY_GATE_SCHEMA,
        "gate": gate_id,
        "stage": str(spec["stage"]),
        "state": state,
        "verdict": verdict,
        "missing_fields": list(spec["missing_fields"]),
        "acceptable_evidence_types": list(spec["observed_evidence_types"]),
        "allowed_resolution_paths": list(spec["paths"]),
        "recommended_path": str(spec["recommended_path"]),
        "alternatives": rows,
        "accepted_evidence_digests": [row["evidence_digest"]
                                      for row in accepted],
        "selected_value": selected,
        "averaged": False,
        "model_authority_ceiling": PROPOSED,
        "input_workflow_digest": input_digest,
        "same_old_state": True,
        "reduction": "CANONICAL_ORDER_DETERMINISTIC_REDUCE",
    }
    gate["gate_digest"] = stable_digest(gate)
    if verdict == "ANSWER":
        return gate, None
    reason = ("the capability is not established by non-model typed "
              "OBSERVED evidence; model output remains PROPOSED")
    request = make_resolution_request(
        stage=str(spec["stage"]), code=str(spec["verdict"]), reason=reason,
        details={"missing_fields": list(spec["missing_fields"]),
                 "state": state,
                 "capability_gate_digest": gate["gate_digest"]},
        provenance={"capability_gate": gate_id,
                    "input_workflow_digest": input_digest,
                    **_plain(provenance or {})},
        resolution_paths=spec["paths"],
        recommended_path=str(spec["recommended_path"]),
        capability_gate=gate_id,
        acceptable_evidence_types=spec["observed_evidence_types"],
        request_state=CONTESTED if state == CONTESTED else UNKNOWN)
    return gate, request


def evaluate_capability_gates(
        workflow: Mapping[str, Any], gate_ids: Sequence[str], *,
        evidence: Any = None,
        provenance: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Evaluate capability gates without allowing a model to close them."""
    current = migrate_workflow(workflow, str(workflow.get("owner_id", "job")))
    if isinstance(gate_ids, str):
        gate_ids = [gate_ids]
    names = sorted({str(gate).strip().upper() for gate in gate_ids
                    if str(gate).strip()})
    before_digest = current["workflow_digest"]
    gates = []
    requests = []
    known_gate_digests = {
        row.get("gate_digest") for row in current["capability_gate_history"]
        if isinstance(row, Mapping)
    }
    for gate_id in names:
        gate, request = _evaluate_capability_gate(
            gate_id, _capability_evidence_for(evidence, gate_id),
            input_digest=before_digest, provenance=provenance)
        gates.append(gate)
        if gate["gate_digest"] not in known_gate_digests:
            current["capability_gate_history"].append(gate)
            known_gate_digests.add(gate["gate_digest"])
        if request is not None:
            _append_resolution_request(current, request)
            requests.append(request)
    current["capability_gate_history"].sort(
        key=lambda row: (str(row.get("gate", "")),
                         str(row.get("gate_digest", ""))))
    if names:
        current["revision"] = int(current.get("revision", 0)) + 1
        _seal(current)
    return {
        "verdict": ("ANSWER" if all(gate["verdict"] == "ANSWER"
                                    for gate in gates)
                    else "UNKNOWN_CAPABILITY_GATES"),
        "workflow": current,
        "gates": gates,
        "resolution_request": requests[0] if requests else None,
        "resolution_requests": requests,
        "input_workflow_digest": before_digest,
        "same_old_state": True,
        "reduction": "CANONICAL_ORDER_DETERMINISTIC_REDUCE",
    }


def _physical_contract_payload(
        decision: Mapping[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    """Derive a gate payload only from an authorized physical decision.

    Callers cannot add missing measurements beside the decision.  If the
    decision does not carry enough measured detail, the corresponding gate
    remains open and the UI receives its ordinary typed resolution request.
    """
    claim_kind = str(decision.get("claim_kind", ""))
    value: Dict[str, Any] = {
        "physical_calibration_decision": _plain(decision),
        "calibration_digest": str(decision.get("decision_digest", "")),
    }
    if claim_kind == physical_calibration_contract.ClaimKind.MATERIAL_CALIBRATED.value:
        properties: Dict[str, Any] = {}
        reduction = _first_mapping(decision.get("property_reduction"))
        entries = reduction.get("entries", ())
        if isinstance(entries, Sequence) and not isinstance(entries, (str, bytes)):
            for row in entries:
                if not isinstance(row, Mapping) or row.get("state") != "MEASURED":
                    continue
                supported = _first_mapping(row.get("single_supported_value"))
                if "value" in supported:
                    properties[str(row.get("property_name", ""))] = _plain(
                        supported["value"])
        value.update({
            "composition": properties.get("composition"),
            "thickness_m": properties.get("thickness"),
            "stretch": {
                "warp": properties.get("stretch_warp"),
                "weft": properties.get("stretch_weft"),
            },
            "friction": {
                "static": properties.get("friction_static"),
                "dynamic": properties.get("friction_dynamic"),
            },
            "bending": {
                "warp": properties.get("bending_warp"),
                "weft": properties.get("bending_weft"),
            },
        })
        return "MEASURED_MATERIAL", value

    checks = decision.get("validation_checks", ())
    counted = sorted({
        str(digest) for check in checks if isinstance(check, Mapping)
        for digest in check.get("counted_measurement_digests", ())
        if str(digest)
    }) if isinstance(checks, Sequence) and not isinstance(
        checks, (str, bytes)) else []
    thresholds = [
        _plain(check.get("threshold")) for check in checks
        if isinstance(check, Mapping) and isinstance(check.get("threshold"), Mapping)
    ] if isinstance(checks, Sequence) and not isinstance(
        checks, (str, bytes)) else []
    observations = [
        _plain(row) for check in checks if isinstance(check, Mapping)
        for row in check.get("all_observations", ()) if isinstance(row, Mapping)
    ] if isinstance(checks, Sequence) and not isinstance(
        checks, (str, bytes)) else []

    if claim_kind == physical_calibration_contract.ClaimKind.REAL_CLOTH_ERROR_BOUND.value:
        authorized = _first_mapping(decision.get("authorized_claim"))
        maximum_error = authorized.get("maximum_error_percent")
        threshold_values = [row.get("value") for row in thresholds
                            if row.get("unit") == "%"]
        value.update({
            "error_percent": maximum_error,
            "sample_count": len(counted),
            "test_population": counted,
            "threshold_percent": (threshold_values[0]
                                  if threshold_values else maximum_error),
            "validation_set_digest": stable_digest(counted),
        })
        return "REAL_CLOTH_ERROR_GUARANTEE", value

    if claim_kind == physical_calibration_contract.ClaimKind.WIND_TUNNEL_CALIBRATED.value:
        conditions = [row.get("conditions") for row in observations
                      if row.get("conditions") not in (None, {}, [])]
        value.update({
            "measurements": observations or counted,
            "measurement_digest": stable_digest(observations or counted),
            "boundary_conditions": conditions,
            "boundary_condition_digest": (
                stable_digest(conditions) if conditions else None),
        })
        return "WIND_TUNNEL_CALIBRATION", value
    return None, value


def _reconstruction_contract_payload(
        decision: Mapping[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    claim_kind = str(decision.get("claim_kind", ""))
    authorized = _first_mapping(decision.get("authorized_claim"))
    scope_ids = list(authorized.get("scope_item_ids", ()))
    validations = [row for row in decision.get("validation", ())
                   if isinstance(row, Mapping)]
    value: Dict[str, Any] = {
        "reconstruction_claim_decision": _plain(decision),
        "scope_kind": "FINITE_DECLARED",
        "coverage_complete": bool(scope_ids) and all(
            row.get("passed") is True for row in validations),
        "validation_set": _plain(validations),
        "validation_set_digest": stable_digest(validations),
    }
    if claim_kind == reconstruction_claim_contract.ClaimKind.EXACT_BODY_MEASUREMENTS.value:
        aliases = {
            "height": {"height", "height_cm", "body.height", "body.height_cm"},
            "chest": {"chest", "chest_cm", "bust", "bust_cm",
                      "body.chest", "body.bust"},
            "waist": {"waist", "waist_cm", "body.waist"},
            "hip": {"hip", "hip_cm", "body.hip"},
            "body_length": {"body_length", "body_length_cm", "torso_length",
                            "torso_length_cm", "body.length", "body.body_length"},
        }
        for row in decision.get("hypotheses", ()):
            if not isinstance(row, Mapping):
                continue
            metric = str(row.get("metric", "")).strip().lower()
            submitted = _first_mapping(row.get("value"))
            for target, names in aliases.items():
                if metric in names:
                    value[target] = _plain(row.get("value"))
                    continue
                for name in sorted(names):
                    if name in submitted and submitted.get(name) not in (
                            None, "", (), []):
                        value[target] = _plain(submitted[name])
                        break
        return "BODY_DIMENSIONS_FROM_IMAGE", value
    if claim_kind == reconstruction_claim_contract.ClaimKind.ARBITRARY_GARMENT_FIDELITY.value:
        value["fidelity_threshold"] = authorized.get("threshold_digests")
        return "ARBITRARY_GARMENT_FIDELITY", value
    if claim_kind == (
            reconstruction_claim_contract.ClaimKind.UNIVERSAL_AUTOMATIC_SEWABLE_PATTERN.value):
        value.update({
            "pattern_digest": decision.get("claim_digest"),
            "manufacturability_checks": validations,
            "qualified_review_digest": stable_digest(validations),
        })
        return "COMPLETE_PATTERN_GUARANTEE", value
    return None, value


def _manufacturing_contract_payload(
        decision: Mapping[str, Any], approval: Mapping[str, Any]) -> Dict[str, Any]:
    grouped: Dict[str, Dict[str, Any]] = {
        "seam_finish": {}, "interfacing": {}, "lining": {},
    }
    selections = _first_mapping(approval.get("selections"))
    for raw_key, selected in selections.items():
        field, separator, target = str(raw_key).partition(":")
        if separator and field in grouped:
            grouped[field][target] = _plain(selected)
    return {
        **grouped,
        # The finish contract intentionally does not infer a machine setup.
        # Leaving this absent keeps the broader construction gate open.
        "manufacturing_finish_decision": _plain(decision),
        "manufacturing_finish_approval": _plain(approval),
    }


def _contract_admission_refusal(
        workflow: Mapping[str, Any], *, code: str, reason: str,
        contract_kind: str, details: Optional[Mapping[str, Any]] = None,
        provenance: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    recorded = record_stage(
        workflow, stage="CONTRACT_ADMISSION",
        event={"type": "ADMIT_AUTHORITATIVE_CONTRACT",
               "contract_kind": contract_kind},
        outcome={"verdict": code, "reason": reason,
                 "details": _plain(details or {})},
        provenance=provenance)
    return {
        "schema": CONTRACT_ADMISSION_SCHEMA,
        "verdict": code,
        "why": reason,
        "contract_kind": contract_kind,
        "workflow": recorded["workflow"],
        "resolution_request": recorded["resolution_request"],
        "resolution_requests": recorded["resolution_requests"],
    }


def admit_authoritative_contract(
        workflow: Mapping[str, Any], *, contract_kind: str,
        decision: Mapping[str, Any],
        approval: Optional[Mapping[str, Any]] = None,
        provenance: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Admit a strict domain decision into the shared workflow.

    Admission and capability closure are separate.  A valid decision is
    recorded even when it cannot establish all fields of the wider product
    claim.  In that case the returned resolution request is the UI resume
    contract; UNKNOWN is never silently imputed by an LLM.
    """
    current = migrate_workflow(workflow, str(workflow.get("owner_id", "job")))
    kind = str(contract_kind or "").strip().upper()
    if not isinstance(decision, Mapping):
        return _contract_admission_refusal(
            current, code="UNKNOWN_CONTRACT_DECISION_REQUIRED",
            reason="a typed decision object is required",
            contract_kind=kind, provenance=provenance)

    gate_id: Optional[str] = None
    evidence_type = ""
    source_type = ""
    state = OBSERVED
    value: Dict[str, Any] = {}
    rejection_reasons: List[str] = []

    if kind == "PHYSICAL_CALIBRATION":
        if decision.get("schema") != physical_calibration_contract.DECISION_SCHEMA:
            rejection_reasons.append("INVALID_PHYSICAL_CALIBRATION_SCHEMA")
        if not _self_digest_valid(decision, "decision_digest"):
            rejection_reasons.append("INVALID_PHYSICAL_CALIBRATION_DIGEST")
        if (decision.get("verdict") != physical_calibration_contract.CLAIM_AUTHORIZED
                or decision.get("claim_authorized") is not True):
            rejection_reasons.append("PHYSICAL_CALIBRATION_NOT_AUTHORIZED")
        gate_id, value = _physical_contract_payload(decision)
        evidence_type = {
            "MEASURED_MATERIAL": "MATERIAL_LAB_MEASUREMENT",
            "REAL_CLOTH_ERROR_GUARANTEE": "CALIBRATED_REAL_CLOTH_TRIAL",
            "WIND_TUNNEL_CALIBRATION": "WIND_TUNNEL_MEASUREMENT",
        }.get(gate_id or "", "")
        source_type = "LAB"
    elif kind == "RECONSTRUCTION_CLAIM":
        if decision.get("schema") != reconstruction_claim_contract.DECISION_SCHEMA:
            rejection_reasons.append("INVALID_RECONSTRUCTION_CLAIM_SCHEMA")
        if not _self_digest_valid(decision, "decision_digest"):
            rejection_reasons.append("INVALID_RECONSTRUCTION_CLAIM_DIGEST")
        if decision.get("status") != reconstruction_claim_contract.CLAIM_AUTHORIZED_SCOPED:
            rejection_reasons.append("RECONSTRUCTION_CLAIM_NOT_AUTHORIZED")
        if decision.get("conflicts"):
            rejection_reasons.append("RECONSTRUCTION_CLAIM_CONTESTED")
        gate_id, value = _reconstruction_contract_payload(decision)
        evidence_type = {
            "BODY_DIMENSIONS_FROM_IMAGE": "TAPE_MEASUREMENT",
            "ARBITRARY_GARMENT_FIDELITY": "HUMAN_APPROVED_TARGET",
            "COMPLETE_PATTERN_GUARANTEE": "QUALIFIED_PATTERN_REVIEW",
        }.get(gate_id or "", "")
        source_type = "VALIDATION_REVIEW"
    elif kind == "MANUFACTURING_FINISH":
        approval_map = approval if isinstance(approval, Mapping) else {}
        rejection_reasons.extend(_finish_decision_rejections(
            {"manufacturing_finish_decision": decision,
             "manufacturing_finish_approval": approval_map}, {}))
        gate_id = "SEAM_FINISH_CONSTRUCTION"
        evidence_type = "APPROVED_SEWING_SPEC"
        source_type = "HUMAN_APPROVAL"
        state = INFERRED
        value = _manufacturing_contract_payload(decision, approval_map)
    else:
        rejection_reasons.append("UNKNOWN_AUTHORITATIVE_CONTRACT_KIND")

    if not gate_id:
        rejection_reasons.append("NO_CAPABILITY_GATE_FOR_CONTRACT_CLAIM")
    if rejection_reasons:
        return _contract_admission_refusal(
            current, code="UNKNOWN_AUTHORITATIVE_CONTRACT_REFUSED",
            reason="the contract artifact failed typed admission",
            contract_kind=kind,
            details={"reason_codes": sorted(set(rejection_reasons))},
            provenance=provenance)

    decision_digest = str(decision.get("decision_digest", ""))
    source = "%s:%s" % (kind.lower(), decision_digest[:12])
    evidence = {
        "gate": gate_id,
        "evidence_type": evidence_type,
        "state": state,
        "source": source,
        "source_type": source_type,
        "value": value,
        "provenance": {
            "contract_kind": kind,
            "decision_digest": decision_digest,
            **_plain(provenance or {}),
        },
    }
    contract_state = ("USER_APPROVED" if kind == "MANUFACTURING_FINISH"
                      else OBSERVED)
    event = {
        "type": "ADMIT_AUTHORITATIVE_CONTRACT",
        "contract_kind": kind,
        "required_capabilities": [gate_id],
        "capability_evidence": {gate_id: [evidence]},
        "cross_claims": [{
            "address": "contract.%s.%s" % (kind.lower(), decision_digest),
            "value": {"decision_digest": decision_digest,
                      "gate": gate_id,
                      "approval_digest": (approval or {}).get(
                          "approval_digest") if isinstance(approval, Mapping)
                      else None},
            "state": state,
            "source": source,
            "source_type": source_type,
            "provenance": _plain(provenance or {}),
        }],
    }
    recorded = record_stage(
        current, stage="CONTRACT_ADMISSION", event=event,
        outcome={"verdict": "ANSWER", "contract_kind": kind,
                 "contract_state": contract_state,
                 "decision_digest": decision_digest},
        provenance=provenance)
    gate = next((row for row in reversed(
        recorded["workflow"].get("capability_gate_history", ()))
        if isinstance(row, Mapping) and row.get("gate") == gate_id), None)
    admission = {
        "schema": CONTRACT_ADMISSION_SCHEMA,
        "verdict": "CONTRACT_ADMITTED",
        "contract_kind": kind,
        "contract_state": contract_state,
        "decision_digest": decision_digest,
        "approval_digest": ((approval or {}).get("approval_digest")
                            if isinstance(approval, Mapping) else None),
        "capability_gate": gate_id,
        "capability_verdict": gate.get("verdict") if gate else None,
        "capability_state": gate.get("state") if gate else None,
        "workflow": recorded["workflow"],
        "resolution_request": recorded["resolution_request"],
        "resolution_requests": recorded["resolution_requests"],
    }
    admission["admission_digest"] = stable_digest({
        key: value for key, value in admission.items()
        if key not in {"workflow", "resolution_request", "resolution_requests"}
    })
    return admission


def record_stage(workflow: Mapping[str, Any], *, stage: str,
                 event: Optional[Mapping[str, Any]] = None,
                 outcome: Optional[Mapping[str, Any]] = None,
                 provenance: Optional[Mapping[str, Any]] = None
                 ) -> Dict[str, Any]:
    """Record one stage using the same pre-stage state for all three channels."""
    current = migrate_workflow(workflow, str(workflow.get("owner_id", "job")))
    event_map = _plain(event or {})
    outcome_map = _plain(outcome or {"verdict": "ANSWER"})
    before_digest = current["workflow_digest"]
    declared_input = str(event_map.get("input_workflow_digest",
                                       before_digest))

    gate_results: List[Dict[str, Any]] = []
    gate_resolution_requests: List[Dict[str, Any]] = []
    known_gate_digests = {
        row.get("gate_digest") for row in current["capability_gate_history"]
        if isinstance(row, Mapping)
    }
    for gate_id in _capability_ids(event_map, outcome_map):
        gate_evidence = (
            _capability_evidence_for(event_map.get("capability_evidence"),
                                     gate_id)
            + _capability_evidence_for(
                outcome_map.get("capability_evidence"), gate_id))
        gate, gate_request = _evaluate_capability_gate(
            gate_id, gate_evidence, input_digest=before_digest,
            provenance=provenance)
        gate_results.append(gate)
        if gate["gate_digest"] not in known_gate_digests:
            current["capability_gate_history"].append(gate)
            known_gate_digests.add(gate["gate_digest"])
        if gate_request is not None:
            _append_resolution_request(current, gate_request)
            gate_resolution_requests.append(gate_request)
    current["capability_gate_history"].sort(
        key=lambda row: (str(row.get("gate", "")),
                         str(row.get("gate_digest", ""))))

    claims = _claims_from(event_map) + _claims_from(outcome_map)
    prior_unknowns = {
        row.get("unknown_digest") for row in current.get("claim_unknowns", ())
        if isinstance(row, Mapping)
    }
    verdict = str(outcome_map.get("verdict", "ANSWER"))
    if _find_unknown(outcome_map) is None:
        claims.append({
            "address": "stage." + str(stage) + ".verdict",
            "value": verdict,
            "state": INFERRED,
            "source": "cross-workflow-harness",
            "source_type": "DETERMINISTIC_HARNESS",
            "provenance": {"input_workflow_digest": before_digest},
        })
    current = _ingest_claims(current, claims,
                             default_source="stage:" + str(stage))
    new_claim_unknowns = [
        row for row in current.get("claim_unknowns", ())
        if row.get("unknown_digest") not in prior_unknowns
    ]

    physical = _physical_from(event_map, outcome_map)
    physical_digest = None
    if physical is not None:
        physical_payload = _plain(physical)
        physical_digest = typed_result_digest(physical_payload)
        layer = {
            "stage": str(stage),
            "state": _normal_state(physical_payload.get("state", INFERRED)),
            "input_state_digest": before_digest,
            "declared_input_state_digest": declared_input,
            "same_old_state": True,
            "reduction": "CANONICAL_ORDER_DETERMINISTIC_REDUCE",
            "artifact": physical_payload,
            "artifact_digest": physical_digest,
        }
        if _is_model_source(physical_payload):
            layer["state"] = PROPOSED
        layer["layer_digest"] = stable_digest(layer)
        existing = {row.get("layer_digest")
                    for row in current["physical"]["layers"]}
        if layer["layer_digest"] not in existing:
            current["physical"]["layers"].append(layer)
        current["physical"]["latest_layer_digest"] = layer["layer_digest"]

    obligations = [{
        "id": "same-old-state-chain",
        "statement": "all stage channels consumed the same workflow state",
        "predicate": "exact_equal",
        # ProofCross exact_equal works over explicit rational values.  The
        # compared digests remain in the stage report; this predicate checks
        # their deterministic equality without pretending a SHA string is a
        # physical scalar.
        "data": {"left": 1,
                 "right": 1 if before_digest == declared_input else 0},
        "effect": "permits only deterministic Cross channel reduction",
    }]
    supplied = event_map.get("proof_obligations", ())
    if isinstance(supplied, Sequence) and not isinstance(supplied, (str, bytes)):
        obligations.extend(row for row in supplied if isinstance(row, Mapping))
    obligations = sorted((_plain(row) for row in obligations),
                         key=lambda row: (str(row.get("id", "")),
                                          stable_digest(row)))
    proof = physics_proof_cross.verify({
        "schema": physics_proof_cross.SCHEMA,
        "run_id": current["owner_id"] + ":" + str(stage) + ":" +
                  str(current["revision"] + 1),
        "solver": "cross-workflow-harness",
        "obligations": obligations,
    })
    proof_digest = str(proof.get("proof_digest", stable_digest(proof)))
    upstream_proof = _proof_from(event_map, outcome_map)
    report = {
        "stage": str(stage),
        "input_state_digest": before_digest,
        "report": proof,
        "proof_digest": proof_digest,
        "upstream_report": _plain(upstream_proof)
        if upstream_proof is not None else None,
        "upstream_proof_digest": stable_digest(upstream_proof)
        if upstream_proof is not None else None,
        "disagreement_policy": "PRESERVE_NO_VOTE_NO_AVERAGE",
    }
    current["proof"]["reports"].append(report)
    current["proof"]["latest_proof_digest"] = proof_digest

    unresolved_items: List[Tuple[str, str, Dict[str, Any]]] = []
    unresolved = _find_unknown(outcome_map)
    if unresolved is not None:
        unresolved_items.append(unresolved)
    if new_claim_unknowns:
        unresolved_items.append((
            "UNKNOWN_CROSS_EVIDENCE_OBLIGATION",
            "EvidenceCross contains entries without supportable authority",
            {"missing_fields": sorted({
                str(row.get("address", "unknown-evidence"))
                for row in new_claim_unknowns
            }), "claim_unknowns": copy.deepcopy(new_claim_unknowns)},
        ))
    if upstream_proof is not None:
        upstream_verdict = str(upstream_proof.get("verdict", ""))
        if (upstream_verdict.startswith(("UNKNOWN_", "REFUTED_"))
                or "CONTESTED" in upstream_verdict):
            unresolved_items.append((
                upstream_verdict or "UNKNOWN_UPSTREAM_PROOF_CROSS",
                "the upstream ProofCross did not establish its obligations",
                {"missing_fields": ["proof_cross"],
                 "upstream_proof_digest": stable_digest(upstream_proof),
                 "upstream_verdict": upstream_verdict},
            ))
    if proof.get("verdict") != "ANSWER":
        unresolved_items.append((
            "UNKNOWN_CROSS_STAGE_PROOF",
            "stage digest/proof obligations did not all pass",
            {"proof_verdict": proof.get("verdict"),
             "proof_digest": proof_digest},
        ))

    resolution_requests: List[Dict[str, Any]] = [
        copy.deepcopy(request) for request in gate_resolution_requests
    ]
    for code, reason, details in unresolved_items:
        unsolvable = any(token in code.upper() for token in
                         ("AUTHORITY_ESCALATION", "NOT_IMPLEMENTED", "INTERNAL"))
        resolution = make_resolution_request(
            stage=str(stage), code=code, reason=reason, details=details,
            provenance={
                "owner_id": current["owner_id"],
                "input_workflow_digest": before_digest,
                **_plain(provenance or {}),
            }, unsolvable=unsolvable)
        _append_resolution_request(current, resolution)
        if resolution["request_id"] not in {
                row["request_id"] for row in resolution_requests}:
            resolution_requests.append(resolution)

    resolution = resolution_requests[0] if resolution_requests else None

    history = {
        "sequence": len(current["stage_history"]) + 1,
        "stage": str(stage),
        "event_kind": str(event_map.get("type", event_map.get("kind", ""))),
        "outcome_verdict": verdict,
        "input_workflow_digest": before_digest,
        "same_old_state": True,
        "reduction": "CANONICAL_ORDER_DETERMINISTIC_REDUCE",
        "physical_layer_digest": physical_digest,
        "proof_digest": proof_digest,
        "capability_gate_digests": [row["gate_digest"]
                                    for row in gate_results],
        "resolution_request_id": (resolution.get("request_id")
                                  if resolution else None),
        "resolution_request_ids": [row["request_id"]
                                   for row in resolution_requests],
    }
    history["stage_digest"] = stable_digest(history)
    current["stage_history"].append(history)
    current["revision"] = int(current.get("revision", 0)) + 1
    _seal(current)
    return {"workflow": current, "resolution_request": resolution,
            "resolution_requests": resolution_requests,
            "stage_record": history}


def grant_model_consent(workflow: Mapping[str, Any], *, scope: str,
                        fields: Sequence[str], granted_by: str,
                        expires_after_revision: int,
                        request_id: Optional[str] = None) -> Dict[str, Any]:
    current = migrate_workflow(workflow, str(workflow.get("owner_id", "job")))
    fields_are_sequence = (isinstance(fields, Sequence)
                           and not isinstance(fields, (str, bytes)))
    names = (sorted({str(field).strip() for field in fields
                     if str(field).strip()})
             if fields_are_sequence else [])
    if (not str(scope).strip() or not fields_are_sequence or not names
            or not str(granted_by).strip()
            or _is_model_actor(str(granted_by))
            or isinstance(expires_after_revision, bool)
            or not isinstance(expires_after_revision, int)
            or expires_after_revision <= int(current["revision"])):
        request = make_resolution_request(
            stage=str(scope or "CONSENT"),
            code="UNKNOWN_INVALID_MODEL_CONSENT",
            reason="scope, fields, named grantor, and future expiry are required",
            details={"missing_fields": ["scope", "fields", "granted_by",
                                        "expires_after_revision"]},
            provenance={"workflow_digest": current["workflow_digest"]})
        _append_resolution_request(current, request)
        current["revision"] += 1
        _seal(current)
        return {"verdict": "UNKNOWN_INVALID_MODEL_CONSENT",
                "workflow": current, "resolution_request": request}
    consent = {
        "schema": CONSENT_SCHEMA,
        "owner_id": str(current["owner_id"]),
        "state": OBSERVED,
        "authority": "HUMAN_CONSENT_FOR_MODEL_PROPOSAL_ONLY",
        "authority_ceiling": PROPOSED,
        "scope": str(scope).strip(),
        "fields": names,
        "granted_by": str(granted_by).strip(),
        "request_id": str(request_id or ""),
        "issued_at_revision": int(current["revision"]),
        "expiry": {"kind": "WORKFLOW_REVISION",
                   "expires_after_revision": expires_after_revision},
        "bound_workflow_digest": current["workflow_digest"],
        "may_promote_to_observed": False,
        "maximum_uses": 1,
    }
    consent["consent_digest"] = stable_digest(consent)
    current["consents"].append(consent)
    current["consents"].sort(key=lambda row: row["consent_digest"])
    current["revision"] += 1
    _seal(current)
    return {"verdict": "ANSWER", "workflow": current,
            "consent_artifact": consent}


def _valid_consent(workflow: Mapping[str, Any], consent_digest: str,
                   request: Mapping[str, Any], fields: Sequence[str]
                   ) -> Optional[Mapping[str, Any]]:
    consent = next((row for row in workflow.get("consents", ())
                    if row.get("consent_digest") == consent_digest), None)
    if not isinstance(consent, Mapping):
        return None
    if consent.get("consent_digest") != stable_digest({
            key: copy.deepcopy(value) for key, value in consent.items()
            if key != "consent_digest"}):
        return None
    if consent.get("owner_id") != workflow.get("owner_id"):
        return None
    # The consent is issued against the exact pre-consent workflow.  Rebuild
    # that state rather than trusting a caller-rehashed consent artifact.
    issued_at = consent.get("issued_at_revision")
    if isinstance(issued_at, bool) or not isinstance(issued_at, int):
        return None
    bound_state = copy.deepcopy(dict(workflow))
    bound_state["consents"] = [
        copy.deepcopy(row) for row in workflow.get("consents", ())
        if isinstance(row, Mapping)
        and row.get("consent_digest") != consent_digest
    ]
    bound_state["revision"] = issued_at
    _seal(bound_state)
    if bound_state.get("workflow_digest") != consent.get(
            "bound_workflow_digest"):
        return None
    if any(row.get("consent_digest") == consent_digest
           for row in workflow.get("resolutions", ())
           if isinstance(row, Mapping)):
        return None
    expiry = consent.get("expiry", {})
    if (not isinstance(expiry, Mapping)
            or int(workflow.get("revision", 0)) >
            int(expiry.get("expires_after_revision", -1))):
        return None
    if consent.get("scope") != request.get("stage"):
        return None
    if request.get("request_id") and consent.get("request_id") != request.get(
            "request_id"):
        return None
    return consent if set(fields).issubset(set(consent.get("fields", ()))) else None


def resolve_request(workflow: Mapping[str, Any], *, request_id: str,
                    choice: str, values: Optional[Mapping[str, Any]] = None,
                    actor: str, consent_digest: Optional[str] = None,
                    provenance: Optional[Mapping[str, Any]] = None
                    ) -> Dict[str, Any]:
    current = migrate_workflow(workflow, str(workflow.get("owner_id", "job")))
    request = next((row for row in current["obligations"]
                    if row.get("request_id") == request_id), None)
    requested = str(choice or "").strip().upper()
    legacy_human_input = requested == HUMAN_INPUT
    if requested in RESOLUTION_PATHS:
        path = requested
        canonical_choice = _PATH_TO_CHOICE[path]
    elif requested in RESOLUTION_CHOICES:
        canonical_choice = requested
        path = _CHOICE_TO_PATH[requested]
    else:
        path = ""
        canonical_choice = ""
    if not isinstance(request, Mapping) or not path:
        unresolved = make_resolution_request(
            stage="RESOLUTION", code="UNKNOWN_INVALID_RESOLUTION",
            reason="request id and a closed-vocabulary resolution path are required",
            details={"missing_fields": ["request_id", "choice"]},
            provenance={"workflow_digest": current["workflow_digest"]})
        _append_resolution_request(current, unresolved)
        current["revision"] += 1
        _seal(current)
        return {"verdict": "UNKNOWN_INVALID_RESOLUTION",
                "workflow": current, "resolution_request": unresolved}

    allowed_rows = request.get("resolution_paths", ())
    allowed_paths = {
        str(row.get("path", "")).strip().upper()
        for row in allowed_rows if isinstance(row, Mapping)
    }
    if allowed_paths and path not in allowed_paths:
        unresolved = make_resolution_request(
            stage=str(request.get("stage", "RESOLUTION")),
            code="UNKNOWN_RESOLUTION_PATH_NOT_ALLOWED",
            reason="the selected path is outside this capability gate",
            details={"missing_fields": request.get("missing_fields", ()),
                     "requested_path": path},
            provenance={"request_id": request_id,
                        "workflow_digest": current["workflow_digest"]},
            resolution_paths=sorted(
                allowed_paths, key=lambda name: _PATH_ORDER[name]),
            recommended_path=str(request.get("recommended_path", "")) or None,
            capability_gate=request.get("capability_gate"))
        _append_resolution_request(current, unresolved)
        current["revision"] += 1
        _seal(current)
        return {"verdict": "UNKNOWN_RESOLUTION_PATH_NOT_ALLOWED",
                "workflow": current, "resolution_request": unresolved}

    value_paths = {MEASURED_INPUT, HUMAN_EDIT,
                   CONSENTED_LLM_PROPOSAL, BOUNDED_ALTERNATIVES}
    if path in value_paths and (not isinstance(values, Mapping) or not values):
        unresolved = make_resolution_request(
            stage=str(request.get("stage", "RESOLUTION")),
            code="UNKNOWN_RESOLUTION_VALUES_REQUIRED",
            reason="the selected resolution path requires named field values",
            details={"missing_fields": request.get("missing_fields", ())},
            provenance={"request_id": request_id,
                        "workflow_digest": current["workflow_digest"]},
            resolution_paths=[path], recommended_path=path,
            capability_gate=request.get("capability_gate"))
        _append_resolution_request(current, unresolved)
        current["revision"] += 1
        _seal(current)
        return {"verdict": "UNKNOWN_RESOLUTION_VALUES_REQUIRED",
                "workflow": current, "resolution_request": unresolved}

    payload = _plain(values or {})
    fields = sorted(payload)
    required_fields = sorted({str(field).strip()
                              for field in request.get("missing_fields", ())
                              if str(field).strip()})
    unexpected_fields = sorted(set(fields) - set(required_fields))
    if unexpected_fields:
        unresolved = make_resolution_request(
            stage=str(request.get("stage", "RESOLUTION")),
            code="UNKNOWN_RESOLUTION_FIELD_MISMATCH",
            reason="resolution values must address only fields named by this request",
            details={"missing_fields": required_fields,
                     "unexpected_fields": unexpected_fields},
            provenance={"request_id": request_id,
                        "workflow_digest": current["workflow_digest"]},
            resolution_paths=[path], recommended_path=path,
            capability_gate=request.get("capability_gate"))
        _append_resolution_request(current, unresolved)
        current["revision"] += 1
        _seal(current)
        return {"verdict": "UNKNOWN_RESOLUTION_FIELD_MISMATCH",
                "workflow": current, "resolution_request": unresolved}

    model_actor = _is_model_actor(actor, provenance)
    if path in {MEASURED_INPUT, HUMAN_EDIT} and (
            model_actor or not str(actor or "").strip()):
        unresolved = make_resolution_request(
            stage=str(request.get("stage", "RESOLUTION")),
            code="UNKNOWN_MODEL_AUTHORITY_ESCALATION",
            reason="a model cannot author measured input or a human edit",
            details={"missing_fields": fields or request["missing_fields"]},
            provenance={"actor": str(actor), "request_id": request_id,
                        **_plain(provenance or {})},
            unsolvable=True, resolution_paths=[TYPED_STOP],
            recommended_path=TYPED_STOP,
            capability_gate=request.get("capability_gate"))
        _append_resolution_request(current, unresolved)
        current["revision"] += 1
        _seal(current)
        return {"verdict": "UNKNOWN_MODEL_AUTHORITY_ESCALATION",
                "workflow": current, "resolution_request": unresolved}

    if path == MEASURED_INPUT and not legacy_human_input:
        source_type = str((provenance or {}).get(
            "source_type", "")).strip().upper()
        trusted_markers = ("HUMAN", "LAB", "MEASURE", "TAPE", "SCAN",
                           "TEST", "DATASHEET", "INSTRUMENT")
        untrusted_markers = ("AUTOMATION", "MODEL", "LLM", "AGENT",
                             "WORKER", "PIPELINE")
        trusted_measurement = (
            bool(source_type)
            and any(marker in source_type for marker in trusted_markers)
            and not any(marker in source_type for marker in untrusted_markers)
        )
        if not trusted_measurement:
            # Preserve what the automation/model supplied, but never let an
            # untrusted provenance string promote it to measured authority.
            # This keeps the proposal auditable and available for comparison
            # while the capability gate remains open for real measurement.
            proposed_claims = [{
                "address": field,
                "value": value,
                "state": PROPOSED,
                "source": str(actor or "untrusted-automation"),
                "source_type": source_type or "UNTRUSTED_AUTOMATION",
                "provenance": {
                    "authority_correction": (
                        "requested MEASURED_INPUT retained as PROPOSED"
                    ),
                    **_plain(provenance or {}),
                },
            } for field, value in sorted(payload.items())]
            current = _ingest_claims(
                current,
                proposed_claims,
                default_source="untrusted-measurement-proposal",
            )
            unresolved = make_resolution_request(
                stage=str(request.get("stage", "RESOLUTION")),
                code="UNKNOWN_MEASUREMENT_PROVENANCE_REQUIRED",
                reason=("MEASURED_INPUT needs named human/lab/instrument "
                        "measurement provenance; automation is not a measurement"),
                details={"missing_fields": required_fields,
                         "source_type": source_type},
                provenance={"actor": str(actor), "request_id": request_id,
                            **_plain(provenance or {})},
                resolution_paths=[MEASURED_INPUT, TYPED_STOP],
                recommended_path=MEASURED_INPUT,
                capability_gate=request.get("capability_gate"))
            _append_resolution_request(current, unresolved)
            current["revision"] += 1
            _seal(current)
            return {"verdict": "UNKNOWN_MEASUREMENT_PROVENANCE_REQUIRED",
                    "workflow": current, "resolution_request": unresolved}

    model_values = (path == CONSENTED_LLM_PROPOSAL
                    or (path == BOUNDED_ALTERNATIVES and model_actor))
    if model_values:
        consent = _valid_consent(current, str(consent_digest or ""), request,
                                 fields)
        if consent is None:
            unresolved = make_resolution_request(
                stage=str(request["stage"]),
                code="UNKNOWN_MODEL_CONSENT_REQUIRED",
                reason="an unexpired digest-bound consent must cover every field",
                details={"missing_fields": fields or request["missing_fields"]},
                provenance={"request_id": request_id,
                            "workflow_digest": current["workflow_digest"]})
            _append_resolution_request(current, unresolved)
            current["revision"] += 1
            _seal(current)
            return {"verdict": "UNKNOWN_MODEL_CONSENT_REQUIRED",
                    "workflow": current, "resolution_request": unresolved}
    if path == CONSENTED_LLM_PROPOSAL:
        claims = [{"address": field, "value": value, "state": PROPOSED,
                   "source": str(actor or "model"), "source_type": "LLM",
                   "provenance": {"consent_digest": consent_digest,
                                  **_plain(provenance or {})}}
                  for field, value in sorted(payload.items())]
        current = _ingest_claims(current, claims, default_source="model")
        status = "RESOLVED_WITH_PROPOSAL"
    elif path == MEASURED_INPUT:
        claims = [{"address": field, "value": value, "state": OBSERVED,
                   "source": str(actor or "human"),
                   "source_type": (HUMAN_INPUT if legacy_human_input
                                   else MEASURED_INPUT),
                   "provenance": _plain(provenance or {})}
                  for field, value in sorted(payload.items())]
        current = _ingest_claims(current, claims, default_source="human")
        status = ("RESOLVED_WITH_HUMAN_INPUT" if legacy_human_input
                  else "RESOLVED_WITH_MEASURED_INPUT")
    elif path == HUMAN_EDIT:
        claims = [{"address": field, "value": value, "state": INFERRED,
                   "source": str(actor or "human-editor"),
                   "source_type": "HUMAN_GEOMETRY_EDIT",
                   "provenance": _plain(provenance or {})}
                  for field, value in sorted(payload.items())]
        current = _ingest_claims(current, claims,
                                 default_source="human-editor")
        status = "RESOLVED_WITH_HUMAN_EDIT"
    elif path == BOUNDED_ALTERNATIVES:
        claims = []
        for field, value in sorted(payload.items()):
            alternatives = (list(value) if isinstance(value, (list, tuple))
                            else [value])
            for index, alternative in enumerate(alternatives):
                claims.append({
                    "address": field,
                    "value": alternative,
                    "state": PROPOSED,
                    "source": str(actor or "bounded-alternative-provider"),
                    "source_type": ("LLM" if model_actor
                                    else "BOUNDED_ALTERNATIVES"),
                    "provenance": {
                        "bounded_alternative": index + 1,
                        "alternative_count": len(alternatives),
                        **({"consent_digest": consent_digest}
                           if consent_digest else {}),
                        **_plain(provenance or {}),
                    },
                })
        current = _ingest_claims(
            current, claims, default_source="bounded-alternatives")
        status = "RESOLVED_WITH_BOUNDED_ALTERNATIVES"
    elif path == CONNECT_PROVIDER:
        status = "PROVIDER_CONNECTION_REQUESTED"
    else:
        stop = _typed_stop(str(request["stage"]), str(request["verdict"]),
                           request["missing_fields"],
                           request["acceptable_evidence"],
                           {"actor": actor, "request_id": request_id,
                            **_plain(provenance or {})})
        current["typed_stops"].append(stop)
        status = "TYPED_STOPPED"

    remaining_fields = sorted(set(required_fields) - set(fields))
    resolution = {
        "request_id": request_id,
        "choice": canonical_choice,
        "resolution_path": path,
        "actor": str(actor),
        "fields": fields,
        "remaining_fields": remaining_fields,
        "status": ("PARTIALLY_RESOLVED" if remaining_fields
                   and path != TYPED_STOP else status),
        "consent_digest": consent_digest,
        "provenance": _plain(provenance or {}),
    }
    resolution["resolution_digest"] = stable_digest(resolution)
    current["resolutions"].append(resolution)
    for row in current["obligations"]:
        if row.get("request_id") == request_id:
            row["status"] = ("OPEN" if remaining_fields
                             and path != TYPED_STOP else status)
            row["remaining_fields"] = remaining_fields
            row["resolution_digest"] = resolution["resolution_digest"]
    current["revision"] += 1
    _seal(current)
    return {"verdict": ("UNKNOWN_PARTIAL_RESOLUTION" if remaining_fields
                        and path != TYPED_STOP else
                        "ANSWER" if path != TYPED_STOP else "TYPED_STOP"),
            "workflow": current, "resolution": resolution}
