# -*- coding: utf-8 -*-
"""Turn confirmed front geometry into broad, falsifiable structures.

Pixels cannot reveal a back, seam topology or material.  This boundary derives
dimensionless measurements from the outer outline and, when supplied, visible
closed ``internal_boundaries`` or open ``internal_lines``.  Those geometries let
a waist-like division, stacked transverse marks or an oscillating decorative
edge influence the proposal without turning their semantic interpretation into
observation.  Every interpretation remains ``PROPOSED`` and every centimetre
dimension comes from the preview mannequin defaults in
``front_structure_hypotheses``.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Tuple

from . import image_structure_operations
from .front_structure_hypotheses import (
    CueState, FrontStructureCues, TypedCue, hypothesize_front_structure,
)


PROPOSED = "PROPOSED"
SCHEMA = "garment.front-outline-hypotheses.v1"


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {"verdict": code, "schema": SCHEMA, "why": why,
            "how_to_close": "supply one finite, non-degenerate confirmed clothing outline",
            **detail}


def _polyline(raw: Any, *, minimum: int) -> List[Tuple[float, float]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    points: List[Tuple[float, float]] = []
    for row in raw:
        if (not isinstance(row, Sequence) or isinstance(row, (str, bytes))
                or len(row) < 2 or isinstance(row[0], bool)
                or isinstance(row[1], bool)):
            continue
        try:
            x, y = float(row[0]), float(row[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            points.append((x, y))
    return points if len(points) >= minimum else []


def _points(value: Any) -> Tuple[List[Tuple[float, float]], Dict[str, Any]]:
    source = value if isinstance(value, Mapping) else {"outline": value}
    points = _polyline(source.get("outline"), minimum=3)
    return points, source


def _internal_boundaries(source: Mapping[str, Any]) -> List[List[Tuple[float, float]]]:
    """Read optional confirmed front polylines without assigning them a class."""
    raw = source.get("internal_boundaries", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    boundaries = []
    for row in raw:
        points = _polyline(row, minimum=2)
        if points:
            boundaries.append(points)
    return boundaries


def _internal_lines(source: Mapping[str, Any]) -> List[List[Tuple[float, float]]]:
    """Read optional open front polylines without assigning them a meaning."""
    raw = source.get("internal_lines", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    lines = []
    for row in raw:
        points = _polyline(row, minimum=2)
        if points:
            lines.append(points)
    return lines


def _span(points: List[Tuple[float, float]], low: float, height: float,
          start: float, end: float) -> float | None:
    xs = [x for x, y in points
          if low + height * start <= y <= low + height * end]
    return max(xs) - min(xs) if len(xs) >= 2 else None


def _metrics(points: List[Tuple[float, float]]) -> Dict[str, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    if width <= 0.0 or height <= 0.0:
        return {}
    low = min(ys)
    upper = _span(points, low, height, .05, .34)
    middle = _span(points, low, height, .34, .67)
    lower = _span(points, low, height, .67, .98)
    perimeter = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                    for a, b in zip(points, points[1:] + points[:1]))
    return {
        "width_height_ratio": round(width / height, 6),
        "upper_middle_ratio": round((upper / middle), 6)
            if upper is not None and middle and middle > 0 else 1.0,
        "lower_middle_ratio": round((lower / middle), 6)
            if lower is not None and middle and middle > 0 else 1.0,
        "perimeter_box_ratio": round(perimeter / max(2.0 * (width + height), 1e-9), 6),
    }


def _direction_reversals(values: Sequence[float], tolerance: float) -> int:
    signs: List[int] = []
    for left, right in zip(values, values[1:]):
        delta = right - left
        if abs(delta) <= tolerance:
            continue
        sign = 1 if delta > 0.0 else -1
        if not signs or signs[-1] != sign:
            signs.append(sign)
    return max(0, len(signs) - 1)


def _geometry_class_counts(
    outline: List[Tuple[float, float]],
    geometries: List[List[Tuple[float, float]]],
) -> Tuple[int, int, int]:
    """Count geometric classes without assigning construction semantics."""
    xs, ys = [point[0] for point in outline], [point[1] for point in outline]
    left, top = min(xs), min(ys)
    width, height = max(xs) - left, max(ys) - top
    transverse = 0
    waist_like = 0
    oscillating = 0
    for geometry in geometries:
        bx = [point[0] for point in geometry]
        by = [point[1] for point in geometry]
        x_span = max(bx) - min(bx)
        y_span = max(by) - min(by)
        horizontal = x_span / width >= 0.30 and y_span / height <= 0.18
        if not horizontal:
            continue
        transverse += 1
        mean_y = (sum(by) / len(by) - top) / height
        if 0.30 <= mean_y <= 0.72:
            waist_like += 1
        path = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                   for a, b in zip(geometry, geometry[1:]))
        reversals = _direction_reversals(by, height * 0.005)
        if reversals >= 2 and path / max(x_span, 1e-9) >= 1.03:
            oscillating += 1
    return transverse, waist_like, oscillating


def _internal_metrics(
    outline: List[Tuple[float, float]],
    boundaries: List[List[Tuple[float, float]]],
    lines: List[List[Tuple[float, float]]],
) -> Dict[str, float]:
    """Describe internal geometry; do not name seams, layers or garments."""
    boundary_counts = _geometry_class_counts(outline, boundaries)
    line_counts = _geometry_class_counts(outline, lines)
    return {
        "internal_boundary_count": float(len(boundaries)),
        "transverse_boundary_count": float(boundary_counts[0]),
        "waist_like_boundary_count": float(boundary_counts[1]),
        "oscillating_boundary_count": float(boundary_counts[2]),
        "internal_line_count": float(len(lines)),
        "transverse_internal_line_count": float(line_counts[0]),
        "waist_like_internal_line_count": float(line_counts[1]),
        "oscillating_internal_line_count": float(line_counts[2]),
    }


def _cue(value: Any, basis: str, breaks_when: str) -> TypedCue:
    return TypedCue(value, CueState.PROPOSED, basis, breaks_when)


def hypothesize(outline: Any, *, source_id: str = "confirmed-front") -> Dict[str, Any]:
    points, source = _points(outline)
    if len(points) < 3:
        return _unknown("UNKNOWN_FRONT_OUTLINE", "outline needs at least three finite points")
    metrics = _metrics(points)
    if not metrics:
        return _unknown("UNKNOWN_FRONT_OUTLINE_DEGENERATE", "outline has zero width or height")
    boundaries = _internal_boundaries(source)
    lines = _internal_lines(source)
    metrics.update(_internal_metrics(points, boundaries, lines))
    expansion = metrics["lower_middle_ratio"]
    silhouette = ("anime_exaggerated" if expansion >= 1.75 else
                  "flared" if expansion >= 1.18 else
                  "close" if expansion <= 0.82 else "straight")
    source_digest = hashlib.sha256(json.dumps(
        points, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    # Preserve candidate identities for both the original outline-only API and
    # the existing boundary-only API.  Open lines extend the digest only when
    # valid line geometry is actually supplied.
    if lines:
        geometry_payload: Dict[str, Any] = {
            "outline": points,
            "internal_lines": lines,
        }
        if boundaries:
            geometry_payload["internal_boundaries"] = boundaries
        geometry_digest = hashlib.sha256(json.dumps(
            geometry_payload, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()
    elif boundaries:
        geometry_digest = hashlib.sha256(json.dumps(
            {"outline": points, "internal_boundaries": boundaries},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
    else:
        geometry_digest = source_digest
    cue_basis = "dimensionless geometry derived from the confirmed front clothing boundary"
    boundary_transverse = int(metrics["transverse_boundary_count"])
    boundary_waist_like = int(metrics["waist_like_boundary_count"])
    boundary_oscillating = int(metrics["oscillating_boundary_count"])
    line_transverse = int(metrics["transverse_internal_line_count"])
    line_waist_like = int(metrics["waist_like_internal_line_count"])
    line_oscillating = int(metrics["oscillating_internal_line_count"])
    transverse = boundary_transverse + line_transverse
    waist_like = boundary_waist_like + line_waist_like
    oscillating = boundary_oscillating + line_oscillating
    composition = "separates" if waist_like else "ambiguous"
    layer_count = min(4, max(1, transverse))
    detail_values: List[str] = []
    # A lone open transverse mark away from the waist must affect at least one
    # structure candidate.  ``overlay`` is still only a falsifiable proposal:
    # the mark may instead be a seam, print, fold, piping or lighting edge.
    if transverse >= 2 or (line_transverse and not line_waist_like):
        detail_values.append("overlay")
    if oscillating:
        detail_values.append("ruffle")
    if not detail_values:
        detail_values.append("decorative_ambiguous")
    internal_basis = (
        f"{len(boundaries)} supplied closed internal boundaries and "
        f"{len(lines)} open internal lines include {transverse} broad "
        f"transverse and {oscillating} oscillating geometries"
    )
    cues = FrontStructureCues(
        source_id=f"{source_id}:{geometry_digest[:16]}",
        composition=_cue(
            composition,
            (internal_basis if waist_like else cue_basis),
            "the visible line is an overlay edge rather than a separation, or a construction observation resolves continuity"),
        silhouette=_cue(
            silhouette, cue_basis,
            "the confirmed mask includes hair, props, limbs or detached decoration"),
        lower_shape=_cue(
            "ambiguous", "one outer front silhouette cannot distinguish skirt volume, split legs or drape",
            "a crotch/slit observation or side/rear view resolves lower topology"),
        sleeve_shape=_cue(
            "ambiguous", "the outer boundary does not reliably separate sleeves, arms and detached pieces",
            "arm-region labels or another view resolve sleeve topology"),
        layer_count=_cue(
            layer_count,
            (internal_basis if transverse else
             "one silhouette supplies no reliable depth ordering; one base layer is the minimum preview"),
            "an internal boundary belongs to print, trim or one folded surface rather than a distinct layer"),
        details=_cue(
            tuple(detail_values),
            (internal_basis if boundaries or lines else
             "front-boundary complexity may be body contour, overlay or gathered decoration"),
            "internal region segmentation identifies or rejects overlays and ruffles"),
    )
    generated = hypothesize_front_structure(cues)
    hypotheses = []
    for row in generated:
        structure = {key: row[key] for key in ("schema", "nodes", "operations")}
        back = row["back_alternative"]
        hypotheses.append({
            "candidate_id": row["candidate_id"],
            "back_design": back["alternative_id"],
            "structure": structure,
            "state": PROPOSED,
            "assumptions": list(row["basis"]) + list(row["breaks_when"]),
            "outline_metrics": metrics,
            "unobserved": row["unobserved"],
            "provenance": row["provenance"],
        })
    hypotheses, operation_audit = (
        image_structure_operations.apply_cutout_alternative(source, hypotheses))
    result = {
        "verdict": PROPOSED, "schema": SCHEMA,
        "source_id": cues.source_id, "source_outline_digest": source_digest,
        "front_geometry_digest": geometry_digest,
        "outline_state": ((source.get("provenance") or {}).get("kind", PROPOSED)
                          if isinstance(source.get("provenance"), Mapping) else PROPOSED),
        "metrics": metrics, "typed_cues": cues.as_dict(),
        "hypotheses": hypotheses,
        "image_structure_operation_audit": operation_audit,
        "claims": {"back_observed": False, "depth_observed": False,
                   "material_inferred": False, "measurements_from_pixels": False,
                   "internal_boundary_semantics_observed": False,
                   "internal_line_semantics_observed": False},
    }
    result["digest"] = hashlib.sha256(json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()
    return result


generate = hypothesize
