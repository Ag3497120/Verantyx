"""A language model's embedding table, used as the static dictionary it is.

The idea under test was: a local model (jgen) as a dictionary — not chat, not
generation, a lookup. `jgen_forge` already builds the artifact (`--parts
lexicon`: embed table, lm_head, final norm, nothing else), so the question was
never "can we", it was "for WHICH questions is a frozen embedding table a
trustworthy dictionary". Measured on qwen3.5:4b against this project's own
vocabulary before a line of this module existed:

    state-likeness   USABLE. Is this word the KIND of word that can carry a
                     pole? Similarity to the known-vocabulary centroid minus
                     similarity to a generic-noun centroid separated the real
                     proposal queue perfectly: 舗装損傷 +0.124, 停電 +0.163,
                     解消 +0.122 (the true candidates) against 八代支店 −0.159,
                     地区 −0.277 (the false ones). Unseen state words landed
                     right too: 滞留 +0.087, 孤立 +0.081, 冠水 +0.034.

    nearest known    USABLE AS SEARCH. 冠水→断水 (0.50), 停電→停止 (0.42) —
                     shown to the operator as context, and a high-similarity
                     neighbour is a reasonable aspect hint. But 解消's
                     neighbours include 再開 AND 受付終了 — both poles sit
                     together, which is the next line's problem.

    polarity         FORBIDDEN. Leave-one-out on the 31 known terms: 54.8%,
                     a coin flip. 危険/安全, 有効/無効, 断水/復旧 — opposite
                     poles live in the same contexts, so a static table
                     cannot tell them apart, and this module deliberately has
                     no function that returns one. Polarity comes from the
                     succession slot's grammar and from a person, as before.

So the model annotates and ranks; it approves nothing. The acceptance
asymmetry from `vocab_growth` is unchanged — a person still makes the one
judgement per word — this just sorts the queue so the judgements that are
probably real come first, and shows the dictionary context beside them.

Runtime shape: pure stdlib, no inference engine, no numpy, no network. The
jgen is opened, the header walked once, and only the rows a word's tokens
name are ever read — a dictionary lookup in the file-format sense too. The
tokenizer is pluggable; `tokenizers` (the HF wheel) is used when installed,
and when it is not, annotation silently does not happen rather than half-
happening.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

#: Generic-noun anchors for the other end of the state-likeness axis. Chosen
#: as the kinds of words the real queue wrongly proposed — places, buildings,
#: administrative nouns — and fixed here so a score means the same thing on
#: every machine.
GENERIC_ANCHORS = ("市役所", "支店", "地区", "学校", "住民", "道路", "公園", "窓口")

#: Where an operator's home points the loop at a lexicon, if they have one.
CONFIG = "lexicon.json"


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: List[float]) -> Optional[List[float]]:
    n = _dot(v, v) ** 0.5
    return [x / n for x in v] if n > 1e-9 else None


class LexiconDict:
    """Row-level reads over a jgen embed table. Open once, look up words."""

    def __init__(self, jgen: Path, tokenize: Callable[[str], List[int]]):
        self.path = Path(jgen)
        self.tokenize = tokenize
        self._rows = 0
        self._cols = 0
        self._embed_at = -1
        self._cache: Dict[str, Optional[List[float]]] = {}
        self._walk_header()

    def _walk_header(self) -> None:
        with self.path.open("rb") as f:
            if f.read(4) != b"JGEN":
                raise ValueError(f"{self.path.name} is not a jgen file")
            _ver, count = struct.unpack("<II", f.read(8))
            for _ in range(count):
                nlen, = struct.unpack("<H", f.read(2))
                name = f.read(nlen).decode()
                ttype, = struct.unpack("<B", f.read(1))
                if ttype == 2:
                    rows, cols = struct.unpack("<II", f.read(8))
                    if "embed" in name:
                        self._rows, self._cols = rows, cols
                        self._embed_at = f.tell()
                        return
                    f.seek(rows * cols * 2, 1)
                elif ttype == 3:
                    n, = struct.unpack("<I", f.read(4))
                    f.seek(n * 2, 1)
                elif ttype == 1:
                    r, c, k = struct.unpack("<III", f.read(12))
                    f.seek((r * k + k + c * k + c + r + k * k) * 2, 1)
                else:
                    raise ValueError(f"unknown tensor type {ttype} in {name}")
        raise ValueError(f"no embed table in {self.path.name}")

    def _row(self, f, i: int) -> List[float]:
        f.seek(self._embed_at + i * self._cols * 2)
        return list(struct.unpack(f"<{self._cols}e", f.read(self._cols * 2)))

    def vector(self, word: str) -> Optional[List[float]]:
        """Mean-pooled, normalized — or None when the tokenizer yields nothing."""
        if word in self._cache:
            return self._cache[word]
        ids = [i for i in (self.tokenize(word) or []) if 0 <= i < self._rows]
        out: Optional[List[float]] = None
        if ids:
            with self.path.open("rb") as f:
                acc = [0.0] * self._cols
                for i in ids:
                    for j, x in enumerate(self._row(f, i)):
                        acc[j] += x
            out = _norm([x / len(ids) for x in acc])
        self._cache[word] = out
        return out

    # -- the two measured-usable questions ---------------------------------

    def state_likeness(self, word: str, known_terms: List[str]) -> Optional[float]:
        """How much the word lives with the state vocabulary rather than with
        generic nouns. Positive separated every true candidate from every
        false one on the real queue; still an annotation, never a verdict."""
        v = self.vector(word)
        if v is None:
            return None
        state = self._centroid(known_terms)
        generic = self._centroid(list(GENERIC_ANCHORS))
        if state is None or generic is None:
            return None
        return round(_dot(v, state) - _dot(v, generic), 4)

    def nearest(self, word: str, known_terms: List[str], k: int = 3
                ) -> List[Tuple[str, float]]:
        """The dictionary-search half: closest known terms, for a human to
        read. A high-similarity neighbour is a fair aspect hint; its POLE is
        not, and nothing here pretends otherwise."""
        v = self.vector(word)
        if v is None:
            return []
        scored = []
        for t in known_terms:
            u = self.vector(t)
            if u is not None and t != word:
                scored.append((t, round(_dot(v, u), 3)))
        return sorted(scored, key=lambda x: -x[1])[:k]

    def _centroid(self, words: List[str]) -> Optional[List[float]]:
        vs = [v for v in (self.vector(w) for w in words) if v is not None]
        if not vs:
            return None
        return _norm([sum(col) / len(vs) for col in zip(*vs)])


def hf_tokenizer(path: Path) -> Optional[Callable[[str], List[int]]]:
    """The pluggable default: HF `tokenizers` when installed, else None —
    and None means annotation does not happen, not that it half-happens."""
    try:
        from tokenizers import Tokenizer  # type: ignore
    except ImportError:
        return None
    tok = Tokenizer.from_file(str(path))
    return lambda w: tok.encode(w, add_special_tokens=False).ids


def open_configured(home: Path) -> Optional[LexiconDict]:
    """The operator's lexicon, if their home names one.

    ~/.verantyx-audit/lexicon.json:
        {"jgen": "/path/to/x_lexicon_full.jgen",
         "tokenizer": "/path/to/x.jgen.tokenizer/tokenizer.json"}
    """
    cfg = Path(home) / CONFIG
    if not cfg.exists():
        return None
    try:
        raw = json.loads(cfg.read_text(encoding="utf-8"))
        jgen, tok_path = Path(raw["jgen"]), Path(raw["tokenizer"])
    except (ValueError, KeyError):
        return None
    if not (jgen.exists() and tok_path.exists()):
        return None
    tokenize = hf_tokenizer(tok_path)
    if tokenize is None:
        return None
    try:
        return LexiconDict(jgen, tokenize)
    except ValueError:
        return None


def annotate(proposals: List[Dict[str, Any]], home: Path) -> List[Dict[str, Any]]:
    """Attach the dictionary's two usable answers and sort the queue by them.

    Proposals without a lexicon pass through untouched, in their original
    order. Nothing is dropped and nothing is accepted on a score: the score
    exists so the person reads the probably-real candidates first, with the
    dictionary context beside them.
    """
    lex = open_configured(home)
    if lex is None:
        return proposals
    from .ja_grammar import ASPECT_OF

    known = sorted(ASPECT_OF)
    for row in proposals:
        word = row.get("word")
        if not word or row.get("status") != "proposed":
            continue
        score = lex.state_likeness(word, known)
        if score is None:
            continue
        row["lexicon"] = {
            "state_likeness": score,
            "nearest_known": lex.nearest(word, known),
            "read_this_as": (
                "annotation only — the same model scored 54.8% on polarity, "
                "so which pole the word is stays with the slot grammar and "
                "with you"
            ),
        }
    def _key(r: Dict[str, Any]) -> float:
        got = (r.get("lexicon") or {}).get("state_likeness")
        return -got if isinstance(got, (int, float)) else 1.0
    proposals.sort(key=_key)
    return proposals
