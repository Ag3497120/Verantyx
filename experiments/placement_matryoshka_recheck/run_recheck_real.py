# -*- coding: utf-8 -*-
"""同点換え再検査 — 実ストア測定。RECHECK.md 追記2が事前登録。

読み取り専用。店には一切書かない。決定論(seed固定)・LLMなし。
"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.cross import AXES, ShellCross
from verantyx.consensus import run_consensus
from verantyx.consensus_store import _MassView, candidates_for_query
from verantyx.export_sqlite import vera as load_published
from verantyx.face_roles import FACET_FACES
from verantyx.placement import (choose_for_core, demand_from_queries,
                                facet_document_frequency, score_facets)

N_PROBES = 300
K_CANDIDATES = 6
DB = Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db"


def mid_facets(store, core, n=3, seed=0):
    """中頻度の facet n語。最頻は一般語すぎ、最稀は断片が多いので中央帯。"""
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


def main():
    t0 = time.time()
    v = load_published(DB)
    store = v.stores["ja"]
    masses = _MassView(store)
    df = facet_document_frequency(store)
    print(f"store loaded: {store.n_cores()} cores  {time.time()-t0:.1f}s",
          file=sys.stderr)

    rich = sorted(c for c, f in store.crosses.items() if len(f) >= 8)
    picks_pop = random.Random(42).sample(rich, min(N_PROBES, len(rich)))

    # 需要(train): 同じ核母集団から別seedで3反復
    train = []
    for r in range(3):
        for c in picks_pop:
            t = mid_facets(store, c, seed=100 + r)
            if t:
                train.append(" ".join(t))
    asked = demand_from_queries(store, train)
    print(f"demand from {len(train)} train queries  {time.time()-t0:.1f}s",
          file=sys.stderr)

    def picks_for(cores, policy, tie_reversed=False):
        out = {}
        for c in cores:
            if policy == "frequency" and not tie_reversed:
                out[c] = [f for f, _n in store.top_facets(c, k=len(FACET_FACES))]
                continue
            if policy == "frequency" and tie_reversed:
                cross = store.crosses.get(c) or {}
                items = sorted(cross.items(), key=lambda kv: kv[0], reverse=True)
                items = sorted(items, key=lambda kv: -kv[1])
                out[c] = [f for f, _n in items[:len(FACET_FACES)]]
                continue
            scored = score_facets(store, c, df=df, n_cores=store.n_cores(),
                                  asked=asked, weight=0.0)
            if tie_reversed:
                pairs = sorted(scored, key=lambda sf: sf[1], reverse=True)
                pairs = sorted(pairs, key=lambda sf: -sf[0])
            else:
                pairs = scored
            out[c] = [f for _s, f in pairs[:len(FACET_FACES)]]
        return out

    def build_shell(cores, picks):
        shell = ShellCross()
        for axis, core in zip(AXES, cores):
            shell.faces[axis]["tip"] = core
            shell.reflections[axis] = core
            for face, facet in zip(FACET_FACES, picks[core]):
                shell.faces[axis][face] = facet
        return shell

    arms = {a: {"correct": 0, "wrong": 0, "refusal": 0}
            for a in ("frequency", "simulated",
                      "recheck_ties", "recheck_ties_freq")}
    reachable = 0  # 正解核が候補6件に入っていた問い(鍵が意味を持つ範囲)
    demoted = {"recheck_ties": {"was_correct": 0, "was_wrong": 0},
               "recheck_ties_freq": {"was_correct": 0, "was_wrong": 0}}
    n_asked_q = 0

    for want in picks_pop:
        terms = mid_facets(store, want, seed=999)
        if not terms:
            continue
        q = " ".join(terms)
        cores = candidates_for_query(store, q, k=K_CANDIDATES)
        if not cores:
            continue
        n_asked_q += 1
        if want in cores:
            reachable += 1
        for policy in ("frequency", "simulated"):
            p1 = picks_for(cores, policy)
            r1 = run_consensus(build_shell(cores, p1), q, masses=masses)

            def cls(verdict, core):
                if verdict != "ANSWER":
                    return "refusal"
                return "correct" if core == want else "wrong"

            arms[policy][cls(r1.verdict, r1.core)] += 1

            gate = ("recheck_ties" if policy == "simulated"
                    else "recheck_ties_freq")
            if r1.verdict != "ANSWER":
                arms[gate][cls(r1.verdict, r1.core)] += 1
                continue
            p2 = picks_for(cores, policy, tie_reversed=True)
            r2 = run_consensus(build_shell(cores, p2), q, masses=masses)
            if (r2.verdict, r2.core) == (r1.verdict, r1.core):
                arms[gate][cls(r1.verdict, r1.core)] += 1
            else:
                arms[gate]["refusal"] += 1
                key = "was_correct" if r1.core == want else "was_wrong"
                demoted[gate][key] += 1

    out = {"db": str(DB), "n_cores": store.n_cores(),
           "n_probes_asked": n_asked_q,
           "n_reachable": reachable,
           "arms": arms, "demoted_answers": demoted,
           "elapsed_s": round(time.time() - t0, 1)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path(__file__).with_name("results_recheck_real.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
