# -*- coding: utf-8 -*-
"""Deterministic front-region evidence to garment structure proposals.

The input boundary is one confirmed front clothing outline plus optional
front-view region polygons.  Region labels and detector confidence remain
source metadata: they may narrow a proposal, but they never establish an
unseen back, material, seam topology, or sewing method as observation.

This module deliberately sits between segmentation and
``front_structure_hypotheses``.  It extracts bounded typed cues from label and
geometry signals, then delegates all 3-D structure composition to that module.
Missing, weak, unknown, or contradictory labels keep the affected cue
ambiguous so the downstream generator opens several falsifiable candidates.
"""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Tuple

from . import front_geometry_cues, image_structure_operations
from .front_structure_hypotheses import (
    CueState,
    FrontStructureCues,
    TypedCue,
    hypothesize_front_structure,
)


PROPOSED = "PROPOSED"
SCHEMA = "garment.front-region-structure-hypotheses.v1"


_LABEL_SIGNALS = {
    "upper": ("upper", "top", "bodice", "shirt", "blouse", "jacket",
              "身頃", "上衣", "トップス", "シャツ", "ブラウス"),
    "lower": ("lower", "bottom", "skirt", "trouser", "pants", "shorts",
              "スカート", "ズボン", "パンツ", "ボトム"),
    "leg": ("leg", "trouser", "pants", "culotte", "脚", "ズボン", "パンツ"),
    "one_piece": ("one-piece", "one piece", "one_piece", "dress", "gown", "robe",
                  "ワンピース", "ドレス", "ローブ"),
    "separator": ("waist", "waistline", "belt", "waist seam", "切替",
                  "ウエスト", "ベルト", "腰"),
    "sleeve": ("sleeve", "arm piece", "袖", "アーム"),
    "short_sleeve": ("short sleeve", "cap sleeve", "半袖", "短袖"),
    "long_sleeve": ("long sleeve", "長袖"),
    "bell_sleeve": ("bell sleeve", "flared sleeve", "ベル袖", "フレア袖"),
    "puff_sleeve": ("puff sleeve", "puffy sleeve", "パフ袖"),
    "detached_sleeve": ("detached sleeve", "arm cover", "分離袖", "付け袖"),
    "ruffle": ("ruffle", "frill", "gather", "フリル", "ラッフル", "ギャザー"),
    "overlay": ("overlay", "over layer", "apron", "overskirt", "panel",
                "重ね", "オーバーレイ", "オーバースカート", "前掛け"),
    "cape": ("cape", "mantle", "ケープ", "マント"),
    "peplum": ("peplum", "ペプラム"),
    "tail_panel": ("tail", "train", "尾", "トレーン"),
    "asymmetry": ("asymmetric", "asymmetry", "片側", "非対称", "アシンメトリー"),
    "layer": ("layer", "lining", "under dress", "underlayer", "レイヤー",
              "裏地", "重ね着", "下衣"),
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "schema": SCHEMA,
        "why": why,
        "how_to_close": "supply one finite non-degenerate confirmed front clothing outline",
        **detail,
    }


def _finite_points(raw: Any) -> List[Tuple[float, float]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    points: List[Tuple[float, float]] = []
    for row in raw:
        if (not isinstance(row, Sequence) or isinstance(row, (str, bytes))
                or len(row) < 2 or isinstance(row[0], bool)
                or isinstance(row[1], bool)):
            continue
        try:
            point = (float(row[0]), float(row[1]))
        except (TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in point):
            points.append(point)
    return points


def _outline_points(value: Any) -> List[Tuple[float, float]]:
    raw = value.get("outline") if isinstance(value, Mapping) else value
    return _finite_points(raw)


def _bounds(points: Sequence[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _normalise_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    return " ".join(text.replace("_", " ").split())


def _labels(row: Mapping[str, Any]) -> Tuple[str, ...]:
    raw = row.get("labels", row.get("label", row.get("class", row.get("name", ()))))
    if isinstance(raw, str):
        values: Iterable[Any] = (raw,)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = raw
    else:
        values = ()
    return tuple(sorted({label for label in map(_normalise_text, values) if label}))


def _confidence(value: Any) -> Any:
    """Preserve a detector annotation without turning it into evidence state."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return round(number, 6) if math.isfinite(number) and 0.0 <= number <= 1.0 else None
    label = _normalise_text(value)
    return label if label in {"low", "medium", "high", "unknown"} else None


def _strong(row: Mapping[str, Any]) -> bool:
    value = row.get("input_confidence")
    if isinstance(value, (int, float)):
        return float(value) >= 0.5
    return value not in {"low", "unknown"}


def _polygon_area(points: Sequence[Tuple[float, float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) * 0.5


def _normalised_polygon(
    points: Sequence[Tuple[float, float]],
    outline_bounds: Tuple[float, float, float, float],
    coordinate_space: str,
) -> List[Tuple[float, float]]:
    left, top, width, height = outline_bounds
    if coordinate_space == "normalized":
        return [(round(x, 6), round(y, 6)) for x, y in points]
    return [(round((x - left) / width, 6), round((y - top) / height, 6))
            for x, y in points]


def _region_row(
    value: Any,
    outline_bounds: Tuple[float, float, float, float],
) -> Dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    raw_polygon = value.get("polygon", value.get("points", value.get("outline")))
    points = _finite_points(raw_polygon)
    if len(points) < 3 or _polygon_area(points) <= 0.0:
        return None
    space = _normalise_text(value.get("coordinate_space", ""))
    if value.get("normalized") is True:
        space = "normalized"
    if space not in {"normalized", "image", "pixel", "pixels"}:
        # A 0..1 polygon alongside a pixel-space outline is a common wire form.
        space = "normalized" if all(0.0 <= v <= 1.0 for point in points for v in point) else "image"
    polygon = _normalised_polygon(points, outline_bounds, space)
    xs, ys = [point[0] for point in polygon], [point[1] for point in polygon]
    labels = _labels(value)
    payload = {
        "labels": labels,
        "polygon": polygon,
        "input_confidence": _confidence(value.get("confidence")),
    }
    polygon_digest = _digest(payload)
    provenance = value.get("provenance") if isinstance(value.get("provenance"), Mapping) else {}
    source_kind = str(provenance.get("kind", value.get("state", PROPOSED))).upper()
    front_state = "OBSERVED" if source_kind in {
        "OBSERVED", "CONFIRMED", "HUMAN_CONFIRMED"
    } else PROPOSED
    return {
        "region_id": str(value.get("region_id", value.get("id", f"region-{polygon_digest[:12]}"))),
        "labels": list(labels),
        "polygon_digest": polygon_digest,
        "bbox_normalized": [round(min(xs), 6), round(min(ys), 6),
                            round(max(xs), 6), round(max(ys), 6)],
        "centroid_normalized": [round(sum(xs) / len(xs), 6),
                                round(sum(ys) / len(ys), 6)],
        "area_normalized": round(_polygon_area(polygon), 6),
        "input_confidence": payload["input_confidence"],
        "front_evidence_state": front_state,
        "coordinate_interpretation": space,
        "_polygon": polygon,
    }


def _parallel_region_rows(
    regions: Any,
    region_polygons: Any,
    labels: Any,
    confidences: Any,
) -> List[Any]:
    """Accept record rows and the common parallel-array segmentation wire form."""
    source = regions
    if isinstance(source, Mapping):
        if isinstance(source.get("regions"), Sequence):
            source = source.get("regions")
        else:
            region_polygons = source.get(
                "region_polygons", source.get("polygons", region_polygons))
            labels = source.get("region_labels", source.get("labels", labels))
            confidences = source.get(
                "region_confidences", source.get("confidences", confidences))
            source = None
    if source is None:
        source = region_polygons
    if not isinstance(source, Sequence) or isinstance(source, (str, bytes)):
        return []
    label_rows = (labels if isinstance(labels, Sequence)
                  and not isinstance(labels, (str, bytes)) else ())
    confidence_rows = (confidences if isinstance(confidences, Sequence)
                       and not isinstance(confidences, (str, bytes)) else ())
    rows: List[Any] = []
    for index, value in enumerate(source):
        if isinstance(value, Mapping):
            row = dict(value)
        else:
            row = {"polygon": value}
        if "label" not in row and "labels" not in row and index < len(label_rows):
            row["labels"] = label_rows[index]
        if "confidence" not in row and index < len(confidence_rows):
            row["confidence"] = confidence_rows[index]
        rows.append(row)
    return rows


def _tagged(region: Mapping[str, Any], signal: str) -> bool:
    labels = region.get("labels", ())
    return any(token in label for label in labels for token in _LABEL_SIGNALS[signal])


def _regions_for(regions: Sequence[Mapping[str, Any]], signal: str,
                 *, strong: bool = False) -> List[Mapping[str, Any]]:
    return [row for row in regions
            if _tagged(row, signal) and (not strong or _strong(row))]


def _span_at(region: Mapping[str, Any], start: float, end: float) -> float | None:
    polygon = region.get("_polygon", ())
    if not polygon:
        return None
    ys = [point[1] for point in polygon]
    top, height = min(ys), max(ys) - min(ys)
    xs = [x for x, y in polygon if top + height * start <= y <= top + height * end]
    return max(xs) - min(xs) if len(xs) >= 2 else None


def _bilateral_lower(regions: Sequence[Mapping[str, Any]]) -> bool:
    lower = [row for row in regions
             if _tagged(row, "leg") or row["centroid_normalized"][1] >= 0.58]
    left = [row for row in lower if row["centroid_normalized"][0] < 0.46]
    right = [row for row in lower if row["centroid_normalized"][0] > 0.54]
    for one in left:
        for other in right:
            a, b = one["bbox_normalized"], other["bbox_normalized"]
            overlap = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
            shortest = min(a[3] - a[1], b[3] - b[1])
            if shortest > 0.0 and overlap / shortest >= 0.45:
                return True
    return False


def _side_sleeves(regions: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    explicit = _regions_for(regions, "sleeve", strong=True)
    if explicit:
        return explicit
    return [row for row in regions if _strong(row)
            and row["centroid_normalized"][1] <= 0.58
            and (row["centroid_normalized"][0] <= 0.22
                 or row["centroid_normalized"][0] >= 0.78)
            and row["bbox_normalized"][3] - row["bbox_normalized"][1] >= 0.12]


def _polygon_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    aa, bb = a["bbox_normalized"], b["bbox_normalized"]
    width = max(0.0, min(aa[2], bb[2]) - max(aa[0], bb[0]))
    height = max(0.0, min(aa[3], bb[3]) - max(aa[1], bb[1]))
    intersection = width * height
    smaller = min((aa[2] - aa[0]) * (aa[3] - aa[1]),
                  (bb[2] - bb[0]) * (bb[3] - bb[1]))
    return intersection / smaller if smaller > 0.0 else 0.0


def _signal_ids(regions: Sequence[Mapping[str, Any]], *signals: str) -> List[str]:
    return sorted({str(row["region_id"]) for row in regions
                   if any(_tagged(row, signal) for signal in signals)})


def _cue(value: Any, basis: str, breaks_when: str) -> TypedCue:
    # Even confirmed front polygons do not directly observe construction.
    return TypedCue(value, CueState.PROPOSED, basis, breaks_when)


def _typed_cues(
    source_id: str,
    metrics: Mapping[str, Any],
    regions: Sequence[Mapping[str, Any]],
) -> Tuple[FrontStructureCues, Dict[str, Any]]:
    strong = [row for row in regions if _strong(row)]
    weak_ids = sorted(str(row["region_id"]) for row in regions if not _strong(row))

    upper = _regions_for(strong, "upper")
    lower = _regions_for(strong, "lower")
    separators = _regions_for(strong, "separator")
    one_piece = _regions_for(strong, "one_piece")
    separates_signal = bool(separators or (upper and lower))
    one_piece_signal = bool(one_piece)
    if separates_signal == one_piece_signal:
        composition = "ambiguous"
    else:
        composition = "separates" if separates_signal else "one_piece"

    expansion = float(metrics.get("lower_middle_ratio", 1.0))
    silhouette = ("anime_exaggerated" if expansion >= 1.75 else
                  "flared" if expansion >= 1.18 else
                  "close" if expansion <= 0.82 else "straight")

    bilateral = _bilateral_lower(strong)
    leg_signal = bool(_regions_for(strong, "leg"))
    lower_regions = lower or [row for row in strong
                              if row["centroid_normalized"][1] >= 0.58]
    flared_region = False
    for row in lower_regions:
        top_span, bottom_span = _span_at(row, 0.05, 0.35), _span_at(row, 0.65, 0.98)
        if top_span and bottom_span and bottom_span / top_span >= 1.18:
            flared_region = True
    if bilateral or leg_signal:
        lower_shape = "split"
        silhouette = "split_lower"
    elif lower_regions and (flared_region or expansion >= 1.18):
        lower_shape = "flare"
    elif lower_regions and (_regions_for(strong, "lower") or separates_signal):
        lower_shape = "tube"
    else:
        lower_shape = "ambiguous"

    sleeves = _side_sleeves(strong)
    if _regions_for(strong, "detached_sleeve"):
        sleeve_shape = "detached"
    elif _regions_for(strong, "bell_sleeve"):
        sleeve_shape = "bell"
    elif _regions_for(strong, "puff_sleeve"):
        sleeve_shape = "puff"
    elif _regions_for(strong, "short_sleeve"):
        sleeve_shape = "short"
    elif _regions_for(strong, "long_sleeve"):
        sleeve_shape = "long"
    elif sleeves:
        extents = [row["bbox_normalized"][3] - row["bbox_normalized"][1]
                   for row in sleeves]
        sleeve_shape = "long" if max(extents) >= 0.34 else "short"
    else:
        sleeve_shape = "ambiguous"

    detail_names: set[str] = set()
    for name in ("ruffle", "overlay", "cape", "peplum", "tail_panel", "asymmetry"):
        if _regions_for(strong, name):
            detail_names.add(name)
    layer_regions = [row for row in strong
                     if any(_tagged(row, signal) for signal in ("overlay", "cape", "layer"))]
    overlap_pairs = sum(
        1 for index, row in enumerate(strong)
        for other in strong[index + 1:] if _polygon_overlap(row, other) >= 0.55)
    if layer_regions or overlap_pairs:
        detail_names.add("overlay")
    if not detail_names:
        detail_names.add("decorative_ambiguous")
    layer_count = min(4, max(1, 1 + len(layer_regions), 2 if overlap_pairs else 1))

    region_ids = sorted(str(row["region_id"]) for row in regions)
    basis_prefix = ("front-region evidence " + ", ".join(region_ids)
                    if region_ids else "no usable internal front-region label")
    cues = FrontStructureCues(
        source_id=source_id,
        composition=_cue(
            composition,
            f"{basis_prefix}; waist separation and upper/lower continuity are interpreted only on the front",
            "a corrected waist label, occlusion boundary, side view, or back view changes one-piece versus separates"),
        silhouette=_cue(
            silhouette,
            "dimensionless confirmed-outline geometry combined with front-only lower-region topology",
            "the confirmed outline includes hair, props, limbs, or detached decoration"),
        lower_shape=_cue(
            lower_shape,
            f"front lower components and labels; bilateral={bilateral}, expansion={expansion:.6f}",
            "a crotch, slit, side, or rear observation resolves skirt versus two-leg topology"),
        sleeve_shape=_cue(
            sleeve_shape,
            "front side-region extent and sleeve-labelled polygons; arms and detached ornaments remain confounders",
            "arm-region correction or another view changes sleeve attachment or volume"),
        layer_count=_cue(
            layer_count,
            f"front overlap/overlay signals only; labelled_layers={len(layer_regions)}, overlap_pairs={overlap_pairs}",
            "depth ordering, transparency, lining, or another view changes the layer count"),
        details=_cue(
            tuple(sorted(detail_names)),
            "bounded decorative interpretations from visible front labels and overlapping regions",
            "a closer observation identifies body contour, print, hair, prop, or another construction detail"),
    )
    cue_evidence = {
        "all_region_ids": region_ids,
        "weak_or_uncertain_region_ids": weak_ids,
        "composition_region_ids": sorted(set(
            _signal_ids(regions, "upper", "lower", "separator", "one_piece"))),
        "lower_region_ids": sorted(set(_signal_ids(regions, "lower", "leg"))),
        "sleeve_region_ids": sorted(str(row["region_id"]) for row in sleeves),
        "detail_region_ids": sorted(set(_signal_ids(
            regions, "ruffle", "overlay", "cape", "peplum", "tail_panel", "asymmetry", "layer"))),
        "geometric_signals": {
            "bilateral_lower": bilateral,
            "flared_lower_region": flared_region,
            "overlap_pairs": overlap_pairs,
        },
        "interpretation_state": PROPOSED,
    }
    return cues, cue_evidence


def hypothesize(
    outline: Any,
    regions: Any = None,
    *,
    region_polygons: Any = None,
    labels: Any = None,
    confidences: Any = None,
    source_id: str = "confirmed-front-regions",
) -> Dict[str, Any]:
    """Return typed front cues and multiple deterministic structure proposals."""
    outline_points = _outline_points(outline)
    if len(outline_points) < 3:
        return _unknown("UNKNOWN_FRONT_OUTLINE", "outline needs at least three finite points")
    left, top, width, height = _bounds(outline_points)
    if width <= 0.0 or height <= 0.0:
        return _unknown("UNKNOWN_FRONT_OUTLINE_DEGENERATE", "outline has zero width or height")

    outline_input = outline if isinstance(outline, Mapping) else {"outline": outline_points}
    geometry = front_geometry_cues.hypothesize(outline_input, source_id=source_id)
    if geometry.get("verdict") != PROPOSED:
        return _unknown(str(geometry.get("verdict", "UNKNOWN_FRONT_OUTLINE")),
                        str(geometry.get("why", "outline geometry could not be interpreted")))

    if regions is None and isinstance(outline, Mapping):
        regions = outline.get("regions")
        region_polygons = outline.get("region_polygons", region_polygons)
        labels = outline.get("region_labels", outline.get("labels", labels))
        confidences = outline.get(
            "region_confidences", outline.get("confidences", confidences))
    raw_regions = _parallel_region_rows(
        regions, region_polygons, labels, confidences)
    parsed = [_region_row(row, (left, top, width, height)) for row in raw_regions]
    valid = [row for row in parsed if row is not None]
    # Input ordering does not select a structure candidate.
    valid.sort(key=lambda row: (row["polygon_digest"], row["region_id"]))

    source_payload = {
        "outline": [[round(x, 6), round(y, 6)] for x, y in outline_points],
        # The geometry digest includes closed internal boundaries and open
        # internal lines.  Without it two RegionPicker payloads with the same
        # outer polygon/regions but different switch-line evidence would share
        # one source identity even though they open different structures.
        "front_geometry_digest": geometry["front_geometry_digest"],
        "regions": [{key: value for key, value in row.items() if key != "_polygon"}
                    for row in valid],
    }
    source_digest = _digest(source_payload)
    stable_source_id = f"{source_id}:{source_digest[:16]}"
    cues, cue_evidence = _typed_cues(
        stable_source_id, geometry["metrics"], valid)
    generated = hypothesize_front_structure(cues)
    hypotheses: List[Dict[str, Any]] = []
    cue_digest = _digest(cues.as_dict())
    for candidate in generated:
        row = dict(candidate)
        row.update({
            "state": PROPOSED,
            "front_region_evidence_digest": source_digest,
            "front_geometry_digest": geometry["front_geometry_digest"],
            "typed_cue_digest": cue_digest,
            "candidate_claims": {
                "back_observed": False,
                "material_observed": False,
                "sewing_observed": False,
                "construction_observed": False,
            },
        })
        hypotheses.append(row)
    hypotheses, operation_audit = (
        image_structure_operations.apply_cutout_alternative(
            outline_input, hypotheses))

    outline_provenance = (outline.get("provenance")
                          if isinstance(outline, Mapping)
                          and isinstance(outline.get("provenance"), Mapping) else {})
    outline_state = str(outline_provenance.get("kind", PROPOSED)).upper()
    public_regions = [{key: value for key, value in row.items() if key != "_polygon"}
                      for row in valid]
    result = {
        "verdict": PROPOSED,
        "schema": SCHEMA,
        "source_id": stable_source_id,
        "source_digest": source_digest,
        "outline_digest": geometry["source_outline_digest"],
        "front_geometry_digest": geometry["front_geometry_digest"],
        "outline_state": outline_state,
        "metrics": geometry["metrics"],
        "regions": public_regions,
        "rejected_region_count": len(raw_regions) - len(valid),
        "typed_cues": cues.as_dict(),
        "typed_cue_digest": cue_digest,
        "cue_evidence": cue_evidence,
        "hypotheses": hypotheses,
        "image_structure_operation_audit": operation_audit,
        "claims": {
            "front_only": True,
            "back_observed": False,
            "depth_observed": False,
            "material_observed": False,
            "sewing_observed": False,
            "measurements_from_pixels": False,
            "detector_confidence_is_fact": False,
            "internal_boundary_semantics_observed": False,
            "internal_line_semantics_observed": False,
        },
        "provenance": {
            "method": "deterministic confirmed-front region cue extraction",
            "corpus_used": False,
            "llm_used": False,
            "downstream_generator": "front_structure_hypotheses",
        },
    }
    result["digest"] = _digest(result)
    return result


extract = hypothesize
generate = hypothesize
