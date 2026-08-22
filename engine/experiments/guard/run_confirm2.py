# -*- coding: utf-8 -*-
"""番人 第二段の確認測定 — PREREG2.md の V6〜V10。

④ required は証人で見る / ① 隔離席(LLM手渡し) / ③ 焼き込み推論。
数値は全て実行結果から。予想は書かない。
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import (Covenant, Register,  # noqa: E402
                               bake_inferred)
from verantyx.cross_store import CrossStore  # noqa: E402
from verantyx.document_ingest import Document, ingest_documents  # noqa: E402

RESULTS = {"prereg": "experiments/guard/PREREG2.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _cov(name, quote="", forbids=(), requires=(), turn=-1):
    return Covenant(name=name, quote=quote, forbids=list(forbids),
                    requires=list(requires), said_at_turn=turn)


# ---------------------------------------------------------------- V6
# 証人: 実行記録があれば WITNESSED、なければ UNWITNESSED。
# 境界より前の証人は数えない(ターンを跨いだ「やった」の混入は停止条件)。

def v6():
    reg = Register()
    reg.add(_cov("must-test", quote="必ずpytestを実行して",
                 requires=["pytest"]))
    a0 = reg.audit()["verdict"]
    # PREREG3 の再張り: 終了状態つきで初めて WITNESSED(無ければ
    # UNVERIFIED — 不在と否定を混ぜない)。
    reg.witness("Bash", detail="python3 -m pytest tests/ -q", ok=True)
    a1 = reg.audit()["verdict"]
    reg.boundary()
    a2 = reg.audit()["verdict"]
    # 境界後に別の tool だけ動いた場合も UNWITNESSED のまま
    reg.witness("Bash", detail="git status", ok=True)
    a3 = reg.audit()["verdict"]
    ok = (a0 == "REQUIRED_UNWITNESSED" and a1 == "REQUIRED_WITNESSED"
          and a2 == "REQUIRED_UNWITNESSED" and a3 == "REQUIRED_UNWITNESSED")
    record("V6_witness_and_boundary", ok,
           {"no_witness": a0, "witnessed": a1, "after_boundary": a2,
            "unrelated_tool": a3})


# ---------------------------------------------------------------- V7
# 隔離席: candidate の違反は shadow に出るだけで verdict は KEPT。
# adopt 後は同じ文で BROKEN。retire で棄却できる。

def v7():
    reg = Register()
    reg.propose(_cov("no-exclaim", quote="ビックリマークは控えめに",
                     forbids=["!"]))
    text = "できました!すごい!"
    shadowed = reg.check(text)
    reg.adopt("no-exclaim")
    enforced = reg.check(text)
    reg.retire("no-exclaim", quote="やっぱりいい", turn=9)
    released = reg.check(text)
    ok = (shadowed["verdict"] == "KEPT"
          and len(shadowed.get("shadow_violations", [])) == 1
          and enforced["verdict"] == "BROKEN"
          and released["verdict"] == "KEPT")
    record("V7_quarantine_shadow_then_gate", ok,
           {"candidate": [shadowed["verdict"],
                          len(shadowed.get("shadow_violations", []))],
            "adopted": enforced["verdict"],
            "retired": released["verdict"]})


# ---------------------------------------------------------------- V8
# 拒否: requires の無い台帳の audit は NO_REQUIREMENTS(証人ゼロを違反と
# 呼ばない)。空の候補は propose されない(CLI 経由)。

def v8():
    reg = Register()
    reg.add(_cov("no-emoji", quote="絵文字を使わないで", forbids=["絵文字"]))
    a = reg.audit()["verdict"]

    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "verantyx.cli", "--store",
         "/tmp/g2_v8.json", "guard", "propose"],
        input='{"name":"empty","quote":"なんとなく"}',
        capture_output=True, text=True, cwd=str(ROOT), timeout=60)
    out = json.loads(r.stdout)
    ok = (a == "NO_REQUIREMENTS"
          and out["verdict"] == "UNKNOWN_EMPTY_CANDIDATE")
    record("V8_refusals", ok,
           {"audit_no_requires": a, "empty_propose": out["verdict"]})


# ---------------------------------------------------------------- V9
# 順序: 証人の記録順・約束の登録順を入れ替えても audit/check の判定不変。

def v9():
    import itertools
    wits = [("Bash", "python3 -m pytest -q"), ("Bash", "git diff"),
            ("Write", "src/main.py")]
    covs = [("t", [], ["pytest"]), ("no-todo", ["TODO"], []),
            ("lint", [], ["ruff"])]
    base = None
    same = True
    for wperm in itertools.permutations(wits):
        for cperm in itertools.permutations(covs):
            reg = Register()
            for n, f, rq in cperm:
                reg.add(_cov(n, quote=n, forbids=f, requires=rq))
            reg.boundary()
            for t, d in wperm:
                reg.witness(t, detail=d)
            aud = reg.audit()
            chk = reg.check("TODO: fix")
            key = (aud["verdict"],
                   tuple(sorted((r["covenant"], r["requires"],
                                 r["witnessed"]) for r in aud["rows"])),
                   chk["verdict"],
                   tuple(sorted(v["covenant"] for v in chk["violations"])))
            if base is None:
                base = key
            elif key != base:
                same = False
    ok = same and base[0] == "REQUIRED_UNWITNESSED"
    record("V9_order_invariance", ok,
           {"permutations": 36, "identical": same, "audit": base[0]})


# ---------------------------------------------------------------- V10
# 焼き込み推論: 店に姉妹語がある語 → inferred_forbids に焼かれ、姉妹語の
# 使用が inferred 型で報じられる。店に無い語 → 空。check の実時間は
# 素の字面と同桁(≤2倍)。

def v10():
    store = CrossStore()
    body = ("甲条は拘禁刑を科する。甲条は規定である。"
            "乙条は罰金を科する。乙条は規定である。"
            "丙条は拘禁刑を科する。丙条は罰金を科する。"
            "丁条は拘禁刑を科する。丁条は罰金を科する。")
    ingest_documents(store, [Document(source="刑法", text=body)])

    c = _cov("no-kinkin", quote="拘禁刑の話はしないで", forbids=["拘禁刑"])
    baked = bake_inferred(c, store, store_name="fixture")
    reg = Register()
    reg.add(c)
    hit = reg.check("この刑は罰金である。")
    inferred_used = [u for v in hit["violations"]
                     for u in v.get("inferred_forbidden_used", [])]
    plain = reg.check("この条文は規定について述べる。")

    c2 = _cov("no-unknown", quote="ゾルタクスゼイアンは使わないで",
              forbids=["ゾルタクスゼイアン"])
    baked2 = bake_inferred(c2, store, store_name="fixture")

    # 実時間: 焼き込み済み check vs 字面のみ check(各200回)
    reg_lit = Register()
    reg_lit.add(_cov("lit", quote="q", forbids=["拘禁刑"]))
    t0 = time.time()
    for _ in range(200):
        reg_lit.check("この刑は罰金である。")
    lit_s = time.time() - t0
    t0 = time.time()
    for _ in range(200):
        reg.check("この刑は罰金である。")
    baked_s = time.time() - t0
    ratio = baked_s / max(lit_s, 1e-9)

    ok = ("罰金" in baked["inferred_forbids"]
          and hit["verdict"] == "BROKEN" and "罰金" in inferred_used
          and plain["verdict"] == "KEPT"            # 停止条件: 平文誤検知
          and baked2["inferred_forbids"] == []
          and ratio <= 2.0)
    record("V10_baked_inference", ok,
           {"baked": baked["inferred_forbids"],
            "inferred_hit": inferred_used,
            "plain": plain["verdict"],
            "unknown_term_baked": baked2["inferred_forbids"],
            "check_s_200": {"literal": round(lit_s, 4),
                            "baked": round(baked_s, 4),
                            "ratio": round(ratio, 2)}})


if __name__ == "__main__":
    Path("/tmp/g2_v8.covenants.json").unlink(missing_ok=True)
    for f in (v6, v7, v8, v9, v10):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm2.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
