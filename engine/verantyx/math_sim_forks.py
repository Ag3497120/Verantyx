"""Forks for math simulation (wire arithmetic / matryoshka eval / typed equations)."""
from __future__ import annotations

import random
from typing import Any, Dict, List

from .math_sim import eval_expr, math_ask, solve_equation, wire_add, wire_mul, wire_sub


def math_wire_add_fork() -> Dict[str, Any]:
    """筆算 = 繰り上がり電流。桁トレースと overflow の型付きを検証."""
    r = wire_add(247, 385)
    carries = [s["carry_out"] for s in r["steps"]]
    ov = wire_add(999999, 1)
    ok = (
        r["verdict"] == "ANSWER"
        and r["value"] == 632
        and carries[:3] == [1, 1, 0]  # 7+5=12, 4+8+1=13, 2+3+1=6
        and ov["verdict"] == "UNKNOWN_OVERFLOW"
        and wire_add(247, 385) == r  # 決定論
    )
    return {
        "experiment": "math_sim",
        "fork": "MATH_WIRE_ADD",
        "pass": bool(ok),
        "result": {"value": r["value"], "carries": carries,
                   "overflow_verdict": ov["verdict"]},
    }


def math_wire_sub_fork() -> Dict[str, Any]:
    """借り電流と、自然数 v0 の負結果拒否 (UNKNOWN_NEGATIVE)."""
    r = wire_sub(632, 385)
    neg = wire_sub(3, 5)
    ok = (
        r["verdict"] == "ANSWER"
        and r["value"] == 247
        and neg["verdict"] == "UNKNOWN_NEGATIVE"
        and neg["value"] is None
    )
    return {
        "experiment": "math_sim",
        "fork": "MATH_WIRE_SUB",
        "pass": bool(ok),
        "result": {"value": r["value"], "neg_verdict": neg["verdict"]},
    }


def math_matryoshka_eval_fork() -> Dict[str, Any]:
    """括弧の深さ = 層。内層の結論が上へ渡る評価."""
    r = eval_expr("(2 + 3) * 4")
    prec = eval_expr("2 + 3 * 4")
    deep = eval_expr("((1 + 2) * (3 + 4)) - 5")
    ok = (
        r["verdict"] == "ANSWER"
        and r["value"] == 20
        and len(r["layers"]) >= 2
        and r["layers"][0]["expr"] == "2 + 3"
        and prec["value"] == 14
        and deep["value"] == 16
        and len(deep["layers"]) >= 4
    )
    return {
        "experiment": "math_sim",
        "fork": "MATH_MATRYOSHKA_EVAL",
        "pass": bool(ok),
        "result": {"layers": r["layers"], "precedence": prec["value"],
                   "deep": deep["value"]},
    }


def math_equation_typed_fork() -> Dict[str, Any]:
    """方程式の型付き verdict: 一意/複数/解なし を言い分ける."""
    unique = solve_equation("x + 3 = 7")
    multi = solve_equation("x * 0 = 0")
    none1 = solve_equation("x + 5 = 3")
    none2 = solve_equation("x * 2 = 7")
    ok = (
        unique["verdict"] == "ANSWER"
        and unique["x"] == 4
        and multi["verdict"] == "AMBIGUOUS"
        and len(multi["solutions"]) > 1
        and none1["verdict"] == "UNKNOWN_NO_SOLUTION"
        and none2["verdict"] == "UNKNOWN_NO_SOLUTION"
    )
    return {
        "experiment": "math_sim",
        "fork": "MATH_EQUATION_TYPED",
        "pass": bool(ok),
        "result": {
            "unique": unique["x"],
            "multi_verdict": multi["verdict"],
            "no_solution": [none1["verdict"], none2["verdict"]],
        },
    }


def math_exactness_sweep_fork(n: int = 200, seed: int = 7) -> Dict[str, Any]:
    """構成上ミスしない、の実測: 乱数 (seed 固定) n 件を int と照合."""
    rng = random.Random(seed)
    wrong: List[str] = []
    for _ in range(n):
        a, b = rng.randint(0, 99999), rng.randint(0, 99999)
        r = wire_add(a, b)
        if r["verdict"] == "ANSWER" and r["value"] != a + b:
            wrong.append(f"{a}+{b}")
        if a >= b:
            r = wire_sub(a, b)
            if r["verdict"] == "ANSWER" and r["value"] != a - b:
                wrong.append(f"{a}-{b}")
        m, k = rng.randint(0, 300), rng.randint(0, 999)
        rm = wire_mul(m, k)
        if rm["verdict"] == "ANSWER" and rm["value"] != m * k:
            wrong.append(f"{m}*{k}")
    ok = not wrong
    return {
        "experiment": "math_sim",
        "fork": "MATH_EXACTNESS_SWEEP",
        "pass": bool(ok),
        "result": {"n": n, "wrong": wrong[:5]},
    }


def math_calculator_trailing_equals_fork() -> Dict[str, Any]:
    """Calculator-style trailing "=" ("1+1=") must compute, not fall through
    to knowledge search — regression for a live bug found in chat."""
    a = math_ask("1+1=")
    b = math_ask("1 + 1 = ")
    eq = math_ask("x + 3 = 7")  # equation route must still work (has "x")
    ok = (
        a["verdict"] == "ANSWER" and a["value"] == 2
        and b["verdict"] == "ANSWER" and b["value"] == 2
        and eq["mode"] == "equation" and eq["x"] == 4
    )
    return {
        "experiment": "math_sim",
        "fork": "MATH_CALCULATOR_TRAILING_EQUALS",
        "pass": bool(ok),
        "result": {"a": a.get("value"), "b": b.get("value"), "eq_x": eq.get("x")},
    }


def math_ask_route_fork() -> Dict[str, Any]:
    """自然文入口: what is / solve のルーティングと非数式の拒否."""
    e = math_ask("what is (2 + 3) * 4")
    q = math_ask("solve x + 3 = 7")
    junk = math_ask("what is banana + 3")
    ok = (
        e["verdict"] == "ANSWER"
        and e["value"] == 20
        and q["verdict"] == "ANSWER"
        and q["x"] == 4
        and junk["verdict"] == "UNKNOWN_UNPARSED"
    )
    return {
        "experiment": "math_sim",
        "fork": "MATH_ASK_ROUTE",
        "pass": bool(ok),
        "result": {"expr": e["value"], "eq": q["x"],
                   "junk_verdict": junk["verdict"]},
    }


def all_math_sim_forks() -> List[Dict[str, Any]]:
    return [
        math_wire_add_fork(),
        math_wire_sub_fork(),
        math_matryoshka_eval_fork(),
        math_equation_typed_fork(),
        math_exactness_sweep_fork(),
        math_calculator_trailing_equals_fork(),
        math_ask_route_fork(),
    ]
