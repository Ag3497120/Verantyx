# -*- coding: utf-8 -*-
"""Calibrated multi-view silhouettes without a plausible-number fallback.

``analyze`` accepts already extracted outlines.  It deliberately does no image
decoding: blur and registration error have to be supplied by the calibration
stage that still has access to pixels.  Every accepted frame is reported in
``provenance`` as OBSERVED.  A front/back ratio is returned as INFERRED only
when the camera angles make the two horizontal axes independently observable.

Each view is a mapping with these fields::

    {
        "frame_id": "front-001",       # unique, stable provenance key
        "source": "capture/front.png", # optional human-readable origin
        "outline": [(x, y), ...],       # closed implicitly; pixel/unit points
        "azimuth_deg": 0.0,             # 0=front, 90=side (modulo 180)
        "cm_per_unit": 0.1,             # ``cm_per_pixel`` is also accepted
        "blur_sigma_units": 0.7,        # ``blur_sigma_px`` is also accepted
        "registration_error_units": 0.4 # or ``registration_error_px``
    }

The quality values are lengths in the same coordinate units as ``outline``.
They are normalized by silhouette height, so thresholds remain meaningful
across resolutions.  They are required: an outline cannot reveal whether the
source edge was blurred before segmentation, and silently treating missing
quality evidence as sharp would be a guess.

At a common set of heights the measured half-width ``h`` at camera azimuth
``t`` is fitted to an axis-aligned elliptical horizontal section::

    h**2 = width_radius**2 * cos(t)**2
           + depth_radius**2 * sin(t)**2

The reported ratio is ``depth_radius / width_radius`` (back-to-front depth
divided by left-to-right width; radii or full diameters give the same ratio).
The per-height solutions are combined by their median.  A residual gate checks
that one stable ratio is actually supported; it does not clamp bad geometry.

No third-party package is imported.  This module also does not import another
photoloset module, which keeps it usable as a self-contained calibration gate.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple


OBSERVED = "OBSERVED"
INFERRED = "INFERRED"

INSUFFICIENT_PARALLAX = "UNKNOWN_INSUFFICIENT_PARALLAX"
FRAME_TOO_BLURRED = "UNKNOWN_FRAME_TOO_BLURRED"
FRAME_UNSTABLE = "UNKNOWN_FRAME_UNSTABLE"
FRAME_QUALITY_NOT_RECORDED = "UNKNOWN_FRAME_QUALITY_NOT_RECORDED"
BAD_VIEW = "UNKNOWN_MALFORMED_CALIBRATED_VIEW"
NO_COMMON_COVERAGE = "UNKNOWN_NO_COMMON_OUTLINE_COVERAGE"
GEOMETRY_INCONSISTENT = "UNKNOWN_MULTI_VIEW_GEOMETRY_INCONSISTENT"

Vec2 = Tuple[float, float]


def _refusal(verdict: str, why: str, how: str,
             provenance: List[Dict[str, Any]], **detail: Any
             ) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "verdict": verdict,
        "why": why,
        "how_to_close": how,
        "provenance": provenance,
    }
    out.update(detail)
    return out


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _field(view: Mapping[str, Any], name: str, *aliases: str) -> Any:
    calibration = view.get("calibration")
    places = (view, calibration) if isinstance(calibration, Mapping) else (view,)
    for place in places:
        for key in (name,) + aliases:
            if key in place:
                return place[key]
    return None


def _outline(value: Any, scale: float) -> Optional[List[Vec2]]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or len(value) < 3):
        return None
    points: List[Vec2] = []
    for point in value:
        if (not isinstance(point, Sequence) or isinstance(point, (str, bytes))
                or len(point) != 2):
            return None
        x, y = _number(point[0]), _number(point[1])
        if x is None or y is None:
            return None
        points.append((x * scale, y * scale))
    if len(set(points)) < 3:
        return None
    xs, ys = zip(*points)
    if max(xs) - min(xs) <= 0.0 or max(ys) - min(ys) <= 0.0:
        return None
    return points


def _width_at(outline: Sequence[Vec2], y: float) -> Optional[float]:
    intersections: List[float] = []
    for index, (x0, y0) in enumerate(outline):
        x1, y1 = outline[(index + 1) % len(outline)]
        if y0 == y1:
            continue
        lo, hi = sorted((y0, y1))
        # Half-open edges avoid counting a shared vertex twice.  The final
        # sample stays away from extrema, so excluding ``hi`` loses nothing.
        if lo <= y < hi:
            intersections.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
    if len(intersections) < 2:
        return None
    return max(intersections) - min(intersections)


def _angle_gap(a: float, b: float) -> float:
    gap = abs((a - b) % 180.0)
    return min(gap, 180.0 - gap)


def _solve_axes(angles: Sequence[float], half_widths: Sequence[float]
                ) -> Optional[Tuple[float, float, float]]:
    """Return width radius, depth radius, relative RMS projection residual."""
    rows = []
    for angle, half_width in zip(angles, half_widths):
        radians = math.radians(angle)
        rows.append((math.cos(radians) ** 2, math.sin(radians) ** 2,
                     half_width ** 2))
    scc = sum(c * c for c, _, _ in rows)
    sss = sum(s * s for _, s, _ in rows)
    scs = sum(c * s for c, s, _ in rows)
    scy = sum(c * y for c, _, y in rows)
    ssy = sum(s * y for _, s, y in rows)
    determinant = scc * sss - scs * scs
    if determinant <= 1e-12:
        return None
    width_sq = (scy * sss - ssy * scs) / determinant
    depth_sq = (ssy * scc - scy * scs) / determinant
    if width_sq <= 0.0 or depth_sq <= 0.0:
        return None
    width_radius, depth_radius = math.sqrt(width_sq), math.sqrt(depth_sq)
    squared_errors = []
    for c, s, observed_sq in rows:
        predicted = math.sqrt(width_sq * c + depth_sq * s)
        observed = math.sqrt(observed_sq)
        squared_errors.append((predicted - observed) ** 2)
    rms = math.sqrt(sum(squared_errors) / len(squared_errors))
    mean_half_width = sum(half_widths) / len(half_widths)
    return width_radius, depth_radius, rms / mean_half_width


def analyze(views: Sequence[Mapping[str, Any]], *, sample_count: int = 9,
            min_parallax_deg: float = 20.0,
            min_condition_score: float = 0.02,
            max_blur_fraction: float = 0.01,
            max_registration_error_fraction: float = 0.02,
            max_projection_residual_fraction: float = 0.08,
            max_ratio_spread_fraction: float = 0.12) -> Dict[str, Any]:
    """Measure support for, and when justified infer, a front/back ratio.

    The function always returns a mapping.  ``ANSWER`` includes
    ``front_back_ratio`` and ``ratio_basis``.  Every other verdict starts with
    ``UNKNOWN_`` and intentionally omits a ratio.
    """
    provenance: List[Dict[str, Any]] = []
    if isinstance(views, Sequence) and not isinstance(views, (str, bytes)):
        # Seed one record per input before validation.  Thus even an early
        # refusal (for example missing quality on frame 1) still identifies
        # every frame the caller supplied; later validation enriches records
        # whose calibrated measurements can honestly be reported.
        for index, raw in enumerate(views):
            mapping = raw if isinstance(raw, Mapping) else {}
            provenance.append({
                "frame_index": index,
                "frame_id": mapping.get("frame_id"),
                "source": mapping.get("source"),
                "kind": OBSERVED,
            })
    if (not isinstance(views, Sequence) or isinstance(views, (str, bytes))
            or len(views) < 2):
        return _refusal(
            INSUFFICIENT_PARALLAX, "前後比には少なくとも2視点が必要です",
            "異なる方位角から較正した輪郭を2フレーム以上渡してください",
            provenance, frame_count=len(views) if isinstance(views, Sequence) else 0)
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 3:
        return _refusal(BAD_VIEW, "sample_count は3以上の整数である必要があります",
                        "sample_countを3以上にしてください", provenance)

    parsed: List[Dict[str, Any]] = []
    seen_ids = set()
    for index, raw in enumerate(views):
        if not isinstance(raw, Mapping):
            return _refusal(BAD_VIEW, f"views[{index}] がmappingではありません",
                            "各viewをフィールド付きmappingで渡してください",
                            provenance, frame_index=index)
        frame_id = raw.get("frame_id")
        source = raw.get("source")
        shell = provenance[index]
        if not isinstance(frame_id, str) or not frame_id or frame_id in seen_ids:
            return _refusal(BAD_VIEW, f"views[{index}] のframe_idが空または重複です",
                            "各フレームに一意な空でないframe_idを付けてください",
                            provenance, frame_index=index)
        seen_ids.add(frame_id)
        scale = _number(_field(raw, "cm_per_unit", "cm_per_pixel"))
        angle = _number(_field(raw, "azimuth_deg", "angle_deg"))
        if scale is None or scale <= 0.0 or angle is None:
            return _refusal(BAD_VIEW, f"{frame_id}: 実寸scaleまたはazimuthが不正です",
                            "正のcm_per_unitと有限なazimuth_degを記録してください",
                            provenance, frame_id=frame_id)
        points = _outline(raw.get("outline"), scale)
        if points is None:
            return _refusal(BAD_VIEW, f"{frame_id}: 輪郭が退化または不正です",
                            "有限な2次元点を3点以上持つ非退化輪郭を渡してください",
                            provenance, frame_id=frame_id)
        blur_units = _number(_field(raw, "blur_sigma_units", "blur_sigma_px"))
        registration_units = _number(_field(
            raw, "registration_error_units", "registration_error_px"))
        if blur_units is None or registration_units is None:
            shell.update({"azimuth_deg": angle % 180.0,
                          "cm_per_unit": scale,
                          "quality_recorded": False})
            return _refusal(
                FRAME_QUALITY_NOT_RECORDED,
                f"{frame_id}: ぼけ量または位置合わせ誤差が記録されていません",
                "画素段階でblur_sigma_unitsとregistration_error_unitsを測り、"
                "輪郭と一緒に渡してください", provenance, frame_id=frame_id)
        if blur_units < 0.0 or registration_units < 0.0:
            return _refusal(BAD_VIEW, f"{frame_id}: quality値が負です",
                            "quality値を0以上の長さで記録してください",
                            provenance, frame_id=frame_id)
        ys = [point[1] for point in points]
        height = max(ys) - min(ys)
        blur_fraction = blur_units * scale / height
        registration_fraction = registration_units * scale / height
        shell.update({
            "azimuth_deg": round(angle % 180.0, 6),
            "cm_per_unit": scale,
            "outline_point_count": len(points),
            "silhouette_height_cm": round(height, 6),
            "blur_sigma_cm": round(blur_units * scale, 6),
            "blur_fraction_of_height": round(blur_fraction, 8),
            "registration_error_cm": round(registration_units * scale, 6),
            "registration_error_fraction_of_height": round(registration_fraction, 8),
            "quality_recorded": True,
        })
        parsed.append({"id": frame_id, "angle": angle % 180.0,
                       "outline": points, "lo": min(ys), "hi": max(ys),
                       "blur": blur_fraction, "registration": registration_fraction})

    blurred = [item["id"] for item in parsed if item["blur"] > max_blur_fraction]
    if blurred:
        return _refusal(
            FRAME_TOO_BLURRED,
            "輪郭抽出前のエッジぼけが許容値を超えたフレームがあります",
            "該当フレームを再撮影するか、同じ方位角の鮮明なフレームに差し替えてください",
            provenance, affected_frames=blurred,
            max_blur_fraction=max_blur_fraction)
    unstable = [item["id"] for item in parsed
                if item["registration"] > max_registration_error_fraction]
    if unstable:
        return _refusal(
            FRAME_UNSTABLE,
            "較正基準に対するフレーム位置の誤差が許容値を超えています",
            "固定カメラまたは基準マーカーで再登録し、誤差を測り直してください",
            provenance, affected_frames=unstable,
            max_registration_error_fraction=max_registration_error_fraction)

    angles = [item["angle"] for item in parsed]
    parallax = max(_angle_gap(a, b) for i, a in enumerate(angles)
                   for b in angles[i + 1:])
    design = [(math.cos(math.radians(a)) ** 2,
               math.sin(math.radians(a)) ** 2) for a in angles]
    scc = sum(c * c for c, _ in design)
    sss = sum(s * s for _, s in design)
    scs = sum(c * s for c, s in design)
    trace = scc + sss
    condition_score = (4.0 * (scc * sss - scs * scs) / (trace * trace)
                       if trace else 0.0)
    parallax_measurement = {
        "kind": OBSERVED,
        "azimuths_deg": [round(a, 6) for a in angles],
        "maximum_separation_deg": round(parallax, 6),
        "condition_score": round(condition_score, 8),
    }
    if parallax < min_parallax_deg or condition_score < min_condition_score:
        return _refusal(
            INSUFFICIENT_PARALLAX,
            "方位角の分離では幅軸と奥行軸を独立に解けません",
            "正面(0°)から少なくとも{:.1f}°離れ、できれば側面(90°)に近い"
            "較正輪郭を追加してください".format(min_parallax_deg),
            provenance, parallax=parallax_measurement,
            thresholds={"min_parallax_deg": min_parallax_deg,
                        "min_condition_score": min_condition_score})

    common_lo = max(item["lo"] for item in parsed)
    common_hi = min(item["hi"] for item in parsed)
    if common_hi <= common_lo:
        return _refusal(NO_COMMON_COVERAGE, "全視点に共通する高さ範囲がありません",
                        "同じ実寸座標系へ登録し、共通の身体区間を覆ってください",
                        provenance, common_y_range_cm=[common_lo, common_hi])
    sample_ys = [common_lo + (common_hi - common_lo) * (i + 1) / (sample_count + 1)
                 for i in range(sample_count)]
    solved = []
    for y in sample_ys:
        widths = [_width_at(item["outline"], y) for item in parsed]
        if any(width is None or width <= 0.0 for width in widths):
            continue
        solution = _solve_axes(angles, [width / 2.0 for width in widths])  # type: ignore[operator]
        if solution is not None:
            width_radius, depth_radius, residual = solution
            solved.append((y, width_radius, depth_radius,
                           depth_radius / width_radius, residual, widths))
    if len(solved) < 3:
        return _refusal(NO_COMMON_COVERAGE,
                        "共通高さで前後比を解ける輪郭走査が3本未満です",
                        "全視点で同じ高さを連続して覆う閉輪郭を渡してください",
                        provenance, requested_samples=sample_count,
                        solved_samples=len(solved))

    ratios = [row[3] for row in solved]
    residuals = [row[4] for row in solved]
    ratio = statistics.median(ratios)
    spread = ((max(ratios) - min(ratios)) / ratio) if ratio > 0.0 else math.inf
    max_residual = max(residuals)
    if (max_residual > max_projection_residual_fraction
            or spread > max_ratio_spread_fraction):
        return _refusal(
            GEOMETRY_INCONSISTENT,
            "単一の楕円前後比では複数輪郭の投影を許容残差内で説明できません",
            "方位角・実寸scale・同期姿勢を確認するか、高さ別比を扱うモデルへ送ってください",
            provenance, parallax=parallax_measurement,
            measured={"solved_samples": len(solved),
                      "max_projection_residual_fraction": round(max_residual, 8),
                      "ratio_spread_fraction": round(spread, 8)},
            thresholds={"max_projection_residual_fraction": max_projection_residual_fraction,
                        "max_ratio_spread_fraction": max_ratio_spread_fraction})

    basis = {
        "model": "h^2 = width_radius^2*cos(azimuth)^2 + depth_radius^2*sin(azimuth)^2",
        "ratio_definition": "depth_radius / width_radius",
        "frame_ids": [item["id"] for item in parsed],
        "azimuths_deg": [round(a, 6) for a in angles],
        "common_y_range_cm": [round(common_lo, 6), round(common_hi, 6)],
        "solved_sample_count": len(solved),
        "sample_ratios": [[round(row[0], 6), round(row[3], 8)] for row in solved],
        "aggregation": "median of per-height ellipse projection solutions",
        "maximum_parallax_deg": round(parallax, 6),
        "condition_score": round(condition_score, 8),
        "max_projection_residual_fraction": round(max_residual, 8),
        "ratio_spread_fraction": round(spread, 8),
    }
    rounded_ratio = round(ratio, 8)
    return {
        "verdict": "ANSWER",
        "front_back_ratio": {
            "value": rounded_ratio,
            "assumed": rounded_ratio,
            "basis": basis,
            "kind": INFERRED,
        },
        "ratio_basis": basis,
        "parallax": parallax_measurement,
        "frame_stability": {
            "kind": OBSERVED,
            "max_blur_fraction": round(max(item["blur"] for item in parsed), 8),
            "max_registration_error_fraction": round(
                max(item["registration"] for item in parsed), 8),
            "thresholds": {
                "max_blur_fraction": max_blur_fraction,
                "max_registration_error_fraction": max_registration_error_fraction,
            },
        },
        "provenance": provenance,
    }


__all__ = [
    "analyze", "OBSERVED", "INFERRED", "INSUFFICIENT_PARALLAX",
    "FRAME_TOO_BLURRED", "FRAME_UNSTABLE", "FRAME_QUALITY_NOT_RECORDED",
    "BAD_VIEW", "NO_COMMON_COVERAGE", "GEOMETRY_INCONSISTENT",
]
