"""Report a defect without sending the document.

Five genres have been read blind so far and every one found defects — three
per genre, and the rate is not falling. That is not a bug in the engine; it is
the shape of the problem. A reading rule is a fact about a language and a
layout, and there are more layouts than anyone can enumerate in advance.

So the release has to assume defects keep arriving, which means the people who
find them must be able to report them. And the documents they find them in are
municipal drafts, hospital lists, evacuee registers — the reason the audit tool
never sends a file anywhere in the first place.

The way out is an observation about the defects themselves. Every one found so
far is a GRAMMATICAL SHAPE, not a fact about any document:

    〜されるまで        the state is the end of a period, so it has not arrived
    ◻又は◻は           a conjunction head swallowed into the preceding noun
    〜であると認める      a statute defining a category, not asserting one
    ◻しておりましたが、◻  an adversative, where the later clause is current
    【７月 30 日～】     a date the layout split, leaving 日 as a topic

None of those needs the noun. So a report keeps the function words, the
punctuation and the polar term — which is public vocabulary, shipped in
ja_grammar.json — and redacts every content word to ◻.

What that guarantees, stated as the property rather than as an intention:
a content run cannot survive redaction, so a place name, a person's name, a
facility, a number of households and a case count cannot appear in a report.
`audit_redaction` re-checks the output against the input and refuses to emit
a report that still contains any of them.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

REDACTED = "◻"

#: Digits are redacted too. A grammatical shape never needs the number, and a
#: household count, a case count or a phone number is exactly the kind of
#: thing that identifies a document.
_DIGITS = re.compile(r"[0-9０-９]+")
_LATIN = re.compile(r"[A-Za-z]{2,}")
_COLLAPSE = re.compile(REDACTED + r"{2,}")

#: The attribution suffix ingestion appends. A file name is not content, but
#: it is very often a place — 「宇城市.pdf」, 「八代_避難所名簿.xlsx」 — and the
#: shape of a defect never needs to know which document it came from. Removed
#: whole rather than redacted, so a report does not carry an empty bracket
#: that invites someone to wonder what was in it.
_ATTRIBUTION = re.compile(r"\s*[（(]\s*(?:reported by|said by)[^）)]*[）)]\s*$")


def _polar_vocabulary() -> set:
    from .ja_grammar import ALIASES, ASPECT_OF

    return set(ASPECT_OF) | set(ALIASES)


def skeleton(sentence: str, keep: Optional[set] = None) -> str:
    """The grammatical shape, with every content word replaced by ◻.

    `keep` defaults to the polar vocabulary, which is public data. Anything
    else — nouns, names, numbers, Latin words — goes.
    """
    kept = keep if keep is not None else _polar_vocabulary()
    from .lang import ja_content_runs

    out = _ATTRIBUTION.sub("", sentence or "")
    runs = sorted(set(ja_content_runs(out)), key=len, reverse=True)
    for run in runs:
        if run in kept:
            continue
        out = out.replace(run, REDACTED)
    out = _LATIN.sub(REDACTED, out)
    out = _DIGITS.sub(REDACTED, out)
    return _COLLAPSE.sub(REDACTED, out).strip()


def leaks(sentence: str, report: str, keep: Optional[set] = None) -> List[str]:
    """Anything from the source that survived into the report.

    Checked rather than assumed. The redaction is a claim about privacy, and
    a claim about privacy that is not tested is a hope.
    """
    kept = keep if keep is not None else _polar_vocabulary()
    from .lang import ja_content_runs

    source = _ATTRIBUTION.sub("", sentence or "")
    out = []
    for run in set(ja_content_runs(source)):
        if run in kept:
            continue
        if run in report:
            out.append(run)
    for m in _LATIN.finditer(source):
        if m.group(0) in report:
            out.append(m.group(0))
    for m in _DIGITS.finditer(source):
        if m.group(0) in report:
            out.append(m.group(0))
    return sorted(set(out))


#: The engine's OWN rules, as the aggregation key.
#:
#: Two earlier attempts to key on the text failed for the same reason: a fixed
#: window and a cut-at-the-first-noun both split one defect into three keys,
#: because 「閉鎖されるまでの間で」 and 「閉鎖されるまで利用できます」 differ in
#: what comes after the grammar — and what comes after the grammar is exactly
#: the part that is not the defect.
#:
#: What makes two reports the same defect is not that their text matches. It
#: is that the same RULE decided them, and the rules are already named in
#: `polarity`. Keying on which ones fire needs no window at all, and it lands
#: the report where a fix would go.
_RULE_NAMES = (
    ("until", "_JA_UNTIL"),
    ("deeming", "_JA_DEEMING"),
    ("negation", "_JA_NEG_AFTER"),
    ("cell_value", "_JA_CELL_VALUE"),
    ("cause", "_JA_CAUSE_MARK"),
)


def rules_fired(sentence: str, term: str) -> List[str]:
    """Which of the engine's guards see this term's frame, by name."""
    from . import polarity as _p

    src = _ATTRIBUTION.sub("", sentence or "")
    at = src.find(term)
    if at < 0:
        # A contradiction's evidence is TWO sentences and only one of them
        # holds the reported term; the other is the side it disagrees with.
        # Returning "none" for that one invented a second, empty key for
        # every report — an aggregation key that means "this sentence is not
        # about the defect" is worse than no key.
        return []
    tail = src[at + len(term):]
    out = []
    for label, attr in _RULE_NAMES:
        rx = getattr(_p, attr, None)
        if rx is not None and rx.match(tail):
            out.append(label)
    if not out:
        out.append("none")
    return out


def frame(sentence: str, term: str) -> str:
    """The aggregation key: the term's pole plus the rules that fired on it.

    Carries no text from the document at all — a rule name is this
    repository's own vocabulary — so it is safe to send even where the
    redacted skeleton would make somebody hesitate.
    """
    from .ja_grammar import ALIASES, ASPECT_OF

    fired = rules_fired(sentence, term)
    if not fired:
        return ""
    canonical = ALIASES.get(term, term)
    hit = ASPECT_OF.get(canonical)
    pole = f"{hit[0]}{hit[1]}" if hit else "?"
    return f"{pole} + {'+'.join(fired)}"


@dataclass
class Defect:
    """One reportable shape. No document, no identity, no counts."""

    kind: str                      # "false_positive" | "false_negative"
    aspect: str = ""               # the opposition, e.g. 開設
    value: str = ""                # the pole read, e.g. 閉鎖
    shapes: List[str] = field(default_factory=list)   # redacted sentences
    #: The aggregation key — what makes two reports the same defect.
    frames: List[str] = field(default_factory=list)
    note: str = ""                 # free text the reporter chooses to add
    engine: str = ""
    #: Corpus statistics carry no content and make a report actionable —
    #: a defect at 40% coverage is a different problem from one at 95%.
    coverage: Optional[float] = None
    corpus_kind: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in ("", None, [])}


def build(kind: str, sentences: List[str], *, aspect: str = "", value: str = "",
          note: str = "", coverage: Optional[float] = None,
          corpus_kind: str = "") -> Defect:
    """Turn evidence into a report, refusing if anything survives redaction."""
    shapes = []
    for s in sentences:
        shape = skeleton(s)
        found = leaks(s, shape)
        if found:
            raise ValueError(
                "redaction failed; refusing to build a report that still "
                f"contains: {', '.join(found)}"
            )
        if shape and shape not in shapes:
            shapes.append(shape)
    frames = []
    if value:
        term = value.replace("not_", "")
        for s in sentences:
            f = frame(s, term)
            if f and f not in frames:
                frames.append(f)
    return Defect(kind=kind, aspect=aspect, value=value, shapes=shapes,
                  frames=frames,
                  note=note.strip()[:400],
                  coverage=round(coverage, 3) if coverage is not None else None,
                  corpus_kind=corpus_kind)


def render(defect: Defect) -> str:
    """The text a reporter pastes into an issue. Human-readable on purpose:
    a report nobody can read before sending is a report nobody sends."""
    d = defect.as_dict()
    head = ("Vera defect report — no document content is included.\n"
            "Every content word is redacted to ◻; the polar term is public "
            "vocabulary from ja_grammar.json.\n")
    return head + json.dumps(d, ensure_ascii=False, indent=2)
