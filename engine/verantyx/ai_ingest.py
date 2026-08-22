"""AI-output ingestion — passive memory from an assistant's final text,
quarantined until a human reviews it.

Design covenant this module must not break: Vera never presents an
unverified claim as a fact. An LLM's own output (even its *final*, non-
thinking text) can be wrong, hedged, or exploratory — remembering it
directly into the trusted store would launder hallucination into
"verified, counted" memory, which is the one failure mode this whole
project exists to prevent.

So this module never writes into the main store. It only proposes
candidate sentences into a separate ``AiFactQuarantine`` — a holding area a
human (or the user, via ``vera review-ai-facts``) must explicitly accept
before anything reaches the trusted ``CrossStore``. Filters:

  - thinking/chain-of-thought text is out of scope by construction: callers
    must pass only an assistant's final visible reply, never a <thinking>
    block — this module has no signature that accepts one.
  - hedge-word sentences ("might", "probably", "I think", "seems", …) are
    dropped before they even reach quarantine — a sentence the model
    itself is unsure of should not become a fact candidate at all.
  - meta-commentary about the assistant's own process ("let me check",
    "I'll now run", "as an AI") is dropped — it is not world knowledge.
  - questions/imperatives/task-labeled text reuse ``lang.is_question`` —
    the same gate that stops "tell me something" from self-polluting chat.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .en_decompose import split_sentences
from .lang import is_question

_HEDGE_WORDS = {
    "might", "may", "maybe", "perhaps", "possibly", "probably", "likely",
    "unlikely", "seems", "seem", "appears", "appear", "presumably",
    "arguably", "supposedly", "allegedly", "guess", "guessing", "unsure",
    "unclear", "uncertain", "assume", "assuming", "suspect", "roughly",
    "approximately", "i think", "i believe", "i suspect", "i assume",
    "i'd guess", "not sure", "could be", "might be", "may be",
}

_META_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"^(let me|i'll|i will|i'm going to|i am going to)\b",
        r"^(now|next|first|then)\s+i\s*(will|'ll)\b",
        r"\bas an ai\b",
        r"^(checking|running|looking|searching|verifying)\b",
        r"^(here'?s|here is)\b",
    )
]


def _has_hedge(sentence: str) -> bool:
    s = sentence.casefold()
    return any(h in s for h in _HEDGE_WORDS)


def _is_meta(sentence: str) -> bool:
    return any(p.search(sentence) for p in _META_PATTERNS)


def candidate_sentences(final_text: str) -> List[str]:
    """Split an assistant's FINAL (non-thinking) reply into sentence-level
    fact candidates, dropping hedged, meta, and question/task sentences.

    Caller's responsibility: ``final_text`` must be the model's confirmed
    output, never a thinking/chain-of-thought block — this function has no
    way to tell the difference, so passing thinking text here defeats the
    whole point of the quarantine design.
    """
    out: List[str] = []
    for sent in split_sentences(final_text or ""):
        s = sent.strip()
        if not s or len(s) < 8:
            continue
        if is_question(s):
            continue
        if _has_hedge(s):
            continue
        if _is_meta(s):
            continue
        out.append(s)
    return out


@dataclass
class QuarantineEntry:
    text: str
    source: str
    ts: float
    status: str = "pending"  # pending | accepted | rejected

    def as_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "source": self.source, "ts": self.ts,
                "status": self.status}


@dataclass
class AiFactQuarantine:
    """Holding area for AI-proposed facts. Nothing here is queryable via
    ``ask`` until a human accepts it — quarantine is a separate file from
    the trusted CrossStore, by design, so the two can never be confused."""

    entries: List[QuarantineEntry] = field(default_factory=list)

    def propose(self, final_text: str, *, source: str) -> List[QuarantineEntry]:
        added = [
            QuarantineEntry(text=s, source=source, ts=round(time.time(), 2))
            for s in candidate_sentences(final_text)
        ]
        self.entries.extend(added)
        return added

    def propose_raw(self, text: str, *, source: str) -> QuarantineEntry:
        """Milestone O: for raw fetched evidence (a gap-resolution web
        excerpt), not a conversational reply. `propose()`'s
        candidate_sentences() is tuned for filtering an LLM's spoken
        answer (hedge words, meta-commentary, question sentences) --
        confirmed directly that running a real Wikipedia excerpt through
        it produced ZERO surviving candidates, silently dropping the
        evidence entirely. This adds exactly one entry, verbatim, so a
        human reviewer sees the actual retrieved text to accept/reject as
        a whole rather than losing it to filters meant for a different
        kind of input."""
        entry = QuarantineEntry(text=text, source=source, ts=round(time.time(), 2))
        self.entries.append(entry)
        return entry

    def pending(self) -> List[QuarantineEntry]:
        return [e for e in self.entries if e.status == "pending"]

    def accept(self, entry: QuarantineEntry, store) -> Optional[str]:
        """Ingest one pending entry into the trusted store. Operates on the
        entry object directly (not a list position) — positional indices
        into ``pending()`` shift as entries resolve, which is a classic
        source of off-by-one bugs in review loops. Identity check (``is``),
        not ``==``, since two proposals can share identical field values."""
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return None
        key = store.ingest_sentence(entry.text)
        entry.status = "accepted"
        return key

    def reject(self, entry: QuarantineEntry) -> bool:
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return False
        entry.status = "rejected"
        return True

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps([e.as_dict() for e in self.entries], ensure_ascii=False)
        )

    @classmethod
    def load(cls, path: Path) -> "AiFactQuarantine":
        p = Path(path)
        if not p.is_file():
            return cls()
        data = json.loads(p.read_text())
        return cls(entries=[
            QuarantineEntry(d["text"], d["source"], d["ts"], d.get("status", "pending"))
            for d in data
        ])
