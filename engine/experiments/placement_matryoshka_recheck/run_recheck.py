# -*- coding: utf-8 -*-
"""事前シミュ × 配置換え再検査 — 捏造率の測定。RECHECK.md が事前登録。

決定論: seed は全て固定。LLM なし。
"""
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.cross import AXES, ShellCross
from verantyx.cross_store import CrossStore
from verantyx.consensus import matryoshka_consensus, run_consensus
from verantyx.consensus_store import _MassView, candidates_for_query
from verantyx.face_roles import FACET_FACES
from verantyx.placement import (choose_for_core, demand_from_queries,
                                facet_document_frequency)

DOMAINS = {
    "clinic": ["dosage", "contraindication", "onset", "interval",
                "monitoring", "titration", "storage", "renewal",
                "eligibility", "referral", "billing", "followup"],
    "shelter": ["capacity", "intake", "curfew", "meals",
                 "laundry", "lockers", "pets", "transport",
                 "childcare", "counseling", "duration", "waitlist"],
}
N_CORES = 6          # ドメインごと
N_CARRY = 8          # 各coreが持つ側面数(12個中)
K_CANDIDATES = 6


def build_store() -> CrossStore:
    store = CrossStore()
    for dom, aspects in DOMAINS.items():
        for i in range(N_CORES):
            core = f"{dom}{chr(97 + i)}"
            rng = random.Random(f"carry:{core}")
            carried = sorted(rng.sample(aspects, N_CARRY))
            for a in carried:
                store.ingest_sentence(f"{core} has {a}")
    return store


def _zipf_pair(dom: str, rng: random.Random):
    aspects = DOMAINS[dom]
    order = sorted(
        aspects,
        key=lambda a: hashlib.sha256(f"{dom}\x00{a}".encode()).hexdigest())
    wts = [1.0 / (i + 1) for i in range(len(order))]
    a = rng.choices(order, weights=wts, k=1)[0]
    b = a
    while b == a:
        b = rng.choices(order, weights=wts, k=1)[0]
    return a, b


def draw_queries(seed: int, n_per_domain: int):
    out = []
    for dom in DOMAINS:
        rng = random.Random(f"{seed}:{dom}")
        for _ in range(n_per_domain):
            a, b = _zipf_pair(dom, rng)
            out.append((f"what has {a} {b}", frozenset((a, b))))
    return out


def build_shell(store, cores, picks_by_core, order):
    """order: cores の並び替え済みリスト → AXES へ割当て。"""
    shell = ShellCross()
    for axis, core in zip(AXES, order):
        shell.faces[axis]["tip"] = core
        shell.reflections[axis] = core
        for face, facet in zip(FACET_FACES, picks_by_core[core]):
            shell.faces[axis][face] = facet
    return shell


def classify(verdict, core, asked_pair, cores, store):
    carriers = [c for c in cores
                if asked_pair <= set(store.crosses.get(c, {}))]
    justified = len(carriers) == 1
    if verdict == "ANSWER":
        if justified and core == carriers[0]:
            return "justified"
        return "manufactured"
    return "missed" if justified else "correct_refusal"


def main():
    store = build_store()
    masses = _MassView(store)
    df = facet_document_frequency(store)

    train = []
    for r in range(3):
        train += [q for q, _p in draw_queries(100 + r, 34)]
    test_raw = draw_queries(999, 200)
    seen_train = set(train)
    test, seen = [], set()
    for q, pair in test_raw:
        if q in seen or q in seen_train:
            continue
        seen.add(q)
        test.append((q, pair))
    asked = demand_from_queries(store, train)

    def picks_for(cores, policy):
        return {c: choose_for_core(
            store, c, policy=policy, df=df, n_cores=store.n_cores(),
            asked=asked if policy == "simulated" else None, weight=0.0)
            for c in cores}

    def picks_ties_reversed(cores, policy):
        """同じスコアで、同点だけを facet 降順で崩した第2の配置。
        score_facets/top_facets は (-score, facet昇順) — ここは
        (-score, facet降順)。同点が無い core では同一の picks になる。"""
        from verantyx.placement import score_facets
        out = {}
        for c in cores:
            if policy == "frequency":
                cross = store.crosses.get(c) or {}
                items = sorted(cross.items(),
                               key=lambda kv: (-kv[1],), reverse=False)
                items = sorted(cross.items(), key=lambda kv: kv[0],
                               reverse=True)
                items = sorted(items, key=lambda kv: -kv[1])
                out[c] = [f for f, _n in items[:len(FACET_FACES)]]
            else:
                scored = score_facets(
                    store, c, df=df, n_cores=store.n_cores(),
                    asked=asked, weight=0.0)
                pairs = sorted(scored, key=lambda sf: sf[1], reverse=True)
                pairs = sorted(pairs, key=lambda sf: -sf[0])
                out[c] = [f for _s, f in pairs[:len(FACET_FACES)]]
        return out

    arms = {a: {"justified": 0, "manufactured": 0,
                "correct_refusal": 0, "missed": 0}
            for a in ("frequency", "simulated", "matryoshka_copy",
                      "recheck1", "recheck2",
                      "recheck_ties", "recheck_ties_freq")}
    h1_identical = True

    for q, pair in test:
        cores = candidates_for_query(store, q, k=K_CANDIDATES)
        if not cores:
            continue
        for policy in ("frequency", "simulated"):
            picks = picks_for(cores, policy)
            shell = build_shell(store, cores, picks, list(cores))
            res = run_consensus(shell, q, masses=masses)
            arms[policy][classify(res.verdict, res.core, pair,
                                  cores, store)] += 1

            # 腕6/7: 同点崩し換え再検査 — ANSWER は、同点を逆向きに崩した
            # 第2の配置でも同じ core で ANSWER のときだけ残る。
            tie_arm = ("recheck_ties" if policy == "simulated"
                       else "recheck_ties_freq")
            if res.verdict != "ANSWER":
                v2, c2 = res.verdict, res.core
            else:
                p2 = picks_ties_reversed(cores, policy)
                s2 = build_shell(store, cores, p2, list(cores))
                r2 = run_consensus(s2, q, masses=masses)
                if (r2.verdict, r2.core) == (res.verdict, res.core):
                    v2, c2 = res.verdict, res.core
                else:
                    v2, c2 = "AMBIGUOUS_PLACEMENT", None
            arms[tie_arm][classify(v2, c2, pair, cores, store)] += 1

            if policy != "simulated":
                continue

            # 腕3: マトリョーシカ写し(既存実装そのまま)
            shell3 = build_shell(store, cores, picks, list(cores))
            m = matryoshka_consensus(shell3, q, carry="A", n_layers=3,
                                     masses=masses)
            arms["matryoshka_copy"][classify(m["verdict"], m["core"], pair,
                                             cores, store)] += 1
            if (m["verdict"], m["core"]) != (res.verdict, res.core):
                h1_identical = False

            # 腕4/5: 配置換え再検査。ANSWER は別配置でも同じ core で
            # ANSWER のときだけ残る。
            def rerun(order):
                s = build_shell(store, cores, picks, order)
                r = run_consensus(s, q, masses=masses)
                return r.verdict, r.core

            rot = list(cores)[1:] + list(cores)[:1]
            rev = list(reversed(list(cores)))
            base = (res.verdict, res.core)
            for arm, orders in (("recheck1", [rot]),
                                ("recheck2", [rot, rev])):
                if base[0] != "ANSWER":
                    v, c = base       # 再検査は ANSWER だけを検査する
                else:
                    others = [rerun(o) for o in orders]
                    if all(x == base for x in others):
                        v, c = base
                    else:
                        v, c = "AMBIGUOUS_ARRANGEMENT", None
                arms[arm][classify(v, c, pair, cores, store)] += 1

    out = {"n_test": len(test), "h1_matryoshka_identical": h1_identical,
           "arms": {}}
    for arm, cells in arms.items():
        answers = cells["justified"] + cells["manufactured"]
        rate = (cells["manufactured"] / answers) if answers else None
        # 捏造率の分母は dd22760 と同じ「ANSWER のうち」…ではなく
        # docs は 21/68=30.9% → 全問中。両方出す。
        out["arms"][arm] = {
            **cells,
            "manufacture_rate_of_all": round(
                cells["manufactured"] / len(test), 4),
            "manufacture_rate_of_answers": (round(rate, 4)
                                            if rate is not None else None),
        }
    print(json.dumps(out, indent=2))
    dst = Path(__file__).with_name("results_recheck.json")
    dst.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
