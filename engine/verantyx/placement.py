"""Placement simulation — decide what goes on the faces BEFORE shipping.

An arm has five faces: one core and four facets. A core in a real store
usually has more facets than that (18.5% of the cores in the reference store
have more than four; the largest has 23,714). So every arm is a *choice* of
four, and until now the choice was made by a single line:

    store.top_facets(core, k=4)          # the four most frequent

Frequency is a rule about the corpus, not about the question. Two consequences
were measured on the reference store (889,144 cores) before this module
existed:

  * across 120 queries, changing which four facets were placed changed the
    answer text 120/120 times and the verdict 0/120 times — placement decides
    WHAT COMES OUT, not whether anything comes out
  * frequency ordering puts the same generic word on every competing arm.
    In a six-core probe every single arm led with the same facet, because
    the most frequent facet of near-neighbours is near-always shared

The second one is the defect. An arm whose four faces are all shared with its
five competitors distinguishes nothing, and the answer it composes is true but
uninformative — the reading equivalent of answering "what is a lemon?" with
"it is a thing that is bright".

So this module does what the conception called 粒度の事前シミュレーション:
compute the anticipated answer distribution once, at build time, and assign
facts to nodes accordingly. The result is baked into the store as data, and
the engine that reads it stays deterministic — the same store answers the
same question the same way forever. This is a build-time stage, not a
learning loop at query time; nothing here runs when a question is asked.

Two policies, both deterministic:

  frequency  the historical rule, kept so its behaviour remains reachable
             and so any comparison has an honest baseline
  simulated  expected demand × discrimination, described below

`simulated` scores a candidate facet f for core c as

    demand(c, f)  =  count(c, f) / mass(c)        how often the fact co-occurs
    discrim(f)    =  log(N / df(f))               how few cores also carry it
    score         =  demand * (1 + w * discrim)

df(f) is the number of cores carrying f, so a facet on every core scores
log(1)=0 discrimination and survives on demand alone; a facet unique to this
core gets the full log(N). This is TF-IDF, and saying so is more useful than
inventing a name for it: the novelty here is not the formula, it is that the
formula is evaluated once before shipping and frozen into the geometry.

When the operator supplies the queries the system will actually be asked,
demand is measured against those instead — a facet that covers a term someone
asks for is worth more than a facet that is merely common. That is the part
that makes this a *simulation of the answer distribution* rather than a
re-weighting of the corpus.

Nothing here writes to the shipped grammar or invents a fact. Placement can
only reorder and select among facts the store already holds, which bounds the
damage a bad policy can do: the worst outcome is an uninformative true answer,
never a false one.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .cross_store import CrossStore
from .face_roles import FACET_FACES

#: Faces available for facts on one arm.
N_FACES = len(FACET_FACES)

#: Weight on the discrimination term. DEFAULT ZERO, because it was measured
#: and it did not help. `--sweep` over 200 held-out questions on the reference
#: store:
#:
#:     w=0.00   uncovered 0.700      w=1.00   uncovered 0.715
#:     w=0.25   uncovered 0.715      w=2.00   uncovered 0.720
#:     w=0.50   uncovered 0.715      (frequency baseline 0.805)
#:
#: So the entire gain comes from observed demand, and discrimination is a
#: small tax on it. That is not a refutation of the idea: discrimination
#: exists to stop competing arms leading with the same facet, and on this
#: store retrieval fills exactly one arm on 300 of 300 questions, so the
#: benefit it targets cannot occur while its cost still can. The parameter
#: stays, at zero, with the measurement attached — if retrieval is ever
#: changed to fill several arms, re-run the sweep before assuming it helps.
DISCRIM_WEIGHT = 0.0

POLICIES = ("frequency", "simulated")


# ---------------------------------------------------------------------------
# corpus statistics
# ---------------------------------------------------------------------------

def facet_document_frequency(store: CrossStore) -> Dict[str, int]:
    """facet → number of cores that carry it.

    One pass over the whole store. On the reference store this is ~9.8M
    increments and takes a few seconds; it is build-time work by design.
    """
    df: Counter = Counter()
    for cross in store.crosses.values():
        df.update(cross.keys())
    return dict(df)


def demand_from_queries(
    store: CrossStore,
    queries: Sequence[str],
) -> Dict[str, Dict[str, int]]:
    """core → facet → how many anticipated questions asked for it there.

    Conditional on the core, not flat over tokens. A flat map was the first
    version and it cannot express the thing being modelled: "outage" is a
    common word, but whether someone asking about a particular town wants to
    hear about outages is a fact about that town's arm, and a global count
    averages exactly that away.

    The core of a question is whatever retrieval would actually pick for it,
    so this reads the same path the engine will — a demand model built on a
    different notion of "which topic is this about" would optimise faces the
    query never lands on.

    EVERY retrieved core is credited, not just the top one. Crediting only
    the first was the first version, and it manufactured confidence: given
    "what has dosage onset" against six clinics that all have dosage and
    onset, the whole question's demand landed on whichever clinic ranked
    first, that clinic alone got those two facts placed, its arm out-scored
    five identical rivals, and a question that is genuinely undecidable came
    back as a confident ANSWER naming one clinic. The frequency rule it
    replaced said AMBIGUOUS, correctly.

    That is the worst failure available to this module — a correct refusal
    turned into a wrong answer — and it comes from the demand model, not the
    scorer. When a descriptive question legitimately matches six cores, all
    six of them are what someone asking that question wants to hear about.
    Pinned by PLACEMENT_CANNOT_MANUFACTURE_CONFIDENCE.

    A question is credited only for the tokens that are real facets of that
    core. Terms it does not have are not placement's problem; they are the
    vocabulary queue's.
    """
    from .consensus_store import MAX_ARMS, candidates_for_query
    from .lex_filters import norm_words

    want: Dict[str, Counter] = {}
    for q in queries:
        cores = candidates_for_query(store, q, k=MAX_ARMS)
        if not cores:
            continue
        toks: set = set()
        for raw in str(q).split():
            toks |= norm_words(raw.casefold().strip())
        for core in cores:
            cross = store.crosses.get(core) or {}
            hits = [t for t in toks if t in cross]
            if hits:
                want.setdefault(core, Counter()).update(hits)
    return {c: dict(v) for c, v in want.items()}


# ---------------------------------------------------------------------------
# the policies
# ---------------------------------------------------------------------------

def score_facets(
    store: CrossStore,
    core: str,
    *,
    df: Dict[str, int],
    n_cores: int,
    asked: Optional[Dict[str, Dict[str, int]]] = None,
    weight: float = DISCRIM_WEIGHT,
) -> List[Tuple[float, str]]:
    """(score, facet) for every facet of ``core``, best first.

    Ties break lexicographically on the facet, so the result is a total order
    and two runs over the same store cannot disagree.
    """
    cross = store.crosses.get(core) or {}
    if not cross:
        return []
    mass = max(1.0, float(sum(cross.values())))
    here = (asked or {}).get(core) or {}
    n_asked = float(sum(here.values()))

    out: List[Tuple[float, str]] = []
    for facet, cnt in cross.items():
        demand = cnt / mass
        if n_asked:
            # An anticipated question that named this fact ON THIS CORE is
            # direct evidence of demand; corpus co-occurrence is the prior it
            # updates. Observed demand dominates, because the whole point is
            # that what people ask beats what the corpus repeats — but the
            # prior survives so a core with two logged questions does not
            # throw away everything else it knows.
            demand = 0.25 * demand + 0.75 * (here.get(facet, 0) / n_asked)
        d = max(1, df.get(facet, 1))
        discrim = math.log(max(1.0, n_cores / d))
        out.append((demand * (1.0 + weight * discrim), facet))
    # -score first, then facet ascending — a stable, total, reproducible order
    out.sort(key=lambda sf: (-sf[0], sf[1]))
    return out


def choose_for_core(
    store: CrossStore,
    core: str,
    *,
    policy: str = "simulated",
    df: Optional[Dict[str, int]] = None,
    n_cores: int = 0,
    asked: Optional[Dict[str, Dict[str, int]]] = None,
    weight: float = DISCRIM_WEIGHT,
    k: int = N_FACES,
) -> List[str]:
    """The facets that should occupy this core's faces, in read order."""
    if policy == "frequency":
        return [f for f, _c in store.top_facets(core, k=k)]
    if policy != "simulated":
        raise ValueError(f"unknown placement policy {policy!r}; expected {POLICIES}")
    if df is None:
        df = facet_document_frequency(store)
        n_cores = store.n_cores()
    scored = score_facets(
        store, core, df=df, n_cores=n_cores or store.n_cores(),
        asked=asked, weight=weight,
    )
    return [f for _s, f in scored[:k]]


def simulate(
    store: CrossStore,
    *,
    policy: str = "simulated",
    queries: Optional[Sequence[str]] = None,
    cores: Optional[Iterable[str]] = None,
    weight: float = DISCRIM_WEIGHT,
    only_contested: bool = True,
) -> Dict[str, List[str]]:
    """Compute the placement map for a store. Build-time; not cheap.

    ``only_contested`` skips cores with at most ``N_FACES`` facets, where
    every facet is placed regardless of policy and an entry would be pure
    storage cost. On the reference store that is 81.5% of the cores.
    """
    df = facet_document_frequency(store)
    n_cores = store.n_cores()
    asked = demand_from_queries(store, queries) if queries else None
    keys = list(cores) if cores is not None else list(store.crosses.keys())

    placement: Dict[str, List[str]] = {}
    for core in keys:
        cross = store.crosses.get(core) or {}
        if only_contested and len(cross) <= N_FACES:
            continue
        chosen = choose_for_core(
            store, core, policy=policy, df=df, n_cores=n_cores,
            asked=asked, weight=weight,
        )
        if chosen:
            placement[core] = chosen
    return placement


# ---------------------------------------------------------------------------
# measurement — a policy that is not measured is a preference
# ---------------------------------------------------------------------------

def distinctness(
    store: CrossStore,
    cores: Sequence[str],
    placement: Optional[Dict[str, List[str]]] = None,
    *,
    policy_fallback: str = "frequency",
) -> Dict[str, Any]:
    """How distinguishable are the arms of one shell?

    The number that matters is ``lead_collisions``: how many arms lead with a
    facet another arm also leads with. That is the observed defect stated as
    a measurement — six arms leading with the same word is five collisions.
    """
    arms: List[List[str]] = []
    for c in cores:
        if placement and c in placement:
            arms.append(list(placement[c])[:N_FACES])
        else:
            arms.append([f for f, _ in store.top_facets(c, k=N_FACES)])
    leads = [a[0] for a in arms if a]
    lead_counts = Counter(leads)
    collisions = sum(n - 1 for n in lead_counts.values() if n > 1)

    seen: Counter = Counter()
    for a in arms:
        seen.update(set(a))
    total = sum(seen.values())
    shared = sum(n for n in seen.values() if n > 1)
    return {
        "n_arms": len(arms),
        "lead_collisions": collisions,
        "distinct_leads": len(lead_counts),
        "shared_facet_frac": round(shared / total, 4) if total else 0.0,
        "arms": {c: a for c, a in zip(cores, arms)},
    }


def compare(
    store: CrossStore,
    queries: Sequence[str],
    *,
    weight: float = DISCRIM_WEIGHT,
    k: int = 6,
    train: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Run both policies over the same queries and report the difference.

    ``train`` is the anticipated-question set the placement is computed FROM;
    ``queries`` is what it is judged ON. They must be different, or this
    measures memorisation: the simulated policy takes demand straight from
    the questions it is shown, so scoring it on those same questions is
    guaranteed to flatter it. Passing train=None makes the comparison
    demand-free — corpus discrimination only — which is the fair fallback
    when no operator traffic exists.

    Reports verdict counts as well as distinctness, because a placement that
    made answers distinctive by breaking them would be worse than the rule it
    replaced, and the only way to know is to look.
    """
    from .consensus import run_consensus
    from .consensus_store import _MassView, candidates_for_query
    from .cross import AXES, ShellCross

    df = facet_document_frequency(store)
    n_cores = store.n_cores()
    asked = demand_from_queries(store, train) if train else None
    masses = _MassView(store)

    def shell_for(cores: List[str], policy: str) -> ShellCross:
        sh = ShellCross()
        for axis, core in zip(AXES, cores):
            sh.faces[axis]["tip"] = core
            sh.reflections[axis] = core
            picks = choose_for_core(
                store, core, policy=policy, df=df, n_cores=n_cores,
                asked=asked if policy == "simulated" else None, weight=weight,
            )
            for face, facet in zip(FACET_FACES, picks):
                sh.faces[axis][face] = facet
        return sh

    rows: List[Dict[str, Any]] = []
    agg: Dict[str, Dict[str, Any]] = {
        p: {"verdicts": Counter(), "collisions": 0, "uncovered": 0, "shells": 0}
        for p in POLICIES
    }
    changed_text = 0
    arms_hist: Counter = Counter()
    for q in queries:
        cores = candidates_for_query(store, q, k=k)
        if not cores:
            continue
        arms_hist[len(cores)] += 1
        row: Dict[str, Any] = {"query": q, "cores": cores}
        for policy in POLICIES:
            sh = shell_for(cores, policy)
            res = run_consensus(sh, q, masses=masses)
            d = distinctness(
                store, cores,
                {c: choose_for_core(
                    store, c, policy=policy, df=df, n_cores=n_cores,
                    asked=asked if policy == "simulated" else None,
                    weight=weight) for c in cores},
            )
            a = agg[policy]
            a["verdicts"][res.verdict] += 1
            a["collisions"] += d["lead_collisions"]
            a["shells"] += 1
            # Terms the question asked about that the answer did not mention.
            from .consensus import query_content
            qset, _h = query_content(q)
            covered = set(str(res.text or "").split()) | {str(res.core or "")}
            a["uncovered"] += len(qset - covered)
            row[policy] = {"verdict": res.verdict, "core": res.core,
                           "text": res.text, "collisions": d["lead_collisions"]}
        if row["frequency"]["text"] != row["simulated"]["text"]:
            changed_text += 1
        rows.append(row)

    n = max(1, len(rows))
    summary = {
        p: {
            "verdicts": dict(agg[p]["verdicts"]),
            "answer_rate": round(agg[p]["verdicts"].get("ANSWER", 0) / n, 4),
            "mean_lead_collisions": round(agg[p]["collisions"] / n, 4),
            "mean_uncovered_terms": round(agg[p]["uncovered"] / n, 4),
        }
        for p in POLICIES
    }
    return {
        "n_queries": len(rows),
        "answers_that_changed": changed_text,
        # How many arms retrieval actually fills. Reported because it bounds
        # what placement can do: with one arm there is nothing for the six
        # cross-sections to disagree about, so collisions are structurally
        # zero and coverage is the only lever. On the reference store this
        # came back {1: 99.3%}, which is a fact about `candidates_for_query`,
        # not about the geometry.
        "arms_per_query": dict(sorted(arms_hist.items())),
        "mean_arms": round(
            sum(k_ * v for k_, v in arms_hist.items()) / max(1, sum(arms_hist.values())), 3),
        "summary": summary,
        "delta": {
            "answer_rate": round(
                summary["simulated"]["answer_rate"]
                - summary["frequency"]["answer_rate"], 4),
            "lead_collisions": round(
                summary["simulated"]["mean_lead_collisions"]
                - summary["frequency"]["mean_lead_collisions"], 4),
            "uncovered_terms": round(
                summary["simulated"]["mean_uncovered_terms"]
                - summary["frequency"]["mean_uncovered_terms"], 4),
        },
        "rows": rows[:20],
    }


def sweep_weight(
    store: CrossStore,
    queries: Sequence[str],
    weights: Sequence[float] = (0.0, 0.25, 0.5, 1.0, 2.0),
    *,
    train: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """The discrimination weight, measured rather than asserted.

    w=0 is the demand-only policy, which is close to but not identical with
    frequency (it normalises by mass), so the sweep also shows how much of any
    gain comes from discrimination as opposed to normalisation.
    """
    out = []
    for w in weights:
        c = compare(store, queries, weight=w, train=train)
        out.append({
            "weight": w,
            "answer_rate": c["summary"]["simulated"]["answer_rate"],
            "mean_lead_collisions": c["summary"]["simulated"]["mean_lead_collisions"],
            "mean_uncovered_terms": c["summary"]["simulated"]["mean_uncovered_terms"],
        })
    base = compare(store, queries, train=train)
    return {"baseline_frequency": base["summary"]["frequency"],
            "mean_arms": base["mean_arms"], "sweep": out}


# ---------------------------------------------------------------------------
# the gate — a placement is only kept if it is measured not to cost anything
# ---------------------------------------------------------------------------

def accept(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """Should the simulated placement be baked in?

    Same shape as the self-evolve gate: one thing that must not get worse,
    and one thing that must actually get better.

      * the answer rate must not fall — a more distinctive answer that is
        also a refusal is not an improvement
      * uncovered query terms must not rise
      * and then SOMETHING must improve: fewer uncovered terms, or fewer
        lead collisions

    The two improvement routes are not alternatives to taste; they are the
    one-arm and multi-arm cases. With a single arm — 99.3% of queries on the
    reference store — collisions cannot exist, so requiring them to fall
    would reject every placement on a technicality. With several arms the
    collision count is the defect that motivated this module. Requiring
    either lets one gate cover both without letting a no-op pass.
    """
    d = comparison["delta"]
    hard: List[str] = []
    if d["answer_rate"] < 0:
        hard.append(f"answer_rate fell by {-d['answer_rate']:.4f}")
    if d["uncovered_terms"] > 0:
        hard.append(f"uncovered query terms rose by {d['uncovered_terms']:.4f}")
    improved = d["uncovered_terms"] < 0 or d["lead_collisions"] < 0
    if not improved:
        hard.append(
            "nothing improved: uncovered terms "
            f"{d['uncovered_terms']:+.4f}, lead collisions "
            f"{d['lead_collisions']:+.4f}")
    won = []
    if d["uncovered_terms"] < 0:
        won.append(f"uncovered terms {d['uncovered_terms']:+.4f}")
    if d["lead_collisions"] < 0:
        won.append(f"lead collisions {d['lead_collisions']:+.4f}")
    return {
        "verdict": "ACCEPTED" if not hard else "REJECTED",
        "reasons": hard or [f"answer rate held; " + ", ".join(won)],
        "delta": d,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

#: How the synthetic questions choose which facet to ask about. This is the
#: single assumption the whole pre-simulation rests on, so it is a parameter
#: with two named settings rather than a constant buried in a function.
#:
#:   uniform  every facet of a core is equally likely to be asked about.
#:            Under this assumption no query-independent placement can beat
#:            any other: placing 4 of N facets covers the asked one with
#:            probability 4/N whatever the policy. Measured on the reference
#:            store, and it came out exactly that way.
#:   zipf     each core has a stable preference order over its facets, and
#:            questions concentrate on the front of it. This is what a real
#:            deployment looks like — a water utility asks about outages, not
#:            uniformly about every noun in its own bulletins — and it is the
#:            only condition under which pre-simulation has anything to learn.
DEMAND_MODELS = ("uniform", "zipf")


def derive_queries(
    store: CrossStore,
    n: int,
    *,
    seed: int = 0,
    demand: str = "zipf",
) -> List[str]:
    """Questions synthesised from the store, for when no traffic exists.

    Each is "what is CORE FACET". Which facet gets asked about is decided by
    ``demand`` (see DEMAND_MODELS), and that choice decides the experiment —
    which is why both settings are kept and both are reported.

    The per-core preference order under ``zipf`` is derived from a hash of
    the core name, NOT from corpus frequency. Deriving it from frequency
    would hand the baseline the answer key; deriving it from rarity would
    hand it to the challenger. A hash is arbitrary, stable, and independent
    of both policies, which is what a fair held-out split needs.

    This is a stand-in, and it is labelled as one everywhere it is reported.
    Real operator questions beat it and should be passed with --queries.
    """
    import hashlib
    import random

    if demand not in DEMAND_MODELS:
        raise ValueError(f"unknown demand model {demand!r}; expected {DEMAND_MODELS}")
    rng = random.Random(seed)
    contested = sorted(
        c for c, f in store.crosses.items()
        if len(f) > N_FACES and c.isalpha() and store.mass(c) >= 5
    )
    if not contested:
        return []
    # WHICH cores are asked about is fixed across seeds; only which facet is
    # asked about varies. Otherwise two draws are two different populations
    # and no train/test comparison between them means anything.
    picks = (contested if len(contested) <= n
             else random.Random(0).sample(contested, n))
    out: List[str] = []
    for c in sorted(picks):
        facets = sorted(f for f in store.crosses[c] if f.isalpha())
        if not facets:
            continue
        if demand == "uniform":
            out.append(f"what is {c} {rng.choice(facets)}")
            continue
        # Stable arbitrary preference order, then a 1/rank draw over it.
        order = sorted(
            facets,
            key=lambda f: hashlib.sha256(f"{c}\x00{f}".encode()).hexdigest(),
        )
        wts = [1.0 / (i + 1) for i in range(len(order))]
        out.append(f"what is {c} {rng.choices(order, weights=wts, k=1)[0]}")
    return out


def derive_split(
    store: CrossStore, n: int, *, demand: str = "zipf", reps: int = 3,
) -> Tuple[List[str], List[str]]:
    """(train, test) drawn from the same demand model over the SAME cores.

    Splitting one query per core into two halves — the first thing tried —
    puts disjoint cores in train and test, so a placement learned for one
    half is evaluated on cores it never saw. That measures nothing except
    that facts about `apple` do not predict facts about `zebra`, and it is
    not what pre-simulation claims. What it claims is that PAST questions
    about a body of knowledge predict FUTURE questions about the same body,
    so train and test must be independent draws over one core set.

    ``reps`` is how many training questions are seen per core. One draw from
    a 1/rank distribution is a weak signal; three is still modest and keeps
    the claim honest about how little traffic this needs.
    """
    train: List[str] = []
    for r in range(reps):
        train += derive_queries(store, n, seed=100 + r, demand=demand)
    test = derive_queries(store, n, seed=999, demand=demand)
    return train, test


def _load_queries(
    path: Optional[str], store: CrossStore, n: int, demand: str = "zipf",
) -> List[str]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
    return derive_queries(store, n, demand=demand)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Simulate face placement before shipping a store.")
    ap.add_argument("store")
    ap.add_argument("--queries", help="one anticipated question per line")
    ap.add_argument("--n-queries", type=int, default=120)
    ap.add_argument("--demand", choices=DEMAND_MODELS, default="zipf",
                    help="how synthetic questions choose a facet; ignored "
                         "when --queries supplies real ones")
    ap.add_argument("--weight", type=float, default=DISCRIM_WEIGHT)
    ap.add_argument("--sweep", action="store_true",
                    help="measure the discrimination weight instead of using it")
    ap.add_argument("--write", metavar="OUT",
                    help="bake the placement into a copy of the store")
    a = ap.parse_args(argv)

    store = CrossStore.load(Path(a.store))
    # Held-out split. Placement is computed from `train` and judged on `test`,
    # because the simulated policy reads demand off the questions it is given
    # and would otherwise be graded on its own answer key.
    if a.queries:
        queries = _load_queries(a.queries, store, a.n_queries)
        cut = len(queries) // 2
        train, test = queries[:cut], queries[cut:]
        if not train or not test:
            train, test = [], queries
    else:
        train, test = derive_split(store, a.n_queries, demand=a.demand)

    if a.sweep:
        print(json.dumps(sweep_weight(store, test, train=train),
                         ensure_ascii=False, indent=2))
        return 0

    comparison = compare(store, test, weight=a.weight, train=train)
    gate = accept(comparison)
    report = {
        "verdict": gate["verdict"],
        "n_train": len(train),
        "n_test": comparison["n_queries"],
        "queries_from": a.queries or
                        f"derived from the store, demand={a.demand} "
                        f"(not real traffic)",
        "arms_per_query": comparison["arms_per_query"],
        "mean_arms": comparison["mean_arms"],
        "summary": comparison["summary"],
        "delta": comparison["delta"],
        "answers_that_changed": comparison["answers_that_changed"],
        "reasons": gate["reasons"],
    }

    if a.write:
        if gate["verdict"] != "ACCEPTED":
            report["wrote"] = None
            report["note"] = "not written: the gate rejected this placement"
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        # Built from `train` only — the same set the accepted delta was
        # measured against on held-out questions. Rebuilding from train+test
        # here would ship a placement no measurement covers.
        placement = simulate(store, queries=train, weight=a.weight)
        store.placement = placement
        store.placement_meta = {
            "policy": "simulated",
            "weight": a.weight,
            "n_cores": len(placement),
            "queries": a.queries or "derived",
            "n_train": len(train),
            "measured_on_heldout": comparison["n_queries"],
            "delta": comparison["delta"],
        }
        store.save(Path(a.write))
        report["wrote"] = a.write
        report["placed_cores"] = len(placement)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if gate["verdict"] == "ACCEPTED" else 1


if __name__ == "__main__":
    sys.exit(main())
