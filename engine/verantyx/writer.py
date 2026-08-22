"""The generation stack, assembled — and kept away from the answer path.

Five pieces were built and measured separately. This wires them, because a
caller assembling them by hand gets the order wrong: a walk without a
vocabulary fills sentences with 1980アイコ, a vocabulary attested on the
wrong register loses 場合 and 被保険者, and forms harvested from one corpus
write in that corpus's voice whatever the content is.

    vocabulary   which facets are words              33,126 of 123,734
    forms        sentence shapes with typed holes    478
    selection    what the corpus puts in each slot   382,884 triples
    trace        where the walk went, held outside   subject held 5.3 steps
    compose      one sentence per step

## The order is load-bearing

Attestation must come from the SAME register as the stores. 626MB of statute
raised the facet count 1.4x and the vocabulary not at all, because every
attesting corpus was encyclopedia prose; adding the statute bodies took the
vocabulary from 12,348 to 33,126 and the selection triples from 8,805 to
382,884. A `Writer` therefore takes its corpora explicitly and reports what
each contributed, so a build that judges law by Wikipedia is visible rather
than silent.

## Never on the answer path

Nothing here is imported by `gather`, `descend`, `consensus_over_store` or
any verdict. A generated sentence is a draft with two citations — one for
the content, one for the shape — and neither makes it true. The whole point
of the closure elsewhere is that a reader can trust a citation; a sentence
this module assembled must never be able to arrive where one is expected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .compose_ja import _SURU as _SURU_LOAD
from .compose_ja import (Form, compose, harvest, learn_joins,
                         learn_selection)
from .trace import Trace, walk
from .vocabulary import Vocabulary, from_stores, statute_text


#: 旧仮名(促音の大書き)の現代化 — 文型にだけ効く(2026-08-19)。
#:
#: 実測: speakable 597文型のうち16本(2.7%)が e-Gov の旧法文から
#: 「によつて」「なつた」「つづつて」を運び、生成が「経費によつて精算
#: する」を出していた。原文がそう書いているので破損ではない — 旧法の
#: 正字である。だが読み手には誤字に見える。
#:
#: 触ってよい理由は provenance にある: 文型は**主張を運ばない**
#: (compose_ja の冒頭「A form's source wrote that shape, not the claim」)。
#: 引用は一切通らない — quote_in_words の引用文字列も、文書の text も、
#: この表は見ない。形の綴りだけを今の読み手の綴りに直す。
#:
#: 閉じた列。機能語の語尾に限り、各項は上の実測に現れたものだけ。
#: 「かつた/とつた」等の類推追加はしない — 測っていないものは入れない。
_OLD_KANA = (
    ("によつて", "によって"), ("であつて", "であって"),
    ("であつた", "であった"), ("わたつて", "わたって"),
    ("つづつて", "つづって"), ("もつて", "もって"),
    ("あつた", "あった"), ("なつた", "なった"), ("よつて", "よって"),
)


def modernize_form(tpl: str) -> str:
    """文型の旧仮名を現代表記へ。引用には決して使わない。"""
    for old, new in _OLD_KANA:
        if old in tpl:
            tpl = tpl.replace(old, new)
    return tpl


@dataclass
class Writer:
    """Everything composition needs, built once and reported on."""

    vocab: Vocabulary = field(default_factory=Vocabulary)
    forms: Dict[str, Form] = field(default_factory=dict)
    built: Dict[str, Any] = field(default_factory=dict)
    #: Corpus labels whose text states norms rather than reporting facts.
    #: Known without a classifier because `build` is told which sources are
    #: statutes — the API already separates them.
    norm_corpora: Set[str] = field(default_factory=set)

    def licence(self, subject: str) -> str:
        """What a sentence about ``subject`` is entitled to assert.

        Read from the corpus that uses the word most, which the vocabulary
        records per term for exactly this kind of question. A subject the
        statutes use is one the law has spoken about; a subject only an
        encyclopedia uses is not, whatever else is true of it.
        """
        at = self.vocab.attested.get(subject) or {}
        if not at:
            return "unknown"
        best = max(at.items(), key=lambda kv: (kv[1], kv[0]))[0]
        return "norm" if best in self.norm_corpora else "record"

    @classmethod
    def build(
        cls,
        stores: Iterable[Any],
        prose: Sequence[Tuple[str, str]],
        *,
        statutes: Optional[Iterable[Path]] = None,
        norm_corpora: Optional[Iterable[str]] = None,
    ) -> "Writer":
        """``prose`` is (label, text). ``statutes`` are e-Gov XML paths.

        Statutes are read separately because their prose is inside a schema,
        and because leaving them out is the exact mistake that made a
        vocabulary blind to the register it was judging.
        """
        corpora = list(prose)
        if statutes:
            law = statute_text(statutes)
            if law:
                corpora.append(("statute", law))
        w = cls()
        w.norm_corpora = set(norm_corpora) if norm_corpora is not None else set()
        if statutes:
            w.norm_corpora.add("statute")
        w.vocab = from_stores(stores, corpora)
        sel = learn_selection(corpora)
        joins_ = learn_joins(corpora)
        w.forms = harvest(corpora)
        w.built = {
            "corpora": {label: len(text) for label, text in corpora},
            "vocabulary": w.vocab.report(),
            "forms": len(w.forms),
            "norm_forms": sum(1 for f in w.forms.values()
                              if f.register == "norm"),
            "norm_corpora": sorted(w.norm_corpora),
            "selection": sel,
            "joins": joins_,
        }
        return w

    def sentence(
        self,
        store: Any,
        subject: str,
        *,
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
        """Sentences about one subject, or nothing if it is not a word."""
        if subject not in self.vocab:
            return []
        labels = getattr(store, "source_labels", set()) or set()
        facets = [f for f in (store.crosses.get(subject) or {})
                  if f not in labels]
        return [d.as_dict() for d in
                compose(self.forms, subject, sorted(facets), limit=limit,
                        content_from=[subject], vocab=self.vocab,
                        licence=self.licence(subject))]

    def passage(
        self,
        store: Any,
        seed: str,
        *,
        steps: int = 6,
        mode: str = "path",
        trace: Optional[Trace] = None,
    ) -> Dict[str, Any]:
        """A walk, and a sentence at each step it could write one for.

        Anchoring on the path rather than the seed is the default because
        that is what a developing text needs: measured, path-anchoring walks
        furthest and overlaps its previous step most (0.069 against 0.033),
        while seed-anchoring holds the ORIGINAL subject longest (6.9 steps
        against 1.7) and is what a question wants.

        The trace comes back with the passage. It is the only mutable thing
        here, and returning it is what makes a passage resumable.
        """
        t = walk(store, seed, mode=mode, steps=steps, trace=trace)
        out: List[Dict[str, Any]] = []
        for core in t.seen:
            got = self.sentence(store, core, limit=1)
            if got:
                out.append(got[0])
        return {
            "seed": seed,
            "path": list(t.seen),
            "sentences": out,
            "written": len(out),
            "skipped": len(t.seen) - len(out),
            "trace": t,
            "note": "each sentence carries its content source and its form "
                    "source; neither makes it true",
        }

    def save(self, path: Path) -> Dict[str, Any]:
        """Write everything `build` learned, so it is learned once.

        Building this from 626MB takes minutes and the inputs are a
        third-party corpus that has now been lost twice to a cleaned temp
        directory. A learned artifact that only exists in a live process is
        the same mistake one level up: the corpus manifests were fixed so a
        corpus can be rebuilt, and this is so it does not have to be.
        """
        from .compose_ja import JOIN, dump_selection

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "vocab": self.vocab.attested,
            "norm_corpora": sorted(self.norm_corpora),
            "forms": [{"template": f.template, "cases": f.cases,
                       "slots": [list(s) if s else None for s in f.slots],
                       "count": f.count, "example": f.example,
                       "source": f.source} for f in self.forms.values()],
            "selection": dump_selection(),
            "joins": dict(JOIN),
            "built": self.built,
        }, ensure_ascii=False), encoding="utf-8")
        return {"path": str(path), "bytes": path.stat().st_size,
                "forms": len(self.forms), "terms": len(self.vocab.attested)}

    @classmethod
    def load(cls, path: Path) -> "Writer":
        """Restore a saved writer, slot tables included.

        The tables are module globals, so a writer restored without them
        composes with `selects` answering None everywhere — every fill
        "unknown but not refused", which is silently a different system.
        """
        from .compose_ja import JOIN, load_selection

        d = json.loads(Path(path).read_text(encoding="utf-8"))
        w = cls()
        w.vocab = Vocabulary()
        w.vocab.attested = d["vocab"]
        w.norm_corpora = set(d.get("norm_corpora") or ())
        w.forms = {}
        for f in d.get("forms") or []:
            form = Form(template=f["template"], cases=f["cases"],
                        slots=[tuple(s) if s else None for s in f["slots"]],
                        count=f["count"], example=f["example"],
                        source=f["source"])
            # 出荷済み writer.json の穴の型は、収穫当時の _SURU で判定
            # されている。旧 _SURU は している/します/し、 を見落とし、
            # する動詞の穴が free 型で焼き付いた — free なら fits() が
            # 素通しになり、する名詞でない語が詰まって「効力を方式して
            # いる」ができる(実測 2026-08-19)。型は文型文字列から決定的に
            # 引き直せるので、積み込み時に再導出する。データの主張は
            # 変えない — 同じ文字列を今の読み手で読み直すだけ。
            import re as _re
            # 穴0も対象(2026-08-19): range(1,…) が主語穴を飛ばし、
            # 「<0>されているのは…」に 領収書 が入った(される に続く穴は
            # する名詞しか立てない)。
            for _i in range(0, len(form.cases)):
                if form.cases[_i] != "free":
                    continue
                _m = _re.search("<%d>" % _i, form.template)
                if _m and _SURU_LOAD.match(
                        form.template[_m.end():_m.end() + 4]):
                    form.cases[_i] = "verbalnoun"
            # 綴りの現代化は型の再導出の後 — 型は文型文字列から引くので、
            # 先に綴りを変えると「されて」等の判定が変わりうる。
            _modern = modernize_form(form.template)
            if _modern != form.template:
                form.template = _modern
            # 現代表記の双子と衝突したら回数の多い方を残す — 綴りを直した
            # 結果として実測(頻度)を捨てないため。
            _prev = w.forms.get(form.template)
            if _prev is not None and _prev.count >= form.count:
                _prev.count += form.count
            else:
                if _prev is not None:
                    form.count += _prev.count
                w.forms[form.template] = form
        w.built = d.get("built") or {}
        w.built["selection_restored"] = load_selection(d.get("selection") or {})
        JOIN.clear(); JOIN.update(d.get("joins") or {})
        w.built["joins_restored"] = len(JOIN)
        return w

    def report(self) -> Dict[str, Any]:
        return dict(self.built)
