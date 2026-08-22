"""Grow the vocabulary from the documents' own narrative — as proposals.

The last line the loop could not reach on its own was the seed line: which
words oppose which. A layout defect has an internal answer key and a guard
conflict has one, but no transformation of a document reveals what a word the
engine has never seen MEANS — that judgement needs the world, and the honest
versions of this project have said so every time.

What a document series does carry is SUCCESSION. An official report narrates
states ending: the outage that opened report 3 is closed out in report 12,
and the closing sentence has a fixed grammar — the state as topic, and a
completion predicate:

    停電は復旧済み                the predicate is known, the topic is not
    断水は解消しました              the topic is known, the predicate is not

Those are the two slots, and each one anchors an unknown word to a known one:

    A   known "-" topic + unknown completed predicate
        the predicate ends the state, so it is the "+" pole of the same
        aspect — 解消 sits where 復旧 sits.
    B   unknown topic + known "+" completed predicate
        the topic is what got completed away, so it is the "-" pole —
        停電 sits where 断水 sits. Found live: the vocabulary that read
        five corpora and 21 million characters does not know 停電, and
        「停電は復旧済み」 is in 内閣府's own reports.

Why this stays a PROPOSAL and never becomes a repair, stated as the asymmetry
the gate enforces:

    the gate can REJECT a candidate — adding the join and re-measuring is
        internal, and a candidate that costs a confirmed detection or breaks
        the planted suite is dropped before anyone sees it
    the gate cannot ACCEPT one — succession is statistics, not proof. 「断水は
        限界です」 fits slot A's grammar and 限界 is not a restoration. The
        difference between "this word sat where a pole sits" and "this word IS
        that pole" is a fact about Japanese, and the corpus cannot testify
        about itself.

So what a person receives is the residue: candidates that appeared in a real
succession slot, carry completion morphology, and measurably break nothing.
The person's whole remaining job is the one judgement the machine cannot
make. Everything else — finding, anchoring, damage-testing, deduplicating,
writing the overlay snippet — is done before they look.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROPOSALS = "vocab_proposals.json"

#: Completion morphology — the grammar of a state being over. Deliberately
#: narrow: しつつある (still in progress) is excluded, because a state that is
#: "clearing" has not cleared, and a candidate anchored to it would carry the
#: wrong pole.
_TAIL = r"(?:済み?|しました|されました|いたしました|が確認された|になりました|した(?=[。、\n]))"

#: A candidate word: 2–6 CJK characters, no digits, no dates. One character
#: is debris (the audit's own finding), and past six it is a clause.
_WORD = r"[㐀-䶿一-鿿]{2,6}"

_MID = r"[^。、\n]{0,14}?"

#: A row in a parallel list: a subject, whitespace, a predicate, an optional
#: state marker. Anchored at both ends so a fragment of prose cannot match.
_ROW = re.compile(r"^\s*([㐀-䶿一-鿿ァ-ヺー]{2,10})\s+"
                  r"([㐀-䶿一-鿿]{2,6})(あり|なし|中|済み?)?\s*$")

#: Predicate positions that are never a state, however parallel the rows look.
#: A place name in the predicate column is the failure mode this guard exists
#: for: 「天草市 熊本県あり」 is a malformed row, not evidence that 熊本県 is
#: a state word, and without this the sibling rule proposes prefecture names.
_NOT_A_STATE = re.compile(r"(?:都|道|府|県|市|区|町|村|郡|島|港|駅|線|川|山)$")

#: How the marker fixes the pole when there is no anchor to borrow it from.
#: あり asserts the state; なし denies it; 〜中 and 〜済 are the two ends of a
#: process. These are facts about the marker, not about any vocabulary.
_MARKER_POLE = {"あり": None, "なし": None, "中": "-", "済": "+", "済み": "+"}


@dataclass
class Proposal:
    word: str
    aspect: str
    polarity: str                      # "+" | "-"
    slot: str                          # "A" | "B"
    anchor: str                        # the known term that anchored it
    seen: int = 1
    #: Redacted, like everything that leaves the reading path.
    shapes: List[str] = field(default_factory=list)
    measured: Dict[str, Any] = field(default_factory=dict)

    def overlay_entry(self) -> List[str]:
        return [self.word, self.aspect, self.polarity]

    def as_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["overlay"] = {"aspect_joins": [self.overlay_entry()]}
        d["still_yours_to_decide"] = (
            f"Measurement shows this join breaks nothing confirmed. It cannot "
            f"show that {self.word} really is the {self.polarity} pole of "
            f"{self.aspect} — a word can sit in a completion slot without "
            f"being one. Read the shapes; if {self.word} could end a sentence "
            f"about {self.aspect} without meaning the state "
            f"{'ended' if self.polarity == '+' else 'held'}, refuse it."
        )
        return d


def _slot_patterns() -> List[Tuple[str, re.Pattern]]:
    from .ja_grammar import ASPECT_OF, ALIASES, TERMS

    neg = sorted((t for t in TERMS
                  if ASPECT_OF.get(ALIASES.get(t, t), ("", ""))[1] == "-"),
                 key=len, reverse=True)
    pos = sorted((t for t in TERMS
                  if ASPECT_OF.get(ALIASES.get(t, t), ("", ""))[1] == "+"),
                 key=len, reverse=True)
    out = []
    if neg:
        out.append(("A", re.compile(
            "(" + "|".join(map(re.escape, neg)) + ")"
            + r"[はがも]" + _MID + "(" + _WORD + ")" + _TAIL)))
    if pos:
        out.append(("B", re.compile(
            "(" + _WORD + ")" + r"[はがも]" + _MID
            + "(" + "|".join(map(re.escape, pos)) + ")" + _TAIL)))
    return out


def siblings(paths: List[str]) -> List[Proposal]:
    """Parallel rows: one row's predicate is known, the next one's is not.

        宇城市 断水あり     断水 is in the vocabulary
        天草市 冠水あり     冠水 is not — but it is in the same column, of the
        八代市 断水あり     same table, under the same marker, beside rows that
        氷川町 冠水あり     ARE known

    The succession slots need an anchor inside the same sentence, so on a
    corpus whose vocabulary barely overlaps this engine's they find nothing —
    measured: 0 candidates on 8 FDMA bulletins, where 2 of the 31 known terms
    appear at all. A list does not need the anchor in the sentence. It needs
    it in a SIBLING, which is a much weaker requirement and the shape official
    documents are actually written in.

    The pole comes from the parallel rather than from the word. 断水 is the
    negative pole of 復旧; 冠水 stands in the same construction under the same
    marker, so it is the negative pole of the same aspect. That is exactly the
    question a frozen embedding table could not answer — 64.5% leave-one-out,
    a coin flip — and structure settles it without one.
    """
    from .catalog import collect
    from .defect_report import skeleton
    from .document_loaders import load_paths
    from .ja_grammar import ALIASES, ASPECT_OF

    docs = load_paths(collect(list(paths))["files"])["documents"]
    found: Dict[Tuple[str, str, str], Proposal] = {}

    for doc in docs:
        # Group by MARKER, not by position: a table's rows are siblings when
        # they say the same kind of thing, and 「…あり」 beside 「…なし」 are
        # opposite claims rather than parallel ones.
        by_marker: Dict[str, List[Tuple[str, str, str]]] = {}
        for line in doc.text.split("\n"):
            m = _ROW.match(line)
            if not m:
                continue
            subj, pred, marker = m.group(1), m.group(2), m.group(3) or ""
            by_marker.setdefault(marker, []).append((subj, pred, line.strip()))

        for marker, rows in by_marker.items():
            if len(rows) < 2:
                continue
            anchors = [(p, ASPECT_OF[ALIASES.get(p, p)])
                       for _s, p, _l in rows if ALIASES.get(p, p) in ASPECT_OF]
            if not anchors:
                continue
            aspect, pole = anchors[0][1]
            # Every anchor in the group must agree. A column holding both
            # poles is not a parallel list, it is a status column, and
            # borrowing a pole from it would be a coin flip with extra steps.
            if len({a[1] for a in anchors}) > 1:
                continue
            for subj, pred, line in rows:
                if ALIASES.get(pred, pred) in ASPECT_OF:
                    continue
                if _NOT_A_STATE.search(pred) or pred == subj:
                    continue
                key = (pred, aspect, pole)
                if key in found:
                    found[key].seen += 1
                else:
                    found[key] = Proposal(
                        pred, aspect, pole, "S", anchors[0][0],
                        shapes=[skeleton(line, keep={pred, anchors[0][0]})])
    return sorted(found.values(), key=lambda p: -p.seen)


def successions(paths: List[str]) -> List[Proposal]:
    """Every unknown word a real succession slot anchored, deduplicated."""
    from .catalog import collect
    from .defect_report import skeleton
    from .document_loaders import load_paths
    from .ja_grammar import ASPECT_OF, ALIASES, TERMS

    known = set(ASPECT_OF) | set(ALIASES)
    docs = load_paths(collect(list(paths))["files"])["documents"]
    found: Dict[Tuple[str, str, str], Proposal] = {}

    for slot, rx in _slot_patterns():
        for doc in docs:
            for m in rx.finditer(doc.text):
                anchor, word = (m.group(1), m.group(2)) if slot == "A" else (
                    m.group(2), m.group(1))
                if word in known or any(t in word for t in TERMS):
                    continue
                canonical = ALIASES.get(anchor, anchor)
                aspect, _pol = ASPECT_OF[canonical]
                polarity = "+" if slot == "A" else "-"
                key = (word, aspect, polarity)
                sent_start = doc.text.rfind("\n", 0, m.start()) + 1
                sent_end = doc.text.find("\n", m.end())
                shape = skeleton(
                    doc.text[sent_start:sent_end if sent_end > 0 else None]
                    .strip()[:120],
                    keep=set(known) | {word})
                if key in found:
                    found[key].seen += 1
                    if shape not in found[key].shapes:
                        found[key].shapes.append(shape)
                else:
                    found[key] = Proposal(word, aspect, polarity, slot,
                                          canonical, shapes=[shape])
    return sorted(found.values(), key=lambda p: -p.seen)


def damage_test(proposal: Proposal, paths: List[str]) -> Tuple[bool, str]:
    """Whether the join measurably breaks anything. Reject-only, by design.

    A True here means "nothing confirmed got worse", never "the word is
    right" — the docstring at the top of this module is the contract, and the
    eval pins that nothing in this file can write an overlay.
    """
    import contextlib
    import io

    from . import ja_grammar as grammar
    from .corpus_audit import audit_paths
    from .generalization_eval import main as _gen

    before = audit_paths(paths)
    det_before = sorted(f"{d.topic} / {d.aspect}" for d in before.detections)

    entry = proposal.overlay_entry()
    grammar.ASPECT_JOINS.append(entry)
    try:
        grammar._rebuild()
        with contextlib.redirect_stdout(io.StringIO()):
            planted = _gen() == 0
        after = audit_paths(paths)
    finally:
        grammar.ASPECT_JOINS.remove(entry)
        grammar._rebuild()

    det_after = sorted(f"{d.topic} / {d.aspect}" for d in after.detections)
    lost = [d for d in det_before if d not in det_after]
    if not planted:
        return False, "the planted suite stopped passing"
    if lost:
        return False, f"it costs {len(lost)} confirmed detection(s): {', '.join(lost)}"
    return True, (f"nothing confirmed got worse; claims "
                  f"{before.polar_claims} -> {after.polar_claims}")


def propose(paths: List[str], *, home: Path) -> List[Dict[str, Any]]:
    """Find, damage-test, and queue — everything up to the human judgement."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / PROPOSALS
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            existing = {p["word"]: p for p in json.loads(
                path.read_text(encoding="utf-8"))}
        except ValueError:
            existing = {}

    from .proposal_verify import check as _verify

    out: List[Dict[str, Any]] = []
    seen_words = set()
    for prop in list(successions(paths)) + list(siblings(paths)):
        if prop.word in seen_words:
            continue
        seen_words.add(prop.word)
        old = existing.get(prop.word)
        if old and old.get("status") in ("accepted", "refused"):
            # A judgement was made; re-proposing it every run would teach the
            # operator to stop reading the queue.
            continue
        ok, why = damage_test(prop, paths)
        if not ok:
            # Dropped before anyone sees it — the reject half is mechanical.
            out.append({"word": prop.word, "status": "dropped", "reason": why})
            continue

        # Three states, not a score. `contradicts` is a REFUTATION — the join
        # would make one source hold both poles of the aspect — so it drops
        # the candidate without a reader, the same way damage_test does.
        # `verified` is only corroboration: two sources putting a word in the
        # same completion slot is the corpus agreeing with itself, and a
        # corpus can agree with itself about something untrue. So it sorts
        # first and is marked, never accepted.
        verdict = _verify(prop, paths)
        if verdict.state == "contradicts":
            out.append({"word": prop.word, "status": "dropped",
                        "reason": verdict.why, "collision": verdict.collision})
            continue

        prop.measured = {"verdict": why, "state": verdict.state,
                         "why": verdict.why, "sources": verdict.sources}
        row = {**prop.as_dict(), "status": "proposed", "state": verdict.state}
        out.append(row)
        existing[prop.word] = row

    # Corroborated first, so the reader meets the likely-real ones while they
    # are still reading carefully.
    out.sort(key=lambda r: (0 if r.get("state") == "verified" else
                            1 if r.get("status") == "proposed" else 2))

    # If the operator configured a lexicon, its two measured-usable answers
    # ride along and order the queue. Measured before trusted: state-likeness
    # separated the real queue's true candidates from its false ones, and the
    # same model was a coin flip (54.8%) on polarity — so the score sorts,
    # the neighbours inform, and neither decides.
    from .jgen_lexicon import annotate
    out = annotate(out, home)

    path.write_text(json.dumps(
        [v for v in existing.values() if isinstance(v, dict)],
        ensure_ascii=False, indent=2), encoding="utf-8")
    return out
