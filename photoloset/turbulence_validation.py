# -*- coding: utf-8 -*-
"""Evidence-gated validation harness for :mod:`incompressible_fluid`.

The harness executes deterministic manufactured/known cases, measures the
discrete pressure projection, estimates grid-refinement order, and audits
energy and mass ledgers.  It deliberately separates those regression results
from external DNS or wind-tunnel validation.  Such claims require a complete,
digest-bound dataset manifest *and* a quantitative comparison within a stated
tolerance; a dataset name or citation alone is not evidence of agreement.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from . import incompressible_fluid


ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_TURBULENCE_VALIDATION_INPUT"
SOLVER_REFUSAL = "UNKNOWN_TURBULENCE_SOLVER_REFUSAL"
MANIFEST_REFUSAL = "UNKNOWN_TURBULENCE_DATASET_MANIFEST"
CLAIM_REFUSAL = "UNKNOWN_TURBULENCE_CLAIM_WITHOUT_EVIDENCE"
VALIDATION_FAILED = "UNKNOWN_TURBULENCE_VALIDATION_FAILED"
MANIFEST_SCHEMA = "fluid.validation-dataset.v1"
_HEX = frozenset("0123456789abcdef")


class _Invalid(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Describe checks and the claims they do not independently establish."""
    return {
        "verdict": ANSWER,
        "backend": "deterministic_python_stdlib_validation_harness",
        "checks": {
            "manufactured_divergence_free": True,
            "pressure_projection_reduction": True,
            "grid_refinement_observed_order": True,
            "gci_like_fine_grid_uncertainty": True,
            "kinetic_energy_ledger": True,
            "constant_density_mass_ledger": True,
            "dns_manifest_gate": True,
            "wind_tunnel_manifest_gate": True,
            "claim_evidence_gate": True,
        },
        "limits": {
            "harness_is_dns": False,
            "harness_is_wind_tunnel_validation": False,
            "gci_is_formal_asme_gci": False,
            "les_validated_by_manufactured_cases": False,
        },
        "solver_capabilities": incompressible_fluid.capabilities(),
    }


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def _number(value: Any, name: str, *, low: float | None = None,
            strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise _Invalid(f"{name} must be finite")
    if low is not None and (result <= low if strict else result < low):
        relation = ">" if strict else ">="
        raise _Invalid(f"{name} must be {relation} {low}")
    return result


def _resolution(value: Any, name: str = "resolution") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 4:
        raise _Invalid(f"{name} must be an integer >= 4")
    return value


def _taylor_green(resolution: int, amplitude: float,
                  domain_length_m: float) -> Tuple[Tuple[float, float, float], ...]:
    """Return a discrete-divergence-free periodic Taylor--Green field."""
    h = domain_length_m / resolution
    wave = 2.0 * math.pi / domain_length_m
    values = []
    for k in range(resolution):
        del k  # The manufactured case is extruded exactly in z.
        for j in range(resolution):
            y_face, y_center = (j + 1) * h, (j + 0.5) * h
            for i in range(resolution):
                x_face, x_center = (i + 1) * h, (i + 0.5) * h
                values.append((
                    amplitude * math.sin(wave * x_face) * math.cos(wave * y_center),
                    -amplitude * math.cos(wave * x_center) * math.sin(wave * y_face),
                    0.0,
                ))
    return tuple(values)


def _uniform(resolution: int, amplitude: float
             ) -> Tuple[Tuple[float, float, float], ...]:
    return ((amplitude, -0.5 * amplitude, 0.25 * amplitude),) * resolution**3


def manufactured_case(name: str, resolution: int, *, amplitude_m_s: float = 0.1,
                      domain_length_m: float = 1.0) -> Dict[str, Any]:
    """Build one immutable known case consumed by ``incompressible_fluid``."""
    try:
        n = _resolution(resolution)
        amplitude = _number(amplitude_m_s, "amplitude_m_s", low=0.0, strict=True)
        length = _number(domain_length_m, "domain_length_m", low=0.0, strict=True)
        if name == "uniform_periodic":
            velocity = _uniform(n, amplitude)
            expected = "exactly invariant under advection, viscosity, and projection"
        elif name == "taylor_green_periodic":
            velocity = _taylor_green(n, amplitude, length)
            expected = "discrete divergence-free Euler steady velocity after pressure balance"
        else:
            return _refusal(INVALID_INPUT, "unknown manufactured case", case=name)
        payload = {
            "case": name,
            "shape": [n, n, n],
            "domain_length_m": length,
            "cell_size_m": length / n,
            "amplitude_m_s": amplitude,
            "velocities_m_s": [list(value) for value in velocity],
            "boundary": "periodic",
            "expected_property": expected,
        }
        return {"verdict": ANSWER, "case": payload, "digest": _digest(payload)}
    except _Invalid as error:
        return _refusal(INVALID_INPUT, str(error))


def _solver_request(case: Mapping[str, Any], density: float, viscosity: float,
                    courant: float, pressure_iterations: int,
                    pressure_tolerance: float) -> Dict[str, Any]:
    dt = courant * case["cell_size_m"] / case["amplitude_m_s"]
    return {
        "shape": case["shape"],
        "cell_size_m": case["cell_size_m"],
        "density_kg_m3": density,
        "kinematic_viscosity_m2_s": viscosity,
        "time_step_s": dt,
        "velocities_m_s": case["velocities_m_s"],
        "boundary": case["boundary"],
        "cfl_safety": max(0.5, min(1.0, 2.0 * courant)),
        "pressure_iterations": pressure_iterations,
        "pressure_tolerance_s_inv": pressure_tolerance,
    }


def _rms_error(actual: Sequence[Sequence[float]],
               expected: Sequence[Sequence[float]]) -> float:
    if len(actual) != len(expected):
        raise _Invalid("solver output and manufactured field sizes differ")
    squared = []
    for left, right in zip(actual, expected):
        if len(left) != 3 or len(right) != 3:
            raise _Invalid("velocity records must have three components")
        squared.extend((float(a) - float(b))**2 for a, b in zip(left, right))
    return math.sqrt(math.fsum(squared) / len(squared))


def _kinetic_energy(velocities: Sequence[Sequence[float]], density: float,
                    cell_size: float) -> float:
    return 0.5 * density * cell_size**3 * math.fsum(
        math.fsum(float(component)**2 for component in velocity)
        for velocity in velocities)


def _projection_case(resolution: int, amplitude: float, domain_length: float,
                     density: float, pressure_iterations: int,
                     pressure_tolerance: float) -> Dict[str, Any]:
    h = domain_length / resolution
    wave = 2.0 * math.pi / domain_length
    values = []
    for _k in range(resolution):
        for _j in range(resolution):
            for i in range(resolution):
                x_face = (i + 1) * h
                values.append((amplitude * math.sin(wave * x_face), 0.0, 0.0))
    request = {
        "shape": [resolution] * 3, "cell_size_m": h,
        "density_kg_m3": density, "kinematic_viscosity_m2_s": 0.0,
        "time_step_s": 0.1 * h / amplitude,
        "velocities_m_s": values, "boundary": "periodic",
        "cfl_safety": 0.5, "pressure_iterations": pressure_iterations,
        "pressure_tolerance_s_inv": pressure_tolerance,
    }
    result = incompressible_fluid.step(request)
    if result.get("verdict") != ANSWER:
        return _refusal(SOLVER_REFUSAL, "projection case was refused", solver=result)
    before = result["diagnostics"]["divergence_before_projection"]["l2_rms_s_inv"]
    after = result["diagnostics"]["divergence_after_projection"]["l2_rms_s_inv"]
    ratio = 0.0 if before == 0.0 else after / before
    return {
        "verdict": ANSWER,
        "before_l2_rms_s_inv": before,
        "after_l2_rms_s_inv": after,
        "after_over_before": ratio,
        "pressure_residual": result["diagnostics"]["pressure_poisson"]
                             ["residual_rms_kg_m3_s2"],
        "passed": before > 0.0 and ratio <= 1.0e-5,
    }


def validate_dataset_manifest(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Fail closed on incomplete DNS/wind-tunnel evidence metadata."""
    if not isinstance(manifest, Mapping):
        return _refusal(MANIFEST_REFUSAL, "dataset manifest must be an object")
    required = ("schema", "dataset_id", "kind", "license", "lineage",
                "conditions", "measurements", "uncertainty", "checksum_sha256")
    missing = [field for field in required if field not in manifest]
    if missing:
        return _refusal(MANIFEST_REFUSAL, "dataset manifest fields are missing",
                        missing=missing)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        return _refusal(MANIFEST_REFUSAL, f"schema must be {MANIFEST_SCHEMA}")
    kind = manifest.get("kind")
    if kind not in ("dns", "wind_tunnel"):
        return _refusal(MANIFEST_REFUSAL, "kind must be dns or wind_tunnel")
    licence = manifest.get("license")
    if (not isinstance(licence, Mapping)
            or not isinstance(licence.get("url"), str) or not licence["url"].strip()
            or licence.get("commercial_use") not in ("allowed", "denied", "unknown")):
        return _refusal(MANIFEST_REFUSAL,
                        "license needs URL and typed commercial_use rights")
    if licence["commercial_use"] != "allowed":
        return _refusal(MANIFEST_REFUSAL,
                        "commercial use is not explicitly allowed",
                        commercial_use=licence["commercial_use"])
    lineage = manifest.get("lineage")
    if (not isinstance(lineage, Sequence) or isinstance(lineage, (str, bytes))
            or not lineage or any(not isinstance(item, Mapping)
                                  or not item.get("source") for item in lineage)):
        return _refusal(MANIFEST_REFUSAL, "lineage requires named source records")
    conditions = manifest.get("conditions")
    condition_fields = ("geometry", "boundary_conditions", "fluid_properties", "units")
    if (not isinstance(conditions, Mapping)
            or conditions.get("units") != "SI"
            or any(not conditions.get(field) for field in condition_fields[:-1])):
        return _refusal(MANIFEST_REFUSAL,
                        "conditions require geometry, boundaries, fluid properties, and SI units")
    measurements = manifest.get("measurements")
    common = {"velocity", "sampling", "coordinates"}
    specific = ({"pressure", "grid_resolution", "numerical_method", "convergence"}
                if kind == "dns" else
                {"force_or_pressure", "calibration", "facility"})
    measurement_fields = set(measurements) if isinstance(measurements, Mapping) else set()
    if not isinstance(measurements, Mapping) or not common | specific <= measurement_fields:
        return _refusal(MANIFEST_REFUSAL, "required measurements are missing",
                        missing=sorted((common | specific) - measurement_fields))
    uncertainty = manifest.get("uncertainty")
    if (not isinstance(uncertainty, Mapping)
            or not uncertainty.get("method") or "values" not in uncertainty):
        return _refusal(MANIFEST_REFUSAL,
                        "uncertainty needs a method and reported values")
    checksum = manifest.get("checksum_sha256")
    if (not isinstance(checksum, str) or len(checksum) != 64
            or any(character not in _HEX for character in checksum.lower())):
        return _refusal(MANIFEST_REFUSAL,
                        "checksum_sha256 must be a 64-character hexadecimal digest")
    normalized = json.loads(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return {"verdict": ANSWER, "kind": kind, "manifest": normalized,
            "manifest_digest": _digest(normalized), "legal_opinion": False}


def assess_claims(claims: Sequence[Mapping[str, Any]],
                  internal_evidence: Mapping[str, Any]) -> Dict[str, Any]:
    """Accept only claims bound to sufficient generated or external evidence."""
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        return _refusal(CLAIM_REFUSAL, "claims must be a sequence")
    reports = []
    refused = False
    internal_requirements = {
        "manufactured_cases_verified": "manufactured_cases",
        "pressure_projection_verified": "pressure_projection",
        "grid_convergence_observed": "grid_refinement",
        "mass_energy_ledgers_verified": "ledgers",
    }
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping) or not isinstance(claim.get("name"), str):
            reports.append({"index": index, "verdict": CLAIM_REFUSAL,
                            "why": "claim requires a typed name"})
            refused = True
            continue
        name = claim["name"]
        evidence = claim.get("evidence")
        if name in internal_requirements:
            key = internal_requirements[name]
            supplied = (isinstance(evidence, Sequence)
                        and not isinstance(evidence, (str, bytes)) and key in evidence)
            generated = internal_evidence.get(key)
            passed = isinstance(generated, Mapping) and generated.get("passed") is True
            if supplied and passed:
                reports.append({"name": name, "verdict": ANSWER,
                                "evidence_digest": _digest(generated)})
            else:
                reports.append({"name": name, "verdict": CLAIM_REFUSAL,
                                "why": f"claim needs passing generated evidence {key}"})
                refused = True
            continue
        if name in ("dns_agreement", "wind_tunnel_agreement"):
            expected_kind = "dns" if name == "dns_agreement" else "wind_tunnel"
            if not isinstance(evidence, Mapping):
                reports.append({"name": name, "verdict": CLAIM_REFUSAL,
                                "why": "external claim needs manifest and comparison evidence"})
                refused = True
                continue
            manifest_result = validate_dataset_manifest(evidence.get("dataset_manifest"))
            comparison = evidence.get("comparison")
            comparison_ok = False
            if isinstance(comparison, Mapping):
                try:
                    value = _number(comparison.get("value"), "comparison.value", low=0.0)
                    threshold = _number(comparison.get("threshold"),
                                        "comparison.threshold", low=0.0, strict=True)
                    samples = comparison.get("sample_count")
                    comparison_ok = (comparison.get("metric") in
                                     ("normalized_rmse", "relative_l2")
                                     and isinstance(samples, int) and not isinstance(samples, bool)
                                     and samples >= 16 and value <= threshold)
                except _Invalid:
                    comparison_ok = False
            accepted = (manifest_result.get("verdict") == ANSWER
                        and manifest_result.get("kind") == expected_kind
                        and comparison_ok)
            if accepted:
                reports.append({"name": name, "verdict": ANSWER,
                                "manifest_digest": manifest_result["manifest_digest"],
                                "comparison": copy.deepcopy(comparison)})
            else:
                reports.append({"name": name, "verdict": CLAIM_REFUSAL,
                                "why": "typed dataset rights and an in-tolerance comparison are required",
                                "manifest_gate": manifest_result})
                refused = True
            continue
        reports.append({"name": name, "verdict": CLAIM_REFUSAL,
                        "why": "claim is not supported by this harness"})
        refused = True
    return {"verdict": CLAIM_REFUSAL if refused else ANSWER, "claims": reports}


def validate(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the deterministic validation suite and optionally assess claims."""
    snapshot = copy.deepcopy(request)
    try:
        if not isinstance(request, Mapping):
            raise _Invalid("request must be an object")
        raw_resolutions = request.get("resolutions", (4, 8, 16))
        if (not isinstance(raw_resolutions, Sequence)
                or isinstance(raw_resolutions, (str, bytes))
                or len(raw_resolutions) != 3):
            raise _Invalid("resolutions must contain exactly three refinement levels")
        resolutions = tuple(_resolution(value, f"resolutions[{index}]")
                            for index, value in enumerate(raw_resolutions))
        if not resolutions[0] < resolutions[1] < resolutions[2]:
            raise _Invalid("resolutions must be strictly increasing")
        ratio_a = resolutions[1] / resolutions[0]
        ratio_b = resolutions[2] / resolutions[1]
        if abs(ratio_a - ratio_b) > 1.0e-12 or ratio_a <= 1.0:
            raise _Invalid("GCI-like estimate requires one constant refinement ratio")
        amplitude = _number(request.get("amplitude_m_s", 0.1), "amplitude_m_s",
                            low=0.0, strict=True)
        length = _number(request.get("domain_length_m", 1.0), "domain_length_m",
                         low=0.0, strict=True)
        density = _number(request.get("density_kg_m3", 1.2), "density_kg_m3",
                          low=0.0, strict=True)
        viscosity = _number(request.get("kinematic_viscosity_m2_s", 0.0),
                            "kinematic_viscosity_m2_s", low=0.0)
        courant = _number(request.get("courant", 0.1), "courant", low=0.0,
                          strict=True)
        if courant > 0.4:
            raise _Invalid("validation courant must be <= 0.4")
        iterations = request.get("pressure_iterations", 300)
        if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
            raise _Invalid("pressure_iterations must be a positive integer")
        pressure_tolerance = _number(request.get("pressure_tolerance_s_inv", 1.0e-8),
                                     "pressure_tolerance_s_inv", low=0.0)
        minimum_order = _number(request.get("minimum_observed_order", 1.0),
                                "minimum_observed_order", low=0.0)

        manufactured_reports = []
        errors = []
        ledger_reports = []

        # Uniform periodic flow is an exact invariant of every implemented
        # stage. It is distinct from the vortical refinement case below.
        uniform_made = manufactured_case("uniform_periodic", resolutions[0],
                                         amplitude_m_s=amplitude,
                                         domain_length_m=length)
        uniform_case = uniform_made["case"]
        uniform_request = _solver_request(uniform_case, density, viscosity, courant,
                                          iterations, pressure_tolerance)
        uniform_solved = incompressible_fluid.step(uniform_request)
        if uniform_solved.get("verdict") != ANSWER:
            return _refusal(SOLVER_REFUSAL, "solver refused uniform manufactured case",
                            solver=uniform_solved,
                            immutable_input_snapshot=snapshot)
        uniform_error = _rms_error(uniform_solved["state"]["velocities_m_s"],
                                   uniform_case["velocities_m_s"])
        uniform_divergence = (
            uniform_solved["diagnostics"]["divergence_after_projection"])
        manufactured_reports.append({
            "case": "uniform_periodic", "resolution": resolutions[0],
            "case_digest": uniform_made["digest"],
            "velocity_rms_error_m_s": uniform_error,
            "post_projection_divergence_l2_s_inv":
                uniform_divergence["l2_rms_s_inv"],
            "solver_terminal_verdict": uniform_solved["terminal_verdict"],
            "exact_invariance_passed": uniform_error <= 1.0e-12,
        })

        for resolution in resolutions:
            made = manufactured_case("taylor_green_periodic", resolution,
                                     amplitude_m_s=amplitude,
                                     domain_length_m=length)
            case = made["case"]
            solver_request = _solver_request(case, density, viscosity, courant,
                                             iterations, pressure_tolerance)
            solved = incompressible_fluid.step(solver_request)
            if solved.get("verdict") != ANSWER:
                return _refusal(SOLVER_REFUSAL,
                                f"solver refused resolution {resolution}",
                                solver=solved, immutable_input_snapshot=snapshot)
            error = _rms_error(solved["state"]["velocities_m_s"],
                               case["velocities_m_s"])
            errors.append(error)
            divergence = solved["diagnostics"]["divergence_after_projection"]
            initial_energy = _kinetic_energy(case["velocities_m_s"], density,
                                             case["cell_size_m"])
            final_energy = _kinetic_energy(solved["state"]["velocities_m_s"], density,
                                           case["cell_size_m"])
            mass = solved["diagnostics"]["mass_ledger"]
            manufactured_reports.append({
                "case": "taylor_green_periodic",
                "resolution": resolution, "case_digest": made["digest"],
                "velocity_rms_error_m_s": error,
                "post_projection_divergence_l2_s_inv": divergence["l2_rms_s_inv"],
                "solver_terminal_verdict": solved["terminal_verdict"],
            })
            ledger_reports.append({
                "resolution": resolution,
                "initial_kinetic_energy_j": initial_energy,
                "final_kinetic_energy_j": final_energy,
                "energy_change_j": final_energy - initial_energy,
                "initial_mass_kg": mass["initial_mass_kg"],
                "final_mass_kg": mass["final_mass_kg"],
                "mass_change_kg": mass["mass_change_kg"],
                "boundary_volume_balance_m3_s":
                    mass["projection_volume_balance_residual_m3_s"],
            })

        if any(error <= 0.0 for error in errors):
            raise _Invalid("observed order is undefined for zero refinement error")
        orders = (math.log(errors[0] / errors[1]) / math.log(ratio_a),
                  math.log(errors[1] / errors[2]) / math.log(ratio_a))
        observed = min(orders)
        gci = (math.inf if observed <= 0.0 else
               1.25 * errors[-1] / (ratio_a**observed - 1.0))
        refinement = {
            "resolutions": list(resolutions), "refinement_ratio": ratio_a,
            "time_step_scaling": "constant Courant; dt proportional to cell size",
            "rms_errors_m_s": errors, "pairwise_observed_orders": list(orders),
            "conservative_observed_order": observed,
            "gci_like_fine_uncertainty_m_s": gci,
            "formal_asme_gci": False,
            "passed": observed >= minimum_order and math.isfinite(gci),
        }
        manufactured_evidence = {
            "cases": manufactured_reports,
            "maximum_post_projection_divergence_l2_s_inv": max(
                report["post_projection_divergence_l2_s_inv"]
                for report in manufactured_reports),
            "passed": (uniform_error <= 1.0e-12
                       and all(report["post_projection_divergence_l2_s_inv"] <= 1.0e-6
                               for report in manufactured_reports)),
        }
        projection = _projection_case(resolutions[1], amplitude, length, density,
                                      iterations, pressure_tolerance)
        ledgers = {
            "levels": ledger_reports,
            "passed": all(abs(report["mass_change_kg"]) <= 1.0e-14
                          and abs(report["boundary_volume_balance_m3_s"]) <= 1.0e-9
                          and math.isfinite(report["final_kinetic_energy_j"])
                          and report["final_kinetic_energy_j"] >= 0.0
                          and report["final_kinetic_energy_j"]
                              <= report["initial_kinetic_energy_j"]
                                 + max(1.0e-12,
                                       1.0e-8 * report["initial_kinetic_energy_j"])
                          for report in ledger_reports),
            "energy_expectation":
                "no external work: projection/advection/viscosity must not increase kinetic energy",
        }
        internal = {
            "manufactured_cases": manufactured_evidence,
            "pressure_projection": projection,
            "grid_refinement": refinement,
            "ledgers": ledgers,
        }
        all_passed = all(item.get("passed") is True for item in internal.values())
        claims_result = assess_claims(request.get("claims", ()), internal)
        verdict = (VALIDATION_FAILED if not all_passed else
                   claims_result["verdict"] if claims_result["verdict"] != ANSWER
                   else ANSWER)
        result = {
            "verdict": verdict,
            "validation": internal,
            "claims": claims_result,
            "all_internal_checks_passed": all_passed,
            "input_digest": _digest(json.loads(json.dumps(request, sort_keys=True))),
            "backend": capabilities(),
        }
        if verdict != ANSWER:
            result["why"] = ("one or more numerical checks failed" if not all_passed
                             else "one or more requested claims lack sufficient evidence")
        return result
    except (KeyError, TypeError, ValueError, IndexError, _Invalid) as error:
        return _refusal(INVALID_INPUT, str(error), immutable_input_snapshot=snapshot)


__all__ = [
    "ANSWER", "CLAIM_REFUSAL", "INVALID_INPUT", "MANIFEST_REFUSAL",
    "MANIFEST_SCHEMA", "SOLVER_REFUSAL", "VALIDATION_FAILED",
    "assess_claims", "capabilities", "manufactured_case",
    "validate", "validate_dataset_manifest",
]
