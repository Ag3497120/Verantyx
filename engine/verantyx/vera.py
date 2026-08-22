"""One entry point: a question in, a typed answer with its route out.

Everything measured this session sits in layers, and the layers only work
layered — six pooled combinations were worse, six layered ones better. This
wires them in the order the measurements put them:

    1  language     detect, and route to the sovereign built from that
                    language. Never a census across two: mixing them
                    answered superconductivity with contract
    2  deictic      「今日の天気は」 has no answer in a store with no clock.
                    Typed out before anything is looked up
    3  staircase    grain and grammar over the cores of that sovereign,
                    six settings for kanji and two for latin — character
                    windows collide at 26 letters and discriminate at 2,000
    4  core         the inference core, entered directly or seeded by the
                    staircase when it cannot enter at all. Sections converge
                    and the axis words along the agreed paths are the answer
    5  reach        when the term is not held: split it into units the
                    corpus attests (10.4% overlap) before falling back on a
                    longer word that contains it (4.5%)
    6  words        the path becomes the content and a harvested template
                    supplies only the form
    7  remedy       what an expert would register to close a refusal, and
                    which refusals should not be closed

Each stage hands the next something typed. None of them votes with another.

## Every answer says how it was reached

`ANSWER` is the core converging on the question as asked. `SEEDED` means the
staircase had to name the subject first. `UNITS` and `CONTAINMENT` are two
different ways of landing near a word the store never held, measured 16.3x
and 3.9x over chance, and reported apart because a reader discounting one
needs to know which they have.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class Vera:
    """The federation, its sovereigns, and everything built over them."""

    stores: Dict[str, Any] = field(default_factory=dict)
    judges: Dict[str, Any] = field(default_factory=dict)
    models: Dict[str, Any] = field(default_factory=dict)
    writer: Optional[Any] = None
    built: Dict[str, Any] = field(default_factory=dict)
    #: Data-varied witnesses: one merged store per SELECTION RULE (百科 is
    #: "articles that cite statutes", 法学 is "articles in doctrine
    #: categories", 多分野 is "sixteen named fields", 法令 is the statute
    #: corpus). They never vote — the trajectory measured what pooling does
    #: (out-of-corpus errors 0 -> 8 when cut-varied readings joined a
    #: census, answered 284 -> 208 when domains were split INTO the vote).
    #: They are read independently AFTER the verdict, and the answer carries
    #: how many of them reached the same core. Data-varied agreement is
    #: evidence; this is the place the trajectory said it belongs — beside
    #: the verdict, never in it.
    witnesses: Dict[str, Any] = field(default_factory=dict)
    #: Optional provenance lookup (core, shown facets) -> source leaves.
    #: Supplied by the sqlite path, absent on the pickle path — provenance
    #: at facet grain lives in the published file's tables.
    origin: Optional[Any] = None
    #: Optional edge lookup (core, facets) -> same-sentence pairs, from the
    #: vera_edges.db sidecar. Edges are the geometry's relation seats: a
    #: face holds an item, an edge holds which two items one sentence wrote
    #: together — the licence the sentence gate needs.
    edges: Optional[Any] = None
    #: Optional gap store (vera_gaps.db) — refusals report already-mapped
    #: holes instead of pretending each absence is news.
    gaps: Optional[Any] = None

    def add(self, lang: str, store: Any) -> "Vera":
        from .graded import GradedJudge, settings_for
        from .reach import build_model

        probe = "これは日本語です。" if lang == "ja" else "This is English."
        self.stores[lang] = store
        self.judges[lang] = GradedJudge(settings_for(probe)).build(store)
        self.models[lang] = build_model(store)
        self.built[lang] = {"cores": len(store.crosses),
                            "settings": len(self.judges[lang].settings)}
        return self

    def ask(self, query: str, *, limit: int = 3,
            **kwargs: Any) -> Dict[str, Any]:
        from .lang import detect
        from .remedy import remedy
        from .stacked import ask as stacked_ask, in_words

        lang = detect(query)
        if lang == "latin" and "en" in self.stores:
            lang = "en"
        # Kanji without kana detects as Chinese — the same shape
        # `document_ingest._place` already handles for table rows: a
        # kana-less segment inside a Japanese document is Japanese. A
        # kana-less QUERY typed at a system holding a Japanese sovereign is
        # the query-level case: 「過失 故意 責任」 is three Japanese law
        # terms and no kana, and refusing it as an unheld language while
        # holding all three terms is a routing failure, not honesty. A
        # genuinely Chinese question still gets no false answer — the
        # Japanese sovereign refuses on its own evidence.
        if lang == "zh" and "zh" not in self.stores and "ja" in self.stores:
            lang = "ja"
        store = self.stores.get(lang)
        if store is None:
            out = {"verdict": "UNKNOWN_LANGUAGE_NOT_HELD", "language": lang,
                   "have": sorted(self.stores)}
            return {**out, "remedy": remedy(out)}

        judge = self.judges[lang]
        graded = judge.ask(query)
        # A question about now cannot be answered by a store with no clock,
        # and the deictic is in the QUESTION — so it is settled before any
        # lookup rather than after one succeeds.
        if graded.get("verdict") == "UNKNOWN_TIME_DEPENDENT":
            return {**graded, "language": lang, "remedy": remedy(graded)}

        core = stacked_ask(store, query, judge=judge, **kwargs)
        out: Dict[str, Any] = {**core, "language": lang,
                               "coverage": graded.get("coverage"),
                               "as_core": graded.get("as_core"),
                               "as_facet_only": graded.get("as_facet_only"),
                               "missing": graded.get("missing")}

        if out.get("text") and self.writer is not None:
            if self.edges is not None and out.get("core_key"):
                shown = str(out["text"]).split()[1:]
                try:
                    out["edge_pairs"] = self.edges(str(out["core_key"]), shown)
                except Exception:
                    pass
            out["written"] = in_words(store, out, self.writer, limit=limit,
                                      edge_partners=getattr(
                                          self, "edge_partners", None))

        # Nothing was held. Try to land NEAR the terms rather than refuse
        # outright, and say by which route — the two are not the same claim.
        if not out.get("text"):
            from .reach import reach

            landed = []
            unreached = []
            for t in (graded.get("terms") or []):
                r = reach(store, t, model=self.models.get(lang), judge=judge)
                if r["verdict"] in ("UNITS", "CONTAINMENT"):
                    landed.append(r)
                elif r["verdict"] == "UNKNOWN_NO_REACH":
                    unreached.append(t)
            # A UNITS landing may carry a constructed explanation — the
            # minimal two-path crossing, typed EXPLAINED_BY_UNITS or a
            # typed abstention, never folded into any verdict here.
            # CONTAINMENT is handed back bare on purpose: locating is
            # not explaining. Needs the writer's vocabulary as the word
            # gate, so without a writer nothing is attached.
            if self.writer is not None and (landed or unreached):
                from .explain import explain

                for rr in landed:
                    if rr.get("verdict") != "UNITS":
                        continue
                    try:
                        ex = explain(store, rr["term"],
                                     model=self.models.get(lang),
                                     vocab=self.writer.vocab,
                                     edges=self.edges, judge=judge)
                        if ex.get("constructed"):
                            rr["explained"] = ex
                    except Exception:
                        pass
                # Terms the unit model cannot reach may still have
                # lattice kin — a NEIGHBOURHOOD, typed apart because it
                # is a weaker claim than a landing (measured: it widens
                # 86 -> 140 of 150 at no precision gain).
                for t in unreached:
                    try:
                        ex = explain(store, t,
                                     model=self.models.get(lang),
                                     vocab=self.writer.vocab,
                                     edges=self.edges, judge=judge,
                                     lat=self._kin_lattice())
                        if ex.get("verdict") == "KIN_NEIGHBOURHOOD":
                            landed.append(ex)
                    except Exception:
                        pass
            if landed:
                out["reached"] = landed
        # Grain agreement, beside the data-varied witnesses and never pooled
        # with them: cut-varied readings agreeing is STRUCTURE, data-varied
        # is EVIDENCE (measured: pooling the two let out-of-corpus terms
        # reach quorum, 0 -> 8). Both are worth showing; they answer
        # different questions, so they ride under different names. The
        # number was always computed — the staircase's rungs vote every
        # ask — and simply never surfaced, which is why a viewer watching
        # the rungs saw only the abstainers and read failure into a 2/6.
        if graded.get("agreeing") is not None:
            out["grain"] = {"agree": graded.get("agreeing"),
                            "of": len(self.judges[lang].settings)}
        if out.get("core_key") and lang == "ja" and self.witnesses:
            out["witnesses"] = self.attest(out)
        if out.get("core_key") and out.get("text") and self.origin is not None:
            shown = str(out["text"]).split()[1:]
            try:
                out["facet_origin"] = self.origin(str(out["core_key"]), shown)
            except Exception:
                pass
        # CALIBRATED TIER — the four signals composed, not another signal.
        # Every number below is measured elsewhere and only COMBINED here:
        # grain bands (3+ rungs agreeing read 100% on the fixture bank,
        # 2 read ~31%), data-varied witness pairs (97.6% vs 53.7%), and
        # order evidence. The tier changes NOTHING about the verdict — it
        # is the reader's discount rate, stated instead of implied.
        if out.get("core_key"):
            g = (out.get("grain") or {}).get("agree") or 0
            wt = (out.get("witnesses") or {}).get("agree") or 0
            why = []
            score = 0
            if g >= 3: score += 2; why.append("grain %d" % g)
            elif g == 2: score += 1; why.append("grain 2")
            if wt >= 2: score += 2; why.append("witnesses %d" % wt)
            elif wt == 1: score += 1; why.append("witness 1")
            if out.get("order_evidence") in ("ranked", "aspect"):
                score += 1; why.append("order " + out["order_evidence"])
            out["tier"] = {"label": ("strong" if score >= 4 else
                                     "medium" if score >= 2 else "weak"),
                           "score": score, "why": why}
        # KNOWN GAP — a refusal checks the gap store: if this absence is
        # already recorded (with which witnesses hold it), the reader sees
        # a mapped hole, not a fresh one.
        # NEAR TERMS — a refusal offers same-slot siblings as SUGGESTIONS,
        # never as answers: 返済 refused suggests 弁済 because both fill
        # the same slots under shared parents. Suggesting is not deciding;
        # the reader picks, which is why ties are fine here.
        if str(out.get("verdict", "")).startswith("UNKNOWN") and lang == "ja":
            subj = out.get("subject")
            if subj:
                try:
                    from .covenant import siblings
                    near = siblings(store, subj, limit=6)
                    if near:
                        out["near_terms"] = near[:5]
                except Exception:
                    pass
        if (str(out.get("verdict", "")).startswith("UNKNOWN")
                and self.gaps is not None):
            subj = out.get("subject")
            if subj and subj in self.gaps.crosses:
                out["known_gap"] = sorted(self.gaps.crosses[subj])[:6]
        out["remedy"] = remedy(out)
        # Opt-in only: when $VERA_QUEUE names a file, queueable refusals
        # are appended there and become the fetch list for `grow`. The
        # answer itself is unchanged — the queue is how the corpus learns
        # where the questions found it thin.
        from .grow import log_refusal

        log_refusal(out)
        return out

    def _kin_lattice(self) -> Optional[Any]:
        """The lattice over the writer's vocabulary, built once per Vera.

        Supplies kin hand-overs for terms the unit model cannot reach;
        None without a writer, because lattice membership IS the
        vocabulary sieve and there is no gate to build it behind.
        """
        if self.writer is None:
            return None
        if getattr(self, "_lat", None) is None:
            from .lattice import build

            self._lat = build(list(self.writer.vocab.attested))
        return self._lat

    def attest(self, out: Dict[str, Any]) -> Dict[str, Any]:
        """How many independent corpora reach the same core, read separately.

        Each witness is built from documents a DIFFERENT selection rule
        chose, so two witnesses landing on the same core is two unrelated
        document sets saying the same thing — the trajectory measured that
        kind of agreement at 97.6% against 53.7% for structural agreement
        on the same match count. The read is the seeded subject (the same
        entry the main answer used), each witness runs its own full
        consensus with its own gates, and an abstaining witness is not a
        disagreement — it simply never read about the subject.

        What this does NOT do — measured before shipping — is expose
        sense pollution: 時効 attests 2/2 because a 労働基準法 article
        (百科) also holds the core, even though the SHOWN facets all come
        from one 法学 article about 法の不遡及. Core-name agreement cannot
        see that, and per-facet witness attestation decided 0 of 1,776 tied
        cores, so the pollution is surfaced by `facet_origin` (provenance
        display) instead. The badge answers one question only: how many
        unrelated document sets know this subject at all.
        """
        from .consensus_store import consensus_over_store

        target = str(out.get("core_key") or "")
        probe = (out.get("seeded_from") or {}).get("query") or target
        by: Dict[str, Any] = {}
        agree = answered = 0
        for name in sorted(self.witnesses):
            r = consensus_over_store(self.witnesses[name], probe)
            wcore = r.get("core_key")
            if r.get("verdict", "").startswith(("ANSWER", "SEEDED")) and wcore:
                answered += 1
                same = str(wcore) == target
                agree += same
                by[name] = {"core": r.get("core"), "same": same}
            else:
                by[name] = {"verdict": r.get("verdict")}
        return {"agree": agree, "answered": answered,
                "of": len(self.witnesses), "by": by}

    def report(self) -> Dict[str, Any]:
        return {"sovereigns": dict(self.built),
                "writer": (self.writer.report() if self.writer else None)}


def load(root: Any = None) -> Vera:
    """The built federation, the English sovereign, and the writer."""
    import pickle
    from pathlib import Path

    from .cross_store import CrossStore
    from .writer import Writer

    root = Path(root or (corpus_root()))
    v = Vera()

    doms = pickle.loads((root / "build" / "federation.pkl").read_bytes())
    ja = CrossStore()
    for d in doms:
        for s in doms[d].values():
            ja.source_labels |= getattr(s, "source_labels", set())
            # SUM across leaves, never overwrite. This line was
            # `.update(cr)`, which kept the LAST leaf's count for any
            # (core, facet) two leaves both attest — so cross-leaf
            # corroboration, the one evidential signal a flat corpus has,
            # was discarded at the door, and the merge result depended on
            # leaf iteration order. Measured on the answered-core bank:
            # summing decides the leading facet on 6/11 cores against 3/11,
            # and 91% of facet counts are 1 in a single leaf, so within-leaf
            # frequency alone cannot rank anything.
            for c, cr in s.crosses.items():
                dst = ja.crosses.setdefault(c, {})
                for f, n in cr.items():
                    dst[f] = dst.get(f, 0) + n
            # core_count was never merged at all, which left the Japanese
            # sovereign with an empty mass table while the English one had a
            # real one — `mass()` returned 0 for every Japanese core, and
            # `placement.derive_queries` found zero eligible cores because
            # of it.
            for c, n in getattr(s, "core_count", {}).items():
                ja.core_count[c] = ja.core_count.get(c, 0) + n
    v.add("ja", ja)

    # One witness per selection rule, merged the same way. The witnesses
    # hold the same leaves the sovereign holds — partitioned, not copied —
    # so nothing here can know something the sovereign does not.
    for d in doms:
        w = CrossStore()
        for s in doms[d].values():
            w.source_labels |= getattr(s, "source_labels", set())
            for c, cr in s.crosses.items():
                dst = w.crosses.setdefault(c, {})
                for f, n in cr.items():
                    dst[f] = dst.get(f, 0) + n
        if w.crosses:
            v.witnesses[d] = w

    en_path = root / "build" / "english.pkl"
    if en_path.is_file():
        v.add("en", pickle.loads(en_path.read_bytes()))

    wpath = root / "build" / "writer.json"
    if wpath.is_file():
        v.writer = Writer.load(wpath)
    return v
