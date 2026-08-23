# -*- coding: utf-8 -*-
"""生地の性質と重ね着の確認測定 — PREREG10_LAYERS.md の VL1〜VL9。

測るのは「割れを隠した生地表にしないこと」と「下限を必要量に見せない
こと」。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger                              # noqa: E402
from verantyx.garment_material import (Fabrics, NO_SOURCE,       # noqa: E402
                                       SPLIT, UNKNOWN,
                                       cloth_estimate, layer_fit,
                                       surface_area)
from verantyx.garment_measure import Measures                    # noqa: E402
from verantyx.garment_solid import build                         # noqa: E402

RESULTS = {"prereg": "experiments/garment/PREREG10_LAYERS.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fixture() -> Fabrics:
    f = Fabrics()
    f.record("メルトン", "weight", 450, "A社仕様書 2024")
    f.record("メルトン", "thickness", 2.4, "A社仕様書 2024")
    f.record("キュプラ", "weight", 78, "裏地資料 p.4")
    f.record("キュプラ", "thickness", 0.2, "裏地資料 p.4")
    return f


def solid() -> dict:
    led = Ledger()
    led.observe("body", "silhouette", "Aライン", "cut 0:12:07")
    m = Measures()
    m.measured("body_length", 96.0, "cm", source="採寸", by="担当")
    return build(led, m)


# ---------------------------------------------------------------- VL1
def vl1():
    """**出典の無い性質は入らない。**"""
    f = Fabrics()
    refused = []
    for src in ("", "   "):
        try:
            f.record("メルトン", "weight", 450, src)
            refused.append(False)
        except ValueError as e:
            refused.append(NO_SOURCE in str(e))
    bad_prop = False
    try:
        f.record("メルトン", "色", "黒", "資料")
    except ValueError as e:
        bad_prop = "UNKNOWN_PROPERTY" in str(e)
    ok = all(refused) and bad_prop and not f.entries
    record("VL1_a_property_without_a_source_is_refused", ok,
           {"refused": refused, "unknown_property_refused": bad_prop,
            "ledger_empty": not f.entries})


# ---------------------------------------------------------------- VL2
def vl2():
    """食い違いは割れとして出る。**片方を勝たせない。**"""
    f = fixture()
    f.record("メルトン", "weight", 420, "B社カタログ #77")
    s = f.state("メルトン", "weight")
    sides = {x["value"] for x in s.get("sides", [])}
    # 十字も同じものを矛盾として拾う
    contra = f.cross().contradictions("fabric:メルトン")
    keys = set()
    for row in contra:
        k = row.get("key") or row.get("aspect")
        if k:
            keys.add(str(k))
        for v in row.get("values", []) or []:
            if ":" in v:
                keys.add(v.split(":", 1)[0])
    ok = (s["state"] == SPLIT and sides == {"420", "450"}
          and f.number("メルトン", "weight") is None
          and "weight" in keys)
    record("VL2_disagreeing_sources_are_kept_as_a_split", ok,
           {"state": s["state"], "sides": sorted(sides),
            "cross_agrees": "weight" in keys,
            "not_turned_into_a_number": f.number("メルトン", "weight") is None})


# ---------------------------------------------------------------- VL3
def vl3():
    """面積から出した重さは派生。**面積と目付の両方が残る。**"""
    f = fixture()
    sol = solid()
    est = cloth_estimate(sol, f, "メルトン")
    ok = (est["state"] == "DERIVED"
          and est["gsm"] == 450.0
          and est["surface_area_m2"] > 0
          # 書いた式を検算したら書いた数になること
          and est["weight_g"] == round(est["surface_area_m2"] * 450.0, 1)
          and "実測ではありません" in est["note"]
          and "×" in est["from"])
    record("VL3_weight_from_area_is_derived_not_measured", ok,
           {"state": est["state"], "from": est["from"],
            "weight_g": est["weight_g"]})


# ---------------------------------------------------------------- VL4
def vl4():
    """**型紙が無いことを言う。** 下限の目安であって必要量ではない。"""
    est = cloth_estimate(solid(), fixture(), "メルトン")
    ok = ("型紙ではありません" in est["not_a_yardage"]
          and "下限の目安" in est["not_a_yardage"]
          and "必要な" in est["not_a_yardage"])
    record("VL4_it_says_this_is_not_a_yardage", ok,
           {"disclaimer": est["not_a_yardage"][:44]})


# ---------------------------------------------------------------- VL5
def vl5():
    """重ね着の可否は引き算。**片方が無ければ出ない。**"""
    f = fixture()
    got = layer_fit(100.0, 110.0, [f.number("メルトン", "thickness")])
    none_inner = layer_fit(None, 110.0, [2.4])
    none_thick = layer_fit(100.0, 110.0, [None])
    ok = (got["verdict"] == "ANSWER" and got["fits"] is True
          and none_inner["verdict"] == "UNKNOWN_NO_BASIS"
          and "内側の外周" in none_inner["missing"]
          and none_thick["verdict"] == "UNKNOWN_NO_BASIS"
          and none_thick.get("how_to_close"))
    record("VL5_layer_fit_is_a_subtraction_and_needs_every_side", ok,
           {"slack": got["slack_cm"], "missing_inner": none_inner["missing"],
            "missing_thickness": none_thick["missing"]})


# ---------------------------------------------------------------- VL6
def vl6():
    """**入らないものは入らないと言う。** 負を丸めない。"""
    tight = layer_fit(110.0, 108.0, [2.4])
    ok = (tight["slack_cm"] < 0 and tight["fits"] is False
          and tight["slack_cm"] == round(108.0 - 110.0
                                         - 2.4 / 10.0 * 2 * 3.141592653589793,
                                         1))
    record("VL6_a_garment_that_does_not_go_over_says_so", ok,
           {"slack": tight["slack_cm"], "fits": tight["fits"]})


# ---------------------------------------------------------------- VL7
def vl7():
    """**布の落ち方を主張しない。**"""
    blob = (json.dumps(layer_fit(100.0, 110.0, [2.4]), ensure_ascii=False)
            + json.dumps(cloth_estimate(solid(), fixture(), "メルトン"),
                         ensure_ascii=False))
    # **話題語ではなく断定形を禁じる。** 計算しないものを名指しするのは
    # 主張ではない — そこを禁じると、正直な但し書きほど落ちる。
    # (V63 で「オリジナル」を否定形ごと禁じた件とは性質が違う。あちらは
    #  判定語で、切り出されれば断定に読める。こちらは話題語。)
    claims = [w for w in ("皺が出ます", "動きやすいです", "着心地は良",
                          "シミュレーションした結果", "drape simulation",
                          "as it hangs")
              if w in blob]
    ok = (not claims
          and "布の落ち方・皺・動きやすさは計算していません"
          in layer_fit(100.0, 110.0, [2.4])["not_a_drape"])
    record("VL7_it_does_not_claim_how_the_cloth_falls", ok,
           {"claiming_words_found": claims})


# ---------------------------------------------------------------- VL8
def vl8():
    """同じ入力から同じ答え。"""
    f, sol = fixture(), solid()
    a = json.dumps(cloth_estimate(sol, f, "メルトン"), ensure_ascii=False,
                   sort_keys=True)
    b = json.dumps(cloth_estimate(sol, f, "メルトン"), ensure_ascii=False,
                   sort_keys=True)
    c = surface_area(sol)
    d = surface_area(build(Ledger(), None))
    ok = (a == b and c == surface_area(sol) and d == 0.0)
    record("VL8_deterministic", ok,
           {"same": a == b, "empty_solid_area": d})


# ---------------------------------------------------------------- VL9
def vl9():
    """**十字は生地台帳を書き換えない。** 像であって台帳ではない。"""
    f = fixture()
    before = json.dumps([e.__dict__ for e in f.entries],
                        ensure_ascii=False, sort_keys=True)
    for _ in range(3):
        f.cross()
        f.report()
    after = json.dumps([e.__dict__ for e in f.entries],
                       ensure_ascii=False, sort_keys=True)
    empty = Fabrics().report()
    ok = (before == after and empty["counts"]["recorded"] == 0
          and not empty["fabrics"])
    record("VL9_the_cross_never_writes_back_to_the_fabric_ledger", ok,
           {"unchanged": before == after,
            "empty_stays_empty": empty["counts"]})


if __name__ == "__main__":
    for f_ in (vl1, vl2, vl3, vl4, vl5, vl6, vl7, vl8, vl9):
        f_()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_layers.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
