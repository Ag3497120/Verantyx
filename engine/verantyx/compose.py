"""Long-form prose from the store — grammatical, not fluent, and never invented.

The distinction this module exists to test is a real one. Fluency is the
choice among many valid phrasings, and that choice is a distribution, learned
from use; rules cannot supply it, and adding rules until they collide is just
a hand-built worse version of one. But GRAMMATICALITY of a declarative
statement of fact is a small closed system — 「Xは Y です」, "X is Y" — and a
closed system is exactly what rules are for.

So this composes reports, not essays. The output is correct and monotonous.
For a situation report or a decision rationale, monotonous is the right
register: a responder reading about a road closure is not looking for
variety, and the sameness of the sentence shapes is what lets them scan.

The property that matters more than either:

    every sentence is traceable to a stored fact

`compose_report` returns the text and, alongside it, the facet each sentence
came from. `unsupported_sentences()` re-checks the whole output against the
store and returns anything that is not backed — which is always empty by
construction here, and is checked anyway, because "cannot hallucinate" is a
claim that should be tested rather than asserted.

Length comes from structure, not from padding: one section per arm, one
sentence per fact, one paragraph per source disagreement. A store with more
in it produces a longer report, and that is the only way this gets longer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .arm_schema import ARMS, ArmIndex
from .cross_store import CrossStore
from .document_ingest import _sources_for, deep_report

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")
#: Kanji compounds of two or more characters take する — 配布する, 復旧する.
#: Everything else is treated as a plain noun and takes です. Crude, closed,
#: and inspectable, which is the point: a wrong choice here yields a stiff
#: sentence, never a false one.
_SURU = re.compile(r"^[㐀-䶿一-鿿]{2,}$")

#: Facets that are adjective stems rather than nouns; です attaches directly
#: but the reading differs, so they are listed rather than guessed.
_JA_ADJ = {"危険", "安全", "必要", "可能", "不可"}


@dataclass
class Sentence:
    text: str
    #: The stored facet this sentence states. Empty only for connectives,
    #: which assert nothing.
    evidence: str = ""
    sources: List[str] = field(default_factory=list)


@dataclass
class Report:
    core: str
    lang: str
    sentences: List[Sentence] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.sentences) if self.lang == "ja" \
            else " ".join(s.text for s in self.sentences)

    def as_dict(self) -> Dict[str, Any]:
        return {"core": self.core, "lang": self.lang, "text": self.text,
                "n_sentences": len(self.sentences),
                "chars": len(self.text),
                "evidence": [s.evidence for s in self.sentences if s.evidence]}


# ---------------------------------------------------------------------------
# Sentence shapes — the closed grammar
# ---------------------------------------------------------------------------

#: Correct predicate form per polar term. These come from a closed
#: vocabulary (polarity.ANTONYM_PAIRS_JA), so the form can be stated instead
#: of inferred — which is the whole argument for rules over a model, applied
#: honestly to the one place the vocabulary really is closed. Inferring it
#: from shape produced 「通行可能しています」 and 「通行止しています」, both wrong:
#: 通行可能 is adjectival and 通行止 is a plain noun, and no regex over kanji
#: count distinguishes either from 配布, which does take する.
# Predicate forms ship as data with the vocabulary they describe —
# adding a pair through the overlay and its predicate form is one
# edit in one file, not two edits in two languages.
from .ja_grammar import PREDICATES as _JA_PREDICATE


def _ja_state(core: str, facet: str) -> str:
    """One fact as one Japanese sentence.

    Three shapes, chosen by the facet's own form rather than by meaning:
    サ変名詞 takes しています, listed adjectives take です directly, and
    anything else is a plain noun predicate. Getting the choice wrong makes
    the sentence stiff; it cannot make it untrue, which is the trade this
    module is willing to take.
    """
    known = _JA_PREDICATE.get(facet) or _JA_PREDICATE.get(facet.replace("not_", ""))
    if known:
        return core + known
    if facet in _JA_ADJ:
        return f"{core}は{facet}です。"
    if _SURU.match(facet):
        return f"{core}は{facet}しています。"
    return f"{core}は{facet}です。"


def _en_state(core: str, facet: str) -> str:
    subject = core.replace("_", " ")
    value = facet.replace("_", " ").replace("#p", "")
    return f"The {subject} is {value}."


#: Facet keys whose relation to the core IS known: a polar aspect states a
#: property of the core, so the copula is correct for these and only these.
def _relation_is_known(facet: str, polar_values: set) -> bool:
    return facet in polar_values


def _state(core: str, facet: str, lang: str) -> str:
    return _ja_state(core, facet) if lang == "ja" else _en_state(core, facet)


def _replay(store: CrossStore, core: str, facet: str) -> str:
    """The sentence this facet was learned from, verbatim.

    Preferred over composing one, and the reason is the finding that produced
    this function. A facet carries no relation to its core: `blankets`,
    `midnight` and `main_street` all sit in the same bag, so a copula template
    emits "The shelter is blankets" — well-formed, and false, because it
    asserts identity where the source said possession. Surface grammaticality
    is reachable by rule; the RELATION is not, because it was never stored.

    Replaying the original sentence sidesteps that entirely: the relation
    comes back with the words that carried it. Composition then supplies what
    it can actually supply — selection, ordering, attribution, and the
    separation of settled from contested — which is the part a summariser
    destroys and the part a reader needs.
    """
    slot = (store.provenance.get(core, {}) or {}).get(facet)
    if not slot or len(slot) < 3:
        return ""
    raw = re.sub(r"\s*\(reported by [^)]+\)\s*", "", str(slot[2])).strip()
    return raw


def _cite(sources: List[str], lang: str) -> str:
    if not sources:
        return ""
    joined = "、".join(sources) if lang == "ja" else ", ".join(sources)
    return f"（出典: {joined}）" if lang == "ja" else f" (source: {joined})"


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def compose_report(store: CrossStore, core: str, *, lang: str = "auto",
                   arms: Optional[ArmIndex] = None,
                   max_facts: int = 12) -> Report:
    """A situation report for one topic, built from what is stored.

    Order is deliberate and is the report's argument: what is agreed, then
    what is contested and who says which, then what nobody answered. A reader
    who stops after one paragraph has still read the settled facts; a reader
    who stops before the last has at least not mistaken a gap for a finding.
    """
    if lang == "auto":
        lang = "ja" if _CJK.search(core) else "en"
    rep = Report(core=core, lang=lang)
    detail = deep_report(store, core, arms)

    # 1. Settled
    settled = detail["settled"][:max_facts]
    settled_start = len(rep.sentences)
    if settled:
        rep.sentences.append(Sentence(
            "以下は確認された情報です。" if lang == "ja"
            else "The following is settled."))
        # A replayed sentence can carry a claim that is contested elsewhere in
        # the same report — "the shelter is closed" is one source's sentence,
        # and closed/open is exactly what the sources disagree about. Listing
        # it as settled while also listing it as disputed is the one thing this
        # report must never do, so contested wording is kept out of settled.
        contested_words = {side["claim"]
                           for entry in detail["disputed"]
                           for side in entry["sides"]}
        seen_text: set = set()
        for item in settled:
            body = _replay(store, core, item["claim"])
            if body and any(w in body.lower() or w in body
                            for w in contested_words):
                continue
            if not body:
                # No stored sentence to replay. Rather than assert a relation
                # that was never recorded, name the fact without claiming what
                # it is to the core.
                body = (f"{core}に関する記録: {item['claim']}。" if lang == "ja"
                        else f"Recorded for {core}: {item['claim']}.")
            if body in seen_text:
                continue          # one source sentence can back several facets
            seen_text.add(body)
            rep.sentences.append(Sentence(body + _cite(item["sources"], lang),
                                          evidence=item["claim"],
                                          sources=item["sources"]))

    # Everything under the heading may have been filtered out as contested,
    # and a heading with nothing under it reads as "we found nothing settled"
    # when the truth is "everything here is disputed".
    if len(rep.sentences) == settled_start + 1:
        rep.sentences.pop()

    # 2. Contested — the part a summary destroys
    if detail["disputed"]:
        rep.sentences.append(Sentence(
            "以下は情報源によって食い違っています。" if lang == "ja"
            else "The following is contested between sources."))
        for entry in detail["disputed"]:
            for side in entry["sides"]:
                # Polar values ARE a property of the core — "open"/"closed" is
                # a state, not a possession — so the copula is correct here,
                # which is why this branch composes and the settled branch
                # replays.
                text = _state(core, side["claim"], lang) + _cite(side["sources"], lang)
                rep.sentences.append(Sentence(text, evidence=side["claim"],
                                              sources=side["sources"]))
            rep.sentences.append(Sentence(
                "この点は未確定です。" if lang == "ja"
                else "This point is unresolved."))

    # 2b. Updated — one story told twice, shown as a timeline, because a
    # reopening rendered as a conflict is how the board loses its reader.
    if detail.get("updated"):
        rep.sentences.append(Sentence(
            "以下は更新されました（新しい発表が古い発表を置き換えています）。"
            if lang == "ja" else
            "The following was updated — newer reports supersede older ones."))
        for entry in detail["updated"]:
            cur = entry["current"]
            text = _state(core, cur["claim"], lang)
            cite = _cite(cur["sources"], lang)
            when = cur.get("when", "")
            rep.sentences.append(Sentence(
                text + (f"（{when} 時点{cite}）" if lang == "ja"
                        else f" (as of {when}{cite})"),
                evidence=cur["claim"], sources=cur["sources"]))
            for old_side in entry["superseded"]:
                prev = re.sub(r"(?:です|しています|されています)?[。.]$", "",
                              _state(core, old_side["claim"], lang))
                rep.sentences.append(Sentence(
                    (f"（それ以前の発表では{prev}でした"
                     f"{_cite(old_side['sources'], lang)}）") if lang == "ja"
                    else (f"(Earlier reports said: {prev}"
                          f"{_cite(old_side['sources'], lang)}.)"),
                    evidence=old_side["claim"], sources=old_side["sources"]))

    # 3. Arms — the six questions, answered or named as unanswered
    if arms is not None:
        held = arms.arms.get(core, {})
        for arm in ARMS:
            for snippet in held.get(arm, [])[:2]:
                body = snippet.split(" — ")[0]
                rep.sentences.append(Sentence(body if body.endswith(("。", "."))
                                              else body + ("。" if lang == "ja" else "."),
                                              evidence=arm))
        missing = detail.get("missing") or []
        if missing:
            names = "、".join(m["arm"] for m in missing) if lang == "ja" \
                else ", ".join(m["arm"] for m in missing)
            rep.sentences.append(Sentence(
                f"次の観点は記録がありません: {names}。" if lang == "ja"
                else f"No record answers these: {names}."))

    if not rep.sentences:
        rep.sentences.append(Sentence(
            f"{core}について記録がありません。" if lang == "ja"
            else f"Nothing is recorded about {core}."))
    return rep


def compose_digest(store: CrossStore, cores: List[str], *,
                   lang: str = "auto", arms: Optional[ArmIndex] = None) -> Report:
    """Many topics in one document. Length comes from how much is stored."""
    if lang == "auto":
        lang = "ja" if any(_CJK.search(c) for c in cores) else "en"
    out = Report(core="digest", lang=lang)
    for core in cores:
        out.sentences.append(Sentence(
            f"\n【{core}】\n" if lang == "ja" else f"\n## {core}\n"))
        out.sentences.extend(compose_report(store, core, lang=lang,
                                            arms=arms).sentences)
    return out


def unsupported_sentences(store: CrossStore, report: Report) -> List[str]:
    """Sentences asserting something the store does not hold.

    Empty by construction — every asserting sentence is built from a facet
    read out of the store moments earlier. Checked anyway: "this cannot
    hallucinate" is a claim about a program, and claims about programs are
    worth running rather than believing.
    """
    # Every core in the report, not just `report.core` — a digest's core is
    # the literal string "digest", against which every real facet looks
    # unsupported. The first run of this check reported ten fabrications in
    # text that was entirely backed.
    known: set = set()
    for core in store.crosses:
        known |= {f for f, _ in store.top_facets(core, k=200)}
    # deep_report strips the `aspect:` prefix from contested claims, so the
    # bare value is what appears in the prose and must be matched too.
    known |= {f.split(":", 1)[1] for f in known if ":" in f}
    bad: List[str] = []
    for s in report.sentences:
        if not s.evidence or s.evidence in ARMS:
            continue
        if s.evidence not in known:
            bad.append(s.text)
    return bad
