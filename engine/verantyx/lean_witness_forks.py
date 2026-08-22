"""Forks for the Lean witness type — the sorry catch above all."""
from __future__ import annotations

from typing import Any, Dict, List


def structure_to_lean_loop_fork() -> Dict[str, Any]:
    """構造が出した結論を、Lean が独立に検査して通す — そして嘘は落ちる。

    「格納されていないことは主張しない」を外さずに帰結を出せるか、という
    問いの実装上の答え(2026-08-19、experiments/structure_to_lean)。
    格納された202規則だけを適用して導出した和は、コーパスのどこにも
    書かれていないが、根拠は全て格納済みで、Lean は導出器の言い分を
    一切信用しない。**禁じられているのは推測であって帰結ではない。**

    3点: (a) 導出が ANSWER で正しい値を出す (b) その結論を Lean が
    VERIFIED にする (c) 結論を改竄すると Lean が落とす — ②が①の
    番人として実際に機能していること。

    lean が無い機械では報告してスキップ(合格に数えない)。
    """
    from .lean_witness import lean_binary, verify
    from .rewrite_math import rewrite_add

    name = "STRUCTURE_TO_LEAN_LOOP"
    if lean_binary() is None:
        return {"experiment": "lean_witness", "fork": name,
                "skipped": "no lean toolchain on this machine"}

    a, b = 847, 231
    r = rewrite_add(a, b)
    derived = (str(r.get("verdict")) == "ANSWER" and r.get("value") == a + b)

    ok_true = verify("theorem t : %d + %d = %d := by decide"
                     % (a, b, r.get("value")))
    passes = str(ok_true.get("verdict")) == "VERIFIED"

    ok_lie = verify("theorem t : %d + %d = %d := by decide"
                    % (a, b, a + b + 1))
    catches = str(ok_lie.get("verdict")) != "VERIFIED"

    ok = bool(derived and passes and catches)
    return {"experiment": "lean_witness", "fork": name, "pass": ok,
            "result": {"derived_value": r.get("value"), "expected": a + b,
                       "lean_on_derived": ok_true.get("verdict"),
                       "lean_on_tampered": ok_lie.get("verdict")}}


def lean_witness_types_fork() -> Dict[str, Any]:
    """The three absences stay apart, and `sorry` never verifies.

    VERIFIED must carry a toolchain-versioned witness facet (the
    citation), a failing proof must land in UNPROVEN without any claim
    of falsity, and a `sorry` proof — which the kernel accepts with
    exit 0 and a warning — must be caught by name. The smoke test that
    built this module caught exactly that: the warning's quoting
    changed between Lean releases and `sorry` verified quietly.

    Skipped (reported, never counted as a pass) on machines without a
    lean executable.
    """
    from .lean_witness import lean_binary, verify

    name = "LEAN_WITNESS_TYPES"
    if lean_binary() is None:
        return {"experiment": "lean_witness", "fork": name,
                "skipped": "no lean toolchain on this machine"}

    ok_true = verify("theorem t : 1 + 1 = 2 := rfl")
    ok_false = verify("theorem t : 1 + 1 = 3 := rfl")
    ok_sorry = verify("theorem t : 1 + 1 = 2 := sorry")

    ok = (ok_true["verdict"] == "VERIFIED"
          and str(ok_true.get("witness", "")).startswith("verified:lean4:")
          and ok_false["verdict"] == "UNPROVEN"
          and "false" not in str(ok_false.get("note", "")).split("not a claim")[0]
          and ok_sorry["verdict"] == "UNPROVEN_SORRY")
    return {"experiment": "lean_witness", "fork": name, "pass": bool(ok),
            "result": {"true": ok_true["verdict"],
                       "witness": ok_true.get("witness"),
                       "false": ok_false["verdict"],
                       "sorry": ok_sorry["verdict"]}}


def all_lean_witness_forks() -> List[Dict[str, Any]]:
    return [lean_witness_types_fork(), structure_to_lean_loop_fork()]
