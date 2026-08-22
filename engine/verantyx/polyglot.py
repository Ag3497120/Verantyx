"""One sovereign per language, and a question goes to exactly one.

A single federation holding both languages cannot be asked in either. The
English decomposer collapses 「Article 199 provides for homicide」 to the
core `article`, and once that core is in the same store as 刑法第百九十九条,
a Japanese question and an English one compete in the same census over
items neither reader produced.

The failure is the one already measured on the other axes and it is the same
shape: pooling votes from structures that mean different things by
"agreement". Cut-varied sovereigns agreeing is structural, data-varied is
evidential, and cross-LANGUAGE agreement is neither — it is a collision
between two tokenizers.

    detect(query) -> the sovereign built from that language
                  -> the staircase that script can carry

## The staircase is per language, not global

Character windows discriminate over kanji, of which there are thousands, and
collide over latin, of which there are twenty-six. Measured on a nine-core
English store against ten words it never held: six settings with windows
gave four false answers, whole-grain only gave none, and the same six
settings gave none on Japanese. `graded.settings_for` picks it; this routes
to the store it applies to.

## What it does not do

Translate, align, or answer a Japanese question from English documents. A
question in a language no sovereign was built for is refused by name —
`UNKNOWN_LANGUAGE_NOT_HELD` — rather than being handed to whichever
tokenizer happens to accept the characters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class Polyglot:
    """A sovereign per language, addressed by the language of the question."""

    #: language tag -> the store built from documents in that language
    stores: Dict[str, Any] = field(default_factory=dict)
    judges: Dict[str, Any] = field(default_factory=dict)
    built: Dict[str, Any] = field(default_factory=dict)

    def add(self, lang: str, store: Any,
            settings: Optional[Sequence[Tuple[str, Dict[str, Any]]]] = None,
            *, read: Optional[Any] = None) -> "Polyglot":
        """Register one language's sovereign.

        ``settings`` defaults to the staircase the script can carry rather
        than to the Japanese one, because that default was measured wrong
        for latin — see `graded.settings_for`.
        """
        from .graded import GradedJudge, DEFAULT_SETTINGS, LATIN_SETTINGS

        if settings is None:
            settings = LATIN_SETTINGS if lang in ("en", "latin") else DEFAULT_SETTINGS
        self.stores[lang] = store
        self.judges[lang] = GradedJudge(settings, read=read).build(store)
        self.built[lang] = {"cores": len(store.crosses),
                            "settings": len(settings)}
        return self

    def route(self, query: str) -> str:
        """Which sovereign this question belongs to."""
        from .lang import detect

        return detect(query)

    def ask(self, query: str) -> Dict[str, Any]:
        """Ask exactly one sovereign, and say which.

        Never a census across languages. Two tokenizers arriving at the same
        string have not agreed about anything — they have collided, and the
        vote would be counting a collision as corroboration.
        """
        lang = self.route(query)
        j = self.judges.get(lang)
        if j is None:
            # `latin` is what `detect` returns for latin script it will not
            # call English; fall back to an English sovereign if one exists,
            # since that is the reader it would have used anyway.
            if lang == "latin" and "en" in self.judges:
                lang, j = "en", self.judges["en"]
        if j is None:
            return {
                "verdict": "UNKNOWN_LANGUAGE_NOT_HELD",
                "language": lang, "have": sorted(self.judges),
                "note": "no sovereign was built from documents in this "
                        "language; handing the question to another "
                        "tokenizer would answer from a store that never "
                        "read it",
            }
        out = dict(j.ask(query))
        out["language"] = lang
        out["sovereign"] = "%s (%d cores)" % (lang, len(self.stores[lang].crosses))
        return out

    def report(self) -> Dict[str, Any]:
        return dict(self.built)
