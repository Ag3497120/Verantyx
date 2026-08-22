"""Where independently-built fields meet — and how much a change moves it.

Each field is modelled on its own: its own store, its own geometry, its own
placement. Federating them does not merge those models, and it is not
supposed to. What federation creates is a set of POINTS where two or three
fields turn out to be talking about the same thing:

    家庭裁判所   刑事 38 entities ｜ 民事 54     one institution, two procedures
    存続期間     民事 15          ｜ 知財 26     a lease term and a patent term
    救助         民事 15          ｜ 防災 20     salvage at sea and disaster relief
    関数         数学 68          ｜ 経済 10

Those are the joins. A question that arrives at one of them can be answered
from either side, and the two sides can disagree — which is the thing this
whole package exists to surface.

## The band, and why it is not a tuning knob

A concept present in EVERY field carries no field. Measured over twelve
fields (17,407 concepts, 9,370 cores): 18.7% span more than one field, and
the ones spanning all twelve are 作成, 必要, 定義, 目的, 規定, 情報 —
function words of legal and technical prose. Reading them as fusion would
say every field is fused with every other, which is true and useless.

The informative band is small: concepts held by BAND_LOW..BAND_HIGH fields.
Two fields sharing a term is a bridge; twelve fields sharing it is grammar.

## One field per SOURCE, or the measurement reads the prose style

Built at scale the first time with twenty-five fields — statutes split by
legal area, and ja.wikipedia split three ways by category — the largest
join was 全_文学 x 引用_法 at 202 concepts. Literature and jurisprudence had
not converged; both slices were Wikipedia, and what they shared was its
prose. Slicing one source into several fields makes the source's own style
arrive as fusion.

Re-cut so that each SOURCE is one field (e-Gov statutes by law, all of
ja.wikipedia as one), on nearly the same leaves:

    25 fields, source mixed   1,223 joins   top pair 全_文学 x 引用_法  202
     9 fields, one per source   858 joins   top pair 法令_民事 x 百科   240

Fewer joins and every top pair is now primary-source-against-commentary,
which is a relation that exists. Abstention in the resolution ladder fell
too, 24.9% to 20.3%: leaves cut from one source were more alike than the
field labels claimed.

## Why a baseline is computed before anything changes

The number that matters is not the fusion index — it is the DELTA when a
document arrives. An amendment that connects two fields which were separate,
or one that dissolves a bridge, is a structural event, and it is only
visible against a figure taken beforehand. That is what makes this a
pre-simulation rather than a report: `index` is run at build time so
`delta` has something to subtract from.

Nothing here merges stores or writes to a field. A fusion point is an
observation ABOUT two models, held outside both.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .cross_store import CrossStore
from .lex_filters import is_junk_core

#: Fields a concept may span and still say something about which field it is.
#: The upper bound is the load-bearing one — see the module docstring.
BAND_LOW, BAND_HIGH = 2, 3

#: Both sides must actually talk about it. A bridge one entity wide is a
#: coincidence of vocabulary, not a place two models meet.
MIN_ENTITIES = 2

_NUMERAL = re.compile(r"^[〇一二三四五六七八九十百千万0-9０-９]+$")


#: Cores that are article enumeration, not entities. 3.3% of the cores in
#: the reference federation are bare numerals — 三, 二, 五 — and a join
#: whose evidence on both sides is those is a join between two lists.
_BARE_NUMERAL = re.compile(r"^[〇一二三四五六七八九十百千]+$")


def _real_entities(entities: Iterable[str]) -> List[str]:
    return [e for e in entities if not _BARE_NUMERAL.match(e)]


def usable(term: str) -> bool:
    """Is this a concept, or is it bookkeeping?

    Article enumerations (一, 十二, 第三) dominate any raw count over
    statutes — they were 85% of the cross-field cores the first pass found,
    and none of them meant anything.
    """
    t = str(term)
    return (2 <= len(t) <= 10
            and not _NUMERAL.match(t)
            and not is_junk_core(t)
            and not t.endswith("txt"))


@dataclass
class Point:
    """One concept, and which entity of each field carries it."""

    concept: str
    by_field: Dict[str, Set[str]] = field(default_factory=dict)

    @property
    def fields(self) -> List[str]:
        return sorted(self.by_field)

    @property
    def width(self) -> int:
        """The thinner side. A bridge is only as wide as its narrow end."""
        return min((len(v) for v in self.by_field.values()), default=0)

    @property
    def mass(self) -> int:
        return sum(len(v) for v in self.by_field.values())

    def as_dict(self) -> Dict[str, Any]:
        return {"concept": self.concept, "fields": self.fields,
                "width": self.width, "mass": self.mass,
                "entities": {d: sorted(v)[:4] for d, v in sorted(self.by_field.items())}}


def concept_map(fields: Dict[str, Dict[str, CrossStore]]) -> Dict[str, Dict[str, Set[str]]]:
    """concept -> field -> the entities of that field which carry it."""
    holds: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for name, leaves in fields.items():
        for store in leaves.values():
            labels = getattr(store, "source_labels", set()) or set()
            for core, cross in store.crosses.items():
                for facet in cross:
                    if facet in labels or not usable(facet):
                        continue
                    holds[facet][name].add(core)
    return {c: dict(v) for c, v in holds.items()}


def points(
    fields: Dict[str, Dict[str, CrossStore]],
    *,
    band: Tuple[int, int] = (BAND_LOW, BAND_HIGH),
    min_entities: int = MIN_ENTITIES,
    only: Optional[Iterable[str]] = None,
) -> List[Point]:
    """The places two or three fields turn out to mean the same thing."""
    keep = set(only) if only else None
    out: List[Point] = []
    for concept, by in concept_map(fields).items():
        if keep is not None:
            by = {d: e for d, e in by.items() if d in keep}
        if not (band[0] <= len(by) <= band[1]):
            continue
        p = Point(concept=concept, by_field=by)
        if p.width < min_entities:
            continue
        out.append(p)
    out.sort(key=lambda p: (-p.width, -p.mass, p.concept))
    return out


def index(
    fields: Dict[str, Dict[str, CrossStore]],
    **kw: Any,
) -> Dict[str, Any]:
    """The baseline. Run at build time so `delta` has something to subtract.

    Reports the pair census as well as the total, because "these two fields
    became connected" is the event worth noticing and a single number hides
    which pair moved.
    """
    pts = points(fields, **kw)
    pair: Dict[str, int] = defaultdict(int)
    for p in pts:
        fs = p.fields
        for i in range(len(fs)):
            for j in range(i + 1, len(fs)):
                pair[f"{fs[i]}×{fs[j]}"] += 1
    return {
        "fields": sorted(fields),
        "n_points": len(pts),
        "total_mass": sum(p.mass for p in pts),
        "pairs": dict(sorted(pair.items(), key=lambda kv: (-kv[1], kv[0]))),
        "concepts": {p.concept: p.width for p in pts},
        "top": [p.as_dict() for p in pts[:20]],
    }


def delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """What an external change did to the joins.

    Three outcomes, and the first two are what a reader wants:

      opened   a concept that now bridges fields and did not before
      closed   a bridge that stopped being one
      widened  a bridge whose narrow end grew

    A change that only adds entities to existing bridges is reported as
    widening rather than as new fusion, because a field learning more about
    something it already shared is not a new connection.
    """
    b, a = before.get("concepts", {}), after.get("concepts", {})
    opened = sorted(set(a) - set(b))
    closed = sorted(set(b) - set(a))
    widened = sorted(c for c in (set(a) & set(b)) if a[c] > b[c])
    narrowed = sorted(c for c in (set(a) & set(b)) if a[c] < b[c])
    pb, pa = before.get("pairs", {}), after.get("pairs", {})
    pair_delta = {k: pa.get(k, 0) - pb.get(k, 0)
                  for k in set(pb) | set(pa) if pa.get(k, 0) != pb.get(k, 0)}
    return {
        "verdict": "CHANGED" if (opened or closed or widened or narrowed)
                   else "UNCHANGED",
        "n_points": {"before": before.get("n_points", 0),
                     "after": after.get("n_points", 0)},
        "opened": opened, "closed": closed,
        "widened": widened, "narrowed": narrowed,
        "pairs_moved": dict(sorted(pair_delta.items(),
                                   key=lambda kv: (-abs(kv[1]), kv[0]))),
    }


#: What kind of thing a field's documents are. A statute says what must be
#: so; a commentary says what was. Read as poles those are opposite and they
#: are not a disagreement, which is why 22.0% of joins came back
#: "contradiction" before this distinction existed.
REGISTERS = ("norm", "record", "unknown")

#: Sentence endings that mark a claim as normative rather than reported.
#: Narrow on purpose: measured over 8,572 statute sentences and 15,553
#: encyclopedia ones, these fire on 17.4% of law and 1.3% of prose, and the
#: descriptive set on 0.6% and 5.8%. They separate the registers where they
#: fire and say nothing on the 82-93% where they do not — so they REFINE the
#: field's declared register and never override it.
_NORM = re.compile(
    r"(なければならない|するものとする|してはならない|することができる"
    r"|に処する|を要する|とする。?$)")
_RECORD = re.compile(r"(した。?$|している|であった|された。?$|となった)")


def register_of(text: str) -> str:
    """norm / record / unknown, from a sentence's own ending."""
    s = (text or "").strip()
    if not s:
        return "unknown"
    n, d = bool(_NORM.search(s)), bool(_RECORD.search(s))
    if n and not d:
        return "norm"
    if d and not n:
        return "record"
    return "unknown"


#: 分野そのものの登録(2026-08-19)。`classify` の `registers` 引数は
#: 実装されて以来**一度も渡されていなかった** — 呼び出し元が居らず、
#: NORM_VS_RECORD の枝は到達不能だった(bridge.rs と同じ「実装済み未到達」)。
#: 文の登録は `register_of` が文末から読むが、join の両側は文ではなく
#: **分野**なので、そこは分野の性格から読む: 法令は定め、他は記す。
#: 連合の分野名は build_ja が付けたもの(法令/法学/百科/多分野/指名/辞書/
#: 百科本文)で、増えた分野は unknown に落ちる — 知らない分野を norm とは
#: 言わない。
_FIELD_REGISTER = {"法令": "norm", "法学": "record", "百科": "record",
                   "百科本文": "record", "多分野": "record",
                   "指名": "record", "辞書": "record"}


def field_register(name: str) -> str:
    """分野の登録: norm(定める) / record(記す) / unknown。"""
    return _FIELD_REGISTER.get(str(name or ""), "unknown")


def classify(
    fields: Dict[str, Dict[str, CrossStore]],
    point: "Point",
    *,
    registers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Is this join an agreement, a contradiction, or a complement?

    Each side's entities are read for polar terms, giving a set of
    (aspect, pole) pairs per field. Then:

        complement    the two sides talk about different aspects entirely
        agreement     a shared aspect, same pole on both sides
        contradiction a shared aspect, opposite poles

    Over 858 joins on the source-clean federation:

        no polar vocabulary   520   60.6%
        contradiction         189   22.0%
        agreement             101   11.8%
        complement             48    5.6%

    ## The 22% is a CANDIDATE rate, not a finding

    (2026-08-19: the breakdown above predates NORM_VS_RECORD, which now
    splits the prescribe-vs-report pairs out of that 22% before it is
    counted. The rate has not been re-taken on the current federation.)

    A statute states when a thing must be so; an encyclopedia describes a
    case where it was not. Read as poles those are opposite, and they are
    not a disagreement — 無線局 comes back "contradiction" for exactly that
    reason. Nothing here checks that the two sides are asserting about the
    same occasion, which is what a real contradiction needs and what
    `document_ingest` does have for claims inside one aspect.

    So this types the SHAPE of a join and hands the result to something that
    can adjudicate. Reporting 189 contradictions between Japanese statutes
    and their commentary would be false, and it is not what the count says.
    """
    from .ja_grammar import ASPECT_OF as _JA

    sides: Dict[str, Set[Tuple[str, str]]] = {}
    witness: Dict[str, Set[str]] = {}
    for name, entities in point.by_field.items():
        poles: Set[Tuple[str, str]] = set()
        seen_by: Set[str] = set()
        for store in (fields.get(name) or {}).values():
            # Only entities that are entities. A bare numeral is article
            # enumeration — 3.3% of cores in the reference federation — and
            # every candidate that survived the register test was evidenced
            # on both sides by nothing but those.
            for entity in _real_entities(entities):
                cross = store.crosses.get(entity)
                if not cross:
                    continue
                for facet in cross:
                    hit = _JA.get(facet)
                    if hit:
                        poles.add((hit[0], hit[1]))
                        seen_by.add(entity)
        sides[name] = poles
        witness[name] = seen_by

    speaking = [n for n, p in sides.items() if p]
    if len(speaking) < 2:
        return {"concept": point.concept, "kind": "NO_POLARITY",
                "fields": point.fields}
    a, b = sides[speaking[0]], sides[speaking[1]]
    shared = {x[0] for x in a} & {x[0] for x in b}
    if not shared:
        return {"concept": point.concept, "kind": "COMPLEMENT",
                "fields": speaking[:2],
                "aspects": {speaking[0]: sorted({x[0] for x in a})[:4],
                            speaking[1]: sorted({x[0] for x in b})[:4]}}
    clash = sorted(s for s in shared
                   if ((s, "+") in a and (s, "-") in b)
                   or ((s, "-") in a and (s, "+") in b))
    if not clash:
        return {"concept": point.concept, "kind": "AGREEMENT",
                "fields": speaking[:2], "aspects": sorted(shared)[:4]}

    # A norm and a record can carry opposite poles and disagree about
    # nothing: the statute says a thing must be so, the commentary reports an
    # occasion when it was not. Only two sides of the SAME register are
    # candidates for contradiction.
    # 呼び出し元が渡さなければ分野名から自給する。引数は残す(呼び出し元が
    # 文単位の登録を持っているならそちらが強い)が、既定で枝が死なない。
    reg = dict(registers or {})
    for _n in speaking:
        reg.setdefault(_n, field_register(_n))
    ra, rb = reg.get(speaking[0], "unknown"), reg.get(speaking[1], "unknown")
    if "norm" in (ra, rb) and "record" in (ra, rb):
        return {
            "concept": point.concept, "kind": "NORM_VS_RECORD",
            "fields": speaking[:2], "registers": [ra, rb],
            "aspects": sorted(shared)[:4], "opposed": clash[:4],
            "note": "one side prescribes, the other reports — opposite poles, "
                    "no disagreement",
        }
    return {
        "concept": point.concept,
        "kind": "CONTRADICTION_CANDIDATE",
        "fields": speaking[:2],
        "registers": [ra, rb],
        "aspects": sorted(shared)[:4],
        "opposed": clash[:4],
        "witnesses": {n: sorted(witness.get(n, ()))[:3] for n in speaking[:2]},
        "caveat": "same register and opposite poles — still not checked to be "
                  "about the same occasion",
    }


def read_at(
    fields: Dict[str, Dict[str, CrossStore]],
    concept: str,
    *,
    limit: int = 6,
) -> Dict[str, Any]:
    """What each side of a join says, side by side, without merging them.

    The point of keeping the models apart is that this can show a
    disagreement instead of averaging it away. Nothing here chooses.
    """
    from .consensus_store import ja_consensus_ask

    out: Dict[str, List[Dict[str, Any]]] = {}
    for name, leaves in fields.items():
        rows: List[Dict[str, Any]] = []
        for leaf, store in leaves.items():
            if not any(concept in c for c in store.crosses.values()):
                continue
            res = ja_consensus_ask(store, concept)
            rows.append({"leaf": leaf, "verdict": res.get("verdict"),
                         "core": res.get("core"), "text": res.get("text", "")})
            if len(rows) >= limit:
                break
        if rows:
            out[name] = rows
    return {"concept": concept, "fields": sorted(out), "by_field": out}
