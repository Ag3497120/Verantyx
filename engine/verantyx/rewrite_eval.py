"""Does the rule-data version of digit addition agree with wire_add?

The same standard Q3 held procedure_exec to: the generalisation is accepted
only if it reproduces the existing, trusted implementation exactly — verdict
for verdict, value for value — across a product of values that includes both
overflow shapes (too many digits; carry out of the last arm). If this fails,
the generalisation is wrong, not the original.

Also exercises the two typed failure modes the rewriting layer adds:
UNKNOWN_BUDGET (normalisation cut off) and UNKNOWN_NO_RULE (a stuck term —
the "missing rule" signal a GapNode is shaped to hold).

Run:  python3 -m verantyx.rewrite_eval
"""
from __future__ import annotations

import itertools
import sys

from .math_sim import wire_add
from .rewrite_core import Rule, Var, make_rule, normalize
from .rewrite_math import digit_addition_rules, rewrite_add


def main() -> int:
    failures = []

    # ── 1. Full regression vs wire_add ──────────────────────────────────
    values = [0, 1, 7, 9, 55, 99, 455, 909, 4999, 99999, 123456, 999999]
    n = 0
    bad = 0
    for a, b in itertools.product(values, repeat=2):
        w = wire_add(a, b)
        r = rewrite_add(a, b)
        n += 1
        if (w["verdict"], w["value"]) != (r["verdict"], r["value"]):
            bad += 1
            if bad <= 3:
                print(f"        mismatch a={a} b={b}: wire={w['verdict']}/{w['value']} "
                      f"rewrite={r['verdict']}/{r['value']}")
    ok = bad == 0
    print(f"[{'ok  ' if ok else 'FAIL'}] regression vs wire_add: {n - bad}/{n} agree "
          f"(incl. carry-overflow cases like 999999+1)")
    if not ok:
        failures.append("regression vs wire_add")
    print()

    # ── 2. The seven-digit guard matches wire_add's geometry verdict ────
    w = wire_add(1234567, 1)
    r = rewrite_add(1234567, 1)
    ok = w["verdict"] == r["verdict"] == "UNKNOWN_OVERFLOW"
    print(f"[{'ok  ' if ok else 'FAIL'}] >6-digit guard: both say {r['verdict']}")
    if not ok:
        failures.append(">6-digit guard")
    print()

    # ── 3. Termination is proven, not hoped ─────────────────────────────
    rules = digit_addition_rules()
    unoriented = [ru.name for ru in rules if not ru.oriented]
    ok = not unoriented and len(rules) == 202
    print(f"[{'ok  ' if ok else 'FAIL'}] all {len(rules)} rules oriented "
          f"(size strictly decreases every step)")
    if not ok:
        failures.append("orientation")
    print()

    # ── 4. Budget exhaustion is typed, and feeds the capacity loop ──────
    r = rewrite_add(999999, 999998, budget=3)
    ok = r["verdict"] == "UNKNOWN_BUDGET"
    print(f"[{'ok  ' if ok else 'FAIL'}] tiny budget -> {r['verdict']} "
          f"(the verdict capacity_calibration already knows how to re-run)")
    if not ok:
        failures.append("budget verdict")
    print()

    # ── 5. A stuck term is UNKNOWN_NO_RULE, with the term attached ──────
    # Deliberately withhold the terminal rule: normalisation runs the six
    # digit steps and then stops at add(0, nil, nil, acc) with nothing to
    # fire — a missing rule, not a missing budget, and the two must not be
    # conflated because their remedies are different (write a rule vs raise
    # a number).
    partial = [ru for ru in rules if ru.name != "add_done"]
    from .rewrite_math import _encode, _is_result  # test-only reach-in
    res = normalize(_encode(12, 34), partial, budget=2000, is_result=_is_result)
    ok = res.verdict == "UNKNOWN_NO_RULE" and isinstance(res.term, tuple) \
        and res.term[0] == "add"
    print(f"[{'ok  ' if ok else 'FAIL'}] missing rule -> {res.verdict}, stuck term kept "
          f"for the gap graph")
    if not ok:
        failures.append("stuck term verdict")
    print()

    # ── 6. An unorientable rule is flagged at registration ──────────────
    flipped = make_rule("swap", ("pair", Var("x"), Var("y")),
                        ("pair", Var("y"), Var("x")))
    dup = make_rule("dup", ("wrap", Var("x")),
                    ("pair", Var("x"), Var("x")))
    ok = not flipped.oriented and not dup.oriented
    print(f"[{'ok  ' if ok else 'FAIL'}] orientation check rejects a swap rule and a "
          f"variable-duplicating rule")
    if not ok:
        failures.append("orientation check")
    print()

    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        return 1
    print("all rewrite cases behaved as labelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
