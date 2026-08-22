"""Growth-signal log — Vera's own record of where it keeps failing or drifting.

Milestone M's self-growth loop needs a structural, non-LLM signal for "this
might be worth a new deterministic module" instead of syncing to any single
caller (chat turn, IDE UI-automation, etc). Two signals are tracked, both
sourced from things Vera already computes on every normal `route()` call:

  1. Recurring typed UNKNOWN verdicts, bucketed by a light query
     normalization — the same shape of question failing repeatedly is
     stronger evidence than one-off gaps.
  2. `CrossStore.mass()` drift between heartbeats — a proxy for "the
     knowledge structure reorganized" since there is no time-decay
     mechanism in `cross_store.py` (unlike the IDE's EternalMemoryStore)
     to read that from directly.

Persisted next to the fact store (same directory as `VeraConfig.store`),
never inside `vera_store.json` itself — this is meta-signal, not a fact.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cross_store import CrossStore

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "what", "which", "who", "how", "why", "of", "to", "in", "on", "for",
})


def normalize_query(query: str) -> str:
    """Light, deterministic normalization so paraphrases of the same
    question cluster into one bucket. Not full NLP — matches the honesty
    already documented in en_decompose.py: rough heuristics, not fluent."""
    words = re.findall(r"[a-zA-Z0-9぀-ヿ一-鿿]+", query.lower())
    kept = [w for w in words if w not in _STOPWORDS]
    return " ".join(kept) or query.strip().lower()


@dataclass
class UnknownBucket:
    normalized: str
    verdict_counts: Dict[str, int] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    first_seen: float = 0.0
    last_seen: float = 0.0
    matched_domain_count: int = 0  # times some domain module claimed the
    # query (a real "route" was set) but still returned a typed UNKNOWN —
    # distinct from "no domain even recognized the shape". Without this,
    # boundary.classify cannot tell a Kripke "known formula, unregistered
    # proposition" gap (needs_more_facts) from a genuinely new domain
    # shape (growth_candidate) when both surface as UNKNOWN_NO_EVIDENCE.

    def record(self, raw_query: str, verdict: str, matched_domain: bool = False) -> None:
        self.verdict_counts[verdict] = self.verdict_counts.get(verdict, 0) + 1
        if matched_domain:
            self.matched_domain_count += 1
        if raw_query not in self.examples and len(self.examples) < 8:
            self.examples.append(raw_query)
        now = time.time()
        if not self.first_seen:
            self.first_seen = now
        self.last_seen = now

    def total(self) -> int:
        return sum(self.verdict_counts.values())

    def dominant_verdict(self) -> str:
        return max(self.verdict_counts, key=self.verdict_counts.get)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "normalized": self.normalized,
            "verdict_counts": self.verdict_counts,
            "examples": self.examples,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "matched_domain_count": self.matched_domain_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UnknownBucket":
        return cls(
            normalized=d["normalized"],
            verdict_counts=dict(d.get("verdict_counts", {})),
            examples=list(d.get("examples", [])),
            first_seen=d.get("first_seen", 0.0),
            last_seen=d.get("last_seen", 0.0),
            matched_domain_count=d.get("matched_domain_count", 0),
        )


class GrowthSignals:
    def __init__(self) -> None:
        self.buckets: Dict[str, UnknownBucket] = {}
        self.mass_snapshot: Dict[str, float] = {}
        self.drifted_cores: Dict[str, float] = {}  # core -> last observed |delta|
        #: Refusals handed to an action branch, and what the branch did.
        #: Append-only, beside the buckets — never instead of them.
        self.branch_outcomes: List[Dict[str, Any]] = []

    def record_unknown(self, query: str, verdict: str, matched_domain: bool = False) -> UnknownBucket:
        key = normalize_query(query)
        bucket = self.buckets.setdefault(key, UnknownBucket(normalized=key))
        bucket.record(query, verdict, matched_domain=matched_domain)
        return bucket

    def record_branch_outcome(self, query: str, verdict: str, branch: str,
                              resolved: bool) -> None:
        """A refusal was handed to an action branch; this is what happened.

        The refusal's bucket is deliberately NOT touched: a refusal that
        an agent auto-resolved is a success, not a refusal that never
        happened, and a ledger that loses auto-resolved entries tells the
        same shape of lie as an ingest that hides its failures. `resolved`
        should come from the one honest oracle — re-asking after the
        branch and the store now answering — not from the agent's say-so.
        """
        import time

        self.branch_outcomes.append({
            "query": normalize_query(query), "verdict": verdict,
            "branch": branch, "resolved": bool(resolved),
            "at": round(time.time(), 2)})

    def record_mass_snapshot(self, store: CrossStore, drift_threshold: float = 0.4) -> List[str]:
        """Compares each core's current `mass()` against the last snapshot;
        returns cores whose relative change exceeds `drift_threshold`
        (e.g. 0.4 = 40% up or down since the last heartbeat)."""
        drifted: List[str] = []
        for core in store.crosses:
            new_mass = store.mass(core)
            old_mass = self.mass_snapshot.get(core)
            if old_mass is not None and old_mass > 0:
                rel_delta = abs(new_mass - old_mass) / old_mass
                if rel_delta >= drift_threshold:
                    drifted.append(core)
                    self.drifted_cores[core] = rel_delta
            self.mass_snapshot[core] = new_mass
        return drifted

    def save(self, path: Path) -> None:
        data = {
            "buckets": {k: b.as_dict() for k, b in self.buckets.items()},
            "mass_snapshot": self.mass_snapshot,
            "drifted_cores": self.drifted_cores,
            "branch_outcomes": self.branch_outcomes,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: Path) -> "GrowthSignals":
        gs = cls()
        if not path.is_file():
            return gs
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return gs
        gs.buckets = {
            k: UnknownBucket.from_dict(v) for k, v in data.get("buckets", {}).items()
        }
        gs.mass_snapshot = dict(data.get("mass_snapshot", {}))
        gs.drifted_cores = dict(data.get("drifted_cores", {}))
        gs.branch_outcomes = list(data.get("branch_outcomes", []))
        return gs


def growth_signals_path(store_path: Path) -> Path:
    return store_path.parent / "growth_signals.json"
