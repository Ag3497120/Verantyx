"""Does a field report reach a verdict someone can act on — or safely not?

The measurement that produced this module: ten realistic resident postings
(「ここ給水やってる」「水もうないです」) yielded a usable state in ZERO of
them, because the engine reads formal announcements and residents do not
write formally. This suite pins the design answer — statuses are chosen,
not written — and the verdicts that make a chosen status worth trusting.

The asymmetry every case here is built around: a wrong "usable" sends
someone carrying a baby two kilometres to a closed door. A wrong "we
cannot say" costs them one phone call. So the suite is strict about
EXPIRED and CONFLICT never being softened into a usable answer, and
relaxed about the reverse.

Run:  python3 -m verantyx.field_reports_eval
"""
from __future__ import annotations

import sys
from typing import List

from .field_reports import (CATEGORIES, NEEDS, USABLE, Report, assess,
                            for_needs, validate)

NOW = 1000


def corpus() -> List[Report]:
    return [
        Report("給水所A", "water", "available", NOW - 20, "住民1"),
        Report("給水所A", "water", "available", NOW - 15, "住民2"),
        Report("給水所B", "water", "available", NOW - 10, "市公式", official=True),
        Report("給水所B", "water", "out", NOW - 5, "住民3", note="3時前に終了"),
        Report("スーパーC", "food", "open", NOW - 240, "住民4"),
        Report("避難所D", "shelter", "open", NOW - 600, "市公式", official=True),
        Report("トイレE", "toilet", "unusable", NOW - 500, "住民5"),
        Report("トイレE", "toilet", "usable", NOW - 30, "住民6"),
    ]


def main() -> int:
    print(f"field reports — {len(CATEGORIES)} categories, {len(NEEDS)} needs\n")
    failures: List[str] = []
    R = corpus()

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"[{'ok  ' if ok else 'FAIL'}] {label}{('  — ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    # -- The verdicts -------------------------------------------------------
    a = assess(R, NOW, "給水所A", "water")
    check("two reporters agreeing recently is CONFIRMED",
          a.verdict == "CONFIRMED" and a.usable is True, a.verdict)

    b = assess(R, NOW, "給水所B", "water")
    check("fresh disagreement is CONFLICT, and usable is left unset",
          b.verdict == "CONFLICT" and b.usable is None, b.verdict)
    # An official page saying open while someone standing there says closed
    # is the disagreement most worth showing. Preferring the official source
    # would delete exactly the report that walked to the place.
    official_side = [s for s in b.sides if s.get("official")]
    check("the official source is a side, not the answer",
          len(official_side) == 1 and len(b.sides) == 2,
          f"{len(b.sides)} sides")

    c = assess(R, NOW, "スーパーC", "food")
    check("nothing within the TTL is EXPIRED, not 'closed'",
          c.verdict == "EXPIRED" and c.usable is None, c.verdict)
    check("EXPIRED says how old and how stale is too stale",
          "240" in c.reason and str(CATEGORIES["food"]["ttl"]) in c.reason)

    d = assess(R, NOW, "避難所D", "shelter")
    check("a 10-hour-old shelter report is still current (TTL 1440)",
          d.verdict == "REPORTED" and d.usable is True, d.verdict)

    e = assess(R, NOW, "トイレE", "toilet")
    check("a newer report supersedes an older opposite one",
          e.verdict == "REPORTED" and e.status == "usable"
          and any(s["status"] == "unusable" for s in e.superseded), e.status)

    z = assess(R, NOW, "給水所Z", "water")
    check("never reported is UNKNOWN_NO_REPORT, distinct from EXPIRED",
          z.verdict == "UNKNOWN_NO_REPORT")

    # A single reporter is never CONFIRMED. One person can be wrong, or can
    # have been looking at the wrong entrance.
    single = [Report("X", "water", "available", NOW - 5, "住民1"),
              Report("X", "water", "available", NOW - 3, "住民1")]
    s1 = assess(single, NOW, "X", "water")
    check("the same reporter twice is still REPORTED, not CONFIRMED",
          s1.verdict == "REPORTED", s1.verdict)

    # Two stale reports agreeing are not agreement about now.
    old = [Report("Y", "water", "available", NOW - 500, "住民1"),
           Report("Y", "water", "available", NOW - 480, "住民2")]
    s2 = assess(old, NOW, "Y", "water")
    check("two stale agreeing reports are EXPIRED, not CONFIRMED",
          s2.verdict == "EXPIRED", s2.verdict)
    print()

    # -- Chosen statuses, never written ------------------------------------
    check("a free-text status is refused with the allowed set named",
          bool(validate(Report("X", "water", "やってる", NOW))))
    check("an unknown category is refused",
          bool(validate(Report("X", "天気", "open", NOW))))
    bad = [c for c, spec in CATEGORIES.items()
           if not spec["statuses"] or not spec["ttl"]]
    check("every category has a closed status set and a TTL", not bad, str(bad))
    unknown_status = [(c, s) for c, spec in CATEGORIES.items()
                      for s in spec["statuses"]
                      if s not in USABLE and s not in
                      {"out", "closed", "unusable", "unavailable", "ended", "full"}]
    check("every status is classified usable or not", not unknown_status,
          str(unknown_status))
    print()

    # -- Needs, not identities ---------------------------------------------
    rows = for_needs(R, NOW, ["water", "toilet"])
    # Four, not three: the "water" need reaches the food category too,
    # because a shop that is open is somewhere to get water. The first
    # version of this assertion expected three and was wrong about the
    # design rather than finding a bug in it — needs deliberately fan out
    # to every category that could answer them.
    cats = {r["category"] for r in rows}
    check("need-based selection fans out to every category that answers it",
          cats == {"water", "food", "toilet"}, str(sorted(cats)))
    check("usable findings sort ahead of conflicts and expired ones",
          rows[0]["verdict"] in ("CONFIRMED", "REPORTED")
          and rows[-1]["verdict"] in ("EXPIRED", "UNKNOWN_NO_REPORT"),
          rows[0]["verdict"] + " … " + rows[-1]["verdict"])
    # Nothing is filtered out. Someone may still choose to walk to a place
    # whose status expired; a person shown only usable places never learns
    # it exists.
    check("conflicted and expired places are still listed, not hidden",
          any(r["verdict"] == "CONFLICT" for r in rows)
          and any(r["verdict"] == "EXPIRED" for r in for_needs(R, NOW, ["food"])))

    # The needs table must not key on who someone is. Grepping the labels
    # for identity words is crude, and it is the kind of thing that gets
    # added later by someone who means well.
    identity = ["高齢", "障害", "子育て", "世帯", "elderly", "disabled",
                "単身", "独居"]
    leaked = [k for k, v in NEEDS.items()
              if any(w in v["ja"] or w in v["en"] for w in identity)]
    check("needs are phrased as needs, never as who the person is",
          not leaked, str(leaked))
    print()

    # -- No confidence scores ----------------------------------------------
    # A number invites a reader to treat it as permission. Every finding is
    # a named verdict plus an age, and that is deliberate.
    numeric = [k for k in a.as_dict()
               if k in ("confidence", "score", "probability", "trust")]
    check("findings carry a verdict and an age, never a confidence score",
          not numeric, str(numeric))
    print()

    # -- Corpus suitability -------------------------------------------------
    # Three real 内閣府 corpora — 6 portal pages, 2 case-study PDFs, and two
    # revisions of one guideline — all returned zero contradictions, and the
    # reason is the same in each: zero opposable pairs. Guidance documents
    # do not contradict each other. A revision ADDS (令和6 held 使用可能 for
    # トイレ where 令和4 held nothing) rather than reversing. Reporting a
    # zero without this number invites the reader to credit a detector that
    # never had the chance to fire.
    import tempfile as _tf
    from pathlib import Path as _P
    from .corpus_audit import audit as _audit, worksheet as _ws
    with _tf.TemporaryDirectory() as td:
        r = _P(td)
        (r / "A.txt").write_text("国道4号は通行止です。避難所は開設されました。",
                                 encoding="utf-8")
        (r / "B.txt").write_text("国道4号は通行可能です。避難所は閉鎖されました。",
                                 encoding="utf-8")
        a = _audit([str(r / "A.txt"), str(r / "B.txt")])
        ok = a.opposable_pairs == 2 and a.corpus_kind == "descriptive" \
            and len(a.detections) == 2
        check("a corpus that does disagree reports opposable pairs and finds them",
              ok, f"{a.opposable_pairs} pairs, {len(a.detections)} found")

        (r / "C.txt").write_text("トイレの確保は重要です。実施してください。",
                                 encoding="utf-8")
        g = _audit([str(r / "C.txt")])
        ok = g.opposable_pairs == 0 and g.corpus_kind != "descriptive"
        check("a single-source corpus reports zero opposable pairs", ok,
              g.corpus_kind)
        ok = "精度は測れません" in _ws(g) or "No precision" in _ws(g)
        check("the worksheet refuses to imply precision from an unopposable zero",
              ok)
    print()

    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        return 1
    print("chosen statuses reach typed verdicts; stale never reads as usable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
