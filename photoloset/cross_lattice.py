# -*- coding: utf-8 -*-
"""Deterministic mesoscopic cross-lattice representation of cloth meshes.

This is a geometric/data-model layer, not an atom or molecule model and not a
time-integrating cloth solver.  Every surface vertex owns a local six-arm cross
(+/- warp, +/- weft, +/- normal).  Mesh edges provide membrane neighborhoods;
opposite vertices across an interior edge provide bending neighborhoods.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]
_EPS = 1.0e-12
ARM_NAMES = ("+warp", "-warp", "+weft", "-weft", "+normal", "-normal")


def _v3(value: Sequence[float]) -> Vec3:
    if len(value) != 3:
        raise ValueError("a vector must contain three coordinates")
    result = (float(value[0]), float(value[1]), float(value[2]))
    if not all(math.isfinite(v) for v in result):
        raise ValueError("vector coordinates must be finite")
    return result


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Vec3, scale: float) -> Vec3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec3) -> Vec3:
    length = _norm(a)
    if length <= _EPS:
        raise ValueError("cannot normalize a zero-length vector")
    return _mul(a, 1.0 / length)


def _project_tangent(axis: Vec3, normal: Vec3) -> Vec3:
    return _sub(axis, _mul(normal, _dot(axis, normal)))


def _canonical_tangent(normal: Vec3) -> Vec3:
    # Choose the least parallel world axis, with a stable tie order.
    candidates = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    source = min(enumerate(candidates), key=lambda item:
                 (abs(_dot(item[1], normal)), item[0]))[1]
    return _unit(_project_tangent(source, normal))


@dataclass(frozen=True)
class Provenance:
    source: str
    method: str
    revision: str = "1"
    assumptions: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.method.strip() or not self.revision.strip():
            raise ValueError("provenance fields must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return {"assumptions": list(self.assumptions), "method": self.method,
                "revision": self.revision, "source": self.source}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Provenance":
        return cls(str(value["source"]), str(value["method"]),
                   str(value.get("revision", "1")),
                   tuple(str(v) for v in value.get("assumptions", ())))


@dataclass(frozen=True)
class FacetContribution:
    """One bounded explanatory facet; it does not control accumulation."""

    facet_id: str
    signal_kind: str
    energy_j: float
    provenance: Provenance

    def __post_init__(self) -> None:
        if not self.facet_id.strip() or not self.signal_kind.strip():
            raise ValueError("facet id and signal kind must be non-empty")
        if not math.isfinite(self.energy_j) or self.energy_j < 0.0:
            raise ValueError("facet energy must be finite and non-negative")

    def to_dict(self) -> Dict[str, Any]:
        return {"energy_j": self.energy_j, "facet_id": self.facet_id,
                "provenance": self.provenance.to_dict(),
                "signal_kind": self.signal_kind}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FacetContribution":
        return cls(str(value["facet_id"]), str(value["signal_kind"]),
                   float(value["energy_j"]),
                   Provenance.from_dict(value["provenance"]))


@dataclass(frozen=True)
class CrossArm:
    name: str
    direction: Vec3
    neighbor: Optional[int]
    rest_distance_m: Optional[float]
    physical_energy_j: float = 0.0
    visible_facets: Tuple[FacetContribution, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.physical_energy_j) or self.physical_energy_j < 0.0:
            raise ValueError("arm physical energy must be finite and non-negative")
        if len(self.visible_facets) > 4:
            raise ValueError("an arm has at most four visible facet slots")

    def to_dict(self) -> Dict[str, Any]:
        return {"direction": list(self.direction), "name": self.name,
                "neighbor": self.neighbor,
                "physical_energy_j": self.physical_energy_j,
                "rest_distance_m": self.rest_distance_m,
                "visible_facets": [facet.to_dict() for facet in self.visible_facets]}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CrossArm":
        distance = value.get("rest_distance_m")
        return cls(str(value["name"]), _v3(value["direction"]),
                   None if value.get("neighbor") is None else int(value["neighbor"]),
                   None if distance is None else float(distance),
                   float(value.get("physical_energy_j", 0.0)),
                   tuple(FacetContribution.from_dict(v)
                         for v in value.get("visible_facets", ())))


@dataclass(frozen=True)
class CrossVertex:
    vertex_id: int
    position_m: Vec3
    velocity_m_s: Vec3
    mass_kg: float
    warp: Vec3
    weft: Vec3
    normal: Vec3
    arms: Tuple[CrossArm, ...]
    provenance: Provenance

    def to_dict(self) -> Dict[str, Any]:
        return {"arms": [arm.to_dict() for arm in self.arms],
                "mass_kg": self.mass_kg, "normal": list(self.normal),
                "position_m": list(self.position_m),
                "provenance": self.provenance.to_dict(),
                "velocity_m_s": list(self.velocity_m_s),
                "vertex_id": self.vertex_id, "warp": list(self.warp),
                "weft": list(self.weft)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CrossVertex":
        return cls(int(value["vertex_id"]), _v3(value["position_m"]),
                   _v3(value["velocity_m_s"]), float(value["mass_kg"]),
                   _v3(value["warp"]), _v3(value["weft"]),
                   _v3(value["normal"]),
                   tuple(CrossArm.from_dict(v) for v in value["arms"]),
                   Provenance.from_dict(value["provenance"]))


@dataclass(frozen=True)
class CrossFace:
    face_id: int
    vertices: Tuple[int, int, int]
    material_id: str
    area_m2: float
    normal: Vec3
    physical_energy_j: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.physical_energy_j) or self.physical_energy_j < 0.0:
            raise ValueError("face physical energy must be finite and non-negative")

    def to_dict(self) -> Dict[str, Any]:
        return {"area_m2": self.area_m2, "face_id": self.face_id,
                "material_id": self.material_id, "normal": list(self.normal),
                "physical_energy_j": self.physical_energy_j,
                "vertices": list(self.vertices)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CrossFace":
        vertices = tuple(int(v) for v in value["vertices"])
        if len(vertices) != 3:
            raise ValueError("serialized face must contain three indices")
        return cls(int(value["face_id"]), vertices, str(value["material_id"]),
                   float(value["area_m2"]), _v3(value["normal"]),
                   float(value.get("physical_energy_j", 0.0)))


@dataclass(frozen=True)
class LatticeLink:
    link_id: int
    kind: str
    vertices: Tuple[int, int]
    rest_length_m: float
    rest_angle_rad: Optional[float]
    supporting_faces: Tuple[int, ...]
    material_ids: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "link_id": self.link_id,
                "material_ids": list(self.material_ids),
                "rest_angle_rad": self.rest_angle_rad,
                "rest_length_m": self.rest_length_m,
                "supporting_faces": list(self.supporting_faces),
                "vertices": list(self.vertices)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LatticeLink":
        vertices = tuple(int(v) for v in value["vertices"])
        angle = value.get("rest_angle_rad")
        return cls(int(value["link_id"]), str(value["kind"]), vertices,
                   float(value["rest_length_m"]),
                   None if angle is None else float(angle),
                   tuple(int(v) for v in value["supporting_faces"]),
                   tuple(str(v) for v in value["material_ids"]))


@dataclass(frozen=True)
class CrossLattice:
    vertices: Tuple[CrossVertex, ...]
    faces: Tuple[CrossFace, ...]
    links: Tuple[LatticeLink, ...]
    provenance: Provenance
    discretization: str = "mesoscopic_surface_cross_lattice"
    schema_version: str = "2"

    def to_dict(self) -> Dict[str, Any]:
        return {"discretization": self.discretization,
                "faces": [face.to_dict() for face in self.faces],
                "links": [link.to_dict() for link in self.links],
                "provenance": self.provenance.to_dict(),
                "schema_version": self.schema_version,
                "vertices": [vertex.to_dict() for vertex in self.vertices]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)

    def energy_report(self) -> Dict[str, Any]:
        """Report physical energy separately from bounded diagnostic facets."""
        sections = {name: 0.0 for name in ARM_NAMES}
        diagnostics: Dict[str, List[Dict[str, Any]]] = {name: [] for name in sections}
        for vertex in self.vertices:
            for arm in vertex.arms:
                sections[arm.name] += arm.physical_energy_j
                diagnostics[arm.name].extend(facet.to_dict()
                                             for facet in arm.visible_facets)
        face_energy = {str(face.face_id): face.physical_energy_j
                       for face in self.faces}
        total = math.fsum(sections.values()) + math.fsum(face_energy.values())
        return {"code": "ANSWER", "diagnostic_facets": diagnostics,
                "face_energy_j": face_energy, "section_energy_j": sections,
                "total_physical_energy_j": total, "verdict": "ANSWER"}

    def semantic_digest(self) -> str:
        """Digest geometry/material meaning independent of mesh scan/index order."""
        semantic_faces = []
        for face in self.faces:
            coordinates = sorted(tuple(self.vertices[i].position_m)
                                 for i in face.vertices)
            semantic_faces.append({"energy_j": face.physical_energy_j,
                                   "material_id": face.material_id,
                                   "positions": coordinates})
        semantic_faces.sort(key=lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")))
        payload = {"discretization": self.discretization,
                   "faces": semantic_faces,
                   "schema_version": self.schema_version}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CrossLattice":
        lattice = cls(tuple(CrossVertex.from_dict(v) for v in value["vertices"]),
                      tuple(CrossFace.from_dict(v) for v in value["faces"]),
                      tuple(LatticeLink.from_dict(v) for v in value["links"]),
                      Provenance.from_dict(value["provenance"]),
                      str(value.get("discretization", "")),
                      str(value.get("schema_version", "1")))
        error = validate_cross_lattice(lattice)
        if error is not None:
            raise ValueError(error)
        return lattice

    @classmethod
    def from_json(cls, text: str) -> "CrossLattice":
        return cls.from_dict(json.loads(text))


def _unknown(code: str, reasons: Iterable[str], provenance: Provenance) -> Dict[str, Any]:
    return {"code": code, "provenance": provenance.to_dict(),
            "reasons": list(reasons), "verdict": "UNKNOWN"}


def _answer(lattice: CrossLattice) -> Dict[str, Any]:
    return {"code": "ANSWER", "lattice": lattice.to_dict(),
            "provenance": lattice.provenance.to_dict(), "reasons": [],
            "verdict": "ANSWER"}


def validate_cross_lattice(lattice: CrossLattice, tolerance: float = 1.0e-9
                           ) -> Optional[str]:
    """Return an explanatory error, or ``None`` for a valid local frame model."""
    ids = {vertex.vertex_id for vertex in lattice.vertices}
    if ids != set(range(len(lattice.vertices))):
        return "vertex ids must be contiguous and zero based"
    for vertex in lattice.vertices:
        if vertex.mass_kg <= 0.0 or not math.isfinite(vertex.mass_kg):
            return f"vertex {vertex.vertex_id} has invalid mass"
        axes = (vertex.warp, vertex.weft, vertex.normal)
        if any(abs(_norm(axis) - 1.0) > tolerance for axis in axes):
            return f"vertex {vertex.vertex_id} frame axes are not unit length"
        if any(abs(_dot(a, b)) > tolerance for a, b in
               ((axes[0], axes[1]), (axes[0], axes[2]), (axes[1], axes[2]))):
            return f"vertex {vertex.vertex_id} frame axes are not orthogonal"
        if _dot(_cross(vertex.warp, vertex.weft), vertex.normal) < 1.0 - tolerance:
            return f"vertex {vertex.vertex_id} frame is not right handed"
        if tuple(arm.name for arm in vertex.arms) != ARM_NAMES:
            return f"vertex {vertex.vertex_id} does not have the canonical six arms"
        if any(len(arm.visible_facets) > 4 for arm in vertex.arms):
            return f"vertex {vertex.vertex_id} exceeds four facets per arm"
        if any(arm.neighbor is not None and arm.neighbor not in ids
               for arm in vertex.arms):
            return f"vertex {vertex.vertex_id} arm references an unknown neighbor"
    if any(link.vertices[0] not in ids or link.vertices[1] not in ids or
           link.vertices[0] == link.vertices[1] or link.rest_length_m <= 0.0
           for link in lattice.links):
        return "a link has invalid endpoints or rest length"
    return None


def mesh_to_cross_lattice(
        vertices: Sequence[Sequence[float]],
        faces: Sequence[Sequence[int]], *,
        face_material_ids: Optional[Sequence[str]] = None,
        face_warp_directions: Optional[Sequence[Sequence[float]]] = None,
        velocities: Optional[Sequence[Sequence[float]]] = None,
        vertex_masses: Optional[Sequence[float]] = None,
        face_energies_j: Optional[Sequence[float]] = None,
        arm_physical_energies_j: Optional[Mapping[Tuple[int, str], float]] = None,
        arm_visible_facets: Optional[
            Mapping[Tuple[int, str], Sequence[Mapping[str, Any]]]] = None,
        areal_density_kg_m2: float = 1.0,
        provenance: Optional[Provenance] = None) -> Dict[str, Any]:
    """Convert an oriented indexed triangle mesh to a typed lattice result."""
    prov = provenance or Provenance(
        "indexed-triangle-mesh", "deterministic cross-lattice conversion", "1",
        ("mesoscopic discretization; not atoms or molecules",))
    try:
        points = tuple(_v3(v) for v in vertices)
        triangles = tuple(tuple(int(i) for i in face) for face in faces)
    except (TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_INVALID_INPUT", (str(exc),), prov)
    if not points or not triangles:
        return _unknown("UNKNOWN_EMPTY_MESH", ("vertices and faces are required",), prov)
    if any(len(face) != 3 for face in triangles):
        return _unknown("UNKNOWN_NOT_TRIANGULATED",
                        ("every face must have exactly three indices",), prov)
    if face_material_ids is None:
        materials = tuple("default" for _ in triangles)
    else:
        materials = tuple(str(value) for value in face_material_ids)
        if len(materials) != len(triangles) or any(not value for value in materials):
            return _unknown("UNKNOWN_MATERIAL_MAP",
                            ("one non-empty material id is required per face",), prov)
    if face_warp_directions is not None and len(face_warp_directions) != len(triangles):
        return _unknown("UNKNOWN_MATERIAL_AXES",
                        ("one warp direction is required per face",), prov)
    if face_energies_j is None:
        face_energies = tuple(0.0 for _ in triangles)
    else:
        try:
            face_energies = tuple(float(value) for value in face_energies_j)
        except (TypeError, ValueError) as exc:
            return _unknown("UNKNOWN_INVALID_ENERGY", (str(exc),), prov)
        if len(face_energies) != len(triangles) or any(
                not math.isfinite(value) or value < 0.0 for value in face_energies):
            return _unknown("UNKNOWN_INVALID_ENERGY",
                            ("one finite non-negative energy is required per face",), prov)
    arm_energies = dict(arm_physical_energies_j or {})
    if any(not isinstance(key, tuple) or len(key) != 2 or
           key[1] not in ARM_NAMES or not isinstance(key[0], int)
           for key in arm_energies):
        return _unknown("UNKNOWN_INVALID_ENERGY",
                        ("arm energy keys must be (vertex_id, arm_name)",), prov)
    try:
        arm_energies = {key: float(value) for key, value in arm_energies.items()}
    except (TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_INVALID_ENERGY", (str(exc),), prov)
    if any(not math.isfinite(value) or value < 0.0
           for value in arm_energies.values()):
        return _unknown("UNKNOWN_INVALID_ENERGY",
                        ("arm energies must be finite and non-negative",), prov)
    raw_facets = dict(arm_visible_facets or {})
    if any(not isinstance(key, tuple) or len(key) != 2 or
           key[1] not in ARM_NAMES or not isinstance(key[0], int)
           for key in raw_facets):
        return _unknown("UNKNOWN_INVALID_FACET",
                        ("facet keys must be (vertex_id, arm_name)",), prov)
    over_capacity = sorted((key, len(values)) for key, values in raw_facets.items()
                           if len(values) > 4)
    if over_capacity:
        key, count = over_capacity[0]
        return _unknown("UNKNOWN_REFINEMENT_REQUIRED",
                        (f"arm {key} has {count} independent contributions; "
                         "create a nested refinement cell/layer",), prov)
    parsed_facets: Dict[Tuple[int, str], Tuple[FacetContribution, ...]] = {}
    try:
        for key, values in raw_facets.items():
            parsed_facets[key] = tuple(
                value if isinstance(value, FacetContribution) else
                FacetContribution(
                    str(value["facet_id"]), str(value["signal_kind"]),
                    float(value["energy_j"]),
                    (value.get("provenance")
                     if isinstance(value.get("provenance"), Provenance) else
                     Provenance.from_dict(value.get("provenance", prov.to_dict()))))
                for value in values)
    except (KeyError, TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_INVALID_FACET", (str(exc),), prov)
    if velocities is None:
        speeds = tuple((0.0, 0.0, 0.0) for _ in points)
    else:
        try:
            speeds = tuple(_v3(v) for v in velocities)
        except (TypeError, ValueError) as exc:
            return _unknown("UNKNOWN_INVALID_VELOCITY", (str(exc),), prov)
        if len(speeds) != len(points):
            return _unknown("UNKNOWN_INVALID_VELOCITY",
                            ("one velocity is required per vertex",), prov)
    if not math.isfinite(areal_density_kg_m2) or areal_density_kg_m2 <= 0.0:
        return _unknown("UNKNOWN_INVALID_MASS",
                        ("areal density must be finite and positive",), prov)

    built_faces: List[CrossFace] = []
    edge_faces: Dict[Tuple[int, int], List[Tuple[int, int, int]]] = {}
    vertex_faces: List[List[int]] = [[] for _ in points]
    face_warps: List[Vec3] = []
    for face_id, face in enumerate(triangles):
        if any(i < 0 or i >= len(points) for i in face):
            return _unknown("UNKNOWN_INDEX_OUT_OF_RANGE",
                            (f"face {face_id} references an absent vertex",), prov)
        if len(set(face)) != 3:
            return _unknown("UNKNOWN_DEGENERATE_FACE",
                            (f"face {face_id} repeats a vertex",), prov)
        raw_normal = _cross(_sub(points[face[1]], points[face[0]]),
                            _sub(points[face[2]], points[face[0]]))
        twice_area = _norm(raw_normal)
        if twice_area <= _EPS:
            return _unknown("UNKNOWN_DEGENERATE_FACE",
                            (f"face {face_id} has zero area",), prov)
        normal = _mul(raw_normal, 1.0 / twice_area)
        if face_warp_directions is None:
            warp = _canonical_tangent(normal)
        else:
            try:
                supplied = _v3(face_warp_directions[face_id])
                warp = _unit(_project_tangent(supplied, normal))
            except ValueError:
                return _unknown("UNKNOWN_MATERIAL_AXES",
                                (f"face {face_id} warp axis is not tangent-defining",), prov)
        face_warps.append(warp)
        built_faces.append(CrossFace(face_id, face, materials[face_id],
                                     0.5 * twice_area, normal,
                                     face_energies[face_id]))
        for vertex_id in face:
            vertex_faces[vertex_id].append(face_id)
        for a, b, opposite in ((face[0], face[1], face[2]),
                               (face[1], face[2], face[0]),
                               (face[2], face[0], face[1])):
            edge_faces.setdefault(tuple(sorted((a, b))), []).append(
                (face_id, a, opposite))
    for edge, uses in sorted(edge_faces.items()):
        if len(uses) > 2:
            return _unknown("UNKNOWN_NONMANIFOLD_EDGE",
                            (f"edge {edge} belongs to {len(uses)} faces",), prov)
        if len(uses) == 2 and uses[0][1] == uses[1][1]:
            return _unknown("UNKNOWN_INCONSISTENT_WINDING",
                            (f"faces at edge {edge} traverse it in the same direction",), prov)
    if any(not incident for incident in vertex_faces):
        return _unknown("UNKNOWN_NONMANIFOLD_VERTEX",
                        ("isolated vertices cannot define local cloth frames",), prov)

    normals: List[Vec3] = []
    warps: List[Vec3] = []
    wefts: List[Vec3] = []
    masses_from_area = [0.0 for _ in points]
    for vertex_id, incident in enumerate(vertex_faces):
        normal_sum = (0.0, 0.0, 0.0)
        for face_id in incident:
            face = built_faces[face_id]
            normal_sum = _add(normal_sum, _mul(face.normal, face.area_m2))
            masses_from_area[vertex_id] += face.area_m2 * areal_density_kg_m2 / 3.0
        try:
            normal = _unit(normal_sum)
        except ValueError:
            return _unknown("UNKNOWN_LOCAL_FRAME",
                            (f"vertex {vertex_id} has cancelling incident normals",), prov)
        warp_sum = (0.0, 0.0, 0.0)
        for face_id in incident:
            candidate = _project_tangent(face_warps[face_id], normal)
            if _norm(candidate) > _EPS:
                # Align the unoriented material axes before averaging.
                if _norm(warp_sum) > _EPS and _dot(candidate, warp_sum) < 0.0:
                    candidate = _mul(candidate, -1.0)
                warp_sum = _add(warp_sum, _mul(candidate, built_faces[face_id].area_m2))
        try:
            warp = _unit(warp_sum)
        except ValueError:
            warp = _canonical_tangent(normal)
        weft = _unit(_cross(normal, warp))
        warp = _unit(_cross(weft, normal))
        normals.append(normal)
        warps.append(warp)
        wefts.append(weft)
    if vertex_masses is None:
        masses = tuple(masses_from_area)
    else:
        try:
            masses = tuple(float(value) for value in vertex_masses)
        except (TypeError, ValueError) as exc:
            return _unknown("UNKNOWN_INVALID_MASS", (str(exc),), prov)
        if len(masses) != len(points) or any(not math.isfinite(v) or v <= 0.0
                                             for v in masses):
            return _unknown("UNKNOWN_INVALID_MASS",
                            ("one finite positive mass is required per vertex",), prov)
    if any(vertex_id < 0 or vertex_id >= len(points)
           for vertex_id, _ in tuple(arm_energies) + tuple(parsed_facets)):
        return _unknown("UNKNOWN_INDEX_OUT_OF_RANGE",
                        ("an arm contribution references an absent vertex",), prov)

    structural: List[Tuple[str, int, int, float, Tuple[int, ...], Tuple[str, ...]]] = []
    for edge, uses in sorted(edge_faces.items()):
        a, b = edge
        direction = _unit(_sub(points[b], points[a]))
        avg_warp_raw = _add(warps[a], warps[b])
        avg_warp = warps[a] if _norm(avg_warp_raw) <= _EPS else _unit(avg_warp_raw)
        avg_weft_raw = _add(wefts[a], wefts[b])
        avg_weft = wefts[a] if _norm(avg_weft_raw) <= _EPS else _unit(avg_weft_raw)
        warp_alignment = abs(_dot(direction, avg_warp))
        weft_alignment = abs(_dot(direction, avg_weft))
        kind = "bias" if abs(warp_alignment - weft_alignment) <= 0.15 else (
            "warp" if warp_alignment > weft_alignment else "weft")
        face_ids = tuple(sorted(use[0] for use in uses))
        material_ids = tuple(sorted({materials[i] for i in face_ids}))
        structural.append((kind, a, b, _norm(_sub(points[b], points[a])),
                           face_ids, material_ids))

    link_specs: List[Tuple[str, int, int, float, Optional[float],
                           Tuple[int, ...], Tuple[str, ...]]] = []
    for kind, a, b, length, face_ids, material_ids in structural:
        link_specs.append((kind, a, b, length, None, face_ids, material_ids))
    for edge, uses in sorted(edge_faces.items()):
        if len(uses) != 2:
            continue
        left, right = uses
        a, b = sorted((left[2], right[2]))
        normals_pair = (built_faces[left[0]].normal, built_faces[right[0]].normal)
        angle = math.acos(max(-1.0, min(1.0, _dot(*normals_pair))))
        face_ids = tuple(sorted((left[0], right[0])))
        material_ids = tuple(sorted({materials[i] for i in face_ids}))
        link_specs.append(("bending", a, b, _norm(_sub(points[b], points[a])),
                           angle, face_ids, material_ids))
    kind_order = {"warp": 0, "weft": 1, "bias": 2, "bending": 3}
    link_specs.sort(key=lambda value: (kind_order[value[0]], value[1], value[2],
                                       value[5]))
    links = tuple(LatticeLink(index, spec[0], (spec[1], spec[2]), spec[3],
                              spec[4], spec[5], spec[6])
                  for index, spec in enumerate(link_specs))

    neighbors: Dict[int, List[Tuple[int, float]]] = {i: [] for i in range(len(points))}
    for _, a, b, length, _, _ in structural:
        neighbors[a].append((b, length))
        neighbors[b].append((a, length))

    cross_vertices: List[CrossVertex] = []
    for vertex_id, point in enumerate(points):
        axes = (("+warp", warps[vertex_id], 1.0),
                ("-warp", warps[vertex_id], -1.0),
                ("+weft", wefts[vertex_id], 1.0),
                ("-weft", wefts[vertex_id], -1.0))
        arms: List[CrossArm] = []
        for name, axis, sign in axes:
            candidates = []
            for other, distance in neighbors[vertex_id]:
                direction = _unit(_sub(points[other], point))
                score = sign * _dot(direction, axis)
                if score > _EPS:
                    candidates.append((-score, other, distance))
            if candidates:
                _, neighbor, distance = min(candidates)
                arms.append(CrossArm(
                    name, _mul(axis, sign), neighbor, distance,
                    arm_energies.get((vertex_id, name), 0.0),
                    parsed_facets.get((vertex_id, name), ())))
            else:
                arms.append(CrossArm(
                    name, _mul(axis, sign), None, None,
                    arm_energies.get((vertex_id, name), 0.0),
                    parsed_facets.get((vertex_id, name), ())))
        arms.extend((
            CrossArm("+normal", normals[vertex_id], None, None,
                     arm_energies.get((vertex_id, "+normal"), 0.0),
                     parsed_facets.get((vertex_id, "+normal"), ())),
            CrossArm("-normal", _mul(normals[vertex_id], -1.0), None, None,
                     arm_energies.get((vertex_id, "-normal"), 0.0),
                     parsed_facets.get((vertex_id, "-normal"), ()))))
        cross_vertices.append(CrossVertex(vertex_id, point, speeds[vertex_id],
                                          masses[vertex_id], warps[vertex_id],
                                          wefts[vertex_id], normals[vertex_id],
                                          tuple(arms), prov))
    lattice = CrossLattice(tuple(cross_vertices), tuple(built_faces), links, prov)
    error = validate_cross_lattice(lattice)
    if error is not None:
        return _unknown("UNKNOWN_LOCAL_FRAME", (error,), prov)
    return _answer(lattice)


def jacobi_center_update(
        old_center_m: Sequence[float],
        section_contributions: Sequence[Mapping[str, Any]], *,
        agreement_tolerance_m: float,
        stability_tolerance_m: float,
        provenance: Optional[Provenance] = None) -> Dict[str, Any]:
    """Evaluate all six sections against one old state, then reduce once.

    A contribution proposes a center from its own exterior section.  No proposal
    observes another proposal's update.  A disagreement does not select a winner;
    it returns ``CONTESTED`` without an updated center.
    """
    prov = provenance or Provenance(
        "cross-sections", "six-section Jacobi center reduction", "1",
        ("all sections read the identical old center",))
    try:
        old = _v3(old_center_m)
        agreement = float(agreement_tolerance_m)
        stability = float(stability_tolerance_m)
    except (TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_INVALID_INPUT", (str(exc),), prov)
    if (not math.isfinite(agreement) or agreement < 0.0 or
            not math.isfinite(stability) or stability < 0.0):
        return _unknown("UNKNOWN_INVALID_TOLERANCE",
                        ("tolerances must be finite and non-negative",), prov)
    parsed: Dict[str, Tuple[Vec3, float, str, Vec3]] = {}
    try:
        for value in section_contributions:
            arm = str(value["arm"])
            if arm not in ARM_NAMES or arm in parsed:
                return _unknown("UNKNOWN_SECTION_SET",
                                ("each canonical arm must occur exactly once",), prov)
            center = _v3(value["proposed_center_m"])
            read_center = _v3(value["read_center_m"])
            energy = float(value["physical_energy_j"])
            signal = str(value["signal_kind"])
            if not math.isfinite(energy) or energy < 0.0 or not signal:
                raise ValueError("section energy and signal kind are invalid")
            parsed[arm] = (center, energy, signal, read_center)
    except (KeyError, TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_INVALID_SECTION", (str(exc),), prov)
    if set(parsed) != set(ARM_NAMES):
        return _unknown("UNKNOWN_SECTION_SET",
                        ("all six independent cross-sections are required",), prov)
    if any(value[3] != old for value in parsed.values()):
        return _unknown("UNKNOWN_NON_JACOBI_READ",
                        ("every section must read the identical supplied old center",), prov)
    signals = {value[2] for value in parsed.values()}
    if len(signals) != 1:
        return _unknown("UNKNOWN_MIXED_SIGNAL",
                        ("different signal meanings require separate layers",), prov)
    ordered = tuple((name,) + parsed[name] for name in ARM_NAMES)
    candidate = tuple(math.fsum(item[1][axis] for item in ordered) / 6.0
                      for axis in range(3))
    max_disagreement = max(_norm(_sub(left[1], right[1]))
                           for i, left in enumerate(ordered)
                           for right in ordered[i + 1:])
    energies = {item[0]: item[2] for item in ordered}
    total_energy = math.fsum(energies.values())
    contributions = [{"arm": item[0], "physical_energy_j": item[2],
                      "proposed_center_m": list(item[1]),
                      "read_center_m": list(item[4]),
                      "signal_kind": item[3]} for item in ordered]
    common = {"max_section_disagreement_m": max_disagreement,
              "old_center_m": list(old), "provenance": prov.to_dict(),
              "section_contributions": contributions,
              "section_energy_j": energies,
              "total_physical_energy_j": total_energy}
    if max_disagreement > agreement:
        return dict(common, code="CONTESTED", converged=False,
                    reasons=["cross-sections disagree; no center was selected"],
                    updated_center_m=None, verdict="UNKNOWN")
    movement = _norm(_sub(candidate, old))
    if movement > stability:
        return dict(common, code="IN_PROGRESS", converged=False,
                    movement_m=movement,
                    reasons=["sections agree but the center is not stable"],
                    updated_center_m=list(candidate), verdict="ANSWER")
    return dict(common, code="CONVERGED", converged=True, movement_m=movement,
                reasons=["all sections agree within tolerance and are stable"],
                updated_center_m=list(candidate), verdict="ANSWER")


def typed_result_digest(value: Mapping[str, Any]) -> str:
    """Canonical digest used to pass one typed layer output to the next."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stack_resolution_layers(layers: Sequence[Mapping[str, Any]], *,
                            provenance: Optional[Provenance] = None
                            ) -> Dict[str, Any]:
    """Validate coarse->medium->fine views of one target without voting.

    Every layer is the same target at another resolution, not a partition.  Its
    typed predecessor is chained by digest.  Signal kinds are never combined,
    and copying an unchanged signal into a finer layer is rejected as an
    identity refinement.
    """
    prov = provenance or Provenance(
        "resolution-stack", "typed coarse-to-medium-to-fine composition", "1",
        ("layers inspect the same target at increasing resolution",))
    if len(layers) != 3:
        return _unknown("UNKNOWN_RESOLUTION_STACK",
                        ("exactly coarse, medium and fine layers are required",), prov)
    expected = ("coarse", "medium", "fine")
    normalized: List[Dict[str, Any]] = []
    previous_output: Optional[Mapping[str, Any]] = None
    previous_payload_digest: Optional[str] = None
    target_id: Optional[str] = None
    signal_kind: Optional[str] = None
    for index, raw in enumerate(layers):
        try:
            resolution = str(raw["resolution"])
            current_target = str(raw["target_id"])
            current_signal = str(raw["signal_kind"])
            output = raw["output"]
        except (KeyError, TypeError) as exc:
            return _unknown("UNKNOWN_RESOLUTION_STACK", (str(exc),), prov)
        if resolution != expected[index]:
            return _unknown("UNKNOWN_RESOLUTION_STACK",
                            ("layer order must be coarse, medium, fine",), prov)
        if not current_target or not current_signal or not isinstance(output, Mapping):
            return _unknown("UNKNOWN_RESOLUTION_STACK",
                            ("target, signal and typed output are required",), prov)
        if output.get("verdict") not in ("ANSWER", "UNKNOWN") or not output.get("code"):
            return _unknown("UNKNOWN_UNTYPED_LAYER",
                            (f"{resolution} output is not typed",), prov)
        if target_id is None:
            target_id, signal_kind = current_target, current_signal
        elif current_target != target_id:
            return _unknown("UNKNOWN_DIFFERENT_TARGET",
                            ("all resolutions must inspect the same target",), prov)
        elif current_signal != signal_kind:
            return _unknown("UNKNOWN_MIXED_SIGNAL",
                            ("different signal meanings require separate stacks",), prov)
        if previous_output is not None:
            expected_digest = typed_result_digest(previous_output)
            if raw.get("input_digest") != expected_digest:
                return _unknown("UNKNOWN_BROKEN_LAYER_CHAIN",
                                (f"{resolution} did not consume the preceding typed output",),
                                prov)
        payload = output.get("payload")
        payload_digest = typed_result_digest({"payload": payload})
        if previous_payload_digest == payload_digest:
            return _unknown("UNKNOWN_IDENTITY_REFINEMENT",
                            (f"{resolution} copies the same signal without refinement",), prov)
        normalized.append({"input_digest": raw.get("input_digest"),
                           "output": dict(output), "resolution": resolution,
                           "signal_kind": current_signal,
                           "target_id": current_target})
        previous_output = output
        previous_payload_digest = payload_digest
    return {"code": "ANSWER", "layers": normalized,
            "provenance": prov.to_dict(),
            "reasons": ["typed layers are stacked without voting or signal bundling"],
            "signal_kind": signal_kind, "target_id": target_id,
            "verdict": "ANSWER"}


def lattice_from_result(result: Mapping[str, Any]) -> CrossLattice:
    """Recover the data model from a successful typed conversion result."""
    if result.get("verdict") != "ANSWER" or "lattice" not in result:
        raise ValueError("result does not contain an ANSWER lattice")
    return CrossLattice.from_dict(result["lattice"])
