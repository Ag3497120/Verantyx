"""Milestone Q4 — Procedure quarantine, the sister of module_ingest.py's
DomainModuleQuarantine (which is itself the sister of ai_ingest.py's
AiFactQuarantine). Same guarantee, same shape: nothing here is callable
via procedure_exec's registry until a human calls `accept`.

Not yet wired to an LLM-generation source (Milestone Q's own explicit
scope: this is the queue/type, not the JGEN-candidate-generation path --
that's future work, same as module_ingest.py's propose_domain_module also
accepts hand-written candidates today, not just LLM-drafted ones).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import procedure_exec
from .procedure import Procedure


@dataclass
class ProcedureEntry:
    procedure: Procedure
    candidate_summary: str
    verify_report: Dict[str, Any]
    ts: float
    status: str = "pending"  # pending | accepted | rejected

    def as_dict(self) -> Dict[str, Any]:
        return {
            "procedure": self.procedure.as_dict(),
            "candidate_summary": self.candidate_summary,
            "verify_report": self.verify_report,
            "ts": self.ts,
            "status": self.status,
        }


@dataclass
class ProcedureQuarantine:
    entries: List[ProcedureEntry] = field(default_factory=list)

    def propose(
        self, proc: Procedure, candidate_summary: str, verify_report: Dict[str, Any],
    ) -> ProcedureEntry:
        entry = ProcedureEntry(
            procedure=proc, candidate_summary=candidate_summary,
            verify_report=verify_report, ts=round(time.time(), 2),
        )
        self.entries.append(entry)
        return entry

    def pending(self) -> List[ProcedureEntry]:
        return [e for e in self.entries if e.status == "pending"]

    def accept(self, entry: ProcedureEntry, procedures_dir: Path) -> Optional[str]:
        """Writes the Procedure as JSON to verantyx/procedures/generated/
        and registers it live in procedure_exec's registry. The ONLY path
        from quarantine to an executable procedure -- never automatic,
        matching accept_ai_fact / accept_domain_module."""
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return None
        generated_dir = procedures_dir / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        out_path = generated_dir / f"{entry.procedure.procedure_id}.json"
        entry.procedure.status = "TRUSTED"
        out_path.write_text(json.dumps(entry.procedure.as_dict(), ensure_ascii=False, indent=2))
        procedure_exec.register_procedure(entry.procedure)
        entry.status = "accepted"
        return str(out_path)

    def reject(self, entry: ProcedureEntry) -> bool:
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return False
        entry.status = "rejected"
        return True

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps([e.as_dict() for e in self.entries], ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, path: Path) -> "ProcedureQuarantine":
        p = Path(path)
        if not p.is_file():
            return cls()
        data = json.loads(p.read_text())
        return cls(entries=[
            ProcedureEntry(
                Procedure.from_dict(d["procedure"]), d["candidate_summary"],
                d.get("verify_report", {}), d["ts"], d.get("status", "pending"),
            )
            for d in data
        ])
