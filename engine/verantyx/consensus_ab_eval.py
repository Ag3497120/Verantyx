"""Effect measurement for the conception's three tuning axes, on one field.

The claim under test is the designer's: that "cleverness" can be changed by
(1) how finely data is placed into the cross, and (2) the matryoshka —
layered handling of disagreement — and (3, added this session) the
visibility topology. Until now each axis had a fork proving its *mechanism*
on toy shells; this file measures their *effect* on the same store and the
same fixed query set, which is the difference between "it works" and "it
helps".

Two numbers per arm, because one alone can be gamed:

  accuracy   share of askable cores the arm answers with the right core.
             An arm that answers everything scores high here and must be
             caught by the other number.
  honesty    share of nonsense queries the arm correctly refuses (typed
             UNKNOWN instead of an invented core). An arm that refuses
             everything scores high here and is caught by accuracy.

Ground truth is self-derived and therefore honest by construction: the
askable set is cores the store itself contains (query "what is <core>",
correct = that core comes back); the nonsense set is tokens the store has
never seen. No hand labels, no way for the harness author to lean on the
scale.

Deterministic end to end: synthetic corpus, sorted core sampling, no RNG.

Run:  python3 -m verantyx.consensus_ab_eval
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Tuple

from .consensus import ConsensusConfig
from .consensus_store import consensus_over_store
from .cross_store import CrossStore, pour_corpus

N_ASKABLE = 18  # the synthetic corpus's full core set
N_NONSENSE = 20
_NONSENSE = [f"zzqx{i}blorpt" for i in range(N_NONSENSE)]


def _build_stores() -> Tuple[CrossStore, CrossStore]:
    """Fine: the synthetic corpus as-is, one sentence per ingest. Coarse:
    the SAME rows joined pairwise into run-ons before pouring — the same
    words reaching the structure in halved granularity."""
    from .corpus_en import iter_synthetic_rows

    fine, _meta = pour_corpus(source="synthetic", max_rows=2000)

    coarse = CrossStore()
    rows = list(iter_synthetic_rows(2000))
    pairs = [" ".join(rows[i:i + 2]) for i in range(0, len(rows), 2)]
    coarse.scan_cap_stats(iter(pairs))
    for p in pairs:
        coarse.ingest_sentence(p)
    return fine, coarse


def _askable_cores(store: CrossStore, k: int) -> List[str]:
    """Every k-th core with enough facets to be answerable at all, sorted —
    sampling without randomness so reruns are comparable."""
    cores = sorted(c for c in store_cores(store) if len(store.top_facets(c, k=2)) >= 1)
    if not cores:
        return []
    step = max(1, len(cores) // k)
    return cores[::step][:k]


def store_cores(store: CrossStore) -> List[str]:
    # The core mapping is the `crosses` dict (checked against the real
    # class, not guessed — a first draft guessed attribute names and
    # returned nothing, which the harness's own validity check caught).
    return list(store.crosses.keys())


def _run_arm(store: CrossStore, cores: List[str], *,
             matryoshka: bool = False, carry: str = "A",
             geometric: bool = False) -> Dict[str, Any]:
    cfg = ConsensusConfig(geometric_visibility=True) if geometric else None
    kwargs: Dict[str, Any] = {}
    if matryoshka:
        kwargs = {"matryoshka": True, "carry": carry}
    elif cfg is not None:
        kwargs = {"cfg": cfg}

    right = 0
    verdicts: Dict[str, int] = {}
    for core in cores:
        out = consensus_over_store(store, f"what is {core}", **kwargs)
        v = out.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
        if v == "ANSWER" and out.get("core_key", out.get("core")) == core:
            right += 1

    refused = 0
    invented = 0
    for q in _NONSENSE:
        out = consensus_over_store(store, f"what is {q}", **kwargs)
        if out.get("verdict") == "ANSWER":
            invented += 1
        else:
            refused += 1

    n = max(len(cores), 1)
    return {
        "accuracy": round(right / n, 3),
        "honesty": round(refused / max(N_NONSENSE, 1), 3),
        "invented_answers": invented,
        "verdicts": dict(sorted(verdicts.items(), key=lambda kv: -kv[1])),
    }


def _facet_queries(store: CrossStore, cores: List[str]) -> List[Tuple[str, str]]:
    """The hard battery: ask by facets WITHOUT naming the core.

    "what is river" is answerable by lookup and every arm aced it — a
    ceiling, not a result. Asking "what is <facet1> <facet2>" forces real
    disambiguation because the synthetic corpus reuses facet words across
    cores; expected answer = the core those facets came from. Pairs whose
    facets are too generic to identify one core are still included — an arm
    is allowed to answer a DIFFERENT core that also owns both words, so the
    scoring below checks ownership, not string equality with one label."""
    out: List[Tuple[str, str]] = []
    for core in cores:
        facets = [f for f, _ in store.top_facets(core, k=3)]
        if len(facets) >= 2:
            out.append((f"what is {facets[0]} {facets[1]}", core))
    return out


def _run_facet_arm(store: CrossStore, queries: List[Tuple[str, str]], *,
                   matryoshka: bool = False, carry: str = "A",
                   geometric: bool = False) -> Dict[str, Any]:
    cfg = ConsensusConfig(geometric_visibility=True) if geometric else None
    kwargs: Dict[str, Any] = {}
    if matryoshka:
        kwargs = {"matryoshka": True, "carry": carry}
    elif cfg is not None:
        kwargs = {"cfg": cfg}

    exact = 0
    owns = 0
    answered = 0
    verdicts: Dict[str, int] = {}
    for q, expected in queries:
        out = consensus_over_store(store, q, **kwargs)
        v = out.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
        if v != "ANSWER":
            continue
        answered += 1
        got = out.get("core_key", out.get("core"))
        if got == expected:
            exact += 1
        # Ownership: the answered core must actually hold both query facets.
        # Without this, a wrong-but-plausible core counts as a miss even
        # when the question was genuinely ambiguous — and an arm should not
        # be punished for a defensible reading of an ambiguous question.
        qtok = set(q.split()[2:])
        got_facets = {f for f, _ in store.top_facets(str(got), k=6)}
        if qtok <= got_facets:
            owns += 1
    n = max(len(queries), 1)
    return {
        "exact": round(exact / n, 3),
        "defensible": round(owns / n, 3),
        "answer_rate": round(answered / n, 3),
        "verdicts": dict(sorted(verdicts.items(), key=lambda kv: -kv[1])),
    }


def main() -> int:
    print("building stores (fine / coarse placement of the same corpus)…")
    fine, coarse = _build_stores()
    fine_cores = _askable_cores(fine, N_ASKABLE)
    # Placement comparison is only fair on cores BOTH stores contain.
    coarse_set = set(store_cores(coarse))
    shared = [c for c in fine_cores if c in coarse_set]
    print(f"store: fine {fine.n_cores()} cores / coarse {coarse.n_cores()} cores, "
          f"query set {len(fine_cores)} askable ({len(shared)} shared), "
          f"{N_NONSENSE} nonsense\n")
    if len(fine_cores) < 10:
        print("INVALID: too few askable cores — the corpus did not pour as expected")
        return 1

    arms: List[Tuple[str, CrossStore, List[str], Dict[str, Any]]] = [
        ("flat / ring   / fine", fine, fine_cores, {}),
        ("flat / geo    / fine", fine, fine_cores, {"geometric": True}),
        ("matryoshka A  / fine", fine, fine_cores, {"matryoshka": True, "carry": "A"}),
        ("matryoshka B  / fine", fine, fine_cores, {"matryoshka": True, "carry": "B"}),
        ("matryoshka C  / fine", fine, fine_cores, {"matryoshka": True, "carry": "C"}),
        ("flat / ring   / coarse", coarse, shared, {}),
        ("flat / ring   / fine*", fine, shared, {}),  # same shared set, for a fair pair
    ]

    print(f"{'arm':24} {'accuracy':>9} {'honesty':>8} {'invented':>9}  verdicts")
    results: Dict[str, Dict[str, Any]] = {}
    for name, store, cores, kw in arms:
        r = _run_arm(store, cores, **kw)
        results[name] = r
        vs = ", ".join(f"{k}:{v}" for k, v in list(r["verdicts"].items())[:3])
        print(f"{name:24} {r['accuracy']:>9} {r['honesty']:>8} "
              f"{r['invented_answers']:>9}  {vs}")

    print()
    # The harness's own validity checks — the same discipline as every other
    # eval here: a measurement that cannot fail is not a measurement.
    problems: List[str] = []
    if all(r["accuracy"] == 0 for r in results.values()):
        problems.append("every arm scored 0 accuracy — the harness, not the arms")
    if any(r["honesty"] < 1.0 and r["invented_answers"] > N_NONSENSE // 2
           for r in results.values()):
        problems.append("an arm invents answers for most nonsense — check the "
                        "coverage gate before believing any accuracy above")

    fine_pair = results.get("flat / ring   / fine*", {})
    coarse_pair = results.get("flat / ring   / coarse", {})
    if fine_pair and coarse_pair:
        d = round(fine_pair.get("accuracy", 0) - coarse_pair.get("accuracy", 0), 3)
        print(f"placement effect (fine − coarse, same {len(shared)} cores): {d:+}")
    flat = results.get("flat / ring   / fine", {})
    for m in ("A", "B", "C"):
        r = results.get(f"matryoshka {m}  / fine", {})
        if r and flat:
            print(f"matryoshka {m} effect vs flat: "
                  f"accuracy {r['accuracy'] - flat['accuracy']:+.3f}, "
                  f"honesty {r['honesty'] - flat['honesty']:+.3f}")
    geo = results.get("flat / geo    / fine", {})
    if geo and flat:
        print(f"geometry effect (geo − ring): "
              f"accuracy {geo['accuracy'] - flat['accuracy']:+.3f}, "
              f"honesty {geo['honesty'] - flat['honesty']:+.3f}")

    # ── The hard battery: facet-only queries ─────────────────────────────
    fq_fine = _facet_queries(fine, fine_cores)
    fq_shared = [(q, c) for q, c in fq_fine if c in coarse_set]
    print()
    print(f"facet-only battery ({len(fq_fine)} queries, no core name in the query):")
    print(f"{'arm':24} {'exact':>7} {'defensible':>11} {'answer_rate':>12}  verdicts")
    fresults: Dict[str, Dict[str, Any]] = {}
    farms = [
        ("flat / ring   / fine", fine, fq_fine, {}),
        ("flat / geo    / fine", fine, fq_fine, {"geometric": True}),
        ("matryoshka A  / fine", fine, fq_fine, {"matryoshka": True, "carry": "A"}),
        ("matryoshka B  / fine", fine, fq_fine, {"matryoshka": True, "carry": "B"}),
        ("matryoshka C  / fine", fine, fq_fine, {"matryoshka": True, "carry": "C"}),
        ("flat / ring   / coarse", coarse, fq_shared, {}),
        ("flat / ring   / fine*", fine, fq_shared, {}),
    ]
    for name, store, qs, kw in farms:
        r = _run_facet_arm(store, qs, **kw)
        fresults[name] = r
        vs = ", ".join(f"{k}:{v}" for k, v in list(r["verdicts"].items())[:3])
        print(f"{name:24} {r['exact']:>7} {r['defensible']:>11} "
              f"{r['answer_rate']:>12}  {vs}")

    print()
    fflat = fresults.get("flat / ring   / fine", {})
    for m in ("A", "B", "C"):
        r = fresults.get(f"matryoshka {m}  / fine", {})
        if r and fflat:
            print(f"facet: matryoshka {m} vs flat: exact {r['exact']-fflat['exact']:+.3f}, "
                  f"defensible {r['defensible']-fflat['defensible']:+.3f}")
    fgeo = fresults.get("flat / geo    / fine", {})
    if fgeo and fflat:
        print(f"facet: geometry (geo − ring): exact {fgeo['exact']-fflat['exact']:+.3f}, "
              f"defensible {fgeo['defensible']-fflat['defensible']:+.3f}")
    ffp = fresults.get("flat / ring   / fine*", {})
    fcp = fresults.get("flat / ring   / coarse", {})
    if ffp and fcp:
        print(f"facet: placement (fine − coarse, {len(fq_shared)} shared): "
              f"exact {ffp['exact']-fcp['exact']:+.3f}, "
              f"defensible {ffp['defensible']-fcp['defensible']:+.3f}")

    # Ceiling check: a battery every arm aces cannot rank arms. Saying so
    # beats printing zeros as if they were findings.
    if fresults and all(r["exact"] >= 0.99 for r in fresults.values()):
        print()
        print("NOTE: the facet battery ALSO saturated — differences between arms "
              "cannot be measured on this corpus; a richer corpus is the next step.")

    if problems:
        print()
        for p in problems:
            print(f"INVALID: {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
