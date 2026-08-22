"""Failure-pack quarantine — the fourth sibling of AiFactQuarantine,
DomainModuleQuarantine and CapacityQuarantine.

Same guarantee, one more kind of knowledge: a proposed verdict changes
nothing until a human calls accept. What accept writes here is a JSON pack
into the overlay directory, where it outranks the shipped version — which
is what makes "a domain expert corrects my seeded taxonomy" a real
workflow rather than a promise.

Two things this queue does that its siblings do not need to:

  - It re-validates at accept time, not only at propose time. A pack can be
    proposed, another pack edited, and the first proposal then be stale;
    the maturity contract is cheap to re-run and expensive to skip.
  - It writes the WHOLE pack, not a diff. Packs are small, and a diff that
    applies to a file someone edited in between is precisely how an expert's
    correction gets silently reverted.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PackEntry:
    pack_name: str
    verdict: str
    #: The complete proposed pack, in on-disk JSON form.
    proposed: Dict[str, Any]
    #: The examples the author pasted — the evidence a reviewer judges. A
    #: reviewer shown only a regex is not reviewing anything.
    positives: List[str]
    negatives: List[str]
    author: str
    report: Dict[str, Any]
    ts: float
    status: str = "pending"  # pending | accepted | rejected

    def as_dict(self) -> Dict[str, Any]:
        return {
            "pack_name": self.pack_name, "verdict": self.verdict,
            "proposed": self.proposed, "positives": self.positives,
            "negatives": self.negatives, "author": self.author,
            "report": self.report, "ts": self.ts, "status": self.status,
        }


@dataclass
class PackQuarantine:
    entries: List[PackEntry] = field(default_factory=list)

    def propose(self, pack_name: str, verdict: str, proposed: Dict[str, Any],
                positives: List[str], negatives: List[str], author: str,
                report: Dict[str, Any]) -> Optional[PackEntry]:
        for e in self.entries:
            if (e.pack_name == pack_name and e.verdict == verdict
                    and e.status == "pending"):
                return None
        entry = PackEntry(pack_name=pack_name, verdict=verdict,
                          proposed=proposed, positives=positives,
                          negatives=negatives, author=author, report=report,
                          ts=time.time())
        self.entries.append(entry)
        return entry

    def pending(self) -> List[PackEntry]:
        return [e for e in self.entries if e.status == "pending"]

    def accept(self, index: int, overlay_dir: Path) -> Dict[str, Any]:
        """Write the proposed pack into the overlay directory and reload.

        The only path from proposal to a live classifier. Re-validates
        first: a proposal that was fine when made can have gone stale, and
        writing a pack the loader will then reject would leave the expert
        with a file that silently does nothing.
        """
        from .failure_domains import BUILTIN_PACK_DIR, pack_from_dict, reload_from, validate

        pend = self.pending()
        if not 0 <= index < len(pend):
            return {"ok": False, "error": f"no pending entry {index}"}
        entry = pend[index]

        try:
            dom = pack_from_dict(entry.proposed)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"proposal is not a loadable pack: {e}"}
        errs = validate(dom)
        if errs:
            return {"ok": False, "error": "proposal no longer satisfies the "
                                          "maturity contract",
                    "contract_errors": errs}

        overlay = Path(overlay_dir)
        overlay.mkdir(parents=True, exist_ok=True)
        path = overlay / f"{entry.pack_name}.json"
        path.write_text(json.dumps(entry.proposed, ensure_ascii=False, indent=1))
        entry.status = "accepted"

        result = reload_from([BUILTIN_PACK_DIR, overlay])
        return {"ok": True, "pack": entry.pack_name, "verdict": entry.verdict,
                "written_to": str(path), "reload": result}

    def reject(self, index: int) -> Dict[str, Any]:
        pend = self.pending()
        if not 0 <= index < len(pend):
            return {"ok": False, "error": f"no pending entry {index}"}
        pend[index].status = "rejected"
        return {"ok": True}

    def save(self, path: Path) -> None:
        path.write_text(json.dumps([e.as_dict() for e in self.entries],
                                   ensure_ascii=False, indent=1))

    @classmethod
    def load(cls, path: Path) -> "PackQuarantine":
        if not Path(path).is_file():
            return cls()
        try:
            raw = json.loads(Path(path).read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(entries=[
            PackEntry(pack_name=d["pack_name"], verdict=d["verdict"],
                      proposed=d["proposed"], positives=d.get("positives", []),
                      negatives=d.get("negatives", []),
                      author=d.get("author", "unknown"),
                      report=d.get("report", {}), ts=d.get("ts", 0.0),
                      status=d.get("status", "pending"))
            for d in raw
        ])
