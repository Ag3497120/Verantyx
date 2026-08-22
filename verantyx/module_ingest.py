"""Domain-module quarantine — the sister of ai_ingest.py's AiFactQuarantine,
for LLM-drafted domain modules instead of LLM-proposed facts.

Same guarantee: nothing here is live in the domain registry until a human
calls `accept`. `propose_domain_module`/`accept_domain_module`/
`reject_domain_module` in mcp_server.py are the only entry points, matching
`propose_ai_facts`/`accept_ai_fact`/`reject_ai_fact` exactly.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import domains

GENERATED_DIR_NAME = "domains/generated"


@dataclass
class ModuleEntry:
    name: str
    source_code: str
    candidate_summary: str
    test_report: List[Dict[str, Any]]
    ts: float
    status: str = "pending"  # pending | accepted | rejected

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source_code": self.source_code,
            "candidate_summary": self.candidate_summary,
            "test_report": self.test_report,
            "ts": self.ts,
            "status": self.status,
        }


@dataclass
class DomainModuleQuarantine:
    entries: List[ModuleEntry] = field(default_factory=list)

    def propose(
        self, name: str, source_code: str, candidate_summary: str,
        test_report: List[Dict[str, Any]],
    ) -> ModuleEntry:
        entry = ModuleEntry(
            name=name, source_code=source_code, candidate_summary=candidate_summary,
            test_report=test_report, ts=round(time.time(), 2),
        )
        self.entries.append(entry)
        return entry

    def pending(self) -> List[ModuleEntry]:
        return [e for e in self.entries if e.status == "pending"]

    def accept(self, entry: ModuleEntry, verantyx_pkg_dir: Path) -> Optional[str]:
        """Writes the module to verantyx/domains/generated/<name>.py and
        registers it live. This is the ONLY path from quarantine to an
        active domain — never automatic, matching accept_ai_fact."""
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return None
        generated_dir = verantyx_pkg_dir / "domains" / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        init_file = generated_dir / "__init__.py"
        if not init_file.is_file():
            init_file.write_text("")
        module_path = generated_dir / f"{entry.name}.py"
        module_path.write_text(entry.source_code)

        namespace: Dict[str, Any] = {}
        exec(compile(entry.source_code, str(module_path), "exec"), namespace)
        ask_fn = namespace["ask"]
        if entry.name not in {m.name for m in domains.registered()}:
            domains.register(domains.DomainModule(entry.name, ask_fn, source="generated"))
        entry.status = "accepted"
        return str(module_path)

    def reject(self, entry: ModuleEntry) -> bool:
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return False
        entry.status = "rejected"
        return True

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps([e.as_dict() for e in self.entries], ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, path: Path) -> "DomainModuleQuarantine":
        p = Path(path)
        if not p.is_file():
            return cls()
        data = json.loads(p.read_text())
        return cls(entries=[
            ModuleEntry(
                d["name"], d["source_code"], d["candidate_summary"],
                d.get("test_report", []), d["ts"], d.get("status", "pending"),
            )
            for d in data
        ])
