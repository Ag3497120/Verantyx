"""Milestone R3 — the minimal log this session agreed to build first:
did a structurally-matched resolution actually work when reused on a
different gap?

Nothing today records this. structural_similarity.py can say "this gap
looks like that one, and that one was resolved" (SKILL_REUSE_CANDIDATE),
but once a human/agent actually tries the suggested resolution, the
outcome vanishes -- there's no way to look back later and ask "does
matching on these dimensions actually predict a successful transfer, or
doesn't it?" Without that history, an accumulating pile of unresolved
gaps only ever reads as "not enough knowledge yet" (a level-1 problem),
even when the real cause is that structural_similarity's fixed 7
dimensions genuinely don't explain what's failing (a level-3 problem --
the comparison SHAPE itself, not its vocabulary, is insufficient).

This module deliberately does ONLY the recording. No calibration
analysis, no automatic type/schema proposals -- those need real
accumulated data to be anything but a guess, and were explicitly agreed
to be a later step once this log has something in it. Same "record
first, judge later" discipline as InterventionRecord (Milestone P5):
`success` starts unset; it's filled in either by a human/agent that
observed the real result, or deterministically inferred later from the
target gap's own status (see infer_missing_outcomes below) -- never
guessed by this module itself.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .gap_graph import BLOCKED_STATUSES, GapGraph
from .structural_similarity import StructuralMatch


@dataclass
class TransferOutcome:
    outcome_id: str
    source_gap_id: str          # the gap whose resolution was reused
    target_gap_id: str          # the gap it was tried on
    match_level: str            # StructuralMatch.level at the time of the attempt
    matched_dimensions: List[str]
    different_dimensions: List[str]
    resolution_applied: str     # what was actually tried (free text, e.g. a copy of source's .resolution)
    success: Optional[bool] = None   # None = outcome not yet known
    judged_by: Optional[str] = None  # "human" | "gap_resolved" | "gap_blocked" | ...
    ts: float = field(default_factory=time.time)
    judged_ts: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "outcome_id": self.outcome_id, "source_gap_id": self.source_gap_id,
            "target_gap_id": self.target_gap_id, "match_level": self.match_level,
            "matched_dimensions": self.matched_dimensions, "different_dimensions": self.different_dimensions,
            "resolution_applied": self.resolution_applied, "success": self.success,
            "judged_by": self.judged_by, "ts": self.ts, "judged_ts": self.judged_ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TransferOutcome":
        return cls(
            outcome_id=d["outcome_id"], source_gap_id=d["source_gap_id"],
            target_gap_id=d["target_gap_id"], match_level=d["match_level"],
            matched_dimensions=list(d.get("matched_dimensions", [])),
            different_dimensions=list(d.get("different_dimensions", [])),
            resolution_applied=d.get("resolution_applied", ""),
            success=d.get("success"), judged_by=d.get("judged_by"),
            ts=d.get("ts", 0.0), judged_ts=d.get("judged_ts"),
        )


@dataclass
class TransferOutcomeLog:
    """Append-only -- same "never delete, keep as history" contract as
    gap_graph.json/intervention_log.json. A wrong or failed transfer is
    exactly as valuable to keep as a successful one; this is evidence
    for a future calibration step, not a scoreboard to keep clean."""
    records: List[TransferOutcome] = field(default_factory=list)

    def append(self, record: TransferOutcome) -> None:
        self.records.append(record)

    def get(self, outcome_id: str) -> Optional[TransferOutcome]:
        for r in self.records:
            if r.outcome_id == outcome_id:
                return r
        return None

    def unjudged(self) -> List[TransferOutcome]:
        return [r for r in self.records if r.success is None]

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps([r.as_dict() for r in self.records], ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, path: Path) -> "TransferOutcomeLog":
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(records=[TransferOutcome.from_dict(d) for d in data])


def transfer_outcome_log_path(store_path: Path) -> Path:
    return store_path.parent / "transfer_outcomes.json"


def record_transfer_attempt(
    log: TransferOutcomeLog, match: StructuralMatch, *, target_gap_id: str, resolution_applied: str,
) -> TransferOutcome:
    """Call this the moment a structurally-matched resolution is actually
    tried (not just surfaced as a candidate) -- `success` starts as None
    on purpose. Recording an attempt is not the same claim as recording a
    result."""
    record = TransferOutcome(
        outcome_id=f"xfer_{uuid.uuid4().hex[:8]}",
        source_gap_id=match.gap_id, target_gap_id=target_gap_id,
        match_level=match.level, matched_dimensions=list(match.matched_dimensions),
        different_dimensions=list(match.different_dimensions),
        resolution_applied=resolution_applied,
    )
    log.append(record)
    return record


def record_transfer_outcome(
    log: TransferOutcomeLog, outcome_id: str, *, success: bool, judged_by: str,
) -> Optional[TransferOutcome]:
    """Direct judgment (typically a human, or a caller that ran a real
    verification check) -- takes priority over anything
    infer_missing_outcomes would later guess from gap status."""
    record = log.get(outcome_id)
    if record is None:
        return None
    record.success = success
    record.judged_by = judged_by
    record.judged_ts = time.time()
    return record


def infer_missing_outcomes(log: TransferOutcomeLog, gap_graph: GapGraph) -> List[TransferOutcome]:
    """Deterministic fallback for outcomes nobody explicitly judged yet:
    if the target gap has since reached RESOLVED, count the transfer as a
    success; if it's landed in one of the terminal BLOCKED_*/STALE
    states, count it as a failure. Anything still mid-lifecycle (DETECTED/
    SCOPED/ACQUIRING/...) is left unjudged -- there's no result yet, and
    guessing one would corrupt the exact signal this log exists to
    produce. Returns the records this call actually updated."""
    updated: List[TransferOutcome] = []
    for record in log.unjudged():
        node = gap_graph.get(record.target_gap_id)
        if node is None:
            continue
        if node.status == "RESOLVED":
            record.success = True
            record.judged_by = "gap_resolved"
            record.judged_ts = time.time()
            updated.append(record)
        elif node.status in BLOCKED_STATUSES:
            record.success = False
            record.judged_by = "gap_blocked"
            record.judged_ts = time.time()
            updated.append(record)
    return updated
