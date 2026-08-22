"""Deterministic stage-boundary split — the arrow that `staged` cannot guess.

`stacked.staged` already holds a multi-hop intersection: each intermediate
stage hands survivors forward and only the last stage elects. What it will
not do is invent the cuts. 「背任罪の刑の上限を科された者の再審請求先」hides
those cuts in case grammar; guessing one answers a different chain. This
module turns a nested noun phrase into an ordered stage list `staged`
could consume (`fragment → fragment → …`), or it says it cannot.

Tokenizer: surface-string rules, not Fugashi. Fugashi (unidic-lite) is
installed and deterministic, but a dictionary update would move a boundary
without a rule changing. The cuts here are closed tables on the surface.

Frozen head-noun table (longest first):

    場所 者 物 先 日 年 罪 刑 額 数

A content run is headed when it carries one of those as a suffix
(「背任罪」yes, 「日本」no — 日 is a prefix, not the head).

Bare temporal nouns (closed exclusion, longest first):

    一昨日 一昨年 今日 昨日 明日 今年 昨年 来年 本年
    毎年 翌年 前年 毎日 今月 先月 来月 本日 当日 翌日

A left interval whose entire content is one of those does not
license a 「の」 cut, even though it ends in 日/年/月. 日 and 年
stay in the head table for genuine stage heads (施行日, 判決年).
This is why 今年の予算額 stays one stage and 殺人罪の刑の上限
still cuts.

「の」-split rule (stated so a reader can audit every cut):

    A 「の」 is a stage boundary only when the left interval (from the
    previous cut) contains a closed relative predicate (された / する)
    or its rightmost content run is headed, AND the first content run
    of the right interval is also headed. Otherwise the 「の」 is a
    modifier. That is why 東京の人口 and 刑の上限 stay one piece, while
    背任罪の刑 and 者の再審請求先 cut.

Relative-clause cut: された or する immediately followed by a headed
run. Each stage is (condition-fragment, head). Order is innermost
first — Japanese is head-final, so left-to-right is resolution order.
The rightmost head is the final question target.

Unsplittable or ambiguous input returns UNKNOWN_UNSEGMENTED. Never
guess a boundary. False-splitting 東京の人口 is the bad failure;
abstaining on a nested legal NP is cheaper than inventing a cut.

## Measured — preregistered bank 2026-08-14, 30 questions

    exact-match (whole chain)        30 / 30
    boundary precision               1.0000
    boundary recall                  1.0000
    false-split rate (10 nosplit)    0 / 10   the bad failure
    abstention count                 10
    (UNKNOWN_UNSEGMENTED; all 10 hard items)

    by kind
        multihop exact               10 / 10
        nosplit exact                10 / 10
        hard abstain                 10 / 10

    fork STAGE_SPLIT_DEFENSE         pass
    tokenizer                        surface-rules
    bank predates first split        yes

The 30/30 is rule-consistency: expected chains were handwritten
from the same frozen tables before the first split call, not an
independent linguistic gold. The number that would move under a
different rule is the false-split rate (0/10) and the ten typed
abstentions on した-relatives, mid が, coordination, and unheaded
された+場合.

## Measured — amendment 2026-08-14T21:26:00+09:00 (temporal exclusion)

    exact-match (old 30 + 10 new)    40 / 40
    boundary precision               1.0000
    boundary recall                  1.0000
    false-split rate (18 nosplit)    0 / 18   the bad failure
    (old 10 + 8 temporal lefts)
    abstention count                 10
    (still the original 10 hard items)

    by kind
        multihop exact               12 / 12
        nosplit exact                18 / 18
        hard abstain                 10 / 10

    fork STAGE_SPLIT_DEFENSE         pass
    (今年の予算額 / 昨日の提出先 stay 1 stage;
     殺人罪の刑の上限 → 殺人罪 → 刑の上限)
    amendment predates first
    amendment split                  yes
    (registered_amendment set; first
     amendment split at call 31)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Longest first so 場所 is not read as a one-character head.
HEAD_NOUNS: Tuple[str, ...] = (
    "場所",
    "者", "物", "先", "日", "年", "罪", "刑", "額", "数",
)

# Bare deictic/calendar nouns. A left interval that IS one of these
# does not license a 「の」 cut. 日/年 remain heads for 施行日/判決年.
TEMPORAL_NOUNS: Tuple[str, ...] = (
    "一昨日", "一昨年",
    "今日", "昨日", "明日",
    "今年", "昨年", "来年", "本年", "毎年", "翌年", "前年",
    "毎日",
    "今月", "先月", "来月",
    "本日", "当日", "翌日",
)
_TEMPORAL = frozenset(TEMPORAL_NOUNS)

REL_PREDICATES: Tuple[str, ...] = ("された", "する")

# Past / progressive relatives that look like された/する but are not.
# Longest first so していた wins over した.
_NEAR_MISS: Tuple[str, ...] = (
    "せられた", "されている", "される",
    "していた", "している", "した",
)

_NOMINALIZERS: Tuple[str, ...] = (
    "もの", "こと", "とき", "ため", "よう", "ほう", "ところ",
)

_TRAIL: Tuple[str, ...] = (
    "でしょうか", "だろうか", "ですか", "ますか",
    "とは", "って", "か", "は", "を", "が", "の",
)

_QWORDS: Tuple[str, ...] = (
    "何", "誰", "どこ", "いつ", "なぜ", "どう", "どれ", "どの",
)

_CONTENT = re.compile(
    r"[A-Za-zＡ-Ｚａ-ｚ][A-Za-z0-9Ａ-Ｚａ-ｚ０-９.+#_-]*"
    r"|[ァ-ヺー]+"
    r"|[㐀-䶿一-鿿0-9０-９]+"
)
_JA = re.compile(r"[぀-ゟ゠-ヺ㐀-䶿一-鿿]")
_TOPIC = re.compile(
    r"[㐀-䶿一-鿿ァ-ヺーA-Za-z0-9][はが][㐀-䶿一-鿿ァ-ヺーA-Za-z]"
)
_COORD = re.compile(
    r"[㐀-䶿一-鿿ァ-ヺーA-Za-z0-9]"
    r"(?:と|や|または|又は|若しくは|および|及び|並びに)"
    r"[㐀-䶿一-鿿ァ-ヺーA-Za-z]"
)
_MID_STOP = re.compile(r"[。！？](?!$)")

TOKENIZER = "surface-rules"


def _unknown(reason: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "verdict": "UNKNOWN_UNSEGMENTED",
        "reason": reason,
        "tokenizer": TOKENIZER,
    }
    out.update(extra)
    return out


def _strip(query: str) -> str:
    t = (query or "").strip()
    t = t.rstrip("?？。！! 　")
    for suf in _TRAIL:
        if t.endswith(suf) and len(t) > len(suf):
            t = t[:-len(suf)]
            break
    return t.strip()


def _head_of(run: str) -> Optional[str]:
    for h in HEAD_NOUNS:
        if run.endswith(h):
            return h
    return None


def _runs(text: str) -> List[re.Match]:
    return list(_CONTENT.finditer(text))


def _rightmost_headed(text: str) -> bool:
    rs = _runs(text)
    return bool(rs and _head_of(rs[-1].group(0)))


def _first_headed(text: str) -> bool:
    m = _CONTENT.search(text)
    return bool(m and _head_of(m.group(0)))


def _has_rel_pred(text: str) -> bool:
    return any(p in text for p in REL_PREDICATES)


def _bare_temporal_left(text: str) -> bool:
    """True when the left interval is exactly one frozen temporal noun."""
    return (text or "").strip() in _TEMPORAL


def _no_splits(left: str, right: str) -> bool:
    if not left or not right:
        return False
    headed = _rightmost_headed(left) and not _bare_temporal_left(left)
    left_ok = _has_rel_pred(left) or headed
    right_ok = _first_headed(right)
    return left_ok and right_ok


def _stage_parts(fragment: str) -> Tuple[str, str]:
    rs = _runs(fragment)
    if not rs:
        return fragment, ""
    last = rs[-1]
    run = last.group(0)
    table = _head_of(run)
    if table:
        if fragment.endswith(table):
            return fragment[:-len(table)], table
        return fragment, table
    # Unheaded rightmost noun keeps its okurigana (高さ, 大きさ).
    # Table heads never take this path, so 科された is not swallowed
    # into a head — those stages close on 者/物/先/….
    end = last.end()
    while end < len(fragment) and "ぁ" <= fragment[end] <= "ん":
        end += 1
    head = fragment[last.start():end]
    if fragment.endswith(head):
        return fragment[:-len(head)], head
    return fragment, head


def _licensed_rel_spans(text: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    for pred in REL_PREDICATES:
        start = 0
        while True:
            p = text.find(pred, start)
            if p < 0:
                break
            after = p + len(pred)
            m = _CONTENT.match(text, after)
            if m and _head_of(m.group(0)):
                spans.append((p, m.end()))
            start = p + 1
    return spans


def _inside(pos: int, spans: List[Tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def _abstain(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return _unknown("EMPTY")
    if not _JA.search(text):
        return _unknown("NO_JAPANESE")
    if "→" in text or "->" in text or "⇒" in text:
        return _unknown("HAS_ARROW")
    if _MID_STOP.search(text):
        return _unknown("MULTI_SENTENCE")
    if any(w in text for w in _QWORDS):
        return _unknown("QUESTION_WORD")
    if _COORD.search(text):
        return _unknown("COORDINATION")
    if _TOPIC.search(text):
        return _unknown("TOPIC_PARTICLE")
    if not _runs(text):
        return _unknown("NO_CONTENT")

    licensed = _licensed_rel_spans(text)
    for pred in REL_PREDICATES:
        start = 0
        while True:
            p = text.find(pred, start)
            if p < 0:
                break
            after = p + len(pred)
            if text.startswith("の", after):
                return _unknown("NOMINALIZER")
            if any(text.startswith(n, after) for n in _NOMINALIZERS):
                return _unknown("NOMINALIZER")
            m = _CONTENT.match(text, after)
            if m and not _head_of(m.group(0)):
                return _unknown("UNHEADED_RELATIVE")
            start = p + 1

    for m in _CONTENT.finditer(text):
        if m.start() == 0:
            continue
        prev = text[m.start() - 1]
        if prev not in "るたて":
            continue
        if not _head_of(m.group(0)):
            continue
        before = text[:m.start()]
        if before.endswith("された") or before.endswith("する"):
            continue
        return _unknown("UNLICENSED_RELATIVE")

    for pred in _NEAR_MISS:
        start = 0
        while True:
            p = text.find(pred, start)
            if p < 0:
                break
            after = p + len(pred)
            if not _inside(p, licensed) and _CONTENT.match(text, after):
                return _unknown("NEAR_MISS")
            start = p + 1
    return None


def _next_relative(text: str, i: int) -> Optional[Tuple[int, int, str]]:
    """Earliest licensed relative in text[i:]; returns (pred_start, head_end, head)."""
    best: Optional[Tuple[int, int, str]] = None
    for pred in REL_PREDICATES:
        start = i
        while True:
            p = text.find(pred, start)
            if p < 0:
                break
            after = p + len(pred)
            m = _CONTENT.match(text, after)
            if m:
                head = _head_of(m.group(0))
                if head and (best is None or p < best[0]):
                    best = (p, m.end(), head)
            start = p + 1
    return best


def _next_splitting_no(text: str, i: int) -> Optional[int]:
    start = i
    while True:
        p = text.find("の", start)
        if p < 0:
            return None
        if _no_splits(text[i:p], text[p + 1:]):
            return p
        start = p + 1


def split(query: str) -> Dict[str, Any]:
    """Split a nested Japanese question into an ordered stage chain.

    Successful verdict is STAGED: ``stages`` is innermost-first,
    ``chain`` is the arrow string `staged` could consume, ``spans`` /
    ``cuts`` are the raw offsets in the stripped surface. Failure is
    UNKNOWN_UNSEGMENTED with a closed reason code.
    """
    text = _strip(query)
    refused = _abstain(text)
    if refused is not None:
        return refused

    stages: List[Dict[str, Any]] = []
    i = 0
    n = len(text)
    while i < n:
        rel = _next_relative(text, i)
        no = _next_splitting_no(text, i)
        rel_at = rel[0] if rel else None
        if rel is not None and (no is None or rel_at < no):
            end = rel[1]
            fragment = text[i:end]
            if not fragment:
                return _unknown("EMPTY_STAGE")
            cond, head = _stage_parts(fragment)
            stages.append({
                "condition": cond,
                "head": head,
                "fragment": fragment,
                "span": [i, end],
            })
            i = end
            if i < n and text[i] == "の":
                i += 1
            continue
        if no is not None:
            fragment = text[i:no]
            if not fragment:
                return _unknown("EMPTY_STAGE")
            cond, head = _stage_parts(fragment)
            stages.append({
                "condition": cond,
                "head": head,
                "fragment": fragment,
                "span": [i, no],
            })
            i = no + 1
            continue
        fragment = text[i:]
        if not fragment:
            return _unknown("EMPTY_STAGE")
        cond, head = _stage_parts(fragment)
        stages.append({
            "condition": cond,
            "head": head,
            "fragment": fragment,
            "span": [i, n],
        })
        break

    if not stages:
        return _unknown("NO_CONTENT")
    if any(not s["fragment"] or not s["head"] for s in stages):
        return _unknown("EMPTY_STAGE")

    spans = [s["span"] for s in stages]
    cuts = [s["span"][1] for s in stages[:-1]]
    chain = " → ".join(s["fragment"] for s in stages)
    try:
        from .lang import ja_content_runs
        stage_terms = [ja_content_runs(s["fragment"]) for s in stages]
    except Exception:
        stage_terms = []
    return {
        "verdict": "STAGED",
        "stages": stages,
        "chain": chain,
        "spans": spans,
        "cuts": cuts,
        "stage_terms": stage_terms,
        "tokenizer": TOKENIZER,
        "text": text,
    }


def as_staged_query(result: Dict[str, Any]) -> Optional[str]:
    """The arrow string `stacked.staged` accepts, or None if unusable."""
    if result.get("verdict") != "STAGED":
        return None
    chain = result.get("chain") or ""
    if "→" not in chain:
        return None
    return chain


def regression() -> Dict[str, Any]:
    """Fork-equivalent: the no-split defense and the flagship 3-cut."""
    tokyo = split("東京の人口")
    fuji = split("富士山の高さ")
    flag = split("背任罪の刑の上限を科された者の再審請求先")
    coord = split("殺人罪と傷害罪の刑の上限")
    case = split("上限を科された場合の手続")
    year = split("今年の予算額")
    yest = split("昨日の提出先")
    cap = split("殺人罪の刑の上限")
    heads = [s["head"] for s in (flag.get("stages") or [])]
    cap_heads = [s["head"] for s in (cap.get("stages") or [])]
    ok = all([
        tokyo.get("verdict") == "STAGED" and len(tokyo.get("stages") or []) == 1,
        fuji.get("verdict") == "STAGED" and len(fuji.get("stages") or []) == 1,
        flag.get("verdict") == "STAGED" and len(flag.get("stages") or []) == 3,
        heads == ["罪", "者", "先"],
        flag.get("chain") == "背任罪 → 刑の上限を科された者 → 再審請求先",
        coord.get("verdict") == "UNKNOWN_UNSEGMENTED",
        case.get("verdict") == "UNKNOWN_UNSEGMENTED",
        year.get("verdict") == "STAGED" and len(year.get("stages") or []) == 1,
        yest.get("verdict") == "STAGED" and len(yest.get("stages") or []) == 1,
        cap.get("verdict") == "STAGED" and len(cap.get("stages") or []) == 2,
        cap.get("chain") == "殺人罪 → 刑の上限",
        cap_heads == ["罪", "上限"],
        HEAD_NOUNS[0] == "場所" and len(HEAD_NOUNS) == 10,
        "今年" in _TEMPORAL and "昨日" in _TEMPORAL,
        TOKENIZER == "surface-rules",
    ])
    return {
        "experiment": "stage_split",
        "fork": "STAGE_SPLIT_DEFENSE",
        "pass": bool(ok),
        "result": {
            "tokyo_n": len(tokyo.get("stages") or []),
            "flag_heads": heads,
            "flag_chain": flag.get("chain"),
            "coord": coord.get("verdict"),
            "case": case.get("verdict"),
            "year_n": len(year.get("stages") or []),
            "yest_n": len(yest.get("stages") or []),
            "cap_chain": cap.get("chain"),
        },
    }
