"""photoloset — a garment tool that refuses to guess.

Every number that reaches a pattern can be traced to a person who measured it.
Anything that was not measured is named as not measured, and the tool declines
to draft around it.
"""

__version__ = "0.0.0"

from .garment import (  # noqa: F401
    CONTESTED,
    INFERRED,
    OBSERVED,
    PROPOSED,
    PARTS,
    Entry,
    Ledger,
)
from .garment_measure import Measure, Measures  # noqa: F401
from . import i18n  # noqa: F401
from .i18n import translate as en  # noqa: F401


def set_language(lang: str) -> str:
    """Set the language every public entry point returns.

    This wraps a fixed list of functions rather than threading a `_()` call
    through the engine, because the engine is shared with a larger project and
    two copies would drift. `photoloset.en(result)` does the same thing for one
    value if you would rather be explicit.

    A string the table does not know comes back in Japanese —
    `i18n.missing(result)` lists exactly which.
    """
    if lang not in i18n.LANGUAGES:
        raise ValueError(f"UNKNOWN_LANGUAGE: {lang} — one of {i18n.LANGUAGES}")
    global _LANG
    _LANG = lang
    _install(lang)
    return lang


_LANG = "ja"
_ORIGINALS: dict = {}


def _install(lang: str) -> None:
    from . import garment_drape, garment_draw, garment_marks
    from . import garment_pattern, garment_sew
    import functools

    targets = [
        (garment_pattern, "draft"), (garment_pattern, "to_svg"),
        (garment_marks, "apply"),
        (garment_sew, "build"), (garment_sew, "sew_and_drape"),
        (garment_sew, "validate"),
        (garment_drape, "validate"), (garment_drape, "material_from"),
        (garment_draw, "draw"),
        (Ledger, "state"), (Ledger, "spec"), (Ledger, "worklist"),
        (Ledger, "techpack"), (Ledger, "timeline"),
        (Measures, "state"), (Measures, "sheet"),
    ]
    for owner, name in targets:
        key = (id(owner), name)
        if key not in _ORIGINALS:
            _ORIGINALS[key] = getattr(owner, name)
        original = _ORIGINALS[key]
        if lang == "ja":
            setattr(owner, name, original)
            continue

        def wrap(fn):
            @functools.wraps(fn)
            def inner(*a, **k):
                return i18n.translate(fn(*a, **k), _LANG)
            return inner

        setattr(owner, name, wrap(original))

__all__ = [
    "OBSERVED", "CONTESTED", "INFERRED", "PROPOSED", "PARTS",
    "Entry", "Ledger", "Measure", "Measures",
    "i18n", "en", "set_language", "__version__",
]
