# -*- coding: utf-8 -*-
"""CLI 移設の確認測定 — PREREG7_CLI_PARITY.md の V31〜V34。

新機能ではなく入口の移設なので、測るのは「同じ扉に届いているか」と
「設定を壊さないか」。数値は実行結果のみ。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RESULTS = {"prereg": "experiments/guard/PREREG7_CLI_PARITY.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def vera(store, *argv, cwd=None, timeout=900):
    r = subprocess.run(
        [sys.executable, "-m", "verantyx.cli", "--store", str(store), *argv],
        capture_output=True, text=True, cwd=str(cwd or ROOT), timeout=timeout)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"_stdout": r.stdout[-400:],
                              "_stderr": r.stderr[-400:]}


# ---------------------------------------------------------------- V31
def v31():
    tmp = Path(tempfile.mkdtemp())
    docs = tmp / "docs"
    docs.mkdir()
    (docs / "規程.txt").write_text(
        "第3条 出張費は事前承認が必要である。\n"
        "第4条 交際費は上限を月5万円とする。\n", encoding="utf-8")
    (docs / "tech.md").write_text(
        "The implementation language is TypeScript.\n", encoding="utf-8")
    store = tmp / "store.json"

    rc_load, loaded = vera(store, "documents", str(docs))
    rc_a, ans = vera(store, "ask", "交際費")
    rc_b, absent = vera(store, "ask", "ゾルタクスゼイアン")

    ok = (rc_load == 0 and loaded.get("loaded") == 2
          and ans.get("verdict") == "ANSWER" and ans.get("core") == "交際費"
          and str(absent.get("verdict", "")).startswith("UNKNOWN"))
    record("V31_documents_go_in_from_the_cli", ok,
           {"loaded": loaded.get("loaded"), "sources": loaded.get("sources"),
            "in_stock": [ans.get("verdict"), ans.get("core"),
                         ans.get("text")],
            "out_of_stock": absent.get("verdict"),
            "exit_codes": [rc_load, rc_a, rc_b]})


# ---------------------------------------------------------------- V32
def v32():
    tmp = Path(tempfile.mkdtemp())
    rc, out = vera(tmp / "store.json", "domain", "list")
    ok = rc == 0 and isinstance(out, dict) and "_stdout" not in out
    record("V32_domains_reachable_from_the_cli", ok,
           {"exit_code": rc, "keys": sorted(out.keys())[:6]})


# ---------------------------------------------------------------- V33
def v33():
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "store.json"
    rc_list, listed = vera(store, "tool", "list")
    from verantyx.mcp_server import build

    mcp = build(str(store))
    mcp_doors = len(mcp._tool_manager.list_tools())

    rc_missing, missing = vera(store, "tool", "call", "no_such_door")

    ok = (rc_list == 0 and listed.get("doors") == mcp_doors
          and mcp_doors >= 120
          and missing.get("verdict") == "UNKNOWN_NO_SUCH_DOOR"
          and rc_missing != 0)
    record("V33_every_door_is_reachable_and_absence_is_typed", ok,
           {"cli_doors": listed.get("doors"), "mcp_doors": mcp_doors,
            "missing_verdict": missing.get("verdict"),
            "missing_exit_code": rc_missing})


# ---------------------------------------------------------------- V34
def v34():
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "store.json"
    cfg = tmp / ".mcp.json"
    cfg.write_text(json.dumps(
        {"mcpServers": {"other-server": {"command": "keep-me"}}}),
        encoding="utf-8")

    rc_show, shown = vera(store, "mcp-config", cwd=tmp)
    untouched = json.loads(cfg.read_text(encoding="utf-8"))

    rc_ins, installed = vera(store, "mcp-config", "--install", cwd=tmp)
    after = json.loads(cfg.read_text(encoding="utf-8"))

    ok = (rc_show == 0 and "vera-memory" in shown["snippet"]["mcpServers"]
          and untouched == {"mcpServers": {"other-server":
                                           {"command": "keep-me"}}}
          and rc_ins == 0
          and after["mcpServers"]["other-server"] == {"command": "keep-me"}
          and "vera-memory" in after["mcpServers"]
          and "mcp" in after["mcpServers"]["vera-memory"]["args"])
    record("V34_config_is_shown_by_default_and_merges_on_install", ok,
           {"default_wrote_nothing": untouched == {
               "mcpServers": {"other-server": {"command": "keep-me"}}},
            "after_install_servers": sorted(after["mcpServers"]),
            "installed_to": (installed.get("installed") or {}).get(
                "claude-code", "")[-24:]})


if __name__ == "__main__":
    for f in (v31, v32, v33, v34):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm7.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
