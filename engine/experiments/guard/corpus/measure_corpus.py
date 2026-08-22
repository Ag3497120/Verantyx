# -*- coding: utf-8 -*-
"""C1/C2/C3/C5 の測定 — 事前登録 PREREG_CORPUS.md の基準で。

巨大な本店は **1回だけ** 読む。読んだあと本店から必要な数字を全部取って
から解放する。数値は全て実行結果で、予想は書かない。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import extract_covenants, siblings  # noqa: E402
from verantyx.cross_store import CrossStore  # noqa: E402

HERE = Path(__file__).resolve().parent
NEW_STORE = HERE / "guard_store.json"
MAIN_STORE = ROOT / "vera_store.json"

# ---------------------------------------------------------------- 語表
# PREREG_CORPUS.md で固定。測定後に足さない。
C1_TERMS_JA = ["絵文字", "テスト", "型注釈", "敬語", "箇条書き", "見出し",
               "注釈", "検証"]
C1_TERMS_EN = ["typescript", "javascript", "pytest", "unittest", "eslint",
               "prettier", "mypy", "ruff", "black", "print", "console",
               "todo", "emoji", "docstring", "lint", "commit"]
C1_TERMS = C1_TERMS_JA + C1_TERMS_EN

C2_ORDINARY = ["the", "is", "are", "new", "use", "used", "using", "one",
               "time", "part", "name", "make", "get", "set", "run", "file",
               "code", "all", "can", "will",
               "場合", "必要", "使用", "以下", "内容", "方法"]
C2_CONTENT = ["typescript", "javascript", "pytest", "unittest", "eslint",
              "prettier", "mypy", "ruff", "docstring", "emoji",
              "絵文字", "型注釈", "敬語", "箇条書き"]
C2_THRESHOLDS = [0.02, 0.01, 0.005, 0.002]

C3_TARGETS = {
    "typescript": ["javascript"],
    "pytest": ["unittest", "nose", "test"],
    "print": ["log", "logging", "console"],
    "eslint": ["prettier", "ruff", "lint"],
    "テスト": ["pytest", "unittest", "test"],
    "絵文字": ["emoji", "記号", "顔文字"],
}

# C5: 20本の指示文(固定)
C5_SENTENCES = [
    "絵文字を使わないで",
    "TODOを書かないでください",
    "必ずテストを実行して",
    "型注釈を必ず付けて",
    "print文は使わないで",
    "TypeScriptを使ってください",
    "コミットは絶対にしないで",
    "日本語で答えて",
    "敬語は使わなくていい",
    "箇条書きにして",
    "Never use emojis",
    "Always run pytest before committing",
    "Do not use console.log",
    "Stop using TODO comments",
    "You must use TypeScript",
    "Never commit to main",
    "Always add type hints",
    "Do not create documentation files",
    "なんかいい感じにして",
    "just make it nice",
]


def facet_stats(store: CrossStore) -> tuple[Counter, int]:
    """facet → その語を持つ core 数。siblings の _too_common と同じ数え方。"""
    labels = getattr(store, "source_labels", set()) or set()
    tally: Counter = Counter()
    for cross in store.crosses.values():
        for f in cross or ():
            if f not in labels:
                tally[f] += 1
    return tally, len(store.crosses)


def rank_table(tally: Counter, n_cores: int, terms) -> dict:
    ordered = tally.most_common()
    rank_of = {w: i + 1 for i, (w, _c) in enumerate(ordered)}
    out = {}
    for t in terms:
        key = t.casefold()
        cnt = tally.get(key, 0)
        out[t] = {"cores_with_facet": cnt,
                  "share": round(cnt / n_cores, 8) if n_cores else 0.0,
                  "share_pct": round(100.0 * cnt / n_cores, 4) if n_cores else 0.0,
                  "rank": rank_of.get(key)}
    return out


def main() -> int:
    res: dict = {"prereg": "PREREG_CORPUS.md", "generated": time.strftime("%F %T")}

    # ------------------------------------------------------ 新店
    t0 = time.time()
    new = CrossStore.load(NEW_STORE)
    res["new_store"] = {
        "path": str(NEW_STORE), "load_seconds": round(time.time() - t0, 1),
        "cores": len(new.crosses), "n_sentences": new.n_sentences,
        "distinct_facets": None, "source_labels": len(new.source_labels)}
    new_tally, new_cores = facet_stats(new)
    res["new_store"]["distinct_facets"] = len(new_tally)

    # 停止条件 S2
    res["stop_S2_cores_below_1000"] = new_cores < 1000

    # ---- C1 (新店側) --------------------------------------------------
    c1_new = rank_table(new_tally, new_cores, C1_TERMS)
    for t in C1_TERMS:
        c1_new[t]["is_core"] = t.casefold() in new.crosses

    # ---- C2 -----------------------------------------------------------
    c2_new = rank_table(new_tally, new_cores, sorted(set(C2_ORDINARY + C2_CONTENT)))
    c2 = {"n_cores": new_cores, "n_distinct_facets": len(new_tally),
          "terms": c2_new, "thresholds": {}}
    for th in C2_THRESHOLDS:
        dropped_all = sum(1 for _w, c in new_tally.items() if c / new_cores >= th)
        ord_dropped = [w for w in C2_ORDINARY
                       if new_tally.get(w.casefold(), 0) / new_cores >= th]
        ord_absent = [w for w in C2_ORDINARY
                      if new_tally.get(w.casefold(), 0) == 0]
        cont_dropped = [w for w in C2_CONTENT
                        if new_tally.get(w.casefold(), 0) / new_cores >= th]
        cont_absent = [w for w in C2_CONTENT
                       if new_tally.get(w.casefold(), 0) == 0]
        c2["thresholds"][f"{th:.3f}"] = {
            "words_dropped_total": dropped_all,
            "ordinary_dropped": ord_dropped,
            "ordinary_dropped_n": len(ord_dropped),
            "ordinary_absent_from_store": ord_absent,
            "content_wrongly_dropped": cont_dropped,
            "content_wrongly_dropped_n": len(cont_dropped),
            "content_absent_from_store": cont_absent,
            "verdict_prereg": (len(ord_dropped) >= 21 and not cont_dropped),
        }
    c2["separates"] = any(v["verdict_prereg"] for v in c2["thresholds"].values())
    # 上位40 facet — 何が家具かを目で見るため
    c2["top40_facets"] = [
        {"term": w, "cores": c, "share_pct": round(100.0 * c / new_cores, 4)}
        for w, c in new_tally.most_common(40)]
    res["C2_word_quality"] = c2

    # ---- C3 姉妹語 -----------------------------------------------------
    c3 = {"params": "limit=6, min_shared=2, max_fanout=60, max_common=0.02",
          "terms": {}}
    hits = 0
    for term, wanted in C3_TARGETS.items():
        t0 = time.time()
        sib = siblings(new, term, limit=6)
        got = [w for w, _s in sib]
        ok = any(w in got for w in wanted)
        hits += 1 if ok else 0
        c3["terms"][term] = {"top6": sib, "wanted_any_of": wanted,
                             "recovered": ok,
                             "seconds": round(time.time() - t0, 2)}
    c3["recovered_n"] = hits
    c3["verdict_prereg"] = ("recovers" if hits >= 3
                            else "partial" if hits >= 1 else "does_not_recover")
    res["C3_siblings_new_store"] = c3

    # ---- C5 抽出 -------------------------------------------------------
    c5 = [{"text": s, "candidates": len(extract_covenants(s)),
           "requires": [c.get("requires") for c in extract_covenants(s)],
           "forbids": [c.get("forbids") for c in extract_covenants(s)]}
          for s in C5_SENTENCES]
    res["C5_extraction"] = {
        "note": "extract_covenants は店を引数に取らない — 同一プロセスで"
                "新店を読んだ後に走らせた結果",
        "with_candidates": sum(1 for r in c5 if r["candidates"]),
        "total": len(c5), "rows": c5}

    del new_tally
    del new

    # ------------------------------------------------------ 本店(1回だけ)
    t0 = time.time()
    main_store = CrossStore.load(MAIN_STORE)
    load_s = round(time.time() - t0, 1)
    main_tally, main_cores = facet_stats(main_store)
    c1_main = rank_table(main_tally, main_cores, C1_TERMS)
    for t in C1_TERMS:
        c1_main[t]["is_core"] = t.casefold() in main_store.crosses
    ref = rank_table(main_tally, main_cores, ["new", "dependencies", "game",
                                              "the", "time", "part", "name"])
    res["main_store"] = {"path": str(MAIN_STORE), "load_seconds": load_s,
                         "cores": main_cores, "n_sentences": main_store.n_sentences,
                         "distinct_facets": len(main_tally),
                         "source": main_store.source,
                         "reference_ranks": ref}
    # 本店でも姉妹語を試す — 対比のため
    c3m = {}
    for term, wanted in C3_TARGETS.items():
        t0 = time.time()
        sib = siblings(main_store, term, limit=6)
        c3m[term] = {"top6": sib, "recovered": any(w in [x for x, _ in sib]
                                                   for w in wanted),
                     "seconds": round(time.time() - t0, 2)}
    res["C3_siblings_main_store"] = c3m

    # ---- C1 対比表 -----------------------------------------------------
    table = []
    for t in C1_TERMS:
        table.append({"term": t,
                      "main_cores_with_facet": c1_main[t]["cores_with_facet"],
                      "main_is_core": c1_main[t]["is_core"],
                      "new_cores_with_facet": c1_new[t]["cores_with_facet"],
                      "new_share_pct": c1_new[t]["share_pct"],
                      "new_rank": c1_new[t]["rank"],
                      "new_is_core": c1_new[t]["is_core"]})
    present_new = sum(1 for r in table if r["new_cores_with_facet"] > 0)
    present_main = sum(1 for r in table if r["main_cores_with_facet"] > 0)
    res["C1_coverage"] = {
        "terms": len(C1_TERMS), "present_in_main": present_main,
        "present_in_new": present_new, "table": table,
        "verdict_prereg": ("improved" if present_new >= 18
                           else "partial" if present_new >= 4
                           else "not_improved")}

    (HERE / "results_corpus.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"C1": res["C1_coverage"]["verdict_prereg"],
                      "present_main": present_main,
                      "present_new": present_new,
                      "C2_separates": c2["separates"],
                      "C3": c3["verdict_prereg"],
                      "C3_recovered": hits}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
