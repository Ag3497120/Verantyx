from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

AXES: Tuple[str, ...] = ("+x", "-x", "+y", "-y", "+z", "-z")
# Five exposed faces per arm (attachment to center excluded).
FACE_SLOTS: Tuple[str, ...] = ("tip", "north", "south", "east", "west")


@dataclass
class LinearCross:
    """S1 wire cross: interior slots along each arm; shared center C."""

    L: int = 4
    center: Optional[str] = None
    # cells[axis][k] token or None; k=0 outer tip, k=L-1 near center
    cells: Dict[str, List[Optional[str]]] = field(default_factory=dict)
    reflections: Dict[str, Optional[str]] = field(default_factory=dict)
    read_order: List[Tuple[str, int]] = field(default_factory=list)

    def __post_init__(self):
        if not self.cells:
            self.cells = {a: [None] * self.L for a in AXES}
        if not self.reflections:
            self.reflections = {a: None for a in AXES}
        if not self.read_order:
            # default: all tips then inward
            self.read_order = [(a, k) for k in range(self.L) for a in AXES]

    def clear_wires(self):
        for a in AXES:
            self.cells[a] = [None] * self.L

    def dump_volume(self) -> int:
        return sum(1 for a in AXES for t in self.cells[a] if t is not None) + (
            1 if self.center else 0
        )


@dataclass
class ShellCross:
    """S3 shell: face labels only; interior empty."""

    center: Optional[str] = None
    faces: Dict[str, Dict[str, Optional[str]]] = field(default_factory=dict)
    reflections: Dict[str, Optional[str]] = field(default_factory=dict)
    read_order: List[Tuple[str, str]] = field(default_factory=list)  # (axis, face)

    def __post_init__(self):
        if not self.faces:
            self.faces = {a: {f: None for f in FACE_SLOTS} for a in AXES}
        if not self.reflections:
            self.reflections = {a: None for a in AXES}
        if not self.read_order:
            self.read_order = [(a, f) for a in AXES for f in FACE_SLOTS]

    def dump_volume(self) -> int:
        n = sum(1 for a in AXES for t in self.faces[a].values() if t is not None)
        return n + (1 if self.center else 0)
