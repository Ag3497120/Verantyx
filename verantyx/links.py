"""Connections a source does not print — held apart from what it does.

    民法第七百九条
    「故意又は過失によって他人の権利…を侵害した者は、…損害を賠償する責任を負う。」

That article defines 不法行為 and does not contain the word. Measured: an
external key of topic→article assignments was reachable 26.7% of the time,
word-form bridging took it to 73.3%, and the residual is entirely of this
kind — 刑事訴訟法第二百十三条 and 労働組合法第八条 are cited under 不法行為
by a source that knows the doctrine, and neither article says so.

Raising the per-article index from 8 terms to 64 moved the links from
78,103 to 182,608 and the recall not at all. **What a text does not say
cannot be indexed out of it.** The connection has to come from a different
source, and then it has to stay visibly different.

## Why a separate layer rather than more facets

Writing 不法行為 onto 刑事訴訟法第二百十三条 would make the store say the
statute says it. Everything downstream — the coverage gate, contradiction
detection, the citation shown to a reader — treats a facet as something the
source printed. A doctrinal link is a third party's claim ABOUT two things,
and it carries its own provenance, its own reliability, and its own way of
being wrong.

So links live here, keyed by their own source, and a reader always sees
which of the two they are being shown:

    printed   the article contains the term
    linked    an outside source connects them, and names itself

`resolve()` returns both, labelled. Nothing merges them.

## What this is not

Not inference. A link is an assertion someone else published, recorded with
attribution and no attempt to check it. An encyclopedia that is wrong about
which article governs something will make this wrong in the same way and
say who to blame.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

#: Statutes whose citations are recognised. Closed on purpose: a general
#: "NAME第N条" pattern also matches 就業規則第3条 and 定款第5条, which are not
#: statutes and would attach a doctrine to a document nobody can look up.
DEFAULT_LAWS: Tuple[str, ...] = (
    "民法", "刑法", "商法", "会社法", "民事訴訟法", "刑事訴訟法",
    "労働基準法", "労働組合法", "労働契約法", "労働安全衛生法", "最低賃金法",
    "著作権法", "特許法", "商標法", "意匠法", "不正競争防止法",
    "消費者契約法", "割賦販売法", "消費者基本法", "製造物責任法",
    "災害対策基本法", "災害救助法", "消防法", "建築基準法", "水防法",
    "気象業務法", "放送法", "電波法", "電気通信事業法",
    "行政手続法", "行政不服審査法", "国家賠償法", "行政事件訴訟法",
    "少年法", "軽犯罪法", "借地借家法", "犯罪被害者等基本法",
)

_KANJI_DIGITS = "〇一二三四五六七八九十百千"
_UNITS = "〇一二三四五六七八九"


def _to_kanji(num: str) -> str:
    """21 -> 二十一. Citations are written in arabic and cores in kanji.

    Only up to 999: article numbers run higher, and a wrong conversion
    would file a doctrine under an article that exists but is not the one
    meant, which is worse than filing none.
    """
    if not re.fullmatch(r"[0-9０-９]+", num):
        return num
    n = int(num.translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    if n < 10:
        return _UNITS[n]
    if n < 100:
        return ("" if n // 10 == 1 else _UNITS[n // 10]) + "十" + \
               ("" if n % 10 == 0 else _UNITS[n % 10])
    if n < 1000:
        out = ("" if n // 100 == 1 else _UNITS[n // 100]) + "百"
        rest = n % 100
        if rest >= 10:
            out += ("" if rest // 10 == 1 else _UNITS[rest // 10]) + "十"
        if rest % 10:
            out += _UNITS[rest % 10]
        return out
    return num


def _pattern(laws: Sequence[str]) -> "re.Pattern":
    names = "|".join(re.escape(x) for x in sorted(laws, key=len, reverse=True))
    return re.compile(f"({names})(?:第)?([0-9０-９{_KANJI_DIGITS}]{{1,8}})条")


@dataclass
class LinkSet:
    """topic -> articles, with the source that said so."""

    by_topic: Dict[str, Dict[str, Set[str]]] = field(default_factory=dict)

    def add(self, topic: str, article: str, source: str) -> None:
        self.by_topic.setdefault(topic, {}).setdefault(article, set()).add(source)

    def articles(self, topic: str) -> List[str]:
        return sorted(self.by_topic.get(topic, {}))

    def sources(self, topic: str, article: str) -> List[str]:
        return sorted((self.by_topic.get(topic) or {}).get(article, ()))

    def n_links(self) -> int:
        return sum(len(v) for v in self.by_topic.values())

    def report(self) -> Dict[str, Any]:
        return {"topics": len(self.by_topic), "links": self.n_links(),
                "sources": len({s for v in self.by_topic.values()
                                for ss in v.values() for s in ss})}

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(
            {t: {a: sorted(s) for a, s in v.items()}
             for t, v in sorted(self.by_topic.items())},
            ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LinkSet":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        ls = cls()
        ls.by_topic = {t: {a: set(s) for a, s in v.items()}
                       for t, v in raw.items()}
        return ls


def harvest(
    paths: Iterable[Path],
    *,
    laws: Sequence[str] = DEFAULT_LAWS,
    topic_from: str = "stem",
) -> LinkSet:
    """Read documents and record which articles each says a topic involves.

    ``topic_from="stem"`` takes the topic from the filename, which is how an
    encyclopedia dump is organised: the file IS the topic. The source
    recorded is that same filename, so a link can always be traced back to
    the document that asserted it.
    """
    pat = _pattern(laws)
    ls = LinkSet()
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue
        topic = path.stem if topic_from == "stem" else str(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for law, num in pat.findall(text):
            ls.add(topic, f"{law}第{_to_kanji(num)}条", topic)
    return ls


def resolve(
    fields: Dict[str, Dict[str, Any]],
    links: LinkSet,
    topic: str,
    *,
    limit: int = 12,
) -> Dict[str, Any]:
    """Both kinds of answer for one topic, labelled and never merged.

    printed   an article whose own text carries the term
    linked    an article an outside source connects to it, with that source

    A reader has to be able to tell these apart. The first is what the
    legislature wrote; the second is what somebody says about it, and only
    one of them is evidence.
    """
    printed: List[Dict[str, Any]] = []
    for fname, leaves in fields.items():
        for leaf, store in leaves.items():
            for core, cross in store.crosses.items():
                if topic in cross:
                    printed.append({"article": core, "field": fname, "leaf": leaf})
                    break
            if len(printed) >= limit:
                break

    home: Dict[str, Tuple[str, str]] = {}
    for fname, leaves in fields.items():
        for leaf, store in leaves.items():
            for core in store.crosses:
                home.setdefault(core, (fname, leaf))

    linked: List[Dict[str, Any]] = []
    for art in links.articles(topic):
        if any(p["article"] == art for p in printed):
            continue
        where = home.get(art)
        linked.append({
            "article": art,
            "field": where[0] if where else None,
            "leaf": where[1] if where else None,
            "in_store": where is not None,
            "asserted_by": links.sources(topic, art),
        })
    return {
        "topic": topic,
        "printed": printed[:limit],
        "linked": linked[:limit],
        "n_printed": len(printed),
        "n_linked": len(linked),
    }
