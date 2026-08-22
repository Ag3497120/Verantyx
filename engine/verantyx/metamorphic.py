"""Prove a defect from inside, with no answer key and nobody reading.

`self_audit` found the SHAPES a defect leaves and stopped there, on purpose:
a shape is a suspicion, the ranges overlap with correct output, and no
procedure inside the engine can decide whether its own reading of a sentence
is right. That boundary is real and this module does not cross it.

It goes around it. There is a second question that IS decidable from inside:

    not   "is this reading correct?"      — needs the world
    but   "do two readings of the SAME CONTENT agree?" — needs only the store

If they disagree, one of them is wrong. That is a proof, not a suspicion, and
it costs no human and no network. What makes it usable is that for some
transformations the direction is decidable too:

    LAYOUT CANNOT ADD INFORMATION.

A space between two kanji is put there by a PDF extractor, not by the author —
Japanese does not space its words. So if collapsing that space makes a claim
DISAPPEAR, the claim was manufactured by the layout, and it is spurious. Not
"suspicious": spurious, because no arrangement of whitespace can be evidence
that a town has water.

Measured on the defect that started this: 「７月 30 日 から 全 12 戸 が 断水」
reads as a claim about 全, and the same sentence without the extractor's
spaces reads as a claim about 全12戸. The first is a fragment. No one had to
read either to know that one of them is wrong.

The probes, and why each preserves meaning:

    counter_split A numeral and the counter after it — 12戸, 15炉 — are one
                  word, and a space between them is column alignment. The one
                  repair that measured FREE: 5 proven defects gone, and the
                  corpus placed the same 18,460 sentences afterwards.
    layout_space  A single space between two CJK characters. Japanese has no
                  inter-word space, so in prose it is always the extractor.
                  Table rows are EXCLUDED — `_is_table_row` exists because a
                  row's single spaces are column separators, and collapsing
                  those would change meaning rather than restore it.
    digit_width   ７ and 7 are the same digit. Nothing weaker to argue.
    doc_order     The order documents arrive in is not part of what they say.
                  Symmetric: neither reading is canonical, they must agree.
    reread        Reading the same document twice must add nothing. The
                  user's own test — "if re-reading is enough to evolve it" —
                  requires this to hold, or the second read is not a re-read.

What is filed as PROVEN and what is not. Only the manufactured direction:
a claim present in the noisy reading and absent in the clean one. The reverse
— a claim the clean reading has and the noisy one lacks — is filed as
suspected, because a document whose layout carries structure can legitimately
read differently, and a normalisation that flattens a table is not a fix.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: A single space between two CJK characters. Two or more spaces are a column
#: gap and belong to `_is_table_row`'s problem, not this one.
_CJK = r"[㐀-䶿一-鿿ぁ-ゖァ-ヺー0-9０-９]"
_LAYOUT_SPACE = re.compile(f"(?<={_CJK})[ 　](?={_CJK})")

#: The same idea, narrowed to a numeral and the counter that follows it.
#:
#: Measured, which is the only reason it exists as a separate probe. The wide
#: form proves 8 defects on the ministry PDFs and costs 71 sentences their
#: core — it joins runs that were never one word, and the loop rejected it.
#: This one proves 5 and costs NOTHING: 18,460 sentences placed before and
#: after, 9 confirmed detections before and after. Every defect the wide probe
#: found on real documents has this shape — 15炉, ８金融機関, 戸供給, 月3,
#: 箇所 — because a counter is where a PDF's column alignment most often falls.
_COUNTER_SPLIT = re.compile(r"(?<=[0-9０-９])[ 　](?=[㐀-䶿一-鿿])")

_FULLWIDTH = {ord(c): ord(d) for c, d in zip("０１２３４５６７８９", "0123456789")}


def collapse_layout_space(text: str) -> str:
    """Remove extractor spaces, leaving table rows alone."""
    from .document_loaders import _is_table_row

    out = []
    for line in (text or "").split("\n"):
        out.append(line if _is_table_row(line) else _LAYOUT_SPACE.sub("", line))
    return "\n".join(out)


def split_counter(text: str) -> str:
    """Rejoin a numeral to its counter across an extractor's space."""
    from .document_loaders import _is_table_row

    return "\n".join(
        line if _is_table_row(line) else _COUNTER_SPLIT.sub("", line)
        for line in (text or "").split("\n"))


def normalize_digits(text: str) -> str:
    return (text or "").translate(_FULLWIDTH)


#: name -> (transform, symmetric, why it preserves meaning)
PERTURBATIONS: Dict[str, Tuple[Any, bool, str]] = {
    "counter_split": (
        split_counter, False,
        "A numeral and its counter are one word — 12戸, 15炉, 8金融機関 — and "
        "a space between them is column alignment, never grammar. The narrow "
        "case of layout_space, kept separate because it is the one that "
        "measured free: 5 proven defects removed, zero sentences lost.",
    ),
    "layout_space": (
        collapse_layout_space, False,
        "Japanese does not space its words; a single space between two CJK "
        "characters in prose was put there by the extractor. Table rows are "
        "excluded because there the space is a column separator.",
    ),
    "digit_width": (
        normalize_digits, False,
        "７ and 7 are the same digit.",
    ),
}


@dataclass
class Divergence:
    """Two readings of the same content disagreeing. A proof, or a suspicion."""

    perturbation: str
    kind: str           # manufactured | destroyed | order | reread | guard_conflict
    core: str
    facet: str
    proven: bool
    #: Redacted, like everything that leaves the reading path.
    shape: str = ""
    #: For a guard conflict: the grammar the guard matched — function words
    #: only, safe to carry, and exactly what a repair candidate is made from.
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in ("", None)}


def _claims(docs) -> Dict[Tuple[str, str], str]:
    """Every polar claim in a fresh store, with the sentence it came from."""
    from .cross_store import CrossStore
    from .document_ingest import ingest_documents

    store = CrossStore(track_provenance=True)
    ingest_documents(store, list(docs))
    out: Dict[Tuple[str, str], str] = {}
    prov = getattr(store, "provenance", {}) or {}
    for core in store.crosses:
        for facet in store.crosses[core]:
            if ":" not in facet:
                continue
            slot = (prov.get(core) or {}).get(facet)
            out[(core, facet)] = str(slot[2]) if slot and len(slot) > 2 else ""
    return out


def _perturbed(docs, transform):
    from .document_loaders import Document

    out = []
    for d in docs:
        new = Document(d.source, transform(d.text))
        for attr in ("path", "kind", "meta"):
            if hasattr(d, attr):
                try:
                    setattr(new, attr, getattr(d, attr))
                except Exception:
                    pass
        out.append(new)
    return out


def probe(docs, *, perturbations: Optional[Sequence[str]] = None
          ) -> List[Divergence]:
    """Every disagreement between readings of the same content."""
    from .defect_report import skeleton

    docs = list(docs)
    if not docs:
        return []
    observed = _claims(docs)
    found: List[Divergence] = []

    for name in (perturbations or PERTURBATIONS):
        transform, symmetric, _why = PERTURBATIONS[name]
        clean = _claims(_perturbed(docs, transform))
        # A core is TEXT, so the transform renames it too: 「７月30日」 becomes
        # 「7月30日」 and the naive set difference reports one claim twice, once
        # in each direction. The first run of this module said 18 manufactured
        # and 18 destroyed on 内閣府 — the same 18 renames, and no defect at
        # all. Comparing modulo the transform is what makes a difference mean
        # the reading changed rather than the spelling.
        seen = {(transform(c), f): v for (c, f), v in observed.items()}
        clean = {(transform(c), f): v for (c, f), v in clean.items()}
        for key in sorted(set(seen) - set(clean)):
            # The decidable direction. Layout cannot be evidence.
            found.append(Divergence(name, "manufactured", key[0], key[1],
                                    True, skeleton(seen[key])))
        for key in sorted(set(clean) - set(seen)):
            # Suspected only: a document whose layout carries structure may
            # legitimately read differently, and flattening a table is not a fix.
            found.append(Divergence(name, "destroyed", key[0], key[1],
                                    symmetric, skeleton(clean[key])))

    # Order is not part of what a document says.
    if len(docs) > 1:
        flipped = _claims(list(reversed(docs)))
        for key in sorted(set(observed) ^ set(flipped)):
            found.append(Divergence("doc_order", "order", key[0], key[1], True,
                                    skeleton(observed.get(key)
                                             or flipped.get(key, ""))))

    # And re-reading must add nothing, or "read it again" is not a re-read.
    from .cross_store import CrossStore
    from .document_ingest import ingest_documents

    twice = CrossStore(track_provenance=True)
    ingest_documents(twice, docs)
    before = {(c, f) for c in twice.crosses for f in twice.crosses[c]}
    ingest_documents(twice, docs)
    after = {(c, f) for c in twice.crosses for f in twice.crosses[c]}
    for core, facet in sorted(after - before):
        found.append(Divergence("reread", "reread", core, facet, True))
    return found


def probe_paths(paths: Sequence[str], *,
                perturbations: Optional[Sequence[str]] = None
                ) -> List[Divergence]:
    """The same question, asked through the switch the repair actually flips.

    `probe` perturbs document TEXT, which is honest about the text but not
    about the engine: the reading path applies a normalizer only where the
    format was laid out, because a PDF's stray space and an HTML table's cell
    separator are the same character and only the loader knows which it has.

    That gap was not theoretical. Perturbing text directly reported four
    proven divergences on municipal HTML — and collapsing those spaces turned
    「日時 開催場所 担当部署」, three table headers, into one word. The
    transform does not preserve meaning there, so nothing it showed was
    proven, and the loop was measuring a repair it would never make.

    Toggling the real switch and reloading makes probe and repair the same
    code path by construction, so that class of mismatch cannot come back.
    """
    from .catalog import collect
    from .defect_report import skeleton
    from .document_loaders import load_paths
    from . import ja_grammar as grammar

    files = collect(list(paths))["files"]
    if not files:
        return []
    observed = _claims(load_paths(files)["documents"])
    found: List[Divergence] = []
    have = {n for n, _ in grammar.NORMALIZERS}

    for name in (perturbations or PERTURBATIONS):
        if name in have:
            continue
        transform, symmetric, _why = PERTURBATIONS[name]
        entry = (name, "probe")
        grammar.NORMALIZERS.append(entry)
        try:
            clean = _claims(load_paths(files)["documents"])
        finally:
            if entry in grammar.NORMALIZERS:
                grammar.NORMALIZERS.remove(entry)
        seen = {(transform(c), f): v for (c, f), v in observed.items()}
        clean = {(transform(c), f): v for (c, f), v in clean.items()}
        for key in sorted(set(seen) - set(clean)):
            found.append(Divergence(name, "manufactured", key[0], key[1],
                                    True, skeleton(seen[key])))
        for key in sorted(set(clean) - set(seen)):
            found.append(Divergence(name, "destroyed", key[0], key[1],
                                    symmetric, skeleton(clean[key])))
    return found


#: The engine's no-assert guards, by name. Each one's meaning is "a match
#: after the polar term means the term asserts nothing" — which makes a
#: placed pole whose tail matches one of them an internal contradiction,
#: decidable without the world.
GUARDS = (("until", "_JA_UNTIL"), ("deeming", "_JA_DEEMING"),
          ("cause", "_JA_CAUSE_MARK"))


def rule_conflicts(paths: Sequence[str]) -> List[Divergence]:
    """Placed poles that the engine's own rules say assert nothing.

    The second internal oracle, next to meaning-preserving transforms. It
    never asks whether a reading is right — it asks whether the OUTPUT and
    the RULES agree with each other, and both live in this process. Every
    guard-skipped defect this project hit by hand — enumeration, deeming,
    until, and now のため — is this exact disagreement: some path placed a
    pole whose tail a guard on another path would have refused.

    Found five on the first run, all on the statutes, all `cause`:
    「災害復旧のため派遣された職員」 placed 復旧:復旧 on 災害派遣手当 — a
    dispatch allowance is not a restored water main. Nobody read anything.

    The tail is taken at the LAST occurrence of the term, because that is the
    occurrence placement itself uses (`seen_at = read.rfind(word)`); auditing
    a different occurrence than the one that placed the pole would report
    conflicts placement never committed.
    """
    from . import polarity as _p
    from .catalog import collect
    from .cross_store import CrossStore
    from .defect_report import _ATTRIBUTION, skeleton
    from .document_ingest import ingest_documents
    from .document_loaders import load_paths

    docs = load_paths(collect(list(paths))["files"])["documents"]
    store = CrossStore(track_provenance=True)
    ingest_documents(store, docs)

    out: List[Divergence] = []
    for core in sorted(store.crosses):
        prov = (getattr(store, "provenance", {}) or {}).get(core, {})
        for facet in sorted(f for f in store.crosses[core] if ":" in f):
            slot = prov.get(facet)
            if not (slot and len(slot) > 2):
                continue
            sentence = _ATTRIBUTION.sub("", str(slot[2]))
            word = facet.split(":", 1)[1].replace("not_", "")
            at = sentence.rfind(word)
            if at < 0:
                continue
            tail = sentence[at + len(word):]
            for label, attr in GUARDS:
                rx = getattr(_p, attr, None)
                m = rx.match(tail) if rx else None
                if m:
                    out.append(Divergence(
                        "own_rules", "guard_conflict", core, facet, True,
                        skeleton(sentence), m.group(0)))
                    break
    return out


def summary(divs: List[Divergence]) -> Dict[str, Any]:
    proven = [d for d in divs if d.proven]
    by: Dict[str, int] = {}
    for d in divs:
        by[f"{d.perturbation}/{d.kind}"] = by.get(f"{d.perturbation}/{d.kind}", 0) + 1
    return {
        "total": len(divs),
        "proven": len(proven),
        "by_probe": by,
        "what_proven_means": (
            "Two readings of the same content disagree, and the transform "
            "between them cannot have changed what the content says. One of "
            "the readings is wrong — established without an answer key, a "
            "network, or a person. It still does not say which reading is "
            "RIGHT, except where layout manufactured a claim: layout cannot "
            "add information, so that claim is spurious."
        ),
    }
