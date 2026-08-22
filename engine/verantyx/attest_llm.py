"""Check a sentence somebody else wrote against what the store holds.

The architecture this exists for puts an LLM in the generation layer and
Vera underneath it as verification, citation and structure. That only means
anything if the verification actually catches an unsupported sentence — a
citation layer that passes everything is decoration, and a fluent wrong
answer with a citation stapled to it is worse than a fluent wrong answer.

So this scores a sentence it did not write, against a SUBJECT:

    terms    content runs the sentence uses
    linked   the ones the subject's own cross holds
    support  linked / terms

## Presence is not support, and measuring presence fails backwards

The first version asked whether the corpus held each term anywhere, and
whether adjacent pairs were crossed. Measured against a local 4B model over
14 subjects it ranked FREE generation above grounded generation — 95.7%
term presence against 85.5%, 25.3% pair support against 15.0% — because a
fluent answer about Japanese law is built from 法律, 制定, 原則, 国民, and a
federation of 54,244 legal cores holds every one of them. In a large corpus
presence is nearly free, so a checker built on it passes everything.

What is not free is the link to the SUBJECT. Asked about 第37条 the model
wrote 「国家の権限を保障し、国家が法律を制定する権利を確認する条文である」 —
fluent, plausible, and sharing nothing with what the store records under
第37条. Same 14 subjects, scored that way:

    grounded   64.1% of terms in the subject's cross
    free        6.4%

    at a 30% threshold: 0 of 14 grounded flagged, 14 of 14 free flagged

## Not knowing is not disagreeing

The first version returned the same verdict for both of these:

    超伝導は電気抵抗がゼロになる現象である。   true, and absent
    超伝導は江戸時代の農地制度である。         false, and absent

Both scored 0.00 and came back UNSUPPORTED_BY_CORPUS, because the subject
has no cross to link to and an empty cross links nothing. A reader would
have taken that as a judgment on a correct sentence. Every other path in
this package separates "no evidence" from "evidence against"; this one had
dropped the distinction.

So the subject is checked FIRST. A subject the store does not hold gets
`UNKNOWN_SUBJECT_NOT_HELD` — a refusal to judge, not a finding — and a
subject held too thinly to judge on gets `UNKNOWN_SUBJECT_TOO_THIN` with
its facet count attached. Measured on the 626MB federation the median core
carries 11 facets and 3.5% carry fewer than three, so three is the floor:
below it a 0.30 support figure is one facet's worth of luck.

## What it can and cannot say

It says "this corpus does not support that", never "that is false". 超伝導
is absent from a federation of Japanese statute and encyclopedia articles
and is not thereby untrue. The distinction is the whole point of putting a
store under a generator rather than asking the generator to grade itself:
one of them can be wrong about the world and the other can only be wrong
about the corpus, and the second failure is the one a reader can check.

A sentence that passes is not verified true. It is verified to be about
things this corpus holds, joined the way this corpus joins them — which is
exactly the claim a citation makes and no more.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_RUN = re.compile(r"[㐀-䶿一-鿿ァ-ヺー々〆]{2,}")


@dataclass
class Report:
    subject: str
    sentence: str
    terms: List[str] = field(default_factory=list)
    linked: List[str] = field(default_factory=list)
    unlinked: List[str] = field(default_factory=list)

    @property
    def support(self) -> float:
        return len(self.linked) / max(len(self.terms), 1)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject, "sentence": self.sentence,
            "terms": len(self.terms), "support": round(self.support, 3),
            "linked": self.linked[:8], "unlinked": self.unlinked[:8],
            "note": "unsupported by THIS corpus for THIS subject; "
                    "not a claim about truth",
        }


#: Below this, the sentence is about something other than what the store
#: records under the subject. Measured, not chosen: grounded output does not
#: reach down to it and free output does not reach up to it.
THRESHOLD = 0.30

#: Facets a subject needs before a support figure means anything. The median
#: core in the 626MB federation holds 11 and 3.5% hold fewer than three;
#: under that, one facet decides the verdict.
MIN_FACETS = 3


#: 英語の否定は語の前に立つ。閉じた表 — 開いた賢さは持ち込まない。
_EN_NEG = re.compile(r"\b(?:not|no|never|without|cannot|can't|doesn't|"
                     r"does not|didn't|did not|isn't|is not|aren't|are not)\b",
                     re.I)

#: 共有の `polarity._JA_NEG_AFTER` は「〜していない」を覆うが、サ変の
#: 辞書形否定「〜しない / 〜しません」を覆わない(実測: 「支給しない」が
#: 素通りした)。共有側は取り込み経路(否定53,885件の実測履歴)に効くので
#: 触らず、**主張を読む側にだけ**閉じた補足を置く。共有側の拡張は独自の
#: 事前登録が要る。位置で読む点は同じ — 語の直後だけを見る。
_JA_NEG_AFTER_SUPPL = re.compile(r"^し(?:ない|ません)(?![ぁ-ん])")


def claim_polarity(sentence: str, terms: Sequence[str]) -> Dict[str, str]:
    """主張側の極性: 語ごとに "+"/"-"。**位置で読む**(品詞ラベルは使わない)。

    日本語は語の直後の接尾(polarity._JA_NEG_AFTER — 過去4回の失敗の後に
    残った、唯一壊れていない読み方)。英語は同じ節の中の閉じた否定語。
    明示的な否定が付いていない語は、断定文の中では "+" と読む —
    detect_ja が非否定に対してしている読みと同じ。
    """
    from .polarity import _JA_NEG_AFTER, _standalone_index

    text = sentence or ""
    out: Dict[str, str] = {}
    for t in terms:
        i = _standalone_index(text, t)
        if i < 0:
            i = text.find(t)
        if i < 0:
            continue
        tail = text[i + len(t):]
        neg = bool(_JA_NEG_AFTER.match(tail)
                   or _JA_NEG_AFTER_SUPPL.match(tail))
        if not neg:
            # 英語(または混在)は節内の否定語を見る。節の切れ目は句読点。
            clause = re.split(r"[。．.!?;]", text)[0]
            if _EN_NEG.search(clause) and re.search(r"[A-Za-z]", clause):
                neg = True
        out[t] = "-" if neg else "+"
    return out


def store_polarity(cross: Iterable[str], term: str) -> Optional[str]:
    """店側の極性: aspect:value / aspect:not_value / ¬x のみを読む。

    記録が無ければ None — **無いことを「肯定」と読まない**(不在と否定を
    混ぜない)。ingest_polar_ja が実際に書く形式に合わせてある。
    """
    pos = neg = False
    for f in cross:
        if f == "\u00ac" + term or f.startswith("\u00ac" + term):
            neg = True
            continue
        if ":" not in f:
            continue
        key, val = f.split(":", 1)
        if val == term:
            pos = True
        elif val == "not_" + term:
            neg = True
    if pos and not neg:
        return "+"
    if neg and not pos:
        return "-"
    if pos and neg:
        return "both"
    return None


def adjudicate_polarity(cross: Iterable[str], reports: Sequence["Report"]
                        ) -> Dict[str, Any]:
    """極性の裁定。三つの結果を混ぜない(証拠 > 判定不能 > 争点なし)。"""
    cross = set(cross)
    contradicted: List[Dict[str, Any]] = []
    unjudged: List[Dict[str, Any]] = []
    for r in reports:
        pol = claim_polarity(r.sentence, r.linked)
        for term, claim_pole in pol.items():
            held = store_polarity(cross, term)
            if held in ("+", "-") and held != claim_pole:
                contradicted.append({
                    "term": term, "claim": claim_pole, "corpus": held,
                    "facet": next((f for f in cross
                                   if f.endswith(":" + term)
                                   or f.endswith(":not_" + term)), None),
                    "sentence": r.sentence})
            elif held is None and claim_pole == "-":
                # 語は持つが極性は記録していない。支持率は肯定と否定を
                # 同点にするので、その数字は主張できない。
                unjudged.append({"term": term, "claim": "-",
                                 "sentence": r.sentence})
    return {"contradicted": contradicted, "unjudged": unjudged}


def subject_coverage(store: Any, subject: str) -> Dict[str, Any]:
    """What the store has to judge this subject with, before judging.

    Held as a core is the strong case. Held only as somebody else's facet
    is weaker and is reported as such: the store knows the word exists and
    records nothing under it.
    """
    labels = getattr(store, "source_labels", set()) or set()
    cross = {f for f in (store.crosses.get(subject) or {}) if f not in labels}
    if cross:
        return {"held": "core", "facets": len(cross), "cross": cross}
    seen_as_facet = any(subject in (c or ()) for c in store.crosses.values())
    return {"held": "facet" if seen_as_facet else "absent",
            "facets": 0, "cross": set()}


def check(store: Any, subject: str, sentence: str,
          cross: Optional[Set[str]] = None) -> Report:
    labels = getattr(store, "source_labels", set()) or set()
    if cross is None:
        cross = {f for f in (store.crosses.get(subject) or {}) if f not in labels}
    terms: List[str] = []
    for t in _RUN.findall(sentence or ""):
        if t != subject and t not in terms and t not in labels:
            terms.append(t)
    r = Report(subject=subject, sentence=sentence, terms=terms)
    for t in terms:
        (r.linked if t in cross else r.unlinked).append(t)
    return r


def check_all(store: Any, subject: str, text: str) -> Dict[str, Any]:
    """Split on 。 and score every sentence against the subject.

    The subject is checked before the sentences are. Judging a claim about
    something the store never recorded is not verification, it is a coin
    flip dressed as one.
    """
    cov = subject_coverage(store, subject)
    if cov["held"] != "core":
        return {
            "verdict": "UNKNOWN_SUBJECT_NOT_HELD",
            "subject": subject, "held": cov["held"], "facets": 0,
            "note": "the store records nothing under this subject, so it "
                    "cannot judge the claim either way — this is a refusal "
                    "to judge, NOT a finding against the claim",
        }
    if cov["facets"] < MIN_FACETS:
        return {
            "verdict": "UNKNOWN_SUBJECT_TOO_THIN",
            "subject": subject, "held": "core", "facets": cov["facets"],
            "min_facets": MIN_FACETS,
            "note": "too few facets for a support figure to mean anything; "
                    "one facet would decide it",
        }

    sents = [s.strip() for s in re.split(r"[。\n]", text or "") if s.strip()]
    reps = [check(store, subject, s, cross=cov["cross"]) for s in sents]
    reps = [r for r in reps if r.terms]
    if not reps:
        return {"verdict": "UNKNOWN_EMPTY", "sentences": 0}
    sup = sum(r.support for r in reps) / len(reps)
    # 極性の裁定(PREREGISTERED_2026-08-20_attest_polarity)。この経路は
    # 漢字・カタカナの連しか見ないため、「支給する」と「支給しない」を
    # 構成上 同点にしていた(実測 support 1.0 vs 1.0、二者独立に発見)。
    pol = adjudicate_polarity(cov["cross"], reps)
    if pol["contradicted"]:
        return {
            "verdict": "CONTRADICTED_BY_CORPUS",
            "subject": subject, "held": "core", "facets": cov["facets"],
            "sentences": len(reps), "support": round(sup, 3),
            "contradictions": pol["contradicted"],
            "note": "この主題について、店は反対の極を証拠として持つ — "
                    "支持率ではなく極性が決めた。真偽の主張ではなく、"
                    "この蔵書との不一致",
            "reports": [r.as_dict() for r in reps],
        }
    if pol["unjudged"]:
        return {
            "verdict": "UNKNOWN_POLARITY_UNJUDGED",
            "subject": subject, "held": "core", "facets": cov["facets"],
            "sentences": len(reps), "support": round(sup, 3),
            "unjudged": pol["unjudged"],
            "note": "主張は否定を含むが、店はこの語の極性を記録していない。"
                    "支持率は肯定と否定を同点にするので、この数字では"
                    "判定できない — 黙って同点にしないための型付き拒否",
            "reports": [r.as_dict() for r in reps],
        }
    return {
        # The typed refusal is the point. A generation layer that gets
        # UNSUPPORTED back has been told something a fluent draft cannot
        # tell it, and a reader who sees ANSWER has a link to check.
        "verdict": "ANSWER" if sup >= THRESHOLD else "UNSUPPORTED_BY_CORPUS",
        "subject": subject, "held": "core", "facets": cov["facets"],
        "sentences": len(reps),
        "support": round(sup, 3), "threshold": THRESHOLD,
        "reports": [r.as_dict() for r in reps],
    }
