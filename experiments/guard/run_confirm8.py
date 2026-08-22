# -*- coding: utf-8 -*-
"""配線と窓の確認測定 — PREREG8_WIRING_AND_WINDOW.md の V35〜V38。

①静かに壊れないこと(配線の検査)と、②欠けを1つの窓に出すこと。
どちらも新しい機構ではない — 既にあるものを繋いで見えるようにした
だけなので、測るのは「壊れたら言うか」と「何も変えないか」。
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.doctor import full_doctor, installation_check  # noqa: E402

RESULTS = {"prereg": "experiments/guard/PREREG8_WIRING_AND_WINDOW.md",
           "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _write(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------- V35
# 壊した配線を名指しする。台本が無い / 設定が実在しない command を指す。

def v35():
    tmp = Path(tempfile.mkdtemp())
    # フックは設定されているが台本が消えている
    broken_hooks = _write(tmp / "settings.json", {"hooks": {"Stop": [
        {"hooks": [{"type": "command",
                    "command": f"python3 {tmp}/gone/hook_stop.py"}]}]}})
    # MCP は設定されているがバイナリが実在しない
    broken_mcp = _write(tmp / ".mcp.json", {"mcpServers": {"vera-memory": {
        "command": str(tmp / "no-such-binary"),
        "args": ["--store", str(tmp / "store.json"), "mcp"]}}})

    out = installation_check(settings_files=[str(broken_hooks)],
                             mcp_files=[str(broken_mcp)])
    states = {r["what"]: r["state"] for r in out["rows"]}

    # 健全な配線(台本もバイナリも実在)では PARTIAL を出さない — 狼少年の禁止
    good_hooks = _write(tmp / "good_settings.json", {"hooks": {"Stop": [
        {"hooks": [{"type": "command",
                    "command": f"python3 {ROOT}/tools/guard/hook_stop.py"}]}]}})
    good_mcp = _write(tmp / "good.mcp.json", {"mcpServers": {"vera-memory": {
        "command": sys.executable,
        "args": ["--store", str(tmp / "store.json"), "mcp"]}}})
    healthy = installation_check(settings_files=[str(good_hooks)],
                                 mcp_files=[str(good_mcp)])
    healthy_states = {r["what"]: r["state"] for r in healthy["rows"]
                      if r["what"] in ("hook", "mcp_server")}

    # 凍結バイナリの中では repo が無いのが正常。そこで「ソースが無い」と
    # 言うのは誤警報(停止条件)。実物があるなら実物で確かめる。
    vendor = Path.home() / "Projects/Verantyx/cli/VerantyxIDE/Vendor/vera-memory"
    frozen_alarm = None
    if vendor.exists():
        r = subprocess.run([str(vendor), "doctor"], capture_output=True,
                           text=True, timeout=900)
        try:
            d = json.loads(r.stdout)
            frozen_alarm = [p for p in d["wiring"]["problems"]
                            if p.startswith("source")]
        except Exception as e:                 # noqa: BLE001
            frozen_alarm = [f"unreadable: {e!r}"]

    ok = (out["verdict"] == "PARTIAL"
          and states.get("hook") == "MISSING_SCRIPT"
          and states.get("mcp_server") == "MISSING_COMMAND"
          and set(healthy_states.values()) == {"OK"}
          and not frozen_alarm)
    record("V35_broken_wiring_is_named", ok,
           {"broken": [out["verdict"], out["problems"]],
            "healthy_rows": healthy_states,
            "healthy_verdict_not_false_alarm":
                set(healthy_states.values()) == {"OK"},
            "frozen_binary_false_alarm": frozen_alarm})


# ---------------------------------------------------------------- V36
# 未導入は故障ではない。NOT_WIRED であって BROKEN ではない。

def v36():
    tmp = Path(tempfile.mkdtemp())
    fresh = installation_check(settings_files=[str(tmp / "none.json")],
                               mcp_files=[str(tmp / "none2.json")])
    whole = full_doctor()
    ok = (fresh["verdict"] == "NOT_WIRED"
          and fresh["configured_places"] == 0
          and whole["verdict"] in ("OK", "DEGRADED")   # 保証は生きている
          and not whole["failed"])
    record("V36_not_installed_is_not_broken", ok,
           {"fresh_machine": fresh["verdict"],
            "whole_doctor": whole["verdict"],
            "guarantees_failed": whole["failed"]})


# ---------------------------------------------------------------- V37
# 窓が実際の保留を数え、閉じ方を挙げる。

def v37():
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "store.json"

    def door(name, payload=None):
        r = subprocess.run(
            [sys.executable, "-m", "verantyx.cli", "--store", str(store),
             "tool", "call", name]
            + (["--json", json.dumps(payload, ensure_ascii=False)]
               if payload else []),
            capture_output=True, text=True, cwd=str(ROOT), timeout=900)
        try:
            return json.loads(r.stdout)
        except Exception:
            return {"_stdout": r.stdout[-300:], "_stderr": r.stderr[-300:]}

    before = door("pending_decisions")
    door("propose_covenant", {"name": "no-emoji", "forbids": "絵文字",
                              "quote": "絵文字を使わないで"})
    door("propose_web_evidence", {"text": "出張費は事前承認が必要である。",
                                  "source": "https://example.invalid/rule"})
    after = door("pending_decisions")

    def waiting(out, kind):
        return next((q["waiting"] for q in out.get("queues", [])
                     if q["kind"] == kind), None)

    ok = (before.get("waiting_total") == 0
          and waiting(after, "covenant_candidates") == 1
          and waiting(after, "ai_facts") == 1
          and after["waiting_total"] >= 2
          and all(q.get("close_with") for q in after["queues"])
          and "autonomous" in after["acquire_modes"])
    record("V37_one_window_counts_real_waiting_items", ok,
           {"before_total": before.get("waiting_total"),
            "after_total": after.get("waiting_total"),
            "covenant_candidates": waiting(after, "covenant_candidates"),
            "web_evidence_landed_in": "ai_facts",
            "modes": list(after.get("acquire_modes", {}))})


# ---------------------------------------------------------------- V38
# 窓は何も変えない(読むだけ)。

def v38():
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "store.json"

    def door(name, payload=None):
        subprocess.run(
            [sys.executable, "-m", "verantyx.cli", "--store", str(store),
             "tool", "call", name]
            + (["--json", json.dumps(payload, ensure_ascii=False)]
               if payload else []),
            capture_output=True, text=True, cwd=str(ROOT), timeout=900)

    door("propose_covenant", {"name": "c", "forbids": "TODO", "quote": "q"})
    sidecar = store.with_name(store.stem + ".covenants.json")
    files = sorted(p for p in tmp.iterdir() if p.is_file())
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in files}
    door("pending_decisions")
    door("pending_decisions")
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(q for q in tmp.iterdir() if q.is_file())}

    ok = before == after and sidecar.name in before
    record("V38_the_window_changes_nothing", ok,
           {"files_watched": sorted(before), "identical": before == after})


if __name__ == "__main__":
    for f in (v35, v36, v37, v38):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm8.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
