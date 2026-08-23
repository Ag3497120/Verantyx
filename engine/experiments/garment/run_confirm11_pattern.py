# -*- coding: utf-8 -*-
"""型紙の確認測定 — PREREG11_PATTERN.md の VT1〜VT8。

測るのは「足りない寸法を勝手に埋めないこと」と「縫えない型紙を縫えるように
見せないこと」。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, is_generated                # noqa: E402
from verantyx.garment_measure import Measures                    # noqa: E402
from verantyx.garment_pattern import (EASE_IN, FORMULAS,         # noqa: E402
                                      REQUIRED, draft, save, to_svg)

RESULTS = {"prereg": "experiments/garment/PREREG11_PATTERN.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def full() -> Measures:
    m = Measures()
    for spot, v in (("body_length", 96.0), ("chest", 104.0),
                    ("shoulder", 47.0), ("sleeve_length", 59.0)):
        m.measured(spot, v, "cm", source="実物採寸", by="担当:西小田")
    return m


# ---------------------------------------------------------------- VT1
def vt1():
    """型紙は派生。**どの寸法から引いたかが残る。**"""
    d = draft(full())
    ok = (d["verdict"] == "ANSWER"
          and set(d["used"]) >= set(REQUIRED)
          and d["used"]["chest"] == 104.0
          and "実物の型紙を見たものではありません" in d["note"])
    record("VT1_the_pattern_is_derived_and_names_its_inputs", ok,
           {"used": d["used"]})


# ---------------------------------------------------------------- VT2
def vt2():
    """**足りない寸法を既定で埋めない。** 立体とはここが違う。"""
    empty = draft(Measures())
    partial = Measures()
    partial.measured("chest", 104.0, "cm", source="採寸", by="担当")
    some = draft(partial)
    # 袖だけ足りない場合は、身頃は引けて袖だけ出ない
    no_sleeve = Measures()
    for spot, v in (("body_length", 96.0), ("chest", 104.0),
                    ("shoulder", 47.0)):
        no_sleeve.measured(spot, v, "cm", source="採寸", by="担当")
    d = draft(no_sleeve)
    ok = (empty["verdict"] == "UNKNOWN_MISSING_MEASUREMENTS"
          and set(empty["missing"]) == set(REQUIRED)
          and empty.get("how_to_close")
          and "pieces" not in empty
          and some["verdict"] == "UNKNOWN_MISSING_MEASUREMENTS"
          and "chest" not in some["missing"]
          and d["verdict"] == "ANSWER"
          and [p["name"] for p in d["pieces"]] == ["後身頃", "前身頃"]
          and d["sleeve_missing"] == ["sleeve_length"])
    record("VT2_missing_measurements_are_never_filled_with_defaults", ok,
           {"empty": empty["missing"], "partial": some["missing"],
            "pieces_without_sleeve": [p["name"] for p in d["pieces"]]})


# ---------------------------------------------------------------- VT3
def vt3():
    """同じ寸法から同じ座標。"""
    a = draft(full())
    b = draft(full())
    ok = (a["pieces"] == b["pieces"]
          and a["seam_checks"] == b["seam_checks"]
          and to_svg(a) == to_svg(b))
    record("VT3_deterministic", ok,
           {"same": a["pieces"] == b["pieces"],
            "pieces": len(a["pieces"])})


# ---------------------------------------------------------------- VT4
def vt4():
    """**縫い合わせの差を必ず出す。** 合っていることを主張しない。"""
    d = draft(full())
    checks = {c["label"]: c for c in d["seam_checks"]}
    cap = checks["袖山と袖ぐり"]
    ok = (len(checks) == 3
          and all("difference" in c for c in d["seam_checks"])
          and all("sewable" in c for c in d["seam_checks"])
          and all(c["why"] for c in d["seam_checks"])
          and abs(checks["肩線"]["difference"]) <= 0.3
          # 袖山は狙った分だけ長い。**0 ではなく、いせ込みの分。**
          and abs(cap["difference"] - EASE_IN) < 0.1
          and cap["sewable"])
    record("VT4_every_seam_pair_reports_its_difference", ok,
           {k: c["difference"] for k, c in checks.items()})


# ---------------------------------------------------------------- VT5
def vt5():
    """書き出した型紙は生成物。**そこから観測はできない。**"""
    with tempfile.TemporaryDirectory() as dd:
        p = Path(dd) / "pattern.svg"
        info = save(full(), p)
        led = Ledger()
        refused = False
        try:
            led.observe("back", "structure", "背中心切替あり", "型紙から",
                        ref_path=str(p))
        except ValueError as e:
            refused = "UNKNOWN_GENERATED_NOT_EVIDENCE" in str(e)
        ok = (is_generated(p) and refused and Path(info["stamp"]).exists())
        record("VT5_the_pattern_cannot_be_read_back_as_evidence", ok,
               {"marked": is_generated(p), "observe_refused": refused})


# ---------------------------------------------------------------- VT6
def vt6():
    """**既存の製図法を名乗らない。** 式は全部出す。"""
    d = draft(full())
    blob = json.dumps(d, ensure_ascii=False) + to_svg(d)
    names = [w for w in ("文化式", "ドレメ式", "原型を使用", "JIS製図")
             if w in blob and w not in d["not_a_published_system"]]
    ok = (not names
          and set(d["formulas"]) == set(FORMULAS)
          and len(FORMULAS) >= 8
          and "公表された" in d["not_a_published_system"])
    record("VT6_it_does_not_claim_a_published_drafting_system", ok,
           {"claimed_names": names, "formulas": len(d["formulas"])})


# ---------------------------------------------------------------- VT7
def vt7():
    """**縫い代は入っていないと言う。**"""
    d = draft(full())
    ok = ("縫い代は入っていません" in d["seam_allowance"]
          and "出来上がり線" in d["seam_allowance"]
          and d["seam_allowance"] in to_svg(d))
    record("VT7_it_says_there_is_no_seam_allowance", ok,
           {"note": d["seam_allowance"]})


# ---------------------------------------------------------------- VT8
def vt8():
    """ピースごとの面積が出る。**立体からではなく型紙から見積もれる。**"""
    d = draft(full())
    areas = {p["name"]: p["area_cm2"] for p in d["pieces"]}
    ok = (all(a > 0 for a in areas.values())
          and abs(d["total_area_cm2"] - round(sum(areas.values()), 1)) < 0.05
          and len(areas) == 3)
    record("VT8_area_per_piece_is_reported", ok,
           {"areas": areas, "total": d["total_area_cm2"]})


if __name__ == "__main__":
    for f in (vt1, vt2, vt3, vt4, vt5, vt6, vt7, vt8):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_pattern.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
