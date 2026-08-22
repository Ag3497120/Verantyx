"""Three states for a vocabulary proposal, so a person reads fewer of them.

The IDE carries this idea in `IRVerificationEngine`: an LLM emits a hypothesis
and a DETERMINISTIC engine checks it against what is already known, returning
one of three states rather than a score —

    verified      corroborated by evidence already held
    unverified    no evidence either way; a person must look
    contradicts   the evidence says the opposite

Reading that engine before porting it turned up something worth stating: the
Swift `contradicts` case is declared in the result type and `verifySingle`
never returns it. Only `verified` and `unverified` are reachable. So this is
not a translation — the third state has to be built, and Vera is a better
place to build it than a chat loop, because Vera has an internal answer key
that a conversation does not.

What corroborates a vocabulary proposal, and what refutes it:

    verified      the same word was anchored by the succession grammar more
                  than once, by more than one SOURCE. One document phrasing
                  something oddly is a coincidence; two independent documents
                  putting the same unknown word in the same completion slot is
                  the corpus agreeing with itself.
    contradicts   adding the join would make a single source assert BOTH poles
                  of that aspect about one core. A document rarely contradicts
                  itself, so the join is far more likely to be wrong than the
                  document — the same reasoning `self_audit.self_conflict`
                  already uses, applied before the join exists rather than
                  after.
    unverified    everything else, which on the real corpora is most of it.

The point is the queue, not the automation. `contradicts` is a refutation, so
it can drop a candidate without a person; `verified` is corroboration, which
is NOT proof that the word means what the slot implies — 「断水は限界です」
would corroborate itself in two documents and 限界 is still not a restoration.
So verified proposals are sorted first and marked, never accepted. The
asymmetry from `vocab_growth` is unchanged: this file has no way to write an
overlay either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: How many distinct sources must anchor a word before corroboration counts.
#: Two, because one source repeating itself is one source.
MIN_SOURCES = 2

STATES = {
    "verified": (
        "More than one source put this word in the same completion slot. The "
        "corpus agrees with itself — which is corroboration, not proof that "
        "the word carries that pole."
    ),
    "unverified": (
        "One source, and nothing refutes it. This is the normal state and the "
        "one that needs a reader."
    ),
    "contradicts": (
        "Adding this join would make a single source assert both poles of the "
        "aspect about one core. A document rarely contradicts itself, so the "
        "join is the likelier mistake."
    ),
}


@dataclass
class Verdict:
    state: str                    # verified | unverified | contradicts
    why: str = ""
    sources: List[str] = field(default_factory=list)
    #: For `contradicts`: the core and aspect that would collide.
    collision: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in ("", [], None)}


def _self_conflicts(store) -> set:
    """(core, aspect) where ONE source holds both poles — the misread shape.

    Uses `deep_report`, which resolves a claim back to the DOCUMENT it came
    from. A first version read provenance's stored snippet instead, and that
    snippet is the SENTENCE: two sentences from one file looked like two
    sources, the intersection was always empty, and the refutation never
    fired once. Same lesson as the defect-report aggregation key, in a third
    place — text is not identity.
    """
    from .document_ingest import deep_report

    out = set()
    for core in list(store.crosses):
        for entry in deep_report(store, core).get("disputed", []):
            sources = {s for side in entry["sides"] for s in side["sources"]}
            if len(sources) == 1:
                out.add((core, entry["aspect"]))
    return out


def sources_for(word: str, paths: List[str]) -> List[str]:
    """Which documents anchored this word through a succession slot."""
    from .catalog import collect
    from .document_loaders import load_paths
    from .ja_grammar import ALIASES, ASPECT_OF, TERMS
    from .vocab_growth import _slot_patterns

    known = set(ASPECT_OF) | set(ALIASES)
    docs = load_paths(collect(list(paths))["files"])["documents"]
    found: List[str] = []
    for slot, rx in _slot_patterns():
        for doc in docs:
            for m in rx.finditer(doc.text):
                got = (m.group(2) if slot == "A" else m.group(1))
                if got != word or got in known or any(t in got for t in TERMS):
                    continue
                if doc.source not in found:
                    found.append(doc.source)
    return found


def check(proposal, paths: List[str]) -> Verdict:
    """Which of the three states this proposal is in, decided by measurement.

    `contradicts` is established by SIMULATION: apply the join, re-read, and
    see whether a source that did not contradict itself before now does. The
    join is put back either way — a check that leaves the grammar changed
    would make every later candidate measure a different engine.
    """
    from . import ja_grammar as grammar
    from .catalog import collect
    from .cross_store import CrossStore
    from .document_ingest import ingest_documents
    from .document_loaders import load_paths

    files = collect(list(paths))["files"]

    def conflicts() -> set:
        store = CrossStore(track_provenance=True)
        ingest_documents(store, load_paths(files)["documents"])
        return _self_conflicts(store)

    before = conflicts()
    entry = proposal.overlay_entry()
    grammar.ASPECT_JOINS.append(entry)
    try:
        grammar._rebuild()
        after = conflicts()
    finally:
        grammar.ASPECT_JOINS.remove(entry)
        grammar._rebuild()

    new = sorted(after - before)
    if new:
        core, aspect = new[0]
        return Verdict(
            "contradicts",
            f"the join makes one source hold both poles of {aspect} on {core}",
            collision=f"{core} / {aspect}")

    srcs = sources_for(proposal.word, paths)
    if len(srcs) >= MIN_SOURCES:
        return Verdict("verified",
                       f"{len(srcs)} independent sources anchored it in the "
                       f"same slot", sources=srcs)
    return Verdict("unverified", "one source, and nothing refutes it",
                   sources=srcs)


def triage(proposals: List[Any], paths: List[str]
           ) -> List[Tuple[Any, Verdict]]:
    """Every proposal with its state, refutations last.

    Sorted so a reader meets corroborated candidates first and refuted ones at
    the bottom, where they can be skipped — the whole reason for having three
    states instead of a queue in discovery order.
    """
    rank = {"verified": 0, "unverified": 1, "contradicts": 2}
    out = [(p, check(p, paths)) for p in proposals]
    out.sort(key=lambda pv: (rank.get(pv[1].state, 1), -getattr(pv[0], "seen", 0)))
    return out
