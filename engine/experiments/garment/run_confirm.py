# -*- coding: utf-8 -*-
"""服飾台帳の確認測定 — PREREG.md の V53〜V57。

裁断は取り返しがつかないので、測るのは「推測が確定に混ざらないこと」。
数値は実行結果のみ。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import (CONTESTED, INFERRED, OBSERVED,  # noqa: E402
                              PROPOSED, UNKNOWN, Ledger)

RESULTS = {"prereg": "experiments/garment/PREREG.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fixture() -> Ledger:
    led = Ledger(title="映画◯◯ 00:12:03-00:12:19 のコート")
    led.observe("collar", "shape", "ノッチドラペル", "cut 0:12:05")
    led.observe("collar", "shape", "ノッチドラペル", "cut 0:12:11")
    led.observe("sleeve", "length", "肘下12cm相当", "cut 0:12:07")
    led.infer("sleeve", "construction", "二枚袖", "袖山の皺の入り方から")
    led.propose("fabric", "kind", "ウール混", "視覚モデルv2",
                note="モデルの自己申告 0.71 — 事実の欄には入れない")
    led.propose("back", "structure", "背中心切替あり", "画像検索の類似品",
                note="https://example.invalid/item/123")
    led.observe("pocket", "existence", "無し", "cut 0:12:14")
    # 観測が割れる例(別カットで別の値)
    led.observe("detail", "button", "2つ", "cut 0:12:06")
    led.observe("detail", "button", "3つ", "cut 0:12:17")
    return led


# ---------------------------------------------------------------- V53
def v53():
    """提案は確定に混ざらない。採用して初めて入る。"""
    led = fixture()
    before = led.state("fabric", "kind")
    spec_before = led.spec()
    in_confirmed_before = [s for s in spec_before["confirmed"]
                           if s["part"] == "fabric"]
    led.adopt("fabric", "kind", "ウール混", by="担当:西小田")
    after = led.state("fabric", "kind")
    spec_after = led.spec()
    in_confirmed_after = [s for s in spec_after["confirmed"]
                          if s["part"] == "fabric"]
    ok = (before["state"] == PROPOSED and not in_confirmed_before
          and after["state"] == OBSERVED and len(in_confirmed_after) == 1
          and after["adopted_by"] == "担当:西小田"
          # 採用しても出所は消えない
          and after["sources"] == ["視覚モデルv2"])
    record("V53_a_proposal_enters_only_by_adoption", ok,
           {"before": before["state"], "after": after["state"],
            "adopted_by": after.get("adopted_by"),
            "source_kept": after.get("sources")})


# ---------------------------------------------------------------- V54
def v54():
    """観測が割れたら片方を勝たせない。"""
    led = fixture()
    s = led.state("detail", "button")
    sides = {x["value"]: x["sources"] for x in s.get("sides", [])}
    spec = led.spec()
    in_confirmed = [x for x in spec["confirmed"]
                    if x["part"] == "detail" and x["aspect"] == "button"]
    ok = (s["state"] == CONTESTED and set(sides) == {"2つ", "3つ"}
          and all(sides.values()) and not in_confirmed
          and len(spec["contested"]) == 1)
    record("V54_split_observations_do_not_pick_a_winner", ok,
           {"state": s["state"], "sides": sides,
            "in_confirmed": len(in_confirmed)})


# ---------------------------------------------------------------- V55
def v55():
    """「無し」と「見えていない」を別の値で返す。"""
    led = fixture()
    none_observed = led.state("pocket", "existence")     # 観測: 無し
    never_seen = led.state("lining", "existence")        # 一度も映っていない
    ok = (none_observed["state"] == OBSERVED
          and none_observed["value"] == "無し"
          and never_seen["state"] == UNKNOWN
          and "how_to_close" in never_seen
          and none_observed["state"] != never_seen["state"])
    record("V55_absent_is_not_the_same_as_unobserved", ok,
           {"observed_none": [none_observed["state"],
                              none_observed.get("value")],
            "never_observed": [never_seen["state"],
                               never_seen.get("how_to_close")]})


# ---------------------------------------------------------------- V56
def v56():
    """指示書の三節が混ざらない — 確定欄に推論も提案も1件も出ない。"""
    led = fixture()
    spec = led.spec()
    confirmed_states = {s["state"] for s in spec["confirmed"]}
    inferred_states = {s["state"] for s in spec["inferred"]}
    leaked = [s for s in spec["confirmed"]
              if s["state"] != OBSERVED or s.get("proposals") is None]
    # 推論は inferred 節にだけ
    sleeve = [s for s in spec["inferred"]
              if s["part"] == "sleeve" and s["aspect"] == "construction"]
    ok = (confirmed_states == {OBSERVED} and inferred_states <= {INFERRED}
          and len(sleeve) == 1 and not any(
              s["state"] in (INFERRED, PROPOSED) for s in spec["confirmed"]))
    record("V56_the_three_sections_never_blend", ok,
           {"counts": spec["counts"], "confirmed_states":
            sorted(confirmed_states), "inference_in_its_own_section":
            len(sleeve) == 1})


# ---------------------------------------------------------------- V57
def v57():
    """未確定の一覧が、そのまま作業指示になっている。"""
    led = fixture()
    work = led.worklist()
    ok = (len(work) > 0
          and all(w["how_to_close"] for w in work)
          and any(w["part"] == "back" and w["aspect"] == "closure"
                  for w in work))
    record("V57_every_open_item_says_how_to_close", ok,
           {"open_items": len(work), "all_have_closers":
            all(w["how_to_close"] for w in work),
            "example": work[0] if work else None})


# ---------------------------------------------------------------- V58
def v58():
    """提案は何も閉じない。確定は増えず、未確定も減らない。"""
    led = fixture()
    before = led.spec()["counts"]
    led.propose("collar", "material", "メルトンウール", "類似品検索03")
    after = led.spec()["counts"]
    ok = (after["confirmed"] == before["confirmed"]
          and after["open"] == before["open"])
    record("V58_a_proposal_closes_nothing", ok,
           {"before": before, "after": after})


# ---------------------------------------------------------------- V59
def v59():
    """open の内訳は open をちょうど割る。提案を引かない。"""
    led = fixture()
    led.propose("collar", "material", "メルトンウール", "類似品検索03")
    c = led.spec()["counts"]
    ok = (c["proposed"] + c["unobserved"] == c["open"] and c["proposed"] >= 1)
    record("V59_open_splits_into_proposed_and_unobserved", ok, {"counts": c})


# ---------------------------------------------------------------- V60
def v60():
    """名前の無い採用は通らない。台帳は一切変わらない。"""
    led = fixture()
    led.propose("collar", "material", "メルトンウール", "類似品検索03")
    before = json.dumps(led.spec(), ensure_ascii=False, sort_keys=True)
    refused = []
    for name in ("", "   ", "\t"):
        try:
            led.adopt("collar", "material", "メルトンウール", name)
            refused.append(False)
        except Exception:
            refused.append(True)
    after = json.dumps(led.spec(), ensure_ascii=False, sort_keys=True)
    ok = (before == after)
    record("V60_adoption_without_a_name_changes_nothing", ok,
           {"ledger_unchanged": before == after, "raised": refused})


# ---------------------------------------------------------------- V61
def v61():
    """採用しても出所は消えない。誰の言い分だったかが残る。"""
    led = fixture()
    led.propose("collar", "material", "メルトンウール", "類似品検索03")
    led.adopt("collar", "material", "メルトンウール", "担当:西小田")
    row = next(r for r in led.spec()["confirmed"]
               if r["part"] == "collar" and r["aspect"] == "material")
    ok = ("類似品検索03" in row.get("sources", [])
          and row.get("adopted_by") == "担当:西小田")
    record("V61_adoption_keeps_the_origin", ok, {"row": row})


# ---------------------------------------------------------------- V62
def v62():
    """提案を置く順は結論を動かさない。"""
    a = fixture()
    a.propose("collar", "material", "メルトンウール", "類似品検索03")
    a.propose("lining", "kind", "キュプラ", "類似品検索07")
    b = fixture()
    b.propose("lining", "kind", "キュプラ", "類似品検索07")
    b.propose("collar", "material", "メルトンウール", "類似品検索03")

    def shape(led):
        sp = led.spec()
        return (sorted((r["part"], r["aspect"], r.get("value", ""))
                       for r in sp["confirmed"]),
                sorted((r["part"], r["aspect"]) for r in sp["contested"]),
                sp["counts"])

    ok = shape(a) == shape(b)
    record("V62_proposal_order_does_not_move_the_verdict", ok,
           {"same": ok, "counts": shape(a)[2]})


if __name__ == "__main__":
    for f in (v53, v54, v55, v56, v57, v58, v59, v60, v61, v62):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
