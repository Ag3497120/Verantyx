"""Milestone R1 — ARC-AGI-3 environment adapter: turn a 2D dynamic-puzzle
observation into a GapNode.

Context: ARC-AGI-3 tasks are NOT the static input-grid -> output-grid
transformation of ARC-AGI-1/2. They are interactive: an agent takes an
action inside a 2D grid "game" and observes the resulting frame, across
many steps, with the level's actual rule undiscovered up front. This
module is the thing router.py/agent.py never had: a way to turn "I took
an action and the resulting frame didn't match what I expected" into a
GapNode, using the exact same typed fields (role/failure_type/input_type/
output_type/expected_transition/observed_transition) gap_graph.py already
carries for that purpose (added in the Milestone O structural-similarity
extension, specifically anticipating a non-text domain like this one).

Deliberately narrow for this pass (see the design conversation this
milestone came out of): only ONE prediction hypothesis is implemented
(the identity/"nothing changes" hypothesis) -- this is not meant to be a
puzzle solver. Its only job is to notice "the world didn't behave as
naively expected" and hand that off as a structured gap. structural_
similarity.py (already built, unmodified by this module) is what then
finds whether a previously-resolved gap looks like the same shape of
failure -- that cross-domain reuse is the actual point being tested here,
not this module's own prediction quality.

Does NOT touch procedure_exec.py's closed instruction set. That set is
still digit-addition-only; giving Vera a real vocabulary of ARC-style
transformations (rotate/reflect/recolor/flood-fill/...) to RESOLVE these
gaps with is explicitly future work, gated on first seeing which failure
shapes actually recur (see this module's own honest-limits note below).
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from .gap_graph import GapGraph, GapNode
from .structural_similarity import StructuralMatch, find_structural_matches

Grid = Sequence[Sequence[int]]


def grid_shape(grid: Grid) -> Tuple[int, int]:
    h = len(grid)
    w = len(grid[0]) if h else 0
    return h, w


def diff_grids(before: Grid, after: Grid) -> List[Tuple[int, int, int, int]]:
    """(row, col, old_value, new_value) for every cell that changed.
    Grids of different shape are reported as a single sentinel diff --
    per-cell comparison is meaningless once dimensions don't line up."""
    if grid_shape(before) != grid_shape(after):
        return [(-1, -1, -1, -1)]
    out: List[Tuple[int, int, int, int]] = []
    for r, (row_b, row_a) in enumerate(zip(before, after)):
        for c, (old, new) in enumerate(zip(row_b, row_a)):
            if old != new:
                out.append((r, c, old, new))
    return out


def _bucket(n: int) -> str:
    """Coarse, deliberately lossy bucketing -- see this module's own
    honest-limits note. The point is letting two DIFFERENT puzzles that
    both made "a few cells change color, grid otherwise stable" compare
    as structurally equal, not capturing exact geometry (that would make
    every real observation unique and defeat structural_similarity's
    exact-string equality check on expected/observed_transition)."""
    if n == 0:
        return "0"
    if n <= 3:
        return "1-3"
    if n <= 9:
        return "4-9"
    return "10+"


def _canonical_transition(shape_changed: bool, diff: List[Tuple[int, int, int, int]]) -> str:
    n_changed = len(diff)
    n_distinct_pairs = len({(old, new) for _, _, old, new in diff})
    return f"shape_{'changed' if shape_changed else 'same'}|cells_{_bucket(n_changed)}|colors_{_bucket(n_distinct_pairs)}"


def predict_identity(frame: Grid) -> List[List[int]]:
    """The ONLY hypothesis this pass implements: "the action changes
    nothing." Deliberately the simplest possible prediction, so that
    almost any real rule surfaces a mismatch immediately -- this module's
    job is to notice gaps, not to guess well."""
    return [list(row) for row in frame]


def observe_transition(
    gap_graph: GapGraph, *, session_id: str, level_id: str, action: str,
    frame_before: Grid, frame_after: Grid,
) -> Optional[GapNode]:
    """Called once per action taken in an ARC-AGI-3 session. Returns the
    GapNode for this mismatch (new or a previously-seen one for the same
    level+action, deduplicated by GapGraph.create's own scope/subject
    rule) if the identity hypothesis was wrong, or None if the action
    genuinely did nothing (no gap -- there's nothing unexplained about a
    correctly-predicted no-op)."""
    predicted = predict_identity(frame_before)
    predicted_shape = grid_shape(predicted)
    actual_shape = grid_shape(frame_after)

    expected_diff = diff_grids(frame_before, predicted)  # always empty by construction
    observed_diff = diff_grids(frame_before, frame_after)
    if not observed_diff:
        return None  # identity hypothesis was correct this step -- not a gap

    shape_changed = predicted_shape != actual_shape
    node = gap_graph.create(
        gap_type="MISSING_STATE_TRANSITION_RULE",
        subject=f"level:{level_id} action:{action}",
        scope=f"arc:{session_id}:{level_id}:{action}",
        severity="QUALITY",  # a game rule being unknown is never CRITICAL/blocking (gap_severity.py's own default)
        status="DETECTED",
        # NOT web_search/fetch_url/vera_ask: no acquisition method here
        # can meaningfully close this gap yet. Sleep mode's heartbeat()
        # doesn't recognize "structural_transfer" either (only checks for
        # "web_search"), so it correctly falls through to
        # BLOCKED_NO_SOURCE rather than firing a nonsensical web search
        # against a grid-diff string -- an honest failure mode, not a bug.
        acquisition_methods=["structural_transfer"],
        allowed_sources=["structural_similarity"],
        role="trigger",
        failure_type="missing_state_transition",
        input_type=f"grid2d:{predicted_shape[0]}x{predicted_shape[1]}",
        output_type=f"grid2d:{actual_shape[0]}x{actual_shape[1]}",
        expected_transition=_canonical_transition(False, expected_diff),
        observed_transition=_canonical_transition(shape_changed, observed_diff),
    )
    return node


def find_transferable_matches(
    gap_node: GapNode, gap_graph: GapGraph, *, limit: int = 5,
) -> List[StructuralMatch]:
    """Thin wrapper over structural_similarity.find_structural_matches,
    restricted to the question this module exists to answer: "has a
    structurally-identical failure been seen (and ideally resolved)
    before, regardless of which level/session it came from?" No new
    comparison logic here -- reuses the same ranking already built and
    tested for the text-query gap case."""
    candidates = [n for n in gap_graph.nodes.values() if n.gap_id != gap_node.gap_id]
    return find_structural_matches(gap_node, candidates, limit=limit)
