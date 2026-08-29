# -*- coding: utf-8 -*-
"""Typed, non-medical comfort screening from observed physical conditions."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Mapping, Sequence


SCHEMA = "garment.comfort-observations.v1"
REVIEW = "REVIEW"
BAD_RECORD = "UNKNOWN_BAD_COMFORT_OBSERVATION"
MISSING_OBSERVATION = "UNKNOWN_UNOBSERVED_COMFORT_CHANNEL"
MISSING_PROVENANCE = "UNKNOWN_COMFORT_PROVENANCE"
MISSING_CALIBRATION = "UNKNOWN_MATERIAL_CALIBRATION"

_FIELDS = ("pressure_pa", "contact_time_s", "air_velocity_m_s",
           "temperature_k", "relative_humidity")


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def _sha256(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value.lower()))


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return result


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


def _range(values: Sequence[float], unit: str) -> Dict[str, Any]:
    return {"minimum": min(values), "maximum": max(values), "unit": unit,
            "sample_count": len(values)}


def evaluate(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Return observed ranges and a REVIEW-only engineering proxy.

    The proxy is useful for comparing two simulations under the same declared
    assumptions.  It is not a diagnosis, injury threshold, or medical safety
    decision and is intentionally never returned as PASS or SAFE.
    """
    if not isinstance(record, Mapping):
        return _refusal(BAD_RECORD, "record must be an object")
    if record.get("schema") != SCHEMA:
        return _refusal(BAD_RECORD, f"schema must be {SCHEMA}")
    calibration_digest = record.get("calibration_digest")
    if not _sha256(calibration_digest):
        return _refusal(MISSING_CALIBRATION,
                        "calibration_digest must identify an SI material calibration")
    try:
        observation_digest = _digest(record)
        provenance = _provenance(record.get("provenance"))
    except LookupError as exc:
        return _refusal(MISSING_PROVENANCE, str(exc))
    except (TypeError, ValueError) as exc:
        return _refusal(BAD_RECORD, f"record is not canonical JSON: {exc}")
    observations = record.get("observations")
    if (not isinstance(observations, Sequence)
            or isinstance(observations, (str, bytes)) or not observations
            or any(not isinstance(row, Mapping) for row in observations)):
        return _refusal(MISSING_OBSERVATION,
                        "observations must contain at least one complete sample")
    missing = sorted({field for row in observations for field in _FIELDS
                      if field not in row})
    if missing:
        return _refusal(MISSING_OBSERVATION,
                        "every comfort channel must be observed in every sample",
                        missing=missing)
    limits = {
        "pressure_pa": (0.0, 1.0e7),
        "contact_time_s": (0.0, 31_536_000.0),
        "air_velocity_m_s": (0.0, 100.0),
        "temperature_k": (150.0, 400.0),
        "relative_humidity": (0.0, 1.0),
    }
    try:
        samples = [{field: _number(row[field], field, *limits[field])
                    for field in _FIELDS} for row in observations]
    except ValueError as exc:
        return _refusal(BAD_RECORD, str(exc))

    pressure = [row["pressure_pa"] for row in samples]
    duration = [row["contact_time_s"] for row in samples]
    ventilation = [row["air_velocity_m_s"] for row in samples]
    temperature = [row["temperature_k"] for row in samples]
    humidity = [row["relative_humidity"] for row in samples]
    pressure_dose = [row["pressure_pa"] * row["contact_time_s"]
                     for row in samples]

    # Dimensionless, bounded comparison proxy.  The declared reference values
    # are engineering assumptions, not clinical cutoffs.
    proxy = []
    for row in samples:
        p = min(row["pressure_pa"] / 10_000.0, 1.0)
        t = min(row["contact_time_s"] / 14_400.0, 1.0)
        still_air = 1.0 - min(row["air_velocity_m_s"] / 0.30, 1.0)
        thermal = min(abs(row["temperature_k"] - 295.15) / 8.0, 1.0)
        moisture = min(abs(row["relative_humidity"] - 0.50) / 0.50, 1.0)
        proxy.append(0.30 * p + 0.15 * t + 0.20 * still_air
                     + 0.20 * thermal + 0.15 * moisture)

    ranges = {
        "pressure": _range(pressure, "Pa"),
        "contact_time": _range(duration, "s"),
        "ventilation_air_velocity": _range(ventilation, "m/s"),
        "temperature": _range(temperature, "K"),
        "relative_humidity": _range(humidity, "1"),
        "pressure_time_exposure": _range(pressure_dose, "Pa*s"),
        "engineering_discomfort_proxy": _range(proxy, "1"),
    }
    result = {
        "verdict": REVIEW,
        "schema": "garment.comfort-review.v1",
        "calibration_digest": calibration_digest,
        "observation_digest": observation_digest,
        "ranges": ranges,
        "review_reasons": [
            "comfort varies by person, fit, activity, duration, and environment",
            "engineering proxy requires human review",
        ],
        "medical_safety_claim": False,
        "allowed_use": "comparative engineering screening under identical assumptions",
        "provenance": provenance,
        "assumptions": {
            "reference_temperature_k": 295.15,
            "reference_air_velocity_m_s": 0.30,
            "proxy_is_not_a_clinical_threshold": True,
        },
    }
    result["evaluation_digest"] = _digest(result)
    return result


def capabilities() -> Dict[str, Any]:
    return {
        "verdict": "ANSWER",
        "schema": SCHEMA,
        "required_observation_fields": list(_FIELDS),
        "required_binding": ["calibration_digest", "provenance.lineage"],
        "outputs": ["observed SI ranges", "engineering comparison proxy", "REVIEW"],
        "possible_success_verdicts": [REVIEW],
        "medical_safety_claim": False,
        "deterministic": True,
        "standard_library_only": True,
    }


__all__ = ["BAD_RECORD", "MISSING_CALIBRATION", "MISSING_OBSERVATION",
           "MISSING_PROVENANCE", "REVIEW", "SCHEMA", "capabilities", "evaluate"]
