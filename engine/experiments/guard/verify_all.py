# -*- coding: utf-8 -*-
"""番人の証拠を1コマンドで全部回す — 提出物の再現性のため(PREREG5)。

fork(構造の性質)と、事前登録つき測定5本を全部走らせて1行で答える。
落ちたものは名指しする(合計だけ出す要約は証拠を隠す)。
終了コード: 全部緑なら 0、一つでも落ちたら 1。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

CONFIRMATIONS = ["run_confirm.py", "run_confirm2.py", "run_confirm3.py",
                 "run_confirm_lang.py", "run_confirm4.py",
                 "run_confirm5.py", "run_confirm6.py", "run_confirm7.py", "run_confirm8.py", "run_confirm9.py", "run_confirm10.py"]


def main() -> int:
    from verantyx.cross_geometry_forks import all_cross_geometry_forks

    rows = all_cross_geometry_forks()
    fork_bad = [r["fork"] for r in rows if not r["pass"]]
    fork_line = f"forks {sum(r['pass'] for r in rows)}/{len(rows)}"

    total = passed = 0
    failures = []
    per_file = {}
    for name in CONFIRMATIONS:
        r = subprocess.run([sys.executable, str(HERE / name)],
                           capture_output=True, text=True, cwd=str(ROOT),
                           timeout=1800)
        tail = (r.stdout or "").strip().splitlines()
        m = re.search(r"(\d+)/(\d+) passed", tail[-1] if tail else "")
        if not m:
            failures.append(f"{name}: 実行できなかった")
            per_file[name] = "ERROR"
            continue
        p, t = int(m.group(1)), int(m.group(2))
        passed += p
        total += t
        per_file[name] = f"{p}/{t}"
        for line in tail:
            if line.startswith("[FAIL]"):
                failures.append(f"{name}: {line[7:80]}")

    ok = not fork_bad and not failures and passed == total
    print(f"{fork_line} / 測定 {passed}/{total} — "
          f"{'全て緑' if ok else '落ちたものあり'}")
    for name, v in per_file.items():
        print(f"    {name:<22} {v}")
    for f in fork_bad:
        print(f"    [FORK FAIL] {f}")
    for f in failures:
        print(f"    [FAIL] {f}")
    (HERE / "verify_all_result.json").write_text(json.dumps(
        {"forks": fork_line, "measurements": f"{passed}/{total}",
         "per_file": per_file, "fork_failures": fork_bad,
         "failures": failures, "all_green": ok},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
