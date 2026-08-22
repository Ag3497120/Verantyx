"""Lexical hygiene for mass pour: junk filters, proper-noun compounding,
sense channels.

順に (1) 機能語崩れ core の遮断 ("however", "two", "s", 数字…)、
(2) 連続大文字語の複合語化 ("Sun Tzu" → "sun_tzu")、
(3) 固有名チャネル分離 (core#p) — "sun" (common) と "sun_tzu#p" /
"paris#p" (proper) を別十字に。表層規則のみ・決定論・LM なし。
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Set, Tuple

from .en_decompose import is_function_role, tag_role

PROPER_SUFFIX = "#p"

# 接続副詞・数量・数詞・断片 — 初歩 POS が NOUN と誤認する常連。
STOP_CORES: Set[str] = {
    # conjunctive / temporal adverbs
    "however", "later", "also", "thus", "moreover", "therefore", "meanwhile",
    "instead", "further", "furthermore", "finally", "eventually", "currently",
    "recently", "previously", "initially", "originally", "additionally",
    "again", "often", "sometimes", "usually", "especially", "particularly",
    "still", "yet", "soon", "now", "then", "here", "there", "once", "twice",
    "well", "early", "late", "far", "away", "back", "even", "only", "just",
    # quantifiers / determin-ish
    "some", "all", "many", "most", "few", "several", "both", "each", "every",
    "none", "other", "others", "another", "such", "same", "more", "less",
    "much", "own", "any", "enough", "either", "neither",
    # number words / ordinals
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "twenty", "thirty", "forty", "fifty",
    "hundred", "thousand", "million", "billion",
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth",
    # contraction fragments
    "s", "t", "d", "ll", "m", "re", "ve", "nt",
    # prepositions / connectives the elementary POS misses
    "no", "not", "despite", "since", "although", "though", "while", "during",
    "including", "according", "throughout", "unlike", "via", "per", "versus",
    "amid", "toward", "towards", "onto", "beyond", "except", "unless",
    "until", "whether", "because", "due",
    # HTML entity fragments (news markup: &lt; &quot; …)
    "lt", "gt", "quot", "amp", "nbsp", "apos", "mdash", "ndash", "hellip",
}

_YEAR = re.compile(r"^\d{4}$")


def norm_words(sym: str) -> Set[str]:
    """Compound/namespaced key → constituent words.

    "sun_tzu#p" → {sun, tzu} (proper-noun compounding, underscore)
    "contest:2026h1" → {contest, 2026h1} (structured key:value facet,
    colon) — needed so a natural-language query ("what is contest:2026h1")
    can ground against a hand-structured record the same way it grounds
    against an ordinary word, instead of treating the whole namespaced
    string as one indivisible token.
    """
    base = sym[: -len(PROPER_SUFFIX)] if sym.endswith(PROPER_SUFFIX) else sym
    return {w for w in re.split(r"[_:]", base) if w}


def display_sym(sym: str) -> str:
    base = sym[: -len(PROPER_SUFFIX)] if sym.endswith(PROPER_SUFFIX) else sym
    return base.replace("_", " ")


def is_proper_key(sym: str) -> bool:
    return sym.endswith(PROPER_SUFFIX)


def is_junk_core(tok: str) -> bool:
    """A token that must never stand as a core.

    STOP_CORES is a hand-written list of 139 words and it was the ONLY
    lexical test here — so 26 of 27 basic English function words walked
    straight through it, and `the` stands in the ja store as a core with
    **6,074 facets** (measured 2026-08-19). Meanwhile `_cap_content` a few
    lines below has been consulting the role tagger the whole time, and the
    tagger already knows: the=DET, of=ADP, is=AUX — 25/25 function words
    judged correctly, 8/8 content words left alone, and 15/15 Japanese cores
    (正当防衛, 時効, 経費 …) tagged NOUN so nothing Japanese is touched.

    Implemented, and unreached from this one function. The list stays — the
    tagger is layered on top of it, not swapped for it.
    """
    tok = tok.casefold().strip()
    if len(tok) < 2:
        return True
    if tok in STOP_CORES:
        return True
    if not any(c.isalpha() for c in tok):
        return True
    if is_function_role(tag_role(tok)):
        return True
    return False


def is_junk_facet(tok: str) -> bool:
    tok = tok.casefold().strip()
    if _YEAR.match(tok):
        return False  # years may be legitimate facts
    return is_junk_core(tok)


def _cap_content(raw: str) -> bool:
    """Capitalized alphabetic token that is not a function word."""
    if not raw or not raw[0].isupper():
        return False
    core = re.sub(r"[^A-Za-z']", "", raw)
    if len(core) < 2 or not core.isalpha():
        return False
    return not is_function_role(tag_role(core.casefold()))


def proper_runs(text: str) -> List[List[str]]:
    """Runs of ≥2 consecutive capitalized content words (lowercased).

    Sentence-initial runs count too ("Sun Tzu wrote…"); a leading function
    word ("The Big Apple") is dropped from the run boundary by _cap_content.
    """
    toks = (text or "").split()
    runs: List[List[str]] = []
    cur: List[str] = []
    for raw in toks:
        if _cap_content(raw):
            cur.append(re.sub(r"[^A-Za-z']", "", raw).casefold())
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def proper_singles(text: str) -> Set[str]:
    """Mid-sentence capitalized single content words (lowercased)."""
    toks = (text or "").split()
    out: Set[str] = set()
    for i, raw in enumerate(toks):
        if i == 0:
            continue  # sentence-initial capitalization is ambiguous
        if _cap_content(raw):
            prev_cap = _cap_content(toks[i - 1])
            next_cap = i + 1 < len(toks) and _cap_content(toks[i + 1])
            if not prev_cap and not next_cap:
                out.add(re.sub(r"[^A-Za-z']", "", raw).casefold())
    return out


def sense_key(
    core: str,
    text: str,
    runs: Optional[Sequence[Sequence[str]]] = None,
    proper_lexicon: Optional[Set[str]] = None,
) -> Tuple[str, List[str]]:
    """Core token → (channel key, run members to drop from facts).

    - core inside a proper run → joined "a_b#p", members dropped from facts
    - mid-sentence capitalized single → "core#p"
    - sentence-initial capitalized, but corpus statistics say the word is
      predominantly a name (``proper_lexicon``) → "core#p"  (二段判定)
    - else common channel "core"
    """
    runs = list(runs) if runs is not None else proper_runs(text)
    for run in runs:
        if core in run:
            return "_".join(run) + PROPER_SUFFIX, [w for w in run if w != core]
    if core in proper_singles(text):
        return core + PROPER_SUFFIX, []
    if proper_lexicon and core in proper_lexicon:
        toks = (text or "").split()
        if toks and _cap_content(toks[0]):
            first = re.sub(r"[^A-Za-z']", "", toks[0]).casefold()
            if first == core:
                return core + PROPER_SUFFIX, []
    return core, []


def update_cap_stats(stats: dict, text: str) -> None:
    """word → [n_capitalized_mid_sentence, n_lowercase] を累積 (pass 1)."""
    toks = (text or "").split()
    for i, raw in enumerate(toks):
        word = re.sub(r"[^A-Za-z']", "", raw)
        if len(word) < 2 or not word.isalpha():
            continue
        key = word.casefold()
        cell = stats.setdefault(key, [0, 0])
        if i > 0 and raw[0].isupper():
            cell[0] += 1
        elif raw[0].islower():
            cell[1] += 1


def proper_lexicon_from_stats(
    stats: dict, *, min_cap: int = 3, ratio: float = 0.7
) -> Set[str]:
    """文中大文字率が高い語 = 名前として扱う語彙 (二段判定用)."""
    out: Set[str] = set()
    for word, (cap, low) in stats.items():
        if cap >= min_cap and cap / max(1, cap + low) >= ratio:
            out.add(word)
    return out
