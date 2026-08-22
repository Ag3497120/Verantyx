# -*- coding: utf-8 -*-
"""番人フックの共通部 — guard サブコマンド直呼び(橋なし)。

実地試験の限界5(橋の起動中 15〜45秒 fail-open)への答え: 常駐を待たず、
呼び出しごとに `vera-memory guard <op>` を同期実行する。covenants.json
しか読まないので秒台で返る。CLI が見つからない/落ちた場合だけ素通し
(Vera の都合で作業は止めない、は維持 — ただし窓は「常駐の起動中」から
「バイナリ不在」だけに縮む)。
"""
import json
import os
import shutil
import subprocess
import sys

#: 凍結バイナリの探索順(環境変数 → Vendor → PATH)
_CANDIDATES = [
    os.environ.get("VERA_MEMORY_BIN", ""),
    os.path.expanduser(
        "~/Projects/Verantyx/cli/VerantyxIDE/Vendor/vera-memory"),
    shutil.which("vera-memory") or "",
]


#: リポジトリがあるならソース直呼びが最速(実測 0.04s/回。
#: onefile 凍結バイナリは毎回展開するため数秒かかる — 実測 3.7s)。
_REPO = os.path.expanduser("~/Projects/Verantyx-Vera-alpha")


def _cmd_head():
    override = os.environ.get("VERA_GUARD_CMD", "")
    if override:
        return override.split()
    if os.path.isdir(os.path.join(_REPO, "verantyx")):
        for py in ("python3.11", "python3"):
            if shutil.which(py):
                return [py, "-m", "verantyx.cli"]
    for c in _CANDIDATES:
        if c and os.path.exists(c):
            return [c]
    return None


def guard(op, payload, store=None, timeout=20):
    """1回の guard 呼び出し。失敗は None(素通し側の判断は呼び出し元)。"""
    head = _cmd_head()
    if head is None:
        return None
    cmd = list(head)
    if store:
        cmd += ["--store", store]
    cmd += ["guard", op]
    try:
        env = dict(os.environ)
        if cmd[0] != _CANDIDATES[1]:      # module invocation
            env["PYTHONPATH"] = _REPO + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(cmd, input=json.dumps(payload, ensure_ascii=False),
                           capture_output=True, text=True,
                           timeout=timeout, env=env)
        return json.loads(r.stdout) if r.stdout.strip() else None
    except Exception:
        return None


def read_hook_input():
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def store_path():
    return os.environ.get(
        "VERA_GUARD_STORE",
        os.path.expanduser("~/.vera_guard/vera_store.json"))
