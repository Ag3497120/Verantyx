# -*- coding: utf-8 -*-
"""台帳の有界化と IDE の到達 — PREREG9_LEDGER_AND_REACH.md の V39〜V44。

台帳は**消さずに書庫へ移す**。IDE は MCP 経由なので、CLI にしか無い
機能へは橋で届かせる(扉を写さない)。数値は実行結果のみ。
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import Covenant, Register  # noqa: E402

RESULTS = {"prereg": "experiments/guard/PREREG9_LEDGER_AND_REACH.md",
           "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _loaded(n_adopted=5, n_candidates=995, turns=250):
    reg = Register()
    for i in range(n_adopted + n_candidates):
        c = Covenant(name=f"c{i}", quote=f"語{i}を使わないで",
                     forbids=[f"語{i}"])
        if i >= n_adopted:
            c.status = "candidate"
        reg.add(c)
    for _ in range(turns):
        reg.check("対応しました。語3 を含む文です。")
    return reg


# ---------------------------------------------------------------- V39
# 履歴を間引いても**数は消えない**(checked/kept の総数が保存される)。

def v39():
    reg = _loaded(n_adopted=3, n_candidates=27, turns=300)
    before_rows = sum(len(v) for v in reg.history.values())
    before_kept = sum(sum(1 for k in v if k) for v in reg.history.values())

    tmp = Path(tempfile.mkdtemp())
    out = reg.prune(path=tmp / "s.covenants.json", max_history=50,
                    max_live=1000)

    after_rows = sum(len(v) for v in reg.history.values())
    tot_checked = sum(t["checked"] for t in reg.history_totals.values())
    tot_kept = sum(t["kept"] for t in reg.history_totals.values())
    kept_now = sum(sum(1 for k in v if k) for v in reg.history.values())

    ok = (out["history_trimmed"] > 0
          and after_rows < before_rows
          and tot_checked + after_rows == before_rows
          and tot_kept + kept_now == before_kept)
    record("V39_trimming_history_keeps_the_counts", ok,
           {"rows_before": before_rows, "rows_after": after_rows,
            "folded_into_totals": tot_checked,
            "kept_before": before_kept, "kept_now_plus_totals":
                tot_kept + kept_now})


# ---------------------------------------------------------------- V40
# 生きた台帳が上限に収まり、**移したものが書庫で全部見つかる**。

def v40():
    reg = _loaded()
    names_before = {c.name for c in reg.covenants}
    tmp = Path(tempfile.mkdtemp())
    ledger = tmp / "s.covenants.json"
    out = reg.prune(path=ledger, max_live=300)

    arch = ledger.with_suffix(".archive.jsonl")
    archived = [json.loads(line) for line in
                arch.read_text(encoding="utf-8").splitlines() if line.strip()]
    names_after = {c.name for c in reg.covenants}
    names_arch = {r["name"] for r in archived}

    ok = (len(reg.covenants) == 300
          and out["archived"] == 700
          and names_after | names_arch == names_before   # 何も消えていない
          and not (names_after & names_arch)             # 二重にもならない
          and all(r.get("archived_reason") for r in archived))
    record("V40_nothing_vanishes_it_moves_to_the_archive", ok,
           {"live": len(reg.covenants), "archived": len(archived),
            "union_equals_original": names_after | names_arch == names_before,
            "reasons": sorted({r["archived_reason"] for r in archived})})


# ---------------------------------------------------------------- V41
# 人が採用した約束は1本も移らない。

def v41():
    reg = _loaded(n_adopted=40, n_candidates=960)
    adopted_before = {c.name for c in reg.covenants
                      if c.status == "adopted" and not c.retired}
    tmp = Path(tempfile.mkdtemp())
    reg.prune(path=tmp / "s.covenants.json", max_live=100)
    adopted_after = {c.name for c in reg.covenants
                     if c.status == "adopted" and not c.retired}
    ok = adopted_before == adopted_after and len(adopted_after) == 40
    record("V41_adopted_covenants_are_never_moved", ok,
           {"adopted_before": len(adopted_before),
            "adopted_after": len(adopted_after),
            "live_total": len(reg.covenants)})


# ---------------------------------------------------------------- V42
# 間引き後、照合と保存が上限内(各5ms)。

def v42():
    reg = _loaded()
    tmp = Path(tempfile.mkdtemp())
    ledger = tmp / "s.covenants.json"

    def timed():
        t0 = time.time()
        for _ in range(30):
            reg.check("対応しました。")
        chk = (time.time() - t0) / 30 * 1000
        t0 = time.time()
        for _ in range(5):
            reg.save(ledger)
        sav = (time.time() - t0) / 5 * 1000
        return round(chk, 3), round(sav, 3)

    before = timed()
    reg.prune(path=ledger, max_live=300, max_history=200)
    after = timed()
    ok = after[0] <= 5.0 and after[1] <= 5.0
    record("V42_after_pruning_it_stays_inside_the_bar", ok,
           {"check_ms": {"before": before[0], "after": after[0]},
            "save_ms": {"before": before[1], "after": after[1]},
            "bar_ms": 5.0, "ledger_kb": round(ledger.stat().st_size / 1024, 1)})


# ---------------------------------------------------------------- V43
# IDE(MCP)から CLI 限定の機能へ届く。許可表の外は型つきで断る。

def v43():
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "store.json"

    def call(door, payload):
        r = subprocess.run(
            [sys.executable, "-m", "verantyx.cli", "--store", str(store),
             "tool", "call", door, "--json",
             json.dumps(payload, ensure_ascii=False)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=1800)
        try:
            return json.loads(r.stdout)
        except Exception:
            return {"_stdout": r.stdout[-300:]}

    simp = call("vera_cli", {"command": "simplify",
                             "args_json": json.dumps(["(x+0)*1"])})
    doc = call("vera_doctor", {})
    # 破壊的・公開系は橋に載せない
    forbidden = [call("vera_cli", {"command": c})["verdict"]
                 for c in ("forget", "push-store", "setup")]

    ok = (simp.get("verdict") == "ANSWER"
          and simp["result"]["term"] == "x"
          and doc.get("verdict") in ("OK", "DEGRADED")
          and len(doc.get("guard", {}).get("guarantees", [])) == 4
          and len(doc.get("standalone", {}).get("guarantees", [])) == 4
          and forbidden == ["UNKNOWN_NOT_ALLOWED"] * 3)
    record("V43_the_ide_reaches_cli_only_features", ok,
           {"simplify_via_bridge": simp.get("result", {}).get("term"),
            "doctor_via_door": doc.get("verdict"),
            "refused_dangerous": forbidden})


# ---------------------------------------------------------------- V44
# 橋は許可表の外を実行しない — 名前を捏ねても通らない。

def v44():
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "store.json"
    marker = tmp / "should_not_exist.txt"

    def call(payload):
        r = subprocess.run(
            [sys.executable, "-m", "verantyx.cli", "--store", str(store),
             "tool", "call", "vera_cli", "--json",
             json.dumps(payload, ensure_ascii=False)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=900)
        try:
            return json.loads(r.stdout)
        except Exception:
            return {"_stdout": r.stdout[-200:]}

    tries = [call({"command": c}) for c in
             ("forget", "ask; touch " + str(marker), "../../bin/sh",
              "PUSH-STORE", "doctor ")]
    verdicts = [t.get("verdict") for t in tries]
    ok = (verdicts == ["UNKNOWN_NOT_ALLOWED"] * 5
          and not marker.exists())
    record("V44_the_bridge_runs_nothing_outside_the_table", ok,
           {"verdicts": verdicts, "side_effect_file": marker.exists()})


if __name__ == "__main__":
    for f in (v39, v40, v41, v42, v43, v44):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm9.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
