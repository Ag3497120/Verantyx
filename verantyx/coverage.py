"""Which shelf would close this refusal — the atlas read for humans.

The enterprise shape of the growth loop is inverted on purpose: the
system does not fetch documents, it NAMES the missing document and a
human supplies it. That inversion needs two things this module
provides:

    closing_domains   rank the federation's domains (多分野・法令・
                      法学・百科・指名 …) by how close each one already
                      is to the refused subject — held as a core, or
                      holding one of its units as a core. The winner is
                      the shelf whose kind of document would close the
                      gap; ties are DISPLAYED, not broken (a suggestion
                      surface, like near_terms — the reader picks)
    coverage_hole     no domain holds anything near the subject. That
                      is not a ranking, it is the atlas saying a whole
                      genre is missing — the "which knowledge is the
                      store thin on" recognition, read off operation
                      instead of guessed

The atlas is the existing federation: 多分野 (wiki fields) is already
the shallow world layer, and a domain absent from it shows up here as
holes accumulating under one genre. Widening the atlas is corpus work
(grow), not new machinery.

Nothing here votes. The output rides GapNodes (allowed_sources) and
displays; verdicts never read it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _units_of(subject: str) -> List[str]:
    from .granularity import SPLITS

    out: List[str] = []
    for a, _b in SPLITS.get(len(subject), ()):
        out.extend([subject[:a], subject[a:]])
    return [u for u in out if len(u) >= 2]


def closing_domains(
    domains: Dict[str, Any],
    subject: str,
    *,
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Rank shelves by proximity to ``subject``; name the hole honestly.

    Scores are deliberately coarse and recountable: held as a core is 2,
    a unit of the subject held as a core is 1 per unit, and — when an
    alias sidecar is supplied — the subject's canonical title held as a
    core is 2 with the hop NAMED in the signal (パワハラ is a redirect;
    the shelf holds パワーハラスメント, and a reader must see which of
    the two the evidence actually sits under). One hop only: an alias
    of an alias is a chain nobody attested. No frequency, no similarity
    — presence only, so a reader can re-derive every number by looking.
    """
    subject = (subject or "").strip()
    canonical = (aliases or {}).get(subject)
    ranked: List[Dict[str, Any]] = []
    units = _units_of(subject)
    for name in sorted(domains):
        store = domains[name]
        labels = getattr(store, "source_labels", set()) or set()
        signals: List[str] = []
        score = 0
        if subject in store.crosses and subject not in labels:
            score += 2
            signals.append("held: %s" % subject)
        if (canonical and canonical.casefold() in store.crosses
                and canonical not in labels):
            score += 2
            signals.append("alias held: %s → %s" % (subject, canonical))
        for u in units:
            if u in store.crosses and u not in labels:
                score += 1
                signals.append("unit held: %s" % u)
        if score:
            ranked.append({"domain": name, "score": score,
                           "signals": signals[:4]})
    ranked.sort(key=lambda d: (-d["score"], d["domain"]))
    out: Dict[str, Any] = {
        "subject": subject,
        "closest": ranked[:4],
        "coverage_hole": not ranked,
    }
    if canonical:
        out["canonical"] = canonical
    return out


def document_needed(
    domains: Dict[str, Any],
    subject: str,
    verdict: str = "UNKNOWN_NOT_PRESENT",
    *,
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """The human-readable line: which document, from which shelf.

    Combines the shelf ranking with the refusal's own repair
    (`remedy.remedy` — what to register and how much). When the atlas
    has a hole, it says so instead of naming a shelf it does not have:
    a named-but-wrong shelf would send a human to fetch the wrong
    document, which is worse than the honest hole.
    """
    from .remedy import remedy as _remedy

    where = closing_domains(domains, subject, aliases=aliases)
    repair = _remedy({"verdict": verdict, "subject": subject})
    out: Dict[str, Any] = {**where, "verdict": verdict,
                           "repair": repair}
    if where["coverage_hole"]:
        out["document"] = (
            "どの棚もこの主題の近くを持っていない — %r のジャンルごと"
            "不足。まずこの分野の概説文書を1本(浅くて良い)" % subject)
    else:
        top = where["closest"][0]
        tied = [d["domain"] for d in where["closest"]
                if d["score"] == top["score"]]
        out["document"] = (
            "%s の文書 — %s を独立した文で書くもの(%s)"
            % ("・".join(tied), subject,
               repair.get("register", "3文以上")))
    return out
