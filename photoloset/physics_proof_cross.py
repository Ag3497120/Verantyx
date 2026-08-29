# -*- coding: utf-8 -*-
"""Deterministic proof-obligation ledger on the six-arm cross.

The cross does not solve a PDE.  It records what a numerical stage claimed,
which deterministic predicate checked it, which inputs caused the result,
which effects consume it, and whether independent witnesses disagree.  Exact
rational predicates and bounded numerical certificates are never presented as
the same guarantee class.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from fractions import Fraction
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .cross import CONTESTED_IN_CROSS, CrossStore


SCHEMA = "solver.proof-cross.v1"
ANSWER = "ANSWER"
UNKNOWN = "UNKNOWN_PROOF_OBLIGATION"
CONTESTED = "CONTESTED_PROOF_OBLIGATION"
REFUTED = "REFUTED_PROOF_OBLIGATION"


def capabilities() -> Dict[str, Any]:
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "predicates": [
            "exact_equal", "bounded_absolute", "interval_contains",
            "ordered_interval",
            "monotone_nonincreasing", "conservation",
            "residual_reduction", "minimum_integer_order",
        ],
        "exact_domain": "rational values represented by int or decimal string",
        "numerical_domain": "explicit caller-supplied bounds only",
        "cross_role": {
            "support+": "deterministic checks and named witnesses",
            "support-": "emerges only when witnesses disagree at one address",
            "cause+": "inputs and derivation trace",
            "cause-": "declared downstream effect",
            "kind+": "generic theorem only after two independent sources",
            "kind-": "this run and this obligation",
        },
        "does_not_do": [
            "solve differential equations", "invent an error bound",
            "turn a regression test into a theorem",
            "certify floating-point hardware or a compiler",
        ],
    }


def _fraction(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("boolean is not a scalar")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        return Fraction(value.strip())
    if isinstance(value, float) and math.isfinite(value):
        # Decimal spelling is the caller-visible value.  Binary float internals
        # are not silently promoted to an exact physical measurement.
        return Fraction(str(value))
    raise ValueError("value must be a finite int, float or decimal string")


def _many(values: Any) -> List[Fraction]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("values must be an array")
    return [_fraction(value) for value in values]


def _evaluate(predicate: str, data: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        if predicate == "exact_equal":
            left, right = _fraction(data["left"]), _fraction(data["right"])
            holds = left == right
            trace = {"left": str(left), "right": str(right)}
            guarantee = "EXACT_RATIONAL"
        elif predicate == "bounded_absolute":
            value, bound = abs(_fraction(data["value"])), _fraction(data["bound"])
            if bound < 0:
                raise ValueError("bound must be non-negative")
            holds = value <= bound
            trace = {"absolute_value": str(value), "bound": str(bound)}
            guarantee = "BOUNDED_NUMERICAL"
        elif predicate == "interval_contains":
            lower = _fraction(data["lower"])
            value = _fraction(data["value"])
            upper = _fraction(data["upper"])
            if lower > upper:
                raise ValueError("lower must not exceed upper")
            holds = lower <= value <= upper
            trace = {"lower": str(lower), "value": str(value),
                     "upper": str(upper)}
            guarantee = "BOUNDED_NUMERICAL"
        elif predicate == "ordered_interval":
            lower = _fraction(data["lower"])
            upper = _fraction(data["upper"])
            domain_lower = _fraction(data.get("domain_lower", lower))
            domain_upper = _fraction(data.get("domain_upper", upper))
            if domain_lower > domain_upper:
                raise ValueError("domain_lower must not exceed domain_upper")
            holds = domain_lower <= lower <= upper <= domain_upper
            trace = {"domain_lower": str(domain_lower), "lower": str(lower),
                     "upper": str(upper), "domain_upper": str(domain_upper)}
            guarantee = "EXACT_RATIONAL_INTERVAL_ORDER"
        elif predicate == "monotone_nonincreasing":
            values = _many(data["values"])
            if len(values) < 2:
                raise ValueError("at least two values are required")
            holds = all(after <= before
                        for before, after in zip(values, values[1:]))
            trace = {"values": [str(value) for value in values]}
            guarantee = "EXACT_RATIONAL_SEQUENCE"
        elif predicate == "conservation":
            before, after = _fraction(data["before"]), _fraction(data["after"])
            tolerance = _fraction(data["tolerance"])
            if tolerance < 0:
                raise ValueError("tolerance must be non-negative")
            defect = abs(after - before)
            holds = defect <= tolerance
            trace = {"before": str(before), "after": str(after),
                     "defect": str(defect), "tolerance": str(tolerance)}
            guarantee = "BOUNDED_CONSERVATION"
        elif predicate == "residual_reduction":
            initial = abs(_fraction(data["initial"]))
            final = abs(_fraction(data["final"]))
            factor = _fraction(data.get("minimum_factor", 1))
            if initial <= 0 or factor <= 0:
                raise ValueError("initial and minimum_factor must be positive")
            holds = final * factor <= initial
            trace = {"initial": str(initial), "final": str(final),
                     "minimum_factor": str(factor)}
            guarantee = "BOUNDED_NUMERICAL"
        elif predicate == "minimum_integer_order":
            errors = _many(data["errors"])
            spacings = _many(data["spacings"])
            order = int(data["minimum_order"])
            if (len(errors) < 2 or len(errors) != len(spacings)
                    or order < 0 or any(x <= 0 for x in errors + spacings)):
                raise ValueError("positive paired errors/spacings and order>=0 required")
            checks = []
            for e0, e1, h0, h1 in zip(errors, errors[1:],
                                      spacings, spacings[1:]):
                if h1 >= h0:
                    raise ValueError("spacings must strictly decrease")
                checks.append(e1 * (h0 ** order) <= e0 * (h1 ** order))
            holds = all(checks)
            trace = {"errors": [str(x) for x in errors],
                     "spacings": [str(x) for x in spacings],
                     "minimum_order": order, "pair_checks": checks}
            guarantee = "EXACT_RATIONAL_RATE_BOUND"
        else:
            return {"verdict": UNKNOWN, "why": "unsupported predicate",
                    "predicate": predicate}
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return {"verdict": UNKNOWN, "why": str(exc), "predicate": predicate}
    return {"verdict": ANSWER, "holds": holds, "predicate": predicate,
            "guarantee_class": guarantee, "trace": trace}


def _sources(values: Any) -> List[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [value.strip() for value in values
            if isinstance(value, str) and value.strip()]


def verify(request: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = copy.deepcopy(request)
    if not isinstance(request, Mapping) or request.get("schema") != SCHEMA:
        return {"verdict": "UNKNOWN_INVALID_PROOF_CROSS_INPUT",
                "why": f"schema must be {SCHEMA}",
                "immutable_input_snapshot": snapshot}
    run_id = str(request.get("run_id", "")).strip()
    solver = str(request.get("solver", "")).strip()
    obligations = request.get("obligations")
    if not run_id or not solver or not isinstance(obligations, list) or not obligations:
        return {"verdict": "UNKNOWN_INVALID_PROOF_CROSS_INPUT",
                "why": "run_id, solver and a non-empty obligations array are required",
                "immutable_input_snapshot": snapshot}

    store = CrossStore()
    root = f"proof:{run_id}"
    reports: List[Dict[str, Any]] = []
    seen = set()
    for raw in obligations:
        if not isinstance(raw, Mapping):
            reports.append({"verdict": UNKNOWN, "why": "obligation must be an object"})
            continue
        oid = str(raw.get("id", "")).strip()
        if not oid or oid in seen:
            reports.append({"id": oid, "verdict": UNKNOWN,
                            "why": "obligation id must be unique and non-empty"})
            continue
        seen.add(oid)
        prefix = f"{oid}."
        predicate = str(raw.get("predicate", ""))
        data = raw.get("data")
        evaluated = (_evaluate(predicate, data) if isinstance(data, Mapping)
                     else {"verdict": UNKNOWN, "why": "data must be an object",
                           "predicate": predicate})
        writes = [
            (prefix + "statement", str(raw.get("statement", oid)), "specific", solver),
            (prefix + "predicate", predicate, "specific", "proof-cross-kernel"),
            (prefix + "input", dict(data) if isinstance(data, Mapping) else data,
             "input", solver),
        ]
        if evaluated.get("verdict") == ANSWER:
            writes.extend([
                (prefix + "derivation", evaluated["trace"], "derived",
                 "proof-cross-kernel"),
                (prefix + "holds", bool(evaluated["holds"]), "measured",
                 "deterministic:" + predicate),
                (prefix + "effect", str(raw.get("effect", "solver claim gate")),
                 "feeds", solver),
            ])
        for key, value, kind, source in writes:
            store.put(root, key, value, kind, source)

        theorem = raw.get("theorem")
        theorem_sources = _sources(raw.get("theorem_sources"))
        if theorem is not None:
            for source in theorem_sources:
                store.put(root, prefix + "theorem", theorem, "generic", source)

        for witness in raw.get("witnesses", []) if isinstance(raw.get("witnesses", []), list) else []:
            if (isinstance(witness, Mapping)
                    and isinstance(witness.get("holds"), bool)
                    and str(witness.get("source", "")).strip()):
                store.put(root, prefix + "holds", witness["holds"], "measured",
                          str(witness["source"]).strip())

        resolved = store.resolve(root, prefix + "holds")
        if evaluated.get("verdict") != ANSWER:
            verdict = UNKNOWN
        elif resolved.get("verdict") == CONTESTED_IN_CROSS:
            verdict = CONTESTED
        elif resolved.get("verdict") != ANSWER:
            verdict = UNKNOWN
        elif resolved.get("value") is True:
            verdict = ("CERTIFIED_EXACT" if
                       str(evaluated.get("guarantee_class", "")).startswith("EXACT")
                       else "CERTIFIED_BOUNDED")
        else:
            verdict = REFUTED
        reports.append({"id": oid, "verdict": verdict,
                        "evaluation": evaluated, "cross_resolution": resolved,
                        "generic_theorem_bought": len(set(theorem_sources)) >= 2
                                                   if theorem is not None else None})

    verdicts = {report.get("verdict") for report in reports}
    if CONTESTED in verdicts:
        overall = CONTESTED
    elif REFUTED in verdicts:
        overall = REFUTED
    elif UNKNOWN in verdicts:
        overall = UNKNOWN
    else:
        overall = ANSWER
    canonical = json.dumps({"run_id": run_id, "solver": solver,
                            "obligations": reports}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return {
        "verdict": overall,
        "schema": "solver.proof-cross-result.v1",
        "run_id": run_id,
        "solver": solver,
        "obligations": reports,
        "proof_digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "cross": store.to_dict(),
        "cross_verification": store.verify(),
        "industrial_certification": False,
        "immutable_input_snapshot": snapshot,
    }


def verify_stage_results(run_id: str, stages: Mapping[str, Any]) -> Dict[str, Any]:
    """Build arithmetic obligations from already-produced stage diagnostics.

    This checks the internal report, not the external physical world.  Every
    generated statement therefore names its scope as self-reported arithmetic.
    Independent experimental evidence must still arrive as a separate witness.
    """
    obligations: List[Dict[str, Any]] = []
    shell = stages.get("nonlinear_shell", {})
    if isinstance(shell, Mapping) and shell.get("verdict") == ANSWER:
        summaries = shell.get("increment_summaries", [])
        if isinstance(summaries, list) and summaries:
            final = summaries[-1]
            if isinstance(final, Mapping):
                obligations.append({
                    "id": "shell.final-residual",
                    "statement": "reported shell residual is within reported tolerance",
                    "predicate": "bounded_absolute",
                    "data": {"value": final.get("residual_l2_n"),
                             "bound": final.get("tolerance_n")},
                    "effect": "permits the workflow to label this increment converged",
                })
    fluid = stages.get("incompressible_fluid", {})
    if isinstance(fluid, Mapping) and fluid.get("verdict") == ANSWER:
        diagnostics = fluid.get("diagnostics", {})
        if isinstance(diagnostics, Mapping):
            mass = diagnostics.get("mass_ledger", {})
            if isinstance(mass, Mapping):
                obligations.append({
                    "id": "fluid.reported-mass",
                    "statement": "reported constant-density mass is conserved",
                    "predicate": "exact_equal",
                    "data": {"left": mass.get("initial_mass_kg"),
                             "right": mass.get("final_mass_kg")},
                    "effect": "supports only the discrete constant-density ledger",
                })
            before = diagnostics.get("divergence_before_projection", {})
            after = diagnostics.get("divergence_after_projection", {})
            if isinstance(before, Mapping) and isinstance(after, Mapping):
                obligations.append({
                    "id": "fluid.projection-divergence",
                    "statement": "reported pressure projection did not increase RMS divergence",
                    "predicate": "residual_reduction",
                    "data": {"initial": before.get("l2_rms_s_inv"),
                             "final": after.get("l2_rms_s_inv"),
                             "minimum_factor": 1},
                    "effect": "supports the discrete projection check, not DNS validity",
                })
    dynamic_shell = stages.get("implicit_shell_dynamics", {})
    if (isinstance(dynamic_shell, Mapping)
            and dynamic_shell.get("verdict") == ANSWER):
        ledger = dynamic_shell.get("residual_ledger", [])
        if isinstance(ledger, list) and ledger:
            final = ledger[-1]
            if isinstance(final, Mapping):
                obligations.append({
                    "id": "dynamic-shell.final-residual",
                    "statement": "reported implicit dynamic residual is within its tolerance",
                    "predicate": "bounded_absolute",
                    "data": {"value": final.get("residual_l2_n"),
                             "bound": final.get("tolerance_n")},
                    "effect": "supports only the reported Newton terminal state",
                })
    collision = stages.get("production_collision", {})
    if isinstance(collision, Mapping) and collision.get("verdict") == ANSWER:
        events = collision.get("events", [])
        if isinstance(events, list):
            for index, event in enumerate(events):
                bracket = event.get("toi_normalized_bracket") if isinstance(event, Mapping) else None
                if isinstance(bracket, (list, tuple)) and len(bracket) == 2:
                    obligations.append({
                        "id": f"collision.event-{index}-bracket",
                        "statement": "reported normalized TOI bracket is ordered inside the step",
                        "predicate": "ordered_interval",
                        "data": {"lower": bracket[0], "upper": bracket[1],
                                 "domain_lower": 0, "domain_upper": 1},
                        "effect": "supports bracket well-formedness, not symbolic exactness",
                    })
    if not obligations:
        return {"verdict": UNKNOWN,
                "why": "no successful stage exposed a supported arithmetic obligation",
                "scope": "SELF_REPORTED_ARITHMETIC_ONLY"}
    result = verify({"schema": SCHEMA, "run_id": run_id,
                     "solver": "high-fidelity-workflow", "obligations": obligations})
    result["scope"] = "SELF_REPORTED_ARITHMETIC_ONLY"
    result["external_physical_validation"] = False
    return result
