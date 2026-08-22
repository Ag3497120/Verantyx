"""Layered memory — the missing half of the matryoshka.

Two matryoshkas were described in the original conception and only one was
built. `matryoshka_consensus` is the PER-QUERY one: disagreement inside a
single inference is handed upward until it resolves or types out. This
module is the MEMORY one: "ある程度ノードの数が増えてきたら上に重ねて、
その上でノードを増やしていく" — when a layer's node count reaches capacity,
freeze it and stack a fresh layer on top; new knowledge lands in the top
layer from then on.

The same stacking answers two different needs at once, which is why it is
one mechanism and not two:

  - growth:    knowledge never stops being addable, but no single cross
               store grows without bound
  - alignment: "推論のたびに全ノードを整列される時に参照される" stays
               affordable, because each layer is consulted as a unit and a
               frozen layer's internal arrangement never changes again

Inference across layers is the extended inference of the conception: the
first layer concludes, its conclusion flows to the next layer, which
extends or revises, and so on. The open question the conception flags —
whether the ORIGINAL query rides along to later layers — is deliberately
not decided here. It is the same question `matryoshka_consensus` already
parameterises as CARRY_MODES (A: full query every layer, B: first layer
only, C: intent head only), so the modes are reused verbatim and the
answer stays an experiment, not an opinion baked into an engine.

Verdicts are typed, as everywhere:

  ANSWER            layers converged — two consecutive layers named the
                    same core (stability, the conception's halting idea)
  UNKNOWN_DRIFT     layers kept answering but never twice the same — the
                    telephone-game failure mode of carrying no query,
                    surfaced as a type instead of a wrong answer
  anything else     the last layer's own typed verdict, passed through
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .consensus import CARRY_MODES, carry_query
from .cross_store import CrossStore

#: Default per-layer capacity, in cores. Deliberately small enough that
#: stacking actually happens in practice; a starting point to tune from
#: real stores, not a measured constant.
DEFAULT_CAPACITY = 512


@dataclass
class LayeredMemory:
    """A stack of cross stores. Index 0 is the oldest (the first layer of
    the conception); the last element is the only one that accepts writes."""

    levels: List[CrossStore] = field(default_factory=lambda: [CrossStore()])
    capacity: int = DEFAULT_CAPACITY
    #: Multiresolution promotion: when a layer freezes, its `promote_k`
    #: highest-mass cores are distilled into short summary sentences and
    #: ingested into the NEW top layer. The pyramid this builds is what the
    #: coarse-to-fine idea needs: the active layer always carries a coarse
    #: memory of everything below it, so recent questions answer fast, and
    #: agreement between a promoted summary and its frozen original is
    #: vertical agreement — the sections' halting criterion turned 90°.
    #: Default 0 (off): promotion consumes capacity in the new layer and
    #: changes growth arithmetic, so it is opted into, never inherited.
    promote_k: int = 0

    # -- growth ------------------------------------------------------------

    @property
    def top(self) -> CrossStore:
        return self.levels[-1]

    def _distill(self, frozen: CrossStore) -> List[str]:
        """Summary sentences for the highest-mass cores of a freezing layer.
        Deliberately lossy — a coarse node is the point, not a copy. The
        frozen fine-grained original stays below, untouched, which is what
        makes coarse-vs-fine disagreement detectable later instead of the
        summary silently replacing the evidence."""
        cores = sorted(frozen.crosses.keys(),
                       key=lambda c: (-frozen.mass(c), c))[: self.promote_k]
        out = []
        for core in cores:
            facets = [f for f, _ in frozen.top_facets(core, k=3)]
            if facets:
                out.append(f"{core} is {' '.join(facets)}")
        return out

    def _maybe_stack(self) -> bool:
        if self.top.n_cores() >= self.capacity:
            frozen = self.top
            self.levels.append(CrossStore())
            if self.promote_k > 0:
                for sentence in self._distill(frozen):
                    self.top.ingest_sentence(sentence)
            return True
        return False

    def locate(self, core: str) -> Dict[str, Any]:
        """Where does a topic live? The typed answer to 'did the context
        fall out of the window' — which, here, can only ever be ACTIVE (top
        layer), FROZEN (a lower layer, intact and consultable), or ABSENT.
        There is no fourth state; silent truncation does not exist."""
        hits = [i for i, lvl in enumerate(self.levels) if lvl.has(core)]
        if not hits:
            return {"status": "ABSENT", "levels": []}
        top_idx = len(self.levels) - 1
        status = "ACTIVE" if top_idx in hits else "FROZEN"
        return {"status": status, "levels": hits,
                "frozen_levels": [i for i in hits if i != top_idx]}

    def ingest_sentence(self, text: str) -> Dict[str, Any]:
        """New knowledge goes to the top layer; a full top layer is frozen
        by stacking an empty one above it — never by evicting from it.
        Freezing is what keeps a lower layer's arrangement stable, which is
        the whole point of the stack."""
        stacked = self._maybe_stack()
        core = self.top.ingest_sentence(text)
        return {"core": core, "level": len(self.levels) - 1, "stacked": stacked}

    def n_levels(self) -> int:
        return len(self.levels)

    def total_cores(self) -> int:
        return sum(s.n_cores() for s in self.levels)

    # -- persistence -------------------------------------------------------

    def save(self, path: Path) -> None:
        base = Path(path)
        meta = {"capacity": self.capacity, "n_levels": len(self.levels),
                "promote_k": self.promote_k}
        base.write_text(json.dumps(meta, ensure_ascii=False))
        for i, level in enumerate(self.levels):
            level.save(base.with_suffix(f".L{i}.json"))

    @classmethod
    def load(cls, path: Path) -> "LayeredMemory":
        base = Path(path)
        if not base.is_file():
            return cls()
        meta = json.loads(base.read_text())
        levels = [
            CrossStore.load(base.with_suffix(f".L{i}.json"))
            for i in range(int(meta.get("n_levels", 1)))
        ]
        return cls(levels=levels or [CrossStore()],
                   capacity=int(meta.get("capacity", DEFAULT_CAPACITY)),
                   promote_k=int(meta.get("promote_k", 0)))


def layered_ask(
    memory: LayeredMemory,
    query: str,
    *,
    carry: str = "A",
    per_level_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extended inference across the stack, oldest layer first.

    Each layer runs the ordinary store consensus. Its answer tokens are
    appended to the next layer's query, so a later layer extends what an
    earlier one concluded rather than starting from nothing. What ELSE the
    next layer receives is the carry mode:

      A  original query + previous answer   (anchored extension)
      B  previous answer only               (pure hand-off — the arm that
                                             can drift, by design)
      C  intent head + previous answer      (anchored intent, decayed words)

    Halts early when two consecutive layers agree on a core — the
    conception's "stable and matching" criterion applied across layers.
    """
    if carry not in CARRY_MODES:
        raise ValueError(f"carry must be one of {CARRY_MODES}")
    from .consensus_store import consensus_over_store

    kwargs = per_level_kwargs or {}
    trace: List[Dict[str, Any]] = []
    prev_core: Optional[str] = None
    answer_tokens: List[str] = []
    last: Dict[str, Any] = {"verdict": "UNKNOWN_NO_EVIDENCE", "core": None, "text": ""}
    answered_cores: List[str] = []

    for i, level in enumerate(memory.levels):
        base = carry_query(query, carry, i)
        q = " ".join(t for t in ([base] + answer_tokens) if t).strip()
        if not q:
            # Mode B with an empty previous answer has literally nothing to
            # ask. Recording that beats inventing a query.
            trace.append({"level": i, "query": "", "skipped": "empty_query"})
            continue
        out = consensus_over_store(level, q, **kwargs)
        trace.append({"level": i, "query": q,
                      "verdict": out.get("verdict"),
                      "core": out.get("core"), "text": out.get("text", "")})
        last = out

        core = out.get("core")
        if out.get("verdict") == "ANSWER" and core:
            answered_cores.append(core)
            if prev_core is not None and core == prev_core:
                return {"verdict": "ANSWER", "core": core,
                        "text": out.get("text", ""),
                        "stable_at_level": i, "carry": carry, "trace": trace}
            prev_core = core
            answer_tokens = [t for t in str(out.get("text", "")).split() if t]
        # A typed UNKNOWN from one layer is information for the next, not a
        # stop: the conception's later layers exist to 付け足し・探索 what an
        # earlier layer could not settle. The previous answer (if any) still
        # rides forward.

    distinct = len(set(answered_cores))
    if distinct >= 2:
        # Every layer that answered named a different core and no two
        # consecutive ones agreed. That is not "an answer, roughly" — it is
        # the drift failure, and it gets its own type so the carry-mode
        # experiment can count it.
        return {"verdict": "UNKNOWN_DRIFT", "core": None, "text": "",
                "cores_seen": answered_cores, "carry": carry, "trace": trace}
    if distinct == 1:
        # One layer answered and no other layer confirmed or contradicted
        # it. Honest but weaker than stability; the single answer is
        # returned with where it came from.
        return {"verdict": "ANSWER", "core": answered_cores[0],
                "text": next(t["text"] for t in trace
                             if t.get("core") == answered_cores[0]),
                "stable_at_level": None, "carry": carry, "trace": trace}
    out = dict(last)
    out["carry"] = carry
    out["trace"] = trace
    return out
