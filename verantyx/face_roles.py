"""Per-arm face roles (original stereo-cross vision).

Geometry: center cube + 6 arms; 5 exposed faces per arm.

Roles (formula):
  tip          = CORE   — core meaning slot for the lemma on that axis
  north/south/east/west = FACET — constitutive / factual aspects

Read order for a single-axis facet document (default):
  tip → north → south → east → west
  (EOS when the path hits an empty face after content, or max_doc)

Notation:
  role(f) ∈ {core, facet}
  CORE_FACE = tip
  FACET_FACES = (north, south, east, west)
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .cross import AXES, FACE_SLOTS, ShellCross

CORE_FACE: str = "tip"
FACET_FACES: Tuple[str, ...] = ("north", "south", "east", "west")
# Documented default compose order for one activated axis.
FACET_READ_ORDER: Tuple[str, ...] = (CORE_FACE,) + FACET_FACES

FACE_ROLE: Dict[str, str] = {
    "tip": "core",
    "north": "facet",
    "south": "facet",
    "east": "facet",
    "west": "facet",
}


def role_of(face: str) -> str:
    """Return 'core' or 'facet' for a face slot name."""
    if face not in FACE_SLOTS:
        raise KeyError(f"unknown face {face!r}; expected one of {FACE_SLOTS}")
    return FACE_ROLE[face]


def is_core_face(face: str) -> bool:
    return face == CORE_FACE


def is_facet_face(face: str) -> bool:
    return face in FACET_FACES


def find_core_axis(shell: ShellCross, core: str) -> Optional[str]:
    """Axis whose tip holds ``core``, else None."""
    for a in AXES:
        if shell.faces[a].get(CORE_FACE) == core:
            return a
    return None


def facts_on_axis(shell: ShellCross, axis: str) -> List[str]:
    """Non-empty facet-face tokens on ``axis`` in FACET_FACES order."""
    out: List[str] = []
    for f in FACET_FACES:
        tok = shell.faces[axis].get(f)
        if tok is not None:
            out.append(tok)
    return out


def facet_read_path(
    shell: ShellCross,
    axis: str,
    *,
    include_empty: bool = False,
    join_neighbor_axes: bool = False,
) -> List[Tuple[str, str, str, str]]:
    """Build (axis, face, role, token) path for document composition.

    Primary axis: tip then facets. Optional: append neighbor-axis tip+facets
    that are occupied (join-network stub — partial vs full vision).
    """
    path: List[Tuple[str, str, str, str]] = []
    axes_walk: List[str] = [axis]
    if join_neighbor_axes:
        i = AXES.index(axis)
        for off in (1, -1, 2, -2, 3):
            a = AXES[(i + off) % len(AXES)]
            if a not in axes_walk:
                axes_walk.append(a)

    for a in axes_walk:
        for f in FACET_READ_ORDER:
            tok = shell.faces[a].get(f)
            if tok is None:
                if include_empty:
                    path.append((a, f, role_of(f), ""))
                elif path and a == axis:
                    # soft EOS on primary axis after content
                    return path
                continue
            path.append((a, f, role_of(f), tok))
    return path


def place_core_facts_on_shell(
    shell: ShellCross,
    core: str,
    facts: Sequence[str],
    *,
    axis: Optional[str] = None,
    prefer_axes: Optional[Sequence[str]] = None,
    overwrite_core: bool = False,
) -> Dict[str, object]:
    """Assign core→tip and facts→facet faces (deterministic).

    Collision rules:
      1. Choose axis: explicit ``axis``, else first of ``prefer_axes``,
         else first AXES with free tip (or tip==core).
      2. If tip occupied by another symbol and not overwrite_core → next axis.
      3. Facts fill FACET_FACES in order; skip occupied cells; leftover facts
         spill to next free facet faces on subsequent axes (same prefer order).
    """
    core = str(core).casefold().strip()
    fact_list = [str(f).casefold().strip() for f in facts if str(f).strip()]
    order: List[str] = []
    if axis is not None:
        order.append(axis)
    if prefer_axes:
        for a in prefer_axes:
            if a not in order:
                order.append(a)
    for a in AXES:
        if a not in order:
            order.append(a)

    chosen: Optional[str] = None
    for a in order:
        tip = shell.faces[a].get(CORE_FACE)
        if tip is None or tip == core or overwrite_core:
            chosen = a
            break
    if chosen is None:
        return {
            "placed": False,
            "core": core,
            "axis": None,
            "facts_placed": [],
            "facts_overflow": list(fact_list),
            "reason": "no_free_tip",
        }

    shell.faces[chosen][CORE_FACE] = core
    shell.reflections[chosen] = core

    placed: List[Tuple[str, str, str]] = []  # (axis, face, token)
    remaining = list(fact_list)
    # Primary axis facets first, then spill.
    spill_axes = [chosen] + [a for a in order if a != chosen]
    for a in spill_axes:
        if not remaining:
            break
        for f in FACET_FACES:
            if not remaining:
                break
            if shell.faces[a][f] is not None and shell.faces[a][f] != remaining[0]:
                continue
            tok = remaining.pop(0)
            shell.faces[a][f] = tok
            placed.append((a, f, tok))

    # Custom read order for this axis (core then facets) — vision compose default.
    # Keep global read_order but prepend this axis's facet path for locality.
    axis_order = [(chosen, f) for f in FACET_READ_ORDER]
    rest = [(a, f) for a, f in shell.read_order if a != chosen]
    shell.read_order = axis_order + rest

    return {
        "placed": True,
        "core": core,
        "axis": chosen,
        "facts_placed": placed,
        "facts_overflow": remaining,
        "reason": "ok",
    }
