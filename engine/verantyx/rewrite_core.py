"""Term rewriting — the generalisation of procedure_exec's closed instruction
set, with the arithmetic moved OUT of the interpreter and INTO rule data.

Why this exists. `procedure_exec.ALLOWED_OPS` is four instructions —
`read_digit`, `add_with_carry`, `write_digit`, `check_overflow` — and the
arithmetic lives inside the interpreter. Every new capability (subtraction,
multiplication, algebra) would need new instructions, and a closed set that
grows per capability is not closed. Here the interpreter knows exactly four
operations of a different kind:

    match(pattern, term)      -> bindings | None
    substitute(term, binds)   -> term
    rewrite(term, rule)       -> term' | None      (leftmost-innermost)
    normalize(term, rules)    -> normal form, or a typed UNKNOWN

and knows NOTHING about digits. Digit addition becomes a *rule set* — plain
data, generated deterministically, inspectable, quarantinable through the
same propose/accept gate as everything else. The gate that makes this real
rather than aspirational is `rewrite_eval`'s regression: the rule-set version
must agree with `wire_add` verdict-for-verdict and value-for-value, including
the overflow cases, over the whole product of test values. Same standard Q3
held `procedure_exec` to.

Termination, honestly. General rewriting does not terminate, and deciding
termination is not possible in general (Knuth-Bendix completion exists
precisely because this is hard). Two defences, stated plainly:

  - Orientation check at registration: a rule whose right side cannot be
    shown smaller than its left (by the size measure below) is flagged
    `oriented=False`. The flag is honest metadata, not a guarantee.
  - A step budget on `normalize`. Exhausting it returns UNKNOWN_BUDGET —
    the same typed verdict the capacity-calibration loop already knows how
    to re-run, verify, and propose raising. A stuck term (no rule applies,
    not a recognised result form) returns UNKNOWN_NO_RULE with the stuck
    term attached: exactly the "missing lemma / missing rule" signal the
    GapGraph is shaped to hold.

Terms are nested tuples: ("op", child, child, ...); leaves are ints or
strings. Pattern variables are Var("name"). Nothing here imports the math
modules — the dependency points the other way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

Term = Any  # int | str | Tuple[str, Term, ...]


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Rule:
    name: str
    lhs: Term
    rhs: Term
    #: True when the size measure strictly decreases lhs -> rhs for every
    #: instantiation — sufficient for termination of this rule alone, not of
    #: the system. False does not mean wrong; it means unproven.
    oriented: bool = True


def term_size(t: Term) -> int:
    """Nodes in the term tree. Var counts 1, so `oriented` computed on the
    patterns is a lower bound on the instantiated decrease only when each
    variable occurs at most as often on the right as on the left — checked
    in `orient`."""
    if isinstance(t, tuple):
        return 1 + sum(term_size(c) for c in t[1:])
    return 1


def _var_counts(t: Term, out: Dict[str, int]) -> None:
    if isinstance(t, Var):
        out[t.name] = out.get(t.name, 0) + 1
    elif isinstance(t, tuple):
        for c in t[1:]:
            _var_counts(c, out)


def orient(lhs: Term, rhs: Term) -> bool:
    """Is rhs provably smaller than lhs for every instantiation?

    Sufficient condition, deliberately conservative: pattern size strictly
    decreases AND no variable occurs more often on the right than the left
    (a duplicated variable can blow the instantiated size past any pattern-
    level accounting)."""
    lv: Dict[str, int] = {}
    rv: Dict[str, int] = {}
    _var_counts(lhs, lv)
    _var_counts(rhs, rv)
    if any(rv.get(k, 0) > lv.get(k, 0) for k in set(lv) | set(rv)):
        return False
    return term_size(rhs) < term_size(lhs)


def make_rule(name: str, lhs: Term, rhs: Term) -> Rule:
    return Rule(name=name, lhs=lhs, rhs=rhs, oriented=orient(lhs, rhs))


# ---------------------------------------------------------------------------
# The four operations.
# ---------------------------------------------------------------------------

def match(pattern: Term, term: Term,
          binds: Optional[Dict[str, Term]] = None) -> Optional[Dict[str, Term]]:
    """Structural match; a Var binds once and must agree on re-occurrence."""
    if binds is None:
        binds = {}
    if isinstance(pattern, Var):
        if pattern.name in binds:
            return binds if binds[pattern.name] == term else None
        out = dict(binds)
        out[pattern.name] = term
        return out
    if isinstance(pattern, tuple):
        if (not isinstance(term, tuple) or len(term) != len(pattern)
                or term[0] != pattern[0]):
            return None
        for p, t in zip(pattern[1:], term[1:]):
            binds = match(p, t, binds)
            if binds is None:
                return None
        return binds
    return binds if pattern == term else None


def substitute(term: Term, binds: Dict[str, Term]) -> Term:
    if isinstance(term, Var):
        if term.name not in binds:
            raise ValueError(f"unbound variable in rhs: {term.name}")
        return binds[term.name]
    if isinstance(term, tuple):
        return (term[0],) + tuple(substitute(c, binds) for c in term[1:])
    return term


def rewrite(term: Term, rules: List[Rule]) -> Optional[Tuple[Term, str]]:
    """One leftmost-innermost step. Returns (new_term, rule_name) or None.

    Innermost first, so arguments are normal before an outer rule fires —
    the rewriting analogue of Matryoshka evaluation's "innermost bracket
    first", and the order under which a terminating rule set gives unique
    results for the rule shapes used here."""
    if isinstance(term, tuple):
        for i, child in enumerate(term[1:], start=1):
            sub = rewrite(child, rules)
            if sub is not None:
                new_child, rule_name = sub
                return (term[:i] + (new_child,) + term[i + 1:], rule_name)
    for rule in rules:
        binds = match(rule.lhs, term)
        if binds is not None:
            return substitute(rule.rhs, binds), rule.name
    return None


@dataclass
class NormalizeResult:
    verdict: str            # ANSWER | UNKNOWN_BUDGET | UNKNOWN_NO_RULE
    term: Term              # normal form, or the term where work stopped
    steps: int
    trace: List[str] = field(default_factory=list)
    reason: str = ""


def normalize(term: Term, rules: List[Rule], budget: int = 2000,
              is_result: Optional[Any] = None) -> NormalizeResult:
    """Rewrite to a fixed point within `budget` steps.

    `is_result(term) -> bool` names the shapes that count as finished. A
    fixed point that is NOT a result form is a stuck term: some rule is
    missing, and that is a different failure from running out of budget —
    UNKNOWN_NO_RULE carries the stuck term so the gap is inspectable,
    UNKNOWN_BUDGET is the capacity loop's business."""
    trace: List[str] = []
    steps = 0
    current = term
    while steps < budget:
        step = rewrite(current, rules)
        if step is None:
            if is_result is None or is_result(current):
                return NormalizeResult("ANSWER", current, steps, trace)
            return NormalizeResult(
                "UNKNOWN_NO_RULE", current, steps, trace,
                reason=f"no rule applies to non-result term: {current!r:.120}")
        current, rule_name = step
        trace.append(rule_name)
        steps += 1
    return NormalizeResult(
        "UNKNOWN_BUDGET", current, steps, trace,
        reason=f"budget({budget})_exhausted")
