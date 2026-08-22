"""Milestone S — the first wire between the IDE's "body" (Swift-side UI
automation: HiddenWindowAutomation, VisualDiffRegion, UITestVectorTrace)
and Vera-alpha's "mind" (GapNode). Direct precedent: arc_env_adapter.py,
which does the same job for ARC-AGI-3 grid observations. This module is
that same pattern applied to IDE UI actions instead of grid diffs.

Deliberately narrow, matching arc_env_adapter's own honesty about scope:
this does NOT implement a prediction hypothesis yet (arc_env_adapter's
"identity" hypothesis has no UI equivalent here). v1 only records what was
observed -- expected_transition stays unset. Turning the accumulated
observations into real mismatch detection (via structural_similarity.
find_structural_matches across sessions) is deliberately future work; see
this module's own note at the bottom of the file it was planned alongside.

Model-independent by design: nothing here touches JGEN's vector space or
any model-specific state (unlike UITestVectorTrace.swift, which embeds via
JCrossChatManager and is JGEN-backend-only). This is the persistent,
model-swappable half of the loop.
"""
from __future__ import annotations

import re
from typing import Optional

from .gap_graph import GapGraph, GapNode

# Strips the parts of an action label most likely to vary between
# otherwise-identical occurrences (coordinates, quoted literal text) so
# repeated instances of "the same kind of action" collapse into one
# GapNode via GapGraph.create's own (scope, subject) dedup, rather than
# spawning a new node per pixel-coordinate.
_COORD_RE = re.compile(r"-?\d+(\.\d+)?")
_QUOTED_RE = re.compile(r'"[^"]*"')


def normalize_action_label(action_label: str) -> str:
    normalized = _QUOTED_RE.sub('"…"', action_label)
    normalized = _COORD_RE.sub("#", normalized)
    return normalized.strip().lower()


def observe_ui_transition(
    gap_graph: GapGraph, *, session_id: str, action_label: str, changed: bool,
) -> GapNode:
    """Called once per recorded UI-automation step (mirrors
    UITestVectorTrace.recordMoment's call site in AgentLoop.swift). Unlike
    arc_env_adapter.observe_transition, this always returns a node (never
    None) -- v1's job is building the substrate (a causal action ->
    observation record Vera can later mine), not judging surprise, so
    every observation is worth keeping, not just the unexpected ones.

    Known v1 limitation, inherited as-is from GapGraph.create's existing
    (and unmodified) dedup contract: a second observation of the same
    (session, normalized action) that produced a DIFFERENT
    observed_transition than the first does NOT update the existing node
    -- create() returns the first-seen node unchanged. That "same action
    family, different outcome" case is exactly the kind of real mismatch
    a future pass should surface, but reconciling it means either
    updating GapGraph.create's reuse behavior or adding an explicit
    update path here, both deliberately deferred rather than changed
    silently as part of this pass."""
    normalized = normalize_action_label(action_label)
    node = gap_graph.create(
        gap_type="UI_ACTION_OBSERVATION",
        # Real bug caught by an offline test while building this: GapGraph.
        # create()'s dedup requires an EXACT match on (scope, subject), not
        # just scope. Using the raw (un-normalized) action_label as subject
        # meant "click 412,600" and "click 415,598" never deduplicated at
        # all -- defeating the entire point of normalizing in the first
        # place. subject must be the normalized family, same as scope's
        # suffix; arc_env_adapter's own subject ("level:X action:Y") is
        # already family-level for the same reason, not raw per-instance
        # data.
        subject=normalized,
        scope=f"ide_ui:{session_id}:{normalized}",
        severity="QUALITY",
        status="DETECTED",
        role="ui_action",
        failure_type=None,
        input_type="ui_action",
        output_type="screen_region",
        expected_transition=None,
        observed_transition="changed" if changed else "no_change",
    )
    return node
