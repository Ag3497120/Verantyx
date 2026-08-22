"""Measure a real corpus — and be strict about what a real corpus cannot measure.

Planted ground truth gives precision and recall for free, and both come back
100% because the same person wrote the corpus and the detector. Real
documents are the opposite: they are honest, and they carry no answer key.
Running the planted suite and calling the result "measured on real
documents" is the single easiest way to lie about a system like this, so
this module separates the three cases and refuses to blur them.

    MEASURED AUTOMATICALLY
      coverage        sentences that produced a core, over sentences seen
      fragmentation   cores that look like segmentation debris
      throughput      characters per second
      detections      every contradiction found, with the source sentences

    MEASURED BY A PERSON
      precision       someone reads each detection and marks it true or false.
                      The module produces the worksheet and computes the
                      ratio; it does not judge its own output.

    NOT MEASURED, AND SAID SO
      recall          nobody knows what a corpus of real documents disagrees
                      about until a human marks it. An unannotated corpus can
                      never yield a recall number, and quoting one from it
                      would be fabrication.

The asymmetry that shapes the report: a missed disagreement costs one
finding; an invented one costs the reader's trust in every finding. So every
detection is printed in full with its evidence, and the summary leads with
precision rather than with counts.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arm_schema import ArmIndex
from .catalog import collect
from .cross_store import CrossStore
from .document_ingest import Document, deep_report, ingest_documents
from .document_loaders import load_paths
from .intake_quality import assess

#: A core this short is segmentation debris far more often than a topic.
#: Script-aware for the same reason the sentence floor is.
_MIN_CORE = {"cjk": 2, "latin": 3}


def _is_fragment(core: str) -> bool:
    import re
    cjk = re.search(r"[぀-ヿ㐀-䶿一-鿿]", core)
    return len(core) < (_MIN_CORE["cjk"] if cjk else _MIN_CORE["latin"])


@dataclass
class Detection:
    """One contradiction the system found, with everything a person needs to
    judge it — and a `truth` field that starts empty on purpose."""

    topic: str
    aspect: str
    sides: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    truth: str = ""          # "true" | "false" — filled in by a human
    note: str = ""


@dataclass
class Audit:
    """A corpus measurement. `polar_claims` is here for one reason: without
    it, a zero-detection result is unreadable. Zero contradictions over a
    corpus containing zero polar claims is arithmetic, not performance, and
    reporting the first without the second invites the reader to credit a
    detector that never had the chance to fire."""

    files: int
    chars: int
    sentences_seen: int
    sentences_placed: int
    topics: int
    seconds: float
    intake: Dict[str, Any]
    detections: List[Detection]
    fragment_ratio: float
    polar_claims: int = 0
    vocabulary_seen: Dict[str, int] = field(default_factory=dict)
    #: (core, aspect) pairs where two DIFFERENT sources placed poles. This is
    #: the true upper bound on detectable contradictions: zero here means a
    #: zero detection count carries no information about the detector, no
    #: matter how many polar claims the corpus contains.
    opposable_pairs: int = 0
    corpus_kind: str = ""

    @property
    def coverage(self) -> float:
        return self.sentences_placed / max(self.sentences_seen, 1)

    def as_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "detections"}
        d["coverage"] = round(self.coverage, 3)
        d["detections"] = [asdict(x) for x in self.detections]
        return d


def _evidence(store: CrossStore, topic: str, claim: str,
              aspect: str = "") -> str:
    """The sentence a claim came from, unmodified.

    Verbatim rather than paraphrased: the person marking this true or false
    is checking the system's reading against the source, and a paraphrase
    would be the system marking its own homework.

    The KEYED facet is looked up first, and that is not a detail. A polar
    word is also an ordinary facet of whatever sentence contained it, so
    「７月29日（水）に開設した熊本刑務所の避難所につき、８月３日（月）をもって閉鎖」
    puts a bare 開設 on 避難所 as well as the pole 開設:閉鎖 — and the bare one
    won the lookup. Both sides of that detection were then shown the SAME
    sentence, the closing one, while the opening side really came from a
    different revision. A worksheet that shows the wrong quote invites a
    person to mark a true detection false, which is worse than not offering
    the quote at all.
    """
    prov = store.provenance.get(topic, {}) or {}
    slot = prov.get(f"{aspect}:{claim}") if aspect else None
    if not slot or len(slot) < 3:
        for key, s in prov.items():
            if key.endswith(":" + claim) and len(s) > 2:
                slot = s
                break
    if not slot or len(slot) < 3:
        slot = prov.get(claim)
    return str(slot[2]) if slot and len(slot) > 2 else ""


def audit(paths: List[str]) -> Audit:
    t0 = time.time()
    res = load_paths(paths)
    docs: List[Document] = res["documents"]
    store, arms = CrossStore(), ArmIndex()
    rep = ingest_documents(store, docs, arms)
    elapsed = time.time() - t0

    detections: List[Detection] = []
    for topic in store.crosses:
        detail = deep_report(store, topic, arms)
        for entry in detail["disputed"]:
            sides = [{"claim": s["claim"], "sources": s["sources"]}
                     for s in entry["sides"]]
            detections.append(Detection(
                topic=topic, aspect=entry["aspect"], sides=sides,
                evidence=[e for e in
                          (_evidence(store, topic, s["claim"], entry["aspect"])
                           for s in sides)
                          if e]))

    cores = list(store.crosses)
    frag = (sum(1 for c in cores if _is_fragment(c)) / len(cores)) if cores else 0.0

    # Which opposition terms the corpus actually contains, and in how many
    # documents. A term appearing in one document can never produce a
    # contradiction — it takes two sources to disagree — so this column is
    # what separates "found nothing" from "had nothing to find".
    from . import ja_grammar
    seen: Dict[str, int] = {}
    for term in ja_grammar.TERMS:
        n = sum(1 for d in docs if term in d.text)
        if n:
            seen[term] = n

    # Could any contradiction have been found at all? Measured per document,
    # because it takes two sources to disagree and a corpus where every pole
    # sits in one file has nothing to detect however rich it looks.
    #
    # The distinction this exposes, found on two revisions of one 内閣府
    # guideline: PRESCRIPTIVE documents (指針, ガイドライン) do not
    # contradict each other — a revision adds and refines, it does not
    # assert the opposite. 令和4 held 実施 and 有効 for トイレ; 令和6 held
    # 使用可能 as well and nothing against. DESCRIPTIVE documents (status
    # announcements, situation reports) are where real disagreement lives,
    # because they describe a world that changed rather than a rule that was
    # refined. A corpus of guidance is the wrong shelf, and no amount of it
    # will produce a precision figure.
    # Keyed by POSITION, not by `doc.source`. The source label is a basename,
    # and a corpus of any size repeats them: 21.6M characters of this author's
    # repositories held four files called docker.md, so each one overwrote the
    # last and the empty copy won. The audit then reported zero opposable
    # pairs beside a worksheet containing a detection — a report contradicting
    # itself, in the module whose only job is to say what was really measured.
    by_source: Dict[int, Dict[str, set]] = {}
    for i, doc in enumerate(docs):
        one = CrossStore()
        one.track_provenance = True
        ingest_documents(one, [doc])
        held: Dict[str, set] = {}
        for core, facets in one.crosses.items():
            for f in facets:
                if ":" in f:
                    held.setdefault(f"{core}\t{f.split(':', 1)[0]}", set()).add(f)
        by_source[i] = held

    opposable = 0
    keys = set().union(*(set(h) for h in by_source.values())) if by_source else set()
    for key in keys:
        values = [h[key] for h in by_source.values() if key in h]
        if len(values) > 1 and len(set().union(*values)) > 1:
            opposable += 1

    kind = ("descriptive" if opposable else
            ("prescriptive" if rep.polar_claims else "no_state_claims"))

    return Audit(
        opposable_pairs=opposable, corpus_kind=kind,
        files=res["loaded"], chars=sum(len(d.text) for d in docs),
        sentences_seen=rep.sentences_seen, sentences_placed=rep.sentences,
        topics=len(cores), seconds=round(elapsed, 2),
        intake=assess(store, rep), detections=detections,
        fragment_ratio=round(frag, 3), polar_claims=rep.polar_claims,
        vocabulary_seen=dict(sorted(seen.items(), key=lambda kv: -kv[1])))


def worksheet(a: Audit, lang: str = "ja") -> str:
    """The sheet a person marks. One detection per block, evidence verbatim.

    Printed even when there are zero detections, with the reason spelled
    out, because "we found nothing" and "we did not look" are the two
    readings a bare zero invites and only one of them is true.
    """
    ja = lang == "ja"
    out: List[str] = []
    out.append("# " + ("矛盾検出の判定シート" if ja
                       else "Contradiction worksheet"))
    out.append("")
    out.append(("各検出について、原文を読んで true(本当の食い違い) か "
                "false(誤検出) を記入してください。" if ja else
                "For each detection, read the evidence and mark it true (a real "
                "disagreement) or false (a false positive)."))
    out.append("")
    if not a.detections:
        if a.opposable_pairs == 0:
            out.append(("**検出ゼロ、そして矛盾になり得た組も 0。** 極性を持つ主張は"
                        f"{a.polar_claims} 件ありますが、同じ話題の同じ観点について"
                        "異なる出典が異なる状態を述べた箇所が一つもありません。"
                        "食い違うには2つの出典が要るので、検出 0 は必然です。"
                        "**この結果から精度は測れません。**" if ja else
                        f"**Zero detections, and zero opposable pairs.** The corpus "
                        f"holds {a.polar_claims} polar claims, but no two sources "
                        "ever place different states on one topic and aspect. It "
                        "takes two to disagree. **No precision can be read from "
                        "this.**"))
            return "\n".join(out)
        if a.polar_claims == 0:
            out.append(("**検出ゼロ、ただし極性を持つ主張も 0 件。** この文書群には"
                        "状態の主張(開/閉、通行可否など)が一つも含まれていないため、"
                        "矛盾が 0 なのは算術的な必然であり、検出器の性能とは無関係です。"
                        "**この結果から精度は測れません。**" if ja else
                        "**Zero detections, and zero polar claims.** These "
                        "documents contain no state assertions at all, so zero "
                        "contradictions is arithmetic rather than performance. "
                        "**No precision can be read from this.**"))
            return "\n".join(out)
        out.append(("**検出ゼロ。** これは検出器が働いた証拠ではありません。"
                    "この文書群が実際に食い違っていないだけかもしれず、"
                    "見逃しの可能性も残ります(下記のとおり再現率は測っていません)。"
                    if ja else
                    "**Zero detections.** This is not evidence the detector "
                    "works. These documents may simply not disagree, and "
                    "misses remain possible — recall is not measured here."))
        return "\n".join(out)

    for i, d in enumerate(a.detections, start=1):
        out.append(f"## {i}. {d.topic} — {d.aspect}")
        for s in d.sides:
            out.append(f"- **{s['claim']}** ← {', '.join(s['sources']) or '?'}")
        for e in d.evidence:
            out.append(f"  > {e}")
        out.append("")
        out.append("  truth: [ ]  note:")
        out.append("")
    return "\n".join(out)


def report(a: Audit, marked: Optional[List[Detection]] = None,
           lang: str = "ja") -> str:
    ja = lang == "ja"
    out: List[str] = []
    out.append("# " + ("実文書での測定" if ja else "Real-corpus measurement"))
    out.append("")
    out.append(("## 自動で測れたもの" if ja else "## Measured automatically"))
    out.append("")
    out.append(f"- {'文書' if ja else 'documents'}: {a.files:,}")
    out.append(f"- {'文字' if ja else 'characters'}: {a.chars:,}")
    out.append(f"- {'被覆率' if ja else 'coverage'}: {a.coverage:.1%} "
               f"({a.sentences_placed:,}/{a.sentences_seen:,})")
    out.append(f"- {'話題' if ja else 'topics'}: {a.topics:,}"
               f" / {'断片率' if ja else 'fragment ratio'} {a.fragment_ratio:.1%}")
    out.append(f"- {'処理' if ja else 'throughput'}: {a.chars / max(a.seconds, .01):,.0f}"
               f" {'文字/秒' if ja else 'chars/sec'} ({a.seconds}s)")
    out.append(f"- {'極性を持つ主張' if ja else 'polar claims'}: {a.polar_claims}")
    multi = {t: n for t, n in a.vocabulary_seen.items() if n > 1}
    out.append(f"- {'対立語彙が2出典以上に現れた数' if ja else 'opposition terms in >1 source'}"
               f": {len(multi)}"
               + (f" ({', '.join(list(multi)[:6])})" if multi else ""))
    out.append(f"- {'矛盾になり得た組' if ja else 'opposable pairs'}: "
               f"**{a.opposable_pairs}**"
               + (f" — {'この数が 0 なら検出 0 は必然' if ja else 'zero here makes a zero detection meaningless'}"
                  if a.opposable_pairs == 0 else ""))
    kinds = {"descriptive": "状態を述べる文書(矛盾が起こり得る)",
             "prescriptive": "規範を述べる文書(改定は追加であって反転ではない)",
             "no_state_claims": "状態の主張が無い文書"}
    out.append(f"- {'コーパスの種類' if ja else 'corpus kind'}: "
               f"**{a.corpus_kind}**"
               + (f" — {kinds.get(a.corpus_kind, '')}" if ja else ""))
    out.append(f"- {'取り込み診断' if ja else 'intake'}: **{a.intake['verdict']}**")
    for f in a.intake.get("findings", []):
        out.append(f"  - {f['verdict']}: {f.get('measured', '')}")
    out.append("")

    out.append(("## 人が判定したもの" if ja else "## Measured by a person"))
    out.append("")
    if not marked:
        out.append(("未判定です。`worksheet()` を出力して、各検出に true/false を"
                    "記入してから再集計してください。**判定前の検出数は精度では"
                    "ありません。**" if ja else
                    "Not yet judged. Print `worksheet()`, mark each detection "
                    "true or false, and re-run. **A detection count before "
                    "judgement is not a precision figure.**"))
    else:
        t = sum(1 for d in marked if d.truth == "true")
        f = sum(1 for d in marked if d.truth == "false")
        u = len(marked) - t - f
        total = t + f
        out.append(f"- {'検出' if ja else 'detections'}: {len(marked)}"
                   f" ({'真' if ja else 'true'} {t} / "
                   f"{'偽' if ja else 'false'} {f} / "
                   f"{'未判定' if ja else 'unjudged'} {u})")
        if total:
            out.append(f"- **{'精度' if ja else 'precision'}: {t/total:.1%}**"
                       f" ({t}/{total})")
        if u:
            out.append(("- 未判定が残っているため、この精度は暫定です。"
                        if ja else
                        "- Unjudged detections remain; this precision is provisional."))
    out.append("")

    out.append(("## 測っていないもの" if ja else "## NOT measured"))
    out.append("")
    out.append(("**再現率(見逃し率)は、この測定では出せません。** 実文書には"
                "「本当はどこが食い違っているか」の正解が付いておらず、人が全文を"
                "読んで印を付けない限り分母が存在しないためです。仕込み正解での"
                "再現率100%は、この数字の代わりにはなりません。"
                if ja else
                "**Recall cannot come out of this.** Real documents carry no "
                "answer key; without a human marking every real disagreement "
                "there is no denominator. The planted-corpus 100% does not "
                "substitute for it."))
    return "\n".join(out)


def audit_paths(roots: List[str]) -> Audit:
    return audit(collect(roots)["files"])


def save(a: Audit, path: str) -> None:
    Path(path).write_text(json.dumps(a.as_dict(), ensure_ascii=False, indent=1),
                          encoding="utf-8")


def load_marked(path: str) -> List[Detection]:
    """Read back a worksheet that a person has filled in (JSON form)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("detections", raw)
    return [Detection(**r) for r in rows]
