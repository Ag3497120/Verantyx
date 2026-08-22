"""Milestone R2 — bootstrap_unknown_task(): a domain-agnostic entry point
for "I've been handed a task I don't understand yet" (ARC-AGI-3, an
unfamiliar CLI/library, an unfamiliar repository, or anything else).

Design context (from the session's own design discussion): the earlier
draft split unknowns into just two search intents ("what is this" /
"how do I operate it"). That framing doesn't generalize -- every new task
category would need its own new intent added by hand. This module
implements the corrected design: decompose ANY task into a small set of
COMMON structural slots (the things that must be known before Vera can
act at all), and only within that generic decomposition do specific
search/acquisition intents appear.

This function does NOT search the web itself. Its only job is to turn an
under-specified task into a structured picture of what's known, what's
missing, and how urgently each missing piece blocks action -- i.e. it
builds the GapNodes; deciding how to go fill them in is
plan_acquisition()'s job, and actually filling them in is a separate step
(existing web_search/fetch_url/vera_code_ingest tools, or -- for gaps
about how ONE SPECIFIC environment instance behaves rather than the task
type in general -- active experimentation, which stays with
arc_env_adapter.py and is deliberately NOT reachable from here; see the
allowed/forbidden resolution mode note on TRANSITIONS-shaped gaps in that
module's own docstring).

Explicitly reduced scope for this pass (matches the user's own "MVP" cut
of the fuller design):
- 6 core slots (IDENTITY / GOAL / AFFORDANCES / INPUTS / SUCCESS_CRITERIA
  / CONSTRAINTS), not the full 12-slot list from the design discussion
  (STATE/TRANSITIONS/TOOLS/KNOWLEDGE_SOURCES/FAILURE_MODES stay with
  arc_env_adapter.py and future work -- a live environment's dynamics
  aren't knowable before any interaction happens, so bootstrapping them
  here would just be guessing).
- Contradiction detection is NOT implemented (`contradictions` is always
  `[]`) -- would need multiple independent evidence sources to actually
  disagree, which requires the acquisition step (not built here) to have
  already run at least twice.
- Fact/Procedure/Hypothesis/Skill quarantine-type separation is NOT
  implemented here -- acquired evidence still lands in the existing
  single AiFactQuarantine, same as every other gap-resolution path in
  this codebase today. Flagged as real future work, not silently dropped.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .gap_graph import GapGraph, GapNode
from .structural_similarity import StructuralMatch, find_structural_matches

# The reduced 6-slot decomposition (see module docstring for why the
# fuller 12-slot design was cut down for this pass).
CORE_SLOTS = ("IDENTITY", "GOAL", "AFFORDANCES", "INPUTS", "SUCCESS_CRITERIA", "CONSTRAINTS")

# A slot being unknown blocks action outright (CRITICAL) vs. merely makes
# action less well-informed (QUALITY) -- same two-tier model gap_severity.py
# already established, applied slot-by-slot instead of query-by-query.
# GOAL/AFFORDANCES/SUCCESS_CRITERIA are what SELECT_ACTION and "did this
# work" actually depend on; IDENTITY/INPUTS/CONSTRAINTS inform the choice
# but don't strictly block making *a* first move.
_CRITICAL_SLOTS = frozenset({"GOAL", "AFFORDANCES", "SUCCESS_CRITERIA"})

# Full intent vocabulary from the design discussion (section 4) -- kept
# wider than the 3 the MVP cut activates real query templates for, per
# the explicit "内部型としては...少し広くしておく方がよい" guidance, so
# adding real support for the rest later doesn't require touching this
# enum-equivalent set of string constants.
INTENT_TYPES = (
    "IDENTIFY_ENTITY", "DISCOVER_AFFORDANCES", "DISCOVER_INTERFACE",
    "DISCOVER_GOAL", "DISCOVER_CONSTRAINTS", "DISCOVER_STATE_SCHEMA",
    "DISCOVER_TRANSITION_RULES", "FIND_EXAMPLES", "FIND_VERIFIER",
    "RESOLVE_CONTRADICTION", "DISCOVER_SUCCESS_CRITERIA",
)

_SLOT_INTENT: Dict[str, str] = {
    "IDENTITY": "IDENTIFY_ENTITY",
    "GOAL": "DISCOVER_GOAL",
    "AFFORDANCES": "DISCOVER_AFFORDANCES",
    "INPUTS": "DISCOVER_INTERFACE",
    "SUCCESS_CRITERIA": "DISCOVER_SUCCESS_CRITERIA",
    "CONSTRAINTS": "DISCOVER_CONSTRAINTS",
}


@dataclass
class TaskDescriptor:
    name: str
    description: str = ""
    user_goal: str = ""
    available_inputs: List[str] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    known_affordances: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    allowed_sources: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)


@dataclass
class AcquisitionIntent:
    """Deliberately separate from GapNode (per the design discussion's
    section 3): a gap is "what's missing and why it matters"; an intent
    is "how we're going to go find out" -- keeping these apart means the
    SAME gap type can route to different tools depending on what sources
    are actually available (local repo checkout vs. web-only vs.
    interactive-environment-only), without the gap itself needing to
    encode that decision."""
    intent_type: str
    target_gap_id: str
    required_evidence: List[str]
    allowed_sources: List[str]
    preferred_tools: List[str]
    budget: int = 3


@dataclass
class TaskBootstrapResult:
    task_id: str
    normalized_descriptor: TaskDescriptor
    structural_matches: List[StructuralMatch]
    known_nodes: List[str]         # slot names Vera already had content for (see module note: no
                                    # per-slot node objects exist yet, this is slot names, not gap_ids)
    gap_nodes: List[str]           # gap_ids, severity-ranked (CRITICAL first)
    contradictions: List[str]      # always [] in this pass -- see module docstring
    executable: bool               # True iff no CRITICAL-severity gap remains open
    next_resolution_targets: List[str]  # gap_ids, same order as gap_nodes


def _task_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:60] or "task"


def _slot_content(descriptor: TaskDescriptor, slot: str) -> List[str]:
    return {
        "IDENTITY": [descriptor.description] if descriptor.description else [],
        "GOAL": [descriptor.user_goal] if descriptor.user_goal else [],
        "AFFORDANCES": list(descriptor.known_affordances),
        "INPUTS": list(descriptor.available_inputs),
        "SUCCESS_CRITERIA": list(descriptor.success_criteria),
        "CONSTRAINTS": list(descriptor.constraints),
    }[slot]


def bootstrap_unknown_task(gap_graph: GapGraph, descriptor: TaskDescriptor) -> TaskBootstrapResult:
    task_id = _task_id(descriptor.name)

    known_slots: List[str] = []
    unknown_slots: List[str] = []
    for slot in CORE_SLOTS:
        (known_slots if _slot_content(descriptor, slot) else unknown_slots).append(slot)

    # A lightweight, persisted "this task was bootstrapped" node -- exists
    # purely so a FUTURE bootstrap call has something to structurally
    # compare against (see module docstring's "タスク開始時" comparison
    # point). Reuses GapNode's existing fields pragmatically: failure_type
    # here doesn't mean "this failed", it's the comparison key structural_
    # similarity.py already keys on -- documented rather than silently
    # repurposed.
    slot_pattern = f"known:{','.join(sorted(known_slots))}|unknown:{','.join(sorted(unknown_slots))}"
    task_node = gap_graph.create(
        gap_type="TASK_BOOTSTRAPPED", subject=descriptor.name, scope=f"task:{task_id}",
        severity="OPTIONAL" if not unknown_slots else "QUALITY",
        status="RESOLVED" if not unknown_slots else "DETECTED",
        role="task_bootstrap", failure_type="task_identity",
        input_type=f"inputs_{'given' if descriptor.available_inputs else 'unspecified'}",
        output_type=f"goal_{'given' if descriptor.user_goal else 'unspecified'}",
        expected_transition=slot_pattern, observed_transition=slot_pattern,
    )
    candidates = [n for n in gap_graph.nodes.values() if n.gap_id != task_node.gap_id]
    structural_matches = find_structural_matches(task_node, candidates, limit=5)

    gap_ids: List[str] = []
    for slot in unknown_slots:
        severity = "CRITICAL" if slot in _CRITICAL_SLOTS else "QUALITY"
        node = gap_graph.create(
            gap_type=f"UNKNOWN_{slot}",
            subject=f"{descriptor.name}: {slot}",
            scope=f"task:{task_id}:{slot}",
            severity=severity,
            status="DETECTED",
            required_for=[f"bootstrap:{task_id}"],
            role="task_bootstrap_slot",
            failure_type=f"missing_{slot.lower()}",
            input_type=f"slot:{slot}",
            output_type="unresolved",
        )
        gap_ids.append(node.gap_id)

    # CRITICAL-first ranking (simple, not the fuller cost/value formula
    # from the design discussion -- that lives in a future heartbeat
    # rewrite, not here).
    gap_ids.sort(key=lambda gid: 0 if gap_graph.get(gid).severity == "CRITICAL" else 1)
    # "executable" means no CRITICAL gap is still OPEN -- severity alone
    # isn't enough to check (a resolved gap keeps its CRITICAL severity as
    # a historical record, it just isn't blocking anymore).
    executable = not any(
        gap_graph.get(gid).severity == "CRITICAL" and gap_graph.get(gid).status != "RESOLVED"
        for gid in gap_ids
    )

    return TaskBootstrapResult(
        task_id=task_id, normalized_descriptor=descriptor,
        structural_matches=structural_matches, known_nodes=known_slots,
        gap_nodes=gap_ids, contradictions=[], executable=executable,
        next_resolution_targets=list(gap_ids),
    )


def build_search_query(intent_type: str, subject: str) -> str:
    """Query text varies by WHAT we're trying to learn, not a single
    template reused for everything (the exact problem with the earlier
    what_is_this/how_to_operate split -- it collapsed distinct intents
    into the same query shape)."""
    if intent_type == "IDENTIFY_ENTITY":
        return f"{subject} overview definition official"
    if intent_type == "DISCOVER_INTERFACE":
        return f"{subject} official API action observation schema"
    if intent_type == "DISCOVER_AFFORDANCES":
        return f"{subject} supported operations controls documentation"
    if intent_type == "DISCOVER_GOAL":
        return f"{subject} objective what counts as completion"
    if intent_type == "DISCOVER_SUCCESS_CRITERIA":
        return f"{subject} success criteria validation official"
    if intent_type == "DISCOVER_CONSTRAINTS":
        return f"{subject} limitations restrictions rules official"
    if intent_type == "FIND_VERIFIER":
        return f"{subject} validation success criteria official"
    if intent_type == "FIND_EXAMPLES":
        return f"{subject} example usage sample"
    return f"{subject} overview"


def plan_acquisition(gap: GapNode, descriptor: TaskDescriptor) -> AcquisitionIntent:
    """One gap in, one concrete acquisition plan out. The routing rule
    that matters (from the design discussion's section 8): a local
    checkout takes priority over the web for code-shaped tasks, because
    for a repo, code/tests ARE the ground truth and a web search would
    just be a worse copy of what's already on disk."""
    slot = gap.gap_type.replace("UNKNOWN_", "", 1)
    intent_type = _SLOT_INTENT.get(slot, "IDENTIFY_ENTITY")

    if "local_repository" in descriptor.allowed_sources:
        preferred_tools = ["vera_code_query", "vera_code_ingest"]
        allowed_sources = ["local_repository"]
    else:
        preferred_tools = ["web_search", "fetch_url"]
        allowed_sources = ["web"] + [s for s in descriptor.allowed_sources if s != "web"]

    return AcquisitionIntent(
        intent_type=intent_type, target_gap_id=gap.gap_id,
        required_evidence=[build_search_query(intent_type, gap.subject)],
        allowed_sources=allowed_sources, preferred_tools=preferred_tools,
    )


def select_next_action(
    result: TaskBootstrapResult, gap_graph: GapGraph,
) -> Optional[AcquisitionIntent]:
    """"Select ONE acquisition action" (the MVP flow's own last step) --
    not a scheduler, just picks the top of the already-ranked list. A
    real priority-ranked multi-gap scheduler is heartbeat()'s job, not
    this one-shot bootstrap call's."""
    for gap_id in result.next_resolution_targets:
        node = gap_graph.get(gap_id)
        if node is not None and node.status in ("DETECTED", "SCOPED", "RESOLUTION_PLANNED"):
            return plan_acquisition(node, result.normalized_descriptor)
    return None
