# -*- coding: utf-8 -*-
"""Deterministic, candidate-specific 3D previews for garment structures.

The generated triangles are deliberately simple procedural visualisations.
They are useful for comparing proposed structures, but they do not establish
pattern correctness, fit, seam topology, material behaviour, or
manufacturability.  The boundary fails closed when a structure contains a
primitive for which this module has no preview geometry.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple

from . import garment_structure
from . import structure_to_pattern as _pattern_compiler


ANSWER = "ANSWER"
PROPOSED = "PROPOSED"
PREVIEW_SCHEMA = "garment.structure.preview.v1"
UNSUPPORTED = "UNKNOWN_STRUCTURE_PREVIEW_UNSUPPORTED_PRIMITIVE"
BAD_REQUEST = "UNKNOWN_STRUCTURE_PREVIEW_BAD_REQUEST"
BAD_GEOMETRY = "UNKNOWN_STRUCTURE_PREVIEW_GEOMETRY"
OPERATION_MISMATCH = "UNKNOWN_STRUCTURE_PREVIEW_OPERATION_MISMATCH"
SPLIT_RESOLUTION = "UNKNOWN_STRUCTURE_PREVIEW_SPLIT_RESOLUTION"
CUTOUT_PROJECTION = "UNKNOWN_STRUCTURE_PREVIEW_CUTOUT_PROJECTION"
CUTOUT_BOUNDARY = "UNKNOWN_STRUCTURE_PREVIEW_CUTOUT_BOUNDARY"
CUTOUT_EMPTY = "UNKNOWN_STRUCTURE_PREVIEW_CUTOUT_REMOVES_ALL_FACES"
SLEEVE_ATTACHMENT = "UNKNOWN_STRUCTURE_PREVIEW_SLEEVE_ATTACHMENT"
SLEEVE_SIDE_MISMATCH = "UNKNOWN_STRUCTURE_PREVIEW_SLEEVE_SIDE_MISMATCH"

_SUPPORTED = frozenset({
    "BODY_SHELL", "TUBE", "FRUSTUM", "FLARE", "GORE", "SLEEVE",
    "BAND", "OVERLAY", "GUSSET", "YOKE", "COLLAR", "HOOD",
    "OPENING", "DRAPE_ANCHOR",
})
_EPS = 1.0e-10
_GEOMETRY_OPERATION_KINDS = frozenset({
    "SPLIT", "MIRROR", "ASYMMETRY", "CUTOUT",
})

Vec3 = Tuple[float, float, float]
Triangle = Tuple[int, int, int]


class _PreviewRefusal(Exception):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unknown(code: str, why: str, *, candidate_id: Optional[str],
             **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "schema": PREVIEW_SCHEMA,
        "state": PROPOSED,
        "candidate_id": candidate_id,
        "why": why,
        "how_to_close": "provide a valid garment.structure.v1 using supported preview primitives",
        "claims": {
            "preview_only": True,
            "manufacturing_ready": False,
            "sewable_pattern": False,
            "fit_validated": False,
        },
        **detail,
    }


def _position(node: Mapping[str, Any]) -> Vec3:
    dimensions = node["dimensions"]
    return (float(dimensions.get("x_cm", 0.0)),
            float(dimensions.get("y_cm", 0.0)),
            float(dimensions.get("z_cm", 0.0)))


def _ring_surface(levels: Sequence[Tuple[float, float]], *,
                  segments: int, center: Vec3, depth_ratio: float = 1.0,
                  radial_offset: float = 0.0) -> Tuple[List[Vec3], List[Triangle]]:
    """Create an open, triangulated surface from ``(axis_y, radius)`` rings."""
    vertices: List[Vec3] = []
    cx, cy, cz = center
    for axis_y, radius in levels:
        outer_radius = radius + radial_offset
        for segment in range(segments):
            angle = 2.0 * math.pi * segment / segments
            vertices.append((cx + outer_radius * math.cos(angle),
                             cy + axis_y,
                             cz + outer_radius * depth_ratio * math.sin(angle)))
    faces: List[Triangle] = []
    for level in range(len(levels) - 1):
        first = level * segments
        second = (level + 1) * segments
        for segment in range(segments):
            following = (segment + 1) % segments
            a, b = first + segment, first + following
            c, d = second + following, second + segment
            faces.extend(((a, d, c), (a, c, b)))
    return vertices, faces


def _trapezoid(*, length: float, top_width: float, bottom_width: float,
               center: Vec3, surface_z: float) -> Tuple[List[Vec3], List[Triangle]]:
    cx, cy, cz = center
    vertices = [
        (cx - top_width / 2.0, cy, cz + surface_z),
        (cx + top_width / 2.0, cy, cz + surface_z),
        (cx + bottom_width / 2.0, cy - length, cz + surface_z),
        (cx - bottom_width / 2.0, cy - length, cz + surface_z),
    ]
    return vertices, [(0, 2, 1), (0, 3, 2)]


def _overlay(*, height: float, width: float, center: Vec3,
             surface_z: float) -> Tuple[List[Vec3], List[Triangle]]:
    """Create a small curved 3x3 patch so an overlay is visible as a surface."""
    cx, cy, cz = center
    vertices: List[Vec3] = []
    for row in range(3):
        y = cy - height * row / 2.0
        for column in range(3):
            x_fraction = column / 2.0
            x = cx + width * (x_fraction - 0.5)
            fold = width * 0.035 * math.sin(math.pi * x_fraction)
            vertices.append((x, y, cz + surface_z + fold))
    faces: List[Triangle] = []
    for row in range(2):
        for column in range(2):
            a = row * 3 + column
            b, c, d = a + 1, a + 4, a + 3
            faces.extend(((a, d, c), (a, c, b)))
    return vertices, faces


def _body_radius(nodes: Sequence[Mapping[str, Any]]) -> float:
    circumferences = []
    for node in nodes:
        dimensions = node["dimensions"]
        if node["kind"] == "BODY_SHELL":
            circumferences.append(float(dimensions["circumference_cm"]))
    return (max(circumferences) / (2.0 * math.pi)
            if circumferences else 15.0)


def _body_height(nodes: Sequence[Mapping[str, Any]]) -> float:
    heights = [float(node["dimensions"]["height_cm"])
               for node in nodes if node["kind"] == "BODY_SHELL"]
    return max(heights) if heights else 60.0


def _sleeve_sides(node: Mapping[str, Any]) -> Tuple[str, ...]:
    """Resolve explicit sleeve multiplicity without guessing a missing side."""
    attributes = node.get("attributes", {})
    if not isinstance(attributes, Mapping):
        raise _PreviewRefusal(
            SLEEVE_SIDE_MISMATCH,
            f"{node.get('node_id')} attributes must be an object",
            node_id=node.get("node_id"))
    raw_side = attributes.get("side")
    side = (str(raw_side).strip().lower()
            if isinstance(raw_side, str) else None)
    if raw_side is not None and (not side or side not in {
            "left", "right", "bilateral"}):
        raise _PreviewRefusal(
            SLEEVE_SIDE_MISMATCH,
            f"{node.get('node_id')} has no supported explicit sleeve side",
            node_id=node.get("node_id"), side=copy.deepcopy(raw_side))

    bilateral = attributes.get("bilateral")
    if bilateral is not None and not isinstance(bilateral, bool):
        raise _PreviewRefusal(
            SLEEVE_SIDE_MISMATCH,
            f"{node.get('node_id')}.bilateral must be boolean",
            node_id=node.get("node_id"), bilateral=copy.deepcopy(bilateral))
    if bilateral is True and side in {"left", "right"}:
        raise _PreviewRefusal(
            SLEEVE_SIDE_MISMATCH,
            f"{node.get('node_id')} cannot be bilateral and unilateral",
            node_id=node.get("node_id"), side=side, bilateral=True)
    if bilateral is False and side == "bilateral":
        raise _PreviewRefusal(
            SLEEVE_SIDE_MISMATCH,
            f"{node.get('node_id')} side and bilateral flag disagree",
            node_id=node.get("node_id"), side=side, bilateral=False)

    quantity = attributes.get("quantity")
    if (quantity is not None
            and (isinstance(quantity, bool) or not isinstance(quantity, int)
                 or quantity not in (1, 2))):
        raise _PreviewRefusal(
            SLEEVE_SIDE_MISMATCH,
            f"{node.get('node_id')}.quantity must be 1 or 2",
            node_id=node.get("node_id"), quantity=copy.deepcopy(quantity))

    explicit_bilateral = side == "bilateral" or bilateral is True
    if explicit_bilateral:
        # ``bilateral=True`` without quantity is retained for the original
        # garment.structure.v1 preview fixtures.  The Parts IR form is stricter:
        # side=bilateral must carry quantity=2.
        if side == "bilateral" and quantity != 2:
            raise _PreviewRefusal(
                SLEEVE_SIDE_MISMATCH,
                f"{node.get('node_id')} side=bilateral requires quantity=2",
                node_id=node.get("node_id"), side=side, quantity=quantity)
        if quantity not in (None, 2):
            raise _PreviewRefusal(
                SLEEVE_SIDE_MISMATCH,
                f"{node.get('node_id')} bilateral sleeve requires quantity=2",
                node_id=node.get("node_id"), quantity=quantity)
        return ("left", "right")

    if quantity == 2:
        raise _PreviewRefusal(
            SLEEVE_SIDE_MISMATCH,
            f"{node.get('node_id')} quantity=2 needs side=bilateral",
            node_id=node.get("node_id"), side=side, quantity=quantity)
    return (side or "right",)


def _attached_parent_id(node: Mapping[str, Any]) -> Optional[str]:
    attributes = node.get("attributes", {})
    value = attributes.get("attached_to") if isinstance(attributes, Mapping) else None
    if value is None:
        return None
    if isinstance(value, str):
        parents = [value.strip()] if value.strip() else []
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parents = [str(item).strip() for item in value
                   if isinstance(item, str) and item.strip()]
        if len(parents) != len(value):
            parents = []
    else:
        parents = []
    if len(parents) != 1:
        raise _PreviewRefusal(
            SLEEVE_ATTACHMENT,
            f"{node.get('node_id')} needs exactly one resolvable attached_to parent",
            node_id=node.get("node_id"), attached_to=copy.deepcopy(value))
    return parents[0]


def _sleeve_layouts(
        canonical: Mapping[str, Any], *, layer_spacing_cm: float
        ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Resolve proposal-only sleeve axes and side-specific relation lineage."""
    nodes = list(canonical["nodes"])
    node_table = {str(node["node_id"]): node for node in nodes}
    sleeve_ids = {node_id for node_id, node in node_table.items()
                  if node["kind"] == "SLEEVE"}
    sides = {node_id: _sleeve_sides(node_table[node_id])
             for node_id in sleeve_ids}
    parents: Dict[str, Optional[str]] = {}
    for node_id in sleeve_ids:
        parent_id = _attached_parent_id(node_table[node_id])
        if parent_id is not None and parent_id not in node_table:
            raise _PreviewRefusal(
                SLEEVE_ATTACHMENT,
                f"{node_id} references an unknown attached_to parent",
                node_id=node_id, attached_to=parent_id)
        parents[node_id] = parent_id

    relations: Dict[str, Mapping[str, Any]] = {}
    for operation in canonical.get("operations", []):
        if operation["kind"] not in {"JOIN", "GATHER", "LAYER"}:
            continue
        target = operation.get("target")
        if not isinstance(target, Mapping):
            continue
        source_id = str(operation["source"]["node_id"])
        target_id = str(target["node_id"])
        if source_id not in sleeve_ids or target_id not in sleeve_ids:
            continue
        if operation["kind"] == "GATHER":
            parameters = operation.get("parameters", {})
            parameters = parameters if isinstance(parameters, Mapping) else {}
            role = str(parameters.get(
                "construction_role", operation.get("construction_role", ""),
            )).strip().upper()
            if role != "GATHER_SLEEVE_SEGMENTS":
                raise _PreviewRefusal(
                    SLEEVE_ATTACHMENT,
                    f"{operation['operation_id']} sleeve GATHER needs typed GATHER_SLEEVE_SEGMENTS",
                    operation_id=operation["operation_id"],
                    construction_role=role,
                    required_construction_role="GATHER_SLEEVE_SEGMENTS")
        if source_id in relations:
            raise _PreviewRefusal(
                SLEEVE_ATTACHMENT,
                f"{source_id} has multiple sleeve-parent relations",
                node_id=source_id,
                operation_ids=[relations[source_id]["operation_id"],
                               operation["operation_id"]])
        if parents[source_id] != target_id:
            raise _PreviewRefusal(
                SLEEVE_ATTACHMENT,
                f"{operation['operation_id']} disagrees with explicit attached_to",
                node_id=source_id, attached_to=parents[source_id],
                operation_target=target_id)
        relations[source_id] = operation

    body_radius = _body_radius(nodes)
    body_height = _body_height(nodes)
    layouts: Dict[str, List[Dict[str, Any]]] = {}
    resolving: List[str] = []

    def resolve(node_id: str) -> List[Dict[str, Any]]:
        if node_id in layouts:
            return layouts[node_id]
        if node_id in resolving:
            raise _PreviewRefusal(
                SLEEVE_ATTACHMENT,
                "sleeve attachment graph contains a cycle",
                cycle=resolving[resolving.index(node_id):] + [node_id])
        resolving.append(node_id)
        node = node_table[node_id]
        dimensions = node["dimensions"]
        center = _position(node)
        layer = int(node.get("layer", 0))
        length = float(dimensions["length_cm"])
        raw_upper = float(dimensions["upper_circumference_cm"]) / (2.0 * math.pi)
        raw_cuff = float(dimensions["cuff_circumference_cm"]) / (2.0 * math.pi)
        parent_id = parents[node_id]
        relation = relations.get(node_id)

        if parent_id in sleeve_ids and relation is None:
            raise _PreviewRefusal(
                SLEEVE_ATTACHMENT,
                f"{node_id} names a sleeve parent but has no exact JOIN, GATHER, or LAYER",
                node_id=node_id, attached_to=parent_id)
        if relation is not None and parent_id not in sleeve_ids:
            raise _PreviewRefusal(
                SLEEVE_ATTACHMENT,
                f"{node_id} sleeve relation has no resolvable sleeve parent",
                node_id=node_id, attached_to=parent_id,
                operation_id=relation["operation_id"])

        resolved: List[Dict[str, Any]] = []
        if parent_id not in sleeve_ids:
            radial_offset = layer * layer_spacing_cm
            for index, side in enumerate(sides[node_id]):
                sign = -1.0 if side == "left" else 1.0
                resolved.append({
                    "instance_id": f"{node_id}:{side}",
                    "source_node_id": node_id,
                    "side": side,
                    "quantity_index": index,
                    "axis_origin_cm": [
                        center[0] + sign * (body_radius + raw_upper * 0.7),
                        center[1] + body_height * 0.72,
                        center[2],
                    ],
                    "length_cm": length,
                    "upper_radius_cm": raw_upper + radial_offset,
                    "cuff_radius_cm": raw_cuff + radial_offset,
                    "attached_to_node_id": parent_id,
                    "parent_instance_id": None,
                    "relation_operation_id": None,
                    "relation_kind": ("BODY_ATTACHMENT" if parent_id else None),
                    "radial_clearance_cm": 0.0,
                    "state": PROPOSED,
                })
        else:
            parent_instances = {row["side"]: row
                                for row in resolve(parent_id)}
            child_sides = sides[node_id]
            missing_sides = [side for side in child_sides
                             if side not in parent_instances]
            if missing_sides:
                raise _PreviewRefusal(
                    SLEEVE_SIDE_MISMATCH,
                    f"{node_id} has no same-side parent sleeve instance",
                    node_id=node_id, attached_to=parent_id,
                    child_sides=list(child_sides),
                    parent_sides=sorted(parent_instances),
                    missing_sides=missing_sides)
            assert relation is not None
            relation_kind = str(relation["kind"])
            parent_node = node_table[parent_id]
            parent_layer = int(parent_node.get("layer", 0))
            if relation_kind == "JOIN":
                difference = abs(
                    float(dimensions["upper_circumference_cm"])
                    - float(parent_node["dimensions"]["cuff_circumference_cm"]))
                if difference > 0.05:
                    raise _PreviewRefusal(
                        SLEEVE_ATTACHMENT,
                        f"{relation['operation_id']} dimensions do not meet at the cuff",
                        operation_id=relation["operation_id"],
                        difference_cm=difference)
            elif relation_kind == "LAYER" and layer <= parent_layer:
                raise _PreviewRefusal(
                    SLEEVE_ATTACHMENT,
                    f"{relation['operation_id']} outer sleeve must use a higher layer",
                    operation_id=relation["operation_id"],
                    source_layer=layer, target_layer=parent_layer)

            for index, side in enumerate(child_sides):
                parent = parent_instances[side]
                parent_axis = [float(value)
                               for value in parent["axis_origin_cm"]]
                gather_lineage: Optional[Dict[str, Any]] = None
                if relation_kind in {"JOIN", "GATHER"}:
                    axis_origin = [parent_axis[0],
                                   parent_axis[1] - float(parent["length_cm"]),
                                   parent_axis[2]]
                    upper_radius = float(parent["cuff_radius_cm"])
                    cuff_radius = raw_cuff + layer * layer_spacing_cm
                    clearance = 0.0
                    if relation_kind == "GATHER":
                        parameters = relation.get("parameters", {})
                        parameters = (parameters
                                      if isinstance(parameters, Mapping) else {})
                        source_cut = float(
                            dimensions["upper_circumference_cm"])
                        target_finished = float(
                            parent_node["dimensions"]["cuff_circumference_cm"])
                        gather_lineage = {
                            "construction_role": "GATHER_SLEEVE_SEGMENTS",
                            "source_cut_length_cm": source_cut,
                            "target_finished_length_cm": target_finished,
                            "source_fullness_cm": source_cut - target_finished,
                            "ratio": float(parameters["ratio"]),
                            "distribution": str(parameters.get(
                                "distribution", "uniform")),
                            "mesh_representation": "PARENT_CUFF_ENVELOPE_ONLY",
                            "physical_gathered_folds_resolved": False,
                            "state": PROPOSED,
                        }
                else:
                    axis_origin = parent_axis
                    parent_fraction = min(
                        1.0, length / max(float(parent["length_cm"]), _EPS))
                    parent_at_end = (
                        float(parent["upper_radius_cm"])
                        + (float(parent["cuff_radius_cm"])
                           - float(parent["upper_radius_cm"])) * parent_fraction)
                    minimum_clearance = max(
                        layer_spacing_cm,
                        (layer - parent_layer) * layer_spacing_cm)
                    upper_radius = max(
                        raw_upper + layer * layer_spacing_cm,
                        float(parent["upper_radius_cm"]) + minimum_clearance)
                    cuff_radius = max(
                        raw_cuff + layer * layer_spacing_cm,
                        parent_at_end + minimum_clearance)
                    clearance = min(
                        upper_radius - float(parent["upper_radius_cm"]),
                        cuff_radius - parent_at_end)
                resolved.append({
                    "instance_id": f"{node_id}:{side}",
                    "source_node_id": node_id,
                    "side": side,
                    "quantity_index": index,
                    "axis_origin_cm": axis_origin,
                    "length_cm": length,
                    "upper_radius_cm": upper_radius,
                    "cuff_radius_cm": cuff_radius,
                    "attached_to_node_id": parent_id,
                    "parent_instance_id": parent["instance_id"],
                    "relation_operation_id": relation["operation_id"],
                    "relation_kind": relation_kind,
                    **({"gather_lineage": copy.deepcopy(gather_lineage)}
                       if gather_lineage is not None else {}),
                    "radial_clearance_cm": clearance,
                    "state": PROPOSED,
                })
        resolving.pop()
        layouts[node_id] = resolved
        return resolved

    for sleeve_id in sorted(sleeve_ids):
        resolve(sleeve_id)

    coverage: List[Dict[str, Any]] = []
    for child_id, relation in sorted(
            relations.items(), key=lambda item: str(item[1]["operation_id"])):
        parent_id = parents[child_id]
        assert parent_id is not None
        for instance in layouts[child_id]:
            coverage.append({
                "operation_id": relation["operation_id"],
                "kind": relation["kind"],
                "state": PROPOSED,
                "source_node_id": child_id,
                "target_node_id": parent_id,
                "attached_to_node_id": parent_id,
                "side": instance["side"],
                "source_instance_id": instance["instance_id"],
                "target_instance_id": instance["parent_instance_id"],
                "source_boundary": ("upper" if relation["kind"] in {"JOIN", "GATHER"}
                                    else "outer_surface"),
                "target_boundary": ("cuff" if relation["kind"] in {"JOIN", "GATHER"}
                                    else "inner_surface"),
                **({"gather_lineage": copy.deepcopy(
                    instance["gather_lineage"])}
                   if relation["kind"] == "GATHER" else {}),
                "radial_clearance_cm": instance["radial_clearance_cm"],
                "authority": PROPOSED,
                "preview_only": True,
            })
    return layouts, coverage


def _node_geometry(node: Mapping[str, Any], *, nodes: Sequence[Mapping[str, Any]],
                   segments: int, layer_spacing_cm: float,
                   sleeve_layouts: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None
                   ) -> Tuple[List[Vec3], List[Triangle], List[str]]:
    kind = str(node["kind"])
    dimensions = node["dimensions"]
    attributes = node.get("attributes", {})
    layer = int(node.get("layer", 0))
    center = _position(node)
    radial_offset = layer * layer_spacing_cm
    body_radius = _body_radius(nodes)
    body_height = _body_height(nodes)
    consumed_attributes: List[str] = []

    if kind == "BODY_SHELL":
        height = float(dimensions["height_cm"])
        radius = float(dimensions["circumference_cm"]) / (2.0 * math.pi)
        bottom = float(dimensions.get(
            "bottom_circumference_cm", dimensions["circumference_cm"])) / (2.0 * math.pi)
        top = float(dimensions.get(
            "top_circumference_cm", dimensions["circumference_cm"] * 0.72)) / (2.0 * math.pi)
        return (*_ring_surface(((0.0, bottom),
                                (height * 0.25, radius),
                                (height * 0.62, radius * 0.92),
                                (height, top)),
                               segments=segments, center=center,
                               depth_ratio=0.70, radial_offset=radial_offset),
                consumed_attributes)
    if kind == "TUBE":
        length = float(dimensions["length_cm"])
        radius = float(dimensions["circumference_cm"]) / (2.0 * math.pi)
        return (*_ring_surface(((0.0, radius), (-length, radius)),
                               segments=segments, center=center,
                               radial_offset=radial_offset), consumed_attributes)
    if kind in ("FRUSTUM", "FLARE"):
        height = float(dimensions["height_cm"])
        top = float(dimensions["top_circumference_cm"]) / (2.0 * math.pi)
        bottom = float(dimensions["bottom_circumference_cm"]) / (2.0 * math.pi)
        if kind == "FLARE":
            levels = ((0.0, top), (-height * 0.42, top + (bottom-top) * 0.28),
                      (-height, bottom))
        else:
            levels = ((0.0, top), (-height, bottom))
        return (*_ring_surface(levels, segments=segments, center=center,
                               radial_offset=radial_offset), consumed_attributes)
    if kind == "GORE":
        return (*_trapezoid(length=float(dimensions["length_cm"]),
                            top_width=float(dimensions["top_width_cm"]),
                            bottom_width=float(dimensions["bottom_width_cm"]),
                            center=center,
                            surface_z=body_radius + (layer + 1) * layer_spacing_cm),
                consumed_attributes)
    if kind in ("GUSSET", "YOKE"):
        length_key = "length_cm" if kind == "GUSSET" else "height_cm"
        return (*_overlay(height=float(dimensions[length_key]),
                          width=float(dimensions["width_cm"]), center=center,
                          surface_z=body_radius + (layer + 1) * layer_spacing_cm),
                consumed_attributes)
    if kind == "SLEEVE":
        layouts = (() if sleeve_layouts is None
                   else sleeve_layouts.get(str(node["node_id"]), ()))
        if not layouts:
            raise ValueError(f"{node['node_id']} has no resolved sleeve instances")
        for name in ("bilateral", "side", "quantity", "attached_to"):
            if name in attributes:
                consumed_attributes.append(name)
        all_vertices: List[Vec3] = []
        all_faces: List[Triangle] = []
        for instance in layouts:
            sleeve_center = tuple(float(value)
                                  for value in instance["axis_origin_cm"])
            vertices, faces = _ring_surface(
                                            ((0.0, float(instance["upper_radius_cm"])),
                                             (-float(instance["length_cm"]),
                                              float(instance["cuff_radius_cm"]))),
                                            segments=segments,
                                            center=sleeve_center)
            offset = len(all_vertices)
            all_vertices.extend(vertices)
            all_faces.extend(tuple(index + offset for index in face)
                             for face in faces)
        return all_vertices, all_faces, consumed_attributes
    if kind == "BAND":
        radius = float(dimensions["length_cm"]) / (2.0 * math.pi)
        width = float(dimensions["width_cm"])
        return (*_ring_surface(((0.0, radius), (-width, radius)),
                               segments=segments, center=center,
                               radial_offset=radial_offset), consumed_attributes)
    if kind == "COLLAR":
        radius = float(dimensions["length_cm"]) / (2.0 * math.pi)
        width = float(dimensions["width_cm"])
        collar_center = (center[0], center[1] + body_height, center[2])
        return (*_ring_surface(((0.0, radius), (width, radius * 1.08)),
                               segments=segments, center=collar_center,
                               radial_offset=radial_offset), consumed_attributes)
    if kind == "HOOD":
        height = float(dimensions["height_cm"])
        width = float(dimensions["width_cm"])
        depth = float(dimensions["depth_cm"])
        hood_center = (center[0], center[1] + body_height, center[2])
        return (*_ring_surface(((0.0, width * 0.42),
                                (height * 0.55, width * 0.52),
                                (height, width * 0.28)),
                               segments=segments, center=hood_center,
                               depth_ratio=max(0.25, depth / max(width, _EPS)),
                               radial_offset=radial_offset), consumed_attributes)
    if kind == "OVERLAY":
        return (*_overlay(height=float(dimensions["height_cm"]),
                          width=float(dimensions["width_cm"]), center=center,
                          surface_z=body_radius + (layer + 1) * layer_spacing_cm),
                consumed_attributes)
    if kind == "OPENING":
        return (*_overlay(height=float(dimensions["length_cm"]), width=0.8,
                          center=center,
                          surface_z=body_radius + (layer + 1) * layer_spacing_cm),
                consumed_attributes)
    if kind == "DRAPE_ANCHOR":
        return (*_overlay(height=2.0, width=2.0, center=center,
                          surface_z=body_radius + (layer + 1) * layer_spacing_cm),
                consumed_attributes)
    raise ValueError(f"unsupported primitive {kind}")


def _triangle_area(vertices: Sequence[Vec3], face: Triangle) -> float:
    a, b, c = (vertices[index] for index in face)
    ab = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
    ac = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
    cross = (ab[1]*ac[2]-ab[2]*ac[1],
             ab[2]*ac[0]-ab[0]*ac[2],
             ab[0]*ac[1]-ab[1]*ac[0])
    return 0.5 * math.sqrt(sum(value * value for value in cross))


def _topology(vertices: Sequence[Vec3], faces: Sequence[Triangle]) -> Dict[str, Any]:
    edge_uses: Dict[Tuple[int, int], int] = {}
    degenerate = []
    for face_index, face in enumerate(faces):
        if len(set(face)) != 3 or _triangle_area(vertices, face) <= _EPS:
            degenerate.append(face_index)
        for first, second in ((face[0], face[1]), (face[1], face[2]),
                              (face[2], face[0])):
            edge = tuple(sorted((first, second)))
            edge_uses[edge] = edge_uses.get(edge, 0) + 1
    nonmanifold = [list(edge) for edge, count in sorted(edge_uses.items())
                   if count > 2]
    return {
        "vertex_count": len(vertices),
        "triangle_count": len(faces),
        "boundary_edge_count": sum(count == 1 for count in edge_uses.values()),
        "nonmanifold_edges": nonmanifold,
        "degenerate_face_indices": degenerate,
    }


def _part_face_indices(part: Mapping[str, Any]) -> List[int]:
    explicit = part.get("face_indices")
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        return [int(value) for value in explicit]
    start, stop = part["face_range"]
    return list(range(int(start), int(stop)))


def _find_part(parts: Sequence[Mapping[str, Any]], piece_id: str
               ) -> Optional[Mapping[str, Any]]:
    return next((part for part in parts
                 if str(part.get("piece_id", part.get("node_id"))) == piece_id), None)


def _bbox_projection(vertices: Sequence[Vec3], vertex_indices: Sequence[int],
                     outline: Sequence[Sequence[float]]) -> Dict[int, Tuple[float, float]]:
    """Project one procedural part into its compiler flat-pattern bounds.

    This projection is only an ownership/transform carrier.  It does not claim
    that the procedural preview is an isometric drape of the flat pattern.
    """
    xs = [vertices[index][0] for index in vertex_indices]
    ys = [vertices[index][1] for index in vertex_indices]
    flat_xs = [float(point[0]) for point in outline]
    flat_ys = [float(point[1]) for point in outline]
    if not xs or not ys or not flat_xs or not flat_ys:
        raise ValueError("operation source has no projectable geometry")
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    flat_x_lo, flat_x_hi = min(flat_xs), max(flat_xs)
    flat_y_lo, flat_y_hi = min(flat_ys), max(flat_ys)

    def normalise(value: float, low: float, high: float) -> float:
        return 0.5 if abs(high - low) <= _EPS else (value - low) / (high - low)

    return {
        index: (
            flat_x_lo + normalise(vertices[index][0], x_lo, x_hi)
            * (flat_x_hi - flat_x_lo),
            flat_y_lo + normalise(vertices[index][1], y_lo, y_hi)
            * (flat_y_hi - flat_y_lo),
        )
        for index in vertex_indices
    }


def _compiler_failure(result: Mapping[str, Any], *, candidate_id: str,
                      structure_digest: str) -> Dict[str, Any]:
    failure = _unknown(
        str(result.get("verdict", OPERATION_MISMATCH)),
        str(result.get("why", "2D operation compiler refused the structure")),
        candidate_id=candidate_id,
        structure_digest=structure_digest,
        pattern_operation_refusal=True,
    )
    for name, value in result.items():
        if name not in {"verdict", "why", "how_to_close", "schema", "state",
                        "candidate_id", "structure_digest", "claims"}:
            failure[name] = copy.deepcopy(value)
    if result.get("how_to_close"):
        failure["how_to_close"] = str(result["how_to_close"])
    return failure


def _source_outline(compiled_pieces: Mapping[str, Mapping[str, Any]],
                    record: Mapping[str, Any]) -> List[List[float]]:
    source_id = str(record.get("source_piece_id", record.get("piece_id", "")))
    source = compiled_pieces.get(source_id)
    if source is not None:
        return copy.deepcopy(source["outline"])
    if record["kind"] == "SPLIT":
        child_ids = record["new_piece_ids"]
        points = []
        for side in ("negative", "positive"):
            child = compiled_pieces.get(str(child_ids[side]))
            if child is None:
                raise ValueError("compiled SPLIT child is missing")
            points.extend(copy.deepcopy(child["outline"]))
        return points
    raise ValueError(f"compiled source piece {source_id!r} is missing")


def _split_faces(*, vertices: Sequence[Vec3], faces: Sequence[Triangle],
                 source_part: Mapping[str, Any], source_outline: Sequence[Sequence[float]],
                 line: Sequence[Sequence[float]], negative_id: str,
                 positive_id: str) -> Tuple[Dict[int, str], List[List[int]]]:
    face_indices = _part_face_indices(source_part)
    vertex_indices = sorted({index for face_index in face_indices
                             for index in faces[face_index]})
    projected = _bbox_projection(vertices, vertex_indices, source_outline)
    a = (float(line[0][0]), float(line[0][1]))
    b = (float(line[1][0]), float(line[1][1]))

    def side(point: Tuple[float, float]) -> float:
        return ((b[0] - a[0]) * (point[1] - a[1])
                - (b[1] - a[1]) * (point[0] - a[0]))

    ownership: Dict[int, str] = {}
    edge_faces: Dict[Tuple[int, int], List[int]] = {}
    for face_index in face_indices:
        face = faces[face_index]
        centroid = (
            sum(projected[index][0] for index in face) / 3.0,
            sum(projected[index][1] for index in face) / 3.0,
        )
        ownership[face_index] = negative_id if side(centroid) <= 0.0 else positive_id
        for first, second in ((face[0], face[1]), (face[1], face[2]),
                              (face[2], face[0])):
            edge_faces.setdefault(tuple(sorted((first, second))), []).append(face_index)
    boundary = [list(edge) for edge, incident in sorted(edge_faces.items())
                if len(incident) == 2
                and ownership[incident[0]] != ownership[incident[1]]]
    return ownership, boundary


def _append_derived_part(*, vertices: List[Vec3], faces: List[Triangle],
                         vertex_layers: List[int], face_layers: List[int],
                         face_node_ids: List[str], face_piece_ids: List[str],
                         parts: List[Dict[str, Any]], source_part: Mapping[str, Any],
                         new_piece_id: str, operation: Mapping[str, Any],
                         transform: Any) -> Dict[str, Any]:
    source_faces = _part_face_indices(source_part)
    source_vertices = sorted({index for face_index in source_faces
                              for index in faces[face_index]})
    first_vertex, first_face = len(vertices), len(faces)
    remap: Dict[int, int] = {}
    for old_index in source_vertices:
        remap[old_index] = len(vertices)
        vertices.append(transform(old_index, vertices[old_index]))
        vertex_layers.append(vertex_layers[old_index])
    source_node_id = str(source_part.get("source_node_id", source_part["node_id"]))
    for old_face_index in source_faces:
        faces.append(tuple(remap[index] for index in faces[old_face_index]))
        face_layers.append(face_layers[old_face_index])
        face_node_ids.append(source_node_id)
        face_piece_ids.append(new_piece_id)
    derived = {
        "node_id": new_piece_id,
        "source_node_id": source_node_id,
        "piece_id": new_piece_id,
        "kind": source_part["kind"],
        "layer": source_part["layer"],
        "vertex_range": [first_vertex, len(vertices)],
        "face_range": [first_face, len(faces)],
        "face_indices": list(range(first_face, len(faces))),
        "consumed_attributes": copy.deepcopy(source_part.get("consumed_attributes", [])),
        "unconsumed_attributes": copy.deepcopy(source_part.get("unconsumed_attributes", [])),
        "derived": True,
        "operation_id": operation["operation_id"],
        "operation_kind": operation["kind"],
        "state": PROPOSED,
    }
    parts.append(derived)
    return derived


def _bilinear_offset(point: Tuple[float, float], outline: Sequence[Sequence[float]],
                     offsets: Sequence[Sequence[float]]) -> Tuple[float, float]:
    xs = [float(value[0]) for value in outline]
    ys = [float(value[1]) for value in outline]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    u = 0.5 if abs(x_hi - x_lo) <= _EPS else (point[0] - x_lo) / (x_hi - x_lo)
    v = 0.5 if abs(y_hi - y_lo) <= _EPS else (point[1] - y_lo) / (y_hi - y_lo)
    u, v = min(1.0, max(0.0, u)), min(1.0, max(0.0, v))
    if len(offsets) == 4:
        # Compiler rectangles/trapezoids are bottom-left, bottom-right,
        # top-right, top-left.
        weights = ((1-u)*(1-v), u*(1-v), u*v, (1-u)*v)
    else:
        distances = [math.hypot(point[0] - float(vertex[0]),
                                point[1] - float(vertex[1]))
                     for vertex in outline]
        nearest = min(range(len(distances)), key=distances.__getitem__)
        if distances[nearest] <= _EPS:
            weights = tuple(1.0 if index == nearest else 0.0
                            for index in range(len(offsets)))
        else:
            inverse = [1.0 / max(distance, _EPS) for distance in distances]
            total = sum(inverse)
            weights = tuple(value / total for value in inverse)
    return (
        sum(weight * float(offset[0]) for weight, offset in zip(weights, offsets)),
        sum(weight * float(offset[1]) for weight, offset in zip(weights, offsets)),
    )


Point2 = Tuple[float, float]


def _orientation(a: Point2, b: Point2, c: Point2) -> float:
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def _point_on_segment(point: Point2, a: Point2, b: Point2) -> bool:
    return (abs(_orientation(a, b, point)) <= 1.0e-9
            and min(a[0], b[0]) - 1.0e-9 <= point[0] <= max(a[0], b[0]) + 1.0e-9
            and min(a[1], b[1]) - 1.0e-9 <= point[1] <= max(a[1], b[1]) + 1.0e-9)


def _segments_intersect(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    values = (_orientation(a, b, c), _orientation(a, b, d),
              _orientation(c, d, a), _orientation(c, d, b))
    if ((values[0] > 1.0e-9 and values[1] < -1.0e-9
         or values[0] < -1.0e-9 and values[1] > 1.0e-9)
            and (values[2] > 1.0e-9 and values[3] < -1.0e-9
                 or values[2] < -1.0e-9 and values[3] > 1.0e-9)):
        return True
    return any((abs(value) <= 1.0e-9 and _point_on_segment(point, first, second))
               for value, point, first, second in (
                   (values[0], c, a, b), (values[1], d, a, b),
                   (values[2], a, c, d), (values[3], b, c, d)))


def _inside_polygon(point: Point2, polygon: Sequence[Point2]) -> bool:
    if any(_point_on_segment(point, a, b)
           for a, b in zip(polygon, polygon[1:] + polygon[:1])):
        return True
    inside = False
    x, y = point
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) == (b[1] > y):
            continue
        crossing_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        if crossing_x > x:
            inside = not inside
    return inside


def _inside_triangle(point: Point2, triangle: Sequence[Point2]) -> bool:
    signs = [_orientation(a, b, point)
             for a, b in zip(triangle, triangle[1:] + triangle[:1])]
    return (all(value >= -1.0e-9 for value in signs)
            or all(value <= 1.0e-9 for value in signs))


def _triangle_overlaps_polygon(triangle: Sequence[Point2],
                               polygon: Sequence[Point2]) -> bool:
    if any(_inside_polygon(point, polygon) for point in triangle):
        return True
    if any(_inside_triangle(point, triangle) for point in polygon):
        return True
    return any(_segments_intersect(a, b, c, d)
               for a, b in zip(triangle, triangle[1:] + triangle[:1])
               for c, d in zip(polygon, polygon[1:] + polygon[:1]))


def _point_segment_distance(point: Point2, a: Point2, b: Point2) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= _EPS:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = max(0.0, min(1.0,
                     ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy)
                     / length_squared))
    return math.hypot(point[0] - (a[0] + t * dx),
                      point[1] - (a[1] + t * dy))


def _closed_edge_cycles(edges: Sequence[Sequence[int]]) -> bool:
    degree: Dict[int, int] = {}
    for first, second in edges:
        degree[int(first)] = degree.get(int(first), 0) + 1
        degree[int(second)] = degree.get(int(second), 0) + 1
    return bool(degree) and all(value == 2 for value in degree.values())


def _replace_faces(*, faces: List[Triangle], face_layers: List[int],
                   face_node_ids: List[str], face_piece_ids: List[str],
                   parts: List[Dict[str, Any]], removed: Sequence[int],
                   additions: Sequence[Tuple[Triangle, int, str, str]],
                   source_part: Mapping[str, Any]) -> List[int]:
    removed_set = set(removed)
    old_to_new: Dict[int, int] = {}
    kept_faces: List[Triangle] = []
    kept_layers: List[int] = []
    kept_nodes: List[str] = []
    kept_pieces: List[str] = []
    for old_index, face in enumerate(faces):
        if old_index in removed_set:
            continue
        old_to_new[old_index] = len(kept_faces)
        kept_faces.append(face)
        kept_layers.append(face_layers[old_index])
        kept_nodes.append(face_node_ids[old_index])
        kept_pieces.append(face_piece_ids[old_index])
    first_new = len(kept_faces)
    for face, layer, node_id, piece_id in additions:
        kept_faces.append(face)
        kept_layers.append(layer)
        kept_nodes.append(node_id)
        kept_pieces.append(piece_id)
    new_indices = list(range(first_new, len(kept_faces)))
    for part in parts:
        if part is source_part:
            part["face_indices"] = new_indices
            part["face_range"] = [first_new, len(kept_faces)]
            continue
        remapped = [old_to_new[index] for index in _part_face_indices(part)
                    if index in old_to_new]
        part["face_indices"] = remapped
        part["face_range"] = ([min(remapped), max(remapped) + 1]
                              if remapped and remapped == list(
                                  range(min(remapped), max(remapped) + 1))
                              else None)
    faces[:] = kept_faces
    face_layers[:] = kept_layers
    face_node_ids[:] = kept_nodes
    face_piece_ids[:] = kept_pieces
    return new_indices


def _apply_cutout_mesh(*, vertices: List[Vec3], faces: List[Triangle],
                       vertex_layers: List[int], face_layers: List[int],
                       face_node_ids: List[str], face_piece_ids: List[str],
                       parts: List[Dict[str, Any]], source_part: Mapping[str, Any],
                       source_outline: Sequence[Sequence[float]],
                       record: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Conservatively subtract a 2D contour from a refined procedural surface."""
    source_faces = _part_face_indices(source_part)
    source_vertices = sorted({index for face_index in source_faces
                              for index in faces[face_index]})
    if not source_faces or len(source_vertices) < 3:
        return None, CUTOUT_PROJECTION
    projected = _bbox_projection(vertices, source_vertices, source_outline)
    hole = [(float(point[0]), float(point[1])) for point in record["points"]]
    source_x = [float(point[0]) for point in source_outline]
    source_y = [float(point[1]) for point in source_outline]
    hole_x = [point[0] for point in hole]
    hole_y = [point[1] for point in hole]
    source_span = (max(source_x) - min(source_x), max(source_y) - min(source_y))
    hole_span = (max(hole_x) - min(hole_x), max(hole_y) - min(hole_y))
    if (min(source_span) <= _EPS or min(hole_span) <= _EPS
            or not all(math.isfinite(value) for value in source_span + hole_span)):
        return None, CUTOUT_PROJECTION
    reuse_existing_refinement = bool(source_part.get("inner_cutouts"))
    subdivisions = (1 if reuse_existing_refinement else
                    max(4, min(12, int(math.ceil(max(
                        source_span[0] / hole_span[0],
                        source_span[1] / hole_span[1]) * 2.0)))))

    vertex_cache: Dict[Tuple[float, float, float], int] = {}
    generated_uv: Dict[int, Point2] = (dict(projected)
                                       if reuse_existing_refinement else {})
    refined: List[Tuple[Triangle, bool]] = []
    layer = int(source_part["layer"])

    def generated_vertex(face: Triangle, i: int, j: int) -> int:
        wa = 1.0 - (i + j) / subdivisions
        wb = i / subdivisions
        wc = j / subdivisions
        source = [vertices[index] for index in face]
        flat = [projected[index] for index in face]
        point3 = tuple(wa * source[0][axis] + wb * source[1][axis]
                       + wc * source[2][axis] for axis in range(3))
        point2 = (wa * flat[0][0] + wb * flat[1][0] + wc * flat[2][0],
                  wa * flat[0][1] + wb * flat[1][1] + wc * flat[2][1])
        key = tuple(round(value, 11) for value in point3)
        index = vertex_cache.get(key)
        if index is None:
            index = len(vertices)
            vertex_cache[key] = index
            vertices.append((point3[0], point3[1], point3[2]))
            vertex_layers.append(layer)
            generated_uv[index] = point2
        return index

    for source_face_index in source_faces:
        source_face = faces[source_face_index]
        if reuse_existing_refinement:
            flat_triangle = [projected[index] for index in source_face]
            refined.append((source_face,
                            _triangle_overlaps_polygon(flat_triangle, hole)))
            continue
        grid: Dict[Tuple[int, int], int] = {}
        for i in range(subdivisions + 1):
            for j in range(subdivisions + 1 - i):
                grid[(i, j)] = generated_vertex(source_face, i, j)
        for i in range(subdivisions):
            for j in range(subdivisions - i):
                triangles = [(grid[(i, j)], grid[(i + 1, j)], grid[(i, j + 1)])]
                if i + j < subdivisions - 1:
                    triangles.append((grid[(i + 1, j)], grid[(i + 1, j + 1)],
                                      grid[(i, j + 1)]))
                for triangle in triangles:
                    flat_triangle = [generated_uv[index] for index in triangle]
                    refined.append((triangle,
                                    _triangle_overlaps_polygon(flat_triangle, hole)))

    removed_triangles = [triangle for triangle, remove in refined if remove]
    retained_triangles = [triangle for triangle, remove in refined if not remove]
    if not removed_triangles:
        return None, CUTOUT_PROJECTION
    if not retained_triangles:
        return None, CUTOUT_EMPTY

    edge_states: Dict[Tuple[int, int], set] = {}
    for triangle, remove in refined:
        for first, second in ((triangle[0], triangle[1]),
                              (triangle[1], triangle[2]),
                              (triangle[2], triangle[0])):
            edge_states.setdefault(tuple(sorted((first, second))), set()).add(remove)
    boundary_edges = [list(edge) for edge, states in sorted(edge_states.items())
                      if states == {False, True}]
    if not boundary_edges or not _closed_edge_cycles(boundary_edges):
        return None, CUTOUT_BOUNDARY

    source_node_id = str(source_part.get("source_node_id", source_part["node_id"]))
    piece_id = str(source_part.get("piece_id", source_part["node_id"]))
    additions = [(triangle, layer, source_node_id, piece_id)
                 for triangle in retained_triangles]
    _replace_faces(
        faces=faces, face_layers=face_layers, face_node_ids=face_node_ids,
        face_piece_ids=face_piece_ids, parts=parts, removed=source_faces,
        additions=additions, source_part=source_part)

    boundary_vertices = sorted({index for edge in boundary_edges for index in edge})
    boundary_distances = [
        min(_point_segment_distance(generated_uv[index], a, b)
            for a, b in zip(hole, hole[1:] + hole[:1]))
        for index in boundary_vertices
    ]
    boundary_lengths = [math.hypot(
        generated_uv[first][0] - generated_uv[second][0],
        generated_uv[first][1] - generated_uv[second][1])
        for first, second in boundary_edges]
    error_upper = max(boundary_distances + boundary_lengths)
    boundary = {
        "operation_id": record["operation_id"],
        "kind": "CUTOUT_INNER_BOUNDARY",
        "state": PROPOSED,
        "piece_id": piece_id,
        "contour_id": record["contour_id"],
        "mesh_edges": boundary_edges,
        "mesh_edge_points_cm": [
            [[round(value, 9) for value in vertices[first]],
             [round(value, 9) for value in vertices[second]]]
            for first, second in boundary_edges
        ],
        "projected_edge_points_cm": [
            [[round(value, 9) for value in generated_uv[first]],
             [round(value, 9) for value in generated_uv[second]]]
            for first, second in boundary_edges
        ],
        "contour_edge_lineage": copy.deepcopy(record["contour_edge_lineage"]),
        "approximation": {
            "method": "conservative overlap removal after barycentric triangle refinement",
            "subdivisions_per_source_edge": subdivisions,
            "reused_existing_refined_mesh": reuse_existing_refinement,
            "removed_triangle_count": len(removed_triangles),
            "retained_triangle_count": len(retained_triangles),
            "maximum_boundary_deviation_cm": round(max(boundary_distances), 9),
            "maximum_boundary_edge_length_cm": round(max(boundary_lengths), 9),
            "error_upper_bound_cm": round(error_upper, 9),
            "conservative": True,
            "limits": [
                "flat-pattern coordinates use a preview-surface bounding-box projection",
                "the opening is expanded to remove every refined triangle touching the contour",
                "this is preview topology, not a fitted or manufacturing-certified cut surface",
            ],
        },
    }
    source_part.setdefault("inner_cutouts", []).append({
        "operation_id": record["operation_id"],
        "contour_id": record["contour_id"],
        "piece_id": piece_id,
        "state": PROPOSED,
        "pattern_cutout_digest": record["digest"],
        "hole_boundary_edge_count": len(boundary_edges),
        "approximation_error_upper_bound_cm": round(error_upper, 9),
    })
    return boundary, None


def _apply_geometry_operations(*, canonical: Mapping[str, Any], candidate_id: str,
                               structure_digest: str, vertices: List[Vec3],
                               faces: List[Triangle], vertex_layers: List[int],
                               face_layers: List[int], face_node_ids: List[str],
                               face_piece_ids: List[str], parts: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    requested = [operation for operation in canonical.get("operations", [])
                 if operation["kind"] in _GEOMETRY_OPERATION_KINDS]
    if not requested:
        return {
            "geometry_operations": [], "construction_boundaries": [],
            "pattern_conformance": None,
        }, None
    compiled = _pattern_compiler.compile_structure(
        canonical, candidate_state=PROPOSED, candidate_id=candidate_id)
    if compiled.get("verdict") != ANSWER:
        return None, _compiler_failure(
            compiled, candidate_id=candidate_id,
            structure_digest=structure_digest)
    if (compiled.get("candidate_id") != candidate_id
            or compiled.get("structure_digest") != structure_digest):
        return None, _unknown(
            OPERATION_MISMATCH,
            "2D pattern and 3D preview candidate lineage disagree",
            candidate_id=candidate_id, structure_digest=structure_digest,
            pattern_candidate_id=compiled.get("candidate_id"),
            pattern_structure_digest=compiled.get("structure_digest"))

    records = list(compiled.get("geometry_operations", []))
    requested_identity = [(row["operation_id"], row["kind"]) for row in requested]
    record_identity = [(row.get("operation_id"), row.get("kind")) for row in records]
    if requested_identity != record_identity:
        return None, _unknown(
            OPERATION_MISMATCH,
            "2D pattern did not emit every requested preview geometry operation in order",
            candidate_id=candidate_id, structure_digest=structure_digest,
            requested_operations=[list(value) for value in requested_identity],
            pattern_operations=[list(value) for value in record_identity])

    compiled_pieces = {str(piece["piece_id"]): piece
                       for piece in compiled.get("pieces", [])}
    operation_rows: List[Dict[str, Any]] = []
    construction_boundaries: List[Dict[str, Any]] = []
    nodes = {str(node["node_id"]): node for node in canonical["nodes"]}

    for requested_operation, record in zip(requested, records):
        operation_id = str(record["operation_id"])
        kind = str(record["kind"])
        source_piece_id = str(record.get("source_piece_id", record.get("piece_id", "")))
        source_part = _find_part(parts, source_piece_id)
        if source_part is None:
            return None, _unknown(
                OPERATION_MISMATCH,
                f"{operation_id} source piece has no 3D preview ownership",
                candidate_id=candidate_id, structure_digest=structure_digest,
                operation_id=operation_id, source_piece_id=source_piece_id)
        source_outline = _source_outline(compiled_pieces, record)
        source_node_id = str(source_part.get("source_node_id", source_part["node_id"]))
        node_center = _position(nodes[source_node_id])

        if kind == "CUTOUT":
            lineage = record.get("contour_edge_lineage")
            points = record.get("points")
            pattern_piece = compiled_pieces.get(source_piece_id)
            bound_cutout = (
                next((row for row in pattern_piece.get("inner_cutouts", [])
                      if row.get("digest") == record.get("digest")), None)
                if pattern_piece is not None else None)
            if (not isinstance(points, Sequence) or isinstance(points, (str, bytes))
                    or len(points) < 3
                    or not isinstance(lineage, Sequence)
                    or isinstance(lineage, (str, bytes))
                    or len(lineage) != len(points)
                    or bound_cutout != record):
                return None, _unknown(
                    OPERATION_MISMATCH,
                    f"{operation_id} 2D hole geometry and lineage are incomplete or disagree",
                    candidate_id=candidate_id, structure_digest=structure_digest,
                    operation_id=operation_id, piece_id=source_piece_id)
            boundary, cutout_error = _apply_cutout_mesh(
                vertices=vertices, faces=faces,
                vertex_layers=vertex_layers, face_layers=face_layers,
                face_node_ids=face_node_ids, face_piece_ids=face_piece_ids,
                parts=parts, source_part=source_part,
                source_outline=source_outline, record=record)
            if cutout_error is not None:
                reasons = {
                    CUTOUT_PROJECTION: (
                        "the validated 2D cutout cannot be resolved on the candidate preview surface"),
                    CUTOUT_BOUNDARY: (
                        "conservative face removal did not create a closed inner mesh boundary"),
                    CUTOUT_EMPTY: (
                        "the cutout removes every preview face owned by the source piece"),
                }
                return None, _unknown(
                    cutout_error, reasons[cutout_error],
                    candidate_id=candidate_id, structure_digest=structure_digest,
                    operation_id=operation_id, operation_kind="CUTOUT",
                    piece_id=source_piece_id, contour_id=record["contour_id"],
                    pattern_cutout_digest=record["digest"],
                    approximation_attempted=True)
            assert boundary is not None
            construction_boundaries.append(boundary)
            derived_ids = []
        elif kind == "SPLIT":
            child_ids = record["new_piece_ids"]
            negative_id = str(child_ids["negative"])
            positive_id = str(child_ids["positive"])
            ownership, boundary_edges = _split_faces(
                vertices=vertices, faces=faces, source_part=source_part,
                source_outline=source_outline, line=record["line"],
                negative_id=negative_id, positive_id=positive_id)
            owned = {piece_id: sorted(index for index, owner in ownership.items()
                                      if owner == piece_id)
                     for piece_id in (negative_id, positive_id)}
            if not all(owned.values()) or not boundary_edges:
                return None, _unknown(
                    SPLIT_RESOLUTION,
                    f"{operation_id} cannot be represented by the current preview mesh resolution",
                    candidate_id=candidate_id, structure_digest=structure_digest,
                    operation_id=operation_id, radial_segments_required="increase radial_segments")
            source_index = parts.index(source_part)  # type: ignore[arg-type]
            replacements = []
            for side, piece_id in (("negative", negative_id),
                                   ("positive", positive_id)):
                child = {
                    **copy.deepcopy(dict(source_part)),
                    "node_id": piece_id,
                    "source_node_id": source_node_id,
                    "piece_id": piece_id,
                    "face_indices": owned[piece_id],
                    "face_range": None,
                    "derived": True,
                    "derived_side": side,
                    "operation_id": operation_id,
                    "operation_kind": kind,
                    "state": PROPOSED,
                }
                replacements.append(child)
                for face_index in owned[piece_id]:
                    face_piece_ids[face_index] = piece_id
            parts[source_index:source_index + 1] = replacements
            construction_boundaries.append({
                "operation_id": operation_id,
                "kind": "SPLIT_REJOIN",
                "state": PROPOSED,
                "source_piece_id": source_piece_id,
                "piece_ids": [negative_id, positive_id],
                "mesh_edges": boundary_edges,
                "generated_join": copy.deepcopy(record["generated_join"]),
                "approximation": "split line snapped to existing preview mesh edges",
            })
            derived_ids = [negative_id, positive_id]
        elif kind == "MIRROR":
            axis_index = 0 if record["axis"] == "x" else 1
            offset = float(record["offset_cm"])

            def reflect(_index: int, vertex: Vec3) -> Vec3:
                values = list(vertex)
                local = values[axis_index] - node_center[axis_index]
                values[axis_index] = node_center[axis_index] + 2.0 * offset - local
                return (values[0], values[1], values[2])

            new_piece_id = str(record["new_piece_id"])
            _append_derived_part(
                vertices=vertices, faces=faces, vertex_layers=vertex_layers,
                face_layers=face_layers, face_node_ids=face_node_ids,
                face_piece_ids=face_piece_ids, parts=parts,
                source_part=source_part, new_piece_id=new_piece_id,
                operation=record, transform=reflect)
            derived_ids = [new_piece_id]
        elif kind == "ASYMMETRY":
            source_faces = _part_face_indices(source_part)
            source_vertices = sorted({index for face_index in source_faces
                                      for index in faces[face_index]})
            projection = _bbox_projection(vertices, source_vertices, source_outline)
            offsets = record["vertex_offsets_cm"]

            def deform(index: int, vertex: Vec3) -> Vec3:
                delta = _bilinear_offset(projection[index], source_outline, offsets)
                return (vertex[0] + delta[0], vertex[1] + delta[1], vertex[2])

            new_piece_id = str(record["new_piece_id"])
            _append_derived_part(
                vertices=vertices, faces=faces, vertex_layers=vertex_layers,
                face_layers=face_layers, face_node_ids=face_node_ids,
                face_piece_ids=face_piece_ids, parts=parts,
                source_part=source_part, new_piece_id=new_piece_id,
                operation=record, transform=deform)
            derived_ids = [new_piece_id]
        else:  # pragma: no cover - guarded by compiler/request identity
            return None, _unknown(
                OPERATION_MISMATCH, f"unsupported geometry operation {kind}",
                candidate_id=candidate_id, structure_digest=structure_digest,
                operation_id=operation_id)

        operation_detail: Dict[str, Any] = {}
        if kind == "SPLIT":
            operation_detail = {
                "line": copy.deepcopy(record["line"]),
                "generated_join": copy.deepcopy(record["generated_join"]),
            }
        elif kind == "CUTOUT":
            operation_detail = {
                "piece_id": record["piece_id"],
                "contour_id": record["contour_id"],
                "hole_points_cm": copy.deepcopy(record["points"]),
                "hole_digest": record["digest"],
                "contour_edge_lineage": copy.deepcopy(
                    record["contour_edge_lineage"]),
                "approximation": copy.deepcopy(
                    construction_boundaries[-1]["approximation"]),
            }
        elif kind == "MIRROR":
            operation_detail = {
                "axis": record["axis"],
                "offset_cm": record["offset_cm"],
                "side": record["side"],
            }
        elif kind == "ASYMMETRY":
            operation_detail = {
                "side": record["side"],
                "vertex_offsets_cm": copy.deepcopy(record["vertex_offsets_cm"]),
            }
        operation_rows.append({
            "operation_id": operation_id,
            "kind": kind,
            "state": PROPOSED,
            "source_piece_id": source_piece_id,
            "derived_piece_ids": derived_ids,
            **operation_detail,
            "parameters_digest": _digest(requested_operation.get("parameters", {})),
            "pattern_operation_digest": _digest(record),
            "pattern_operation": copy.deepcopy(record),
        })

    identity = [{"operation_id": row["operation_id"], "kind": row["kind"]}
                for row in operation_rows]
    return {
        "geometry_operations": operation_rows,
        "construction_boundaries": construction_boundaries,
        "pattern_conformance": {
            "schema": "garment.preview-pattern-conformance.v1",
            "state": PROPOSED,
            "candidate_id": candidate_id,
            "structure_digest": structure_digest,
            "pattern_digest": compiled["digest"],
            "operation_identity": identity,
            "operation_identity_digest": _digest(identity),
        },
    }, None


def generate_preview(structure: Mapping[str, Any], *, candidate_id: str,
                     radial_segments: int = 16,
                     layer_spacing_cm: float = 0.6) -> Dict[str, Any]:
    """Generate one deterministic preview mesh for one named candidate."""
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        return _unknown(BAD_REQUEST, "candidate_id must be a non-empty string",
                        candidate_id=None)
    candidate_id = candidate_id.strip()
    if (isinstance(radial_segments, bool) or not isinstance(radial_segments, int)
            or radial_segments < 3):
        return _unknown(BAD_REQUEST, "radial_segments must be an integer >= 3",
                        candidate_id=candidate_id)
    if (isinstance(layer_spacing_cm, bool)
            or not isinstance(layer_spacing_cm, (int, float))
            or not math.isfinite(float(layer_spacing_cm))
            or float(layer_spacing_cm) <= 0.0):
        return _unknown(BAD_REQUEST, "layer_spacing_cm must be finite and positive",
                        candidate_id=candidate_id)
    if not isinstance(structure, Mapping):
        return _unknown(BAD_REQUEST, "structure must be a mapping",
                        candidate_id=candidate_id)

    validated = garment_structure.validate(structure)
    if validated.get("verdict") != ANSWER:
        return _unknown(str(validated.get("verdict", BAD_REQUEST)),
                        str(validated.get("why", "structure validation failed")),
                        candidate_id=candidate_id,
                        structure_validation=validated)
    canonical = validated["graph"]
    nodes = canonical["nodes"]
    unsupported = [{"node_id": node["node_id"], "kind": node["kind"]}
                   for node in nodes if node["kind"] not in _SUPPORTED]
    if unsupported:
        return _unknown(
            UNSUPPORTED,
            "every primitive must have explicit preview geometry; none were omitted",
            candidate_id=candidate_id, unsupported_primitives=unsupported,
            supported_primitives=sorted(_SUPPORTED),
            structure_digest=validated["digest"])

    try:
        sleeve_layouts, sleeve_relation_coverage = _sleeve_layouts(
            canonical, layer_spacing_cm=float(layer_spacing_cm))
    except _PreviewRefusal as exc:
        return _unknown(
            exc.code, exc.why, candidate_id=candidate_id,
            structure_digest=validated["digest"], **exc.detail)

    vertices: List[Vec3] = []
    faces: List[Triangle] = []
    vertex_layers: List[int] = []
    face_layers: List[int] = []
    face_node_ids: List[str] = []
    face_piece_ids: List[str] = []
    parts = []
    try:
        for node in nodes:
            first_vertex, first_face = len(vertices), len(faces)
            local_vertices, local_faces, consumed = _node_geometry(
                node, nodes=nodes, segments=radial_segments,
                layer_spacing_cm=float(layer_spacing_cm),
                sleeve_layouts=sleeve_layouts)
            offset = len(vertices)
            vertices.extend(local_vertices)
            faces.extend(tuple(index + offset for index in face)
                         for face in local_faces)
            layer = int(node.get("layer", 0))
            vertex_layers.extend([layer] * len(local_vertices))
            face_layers.extend([layer] * len(local_faces))
            face_node_ids.extend([node["node_id"]] * len(local_faces))
            face_piece_ids.extend([node["node_id"]] * len(local_faces))
            attributes = node.get("attributes", {})
            part = {
                "node_id": node["node_id"], "kind": node["kind"],
                "source_node_id": node["node_id"],
                "piece_id": node["node_id"],
                "layer": layer,
                "vertex_range": [first_vertex, len(vertices)],
                "face_range": [first_face, len(faces)],
                "face_indices": list(range(first_face, len(faces))),
                "consumed_attributes": sorted(consumed),
                "unconsumed_attributes": sorted(
                    str(name) for name in attributes if name not in consumed),
                "state": PROPOSED,
            }
            if node["kind"] == "SLEEVE":
                instance_vertex_count = radial_segments * 2
                instance_face_count = radial_segments * 2
                instances = []
                for index, layout in enumerate(sleeve_layouts[node["node_id"]]):
                    instance = copy.deepcopy(layout)
                    instance["vertex_range"] = [
                        first_vertex + index * instance_vertex_count,
                        first_vertex + (index + 1) * instance_vertex_count,
                    ]
                    instance["face_range"] = [
                        first_face + index * instance_face_count,
                        first_face + (index + 1) * instance_face_count,
                    ]
                    instance["face_indices"] = list(range(*instance["face_range"]))
                    instance["lineage"] = {
                        "source_node_id": node["node_id"],
                        "instance_id": instance["instance_id"],
                        "side": instance["side"],
                        "parent_instance_id": instance["parent_instance_id"],
                        "relation_operation_id": instance["relation_operation_id"],
                        "relation_kind": instance["relation_kind"],
                        **({"gather_lineage": copy.deepcopy(
                            instance["gather_lineage"])}
                           if "gather_lineage" in instance else {}),
                        "authority": PROPOSED,
                    }
                    instances.append(instance)
                part["instances"] = instances
                part["instance_lineage_digest"] = _digest(instances)
            parts.append(part)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _unknown(BAD_GEOMETRY, str(exc), candidate_id=candidate_id,
                        structure_digest=validated["digest"])

    try:
        operation_result, operation_error = _apply_geometry_operations(
            canonical=canonical, candidate_id=candidate_id,
            structure_digest=validated["digest"], vertices=vertices,
            faces=faces, vertex_layers=vertex_layers, face_layers=face_layers,
            face_node_ids=face_node_ids, face_piece_ids=face_piece_ids,
            parts=parts)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _unknown(BAD_GEOMETRY, str(exc), candidate_id=candidate_id,
                        structure_digest=validated["digest"])
    if operation_error is not None:
        return operation_error
    assert operation_result is not None

    topology = _topology(vertices, faces)
    if topology["degenerate_face_indices"] or topology["nonmanifold_edges"]:
        return _unknown(BAD_GEOMETRY, "generated topology failed validation",
                        candidate_id=candidate_id,
                        structure_digest=validated["digest"],
                        topology=topology)

    layer_rows = []
    for layer in sorted(set(vertex_layers) | set(face_layers)):
        layer_rows.append({
            "layer": layer,
            "node_ids": [part["node_id"] for part in parts
                         if part["layer"] == layer],
            "vertex_indices": [index for index, value in enumerate(vertex_layers)
                               if value == layer],
            "face_indices": [index for index, value in enumerate(face_layers)
                             if value == layer],
        })
    layer_relations = []
    node_layers = {node["node_id"]: int(node.get("layer", 0)) for node in nodes}
    for operation in canonical.get("operations", []):
        if operation["kind"] == "LAYER":
            source = operation["source"]["node_id"]
            target = operation["target"]["node_id"]
            row = {
                "operation_id": operation["operation_id"],
                "source_node_id": source, "source_layer": node_layers[source],
                "target_node_id": target, "target_layer": node_layers[target],
            }
            relation_side = str(
                operation.get("parameters", {}).get("relation_side", "")
            ).strip().lower()
            if relation_side in {"left", "right"}:
                row["relation_side"] = relation_side
            instance_coverage = [copy.deepcopy(item)
                                 for item in sleeve_relation_coverage
                                 if item["operation_id"] == operation["operation_id"]]
            if instance_coverage:
                row["instance_coverage"] = instance_coverage
            layer_relations.append(row)

    sleeve_instances = [copy.deepcopy(instance)
                        for part in parts if part.get("kind") == "SLEEVE"
                        for instance in part.get("instances", [])]

    mesh = {
        "units": "cm",
        "vertices": [[round(value, 9) for value in vertex]
                     for vertex in vertices],
        "faces": [list(face) for face in faces],
        "vertex_layers": vertex_layers,
        "face_layers": face_layers,
        "face_node_ids": face_node_ids,
        "face_piece_ids": face_piece_ids,
    }
    result = {
        "verdict": ANSWER,
        "schema": PREVIEW_SCHEMA,
        "state": PROPOSED,
        "candidate_id": candidate_id,
        "structure_digest": validated["digest"],
        "mesh": mesh,
        "parts": parts,
        "layers": layer_rows,
        "layer_relations": layer_relations,
        "sleeve_instances": sleeve_instances,
        "sleeve_relation_coverage": sleeve_relation_coverage,
        "geometry_operations": operation_result["geometry_operations"],
        "construction_boundaries": operation_result["construction_boundaries"],
        "pattern_conformance": operation_result["pattern_conformance"],
        "topology": topology,
        "claims": {
            "preview_only": True,
            "manufacturing_ready": False,
            "sewable_pattern": False,
            "fit_validated": False,
            "material_simulated": False,
            "attachment_aware_sleeve_preview": True,
            "physical_gathered_folds_resolved": False,
            "mannequin_certified": False,
            "pattern_geometry_identity_checked": bool(
                operation_result["pattern_conformance"]),
        },
        "provenance": {
            "origin": "PROCEDURAL_GARMENT_STRUCTURE_V1",
            "method": "deterministic primitive triangulation",
            "candidate_specific": True,
            "corpus_used": False,
            "input_structure_state": PROPOSED,
            "radial_segments": radial_segments,
            "layer_spacing_cm": float(layer_spacing_cm),
            "operation_surface_mapping": (
                "flat-pattern bounding-box projection; SPLIT boundaries snap to preview mesh edges"),
            "sleeve_attachment_method": (
                "typed side instances plus exact JOIN/GATHER/LAYER parent lineage"),
            "unvalidated": [
                "pattern", "seams", "fit", "material", "manufacturing",
                "cloth simulation", "physical gathered-fold geometry",
                "mannequin certification",
            ],
        },
    }
    result["preview_digest"] = _digest({
        "candidate_id": candidate_id,
        "structure_digest": result["structure_digest"],
        "mesh": mesh,
        "layers": layer_rows,
        "layer_relations": layer_relations,
        "sleeve_instances": sleeve_instances,
        "sleeve_relation_coverage": sleeve_relation_coverage,
        "geometry_operations": operation_result["geometry_operations"],
        "construction_boundaries": operation_result["construction_boundaries"],
        "pattern_conformance": operation_result["pattern_conformance"],
    })
    return result


def generate_candidate_preview(candidate: Mapping[str, Any], *,
                               radial_segments: int = 16,
                               layer_spacing_cm: float = 0.6) -> Dict[str, Any]:
    """JSON-friendly boundary accepting ``{candidate_id, structure}``."""
    if not isinstance(candidate, Mapping):
        return _unknown(BAD_REQUEST, "candidate must be a mapping",
                        candidate_id=None)
    return generate_preview(candidate.get("structure"),
                            candidate_id=candidate.get("candidate_id"),
                            radial_segments=radial_segments,
                            layer_spacing_cm=layer_spacing_cm)


build = generate_candidate_preview
