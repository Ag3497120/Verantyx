# -*- coding: utf-8 -*-
"""Cross-stage engineering review for one garment candidate.

This module does not solve cloth mechanics.  It prevents a successful call to
one numerical kernel from being presented as a successful garment.  Pattern,
topology, manufacturing preview, simulation, strength calibration and wearer
comfort remain separate gates with separate authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SCHEMA = "garment.engineering-review.v1"
REVIEW = "REVIEW_ENGINEERING_GATES_REQUIRED"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


def _gate(name: str, verdict: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {"gate": name, "verdict": verdict, "why": why, **detail}


def assembly_connectivity(pattern: Mapping[str, Any]) -> Dict[str, Any]:
    """Check that every declared garment unit is one sewn/layered component.

    Edge-length checks answer whether named edges *could* be sewn.  They do not
    answer whether the result is one garment: a bodice, two sleeves and an
    overlay can each have valid intrinsic closure seams while remaining four
    disconnected objects.  This gate keeps those questions separate.

    ``attributes.garment_unit`` explicitly permits separates (for example an
    ``upper`` and ``lower`` unit).  Without that declaration every pattern
    piece belongs to one candidate garment and must be connected.  A relation
    is counted only when a compiled seam or layer names two different pieces;
    a wrap's self-closing seam cannot connect it to another piece.
    """
    pieces = pattern.get("pieces")
    if (not isinstance(pieces, Sequence)
            or isinstance(pieces, (str, bytes)) or not pieces
            or any(not isinstance(row, Mapping) for row in pieces)):
        return {
            "verdict": "REVIEW_PATTERN_PIECES_REQUIRED",
            "connected": False,
            "why": "assembly connectivity requires typed compiled pattern pieces",
            "components": [],
            "disconnected_units": [],
        }

    ids: List[str] = []
    unit_of: Dict[str, str] = {}
    undeclared_units: List[str] = []
    has_explicit_units = any(
        isinstance(row.get("attributes"), Mapping)
        and isinstance(row.get("attributes", {}).get("garment_unit"), str)
        and bool(str(row.get("attributes", {}).get("garment_unit", "")).strip())
        for row in pieces)
    for index, piece in enumerate(pieces):
        identity = piece.get("piece_id", piece.get("name"))
        if not isinstance(identity, str) or not identity or identity in ids:
            return {
                "verdict": "UNKNOWN_PATTERN_PIECE_ID",
                "connected": False,
                "why": "piece ids must be unique non-empty strings",
                "piece_index": index,
            }
        ids.append(identity)
        attributes = piece.get("attributes", {})
        attributes = attributes if isinstance(attributes, Mapping) else {}
        unit = attributes.get(
            "garment_unit", "__UNDECLARED__" if has_explicit_units else "candidate")
        if not isinstance(unit, str) or not unit.strip():
            return {
                "verdict": "UNKNOWN_GARMENT_UNIT",
                "connected": False,
                "why": f"{identity}.attributes.garment_unit must be a string",
            }
        unit_of[identity] = unit.strip()
        if unit_of[identity] == "__UNDECLARED__":
            undeclared_units.append(identity)

    parent = {identity: identity for identity in ids}

    def find(identity: str) -> str:
        while parent[identity] != identity:
            parent[identity] = parent[parent[identity]]
            identity = parent[identity]
        return identity

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    relations: List[Dict[str, str]] = []
    for collection in ("seams", "layers"):
        rows = pattern.get(collection, [])
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            return {
                "verdict": "UNKNOWN_PATTERN_RELATIONS",
                "connected": False,
                "why": f"{collection} must be a sequence",
            }
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                return {
                    "verdict": "UNKNOWN_PATTERN_RELATION",
                    "connected": False,
                    "why": f"{collection}[{index}] must be an object",
                }
            endpoints: List[str] = []
            for side in ("a", "b"):
                ref = row.get(side)
                identity = ref.get("piece_id") if isinstance(ref, Mapping) else None
                if not isinstance(identity, str) or identity not in parent:
                    return {
                        "verdict": "UNKNOWN_PATTERN_RELATION_ADDRESS",
                        "connected": False,
                        "why": f"{collection}[{index}].{side} names no compiled piece",
                    }
                endpoints.append(identity)
            a, b = endpoints
            relations.append({"collection": collection, "a": a, "b": b,
                              "operation_id": str(row.get("operation_id", ""))})
            if a != b:
                union(a, b)

    components_by_root: Dict[str, List[str]] = {}
    for identity in ids:
        components_by_root.setdefault(find(identity), []).append(identity)
    components = [sorted(group) for group in components_by_root.values()]
    components.sort(key=lambda group: tuple(group))

    units: Dict[str, List[str]] = {}
    for identity in ids:
        units.setdefault(unit_of[identity], []).append(identity)
    disconnected: List[Dict[str, Any]] = []
    for unit, members in sorted(units.items()):
        roots = sorted({find(identity) for identity in members})
        if len(roots) > 1:
            disconnected.append({
                "garment_unit": unit,
                "pieces": sorted(members),
                "components": [sorted(components_by_root[root]) for root in roots],
            })

    connected = not disconnected and not undeclared_units
    if undeclared_units:
        verdict = "REVIEW_UNDECLARED_GARMENT_UNIT"
        why = ("some pieces omit garment_unit while other pieces explicitly "
               "declare separates; their assembly ownership is ambiguous")
    elif disconnected:
        verdict = "REVIEW_DISCONNECTED_PATTERN_ASSEMBLY"
        why = ("one or more garment units contain pieces with no compiled "
               "attachment path")
    else:
        verdict = "ANSWER"
        why = "every declared garment unit is connected by compiled seams or layers"
    return {
        "verdict": verdict,
        "connected": connected,
        "why": why,
        "components": components,
        "garment_units": {key: sorted(value) for key, value in sorted(units.items())},
        "disconnected_units": disconnected,
        "undeclared_unit_pieces": sorted(undeclared_units),
        "relations": relations,
        "self_closures_do_not_connect_components": True,
    }


def review(pattern: Mapping[str, Any], *,
           repair: Optional[Mapping[str, Any]] = None,
           manufacturing: Optional[Mapping[str, Any]] = None,
           sewing_plan: Optional[Mapping[str, Any]] = None,
           simulation: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(pattern, Mapping) or pattern.get("schema") != "garment.compiled-pattern.v1":
        return {"verdict": "UNKNOWN_COMPILED_PATTERN_REQUIRED", "schema": SCHEMA,
                "why": "engineering review requires garment.compiled-pattern.v1"}

    repair = repair if isinstance(repair, Mapping) else {}
    manufacturing = (manufacturing if isinstance(manufacturing, Mapping)
                     else pattern.get("manufacturing_preview", {}))
    manufacturing = manufacturing if isinstance(manufacturing, Mapping) else {}
    sewing_plan = (sewing_plan if isinstance(sewing_plan, Mapping)
                   else pattern.get("topology_sewing_plan", {}))
    sewing_plan = sewing_plan if isinstance(sewing_plan, Mapping) else {}
    simulation = simulation if isinstance(simulation, Mapping) else {}

    gates = []
    uncovered = pattern.get("uncompiled_visual_parts", [])
    coverage_ok = (pattern.get("representation_complete", True) is True
                   and isinstance(uncovered, Sequence)
                   and not isinstance(uncovered, (str, bytes))
                   and not uncovered)
    gates.append(_gate(
        "visual_representation_coverage", "PASS" if coverage_ok else
        "REVIEW_UNCOMPILED_VISUAL_PARTS",
        "all visual parts admitted by the candidate have deterministic geometry"
        if coverage_ok else
        "the selected candidate contains visible parts that were not compiled into geometry",
        uncompiled_visual_parts=(list(uncovered)
                                 if isinstance(uncovered, Sequence)
                                 and not isinstance(uncovered, (str, bytes)) else [])))

    connectivity = assembly_connectivity(pattern)
    connectivity_ok = connectivity.get("verdict") == "ANSWER"
    gates.append(_gate(
        "assembly_connectivity", "PASS" if connectivity_ok else
        str(connectivity.get("verdict", "REVIEW_DISCONNECTED_PATTERN_ASSEMBLY")),
        str(connectivity.get("why", "pattern assembly connectivity was not established")),
        components=connectivity.get("components", []),
        garment_units=connectivity.get("garment_units", {}),
        disconnected_units=connectivity.get("disconnected_units", [])))

    seam_checks = pattern.get("seam_checks", [])
    seam_ok = (bool(repair.get("sewable")) if repair else
               bool(seam_checks) and all(
                   row.get("geometrically_sewable", row.get("sewable")) is not False
                   for row in seam_checks if isinstance(row, Mapping)))
    gates.append(_gate(
        "geometric_sewability", "PASS" if seam_ok else "REVIEW_PATTERN_REPAIR_REQUIRED",
        "named edge pairs pass the current geometric checks" if seam_ok else
        "one or more geometric sewing checks remain unresolved",
        manufacturing_certified=False))

    order_ok = sewing_plan.get("order_verdict") == "ANSWER"
    gates.append(_gate(
        "construction_order", "PASS" if order_ok else
        str(sewing_plan.get("verdict", "REVIEW_CONSTRUCTION_ORDER_REQUIRED")),
        "topology has a deterministic dependency order" if order_ok else
        "construction dependencies are missing or invalid",
        unresolved_choices=sewing_plan.get("reviews", [])))

    preview_ok = (manufacturing.get("verdict") == "ANSWER"
                  and manufacturing.get("manufacturing_preview_ready") is True)
    production_ok = manufacturing.get("manufacturing_ready") is True
    gates.append(_gate(
        "cutting_artifact", "PASS" if production_ok else
        ("REVIEW_MANUFACTURING_GATES_REQUIRED" if preview_ok else
         str(manufacturing.get("verdict", "REVIEW_MANUFACTURING_PREVIEW_REQUIRED"))),
        "production gates are closed" if production_ok else
        "cut/sew lines may be inspectable, but remaining gates prevent production approval",
        preview_ready=preview_ok,
        remaining_gates=manufacturing.get("remaining_gates", [])))

    stages = simulation.get("stages", {}) if simulation.get("verdict") == "ANSWER" else {}
    stages = stages if isinstance(stages, Mapping) else {}
    xpbd = stages.get("xpbd", {})
    xpbd_ok = isinstance(xpbd, Mapping) and xpbd.get("verdict") == "ANSWER"
    gates.append(_gate(
        "cloth_numerics", "PASS" if xpbd_ok else "REVIEW_SIMULATION_REQUIRED",
        "typed XPBD reference step completed" if xpbd_ok else
        "no accepted cloth numerical result is bound to this candidate",
        diagnostics=xpbd.get("diagnostics") if xpbd_ok else None,
        industrial_completion=False))

    calibration = stages.get("material_calibration", {})
    calibrated = (isinstance(calibration, Mapping)
                  and calibration.get("verdict") == "ANSWER")
    gates.append(_gate(
        "material_and_strength", "PASS" if calibrated else
        "REVIEW_STRENGTH_CALIBRATION_REQUIRED",
        "material response is bound to measured calibration" if calibrated else
        "numerical strain without measured material/seam failure limits is not a strength guarantee",
        calibration_digest=(calibration.get("calibration_digest")
                            if isinstance(calibration, Mapping) else None)))

    contact = stages.get("ccd", {})
    contact_ok = isinstance(contact, Mapping) and contact.get("verdict") == "ANSWER"
    gates.append(_gate(
        "contact_and_seams", "PASS" if contact_ok else "REVIEW_CONTACT_REQUIRED",
        "typed contact/seam projection completed" if contact_ok else
        "contact or seam mechanics were skipped or not accepted",
        exact_symbolic_ccd=False,
        experimentally_calibrated_failure=False))

    comfort = stages.get("comfort", {})
    comfort_reviewed = isinstance(comfort, Mapping) and comfort.get("verdict") == "REVIEW"
    gates.append(_gate(
        "wearer_comfort", "REVIEW" if comfort_reviewed else
        "REVIEW_COMFORT_OBSERVATIONS_REQUIRED",
        "engineering comfort observations are available for human review" if comfort_reviewed else
        "wearer-specific pressure, motion and thermal observations are missing",
        medical_claim=False))

    approval = pattern.get("approval")
    approved = (pattern.get("candidate_state") == "APPROVED"
                and isinstance(approval, Mapping) and bool(approval.get("by")))
    gates.append(_gate(
        "front_only_authority", "REVIEW" if approved else "REVIEW_SHAPE_APPROVAL_REQUIRED",
        "a named person accepted this proposed back/structure" if approved else
        "the front image cannot observe the back; an exact candidate still needs approval",
        back_observed=False,
        proposal_remains_proposed=True))

    actionable = [row["gate"] for row in gates
                  if row["verdict"] not in {"PASS", "REVIEW"}]
    artifact = {
        "schema": SCHEMA,
        "candidate_id": pattern.get("candidate_id"),
        "pattern_digest": pattern.get("digest"),
        "structure_digest": pattern.get("structure_digest"),
        "gates": gates,
        "pass_count": sum(row["verdict"] == "PASS" for row in gates),
        "review_count": sum(row["verdict"] == "REVIEW" for row in gates),
        "actionable_gates": actionable,
        "loop_directive": "CONTINUE" if actionable else "HUMAN_REVIEW",
        "manufacturing_ready": all(row["verdict"] == "PASS" for row in gates),
        "industrial_or_medical_certification": False,
        "provenance": {
            "method": "deterministic cross-stage gate aggregation",
            "model_used": False,
            "corpus_used": False,
        },
    }
    artifact["digest"] = _digest(artifact)
    return {"verdict": REVIEW, **artifact}


evaluate = review
