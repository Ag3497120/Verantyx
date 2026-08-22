"""Lazy, cached loaders for the meaning-layer sidecars the MCP doors need.

The doors (vera_diff / vera_typo) need the same four assets every call:
predicate profiles (107MB json), the alias map (48MB, 941,604 entries),
the sense inventory (62MB, 122,988 surfaces), and the attested-word
lattice (built from writer.json's vocabulary, long window included).
Loading any of them per call would make the first tool answer the only
tool answer, so each loads once per process and stays.

What deliberately does NOT load here: the shallow shelf (912MB) and the
definition sidecar (250MB). A door that costs the host a gigabyte of
resident json to render two shelf layers is the wrong trade until those
sidecars move to an indexed store; `diff` is called with an empty shelf
and its coverage field says honestly that layers ④/⑥ abstained. The
measurement scripts, which run once and exit, keep loading the real
shelf — the 11/30 bank number is theirs, not the door's.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
from pathlib import Path
from typing import Any, Dict, Optional

BUILD = corpus_root() / "build"

_cache: Dict[str, Any] = {}


def _indexed() -> Optional[Dict[str, Any]]:
    """The SQLite index's read-through maps, or None when unbuilt.

    Preferred over the json for every door: holding the three big
    sidecars resident cost 2.4GB and got the engine process killed
    mid-call inside the IDE (see meaning_index's docstring for the
    measurement and the refusal it corrupted).
    """
    if "indexed" not in _cache:
        from .meaning_index import maps
        _cache["indexed"] = maps()
    return _cache["indexed"]


def profiles() -> Dict[str, Any]:
    """The predicate profiles a door reads.

    Prefers the polarity-marked table when the index carries one: an
    observed ¬ is testimony the diff and the connective render may use
    (「しかし」 is reachable only through such a pair), and withholding
    it from the doors was the wiring gap that made every rendered
    opposition impossible. The plain table stays beside it because the
    burned measurements were taken on it; `extractor()` names which
    table answered, so no number is silently re-attributed.
    """
    if "profiles" not in _cache:
        idx = _indexed()
        if idx is not None:
            polar = idx.get("profiles_polar")
            if polar is not None and len(polar):
                _cache["extractor"] = "indexed+polarity"
                _cache["profiles"] = polar
            else:
                _cache["extractor"] = "indexed"
                _cache["profiles"] = idx["profiles"]
        else:
            from .predicate_profile import load
            _cache["extractor"], _cache["profiles"] = load()
    return _cache["profiles"]


def extractor() -> str:
    profiles()
    return _cache["extractor"]


def aliases() -> Dict[str, str]:
    if "aliases" not in _cache:
        idx = _indexed()
        _cache["aliases"] = idx["aliases"] if idx is not None else json.loads(
            (BUILD / "jawiki_aliases.json").read_text(encoding="utf-8"))
    return _cache["aliases"]


def senses() -> Dict[str, Any]:
    if "senses" not in _cache:
        idx = _indexed()
        if idx is not None:
            _cache["senses"] = idx["senses"]
        else:
            d = json.loads(
                (BUILD / "jawiki_senses.json").read_text(encoding="utf-8"))
            _cache["senses"] = d.get("senses", d)
    return _cache["senses"]


def lattice() -> Any:
    if "lattice" not in _cache:
        from .lattice import build
        from .writer import Writer
        vocab = Writer.load(BUILD / "writer.json").vocab
        _cache["vocab"] = set(vocab.attested)
        _cache["lattice"] = build(_cache["vocab"])
    return _cache["lattice"]


def vocab() -> Any:
    lattice()
    return _cache["vocab"]


def defs() -> Dict[str, str]:
    """The definition sidecar (250MB json). The heaviest asset here —
    loaded only when a door actually descends, then kept. The module
    docstring's shelf argument does not apply: defs is a flat
    surface->sentence map, not the 912MB cross shelf, and the descent
    door is the one organ that cannot work without it."""
    if "defs" not in _cache:
        idx = _indexed()
        _cache["defs"] = idx["defs"] if idx is not None else json.loads(
            (BUILD / "jawiki_defs.json").read_text(encoding="utf-8"))
    return _cache["defs"]


def empty_shelf() -> Any:
    if "empty_shelf" not in _cache:
        from .cross_store import CrossStore
        _cache["empty_shelf"] = CrossStore()
    return _cache["empty_shelf"]
