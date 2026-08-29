# -*- coding: utf-8 -*-
"""Deterministic calibration of measured seam behaviour in SI units."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Mapping, Sequence


SCHEMA = "seam.measurements.v1"
ANSWER = "ANSWER"
BAD_RECORD = "UNKNOWN_BAD_SEAM_MEASUREMENT"
MISSING_OBSERVATION = "UNKNOWN_UNOBSERVED_SEAM_CHANNEL"
INSUFFICIENT_SERIES = "UNKNOWN_INSUFFICIENT_SEAM_SERIES"
MISSING_PROVENANCE = "UNKNOWN_SEAM_PROVENANCE"

_CHANNELS = ("tension", "slippage", "puckering", "fatigue", "breakage")


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def _sha256(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value.lower()))


def _number(value: Any, name: str, *, positive: bool = False,
            nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _series(value: Any, name: str, minimum: int = 2
            ) -> Sequence[Mapping[str, Any]]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or any(not isinstance(row, Mapping) for row in value)):
        raise ValueError(f"{name} must be a list of observation objects")
    if len(value) < minimum:
        raise LookupError(f"{name} needs at least {minimum} observations")
    return value


def _provenance(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LookupError("provenance must be an object")
    for key in ("source", "method", "revision"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise LookupError(f"provenance.{key} must be non-empty")
    lineage = value.get("lineage")
    if (not isinstance(lineage, Sequence) or isinstance(lineage, (str, bytes))
            or not lineage):
        raise LookupError("provenance.lineage must contain source records")
    for index, item in enumerate(lineage):
        if (not isinstance(item, Mapping)
                or not isinstance(item.get("source"), str)
                or not item["source"].strip() or not _sha256(item.get("digest"))):
            raise LookupError(
                f"provenance.lineage[{index}] needs source and SHA-256 digest")
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _mean(values: Sequence[float], label: str) -> Dict[str, Any]:
    value = math.fsum(values) / len(values)
    standard_error = math.sqrt(
        math.fsum((x - value) ** 2 for x in values)
        / (len(values) - 1) / len(values))
    return {"value": value, "standard_error": standard_error,
            "sample_count": len(values), "fit": "arithmetic_mean"}


def _origin_fit(rows: Sequence[Mapping[str, Any]], x_name: str, y_name: str,
                label: str) -> Dict[str, Any]:
    pairs = [(_number(row.get(x_name), f"{label}.{x_name}"),
              _number(row.get(y_name), f"{label}.{y_name}")) for row in rows]
    xx = math.fsum(x * x for x, _ in pairs)
    if xx <= 0.0:
        raise ValueError(f"{label} has no non-zero excitation")
    value = math.fsum(x * y for x, y in pairs) / xx
    if value < 0.0:
        raise ValueError(f"{label} fitted a negative coefficient")
    residual = math.fsum((y - value * x) ** 2 for x, y in pairs)
    standard_error = math.sqrt(residual / (len(pairs) - 1) / xx)
    return {"value": value, "standard_error": standard_error,
            "sample_count": len(pairs),
            "fit": "least_squares_through_origin"}


def _puckering(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    ratios, heights = [], []
    for row in rows:
        length = _number(row.get("seam_length_m"),
                         "puckering.seam_length_m", positive=True)
        excess = _number(row.get("excess_path_length_m"),
                         "puckering.excess_path_length_m", nonnegative=True)
        height = _number(row.get("rms_height_m"),
                         "puckering.rms_height_m", nonnegative=True)
        ratios.append(excess / length)
        heights.append(height)
    return {"excess_length_ratio": _mean(ratios, "puckering ratio"),
            "rms_height_m": _mean(heights, "puckering height")}


def _fatigue(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    # Fit loss = rate * cycles, constrained to an observed undamaged state of 1.
    pairs = []
    for row in rows:
        cycles = _number(row.get("cycle_count"), "fatigue.cycle_count",
                         nonnegative=True)
        retained = _number(row.get("retained_strength_ratio"),
                           "fatigue.retained_strength_ratio",
                           nonnegative=True)
        if retained > 1.0:
            raise ValueError("retained_strength_ratio cannot exceed 1")
        pairs.append((cycles, 1.0 - retained))
    xx = math.fsum(x * x for x, _ in pairs)
    if xx <= 0.0:
        raise ValueError("fatigue has no non-zero cycle count")
    rate = math.fsum(x * y for x, y in pairs) / xx
    residual = math.fsum((y - rate * x) ** 2 for x, y in pairs)
    return {"value": rate,
            "standard_error": math.sqrt(residual / (len(pairs) - 1) / xx),
            "sample_count": len(pairs), "unit": "1/cycle",
            "fit": "retained_strength_loss_through_origin"}


def _breakage(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    # Basquin-style log relation: ln(cycles) = intercept - exponent*ln(force).
    points = []
    for row in rows:
        force = _number(row.get("line_force_n_m"),
                        "breakage.line_force_n_m", positive=True)
        cycles = _number(row.get("cycles_to_failure"),
                         "breakage.cycles_to_failure", positive=True)
        points.append((math.log(force), math.log(cycles)))
    x_mean = math.fsum(x for x, _ in points) / len(points)
    y_mean = math.fsum(y for _, y in points) / len(points)
    xx = math.fsum((x - x_mean) ** 2 for x, _ in points)
    if xx <= 0.0:
        raise ValueError("breakage line forces must not all be equal")
    slope = math.fsum((x - x_mean) * (y - y_mean)
                      for x, y in points) / xx
    if slope >= 0.0:
        raise ValueError("cycles to failure must decrease as force increases")
    intercept = y_mean - slope * x_mean
    residual = math.fsum((y - (intercept + slope * x)) ** 2
                         for x, y in points)
    residual_variance = residual / max(len(points) - 2, 1)
    slope_se = math.sqrt(residual_variance / xx)
    intercept_se = math.sqrt(
        residual_variance * (1.0 / len(points) + x_mean * x_mean / xx))
    reference_cycles = math.exp(intercept)
    return {
        "fatigue_exponent": {"value": -slope,
                             "standard_error": slope_se,
                             "sample_count": len(points)},
        "cycles_at_reference_force": {
            "value": reference_cycles,
            "standard_error": reference_cycles * intercept_se,
            "standard_error_log_space": intercept_se,
            "reference_line_force_n_m": 1.0,
            "sample_count": len(points)},
        "fit": "log_log_force_life_regression",
    }


def calibrate(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Calibrate measured seam response without imputing missing channels."""
    if not isinstance(record, Mapping):
        return _refusal(BAD_RECORD, "record must be an object")
    if record.get("schema") != SCHEMA:
        return _refusal(BAD_RECORD, f"schema must be {SCHEMA}")
    if not isinstance(record.get("seam_id"), str) or not record["seam_id"].strip():
        return _refusal(BAD_RECORD, "seam_id must be non-empty")
    try:
        measurement_digest = _digest(record)
        provenance = _provenance(record.get("provenance"))
    except LookupError as exc:
        return _refusal(MISSING_PROVENANCE, str(exc))
    except (TypeError, ValueError) as exc:
        return _refusal(BAD_RECORD, f"record is not canonical JSON: {exc}")
    measurements = record.get("measurements")
    if not isinstance(measurements, Mapping):
        return _refusal(BAD_RECORD, "measurements must be an object")
    missing = [name for name in _CHANNELS if name not in measurements]
    if missing:
        return _refusal(MISSING_OBSERVATION,
                        "all seam channels must be observed", missing=missing)
    try:
        coefficients = {
            "line_tensile_stiffness_n_m": _origin_fit(
                _series(measurements["tension"], "tension"), "strain",
                "line_force_n_m", "tension"),
            "slippage_stiffness_n_m2": _origin_fit(
                _series(measurements["slippage"], "slippage"), "opening_m",
                "line_force_n_m", "slippage"),
            "puckering": _puckering(
                _series(measurements["puckering"], "puckering")),
            "fatigue_strength_loss_per_cycle": _fatigue(
                _series(measurements["fatigue"], "fatigue", minimum=3)),
            "breakage_force_life": _breakage(
                _series(measurements["breakage"], "breakage", minimum=3)),
        }
    except LookupError as exc:
        return _refusal(INSUFFICIENT_SERIES, str(exc))
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        return _refusal(BAD_RECORD, str(exc))
    result = {
        "schema": "seam.calibration.v1",
        "seam_id": record["seam_id"],
        "units": "SI",
        "coefficients": coefficients,
        "uncertainty_kind": "standard_error_from_observed_repeatability",
        "measurement_digest": measurement_digest,
        "provenance": provenance,
    }
    result["calibration_digest"] = _digest(result)
    return {"verdict": ANSWER, **result}


def capabilities() -> Dict[str, Any]:
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "required_channels": list(_CHANNELS),
        "series_fields_si": {
            "tension": ["strain", "line_force_n_m"],
            "slippage": ["opening_m", "line_force_n_m"],
            "puckering": ["seam_length_m", "excess_path_length_m",
                          "rms_height_m"],
            "fatigue": ["cycle_count", "retained_strength_ratio"],
            "breakage": ["line_force_n_m", "cycles_to_failure"],
        },
        "minimum_samples": {"tension": 2, "slippage": 2, "puckering": 2,
                            "fatigue": 3, "breakage": 3},
        "fills_unobserved_channels": False,
        "deterministic": True,
        "standard_library_only": True,
    }


__all__ = ["ANSWER", "BAD_RECORD", "INSUFFICIENT_SERIES",
           "MISSING_OBSERVATION", "MISSING_PROVENANCE", "SCHEMA",
           "calibrate", "capabilities"]
