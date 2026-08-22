"""Read documents, prove a defect, repair it, and keep the repair — alone.

This is the loop the project has been walking toward, and it is worth being
exact about which part is new, because three of the four steps already worked.

    generation   `self_audit` raises gaps from structure, no reader needed.
    synthesis    `rule_synthesis` derives a candidate from examples.
    measurement  `verify` re-runs every corpus and the planted suite.
    ACCEPTANCE   — was a person's, always, because nothing inside the engine
                   could say a reading was wrong.

`metamorphic` supplies the missing piece: an answer key made of the documents
themselves. Two readings of the same content that disagree prove one of them
wrong, and where the transform between them is layout — which cannot carry
information — the manufactured reading is the wrong one. No world knowledge
enters. So for THIS class of defect, and only this class, acceptance can be
mechanical, and the engine is allowed to change how it reads.

The bar it has to clear is the whole regression, not the defect it found:

    the planted suite still passes, with its own answer key
    every detection confirmed true by a person across five corpora survives
    coverage does not fall
    the count of proven defects strictly falls

A repair that clears all four is written into an overlay with the evidence
that justified it. One that fails any is rejected and recorded as rejected,
because a loop that only remembers its successes is a loop that will try the
same bad rule again next month — and `layout_space` is exactly that rule: it
proves 8 real defects on the ministry PDFs and will propose itself on every
run forever, while costing 71 sentences their core.

Nothing here touches the shipped engine. `ja_grammar.json` ships with no
normalizers at all, and an accepted repair is written to the operator's own
overlay. An installation evolves from the documents IT was given, which is
the only honest place for evidence that came from those documents.

What this does NOT make autonomous, stated plainly. The class is layout. A
vocabulary gap — a word the engine has never seen a pole for — has no internal
answer key, because no transformation of the documents can reveal what 「滞留」
means. A too-wide guard has none either. Those still route to a person through
`defect_gaps`, and the honest reading of this module is that the engine can now
repair what its own reader broke, not what it never knew.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: Where an unattended engine keeps what it changed about itself. Beside the
#: gap graph, because the two are the same story from opposite ends.
LEDGER = "evolution.jsonl"


@dataclass
class Repair:
    """One proposed change to how the engine reads, and what it cost."""

    normalizer: str
    #: "normalizer" or "suppression" — which mechanism the repair changes.
    mechanism: str = "normalizer"
    targets: List[str] = field(default_factory=list)   # proven divergences
    accepted: bool = False
    reason: str = ""
    before: Dict[str, Any] = field(default_factory=dict)
    after: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in ([], {}, "")}


def _state(paths: List[str]) -> Dict[str, Any]:
    """Everything a repair could damage, measured in one pass."""
    from .corpus_audit import audit_paths
    from .metamorphic import probe_paths, rule_conflicts

    a = audit_paths(paths)
    divs = probe_paths(paths) + rule_conflicts(paths)
    return {
        "coverage": round(a.coverage, 4),
        "claims": len(a.claims) if hasattr(a, "claims") else None,
        "detections": sorted(f"{d.topic} / {d.aspect}" for d in a.detections),
        "proven": sorted(f"{d.perturbation}/{d.kind}:{d.core}/{d.facet}"
                         for d in divs if d.proven),
    }


def _planted_holds() -> bool:
    import contextlib
    import io

    from .generalization_eval import main as _gen

    with contextlib.redirect_stdout(io.StringIO()):
        return _gen() == 0


def propose(paths: List[str], rejected: Optional[Any] = None) -> List[str]:
    """Which normalizers the documents themselves ask for.

    A normalizer is proposed only when the probe PROVED something with it —
    never because it is available. An engine that applied every transform it
    owns would be normalising on faith, which is the thing this project keeps
    refusing to do.
    """
    from .ja_grammar import NORMALIZERS
    from .metamorphic import probe_paths

    have = {n for n, _ in NORMALIZERS} | set(rejected or ())
    want: List[str] = []
    for d in probe_paths(paths):
        if (d.proven and d.kind == "manufactured"
                and d.perturbation not in have and d.perturbation not in want):
            want.append(d.perturbation)
    return want


def propose_suppressions(paths: List[str],
                         rejected: Optional[Any] = None) -> List[str]:
    """Candidate suppressions, made from the guards' own matches.

    The candidate is the exact grammar the guard matched on a conflicting
    placement — ^のため from 「復旧のため派遣された職員」 — not the guard's whole
    alternation. That keeps the linguistic judgement inside the gate: のため
    (purpose: the state has not happened) and により (cause: the state DID
    happen, and something followed from it) sit in the same guard, and a
    candidate as wide as the guard would silence presupposed real states along
    with the manufactured ones. Splitting per-match lets measurement accept
    one and reject the other, which is the whole design: the loop does not
    know Japanese, it knows what each candidate costs.
    """
    import re as _re

    from .ja_grammar import SUPPRESSIONS
    from .metamorphic import rule_conflicts

    have = ({p for p, _ in SUPPRESSIONS}
            | {r for r in (rejected or ()) if r.startswith("^")})
    out: List[str] = []
    for d in rule_conflicts(paths):
        cand = "^" + _re.escape(d.detail)
        if cand and cand not in have and cand not in out:
            out.append(cand)
    return out


def rejected_before(home: Path) -> Dict[str, str]:
    """What the ledger already measured and turned down.

    Without this the loop re-runs the whole regression on the same losing
    candidate every time somebody reads a document — and `layout_space` IS a
    losing candidate that the ministry PDFs propose on every single run,
    because the defects it proves are real even though the repair costs too
    much. Remembering the rejection is what makes an unattended loop cheap
    enough to leave running.
    """
    path = Path(home) / LEDGER
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("normalizer") and not row.get("accepted"):
            out[row["normalizer"]] = row.get("reason", "")
        elif row.get("accepted"):
            out.pop(row.get("normalizer"), None)
    return out


def attempt(name: str, paths: List[str], *, why: str = "",
            mechanism: str = "normalizer") -> Repair:
    """Apply one candidate repair, measure everything, and put it back.

    Two mechanisms, one gate. A normalizer changes what the loader hands the
    reader; a suppression is a pattern after a polar term that means the term
    asserts nothing, consulted at the placement choke point. Both are DATA,
    which is what lets an unattended loop hold them: the worst a bad candidate
    can do is what the gate measures, never arbitrary behaviour.
    """
    from . import ja_grammar as grammar

    before = _state(paths)
    prefix = ("own_rules/guard_conflict" if mechanism == "suppression"
              else f"{name}/manufactured")
    targets = [p for p in before["proven"] if p.startswith(prefix)]
    if not targets:
        return Repair(name, mechanism, [], False,
                      "it targets nothing that was proven", before, before)

    entry = (name, why or f"proved by metamorphic probe on {len(paths)} path(s)")
    bag = (grammar.SUPPRESSIONS if mechanism == "suppression"
           else grammar.NORMALIZERS)
    bag.append(entry)
    try:
        planted = _planted_holds()
        after = _state(paths)
    finally:
        if entry in bag:
            bag.remove(entry)

    # A divergence is identified by its CORE, and a repair's whole job is to
    # change the core — so comparing the two lists by name reports a repaired
    # defect as a brand new one. It did, on the first run: `counter_split` was
    # turned down for "proving 9 new divergences" that were 11店舗, 12戸 and
    # 13路線, the same three fragments it had just attached their numerals to.
    #
    # This project has now hit that in three places: a fixed window and a
    # cut-at-the-first-noun both split one defect report into three, and both
    # were fixed by keying on something that is not the text. Here the thing
    # that is not the text is the COUNT, and the gate says what it actually
    # means: fewer proven defects than before, and nothing else worse.
    lost = [d for d in before["detections"] if d not in after["detections"]]
    drop = before["coverage"] - after["coverage"]
    net = len(before["proven"]) - len(after["proven"])

    if not planted:
        return Repair(name, mechanism, targets, False,
                      "the planted suite stopped passing", before, after)
    if lost:
        return Repair(name, mechanism, targets, False,
                      f"it costs {len(lost)} confirmed detection(s): "
                      f"{', '.join(lost)}", before, after)
    if drop > 0.0001:
        return Repair(name, mechanism, targets, False,
                      f"coverage falls {drop:.2%} — {len(targets)} of those "
                      f"sentences were the spurious claims it removed, the "
                      f"rest are real", before, after)
    if net <= 0:
        return Repair(name, mechanism, targets, False,
                      f"proven defects do not fall "
                      f"({len(before['proven'])} -> {len(after['proven'])})",
                      before, after)
    return Repair(name, mechanism, targets, True,
                  f"proven defects fall {len(before['proven'])} -> "
                  f"{len(after['proven'])}, no confirmed detection is lost, "
                  f"and coverage moves {-drop:+.2%}", before, after)


def apply(repair: Repair, overlay: Path) -> Dict[str, Any]:
    """Write an accepted repair where the next run will load it.

    Refuses to write a rejected one. The check is here rather than at the call
    site because "apply whatever came back" is exactly the shortcut an
    unattended loop takes at three in the morning.
    """
    if not repair.accepted:
        raise ValueError(f"refusing to apply a rejected repair: {repair.reason}")
    key = "suppressions" if repair.mechanism == "suppression" else "normalizers"
    p = Path(overlay)
    raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    have = {tuple(x) for x in raw.get(key, [])}
    item = [repair.normalizer, repair.reason]
    if tuple(item) not in have:
        raw.setdefault(key, []).append(item)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"overlay": str(p), key: raw[key]}


def record(repair: Repair, home: Path) -> None:
    """Append to the ledger, accepted or not.

    A rejected repair is the more useful record: it is the only thing that
    stops the loop deriving the same broken rule from the same documents on
    every run, and it is what a person reads to see what the engine tried.
    """
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    line = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **repair.as_dict()}
    with (home / LEDGER).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def file_unrepaired(paths: List[str], home: Path) -> List[Dict[str, Any]]:
    """Proven defects that no accepted repair fixes go to a person — as PROVEN.

    This is the one place the loop hands work back, and the hand-off is
    stronger than anything `self_audit` could produce. A structural signal is
    a suspicion because its ranges overlap with correct output. A divergence
    is not: two readings of the same content disagree, and the transform
    between them cannot have changed the content. So these are filed CRITICAL
    with `observed_transition="proven"`, and unlike a suspected gap they are
    allowed to reach rule synthesis — the answer key is already in the store.
    """
    from .defect_gaps import SCOPE
    from .gap_graph import GapGraph, gap_graph_path
    from .metamorphic import probe_paths

    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = gap_graph_path(home / "audit.json")
    graph = GapGraph.load(path)
    filed = []
    for d in probe_paths(paths):
        if not (d.proven and d.kind == "manufactured"):
            continue
        subject = f"proven:{d.perturbation}:{d.core}/{d.facet}"
        existing = graph.find_by_scope_subject(SCOPE, subject)
        if existing is not None:
            filed.append({"status": "known", "gap_id": existing.gap_id,
                          "subject": subject})
            continue
        node = graph.create(
            gap_type="reading_defect", subject=subject, scope=SCOPE,
            severity="CRITICAL", failure_type=f"manufactured_by_{d.perturbation}",
            observed_transition="proven",
            expected_transition="no claim placed",
            blocks=[d.shape] if d.shape else [],
            caused_by=[f"probe:{d.perturbation}"],
            acquisition_methods=["human_rule"], max_depth=1)
        filed.append({"status": "created", "gap_id": node.gap_id,
                      "subject": subject})
    graph.save(path)
    return filed


def run(paths: List[str], *, home: Path, overlay: Optional[Path] = None,
        write: bool = False) -> Dict[str, Any]:
    """Probe, repair, measure, keep. The whole loop, one call, no network."""
    skip = rejected_before(home)
    out: Dict[str, Any] = {"proposed": propose(paths, skip),
                           "skipped_as_already_rejected": skip, "repairs": []}
    out["proposed_suppressions"] = propose_suppressions(paths, skip)
    from . import ja_grammar as grammar

    # Accepted repairs STACK while the loop runs: the next candidate is
    # measured against a store that already holds the previous one, or two
    # repairs that each pass alone could double-silence together unseen. But
    # the stack is unwound before returning — the overlay is the durable
    # store, and a run() that leaves module state behind would make the next
    # in-process audit measure an engine nobody configured.
    stacked: List[Tuple[Any, Tuple[str, str]]] = []
    try:
        for name, mech in ([(n, "normalizer") for n in out["proposed"]]
                           + [(c, "suppression")
                              for c in out["proposed_suppressions"]]):
            repair = attempt(name, paths, mechanism=mech)
            record(repair, home)
            row = repair.as_dict()
            if repair.accepted:
                if write and overlay is not None:
                    row["applied"] = apply(repair, Path(overlay))
                bag = (grammar.SUPPRESSIONS if mech == "suppression"
                       else grammar.NORMALIZERS)
                entry = (repair.normalizer, repair.reason)
                bag.append(entry)
                stacked.append((bag, entry))
            out["repairs"].append(row)
    finally:
        for bag, entry in stacked:
            if entry in bag:
                bag.remove(entry)
    out["accepted"] = sum(1 for r in out["repairs"] if r.get("accepted"))
    out["filed_for_a_person"] = file_unrepaired(paths, home)
    # Vocabulary grows by PROPOSAL, never by repair — the asymmetry is the
    # design and vocab_growth's docstring is the contract. The queue lands in
    # the same home directory as everything else the loop keeps.
    from .vocab_growth import propose as _vocab
    out["vocabulary"] = _vocab(paths, home=home)
    out["still_a_person's"] = (
        "Only defects with an internal answer key are repaired here. A "
        "missing word has none — no transformation of a document reveals "
        "what an unseen word means — so vocabulary candidates arrive as "
        "damage-tested proposals, and the one judgement left is whether the "
        "word really is that pole."
    )
    return out
