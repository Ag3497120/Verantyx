# -*- coding: utf-8 -*-
"""Bind front-image candidates to structure and pattern artifacts.

This module is a deterministic integration boundary.  It deliberately calls
the existing front-image contract, front-layered composer, and structure
compiler instead of classifying garment names or interpreting pixels itself.

Every source candidate keeps the id and digest assigned by
``front_image_generation_contract``.  Every generated structure alternative
keeps the id and digest assigned by ``front_layered_composition``.  Pattern
compilation is attempted independently for every structure alternative; an
unsupported alternative becomes a candidate-specific typed stop and never
removes a sibling candidate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from . import front_image_generation_contract as _front_contract
from . import front_layered_composition as _front_layers
from . import structure_preview as _structure_preview
from . import structure_to_pattern as _pattern_compiler
from . import target_reconstruction as _target_reconstruction


REQUEST_SCHEMA = "garment.front-candidate-artifact-pipeline.request.v1"
SCHEMA = "garment.front-candidate-artifact-pipeline.v1"
PATTERN_ARTIFACT_SCHEMA = "garment.front-candidate-pattern-artifact.v1"

PROPOSED = "PROPOSED"
REVIEW = "REVIEW"
STOPPED = "STOPPED"
ANSWER = "ANSWER"


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
    encoded = json.dumps(
        _plain(value), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stopped(request: Any, code: str, why: str, **detail: Any) -> Dict[str, Any]:
    try:
        input_digest: Optional[str] = stable_digest(request)
    except (TypeError, ValueError, OverflowError):
        input_digest = None
    result = {
        "schema": SCHEMA,
        "verdict": STOPPED,
        "state": STOPPED,
        "reason_code": code,
        "why": why,
        "how_to_close": (
            "supply a valid front-image contract request with proposal-only "
            "candidates and explicit geometric parts"
        ),
        "input_digest": input_digest,
        "source_candidates": [],
        "human_choice": {
            "required": True,
            "candidate_ids": [],
            "selected_candidate_id": None,
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        **copy.deepcopy(detail),
    }
    result["digest"] = stable_digest(result)
    return result


def _candidate_stop(*, source_candidate_id: str,
                    source_candidate_digest: str, code: str, why: str,
                    stage: str, detail: Any = None) -> Dict[str, Any]:
    result = {
        "schema": "garment.front-candidate-artifact-stop.v1",
        "state": STOPPED,
        "verdict": code,
        "reason_code": code,
        "why": why,
        "stage": stage,
        "source_candidate_id": source_candidate_id,
        "source_candidate_digest": source_candidate_digest,
        "authority": {
            "rear": PROPOSED,
            "material": PROPOSED,
            "dimensions": PROPOSED,
            "hidden_joins": PROPOSED,
        },
        "detail": copy.deepcopy(detail),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["digest"] = stable_digest(result)
    return result


def _pattern_artifact(source: Mapping[str, Any],
                      alternative: Mapping[str, Any]) -> Dict[str, Any]:
    source_id = str(source["candidate_id"])
    source_digest = str(source["candidate_digest"])
    structure_id = str(alternative["candidate_id"])
    structure_candidate_digest = str(alternative["candidate_digest"])
    structure_digest = str(alternative["structure_digest"])
    binding = {
        "source_candidate_id": source_id,
        "source_candidate_digest": source_digest,
        "structure_candidate_id": structure_id,
        "structure_candidate_digest": structure_candidate_digest,
        "structure_digest": structure_digest,
    }
    compiled = _pattern_compiler.compile(
        copy.deepcopy(alternative["structure_graph"]),
        candidate_state=PROPOSED,
        candidate_id=structure_id,
    )
    answered = compiled.get("verdict") == ANSWER
    result = {
        "schema": PATTERN_ARTIFACT_SCHEMA,
        # Keep the structure alternative's identity as the pattern candidate
        # identity.  The compiler digest names the artifact, not a replacement
        # garment hypothesis.
        "candidate_id": structure_id,
        "candidate_digest": structure_candidate_digest,
        "source_candidate_id": source_id,
        "source_candidate_digest": source_digest,
        "structure_digest": structure_digest,
        "source_binding": binding,
        "source_binding_digest": stable_digest(binding),
        "state": PROPOSED if answered else STOPPED,
        "verdict": ANSWER if answered else str(
            compiled.get("verdict", "UNKNOWN_PATTERN_COMPILATION")),
        "reason_code": (
            "PROPOSED_CANDIDATE_PATTERN_COMPILED" if answered else
            str(compiled.get("verdict", "UNKNOWN_PATTERN_COMPILATION"))
        ),
        "why": (
            "candidate-specific deterministic cutting geometry compiled"
            if answered else
            str(compiled.get("why", "the structure did not compile to a pattern"))
        ),
        "cuttable_geometric_prototype": bool(
            answered and compiled.get("cuttable_geometric_prototype") is True),
        "compiler_result": copy.deepcopy(compiled),
        "authority": {
            "rear": PROPOSED,
            "material": PROPOSED,
            "dimensions": PROPOSED,
            "hidden_joins": PROPOSED,
        },
        "requires_human_approval": True,
        "auto_approved": False,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    if not answered:
        result["typed_stop"] = {
            "stage": "PATTERN_COMPILATION",
            "reason_code": result["reason_code"],
            "how_to_close": compiled.get(
                "how_to_close",
                "supply or approve the missing typed construction geometry",
            ),
        }
    result["artifact_digest"] = stable_digest(result)
    return result


def _structure_bundle(source: Mapping[str, Any],
                      alternative: Mapping[str, Any], *,
                      front_target: Optional[Mapping[str, Any]] = None,
                      base_avatar: Optional[Mapping[str, Any]] = None,
                      ) -> Dict[str, Any]:
    source_id = str(source["candidate_id"])
    source_digest = str(source["candidate_digest"])
    if (alternative.get("source_candidate_id") != source_id
            or alternative.get("source_candidate_digest") != source_digest):
        stop = _candidate_stop(
            source_candidate_id=source_id,
            source_candidate_digest=source_digest,
            code="UNKNOWN_STRUCTURE_SOURCE_BINDING_MISMATCH",
            why="the structure alternative is not bound to the exact source candidate",
            stage="STRUCTURE_BINDING",
            detail={
                "structure_candidate_id": alternative.get("candidate_id"),
                "received_source_candidate_id": alternative.get(
                    "source_candidate_id"),
                "received_source_candidate_digest": alternative.get(
                    "source_candidate_digest"),
            },
        )
        return {
            "candidate_id": str(alternative.get("candidate_id", "")),
            "candidate_digest": str(alternative.get("candidate_digest", "")),
            "source_candidate_id": source_id,
            "source_candidate_digest": source_digest,
            "state": STOPPED,
            "structure": copy.deepcopy(dict(alternative)),
            "pattern_candidate": None,
            "typed_stop": stop,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        }

    pattern = _pattern_artifact(source, alternative)
    preview = _structure_preview.generate_preview(
        copy.deepcopy(alternative["structure_graph"]),
        candidate_id=str(alternative["candidate_id"]),
    )
    target_bound_preview: Optional[Dict[str, Any]] = None
    if isinstance(front_target, Mapping) and isinstance(base_avatar, Mapping):
        target_bound_preview = (
            _target_reconstruction.build_target_bound_candidate_preview({
                "schema": _target_reconstruction.
                    TARGET_BOUND_PREVIEW_REQUEST_SCHEMA,
                "candidate_id": str(alternative["candidate_id"]),
                "front_target": copy.deepcopy(dict(front_target)),
                "candidate_preview": copy.deepcopy(preview),
                "base_avatar": copy.deepcopy(dict(base_avatar)),
            })
        )
    preview_answered = preview.get("verdict") == ANSWER
    target_answered = (target_bound_preview is None
                       or target_bound_preview.get("verdict") == ANSWER)
    artifact_answered = (pattern["state"] == PROPOSED
                         and preview_answered and target_answered)
    result = {
        "candidate_id": str(alternative["candidate_id"]),
        "candidate_digest": str(alternative["candidate_digest"]),
        "source_candidate_id": source_id,
        "source_candidate_digest": source_digest,
        "structure_digest": str(alternative["structure_digest"]),
        "state": PROPOSED if artifact_answered else STOPPED,
        "structure": copy.deepcopy(dict(alternative)),
        "preview_candidate": copy.deepcopy(preview),
        "target_bound_preview": copy.deepcopy(target_bound_preview),
        "pattern_candidate": pattern,
        "typed_stop": (copy.deepcopy(pattern.get("typed_stop"))
                       if pattern["state"] != PROPOSED else
                       ({
                           "stage": "CANDIDATE_3D_PREVIEW",
                           "reason_code": str(preview.get(
                               "verdict", "UNKNOWN_CANDIDATE_3D_PREVIEW")),
                           "why": str(preview.get(
                               "why", "candidate 3D preview was unavailable")),
                       } if not preview_answered else
                       ({
                           "stage": "TARGET_BOUND_CANDIDATE_3D",
                           "reason_code": str(target_bound_preview.get(
                               "verdict", "UNKNOWN_TARGET_BOUND_PREVIEW")),
                           "why": str(target_bound_preview.get(
                               "why", "target-bound candidate 3D was unavailable")),
                       } if not target_answered
                        and isinstance(target_bound_preview, Mapping)
                        else None))),
        "authority": {
            "rear": PROPOSED,
            "material": PROPOSED,
            "dimensions": PROPOSED,
            "hidden_joins": PROPOSED,
        },
        "requires_human_approval": True,
        "auto_approved": False,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["artifact_digest"] = stable_digest(result)
    return result


def assemble(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the three existing deterministic stages without selecting a result."""
    if not isinstance(request, Mapping):
        return _stopped(
            request, "UNKNOWN_FRONT_CANDIDATE_PIPELINE_REQUEST",
            "request must be an object")
    original = copy.deepcopy(dict(request))
    try:
        if request.get("schema") != REQUEST_SCHEMA:
            return _stopped(
                original, "UNKNOWN_FRONT_CANDIDATE_PIPELINE_SCHEMA",
                f"expected {REQUEST_SCHEMA}")
        front_request = request.get("front_image_request")
        if not isinstance(front_request, Mapping):
            return _stopped(
                original, "UNKNOWN_FRONT_IMAGE_CONTRACT_REQUEST_REQUIRED",
                "front_image_request must contain the existing front-image contract request")

        # Reconstruction and construction remain independent contracts.  If
        # an image-specific target is available, carry its garment-component
        # front into every candidate instead of replacing it with a generic
        # structure primitive.  Omission preserves the historical API.
        target_envelope = request.get("target_reconstruction")
        front_target = request.get("front_target_surface")
        base_avatar = request.get("base_avatar")
        if isinstance(target_envelope, Mapping):
            component_surface = target_envelope.get(
                "garment_component_surface")
            fallback_surface = target_envelope.get("sculpt_surface")
            if isinstance(component_surface, Mapping):
                front_target = component_surface
            elif isinstance(fallback_surface, Mapping):
                front_target = fallback_surface
            if not isinstance(base_avatar, Mapping):
                embedded_avatar = target_envelope.get("base_avatar")
                if isinstance(embedded_avatar, Mapping):
                    base_avatar = embedded_avatar
        if not isinstance(front_target, Mapping):
            front_target = None
        if not isinstance(base_avatar, Mapping):
            base_avatar = None

        contract_result = _front_contract.orchestrate(
            copy.deepcopy(dict(front_request)))
        normalized_candidates = contract_result.get("candidates")
        if (not isinstance(normalized_candidates, Sequence)
                or isinstance(normalized_candidates, (str, bytes))
                or not normalized_candidates
                or any(not isinstance(row, Mapping)
                       for row in normalized_candidates)):
            return _stopped(
                original, "STOP_FRONT_CONTRACT_PRODUCED_NO_CANDIDATES",
                "the front-image contract did not accept any source candidate",
                front_contract_result=contract_result)

        source_candidates = [copy.deepcopy(dict(row))
                             for row in normalized_candidates]
        source_candidates.sort(key=lambda row: str(row["candidate_id"]))
        source_by_id = {str(row["candidate_id"]): row
                        for row in source_candidates}

        composition_request = {
            "schema": _front_layers.REQUEST_SCHEMA,
            "front_only": True,
            "source": copy.deepcopy(contract_result.get(
                "source", front_request.get("source", {}))),
            # These are the normalized candidates returned by the contract;
            # their supplied candidate_digest is intentionally preserved by
            # front_layered_composition.
            "candidates": copy.deepcopy(source_candidates),
        }
        composition_result = _front_layers.compose(composition_request)
        raw_alternatives = composition_result.get("candidates", [])
        alternatives = ([copy.deepcopy(dict(row)) for row in raw_alternatives]
                        if isinstance(raw_alternatives, Sequence)
                        and not isinstance(raw_alternatives, (str, bytes))
                        and all(isinstance(row, Mapping)
                                for row in raw_alternatives) else [])
        alternatives.sort(key=lambda row: str(row.get("candidate_id", "")))

        failures_by_source: Dict[str, List[Dict[str, Any]]] = {}
        raw_failures = composition_result.get("source_candidate_failures", [])
        if (isinstance(raw_failures, Sequence)
                and not isinstance(raw_failures, (str, bytes))):
            for raw in raw_failures:
                if not isinstance(raw, Mapping):
                    continue
                row = copy.deepcopy(dict(raw))
                failures_by_source.setdefault(
                    str(row.get("source_candidate_id", "")), []).append(row)

        bundles: List[Dict[str, Any]] = []
        all_structure_ids: List[str] = []
        compiled_count = 0
        stopped_count = 0
        for source_id in sorted(source_by_id):
            source = source_by_id[source_id]
            source_digest = str(source["candidate_digest"])
            source_alternatives = [
                row for row in alternatives
                if row.get("source_candidate_id") == source_id
            ]
            structure_artifacts = [
                _structure_bundle(
                    source, row,
                    front_target=front_target,
                    base_avatar=base_avatar,
                )
                for row in source_alternatives
            ]
            all_structure_ids.extend(
                row["candidate_id"] for row in structure_artifacts
                if row["candidate_id"])
            compiled_count += sum(
                row.get("pattern_candidate", {}).get("verdict") == ANSWER
                for row in structure_artifacts
                if isinstance(row.get("pattern_candidate"), Mapping)
            )
            stopped_count += sum(row["state"] == STOPPED
                                 for row in structure_artifacts)

            source_stops: List[Dict[str, Any]] = []
            for failure in failures_by_source.get(source_id, []):
                source_stops.append(_candidate_stop(
                    source_candidate_id=source_id,
                    source_candidate_digest=source_digest,
                    code=str(failure.get(
                        "verdict", "UNKNOWN_STRUCTURE_COMPOSITION")),
                    why=str(failure.get(
                        "why", "the source candidate did not compose")),
                    stage="STRUCTURE_COMPOSITION",
                    detail=failure,
                ))
            if not structure_artifacts and not source_stops:
                source_stops.append(_candidate_stop(
                    source_candidate_id=source_id,
                    source_candidate_digest=source_digest,
                    code="UNKNOWN_NO_STRUCTURE_ALTERNATIVE_FOR_SOURCE",
                    why="no structure alternative was returned for this source candidate",
                    stage="STRUCTURE_COMPOSITION",
                    detail=composition_result,
                ))
            stopped_count += len(source_stops)
            bundle = {
                "candidate_id": source_id,
                "candidate_digest": source_digest,
                "state": PROPOSED,
                "front_candidate": copy.deepcopy(source),
                "structure_alternatives": structure_artifacts,
                "candidate_stops": source_stops,
                "authority": {
                    "rear": PROPOSED,
                    "material": PROPOSED,
                    "dimensions": PROPOSED,
                    "hidden_joins": PROPOSED,
                },
                "selected_structure_candidate_id": None,
                "manufacturing_ready": False,
                "manufacturing_certified": False,
            }
            bundle["artifact_digest"] = stable_digest(bundle)
            bundles.append(bundle)

        review_required = (len(all_structure_ids) != 1
                           or stopped_count > 0
                           or contract_result.get("requires_human_approval") is True
                           or composition_result.get("human_choice", {}).get(
                               "required") is True)
        result = {
            "schema": SCHEMA,
            "verdict": REVIEW if review_required else PROPOSED,
            "state": PROPOSED,
            "reason_code": (
                "REVIEW_BOUND_CANDIDATE_ARTIFACTS" if review_required else
                "PROPOSED_BOUND_CANDIDATE_ARTIFACTS"
            ),
            "why": (
                "candidate-specific structures and patterns remain unselected proposals"
            ),
            "input_digest": stable_digest({
                "request_schema": REQUEST_SCHEMA,
                "front_contract_input_digest": contract_result.get(
                    "input_digest"),
            }),
            "front_contract_result": copy.deepcopy(contract_result),
            "front_layered_composition_result": copy.deepcopy(
                composition_result),
            "source_candidate_count": len(bundles),
            "structure_candidate_count": len(all_structure_ids),
            "compiled_pattern_candidate_count": compiled_count,
            "stopped_candidate_count": stopped_count,
            "source_candidates": bundles,
            "human_choice": {
                "required": True,
                "candidate_ids": sorted(all_structure_ids),
                "selected_candidate_id": None,
            },
            "authority": {
                "rear": PROPOSED,
                "material": PROPOSED,
                "dimensions": PROPOSED,
                "hidden_joins": PROPOSED,
            },
            "claims": {
                "existing_front_contract_called": True,
                "existing_front_layered_composition_called": True,
                "existing_structure_preview_called": True,
                "existing_structure_to_pattern_compiler_called": True,
                "image_front_target_binding_used": bool(
                    front_target is not None and base_avatar is not None),
                "pixels_interpreted_here": False,
                "garment_name_classifier_used": False,
                "garment_class_enum_added": False,
                "candidate_auto_selected": False,
                "candidate_auto_approved": False,
                "failed_candidate_dropped": False,
                "manufacturing_certification_created": False,
            },
            "requires_human_approval": True,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        }
        result["digest"] = stable_digest(result)
        return result
    except (TypeError, ValueError, OverflowError, KeyError) as exc:
        return _stopped(
            original, "UNKNOWN_FRONT_CANDIDATE_PIPELINE_MALFORMED",
            str(exc), exception_type=type(exc).__name__)


run = assemble
build = assemble


__all__ = [
    "REQUEST_SCHEMA", "SCHEMA", "PATTERN_ARTIFACT_SCHEMA",
    "assemble", "run", "build", "stable_digest",
]
