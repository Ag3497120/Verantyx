# -*- coding: utf-8 -*-
"""Deterministic, proposal-only topology for completed vision parts IR.

The module consumes :mod:`photoloset.parts_ir_completion` output.  It never
infers attachment from a part name, image, or proximity.  Operations are made
only from model-supplied ``attached_to`` relations plus the bounded rules in
this file.  Any missing target, incompatible dimension, unsupported relation,
or incomplete trouser topology is returned as typed ``UNKNOWN``/``UNRESOLVED``.

Set-in sleeve construction is intentionally absent: ``structure_to_pattern``
owns the BODY_SHELL/SLEEVE bridge and adding a primitive JOIN here would create
a duplicate seam with weaker addressing.
"""
from __future__ import annotations

import copy
import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from . import garment_structure
from .parts_ir_completion import (
    ORNAMENT_ARTIFACT_SCHEMA,
    RESULT_SCHEMA as COMPLETION_SCHEMA,
)


SCHEMA = "garment.parts-ir.topology.v1"
CANDIDATE_GEOMETRY_SCHEMA = "garment.parts-ir.candidate-geometry.v1"
PROPOSED = "PROPOSED"
UNRESOLVED = "UNRESOLVED"
_TOLERANCE_CM = 0.05
_TROUSER_ROLES = {"trouser", "trousers", "trouser_leg", "pants_leg"}
_MAX_WAIST_STACK_LAYERS = 8
_WAIST_STACK_CONSTRUCTION_MODES = {"JOIN", "GATHER", "LAYER"}
_WAIST_STACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_SLEEVE_GATHER_RATIO = 3.0
_OUTER_WAIST_OVERLAY_KINDS = {"FLARE", "FRUSTUM", "GORE", "OVERLAY"}


class _Refusal(Exception):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verdict": code,
        "state": UNRESOLVED,
        "why": why,
        "how_to_close": (
            "supply explicit PROPOSED attached_to/side/garment_unit fields and "
            "dimensionally compatible boundary lengths"
        ),
        **detail,
    }


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_NOT_JSON",
                       f"{field} must contain finite JSON data",
                       field=field, error=str(exc)) from exc
    return copy.deepcopy(value)


def _positive(value: Any, *, field: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) <= 0.0):
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_DIMENSION",
                       f"{field} must be finite and positive", field=field)
    return float(value)


def _attributes(node: Mapping[str, Any]) -> Mapping[str, Any]:
    value = node.get("attributes", {})
    if not isinstance(value, Mapping):
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_ATTRIBUTES",
                       f"{node.get('node_id')} attributes must be an object")
    return value


def _attribute(node: Mapping[str, Any], name: str) -> Any:
    return _attributes(node).get(name)


def _opening_semantic_authority(node: Mapping[str, Any]) -> None:
    """Reject a tampered completion that promotes model closure semantics."""
    for field in ("closure_detail", "opening_topology"):
        value = _attribute(node, field)
        if not isinstance(value, Mapping):
            continue
        for authority_field in ("state", "authority", "verdict"):
            claimed = value.get(authority_field)
            if claimed is None:
                continue
            if not isinstance(claimed, str) or claimed.upper() != PROPOSED:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_AUTHORITY_ESCALATION",
                    f"{node.get('node_id')}.{field} must remain PROPOSED",
                    node_id=node.get("node_id"), field=field,
                    authority_field=authority_field, claimed_state=claimed)


def _opening_topology_proposal(node: Mapping[str, Any],
                               parent_id: str) -> Dict[str, Any]:
    resolution = {
        "state": PROPOSED,
        "basis": f"{node.get('node_id')}.attached_to explicitly names {parent_id}",
        "breaks_when": (
            "the opening position, closure method or target panel changes"),
        "geometry_cut_created": False,
        "not_observed_from_front_only_input": True,
    }
    proposed = _attribute(node, "opening_topology")
    if proposed is None:
        return resolution
    if isinstance(proposed, Mapping):
        result = copy.deepcopy(dict(proposed))
        result["state"] = PROPOSED
        result["geometry_cut_created"] = False
        result["topology_resolution"] = resolution
        return result
    visible = _attributes(node).get("visible_basis", {})
    visible = visible if isinstance(visible, Mapping) else {}
    return {
        "state": PROPOSED,
        "proposal": copy.deepcopy(proposed),
        "basis": visible.get(
            "basis", "model-supplied opening topology proposal"),
        "breaks_when": visible.get(
            "breaks_when", "another view or construction review rejects it"),
        "geometry_cut_created": False,
        "topology_resolution": resolution,
    }


def _tokens(value: Any) -> Set[str]:
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {str(item).strip().lower() for item in value
                if isinstance(item, str) and item.strip()}
    return set()


def _semantic_words(value: Any) -> Set[str]:
    """Tokenize descriptive proposal evidence without granting authority.

    `_tokens` intentionally preserves closed enum-like values.  Pixel-model
    `visible_basis`, however, is natural language and may carry the only
    explicit statement that a front panel is an asymmetric overlay.  Read its
    words recursively while keeping the resulting relation PROPOSED.
    """
    if isinstance(value, str):
        text = value.lower()
        for separator in ("-", "_", "/", ",", ";", ":", "(", ")"):
            text = text.replace(separator, " ")
        return {word for word in text.split() if word}
    if isinstance(value, Mapping):
        words: Set[str] = set()
        for item in value.values():
            words.update(_semantic_words(item))
        return words
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        words = set()
        for item in value:
            words.update(_semantic_words(item))
        return words
    return set()


def _positive_evidence_words(value: Any) -> Set[str]:
    """Read only the asserted part of a provenance/evidence record.

    ``breaks_when`` deliberately describes the opposite condition.  Treating
    those words as positive geometry semantics can turn a proposed decorative
    layer into a structural seam (or vice versa).  Model adapters may supply a
    bare string, while the typed completion normally supplies ``basis``.
    """
    if not isinstance(value, Mapping):
        return _semantic_words(value)
    words: Set[str] = set()
    for key in ("basis", "value", "proposal", "description", "note"):
        if key in value:
            words.update(_semantic_words(value.get(key)))
    return words


def _attached(node: Mapping[str, Any]) -> Tuple[str, ...]:
    value = _attribute(node, "attached_to")
    if value is None:
        return ()
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if (isinstance(value, Sequence) and not isinstance(value, (str, bytes))
            and value and all(isinstance(item, str) and item.strip()
                              for item in value)):
        return tuple(item.strip() for item in value)
    raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_ATTACHED_TO",
                   f"{node.get('node_id')} has malformed attached_to",
                   node_id=node.get("node_id"))


def _one_parent(node: Mapping[str, Any]) -> str:
    parents = _attached(node)
    if len(parents) != 1:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS",
            f"{node.get('node_id')} needs exactly one attached_to target",
            node_id=node.get("node_id"), attached_to=list(parents),
        )
    return parents[0]


def _unit(node: Mapping[str, Any]) -> Optional[str]:
    value = _attribute(node, "garment_unit")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _require_unit_compatibility(a: Mapping[str, Any], b: Mapping[str, Any],
                                *, relation: str) -> None:
    a_unit, b_unit = _unit(a), _unit(b)
    if a_unit is not None and b_unit is not None and a_unit != b_unit:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_GARMENT_UNIT_MISMATCH",
            f"{relation} cannot join different garment_unit values",
            source_node_id=a.get("node_id"), source_garment_unit=a_unit,
            target_node_id=b.get("node_id"), target_garment_unit=b_unit,
        )


def _dimension(node: Mapping[str, Any], name: str) -> float:
    dimensions = node.get("dimensions", {})
    if not isinstance(dimensions, Mapping) or name not in dimensions:
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_DIMENSION_MISSING",
                       f"{node.get('node_id')} lacks {name}",
                       node_id=node.get("node_id"), dimension=name)
    return _positive(dimensions[name], field=f"{node.get('node_id')}.{name}")


def _optional_dimension(node: Mapping[str, Any], *names: str) -> Optional[float]:
    dimensions = node.get("dimensions", {})
    if not isinstance(dimensions, Mapping):
        return None
    for name in names:
        if name in dimensions:
            return _positive(dimensions[name],
                             field=f"{node.get('node_id')}.{name}")
    return None


def _port(node: Dict[str, Any], port_id: str, length_cm: float,
          interface: str, *, role: str = "loop") -> None:
    ports = node.setdefault("ports", [])
    if not isinstance(ports, list):
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_PORTS",
                       f"{node.get('node_id')} ports must be an array")
    if any(row.get("port_id") == port_id for row in ports
           if isinstance(row, Mapping)):
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_DUPLICATE_PORT",
                       f"duplicate port {node.get('node_id')}/{port_id}")
    ports.append({
        "port_id": port_id,
        "length_cm": round(length_cm, 6),
        "interface": interface,
        "role": role,
        "layer": int(node.get("layer", 0)),
        "stretch_range": [1.0, 1.0],
    })


def _operation(operation_id: str, kind: str, source_node: str,
               source_port: str, target_node: str, target_port: str,
               *, basis: str, breaks_when: str,
               parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    params = {
        "state": PROPOSED,
        "authority": PROPOSED,
        "basis": basis,
        "breaks_when": breaks_when,
        "relation_source": "MODEL_SUPPLIED_ATTACHED_TO_PLUS_TYPED_RULE",
        "not_observed_from_image": True,
    }
    if parameters:
        params.update(copy.deepcopy(dict(parameters)))
    return {
        "operation_id": operation_id,
        "kind": kind,
        "source": {"node_id": source_node, "port_id": source_port},
        "target": {"node_id": target_node, "port_id": target_port},
        "parameters": params,
        "prerequisites": [],
    }


def _bind_ornament_artifacts(candidate: Mapping[str, Any],
                             nodes: Mapping[str, Dict[str, Any]], *,
                             topology_structure_digest: str
                             ) -> Optional[Dict[str, Any]]:
    """Validate and bind completion's real ornament artifacts to this graph.

    Ornament polygons are not ``PrimitiveKind`` nodes.  They remain an
    explicit candidate extension whose garment-facing ports resolve only to
    model-supplied target node ids.  This boundary never chooses an attachment
    from image position, names, or proximity.
    """
    raw = candidate.get("ornament_artifacts")
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or raw.get("schema") != ORNAMENT_ARTIFACT_SCHEMA:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_SCHEMA",
            "ornament_artifacts must use the completion artifact schema",
            schema=(raw.get("schema") if isinstance(raw, Mapping) else None),
        )
    bundle = _json_copy(dict(raw), field="candidate.ornament_artifacts")
    if (bundle.get("state") != PROPOSED
            or bundle.get("source_structure_digest")
            != candidate.get("structure_digest")):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_BINDING",
            "ornament artifacts must remain PROPOSED and bind to the completion structure digest",
            artifact_state=bundle.get("state"),
            artifact_structure_digest=bundle.get("source_structure_digest"),
            candidate_structure_digest=candidate.get("structure_digest"),
        )
    authority = bundle.get("authority", {})
    if (not isinstance(authority, Mapping)
            or authority.get("highest_state") != PROPOSED
            or authority.get("observed") is not False
            or authority.get("approved") is not False
            or authority.get("image_promoted_to_observed") is not False):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_AUTHORITY_ESCALATION",
            "ornament artifacts may not become observed facts or approvals",
            authority=authority,
        )

    collections: Dict[str, List[Dict[str, Any]]] = {}
    for field in ("pattern_pieces", "attachment_ports", "seam_intents"):
        values = bundle.get(field)
        if (not isinstance(values, Sequence)
                or isinstance(values, (str, bytes))
                or any(not isinstance(value, Mapping) for value in values)):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_ARTIFACTS",
                f"ornament {field} must be an array of objects", field=field,
            )
        collections[field] = [copy.deepcopy(dict(value)) for value in values]
    pieces = collections["pattern_pieces"]
    ports = collections["attachment_ports"]
    intents = collections["seam_intents"]
    identifiers: Dict[str, Set[str]] = {}
    for field, values, key in (
            ("pattern_pieces", pieces, "piece_id"),
            ("attachment_ports", ports, "port_id"),
            ("seam_intents", intents, "intent_id")):
        ids = [value.get(key) for value in values]
        if (any(not isinstance(identifier, str) or not identifier for identifier in ids)
                or len(ids) != len(set(ids))):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_ARTIFACT_ID",
                f"ornament {field} ids must be non-empty and unique",
                field=field, identifiers=ids,
            )
        identifiers[field] = set(ids)
    piece_ids = identifiers["pattern_pieces"]
    port_ids = identifiers["attachment_ports"]

    for piece in pieces:
        geometry_authority = piece.get("geometry_authority", {})
        if (piece.get("state") != PROPOSED
                or not isinstance(geometry_authority, Mapping)
                or geometry_authority.get("state") != PROPOSED
                or geometry_authority.get("observed") is not False):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_AUTHORITY_ESCALATION",
                "ornament pattern geometry must remain proposal-only",
                piece_id=piece.get("piece_id"),
            )

    unresolved_bindings: List[Dict[str, Any]] = []
    resolved_bindings: List[Dict[str, Any]] = []
    binding_by_target: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {}
    for port in ports:
        if (port.get("state") != PROPOSED or port.get("observed") is not False
                or port.get("owner_piece_id") not in piece_ids):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_AUTHORITY_ESCALATION",
                "ornament attachment ports must remain proposal-only and name an ornament piece",
                port_id=port.get("port_id"),
            )
        target = port.get("target")
        if target is None:
            unresolved_bindings.append({
                "port_id": port["port_id"],
                "state": "REVIEW",
                "code": "REVIEW_ORNAMENT_ATTACHMENT_REQUIRED",
                "why": "no garment target was supplied; topology did not guess one",
            })
            port["topology_binding"] = copy.deepcopy(unresolved_bindings[-1])
            continue
        if not isinstance(target, Mapping):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_TARGET",
                "an ornament attachment target must be an object or null",
                port_id=port.get("port_id"),
            )
        target_id = target.get("target_piece_id")
        target_port_id = target.get("target_port_id")
        if (target.get("state") != PROPOSED
                or target.get("observed") is not False):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_AUTHORITY_ESCALATION",
                "an image-derived ornament target must remain PROPOSED",
                port_id=port.get("port_id"), target=target,
            )
        if not isinstance(target_id, str) or not target_id:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_TARGET",
                "an ornament attachment needs one explicit target node id",
                port_id=port.get("port_id"), target=target,
            )
        if target_id not in nodes:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_TARGET_MISSING",
                f"ornament port {port.get('port_id')} references unknown {target_id}",
                port_id=port.get("port_id"), target_node_id=target_id,
            )
        structural_port_ids = {
            value.get("port_id") for value in nodes[target_id].get("ports", [])
            if isinstance(value, Mapping)
        }
        exact_port_resolved = (
            isinstance(target_port_id, str) and target_port_id in structural_port_ids)
        binding = {
            "port_id": port["port_id"],
            "state": PROPOSED,
            "target_node_id": target_id,
            "requested_target_port_id": target_port_id,
            "target_node_resolved": True,
            "target_port_resolved": exact_port_resolved,
            "target_port_state": (PROPOSED if exact_port_resolved else "REVIEW"),
            "observed": False,
            "basis": "model-supplied ornament attachment target plus exact node lookup",
            "breaks_when": "the ornament target, target port, or structure candidate changes",
        }
        port["topology_binding"] = copy.deepcopy(binding)
        resolved_bindings.append(copy.deepcopy(binding))
        binding_by_target[(target_id, target_port_id)] = binding

    orders = [intent.get("order") for intent in intents]
    if orders != list(range(1, len(intents) + 1)):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_SEAM_ORDER",
            "flattened ornament seam intent order must be contiguous",
            orders=orders,
        )
    for intent in intents:
        if intent.get("state") != PROPOSED:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_AUTHORITY_ESCALATION",
                "ornament seam intents must remain proposal-only",
                intent_id=intent.get("intent_id"),
            )
        for side in ("source", "target"):
            address = intent.get(side)
            if address is None:
                continue
            if not isinstance(address, Mapping):
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_SEAM_ADDRESS",
                    "ornament seam addresses must be objects or null",
                    intent_id=intent.get("intent_id"), side=side,
                )
            if "piece_id" in address and address.get("piece_id") not in piece_ids:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_SEAM_PIECE_MISSING",
                    "ornament seam intent references a missing pattern piece",
                    intent_id=intent.get("intent_id"), side=side,
                    piece_id=address.get("piece_id"),
                )
            if "port_id" in address and address.get("port_id") not in port_ids:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_SEAM_PORT_MISSING",
                    "ornament seam intent references a missing attachment port",
                    intent_id=intent.get("intent_id"), side=side,
                    port_id=address.get("port_id"),
                )
            if "target_piece_id" in address:
                key = (address.get("target_piece_id"),
                       address.get("target_port_id"))
                if key not in binding_by_target:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_SEAM_TARGET_MISSING",
                        "garment attachment intent has no matching resolved port",
                        intent_id=intent.get("intent_id"), target=dict(address),
                    )
                intent["topology_binding"] = copy.deepcopy(binding_by_target[key])

    expected_order = bundle.get("construction_order")
    if expected_order != [intent["intent_id"] for intent in intents]:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_ORNAMENT_CONSTRUCTION_ORDER",
            "ornament construction order does not match its seam intents",
        )
    bundle.update({
        "candidate_id": candidate.get("candidate_id"),
        "topology_structure_digest": topology_structure_digest,
        "pattern_pieces": pieces,
        "attachment_ports": ports,
        "seam_intents": intents,
        "topology_binding": {
            "state": PROPOSED,
            "resolved": resolved_bindings,
            "unresolved": unresolved_bindings,
            "all_targets_resolved": not unresolved_bindings,
            "image_attachment_inference": False,
            "name_based_attachment_inference": False,
            "authority_granted": False,
        },
    })
    bundle.pop("digest", None)
    bundle["topology_digest"] = garment_structure.semantic_digest(bundle)
    return bundle


def _candidate_geometry_identity(
        *, structure_digest: str,
        nodes: Mapping[str, Dict[str, Any]],
        operations: Sequence[Mapping[str, Any]],
        ornament_artifacts: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Create one proposal-only renderer identity for all candidate geometry.

    The structural graph digest already distinguishes primitive dimensions and
    typed LAYER/JOIN/GATHER topology, but ornaments intentionally live outside
    that graph.  A renderer or cache keyed only by ``structure_digest`` could
    therefore collapse two candidates that differ solely by repeated surface
    decoration.  Bind the existing structural digest to the already
    materialized ornament polygons and attachment geometry without inventing
    placement, rear geometry, material, or a formed 3D result.
    """
    layer_operation_ids = sorted(
        str(operation.get("operation_id"))
        for operation in operations
        if operation.get("kind") == "LAYER"
    )
    overlay_node_ids = {
        str(node_id) for node_id, node in nodes.items()
        if node.get("kind") == "OVERLAY"
    }
    for operation in operations:
        parameters = operation.get("parameters", {})
        if (operation.get("kind") == "LAYER"
                and isinstance(parameters, Mapping)
                and parameters.get("construction_role")
                == "PROPOSED_GORE_OVERLAY"):
            source = operation.get("source", {})
            if isinstance(source, Mapping):
                source_id = source.get("node_id")
                if isinstance(source_id, str) and source_id:
                    overlay_node_ids.add(source_id)

    asymmetric_attachment_node_ids = []
    for node_id, node in nodes.items():
        semantics = (
            _tokens(_attribute(node, "shape"))
            | _tokens(_attribute(node, "side"))
            | _tokens(_attribute(node, "placement"))
            | _positive_evidence_words(_attribute(node, "visible_basis"))
        )
        if (_attached(node)
                and semantics & {"asymmetric", "asymmetrical"}):
            asymmetric_attachment_node_ids.append(str(node_id))

    ornament_pieces: List[Dict[str, Any]] = []
    ornament_ports: List[Dict[str, Any]] = []
    if ornament_artifacts is not None:
        ornament_pieces = [
            copy.deepcopy(dict(piece))
            for piece in ornament_artifacts.get("pattern_pieces", [])
            if isinstance(piece, Mapping)
        ]
        ornament_ports = [
            copy.deepcopy(dict(port))
            for port in ornament_artifacts.get("attachment_ports", [])
            if isinstance(port, Mapping)
        ]

    geometry_payload = {
        "structure_digest": structure_digest,
        "ornament_pattern_pieces": ornament_pieces,
        "ornament_attachment_ports": ornament_ports,
    }
    return {
        "schema": CANDIDATE_GEOMETRY_SCHEMA,
        "state": PROPOSED,
        "digest": garment_structure.semantic_digest(geometry_payload),
        "structure_digest": structure_digest,
        "layer_operation_ids": layer_operation_ids,
        "overlay_node_ids": sorted(overlay_node_ids),
        "asymmetric_attachment_node_ids": sorted(
            asymmetric_attachment_node_ids),
        "decorative_surface_instances": [
            {
                "piece_id": piece.get("piece_id"),
                "role": piece.get("role"),
                "copy_index": piece.get("copy_index"),
                "layer": piece.get("layer"),
                "state": PROPOSED,
            }
            for piece in ornament_pieces
        ],
        "candidate_local": True,
        "formed_3d_geometry_claimed": False,
        "rear_geometry_observed": False,
        "material_observed": False,
        "authority_granted": False,
    }


def _length_match(a: float, b: float, *, operation_id: str) -> None:
    difference = abs(a - b)
    if difference > _TOLERANCE_CM:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_JOIN_LENGTH_MISMATCH",
            f"{operation_id} differs by {difference:.6g}cm",
            operation_id=operation_id, source_cm=a, target_cm=b,
            tolerance_cm=_TOLERANCE_CM,
        )


def _join(nodes: Mapping[str, Dict[str, Any]], operations: List[Dict[str, Any]],
          parent_id: str, child_id: str, interface: str,
          parent_length: float, child_length: float, *, suffix: str = "",
          parameters: Optional[Mapping[str, Any]] = None) -> None:
    operation_id = f"join-{interface}-{parent_id}-{child_id}{suffix}"
    _length_match(parent_length, child_length, operation_id=operation_id)
    parent_port = f"{interface}-to-{child_id}{suffix}"
    child_port = f"{interface}-to-{parent_id}{suffix}"
    _port(nodes[parent_id], parent_port, parent_length, interface)
    _port(nodes[child_id], child_port, child_length, interface)
    operations.append(_operation(
        operation_id, "JOIN", child_id, child_port, parent_id, parent_port,
        basis=(
            f"{child_id}.attached_to explicitly names {parent_id}; typed "
            f"{interface} boundaries agree within {_TOLERANCE_CM}cm"
        ),
        breaks_when=(
            "attached_to changes, garment units diverge, or either boundary "
            "length is corrected"
        ),
        parameters=parameters,
    ))


def _sleeve_gather_provenance(node: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the proposal-only truth boundary for a sleeve gather.

    The topology layer may verify geometry, but it may not promote a model
    proposal to an observation, approval, or manufacturing claim.  Preserve
    the supplied provenance verbatim after checking that it is finite JSON and
    does not contradict that boundary.
    """
    state = _attribute(node, "sleeve_join_state")
    if not isinstance(state, str) or state.strip().upper() != PROPOSED:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_AUTHORITY",
            "sleeve GATHER relation must remain explicitly PROPOSED",
            node_id=node.get("node_id"), field="sleeve_join_state",
            claimed_state=state,
        )
    raw = _attribute(node, "sleeve_join_provenance")
    if not isinstance(raw, Mapping):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_PROVENANCE",
            "sleeve GATHER requires mapping sleeve_join_provenance",
            node_id=node.get("node_id"),
            field="sleeve_join_provenance",
        )
    provenance = _json_copy(
        dict(raw), field=f"{node.get('node_id')}.sleeve_join_provenance")
    for field in ("state", "verdict"):
        claimed = provenance.get(field)
        if (claimed is not None and (
                not isinstance(claimed, str)
                or claimed.strip().upper() != PROPOSED)):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_AUTHORITY",
                "sleeve gather provenance may not elevate proposal authority",
                node_id=node.get("node_id"),
                field=f"sleeve_join_provenance.{field}",
                claimed_state=claimed,
            )
    authority = provenance.get("authority")
    allowed_authorities = {PROPOSED, "PROPOSED_RELATION_DERIVED"}
    if (authority is not None and (
            not isinstance(authority, str)
            or authority.strip().upper() not in allowed_authorities)):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_AUTHORITY",
            "sleeve gather provenance authority must remain a proposal or "
            "a relation-derived proposal",
            node_id=node.get("node_id"),
            field="sleeve_join_provenance.authority",
            claimed_state=authority,
            allowed_states=sorted(allowed_authorities),
        )
    for field in (
            "observed", "approved", "answer", "authority_granted",
            "manufacturing_ready", "manufacturing_certified"):
        if field in provenance and provenance[field] is not False:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_AUTHORITY",
                "sleeve gather provenance may not claim observation, "
                "approval, or manufacturing readiness",
                node_id=node.get("node_id"),
                field=f"sleeve_join_provenance.{field}",
                claimed_value=provenance[field],
            )
    if ("dimensions_changed" in provenance
            and provenance["dimensions_changed"] is not False):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_PROVENANCE",
            "sleeve gather provenance must not claim dimension edits",
            node_id=node.get("node_id"),
            field="sleeve_join_provenance.dimensions_changed",
            claimed_value=provenance["dimensions_changed"],
        )
    return provenance


def _waist_length(node: Mapping[str, Any], *, child: bool) -> float:
    kind = str(node.get("kind"))
    if kind == "BODY_SHELL":
        value = _optional_dimension(
            node, "bottom_circumference_cm", "waist_circumference_cm",
            "circumference_cm")
        if value is not None:
            return value
    if kind in ("FLARE", "FRUSTUM"):
        return _dimension(node, "top_circumference_cm")
    if kind == "TUBE":
        return _dimension(node, "circumference_cm")
    raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_WAIST_BOUNDARY",
                   f"{node.get('node_id')} has no typed waist boundary",
                   node_id=node.get("node_id"), child=child)


def _neck_child_length(node: Mapping[str, Any]) -> Tuple[float, bool]:
    if node.get("kind") == "COLLAR":
        return _dimension(node, "length_cm"), False
    if node.get("kind") == "HOOD":
        explicit = _optional_dimension(node, "neck_edge_cm")
        if explicit is not None:
            return explicit, False
        # HOOD.width_cm is the only required opening-axis measure in
        # garment.structure.v1.  Using it is a typed preview approximation and
        # is recorded as such, never as an observed neckline.
        return _dimension(node, "width_cm"), True
    raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_NECK_BOUNDARY",
                   f"{node.get('node_id')} is not a neck-attached primitive")


def _ruffle_target(node: Mapping[str, Any], placement: Any) -> Tuple[float, str]:
    kind = str(node.get("kind"))
    text = json.dumps(placement, sort_keys=True, ensure_ascii=False).lower()
    if kind == "BODY_SHELL":
        return _waist_length(node, child=False), "body-boundary"
    if kind in ("FLARE", "FRUSTUM"):
        if any(token in text for token in ("hem", "bottom", "lower")):
            return _dimension(node, "bottom_circumference_cm"), "hem"
        if any(token in text for token in ("waist", "top", "upper")):
            return _dimension(node, "top_circumference_cm"), "waist"
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_GATHER_TARGET_AMBIGUOUS",
            f"ruffle placement does not select top or bottom of {node.get('node_id')}",
            target_node_id=node.get("node_id"), placement=placement,
        )
    if kind == "TUBE":
        return _dimension(node, "circumference_cm"), "tube-loop"
    if kind == "SLEEVE":
        if any(token in text for token in ("cuff", "wrist", "lower")):
            return _dimension(node, "cuff_circumference_cm"), "cuff"
        if any(token in text for token in ("upper", "cap", "armhole")):
            return _dimension(node, "upper_circumference_cm"), "upper-sleeve"
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_GATHER_TARGET_AMBIGUOUS",
            f"ruffle placement does not select a sleeve boundary",
            target_node_id=node.get("node_id"), placement=placement,
        )
    if kind == "OVERLAY":
        return _dimension(node, "width_cm"), "overlay-edge"
    if kind in ("BAND", "COLLAR"):
        return _dimension(node, "length_cm"), "long-edge"
    if kind == "GORE":
        if any(token in text for token in ("hem", "bottom", "lower")):
            return _dimension(node, "bottom_width_cm"), "gore-bottom"
        if any(token in text for token in ("waist", "top", "upper")):
            return _dimension(node, "top_width_cm"), "gore-top"
    raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_GATHER_TARGET_UNSUPPORTED",
                   f"{node.get('node_id')} has no supported gather boundary",
                   target_node_id=node.get("node_id"), target_kind=kind)


def _band_target(node: Mapping[str, Any], placement: Any) -> Tuple[float, str]:
    """Resolve a non-gathered band to one explicit sewing boundary.

    Unlike a ruffle, a waistband/cuff/neckband must already have the same
    sewing length as its target.  Ambiguous placement is refused rather than
    silently choosing an edge.
    """
    kind = str(node.get("kind"))
    text = json.dumps(placement, sort_keys=True, ensure_ascii=False).lower()
    if kind == "BODY_SHELL":
        is_neck = any(token in text for token in ("neck", "collar", "neckline"))
        is_waist = any(token in text for token in
                       ("waist", "belt", "sash", "bottom", "hem"))
        if is_neck and is_waist:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_BAND_TARGET_CONFLICT",
                "band placement/shape/detail_role select both neck and waist",
                target_node_id=node.get("node_id"), placement=placement,
            )
        if is_neck:
            value = _optional_dimension(node, "neck_circumference_cm")
            if value is None:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_NECK_BOUNDARY",
                    f"{node.get('node_id')} has no typed neckline for a band",
                    target_node_id=node.get("node_id"))
            return value, "neck"
        if is_waist:
            return _waist_length(node, child=False), "waist"
    if kind in ("FLARE", "FRUSTUM"):
        is_hem = any(token in text for token in ("hem", "bottom", "lower"))
        is_waist = any(token in text for token in ("waist", "top", "upper"))
        if is_hem and is_waist:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_BAND_TARGET_CONFLICT",
                "band placement/shape/detail_role select both hem and waist",
                target_node_id=node.get("node_id"), placement=placement,
            )
        if is_hem:
            return _dimension(node, "bottom_circumference_cm"), "hem"
        if is_waist:
            return _dimension(node, "top_circumference_cm"), "waist"
    if kind == "TUBE":
        return _dimension(node, "circumference_cm"), "tube-loop"
    if kind == "SLEEVE":
        is_cuff = any(token in text for token in ("cuff", "wrist", "lower"))
        is_upper = any(token in text for token in ("upper", "cap", "armhole"))
        if is_cuff and is_upper:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_BAND_TARGET_CONFLICT",
                "band placement/shape/detail_role select both cuff and upper sleeve",
                target_node_id=node.get("node_id"), placement=placement,
            )
        if is_cuff:
            return _dimension(node, "cuff_circumference_cm"), "cuff"
        if is_upper:
            return _dimension(node, "upper_circumference_cm"), "upper-sleeve"
    if kind == "OVERLAY":
        return _dimension(node, "width_cm"), "overlay-edge"
    if kind in ("BAND", "COLLAR"):
        return _dimension(node, "length_cm"), "long-edge"
    raise _Refusal(
        "UNKNOWN_PARTS_TOPOLOGY_BAND_TARGET_AMBIGUOUS",
        f"band placement does not select a supported boundary on {node.get('node_id')}",
        target_node_id=node.get("node_id"), target_kind=kind,
        placement=placement)


def _is_trouser_leg(node: Mapping[str, Any]) -> bool:
    return bool((_tokens(_attribute(node, "shape"))
                 | _tokens(_attribute(node, "detail_role"))) & _TROUSER_ROLES)


def _is_trouser_gusset(node: Mapping[str, Any]) -> bool:
    if node.get("kind") != "GUSSET":
        return False
    tokens = _tokens(_attribute(node, "shape")) | _tokens(
        _attribute(node, "detail_role"))
    return bool(tokens & {"trouser", "trousers", "trouser_gusset", "crotch_gusset"})


def _waist_stack_field(node: Mapping[str, Any], name: str) -> Any:
    """Read one explicit stack field without guessing a missing value.

    Current parts-IR completion preserves proposal extensions inside
    ``waist_join_provenance``. Direct attributes are also accepted for callers
    that already hold a completed structure node. If both representations are
    present they must agree exactly; this boundary never chooses between
    conflicting model proposals.
    """
    values: List[Any] = []
    direct = _attribute(node, name)
    if direct is not None:
        values.append(direct)
    provenance = _attribute(node, "waist_join_provenance")
    if isinstance(provenance, Mapping):
        if provenance.get(name) is not None:
            values.append(provenance[name])
        nested = provenance.get("waist_stack")
        if isinstance(nested, Mapping) and nested.get(name) is not None:
            values.append(nested[name])
    if not values:
        return None
    canonical = json.dumps(values[0], sort_keys=True, ensure_ascii=False,
                           allow_nan=False)
    if any(json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) != canonical for value in values[1:]):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_METADATA_CONFLICT",
            "direct and provenance waist-stack metadata disagree",
            node_id=node.get("node_id"), field=name, values=values,
        )
    return copy.deepcopy(values[0])


def _waist_stack_metadata(node: Mapping[str, Any], parent_id: str
                          ) -> Optional[Dict[str, Any]]:
    field_names = (
        "waist_stack_state", "waist_stack_parent", "waist_stack_id",
        "waist_stack_order", "waist_stack_construction_mode",
    )
    raw = {name: _waist_stack_field(node, name) for name in field_names}
    if all(value is None for value in raw.values()):
        return None
    missing = [name for name, value in raw.items() if value is None]
    if missing:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_METADATA",
            "every layered waist child needs the complete typed stack contract",
            node_id=node.get("node_id"), field="waist_stack_contract",
            missing=missing,
        )
    state = raw["waist_stack_state"]
    if not isinstance(state, str) or state.strip().upper() != PROPOSED:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_AUTHORITY",
            "waist-stack metadata must remain explicitly PROPOSED",
            node_id=node.get("node_id"), field="waist_stack_state",
            claimed_state=state,
        )
    stack_parent = raw["waist_stack_parent"]
    if not isinstance(stack_parent, str) or stack_parent.strip() != parent_id:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_PARENT",
            "waist_stack_parent must exactly match the attached BODY_SHELL",
            node_id=node.get("node_id"), field="waist_stack_parent",
            expected_parent=parent_id,
            waist_stack_parent=stack_parent,
        )
    stack_id = raw["waist_stack_id"]
    if (not isinstance(stack_id, str)
            or _WAIST_STACK_ID.fullmatch(stack_id.strip()) is None):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_ID",
            "waist_stack_id must be a stable bounded identifier",
            node_id=node.get("node_id"), field="waist_stack_id",
            waist_stack_id=stack_id,
        )
    order = raw["waist_stack_order"]
    if (isinstance(order, bool) or not isinstance(order, int)
            or not 1 <= order <= _MAX_WAIST_STACK_LAYERS):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_ORDER",
            "waist_stack_order must be a positive bounded integer",
            node_id=node.get("node_id"), field="waist_stack_order",
            waist_stack_order=order,
            maximum=_MAX_WAIST_STACK_LAYERS,
        )
    mode = raw["waist_stack_construction_mode"]
    mode = mode.strip().upper() if isinstance(mode, str) else None
    if mode not in _WAIST_STACK_CONSTRUCTION_MODES:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_MODE",
            "waist_stack_construction_mode must be JOIN or GATHER",
            node_id=node.get("node_id"),
            field="waist_stack_construction_mode", construction_mode=raw[
                "waist_stack_construction_mode"],
        )
    existing_mode = str(_attribute(node, "waist_join_mode") or "JOIN").upper()
    attachment_relation = str(
        _attribute(node, "attachment_relation") or "").strip().upper()
    if attachment_relation == "LAYER" and _attribute(
            node, "waist_join_mode") is None:
        existing_mode = "LAYER"
    if mode != existing_mode:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_MODE",
            "waist-stack construction mode conflicts with the typed waist rule",
            node_id=node.get("node_id"),
            field="waist_stack_construction_mode", construction_mode=mode,
            waist_join_mode=existing_mode,
        )
    result = {
        "state": PROPOSED,
        "parent_node_id": parent_id,
        "stack_id": stack_id.strip(),
        "order": order,
        "construction_mode": mode,
        "dimensions_changed": False,
        "authority_granted": False,
    }
    role = _waist_stack_field(node, "waist_stack_role")
    if role is not None:
        if not isinstance(role, str) or not role.strip():
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_ROLE",
                "waist_stack_role must be a non-empty typed role",
                node_id=node.get("node_id"), field="waist_stack_role",
                waist_stack_role=role,
            )
        result["role"] = role.strip().upper()
    return result


def _ownership_contract(node: Mapping[str, Any], parent_id: str, *,
                        required_relation: str,
                        required_layer_role: str,
                        required_attachment_port: str
                        ) -> Optional[Dict[str, Any]]:
    """Validate an optional model-supplied ownership edge.

    The contract is deliberately all-or-nothing.  It can preserve an explicit
    parent/owner/layer/attachment proposal, but it cannot choose a likely
    owner from ids, names, geometry, or proximity.
    """
    names = (
        "owner_node_id", "ownership_state", "layer_role",
        "attachment_port",
    )
    raw = {name: _attribute(node, name) for name in names}
    if all(value is None for value in raw.values()):
        return None
    missing = [name for name, value in raw.items() if value is None]
    relation = _attribute(node, "attachment_relation")
    if relation is None:
        missing.append("attachment_relation")
    if missing:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OWNERSHIP_CONTRACT",
            "typed ownership needs parent, owner, layer role, attachment port and relation",
            node_id=node.get("node_id"), field="ownership_contract",
            missing=sorted(missing),
        )
    owner = raw["owner_node_id"]
    if not isinstance(owner, str) or owner.strip() != parent_id:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OWNER_MISMATCH",
            "owner_node_id must exactly match the explicit attached_to parent",
            node_id=node.get("node_id"), expected_owner=parent_id,
            owner_node_id=owner,
        )
    state = raw["ownership_state"]
    if not isinstance(state, str) or state.strip().upper() != PROPOSED:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OWNERSHIP_AUTHORITY",
            "ownership_state must remain explicitly PROPOSED",
            node_id=node.get("node_id"), claimed_state=state,
        )
    normalized_relation = (
        relation.strip().upper() if isinstance(relation, str) else "")
    if normalized_relation != required_relation:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OWNERSHIP_RELATION",
            "attachment_relation conflicts with the typed ownership role",
            node_id=node.get("node_id"), expected_relation=required_relation,
            attachment_relation=relation,
        )
    layer_role = raw["layer_role"]
    normalized_layer_role = (
        layer_role.strip().upper() if isinstance(layer_role, str) else "")
    if normalized_layer_role != required_layer_role:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_LAYER_ROLE",
            "layer_role conflicts with the typed ownership role",
            node_id=node.get("node_id"),
            expected_layer_role=required_layer_role, layer_role=layer_role,
        )
    attachment_port = raw["attachment_port"]
    normalized_port = (
        attachment_port.strip().upper()
        if isinstance(attachment_port, str) else "")
    if normalized_port != required_attachment_port:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_ATTACHMENT_PORT",
            "attachment_port conflicts with the typed ownership role",
            node_id=node.get("node_id"),
            expected_attachment_port=required_attachment_port,
            attachment_port=attachment_port,
        )
    return {
        "state": PROPOSED,
        "parent_node_id": parent_id,
        "owner_node_id": parent_id,
        "layer_role": required_layer_role,
        "attachment_relation": required_relation,
        "attachment_port": required_attachment_port,
        "authority_granted": False,
        "observed": False,
        "approved": False,
    }


def _outer_waist_overlay_contract(
        node: Mapping[str, Any], nodes: Mapping[str, Dict[str, Any]],
        ) -> Optional[Dict[str, Any]]:
    """Resolve only an explicit proposal-only outer waist overlay contract."""
    role = _attribute(node, "layer_role")
    stack_role = _waist_stack_field(node, "waist_stack_role")
    relation = str(
        _attribute(node, "attachment_relation") or "").strip().upper()
    lower_layer_signal = (
        node.get("kind") in {"FLARE", "FRUSTUM"} and relation == "LAYER")
    explicitly_outer = (
        isinstance(role, str) and role.strip().upper() == "OUTER_OVERLAY")
    explicitly_stack_outer = (
        isinstance(stack_role, str)
        and stack_role.strip().upper() == "OUTER_OVERLAY")
    if not (lower_layer_signal or explicitly_outer or explicitly_stack_outer):
        return None
    if node.get("kind") not in _OUTER_WAIST_OVERLAY_KINDS:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OUTER_OVERLAY_KIND",
            "typed OUTER_OVERLAY is not supported for this primitive kind",
            node_id=node.get("node_id"), kind=node.get("kind"),
        )
    parent_id = _one_parent(node)
    parent = nodes[parent_id]
    if parent.get("kind") != "BODY_SHELL":
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OUTER_OVERLAY_PARENT",
            "an outer waist overlay must explicitly target its BODY_SHELL waist owner",
            node_id=node.get("node_id"), target_id=parent_id,
            target_kind=parent.get("kind"),
        )
    _require_unit_compatibility(
        node, parent, relation="outer waist overlay ownership")
    ownership = _ownership_contract(
        node, parent_id, required_relation="LAYER",
        required_layer_role="OUTER_OVERLAY",
        required_attachment_port="WAIST_STACK")
    if ownership is None:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OWNERSHIP_CONTRACT",
            "an outer waist overlay needs the complete proposal-only ownership contract",
            node_id=node.get("node_id"), field="ownership_contract",
        )
    stack = _waist_stack_metadata(node, parent_id)
    if stack is None:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_METADATA",
            "an outer waist overlay needs a complete typed waist-stack contract",
            node_id=node.get("node_id"), field="waist_stack_contract",
        )
    if stack["construction_mode"] != "LAYER" or stack.get("role") != (
            "OUTER_OVERLAY"):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_ROLE",
            "outer overlay waist metadata must use role=OUTER_OVERLAY and construction_mode=LAYER",
            node_id=node.get("node_id"), field="waist_stack_role",
            waist_stack_role=stack.get("role"),
            construction_mode=stack.get("construction_mode"),
        )
    child_layer = node.get("layer")
    parent_layer = parent.get("layer")
    layer_is_higher = (
        isinstance(child_layer, (int, float))
        and not isinstance(child_layer, bool)
        and isinstance(parent_layer, (int, float))
        and not isinstance(parent_layer, bool)
        and math.isfinite(float(child_layer))
        and math.isfinite(float(parent_layer))
        and float(child_layer) > float(parent_layer))
    if not layer_is_higher:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_OUTER_OVERLAY_LAYER_ORDER",
            "an OUTER_OVERLAY must have a strictly higher layer than its waist owner",
            node_id=node.get("node_id"), target_id=parent_id,
            child_layer=child_layer, parent_layer=parent_layer,
        )
    return {
        "parent_node_id": parent_id,
        "source_layer": child_layer,
        "target_layer": parent_layer,
        "ownership": ownership,
        "waist_stack": stack,
    }


def _validate_parallel_waist_stack(
        nodes: Mapping[str, Dict[str, Any]], parent_id: str,
        child_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Accept only an explicitly typed, bounded parallel waist stack."""
    if len(child_ids) > _MAX_WAIST_STACK_LAYERS:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_SIZE",
            "parallel waist stack exceeds the bounded layer count",
            parent_node_id=parent_id, child_node_ids=list(child_ids),
            maximum=_MAX_WAIST_STACK_LAYERS,
        )
    relations = {parent_id: list(child_ids)}
    try:
        metadata = {
            child_id: _waist_stack_metadata(nodes[child_id], parent_id)
            for child_id in sorted(child_ids)
        }
    except _Refusal as refusal:
        refusal.detail.setdefault("relations", relations)
        raise
    if all(value is None for value in metadata.values()):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_MULTIPLE_WAIST_CHILDREN",
            "multiple lower parts target one waist without a typed trouser topology or waist-stack contract",
            relations=relations,
        )
    missing = [child_id for child_id, value in metadata.items()
               if value is None]
    if missing:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_METADATA",
            "every ambiguous waist child must carry the same explicit stack contract",
            parent_node_id=parent_id, field="waist_stack_contract",
            missing_child_node_ids=missing, relations=relations,
        )
    typed = {child_id: value for child_id, value in metadata.items()
             if value is not None}
    stack_ids = {value["stack_id"] for value in typed.values()}
    if len(stack_ids) != 1:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_ID",
            "all children on one parallel waist stack must share one stable id",
            parent_node_id=parent_id, field="waist_stack_id",
            stack_ids=sorted(stack_ids), relations=relations,
        )
    orders = [value["order"] for value in typed.values()]
    if len(orders) != len(set(orders)):
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_WAIST_STACK_ORDER",
            "parallel waist-stack children need unique positive orders",
            parent_node_id=parent_id, field="waist_stack_order",
            waist_stack_orders=sorted(orders), relations=relations,
        )
    return typed


def _trouser_group_topology(nodes: Mapping[str, Dict[str, Any]],
                            operations: List[Dict[str, Any]],
                            consumed: Set[str], *,
                            legs: Sequence[Dict[str, Any]],
                            gussets: Sequence[Dict[str, Any]],
                            group_key: Tuple[Optional[str], int]) -> None:
    leg_ids = {str(node["node_id"]) for node in legs}
    if len(legs) != 2 or len(gussets) != 1:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_INCOMPLETE",
            "each trouser garment_unit/layer requires exactly two typed TUBE legs and one typed GUSSET",
            garment_unit=group_key[0], layer=group_key[1],
            leg_node_ids=[node.get("node_id") for node in legs],
            gusset_node_ids=[node.get("node_id") for node in gussets],
        )
    by_side = {str(_attribute(node, "side") or "").strip().lower(): node
               for node in legs}
    if set(by_side) != {"left", "right"}:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_SIDE",
            "trouser TUBE nodes must explicitly identify left and right sides",
            sides=sorted(by_side),
        )
    gusset = gussets[0]
    if str(_attribute(gusset, "side") or "").strip().lower() != "center":
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_TROUSERS_SIDE",
                       "the trouser GUSSET must explicitly use side=center",
                       gusset_node_id=gusset.get("node_id"))
    if set(_attached(gusset)) != leg_ids:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_GUSSET_ATTACHMENT",
            "the trouser GUSSET attached_to must name both leg node ids",
            expected=sorted(leg_ids), actual=sorted(_attached(gusset)),
        )
    parent_lists = [_attached(node) for node in legs]
    parent_id: Optional[str]
    if all(not parents for parents in parent_lists):
        # A separately wearable pair has no upper-garment parent.  The open
        # waist remains an explicit unclosed boundary for a later waistband or
        # facing operation; it must not be invented as a BODY_SHELL.
        parent_id = None
    elif all(len(parents) == 1 for parents in parent_lists):
        parent_ids = {parents[0] for parents in parent_lists}
        if len(parent_ids) != 1:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_PARENT",
                "both attached trouser legs must name the same BODY_SHELL",
                parent_ids=sorted(parent_ids),
            )
        parent_id = next(iter(parent_ids))
        if parent_id not in nodes or nodes[parent_id].get("kind") != "BODY_SHELL":
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_PARENT",
                "an attached trouser pair must target a BODY_SHELL; omit both leg attachments for standalone trousers",
                parent_id=parent_id,
            )
    else:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_PARENT",
            "trouser legs must either both be standalone or both attach to one BODY_SHELL",
            attached_to=[list(parents) for parents in parent_lists],
        )
    unit_nodes = [*legs, gusset]
    if parent_id is not None:
        unit_nodes.append(nodes[parent_id])
    units = {_unit(node) for node in unit_nodes}
    if None in units or len(units) != 1:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_GARMENT_UNIT",
            "the trouser unit (and BODY_SHELL when attached) needs one explicit shared garment_unit",
            garment_units=sorted(str(unit) for unit in units),
        )
    ownership_by_side: Dict[str, Optional[Dict[str, Any]]] = {
        side: (_ownership_contract(
            leg, parent_id, required_relation="JOIN",
            required_layer_role="OWNED_LEG",
            required_attachment_port="WAIST")
               if parent_id is not None else None)
        for side, leg in by_side.items()
    }
    ownership_present = {
        side for side, contract in ownership_by_side.items()
        if contract is not None}
    if ownership_present and ownership_present != {"left", "right"}:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSER_OWNERSHIP_INCOMPLETE",
            "both trouser legs must carry the same typed ownership contract",
            parent_node_id=parent_id,
            present_sides=sorted(ownership_present),
            missing_sides=sorted({"left", "right"} - ownership_present),
        )
    if parent_id is None:
        dangling_contracts = [
            str(node["node_id"]) for node in legs
            if any(_attribute(node, name) is not None for name in (
                "owner_node_id", "ownership_state", "layer_role",
                "attachment_port"))]
        if dangling_contracts:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_TROUSER_OWNER_MISSING",
                "standalone trouser legs cannot claim an owner without attached_to",
                leg_node_ids=sorted(dangling_contracts),
            )
    quantities = [_attribute(node, "quantity") for node in [*legs, gusset]]
    if any(value not in (None, 1) for value in quantities):
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_TROUSERS_QUANTITY",
                       "each explicit trouser leg and gusset node must have quantity=1")

    leg_lengths = {side: _waist_length(node, child=True)
                   for side, node in by_side.items()}
    if parent_id is not None:
        body_waist = _waist_length(nodes[parent_id], child=False)
        _length_match(body_waist, sum(leg_lengths.values()),
                      operation_id=f"split-waist-{parent_id}-trousers")
        for side in ("left", "right"):
            leg = by_side[side]
            leg_id = str(leg["node_id"])
            _join(nodes, operations, parent_id, leg_id, "waist",
                  leg_lengths[side], leg_lengths[side], suffix=f"-{side}",
                  parameters=(
                      {"ownership": ownership_by_side[side]}
                      if ownership_by_side[side] is not None else None))

    gusset_length = _dimension(gusset, "length_cm")
    gusset_id = str(gusset["node_id"])
    for side in ("left", "right"):
        leg_id = str(by_side[side]["node_id"])
        _join(nodes, operations, leg_id, gusset_id, "crotch",
              gusset_length, gusset_length, suffix=f"-{side}")
    consumed.update(leg_ids)
    consumed.add(gusset_id)


def _trouser_topology(nodes: Mapping[str, Dict[str, Any]],
                      operations: List[Dict[str, Any]],
                      consumed: Set[str]) -> None:
    """Compile each physical trouser layer independently.

    A layered outfit can legitimately contain trousers, leggings and another
    trouser-like underlayer in one candidate. The previous global cardinality
    check combined every typed leg and gusset, so two valid pairs became an
    invalid four-leg garment. ``garment_unit`` plus primitive layer is the
    explicit typed address; no grouping is inferred from names or proximity.
    """
    legs = [node for node in nodes.values()
            if node.get("kind") == "TUBE" and _is_trouser_leg(node)]
    all_gussets = [node for node in nodes.values()
                   if node.get("kind") == "GUSSET"]
    typed_gussets = [node for node in all_gussets
                     if _is_trouser_gusset(node)]
    if not legs and not typed_gussets:
        return

    def key(node: Mapping[str, Any]) -> Tuple[Optional[str], int]:
        raw_layer = node.get("layer", 0)
        layer = raw_layer if isinstance(raw_layer, int) and not isinstance(
            raw_layer, bool) else 0
        return (_unit(node), layer)

    groups: Dict[Tuple[Optional[str], int], List[Dict[str, Any]]] = {}
    for leg in legs:
        groups.setdefault(key(leg), []).append(leg)
    used_gussets: Set[str] = set()
    for group_key in sorted(groups, key=lambda value: (str(value[0]), value[1])):
        group_legs = groups[group_key]
        leg_ids = {str(node["node_id"]) for node in group_legs}
        # An exact attachment to both explicitly typed legs is stronger than
        # a missing/rephrased gusset role.  Accept that typed relation without
        # guessing from names or proximity; use same-unit/layer fallback only
        # for explicitly trouser-typed gussets.
        exact = [gusset for gusset in all_gussets
                 if set(_attached(gusset)) == leg_ids]
        candidates = exact or [gusset for gusset in typed_gussets
                               if key(gusset) == group_key]
        _trouser_group_topology(
            nodes, operations, consumed, legs=group_legs,
            gussets=candidates, group_key=group_key)
        used_gussets.update(str(node["node_id"]) for node in candidates)

    orphan_gussets = [node for node in typed_gussets
                       if str(node["node_id"]) not in used_gussets]
    if orphan_gussets:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_INCOMPLETE",
            "typed trouser GUSSET does not address one exact garment_unit/layer leg pair",
            leg_groups=[{"garment_unit": group[0], "layer": group[1],
                         "leg_node_ids": [node.get("node_id")
                                          for node in groups[group]]}
                        for group in sorted(
                            groups, key=lambda value: (str(value[0]), value[1]))],
            orphan_gusset_node_ids=[node.get("node_id")
                                    for node in orphan_gussets],
        )


def _candidate_topology(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    if candidate.get("state") != PROPOSED:
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_AUTHORITY",
                       "candidate state must remain PROPOSED",
                       candidate_id=candidate.get("candidate_id"),
                       state=candidate.get("state"))
    if candidate.get("schema") != garment_structure.SCHEMA:
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_STRUCTURE_SCHEMA",
                       f"expected {garment_structure.SCHEMA}")
    if candidate.get("operations") not in (None, [], ()):
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_ALREADY_ADDRESSED",
                       "the topology boundary only accepts operation-free completion output",
                       candidate_id=candidate.get("candidate_id"))
    raw_nodes = candidate.get("nodes")
    if (not isinstance(raw_nodes, Sequence) or isinstance(raw_nodes, (str, bytes))
            or not raw_nodes):
        raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_NODES",
                       "candidate needs a non-empty nodes array")
    nodes: Dict[str, Dict[str, Any]] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_NODE",
                           "every node must be an object")
        node = _json_copy(dict(raw), field="candidate.nodes")
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or not node_id or node_id in nodes:
            raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_NODE_ID",
                           "node ids must be unique and non-empty", node_id=node_id)
        if node.get("ports") not in (None, [], ()):
            raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_ALREADY_ADDRESSED",
                           "completion nodes must not already contain ports",
                           node_id=node_id)
        node["ports"] = []
        nodes[node_id] = node

    operations: List[Dict[str, Any]] = []
    consumed: Set[str] = set()
    delegated: List[Dict[str, Any]] = []
    # Run the cardinality guard before generic reference checks so a missing
    # leg cannot be misreported merely as a missing arbitrary attachment.
    _trouser_topology(nodes, operations, consumed)

    for node in nodes.values():
        for target_id in _attached(node):
            if target_id not in nodes:
                raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_TARGET_MISSING",
                               f"{node['node_id']} references unknown {target_id}",
                               node_id=node["node_id"], target_id=target_id)
            if target_id == node["node_id"]:
                raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_SELF_ATTACHMENT",
                               f"{node['node_id']} cannot attach to itself")

    typed_outer_waist_overlays: Dict[str, Dict[str, Any]] = {}
    for node_id in sorted(nodes):
        node = nodes[node_id]
        contract = _outer_waist_overlay_contract(node, nodes)
        if contract is not None:
            typed_outer_waist_overlays[node_id] = contract

    # More than one ordinary lower boundary on one body is ambiguous unless it
    # passed the explicit trouser rule above or every child supplies the same
    # bounded, proposal-only parallel waist-stack contract.
    ordinary_waist_children: Dict[str, List[str]] = {}
    for node in nodes.values():
        if node["node_id"] in consumed or node.get("kind") not in {
                "FLARE", "FRUSTUM", "TUBE"}:
            continue
        if node["node_id"] in typed_outer_waist_overlays:
            continue
        if node.get("kind") == "TUBE" and _is_trouser_leg(node):
            continue
        parents = _attached(node)
        if parents and len(parents) == 1 and nodes[parents[0]].get("kind") == "BODY_SHELL":
            ordinary_waist_children.setdefault(parents[0], []).append(node["node_id"])
    parallel_waist_children = copy.deepcopy(ordinary_waist_children)
    for node_id, contract in typed_outer_waist_overlays.items():
        parallel_waist_children.setdefault(
            contract["parent_node_id"], []).append(node_id)
    ambiguous = {
        parent: sorted(set(children))
        for parent, children in parallel_waist_children.items()
        if len(set(children)) > 1}
    accepted_waist_stacks: Dict[str, Dict[str, Any]] = {
        node_id: copy.deepcopy(contract["waist_stack"])
        for node_id, contract in typed_outer_waist_overlays.items()
    }
    for parent_id in sorted(ambiguous):
        accepted_waist_stacks.update(_validate_parallel_waist_stack(
            nodes, parent_id, ambiguous[parent_id]))

    for node_id in sorted(nodes):
        node = nodes[node_id]
        if node_id in consumed:
            continue
        kind = str(node.get("kind"))
        parents = _attached(node)

        outer_waist_overlay = typed_outer_waist_overlays.get(node_id)
        if outer_waist_overlay is not None:
            parent_id = outer_waist_overlay["parent_node_id"]
            parent = nodes[parent_id]
            interface = "waist-stack-layer-anchor"
            source_port = f"waist-stack-layer-to-{parent_id}"
            target_port = f"waist-stack-layer-from-{node_id}"
            _port(node, source_port, 1.0, interface, role="point")
            _port(parent, target_port, 1.0, interface, role="point")
            operations.append(_operation(
                f"layer-waist-overlay-{node_id}-on-{parent_id}", "LAYER",
                node_id, source_port, parent_id, target_port,
                basis=(
                    f"{node_id}.attached_to and owner_node_id explicitly name "
                    f"{parent_id}; the PROPOSED OUTER_OVERLAY waist-stack "
                    "contract selects a non-seam layer anchor"
                ),
                breaks_when=(
                    "parent, ownership, numeric layer, waist-stack id/order, "
                    "attachment relation, or attachment port changes"
                ),
                parameters={
                    "construction_role": "PROPOSED_WAIST_OUTER_OVERLAY",
                    "source_layer": outer_waist_overlay["source_layer"],
                    "target_layer": outer_waist_overlay["target_layer"],
                    "attachment_relation": "LAYER",
                    "attachment_port": "WAIST_STACK",
                    "ownership": outer_waist_overlay["ownership"],
                    "waist_stack": accepted_waist_stacks[node_id],
                    "dimensions_changed": False,
                    "seam_join_created": False,
                    "manufacturing_ready": False,
                    "manufacturing_certified": False,
                    "truth": {
                        "state": PROPOSED,
                        "observed": False,
                        "approved": False,
                        "authority_granted": False,
                        "not_observed_from_front_only_input": True,
                    },
                },
            ))
            delegated.append({
                "node_id": node_id,
                "target_node_id": parent_id,
                "rule": "TYPED_WAIST_OUTER_OVERLAY_LAYER",
                "construction_role": "PROPOSED_WAIST_OUTER_OVERLAY",
                "state": PROPOSED,
                "primitive_join_created": False,
                "dimensions_changed": False,
                "not_observed_from_front_only_input": True,
                "manufacturing_ready": False,
                "manufacturing_certified": False,
            })
            consumed.add(node_id)
            continue

        if kind in {"FLARE", "FRUSTUM", "TUBE"}:
            if not parents:
                bodies = [body for body in nodes.values()
                          if body.get("kind") == "BODY_SHELL"]
                same_or_unknown = [body for body in bodies
                                   if _unit(body) is None or _unit(node) is None
                                   or _unit(body) == _unit(node)]
                if same_or_unknown:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_WAIST_TARGET_UNRESOLVED",
                        f"{node_id} could meet a BODY_SHELL but attached_to is absent",
                        node_id=node_id,
                        possible_targets=[body["node_id"] for body in same_or_unknown],
                    )
                continue
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            if parent.get("kind") != "BODY_SHELL":
                raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_WAIST_TARGET",
                               f"{node_id} waist target must be BODY_SHELL",
                               node_id=node_id, target_id=parent_id)
            _require_unit_compatibility(node, parent, relation="waist JOIN")
            parent_length = _waist_length(parent, child=False)
            child_length = _waist_length(node, child=True)
            stack_metadata = accepted_waist_stacks.get(node_id)
            waist_mode = str(_attribute(node, "waist_join_mode") or "").upper()
            if waist_mode == "GATHER":
                if str(_attribute(node, "waist_join_state") or "").upper() != PROPOSED:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_WAIST_GATHER_AUTHORITY",
                        "waist GATHER relation must remain explicitly PROPOSED",
                        node_id=node_id,
                        state=_attribute(node, "waist_join_state"),
                    )
                provenance = _attribute(node, "waist_join_provenance")
                if not isinstance(provenance, Mapping):
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_WAIST_GATHER_PROVENANCE",
                        "waist GATHER requires explicit proposal provenance",
                        node_id=node_id,
                    )
                if child_length <= parent_length:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_GATHER_NOT_LONGER",
                        "a gathered skirt waist must be longer than its BODY_SHELL target",
                        node_id=node_id, target_id=parent_id,
                        source_cm=child_length, target_cm=parent_length,
                    )
                ratio = child_length / parent_length
                if ratio > 8.0:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_GATHER_RATIO",
                        "waist GATHER ratio exceeds the bounded preview limit",
                        node_id=node_id, target_id=parent_id, ratio=ratio,
                    )
                interface = f"waist-gather-{node_id}-{parent_id}"
                source_port = f"waist-gather-to-{parent_id}"
                target_port = f"waist-gather-from-{node_id}"
                _port(node, source_port, child_length, interface, role="edge")
                _port(parent, target_port, parent_length, interface, role="edge")
                operations.append(_operation(
                    f"gather-waist-{node_id}-to-{parent_id}", "GATHER",
                    node_id, source_port, parent_id, target_port,
                    basis=(
                        f"{node_id}.attached_to explicitly names {parent_id}; "
                        "waist_join_mode is a PROPOSED fullness construction"
                    ),
                    breaks_when=(
                        "a reviewed pleat, dart, ease, separate waistband, "
                        "calibrated dimension, or different attachment is supplied"
                    ),
                    parameters={
                        "ratio": ratio,
                        "source_length_cm": child_length,
                        "target_length_cm": parent_length,
                        "construction_alternatives_unobserved": [
                            "PLEAT", "EASE", "SEPARATE_WAISTBAND",
                        ],
                        **({"waist_stack": stack_metadata}
                           if stack_metadata is not None else {}),
                    },
                ))
            else:
                _join(nodes, operations, parent_id, node_id, "waist",
                      parent_length, child_length,
                      parameters=({"waist_stack": stack_metadata}
                                  if stack_metadata is not None else None))
            consumed.add(node_id)
            continue

        if kind == "BODY_SHELL":
            # A second skin, lining, dress body and outer bodice may all be
            # represented as BODY_SHELL primitives.  When the model supplies
            # an explicit parent and a strictly higher layer, preserve that
            # ownership as a proposal-only LAYER anchor.  This does not invent
            # a seam between the shells and does not promote the rear or
            # inside construction to an observation.
            if not parents:
                continue
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            if parent.get("kind") != "BODY_SHELL":
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_BODY_LAYER_TARGET",
                    "a layered BODY_SHELL requires one BODY_SHELL parent",
                    node_id=node_id, target_id=parent_id,
                    target_kind=parent.get("kind"),
                )
            _require_unit_compatibility(
                node, parent, relation="layered BODY_SHELL ownership")
            child_layer = node.get("layer")
            parent_layer = parent.get("layer")
            layer_is_higher = (
                isinstance(child_layer, (int, float))
                and not isinstance(child_layer, bool)
                and isinstance(parent_layer, (int, float))
                and not isinstance(parent_layer, bool)
                and math.isfinite(float(child_layer))
                and math.isfinite(float(parent_layer))
                and float(child_layer) > float(parent_layer)
            )
            if not layer_is_higher:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_BODY_LAYER_ORDER",
                    "a child BODY_SHELL must have a strictly higher finite layer than its BODY_SHELL parent",
                    node_id=node_id, target_id=parent_id,
                    child_layer=child_layer, parent_layer=parent_layer,
                )
            interface = "body-shell-layer-anchor"
            source_port = f"layer-to-{parent_id}"
            target_port = f"layer-from-{node_id}"
            _port(node, source_port, 1.0, interface, role="point")
            _port(parent, target_port, 1.0, interface, role="point")
            operations.append(_operation(
                f"layer-body-{node_id}-on-{parent_id}", "LAYER",
                node_id, source_port, parent_id, target_port,
                basis=(
                    f"{node_id}.attached_to explicitly names BODY_SHELL "
                    f"{parent_id}; garment_unit agrees and the child layer is "
                    "strictly higher"
                ),
                breaks_when=(
                    "attached_to, garment_unit, ownership, or either layer "
                    "address changes"
                ),
                parameters={
                    "construction_role": "PROPOSED_LAYERED_BODY_SHELL",
                    "source_layer": child_layer,
                    "target_layer": parent_layer,
                    "owner_node_id": parent_id,
                    "attachment_relation": "LAYER",
                    "relation_state": PROPOSED,
                    "dimensions_changed": False,
                    "seam_join_created": False,
                    "manufacturing_ready": False,
                    "manufacturing_certified": False,
                    "truth": {
                        "state": PROPOSED,
                        "observed": False,
                        "approved": False,
                        "authority_granted": False,
                        "rear_or_inside_construction_observed": False,
                    },
                },
            ))
            delegated.append({
                "node_id": node_id,
                "target_node_id": parent_id,
                "rule": "TYPED_LAYERED_BODY_SHELL_OWNERSHIP",
                "construction_role": "PROPOSED_LAYERED_BODY_SHELL",
                "state": PROPOSED,
                "primitive_join_created": False,
                "dimensions_changed": False,
                "not_observed_from_front_only_input": True,
                "manufacturing_ready": False,
                "manufacturing_certified": False,
            })
            consumed.add(node_id)
            continue

        if kind in {"COLLAR", "HOOD"}:
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            if parent.get("kind") != "BODY_SHELL":
                raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_NECK_TARGET",
                               f"{node_id} neck target must be BODY_SHELL",
                               node_id=node_id, target_id=parent_id)
            _require_unit_compatibility(node, parent, relation="neck JOIN")
            child_length, approximation = _neck_child_length(node)
            parent_length = _optional_dimension(parent, "neck_circumference_cm")
            parent_length = child_length if parent_length is None else parent_length
            _join(nodes, operations, parent_id, node_id, "neck",
                  parent_length, child_length)
            node["attributes"]["topology_neck_boundary_approximation"] = {
                "state": PROPOSED,
                "used": approximation,
                "basis": ("HOOD.width_cm used as proposed neck-edge preview"
                          if approximation else "explicit typed neck edge"),
                "breaks_when": "a drafted neckline/hood seam length is available",
            }
            consumed.add(node_id)
            continue

        if kind == "GORE":
            # A structural gore is normally one panel in a complete skirt
            # assembly and cannot be sewn merely because it names a parent.
            # Front-image models also use GORE/PANEL for an asymmetric surface
            # overlay, however. Accept only that explicit higher-layer case as
            # a point-anchored LAYER relation; keep structural-gore topology a
            # review gate instead of inventing adjacent panel seams.
            typed_semantics: Set[str] = set()
            for semantic_field in (
                    "placement", "shape", "detail_role", "model_kind",
                    "attachment_relation", "construction_role"):
                typed_semantics.update(_semantic_words(
                    _attribute(node, semantic_field)))
            visible_semantics = _positive_evidence_words(
                _attribute(node, "visible_basis"))
            semantics = typed_semantics | visible_semantics

            # Explicit construction semantics outrank image-description words.
            # A model may call a region an overlay visually while also proposing
            # JOIN/structural_gore_panel; that is a real panel-topology request
            # and must remain a review gate.
            structural_semantics = bool(typed_semantics & {
                "structural", "join", "joined", "seam", "seamed",
            })
            overlay_words = {
                "overlay", "decorative", "ornamental", "applique",
                "appliqué", "floating", "overskirt", "overlayer",
            }
            layer_words = {"layer", "layered", "layering"}
            front_surface_words = {"front", "panel", "surface"}
            explicit_overlay = not structural_semantics and (
                bool(typed_semantics & overlay_words)
                or (
                    bool(semantics & {"asymmetric", "asymmetrical"})
                    and bool(semantics & front_surface_words)
                    and bool(semantics & layer_words)
                )
                or (
                    bool(visible_semantics & overlay_words)
                    and bool(visible_semantics & front_surface_words)
                )
            )
            if not parents:
                if explicit_overlay:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS",
                        "a decorative GORE overlay needs one explicit carrier; front-only semantics cannot select it",
                        node_id=node_id,
                    )
                # An unaddressed structural GORE remains an independent panel
                # proposal. Adjacent-gore assembly is a separate typed graph
                # operation and is never inferred here.
                continue
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            if not explicit_overlay:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_GORE_ATTACHMENT_ROLE",
                    "an attached GORE needs explicit decorative overlay semantics; structural gore seams require a complete panel topology",
                    node_id=node_id, target_id=parent_id,
                    placement=_attribute(node, "placement"),
                    shape=_attribute(node, "shape"),
                    detail_role=_attribute(node, "detail_role"),
                    visible_basis=_attribute(node, "visible_basis"),
                    attachment_relation=_attribute(
                        node, "attachment_relation"),
                    typed_semantics=sorted(typed_semantics),
                    positive_visible_semantics=sorted(visible_semantics),
                    structural_semantics=structural_semantics,
                )
            if parent.get("kind") not in {
                    "BODY_SHELL", "FLARE", "FRUSTUM", "TUBE", "OVERLAY"}:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_GORE_OVERLAY_TARGET",
                    "a decorative GORE overlay needs a supported garment-surface parent",
                    node_id=node_id, target_id=parent_id,
                    target_kind=parent.get("kind"),
                )
            _require_unit_compatibility(
                node, parent, relation="decorative GORE overlay LAYER")
            child_layer = node.get("layer", 0)
            parent_layer = parent.get("layer", 0)
            if (not isinstance(child_layer, (int, float))
                    or isinstance(child_layer, bool)
                    or not isinstance(parent_layer, (int, float))
                    or isinstance(parent_layer, bool)
                    or not math.isfinite(float(child_layer))
                    or not math.isfinite(float(parent_layer))
                    or float(child_layer) <= float(parent_layer)):
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_GORE_OVERLAY_LAYER",
                    "a decorative GORE overlay must be on a strictly higher finite layer than its carrier",
                    node_id=node_id, target_id=parent_id,
                    source_layer=child_layer, target_layer=parent_layer,
                )
            interface = "gore-layer-anchor"
            source_port = f"gore-layer-to-{parent_id}"
            target_port = f"gore-layer-from-{node_id}"
            _port(node, source_port, 1.0, interface, role="point")
            _port(parent, target_port, 1.0, interface, role="point")
            relation_side = str(_attribute(node, "side") or "").strip().lower()
            if relation_side not in {"left", "right"}:
                relation_side = ""
            operations.append(_operation(
                f"layer-gore-{node_id}-on-{parent_id}", "LAYER",
                node_id, source_port, parent_id, target_port,
                basis=(f"{node_id}.attached_to explicitly names {parent_id}; "
                       "typed decorative/asymmetric overlay semantics and "
                       "strictly higher layer select a non-structural surface anchor"),
                breaks_when=(
                    "attached_to, garment unit, layer order, placement, shape, "
                    "detail role, or reviewed panel topology changes"),
                parameters={
                    "construction_role": "PROPOSED_GORE_OVERLAY",
                    "source_layer": child_layer,
                    "target_layer": parent_layer,
                    **({"relation_side": relation_side}
                       if relation_side else {}),
                    "relation_state": PROPOSED,
                    "dimensions_changed": False,
                    "seam_join_created": False,
                    "manufacturing_ready": False,
                    "manufacturing_certified": False,
                    "truth": {
                        "state": PROPOSED,
                        "observed": False,
                        "approved": False,
                        "authority_granted": False,
                        "not_observed_from_front_only_input": True,
                    },
                },
            ))
            delegated.append({
                "node_id": node_id,
                "target_node_id": parent_id,
                "rule": "TYPED_DECORATIVE_GORE_OVERLAY_LAYER",
                "construction_role": "PROPOSED_GORE_OVERLAY",
                "state": PROPOSED,
                "primitive_join_created": False,
                "dimensions_changed": False,
                "not_observed_from_front_only_input": True,
                "manufacturing_ready": False,
                "manufacturing_certified": False,
            })
            consumed.add(node_id)
            continue

        if kind == "OVERLAY":
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            interface = "layer-anchor"
            source_port = f"layer-to-{parent_id}"
            target_port = f"layer-from-{node_id}"
            _port(node, source_port, 1.0, interface, role="point")
            _port(parent, target_port, 1.0, interface, role="point")
            operations.append(_operation(
                f"layer-{node_id}-on-{parent_id}", "LAYER",
                node_id, source_port, parent_id, target_port,
                basis=f"{node_id}.attached_to explicitly names {parent_id}",
                breaks_when="layer order or attached_to is revised",
                parameters={"source_layer": node.get("layer", 0),
                            "target_layer": parent.get("layer", 0)},
            ))
            consumed.add(node_id)
            continue

        gathered_band_roles = _tokens(_attribute(node, "detail_role")) & {
            "ruffle", "frill",
        }
        if kind == "BAND" and gathered_band_roles:
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            source_length = _dimension(node, "length_cm")
            target_length, target_role = _ruffle_target(
                parent, _attribute(node, "placement"))
            if source_length <= target_length:
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_GATHER_NOT_LONGER",
                    "a ruffle source edge must be longer than its target edge",
                    node_id=node_id, target_id=parent_id,
                    source_cm=source_length, target_cm=target_length,
                )
            interface = f"gather-{node_id}-{parent_id}"
            source_port = f"gather-to-{parent_id}"
            target_port = f"gather-from-{node_id}"
            _port(node, source_port, source_length, interface, role="edge")
            _port(parent, target_port, target_length, interface, role="edge")
            ratio = source_length / target_length
            relation_side = str(_attribute(node, "side") or "").strip().lower()
            if relation_side not in {"left", "right"}:
                relation_side = ""
            operations.append(_operation(
                f"gather-{node_id}-to-{parent_id}", "GATHER",
                node_id, source_port, parent_id, target_port,
                basis=(f"{node_id} is explicitly detail_role="
                       f"{sorted(gathered_band_roles)} and attached_to "
                       f"{parent_id}; placement selects {target_role}"),
                breaks_when="detail_role, placement, attachment, or either edge length changes",
                parameters={
                    "ratio": ratio,
                    "target_role": target_role,
                    **({"relation_side": relation_side}
                       if relation_side else {}),
                },
            ))
            consumed.add(node_id)
            continue

        if kind == "BAND":
            if not parents:
                # A loose belt or sash is a wearable unit in its own right; it
                # is not necessarily sewn to the bodice visible behind it.
                # Accept it only when the model made that intent explicit.
                # The rectangular cut geometry is safe to preview, while the
                # closure and overlap remain a review gate rather than an
                # invented self-JOIN.
                role_tokens = (_tokens(_attribute(node, "detail_role"))
                               | _tokens(_attribute(node, "shape")))
                placement_tokens = _tokens(_attribute(node, "placement"))
                is_independent_band = bool(
                    role_tokens & {"belt", "sash", "independent_belt",
                                   "standalone_belt", "waist_belt",
                                   "standalone_garter", "garter",
                                   "standalone_strap", "accessory_band"}
                    or placement_tokens & {"belt", "waist", "waist belt"}
                )
                if not is_independent_band or _unit(node) is None:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS",
                        f"{node_id} needs one attached_to target or an explicit standalone belt/sash role and garment_unit",
                        node_id=node_id, attached_to=[],
                        detail_role=_attribute(node, "detail_role"),
                        placement=_attribute(node, "placement"),
                        garment_unit=_unit(node),
                    )
                length_cm = _dimension(node, "length_cm")
                width_cm = _dimension(node, "width_cm")
                node["attributes"]["standalone_band_topology"] = {
                    "state": "REVIEW",
                    "wearable_unit": True,
                    "length_cm_preserved": length_cm,
                    "width_cm_preserved": width_cm,
                    "closure_selected": False,
                    "overlap_cm": None,
                    "basis": (
                        "explicit standalone belt/sash role plus garment_unit; "
                        "the front image does not establish rear closure or overlap"
                    ),
                    "breaks_when": (
                        "a rear/inside view, closure choice, target waist, or "
                        "construction review changes the belt topology"
                    ),
                }
                delegated.append({
                    "node_id": node_id,
                    "target_node_id": None,
                    "rule": "REVIEW_STANDALONE_BAND_CLOSURE_AND_OVERLAP",
                    "state": "REVIEW",
                    "primitive_join_created": False,
                })
                consumed.add(node_id)
                continue
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            _require_unit_compatibility(node, parent, relation="band JOIN")
            source_length = _dimension(node, "length_cm")
            selector = {
                "placement": _attribute(node, "placement"),
                "shape": _attribute(node, "shape"),
                "detail_role": _attribute(node, "detail_role"),
            }
            target_length, target_role = _band_target(parent, selector)
            source_evidence = (node.get("attributes", {})
                               .get("dimension_evidence", {})
                               .get("length_cm", {}))
            source_is_bounded_completion = bool(
                isinstance(source_evidence, Mapping)
                and source_evidence.get("completed") is True
                and source_evidence.get("model_supplied") is False
                and source_evidence.get("dimension_source")
                == "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL"
            )
            # BODY_SHELL.circumference_cm is an upper/body loop, not a typed
            # waist seam. If the parent has no explicit waist/bottom boundary,
            # a preview-completed, explicitly attached waist BAND is the only
            # candidate-local sewing length. Use that value for the preview
            # port and record the approximation. A model/user-supplied BAND is
            # never allowed to redefine the parent seam; an explicit mismatch
            # must continue to fail closed.
            if (parent.get("kind") == "BODY_SHELL" and target_role == "waist"
                    and _optional_dimension(
                        parent, "bottom_circumference_cm",
                        "waist_circumference_cm") is None
                    and source_is_bounded_completion):
                target_length = source_length
                parent.setdefault("dimensions", {})[
                    "bottom_circumference_cm"] = source_length
                parent.setdefault("attributes", {})[
                    "topology_waist_boundary_approximation"] = {
                        "state": PROPOSED,
                        "used": True,
                        "value_cm": source_length,
                        "source_node_id": node_id,
                        "basis": (
                            "explicit attached_to plus waist BAND semantics; "
                            "BODY_SHELL has no typed waist/bottom boundary"
                        ),
                        "not_measured_from_image": True,
                        "breaks_when": (
                            "a wearer waist, drafted body waist seam, or revised "
                            "band length is supplied"
                        ),
                    }
            _join(nodes, operations, parent_id, node_id,
                  f"band-{target_role}", target_length, source_length)
            consumed.add(node_id)
            continue

        if kind == "YOKE":
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            if parent.get("kind") != "BODY_SHELL":
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_YOKE_TARGET",
                    "a proposed YOKE currently requires a BODY_SHELL target",
                    node_id=node_id, target_id=parent_id)
            _require_unit_compatibility(node, parent, relation="yoke LAYER")
            source_port = f"layer-to-{parent_id}"
            target_port = f"layer-from-{node_id}"
            _port(node, source_port, 1.0, "yoke-layer-anchor", role="point")
            _port(parent, target_port, 1.0, "yoke-layer-anchor", role="point")
            operations.append(_operation(
                f"layer-{node_id}-on-{parent_id}", "LAYER",
                node_id, source_port, parent_id, target_port,
                basis=(f"{node_id}.attached_to names {parent_id}; the front image "
                       "supports a yoke region but not whether it replaces or overlays the shell"),
                breaks_when=("a rear/inside view establishes a structural yoke seam "
                             "instead of an overlay treatment"),
                parameters={"relation_state": "PROPOSED_YOKE_TREATMENT",
                            "structural_seam_inferred": False},
            ))
            delegated.append({
                "node_id": node_id,
                "target_node_id": parent_id,
                "rule": "PROPOSED_YOKE_LAYER_UNTIL_CONSTRUCTION_REVIEW",
                "state": PROPOSED,
                "primitive_join_created": False,
            })
            consumed.add(node_id)
            continue

        if kind == "OPENING":
            _opening_semantic_authority(node)
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            _require_unit_compatibility(node, parent, relation="opening feature")
            node["attributes"]["opening_target_id"] = parent_id
            node["attributes"]["opening_topology"] = (
                _opening_topology_proposal(node, parent_id))
            node["attributes"]["opening_semantic_authority"] = {
                "state": PROPOSED,
                "observed": False,
                "approved": False,
                "source": "MODEL_PROPOSAL_PLUS_TYPED_ATTACHMENT_RESOLUTION",
                "closure_detail_present": (
                    _attribute(node, "closure_detail") is not None),
            }
            delegated.append({
                "node_id": node_id,
                "target_node_id": parent_id,
                "rule": "DELEGATED_OPENING_FEATURE_NO_CUT_GEOMETRY",
                "state": PROPOSED,
                "primitive_join_created": False,
            })
            consumed.add(node_id)
            continue

        if kind == "SLEEVE":
            shape = str(_attribute(node, "shape") or "").strip().lower()
            if shape == "detached":
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_DETACHED_SLEEVE_UNRESOLVED",
                    "detached sleeves need an explicit anchor rule not provided here",
                    node_id=node_id, attached_to=list(parents),
                )
            parent_id = _one_parent(node)
            parent = nodes[parent_id]
            parent_kind = parent.get("kind")
            if parent_kind == "SLEEVE":
                _require_unit_compatibility(
                    node, parent, relation="sleeve/sleeve relation")
                relation_text = json.dumps({
                    "placement": _attribute(node, "placement"),
                    "shape": _attribute(node, "shape"),
                    "detail_role": _attribute(node, "detail_role"),
                }, sort_keys=True, ensure_ascii=False).lower()
                explicit_extension = any(token in relation_text for token in (
                    "lower sleeve", "sleeve extension", "cuff extension",
                    "gauntlet", "forearm",
                ))
                explicit_layer = any(token in relation_text for token in (
                    "oversleeve", "over-sleeve", "outer sleeve",
                    "layered sleeve", "sleeve overlay", "decorative sleeve",
                    "floating sleeve", "wing sleeve",
                ))
                typed_relation = str(
                    _attribute(node, "attachment_relation") or ""
                ).strip().upper()
                child_layer = node.get("layer")
                parent_layer = parent.get("layer")
                layer_is_higher = (
                    isinstance(child_layer, (int, float))
                    and not isinstance(child_layer, bool)
                    and isinstance(parent_layer, (int, float))
                    and not isinstance(parent_layer, bool)
                    and math.isfinite(float(child_layer))
                    and math.isfinite(float(parent_layer))
                    and float(child_layer) > float(parent_layer)
                )
                relation_conflicts = (
                    (typed_relation == "JOIN" and explicit_layer)
                    or (typed_relation == "LAYER" and explicit_extension)
                    or (typed_relation == "GATHER" and explicit_layer)
                    or (explicit_extension and explicit_layer)
                )
                if relation_conflicts:
                    raise _Refusal(
                        "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_RELATION_CONFLICT",
                        "sleeve semantics select both an edge extension and an outer layer",
                        node_id=node_id, target_id=parent_id,
                        placement=_attribute(node, "placement"),
                        shape=_attribute(node, "shape"),
                        detail_role=_attribute(node, "detail_role"),
                    )
                if typed_relation == "GATHER":
                    if not explicit_extension:
                        raise _Refusal(
                            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_SEMANTICS",
                            "a sleeve GATHER requires explicit lower-sleeve extension semantics",
                            node_id=node_id, target_id=parent_id,
                            placement=_attribute(node, "placement"),
                            shape=_attribute(node, "shape"),
                            detail_role=_attribute(node, "detail_role"),
                        )
                    provenance = _sleeve_gather_provenance(node)
                    parent_length = _dimension(
                        parent, "cuff_circumference_cm")
                    child_length = _dimension(
                        node, "upper_circumference_cm")
                    if child_length <= parent_length:
                        raise _Refusal(
                            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_NOT_LONGER",
                            "a gathered lower-sleeve upper edge must be "
                            "longer than the parent cuff",
                            node_id=node_id, target_id=parent_id,
                            source_cm=child_length,
                            target_cm=parent_length,
                        )
                    ratio = child_length / parent_length
                    if ratio > _MAX_SLEEVE_GATHER_RATIO:
                        raise _Refusal(
                            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_GATHER_RATIO",
                            "sleeve GATHER ratio exceeds the bounded preview limit",
                            node_id=node_id, target_id=parent_id,
                            ratio=ratio,
                            maximum=_MAX_SLEEVE_GATHER_RATIO,
                            source_cm=child_length,
                            target_cm=parent_length,
                        )
                    interface = f"sleeve-gather-{parent_id}-{node_id}"
                    source_port = f"sleeve-gather-to-{parent_id}"
                    target_port = f"sleeve-gather-from-{node_id}"
                    _port(node, source_port, child_length, interface,
                          role="edge")
                    _port(parent, target_port, parent_length, interface,
                          role="edge")
                    operations.append(_operation(
                        f"gather-sleeve-extension-{parent_id}-{node_id}",
                        "GATHER", node_id, source_port, parent_id,
                        target_port,
                        basis=(
                            f"{node_id}.attached_to explicitly names sleeve "
                            f"{parent_id}; lower-sleeve semantics and a "
                            "PROPOSED gather contract select a reducing edge "
                            "connection"
                        ),
                        breaks_when=(
                            "attachment, lower-sleeve semantics, proposal "
                            "provenance, or either sleeve boundary changes"
                        ),
                        parameters={
                            "attachment_relation": "GATHER",
                            "construction_role":
                                "GATHER_SLEEVE_SEGMENTS",
                            "ratio": ratio,
                            "source_length_cm": child_length,
                            "target_length_cm": parent_length,
                            "dimensions_changed": False,
                            "manufacturing_ready": False,
                            "manufacturing_certified": False,
                            "sleeve_join_provenance": provenance,
                            "truth": {
                                "state": PROPOSED,
                                "observed": False,
                                "approved": False,
                                "authority_granted": False,
                                "not_observed_from_front_only_input": True,
                            },
                        },
                    ))
                    delegated.append({
                        "node_id": node_id,
                        "target_node_id": parent_id,
                        "rule": "TYPED_LOWER_SLEEVE_EXTENSION_GATHER",
                        "construction_role": "GATHER_SLEEVE_SEGMENTS",
                        "state": PROPOSED,
                        "primitive_join_created": True,
                        "not_observed_from_front_only_input": True,
                        "attachment_relation": "GATHER",
                        "dimensions_changed": False,
                        "manufacturing_ready": False,
                        "manufacturing_certified": False,
                    })
                    consumed.add(node_id)
                    continue
                if typed_relation == "JOIN" or explicit_extension:
                    _join(
                        nodes, operations, parent_id, node_id,
                        "sleeve-extension",
                        _dimension(parent, "cuff_circumference_cm"),
                        _dimension(node, "upper_circumference_cm"),
                    )
                    delegated.append({
                        "node_id": node_id,
                        "target_node_id": parent_id,
                        "rule": "TYPED_LOWER_SLEEVE_EXTENSION_JOIN",
                        "state": PROPOSED,
                        "primitive_join_created": True,
                        "not_observed_from_front_only_input": True,
                        "attachment_relation": "JOIN",
                    })
                    consumed.add(node_id)
                    continue
                if typed_relation == "LAYER" or explicit_layer or layer_is_higher:
                    if not layer_is_higher:
                        raise _Refusal(
                            "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_LAYER_ORDER",
                            "a sleeve LAYER requires a strictly higher numeric layer than its parent sleeve",
                            node_id=node_id, target_id=parent_id,
                            child_layer=child_layer, parent_layer=parent_layer,
                        )
                    interface = "sleeve-layer-anchor"
                    source_port = f"layer-to-{parent_id}"
                    target_port = f"layer-from-{node_id}"
                    _port(node, source_port, 1.0, interface, role="point")
                    _port(parent, target_port, 1.0, interface, role="point")
                    operations.append(_operation(
                        f"layer-{node_id}-on-{parent_id}", "LAYER",
                        node_id, source_port, parent_id, target_port,
                        basis=(
                            f"{node_id}.attached_to explicitly names sleeve "
                            f"{parent_id}; outer-layer semantics or a strictly "
                            "higher layer index select a non-seam preview anchor"
                        ),
                        breaks_when=(
                            "layer order, attached_to, placement, shape or "
                            "detail_role changes"
                        ),
                        parameters={
                            "source_layer": child_layer,
                            "target_layer": parent_layer,
                            "relation_state": "PROPOSED_OVERSLEEVE_LAYER",
                            "attachment_relation": "LAYER",
                            "seam_join_created": False,
                        },
                    ))
                    delegated.append({
                        "node_id": node_id,
                        "target_node_id": parent_id,
                        "rule": "DELEGATED_EXPLICIT_OVERSLEEVE_LAYER_ANCHOR",
                        "state": PROPOSED,
                        "primitive_join_created": False,
                        "not_observed_from_front_only_input": True,
                        "attachment_relation": "LAYER",
                    })
                    consumed.add(node_id)
                    continue
                raise _Refusal(
                    "UNKNOWN_PARTS_TOPOLOGY_SLEEVE_TARGET",
                    "a SLEEVE attached to SLEEVE needs explicit lower-extension semantics or a higher/outer layer address",
                    node_id=node_id, target_id=parent_id,
                    child_layer=child_layer, parent_layer=parent_layer,
                )
            if parent_kind != "BODY_SHELL":
                raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_SLEEVE_TARGET",
                               f"{node_id} targets {parent_id} ({parent_kind}); "
                               "an attached SLEEVE needs BODY_SHELL, a typed "
                               "SLEEVE relation, or a separately modelled "
                               "armhole carrier",
                               node_id=node_id, target_id=parent_id,
                               target_kind=parent_kind)
            _require_unit_compatibility(node, parent,
                                        relation="bodice/sleeve bridge")
            delegated.append({
                "node_id": node_id,
                "target_node_id": parent_id,
                "rule": "DELEGATED_BODICE_SET_IN_SLEEVE_BRIDGE",
                "state": PROPOSED,
                "primitive_join_created": False,
            })
            consumed.add(node_id)
            continue

        if parents:
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_RELATION_UNSUPPORTED",
                f"no typed topology rule handles {kind}.attached_to",
                node_id=node_id, kind=kind, attached_to=list(parents),
            )

    graph_spec = {
        "schema": garment_structure.SCHEMA,
        "nodes": [nodes[node_id] for node_id in sorted(nodes)],
        "operations": operations,
    }
    checked = garment_structure.validate(graph_spec)
    if checked.get("verdict") != garment_structure.ANSWER:
        raise _Refusal(
            "UNKNOWN_PARTS_TOPOLOGY_VALIDATION",
            "generated ports/operations failed garment.structure.v1 validation",
            validator_code=checked.get("verdict"),
            validator_why=checked.get("why"),
        )
    graph = checked["graph"]
    ornament_artifacts = _bind_ornament_artifacts(
        candidate, nodes, topology_structure_digest=checked["digest"])
    candidate_geometry = _candidate_geometry_identity(
        structure_digest=checked["digest"],
        nodes=nodes,
        operations=operations,
        ornament_artifacts=ornament_artifacts,
    )
    result = copy.deepcopy(graph)
    result.update({
        "candidate_id": candidate.get("candidate_id"),
        "state": PROPOSED,
        "source_structure_digest": candidate.get("structure_digest"),
        "structure_digest": checked["digest"],
        "topology_digest": checked["digest"],
        "candidate_geometry_digest": candidate_geometry["digest"],
        "candidate_geometry": candidate_geometry,
        "completion_variant": candidate.get("completion_variant"),
        "topology": {
            "state": PROPOSED,
            "operation_count": len(operations),
            "operation_ids": [row["operation_id"] for row in operations],
            "delegated_relations": delegated,
            "authority_granted": False,
            "input_mutated": False,
        },
        "provenance": {
            **copy.deepcopy(candidate.get("provenance", {})),
            "topology_method": "explicit attached_to plus bounded typed rules",
            "image_attachment_inference": False,
            "name_based_attachment_inference": False,
        },
        "limitations": list(candidate.get("limitations", [])) + [
            "ports and operations remain PROPOSED until reviewed",
            "set-in sleeve seams are delegated to the existing bodice/sleeve bridge",
            "unsupported or dimensionally ambiguous relations fail closed",
        ],
    })
    if ornament_artifacts is not None:
        result["ornament_artifacts"] = ornament_artifacts
        result["candidate_artifact_digest"] = garment_structure.semantic_digest({
            "structure_digest": checked["digest"],
            "ornament_topology_digest": ornament_artifacts["topology_digest"],
        })
    return result


def apply_parts_ir_topology(completion: Mapping[str, Any]) -> Dict[str, Any]:
    """Add validated proposal-only ports and operations to completion output."""
    try:
        if not isinstance(completion, Mapping):
            raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_INPUT",
                           "completion must be an object")
        if (completion.get("schema") != COMPLETION_SCHEMA
                or completion.get("verdict") != PROPOSED
                or completion.get("state") != PROPOSED):
            raise _Refusal(
                "UNKNOWN_PARTS_TOPOLOGY_COMPLETION_STATE",
                "input must be successful PROPOSED parts-ir completion output",
                input_schema=completion.get("schema"),
                input_verdict=completion.get("verdict"),
                input_state=completion.get("state"),
            )
        candidates = completion.get("candidates")
        if (not isinstance(candidates, Sequence)
                or isinstance(candidates, (str, bytes)) or len(candidates) < 2):
            raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_CANDIDATES_INSUFFICIENT",
                           "at least two completed candidates are required",
                           candidate_count=(len(candidates)
                                            if isinstance(candidates, Sequence)
                                            and not isinstance(candidates, (str, bytes))
                                            else None))
        original_digest = garment_structure.semantic_digest(completion)
        output = [_candidate_topology(candidate) for candidate in candidates]
        if garment_structure.semantic_digest(completion) != original_digest:
            raise _Refusal("UNKNOWN_PARTS_TOPOLOGY_INPUT_MUTATED",
                           "topology construction mutated its completion input")
        return {
            "schema": SCHEMA,
            "verdict": PROPOSED,
            "state": PROPOSED,
            "candidate_count": len(output),
            "candidates": output,
            "input_completion_digest": original_digest,
            "topology_digest": garment_structure.semantic_digest(output),
            "authority": {
                "highest_state": PROPOSED,
                "approved": False,
                "observed": False,
                "answer": False,
            },
            "provenance": {
                "method": "deterministic typed parts topology",
                "raw_pixels_consumed": False,
                "name_based_attachment_inference": False,
                "input_mutated": False,
            },
        }
    except _Refusal as refusal:
        return _unknown(refusal.code, refusal.why, **refusal.detail)
    except (TypeError, ValueError, OverflowError) as exc:
        return _unknown("UNKNOWN_PARTS_TOPOLOGY_MALFORMED", str(exc))


build_topology = apply_parts_ir_topology
topologize = apply_parts_ir_topology


__all__ = [
    "SCHEMA", "apply_parts_ir_topology", "build_topology", "topologize",
]
