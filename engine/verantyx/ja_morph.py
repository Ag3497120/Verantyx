"""Query-side word-form bridging — 傷害罪 must reach 傷害.

Measured against an external answer key (topics that ja.wikipedia states
belong to a specific article), recall was 26.7%, and 46.7% of the total
failed for one reason: the word the outside world uses is not the word the
statute prints.

    外部が問う    store が持つ
    傷害罪        傷害          刑法第二百四条の見出しは（傷害）
    建築確認      確認
    殺人罪        殺人

Nothing is missing from the store. The two strings simply do not match, and
this engine has no morphology, so 46.7% of a real question set could not
begin.

## Why this expands the QUERY and never the store

A store is evidence. Writing 傷害罪 into it because 傷害 is there would put
a word the legislature did not print next to a citation of what it did,
and every downstream reader — the coverage gate, the contradiction
detector, the provenance trail — would treat it as something the source
said. The same discipline that keeps accepted repairs out of the shipped
grammar applies here: the reading may be widened, the record may not.

So `variants()` is consulted where a query is matched against terms, and
the store is untouched. Turning it off restores the previous behaviour
exactly.

## Why the list is short and closed

Every entry is a claim about Japanese that a lawyer or a doctor could
check, and a long speculative table is a liability in the setting this was
built for. These are nominal suffixes that name the KIND of a thing without
changing which thing it is: 傷害 and 傷害罪 pick out the same conduct, and
one of them is what the code prints. Suffixes that change reference —
被〜, 反〜, 準〜, 〜未遂 — are deliberately absent, because 殺人 and
殺人未遂 are not the same article and bridging them would fabricate.
"""
from __future__ import annotations

from typing import Iterable, List, Set

#: Nominal suffixes that name a kind without changing the referent. Ordered
#: longest-first so 権利 is not stripped to 権 by a shorter rule.
STRIPPABLE: tuple = (
    "に関する法律", "に関する規則",
    "行為", "制度", "手続", "処分",
    "罪", "権", "法", "税", "料", "費", "額", "率", "性", "化", "等", "類",
)

#: Suffixes worth ADDING to a bare query: the store often holds the plain
#: noun and the asker adds the kind. Kept much shorter than STRIPPABLE,
#: because adding is the direction that invents strings.
ADDABLE: tuple = ("罪", "権", "法", "行為")

#: Below this a "stem" is not a word. 罪 stripped from 犯罪 leaves 犯, which
#: matches nothing useful and everything noisy.
MIN_STEM = 2

#: A four-plus character kanji compound is usually modifier + head, and the
#: two halves are words: 建築確認 = 建築 + 確認, and the statute prints 建築.
#: Split only at the midpoint of an even-length all-kanji run — offering
#: every cut point would turn one query into a handful of fragments.
_KANJI = "㐀-䶿一-鿿"


def _is_kanji_run(s: str) -> bool:
    import re
    return bool(re.fullmatch(f"[{_KANJI}]+", s))


def variants(term: str, *, add: bool = True, split: bool = True) -> List[str]:
    """The forms of ``term`` worth looking for, original first.

    Deterministic and order-stable: a caller that takes the first match gets
    the same answer every run, and the original always wins a tie.
    """
    t = (term or "").strip()
    if not t:
        return []
    out: List[str] = [t]
    seen: Set[str] = {t}

    def push(s: str) -> None:
        if len(s) >= MIN_STEM and s not in seen:
            seen.add(s)
            out.append(s)

    stripped = False
    for suf in STRIPPABLE:
        if t.endswith(suf) and len(t) - len(suf) >= MIN_STEM:
            push(t[: -len(suf)])
            stripped = True
            break

    if split and len(t) >= 4 and len(t) % 2 == 0 and _is_kanji_run(t):
        half = len(t) // 2
        push(t[half:])   # head first — 建築確認 is a kind of 確認
        push(t[:half])

    # Adding a suffix to a word that already carries one produces strings
    # nobody wrote: 傷害罪 -> 傷害罪権. Only bare nouns get the addition.
    if add and not stripped:
        for suf in ADDABLE:
            if not t.endswith(suf):
                push(t + suf)
    return out


def expand(terms: Iterable[str], *, add: bool = True,
           split: bool = True) -> List[str]:
    """variants() over a query's runs, de-duplicated, order preserved."""
    out: List[str] = []
    seen: Set[str] = set()
    for t in terms:
        for v in variants(t, add=add, split=split):
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def matches(term: str, vocabulary: Set[str], *, add: bool = True,
            split: bool = True) -> List[str]:
    """Which forms of ``term`` the vocabulary actually holds, best first."""
    return [v for v in variants(term, add=add, split=split) if v in vocabulary]
