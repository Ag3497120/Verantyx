# -*- coding: utf-8 -*-
"""診断2(探索・読み取り専用): 被覆同点帯の中で正解を分ける特徴は何か。

逆方向は帯が唯一の時だけ答える(158/0)。帯が割れた142問は棄権する。
「合意が正解を選ぶ」が意味を持つのはまさにここ — 被覆では同点の核の
中から、追加の実測特徴で正解を一位にできるか。

これは仮説生成の探索。確認測定は別の種(異なる300核)で事前登録する。

候補特徴(全て店の実測のみ):
  attestation = 覆った語の facet 数の合計(その核がその語を何回証言したか)
  specificity = 被覆 / その核の面数
  mass        = 核の出現回数(log減衰)
  n_faces     = 面数
"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.consensus import query_content
from verantyx.consensus_store import _word_index, direction_band
from verantyx.export_sqlite import vera as load_published
from verantyx.lex_filters import norm_words

N_PROBES = 300
DB = Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db"


def mid_facets(store, core, n=3, seed=0):
    cross = store.crosses.get(core) or {}
    facets = sorted((f for f, c in cross.items() if f.isalpha() or
                     all("぀" <= ch or ch.isalnum() for ch in f)),
                    key=lambda f: (-cross[f], f))
    if len(facets) < n:
        return None
    mid = facets[len(facets) // 4: len(facets) // 4 + max(n * 3, n)]
    if len(mid) < n:
        mid = facets
    rng = random.Random(f"{seed}:{core}")
    return rng.sample(mid, n) if len(mid) >= n else None


def features(store, core, qset):
    cross = store.crosses.get(core) or {}
    nw = norm_words(core)
    covered = [w for w in qset if w in cross or w in nw]
    attest = sum(cross.get(w, 0) for w in covered)
    return dict(
        coverage=len(covered),
        attestation=attest,
        specificity=len(covered) / max(1, len(cross)),
        mass=store.mass(core),
        n_faces=len(cross),
    )


def main():
    t0 = time.time()
    v = load_published(DB)
    store = v.stores["ja"]
    rich = sorted(c for c, f in store.crosses.items() if len(f) >= 8)
    picks_pop = random.Random(42).sample(rich, min(N_PROBES, len(rich)))

    n = dict(asked=0, band_unique=0, band_unique_correct=0,
             band_split_want_in=0, band_split_want_out=0)
    band_sizes = []
    # 帯が割れ、正解が帯に居る事例: 各特徴で正解が一位になる率
    feat_wins = {k: 0 for k in ("attestation", "specificity", "mass",
                                "n_faces_min", "attest_then_spec")}
    split_rows = []
    for want in picks_pop:
        terms = mid_facets(store, want, seed=999)
        if not terms:
            continue
        q = " ".join(terms)
        qset, _h = query_content(q)
        band, best = direction_band(store, qset)
        if not band:
            continue
        n["asked"] += 1
        band_sizes.append(len(band))
        if len(band) == 1:
            n["band_unique"] += 1
            if next(iter(band)) == want:
                n["band_unique_correct"] += 1
            continue
        if want not in band:
            n["band_split_want_out"] += 1
            continue
        n["band_split_want_in"] += 1
        fs = {c: features(store, c, qset) for c in band}
        # 各特徴の単独一位(同点一位は不当選 — 正直な規則)
        def unique_top(key, reverse=True):
            vals = sorted(((fs[c][key], c) for c in band), reverse=reverse)
            return vals[0][1] if len(vals) < 2 or vals[0][0] != vals[1][0] else None
        if unique_top("attestation") == want:
            feat_wins["attestation"] += 1
        if unique_top("specificity") == want:
            feat_wins["specificity"] += 1
        if unique_top("mass") == want:
            feat_wins["mass"] += 1
        # 面数が最小 = 最も専門の核
        vals = sorted((fs[c]["n_faces"], c) for c in band)
        if len(vals) >= 2 and vals[0][0] != vals[1][0] and vals[0][1] == want:
            feat_wins["n_faces_min"] += 1
        # 段階: attestation 一位、同点なら specificity
        top_a = unique_top("attestation")
        if top_a is None:
            best_a = max(fs[c]["attestation"] for c in band)
            tied = [c for c in band if fs[c]["attestation"] == best_a]
            vals = sorted(((fs[c]["specificity"], c) for c in tied), reverse=True)
            top_a = (vals[0][1] if len(vals) < 2 or vals[0][0] != vals[1][0]
                     else None)
        if top_a == want:
            feat_wins["attest_then_spec"] += 1
        if len(split_rows) < 10:
            split_rows.append(dict(
                query=q, want=want, band_size=len(band),
                want_feat=fs[want],
                rivals={c: fs[c] for c in sorted(band)[:4] if c != want}))

    import statistics
    out = dict(
        db=str(DB), counts=n,
        band_size=dict(
            median=statistics.median(band_sizes) if band_sizes else None,
            max=max(band_sizes) if band_sizes else None),
        feature_picks_want_of_split_want_in=feat_wins,
        elapsed_s=round(time.time() - t0, 1),
        samples=split_rows)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    Path(__file__).with_name("results_diagnose2.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
