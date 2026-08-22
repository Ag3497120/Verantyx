# -*- coding: utf-8 -*-
"""寸法の確認測定 — PREREG6_MEASURE.md の VD1〜VD5。

測るのは「比率から出した数字が実寸の顔をしないこと」。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment_measure import (Measures, NOT_TAKEN,      # noqa: E402
                                      NO_BASIS, NO_UNIT, SPOTS)

RESULTS = {"prereg": "experiments/garment/PREREG6_MEASURE.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- VD1
def vd1():
    """基準の無い比率は長さにならない。"""
    m = Measures()
    m.ratio("sleeve_length", 0.62, "body_length", source="映像からの比率読み")
    s = m.state("sleeve_length")
    sheet = m.sheet()
    in_measured = any(r["spot"] == "sleeve_length" for r in sheet["measured"])
    in_derived = any(r["spot"] == "sleeve_length" for r in sheet["derived"])
    ok = (s["state"] == NO_BASIS and s.get("how_to_close")
          and not in_measured and not in_derived
          and "value" not in s)
    record("VD1_a_ratio_without_a_basis_is_not_a_length", ok,
           {"state": s["state"], "has_closer": bool(s.get("how_to_close")),
            "leaked_into_measured": in_measured,
            "leaked_into_derived": in_derived})


# ---------------------------------------------------------------- VD2
def vd2():
    """単位の無い数字を受け取らない。"""
    m = Measures()
    refused = []
    for unit in ("", "  ", "尺", "cm2"):
        try:
            m.measured("chest", 104, unit, source="x")
            refused.append(False)
        except ValueError as e:
            refused.append(NO_UNIT in str(e))
    ok = all(refused) and not m.entries
    record("VD2_a_number_without_a_unit_is_refused", ok,
           {"all_refused": all(refused), "ledger_empty": not m.entries})


# ---------------------------------------------------------------- VD3
def vd3():
    """基準が入ると比率は長さになる。**ただし実測と同じ欄には入らない。**"""
    m = Measures()
    m.ratio("sleeve_length", 0.62, "body_length", source="比率読み")
    m.measured("body_length", 96.0, "cm", source="実物採寸", by="担当:西小田")
    s = m.state("sleeve_length")
    sheet = m.sheet()
    measured_spots = {r["spot"] for r in sheet["measured"]}
    derived_spots = {r["spot"] for r in sheet["derived"]}
    ok = (s["state"] == "DERIVED" and s["value"] == 59.5 and s["unit"] == "cm"
          and "sleeve_length" in derived_spots
          and "sleeve_length" not in measured_spots
          and "body_length" in measured_spots
          and s.get("note"))
    record("VD3_a_derived_length_never_enters_the_measured_column", ok,
           {"state": s["state"], "value": s.get("value"),
            "from": s.get("from"), "measured": sorted(measured_spots),
            "derived": sorted(derived_spots)})


# ---------------------------------------------------------------- VD4
def vd4():
    """寸法表は欠けを隠さない。"""
    m = Measures()
    m.measured("body_length", 96.0, "cm", source="実物採寸", by="担当")
    sheet = m.sheet()
    total = (sheet["counts"]["measured"] + sheet["counts"]["derived"]
             + sheet["counts"]["open"])
    all_have_closer = all(r.get("how_to_close") for r in sheet["open"])
    ok = (total == len(SPOTS) and sheet["counts"]["open"] == len(SPOTS) - 1
          and all_have_closer)
    record("VD4_the_sheet_does_not_hide_what_is_missing", ok,
           {"total_rows": total, "spots": len(SPOTS),
            "counts": sheet["counts"], "every_open_says_how": all_have_closer})


# ---------------------------------------------------------------- VD5
def vd5():
    """入れる順で寸法表は変わらない。"""
    acts = [
        lambda m: m.ratio("sleeve_length", 0.62, "body_length", source="比率"),
        lambda m: m.measured("body_length", 96.0, "cm", source="採寸", by="担当"),
        lambda m: m.measured("shoulder", 45.0, "cm", source="採寸", by="担当"),
        lambda m: m.ratio("hem_width", 1.15, "chest", source="比率"),
    ]

    def build(order):
        m = Measures()
        for i in order:
            acts[i](m)
        sheet = m.sheet()
        return json.dumps({k: sheet[k] for k in
                           ("measured", "derived", "open", "counts")},
                          ensure_ascii=False, sort_keys=True)

    a = build([0, 1, 2, 3])
    b = build([3, 2, 1, 0])
    c = build([1, 3, 0, 2])
    ok = (a == b == c)
    record("VD5_order_does_not_change_the_sheet", ok,
           {"same": a == b == c})


if __name__ == "__main__":
    for f in (vd1, vd2, vd3, vd4, vd5):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_measure.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
