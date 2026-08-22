"""Digit addition as rule DATA over rewrite_core — the proof that the
generalised instruction set can carry what procedure_exec carried, without
the interpreter knowing what a digit is.

The rule set is 202 rules, generated deterministically:

  - 200 digit rules, one per (x, y, carry_in) combination:
        add(c, cons(x, as), cons(y, bs), acc)
          -> add(c', as, bs, cons(d, acc))        where d, c' = x+y+c
    The arithmetic table is IN the rules. The interpreter only matches and
    substitutes.
  - 1 terminal rule:   add(0, nil, nil, acc) -> result(acc)
  - 1 overflow rule:   add(1, nil, nil, _)   -> overflow
    (a carry surviving the last arm — wire_add's "carry_out_of_last_arm")

Every rule passes `orient`, so the size measure strictly decreases at every
step and the system terminates unconditionally — asserted at build time
rather than hoped. The >6-digit guard stays outside the rules for the same
reason it is outside procedure_exec: it is the cross's geometry, checked
before encoding.

The gate is `regression_vs_wire_add`: verdict-for-verdict, value-for-value
agreement with `wire_add` across the full product of test values, overflow
cases included. Run via `python3 -m verantyx.rewrite_eval`.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .rewrite_core import Rule, Var, make_rule, normalize

NIL = "nil"
N_ARMS = 6  # mirrors math_sim.N_ARMS = len(AXES); geometry, not a knob


def _cons(head, tail):
    return ("cons", head, tail)


def digit_addition_rules() -> List[Rule]:
    rules: List[Rule] = []
    for x in range(10):
        for y in range(10):
            for c in (0, 1):
                s = x + y + c
                d, c2 = s % 10, s // 10
                rules.append(make_rule(
                    f"add_{x}_{y}_c{c}",
                    ("add", c, _cons(x, Var("as")), _cons(y, Var("bs")), Var("acc")),
                    ("add", c2, Var("as"), Var("bs"), _cons(d, Var("acc"))),
                ))
    rules.append(make_rule(
        "add_done",
        ("add", 0, NIL, NIL, Var("acc")),
        ("result", Var("acc")),
    ))
    rules.append(make_rule(
        "add_overflow",
        ("add", 1, NIL, NIL, Var("acc")),
        ("overflow",),
    ))
    # Termination is a property of the whole set, proven rule-by-rule via the
    # decreasing size measure. If generation ever produces an unoriented rule
    # this is a bug in the generator, not a tunable — fail loudly here.
    bad = [r.name for r in rules if not r.oriented]
    assert not bad, f"unoriented rules from a fixed generator: {bad}"
    return rules


_RULES = digit_addition_rules()


def _digits_le(n: int) -> List[int]:
    if n == 0:
        return [0]
    out = []
    while n:
        out.append(n % 10)
        n //= 10
    return out


def _encode(a: int, b: int):
    """Both operands padded to exactly N_ARMS digits, little-endian, as cons
    lists — the same 'iterate all six arms' convention wire_add uses, which
    is what makes the final-carry overflow rule line up with
    carry_out_of_last_arm."""
    da, db = _digits_le(a), _digits_le(b)
    da = da + [0] * (N_ARMS - len(da))
    db = db + [0] * (N_ARMS - len(db))
    ta: Any = NIL
    tb: Any = NIL
    for d in reversed(da):
        ta = _cons(d, ta)
    for d in reversed(db):
        tb = _cons(d, tb)
    return ("add", 0, ta, tb, NIL)


def _is_result(term) -> bool:
    return isinstance(term, tuple) and term[0] in ("result", "overflow")


def _decode(term) -> int:
    # acc was built by pushing each processed (little-endian) digit, so it
    # reads back most-significant first.
    digits = []
    node = term[1]
    while node != NIL:
        digits.append(node[1])
        node = node[2]
    return int("".join(str(d) for d in digits))


def rewrite_add(a: int, b: int, budget: int = 2000) -> Dict[str, Any]:
    """wire_add's contract, computed by normalisation over rule data."""
    if max(len(_digits_le(a)), len(_digits_le(b))) > N_ARMS:
        return {"verdict": "UNKNOWN_OVERFLOW", "value": None,
                "reason": f"needs>{N_ARMS}_arms"}
    r = normalize(_encode(a, b), _RULES, budget=budget, is_result=_is_result)
    if r.verdict != "ANSWER":
        return {"verdict": r.verdict, "value": None, "reason": r.reason}
    if r.term == ("overflow",):
        return {"verdict": "UNKNOWN_OVERFLOW", "value": None,
                "reason": "carry_out_of_last_arm"}
    return {"verdict": "ANSWER", "value": _decode(r.term),
            "steps": r.steps, "rules_applied": r.trace}
