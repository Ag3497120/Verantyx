# -*- coding: utf-8 -*-
"""単体 Vera の確認測定 — PREREG6_STANDALONE.md の V28〜V30。

番人と同じ規律: 通るだけの自己検査は自己申告なので、**壊した装置で
BROKEN を返せること**まで測る。数値は実行結果のみ。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.doctor import full_doctor, store_self_check  # noqa: E402

RESULTS = {"prereg": "experiments/guard/PREREG6_STANDALONE.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- V28
# 治具(企業文書2件+技術方針1件)で S1〜S4 が成立する。
# 在庫外で ANSWER が1件でも出たらその場で不合格。

def v28():
    out = store_self_check()
    by = {p["probe"]: p for p in out["guarantees"]}
    absence = by["S2_absence_is_refused"]["detail"]
    fabricated = [q for q, v in absence.items()
                  if isinstance(v, list) and v[0] == "ANSWER"]
    ok = (out["verdict"] == "OK" and not fabricated
          and by["S3_ingest_order_invariant"]["detail"]["permutations"] == 6)
    record("V28_standalone_guarantees_hold", ok,
           {"verdict": out["verdict"],
            "in_stock": by["S1_in_stock_answers"]["detail"],
            "absence": absence,
            "fabricated_answers": fabricated,
            "strangers": by["S4_answer_uses_only_stored_words"]["detail"]
            ["strangers"]})


# ---------------------------------------------------------------- V29
# 壊した装置で BROKEN を返し、壊れた保証を名指しできる。

def v29():
    def mute_ask(store, q):
        """何にも答えない装置(S1が壊れた状態)。"""
        return {"verdict": "UNKNOWN_NO_EVIDENCE", "core": None, "text": ""}

    def fabricating_ask(store, q):
        """在庫外にも答えてしまう装置(S2が壊れた状態)。
        埋め込み検索の RAG が構造上こうなる — 近傍は常に何かを返す。"""
        return {"verdict": "ANSWER", "core": q, "text": f"{q} は 重要 である",
                "tokens": [q, "重要", "である"]}

    def order_dependent_ask(store, q):
        """取り込み順に依存する装置(S3が壊れた状態)。"""
        first = next(iter(store.crosses), None)
        return {"verdict": "ANSWER", "core": first, "text": str(first),
                "tokens": [first] if first else []}

    mute = store_self_check(ask=mute_ask)
    fab = store_self_check(ask=fabricating_ask)
    ordered = store_self_check(ask=order_dependent_ask)

    ok = (mute["verdict"] == "BROKEN"
          and "S1_in_stock_answers" in mute["failed"]
          and fab["verdict"] == "BROKEN"
          and "S2_absence_is_refused" in fab["failed"]
          and "S4_answer_uses_only_stored_words" in fab["failed"]
          and ordered["verdict"] == "BROKEN"
          and "S3_ingest_order_invariant" in ordered["failed"]
          # 壊していない保証まで巻き添えにしていないか(名指しの精度)
          and "S3_ingest_order_invariant" not in fab["failed"])
    record("V29_doctor_reports_broken_when_broken", ok,
           {"mute": [mute["verdict"], mute["failed"]],
            "fabricating": [fab["verdict"], fab["failed"]],
            "order_dependent": [ordered["verdict"], ordered["failed"]]})


# ---------------------------------------------------------------- V30
# 二つの顔を1回で検査し、片方が壊れていればもう片方が緑でも BROKEN。
# 要約が証拠を隠さない、の適用。

def v30():
    import verantyx.covenant as cov

    healthy = full_doctor()

    real = cov.self_check
    try:
        cov.self_check = lambda *a, **k: {
            "verdict": "BROKEN", "guarantees": [],
            "failed": ["G1_registered_covenant_blocks"]}
        half = full_doctor()
    finally:
        cov.self_check = real

    r = subprocess.run([sys.executable, "-m", "verantyx.cli", "doctor"],
                       capture_output=True, text=True, cwd=str(ROOT),
                       timeout=600)
    cli = json.loads(r.stdout)

    # 2026-08-22 の再張り: 配線検査(PREREG8)が入ったので、健全な
    # エンジンでも凍結が古い機械では DEGRADED になる。**保証が生きて
    # いるか**は failed が空かどうかで見る — verdict の OK/DEGRADED は
    # 環境の話であって、この測定が主張していることではない。
    ok = (healthy["verdict"] in ("OK", "DEGRADED")
          and not healthy["failed"]
          and half["verdict"] == "BROKEN"
          and half["standalone"]["verdict"] == "OK"   # 片方は緑のまま
          and "G1_registered_covenant_blocks" in half["failed"]
          and cli["verdict"] == "OK" and r.returncode == 0
          and len(cli["guard"]["guarantees"]) == 4
          and len(cli["standalone"]["guarantees"]) == 4)
    record("V30_one_command_covers_both_faces", ok,
           {"healthy": healthy["verdict"],
            "one_face_broken": [half["verdict"],
                                half["standalone"]["verdict"],
                                half["failed"]],
            "cli": [cli["verdict"], r.returncode,
                    len(cli["guard"]["guarantees"]),
                    len(cli["standalone"]["guarantees"])]})


if __name__ == "__main__":
    for f in (v28, v29, v30):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm6.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
