# -*- coding: utf-8 -*-
"""不在の型と、状態の出典 — PREREG2_ABSENCE.md の V49〜V52。

報告の面(`deep_report`)で「持っていない」と「持っているが確定が無い」を
分け、構造化して置いた状態の出所も読めるようにした。既存の判定は
一つも変えていないこと(V50)を同時に測る。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.cross_store import CrossStore  # noqa: E402
from verantyx.document_ingest import (Document, deep_report,  # noqa: E402
                                      ingest_documents)

RESULTS = {"prereg": "experiments/state_reconciliation/PREREG2_ABSENCE.md",
           "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fixture():
    """状態を置く。**極つきの面と裸の語の両方**を置くのは、散文の
    取り込み(`ingest_documents`)がそうしているから — 片方だけ置くと、
    争いは見えるのに合意が見えない報告になる(最初にそれで落とした)。
    エンジンの側は一貫していて、私の置き方が不完全だった。"""
    st = CrossStore(track_provenance=True)

    def state(core, aspect, value, source):
        st.add(core, [f"{aspect}:{value}", value], source=source)

    state("県道1号", "通行可能", "通行可能", "県道路課")
    state("県道1号", "通行可能", "通行止", "市災害対策本部")
    state("避難所2", "開設", "開設", "市災害対策本部")
    st.add("倉庫3", ["職員"], source="現地パトロール")   # 側面を持たない
    return st


# ---------------------------------------------------------------- V49
def v49():
    st = fixture()
    got = {c: deep_report(st, c) for c in
           ("県道1号", "避難所2", "倉庫3", "浄水場99")}
    conf = {c: r["confidence"] for c, r in got.items()}
    held = {c: r["held"] for c, r in got.items()}
    ok = (conf["県道1号"] == "contested"
          and conf["避難所2"] == "supported"
          and conf["浄水場99"] == "unknown_not_held"
          and held["浄水場99"] is False
          and held["県道1号"] is True
          # 「見たが言うことが無い」と「そもそも無い」が別の値
          and conf["倉庫3"] != conf["浄水場99"])
    record("V49_absence_is_a_different_answer", ok,
           {"confidence": conf, "held": held})


# ---------------------------------------------------------------- V50
def v50():
    """在る核の判定は不変 — 文章として取り込んだ古い経路で確かめる。"""
    st = CrossStore(track_provenance=True)
    ingest_documents(st, [
        Document(source="市役所", text="避難所は開設している。"),
        Document(source="県", text="避難所は閉鎖している。")])
    r = deep_report(st, "避難所")
    sides = (r["disputed"][0]["sides"] if r["disputed"] else [])
    named = [s["sources"] for s in sides]
    ok = (r["confidence"] == "contested" and r["held"] is True
          and all(n for n in named))
    record("V50_prose_path_unchanged", ok,
           {"confidence": r["confidence"], "held": r["held"],
            "sources": named})


# ---------------------------------------------------------------- V51
def v51():
    """構造化して置いた状態でも、どちらを誰が言ったかが報告に出る。"""
    st = fixture()
    r = deep_report(st, "県道1号")
    sides = r["disputed"][0]["sides"] if r["disputed"] else []
    by = {s["claim"]: s["sources"] for s in sides}
    ok = (by.get("通行可能") == ["県道路課"]
          and by.get("通行止") == ["市災害対策本部"])
    record("V51_structured_state_keeps_its_sources", ok, {"sides": by})


# ---------------------------------------------------------------- V52
def v52():
    """長い文を出所名として出さない(報告が読めなくなるため)。"""
    st = CrossStore(track_provenance=True)
    long_label = ("市の担当者が現地で確認したところ通行できる状態であると"
                  "説明したが後刻訂正される可能性がある。")
    st.add("県道9号", ["通行可能:通行可能"], source=long_label)
    st.add("県道9号", ["通行可能:通行止"], source="県")
    r = deep_report(st, "県道9号")
    sides = r["disputed"][0]["sides"] if r["disputed"] else []
    by = {s["claim"]: s["sources"] for s in sides}
    ok = by.get("通行可能") == [] and by.get("通行止") == ["県"]
    record("V52_a_sentence_is_not_a_source_label", ok, {"sides": by})


if __name__ == "__main__":
    for f in (v49, v50, v51, v52):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results2.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
