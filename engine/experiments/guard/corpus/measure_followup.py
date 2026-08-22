# -*- coding: utf-8 -*-
"""追測 — C2 の閾値の算術と、C3 が5つ落ちた理由の診断。

事前登録の判定は measure_corpus.py で確定済み。ここは「では実際どこに
線が引けるのか」「なぜ姉妹語が出なかったのか」を数字で言うための追測で、
新しい合否は作らない。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import Covenant, bake_inferred  # noqa: E402
from verantyx.cross_store import CrossStore  # noqa: E402

HERE = Path(__file__).resolve().parent
NEW_STORE = HERE / "guard_store.json"

ORD = ["the", "is", "are", "new", "use", "used", "using", "one", "time",
       "part", "name", "make", "get", "set", "run", "file", "code", "all",
       "can", "will", "場合", "必要", "使用", "以下", "内容", "方法"]
CON = ["typescript", "javascript", "pytest", "unittest", "eslint",
       "prettier", "mypy", "ruff", "docstring", "emoji", "絵文字",
       "型注釈", "敬語", "箇条書き"]

PAIRS = [("typescript", "javascript"), ("pytest", "unittest"),
         ("テスト", "pytest"), ("print", "console"), ("eslint", "prettier"),
         ("絵文字", "emoji"), ("print", "logging")]


def main() -> int:
    store = CrossStore.load(NEW_STORE)
    labels = store.source_labels or set()
    n = len(store.crosses)
    tally: Counter = Counter()
    for cross in store.crosses.values():
        for f in cross or ():
            if f not in labels:
                tally[f] += 1

    out: dict = {"n_cores": n}

    # ---- C2b 閾値の算術 ------------------------------------------------
    ord_sh = sorted(((w, tally.get(w.casefold(), 0) / n) for w in ORD),
                    key=lambda x: -x[1])
    con_sh = sorted(((w, tally.get(w.casefold(), 0) / n) for w in CON),
                    key=lambda x: -x[1])
    # 26語中21語を落とすのに必要な閾値 = 21番目に高い普通語の share
    need = ord_sh[20][1]
    casualties = [(w, round(100 * s, 4)) for w, s in con_sh if s >= need]
    out["C2b_threshold_arithmetic"] = {
        "ordinary_sorted_pct": [(w, round(100 * s, 4)) for w, s in ord_sh],
        "content_sorted_pct": [(w, round(100 * s, 4)) for w, s in con_sh],
        "threshold_to_drop_21_of_26_pct": round(100 * need, 4),
        "21st_ordinary_word": ord_sh[20][0],
        "content_words_killed_at_that_threshold": casualties,
        "content_killed_n": len(casualties),
        "content_surviving": [(w, round(100 * s, 4)) for w, s in con_sh
                              if 0 < s < need],
        "highest_content": con_sh[0],
        "lowest_nonzero_ordinary": [(w, round(100 * s, 4))
                                    for w, s in ord_sh if s > 0][-1],
        "ordinary_words_below_highest_content": [
            (w, round(100 * s, 4)) for w, s in ord_sh
            if 0 < s < con_sh[0][1]],
    }

    # ---- C3b なぜ姉妹語が出なかったか ------------------------------------
    manifest = json.loads((HERE / "corpus_manifest.json").read_text())
    texts = {}
    for row in manifest["kept"]:
        texts[row["path"]] = Path(row["path"]).read_text(encoding="utf-8")

    pair_rows = []
    for a, b in PAIRS:
        al, bl = a.casefold(), b.casefold()
        both_cores = [c for c, cr in store.crosses.items()
                      if cr and al in cr and bl in cr]
        files_both = 0
        lines_both = 0
        for t in texts.values():
            tl = t.casefold()
            if al in tl and bl in tl:
                files_both += 1
                for line in tl.splitlines():
                    if al in line and bl in line:
                        lines_both += 1
        pair_rows.append({
            "pair": [a, b],
            "cores_holding_both_facets": len(both_cores),
            "example_cores": sorted(both_cores)[:6],
            "corpus_files_containing_both": files_both,
            "corpus_lines_containing_both": lines_both,
            "a_cores": tally.get(al, 0), "b_cores": tally.get(bl, 0),
        })
    out["C3b_cooccurrence"] = pair_rows

    # ---- C3c 番人から見た実際の焼き込み(読み取りのみ・保存しない) ---------
    bakes = {}
    for req in ("TypeScript", "pytest", "テスト", "絵文字"):
        c = Covenant(name=f"probe-{req}", quote=f"{req}を使う",
                     requires=[req], forbids=[])
        r = bake_inferred(c, store, limit=6, store_name="guard_store.json")
        bakes[req] = {"inferred_forbids": r.get("inferred_forbids"),
                      "verdict": r.get("verdict")}
    out["C3c_bake_inferred_readonly"] = bakes

    (HERE / "results_followup.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
