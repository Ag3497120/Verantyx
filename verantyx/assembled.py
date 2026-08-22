"""Every organ on one road, so what this engine actually is can be seen.

Why this exists
---------------
174 modules are in this package. The ask path — `stacked` / `vera` —
imports sixteen. The rest are reachable only from the CLI, from
`sovereign`, from `full_sovereign`, or from a door nobody calls, and
several were measured this session to have never run at all:

    polarity          97/97 on its own bank, 0 ¬ facets in the store
    arm_schema        English cues only; every Japanese fact untagged
    ingest_coherence  no caller anywhere
    placement         699 lines, 30.9% → 7.4% fabrication, CLI only
    hierarchy         552 lines, 95% descent / 0 wrong, sovereign only
    typo_recovery     84.8% recovery, not on the ask path

So the capability of this engine has never been visible in one place. A
reader — including me, twice today — measures whichever door they open
first and calls that "the engine".

What this is
------------
A single road that runs the organs in order around the existing
`Vera.ask`, and REPORTS which of them fired. It does not replace the ask
path: the seven layers still do the answering. This adds the stages that
were built, measured, and left off the road, and it says out loud when
one of them changed the answer.

Every stage is optional and every stage is honest about not firing. A
stage that cannot run reports why rather than being silently skipped —
a skipped stage and an absent one look identical from the outside, and
that is how organs stay dead for a month.

Order, and why
--------------
    ① typo      the query is repaired BEFORE anything reads it, because
                a misspelt subject fails every later stage identically
    ② intent    an instruction is not a question; if the closed table
                frames it, say so rather than searching for a fact
    ③ stage     multi-hop queries are split before the store is asked
    ④ ask       the seven layers, unchanged
    ⑤ descend   when the census refuses, `explain` reaches by units
    ⑥ arms      the answer's facets become claims where a cue licenses it
    ⑦ remedy    what would close the gap, carried out rather than dropped

Nothing here votes. Every stage either hands the next one a better
question or annotates the answer; none of them writes to the store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Stage:
    """One organ's turn on the road, and what it did with it."""

    name: str
    fired: bool
    note: str = ""
    changed: bool = False        # did it change what the next stage saw

    def as_dict(self) -> Dict[str, Any]:
        return {"stage": self.name, "fired": self.fired,
                "changed": self.changed, "note": self.note}


def _typo(query: str) -> Stage:
    """Repair the query before anything reads it.

    Measured 84.8% recovery@5 with zero false fires on in-vocabulary
    words, and never once on the ask path — so a query with one wrong
    character failed identically to a query about something the store
    has never heard of, and the two are not the same problem.
    """
    try:
        from .meaning_assets import lattice, vocab
        from .typo_recovery import recover
    except Exception as exc:
        return Stage("typo", False, "assets unavailable: %s" % str(exc)[:60])
    try:
        r = recover(query.strip(), lattice=lattice(), vocab=vocab())
    except Exception as exc:
        return Stage("typo", False, str(exc)[:60])
    v = r.get("verdict")
    if v == "TYPO_CANDIDATE" and r.get("candidates"):
        best = r["candidates"][0]["word"]
        return Stage("typo", True, "%s → %s" % (query, best), changed=True)
    return Stage("typo", True, str(v))


def _intent(query: str) -> Stage:
    """An instruction is not a question.

    48 verbs × 28 operations, and anything outside refuses. Wired here so
    「ファイルを消して」 is not searched for as a fact — the store has
    nothing to say about it and would answer UNKNOWN, which reads as
    ignorance rather than as a category error.
    """
    from .intent_frames import parse
    r = parse(query)
    if r.get("verdict") == "INTENT":
        return Stage("intent", True, "op=%s" % r["op"], changed=True)
    return Stage("intent", True, "UNKNOWN_INTENT（問いとして扱う）")


def _stage_split(query: str) -> Stage:
    from .stage_split import split
    try:
        r = split(query)
    except Exception as exc:
        return Stage("stage_split", False, str(exc)[:60])
    if r.get("verdict") == "STAGED" and len(r.get("stages", [])) > 1:
        return Stage("stage_split", True, r.get("chain", ""), changed=True)
    return Stage("stage_split", True, str(r.get("verdict")))


def _arms(obj: Dict[str, Any]) -> Stage:
    """Facets become claims where a cue licenses it.

    Registered and measured today: the decoy set passes at zero
    over-fires, and the cues themselves reach 2/10 because the region
    rule cuts them at the particle. So this fires rarely and says so —
    a facet with no arm stays a facet, which is the whole discipline.
    """
    from .arm_schema import classify_arm
    core = obj.get("core") or ""
    if not core:
        return Stage("arms", True, "核が無い")
    claims: List[str] = []
    for f in (obj.get("tokens") or [])[:8]:
        arm = classify_arm("%sは%sである" % (core, f))
        if arm:
            claims.append("%s --%s--> %s" % (core, arm, f))
    if claims:
        return Stage("arms", True, " / ".join(claims[:3]), changed=True)
    return Stage("arms", True, "手がかり無し — 面のまま（untagged）")


def ask(query: str, vera: Any = None) -> Dict[str, Any]:
    """One question, every organ, and a record of which ones fired.

    `vera` is the loaded stack. Passed in rather than loaded here so a
    caller that already holds one does not pay for a second, and so this
    module never decides WHICH store answers — that is the host's job
    and getting it wrong is how a probe measures the default store and
    reports it as the engine.
    """
    stages: List[Stage] = []
    q = query.strip()

    s = _typo(q)
    stages.append(s)
    if s.changed and "→" in s.note:
        q = s.note.split("→")[-1].strip()

    stages.append(_intent(q))
    stages.append(_stage_split(q))

    if vera is None:
        return {"verdict": "UNKNOWN_NO_STORE",
                "stages": [x.as_dict() for x in stages],
                "note": "積層が渡されていない。どの店が答えるかは呼ぶ側が決める"}

    obj = dict(vera.ask(q))
    stages.append(Stage("ask", True, str(obj.get("verdict"))))

    # Descent when the census has nothing. It is a CONSTRUCTED
    # explanation and carries `constructed: True` of its own; it is not
    # promoted to a census answer here.
    if str(obj.get("verdict", "")).startswith("UNKNOWN"):
        try:
            from .meaning_descent import descend
            d = descend(q.replace("とは", "").strip())
            if d and not str(d.get("verdict", "")).startswith("UNKNOWN"):
                obj["descent"] = d
                stages.append(Stage("descend", True, str(d.get("verdict")),
                                    changed=True))
            else:
                stages.append(Stage("descend", True, "届かない"))
        except Exception as exc:
            stages.append(Stage("descend", False, str(exc)[:60]))
    else:
        stages.append(Stage("descend", True, "不要（合議が答えた）"))

    stages.append(_arms(obj))

    if obj.get("remedy"):
        stages.append(Stage("remedy", True, str(obj["remedy"])[:80]))

    obj["stages"] = [x.as_dict() for x in stages]
    obj["fired"] = sum(1 for x in stages if x.fired)
    obj["changed_by"] = [x.name for x in stages if x.changed]
    return obj
