# -*- coding: utf-8 -*-
"""facet重なり補完の追記 — PREREG.md が事前登録。読み取り専用・決定論。"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.cross import AXES, ShellCross
from verantyx.consensus import run_consensus
from verantyx.consensus_store import (_MassView, candidates_for_query,
                                      query_content)
from verantyx.export_sqlite import vera as load_published
from verantyx.face_roles import FACET_FACES
from verantyx.placement import (demand_from_queries, facet_document_frequency,
                                score_facets)

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


def candidates_appended(store, query, *, k=K):
    """変分: 現行候補の後ろに facet 重なり候補を追記(残枠のみ)。"""
    base = candidates_for_query(store, query, k=k)
    if len(base) >= k:
        return base
    qset, _head = query_content(query)
    if not qset:
        return base
    scored = []
    for core, cross in store.crosses.items():
        if core in base:
            continue
        overlap = len(qset & set(cross))
        if overlap > 0:
            scored.append((-(overlap * 1000 + store.mass(core)), core))
    scored.sort()
    return base + [c for _s, c in scored[:k - len(base)]]


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

    def build_shell(cores, picks):
        shell = ShellCross()
        for axis, core in zip(AXES, cores):
            shell.faces[axis]["tip"] = core
            shell.reflections[axis] = core
            for face, facet in zip(FACET_FACES, picks[core]):
                shell.faces[axis][face] = facet
        return shell

    res = {a: {"reachable": 0, "correct": 0, "wrong": 0, "refusal": 0,
               "asked": 0}
           for a in ("baseline", "appended")}
    for want in picks_pop:
        terms = mid_facets(store, want, seed=999)
        if not terms:
            continue
        q = " ".join(terms)
        for arm, fn in (("baseline", candidates_for_query),
                        ("appended", candidates_appended)):
            cores = fn(store, q, k=K)
            if not cores:
                continue
            res[arm]["asked"] += 1
            if want in cores:
                res[arm]["reachable"] += 1
            r1 = run_consensus(build_shell(cores, picks_for(cores)), q,
                               masses=masses)
            if r1.verdict != "ANSWER":
                res[arm]["refusal"] += 1
            elif r1.core == want:
                res[arm]["correct"] += 1
            else:
                res[arm]["wrong"] += 1
    out = {"db": str(DB), "arms": res,
           "elapsed_s": round(time.time() - t0, 1)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path(__file__).with_name("results_reach.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
