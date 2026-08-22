# -*- coding: utf-8 -*-
"""番人 第三段の確認測定 — PREREG3.md の V14〜V18。

RESULTS2 が名指した残り3つの限界:
  ⑤ 実行のふりと実走の区別(呼ばれた道具 + 終了状態)
  ⑥ shadow 実績からの昇格(推薦と棄権のみ、採用は門のまま)
  ⑦ 焼き込みの陳腐化(stat だけの検知と、店を1回だけ読む焼き直し)

数値は全て実行結果から。予想は書かない。
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import (Covenant, Register,  # noqa: E402
                               bake_inferred, invoked_programs)
from verantyx.cross_store import CrossStore  # noqa: E402
from verantyx.document_ingest import Document, ingest_documents  # noqa: E402

RESULTS = {"prereg": "experiments/guard/PREREG3.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _reg(requires=("pytest",)):
    r = Register()
    r.add(Covenant(name="t", quote="必ずpytestを実行して",
                   requires=list(requires)))
    return r


# ---------------------------------------------------------------- V14
# ふりと実走: echo pytest は MENTIONED 止まり。実走形は INVOKED。
# 停止条件: 素の pytest やスクリプト実行を取りこぼしたら語り分けを棄却。

def v14():
    fake = _reg()
    fake.witness("Bash", detail="echo pytest")
    f_audit = fake.audit()
    f_row = f_audit["rows"][0]

    real_forms = ["python3 -m pytest -q", "pytest -q", "uv run pytest",
                  "cd /tmp && python3.11 -m pytest tests/"]
    real_states = []
    for cmd in real_forms:
        r = _reg()
        r.witness("Bash", detail=cmd, ok=True)
        real_states.append(r.audit()["rows"][0]["match"])

    # 別名の道具でも同じ(en の約束 + npx 包み)
    lint = Register()
    lint.add(Covenant(name="l", quote="Always run eslint",
                      requires=["eslint"]))
    lint.witness("Bash", detail="npx eslint src/ --fix", ok=True)
    lint_state = lint.audit()["rows"][0]["match"]

    # 書き置きに道具名が出てくるだけ(ファイル書き込み)は証人でない
    note = _reg()
    note.witness("Write", detail="/tmp/notes.md")
    note.witness("Bash", detail="echo 'run pytest later' > notes.txt")
    note_state = note.audit()["verdict"]

    ok = (f_audit["verdict"] == "REQUIRED_UNWITNESSED"
          and f_row["match"] == "MENTIONED"
          and f_row["mentioned_only"]           # 黙って捨てない
          and real_states == ["INVOKED"] * 4
          and lint_state == "INVOKED"
          and note_state == "REQUIRED_UNWITNESSED")
    record("V14_pretend_vs_real_run", ok,
           {"echo_pytest": [f_audit["verdict"], f_row["match"]],
            "real_forms": dict(zip(real_forms, real_states)),
            "npx_eslint": lint_state, "note_only": note_state,
            "programs_sample": invoked_programs("git add . && npm run lint")})


# ---------------------------------------------------------------- V15
# 終了状態の三値。不在と否定を混ぜない。

def v15():
    passed = _reg()
    passed.witness("Bash", detail="pytest -q", ok=True)
    unknown = _reg()
    unknown.witness("Bash", detail="pytest -q")            # ok 未記録
    failed = _reg()
    failed.witness("Bash", detail="pytest -q", ok=False)
    # 同じターンに通った回と落ちた回 → 落ちた回を報せる(証拠を隠さない)
    both = _reg()
    both.witness("Bash", detail="pytest -q", ok=True)
    both.witness("Bash", detail="pytest tests/unit", ok=False)
    both_rev = _reg()
    both_rev.witness("Bash", detail="pytest tests/unit", ok=False)
    both_rev.witness("Bash", detail="pytest -q", ok=True)

    got = [passed.audit()["verdict"], unknown.audit()["verdict"],
           failed.audit()["verdict"], both.audit()["verdict"],
           both_rev.audit()["verdict"]]
    ok = got == ["REQUIRED_WITNESSED", "REQUIRED_WITNESSED_UNVERIFIED",
                 "REQUIRED_FAILED", "REQUIRED_FAILED", "REQUIRED_FAILED"]
    record("V15_exit_status_three_valued", ok,
           {"ok_true": got[0], "ok_unknown": got[1], "ok_false": got[2],
            "mixed_same_turn": got[3:5]})


# ---------------------------------------------------------------- V16
# 昇格は推薦と棄権だけ。事前登録の帯(8回・1発火・50%)で4つに分かれ、
# 推薦しても status は candidate のまま。

def v16():
    reg = Register()
    reg.propose(Covenant(name="good", quote="!は控えめに", forbids=["!"]))
    # 過検出役は**本文に実際に現れる**語でないと過検出にならない。
    # 最初「の」を選んで一度も発火せず NEVER_FIRED になった(治具の誤り、
    # 実測して気づいた)。「ました」は10文中7文にある。
    reg.propose(Covenant(name="loud", quote="ましたを禁止",
                         forbids=["ました"]))
    reg.propose(Covenant(name="silent", quote="ゾルタクスを禁止",
                         forbids=["ゾルタクス"]))

    texts = ["対応しました", "できました", "終わりました", "確認しました",
             "直しました!", "了解です", "進めます", "完了です", "見ました",
             "書きました"]
    for t in texts:
        reg.check(t)
    # young2 だけ標本を薄くする(後から提案 = 履歴が短い)
    reg.propose(Covenant(name="young2", quote="FIXME禁止",
                         forbids=["FIXME"]))
    for t in texts[:3]:
        reg.check(t)

    rev = reg.promotion_review()
    by = {r["covenant"]: r["verdict"] for r in rev["rows"]}
    statuses = {c.name: c.status for c in reg.covenants}
    ok = (by.get("good") == "PROMOTABLE"
          and by.get("loud") == "REFUSED_OVERFIRING"
          and by.get("silent") == "REFUSED_NEVER_FIRED"
          and by.get("young2") == "UNKNOWN_TOO_FEW_CHECKS"
          and not any("fire_rate" in r for r in rev["rows"]
                      if r["verdict"] == "UNKNOWN_TOO_FEW_CHECKS")
          and set(statuses.values()) == {"candidate"})
    record("V16_promotion_is_a_recommendation", ok,
           {"verdicts": by, "promotable": rev["promotable"],
            "criteria": rev["criteria"],
            "all_still_candidates": set(statuses.values()) == {"candidate"}})


# ---------------------------------------------------------------- V17
# 陳腐化は stat だけ(100ms以内)。焼き直しは店を1回読み、差分を報せる。
# dry_run は保存しない。停止条件: stale が遅い/check が店を読む。

def v17():
    tmp = Path("/tmp/guard_v17_store.json")
    store = CrossStore()
    ingest_documents(store, [Document(source="刑法", text=(
        "甲条は拘禁刑を科する。甲条は規定である。"
        "乙条は罰金を科する。乙条は規定である。"
        "丙条は拘禁刑を科する。丙条は罰金を科する。"
        "丁条は拘禁刑を科する。丁条は罰金を科する。"))])
    store.save(tmp)

    reg = Register()
    c = Covenant(name="k", quote="拘禁刑の話はしないで", forbids=["拘禁刑"])
    reg.add(c)
    bake_inferred(c, store, store_name=tmp.name, store_path=tmp)
    baked_first = list(c.inferred_forbids)

    t0 = time.time()
    fresh = reg.stale(tmp)
    fresh_s = time.time() - t0

    # 店が育つ: 拘禁刑と席を共にする語をもう一つ足す
    time.sleep(0.01)
    ingest_documents(store, [Document(source="刑法2", text=(
        "戊条は拘禁刑を科する。戊条は科料を科する。"
        "己条は拘禁刑を科する。己条は科料を科する。"
        "庚条は拘禁刑を科する。庚条は科料を科する。"))])
    store.save(tmp)

    t0 = time.time()
    st = reg.stale(tmp)
    stale_s = time.time() - t0

    dry = reg.rebake(store, store_path=tmp, dry_run=True)
    after_dry = list(c.inferred_forbids)
    wet = reg.rebake(store, store_path=tmp)
    after_wet = list(c.inferred_forbids)
    fresh_again = reg.stale(tmp)["verdict"]

    ok = (fresh["verdict"] == "FRESH" and st["verdict"] == "STALE"
          and stale_s <= 0.1 and fresh_s <= 0.1
          and after_dry == baked_first            # dry_run は変えない
          and "科料" in after_wet                  # 店の成長が届いた
          and dry["dry_run"] is True and wet["dry_run"] is False
          and fresh_again == "FRESH")
    record("V17_staleness_by_stat_and_rebake", ok,
           {"baked_first": baked_first, "after_dry_run": after_dry,
            "after_rebake": after_wet,
            "added": wet["rows"][0]["added"],
            "stale_s": round(stale_s, 5), "fresh_s": round(fresh_s, 5),
            "verdicts": [fresh["verdict"], st["verdict"], fresh_again]})


# ---------------------------------------------------------------- V18
# 順序不変: 証人の記録順・約束の登録順を入れ替えても audit の判定と行、
# 昇格の行が同一。

def v18():
    import itertools
    wits = [("Bash", "pytest -q", True), ("Bash", "git diff", None),
            ("Bash", "npx eslint src", False)]
    covs = [("t", ["pytest"]), ("l", ["eslint"]), ("g", ["git"])]
    base = None
    same = True
    for wperm in itertools.permutations(wits):
        for cperm in itertools.permutations(covs):
            reg = Register()
            for n, rq in cperm:
                reg.add(Covenant(name=n, quote=n, requires=rq))
            reg.boundary()
            for t, d, ok in wperm:
                reg.witness(t, detail=d, ok=ok)
            a = reg.audit()
            key = (a["verdict"],
                   tuple((r["covenant"], r["requires"], r["state"],
                          r["match"]) for r in a["rows"]))
            if base is None:
                base = key
            elif key != base:
                same = False
    record("V18_order_invariance", same and base[0] == "REQUIRED_FAILED",
           {"permutations": 36, "identical": same, "verdict": base[0],
            "rows": [list(r) for r in base[1]]})


if __name__ == "__main__":
    for f in (v14, v15, v16, v17, v18):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm3.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
