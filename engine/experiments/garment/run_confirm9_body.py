# -*- coding: utf-8 -*-
"""基準体・ゆとり・サイズ展開の確認測定 — PREREG9_BODY.md の VB1〜VB8。

測るのは「観測していない体を観測にしないこと」と「知らない着心地を
語らないこと」。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, PARTS                       # noqa: E402
from verantyx.garment_body import (BODY_SIZES, NO_BASIS,         # noqa: E402
                                   body, ease, grade)
from verantyx.garment_measure import Measures                    # noqa: E402

RESULTS = {"prereg": "experiments/garment/PREREG9_BODY.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fixture() -> Measures:
    m = Measures()
    m.measured("chest", 104.0, "cm", source="実物採寸", by="担当:西小田")
    m.measured("shoulder", 47.0, "cm", source="実物採寸", by="担当:西小田")
    m.measured("body_length", 96.0, "cm", source="実物採寸", by="担当:西小田")
    return m


# ---------------------------------------------------------------- VB1
def vb1():
    """**基準体は観測ではない。** 台帳の観測欄に入らない。"""
    b = body("M")
    led = Ledger()
    before = len(led.entries)
    # 体の寸法は服の側面ではない。置こうとしても表に無い。
    is_a_garment_aspect = any("chest" in aspects for aspects in PARTS.values())
    ok = (b["kind"] == "reference_body"
          and "着る人ではありません" in b["note"]
          and not is_a_garment_aspect
          and len(led.entries) == before)
    record("VB1_the_reference_body_is_not_an_observation", ok,
           {"kind": b["kind"], "is_garment_aspect": is_a_garment_aspect})


# ---------------------------------------------------------------- VB2
def vb2():
    """ゆとりは引き算。**片方が無ければ出ない。**"""
    e = ease(fixture(), "M")
    got = {r["spot"]: r for r in e["rows"]}
    chest = got["chest"]
    waist = got["waist"]
    ok = (chest["ease"] == round(104.0 - BODY_SIZES["M"]["chest"], 1)
          and waist["state"] == NO_BASIS
          and "ease" not in waist
          and waist.get("how_to_close"))
    record("VB2_ease_is_a_subtraction_and_needs_both_sides", ok,
           {"chest_ease": chest["ease"], "waist": waist["state"]})


# ---------------------------------------------------------------- VB3
def vb3():
    """**負のゆとりを隠さない。** 入らない服は入らないと言う。"""
    m = Measures()
    m.measured("chest", 84.0, "cm", source="採寸", by="担当")
    e = ease(m, "M")
    chest = next(r for r in e["rows"] if r["spot"] == "chest")
    ok = (chest["ease"] < 0
          and chest["ease"] == round(84.0 - BODY_SIZES["M"]["chest"], 1)
          and "chest" in e["negative"])
    record("VB3_negative_ease_is_not_rounded_away", ok,
           {"ease": chest["ease"], "flagged": e["negative"]})


# ---------------------------------------------------------------- VB4
def vb4():
    """展開した寸法は実測ではない。**基準サイズと振り分け量が残る。**"""
    g = grade(fixture(), "M", ["S", "M", "L"])
    s_chest = next(r for r in g["table"]["S"] if r["spot"] == "chest")
    m_chest = next(r for r in g["table"]["M"] if r["spot"] == "chest")
    ok = (m_chest["state"] == "MEASURED"
          and s_chest["state"] == "GRADED"
          and s_chest["value"] == 100.0
          and s_chest["step"] == 4.0
          and "M の 104.0" in s_chest["from"]
          and g["base_size"] == "M")
    record("VB4_graded_sizes_are_not_measurements", ok,
           {"M": m_chest["state"], "S": s_chest["state"],
            "S_from": s_chest["from"]})


# ---------------------------------------------------------------- VB5
def vb5():
    """展開は基準を書き換えない。**読み出しであって書き込みではない。**"""
    m = fixture()
    before = json.dumps(m.sheet(), ensure_ascii=False, sort_keys=True)
    for _ in range(3):
        grade(m, "M")
        ease(m, "L")
        body("XL")
    after = json.dumps(m.sheet(), ensure_ascii=False, sort_keys=True)
    ok = (before == after)
    record("VB5_grading_never_rewrites_the_base_measurements", ok,
           {"unchanged": before == after})


# ---------------------------------------------------------------- VB6
def vb6():
    """同じ入力から同じ表。"""
    a = json.dumps(grade(fixture(), "M"), ensure_ascii=False, sort_keys=True)
    b = json.dumps(grade(fixture(), "M"), ensure_ascii=False, sort_keys=True)
    c = json.dumps(ease(fixture(), "M"), ensure_ascii=False, sort_keys=True)
    d = json.dumps(ease(fixture(), "M"), ensure_ascii=False, sort_keys=True)
    ok = (a == b and c == d)
    record("VB6_deterministic", ok, {"grade_same": a == b, "ease_same": c == d})


# ---------------------------------------------------------------- VB7
def vb7():
    """**着装を名乗らない。** 知らない着心地を語らない。"""
    blob = (json.dumps(ease(fixture(), "M"), ensure_ascii=False)
            + json.dumps(body("M"), ensure_ascii=False)
            + json.dumps(grade(fixture(), "M"), ensure_ascii=False))
    claims = [w for w in ("着た姿", "着装した", "フィットします",
                          "着心地は", "as worn", "fits well")
              if w in blob]
    ok = not claims
    record("VB7_it_never_claims_the_garment_was_worn", ok,
           {"claiming_words_found": claims})


# ---------------------------------------------------------------- VB8
def vb8():
    """**型紙が無いことを言う。** 引き算だと明記される。"""
    e = ease(fixture(), "M")
    ok = ("型紙" in e["not_a_fit_calculation"]
          and "引き算" in e["not_a_fit_calculation"]
          and "着る人ではありません" in e["reference_body"])
    record("VB8_it_says_there_is_no_pattern_behind_this", ok,
           {"disclaimer": e["not_a_fit_calculation"][:46]})


if __name__ == "__main__":
    for f in (vb1, vb2, vb3, vb4, vb5, vb6, vb7, vb8):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_body.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
