# -*- coding: utf-8 -*-
"""Complete a small vision-model parts proposal into structure candidates.

This is an authority boundary, not an image measurement system.  The input is
already interpreted by a model and every output remains ``PROPOSED``.  Missing
primitive dimensions are completed from either caller-supplied mannequin
measurements or an explicitly selected, bounded preview-mannequin profile.
Pixel coordinates and visible proportions are never relabelled as centimetres.

Two input shapes are accepted::

    {"parts": [...], "candidate_count": 2}

or::

    {"candidates": [{"candidate_id": "a", "parts": [...]}, ...]}

The first form deliberately expands one parts template into bounded ease
variants.  The second form represents alternatives already proposed by the
vision model and therefore refuses fewer than two candidates rather than
silently duplicating one.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .front_structure_hypotheses import _DEFAULT_MEASUREMENTS
from . import ornament_primitives
from .garment_structure import (
    ANSWER,
    PrimitiveKind,
    PrimitiveNode,
    StructureGraph,
    _REQUIRED_DIMENSIONS,
    semantic_digest,
    validate_structure,
)


SCHEMA = "garment.parts-ir.v1"
RESULT_SCHEMA = "garment.parts-ir.completion.v1"
ORNAMENT_ARTIFACT_SCHEMA = "garment.parts-ir.ornament-artifacts.v1"
PROPOSED = "PROPOSED"


# The first eight values are reused directly from front_structure_hypotheses.
# Additional values only support primitive kinds that the front hypothesis
# module does not currently emit.  They are preview values, not population
# averages, sizing standards, or measurements inferred from an image.
_PREVIEW_VALUES_CM: Dict[str, float] = {
    **_DEFAULT_MEASUREMENTS,
    "neck_circumference_cm": 38.0,
    "head_height_cm": 36.0,
    "head_width_cm": 31.0,
    "head_depth_cm": 24.0,
    "shoulder_width_cm": 40.0,
}

_PREVIEW_BOUNDS_CM: Dict[str, Tuple[float, float]] = {
    "upper_height_cm": (20.0, 80.0),
    "body_circumference_cm": (45.0, 220.0),
    "waist_circumference_cm": (35.0, 200.0),
    "lower_length_cm": (10.0, 160.0),
    "hem_circumference_cm": (40.0, 500.0),
    "sleeve_length_cm": (5.0, 110.0),
    "upper_arm_circumference_cm": (10.0, 100.0),
    "cuff_circumference_cm": (5.0, 80.0),
    "neck_circumference_cm": (15.0, 90.0),
    "head_height_cm": (15.0, 55.0),
    "head_width_cm": (12.0, 50.0),
    "head_depth_cm": (10.0, 45.0),
    "shoulder_width_cm": (18.0, 80.0),
}

_MEASUREMENT_ALIASES = {
    "body_length_cm": "upper_height_cm",
    "body_length": "upper_height_cm",
    "chest_cm": "body_circumference_cm",
    "chest": "body_circumference_cm",
    "bust_cm": "body_circumference_cm",
    "bust": "body_circumference_cm",
    "waist_cm": "waist_circumference_cm",
    "waist": "waist_circumference_cm",
    "skirt_length_cm": "lower_length_cm",
    "sleeve_cm": "sleeve_length_cm",
    "upper_arm_cm": "upper_arm_circumference_cm",
    "cuff_cm": "cuff_circumference_cm",
    "neck_cm": "neck_circumference_cm",
}

_VARIANTS = (
    {"variant_id": "balanced", "ease": 1.04, "length": 1.00,
     "flare": 1.00},
    {"variant_id": "relaxed", "ease": 1.12, "length": 1.03,
     "flare": 1.12},
    {"variant_id": "close", "ease": 1.00, "length": 0.97,
     "flare": 0.92},
    {"variant_id": "expanded", "ease": 1.18, "length": 1.06,
     "flare": 1.25},
)

_PART_SEMANTIC_FIELDS = (
    "garment_unit", "attached_to", "side", "shape", "detail_role",
    "quantity", "closure_detail", "opening_topology", "attachment_relation",
    "waist_join_mode", "waist_join_state", "waist_join_provenance",
    "owner_node_id", "ownership_state", "layer_role", "attachment_port",
    "waist_stack_state", "waist_stack_parent", "waist_stack_id",
    "waist_stack_order", "waist_stack_construction_mode",
    "waist_stack_role",
)


class _Refusal(Exception):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "state": "UNKNOWN",
        "why": why,
        "how_to_close": (
            "supply at least two PROPOSED parts candidates and explicit, finite "
            "model dimensions, target mannequin measurements, or a bounded "
            "preview mannequin profile"
        ),
        **detail,
    }


def bounded_preview_profile() -> Dict[str, Any]:
    """Return the explicit profile matching the existing front-view defaults.

    Passing this object to :func:`complete_parts_ir` is an explicit choice to
    make preview geometry.  The values must be replaced or approved elsewhere
    before a manufacturing claim can be made.
    """
    return {
        "profile_id": "front-structure-bounded-preview-v1",
        "state": PROPOSED,
        "values_cm": copy.deepcopy(_PREVIEW_VALUES_CM),
        "bounds_cm": {
            name: [bounds[0], bounds[1]]
            for name, bounds in _PREVIEW_BOUNDS_CM.items()
        },
        "basis": (
            "bounded preview-mannequin defaults aligned with "
            "front_structure_hypotheses; not measured from the image"
        ),
        "breaks_when": (
            "calibrated target-wearer or mannequin measurements are supplied"
        ),
        "not_measured_from_image": True,
    }


def required_dimensions() -> Dict[str, Tuple[str, ...]]:
    """Expose the current structure schema's required dimensions read-only."""
    return {kind.value: tuple(names)
            for kind, names in _REQUIRED_DIMENSIONS.items()}


def _number(value: Any, *, code: str, field: str,
            coordinate: bool = False) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value))):
        raise _Refusal(code, f"{field} must be a finite number", field=field)
    number = float(value)
    if not coordinate and number <= 0.0:
        raise _Refusal(code, f"{field} must be positive", field=field,
                       value=number)
    if coordinate:
        if abs(number) > 1000.0:
            raise _Refusal("UNKNOWN_PARTS_IR_DIMENSION_OUT_OF_RANGE",
                           f"{field} exceeds the bounded preview range",
                           field=field, value=number)
    elif number > 1000.0:
        raise _Refusal("UNKNOWN_PARTS_IR_DIMENSION_OUT_OF_RANGE",
                       f"{field} exceeds the bounded preview range",
                       field=field, value=number)
    return number


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _Refusal("UNKNOWN_PARTS_IR_NOT_JSON",
                       f"{field} must contain finite JSON values",
                       field=field, error=str(exc)) from exc
    return copy.deepcopy(value)


def _proposal_state(value: Any, *, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or value.upper() != PROPOSED:
        raise _Refusal(
            "UNKNOWN_PARTS_IR_AUTHORITY_ESCALATION",
            f"{field} may only claim PROPOSED authority",
            field=field, claimed_state=value,
        )


def _visible_basis(value: Any, *, part_id: str) -> Dict[str, Any]:
    if isinstance(value, str):
        if not value.strip():
            raise _Refusal("UNKNOWN_PARTS_IR_VISIBLE_BASIS",
                           f"{part_id}.visible_basis must not be empty",
                           part_id=part_id)
        return {
            "state": PROPOSED,
            "basis": value.strip(),
            "breaks_when": (
                "the image interpretation is revised or another view "
                "contradicts this proposed part"
            ),
        }
    if not isinstance(value, Mapping) or not value:
        raise _Refusal("UNKNOWN_PARTS_IR_VISIBLE_BASIS",
                       f"{part_id}.visible_basis must be a string or object",
                       part_id=part_id)
    for key in ("state", "authority", "verdict"):
        if key in value:
            _proposal_state(value[key], field=f"{part_id}.visible_basis.{key}")
    basis = value.get("basis", value.get("description", value.get("source")))
    if not isinstance(basis, str) or not basis.strip():
        raise _Refusal("UNKNOWN_PARTS_IR_VISIBLE_BASIS",
                       f"{part_id}.visible_basis needs basis/description/source",
                       part_id=part_id)
    breaks_when = value.get(
        "breaks_when",
        "the image interpretation is revised or another view contradicts this proposed part",
    )
    if not isinstance(breaks_when, str) or not breaks_when.strip():
        raise _Refusal("UNKNOWN_PARTS_IR_VISIBLE_BASIS",
                       f"{part_id}.visible_basis.breaks_when must not be empty",
                       part_id=part_id)
    preserved = _json_copy(dict(value), field=f"{part_id}.visible_basis")
    preserved["state"] = PROPOSED
    preserved["basis"] = basis.strip()
    preserved["breaks_when"] = breaks_when.strip()
    preserved["not_measured_from_image"] = True
    return preserved


def _measurement_entry(name: str, raw: Any, *, source: str,
                       default_basis: str,
                       default_breaks_when: str,
                       allow_observed_source: bool = False) -> Dict[str, Any]:
    source_was_observed = False
    if isinstance(raw, Mapping):
        raw_state = raw.get("state")
        if raw_state is not None:
            if (allow_observed_source and isinstance(raw_state, str)
                    and raw_state.upper() == "OBSERVED"):
                source_was_observed = True
            else:
                _proposal_state(raw_state, field=f"measurement.{name}.state")
        value = raw.get("value", raw.get("value_cm"))
        basis = raw.get("basis", default_basis)
        breaks_when = raw.get("breaks_when", default_breaks_when)
    else:
        value = raw
        basis = default_basis
        breaks_when = default_breaks_when
    number = _number(value, code="UNKNOWN_PARTS_IR_INVALID_MEASUREMENT",
                     field=name)
    if not isinstance(basis, str) or not basis.strip():
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_MEASUREMENT",
                       f"{name} needs a non-empty basis", measurement=name)
    if not isinstance(breaks_when, str) or not breaks_when.strip():
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_MEASUREMENT",
                       f"{name} needs a non-empty breaks_when", measurement=name)
    return {
        "value_cm": number,
        "state": PROPOSED,
        "dimension_source": source,
        "basis": basis.strip(),
        "breaks_when": breaks_when.strip(),
        "not_measured_from_image": True,
        "source_measurement_was_observed": source_was_observed,
    }


def _target_metrics(target: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if target is None:
        return {}
    if not isinstance(target, Mapping) or not target:
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_TARGET_MEASUREMENTS",
                       "target_measurements must be a non-empty object")
    raw_values = target.get("values_cm", target.get("measurements_cm", target))
    if not isinstance(raw_values, Mapping) or not raw_values:
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_TARGET_MEASUREMENTS",
                       "target_measurements needs values_cm or measurement keys")
    source_id = target.get("source_id", "caller-supplied-target-mannequin")
    if not isinstance(source_id, str) or not source_id.strip():
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_TARGET_MEASUREMENTS",
                       "target measurement source_id must be non-empty")
    result: Dict[str, Dict[str, Any]] = {}
    for raw_name, raw in raw_values.items():
        name = _MEASUREMENT_ALIASES.get(str(raw_name), str(raw_name))
        if name not in _PREVIEW_VALUES_CM:
            continue
        entry = _measurement_entry(
            name, raw, source="TARGET_MANNEQUIN_MEASUREMENT",
            default_basis=(
                f"explicit target mannequin measurement {raw_name} from {source_id}; "
                "not inferred from image pixels"
            ),
            default_breaks_when=(
                f"the target mannequin measurement {raw_name} is corrected or recalibrated"
            ),
            allow_observed_source=True,
        )
        previous = result.get(name)
        if previous is not None and previous["value_cm"] != entry["value_cm"]:
            raise _Refusal("UNKNOWN_PARTS_IR_CONFLICTING_MEASUREMENT",
                           f"aliases for {name} disagree", measurement=name)
        result[name] = entry
    if not result:
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_TARGET_MEASUREMENTS",
                       "no recognised target mannequin measurements were supplied")
    return result


def _profile_metrics(profile: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if profile is None:
        return {}
    if not isinstance(profile, Mapping) or not profile:
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_PREVIEW_PROFILE",
                       "preview_profile must be a non-empty object")
    _proposal_state(profile.get("state"), field="preview_profile.state")
    profile_id = profile.get("profile_id")
    values = profile.get("values_cm", profile.get("measurements_cm"))
    bounds = profile.get("bounds_cm")
    if (not isinstance(profile_id, str) or not profile_id.strip()
            or not isinstance(values, Mapping) or not values
            or not isinstance(bounds, Mapping) or not bounds):
        raise _Refusal(
            "UNKNOWN_PARTS_IR_INVALID_PREVIEW_PROFILE",
            "preview_profile needs profile_id, values_cm, and bounds_cm",
        )
    default_basis = profile.get(
        "basis", f"explicit bounded preview mannequin profile {profile_id}")
    default_breaks = profile.get(
        "breaks_when", "target mannequin measurements replace this preview profile")
    result: Dict[str, Dict[str, Any]] = {}
    for raw_name, raw in values.items():
        name = _MEASUREMENT_ALIASES.get(str(raw_name), str(raw_name))
        if name not in _PREVIEW_VALUES_CM:
            continue
        raw_bounds = bounds.get(raw_name, bounds.get(name))
        if (not isinstance(raw_bounds, Sequence)
                or isinstance(raw_bounds, (str, bytes))
                or len(raw_bounds) != 2):
            raise _Refusal("UNKNOWN_PARTS_IR_UNBOUNDED_PREVIEW_VALUE",
                           f"{raw_name} lacks a [min, max] preview bound",
                           measurement=str(raw_name))
        lo = _number(raw_bounds[0], code="UNKNOWN_PARTS_IR_INVALID_PREVIEW_BOUND",
                     field=f"{raw_name}.min")
        hi = _number(raw_bounds[1], code="UNKNOWN_PARTS_IR_INVALID_PREVIEW_BOUND",
                     field=f"{raw_name}.max")
        if lo > hi:
            raise _Refusal("UNKNOWN_PARTS_IR_INVALID_PREVIEW_BOUND",
                           f"{raw_name} has min greater than max",
                           measurement=str(raw_name))
        entry = _measurement_entry(
            name, raw, source="BOUNDED_PREVIEW_MANNEQUIN_VALUE",
            default_basis=str(default_basis),
            default_breaks_when=str(default_breaks),
        )
        if not lo <= entry["value_cm"] <= hi:
            raise _Refusal("UNKNOWN_PARTS_IR_PREVIEW_VALUE_OUT_OF_BOUNDS",
                           f"{raw_name} falls outside its explicit bounds",
                           measurement=str(raw_name), value_cm=entry["value_cm"],
                           bounds_cm=[lo, hi])
        entry["profile_id"] = profile_id
        entry["bounds_cm"] = [lo, hi]
        result[name] = entry
    if not result:
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_PREVIEW_PROFILE",
                       "preview profile has no recognised mannequin values")
    return result


def _metrics(target: Optional[Mapping[str, Any]],
             profile: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    # An explicit target wins per metric; an explicit preview profile can fill
    # target fields that were not measured.  Each derived dimension records the
    # exact mixture rather than flattening both sources into one authority.
    preview = _profile_metrics(profile)
    target_values = _target_metrics(target)
    return {**preview, **target_values}


def _need(metrics: Mapping[str, Dict[str, Any]], *names: str
          ) -> Tuple[List[float], List[Dict[str, Any]]]:
    missing = [name for name in names if name not in metrics]
    if missing:
        raise _Refusal(
            "UNKNOWN_PARTS_IR_MEASUREMENTS_MISSING",
            "the selected mannequin source cannot complete a required dimension",
            missing=missing,
        )
    entries = [metrics[name] for name in names]
    return [float(entry["value_cm"]) for entry in entries], entries


def _placement_text(placement: Any) -> str:
    return json.dumps(placement, ensure_ascii=False, sort_keys=True).lower()


def _derived_for(kind: PrimitiveKind, metrics: Mapping[str, Dict[str, Any]],
                 placement: Any, variant: Mapping[str, Any],
                 needed: Sequence[str]
                 ) -> Dict[str, Tuple[float, str, Tuple[str, ...], List[Dict[str, Any]]]]:
    ease = float(variant["ease"])
    length_scale = float(variant["length"])
    flare_scale = float(variant["flare"])
    placed = _placement_text(placement)

    needed_names = set(needed)

    def one(output: str, names: Tuple[str, ...], formula: str,
            calculate: Any) -> Optional[Tuple[str, Tuple[float, str, Tuple[str, ...], List[Dict[str, Any]]]]]:
        if output not in needed_names:
            return None
        values, entries = _need(metrics, *names)
        return output, (round(float(calculate(*values)), 6), formula, names, entries)

    rows: List[Optional[Tuple[str, Tuple[float, str, Tuple[str, ...], List[Dict[str, Any]]]]]] = []
    if kind is PrimitiveKind.BODY_SHELL:
        rows = [
            one("height_cm", ("upper_height_cm",), "upper_height * variant.length",
                lambda height: height * length_scale),
            one("circumference_cm", ("body_circumference_cm",),
                "body_circumference * variant.ease", lambda circumference: circumference * ease),
        ]
    elif kind is PrimitiveKind.TUBE:
        circumference_metric = ("upper_arm_circumference_cm"
                                  if "arm" in placed else "waist_circumference_cm")
        length_metric = "sleeve_length_cm" if "arm" in placed else "lower_length_cm"
        rows = [
            one("length_cm", (length_metric,), f"{length_metric} * variant.length",
                lambda length: length * length_scale),
            one("circumference_cm", (circumference_metric,),
                f"{circumference_metric} * variant.ease",
                lambda circumference: circumference * ease),
        ]
    elif kind in (PrimitiveKind.FRUSTUM, PrimitiveKind.FLARE):
        rows = [
            one("height_cm", ("lower_length_cm",),
                "lower_length * variant.length", lambda height: height * length_scale),
            one("top_circumference_cm", ("waist_circumference_cm",),
                "waist_circumference * variant.ease", lambda circumference: circumference * ease),
            one("bottom_circumference_cm", ("hem_circumference_cm",),
                "hem_circumference * variant.flare",
                lambda circumference: circumference * flare_scale),
        ]
    elif kind is PrimitiveKind.GORE:
        rows = [
            one("length_cm", ("lower_length_cm",),
                "lower_length * variant.length", lambda length: length * length_scale),
            one("top_width_cm", ("waist_circumference_cm",),
                "waist_circumference / 8 * variant.ease",
                lambda circumference: circumference / 8.0 * ease),
            one("bottom_width_cm", ("hem_circumference_cm",),
                "hem_circumference / 8 * variant.flare",
                lambda circumference: circumference / 8.0 * flare_scale),
        ]
    elif kind is PrimitiveKind.GUSSET:
        rows = [
            one("length_cm", ("lower_length_cm",), "lower_length * 0.29",
                lambda length: length * 0.29),
            one("width_cm", ("waist_circumference_cm",), "waist_circumference * 0.108",
                lambda circumference: circumference * 0.108),
        ]
    elif kind is PrimitiveKind.YOKE:
        rows = [
            one("height_cm", ("upper_height_cm",), "upper_height * 0.25",
                lambda height: height * 0.25),
            one("width_cm", ("body_circumference_cm",), "body_circumference * 0.46",
                lambda circumference: circumference * 0.46),
        ]
    elif kind is PrimitiveKind.COLLAR:
        rows = [
            one("length_cm", ("neck_circumference_cm",),
                "neck_circumference * variant.ease",
                lambda circumference: circumference * ease),
            one("width_cm", ("upper_height_cm",), "upper_height * 0.17",
                lambda height: height * 0.17),
        ]
    elif kind is PrimitiveKind.HOOD:
        rows = [
            one("height_cm", ("head_height_cm",), "head_height * 1.05",
                lambda height: height * 1.05),
            one("width_cm", ("head_width_cm",), "head_width * 1.15",
                lambda width: width * 1.15),
            one("depth_cm", ("head_depth_cm",), "head_depth * 1.15",
                lambda depth: depth * 1.15),
        ]
    elif kind is PrimitiveKind.SLEEVE:
        rows = [
            one("length_cm", ("sleeve_length_cm",),
                "sleeve_length * variant.length", lambda length: length * length_scale),
            one("upper_circumference_cm", ("upper_arm_circumference_cm",),
                "upper_arm_circumference * variant.ease",
                lambda circumference: circumference * ease),
            one("cuff_circumference_cm", ("cuff_circumference_cm",),
                "cuff_circumference * variant.ease",
                lambda circumference: circumference * ease),
        ]
    elif kind is PrimitiveKind.BAND:
        if "cuff" in placed or "wrist" in placed:
            loop_metric = "cuff_circumference_cm"
        elif "neck" in placed or "collar" in placed:
            loop_metric = "neck_circumference_cm"
        elif "hem" in placed:
            loop_metric = "hem_circumference_cm"
        else:
            loop_metric = "waist_circumference_cm"
        rows = [
            one("length_cm", (loop_metric,), f"{loop_metric} * variant.ease",
                lambda circumference: circumference * ease),
            one("width_cm", ("upper_height_cm",), "upper_height * 0.12",
                lambda height: height * 0.12),
        ]
    elif kind is PrimitiveKind.OVERLAY:
        height_metric = "lower_length_cm" if any(
            token in placed for token in ("lower", "skirt", "leg")) else "upper_height_cm"
        rows = [
            one("height_cm", (height_metric,), f"{height_metric} * 0.75 * variant.length",
                lambda height: height * 0.75 * length_scale),
            one("width_cm", ("body_circumference_cm",),
                "body_circumference * 0.55 * variant.ease",
                lambda circumference: circumference * 0.55 * ease),
        ]
    elif kind is PrimitiveKind.OPENING:
        length_metric = "lower_length_cm" if any(
            token in placed for token in ("lower", "skirt", "leg")) else "upper_height_cm"
        rows = [one("length_cm", (length_metric,), f"{length_metric} * 0.72",
                    lambda height: height * 0.72)]
    elif kind is PrimitiveKind.DRAPE_ANCHOR:
        rows = []
    else:  # Defensive: enum additions must not silently receive a generic size.
        raise _Refusal("UNKNOWN_PARTS_IR_UNSUPPORTED_KIND",
                       f"no deterministic completion exists for {kind.value}",
                       kind=kind.value)
    return dict(row for row in rows if row is not None)


def _model_dimensions(raw: Any, *, kind: PrimitiveKind, part_id: str,
                      visible: Mapping[str, Any]) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]:
    if raw is None:
        return {}, {}
    if not isinstance(raw, Mapping):
        raise _Refusal("UNKNOWN_PARTS_IR_DIMENSIONS",
                       f"{part_id}.dimensions must be an object", part_id=part_id)
    values: Dict[str, float] = {}
    evidence: Dict[str, Dict[str, Any]] = {}
    for raw_name, raw_value in raw.items():
        name = str(raw_name)
        if not name or not (name.endswith("_cm") or name.endswith("_angle_deg")):
            raise _Refusal("UNKNOWN_PARTS_IR_DIMENSION_NAME",
                           f"{part_id}.{name} is not a typed geometric dimension",
                           part_id=part_id, dimension=name)
        if isinstance(raw_value, Mapping):
            _proposal_state(raw_value.get("state"),
                            field=f"{part_id}.dimensions.{name}.state")
            number_value = raw_value.get("value", raw_value.get("value_cm"))
            basis = raw_value.get("basis", visible["basis"])
            breaks_when = raw_value.get("breaks_when", visible["breaks_when"])
        else:
            number_value = raw_value
            basis = visible["basis"]
            breaks_when = visible["breaks_when"]
        coordinate = name in ("x_cm", "y_cm", "z_cm") or name.endswith("_angle_deg")
        number = _number(number_value, code="UNKNOWN_PARTS_IR_INVALID_DIMENSION",
                         field=f"{part_id}.{name}", coordinate=coordinate)
        if not isinstance(basis, str) or not basis.strip():
            raise _Refusal("UNKNOWN_PARTS_IR_INVALID_DIMENSION",
                           f"{part_id}.{name} needs a model basis")
        if not isinstance(breaks_when, str) or not breaks_when.strip():
            raise _Refusal("UNKNOWN_PARTS_IR_INVALID_DIMENSION",
                           f"{part_id}.{name} needs breaks_when")
        values[name] = number
        evidence[name] = {
            "value_cm": number,
            "state": PROPOSED,
            "dimension_source": "MODEL_SUPPLIED_PROPOSAL",
            "basis": basis.strip(),
            "breaks_when": breaks_when.strip(),
            "model_supplied": True,
            "completed": False,
            "not_measured_from_image": True,
        }
    return values, evidence


def _completed_evidence(value: float, formula: str, metric_names: Tuple[str, ...],
                        metric_entries: List[Dict[str, Any]],
                        variant_id: str) -> Dict[str, Any]:
    source_types = {entry["dimension_source"] for entry in metric_entries}
    if source_types == {"TARGET_MANNEQUIN_MEASUREMENT"}:
        source = "TARGET_MANNEQUIN_DERIVED_PROPOSAL"
    elif source_types == {"BOUNDED_PREVIEW_MANNEQUIN_VALUE"}:
        source = "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL"
    else:
        source = "MIXED_MANNEQUIN_DERIVED_PROPOSAL"
    return {
        "value_cm": value,
        "state": PROPOSED,
        "dimension_source": source,
        "basis": (
            f"deterministic formula `{formula}` using {', '.join(metric_names)} "
            f"for completion variant {variant_id}; no image pixels were converted to centimetres"
        ),
        "breaks_when": (
            "a source mannequin value changes, the model supplies this dimension explicitly, "
            "or the proposed ease/shape variant is rejected"
        ),
        "source_measurements": copy.deepcopy(metric_entries),
        "model_supplied": False,
        "completed": True,
        "not_measured_from_image": True,
    }


def _part_semantics(part: Mapping[str, Any], *, part_id: str,
                    visible: Mapping[str, Any]) -> Dict[str, Any]:
    """Preserve model topology hints without raising their authority."""
    values: Dict[str, Any] = {}
    evidence: Dict[str, Dict[str, Any]] = {}
    for field in _PART_SEMANTIC_FIELDS:
        if field not in part:
            continue
        value = part[field]
        if field == "quantity":
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 1 <= value <= 32):
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_INVALID_QUANTITY",
                    f"{part_id}.quantity must be an integer from 1 through 32",
                    part_id=part_id, quantity=value,
                )
        elif field == "attachment_relation":
            if (not isinstance(value, str)
                    or value.strip().upper() not in {"JOIN", "LAYER"}):
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_INVALID_ATTACHMENT_RELATION",
                    f"{part_id}.attachment_relation must be JOIN or LAYER",
                    part_id=part_id, attachment_relation=value,
                )
            value = value.strip().upper()
        elif field in {"ownership_state", "waist_stack_state"}:
            if (not isinstance(value, str)
                    or value.strip().upper() != PROPOSED):
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_AUTHORITY_ESCALATION",
                    f"{part_id}.{field} must remain PROPOSED",
                    part_id=part_id, field=field, claimed_state=value,
                )
            value = PROPOSED
        elif field == "waist_stack_order":
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 1 <= value <= 8):
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_INVALID_WAIST_STACK_ORDER",
                    f"{part_id}.waist_stack_order must be an integer from 1 through 8",
                    part_id=part_id, waist_stack_order=value,
                )
        elif field in {
                "owner_node_id", "layer_role", "attachment_port",
                "waist_stack_parent", "waist_stack_id",
                "waist_stack_construction_mode", "waist_stack_role"}:
            if not isinstance(value, str) or not value.strip():
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_INVALID_TOPOLOGY_CONTRACT",
                    f"{part_id}.{field} must be a non-empty string",
                    part_id=part_id, field=field,
                )
            value = value.strip()
        elif field == "attached_to":
            if isinstance(value, str):
                if not value.strip():
                    raise _Refusal("UNKNOWN_PARTS_IR_INVALID_ATTACHED_TO",
                                   f"{part_id}.attached_to must not be empty",
                                   part_id=part_id)
                value = value.strip()
            elif (isinstance(value, Sequence)
                  and not isinstance(value, (str, bytes))):
                if (not value or any(not isinstance(item, str)
                                     or not item.strip() for item in value)):
                    raise _Refusal("UNKNOWN_PARTS_IR_INVALID_ATTACHED_TO",
                                   f"{part_id}.attached_to must name non-empty part ids",
                                   part_id=part_id)
                value = [item.strip() for item in value]
                if len(value) != len(set(value)):
                    raise _Refusal("UNKNOWN_PARTS_IR_INVALID_ATTACHED_TO",
                                   f"{part_id}.attached_to contains duplicate ids",
                                   part_id=part_id)
            else:
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_INVALID_ATTACHED_TO",
                    f"{part_id}.attached_to must be a part id or an array of part ids",
                    part_id=part_id,
                )
        elif field == "detail_role" and isinstance(value, Sequence) \
                and not isinstance(value, (str, bytes)):
            if (not value or any(not isinstance(item, str) or not item.strip()
                                 for item in value)):
                raise _Refusal("UNKNOWN_PARTS_IR_INVALID_SEMANTIC_FIELD",
                               f"{part_id}.{field} must contain non-empty strings",
                               part_id=part_id, field=field)
            value = [item.strip() for item in value]
        elif field in {"closure_detail", "opening_topology",
                       "waist_join_provenance"}:
            if isinstance(value, str):
                if field == "waist_join_provenance":
                    raise _Refusal(
                        "UNKNOWN_PARTS_IR_INVALID_SEMANTIC_FIELD",
                        f"{part_id}.{field} must be a non-empty object",
                        part_id=part_id, field=field)
                if not value.strip():
                    raise _Refusal(
                        "UNKNOWN_PARTS_IR_INVALID_SEMANTIC_FIELD",
                        f"{part_id}.{field} must not be empty",
                        part_id=part_id, field=field)
                value = value.strip()
            elif isinstance(value, Mapping) and value:
                value = copy.deepcopy(dict(value))
                for authority_field in ("state", "authority", "verdict"):
                    if authority_field in value:
                        _proposal_state(
                            value[authority_field],
                            field=f"{part_id}.{field}.{authority_field}")
                value["state"] = PROPOSED
            else:
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_INVALID_SEMANTIC_FIELD",
                    f"{part_id}.{field} must be a non-empty string or object",
                    part_id=part_id, field=field)
        elif field == "waist_join_mode":
            if not isinstance(value, str) or value.strip().upper() != "GATHER":
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_INVALID_SEMANTIC_FIELD",
                    f"{part_id}.waist_join_mode must be GATHER",
                    part_id=part_id, field=field, value=value)
            value = "GATHER"
        elif field == "waist_join_state":
            _proposal_state(value, field=f"{part_id}.waist_join_state")
            value = PROPOSED
        elif not isinstance(value, str) or not value.strip():
            raise _Refusal("UNKNOWN_PARTS_IR_INVALID_SEMANTIC_FIELD",
                           f"{part_id}.{field} must be a non-empty string",
                           part_id=part_id, field=field)
        else:
            value = value.strip()
        value = _json_copy(value, field=f"{part_id}.{field}")
        values[field] = value
        evidence[field] = {
            "value": copy.deepcopy(value),
            "state": PROPOSED,
            "source": "MODEL_SUPPLIED_PARTS_IR_PROPOSAL",
            "basis": visible["basis"],
            "breaks_when": visible["breaks_when"],
            "not_inferred_by_completion": True,
        }
    return {"values": values, "evidence": evidence}


def _part_node(part: Mapping[str, Any], metrics: Mapping[str, Dict[str, Any]],
               variant: Mapping[str, Any], candidate_id: str) -> PrimitiveNode:
    part_id = part.get("part_id")
    if not isinstance(part_id, str) or not part_id.strip():
        raise _Refusal("UNKNOWN_PARTS_IR_PART_ID",
                       "every part needs a non-empty part_id")
    part_id = part_id.strip()
    try:
        kind = PrimitiveKind(part.get("kind"))
    except (TypeError, ValueError) as exc:
        raise _Refusal("UNKNOWN_PARTS_IR_UNKNOWN_KIND",
                       f"{part_id} names an unknown PrimitiveKind",
                       part_id=part_id, kind=part.get("kind")) from exc
    layer = part.get("layer")
    if (isinstance(layer, bool) or not isinstance(layer, int)
            or not 0 <= layer <= 15):
        raise _Refusal("UNKNOWN_PARTS_IR_INVALID_LAYER",
                       f"{part_id}.layer must be an integer from 0 through 15",
                       part_id=part_id, layer=layer)
    if "placement" not in part:
        raise _Refusal("UNKNOWN_PARTS_IR_PLACEMENT",
                       f"{part_id} needs an explicit placement", part_id=part_id)
    placement = part["placement"]
    if ((isinstance(placement, str) and not placement.strip())
            or (not isinstance(placement, (str, Mapping)))):
        raise _Refusal("UNKNOWN_PARTS_IR_PLACEMENT",
                       f"{part_id}.placement must be a non-empty string or object",
                       part_id=part_id)
    placement = _json_copy(placement, field=f"{part_id}.placement")
    if "visible_basis" not in part:
        raise _Refusal("UNKNOWN_PARTS_IR_VISIBLE_BASIS",
                       f"{part_id} needs visible_basis", part_id=part_id)
    visible = _visible_basis(part["visible_basis"], part_id=part_id)
    semantics = _part_semantics(part, part_id=part_id, visible=visible)
    model_values, evidence = _model_dimensions(
        part.get("dimensions"), kind=kind, part_id=part_id, visible=visible)
    values = dict(model_values)
    missing_required = [name for name in _REQUIRED_DIMENSIONS[kind]
                        if name not in values]
    if missing_required and not metrics:
        raise _Refusal(
            "UNKNOWN_PARTS_IR_MEASUREMENT_SOURCE_REQUIRED",
            f"{part_id} has dimensions that need a mannequin source",
            part_id=part_id, missing=missing_required,
        )
    derived = (_derived_for(kind, metrics, placement, variant, missing_required)
               if missing_required else {})
    for name in _REQUIRED_DIMENSIONS[kind]:
        if name in values:
            continue
        value, formula, metric_names, metric_entries = derived[name]
        value = _number(
            value, code="UNKNOWN_PARTS_IR_COMPLETED_DIMENSION_OUT_OF_RANGE",
            field=f"{part_id}.{name}",
        )
        values[name] = value
        evidence[name] = _completed_evidence(
            value, formula, metric_names, metric_entries,
            str(variant["variant_id"]),
        )
    attributes = {
        "state": PROPOSED,
        "proposal_only": True,
        "candidate_id": candidate_id,
        "completion_variant": variant["variant_id"],
        "placement": placement,
        "visible_basis": visible,
        **semantics["values"],
        "parts_ir_semantics": {
            "placement": {
                "value": copy.deepcopy(placement),
                "state": PROPOSED,
                "source": "MODEL_SUPPLIED_PARTS_IR_PROPOSAL",
                "basis": visible["basis"],
                "breaks_when": visible["breaks_when"],
                "not_inferred_by_completion": True,
            },
            **semantics["evidence"],
        },
        "dimension_evidence": evidence,
        "dimension_source": {
            name: row["dimension_source"] for name, row in evidence.items()
        },
        "dimension_basis": {name: row["basis"] for name, row in evidence.items()},
        "dimension_breaks_when": {
            name: row["breaks_when"] for name, row in evidence.items()
        },
        "not_measured_from_image": True,
        "construction_topology": "UNRESOLVED_PROPOSAL",
    }
    return PrimitiveNode(part_id, kind, values, (), layer, attributes)


def _candidate_specs(parts_ir: Mapping[str, Any], candidate_count: Optional[int]
                     ) -> List[Dict[str, Any]]:
    if (candidate_count is not None
            and (isinstance(candidate_count, bool)
                 or not isinstance(candidate_count, int))):
        raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATE_COUNT",
                       "candidate_count must be an integer",
                       candidate_count=candidate_count)
    has_parts = "parts" in parts_ir
    has_candidates = "candidates" in parts_ir
    if has_parts == has_candidates:
        raise _Refusal("UNKNOWN_PARTS_IR_SHAPE",
                       "provide exactly one of parts or candidates")
    if has_candidates:
        raw = parts_ir.get("candidates")
        if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))):
            raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATES",
                           "candidates must be an array")
        if len(raw) < 2:
            raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATES_INSUFFICIENT",
                           "the vision-model boundary requires at least two candidates",
                           candidate_count=len(raw))
        if len(raw) > len(_VARIANTS):
            raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATES_EXCESSIVE",
                           f"at most {len(_VARIANTS)} bounded candidates are accepted",
                           candidate_count=len(raw))
        if candidate_count is not None and candidate_count != len(raw):
            raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATE_COUNT_MISMATCH",
                           "candidate_count disagrees with candidates length",
                           candidate_count=candidate_count, actual=len(raw))
        specs = []
        for index, row in enumerate(raw):
            if not isinstance(row, Mapping):
                raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATE",
                               "every candidate must be an object", index=index)
            _proposal_state(row.get("state"), field=f"candidates[{index}].state")
            specs.append(dict(row))
        return specs

    count = candidate_count if candidate_count is not None else parts_ir.get(
        "candidate_count", 2)
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATES_INSUFFICIENT",
                       "candidate_count must be an integer of at least two",
                       candidate_count=count)
    if count > len(_VARIANTS):
        raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATES_EXCESSIVE",
                       f"candidate_count may not exceed {len(_VARIANTS)}",
                       candidate_count=count)
    return [{"parts": parts_ir["parts"]} for _ in range(count)]


def _candidate_identifier(spec: Mapping[str, Any], index: int,
                          variant_id: str) -> str:
    supplied = spec.get("candidate_id")
    if supplied is not None:
        if not isinstance(supplied, str) or not supplied.strip():
            raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATE_ID",
                           "candidate_id must be a non-empty string", index=index)
        return supplied.strip()
    return "parts-" + semantic_digest({
        "parts": spec.get("parts"), "index": index, "variant": variant_id,
    })[:16]


def _candidate_variants(specs: Sequence[Mapping[str, Any]]) \
        -> Tuple[List[Mapping[str, Any]], str]:
    """Assign bounded completion variants without coupling them to row order.

    A vision-model candidate already has a semantic identity.  Giving the
    first array element ``balanced`` and the second ``relaxed`` made the same
    candidate change geometry merely because a JSON producer reordered the
    array.  When every candidate supplies a unique id, rank those ids and bind
    variants by that stable rank while preserving the caller's output order.

    The template expansion form has no candidate identities by design, so it
    retains positional assignment; its generated ids explicitly include that
    position and never claim reorder stability.
    """
    supplied: List[str] = []
    for index, spec in enumerate(specs):
        value = spec.get("candidate_id")
        if value is None:
            return list(_VARIANTS[:len(specs)]), "POSITIONAL_TEMPLATE_EXPANSION"
        if not isinstance(value, str) or not value.strip():
            raise _Refusal("UNKNOWN_PARTS_IR_CANDIDATE_ID",
                           "candidate_id must be a non-empty string", index=index)
        supplied.append(value.strip())
    if len(supplied) != len(set(supplied)):
        duplicate = next(value for value in supplied
                         if supplied.count(value) > 1)
        raise _Refusal("UNKNOWN_PARTS_IR_DUPLICATE_CANDIDATE",
                       "candidate ids must be unique", candidate_id=duplicate)
    by_id = {
        candidate_id: _VARIANTS[index]
        for index, candidate_id in enumerate(sorted(supplied))
    }
    return [by_id[candidate_id] for candidate_id in supplied], \
        "STABLE_CANDIDATE_ID_RANK"


def _route_ornaments(parts_ir: Mapping[str, Any]
                     ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """Remove typed ornaments from PrimitiveKind parsing without losing them.

    ``ornament_primitives`` owns the centimetre geometry.  Completion owns the
    candidate boundary, so it keeps the routed result beside the completed
    structure instead of coercing an ornament into a garment-class primitive.
    An ornament expansion refusal fails the completion explicitly; it is never
    treated as an absent decorative detail.
    """
    routed = ornament_primitives.route_parts_ir(parts_ir)
    if routed.get("schema") != ornament_primitives.ROUTING_SCHEMA:
        raise _Refusal(
            "UNKNOWN_PARTS_IR_ORNAMENT_ROUTING_SCHEMA",
            "ornament router returned an unexpected schema",
            router_schema=routed.get("schema"),
        )
    verdict = routed.get("verdict")
    if isinstance(verdict, str) and verdict.startswith("UNKNOWN_"):
        raise _Refusal(
            verdict,
            str(routed.get("why", "ornament expansion was refused")),
            ornament_routing=_json_copy(routed, field="ornament_routing"),
        )
    raw_rows = routed.get("candidates")
    if (not isinstance(raw_rows, Sequence)
            or isinstance(raw_rows, (str, bytes)) or not raw_rows
            or any(not isinstance(row, Mapping) for row in raw_rows)):
        raise _Refusal(
            "UNKNOWN_PARTS_IR_ORNAMENT_ROUTING_RESULT",
            "ornament router returned no candidate routing records",
        )
    rows = [_json_copy(dict(row), field="ornament_routing.candidates")
            for row in raw_rows]
    if any(row.get("all_parts_preserved") is not True for row in rows):
        raise _Refusal(
            "UNKNOWN_PARTS_IR_ORNAMENT_DROPPED",
            "ornament routing did not account for every input part",
            ornament_routing=_json_copy(routed, field="ornament_routing"),
        )

    prepared = _json_copy(dict(parts_ir), field="parts_ir")
    if "parts" in prepared:
        if len(rows) != 1:
            raise _Refusal(
                "UNKNOWN_PARTS_IR_ORNAMENT_ROUTING_COUNT",
                "one parts template must produce one ornament routing record",
                routing_count=len(rows),
            )
        prepared["parts"] = copy.deepcopy(rows[0]["passthrough_parts"])
        if not prepared["parts"]:
            raise _Refusal(
                "UNKNOWN_PARTS_IR_ORNAMENT_STRUCTURE_REQUIRED",
                "an ornament-only proposal has no structure node to attach to",
                ornament_routing=_json_copy(routed, field="ornament_routing"),
            )
    else:
        candidates = prepared.get("candidates")
        if (not isinstance(candidates, list) or len(candidates) != len(rows)):
            raise _Refusal(
                "UNKNOWN_PARTS_IR_ORNAMENT_ROUTING_COUNT",
                "candidate and ornament routing counts disagree",
                candidate_count=(len(candidates)
                                 if isinstance(candidates, list) else None),
                routing_count=len(rows),
            )
        for index, row in enumerate(rows):
            if not isinstance(candidates[index], dict):
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_ORNAMENT_ROUTING_CANDIDATE",
                    "prepared candidate must be an object", index=index,
                )
            candidates[index]["parts"] = copy.deepcopy(row["passthrough_parts"])
            if not candidates[index]["parts"]:
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_ORNAMENT_STRUCTURE_REQUIRED",
                    "an ornament-only candidate has no structure node to attach to",
                    candidate_index=index,
                    ornament_routing=_json_copy(row, field="ornament_routing.candidate"),
                )
    return prepared, rows, _json_copy(routed, field="ornament_routing")


def _contains_supported_ornament(parts_ir: Mapping[str, Any]) -> bool:
    raw_groups: List[Any]
    if "parts" in parts_ir:
        raw_groups = [parts_ir.get("parts")]
    else:
        candidates = parts_ir.get("candidates")
        raw_groups = ([row.get("parts") for row in candidates
                       if isinstance(row, Mapping)]
                      if isinstance(candidates, Sequence)
                      and not isinstance(candidates, (str, bytes)) else [])
    return any(
        isinstance(part, Mapping)
        and str(part.get("kind", "")).upper()
        in ornament_primitives.SUPPORTED_KINDS
        for group in raw_groups
        if isinstance(group, Sequence) and not isinstance(group, (str, bytes))
        for part in group
    )


def _ornament_artifacts(route: Mapping[str, Any], *,
                        source_structure_digest: str) -> Optional[Dict[str, Any]]:
    """Flatten one routed ornament set into candidate-bound real artifacts."""
    inputs = route.get("ornament_inputs", [])
    results = route.get("ornament_results", [])
    if not isinstance(inputs, Sequence) or isinstance(inputs, (str, bytes)):
        raise _Refusal("UNKNOWN_PARTS_IR_ORNAMENT_INPUTS",
                       "ornament_inputs must be an array")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise _Refusal("UNKNOWN_PARTS_IR_ORNAMENT_RESULTS",
                       "ornament_results must be an array")
    if len(inputs) != len(results):
        raise _Refusal(
            "UNKNOWN_PARTS_IR_ORNAMENT_RESULT_COUNT",
            "every routed ornament must retain one explicit result",
            input_count=len(inputs), result_count=len(results),
        )
    if not results:
        return None

    pattern_pieces: List[Dict[str, Any]] = []
    attachment_ports: List[Dict[str, Any]] = []
    seam_intents: List[Dict[str, Any]] = []
    result_manifest: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    for index, raw in enumerate(results):
        if not isinstance(raw, Mapping):
            raise _Refusal("UNKNOWN_PARTS_IR_ORNAMENT_RESULT",
                           "every ornament result must be an object", index=index)
        result = _json_copy(dict(raw), field="ornament_result")
        state = result.get("state")
        if state not in {PROPOSED, "REVIEW"}:
            raise _Refusal(
                "UNKNOWN_PARTS_IR_ORNAMENT_RESULT_STATE",
                "a completed ornament result must remain PROPOSED or REVIEW",
                index=index, state=state, verdict=result.get("verdict"),
            )
        authority = result.get("authority", {})
        if (not isinstance(authority, Mapping)
                or authority.get("observed") is not False
                or authority.get("approved") is not False
                or authority.get("image_promoted_to_observed") is not False
                or authority.get("output_state") != PROPOSED):
            raise _Refusal(
                "UNKNOWN_PARTS_IR_ORNAMENT_AUTHORITY_ESCALATION",
                "ornament geometry may not become fact or approval at completion",
                ornament_id=result.get("ornament_id"), authority=authority,
            )
        pieces = result.get("pattern_pieces", [])
        ports = result.get("attachment_ports", [])
        intents = result.get("seam_intents", [])
        for field, values in (("pattern_pieces", pieces),
                              ("attachment_ports", ports),
                              ("seam_intents", intents)):
            if (not isinstance(values, Sequence)
                    or isinstance(values, (str, bytes))
                    or any(not isinstance(value, Mapping) for value in values)):
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_ORNAMENT_ARTIFACTS",
                    f"ornament {field} must be an array of objects",
                    ornament_id=result.get("ornament_id"), field=field,
                )
        pattern_pieces.extend(copy.deepcopy(list(pieces)))
        attachment_ports.extend(copy.deepcopy(list(ports)))
        for raw_intent in intents:
            intent = copy.deepcopy(dict(raw_intent))
            intent["ornament_order"] = intent.get("order")
            intent["order"] = len(seam_intents) + 1
            seam_intents.append(intent)
        materialized = bool(pieces and ports and intents)
        result_manifest.append({
            "ornament_id": result.get("ornament_id"),
            "kind": result.get("kind"),
            "verdict": result.get("verdict"),
            "state": state,
            "digest": result.get("digest"),
            "geometry_materialized": materialized,
        })
        if state != PROPOSED or not materialized:
            unresolved.append({
                "ornament_id": result.get("ornament_id"),
                "kind": result.get("kind"),
                "verdict": result.get("verdict"),
                "state": state,
                "why": result.get("why"),
                "geometry_materialized": materialized,
            })

    for field, values, key in (
            ("pattern piece", pattern_pieces, "piece_id"),
            ("attachment port", attachment_ports, "port_id"),
            ("seam intent", seam_intents, "intent_id")):
        identifiers = [value.get(key) for value in values]
        if (any(not isinstance(identifier, str) or not identifier
                for identifier in identifiers)
                or len(identifiers) != len(set(identifiers))):
            raise _Refusal(
                "UNKNOWN_PARTS_IR_ORNAMENT_ARTIFACT_ID",
                f"{field} ids must be non-empty and unique",
                field=field, identifiers=identifiers,
            )
    for piece in pattern_pieces:
        authority = piece.get("geometry_authority", {})
        if (piece.get("state") != PROPOSED
                or not isinstance(authority, Mapping)
                or authority.get("state") != PROPOSED
                or authority.get("observed") is not False):
            raise _Refusal(
                "UNKNOWN_PARTS_IR_ORNAMENT_AUTHORITY_ESCALATION",
                "ornament pattern pieces must remain proposal-only",
                piece_id=piece.get("piece_id"),
            )
    if any(port.get("state") != PROPOSED or port.get("observed") is not False
           for port in attachment_ports):
        raise _Refusal(
            "UNKNOWN_PARTS_IR_ORNAMENT_AUTHORITY_ESCALATION",
            "ornament attachment ports must remain proposal-only",
        )
    if any(intent.get("state") != PROPOSED for intent in seam_intents):
        raise _Refusal(
            "UNKNOWN_PARTS_IR_ORNAMENT_AUTHORITY_ESCALATION",
            "ornament seam intents must remain proposal-only",
        )

    payload: Dict[str, Any] = {
        "schema": ORNAMENT_ARTIFACT_SCHEMA,
        "state": PROPOSED,
        "readiness": ("REVIEW" if unresolved else "MATERIALIZED"),
        "source_structure_digest": source_structure_digest,
        "ornament_count": len(results),
        "materialized_ornament_count": sum(
            1 for row in result_manifest if row["geometry_materialized"]),
        "pattern_pieces": pattern_pieces,
        "attachment_ports": attachment_ports,
        "seam_intents": seam_intents,
        "construction_order": [row["intent_id"] for row in seam_intents],
        "results": copy.deepcopy(list(results)),
        "result_manifest": result_manifest,
        "routing_manifest": copy.deepcopy(route.get("routing_manifest", [])),
        "unresolved": unresolved,
        "all_input_parts_preserved": route.get("all_parts_preserved") is True,
        "authority": {
            "highest_state": PROPOSED,
            "observed": False,
            "approved": False,
            "image_promoted_to_observed": False,
        },
        "provenance": {
            "method": "ornament_primitives route bound to parts-IR completion",
            "corpus_used": False,
            "garment_class_enum_modified": False,
            "image_measurements_claimed": False,
        },
    }
    payload["digest"] = semantic_digest(payload)
    return payload


def complete_parts_ir(
    parts_ir: Mapping[str, Any], *,
    target_measurements: Optional[Mapping[str, Any]] = None,
    preview_profile: Optional[Mapping[str, Any]] = None,
    candidate_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Complete small parts proposals into validation-ready structure proposals.

    The successful result deliberately uses ``verdict=PROPOSED``.  Internal
    schema validation may return ``ANSWER`` to this module, but that only means
    the graph is structurally valid; it is never exposed as evidence, approval,
    a wearer measurement, or a sewing answer.
    """
    try:
        if not isinstance(parts_ir, Mapping):
            raise _Refusal("UNKNOWN_PARTS_IR_SCHEMA",
                           "parts_ir must be an object")
        schema = parts_ir.get("schema", SCHEMA)
        if schema != SCHEMA:
            raise _Refusal("UNKNOWN_PARTS_IR_SCHEMA",
                           f"expected {SCHEMA}", schema=schema)
        _proposal_state(parts_ir.get("state"), field="parts_ir.state")
        if _contains_supported_ornament(parts_ir):
            prepared_parts_ir, ornament_routes, ornament_routing = (
                _route_ornaments(parts_ir))
        else:
            prepared_parts_ir = parts_ir
            ornament_routes = []
            ornament_routing = {}
        specs = _candidate_specs(prepared_parts_ir, candidate_count)
        metrics = _metrics(target_measurements, preview_profile)
        variants, variant_assignment = _candidate_variants(specs)
        candidates: List[Dict[str, Any]] = []
        candidate_ids: set[str] = set()
        for index, spec in enumerate(specs):
            variant = variants[index]
            candidate_id = _candidate_identifier(
                spec, index, str(variant["variant_id"]))
            if candidate_id in candidate_ids:
                raise _Refusal("UNKNOWN_PARTS_IR_DUPLICATE_CANDIDATE",
                               "candidate ids must be unique",
                               candidate_id=candidate_id)
            candidate_ids.add(candidate_id)
            raw_parts = spec.get("parts")
            if (not isinstance(raw_parts, Sequence)
                    or isinstance(raw_parts, (str, bytes)) or not raw_parts):
                raise _Refusal("UNKNOWN_PARTS_IR_PARTS_MISSING",
                               "every candidate needs a non-empty parts array",
                               candidate_id=candidate_id)
            if any(not isinstance(row, Mapping) for row in raw_parts):
                raise _Refusal("UNKNOWN_PARTS_IR_PART",
                               "every part must be an object",
                               candidate_id=candidate_id)
            nodes = tuple(_part_node(row, metrics, variant, candidate_id)
                          for row in raw_parts)
            node_ids = [node.node_id for node in nodes]
            if len(node_ids) != len(set(node_ids)):
                raise _Refusal("UNKNOWN_PARTS_IR_DUPLICATE_PART",
                               "part_id values must be unique within a candidate",
                               candidate_id=candidate_id)
            graph = StructureGraph(nodes, ())
            checked = validate_structure(graph)
            if checked.get("verdict") != ANSWER:
                raise _Refusal(
                    "UNKNOWN_PARTS_IR_GENERATED_STRUCTURE",
                    "completed dimensions did not pass garment.structure.v1 validation",
                    candidate_id=candidate_id,
                    validator_code=checked.get("verdict"),
                    validator_why=checked.get("why"),
                )
            candidate = graph.as_dict()
            ornament_artifacts = None
            if ornament_routes:
                route = (ornament_routes[index]
                         if "candidates" in prepared_parts_ir
                         else ornament_routes[0])
                ornament_artifacts = _ornament_artifacts(
                    route, source_structure_digest=graph.digest)
            candidate.update({
                "candidate_id": candidate_id,
                "state": PROPOSED,
                "structure_digest": graph.digest,
                "completion_variant": variant["variant_id"],
                "schema_validation": {
                    "validated": True,
                    "validator": "garment.structure.v1 deterministic schema validation",
                    "authority_granted": False,
                },
                "provenance": {
                    "method": "deterministic parts-IR dimension completion",
                    "model_parts_preserved_as": PROPOSED,
                    "raw_pixels_consumed": False,
                    "image_measurements_claimed": False,
                    "corpus_used": False,
                },
                "limitations": [
                    "placement and visible_basis remain model proposals",
                    "empty operations means seam topology is not established by this boundary",
                    "preview dimensions are not manufacturing measurements",
                ],
            })
            if ornament_artifacts is not None:
                candidate["ornament_artifacts"] = ornament_artifacts
                candidate["candidate_artifact_digest"] = semantic_digest({
                    "structure_digest": graph.digest,
                    "ornament_digest": ornament_artifacts["digest"],
                })
            candidates.append(candidate)
        return {
            "schema": RESULT_SCHEMA,
            "verdict": PROPOSED,
            "state": PROPOSED,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "authority": {
                "highest_state": PROPOSED,
                "approved": False,
                "observed": False,
                "answer": False,
            },
            "provenance": {
                "input_schema": SCHEMA,
                "raw_pixels_consumed": False,
                "image_measurements_claimed": False,
                "target_measurements_present": target_measurements is not None,
                "bounded_preview_profile_present": preview_profile is not None,
                "completion_variant_assignment": variant_assignment,
                "candidate_row_order_changes_geometry": False
                    if variant_assignment == "STABLE_CANDIDATE_ID_RANK" else None,
                **({
                    "ornament_route_schema": ornament_routing.get("schema"),
                    "ornament_route_used": True,
                    "ornaments_silently_dropped": False,
                } if ornament_routes else {}),
            },
        }
    except _Refusal as refusal:
        return _unknown(refusal.code, refusal.why, **refusal.detail)
    except (TypeError, ValueError, OverflowError) as exc:
        return _unknown("UNKNOWN_PARTS_IR_MALFORMED", str(exc))


complete = complete_parts_ir


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "ORNAMENT_ARTIFACT_SCHEMA",
    "bounded_preview_profile",
    "required_dimensions", "complete_parts_ir", "complete",
]
