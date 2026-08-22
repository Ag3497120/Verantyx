# -*- coding: utf-8 -*-
"""能力の索引の確認測定 — PREREG10_INDEX.md の V45〜V48。

索引が実物とずれないこと、実在するものを見つけること、**無いものに
何も返さないこと**、そして一覧ではなく導出であること。
数値は実行結果のみ。
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.index import build, search  # noqa: E402

RESULTS = {"prereg": "experiments/guard/PREREG10_INDEX.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- V45
# 索引の数が実物と一致する(独立に数えて突き合わせる)。

def v45():
    idx = build()
    src = (ROOT / "verantyx" / "mcp_server.py").read_text(encoding="utf-8")
    doors_real = len(re.findall(r"@(?:mcp|server)\.tool", src))
    forks_src = (ROOT / "verantyx" / "cross_geometry_forks.py").read_text(
        encoding="utf-8")
    forks_real = len(re.findall(r"^def \w+_fork\(", forks_src, re.M))
    preregs_real = len([p for p in ROOT.rglob("PREREG*.md")
                        if ".git" not in p.parts])
    modules_real = len(list((ROOT / "verantyx").glob("*.py")))

    c = idx["counts"]
    ok = (c["door"] == doors_real and c["fork"] == forks_real
          and c["prereg"] == preregs_real and c["module"] == modules_real)
    record("V45_the_index_matches_the_real_thing", ok,
           {"door": [c["door"], doors_real], "fork": [c["fork"], forks_real],
            "prereg": [c["prereg"], preregs_real],
            "module": [c["module"], modules_real]})


# ---------------------------------------------------------------- V46
# 実在する資産が、名指しで上位に出る。

def v46():
    want = {
        "約束 破棄": "retire_covenant",
        "文書 投入": "ingest_documents",
        "配置": "placement",
        "証人": "witness",
        "欠け 保留": "pending",
    }
    got = {}
    ok = True
    for q, expect in want.items():
        out = search(q, limit=5)
        names = [h["name"] for h in out.get("hits", [])]
        got[q] = names[:3]
        if not any(expect in n for n in names):
            ok = False
    record("V46_real_assets_come_back_named", ok, got)


# ---------------------------------------------------------------- V47
# 無いものには何も返さない。試す語は**この測定だけが持つ**
# (事前登録に書くと、索引が自分の仕様書に当たって汚れる)。

def v47():
    # 試験語は grep で不在を確かめてから選ぶ。最初に選んだ
    # 「ゾルタクスゼイアン」は自分が RESULTS2 に書いていたので当たった —
    # 索引は正しく、治具が間違っていた(この種の自己汚染は2度目)。
    absent = ["潮汐発電", "オルニチン", "cassoulet", "peregrine falcon"]
    verdicts = {q: search(q)["verdict"] for q in absent}
    ok = all(v == "UNKNOWN_NOT_FOUND" for v in verdicts.values())
    record("V47_absence_is_answered_not_guessed", ok, verdicts)


# ---------------------------------------------------------------- V48
# 一覧ではなく導出であること: 別の根で数が変わる。

def v48():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "verantyx").mkdir()
    (tmp / "verantyx" / "mcp_server.py").write_text(
        'from x import mcp\n\n\n@mcp.tool()\ndef only_door() -> str:\n'
        '    """the only door here"""\n    return ""\n', encoding="utf-8")
    (tmp / "verantyx" / "cross_geometry_forks.py").write_text(
        'def a_fork() -> dict:\n    """the only fork"""\n    return {}\n',
        encoding="utf-8")
    (tmp / "verantyx" / "cli.py").write_text("x = 1\n", encoding="utf-8")

    small = build(tmp)
    real = build()
    ok = (small["counts"].get("door") == 1
          and small["counts"].get("fork") == 1
          and real["counts"]["door"] > 100
          and small["total"] < real["total"])
    record("V48_the_index_is_derived_not_listed", ok,
           {"synthetic_root": small["counts"], "real_doors":
            real["counts"]["door"]})


if __name__ == "__main__":
    for f in (v45, v46, v47, v48):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm10.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
