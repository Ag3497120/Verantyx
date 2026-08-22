"""A constructed explanation for a term the store never held.

`reach` lands NEAR an unheld term and says by which route. This module
takes the UNITS landing one step further, and the step is the minimal
case of multi-stage crossing: two paths (one per unit), one intersection
(the facets both units' crosses hold).

    電荷密度    not held
    電荷        held — one path
    密度        held — the other
    crossing    the facets the two crosses share
    edges       pairs the corpus wrote in ONE sentence, when a lookup
                is supplied

## Constructed, and typed as such

The verdict is EXPLAINED_BY_UNITS and every payload carries
``constructed: True`` plus a reader-visible marker in the draft text.
Nothing here is testimony: the corpus never wrote a sentence about the
term, and this module never pretends it did. Every content token is a
held core, a held facet, or an edge the corpus wrote; the FRAME ("X is
composed of A and B") is a claim about the store's own decomposition,
recountable by anyone holding the store.

It follows that nothing here may enter a verdict, a census, or the
concord vocabulary. This layer is hand-over only — the same seat
`writer` sits in, pinned the same way (see
EXPLANATION_NEVER_ON_ANSWER_PATH in `cross_geometry_forks`).

## Abstentions are load-bearing

ABSTAIN_BARE_SUFFIX_SPLIT — every candidate split leaves a one-character
head. 発明者 -> 者 is what the head-final preference costs, and the
judgment is made AT THE SPLIT, never by tightening the vocabulary gate:
moving the gate was measured to be the wrong lever (MIN_ATTEST 3 -> 1
lifted speakable centres to 64% at 4% real words). If a bare suffix ever
passes, the split side is what gets fixed.

ABSTAIN_SPLIT_TIED — two splits score the same and neither leads
strictly. A tie broken any other way is the manufactured agreement the
staircase measurements caught (unanimity 86 -> 321, accuracy 73.3% ->
23.7%).

ABSTAIN_UNIT_NOT_A_WORD — no held unit passes the vocabulary gate. An
explanation whose subject is not a word is the exact failure the
vocabulary layer exists to stop (7.4% of facets are words).

CONTAINMENT is handed back untouched: a longer word that happens to hold
the term locates it and does not explain it, and the two must stay
distinguishable for the reader.

## Measured — 150 held-out cores, reach's protocol reconstructed

Kanji-only federation cores of length 3-5, sorted, deterministic stride
down to 150, popped from the store BEFORE the unit model and the
containment ladder were built. Same protocol as `reach`'s measurement,
NOT the same set — the original selection script was not preserved and
the store has grown since, which is why reach's own route split reads
differently here (90 UNITS / 19 CONTAINMENT against its recorded
50 / 46). The funnel, on the 89,369-core federation (22,389 eligible,
stride 149) with the writer's 51,798-word vocabulary as the gate:

    UNITS landed                           90 of 150
      EXPLAINED_BY_UNITS                   53   (58.9% of UNITS)
      ABSTAIN_BARE_SUFFIX_SPLIT            20
      ABSTAIN_UNIT_NOT_A_WORD              16
      ABSTAIN_SPLIT_TIED                    1
    CONTAINMENT (handed back, no claim)    19
    UNKNOWN_NO_REACH                       41

26 of the 53 drafts carry a two-path crossing (both units held).
Abstention is 41.1% of UNITS and is reported as a result, not a
failure: the twenty bare-suffix terms are 〜者/〜法-shaped heads a
reader must not be handed a meaning for, and the sixteen not-a-word
terms landed on units the corpus never writes standalone.

With the lattice wired (same 150, tools/measure_explain_funnel.py):

    UNKNOWN_NO_REACH                       41 -> 3
    KIN_NEIGHBOURHOOD                      38

The 38 are neighbourhoods, not landings — 㭍月例祭 gets the 祭@R
family (司祭、感謝祭、映画祭), which is the right room and no more.
The three still refused (水戸芸術館, 準絶滅危惧, 話者指示性) have no
two attested kin, and one relative is a point, not a family.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: The marker a draft carries so an audit surface can tell construction
#: from testimony at a glance. Appended, never optional.
CONSTRUCTED_MARK = "（構成的説明 — 証言ではない）"


def _splits_for(model: Any, term: str) -> List[Dict[str, Any]]:
    """Candidate splits, the same condition `reach.units_for` applies."""
    from .granularity import SPLITS

    out: List[Dict[str, Any]] = []
    for a, b in SPLITS.get(len(term), ()):
        left, right = term[:a], term[a:]
        if (left in model.slots.get((a, "L"), ())
                and right in model.slots.get((b, "R"), ())):
            out.append({"left": left, "right": right, "at": a})
    return out


def _unit(store: Any, labels: Any, vocab: Any, part: str, pos: str) -> Dict[str, Any]:
    held = part in store.crosses and part not in labels
    return {"part": part, "position": pos, "held": held,
            "word": part in vocab}


def kin_neighbourhood(
    lat: Any,
    store: Any,
    term: str,
    vocab: Any,
) -> Optional[Dict[str, Any]]:
    """The term's lattice families, as a NEIGHBOURHOOD — never a meaning.

    Measured ceiling (lattice.py): kin recovers 4% of a held-out word's
    own facets — ten times chance and nowhere near comprehension. So
    this hand-over claims exactly what the lattice attests: which
    positional families the term's units belong to, and what those
    FAMILIES talk about. The facets shown are the family's, labelled as
    such; calling them the term's would be the overclaim the ceiling
    forbids. Returns None below two distinct kin — one relative is a
    point, not a family.
    """
    from .lattice import kin, predict_facets

    fams = kin(lat, term, min_unit=1)
    distinct = sorted({w for ws in fams.values() for w in ws})
    if len(distinct) < 2:
        return None
    family_facets = [f for f in predict_facets(lat, store, term)
                     if f in vocab][:6]
    parts = []
    for slot in sorted(fams):
        parts.append("%s の家族（%s）" % (slot, "、".join(fams[slot][:4])))
    text = "%sは未保持。%s に近い。" % (term, "；".join(parts))
    if family_facets:
        text += "家族が語る面: %s。" % "、".join(family_facets[:4])
    return {
        "verdict": "KIN_NEIGHBOURHOOD", "constructed": True,
        "term": term, "families": {k: v for k, v in sorted(fams.items())},
        "family_facets": family_facets,
        "text": text + CONSTRUCTED_MARK,
        "note": "a neighbourhood, not a meaning: the facets are what the "
                "positional families talk about (measured recall of the "
                "term's own facets: 4%), and every family member is an "
                "attested word",
    }


def explain(
    store: Any,
    term: str,
    *,
    model: Any,
    vocab: Any,
    edges: Optional[Any] = None,
    judge: Optional[Any] = None,
    lat: Optional[Any] = None,
) -> Dict[str, Any]:
    """One constructed explanation, or a typed abstention — never a guess.

    ``vocab`` is the word gate (`vocabulary.Vocabulary`); only units that
    pass it are spoken. ``edges`` is the optional same-sentence pair
    lookup with `vera.Vera.edges`' shape: (core, shown) -> pairs.
    ``lat`` is an optional `lattice.Lattice`; when the unit model cannot
    reach the term at all, the lattice's positional families widen the
    hand-over (measured: 86 -> 140 of 150 predictable) as a
    KIN_NEIGHBOURHOOD — typed apart because it is a weaker claim.
    """
    from .reach import reach

    r = reach(store, term, model=model, judge=judge)
    if r["verdict"] != "UNITS":
        # HELD needs no construction, CONTAINMENT locates without
        # explaining. NO_REACH may still have lattice kin — a
        # neighbourhood is less than an explanation and more than a
        # bare refusal, and the type says which one the reader holds.
        if r["verdict"] == "UNKNOWN_NO_REACH" and lat is not None:
            nb = kin_neighbourhood(lat, store, term, vocab)
            if nb is not None:
                return nb
        return r

    labels = getattr(store, "source_labels", set()) or set()
    splits = _splits_for(model, term)

    # Bare suffix, judged at the split: a one-character head is not a
    # subject to explain with, whatever the vocabulary says about it.
    speakable_splits = [s for s in splits if len(s["right"]) > 1]
    if not speakable_splits:
        units = [_unit(store, labels, vocab, s["right"], "R") for s in splits]
        return {"verdict": "ABSTAIN_BARE_SUFFIX_SPLIT", "constructed": True,
                "term": term, "units": units,
                "note": "every candidate split leaves a one-character "
                        "head; the judgment is the split's, not the "
                        "vocabulary gate's"}

    # One split must lead strictly. Score = units that could be spoken
    # (held AND word), then units merely held; a tie abstains.
    def score(s: Dict[str, Any]) -> tuple:
        us = [_unit(store, labels, vocab, s["right"], "R"),
              _unit(store, labels, vocab, s["left"], "L")]
        return (sum(1 for u in us if u["held"] and u["word"]),
                sum(1 for u in us if u["held"]))

    ranked = sorted(speakable_splits, key=score, reverse=True)
    if len(ranked) > 1 and score(ranked[0]) == score(ranked[1]):
        return {"verdict": "ABSTAIN_SPLIT_TIED", "constructed": True,
                "term": term,
                "splits": [[s["left"], s["right"]] for s in ranked[:4]],
                "note": "two splits score the same; a tie broken any "
                        "other way is manufactured agreement"}
    chosen = ranked[0]

    units = [_unit(store, labels, vocab, chosen["right"], "R"),
             _unit(store, labels, vocab, chosen["left"], "L")]
    spoken = [u for u in units if u["held"] and u["word"]]
    if not spoken:
        return {"verdict": "ABSTAIN_UNIT_NOT_A_WORD", "constructed": True,
                "term": term, "units": units,
                "note": "no held unit passes the vocabulary gate; an "
                        "explanation needs a subject the corpus writes "
                        "standalone"}

    # The crossing — the minimal multi-stage intersection. Lexicographic
    # on purpose: presence is the claim, rank is not.
    crossing: List[str] = []
    held_parts = [u["part"] for u in units if u["held"]]
    if len(held_parts) == 2:
        a, b = (store.crosses.get(held_parts[0]) or {}), (store.crosses.get(held_parts[1]) or {})
        crossing = sorted(f for f in set(a) & set(b) if f not in labels)[:8]

    subject = spoken[0]["part"]
    out: Dict[str, Any] = {
        "verdict": "EXPLAINED_BY_UNITS", "constructed": True,
        "term": term, "split": [chosen["left"], chosen["right"]],
        "units": units, "subject": subject,
        "subject_position": spoken[0]["position"],
        "crossing": crossing,
    }

    if edges is not None and subject in store.crosses:
        shown = [u["part"] for u in units if u["part"] != subject] + crossing
        try:
            pairs = edges(subject, shown)
            if pairs:
                out["edge_pairs"] = pairs
        except Exception:
            pass

    # 「〜に分解される」, never 「〜から構成される語」: the term itself was
    # never attested, and calling it a word would be this layer asserting
    # the one thing it cannot know.
    if len(spoken) == 2:
        frame = "%sは、%sと%sに分解される。" % (
            term, chosen["left"], chosen["right"])
    else:
        frame = "%sは、%sを単位に含む。" % (term, subject)
    # The word gate applies to everything SPOKEN, shared facets included:
    # the payload's crossing stays raw for recounting, but a draft that
    # says 「共有する面: a、受」 hands the reader fragments as words. Same
    # line as the units — the gate decides what may be said, never what
    # is held.
    speakable_crossing = [f for f in crossing if f in vocab]
    if speakable_crossing:
        frame += "両単位の十字が共有する面: %s。" % "、".join(
            speakable_crossing[:4])
    out["text"] = frame + CONSTRUCTED_MARK
    out["note"] = ("constructed from unit testimony; not itself attested. "
                   "every token is a held core, a held facet, or an edge "
                   "the corpus wrote")
    return out
