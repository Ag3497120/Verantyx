# -*- coding: utf-8 -*-
"""双方向の重ね — PREREG.md が事前登録。読み取り専用・決定論。"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.cross import AXES, ShellCross
from verantyx.consensus import run_consensus, query_content
from verantyx.consensus_store import _MassView, candidates_for_query
from verantyx.export_sqlite import vera as load_published
from verantyx.face_roles import FACET_FACES
from verantyx.placement import demand_from_queries, facet_document_frequency, score_facets

N_PROBES = 300
K = 6
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


from verantyx.consensus_store import direction_band as reverse_top
# 配線済みの direction_band(名前も被覆に数える版)をそのまま使う —
# 実験と本体が別実装だと、測ったものと出荷したものが乖離する。


def main():
    t0 = time.time()
    v = load_published(DB)
    store = v.stores["ja"]
    masses = _MassView(store)
    df = facet_document_frequency(store)
    rich = sorted(c for c, f in store.crosses.items() if len(f) >= 8)
    picks_pop = random.Random(42).sample(rich, min(N_PROBES, len(rich)))
    train = []
    for r in range(3):
        for c in picks_pop:
            t = mid_facets(store, c, seed=100 + r)
            if t:
                train.append(" ".join(t))
    asked = demand_from_queries(store, train)

    def picks_for(cores):
        out = {}
        for c in cores:
            scored = score_facets(store, c, df=df, n_cores=store.n_cores(),
                                  asked=asked, weight=0.0)
            out[c] = [f for _s, f in scored[:len(FACET_FACES)]]
        return out

    def build_shell(cores):
        shell = ShellCross()
        p = picks_for(cores)
        for axis, core in zip(AXES, cores):
            shell.faces[axis]["tip"] = core
            shell.reflections[axis] = core
            for face, facet in zip(FACET_FACES, p[core]):
                shell.faces[axis][face] = facet
        return shell

    res = {a: {"correct": 0, "wrong": 0, "refusal": 0, "asked": 0}
           for a in ("forward", "reverse", "layered")}
    rev_band_sizes = []
    for want in picks_pop:
        terms = mid_facets(store, want, seed=999)
        if not terms:
            continue
        q = " ".join(terms)
        qset, _h = query_content(q)
        cores = candidates_for_query(store, q, k=K)
        if not cores:
            continue
        for a in res:
            res[a]["asked"] += 1
        r1 = run_consensus(build_shell(cores), q, masses=masses)
        fw = ("refusal" if r1.verdict != "ANSWER"
              else ("correct" if r1.core == want else "wrong"))
        res["forward"][fw] += 1

        band, best = reverse_top(store, qset)
        rev_band_sizes.append(len(band))
        # reverse 単独(参考): 同点帯が1つならそれを答え、複数なら棄権
        if len(band) == 1:
            rv_core = next(iter(band))
            res["reverse"]["correct" if rv_core == want else "wrong"] += 1
        else:
            res["reverse"]["refusal"] += 1

        # layered: 順方向ANSWERが逆方向の同点帯に入る時だけANSWER
        if r1.verdict != "ANSWER":
            res["layered"]["refusal"] += 1
        elif r1.core in band:
            res["layered"]["correct" if r1.core == want else "wrong"] += 1
        else:
            res["layered"]["refusal"] += 1

    import statistics
    out = {"db": str(DB), "arms": res,
           "reverse_band_size": {
               "median": statistics.median(rev_band_sizes) if rev_band_sizes else None,
               "max": max(rev_band_sizes) if rev_band_sizes else None},
           "elapsed_s": round(time.time() - t0, 1)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path(__file__).with_name("results_bidir.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
