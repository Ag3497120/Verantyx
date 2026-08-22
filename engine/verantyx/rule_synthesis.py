"""Derive a reading rule from a gap, then measure whether it breaks anything.

The loop was still open at the far end. A defect became a GapNode and a
person had to write the rule, which means the growth loop was one only its
authors could be in.

Two facts make the last step mechanical.

Every reading rule this engine has is the SAME SHAPE — a pattern matched
against the characters immediately after a polar term, where a match means
the term asserts nothing:

    _JA_UNTIL      ^(?:さ?れ|し)?る?まで
    _JA_DEEMING    ^[ぁ-ん]{0,8}(?:と|であると|でないと)?(認め|みなす|見なす)
    _JA_CAUSE_MARK ^(?:による|によって|により|に伴う|に因る|のため)

A shape that uniform is derivable from examples: the longest prefix the
reported frames share, anchored, is the candidate.

And a candidate can be MEASURED. Not for correctness — no procedure here can
decide whether 「〜の方向で」 really means a closure has not happened — but for
damage, against everything already known to be true. The engine carries 14
detections read and confirmed by a person across two corpora, a planted suite
with its own answer key, and whatever documents the operator points it at.

So the boundary this module draws, and will not cross:

    it can say     this pattern removes the reported false positives, and
                   nothing that was true before stopped being true
    it cannot say  this pattern is right

The second is a person's, and the proposal is written to make that judgement
cheap: the pattern, what it suppresses, what it left alone, and the count of
true findings before and after. A rule that survives is a candidate. A rule
that costs one confirmed detection is rejected here and never reaches them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: A derived pattern shorter than this matches too much to be a rule. 「る」
#: after a polar term is most of Japanese; 「るまで」 is a rule.
MIN_PATTERN = 2
#: And one longer than this has stopped being grammar and started being a
#: sentence — it would only ever match the document it came from.
MAX_PATTERN = 10

#: Whether the character after the shared prefix continues a word. If every
#: tail turns to kana or punctuation there, the prefix ended on a boundary and
#: the run before it is grammar rather than a truncated noun.
_JA_CONTENT_CONT = re.compile(r"[㐀-䶿一-鿿ァ-ヺ]")


@dataclass
class Candidate:
    pattern: str
    provenance: str
    #: The frames it was derived from, which are already redacted.
    from_frames: List[str] = field(default_factory=list)
    tails: List[str] = field(default_factory=list)


def _tail_after(sentence: str, term: str) -> str:
    from .defect_report import _ATTRIBUTION

    src = _ATTRIBUTION.sub("", sentence or "")
    at = src.find(term)
    return "" if at < 0 else src[at + len(term):]


def _common_prefix(tails: List[str]) -> str:
    if not tails:
        return ""
    head = tails[0]
    for t in tails[1:]:
        i = 0
        while i < min(len(head), len(t)) and head[i] == t[i]:
            i += 1
        head = head[:i]
        if not head:
            return ""
    return head


def derive(sentences: List[str], term: str, *, provenance: str = ""
           ) -> Optional[Candidate]:
    """The longest anchored prefix the reported tails share.

    Deliberately the simplest thing that could work. A cleverer generaliser —
    one that guessed 「〜する|される」 from two examples — would be inventing a
    rule from evidence it does not have, which is how the three too-wide
    guards in `polarity` got that way.
    """
    tails = [t for t in (_tail_after(s, term) for s in sentences) if t]
    if len(tails) < 2:
        return None
    shared = _common_prefix(tails)[:MAX_PATTERN]
    # Only a content word left DANGLING at the end is the document rather than
    # the grammar. A first attempt cut at the first content run anywhere, and
    # threw away 「の方向で」 — where 方向 is part of the construction, not the
    # noun the sentence is about. What marks the document is a run that the
    # shared prefix ends inside or on, because that is where the sentences
    # stopped agreeing.
    from .lang import ja_content_runs

    while shared:
        runs = ja_content_runs(shared)
        if not runs:
            break
        last = runs[-1]
        if not shared.endswith(last):
            break
        # A run the tails carried on past is grammar; one the prefix ends on
        # only survived because the divergence happened to fall after it.
        longer = [t for t in tails if len(t) > len(shared)]
        if longer and all(not _JA_CONTENT_CONT.match(t[len(shared):])
                          for t in longer):
            break
        shared = shared[:-len(last)]
    if len(shared) < MIN_PATTERN:
        return None
    return Candidate(pattern="^" + re.escape(shared), provenance=provenance,
                     tails=tails)


@dataclass
class Verdict:
    """What measuring the candidate showed. Never whether it is right."""

    accepted: bool
    reason: str
    fixed: List[str] = field(default_factory=list)     # reports it silences
    lost: List[str] = field(default_factory=list)      # true findings it costs
    before: Dict[str, int] = field(default_factory=dict)
    after: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in ([], {}, "")}


def _detections(paths: List[str]) -> List[Tuple[str, str]]:
    from .corpus_audit import audit_paths

    a = audit_paths(paths)
    return sorted((d.topic, d.aspect) for d in a.detections)


def _planted_holds() -> bool:
    """The planted suite still passes. It has an answer key, so it is the one
    place a rule can be shown to have broken something outright."""
    import io
    import contextlib

    from .generalization_eval import main as _gen

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _gen()
    return code == 0


def verify(candidate: Candidate, *, corpora: List[str],
           should_silence: List[Tuple[str, str]]) -> Verdict:
    """Apply the candidate, re-measure everything, and put it back.

    `should_silence` is what the reports said was wrong — (topic, aspect)
    pairs that ought to disappear. Everything else that disappears is damage.
    """
    from . import ja_grammar as grammar

    before = {p: _detections([p]) for p in corpora}
    entry = (candidate.pattern, candidate.provenance)
    grammar.SUPPRESSIONS.append(entry)
    try:
        planted = _planted_holds()
        after = {p: _detections([p]) for p in corpora}
    finally:
        if entry in grammar.SUPPRESSIONS:
            grammar.SUPPRESSIONS.remove(entry)

    gone: List[str] = []
    for p in corpora:
        for hit in before[p]:
            if hit not in after[p]:
                gone.append(f"{hit[0]} / {hit[1]}")
    appeared: List[str] = []
    for p in corpora:
        for hit in after[p]:
            if hit not in before[p]:
                appeared.append(f"{hit[0]} / {hit[1]}")

    wanted = {f"{t} / {a}" for t, a in should_silence}
    fixed = [g for g in gone if g in wanted]
    lost = [g for g in gone if g not in wanted]

    counts_before = {p: len(before[p]) for p in corpora}
    counts_after = {p: len(after[p]) for p in corpora}

    if not planted:
        return Verdict(False, "the planted suite stopped passing", fixed, lost,
                       counts_before, counts_after)
    if lost:
        return Verdict(False,
                       f"it costs {len(lost)} finding(s) that were confirmed "
                       f"true: {', '.join(lost)}",
                       fixed, lost, counts_before, counts_after)
    if appeared:
        return Verdict(False,
                       f"it introduces {len(appeared)} finding(s) that were "
                       f"not there: {', '.join(appeared)}",
                       fixed, lost, counts_before, counts_after)
    if not fixed:
        return Verdict(False, "it changes nothing the reports complained about",
                       fixed, lost, counts_before, counts_after)
    return Verdict(True,
                   f"it silences {len(fixed)} reported finding(s) and costs "
                   f"nothing measured",
                   fixed, lost, counts_before, counts_after)


def propose(candidate: Candidate, verdict: Verdict) -> Dict[str, Any]:
    """What a person is asked to accept — and what they still have to decide."""
    return {
        "overlay": {"suppressions": [[candidate.pattern,
                                      candidate.provenance]]},
        "measured": verdict.as_dict(),
        "still_yours_to_decide": (
            "Measurement shows this pattern breaks nothing already confirmed. "
            "It cannot show that the pattern is RIGHT — that the grammar it "
            "matches really does mean the state has not occurred. Read the "
            "pattern against a sentence where the state HAS occurred and "
            "confirm it does not match that too."
        ),
    }
