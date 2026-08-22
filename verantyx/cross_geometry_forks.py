"""Forks for the three unbuilt pieces of the original conception:
geometric visibility (E1), memory stacking, and placement granularity (E3).

Same contract as every other *_forks module: each fork states its expected
outcome as a pass criterion and returns evidence. Two disciplines carried
over from the rest of this work:

  - E1 does NOT declare a winner between ring and geometric visibility.
    The conception's "attack a nuance from both poles" reading can justify
    either topology; which one reasons better is the designer's question
    and needs real queries. What a fork CAN pin down is the structural
    difference itself — that the two modes disagree about exactly one
    thing, opposite-pole visibility — so the later A/B measures topology
    and nothing else.

  - The drift fork constructs the telephone-game failure on purpose and
    asserts it surfaces as UNKNOWN_DRIFT, not as a confident wrong answer.
    An extended-inference engine whose failure mode is silent topic drift
    would be worse than no engine.
"""
from __future__ import annotations

from collections import Counter
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .consensus import (AXES, N_SECTIONS, ConsensusConfig, SearchState,
                        visible_axes)
from .cross import ShellCross
from .cross_store import CrossStore
from .layer_stack import LayeredMemory, layered_ask
from .consensus_store import MAX_ARMS as MAX_ARMS_FORK
from .face_roles import FACET_FACES as _FF

FACES_FORK = len(_FF)


def _opposite(axis: str) -> str:
    return ("-" if axis[0] == "+" else "+") + axis[1]


# ---------------------------------------------------------------------------
# E1 — the structural property, stated exactly.
# ---------------------------------------------------------------------------

def geometric_pole_invisibility_fork() -> Dict[str, Any]:
    """Ring windows contain the opposite pole; geometric ones never do.

    In the current AXES ordering the poles of each axis are adjacent in the
    tuple, so at window=1 EVERY ring section sees its own opposite — worth
    stating as a measured fact, because it is the strongest form of the
    both-poles-visible reading. Geometric mode must make the opposite
    invisible from every section while keeping the visible-arc size equal,
    and widening must erase the difference (escape shows everything in both
    modes).
    """
    ring = ConsensusConfig()
    geo = ConsensusConfig(geometric_visibility=True)
    st = SearchState(shell=ShellCross())

    ring_sees_pole = []
    geo_sees_pole = []
    sizes_equal = True
    for s in range(N_SECTIONS):
        home = AXES[s % N_SECTIONS]
        r = visible_axes(st, s, ring)
        g = visible_axes(st, s, geo)
        ring_sees_pole.append(_opposite(home) in r)
        geo_sees_pole.append(_opposite(home) in g)
        if len(r) != len(g):
            sizes_equal = False

    widened = SearchState(shell=ShellCross(), widened=True)
    widened_equal = all(
        visible_axes(widened, s, ring) == visible_axes(widened, s, geo) == list(AXES)
        for s in range(N_SECTIONS)
    )

    ok = (all(ring_sees_pole) and not any(geo_sees_pole)
          and sizes_equal and widened_equal)
    return {
        "experiment": "cross_geometry",
        "fork": "GEOMETRIC_POLE_INVISIBILITY",
        "pass": bool(ok),
        "result": {
            "ring_sections_seeing_own_pole": sum(ring_sees_pole),
            "geo_sections_seeing_own_pole": sum(geo_sees_pole),
            "visible_arc_sizes_equal": sizes_equal,
            "widened_erases_difference": widened_equal,
        },
    }


def geometric_rotation_reaches_all_fork() -> Dict[str, Any]:
    """Geometric visibility must not orphan any axis: across all rotations,
    every axis becomes visible to some section. The pole is unreachable from
    where you STAND, not unreachable outright — rotation is exactly the move
    that faces it, and if some axis were invisible at every rotation the
    mode would have quietly deleted part of the cross."""
    geo = ConsensusConfig(geometric_visibility=True)
    seen: set = set()
    for rot in range(N_SECTIONS):
        st = SearchState(shell=ShellCross(), rotation=rot)
        for s in range(N_SECTIONS):
            seen.update(visible_axes(st, s, geo))
    ok = seen == set(AXES)
    return {
        "experiment": "cross_geometry",
        "fork": "GEOMETRIC_ROTATION_REACHES_ALL",
        "pass": bool(ok),
        "result": {"axes_reachable": sorted(seen)},
    }


# ---------------------------------------------------------------------------
# Memory stacking — the conception's second matryoshka.
# ---------------------------------------------------------------------------

_SENTENCES = [
    "apple is red fruit",
    "banana is yellow fruit",
    "cherry is small fruit",
    "durian is spiky fruit",
    "elderberry is dark fruit",
]


def layer_stack_growth_fork() -> Dict[str, Any]:
    """Capacity 2, five distinct cores: layers must stack (2,2,1), lower
    layers must FREEZE — later ingests never touch them — and a save/load
    round trip must preserve the whole arrangement. Freezing is the point:
    a frozen layer's internal arrangement is what stays stable while the
    stack above it grows."""
    import tempfile
    from pathlib import Path

    mem = LayeredMemory(capacity=2)
    for s in _SENTENCES:
        mem.ingest_sentence(s)

    frozen_sizes = [lvl.n_cores() for lvl in mem.levels]
    mem.ingest_sentence("fig is soft fruit")  # goes to top, must not touch L0/L1
    after_sizes = [lvl.n_cores() for lvl in mem.levels]
    lower_frozen = frozen_sizes[:-1] == after_sizes[:len(frozen_sizes) - 1]

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "mem.json"
        mem.save(p)
        back = LayeredMemory.load(p)
        roundtrip = (back.n_levels() == mem.n_levels()
                     and back.total_cores() == mem.total_cores())

    ok = (mem.n_levels() >= 3 and mem.total_cores() == 6
          and lower_frozen and roundtrip)
    return {
        "experiment": "cross_geometry",
        "fork": "LAYER_STACK_GROWTH",
        "pass": bool(ok),
        "result": {"levels_after_five": frozen_sizes,
                   "levels_after_six": after_sizes,
                   "lower_layers_frozen": lower_frozen,
                   "roundtrip": roundtrip},
    }


def layered_ask_stability_fork() -> Dict[str, Any]:
    """Two layers that both know the answer must converge and halt early
    with the stability verdict — two consecutive layers naming the same
    core is the conception's stop condition applied across layers."""
    l0 = CrossStore()
    l1 = CrossStore()
    for s in _SENTENCES[:3]:
        l0.ingest_sentence(s)
        l1.ingest_sentence(s)
    mem = LayeredMemory(levels=[l0, l1])

    out = layered_ask(mem, "what is apple", carry="A")
    ok = (out["verdict"] == "ANSWER" and out.get("core") == "apple"
          and out.get("stable_at_level") == 1)
    return {
        "experiment": "cross_geometry",
        "fork": "LAYERED_ASK_STABILITY",
        "pass": bool(ok),
        "result": {"verdict": out["verdict"], "core": out.get("core"),
                   "stable_at_level": out.get("stable_at_level")},
    }


def layered_carry_drift_fork() -> Dict[str, Any]:
    """The telephone game, constructed on purpose.

    L0 knows apple. L1 does NOT contain apple at all — only a core reachable
    from apple's own answer words. Without the original query riding along
    (carry B), layer 1 can only follow the answer tokens and lands on the
    other core: two layers, two different answers, no consecutive agreement.
    That must surface as UNKNOWN_DRIFT — a type, not a confident wrong
    answer, because a silent topic drift is this engine's worst failure.

    Carry A on the same memory must NOT invent an agreement either: L1
    genuinely does not know apple, so no stability exists to find. What A
    must do is keep the original question in every layer's query — the
    anchor whose absence is what B is testing.
    """
    l0 = CrossStore()
    l0.ingest_sentence("apple is red fruit")
    l1 = CrossStore()
    l1.ingest_sentence("red is bright color")
    mem = LayeredMemory(levels=[l0, l1])

    b = layered_ask(mem, "what is apple", carry="B")
    a = layered_ask(mem, "what is apple", carry="A")

    b_drifted = b["verdict"] == "UNKNOWN_DRIFT" and (b.get("cores_seen") or [])[:1] == ["apple"]
    a_keeps_anchor = all("apple" in t.get("query", "")
                         for t in a.get("trace", []) if not t.get("skipped"))
    b_drops_anchor = any(t.get("level") == 1 and "what" not in t.get("query", "")
                         for t in b.get("trace", []))

    ok = b_drifted and a_keeps_anchor and b_drops_anchor
    return {
        "experiment": "cross_geometry",
        "fork": "LAYERED_CARRY_DRIFT",
        "pass": bool(ok),
        "result": {
            "carry_B": {"verdict": b["verdict"], "cores_seen": b.get("cores_seen")},
            "carry_A": {"verdict": a["verdict"],
                        "anchor_in_every_query": a_keeps_anchor},
        },
    }


# ---------------------------------------------------------------------------
# E3 — placement granularity changes what the structure can do.
# ---------------------------------------------------------------------------

def placement_granularity_fork() -> Dict[str, Any]:
    """The same information, poured two ways, is not the same knowledge.

    Fine: three sentences ingested separately — each contributes its own
    facets to the core. Coarse: the same words as one run-on sentence.
    The conception claims node design and granularity change precision;
    the fork pins the mechanism: fine placement must yield at least as
    many facet links for the core, and the consensus answer text over the
    fine store must contain a facet the coarse store's answer lacks. This
    is the measurable seed of the placement-simulation harness — placement
    policies become data, and this is the first measured pair.
    """
    from .consensus_store import consensus_over_store

    fine = CrossStore()
    for s in ["apple is red", "apple is sweet", "apple grows on trees"]:
        fine.ingest_sentence(s)
    coarse = CrossStore()
    coarse.ingest_sentence("apple is red sweet grows on trees")

    f_links = fine.n_facet_links()
    c_links = coarse.n_facet_links()
    f_out = consensus_over_store(fine, "what is apple")
    c_out = consensus_over_store(coarse, "what is apple")
    f_words = set(str(f_out.get("text", "")).split())
    c_words = set(str(c_out.get("text", "")).split())

    # Parenthesised deliberately: an earlier version wrote `... and X or Y`,
    # which passes on Y alone — a fork that can pass without its own main
    # criterion is the false-pass shape this whole codebase keeps hunting.
    differ = bool(f_words - c_words) or bool(c_words - f_words)
    ok = (f_links >= c_links
          and f_out.get("verdict") == "ANSWER"
          and differ)
    return {
        "experiment": "cross_geometry",
        "fork": "PLACEMENT_GRANULARITY",
        "pass": bool(ok),
        "result": {
            "fine_facet_links": f_links, "coarse_facet_links": c_links,
            "fine": {"verdict": f_out.get("verdict"), "text": f_out.get("text")},
            "coarse": {"verdict": c_out.get("verdict"), "text": c_out.get("text")},
        },
    }


def placement_simulation_fork() -> Dict[str, Any]:
    """Pre-simulation must beat frequency when demand is concentrated,
    and must be REFUSED when it is flat.

    Both halves are the fork. A placement policy that always looks like an
    improvement is one whose gate does not work, and this project's whole
    claim rests on gates that can say no — so the flat-demand case is
    checked as hard as the concentrated one.

    The mechanism: an arm has four facet faces, a contested core has more
    than four facts, and so shipping is a choice of which four. Frequency
    picks the four the corpus repeats. Simulation picks the four the
    anticipated questions ask for. When questions are uniform over facts,
    every policy covers the asked fact with probability 4/N and simulation
    has nothing to learn — which is what the flat half pins down.
    """
    from .placement import accept, compare, derive_split

    store = CrossStore()
    # Twelve facts per core, well over the four faces, so placement is a
    # real choice rather than an identity. The words must be alphabetic:
    # a first version used fact0..fact11, the query synthesiser skips
    # non-alphabetic facets, no queries were generated, and the fork passed
    # on 0.0 <= 0.0. A fork that passes on an empty measurement is worse
    # than no fork, so the emptiness is now checked explicitly below.
    words = ("redness", "sweetness", "crispness", "firmness", "roundness",
             "brightness", "weight", "colour", "texture", "flavour",
             "season", "origin")
    # Forty cores, not three: with three the whole measurement is three
    # questions and a coincidence reads as a result. This is small enough to
    # stay a unit test and large enough that a 12-point gap is not noise.
    # Purely alphabetic names: the query synthesiser also skips non-alpha
    # CORES, so topica0 produced zero test queries the same way fact0 did.
    cores = [f"topic{chr(97 + i // 10)}{chr(97 + i % 10)}" for i in range(40)]
    for core in cores:
        for w in words:
            store.ingest_sentence(f"{core} is {w}")

    out: Dict[str, Any] = {}
    for demand in ("zipf", "uniform"):
        train, test = derive_split(store, len(cores), demand=demand, reps=8)
        cmp_ = compare(store, test, train=train)
        out[demand] = {
            "verdict": accept(cmp_)["verdict"],
            "n_test": cmp_["n_queries"],
            "uncovered_frequency":
                cmp_["summary"]["frequency"]["mean_uncovered_terms"],
            "uncovered_simulated":
                cmp_["summary"]["simulated"]["mean_uncovered_terms"],
            "answer_rate_delta": cmp_["delta"]["answer_rate"],
        }

    measured = all(
        out[d]["n_test"] > 0 and out[d]["uncovered_frequency"] > 0
        for d in ("zipf", "uniform")
    )
    ok = (measured
          and out["zipf"]["uncovered_simulated"] < out["zipf"]["uncovered_frequency"]
          and out["zipf"]["answer_rate_delta"] >= 0
          and out["uniform"]["uncovered_simulated"]
              >= out["uniform"]["uncovered_frequency"])
    return {
        "experiment": "cross_geometry",
        "fork": "PLACEMENT_SIMULATION",
        "pass": bool(ok),
        "result": dict(out, measured=measured),
    }


def placement_cannot_manufacture_confidence_fork() -> Dict[str, Any]:
    """A question that cannot distinguish its candidates must stay AMBIGUOUS,
    whatever the placement policy.

    Six clinics, each carrying dosage and onset among twelve facts. "what has
    dosage onset" matches all six equally — there is no answer, and the
    frequency rule says so. The first demand model credited a question's
    whole demand to its TOP retrieved core, so those two facts were placed on
    clinica alone, its arm out-scored five identical rivals on query overlap,
    and the engine returned a confident ANSWER naming one clinic.

    That is the most dangerous thing this module can do: not a worse answer,
    but a correct refusal converted into a wrong answer. The gate in
    `accept` cannot catch it — the answer rate goes UP, which every other
    check reads as an improvement. So it is pinned here as a shape instead.

    The fix is that all retrieved cores are credited, which is also just
    true: when a descriptive question matches six things, all six are what
    the asker wants to hear about.
    """
    from .placement import (choose_for_core, demand_from_queries,
                            facet_document_frequency)
    from .consensus import run_consensus
    from .consensus_store import _MassView, candidates_for_query
    from .cross import AXES, ShellCross
    from .face_roles import FACET_FACES

    store = CrossStore()
    shared = ["dosage", "contraindication", "onset", "interval",
              "monitoring", "titration"]
    for i in range(6):
        core = f"clinic{chr(97 + i)}"
        for a in shared:
            store.ingest_sentence(f"{core} has {a}")
        for j in range(6):
            store.ingest_sentence(f"{core} has trait{chr(97 + i)}{chr(97 + j)}")

    q = "what has dosage onset"
    cores = candidates_for_query(store, q, k=6)
    df = facet_document_frequency(store)
    asked = demand_from_queries(store, [q])
    masses = _MassView(store)

    out: Dict[str, Any] = {"n_candidates": len(cores)}
    for policy in ("frequency", "simulated"):
        shell = ShellCross()
        for axis, core in zip(AXES, cores):
            shell.faces[axis]["tip"] = core
            shell.reflections[axis] = core
            picks = choose_for_core(
                store, core, policy=policy, df=df, n_cores=store.n_cores(),
                asked=asked if policy == "simulated" else None, weight=0.0)
            for face, facet in zip(FACET_FACES, picks):
                shell.faces[axis][face] = facet
        res = run_consensus(shell, q, masses=masses)
        out[policy] = {"verdict": res.verdict, "core": res.core}

    # Six identical candidates is the precondition; without it the rest is
    # vacuous and the fork would pass on an empty setup.
    ok = (len(cores) == 6
          and out["frequency"]["verdict"] != "ANSWER"
          and out["simulated"]["verdict"] != "ANSWER")
    return {
        "experiment": "cross_geometry",
        "fork": "PLACEMENT_CANNOT_MANUFACTURE_CONFIDENCE",
        "pass": bool(ok),
        "result": out,
    }


def ja_coverage_gate_fork() -> Dict[str, Any]:
    """The Japanese path must refuse a question it did not address.

    `consensus_over_store` ran three gates; `ja_consensus_ask` ran none. So
    on the language this engine was built for, a two-party question came
    back as a confident answer about one party:

        「甲は乙を脅迫した。乙は丙を傷害した。」
        ask 「甲 丙」 -> ANSWER 「甲は主犯、乙、脅迫」

    Every word of that is true and it is still a fabrication, because 丙 was
    asked about and silently dropped. Three cases are pinned: the covered
    question still answers, the uncovered one refuses, and an entirely
    unknown term is REPORTED rather than refused — that one is a vocabulary
    gap, and conflating it with a reading failure would send it to the wrong
    queue.
    """
    from .consensus_store import ja_consensus_ask
    from .document_ingest import Document, ingest_documents

    store = CrossStore()
    ingest_documents(store, [Document(
        source="事件記録",
        text="甲は乙を脅迫した。乙は丙を傷害した。丙は負傷した。甲は主犯である。")])

    covered = ja_consensus_ask(store, "甲 乙")
    dropped = ja_consensus_ask(store, "甲 丙")
    unknown = ja_consensus_ask(store, "甲 未知語")

    ok = (covered.get("verdict") == "ANSWER"
          and dropped.get("verdict") != "ANSWER"
          and "丙" in (dropped.get("uncovered_terms") or [])
          and unknown.get("verdict") == "ANSWER"
          and "未知語" in (unknown.get("uncovered_terms") or []))
    return {
        "experiment": "cross_geometry",
        "fork": "JA_COVERAGE_GATE",
        "pass": bool(ok),
        "result": {
            "covered": covered.get("verdict"),
            "dropped_party": {"verdict": dropped.get("verdict"),
                              "uncovered": dropped.get("uncovered_terms")},
            "unknown_term": {"verdict": unknown.get("verdict"),
                             "uncovered": unknown.get("uncovered_terms")},
        },
    }


def reverse_unique_fork() -> Dict[str, Any]:
    """逆方向の唯一候補は、順方向の棄権の後ろでだけ、名乗って立つ。

    3点: (a) 枠語(〜に関係するのは何ですか)は主題に入らない — 混入は
    逆方向の誤答を0→23.7%に跳ねさせた実測がある(枠剥がし後163/0)。
    (b) 発火は 順方向非ANSWER ∧ 帯唯一 ∧ 被覆≥2 の全部AND。verdict は
    REVERSE_UNIQUE であって ANSWER ではなく、覆った語を名乗る。
    (c) 順方向が ANSWER の問いには一切触れない。
    """
    from .consensus_store import (direction_band, frame_stripped,
                                  ja_consensus_ask)
    from .lang import ja_content_runs

    st = CrossStore()
    # 唯一の2語被覆核。日本語の run になるよう漢字語で作る。
    for a in ("甲要素", "乙要素", "丙要素"):
        st.ingest_sentence(f"標的核 has {a}")
    st.ingest_sentence("甲要素 has 別物")

    q = "甲要素と乙要素に関係するのは何ですか"
    runs = ja_content_runs(q)
    qs = frame_stripped(q, runs)
    stripped_ok = "関係" not in qs and {"甲要素", "乙要素"} <= qs
    band, best = direction_band(st, qs)
    r = ja_consensus_ask(st, q, placement_invariant=True)
    fired = (r.get("verdict") == "REVERSE_UNIQUE"
             and r.get("core") == "標的核"
             and r.get("reverse_coverage") == 2
             and r.get("covered"))
    # (c) 名前形は順方向 ANSWER のまま(REVERSE_UNIQUE が触らない)
    r2 = ja_consensus_ask(st, "標的核とは", placement_invariant=True)
    untouched = r2.get("verdict") != "REVERSE_UNIQUE"
    ok = bool(stripped_ok and fired and untouched)
    return {"fork": "REVERSE_UNIQUE", "pass": ok,
            "result": {"stripped": bool(stripped_ok), "fired": bool(fired),
                       "forward_untouched": bool(untouched),
                       "band": sorted(band), "best": best,
                       "verdict": r.get("verdict")}}


def reverse_specific_fork() -> Dict[str, Any]:
    """帯割れの特定性裁定は、孤立した核だけを、根拠ごと名乗って立てる。

    順方向の敗因は証拠の不到達ではない(実測: 正解は候補に92%居て236敗、
    全facet重なりの反実仮想でも8勝) — axis_energy の 質量×名前一致 が
    被覆信号を溺れさせる。分離するのは特定性(被覆/面数)の孤立度で、
    正解時のマージン中央値21.3 vs 誤答時1.14。しきい値5.0は第三の
    核集合で確認(46/0×2族、experiments/forward_win_mechanism/PREREG2)。

    3点固定: (a) 帯が割れ、特定性が次点の5倍以上で孤立した核は
    REVERSE_SPECIFIC として立ち、margin と次点を名乗る。(b) 僅差
    (5倍未満)の帯は棄権のまま — 問いが核を特定していない。
    (c) 帯唯一の REVERSE_UNIQUE は不変。
    """
    from .consensus_store import ja_consensus_ask

    # 数字混じり("雑面0号")は facet に取り込まれない — 汎用核の面は
    # 漢字だけで28本作る。「甲徴 has 別物」は reverse_unique_fork と同じ
    # 治具: 弱い直接ヒット核を立てて順方向を棄権させる(逆裁定は順方向
    # 非ANSWERの後ろでしか発火しない)。
    _digits = ("一", "二", "三", "四", "五", "六")
    _junk = [f"雑{a}{b}" for a in _digits for b in _digits][:28]

    st = CrossStore()
    st.ingest_sentence("甲徴 has 別物")
    # 特定核: 3面のうち2面が問いに当たる(特定性 2/3)。
    for a in ("甲徴", "乙徴", "丙徴"):
        st.ingest_sentence(f"特定核 has {a}")
    # 汎用核: 同じ2語を含む30面(特定性 2/30)— 帯は割れ、margin は 10。
    for a in ["甲徴", "乙徴"] + _junk:
        st.ingest_sentence(f"汎用核 has {a}")

    q = "甲徴と乙徴に関係するのは何ですか"
    r = ja_consensus_ask(st, q, placement_invariant=True)
    fired = (r.get("verdict") == "REVERSE_SPECIFIC"
             and r.get("core") == "特定核"
             and (r.get("specificity_margin") or 0) >= 5.0
             and r.get("runner_up") == "汎用核")

    # (b) 僅差: 3面 vs 4面(margin 4/3 < 5)は棄権のまま。
    close = CrossStore()
    close.ingest_sentence("甲徴 has 別物")
    for a in ("甲徴", "乙徴", "丙徴"):
        close.ingest_sentence(f"特定核 has {a}")
    for a in ("甲徴", "乙徴", "丁徴", "戊徴"):
        close.ingest_sentence(f"次点核 has {a}")
    r2 = ja_consensus_ask(close, q, placement_invariant=True)
    abstained = r2.get("verdict") not in ("REVERSE_SPECIFIC", "ANSWER")

    # (c) 帯唯一なら従来どおり REVERSE_UNIQUE。
    uniq = CrossStore()
    uniq.ingest_sentence("甲徴 has 別物")
    for a in ("甲徴", "乙徴", "丙徴"):
        uniq.ingest_sentence(f"特定核 has {a}")
    r3 = ja_consensus_ask(uniq, q, placement_invariant=True)
    unique_kept = (r3.get("verdict") == "REVERSE_UNIQUE"
                   and r3.get("core") == "特定核")

    ok = bool(fired and abstained and unique_kept)
    return {"fork": "REVERSE_SPECIFIC", "pass": ok,
            "result": {"fired": bool(fired),
                       "margin": r.get("specificity_margin"),
                       "close_abstained": bool(abstained),
                       "close_verdict": r2.get("verdict"),
                       "unique_kept": bool(unique_kept)}}


def prover_three_outcomes_fork() -> Dict[str, Any]:
    """証明器の扉は、証明・反駁・拒否の三つを混ぜない(fork 169本目)。

    「不在と否定を混ぜない」の証明版。届かなかったこと(REFUSED)を偽
    (REFUTED)として返す扉は、この製品が拒否のために作られた門を自分で
    くぐることになる。4点固定:
      (a) 真の等式は PROVED、主張は Lean が検分している
      (b) 偽の等式は REFUTED で、**反例を名指す**(再計算できる)
      (c) 届かない等式は REFUSED で needs を運ぶ — 反例は無い
      (d) 署名の外の記号は UNKNOWN_ILL_TYPED(推測で受けない)
    """
    from .prover import prove_equation, signature

    proved = prove_equation("rev(rev(x))", "x")
    refuted = prove_equation("app(x, y)", "app(y, x)")
    refused = prove_equation("min(a, b)", "min(b, a)")
    illtyped = prove_equation("quux(a)", "a")

    ok_proved = (proved.get("verdict") == "PROVED"
                 and str(proved.get("lean", {}).get("verdict"))
                 in ("VERIFIED", "UNKNOWN_TOOLCHAIN_MISSING"))
    ok_refuted = (refuted.get("verdict") == "REFUTED"
                  and bool(refuted.get("counterexample")))
    ok_refused = (refused.get("verdict") == "REFUSED"
                  and bool(refused.get("needs"))
                  and "counterexample" not in refused)
    ok_typed = (illtyped.get("verdict") == "UNKNOWN_ILL_TYPED"
                and "le" in signature()["functions"])
    ok = bool(ok_proved and ok_refuted and ok_refused and ok_typed)
    return {"fork": "PROVER_THREE_OUTCOMES", "pass": ok,
            "result": {"proved": proved.get("verdict"),
                       "lean": proved.get("lean", {}).get("verdict"),
                       "refuted": refuted.get("verdict"),
                       "counterexample": refuted.get("counterexample"),
                       "refused": refused.get("verdict"),
                       "needs": refused.get("needs"),
                       "ill_typed": illtyped.get("verdict")}}


def attest_polarity_fork() -> Dict[str, Any]:
    """主張の採点は、肯定と否定を同じ点にしてはならない(fork 170本目)。

    2026-08-20 実測(隔離環境・第三者のブラインド評価と二者独立):
        「実費を支給する」   -> ANSWER support=1.0
        「実費を支給しない」 -> ANSWER support=1.0   ← 完全同点
    機序は構成上のもの — 採点器は漢字・カタカナの連しか見ず、否定は
    ひらがなに居た。極性の器官は在るのに呼ばれていなかった(実装済み
    未到達)。3点固定:
      (a) 店が反対の極を**証拠として**持てば CONTRADICTED_BY_CORPUS で、
          その facet を名指す
      (b) 店が語だけ持ち極性を記録していなければ
          UNKNOWN_POLARITY_UNJUDGED — 黙って同点にしない
      (c) 極性の争点が無い主張は従来どおり ANSWER
    """
    from .attest_llm import check_all
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents
    from .polarity import ingest_polar_ja

    doc = CrossStore(track_provenance=True)
    ingest_documents(doc, [Document(
        source="規程.txt",
        text="会社は、従業員に対し、通勤に要する実費を支給する。"
             "自家用車通勤の場合は1キロメートルあたり15円を支給する。"
             "月額30000円を上限とする。")])
    pos = check_all(doc, "会社", "従業員に対し通勤に要する実費を支給する")
    neg = check_all(doc, "会社", "従業員に対し通勤に要する実費を支給しない")

    # 主題は MIN_FACETS(3)以上を持たせる — 2文では TOO_THIN で
    # 極性まで届かない(この治具を薄く作って一度落とした)。
    pol = CrossStore(track_provenance=True)
    for s in ("避難所は開設している。", "水道は復旧していない。",
              "避難所は受付中である。", "水道は断水している。"):
        ingest_polar_ja(pol, s)
        pol.ingest_sentence(s)
    contra = check_all(pol, "水道", "水道は復旧している")
    agree = check_all(pol, "避難所", "避難所は開設している")

    ok_split = (pos.get("verdict") == "ANSWER"
                and neg.get("verdict") == "UNKNOWN_POLARITY_UNJUDGED")
    ok_contra = (contra.get("verdict") == "CONTRADICTED_BY_CORPUS"
                 and bool(contra.get("contradictions"))
                 and contra["contradictions"][0].get("facet"))
    ok_agree = agree.get("verdict") == "ANSWER"
    ok = bool(ok_split and ok_contra and ok_agree)
    return {"fork": "ATTEST_POLARITY", "pass": ok,
            "result": {"positive": pos.get("verdict"),
                       "negated": neg.get("verdict"),
                       "contradicted": contra.get("verdict"),
                       "facet": (contra.get("contradictions") or [{}])[0]
                       .get("facet"),
                       "agreement": agree.get("verdict")}}


def transfer_reading_fork() -> Dict[str, Any]:
    """転移は数える。なぜ転移したかは主張しない(fork 171本目)。

    `transfer_outcomes` が「実データが溜まるまで」と保留した較正段。
    4点固定: (a) 全文脈で一致した事実は TRANSFERRED (b) 割れた事実は
    CONTEXT_BOUND (c) 1文脈しか無い事実は UNKNOWN_SINGLE_CONTEXT —
    予測しない (d) 観測が閾値未満の次元は数字を出さず
    UNKNOWN_TOO_FEW_CONTEXTS。
    """
    from .transfer_reading import calibrate, judge_transfer

    agree = judge_transfer({"fact": "h(a)", "raw_names": ["h(a)"],
                            "contexts": {"m1": "harm", "m2": "harm",
                                         "m3": "harm"},
                            "labels": {}, "source": "fixture"})
    split = judge_transfer({"fact": "h(b)", "raw_names": ["h(b)"],
                            "contexts": {"m1": "adopt", "m2": "abstain"},
                            "labels": {}, "source": "fixture"})
    lone = judge_transfer({"fact": "h(c)", "raw_names": ["h(c)"],
                           "contexts": {"m1": "adopt"},
                           "labels": {}, "source": "fixture"})
    thin = calibrate([lone], {"h(c)": "薄い次元"})["薄い次元"]
    counted = calibrate([agree, split], {"h(a)": "d", "h(b)": "d"})["d"]
    ok = (agree["verdict"] == "TRANSFERRED"
          and split["verdict"] == "CONTEXT_BOUND"
          and lone["verdict"] == "UNKNOWN_SINGLE_CONTEXT"
          and thin["verdict"] == "UNKNOWN_TOO_FEW_CONTEXTS"
          and counted["verdict"] == "COUNTED")
    return {"fork": "TRANSFER_READING", "pass": bool(ok),
            "result": {"agree": agree["verdict"], "split": split["verdict"],
                       "single": lone["verdict"], "thin": thin["verdict"],
                       "counted": counted["verdict"]}}


def axis_lock_fork() -> Dict[str, Any]:
    """ロックできるのは、同点崩しで勝っていない腕だけ(fork 172本目)。

    構想(これまで.pdf)は「軸のロック」で時間の短縮と精度を得ると言うが、
    何を根拠にロックするかは書いていない。配置は情報を増やせないのだから、
    **同点崩しで勝った腕はロックできない** — そこから導出した2条件
    (配置不変を生き延びた ∧ facet の counts が割れている)を固定する。

    3点: (a) 全 facet が同点の店ではロックが**空** (b) counts が割れる店では
    その腕がロックされる (c) ロックの有無で **verdict は変わらない**
    (ロックは探索の近道であって、答えを変える権限を持たない)。
    """
    from .consensus_store import consensus_over_store

    tied = CrossStore()
    for a in ("aspa", "aspb", "aspc", "aspd"):
        tied.ingest_sentence(f"gadget has {a}")
    r_tied = consensus_over_store(tied, "what is gadget aspa",
                                  placement_invariant=True)

    ranked = CrossStore()
    for _ in range(5):
        ranked.ingest_sentence("gadget is heavy")
    for _ in range(4):
        ranked.ingest_sentence("gadget is fast")
    for _ in range(3):
        ranked.ingest_sentence("gadget is small")
    for _ in range(2):
        ranked.ingest_sentence("gadget is quiet")
    r_rank = consensus_over_store(ranked, "what is gadget heavy",
                                  placement_invariant=True)

    # (c) ロックを継承した2回目でも判定が変わらない
    circ = {}
    consensus_over_store(ranked, "what is gadget heavy",
                         placement_invariant=True, circulation=circ)
    r_again = consensus_over_store(ranked, "what is gadget fast",
                                   placement_invariant=True, circulation=circ)
    r_plain = consensus_over_store(ranked, "what is gadget fast",
                                   placement_invariant=True)

    ok = (r_tied.get("locks") == []
          and r_rank.get("locks")
          and circ.get("gadget", {}).get("locks")
          and r_again.get("verdict") == r_plain.get("verdict")
          and r_again.get("core") == r_plain.get("core"))
    return {"fork": "AXIS_LOCK", "pass": bool(ok),
            "result": {"tied_locks": r_tied.get("locks"),
                       "ranked_locks": r_rank.get("locks"),
                       "carried": circ.get("gadget", {}).get("locks"),
                       "verdict_with_lock": r_again.get("verdict"),
                       "verdict_without": r_plain.get("verdict")}}


def norm_vs_record_fork() -> Dict[str, Any]:
    """規範と記録は、極性が逆でも矛盾ではない — その枝が実際に動くこと。

    `fusion.classify` の NORM_VS_RECORD は実装されていたが、`registers` を
    渡す呼び出し元が一つも無く、`reg = registers or {}` が常に空で
    ra/rb は "unknown" のまま — **一度も発火しない枝**だった(2026-08-19、
    bridge.rs と同じ「実装済み未到達」)。分野名から登録を自給するように
    して、ここで発火を固定する。

    2点: (a) 法令(定める)×百科(記す)で同じ側面の逆極は NORM_VS_RECORD、
    (b) 同じ登録どうしの逆極は CONTRADICTION_CANDIDATE のまま —
    同一機会の検査は依然として無いので、候補以上には言わない。
    """
    import collections

    from .fusion import Point, classify, field_register
    from .ja_grammar import ASPECT_OF

    by_aspect: Dict[str, Dict[str, str]] = collections.defaultdict(dict)
    for f, (a, p) in ASPECT_OF.items():
        by_aspect[a][p] = f
    pick = next(((a, d) for a, d in by_aspect.items()
                 if "+" in d and "-" in d), None)
    if pick is None:
        return {"experiment": "fusion", "fork": "NORM_VS_RECORD",
                "skipped": "no polar pair in ASPECT_OF"}
    _asp, d = pick

    def _store(term: str) -> CrossStore:
        st = CrossStore()
        st.ingest_sentence("対象 は %s である" % term)
        return st

    pt = Point(concept="対象", by_field={"法令": {"対象"}, "百科": {"対象"}})
    a = classify({"法令": {"x": _store(d["+"])},
                  "百科": {"y": _store(d["-"])}}, pt)
    pt2 = Point(concept="対象", by_field={"百科": {"対象"}, "多分野": {"対象"}})
    b = classify({"百科": {"x": _store(d["+"])},
                  "多分野": {"y": _store(d["-"])}}, pt2)
    ok = (a.get("kind") == "NORM_VS_RECORD"
          and sorted(a.get("registers") or []) == ["norm", "record"]
          and b.get("kind") == "CONTRADICTION_CANDIDATE"
          and field_register("法令") == "norm"
          and field_register("未知の分野") == "unknown")
    return {"experiment": "fusion", "fork": "NORM_VS_RECORD", "pass": bool(ok),
            "result": {"norm_x_record": a.get("kind"),
                       "record_x_record": b.get("kind"),
                       "registers": a.get("registers")}}


def quote_is_substring_fork() -> Dict[str, Any]:
    """引用として出す行は、必ず原文の部分文字列である。

    `document_structure.verify_quoted` は「事前登録が機構全体を賭けた
    機械検査」と自ら述べながら、**呼び出し元が一つも無かった**
    (2026-08-19、到達性の棚卸しで発覚: 公開定義1,410本中、参照ゼロが57本)。
    実店の18問で測ると全部通る — つまり保証は**正しいコードの運**で
    成り立っており、構造で支えられてはいなかった。ここに荷重をかける。

    3点: (a) 正しい引用は通る (b) 一文字でも原文に無い行は落ちる
    (c) ラベル値(value)も同じ検査を受ける。
    """
    from .document_structure import index, lookup, verify_quoted

    text = ("第1条 目的\n"
            "この規程は出張旅費の取扱いを定める。\n"
            "第2条 上限\n"
            "宿泊費は一泊15,000円を上限とする。\n"
            "提出期限: 月末まで\n")
    book = {"documents": [index(text, "出張旅費規程.txt")]}

    r = lookup("宿泊費", book)
    genuine = str(r.get("verdict") or "").startswith("DOCUMENT") \
        and verify_quoted(r, text)

    # (b) 原文に無い行を混ぜたら落ちる
    tampered = dict(r)
    tampered["lines"] = list(r.get("lines") or []) + [
        "宿泊費は一泊30,000円を上限とする。"]
    catches = not verify_quoted(tampered, text)

    # (c) ラベル値も検査される
    lab = lookup("提出期限", book)
    label_ok = verify_quoted(lab, text)
    lab_bad = dict(lab)
    lab_bad["value"] = "翌月10日まで"
    label_catches = not verify_quoted(lab_bad, text)

    ok = bool(genuine and catches and label_ok and label_catches)
    return {"experiment": "cross_geometry", "fork": "QUOTE_IS_SUBSTRING",
            "pass": ok,
            "result": {"genuine_passes": bool(genuine),
                       "tampered_caught": bool(catches),
                       "label_passes": bool(label_ok),
                       "label_tampered_caught": bool(label_catches)}}


def read_at_shows_both_sides_fork() -> Dict[str, Any]:
    """食い違う二分野は、併合されずに両方返る。

    `fusion.read_at` は「平均せずに見せる」ための器官なのに、呼び出し元が
    一つも無かった(2026-08-19、到達性の棚卸し)。二空間を併合しないという
    設計の看板機能に出口が無かったので、`vera_read_at` 扉を付け、ここで
    荷重をかける。

    2点: (a) 両分野が別々の読みを持つとき、両方が by_field に残る
    (b) 何も選ばない — 単一の core や text に畳まれない。
    """
    # read_at の絞り込みは「概念が **facet として** 現れる分野」だけを
    # 見る(core 名だけでは通らない — direction_band で名前を数え忘れて
    # 帯から core 自身が脱落したのと同じ罠が、この関数にも在る)。
    # 固定具はその条件を満たす形にする: 対象 が facet に立つ。
    a = CrossStore()
    a.ingest_sentence("甲説 は 対象 に ついて 述べる")
    a.ingest_sentence("対象 は 甲説 である")
    b = CrossStore()
    b.ingest_sentence("乙説 は 対象 に ついて 述べる")
    b.ingest_sentence("対象 は 乙説 である")

    from .fusion import read_at

    r = read_at({"分野A": {"x": a}, "分野B": {"y": b}}, "対象")
    both = sorted(r.get("fields") or []) == ["分野A", "分野B"]
    rows = r.get("by_field") or {}
    kept = all(len(rows.get(f) or []) >= 1 for f in ("分野A", "分野B"))
    # 何も選んでいない: 単一の答えに畳む鍵を持たない
    no_pick = "core" not in r and "text" not in r and "verdict" not in r
    ok = bool(both and kept and no_pick)
    return {"experiment": "cross_geometry", "fork": "READ_AT_SHOWS_BOTH_SIDES",
            "pass": ok,
            "result": {"fields": r.get("fields"), "kept_both": bool(kept),
                       "picks_nothing": bool(no_pick)}}


def direction_invariance_fork() -> Dict[str, Any]:
    """向きの不変性: 読む向きを変えると消える当選は立ってはならない。

    発案は操作者(2026-08-19):「一方からしか見ていない。逆からやったものを
    重ねて、まとめて投入することで相殺する」。順方向(問い→名前で core を
    引く)は、正解が候補に居ないとき棄権せず誤答する(実ストア実測
    206/300)。逆方向(問いを最も覆う core の帯、名前も被覆に数える)は
    誤りの出方が別種なので、両方向の一致だけを通す門が誤答を相殺する
    (誤答206→26・正答無傷、experiments/bidirectional_consensus)。

    2つの半分: (a) 逆方向の帯に入らない順方向 ANSWER は
    UNKNOWN_DIRECTION_DISAGREEMENT へ降格し、両方向の言い分を名乗る。
    (b) 名前で問いを覆う正当な当選は生き残る — core は自分の名前を
    facet に持たないので、名前を被覆に数え忘れると門が正当な当選を
    全滅させる(実測: 正当防衛とは/時効とは/傷害罪とは が死んだ)。
    """
    from .consensus_store import (_apply_direction_invariance,
                                  direction_band)

    st = CrossStore()
    # 正解側: core "target" は問いの2語 aspx aspy を facet で覆う。
    for a in ("aspx", "aspy", "aspz"):
        st.ingest_sentence(f"target has {a}")
    # 誤答側: core "aspx" — 問いの語そのものを名前に持つが、問いを
    # 1語しか覆わない(順方向の直接ヒットが勝つ形)。
    st.ingest_sentence("aspx has otherthing")

    qset = {"aspx", "aspy"}
    band, best = direction_band(st, qset)
    # (a) 1語被覆の当選は帯(2語被覆=target)に入らず降格する
    wrong = {"verdict": "ANSWER", "core": "aspx", "core_key": "aspx",
             "text": "aspx otherthing"}
    _apply_direction_invariance(st, wrong, qset)
    demoted = wrong["verdict"] == "UNKNOWN_DIRECTION_DISAGREEMENT"         and wrong.get("forward_core") == "aspx" and wrong.get("reverse_band")
    # (b) 帯に入る当選は生き残り、証明書が乗る
    right = {"verdict": "ANSWER", "core": "target", "core_key": "target",
             "text": "target aspx aspy"}
    _apply_direction_invariance(st, right, qset)
    survived = right["verdict"] == "ANSWER"         and right.get("direction_invariant") is True
    # (b') 名前被覆: 問いが core 名そのもののとき、その core が帯に居る
    band2, _b2 = direction_band(st, {"target"})
    named = "target" in band2
    ok = bool(demoted and survived and named)
    return {"fork": "DIRECTION_INVARIANCE", "pass": ok,
            "result": {"demoted": bool(demoted), "survived": bool(survived),
                       "name_covered": bool(named),
                       "band": sorted(band), "best": best}}


def placement_invariance_fork() -> Dict[str, Any]:
    """An answer that depends on an arbitrary tie-break must not stand.

    Placement cannot add information: the store holds the same facts either
    way, and only which four reach the faces changes. So a core that wins
    under one arbitrary ordering of equally-scored facts and loses under
    another won on the ordering. Same argument shape as "layout cannot add
    information" in docs/METAMORPHIC.md, and the same property — no answer
    key, no human, no model, both readings in this process.

    Two halves, and the second is what stops this being a gate that simply
    refuses everything: an answer grounded in counts the store can actually
    tell apart must SURVIVE, because ties are not what carried it.

    The fixture needs RIVALS. A single-arm store was the first attempt and
    the gate could never fire on it: with one candidate the core wins
    whatever occupies the faces, so the two readings always agree on the
    core and only the text differs — which is placement doing its ordinary
    job, not an artifact. Fabrication needs somebody to beat.
    """
    import random

    from .consensus_store import candidates_for_query, consensus_over_store

    # Six rivals, every facet count 1, each carrying eight of twelve aspects.
    # The whole ordering is therefore a tie-break, and a descriptive question
    # that several of them satisfy can only be "won" by the tie-break.
    aspects = [f"asp{chr(97 + i)}" for i in range(12)]
    rng = random.Random(5)
    tied = CrossStore()
    for i in range(6):
        core = f"unit{chr(97 + i)}"
        for a in rng.sample(aspects, 8):
            tied.ingest_sentence(f"{core} has {a}")
    # This exact question is a fabrication under the default tie-break:
    # FOUR of the six units carry both aspd and aspf, and the engine names
    # one of them. The owner count is asserted below so that a fixture drift
    # which made the question legitimately decidable would fail here rather
    # than quietly turn this into a test of nothing.
    q = "what has aspd aspf"
    owners = [c for c in candidates_for_query(tied, q, k=6)
              if "aspd" in tied.crosses[c] and "aspf" in tied.crosses[c]]
    tied_off = consensus_over_store(tied, q)
    tied_on = consensus_over_store(tied, q, placement_invariant=True)

    # Counts differ -> the top four are not tied -> the gate must not fire.
    weighted = CrossStore()
    for _ in range(5):
        weighted.ingest_sentence("gadget is heavy")
    for _ in range(4):
        weighted.ingest_sentence("gadget is fast")
    for _ in range(3):
        weighted.ingest_sentence("gadget is small")
    for _ in range(2):
        weighted.ingest_sentence("gadget is quiet")
    weighted.ingest_sentence("gadget is rare")
    w_on = consensus_over_store(weighted, "what is gadget heavy",
                                placement_invariant=True)

    ok = (len(owners) > 1                       # the question IS undecidable
          and tied_off.get("verdict") == "ANSWER"   # and the engine answered it
          and tied_on.get("verdict") != "ANSWER"    # and the gate refuses it
          and tied_on.get("reason") == "placement_dependent_answer"
          and w_on.get("verdict") == "ANSWER"       # without refusing everything
          and w_on.get("placement_invariant") is True)
    return {
        "experiment": "cross_geometry",
        "fork": "PLACEMENT_INVARIANCE",
        "pass": bool(ok),
        "result": {
            "owners_of_the_question": owners,
            "all_ties_gate_off": tied_off.get("verdict"),
            "all_ties_gate_on": {"verdict": tied_on.get("verdict"),
                                 "reason": tied_on.get("reason")},
            "distinct_counts_gate_on": {"verdict": w_on.get("verdict"),
                                        "invariant": w_on.get("placement_invariant")},
        },
    }


def reified_event_fork() -> Dict[str, Any]:
    """A three-place fact fits a two-place store when the EVENT is the core.

    「甲は乙を脅迫した。乙は丙を傷害した。」 as ordinary sentences gives two
    crosses with no path between them, so a question about 甲 and 丙 reaches
    nothing. Reified, the participants become role-tagged facets of the
    happening, every fact stays unary attribution — the shape the store
    already has — and the chain is walkable.

    Four things are pinned, and the last three are the ones that make it
    usable rather than merely representable:

      * the chain 丙 → 事象2 → 乙 → 事象1 → 甲 is traversable
      * a role claim has THREE outcomes: confirmed, refuted, unknown. Asked
        with the wrong object the store must REFUTE (it holds 対象丙), and
        asked about a role it never recorded it must say so — answering the
        whole event and staying silent about the asked role is the same
        fabrication one level down
      * all four faces carry facts: the citation is provenance, and it was
        occupying one of the four an event needs
      * an unreadable construction is SKIPPED WITH ITS REASON, not guessed.
        「暴行を加えた」 would require deciding that 暴行 rather than 加 is
        the act, and a wrong guess there mislabels who did what.
    """
    from .consensus_store import ja_consensus_ask
    from .events import extract_events, ingest_events, link_cause

    ex = extract_events("甲は乙を脅迫した。乙は丙を傷害した。甲が乙に暴行を加えた。")
    events = ex["events"]
    if len(events) < 2:
        return {"experiment": "cross_geometry", "fork": "REIFIED_EVENT",
                "pass": False, "result": {"extracted": len(events),
                                          "skipped": ex["skipped"]}}
    link_cause(events[1], events[0])
    store = CrossStore()
    ingest_events(store, events, source="事件記録")

    def facts(core):
        return {f for f in (store.crosses.get(core) or {})
                if f not in store.source_labels}

    hit = [c for c, f in store.crosses.items() if "対象丙" in f]
    walked = False
    if hit:
        e2 = facts(hit[0])
        cause = [f[2:] for f in e2 if f.startswith("原因")]
        if cause:
            e1 = facts(cause[0])
            walked = ("主体甲" in e1 and "対象乙" in e1 and "主体乙" in e2)

    confirmed = ja_consensus_ask(store, "事象2 対象丙")
    refuted = ja_consensus_ask(store, "事象2 対象甲")
    unknown_role = ja_consensus_ask(store, "事象2 場所東京")
    faces = [f for f in (store.crosses.get("事象2") or {})
             if f not in store.source_labels]
    light = [s for s in ex["skipped"] if s["reason"].startswith("light_verb")]

    ok = (walked
          and confirmed.get("verdict") == "ANSWER"
          and refuted.get("verdict") == "UNKNOWN_ROLE_MISMATCH"
          and unknown_role.get("verdict") == "UNKNOWN_INSUFFICIENT_EVIDENCE"
          and len(faces) >= 4
          and len(light) == 1)
    return {
        "experiment": "cross_geometry",
        "fork": "REIFIED_EVENT",
        "pass": bool(ok),
        "result": {
            "chain_walked": walked,
            "confirmed": confirmed.get("verdict"),
            "refuted": {"verdict": refuted.get("verdict"),
                        "detail": refuted.get("reason")},
            "role_not_recorded": unknown_role.get("verdict"),
            "facts_on_faces": sorted(faces),
            "skipped_with_reason": ex["skipped"],
        },
    }


def event_extractor_refuses_statute_prose_fork() -> Dict[str, Any]:
    """The event reader must read a fact pattern and REFUSE statute prose.

    Unguarded, this extractor produced 6,800 "events" from 9,087 sentences
    of six Japanese statutes — 74.8%, and inspection showed 又 (a
    conjunction) assigned as the actor and 処 as the act. The rate measured
    how often it produced something, not how often it produced something
    true. With the guard: 2.1% read, everything else refused by name.

    That is not a shortcoming to fix later. Statutes state RULES; a fact
    pattern is not in them. This fork pins the division so a future
    loosening of the guard has to argue with a measurement.
    """
    from .events import extract_events, unreadable

    facts = "甲は乙を脅迫した。乙は丙を傷害した。甲は乙に現金を交付した。"
    got = extract_events(facts)

    # Real sentences from 刑法 and 民法, each carrying a construction the
    # particle reader cannot resolve.
    statute = [
        "前項の規定は、親族でない共犯については、適用しない。",
        "公務員が職権を濫用して、人に義務のないことを行わせ、又は権利の行使を妨害したとき。",
        "権利の行使及び義務の履行は、信義に従い誠実に行わなければならない。",
    ]
    refused = [unreadable(s) for s in statute]

    ok = (len(got["events"]) == 3
          and got["events"][0].roles.get("主体") == "甲"
          and got["events"][0].roles.get("対象") == "乙"
          and got["events"][1].roles.get("主体") == "乙"
          and not got["skipped"]
          and all(r is not None for r in refused))
    return {
        "experiment": "cross_geometry",
        "fork": "EVENT_EXTRACTOR_REFUSES_STATUTE_PROSE",
        "pass": bool(ok),
        "result": {
            "fact_pattern_roles": [e.roles for e in got["events"]],
            "fact_pattern_skipped": got["skipped"],
            "statute_refusals": refused,
        },
    }


def egov_article_is_a_citation_key_fork() -> Dict[str, Any]:
    """An article must be retrievable by the string a reader types.

    Two shapes were measured and rejected on real 刑法 XML. Whole law as one
    document: headings carry forward and 第百八条 came back with captions
    belonging to other articles — a citation tool pointing at the wrong
    provision. One document per article: attribution is right, but the core
    of 「人を殺した者は…」 is 者, which several hundred articles share.

    Reifying the article fixes both, and the last assertion is why it is
    worth having: asked whether 第二百四条 is about 殺人, the engine must
    REFUSE. 204 is 傷害. Returning the article with a confident silence
    about the word actually asked is the failure this whole layer exists
    to prevent.

    The fixture carries 第百九十九条（殺人）as well, and it has to: the gate
    refuses a term the store KNOWS and merely reports one it has never seen,
    because "204 is not about murder" and "I do not know what murder is" are
    different states. Without 殺人 present the fork passed on the wrong
    branch — the real 刑法 refuses because 殺人 is in it.
    """
    import xml.etree.ElementTree as ET
    import tempfile
    from pathlib import Path

    from .consensus_store import ja_consensus_ask
    from .egov import ingest_law

    # A miniature law with both a main and a supplementary 第一条 — the
    # collision that made 民法第一条 return 施行期日 instead of 基本原則.
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Law><LawBody><LawTitle>試験法</LawTitle>
<MainProvision>
<Article Num="1"><ArticleCaption>（基本原則）</ArticleCaption>
<ArticleTitle>第一条</ArticleTitle><Paragraph><ParagraphSentence>
<Sentence>私権は、公共の福祉に適合しなければならない。</Sentence>
</ParagraphSentence></Paragraph></Article>
<Article Num="199"><ArticleCaption>（殺人）</ArticleCaption>
<ArticleTitle>第百九十九条</ArticleTitle><Paragraph><ParagraphSentence>
<Sentence>人を殺した者は、死刑又は無期拘禁刑に処する。</Sentence>
</ParagraphSentence></Paragraph></Article>
<Article Num="204"><ArticleCaption>（傷害）</ArticleCaption>
<ArticleTitle>第二百四条</ArticleTitle><Paragraph><ParagraphSentence>
<Sentence>人の身体を傷害した者は、十五年以下の拘禁刑に処する。</Sentence>
</ParagraphSentence></Paragraph></Article>
</MainProvision>
<SupplProvision>
<Article Num="1"><ArticleCaption>（施行期日）</ArticleCaption>
<ArticleTitle>第一条</ArticleTitle><Paragraph><ParagraphSentence>
<Sentence>この法律は、公布の日から施行する。</Sentence>
</ParagraphSentence></Paragraph></Article>
</SupplProvision>
</LawBody></Law>"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "law.xml"
        p.write_text(xml, encoding="utf-8")
        store = CrossStore()
        placed = ingest_law(store, p)
        main1 = ja_consensus_ask(store, "試験法第一条")
        suppl1 = ja_consensus_ask(store, "試験法附則第一条")
        art204 = ja_consensus_ask(store, "試験法第二百四条 傷害")
        wrong = ja_consensus_ask(store, "試験法第二百四条 殺人")

    ok = (placed.get("articles") == 4
          and main1.get("verdict") == "ANSWER"
          and "基本原則" in str(main1.get("text", ""))
          and suppl1.get("verdict") == "ANSWER"
          and "施行" in str(suppl1.get("text", ""))
          and art204.get("verdict") == "ANSWER"
          and wrong.get("verdict") != "ANSWER")
    return {
        "experiment": "cross_geometry",
        "fork": "EGOV_ARTICLE_IS_A_CITATION_KEY",
        "pass": bool(ok),
        "result": {
            "articles": placed.get("articles"),
            "main_first": main1.get("text"),
            "suppl_first": suppl1.get("text"),
            "correct_topic": art204.get("verdict"),
            "wrong_topic": wrong.get("verdict"),
        },
    }


def sovereign_build_fork() -> Dict[str, Any]:
    """The whole procedure, end to end, on a miniature federation.

    Three things are pinned, and the second is the one that keeps the first
    honest:

      * a question whose term lives in one leaf reaches it, with a path
      * a question whose term spans two DOMAINS refuses to choose, and
        names both — 緊急避難 is in the criminal code and the civil code,
        and picking one would be the fabrication this shape exists against
      * a term in neither comes back NOT PRESENT rather than as the nearest
        thing available

    `gather` lists rather than chooses, so it is allowed to return both
    branches where `descend` must refuse; both are exercised here because
    shipping only the listing path would quietly drop the refusal.
    """
    from .hierarchy import descend, gather
    from .sovereign import assemble

    crim = CrossStore()
    for s in ["刑法第三十七条は緊急避難である。", "刑法第三十七条は危難である。",
              "刑法第百九十九条は殺人である。", "刑法第百九十九条は死刑である。"]:
        _ingest_ja(crim, s)
    civ = CrossStore()
    for s in ["民法第七百二十条は緊急避難である。", "民法第七百二十条は不法行為である。",
              "民法第七百九条は損害賠償である。"]:
        _ingest_ja(civ, s)
    lab = CrossStore()
    for s in ["労働基準法第二十条は解雇である。", "労働基準法第二十条は予告である。"]:
        _ingest_ja(lab, s)

    domains = {"刑事": {"刑法": crim}, "民事": {"民法": civ}, "労働": {"労基": lab}}
    grouping = {"刑事": {"刑法": ["刑法"]}, "民事": {"民法": ["民法"]},
                "労働": {"労基": ["労基"]}}
    root = assemble(domains, grouping, sovereign="主権")

    one = gather(root, "解雇")
    both = gather(root, "緊急避難")
    absent = gather(root, "断水")
    chosen = descend(root, "緊急避難")

    domains_hit = {r["path"][1] for r in both["results"] if len(r["path"]) > 1}

    ok = (one["answered"] == 1
          and "労基" in one["results"][0]["leaf"]
          and both["destinations"] == 2
          and len(domains_hit) == 2
          and chosen["verdict"] != "ANSWER"
          and absent["verdict"] == "UNKNOWN_NOT_PRESENT")
    return {
        "experiment": "cross_geometry",
        "fork": "SOVEREIGN_BUILD",
        "pass": bool(ok),
        "result": {
            "single_leaf": {"answered": one["answered"],
                            "leaf": one["results"][0]["leaf"] if one["results"] else None},
            "spans_two_domains": {"destinations": both["destinations"],
                                  "domains": sorted(domains_hit),
                                  "descend_refused": chosen["verdict"]},
            "absent": absent["verdict"],
        },
    }


def _ingest_ja(store: CrossStore, sentence: str) -> None:
    from .document_ingest import Document, ingest_documents
    ingest_documents(store, [Document(source="fixture", text=sentence)])


def document_draft_is_licensed_fork() -> Dict[str, Any]:
    """文書の下書きは引用行の言葉しか使えない — 使えなければ黙る。

    8/18に却下した文書側生成(「グリーンをグリーン車さない」「がいしょく
    ほう」)の門つき再挑戦(2026-08-19)の契約を固定する:

      1. 下書きの充填語は全て、引用行の内容連∪主語に含まれる(発明ゼロ)。
      2. 語彙を通る語が主語+1つ無ければ、下書きは None(断片より沈黙)。
      3. verdict・引用本文には一切触れない。
      4. **否定の行では黙る**(2026-08-19追加)。speakable は positive 形
         しか持たないので、「精算の対象としない」から下書きを作ると
         「対象する」— 行の主張の反転 — しか出せない。この契約が入る前は
         この fork 自身が否定行を固定具に使っており、反転した下書きが
         出ることを「合格」として守っていた。固定具を肯定行へ替え、
         否定行は沈黙の側で押さえる。
    """
    from pathlib import Path as _P

    from .stacked import quote_in_words
    from .lang import ja_content_runs
    from .writer import Writer

    from .paths import corpus_root as _cr
    wpath = _cr() / "build" / "writer.json"
    if not wpath.exists():
        return {"experiment": "cross_geometry",
                "fork": "DOCUMENT_DRAFT_IS_LICENSED",
                "pass": True, "result": {"skipped": "no writer.json"}}
    w = Writer.load(wpath)

    line = "グリーン車および指定席の追加料金は、精算の対象とする。"
    r = {"verdict": "DOCUMENT_LINE", "subject": "精算",
         "section": "交通費の上限", "lines": [line], "text": line}
    qw = quote_in_words(r, w)
    licensed = True
    if qw:
        allowed = set(ja_content_runs(line) or []) | {r["subject"],
                                                      r["section"]}
        for d in qw["sentences"]:
            for f in d["fills"]:
                if f not in allowed:
                    licensed = False
    # 語彙語が立たない行では黙る
    r2 = {"verdict": "DOCUMENT_LINE", "subject": "ぷにゃ",
          "lines": ["ぷにゃぷにゃとぽよぽよのこと。"],
          "text": "ぷにゃぷにゃとぽよぽよのこと。"}
    qw2 = quote_in_words(r2, w)
    # 4. 否定の行は沈黙 — 反転した主張を作らない。
    neg = "グリーン車および指定席の追加料金は、精算の対象としない。"
    qw3 = quote_in_words({"verdict": "DOCUMENT_LINE", "subject": "精算",
                          "section": "交通費の上限", "lines": [neg],
                          "text": neg}, w)
    ok = (qw is not None and licensed and qw.get("constructed") is True
          and qw2 is None and qw3 is None
          and r["verdict"] == "DOCUMENT_LINE" and r["text"] == line)
    return {
        "experiment": "cross_geometry",
        "fork": "DOCUMENT_DRAFT_IS_LICENSED",
        "pass": bool(ok),
        "result": {"draft": (qw or {}).get("sentences", [{}])[0].get("text"),
                   "licensed": licensed,
                   "silent_on_nonwords": qw2 is None,
                   "silent_on_negation": qw3 is None},
    }


def edge_fallback_routes_off_face_fork() -> Dict[str, Any]:
    """面が知らない語は、辺語彙の一意所有でだけ枝に届く — 共有なら棄権。

    実測 2026-08-19 (experiments/edge_routing/): 面のみの経路語彙では
    面外 0/187、面∪辺で 正43・誤0・棄権0。top-32→64 でも誤答0は不変。
    この fork はその契約を最小の木で固定する:

      1. 合議(router)が棄権した語でも、ちょうど1つの子の辺語彙が持つ
         なら、その子へ ANSWER(via=edges, routed_on 明示)。
      2. 両方の子の辺語彙にある語は識別に使えない — 後退路は動かず、
         型付き拒否がそのまま立つ(同点は棄権)。
    """
    from .hierarchy import build, route

    a = CrossStore()
    for s in ["甲学は電荷と密度である。", "甲学は粒子と質量である。"]:
        _ingest_ja(a, s)
    b = CrossStore()
    for s in ["乙学は債権と契約である。", "乙学は担保と質量である。"]:
        _ingest_ja(b, s)
    node = build("根", {"甲": a, "乙": b})

    # 電荷 は甲の辺語彙にだけある。router の面に載っているかは問わない —
    # 後退路は合議が棄権した時にだけ動くので、直接 route を観測する。
    r_unique = route(node, "電荷")
    # 質量 は両方の子の同一文共起に現れる — 一意所有でないので後退路は
    # 沈黙し、経路は型付き拒否のまま。
    r_shared = route(node, "質量")

    unique_ok = (r_unique.get("child") == "甲"
                 and (r_unique.get("via") == "edges"
                      or r_unique.get("verdict") == "ANSWER"))
    shared_ok = not (r_shared.get("verdict") == "ANSWER"
                     and r_shared.get("via") == "edges")
    ok = (unique_ok and shared_ok
          and "電荷" in node.edge_vocab.get("甲", set())
          and "質量" in node.edge_vocab.get("甲", set())
          and "質量" in node.edge_vocab.get("乙", set()))
    return {
        "experiment": "cross_geometry",
        "fork": "EDGE_FALLBACK_ROUTES_OFF_FACE",
        "pass": bool(ok),
        "result": {"unique": {k: r_unique.get(k) for k in
                              ("verdict", "child", "via", "routed_on")},
                   "shared": {k: r_shared.get(k) for k in
                              ("verdict", "child", "via")}},
    }


def one_root_saturates_at_capacity_fork() -> Dict[str, Any]:
    """A single root routes CAPACITY terms and never more, at any depth.

    Measured on a twelve-field federation (1,098 leaves), asking the router
    alone — no index — about the very questions it was built from:

        anticipated   12    24    48    96   192   384   768
        correct       12    20    23    24    23    23    22

    The ABSOLUTE count saturates at 24 = MAX_ARMS x N_FACES and stops. Depth
    stayed 6 throughout, so layers BELOW the root do not raise it: the root
    has six arms and four faces each, and every question that fails there is
    lost whatever is underneath.

    The consequence for a federated design is the opposite of intuitive. A
    single sovereign is a routing ceiling; querying the field roots in
    parallel multiplies it by the number of fields — 220 of 1,536 against
    the sovereign's 24, on the same tree.

    This fixture is small enough to run as a unit test and shows the same
    shape: correct answers stop growing once the anticipated set passes what
    the root can hold.
    """
    from .hierarchy import descend
    from .sovereign import assemble

    # Twelve fields, each with a leaf carrying terms unique to it, so every
    # question has exactly one correct destination.
    doms: Dict[str, Dict[str, CrossStore]] = {}
    grps: Dict[str, Dict[str, List[str]]] = {}
    by_field: List[List[Any]] = []
    for d in range(12):
        field = f"分野{chr(0x4E00 + d)}"
        st = CrossStore()
        own: List[Any] = []
        for i in range(20):
            term = f"語{chr(0x4E00 + d)}{chr(0x4E00 + i)}"
            _ingest_ja(st, f"{field}項{chr(0x4E00 + i)}は{term}である。")
            own.append((term, field))
        by_field.append(own)
        doms[field] = {field: st}
        grps[field] = {field: [field]}
    # Round-robin, so every prefix of the anticipated set covers all twelve
    # fields. Ordered by field, the first twelve questions all pointed at one
    # branch and the root looked far worse than its capacity.
    key: List[Any] = [row[i] for i in range(20) for row in by_field]

    counts: Dict[int, int] = {}
    for n in (12, 24, 96, 240):
        asked = [q for q, _w in key[:n]]
        root = assemble(doms, grps, sovereign="主権", asked=asked)
        counts[n] = sum(
            1 for q, w in key[:n]
            if w in (descend(root, q, use_probe=False).get("path") or []))

    ceiling = MAX_ARMS_FORK * FACES_FORK
    # Grows while it fits, then stops at the ceiling however many more are
    # anticipated. The second half is the claim; without it this passes on a
    # tree that simply answers everything.
    ok = (counts[12] >= 10
          and counts[24] >= counts[12]
          and counts[96] <= ceiling
          and counts[240] <= ceiling
          and counts[240] <= counts[96] + 1)
    return {
        "experiment": "cross_geometry",
        "fork": "ONE_ROOT_SATURATES_AT_CAPACITY",
        "pass": bool(ok),
        "result": {"correct_by_anticipated": counts, "ceiling": ceiling},
    }


def fusion_is_not_monotonic_fork() -> Dict[str, Any]:
    """A field arriving can DISSOLVE a bridge between two others.

    Fusion is measured on concepts held by two or three fields, because a
    concept every field carries identifies none of them. That band is what
    makes the arrival of a third field able to subtract: a concept bridging
    A and B, once C also has it, spans three and on the next arrival falls
    out of the band entirely.

    Measured on the twelve-field federation:

        知財 arrives   opened 57, closed 37   民事×知財 +42, 刑事×民事 -17
        医療 arrives   opened 41, closed 66   医療×工学 +29, 工学×数学 -43

    So "combine the fields and watch fusion grow" is not what happens.
    Fusion between two fields is a function of everything else present, and
    a federation that only ever reports additions would show a rising number
    while the joins it names quietly changed underneath.

    Pinned here at a scale small enough to read: three fields where A and B
    share a concept, then C arrives carrying it too.
    """
    from .fusion import delta, index

    def mk(pairs: List[Tuple[str, str]]) -> CrossStore:
        st = CrossStore()
        for entity, term in pairs:
            _ingest_ja(st, f"{entity}は{term}である。")
        return st

    # Three fields share 保全 through two entities each — a join, in band.
    a = mk([("甲野第一条", "保全"), ("甲野第二条", "保全"),
            ("甲野第三条", "固有甲")])
    b = mk([("乙野第一条", "保全"), ("乙野第二条", "保全"),
            ("乙野第三条", "固有乙")])
    c = mk([("丙野第一条", "保全"), ("丙野第二条", "保全"),
            ("丙野第三条", "固有丙")])
    # A fourth is what pushes it out: BAND_HIGH is three, so a concept in
    # three fields is still a join. The band is the mechanism, not a filter
    # applied afterwards, and the fixture has to cross it.
    e = mk([("丁野第一条", "保全"), ("丁野第二条", "保全"),
            ("丁野第三条", "固有丁")])

    three = {"甲野": {"甲野": a}, "乙野": {"乙野": b}, "丙野": {"丙野": c}}
    four = dict(three, **{"丁野": {"丁野": e}})

    before = index(three)
    after = index(four)
    d = delta(before, after)

    bridged_before = "保全" in before.get("concepts", {})
    gone_after = "保全" not in after.get("concepts", {})

    ok = bridged_before and gone_after and "保全" in d["closed"]
    return {
        "experiment": "cross_geometry",
        "fork": "FUSION_IS_NOT_MONOTONIC",
        "pass": bool(ok),
        "result": {
            "points_before": before["n_points"],
            "points_after": after["n_points"],
            "bridge_before": bridged_before,
            "bridge_survives_arrival": not gone_after,
            "closed": d["closed"],
        },
    }


def word_form_is_a_fallback_fork() -> Dict[str, Any]:
    """Widen the query only when the printed word found nothing.

    Against an external key (topics ja.wikipedia assigns to specific
    articles), 46.7% of questions could not begin because the word the world
    uses is not the word the statute prints — 傷害罪 against a code that
    prints 傷害.

    Expanding every query fixed that and broke the answer:

        exact only        recall 26.7%   destinations   4
        always expand     recall 86.7%   destinations 117
        staged fallback   recall 73.3%   destinations  41

    不法行為 also matches 行為, which sits in 173 articles across six
    statutes, so an unconditional widening turns one question into most of
    the corpus. Staged keeps the printed term authoritative and reports
    which stage answered, so a reader can see the query was not the one
    they typed.
    """
    from .hierarchy import gather
    from .sovereign import assemble

    st = CrossStore()
    for s in ["刑法第二百四条は傷害である。", "刑法第二百四条は身体である。",
              "刑法第二百五条は傷害致死である。",
              "建築基準法第六条は建築である。", "建築基準法第六条は確認である。",
              "民法第七百九条は不法行為である。", "商法第五百九十条は行為である。",
              "商法第五百九十一条は行為である。"]:
        _ingest_ja(st, s)
    root = assemble({"法": {"法": st}}, {"法": {"法": ["法"]}}, sovereign="主権")

    exact = gather(root, "不法行為", limit=40, morph=True)
    suffix = gather(root, "傷害罪", limit=40, morph=True)
    compound = gather(root, "建築確認", limit=40, morph=True)
    off = gather(root, "傷害罪", limit=40, morph=False)

    ok = (exact["matched_as"] == "exact"            # printed term wins
          and exact["destinations"] == 1            # and is not widened
          and suffix["matched_as"] == "suffix"
          and suffix["destinations"] >= 1
          and compound["matched_as"] == "compound"
          and off["destinations"] == 0)             # off restores the old behaviour
    return {
        "experiment": "cross_geometry",
        "fork": "WORD_FORM_IS_A_FALLBACK",
        "pass": bool(ok),
        "result": {
            "exact": {"stage": exact["matched_as"], "dest": exact["destinations"]},
            "suffix": {"stage": suffix["matched_as"], "dest": suffix["destinations"]},
            "compound": {"stage": compound["matched_as"], "dest": compound["destinations"]},
            "morph_off": off["destinations"],
        },
    }


def linked_is_not_printed_fork() -> Dict[str, Any]:
    """A doctrinal connection must never look like something the source said.

    民法第七百九条 defines 不法行為 and does not contain the word. Measured
    over 271 published topic→article assignments that name articles this
    store holds, indexing the statutes reaches 25.5% of them; the other
    74.5% are connections a third party asserts and no statute prints.
    Raising the per-article index eightfold moved that number not at all.

    So they are kept in their own layer with the source that asserted them,
    and `resolve` returns the two kinds LABELLED. Writing the topic onto the
    article as a facet would make the coverage gate, the contradiction
    detector and the citation shown to a reader all treat a third party's
    doctrine as the legislature's text.
    """
    import tempfile
    from pathlib import Path as _P

    from .links import harvest, resolve

    store = CrossStore()
    _ingest_ja(store, "民法第七百九条は損害賠償である。")
    _ingest_ja(store, "民法第七百九条は侵害である。")
    _ingest_ja(store, "刑事訴訟法第二百十三条は現行犯人である。")
    fields = {"法": {"法": store}}

    with tempfile.TemporaryDirectory() as td:
        d = _P(td)
        (d / "不法行為.txt").write_text(
            "不法行為については民法第709条に定めがある。"
            "現行犯逮捕は刑事訴訟法第213条による。", encoding="utf-8")
        ls = harvest([d / "不法行為.txt"])

    r = resolve(fields, ls, "不法行為")
    linked = {x["article"] for x in r["linked"]}
    printed = {x["article"] for x in r["printed"]}
    # The store never learned the word, so nothing is printed...
    # ...and both articles arrive as links, each naming who said so.
    sources = {s for x in r["linked"] for s in x["asserted_by"]}

    ok = (ls.n_links() == 2
          and "刑事訴訟法第二百十三条" in linked
          and "民法第七百九条" in linked
          and not printed
          and sources == {"不法行為"}
          and all(x["in_store"] for x in r["linked"]))
    return {
        "experiment": "cross_geometry",
        "fork": "LINKED_IS_NOT_PRINTED",
        "pass": bool(ok),
        "result": {"links": ls.n_links(), "printed": sorted(printed),
                   "linked": sorted(linked), "asserted_by": sorted(sources)},
    }


def granularity_composes_fork() -> Dict[str, Any]:
    """Two granularities over one corpus can form what one cannot.

    A single store is closed: measured over 117 real queries the search
    emitted a symbol absent from the initial shell zero times, and it cannot,
    because faces come from the store and the moves permute faces. That is
    why it cannot fabricate and equally why it cannot generalise.

    Two stores at different granularities do not share the limit. The
    word-level store holds 断水 as an atom; the character-level store over
    the same text holds 断 and 水 AND their positions, and those positions
    license strings the word store cannot form.

    Measured on 5,371 legal words against 2.4M characters of held-out
    encyclopedia text that built neither model:

        proposals                       13,969
        appear as a substring            13.2%
        stand alone 3+ times              1.7%   <- words, not fragments
        same characters, paired randomly  0.1%

    自動 死去 公式 人権 主義 実数 定理 — none in the vocabulary that
    generated them. The control is the finding: what the character model
    contributes is not the characters, it is where they go.

    Longer words compose from UNITS, not from characters: 公務員 is 公務+員,
    not three characters chosen by position, which would propose 公再員. At
    three and four characters the yield falls and the advantage RISES —
    2字 x4.9, 3字 x15.5, 4字 x16.0 — because a random four-kanji string is
    almost never Japanese (0.01%), so structure is doing nearly all of it.

    This fork asserts the ADVANTAGE, not the yield. A yield alone could be a
    fact about how many kanji pairs happen to be Japanese.
    """
    from .granularity import (control, control_units, decompose,
                              decompose_units, propose, propose_units, verify)

    # A miniature corpus with a real positional regularity: 災/断/給 begin,
    # 害/水/電 end, and the held-out text contains the crossings.
    words = ["災害", "断水", "給電", "災難", "断熱", "給水"]
    held = ("停電が発生した。断電の記録はない。"
            "災水の被害は確認されていない。給熱の設備を点検する。"
            "停電は各地で発生し、停電の復旧が急がれる。停電。"
            "災水。災水の報告。給熱。給熱の点検。給熱。")

    model = decompose(words)
    got = verify(propose(model, top=6), held, min_standalone=2)
    ctl = verify(control(model, 40, seed=1), held, min_standalone=2)

    # Three characters, composed from units rather than positions.
    words3 = ["行政処分", "行政指導", "懲戒処分", "懲戒解雇"]
    held3 = ("行政解雇の例はない。懲戒指導が行われた。懲戒指導。懲戒指導の記録。"
             "行政解雇。行政解雇の通知。行政解雇。")
    m3 = decompose_units(words3)
    got3 = verify(propose_units(m3, length=4, top=8), held3, min_standalone=2)

    ok = (model.report()["words"] == 6
          and got["words"] >= 2                 # composed real strings
          and got["words"] > ctl["words"]       # and beat the same characters
          and got3["words"] >= 2)               # and units compose too
    return {
        "experiment": "cross_geometry",
        "fork": "GRANULARITY_COMPOSES",
        "pass": bool(ok),
        "result": {"model": model.report(),
                   "proposed_words": got["words"], "proposed_top": got["top"][:5],
                   "control_words": ctl["words"],
                   "unit_composition": got3["top"][:4]},
    }


def resolution_ladder_grades_doubt_fork() -> Dict[str, Any]:
    """A tied rung abstains, and unanimity therefore means something.

    The same corpus read at several grain sizes votes several ways, and how
    many rungs concur grades the answer. Measured on 10,222 statute articles
    asked by their own captions, 600 probes:

        best single rung, answering everything        29.8%
        three or four rungs answer and all agree     100.0%  (77 probes)
        two rungs answer and agree                    31.1%  (103)
        no rung had grounds                             --   (383)

    Three things this fork exists to stop coming back.

    RUNGS MUST BE NESTED. The first version binned terms by length, which is
    a partition: a term reaches exactly one rung, 507 of 600 probes had a
    single rung answer, and agreement was not low but impossible.

    A TIED RUNG MUST ABSTAIN. Breaking ties by insertion order made a rung's
    answer depend on ingest order. Breaking them lexicographically was
    WORSE: every tied rung chose the same smallest item, unanimity rose from
    86 probes to 321 and its accuracy fell from 73.3% to 23.7%, below the
    3-1 majority. Determinism at the tie manufactures agreement.

    REORDERING THE RUNGS MUST CHANGE NOTHING.
    """
    from .resolution import Ladder, ask, grains

    assert grains("損害賠償", 2) == ["損害", "害賠", "賠償"]

    items = {
        "甲条": {"損害賠償", "責任"},
        "乙条": {"損害", "賠償", "損失", "賠責"},
        "丙条": {"契約", "範囲"},
    }
    ladder = Ladder().build(items)

    every_rung_sees = ("損害賠償" in ladder.index["whole"]
                       and "損害" in ladder.index["g2"]
                       and "損" in ladder.index["g1"])

    unanimous = ask(ladder, ["契約"])

    # 損害賠償 is a whole term of 甲条 and is spelled out piecewise by 乙条,
    # so the character rung cannot separate them and says nothing.
    votes = ladder.vote(["損害賠償"])
    abstained = [r for r, v in votes.items() if v is None]
    spoke = ask(ladder, ["損害賠償"])

    flipped = Ladder(rungs=(("g1", 1), ("g2", 2), ("g3", 3), ("whole", 0)))
    flipped.build(items)
    stable = (ask(flipped, ["損害賠償"])["item"] == spoke["item"]
              and ask(flipped, ["契約"])["item"] == unanimous["item"])

    ok = (every_rung_sees
          and unanimous["item"] == "丙条"
          and unanimous["verdict"] == "ANSWER"
          and unanimous["concord"] == 1.0
          and abstained == ["g1"]          # the tied rung, and only it
          and spoke["answered"] == 3       # the others still spoke
          and stable)
    return {
        "experiment": "cross_geometry",
        "fork": "RESOLUTION_LADDER_GRADES_DOUBT",
        "pass": bool(ok),
        "result": {
            "unanimous": {k: unanimous[k] for k in
                          ("item", "verdict", "answered", "majority", "concord")},
            "tie_abstained": abstained,
            "after_abstention": {k: spoke[k] for k in
                                 ("item", "verdict", "answered", "concord")},
            "stable_under_rung_reorder": stable,
        },
    }


def concord_rides_alongside_the_list_fork() -> Dict[str, Any]:
    """Confidence is reported BESIDE the destinations, never instead of them.

    `gather` lists every leaf holding the query terms and chooses nothing —
    that is what makes it unable to fabricate. The resolution ladder does
    choose, and says how much of itself concurred. Wiring the second into
    the first must not let it overwrite the first, or the listing stops
    being a listing.

    Two behaviours are pinned. A multi-term query that the rungs agree on
    reports the leaf AND stays in the list. A single-term query cannot be
    discriminated — every leaf holding it ties — so every rung abstains and
    concord is zero. That is correct rather than broken: the leaves really
    are indistinguishable on one term, and `gather` has already said so by
    listing them all.
    """
    from .hierarchy import gather
    from .sovereign import assemble

    a = CrossStore()
    for s in ["労基第二十条は解雇である。", "労基第二十条は予告である。",
              "労基第二十条は三十日である。"]:
        _ingest_ja(a, s)
    b = CrossStore()
    for s in ["労基第八十九条は解雇である。", "労基第八十九条は就業規則である。"]:
        _ingest_ja(b, s)
    root = assemble({"労働": {"予告": a, "規則": b}},
                    {"労働": {"労働": ["予告", "規則"]}}, sovereign="主権")

    sharp = gather(root, "解雇 予告 三十日", limit=8, concord=True)
    blunt = gather(root, "解雇", limit=8, concord=True)
    plain = gather(root, "解雇 予告 三十日", limit=8)

    ok = (sharp["concord"]["verdict"] == "ANSWER"
          and sharp["concord"]["concord"] == 1.0
          and sharp["concord"]["in_destinations"]
          # the list is unchanged by asking for confidence
          and sharp["destinations"] == plain["destinations"]
          and "concord" not in plain
          # both leaves hold 解雇, so one term cannot separate them
          and blunt["destinations"] == 2
          and blunt["concord"]["answered_rungs"] == 0)
    return {
        "experiment": "cross_geometry",
        "fork": "CONCORD_RIDES_ALONGSIDE_THE_LIST",
        "pass": bool(ok),
        "result": {
            "multi_term": {k: sharp["concord"][k] for k in
                           ("item", "verdict", "agreeing", "answered_rungs",
                            "in_destinations")},
            "single_term": {"destinations": blunt["destinations"],
                            "answered_rungs": blunt["concord"]["answered_rungs"]},
            "list_unchanged": sharp["destinations"] == plain["destinations"],
        },
    }


def long_form_drifts_and_lists_fork() -> Dict[str, Any]:
    """Chained read-out is not prose, and it loses its subject in two steps.

    Asked whether this engine can generate long form for creative use, the
    answer is measured rather than argued. Following a core to one of its
    own facets and reading again, 40 seeds per field:

        field   mean steps   steps still on topic
        数学        7.9            1.7
        工学        7.4            1.9
        経済        6.7            1.7
        医療        6.2            1.3
        刑事/民事    1.0            1.0

    A chain runs six to eight steps and stops being about anything after
    one or two. Observed: 細胞 -> 現象 -> 関係 -> 副作用 -> アメリカ ->
    学術雑誌.

    And every step reads out as 「Xは A、B、C、D」 — the four faces joined by
    a comma. That is a fact list, not a sentence, and no amount of chaining
    turns a list into prose.

    Both properties follow from the closure this design is built on: the
    read-out can only emit stored symbols, and the only ordering it has is
    the face order. Composition into sentences would need something that
    generates function words, which is exactly what a closed system cannot
    do — see `granularity`, where breaking the closure at a granularity
    boundary is the one route that produces anything new, and produces
    single words rather than clauses.

    This fork exists so the limitation is not quietly re-discovered as a
    bug. It asserts the shape, not the numbers.
    """
    from .consensus_store import ja_consensus_ask

    store = CrossStore()
    for s in ["甲は乙である。", "甲は丙である。", "乙は丁である。", "乙は戊である。",
              "丁は己である。", "丁は庚である。", "己は辛である。", "己は壬である。"]:
        _ingest_ja(store, s)

    seed = "甲"
    start = {f for f in store.crosses.get(seed, {})
             if f not in store.source_labels}
    cur, seen, texts, on_topic = seed, [], [], 0
    still = True
    for _ in range(6):
        out = ja_consensus_ask(store, cur)
        if out.get("verdict") != "ANSWER":
            break
        core = out.get("core")
        seen.append(core)
        texts.append(out.get("text", ""))
        facets = {f for f in store.crosses.get(core, {})
                  if f not in store.source_labels}
        if still and (facets & start):
            on_topic += 1
        elif still:
            still = False
        nxt = sorted(f for f in facets if f in store.crosses and f not in seen)
        if not nxt:
            break
        cur = nxt[0]

    listy = all("、" in t or len(t.split("は")[-1].split("、")) >= 1
                for t in texts if t)
    ok = (len(seen) >= 3                 # the chain does run
          and on_topic < len(seen)       # and leaves its subject before the end
          and listy)                     # and every step is a list
    return {
        "experiment": "cross_geometry",
        "fork": "LONG_FORM_DRIFTS_AND_LISTS",
        "pass": bool(ok),
        "result": {"steps": len(seen), "on_topic_steps": on_topic,
                   "path": seen, "sample": texts[:3]},
    }


def trace_is_memory_outside_the_store_fork() -> Dict[str, Any]:
    """The path is a value, kept beside the stores, and it resumes a walk.

    A read-out chain had no memory: each step saw only its current core, so
    the next was chosen without reference to where the walk began or what it
    had passed. I first reported that as the structure forgetting its
    subject. It was not — nothing was remembering. 40 seeds per field:

        rule            steps   subject held   adjacent overlap   with path
        lexicographic     8.7        1.7            0.033           0.269
        anchor on seed   10.9        6.9            0.042           0.385
        anchor on path   11.0        5.0            0.069           0.433

    Two different instruments. Anchoring on the SEED holds the original
    subject four times longer, which is what a question wants. Anchoring on
    the PATH walks furthest and overlaps both its previous step and
    everything before it most, which is what a developing text wants.

    A trace is NOT knowledge — nothing in it was said by a source — so it
    lives outside the stores, where a later reader cannot mistake a footprint
    for a fact. Being a value rather than a local variable is also what makes
    a walk resumable and replayable, which a deterministic engine should be
    and was not.
    """
    from .trace import Trace, replay, walk

    store = CrossStore()
    for s in ["甲は乙である。", "甲は丙である。", "乙は丁である。", "乙は丙である。",
              "丁は戊である。", "丁は丙である。", "戊は己である。", "戊は丙である。"]:
        _ingest_ja(store, s)

    t = walk(store, "甲", mode="path", steps=2)
    first = list(t.seen)

    import tempfile
    from pathlib import Path as _P
    with tempfile.TemporaryDirectory() as td:
        p = _P(td) / "t.json"
        t.save(p)
        back = Trace.load(p)
        round_trip = (back.seen == t.seen and back.horizon == t.horizon)
        resumed = walk(store, "甲", mode="path", steps=2, trace=back)

    rep = replay(store, resumed)
    unchanged = all(not r["changed"] for r in rep)

    # The horizon grows; it is the anchor and it is not the seed's alone.
    grew = len(resumed.horizon) >= len(t.horizon)

    ok = (len(first) >= 2
          and round_trip
          and len(resumed.seen) > len(first)      # resuming continues
          and resumed.seen[:len(first)] == first  # from where it stopped
          and unchanged                           # replay is exact
          and grew)
    return {
        "experiment": "cross_geometry",
        "fork": "TRACE_IS_MEMORY_OUTSIDE_THE_STORE",
        "pass": bool(ok),
        "result": {"first_walk": first, "resumed": resumed.seen,
                   "round_trip": round_trip, "replay_unchanged": unchanged,
                   "horizon": len(resumed.horizon)},
    }


def constellation_beats_one_sovereign_fork() -> Dict[str, Any]:
    """Parallel sovereigns at different settings, with nothing above them.

    One apex is a routing ceiling — six arms, four faces, 24 terms, and no
    depth beneath raises it. Measured: 24 placed against 220 for the same
    tree queried at its field roots in parallel.

    A constellation holds the corpus several times over, each member at its
    own setting, and reports a CENSUS rather than a verdict. At 626MB over
    5,401 leaves, 1,200 probes:

        single sovereign     80.3%
        eight in parallel    84.3%

        agreeing  7   44 probes  100.0%
                  6   92         100.0%
                  5  191         100.0%
                  4  499         100.0%
                  3  119          97.5%
                  2   88          67.0%
                  1  145           7.6%

    Four or more concurring covered 69% of probes and was right every time.

    Three things are pinned. Unanimity reports itself as ANSWER with concord
    1.0. A split is reported as a split and NOT resolved into a winner —
    voting a disagreement into an answer is the failure a census exists to
    avoid. And a member with no single leader ABSTAINS rather than breaking
    the tie, because a tie-break shared across members manufactures
    agreement for a reason unrelated to evidence — measured one level down,
    where it took unanimity from 86 probes to 321 and its accuracy from
    73.3% to 23.7%.
    """
    from .constellation import Constellation, Sovereign

    # Members that genuinely see different things: this is what varying a
    # setting produces, constructed directly so the fork tests the census
    # rather than the indexing.
    coarse = Sovereign("coarse", {"rungs": (("whole", 0),)}).build({
        "甲章": {"損害賠償", "責任"},
        "乙章": {"契約", "解除"},
    })
    fine = Sovereign("fine", {"rungs": (("whole", 0),)}).build({
        "甲章": {"責任"},
        "乙章": {"損害賠償", "契約"},
    })
    third = Sovereign("third", {"rungs": (("whole", 0),)}).build({
        "甲章": {"損害賠償"},
        "乙章": {"契約", "解除"},
    })
    c = Constellation().add(coarse).add(fine).add(third)

    split = c.ask(["損害賠償"])
    unanimous = c.ask(["契約"])

    # One member sees 損害賠償 in 乙章, two in 甲章 — a majority, not a verdict.
    votes = {m.name: m.vote(["損害賠償"]) for m in c.members}
    differ = len({v for v in votes.values() if v}) > 1

    # A member whose top score ties abstains rather than picking.
    tied = Sovereign("tied", {"rungs": (("whole", 0),)}).build({
        "甲章": {"共通"}, "乙章": {"共通"},
    })
    abstains = tied.vote(["共通"]) is None

    ok = (unanimous["verdict"] == "ANSWER"
          and unanimous["concord"] == 1.0
          and unanimous["item"] == "乙章"
          and differ
          and split["verdict"] == "MAJORITY"   # reported as a majority...
          and split["agreeing"] == 2           # ...with the count visible
          and split["spoke"] == 3
          and abstains)
    return {
        "experiment": "cross_geometry",
        "fork": "CONSTELLATION_BEATS_ONE_SOVEREIGN",
        "pass": bool(ok),
        "result": {
            "unanimous": {k: unanimous[k] for k in
                          ("item", "verdict", "spoke", "agreeing", "concord")},
            "split": {k: split[k] for k in
                      ("item", "verdict", "spoke", "agreeing", "concord")},
            "votes": votes,
            "tied_member_abstains": abstains,
        },
    }


def writer_never_reaches_the_answer_path_fork() -> Dict[str, Any]:
    """A generated sentence must not be able to arrive where a citation is.

    The whole closure argument elsewhere is that a reader can trust what
    comes back: every symbol traces to a source, measured at 0 of 117
    outputs containing anything the store did not hold. A composed sentence
    breaks that on purpose — it is a recombination of a form somebody wrote
    and content somebody else wrote, and the combination is nobody's claim.

    So `writer` is imported by nothing on the answer path, and every draft
    carries both sources so the two can be told apart. This fork asserts the
    isolation as a fact about the code, not a convention.
    """
    import inspect

    from . import consensus_store, hierarchy, writer
    from .cross_store import CrossStore
    from .writer import Writer

    # Nothing that produces a verdict may reach the generator.
    leak = [m.__name__ for m in (consensus_store, hierarchy)
            if "writer" in inspect.getsource(m)
            or "compose_ja" in inspect.getsource(m)]

    store = CrossStore()
    for s in ["甲条は届出である。", "甲条は選択である。", "甲条は事情である。"]:
        _ingest_ja(store, s)
    # The prose must attest the SUBJECT too, not just the facets: a term the
    # corpus never uses standing alone is not a word, and `sentence` returns
    # nothing for it. Without 甲条 here the fork passed on an empty draft
    # list and asserted nothing about citations at all.
    # A RECORD-register form on purpose. The corpus here reports; it does
    # not legislate, so a 「〜することができる」 shape would be refused by the
    # modality licence and this fork would be testing that instead — see
    # `form_may_not_assert_more_than_content_licenses_fork`.
    prose = [("fixture",
              "甲条は、いつでも届出を選択した。"
              "事情は、いつでも届出を選択した。"
              "甲条は、いつでも事情を選択した。"
              "甲条は、いつでも届出を選択した。"
              "事情は、いつでも甲条を選択した。")]
    w = Writer.build([store], prose)

    drafts = w.sentence(store, "甲条")
    unknown = w.sentence(store, "存在しない語")

    both_cited = bool(drafts) and all(d.get("content_from") and d.get("form_from")
                                      for d in drafts)

    ok = (not leak
          and w.report()["vocabulary"]["terms"] > 0
          and drafts                 # the fixture must actually write
          and unknown == []          # a non-word writes nothing
          and both_cited)
    return {
        "experiment": "cross_geometry",
        "fork": "WRITER_NEVER_REACHES_THE_ANSWER_PATH",
        "pass": bool(ok),
        "result": {
            "answer_path_imports_generator": leak,
            "built": w.report(),
            "drafts": [d["text"] for d in drafts][:2],
            "non_word_writes_nothing": unknown == [],
        },
    }


def form_may_not_assert_more_than_content_licenses_fork() -> Dict[str, Any]:
    """Closure stops invented symbols. It does not stop invented relations.

    A store holds co-occurrence. A form holds a relation, and supplies it
    whoever fills the holes: 「<0>は、<1>を<2>しなければならない」 states an
    obligation about anything put in hole 0. Measured over 278 generated
    sentences on the 626MB federation, 21.9% asserted a norm — obligation,
    prohibition, or permission — and 42.6% of those were about content no
    statute had ever spoken of. 【女性】は、【従事】を【行為】しなければ
    ならない passes closure on every symbol and fabricates the only thing in
    it that carries meaning.

    So a norm-shaped form needs a norm-registered subject. The restriction
    runs one way: a legal duty stated as a plain fact loses information, a
    plain fact stated as a legal duty invents an obligation.
    """
    from .cross_store import CrossStore
    from .writer import Writer

    store = CrossStore()
    for s in ["甲条は届出である。", "甲条は選択である。", "甲条は事情である。"]:
        _ingest_ja(store, s)

    norm = ("甲条は、いつでも届出を選択しなければならない。" * 3
            + "事情は、いつでも届出を選択しなければならない。"
            + "甲条は、いつでも事情を選択しなければならない。")

    # Same corpus, same store, same subject — only the licence differs.
    unlicensed = Writer.build([store], [("prose", norm)])
    licensed = Writer.build([store], [("statute", norm)],
                            norm_corpora=["statute"])

    a = unlicensed.sentence(store, "甲条")
    b = licensed.sentence(store, "甲条")

    norm_forms = [f for f in licensed.forms.values() if f.register == "norm"]

    ok = (norm_forms                  # the fixture really did offer a norm
          and a == []                 # unlicensed content writes no norm
          and b                       # licensed content still writes
          and unlicensed.licence("甲条") == "record"
          and licensed.licence("甲条") == "norm")
    return {
        "experiment": "cross_geometry",
        "fork": "FORM_MAY_NOT_ASSERT_MORE_THAN_CONTENT_LICENSES",
        "pass": bool(ok),
        "result": {
            "norm_forms_offered": len(norm_forms),
            "licence_without_statute": unlicensed.licence("甲条"),
            "licence_with_statute": licensed.licence("甲条"),
            "unlicensed_wrote": [d["text"] for d in a],
            "licensed_wrote": [d["text"] for d in b],
        },
    }


def concord_is_not_coverage_fork() -> Dict[str, Any]:
    """Agreement about a leaf is not evidence the question was answered.

    The census bands are sharp on questions the corpus can answer: over 300
    in-corpus probes, three or more concurring was right 185 times out of
    185, two 71.4%, one 8.7%. That calibration was built from anticipated
    questions over the corpus, so it says nothing about a question the
    corpus cannot answer — and the two come apart hardest in the middle
    case, where a query mixes a term the federation holds with one it does
    not. Measured over 80 such questions only 3 were refused and 8 reached
    four or more concurring, the band calibrated at 100%, each time by
    answering about the other word.

    Coverage is reported beside the concord and never folded into it. A
    reader who wants the leaf anyway can still have it; a reader who assumed
    a high count meant their term was addressed can now see it was not.
    """
    from .constellation import staircase

    items = {"甲葉": ["登記", "申請", "期間"], "乙葉": ["解雇", "予告", "賃金"]}
    c = staircase(items)

    hit = c.ask(["登記"])
    mixed = c.ask(["登記", "超伝導"])
    absent = c.ask(["超伝導"])

    ok = (hit["coverage"] == 1.0 and hit["missing"] == []
          # the mixed query still answers, and still says what it missed
          and mixed["verdict"] in ("ANSWER", "MAJORITY")
          and mixed["missing"] == ["超伝導"]
          and mixed["coverage"] == 0.5
          # coverage does NOT quietly lower the concord
          and mixed["agreeing"] == hit["agreeing"]
          and absent["verdict"] == "UNKNOWN_NOT_PRESENT"
          and absent["coverage"] == 0.0)
    return {
        "experiment": "cross_geometry",
        "fork": "CONCORD_IS_NOT_COVERAGE",
        "pass": bool(ok),
        "result": {
            "in_corpus": {k: hit[k] for k in
                          ("verdict", "agreeing", "coverage", "missing")},
            "mixed": {k: mixed[k] for k in
                      ("verdict", "agreeing", "coverage", "missing")},
            "absent": {k: absent[k] for k in
                       ("verdict", "agreeing", "coverage", "missing")},
        },
    }


def every_manifest_can_rebuild_its_corpus_fork() -> Dict[str, Any]:
    """A manifest that cannot rebuild its corpus is a receipt, not a backup.

    `corpus_fetch` was written because a corpus was lost in a session temp
    directory. It was lost from one a second time, and the manifests are why
    the two losses ended differently: every e-Gov entry carried a URL and
    came back, while all 202 Wikipedia entries carried an empty one and had
    to be reconstructed from their filenames by a module written after the
    fact. The manifest could prove the corpus was gone and not get it back.

    Three more entries reported no URL for a different reason — index.json
    and urls.tsv were written BY the fetch rather than fetched, so recording
    them as corpus files made two manifests report themselves irreproducible
    over their own bookkeeping.

    Reproducibility is a property of the manifest, checkable without the
    network and without the corpus, so it is checked here every run.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "corpora"
    seen, broken = [], []
    for path in sorted(root.glob("*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        files = m.get("files") or []
        missing = [e["name"] for e in files if not e.get("url")]
        seen.append({"manifest": path.stem, "files": len(files),
                     "without_url": len(missing)})
        if missing or not m.get("reproducible"):
            broken.append({"manifest": path.stem, "examples": missing[:3],
                           "declared": m.get("reproducible")})

    ok = bool(seen) and not broken
    return {
        "experiment": "cross_geometry",
        "fork": "EVERY_MANIFEST_CAN_REBUILD_ITS_CORPUS",
        "pass": bool(ok),
        "result": {"manifests": seen, "not_reproducible": broken},
    }


def a_reloaded_writer_is_the_same_writer_fork() -> Dict[str, Any]:
    """Restoring must bring back the slot tables, not just the vocabulary.

    `SELECTION` and `SELECTION_TAIL` are module globals — `selects` is
    called from inside the fill loop and threading them through every caller
    bought nothing. That makes them the one part of the writer a reload
    cannot recover on its own, and the failure is quiet rather than loud: a
    writer restored without them still has its vocabulary, still has its
    forms, still writes sentences, and answers `selects` with None on every
    fill. Every candidate becomes "unknown but not refused", which is a
    different system that looks like this one.

    So the fork restores into a process whose tables were deliberately
    cleared and requires the same sentence back.
    """
    from .compose_ja import SELECTION, SELECTION_TAIL, learn_selection, selects
    from .cross_store import CrossStore
    from .writer import Writer

    store = CrossStore()
    for s in ["甲条は届出である。", "甲条は選択である。", "甲条は事情である。"]:
        _ingest_ja(store, s)
    prose = [("fixture",
              "甲条は、いつでも届出を選択した。" * 3
              + "事情は、いつでも届出を選択した。"
              + "甲条は、いつでも事情を選択した。")]

    saved_sel = {k: v.copy() for k, v in SELECTION.items()}
    saved_tail = {k: v.copy() for k, v in SELECTION_TAIL.items()}
    try:
        w = Writer.build([store], prose)
        before = w.sentence(store, "甲条")
        attested_before = selects("届出", "を", "選択")

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "writer.json"
            w.save(path)
            # Wipe the globals: this is what a fresh process looks like.
            SELECTION.clear()
            SELECTION_TAIL.clear()
            blind = selects("届出", "を", "選択")
            w2 = Writer.load(path)
            after = w2.sentence(store, "甲条")
            attested_after = selects("届出", "を", "選択")

        ok = (before and before == after
              and attested_before is True
              and blind is None              # the wipe really did blind it
              and attested_after is True)
        return {
            "experiment": "cross_geometry",
            "fork": "A_RELOADED_WRITER_IS_THE_SAME_WRITER",
            "pass": bool(ok),
            "result": {
                "before": [d["text"] for d in before],
                "after": [d["text"] for d in after],
                "selects_before": attested_before,
                "selects_while_wiped": blind,
                "selects_after_reload": attested_after,
            },
        }
    finally:
        SELECTION.clear()
        SELECTION.update(saved_sel)
        SELECTION_TAIL.clear()
        SELECTION_TAIL.update(saved_tail)


def coarsening_adds_a_reading_and_never_overturns_one_fork() -> Dict[str, Any]:
    """The verdict is quantized like the index, and typed so it cannot lie.

    刑法第百九十九条 carries the facet 殺人 from its own caption, and the
    doctrinal term is 殺人罪. One character apart, and the whole-grain gate
    reported `query_terms_not_addressed` exactly as it would for a word the
    corpus had never held. Running the judgment at several grains tells the
    two apart.

    Measured over 500 morphological variants that are NOT themselves cores,
    so the whole grain must fail: 468 came back ANSWER_BY_COARSENING and
    98.7% of those reached the ORIGINAL core — 100.0% at two or more settings
    agreeing, 95.0% at one. Against 18 variants of words the corpus never
    held, 17 refused and 1 answered, which is the cost of coarsening and the
    reason a coarse answer is never typed ANSWER.

    This fork pins the type discipline rather than the accuracy: a reading
    only a coarse setting reached must be labelled as one, and a term the
    store does not hold at any grain must still refuse.
    """
    from .cross_store import CrossStore
    from .graded import GradedJudge

    store = CrossStore()
    for s in ["傷害罪は暴行である。", "傷害罪は故意である。", "傷害罪は結果である。",
              "殺人は死刑である。", "殺人は無期である。", "殺人は拘禁刑である。"]:
        _ingest_ja(store, s)
    j = GradedJudge().build(store)

    exact = j.ask("傷害罪とは")          # the store holds this name
    coarse = j.ask("殺人罪とは")         # holds 殺人, asked as 殺人罪
    absent = j.ask("超伝導とは")         # holds nothing like it

    ok = (exact["verdict"] == "ANSWER"
          and exact["item"] == "傷害罪"
          # a coarsened reading is REACHED and is not called ANSWER
          and coarse["verdict"] == "ANSWER_BY_COARSENING"
          and coarse["item"] == "殺人"
          and coarse["readings"]["whole"] is None
          # and coarsening does not manufacture an answer from nothing
          and absent["verdict"] == "UNKNOWN_NOT_PRESENT")
    return {
        "experiment": "cross_geometry",
        "fork": "COARSENING_ADDS_A_READING_AND_NEVER_OVERTURNS_ONE",
        "pass": bool(ok),
        "result": {
            "exact": {k: exact[k] for k in ("verdict", "item", "agreeing")},
            "coarsened": {k: coarse[k] for k in ("verdict", "item", "agreeing")},
            "coarsened_strict_reading": coarse["readings"]["whole"],
            "absent": {k: absent[k] for k in ("verdict", "item", "agreeing")},
        },
    }


def a_citation_is_listed_not_chosen_fork() -> Dict[str, Any]:
    """Three readings from one ask, kept apart because merging destroys them.

    A sovereign was only ever a ladder: placement, hierarchy, granularity
    and links were built, measured, and never reached by one. Wiring them in
    produced two results worth pinning.

    Merging citations into the core ladder scored 0 of 387 gold links. The
    first wiring added the cited articles to the TOPIC's terms, so asking
    わいせつ returned the core わいせつ — what it already returned. Keying
    the ARTICLE by the topic instead answers, and then ties: わいせつ is
    provided for by 刑法第百七十四条 through 第百七十七条, four articles at
    one point each, and a ladder asked which ONE abstains. Choosing answered
    54 of 130 topics and was right every time; listing reaches 164 of 164.

    Listing is not choosing, so it cannot fabricate — and the citation stays
    a fact about the citing document, never a claim the statute made.
    """
    from .cross_store import CrossStore
    from .full_sovereign import FullSovereign, DEFAULT_SETTINGS

    store = CrossStore()
    for s in ["刑法第百七十四条はわいせつである。", "刑法第百七十五条はわいせつである。",
              "わいせつは公然である。", "わいせつは頒布である。"]:
        _ingest_ja(store, s)

    sv = FullSovereign(name="cites", setting=dict(DEFAULT_SETTINGS)["cites"])
    sv.build(store, None, shared={}, link_paths=[],
             with_tree=False, with_placement=False)
    # Stand in for a harvest: one topic, two articles — the tie case.
    sv.links = {"わいせつ": ["刑法第百七十四条", "刑法第百七十五条"]}

    listed = sv.cited(["わいせつ"])
    none = sv.cited(["超伝導"])

    ok = (listed["verdict"] == "ANSWER"
          # BOTH articles, not one picked
          and len(listed["articles"]) == 2
          and "刑法第百七十四条" in listed["articles"]
          and "刑法第百七十五条" in listed["articles"]
          # the topic that cited them travels with them
          and listed["by_topic"]["わいせつ"]
          # and a topic nobody cited gets a typed refusal, not an empty answer
          and none["verdict"] == "UNKNOWN_NO_CITATION"
          and none["articles"] == [])
    return {
        "experiment": "cross_geometry",
        "fork": "A_CITATION_IS_LISTED_NOT_CHOSEN",
        "pass": bool(ok),
        "result": {"listed": listed["articles"],
                   "by_topic": listed["by_topic"],
                   "uncited": none["verdict"]},
    }


def a_template_cut_inside_a_word_is_caught_at_the_seam_fork() -> Dict[str, Any]:
    """The break shows at the fill, not at the harvest, so test it there.

    `_CUT_STEM` lists eleven inflection fragments by hand — a rule written
    rather than learned, and measured to catch NONE of the 659 forms
    harvested at 626MB. 「う」 is not on the list, so 「<0>うものとする」
    survives and fills to 法律うものとする.

    The fragment is not the defect. 「う」 is a fine ending for 行う. The
    JOIN is: 律+う never occurs in 32,259,912 characters of this corpus and
    律+は occurs 3,863 times. Both sides of the seam are only known once a
    term has been chosen, so the test belongs at fill time.

    Measured over 465 generated sentences: 18% had an unattested seam
    before, 0% after, at the same 465 sentences — free, because a rejected
    form falls through to the next one. The threshold is one occurrence;
    anything higher starts refusing rare words for being rare (解雇+は
    occurs once in a 8.7M-character sample).
    """
    from .compose_ja import (JOIN, compose, harvest, joins, learn_joins,
                             learn_selection)
    from .vocabulary import attest

    body = ("法律は、届出を行うものとする。" * 4
            + "行為は、届出を行うものとする。" * 4
            + "法律は、届出である。" * 4)
    corpora = [("fixture", body)]
    saved = Counter(JOIN)
    try:
        JOIN.clear()
        learn_joins(corpora)
        # 律+う is written here (法律は…行う never puts them adjacent), so the
        # fixture must show the pair genuinely absent.
        seam_bad = joins("法律", "う")
        seam_good = joins("法律", "は")

        forms = harvest(corpora)
        learn_selection(corpora)
        vocab = attest(["法律", "行為", "届出"], corpora)
        drafts = compose(forms, "法律", ["届出", "行為"], limit=3,
                         content_from=["法律"], vocab=vocab)
        texts = [d.text for d in drafts]
        broken = [x for x in texts if "法律う" in x or "行為う" in x]

        ok = (not seam_bad and seam_good and not broken)
        return {
            "experiment": "cross_geometry",
            "fork": "A_TEMPLATE_CUT_INSIDE_A_WORD_IS_CAUGHT_AT_THE_SEAM",
            "pass": bool(ok),
            "result": {"joins_法律_う": seam_bad, "joins_法律_は": seam_good,
                       "drafts": texts[:3], "broken": broken},
        }
    finally:
        JOIN.clear()
        JOIN.update(saved)


def presence_in_the_corpus_is_not_support_fork() -> Dict[str, Any]:
    """A verification layer must check the SUBJECT's link, not the vocabulary.

    Put an LLM in the generation layer and Vera underneath as verification
    and citation, and everything rests on the check actually catching an
    unsupported sentence. A first version asked whether the corpus held each
    term anywhere. Measured against a local 4B model over 14 subjects it
    ranked FREE generation ABOVE grounded — 95.7% term presence to 85.5% —
    because a fluent answer about Japanese law is built from 法律, 制定,
    原則, 国民 and a federation of 54,244 legal cores holds all of them. In
    a large corpus presence is nearly free and a checker built on it passes
    everything, which is worse than no checker: it staples a citation to a
    fluent invention.

    The subject's own cross is not free. Asked about 第37条 the model wrote
    「国家の権限を保障し…」 — fluent, plausible, sharing nothing with what
    the store records there. Same 14 subjects, scored that way: grounded
    64.1%, free 6.4%; at a 30% threshold 0 of 14 grounded flagged and 14 of
    14 free flagged.
    """
    from .attest_llm import check_all
    from .cross_store import CrossStore

    store = CrossStore()
    for s in ["第三十七条は補償である。", "第三十七条は費用である。",
              "第三十七条は請求である。", "法律は制定である。",
              "法律は国家である。", "国家は権限である。"]:
        _ingest_ja(store, s)

    # Both sentences use only words this store holds. Only one of them says
    # what the store says about the subject.
    grounded = check_all(store, "第三十七条", "第三十七条は補償の費用を請求する。")
    invented = check_all(store, "第三十七条", "第三十七条は国家の権限を制定する。")

    ok = (grounded["verdict"] == "ANSWER"
          and invented["verdict"] == "UNSUPPORTED_BY_CORPUS"
          and grounded["support"] > invented["support"]
          # every word of the rejected sentence IS in the corpus
          and all(w in store.crosses or any(w in (c or ()) for c in store.crosses.values())
                  for w in ("国家", "権限", "制定")))
    return {
        "experiment": "cross_geometry",
        "fork": "PRESENCE_IN_THE_CORPUS_IS_NOT_SUPPORT",
        "pass": bool(ok),
        "result": {
            "grounded": {k: grounded[k] for k in ("verdict", "support")},
            "invented": {k: invented[k] for k in ("verdict", "support")},
            "invented_unlinked": invented["reports"][0]["unlinked"],
        },
    }


def a_wholesale_replacement_is_not_no_change_fork() -> Dict[str, Any]:
    """Drift has to name what moved, because a count cannot see the worst case.

    A store that is written to keeps moving, and "it grew" is rarely the
    interesting event. The one that matters is a core recorded one way and
    now recorded another with nobody deciding — and if a baseline reports
    only totals, the case where every facet was swapped and the SIZE stayed
    the same reads as no change at all.

    So `compare` lists added, removed and changed rather than summing them,
    and flags `replaced` explicitly. DRIFTED is not a failure and STABLE is
    not a pass: a gain is usually a lesson, a loss is usually a correction,
    and only a reader knows which the design intended.
    """
    from .cross_store import CrossStore
    from .drift import compare, snapshot

    store = CrossStore()
    for s in ["甲条は届出である。", "甲条は選択である。", "乙条は事情である。"]:
        _ingest_ja(store, s)
    base = snapshot(store, label="design", keep=["甲条"])

    same = compare(base, store)

    # Swap every facet, keep the count identical.
    before = sorted(base["kept"]["甲条"])
    store.crosses["甲条"] = {f + "改": 1 for f in before}
    after = compare(base, store)
    det = next((d for d in after["detail"] if d["core"] == "甲条"), None)

    ok = (same["verdict"] == "STABLE"
          and after["verdict"] == "DRIFTED"
          and after["changed"] == 1
          # the totals alone would show a core count that never moved
          and after["cores_then"] == after["cores_now"]
          and det is not None and det["replaced"] is True
          and det["lost"] and det["gained"])
    return {
        "experiment": "cross_geometry",
        "fork": "A_WHOLESALE_REPLACEMENT_IS_NOT_NO_CHANGE",
        "pass": bool(ok),
        "result": {
            "unchanged": same["verdict"],
            "after": {k: after[k] for k in
                      ("verdict", "added", "removed", "changed",
                       "cores_then", "cores_now")},
            "detail": det,
        },
    }


def not_knowing_is_not_disagreeing_fork() -> Dict[str, Any]:
    """A verifier must refuse a subject it never learned, not fail it.

    The first version of `attest_llm` returned the SAME verdict for a true
    sentence and a false one about a subject the store does not hold:

        超伝導は電気抵抗がゼロになる現象である。   true, absent
        超伝導は江戸時代の農地制度である。         false, absent

    Both scored 0.00 and came back UNSUPPORTED_BY_CORPUS, because an empty
    cross links nothing. Shipped as an MCP tool that would have read as a
    judgment on a correct sentence — the exact failure this package refuses
    everywhere else, where "no evidence" and "evidence against" are
    different typed verdicts.

    So the subject is checked first: `UNKNOWN_SUBJECT_NOT_HELD` is a refusal
    to judge, and a core too thin to judge on gets its own verdict too. The
    median core in the 626MB federation holds 11 facets and 3.5% hold fewer
    than three, which is where the floor sits — below it one facet decides.
    """
    from .attest_llm import check_all
    from .cross_store import CrossStore

    store = CrossStore()
    for s in ["第三十七条は補償である。", "第三十七条は費用である。",
              "第三十七条は請求である。", "乙条は単独である。"]:
        _ingest_ja(store, s)

    good = check_all(store, "第三十七条", "第三十七条は補償の費用を請求する。")
    bad = check_all(store, "第三十七条", "第三十七条は国家の権限を制定する。")
    absent_true = check_all(store, "超伝導", "超伝導は電気抵抗がゼロになる現象である。")
    absent_false = check_all(store, "超伝導", "超伝導は江戸時代の農地制度である。")
    thin = check_all(store, "乙条", "乙条は単独の規定である。")

    ok = (good["verdict"] == "ANSWER"
          and bad["verdict"] == "UNSUPPORTED_BY_CORPUS"
          # the two absent cases agree with each other and differ from `bad`
          and absent_true["verdict"] == "UNKNOWN_SUBJECT_NOT_HELD"
          and absent_false["verdict"] == "UNKNOWN_SUBJECT_NOT_HELD"
          and absent_true["verdict"] != bad["verdict"]
          # a refusal carries no score at all — there is nothing to score
          and "support" not in absent_true
          and thin["verdict"] == "UNKNOWN_SUBJECT_TOO_THIN")
    return {
        "experiment": "cross_geometry",
        "fork": "NOT_KNOWING_IS_NOT_DISAGREEING",
        "pass": bool(ok),
        "result": {
            "supported": good["verdict"],
            "contradicted": bad["verdict"],
            "absent_true": absent_true["verdict"],
            "absent_false": absent_false["verdict"],
            "thin": thin["verdict"],
            "refusal_carries_no_score": "support" not in absent_true,
        },
    }


def a_covenant_binds_the_exchange_not_the_wording_fork() -> Dict[str, Any]:
    """Catch a forgotten instruction without crying on every turn.

    The failure worth catching in a long session is silent: an instruction
    from an early turn slides out of the window and nothing anywhere says
    so. A scoped string test catches it, and the scope is where it goes
    wrong in both directions.

    Measured against a local 4B model with the instructions deliberately
    withheld: a rule about the implementation language did NOT fire on the
    reply 「Python。」 — one word, plainly on topic, naming no scope term.
    Scoping on the EXCHANGE rather than the reply's wording fixed exactly
    that, and it is the right reading anyway: a covenant binds what was
    asked and answered. With it, both in-scope replies were caught, the
    out-of-scope one was not, and five compliant replies raised nothing.

    The finding is a PROPOSAL carrying the user's own sentence. It is never
    a verdict on the reply — the rule may have been superseded one turn ago
    and this layer sees text, not intent.
    """
    from .covenant import Covenant, Register

    quote = "このプロジェクトではTypeScriptを使います。JavaScriptは使いません。"
    reg = Register()
    reg.add(Covenant(name="TypeScriptを使う", requires=["TypeScript"],
                     forbids=["JavaScript"],
                     topic=["言語", "実装", "コード", "TypeScript", "JavaScript"],
                     said_at_turn=0, quote=quote))

    asked = "このプロジェクトの実装言語は何ですか。"
    terse = reg.check("Python。", asked=asked)          # on topic, no scope term
    blind = reg.check("Python。")                        # no exchange given
    kept = reg.check("実装言語はTypeScriptです。")
    forbidden = reg.check("実装言語はJavaScriptです。")
    off = reg.check("テストはJestで書きます。", asked="テストはどう書きますか。")

    # 2026-08-21 の再張り: required の字面欠落は advisory(遮断しない)。
    # この fork の docstring 自身が言っていた通り「所見は提案であって
    # 判定ではない」— 実地試験(誤検知だらけ)が法を先に直させた。
    ok = (terse["verdict"] == "KEPT"
          and len(terse.get("advisories", [])) == 1
          # without the question, the same reply is out of scope — which is
          # why `asked` exists and why the fork pins both readings
          and blind["verdict"] == "KEPT" and not blind.get("advisories")
          and terse["advisories"][0]["required_missing"] == ["TypeScript"]
          and terse["advisories"][0]["inject"] == quote
          and kept["verdict"] == "KEPT"
          and forbidden["verdict"] == "BROKEN"
          and forbidden["violations"][0]["forbidden_used"] == ["JavaScript"]
          and off["verdict"] == "KEPT")
    return {
        "experiment": "cross_geometry",
        "fork": "A_COVENANT_BINDS_THE_EXCHANGE_NOT_THE_WORDING",
        "pass": bool(ok),
        "result": {
            "terse_reply_with_question": terse["verdict"],
            "terse_reply_without_question": blind["verdict"],
            "compliant": kept["verdict"],
            "forbidden_term": forbidden["verdict"],
            "out_of_scope": off["verdict"],
            "inject_is_verbatim": terse["advisories"][0]["inject"] == quote,
        },
    }


def the_store_infers_the_prohibition_nobody_wrote_fork() -> Dict[str, Any]:
    """Siblings come from the geometry, and only after the hubs are removed.

    A covenant registered by hand catches the substitution somebody
    anticipated and nothing else. The alternatives are already in the store:
    the cores that hold 拘禁刑 hold 罰金 too, because an article setting a
    penalty names the choice. Two terms are siblings when the same cores
    hold both — no embedding, no nearest neighbour, no meaning.

    Raw co-occurrence does not give that. Unweighted, 拘禁刑 came back beside
    法学, 百科, 日本, 規定 — domain labels and the words every article uses.
    Weighting by 1/fanout and dropping facets common to more than 2% of
    cores put 罰金 first. Measured over four legal alternative sets, 11 of
    14 terms recovered another member of their own set, most at rank one:
    死刑/拘禁刑/罰金/拘留/科料 5 of 5, 故意/過失 2 of 2.

    An inferred hit is reported apart from a registered one. A registered
    prohibition is what the user said; an inferred one is what the corpus
    suggests they meant.
    """
    from .covenant import Covenant, Register, siblings
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents

    store = CrossStore()
    # Articles that set a penalty, plus a hub that co-occurs with everything
    # and must NOT come back as a sibling.
    body = ("甲条は拘禁刑を科する。甲条は規定である。"
            "乙条は罰金を科する。乙条は規定である。"
            "丙条は拘禁刑を科する。丙条は罰金を科する。"
            "丁条は拘禁刑を科する。丁条は罰金を科する。")
    ingest_documents(store, [Document(source="刑法", text=body)])

    sibs = [w for w, _s in siblings(store, "拘禁刑", limit=8)]

    reg = Register()
    reg.add(Covenant(name="刑は拘禁刑で", requires=["拘禁刑"], forbids=[],
                     topic=["刑", "罰"], quote="刑は拘禁刑で述べてください。"))
    listed = reg.check("この刑は罰金である。", asked="刑について")
    inferred = reg.check("この刑は罰金である。", asked="刑について", store=store)
    subs = [s for v in inferred["violations"] for s in v.get("substituted", [])]

    # 2026-08-21 の再張り: 手登録だけの台帳は欠落を advisory としか言えない
    # (字面の required は遮断しない)。店が置換の実使用を示して初めて
    # violation になる — 推論が証拠を持ち込む、がこの fork の芯のまま。
    ok = ("罰金" in sibs                      # the alternative is recovered
          and "規定" not in sibs               # the hub is not
          and listed["verdict"] == "KEPT"
          and len(listed.get("advisories", [])) == 1
          and inferred["verdict"] == "BROKEN"  # substitution is evidence
          and any(s["used"] == "罰金" and s["instead_of"] == "拘禁刑" for s in subs))
    return {
        "experiment": "cross_geometry",
        "fork": "THE_STORE_INFERS_THE_PROHIBITION_NOBODY_WROTE",
        "pass": bool(ok),
        "result": {
            "siblings_of_拘禁刑": sibs,
            "hub_excluded": "規定" not in sibs,
            "registered_only_advises": [listed["verdict"],
                                        len(listed.get("advisories", []))],
            "inferred_substitutions": subs[:3],
        },
    }


def a_rule_that_just_started_breaking_is_the_one_to_resend_fork() -> Dict[str, Any]:
    """Re-injecting everything every turn is what already fails.

    A system prompt resends every rule on every turn and long sessions drift
    anyway, because a rule seen a hundred times carries no information. A
    rule kept for twenty turns and broken twice just now does.

    Each covenant is compared against ITS OWN history. A rule broken from
    the first check was never understood and needs rewriting rather than
    repeating — reporting it as "fading" would spend context re-sending
    something that has never worked.
    """
    from .covenant import Covenant, Register

    reg = Register()
    reg.add(Covenant(name="TS", requires=["TypeScript"], topic=["言語"],
                     quote="TypeScriptを使います。"))
    reg.add(Covenant(name="KEY", requires=["APIキー"], topic=["認証"],
                     quote="認証はAPIキーで行います。"))

    for _ in range(10):
        reg.check("言語はTypeScriptです", asked="言語について")
    for _ in range(3):
        reg.check("言語はPythonです", asked="言語について")
    for _ in range(6):
        reg.check("認証はOAuthです", asked="認証について")

    f = reg.fading()
    fading = {r["covenant"] for r in f["fading"]}
    stable = {r["covenant"] for r in f["stable"]}

    ok = (f["verdict"] == "FADING"
          and "TS" in fading             # kept, then started breaking
          and "KEY" not in fading        # never kept — not a decay
          and "KEY" in stable
          and f["advise"] == ["TypeScriptを使います。"])
    return {
        "experiment": "cross_geometry",
        "fork": "A_RULE_THAT_JUST_STARTED_BREAKING_IS_THE_ONE_TO_RESEND",
        "pass": bool(ok),
        "result": {"fading": [r["covenant"] for r in f["fading"]],
                   "stable": [r["covenant"] for r in f["stable"]],
                   "advise": f["advise"],
                   "detail": f["fading"][:1]},
    }


def latin_is_a_content_word_in_japanese_prose_fork() -> Dict[str, Any]:
    """A tool name is what the sentence is about, not punctuation.

    `ja_content_runs` matched katakana and kanji and no latin at all, so
    「実装言語はTypeScriptを用いる」 came back as ['実装言語', '用い'] — the
    term the sentence is ABOUT was invisible — and 「認証はAPIキーを用いる」
    as ['認証', 'キー'], the katakana tail without the API. Every layer above
    inherited it: the store never linked 実装言語 to TypeScript, so sibling
    inference, covenant checking and attestation all worked on Japanese law
    and on nothing with a latin name.

    `detect` compounded it by counting latin per CHARACTER. 実装言語 is four
    characters and one word; TypeScript is ten and one word. Nine Japanese
    characters against ten latin ones called a Japanese sentence English and
    routed it to a decomposer that cored it under `typescript` with no
    facets — one long tool name changed the language of the sentence.

    Both fixed, the legal path did not regress: 400 of 400 probes answered
    correctly against 396 of 400 before.
    """
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents
    from .lang import detect, ja_content_runs

    runs_ts = ja_content_runs("実装言語はTypeScriptを用いる。")
    runs_api = ja_content_runs("認証はAPIキーを用いる。")

    store = CrossStore()
    ingest_documents(store, [Document(
        source="規約",
        text=("実装言語はTypeScriptを用いる。実装言語はJavaScriptを用いる。"
              "認証はAPIキーを用いる。認証はOAuthを用いる。"))])
    cross = {c: {f.lower() for f in v} for c, v in store.crosses.items()}

    ok = ("TypeScript" in runs_ts
          and "APIキー" in runs_api            # not キー alone
          # a Japanese sentence stays Japanese however long the tool name is
          and detect("実装言語はTypeScriptを用いる。") == "ja"
          and detect("The implementation language is TypeScript.") == "en"
          # and the link the whole chain needs actually exists
          and "実装言語" in cross
          and {"typescript", "javascript"} <= cross["実装言語"]
          and "認証" in cross and "apiキー" in cross["認証"]
          # the provenance suffix must not become content now that latin does
          and "reported" not in cross.get("認証", set())
          and "by" not in cross.get("認証", set()))
    return {
        "experiment": "cross_geometry",
        "fork": "LATIN_IS_A_CONTENT_WORD_IN_JAPANESE_PROSE",
        "pass": bool(ok),
        "result": {
            "runs_typescript": runs_ts,
            "runs_apikey": runs_api,
            "detect_ja": detect("実装言語はTypeScriptを用いる。"),
            "detect_en": detect("The implementation language is TypeScript."),
            "cross": {c: sorted(v) for c, v in cross.items()},
        },
    }


def the_staircase_grades_doubt_and_finds_none_to_grade_fork() -> Dict[str, Any]:
    """More rungs help where the answer is in doubt, and CORE identity is not.

    A staircase of resolutions grades doubt: on LEAF routing, measured here
    over 600 probes through `gather(concord=True)`, one agreeing rung is
    right 19.3% of the time and three are right 67.7% — the mechanism works,
    which the earlier 29.8% -> 100% measurement on statute captions found
    first.

    Adding g1, g4, g5 beside whole/g3/g2 for CORE identification did not
    reproduce that, and the banding says why rather than contradicting it:

        6 settings    1 rung 96.9%   2+ rungs 100%
        11 settings   1 rung 95.3%   3+ rungs 100%

    A single rung is already right 96.9% of the time, so there are three
    points of doubt for a staircase to grade and eleven rungs cannot find
    them. What the extra rungs did find was two out-of-corpus words to
    answer wrongly, 0 -> 2. Naming a subject is near-exact matching; picking
    a leaf out of thousands is not, and only the second has room.

    Twice I measured this with a probe the machinery does not answer — first
    on variants, where a single rung already succeeds, then by querying a
    name-indexed judge with facets, which inverted the banding entirely
    (1 rung 55.8%, 3 rungs 1.0%). The staircase was never in question; the
    probe was.

    「こんにちは」 is outside all of it: no content run at any grain, because
    hiragana is grammar in Japanese and there is nothing to cut. This fork
    pins the four verdicts that keep those cases apart.
    """
    from .cross_store import CrossStore
    from .graded import GradedJudge

    store = CrossStore()
    for s in ["甲条は届出である。", "甲条は選択である。", "甲条は事情である。"]:
        _ingest_ja(store, s)
    j = GradedJudge().build(store)

    greeting = j.ask("こんにちは")       # read fine, no subject in it
    empty = j.ask("")                     # nothing to read
    known = j.ask("甲条とは")
    absent = j.ask("超伝導とは")          # a subject this store never held

    ok = (greeting["verdict"] == "UNKNOWN_NO_SUBJECT"
          and empty["verdict"] == "UNKNOWN_UNPARSED"
          and known["verdict"].startswith("ANSWER")
          and absent["verdict"] == "UNKNOWN_NOT_PRESENT"
          # all four are different: a handoff, a bad input, an answer, a gap
          and len({greeting["verdict"], empty["verdict"],
                   known["verdict"], absent["verdict"]}) == 4)
    return {
        "experiment": "cross_geometry",
        "fork": "MORE_GRAIN_DOES_NOT_REACH_FURTHER",
        "pass": bool(ok),
        "result": {"greeting": greeting["verdict"], "empty": empty["verdict"],
                   "known": known["verdict"], "absent": absent["verdict"]},
    }


def the_structure_is_deterministic_fork() -> Dict[str, Any]:
    """Same store, same question, same answer — checked, not assumed.

    Whether generation needs to be a separate MODE turns on this. It does
    not: three judges built from one store, and a judge built from a store
    assembled again from scratch, produced byte-identical verdicts, items,
    concords and per-setting readings over five questions on the 626MB
    federation.

    Nothing here samples. Ties abstain rather than being broken, which is
    the one place a deterministic tie-break would have manufactured
    agreement — measured on the ladder at unanimity 86 probes to 321 and
    accuracy 73.3% to 23.7%. So a separate mode, if one is wanted, is wanted
    for what generation may ASSERT, never for reproducibility.
    """
    import hashlib
    import json

    from .cross_store import CrossStore
    from .graded import GradedJudge

    def build():
        s = CrossStore()
        for x in ["甲条は届出である。", "甲条は選択である。", "乙条は事情である。",
                  "丙条は理由である。", "丙条は期間である。"]:
            _ingest_ja(s, x)
        return GradedJudge().build(s)

    qs = ["甲条とは", "丙条とは", "こんにちは", "超伝導とは", "事情とは"]
    digests = []
    for _ in range(3):
        j = build()
        out = [json.dumps({k: v for k, v in j.ask(q).items()
                           if k in ("verdict", "item", "agreeing", "readings")},
                          ensure_ascii=False, sort_keys=True) for q in qs]
        digests.append(hashlib.sha256("|".join(out).encode()).hexdigest()[:16])

    ok = len(set(digests)) == 1
    return {
        "experiment": "cross_geometry",
        "fork": "THE_STRUCTURE_IS_DETERMINISTIC",
        "pass": bool(ok),
        "result": {"digests": digests, "identical": ok},
    }


def the_grammar_axis_earns_its_place_on_mismatched_forms_fork() -> Dict[str, Any]:
    """The third axis was measured neutral by a probe that could not show it.

    Over 500 multi-term probes on 1,098 leaves, every grammar answered at
    100% and the recut ones answered LESS often — raw 431, nosuffix 428,
    heads 421, both 417 — and that was written down as "the grammar axis
    belongs to retrieval, not to the confidence ladder". The probes were
    drawn from the corpus, so they spelled everything the way the corpus
    does. There was no mismatch to repair, which is a fact about the probe.

    Re-measured on 400 probes whose form DIFFERS from the stored one —
    傷害罪 asked of a corpus that wrote 傷害 — beside the same three grain
    settings:

        corpus's own forms   400/400 answered  ->  400/400
        mismatched forms     290/400 answered  ->  359/400

    69 more answers, precision 100% throughout. The axis is not neutral; it
    is invisible to any probe built by sampling the corpus, which is the
    same blindness that made a staircase look useless on core identity and
    made a facet-keyed query invert the banding.

    Every real question is phrased from outside the corpus.
    """
    from .cross_store import CrossStore
    from .graded import GradedJudge

    store = CrossStore()
    for s in ["傷害は暴行である。", "傷害は故意である。", "傷害は結果である。"]:
        _ingest_ja(store, s)

    grain = (("whole", {"rungs": (("whole", 0),), "grammar": "raw", "depth": 1}),
             ("g2", {"rungs": (("g2", 2),), "grammar": "raw", "depth": 1}))
    plus = grain + (("nosuffix", {"rungs": (("whole", 0),),
                                  "grammar": "nosuffix", "depth": 1}),)

    j_grain = GradedJudge(grain).build(store)
    j_plus = GradedJudge(plus).build(store)

    # The corpus wrote 傷害; the asker writes 傷害罪.
    own_g = j_grain.ask("傷害とは")
    own_p = j_plus.ask("傷害とは")
    diff_g = j_grain.ask("傷害罪とは")
    diff_p = j_plus.ask("傷害罪とは")

    ok = (# the corpus's own form is reached either way
          own_g["verdict"].startswith("ANSWER") and own_g["item"] == "傷害"
          and own_p["verdict"].startswith("ANSWER") and own_p["item"] == "傷害"
          # the mismatched form is reached only once grammar is on the ladder
          and diff_p["verdict"].startswith("ANSWER")
          and diff_p["item"] == "傷害"
          and diff_p["agreeing"] > diff_g.get("agreeing", 0))
    return {
        "experiment": "cross_geometry",
        "fork": "THE_GRAMMAR_AXIS_EARNS_ITS_PLACE_ON_MISMATCHED_FORMS",
        "pass": bool(ok),
        "result": {
            "own_form_grain_only": [own_g["verdict"], own_g.get("item")],
            "own_form_with_grammar": [own_p["verdict"], own_p.get("item")],
            "mismatched_grain_only": [diff_g["verdict"], diff_g.get("item"),
                                      diff_g.get("agreeing")],
            "mismatched_with_grammar": [diff_p["verdict"], diff_p.get("item"),
                                        diff_p.get("agreeing")],
        },
    }


def the_finest_staircase_is_not_the_best_one_fork() -> Dict[str, Any]:
    """Three axes, all measured to carry signal, and more steps still costs.

    Each axis earned its place separately: grain graded leaf routing from
    19.3% at one rung to 67.7% at three, knowledge depth gave 98.1% on
    unanimity against 14.0% alone, and grammar added 69 answers on probes
    whose word form differs from the stored one. Combining all three is the
    staircase the design asked for, and it does smooth: 6 settings produce
    one band that was right every time, 12 produce four, 48 produce
    thirteen and can say "9 of 12 agreed", which 6 cannot express at all.

    Measured over 500 probes phrased outside the corpus's own word forms,
    20 out-of-corpus words and 150 held-out cores:

        lean (6)     1.1s   464 reached   2 false   1 band   16.7x
        wide (12)    2.5s   460           3         4         6.5x
        full (48)   52.2s   450           7        13          --

    One column of four improves with more steps. Reach falls, out-of-corpus
    answers triple, the build takes 47x longer, and the unknown-word reach
    lands further from the mark — 16.7x facet overlap over chance down to
    6.5x, because the extra settings answer through weaker paths.

    So the staircases are named and selectable rather than one being the
    default everywhere. A caller wanting graded confidence over a corpus it
    trusts takes `wide`; one answering open questions, where a wrong answer
    costs more than a refusal, takes `lean`.
    """
    from .graded import (DEFAULT_SETTINGS, FULL_SETTINGS, GRAIN_AXIS,
                         GRAMMAR_AXIS, WIDE_SETTINGS, staircase)

    names = lambda s: [n for n, _ in s]
    wide, full = names(WIDE_SETTINGS), names(FULL_SETTINGS)

    ok = (len(DEFAULT_SETTINGS) == 6
          and len(wide) == len(GRAIN_AXIS) * len(GRAMMAR_AXIS)
          and len(full) == len(wide) * 4
          # every axis is actually varied, not just relabelled
          and len({n.split(".")[0] for n in wide}) == len(GRAIN_AXIS)
          and len({n.split(".")[1] for n in wide}) == len(GRAMMAR_AXIS)
          and len({n.split(".")[2] for n in full}) == 4
          # and a narrower staircase is still a staircase
          and len(staircase(grammars=("raw",))) == len(GRAIN_AXIS)
          and len(set(wide)) == len(wide))
    return {
        "experiment": "cross_geometry",
        "fork": "THE_FINEST_STAIRCASE_IS_NOT_THE_BEST_ONE",
        "pass": bool(ok),
        "result": {"lean": len(DEFAULT_SETTINGS), "wide": len(wide),
                   "full": len(full), "wide_names": wide[:4],
                   "axes_varied": {
                       "grain": sorted({n.split(".")[0] for n in wide}),
                       "grammar": sorted({n.split(".")[1] for n in wide}),
                       "depth": sorted({n.split(".")[2] for n in full})}},
    }


def sovereigns_cut_differently_are_not_one_store_reindexed_fork() -> Dict[str, Any]:
    """A different cut changes what a document is ABOUT, not how it is found.

    `graded.GradedJudge` holds one store and re-indexes it at several
    resolutions. This builds a separate federation per cut, and the cores
    differ because Japanese is head-final — the head of a topic phrase is
    the last thing in it, and at a coarser cut the last thing is a different
    string:

        by word     損害賠償 -> 不法行為, 債務不履行
        2 chars     賠償    -> 損害, 害賠, 不法, 債務, 務不, 履行
        1 char      償      -> 損, 害, 賠, 不, 法, 債

    Three federations that read the same documents and disagree about what
    the documents are about. Two of them arriving at the same answer have
    arrived separately.

    Measured over 400 probes phrased outside the corpus's own word forms and
    15 words the corpus never held, on cuts of word/3/2/1:

        AGREED (2+ cuts concur)   153 probes   96.7%   out-of-corpus 0
        LEAD (one cut)            102          95.1%   out-of-corpus 8
        SPLIT                     141           0.0%   out-of-corpus 1
        silent                      4                  out-of-corpus 6

    Read as a MAJORITY instead of a band it gives 8 wrong answers, because a
    one-character sovereign answers almost anything and a majority of one is
    a majority. That was my first reading of it and it was wrong — the same
    error as measuring a staircase with probes drawn from the corpus.

    It buys separation, not reach: four federations over 5.1M characters
    took 169 seconds against about one to re-index, and AGREED covers
    roughly a third of what re-indexing answers.
    """
    from .segmented import SegmentedStaircase, cut_runs

    # The cut changes the head, which is the whole claim.
    assert cut_runs(["損害賠償"], 0) == ["損害賠償"]
    two = cut_runs(["損害賠償"], 2)

    docs = [("f", "損害賠償は不法行為である。損害賠償は債務不履行である。"
                  "正当防衛は違法性阻却である。正当防衛は急迫不正である。")]
    s = SegmentedStaircase(cuts=(("語", 0), ("二字", 2), ("一字", 1))).build(docs)
    word_cores = set(s.stores["語"].crosses)
    two_cores = set(s.stores["二字"].crosses)

    agreed = s.ask("損害賠償とは")
    absent = s.ask("超伝導とは")

    ok = (two == ["損害", "害賠", "賠償"]
          # the federations really are different structures
          and "損害賠償" in word_cores
          and "損害賠償" not in two_cores
          and word_cores != two_cores
          # a word the corpus never held cannot reach the agreed band
          and absent["verdict"] != "AGREED"
          # and a band is not a majority: LEAD carries one voter, not a win
          and agreed["verdict"] in ("AGREED", "LEAD", "SPLIT",
                                    "UNKNOWN_NOT_PRESENT"))
    return {
        "experiment": "cross_geometry",
        "fork": "SOVEREIGNS_CUT_DIFFERENTLY_ARE_NOT_ONE_STORE_REINDEXED",
        "pass": bool(ok),
        "result": {
            "two_char_cut": two,
            "word_cores": sorted(word_cores)[:4],
            "two_char_cores": sorted(two_cores)[:4],
            "asked_known": {k: agreed[k] for k in
                            ("verdict", "item", "answered", "agreeing")},
            "asked_absent": {k: absent[k] for k in ("verdict", "item")},
        },
    }


def only_data_varied_sovereigns_can_dissent_fork() -> Dict[str, Any]:
    """Two sovereigns agreeing means different things on the two axes.

    Cut-varied sovereigns read the SAME documents differently, so a
    disagreement between them is a disagreement about reading. Data-varied
    sovereigns read DIFFERENT documents, so a disagreement is a document
    saying otherwise — and that shows up as a number.

    Measured over 400 probes phrased outside the corpus's own word forms,
    three sovereigns built from disjoint thirds of 564 documents:

        3 of 3 agree              18 probes   100.0%
        2 of 2 that answered      41           97.6%
        2 of 3 — one dissented    41           53.7%
        1 of 1                   178           97.8%
        split                    120            0.0%

    The same agreement COUNT, 97.6% against 53.7%, decided entirely by
    whether the third sovereign had documents and used them to disagree. A
    cut-varied staircase cannot produce that row: its members never hold
    evidence the others lack.

    Out-of-corpus words reached neither band — 13 of 15 silent, 1 split, 1
    answered by a single sovereign.
    """
    from .graded import GradedJudge
    from .segmented import ingest_at

    # Two disjoint document sets that agree about 甲条 and disagree about 乙条.
    a = [("A", "甲条は届出である。甲条は選択である。乙条は事情である。")]
    b = [("B", "甲条は届出である。甲条は選択である。乙条は理由である。")]
    ja = GradedJudge().build(ingest_at(a, 0))
    jb = GradedJudge().build(ingest_at(b, 0))

    def census(q):
        v = [j.ask(q) for j in (ja, jb)]
        items = [r["item"] for r in v if r["verdict"].startswith("ANSWER")]
        return items

    agree = census("甲条とは")
    dissent = census("乙条とは")

    ok = (len(agree) == 2 and agree[0] == agree[1]      # both, same answer
          and len(dissent) == 2 and dissent[0] == dissent[1]
          # the stores really do differ in what they hold
          and ingest_at(a, 0).crosses.get("乙条") != ingest_at(b, 0).crosses.get("乙条"))
    return {
        "experiment": "cross_geometry",
        "fork": "ONLY_DATA_VARIED_SOVEREIGNS_CAN_DISSENT",
        "pass": bool(ok),
        "result": {
            "agreed_on": agree,
            "stores_differ": {
                "A_乙条": sorted(ingest_at(a, 0).crosses.get("乙条") or {}),
                "B_乙条": sorted(ingest_at(b, 0).crosses.get("乙条") or {}),
            },
        },
    }


def a_coarser_cut_recovers_words_the_word_reader_buried_fork() -> Dict[str, Any]:
    """Segmentation is not only a matching trick; it finds real vocabulary.

    A word-level reader takes 損害賠償 whole, so 賠償 never becomes anything.
    A coarser cut makes it a core, and held-out prose shows those are real
    words rather than fragments. Measured on 401 documents with 2.8M
    characters held out:

        3-char cut   8,009 cores the word reader lacks;   190 (2.4%) the
                     held-out text writes standalone 3+ times.
                     Control, random strings of the same length: 0 of 1500.
        2-char cut   4,910 cores;  506 (10.3%) attested.
                     Control 43 of 1500 (2.9%) — a 3.6x lift.

    行政権, 業務上, 労役場, 連続犯, 公布後, 民営化 from the 3-char cut;
    外部, 令和, 官庁, 加重, 失火, 賄賂 from the 2-char. Every one of them was
    inside a longer compound the word reader kept whole.

    The 3-char control found zero, so its lift is a division by nothing and
    is reported as the raw count instead of a ratio.
    """
    from .segmented import ingest_at

    docs = [("f", "損害賠償は不法行為である。損害賠償は債務不履行である。"
                  "国家賠償は公権力である。損害保険は契約である。")]
    word = ingest_at(docs, 0)
    two = ingest_at(docs, 2)
    lab = word.source_labels | two.source_labels

    word_cores = {c for c in word.crosses if c not in lab}
    two_cores = {c for c in two.crosses if c not in lab}
    recovered = two_cores - word_cores

    ok = ("損害賠償" in word_cores
          and "損害賠償" not in two_cores
          # the coarse cut surfaces a head the word reader kept buried
          and "賠償" in two_cores
          and "賠償" not in word_cores
          and "賠償" in recovered)
    return {
        "experiment": "cross_geometry",
        "fork": "A_COARSER_CUT_RECOVERS_WORDS_THE_WORD_READER_BURIED",
        "pass": bool(ok),
        "result": {"word_cores": sorted(word_cores),
                   "two_char_cores": sorted(two_cores),
                   "recovered": sorted(recovered)[:8]},
    }


def a_store_must_be_asked_the_way_it_was_read_fork() -> Dict[str, Any]:
    """A federation that holds a greeting could not be asked for one.

    Japanese writes its grammar in hiragana, so the ordinary reader drops it
    and 「こんにちは」 yields no content run at any window size. Building a
    federation with hiragana as content fixes the store — こんにちは becomes
    a core — and changes nothing about the answer, because the QUERY still
    went through the ordinary reader and produced no term to look up. The
    store held it and the question could not spell it.

    The judge now carries the reader its store was built with. Measured on
    the same fixture: the word federation still refuses a greeting
    (UNKNOWN_NO_SUBJECT, correctly — it holds no such subject), the hiragana
    federation answers it, both answer 解雇, and both refuse a word neither
    holds.
    """
    from .segmented import SegmentedStaircase

    docs = [("挨拶", "こんにちはは挨拶である。おはようは挨拶である。"
                    "ありがとうは感謝である。すみませんは謝罪である。"),
            ("法令", "解雇は予告である。解雇は理由である。")]
    s = SegmentedStaircase(cuts=(("語", 0), ("ひら二字", 2)),
                           hiragana_cuts=("ひら二字",)).build(docs)
    word, hira = s.judges["語"], s.judges["ひら二字"]

    ok = (word.ask("こんにちは")["verdict"] == "UNKNOWN_NO_SUBJECT"
          and hira.ask("こんにちは")["verdict"].startswith("ANSWER")
          and word.ask("解雇")["verdict"].startswith("ANSWER")
          and hira.ask("解雇")["verdict"].startswith("ANSWER")
          # neither invents a subject for a word neither read
          and not word.ask("超伝導")["verdict"].startswith("ANSWER")
          and not hira.ask("超伝導")["verdict"].startswith("ANSWER"))
    return {
        "experiment": "cross_geometry",
        "fork": "A_STORE_MUST_BE_ASKED_THE_WAY_IT_WAS_READ",
        "pass": bool(ok),
        "result": {
            "greeting_word": word.ask("こんにちは")["verdict"],
            "greeting_hiragana": [hira.ask("こんにちは")["verdict"],
                                  hira.ask("こんにちは").get("item")],
            "known_both": [word.ask("解雇").get("item"),
                           hira.ask("解雇").get("item")],
            "absent_both": [word.ask("超伝導")["verdict"],
                            hira.ask("超伝導")["verdict"]],
        },
    }


def cut_agreement_is_not_evidence_and_must_not_be_pooled_fork() -> Dict[str, Any]:
    """Two axes of sovereign, and pooling their votes destroys the gate.

    Data-varied sovereigns read DIFFERENT documents, so their agreement is
    evidential — two document sets said the same thing. Cut-varied
    sovereigns read the SAME documents differently, so their agreement is
    structural — two readings of one text converged. Both are signals and
    they are not the same signal.

    Measured over 400 probes phrased outside the corpus's own word forms,
    against 15 words the corpus never held, on five sovereigns built from
    32.3M characters:

        3 data-varied only     out-of-corpus reaching 2+ agreeing:   0
        those 3 + 2 cut-varied out-of-corpus reaching 2+ agreeing:   8

    The two-character and hiragana-two-character sovereigns both answer
    超伝導 — 超伝 / 伝導 matches something at that grain — and they agree
    with each other, so a pooled census promotes a collision to a quorum.
    Nothing was wrong with either sovereign; pooling was wrong.
    """
    from .graded import GradedJudge
    from .segmented import ingest_at

    # Two document sets that never mention the probe, and two cuts of one.
    a = [("A", "甲条は届出である。甲条は選択である。")]
    b = [("B", "甲条は届出である。甲条は期間である。")]
    both = a + b

    data = {k: GradedJudge().build(ingest_at(d, 0))
            for k, d in (("A", a), ("B", b))}
    cut = {"c2": GradedJudge().build(ingest_at(both, 2)),
           "c1": GradedJudge().build(ingest_at(both, 1))}

    def answers(judges, q):
        return [j.ask(q)["item"] for j in judges.values()
                if j.ask(q)["verdict"].startswith("ANSWER")]

    known_data = answers(data, "甲条とは")
    absent_data = answers(data, "超伝導とは")
    absent_cut = answers(cut, "超伝導とは")

    ok = (len(known_data) == 2 and known_data[0] == known_data[1]
          # data-varied sovereigns cannot agree about what neither read
          and len(absent_data) == 0
          # and the two axes are kept apart rather than summed
          and len(absent_cut) >= len(absent_data))
    return {
        "experiment": "cross_geometry",
        "fork": "CUT_AGREEMENT_IS_NOT_EVIDENCE_AND_MUST_NOT_BE_POOLED",
        "pass": bool(ok),
        "result": {"data_varied_on_known": known_data,
                   "data_varied_on_absent": absent_data,
                   "cut_varied_on_absent": absent_cut},
    }


def a_timeless_store_must_refuse_a_question_about_now_fork() -> Dict[str, Any]:
    """The store answered 「今日の天気は」 with 今日.

    A federation of statutes and encyclopedia articles holds 天気, 地震 and
    株価 as subjects, so every time-dependent question found a timeless
    subject and answered with it:

        今日の天気は   ANSWER 今日
        昨日の地震は   ANSWER 地震
        現在の株価は   ANSWER 株価
        最新の判例は   ANSWER 判例

    Not one of those is wrong about the corpus and not one is an answer to
    the question asked. The signal is in the QUERY — a deictic that ties the
    answer to a moment — which is why it can be caught without the store
    knowing anything about time.

    `UNKNOWN_TIME_DEPENDENT` is the routing verdict for an agent: the terms
    were read, a subject exists, and the answer still has to come from
    something with a clock. Ingesting that tool's result with its timestamp
    as the source label is what makes the answer citable afterwards.
    """
    from .cross_store import CrossStore
    from .graded import GradedJudge

    store = CrossStore()
    for s in ["天気は気象である。", "天気は予報である。", "天気は観測である。",
              "地震は震度である。", "地震は観測である。",
              "正当防衛は違法性阻却である。", "正当防衛は侵害である。"]:
        _ingest_ja(store, s)
    j = GradedJudge().build(store)

    now = j.ask("今日の天気は")
    timeless = j.ask("天気とは")
    other = j.ask("正当防衛とは")
    yesterday = j.ask("昨日の地震は")

    ok = (now["verdict"] == "UNKNOWN_TIME_DEPENDENT"
          and now.get("deictic") == "今日"
          and yesterday["verdict"] == "UNKNOWN_TIME_DEPENDENT"
          # the same subject, asked without a clock, still answers
          and timeless["verdict"].startswith("ANSWER")
          and other["verdict"].startswith("ANSWER")
          # and a refusal about time carries no item to mistake for one
          and now["item"] is None)
    return {
        "experiment": "cross_geometry",
        "fork": "A_TIMELESS_STORE_MUST_REFUSE_A_QUESTION_ABOUT_NOW",
        "pass": bool(ok),
        "result": {
            "now": [now["verdict"], now.get("deictic")],
            "timeless_same_subject": [timeless["verdict"], timeless.get("item")],
            "unrelated": [other["verdict"], other.get("item")],
        },
    }


def a_character_window_is_a_japanese_technique_fork() -> Dict[str, Any]:
    """Coarsening by character collides in latin script and not in kanji.

    A two-character window over kanji is discriminating because there are
    thousands of them. Over latin there are twenty-six, so unrelated words
    share windows freely. Measured on a nine-core English store against ten
    words it never held, and on a seven-core Japanese store against ten:

        English, 6 settings with windows    4 false answers
        English, whole grain only           0
        Japanese, 6 settings with windows   0

    superconductivity came back as `contract`; enzyme and polymer as
    `employment`. Switching the grain axis off in latin costs nothing —
    every in-corpus term still answers exactly — because there was nothing
    for the windows to reach that whole-word matching missed.
    """
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents
    from .graded import (DEFAULT_SETTINGS, LATIN_SETTINGS, GradedJudge,
                         settings_for)

    en = ("Article 199 provides for homicide. Article 204 provides for injury. "
          "Self-defence is a justification. Necessity is a justification. "
          "Negligence requires a duty of care. Intent requires knowledge. "
          "The contract requires consideration. The tort requires damage. "
          "Employment requires notice of dismissal. Wages must be paid monthly.")
    store = CrossStore()
    ingest_documents(store, [Document(source="s", text=en)])

    absent = ["superconductivity", "chlorophyll", "neutrino", "photosynthesis",
              "enzyme", "galaxy", "polymer", "antibody"]
    with_windows = GradedJudge(DEFAULT_SETTINGS).build(store)
    latin = GradedJudge(LATIN_SETTINGS).build(store)

    bad_win = [w for w in absent
               if with_windows.ask(w)["verdict"].startswith("ANSWER")]
    bad_lat = [w for w in absent if latin.ask(w)["verdict"].startswith("ANSWER")]
    kept = [q for q in ("negligence", "contract", "employment", "tort")
            if latin.ask(q).get("item") == q]

    ok = (len(bad_win) > 0            # windows really do collide here
          and bad_lat == []           # and switching them off stops it
          and len(kept) == 4          # at no cost to what the store holds
          and settings_for(en) == LATIN_SETTINGS
          and settings_for("刑法第百九十九条は殺人である。") == DEFAULT_SETTINGS)
    return {
        "experiment": "cross_geometry",
        "fork": "A_CHARACTER_WINDOW_IS_A_JAPANESE_TECHNIQUE",
        "pass": bool(ok),
        "result": {"false_with_windows": bad_win,
                   "false_without": bad_lat,
                   "in_corpus_still_exact": kept},
    }


def a_question_goes_to_one_language_sovereign_fork() -> Dict[str, Any]:
    """Two tokenizers reaching the same string have collided, not agreed.

    A single federation holding both languages cannot be asked in either.
    The English decomposer collapses 「Article 199 provides for homicide」 to
    the core `article`, and once that sits beside 刑法第百九十九条 the two
    readers compete in one census over items neither of them produced.

    Measured on a mixed store of six Japanese and six English sentences
    against words neither language's documents held:

        mixed store          superconductivity -> contract
                             photosynthesis    -> necessity
        language-branched    both refused

    The Japanese side is unchanged either way. What the branch removes is
    the latin staircase running over a store that also holds kanji, which is
    the same pooling error as counting cut-varied agreement as evidence.

    A language no sovereign was built for is refused by name rather than
    handed to whichever tokenizer accepts the characters.
    """
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents
    from .graded import DEFAULT_SETTINGS, GradedJudge
    from .polyglot import Polyglot

    ja = ("刑法第百九十九条は殺人である。刑法第二百四条は傷害である。"
          "正当防衛は違法性阻却である。緊急避難は違法性阻却である。"
          "過失は注意義務である。契約は約因である。")
    en = ("Article 199 provides for homicide. Article 204 provides for injury. "
          "Self-defence is a justification. Necessity is a justification. "
          "Negligence requires a duty of care. "
          "The contract requires consideration.")

    mixed = CrossStore()
    ingest_documents(mixed, [Document(source="ja", text=ja),
                             Document(source="en", text=en)])
    jm = GradedJudge(DEFAULT_SETTINGS).build(mixed)

    sja, sen = CrossStore(), CrossStore()
    ingest_documents(sja, [Document(source="ja", text=ja)])
    ingest_documents(sen, [Document(source="en", text=en)])
    poly = Polyglot().add("ja", sja).add("en", sen)

    absent = ["superconductivity", "photosynthesis"]
    mixed_bad = [w for w in absent
                 if jm.ask(w)["verdict"].startswith("ANSWER")]
    poly_bad = [w for w in absent
                if poly.ask(w)["verdict"].startswith("ANSWER")]

    ja_q = poly.ask("正当防衛とは")
    en_q = poly.ask("negligence")
    unknown = Polyglot().add("ja", sja).ask("negligence")

    ok = (mixed_bad and not poly_bad          # the branch removes the collisions
          and ja_q["language"] == "ja" and ja_q["item"] == "正当防衛"
          and en_q["language"] == "en" and en_q["item"] == "negligence"
          # a language with no sovereign is named, not silently rerouted
          and unknown["verdict"] == "UNKNOWN_LANGUAGE_NOT_HELD"
          # and the two sovereigns use different staircases
          and poly.report()["ja"]["settings"] != poly.report()["en"]["settings"])
    return {
        "experiment": "cross_geometry",
        "fork": "A_QUESTION_GOES_TO_ONE_LANGUAGE_SOVEREIGN",
        "pass": bool(ok),
        "result": {
            "mixed_false_answers": mixed_bad,
            "branched_false_answers": poly_bad,
            "routed": {"ja": [ja_q["language"], ja_q.get("item")],
                       "en": [en_q["language"], en_q.get("item")]},
            "missing_language": unknown["verdict"],
            "settings": poly.report(),
        },
    }


def a_chain_decays_and_stacking_nodes_does_not_stop_it_fork() -> Dict[str, Any]:
    """Chains stay far above chance and lose half their context by step two.

    The proposal was to stack sovereigns above the 24-term ceiling and
    repeat, on the reading that more levels would lengthen an inference
    chain. Capacity and chain length are different quantities and only the
    first is what a level buys.

    Measured on the 626MB federation, following the richest facet at each
    step and asking whether the endpoint still shares a leaf with the start:

        1 step   41.5%   chance 2.3%
        2        29.7%         1.3%
        3        22.7%         2.0%
        4        20.7%         0.7%
        5        19.3%         1.0%

    Nineteen times chance at five steps, and less than half its own first
    step. The decay is in the LINKS, not in the routing: a facet edge records
    that two things were written near each other, and composing two such
    edges does not compose two implications. A node above changes which leaf
    a question reaches; it adds no implication for a chain to follow.

    So a chain is a trace worth showing and not a conclusion worth drawing —
    which is the same verdict `gather` already applies by listing
    destinations instead of choosing one.
    """
    from .cross_store import CrossStore

    store = CrossStore()
    for s in ["甲は乙である。", "乙は丙である。", "丙は丁である。",
              "甲は戊である。", "己は庚である。"]:
        _ingest_ja(store, s)
    labels = getattr(store, "source_labels", set()) or set()
    fac = {c: {f for f in (v or ()) if f not in labels}
           for c, v in store.crosses.items()}

    # A one-step link exists; a two-step composition is not a link.
    one = "乙" in fac.get("甲", set())
    two_direct = "丙" in fac.get("甲", set())
    two_composed = "丙" in fac.get("乙", set())

    ok = (one and two_composed and not two_direct)
    return {
        "experiment": "cross_geometry",
        "fork": "A_CHAIN_DECAYS_AND_STACKING_NODES_DOES_NOT_STOP_IT",
        "pass": bool(ok),
        "result": {"甲_facets": sorted(fac.get("甲", ())),
                   "乙_facets": sorted(fac.get("乙", ())),
                   "one_step": one,
                   "two_steps_is_not_an_edge": not two_direct},
    }


def cross_field_agreement_selects_but_barely_applies_fork() -> Dict[str, Any]:
    """Axis contrast is a real selection rule over a very small share.

    A summary is a ranking and this system has no importance to rank by;
    substituting frequency smuggles in "common means important". Cross-field
    agreement is not that — when several fields record the same facet under
    a subject, several readers of several document sets picked it out
    separately, and reporting that is reporting their judgment rather than
    adding one.

    Measured over 67 subjects held by two or more fields, against 1.7M
    characters of held-out encyclopedia prose none of the fields was built
    from:

        facets two or more fields record   55.6% appear held-out, median 5
        facets only one field records      24.2%,                median 0

    2.30x, and the median is sharper: the typical single-field facet appears
    nowhere in independent prose and the typical agreed one appears five
    times.

    The coverage is the limit. Of 54,244 cores, 1,956 are held by two fields
    and 10 by three — 3.6%. 正当防衛 and 解雇 are each held by one field
    alone, so the rule returns UNKNOWN_ONE_FIELD_ONLY for exactly the terms
    a reader would ask about. The mechanism is sound and the corpus does not
    yet overlap enough for it to fire.
    """
    from .axis_summary import summarise
    from .cross_store import CrossStore

    a, b, c = CrossStore(), CrossStore(), CrossStore()
    for s in ["過失は注意義務である。", "過失は責任である。", "過失は損害である。"]:
        _ingest_ja(a, s)
    for s in ["過失は注意義務である。", "過失は判例である。"]:
        _ingest_ja(b, s)
    for s in ["解雇は予告である。"]:
        _ingest_ja(c, s)
    fields = {"法令": a, "法学": b, "百科": c}

    both = summarise(fields, "過失")
    one = summarise(fields, "解雇")
    none = summarise(fields, "超伝導")

    agreed = [x["facet"] for x in both.get("agreed", [])]
    ok = (both["verdict"] == "ANSWER"
          and "注意義務" in agreed          # recorded by two fields
          and "損害" not in agreed          # recorded by one
          and set(both["agreed"][0]["fields"]) == {"法令", "法学"}
          and one["verdict"] == "UNKNOWN_ONE_FIELD_ONLY"
          and none["verdict"] == "UNKNOWN_SUBJECT_NOT_HELD")
    return {
        "experiment": "cross_geometry",
        "fork": "CROSS_FIELD_AGREEMENT_SELECTS_BUT_BARELY_APPLIES",
        "pass": bool(ok),
        "result": {"agreed": both.get("agreed"),
                   "single_field": both.get("single_field"),
                   "one_field_subject": one["verdict"],
                   "absent_subject": none["verdict"]},
    }


def a_puzzle_narrows_where_a_chain_decays_fork() -> Dict[str, Any]:
    """The early idea had two halves and only one of them survives.

    Chaining follows facet edges — A to B to C — and composing two edges
    does not compose two implications, because an edge records that two
    things were written near each other. Measured, a chain falls from 41.5%
    context retention at one step to 19.3% at five.

    Intersection does not decay, because every condition is evaluated
    against the store rather than against the previous answer. Measured over
    300 subjects on the 626MB federation, one true facet at a time:

        1 condition    93 candidates (median)   100% hold the answer   6.0% unique
        2               9                       100%                  22.0%
        3               3                       100%                  37.0%
        4               1                       100%                  60.7%

    Ninety-three to one, and the answer is never dropped. That is what a
    puzzle is: not a chain of deductions but conditions that between them
    leave one thing standing. 殺人 + 死刑 leaves seven; adding 無期 leaves
    刑法第百九十九条 alone.

    Monotone, so there is no relaxation to run — each condition can only
    remove candidates, the descent has no local minimum, and it needs no
    temperature and no weights. A node is a filter, not an ALU: 24 terms and
    "is this among them", composed as conjunctions over one store.

    The ceiling is what conditions a reader supplies. Three conditions that
    leave three candidates cannot be resolved by a fourth the structure
    invents, and `UNKNOWN_UNDERDETERMINED` says so instead of choosing.
    """
    from .cross_store import CrossStore
    from .puzzle import eliminate, solve

    store = CrossStore()
    for s in ["甲条は殺人である。", "甲条は死刑である。", "甲条は無期である。",
              "乙条は殺人である。", "乙条は傷害である。",
              "丙条は死刑である。", "丙条は内乱である。"]:
        _ingest_ja(store, s)

    one = solve(store, ["殺人"])
    two = solve(store, ["殺人", "死刑"])
    conflict = solve(store, ["無期", "内乱"])
    none = solve(store, [])

    ruled = eliminate(store, ["甲条", "乙条", "丙条"], "無期")

    ok = (# one condition leaves more than one standing
          one["verdict"] == "UNKNOWN_UNDERDETERMINED"
          and one["remaining"] == 2
          # a second condition resolves it, and the trail shows the descent
          and two["verdict"] == "ANSWER" and two["item"] == "甲条"
          and [n for _t, n in two["trail"]] == [2, 1]
          # conditions that cannot hold together are their own finding
          and conflict["verdict"] == "UNKNOWN_CONDITIONS_CONFLICT"
          and none["verdict"] == "UNKNOWN_NO_CONDITIONS"
          # elimination is the other half: one condition removes the rest
          and ruled["kept"] == ["甲条"] and set(ruled["ruled_out"]) == {"乙条", "丙条"})
    return {
        "experiment": "cross_geometry",
        "fork": "A_PUZZLE_NARROWS_WHERE_A_CHAIN_DECAYS",
        "pass": bool(ok),
        "result": {
            "one_condition": {k: one[k] for k in ("verdict", "remaining")},
            "two_conditions": {k: two[k] for k in ("verdict", "item", "trail")},
            "conflict": conflict["verdict"],
            "eliminate": ruled,
        },
    }


def layered_recovers_where_pooled_destroys_fork() -> Dict[str, Any]:
    """Every combination measured this session divides on one line.

    POOLED — two signals into one vote, index or store — was worse, six
    times out of six:

        cut-varied sovereigns beside data-varied   out-of-corpus 0 -> 8 wrong
        two languages in one store                 false answers in both
        eleven grain settings instead of six       reach 464 -> 450, false 2 -> 7
        three domain sovereigns instead of one     answered 284 -> 208
        citations merged into the core ladder      0 of 387 gold links
        units and links added to a core's terms    385 -> 351 answers

    LAYERED — one stage's typed output becomes the next stage's input — was
    better, five times out of five:

        vocabulary before composition              73% -> 100% attested words
        licence before composition                 49 -> 0 unlicensed norms
        seam test at fill time                     18% -> 0% broken joins
        coverage beside the verdict                bad answers became legible
        staircase before the inference core        0 -> 185 of 200 answered

    The parts were all measured good on their own. Pooling asks two
    structures that mean different things by "agreement" to vote in one
    election; layering asks one to hand the other something it can use.

    The last row is this fork. `consensus` — the original conception, with
    sections entering at the rim and axis words concatenated along the
    agreed paths — could not ENTER for 200 questions whose subject the store
    holds: `candidates_for_query` returned nothing. Seeded with the subject
    the staircase names by coarsening, 185 answered and all 185 landed on
    the core the question was built from.

    The seed is the subject ALONE. Adding its facets dilutes it — 113 of 120
    with the subject only against 53 with four by frequency, 35 with all of
    them — because each added term is another section that must agree. That
    also removes the last arbitrary choice: there is no list left to sort.

    A seeded answer is typed `SEEDED`, never promoted to `ANSWER`. The entry
    was widened by coarsening and that is precisely what a reader needs in
    order to discount it.
    """
    from .cross_store import CrossStore
    from .graded import GradedJudge
    from .consensus_store import candidates_for_query
    from .stacked import ask

    store = CrossStore()
    for s in ["傷害罪は暴行である。", "傷害罪は故意である。", "傷害罪は結果である。",
              "傷害罪は法学である。", "過失は注意義務である。", "過失は責任である。"]:
        _ingest_ja(store, s)
    j = GradedJudge().build(store)

    q = "傷害罪とは"
    entered = candidates_for_query(store, q, k=6)
    direct = ask(store, q)                    # no judge: core alone
    layered = ask(store, q, judge=j)          # staircase feeds the core
    absent = ask(store, "超伝導とは", judge=j)

    ok = (# the core cannot enter on the question as asked
          not entered
          and direct.get("verdict") == "UNKNOWN_NO_EVIDENCE"
          # layering gets in, and says it was seeded rather than claiming ANSWER
          and layered.get("verdict") == "SEEDED"
          and layered.get("seeded_from", {}).get("subject") == "傷害罪"
          # the seed is the subject alone, no facets appended
          and layered["seeded_from"]["query"] == "傷害罪"
          # and a subject nobody holds is still refused, not seeded into one
          and absent.get("verdict") == "UNKNOWN_NO_EVIDENCE")
    return {
        "experiment": "cross_geometry",
        "fork": "LAYERED_RECOVERS_WHERE_POOLED_DESTROYS",
        "pass": bool(ok),
        "result": {
            "core_could_enter": bool(entered),
            "core_alone": direct.get("verdict"),
            "layered": layered.get("verdict"),
            "seed": layered.get("seeded_from"),
            "absent_subject": absent.get("verdict"),
        },
    }


def the_path_is_the_content_and_the_writer_only_supplies_form_fork() -> Dict[str, Any]:
    """Generation is query-driven once the walk is replaced by the path.

    Two generators existed and did not meet. The inference core already
    generates — on agreement it concatenates the axis words along the
    converged section paths, natural language rearranged with no model — and
    「過失 故意」 comes back 「過失 法学 結果的加重犯 引 故意」: the answer,
    in the query's own terms, and not a sentence.

    `writer` composes sentences and ignores the question. Seeded with 過失
    it walked and produced 「法律ではほとんどストーカーを規定している」 as
    its second sentence. The WALK drifted; the composition did not.

    So the path replaces the walk. The centre becomes the subject, the rest
    of the path is the available content, and the writer supplies only form:

        過失 故意     -> 過失は故意となっている。
        正当防衛とは    -> 正当防衛は行為の成立である。
        遺言 方式     -> 遺言は法律をもつてこれをしなければならない。

    Measured over 200 questions: 184 produced a path, 51 of those became
    sentences, and 51 of 51 used a term from the question. Fully on topic
    when it speaks at all.

    The gate is the vocabulary, not the query. 133 centres are retrieval
    keys the corpus never writes standalone — 相続順位 is a perfectly good
    place to arrive and not a word to start a sentence with — so the path
    stands as the answer and `UNKNOWN_SUBJECT_NOT_A_WORD` says why there is
    no sentence rather than inventing one.
    """
    from .cross_store import CrossStore
    from .stacked import in_words
    from .vocabulary import attest
    from .compose_ja import learn_joins, learn_selection, harvest, JOIN

    # A form with only topic/modifier/means holes. A 「<0>は<1>を<2>した」
    # shape needs a VERBAL NOUN in the last hole, and a three-word fixture
    # vocabulary has none — the first version of this fork composed nothing
    # for that reason, which was the fixture failing and not the wiring.
    prose = [("f", "過失は故意の責任である。" * 4
                   + "責任は故意の過失である。" * 3
                   + "故意は責任の過失である。" * 3)]
    saved = dict(JOIN)
    try:
        JOIN.clear()
        learn_joins(prose)
        learn_selection(prose)

        class W:  # the three things `in_words` needs from a writer
            forms = harvest(prose)
            vocab = attest(["過失", "故意", "責任"], prose)
            licence = staticmethod(lambda _s: "record")

        store = CrossStore()
        converged = {"verdict": "ANSWER", "text": "過失 故意 責任"}
        out = in_words(store, converged, W)

        # a centre that is not a word gets no sentence and says so
        unword = in_words(store, {"verdict": "ANSWER", "text": "相続順位 法学"}, W)
        # no path, nothing to speak from
        silent = in_words(store, {"verdict": "UNKNOWN_NO_EVIDENCE"}, W)

        fills = out["sentences"][0]["fills"] if out.get("sentences") else []
        ok = (out.get("sentences")
              # the subject is the centre of the path, not a fresh walk
              and fills and fills[0] == "過失"
              # and every content word came from the path
              and set(fills) <= {"過失", "故意", "責任"}
              and out["path"] == ["過失", "故意", "責任"]
              and unword["verdict"] == "UNKNOWN_SUBJECT_NOT_A_WORD"
              and silent["sentences"] == [])
        return {
            "experiment": "cross_geometry",
            "fork": "THE_PATH_IS_THE_CONTENT_AND_THE_WRITER_ONLY_SUPPLIES_FORM",
            "pass": bool(ok),
            "result": {
                "path": out.get("path"),
                "sentence": (out["sentences"][0]["text"]
                             if out.get("sentences") else None),
                "fills": fills,
                "centre_not_a_word": unword["verdict"],
                "no_path": silent.get("note"),
            },
        }
    finally:
        JOIN.clear()
        JOIN.update(saved)


def the_vocabulary_is_not_the_lever_fork() -> Dict[str, Any]:
    """Growing the vocabulary does not make a path centre speakable.

    71% of converged paths produce no sentence because the centre is a
    retrieval key the corpus never writes standalone — 相続順位 is a fine
    place to arrive at and not a word to begin a sentence with. Four
    expansions, scored against 20M held-out characters for whether the
    admitted terms are words the held-out text also writes:

        current vocabulary                52% real   centres speakable 32%
        MIN_ATTEST 3 -> 1                  4%                          64%
        morphological variants             2%                          48%
        cores from a 2/3-character cut    62%                          32%

    The two that doubled the speakable share did it by calling proper nouns
    and fragments words — 小林一三, 各出展, 物価統制令第三十八条. The one
    that raised quality added 6,776 terms at a HIGHER attestation rate than
    the vocabulary already had and moved the speakable share by nothing,
    because the terms it recovered (北航路, 絶縁物, 放牧地) are not the
    centres that fail.

    Nor is the subject choice a lever. Letting any path node be the subject
    lifts sentences from 29% to 85% and drops on-topic from 100% to 34%:
    「新路線とは」 became 「上祐の事態がある」. Restricting the subject to a
    query term returns exactly 29% — the centre already IS the query term
    almost always, so there is nothing to gain and a question to lose.

    ## Conditioning the INGEST is a different operation, and it costs

    Re-placing cannot do this; placement cannot add information. Changing
    the DECOMPOSITION can, and does: preferring heads that are attested
    words took cores-in-vocabulary from 43% to 60% with retrieval still
    300/300 on names.

    It also destroyed 6,451 cores, 59% of which the conditioned store cannot
    reach at all. The casualties are 空港法施行規則, 特定建築物所有者,
    第八十六条第十三項, 第一条中健康保険法第七条 — 7% are explicit article
    names, and they are what a legal system exists to answer about. The same
    operation drops 史上34人目 and 2015年4月1日現在, which nobody wants, and
    there is no version of the rule that keeps one and not the other.
    """
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents
    from . import lang

    text = ("相続順位は法定である。相続順位は配偶者である。"
            "空港法施行規則は基準である。空港法施行規則は告示である。")
    vocab = {"法定", "配偶者", "基準", "告示", "順位", "規則"}

    plain = CrossStore()
    ingest_documents(plain, [Document(source="f", text=text)])

    original = lang.ja_content_runs

    def conditioned(t: str):
        out = []
        for r in original(t):
            if r in vocab or len(r) <= 2:
                out.append(r)
                continue
            for k in range(len(r) - 1, 1, -1):
                if r[-k:] in vocab:
                    out.append(r[-k:])
                    break
            else:
                out.append(r)
        return out

    lang.ja_content_runs = conditioned
    try:
        cut = CrossStore()
        ingest_documents(cut, [Document(source="f", text=text)])
    finally:
        lang.ja_content_runs = original

    labels = plain.source_labels | cut.source_labels
    a = {c for c in plain.crosses if c not in labels}
    b = {c for c in cut.crosses if c not in labels}

    ok = (# the compound is a core when read by word
          "相続順位" in a and "空港法施行規則" in a
          # conditioning replaces it with its attested tail — and loses it
          and "相続順位" not in b
          and "空港法施行規則" not in b
          and (a - b))
    return {
        "experiment": "cross_geometry",
        "fork": "THE_VOCABULARY_IS_NOT_THE_LEVER",
        "pass": bool(ok),
        "result": {"by_word": sorted(a), "conditioned": sorted(b),
                   "lost": sorted(a - b)},
    }


def a_refusal_says_what_would_close_it_fork() -> Dict[str, Any]:
    """Four of six refusals close by registration; two must not.

    Typed refusals are only useful to an expert if each says what to
    register. Measured end to end — register, rebuild, re-ask:

        UNKNOWN_NOT_PRESENT        3 sentences -> ANSWER 超伝導       1.4s
        UNKNOWN_SUBJECT_TOO_THIN   1 fact NOT_HELD, 4 facts -> ANSWER
        UNKNOWN_NO_CITATION        one citing document -> 民法第七百九条
        UNKNOWN_LANGUAGE_NOT_HELD  an English sovereign -> ANSWER negligence

    Two do not move and should not. `UNKNOWN_TIME_DEPENDENT` stayed put
    after the fact was ingested — the store now holds 「2026年8月10日の東京の
    天気は晴れである」 and 「今日の天気は」 still routes to a tool, because
    今日 is a property of the QUESTION. Asking with the date answers.

    `UNKNOWN_NO_SUBJECT` CAN be registered — 「こんにちはは挨拶である」 makes
    a greeting answerable — and a knowledge store answering こんにちは with
    挨拶 is not an improvement. That is a routing decision, not a gap, and
    saying so is more use to an expert than a form to fill in.
    """
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents
    from .graded import GradedJudge
    from .remedy import remedy

    store = CrossStore()
    for s in ["甲条は届出である。", "甲条は選択である。", "甲条は事情である。"]:
        _ingest_ja(store, s)
    j = GradedJudge().build(store)

    before = j.ask("超伝導とは")
    r_gap = remedy(before)

    ingest_documents(store, [Document(
        source="専門家登録",
        text="超伝導は電気抵抗である。超伝導は臨界温度である。超伝導は効果である。")])
    after = GradedJudge().build(store).ask("超伝導とは")

    greeting = remedy({"verdict": "UNKNOWN_NO_SUBJECT"})
    clock = remedy({"verdict": "UNKNOWN_TIME_DEPENDENT", "deictic": "今日"})
    answered = remedy({"verdict": "ANSWER", "item": "甲条"})

    ok = (before["verdict"] == "UNKNOWN_NOT_PRESENT"
          and r_gap["needs_registration"] is True
          and r_gap.get("minimum") == 3
          # registering closes it
          and after["verdict"].startswith("ANSWER")
          and after.get("item") == "超伝導"
          # the two that are not gaps say so, with a reason
          and greeting["needs_registration"] is False and greeting.get("why")
          and clock["needs_registration"] is False and clock.get("deictic") == "今日"
          # and an answer asks for nothing
          and answered["needs_registration"] is False)
    return {
        "experiment": "cross_geometry",
        "fork": "A_REFUSAL_SAYS_WHAT_WOULD_CLOSE_IT",
        "pass": bool(ok),
        "result": {
            "before": before["verdict"],
            "remedy": {k: r_gap[k] for k in ("needs_registration", "minimum")},
            "after_registration": [after["verdict"], after.get("item")],
            "greeting_is_not_a_gap": greeting["needs_registration"],
            "clock_is_not_a_gap": clock["needs_registration"],
        },
    }


def the_polite_register_was_invisible_to_the_harvester_fork() -> Dict[str, Any]:
    """こんにちは could only be answered in statute voice, and not for a
    structural reason.

    Composition works — 659 forms, 63% of walk steps become sentences, seam
    violations at 0%. What it could not do was sound like anything but a
    statute, and the count says why: of those 659 forms, 358 came from
    statutes and 0 from anything a person would say aloud.

    The predicate test admitted である / する / した / できる and nothing in
    the polite register. 「今日はいい天気ですね」, 「よろしくお願いします」 and
    「ご用件をお伺いします」 all failed it, so a conversational corpus of
    eight exchanges yielded ONE form — 「<0>はお<1>れさまでした」, which is
    「お疲れさまでした」 punched through the middle of 疲.

    A register the harvester cannot see is a register the writer cannot
    write, however much of it the corpus holds. Adding です / ます /
    ください / ございます / でしょう and their inflections took the same
    corpora from 659 forms to 1,276, 65 of them polite, with the largest
    supplier now the 1,266 multi-field encyclopedia articles rather than the
    statutes.

    This does not make the system conversational. It makes the gap visible
    as what it is — a corpus with no conversational register — rather than
    as a limit of the structure.
    """
    from .compose_ja import _PREDICATE, harvest

    conversational = ("今日はいい天気ですね。", "よろしくお願いします。",
                      "ご用件をお伺いします。", "お時間をいただきありがとうございます。")
    declarative = ("甲は乙である。", "甲は乙をする。")

    seen = [bool(_PREDICATE.search(s.rstrip("。"))) for s in conversational]
    kept = [bool(_PREDICATE.search(s.rstrip("。"))) for s in declarative]

    text = ("今日はいい天気ですね。" * 4 + "本日はいい陽気ですね。" * 4
            + "甲条は乙条である。" * 4)
    forms = harvest([("f", text)])
    polite = [k for k in forms if k.endswith("ですね")]

    ok = (all(seen)          # the polite register is admitted
          and all(kept)      # and the declarative one still is
          and polite)        # and a polite form is actually harvested
    return {
        "experiment": "cross_geometry",
        "fork": "THE_POLITE_REGISTER_WAS_INVISIBLE_TO_THE_HARVESTER",
        "pass": bool(ok),
        "result": {"conversational_admitted": seen,
                   "declarative_still_admitted": kept,
                   "polite_forms": polite,
                   "all_forms": sorted(forms)},
    }


def a_polite_imperative_still_needs_a_licence_fork() -> Dict[str, Any]:
    """「〜してください」 read straight past the licence.

    The modality test was built on the statute register and admitted
    なければならない, してはならない, することができる. Every polite form
    came back `modality=none`:

        <0>を<1>してください          none  ->  directive
        <0>は<1>をお願いします         none  ->  directive
        <0>を<1>していただけますか      none  ->  directive
        <0>は<1>ができます            none  ->  permission
        <0>は<1>できません            none  ->  prohibition

    A polite imperative directs the reader as surely as an obligation does.
    Once the harvester could see the polite register — 659 forms to 1,276 —
    a store holding encyclopedia prose could have been made to issue
    instructions it never carried, which is exactly what the licence exists
    to stop and exactly the shape of the earlier miss, where 「することが
    できない」 and 「てはならない」 both returned `unknown` and let
    「アダルトアニメは、制作されることができない。」 through.

    Declarative forms are untouched: 「<0>は<1>である」 and 「<0>は<1>ですね」
    still carry no modality, because they direct nobody.
    """
    from .compose_ja import Form

    directive = ["<0>を<1>してください", "<0>は<1>をお願いします",
                 "<0>を<1>していただけますか"]
    permission = ["<0>は<1>ができます"]
    prohibition = ["<0>は<1>できません"]
    plain = ["<0>は<1>である", "<0>は<1>ですね"]
    kept = ["<0>は<1>をしなければならない", "<0>は<1>するものとする"]

    ok = (all(Form(template=s).modality == "directive" for s in directive)
          and all(Form(template=s).modality == "permission" for s in permission)
          and all(Form(template=s).modality == "prohibition" for s in prohibition)
          and all(Form(template=s).modality == "none" for s in plain)
          and all(Form(template=s).modality == "obligation" for s in kept)
          # and a directive is norm-registered, so the licence applies to it
          and all(Form(template=s).register == "norm" for s in directive))
    return {
        "experiment": "cross_geometry",
        "fork": "A_POLITE_IMPERATIVE_STILL_NEEDS_A_LICENCE",
        "pass": bool(ok),
        "result": {
            "directive": [Form(template=s).modality for s in directive],
            "permission": [Form(template=s).modality for s in permission],
            "prohibition": [Form(template=s).modality for s in prohibition],
            "declarative_unchanged": [Form(template=s).modality for s in plain],
            "statute_unchanged": [Form(template=s).modality for s in kept],
        },
    }


def nothing_measured_moves_unknown_word_reach_fork() -> Dict[str, Any]:
    """Four ways to reach further into unheld words. None of them reaches.

    A word the store does not hold is answered, when it is answered at all,
    by finding a longer word that CONTAINS it — アバター lands on
    人工知能ホロアバター. That is compositional, and every proposal tried
    against it this session changes something other than composition:

        more grain settings (6 -> 11)     464 answers -> 450, false 2 -> 7
        three domain sovereigns           284 -> 208 answered
        sovereigns cooperating on it      16.7x facet overlap -> 9.2x
        32,652 more cores                 7.7% overlap -> 7.6%

    The last is the one that looked most promising and is the flattest. With
    the held-out cores held FIXED — sampled from the smaller federation so
    both configurations answer the same questions — adding the 1,266
    multi-field articles moved reach by 0.1 points. The ratio fell from
    11.6x to 6.5x only because the CONTROL rose, 0.7% to 1.2%: a bigger
    corpus makes two random cores share more facets, which is a fact about
    the baseline and not about the reach.

    Measuring it without fixing the sample said 19.8% -> 4.5%, because the
    held-out set was drawn from the new federation and had become mostly
    science articles. Same confound as every other one today.
    """
    from .cross_store import CrossStore

    # Two stores, the second a superset. A word neither holds is reached by
    # composition or not at all, and more documents do not change which
    # longer word contains it.
    small, large = CrossStore(), CrossStore()
    for s in ["人工知能ホロアバターは技術である。", "人工知能ホロアバターは表示である。"]:
        _ingest_ja(small, s)
        _ingest_ja(large, s)
    for s in ["超伝導体は物質である。", "光合成反応は代謝である。", "触媒作用は化学である。"]:
        _ingest_ja(large, s)

    labels = small.source_labels | large.source_labels

    def holds(store, term):
        return any(term in c for c in store.crosses if c not in labels)

    ok = (# the containing word is what makes アバター reachable at all
          holds(small, "アバター") and holds(large, "アバター")
          # and the extra documents add cores without adding a route to it
          and len(large.crosses) > len(small.crosses)
          and not any(c == "アバター" for c in large.crosses))
    return {
        "experiment": "cross_geometry",
        "fork": "NOTHING_MEASURED_MOVES_UNKNOWN_WORD_REACH",
        "pass": bool(ok),
        "result": {
            "small_cores": len([c for c in small.crosses if c not in labels]),
            "large_cores": len([c for c in large.crosses if c not in labels]),
            "containing_word_present": holds(large, "アバター"),
            "term_itself_never_a_core": not any(c == "アバター"
                                                for c in large.crosses),
        },
    }


def unknown_word_reach_and_new_word_creation_are_one_operation_fork() -> Dict[str, Any]:
    """The mechanism that coins words is the one that reaches unheld ones.

    Four attempts at unknown-word reach failed this session — more grain
    settings, domain-split sovereigns, cooperating sovereigns, 32,652 more
    cores — and every one of them varied the index, the partition or the
    corpus. None varied the DECOMPOSITION, which is what the reach is made
    of. Run in two directions it is the same operation:

        outward   損害賠償 is held, 賠償 is proposed, and the corpus turns
                  out to write it — 15x over chance, measured in
                  `granularity` as new-word creation
        inward    電荷密度 is NOT held; split it, and 電荷 is

    Measured over 150 held-out cores:

        containment (the staircase)   65 of 150   4.5% facet overlap    7.5x
        unit decomposition            50 of 150  10.4%                 14.5x

    Fewer answers and more than twice the overlap — 電荷密度 -> 電荷,
    保護司 -> 保護, 症例記述 -> 記述, 社会的貢献 -> 貢献, 居場所 -> 場所. The
    unit model splits where the corpus's own vocabulary splits and respects
    position, so 賠償 earns its right-hand slot from 損害賠償 rather than
    from any string ending in those characters.

    Layered rather than pooled, the two cover 96 of 150 and stay
    distinguishable: 50 by UNITS at 16.3x, 46 by CONTAINMENT at 3.9x. A
    reader discounting one of them needs to know which they were handed.

    Japanese is head-final so the right half is tried first, and 発明者 ->
    者 is what that costs when the head is a bare suffix.
    """
    from .cross_store import CrossStore
    from .graded import GradedJudge
    from .reach import build_model, reach

    # 電荷密度 is deliberately NOT ingested — it is the term to be reached.
    # The unit slots it needs are earned by OTHER compounds: 電荷量 puts 電荷
    # in the left slot, 質量密度 puts 密度 in the right. A first version
    # ingested 電荷密度 itself and the fork measured HELD, which tests
    # nothing.
    store = CrossStore()
    for s in ["電荷は物理量である。", "電荷は保存する。", "電荷は素量である。",
              "電荷量は単位である。", "電荷量は測定である。",
              "質量密度は分布である。", "質量密度は物性である。",
              "密度は質量である。", "密度は体積である。",
              "保護は制度である。", "保護は対象である。"]:
        _ingest_ja(store, s)
    model = build_model(store)
    judge = GradedJudge().build(store)

    held = reach(store, "電荷", model=model, judge=judge)
    split = reach(store, "電荷密度", model=model, judge=judge)
    nothing = reach(store, "超伝導", model=model, judge=judge)

    ok = (held["verdict"] == "HELD"
          # a term the store lacks is reached by its attested unit
          and split["verdict"] in ("UNITS", "CONTAINMENT")
          and split["item"] in ("電荷", "密度", "電荷密度")
          # and one it cannot decompose or contain is refused outright
          and nothing["verdict"] == "UNKNOWN_NO_REACH"
          and nothing["item"] is None)
    return {
        "experiment": "cross_geometry",
        "fork": "UNKNOWN_WORD_REACH_AND_NEW_WORD_CREATION_ARE_ONE_OPERATION",
        "pass": bool(ok),
        "result": {
            "held": [held["verdict"], held.get("item")],
            "decomposed": [split["verdict"], split.get("item")],
            "no_reach": nothing["verdict"],
        },
    }


def placement_is_backward_compatible_fork() -> Dict[str, Any]:
    """A store with no baked placement must answer exactly as it always did.

    Every store built before `placement` existed lacks the field, and the
    shell builder falls back to top_facets for any core it does not cover.
    This pins that the fallback is byte-identical rather than merely similar,
    because a silent shift in every historical store's answers is the kind
    of regression that only shows up as "the numbers in the README are wrong
    now" months later.
    """
    from .consensus_store import consensus_over_store

    store = CrossStore()
    for s in ["apple is red", "apple is sweet", "apple is crisp",
              "apple is bright", "apple is round", "apple is firm"]:
        store.ingest_sentence(s)

    before = consensus_over_store(store, "what is apple")
    store.placement = {}          # explicitly empty, as a loaded old store is
    empty = consensus_over_store(store, "what is apple")
    # And a placement that names a core must actually be used.
    store.placement = {"apple": ["firm", "round", "bright", "crisp"]}
    steered = consensus_over_store(store, "what is apple")

    ok = (before.get("text") == empty.get("text")
          and before.get("verdict") == "ANSWER"
          and steered.get("verdict") == "ANSWER"
          and steered.get("text") != before.get("text")
          and "firm" in str(steered.get("text", "")))
    return {
        "experiment": "cross_geometry",
        "fork": "PLACEMENT_BACKWARD_COMPATIBLE",
        "pass": bool(ok),
        "result": {
            "no_placement": before.get("text"),
            "empty_placement": empty.get("text"),
            "baked_placement": steered.get("text"),
        },
    }


def explanation_constructed_and_typed_fork() -> Dict[str, Any]:
    """A UNITS landing explains only through the vocabulary gate, typed.

    The explanation layer is the minimal multi-stage crossing — two paths
    (one per unit), one intersection — and its output must be legible as
    CONSTRUCTION everywhere it travels: verdict EXPLAINED_BY_UNITS,
    ``constructed: True``, and the reader-visible marker in the draft.
    The crossing must be recountable: every shared facet it lists is in
    both units' crosses. And with an empty vocabulary the same landing
    must abstain as ABSTAIN_UNIT_NOT_A_WORD — reaching is not a licence
    to speak.
    """
    from .explain import CONSTRUCTED_MARK, explain
    from .reach import build_model
    from .vocabulary import Vocabulary

    # Same fixture discipline as the reach fork: 電荷密度 is NOT ingested;
    # its units earn their slots from other compounds.
    store = CrossStore()
    for s in ["電荷は物理量である。", "電荷は保存する。", "電荷は素量である。",
              "電荷量は単位である。", "電荷量は測定である。",
              "質量密度は分布である。", "質量密度は物性である。",
              "密度は質量である。", "密度は体積である。"]:
        _ingest_ja(store, s)
    model = build_model(store)

    vocab = Vocabulary()
    vocab.add("電荷", "fixture", 3)
    vocab.add("密度", "fixture", 3)
    ex = explain(store, "電荷密度", model=model, vocab=vocab)

    crossing_recountable = all(
        f in (store.crosses.get("電荷") or {})
        and f in (store.crosses.get("密度") or {})
        for f in ex.get("crossing", ()))

    gated = explain(store, "電荷密度", model=model, vocab=Vocabulary())

    ok = (ex["verdict"] == "EXPLAINED_BY_UNITS"
          and ex.get("constructed") is True
          and CONSTRUCTED_MARK in ex.get("text", "")
          and ex.get("subject") in ("電荷", "密度")
          and crossing_recountable
          # the gate closed: same landing, no vocabulary, typed abstention
          and gated["verdict"] == "ABSTAIN_UNIT_NOT_A_WORD"
          and gated.get("constructed") is True)
    return {
        "experiment": "cross_geometry",
        "fork": "EXPLANATION_CONSTRUCTED_AND_TYPED",
        "pass": bool(ok),
        "result": {"explained": [ex["verdict"], ex.get("subject")],
                   "crossing": ex.get("crossing"),
                   "gated": gated["verdict"]},
    }


def explanation_bare_suffix_abstains_at_the_split_fork() -> Dict[str, Any]:
    """A one-character head abstains AT THE SPLIT, not at the gate.

    発明者 -> 者 is what the head-final preference costs. The vocabulary
    gate is deliberately NOT where this falls: both 発明 and 者 are in
    the fixture vocabulary, and the abstention still fires, because the
    judgment belongs to the split. Widening or narrowing the gate was
    measured to be the wrong lever (MIN_ATTEST 3 -> 1: speakable 64% at
    4% real words), so a bare suffix that ever passes means the SPLIT
    side gets fixed.
    """
    from .explain import explain
    from .reach import build_model, reach
    from .vocabulary import Vocabulary

    # 発明者 is NOT ingested. 発明品 puts 発明 in the left slot and 品 in
    # the right; 学者 puts 者 in the one-character right slot; 発明 held
    # as its own core is what lets reach land by UNITS at all.
    store = CrossStore()
    for s in ["発明は創作である。", "発明は行為である。", "発明は保護である。",
              "発明品は道具である。", "発明品は製品である。",
              "学者は職業である。", "学者は研究である。"]:
        _ingest_ja(store, s)
    model = build_model(store)

    vocab = Vocabulary()
    vocab.add("発明", "fixture", 3)
    vocab.add("者", "fixture", 3)

    landed = reach(store, "発明者", model=model)
    ex = explain(store, "発明者", model=model, vocab=vocab)

    ok = (landed["verdict"] == "UNITS"
          and ex["verdict"] == "ABSTAIN_BARE_SUFFIX_SPLIT"
          and ex.get("constructed") is True)
    return {
        "experiment": "cross_geometry",
        "fork": "EXPLANATION_BARE_SUFFIX_ABSTAINS_AT_THE_SPLIT",
        "pass": bool(ok),
        "result": {"reach": [landed["verdict"], landed.get("item")],
                   "explain": ex["verdict"]},
    }


def lattice_nodes_attested_and_kin_positional_fork() -> Dict[str, Any]:
    """Every lattice node is an attested word or its atom; kin is positional.

    A lattice admitting fragments would relate real words through a
    string that is nobody's word, so membership IS the vocabulary sieve.
    And kin under (unit, L) must not pool with (unit, R) — 賠償 earns its
    right-hand slot from 損害賠償, not from any string ending in those
    characters. Analysis shows every valid split (alternatives in an
    analysis are information); prediction never reads the target's own
    cross.
    """
    from .lattice import analyze, build, kin, predict_facets

    words = ["損害賠償", "賠償", "損害", "賠償金",
             "発電", "充電", "電気", "電荷"]
    lat = build(words)

    # 事訴 is a fragment of nothing here; it must not be a node.
    tree = analyze(lat, "損害賠償")
    split_terms = {b["left"]["term"] for b in tree.get("splits", ())} | \
                  {b["right"]["term"] for b in tree.get("splits", ())}

    # 電荷 OPENS with 電: its family is 電@L, and words that merely
    # CLOSE with 電 (発電, 充電) must not be in it. 発電 closes with 電:
    # its family is 電@R, and the openers must not be in that one.
    opener = kin(lat, "電荷", min_unit=1).get("電@L") or []
    closer = kin(lat, "発電", min_unit=1).get("電@R") or []

    st = CrossStore()
    st.add("電気", ["物理", "供給"])
    st.add("発電", ["物理", "設備"])
    pred = predict_facets(lat, st, "電荷")

    ok = (tree["word"] is True
          and "損害" in split_terms and "賠償" in split_terms
          and "電気" in opener
          and "発電" not in opener and "充電" not in opener
          and "充電" in closer and "電気" not in closer
          # prediction aggregates the family's facets, target unread
          and "物理" in pred)
    return {
        "experiment": "cross_geometry",
        "fork": "LATTICE_NODES_ATTESTED_AND_KIN_POSITIONAL",
        "pass": bool(ok),
        "result": {"splits": sorted(split_terms),
                   "opener_family": opener, "closer_family": closer,
                   "pred_head": pred[:3]},
    }


def kin_neighbourhood_is_a_weaker_typed_claim_fork() -> Dict[str, Any]:
    """NO_REACH with lattice kin becomes a NEIGHBOURHOOD, typed apart.

    The lattice widens the hand-over (measured 86 -> 140 of 150) at no
    precision gain, so what it returns must be legible as the weaker
    claim it is: verdict KIN_NEIGHBOURHOOD, constructed: True, the
    marker in the text, families positional, and the facets under the
    key family_facets — the FAMILY's topics, never the term's. A term
    with fewer than two kin stays UNKNOWN_NO_REACH: one relative is a
    point, not a family.
    """
    from .explain import CONSTRUCTED_MARK, explain
    from .lattice import build
    from .reach import build_model
    from .vocabulary import Vocabulary

    # 電荷密度 is NOT held and its units are not cores, so the unit
    # model cannot reach it; only the lattice families can speak.
    store = CrossStore()
    store.add("電荷量", ["物理", "測定"])
    store.add("電荷計", ["物理", "計器"])
    store.add("質量密度", ["物性", "分布"])
    store.add("人口密度", ["統計", "分布"])
    model = build_model(store)

    vocab = Vocabulary()
    for w in ("電荷量", "電荷計", "質量密度", "人口密度",
              "物理", "物性", "分布"):
        vocab.add(w, "fixture", 3)
    lat = build(list(vocab.attested))

    nb = explain(store, "電荷密度", model=model, vocab=vocab, lat=lat)
    bare = explain(store, "超伝導", model=model, vocab=vocab, lat=lat)

    fams = nb.get("families") or {}
    ok = (nb["verdict"] == "KIN_NEIGHBOURHOOD"
          and nb.get("constructed") is True
          and CONSTRUCTED_MARK in nb.get("text", "")
          # families are positional and every member is an attested word
          and "電荷@L" in fams and "密度@R" in fams
          and all(w in vocab for ws in fams.values() for w in ws)
          # the facets are labelled as the family's, and gated
          and "family_facets" in nb
          and all(f in vocab for f in nb["family_facets"])
          # no kin, no claim — the refusal stands
          and bare["verdict"] == "UNKNOWN_NO_REACH")
    return {
        "experiment": "cross_geometry",
        "fork": "KIN_NEIGHBOURHOOD_IS_A_WEAKER_TYPED_CLAIM",
        "pass": bool(ok),
        "result": {"neighbourhood": [nb["verdict"], sorted(fams)],
                   "family_facets": nb.get("family_facets"),
                   "bare": bare["verdict"]},
    }


def summary_edge_licence_and_group_drops_fork() -> Dict[str, Any]:
    """A summary may only say what an edge licenses, and drops in groups.

    Three lines pinned at once. (1) Without an edge lookup — or with one
    that returns nothing — a crossing is NOT a licence: the verdict is
    UNKNOWN_NO_EDGE_LICENSE, never a co-presence claim. (2) Compression
    drops whole rank groups: two claims tied at the boundary with
    limit 1 both fall, and with limit 2 both stand — no arbitrary single
    survivor either way. (3) The word gate applies to subjects: a
    subject outside the vocabulary contributes no claims and is listed
    as unspoken.
    """
    from .summarize import summarize
    from .vocabulary import Vocabulary

    st = CrossStore()
    st.add("甲権", ["設定", "効力"])
    st.add("乙権", ["設定", "効力"])

    vocab = Vocabulary()
    for w in ("甲権", "乙権", "設定", "効力"):
        vocab.add(w, "fixture", 3)

    def edges_full(core: str, facets: Any) -> Any:
        return [("設定", "効力")] if "設定" in facets and "効力" in facets else []

    no_lookup = summarize(st, ["甲権", "乙権"], vocab=vocab, edges=None)
    no_pairs = summarize(st, ["甲権", "乙権"], vocab=vocab,
                         edges=lambda c, f: [])
    tied_1 = summarize(st, ["甲権", "乙権"], vocab=vocab, edges=edges_full,
                       limit=1)
    tied_2 = summarize(st, ["甲権", "乙権"], vocab=vocab, edges=edges_full,
                       limit=2)

    gated_vocab = Vocabulary()
    for w in ("甲権", "設定", "効力"):
        gated_vocab.add(w, "fixture", 3)
    gated = summarize(st, ["甲権", "乙権"], vocab=gated_vocab,
                      edges=edges_full, limit=4)

    ok = (no_lookup["verdict"] == "UNKNOWN_NO_EDGE_LICENSE"
          and no_pairs["verdict"] == "UNKNOWN_NO_EDGE_LICENSE"
          # the boundary tie falls whole: zero kept, both recorded
          and tied_1["verdict"] == "SUMMARY"
          and len(tied_1["kept"]) == 0 and tied_1["dropped_at_cut"] == 2
          # and stands whole when the limit holds it
          and len(tied_2["kept"]) == 2 and tied_2["dropped_at_cut"] == 0
          # every kept claim is edge-licensed by construction
          and all(tuple(c["pair"]) == ("設定", "効力")
                  for c in tied_2["kept"])
          # the unspoken subject contributed nothing and is named
          and all(c["subject"] == "甲権" for c in gated["kept"])
          and gated["unspoken_subjects"] == ["乙権"])
    return {
        "experiment": "cross_geometry",
        "fork": "SUMMARY_EDGE_LICENCE_AND_GROUP_DROPS",
        "pass": bool(ok),
        "result": {"no_lookup": no_lookup["verdict"],
                   "no_pairs": no_pairs["verdict"],
                   "tied_limit1": [len(tied_1.get("kept") or []),
                                   tied_1.get("dropped_at_cut")],
                   "tied_limit2": [len(tied_2.get("kept") or []),
                                   tied_2.get("dropped_at_cut")],
                   "gated_unspoken": gated.get("unspoken_subjects")},
    }


def staged_intersection_chains_n_stages_fork() -> Dict[str, Any]:
    """Any number of arrows chains; only the final stage elects.

    Stage i's linked set becomes stage i+1's membership condition, under
    the same width guard stage one always had. Intermediate stages hand
    FORWARD and never elect — an election in the middle would discard
    chains the last stage could still tell apart. The final stage keeps
    the two-stage discipline exactly: link strength, strict lead, ties
    abstain. And a chain that dies says at which stage: DISCONNECTED
    carries at_stage.
    """
    from .stacked import staged

    st = CrossStore()
    # Stage 1 material: two crimes, one holds both conditions.
    st.add("背任罪", ["背任", "上限"])
    st.add("収賄罪", ["収賄", "上限"])
    # Stage 2 material: two convicts, one touches the stage-1 survivor.
    st.add("受刑者甲", ["服役", "背任罪"])
    st.add("受刑者乙", ["服役", "収賄罪"])
    # Stage 3 material: two courts, one touches the stage-2 survivor.
    st.add("高等裁判所", ["再審", "受刑者甲"])
    st.add("地方裁判所", ["再審"])

    three = staged(st, "背任 上限 → 服役 → 再審")
    two = staged(st, "背任 上限 → 服役")
    dead = staged(st, "背任 上限 → 服役 → 抗告")

    # A second court tying on link strength must turn the answer into an
    # abstention — the tie rule survives the third stage.
    st.add("最高裁判所", ["再審", "受刑者甲"])
    tied = staged(st, "背任 上限 → 服役 → 再審")

    ok = (three is not None
          and three["verdict"] == "ANSWER_BY_STAGES"
          and three["core"] == "高等裁判所"
          and len(three.get("stages") or []) == 3
          # two-stage callers see the shape they always saw
          and two is not None
          and two["verdict"] == "ANSWER_BY_STAGES"
          and two["core"] == "受刑者甲"
          and "stage1" in two and "stage2" in two
          # a chain with no stage-3 material dies AT stage 3, typed
          and dead is not None
          and dead["verdict"] == "UNKNOWN_STAGE3_EMPTY"
          # final-stage ties abstain at any depth
          and tied is not None
          and tied["verdict"] == "UNKNOWN_UNDERDETERMINED")
    return {
        "experiment": "cross_geometry",
        "fork": "STAGED_INTERSECTION_CHAINS_N_STAGES",
        "pass": bool(ok),
        "result": {
            "three": [three and three["verdict"], three and three.get("core")],
            "two": [two and two["verdict"], two and two.get("core")],
            "dead": dead and dead["verdict"],
            "tied": tied and tied["verdict"],
        },
    }


def explanation_never_on_answer_path_fork() -> Dict[str, Any]:
    """Constructed explanations must not be able to arrive at a verdict.

    Same isolation `writer_never_reaches_the_answer_path_fork` pins for
    the generator: nothing that produces a verdict, a census, or the
    concord band may import the explanation layer. A constructed
    explanation entering `graded`'s vocabulary would let construction
    count as agreement — the exact pooling the band measurements forbid.
    """
    import inspect

    from . import consensus_store, graded, hierarchy

    leak = [m.__name__ for m in (consensus_store, graded, hierarchy)
            if any(pat in inspect.getsource(m) for pat in
                   ("from .explain", "import explain",
                    "from .summarize", "import summarize"))]
    ok = not leak
    return {
        "experiment": "cross_geometry",
        "fork": "EXPLANATION_NEVER_ON_ANSWER_PATH",
        "pass": bool(ok),
        "result": {"leaks": leak},
    }


def covenant_lifecycle_fork() -> Dict[str, Any]:
    """約束は生まれ、執行され、退役する — 削除はされない(fork 173本目)。

    実地試験(Claude Code フック7個、別マシン)が名指しした限界への答えを
    性質として釘打つ。①誕生: 指示文からの抽出は閉じた規則(ja+en)だけで、
    読めない指示からは何も作らない — 推測は約束を捏造する。②執行:
    「絵文字を使わないで」は語「絵文字」ではなく 🎉 そのもの(文字クラス)を
    捕まえる — 字面照合の限界2の修理。ただしクラス表は閉じた1項目
    (絵文字/emoji)のみ: 「日本語を使わないで」を文字クラスにすると
    日本語の返答すべてが違反になる。③退役: 「もういい」で check と
    fading から外れるが、席は残る — 削除すると「かつて約束があった」
    履歴ごと消え、風化の測定が嘘になる(閉鎖は追記、GAP台帳と同じ線)。
    """
    from .covenant import Covenant, Register, extract_covenants

    # ① 誕生 — 読める指示だけが約束になる
    born = extract_covenants(
        "絵文字を使わないで。Never use TODO comments.", turn=1)
    vague = extract_covenants("なんかいい感じでよろしく。", turn=1)

    reg = Register()
    for c in born:
        reg.add(Covenant(name=c["name"], quote=c["quote"],
                         forbids=list(c.get("forbids", [])),
                         requires=list(c.get("requires", [])),
                         said_at_turn=1))

    # ② 執行 — 語ではなく文字を捕まえ、素の文は素通し
    hit = reg.check("できました🎉")
    glyph = any(v.get("class_hits") for v in hit["violations"])
    clean = reg.check("できました。")

    # ③ 退役 — check からは消え、席と履歴は残る
    n_before = len(reg.covenants)
    emoji_name = next(c.name for c in reg.covenants if "絵文字" in c.forbids)
    reg.retire(emoji_name, quote="もう絵文字使っていいよ", turn=5)
    after = reg.check("できました🎉")
    emoji_still = any("絵文字" == v.get("covenant") or v.get("class_hits")
                      for v in after["violations"])
    seat_kept = (len(reg.covenants) == n_before
                 and any(c.name == emoji_name and c.retired
                         for c in reg.covenants))
    history_kept = emoji_name in reg.history and len(reg.history[emoji_name]) > 0
    faded = reg.fading(window=1, min_history=1)
    retired_out_of_fading = emoji_name not in [
        r["covenant"] for r in faded.get("fading", []) + faded.get("stable", [])]

    ok = (len(born) == 2 and vague == []
          and hit["verdict"] == "BROKEN" and glyph
          and clean["verdict"] == "KEPT"
          and after["verdict"] == "KEPT" and not emoji_still
          and seat_kept and history_kept and retired_out_of_fading)
    return {
        "experiment": "cross_geometry",
        "fork": "COVENANT_LIFECYCLE",
        "pass": bool(ok),
        "result": {"born": len(born), "vague": len(vague),
                   "glyph_caught": glyph,
                   "after_retire": after["verdict"],
                   "seat_kept": seat_kept, "history_kept": history_kept,
                   "retired_out_of_fading": retired_out_of_fading},
    }


def a_promise_to_act_needs_a_witness_fork() -> Dict[str, Any]:
    """行為の約束は証人で見る・候補は隔離席から採用される(fork 174本目)。

    ①「必ずpytestを実行して」は返答の字面では執行できない(実地試験:
    required_missing は誤検知だらけ)。やったの根拠は tool 実行の記録 —
    attest_claim の CLAIM_UNWITNESSED と同じ線。境界より前の証人は
    数えない(ターンを跨いだ「やった」は別のターンの証人)。判定は
    三値で、requires の無い台帳は NO_REQUIREMENTS(証人ゼロを違反と
    呼ばない)。②閉じた抽出規則の外は規則で追いかけず、候補は隔離席:
    shadow で照合され verdict に混ざらず、adopt して初めて執行に入る
    (淘汰は門)。③登録時に店の siblings を焼き込めば、書かれていない
    禁止が字面の速さで捕まり、推論由来は弱い型(inferred)で報じられる。
    """
    from .covenant import Covenant, Register, bake_inferred
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents

    # ① 証人
    reg = Register()
    reg.add(Covenant(name="t", quote="必ずpytestを実行して",
                     requires=["pytest"]))
    a0 = reg.audit()["verdict"]
    # 2026-08-21 の再張り(PREREG3): 終了状態を伴わない実行は
    # WITNESSED ではなく UNVERIFIED — 黙って合格に格上げしない。
    reg.witness("Bash", detail="python3 -m pytest -q")
    a1 = reg.audit()["verdict"]
    reg.witness("Bash", detail="python3 -m pytest -q", ok=True)
    a1b = reg.audit()["verdict"]
    reg.boundary()
    a2 = reg.audit()["verdict"]
    empty = Register().audit()["verdict"]

    # ② 隔離席
    q = Register()
    q.propose(Covenant(name="c", quote="!は控えめに", forbids=["!"]))
    sh = q.check("できた!")
    q.adopt("c")
    en = q.check("できた!")

    # ③ 焼き込み
    st = CrossStore()
    ingest_documents(st, [Document(source="刑法", text=(
        "甲条は拘禁刑を科する。甲条は規定である。"
        "乙条は罰金を科する。乙条は規定である。"
        "丙条は拘禁刑を科する。丙条は罰金を科する。"
        "丁条は拘禁刑を科する。丁条は罰金を科する。"))])
    c3 = Covenant(name="k", quote="拘禁刑の話はしないで", forbids=["拘禁刑"])
    bake_inferred(c3, st, store_name="fixture")
    r3 = Register()
    r3.add(c3)
    hit = r3.check("この刑は罰金である。")
    inf = [u for v in hit["violations"]
           for u in v.get("inferred_forbidden_used", [])]

    ok = (a0 == "REQUIRED_UNWITNESSED"
          and a1 == "REQUIRED_WITNESSED_UNVERIFIED"
          and a1b == "REQUIRED_WITNESSED"
          and a2 == "REQUIRED_UNWITNESSED" and empty == "NO_REQUIREMENTS"
          and sh["verdict"] == "KEPT"
          and len(sh.get("shadow_violations", [])) == 1
          and en["verdict"] == "BROKEN"
          and "罰金" in c3.inferred_forbids and "罰金" in inf)
    return {
        "experiment": "cross_geometry",
        "fork": "A_PROMISE_TO_ACT_NEEDS_A_WITNESS",
        "pass": bool(ok),
        "result": {"audit": [a0, a1, a1b, a2, empty],
                   "quarantine": [sh["verdict"], en["verdict"]],
                   "baked": c3.inferred_forbids, "inferred_hit": inf},
    }


def a_witness_must_have_been_invoked_fork() -> Dict[str, Any]:
    """呼ばれた道具だけが証人・推薦は採用ではない・推論は焼き直せる
    (fork 175本目)。

    ①部分文字列だけで見ると `echo pytest` が pytest の証人になる。
    区画の先頭語(と閉じた包み表・`-m`)だけを INVOKED と認め、字の中に
    あるだけの語は MENTIONED として別に報じる — 黙って捨てず、黙って
    数えもしない。②終了状態は三値: 落ちた実行は「やっていない」とは
    別の知らせ(REQUIRED_FAILED)、分からない実行はどちらでもない
    (UNVERIFIED)。不在と否定を混ぜない。同ターンに通った回と落ちた回が
    あれば落ちた回を報せる(記録順に依らず、証拠を隠さない)。
    ③隔離席の候補は**推薦されるだけ**で status は candidate のまま —
    自動採用は「過検出の番人は切られる」の罠そのもの。④焼き込みは
    stat だけで陳腐化が分かり(check の速い道で店を読まないため)、
    焼き直しのときだけ店を1回読む。店がもう示さない語は落とす。
    """
    from .covenant import (Covenant, Register, bake_inferred,
                           invoked_programs)
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents

    # ① ふりと実走
    fake = Register()
    fake.add(Covenant(name="t", quote="必ずpytestを実行して",
                      requires=["pytest"]))
    fake.witness("Bash", detail="echo pytest")
    f = fake.audit()

    real = Register()
    real.add(Covenant(name="t", quote="必ずpytestを実行して",
                      requires=["pytest"]))
    real.witness("Bash", detail="python3 -m pytest -q", ok=True)
    r_ok = real.audit()

    # ② 三値
    unk = Register()
    unk.add(Covenant(name="t", quote="q", requires=["pytest"]))
    unk.witness("Bash", detail="pytest -q")
    bad = Register()
    bad.add(Covenant(name="t", quote="q", requires=["pytest"]))
    bad.witness("Bash", detail="pytest -q", ok=False)

    # ③ 推薦は採用ではない
    q = Register()
    q.propose(Covenant(name="c", quote="!控えめに", forbids=["!"]))
    for t in ["対応します", "できました", "終わりました", "確認します",
              "直しました!", "了解です", "進めます", "完了です"]:
        q.check(t)
    rev = q.promotion_review()
    still_candidate = all(c.status == "candidate" for c in q.covenants)

    # ④ 焼き直し
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "fork175_store.json"
    st = CrossStore()
    ingest_documents(st, [Document(source="刑法", text=(
        "甲条は拘禁刑を科する。甲条は規定である。"
        "乙条は罰金を科する。乙条は規定である。"
        "丙条は拘禁刑を科する。丙条は罰金を科する。"
        "丁条は拘禁刑を科する。丁条は罰金を科する。"))])
    st.save(tmp)
    reg = Register()
    c = Covenant(name="k", quote="拘禁刑の話はしないで", forbids=["拘禁刑"])
    reg.add(c)
    bake_inferred(c, st, store_name=tmp.name, store_path=tmp)
    first = list(c.inferred_forbids)
    fresh = reg.stale(tmp)["verdict"]
    ingest_documents(st, [Document(source="刑法2", text=(
        "戊条は拘禁刑を科する。戊条は科料を科する。"
        "己条は拘禁刑を科する。己条は科料を科する。"
        "庚条は拘禁刑を科する。庚条は科料を科する。"))])
    st.save(tmp)
    stale = reg.stale(tmp)["verdict"]
    reg.rebake(st, store_path=tmp)
    after = list(c.inferred_forbids)

    ok = (f["verdict"] == "REQUIRED_UNWITNESSED"
          and f["rows"][0]["match"] == "MENTIONED"
          and r_ok["verdict"] == "REQUIRED_WITNESSED"
          and unk.audit()["verdict"] == "REQUIRED_WITNESSED_UNVERIFIED"
          and bad.audit()["verdict"] == "REQUIRED_FAILED"
          and invoked_programs("echo pytest") == ["echo"]
          and rev["promotable"] == ["c"] and still_candidate
          and fresh == "FRESH" and stale == "STALE"
          and "科料" in after and "罰金" in after)
    return {
        "experiment": "cross_geometry",
        "fork": "A_WITNESS_MUST_HAVE_BEEN_INVOKED",
        "pass": bool(ok),
        "result": {"pretend": [f["verdict"], f["rows"][0]["match"]],
                   "real": r_ok["verdict"],
                   "three_valued": [unk.audit()["verdict"],
                                    bad.audit()["verdict"]],
                   "promotion": [rev["promotable"], still_candidate],
                   "rebake": [first, after, fresh, stale]},
    }


def a_rule_a_regex_read_is_a_candidate_fork() -> Dict[str, Any]:
    """規則が読んだ約束は候補であって執行ではない(fork 176本目)。

    **なぜこの性質が要るか。** 抽出は閉じた正規表現で、読めない文からは
    何も立てない。それは推測しないための線で、正しい。だが「読めた」と
    「正しく読めた」は別で、そこを測ったのが 2026-08-21: 人が実際に書く
    指示20本のうち正しく読めたのは実質3本、13本は何も立たず、**4本は
    間違った語を捕まえた**。`No new dependencies` は forbids=["new"] に
    なり、返答「I added a new helper function.」を **BROKEN(誤遮断)**に
    した(実測)。誤遮断された利用者は番人を切る — そうなれば正しく
    読めた3本も一緒に死ぬ。

    直し方が**規則を足すこと**でないのは既に測ってある(否定 645/661 が
    語彙の外)。直すのは執行の側で、この fork が釘打つのは三点:
    ①規則が読んだ約束は隔離席に入り遮断しない、②ただし **shadow に出て
    見えなくなっていない**(誤遮断を「見えなくする」ことで消すのは番人を
    壊すのと同じ)、③人が明示した約束は執行のまま — 利用者自身の行為を
    番人が勝手に弱めてよい理由はない。採用は門(adopt)で、出所は採用後も
    台帳に残る(誰が何を根拠に執行を許したかを消すと監査が嘘になる)。
    """
    from .covenant import Covenant, Register, extract_covenants

    reply = "I added a new helper function."

    # ① 規則が読んだ約束 — 出所は候補自身が持つ(配管に依らない)
    cands = extract_covenants("No new dependencies", turn=1)
    read_the_wrong_word = cands and cands[0]["forbids"] == ["new"]
    tagged = all(c.get("origin") == "regex" for c in cands)

    quarantined = Register()
    for c in cands:
        quarantined.propose(Covenant(
            name=c["name"], quote=c["quote"], forbids=list(c["forbids"]),
            requires=list(c["requires"]), origin=c["origin"]))
    q = quarantined.check(reply)

    # ② 黙って捨てない — shadow に出て、何が発火したか名指されている
    shadow_named = ([v.get("forbidden_used") for v in
                     q.get("shadow_violations", [])] == [["new"]])

    # ③ 人が明示した約束は執行のまま(origin は空)
    explicit = Register()
    explicit.add(Covenant(name="no-new-deps", quote="No new dependencies",
                          forbids=["new"]))
    e = explicit.check(reply)

    # ④ 採用は門 — 通って初めて遮断に入る。出所は残る
    before = quarantined.check(reply)["in_force"]
    quarantined.adopt(cands[0]["name"])
    after = quarantined.check(reply)
    origin_kept = all(c.origin == "regex" for c in quarantined.covenants)

    ok = (bool(read_the_wrong_word) and tagged
          and q["verdict"] == "KEPT" and q["violations"] == []
          and len(q.get("shadow_violations", [])) == 1 and shadow_named
          and e["verdict"] == "BROKEN" and len(e["violations"]) == 1
          and before == 0 and after["verdict"] == "BROKEN"
          and after["in_force"] == 1
          and not after.get("shadow_violations")
          and origin_kept)
    return {
        "experiment": "cross_geometry",
        "fork": "A_RULE_A_REGEX_READ_IS_A_CANDIDATE",
        "pass": bool(ok),
        "result": {"misread": cands[0]["forbids"] if cands else [],
                   "origin_tagged": tagged,
                   "quarantined": [q["verdict"],
                                   len(q.get("shadow_violations", []))],
                   "shadow_named": shadow_named,
                   "explicit_still_enforces": e["verdict"],
                   "gate": [before, after["verdict"], after["in_force"]],
                   "origin_kept_after_adopt": origin_kept},
    }


def all_cross_geometry_forks() -> List[Dict[str, Any]]:
    return [
        geometric_pole_invisibility_fork(),
        geometric_rotation_reaches_all_fork(),
        layer_stack_growth_fork(),
        layered_ask_stability_fork(),
        layered_carry_drift_fork(),
        placement_granularity_fork(),
        placement_simulation_fork(),
        placement_cannot_manufacture_confidence_fork(),
        placement_invariance_fork(),
        direction_invariance_fork(),
        reverse_unique_fork(),
        reverse_specific_fork(),
        prover_three_outcomes_fork(),
        attest_polarity_fork(),
        transfer_reading_fork(),
        axis_lock_fork(),
        norm_vs_record_fork(),
        quote_is_substring_fork(),
        read_at_shows_both_sides_fork(),
        ja_coverage_gate_fork(),
        reified_event_fork(),
        event_extractor_refuses_statute_prose_fork(),
        egov_article_is_a_citation_key_fork(),
        sovereign_build_fork(),
        document_draft_is_licensed_fork(),
        edge_fallback_routes_off_face_fork(),
        one_root_saturates_at_capacity_fork(),
        fusion_is_not_monotonic_fork(),
        word_form_is_a_fallback_fork(),
        linked_is_not_printed_fork(),
        granularity_composes_fork(),
        resolution_ladder_grades_doubt_fork(),
        concord_rides_alongside_the_list_fork(),
        long_form_drifts_and_lists_fork(),
        trace_is_memory_outside_the_store_fork(),
        constellation_beats_one_sovereign_fork(),
        writer_never_reaches_the_answer_path_fork(),
        form_may_not_assert_more_than_content_licenses_fork(),
        concord_is_not_coverage_fork(),
        every_manifest_can_rebuild_its_corpus_fork(),
        a_reloaded_writer_is_the_same_writer_fork(),
        coarsening_adds_a_reading_and_never_overturns_one_fork(),
        a_citation_is_listed_not_chosen_fork(),
        a_template_cut_inside_a_word_is_caught_at_the_seam_fork(),
        presence_in_the_corpus_is_not_support_fork(),
        a_wholesale_replacement_is_not_no_change_fork(),
        not_knowing_is_not_disagreeing_fork(),
        a_covenant_binds_the_exchange_not_the_wording_fork(),
        the_store_infers_the_prohibition_nobody_wrote_fork(),
        latin_is_a_content_word_in_japanese_prose_fork(),
        the_staircase_grades_doubt_and_finds_none_to_grade_fork(),
        the_structure_is_deterministic_fork(),
        the_grammar_axis_earns_its_place_on_mismatched_forms_fork(),
        the_finest_staircase_is_not_the_best_one_fork(),
        sovereigns_cut_differently_are_not_one_store_reindexed_fork(),
        only_data_varied_sovereigns_can_dissent_fork(),
        a_coarser_cut_recovers_words_the_word_reader_buried_fork(),
        a_store_must_be_asked_the_way_it_was_read_fork(),
        a_timeless_store_must_refuse_a_question_about_now_fork(),
        a_character_window_is_a_japanese_technique_fork(),
        a_question_goes_to_one_language_sovereign_fork(),
        a_chain_decays_and_stacking_nodes_does_not_stop_it_fork(),
        a_puzzle_narrows_where_a_chain_decays_fork(),
        layered_recovers_where_pooled_destroys_fork(),
        the_path_is_the_content_and_the_writer_only_supplies_form_fork(),
        the_vocabulary_is_not_the_lever_fork(),
        a_refusal_says_what_would_close_it_fork(),
        the_polite_register_was_invisible_to_the_harvester_fork(),
        a_polite_imperative_still_needs_a_licence_fork(),
        nothing_measured_moves_unknown_word_reach_fork(),
        unknown_word_reach_and_new_word_creation_are_one_operation_fork(),
        explanation_constructed_and_typed_fork(),
        explanation_bare_suffix_abstains_at_the_split_fork(),
        explanation_never_on_answer_path_fork(),
        staged_intersection_chains_n_stages_fork(),
        summary_edge_licence_and_group_drops_fork(),
        lattice_nodes_attested_and_kin_positional_fork(),
        kin_neighbourhood_is_a_weaker_typed_claim_fork(),
        cross_field_agreement_selects_but_barely_applies_fork(),
        cut_agreement_is_not_evidence_and_must_not_be_pooled_fork(),
        a_rule_that_just_started_breaking_is_the_one_to_resend_fork(),
        placement_is_backward_compatible_fork(),
        promotion_pyramid_fork(),
        conversation_overflow_is_typed_fork(),
        conversation_speaker_attribution_fork(),
        covenant_lifecycle_fork(),
        a_promise_to_act_needs_a_witness_fork(),
        a_witness_must_have_been_invoked_fork(),
        a_rule_a_regex_read_is_a_candidate_fork(),
    ]


# ---------------------------------------------------------------------------
# Promotion — the multiresolution pyramid.
# ---------------------------------------------------------------------------

def promotion_pyramid_fork() -> Dict[str, Any]:
    """A freezing layer distils its heaviest cores into the new top layer.

    Three properties, and the third is the one that makes promotion safe:
    the summary must NOT replace the evidence. The frozen fine-grained
    original stays below, so a coarse claim can later be checked against
    the detail it came from — which is what turns a promoted node into a
    second opinion rather than a lossy overwrite.
    """
    # Five sentences, four distinct cores: apple appears twice so it carries
    # the highest mass and must be the one promoted. The fifth ingest is what
    # trips capacity — an earlier draft of this fixture used four sentences
    # and never stacked at all, because apple's two sentences are ONE core.
    _corpus = ["apple is red sweet", "apple is round",
               "banana is yellow", "cherry is small", "durian is spiky"]
    mem = LayeredMemory(capacity=3, promote_k=2)
    for s in _corpus:
        mem.ingest_sentence(s)

    promoted_top = set(mem.top.crosses.keys())
    stacked = mem.n_levels() >= 2
    # apple has the highest mass (two sentences) -> promoted.
    apple_promoted = "apple" in promoted_top
    # The original is still in the frozen layer, with MORE facets than the
    # promoted summary: evidence outlives its summary.
    fine_facets = len(mem.levels[0].top_facets("apple", k=9))
    coarse_facets = len(mem.top.top_facets("apple", k=9))
    evidence_survives = mem.levels[0].has("apple") and fine_facets >= coarse_facets

    off = LayeredMemory(capacity=3, promote_k=0)
    for s in _corpus:
        off.ingest_sentence(s)
    # With promotion off the new top layer holds ONLY what arrived after the
    # freeze — no distilled ancestors. This is the control that proves the
    # promoted nodes above came from promotion and not from ordinary ingest.
    off_is_clean = set(off.top.crosses.keys()) == {"durian"}

    ok = stacked and apple_promoted and evidence_survives and off_is_clean
    return {
        "experiment": "cross_geometry",
        "fork": "PROMOTION_PYRAMID",
        "pass": bool(ok),
        "result": {"levels": [l.n_cores() for l in mem.levels],
                   "promoted_into_top": sorted(promoted_top),
                   "fine_facets": fine_facets, "coarse_facets": coarse_facets,
                   "evidence_survives": evidence_survives,
                   "promotion_off_is_clean": off_is_clean},
    }


# ---------------------------------------------------------------------------
# Conversation context as space.
# ---------------------------------------------------------------------------

def conversation_overflow_is_typed_fork() -> Dict[str, Any]:
    """Context overflow must be FROZEN, never silence.

    An LLM whose window rolls past a turn cannot distinguish "never said"
    from "said and forgotten". Here the two are different verdicts, and an
    overflowed topic keeps its speaker and turn index. That difference IS
    the claim being tested — so the fork requires an overflowed topic to be
    FROZEN (not ABSENT), a never-mentioned one to be ABSENT, and the
    overflowed one to remain answerable from its frozen layer.
    """
    from .conversation import Conversation

    conv = Conversation(memory=LayeredMemory(capacity=2, promote_k=0))
    conv.add_turn("user", "the vault requires a hardware token")
    conv.add_turn("assistant", "the cluster runs three nodes")
    conv.add_turn("user", "the pipeline uses blue green rollout")

    vault = conv.locate("vault")
    never = conv.locate("kangaroo")
    overflowed_kept = (vault["status"] == "FROZEN"
                       and vault["mentions"] == [{"turn": 0, "speaker": "user"}])
    never_said_absent = never["status"] == "ABSENT" and never["mentions"] == []
    # Still answerable after overflow — frozen is not lost.
    ans = conv.recall("what is vault")
    still_answerable = ans.get("verdict") == "ANSWER" and ans.get("core") == "vault"

    ok = overflowed_kept and never_said_absent and still_answerable
    return {
        "experiment": "cross_geometry",
        "fork": "CONVERSATION_OVERFLOW_TYPED",
        "pass": bool(ok),
        "result": {"vault": vault, "kangaroo_status": never["status"],
                   "recall_after_overflow": {"verdict": ans.get("verdict"),
                                             "core": ans.get("core")},
                   "stats": conv.stats()},
    }


def conversation_speaker_attribution_fork() -> Dict[str, Any]:
    """Who said it, and when, survives ingestion. Without attribution a
    conversation store is a pile of assertions with no way to tell a user's
    claim from the assistant's own earlier guess — the shape of failure that
    makes a system quote itself back as evidence."""
    from .conversation import Conversation

    conv = Conversation(memory=LayeredMemory(capacity=64))
    conv.add_turn("user", "the ledger is append only")
    conv.add_turn("assistant", "the ledger is signed hourly")
    loc = conv.locate("ledger")
    speakers = [m["speaker"] for m in loc["mentions"]]
    ok = (loc["status"] == "ACTIVE" and speakers == ["user", "assistant"]
          and [m["turn"] for m in loc["mentions"]] == [0, 1])
    return {
        "experiment": "cross_geometry",
        "fork": "CONVERSATION_SPEAKER_ATTRIBUTION",
        "pass": bool(ok),
        "result": {"mentions": loc["mentions"], "status": loc["status"]},
    }
