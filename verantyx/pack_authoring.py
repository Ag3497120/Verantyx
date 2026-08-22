"""Authoring failure-domain knowledge from EXAMPLES, not from regular
expressions.

This exists because of three bugs in a row, all the same bug: `bureau` did
not match "bureaus", `reagent (expired` did not match "reagent R-114
expired", `assumes (concept` did not match "assumes concept not yet
mastered". Every one was written by someone who knew the domain fact
perfectly and got the regex slightly wrong. Asking a metrologist or a
clinician to debug `\\b` is asking the wrong person the wrong question.

So the authoring interface is: **paste the real log line, choose the
verdict**. A pattern is *proposed* from the examples, and the proposal is
only offered if it survives checks the author cannot be expected to run in
their head:

  - it matches every positive example given
  - it matches no negative example given
  - it does not steal any EXISTING fixture in the pack (the shadowing
    failure that patterns-outer priority makes easy to cause)
  - the resulting pack still passes the full maturity contract

If any check fails the proposal is refused WITH the counter-example,
because "your pattern also catches this other failure" is information the
author can act on and "invalid" is not.

Nothing here writes a live pack. Output is a proposed pack dict that goes
through the same quarantine-and-accept path as facts, modules and limits.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .failure_domains import (REMEDY_KINDS, VERIFY_METHODS, FailureDomain,
                              Fixture, RemedySpec, get, pack_from_dict,
                              pack_to_dict, validate)

#: Tokens that carry no discriminating power — dropping them keeps a
#: proposed pattern from keying on log furniture.
_STOP = frozenset({
    "the", "a", "an", "is", "was", "are", "were", "be", "been", "to", "of",
    "in", "on", "at", "for", "with", "from", "by", "and", "or", "not", "no",
    "this", "that", "it", "its", "error", "failed", "failure", "warning",
    "info", "debug", "log", "line",
})

_WORD = re.compile(r"[A-Za-z][A-Za-z_-]{2,}")


def _content_words(line: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(line) if w.lower() not in _STOP]


def propose_pattern(positives: List[str], negatives: List[str]) -> Optional[str]:
    """Build a regex from shared vocabulary across the positive examples.

    Deliberately simple and deliberately explainable: the pattern is an
    alternation-free conjunction of the words every positive example shares,
    in the order they appear, separated by `.*`. An author reading
    `reagent.*expired` can tell what it will and will not match; an author
    reading a cleverly minimised automaton cannot, and this file exists to
    keep the author in the loop rather than to be smart.

    Returns None when the examples share too little to key on — better to
    say "these examples have nothing in common" than to emit a pattern that
    keys on the word "the".
    """
    if not positives:
        return None
    word_sets = [set(_content_words(p)) for p in positives]
    shared = set.intersection(*word_sets) if word_sets else set()
    # Drop words that also appear in every negative — they cannot discriminate.
    if negatives:
        neg_common = set.intersection(*[set(_content_words(n)) for n in negatives])
        shared -= neg_common
    if not shared:
        return None
    # Order by first appearance in the first positive, so the pattern reads
    # in the same order as the log line it came from.
    first = _content_words(positives[0])
    ordered = [w for w in first if w in shared]
    # Keep it short: three anchors is enough to be specific and few enough
    # to stay readable and to survive small wording changes.
    ordered = ordered[:3]
    if not ordered:
        return None
    return r".*".join(re.escape(w) for w in ordered)


def check_proposal(
    pack_name: str,
    verdict: str,
    pattern: str,
    positives: List[str],
    negatives: List[str],
) -> Dict:
    """Would adding this verdict to this pack be safe and correct?

    Returns {"ok": bool, "problems": [...], "shadowed": [...]}. `shadowed`
    names existing fixtures this pattern would now claim — the specific
    failure that priority ordering makes easy and that a person cannot see
    by reading their own pattern.
    """
    problems: List[str] = []
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"ok": False, "problems": [f"pattern does not compile: {e}"],
                "shadowed": []}

    # Specificity. "Matches the positives, misses the negatives" is a weak
    # guarantee when only one or two negatives were supplied, and it passed a
    # real proposal down to a single generic token: two disaster examples
    # shared only "route" once "query" was cancelled by the counter-example,
    # and `route` would then claim every routing log ever written. A pattern
    # anchored on one short common word is not a classifier, so it is refused
    # here rather than queued for a reviewer who has no way to see the
    # problem from the pattern alone. Length is the discriminator: a lone
    # "cloudflare" or "landslide" is genuinely distinctive, a lone "route" is
    # not, and asking for one more counter-example is a cheap fix the author
    # can act on.
    anchors = [a for a in re.split(r"\.\*", pattern) if a]
    if len(anchors) < 2:
        longest = max((len(a) for a in anchors), default=0)
        if longest < 8:
            problems.append(
                f"too generic: anchored on the single short token "
                f"{anchors[0] if anchors else '(none)'!r}, which would claim "
                f"unrelated failures. Add a counter-example that also contains "
                f"it, or a positive example that shares a more distinctive word.")

    for p in positives:
        if not any(rx.search(ln.strip()) for ln in p.splitlines() if ln.strip()):
            problems.append(f"does not match a positive example: {p[:120]!r}")
    for n in negatives:
        hit = next((ln.strip() for ln in n.splitlines()
                    if ln.strip() and rx.search(ln.strip())), None)
        if hit:
            problems.append(f"matches a negative example: {hit[:120]!r}")

    shadowed: List[str] = []
    dom = get(pack_name)
    if dom is not None:
        for f in dom.fixtures:
            if f.expect == verdict:
                continue
            if any(rx.search(ln.strip()) for ln in f.evidence.splitlines() if ln.strip()):
                # Only a real problem if the new verdict would win, i.e. it
                # is placed before the fixture's own verdict. New verdicts
                # append last, so report it as a warning-level fact and let
                # the caller decide placement.
                shadowed.append(f"{f.name} (expects {f.expect})")

    return {"ok": not problems, "problems": problems, "shadowed": shadowed}


def propose_verdict(
    pack_name: str,
    verdict: str,
    note: str,
    positives: List[str],
    negatives: List[str],
    remedy_kind: str,
    remedy_owner: str,
    verify: str,
    remedy_note: str = "",
    author: str = "unknown",
    pattern: Optional[str] = None,
) -> Dict:
    """Propose one new verdict for an existing pack, from examples.

    The returned dict is a complete proposed pack (same shape as the JSON on
    disk) plus a report. It is NOT written anywhere — the caller queues it.

    `author` is stamped into provenance as `human:<author>`. That is the
    correction workflow in one field: a claude_seeded taxonomy edited by a
    domain expert stops claiming to be mine.
    """
    dom = get(pack_name)
    if dom is None:
        return {"ok": False, "error": f"unknown pack: {pack_name}"}
    if remedy_kind not in REMEDY_KINDS:
        return {"ok": False, "error": f"remedy kind {remedy_kind!r} not in vocabulary",
                "allowed": sorted(REMEDY_KINDS)}
    if verify not in VERIFY_METHODS:
        return {"ok": False, "error": f"verify {verify!r} not in vocabulary",
                "allowed": sorted(VERIFY_METHODS)}
    if any(v == verdict for v, _, _ in dom.patterns):
        return {"ok": False, "error": f"pack already has verdict {verdict}"}
    if not positives:
        return {"ok": False, "error": "at least one positive example is required — "
                                      "a verdict with no example is the thing this "
                                      "module exists to prevent"}

    generated = pattern is None
    pat = pattern or propose_pattern(positives, negatives)
    if pat is None:
        return {"ok": False,
                "error": "the positive examples share no discriminating words; "
                         "give examples that have something in common, or supply "
                         "a pattern explicitly"}

    check = check_proposal(pack_name, verdict, pat, positives, negatives)

    # Build the proposed pack: new verdict appended last (lowest priority),
    # every positive example retained as a fixture so the next author's
    # pattern cannot silently steal them.
    d = pack_to_dict(dom)
    d["verdicts"].append({
        "verdict": verdict,
        "pattern": pat,
        "note": note,
        "provenance": f"human:{author}" if not generated else f"human:{author}(from-examples)",
        "remedy": {"kind": remedy_kind, "owner": remedy_owner, "verify": verify,
                   "auto_calibratable": False, "note": remedy_note},
    })
    for i, p in enumerate(positives):
        d["fixtures"].append({
            "name": f"{verdict.lower()}_example_{i + 1}",
            "expect": verdict, "evidence": p, "provenance": "synthetic",
        })

    contract = validate(pack_from_dict(d))
    ok = check["ok"] and not contract
    return {
        "ok": ok,
        "pattern": pat,
        "pattern_was_generated": generated,
        "problems": check["problems"],
        "shadowed_fixtures": check["shadowed"],
        "contract_errors": contract,
        "proposed_pack": d,
    }


def test_pack_against_logs(pack_name: str, logs: List[str]) -> Dict:
    """Run a pack over real log samples and report the distribution.

    The number that matters is `unclassified`: a taxonomy that types 3 of
    200 real failures is not a taxonomy of that field yet, however tidy it
    looks. Sample lines are returned per verdict so an author can see WHAT
    it caught, not just how many — a pattern matching 90% of logs on the
    word "error" scores wonderfully and means nothing.
    """
    dom = get(pack_name)
    if dom is None:
        return {"error": f"unknown pack: {pack_name}"}
    counts: Dict[str, int] = {}
    samples: Dict[str, List[str]] = {}
    for log in logs:
        v, evidence, _ = dom.classify(log)
        counts[v] = counts.get(v, 0) + 1
        samples.setdefault(v, [])
        if len(samples[v]) < 3:
            samples[v].append((evidence or log)[:160])
    total = max(len(logs), 1)
    unclassified = counts.get(dom.fallback, 0)
    return {
        "pack": pack_name, "maturity": dom.maturity, "total": len(logs),
        "counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "samples": samples,
        "unclassified": unclassified,
        "coverage": round(1.0 - unclassified / total, 3),
    }
