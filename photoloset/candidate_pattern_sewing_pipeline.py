# -*- coding: utf-8 -*-
"""Bind one front-derived structure candidate to cut and sew artifacts.

The existing front candidate pipeline stops after
``garment.compiled-pattern.v1``.  The existing manufacturing adapter and
topology sewing planner can already derive cut lines and a dependency order,
but neither result carries the front structure candidate digest.  This module
is the deliberately small integration boundary that keeps that identity from
structure candidate through cutting preview and construction-order proposal.

No corpus, garment-name classifier, LLM, or guessed sewing method is used.
Missing closure, seam, layer, grain, allowance, material, fit, or operator
choices remain candidate-specific ``REVIEW`` records.  A geometric or binding
failure becomes a candidate-specific ``STOPPED`` record without removing a
sibling candidate.  No result is manufacturing-ready or certified.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from . import front_candidate_artifact_pipeline as _front_artifacts
from . import pattern_manufacturing_bundle as _cutting
from . import structure_sewing_plan as _sewing


REQUEST_SCHEMA = _front_artifacts.REQUEST_SCHEMA
SOURCE_SCHEMA = _front_artifacts.SCHEMA
SCHEMA = "garment.candidate-pattern-sewing-pipeline.v1"
CANDIDATE_SCHEMA = "garment.candidate-cut-sew-artifact.v1"
CUTTING_SCHEMA = "garment.candidate-cutting-pattern.v1"
SEWING_SCHEMA = "garment.candidate-topology-sewing-plan.v1"

ANSWER = "ANSWER"
PROPOSED = "PROPOSED"
REVIEW = "REVIEW"
STOPPED = "STOPPED"


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


def _digest_matches(record: Any, *, digest_field: str = "digest",
                    omitted_fields: Sequence[str] = ()) -> bool:
    """Verify an artifact using the digest convention of its producer.

    Some existing producers add the transport-level ``verdict`` after sealing
    their artifact.  ``omitted_fields`` makes that convention explicit at the
    call site instead of accepting an opaque digest as lineage evidence.
    """
    if not isinstance(record, Mapping):
        return False
    expected = _text(record.get(digest_field))
    if expected is None:
        return False
    omitted = {digest_field, *omitted_fields}
    payload = {
        key: copy.deepcopy(value) for key, value in record.items()
        if key not in omitted
    }
    return stable_digest(payload) == expected


def _artifact_lineage(*, candidate_id: str, candidate_digest: str,
                      structure_digest: str, pattern_digest: str,
                      producer_artifact_digest: str,
                      producer: str) -> Dict[str, Any]:
    lineage: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "structure_digest": structure_digest,
        "source_pattern_digest": pattern_digest,
        "producer_artifact_digest": producer_artifact_digest,
        "producer": producer,
    }
    lineage["binding_digest"] = stable_digest(lineage)
    return lineage


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _rows(value: Any) -> Optional[List[Mapping[str, Any]]]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or any(not isinstance(row, Mapping) for row in value)):
        return None
    return list(value)


def _stop(*, candidate_id: str = "", candidate_digest: str = "",
          source_candidate_id: str = "", source_candidate_digest: str = "",
          structure_digest: Optional[str] = None, stage: str, code: str,
          why: str, detail: Any = None,
          pattern_candidate: Any = None,
          cutting_pattern: Any = None,
          topology_plan: Any = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "source_candidate_id": source_candidate_id,
        "source_candidate_digest": source_candidate_digest,
        "structure_digest": structure_digest,
        "state": STOPPED,
        "verdict": code,
        "reason_code": code,
        "typed_stop": {
            "stage": stage,
            "reason_code": code,
            "why": why,
            "how_to_close": (
                "revise or approve this exact candidate's typed geometry or "
                "construction assumptions, then regenerate its artifacts"
            ),
            "detail": copy.deepcopy(detail),
        },
        "pattern_candidate": copy.deepcopy(pattern_candidate),
        "cutting_pattern": copy.deepcopy(cutting_pattern),
        "sewing_plan": copy.deepcopy(topology_plan),
        "requires_human_approval": True,
        "corpus_used": False,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["artifact_digest"] = stable_digest(result)
    return result


def _compact_cutting_pattern(result: Mapping[str, Any], *,
                             candidate_id: str,
                             candidate_digest: str,
                             structure_digest: str,
                             pattern_digest: str) -> Dict[str, Any]:
    cutting_digest = str(result["digest"])
    lineage = _artifact_lineage(
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        structure_digest=structure_digest,
        pattern_digest=pattern_digest,
        producer_artifact_digest=cutting_digest,
        producer="pattern_manufacturing_bundle",
    )
    pieces: List[Dict[str, Any]] = []
    for raw in result.get("pieces", []):
        if not isinstance(raw, Mapping):
            continue
        pieces.append({
            key: copy.deepcopy(raw[key])
            for key in (
                "piece_id", "name", "role", "primitive_kind", "layer",
                "cut_count", "sew_line", "cut_line", "boundary_layers",
                "seam_allowance_cm", "grain", "inner_cutouts", "area_cm2",
                "cut_area_cm2",
            )
            if key in raw
        })
    compact: Dict[str, Any] = {
        "schema": CUTTING_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "structure_digest": structure_digest,
        "source_pattern_digest": pattern_digest,
        "source_cutting_artifact_digest": cutting_digest,
        "state": PROPOSED,
        "verdict": PROPOSED,
        "units": result.get("units", "cm"),
        "pieces": pieces,
        "cut_manifest": copy.deepcopy(result.get("cut_manifest", [])),
        "seams": copy.deepcopy(result.get("seams", [])),
        "layers": copy.deepcopy(result.get("layers", [])),
        "layer_order": copy.deepcopy(result.get("layer_order", [])),
        "seam_allowance_cm": copy.deepcopy(
            result.get("seam_allowance_cm", {})),
        "notches": copy.deepcopy(result.get("notches", {})),
        "grain": copy.deepcopy(result.get("grain", [])),
        "inner_cut_manifest": copy.deepcopy(
            result.get("inner_cut_manifest", [])),
        "remaining_gates": copy.deepcopy(result.get("remaining_gates", [])),
        "exports": {
            "svg_available": isinstance(result.get("svg"), str),
            "dxf_compatible": bool(result.get("dxf_compatible")),
            "payloads_omitted_from_integration_envelope": True,
        },
        "authority": PROPOSED,
        "corpus_used": False,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "provenance": {
            "method": "existing pattern_manufacturing_bundle compact view",
            "lineage": lineage,
            "lineage_binding_digest": lineage["binding_digest"],
            "corpus_used": False,
            "proposed_default_seam_allowance_may_be_present": True,
            "geometry_changed": False,
        },
    }
    compact["digest"] = stable_digest(compact)
    return compact


def _seam_manifest(pattern: Mapping[str, Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for raw in sorted(pattern.get("seams", []),
                      key=lambda row: str(row.get("operation_id", ""))):
        if not isinstance(raw, Mapping):
            continue
        result.append({
            "seam_id": raw.get("operation_id"),
            "kind": raw.get("kind"),
            "a": copy.deepcopy(raw.get("a")),
            "b": copy.deepcopy(raw.get("b")),
            "state": PROPOSED,
            "construction_method_confirmed": any(
                raw.get(name) not in (None, "", {}, [])
                for name in ("construction_method", "seam_method",
                             "method", "stitch_spec")),
        })
    return result


def _topology_sewing_artifact(result: Mapping[str, Any], *,
                              pattern: Mapping[str, Any],
                              candidate_id: str,
                              candidate_digest: str,
                              structure_digest: str) -> Dict[str, Any]:
    pattern_digest = str(pattern["digest"])
    topology_digest = str(result["digest"])
    lineage = _artifact_lineage(
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        structure_digest=structure_digest,
        pattern_digest=pattern_digest,
        producer_artifact_digest=topology_digest,
        producer="structure_sewing_plan",
    )
    reviews = []
    for raw in result.get("reviews", []):
        if isinstance(raw, Mapping):
            reviews.append({"state": REVIEW, **copy.deepcopy(dict(raw))})

    closure_reviews = {
        str(row.get("scope", "")): row for row in reviews
        if row.get("verdict") == "REVIEW_CLOSURE_DETAIL_REQUIRED"
    }
    unresolved_closures: List[Dict[str, Any]] = []
    for seam in _seam_manifest(pattern):
        if seam.get("kind") != "PROCEDURAL_CLOSURE":
            continue
        pieces = sorted({
            str(ref.get("piece_id"))
            for ref in (seam.get("a"), seam.get("b"))
            if isinstance(ref, Mapping) and _text(ref.get("piece_id"))
        })
        matching = next((closure_reviews[piece]
                         for piece in pieces if piece in closure_reviews), None)
        if matching is not None:
            unresolved_closures.append({
                "closure_id": seam.get("seam_id"),
                "piece_ids": pieces,
                "state": REVIEW,
                "why": matching.get("why"),
                "how_to_close": matching.get("how_to_close"),
                "closure_type": None,
            })

    ordered_steps: List[Dict[str, Any]] = []
    for raw in result.get("steps", []):
        if not isinstance(raw, Mapping):
            continue
        operation_id = raw.get("operation_id")
        kind = str(raw.get("kind", ""))
        ordered_steps.append({
            "order": raw.get("step"),
            "step_id": raw.get("step_id"),
            "action": raw.get("action"),
            "piece_ids": copy.deepcopy(raw.get("pieces", [])),
            "seam_id": operation_id if kind in {
                "JOIN", "GATHER", "OVERLAP", "PROCEDURAL_CLOSURE"
            } else None,
            "operation_id": operation_id,
            "kind": raw.get("kind"),
            "quantity": raw.get("quantity"),
            "prerequisite_step_ids": copy.deepcopy(
                raw.get("depends_on", [])),
            "state": PROPOSED,
            "authority": "DERIVED_FROM_COMPILED_TOPOLOGY",
            "manufacturing_validated": False,
        })

    artifact: Dict[str, Any] = {
        "schema": SEWING_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "structure_digest": structure_digest,
        "source_pattern_digest": pattern_digest,
        "source_topology_plan_digest": topology_digest,
        "state": REVIEW if reviews else PROPOSED,
        "verdict": REVIEW if reviews else PROPOSED,
        "order_verdict": result.get("order_verdict"),
        "piece_manifest": [{
            "piece_id": piece.get("piece_id"),
            "cut_count": piece.get("cut_count", 1),
            "role": piece.get("role"),
            "layer": piece.get("layer", 0),
            "state": PROPOSED,
        } for piece in sorted(pattern.get("pieces", []),
                              key=lambda row: str(row.get("piece_id", "")))
            if isinstance(piece, Mapping)],
        "seam_manifest": _seam_manifest(pattern),
        "sewing_order": ordered_steps,
        "dependency_graph": copy.deepcopy(
            result.get("dependency_graph", {})),
        "reviews": reviews,
        "unresolved_closures": unresolved_closures,
        "unknowns": copy.deepcopy(result.get("unknowns", [])),
        "actual_sewing_method_confirmed": False,
        "corpus_used": False,
        "requires_human_approval": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "provenance": {
            "method": "existing structure_sewing_plan topology dependency order",
            "lineage": lineage,
            "lineage_binding_digest": lineage["binding_digest"],
            "corpus_used": False,
            "llm_used": False,
            "sewing_methods_invented": False,
        },
    }
    artifact["digest"] = stable_digest(artifact)
    return artifact


def _prerequisites(cutting: Mapping[str, Any],
                   sewing: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = [{
        "prerequisite_id": "approve-structure-candidate",
        "scope": sewing.get("candidate_id"),
        "state": REVIEW,
        "why": "front-only structure, rear, hidden joins and dimensions remain proposed",
        "how_to_close": "approve this exact candidate digest after 3D and pattern review",
    }]
    for index, gate in enumerate(cutting.get("remaining_gates", []), 1):
        rows.append({
            "prerequisite_id": f"cutting-gate-{index}",
            "scope": "cutting_pattern",
            "state": REVIEW,
            "why": str(gate),
            "how_to_close": "supply and verify the named manufacturing input",
        })
    for review in sewing.get("reviews", []):
        if not isinstance(review, Mapping):
            continue
        rows.append({
            "prerequisite_id": (
                f"sewing-review-{review.get('verdict')}-"
                f"{stable_digest(review)[:10]}"
            ),
            "scope": review.get("scope"),
            "state": REVIEW,
            "why": review.get("why"),
            "how_to_close": review.get("how_to_close"),
        })
    table = {str(row["prerequisite_id"]): row for row in rows}
    return [table[key] for key in sorted(table)]


def _integrate_candidate(candidate: Mapping[str, Any], *,
                         expected_source_candidate_id: str = "",
                         expected_source_candidate_digest: str = "") -> Dict[str, Any]:
    candidate_id = _text(candidate.get("candidate_id")) or ""
    candidate_digest = _text(candidate.get("candidate_digest")) or ""
    source_candidate_id = _text(candidate.get("source_candidate_id")) or ""
    source_candidate_digest = (
        _text(candidate.get("source_candidate_digest")) or "")
    structure_digest = _text(candidate.get("structure_digest"))
    pattern_candidate = candidate.get("pattern_candidate")
    structure_candidate = candidate.get("structure")

    if (source_candidate_id != expected_source_candidate_id
            or source_candidate_digest != expected_source_candidate_digest):
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="CANDIDATE_BINDING",
            code="UNKNOWN_SOURCE_CANDIDATE_BINDING_MISMATCH",
            why="the structure candidate is attached to a different source candidate envelope",
            detail={
                "expected_source_candidate_id": expected_source_candidate_id,
                "expected_source_candidate_digest": (
                    expected_source_candidate_digest),
                "received_source_candidate_id": source_candidate_id,
                "received_source_candidate_digest": source_candidate_digest,
            }, pattern_candidate=pattern_candidate)
    if not candidate_id or not candidate_digest or not structure_digest:
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="CANDIDATE_BINDING",
            code="UNKNOWN_CANDIDATE_DIGEST_BINDING_REQUIRED",
            why="candidate id, candidate digest and structure digest are required",
            pattern_candidate=pattern_candidate)
    if not isinstance(structure_candidate, Mapping):
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="CANDIDATE_BINDING",
            code="UNKNOWN_STRUCTURE_CANDIDATE_REQUIRED",
            why="the candidate-specific structure artifact is missing",
            pattern_candidate=pattern_candidate)
    structure_payload = {
        key: copy.deepcopy(value) for key, value in structure_candidate.items()
        if key != "candidate_digest"
    }
    structure_binding = structure_candidate.get("source_binding")
    structure_binding_valid = bool(
        isinstance(structure_binding, Mapping)
        and structure_binding.get("source_candidate_id")
        == source_candidate_id
        and structure_binding.get("source_candidate_digest")
        == source_candidate_digest
        and structure_binding.get("structure_digest") == structure_digest
        and structure_candidate.get("source_binding_digest")
        == stable_digest(structure_binding)
    )
    if (stable_digest(structure_payload) != candidate_digest
            or structure_candidate.get("candidate_id") != candidate_id
            or structure_candidate.get("candidate_digest") != candidate_digest
            or structure_candidate.get("source_candidate_id")
            != source_candidate_id
            or structure_candidate.get("source_candidate_digest")
            != source_candidate_digest
            or structure_candidate.get("structure_digest") != structure_digest
            or not structure_binding_valid):
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="CANDIDATE_BINDING",
            code="UNKNOWN_STRUCTURE_CANDIDATE_DIGEST_MISMATCH",
            why="candidate_digest does not seal this exact structure alternative",
            detail={
                "recomputed_candidate_digest": stable_digest(structure_payload),
                "structure_candidate_id": structure_candidate.get(
                    "candidate_id"),
                "structure_candidate_digest": structure_candidate.get(
                    "candidate_digest"),
                "structure_artifact_digest": structure_candidate.get(
                    "structure_digest"),
            }, pattern_candidate=pattern_candidate)
    if not _digest_matches(candidate, digest_field="artifact_digest"):
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="CANDIDATE_BINDING",
            code="UNKNOWN_CANDIDATE_ENVELOPE_DIGEST_MISMATCH",
            why="the candidate envelope no longer seals its structure and pattern artifacts",
            detail={
                "received_artifact_digest": candidate.get("artifact_digest"),
            }, pattern_candidate=pattern_candidate)
    if not isinstance(pattern_candidate, Mapping):
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="PATTERN_COMPILATION",
            code="UNKNOWN_CANDIDATE_PATTERN_REQUIRED",
            why="the structure candidate has no candidate-specific pattern",
            pattern_candidate=pattern_candidate)
    if pattern_candidate.get("state") == STOPPED:
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="PATTERN_COMPILATION",
            code=str(pattern_candidate.get(
                "reason_code", "UNKNOWN_PATTERN_COMPILATION")),
            why=str(pattern_candidate.get(
                "why", "candidate-specific pattern compilation stopped")),
            detail=pattern_candidate.get("typed_stop"),
            pattern_candidate=pattern_candidate)

    compiled = pattern_candidate.get("compiler_result")
    if not isinstance(compiled, Mapping) or compiled.get("verdict") != ANSWER:
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="PATTERN_COMPILATION",
            code=str(compiled.get("verdict", "UNKNOWN_PATTERN_COMPILATION")
                     if isinstance(compiled, Mapping)
                     else "UNKNOWN_PATTERN_COMPILATION"),
            why=str(compiled.get("why", "compiled pattern is unavailable")
                    if isinstance(compiled, Mapping)
                    else "compiled pattern is unavailable"),
            pattern_candidate=pattern_candidate)

    pattern_binding = pattern_candidate.get("source_binding")
    expected_pattern_binding = {
        "source_candidate_id": source_candidate_id,
        "source_candidate_digest": source_candidate_digest,
        "structure_candidate_id": candidate_id,
        "structure_candidate_digest": candidate_digest,
        "structure_digest": structure_digest,
    }
    binding_ok = bool(
        pattern_candidate.get("candidate_id") == candidate_id
        and pattern_candidate.get("candidate_digest") == candidate_digest
        and pattern_candidate.get("source_candidate_id") == source_candidate_id
        and pattern_candidate.get("source_candidate_digest")
        == source_candidate_digest
        and pattern_candidate.get("structure_digest") == structure_digest
        and pattern_binding == expected_pattern_binding
        and pattern_candidate.get("source_binding_digest")
        == stable_digest(expected_pattern_binding)
        and _digest_matches(
            pattern_candidate, digest_field="artifact_digest")
        and compiled.get("candidate_id") == candidate_id
        and compiled.get("structure_digest") == structure_digest
        and _text(compiled.get("digest"))
    )
    if not binding_ok:
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="ARTIFACT_BINDING",
            code="UNKNOWN_CANDIDATE_PATTERN_DIGEST_MISMATCH",
            why="the compiled pattern is not bound to this exact candidate and structure digest",
            detail={
                "pattern_candidate_id": pattern_candidate.get("candidate_id"),
                "pattern_candidate_digest": pattern_candidate.get(
                    "candidate_digest"),
                "compiled_candidate_id": compiled.get("candidate_id"),
                "compiled_structure_digest": compiled.get("structure_digest"),
            }, pattern_candidate=pattern_candidate)
    if not _digest_matches(compiled, omitted_fields=("verdict",)):
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="ARTIFACT_BINDING",
            code="UNKNOWN_COMPILED_PATTERN_DIGEST_MISMATCH",
            why="the compiled pattern digest does not seal its candidate-specific geometry",
            detail={
                "compiled_candidate_id": compiled.get("candidate_id"),
                "compiled_structure_digest": compiled.get("structure_digest"),
                "received_compiled_pattern_digest": compiled.get("digest"),
            }, pattern_candidate=pattern_candidate)

    cutting_result = _cutting.build(
        copy.deepcopy(dict(compiled)), allow_proposed_default=True)
    sewing_result = _sewing.plan(copy.deepcopy(dict(compiled)))

    if cutting_result.get("verdict") == ANSWER:
        cutting_provenance = cutting_result.get("provenance")
        cutting_bound = bool(
            cutting_result.get("candidate_id") == candidate_id
            and cutting_result.get("structure_digest") == structure_digest
            and cutting_result.get("source_digest") == compiled.get("digest")
            and isinstance(cutting_provenance, Mapping)
            and cutting_provenance.get("source_digest")
            == compiled.get("digest")
            and _digest_matches(
                cutting_result, omitted_fields=("verdict",))
        )
        if not cutting_bound:
            return _stop(
                candidate_id=candidate_id, candidate_digest=candidate_digest,
                source_candidate_id=source_candidate_id,
                source_candidate_digest=source_candidate_digest,
                structure_digest=structure_digest, stage="ARTIFACT_BINDING",
                code="UNKNOWN_CUTTING_ARTIFACT_DIGEST_MISMATCH",
                why="the cutting artifact is not sealed to this exact candidate and compiled pattern",
                detail={
                    "cutting_candidate_id": cutting_result.get("candidate_id"),
                    "cutting_structure_digest": cutting_result.get(
                        "structure_digest"),
                    "cutting_source_pattern_digest": cutting_result.get(
                        "source_digest"),
                    "cutting_artifact_digest": cutting_result.get("digest"),
                }, pattern_candidate=pattern_candidate)

    if sewing_result.get("order_verdict") == ANSWER:
        sewing_provenance = sewing_result.get("provenance")
        sewing_bound = bool(
            sewing_result.get("candidate_id") == candidate_id
            and sewing_result.get("structure_digest") == structure_digest
            and sewing_result.get("source_pattern_digest")
            == compiled.get("digest")
            and isinstance(sewing_provenance, Mapping)
            and sewing_provenance.get("candidate_id") == candidate_id
            and sewing_provenance.get("structure_digest") == structure_digest
            and sewing_provenance.get("source_pattern_digest")
            == compiled.get("digest")
            and _digest_matches(sewing_result)
        )
        if not sewing_bound:
            return _stop(
                candidate_id=candidate_id, candidate_digest=candidate_digest,
                source_candidate_id=source_candidate_id,
                source_candidate_digest=source_candidate_digest,
                structure_digest=structure_digest, stage="ARTIFACT_BINDING",
                code="UNKNOWN_SEWING_ARTIFACT_DIGEST_MISMATCH",
                why="the sewing-plan artifact and provenance are not sealed to this exact candidate and pattern",
                detail={
                    "sewing_candidate_id": sewing_result.get("candidate_id"),
                    "sewing_structure_digest": sewing_result.get(
                        "structure_digest"),
                    "sewing_source_pattern_digest": sewing_result.get(
                        "source_pattern_digest"),
                    "sewing_artifact_digest": sewing_result.get("digest"),
                }, pattern_candidate=pattern_candidate)

    cutting_pattern = None
    if cutting_result.get("verdict") == ANSWER:
        cutting_pattern = _compact_cutting_pattern(
            cutting_result, candidate_id=candidate_id,
            candidate_digest=candidate_digest,
            structure_digest=structure_digest,
            pattern_digest=str(compiled["digest"]))
    topology_plan = None
    if sewing_result.get("order_verdict") == ANSWER:
        topology_plan = _topology_sewing_artifact(
            sewing_result, pattern=compiled, candidate_id=candidate_id,
            candidate_digest=candidate_digest,
            structure_digest=structure_digest)

    if cutting_result.get("verdict") != ANSWER:
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="CUTTING_PATTERN",
            code=str(cutting_result.get(
                "verdict", "UNKNOWN_CUTTING_PATTERN")),
            why=str(cutting_result.get(
                "why", "candidate cutting pattern could not be produced")),
            detail=cutting_result, pattern_candidate=pattern_candidate,
            topology_plan=topology_plan)
    if sewing_result.get("order_verdict") != ANSWER:
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="SEWING_TOPOLOGY",
            code=str(sewing_result.get(
                "verdict", "UNKNOWN_TOPOLOGY_SEWING_PLAN")),
            why=str(sewing_result.get(
                "why", "candidate sewing topology could not be ordered")),
            detail=sewing_result, pattern_candidate=pattern_candidate,
            cutting_pattern=cutting_pattern)
    assert cutting_pattern is not None and topology_plan is not None

    expected_cutting_lineage = _artifact_lineage(
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        structure_digest=structure_digest,
        pattern_digest=str(compiled["digest"]),
        producer_artifact_digest=str(cutting_result["digest"]),
        producer="pattern_manufacturing_bundle",
    )
    expected_sewing_lineage = _artifact_lineage(
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        structure_digest=structure_digest,
        pattern_digest=str(compiled["digest"]),
        producer_artifact_digest=str(sewing_result["digest"]),
        producer="structure_sewing_plan",
    )
    downstream_bound = bool(
        cutting_result.get("candidate_id") == candidate_id
        and cutting_result.get("structure_digest") == structure_digest
        and cutting_result.get("source_digest") == compiled.get("digest")
        and sewing_result.get("candidate_id") == candidate_id
        and sewing_result.get("structure_digest") == structure_digest
        and sewing_result.get("source_pattern_digest") == compiled.get("digest")
        and cutting_pattern.get("candidate_id") == candidate_id
        and cutting_pattern.get("candidate_digest") == candidate_digest
        and cutting_pattern.get("structure_digest") == structure_digest
        and cutting_pattern.get("source_pattern_digest")
        == compiled.get("digest")
        and cutting_pattern.get("source_cutting_artifact_digest")
        == cutting_result.get("digest")
        and cutting_pattern.get("provenance", {}).get("lineage")
        == expected_cutting_lineage
        and topology_plan.get("candidate_id") == candidate_id
        and topology_plan.get("candidate_digest") == candidate_digest
        and topology_plan.get("structure_digest") == structure_digest
        and topology_plan.get("source_pattern_digest")
        == compiled.get("digest")
        and topology_plan.get("source_topology_plan_digest")
        == sewing_result.get("digest")
        and topology_plan.get("provenance", {}).get("lineage")
        == expected_sewing_lineage
        and _digest_matches(cutting_pattern)
        and _digest_matches(topology_plan)
    )
    authority_safe = bool(
        cutting_result.get("manufacturing_ready") is not True
        and cutting_result.get("manufacturing_certified") is not True
        and sewing_result.get("manufacturing_ready") is not True
        and sewing_result.get("manufacturing_certified") is not True
    )
    if not downstream_bound or not authority_safe:
        return _stop(
            candidate_id=candidate_id, candidate_digest=candidate_digest,
            source_candidate_id=source_candidate_id,
            source_candidate_digest=source_candidate_digest,
            structure_digest=structure_digest, stage="ARTIFACT_BINDING",
            code=("UNKNOWN_DOWNSTREAM_CANDIDATE_DIGEST_MISMATCH"
                  if not downstream_bound
                  else "UNKNOWN_MANUFACTURING_AUTHORITY_ESCALATION"),
            why=("cutting and sewing artifacts are not bound to the same candidate/pattern digest"
                 if not downstream_bound else
                 "a proposal-only downstream artifact claimed manufacturing authority"),
            pattern_candidate=pattern_candidate,
            cutting_pattern=cutting_pattern, topology_plan=topology_plan)

    prerequisites = _prerequisites(cutting_pattern, topology_plan)
    binding = {
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "structure_digest": structure_digest,
        "compiled_pattern_digest": compiled.get("digest"),
        "cutting_source_pattern_digest": cutting_result.get("source_digest"),
        "sewing_source_pattern_digest": sewing_result.get(
            "source_pattern_digest"),
        "cutting_pattern_digest": cutting_pattern.get("digest"),
        "sewing_plan_digest": topology_plan.get("digest"),
        "source_cutting_artifact_digest": cutting_result.get("digest"),
        "source_topology_plan_digest": sewing_result.get("digest"),
        "cutting_lineage_binding_digest": expected_cutting_lineage[
            "binding_digest"],
        "sewing_lineage_binding_digest": expected_sewing_lineage[
            "binding_digest"],
        "same_candidate_digest": True,
        "all_downstream_artifacts_bound": True,
        "state": PROPOSED,
    }
    result: Dict[str, Any] = {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "source_candidate_id": source_candidate_id,
        "source_candidate_digest": source_candidate_digest,
        "structure_digest": structure_digest,
        "state": REVIEW if prerequisites else PROPOSED,
        "verdict": REVIEW if prerequisites else PROPOSED,
        "pattern_candidate": copy.deepcopy(pattern_candidate),
        "cutting_pattern": cutting_pattern,
        "sewing_plan": topology_plan,
        "prerequisites": prerequisites,
        "artifact_binding": binding,
        "artifact_binding_digest": stable_digest(binding),
        "typed_stop": None,
        "requires_human_approval": True,
        "corpus_used": False,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "provenance": {
            "method": (
                "candidate-specific compiled pattern -> existing cutting "
                "adapter + existing topology sewing planner"
            ),
            "corpus_used": False,
            "llm_used": False,
            "actual_sewing_method_invented": False,
            "artifact_binding_digest": stable_digest(binding),
        },
    }
    result["artifact_digest"] = stable_digest(result)
    return result


def bind(front_artifact_result: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach cut/sew artifacts to every structure alternative independently."""
    original = copy.deepcopy(front_artifact_result)
    try:
        if (not isinstance(front_artifact_result, Mapping)
                or front_artifact_result.get("schema") != SOURCE_SCHEMA):
            raise ValueError(f"expected {SOURCE_SCHEMA}")
        source_rows = _rows(front_artifact_result.get("source_candidates"))
        if source_rows is None:
            raise ValueError("source_candidates must be an array")

        candidates: List[Dict[str, Any]] = []
        upstream_stops: List[Dict[str, Any]] = []
        for source in source_rows:
            expected_source_id = _text(source.get("candidate_id"))
            expected_source_digest = _text(source.get("candidate_digest"))
            if expected_source_id is None or expected_source_digest is None:
                raise ValueError(
                    "each source candidate needs candidate_id and candidate_digest")
            alternatives = _rows(source.get("structure_alternatives"))
            if alternatives is None:
                raise ValueError("structure_alternatives must be an array")
            candidates.extend(_integrate_candidate(
                row,
                expected_source_candidate_id=expected_source_id,
                expected_source_candidate_digest=expected_source_digest,
            ) for row in alternatives)
            for stop in source.get("candidate_stops", []):
                if isinstance(stop, Mapping):
                    upstream_stops.append(copy.deepcopy(dict(stop)))

        duplicate_ids = {
            candidate_id for candidate_id, count in Counter(
                str(row.get("candidate_id", "")) for row in candidates
                if _text(row.get("candidate_id"))
            ).items() if count > 1
        }
        if duplicate_ids:
            candidates = [
                (_stop(
                    candidate_id=str(row.get("candidate_id", "")),
                    candidate_digest=str(row.get("candidate_digest", "")),
                    source_candidate_id=str(row.get(
                        "source_candidate_id", "")),
                    source_candidate_digest=str(row.get(
                        "source_candidate_digest", "")),
                    structure_digest=_text(row.get("structure_digest")),
                    stage="ARTIFACT_BINDING",
                    code="UNKNOWN_DUPLICATE_CANDIDATE_ID",
                    why="candidate ids must be globally unique before downstream artifacts are exposed",
                    detail={"duplicate_candidate_id": row.get("candidate_id")},
                    pattern_candidate=row.get("pattern_candidate"),
                    cutting_pattern=row.get("cutting_pattern"),
                    topology_plan=row.get("sewing_plan"),
                ) if row.get("candidate_id") in duplicate_ids else row)
                for row in candidates
            ]
        candidates.sort(key=lambda row: (
            str(row.get("candidate_id", "")),
            str(row.get("candidate_digest", ""))))
        upstream_stops.sort(key=lambda row: (
            str(row.get("source_candidate_id", "")),
            str(row.get("reason_code", row.get("verdict", "")))))
        stopped = [row for row in candidates if row.get("state") == STOPPED]
        review = [row for row in candidates if row.get("state") == REVIEW]
        usable = [row for row in candidates if row.get("state") != STOPPED]
        candidate_ids = [str(row["candidate_id"]) for row in candidates
                         if _text(row.get("candidate_id"))]
        result: Dict[str, Any] = {
            "schema": SCHEMA,
            "verdict": STOPPED if stopped or upstream_stops else (
                REVIEW if review else PROPOSED),
            "state": (STOPPED if not usable else
                      REVIEW if review or stopped or upstream_stops else PROPOSED),
            "source_pipeline_digest": front_artifact_result.get("digest"),
            "candidate_count": len(candidates),
            "review_candidate_count": len(review),
            "stopped_candidate_count": len(stopped) + len(upstream_stops),
            "candidates": candidates,
            "upstream_candidate_stops": upstream_stops,
            "candidate_bindings": [copy.deepcopy(row.get(
                "artifact_binding", {
                    "candidate_id": row.get("candidate_id"),
                    "candidate_digest": row.get("candidate_digest"),
                    "state": STOPPED,
                })) for row in candidates],
            "human_choice": {
                "required": True,
                "candidate_ids": sorted(candidate_ids),
                "selected_candidate_id": None,
            },
            "claims": {
                "candidate_specific_cutting_patterns": bool(usable) and all(
                    isinstance(row.get("cutting_pattern"), Mapping)
                    for row in usable),
                "topology_derived_sewing_order": bool(usable) and all(
                    isinstance(row.get("sewing_plan"), Mapping)
                    for row in usable),
                "corpus_used": False,
                "actual_sewing_methods_confirmed": False,
                "candidate_auto_selected": False,
                "candidate_failures_hidden": False,
                "manufacturing_ready": False,
                "manufacturing_certified": False,
            },
            "requires_human_approval": True,
            "corpus_used": False,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "provenance": {
                "method": (
                    "front candidate artifact pipeline -> candidate-bound "
                    "cutting preview + topology-derived sewing plan"
                ),
                "source_schema": SOURCE_SCHEMA,
                "source_digest_preserved": True,
                "corpus_used": False,
                "input_mutated": front_artifact_result != original,
            },
        }
        result["digest"] = stable_digest(result)
        return result
    except (TypeError, ValueError, OverflowError, KeyError) as exc:
        result = {
            "schema": SCHEMA,
            "verdict": STOPPED,
            "state": STOPPED,
            "reason_code": "UNKNOWN_CANDIDATE_PATTERN_SEWING_INPUT",
            "why": str(exc),
            "source_pipeline_digest": (
                front_artifact_result.get("digest")
                if isinstance(front_artifact_result, Mapping) else None),
            "candidates": [],
            "requires_human_approval": True,
            "corpus_used": False,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        }
        result["digest"] = stable_digest(result)
        return result


def assemble(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the existing front pipeline, then bind cut/sew artifacts."""
    return bind(_front_artifacts.assemble(copy.deepcopy(request)))


run = assemble
build = bind


__all__ = [
    "REQUEST_SCHEMA", "SOURCE_SCHEMA", "SCHEMA", "CANDIDATE_SCHEMA",
    "CUTTING_SCHEMA", "SEWING_SCHEMA", "assemble", "bind", "run", "build",
    "stable_digest",
]
