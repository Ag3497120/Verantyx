# -*- coding: utf-8 -*-
"""Geometry-first modular garment assembly.

The module deliberately separates facts that geometry can establish from
construction knowledge that must come from a sewing corpus (or a human).
Meshes and named boundary ports can be fitted, joined, layered and, when the
topology agrees, welded into one structural mesh without naming a garment
style.  A sewing order is emitted only when every seam carries explicit
construction knowledge and its source.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]

ANSWER = "ANSWER"
UNKNOWN_NEEDS_SEWING_CORPUS = "UNKNOWN_NEEDS_SEWING_CORPUS"


class AssemblyInvariantError(ValueError):
    """A malformed mesh, port or assembly graph, with a stable error code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class Mesh:
    vertices: Tuple[Vec3, ...]
    faces: Tuple[Tuple[int, ...], ...]

    def __post_init__(self) -> None:
        if not self.vertices:
            raise AssemblyInvariantError("EMPTY_MESH", "a piece needs vertices")
        for vertex in self.vertices:
            if len(vertex) != 3 or not all(math.isfinite(v) for v in vertex):
                raise AssemblyInvariantError("INVALID_VERTEX", repr(vertex))
        for face in self.faces:
            if len(face) < 3 or len(set(face)) < 3:
                raise AssemblyInvariantError("DEGENERATE_FACE", repr(face))
            if any(i < 0 or i >= len(self.vertices) for i in face):
                raise AssemblyInvariantError("FACE_INDEX_OUT_OF_RANGE", repr(face))

    @property
    def edges(self) -> frozenset[Tuple[int, int]]:
        out = set()
        for face in self.faces:
            for a, b in zip(face, face[1:] + face[:1]):
                out.add((min(a, b), max(a, b)))
        return frozenset(out)


@dataclass(frozen=True)
class Port:
    """A closed mesh boundary that may fit or join another module.

    ``interface`` is geometric vocabulary (for example ``waist``), not a
    garment class.  ``direction`` distinguishes complementary ends such as a
    top's lower waist and a skirt's upper waist.  The ratios are material or
    design limits supplied by the caller; this module does not invent them.
    """

    name: str
    loop: Tuple[int, ...]
    interface: str
    direction: str = "neutral"
    min_stretch_ratio: float = 1.0
    max_stretch_ratio: float = 1.0

    def __post_init__(self) -> None:
        if not self.name or not self.interface:
            raise AssemblyInvariantError("UNNAMED_PORT", "name and interface are required")
        if len(self.loop) < 3 or len(set(self.loop)) != len(self.loop):
            raise AssemblyInvariantError("INVALID_PORT_LOOP", repr(self.loop))
        if self.direction not in ("upper", "lower", "neutral"):
            raise AssemblyInvariantError("INVALID_PORT_DIRECTION", self.direction)
        if (not math.isfinite(self.min_stretch_ratio)
                or not math.isfinite(self.max_stretch_ratio)
                or self.min_stretch_ratio <= 0
                or self.min_stretch_ratio > self.max_stretch_ratio):
            raise AssemblyInvariantError(
                "INVALID_STRETCH_RANGE",
                f"{self.min_stretch_ratio}..{self.max_stretch_ratio}")


@dataclass(frozen=True)
class GarmentPiece:
    name: str
    mesh: Mesh
    ports: Tuple[Port, ...]
    category: str = "module"
    layer: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise AssemblyInvariantError("UNNAMED_PIECE", "piece name is required")
        names = [port.name for port in self.ports]
        if len(names) != len(set(names)):
            raise AssemblyInvariantError("DUPLICATE_PORT", self.name)
        edges = self.mesh.edges
        for port in self.ports:
            if any(i < 0 or i >= len(self.mesh.vertices) for i in port.loop):
                raise AssemblyInvariantError(
                    "PORT_INDEX_OUT_OF_RANGE", f"{self.name}/{port.name}")
            loop_edges = zip(port.loop, port.loop[1:] + port.loop[:1])
            if any((min(a, b), max(a, b)) not in edges for a, b in loop_edges):
                raise AssemblyInvariantError(
                    "PORT_NOT_MESH_LOOP", f"{self.name}/{port.name}")

    def port(self, name: str) -> Port:
        for port in self.ports:
            if port.name == name:
                return port
        raise AssemblyInvariantError("UNKNOWN_PORT", f"{self.name}/{name}")


@dataclass(frozen=True)
class PortRef:
    piece: str
    port: str


@dataclass(frozen=True)
class Seam:
    name: str
    a: PortRef
    b: PortRef
    merge: bool = False
    allow_cross_layer: bool = False
    construction_method: Optional[str] = None
    construction_source: Optional[str] = None
    prerequisites: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MergedMesh:
    mesh: Mesh
    # Each resulting vertex records every source vertex welded into it.
    vertex_sources: Tuple[Tuple[Tuple[str, int], ...], ...]


@dataclass(frozen=True)
class Assembly:
    pieces: Tuple[GarmentPiece, ...]
    seams: Tuple[Seam, ...]
    merged_mesh: Optional[MergedMesh] = None
    merge_enabled: bool = False

    def piece(self, name: str) -> GarmentPiece:
        for piece in self.pieces:
            if piece.name == name:
                return piece
        raise AssemblyInvariantError("UNKNOWN_PIECE", name)


@dataclass(frozen=True)
class SecondSkinBoundary:
    interface: str
    circumference: float

    def __post_init__(self) -> None:
        if not self.interface or not math.isfinite(self.circumference) or self.circumference <= 0:
            raise AssemblyInvariantError(
                "INVALID_SECOND_SKIN_BOUNDARY", f"{self.interface}: {self.circumference}")


class _Union:
    def __init__(self, values: Iterable[object]) -> None:
        self.up = {value: value for value in values}

    def find(self, value: object) -> object:
        parent = self.up[value]
        if parent != value:
            self.up[value] = self.find(parent)
        return self.up[value]

    def join(self, a: object, b: object) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.up[ra] = rb
        return True


def _distance(a: Vec3, b: Vec3) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def port_length(piece: GarmentPiece, port_name: str) -> float:
    """Return the closed-loop rest length of a port in mesh units."""
    port = piece.port(port_name)
    points = [piece.mesh.vertices[i] for i in port.loop]
    length = sum(_distance(a, b) for a, b in zip(points, points[1:] + points[:1]))
    if length <= 0:
        raise AssemblyInvariantError("ZERO_LENGTH_PORT", f"{piece.name}/{port_name}")
    return length


def stretch_to_second_skin(piece: GarmentPiece, port_name: str,
                           boundary: SecondSkinBoundary) -> Dict[str, object]:
    """Measure, rather than assume, the stretch needed at one body boundary."""
    port = piece.port(port_name)
    if port.interface != boundary.interface:
        raise AssemblyInvariantError(
            "SECOND_SKIN_INTERFACE_MISMATCH",
            f"{port.interface} != {boundary.interface}")
    rest = port_length(piece, port_name)
    ratio = boundary.circumference / rest
    return {
        "verdict": ANSWER,
        "piece": piece.name,
        "port": port_name,
        "interface": port.interface,
        "rest_length": rest,
        "target_length": boundary.circumference,
        "stretch_ratio": ratio,
        "engineering_strain": ratio - 1.0,
        "percent": (ratio - 1.0) * 100.0,
        "within_declared_limits": (
            port.min_stretch_ratio <= ratio <= port.max_stretch_ratio),
        "declared_limits": (port.min_stretch_ratio, port.max_stretch_ratio),
    }


def fit_second_skin(piece: GarmentPiece,
                    boundaries: Mapping[str, SecondSkinBoundary]) -> Dict[str, object]:
    """Fit every port for which a target boundary is supplied."""
    fits = []
    for port in piece.ports:
        boundary = boundaries.get(port.interface)
        if boundary is not None:
            fits.append(stretch_to_second_skin(piece, port.name, boundary))
    return {
        "verdict": ANSWER,
        "piece": piece.name,
        "fits": fits,
        "all_within_declared_limits": bool(fits) and all(
            bool(row["within_declared_limits"]) for row in fits),
        "unmatched_interfaces": sorted(
            set(boundaries) - {port.interface for port in piece.ports}),
    }


def _directions_compatible(a: Port, b: Port) -> bool:
    return (a.direction == "neutral" or b.direction == "neutral"
            or {a.direction, b.direction} == {"upper", "lower"})


def _interface_overlap(a_piece: GarmentPiece, a: Port,
                       b_piece: GarmentPiece, b: Port) -> Optional[Tuple[float, float]]:
    if a.interface != b.interface or not _directions_compatible(a, b):
        return None
    a_len = port_length(a_piece, a.name)
    b_len = port_length(b_piece, b.name)
    low = max(a_len * a.min_stretch_ratio, b_len * b.min_stretch_ratio)
    high = min(a_len * a.max_stretch_ratio, b_len * b.max_stretch_ratio)
    return (low, high) if low <= high else None


def _validate_dependencies(seams: Sequence[Seam]) -> None:
    names = {seam.name for seam in seams}
    for seam in seams:
        missing = set(seam.prerequisites) - names
        if missing:
            raise AssemblyInvariantError(
                "UNKNOWN_SEAM_PREREQUISITE", f"{seam.name}: {sorted(missing)}")
        if seam.name in seam.prerequisites:
            raise AssemblyInvariantError("CYCLIC_SEAM_ORDER", seam.name)
    incoming = {seam.name: set(seam.prerequisites) for seam in seams}
    ready = sorted(name for name, deps in incoming.items() if not deps)
    visited = []
    while ready:
        name = ready.pop(0)
        visited.append(name)
        for other in sorted(incoming):
            if name in incoming[other]:
                incoming[other].remove(name)
                if not incoming[other] and other not in visited and other not in ready:
                    ready.append(other)
                    ready.sort()
    if len(visited) != len(seams):
        raise AssemblyInvariantError("CYCLIC_SEAM_ORDER", "prerequisites contain a cycle")


def assemble(pieces: Sequence[GarmentPiece], seams: Sequence[Seam] = (), *,
             merge_compatible: bool = False) -> Assembly:
    """Validate and assemble modules using only declared port geometry."""
    pieces = tuple(pieces)
    seams = tuple(seams)
    names = [piece.name for piece in pieces]
    if not pieces:
        raise AssemblyInvariantError("EMPTY_ASSEMBLY", "at least one piece is required")
    if len(names) != len(set(names)):
        raise AssemblyInvariantError("DUPLICATE_PIECE", repr(names))
    seam_names = [seam.name for seam in seams]
    if any(not name for name in seam_names) or len(seam_names) != len(set(seam_names)):
        raise AssemblyInvariantError("DUPLICATE_OR_UNNAMED_SEAM", repr(seam_names))

    by_name = {piece.name: piece for piece in pieces}
    used_ports = set()
    for seam in seams:
        if seam.a == seam.b:
            raise AssemblyInvariantError("SEAM_JOINS_PORT_TO_ITSELF", seam.name)
        try:
            pa, pb = by_name[seam.a.piece], by_name[seam.b.piece]
        except KeyError as exc:
            raise AssemblyInvariantError("UNKNOWN_PIECE", str(exc)) from exc
        a, b = pa.port(seam.a.port), pb.port(seam.b.port)
        for ref in (seam.a, seam.b):
            if ref in used_ports:
                raise AssemblyInvariantError("PORT_ALREADY_JOINED", f"{ref.piece}/{ref.port}")
            used_ports.add(ref)
        if pa.layer != pb.layer and not seam.allow_cross_layer:
            raise AssemblyInvariantError("CROSS_LAYER_JOIN_NOT_DECLARED", seam.name)
        if _interface_overlap(pa, a, pb, b) is None:
            raise AssemblyInvariantError("INCOMPATIBLE_INTERFACES", seam.name)
        wants_merge = merge_compatible or seam.merge
        if wants_merge and len(a.loop) != len(b.loop):
            raise AssemblyInvariantError("MERGE_LOOP_ARITY_MISMATCH", seam.name)
    _validate_dependencies(seams)

    merged = (_merge_meshes(pieces, seams, merge_all=merge_compatible)
              if (merge_compatible or any(s.merge for s in seams)) else None)
    result = Assembly(pieces, seams, merged, merge_compatible)
    _assert_graph_invariants(result)
    return result


def _merge_meshes(pieces: Sequence[GarmentPiece], seams: Sequence[Seam], *,
                  merge_all: bool) -> MergedMesh:
    keys = [(piece.name, i) for piece in pieces for i in range(len(piece.mesh.vertices))]
    union = _Union(keys)
    by_name = {piece.name: piece for piece in pieces}
    for seam in seams:
        if not merge_all and not seam.merge:
            continue
        a_piece, b_piece = by_name[seam.a.piece], by_name[seam.b.piece]
        a, b = a_piece.port(seam.a.port), b_piece.port(seam.b.port)
        for ai, bi in zip(a.loop, reversed(b.loop)):
            union.join((a_piece.name, ai), (b_piece.name, bi))

    groups: Dict[object, List[Tuple[str, int]]] = {}
    for key in keys:
        groups.setdefault(union.find(key), []).append(key)
    # Dict insertion order follows ``keys``, so this is deterministic without
    # an O(vertices²) sequence of ``keys.index`` scans on production meshes.
    ordered = list(groups.values())
    index = {source: i for i, group in enumerate(ordered) for source in group}
    vertices: List[Vec3] = []
    source_vertices = {(piece.name, i): vertex
                       for piece in pieces for i, vertex in enumerate(piece.mesh.vertices)}
    for group in ordered:
        points = [source_vertices[source] for source in group]
        vertices.append(tuple(sum(p[axis] for p in points) / len(points)
                              for axis in range(3)))
    faces = []
    for piece in pieces:
        for face in piece.mesh.faces:
            mapped = tuple(index[(piece.name, i)] for i in face)
            if len(set(mapped)) >= 3:
                faces.append(mapped)
    return MergedMesh(Mesh(tuple(vertices), tuple(faces)),
                      tuple(tuple(sorted(group)) for group in ordered))


def _find_join_port(piece: GarmentPiece, interface: str, direction: str) -> Port:
    candidates = [port for port in piece.ports
                  if port.interface == interface
                  and port.direction in (direction, "neutral")]
    if len(candidates) != 1:
        raise AssemblyInvariantError(
            "AMBIGUOUS_INTERFACE",
            f"{piece.name}: expected one {direction} {interface}, got {len(candidates)}")
    return candidates[0]


def _combine_waist(top: GarmentPiece, bottom: GarmentPiece, category: str, *,
                   merge_compatible: bool = False,
                   construction_method: Optional[str] = None,
                   construction_source: Optional[str] = None) -> Assembly:
    if bottom.category != category:
        raise AssemblyInvariantError(
            "WRONG_BOTTOM_CATEGORY", f"expected {category}, got {bottom.category}")
    upper = _find_join_port(top, "waist", "lower")
    lower = _find_join_port(bottom, "waist", "upper")
    seam = Seam(
        f"{top.name}+{bottom.name}:waist",
        PortRef(top.name, upper.name), PortRef(bottom.name, lower.name),
        merge=merge_compatible,
        construction_method=construction_method,
        construction_source=construction_source,
    )
    return assemble((top, bottom), (seam,), merge_compatible=merge_compatible)


def combine_top_trouser(top: GarmentPiece, trouser: GarmentPiece, **kwargs: object) -> Assembly:
    return _combine_waist(top, trouser, "trouser", **kwargs)


def combine_top_skirt(top: GarmentPiece, skirt: GarmentPiece, **kwargs: object) -> Assembly:
    return _combine_waist(top, skirt, "skirt", **kwargs)


def assemble_layers(layers: Sequence[Sequence[GarmentPiece]],
                    seams: Sequence[Seam] = (), *,
                    merge_compatible: bool = False) -> Assembly:
    """Place garment modules in explicit inner-to-outer layers.

    Layering itself creates no seams.  Cross-layer attachment must be explicit
    on a seam with ``allow_cross_layer=True``.
    """
    pieces = tuple(replace(piece, layer=layer)
                   for layer, group in enumerate(layers) for piece in group)
    return assemble(pieces, seams, merge_compatible=merge_compatible)


def graph_report(assembly: Assembly) -> Dict[str, object]:
    """Return connected-component and first-Betti-number seam invariants."""
    names = [piece.name for piece in assembly.pieces]
    union = _Union(names)
    for seam in assembly.seams:
        union.join(seam.a.piece, seam.b.piece)
    components = len({union.find(name) for name in names})
    beta = len(assembly.seams) - len(names) + components
    return {
        "vertices": len(names),
        "edges": len(assembly.seams),
        "components": components,
        "beta": beta,
        "formula": (f"β = E - V + C = {len(assembly.seams)} - "
                    f"{len(names)} + {components} = {beta}"),
        "loop_free": beta == 0,
    }


def _assert_graph_invariants(assembly: Assembly) -> None:
    report = graph_report(assembly)
    if int(report["beta"]) < 0:
        raise AssemblyInvariantError("NEGATIVE_BETA", str(report))
    expected = int(report["edges"]) - int(report["vertices"]) + int(report["components"])
    if report["beta"] != expected:
        raise AssemblyInvariantError("BETA_MISMATCH", str(report))


def _topological_seams(seams: Sequence[Seam]) -> List[Seam]:
    by_name = {seam.name: seam for seam in seams}
    remaining = {seam.name: set(seam.prerequisites) for seam in seams}
    order = []
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:  # assemble() normally catches this; retain a local guard.
            raise AssemblyInvariantError("CYCLIC_SEAM_ORDER", repr(remaining))
        for name in ready:
            order.append(by_name[name])
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)
    return order


def plan_sewing(assembly: Assembly) -> Dict[str, object]:
    """Emit a human-sewable partial order only from explicit knowledge.

    Geometry still reports components and β when construction knowledge is
    absent.  It never fills in a stitch, finish, tool or accessibility claim.
    """
    graph = graph_report(assembly)
    missing = [seam.name for seam in assembly.seams
               if not seam.construction_method or not seam.construction_source]
    if missing:
        return {
            "verdict": UNKNOWN_NEEDS_SEWING_CORPUS,
            "missing_seams": missing,
            "known_geometry": graph,
            "how_to_close": (
                "Supply a human-verified or corpus-backed construction_method "
                "and construction_source for every listed seam."),
        }

    order = _topological_seams(assembly.seams)
    union = _Union(piece.name for piece in assembly.pieces)
    operations = []
    round_count = 0
    for step, seam in enumerate(order, 1):
        flat = union.join(seam.a.piece, seam.b.piece)
        access = "FLAT" if flat else "IN_THE_ROUND"
        round_count += not flat
        operations.append({
            "step": step,
            "seam": seam.name,
            "a": f"{seam.a.piece}/{seam.a.port}",
            "b": f"{seam.b.piece}/{seam.b.port}",
            "method": seam.construction_method,
            "source": seam.construction_source,
            "after": list(seam.prerequisites),
            "access": access,
        })
    beta = int(graph["beta"])
    if round_count != beta:
        raise AssemblyInvariantError(
            "SEAM_LOOP_BETA_MISMATCH", f"round={round_count}, beta={beta}")
    return {
        "verdict": ANSWER,
        "operations": operations,
        "partial_order": [(dependency, seam.name)
                          for seam in assembly.seams
                          for dependency in seam.prerequisites],
        "graph": graph,
        "in_the_round": round_count,
        "in_the_round_minimum": beta,
        "beta_check": round_count == beta,
        "human_sewable": True,
        "scope": ("The order is justified by supplied construction knowledge "
                  "and graph accessibility; machine settings remain outside this model."),
    }
