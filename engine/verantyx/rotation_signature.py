"""Rotation-canonical shape signatures — the 24 symmetries, awake.

Two crosses that are the same arrangement seen from different angles are the
same problem. The octahedron's 24 proper rotations make that computable: a
cross's SHAPE (which arms are filled, how heavily — never the words) is
serialised under every rotation, the lexicographically smallest serialisation
is the canonical form, and its hash is the signature. Same shape up to
rotation ⇒ same signature, by construction rather than by search.

What a signature buys, in the order it becomes real:

  1. Recognition:  "this problem has the shape of one I solved" is a dict
                   lookup, not graph isomorphism.
  2. Replay:       the accepted-move sequence that solved a shape can be
                   re-applied to an identical-signature shell and VERIFIED —
                   replay never trusts, it re-evaluates, and falls back to
                   full search when the check fails. Correctness is not
                   traded for the shortcut.
  3. Transfer:     gaps in different fields with one signature are one shape
                   of problem — the cross-domain prior the remedy taxonomy
                   wants.

Stated limits, so this is not oversold: signatures see shape, not content —
two unrelated problems can share one (the replay check exists precisely for
that); and the speed effect is unmeasurable on toy stores (the fork below
verifies mechanism, not throughput). Replay across ROTATED twins would need
the moves mapped through the aligning rotation and is not implemented —
same-signature-same-orientation only, said plainly.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .consensus import AXES, ConsensusConfig, SearchState, evaluate, query_content
from .cross import FACE_SLOTS, ShellCross

_VEC = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0),
        "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
_LBL = {v: k for k, v in _VEC.items()}


def _rotations() -> List[Dict[str, str]]:
    """The 24 proper rotations of the octahedron, as axis-label permutations.

    Generated, not hand-listed: all signed permutation matrices with
    determinant +1. 48 signed permutations exist; exactly half are proper
    rotations, and asserting the count catches a generation bug loudly."""
    rots: List[Dict[str, str]] = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            # determinant of the signed permutation matrix
            det = signs[0] * signs[1] * signs[2]
            inversions = sum(1 for i in range(3) for j in range(i + 1, 3)
                             if perm[i] > perm[j])
            if inversions % 2 == 1:
                det = -det
            if det != 1:
                continue
            mapping: Dict[str, str] = {}
            for label, vec in _VEC.items():
                out = [0, 0, 0]
                for i in range(3):
                    out[i] = signs[i] * vec[perm[i]]
                mapping[label] = _LBL[tuple(out)]
            rots.append(mapping)
    assert len(rots) == 24, f"octahedron has 24 rotations, generated {len(rots)}"
    return rots


ROTATIONS = _rotations()


def _axis_profile(shell: ShellCross, axis: str) -> Tuple:
    """Shape of one arm: which face slots are filled. Words never enter —
    a signature that saw words would stop matching across domains, which is
    the entire point of having one."""
    faces = shell.faces.get(axis, {})
    return tuple(1 if faces.get(f) is not None else 0 for f in FACE_SLOTS)


def signature(shell: ShellCross) -> str:
    """Canonical (rotation-minimal) serialisation of the fill pattern."""
    best: Optional[Tuple] = None
    for rot in ROTATIONS:
        serial = tuple(_axis_profile(shell, rot[a]) for a in AXES)
        if best is None or serial < best:
            best = serial
    return hashlib.sha256(json.dumps(best).encode()).hexdigest()[:12]


def replay(shell: ShellCross, query: str, moves: List[Dict[str, Any]],
           cfg: Optional[ConsensusConfig] = None) -> Dict[str, Any]:
    """Re-apply a recorded move sequence and RE-EVALUATE the result.

    The cost is len(moves) evaluations instead of a full neighbourhood
    search per step — the shortcut. The re-evaluation is not optional: a
    signature collision (same shape, unrelated content) must fail here and
    fall back, never sail through on trust.
    """
    from .consensus import _apply_move  # intra-package, deliberate

    cfg = cfg or ConsensusConfig()
    qset, _head = query_content(query)
    state = SearchState(shell=shell)
    applied = 0
    for mv in moves:
        kind = mv.get("kind") or mv.get("move")
        arg = mv.get("arg")
        if kind is None:
            continue
        if isinstance(arg, list):
            arg = tuple(arg)
        state = _apply_move(state, (kind, arg))
        applied += 1
    metrics = evaluate(state, qset, cfg)
    return {"applied": applied, "agree_all": metrics.agree_all,
            "contradiction": metrics.contradiction,
            "evaluations": applied + 1}


@dataclass
class SignatureIndex:
    """signature → what solved that shape. The recognition memory."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def record(self, sig: str, *, verdict: str, moves: List[Dict[str, Any]],
               domain: str = "", remedy: str = "") -> None:
        slot = self.entries.setdefault(sig, {"seen": 0, "domains": [],
                                             "verdict": verdict, "moves": moves,
                                             "remedies": []})
        slot["seen"] += 1
        if domain and domain not in slot["domains"]:
            slot["domains"].append(domain)
        if remedy and remedy not in slot["remedies"]:
            slot["remedies"].append(remedy)

    def lookup(self, sig: str) -> Optional[Dict[str, Any]]:
        return self.entries.get(sig)

    def transfer_prior(self, sig: str) -> Dict[str, Any]:
        """Cross-domain read: which fields produced this shape, and what
        fixed it there. A PRIOR, labelled as such — same shape does not
        prove same cause, it proposes where to look first."""
        hit = self.entries.get(sig)
        if hit is None:
            return {"known_shape": False}
        return {"known_shape": True, "seen": hit["seen"],
                "domains": hit["domains"], "remedies": hit["remedies"]}
