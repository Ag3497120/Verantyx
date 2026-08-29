# -*- coding: utf-8 -*-
"""Deterministic geometry-first composition of layered garment primitives.

The module is a boundary between structured front-view interpretation and the
existing :mod:`photoloset.garment_structure` graph.  It deliberately accepts
primitive geometry instead of garment class names.  A top and a lower volume,
for example, can remain separate or can be joined; a split lower body is two
``TUBE`` primitives plus an optional ``GUSSET``; and an overlay is just a
higher-layer primitive with explicit layer/contact constraints.

No pixels are interpreted here.  Rear geometry, material, and any boundary
hidden in the front image remain ``PROPOSED``.  When more than one attachment
topology validates, every feasible graph is returned and human choice is
required.  No result from this module is a manufacturing claim.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .garment_structure import (
    ANSWER,
    BoundaryPort,
    OperationKind,
    PortRef,
    PrimitiveKind,
    PrimitiveNode,
    StructureGraph,
    StructureOperation,
    validate_structure,
)


REQUEST_SCHEMA = "garment.layered-vision.v1"
SCHEMA = "garment.layered-composition.v1"
PROPOSED = "PROPOSED"
OBSERVED = "OBSERVED"
REVIEW = "REVIEW"

_RELATIONS = {"JOIN", "LAYER", "CONTACT", "SEPARATE", "OVERLAP"}
_VISIBILITIES = {"FRONT_VISIBLE", "OCCLUDED", "REAR", "UNKNOWN"}
_PORT_ROLES = {"edge", "loop", "point"}
_MAX_CHOICE_SETS = 8
_MAX_COMBINATIONS = 64


class _Refusal(Exception):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


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


def _unknown(request: Any, code: str, why: str, **detail: Any) -> Dict[str, Any]:
    try:
        input_digest = stable_digest(request)
    except (TypeError, ValueError, OverflowError):
        input_digest = None
    result = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNRESOLVED",
        "why": why,
        "how_to_close": (
            "supply finite primitive geometry, proposal-only hidden claims, "
            "and explicit boundary-addressed topology alternatives"
        ),
        "input_digest": input_digest,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        **copy.deepcopy(detail),
    }
    result["digest"] = stable_digest(result)
    return result


def _identifier(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _Refusal("UNKNOWN_IDENTIFIER_REQUIRED",
                       f"{field} must be a non-empty string", field=field)
    return value.strip()


def _positive(value: Any, *, field: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) <= 0.0):
        raise _Refusal("UNKNOWN_POSITIVE_GEOMETRY_REQUIRED",
                       f"{field} must be finite and positive", field=field)
    return float(value)


def _proposal_claim(value: Any, *, field: str, default_basis: str,
                    default_breaks_when: str) -> Dict[str, Any]:
    if value is None:
        return {
            "state": PROPOSED,
            "basis": default_basis,
            "breaks_when": default_breaks_when,
        }
    if not isinstance(value, Mapping):
        raise _Refusal("UNKNOWN_TYPED_CLAIM_REQUIRED",
                       f"{field} must be a typed claim object", field=field)
    claimed = str(value.get("state", value.get("authority", ""))).upper()
    if claimed != PROPOSED:
        raise _Refusal(
            "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
            f"{field} cannot be observed from one front image",
            field=field, claimed_state=claimed, required_state=PROPOSED,
        )
    basis = value.get("basis", default_basis)
    breaks = value.get("breaks_when", default_breaks_when)
    if (not isinstance(basis, str) or not basis.strip()
            or not isinstance(breaks, str) or not breaks.strip()):
        raise _Refusal("UNKNOWN_TYPED_CLAIM_BASIS_REQUIRED",
                       f"{field} needs basis and breaks_when", field=field)
    result = _plain(value)
    result["state"] = PROPOSED
    result.pop("authority", None)
    result["basis"] = basis.strip()
    result["breaks_when"] = breaks.strip()
    return result


def _normalize_boundary(component_id: str, value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _Refusal("UNKNOWN_BOUNDARY_REQUIRED",
                       f"{component_id}.boundaries entries must be objects")
    boundary_id = _identifier(
        value.get("boundary_id", value.get("port_id")),
        field=f"{component_id}.boundary_id")
    visibility = str(value.get("visibility", "UNKNOWN")).upper()
    if visibility not in _VISIBILITIES:
        raise _Refusal("UNKNOWN_BOUNDARY_VISIBILITY",
                       f"{component_id}/{boundary_id} has invalid visibility",
                       visibility=visibility)
    authority = str(value.get("state", value.get("authority", PROPOSED))).upper()
    if authority not in {OBSERVED, PROPOSED}:
        raise _Refusal("UNKNOWN_BOUNDARY_AUTHORITY",
                       "boundary authority must be OBSERVED or PROPOSED",
                       component_id=component_id, boundary_id=boundary_id)
    if visibility != "FRONT_VISIBLE" and authority == OBSERVED:
        raise _Refusal(
            "UNKNOWN_OCCLUDED_BOUNDARY_AUTHORITY_ESCALATION",
            "rear, occluded, and unknown boundaries cannot be observed from a front image",
            component_id=component_id, boundary_id=boundary_id,
            visibility=visibility, claimed_state=authority,
        )
    role = str(value.get("role", "edge"))
    if role not in _PORT_ROLES:
        raise _Refusal("UNKNOWN_BOUNDARY_ROLE",
                       f"{component_id}/{boundary_id} has invalid role",
                       role=role)
    interface = _identifier(value.get("interface"),
                            field=f"{component_id}/{boundary_id}.interface")
    stretch = value.get("stretch_range", [1.0, 1.0])
    if (not isinstance(stretch, Sequence) or isinstance(stretch, (str, bytes))
            or len(stretch) != 2):
        raise _Refusal("UNKNOWN_STRETCH_RANGE",
                       "stretch_range must contain two positive values")
    lo = _positive(stretch[0], field=f"{component_id}/{boundary_id}.stretch_min")
    hi = _positive(stretch[1], field=f"{component_id}/{boundary_id}.stretch_max")
    if lo > hi:
        raise _Refusal("UNKNOWN_STRETCH_RANGE",
                       "stretch_range minimum cannot exceed maximum")
    basis = value.get(
        "basis", "typed front geometry supplied by an upstream vision step")
    breaks = value.get(
        "breaks_when", "another view or a human boundary edit contradicts it")
    if (not isinstance(basis, str) or not basis.strip()
            or not isinstance(breaks, str) or not breaks.strip()):
        raise _Refusal("UNKNOWN_BOUNDARY_BASIS_REQUIRED",
                       "every boundary needs basis and breaks_when",
                       component_id=component_id, boundary_id=boundary_id)
    return {
        "boundary_id": boundary_id,
        "length_cm": _positive(
            value.get("length_cm"),
            field=f"{component_id}/{boundary_id}.length_cm"),
        "interface": interface,
        "role": role,
        "visibility": visibility,
        "state": authority,
        "basis": basis.strip(),
        "breaks_when": breaks.strip(),
        "stretch_range": [lo, hi],
    }


def _normalize_component(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _Refusal("UNKNOWN_COMPONENT_REQUIRED",
                       "components must contain objects")
    component_id = _identifier(
        value.get("component_id", value.get("node_id")), field="component_id")
    raw_kind = value.get("primitive_kind", value.get("kind"))
    try:
        kind = PrimitiveKind(raw_kind).value
    except (TypeError, ValueError) as exc:
        raise _Refusal(
            "UNKNOWN_GEOMETRIC_PRIMITIVE",
            "components must use an existing garment.structure primitive",
            component_id=component_id, primitive_kind=raw_kind,
            allowed=[item.value for item in PrimitiveKind],
        ) from exc
    dimensions = value.get("dimensions")
    if not isinstance(dimensions, Mapping) or not dimensions:
        raise _Refusal("UNKNOWN_COMPONENT_DIMENSIONS",
                       f"{component_id}.dimensions must be a non-empty object")
    normalized_dimensions: Dict[str, float] = {}
    for name in sorted(dimensions):
        key = _identifier(name, field=f"{component_id}.dimension")
        number = dimensions[name]
        coordinate = key in {"x_cm", "y_cm", "z_cm"} or key.endswith("_angle_deg")
        if coordinate:
            if (isinstance(number, bool) or not isinstance(number, (int, float))
                    or not math.isfinite(float(number))):
                raise _Refusal("UNKNOWN_COMPONENT_DIMENSION",
                               f"{component_id}.{key} must be finite")
            normalized_dimensions[key] = float(number)
        else:
            normalized_dimensions[key] = _positive(
                number, field=f"{component_id}.{key}")
    layer = value.get("layer", 0)
    if (isinstance(layer, bool) or not isinstance(layer, int)
            or not 0 <= layer <= 15):
        raise _Refusal("UNKNOWN_COMPONENT_LAYER",
                       f"{component_id}.layer must be an integer from 0 through 15")
    raw_boundaries = value.get("boundaries", [])
    if (not isinstance(raw_boundaries, Sequence)
            or isinstance(raw_boundaries, (str, bytes))):
        raise _Refusal("UNKNOWN_COMPONENT_BOUNDARIES",
                       f"{component_id}.boundaries must be an array")
    boundaries = [_normalize_boundary(component_id, row)
                  for row in raw_boundaries]
    boundary_ids = [row["boundary_id"] for row in boundaries]
    if len(boundary_ids) != len(set(boundary_ids)):
        raise _Refusal("UNKNOWN_DUPLICATE_BOUNDARY",
                       f"{component_id} boundary ids must be unique")
    zones = value.get("coverage_zones", [])
    if (not isinstance(zones, Sequence) or isinstance(zones, (str, bytes))
            or any(not isinstance(zone, str) or not zone.strip()
                   for zone in zones)):
        raise _Refusal("UNKNOWN_COVERAGE_ZONES",
                       f"{component_id}.coverage_zones must contain strings")
    role = value.get("semantic_role", "unspecified geometric component")
    unit = value.get("garment_unit", component_id)
    role = _identifier(role, field=f"{component_id}.semantic_role")
    unit = _identifier(unit, field=f"{component_id}.garment_unit")
    return {
        "component_id": component_id,
        "primitive_kind": kind,
        "dimensions": normalized_dimensions,
        "layer_hint": layer,
        "semantic_role": role,
        "garment_unit": unit,
        "coverage_zones": sorted(set(zone.strip() for zone in zones)),
        "boundaries": sorted(boundaries, key=lambda row: row["boundary_id"]),
        "rear": _proposal_claim(
            value.get("rear"), field=f"{component_id}.rear",
            default_basis="the rear is absent from the front-only source",
            default_breaks_when="a rear or side view is supplied"),
        "material": _proposal_claim(
            value.get("material"), field=f"{component_id}.material",
            default_basis="appearance does not determine material mechanics",
            default_breaks_when="a material specification or measurement is supplied"),
    }


def _normalize_ref(value: Any, *, field: str,
                   boundaries: Set[Tuple[str, str]]) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        raise _Refusal("UNKNOWN_BOUNDARY_REFERENCE",
                       f"{field} must address a component boundary", field=field)
    component_id = _identifier(
        value.get("component_id", value.get("node_id")),
        field=f"{field}.component_id")
    boundary_id = _identifier(
        value.get("boundary_id", value.get("port_id")),
        field=f"{field}.boundary_id")
    if (component_id, boundary_id) not in boundaries:
        raise _Refusal("UNKNOWN_BOUNDARY_REFERENCE",
                       f"{field} names an unknown boundary",
                       component_id=component_id, boundary_id=boundary_id)
    return {"component_id": component_id, "boundary_id": boundary_id}


def _normalize_alternative(value: Any, *, choice_id: str,
                           boundaries: Set[Tuple[str, str]]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _Refusal("UNKNOWN_TOPOLOGY_ALTERNATIVE",
                       f"{choice_id}.alternatives must contain objects")
    alternative_id = _identifier(value.get("alternative_id"),
                                 field=f"{choice_id}.alternative_id")
    relation = str(value.get("relation", "")).upper()
    if relation not in _RELATIONS:
        raise _Refusal("UNKNOWN_TOPOLOGY_RELATION",
                       "topology relation must be a structural operation",
                       choice_id=choice_id, alternative_id=alternative_id,
                       allowed=sorted(_RELATIONS))
    claimed = str(value.get("state", value.get("authority", PROPOSED))).upper()
    if claimed != PROPOSED:
        raise _Refusal(
            "UNKNOWN_TOPOLOGY_AUTHORITY_ESCALATION",
            "front-derived attachment topology must remain PROPOSED",
            choice_id=choice_id, alternative_id=alternative_id,
            claimed_state=claimed,
        )
    basis = value.get("basis")
    breaks = value.get("breaks_when")
    if (not isinstance(basis, str) or not basis.strip()
            or not isinstance(breaks, str) or not breaks.strip()):
        raise _Refusal("UNKNOWN_TOPOLOGY_BASIS_REQUIRED",
                       "every topology alternative needs basis and breaks_when",
                       choice_id=choice_id, alternative_id=alternative_id)
    parameters = value.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise _Refusal("UNKNOWN_TOPOLOGY_PARAMETERS",
                       "alternative parameters must be an object")
    return {
        "alternative_id": alternative_id,
        "relation": relation,
        "source": _normalize_ref(
            value.get("source"), field=f"{choice_id}/{alternative_id}.source",
            boundaries=boundaries),
        "target": _normalize_ref(
            value.get("target"), field=f"{choice_id}/{alternative_id}.target",
            boundaries=boundaries),
        "state": PROPOSED,
        "basis": basis.strip(),
        "breaks_when": breaks.strip(),
        "contact_zone": str(value.get("contact_zone", "unspecified")).strip()
                        or "unspecified",
        "parameters": _plain(parameters),
    }


def _normalize_choices(value: Any, *,
                       boundaries: Set[Tuple[str, str]]) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or any(not isinstance(row, Mapping) for row in value)):
        raise _Refusal("UNKNOWN_ATTACHMENT_CHOICES",
                       "attachment_choices must be an array of objects")
    if len(value) > _MAX_CHOICE_SETS:
        raise _Refusal("UNKNOWN_ATTACHMENT_CHOICE_LIMIT",
                       f"at most {_MAX_CHOICE_SETS} choice sets are accepted")
    result: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    combinations = 1
    for row in value:
        choice_id = _identifier(row.get("choice_id"), field="choice_id")
        if choice_id in seen:
            raise _Refusal("UNKNOWN_DUPLICATE_ATTACHMENT_CHOICE",
                           "choice ids must be unique", choice_id=choice_id)
        seen.add(choice_id)
        alternatives_value = row.get("alternatives")
        if (not isinstance(alternatives_value, Sequence)
                or isinstance(alternatives_value, (str, bytes))
                or not alternatives_value):
            raise _Refusal("UNKNOWN_TOPOLOGY_ALTERNATIVES_REQUIRED",
                           f"{choice_id} needs at least one alternative")
        alternatives = [_normalize_alternative(
            alternative, choice_id=choice_id, boundaries=boundaries)
            for alternative in alternatives_value]
        alternative_ids = [item["alternative_id"] for item in alternatives]
        if len(alternative_ids) != len(set(alternative_ids)):
            raise _Refusal("UNKNOWN_DUPLICATE_TOPOLOGY_ALTERNATIVE",
                           f"{choice_id} alternative ids must be unique")
        combinations *= len(alternatives)
        if combinations > _MAX_COMBINATIONS:
            raise _Refusal("UNKNOWN_TOPOLOGY_COMBINATION_LIMIT",
                           f"at most {_MAX_COMBINATIONS} topology combinations are accepted")
        result.append({
            "choice_id": choice_id,
            "alternatives": sorted(
                alternatives, key=lambda item: item["alternative_id"]),
        })
    return sorted(result, key=lambda item: item["choice_id"])


def _normalize_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    if request.get("schema") != REQUEST_SCHEMA:
        raise _Refusal("UNKNOWN_LAYERED_VISION_SCHEMA",
                       f"expected schema {REQUEST_SCHEMA}")
    if request.get("front_only") is not True:
        raise _Refusal("UNKNOWN_FRONT_ONLY_SOURCE_REQUIRED",
                       "this composer accepts one structured front-view source")
    source_id = _identifier(request.get("source_id"), field="source_id")
    components_value = request.get("components")
    if (not isinstance(components_value, Sequence)
            or isinstance(components_value, (str, bytes))
            or not components_value):
        raise _Refusal("UNKNOWN_COMPONENTS_REQUIRED",
                       "components must be a non-empty array")
    components = [_normalize_component(row) for row in components_value]
    component_ids = [row["component_id"] for row in components]
    if len(component_ids) != len(set(component_ids)):
        raise _Refusal("UNKNOWN_DUPLICATE_COMPONENT",
                       "component ids must be unique")
    components.sort(key=lambda row: row["component_id"])
    boundaries = {
        (component["component_id"], boundary["boundary_id"])
        for component in components for boundary in component["boundaries"]
    }
    choices = _normalize_choices(
        request.get("attachment_choices", []), boundaries=boundaries)
    return {
        "schema": REQUEST_SCHEMA,
        "source_id": source_id,
        "front_only": True,
        "components": components,
        "attachment_choices": choices,
    }


def _selected_rows(choices: Sequence[Mapping[str, Any]],
                   alternatives: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"choice_id": str(choice["choice_id"]), **copy.deepcopy(dict(alternative))}
        for choice, alternative in zip(choices, alternatives)
    ]


def _solve_layers(components: Sequence[Mapping[str, Any]],
                  selected: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, int]]:
    layers = {str(row["component_id"]): int(row["layer_hint"])
              for row in components}
    edges = [(str(row["source"]["component_id"]),
              str(row["target"]["component_id"]))
             for row in selected if row["relation"] == "LAYER"]
    # outer -> inner edges must be acyclic.  Propagation converts proposal-only
    # layer hints into the smallest candidate-specific ordering that satisfies
    # all explicit alternatives.
    for iteration in range(len(layers) + 1):
        changed = False
        for outer, inner in sorted(edges):
            required = layers[inner] + 1
            if layers[outer] < required:
                layers[outer] = required
                changed = True
                if layers[outer] > 15:
                    return None
        if not changed:
            return layers
        if iteration == len(layers):
            return None
    return layers


def _node(component: Mapping[str, Any], layer: int) -> PrimitiveNode:
    ports = tuple(BoundaryPort(
        str(row["boundary_id"]), float(row["length_cm"]),
        str(row["interface"]), role=str(row["role"]), layer=layer,
        stretch_range=tuple(row["stretch_range"]),
    ) for row in component["boundaries"])
    boundary_evidence = {
        str(row["boundary_id"]): {
            "visibility": row["visibility"],
            "state": row["state"],
            "basis": row["basis"],
            "breaks_when": row["breaks_when"],
        }
        for row in component["boundaries"]
    }
    return PrimitiveNode(
        str(component["component_id"]), PrimitiveKind(component["primitive_kind"]),
        copy.deepcopy(component["dimensions"]), ports, layer,
        {
            "state": PROPOSED,
            "semantic_role": component["semantic_role"],
            "garment_unit": component["garment_unit"],
            "coverage_zones": list(component["coverage_zones"]),
            "layer_authority": "PROPOSED_CANDIDATE_ORDER",
            "dimension_authority": "PROPOSED_FRONT_GEOMETRY",
            "boundary_evidence": boundary_evidence,
            "rear": copy.deepcopy(component["rear"]),
            "material": copy.deepcopy(component["material"]),
        },
    )


def _operation(selected: Mapping[str, Any]) -> Optional[StructureOperation]:
    relation = str(selected["relation"])
    if relation in {"CONTACT", "SEPARATE"}:
        return None
    parameters = copy.deepcopy(dict(selected["parameters"]))
    parameters.update({
        "state": PROPOSED,
        "basis": selected["basis"],
        "breaks_when": selected["breaks_when"],
        "front_only_topology": True,
    })
    return StructureOperation(
        f"{selected['choice_id']}:{selected['alternative_id']}",
        OperationKind(relation),
        PortRef(selected["source"]["component_id"],
                selected["source"]["boundary_id"]),
        PortRef(selected["target"]["component_id"],
                selected["target"]["boundary_id"]),
        parameters,
    )


def _relation_key(source: str, target: str, zone: str) -> Tuple[str, str, str]:
    return source, target, zone


def _constraints(components: Sequence[Mapping[str, Any]], layers: Mapping[str, int],
                 selected: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    attachment: List[Dict[str, Any]] = []
    layer_order: List[Dict[str, Any]] = []
    contact: List[Dict[str, Any]] = []
    explicit_layer_keys: Set[Tuple[str, str, str]] = set()
    explicit_pair_relations: Set[frozenset[str]] = set()
    for row in selected:
        source = row["source"]["component_id"]
        target = row["target"]["component_id"]
        zone = row["contact_zone"]
        relation = row["relation"]
        common = {
            "choice_id": row["choice_id"],
            "alternative_id": row["alternative_id"],
            "source": copy.deepcopy(row["source"]),
            "target": copy.deepcopy(row["target"]),
            "relation": relation,
            "state": PROPOSED,
            "basis": row["basis"],
            "breaks_when": row["breaks_when"],
        }
        attachment.append(common)
        explicit_pair_relations.add(frozenset((source, target)))
        if relation == "LAYER":
            layer_order.append({
                "outer_component_id": source,
                "inner_component_id": target,
                "contact_zone": zone,
                "outer_layer": layers[source],
                "inner_layer": layers[target],
                "state": PROPOSED,
                "basis": row["basis"],
                "breaks_when": row["breaks_when"],
            })
            explicit_layer_keys.add(_relation_key(source, target, zone))
        if relation in {"LAYER", "CONTACT", "OVERLAP"}:
            contact.append({
                "component_ids": sorted((source, target)),
                "contact_zone": zone,
                "mode": "NON_PENETRATION",
                "friction": "UNKNOWN_MATERIAL_REQUIRED",
                "state": PROPOSED,
                "basis": row["basis"],
                "breaks_when": row["breaks_when"],
            })

    # Numeric layer hints are only proposal geometry.  They still provide a
    # deterministic relation for components whose declared coverage overlaps.
    unresolved_layer_pairs: List[Dict[str, Any]] = []
    for left, right in itertools.combinations(components, 2):
        left_id = str(left["component_id"])
        right_id = str(right["component_id"])
        shared = sorted(set(left["coverage_zones"]) & set(right["coverage_zones"]))
        if not shared:
            continue
        pair = frozenset((left_id, right_id))
        if layers[left_id] == layers[right_id]:
            if pair not in explicit_pair_relations:
                unresolved_layer_pairs.append({
                    "component_ids": sorted((left_id, right_id)),
                    "shared_zones": shared,
                    "state": REVIEW,
                    "why": "overlapping components have no determined inside/outside order",
                })
            continue
        outer, inner = ((left_id, right_id) if layers[left_id] > layers[right_id]
                        else (right_id, left_id))
        for zone in shared:
            key = _relation_key(outer, inner, zone)
            if key in explicit_layer_keys:
                continue
            layer_order.append({
                "outer_component_id": outer,
                "inner_component_id": inner,
                "contact_zone": zone,
                "outer_layer": layers[outer],
                "inner_layer": layers[inner],
                "state": PROPOSED,
                "basis": "explicit component layer hints and overlapping coverage zones",
                "breaks_when": "a side/rear view or human layer edit reverses the order",
            })
            contact.append({
                "component_ids": sorted((outer, inner)),
                "contact_zone": zone,
                "mode": "NON_PENETRATION",
                "friction": "UNKNOWN_MATERIAL_REQUIRED",
                "state": PROPOSED,
                "basis": "derived from the candidate-specific layer order",
                "breaks_when": "the components do not overlap in the completed 3D geometry",
            })

    def ordered(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(rows, key=lambda row: stable_digest(row))

    return {
        "attachment": ordered(attachment),
        "layer_order": ordered(layer_order),
        "contact": ordered(contact),
        "unresolved_layer_order": ordered(unresolved_layer_pairs),
    }


def _candidate(normalized: Mapping[str, Any], source_digest: str,
               selected: Sequence[Mapping[str, Any]]) -> Tuple[
                   Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    layers = _solve_layers(normalized["components"], selected)
    selection = [{"choice_id": row["choice_id"],
                  "alternative_id": row["alternative_id"]}
                 for row in selected]
    if layers is None:
        return None, {
            "selected_alternatives": selection,
            "verdict": "UNKNOWN_LAYER_ORDER_CYCLE",
            "why": "the selected layer constraints are cyclic or exceed layer 15",
        }
    graph = StructureGraph(
        tuple(_node(component, layers[str(component["component_id"])])
              for component in normalized["components"]),
        tuple(operation for operation in (_operation(row) for row in selected)
              if operation is not None),
    )
    validation = validate_structure(graph)
    if validation.get("verdict") != ANSWER:
        return None, {
            "selected_alternatives": selection,
            "verdict": validation.get("verdict", "UNKNOWN_INVALID_STRUCTURE"),
            "why": validation.get("why", "the generated structure is invalid"),
        }
    constraints = _constraints(normalized["components"], layers, selected)
    identity = {"source_digest": source_digest,
                "selected_alternatives": selection,
                "layers": layers}
    candidate_id = "layered-" + stable_digest(identity)[:16]
    result = {
        "candidate_id": candidate_id,
        "state": PROPOSED,
        "selected_alternatives": selection,
        "structure_graph": graph.as_dict(),
        "structure_digest": graph.digest,
        "constraints": constraints,
        "authority": {
            "front_visible_boundaries_may_be_observed": True,
            "rear": PROPOSED,
            "material": PROPOSED,
            "occluded_boundaries": PROPOSED,
            "attachment_topology": PROPOSED,
            "layer_order": PROPOSED,
        },
        "requires_human_approval": True,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["candidate_digest"] = stable_digest(result)
    return result, None


def compose(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Compose all feasible primitive topologies from structured vision data.

    ``attachment_choices`` is a list of independent choice sets.  A set with
    one alternative is a fixed proposal; a set with multiple alternatives is
    an ambiguity.  The Cartesian product is validated geometrically, invalid
    combinations are reported, and no feasible alternative is auto-selected.
    """
    if not isinstance(request, Mapping):
        return _unknown(request, "UNKNOWN_LAYERED_VISION_REQUEST",
                        "request must be an object")
    original = copy.deepcopy(dict(request))
    try:
        normalized = _normalize_request(request)
        source_digest = stable_digest(normalized)
        choices = normalized["attachment_choices"]
        products = (itertools.product(*[choice["alternatives"]
                                        for choice in choices])
                    if choices else [tuple()])
        candidates: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        for alternatives in products:
            selected = _selected_rows(choices, alternatives)
            candidate, failure = _candidate(normalized, source_digest, selected)
            if candidate is not None:
                candidates.append(candidate)
            elif failure is not None:
                rejected.append(failure)
        candidates.sort(key=lambda row: row["candidate_id"])
        rejected.sort(key=stable_digest)
        if not candidates:
            return _unknown(
                original, "UNKNOWN_NO_FEASIBLE_TOPOLOGY",
                "none of the explicit attachment alternatives forms a valid structure",
                rejected_combinations=rejected,
            )
        ambiguous_topology = len(candidates) > 1
        unresolved_layers = sorted({
            stable_digest(row): row
            for candidate in candidates
            for row in candidate["constraints"]["unresolved_layer_order"]
        }.values(), key=stable_digest)
        requires_choice = ambiguous_topology or bool(unresolved_layers)
        if ambiguous_topology:
            reason_code = "REVIEW_JOIN_TOPOLOGY_CHOICE_REQUIRED"
            why = "multiple geometrically feasible attachment topologies require human choice"
        elif unresolved_layers:
            reason_code = "REVIEW_LAYER_ORDER_REQUIRED"
            why = "overlapping components need an explicit inside/outside choice"
        else:
            reason_code = "PROPOSED_GEOMETRY_COMPOSED"
            why = "one explicit primitive topology validates geometrically"
        result = {
            "schema": SCHEMA,
            "verdict": REVIEW if requires_choice else PROPOSED,
            "state": PROPOSED,
            "reason_code": reason_code,
            "why": why,
            "source_id": normalized["source_id"],
            "source_digest": source_digest,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "rejected_combinations": rejected,
            "human_choice": {
                "required": requires_choice,
                "reason": reason_code if requires_choice else None,
                "candidate_ids": [row["candidate_id"] for row in candidates],
                "selected_candidate_id": None,
                "unresolved_layer_order": unresolved_layers,
            },
            "unobserved": {
                "rear": PROPOSED,
                "material": PROPOSED,
                "occluded_boundaries": PROPOSED,
            },
            "claims": {
                "pixels_interpreted_here": False,
                "garment_name_classification_used": False,
                "corpus_used": False,
                "candidate_auto_selected": False,
                "rear_observed_from_front": False,
                "material_observed_from_front": False,
            },
            "requires_human_approval": True,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "provenance": {
                "method": "deterministic primitive composition and graph validation",
                "structure_schema": "garment.structure.v1",
            },
        }
        result["digest"] = stable_digest(result)
        return result
    except _Refusal as exc:
        return _unknown(original, exc.code, exc.why, **exc.detail)
    except (TypeError, ValueError, OverflowError) as exc:
        return _unknown(original, "UNKNOWN_LAYERED_VISION_MALFORMED", str(exc))


compose_layered_garment = compose
generate = compose
