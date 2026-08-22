# -*- coding: utf-8 -*-
"""由来の欄の確認測定 — PREREG2_PROVENANCE.md の V63〜V70。

測るのは「この装置が『作ってよい』を言わないこと」。数値は実行結果のみ。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, PARTS                     # noqa: E402
from verantyx.garment_rights import (CONTESTED_ORIGIN,         # noqa: E402
                                     Design, NO_MATCH, RightsLedger,
                                     SPECIFIC, UNCHECKED)

RESULTS = {"prereg": "experiments/garment/PREREG2_PROVENANCE.md",
           "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def observed() -> Ledger:
    led = Ledger(title="映画X 00:14:32 のコート")
    led.observe("collar", "shape", "ノッチドラペル", "cut 0:14:32")
    led.observe("sleeve", "construction", "二枚袖", "cut 0:14:35")
    led.observe("body", "silhouette", "Aライン", "cut 0:14:40")
    return led


def rights() -> RightsLedger:
    r = RightsLedger()
    r.specific("collar", "shape", "映画X 公式衣装資料 p.12")
    r.generic("sleeve", "construction", "工業パターン教本 p.88")
    r.generic("sleeve", "construction", "既製品カタログ2019 #441")
    r.no_match("body", "silhouette", "手持ちの既製品カタログ3社分")
    return r


# ---------------------------------------------------------------- V63
def v63():
    """見つからなかったことを「オリジナル」にしない。"""
    r = rights()
    st = r.state("body", "silhouette")
    blob = json.dumps(r.report(PARTS), ensure_ascii=False)
    # 「オリジナル」を意味する状態がどこにも出ない
    banned = [w for w in ("ORIGINAL", "オリジナル", "問題なし", "合法")
              if w in blob]
    ok = (st["state"] == NO_MATCH and st["searched_scopes"] and not banned)
    record("V63_absence_of_match_is_not_originality", ok,
           {"state": st["state"], "scopes": st["searched_scopes"],
            "banned_words_found": banned})


# ---------------------------------------------------------------- V64
def v64():
    """合法/違法を出さない。問われたら型のついた断りを返す。"""
    r = rights()
    ans = r.may_i_make_this()
    ok = (ans["verdict"] == "UNKNOWN_NOT_A_LEGAL_JUDGMENT"
          and ans.get("how_to_close"))
    record("V64_no_legal_verdict_is_ever_returned", ok,
           {"verdict": ans["verdict"], "has_closer": bool(ans.get("how_to_close"))})


# ---------------------------------------------------------------- V65
def v65():
    """一般構造は独立2本の出典で買う。1本では買えない。"""
    r = RightsLedger()
    r.generic("pocket", "type", "工業パターン教本 p.90")
    one = r.state("pocket", "type")["state"]
    r.generic("pocket", "type", "工業パターン教本 p.90")   # 同じ出典
    dup = r.state("pocket", "type")["state"]
    r.generic("pocket", "type", "別の教本 p.14")
    two = r.state("pocket", "type")["state"]
    refused = False
    try:
        r.generic("pocket", "position", "")
    except ValueError:
        refused = True
    ok = (one == UNCHECKED and dup == UNCHECKED
          and two == "GENERIC_CONSTRUCTION" and refused)
    record("V65_generic_needs_two_independent_sources", ok,
           {"one": one, "same_source_twice": dup, "two": two,
            "sourceless_refused": refused})


# ---------------------------------------------------------------- V66
def v66():
    """用途は許可証ではない。由来状態はひとつも変わらない。"""
    r = rights()
    before = {(x["part"], x["aspect"]): x["state"]
              for x in r.report(PARTS)["rows"]}
    r.set_intent("commercial")
    mid = {(x["part"], x["aspect"]): x["state"]
           for x in r.report(PARTS)["rows"]}
    r.set_intent("personal")
    after = {(x["part"], x["aspect"]): x["state"]
             for x in r.report(PARTS)["rows"]}
    ok = (before == mid == after)
    record("V66_intent_is_not_a_permit", ok,
           {"states_unchanged": before == mid == after,
            "changed": [k for k in before if before[k] != mid[k]]})


# ---------------------------------------------------------------- V67
def v67():
    """設計をいくら書き換えても観測は変わらない。"""
    led = observed()
    snapshot = json.dumps(led.spec(), ensure_ascii=False, sort_keys=True)
    d = Design()
    d.keep(led, "collar", "shape", by="担当:西小田")
    d.change(led, "sleeve", "construction", "一枚袖", by="担当:西小田")
    d.create("detail", "trim", "パイピング無し", by="担当:西小田")
    after = json.dumps(led.spec(), ensure_ascii=False, sort_keys=True)
    ok = (snapshot == after)
    record("V67_design_never_rewrites_the_observation", ok,
           {"observation_unchanged": snapshot == after,
            "design_rows": len(d.entries)})


# ---------------------------------------------------------------- V68
def v68():
    """値を変えても派生元は消えない。"""
    led = observed()
    d = Design()
    d.change(led, "collar", "shape", "ショールカラー", by="担当:西小田")
    h = d.history("collar", "shape")[0]
    ok = (h["derived_from"] == "collar/shape"
          and h["original_value"] == "ノッチドラペル"
          and h["value"] == "ショールカラー")
    record("V68_changing_a_value_keeps_where_it_came_from", ok, {"row": h})


# ---------------------------------------------------------------- V69
def v69():
    """商用は宿題を増やすことはあっても減らさない。"""
    r = rights()
    conf = [{"part": "collar", "aspect": "shape"}]
    personal = r.report(PARTS, confirmed=conf)["worklist"]
    r.set_intent("commercial")
    commercial = r.report(PARTS, confirmed=conf)["worklist"]

    def keys(ws):
        return {(w["part"], w["aspect"], w["why"]) for w in ws}

    ok = keys(personal) <= keys(commercial)
    record("V69_commercial_only_adds_homework", ok,
           {"personal": len(personal), "commercial": len(commercial),
            "superset": keys(personal) <= keys(commercial)})


# ---------------------------------------------------------------- V70
def v70():
    """由来の証拠を入れる順は、由来状態を動かさない。"""
    def build(order):
        r = RightsLedger()
        for f in order:
            f(r)
        return {(x["part"], x["aspect"]): x["state"]
                for x in r.report(PARTS)["rows"]}

    acts = [
        lambda r: r.specific("collar", "shape", "映画X 資料 p.12"),
        lambda r: r.generic("collar", "shape", "教本 p.88"),
        lambda r: r.generic("collar", "shape", "カタログ #441"),
        lambda r: r.no_match("body", "silhouette", "カタログ3社分"),
    ]
    a = build(acts)
    b = build(list(reversed(acts)))
    c = build([acts[2], acts[0], acts[3], acts[1]])
    ok = (a == b == c and a[("collar", "shape")] == CONTESTED_ORIGIN)
    record("V70_order_of_evidence_does_not_move_the_state", ok,
           {"same": a == b == c,
            "collar_shape": a[("collar", "shape")]})


if __name__ == "__main__":
    for f in (v63, v64, v65, v66, v67, v68, v69, v70):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_provenance.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
