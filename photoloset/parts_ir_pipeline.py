# -*- coding: utf-8 -*-
"""Proposal-only orchestration from image-model parts IR to 3D and patterns.

This module is intentionally an integration boundary, not another inference
engine.  It runs the existing deterministic stages in order::

    garment.parts-ir.v1
      -> parts_ir_completion
      -> parts_ir_topology
      -> structure_preview + structure_to_pattern
      -> pattern_manufacturing_bundle + structure_sewing_plan

Each completed candidate is isolated while topology is constructed.  This is
important because the topology API normally fails the whole batch at the first
invalid candidate.  Here a typed refusal remains attached to that candidate,
other candidates are still evaluated, and the aggregate result is
``UNRESOLVED`` whenever any candidate fails.  A successful 3D preview and flat
pattern are additionally bound to the same validated structure digest.

SVG/DXF text is represented compactly by digest and byte count while the
cut/sew lines, allowances and notches remain directly inspectable.  No output
from this module raises image-model proposals above ``PROPOSED`` and no
successful geometric computation is presented as manufacturing approval.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from . import garment_structure
from . import pattern_manufacturing_bundle
from . import parts_ir_completion
from . import parts_ir_topology
from . import structure_preview
from . import structure_sewing_plan
from . import structure_to_pattern


SCHEMA = "garment.parts-ir.pipeline.v1"
PROPOSED = "PROPOSED"
UNRESOLVED = "UNRESOLVED"

_ORNAMENT_ARTIFACT_SCHEMA = "garment.parts-ir.ornament-artifacts.v1"
_ORNAMENT_ACTIONS = {
    "JOIN": "join_ornament_edges",
    "FOLD_AND_TACK": "fold_and_tack_ornament",
    "WRAP": "wrap_ornament_piece",
    "FINISH_RAW_EDGES": "finish_ornament_raw_edges",
    "GATHER": "gather_ornament_piece",
    "FORM_SPIRAL_AND_TACK": "form_and_tack_rosette",
    "ATTACH_TO_GARMENT": "attach_ornament_to_garment",
}


class _OrnamentIntegrationRefusal(Exception):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _digest(value: Any) -> str:
    return garment_structure.semantic_digest(value)


def _failure(stage: str, result: Mapping[str, Any], *,
             fallback: str) -> Dict[str, Any]:
    code = result.get("verdict", fallback)
    if not isinstance(code, str) or not code.startswith("UNKNOWN_"):
        code = fallback
    return {
        "stage": stage,
        "code": code,
        "state": UNRESOLVED,
        "why": str(result.get("why", f"{stage} did not produce a usable result")),
        "how_to_close": str(result.get(
            "how_to_close", "revise the typed proposal and rerun this candidate")),
        "engine_result": copy.deepcopy(dict(result)),
    }


def _payload_record(payload: Any) -> Dict[str, Any]:
    """Describe an omitted export without returning its full text payload."""
    if not isinstance(payload, str):
        return {
            "included": False,
            "available": False,
            "digest": None,
            "utf8_bytes": 0,
        }
    return {
        "included": False,
        "available": True,
        "digest": _digest(payload),
        "utf8_bytes": len(payload.encode("utf-8")),
    }


def _normalised_side(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    side = value.strip().lower()
    aliases = {"l": "left", "r": "right", "both": "bilateral"}
    return aliases.get(side, side) if side else None


def _instance_lineage_record(source_node_id: str, side: str,
                             instance_id: str) -> Dict[str, str]:
    return {
        "key": (
            f"source_node_id={source_node_id}|side={side}|"
            f"instance_id={instance_id}"),
        "source_node_id": source_node_id,
        "side": side,
        "instance_id": instance_id,
    }


def _piece_instance_lineage(
        piece: Mapping[str, Any]) -> tuple[Optional[Dict[str, str]],
                                           Optional[Dict[str, Any]]]:
    """Read explicit piece lineage before any compact artifact is emitted."""
    attributes = piece.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    provenance = piece.get("provenance", {})
    provenance = provenance if isinstance(provenance, Mapping) else {}
    lineage = provenance.get("instance_lineage", {})
    lineage = lineage if isinstance(lineage, Mapping) else {}

    source_values = {
        str(value) for value in (
            piece.get("source_node_id"), attributes.get("source_node_id"),
            lineage.get("source_node_id"))
        if isinstance(value, str) and value
    }
    side_values = {
        str(value) for value in (
            _normalised_side(lineage.get("side")),
            _normalised_side(attributes.get("derived_side")))
        if value in {"left", "right"}
    }
    instance_values = {
        str(value) for value in (
            attributes.get("physical_instance"), piece.get("instance_id"))
        if isinstance(value, str) and value
    }
    if len(source_values) != 1 or len(side_values) != 1:
        return None, {
            "piece_id": piece.get("piece_id"),
            "reason": "piece lacks one unambiguous source_node_id and side",
            "source_node_ids": sorted(source_values),
            "sides": sorted(side_values),
        }
    source_node_id = next(iter(source_values))
    side = next(iter(side_values))
    canonical_instance = f"{source_node_id}:{side}"
    piece_id = piece.get("piece_id")
    if not instance_values and piece_id == canonical_instance:
        instance_values.add(canonical_instance)
    if len(instance_values) != 1 or canonical_instance not in instance_values:
        return None, {
            "piece_id": piece_id,
            "reason": "piece lacks its canonical physical instance address",
            "expected_instance_id": canonical_instance,
            "instance_ids": sorted(instance_values),
        }
    return _instance_lineage_record(
        source_node_id, side, canonical_instance), None


def _compact_manufacturing_preview(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep usable cutting geometry while omitting large SVG/DXF strings.

    ``result.digest`` still binds the complete manufacturing artifact produced
    by ``pattern_manufacturing_bundle.build``.  The compact digest separately
    binds exactly what this pipeline returns.
    """
    dxf = result.get("dxf_export", {})
    dxf = dxf if isinstance(dxf, Mapping) else {}
    pieces = []
    for raw in result.get("pieces", []):
        if not isinstance(raw, Mapping):
            continue
        compact_piece = {
            key: copy.deepcopy(raw[key])
            for key in (
                "piece_id", "name", "role", "primitive_kind", "layer",
                "source_node_id", "source_ornament_id",
                "cut_count", "sew_line", "cut_line", "boundary_layers",
                "seam_allowance_cm", "grain", "inner_cutouts", "area_cm2",
                "cut_area_cm2",
            )
            if key in raw
        }
        raw_attributes = raw.get("attributes", {})
        if isinstance(raw_attributes, Mapping):
            # Preserve only typed presentation semantics needed to keep a
            # candidate-specific 3D proxy from flattening left/right,
            # layering, and visible construction roles.  Measurements,
            # hidden construction and free-form model prose are deliberately
            # not copied into this compact UI boundary.
            presentation_attributes = {
                key: copy.deepcopy(raw_attributes[key])
                for key in (
                    "side", "derived_side", "physical_instance_side",
                    "detail_role", "construction_role", "placement", "shape",
                    "color", "hex_color",
                )
                if key in raw_attributes
            }
            if presentation_attributes:
                compact_piece["attributes"] = presentation_attributes
        instance, _ = _piece_instance_lineage(raw)
        if instance is not None:
            compact_piece["instance_lineage"] = instance
        pieces.append(compact_piece)
    compact: Dict[str, Any] = {
        "schema": result.get("schema"),
        "verdict": result.get("verdict"),
        "view": "COMPACT_CUTTING_PREVIEW",
        "compact": True,
        "candidate_id": result.get("candidate_id"),
        "candidate_state": result.get("candidate_state"),
        "structure_digest": result.get("structure_digest"),
        "source_pattern_digest": result.get("source_digest"),
        "full_artifact_digest": result.get("digest"),
        "pieces": pieces,
        "cut_manifest": copy.deepcopy(result.get("cut_manifest", [])),
        "layer_order": copy.deepcopy(result.get("layer_order", [])),
        "seam_allowance_cm": copy.deepcopy(
            result.get("seam_allowance_cm", {})),
        "notches": copy.deepcopy(result.get("notches", {})),
        "grain": copy.deepcopy(result.get("grain", [])),
        "inner_cut_manifest": copy.deepcopy(
            result.get("inner_cut_manifest", [])),
        "inner_cut_digest": result.get("inner_cut_digest"),
        "exports": {
            "svg": _payload_record(result.get("svg")),
            "dxf": {
                **_payload_record(dxf.get("text")),
                "verdict": dxf.get("verdict"),
                "compatible": bool(result.get("dxf_compatible")),
                "layers": copy.deepcopy(dxf.get("layers", {})),
                "inner_cut_digest": dxf.get("inner_cut_digest"),
            },
            "dxf_layer_records": {
                "included": False,
                "count": len(result.get("dxf_layer_records", [])),
                "digest": _digest(result.get("dxf_layer_records", [])),
            },
        },
        "manufacturing_preview_ready": bool(
            result.get("manufacturing_preview_ready")),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "remaining_gates": copy.deepcopy(result.get("remaining_gates", [])),
        "authority": {
            "highest_state": PROPOSED,
            "candidate_state": result.get("candidate_state"),
            "approved": False,
            "observed": False,
            "answer_is_geometry_only": True,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        },
        "provenance": {
            "method": "compact view of full pattern_manufacturing_bundle artifact",
            "full_artifact_digest_preserved": True,
            "svg_dxf_text_omitted": True,
            "source_provenance": copy.deepcopy(result.get("provenance")),
        },
    }
    if isinstance(result.get("ornament_artifacts"), Mapping):
        compact["ornament_artifacts"] = copy.deepcopy(
            result["ornament_artifacts"])
    compact["compact_digest"] = _digest(compact)
    return compact


def _ornament_refusal(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "state": UNRESOLVED,
        "why": why,
        "how_to_close": (
            "repair the candidate-bound ornament artifact or explicitly resolve "
            "its typed attachment port; do not infer an attachment from proximity"),
        **copy.deepcopy(detail),
    }


def _ornament_rows(value: Any, *, field: str) -> List[Dict[str, Any]]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or any(not isinstance(row, Mapping) for row in value)):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_ARTIFACTS",
            f"ornament_artifacts.{field} must be an array of objects",
            field=field)
    return [copy.deepcopy(dict(row)) for row in value]


def _ornament_grain(piece: Mapping[str, Any]) -> Dict[str, Any]:
    raw = piece.get("grainline")
    if not isinstance(raw, Mapping) or raw.get("state") != PROPOSED:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_GRAIN",
            "an ornament pattern piece needs its proposal-only grainline",
            piece_id=piece.get("piece_id"))
    direction = str(raw.get("direction", "")).upper()
    angles = {
        "LENGTHWISE": 90.0,
        "CROSSWISE": 0.0,
        "BIAS_45": 45.0,
        "BIAS_-45": -45.0,
        "NO_GRAIN": 0.0,
    }
    if direction not in angles:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_GRAIN",
            "an ornament grainline uses an unsupported direction",
            piece_id=piece.get("piece_id"), direction=direction)
    return {
        "direction": direction,
        "angle_deg": angles[direction],
        "state": PROPOSED,
        "basis": "candidate-bound ornament primitive grain proposal",
        "breaks_when": "material, layout, bias behaviour, or construction review changes",
        "manufacturing_confirmed": False,
    }


def _ornament_edge_table(piece: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _ornament_rows(piece.get("edges"), field="pattern_pieces.edges")
    edges: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        address = row.get("address")
        points = row.get("points")
        length = row.get("length_cm")
        if (not isinstance(address, str) or not address
                or address in edges
                or not isinstance(points, Sequence)
                or isinstance(points, (str, bytes))
                or isinstance(length, bool)
                or not isinstance(length, (int, float))
                or not math.isfinite(float(length)) or float(length) <= 0.0):
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_EDGE",
                "ornament edge addresses and lengths must be finite and unique",
                piece_id=piece.get("piece_id"), edge=row)
        edges[address] = {
            "points": copy.deepcopy(list(points)),
            "length": float(length),
            "state": PROPOSED,
        }
    return edges


def _ornament_piece_lineage(
        bundle: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    by_piece: Dict[str, Dict[str, str]] = {}
    for result in _ornament_rows(bundle.get("results"), field="results"):
        kind = result.get("kind")
        ornament_id = result.get("ornament_id")
        if not isinstance(kind, str) or not kind:
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_KIND",
                "every materialized ornament result needs a kind")
        if not isinstance(ornament_id, str) or not ornament_id:
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_ID",
                "every materialized ornament result needs an ornament_id")
        for piece in _ornament_rows(
                result.get("pattern_pieces"), field="results.pattern_pieces"):
            piece_id = piece.get("piece_id")
            if (not isinstance(piece_id, str) or not piece_id
                    or piece_id in by_piece):
                raise _OrnamentIntegrationRefusal(
                    "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PIECE_ID",
                    "ornament result piece ids must be non-empty and unique",
                    piece_id=piece_id)
            by_piece[piece_id] = {
                "kind": kind.upper(),
                "ornament_id": ornament_id,
            }
    return by_piece


def _ornament_piece_kinds(bundle: Mapping[str, Any]) -> Dict[str, str]:
    return {
        piece_id: lineage["kind"]
        for piece_id, lineage in _ornament_piece_lineage(bundle).items()
    }


def _compiled_ornament_piece(piece: Mapping[str, Any], *, kind: str,
                              source_ornament_id: str,
                              topology_digest: str,
                              candidate_id: str) -> Dict[str, Any]:
    piece_id = piece.get("piece_id")
    if not isinstance(piece_id, str) or not piece_id:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PIECE_ID",
            "an ornament pattern piece needs a non-empty piece_id")
    if (piece.get("state") != PROPOSED
            or piece.get("proposal_only") is not True
            or not isinstance(piece.get("geometry_authority"), Mapping)
            or piece["geometry_authority"].get("state") != PROPOSED
            or piece["geometry_authority"].get("observed") is not False):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_AUTHORITY_ESCALATION",
            "ornament pattern pieces must remain proposal-only",
            piece_id=piece_id)
    outline = piece.get("sew_line", piece.get("outline"))
    if (not isinstance(outline, Sequence) or isinstance(outline, (str, bytes))
            or len(outline) < 3):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_OUTLINE",
            "an ornament pattern piece needs a materialized sewing polygon",
            piece_id=piece_id)
    allowance = piece.get("seam_allowance_cm")
    if (isinstance(allowance, bool) or not isinstance(allowance, (int, float))
            or not math.isfinite(float(allowance)) or float(allowance) <= 0.0):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_ALLOWANCE",
            "an ornament cut boundary needs a finite positive proposed allowance",
            piece_id=piece_id)
    cut_count = piece.get("cut_quantity")
    if (isinstance(cut_count, bool) or not isinstance(cut_count, int)
            or cut_count <= 0):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_CUT_COUNT",
            "an ornament piece needs an explicit positive cut quantity",
            piece_id=piece_id)
    area = piece.get("sew_area_cm2")
    if (isinstance(area, bool) or not isinstance(area, (int, float))
            or not math.isfinite(float(area)) or float(area) <= 0.0):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_AREA",
            "an ornament sewing polygon needs a finite positive area",
            piece_id=piece_id)
    return {
        "piece_id": piece_id,
        "name": piece_id,
        "node_id": piece_id,
        "source_ornament_id": source_ornament_id,
        "primitive_kind": kind,
        "layer": int(piece.get("layer", 0)),
        "role": piece.get("role", "ornament"),
        "outline": copy.deepcopy(list(outline)),
        "sew_line": copy.deepcopy(list(outline)),
        "cut_line": copy.deepcopy(piece.get("cut_line")),
        "boundary_layers": copy.deepcopy(piece.get("boundary_layers", {})),
        "edges": _ornament_edge_table(piece),
        "area_cm2": float(area),
        "cut_count": cut_count,
        "grain": _ornament_grain(piece),
        "grainline": copy.deepcopy(piece.get("grainline")),
        "seam_allowance_cm": {
            "value_cm": float(allowance),
            "state": PROPOSED,
            "basis": "candidate-bound ornament primitive proposal",
            "assumption_breaks_when": (
                "material, stitch, reinforcement, edge finish, or factory process changes"),
        },
        "transforms": [],
        "attributes": {
            "state": PROPOSED,
            "proposal_only": True,
            "candidate_id": candidate_id,
            "source_ornament_id": source_ornament_id,
            "ornament_kind": kind,
            "ornament_topology_digest": topology_digest,
            "not_observed_from_image": True,
            "manufacturing_validated": False,
        },
        "ornament_artifact": copy.deepcopy(dict(piece)),
        "provenance": {
            "method": "candidate-bound ornament artifact adapter",
            "source_piece_id": piece_id,
            "ornament_topology_digest": topology_digest,
            "geometry_changed": False,
            "attachment_target_inferred": False,
            "corpus_used": False,
        },
    }


def _integrate_ornament_pattern(pattern: Mapping[str, Any],
                                structure: Mapping[str, Any], *,
                                candidate_id: str) -> Dict[str, Any]:
    """Append materialized ornament pieces without selecting new targets."""
    raw = structure.get("ornament_artifacts")
    if raw is None:
        return copy.deepcopy(dict(pattern))
    if not isinstance(raw, Mapping) or raw.get("schema") != _ORNAMENT_ARTIFACT_SCHEMA:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_SCHEMA",
            f"expected {_ORNAMENT_ARTIFACT_SCHEMA}")
    bundle = copy.deepcopy(dict(raw))
    structure_digest = structure.get("structure_digest")
    topology_digest = bundle.get("topology_digest")
    if (bundle.get("state") != PROPOSED
            or bundle.get("candidate_id") != candidate_id
            or bundle.get("topology_structure_digest") != structure_digest
            or not isinstance(topology_digest, str) or not topology_digest):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_BINDING",
            "ornament artifacts are not bound to this candidate topology",
            candidate_id=candidate_id,
            artifact_candidate_id=bundle.get("candidate_id"),
            structure_digest=structure_digest,
            artifact_structure_digest=bundle.get("topology_structure_digest"))
    digest_payload = copy.deepcopy(bundle)
    digest_payload.pop("topology_digest", None)
    if _digest(digest_payload) != topology_digest:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_DIGEST",
            "ornament topology digest does not match its pieces, ports and intents")
    expected_candidate_artifact_digest = _digest({
        "structure_digest": structure_digest,
        "ornament_topology_digest": topology_digest,
    })
    if structure.get("candidate_artifact_digest") != expected_candidate_artifact_digest:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_CANDIDATE_DIGEST",
            "candidate artifact digest does not bind this topology and ornament bundle",
            expected=expected_candidate_artifact_digest,
            actual=structure.get("candidate_artifact_digest"))
    authority = bundle.get("authority")
    if (not isinstance(authority, Mapping)
            or authority.get("highest_state") != PROPOSED
            or authority.get("observed") is not False
            or authority.get("approved") is not False):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_AUTHORITY_ESCALATION",
            "ornament topology attempted to exceed PROPOSED authority")

    pieces = _ornament_rows(bundle.get("pattern_pieces"), field="pattern_pieces")
    ports = _ornament_rows(bundle.get("attachment_ports"), field="attachment_ports")
    intents = _ornament_rows(bundle.get("seam_intents"), field="seam_intents")
    piece_lineage = _ornament_piece_lineage(bundle)
    piece_kinds = {
        piece_id: lineage["kind"]
        for piece_id, lineage in piece_lineage.items()
    }
    piece_ids = [piece.get("piece_id") for piece in pieces]
    port_ids = [port.get("port_id") for port in ports]
    intent_ids = [intent.get("intent_id") for intent in intents]
    for field, identifiers in (("piece", piece_ids), ("port", port_ids),
                               ("intent", intent_ids)):
        if (any(not isinstance(identity, str) or not identity
                for identity in identifiers)
                or len(identifiers) != len(set(identifiers))):
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_ARTIFACT_ID",
                f"ornament {field} ids must be non-empty and unique",
                field=field, identifiers=identifiers)
    if set(piece_ids) != set(piece_kinds):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_RESULT_BINDING",
            "materialized ornament pieces do not match result lineage",
            artifact_piece_ids=sorted(piece_ids),
            result_piece_ids=sorted(piece_kinds))
    owner_ids = {port.get("owner_piece_id") for port in ports}
    if not owner_ids <= set(piece_ids):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PORT_OWNER",
            "an ornament attachment port does not resolve to an ornament piece",
            unknown_owner_ids=sorted(str(value) for value in owner_ids - set(piece_ids)))
    if any(port.get("state") != PROPOSED or port.get("observed") is not False
           for port in ports):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_AUTHORITY_ESCALATION",
            "ornament attachment ports must remain proposal-only")
    if any(intent.get("state") != PROPOSED for intent in intents):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_AUTHORITY_ESCALATION",
            "ornament seam intents must remain proposal-only")

    result = copy.deepcopy(dict(pattern))
    base_pattern_digest = result.get("digest")
    base_pieces = result.get("pieces")
    if not isinstance(base_pieces, list):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PATTERN",
            "compiled pattern has no mutable piece array")
    base_ids = {piece.get("piece_id") for piece in base_pieces
                if isinstance(piece, Mapping)}
    collisions = sorted(set(piece_ids) & base_ids)
    if collisions:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PIECE_COLLISION",
            "ornament piece ids collide with compiled structural pieces",
            piece_ids=collisions)
    compiled = [
        _compiled_ornament_piece(
            piece, kind=piece_kinds[str(piece["piece_id"])],
            source_ornament_id=piece_lineage[str(piece["piece_id"])][
                "ornament_id"],
            topology_digest=topology_digest, candidate_id=candidate_id)
        for piece in sorted(pieces, key=lambda item: str(item["piece_id"]))
    ]
    result["pieces"].extend(compiled)
    result["pieces"] = sorted(
        result["pieces"], key=lambda item: str(item.get("piece_id", "")))
    result["total_area_cm2"] = round(sum(
        float(piece.get("net_area_cm2", piece["area_cm2"]))
        * int(piece.get("cut_count", 1)) for piece in result["pieces"]), 6)

    binding = bundle.get("topology_binding")
    binding = copy.deepcopy(dict(binding)) if isinstance(binding, Mapping) else {}
    unresolved = copy.deepcopy(binding.get("unresolved", []))
    unresolved_target_ports = [
        copy.deepcopy(port.get("topology_binding"))
        for port in ports
        if isinstance(port.get("topology_binding"), Mapping)
        and port["topology_binding"].get("target_port_resolved") is False
    ]
    readiness = "REVIEW" if (
        bundle.get("readiness") == "REVIEW" or unresolved
        or unresolved_target_ports) else "PROPOSED"
    candidate_digest = _digest({
        "candidate_id": candidate_id,
        "structure_digest": structure_digest,
        "ornament_topology_digest": topology_digest,
    })
    integrated_artifacts = {
        "schema": "garment.compiled-pattern.ornament-artifacts.v1",
        "state": PROPOSED,
        "readiness": readiness,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "source_structure_digest": bundle.get("source_structure_digest"),
        "topology_structure_digest": structure_digest,
        "ornament_topology_digest": topology_digest,
        "base_pattern_digest": base_pattern_digest,
        "pattern_piece_ids": sorted(str(value) for value in piece_ids),
        "pattern_pieces": copy.deepcopy(compiled),
        "attachment_ports": ports,
        "seam_intents": intents,
        "construction_order": copy.deepcopy(bundle.get("construction_order", [])),
        "topology_binding": binding,
        "reviews": {
            "unresolved_attachments": unresolved,
            "unresolved_target_ports": unresolved_target_ports,
        },
        "authority": {
            "highest_state": PROPOSED,
            "observed": False,
            "approved": False,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        },
        "provenance": {
            "method": "candidate-bound ornament-to-compiled-pattern adapter",
            "geometry_changed": False,
            "attachment_target_inferred": False,
            "name_or_proximity_matching_used": False,
            "source_ornament_provenance": copy.deepcopy(bundle.get("provenance")),
        },
    }
    integrated_artifacts["digest"] = _digest(integrated_artifacts)
    result["ornament_artifacts"] = integrated_artifacts
    result["candidate_digest"] = candidate_digest
    result.setdefault("candidate_specific_expansions", []).append({
        "kind": "ORNAMENT_ARTIFACT_INTEGRATION",
        "state": PROPOSED,
        "candidate_id": candidate_id,
        "piece_ids": sorted(str(value) for value in piece_ids),
        "ornament_topology_digest": topology_digest,
        "attachment_target_inferred": False,
        "manufacturing_ready": False,
    })
    gates = list(result.get("remaining_gates", []))
    gates.append("approve ornament stitch, material, reinforcement and finishing choices")
    if unresolved:
        gates.append("resolve every ornament-to-garment attachment target")
    if unresolved_target_ports:
        gates.append("map every proposed ornament attachment to an exact flat-pattern port")
    result["remaining_gates"] = list(dict.fromkeys(gates))
    provenance = copy.deepcopy(dict(result.get("provenance", {})))
    provenance.update({
        "ornament_artifacts_integrated": True,
        "ornament_source_topology_digest": topology_digest,
        "ornament_attachment_target_inferred": False,
        "base_pattern_digest": base_pattern_digest,
    })
    result["provenance"] = provenance
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result.pop("digest", None)
    result["digest"] = _digest(result)
    return result


def _ornament_preview_outline(piece: Mapping[str, Any]) -> List[List[float]]:
    raw = piece.get("sew_line", piece.get("outline"))
    if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
            or len(raw) < 3):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_OUTLINE",
            "an ornament preview proxy needs a polygon with at least three points",
            piece_id=piece.get("piece_id"))
    points: List[List[float]] = []
    for point in raw:
        if (not isinstance(point, Sequence)
                or isinstance(point, (str, bytes)) or len(point) != 2
                or any(isinstance(value, bool)
                       or not isinstance(value, (int, float))
                       or not math.isfinite(float(value)) for value in point)):
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_OUTLINE",
                "ornament preview coordinates must be finite [x,y] pairs",
                piece_id=piece.get("piece_id"))
        points.append([float(point[0]), float(point[1])])
    twice_area = sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points)))
    if abs(twice_area) <= 1.0e-9:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_OUTLINE",
            "ornament preview polygon must have non-zero area",
            piece_id=piece.get("piece_id"))
    return points


def _integrate_ornament_preview(preview: Mapping[str, Any],
                                structure: Mapping[str, Any], *,
                                candidate_id: str,
                                layer_spacing_cm: float) -> Dict[str, Any]:
    """Bind every ornament cut piece to a labelled 3D construction proxy.

    The proxy is deliberately not a claim about the ornament's formed shape.
    It is a scaled planar copy of the deterministic sewing polygon, placed at
    the explicitly proposed target node when available.  This keeps rich image
    parts visible and candidate-bound without pretending that a flat bow strip
    or rosette strip already solves folding, gathering, or tacking mechanics.
    """
    raw = structure.get("ornament_artifacts")
    if raw is None:
        return copy.deepcopy(dict(preview))
    if (not isinstance(raw, Mapping)
            or raw.get("schema") != _ORNAMENT_ARTIFACT_SCHEMA):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_SCHEMA",
            f"expected {_ORNAMENT_ARTIFACT_SCHEMA}")
    if (preview.get("verdict") != structure_preview.ANSWER
            or preview.get("candidate_id") != candidate_id
            or preview.get("structure_digest")
            != structure.get("structure_digest")):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_BINDING",
            "the base preview must be an ANSWER bound to this candidate structure",
            candidate_id=candidate_id,
            preview_candidate_id=preview.get("candidate_id"),
            preview_structure_digest=preview.get("structure_digest"),
            structure_digest=structure.get("structure_digest"))

    bundle = copy.deepcopy(dict(raw))
    pieces = _ornament_rows(bundle.get("pattern_pieces"),
                            field="pattern_pieces")
    ports = _ornament_rows(bundle.get("attachment_ports"),
                           field="attachment_ports")
    lineage = _ornament_piece_lineage(bundle)
    piece_ids = {str(piece.get("piece_id")) for piece in pieces}
    if piece_ids != set(lineage):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_RESULT_BINDING",
            "ornament preview pieces do not match result lineage",
            artifact_piece_ids=sorted(piece_ids),
            result_piece_ids=sorted(lineage))

    target_by_ornament: Dict[str, Optional[str]] = {
        value["ornament_id"]: None for value in lineage.values()
    }
    target_records: Dict[str, List[Dict[str, Any]]] = {
        ornament_id: [] for ornament_id in target_by_ornament
    }
    for port in ports:
        owner_piece_id = port.get("owner_piece_id")
        if owner_piece_id not in lineage:
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PORT_OWNER",
                "ornament preview attachment port has no source ornament",
                owner_piece_id=owner_piece_id)
        ornament_id = lineage[str(owner_piece_id)]["ornament_id"]
        binding = port.get("topology_binding", {})
        binding = binding if isinstance(binding, Mapping) else {}
        target_node_id = binding.get("target_node_id")
        resolved = (binding.get("target_node_resolved") is True
                    and isinstance(target_node_id, str)
                    and bool(target_node_id))
        target_records[ornament_id].append({
            "port_id": port.get("port_id"),
            "target_node_id": target_node_id if resolved else None,
            "target_node_resolved": resolved,
            "target_port_resolved": binding.get("target_port_resolved") is True,
            "state": PROPOSED,
        })
        if resolved:
            prior = target_by_ornament[ornament_id]
            if prior is not None and prior != target_node_id:
                raise _OrnamentIntegrationRefusal(
                    "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_TARGET_AMBIGUOUS",
                    "one ornament cannot be placed on multiple target nodes",
                    ornament_id=ornament_id,
                    target_node_ids=sorted({prior, str(target_node_id)}))
            target_by_ornament[ornament_id] = str(target_node_id)

    result = copy.deepcopy(dict(preview))
    mesh = result.get("mesh")
    if not isinstance(mesh, dict):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_MESH",
            "base preview has no mutable mesh")
    vertices = mesh.get("vertices")
    faces = mesh.get("faces")
    vertex_layers = mesh.get("vertex_layers")
    face_layers = mesh.get("face_layers")
    face_node_ids = mesh.get("face_node_ids")
    face_piece_ids = mesh.get("face_piece_ids")
    preview_parts = result.get("parts")
    if not all(isinstance(value, list) for value in (
            vertices, faces, vertex_layers, face_layers,
            face_node_ids, face_piece_ids, preview_parts)):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_MESH",
            "base preview mesh arrays and parts must be mutable arrays")

    def bounds_for_target(target_node_id: Optional[str]) -> List[float]:
        target_part = next((
            part for part in preview_parts
            if isinstance(part, Mapping)
            and part.get("source_node_id") == target_node_id
        ), None)
        indices: List[int] = []
        if isinstance(target_part, Mapping):
            raw_range = target_part.get("vertex_range")
            if (isinstance(raw_range, Sequence)
                    and not isinstance(raw_range, (str, bytes))
                    and len(raw_range) == 2):
                indices = list(range(int(raw_range[0]), int(raw_range[1])))
        if not indices:
            indices = list(range(len(vertices)))
        selected = [vertices[index] for index in indices]
        return [
            min(float(point[0]) for point in selected),
            max(float(point[0]) for point in selected),
            min(float(point[1]) for point in selected),
            max(float(point[1]) for point in selected),
            max(float(point[2]) for point in selected),
        ]

    ornament_ids = sorted(target_by_ornament)
    slot_by_ornament = {
        ornament_id: index - (len(ornament_ids) - 1) / 2.0
        for index, ornament_id in enumerate(ornament_ids)
    }
    proxy_records: List[Dict[str, Any]] = []
    for piece in sorted(pieces, key=lambda value: str(value.get("piece_id", ""))):
        piece_id = str(piece["piece_id"])
        source = lineage[piece_id]
        ornament_id = source["ornament_id"]
        target_node_id = target_by_ornament[ornament_id]
        min_x, max_x, min_y, max_y, front_z = bounds_for_target(target_node_id)
        target_width = max(max_x - min_x, 1.0)
        target_height = max(max_y - min_y, 1.0)
        outline = _ornament_preview_outline(piece)
        source_min_x = min(point[0] for point in outline)
        source_max_x = max(point[0] for point in outline)
        source_min_y = min(point[1] for point in outline)
        source_max_y = max(point[1] for point in outline)
        source_width = max(source_max_x - source_min_x, 1.0e-9)
        source_height = max(source_max_y - source_min_y, 1.0e-9)
        width_budget = max(2.0, target_width / max(len(ornament_ids), 2) * 0.8)
        height_budget = max(2.0, target_height * 0.42)
        preview_scale = min(1.0, width_budget / source_width,
                            height_budget / source_height)
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        slot_offset = slot_by_ornament[ornament_id] * min(
            max(target_width / max(len(ornament_ids), 2), 1.0), 8.0)
        source_center_x = (source_min_x + source_max_x) / 2.0
        source_center_y = (source_min_y + source_max_y) / 2.0
        layer = int(piece.get("layer", 0))
        z = front_z + max(0.05, float(layer_spacing_cm) * 0.2) * (layer + 1)
        first_vertex = len(vertices)
        for x, y in outline:
            vertices.append([
                round(center_x + slot_offset
                      + (x - source_center_x) * preview_scale, 9),
                round(center_y - (y - source_center_y) * preview_scale, 9),
                round(z, 9),
            ])
            vertex_layers.append(layer)
        first_face = len(faces)
        for index in range(1, len(outline) - 1):
            faces.append([first_vertex, first_vertex + index + 1,
                          first_vertex + index])
            face_layers.append(layer)
            face_node_ids.append(ornament_id)
            face_piece_ids.append(piece_id)
        preview_parts.append({
            "node_id": piece_id,
            "piece_id": piece_id,
            "kind": source["kind"],
            "source_ornament_id": ornament_id,
            "target_node_id": target_node_id,
            "layer": layer,
            "vertex_range": [first_vertex, len(vertices)],
            "face_range": [first_face, len(faces)],
            "face_indices": list(range(first_face, len(faces))),
            "geometry_role": "ORNAMENT_CONSTRUCTION_PROXY",
            "construction_proxy": True,
            "formed_geometry_claimed": False,
            "source_outline_cm": copy.deepcopy(outline),
            "preview_scale": round(preview_scale, 9),
            "state": PROPOSED,
        })
        proxy_records.append({
            "piece_id": piece_id,
            "source_ornament_id": ornament_id,
            "target_node_id": target_node_id,
            "target_node_resolved": target_node_id is not None,
            "preview_scale": round(preview_scale, 9),
            "state": PROPOSED,
        })

    topology = structure_preview._topology(  # type: ignore[attr-defined]
        [tuple(float(value) for value in point) for point in vertices],
        [tuple(int(value) for value in face) for face in faces])
    if topology["degenerate_face_indices"] or topology["nonmanifold_edges"]:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_PREVIEW_TOPOLOGY",
            "ornament construction proxies made the preview topology invalid",
            topology=topology)
    result["topology"] = topology
    layer_rows = []
    for layer in sorted(set(vertex_layers) | set(face_layers)):
        layer_rows.append({
            "layer": layer,
            "node_ids": [
                part["node_id"] for part in preview_parts
                if isinstance(part, Mapping) and part.get("layer") == layer
            ],
            "vertex_indices": [
                index for index, value in enumerate(vertex_layers)
                if value == layer
            ],
            "face_indices": [
                index for index, value in enumerate(face_layers)
                if value == layer
            ],
        })
    result["layers"] = layer_rows
    relations = list(result.get("layer_relations", []))
    relations.extend({
        "operation_id": f"preview-proxy-{record['piece_id']}",
        "source_node_id": record["source_ornament_id"],
        "source_piece_id": record["piece_id"],
        "source_layer": next(
            part["layer"] for part in preview_parts
            if part.get("piece_id") == record["piece_id"]),
        "target_node_id": record["target_node_id"],
        "target_layer": next((
            part["layer"] for part in preview_parts
            if part.get("source_node_id") == record["target_node_id"]
        ), None),
        "kind": "ORNAMENT_CONSTRUCTION_PROXY",
        "state": PROPOSED,
    } for record in proxy_records)
    result["layer_relations"] = relations
    result["ornament_artifacts"] = {
        "schema": "garment.parts-ir.ornament-preview.v1",
        "state": PROPOSED,
        "candidate_id": candidate_id,
        "source_structure_digest": structure.get("structure_digest"),
        "ornament_topology_digest": bundle.get("topology_digest"),
        "pattern_piece_ids": sorted(piece_ids),
        "preview_piece_ids": sorted(record["piece_id"]
                                    for record in proxy_records),
        "all_pattern_pieces_bound_to_preview": (
            sorted(piece_ids)
            == sorted(record["piece_id"] for record in proxy_records)),
        "all_attachment_targets_resolved": all(
            record["target_node_resolved"] for record in proxy_records),
        "formed_geometry_claimed": False,
        "geometry_role": "ORNAMENT_CONSTRUCTION_PROXY",
        "target_bindings": copy.deepcopy(target_records),
        "proxies": proxy_records,
        "authority": {
            "highest_state": PROPOSED,
            "observed": False,
            "approved": False,
            "manufacturing_ready": False,
        },
    }
    claims = copy.deepcopy(dict(result.get("claims", {})))
    claims.update({
        "ornament_construction_proxy": True,
        "formed_ornament_geometry": False,
        "ornament_attachment_validated": result["ornament_artifacts"][
            "all_attachment_targets_resolved"],
    })
    result["claims"] = claims
    provenance = copy.deepcopy(dict(result.get("provenance", {})))
    provenance.update({
        "ornament_pattern_pieces_preserved": True,
        "ornament_preview_method": (
            "scaled planar construction proxies on explicitly proposed target nodes"),
        "formed_ornament_shape_inferred": False,
    })
    result["provenance"] = provenance
    result.pop("preview_digest", None)
    result["preview_digest"] = _digest({
        "candidate_id": candidate_id,
        "structure_digest": result["structure_digest"],
        "mesh": mesh,
        "parts": preview_parts,
        "layers": layer_rows,
        "layer_relations": relations,
        "ornament_artifacts": result["ornament_artifacts"],
        "geometry_operations": result.get("geometry_operations", []),
        "construction_boundaries": result.get("construction_boundaries", []),
        "pattern_conformance": result.get("pattern_conformance", []),
    })
    return result


def _sleeve_sides(node: Mapping[str, Any]) -> tuple[str, ...]:
    attributes = node.get("attributes", {})
    attributes = attributes if isinstance(attributes, Mapping) else {}
    side = _normalised_side(attributes.get("side"))
    quantity = attributes.get("quantity")
    if side == "bilateral" or quantity == 2:
        return ("left", "right")
    if side in {"left", "right"}:
        return (str(side),)
    return ()


def _relation_lineage_record(operation_id: str, kind: str, side: str,
                             source_node_id: str, target_node_id: str,
                             source_instance_id: str,
                             target_instance_id: str) -> Dict[str, str]:
    return {
        "key": (
            f"operation_id={operation_id}|kind={kind}|side={side}|"
            f"source={source_instance_id}|target={target_instance_id}"),
        "operation_id": operation_id,
        "kind": kind,
        "side": side,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "source_instance_id": source_instance_id,
        "target_instance_id": target_instance_id,
    }


def _expected_sleeve_lineage(
        structure: Mapping[str, Any]) -> Dict[str, Any]:
    nodes = {
        str(row["node_id"]): row
        for row in structure.get("nodes", [])
        if (isinstance(row, Mapping)
            and isinstance(row.get("node_id"), str)
            and str(row.get("kind", "")).upper() == "SLEEVE")
    }
    sides_by_node = {
        node_id: _sleeve_sides(node) for node_id, node in nodes.items()
    }
    instances = [
        _instance_lineage_record(node_id, side, f"{node_id}:{side}")
        for node_id in sorted(nodes)
        for side in sides_by_node[node_id]
    ]
    relations: List[Dict[str, str]] = []
    for operation in structure.get("operations", []):
        if not isinstance(operation, Mapping):
            continue
        kind = str(operation.get("kind", "")).upper()
        source = operation.get("source", {})
        target = operation.get("target", {})
        if (kind not in {"JOIN", "LAYER"}
                or not isinstance(source, Mapping)
                or not isinstance(target, Mapping)):
            continue
        source_id = source.get("node_id")
        target_id = target.get("node_id")
        operation_id = operation.get("operation_id")
        if (source_id not in nodes or target_id not in nodes
                or not isinstance(operation_id, str) or not operation_id):
            continue
        source_sides = sides_by_node[str(source_id)]
        target_sides = set(sides_by_node[str(target_id)])
        for side in source_sides:
            if side not in target_sides:
                continue
            relations.append(_relation_lineage_record(
                operation_id, kind, side, str(source_id), str(target_id),
                f"{source_id}:{side}", f"{target_id}:{side}"))
    instances.sort(key=lambda row: row["key"])
    relations.sort(key=lambda row: row["key"])
    return {
        "required": bool(instances),
        "required_source_node_ids": sorted({
            row["source_node_id"] for row in instances}),
        "instances": instances,
        "relations": relations,
    }


def _pattern_relation_lineage(
        pattern: Mapping[str, Any]) -> tuple[List[Dict[str, str]],
                                             Dict[str, Dict[str, str]],
                                             List[Dict[str, Any]]]:
    records: List[Dict[str, str]] = []
    by_compiled_operation: Dict[str, Dict[str, str]] = {}
    errors: List[Dict[str, Any]] = []
    for field in ("seams", "layers"):
        for row in pattern.get(field, []):
            if not isinstance(row, Mapping):
                continue
            lineage = row.get("pattern_lineage")
            if not isinstance(lineage, Mapping):
                continue
            source = lineage.get("source", {})
            target = lineage.get("target", {})
            values = {
                "operation_id": lineage.get("source_operation_id"),
                "kind": lineage.get("relation_kind"),
                "side": _normalised_side(lineage.get("side")),
                "source_node_id": (
                    source.get("node_id") if isinstance(source, Mapping)
                    else None),
                "target_node_id": (
                    target.get("node_id") if isinstance(target, Mapping)
                    else None),
                "source_piece_id": (
                    source.get("piece_id") if isinstance(source, Mapping)
                    else None),
                "target_piece_id": (
                    target.get("piece_id") if isinstance(target, Mapping)
                    else None),
            }
            if (not all(isinstance(values[name], str) and values[name]
                        for name in values)
                    or values["kind"] not in {"JOIN", "LAYER"}
                    or values["side"] not in {"left", "right"}):
                errors.append({
                    "compiled_operation_id": row.get("operation_id"),
                    "reason": "typed sleeve relation lineage is incomplete",
                    "lineage": copy.deepcopy(dict(lineage)),
                })
                continue
            record = _relation_lineage_record(
                str(values["operation_id"]), str(values["kind"]),
                str(values["side"]), str(values["source_node_id"]),
                str(values["target_node_id"]),
                str(values["source_piece_id"]),
                str(values["target_piece_id"]))
            compiled_operation = row.get("operation_id")
            if not isinstance(compiled_operation, str) or not compiled_operation:
                errors.append({
                    "reason": "typed sleeve relation lacks compiled operation_id",
                    "lineage": copy.deepcopy(dict(lineage)),
                })
                continue
            records.append(record)
            by_compiled_operation[compiled_operation] = record
    records.sort(key=lambda row: row["key"])
    return records, by_compiled_operation, errors


def _annotate_sewing_instance_lineage(
        sewing: Mapping[str, Any], pattern: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(sewing))
    piece_lineage: Dict[str, Dict[str, str]] = {}
    for piece in pattern.get("pieces", []):
        if (not isinstance(piece, Mapping)
                or str(piece.get("primitive_kind", "")).upper() != "SLEEVE"):
            continue
        record, _ = _piece_instance_lineage(piece)
        piece_id = piece.get("piece_id")
        if record is not None and isinstance(piece_id, str):
            piece_lineage[piece_id] = record
    _, relation_by_operation, _ = _pattern_relation_lineage(
        pattern)
    all_instances: Dict[str, Dict[str, str]] = {}
    covered_relations: Dict[str, Dict[str, str]] = {}
    steps = result.get("steps", [])
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            records = {
                piece_lineage[piece_id]["key"]: piece_lineage[piece_id]
                for piece_id in step.get("pieces", [])
                if isinstance(piece_id, str) and piece_id in piece_lineage
            }
            if records:
                step["instance_lineage"] = [
                    copy.deepcopy(records[key]) for key in sorted(records)]
                all_instances.update(records)
            relation = relation_by_operation.get(str(step.get("operation_id", "")))
            if relation is not None:
                step["sleeve_relation_lineage"] = copy.deepcopy(relation)
                covered_relations[relation["key"]] = relation
    if piece_lineage:
        result["instance_lineage_records"] = [
            copy.deepcopy(all_instances[key]) for key in sorted(all_instances)]
        result["sleeve_relation_lineage_records"] = copy.deepcopy(
            [covered_relations[key] for key in sorted(covered_relations)])
        provenance = copy.deepcopy(dict(result.get("provenance", {})))
        provenance["candidate_instance_lineage_adapter"] = (
            "exact compiled piece and operation addresses; no name or proximity inference")
        result["provenance"] = provenance
        result.pop("digest", None)
        result["digest"] = _digest(result)
    return result


def _lineage_stage(expected_instances: Sequence[Mapping[str, Any]],
                   actual_instances: Sequence[Mapping[str, Any]],
                   expected_relations: Sequence[Mapping[str, Any]],
                   actual_relations: Sequence[Mapping[str, Any]], *,
                   errors: Sequence[Mapping[str, Any]] = (),
                   applicable: bool = True) -> Dict[str, Any]:
    expected_instance_keys = [str(row["key"]) for row in expected_instances]
    actual_instance_keys = [str(row["key"]) for row in actual_instances]
    expected_relation_keys = [str(row["key"]) for row in expected_relations]
    actual_relation_keys = [str(row["key"]) for row in actual_relations]

    def duplicates(values: Sequence[str]) -> List[str]:
        return sorted({value for value in values if values.count(value) > 1})

    expected_instance_set = set(expected_instance_keys)
    actual_instance_set = set(actual_instance_keys)
    expected_relation_set = set(expected_relation_keys)
    actual_relation_set = set(actual_relation_keys)
    missing_instances = sorted(expected_instance_set - actual_instance_set)
    unexpected_instances = sorted(actual_instance_set - expected_instance_set)
    missing_relations = sorted(expected_relation_set - actual_relation_set)
    unexpected_relations = sorted(actual_relation_set - expected_relation_set)
    duplicate_instances = duplicates(actual_instance_keys)
    duplicate_relations = duplicates(actual_relation_keys)
    preserved = bool(
        applicable
        and not missing_instances and not unexpected_instances
        and not missing_relations and not unexpected_relations
        and not duplicate_instances and not duplicate_relations
        and not errors)
    return {
        "applicable": applicable,
        "preserved": preserved,
        "represented_instance_keys": sorted(actual_instance_set),
        "missing_instance_keys": missing_instances,
        "unexpected_instance_keys": unexpected_instances,
        "duplicate_instance_keys": duplicate_instances,
        "represented_relation_keys": sorted(actual_relation_set),
        "missing_relation_keys": missing_relations,
        "unexpected_relation_keys": unexpected_relations,
        "duplicate_relation_keys": duplicate_relations,
        "lineage_errors": copy.deepcopy(list(errors)),
    }


def _sleeve_instance_preservation_audit(
        structure: Mapping[str, Any], preview: Mapping[str, Any],
        pattern: Mapping[str, Any], manufacturing: Optional[Mapping[str, Any]],
        sewing: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    expected = _expected_sleeve_lineage(structure)
    expected_instances = expected["instances"]
    expected_relations = expected["relations"]
    required_ids = set(expected["required_source_node_ids"])
    if not expected["required"]:
        result = {
            "schema": "garment.parts-ir.instance-preservation.v1",
            "state": PROPOSED,
            "required": False,
            "expected_instances": [],
            "expected_relations": [],
            "stages": {},
            "all_required_artifacts_preserved": True,
            "compatibility": "NO_EXPLICIT_MULTI_INSTANCE_SLEEVE_LINEAGE_REQUIRED",
        }
        result["digest"] = _digest(result)
        return result

    preview_instances: List[Dict[str, str]] = []
    preview_errors: List[Dict[str, Any]] = []
    for part in preview.get("parts", []):
        if (not isinstance(part, Mapping)
                or part.get("source_node_id") not in required_ids):
            continue
        instances = part.get("instances")
        if not isinstance(instances, Sequence) or isinstance(instances, (str, bytes)):
            preview_errors.append({
                "source_node_id": part.get("source_node_id"),
                "reason": "3D preview part lacks an instances array",
            })
            continue
        for instance in instances:
            if not isinstance(instance, Mapping):
                preview_errors.append({
                    "source_node_id": part.get("source_node_id"),
                    "reason": "3D preview instance is not an object",
                })
                continue
            source_id = instance.get("source_node_id")
            side = _normalised_side(instance.get("side"))
            instance_id = instance.get("instance_id")
            if (not isinstance(source_id, str) or source_id not in required_ids
                    or side not in {"left", "right"}
                    or not isinstance(instance_id, str) or not instance_id):
                preview_errors.append({
                    "source_node_id": part.get("source_node_id"),
                    "reason": "3D preview instance lineage is incomplete",
                    "instance": copy.deepcopy(dict(instance)),
                })
                continue
            preview_instances.append(_instance_lineage_record(
                source_id, str(side), instance_id))
    preview_relations: List[Dict[str, str]] = []
    for relation in preview.get("sleeve_relation_coverage", []):
        if not isinstance(relation, Mapping):
            continue
        values = (
            relation.get("operation_id"), relation.get("kind"),
            _normalised_side(relation.get("side")),
            relation.get("source_node_id"), relation.get("target_node_id"),
            relation.get("source_instance_id"),
            relation.get("target_instance_id"))
        if all(isinstance(value, str) and value for value in values):
            preview_relations.append(_relation_lineage_record(
                *[str(value) for value in values]))
        else:
            preview_errors.append({
                "reason": "3D sleeve relation lineage is incomplete",
                "relation": copy.deepcopy(dict(relation)),
            })

    pattern_instances: List[Dict[str, str]] = []
    pattern_errors: List[Dict[str, Any]] = []
    for piece in pattern.get("pieces", []):
        if (not isinstance(piece, Mapping)
                or piece.get("source_node_id") not in required_ids):
            continue
        record, error = _piece_instance_lineage(piece)
        if error is not None:
            pattern_errors.append(error)
        elif record is not None:
            pattern_instances.append(record)
    pattern_relations, pattern_relation_by_operation, relation_errors = (
        _pattern_relation_lineage(pattern))
    pattern_errors.extend(relation_errors)

    manufacturing_instances: List[Dict[str, str]] = []
    manufacturing_errors: List[Dict[str, Any]] = []
    if isinstance(manufacturing, Mapping):
        for piece in manufacturing.get("pieces", []):
            if (not isinstance(piece, Mapping)
                    or piece.get("source_node_id") not in required_ids):
                continue
            record, error = _piece_instance_lineage(piece)
            if error is not None:
                manufacturing_errors.append(error)
            elif record is not None:
                manufacturing_instances.append(record)

    sewing_instances: List[Dict[str, str]] = []
    sewing_relations: List[Dict[str, str]] = []
    sewing_errors: List[Dict[str, Any]] = []
    sewing_applicable = bool(
        isinstance(sewing, Mapping)
        and sewing.get("order_verdict") == structure_sewing_plan.ANSWER)
    if isinstance(sewing, Mapping):
        for record in sewing.get("instance_lineage_records", []):
            if isinstance(record, Mapping) and record.get("source_node_id") in required_ids:
                sewing_instances.append(copy.deepcopy(dict(record)))
        for record in sewing.get("sleeve_relation_lineage_records", []):
            if isinstance(record, Mapping):
                sewing_relations.append(copy.deepcopy(dict(record)))
        if sewing_applicable:
            for operation_id, relation in pattern_relation_by_operation.items():
                step = next((
                    row for row in sewing.get("steps", [])
                    if isinstance(row, Mapping)
                    and row.get("operation_id") == operation_id), None)
                required_pieces = {
                    relation["source_instance_id"],
                    relation["target_instance_id"],
                }
                if (not isinstance(step, Mapping)
                        or not required_pieces <= set(step.get("pieces", []))):
                    sewing_errors.append({
                        "operation_id": operation_id,
                        "reason": "sewing step lacks exact relation endpoint addresses",
                        "required_piece_ids": sorted(required_pieces),
                    })

    stages = {
        "preview_3d": _lineage_stage(
            expected_instances, preview_instances,
            expected_relations, preview_relations, errors=preview_errors),
        "flat_pattern": _lineage_stage(
            expected_instances, pattern_instances,
            expected_relations, pattern_relations, errors=pattern_errors),
        "manufacturing_preview": _lineage_stage(
            expected_instances, manufacturing_instances,
            (), (), errors=manufacturing_errors,
            applicable=isinstance(manufacturing, Mapping)),
        "sewing_plan": _lineage_stage(
            expected_instances, sewing_instances,
            expected_relations, sewing_relations, errors=sewing_errors,
            applicable=sewing_applicable),
    }
    all_preserved = all(stage["preserved"] for stage in stages.values())
    result = {
        "schema": "garment.parts-ir.instance-preservation.v1",
        "state": PROPOSED if all_preserved else UNRESOLVED,
        "required": True,
        "expected_instances": copy.deepcopy(expected_instances),
        "expected_relations": copy.deepcopy(expected_relations),
        "stages": stages,
        "all_required_artifacts_preserved": all_preserved,
        "comparison_basis": (
            "exact source_node_id + side + physical instance and exact "
            "typed sleeve operation relation; no name/proximity inference"),
        "authority": {
            "highest_state": PROPOSED,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        },
    }
    result["digest"] = _digest(result)
    return result


def _part_preservation_audit(completion_candidate: Mapping[str, Any],
                             structure: Mapping[str, Any],
                             preview: Mapping[str, Any],
                             pattern: Mapping[str, Any],
                             manufacturing: Optional[Mapping[str, Any]],
                             sewing: Optional[Mapping[str, Any]],
                             ) -> Dict[str, Any]:
    """Prove that visible source parts are represented at each output stage."""
    source_nodes = [row for row in completion_candidate.get("nodes", [])
                    if isinstance(row, Mapping)]
    nodes = [row for row in structure.get("nodes", [])
             if isinstance(row, Mapping)]
    structural_kinds = {
        str(row.get("node_id")): str(row.get("kind")) for row in source_nodes
        if isinstance(row.get("node_id"), str)
    }
    source_ornament_bundle = completion_candidate.get(
        "ornament_artifacts", {})
    source_ornament_bundle = (
        source_ornament_bundle
        if isinstance(source_ornament_bundle, Mapping) else {})
    ornament_bundle = structure.get("ornament_artifacts", {})
    ornament_bundle = (ornament_bundle
                       if isinstance(ornament_bundle, Mapping) else {})
    source_ornament_ids = {
        str(row.get("ornament_id"))
        for row in source_ornament_bundle.get("result_manifest", [])
        if isinstance(row, Mapping)
        and isinstance(row.get("ornament_id"), str)
    }
    topology_ids = {
        str(row.get("node_id")) for row in nodes
        if isinstance(row.get("node_id"), str)
    }
    topology_ids.update(
        str(row.get("ornament_id"))
        for row in ornament_bundle.get("result_manifest", [])
        if isinstance(row, Mapping)
        and isinstance(row.get("ornament_id"), str))
    ornament_ids = source_ornament_ids
    input_part_ids = set(structural_kinds) | source_ornament_ids

    preview_parts = [row for row in preview.get("parts", [])
                     if isinstance(row, Mapping)]
    preview_ids = {
        str(row.get("source_ornament_id"))
        if row.get("geometry_role") == "ORNAMENT_CONSTRUCTION_PROXY"
        else str(row.get("source_node_id"))
        for row in preview_parts
        if ((row.get("geometry_role") == "ORNAMENT_CONSTRUCTION_PROXY"
             and isinstance(row.get("source_ornament_id"), str))
            or (row.get("geometry_role") != "ORNAMENT_CONSTRUCTION_PROXY"
                and isinstance(row.get("source_node_id"), str)))
    }

    pattern_pieces = [row for row in pattern.get("pieces", [])
                      if isinstance(row, Mapping)]
    pattern_ids = {
        str(value)
        for row in pattern_pieces
        for value in (row.get("source_node_id"),
                      row.get("source_ornament_id"))
        if isinstance(value, str)
    }
    pattern_ids.update(
        str(row.get("node_id")) for field in ("features", "drape_anchors")
        for row in pattern.get(field, []) if isinstance(row, Mapping)
        and isinstance(row.get("node_id"), str))

    cuttable_structural_ids = {
        node_id for node_id, kind in structural_kinds.items()
        if kind not in {"OPENING", "DRAPE_ANCHOR"}
    }
    manufacturing_required_ids = cuttable_structural_ids | ornament_ids
    manufacturing_ids: set[str] = set()
    if isinstance(manufacturing, Mapping):
        manufacturing_ids = {
            str(value)
            for row in manufacturing.get("pieces", [])
            if isinstance(row, Mapping)
            for value in (row.get("source_node_id"),
                          row.get("source_ornament_id"))
            if isinstance(value, str)
        }

    stages = {
        "topology": {
            "represented_part_ids": sorted(topology_ids),
            "missing_part_ids": sorted(input_part_ids - topology_ids),
        },
        "preview_3d": {
            "represented_part_ids": sorted(preview_ids),
            "missing_part_ids": sorted(input_part_ids - preview_ids),
        },
        "flat_pattern": {
            "represented_part_ids": sorted(pattern_ids),
            "missing_part_ids": sorted(input_part_ids - pattern_ids),
        },
        "manufacturing_preview": {
            "represented_part_ids": sorted(manufacturing_ids),
            "required_part_ids": sorted(manufacturing_required_ids),
            "not_applicable_part_ids": sorted(
                input_part_ids - manufacturing_required_ids),
            "missing_part_ids": sorted(
                manufacturing_required_ids - manufacturing_ids),
        },
    }
    missing = sorted({
        part_id for stage in stages.values()
        for part_id in stage["missing_part_ids"]
    })
    instance_preservation = _sleeve_instance_preservation_audit(
        structure, preview, pattern, manufacturing, sewing)
    all_preserved = bool(
        not missing
        and instance_preservation["all_required_artifacts_preserved"])
    result = {
        "schema": "garment.parts-ir.part-preservation.v2",
        "state": PROPOSED if all_preserved else UNRESOLVED,
        "input_part_ids": sorted(input_part_ids),
        "structural_part_ids": sorted(structural_kinds),
        "ornament_part_ids": sorted(ornament_ids),
        "stages": stages,
        "missing_part_ids": missing,
        "all_visible_input_parts_preserved": all_preserved,
        "source_node_set_preserved": not missing,
        "instance_preservation": instance_preservation,
        "instance_preservation_digest": instance_preservation["digest"],
        "all_required_instance_lineage_preserved": (
            instance_preservation["all_required_artifacts_preserved"]),
        "ornament_3d_representation": (
            "CONSTRUCTION_PROXY_NOT_FORMED_GEOMETRY" if ornament_ids
            else "NOT_APPLICABLE"),
        "authority": {
            "highest_state": PROPOSED,
            "observed": False,
            "approved": False,
            "manufacturing_ready": False,
        },
    }
    result["digest"] = _digest(result)
    return result


def _ornament_manufacturing_metadata(
        manufacturing: Mapping[str, Any], pattern: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(manufacturing))
    raw = pattern.get("ornament_artifacts")
    if not isinstance(raw, Mapping):
        return result
    piece_ids = set(raw.get("pattern_piece_ids", []))
    preview_piece_ids = {
        piece.get("piece_id") for piece in result.get("pieces", [])
        if isinstance(piece, Mapping)
    }
    if not piece_ids <= preview_piece_ids:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_MANUFACTURING_PIECES",
            "manufacturing preview omitted candidate-bound ornament pieces",
            missing_piece_ids=sorted(piece_ids - preview_piece_ids))
    result["ornament_artifacts"] = {
        "schema": "garment.manufacturing-preview.ornament-artifacts.v1",
        "state": PROPOSED,
        "readiness": raw.get("readiness"),
        "candidate_id": raw.get("candidate_id"),
        "candidate_digest": raw.get("candidate_digest"),
        "source_pattern_digest": pattern.get("digest"),
        "topology_structure_digest": raw.get("topology_structure_digest"),
        "ornament_topology_digest": raw.get("ornament_topology_digest"),
        "ornament_pattern_digest": raw.get("digest"),
        "pattern_piece_ids": sorted(piece_ids),
        "attachment_ports": copy.deepcopy(raw.get("attachment_ports", [])),
        "seam_intents": copy.deepcopy(raw.get("seam_intents", [])),
        "reviews": copy.deepcopy(raw.get("reviews", {})),
        "authority": {
            "highest_state": PROPOSED,
            "approved": False,
            "observed": False,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        },
    }
    result["ornament_artifacts"]["digest"] = _digest(
        result["ornament_artifacts"])
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result.pop("digest", None)
    result["digest"] = _digest(result)
    return result


def _intent_piece_ids(intent: Mapping[str, Any],
                      port_owners: Mapping[str, str]) -> List[str]:
    pieces: set[str] = set()
    for side in ("source", "target"):
        address = intent.get(side)
        if not isinstance(address, Mapping):
            continue
        piece_id = address.get("piece_id")
        if isinstance(piece_id, str) and piece_id:
            pieces.add(piece_id)
        port_id = address.get("port_id")
        if isinstance(port_id, str) and port_id in port_owners:
            pieces.add(port_owners[port_id])
    return sorted(pieces)


def _ornament_sewing_plan(sewing: Mapping[str, Any],
                          pattern: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(sewing))
    raw = pattern.get("ornament_artifacts")
    if not isinstance(raw, Mapping):
        return result
    if result.get("source_pattern_digest") != pattern.get("digest"):
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_SEWING_BINDING",
            "base sewing plan is not bound to the ornament-integrated pattern")
    intents = _ornament_rows(raw.get("seam_intents"), field="seam_intents")
    ports = _ornament_rows(raw.get("attachment_ports"), field="attachment_ports")
    expected_order = raw.get("construction_order")
    if expected_order != [intent.get("intent_id") for intent in intents]:
        raise _OrnamentIntegrationRefusal(
            "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_SEAM_ORDER",
            "ornament seam intents differ from their candidate-bound construction order")
    port_owners = {
        str(port["port_id"]): str(port["owner_piece_id"])
        for port in ports
        if isinstance(port.get("port_id"), str)
        and isinstance(port.get("owner_piece_id"), str)
    }
    existing_steps = [copy.deepcopy(dict(step)) for step in result.get("steps", [])
                      if isinstance(step, Mapping)]
    existing_step_ids = {step.get("step_id") for step in existing_steps}
    existing_operations = {step.get("operation_id") for step in existing_steps
                           if step.get("operation_id") is not None}
    reviews = [copy.deepcopy(dict(review)) for review in result.get("reviews", [])
               if isinstance(review, Mapping)]
    ornament_steps: List[Dict[str, Any]] = []
    previous_step_id: Optional[str] = None
    for intent in intents:
        intent_id = intent.get("intent_id")
        kind = str(intent.get("kind", "")).upper()
        if (not isinstance(intent_id, str) or not intent_id
                or intent_id in existing_operations
                or kind not in _ORNAMENT_ACTIONS):
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_SEWING_INTENT",
                "ornament sewing intents must have unique ids and supported actions",
                intent_id=intent_id, kind=kind)
        step_id = f"ornament:{intent_id}"
        if step_id in existing_step_ids:
            raise _OrnamentIntegrationRefusal(
                "UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_SEWING_COLLISION",
                "ornament sewing step collides with an existing step",
                step_id=step_id)
        binding = intent.get("topology_binding")
        binding = copy.deepcopy(dict(binding)) if isinstance(binding, Mapping) else None
        state = PROPOSED
        if (intent.get("stitch_choice")
                or (kind == "ATTACH_TO_GARMENT" and (
                    binding is None
                    or binding.get("target_port_resolved") is not True))):
            state = "REVIEW"
        step = {
            "step_id": step_id,
            "action": _ORNAMENT_ACTIONS[kind],
            "pieces": _intent_piece_ids(intent, port_owners),
            "quantity": 1,
            "depends_on": ([previous_step_id] if previous_step_id else []),
            "authority": "PROPOSED_ORNAMENT_TOPOLOGY",
            "state": state,
            "manufacturing_validated": False,
            "operation_id": intent_id,
            "kind": kind,
            "detail": copy.deepcopy(intent),
            "attachment_target_inferred": False,
        }
        if binding is not None:
            step["topology_binding"] = binding
        ornament_steps.append(step)
        previous_step_id = step_id
        if intent.get("stitch_choice"):
            reviews.append({
                "verdict": "REVIEW_STITCH_AND_MATERIAL_REQUIRED",
                "scope": intent_id,
                "why": "ornament geometry does not determine stitch, thread, reinforcement or finish",
                "how_to_close": "approve and test a material-specific ornament construction method",
            })
        if kind == "ATTACH_TO_GARMENT" and binding is None:
            reviews.append({
                "verdict": "REVIEW_ORNAMENT_ATTACHMENT_REQUIRED",
                "scope": intent_id,
                "why": "the ornament attachment target is unresolved and was not guessed",
                "how_to_close": "select one candidate-bound target piece and exact target port",
            })
        elif (kind == "ATTACH_TO_GARMENT"
              and binding.get("target_port_resolved") is not True):
            reviews.append({
                "verdict": "REVIEW_ORNAMENT_TARGET_PORT_REQUIRED",
                "scope": intent_id,
                "why": "the target node exists but no exact structural/flat-pattern port is resolved",
                "how_to_close": "approve an exact candidate-bound target port without proximity matching",
            })
        if kind == "ATTACH_TO_GARMENT":
            reviews.append({
                "verdict": "REVIEW_ORNAMENT_GARMENT_ORDER_REQUIRED",
                "scope": intent_id,
                "why": "geometry does not determine when the ornament is attached relative to garment assembly",
                "how_to_close": "approve attachment timing after accessibility and construction review",
            })

    all_steps = existing_steps + ornament_steps
    for index, step in enumerate(all_steps, 1):
        step["step"] = index
    review_table = {
        (str(review.get("verdict")), str(review.get("scope"))): review
        for review in reviews
    }
    reviews = [review_table[key] for key in sorted(review_table)]
    result.update({
        "verdict": (structure_sewing_plan.REVIEW_REQUIRED
                    if reviews else structure_sewing_plan.ANSWER),
        "order_verdict": structure_sewing_plan.ANSWER,
        "steps": all_steps,
        "dependency_graph": {
            str(step["step_id"]): list(step.get("depends_on", []))
            for step in all_steps
        },
        "reviews": reviews,
        "ornament_artifacts": {
            "schema": "garment.structure-sewing-plan.ornament-artifacts.v1",
            "state": PROPOSED,
            "readiness": raw.get("readiness"),
            "candidate_id": raw.get("candidate_id"),
            "candidate_digest": raw.get("candidate_digest"),
            "source_pattern_digest": pattern.get("digest"),
            "ornament_pattern_digest": raw.get("digest"),
            "ornament_topology_digest": raw.get("ornament_topology_digest"),
            "pattern_piece_ids": copy.deepcopy(raw.get("pattern_piece_ids", [])),
            "attachment_ports": ports,
            "seam_intents": intents,
            "step_ids": [step["step_id"] for step in ornament_steps],
            "authority": {
                "highest_state": PROPOSED,
                "approved": False,
                "observed": False,
                "manufacturing_ready": False,
                "manufacturing_certified": False,
            },
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    })
    result["ornament_artifacts"]["digest"] = _digest(
        result["ornament_artifacts"])
    provenance = copy.deepcopy(dict(result.get("provenance", {})))
    provenance.update({
        "ornament_intents_integrated": True,
        "ornament_attachment_target_inferred": False,
        "ornament_topology_digest": raw.get("ornament_topology_digest"),
    })
    result["provenance"] = provenance
    result.pop("digest", None)
    result["digest"] = _digest(result)
    return result


def _authority_refusal(stage: str, result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "verdict": "UNKNOWN_PARTS_IR_PIPELINE_AUTHORITY_ESCALATION",
        "state": UNRESOLVED,
        "why": f"{stage} attempted to exceed the PROPOSED pipeline boundary",
        "how_to_close": "return proposal-only preview artifacts and retain all manufacturing gates",
        "stage_result": copy.deepcopy(dict(result)),
    }


def _boundary_result(*, input_digest: Optional[str], code: str, why: str,
                     stage: str, input_mutated: bool = False,
                     detail: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    failure: Dict[str, Any] = {
        "stage": stage,
        "code": code,
        "state": UNRESOLVED,
        "why": why,
        "how_to_close": (
            "provide at least two PROPOSED candidates and either explicit target "
            "measurements or an explicit bounded preview profile"
        ),
    }
    if detail:
        failure["detail"] = copy.deepcopy(dict(detail))
    return {
        "schema": SCHEMA,
        "verdict": UNRESOLVED,
        "state": UNRESOLVED,
        "input_parts_ir_digest": input_digest,
        "candidate_count": 0,
        "successful_candidate_count": 0,
        "failed_candidate_count": 0,
        "candidates": [],
        "candidate_bindings": [],
        "failures": [failure],
        "authority": {
            "highest_state": PROPOSED,
            "approved": False,
            "observed": False,
            "answer": False,
        },
        "claims": {
            "proposal_only": True,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "all_candidates_resolved": False,
        },
        "provenance": {
            "method": "deterministic parts-IR proposal pipeline",
            "input_mutated": input_mutated,
            "candidate_failures_hidden": False,
        },
    }


def _isolated_topology(completion: Mapping[str, Any],
                       candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the public topology boundary without coupling candidate failures.

    ``apply_parts_ir_topology`` requires at least two candidates.  A shadow copy
    gives it the required batch shape while retaining identical candidate
    geometry.  Only the original candidate's result is returned; the shadow is
    explicitly recorded in pipeline provenance and never exposed as a design
    alternative.
    """
    candidate_id = str(candidate.get("candidate_id", ""))
    shadow = copy.deepcopy(dict(candidate))
    shadow["candidate_id"] = f"{candidate_id}::topology-isolation-shadow"
    isolated = copy.deepcopy(dict(completion))
    isolated["candidate_count"] = 2
    isolated["candidates"] = [copy.deepcopy(dict(candidate)), shadow]
    result = parts_ir_topology.apply_parts_ir_topology(isolated)
    if result.get("verdict") != PROPOSED:
        return result
    rows = result.get("candidates")
    if (not isinstance(rows, Sequence) or isinstance(rows, (str, bytes))
            or len(rows) != 2 or not isinstance(rows[0], Mapping)):
        return {
            "verdict": "UNKNOWN_PARTS_IR_PIPELINE_TOPOLOGY_RESULT",
            "state": UNRESOLVED,
            "why": "topology returned no candidate matching the isolated input",
            "how_to_close": "repair the parts_ir_topology result contract",
        }
    selected = copy.deepcopy(dict(rows[0]))
    selected["candidate_id"] = candidate_id
    return {
        "verdict": PROPOSED,
        "state": PROPOSED,
        "candidate": selected,
        "isolation_input_digest": result.get("input_completion_digest"),
        "isolation_topology_digest": result.get("topology_digest"),
        "shadow_candidate_exposed": False,
    }


def _completion_shadow(slot: int) -> Dict[str, Any]:
    """Return a valid non-design candidate used only to preserve variant slot."""
    return {
        "candidate_id": f"pipeline-completion-shadow-{slot}",
        "state": PROPOSED,
        "parts": [{
            "part_id": f"pipeline-shadow-anchor-{slot}",
            "kind": "DRAPE_ANCHOR",
            "layer": 0,
            "placement": "pipeline completion isolation only",
            "visible_basis": {
                "state": PROPOSED,
                "basis": "non-design shadow used to isolate one completion candidate",
                "breaks_when": "the completion API accepts a single explicit candidate",
            },
            "dimensions": {},
        }],
    }


def _input_candidate_id(candidate: Any, index: int) -> str:
    if isinstance(candidate, Mapping):
        supplied = candidate.get("candidate_id")
        if isinstance(supplied, str) and supplied.strip():
            return supplied.strip()
    return f"input-candidate-{index}-{_digest(candidate)[:12]}"


def _completion_refusal_candidate(candidate: Any, index: int,
                                  result: Mapping[str, Any]) -> Dict[str, Any]:
    candidate_id = _input_candidate_id(candidate, index)
    failure = _failure(
        "parts_ir_completion", result,
        fallback="UNKNOWN_PARTS_IR_PIPELINE_COMPLETION_REFUSAL")
    candidate_digest = _digest({
        "candidate_id": candidate_id,
        "input_candidate": candidate,
        "failure_codes": [failure["code"]],
    })
    return {
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "state": UNRESOLVED,
        "verdict": failure["code"],
        "execution_status": "REFUSED",
        "completion_structure_digest": None,
        "input_candidate": copy.deepcopy(candidate),
        "failures": [failure],
        "preview": None,
        "flat_pattern": None,
        "manufacturing_preview": None,
        "sewing_plan": None,
    }


def _isolate_explicit_completions(
    parts_ir: Mapping[str, Any], *,
    target_measurements: Optional[Mapping[str, Any]],
    preview_profile: Optional[Mapping[str, Any]],
    candidate_count: Optional[int],
) -> Optional[List[Dict[str, Any]]]:
    """Recover per-candidate completion results after aggregate refusal."""
    raw_candidates = parts_ir.get("candidates")
    if (not isinstance(raw_candidates, Sequence)
            or isinstance(raw_candidates, (str, bytes))
            or len(raw_candidates) < 2):
        return None
    records: List[Dict[str, Any]] = []
    for index, raw_candidate in enumerate(raw_candidates):
        isolated_candidates = [_completion_shadow(slot)
                               for slot in range(len(raw_candidates))]
        isolated_candidates[index] = copy.deepcopy(raw_candidate)
        isolated_input: Dict[str, Any] = {
            "schema": parts_ir.get("schema", parts_ir_completion.SCHEMA),
            "candidates": isolated_candidates,
        }
        if "state" in parts_ir:
            isolated_input["state"] = copy.deepcopy(parts_ir["state"])
        result = parts_ir_completion.complete_parts_ir(
            isolated_input,
            target_measurements=target_measurements,
            preview_profile=preview_profile,
            candidate_count=candidate_count)
        candidates = result.get("candidates")
        if (result.get("verdict") != PROPOSED
                or not isinstance(candidates, Sequence)
                or isinstance(candidates, (str, bytes))
                or len(candidates) != len(raw_candidates)
                or not isinstance(candidates[index], Mapping)):
            records.append({
                "refusal": _completion_refusal_candidate(
                    raw_candidate, index, result),
            })
            continue
        records.append({
            "candidate": copy.deepcopy(dict(candidates[index])),
            "completion": result,
            "completion_isolated": True,
            "completion_shadow_candidates_exposed": False,
        })
    return records


def _run_candidate(completion: Mapping[str, Any],
                   candidate: Mapping[str, Any], *,
                   radial_segments: int,
                   layer_spacing_cm: float) -> Dict[str, Any]:
    candidate_id = candidate.get("candidate_id")
    source_digest = candidate.get("structure_digest")
    row: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "state": PROPOSED,
        "execution_status": "RUNNING",
        "completion_structure_digest": source_digest,
        "completion_candidate": copy.deepcopy(dict(candidate)),
        "failures": [],
        "manufacturing_preview": None,
        "sewing_plan": None,
    }

    topology = _isolated_topology(completion, candidate)
    if topology.get("verdict") != PROPOSED:
        failure = _failure(
            "parts_ir_topology", topology,
            fallback="UNKNOWN_PARTS_IR_PIPELINE_TOPOLOGY_REFUSAL")
        row.update({
            "verdict": failure["code"],
            "state": UNRESOLVED,
            "execution_status": "REFUSED",
            "failures": [failure],
            "preview": None,
            "flat_pattern": None,
            "manufacturing_preview": None,
            "sewing_plan": None,
        })
        row["candidate_digest"] = _digest({
            "candidate_id": candidate_id,
            "completion_structure_digest": source_digest,
            "failure_codes": [failure["code"]],
        })
        return row

    structure = topology["candidate"]
    structure_digest = structure.get("structure_digest")
    row.update({
        "structure": copy.deepcopy(structure),
        "structure_digest": structure_digest,
        "topology_digest": structure.get("topology_digest"),
        "topology_execution": {
            "state": PROPOSED,
            "isolated_with_non_design_shadow": True,
            "shadow_candidate_exposed": False,
            "isolation_input_digest": topology.get("isolation_input_digest"),
            "isolation_topology_digest": topology.get("isolation_topology_digest"),
        },
    })

    preview = structure_preview.generate_preview(
        structure, candidate_id=str(candidate_id),
        radial_segments=radial_segments,
        layer_spacing_cm=layer_spacing_cm)
    base_pattern = structure_to_pattern.compile(
        structure, candidate_state=PROPOSED,
        candidate_id=str(candidate_id))
    pattern = copy.deepcopy(base_pattern)
    ornament_integration_failure: Optional[Dict[str, Any]] = None
    if (base_pattern.get("verdict") == structure_to_pattern.ANSWER
            and isinstance(structure.get("ornament_artifacts"), Mapping)):
        try:
            pattern = _integrate_ornament_pattern(
                base_pattern, structure, candidate_id=str(candidate_id))
            preview = _integrate_ornament_preview(
                preview, structure, candidate_id=str(candidate_id),
                layer_spacing_cm=layer_spacing_cm)
        except _OrnamentIntegrationRefusal as refusal:
            ornament_integration_failure = _ornament_refusal(
                refusal.code, refusal.why, **refusal.detail)
    row["preview"] = copy.deepcopy(preview)
    row["flat_pattern"] = copy.deepcopy(pattern)

    failures: List[Dict[str, Any]] = []
    if preview.get("verdict") != structure_preview.ANSWER:
        failures.append(_failure(
            "structure_preview", preview,
            fallback="UNKNOWN_PARTS_IR_PIPELINE_PREVIEW_REFUSAL"))
    if pattern.get("verdict") != structure_to_pattern.ANSWER:
        failures.append(_failure(
            "structure_to_pattern", pattern,
            fallback="UNKNOWN_PARTS_IR_PIPELINE_PATTERN_REFUSAL"))
    if ornament_integration_failure is not None:
        failures.append(_failure(
            "ornament_artifact_integration", ornament_integration_failure,
            fallback="UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_INTEGRATION"))

    preview_digest = preview.get("structure_digest")
    pattern_digest = pattern.get("structure_digest")
    if (not failures and (not isinstance(structure_digest, str)
                          or preview_digest != structure_digest
                          or pattern_digest != structure_digest)):
        failures.append({
            "stage": "artifact_binding",
            "code": "UNKNOWN_PARTS_IR_PIPELINE_STRUCTURE_DIGEST_MISMATCH",
            "state": UNRESOLVED,
            "why": "candidate 3D and flat pattern were not derived from one structure digest",
            "how_to_close": "rerun both artifacts from the same validated topology candidate",
            "expected_structure_digest": structure_digest,
            "preview_structure_digest": preview_digest,
            "pattern_structure_digest": pattern_digest,
        })

    manufacturing: Optional[Dict[str, Any]] = None
    sewing: Optional[Dict[str, Any]] = None
    if not failures:
        try:
            manufacturing = pattern_manufacturing_bundle.build(
                pattern, allow_proposed_default=True)
            if (manufacturing.get("verdict")
                    == pattern_manufacturing_bundle.ANSWER):
                manufacturing = _ornament_manufacturing_metadata(
                    manufacturing, pattern)
            sewing = structure_sewing_plan.plan(pattern)
            if sewing.get("order_verdict") == structure_sewing_plan.ANSWER:
                sewing = _ornament_sewing_plan(sewing, pattern)
                sewing = _annotate_sewing_instance_lineage(sewing, pattern)
        except _OrnamentIntegrationRefusal as refusal:
            failures.append(_failure(
                "ornament_artifact_integration",
                _ornament_refusal(refusal.code, refusal.why, **refusal.detail),
                fallback="UNKNOWN_PARTS_IR_PIPELINE_ORNAMENT_INTEGRATION"))
            manufacturing = manufacturing if isinstance(
                manufacturing, Mapping) else None
            sewing = sewing if isinstance(sewing, Mapping) else None
    if manufacturing is not None and sewing is not None:
        if manufacturing.get("verdict") != pattern_manufacturing_bundle.ANSWER:
            failures.append(_failure(
                "pattern_manufacturing_bundle", manufacturing,
                fallback="UNKNOWN_PARTS_IR_PIPELINE_MANUFACTURING_REFUSAL"))
        if sewing.get("order_verdict") != structure_sewing_plan.ANSWER:
            failures.append(_failure(
                "structure_sewing_plan", sewing,
                fallback="UNKNOWN_PARTS_IR_PIPELINE_SEWING_PLAN_REFUSAL"))

        manufacturing_escalated = (
            manufacturing.get("verdict") == pattern_manufacturing_bundle.ANSWER
            and (manufacturing.get("candidate_state") != PROPOSED
                 or manufacturing.get("manufacturing_ready") is True
                 or manufacturing.get("manufacturing_certified") is True))
        if manufacturing_escalated:
            authority = _authority_refusal(
                "pattern_manufacturing_bundle", manufacturing)
            failures.append(_failure(
                "pattern_manufacturing_bundle", authority,
                fallback="UNKNOWN_PARTS_IR_PIPELINE_AUTHORITY_ESCALATION"))
        sewing_escalated = (
            sewing.get("order_verdict") == structure_sewing_plan.ANSWER
            and (sewing.get("candidate_state") != PROPOSED
                 or sewing.get("manufacturing_ready") is True
                 or sewing.get("manufacturing_certified") is True))
        if sewing_escalated:
            authority = _authority_refusal("structure_sewing_plan", sewing)
            failures.append(_failure(
                "structure_sewing_plan", authority,
                fallback="UNKNOWN_PARTS_IR_PIPELINE_AUTHORITY_ESCALATION"))

        if (manufacturing.get("verdict") == pattern_manufacturing_bundle.ANSWER
                and sewing.get("order_verdict") == structure_sewing_plan.ANSWER):
            manufacturing_bound = (
                manufacturing.get("candidate_id") == candidate_id
                and manufacturing.get("structure_digest") == structure_digest
                and manufacturing.get("source_digest") == pattern.get("digest"))
            sewing_bound = (
                sewing.get("candidate_id") == candidate_id
                and sewing.get("structure_digest") == structure_digest
                and sewing.get("source_pattern_digest") == pattern.get("digest"))
            if not manufacturing_bound or not sewing_bound:
                failures.append({
                    "stage": "artifact_binding",
                    "code": "UNKNOWN_PARTS_IR_PIPELINE_MANUFACTURING_BINDING_MISMATCH",
                    "state": UNRESOLVED,
                    "why": "manufacturing preview or sewing order is not bound to the candidate flat-pattern digest",
                    "how_to_close": "regenerate both downstream artifacts from this exact compiled pattern",
                    "manufacturing_bound": manufacturing_bound,
                    "sewing_plan_bound": sewing_bound,
                    "expected_pattern_digest": pattern.get("digest"),
                    "manufacturing_source_digest": manufacturing.get("source_digest"),
                    "sewing_source_pattern_digest": sewing.get("source_pattern_digest"),
                })

    if manufacturing is not None:
        row["manufacturing_preview"] = (
            _compact_manufacturing_preview(manufacturing)
            if manufacturing.get("verdict") == pattern_manufacturing_bundle.ANSWER
            else copy.deepcopy(manufacturing))
    if sewing is not None:
        row["sewing_plan"] = copy.deepcopy(sewing)

    part_preservation: Optional[Dict[str, Any]] = None
    if (preview.get("verdict") == structure_preview.ANSWER
            and pattern.get("verdict") == structure_to_pattern.ANSWER
            and isinstance(manufacturing, Mapping)
            and manufacturing.get("verdict")
            == pattern_manufacturing_bundle.ANSWER):
        part_preservation = _part_preservation_audit(
            candidate, structure, preview, pattern, manufacturing, sewing)
        row["part_preservation"] = copy.deepcopy(part_preservation)
        if not failures and not part_preservation["source_node_set_preserved"]:
            failures.append({
                "stage": "part_preservation",
                "code": "UNKNOWN_PARTS_IR_PIPELINE_VISIBLE_PART_DROPPED",
                "state": UNRESOLVED,
                "why": (
                    "one or more visible source parts disappeared between "
                    "topology, 3D preview, flat pattern, and cutting preview"),
                "how_to_close": (
                    "restore explicit source_node_id/source_ornament_id "
                    "lineage and regenerate every candidate-bound artifact"),
                "missing_part_ids": copy.deepcopy(
                    part_preservation["missing_part_ids"]),
                "preservation_audit": copy.deepcopy(part_preservation),
            })
        elif (not failures
              and not part_preservation[
                  "all_required_instance_lineage_preserved"]):
            failures.append({
                "stage": "part_preservation",
                "code": "UNKNOWN_PARTS_IR_PIPELINE_INSTANCE_LINEAGE_DROPPED",
                "state": UNRESOLVED,
                "why": (
                    "a bilateral or layered sleeve instance/relation lost its "
                    "exact source-node, side, physical-instance, or operation lineage"),
                "how_to_close": (
                    "restore exact side-specific instance and typed relation "
                    "addresses in 3D, flat pattern, cutting, and sewing artifacts"),
                "instance_preservation": copy.deepcopy(
                    part_preservation["instance_preservation"]),
            })

    ornament_artifacts = pattern.get("ornament_artifacts", {})
    ornament_topology_digest = (
        ornament_artifacts.get("ornament_topology_digest")
        if isinstance(ornament_artifacts, Mapping) else None)
    manufacturing_ornaments = (
        manufacturing.get("ornament_artifacts", {})
        if isinstance(manufacturing, Mapping) else {})
    sewing_ornaments = (
        sewing.get("ornament_artifacts", {})
        if isinstance(sewing, Mapping) else {})
    ornament_required = isinstance(ornament_artifacts, Mapping) and bool(
        ornament_artifacts)
    ornament_downstream_bound = bool(
        not ornament_required
        or (isinstance(manufacturing_ornaments, Mapping)
            and isinstance(sewing_ornaments, Mapping)
            and manufacturing_ornaments.get("candidate_id") == candidate_id
            and sewing_ornaments.get("candidate_id") == candidate_id
            and manufacturing_ornaments.get("source_pattern_digest")
            == pattern.get("digest")
            and sewing_ornaments.get("source_pattern_digest")
            == pattern.get("digest")
            and manufacturing_ornaments.get("ornament_topology_digest")
            == ornament_topology_digest
            and sewing_ornaments.get("ornament_topology_digest")
            == ornament_topology_digest))
    candidate_digest = _digest({
        "candidate_id": candidate_id,
        "structure_digest": structure_digest,
        "ornament_topology_digest": ornament_topology_digest,
    })
    row.update({
        "candidate_digest": candidate_digest,
        "artifact_binding": {
            "candidate_id": candidate_id,
            "candidate_digest": candidate_digest,
            "structure_digest": structure_digest,
            "preview_structure_digest": preview_digest,
            "pattern_structure_digest": pattern_digest,
            "same_structure_digest": bool(
                isinstance(structure_digest, str)
                and preview_digest == structure_digest
                and pattern_digest == structure_digest),
            "preview_digest": preview.get("preview_digest"),
            "base_pattern_digest": base_pattern.get("digest"),
            "pattern_digest": pattern.get("digest"),
            "ornament_topology_digest": ornament_topology_digest,
            "ornament_pattern_digest": (
                ornament_artifacts.get("digest")
                if isinstance(ornament_artifacts, Mapping) else None),
            "ornament_downstream_bound": ornament_downstream_bound,
            "all_visible_input_parts_preserved": (
                part_preservation.get("all_visible_input_parts_preserved")
                if isinstance(part_preservation, Mapping) else None),
            "all_required_instance_lineage_preserved": (
                part_preservation.get(
                    "all_required_instance_lineage_preserved")
                if isinstance(part_preservation, Mapping) else None),
            "instance_preservation_digest": (
                part_preservation.get("instance_preservation_digest")
                if isinstance(part_preservation, Mapping) else None),
            "manufacturing_source_pattern_digest": (
                manufacturing.get("source_digest")
                if isinstance(manufacturing, Mapping) else None),
            "manufacturing_structure_digest": (
                manufacturing.get("structure_digest")
                if isinstance(manufacturing, Mapping) else None),
            "manufacturing_artifact_digest": (
                manufacturing.get("digest")
                if isinstance(manufacturing, Mapping) else None),
            "sewing_source_pattern_digest": (
                sewing.get("source_pattern_digest")
                if isinstance(sewing, Mapping) else None),
            "sewing_structure_digest": (
                sewing.get("structure_digest")
                if isinstance(sewing, Mapping) else None),
            "sewing_plan_digest": (
                sewing.get("digest") if isinstance(sewing, Mapping) else None),
            "all_downstream_artifacts_bound": bool(
                isinstance(manufacturing, Mapping)
                and isinstance(sewing, Mapping)
                and manufacturing.get("candidate_id") == candidate_id
                and manufacturing.get("source_digest") == pattern.get("digest")
                and manufacturing.get("structure_digest") == structure_digest
                and sewing.get("candidate_id") == candidate_id
                and sewing.get("source_pattern_digest") == pattern.get("digest")
                and sewing.get("structure_digest") == structure_digest
                and ornament_downstream_bound),
            "state": PROPOSED,
        },
        "failures": failures,
    })
    if failures:
        row.update({
            "verdict": failures[0]["code"],
            "state": UNRESOLVED,
            "execution_status": "REFUSED",
        })
    else:
        row.update({
            "verdict": PROPOSED,
            "state": PROPOSED,
            "execution_status": "SUCCEEDED",
        })
    return row


def run_parts_ir_pipeline(
    parts_ir: Mapping[str, Any], *,
    target_measurements: Optional[Mapping[str, Any]] = None,
    preview_profile: Optional[Mapping[str, Any]] = None,
    candidate_count: Optional[int] = None,
    radial_segments: int = 16,
    layer_spacing_cm: float = 0.6,
) -> Dict[str, Any]:
    """Run proposal completion through compact cutting and sewing previews.

    A caller must explicitly supply target measurements or a bounded preview
    profile.  The pipeline never silently chooses mannequin dimensions.
    """
    if not isinstance(parts_ir, Mapping):
        return _boundary_result(
            input_digest=None,
            code="UNKNOWN_PARTS_IR_PIPELINE_INPUT",
            why="parts_ir must be a mapping",
            stage="input")
    try:
        original = copy.deepcopy(parts_ir)
        target_original = copy.deepcopy(target_measurements)
        profile_original = copy.deepcopy(preview_profile)
        input_digest = _digest(parts_ir)
    except (TypeError, ValueError, OverflowError) as exc:
        return _boundary_result(
            input_digest=None,
            code="UNKNOWN_PARTS_IR_PIPELINE_NOT_JSON",
            why=f"parts_ir must contain finite JSON values: {exc}",
            stage="input")

    if target_measurements is None and preview_profile is None:
        return _boundary_result(
            input_digest=input_digest,
            code="UNKNOWN_PARTS_IR_PIPELINE_MEASUREMENT_SOURCE_REQUIRED",
            why=("the proposal pipeline requires target_measurements or an "
                 "explicit bounded preview_profile"),
            stage="measurement_source")

    completion = parts_ir_completion.complete_parts_ir(
        parts_ir,
        target_measurements=target_measurements,
        preview_profile=preview_profile,
        candidate_count=candidate_count)
    candidate_records: Optional[List[Dict[str, Any]]] = None
    if completion.get("verdict") == PROPOSED:
        completed_candidates = completion.get("candidates")
        if (isinstance(completed_candidates, Sequence)
                and not isinstance(completed_candidates, (str, bytes))
                and len(completed_candidates) >= 2
                and all(isinstance(row, Mapping)
                        for row in completed_candidates)):
            candidate_records = [{
                "candidate": candidate,
                "completion": completion,
                "completion_isolated": False,
                "completion_shadow_candidates_exposed": False,
            } for candidate in completed_candidates]
    else:
        # Duplicate ids are a cross-candidate identity failure and cannot be
        # made safe by isolation: recovering both would create ambiguous
        # candidate/digest bindings.
        if completion.get("verdict") != "UNKNOWN_PARTS_IR_DUPLICATE_CANDIDATE":
            candidate_records = _isolate_explicit_completions(
                parts_ir,
                target_measurements=target_measurements,
                preview_profile=preview_profile,
                candidate_count=candidate_count)

    if candidate_records is None:
        failure = _failure(
            "parts_ir_completion", completion,
            fallback="UNKNOWN_PARTS_IR_PIPELINE_COMPLETION_RESULT")
        result = _boundary_result(
            input_digest=input_digest, code=failure["code"],
            why=failure["why"], stage="parts_ir_completion",
            detail={"engine_result": failure["engine_result"]})
        result["failures"] = [failure]
        result["completion"] = copy.deepcopy(completion)
        result["provenance"]["input_mutated"] = (
            parts_ir != original
            or target_measurements != target_original
            or preview_profile != profile_original)
        return result

    candidates: List[Dict[str, Any]] = []
    for record in candidate_records:
        if "refusal" in record:
            candidates.append(record["refusal"])
            continue
        candidate_result = _run_candidate(
            record["completion"], record["candidate"],
            radial_segments=radial_segments,
            layer_spacing_cm=layer_spacing_cm)
        candidate_result["completion_execution"] = {
            "isolated_with_non_design_shadows": record["completion_isolated"],
            "shadow_candidates_exposed": record[
                "completion_shadow_candidates_exposed"],
            "state": PROPOSED,
        }
        candidates.append(candidate_result)
    input_mutated = (
        parts_ir != original
        or _digest(parts_ir) != input_digest
        or target_measurements != target_original
        or preview_profile != profile_original)
    if input_mutated:
        return _boundary_result(
            input_digest=input_digest,
            code="UNKNOWN_PARTS_IR_PIPELINE_INPUT_MUTATED",
            why="a pipeline stage mutated garment.parts-ir.v1 input",
            stage="input_integrity", input_mutated=True,
            detail={"candidate_results": candidates})

    failed = [row for row in candidates
              if row["execution_status"] != "SUCCEEDED"]
    bindings = [{
        "candidate_id": row["candidate_id"],
        "candidate_digest": row["candidate_digest"],
        "structure_digest": row.get("structure_digest"),
        "completion_structure_digest": row.get("completion_structure_digest"),
        "preview_structure_digest": row.get(
            "artifact_binding", {}).get("preview_structure_digest"),
        "pattern_structure_digest": row.get(
            "artifact_binding", {}).get("pattern_structure_digest"),
        "base_pattern_digest": row.get(
            "artifact_binding", {}).get("base_pattern_digest"),
        "pattern_digest": row.get(
            "artifact_binding", {}).get("pattern_digest"),
        "ornament_topology_digest": row.get(
            "artifact_binding", {}).get("ornament_topology_digest"),
        "ornament_pattern_digest": row.get(
            "artifact_binding", {}).get("ornament_pattern_digest"),
        "ornament_downstream_bound": row.get(
            "artifact_binding", {}).get("ornament_downstream_bound"),
        "all_visible_input_parts_preserved": row.get(
            "artifact_binding", {}).get(
                "all_visible_input_parts_preserved"),
        "all_required_instance_lineage_preserved": row.get(
            "artifact_binding", {}).get(
                "all_required_instance_lineage_preserved"),
        "instance_preservation_digest": row.get(
            "artifact_binding", {}).get("instance_preservation_digest"),
        "manufacturing_artifact_digest": row.get(
            "artifact_binding", {}).get("manufacturing_artifact_digest"),
        "manufacturing_source_pattern_digest": row.get(
            "artifact_binding", {}).get(
                "manufacturing_source_pattern_digest"),
        "sewing_plan_digest": row.get(
            "artifact_binding", {}).get("sewing_plan_digest"),
        "sewing_source_pattern_digest": row.get(
            "artifact_binding", {}).get("sewing_source_pattern_digest"),
        "all_downstream_artifacts_bound": row.get(
            "artifact_binding", {}).get("all_downstream_artifacts_bound"),
        "execution_status": row["execution_status"],
    } for row in candidates]
    all_failures = [copy.deepcopy(failure)
                    for row in failed for failure in row["failures"]]
    all_resolved = not failed
    return {
        "schema": SCHEMA,
        "verdict": PROPOSED if all_resolved else UNRESOLVED,
        "state": PROPOSED if all_resolved else UNRESOLVED,
        "input_parts_ir_digest": input_digest,
        "completion_digest": _digest(completion),
        "candidate_count": len(candidates),
        "successful_candidate_count": len(candidates) - len(failed),
        "failed_candidate_count": len(failed),
        "candidates": candidates,
        "candidate_bindings": bindings,
        "failures": all_failures,
        "completion": copy.deepcopy(completion),
        "authority": {
            "highest_state": PROPOSED,
            "approved": False,
            "observed": False,
            "answer": False,
        },
        "claims": {
            "proposal_only": True,
            "manufacturing_preview_ready": bool(
                all_resolved and all(
                    isinstance(row.get("manufacturing_preview"), Mapping)
                    and row["manufacturing_preview"].get(
                        "manufacturing_preview_ready") is True
                    for row in candidates)),
            "topology_sewing_order_derived": bool(
                all_resolved and all(
                    isinstance(row.get("sewing_plan"), Mapping)
                    and row["sewing_plan"].get("order_verdict")
                    == structure_sewing_plan.ANSWER
                    for row in candidates)),
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "all_candidates_resolved": all_resolved,
        },
        "provenance": {
            "method": (
                "parts_ir_completion -> isolated parts_ir_topology -> "
                "candidate-specific structure_preview + structure_to_pattern -> "
                "compact pattern_manufacturing_bundle + structure_sewing_plan"),
            "measurement_source": (
                "TARGET_AND_BOUNDED_PREVIEW" if (
                    target_measurements is not None and preview_profile is not None)
                else "TARGET_MEASUREMENTS" if target_measurements is not None
                else "EXPLICIT_BOUNDED_PREVIEW_PROFILE"),
            "input_mutated": False,
            "candidate_failures_hidden": False,
            "topology_isolation_shadow_is_not_a_design_candidate": True,
            "full_svg_dxf_payloads_returned": False,
            "full_manufacturing_artifact_digests_preserved": True,
        },
    }


run = run_parts_ir_pipeline


__all__ = ["SCHEMA", "run_parts_ir_pipeline", "run"]
