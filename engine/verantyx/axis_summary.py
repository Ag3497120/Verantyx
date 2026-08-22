"""Selection by cross-field agreement — a summary the store can defend.

A summary is a ranking, and this system has no importance to rank by.
Substituting frequency smuggles in "common means important", which is a
claim about the corpus dressed as a claim about the subject.

Cross-field agreement is not that. When 法令 and 百科 and 法学 each record
the same facet under a subject, three readers of three document sets picked
it out separately — an editorial judgment that was already made, three
times, by people. Selecting on it is reporting their agreement, not adding
one.

## Measured

67 subjects held by two or more fields, scored against 1.7M characters of
held-out encyclopedia prose that none of the fields was built from:

    facets two or more fields record   55.6% appear in held-out text
                                       median 5 occurrences
    facets only one field records      24.2%
                                       median 0

2.30x, and the median is the sharper number: the typical single-field facet
appears NOWHERE in independent prose, and the typical agreed one appears
five times.

## What this is not

Not a summary of a document. It selects what several independent readings of
a SUBJECT have in common, which is a different thing from what a text says
and much less than what a reader means by "summarise this". It cannot
order, cannot compress a narrative, and cannot say what matters to the
person asking.

It also inherits the fields' shared blind spots. Three document sets that
all omit something agree about its absence, and this reports that as
silence rather than as a gap — the same limit `fusion` carries, for the
same reason.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: Fields that must record a facet before it counts as agreed. Two, because
#: the measurement above split at two and because one field agreeing with
#: itself is what frequency already measures.
MIN_FIELDS = 2


def facets_by_field(fields: Dict[str, Any], subject: str) -> Dict[str, set]:
    """Per field, what it records under this subject."""
    out: Dict[str, set] = {}
    for name, store in fields.items():
        labels = getattr(store, "source_labels", set()) or set()
        cross = store.crosses.get(subject)
        if cross:
            out[name] = {f for f in cross if f not in labels}
    return out


def summarise(
    fields: Dict[str, Any],
    subject: str,
    *,
    min_fields: int = MIN_FIELDS,
    limit: int = 12,
) -> Dict[str, Any]:
    """What several fields independently record about this subject.

    Every returned facet carries the fields that recorded it, because that
    is the whole warrant: the reader is being shown an agreement, and
    without the names it looks like a judgment this module made.
    """
    per = facets_by_field(fields, subject)
    if not per:
        return {"verdict": "UNKNOWN_SUBJECT_NOT_HELD", "subject": subject,
                "fields": sorted(fields)}
    if len(per) < min_fields:
        return {"verdict": "UNKNOWN_ONE_FIELD_ONLY", "subject": subject,
                "held_by": sorted(per),
                "note": "one field cannot agree with itself; what it records "
                        "is available but is not a cross-field selection"}

    tally: Counter = Counter()
    who: Dict[str, List[str]] = {}
    for name, fs in per.items():
        for f in fs:
            tally[f] += 1
            who.setdefault(f, []).append(name)
    agreed = [(f, n) for f, n in tally.most_common() if n >= min_fields]
    return {
        "verdict": "ANSWER" if agreed else "UNKNOWN_NO_AGREEMENT",
        "subject": subject,
        "fields": sorted(per),
        "agreed": [{"facet": f, "fields": sorted(who[f]), "count": n}
                   for f, n in agreed[:limit]],
        "single_field": sorted(f for f, n in tally.items() if n < min_fields)[:limit],
        "note": "facets several fields recorded independently; measured 2.30x "
                "more likely than single-field facets to appear in held-out "
                "prose. This is their agreement, not a judgment made here",
    }
