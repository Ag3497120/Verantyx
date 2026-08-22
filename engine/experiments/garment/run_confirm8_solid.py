# -*- coding: utf-8 -*-
"""立体の確認測定 — PREREG8_SOLID.md の VS1〜VS7。

測るのは「観測していない立体を作らないこと」と「仮定を実測に見せないこと」。
立体は線画より説得力があるので、嘘の強度が上がる。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, is_generated                # noqa: E402
from verantyx.garment_measure import Measures                    # noqa: E402
from verantyx.garment_solid import (ASSUMED_DEPTH_RATIO,         # noqa: E402
                                    SOLIDABLE, build, save, to_obj)

RESULTS = {"prereg": "experiments/garment/PREREG8_SOLID.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fixture() -> Ledger:
    led = Ledger(title="映画X のコート")
    led.observe("body", "silhouette", "Aライン", "cut 0:12:07")
    led.observe("collar", "shape", "ノッチドラペル", "cut 0:12:05")
    led.infer("sleeve", "construction", "二枚袖", "袖山の皺から")
    return led


# ---------------------------------------------------------------- VS1
def vs1():
    """**台帳に無い面を作らない。** 推論しかない部位は面を持たない。"""
    led = fixture()
    s = build(led)
    parts = {g["part"] for g in s["groups"]}
    ok = (parts == {"body", "collar"}
          and "sleeve" not in parts
          and set(s["made"]) == parts
          and {x["part"] for x in s["skipped"]} == set(SOLIDABLE) - parts)
    record("VS1_no_surface_without_a_confirmed_aspect", ok,
           {"made": sorted(parts),
            "skipped": [x["part"] for x in s["skipped"]]})


# ---------------------------------------------------------------- VS2
def vs2():
    """同じ台帳からは同じ立体。**組み立てであって生成ではない。**"""
    m = Measures()
    m.measured("body_length", 96.0, "cm", source="採寸", by="担当")
    a = build(fixture(), m)
    b = build(fixture(), m)
    ok = (a["vertices"] == b["vertices"] and a["faces"] == b["faces"]
          and to_obj(a) == to_obj(b))
    record("VS2_the_same_ledger_always_builds_the_same_solid", ok,
           {"identical": a["vertices"] == b["vertices"],
            "vertices": len(a["vertices"]), "faces": len(a["faces"])})


# ---------------------------------------------------------------- VS3
def vs3():
    """作らなかった部位が名前で残る。**黙って消えない。**"""
    s = build(fixture())
    obj = to_obj(s)
    ok = (s["skipped"] and all(x["why"] for x in s["skipped"])
          and all(x["part"] in obj for x in s["skipped"])
          and "作らなかった部位" in obj)
    record("VS3_what_was_not_built_is_named", ok,
           {"skipped": [x["part"] for x in s["skipped"]],
            "named_in_obj": True})


# ---------------------------------------------------------------- VS4
def vs4():
    """書き出した立体は生成物。**そこから観測はできない。**"""
    with tempfile.TemporaryDirectory() as d:
        led = fixture()
        p = Path(d) / "block.obj"
        info = save(led, p)
        refused = False
        try:
            led.observe("back", "structure", "背中心切替あり", "立体から",
                        ref_path=str(p))
        except ValueError as e:
            refused = "UNKNOWN_GENERATED_NOT_EVIDENCE" in str(e)
        ok = (is_generated(p) and refused and Path(info["stamp"]).exists()
              and "vertices" not in info)
        record("VS4_the_solid_cannot_be_read_back_as_evidence", ok,
               {"marked": is_generated(p), "observe_refused": refused})


# ---------------------------------------------------------------- VS5
def vs5():
    """寸法が形を決める。既定で補ったものは名指しで残る。"""
    without = build(fixture())
    m = Measures()
    m.measured("body_length", 96.0, "cm", source="採寸", by="担当")
    with_dim = build(fixture(), m)
    ys_without = {v[1] for v in without["vertices"]}
    ys_with = {v[1] for v in with_dim["vertices"]}
    ok = (without["dimensions"]["body_length"] == 100.0
          and "body_length" in without["defaulted"]
          and with_dim["dimensions"]["body_length"] == 96.0
          and "body_length" not in with_dim["defaulted"]
          and ys_without != ys_with
          and "chest" in with_dim["defaulted"])
    record("VS5_measurements_shape_the_solid_and_defaults_are_named", ok,
           {"without": without["dimensions"]["body_length"],
            "with": with_dim["dimensions"]["body_length"],
            "still_defaulted": with_dim["defaulted"]})


# ---------------------------------------------------------------- VS6
def vs6():
    """**奥行きは仮定だと言う。** 比の値も出す。"""
    s = build(fixture())
    obj = to_obj(s)
    ok = (s["assumed"]["depth_ratio"] == ASSUMED_DEPTH_RATIO
          and "仮定" in s["assumed"]["why"]
          and "実測" in s["assumed"]["why"]
          and str(ASSUMED_DEPTH_RATIO) in obj
          and "仮定" in obj)
    record("VS6_the_assumed_depth_is_declared_as_assumed", ok,
           {"ratio": s["assumed"]["depth_ratio"],
            "declared_in_obj": "仮定" in obj})


# ---------------------------------------------------------------- VS7
def vs7():
    """**布の落ち方を主張しない。** 着装を名乗る語が出力に無い。"""
    s = build(fixture())
    blob = json.dumps(s, ensure_ascii=False) + to_obj(s)
    claims = [w for w in ("シミュレーション結果", "ドレープした",
                          "着装した", "simulated drape", "as worn")
              if w in blob]
    ok = (not claims and "布の落ち方は一切主張していません"
          in s["not_a_simulation"])
    record("VS7_it_does_not_claim_to_be_a_drape_simulation", ok,
           {"claiming_words_found": claims,
            "disclaimer": s["not_a_simulation"][:40]})


if __name__ == "__main__":
    for f in (vs1, vs2, vs3, vs4, vs5, vs6, vs7):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_solid.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
