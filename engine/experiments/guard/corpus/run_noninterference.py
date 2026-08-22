# -*- coding: utf-8 -*-
"""C4 非干渉 — 新しい店を作る前と後で、既存の緑が緑のままか。

`python3.11 run_noninterference.py before|after` で
`noninterference_<phase>.json` を書く。

**experiments/guard/ 直下は触らない**という掟があるが、run_confirm*.py は
`Path(__file__).with_name(...)` で自分の隣に結果 json を書く。そこで
実行前に4つの結果 json を退避し、実行後に**バイト単位で書き戻す**
(mtime ごと)。退避・復元の一致もこの json に記録する。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / "experiments" / "guard"
HERE = Path(__file__).resolve().parent
SCRATCH = HERE / "_nonint_backup"

CONFIRMS = [
    ("run_confirm.py", "results_confirm.json", 7),
    ("run_confirm2.py", "results_confirm2.json", 5),
    ("run_confirm3.py", "results_confirm3.json", 5),
    ("run_confirm_lang.py", "results_confirm_lang.json", 3),
]

_SUMMARY = re.compile(r"(\d+)/(\d+) passed")


def fingerprint(p: Path) -> dict:
    st = os.stat(p)
    with open(p, "rb") as fh:
        head = fh.read(65536)
    return {"size": st.st_size, "mtime": st.st_mtime,
            "head64k_sha256": hashlib.sha256(head).hexdigest()}


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(phase: str) -> int:
    out: dict = {"phase": phase, "prereg": "PREREG_CORPUS.md C4"}

    out["vera_store_fingerprint"] = fingerprint(ROOT / "vera_store.json")

    # --- fork suite -------------------------------------------------
    t0 = time.time()
    from verantyx.cross_geometry_forks import all_cross_geometry_forks
    forks = all_cross_geometry_forks()
    passed = sum(1 for f in forks if f.get("pass"))
    out["forks"] = {"passed": passed, "total": len(forks),
                    "seconds": round(time.time() - t0, 2),
                    "failed": [f.get("fork") for f in forks
                               if not f.get("pass")],
                    "names": [f.get("fork") for f in forks]}

    # --- confirm scripts (退避 → 実行 → 復元) -------------------------
    SCRATCH.mkdir(exist_ok=True)
    saved = {}
    for _script, res, _n in CONFIRMS:
        src = GUARD / res
        if src.exists():
            dst = SCRATCH / res
            shutil.copy2(src, dst)
            saved[res] = file_sha(src)

    rows = []
    for script, res, expect in CONFIRMS:
        t0 = time.time()
        r = subprocess.run([sys.executable, str(GUARD / script)],
                           capture_output=True, text=True, cwd=str(ROOT))
        m = None
        for line in r.stdout.splitlines():
            hit = _SUMMARY.search(line)
            if hit:
                m = hit
        got = f"{m.group(1)}/{m.group(2)}" if m else "NO_SUMMARY"
        checks = [ln[:400] for ln in r.stdout.splitlines()
                  if ln.startswith("[PASS]") or ln.startswith("[FAIL]")]
        rows.append({"script": script, "expected": f"{expect}/{expect}",
                     "got": got, "ok": got == f"{expect}/{expect}",
                     "returncode": r.returncode,
                     "seconds": round(time.time() - t0, 2),
                     "failed_checks": [ln for ln in checks
                                       if ln.startswith("[FAIL]")],
                     "checks": checks,
                     "stderr_tail": r.stderr.strip()[-300:]})
    out["confirms"] = rows

    restored = {}
    for _script, res, _n in CONFIRMS:
        src = GUARD / res
        bak = SCRATCH / res
        if res in saved and bak.exists():
            shutil.copy2(bak, src)
            restored[res] = {"restored_sha_matches_backup":
                             file_sha(src) == saved[res]}
    out["guard_dir_restored"] = restored

    out["vera_store_fingerprint_after"] = fingerprint(ROOT / "vera_store.json")
    out["vera_store_unchanged"] = (
        out["vera_store_fingerprint"] == out["vera_store_fingerprint_after"])

    out["all_green"] = (
        out["forks"]["passed"] == out["forks"]["total"]
        and all(r["ok"] for r in rows)
        and out["vera_store_unchanged"]
        and all(v["restored_sha_matches_backup"] for v in restored.values()))

    dest = HERE / f"noninterference_{phase}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items()
                      if k != "vera_store_fingerprint_after"},
                     ensure_ascii=False, indent=1))
    return 0 if out["all_green"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "before"))
