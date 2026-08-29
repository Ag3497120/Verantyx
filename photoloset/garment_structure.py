# -*- coding: utf-8 -*-
"""Corpus-free, geometry-first garment structure graphs.

The graph names geometric ingredients and operations, not garment classes.
Nothing in this module retrieves a precedent or invents a missing dimension.
Malformed or under-specified geometry is returned as a typed ``UNKNOWN``
result before it can become a construction claim.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


ANSWER = "ANSWER"
SCHEMA = "garment.structure.v1"


class PrimitiveKind(str, Enum):
    BODY_SHELL = "BODY_SHELL"
    TUBE = "TUBE"
    FRUSTUM = "FRUSTUM"
    FLARE = "FLARE"
    GORE = "GORE"
    GUSSET = "GUSSET"
    YOKE = "YOKE"
    COLLAR = "COLLAR"
    HOOD = "HOOD"
    SLEEVE = "SLEEVE"
    BAND = "BAND"
    OVERLAY = "OVERLAY"
    OPENING = "OPENING"
    DRAPE_ANCHOR = "DRAPE_ANCHOR"


class OperationKind(str, Enum):
    SPLIT = "SPLIT"
    JOIN = "JOIN"
    OVERLAP = "OVERLAP"
    FOLD = "FOLD"
    GATHER = "GATHER"
    PLEAT = "PLEAT"
    DART = "DART"
    CUTOUT = "CUTOUT"
    MIRROR = "MIRROR"
    ASYMMETRY = "ASYMMETRY"
    LAYER = "LAYER"


_REQUIRED_DIMENSIONS = {
    PrimitiveKind.BODY_SHELL: ("height_cm", "circumference_cm"),
    PrimitiveKind.TUBE: ("length_cm", "circumference_cm"),
    PrimitiveKind.FRUSTUM: ("height_cm", "top_circumference_cm", "bottom_circumference_cm"),
    PrimitiveKind.FLARE: ("height_cm", "top_circumference_cm", "bottom_circumference_cm"),
    PrimitiveKind.GORE: ("length_cm", "top_width_cm", "bottom_width_cm"),
    PrimitiveKind.GUSSET: ("length_cm", "width_cm"),
    PrimitiveKind.YOKE: ("height_cm", "width_cm"),
    PrimitiveKind.COLLAR: ("length_cm", "width_cm"),
    PrimitiveKind.HOOD: ("height_cm", "width_cm", "depth_cm"),
    PrimitiveKind.SLEEVE: ("length_cm", "upper_circumference_cm", "cuff_circumference_cm"),
    PrimitiveKind.BAND: ("length_cm", "width_cm"),
    PrimitiveKind.OVERLAY: ("height_cm", "width_cm"),
    PrimitiveKind.OPENING: ("length_cm",),
    PrimitiveKind.DRAPE_ANCHOR: (),
}


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def semantic_digest(value: Any) -> str:
    encoded = json.dumps(_plain(value), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_positive(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and float(value) > 0.0)


@dataclass(frozen=True)
class BoundaryPort:
    port_id: str
    length_cm: float
    interface: str
    role: str = "edge"
    layer: int = 0
    stretch_range: Tuple[float, float] = (1.0, 1.0)

    def as_dict(self) -> Dict[str, Any]:
        return _plain(self.__dict__)


@dataclass(frozen=True)
class PrimitiveNode:
    node_id: str
    kind: PrimitiveKind
    dimensions: Mapping[str, float]
    ports: Tuple[BoundaryPort, ...] = ()
    layer: int = 0
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", PrimitiveKind(self.kind))
        object.__setattr__(self, "ports", tuple(self.ports))

    def as_dict(self) -> Dict[str, Any]:
        return {"node_id": self.node_id, "kind": self.kind.value,
                "dimensions": _plain(self.dimensions),
                "ports": [p.as_dict() for p in self.ports],
                "layer": self.layer, "attributes": _plain(self.attributes)}


@dataclass(frozen=True)
class PortRef:
    node_id: str
    port_id: str

    def as_dict(self) -> Dict[str, str]:
        return {"node_id": self.node_id, "port_id": self.port_id}


@dataclass(frozen=True)
class StructureOperation:
    operation_id: str
    kind: OperationKind
    source: PortRef
    target: Optional[PortRef] = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    prerequisites: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", OperationKind(self.kind))
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))

    def as_dict(self) -> Dict[str, Any]:
        return {"operation_id": self.operation_id, "kind": self.kind.value,
                "source": self.source.as_dict(),
                "target": None if self.target is None else self.target.as_dict(),
                "parameters": _plain(self.parameters),
                "prerequisites": list(self.prerequisites)}


@dataclass(frozen=True)
class StructureGraph:
    nodes: Tuple[PrimitiveNode, ...]
    operations: Tuple[StructureOperation, ...] = ()
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "operations", tuple(self.operations))

    def as_dict(self) -> Dict[str, Any]:
        return {"schema": self.schema,
                "nodes": [n.as_dict() for n in self.nodes],
                "operations": [o.as_dict() for o in self.operations]}

    @property
    def digest(self) -> str:
        return semantic_digest(self.as_dict())


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why,
            "how_to_close": "supply explicit, geometrically valid typed values",
            **detail}


def _port_table(graph: StructureGraph) -> Tuple[Optional[Dict[Tuple[str, str], BoundaryPort]], Optional[Dict[str, Any]]]:
    table: Dict[Tuple[str, str], BoundaryPort] = {}
    node_ids = [node.node_id for node in graph.nodes]
    if not graph.nodes:
        return None, _unknown("UNKNOWN_EMPTY_STRUCTURE", "the graph has no primitive nodes")
    if (any(not isinstance(x, str) or not x for x in node_ids)
            or len(node_ids) != len(set(node_ids))):
        return None, _unknown("UNKNOWN_DUPLICATE_NODE", "node ids must be unique and non-empty")
    for node in graph.nodes:
        required = _REQUIRED_DIMENSIONS[node.kind]
        missing = [name for name in required if name not in node.dimensions]
        if missing:
            return None, _unknown("UNKNOWN_PRIMITIVE_DIMENSION_MISSING",
                                  f"{node.node_id} lacks required dimensions", missing=missing)
        for name, value in node.dimensions.items():
            coordinate = name in ("x_cm", "y_cm", "z_cm") or name.endswith("_angle_deg")
            finite = (not isinstance(value, bool) and isinstance(value, (int, float))
                      and math.isfinite(float(value)))
            if not finite or (not coordinate and float(value) <= 0.0):
                return None, _unknown("UNKNOWN_INVALID_PRIMITIVE_DIMENSION",
                                      f"{node.node_id}.{name} must be finite"
                                      + ("" if coordinate else " and positive"))
        names = [port.port_id for port in node.ports]
        if (any(not isinstance(x, str) or not x for x in names)
                or len(names) != len(set(names))):
            return None, _unknown("UNKNOWN_DUPLICATE_PORT", f"ports on {node.node_id} are not unique")
        for port in node.ports:
            lo, hi = port.stretch_range
            if (not isinstance(port.interface, str) or not port.interface
                    or port.role not in ("edge", "point", "loop")
                    or not _finite_positive(port.length_cm)
                    or not _finite_positive(lo) or not _finite_positive(hi) or lo > hi):
                return None, _unknown("UNKNOWN_INVALID_PORT", f"invalid port {node.node_id}/{port.port_id}")
            table[(node.node_id, port.port_id)] = port
    return table, None


def _validate_dependencies(operations: Sequence[StructureOperation]) -> Optional[Dict[str, Any]]:
    ids = [op.operation_id for op in operations]
    if (any(not isinstance(x, str) or not x for x in ids)
            or len(ids) != len(set(ids))):
        return _unknown("UNKNOWN_DUPLICATE_OPERATION", "operation ids must be unique and non-empty")
    known = set(ids)
    incoming = {op.operation_id: set(op.prerequisites) for op in operations}
    for operation_id, dependencies in incoming.items():
        missing = dependencies - known
        if missing:
            return _unknown("UNKNOWN_OPERATION_PREREQUISITE", operation_id, missing=sorted(missing))
        if operation_id in dependencies:
            return _unknown("UNKNOWN_CYCLIC_CONSTRUCTION", operation_id)
    ready = sorted(k for k, v in incoming.items() if not v)
    visited = []
    while ready:
        current = ready.pop(0)
        visited.append(current)
        for name in sorted(incoming):
            incoming[name].discard(current)
            if not incoming[name] and name not in visited and name not in ready:
                ready.append(name)
                ready.sort()
    if len(visited) != len(incoming):
        return _unknown("UNKNOWN_CYCLIC_CONSTRUCTION", "operation prerequisites contain a cycle")
    return None


def validate_structure(graph: StructureGraph, *, length_tolerance_cm: float = 0.05) -> Dict[str, Any]:
    """Validate a graph without repairing or selecting a nearby geometry."""
    if not isinstance(graph, StructureGraph) or graph.schema != SCHEMA:
        return _unknown("UNKNOWN_STRUCTURE_SCHEMA", f"expected {SCHEMA}")
    if not _finite_positive(length_tolerance_cm):
        return _unknown("UNKNOWN_INVALID_TOLERANCE", "length tolerance must be positive")
    ports, error = _port_table(graph)
    if error:
        return error
    dependency_error = _validate_dependencies(graph.operations)
    if dependency_error:
        return dependency_error
    assert ports is not None
    binary = {OperationKind.JOIN, OperationKind.OVERLAP, OperationKind.GATHER,
              OperationKind.LAYER}
    used_join_ports = set()
    checks = []
    for op in graph.operations:
        source_key = (op.source.node_id, op.source.port_id)
        target_key = None if op.target is None else (op.target.node_id, op.target.port_id)
        if source_key not in ports or (target_key is not None and target_key not in ports):
            return _unknown("UNKNOWN_OPERATION_PORT", f"{op.operation_id} names an unknown port")
        if op.kind in binary and target_key is None:
            return _unknown("UNKNOWN_OPERATION_TARGET", f"{op.kind.value} requires a target")
        if op.kind not in binary and target_key is not None:
            return _unknown("UNKNOWN_UNEXPECTED_OPERATION_TARGET", f"{op.kind.value} is unary")
        if target_key == source_key:
            return _unknown("UNKNOWN_SELF_JOIN", f"{op.operation_id} joins a port to itself")
        source = ports[source_key]
        target = None if target_key is None else ports[target_key]
        if op.kind in (OperationKind.JOIN, OperationKind.GATHER):
            if source_key in used_join_ports or target_key in used_join_ports:
                return _unknown("UNKNOWN_PORT_ALREADY_CONSUMED", f"{op.operation_id} reuses a joined edge")
            used_join_ports.update((source_key, target_key))
            if source.interface != target.interface:
                return _unknown("UNKNOWN_INTERFACE_MISMATCH", f"{op.operation_id}: {source.interface} != {target.interface}")
        if op.kind is OperationKind.JOIN:
            difference = abs(source.length_cm - target.length_cm)
            if difference > length_tolerance_cm:
                return _unknown("UNKNOWN_JOIN_LENGTH_MISMATCH", f"{op.operation_id} differs by {difference:.6g}cm",
                                source_cm=source.length_cm, target_cm=target.length_cm)
            checks.append({"operation_id": op.operation_id, "length_difference_cm": difference})
        if op.kind is OperationKind.GATHER:
            if source.length_cm <= target.length_cm:
                return _unknown("UNKNOWN_GATHER_DOES_NOT_REDUCE", f"{op.operation_id} source must be longer")
            measured = source.length_cm / target.length_cm
            declared = op.parameters.get("ratio")
            if declared is None or not _finite_positive(declared):
                return _unknown("UNKNOWN_GATHER_RATIO_MISSING", f"{op.operation_id} needs an explicit ratio")
            if abs(float(declared) - measured) > 1e-9:
                return _unknown("UNKNOWN_GATHER_RATIO_MISMATCH", f"{op.operation_id} ratio disagrees with port geometry",
                                measured_ratio=measured, declared_ratio=declared)
            checks.append({"operation_id": op.operation_id, "gather_ratio": measured})
        if op.kind is OperationKind.LAYER and op.source.node_id == op.target.node_id:
            return _unknown("UNKNOWN_LAYER_SELF_REFERENCE", f"{op.operation_id} needs distinct nodes")
    return {"verdict": ANSWER, "schema": SCHEMA, "digest": graph.digest,
            "graph": graph.as_dict(), "checks": checks,
            "provenance": {"method": "deterministic geometry validation", "corpus_used": False}}


construction_validation = validate_structure


def build_structure(nodes: Iterable[PrimitiveNode], operations: Iterable[StructureOperation] = ()) -> Dict[str, Any]:
    """Build and validate in one fail-closed boundary call."""
    try:
        graph = StructureGraph(tuple(nodes), tuple(operations))
    except (TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_MALFORMED_STRUCTURE", str(exc))
    return validate_structure(graph)


def _parse_port(value: Mapping[str, Any]) -> BoundaryPort:
    if not isinstance(value, Mapping):
        raise TypeError("every port must be an object")
    stretch = value.get("stretch_range", (1.0, 1.0))
    layer = value.get("layer", 0)
    if isinstance(layer, bool) or not isinstance(layer, int):
        raise TypeError("port layer must be an integer")
    return BoundaryPort(value.get("port_id", ""), value.get("length_cm"),
                        value.get("interface", ""), value.get("role", "edge"),
                        layer, tuple(stretch))


def _parse_ref(value: Mapping[str, Any]) -> PortRef:
    return PortRef(value.get("node_id", ""), value.get("port_id", ""))


def _parse_graph(spec: Mapping[str, Any]) -> StructureGraph:
    if not isinstance(spec, Mapping):
        raise TypeError("structure must be an object")
    nodes = []
    for row in spec.get("nodes", spec.get("primitives", ())):
        if not isinstance(row, Mapping):
            raise TypeError("every node must be an object")
        ports = tuple(_parse_port(p) for p in row.get("ports", ()))
        layer = row.get("layer", 0)
        if isinstance(layer, bool) or not isinstance(layer, int):
            raise TypeError("node layer must be an integer")
        nodes.append(PrimitiveNode(row.get("node_id", ""), row.get("kind"),
                                   dict(row.get("dimensions", {})), ports,
                                   layer, dict(row.get("attributes", {}))))
    operations = []
    for row in spec.get("operations", spec.get("joins", ())):
        if not isinstance(row, Mapping) or not isinstance(row.get("source"), Mapping):
            raise TypeError("every operation needs an object source")
        target = row.get("target")
        operations.append(StructureOperation(
            row.get("operation_id", row.get("join_id", "")), row.get("kind"), _parse_ref(row["source"]),
            None if target is None else _parse_ref(target),
            dict(row.get("parameters", {})), tuple(row.get("prerequisites", ()))))
    return StructureGraph(tuple(nodes), tuple(operations), str(spec.get("schema", SCHEMA)))


def validate(graph: Mapping[str, Any]) -> Dict[str, Any]:
    """JSON boundary for validating an existing ``garment.structure.v1``."""
    try:
        result = validate_structure(_parse_graph(graph))
        return _plain(result)
    except (TypeError, ValueError, OverflowError) as exc:
        return _unknown("UNKNOWN_MALFORMED_STRUCTURE", str(exc))


def build(spec: Mapping[str, Any]) -> Dict[str, Any]:
    """JSON boundary for canonicalising and validating a structure spec."""
    result = validate(spec)
    if result.get("verdict") == ANSWER:
        result["graph"] = _plain(result["graph"])
    return result
