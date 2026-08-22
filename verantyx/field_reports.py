"""Field reports — structured status, chosen not written, and honest about age.

Measured before this existed: ten realistic resident posts
(「ここ給水やってる」「水もうないです」) produced a usable state in **zero**
of them. The engine reads formal announcements — 「給水所は開設されました」 —
and residents do not write that way. Two walls, one easy (the vocabulary is
formal) and one hard (spoken Japanese drops the topic marker, so the head
cannot be found).

The design answer is not to climb the hard wall. It is to not need it:
a status is CHOSEN from a closed set, the way イマココナビ's thirty-second
post works, so there is no free text to parse. Free text stays as a note
and is never analysed — a field the system quietly misreads is worse than
one it never touches.

Vera then does the part it is good at and nothing else:

    CONFIRMED          several reporters agree, and recently
    REPORTED           one reporter, recently
    CONFLICT           reporters disagree, both still fresh
    SUPERSEDED         an older report replaced by a newer one
    EXPIRED            nothing recent enough to stand behind
    UNKNOWN_NO_REPORT  nobody has said anything

EXPIRED is the verdict this module exists for. A stale post is more
dangerous than a missing one: 「10時に給水やってた」 still on the board three
days later sends someone walking. Staleness is per category, because a
water queue goes stale in an hour and a shelter's existence does not.

No confidence score anywhere, on purpose. "信頼度 85%" performs a precision
nobody has, and a reader takes it as permission. "Confirmed by two people
20 minutes ago; nothing since" leaves the judgement where it belongs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Category → (label ja, label en, allowed statuses, minutes before EXPIRED).
#:
#: The TTLs are the substantive judgement here, and they are judgements, so
#: they are written down rather than hidden in a constant. A queue at a water
#: point turns over in minutes; whether a shelter exists at all changes over
#: days. One global freshness window would either mark shelters stale while
#: they are fine, or leave a sold-out shop looking open — and the second
#: error is the one that makes someone walk.
CATEGORIES: Dict[str, Dict[str, Any]] = {
    "water": {"ja": "給水", "en": "Water point",
              "statuses": ["available", "queue", "out", "closed"], "ttl": 90},
    "food": {"ja": "食料・店舗", "en": "Food / shop",
             "statuses": ["open", "limited", "out", "closed"], "ttl": 120},
    "fuel": {"ja": "給油", "en": "Fuel",
             "statuses": ["available", "queue", "out", "closed"], "ttl": 90},
    "toilet": {"ja": "トイレ", "en": "Toilet",
               "statuses": ["usable", "unusable"], "ttl": 240},
    "bath": {"ja": "入浴", "en": "Bathing",
             "statuses": ["open", "closed"], "ttl": 240},
    "power": {"ja": "充電・電源", "en": "Power / charging",
              "statuses": ["available", "unavailable"], "ttl": 240},
    "medical": {"ja": "医療", "en": "Medical",
                "statuses": ["open", "closed"], "ttl": 360},
    "pharmacy": {"ja": "薬", "en": "Pharmacy",
                 "statuses": ["open", "limited", "closed"], "ttl": 360},
    "shelter": {"ja": "避難所", "en": "Shelter",
                "statuses": ["open", "full", "closed"], "ttl": 1440},
    "supplies": {"ja": "物資配布", "en": "Supply distribution",
                 "statuses": ["ongoing", "ended"], "ttl": 120},
    "road": {"ja": "道路", "en": "Road",
             "statuses": ["passable", "restricted", "closed"], "ttl": 360},
    "network": {"ja": "通信・Wi-Fi", "en": "Network / Wi-Fi",
                "statuses": ["available", "unavailable"], "ttl": 360},
    "accessible": {"ja": "バリアフリー", "en": "Step-free access",
                   "statuses": ["available", "unavailable"], "ttl": 1440},
    "infant": {"ja": "乳児用品・授乳", "en": "Infant supplies / nursing",
               "statuses": ["available", "out"], "ttl": 180},
}

#: Statuses that mean "you can use this now". Everything else does not, and
#: the distinction is per status rather than per category because "queue" is
#: usable and "out" is not, in the same place, minutes apart.
USABLE = {"available", "open", "usable", "passable", "ongoing", "queue",
          "limited", "restricted"}

#: What someone needs → which categories answer it. Deliberately keyed on
#: NEED, never on who the person is.
#:
#: Asking 「高齢者ですか」「障害がありますか」 would classify people in order to
#: help them, and that fails three ways: some will not answer, some do not
#: recognise themselves in the label (a grandparent caring for an infant is
#: not "a family with children"), and holding the answer creates a duty to
#: protect it. Needs reach the same shelves without any of that.
NEEDS: Dict[str, Dict[str, Any]] = {
    "water": {"ja": "水がほしい", "en": "I need water",
              "categories": ["water", "food"]},
    "food": {"ja": "食べ物がほしい", "en": "I need food",
             "categories": ["food", "supplies"]},
    "medicine": {"ja": "薬がほしい", "en": "I need medicine",
                 "categories": ["pharmacy", "medical"]},
    "medical": {"ja": "手当てを受けたい", "en": "I need medical care",
                "categories": ["medical"]},
    "infant": {"ja": "おむつ・ミルク・授乳", "en": "Nappies / formula / nursing",
               "categories": ["infant", "supplies", "toilet"]},
    "toilet": {"ja": "トイレを使いたい", "en": "I need a toilet",
               "categories": ["toilet"]},
    "bath": {"ja": "お風呂に入りたい", "en": "I need to bathe",
             "categories": ["bath"]},
    "power": {"ja": "充電したい", "en": "I need to charge",
              "categories": ["power", "network"]},
    "fuel": {"ja": "給油したい", "en": "I need fuel",
             "categories": ["fuel", "road"]},
    "stepfree": {"ja": "段差なしで行ける所", "en": "Step-free access",
                 "categories": ["accessible", "shelter", "toilet"]},
    "shelter": {"ja": "泊まる場所がほしい", "en": "I need somewhere to stay",
                "categories": ["shelter", "accessible"]},
    "move": {"ja": "移動したい", "en": "I need to travel",
             "categories": ["road", "fuel"]},
}


@dataclass
class Report:
    """One posting. `status` must come from the category's closed set —
    a status the poster typed freely is a status nobody can compare."""

    place: str
    category: str
    status: str
    at: int                       # minutes since an arbitrary epoch
    reporter: str = "resident"
    note: str = ""                # displayed verbatim, never parsed
    official: bool = False        # a municipal/agency posting


@dataclass
class Finding:
    place: str
    category: str
    verdict: str
    status: Optional[str] = None
    usable: Optional[bool] = None
    age_minutes: Optional[int] = None
    reporters: List[str] = field(default_factory=list)
    sides: List[Dict[str, Any]] = field(default_factory=list)
    superseded: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()
                if v not in (None, [], "")}


def validate(report: Report) -> List[str]:
    errs: List[str] = []
    spec = CATEGORIES.get(report.category)
    if spec is None:
        errs.append(f"unknown category {report.category!r}")
        return errs
    if report.status not in spec["statuses"]:
        errs.append(f"status {report.status!r} is not one of "
                    f"{spec['statuses']} for {report.category!r}")
    if not (report.place or "").strip():
        errs.append("place is empty")
    return errs


def assess(reports: List[Report], now: int,
           place: str, category: str) -> Finding:
    """What can be said about one place-and-category, right now.

    Ordering rules, and why each one is the way it is:

      * Reports older than the category's TTL do not vote. They are kept for
        the SUPERSEDED trail but cannot make something CONFIRMED, because
        agreement between two stale reports is not agreement about now.
      * An official report and a resident report are both evidence and
        neither overrides the other. A municipal page saying "open" while
        three people standing there say "closed" is exactly the disagreement
        worth showing, and silently preferring the official source would
        delete it.
      * Disagreement among fresh reports is CONFLICT, never a majority vote.
        Two say open, one says closed: the one may be the only person who
        walked there since. Counting heads would bury them.
    """
    spec = CATEGORIES.get(category)
    if spec is None:
        return Finding(place=place, category=category,
                       verdict="UNKNOWN_NO_CATEGORY",
                       reason=f"no such category: {category}")

    mine = [r for r in reports
            if r.place == place and r.category == category]
    if not mine:
        return Finding(place=place, category=category,
                       verdict="UNKNOWN_NO_REPORT",
                       reason="nobody has reported on this")

    mine.sort(key=lambda r: r.at)
    ttl = spec["ttl"]
    fresh = [r for r in mine if now - r.at <= ttl]
    stale = [r for r in mine if now - r.at > ttl]

    if not fresh:
        newest = mine[-1]
        return Finding(
            place=place, category=category, verdict="EXPIRED",
            status=newest.status, usable=None,
            age_minutes=now - newest.at,
            reporters=[newest.reporter],
            notes=[r.note for r in mine[-2:] if r.note],
            reason=(f"the newest report is {now - newest.at} minutes old; "
                    f"{category} goes stale after {ttl}. Nothing here can be "
                    f"stood behind — this is not the same as 'closed'."))

    statuses = {}
    for r in fresh:
        statuses.setdefault(r.status, []).append(r)

    if len(statuses) > 1:
        return Finding(
            place=place, category=category, verdict="CONFLICT",
            age_minutes=now - fresh[-1].at,
            sides=[{"status": s,
                    "usable": s in USABLE,
                    "reporters": [x.reporter for x in rs],
                    "official": any(x.official for x in rs),
                    "age_minutes": now - max(x.at for x in rs)}
                   for s, rs in sorted(statuses.items())],
            superseded=[{"status": r.status, "reporter": r.reporter,
                         "age_minutes": now - r.at} for r in stale[-3:]],
            notes=[r.note for r in fresh if r.note],
            reason="fresh reports disagree; no side is preferred and none is "
                   "outvoted")

    status = next(iter(statuses))
    backing = statuses[status]
    verdict = "CONFIRMED" if len({r.reporter for r in backing}) > 1 else "REPORTED"
    return Finding(
        place=place, category=category, verdict=verdict, status=status,
        usable=status in USABLE,
        age_minutes=now - backing[-1].at,
        reporters=sorted({r.reporter for r in backing}),
        superseded=[{"status": r.status, "reporter": r.reporter,
                     "age_minutes": now - r.at}
                    for r in stale[-3:] if r.status != status],
        notes=[r.note for r in backing if r.note],
        reason=("more than one reporter, and recently"
                if verdict == "CONFIRMED"
                else "one reporter; nobody has confirmed it independently"))


def for_needs(reports: List[Report], now: int,
              needs: List[str]) -> List[Dict[str, Any]]:
    """Everything relevant to what someone says they need.

    Findings are returned in a fixed order — usable first, then conflicts,
    then unknowns, then expired — but nothing is filtered OUT. A person who
    can see that the nearest water point's status expired forty minutes ago
    may still choose to walk there; a person shown only 'usable' places
    never learns it exists.
    """
    cats: List[str] = []
    for n in needs:
        for c in (NEEDS.get(n) or {}).get("categories", []):
            if c not in cats:
                cats.append(c)

    places = sorted({(r.place, r.category) for r in reports
                     if r.category in cats})
    findings = [assess(reports, now, p, c) for p, c in places]
    order = {"CONFIRMED": 0, "REPORTED": 1, "CONFLICT": 2,
             "UNKNOWN_NO_REPORT": 3, "EXPIRED": 4}
    findings.sort(key=lambda f: (0 if f.usable else 1,
                                 order.get(f.verdict, 9),
                                 f.age_minutes if f.age_minutes is not None else 10**6))
    return [f.as_dict() for f in findings]


def category_list(lang: str = "ja") -> List[Dict[str, Any]]:
    return [{"key": k, "label": v[lang if lang in ("ja", "en") else "ja"],
             "statuses": v["statuses"], "ttl_minutes": v["ttl"]}
            for k, v in CATEGORIES.items()]


def need_list(lang: str = "ja") -> List[Dict[str, str]]:
    return [{"key": k, "label": v[lang if lang in ("ja", "en") else "ja"]}
            for k, v in NEEDS.items()]
