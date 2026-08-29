# -*- coding: utf-8 -*-
"""Route a garment instance graph by construction, never by garment name.

The pipeline in this module is deliberately small and authority preserving::

    garment.instance-graph.v1
        -> typed construction-regime selection
        -> target representation route
        -> manufacturing representation route

It does not draft a hidden rear, turn a model proposal into an observation, or
certify manufacturing.  The output describes which existing geometry concept
can receive the graph and, where possible, preserves explicit rectangular,
drape, wrap, or knit inputs.  Missing inputs remain REVIEW/UNKNOWN.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


INSTANCE_GRAPH_SCHEMA = "garment.instance-graph.v1"
SCHEMA = "garment.construction-route.v1"


class ConstructionRegime(str, Enum):
    SEWN_FITTED = "SEWN_FITTED"
    SEWN_RECTILINEAR = "SEWN_RECTILINEAR"
    DRAPED_UNSTITCHED = "DRAPED_UNSTITCHED"
    WRAPPED = "WRAPPED"
    KNITTED = "KNITTED"
    MODULAR_LAYERED = "MODULAR_LAYERED"
    UNKNOWN_CONSTRUCTION = "UNKNOWN_CONSTRUCTION"


class ManufacturingRepresentation(str, Enum):
    PATTERN_PIECES = "PATTERN_PIECES"
    RECTANGULAR_CUT_PLAN = "RECTANGULAR_CUT_PLAN"
    DRAPE_PLAN = "DRAPE_PLAN"
    KNIT_SPECIFICATION = "KNIT_SPECIFICATION"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN_MANUFACTURING_REPRESENTATION"


class TargetRepresentation(str, Enum):
    DRESSED_FORM = "DRESSED_FORM_TARGET"
    RECTILINEAR_ASSEMBLY = "RECTILINEAR_ASSEMBLY_TARGET"
    DRAPED_SURFACE = "DRAPED_SURFACE_TARGET"
    WRAPPED_SURFACE = "WRAPPED_OVERLAP_TARGET"
    KNIT_SURFACE = "KNIT_SURFACE_TARGET"
    LAYERED_COMPOSITE = "LAYERED_COMPOSITE_TARGET"
    UNKNOWN = "UNKNOWN_TARGET_REPRESENTATION"


_SOURCE_KINDS = {
    "MODEL_PROPOSAL", "HUMAN_INPUT", "OBSERVED_EXTRACTION",
    "DETERMINISTIC_ENGINE",
}
_STATES = {
    "OBSERVED", "MEASURED", "HUMAN_CONFIRMED", "REQUESTED", "DERIVED",
    "PROPOSED", "UNKNOWN", "UNOBSERVED",
}
_METHODS = {"SEWN", "DRAPED", "WRAPPED", "KNITTED", "UNKNOWN"}
_CUT_GEOMETRIES = {
    "FITTED_PANEL", "RECTANGLE", "FREEFORM_PANEL", "NO_CUT", "UNKNOWN",
}
_FITS = {"FITTED", "LOOSE", "BODY_INDEPENDENT", "UNKNOWN"}
_CONNECTIONS = {
    "SEAM", "DRAPE_ANCHOR", "WRAP_OVERLAP", "KNIT_CONTINUITY",
    "MODULE_ATTACHMENT", "LAYER", "NONE", "UNKNOWN",
}
_SHAPING = {
    "DART", "GATHER", "PLEAT", "GORE", "SHAPED_SEAM", "EASE",
    "CURVED_SEAM",
}


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
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
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _enum(value: Any, vocabulary: Set[str], *, field: str) -> str:
    token = str(value if value is not None else "UNKNOWN").upper()
    if token not in vocabulary:
        raise ValueError(f"{field} is outside the closed vocabulary: {token}")
    return token


def _positive(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0.0 else None


def _node_ref(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, Mapping):
        return _text(value.get("node_id"))
    return None


def _refusal(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNKNOWN",
        "why": why,
        "how_to_close": "supply a valid typed garment.instance-graph.v1",
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        **detail,
    }


def _normalise_graph(value: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(value, Mapping) or value.get("schema") != INSTANCE_GRAPH_SCHEMA:
        raise ValueError(f"schema must be exactly {INSTANCE_GRAPH_SCHEMA}")
    graph_id = _text(value.get("graph_id"))
    if not graph_id:
        raise ValueError("graph_id is required")
    source = value.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("source with kind and front_only is required")
    source_kind = _enum(source.get("kind"), _SOURCE_KINDS, field="source.kind")
    if not isinstance(source.get("front_only"), bool):
        raise ValueError("source.front_only must be boolean")
    reviews: List[Dict[str, Any]] = []

    def authority_bound_state(claimed: str, *, subject: str) -> str:
        if source_kind != "MODEL_PROPOSAL":
            return claimed
        bounded = ("UNKNOWN" if claimed in {"UNKNOWN", "UNOBSERVED"}
                   else "PROPOSED")
        if bounded != claimed:
            reviews.append({
                "code": "REVIEW_MODEL_LOCAL_AUTHORITY_REJECTED",
                "state": "REVIEW",
                "subject": subject,
                "claimed_state": claimed,
                "bounded_state": bounded,
                "why": "model node/relation output cannot become an observed, measured, requested, derived, or confirmed fact",
            })
        return bounded

    raw_nodes = value.get("nodes")
    if not _sequence(raw_nodes) or not raw_nodes:
        raise ValueError("nodes must be a non-empty array")
    nodes: List[Dict[str, Any]] = []
    node_ids: Set[str] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, Mapping):
            raise ValueError(f"node {index} must be an object")
        node_id = _text(raw.get("node_id"))
        if not node_id or node_id in node_ids:
            raise ValueError("node ids must be non-empty and unique")
        node_ids.add(node_id)
        construction = raw.get("construction")
        if not isinstance(construction, Mapping):
            raise ValueError(f"{node_id}.construction is required")
        method = _enum(construction.get("method"), _METHODS,
                       field=f"{node_id}.construction.method")
        cut = _enum(construction.get("cut_geometry"), _CUT_GEOMETRIES,
                    field=f"{node_id}.construction.cut_geometry")
        fit = _enum(construction.get("fit"), _FITS,
                    field=f"{node_id}.construction.fit")
        raw_shaping = construction.get("shaping", [])
        if not _sequence(raw_shaping):
            raise ValueError(f"{node_id}.construction.shaping must be an array")
        shaping = sorted({str(item).upper() for item in raw_shaping})
        state = authority_bound_state(
            _enum(raw.get("state", "PROPOSED"), _STATES,
                  field=f"{node_id}.state"),
            subject=f"node:{node_id}",
        )
        layer = raw.get("layer", 0)
        if isinstance(layer, bool) or not isinstance(layer, int) or layer < 0:
            raise ValueError(f"{node_id}.layer must be a non-negative integer")
        dimensions = raw.get("dimensions_cm", construction.get("dimensions_cm", {}))
        if not isinstance(dimensions, Mapping):
            raise ValueError(f"{node_id}.dimensions_cm must be an object")
        finite_dimensions: Dict[str, float] = {}
        for key, dimension in dimensions.items():
            number = _positive(dimension)
            if number is None:
                raise ValueError(f"{node_id}.dimensions_cm.{key} must be positive")
            finite_dimensions[str(key)] = number
        knit = construction.get("knit", {})
        if not isinstance(knit, Mapping):
            raise ValueError(f"{node_id}.construction.knit must be an object")
        nodes.append({
            "node_id": node_id,
            "primitive_kind": str(raw.get("primitive_kind", raw.get("kind", "UNKNOWN"))).upper(),
            "method": method,
            "cut_geometry": cut,
            "fit": fit,
            "shaping": shaping,
            "dimensions_cm": finite_dimensions,
            "knit": _plain(knit),
            "layer": layer,
            "state": state,
        })

    raw_relations = value.get("relations", value.get("operations", []))
    if not _sequence(raw_relations):
        raise ValueError("relations must be an array")
    relations: List[Dict[str, Any]] = []
    relation_ids: Set[str] = set()
    for index, raw in enumerate(raw_relations):
        if not isinstance(raw, Mapping):
            raise ValueError(f"relation {index} must be an object")
        relation_id = (_text(raw.get("relation_id"))
                       or _text(raw.get("operation_id")))
        if not relation_id or relation_id in relation_ids:
            raise ValueError("relation ids must be non-empty and unique")
        relation_ids.add(relation_id)
        source_id = _node_ref(raw.get("source"))
        target_id = _node_ref(raw.get("target"))
        if not source_id or source_id not in node_ids:
            raise ValueError(f"{relation_id}.source must reference a graph node")
        if target_id is not None and target_id not in node_ids:
            raise ValueError(f"{relation_id}.target references an unknown node")
        connection_value = raw.get("connection", "UNKNOWN")
        # Existing garment.structure.v1 LAYER operations carry enough typed
        # information to establish layering, but JOIN/OVERLAP do not establish
        # a sewing or wrap method without an explicit connection value.
        if (connection_value is None or str(connection_value).upper() == "UNKNOWN") and str(raw.get("kind", "")).upper() == "LAYER":
            connection_value = "LAYER"
        connection = _enum(connection_value, _CONNECTIONS,
                           field=f"{relation_id}.connection")
        state = authority_bound_state(
            _enum(raw.get("state", "PROPOSED"), _STATES,
                  field=f"{relation_id}.state"),
            subject=f"relation:{relation_id}",
        )
        parameters = raw.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise ValueError(f"{relation_id}.parameters must be an object")
        relations.append({
            "relation_id": relation_id,
            "kind": str(raw.get("kind", "UNKNOWN")).upper(),
            "connection": connection,
            "source": source_id,
            "target": target_id,
            "parameters": _plain(parameters),
            "state": state,
        })

    proposed = value.get("proposed_construction_regime")
    if proposed is not None:
        token = str(proposed).upper()
        if token not in {item.value for item in ConstructionRegime}:
            reviews.append({
                "code": "REVIEW_MODEL_CONSTRUCTION_PROPOSAL_UNKNOWN",
                "state": "REVIEW",
                "why": f"model proposed unsupported construction regime {token}",
            })
            proposed = None
        else:
            proposed = token

    normalised = {
        "graph_id": graph_id,
        "garment_name": _text(value.get("garment_name")),
        "source": {"kind": source_kind, "front_only": source["front_only"]},
        "nodes": nodes,
        "relations": relations,
        "rear": _plain(value.get("rear", {})) if isinstance(value.get("rear", {}), Mapping) else {},
        "proposed_construction_regime": proposed,
        "claimed_manufacturing_ready": bool(value.get("manufacturing_ready", False)),
        "claimed_manufacturing_certified": bool(value.get("manufacturing_certified", False)),
    }
    return normalised, reviews


def _node_regime(node: Mapping[str, Any]) -> ConstructionRegime:
    method = node["method"]
    if method == "SEWN":
        shaped = (node["fit"] == "FITTED"
                  or node["cut_geometry"] == "FITTED_PANEL"
                  or bool(set(node["shaping"]) & _SHAPING))
        if shaped:
            return ConstructionRegime.SEWN_FITTED
        if node["cut_geometry"] == "RECTANGLE":
            return ConstructionRegime.SEWN_RECTILINEAR
        return ConstructionRegime.UNKNOWN_CONSTRUCTION
    if method == "DRAPED":
        return ConstructionRegime.DRAPED_UNSTITCHED
    if method == "WRAPPED":
        return ConstructionRegime.WRAPPED
    if method == "KNITTED":
        return ConstructionRegime.KNITTED
    return ConstructionRegime.UNKNOWN_CONSTRUCTION


def _relation_regimes(relations: Iterable[Mapping[str, Any]]) -> Dict[str, Set[ConstructionRegime]]:
    result: Dict[str, Set[ConstructionRegime]] = defaultdict(set)
    mapping = {
        "DRAPE_ANCHOR": ConstructionRegime.DRAPED_UNSTITCHED,
        "WRAP_OVERLAP": ConstructionRegime.WRAPPED,
        "KNIT_CONTINUITY": ConstructionRegime.KNITTED,
    }
    for relation in relations:
        inferred = mapping.get(relation["connection"])
        if inferred is None:
            continue
        result[relation["source"]].add(inferred)
        if relation["target"] is not None:
            result[relation["target"]].add(inferred)
    return result


def _select_regime(graph: Mapping[str, Any]) -> Tuple[ConstructionRegime, Dict[str, ConstructionRegime], List[Dict[str, Any]]]:
    reviews: List[Dict[str, Any]] = []
    relation_signals = _relation_regimes(graph["relations"])
    node_regimes: Dict[str, ConstructionRegime] = {}
    seam_nodes: Set[str] = set()
    for relation in graph["relations"]:
        if relation["connection"] == "SEAM":
            seam_nodes.add(relation["source"])
            if relation["target"] is not None:
                seam_nodes.add(relation["target"])

    for node in graph["nodes"]:
        node_id = node["node_id"]
        selected = _node_regime(node)
        signals = relation_signals.get(node_id, set())
        if selected == ConstructionRegime.UNKNOWN_CONSTRUCTION and len(signals) == 1:
            selected = next(iter(signals))
        elif signals and (selected not in signals
                          and selected != ConstructionRegime.UNKNOWN_CONSTRUCTION):
            reviews.append({
                "code": "REVIEW_CONSTRUCTION_SIGNAL_CONTESTED",
                "state": "REVIEW",
                "node_id": node_id,
                "why": "node construction and relation construction disagree",
                "node_regime": selected.value,
                "relation_regimes": sorted(item.value for item in signals),
            })
            selected = ConstructionRegime.UNKNOWN_CONSTRUCTION
        if (selected in {ConstructionRegime.DRAPED_UNSTITCHED,
                         ConstructionRegime.WRAPPED}
                and node_id in seam_nodes):
            reviews.append({
                "code": "REVIEW_UNSTITCHED_CONSTRUCTION_HAS_SEAM",
                "state": "REVIEW", "node_id": node_id,
                "why": "an unstitched drape/wrap node also carries an explicit seam",
            })
            selected = ConstructionRegime.UNKNOWN_CONSTRUCTION
        node_regimes[node_id] = selected

    layered = (len({node["layer"] for node in graph["nodes"]}) > 1
               or any(relation["connection"] in {"LAYER", "MODULE_ATTACHMENT"}
                      for relation in graph["relations"]))
    regimes = set(node_regimes.values())
    known = regimes - {ConstructionRegime.UNKNOWN_CONSTRUCTION}
    has_unknown = ConstructionRegime.UNKNOWN_CONSTRUCTION in regimes
    if layered and len(graph["nodes"]) > 1:
        selected = ConstructionRegime.MODULAR_LAYERED
        if has_unknown:
            reviews.append({
                "code": "REVIEW_LAYER_COMPONENT_CONSTRUCTION_UNKNOWN",
                "state": "REVIEW",
                "why": "layering is explicit but at least one component construction is unknown",
            })
    elif has_unknown:
        selected = ConstructionRegime.UNKNOWN_CONSTRUCTION
    elif known <= {ConstructionRegime.SEWN_FITTED,
                   ConstructionRegime.SEWN_RECTILINEAR}:
        selected = (ConstructionRegime.SEWN_FITTED
                    if ConstructionRegime.SEWN_FITTED in known
                    else ConstructionRegime.SEWN_RECTILINEAR)
    elif len(known) == 1:
        selected = next(iter(known))
    else:
        selected = ConstructionRegime.UNKNOWN_CONSTRUCTION
        reviews.append({
            "code": "REVIEW_CONSTRUCTION_COMPOSITION_RELATION_REQUIRED",
            "state": "REVIEW",
            "why": "mixed construction regimes need an explicit layer/module relation",
        })
    return selected, node_regimes, reviews


def _authority(graph: Mapping[str, Any], reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    source_kind = graph["source"]["kind"]
    front_only = graph["source"]["front_only"]
    rear = graph["rear"]
    claimed_rear = str(rear.get("state", "UNKNOWN")).upper()
    if claimed_rear not in _STATES:
        claimed_rear = "UNKNOWN"
        reviews.append({
            "code": "REVIEW_REAR_STATE_UNKNOWN", "state": "REVIEW",
            "why": "rear.state is outside the authority vocabulary",
        })
    if source_kind == "MODEL_PROPOSAL":
        rear_state = "PROPOSED" if claimed_rear not in {"UNKNOWN", "UNOBSERVED"} else "UNKNOWN"
        if claimed_rear in {"OBSERVED", "MEASURED", "HUMAN_CONFIRMED"}:
            reviews.append({
                "code": "REVIEW_MODEL_REAR_AUTHORITY_REJECTED",
                "state": "REVIEW",
                "why": "model output cannot make rear geometry observed or confirmed",
            })
    elif front_only and claimed_rear in {"OBSERVED", "MEASURED"}:
        rear_state = "UNKNOWN"
        reviews.append({
            "code": "REVIEW_FRONT_ONLY_REAR_OBSERVATION_REJECTED",
            "state": "REVIEW",
            "why": "a front-only source cannot observe or measure the rear",
        })
    else:
        rear_state = claimed_rear

    if graph["claimed_manufacturing_ready"] or graph["claimed_manufacturing_certified"]:
        reviews.append({
            "code": "REVIEW_MANUFACTURING_AUTHORITY_NOT_GRANTED",
            "state": "REVIEW",
            "why": "construction routing cannot grant manufacturing readiness or certification",
        })
    proposal_ceiling = "PROPOSED" if source_kind == "MODEL_PROPOSAL" else "DERIVED"
    return {
        "source_kind": source_kind,
        "construction_state": proposal_ceiling,
        "rear": {
            "claimed_state": claimed_rear,
            "state": rear_state,
            "observed": rear_state in {"OBSERVED", "MEASURED"},
            "promoted": False,
            "front_only_source": front_only,
        },
        "manufacturing": {
            "state": "PROPOSED",
            "ready": False,
            "certified": False,
            "promoted": False,
        },
        "fact_promotions": [],
    }


def _target_kind(regime: ConstructionRegime) -> TargetRepresentation:
    return {
        ConstructionRegime.SEWN_FITTED: TargetRepresentation.DRESSED_FORM,
        ConstructionRegime.SEWN_RECTILINEAR: TargetRepresentation.RECTILINEAR_ASSEMBLY,
        ConstructionRegime.DRAPED_UNSTITCHED: TargetRepresentation.DRAPED_SURFACE,
        ConstructionRegime.WRAPPED: TargetRepresentation.WRAPPED_SURFACE,
        ConstructionRegime.KNITTED: TargetRepresentation.KNIT_SURFACE,
        ConstructionRegime.MODULAR_LAYERED: TargetRepresentation.LAYERED_COMPOSITE,
        ConstructionRegime.UNKNOWN_CONSTRUCTION: TargetRepresentation.UNKNOWN,
    }[regime]


def _target_representation(regime: ConstructionRegime, graph: Mapping[str, Any],
                           authority: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "kind": _target_kind(regime).value,
        "state": authority["construction_state"] if regime != ConstructionRegime.UNKNOWN_CONSTRUCTION else "UNKNOWN",
        "source_node_ids": sorted(node["node_id"] for node in graph["nodes"]),
        "layer_order": [
            {"node_id": node["node_id"], "layer": node["layer"]}
            for node in sorted(graph["nodes"], key=lambda row: (row["layer"], row["node_id"]))
        ],
        "rear": copy.deepcopy(authority["rear"]),
        "generated_geometry": False,
        "current_support": "TYPED_ROUTE_AND_EXPLICIT_INPUT_PRESERVATION",
        "supported_operations": [
            "PRESERVE_TYPED_INSTANCE_GRAPH",
            "BIND_SELECTED_BODY_AND_SAME_CAMERA_TARGET_DOWNSTREAM",
            "KEEP_LAYER_AND_ATTACHMENT_IDENTITY",
        ],
        "not_supported": [
            "INFER_REAR_AS_FACT", "RECONSTRUCT_HIGH_DETAIL_3D_IN_THIS_MODULE",
            "AUTO_ADOPT_MODEL_PROPOSAL",
        ],
    }


def _dimension(node: Mapping[str, Any], *names: str) -> Optional[float]:
    dimensions = node["dimensions_cm"]
    return next((float(dimensions[name]) for name in names if name in dimensions), None)


def _rectangular_plan(nodes: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rectangles: List[Dict[str, Any]] = []
    reviews: List[Dict[str, Any]] = []
    for node in nodes:
        if node["cut_geometry"] != "RECTANGLE":
            continue
        width = _dimension(node, "width", "width_cm")
        length = _dimension(node, "length", "length_cm", "height", "height_cm")
        if width is None or length is None:
            reviews.append({
                "code": "REVIEW_RECTANGLE_DIMENSIONS_REQUIRED",
                "state": "REVIEW", "node_id": node["node_id"],
                "why": "an explicit rectangle needs positive width and length in cm",
            })
            continue
        rectangles.append({
            "node_id": node["node_id"], "width_cm": width,
            "length_cm": length, "cut_count": None,
            "state": node["state"], "geometry_source": "EXPLICIT_DIMENSIONS",
        })
    return rectangles, reviews


def _relations_for(nodes: Set[str], relations: Sequence[Mapping[str, Any]],
                   connection: str) -> List[Dict[str, Any]]:
    return [
        copy.deepcopy(dict(relation)) for relation in relations
        if relation["connection"] == connection
        and relation["source"] in nodes
        and (relation["target"] is None or relation["target"] in nodes)
    ]


def _single_manufacturing(regime: ConstructionRegime,
                          nodes: Sequence[Mapping[str, Any]],
                          relations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    node_ids = {node["node_id"] for node in nodes}
    common: Dict[str, Any] = {
        "state": "PROPOSED" if regime != ConstructionRegime.UNKNOWN_CONSTRUCTION else "UNKNOWN",
        "source_node_ids": sorted(node_ids),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
        "not_supported": [
            "INFER_MISSING_REAR", "INVENT_SEAM_OR_CLOSURE_DETAILS",
            "CERTIFY_FIT_STRENGTH_COMFORT_OR_PRODUCTION",
        ],
    }
    reviews: List[Dict[str, Any]] = []
    if regime == ConstructionRegime.SEWN_FITTED:
        return {**common,
                "kind": ManufacturingRepresentation.PATTERN_PIECES.value,
                "current_support": "ROUTE_ONLY",
                "piece_sources": sorted(node_ids),
                "supported_operations": [
                    "ROUTE_GARMENT_STRUCTURE_V1_TO_STRUCTURE_TO_PATTERN",
                    "PRESERVE_EXPLICIT_SEAM_TOPOLOGY",
                ],
                "implementation_routes": [
                    "photoloset.garment_structure",
                    "photoloset.structure_to_pattern.compile",
                ],
                "review_items": reviews}
    if regime == ConstructionRegime.SEWN_RECTILINEAR:
        rectangles, reviews = _rectangular_plan(nodes)
        return {**common,
                "kind": ManufacturingRepresentation.RECTANGULAR_CUT_PLAN.value,
                "current_support": "EXPLICIT_RECTANGLES_ONLY",
                "rectangles": rectangles,
                "seams": _relations_for(node_ids, relations, "SEAM"),
                "supported_operations": [
                    "EMIT_EXPLICIT_RECTANGLE_DIMENSIONS",
                    "PRESERVE_EXPLICIT_SEAM_RELATIONS",
                ],
                "review_items": reviews}
    if regime in {ConstructionRegime.DRAPED_UNSTITCHED,
                  ConstructionRegime.WRAPPED}:
        anchors = _relations_for(node_ids, relations, "DRAPE_ANCHOR")
        overlaps = _relations_for(node_ids, relations, "WRAP_OVERLAP")
        if regime == ConstructionRegime.DRAPED_UNSTITCHED and not anchors:
            reviews.append({
                "code": "REVIEW_DRAPE_ANCHORS_REQUIRED", "state": "REVIEW",
                "why": "no explicit drape anchor was supplied",
            })
        if regime == ConstructionRegime.WRAPPED and not overlaps:
            reviews.append({
                "code": "REVIEW_WRAP_OVERLAP_REQUIRED", "state": "REVIEW",
                "why": "no explicit wrap overlap/closure relation was supplied",
            })
        return {**common,
                "kind": ManufacturingRepresentation.DRAPE_PLAN.value,
                "plan_subtype": "WRAP_PLAN" if regime == ConstructionRegime.WRAPPED else "UNSTITCHED_DRAPE_PLAN",
                "current_support": "EXPLICIT_ANCHOR_AND_OVERLAP_PRESERVATION_ONLY",
                "anchors": anchors, "overlaps": overlaps,
                "supported_operations": [
                    "PRESERVE_EXPLICIT_DRAPE_ANCHORS",
                    "PRESERVE_EXPLICIT_WRAP_OVERLAPS",
                ],
                "not_supported": common["not_supported"] + [
                    "AUTO_FLATTEN_DRAPE", "PHYSICALLY_VALIDATE_DRAPE_IN_THIS_MODULE",
                ],
                "review_items": reviews}
    if regime == ConstructionRegime.KNITTED:
        specifications = []
        for node in nodes:
            knit = copy.deepcopy(node["knit"])
            missing = [key for key in ("gauge", "yarn") if not knit.get(key)]
            if missing:
                reviews.append({
                    "code": "REVIEW_KNIT_SPECIFICATION_REQUIRED",
                    "state": "REVIEW", "node_id": node["node_id"],
                    "missing": missing,
                    "why": "knit gauge and yarn must be supplied explicitly",
                })
            specifications.append({
                "node_id": node["node_id"], "specification": knit,
                "state": node["state"], "computed_stitch_counts": False,
            })
        return {**common,
                "kind": ManufacturingRepresentation.KNIT_SPECIFICATION.value,
                "current_support": "EXPLICIT_SPECIFICATION_PRESERVATION_ONLY",
                "specifications": specifications,
                "continuities": _relations_for(node_ids, relations, "KNIT_CONTINUITY"),
                "supported_operations": [
                    "PRESERVE_EXPLICIT_GAUGE_YARN_AND_STITCH_COUNTS",
                    "PRESERVE_EXPLICIT_KNIT_CONTINUITY",
                ],
                "not_supported": common["not_supported"] + [
                    "GENERATE_LOOP_LEVEL_KNIT_PROGRAM", "INVENT_GAUGE_OR_STITCH_COUNTS",
                ],
                "review_items": reviews}
    return {**common,
            "kind": ManufacturingRepresentation.UNKNOWN.value,
            "current_support": "NONE",
            "supported_operations": [],
            "review_items": [{
                "code": "UNKNOWN_CONSTRUCTION", "state": "UNKNOWN",
                "why": "typed construction evidence is insufficient",
            }]}


def _manufacturing_representation(regime: ConstructionRegime,
                                  node_regimes: Mapping[str, ConstructionRegime],
                                  graph: Mapping[str, Any]) -> Dict[str, Any]:
    if regime != ConstructionRegime.MODULAR_LAYERED:
        return _single_manufacturing(regime, graph["nodes"], graph["relations"])
    groups: Dict[ConstructionRegime, List[Mapping[str, Any]]] = defaultdict(list)
    for node in graph["nodes"]:
        groups[node_regimes[node["node_id"]]].append(node)
    components = []
    for component_regime in sorted(groups, key=lambda item: item.value):
        component = _single_manufacturing(
            component_regime, groups[component_regime], graph["relations"])
        components.append({
            "regime": component_regime.value,
            "representation": component,
        })
    return {
        "kind": ManufacturingRepresentation.HYBRID.value,
        "state": "PROPOSED",
        "current_support": "COMPONENT_ROUTING_ONLY",
        "components": components,
        "layer_relations": [
            copy.deepcopy(relation) for relation in graph["relations"]
            if relation["connection"] in {"LAYER", "MODULE_ATTACHMENT"}
        ],
        "supported_operations": [
            "ROUTE_EACH_TYPED_COMPONENT",
            "PRESERVE_LAYER_AND_MODULE_RELATIONS",
        ],
        "not_supported": [
            "AUTO_UNIFY_MIXED_CONSTRUCTION_INSTRUCTIONS",
            "INFER_CROSS_REGIME_JOIN_METHODS",
            "CERTIFY_FIT_STRENGTH_COMFORT_OR_PRODUCTION",
        ],
        "review_items": [{
            "code": "REVIEW_HYBRID_INTEGRATION_REQUIRED", "state": "REVIEW",
            "why": "component routes exist, but cross-regime assembly remains a human/deterministic downstream gate",
        }],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }


def route_construction(instance_graph: Mapping[str, Any]) -> Dict[str, Any]:
    """Return one authority-preserving construction and representation route."""
    try:
        graph, reviews = _normalise_graph(instance_graph)
        regime, node_regimes, selection_reviews = _select_regime(graph)
    except (ValueError, TypeError) as exc:
        return _refusal("UNKNOWN_CONSTRUCTION_GRAPH", str(exc))
    reviews.extend(selection_reviews)
    authority = _authority(graph, reviews)
    proposal = graph["proposed_construction_regime"]
    if proposal is None:
        agreement = "NOT_SUPPLIED"
    elif proposal == regime.value:
        agreement = "MATCH"
    else:
        agreement = "CONTESTED"
        reviews.append({
            "code": "REVIEW_MODEL_REGIME_CONTESTED",
            "state": "REVIEW",
            "why": "model regime label disagrees with deterministic typed routing",
            "model_proposal": proposal,
            "deterministic_selection": regime.value,
        })

    construction_basis = {
        "source_front_only": graph["source"]["front_only"],
        "nodes": [
            {key: copy.deepcopy(node[key]) for key in (
                "node_id", "primitive_kind", "method", "cut_geometry", "fit",
                "shaping", "dimensions_cm", "knit", "layer", "state")}
            for node in sorted(graph["nodes"], key=lambda row: row["node_id"])
        ],
        "relations": [copy.deepcopy(relation) for relation in sorted(
            graph["relations"], key=lambda row: row["relation_id"])],
    }
    manufacturing = _manufacturing_representation(regime, node_regimes, graph)
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": ("ANSWER" if regime != ConstructionRegime.UNKNOWN_CONSTRUCTION
                    else ConstructionRegime.UNKNOWN_CONSTRUCTION.value),
        "state": authority["construction_state"] if regime != ConstructionRegime.UNKNOWN_CONSTRUCTION else "UNKNOWN",
        "identity": {
            "graph_id": graph["graph_id"],
            "garment_name": graph["garment_name"],
            "garment_name_used_for_routing": False,
        },
        "construction_digest": stable_digest(construction_basis),
        "construction_regime": {
            "value": regime.value,
            "state": authority["construction_state"] if regime != ConstructionRegime.UNKNOWN_CONSTRUCTION else "UNKNOWN",
            "selected_by": "DETERMINISTIC_TYPED_VERA_ROUTER",
            "node_regimes": {
                node_id: node_regimes[node_id].value for node_id in sorted(node_regimes)
            },
            "model_proposal": ({"value": proposal, "state": "PROPOSED"}
                               if proposal is not None else None),
            "proposal_alignment": agreement,
            "name_independent": True,
        },
        "target_representation": _target_representation(regime, graph, authority),
        "manufacturing_representation": manufacturing,
        "authority": authority,
        "review_items": reviews + copy.deepcopy(manufacturing.get("review_items", [])),
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["route_digest"] = stable_digest(result)
    return result


def select_construction_regime(instance_graph: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the typed regime record while preserving refusal envelopes."""
    result = route_construction(instance_graph)
    if "construction_regime" not in result:
        return result
    return {
        "schema": SCHEMA,
        "verdict": result["verdict"],
        "state": result["state"],
        "construction_digest": result["construction_digest"],
        "construction_regime": copy.deepcopy(result["construction_regime"]),
        "authority": copy.deepcopy(result["authority"]),
        "review_items": copy.deepcopy(result["review_items"]),
        "fact_promotions": [],
    }


# Conventional aliases used by the other small deterministic pipeline modules.
route = route_construction
build = route_construction
compile = route_construction
