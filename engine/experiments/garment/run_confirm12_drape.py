# -*- coding: utf-8 -*-
"""布の落ち方と検証器の確認測定 — PREREG12_DRAPE.md の VE1〜VE8。

測るのは「順序や初期配置が決めた皺を、物理として見せないこと」。
"""
import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, mark_generated                # noqa: E402
from verantyx.garment_drape import (LOCAL_MINIMUM, NOT_CONVERGED,   # noqa: E402
                                    NO_MATERIAL, ORDER_DEPENDENT,
                                    check_energy, check_order,
                                    check_scales, check_starts, grid,
                                    material_from, solve, validate)
from verantyx.garment_material import Fabrics                       # noqa: E402

RESULTS = {"prereg": "experiments/garment/PREREG12_DRAPE.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fabrics() -> Fabrics:
    f = Fabrics()
    f.record("テスト布", "weight", 200, "試験資料 A")
    f.record("テスト布", "thickness", 0.5, "試験資料 A")
    return f


def setup():
    mat = material_from(fabrics(), "テスト布")
    pts, edges = grid(9, 9, 40.0, 40.0)
    return pts, edges, [0, 8], mat


# ---------------------------------------------------------------- VE1
def ve1():
    """同じ入力・同じ順序から同じ座標。"""
    pts, edges, pin, mat = setup()
    a = solve(pts, edges, pin, mat, iterations=120)
    b = solve(pts, edges, pin, mat, iterations=120)
    ok = (a["points"] == b["points"] and a["energy"] == b["energy"])
    record("VE1_deterministic", ok,
           {"same_points": a["points"] == b["points"],
            "vertices": len(a["points"])})


# ---------------------------------------------------------------- VE2
def ve2():
    """**順序不変。** 落ちたら形を返さない。

    そして検査が本当に発火することを確かめる — 発火しない検査は
    通っても意味が無い。
    """
    pts, edges, pin, mat = setup()
    loose = check_order(pts, edges, pin, mat, iterations=300)
    strict = check_order(pts, edges, pin, mat, iterations=300,
                         tolerance=0.001)
    ok = (loose["verdict"] == "ANSWER"
          and strict["verdict"] == ORDER_DEPENDENT
          and strict.get("how_to_close")
          and loose["worst_difference"] > 0)   # 差は実在する
    record("VE2_order_invariance_is_checked_and_the_check_can_fail", ok,
           {"difference": loose["worst_difference"],
            "loose": loose["verdict"], "strict": strict["verdict"]})


# ---------------------------------------------------------------- VE3
def ve3():
    """**順序依存は反復とともに育つ。** 収束させても消えない。

    「よく収束させた」ことが「順序に依らない」を意味しない — これが
    分かっていないと、反復を増やして安心してしまう。
    """
    pts, edges, pin, mat = setup()
    diffs = [check_order(pts, edges, pin, mat,
                         iterations=it)["worst_difference"]
             for it in (50, 300, 800)]
    ok = (diffs[0] < diffs[1] < diffs[2])
    record("VE3_order_dependence_grows_with_iterations", ok,
           {"iterations": [50, 300, 800], "differences": diffs})


# ---------------------------------------------------------------- VE4
def ve4():
    """**多点始動。** 割れたら片方を選ばず、全部の形を返す。"""
    pts, edges, pin, mat = setup()
    strict = check_starts(pts, edges, pin, mat, iterations=200,
                          tolerance=0.01)
    loose = check_starts(pts, edges, pin, mat, iterations=200)
    ok = (strict["verdict"] == LOCAL_MINIMUM
          and len(strict["shapes"]) == 3
          and "片方を選んでいません" in strict.get("note", "")
          and loose["verdict"] == "ANSWER")
    record("VE4_split_starts_return_every_shape_not_one", ok,
           {"strict": strict["verdict"], "shapes": len(strict["shapes"]),
            "loose": loose["verdict"]})


# ---------------------------------------------------------------- VE5
def ve5():
    """**段の収束。** 収束しなければ段ごとの差を出す。"""
    _, _, _, mat = setup()
    got = check_scales(40.0, 40.0, True, mat, iterations=200)
    tight = check_scales(40.0, 40.0, True, mat, iterations=200,
                         tolerance=0.001)
    ok = (got["verdict"] == "ANSWER"
          and len(got["differences"]) == 2
          and got["shrinking"]
          and tight["verdict"] == NOT_CONVERGED
          and tight.get("how_to_close"))
    record("VE5_scale_convergence_is_measured_and_can_fail", ok,
           {"differences": got["differences"], "shrinking": got["shrinking"],
            "tight": tight["verdict"]})


# ---------------------------------------------------------------- VE6
def ve6():
    """エネルギーが単調に下がる。

    **PBD には減少するエネルギーが定義されない** ので、この検査は
    勾配を降りる解法にだけ意味がある。最初 PBD で書いてエネルギーが
    上がり、そこで解法を替えた。
    """
    pts, edges, pin, mat = setup()
    got = check_energy(pts, edges, pin, mat, iterations=400)
    ok = (got["verdict"] == "ANSWER" and got["rises"] == 0
          and got["last"] < got["first"]
          and "PBD" in got["why"])
    record("VE6_energy_decreases_monotonically", ok,
           {"first": got["first"], "last": got["last"],
            "rises": got["rises"], "steps": got["steps"]})


# ---------------------------------------------------------------- VE7
def ve7():
    """**生地の物性が無ければ落とさない。** 既定で埋めない。"""
    empty = material_from(Fabrics(), "知らない布")
    partial = Fabrics()
    partial.record("半分", "weight", 200, "資料")
    half = material_from(partial, "半分")
    # 割れている生地も数にならないので落とせない
    split = fabrics()
    split.record("テスト布", "weight", 180, "別の資料 B")
    contested = material_from(split, "テスト布")
    ok = (empty["verdict"] == NO_MATERIAL
          and set(empty["missing"]) == {"weight", "thickness"}
          and half["verdict"] == NO_MATERIAL
          and half["missing"] == ["thickness"]
          and contested["verdict"] == NO_MATERIAL
          and validate(material=empty)["verdict"] == NO_MATERIAL)
    record("VE7_no_material_no_drape", ok,
           {"empty": empty["missing"], "half": half["missing"],
            "contested_weight_blocks_it": contested["verdict"]})


# ---------------------------------------------------------------- VE8
def ve8():
    """落とした形は生成物。**観測の出典にできない。**

    そして検査が落ちたときは形そのものを返さない。
    """
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "drape.obj"
        p.write_text("x", encoding="utf-8")
        mark_generated(p)
        led = Ledger()
        refused = False
        try:
            led.observe("body", "silhouette", "落ちた形から", "シミュ",
                        ref_path=str(p))
        except ValueError as e:
            refused = "UNKNOWN_GENERATED_NOT_EVIDENCE" in str(e)
    mat = material_from(fabrics(), "テスト布")
    good = validate(material=mat, iterations=200)
    bad = validate(material=mat, iterations=200,
                   tolerances={"order": 0.0001})
    ok = (refused
          and "points" in good and good["verdict"] == "ANSWER"
          and "points" not in bad
          and bad.get("why_no_shape")
          and "観測の出典にはできません" in good["not_a_measurement"])
    record("VE8_the_drape_is_generated_and_withheld_when_checks_fail", ok,
           {"observe_refused": refused, "good": good["verdict"],
            "failed_returns_no_shape": "points" not in bad,
            "failed": bad.get("failed")})


if __name__ == "__main__":
    for f in (ve1, ve2, ve3, ve4, ve5, ve6, ve7, ve8):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_drape.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
