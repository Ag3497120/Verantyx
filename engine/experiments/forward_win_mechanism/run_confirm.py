# -*- coding: utf-8 -*-
"""確認測定 — PREREG.md が事前登録。読み取り専用・決定論。

探索(seed 42)とは別の核集合(seed 4242、探索核を除外)で、
帯割れの特定性裁定(マージン≥3.0)を検査する。
"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.consensus import query_content
from verantyx.consensus_store import direction_band, frame_stripped
from verantyx.export_sqlite import vera as load_published
from verantyx.lex_filters import norm_words

DB = Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db"
MARGIN = 3.0
REPORT_ONLY = (1.5, 2.0, 5.0)


def mid_facets(store, core, n=3, seed=0):
    cross = store.crosses.get(core) or {}
    fs = sorted((f for f, c in cross.items() if f.isalpha() or
                 all("぀" <= ch or ch.isalnum() for ch in f)),
                key=lambda f: (-cross[f], f))
    if len(fs) < n:
        return None
    mid = fs[len(fs) // 4: len(fs) // 4 + max(n * 3, n)]
    if len(mid) < n:
        mid = fs
    rng = random.Random(f"{seed}:{core}")
    return rng.sample(mid, n) if len(mid) >= n else None


def specificity(store, c, qset):
    cross = store.crosses.get(c) or {}
    cov = len([w for w in qset if w in cross or w in norm_words(c)])
    return cov / max(1, len(cross))


def adjudicate(store, qset):
    """(verdict, core, margin): REVERSE_UNIQUE / REVERSE_SPECIFIC / None."""
    band, best = direction_band(store, qset)
    if not band:
        return None, None, None
    if len(band) == 1:
        return "REVERSE_UNIQUE", next(iter(band)), None
    sp = sorted(((specificity(store, c, qset), c) for c in band), reverse=True)
    if sp[0][0] == sp[1][0]:
        return None, None, None
    margin = sp[0][0] / sp[1][0]
    if margin >= MARGIN:
        return "REVERSE_SPECIFIC", sp[0][1], margin
    return None, None, margin


def main():
    t0 = time.time()
    v = load_published(DB)
    store = v.stores["ja"]
    rich = sorted(c for c, f in store.crosses.items() if len(f) >= 8)
    explore = set(random.Random(42).sample(rich, min(300, len(rich))))
    pool = [c for c in random.Random(4242).sample(rich, min(600, len(rich)))
            if c not in explore]
    picks = pool[:300]

    fam = {}
    for name in ("bare", "wrapped"):
        n = dict(asked=0, unique_correct=0, unique_wrong=0,
                 specific_correct=0, specific_wrong=0, abstain=0)
        margins_wrong, wrong_cases = [], []
        report = {th: dict(correct=0, wrong=0) for th in REPORT_ONLY}
        for want in picks:
            t = mid_facets(store, want, seed=999)
            if not t:
                continue
            if name == "bare":
                q = " ".join(t)
                qset, _ = query_content(q)
            else:
                q = f"{t[0]}と{t[1]}と{t[2]}に関係するのは何ですか"
                from verantyx.lang import ja_content_runs
                qset = frame_stripped(q, ja_content_runs(q))
            n["asked"] += 1
            verdict, core, margin = adjudicate(store, qset)
            if verdict is None:
                n["abstain"] += 1
            elif verdict == "REVERSE_UNIQUE":
                n["unique_correct" if core == want else "unique_wrong"] += 1
            else:
                key = "specific_correct" if core == want else "specific_wrong"
                n[key] += 1
                if core != want:
                    margins_wrong.append(round(margin, 2))
                    if len(wrong_cases) < 10:
                        wrong_cases.append(dict(q=q, want=want, picked=core,
                                                margin=round(margin, 2)))
            # 参考しきい値(採否に使わない)
            if margin is not None:
                for th in REPORT_ONLY:
                    if margin >= th:
                        band, _ = direction_band(store, qset)
                        sp = max(((specificity(store, c, qset), c)
                                  for c in band))
                        k = "correct" if sp[1] == want else "wrong"
                        report[th][k] += 1
        fam[name] = dict(counts=n, wrong_margins=margins_wrong,
                         wrong_cases=wrong_cases,
                         report_only={str(t): r for t, r in report.items()})

    # (c) 名前形100本: 順方向 ANSWER 不変(ja_consensus_ask 全経路)
    from verantyx.consensus_store import ja_consensus_ask
    name_ok = name_asked = 0
    from verantyx.lex_filters import display_sym
    for want in picks[:100]:
        q = display_sym(want) + "とは"
        out = ja_consensus_ask(store, q)
        name_asked += 1
        if out.get("verdict") == "ANSWER" and out.get("core_key") == want:
            name_ok += 1
    out = dict(db=str(DB), margin=MARGIN, families=fam,
               name_form=dict(asked=name_asked, forward_answer_correct=name_ok),
               elapsed_s=round(time.time() - t0, 1))
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    Path(__file__).with_name("results_confirm.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
