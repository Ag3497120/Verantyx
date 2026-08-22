"""Conversation context as space, not as a window.

An LLM's context is a POSITION window: when it overflows, the oldest tokens
are dropped, silently, and the model cannot tell it happened. Here a turn is
ingested into the cross store — it becomes a node in space, retrieved by
relevance rather than by recency, and it never falls out of a window because
there is no window. Overflow, if it happens at all, is a LAYER freezing
(the fact is still there, in a lower layer, consultable and typed as FROZEN),
or gravity decay (a policy, not an accident). `LayeredMemory.locate` gives
the typed answer to "is that still in context": ACTIVE / FROZEN / ABSENT,
never a silent nothing.

What this DOES capture: the factual content of a conversation, addressably.
What it does NOT, stated plainly because the boundary matters: linguistic
continuity — resolving "it" or "that" across turns, tense, discourse flow.
That is the generator's job (JGEN's window), and pretending the cross store
carries it would be the same category error as injecting a final-layer
vector into a middle layer. The store carries what was SAID as retrievable
facts; the language cortex carries how it hangs together.

A turn is tagged with speaker and turn index so recall can say who said a
thing and when, and so a later "what did I ask about X" is answerable
without scanning. The store already keeps per-facet provenance
(track_provenance) — this rides on it rather than inventing a parallel log.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .cross_store import CrossStore
from .layer_stack import LayeredMemory

#: Turn text longer than this is summarised to its content clause before
#: ingest — a turn is a fact source, not a transcript, and pouring an essay
#: as one node buries its cores under furniture (the placement-granularity
#: finding: coarse pouring loses facet links).
_MAX_TURN_CHARS = 400
#: Japanese writes 。 with no trailing space, so a splitter that requires
#: whitespace treated a whole Japanese turn as one sentence. The document
#: path learned this and this path did not — the same defect, in the module
#: whose entire job is remembering what was said.
#: A period BETWEEN alphanumerics is a decimal point, not a sentence end.
#:
#: Measured 2026-08-17 while building the operator's clone: the turn
#: 「…もしcpu経路だったらqwen3.8は捨てる。」 split into 「…qwen3.」 and
#: 「8は捨てる。」, so the cores became ['gpu', '捨'] and `locate('qwen3.8')`
#: answered ABSENT about a rule the operator had just stated three times.
#: ABSENT is the one verdict this module must never get wrong.
#:
#: It is not one identifier: every version-bearing name breaks the same way —
#: qwen3.8, gemma-4.1, v1.2, python3.11 — and neither half is the name. The
#: document path already avoided this with `_rejoin_abbreviations`; the
#: conversation path had no equivalent.
#:
#: The rule is narrow on purpose. A real sentence-ending period is followed
#: by whitespace or the end of the text, never by a digit, so requiring a
#: non-alphanumeric on the right costs nothing and fixes the whole class.
_SENT_SPLIT = re.compile(r"(?<=[.!?])(?![0-9A-Za-z])\s*|(?<=[。！？])\s*")


@dataclass
class Turn:
    speaker: str            # "user" | "assistant" | any stable label
    text: str
    index: int
    cores: List[str] = field(default_factory=list)


@dataclass
class Conversation:
    """A layered memory that turns are poured into, plus the turn log needed
    to answer speaker/time questions the store's core index cannot."""

    memory: LayeredMemory = field(default_factory=lambda: LayeredMemory(capacity=512))
    turns: List[Turn] = field(default_factory=list)

    def add_turn(self, speaker: str, text: str) -> Turn:
        """Ingest one utterance. Each sentence of it becomes (or reinforces)
        a node; the turn records which cores it touched so 'what did the user
        ask about' is a lookup, not a scan."""
        idx = len(self.turns)
        turn = Turn(speaker=speaker, text=text, index=idx)
        for sentence in self._sentences(text):
            tagged = f"{sentence} (said by {speaker} in turn {idx})"
            out = self._ingest(tagged, detect_on=sentence)
            core = out.get("core")
            if core and core not in turn.cores:
                turn.cores.append(core)
        self.turns.append(turn)
        return turn

    def _ingest(self, tagged: str, *, detect_on: str) -> Dict[str, Any]:
        """Route by script, exactly as the document path does.

        `LayeredMemory.ingest_sentence` goes straight to the English
        decomposer, whose word pattern is `[A-Za-z0-9']+`. A Japanese turn
        therefore produced ONE core — the entire sentence — so
        「避難所は本町に開設されました」 was stored under itself, and
        `locate('避難所')` answered ABSENT about a topic the conversation had
        just discussed. ABSENT is the one verdict this module must never get
        wrong: it is the answer to "did we talk about that", and a false
        ABSENT is the silent context loss the whole design exists to prevent.
        Detection runs on the UNTAGGED sentence for the reason the document
        path found: the Latin in "(said by … in turn 3)" outvotes a short
        Japanese utterance.
        """
        from .lang import detect, ja_ingest_sentence

        lang = detect(detect_on)
        stacked = self.memory._maybe_stack()
        if lang in ("ja", "zh"):
            core = ja_ingest_sentence(self.memory.top, tagged)
        else:
            core = self.memory.top.ingest_sentence(tagged)
        return {"core": core, "level": len(self.memory.levels) - 1,
                "stacked": stacked}

    def _sentences(self, text: str) -> List[str]:
        t = (text or "").strip()
        if not t:
            return []
        if len(t) <= _MAX_TURN_CHARS:
            return [s for s in _SENT_SPLIT.split(t) if s.strip()]
        # Over budget: keep the first two sentences (the turn's own topic
        # sentence and its elaboration), drop the tail. Lossy on purpose —
        # the alternative is one giant node that answers nothing.
        parts = [s for s in _SENT_SPLIT.split(t) if s.strip()]
        return parts[:2] if parts else [t[:_MAX_TURN_CHARS]]

    def locate(self, topic: str) -> Dict[str, Any]:
        """Is this topic still 'in context'? Typed, never silent.

        ACTIVE  — in the top (writable) layer
        FROZEN  — pushed to a lower layer by overflow; intact, consultable
        ABSENT  — never discussed

        The distinction an LLM cannot make: FROZEN is not lost. 'We talked
        about it earlier, it is in layer 2' is a true, actionable answer;
        an LLM whose window rolled past it can only fail to mention it.
        """
        loc = self.memory.locate(topic)
        # Enrich with who/when from the turn log, if the topic was discussed.
        mentions = [
            {"turn": t.index, "speaker": t.speaker}
            for t in self.turns if topic in t.cores
        ]
        # The turn log is the fallback the core index cannot give. Measured
        # twice on 2026-08-18 while seeding the operator's clone: 事前登録
        # was stored as a FACET of core 測定, and muse-glimmer sat inside a
        # turn whose core was something else — both answered ABSENT about
        # rules the operator had just stated. ABSENT is the one verdict this
        # module must never get wrong, and a verbatim substring of a turn's
        # own text is exact evidence of mention, not a guess.
        if not mentions:
            for t in self.turns:
                if topic and topic in t.text:
                    mentions.append({"turn": t.index, "speaker": t.speaker,
                                     "via": "turn_text"})
        if mentions and loc.get("state") == "ABSENT":
            loc["state"] = "ACTIVE"
            loc["via"] = "turn_text"
        loc["mentions"] = mentions
        return loc

    def recall(self, query: str, *, carry: str = "A") -> Dict[str, Any]:
        """Answer from the conversation's own memory, across all layers.

        Routed by script, like ingestion. `layered_ask` runs the English
        consensus decomposer at every level, so a Japanese query returned
        UNKNOWN_NO_EVIDENCE about a core that was sitting in the store —
        while `locate()` on the same word answered ACTIVE. Two APIs
        disagreeing about the same memory is worse than either being wrong
        alone: the caller has no way to tell which one to believe, and the
        typed verdict this module exists to provide stops meaning anything.
        """
        from .lang import detect, ja_ask
        from .layer_stack import layered_ask

        if detect(query) in ("ja", "zh"):
            return self._recall_ja(query)
        out = layered_ask(self.memory, query, carry=carry)
        # Attach where the answer's topic lives — the context-status the
        # caller usually wants alongside the answer itself.
        if out.get("core"):
            out["location"] = self.locate(out["core"])
        return out

    def _recall_ja(self, query: str) -> Dict[str, Any]:
        """Walk the stack newest-first and report WHICH layer answered.

        Newest first because a conversation's later turns supersede its
        earlier ones, and the layer index is returned so a caller can see
        whether the answer came from live context or from a frozen layer —
        the distinction FROZEN exists to draw.
        """
        from .lang import ja_ask

        trace: List[Dict[str, Any]] = []
        for level in range(len(self.memory.levels) - 1, -1, -1):
            out = dict(ja_ask(self.memory.levels[level], query))
            trace.append({"level": level, "verdict": out.get("verdict"),
                          "core": out.get("core")})
            if out.get("verdict") == "ANSWER":
                out["level"] = level
                out["frozen"] = level < len(self.memory.levels) - 1
                out["trace"] = trace
                if out.get("core"):
                    out["location"] = self.locate(out["core"])
                return out
        return {"verdict": "UNKNOWN_NO_EVIDENCE", "core": None, "text": "",
                "reason": "no_candidate_cross", "trace": trace,
                "location": self.locate(query)}

    def stats(self) -> Dict[str, Any]:
        return {
            "turns": len(self.turns),
            "levels": self.memory.n_levels(),
            "total_cores": self.memory.total_cores(),
            "speakers": sorted({t.speaker for t in self.turns}),
        }
