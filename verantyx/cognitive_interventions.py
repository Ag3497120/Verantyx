"""Milestone P5 — automatic closed-loop hidden-state intervention.

Where jgen_reflect (agent_tools.py, Milestone P4) is a tool the LLM must
explicitly choose to call, this module lets Vera itself decide to reach
into JGEN's hidden state without waiting for an LLM's tool choice --
whenever a freshly-detected GapNode makes a hidden-state probe worth
attempting. This is the actual "Vera decides what JGEN thinks about"
half of the closed loop; jgen_reflect (P4) remains the manual escape
hatch, unchanged.

Every intervention is recorded with provenance (intervention_id,
source_nodes, layer, expected effect, observed effect) so a human can
audit why JGEN's hidden state was ever touched -- matches the same
"nothing here becomes trusted without a visible trail" posture as
ai_ingest.py/module_ingest.py's quarantine queues, just for a diagnostic
probe rather than a knowledge write.

Hard boundary (do not blur this): this module NEVER writes to CrossStore
and NEVER marks a GapNode RESOLVED on its own. An intervention's decoded
observation is fed back into the ReAct transcript (agent.py) as ordinary
tool-observation evidence for Vera/the LLM to reason over on the NEXT
step, exactly like any other tool's observation. "Vera decides to look"
is automated here; "Vera decides to believe what it saw" is not -- that
judgment stays in the normal ReAct loop, same as every other observation.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Deterministic role -> layer assignment. Not learned, not empirically
# tuned -- a fixed, small, auditable mapping in the same spirit as
# procedure_exec.py's closed ALLOWED_OPS set: a short, legible vocabulary
# rather than a black box. Rough intuition only (surface-level state early,
# more abstract state later), explicitly NOT validated against real model
# behavior -- see the honest-limits note in build_intervention_plan below.
ROLE_LAYER_HINTS: Dict[str, int] = {
    "goal": 2,
    "evidence": 4,
    "rejected_hypothesis": 6,
    "knowledge_gap": 8,
}

DEFAULT_ALPHA = 0.12  # matches the design discussion's own example strength


@dataclass
class InterventionSpec:
    role: str  # one of ROLE_LAYER_HINTS's keys
    text_label: str
    layer: int
    alpha: float = DEFAULT_ALPHA

    def as_dict(self) -> Dict[str, Any]:
        return {"layer": self.layer, "text_label": self.text_label, "alpha": self.alpha}


@dataclass
class InterventionRecord:
    """One closed-loop probe: what was injected, where, why, and what
    came back. `accepted` is left unset by this module on purpose -- a
    human (or a later, separate review step) is the one who judges
    whether an intervention's observation was actually useful; this
    module only ever proposes and records, never grades itself."""
    intervention_id: str
    source_nodes: List[str]
    model: str
    specs: List[Dict[str, Any]]
    observe_layers: List[int]
    observations: Dict[str, str]
    expected_effect: str
    ts: float
    accepted: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intervention_id": self.intervention_id, "source_nodes": self.source_nodes,
            "model": self.model, "specs": self.specs, "observe_layers": self.observe_layers,
            "observations": self.observations, "expected_effect": self.expected_effect,
            "ts": self.ts, "accepted": self.accepted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InterventionRecord":
        return cls(
            intervention_id=d["intervention_id"], source_nodes=list(d.get("source_nodes", [])),
            model=d.get("model", ""), specs=list(d.get("specs", [])),
            observe_layers=list(d.get("observe_layers", [])),
            observations=dict(d.get("observations", {})),
            expected_effect=d.get("expected_effect", ""), ts=d.get("ts", 0.0),
            accepted=d.get("accepted"),
        )


@dataclass
class InterventionLog:
    """Append-only provenance log -- same "never delete, keep as history"
    contract as gap_graph.json."""
    records: List[InterventionRecord] = field(default_factory=list)

    def append(self, record: InterventionRecord) -> None:
        self.records.append(record)

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps([r.as_dict() for r in self.records], ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, path: Path) -> "InterventionLog":
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(records=[InterventionRecord.from_dict(d) for d in data])


def intervention_log_path(store_path: Path) -> Path:
    return store_path.parent / "intervention_log.json"


def build_intervention_plan(gap_node: Any, *, confirmed_facts: Optional[List[str]] = None) -> List[InterventionSpec]:
    """Deterministically turns a GapNode's own structural fields into a
    small set of text-labeled interventions. No LLM/JGEN call happens in
    THIS function -- vectorization only happens once these labels reach
    jgen_reflect's encode step (Milestone P4), same "Vera speaks in text,
    JGEN owns the embedding space" boundary as everywhere else in P.

    Kept small and legible on purpose (<=4 specs, one intervention_spec
    per known role, not a general-purpose composer):
    - "goal" always fires (the gap's own subject).
    - "evidence" fires only if the caller supplied confirmed facts.
    - "rejected_hypothesis" fires only if the node already recorded a
      dead-end (`observed_transition` populated by a prior probe/attempt).
    - "knowledge_gap" always fires (the gap's own type + subject, phrased
      as a deficiency rather than a goal, i.e. two different framings of
      the same underlying gap deliberately given different layers).

    Honest limit: layer choice is a fixed heuristic (ROLE_LAYER_HINTS),
    not validated against how these specific layers actually behave in a
    real loaded model -- same caveat Milestone P's plan already stated for
    execute_inject_multi_layer's blended-injection quality.
    """
    specs: List[InterventionSpec] = [
        InterventionSpec("goal", f"Goal: resolve — {gap_node.subject[:200]}",
                          ROLE_LAYER_HINTS["goal"]),
    ]
    if confirmed_facts:
        joined = "; ".join(f for f in confirmed_facts[:3] if f)
        if joined:
            specs.append(InterventionSpec(
                "evidence", f"Known facts: {joined[:200]}", ROLE_LAYER_HINTS["evidence"],
            ))
    if getattr(gap_node, "observed_transition", None):
        specs.append(InterventionSpec(
            "rejected_hypothesis",
            f"Already tried and did not resolve: {gap_node.observed_transition[:200]}",
            ROLE_LAYER_HINTS["rejected_hypothesis"],
        ))
    specs.append(InterventionSpec(
        "knowledge_gap", f"Missing: {gap_node.gap_type} — {gap_node.subject[:150]}",
        ROLE_LAYER_HINTS["knowledge_gap"],
    ))
    return specs


def new_intervention_id() -> str:
    return f"int_{uuid.uuid4().hex[:8]}"
