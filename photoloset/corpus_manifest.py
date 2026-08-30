# -*- coding: utf-8 -*-
"""Fail-closed manifest for optional garment corpora.

The engine does not ship or download a dataset.  This module only describes
the evidence and rights a future corpus must carry before a caller can register
it.  "Free to download" is deliberately not treated as commercial permission.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence


ANSWER = "ANSWER"
BAD_MANIFEST = "UNKNOWN_BAD_CORPUS_MANIFEST"
RIGHTS_UNKNOWN = "UNKNOWN_CORPUS_COMMERCIAL_RIGHTS"
LINEAGE_UNKNOWN = "UNKNOWN_CORPUS_LINEAGE"
UNSUPPORTED_MODALITY = "UNKNOWN_CORPUS_MODALITY"

# Common boundary vocabulary used by every optional recognition/retrieval/
# material/sewing provider.  This lives beside the corpus rights gate so a
# provider cannot invent a softer availability or rights vocabulary.
PROVIDER_BOUNDARY_SCHEMA = "garment.provider-boundary.v1"
PROVIDER_RESULT_SCHEMA = "garment.provider-result.v1"
PROVIDER_CONSENT_SCHEMA = "garment.provider-consent.v1"
PROVIDER_REPORT_SCHEMA = "garment.provider-capability-report.v1"
CONNECT_PROVIDER = "CONNECT_PROVIDER"
CONSENTED_LLM_PROPOSAL = "CONSENTED_LLM_PROPOSAL"
TYPED_STOP = "TYPED_STOP"
PROVIDER_RESULT = "PROVIDER_RESULT"
PROPOSED_UNOBSERVED = "PROPOSED_UNOBSERVED"
DIRECT_AUTHORITIES = {"OBSERVED", "MEASURED", "CALIBRATED", "VALIDATED"}
PROVIDER_HEALTH = {
    "READY", "DEGRADED", "UNAVAILABLE", "FAILED", "RIGHTS_REFUSED",
}
CONSENT_SCOPES = {
    "VISIBLE_GARMENT_ANALYSIS",
    "RETRIEVAL_HYPOTHESIS",
    "REAR_HYPOTHESIS",
    "MATERIAL_HYPOTHESIS",
    "BODY_MEASUREMENT_HYPOTHESIS",
    "SEAM_FINISH_HYPOTHESIS",
    "WIND_RESPONSE_HYPOTHESIS",
    "SEAM_TEST_HYPOTHESIS",
}

# Provider capabilities are named by the evidence they can actually supply,
# not by a product or model name.  This is the shared boundary catalogue for
# recognition, retrieval, calibration and physical validation.  An LLM may
# fill only the explicitly listed proposal scopes; it never substitutes for a
# measurement, calibration, wind-tunnel run or seam test.
PROVIDER_CAPABILITY_SPECS: Dict[str, Dict[str, Any]] = {
    "MULTIMODAL_GARMENT_ANALYSIS": {
        "stage": "VISIBLE_GARMENT_ANALYSIS",
        "consent_scope": "VISIBLE_GARMENT_ANALYSIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["HUMAN_REVIEWED_VISIBLE_REGION"],
    },
    "FASHION_SIMILARITY_RETRIEVAL": {
        "stage": "FASHION_RETRIEVAL",
        "consent_scope": "RETRIEVAL_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["RIGHTS_CLEARED_INDEX_RECORD"],
    },
    "GARMENT_CONSTRUCTION_RETRIEVAL": {
        "stage": "CONSTRUCTION_RETRIEVAL",
        "consent_scope": "RETRIEVAL_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["RIGHTS_CLEARED_CONSTRUCTION_RECORD"],
    },
    "REAR_REFERENCE_RETRIEVAL": {
        "stage": "REAR_RECONSTRUCTION",
        "consent_scope": "REAR_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["RIGHTS_CLEARED_REAR_REFERENCE"],
    },
    "MULTIMODAL_REAR_HYPOTHESIS": {
        "stage": "REAR_RECONSTRUCTION",
        "consent_scope": "REAR_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["REAR_IMAGE", "MULTIVIEW_SCAN"],
    },
    "GEOMETRIC_REAR_EVIDENCE": {
        "stage": "REAR_RECONSTRUCTION",
        "consent_scope": "REAR_HYPOTHESIS",
        "allow_llm_proposal": False,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["DETERMINISTIC_GEOMETRY_RESULT"],
    },
    "NAMED_USER_AUDIT_EVIDENCE": {
        "stage": "HUMAN_AUDIT",
        "consent_scope": "REAR_HYPOTHESIS",
        "allow_llm_proposal": False,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["NAMED_HUMAN_AUDIT"],
    },
    "REAR_GEOMETRY_ALTERNATIVES": {
        "stage": "REAR_RECONSTRUCTION",
        "consent_scope": "REAR_HYPOTHESIS",
        "allow_llm_proposal": False,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["DETERMINISTIC_GEOMETRY_RESULT"],
    },
    "MATERIAL_HYPOTHESIS": {
        "stage": "MATERIAL_HYPOTHESIS",
        "consent_scope": "MATERIAL_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["VISIBLE_MATERIAL_CUE"],
    },
    "MATERIAL_PROPERTY_MEASUREMENT": {
        "stage": "MATERIAL_MEASUREMENT",
        "consent_scope": "MATERIAL_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": "MEASURED",
        "direct_authorities": ["MEASURED"],
        "direct_evidence_types": [
            "MATERIAL_LAB_MEASUREMENT", "NAMED_MATERIAL_DATASHEET",
        ],
    },
    "MATERIAL_PROPERTY_CALIBRATION": {
        "stage": "MATERIAL_CALIBRATION",
        "consent_scope": "MATERIAL_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": "CALIBRATED",
        "direct_authorities": ["MEASURED", "CALIBRATED"],
        "direct_evidence_types": [
            "CALIBRATED_SWATCH_TEST", "CALIBRATED_MATERIAL_DATASHEET",
        ],
    },
    "BODY_MEASUREMENT": {
        "stage": "BODY_FIT",
        "consent_scope": "BODY_MEASUREMENT_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": "MEASURED",
        "direct_authorities": ["MEASURED"],
        "direct_evidence_types": ["TAPE_MEASUREMENT", "BODY_SCAN"],
    },
    "SEWING_CONSTRUCTION_CORPUS": {
        "stage": "SEWING_METHOD",
        "consent_scope": "SEAM_FINISH_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["RIGHTS_CLEARED_CONSTRUCTION_RECORD"],
    },
    "SEAM_FINISHING_HYPOTHESIS": {
        "stage": "SEWING_METHOD",
        "consent_scope": "SEAM_FINISH_HYPOTHESIS",
        "allow_llm_proposal": True,
        "provider_authority_ceiling": PROPOSED_UNOBSERVED,
        "direct_evidence_types": ["APPROVED_SEWING_SPEC"],
    },
    "WIND_TUNNEL_VALIDATION": {
        "stage": "AERODYNAMIC_VALIDATION",
        "consent_scope": "WIND_RESPONSE_HYPOTHESIS",
        "allow_llm_proposal": False,
        "provider_authority_ceiling": "VALIDATED",
        "direct_authorities": ["MEASURED", "CALIBRATED", "VALIDATED"],
        "direct_evidence_types": [
            "WIND_TUNNEL_MEASUREMENT", "VALIDATED_DNS_DATASET",
        ],
    },
    "SEAM_STRENGTH_TEST": {
        "stage": "SEAM_VALIDATION",
        "consent_scope": "SEAM_TEST_HYPOTHESIS",
        "allow_llm_proposal": False,
        "provider_authority_ceiling": "VALIDATED",
        "direct_authorities": ["MEASURED", "CALIBRATED", "VALIDATED"],
        "direct_evidence_types": [
            "PHYSICAL_SEAM_TEST", "CALIBRATED_SEAM_TEST_RECORD",
        ],
    },
}

SCHEMA = "garment.corpus-manifest.v1"
RIGHT_VALUES = {"allowed", "denied", "unknown"}
MODALITIES = {
    "garment_images", "calibrated_multiview", "segmentation_masks",
    "structure_graphs", "patterns_2d", "sewing_construction",
    "material_measurements", "drape_sequences", "meshes_3d",
}

# A sewing answer needs construction-bearing records.  Image embeddings are a
# retrieval hint and intentionally are not a modality in this schema.
CONSTRUCTION_MODALITIES = {"patterns_2d", "sewing_construction"}


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def _plain(value: Any) -> Any:
    """Return deterministic JSON data without retaining caller-owned values."""
    return json.loads(json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def commercial_rights_status(
    value: Any, *, require_commercial: bool = True,
) -> Dict[str, Any]:
    """Read only explicit asset/corpus rights; never infer them from a model.

    The FashionSigLIP model licence and the licence of an indexed image are
    different facts.  This helper therefore looks only at rights records on
    ``value`` and returns UNKNOWN when those records are absent.
    """
    if not require_commercial:
        return {
            "required": False, "allowed": True, "state": "NOT_REQUIRED",
            "basis": "caller did not request commercial-use clearance",
            "legal_opinion": False,
        }
    row = value if isinstance(value, Mapping) else {}
    candidates = []
    for key in ("rights_review", "rights"):
        child = row.get(key)
        if isinstance(child, Mapping):
            candidates.append(child)
    licence = row.get("license", row.get("licence"))
    if isinstance(licence, Mapping):
        # Asset records commonly put commercial_use directly on ``license``;
        # corpus manifests put it under ``license.rights``.  Both are explicit
        # records, so accept either shape without interpreting licence prose.
        candidates.append(licence)
        rights = licence.get("rights")
        if isinstance(rights, Mapping):
            candidates.append(rights)
    saw_allowed = False
    saw_denied = False
    for rights in candidates:
        authorized = rights.get("use_authorized")
        commercial = rights.get(
            "commercial_use", rights.get("commercial"))
        if authorized is False or commercial is False or commercial in (
                "denied", "restricted"):
            saw_denied = True
        if authorized is True or commercial is True or commercial == "allowed":
            saw_allowed = True
    # Conflicting rights records fail closed.  In particular, an optimistic
    # provider-level review must not override an asset-level denial merely
    # because it appeared first in the input mapping.
    if saw_denied:
        state = "DENIED"
        basis = "at least one supplied rights record explicitly refuses this use"
    elif saw_allowed:
        state = "ALLOWED"
        basis = "the supplied rights record explicitly authorizes commercial use"
    else:
        state = "UNKNOWN"
        basis = "no explicit commercial-use authorization was supplied"
    return {
        "required": True,
        "allowed": state == "ALLOWED",
        "state": state,
        "basis": basis,
        "legal_opinion": False,
    }


def provider_resolution_options(
    provider_id: str, capability: str, *, consent_scope: str,
    allow_llm_proposal: bool = True,
) -> List[Dict[str, Any]]:
    """Typed, UI-renderable ways to close an unavailable provider boundary."""
    if consent_scope not in CONSENT_SCOPES:
        raise ValueError(f"unsupported provider consent scope: {consent_scope}")
    options: List[Dict[str, Any]] = [{
        "action": CONNECT_PROVIDER,
        "provider_id": str(provider_id),
        "capability": str(capability),
        "requires_explicit_consent": False,
        "result_authority": "PROVIDER_EVIDENCE_SUBJECT_TO_RIGHTS_GATE",
    }]
    if allow_llm_proposal:
        options.append({
            "action": CONSENTED_LLM_PROPOSAL,
            "provider_id": str(provider_id),
            "capability": str(capability),
            "consent_scope": consent_scope,
            "requires_explicit_consent": True,
            "result_authority": "PROPOSED_UNOBSERVED_ONLY",
            "cannot_promote_to": [
                "OBSERVED", "MEASURED", "CALIBRATED", "VALIDATED",
                "MANUFACTURING_CERTIFIED",
            ],
        })
    options.append({
        "action": TYPED_STOP,
        "provider_id": str(provider_id),
        "capability": str(capability),
        "verdict": "TYPED_STOP",
        "requires_explicit_consent": False,
        "terminal_for_this_attempt": True,
        "state_mutation_allowed": False,
        "resumable_by": [CONNECT_PROVIDER],
        "why": "the required provider evidence is unavailable and must not be fabricated",
    })
    return options


def provider_capability_spec(capability: str) -> Dict[str, Any]:
    """Return the deterministic authority contract for one capability."""
    name = str(capability)
    configured = PROVIDER_CAPABILITY_SPECS.get(name)
    if configured is None:
        return {
            "capability": name,
            "stage": "OPTIONAL_PROVIDER",
            "consent_scope": None,
            "allow_llm_proposal": True,
            "provider_authority_ceiling": PROPOSED_UNOBSERVED,
            "direct_authorities": [],
            "direct_evidence_types": [],
            "front_image_authority_ceiling": PROPOSED_UNOBSERVED,
            "front_image_can_be_observed": False,
            "llm_can_satisfy_measurement_or_validation": False,
        }
    spec = _plain(configured)
    spec["capability"] = name
    spec.setdefault("direct_authorities", [])
    spec["front_image_authority_ceiling"] = PROPOSED_UNOBSERVED
    spec["front_image_can_be_observed"] = False
    spec["llm_can_satisfy_measurement_or_validation"] = False
    return spec


def provider_capability(
    provider_id: str, capability: str, *, health: str, available: bool,
    reason: str = "", consent_scope: Optional[str] = None,
    allow_llm_proposal: Optional[bool] = None,
    require_commercial: bool = False,
    rights: Any = None, details: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the common typed health/capability record."""
    health = str(health).upper()
    if health not in PROVIDER_HEALTH:
        raise ValueError(f"unsupported provider health: {health}")
    contract = provider_capability_spec(str(capability))
    effective_scope = consent_scope or contract.get("consent_scope")
    if effective_scope not in CONSENT_SCOPES:
        raise ValueError(
            f"unsupported provider consent scope: {effective_scope}")
    llm_allowed = (bool(contract.get("allow_llm_proposal"))
                   if allow_llm_proposal is None
                   else bool(allow_llm_proposal))
    rights_gate = commercial_rights_status(
        rights, require_commercial=require_commercial)
    effective = (bool(available) and health in {"READY", "DEGRADED"}
                 and rights_gate["allowed"])
    effective_health = health
    if available and not rights_gate["allowed"]:
        effective_health = "RIGHTS_REFUSED"
    return {
        "schema": PROVIDER_BOUNDARY_SCHEMA,
        "provider_id": str(provider_id),
        "capability": str(capability),
        "health": effective_health,
        "available": effective,
        "provider_reachable_or_supplied": bool(available),
        "reason": str(reason or ""),
        "commercial_rights_gate": rights_gate,
        "capability_contract": contract,
        "consent_scope": effective_scope,
        "result_authority_ceiling": contract[
            "provider_authority_ceiling"],
        "front_image_authority_ceiling": PROPOSED_UNOBSERVED,
        "front_image_can_be_observed": False,
        "resolution_options": (
            [] if effective else provider_resolution_options(
                str(provider_id), str(capability),
                consent_scope=effective_scope,
                allow_llm_proposal=llm_allowed)
        ),
        "details": _plain(dict(details or {})),
    }


def provider_result(
    capability: Mapping[str, Any], *, proposals: Sequence[Any] = (),
    provenance: Sequence[Any] = (), failure: Optional[Mapping[str, Any]] = None,
    result_authority: str = PROPOSED_UNOBSERVED,
    source_origin: str = "UNSPECIFIED_PROVIDER",
    direct_observation: bool = False,
) -> Dict[str, Any]:
    """Wrap provider output and enforce its observation-authority ceiling.

    A front image can produce useful proposals but cannot observe the rear,
    material mechanics, body dimensions, wind response or seam strength.  A
    provider asking for direct authority without direct provenance is retained
    only as a proposal and receives a typed authority refusal.
    """
    if capability.get("schema") != PROVIDER_BOUNDARY_SCHEMA:
        raise ValueError("provider_result requires a provider capability record")
    available = bool(capability.get("available"))
    requested = str(result_authority).upper()
    origin = str(source_origin).upper()
    from_front_image = "FRONT_IMAGE" in origin or origin in {
        "SINGLE_FRONT", "FRONT_PHOTO", "FRONT_VIEW_IMAGE",
    }
    contract = capability.get("capability_contract")
    contract = contract if isinstance(contract, Mapping) else {}
    direct_allowed = set(contract.get("direct_authorities", []))
    authority_refusal: Optional[Dict[str, Any]] = None
    accepted_authority = requested
    if requested in DIRECT_AUTHORITIES and (
            from_front_image or not direct_observation
            or requested not in direct_allowed):
        accepted_authority = PROPOSED_UNOBSERVED
        authority_refusal = {
            "verdict": "UNKNOWN_DIRECT_PROVIDER_EVIDENCE_REQUIRED",
            "requested_authority": requested,
            "accepted_authority": PROPOSED_UNOBSERVED,
            "source_origin": origin,
            "front_image_cannot_be_observed": from_front_image,
            "direct_observation_supplied": bool(direct_observation),
            "required_evidence_types": _plain(
                contract.get("direct_evidence_types", [])),
        }
    elif requested not in DIRECT_AUTHORITIES:
        accepted_authority = PROPOSED_UNOBSERVED
    failure_record = (_plain(dict(failure))
                      if isinstance(failure, Mapping) and failure else None)
    requested_satisfied = (
        available and failure_record is None and accepted_authority == requested)
    typed_stop = not available or failure_record is not None or (
        requested in DIRECT_AUTHORITIES and not requested_satisfied)
    state = (
        "AWAITING_PROVIDER_OR_CONSENT" if not available else
        "TYPED_STOP_PROVIDER_RESULT_FAILURE" if failure_record else
        "TYPED_STOP_DIRECT_EVIDENCE_REQUIRED" if authority_refusal else
        accepted_authority
    )
    return {
        "schema": PROVIDER_RESULT_SCHEMA,
        "provider": _plain(dict(capability)),
        "result_action": TYPED_STOP if typed_stop else PROVIDER_RESULT,
        "verdict": (
            str(failure_record.get("verdict", "UNKNOWN_PROVIDER_RESULT_FAILED"))
            if failure_record else
            "PROPOSED" if available and not authority_refusal else
            authority_refusal["verdict"] if authority_refusal else
            "UNKNOWN_PROVIDER_UNAVAILABLE"
        ),
        "state": state,
        "typed_stop": typed_stop,
        "requested_authority": requested,
        "accepted_authority": accepted_authority,
        "requested_authority_satisfied": requested_satisfied,
        "source_origin": origin,
        "front_image_origin": from_front_image,
        "observation_state": (
            accepted_authority if accepted_authority in DIRECT_AUTHORITIES
            else "UNKNOWN_UNOBSERVED"
        ),
        "observed": (available and failure_record is None
                     and accepted_authority in DIRECT_AUTHORITIES),
        "authority_refusal": authority_refusal,
        "proposals": _plain(list(proposals)) if available else [],
        "provenance": _plain(list(provenance)) if available else [],
        "failure": failure_record,
        "fact_promotions": [],
        "automatic_observed_promotion": False,
        "resolution_options": _plain(capability.get("resolution_options", [])),
    }


def provider_capability_report(
    provider_states: Optional[Mapping[str, Any]] = None, *,
    require_commercial: bool = False,
) -> Dict[str, Any]:
    """Report every garment provider boundary without probing the network.

    ``provider_states`` contains caller-supplied health snapshots keyed by
    capability.  Missing entries are deliberately UNAVAILABLE; this function
    never invents a connected provider, an index, a measurement, or a test.
    """
    supplied = provider_states if isinstance(provider_states, Mapping) else {}
    rows: Dict[str, Any] = {}
    for capability in sorted(PROVIDER_CAPABILITY_SPECS):
        raw = supplied.get(capability, {})
        raw = raw if isinstance(raw, Mapping) else {}
        available = raw.get("available") is True
        health = str(raw.get(
            "health", "READY" if available else "UNAVAILABLE")).upper()
        boundary = provider_capability(
            str(raw.get("provider_id") or capability.lower()), capability,
            health=health, available=available,
            reason=str(raw.get("reason") or (
                "caller supplied provider capability" if available else
                "provider capability was not supplied")),
            require_commercial=bool(raw.get(
                "require_commercial", require_commercial)),
            rights=raw,
            details={
                "configured": capability in supplied,
                "network_probe_performed": False,
            },
        )
        rows[capability] = {
            "provider_boundary": boundary,
            "provider_result": provider_result(
                boundary,
                proposals=(raw.get("proposals", [])
                           if isinstance(raw.get("proposals", []), Sequence)
                           and not isinstance(raw.get("proposals"), (str, bytes))
                           else []),
                provenance=(raw.get("provenance", [])
                            if isinstance(raw.get("provenance", []), Sequence)
                            and not isinstance(raw.get("provenance"), (str, bytes))
                            else []),
                result_authority=str(raw.get(
                    "result_authority", PROPOSED_UNOBSERVED)),
                source_origin=str(raw.get(
                    "source_origin", "UNSPECIFIED_PROVIDER")),
                direct_observation=raw.get("direct_observation") is True,
            ),
        }
    return {
        "schema": PROVIDER_REPORT_SCHEMA,
        "capabilities": rows,
        "ready": sorted(
            key for key, row in rows.items()
            if row["provider_boundary"]["available"]),
        "unresolved": sorted(
            key for key, row in rows.items()
            if not row["provider_boundary"]["available"]),
        "network_probe_performed": False,
        "fabricated_results": False,
        "front_image_can_be_observed": False,
    }


def validate_provider_consent(
    consent: Any, *, required_scope: str,
    subject_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate explicit, actor-bound consent for one LLM proposal scope."""
    if required_scope not in CONSENT_SCOPES:
        raise ValueError(f"unsupported provider consent scope: {required_scope}")
    if not isinstance(consent, Mapping):
        return _refusal(
            "UNKNOWN_PROVIDER_CONSENT_REQUIRED",
            "a typed, named consent record is required",
            required_scope=required_scope,
        )
    if consent.get("schema") != PROVIDER_CONSENT_SCHEMA:
        return _refusal(
            "UNKNOWN_PROVIDER_CONSENT_SCHEMA",
            f"consent.schema must be {PROVIDER_CONSENT_SCHEMA}",
            required_scope=required_scope,
        )
    if consent.get("action") != CONSENTED_LLM_PROPOSAL:
        return _refusal(
            "UNKNOWN_PROVIDER_CONSENT_ACTION",
            f"consent.action must be {CONSENTED_LLM_PROPOSAL}",
            required_scope=required_scope,
        )
    actor = consent.get("by")
    if not isinstance(actor, str) or not actor.strip():
        return _refusal(
            "UNKNOWN_NAMED_PROVIDER_CONSENT_REQUIRED",
            "consent must name the person granting it",
            required_scope=required_scope,
        )
    scopes = consent.get("scopes")
    if (not isinstance(scopes, Sequence) or isinstance(scopes, (str, bytes))
            or required_scope not in scopes):
        return _refusal(
            "UNKNOWN_PROVIDER_CONSENT_SCOPE",
            "consent does not include the required scope",
            required_scope=required_scope,
            supplied_scopes=list(scopes) if isinstance(scopes, Sequence)
            and not isinstance(scopes, (str, bytes)) else [],
        )
    if subject_digest is not None and consent.get("subject_digest") != subject_digest:
        return _refusal(
            "UNKNOWN_PROVIDER_CONSENT_STALE",
            "consent is not bound to the current subject digest",
            required_scope=required_scope,
            expected_subject_digest=subject_digest,
        )
    return {
        "verdict": ANSWER,
        "schema": PROVIDER_CONSENT_SCHEMA,
        "action": CONSENTED_LLM_PROPOSAL,
        "scope": required_scope,
        "by": actor.strip(),
        "subject_digest": subject_digest,
        "authority": "PROPOSED_UNOBSERVED_ONLY",
        "observed_promotion": False,
    }


def validate(manifest: Mapping[str, Any], *, require_commercial: bool = True,
             purpose: str = "retrieval") -> Dict[str, Any]:
    """Validate rights, lineage and machine-readable modalities.

    Legal review is represented as an explicit unknown; this function is not a
    legal opinion and never upgrades ambiguous licence text.
    """
    if not isinstance(manifest, Mapping):
        return _refusal(BAD_MANIFEST, "manifest must be an object")
    required = ("schema", "name", "version", "license", "lineage",
                "modalities", "record_format")
    missing = [key for key in required if key not in manifest]
    if missing:
        return _refusal(BAD_MANIFEST, "required fields are missing",
                        missing=missing)
    if manifest.get("schema") != SCHEMA:
        return _refusal(BAD_MANIFEST, f"schema must be {SCHEMA}")

    licence = manifest.get("license")
    if not isinstance(licence, Mapping):
        return _refusal(BAD_MANIFEST, "license must be an object")
    rights = licence.get("rights")
    if not isinstance(rights, Mapping):
        return _refusal(BAD_MANIFEST, "license.rights must be an object")
    right_names = ("commercial_use", "derivatives", "redistribution")
    malformed = [name for name in right_names
                 if rights.get(name) not in RIGHT_VALUES]
    if malformed:
        return _refusal(BAD_MANIFEST,
                        "every right must be allowed, denied, or unknown",
                        malformed=malformed)
    if not isinstance(licence.get("url"), str) or not licence["url"].strip():
        return _refusal(BAD_MANIFEST,
                        "license.url must cite the controlling text")
    if require_commercial and rights["commercial_use"] != "allowed":
        return _refusal(
            RIGHTS_UNKNOWN,
            "commercial use is not explicitly allowed by the recorded licence",
            commercial_use=rights["commercial_use"],
            legal_review_required=rights["commercial_use"] == "unknown")

    lineage = manifest.get("lineage")
    if (not isinstance(lineage, Sequence) or isinstance(lineage, (str, bytes))
            or not lineage
            or any(not isinstance(item, Mapping) or not item.get("source")
                   for item in lineage)):
        return _refusal(LINEAGE_UNKNOWN,
                        "lineage needs at least one named source record")

    modalities = manifest.get("modalities")
    if (not isinstance(modalities, Sequence)
            or isinstance(modalities, (str, bytes))):
        return _refusal(BAD_MANIFEST, "modalities must be a list")
    unknown = sorted(set(modalities) - MODALITIES)
    if unknown:
        return _refusal(UNSUPPORTED_MODALITY,
                        "manifest contains an unsupported modality",
                        unsupported=unknown)
    if purpose == "sewing" and not (set(modalities) & CONSTRUCTION_MODALITIES):
        return _refusal(UNSUPPORTED_MODALITY,
                        "sewing retrieval requires patterns or construction steps",
                        required=sorted(CONSTRUCTION_MODALITIES))

    record_format = manifest.get("record_format")
    if not isinstance(record_format, Mapping):
        return _refusal(BAD_MANIFEST, "record_format must be an object")
    if record_format.get("units") not in ("SI", "explicit_per_field"):
        return _refusal(BAD_MANIFEST,
                        "record_format.units must be SI or explicit_per_field")
    if not record_format.get("schema_url"):
        return _refusal(BAD_MANIFEST,
                        "record_format.schema_url is required")

    normalised = json.loads(json.dumps(manifest, ensure_ascii=False,
                                       sort_keys=True))
    return {
        "verdict": ANSWER,
        "manifest": normalised,
        "digest": _digest(normalised),
        "commercial_use_recorded": rights["commercial_use"] == "allowed",
        "legal_opinion": False,
        "modalities": sorted(set(modalities)),
        "construction_bearing": bool(set(modalities)
                                     & CONSTRUCTION_MODALITIES),
    }


def expected_record_fields(modality: str) -> Dict[str, Any]:
    """Return the typed payload expected for one modality."""
    fields = {
        "garment_images": ["asset_id", "image_uri", "view", "provenance"],
        "calibrated_multiview": ["asset_id", "camera", "scale", "view", "image_uri"],
        "segmentation_masks": ["asset_id", "image_uri", "mask_uri", "label_map"],
        "structure_graphs": ["asset_id", "nodes", "joins", "assumptions"],
        "patterns_2d": ["asset_id", "units", "pieces", "seam_pairs", "notches", "grain"],
        "sewing_construction": ["asset_id", "steps", "preconditions", "stitches", "tools"],
        "material_measurements": ["asset_id", "test_method", "SI_properties", "uncertainty"],
        "drape_sequences": ["asset_id", "frames", "time_step_s", "boundary_conditions"],
        "meshes_3d": ["asset_id", "vertices", "faces", "units", "correspondence"],
    }
    if modality not in fields:
        return _refusal(UNSUPPORTED_MODALITY, "unknown modality",
                        modality=modality)
    return {"verdict": ANSWER, "modality": modality,
            "required_fields": fields[modality]}
