"""What approving a proposal would actually do — measured, before approving.

The problem with a quarantine
-----------------------------
`list_pending_*` shows a candidate and a button. Nothing on that screen
says what the row means, why it was proposed, or what changes if it goes
in. A person asked to approve under those conditions is not exercising
judgement — they are rubber-stamping, and a rubber stamp turns the gate
into a formality while keeping all of its cost.

So a proposal must arrive with a prospectus, and the prospectus must be
measured rather than described. For a table addition this is entirely
computable: run the refusal log with the row and without it, and show the
person the two lists that differ.

    「見る → READ を足しますか」          ← unanswerable
    「足すと、拒否ログの12件が通ります。    ← readable
      内訳はこれです。既に通っている
      143件は一件も変わりません」

What Vera may and may not say here
----------------------------------
It reports EFFECTS, never verdicts. Whether 「見る」 belongs on READ
rather than CHECK is a question about meaning, and meaning is where this
engine measures 4% — so it says which sentences change and hands the
judgement to the person, who is the one who knows what they meant.

The regression half is the half that matters
--------------------------------------------
"12 more sentences parse" is the easy number and the wrong one to trust
alone. A loosened table always parses more; the question is whether
anything that ALREADY parsed now parses differently, and whether things
that SHOULD refuse have started passing. Both lists are produced, and the
second is printed first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import intent_frames


@dataclass(frozen=True)
class VerbProposal:
    """One row for the closed verb table, with what motivated it."""

    dict_form: str
    op: str
    conj_class: str
    #: The refused inputs that led here. Evidence, not decoration: a row
    #: nobody's instruction asked for is speculative table growth.
    because: Tuple[str, ...] = ()

    @property
    def row(self) -> Tuple[str, str, str]:
        return (self.dict_form, self.op, self.conj_class)


def _parse_with(rows: Sequence[Tuple[str, str, str]],
                texts: Sequence[str]) -> Dict[str, Any]:
    """Parse a corpus against a temporarily modified verb table.

    Global state is restored in `finally`, unconditionally. A measurement
    tool that can leave the engine's own table altered is a worse problem
    than the one it was measuring.
    """
    saved_verbs = intent_frames.VERBS
    saved_conj = intent_frames.CONJ_TABLE
    saved_forms = intent_frames.CONJ_FORMS
    try:
        intent_frames.VERBS = tuple(rows)
        intent_frames.CONJ_TABLE, intent_frames.CONJ_FORMS = \
            intent_frames._build_conj()
        return {t: intent_frames.parse(t) for t in texts}
    finally:
        intent_frames.VERBS = saved_verbs
        intent_frames.CONJ_TABLE = saved_conj
        intent_frames.CONJ_FORMS = saved_forms


def prospectus(p: VerbProposal,
               refused: Sequence[str],
               already_parsing: Sequence[str] = ()) -> Dict[str, Any]:
    """What changes if this row is approved. Two lists, regressions first.

    ``refused`` is the refusal log — inputs that currently answer
    UNKNOWN_INTENT. ``already_parsing`` is anything known to parse today,
    used purely as a regression guard; pass the log of successful frames.
    """
    before_rows = tuple(intent_frames.VERBS)
    if p.row in before_rows:
        return {"verdict": "ALREADY_PRESENT", "row": list(p.row)}
    after_rows = before_rows + (p.row,)

    corpus = list(dict.fromkeys(list(refused) + list(already_parsing)))
    before = _parse_with(before_rows, corpus)
    after = _parse_with(after_rows, corpus)

    newly, changed = [], []
    for t in corpus:
        b, a = before[t], after[t]
        if b == a:
            continue
        if b.get("verdict") != "INTENT" and a.get("verdict") == "INTENT":
            newly.append({"text": t, "now": {"op": a["op"], "args": a["args"]}})
        else:
            changed.append({"text": t, "before": b, "after": a})

    return {
        "verdict": "PROSPECTUS",
        "row": list(p.row),
        "because": list(p.because),
        "writes": "閉じた動詞表に 1 行。%s → %s（%s活用）"
                  % (p.dict_form, p.op, p.conj_class),
        # Printed first on purpose. A proposal is judged by what it breaks,
        # not by what it enables.
        "regressions": changed,
        "newly_parsed": newly,
        "counts": {"corpus": len(corpus), "newly_parsed": len(newly),
                   "regressions": len(changed),
                   "table": "%d → %d 行" % (len(before_rows), len(after_rows))},
        "reversible": "行を取り除けば完全に元へ戻る。事実は書かれない。",
        "vera_does_not_judge": "「見る」が READ か CHECK かは語義の問い。"
                               "この基盤の語義判定は 4% なので、判断はしない。"
                               "変わる文だけを出す。",
    }


def render(pr: Dict[str, Any]) -> str:
    """The prospectus as the person reads it before pressing anything."""
    if pr.get("verdict") != "PROSPECTUS":
        return str(pr)
    L = ["提案: %s" % pr["writes"],
         "  取り消し: %s" % pr["reversible"]]
    if pr["because"]:
        L.append("  根拠となった拒否: " + " / ".join(pr["because"][:3])
                 + (" ほか%d件" % (len(pr["because"]) - 3)
                    if len(pr["because"]) > 3 else ""))
    L.append("")
    c = pr["counts"]
    L.append("■ 壊れるもの: %d 件" % c["regressions"])
    for r in pr["regressions"][:8]:
        L.append("    %s" % r["text"])
        L.append("      前: %s" % r["before"])
        L.append("      後: %s" % r["after"])
    if not pr["regressions"]:
        L.append("    （既に通っている文は一件も変わらない）")
    L.append("")
    L.append("■ 新たに通るもの: %d 件" % c["newly_parsed"])
    for n in pr["newly_parsed"][:12]:
        L.append("    %-28s → %s %s" % (n["text"], n["now"]["op"], n["now"]["args"]))
    L.append("")
    L.append("■ 表: %s ／ 検査した文: %d" % (c["table"], c["corpus"]))
    L.append("■ Vera は良し悪しを言いません: %s" % pr["vera_does_not_judge"])
    return "\n".join(L)
