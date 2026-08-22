"""Did the system understand what was poured in? It says so itself, in types.

The operating goal is "pour any documents in and trust the result". No
pipeline can promise correctness on arbitrary input — but it can refuse to
be QUIETLY wrong about it. Until now, corpus quality was judged by a person
eyeballing the topic list; that person caught `com` and `md` posing as
topics, a 60% duplicate rate, and a notes file buried under its own pasted
code. On the next corpus there is no such person. This module is that
inspection, automated, and its findings are verdicts rather than vibes:

    INTAKE_OK                     nothing below flagged
    UNKNOWN_LOW_COVERAGE          most sentences never became facts
    UNKNOWN_FRAGMENTED_CORES      topics look like segmentation debris
    UNKNOWN_DOMINANT_SOURCE       one document is most of the corpus
    UNKNOWN_HIGH_DUPLICATION      the corpus is mostly copies of itself
    UNKNOWN_NO_PROVENANCE         claims cannot be traced to sources

Every threshold below is a judgment call and is documented as one, with the
reasoning attached. None is fitted to a particular corpus: each detects a
STRUCTURAL failure mode (dropped input, debris keys, single-source
dominance) that means the same thing whatever the documents are about.
A flagged corpus is not rejected — the report says what to check, and the
caller decides. Refusing to bless is not the same as refusing to serve.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .cross_store import CrossStore
from .document_ingest import IngestReport

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")

#: Below this fraction of seen sentences placed, the store is mostly not the
#: corpus. Half is deliberately forgiving: headers, list fragments and
#: captions legitimately place nothing, and a strict floor here would flag
#: healthy corpora and teach callers to ignore the report.
MIN_COVERAGE = 0.35

#: Cores of one Latin character or one ideograph are segmentation debris more
#: often than topics. A store where many keys look like that was probably fed
#: text in a script the segmenter does not really handle.
MAX_FRAGMENT_RATIO = 0.25

#: One source contributing more than this fraction of all sentences means
#: "the corpus says" is mostly "this one file says" — which is not wrong,
#: but it is a different claim, and the reader should know which one is
#: being made.
MAX_SOURCE_SHARE = 0.60


def _is_fragment(core: str) -> bool:
    if _CJK.search(core):
        return len(core) < 2
    return len(core) < 3


def assess(store: CrossStore, rep: IngestReport,
           duplicates: int = 0, files: int = 0) -> Dict[str, Any]:
    """The intake health report for one poured corpus.

    Returns every metric alongside the verdicts, because a verdict without
    its number cannot be argued with — and a report meant to be trusted must
    be checkable, including by someone who disagrees with the thresholds.
    """
    findings: List[Dict[str, Any]] = []

    seen = max(rep.sentences_seen, 1)
    coverage = rep.sentences / seen
    if coverage < MIN_COVERAGE:
        findings.append({
            "verdict": "UNKNOWN_LOW_COVERAGE",
            "measured": round(coverage, 3), "floor": MIN_COVERAGE,
            "meaning": "most sentences never became facts — wrong language, "
                       "wrong format, or content the cleaner removed",
            "check": "load one file with load_path() and read what came out",
        })

    cores = list(store.crosses)
    if cores:
        frag = sum(1 for c in cores if _is_fragment(c)) / len(cores)
        if frag > MAX_FRAGMENT_RATIO:
            findings.append({
                "verdict": "UNKNOWN_FRAGMENTED_CORES",
                "measured": round(frag, 3), "ceiling": MAX_FRAGMENT_RATIO,
                "meaning": "topic keys look like segmentation debris — the "
                           "corpus may be in a script or format the "
                           "segmenter does not truly handle",
                "check": "sample store keys; if they are word fragments, the "
                         "language needs a real segmentation pass first",
            })

    total = sum(rep.per_source.values()) or 1
    if rep.per_source:
        top_source, top_n = max(rep.per_source.items(), key=lambda kv: kv[1])
        share = top_n / total
        if share > MAX_SOURCE_SHARE and len(rep.per_source) > 1:
            findings.append({
                "verdict": "UNKNOWN_DOMINANT_SOURCE",
                "measured": round(share, 3), "ceiling": MAX_SOURCE_SHARE,
                "source": top_source,
                "meaning": "one document is most of the corpus, so agreement "
                           "across 'sources' is mostly one voice",
                "check": "treat cross-source agreement claims accordingly",
            })

    if files:
        dup_ratio = duplicates / max(files, 1)
        if dup_ratio > 0.4:
            findings.append({
                "verdict": "UNKNOWN_HIGH_DUPLICATION",
                "measured": round(dup_ratio, 3), "ceiling": 0.4,
                "meaning": "the corpus is heavily self-copied; counts would "
                           "have been inflated without dedupe",
                "check": "confirm the roots do not contain checkout copies",
            })

    if not store.track_provenance or not store.provenance:
        findings.append({
            "verdict": "UNKNOWN_NO_PROVENANCE",
            "meaning": "claims cannot be walked back to their sentences, so "
                       "nothing in this store is auditable",
            "check": "ingest through ingest_documents, which turns tracking on",
        })

    return {
        "verdict": "INTAKE_OK" if not findings else findings[0]["verdict"],
        "findings": findings,
        "metrics": {
            "sentences_seen": rep.sentences_seen,
            "sentences_placed": rep.sentences,
            "coverage": round(coverage, 3),
            "cores": len(cores),
            "sources": len(rep.per_source),
            "duplicates": duplicates,
            "polar_claims": rep.polar_claims,
        },
    }
