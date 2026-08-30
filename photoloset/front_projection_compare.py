# -*- coding: utf-8 -*-
"""Typed, deterministic front-projection comparison without image libraries.

This module compares an OBSERVED front-image raster contract with a PROPOSED
render of one candidate from the same camera.  It deliberately does not emit a
weighted or aggregate similarity score.  Silhouette, typed parts, boundaries,
visible colour, and visible layer/occlusion relations remain separate axes.

Rear, occlusion-unknown, and otherwise UNKNOWN pixels are excluded from every
metric.  Exclusion never promotes a candidate claim to fact: a converged result
is still a PROPOSED front-view fit requiring human approval.

Masks are JSON-safe binary matrices or row-major run-length encodings::

    [[0, 1], [1, 1]]
    {"encoding": "rle", "size": [2, 2], "counts": [1, 3],
     "starts_with": 0}

Part masks may be direct masks or typed records containing ``mask``, ``state``,
``layer`` and an optional colour.  The input document may also carry
``part_layers`` and ``visible_color_swatches`` mappings.  A camera is bound by
an equal ``camera_digest`` or by deterministic digests of equal ``camera``
objects.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


SCHEMA = "garment.front-projection-comparison.v1"
PROPOSED = "PROPOSED"
OBSERVED = "OBSERVED"


@dataclass(frozen=True)
class ProjectionCompareConfig:
    """Independent acceptance bounds for the front-only refinement loop."""

    min_silhouette_iou: float = 0.92
    min_part_iou: float = 0.80
    max_edge_chamfer_normalized: float = 0.025
    max_color_delta_e: float = 12.0
    max_layer_occlusion_mismatch_ratio: float = 0.03
    min_render_known_coverage: float = 0.95
    max_rounds: int = 8
    max_proposals: int = 6
    worsening_epsilon: float = 1.0e-12

    def __post_init__(self) -> None:
        for name in (
            "min_silhouette_iou", "min_part_iou",
            "max_edge_chamfer_normalized",
            "max_layer_occlusion_mismatch_ratio",
            "min_render_known_coverage",
        ):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(float(value)) or not 0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be a finite value in [0, 1]")
        if (isinstance(self.max_color_delta_e, bool)
                or not isinstance(self.max_color_delta_e, (int, float))
                or not math.isfinite(float(self.max_color_delta_e))
                or self.max_color_delta_e < 0.0):
            raise ValueError("max_color_delta_e must be finite and non-negative")
        if (isinstance(self.max_rounds, bool) or not isinstance(self.max_rounds, int)
                or self.max_rounds < 1):
            raise ValueError("max_rounds must be a positive integer")
        if (isinstance(self.max_proposals, bool)
                or not isinstance(self.max_proposals, int)
                or self.max_proposals < 0):
            raise ValueError("max_proposals must be a non-negative integer")
        if (isinstance(self.worsening_epsilon, bool)
                or not isinstance(self.worsening_epsilon, (int, float))
                or not math.isfinite(float(self.worsening_epsilon))
                or self.worsening_epsilon < 0.0):
            raise ValueError("worsening_epsilon must be finite and non-negative")

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def stable_digest(value: Any) -> str:
    """Return the repository's canonical JSON SHA-256 digest."""

    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def encode_rle(matrix: Sequence[Sequence[Any]]) -> Dict[str, Any]:
    """Encode a small binary matrix as deterministic row-major RLE."""

    decoded = decode_mask(matrix)
    flat = [value for row in decoded for value in row]
    counts: List[int] = []
    current = False
    run = 0
    for value in flat:
        if value == current:
            run += 1
        else:
            counts.append(run)
            current = value
            run = 1
    counts.append(run)
    return {
        "encoding": "rle",
        "size": [len(decoded), len(decoded[0])],
        "counts": counts,
        "starts_with": 0,
    }


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _binary(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, float) and math.isfinite(value) and value in (0.0, 1.0):
        return bool(value)
    raise ValueError("mask values must be binary 0/1 values")


def decode_mask(payload: Any, *, expected_shape: Optional[Tuple[int, int]] = None
                ) -> Tuple[Tuple[bool, ...], ...]:
    """Decode a JSON-safe binary matrix or uncompressed row-major RLE."""

    value = payload
    if isinstance(value, Mapping) and "mask" in value:
        value = value["mask"]
    if isinstance(value, Mapping):
        encoding = str(value.get("encoding", "rle" if "counts" in value else "matrix")).lower()
        if encoding == "matrix":
            value = value.get("data", value.get("matrix", value.get("values")))
        elif encoding == "rle":
            size = value.get("size")
            counts = value.get("counts", value.get("rle"))
            if (not _is_sequence(size) or len(size) != 2
                    or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0
                           for v in size)):
                raise ValueError("RLE size must be [positive height, positive width]")
            if not _is_sequence(counts) or not counts:
                raise ValueError("RLE counts must be a non-empty integer sequence")
            parsed_counts: List[int] = []
            for count in counts:
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ValueError("RLE counts must be non-negative integers")
                parsed_counts.append(count)
            start = value.get("starts_with", 0)
            if start not in (0, 1, False, True):
                raise ValueError("RLE starts_with must be 0 or 1")
            total = int(size[0]) * int(size[1])
            if sum(parsed_counts) != total:
                raise ValueError("RLE counts do not fill the declared size")
            flat: List[bool] = []
            bit = bool(start)
            for count in parsed_counts:
                flat.extend([bit] * count)
                bit = not bit
            width = int(size[1])
            rows = tuple(tuple(flat[offset:offset + width])
                         for offset in range(0, total, width))
            if expected_shape is not None and (int(size[0]), width) != expected_shape:
                raise ValueError("mask shape does not match the silhouette")
            return rows
        else:
            raise ValueError(f"unsupported mask encoding {encoding!r}")

    if not _is_sequence(value) or not value:
        raise ValueError("mask must be a non-empty matrix or RLE object")
    width: Optional[int] = None
    rows_list: List[Tuple[bool, ...]] = []
    for row in value:
        if not _is_sequence(row) or not row:
            raise ValueError("mask rows must be non-empty sequences")
        parsed = tuple(_binary(cell) for cell in row)
        if width is None:
            width = len(parsed)
        elif len(parsed) != width:
            raise ValueError("mask rows must have equal width")
        rows_list.append(parsed)
    rows = tuple(rows_list)
    shape = (len(rows), int(width or 0))
    if expected_shape is not None and shape != expected_shape:
        raise ValueError("mask shape does not match the silhouette")
    return rows


def _zeros(shape: Tuple[int, int]) -> Tuple[Tuple[bool, ...], ...]:
    return tuple(tuple(False for _ in range(shape[1])) for _ in range(shape[0]))


def _or_masks(masks: Iterable[Tuple[Tuple[bool, ...], ...]],
              shape: Tuple[int, int]) -> Tuple[Tuple[bool, ...], ...]:
    flat = [False] * (shape[0] * shape[1])
    for mask in masks:
        for index, value in enumerate(cell for row in mask for cell in row):
            flat[index] = flat[index] or value
    return tuple(tuple(flat[row * shape[1]:(row + 1) * shape[1]])
                 for row in range(shape[0]))


def _state(record: Any, default: str) -> str:
    if not isinstance(record, Mapping):
        return default
    return str(record.get("state", record.get("authority", default))).upper()


def _is_unknown_part(part_id: str, record: Mapping[str, Any]) -> bool:
    upper = part_id.upper()
    visibility = str(record.get("visibility", "FRONT")).upper()
    return (
        _state(record, PROPOSED) in {"UNKNOWN", "UNOBSERVED"}
        or visibility in {"REAR", "BACK", "UNKNOWN", "OCCLUDED_UNKNOWN"}
        or upper in {"UNKNOWN", "REAR", "BACK"}
        or upper.startswith("UNKNOWN_")
        or upper.startswith("REAR_")
        or upper.startswith("BACK_")
    )


def _camera_digest(document: Mapping[str, Any]) -> Optional[str]:
    supplied = document.get("camera_digest")
    if isinstance(supplied, str) and supplied.strip():
        return supplied.strip()
    camera = document.get("camera")
    if isinstance(camera, Mapping) and camera:
        return stable_digest(camera)
    return None


def _normalise_rgb(value: Any) -> Tuple[float, float, float]:
    raw = value
    if isinstance(raw, Mapping):
        raw = raw.get("rgb", raw.get("value", raw.get("color")))
    if isinstance(raw, str):
        token = raw.strip()
        if len(token) == 7 and token.startswith("#"):
            try:
                return tuple(int(token[index:index + 2], 16) / 255.0
                             for index in (1, 3, 5))  # type: ignore[return-value]
            except ValueError as exc:
                raise ValueError("colour hex values must be #RRGGBB") from exc
    if not _is_sequence(raw) or len(raw) != 3:
        raise ValueError("visible colours must be RGB triples or #RRGGBB")
    values: List[float] = []
    for channel in raw:
        if (isinstance(channel, bool) or not isinstance(channel, (int, float))
                or not math.isfinite(float(channel)) or float(channel) < 0.0):
            raise ValueError("RGB channels must be finite and non-negative")
        values.append(float(channel))
    scale = 1.0 if max(values) <= 1.0 else 255.0
    if max(values) > scale:
        raise ValueError("RGB channels must be in [0,1] or [0,255]")
    return tuple(channel / scale for channel in values)  # type: ignore[return-value]


def _swatches(document: Mapping[str, Any], parts: Mapping[str, Mapping[str, Any]],
              *, observation: bool) -> Tuple[Dict[str, Tuple[float, float, float]], List[str]]:
    values = document.get("visible_color_swatches", document.get("color_swatches", {}))
    records: Dict[str, Any] = {}
    if isinstance(values, Mapping):
        records.update({str(key): value for key, value in values.items()})
    elif _is_sequence(values):
        for row in values:
            if isinstance(row, Mapping) and isinstance(row.get("part_id"), str):
                records[str(row["part_id"])] = row
    for part_id, part in parts.items():
        if part_id not in records:
            for key in ("visible_color", "color", "rgb", "hex_color"):
                if key in part:
                    records[part_id] = {
                        "value": part[key],
                        "state": part.get("state", OBSERVED if observation else PROPOSED),
                    }
                    break
    result: Dict[str, Tuple[float, float, float]] = {}
    excluded: List[str] = []
    default = OBSERVED if observation else PROPOSED
    for part_id in sorted(records):
        record = records[part_id]
        metadata = record if isinstance(record, Mapping) else {}
        if (_is_unknown_part(part_id, metadata)
                or (observation and _state(metadata, default) != OBSERVED)):
            excluded.append(part_id)
            continue
        result[part_id] = _normalise_rgb(record)
    return result, excluded


def _normalise_document(document: Mapping[str, Any], *, observation: bool,
                        expected_shape: Optional[Tuple[int, int]] = None
                        ) -> Dict[str, Any]:
    json.dumps(document, allow_nan=False)
    silhouette_record = document.get("silhouette_mask", document.get("silhouette"))
    if silhouette_record is None:
        raise ValueError("silhouette_mask is required")
    if observation and _state(silhouette_record, OBSERVED) != OBSERVED:
        raise ValueError("front silhouette must have OBSERVED authority")
    silhouette = decode_mask(silhouette_record, expected_shape=expected_shape)
    shape = (len(silhouette), len(silhouette[0]))

    unknown_masks = []
    for key in ("occlusion_unknown_mask", "unknown_mask", "rear_unknown_mask",
                "unscored_mask"):
        if key in document and document[key] is not None:
            unknown_masks.append(decode_mask(document[key], expected_shape=shape))
    unknown = _or_masks(unknown_masks, shape) if unknown_masks else _zeros(shape)

    raw_parts = document.get("typed_part_masks", document.get("part_masks", {}))
    if not isinstance(raw_parts, Mapping):
        raise ValueError("typed_part_masks must be an object keyed by part id")
    layers = document.get("part_layers", {})
    if layers is None:
        layers = {}
    if not isinstance(layers, Mapping):
        raise ValueError("part_layers must be an object")
    parts: Dict[str, Dict[str, Any]] = {}
    excluded_parts: List[str] = []
    default_state = OBSERVED if observation else PROPOSED
    for raw_part_id in sorted(raw_parts, key=lambda item: str(item)):
        part_id = str(raw_part_id)
        value = raw_parts[raw_part_id]
        metadata = copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}
        if _is_unknown_part(part_id, metadata):
            excluded_parts.append(part_id)
            continue
        if observation and _state(metadata, default_state) != OBSERVED:
            excluded_parts.append(part_id)
            continue
        mask = decode_mask(value, expected_shape=shape)
        layer = metadata.get("layer", layers.get(part_id))
        if layer is not None and (isinstance(layer, bool) or not isinstance(layer, int)):
            raise ValueError(f"part layer for {part_id!r} must be an integer")
        parts[part_id] = {
            **metadata,
            "mask": mask,
            "state": _state(metadata, default_state),
            "layer": layer,
        }
    has_explicit_layer_relations = "observed_layer_relations" in document
    explicit_layer_relations: Set[Tuple[str, str]] = set()
    if has_explicit_layer_relations:
        if not observation:
            raise ValueError(
                "candidate projections cannot assert observed_layer_relations")
        raw_relations = document.get("observed_layer_relations")
        if not _is_sequence(raw_relations):
            raise ValueError("observed_layer_relations must be a sequence")
        predecessor_by_front: Dict[str, str] = {}
        relation_ids: Set[str] = set()
        for index, raw_relation in enumerate(raw_relations):
            if not isinstance(raw_relation, Mapping):
                raise ValueError(
                    "observed_layer_relations[%d] must be an object" % index)
            relation_id = raw_relation.get("relation_id")
            behind = raw_relation.get(
                "behind_part_id", raw_relation.get("parent_id"))
            front = raw_relation.get(
                "front_part_id", raw_relation.get("child_id"))
            if (not isinstance(relation_id, str) or not relation_id
                    or relation_id in relation_ids):
                raise ValueError("observed layer relation ids must be unique")
            if (str(raw_relation.get("kind", "")).upper() != "LAYER"
                    or _state(raw_relation, "") != OBSERVED
                    or str(raw_relation.get("source", "")).upper()
                    != "HUMAN_EXPLICIT_FRONT_ORDER"
                    or not isinstance(behind, str)
                    or not isinstance(front, str)
                    or behind == front
                    or behind not in parts or front not in parts):
                raise ValueError(
                    "observed layer relations require two known distinct parts")
            if front in predecessor_by_front:
                raise ValueError(
                    "an observed front part cannot have multiple predecessors")
            relation_ids.add(relation_id)
            predecessor_by_front[front] = behind
            explicit_layer_relations.add((behind, front))
        for start in parts:
            seen: Set[str] = set()
            current: Optional[str] = start
            while current is not None:
                if current in seen:
                    raise ValueError("observed layer relations must be acyclic")
                seen.add(current)
                current = predecessor_by_front.get(current)
    colours, excluded_colours = _swatches(document, parts, observation=observation)
    return {
        "shape": shape,
        "silhouette": silhouette,
        "unknown": unknown,
        "parts": parts,
        "colours": colours,
        "excluded_parts": sorted(set(excluded_parts)),
        "excluded_colours": sorted(set(excluded_colours)),
        "camera_digest": _camera_digest(document),
        "has_explicit_layer_relations": has_explicit_layer_relations,
        "explicit_layer_relations": explicit_layer_relations,
    }


def _flatten(mask: Tuple[Tuple[bool, ...], ...]) -> List[bool]:
    return [cell for row in mask for cell in row]


def _valid_mask(observation: Mapping[str, Any], rendering: Mapping[str, Any]
                ) -> Tuple[List[bool], Dict[str, Any]]:
    obs_unknown = _flatten(observation["unknown"])
    render_unknown = _flatten(rendering["unknown"])
    valid = [not left and not right for left, right in zip(obs_unknown, render_unknown)]
    observed_known = sum(not value for value in obs_unknown)
    render_known_on_observed = sum(
        not left and not right for left, right in zip(obs_unknown, render_unknown))
    coverage = (render_known_on_observed / observed_known
                if observed_known else 1.0)
    return valid, {
        "total_pixels": len(valid),
        "observation_unknown_pixels": sum(obs_unknown),
        "render_unknown_pixels": sum(render_unknown),
        "scored_pixels": sum(valid),
        "render_known_coverage_of_observed_front": coverage,
    }


def _iou(left: Iterable[bool], right: Iterable[bool], valid: Iterable[bool]
         ) -> Tuple[float, int, int, int]:
    intersection = 0
    union = 0
    evaluated = 0
    for a, b, keep in zip(left, right, valid):
        if not keep:
            continue
        evaluated += 1
        intersection += int(a and b)
        union += int(a or b)
    return (1.0 if union == 0 else intersection / union,
            intersection, union, evaluated)


def _edge_points(mask: Tuple[Tuple[bool, ...], ...], valid: Sequence[bool]
                 ) -> List[Tuple[int, int]]:
    height, width = len(mask), len(mask[0])
    points: List[Tuple[int, int]] = []
    for row in range(height):
        for column in range(width):
            index = row * width + column
            if not valid[index] or not mask[row][column]:
                continue
            boundary = False
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = row + dr, column + dc
                if nr < 0 or nr >= height or nc < 0 or nc >= width:
                    boundary = True
                    break
                nindex = nr * width + nc
                if valid[nindex] and not mask[nr][nc]:
                    boundary = True
                    break
            if boundary:
                points.append((row, column))
    return points


def _directed_chamfer(source: Sequence[Tuple[int, int]],
                      target: Sequence[Tuple[int, int]], diagonal: float) -> float:
    if not source:
        return 0.0
    if not target:
        return diagonal
    return sum(min(math.hypot(sr - tr, sc - tc) for tr, tc in target)
               for sr, sc in source) / len(source)


def _chamfer(left: Tuple[Tuple[bool, ...], ...],
             right: Tuple[Tuple[bool, ...], ...], valid: Sequence[bool]
             ) -> Dict[str, Any]:
    height, width = len(left), len(left[0])
    diagonal = math.hypot(max(height - 1, 1), max(width - 1, 1))
    left_edges = _edge_points(left, valid)
    right_edges = _edge_points(right, valid)
    if not left_edges and not right_edges:
        pixels = 0.0
    else:
        pixels = (_directed_chamfer(left_edges, right_edges, diagonal)
                  + _directed_chamfer(right_edges, left_edges, diagonal)) / 2.0
    return {
        "status": "SCORED",
        "method": "symmetric_boundary_chamfer_4_neighbour",
        "distance_pixels": pixels,
        "distance_normalized_by_image_diagonal": pixels / diagonal,
        "observation_edge_pixels": len(left_edges),
        "render_edge_pixels": len(right_edges),
    }


def _srgb_to_lab(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
    linear = []
    for channel in rgb:
        linear.append(channel / 12.92 if channel <= 0.04045
                      else ((channel + 0.055) / 1.055) ** 2.4)
    red, green, blue = linear
    x = (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue) / 0.95047
    y = (0.2126729 * red + 0.7151522 * green + 0.0721750 * blue)
    z = (0.0193339 * red + 0.1191920 * green + 0.9503041 * blue) / 1.08883

    def f(value: float) -> float:
        delta = 6.0 / 29.0
        return value ** (1.0 / 3.0) if value > delta ** 3 else value / (3 * delta ** 2) + 4.0 / 29.0

    fx, fy, fz = f(x), f(y), f(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _delta_e(left: Tuple[float, float, float],
             right: Tuple[float, float, float]) -> float:
    first, second = _srgb_to_lab(left), _srgb_to_lab(right)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _top_parts(parts: Mapping[str, Mapping[str, Any]], valid: Sequence[bool],
               total: int) -> Tuple[List[Optional[str]], Set[int]]:
    masks = {part_id: _flatten(part["mask"]) for part_id, part in parts.items()
             if isinstance(part.get("layer"), int)}
    top: List[Optional[str]] = [None] * total
    ambiguous: Set[int] = set()
    for index in range(total):
        if not valid[index]:
            continue
        present = [(int(parts[part_id]["layer"]), part_id)
                   for part_id, mask in masks.items() if mask[index]]
        if not present:
            continue
        highest = max(layer for layer, _ in present)
        winners = sorted(part_id for layer, part_id in present if layer == highest)
        if len(winners) == 1:
            top[index] = winners[0]
        else:
            ambiguous.add(index)
    return top, ambiguous


def _layer_relations(parts: Mapping[str, Mapping[str, Any]], valid: Sequence[bool]
                     ) -> Set[Tuple[str, str]]:
    ids = sorted(part_id for part_id, part in parts.items()
                 if isinstance(part.get("layer"), int))
    flattened = {part_id: _flatten(parts[part_id]["mask"]) for part_id in ids}
    relations: Set[Tuple[str, str]] = set()
    for offset, first_id in enumerate(ids):
        for second_id in ids[offset + 1:]:
            overlap = any(keep and left and right for keep, left, right in zip(
                valid, flattened[first_id], flattened[second_id]))
            if not overlap:
                continue
            first_layer = int(parts[first_id]["layer"])
            second_layer = int(parts[second_id]["layer"])
            if first_layer < second_layer:
                relations.add((first_id, second_id))
            elif second_layer < first_layer:
                relations.add((second_id, first_id))
    return relations


def _layer_axis(observation: Mapping[str, Any], rendering: Mapping[str, Any],
                valid: Sequence[bool]) -> Dict[str, Any]:
    total = len(valid)
    explicit = bool(observation.get("has_explicit_layer_relations"))
    obs_relations = (set(observation.get("explicit_layer_relations", set()))
                     if explicit else
                     _layer_relations(observation["parts"], valid))
    if explicit:
        # The person supplied the relation domain.  Candidate order can be
        # tested from the two typed part layers even when the coarse raster
        # polygons share no scored pixel; absence of overlap must not erase a
        # human statement or invent a replacement relation.
        render_relations: Set[Tuple[str, str]] = set()
        for behind, front in obs_relations:
            behind_part = rendering["parts"].get(behind)
            front_part = rendering["parts"].get(front)
            if behind_part is None or front_part is None:
                continue
            behind_layer = behind_part.get("layer")
            front_layer = front_part.get("layer")
            if not isinstance(behind_layer, int) or not isinstance(front_layer, int):
                continue
            if behind_layer < front_layer:
                render_relations.add((behind, front))
            elif front_layer < behind_layer:
                render_relations.add((front, behind))
    else:
        render_relations = _layer_relations(rendering["parts"], valid)

    # A top-visible part id is evidence about layer order only where at least
    # two observed, integer-layer parts actually overlap.  Comparing it over
    # every occupied pixel makes an ordinary silhouette/part-mask residual
    # appear a second time as a layer-order residual.  In particular, a
    # single confirmed aggregate garment has no observable layer relation at
    # all, so there is nothing that a REORDER operation can truthfully repair.
    relation_domain = [False] * total
    flattened = {
        part_id: _flatten(part["mask"])
        for part_id, part in observation["parts"].items()
    }
    for lower_id, upper_id in obs_relations:
        lower = flattened[lower_id]
        upper = flattened[upper_id]
        for index, (keep, lower_present, upper_present) in enumerate(zip(
                valid, lower, upper)):
            if keep and lower_present and upper_present:
                relation_domain[index] = True

    obs_top, obs_ambiguous = _top_parts(
        observation["parts"], relation_domain, total)
    render_top, render_ambiguous = _top_parts(
        rendering["parts"], relation_domain, total)
    excluded = obs_ambiguous | render_ambiguous
    evaluated = 0
    mismatches = 0
    for index, (left, right) in enumerate(zip(obs_top, render_top)):
        if (not relation_domain[index] or index in excluded
                or (left is None and right is None)):
            continue
        evaluated += 1
        mismatches += int(left != right)
    missing = sorted(obs_relations - render_relations)
    reversed_relations = sorted(
        relation for relation in obs_relations
        if (relation[1], relation[0]) in render_relations)
    ratio = mismatches / evaluated if evaluated else 0.0
    return {
        "status": "SCORED" if evaluated or obs_relations else "NOT_SCORED",
        "method": ("human_explicit_relation_and_typed_candidate_layer_order"
                   if explicit else
                   "typed_top_visible_part_and_explicit_integer_layer_order"),
        "relation_authority": ("HUMAN_EXPLICIT_FRONT_ORDER"
                               if explicit else "INFERRED_FROM_OVERLAPPING_MASKS"),
        "pixel_mismatch_count": mismatches,
        "evaluated_pixels": evaluated,
        "pixel_mismatch_ratio": ratio,
        "observation_overlap_pixels": sum(relation_domain),
        "ambiguous_equal_layer_pixels_excluded": len(excluded),
        "observation_relations": [list(row) for row in sorted(obs_relations)],
        "render_relations": [list(row) for row in sorted(render_relations)],
        "missing_observed_relations": [list(row) for row in missing],
        "reversed_observed_relations": [list(row) for row in reversed_relations],
    }


def _part_axis(observation: Mapping[str, Any], rendering: Mapping[str, Any],
               valid: Sequence[bool]) -> Dict[str, Any]:
    per_part: Dict[str, Any] = {}
    zeros = [False] * len(valid)
    for part_id in sorted(observation["parts"]):
        left = _flatten(observation["parts"][part_id]["mask"])
        right_part = rendering["parts"].get(part_id)
        right = _flatten(right_part["mask"]) if right_part is not None else zeros
        iou, intersection, union, evaluated = _iou(left, right, valid)
        per_part[part_id] = {
            "status": "SCORED",
            "iou": iou,
            "intersection_pixels": intersection,
            "union_pixels": union,
            "evaluated_pixels": evaluated,
            "render_part_present": right_part is not None,
        }
    render_only = sorted(set(rendering["parts"]) - set(observation["parts"]))
    return {
        "status": "SCORED" if per_part else "NOT_SCORED",
        "per_part": per_part,
        "minimum_iou": min((row["iou"] for row in per_part.values()), default=None),
        "render_only_parts_not_scored": render_only,
    }


def _colour_axis(observation: Mapping[str, Any], rendering: Mapping[str, Any]
                 ) -> Dict[str, Any]:
    per_part: Dict[str, Any] = {}
    missing: List[str] = []
    for part_id in sorted(observation["colours"]):
        right = rendering["colours"].get(part_id)
        if right is None:
            missing.append(part_id)
            continue
        left = observation["colours"][part_id]
        per_part[part_id] = {
            "delta_e_76": _delta_e(left, right),
            "observation_rgb": list(left),
            "render_rgb": list(right),
        }
    distances = [row["delta_e_76"] for row in per_part.values()]
    return {
        "status": "SCORED" if per_part else "NOT_SCORED",
        "method": "CIE76_DeltaE_from_sRGB_D65",
        "per_part": per_part,
        "maximum_delta_e": max(distances, default=None),
        "mean_delta_e_descriptive_only": (
            sum(distances) / len(distances) if distances else None),
        "missing_render_swatches": missing,
        "render_only_swatches_not_scored": sorted(
            set(rendering["colours"]) - set(observation["colours"])),
    }


def _proposal(operation: str, axis: str, target: str,
              parameters: Mapping[str, Any]) -> Dict[str, Any]:
    payload = {
        "state": PROPOSED,
        "operation": operation,
        "reason_axis": axis,
        "target": target,
        "parameters": copy.deepcopy(dict(parameters)),
        "authority": "PROPOSED_FRONT_REPROJECTION_CORRECTION",
        "breaks_when": "a new view, changed camera, or human review contradicts this proposal",
        "does_not_assert_observed_geometry": True,
    }
    payload["proposal_id"] = stable_digest(payload)[:20]
    return payload


def _proposals(axes: Mapping[str, Any], exclusions: Mapping[str, Any],
               config: ProjectionCompareConfig) -> List[Dict[str, Any]]:
    values: List[Dict[str, Any]] = []
    silhouette = axes["silhouette"]
    if silhouette["iou"] < config.min_silhouette_iou:
        values.append(_proposal(
            "ADJUST_FRONT_SILHOUETTE", "silhouette", "front_visible_boundary",
            {"comparison": "same_camera_mask", "preserve_unknown": True},
        ))
    parts = axes["parts"]["per_part"]
    for part_id, row in sorted(parts.items(), key=lambda item: (item[1]["iou"], item[0])):
        if row["iou"] < config.min_part_iou:
            values.append(_proposal(
                "ALIGN_TYPED_PART_MASK", "parts", part_id,
                {"comparison": "same_camera_typed_mask", "preserve_unknown": True},
            ))
    edge = axes["edge_chamfer"]
    if edge["distance_normalized_by_image_diagonal"] > config.max_edge_chamfer_normalized:
        values.append(_proposal(
            "REFINE_VISIBLE_FRONT_BOUNDARY", "edge_chamfer", "front_visible_edges",
            {"method": edge["method"], "preserve_unknown": True},
        ))
    colours = axes["color_distance"]
    for part_id in colours["missing_render_swatches"]:
        values.append(_proposal(
            "BIND_VISIBLE_PART_COLOR", "color_distance", part_id,
            {"source": "observed_visible_swatch", "material_identity": "UNKNOWN"},
        ))
    for part_id, row in sorted(
            colours["per_part"].items(),
            key=lambda item: (-item[1]["delta_e_76"], item[0])):
        if row["delta_e_76"] > config.max_color_delta_e:
            values.append(_proposal(
                "ADJUST_VISIBLE_PART_COLOR", "color_distance", part_id,
                {"color_space": "sRGB_D65", "material_identity": "UNKNOWN"},
            ))
    layer = axes["layer_occlusion"]
    if (layer["pixel_mismatch_ratio"] > config.max_layer_occlusion_mismatch_ratio
            or layer["missing_observed_relations"]
            or layer["reversed_observed_relations"]):
        values.append(_proposal(
            "REORDER_VISIBLE_FRONT_LAYERS", "layer_occlusion", "typed_front_parts",
            {"relations": layer["observation_relations"], "rear_order": "UNKNOWN"},
        ))
    if (exclusions["render_known_coverage_of_observed_front"]
            < config.min_render_known_coverage):
        values.append(_proposal(
            "RENDER_KNOWN_FRONT_COVERAGE", "unknown_coverage", "observed_known_front",
            {"rear_and_observation_unknown_remain_unscored": True},
        ))
    return values[:config.max_proposals]


def _axis_losses(axes: Mapping[str, Any], exclusions: Mapping[str, Any]
                 ) -> Dict[str, Optional[float]]:
    losses = {
        "silhouette/iou_loss": 1.0 - float(axes["silhouette"]["iou"]),
        "edge_chamfer/normalized_distance": float(
            axes["edge_chamfer"]["distance_normalized_by_image_diagonal"]),
        "layer_occlusion/pixel_mismatch_ratio": float(
            axes["layer_occlusion"]["pixel_mismatch_ratio"]),
        "unknown_coverage/render_unknown_fraction": 1.0 - float(
            exclusions["render_known_coverage_of_observed_front"]),
    }
    for part_id, row in axes["parts"]["per_part"].items():
        losses[f"parts/{part_id}/iou_loss"] = 1.0 - float(row["iou"])
    colours = axes["color_distance"]
    colour_ids = sorted(set(colours["per_part"])
                        | set(colours["missing_render_swatches"]))
    for part_id in colour_ids:
        missing = part_id in colours["missing_render_swatches"]
        losses[f"color_distance/{part_id}/missing"] = float(missing)
        losses[f"color_distance/{part_id}/delta_e_76"] = (
            None if missing else float(colours["per_part"][part_id]["delta_e_76"]))
    losses["layer_occlusion/missing_relation_count"] = float(
        len(axes["layer_occlusion"]["missing_observed_relations"]))
    losses["layer_occlusion/reversed_relation_count"] = float(
        len(axes["layer_occlusion"]["reversed_observed_relations"]))
    return dict(sorted(losses.items()))


def _meets_bounds(axes: Mapping[str, Any], exclusions: Mapping[str, Any],
                  config: ProjectionCompareConfig) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if axes["silhouette"]["iou"] < config.min_silhouette_iou:
        reasons.append("SILHOUETTE_IOU_BELOW_BOUND")
    for part_id, row in axes["parts"]["per_part"].items():
        if row["iou"] < config.min_part_iou:
            reasons.append(f"PART_IOU_BELOW_BOUND:{part_id}")
    if (axes["edge_chamfer"]["distance_normalized_by_image_diagonal"]
            > config.max_edge_chamfer_normalized):
        reasons.append("EDGE_CHAMFER_ABOVE_BOUND")
    colour = axes["color_distance"]
    for part_id in colour["missing_render_swatches"]:
        reasons.append(f"VISIBLE_COLOR_MISSING:{part_id}")
    for part_id, row in colour["per_part"].items():
        if row["delta_e_76"] > config.max_color_delta_e:
            reasons.append(f"VISIBLE_COLOR_DISTANCE_ABOVE_BOUND:{part_id}")
    layer = axes["layer_occlusion"]
    if layer["pixel_mismatch_ratio"] > config.max_layer_occlusion_mismatch_ratio:
        reasons.append("LAYER_OCCLUSION_PIXEL_MISMATCH_ABOVE_BOUND")
    if layer["missing_observed_relations"]:
        reasons.append("LAYER_RELATION_MISSING")
    if layer["reversed_observed_relations"]:
        reasons.append("LAYER_RELATION_REVERSED")
    if (exclusions["render_known_coverage_of_observed_front"]
            < config.min_render_known_coverage):
        reasons.append("RENDER_KNOWN_COVERAGE_BELOW_BOUND")
    return not reasons, reasons


def _verified_previous(previous: Mapping[str, Any], observation_digest: str,
                       config_digest: str, round_index: int) -> Optional[str]:
    if previous.get("schema") != SCHEMA:
        return "UNKNOWN_PREVIOUS_EVALUATION_SCHEMA"
    supplied = previous.get("evaluation_digest")
    payload = {key: value for key, value in previous.items()
               if key != "evaluation_digest"}
    reference_authority = OBSERVED
    try:
        current = stable_digest(payload)
    except (TypeError, ValueError):
        return "UNKNOWN_PREVIOUS_EVALUATION_JSON"
    if supplied != current:
        return "UNKNOWN_PREVIOUS_EVALUATION_DIGEST"
    if previous.get("observation_digest") != observation_digest:
        return "UNKNOWN_PREVIOUS_OBSERVATION_BINDING"
    if previous.get("config_digest") != config_digest:
        return "UNKNOWN_PREVIOUS_CONFIG_BINDING"
    if not isinstance(previous.get("axis_losses_for_iteration_only"), Mapping):
        return "UNKNOWN_PREVIOUS_AXIS_LOSSES"
    if previous.get("round_index") != round_index - 1:
        return "UNKNOWN_PREVIOUS_ROUND_BINDING"
    convergence = previous.get("convergence")
    if (not isinstance(convergence, Mapping)
            or convergence.get("status") != "CONTINUE"):
        return "UNKNOWN_PREVIOUS_ROUND_TERMINAL"
    return None


def _config(value: Optional[Any]) -> ProjectionCompareConfig:
    if value is None:
        return ProjectionCompareConfig()
    if isinstance(value, ProjectionCompareConfig):
        return value
    if isinstance(value, Mapping):
        return ProjectionCompareConfig(**dict(value))
    raise ValueError("config must be ProjectionCompareConfig or an object")


def compare_front_projection(
    observation: Mapping[str, Any],
    candidate_projection: Mapping[str, Any],
    *,
    round_index: int = 1,
    previous: Optional[Mapping[str, Any]] = None,
    config: Optional[Any] = None,
) -> Dict[str, Any]:
    """Compare one same-camera candidate render to an observed front raster.

    The returned ``convergence`` decision is only an iteration-control result.
    Even ``CONVERGED`` remains PROPOSED and requires a named human approval in
    the surrounding garment workflow.
    """

    try:
        if not isinstance(observation, Mapping) or not isinstance(candidate_projection, Mapping):
            raise ValueError("observation and candidate_projection must be objects")
        if isinstance(round_index, bool) or not isinstance(round_index, int) or round_index < 1:
            raise ValueError("round_index must be a positive integer")
        settings = _config(config)
        if round_index > settings.max_rounds:
            raise ValueError("round_index exceeds config.max_rounds")
        reference_authority = str(
            observation.get("reference_authority", OBSERVED)).upper()
        observation_for_metrics: Mapping[str, Any] = observation
        if reference_authority == "HUMAN_CONFIRMED_TARGET":
            human_edit_digest = observation.get("human_edit_digest")
            if not isinstance(human_edit_digest, str) or not human_edit_digest:
                raise ValueError(
                    "HUMAN_CONFIRMED_TARGET requires human_edit_digest")
            silhouette = observation.get(
                "silhouette_mask", observation.get("silhouette"))
            if _state(silhouette, "") != "HUMAN_CONFIRMED_TARGET":
                raise ValueError(
                    "human target silhouette must have HUMAN_CONFIRMED_TARGET authority")
            # Score a private compatibility copy through the existing strict
            # observed-raster path. The source authority and digest remain a
            # human design target; no observation or fact is promoted.
            scoring_copy = copy.deepcopy(dict(observation))
            scoring_silhouette = scoring_copy.get(
                "silhouette_mask", scoring_copy.get("silhouette"))
            if isinstance(scoring_silhouette, dict):
                scoring_silhouette["state"] = OBSERVED
            raw_parts = scoring_copy.get(
                "typed_part_masks", scoring_copy.get("part_masks", {}))
            if isinstance(raw_parts, Mapping):
                for record in raw_parts.values():
                    if isinstance(record, dict):
                        record["state"] = OBSERVED
            observation_for_metrics = scoring_copy
        elif reference_authority != OBSERVED:
            raise ValueError(
                "reference_authority must be OBSERVED or HUMAN_CONFIRMED_TARGET")
        observed = _normalise_document(
            observation_for_metrics, observation=True)
        rendered = _normalise_document(
            candidate_projection, observation=False, expected_shape=observed["shape"])
        if observed["camera_digest"] is None or rendered["camera_digest"] is None:
            raise ValueError("both inputs require camera or camera_digest")
        if observed["camera_digest"] != rendered["camera_digest"]:
            return {
                "schema": SCHEMA,
                "verdict": "UNKNOWN_FRONT_PROJECTION_CAMERA_MISMATCH",
                "state": "UNKNOWN",
                "observation_camera_digest": observed["camera_digest"],
                "render_camera_digest": rendered["camera_digest"],
                "proposals": [],
                "fact_promotions": [],
            }
    except (TypeError, ValueError) as exc:
        return {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_FRONT_PROJECTION_INPUT",
            "state": "UNKNOWN",
            "why": str(exc),
            "proposals": [],
            "fact_promotions": [],
        }

    observation_digest = stable_digest(observation)
    render_digest = stable_digest(candidate_projection)
    config_digest = stable_digest(settings.as_dict())
    if previous is not None:
        if not isinstance(previous, Mapping):
            return {
                "schema": SCHEMA,
                "verdict": "UNKNOWN_PREVIOUS_EVALUATION_INPUT",
                "state": "UNKNOWN", "proposals": [], "fact_promotions": [],
            }
        invalid = _verified_previous(
            previous, observation_digest, config_digest, round_index)
        if invalid:
            return {
                "schema": SCHEMA, "verdict": invalid, "state": "UNKNOWN",
                "proposals": [], "fact_promotions": [],
            }

    valid, exclusions = _valid_mask(observed, rendered)
    obs_silhouette = _flatten(observed["silhouette"])
    render_silhouette = _flatten(rendered["silhouette"])
    iou, intersection, union, evaluated = _iou(
        obs_silhouette, render_silhouette, valid)
    axes: Dict[str, Any] = {
        "silhouette": {
            "status": "SCORED",
            "iou": iou,
            "intersection_pixels": intersection,
            "union_pixels": union,
            "evaluated_pixels": evaluated,
        },
        "parts": _part_axis(observed, rendered, valid),
        "edge_chamfer": _chamfer(
            observed["silhouette"], rendered["silhouette"], valid),
        "color_distance": _colour_axis(observed, rendered),
        "layer_occlusion": _layer_axis(observed, rendered, valid),
    }
    exclusions.update({
        "observation_excluded_part_ids": observed["excluded_parts"],
        "render_excluded_part_ids": rendered["excluded_parts"],
        "observation_excluded_color_ids": observed["excluded_colours"],
        "render_excluded_color_ids": rendered["excluded_colours"],
        "rear_and_unknown_are_never_scored": True,
    })
    losses = _axis_losses(axes, exclusions)
    within_bounds, unmet = _meets_bounds(axes, exclusions, settings)

    comparison_to_previous: Dict[str, Any] = {
        "status": "FIRST_ROUND", "regressions": [], "improvements": [],
        "ties": [],
    }
    if previous is not None:
        previous_losses = previous["axis_losses_for_iteration_only"]
        paths = sorted(set(losses) | set(previous_losses))
        regressions: List[Dict[str, Any]] = []
        improvements: List[Dict[str, Any]] = []
        ties: List[str] = []
        for path in paths:
            if path not in losses or path not in previous_losses:
                regressions.append({
                    "axis_path": path,
                    "previous_loss": previous_losses.get(path),
                    "current_loss": losses.get(path),
                    "reason": "axis became unavailable or changed its typed domain",
                })
                continue
            before_raw, after_raw = previous_losses[path], losses[path]
            if before_raw is None and after_raw is None:
                ties.append(path)
                continue
            # Colour distance only exists while the swatch is available.  Its
            # companion /missing axis records availability improvement or
            # regression; no invented numeric penalty is assigned to UNKNOWN.
            if before_raw is None or after_raw is None:
                ties.append(path)
                continue
            before, after = float(before_raw), float(after_raw)
            if after > before + settings.worsening_epsilon:
                regressions.append({"axis_path": path, "previous_loss": before,
                                    "current_loss": after})
            elif after < before - settings.worsening_epsilon:
                improvements.append({"axis_path": path, "previous_loss": before,
                                     "current_loss": after})
            else:
                ties.append(path)
        status = ("REGRESSED" if regressions else
                  "IMPROVED_OR_EQUAL" if improvements else "EXACT_AXIS_TIE")
        comparison_to_previous = {
            "status": status,
            "regressions": regressions,
            "improvements": improvements,
            "ties": ties,
            "improvements_never_offset_regressions": True,
        }

    proposed = _proposals(axes, exclusions, settings)
    regressions = comparison_to_previous["regressions"]
    exact_tie = comparison_to_previous["status"] == "EXACT_AXIS_TIE"
    if regressions:
        convergence_status = "REJECT_WORSENED"
    elif within_bounds:
        convergence_status = "CONVERGED"
    elif exact_tie:
        convergence_status = "STALLED_TIE"
    elif round_index >= settings.max_rounds:
        convergence_status = "MAX_ROUNDS_REACHED"
    else:
        convergence_status = "CONTINUE"

    tie_key = [render_digest, str(candidate_projection.get("candidate_id", ""))]
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PROPOSED_FRONT_PROJECTION_EVALUATION",
        "state": PROPOSED,
        "reference_authority": reference_authority,
        "reference_authority_is_not_fact_promotion": True,
        "candidate_id": candidate_projection.get("candidate_id"),
        "round_index": round_index,
        "max_rounds": settings.max_rounds,
        "camera_binding": {
            "status": "BOUND_SAME_CAMERA",
            "camera_digest": observed["camera_digest"],
        },
        "raster_shape": list(observed["shape"]),
        "axes": axes,
        "excluded_from_scoring": exclusions,
        "proposals": proposed,
        "proposal_limit": settings.max_proposals,
        "convergence": {
            "status": convergence_status,
            "all_independent_bounds_met": within_bounds,
            "unmet_bounds": unmet,
            "reject_current_round": bool(regressions),
            "may_advance_to_next_round": (
                convergence_status == "CONTINUE"),
            "requires_human_approval": True,
            "rear_authority": PROPOSED,
            "tie_rule": (
                "only exact axis ties are ordered; lower render digest then "
                "lower candidate_id wins scheduling, never quality authority"),
            "deterministic_tie_key": tie_key,
        },
        "comparison_to_previous": comparison_to_previous,
        "axis_losses_for_iteration_only": losses,
        "no_aggregate_score": True,
        "authority": {
            "front_observation": reference_authority,
            "candidate_projection": PROPOSED,
            "rear": PROPOSED,
            "unknown_regions": "EXCLUDED_NOT_INFERRED",
            "metric_pass_does_not_promote_fact": True,
        },
        "fact_promotions": [],
        "observation_digest": observation_digest,
        "render_digest": render_digest,
        "config": settings.as_dict(),
        "config_digest": config_digest,
        "previous_evaluation_digest": (
            previous.get("evaluation_digest") if previous is not None else None),
    }
    if exact_tie and previous is not None:
        previous_key = [str(previous.get("render_digest", "")),
                        str(previous.get("candidate_id", ""))]
        result["convergence"]["tie_winner"] = (
            "CURRENT" if tie_key < previous_key else "PREVIOUS")
    result["evaluation_digest"] = stable_digest(result)
    return result


def deterministic_tie_break(evaluations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Order exact multi-axis ties without pretending to rank trade-offs."""

    if not _is_sequence(evaluations) or not evaluations:
        return {"verdict": "UNKNOWN_TIE_EVALUATIONS_REQUIRED"}
    rows = list(evaluations)
    for row in rows:
        if (not isinstance(row, Mapping) or row.get("schema") != SCHEMA
                or not isinstance(row.get("axis_losses_for_iteration_only"), Mapping)):
            return {"verdict": "UNKNOWN_TIE_EVALUATION_SCHEMA"}
    canonical_losses = json.dumps(
        rows[0]["axis_losses_for_iteration_only"], sort_keys=True,
        separators=(",", ":"), allow_nan=False)
    if any(json.dumps(row["axis_losses_for_iteration_only"], sort_keys=True,
                      separators=(",", ":"), allow_nan=False) != canonical_losses
           for row in rows[1:]):
        return {
            "verdict": "UNKNOWN_NOT_AN_EXACT_AXIS_TIE",
            "why": "trade-offs remain unordered because no aggregate score exists",
        }
    ordered = sorted(rows, key=lambda row: (
        str(row.get("render_digest", "")), str(row.get("candidate_id", "")),
        str(row.get("evaluation_digest", ""))))
    return {
        "verdict": "PROPOSED_DETERMINISTIC_TIE_ORDER",
        "state": PROPOSED,
        "winner_candidate_id": ordered[0].get("candidate_id"),
        "ordered_candidate_ids": [row.get("candidate_id") for row in ordered],
        "rule": "lower render digest, then candidate_id, then evaluation digest",
        "quality_claim": False,
        "requires_human_approval": True,
    }


# Small aliases keep this usable from workflow/MCP adapters without a class.
compare = compare_front_projection
evaluate = compare_front_projection


__all__ = [
    "SCHEMA", "PROPOSED", "OBSERVED", "ProjectionCompareConfig",
    "stable_digest", "encode_rle", "decode_mask",
    "compare_front_projection", "compare", "evaluate",
    "deterministic_tie_break",
]
