# -*- coding: utf-8 -*-
"""Deterministic anisotropic textile properties on mesh faces.

This module supplies constitutive inputs and small, inspectable calculations
for a cross-facet simulation.  It deliberately does *not* integrate motion,
resolve contact, or claim to be a cloth solver.  All public physical values use
SI units; angles are radians and strain is dimensionless.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Generic, Mapping, Optional, Tuple, TypeVar


Vec3 = Tuple[float, float, float]
FaceId = str
T = TypeVar("T")


class VerdictCode(str, Enum):
    """Machine-readable outcomes; REVIEW is intentionally not a pass."""

    PASS = "PASS"
    REVIEW = "REVIEW"
    INCOMPATIBLE = "INCOMPATIBLE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class Provenance:
    """Where a value came from, without pretending an estimate was observed."""

    source: str
    method: str
    revision: str = "1"
    assumptions: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("source", "method", "revision"):
            if not getattr(self, name).strip():
                raise ValueError(f"provenance.{name} must be non-empty")


@dataclass(frozen=True)
class Verdict(Generic[T]):
    code: VerdictCode
    reasons: Tuple[str, ...]
    value: Optional[T] = None
    provenance: Optional[Provenance] = None

    @property
    def accepted(self) -> bool:
        return self.code is VerdictCode.PASS


def _finite(name: str, value: float, low: float, high: float,
            *, include_low: bool = False) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    good_low = value >= low if include_low else value > low
    if not good_low or value > high:
        left = "[" if include_low else "("
        raise ValueError(f"{name} must be in {left}{low}, {high}]")


@dataclass(frozen=True)
class FaceMaterial:
    """One face's orthotropic material sample, expressed entirely in SI.

    ``*_stretch_limit`` is allowable engineering strain. ``*_modulus_n_m`` is
    membrane stiffness (force per unit length), and ``*_bending_n_m`` is the
    directional bending rigidity.  ``slip`` is a dimensionless 0..1 tendency:
    zero grips and one slips freely.
    """

    warp_stretch_limit: float
    weft_stretch_limit: float
    bias_stretch_limit: float
    warp_modulus_n_m: float
    weft_modulus_n_m: float
    bias_modulus_n_m: float
    warp_bending_n_m: float
    weft_bending_n_m: float
    bias_bending_n_m: float
    areal_density_kg_m2: float
    thickness_m: float
    friction_static: float
    friction_dynamic: float
    slip: float
    permeability_m2: float
    damping_ratio: float
    warp_angle_rad: float = 0.0
    provenance: Provenance = field(default_factory=lambda: Provenance(
        "unspecified", "declared"))

    def __post_init__(self) -> None:
        for axis in ("warp", "weft", "bias"):
            _finite(f"{axis}_stretch_limit",
                    getattr(self, f"{axis}_stretch_limit"), 0.0, 5.0)
            _finite(f"{axis}_modulus_n_m",
                    getattr(self, f"{axis}_modulus_n_m"), 0.0, 1.0e9)
            _finite(f"{axis}_bending_n_m",
                    getattr(self, f"{axis}_bending_n_m"), 0.0, 1.0e3,
                    include_low=True)
        _finite("areal_density_kg_m2", self.areal_density_kg_m2,
                0.0, 100.0)
        _finite("thickness_m", self.thickness_m, 0.0, 0.1)
        _finite("friction_static", self.friction_static, 0.0, 10.0,
                include_low=True)
        _finite("friction_dynamic", self.friction_dynamic, 0.0, 10.0,
                include_low=True)
        if self.friction_dynamic > self.friction_static:
            raise ValueError("friction_dynamic cannot exceed friction_static")
        _finite("slip", self.slip, 0.0, 1.0, include_low=True)
        _finite("permeability_m2", self.permeability_m2, 0.0, 1.0,
                include_low=True)
        _finite("damping_ratio", self.damping_ratio, 0.0, 1.0,
                include_low=True)
        if not math.isfinite(self.warp_angle_rad):
            raise ValueError("warp_angle_rad must be finite")


@dataclass(frozen=True)
class StrainState:
    """Small in-plane strain tensor and directional curvature (1/m)."""

    xx: float
    yy: float
    xy: float = 0.0  # tensor shear; engineering shear is 2*xy
    curvature_warp_1_m: float = 0.0
    curvature_weft_1_m: float = 0.0
    curvature_bias_1_m: float = 0.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (
                self.xx, self.yy, self.xy, self.curvature_warp_1_m,
                self.curvature_weft_1_m, self.curvature_bias_1_m)):
            raise ValueError("strain and curvature values must be finite")


@dataclass(frozen=True)
class StressResponse:
    """Membrane resultants (N/m), bending moments (N), and energy (J/m²)."""

    stress_xx_n_m: float
    stress_yy_n_m: float
    stress_xy_n_m: float
    warp_strain: float
    weft_strain: float
    bias_strain: float
    bending_moment_warp_n: float
    bending_moment_weft_n: float
    bending_moment_bias_n: float
    strain_energy_j_m2: float


@dataclass(frozen=True)
class GravityLoad:
    face_id: FaceId
    mass_kg: float
    force_n: Vec3


@dataclass(frozen=True)
class SeamMetrics:
    stretch_limit_ratio: float
    thickness_ratio: float
    bending_ratio: float
    friction_difference: float


@dataclass(frozen=True)
class TextileField:
    """A default material plus deterministic, spatial per-face overrides."""

    default: FaceMaterial
    faces: Mapping[FaceId, FaceMaterial] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=lambda: Provenance(
        "material-field", "declared per-face field"))

    def __post_init__(self) -> None:
        copied = dict(self.faces)
        if any(not isinstance(k, str) or not k for k in copied):
            raise ValueError("face ids must be non-empty strings")
        if any(not isinstance(v, FaceMaterial) for v in copied.values()):
            raise TypeError("every face value must be FaceMaterial")
        object.__setattr__(self, "faces", copied)

    def at(self, face_id: FaceId) -> FaceMaterial:
        if not isinstance(face_id, str) or not face_id:
            raise ValueError("face_id must be a non-empty string")
        return self.faces.get(face_id, self.default)

    def stress_response(self, face_id: FaceId,
                        strain: StrainState) -> Verdict[StressResponse]:
        mat = self.at(face_id)
        c, s = math.cos(mat.warp_angle_rad), math.sin(mat.warp_angle_rad)
        # Project the global strain tensor onto warp, weft and +45 degree bias.
        ew = c*c*strain.xx + 2*c*s*strain.xy + s*s*strain.yy
        ef = s*s*strain.xx - 2*c*s*strain.xy + c*c*strain.yy
        bx, by = (c-s) / math.sqrt(2.0), (s+c) / math.sqrt(2.0)
        eb = bx*bx*strain.xx + 2*bx*by*strain.xy + by*by*strain.yy
        nw = mat.warp_modulus_n_m * ew
        nf = mat.weft_modulus_n_m * ef
        nb = mat.bias_modulus_n_m * eb
        # Sum three directional rank-one stresses in global coordinates.
        sx = nw*c*c + nf*s*s + nb*bx*bx
        sy = nw*s*s + nf*c*c + nb*by*by
        txy = nw*c*s - nf*c*s + nb*bx*by
        energy = 0.5 * (nw*ew + nf*ef + nb*eb)
        response = StressResponse(
            sx, sy, txy, ew, ef, eb,
            mat.warp_bending_n_m * strain.curvature_warp_1_m,
            mat.weft_bending_n_m * strain.curvature_weft_1_m,
            mat.bias_bending_n_m * strain.curvature_bias_1_m,
            energy)
        exceeded = tuple(axis for axis, actual, limit in (
            ("warp", abs(ew), mat.warp_stretch_limit),
            ("weft", abs(ef), mat.weft_stretch_limit),
            ("bias", abs(eb), mat.bias_stretch_limit)) if actual > limit)
        if exceeded:
            return Verdict(VerdictCode.REVIEW,
                           tuple(f"{a} stretch limit exceeded" for a in exceeded),
                           response, mat.provenance)
        return Verdict(VerdictCode.PASS, ("within directional stretch limits",),
                       response, mat.provenance)

    def gravity_load(self, face_id: FaceId, area_m2: float,
                     gravity_m_s2: Vec3 = (0.0, -9.80665, 0.0)
                     ) -> Verdict[GravityLoad]:
        _finite("area_m2", area_m2, 0.0, 1.0e9)
        if len(gravity_m_s2) != 3 or not all(math.isfinite(v)
                                             for v in gravity_m_s2):
            raise ValueError("gravity_m_s2 must contain three finite values")
        mat = self.at(face_id)
        mass = mat.areal_density_kg_m2 * area_m2
        load = GravityLoad(face_id, mass,
                           tuple(mass * v for v in gravity_m_s2))
        return Verdict(VerdictCode.PASS, ("areal-density gravity load",),
                       load, mat.provenance)

    def seam_compatibility(self, face_a: FaceId, face_b: FaceId, *,
                           direction_a: str = "warp",
                           direction_b: str = "warp") -> Verdict[SeamMetrics]:
        a, b = self.at(face_a), self.at(face_b)
        valid = ("warp", "weft", "bias")
        if direction_a not in valid or direction_b not in valid:
            return Verdict(VerdictCode.INVALID,
                           ("seam direction must be warp, weft, or bias",),
                           provenance=self.provenance)

        def directional(m: FaceMaterial, direction: str) -> Tuple[float, float]:
            return (getattr(m, f"{direction}_stretch_limit"),
                    getattr(m, f"{direction}_bending_n_m"))

        sa, ba = directional(a, direction_a)
        sb, bb = directional(b, direction_b)

        def ratio(x: float, y: float) -> float:
            return max(x, y) / max(min(x, y), 1.0e-15)

        metrics = SeamMetrics(ratio(sa, sb), ratio(a.thickness_m, b.thickness_m),
                              ratio(ba, bb),
                              abs(a.friction_dynamic - b.friction_dynamic))
        hard = []
        review = []
        if metrics.stretch_limit_ratio > 3.0:
            hard.append("directional stretch mismatch exceeds 3:1")
        elif metrics.stretch_limit_ratio > 1.75:
            review.append("directional stretch mismatch exceeds 1.75:1")
        if metrics.thickness_ratio > 4.0:
            hard.append("thickness mismatch exceeds 4:1")
        elif metrics.thickness_ratio > 2.0:
            review.append("thickness mismatch exceeds 2:1")
        if metrics.bending_ratio > 8.0:
            review.append("bending mismatch exceeds 8:1")
        if metrics.friction_difference > 0.5:
            review.append("dynamic friction difference exceeds 0.5")
        if hard:
            return Verdict(VerdictCode.INCOMPATIBLE, tuple(hard + review), metrics,
                           self.provenance)
        if review:
            return Verdict(VerdictCode.REVIEW, tuple(review), metrics,
                           self.provenance)
        return Verdict(VerdictCode.PASS, ("material sides are seam-compatible",),
                       metrics, self.provenance)


def jersey() -> FaceMaterial:
    """Deterministic illustrative jersey profile, not a laboratory claim."""
    p = Provenance("built-in illustrative profile", "engineering estimate",
                   assumptions=("not batch-specific", "verify before manufacture"))
    return FaceMaterial(0.65, 0.85, 0.95, 180.0, 120.0, 70.0,
                        1.2e-5, 9.0e-6, 5.0e-6, 0.180, 0.0007,
                        0.55, 0.40, 0.55, 2.0e-10, 0.12,
                        provenance=p)


def melton() -> FaceMaterial:
    """Deterministic illustrative wool-melton profile, not a lab claim."""
    p = Provenance("built-in illustrative profile", "engineering estimate",
                   assumptions=("not batch-specific", "verify before manufacture"))
    return FaceMaterial(0.08, 0.10, 0.16, 2400.0, 1800.0, 650.0,
                        8.0e-4, 6.0e-4, 2.0e-4, 0.520, 0.0024,
                        0.72, 0.58, 0.24, 2.0e-12, 0.20,
                        provenance=p)


@dataclass(frozen=True)
class MaterialComparison:
    area_m2: float
    jersey_mass_kg: float
    melton_mass_kg: float
    jersey_stress_norm_n_m: float
    melton_stress_norm_n_m: float
    jersey_bending_moment_n: float
    melton_bending_moment_n: float


def compare_jersey_melton(*, area_m2: float = 0.25,
                          strain: StrainState = StrainState(
                              0.03, 0.01, 0.005,
                              curvature_warp_1_m=2.0)
                          ) -> Verdict[MaterialComparison]:
    """Compare constitutive inputs on identical geometry; no drape is solved."""
    _finite("area_m2", area_m2, 0.0, 1.0e9)
    jf, mf = TextileField(jersey()), TextileField(melton())
    jr = jf.stress_response("same-face", strain).value
    mr = mf.stress_response("same-face", strain).value
    assert jr is not None and mr is not None
    value = MaterialComparison(
        area_m2, jersey().areal_density_kg_m2 * area_m2,
        melton().areal_density_kg_m2 * area_m2,
        math.hypot(jr.stress_xx_n_m, jr.stress_yy_n_m),
        math.hypot(mr.stress_xx_n_m, mr.stress_yy_n_m),
        jr.bending_moment_warp_n, mr.bending_moment_warp_n)
    return Verdict(VerdictCode.PASS,
                   ("same geometry produces distinct material response",
                    "comparison is constitutive only, not a cloth solve"),
                   value, jf.provenance)


__all__ = [
    "FaceMaterial", "GravityLoad", "MaterialComparison", "Provenance",
    "SeamMetrics", "StrainState", "StressResponse", "TextileField",
    "Verdict", "VerdictCode", "compare_jersey_melton", "jersey", "melton",
]
