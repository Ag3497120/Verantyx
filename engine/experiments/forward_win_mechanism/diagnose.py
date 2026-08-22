# -*- coding: utf-8 -*-
"""診断: 正解が候補に居るのに順方向合意で負ける瞬間、何が起きているか。

読み取り専用・決定論。run_bidir.py と同一の300探針・同一の殻組み。
変更は一切しない — 各腕のエネルギー分解を記録するだけ。

仮説(測る前に書く):
  H1. 正解核の腕上 facet 重なり(殻に載った4面との交差)は ほぼ0。
      一方、全 cross との交差は 3(探針の定義上)。
      → 証拠は店に在るが、殻の4面切り落としで合意に届いていない。
  H2. 勝った誤答核は「名前一致 or 腕上重なり ≥1」×「巨大質量」で
      エネルギーを稼いでいる。
"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.cross import AXES, ShellCross
from verantyx.consensus import (ConsensusConfig, axis_energy, query_content,
                                run_consensus)
from verantyx.consensus_store import _MassView, candidates_for_query
from verantyx.export_sqlite import vera as load_published
from verantyx.face_roles import FACET_FACES, facts_on_axis
from verantyx.lex_filters import norm_words
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


def main():
    t0 = time.time()
    v = load_published(DB)
    store = v.stores["ja"]
    masses = _MassView(store)
    cfg = ConsensusConfig()
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

    n = dict(asked=0, want_in_cands=0, fw_answer=0, fw_wrong=0, fw_correct=0,
             fw_refuse=0)
    # 正解が候補に居て、順方向が誤答した事例の分解
    rows = []
    for want in picks_pop:
        terms = mid_facets(store, want, seed=999)
        if not terms:
            continue
        q = " ".join(terms)
        qset, _h = query_content(q)
        cores = candidates_for_query(store, q, k=K)
        if not cores:
            continue
        n["asked"] += 1
        in_cands = want in cores
        if in_cands:
            n["want_in_cands"] += 1
        shell = build_shell(cores)
        r1 = run_consensus(shell, q, masses=masses)
        if r1.verdict != "ANSWER":
            n["fw_refuse"] += 1
            outcome = "refuse"
        elif r1.core == want:
            n["fw_correct"] += 1
            outcome = "correct"
        else:
            n["fw_wrong"] += 1
            outcome = "wrong"
        if not in_cands:
            continue

        # 腕ごとのエネルギー分解(evaluate と同じ axis_energy)
        def decomp(core):
            axis = next((a for a in AXES
                         if shell.faces[a].get("tip") == core), None)
            if axis is None:
                return None
            facets = facts_on_axis(shell, axis)
            shell_ov = sum(1 for f in facets if norm_words(f) & qset)
            full_ov = sum(1 for w in qset
                          if w in (store.crosses.get(core) or {})
                          or w in norm_words(core))
            return dict(core=core, axis=axis,
                        mass=round(masses.get(core), 3),
                        name_match=len(norm_words(core) & qset),
                        shell_overlap=shell_ov,
                        full_overlap=full_ov,
                        energy=round(axis_energy(shell, axis, qset, cfg,
                                                 masses), 3))
        row = dict(query=q, want=want, outcome=outcome,
                   winner=r1.core if r1.verdict == "ANSWER" else None,
                   want_rank=cores.index(want),
                   want_arm=decomp(want),
                   winner_arm=(decomp(r1.core)
                               if r1.verdict == "ANSWER" and r1.core != want
                               else None))
        rows.append(row)

    # 集計: 正解候補の腕上重なり分布 / 全cross重なり分布
    from collections import Counter
    shell_ov_dist = Counter(r["want_arm"]["shell_overlap"] for r in rows
                            if r["want_arm"])
    full_ov_dist = Counter(r["want_arm"]["full_overlap"] for r in rows
                           if r["want_arm"])
    wrong_rows = [r for r in rows if r["outcome"] == "wrong" and r["winner_arm"]]
    # 誤答勝者のエネルギー源
    winner_src = Counter()
    energy_gap = []
    for r in wrong_rows:
        w, c = r["winner_arm"], r["want_arm"]
        src = []
        if w["name_match"]:
            src.append("name")
        if w["shell_overlap"]:
            src.append("shell_ov")
        if not src:
            src.append("mass_only")
        winner_src["+".join(src)] += 1
        if c:
            energy_gap.append(round(w["energy"] / max(c["energy"], 1e-9), 2))
    # 仮定検査: 正解の全cross重なりで energy を再計算したら勝つか
    would_win = 0
    for r in wrong_rows:
        w, c = r["winner_arm"], r["want_arm"]
        if not c:
            continue
        e_want = c["mass"] * (1.0 + cfg.w_query * c["name_match"]
                              + cfg.w_overlap * c["full_overlap"])
        e_winner_full = w["mass"] * (1.0 + cfg.w_query * w["name_match"]
                                     + cfg.w_overlap * w["full_overlap"])
        if e_want > e_winner_full:
            would_win += 1
    out = dict(
        db=str(DB), counts=n,
        want_in_cands_outcomes=Counter(r["outcome"] for r in rows),
        want_shell_overlap_dist=dict(shell_ov_dist),
        want_full_overlap_dist=dict(full_ov_dist),
        wrong_winner_energy_source=dict(winner_src),
        energy_ratio_winner_over_want=dict(
            median=(sorted(energy_gap)[len(energy_gap) // 2]
                    if energy_gap else None),
            max=max(energy_gap) if energy_gap else None),
        counterfactual_full_overlap_want_wins=dict(
            of_wrong_with_want_in_cands=len([r for r in wrong_rows
                                             if r["want_arm"]]),
            want_would_win=would_win),
        elapsed_s=round(time.time() - t0, 1),
        samples=rows[:12],
    )
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    Path(__file__).with_name("results_diagnose.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
