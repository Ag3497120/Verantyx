"""Capacity-limit quarantine — the third sibling of AiFactQuarantine and
DomainModuleQuarantine, for calibrated limit increases instead of facts or
modules.

Same guarantee as its siblings: nothing proposed here changes a running
limit until a human calls `accept`. The entry carries the calibration
probes so the reviewer sees the evidence — which queries were re-run, at
which multipliers, and that every one of them answered — rather than a bare
"raise math_solve_limit to 1000".

The parameter whitelist is the safety boundary. `accept` writes into
VeraConfig by attribute name, and an unwhitelisted name would let a
quarantine file edit arbitrary config. The list is short on purpose:
structural constants (N_ARMS — the geometry of the cross) are not runtime
capacity and must never appear here.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The only parameters accept() may touch.
ADJUSTABLE = frozenset({"math_solve_limit", "math_mul_steps"})


@dataclass
class CapacityEntry:
    parameter: str
    current: int
    proposed: int
    normalized: str          # the bucket this came from
    reason: str              # calibrate()'s reason line
    probes: List[Dict[str, Any]]
    ts: float
    status: str = "pending"  # pending | accepted | rejected

    def as_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "current": self.current,
            "proposed": self.proposed,
            "normalized": self.normalized,
            "reason": self.reason,
            "probes": self.probes,
            "ts": self.ts,
            "status": self.status,
        }


@dataclass
class CapacityQuarantine:
    entries: List[CapacityEntry] = field(default_factory=list)

    def propose(
        self, parameter: str, current: int, proposed: int,
        normalized: str, reason: str, probes: List[Dict[str, Any]],
    ) -> Optional[CapacityEntry]:
        if parameter not in ADJUSTABLE:
            return None
        if proposed <= current:
            return None
        # One pending proposal per parameter. A second, larger proposal for
        # the same knob does not add information a reviewer can act on — it
        # adds a choice between two numbers with no basis to prefer either.
        for e in self.entries:
            if e.parameter == parameter and e.status == "pending":
                return None
        entry = CapacityEntry(
            parameter=parameter, current=current, proposed=proposed,
            normalized=normalized, reason=reason, probes=probes,
            ts=time.time(),
        )
        self.entries.append(entry)
        return entry

    def pending(self) -> List[CapacityEntry]:
        return [e for e in self.entries if e.status == "pending"]

    def accept(self, index: int, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """Applies one pending entry to VeraConfig. The ONLY path by which a
        proposed limit becomes a running limit."""
        from .config import CONFIG_PATH, VeraConfig

        pend = self.pending()
        if not 0 <= index < len(pend):
            return {"ok": False, "error": f"no pending entry {index}"}
        entry = pend[index]
        if entry.parameter not in ADJUSTABLE:
            return {"ok": False, "error": f"parameter not adjustable: {entry.parameter}"}

        path = config_path or CONFIG_PATH
        cfg = VeraConfig.load(path)
        before = getattr(cfg, entry.parameter)
        setattr(cfg, entry.parameter, entry.proposed)
        cfg.save(path)
        entry.status = "accepted"
        return {"ok": True, "parameter": entry.parameter,
                "before": before, "after": entry.proposed}

    def reject(self, index: int) -> Dict[str, Any]:
        pend = self.pending()
        if not 0 <= index < len(pend):
            return {"ok": False, "error": f"no pending entry {index}"}
        pend[index].status = "rejected"
        return {"ok": True}

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(
            [e.as_dict() for e in self.entries], indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "CapacityQuarantine":
        if not Path(path).is_file():
            return cls()
        try:
            raw = json.loads(Path(path).read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        entries = [
            CapacityEntry(
                parameter=d["parameter"], current=d["current"],
                proposed=d["proposed"], normalized=d.get("normalized", ""),
                reason=d.get("reason", ""), probes=d.get("probes", []),
                ts=d.get("ts", 0.0), status=d.get("status", "pending"),
            )
            for d in raw
        ]
        return cls(entries=entries)
