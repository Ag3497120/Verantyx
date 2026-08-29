# -*- coding: utf-8 -*-
"""Deterministic SI calibration for measured textile response series.

This module fits small, inspectable constitutive coefficients.  It does not
fill gaps with a named fabric, a learned prior, or an illustrative profile:
every required channel must be present in the supplied record.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Mapping, Sequence, Tuple


SCHEMA = "material.measurements.v1"
ANSWER = "ANSWER"
BAD_RECORD = "UNKNOWN_BAD_MATERIAL_MEASUREMENT"
MISSING_OBSERVATION = "UNKNOWN_UNOBSERVED_MATERIAL_CHANNEL"
INSUFFICIENT_SERIES = "UNKNOWN_INSUFFICIENT_MATERIAL_SERIES"
MISSING_PROVENANCE = "UNKNOWN_MATERIAL_PROVENANCE"

_DIRECTIONS = ("warp", "weft")
_REQUIRED_CHANNELS = ("tension", "shear", "bending", "friction",
                      "damping", "permeability")


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


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


def _series(value: Any, name: str, minimum: int = 2) -> Sequence[Mapping[str, Any]]:
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
        if not isinstance(item, Mapping):
            raise LookupError(f"provenance.lineage[{index}] must be an object")
        if not isinstance(item.get("source"), str) or not item["source"].strip():
            raise LookupError(f"provenance.lineage[{index}].source is required")
        digest = item.get("digest")
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest.lower())):
            raise LookupError(
                f"provenance.lineage[{index}].digest must be SHA-256")
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _origin_fit(rows: Sequence[Mapping[str, Any]], x_name: str, y_name: str,
                label: str) -> Dict[str, Any]:
    pairs = [(_number(row.get(x_name), f"{label}.{x_name}"),
              _number(row.get(y_name), f"{label}.{y_name}")) for row in rows]
    xx = math.fsum(x * x for x, _ in pairs)
    if xx <= 0.0:
        raise ValueError(f"{label} has no non-zero excitation")
    coefficient = math.fsum(x * y for x, y in pairs) / xx
    if coefficient < 0.0:
        raise ValueError(f"{label} fitted a negative physical coefficient")
    residuals = [y - coefficient * x for x, y in pairs]
    standard_error = math.sqrt(
        math.fsum(r * r for r in residuals) / (len(pairs) - 1) / xx)
    return {"value": coefficient, "standard_error": standard_error,
            "sample_count": len(pairs), "fit": "least_squares_through_origin"}


def _mean(values: Sequence[float], label: str) -> Dict[str, Any]:
    if not values:
        raise ValueError(f"{label} has no values")
    value = math.fsum(values) / len(values)
    if value < 0.0:
        raise ValueError(f"{label} fitted a negative physical coefficient")
    if len(values) == 1:
        standard_error = 0.0
    else:
        standard_error = math.sqrt(
            math.fsum((x - value) ** 2 for x in values)
            / (len(values) - 1) / len(values))
    return {"value": value, "standard_error": standard_error,
            "sample_count": len(values), "fit": "arithmetic_mean"}


def _friction(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    static, dynamic = [], []
    for row in rows:
        normal = _number(row.get("normal_force_n"),
                         "friction.normal_force_n", positive=True)
        s = _number(row.get("static_force_n"), "friction.static_force_n",
                    nonnegative=True) / normal
        d = _number(row.get("dynamic_force_n"), "friction.dynamic_force_n",
                    nonnegative=True) / normal
        if d > s:
            raise ValueError("dynamic friction cannot exceed static friction")
        static.append(s)
        dynamic.append(d)
    return {"static": _mean(static, "static friction"),
            "dynamic": _mean(dynamic, "dynamic friction")}


def _damping(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    points = []
    for row in rows:
        cycle = _number(row.get("cycle_index"), "damping.cycle_index",
                        nonnegative=True)
        amplitude = _number(row.get("amplitude"), "damping.amplitude",
                            positive=True)
        points.append((cycle, math.log(amplitude)))
    points.sort()
    if len({x for x, _ in points}) != len(points):
        raise ValueError("damping cycle_index values must be distinct")
    x_mean = math.fsum(x for x, _ in points) / len(points)
    y_mean = math.fsum(y for _, y in points) / len(points)
    xx = math.fsum((x - x_mean) ** 2 for x, _ in points)
    slope = math.fsum((x - x_mean) * (y - y_mean)
                      for x, y in points) / xx
    if slope >= 0.0:
        raise ValueError("damping amplitudes do not decay")
    residual = math.fsum((y - (y_mean + slope * (x - x_mean))) ** 2
                         for x, y in points)
    slope_se = math.sqrt(residual / max(len(points) - 2, 1) / xx)
    decrement = -slope
    denominator = math.sqrt((2.0 * math.pi) ** 2 + decrement ** 2)
    ratio = decrement / denominator
    derivative = (2.0 * math.pi) ** 2 / denominator ** 3
    return {"value": ratio, "standard_error": derivative * slope_se,
            "sample_count": len(points),
            "fit": "log_decrement_linear_regression"}


def _permeability(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    values = []
    for row in rows:
        pressure = _number(row.get("pressure_difference_pa"),
                           "permeability.pressure_difference_pa", positive=True)
        velocity = _number(row.get("flow_velocity_m_s"),
                           "permeability.flow_velocity_m_s", nonnegative=True)
        thickness = _number(row.get("thickness_m"),
                            "permeability.thickness_m", positive=True)
        viscosity = _number(row.get("dynamic_viscosity_pa_s"),
                            "permeability.dynamic_viscosity_pa_s", positive=True)
        values.append(velocity * viscosity * thickness / pressure)
    return _mean(values, "Darcy permeability")


def calibrate(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Fit SI coefficients and repeatability uncertainty from all six channels."""
    if not isinstance(record, Mapping):
        return _refusal(BAD_RECORD, "record must be an object")
    if record.get("schema") != SCHEMA:
        return _refusal(BAD_RECORD, f"schema must be {SCHEMA}")
    if not isinstance(record.get("material_id"), str) or not record["material_id"].strip():
        return _refusal(BAD_RECORD, "material_id must be non-empty")
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
    missing = [name for name in _REQUIRED_CHANNELS if name not in measurements]
    if missing:
        return _refusal(MISSING_OBSERVATION,
                        "all material channels must be observed", missing=missing)
    try:
        tension = measurements["tension"]
        bending = measurements["bending"]
        if not isinstance(tension, Mapping) or not isinstance(bending, Mapping):
            raise ValueError("tension and bending must be directional objects")
        missing_directions = [f"{kind}.{axis}" for kind, block in (
            ("tension", tension), ("bending", bending)) for axis in _DIRECTIONS
            if axis not in block]
        if missing_directions:
            return _refusal(MISSING_OBSERVATION,
                            "warp and weft observations are required",
                            missing=missing_directions)
        coefficients = {
            "tension_modulus_n_m": {
                axis: _origin_fit(_series(tension[axis], f"tension.{axis}"),
                                  "strain", "force_per_width_n_m",
                                  f"tension.{axis}") for axis in _DIRECTIONS},
            "shear_modulus_n_m": _origin_fit(
                _series(measurements["shear"], "shear"), "shear_strain",
                "force_per_width_n_m", "shear"),
            "bending_rigidity_n_m": {
                axis: _origin_fit(_series(bending[axis], f"bending.{axis}"),
                                  "curvature_1_m", "moment_n",
                                  f"bending.{axis}") for axis in _DIRECTIONS},
            "friction_coefficient": _friction(
                _series(measurements["friction"], "friction")),
            "damping_ratio": _damping(
                _series(measurements["damping"], "damping", minimum=3)),
            "permeability_m2": _permeability(
                _series(measurements["permeability"], "permeability")),
        }
    except LookupError as exc:
        return _refusal(INSUFFICIENT_SERIES, str(exc))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        return _refusal(BAD_RECORD, str(exc))

    result = {
        "schema": "material.calibration.v1",
        "material_id": record["material_id"],
        "units": "SI",
        "coefficients": coefficients,
        "uncertainty_kind": "standard_error_from_observed_repeatability",
        "provenance": provenance,
        "measurement_digest": measurement_digest,
    }
    result["calibration_digest"] = _digest(result)
    return {"verdict": ANSWER, **result}


def capabilities() -> Dict[str, Any]:
    """Describe the exact measurements accepted by :func:`calibrate`."""
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "required_channels": list(_REQUIRED_CHANNELS),
        "required_directions": {"tension": list(_DIRECTIONS),
                                "bending": list(_DIRECTIONS)},
        "series_fields_si": {
            "tension": ["strain", "force_per_width_n_m"],
            "shear": ["shear_strain", "force_per_width_n_m"],
            "bending": ["curvature_1_m", "moment_n"],
            "friction": ["normal_force_n", "static_force_n", "dynamic_force_n"],
            "damping": ["cycle_index", "amplitude"],
            "permeability": ["pressure_difference_pa", "flow_velocity_m_s",
                             "thickness_m", "dynamic_viscosity_pa_s"],
        },
        "minimum_samples": {"damping": 3, "all_other_series": 2},
        "deterministic": True,
        "fills_unobserved_channels": False,
        "standard_library_only": True,
    }


__all__ = ["ANSWER", "BAD_RECORD", "MISSING_OBSERVATION",
           "INSUFFICIENT_SERIES", "MISSING_PROVENANCE", "SCHEMA",
           "calibrate", "capabilities"]
