# -*- coding: utf-8 -*-
"""A tiny store, a view over it, and two transforms — the fixture the
``--self-test`` corpus is written against.

Nothing here is part of the shipped package. It exists so the scanner can be
pointed at a suite whose defects are KNOWN, which is the only way to say what
the scanner catches without asking somebody to look harder.

``MiniView`` is shaped like ``photoloset.block.BlockView``: constructed with a
store, read through no-argument methods. One reader (``zones``) is made to
track its store by the honest corpus suite; another (``motto``) is only ever
compared against a literal, which is the T7 blind spot in miniature.
"""

#: A module constant that IS a live call — the T1 shape from finding #1.
FROZEN_ZONES = ("collar", "hem")


class MiniStore:
    """Seats keyed by name. A write is visible to every reader."""

    def __init__(self) -> None:
        self._seats = {"label": "mini coat", "zone:1": "collar",
                       "zone:2": "hem"}

    def put(self, key, value):
        self._seats[key] = value
        return {"verdict": "ANSWER", "key": key}

    def get(self, key):
        return self._seats.get(key)

    def keys(self, prefix=""):
        return sorted(k for k in self._seats if k.startswith(prefix))


class MiniView:
    """Readers over one store."""

    def __init__(self, store) -> None:
        self.store = store

    def zones(self):
        return [self.store.get(k) for k in self.store.keys("zone:")]

    def motto(self):
        return self.store.get("label")

    def seams(self):
        return len(self.zones()) + 3

    def served(self):
        return {"zones": self.zones(), "motto": self.motto(),
                "seams": self.seams()}

    def refusal(self):
        """Answers WITH a verdict, and the verdict is the whole point."""
        return {"verdict": "UNKNOWN_NO_MEASURES", "zones": [],
                "how_to_close": "measure something"}


def view():
    return MiniView(MiniStore())


def draft():
    """A callee whose verdict IS read by the corpus checks file."""
    return {"verdict": "ANSWER", "zones": ["collar", "hem"]}


def quiet_draft():
    """A callee whose verdict NO check in the corpus file ever reads.

    That is B8(c): a refusal subject is unprotected on the day it is
    introduced, which is the day it matters.
    """
    return {"verdict": "UNKNOWN_NO_MEASURES", "pieces": [],
            "how_to_close": "measure something"}


def translate(doc):
    """A transform that is allowed to become the identity — and is one."""
    return dict(doc)


def tidy(doc):
    """A second such transform, so two steps can be planted."""
    return dict(doc)


def shout(doc):
    """A transform that MOVES its input. `shout(x) != x` is the repair a
    T4 asks for, and reporting it as the defect is B5."""
    out = dict(doc)
    out["motto"] = out["motto"].upper()
    return out
