"""Predicate profiles — which predicates co-occur with each subject.

Hand-off-side sidecar, never a census. `extract` walks (title, lead) pairs
and counts deterministic predicate tokens per title. No LLM, no generation.
A morphological analyzer is used when one is importable; otherwise a closed
heuristic (verb-ending candidates and 「〜である」-style frames). The chosen
extractor is recorded on the saved JSON as the top-level ``extractor`` key.

Saved at ~/Projects/vera-corpus/build/predicate_profiles.json as

    {subject: {"predicates": {pred: n}, "total": N}}

plus that ``extractor`` key. Raw counts; the reader normalizes.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

OUT = (corpus_root() / "build"
       / "predicate_profiles.json")

# ---------------------------------------------------------------------------
# Extractor probe — first importable analyzer wins; else the heuristic.
# ---------------------------------------------------------------------------

_ANALYZER_MODULES = ("MeCab", "mecab", "fugashi", "janome", "sudachipy")


def _probe_analyzer() -> Optional[str]:
    for name in _ANALYZER_MODULES:
        try:
            __import__(name)
        except ImportError:
            continue
        return name
    return None


ANALYZER = _probe_analyzer()
EXTRACTOR = ANALYZER if ANALYZER else "heuristic"


# ---------------------------------------------------------------------------
# Heuristic: verb-ending candidates + 「〜である」-style frames.
# ---------------------------------------------------------------------------

#: Definitional / copular frames, longest first so 「のことである」 wins
#: over 「である」. The emitted predicate is the frame itself.
_FRAMES: Tuple[str, ...] = (
    "のことである", "の一種である", "の総称である", "の名称である",
    "と呼ばれている", "と呼ばれた", "と呼ばれる",
    "とされている", "とされた", "とされる",
    "といわれている", "といわれる",
    "を意味する", "を指している", "を指す",
    "にあたる", "に当たる",
    "であった", "である",
    "でした", "です",
    "だった",
    "のこと", "の一種", "の総称",
)

#: サ変 / 受身 / 可能 and a few light auxiliaries, longest first.
#: Stem + this ending is the candidate; the ending is then folded to a
#: dictionary-like form so 関与した and 関与する do not split the count.
_SURU_END: Tuple[str, ...] = (
    "されている", "されていた", "させられる", "させられた",
    "している", "していた",
    "される", "された", "させる", "させた",
    "できる", "できた",
    "する", "した", "して",
)

#: Native-verb endings, longest first. Dictionary godan/ichidan endings
#: plus visible れる/られる. Past-tense folding (った→る) is refused —
#: 持った must not become 持る.
_NATIVE_END: Tuple[str, ...] = (
    "られている", "られていた", "れている", "れていた",
    "られる", "られた", "れる", "れた",
    "っている", "っていた",
    "る", "う", "く", "ぐ", "す", "つ", "ぬ", "ぶ", "む",
)

#: Bare auxiliaries / light verbs that are not a subject's predicate.
_STOP = frozenset({
    "ある", "いる", "なる", "する", "できる", "いう", "言う",
    "よる", "おく", "みる", "見る", "くる", "来る", "いく", "行く",
    "もつ", "持つ", "おる", "てる", "てる",
})

_PAREN = re.compile(r"（[^）]*）|\([^)]*\)")
_REF = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_KANJI = re.compile(r"[㐀-䶿一-鿿々〆〇]")
_KATA = re.compile(r"[ァ-ヺー]")
_HIRA = re.compile(r"[ぁ-ん]")
_CONTENT = re.compile(r"[㐀-䶿一-鿿々〆〇ァ-ヺーぁ-ん]")

#: A filled 「〜である」 frame: the last 2–6 character content run glued
#: to the copula, so 総称である is distinct from a bare である.
_FILLED_DEARU = re.compile(
    r"([㐀-䶿一-鿿々〆〇ァ-ヺー]{2,6})"
    r"(のことである|の一種である|の総称である|である|であった|です|でした)"
)


def _strip_noise(lead: str) -> str:
    text = lead or ""
    text = (text.replace("&lt;", "<").replace("&gt;", ">")
            .replace("&amp;", "&").replace("&quot;", '"')
            .replace("&nbsp;", " "))
    text = _REF.sub("", text)
    text = _TAG.sub("", text)
    return _PAREN.sub("", text)


def _fold_suru(stem: str, end: str) -> str:
    if end.startswith("され") or end.startswith("させ"):
        return stem + "される"
    if end.startswith("でき"):
        return stem + "できる"
    return stem + "する"


def _fold_native(stem: str, end: str) -> str:
    if "られ" in end:
        return stem + "られる"
    if end.startswith("れ"):
        return stem + "れる"
    if end.startswith("って"):
        return stem + "る"
    return stem + end


def _is_stem(s: str) -> bool:
    if not s or s in _STOP:
        return False
    if not _CONTENT.search(s):
        return False
    # A stem that is only hiragana is almost always a particle/aux.
    if _HIRA.fullmatch(s):
        return False
    return True


def _stem_before(text: str, i: int, *, kind: str) -> str:
    """Content stem immediately left of an ending at index ``i``."""
    j = i
    if kind == "native":
        # 伝わ / 流れ — okurigana belongs to the stem, not the ending.
        n_hira = 0
        while j > 0 and _HIRA.match(text[j - 1]) and n_hira < 3:
            j -= 1
            n_hira += 1
        n_kan = 0
        while j > 0 and (_KANJI.match(text[j - 1]) or _KATA.match(text[j - 1])):
            j -= 1
            n_kan += 1
            if n_kan >= 4:
                break
    else:
        while j > 0 and _CONTENT.match(text[j - 1]):
            ch = text[j - 1]
            if _HIRA.match(ch):
                break
            j -= 1
            if i - j >= 8:
                break
    return text[j:i]


def _ok_native(stem: str, end: str) -> bool:
    """Reject 作者る (bare 漢字+る, no okurigana) but keep 作る / 伝わる."""
    if not _is_stem(stem):
        return False
    kan = len(_KANJI.findall(stem))
    hira = len(_HIRA.findall(stem))
    if hira:
        return True
    if end[0] in "うれ" and kan == 1:
        return True
    if end[0] in "くぐすつぬぶむ" and kan <= 2:
        return True
    return False


def _heuristic_predicates(lead: str) -> List[str]:
    text = _strip_noise(lead)
    if not text:
        return []
    found: List[str] = []
    claimed = [False] * len(text)

    def claim(a: int, b: int) -> None:
        for k in range(a, min(b, len(claimed))):
            claimed[k] = True

    # Frames first (longest match at each index).
    i = 0
    while i < len(text):
        hit = None
        for fr in _FRAMES:
            if text.startswith(fr, i):
                hit = fr
                break
        if hit:
            found.append(hit)
            claim(i, i + len(hit))
            i += len(hit)
            continue
        i += 1

    for m in _FILLED_DEARU.finditer(text):
        found.append(m.group(1) + m.group(2))

    # Verb-ending candidates on still-free spans.
    i = 0
    while i < len(text):
        if claimed[i]:
            i += 1
            continue
        hit_end = None
        for end in _SURU_END:
            if text.startswith(end, i) and (i == 0 or not claimed[i]):
                hit_end = ("suru", end)
                break
        if hit_end is None:
            for end in _NATIVE_END:
                if text.startswith(end, i):
                    hit_end = ("native", end)
                    break
        if hit_end:
            kind, end = hit_end
            stem = _stem_before(text, i, kind=kind)
            ok = (_is_stem(stem) if kind == "suru" else _ok_native(stem, end))
            if ok:
                pred = (_fold_suru(stem, end) if kind == "suru"
                        else _fold_native(stem, end))
                if pred not in _STOP and len(pred) >= 2:
                    found.append(pred)
                    claim(i, i + len(end))
                    i += len(end)
                    continue
        i += 1
    return found


# ---------------------------------------------------------------------------
# Optional morphological path (only if a tagger imported).
# ---------------------------------------------------------------------------

def _mecab_predicates(lead: str, tagger: Any) -> List[str]:
    text = _strip_noise(lead)
    out: List[str] = []
    # MeCab parse: surface\tpos,...
    parsed = tagger.parse(text) if hasattr(tagger, "parse") else ""
    for line in parsed.splitlines():
        if line == "EOS" or "\t" not in line:
            continue
        surface, feat = line.split("\t", 1)
        parts = feat.split(",")
        pos = parts[0] if parts else ""
        lemma = parts[6] if len(parts) > 6 and parts[6] != "*" else surface
        if pos.startswith("動詞"):
            if lemma not in _STOP:
                out.append(lemma)
        elif pos.startswith("助動詞") and lemma in ("だ", "です", "である"):
            out.append("である")
    # Frames still fire — they are closed strings, not a parse guess.
    for fr in _FRAMES:
        if fr in text:
            out.append(fr)
    for m in _FILLED_DEARU.finditer(text):
        out.append(m.group(1) + m.group(2))
    return out


# UniDic-lite writes the same light verbs as _STOP in kanji (為る/有る).
# Adapter-local only; the heuristic path is untouched.
_UNIDIC_LIGHT = frozenset({
    "為る", "有る", "居る", "成る", "出来る", "因る", "置く",
})


def _fugashi_written(tok: Any) -> Tuple[str, str]:
    """Modern written form plus stripped UniDic lemma.

    ``tok.feature.lemma`` is the UniDic lemma, but unidic-lite often
    stores the historical kanji (有る, 為る) or a hyphenated note
    (差す-他動詞). ``orthBase`` is the modern written dictionary form
    (ある, する, 指す) that matches _STOP and reads clean.
    """
    feat = tok.feature
    lemma = getattr(feat, "lemma", None) or ""
    orth_base = getattr(feat, "orthBase", None) or ""
    if lemma in ("", "*"):
        lemma = ""
    elif "-" in lemma:
        lemma = lemma.split("-", 1)[0]
    if orth_base in ("", "*"):
        orth_base = ""
    written = orth_base or lemma or tok.surface
    return written, lemma


def _fugashi_predicates(lead: str, tagger: Any) -> List[str]:
    text = _strip_noise(lead)
    out: List[str] = []
    for tok in tagger(text):
        pos = (tok.feature.pos1 if hasattr(tok.feature, "pos1")
               else str(tok.feature).split(",")[0])
        written, lemma = _fugashi_written(tok)
        if pos.startswith("動詞"):
            if (written in _STOP or lemma in _STOP
                    or written in _UNIDIC_LIGHT or lemma in _UNIDIC_LIGHT):
                continue
            out.append(written)
        elif pos.startswith("助動詞") and lemma in ("だ", "です", "である"):
            out.append("である")
    for fr in _FRAMES:
        if fr in text:
            out.append(fr)
    for m in _FILLED_DEARU.finditer(text):
        out.append(m.group(1) + m.group(2))
    return out


def _janome_predicates(lead: str, tokenizer: Any) -> List[str]:
    text = _strip_noise(lead)
    out: List[str] = []
    for tok in tokenizer.tokenize(text):
        pos = tok.part_of_speech.split(",")[0]
        lemma = tok.base_form or tok.surface
        if pos == "動詞" and lemma not in _STOP:
            out.append(lemma)
        elif pos == "助動詞" and lemma in ("だ", "です", "である"):
            out.append("である")
    for fr in _FRAMES:
        if fr in text:
            out.append(fr)
    for m in _FILLED_DEARU.finditer(text):
        out.append(m.group(1) + m.group(2))
    return out


def _sudachi_predicates(lead: str, tokenizer: Any) -> List[str]:
    text = _strip_noise(lead)
    out: List[str] = []
    for tok in tokenizer.tokenize(text):
        pos = tok.part_of_speech()[0]
        lemma = tok.dictionary_form() or tok.surface()
        if pos == "動詞" and lemma not in _STOP:
            out.append(lemma)
        elif pos == "助動詞" and lemma in ("だ", "です", "である"):
            out.append("である")
    for fr in _FRAMES:
        if fr in text:
            out.append(fr)
    for m in _FILLED_DEARU.finditer(text):
        out.append(m.group(1) + m.group(2))
    return out


_TAGGER: Any = None
_TAGGER_READY = False


def _tagger() -> Any:
    global _TAGGER, _TAGGER_READY
    if _TAGGER_READY:
        return _TAGGER
    _TAGGER_READY = True
    name = ANALYZER
    if name in ("MeCab", "mecab"):
        import MeCab  # type: ignore
        _TAGGER = MeCab.Tagger()
    elif name == "fugashi":
        import fugashi  # type: ignore
        _TAGGER = fugashi.Tagger()
    elif name == "janome":
        from janome.tokenizer import Tokenizer  # type: ignore
        _TAGGER = Tokenizer()
    elif name == "sudachipy":
        from sudachipy import dictionary, tokenizer as _st  # type: ignore
        _TAGGER = dictionary.Dictionary().create(mode=_st.Tokenizer.SplitMode.C)
    return _TAGGER


def predicates_of(lead: str) -> List[str]:
    """Predicate tokens of one lead, in appearance order (repeats kept)."""
    if EXTRACTOR in ("MeCab", "mecab"):
        return _mecab_predicates(lead, _tagger())
    if EXTRACTOR == "fugashi":
        return _fugashi_predicates(lead, _tagger())
    if EXTRACTOR == "janome":
        return _janome_predicates(lead, _tagger())
    if EXTRACTOR == "sudachipy":
        return _sudachi_predicates(lead, _tagger())
    return _heuristic_predicates(lead)


def extract(pages: Iterable[Tuple[str, str]], *,
            polarity: bool = False,
            lattice: Any = None) -> Dict[str, Dict[str, Any]]:
    """``{subject: {"predicates": {pred: count}, "total": N}}``.

    ``subject`` is the page title. Empty profiles are kept so coverage
    (subjects with ≥3 predicates / all subjects) is an honest fraction.

    ``polarity`` is an optional fold (default off). When on, observed
    negation marks dictionary-form keys (¬流れる). Default extract is
    unchanged so burned measurements stay valid.
    """
    profiles: Dict[str, Dict[str, Any]] = {}
    for title, lead in pages:
        if not title:
            continue
        rec = profiles.get(title)
        if rec is None:
            rec = {"predicates": {}, "total": 0}
            profiles[title] = rec
        preds = rec["predicates"]
        found = predicates_of(lead)
        if polarity:
            from .polarity import fold_polarity
            toks = None
            if EXTRACTOR == "fugashi":
                try:
                    toks = list(_tagger()(_strip_noise(lead)))
                except Exception:
                    toks = None
            found = fold_polarity(found, lead, lattice=lattice, tokens=toks)
        for p in found:
            preds[p] = preds.get(p, 0) + 1
            rec["total"] += 1
    return profiles


def extract_with_polarity(
    pages: Iterable[Tuple[str, str]],
    *,
    lattice: Any = None,
) -> Dict[str, Dict[str, Any]]:
    """Wrapper for the optional polarity fold. Default extract is untouched."""
    return extract(pages, polarity=True, lattice=lattice)


def save(profiles: Dict[str, Dict[str, Any]], path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    out: Dict[str, Any] = dict(profiles)
    out["extractor"] = EXTRACTOR
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    return path


def load(path: Path = OUT) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    extractor = data.pop("extractor", "unknown")
    profiles = {k: v for k, v in data.items()
                if isinstance(v, dict) and "predicates" in v}
    return extractor, profiles


def report(profiles: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    n = len(profiles)
    ge3 = sum(1 for r in profiles.values() if len(r["predicates"]) >= 3)
    pairs = sum(len(r["predicates"]) for r in profiles.values())
    return {
        "extractor": EXTRACTOR,
        "subjects": n,
        "subjects_ge3": ge3,
        "coverage_ge3": round(ge3 / n, 4) if n else None,
        "pairs": pairs,
    }


def main(pages: Optional[Iterable[Tuple[str, str]]] = None) -> Dict[str, Any]:
    import time
    t0 = time.time()
    if pages is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        from build_shallow_shelf import pages as _pages  # type: ignore

        def _progress():
            n = 0
            for item in _pages():
                n += 1
                if n % 50_000 == 0:
                    print("pages %d %.0fs" % (n, time.time() - t0), flush=True)
                yield item
        pages = _progress()
    profiles = extract(pages)
    save(profiles)
    out = report(profiles)
    out["out"] = str(OUT)
    out["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return out


if __name__ == "__main__":
    main()
