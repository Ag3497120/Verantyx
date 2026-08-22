"""Math simulation on the stereo cross — 構造の物理を計算にする.

道1  wire 筆算: 腕 = 桁 (little-endian)、繰り上がり = 腕から腕への電流。
     digit は腕のセルに置かれ、桁あふれ (overflow) は詰まりとして型付き報告。
道3  Matryoshka 式評価: 括弧の深さ = 層。最内層を評価し結論を上の層へ渡す
     (第一層の結論を上へ、の数学版)。
道2  型付き方程式: 候補 x を提案し wire 演算で検査。解が一意 → ANSWER、
     複数 → AMBIGUOUS、無し → UNKNOWN_NO_SOLUTION。多数決も推測もしない。

自然数のみ (v0)。負になる引き算は UNKNOWN_NEGATIVE と正直に言う。
全て決定論・トレース付き。「学習した数学」ではなく「構成上正確な計算」。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .cross import AXES, LinearCross

N_ARMS = len(AXES)
MAX_MUL_STEPS = 500  # 乗算 = 加算の反復 (決定論の予算)

VERDICT_OK = "ANSWER"


def _digits_le(n: int) -> List[int]:
    """non-negative int → little-endian digits."""
    if n == 0:
        return [0]
    out: List[int] = []
    while n:
        out.append(n % 10)
        n //= 10
    return out


# ---------------------------------------------------------------------------
# 道1: wire 筆算 (加算・減算)
# ---------------------------------------------------------------------------

def wire_add(a: int, b: int) -> Dict[str, Any]:
    """腕=桁で a+b。繰り上がりが腕を渡る電流。6桁超は overflow (型付き)."""
    da, db = _digits_le(a), _digits_le(b)
    if max(len(da), len(db)) > N_ARMS:
        return {
            "verdict": "UNKNOWN_OVERFLOW",
            "value": None,
            "op": "add",
            "steps": [],
            "reason": f"needs>{N_ARMS}_arms",
        }
    cross = LinearCross(L=3)
    steps: List[Dict[str, Any]] = []
    carry = 0
    result: List[int] = []
    for i, axis in enumerate(AXES):
        x = da[i] if i < len(da) else 0
        y = db[i] if i < len(db) else 0
        cross.cells[axis][0] = str(x)
        cross.cells[axis][1] = str(y)
        s = x + y + carry
        d, carry_out = s % 10, s // 10
        cross.cells[axis][2] = str(d)  # settled digit (center side)
        steps.append(
            {"axis": axis, "x": x, "y": y, "carry_in": carry,
             "sum": s, "digit": d, "carry_out": carry_out}
        )
        carry = carry_out
        result.append(d)
    if carry:
        return {
            "verdict": "UNKNOWN_OVERFLOW",
            "value": None,
            "op": "add",
            "steps": steps,
            "reason": "carry_out_of_last_arm",
        }
    value = int("".join(str(d) for d in reversed(result)))
    return {"verdict": VERDICT_OK, "value": value, "op": "add", "steps": steps}


def wire_sub(a: int, b: int) -> Dict[str, Any]:
    """腕=桁で a-b (borrow が電流)。負になるなら UNKNOWN_NEGATIVE."""
    da, db = _digits_le(a), _digits_le(b)
    if max(len(da), len(db)) > N_ARMS:
        return {
            "verdict": "UNKNOWN_OVERFLOW",
            "value": None,
            "op": "sub",
            "steps": [],
            "reason": f"needs>{N_ARMS}_arms",
        }
    steps: List[Dict[str, Any]] = []
    borrow = 0
    result: List[int] = []
    for i, axis in enumerate(AXES):
        x = da[i] if i < len(da) else 0
        y = db[i] if i < len(db) else 0
        s = x - y - borrow
        if s < 0:
            d, borrow_out = s + 10, 1
        else:
            d, borrow_out = s, 0
        steps.append(
            {"axis": axis, "x": x, "y": y, "borrow_in": borrow,
             "digit": d, "borrow_out": borrow_out}
        )
        borrow = borrow_out
        result.append(d)
    if borrow:
        return {
            "verdict": "UNKNOWN_NEGATIVE",
            "value": None,
            "op": "sub",
            "steps": steps,
            "reason": "result_below_zero_naturals_v0",
        }
    value = int("".join(str(d) for d in reversed(result)))
    return {"verdict": VERDICT_OK, "value": value, "op": "sub", "steps": steps}


def wire_mul(a: int, b: int, max_steps: int = MAX_MUL_STEPS) -> Dict[str, Any]:
    """乗算 = wire_add の反復 (小さい方を回数に)。予算超えは型付き.

    `max_steps` is a parameter rather than only a constant because the
    capacity-calibration loop needs to re-run the very queries that exhausted
    it at a larger value and observe whether the verdict changes — that
    re-run is the test of the `needs_more_capacity` classification itself.
    """
    lo, hi = (a, b) if a <= b else (b, a)
    if lo > max_steps:
        return {
            "verdict": "UNKNOWN_BUDGET",
            "value": None,
            "op": "mul",
            "steps": [],
            "reason": f"repeat>{max_steps}",
        }
    acc = 0
    n_adds = 0
    for _ in range(lo):
        r = wire_add(acc, hi)
        if r["verdict"] != VERDICT_OK:
            r["op"] = "mul"
            r["n_adds"] = n_adds
            return r
        acc = r["value"]
        n_adds += 1
    return {
        "verdict": VERDICT_OK,
        "value": acc,
        "op": "mul",
        "steps": [],
        "n_adds": n_adds,
    }


_OPS = {"+": wire_add, "-": wire_sub, "*": wire_mul}


# ---------------------------------------------------------------------------
# 道3: Matryoshka 式評価 (括弧の深さ = 層)
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\d+|[()+\-*]")


def _lex(expr: str) -> Optional[List[str]]:
    toks = _TOKEN.findall(expr or "")
    if "".join(toks).replace(" ", "") != re.sub(r"\s+", "", expr or ""):
        return None
    return toks


def _eval_flat(tokens: List[str], mul_steps: int = MAX_MUL_STEPS) -> Dict[str, Any]:
    """括弧なし列を評価: * を先に、+/- を左から (全演算 wire)."""
    if not tokens or len(tokens) % 2 == 0:
        return {"verdict": "UNKNOWN_UNPARSED", "value": None}
    try:
        vals = [int(tokens[i]) for i in range(0, len(tokens), 2)]
    except ValueError:
        return {"verdict": "UNKNOWN_UNPARSED", "value": None}
    ops = [tokens[i] for i in range(1, len(tokens), 2)]
    if any(o not in _OPS for o in ops):
        return {"verdict": "UNKNOWN_UNPARSED", "value": None}

    # pass 1: 乗算
    i = 0
    while i < len(ops):
        if ops[i] == "*":
            r = wire_mul(vals[i], vals[i + 1], max_steps=mul_steps)
            if r["verdict"] != VERDICT_OK:
                return r
            vals[i:i + 2] = [r["value"]]
            ops.pop(i)
        else:
            i += 1
    # pass 2: 加減 左から
    acc = vals[0]
    for op, v in zip(ops, vals[1:]):
        r = _OPS[op](acc, v)
        if r["verdict"] != VERDICT_OK:
            return r
        acc = r["value"]
    return {"verdict": VERDICT_OK, "value": acc}


def eval_expr(expr: str, mul_steps: int = MAX_MUL_STEPS) -> Dict[str, Any]:
    """Matryoshka 評価: 最内括弧 → 値 → 上の層へ、を収束まで."""
    tokens = _lex(expr)
    if tokens is None or not tokens:
        return {"verdict": "UNKNOWN_UNPARSED", "value": None, "layers": []}
    layers: List[Dict[str, Any]] = []
    layer_no = 0
    while "(" in tokens:
        # 最内の括弧対
        open_i = -1
        for i, t in enumerate(tokens):
            if t == "(":
                open_i = i
            elif t == ")":
                if open_i < 0:
                    return {
                        "verdict": "UNKNOWN_UNPARSED",
                        "value": None,
                        "layers": layers,
                    }
                inner = tokens[open_i + 1:i]
                r = _eval_flat(inner, mul_steps=mul_steps)
                if r["verdict"] != VERDICT_OK:
                    r["layers"] = layers
                    return r
                layers.append(
                    {"layer": layer_no, "expr": " ".join(inner),
                     "value": r["value"]}
                )
                layer_no += 1
                tokens[open_i:i + 1] = [str(r["value"])]
                break
        else:
            return {
                "verdict": "UNKNOWN_UNPARSED",
                "value": None,
                "layers": layers,
            }
    r = _eval_flat(tokens, mul_steps=mul_steps)
    if r["verdict"] != VERDICT_OK:
        r["layers"] = layers
        return r
    layers.append({"layer": layer_no, "expr": " ".join(tokens), "value": r["value"]})
    return {"verdict": VERDICT_OK, "value": r["value"], "layers": layers}


# ---------------------------------------------------------------------------
# 道2: 型付き方程式 (提案 → wire 検査 → 合意)
# ---------------------------------------------------------------------------

def solve_equation(
    equation: str, *, limit: int = 200, mul_steps: int = MAX_MUL_STEPS
) -> Dict[str, Any]:
    """x を 1 つ含む等式を候補探索で解く (検査は wire 演算)。

    一意 → ANSWER / 複数 → AMBIGUOUS。

    解が見つからなかったときの verdict は 2 つに分かれる。以前はどちらも
    UNKNOWN_NO_SOLUTION と言っていたが、それは過大主張だった: "x + 3 = 940"
    の解 x=937 は実在し、探索範囲 0..200 の外にあっただけだ。「範囲内に
    無かった」を「無い」と言う計算機の上では、その verdict から学ぶ分類器も
    較正器も全部間違った結論を学ぶ。

    区別は列挙が既に持っている情報から取れる。x はちょうど 1 回しか現れず
    (上でガード済み)、演算は +,-,* のみで自然数上どれも各引数に単調、
    単調写像の合成は単調 — つまり x_side は x について大域単調であることが
    構造から保証される。全候補を評価済みなので向きは観測できる:

      非減少で最終値が target を超えた → これ以上遠くに解はない
                                          → UNKNOWN_NO_SOLUTION (確定)
      非増加で最終値が target 未満     → 同上
      全値が同一 (定数) で target 以外  → 同上
      まだ target に向かっている途中    → UNKNOWN_BUDGET
                                          "no_solution_in_0..limit"

    途中の候補が wire 演算の overflow で評価不能だった場合は列が欠けるので、
    確定は主張せず UNKNOWN_BUDGET に留まる。
    """
    if "=" not in (equation or ""):
        return {"verdict": "UNKNOWN_UNPARSED", "x": None, "solutions": []}
    lhs, rhs = equation.split("=", 1)
    if (lhs + rhs).count("x") != 1:
        return {"verdict": "UNKNOWN_UNPARSED", "x": None, "solutions": []}

    target_side, x_side = (rhs, lhs) if "x" in lhs else (lhs, rhs)
    tgt = eval_expr(target_side, mul_steps=mul_steps)
    if tgt["verdict"] != VERDICT_OK:
        return {
            "verdict": tgt["verdict"],
            "x": None,
            "solutions": [],
            "reason": "target_side_failed",
        }
    target = tgt["value"]

    solutions: List[int] = []
    values: List[int] = []
    complete = True  # every candidate in range evaluated successfully
    for cand in range(0, limit + 1):
        trial = eval_expr(x_side.replace("x", str(cand)), mul_steps=mul_steps)
        if trial["verdict"] != VERDICT_OK:
            complete = False
            continue
        values.append(trial["value"])
        if trial["value"] == target:
            solutions.append(cand)
            if len(solutions) > 1:
                break  # 複数確定 → AMBIGUOUS
    if not solutions:
        certain = False
        if complete and len(values) >= 2:
            nondec = all(b >= a for a, b in zip(values, values[1:]))
            noninc = all(b <= a for a, b in zip(values, values[1:]))
            certain = (
                (nondec and noninc)                      # 定数で target 以外
                or (nondec and values[-1] > target)      # 通り過ぎた
                or (noninc and values[-1] < target)
            )
        if certain:
            return {
                "verdict": "UNKNOWN_NO_SOLUTION",
                "x": None,
                "solutions": [],
                "searched": limit,
                "reason": "monotone_past_target",
            }
        return {
            "verdict": "UNKNOWN_BUDGET",
            "x": None,
            "solutions": [],
            "searched": limit,
            "reason": f"no_solution_in_0..{limit}",
        }
    if len(solutions) > 1:
        return {
            "verdict": "AMBIGUOUS",
            "x": None,
            "solutions": solutions,
            "reason": "multiple_solutions",
        }
    return {"verdict": VERDICT_OK, "x": solutions[0], "solutions": solutions}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def math_ask(
    query: str, *, solve_limit: int = 200, mul_steps: int = MAX_MUL_STEPS
) -> Dict[str, Any]:
    """"what is 2 + 3" / "(2+3)*4" / "x + 3 = 7" / "1+1=" を型付きで解く.

    limits はキーワード引数。既定値はこれまでの定数と同一なので、引数を
    渡さない既存呼び出しの挙動は変わらない。渡すのは 2 箇所だけ:
    domains の登録ラッパ (設定値を反映) と capacity_calibration (拡大した
    値で再実行して needs_more_capacity 分類そのものを検証する)。
    """
    q = (query or "").strip().lower()
    q = re.sub(r"^(what\s+is|compute|solve)\s+", "", q).rstrip("?").strip()
    if "=" in q and "x" in q:
        out = solve_equation(q, limit=solve_limit, mul_steps=mul_steps)
        out["mode"] = "equation"
        return out
    # 電卓風の末尾 "=" ("1+1=", "1+1 = ") は式であって方程式ではない —
    # x が無ければ左辺だけを評価する (右辺が省略された calculator 記法)
    if q.endswith("="):
        q = q[:-1].strip()
    out = eval_expr(q, mul_steps=mul_steps)
    out["mode"] = "expression"
    return out
