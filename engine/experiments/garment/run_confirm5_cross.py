# -*- coding: utf-8 -*-
"""立体十字への配置の確認測定 — PREREG5_CROSS.md の VC1〜VC6。

測るのは「十字に載せたことが台帳の言い直しでないこと」と
「像が本体を汚さないこと」。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, PARTS                      # noqa: E402
from verantyx.garment_cross import (build, core_of,             # noqa: E402
                                    report, split_aspects)
from verantyx.garment_rights import RightsLedger                # noqa: E402

RESULTS = {"prereg": "experiments/garment/PREREG5_CROSS.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fixture():
    led = Ledger(title="映画X のコート")
    led.observe("collar", "shape", "ノッチドラペル", "cut 0:12:05")
    led.observe("collar", "shape", "ノッチドラペル", "cut 0:12:11")
    led.observe("sleeve", "length", "肘下12cm", "cut 0:12:07")
    led.infer("sleeve", "construction", "二枚袖", "袖山の皺から")
    led.propose("fabric", "kind", "ウール混", "視覚モデルv2")
    # 観測が割れる例
    led.observe("detail", "button", "2つ", "cut 0:12:06")
    led.observe("detail", "button", "3つ", "cut 0:12:17")
    # 由来が割れる例(同じ側面に一般と実例)
    r = RightsLedger()
    r.generic("collar", "shape", "工業パターン教本 p.88")
    r.generic("collar", "shape", "既製品カタログ #441")
    r.specific("collar", "shape", "映画X 公式衣装資料 p.12")
    return led, r


# ---------------------------------------------------------------- VC1
def vc1():
    """台帳と十字が、同じ側面を割れていると言う。

    観測の割れと由来の割れは**別の事**なので、別々に比べる。混ぜて
    比べると、由来が割れている側面を「観測が割れている」と読むことに
    なり、縫製師に渡す指示書の意味が変わる。
    """
    from verantyx.garment_rights import CONTESTED_ORIGIN

    led, r = fixture()
    store = build(led, r)
    obs = split_aspects(led, store)

    # 由来の割れ: 由来台帳が CONTESTED_ORIGIN と言う側面と、十字が
    # origin_* キーで拾う側面が一致するか。
    from_rights = {(p, a) for p, aspects in PARTS.items() for a in aspects
                   if r.state(p, a)["state"] == CONTESTED_ORIGIN}
    from_cross = {tuple(x)
                  for x in split_aspects(led, store, origins=True)["cross"]}

    ok = (obs["agree"]
          and ("detail", "button") in {tuple(x) for x in obs["ledger"]}
          and from_rights == from_cross
          and ("collar", "shape") in from_rights)
    record("VC1_ledger_and_cross_agree_on_what_is_split", ok,
           {"observations_agree": obs["agree"], "observed_split": obs["ledger"],
            "origin_split_rights": sorted(from_rights),
            "origin_split_cross": sorted(from_cross),
            "origins_agree": from_rights == from_cross})


# ---------------------------------------------------------------- VC2
def vc2():
    """**配置は情報を増やさない。** 入れる順で十字は変わらない。"""
    led, r = fixture()

    def shape(entries_order):
        clone = Ledger(title=led.title)
        clone.entries = [led.entries[i] for i in entries_order]
        st = build(clone, r)
        facets = {c: dict(sorted(f.items()))
                  for c, f in sorted(st.crosses.items())}
        contra = sorted(tuple(x) for x in split_aspects(clone, st)["cross"])
        return json.dumps(facets, ensure_ascii=False, sort_keys=True), contra

    n = len(led.entries)
    a = shape(list(range(n)))
    b = shape(list(reversed(range(n))))
    c = shape([3, 0, 6, 1, 5, 2, 4][:n])
    ok = (a == b == c)
    record("VC2_placement_order_does_not_change_the_cross", ok,
           {"same": a == b == c, "contradictions": a[1]})


# ---------------------------------------------------------------- VC3
def vc3():
    """一般は kind+ 側、実例は kind- 側。同じ側面に両方立てば割れている。"""
    led, r = fixture()
    rep = report(led, r)
    gen = rep["arms"]["kind+ (一般)"]
    spec = rep["arms"]["kind- (実例)"]
    both_on_collar = (any(g["part"] == "collar" for g in gen)
                      and any(s_["part"] == "collar" for s_ in spec))
    # 一般は「独立2本で買う」規則があるので、十字が数えた本数が
    # 由来台帳の判定と同じ数になっていること。
    collar_generic = next(g for g in gen if g["part"] == "collar")
    ok = (len(gen) == 1 and len(spec) == 1 and both_on_collar
          and collar_generic["sources"] == 2)
    record("VC3_general_and_instance_sit_on_opposite_arms", ok,
           {"kind+": gen, "kind-": spec, "collar_has_both": both_on_collar,
            "generic_sources_counted": collar_generic["sources"]})


# ---------------------------------------------------------------- VC4
def vc4():
    """提案は確定の質量を増やさない。"""
    led, _ = fixture()
    before = build(led).mass(core_of("fabric"))
    for i in range(5):
        led.propose("fabric", "kind", f"候補{i}", "視覚モデルv2")
    after = build(led).mass(core_of("fabric"))
    store = build(led)
    proposed_core = store.has(core_of("fabric") + "#proposed")
    ok = (before == after and proposed_core)
    record("VC4_proposals_do_not_add_mass_to_the_confirmed_side", ok,
           {"mass_before": before, "mass_after": after,
            "proposals_kept_on_their_own_core": proposed_core})


# ---------------------------------------------------------------- VC5
def vc5():
    """**十字は台帳の像であって台帳ではない。** 作り直しても本体は不変。"""
    led, r = fixture()
    snap = json.dumps([e.__dict__ for e in led.entries],
                      ensure_ascii=False, sort_keys=True)
    rsnap = json.dumps([o.__dict__ for o in r.origins],
                       ensure_ascii=False, sort_keys=True)
    for _ in range(3):
        build(led, r)
        report(led, r)
        split_aspects(led, build(led, r))
    after = json.dumps([e.__dict__ for e in led.entries],
                       ensure_ascii=False, sort_keys=True)
    rafter = json.dumps([o.__dict__ for o in r.origins],
                        ensure_ascii=False, sort_keys=True)
    ok = (snap == after and rsnap == rafter)
    record("VC5_the_cross_never_writes_back_to_the_ledger", ok,
           {"ledger_unchanged": snap == after,
            "rights_unchanged": rsnap == rafter})


# ---------------------------------------------------------------- VC6
def vc6():
    """空の台帳から矛盾は出ない。出るなら検出器が形から作っている。"""
    led = Ledger()
    store = build(led)
    a = split_aspects(led, store)
    ok = (not a["ledger"] and not a["cross"] and store.n_cores() == 0)
    record("VC6_an_empty_ledger_yields_no_contradiction", ok,
           {"ledger": a["ledger"], "cross": a["cross"],
            "cores": store.n_cores()})


if __name__ == "__main__":
    for f in (vc1, vc2, vc3, vc4, vc5, vc6):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_cross.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
