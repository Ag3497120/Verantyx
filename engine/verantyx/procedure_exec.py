"""Milestone Q2 — closed instruction-set interpreter for Procedure.

This is the actual safety boundary, not module_verify.py's static-safety-
scan-of-arbitrary-code approach (Milestone M). A Procedure's `steps` can
ONLY use the four ops in ALLOWED_OPS below -- there is no "eval this
Python" escape hatch anywhere in this file. A step with any other `op`
name fails the procedure with a typed verdict rather than being ignored
or silently skipped, so a malformed/malicious Procedure candidate cannot
sneak in an unsupported instruction and have it quietly do nothing (or
worse, be misinterpreted).

Scope (see plan): this instruction set is deliberately just large enough
to express math_sim.py's digit_addition, not a general-purpose language.
Widening it to cover subtraction/multiplication/ARC-style world models is
explicitly future work.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .procedure import Procedure

ALLOWED_OPS = frozenset({"read_digit", "add_with_carry", "write_digit", "check_overflow"})

# Milestone Q4: the TRUSTED-procedure registry -- mirrors domains.py's own
# register()/registered() pattern (Milestone M), except entries here are
# data (Procedure), not Python callables. Populated only via
# procedure_ingest.ProcedureQuarantine.accept(), never automatically.
_registry: Dict[str, Procedure] = {}


def register_procedure(proc: Procedure) -> None:
    _registry[proc.procedure_id] = proc


def registered_procedures() -> Dict[str, Procedure]:
    return dict(_registry)

N_ARMS = 6  # matches cross.AXES's length; a Procedure operating over more
            # positions than this always fails UNKNOWN_OVERFLOW, mirroring
            # math_sim.wire_add's own N_ARMS cap.


def _digits_le(n: int) -> List[int]:
    if n == 0:
        return [0]
    out: List[int] = []
    while n:
        out.append(n % 10)
        n //= 10
    return out


def _check_preconditions(proc: Procedure, state: Dict[str, Any]) -> "str | None":
    for cond in proc.preconditions:
        if cond.kind == "natural_number":
            for var in cond.params.get("vars", []):
                v = state.get(var)
                if not isinstance(v, int) or v < 0:
                    return f"precondition_failed:natural_number:{var}"
        elif cond.kind == "within_capacity":
            max_digits = cond.params.get("max_digits", N_ARMS)
            for var in cond.params.get("vars", []):
                v = state.get(var)
                if isinstance(v, int) and len(_digits_le(v)) > max_digits:
                    return f"precondition_failed:within_capacity:{var}"
        else:
            return f"precondition_failed:unknown_kind:{cond.kind}"
    return None


def execute_procedure(proc: Procedure, initial_state: Dict[str, Any]) -> Dict[str, Any]:
    """Runs `proc.steps` against `initial_state` under the closed
    instruction set. Returns a typed result dict, never raises for
    ordinary failure modes (unknown op, budget exceeded, precondition
    failure, overflow) -- matches every other Vera entry point's own
    typed-refusal convention."""
    precondition_failure = _check_preconditions(proc, initial_state)
    if precondition_failure:
        return {"verdict": "UNKNOWN_PRECONDITION_FAILED", "value": None, "reason": precondition_failure, "trace": []}

    if len(proc.steps) > proc.budget:
        return {"verdict": "UNKNOWN_BUDGET", "value": None,
                "reason": f"steps({len(proc.steps)})>budget({proc.budget})", "trace": []}

    state: Dict[str, Any] = dict(initial_state)
    state.setdefault("digits_a", _digits_le(state.get("a", 0)))
    state.setdefault("digits_b", _digits_le(state.get("b", 0)))
    state.setdefault("carry", 0)
    state.setdefault("result_digits", [])
    trace: List[Dict[str, Any]] = []

    for step in proc.steps:
        if step.op not in ALLOWED_OPS:
            return {"verdict": "UNKNOWN_UNSUPPORTED_OP", "value": None,
                    "reason": f"op_not_in_closed_set:{step.op}", "trace": trace}

        if step.op == "read_digit":
            operand = step.args["operand"]
            position = step.args["position"]
            digits = state["digits_a"] if operand == "a" else state["digits_b"]
            value = digits[position] if position < len(digits) else 0
            state[f"_x" if operand == "a" else "_y"] = value
            trace.append({"op": "read_digit", "operand": operand, "position": position, "value": value})

        elif step.op == "add_with_carry":
            x, y, carry_in = state.get("_x", 0), state.get("_y", 0), state["carry"]
            s = x + y + carry_in
            digit, carry_out = s % 10, s // 10
            state["_digit"] = digit
            state["carry"] = carry_out
            trace.append({"op": "add_with_carry", "x": x, "y": y, "carry_in": carry_in,
                          "digit": digit, "carry_out": carry_out})

        elif step.op == "write_digit":
            position = step.args["position"]
            digits = state["result_digits"]
            while len(digits) <= position:
                digits.append(0)
            digits[position] = state.get("_digit", 0)
            trace.append({"op": "write_digit", "position": position, "digit": state.get("_digit", 0)})

        elif step.op == "check_overflow":
            if state["carry"] != 0:
                return {"verdict": "UNKNOWN_OVERFLOW", "value": None,
                        "reason": "carry_out_of_last_arm", "trace": trace}
            trace.append({"op": "check_overflow", "carry": state["carry"]})

    value = int("".join(str(d) for d in reversed(state["result_digits"]))) if state["result_digits"] else 0

    # Verify the procedure's own stated expected_effects against what the
    # trace actually shows -- a Procedure that claims one thing but does
    # another is exactly the kind of gap this representation exists to
    # catch (matches the design discussion's "候補→実行→照合→採否" loop).
    actual_writes = sum(1 for t in trace if t["op"] == "write_digit")
    actual_overflow_checked = any(t["op"] == "check_overflow" for t in trace)
    for effect in proc.expected_effects:
        if effect.kind == "digit_written":
            expected_count = effect.params.get("count")
            if expected_count is not None and actual_writes != expected_count:
                return {"verdict": "UNKNOWN_EFFECT_MISMATCH", "value": None,
                        "reason": f"digit_written count expected={expected_count} actual={actual_writes}",
                        "trace": trace}
        elif effect.kind == "no_overflow":
            if not actual_overflow_checked:
                return {"verdict": "UNKNOWN_EFFECT_MISMATCH", "value": None,
                        "reason": "no_overflow effect declared but check_overflow step never ran",
                        "trace": trace}

    return {"verdict": "ANSWER", "value": value, "trace": trace}


def digit_addition_procedure() -> Procedure:
    """The Milestone Q3 proof-of-concept: math_sim.wire_add re-expressed
    as data instead of a fixed Python function, using only ALLOWED_OPS.
    Fully unrolled over N_ARMS positions (no loop construct in this
    instruction set -- keeps the interpreter itself maximally small and
    auditable, per this module's own safety rationale)."""
    from .procedure import Condition, Effect, Procedure as _Procedure, Step

    steps: List[Step] = []
    for pos in range(N_ARMS):
        steps.append(Step("read_digit", {"operand": "a", "position": pos}))
        steps.append(Step("read_digit", {"operand": "b", "position": pos}))
        steps.append(Step("add_with_carry", {}))
        steps.append(Step("write_digit", {"position": pos}))
    steps.append(Step("check_overflow", {}))

    return _Procedure(
        procedure_id="digit_addition",
        preconditions=[
            Condition("natural_number", {"vars": ["a", "b"]}),
            Condition("within_capacity", {"vars": ["a", "b"], "max_digits": N_ARMS}),
        ],
        steps=steps,
        expected_effects=[
            Effect("digit_written", {"count": N_ARMS}),
            Effect("no_overflow", {}),
        ],
        budget=100,
        status="DEFINED",
    )
