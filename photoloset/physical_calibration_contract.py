# -*- coding: utf-8 -*-
"""Typed claim gate for physical garment calibration.

This module is intentionally disjoint from the numerical solvers.  It does
not estimate material constants, average disagreeing evidence, or turn a
simulation into a measurement.  It answers the narrower question: *is there
enough rights-cleared, non-model measurement evidence to make a calibrated or
bounded-error claim?*

The contract is deliberately strict:

* model and simulation producers have an authority ceiling of ``PROPOSED``;
* material properties retain every source and become ``CONTESTED`` when the
  sources disagree;
* validation observations are checked individually, never averaged;
* dataset, test, observation, property, and threshold provenance must all
  permit calibration and claim validation;
* a few-percent real-cloth claim is emitted only when explicit non-model
  observations pass explicit, non-model-approved acceptance thresholds.

Missing evidence produces a typed resolution request.  Bounded alternatives
remain useful for previewing scenarios, but can never authorize a calibrated
claim.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


SCHEMA = "garment.physical-calibration-contract.v1"
DECISION_SCHEMA = "garment.physical-calibration-decision.v1"
RESOLUTION_SCHEMA = "garment.physical-calibration-resolution.v1"
PROPERTY_REDUCTION_SCHEMA = "garment.material-property-reduction.v1"

CLAIM_AUTHORIZED = "CLAIM_AUTHORIZED"
CLAIM_BLOCKED = "CLAIM_BLOCKED"

CALIBRATION_USE = "CALIBRATION"
CLAIM_VALIDATION_USE = "CLAIM_VALIDATION"


class EvidenceAuthority(str, Enum):
    """Authority requested by an evidence producer."""

    MEASURED = "MEASURED"
    PROPOSED = "PROPOSED"


class ProducerKind(str, Enum):
    """Producer classes used to enforce the model authority ceiling."""

    HUMAN = "HUMAN"
    LAB = "LAB"
    PROVIDER = "PROVIDER"
    MODEL = "MODEL"
    SIMULATION = "SIMULATION"


class CalibrationDomain(str, Enum):
    MATERIAL = "MATERIAL"
    REAL_CLOTH = "REAL_CLOTH"
    SEAM = "SEAM"
    WIND_TUNNEL = "WIND_TUNNEL"


class ClaimKind(str, Enum):
    MATERIAL_CALIBRATED = "MATERIAL_CALIBRATED"
    REAL_CLOTH_ERROR_BOUND = "REAL_CLOTH_ERROR_BOUND"
    SEAM_CALIBRATED = "SEAM_CALIBRATED"
    WIND_TUNNEL_CALIBRATED = "WIND_TUNNEL_CALIBRATED"


class ThresholdOperator(str, Enum):
    MAXIMUM = "MAXIMUM"
    MINIMUM = "MINIMUM"


class ResolutionKind(str, Enum):
    MEASURE = "MEASURE"
    CONNECT_PROVIDER = "CONNECT_PROVIDER"
    BOUNDED_ALTERNATIVES = "BOUNDED_ALTERNATIVES"
    TYPED_STOP = "TYPED_STOP"


_NON_MEASURING_PRODUCERS = frozenset(
    {ProducerKind.MODEL, ProducerKind.SIMULATION}
)
_REQUIRED_RIGHTS = (CALIBRATION_USE, CLAIM_VALIDATION_USE)

MATERIAL_PROPERTY_UNITS: Mapping[str, str] = {
    "composition": "mass_fraction",
    "thickness": "m",
    "stretch_warp": "ratio",
    "stretch_weft": "ratio",
    "friction_static": "coefficient",
    "friction_dynamic": "coefficient",
    "bending_warp": "N*m",
    "bending_weft": "N*m",
}
REQUIRED_MATERIAL_PROPERTIES = tuple(sorted(MATERIAL_PROPERTY_UNITS))

_CLAIM_DOMAIN: Mapping[ClaimKind, CalibrationDomain] = {
    ClaimKind.MATERIAL_CALIBRATED: CalibrationDomain.MATERIAL,
    ClaimKind.REAL_CLOTH_ERROR_BOUND: CalibrationDomain.REAL_CLOTH,
    ClaimKind.SEAM_CALIBRATED: CalibrationDomain.SEAM,
    ClaimKind.WIND_TUNNEL_CALIBRATED: CalibrationDomain.WIND_TUNNEL,
}


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % name)
    return value.strip()


def _finite(value: Any, name: str, *, nonnegative: bool = False,
            positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number" % name)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % name)
    if nonnegative and result < 0.0:
        raise ValueError("%s must be non-negative" % name)
    if positive and result <= 0.0:
        raise ValueError("%s must be positive" % name)
    return result


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _canonical(value: Any) -> Any:
    """Return strict canonical JSON data for stable digests."""
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        rows = [_canonical(item) for item in value]
        return sorted(rows, key=lambda item: json.dumps(
            item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not canonical JSON")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError("unsupported canonical value: %s" % type(value).__name__)


def stable_digest(value: Any) -> str:
    """SHA-256 over canonical JSON with no platform-dependent whitespace."""
    payload = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_copy(value: Any, name: str) -> Any:
    try:
        canonical = _canonical(value)
        json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s must be canonical JSON: %s" % (name, exc))
    return canonical


@dataclass(frozen=True)
class RightsRecord:
    """Rights attached to a source used for calibration claims."""

    license_id: str
    holder: str
    permitted_uses: Tuple[str, ...]
    source_uri: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "license_id", _text(
            self.license_id, "rights.license_id"))
        object.__setattr__(self, "holder", _text(
            self.holder, "rights.holder"))
        if not isinstance(self.permitted_uses, tuple):
            object.__setattr__(self, "permitted_uses",
                               tuple(self.permitted_uses))
        uses = tuple(sorted({_text(use, "rights.permitted_use").upper()
                             for use in self.permitted_uses}))
        if not uses:
            raise ValueError("rights.permitted_uses must not be empty")
        object.__setattr__(self, "permitted_uses", uses)
        if self.source_uri and not isinstance(self.source_uri, str):
            raise ValueError("rights.source_uri must be a string")

    def permits(self, *uses: str) -> bool:
        available = set(self.permitted_uses)
        return all(str(use).upper() in available for use in uses)

    def to_dict(self) -> Dict[str, Any]:
        return _canonical(self)


@dataclass(frozen=True)
class ProvenanceRecord:
    """Falsifiable origin and rights for one evidence-producing operation."""

    source_id: str
    source_digest: str
    method: str
    revision: str
    producer_kind: ProducerKind
    rights: RightsRecord
    recorded_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(
            self.source_id, "provenance.source_id"))
        if not _is_sha256(self.source_digest):
            raise ValueError("provenance.source_digest must be SHA-256")
        object.__setattr__(self, "source_digest", self.source_digest.lower())
        object.__setattr__(self, "method", _text(
            self.method, "provenance.method"))
        object.__setattr__(self, "revision", _text(
            self.revision, "provenance.revision"))
        if not isinstance(self.producer_kind, ProducerKind):
            object.__setattr__(self, "producer_kind",
                               ProducerKind(self.producer_kind))
        if not isinstance(self.rights, RightsRecord):
            raise ValueError("provenance.rights must be a RightsRecord")
        if self.recorded_at and not isinstance(self.recorded_at, str):
            raise ValueError("provenance.recorded_at must be a string")

    @property
    def provenance_digest(self) -> str:
        return stable_digest(self)

    def to_dict(self) -> Dict[str, Any]:
        return _canonical(self)


def effective_authority(requested: EvidenceAuthority,
                        provenance: ProvenanceRecord) -> EvidenceAuthority:
    """Apply the absolute model/simulation authority ceiling."""
    authority = requested
    if not isinstance(authority, EvidenceAuthority):
        authority = EvidenceAuthority(authority)
    if provenance.producer_kind in _NON_MEASURING_PRODUCERS:
        return EvidenceAuthority.PROPOSED
    return authority


def _validate_material_value(name: str, value: Any) -> Any:
    if name == "composition":
        if not isinstance(value, Mapping) or not value:
            raise ValueError("composition must be a non-empty fiber/fraction map")
        result: Dict[str, float] = {}
        for fiber, fraction in value.items():
            key = _text(fiber, "composition fiber")
            result[key] = _finite(
                fraction, "composition.%s" % key, nonnegative=True)
            if result[key] > 1.0:
                raise ValueError("composition fractions cannot exceed 1")
        if abs(math.fsum(result.values()) - 1.0) > 1e-6:
            raise ValueError("composition mass fractions must sum to 1")
        return dict(sorted(result.items()))
    number = _finite(value, "material.%s" % name, nonnegative=True)
    if name in {"thickness", "bending_warp", "bending_weft"} and number <= 0.0:
        raise ValueError("material.%s must be positive" % name)
    return number


@dataclass(frozen=True)
class MaterialPropertyInput:
    """One measured or proposed material-property claim."""

    property_name: str
    value: Any
    unit: str
    authority: EvidenceAuthority
    provenance: ProvenanceRecord
    uncertainty: Optional[float] = None
    conditions: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        name = _text(self.property_name, "property_name")
        if name not in MATERIAL_PROPERTY_UNITS:
            raise ValueError("unsupported material property: %s" % name)
        object.__setattr__(self, "property_name", name)
        expected = MATERIAL_PROPERTY_UNITS[name]
        unit = _text(self.unit, "material unit")
        if unit != expected:
            raise ValueError("%s unit must be %s" % (name, expected))
        object.__setattr__(self, "unit", unit)
        if not isinstance(self.authority, EvidenceAuthority):
            object.__setattr__(self, "authority",
                               EvidenceAuthority(self.authority))
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("material provenance must be a ProvenanceRecord")
        object.__setattr__(self, "value",
                           _validate_material_value(name, self.value))
        if self.uncertainty is not None:
            object.__setattr__(self, "uncertainty", _finite(
                self.uncertainty, "material uncertainty", nonnegative=True))
        object.__setattr__(self, "conditions",
                           _json_copy(self.conditions, "material conditions"))

    @property
    def effective_authority(self) -> EvidenceAuthority:
        return effective_authority(self.authority, self.provenance)

    @property
    def evidence_digest(self) -> str:
        return stable_digest(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        result = _canonical(self)
        result["effective_authority"] = self.effective_authority.value
        return result


@dataclass(frozen=True)
class CalibrationObservation:
    """One raw test result; observations are never averaged by this module."""

    observation_id: str
    domain: CalibrationDomain
    test_kind: str
    metric: str
    sample_id: str
    value: float
    unit: str
    authority: EvidenceAuthority
    provenance: ProvenanceRecord
    conditions: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("observation_id", "test_kind", "metric",
                           "sample_id", "unit"):
            object.__setattr__(self, field_name, _text(
                getattr(self, field_name), "observation.%s" % field_name))
        if not isinstance(self.domain, CalibrationDomain):
            object.__setattr__(self, "domain", CalibrationDomain(self.domain))
        if not isinstance(self.authority, EvidenceAuthority):
            object.__setattr__(self, "authority",
                               EvidenceAuthority(self.authority))
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("observation provenance must be a ProvenanceRecord")
        object.__setattr__(self, "value", _finite(
            self.value, "observation.value"))
        object.__setattr__(self, "conditions",
                           _json_copy(self.conditions, "observation conditions"))

    @property
    def effective_authority(self) -> EvidenceAuthority:
        return effective_authority(self.authority, self.provenance)

    @property
    def observation_digest(self) -> str:
        return stable_digest(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        result = _canonical(self)
        result["effective_authority"] = self.effective_authority.value
        return result


@dataclass(frozen=True)
class CalibrationTest:
    test_id: str
    domain: CalibrationDomain
    test_kind: str
    observations: Tuple[CalibrationObservation, ...]
    provenance: ProvenanceRecord

    def __post_init__(self) -> None:
        object.__setattr__(self, "test_id", _text(self.test_id, "test_id"))
        object.__setattr__(self, "test_kind", _text(
            self.test_kind, "test_kind"))
        if not isinstance(self.domain, CalibrationDomain):
            object.__setattr__(self, "domain", CalibrationDomain(self.domain))
        if not isinstance(self.observations, tuple):
            object.__setattr__(self, "observations", tuple(self.observations))
        if not self.observations:
            raise ValueError("calibration test needs observations")
        for observation in self.observations:
            if not isinstance(observation, CalibrationObservation):
                raise ValueError("test observations must be CalibrationObservation")
            if observation.domain != self.domain:
                raise ValueError("test and observation domains must match")
            if observation.test_kind != self.test_kind:
                raise ValueError("test_kind must match every observation")
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("test provenance must be a ProvenanceRecord")

    @property
    def test_digest(self) -> str:
        return stable_digest(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "domain": self.domain.value,
            "test_kind": self.test_kind,
            "observations": [
                row.to_dict() for row in sorted(
                    self.observations,
                    key=lambda item: item.observation_digest)
            ],
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class CalibrationDataset:
    dataset_id: str
    domain: CalibrationDomain
    tests: Tuple[CalibrationTest, ...]
    provenance: ProvenanceRecord

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text(
            self.dataset_id, "dataset_id"))
        if not isinstance(self.domain, CalibrationDomain):
            object.__setattr__(self, "domain", CalibrationDomain(self.domain))
        if not isinstance(self.tests, tuple):
            object.__setattr__(self, "tests", tuple(self.tests))
        if not self.tests:
            raise ValueError("calibration dataset needs at least one test")
        for test in self.tests:
            if not isinstance(test, CalibrationTest):
                raise ValueError("dataset tests must be CalibrationTest")
            if test.domain != self.domain:
                raise ValueError("dataset and test domains must match")
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("dataset provenance must be a ProvenanceRecord")

    @property
    def dataset_digest(self) -> str:
        return stable_digest(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "domain": self.domain.value,
            "tests": [
                test.to_dict() for test in sorted(
                    self.tests, key=lambda item: item.test_digest)
            ],
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class AcceptanceThreshold:
    """Explicit acceptance criterion approved outside a model."""

    threshold_id: str
    domain: CalibrationDomain
    metric: str
    operator: ThresholdOperator
    value: float
    unit: str
    minimum_samples: int
    approved_by: str
    provenance: ProvenanceRecord

    def __post_init__(self) -> None:
        for field_name in ("threshold_id", "metric", "unit", "approved_by"):
            object.__setattr__(self, field_name, _text(
                getattr(self, field_name), "threshold.%s" % field_name))
        if not isinstance(self.domain, CalibrationDomain):
            object.__setattr__(self, "domain", CalibrationDomain(self.domain))
        if not isinstance(self.operator, ThresholdOperator):
            object.__setattr__(self, "operator",
                               ThresholdOperator(self.operator))
        object.__setattr__(self, "value", _finite(
            self.value, "threshold.value", nonnegative=True))
        if (isinstance(self.minimum_samples, bool)
                or not isinstance(self.minimum_samples, int)
                or self.minimum_samples <= 0):
            raise ValueError("threshold.minimum_samples must be a positive int")
        if not isinstance(self.provenance, ProvenanceRecord):
            raise ValueError("threshold provenance must be a ProvenanceRecord")

    @property
    def threshold_digest(self) -> str:
        return stable_digest(self.to_dict())

    @property
    def is_non_model_approved(self) -> bool:
        return (
            self.provenance.producer_kind not in _NON_MEASURING_PRODUCERS
            and self.provenance.rights.permits(*_REQUIRED_RIGHTS)
        )

    def to_dict(self) -> Dict[str, Any]:
        result = _canonical(self)
        result["is_non_model_approved"] = self.is_non_model_approved
        return result


@dataclass(frozen=True)
class ValidationRequirement:
    test_kind: str
    metric: str
    unit: str
    minimum_samples: int

    def __post_init__(self) -> None:
        for field_name in ("test_kind", "metric", "unit"):
            object.__setattr__(self, field_name, _text(
                getattr(self, field_name), "requirement.%s" % field_name))
        if (isinstance(self.minimum_samples, bool)
                or not isinstance(self.minimum_samples, int)
                or self.minimum_samples <= 0):
            raise ValueError("requirement.minimum_samples must be positive")


@dataclass(frozen=True)
class ValidationPlan:
    plan_id: str
    domain: CalibrationDomain
    required_material_properties: Tuple[str, ...]
    requirements: Tuple[ValidationRequirement, ...]
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text(self.plan_id, "plan_id"))
        object.__setattr__(self, "description", _text(
            self.description, "plan.description"))
        if not isinstance(self.domain, CalibrationDomain):
            object.__setattr__(self, "domain", CalibrationDomain(self.domain))
        if not isinstance(self.required_material_properties, tuple):
            object.__setattr__(self, "required_material_properties",
                               tuple(self.required_material_properties))
        properties = tuple(sorted({_text(item, "required property")
                                   for item in self.required_material_properties}))
        unknown = [item for item in properties
                   if item not in MATERIAL_PROPERTY_UNITS]
        if unknown:
            raise ValueError("unknown required properties: %s" % unknown)
        object.__setattr__(self, "required_material_properties", properties)
        if not isinstance(self.requirements, tuple):
            object.__setattr__(self, "requirements", tuple(self.requirements))
        if not self.requirements:
            raise ValueError("validation plan needs test requirements")
        if any(not isinstance(row, ValidationRequirement)
               for row in self.requirements):
            raise ValueError("requirements must be ValidationRequirement")

    @property
    def plan_digest(self) -> str:
        return stable_digest(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "domain": self.domain.value,
            "required_material_properties": list(
                self.required_material_properties),
            "requirements": [
                _canonical(row) for row in sorted(
                    self.requirements,
                    key=lambda item: (item.test_kind, item.metric, item.unit))
            ],
            "description": self.description,
        }


def _requirements(*rows: Tuple[str, str, str, int]
                  ) -> Tuple[ValidationRequirement, ...]:
    return tuple(ValidationRequirement(*row) for row in rows)


_VALIDATION_PLANS: Mapping[CalibrationDomain, ValidationPlan] = {
    CalibrationDomain.MATERIAL: ValidationPlan(
        "material-lab-v1", CalibrationDomain.MATERIAL,
        REQUIRED_MATERIAL_PROPERTIES,
        _requirements(
            ("composition_assay", "composition_repeatability_percent", "%", 2),
            ("thickness_measurement", "thickness_repeatability_percent", "%", 3),
            ("stretch_test", "stretch_repeatability_percent", "%", 3),
            ("friction_test", "friction_repeatability_percent", "%", 3),
            ("bending_test", "bending_repeatability_percent", "%", 3),
        ),
        "Measure composition, thickness, directional stretch, friction, and "
        "directional bending with repeatability checks.",
    ),
    CalibrationDomain.SEAM: ValidationPlan(
        "seam-bench-v1", CalibrationDomain.SEAM,
        REQUIRED_MATERIAL_PROPERTIES,
        _requirements(
            ("seam_tension", "seam_strength_relative_error_percent", "%", 3),
            ("seam_slippage", "seam_slippage_relative_error_percent", "%", 3),
            ("seam_puckering", "seam_puckering_relative_error_percent", "%", 3),
            ("seam_fatigue", "seam_fatigue_relative_error_percent", "%", 3),
        ),
        "Measure strength, slippage, puckering, and cyclic fatigue on the "
        "named fabric/thread/stitch construction.",
    ),
    CalibrationDomain.WIND_TUNNEL: ValidationPlan(
        "wind-tunnel-v1", CalibrationDomain.WIND_TUNNEL,
        REQUIRED_MATERIAL_PROPERTIES,
        _requirements(
            ("force_balance", "drag_relative_error_percent", "%", 3),
            ("pressure_taps", "pressure_rmse_pa", "Pa", 3),
            ("motion_tracking", "displacement_rmse_m", "m", 3),
        ),
        "Record boundary conditions, force balance, pressure taps, and cloth "
        "motion tracking for the same specimen and material calibration.",
    ),
    CalibrationDomain.REAL_CLOTH: ValidationPlan(
        "real-cloth-validation-v1", CalibrationDomain.REAL_CLOTH,
        REQUIRED_MATERIAL_PROPERTIES,
        _requirements(
            ("static_drape", "shape_relative_error_percent", "%", 3),
            ("dynamic_drape", "displacement_relative_error_percent", "%", 3),
            ("seam_response", "seam_relative_error_percent", "%", 3),
        ),
        "Compare simulation and physical specimens for static shape, dynamic "
        "motion, and seam response without treating simulation as measurement.",
    ),
}


def validation_plan(domain: CalibrationDomain) -> ValidationPlan:
    if not isinstance(domain, CalibrationDomain):
        domain = CalibrationDomain(domain)
    return _VALIDATION_PLANS[domain]


@dataclass(frozen=True)
class ClaimRequest:
    claim_id: str
    subject_id: str
    claim_kind: ClaimKind
    material_properties: Tuple[MaterialPropertyInput, ...]
    datasets: Tuple[CalibrationDataset, ...]
    thresholds: Tuple[AcceptanceThreshold, ...]
    requested_error_percent: Optional[float] = None
    plan: Optional[ValidationPlan] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text(self.claim_id, "claim_id"))
        object.__setattr__(self, "subject_id", _text(
            self.subject_id, "subject_id"))
        if not isinstance(self.claim_kind, ClaimKind):
            object.__setattr__(self, "claim_kind", ClaimKind(self.claim_kind))
        for field_name, expected in (
            ("material_properties", MaterialPropertyInput),
            ("datasets", CalibrationDataset),
            ("thresholds", AcceptanceThreshold),
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                value = tuple(value)
                object.__setattr__(self, field_name, value)
            if any(not isinstance(item, expected) for item in value):
                raise ValueError("%s has an invalid typed item" % field_name)
        domain = _CLAIM_DOMAIN[self.claim_kind]
        if any(dataset.domain != domain for dataset in self.datasets):
            raise ValueError("all datasets must match the claim domain")
        if any(threshold.domain != domain for threshold in self.thresholds):
            raise ValueError("all thresholds must match the claim domain")
        selected_plan = self.plan or validation_plan(domain)
        if selected_plan.domain != domain:
            raise ValueError("validation plan domain must match claim")
        object.__setattr__(self, "plan", selected_plan)
        if self.claim_kind == ClaimKind.REAL_CLOTH_ERROR_BOUND:
            if self.requested_error_percent is None:
                raise ValueError("real-cloth error claim needs requested_error_percent")
            object.__setattr__(self, "requested_error_percent", _finite(
                self.requested_error_percent, "requested_error_percent",
                positive=True))
        elif self.requested_error_percent is not None:
            object.__setattr__(self, "requested_error_percent", _finite(
                self.requested_error_percent, "requested_error_percent",
                positive=True))

    @property
    def domain(self) -> CalibrationDomain:
        return _CLAIM_DOMAIN[self.claim_kind]

    def semantic_payload(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "claim_id": self.claim_id,
            "subject_id": self.subject_id,
            "claim_kind": self.claim_kind.value,
            "domain": self.domain.value,
            "material_properties": [
                row.to_dict() for row in sorted(
                    self.material_properties,
                    key=lambda item: item.evidence_digest)
            ],
            "datasets": [
                row.to_dict() for row in sorted(
                    self.datasets, key=lambda item: item.dataset_digest)
            ],
            "thresholds": [
                row.to_dict() for row in sorted(
                    self.thresholds, key=lambda item: item.threshold_digest)
            ],
            "requested_error_percent": self.requested_error_percent,
            "plan": self.plan.to_dict(),
        }

    @property
    def request_digest(self) -> str:
        return stable_digest(self.semantic_payload())


def reduce_material_properties(
        properties: Sequence[MaterialPropertyInput]) -> Dict[str, Any]:
    """Reduce evidence deterministically while retaining every disagreement."""
    groups: Dict[str, list] = {}
    for item in properties:
        if not isinstance(item, MaterialPropertyInput):
            raise ValueError("properties must contain MaterialPropertyInput")
        groups.setdefault(item.property_name, []).append(item)

    entries = []
    conflicts = []
    for name in sorted(groups):
        evidence = sorted(groups[name], key=lambda item: item.evidence_digest)
        variants: Dict[str, Dict[str, Any]] = {}
        for item in evidence:
            semantic_value = {
                "value": _canonical(item.value),
                "unit": item.unit,
                "conditions": _canonical(item.conditions),
            }
            variants.setdefault(stable_digest(semantic_value), semantic_value)
        if len(variants) > 1:
            state = "CONTESTED"
        elif any(item.effective_authority == EvidenceAuthority.MEASURED
                 for item in evidence):
            state = EvidenceAuthority.MEASURED.value
        else:
            state = EvidenceAuthority.PROPOSED.value
        entry = {
            "property_name": name,
            "state": state,
            "aggregate_operation": "NONE",
            "evidence": [item.to_dict() for item in evidence],
            "evidence_digests": [item.evidence_digest for item in evidence],
            "distinct_values": [variants[key] for key in sorted(variants)],
            "single_supported_value": (
                next(iter(variants.values())) if len(variants) == 1 else None),
        }
        entry["entry_digest"] = stable_digest(entry)
        entries.append(entry)
        if state == "CONTESTED":
            conflicts.append({
                "property_name": name,
                "entry_digest": entry["entry_digest"],
                "evidence_digests": entry["evidence_digests"],
                "distinct_values": entry["distinct_values"],
            })
    result = {
        "schema": PROPERTY_REDUCTION_SCHEMA,
        "entries": entries,
        "conflicts": conflicts,
        "conflicts_preserved": True,
        "averaging_performed": False,
    }
    result["reduction_digest"] = stable_digest(result)
    return result


def _rights_cleared(provenance: ProvenanceRecord) -> bool:
    return provenance.rights.permits(*_REQUIRED_RIGHTS)


def _reason(code: str, target: str, detail: str,
            **extra: Any) -> Dict[str, Any]:
    result = {"code": code, "target": target, "detail": detail}
    result.update(extra)
    return result


def _deduplicate_reasons(rows: Iterable[Mapping[str, Any]]) -> list:
    by_digest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        canonical = _canonical(row)
        by_digest.setdefault(stable_digest(canonical), canonical)
    return [by_digest[key] for key in sorted(by_digest)]


def _observation_conflicts(datasets: Sequence[CalibrationDataset]) -> list:
    groups: Dict[Tuple[str, str, str], list] = {}
    for dataset in datasets:
        for test in dataset.tests:
            for observation in test.observations:
                key = (test.test_kind, observation.metric,
                       observation.sample_id)
                groups.setdefault(key, []).append(observation)
    conflicts = []
    for key in sorted(groups):
        observations = sorted(
            groups[key], key=lambda item: item.observation_digest)
        variants = {
            stable_digest({"value": row.value, "unit": row.unit,
                           "conditions": row.conditions})
            for row in observations
        }
        if len(variants) > 1:
            conflicts.append({
                "test_kind": key[0],
                "metric": key[1],
                "sample_id": key[2],
                "observation_digests": [
                    row.observation_digest for row in observations],
                "observations": [row.to_dict() for row in observations],
                "aggregate_operation": "NONE",
            })
    return conflicts


def _resolution_request(request: ClaimRequest, reasons: Sequence[Mapping[str, Any]]
                        ) -> Dict[str, Any]:
    reason_codes = sorted({str(row["code"]) for row in reasons})
    options = [
        {
            "kind": ResolutionKind.MEASURE.value,
            "can_satisfy_claim": True,
            "description": "Supply explicit non-model measurements, units, "
                           "rights, and acceptance evidence.",
        },
        {
            "kind": ResolutionKind.CONNECT_PROVIDER.value,
            "can_satisfy_claim": True,
            "description": "Connect a rights-cleared measurement or laboratory "
                           "provider; provider data remains subject to this gate.",
        },
        {
            "kind": ResolutionKind.BOUNDED_ALTERNATIVES.value,
            "can_satisfy_claim": False,
            "description": "Run named proposed scenarios without making a "
                           "calibrated or bounded-error claim.",
        },
        {
            "kind": ResolutionKind.TYPED_STOP.value,
            "can_satisfy_claim": False,
            "description": "Stop with the missing evidence and claim boundary "
                           "recorded in provenance.",
        },
    ]
    request_id = stable_digest({
        "claim_request_digest": request.request_digest,
        "reason_codes": reason_codes,
        "options": options,
    })
    result = {
        "schema": RESOLUTION_SCHEMA,
        "request_id": request_id,
        "claim_id": request.claim_id,
        "claim_kind": request.claim_kind.value,
        "blocking_reason_codes": reason_codes,
        "options": options,
        "recommended": (
            ResolutionKind.CONNECT_PROVIDER.value
            if any("RIGHTS" in code or "DATASET" in code
                   for code in reason_codes)
            else ResolutionKind.MEASURE.value
        ),
        "model_may_author_measurements": False,
        "bounded_alternatives_are_calibration": False,
    }
    result["resolution_digest"] = stable_digest(result)
    return result


def _threshold_passes(threshold: AcceptanceThreshold, value: float) -> bool:
    if threshold.operator == ThresholdOperator.MAXIMUM:
        return value <= threshold.value
    return value >= threshold.value


def assess_claim(request: ClaimRequest) -> Dict[str, Any]:
    """Gate a calibrated claim against explicit measurement evidence.

    The returned ``authorized_claim`` is ``None`` unless every required check
    succeeds.  Proposed data is still returned for comparison, but never
    contributes to a measurement count.
    """
    if not isinstance(request, ClaimRequest):
        raise ValueError("request must be a ClaimRequest")

    reasons = []
    property_reduction = reduce_material_properties(
        request.material_properties)
    entries = {row["property_name"]: row
               for row in property_reduction["entries"]}

    properties_by_name: Dict[str, list] = {}
    for item in request.material_properties:
        properties_by_name.setdefault(item.property_name, []).append(item)
    for name in request.plan.required_material_properties:
        target = "material.%s" % name
        entry = entries.get(name)
        if entry is None:
            reasons.append(_reason(
                "MISSING_MATERIAL_PROPERTY", target,
                "required material property has no evidence"))
            continue
        if entry["state"] == "CONTESTED":
            reasons.append(_reason(
                "CONTESTED_MATERIAL_PROPERTY", target,
                "material sources disagree; values were preserved, not averaged",
                evidence_digests=entry["evidence_digests"]))
            continue
        measured = [
            item for item in properties_by_name[name]
            if item.effective_authority == EvidenceAuthority.MEASURED
        ]
        if not measured:
            reasons.append(_reason(
                "PROPOSED_MATERIAL_PROPERTY", target,
                "only proposed/model/simulation evidence is available"))
            continue
        if not any(_rights_cleared(item.provenance) for item in measured):
            reasons.append(_reason(
                "MATERIAL_RIGHTS_NOT_CLEARED", target,
                "measured property lacks calibration and claim-validation rights"))

    domain_datasets = tuple(sorted(
        request.datasets, key=lambda item: item.dataset_digest))
    if not domain_datasets:
        reasons.append(_reason(
            "MISSING_CALIBRATION_DATASET", request.domain.value,
            "no typed calibration dataset was supplied"))

    for dataset in domain_datasets:
        if dataset.provenance.producer_kind in _NON_MEASURING_PRODUCERS:
            reasons.append(_reason(
                "DATASET_NOT_NON_MODEL", dataset.dataset_id,
                "model/simulation output may index evidence but cannot certify "
                "a calibration dataset"))
        if not _rights_cleared(dataset.provenance):
            reasons.append(_reason(
                "DATASET_RIGHTS_NOT_CLEARED", dataset.dataset_id,
                "dataset provenance does not permit calibration claims"))

    observation_conflicts = _observation_conflicts(domain_datasets)
    for conflict in observation_conflicts:
        reasons.append(_reason(
            "CONTESTED_CALIBRATION_OBSERVATION",
            "%s.%s.%s" % (conflict["test_kind"], conflict["metric"],
                           conflict["sample_id"]),
            "test observations disagree; values were preserved, not averaged",
            observation_digests=conflict["observation_digests"]))

    thresholds_by_metric: Dict[str, list] = {}
    for threshold in request.thresholds:
        thresholds_by_metric.setdefault(threshold.metric, []).append(threshold)

    validation_checks = []
    for requirement in sorted(
            request.plan.requirements,
            key=lambda row: (row.test_kind, row.metric, row.unit)):
        target = "%s.%s" % (requirement.test_kind, requirement.metric)
        matching_tests = [
            (dataset, test)
            for dataset in domain_datasets for test in dataset.tests
            if test.test_kind == requirement.test_kind
        ]
        if not matching_tests:
            reasons.append(_reason(
                "MISSING_VALIDATION_TEST", target,
                "required physical test was not supplied"))

        threshold_rows = sorted(
            thresholds_by_metric.get(requirement.metric, []),
            key=lambda item: item.threshold_digest)
        threshold = None
        threshold_variants = {
            stable_digest({"operator": row.operator.value,
                           "value": row.value, "unit": row.unit,
                           "minimum_samples": row.minimum_samples})
            for row in threshold_rows
        }
        if not threshold_rows:
            reasons.append(_reason(
                "MISSING_ACCEPTANCE_THRESHOLD", target,
                "required metric has no explicit acceptance threshold"))
        elif len(threshold_variants) > 1:
            reasons.append(_reason(
                "CONTESTED_ACCEPTANCE_THRESHOLD", target,
                "acceptance thresholds disagree and were not collapsed",
                threshold_digests=[row.threshold_digest
                                   for row in threshold_rows]))
        else:
            approved = [row for row in threshold_rows
                        if row.is_non_model_approved]
            if not approved:
                reasons.append(_reason(
                    "THRESHOLD_NOT_NON_MODEL_APPROVED", target,
                    "model/simulation-proposed threshold cannot authorize a claim"))
            else:
                threshold = approved[0]
                if threshold.unit != requirement.unit:
                    reasons.append(_reason(
                        "THRESHOLD_UNIT_MISMATCH", target,
                        "threshold unit does not match the validation plan",
                        expected=requirement.unit, actual=threshold.unit))

        all_observations = []
        counted_observations = []
        for dataset, test in matching_tests:
            test_rights = _rights_cleared(test.provenance)
            if test.provenance.producer_kind in _NON_MEASURING_PRODUCERS:
                reasons.append(_reason(
                    "TEST_NOT_NON_MODEL", test.test_id,
                    "model/simulation output cannot certify a physical test"))
            if not test_rights:
                reasons.append(_reason(
                    "TEST_RIGHTS_NOT_CLEARED", test.test_id,
                    "test provenance does not permit calibration claims"))
            for observation in test.observations:
                if observation.metric != requirement.metric:
                    continue
                all_observations.append(observation)
                if observation.unit != requirement.unit:
                    reasons.append(_reason(
                        "OBSERVATION_UNIT_MISMATCH", target,
                        "observation unit does not match the validation plan",
                        observation_id=observation.observation_id,
                        expected=requirement.unit, actual=observation.unit))
                    continue
                if (observation.effective_authority == EvidenceAuthority.MEASURED
                        and _rights_cleared(observation.provenance)
                        and test_rights
                        and test.provenance.producer_kind
                        not in _NON_MEASURING_PRODUCERS
                        and dataset.provenance.producer_kind
                        not in _NON_MEASURING_PRODUCERS
                        and _rights_cleared(dataset.provenance)):
                    counted_observations.append(observation)

        required_count = max(
            requirement.minimum_samples,
            threshold.minimum_samples if threshold is not None else 1,
        )
        if len(counted_observations) < required_count:
            reasons.append(_reason(
                "INSUFFICIENT_NON_MODEL_MEASUREMENTS", target,
                "model/simulation/proposed rows do not count as measurements",
                required=required_count, actual=len(counted_observations)))

        outside = []
        if threshold is not None:
            outside = [row for row in counted_observations
                       if not _threshold_passes(threshold, row.value)]
            if outside:
                reasons.append(_reason(
                    "MEASUREMENT_OUTSIDE_THRESHOLD", target,
                    "at least one measured sample fails the explicit threshold",
                    observation_digests=[row.observation_digest
                                         for row in outside]))

        validation_checks.append({
            "test_kind": requirement.test_kind,
            "metric": requirement.metric,
            "unit": requirement.unit,
            "required_samples": required_count,
            "all_observations": [
                row.to_dict() for row in sorted(
                    all_observations,
                    key=lambda item: item.observation_digest)
            ],
            "counted_measurement_digests": sorted(
                row.observation_digest for row in counted_observations),
            "threshold": threshold.to_dict() if threshold is not None else None,
            "outside_threshold_digests": sorted(
                row.observation_digest for row in outside),
            "averaging_performed": False,
        })

    if request.claim_kind == ClaimKind.REAL_CLOTH_ERROR_BOUND:
        requested = float(request.requested_error_percent)
        percent_thresholds = [
            row for row in request.thresholds
            if row.unit == "%" and row.is_non_model_approved
        ]
        if not percent_thresholds:
            reasons.append(_reason(
                "MISSING_REAL_CLOTH_ERROR_THRESHOLD", "real_cloth.error_percent",
                "a real-cloth error claim needs measured percent thresholds"))
        for threshold in percent_thresholds:
            if (threshold.operator != ThresholdOperator.MAXIMUM
                    or threshold.value > requested):
                reasons.append(_reason(
                    "REQUESTED_ERROR_BOUND_NOT_COVERED", threshold.metric,
                    "acceptance threshold is weaker than the requested error bound",
                    requested_error_percent=requested,
                    threshold_value=threshold.value,
                    operator=threshold.operator.value))

    reasons = _deduplicate_reasons(reasons)
    authorized = not reasons
    authorized_claim: Optional[Dict[str, Any]] = None
    if authorized:
        authorized_claim = {
            "claim_kind": request.claim_kind.value,
            "subject_id": request.subject_id,
            "authority": EvidenceAuthority.MEASURED.value,
            "basis": "explicit_non_model_measurements_and_acceptance_thresholds",
            "plan_digest": request.plan.plan_digest,
        }
        if request.claim_kind == ClaimKind.REAL_CLOTH_ERROR_BOUND:
            authorized_claim["maximum_error_percent"] = (
                request.requested_error_percent)
            authorized_claim["few_percent_claim"] = (
                request.requested_error_percent <= 5.0)
        authorized_claim["claim_digest"] = stable_digest(authorized_claim)

    result: Dict[str, Any] = {
        "schema": DECISION_SCHEMA,
        "verdict": CLAIM_AUTHORIZED if authorized else CLAIM_BLOCKED,
        "claim_authorized": authorized,
        "claim_authority": (
            EvidenceAuthority.MEASURED.value if authorized else "NONE"),
        "claim_request_digest": request.request_digest,
        "claim_kind": request.claim_kind.value,
        "domain": request.domain.value,
        "validation_plan": request.plan.to_dict(),
        "property_reduction": property_reduction,
        "observation_conflicts": observation_conflicts,
        "validation_checks": validation_checks,
        "blocking_reasons": reasons,
        "authorized_claim": authorized_claim,
        "truth_contract": {
            "model_authority_ceiling": EvidenceAuthority.PROPOSED.value,
            "simulation_is_measurement": False,
            "conflicts_are_averaged": False,
            "bounded_alternatives_authorize_claim": False,
            "few_percent_claim_requires_non_model_measurements": True,
            "few_percent_claim_requires_explicit_thresholds": True,
        },
    }
    result["resolution_request"] = (
        None if authorized else _resolution_request(request, reasons))
    result["decision_digest"] = stable_digest(result)
    return result


def capabilities() -> Dict[str, Any]:
    plans = {
        domain.value: plan.to_dict()
        for domain, plan in sorted(
            _VALIDATION_PLANS.items(), key=lambda pair: pair[0].value)
    }
    result = {
        "schema": SCHEMA,
        "claim_kinds": [item.value for item in ClaimKind],
        "validation_plans": plans,
        "required_material_properties": list(REQUIRED_MATERIAL_PROPERTIES),
        "authority": {
            "model_ceiling": EvidenceAuthority.PROPOSED.value,
            "simulation_ceiling": EvidenceAuthority.PROPOSED.value,
            "measured_requires_non_model_producer": True,
        },
        "reduction": {
            "deterministic": True,
            "order_independent": True,
            "conflicts_preserved": True,
            "averaging_performed": False,
        },
        "resolution_options": [item.value for item in ResolutionKind],
        "unobserved_is_imputed": False,
    }
    result["capability_digest"] = stable_digest(result)
    return result


__all__ = [
    "AcceptanceThreshold", "CalibrationDataset", "CalibrationDomain",
    "CalibrationObservation", "CalibrationTest", "ClaimKind", "ClaimRequest",
    "EvidenceAuthority", "MaterialPropertyInput", "ProducerKind",
    "ProvenanceRecord", "ResolutionKind", "RightsRecord", "ThresholdOperator",
    "ValidationPlan", "ValidationRequirement", "CLAIM_AUTHORIZED",
    "CLAIM_BLOCKED", "MATERIAL_PROPERTY_UNITS", "REQUIRED_MATERIAL_PROPERTIES",
    "assess_claim", "capabilities", "effective_authority",
    "reduce_material_properties", "stable_digest", "validation_plan",
]
