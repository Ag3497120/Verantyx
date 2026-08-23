"""photoloset — a garment tool that refuses to guess.

Every number that reaches a pattern can be traced to a person who measured it.
Anything that was not measured is named as not measured, and the tool declines
to draft around it.
"""

__version__ = "0.1.0"

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

__all__ = [
    "OBSERVED", "CONTESTED", "INFERRED", "PROPOSED", "PARTS",
    "Entry", "Ledger", "Measure", "Measures", "__version__",
]
