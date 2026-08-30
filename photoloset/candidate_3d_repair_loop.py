# -*- coding: utf-8 -*-
"""Candidate-specific 3D comparison and bounded Vera repair orchestration.

This module is deliberately an integration boundary, not another garment
classifier or a generic cape/dress generator.  Every candidate must arrive
with either an exact candidate-bound mesh or a ``garment.structure.v1`` graph
that :mod:`photoloset.structure_preview` can triangulate.  Unsupported or
duplicate geometry stops with a typed ``UNKNOWN`` result.

The loop keeps four contracts separate:

* a same-camera, front-only raster comparison from
  :mod:`photoloset.front_projection_compare`;
* an EvidenceCross-style ledger whose support/cause/kind residuals are never
  collapsed into one score;
* a PhysicalCross-style warp/weft/normal deformation ledger;
* an optional Cross cloth scenario.  Scenario values are always labelled
  ``PROPOSED_SIMULATION`` and never become measurements or material facts.

Rear geometry and material identity remain ``PROPOSED``/``UNKNOWN`` even when
the visible-front bounds converge.  Convergence therefore ends at a named
human review gate.  A pattern handoff is emitted only after that approval is
bound to the final geometry digest and every deterministic gate passes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from . import cross_cloth_solver
from . import physics_proof_cross
from . import repairs as pattern_repairs
from . import structure_preview
from .front_projection_compare import (
    ProjectionCompareConfig,
    compare_front_projection,
    decode_mask,
    stable_digest as projection_digest,
)


REQUEST_SCHEMA = "garment.candidate-3d-repair-loop.request.v1"
SCHEMA = "garment.candidate-3d-repair-loop.v1"
CANDIDATE_SCHEMA = "garment.candidate-3d-repair-result.v1"
EVIDENCE_CROSS_SCHEMA = "garment.candidate-evidence-cross.v1"
PHYSICAL_CROSS_SCHEMA = "garment.candidate-physical-cross.v1"
PATTERN_HANDOFF_SCHEMA = "garment.candidate-pattern-handoff.v1"
REAR_HYPOTHESIS_SCHEMA = "garment.typed-rear-hypothesis.v1"
REAR_HYPOTHESIS_AXES = (
    "closure", "back_volume", "layer_continuation", "attachment_topology",
)

ANSWER = "ANSWER"
PROPOSED = "PROPOSED"
HUMAN_REVIEW = "HUMAN_REVIEW"
UNKNOWN = "UNKNOWN"

_EPS = 1.0e-12
_ALLOWED_UNOBSERVED_AUTHORITIES = {
    "", "UNKNOWN", "UNOBSERVED", "PROPOSED", "PROPOSED_PREVIEW",
    "PROPOSED_REAR", "PROPOSED_MATERIAL", "PROPOSED_SIMULATION",
}


@dataclass(frozen=True)
class RepairLoopConfig:
    """Deterministic bounds for one candidate loop."""

    max_rounds: int = 4
    repair_gain: float = 1.0
    max_repairs_per_round: int = 6
    max_scenario_steps: int = 60
    validate_pattern: bool = False
    pattern_repair_budget: int = 4

    def __post_init__(self) -> None:
        if (isinstance(self.max_rounds, bool)
                or not isinstance(self.max_rounds, int)
                or self.max_rounds < 1):
            raise ValueError("max_rounds must be a positive integer")
        if (isinstance(self.max_repairs_per_round, bool)
                or not isinstance(self.max_repairs_per_round, int)
                or self.max_repairs_per_round < 0):
            raise ValueError("max_repairs_per_round must be non-negative")
        if (isinstance(self.max_scenario_steps, bool)
                or not isinstance(self.max_scenario_steps, int)
                or self.max_scenario_steps < 1):
            raise ValueError("max_scenario_steps must be positive")
        if (isinstance(self.pattern_repair_budget, bool)
                or not isinstance(self.pattern_repair_budget, int)
                or self.pattern_repair_budget < 0):
            raise ValueError("pattern_repair_budget must be non-negative")
        if (isinstance(self.repair_gain, bool)
                or not isinstance(self.repair_gain, (int, float))
                or not math.isfinite(float(self.repair_gain))
                or not 0.0 < float(self.repair_gain) <= 1.0):
            raise ValueError("repair_gain must be finite and in (0, 1]")

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_plain(child) for child in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite values are not canonical JSON")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return copy.deepcopy(value)
    raise TypeError("value is not canonical JSON: %s" % type(value).__name__)


def stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _plain(value), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be numeric" % name)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % name)
    return result


def _config(value: Any) -> RepairLoopConfig:
    if value is None:
        return RepairLoopConfig()
    if isinstance(value, RepairLoopConfig):
        return value
    if isinstance(value, Mapping):
        known = set(RepairLoopConfig.__dataclass_fields__)
        return RepairLoopConfig(**{
            key: child for key, child in dict(value).items() if key in known
        })
    raise ValueError("config must be an object")


def _projection_config(value: Any, loop: RepairLoopConfig) -> Dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    raw["max_rounds"] = loop.max_rounds
    raw["max_proposals"] = min(
        int(raw.get("max_proposals", loop.max_repairs_per_round)),
        loop.max_repairs_per_round,
    )
    return ProjectionCompareConfig(**raw).as_dict()


def _candidate_stop(candidate_id: str, code: str, why: str,
                    **detail: Any) -> Dict[str, Any]:
    result = {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "verdict": code,
        "state": UNKNOWN,
        "stop": {"kind": UNKNOWN, "code": code, "why": why},
        "repair_transcript": [],
        "before_geometry_digest": None,
        "after_geometry_digest": None,
        "pattern_handoff": None,
        "authority": {"front": PROPOSED, "rear": "UNKNOWN",
                      "material": "UNKNOWN"},
        "fact_promotions": [],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        **copy.deepcopy(detail),
    }
    result["digest"] = stable_digest(result)
    return result


def _authority_token(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("authority", value.get("state", ""))
    return str(value or "").strip().upper()


def _unobserved_authority_violations(candidate: Mapping[str, Any]
                                     ) -> List[Dict[str, str]]:
    checks: List[Tuple[str, Any]] = []
    authority = candidate.get("authority")
    if isinstance(authority, Mapping):
        checks.extend(("authority.%s" % key, authority.get(key))
                      for key in ("rear", "back", "material"))
    checks.extend([
        ("rear_authority", candidate.get("rear_authority")),
        ("back_authority", candidate.get("back_authority")),
        ("material_authority", candidate.get("material_authority")),
        ("rear", candidate.get("rear")),
        ("back", candidate.get("back")),
        ("material", candidate.get("material")),
    ])
    for envelope_name in ("target_bound_preview", "preview_candidate"):
        envelope = candidate.get(envelope_name)
        if isinstance(envelope, Mapping):
            nested = envelope.get("authority")
            if isinstance(nested, Mapping):
                checks.extend(("%s.authority.%s" % (envelope_name, key),
                               nested.get(key))
                              for key in ("rear", "back", "material"))
    violations = []
    for path, raw in checks:
        if raw is None:
            continue
        token = _authority_token(raw)
        allowed = (token in _ALLOWED_UNOBSERVED_AUTHORITIES
                   or token.startswith("PROPOSED_")
                   or token.startswith("UNKNOWN_"))
        if not allowed:
            violations.append({"path": path, "claimed": token,
                               "required": "PROPOSED_OR_UNKNOWN"})
    return violations


def _extract_structure(candidate: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    direct = candidate.get("structure_graph")
    if isinstance(direct, Mapping):
        return direct
    nested = candidate.get("structure")
    if isinstance(nested, Mapping):
        for key in ("structure_graph", "graph"):
            value = nested.get(key)
            if isinstance(value, Mapping):
                return value
        if isinstance(nested.get("nodes"), Sequence):
            return nested
        deeper = nested.get("structure")
        if isinstance(deeper, Mapping):
            return _extract_structure({"structure": deeper})
    graph = candidate.get("graph")
    return graph if isinstance(graph, Mapping) else None


def _candidate_rear_hypothesis(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    raw = candidate.get("rear_hypothesis")
    if not isinstance(raw, Mapping):
        nested = candidate.get("rear_candidate")
        if isinstance(nested, Mapping):
            raw = nested.get("rear_hypothesis")
    raw = raw if isinstance(raw, Mapping) else {}
    raw_axes = raw.get("axes") if isinstance(raw.get("axes"), Mapping) else {}
    raw_values = (raw.get("axis_values")
                  if isinstance(raw.get("axis_values"), Mapping) else {})
    values: Dict[str, Any] = {}
    for axis in REAR_HYPOTHESIS_AXES:
        record = raw_axes.get(axis)
        if isinstance(record, Mapping) and "value" in record:
            value = record.get("value")
        else:
            value = raw_values.get(axis, raw.get(axis, "UNKNOWN_UNOBSERVED"))
        values[axis] = _plain(value)
    result = {
        "schema": REAR_HYPOTHESIS_SCHEMA,
        "state": PROPOSED,
        "observation_state": "UNKNOWN_UNOBSERVED",
        "axis_values": values,
        "axes_are_independent": True,
        "conflicts_are_not_averaged": True,
        "front_mutation_allowed": False,
        "source_hypothesis_digest": raw.get("hypothesis_digest"),
        "fact_promotions": [],
    }
    result["hypothesis_digest"] = stable_digest(result)
    return result


def _mesh_envelope(candidate: Mapping[str, Any]
                   ) -> Tuple[Optional[Mapping[str, Any]], List[Mapping[str, Any]],
                              str, Optional[str], Optional[Dict[str, Any]]]:
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    for key in ("target_bound_preview", "preview_candidate"):
        envelope = candidate.get(key)
        if not isinstance(envelope, Mapping):
            continue
        if envelope.get("verdict") != ANSWER:
            continue
        bound_id = str(envelope.get("candidate_id", "")).strip()
        if bound_id and bound_id != candidate_id:
            return None, [], key, None, {
                "verdict": "UNKNOWN_CANDIDATE_GEOMETRY_ID_MISMATCH",
                "why": "%s belongs to %s, not %s" %
                       (key, bound_id, candidate_id),
            }
        mesh = envelope.get("mesh")
        if isinstance(mesh, Mapping):
            parts = envelope.get("parts")
            return (mesh,
                    [row for row in parts if isinstance(row, Mapping)]
                    if _sequence(parts) else [],
                    key, str(envelope.get(
                        "preview_digest", envelope.get("digest", ""))) or None,
                    None)
    for key in ("geometry", "mesh"):
        value = candidate.get(key)
        if isinstance(value, Mapping):
            mesh = value.get("mesh") if isinstance(value.get("mesh"), Mapping) else value
            parts = value.get("parts", candidate.get("parts", []))
            return (mesh,
                    [row for row in parts if isinstance(row, Mapping)]
                    if _sequence(parts) else [],
                    key, str(value.get("digest", "")) or None, None)
    structure = _extract_structure(candidate)
    if structure is None:
        return None, [], "none", None, None
    generated = structure_preview.generate_preview(
        copy.deepcopy(dict(structure)), candidate_id=candidate_id)
    if generated.get("verdict") != ANSWER:
        return None, [], "structure_preview", None, {
            "verdict": str(generated.get(
                "verdict", "UNKNOWN_CANDIDATE_GEOMETRY")),
            "why": str(generated.get(
                "why", "candidate-specific preview was unavailable")),
            "upstream": generated,
        }
    return (generated["mesh"], list(generated.get("parts", [])),
            "structure_preview", generated.get("preview_digest"), None)


def _normalise_geometry(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    if not candidate_id:
        raise ValueError("candidate_id is required")
    mesh, supplied_parts, source_kind, source_digest, source_error = (
        _mesh_envelope(candidate))
    if source_error is not None:
        raise ValueError("%s: %s" %
                         (source_error["verdict"], source_error["why"]))
    if not isinstance(mesh, Mapping):
        raise ValueError(
            "candidate-specific mesh or supported structure graph is required; "
            "generic garment fallback is forbidden")
    raw_vertices = mesh.get("vertices")
    raw_faces = mesh.get("faces")
    if not _sequence(raw_vertices) or len(raw_vertices) < 3:
        raise ValueError("candidate mesh needs at least three vertices")
    vertices: List[List[float]] = []
    for index, raw in enumerate(raw_vertices):
        if not _sequence(raw) or len(raw) < 3:
            raise ValueError("vertex %d needs three coordinates" % index)
        vertices.append([_finite(raw[axis], "vertex") for axis in range(3)])
    if not _sequence(raw_faces) or not raw_faces:
        raise ValueError("candidate mesh needs faces")
    faces: List[List[int]] = []
    for face_index, raw in enumerate(raw_faces):
        if not _sequence(raw) or len(raw) < 3:
            raise ValueError("face %d needs at least three indices" % face_index)
        face: List[int] = []
        for token in raw:
            if isinstance(token, bool) or not isinstance(token, int):
                raise ValueError("face indices must be integers")
            if token < 0 or token >= len(vertices):
                raise ValueError("face index is outside candidate vertices")
            face.append(token)
        faces.append(face)

    raw_part_ids = mesh.get("face_node_ids", mesh.get(
        "face_piece_ids", mesh.get("face_component_ids", [])))
    face_part_ids = ([str(value) for value in raw_part_ids]
                     if _sequence(raw_part_ids)
                     and len(raw_part_ids) == len(faces)
                     else ["garment"] * len(faces))
    raw_layers = mesh.get("face_layers", [])
    face_layers = ([int(value) for value in raw_layers]
                   if _sequence(raw_layers) and len(raw_layers) == len(faces)
                   else [0] * len(faces))
    part_layers: Dict[str, int] = {}
    for part_id, layer in zip(face_part_ids, face_layers):
        part_layers.setdefault(part_id, layer)
    for raw in supplied_parts:
        part_id = str(raw.get(
            "node_id", raw.get("piece_id", raw.get("part_id", "")))).strip()
        if not part_id:
            continue
        if isinstance(raw.get("layer"), int) and not isinstance(raw.get("layer"), bool):
            part_layers[part_id] = int(raw["layer"])
        indices = raw.get("face_indices")
        if not _sequence(indices):
            face_range = raw.get("face_range")
            if (_sequence(face_range) and len(face_range) == 2
                    and all(isinstance(value, int) for value in face_range)):
                indices = list(range(int(face_range[0]), int(face_range[1])))
        if _sequence(indices):
            for face_index in indices:
                if (isinstance(face_index, int) and not isinstance(face_index, bool)
                        and 0 <= face_index < len(faces)):
                    face_part_ids[face_index] = part_id
                    face_layers[face_index] = part_layers.get(part_id, 0)

    override_layers = candidate.get("part_layers")
    if isinstance(override_layers, Mapping):
        for key, value in override_layers.items():
            if isinstance(value, int) and not isinstance(value, bool):
                part_layers[str(key)] = int(value)
    for index, part_id in enumerate(face_part_ids):
        face_layers[index] = part_layers.get(part_id, face_layers[index])

    bindings = candidate.get("part_bindings", {})
    part_bindings = ({str(key): str(value) for key, value in bindings.items()}
                     if isinstance(bindings, Mapping) else {})
    colours = candidate.get(
        "visible_color_swatches", candidate.get("color_swatches", {}))
    visible_colours = (copy.deepcopy(dict(colours))
                       if isinstance(colours, Mapping) else {})
    vertex_layers_raw = mesh.get("vertex_layers", [])
    vertex_layers = ([int(value) for value in vertex_layers_raw]
                     if _sequence(vertex_layers_raw)
                     and len(vertex_layers_raw) == len(vertices)
                     else [0] * len(vertices))
    raw_front_indices = candidate.get(
        "front_vertex_indices", mesh.get("front_vertex_indices"))
    if _sequence(raw_front_indices):
        front_vertex_indices = sorted({
            int(value) for value in raw_front_indices
            if (isinstance(value, int) and not isinstance(value, bool)
                and 0 <= int(value) < len(vertices))
        })
        if not front_vertex_indices:
            raise ValueError("front_vertex_indices did not name any mesh vertex")
        front_selection_method = "EXPLICIT_FRONT_VERTEX_INDICES"
    elif "BACK" in str(candidate.get("domain", "")).upper():
        ordered_z = sorted(float(vertex[2]) for vertex in vertices)
        median_z = ordered_z[len(ordered_z) // 2]
        front_vertex_indices = [
            index for index, vertex in enumerate(vertices)
            if float(vertex[2]) >= median_z - _EPS
        ]
        front_selection_method = "CAMERA_FACING_DEPTH_HALF"
    else:
        front_vertex_indices = list(range(len(vertices)))
        front_selection_method = "WHOLE_CANDIDATE_VISIBLE_DOMAIN"
    front_set = set(front_vertex_indices)
    front_faces = [
        [int(index) for index in face]
        for face in faces if all(int(index) in front_set for index in face)
    ]
    computed_front_digest = stable_digest({
        "xy_vertices": [[index, vertices[index][0], vertices[index][1]]
                        for index in front_vertex_indices],
        "front_faces": front_faces,
        "face_parts": [face_part_ids[index]
                       for index, face in enumerate(faces)
                       if all(int(vertex) in front_set for vertex in face)],
    })
    source_front_digest = str(candidate.get("source_front_digest", "")).strip()
    rear_hypothesis = _candidate_rear_hypothesis(candidate)
    result = {
        "candidate_id": candidate_id,
        "candidate_digest": str(candidate.get("candidate_digest", "")) or None,
        "structure_digest": str(candidate.get(
            "structure_digest", mesh.get("structure_digest", ""))) or None,
        "units": str(mesh.get("units", "cm")),
        "vertices": vertices,
        "faces": faces,
        "face_part_ids": face_part_ids,
        "face_layers": face_layers,
        "vertex_layers": vertex_layers,
        "front_vertex_indices": front_vertex_indices,
        "front_selection_method": front_selection_method,
        "computed_front_contract_digest": computed_front_digest,
        "source_front_digest": source_front_digest or None,
        "rear_hypothesis": rear_hypothesis,
        "part_layers": part_layers,
        "part_bindings": part_bindings,
        "visible_color_swatches": visible_colours,
        "source": {
            "kind": source_kind,
            "digest": source_digest,
            "candidate_specific": True,
            "generic_fallback_used": False,
        },
    }
    _seal_geometry(result)
    return result


def _shape_payload(geometry: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "units": geometry["units"],
        "vertices": geometry["vertices"],
        "faces": geometry["faces"],
        "face_part_ids": geometry["face_part_ids"],
        "face_layers": geometry["face_layers"],
        "part_layers": geometry["part_layers"],
    }


def _computed_front_contract_digest(geometry: Mapping[str, Any]) -> str:
    indices = [int(value) for value in geometry.get(
        "front_vertex_indices", range(len(geometry["vertices"]))) ]
    front_set = set(indices)
    front_faces = []
    front_parts = []
    for face, part_id in zip(geometry["faces"], geometry["face_part_ids"]):
        if all(int(index) in front_set for index in face):
            front_faces.append([int(index) for index in face])
            front_parts.append(str(part_id))
    return stable_digest({
        "xy_vertices": [[index, geometry["vertices"][index][0],
                         geometry["vertices"][index][1]]
                        for index in indices],
        "front_faces": front_faces,
        "face_parts": front_parts,
    })


def _seal_geometry(geometry: Dict[str, Any]) -> None:
    geometry["computed_front_contract_digest"] = (
        _computed_front_contract_digest(geometry))
    geometry["shape_digest"] = stable_digest(_shape_payload(geometry))
    geometry["geometry_digest"] = stable_digest({
        **_shape_payload(geometry),
        "part_bindings": geometry.get("part_bindings", {}),
        "visible_color_swatches": geometry.get("visible_color_swatches", {}),
        "front_vertex_indices": geometry.get("front_vertex_indices", []),
        "computed_front_contract_digest": geometry.get(
            "computed_front_contract_digest"),
        "source_front_digest": geometry.get("source_front_digest"),
        "rear_hypothesis": geometry.get("rear_hypothesis", {}),
    })


def build_candidate_geometry(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a strict candidate-bound geometry envelope or a typed stop."""
    candidate_id = (str(candidate.get("candidate_id", "")).strip()
                    if isinstance(candidate, Mapping) else "")
    if not isinstance(candidate, Mapping):
        return _candidate_stop(candidate_id, "UNKNOWN_CANDIDATE_INPUT",
                               "candidate must be an object")
    violations = _unobserved_authority_violations(candidate)
    if violations:
        return _candidate_stop(
            candidate_id, "UNKNOWN_UNOBSERVED_AUTHORITY_PROMOTION",
            "rear or material authority was promoted beyond PROPOSED/UNKNOWN",
            authority_violations=violations)
    try:
        geometry = _normalise_geometry(candidate)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        text = str(exc)
        code = (text.split(":", 1)[0] if text.startswith("UNKNOWN_")
                else "UNKNOWN_CANDIDATE_SPECIFIC_GEOMETRY_REQUIRED")
        return _candidate_stop(candidate_id, code, text)
    return {
        "verdict": ANSWER,
        "state": PROPOSED,
        "candidate_id": candidate_id,
        "geometry": geometry,
        "authority": {"rear": PROPOSED, "material": "UNKNOWN"},
        "fact_promotions": [],
    }


def _mask_bbox(mask: Sequence[Sequence[Any]]) -> Tuple[float, float, float, float]:
    points = [(column, row) for row, values in enumerate(mask)
              for column, value in enumerate(values) if bool(value)]
    if not points:
        raise ValueError("mask has no foreground pixels")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (float(min(xs)), float(min(ys)),
            float(max(xs) + 1), float(max(ys) + 1))


def _bbox(points: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    if not points:
        raise ValueError("points are empty")
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    result = min(xs), min(ys), max(xs), max(ys)
    if result[2] - result[0] <= _EPS or result[3] - result[1] <= _EPS:
        raise ValueError("candidate front projection has a degenerate bounding box")
    return result


def _point_in_polygon(x: float, y: float,
                      polygon: Sequence[Sequence[float]]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if (y1 > y) != (y2 > y):
            intersection = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection:
                inside = not inside
        previous = current
    return inside


def _rasterise(polygons: Sequence[Sequence[Sequence[float]]],
               rows: int, columns: int) -> List[List[int]]:
    mask = [[0 for _ in range(columns)] for _ in range(rows)]
    for row in range(rows):
        y = row + 0.5
        for column in range(columns):
            x = column + 0.5
            if any(_point_in_polygon(x, y, polygon) for polygon in polygons):
                mask[row][column] = 1
    return mask


def _target_part_masks(target: Mapping[str, Any]
                       ) -> Dict[str, Tuple[Tuple[bool, ...], ...]]:
    raw = target.get("typed_part_masks", target.get("part_masks", {}))
    result = {}
    if isinstance(raw, Mapping):
        for key in sorted(raw, key=lambda item: str(item)):
            value = raw[key]
            metadata = value if isinstance(value, Mapping) else {}
            state = str(metadata.get("state", "OBSERVED")).upper()
            visibility = str(metadata.get("visibility", "FRONT")).upper()
            if state != "OBSERVED" or visibility in {"REAR", "UNKNOWN"}:
                continue
            result[str(key)] = decode_mask(value)
    return result


def _camera_digest(target: Mapping[str, Any]) -> Optional[str]:
    supplied = target.get("camera_digest")
    if isinstance(supplied, str) and supplied.strip():
        return supplied.strip()
    camera = target.get("camera")
    return projection_digest(camera) if isinstance(camera, Mapping) else None


def _project_geometry(geometry: Mapping[str, Any], target: Mapping[str, Any]
                      ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    silhouette = decode_mask(target.get(
        "silhouette_mask", target.get("silhouette")))
    rows, columns = len(silhouette), len(silhouette[0])
    target_box = _mask_bbox(silhouette)
    source_points = [[float(point[0]), -float(point[1])]
                     for point in geometry["vertices"]]
    source_box = _bbox(source_points)
    source_width = source_box[2] - source_box[0]
    source_height = source_box[3] - source_box[1]
    target_width = target_box[2] - target_box[0]
    target_height = target_box[3] - target_box[1]
    scale = min(target_width / source_width, target_height / source_height)
    source_center = ((source_box[0] + source_box[2]) * 0.5,
                     (source_box[1] + source_box[3]) * 0.5)
    target_center = ((target_box[0] + target_box[2]) * 0.5,
                     (target_box[1] + target_box[3]) * 0.5)
    projected = [[
        (point[0] - source_center[0]) * scale + target_center[0],
        (point[1] - source_center[1]) * scale + target_center[1],
    ] for point in source_points]
    polygons: List[List[List[float]]] = []
    by_source_part: Dict[str, List[List[List[float]]]] = {}
    part_vertex_indices: Dict[str, Set[int]] = {}
    for face_index, face in enumerate(geometry["faces"]):
        part_id = str(geometry["face_part_ids"][face_index])
        part_vertex_indices.setdefault(part_id, set()).update(int(i) for i in face)
        for offset in range(1, len(face) - 1):
            polygon = [list(projected[int(face[0])]),
                       list(projected[int(face[offset])]),
                       list(projected[int(face[offset + 1])])]
            polygons.append(polygon)
            by_source_part.setdefault(part_id, []).append(polygon)
    silhouette_mask = _rasterise(polygons, rows, columns)
    bindings = dict(geometry.get("part_bindings", {}))
    target_parts = _target_part_masks(target)
    rendered_parts: Dict[str, Any] = {}
    target_to_source: Dict[str, str] = {}
    requested_ids = sorted(set(target_parts) | set(bindings))
    for target_id in requested_ids:
        source_id = str(bindings.get(target_id, target_id))
        target_to_source[target_id] = source_id
        source_polygons = by_source_part.get(source_id)
        if source_polygons:
            rendered_parts[target_id] = {
                "mask": _rasterise(source_polygons, rows, columns),
                "state": PROPOSED,
                "layer": int(geometry.get("part_layers", {}).get(source_id, 0)),
            }
    for source_id in sorted(by_source_part):
        if source_id in target_to_source.values():
            continue
        rendered_parts[source_id] = {
            "mask": _rasterise(by_source_part[source_id], rows, columns),
            "state": PROPOSED,
            "layer": int(geometry.get("part_layers", {}).get(source_id, 0)),
        }
    colours = {}
    raw_colours = geometry.get("visible_color_swatches", {})
    if isinstance(raw_colours, Mapping):
        for target_id in sorted(set(rendered_parts) | set(target_to_source)):
            source_id = target_to_source.get(target_id, target_id)
            value = raw_colours.get(target_id, raw_colours.get(source_id))
            if value is not None:
                colours[target_id] = copy.deepcopy(value)
    camera_digest = _camera_digest(target)
    if camera_digest is None:
        raise ValueError("target requires camera or camera_digest")
    projection = {
        "candidate_id": geometry["candidate_id"],
        "camera_digest": camera_digest,
        "silhouette_mask": {"mask": silhouette_mask, "state": PROPOSED},
        "typed_part_masks": rendered_parts,
        "visible_color_swatches": colours,
        "occlusion_unknown_mask": [[0 for _ in range(columns)]
                                   for _ in range(rows)],
        "authority": {"front": PROPOSED, "rear": PROPOSED,
                      "material": "UNKNOWN"},
    }
    context = {
        "projected_vertices": projected,
        "source_center": list(source_center),
        "target_center": list(target_center),
        "scale": scale,
        "target_bbox": list(target_box),
        "part_vertex_indices": {
            key: sorted(value) for key, value in part_vertex_indices.items()
        },
        "target_to_source": target_to_source,
    }
    return projection, context


def _target_visible_colour(target: Mapping[str, Any], part_id: str) -> Any:
    values = target.get(
        "visible_color_swatches", target.get("color_swatches", {}))
    if isinstance(values, Mapping):
        return copy.deepcopy(values.get(part_id))
    return None


def _transform_vertices_to_mask(
    geometry: Dict[str, Any], target: Mapping[str, Any],
    target_mask: Sequence[Sequence[Any]], indices: Iterable[int], gain: float,
) -> int:
    _, context = _project_geometry(geometry, target)
    selected = sorted(set(int(value) for value in indices))
    if not selected:
        return 0
    projected = context["projected_vertices"]
    current_box = _bbox([projected[index] for index in selected])
    desired_box = _mask_bbox(target_mask)
    current_center = ((current_box[0] + current_box[2]) * 0.5,
                      (current_box[1] + current_box[3]) * 0.5)
    desired_center = ((desired_box[0] + desired_box[2]) * 0.5,
                      (desired_box[1] + desired_box[3]) * 0.5)
    sx = ((desired_box[2] - desired_box[0]) /
          (current_box[2] - current_box[0]))
    sy = ((desired_box[3] - desired_box[1]) /
          (current_box[3] - current_box[1]))
    scale = float(context["scale"])
    source_center = context["source_center"]
    target_center = context["target_center"]
    changed = 0
    for index in selected:
        px, py = projected[index]
        wanted_x = desired_center[0] + (px - current_center[0]) * sx
        wanted_y = desired_center[1] + (py - current_center[1]) * sy
        next_x = px + (wanted_x - px) * gain
        next_y = py + (wanted_y - py) * gain
        raw_x = (next_x - target_center[0]) / scale + source_center[0]
        flipped_y = (next_y - target_center[1]) / scale + source_center[1]
        raw_y = -flipped_y
        before = geometry["vertices"][index]
        if abs(before[0] - raw_x) > _EPS or abs(before[1] - raw_y) > _EPS:
            before[0] = round(raw_x, 12)
            before[1] = round(raw_y, 12)
            changed += 1
    return changed


def _candidate_specific_proposals(
    candidate_id: str, rear_hypothesis: Mapping[str, Any], proposals: Any,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if _sequence(proposals):
        for source in proposals:
            if not isinstance(source, Mapping):
                continue
            row = copy.deepcopy(dict(source))
            row["upstream_proposal_id"] = row.get("proposal_id")
            row["candidate_id"] = candidate_id
            row["rear_hypothesis_digest"] = rear_hypothesis.get(
                "hypothesis_digest")
            row["mutation_domain"] = "VISIBLE_FRONT_ONLY"
            row["preserve_unobserved_rear_hypothesis"] = True
            row["proposal_id"] = stable_digest({
                key: value for key, value in row.items()
                if key != "proposal_id"
            })[:20]
            rows.append(row)
    return rows


def _rear_axis_repair_constraints(
    candidate_id: str, rear_hypothesis: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    values = rear_hypothesis.get("axis_values", {})
    return [
        {
            "candidate_id": candidate_id,
            "axis": axis,
            "value": copy.deepcopy(values.get(axis, "UNKNOWN_UNOBSERVED")),
            "state": PROPOSED,
            "operation": "PRESERVE_TYPED_REAR_AXIS",
            "applied_from_front_evidence": False,
            "why": "same-camera front residual cannot observe or rewrite this rear axis",
            "rear_hypothesis_digest": rear_hypothesis.get(
                "hypothesis_digest"),
        }
        for axis in REAR_HYPOTHESIS_AXES
    ]


def _comparison_contract(
    evaluation: Mapping[str, Any], rear_hypothesis: Mapping[str, Any],
) -> Dict[str, Any]:
    """Describe the independent residuals that may drive a front repair.

    This is deliberately not a weighted similarity score.  A silhouette gain
    cannot cancel a typed-part or layer-order regression, and none of these
    front observations can rewrite an unobserved rear hypothesis.
    """
    axes = evaluation.get("axes", {})
    axes = axes if isinstance(axes, Mapping) else {}
    return {
        "camera_binding": copy.deepcopy(evaluation.get("camera_binding")),
        "same_camera_required": True,
        "independent_comparisons": {
            "silhouette": {
                "present": "silhouette" in axes,
                "representation": "BINARY_FRONT_MASK",
            },
            "typed_part_masks": {
                "present": "parts" in axes,
                "representation": "TYPED_FRONT_PART_MASKS",
            },
            "layer_order": {
                "present": "layer_occlusion" in axes,
                "representation": "VISIBLE_FRONT_LAYER_ORDER",
            },
        },
        "no_aggregate_similarity_score": True,
        "improvements_never_offset_regressions": True,
        "rear_hypothesis_digest": rear_hypothesis.get("hypothesis_digest"),
        "rear_axes_excluded_from_front_scoring": list(REAR_HYPOTHESIS_AXES),
    }


def _apply_repairs(geometry: Mapping[str, Any], target: Mapping[str, Any],
                   proposals: Sequence[Mapping[str, Any]], *, gain: float,
                   limit: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    current = copy.deepcopy(dict(geometry))
    before_digest = str(current["geometry_digest"])
    operations: List[Dict[str, Any]] = []
    total_changed = 0
    target_parts = _target_part_masks(target)
    for proposal in list(proposals)[:limit]:
        operation = str(proposal.get("operation", ""))
        target_id = str(proposal.get("target", ""))
        changed = 0
        detail: Dict[str, Any] = {}
        if operation in {"ADJUST_FRONT_SILHOUETTE",
                         "REFINE_VISIBLE_FRONT_BOUNDARY"}:
            mask = decode_mask(target.get(
                "silhouette_mask", target.get("silhouette")))
            changed = _transform_vertices_to_mask(
                current, target, mask,
                current.get("front_vertex_indices",
                            range(len(current["vertices"]))), gain)
        elif operation == "ALIGN_TYPED_PART_MASK" and target_id in target_parts:
            source_id = str(current.get("part_bindings", {}).get(
                target_id, target_id))
            indices = set()
            for face, part_id in zip(current["faces"], current["face_part_ids"]):
                if str(part_id) == source_id:
                    indices.update(int(value) for value in face)
            indices.intersection_update(set(current.get(
                "front_vertex_indices", range(len(current["vertices"])))))
            if indices:
                changed = _transform_vertices_to_mask(
                    current, target, target_parts[target_id], indices, gain)
            else:
                detail["cannot_apply"] = "candidate has no bound part %s" % source_id
        elif operation == "REORDER_VISIBLE_FRONT_LAYERS":
            raw_parts = target.get(
                "typed_part_masks", target.get("part_masks", {}))
            if isinstance(raw_parts, Mapping):
                for observed_id in sorted(raw_parts, key=lambda item: str(item)):
                    record = raw_parts[observed_id]
                    if not isinstance(record, Mapping) or not isinstance(
                            record.get("layer"), int):
                        continue
                    source_id = str(current.get("part_bindings", {}).get(
                        str(observed_id), str(observed_id)))
                    desired = int(record["layer"])
                    if current["part_layers"].get(source_id) != desired:
                        current["part_layers"][source_id] = desired
                        changed += 1
                for index, part_id in enumerate(current["face_part_ids"]):
                    current["face_layers"][index] = current[
                        "part_layers"].get(part_id, current["face_layers"][index])
        elif operation in {"BIND_VISIBLE_PART_COLOR",
                           "ADJUST_VISIBLE_PART_COLOR"}:
            colour = _target_visible_colour(target, target_id)
            if colour is not None:
                before = current["visible_color_swatches"].get(target_id)
                if before != colour:
                    current["visible_color_swatches"][target_id] = colour
                    changed = 1
        elif operation == "RENDER_KNOWN_FRONT_COVERAGE":
            detail["cannot_apply"] = (
                "coverage requires new candidate topology; no geometry is invented")
        else:
            detail["cannot_apply"] = "unsupported bounded repair operation"
        total_changed += changed
        operations.append({
            "proposal_id": proposal.get("proposal_id"),
            "upstream_proposal_id": proposal.get("upstream_proposal_id"),
            "candidate_id": proposal.get("candidate_id"),
            "rear_hypothesis_digest": proposal.get(
                "rear_hypothesis_digest"),
            "operation": operation,
            "target": target_id,
            "changed_vertices_or_records": changed,
            **detail,
        })
    _seal_geometry(current)
    return current, {
        "state": PROPOSED,
        "before_geometry_digest": before_digest,
        "after_geometry_digest": current["geometry_digest"],
        "changed_vertices_or_records": total_changed,
        "operations": operations,
        "deterministic_order": True,
        "invented_rear_geometry": False,
        "front_vertex_only_geometry_mutation": True,
        "rear_hypothesis_preserved": True,
        "material_promoted": False,
    }


def _residual(path: str, value: Any, *, authority: str,
              source_digest: Any, meaning: str) -> Dict[str, Any]:
    return {"path": path, "value": copy.deepcopy(value),
            "authority": authority, "source_digest": source_digest,
            "meaning": meaning}


def _evidence_cross(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    axes = evaluation.get("axes", {})
    support_plus = []
    if isinstance(axes, Mapping):
        silhouette = axes.get("silhouette", {})
        edge = axes.get("edge_chamfer", {})
        support_plus.extend([
            _residual("front/silhouette/iou_loss",
                      1.0 - float(silhouette.get("iou", 0.0)),
                      authority="DERIVED_FROM_OBSERVED_FRONT",
                      source_digest=evaluation.get("observation_digest"),
                      meaning="same-camera visible silhouette residual"),
            _residual("front/edge/normalized_chamfer",
                      edge.get("distance_normalized_by_image_diagonal"),
                      authority="DERIVED_FROM_OBSERVED_FRONT",
                      source_digest=evaluation.get("observation_digest"),
                      meaning="same-camera visible boundary residual"),
        ])
        parts = axes.get("parts", {}).get("per_part", {})
        if isinstance(parts, Mapping):
            for part_id in sorted(parts):
                support_plus.append(_residual(
                    "front/parts/%s/iou_loss" % part_id,
                    1.0 - float(parts[part_id].get("iou", 0.0)),
                    authority="DERIVED_FROM_OBSERVED_FRONT",
                    source_digest=evaluation.get("observation_digest"),
                    meaning="typed visible-part residual"))
    exclusions = evaluation.get("excluded_from_scoring", {})
    support_minus = [_residual(
        "front/exclusions", copy.deepcopy(exclusions),
        authority="UNKNOWN_EXCLUDED_NOT_INFERRED",
        source_digest=evaluation.get("observation_digest"),
        meaning="rear, occlusion-unknown and unobserved parts are not scored")]
    proposals = evaluation.get("proposals", [])
    cause_plus = [_residual(
        "proposal/%s" % row.get("proposal_id"),
        {"operation": row.get("operation"), "target": row.get("target")},
        authority=PROPOSED, source_digest=evaluation.get("evaluation_digest"),
        meaning="repair cause proposal, not an observed cause")
        for row in proposals if isinstance(row, Mapping)]
    regressions = evaluation.get("comparison_to_previous", {}).get(
        "regressions", [])
    cause_minus = [_residual(
        "regression/%s" % row.get("axis_path"), row,
        authority="DERIVED_COMPARISON",
        source_digest=evaluation.get("evaluation_digest"),
        meaning="axis worsened and may not be offset by another improvement")
        for row in regressions if isinstance(row, Mapping)]
    layer = axes.get("layer_occlusion", {}) if isinstance(axes, Mapping) else {}
    kind_plus = [
        _residual("kind/visible-part-inventory",
                  sorted(axes.get("parts", {}).get("per_part", {}))
                  if isinstance(axes, Mapping) else [],
                  authority="OBSERVED_FRONT_TYPES",
                  source_digest=evaluation.get("observation_digest"),
                  meaning="typed front inventory remains separate from shape"),
        _residual("kind/visible-layer-order",
                  layer.get("observation_relations", []),
                  authority="OBSERVED_FRONT_TYPES",
                  source_digest=evaluation.get("observation_digest"),
                  meaning="visible layer order remains a separate residual"),
    ]
    kind_minus = [
        _residual("kind/rear", "UNOBSERVED",
                  authority=PROPOSED, source_digest=None,
                  meaning="rear alternatives are proposals only"),
        _residual("kind/material", "UNOBSERVED",
                  authority="UNKNOWN", source_digest=None,
                  meaning="material identity is not inferred from front fit"),
    ]
    result = {
        "schema": EVIDENCE_CROSS_SCHEMA,
        "candidate_id": evaluation.get("candidate_id"),
        "round_index": evaluation.get("round_index"),
        "arms": {"support+": support_plus, "support-": support_minus,
                 "cause+": cause_plus, "cause-": cause_minus,
                 "kind+": kind_plus, "kind-": kind_minus},
        "reduction": "SEPARATE_AXES_NO_WEIGHTED_SCORE",
        "disagreement_preserved": True,
        "fact_promotions": [],
    }
    result["digest"] = stable_digest(result)
    return result


def _span(vertices: Sequence[Sequence[float]], axis: int) -> float:
    values = [float(row[axis]) for row in vertices]
    return max(values) - min(values)


def _physical_cross(before: Mapping[str, Any], after: Mapping[str, Any],
                    scenario_results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    before_vertices = before["vertices"]
    after_vertices = after["vertices"]
    weft_before, weft_after = _span(before_vertices, 0), _span(after_vertices, 0)
    warp_before, warp_after = _span(before_vertices, 1), _span(after_vertices, 1)
    normal_delta = (sum(abs(float(b[2]) - float(a[2]))
                        for b, a in zip(before_vertices, after_vertices)) /
                    max(len(before_vertices), 1))
    weft = ((weft_after - weft_before) / weft_before
            if weft_before > _EPS else None)
    warp = ((warp_after - warp_before) / warp_before
            if warp_before > _EPS else None)

    def arm(value: Optional[float], positive: bool, name: str) -> Dict[str, Any]:
        residual = None if value is None else max(value if positive else -value, 0.0)
        return {
            "residual": residual,
            "quantity": "dimensionless_strain" if name != "normal" else "length",
            "authority": "DERIVED_REPAIR_DEFORMATION",
            "not_measurement": True,
            "source": "before/after candidate geometry",
        }

    arms = {
        "warp+": arm(warp, True, "warp"),
        "warp-": arm(warp, False, "warp"),
        "weft+": arm(weft, True, "weft"),
        "weft-": arm(weft, False, "weft"),
        "normal+": {"residual": normal_delta, "quantity": after["units"],
                    "authority": "DERIVED_REPAIR_DEFORMATION",
                    "not_measurement": True,
                    "source": "mean absolute normal displacement"},
        "normal-": {"residual": 0.0, "quantity": after["units"],
                    "authority": "DERIVED_REPAIR_DEFORMATION",
                    "not_measurement": True,
                    "source": "normal sign is not inferred by the front repair"},
    }
    result = {
        "schema": PHYSICAL_CROSS_SCHEMA,
        "candidate_id": after["candidate_id"],
        "local_basis": ["warp", "weft", "normal"],
        "arms": arms,
        "scenarios": copy.deepcopy(list(scenario_results)),
        "scenario_values_are_measurements": False,
        "solver_exchange_contract": "typed directional residuals",
        "deterministic_reduction": True,
    }
    result["digest"] = stable_digest(result)
    return result


def _scenario_results(geometry: Mapping[str, Any], scenarios: Any,
                      config: RepairLoopConfig) -> List[Dict[str, Any]]:
    if not _sequence(scenarios):
        return []
    values = []
    for index, raw in enumerate(scenarios):
        if not isinstance(raw, Mapping):
            continue
        applies_to = raw.get("candidate_id")
        if applies_to not in (None, "", geometry["candidate_id"]):
            continue
        scenario_id = str(raw.get("scenario_id", "scenario-%d" % (index + 1)))
        profile = raw.get("material")
        materials = raw.get("materials")
        material_id = str(raw.get("material_id", "proposed-material"))
        if isinstance(profile, Mapping):
            materials = {material_id: copy.deepcopy(dict(profile))}
        if not isinstance(materials, Mapping) or not materials:
            values.append({
                "scenario_id": scenario_id,
                "verdict": "UNKNOWN_SCENARIO_MATERIAL_REQUIRED",
                "authority": "PROPOSED_SIMULATION",
                "not_measurement": True,
            })
            continue
        material_ids = sorted(str(key) for key in materials)
        face_material_ids = raw.get("face_material_ids")
        if not (_sequence(face_material_ids)
                and len(face_material_ids) == len(geometry["faces"])):
            face_material_ids = [material_ids[0]] * len(geometry["faces"])
        unit_scale = 0.01 if str(geometry["units"]).lower() == "cm" else 1.0
        vertices = [[float(value) * unit_scale for value in point]
                    for point in geometry["vertices"]]
        max_y = max(point[1] for point in vertices)
        fixed = [i for i, point in enumerate(vertices)
                 if abs(point[1] - max_y) <= 1.0e-9]
        steps = raw.get("steps", min(12, config.max_scenario_steps))
        if not isinstance(steps, int) or isinstance(steps, bool):
            steps = min(12, config.max_scenario_steps)
        steps = max(1, min(steps, config.max_scenario_steps))
        simulated = cross_cloth_solver.simulate(
            vertices, geometry["faces"],
            face_material_ids=list(face_material_ids),
            materials=copy.deepcopy(dict(materials)),
            fixed_vertices=fixed,
            vertex_layers=geometry.get("vertex_layers"),
            constraints=copy.deepcopy(raw.get("constraints", {})),
            environment=copy.deepcopy(raw.get("environment", {})),
            time_step_s=float(raw.get("time_step_s", 1.0 / 120.0)),
            steps=steps,
            constraint_iterations=int(raw.get("constraint_iterations", 12)),
            stable_steps_required=int(raw.get("stable_steps_required", 5)),
        )
        row = {
            "scenario_id": scenario_id,
            "verdict": simulated.get("verdict"),
            "terminal_verdict": simulated.get("terminal_verdict"),
            "authority": "PROPOSED_SIMULATION",
            "material_authority": "PROPOSED_SCENARIO_NOT_IDENTIFIED",
            "not_measurement": True,
            "does_not_update_candidate_material": True,
            "required_gate": bool(raw.get("required", False)),
            "simulation_digest": stable_digest(simulated),
            "diagnostics": {
                "history_length": len(simulated.get("history", [])),
                "failed_stage": simulated.get("failed_stage"),
            },
        }
        values.append(row)
    return values


def _proof_cross(candidate_id: str, first: Mapping[str, Any],
                 final: Mapping[str, Any]) -> Dict[str, Any]:
    initial = first.get("axis_losses_for_iteration_only", {})
    after = final.get("axis_losses_for_iteration_only", {})
    obligations = []
    if isinstance(initial, Mapping) and isinstance(after, Mapping):
        for path in sorted(set(initial) & set(after)):
            before, current = initial[path], after[path]
            if not isinstance(before, (int, float)) or isinstance(before, bool):
                continue
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                continue
            if float(before) > 0.0:
                predicate = "residual_reduction"
                data = {"initial": float(before), "final": float(current),
                        "minimum_factor": 1}
            else:
                predicate = "bounded_absolute"
                data = {"value": float(current), "bound": 0}
            obligations.append({
                "id": "axis-%s" % stable_digest(path)[:16],
                "statement": "%s did not worsen across the bounded loop" % path,
                "predicate": predicate,
                "data": data,
                "effect": "gates only this reported front residual",
            })
    if not obligations:
        return {"verdict": "UNKNOWN_PROOF_OBLIGATION",
                "scope": "SELF_REPORTED_ARITHMETIC_ONLY"}
    result = physics_proof_cross.verify({
        "schema": physics_proof_cross.SCHEMA,
        "run_id": "%s:%s" % (candidate_id,
                               final.get("evaluation_digest", "")[:16]),
        "solver": "candidate-3d-repair-loop",
        "obligations": obligations,
    })
    result["scope"] = "SELF_REPORTED_ARITHMETIC_ONLY"
    result["external_physical_validation"] = False
    return result


def _approval_for(request: Mapping[str, Any], candidate: Mapping[str, Any]
                  ) -> Optional[Mapping[str, Any]]:
    direct = candidate.get("human_approval")
    if isinstance(direct, Mapping):
        return direct
    approvals = request.get("human_approvals", request.get("approvals"))
    if isinstance(approvals, Mapping):
        value = approvals.get(candidate.get("candidate_id"))
        if isinstance(value, Mapping):
            return value
    if _sequence(approvals):
        for row in approvals:
            if (isinstance(row, Mapping)
                    and row.get("candidate_id") == candidate.get("candidate_id")):
                return row
    return None


def _verify_approval(approval: Optional[Mapping[str, Any]], candidate_id: str,
                     candidate_digest: str,
                     final_geometry_digest: str) -> Dict[str, Any]:
    if approval is None:
        return {"verdict": "HUMAN_REVIEW_REQUIRED",
                "why": (
                    "a named approval bound to the candidate and final "
                    "geometry digests is required")}
    by = str(approval.get("by", approval.get("approver", ""))).strip()
    decision = str(approval.get("decision", "APPROVE")).upper()
    bound_id = str(approval.get("candidate_id", "")).strip()
    bound_candidate_digest = str(approval.get(
        "candidate_digest", "")).strip()
    bound_digest = str(approval.get(
        "final_geometry_digest",
        approval.get("geometry_digest", ""))).strip()
    if (not candidate_digest or not by or decision != "APPROVE"
            or bound_id != candidate_id
            or bound_candidate_digest != candidate_digest
            or bound_digest != final_geometry_digest):
        return {
            "verdict": "HUMAN_REVIEW_STALE_OR_INCOMPLETE",
            "why": (
                "approval must name an approver and bind the exact candidate "
                "id, candidate digest, and final geometry digest"),
            "expected_candidate_id": candidate_id,
            "expected_candidate_digest": candidate_digest or None,
            "expected_final_geometry_digest": final_geometry_digest,
        }
    payload = {"candidate_id": candidate_id,
               "candidate_digest": candidate_digest,
               "final_geometry_digest": final_geometry_digest,
               "approver": by, "decision": decision}
    return {"verdict": ANSWER, "approval": payload,
            "approval_digest": stable_digest(payload)}


def _pattern_source(candidate: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    direct = candidate.get("pattern_handoff")
    if isinstance(direct, Mapping):
        return copy.deepcopy(dict(direct))
    artifacts = {}
    for key in ("pattern_candidate", "cutting_pattern", "sewing_plan"):
        value = candidate.get(key)
        if isinstance(value, Mapping):
            artifacts[key] = copy.deepcopy(dict(value))
    return artifacts or None


def _validate_pattern_source(candidate: Mapping[str, Any], source: Dict[str, Any],
                             config: RepairLoopConfig) -> Dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    candidate_digest = str(candidate.get("candidate_digest", ""))
    source_candidate_id = source.get("candidate_id")
    if source_candidate_id not in (None, "", candidate_id):
        return {"verdict": "UNKNOWN_PATTERN_CANDIDATE_BINDING",
                "why": "pattern handoff belongs to another candidate"}
    source_candidate_digest = source.get("candidate_digest")
    if (candidate_digest and source_candidate_digest not in
            (None, "", candidate_digest)):
        return {"verdict": "UNKNOWN_PATTERN_CANDIDATE_DIGEST_BINDING",
                "why": "pattern handoff carries a stale candidate digest"}
    source_verdict = str(source.get("verdict", ""))
    if source.get("state") == "STOPPED" or source_verdict.startswith("UNKNOWN_"):
        return {"verdict": "UNKNOWN_PATTERN_ARTIFACT_STOPPED",
                "why": "pattern handoff is stopped", "artifact": source}
    for name, artifact in source.items():
        if not isinstance(artifact, Mapping):
            continue
        bound_id = artifact.get("candidate_id")
        if bound_id not in (None, "", candidate_id):
            return {"verdict": "UNKNOWN_PATTERN_CANDIDATE_BINDING",
                    "why": "%s belongs to another candidate" % name}
        bound_digest = artifact.get("candidate_digest")
        if (candidate_digest and bound_digest not in
                (None, "", candidate_digest)):
            return {"verdict": "UNKNOWN_PATTERN_CANDIDATE_DIGEST_BINDING",
                    "why": "%s carries a stale candidate digest" % name}
        verdict = str(artifact.get("verdict", ""))
        if artifact.get("state") == "STOPPED" or verdict.startswith("UNKNOWN_"):
            return {"verdict": "UNKNOWN_PATTERN_ARTIFACT_STOPPED",
                    "why": "%s is stopped" % name, "artifact": artifact}
    repair_result = None
    pattern = source.get("pattern")
    if config.validate_pattern and isinstance(pattern, dict):
        repair_result = pattern_repairs.make_sewable(
            pattern, budget=config.pattern_repair_budget)
        if not repair_result.get("sewable"):
            return {"verdict": "UNKNOWN_PATTERN_NOT_SEWABLE",
                    "why": repair_result.get("stop_reason"),
                    "pattern_repair": repair_result}
        source["pattern"] = repair_result["pattern"]
    return {"verdict": ANSWER, "source": source,
            "pattern_repair": repair_result}


def _make_pattern_handoff(candidate: Mapping[str, Any], source: Dict[str, Any],
                          approval: Mapping[str, Any], evaluation: Mapping[str, Any],
                          final_geometry_digest: str,
                          pattern_repair: Any) -> Dict[str, Any]:
    result = {
        "schema": PATTERN_HANDOFF_SCHEMA,
        "verdict": ANSWER,
        "state": PROPOSED,
        "candidate_id": candidate["candidate_id"],
        "candidate_digest": candidate.get("candidate_digest"),
        "final_geometry_digest": final_geometry_digest,
        "front_evaluation_digest": evaluation.get("evaluation_digest"),
        "human_approval": copy.deepcopy(approval.get("approval")),
        "human_approval_digest": approval.get("approval_digest"),
        "artifacts": copy.deepcopy(source),
        "pattern_repair_transcript": (
            copy.deepcopy(pattern_repair.get("transcript", []))
            if isinstance(pattern_repair, Mapping) else []),
        "authority": {"front_fit": PROPOSED, "rear": PROPOSED,
                      "material": "UNKNOWN"},
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "fact_promotions": [],
    }
    result["handoff_digest"] = stable_digest(result)
    return result


def _run_candidate(request: Mapping[str, Any], candidate: Mapping[str, Any],
                   target: Mapping[str, Any], initial_geometry: Mapping[str, Any],
                   config: RepairLoopConfig,
                   projection_config: Mapping[str, Any]) -> Dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    candidate_digest = str(candidate.get("candidate_digest", "")).strip()
    before = copy.deepcopy(dict(initial_geometry))
    current = copy.deepcopy(before)
    accepted_geometry = copy.deepcopy(before)
    rear_hypothesis = copy.deepcopy(current["rear_hypothesis"])
    rear_axis_constraints = _rear_axis_repair_constraints(
        candidate_id, rear_hypothesis)
    transcript: List[Dict[str, Any]] = []
    accepted_evaluations: List[Dict[str, Any]] = []
    previous: Optional[Mapping[str, Any]] = None
    non_improvement_stop: Optional[Dict[str, Any]] = None
    terminal_code = "UNKNOWN_REPAIR_LOOP_INTERNAL"
    terminal_kind = UNKNOWN

    for round_index in range(1, config.max_rounds + 1):
        try:
            projection, _ = _project_geometry(current, target)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            return _candidate_stop(
                candidate_id, "UNKNOWN_SAME_CAMERA_SIMULATION",
                str(exc), before_geometry_digest=before["geometry_digest"],
                after_geometry_digest=current["geometry_digest"],
                candidate_geometry=current, repair_transcript=transcript)
        evaluation = compare_front_projection(
            target, projection, round_index=round_index,
            previous=previous, config=projection_config)
        evaluation_digest = evaluation.get("evaluation_digest")
        if evaluation.get("verdict") != "PROPOSED_FRONT_PROJECTION_EVALUATION":
            return _candidate_stop(
                candidate_id, str(evaluation.get(
                    "verdict", "UNKNOWN_FRONT_PROJECTION_COMPARISON")),
                str(evaluation.get("why", "front projection comparison stopped")),
                before_geometry_digest=before["geometry_digest"],
                after_geometry_digest=current["geometry_digest"],
                candidate_geometry=current, repair_transcript=transcript,
                comparison=evaluation)
        cross = _evidence_cross(evaluation)
        convergence = evaluation["convergence"]["status"]
        proposals = _candidate_specific_proposals(
            candidate_id, rear_hypothesis, evaluation.get("proposals", []))
        step: Dict[str, Any] = {
            "round": round_index,
            "stage_order": ["PROPOSAL", "SIMULATE", "COMPARE", "REPAIR"],
            "proposal_state": PROPOSED,
            "candidate_specific_proposals": copy.deepcopy(proposals),
            "rear_axis_constraints": copy.deepcopy(rear_axis_constraints),
            "simulation": {
                "kind": "SAME_CAMERA_FRONT_PROJECTION",
                "projection_digest": stable_digest(projection),
                "geometry_digest": current["geometry_digest"],
                "authority": PROPOSED,
            },
            "comparison_digest": evaluation_digest,
            "comparison_contract": _comparison_contract(
                evaluation, rear_hypothesis),
            "convergence": convergence,
            "evidence_cross": cross,
            "repair": None,
        }
        if convergence in {"REJECT_WORSENED", "STALLED_TIE"}:
            attempted_digest = str(current["geometry_digest"])
            restored_digest = str(accepted_geometry["geometry_digest"])
            current = copy.deepcopy(accepted_geometry)
            non_improvement_stop = {
                "status": convergence,
                "attempted_geometry_digest": attempted_digest,
                "restored_geometry_digest": restored_digest,
                "attempted_evaluation_digest": evaluation_digest,
                "accepted_evaluation_digest": (
                    accepted_evaluations[-1].get("evaluation_digest")
                    if accepted_evaluations else None),
                "stopped_without_applying_more_repairs": True,
            }
            step["non_improvement_stop"] = True
            step["rollback"] = copy.deepcopy(non_improvement_stop)
            terminal_code = "HUMAN_REVIEW_NON_IMPROVEMENT"
            terminal_kind = HUMAN_REVIEW
            transcript.append(step)
            break

        # The current geometry is accepted only after its independent axes
        # have not regressed.  A following repair remains provisional until
        # the next same-camera comparison accepts it.
        accepted_geometry = copy.deepcopy(current)
        accepted_evaluations.append(copy.deepcopy(evaluation))
        if convergence == "CONVERGED":
            terminal_code = "HUMAN_REVIEW_REQUIRED"
            terminal_kind = HUMAN_REVIEW
            transcript.append(step)
            break
        if convergence == "MAX_ROUNDS_REACHED":
            terminal_code = "HUMAN_REVIEW_NON_CONVERGENCE"
            terminal_kind = HUMAN_REVIEW
            transcript.append(step)
            break
        repaired, repair_record = _apply_repairs(
            current, target, proposals,
            gain=float(config.repair_gain),
            limit=config.max_repairs_per_round)
        step["repair"] = repair_record
        transcript.append(step)
        if repair_record["changed_vertices_or_records"] == 0:
            terminal_code = "HUMAN_REVIEW_REPAIR_UNAVAILABLE"
            terminal_kind = HUMAN_REVIEW
            break
        current = repaired
        previous = evaluation
    else:
        terminal_code = "HUMAN_REVIEW_NON_CONVERGENCE"
        terminal_kind = HUMAN_REVIEW

    if not accepted_evaluations:
        return _candidate_stop(
            candidate_id, "UNKNOWN_NO_ACCEPTED_FRONT_EVALUATION",
            "no same-camera evaluation was accepted",
            before_geometry_digest=before["geometry_digest"],
            after_geometry_digest=current["geometry_digest"],
            candidate_geometry=current, repair_transcript=transcript)
    final_evaluation = accepted_evaluations[-1]
    scenarios = _scenario_results(current, request.get("scenarios"), config)
    physical = _physical_cross(before, current, scenarios)
    proof = _proof_cross(
        candidate_id, accepted_evaluations[0], final_evaluation)
    required_scenarios_pass = all(
        not row.get("required_gate") or row.get("verdict") == ANSWER
        for row in scenarios)
    if not required_scenarios_pass:
        terminal_code = "HUMAN_REVIEW_REQUIRED_SCENARIO_FAILED"
        terminal_kind = HUMAN_REVIEW
    if proof.get("verdict") != ANSWER:
        terminal_code = "HUMAN_REVIEW_PROOF_CROSS_NOT_PASSED"
        terminal_kind = HUMAN_REVIEW

    approval = _verify_approval(
        _approval_for(request, candidate), candidate_id, candidate_digest,
        str(current["geometry_digest"]))
    pattern_handoff = None
    if final_evaluation["convergence"]["status"] == "CONVERGED":
        if approval.get("verdict") == ANSWER and required_scenarios_pass \
                and proof.get("verdict") == ANSWER:
            source = _pattern_source(candidate)
            if source is None:
                terminal_code = "UNKNOWN_PATTERN_HANDOFF_REQUIRED"
                terminal_kind = UNKNOWN
            else:
                checked = _validate_pattern_source(candidate, source, config)
                if checked.get("verdict") != ANSWER:
                    terminal_code = str(checked.get(
                        "verdict", "UNKNOWN_PATTERN_HANDOFF_GATE"))
                    terminal_kind = UNKNOWN
                else:
                    pattern_handoff = _make_pattern_handoff(
                        candidate, checked["source"], approval,
                        final_evaluation, str(current["geometry_digest"]),
                        checked.get("pattern_repair"))
                    terminal_code = ANSWER
                    terminal_kind = ANSWER
        elif approval.get("verdict") != ANSWER:
            terminal_code = str(approval.get(
                "verdict", "HUMAN_REVIEW_REQUIRED"))
            terminal_kind = HUMAN_REVIEW

    result = {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_digest": candidate.get("candidate_digest"),
        "verdict": terminal_code,
        "state": PROPOSED if terminal_kind in {ANSWER, HUMAN_REVIEW} else UNKNOWN,
        "stop": None if terminal_kind == ANSWER else {
            "kind": terminal_kind, "code": terminal_code,
            "why": (
                "a candidate repair did not improve every independent "
                "front axis and was rolled back"
                if non_improvement_stop is not None else
                "visible-front geometry needs a human decision"
                if terminal_kind == HUMAN_REVIEW else
                "a deterministic handoff prerequisite is unknown"),
        },
        "rounds": len(transcript),
        "max_rounds": config.max_rounds,
        "repair_transcript": transcript,
        "before_geometry_digest": before["geometry_digest"],
        "after_geometry_digest": current["geometry_digest"],
        "before_shape_digest": before["shape_digest"],
        "after_shape_digest": current["shape_digest"],
        "candidate_geometry": current,
        "rear_hypothesis": rear_hypothesis,
        "rear_axis_constraints": rear_axis_constraints,
        "comparison_contract": _comparison_contract(
            final_evaluation, rear_hypothesis),
        "non_improvement_stop": non_improvement_stop,
        "initial_evaluation_digest": accepted_evaluations[0].get(
            "evaluation_digest"),
        "final_evaluation": final_evaluation,
        "evidence_cross": _evidence_cross(final_evaluation),
        "physical_cross": physical,
        "proof_cross": proof,
        "scenario_results": scenarios,
        "human_approval_gate": approval,
        "pattern_handoff": pattern_handoff,
        "authority": {"front": PROPOSED, "rear": PROPOSED,
                      "material": "UNKNOWN"},
        "rear_observed": False,
        "material_measured": False,
        "fact_promotions": [],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["digest"] = stable_digest(result)
    return result


def run(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run every candidate independently and preserve all typed stops."""
    if not isinstance(request, Mapping) or request.get("schema") != REQUEST_SCHEMA:
        result = {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_CANDIDATE_3D_REPAIR_REQUEST",
            "state": UNKNOWN,
            "why": "schema must be exactly %s" % REQUEST_SCHEMA,
            "candidates": [], "pattern_handoffs": [],
            "fact_promotions": [],
        }
        result["digest"] = stable_digest(result)
        return result
    target = request.get("target_front", request.get(
        "target", request.get("observation")))
    candidates = request.get("candidates")
    if (not isinstance(target, Mapping) or not _sequence(candidates)
            or not candidates or any(not isinstance(row, Mapping)
                                      for row in candidates)):
        result = {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_TARGET_OR_CANDIDATES_REQUIRED",
            "state": UNKNOWN,
            "why": "target_front and one or more candidate objects are required",
            "candidates": [], "pattern_handoffs": [],
            "fact_promotions": [],
        }
        result["digest"] = stable_digest(result)
        return result
    try:
        config = _config(request.get("config"))
        projection_config = _projection_config(
            request.get("projection_config"), config)
        # Validate the target through the same decoder used by the comparator.
        decode_mask(target.get("silhouette_mask", target.get("silhouette")))
        if _camera_digest(target) is None:
            raise ValueError("target requires camera or camera_digest")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        result = {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_CANDIDATE_3D_REPAIR_INPUT",
            "state": UNKNOWN, "why": str(exc), "candidates": [],
            "pattern_handoffs": [], "fact_promotions": [],
        }
        result["digest"] = stable_digest(result)
        return result

    ordered = sorted((copy.deepcopy(dict(row)) for row in candidates),
                     key=lambda row: (str(row.get("candidate_id", "")),
                                      stable_digest(row)))
    ids = [str(row.get("candidate_id", "")).strip() for row in ordered]
    duplicate_ids = {value for value in ids if value and ids.count(value) > 1}
    built: Dict[str, Dict[str, Any]] = {}
    early: Dict[str, Dict[str, Any]] = {}
    for row in ordered:
        candidate_id = str(row.get("candidate_id", "")).strip()
        if not candidate_id:
            key = "missing:%s" % stable_digest(row)[:12]
            early[key] = _candidate_stop(
                "", "UNKNOWN_CANDIDATE_ID_REQUIRED",
                "every candidate requires a stable candidate_id")
            continue
        if candidate_id in duplicate_ids:
            early[candidate_id] = _candidate_stop(
                candidate_id, "UNKNOWN_DUPLICATE_CANDIDATE_ID",
                "candidate ids must be unique")
            continue
        geometry_result = build_candidate_geometry(row)
        if geometry_result.get("verdict") != ANSWER:
            early[candidate_id] = geometry_result
        else:
            built[candidate_id] = geometry_result["geometry"]

    structural_ids = []
    for row in ordered:
        candidate_id = str(row.get("candidate_id", "")).strip()
        domain = str(row.get("domain", "STRUCTURE")).upper()
        if candidate_id in built and "MATERIAL" not in domain:
            structural_ids.append(candidate_id)
    use_source_front_contract = bool(structural_ids) and all(
        built[candidate_id].get("source_front_digest")
        for candidate_id in structural_ids)
    front_contract_method = (
        "SOURCE_FRONT_DIGEST_CONTRACT" if use_source_front_contract
        else "COMPUTED_FRONT_XY_TOPOLOGY_CONTRACT")
    front_contract_groups: Dict[str, List[str]] = {}
    for candidate_id in structural_ids:
        digest = (built[candidate_id].get("source_front_digest")
                  if use_source_front_contract else built[candidate_id].get(
                      "computed_front_contract_digest"))
        front_contract_groups.setdefault(str(digest), []).append(candidate_id)
    front_mismatch = len(front_contract_groups) > 1
    if front_mismatch:
        groups = [sorted(group) for group in front_contract_groups.values()]
        for candidate_id in list(structural_ids):
            early[candidate_id] = _candidate_stop(
                candidate_id, "UNKNOWN_CANDIDATE_FRONT_NOT_PRESERVED",
                "rear alternatives changed the shared visible-front contract",
                front_contract_method=front_contract_method,
                front_contract_candidate_groups=groups,
                before_geometry_digest=built[candidate_id]["geometry_digest"],
                after_geometry_digest=built[candidate_id]["geometry_digest"])
            built.pop(candidate_id, None)
        structural_ids = []
    by_shape: Dict[str, List[str]] = {}
    for candidate_id in structural_ids:
        by_shape.setdefault(built[candidate_id]["shape_digest"], []).append(candidate_id)
    duplicate_geometry = {
        candidate_id: sorted(group)
        for group in by_shape.values() if len(group) > 1
        for candidate_id in group
    }
    for candidate_id, group in duplicate_geometry.items():
        early[candidate_id] = _candidate_stop(
            candidate_id, "UNKNOWN_CANDIDATE_GEOMETRY_NOT_DISTINCT",
            "structural/rear candidates collapsed to identical geometry",
            duplicate_geometry_candidate_ids=group,
            before_geometry_digest=built[candidate_id]["geometry_digest"],
            after_geometry_digest=built[candidate_id]["geometry_digest"])
        built.pop(candidate_id, None)

    results = []
    for row in ordered:
        candidate_id = str(row.get("candidate_id", "")).strip()
        if candidate_id in early:
            results.append(early.pop(candidate_id))
        elif candidate_id in built:
            results.append(_run_candidate(
                request, row, target, built[candidate_id], config,
                projection_config))
    results.extend(early[key] for key in sorted(early))
    if any(str(row.get("verdict", "")).startswith("UNKNOWN_")
           or row.get("state") == UNKNOWN for row in results):
        verdict, state = "UNKNOWN_CANDIDATE_3D_REPAIR_STOPPED", UNKNOWN
    elif any(row.get("stop", {}).get("kind") == HUMAN_REVIEW
             for row in results if isinstance(row.get("stop"), Mapping)):
        verdict, state = "HUMAN_REVIEW_REQUIRED", PROPOSED
    elif results and all(row.get("verdict") == ANSWER for row in results):
        verdict, state = ANSWER, PROPOSED
    else:
        verdict, state = "UNKNOWN_CANDIDATE_3D_REPAIR_STOPPED", UNKNOWN
    distinct_rows = [{"shape_digest": digest,
                      "candidate_ids": sorted(group)}
                     for digest, group in sorted(by_shape.items())]
    result = {
        "schema": SCHEMA,
        "verdict": verdict,
        "state": state,
        "candidate_count": len(results),
        "candidates": results,
        "distinct_geometry_check": {
            "verdict": (ANSWER if not duplicate_geometry else
                        "UNKNOWN_CANDIDATE_GEOMETRY_NOT_DISTINCT"),
            "groups": distinct_rows,
            "generic_fallback_used": False,
        },
        "front_preservation_check": {
            "verdict": ("UNKNOWN_CANDIDATE_FRONT_NOT_PRESERVED"
                        if front_mismatch else ANSWER),
            "method": front_contract_method,
            "groups": [
                {"front_contract_digest": digest,
                 "candidate_ids": sorted(group)}
                for digest, group in sorted(front_contract_groups.items())
            ],
            "rear_alternatives_may_not_mutate_visible_front": True,
        },
        "pattern_handoffs": [copy.deepcopy(row["pattern_handoff"])
                             for row in results
                             if isinstance(row.get("pattern_handoff"), Mapping)],
        "human_choice": {
            "required": any(row.get("stop", {}).get("kind") == HUMAN_REVIEW
                            for row in results
                            if isinstance(row.get("stop"), Mapping)),
            "candidate_ids": sorted(row.get("candidate_id") for row in results
                                    if row.get("candidate_id")),
            "selected_candidate_id": None,
        },
        "authority": {"front": PROPOSED, "rear": PROPOSED,
                      "material": "UNKNOWN"},
        "fact_promotions": [],
        "no_aggregate_similarity_score": True,
        "bounded_rounds": config.max_rounds,
        "config": config.as_dict(),
        "projection_config": projection_config,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    result["input_digest"] = stable_digest({
        "target": target, "candidates": ordered,
        "config": config.as_dict(), "projection_config": projection_config,
        "scenarios": request.get("scenarios", []),
    })
    result["digest"] = stable_digest(result)
    return result


execute = run
repair_candidates = run


__all__ = [
    "REQUEST_SCHEMA", "SCHEMA", "CANDIDATE_SCHEMA",
    "EVIDENCE_CROSS_SCHEMA", "PHYSICAL_CROSS_SCHEMA",
    "PATTERN_HANDOFF_SCHEMA", "REAR_HYPOTHESIS_SCHEMA",
    "REAR_HYPOTHESIS_AXES", "RepairLoopConfig", "stable_digest",
    "build_candidate_geometry", "run", "execute", "repair_candidates",
]
