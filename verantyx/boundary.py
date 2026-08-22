"""Boundary detector (Direction B) — decides what a recurring UNKNOWN bucket
means, before any LLM is ever asked to write code.

Deliberately rule-based, not LLM-based: this is the "harden the boundary
judgment first" half of the plan. Accuracy is a starting point, not a
measured constant — thresholds are meant to be tuned from real
`growth_signals.json` data over time (same honesty as QueryReformulator's
own thresholds in the IDE's K-milestone work).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .en_decompose import decompose
from .growth_signals import UnknownBucket

Classification = Literal[
    "reject_open_domain", "needs_more_facts", "growth_candidate",
    "needs_more_capacity",
]

MIN_RECURRENCE = 5
_SYMBOL_DENSITY_RE = re.compile(r"[0-9+\-*/=<>()^%]")

# Verdicts meaning "the right procedure ran and hit a limit", as opposed to
# "no procedure exists" or "facts are missing". They used to fall through to
# the needs_more_facts default, which is the worst available answer: the
# facts are already there, and a human told to add more would find nothing to
# add. The remedy is the same shape for both — raise a number, re-run, check
# it now answers — which is what makes them one class rather than two.
#
# UNKNOWN_LOCAL_MINIMUM is deliberately NOT here. Its remedy is a different
# knob (ConsensusConfig.allow_escape) and no case in boundary_eval pins down
# what the right classification for it is, so guessing would put an unverified
# label into the loop that learns from these labels.
_CAPACITY_VERDICTS = frozenset({"UNKNOWN_BUDGET", "UNKNOWN_OVERFLOW"})

# Distinct content tokens, not distinct part-of-speech tags.
#
# The original signal was `len(set(rec.roles))`, which counts grammatical
# categories. That set has ten members in total and only four content ones,
# so it saturates almost immediately: a seventeen-word question about housing
# in cold climates scores 4, exactly the same as "is the staging certificate
# current". The reject branch required *more* than 4, so it was close to
# unreachable, and every query without symbols fell through to the
# growth_candidate default — the permanent architectural boundary was, in
# practice, the path of least resistance into module drafting.
#
# Content-token breadth measures topical spread instead, and it does not
# saturate. Measured on the boundary_eval cases: formal and narrow queries
# land at 2-3, open-domain questions at 8-13. The thresholds sit inside that
# empty band with margin on both sides. Still a starting point to be retuned
# from real growth_signals.json data, but a starting point on a signal that
# can separate the classes at all.
_NARROW_CONTENT_MAX = 4
_OPEN_CONTENT_MIN = 7

# Structural sub-labels for reject_open_domain — logging/routing only, NEVER
# a growth_candidate path. Extending the module-generation loop to "learn"
# any of these would be wrong by construction: module_forge.py's own style
# guide requires a deterministic, typed-verdict function with no LM call —
# narrative continuation, copyrighted-work synopsis, and asset generation
# (3D models, images) cannot be expressed that way, no matter how narrow
# the query shape looks. This is a permanent architectural boundary, not a
# gap to close. Checked BEFORE the generic classification below so a
# narrow-looking query like "make a 3D model of X" can never slip into
# growth_candidate's low-density default branch.
#
# Keyword lists are a deliberately small starting point (same honesty as
# QueryReformulator's own thresholds) — false negatives fall through to the
# generic role-diversity check below, which still correctly rejects most
# open-domain natural language; false positives here are the safer failure
# mode than a false negative that reaches growth_candidate.
_COPYRIGHT_RE = re.compile(
    r"(あらすじ|続きを書|原作|アニメ|漫画|マンガ|小説の続き|"
    r"synopsis|plot summary|continue the story|write.*sequel|fan\s?fiction)",
    re.IGNORECASE,
)
_ASSET_GEN_RE = re.compile(
    r"(3d ?モデル|3dモデルを作|イラストを描|画像を生成|音楽を作|動画を作|"
    r"3d model|generate (an? )?(image|video|3d|model)|draw (a|an|me)|compose (a )?song)",
    re.IGNORECASE,
)
_LINGUISTIC_RE = re.compile(
    r"(という言葉の意味|語源|文法的に|意味を解釈|とはどういう意味|"
    r"word meaning|etymology|grammatically|interpret the meaning)",
    re.IGNORECASE,
)


def _out_of_scope_subcategory(text: str) -> "str | None":
    if _COPYRIGHT_RE.search(text):
        return "copyright_sensitive"
    if _ASSET_GEN_RE.search(text):
        return "asset_generation_out_of_scope"
    if _LINGUISTIC_RE.search(text):
        return "linguistic_interpretation"
    return None


@dataclass
class BoundaryVerdict:
    classification: Classification
    reason: str
    subcategory: "str | None" = None


def _symbol_density(text: str) -> float:
    if not text:
        return 0.0
    hits = len(_SYMBOL_DENSITY_RE.findall(text))
    return hits / max(len(text), 1)


def classify(bucket: UnknownBucket, min_recurrence: int = MIN_RECURRENCE) -> BoundaryVerdict:
    # Structural out-of-scope check first — runs on ALL examples in the
    # bucket (not just [0]), and short-circuits BEFORE the recurrence
    # threshold: a copyright-sensitive request should never sit in
    # growth_signals.json accumulating toward candidacy even once, let
    # alone after 5 repeats.
    for example in (bucket.examples or [bucket.normalized]):
        sub = _out_of_scope_subcategory(example)
        if sub:
            return BoundaryVerdict("reject_open_domain", "structural_out_of_scope", subcategory=sub)

    if bucket.total() < min_recurrence:
        return BoundaryVerdict("needs_more_facts", "below_recurrence_threshold")

    dominant = bucket.dominant_verdict()

    # A limit was hit, not a gap in knowledge. Checked before everything
    # below because the query shape is irrelevant here: a 7-digit addition is
    # as narrow and symbol-dense as a 6-digit one, so the shape heuristics
    # would happily call it a growth_candidate and draft a module duplicating
    # arithmetic that already works.
    if dominant in _CAPACITY_VERDICTS:
        return BoundaryVerdict("needs_more_capacity", f"limit_reached:{dominant}")

    # Repeated "found the right shell, not enough facts" is a memory gap,
    # not a missing domain — telling a human to add facts is the honest fix.
    if dominant == "UNKNOWN_INSUFFICIENT_EVIDENCE":
        return BoundaryVerdict("needs_more_facts", "dominant_insufficient_evidence")

    # A domain module already claimed this query's shape (e.g. Kripke
    # recognizing valid modal-logic syntax but lacking a registered
    # proposition) — that module already exists, so the gap is missing
    # facts, never a reason to draft a duplicate module. Checked BEFORE the
    # generic NO_EVIDENCE/UNPARSED split below, since a matched domain can
    # still report UNKNOWN_NO_EVIDENCE for reasons that have nothing to do
    # with "no domain recognized this shape".
    if bucket.matched_domain_count > bucket.total() / 2:
        return BoundaryVerdict("needs_more_facts", "matched_existing_domain_missing_facts")

    # Only NO_EVIDENCE / UNPARSED buckets (Vera never even found a shape to
    # work with) are candidates for "maybe this needs a whole new module".
    if dominant not in ("UNKNOWN_NO_EVIDENCE", "UNKNOWN_UNPARSED"):
        return BoundaryVerdict("needs_more_facts", f"dominant_verdict_not_structural:{dominant}")

    example = bucket.examples[0] if bucket.examples else bucket.normalized
    density = _symbol_density(example)
    rec = decompose(example)
    breadth = len(set(rec.content_tokens)) if rec.content_tokens else 0

    # High symbol density (numbers/operators) with a tight query shape looks
    # like a closed formal domain (cf. math_sim.py's own regex-first style).
    if density >= 0.15 and breadth <= _NARROW_CONTENT_MAX:
        return BoundaryVerdict("growth_candidate", "high_symbol_density_narrow_shape")

    # Broad natural-language questions are open-domain by nature — no
    # fixed-form module can close them; route to the LLM permanently rather
    # than re-proposing the same rejection every heartbeat.
    if breadth >= _OPEN_CONTENT_MIN:
        return BoundaryVerdict(
            "reject_open_domain", f"content_breadth_too_broad:{breadth}",
            subcategory="general_open_domain",
        )

    # Narrow shape without symbol density: a weak positive, but a positive.
    if breadth <= _NARROW_CONTENT_MAX:
        return BoundaryVerdict("growth_candidate", "narrow_shape_low_density")

    # Between the two thresholds nothing is claimed. The previous version
    # defaulted to growth_candidate here on the grounds that drafting is cheap
    # and human approval gates it anyway. That reasoning inverts what the
    # approval queue is for: it is the last line of defence, not a reason to
    # aim noise at it, and a queue that fills with things a human must reject
    # is a queue a human stops reading carefully. Undecided means undecided.
    return BoundaryVerdict("needs_more_facts", f"content_breadth_undecided:{breadth}")
