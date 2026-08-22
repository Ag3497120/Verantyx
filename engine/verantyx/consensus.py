"""Multi-frontier consensus search — 最初の構想の推論核.

k sections (断面) access the center from different exposed cross-sections.
An edge query changes per-node energy ratios; moves (arm swaps, view rotation,
one-shot escape widening) rearrange the cross; the search halts on:

  ANSWER  ⟺  NoImprovingMove ∧ AllSectionsAgree ∧ EvidenceComplete
             ∧ NoContradiction

Everything else ships as a typed verdict:

  AMBIGUOUS                        ≥2 evidenced hypotheses tie in energy
  UNKNOWN_BUDGET                   improving move exists but budget spent
  UNKNOWN_LOCAL_MINIMUM            locally stable, disagree, escape disabled
  UNKNOWN_SECTION_DISAGREEMENT     locally stable, disagree, escape spent
  UNKNOWN_INSUFFICIENT_EVIDENCE    agreement without required facet evidence
  UNKNOWN_NO_EVIDENCE              no section reaches any occupied node
  UNKNOWN_UNRESOLVED_CONTRADICTION reserved (facet-level negation NYI)

Move acceptance is lexicographic — (contradiction, evidence deficit,
agreement, relevance, path cost) — never a weighted sum, so a short but
unsupported path can never win. "All proposals rejected" only sets the
local-stability flag; shipping an answer additionally requires the
agreement + evidence gates.

Generation on ANSWER: concatenate the axis words from the agreed section
paths toward the center (tip → facets), i.e. natural-language rearrangement,
no LM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .cross import AXES, ShellCross
from .en_decompose import decompose
from .lex_filters import norm_words
from .face_roles import (
    CORE_FACE,
    FACET_READ_ORDER,
    facts_on_axis,
    find_core_axis,
)

VERDICTS: Tuple[str, ...] = (
    "ANSWER",
    "AMBIGUOUS",
    "UNKNOWN_BUDGET",
    "UNKNOWN_LOCAL_MINIMUM",
    "UNKNOWN_SECTION_DISAGREEMENT",
    "UNKNOWN_INSUFFICIENT_EVIDENCE",
    "UNKNOWN_NO_EVIDENCE",
    "UNKNOWN_UNRESOLVED_CONTRADICTION",
)

N_SECTIONS = len(AXES)


@dataclass
class ConsensusConfig:
    window: int = 1              # half-width of each section's visible arc
    required_evidence: int = 1   # facet faces needed on the winning axis
    min_sections: int = 2        # active sections needed for agreement
    w_query: float = 2.0         # tip-in-query energy bonus
    w_overlap: float = 1.0       # facet∩query energy bonus per token
    max_moves: int = 64
    allow_escape: bool = True    # one-shot: unlock all + widen to full view
    tie_delta: float = 0.0       # energy gap treated as a tie (ambiguity)
    # E1 — the visibility question only the designer's data can settle.
    #
    # False (default): the original ring. AXES is treated as a cycle, so a
    # section's window contains its own OPPOSITE pole (+x sees -x at
    # window=1). Under the both-poles-express-nuance reading this is a
    # feature: a section perceives a claim and its counter-side together.
    #
    # True: the actual solid geometry. A section sees its own axis plus
    # PERPENDICULAR neighbours only; the opposite pole is invisible from
    # where you stand, and the only ways to ever face it are rotation or
    # the one-shot escape — turning "consider the counter-evidence" into an
    # explicit, logged move.
    #
    # Same visible-arc size in both modes (2*window+1), so an A/B compares
    # topology, not window area.
    geometric_visibility: bool = False


@dataclass
class SearchState:
    shell: ShellCross
    rotation: int = 0            # section→axis view offset
    widened: bool = False        # escape flag: full visibility
    locks: Set[str] = field(default_factory=set)  # axes frozen for swaps


def copy_shell(shell: ShellCross) -> ShellCross:
    s = ShellCross(center=shell.center)
    s.faces = {a: dict(shell.faces[a]) for a in AXES}
    s.reflections = dict(shell.reflections)
    s.read_order = list(shell.read_order)
    return s


def query_content(query: str) -> Tuple[Set[str], Optional[str]]:
    """(content-token set, intent head) via elementary EN decompose."""
    rec = decompose(query or "")
    toks = set(rec.content_tokens)
    head = rec.heads[0] if rec.heads else None
    return toks, head


def axis_energy(
    shell: ShellCross,
    a: str,
    qset: Set[str],
    cfg: ConsensusConfig,
    masses: Optional[Any] = None,
    memory: Optional[Any] = None,
) -> float:
    tip = shell.faces[a].get(CORE_FACE)
    if tip is None:
        return 0.0
    m = float(masses.get(tip)) if masses is not None else 1.0
    facets = facts_on_axis(shell, a)
    overlap = sum(1 for f in facets if norm_words(f) & qset)
    # 一致語数でスケール: 複合語 "sun_tzu" は "sun tzu" クエリで 2 語一致し
    # 単語 "sun" (1 語一致) より強く引かれる
    e = m * (
        1.0
        + cfg.w_query * len(norm_words(tip) & qset)
        + cfg.w_overlap * overlap
    )
    if memory is not None:
        e += float(getattr(memory, "axis_bias", {}).get(a, 0.0))
    return e


def _perpendicular(axis: str) -> List[str]:
    """The four axes orthogonal to `axis`, in AXES order. The opposite pole
    (same letter, other sign) is exactly what this excludes."""
    return [a for a in AXES if a[1] != axis[1]]


def visible_axes(state: SearchState, section: int, cfg: ConsensusConfig) -> List[str]:
    if state.widened:
        return list(AXES)
    idx = section + state.rotation
    if cfg.geometric_visibility:
        home = AXES[idx % N_SECTIONS]
        # Own axis + the first 2*window perpendicular neighbours. Rotation
        # still changes which axis is "home", so the epistemic move survives;
        # what can never appear here is home's opposite pole.
        return [home] + _perpendicular(home)[: 2 * cfg.window]
    out: List[str] = []
    for off in range(-cfg.window, cfg.window + 1):
        a = AXES[(idx + off) % N_SECTIONS]
        if a not in out:
            out.append(a)
    return out


@dataclass
class Metrics:
    candidates: List[Optional[Tuple[str, str, float]]]  # (axis, core, energy)
    contradiction: int
    deficit: int
    agree_frac: float
    relevance: float
    agree_all: bool
    n_active: int

    def key(self) -> Tuple[float, float, float, float]:
        """Lexicographic minimization key: C, deficit, -A, -R."""
        return (
            float(self.contradiction),
            float(self.deficit),
            -round(self.agree_frac, 9),
            -round(self.relevance, 9),
        )


def evaluate(
    state: SearchState,
    qset: Set[str],
    cfg: ConsensusConfig,
    masses: Optional[Any] = None,
    memory: Optional[Any] = None,
) -> Metrics:
    shell = state.shell
    cands: List[Optional[Tuple[str, str, float]]] = []
    for i in range(N_SECTIONS):
        best: Optional[Tuple[str, str, float]] = None
        for a in visible_axes(state, i, cfg):
            tip = shell.faces[a].get(CORE_FACE)
            if tip is None:
                continue
            e = axis_energy(shell, a, qset, cfg, masses, memory)
            if best is None or e > best[2]:
                best = (a, tip, e)
        cands.append(best)

    active = [c for c in cands if c is not None]
    n_active = len(active)
    if n_active == 0:
        return Metrics(cands, 0, cfg.required_evidence, 0.0, 0.0, False, 0)

    cores = [core for _, core, _ in active]
    counts: Dict[str, int] = {}
    for c in cores:
        counts[c] = counts.get(c, 0) + 1
    agree_frac = max(counts.values()) / n_active
    agree_all = len(counts) == 1 and n_active >= cfg.min_sections

    evidenced_cores = {
        core
        for a, core, _ in active
        if len(facts_on_axis(shell, a)) >= cfg.required_evidence
    }
    contradiction = max(0, len(evidenced_cores) - 1)

    e_min = min(len(facts_on_axis(shell, a)) for a, _, _ in active)
    deficit = max(0, cfg.required_evidence - e_min)
    relevance = sum(e for _, _, e in active)
    return Metrics(cands, contradiction, deficit, agree_frac, relevance, agree_all, n_active)


def _enumerate_moves(state: SearchState) -> List[Tuple[str, Any]]:
    """Deterministic move order: rotations then unlocked arm swaps."""
    moves: List[Tuple[str, Any]] = [("rotate", d) for d in range(1, N_SECTIONS)]
    for i, a in enumerate(AXES):
        for b in AXES[i + 1:]:
            if a in state.locks or b in state.locks:
                continue
            if (
                state.shell.faces[a].get(CORE_FACE) is None
                and state.shell.faces[b].get(CORE_FACE) is None
            ):
                continue
            moves.append(("swap", (a, b)))
    return moves


def _apply_move(state: SearchState, move: Tuple[str, Any]) -> SearchState:
    kind, arg = move
    if kind == "rotate":
        return SearchState(
            shell=state.shell,
            rotation=(state.rotation + int(arg)) % N_SECTIONS,
            widened=state.widened,
            locks=set(state.locks),
        )
    a, b = arg
    shell = copy_shell(state.shell)
    shell.faces[a], shell.faces[b] = shell.faces[b], shell.faces[a]
    shell.reflections[a], shell.reflections[b] = (
        shell.reflections[b],
        shell.reflections[a],
    )
    return SearchState(
        shell=shell,
        rotation=state.rotation,
        widened=state.widened,
        locks=set(state.locks),
    )


def global_hypotheses(
    shell: ShellCross,
    qset: Set[str],
    cfg: ConsensusConfig,
    masses: Optional[Any] = None,
    memory: Optional[Any] = None,
) -> List[Tuple[str, str, float]]:
    """Evidenced (axis, core, energy) across the whole cross, energy-desc."""
    out: List[Tuple[str, str, float]] = []
    for a in AXES:
        tip = shell.faces[a].get(CORE_FACE)
        if tip is None:
            continue
        if len(facts_on_axis(shell, a)) < cfg.required_evidence:
            continue
        out.append((a, tip, axis_energy(shell, a, qset, cfg, masses, memory)))
    out.sort(key=lambda t: (-t[2], AXES.index(t[0])))
    return out


def settled_axes(shell: ShellCross, store: Any, core: Optional[str]) -> List[str]:
    """ロックしてよい軸 — 恣意的な同点崩しで勝っていない軸だけ。

    構想(これまで.pdf)は「軸のロック」で時間の短縮と精度を得ると言うが、
    **何を根拠にロックするか**は書いていない。この製品の線から導出する:
    配置は情報を増やせないのだから、**同点崩しで勝った腕はロックできない**。

    条件は二つ、どちらも既に計算されている値で決まる(新しい判断を足さない):
      ① その腕の core が配置不変(呼び出し側が確認済みであること)
      ② その腕の facet の counts が割れている(= ranked、同点ではない)
    満たさない腕はロックしない — **未ロックは一級の状態**。
    """
    if not core:
        return []
    axis = find_core_axis(shell, core)
    if axis is None:
        return []
    cross = {}
    try:
        cross = store.crosses.get(str(core).casefold().strip()) or {}
    except Exception:
        return []
    facets = [f for f in facts_on_axis(shell, axis) if f in cross]
    if len(facets) < 2:
        return []
    counts = {cross[f] for f in facets}
    return [axis] if len(counts) > 1 else []


def compose_answer(shell: ShellCross, core: str) -> Tuple[str, List[str]]:
    axis = find_core_axis(shell, core)
    if axis is None:
        return "", []
    toks: List[str] = []
    for f in FACET_READ_ORDER:
        t = shell.faces[axis].get(f)
        if t is not None:
            toks.append(t)
    return " ".join(toks), toks


@dataclass
class ConsensusResult:
    verdict: str
    core: Optional[str]
    text: str
    tokens: List[str]
    agree_frac: float
    e_min: int
    contradiction: int
    moves_used: int
    escape_used: bool
    accepted_moves: List[Dict[str, Any]]
    sections: List[Optional[Dict[str, Any]]]
    hypotheses: List[Dict[str, Any]]
    local_stable: bool
    state: Optional[SearchState] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "core": self.core,
            "text": self.text,
            "tokens": list(self.tokens),
            "agree_frac": round(self.agree_frac, 6),
            "e_min": self.e_min,
            "contradiction": self.contradiction,
            "moves_used": self.moves_used,
            "escape_used": self.escape_used,
            "accepted_moves": list(self.accepted_moves),
            "sections": list(self.sections),
            "hypotheses": list(self.hypotheses),
            "local_stable": self.local_stable,
            # The terminal arrangement, exported so a conversation can hand
            # it back as seed_state. Absent state (no search ran) is absent,
            # not zeros — a caller must not mistake "never searched" for
            # "searched and settled at the origin".
            "carry_state": ({
                "rotation": self.state.rotation,
                "widened": self.state.widened,
                "locks": sorted(self.state.locks),
            } if self.state is not None else None),
        }


def _sections_dump(m: Metrics) -> List[Optional[Dict[str, Any]]]:
    out: List[Optional[Dict[str, Any]]] = []
    for c in m.candidates:
        if c is None:
            out.append(None)
        else:
            a, core, e = c
            out.append({"axis": a, "core": core, "energy": round(e, 6)})
    return out


def run_consensus(
    shell: ShellCross,
    query: str,
    *,
    cfg: Optional[ConsensusConfig] = None,
    masses: Optional[Any] = None,
    memory: Optional[Any] = None,
    initial_locks: Optional[Sequence[str]] = None,
    mutate: bool = False,
    qset_override: Optional[Set[str]] = None,
    seed_state: Optional[Dict[str, Any]] = None,
) -> ConsensusResult:
    """Run the multi-frontier consensus search on one shell.

    Deterministic: same shell + query + config → same verdict, text, trace.
    ``qset_override`` lets non-English decomposers (e.g. Japanese script
    runs) supply the content-token set — the gates are language-agnostic.
    """
    cfg = cfg or ConsensusConfig()
    if qset_override is not None:
        qset = set(qset_override)
    else:
        qset, _head = query_content(query)
    # ── 巡回の持ち越し ────────────────────────────────────────────────
    #
    # The original conception (2026-08-16, two utterances) says the search
    # ends at a stable state where the sections agree. It never says the
    # stable state is thrown away — and until 2026-08-18 it was: every turn
    # re-entered the structure bare, and the only thread across turns was
    # last_core. 「一度構造を通ったらそのまま出てきてまた構造に入る」 is the
    # operator's exact description of that defect.
    #
    # What carries is the ARRANGEMENT — rotation, widened view, locks — and
    # deliberately not energy or tokens. Carrying the previous answer's
    # tokens into qset would be two signals in one election, the pooling
    # move measured at 6 failures out of 6 (束ねず重ねる). The structure
    # remembering how it was turned is not a second voter.
    #
    # Determinism is preserved: seed_state is an input like the query, and
    # the same (shell, query, seed) gives the same result.
    _seed = seed_state or {}
    state = SearchState(
        shell=shell if mutate else copy_shell(shell),
        rotation=int(_seed.get("rotation", 0)) % N_SECTIONS,
        widened=bool(_seed.get("widened", False)),
        locks=set(initial_locks or ()) | set(_seed.get("locks") or ()),
    )

    accepted: List[Dict[str, Any]] = []
    moves_used = 0
    escape_used = False
    verdict: Optional[str] = None
    local_stable = False

    while True:
        cur = evaluate(state, qset, cfg, masses, memory)
        cur_key = cur.key()

        # Search phase: best strictly-improving move (lexicographic).
        best_move: Optional[Tuple[str, Any]] = None
        best_key = cur_key
        best_state: Optional[SearchState] = None
        for mv in _enumerate_moves(state):
            s2 = _apply_move(state, mv)
            k2 = evaluate(s2, qset, cfg, masses, memory).key()
            if k2 < best_key:
                best_key = k2
                best_move = mv
                best_state = s2
        if best_move is not None:
            if moves_used >= cfg.max_moves:
                verdict = "UNKNOWN_BUDGET"
                break
            state = best_state  # type: ignore[assignment]
            moves_used += 1
            accepted.append(
                {"move": best_move[0], "arg": best_move[1], "key": list(best_key)}
            )
            continue

        # Local stability: every proposal rejected. Flag only — not shipping.
        local_stable = True
        if cur.n_active == 0:
            verdict = "UNKNOWN_NO_EVIDENCE"
            break
        if cur.agree_all:
            if cur.deficit > 0:
                verdict = "UNKNOWN_INSUFFICIENT_EVIDENCE"
                break
            # Query grounding: evidence must be evidence FOR THE QUERY.
            # An agreed, well-evidenced node with zero connection to a
            # non-empty query is an answer to a different question (幻覚).
            if qset:
                agreed = next(c for c in cur.candidates if c is not None)
                a_ax, a_core, _ = agreed
                facet_words: Set[str] = set()
                for f in facts_on_axis(state.shell, a_ax):
                    facet_words |= norm_words(f)
                grounded = bool(norm_words(a_core) & qset) or bool(
                    facet_words & qset
                )
                if not grounded:
                    verdict = "UNKNOWN_NO_EVIDENCE"
                    break
            hyps = global_hypotheses(state.shell, qset, cfg, masses, memory)
            if len(hyps) >= 2 and (hyps[0][2] - hyps[1][2]) <= cfg.tie_delta:
                verdict = "AMBIGUOUS"
                break
            verdict = "ANSWER"
            break
        # Disagreement at local stability: one-shot escape, then give up.
        if cfg.allow_escape and not escape_used:
            escape_used = True
            state = SearchState(
                shell=state.shell,
                rotation=state.rotation,
                widened=True,
                locks=set(),
            )
            continue
        verdict = (
            "UNKNOWN_SECTION_DISAGREEMENT" if escape_used else "UNKNOWN_LOCAL_MINIMUM"
        )
        break

    final = evaluate(state, qset, cfg, masses, memory)
    hyps = global_hypotheses(state.shell, qset, cfg, masses, memory)
    core: Optional[str] = None
    text, toks = "", []
    if verdict == "ANSWER":
        active = [c for c in final.candidates if c is not None]
        core = active[0][1]
        text, toks = compose_answer(state.shell, core)

    e_min = 0
    active = [c for c in final.candidates if c is not None]
    if active:
        e_min = min(len(facts_on_axis(state.shell, a)) for a, _, _ in active)

    return ConsensusResult(
        verdict=verdict or "UNKNOWN_LOCAL_MINIMUM",
        core=core,
        text=text,
        tokens=toks,
        agree_frac=final.agree_frac,
        e_min=e_min,
        contradiction=final.contradiction,
        moves_used=moves_used,
        escape_used=escape_used,
        accepted_moves=accepted,
        sections=_sections_dump(final),
        hypotheses=[
            {"axis": a, "core": c, "energy": round(e, 6)} for a, c, e in hyps
        ],
        local_stable=local_stable,
        state=state,
    )


# ---------------------------------------------------------------------------
# Matryoshka: upper layers resolve disagreement, not restart from scratch.
# ---------------------------------------------------------------------------

CARRY_MODES: Tuple[str, ...] = ("A", "B", "C")
# A: 常時クエリ / B: 初層限定 / C: 意図固定・内容減衰 (head only)


def carry_query(query: str, mode: str, layer: int) -> str:
    if layer == 0 or mode == "A":
        return query
    if mode == "B":
        return ""
    if mode == "C":
        _qset, head = query_content(query)
        return head or ""
    raise ValueError(f"unknown carry mode {mode!r}")


def build_handoff(result: ConsensusResult, shell: ShellCross) -> Dict[str, Any]:
    """R_h = (候補群, 各経路, 不一致点, ロック状態, 未探索領域)."""
    disagreement: Dict[str, List[int]] = {}
    cand_axes: Dict[str, str] = {}
    for i, sec in enumerate(result.sections):
        if sec is None:
            continue
        disagreement.setdefault(sec["core"], []).append(i)
        cand_axes.setdefault(sec["core"], sec["axis"])
    # AMBIGUOUS lives in the global hypotheses, not the section votes:
    # competing evidenced cores must ride along or the upper layer would
    # "resolve" the tie by simply never seeing the rival (majority-vote leak).
    for h in result.hypotheses:
        disagreement.setdefault(h["core"], [])
        cand_axes.setdefault(h["core"], h["axis"])
    seen_axes = {sec["axis"] for sec in result.sections if sec is not None}
    return {
        "verdict": result.verdict,
        "candidates": [
            {"core": c, "axis": cand_axes[c], "sections": secs}
            for c, secs in disagreement.items()
        ],
        "disagreement_map": disagreement,
        "locks": sorted(result.state.locks) if result.state else [],
        "unexplored_axes": [a for a in AXES if a not in seen_axes],
    }


def build_upper_shell(lower: ShellCross, handoff: Dict[str, Any]) -> ShellCross:
    """Replicate only the competing candidate arms onto a fresh upper cross."""
    upper = ShellCross()
    free = list(AXES)
    for cand in handoff["candidates"]:
        src = cand["axis"]
        if not free:
            break
        dst = free.pop(0)
        upper.faces[dst] = dict(lower.faces[src])
        upper.reflections[dst] = lower.reflections.get(src)
    return upper


def matryoshka_consensus(
    shell: ShellCross,
    query: str,
    *,
    carry: str = "A",
    n_layers: int = 3,
    cfg_layer0: Optional[ConsensusConfig] = None,
    cfg_upper: Optional[ConsensusConfig] = None,
    masses: Optional[Any] = None,
    memory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Layered consensus: unresolved disagreement is handed upward.

    Upper layers get only the competing arms + a carry-mode query; their job
    is resolving the disagreement map, not rebuilding the answer from zero.
    Final layer without agreement → typed UNKNOWN (never majority vote).
    """
    if carry not in CARRY_MODES:
        raise ValueError(f"carry must be one of {CARRY_MODES}")
    cfg0 = cfg_layer0 or ConsensusConfig(allow_escape=False)
    cfgU = cfg_upper or ConsensusConfig(window=N_SECTIONS, allow_escape=True)

    layers: List[Dict[str, Any]] = []
    cur_shell = shell
    res = run_consensus(
        cur_shell, carry_query(query, carry, 0), cfg=cfg0,
        masses=masses, memory=memory,
    )
    layers.append({"layer": 0, "query": carry_query(query, carry, 0), **res.as_dict()})

    h = 0
    while res.verdict != "ANSWER" and h + 1 < n_layers:
        handoff = build_handoff(res, cur_shell)
        if not handoff["candidates"]:
            break
        cur_shell = build_upper_shell(
            res.state.shell if res.state else cur_shell, handoff
        )
        h += 1
        qh = carry_query(query, carry, h)
        res = run_consensus(
            cur_shell, qh, cfg=cfgU, masses=masses, memory=memory
        )
        layers.append(
            {"layer": h, "query": qh, "handoff": handoff, **res.as_dict()}
        )

    return {
        "verdict": res.verdict,
        "core": res.core,
        "text": res.text,
        "carry": carry,
        "resolved_at": h if res.verdict == "ANSWER" else None,
        "n_layers_run": h + 1,
        "layers": layers,
    }
