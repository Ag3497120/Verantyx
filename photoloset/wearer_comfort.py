# -*- coding: utf-8 -*-
"""Wearer-bound, REVIEW-only comparison of observed garment trials."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Mapping, Sequence


SCHEMA = "wearer.comfort-trials.v1"
REVIEW = "REVIEW"
BAD_RECORD = "UNKNOWN_BAD_WEARER_COMFORT_RECORD"
MISSING_OBSERVATION = "UNKNOWN_UNOBSERVED_WEARER_COMFORT_CHANNEL"
MISSING_PROVENANCE = "UNKNOWN_WEARER_COMFORT_PROVENANCE"
MISSING_CALIBRATION = "UNKNOWN_MATERIAL_CALIBRATION"
INSUFFICIENT_COMPARISON = "UNKNOWN_INSUFFICIENT_WEARER_TRIALS"

_BODY_FIELDS = ("stature_m", "mass_kg", "chest_circumference_m",
                "waist_circumference_m", "hip_circumference_m")
_ACTIVITY_FIELDS = ("activity_type", "metabolic_rate_w_m2", "duration_s")
_ENVIRONMENT_FIELDS = ("air_temperature_k", "radiant_temperature_k",
                       "relative_humidity", "air_velocity_m_s")
_CONTACT_FIELDS = ("region", "pressure_pa", "contact_time_s",
                   "skin_temperature_k", "microclimate_temperature_k",
                   "microclimate_relative_humidity", "heat_flux_w_m2")


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


def _observed_range(values: Sequence[float], unit: str) -> Dict[str, Any]:
    return {"minimum": min(values), "maximum": max(values), "unit": unit,
            "sample_count": len(values)}


def _parse_anthropometry(value: Any) -> Dict[str, float]:
    if not isinstance(value, Mapping):
        raise LookupError("anthropometry must be an object")
    missing = [field for field in _BODY_FIELDS if field not in value]
    if missing:
        raise LookupError("anthropometry missing: " + ", ".join(missing))
    limits = {
        "stature_m": (0.30, 3.0), "mass_kg": (1.0, 500.0),
        "chest_circumference_m": (0.10, 3.0),
        "waist_circumference_m": (0.10, 3.0),
        "hip_circumference_m": (0.10, 3.0),
    }
    return {field: _number(value[field], f"anthropometry.{field}", *limits[field])
            for field in _BODY_FIELDS}


def _parse_trial(value: Mapping[str, Any]) -> Dict[str, Any]:
    trial_id = value.get("trial_id")
    if not isinstance(trial_id, str) or not trial_id.strip():
        raise ValueError("trial_id must be non-empty")
    activity, environment = value.get("activity"), value.get("environment")
    if not isinstance(activity, Mapping) or not isinstance(environment, Mapping):
        raise LookupError(f"trial {trial_id} needs activity and environment")
    missing = ([f"activity.{x}" for x in _ACTIVITY_FIELDS if x not in activity]
               + [f"environment.{x}" for x in _ENVIRONMENT_FIELDS
                  if x not in environment])
    contacts = value.get("contact_observations")
    if (not isinstance(contacts, Sequence) or isinstance(contacts, (str, bytes))
            or not contacts or any(not isinstance(row, Mapping)
                                   for row in contacts)):
        raise LookupError(f"trial {trial_id} needs contact observations")
    missing.extend(f"contact.{field}" for row in contacts
                   for field in _CONTACT_FIELDS if field not in row)
    if missing:
        raise LookupError(f"trial {trial_id} missing: " + ", ".join(sorted(set(missing))))
    if (not isinstance(activity["activity_type"], str)
            or not activity["activity_type"].strip()):
        raise ValueError("activity_type must be non-empty")
    parsed_activity = {
        "activity_type": activity["activity_type"],
        "metabolic_rate_w_m2": _number(activity["metabolic_rate_w_m2"],
                                         "metabolic_rate_w_m2", 0.0, 2000.0),
        "duration_s": _number(activity["duration_s"], "duration_s",
                              0.0, 31_536_000.0),
    }
    parsed_environment = {
        "air_temperature_k": _number(environment["air_temperature_k"],
                                      "air_temperature_k", 150.0, 400.0),
        "radiant_temperature_k": _number(environment["radiant_temperature_k"],
                                          "radiant_temperature_k", 150.0, 400.0),
        "relative_humidity": _number(environment["relative_humidity"],
                                     "environment.relative_humidity", 0.0, 1.0),
        "air_velocity_m_s": _number(environment["air_velocity_m_s"],
                                    "air_velocity_m_s", 0.0, 100.0),
    }
    parsed_contacts = []
    for row in contacts:
        if not isinstance(row["region"], str) or not row["region"].strip():
            raise ValueError("contact region must be non-empty")
        parsed_contacts.append({
            "region": row["region"],
            "pressure_pa": _number(row["pressure_pa"], "pressure_pa", 0.0, 1e7),
            "contact_time_s": _number(row["contact_time_s"], "contact_time_s",
                                      0.0, 31_536_000.0),
            "skin_temperature_k": _number(row["skin_temperature_k"],
                                           "skin_temperature_k", 250.0, 350.0),
            "microclimate_temperature_k": _number(
                row["microclimate_temperature_k"],
                "microclimate_temperature_k", 150.0, 400.0),
            "microclimate_relative_humidity": _number(
                row["microclimate_relative_humidity"],
                "microclimate_relative_humidity", 0.0, 1.0),
            "heat_flux_w_m2": _number(row["heat_flux_w_m2"],
                                      "heat_flux_w_m2", -5000.0, 5000.0),
        })
    return {"trial_id": trial_id, "activity": parsed_activity,
            "environment": parsed_environment, "contacts": parsed_contacts}


def _summarise(trial: Mapping[str, Any]) -> Dict[str, Any]:
    contacts = trial["contacts"]
    pressure = [row["pressure_pa"] for row in contacts]
    exposure = [row["pressure_pa"] * row["contact_time_s"] for row in contacts]
    micro_temp = [row["microclimate_temperature_k"] for row in contacts]
    humidity = [row["microclimate_relative_humidity"] for row in contacts]
    heat_flux = [row["heat_flux_w_m2"] for row in contacts]
    proxy = []
    for row in contacts:
        pressure_term = min(row["pressure_pa"] / 10_000.0, 1.0)
        time_term = min(row["contact_time_s"] / 14_400.0, 1.0)
        thermal_term = min(abs(row["microclimate_temperature_k"]
                               - row["skin_temperature_k"]) / 8.0, 1.0)
        moisture_term = min(abs(row["microclimate_relative_humidity"]
                                - 0.50) / 0.50, 1.0)
        flux_term = min(abs(row["heat_flux_w_m2"]) / 200.0, 1.0)
        proxy.append(0.30 * pressure_term + 0.15 * time_term
                     + 0.20 * thermal_term + 0.20 * moisture_term
                     + 0.15 * flux_term)
    mean_proxy = math.fsum(proxy) / len(proxy)
    return {
        "trial_id": trial["trial_id"],
        "ranges": {
            "contact_pressure": _observed_range(pressure, "Pa"),
            "pressure_time_exposure": _observed_range(exposure, "Pa*s"),
            "microclimate_temperature": _observed_range(micro_temp, "K"),
            "microclimate_relative_humidity": _observed_range(humidity, "1"),
            "heat_flux": _observed_range(heat_flux, "W/m2"),
            "engineering_discomfort_proxy": _observed_range(proxy, "1"),
        },
        "mean_engineering_discomfort_proxy": mean_proxy,
    }


def evaluate(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare trials for one wearer; successful output is always REVIEW."""
    if not isinstance(record, Mapping):
        return _refusal(BAD_RECORD, "record must be an object")
    if record.get("schema") != SCHEMA:
        return _refusal(BAD_RECORD, f"schema must be {SCHEMA}")
    if not isinstance(record.get("wearer_id"), str) or not record["wearer_id"].strip():
        return _refusal(BAD_RECORD, "wearer_id must be non-empty")
    if not _sha256(record.get("material_calibration_digest")):
        return _refusal(MISSING_CALIBRATION,
                        "material_calibration_digest must be SHA-256")
    try:
        observation_digest = _digest(record)
        provenance = _provenance(record.get("provenance"))
    except LookupError as exc:
        return _refusal(MISSING_PROVENANCE, str(exc))
    except (TypeError, ValueError) as exc:
        return _refusal(BAD_RECORD, f"record is not canonical JSON: {exc}")
    trials = record.get("trials")
    if (not isinstance(trials, Sequence) or isinstance(trials, (str, bytes))):
        return _refusal(MISSING_OBSERVATION, "trials must be a list")
    if len(trials) < 2:
        return _refusal(INSUFFICIENT_COMPARISON,
                        "personal comparison requires at least two trials")
    if any(not isinstance(trial, Mapping) for trial in trials):
        return _refusal(BAD_RECORD, "every trial must be an object")
    try:
        anthropometry = _parse_anthropometry(record.get("anthropometry"))
        parsed = [_parse_trial(trial) for trial in trials]
    except LookupError as exc:
        return _refusal(MISSING_OBSERVATION, str(exc))
    except ValueError as exc:
        return _refusal(BAD_RECORD, str(exc))
    ids = [trial["trial_id"] for trial in parsed]
    if len(set(ids)) != len(ids):
        return _refusal(BAD_RECORD, "trial_id values must be unique")
    parsed.sort(key=lambda trial: trial["trial_id"])
    summaries = [_summarise(trial) for trial in parsed]
    comparisons = []
    for left_index, left in enumerate(summaries):
        for right in summaries[left_index + 1:]:
            comparisons.append({
                "left_trial_id": left["trial_id"],
                "right_trial_id": right["trial_id"],
                "right_minus_left_proxy": (
                    right["mean_engineering_discomfort_proxy"]
                    - left["mean_engineering_discomfort_proxy"]),
                "interpretation": "directional engineering delta; human review required",
            })
    controls = [{"activity": trial["activity"],
                 "environment": trial["environment"]} for trial in parsed]
    controls_match = all(item == controls[0] for item in controls[1:])
    result = {
        "verdict": REVIEW,
        "schema": "wearer.comfort-review.v1",
        "wearer_id": record["wearer_id"],
        "material_calibration_digest": record["material_calibration_digest"],
        "observation_digest": observation_digest,
        "anthropometry_si": anthropometry,
        "trial_summaries": summaries,
        "comparisons": comparisons,
        "comparison_controls_match": controls_match,
        "review_reasons": [
            "result applies only to the recorded wearer and conditions",
            "different activity or environment confounds comparison"
            if not controls_match else "matching controls do not establish safety",
            "human review is required",
        ],
        "medical_safety_claim": False,
        "population_generalization": False,
        "provenance": provenance,
        "assumptions": {"proxy_is_not_a_clinical_threshold": True},
    }
    result["evaluation_digest"] = _digest(result)
    return result


def capabilities() -> Dict[str, Any]:
    return {
        "verdict": "ANSWER",
        "schema": SCHEMA,
        "minimum_trials": 2,
        "required_anthropometry_si": list(_BODY_FIELDS),
        "required_activity_fields": list(_ACTIVITY_FIELDS),
        "required_environment_fields": list(_ENVIRONMENT_FIELDS),
        "required_contact_fields": list(_CONTACT_FIELDS),
        "required_binding": ["wearer_id", "material_calibration_digest",
                             "provenance.lineage"],
        "possible_success_verdicts": [REVIEW],
        "medical_safety_claim": False,
        "population_generalization": False,
        "deterministic": True,
        "standard_library_only": True,
    }


__all__ = ["BAD_RECORD", "INSUFFICIENT_COMPARISON",
           "MISSING_CALIBRATION", "MISSING_OBSERVATION",
           "MISSING_PROVENANCE", "REVIEW", "SCHEMA", "capabilities",
           "evaluate"]
