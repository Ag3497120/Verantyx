# -*- coding: utf-8 -*-
"""REVERSE_UNIQUE 昇格の3族探針 — PREREG_PROMOTION.md が事前登録。"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.consensus_store import ja_consensus_ask, direction_band
from verantyx.export_sqlite import vera as load_published
from verantyx.lang import ja_content_runs

N = 300
DB = Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db"


def mid_facets(store, core, n=3, seed=999):
    cross = store.crosses.get(core) or {}
    facets = sorted((f for f, c in cross.items() if f.isalpha() or
                     all("぀" <= ch or ch.isalnum() for ch in f)),
                    key=lambda f: (-cross[f], f))
    if len(facets) < n:
        return None
    mid = facets[len(facets) // 4: len(facets) // 4 + max(n * 3, n)]
    if len(mid) < n:
        mid = facets
    rng = random.Random(f"999:{core}")
    return rng.sample(mid, n) if len(mid) >= n else None


import re as _re
_FRAME = _re.compile(r"(に関係する|に関する|について|とは何|は何|を教えて"
                     r"|ですか|でしょうか|ってなに|って何)")

def frame_stripped(query, runs):
    """枠パターンの中にしか現れない run を主題から外す(閉じた規則)。"""
    spans = [m.span() for m in _FRAME.finditer(query)]
    out = set()
    for r in runs:
        keep = False
        for m in _re.finditer(_re.escape(r), query):
            if not any(a <= m.start() and m.end() <= b for a, b in spans):
                keep = True
                break
        if keep:
            out.add(r)
    return out


def promoted(store, query, want):
    """昇格規則そのもの: 順方向非ANSWER ∧ 帯唯一 ∧ 被覆≥2。"""
    r = ja_consensus_ask(store, query, placement_invariant=True)
    v = r.get("verdict")
    if v == "ANSWER":
        return ("fw_answer", r.get("core") == want)
    runs = ja_content_runs(query) or []
    qset = frame_stripped(query, runs)
    if not qset:
        return ("no_qset", None)
    band, best = direction_band(store, qset)
    if len(band) == 1 and best >= 2:
        c = next(iter(band))
        return ("reverse_unique", c == want)
    return ("silent", None)


def main():
    t0 = time.time()
    v = load_published(DB)
    store = v.stores["ja"]
    rich = sorted(c for c, f in store.crosses.items() if len(f) >= 8)
    picks = random.Random(42).sample(rich, min(N, len(rich)))

    out = {}
    for fam, wrap in (("a_bare", "{0} {1} {2}"),
                      ("b_natural", "{0}と{1}と{2}に関係するのは何ですか")):
        st = {"fw_answer_ok": 0, "fw_answer_ng": 0, "ru_ok": 0, "ru_ng": 0,
              "silent": 0, "no_qset": 0, "asked": 0,
              "ng_examples": []}
        for want in picks:
            t = mid_facets(store, want)
            if not t:
                continue
            q = wrap.format(*t)
            st["asked"] += 1
            kind, ok = promoted(store, q, want)
            if kind == "fw_answer":
                st["fw_answer_ok" if ok else "fw_answer_ng"] += 1
            elif kind == "reverse_unique":
                st["ru_ok" if ok else "ru_ng"] += 1
                if not ok and len(st["ng_examples"]) < 5:
                    st["ng_examples"].append(q)
            else:
                st[kind] += 1
        out[fam] = st

    # (c) 名前形の回帰: <core名>とは 100本 — 配線が既存ANSWERを変えないか。
    # 昇格規則は「順方向が非ANSWERの時だけ」動くので、ここでは順方向の
    # verdict がそのまま立つことを確認する。
    name_picks = random.Random(7).sample(rich, 100)
    reg = {"answer": 0, "refusal": 0, "asked": 0}
    for c in name_picks:
        from verantyx.lex_filters import display_sym
        q = display_sym(c) + "とは"
        reg["asked"] += 1
        r = ja_consensus_ask(store, q, placement_invariant=True)
        reg["answer" if r.get("verdict") == "ANSWER" else "refusal"] += 1
    out["c_name_forward"] = reg

    out["elapsed_s"] = round(time.time() - t0, 1)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path(__file__).with_name("results_promotion.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
