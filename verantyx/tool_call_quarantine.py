"""Milestone R4 — mutating-tool approval for the Vera-harness (HTTP) path,
using the SAME propose/pending/accept/reject shape as AiFactQuarantine/
DomainModuleQuarantine/ProcedureQuarantine, not a new mechanism.

Context: vera_server.py's Agent construction never passes an `approver`,
so every mutating tool call in the IDE's Vera-harness chat was
unconditionally denied (agent.py's `_approve()` returns False whenever
`self.approver is None`) -- not just in Sleep mode, in every cognition
mode. The CLI's own interactive approver (arrow-key approve/always/deny)
is fundamentally synchronous and can't reach across an HTTP request/
response boundary. Rather than building a new blocking-approval protocol
over SSE, this reuses the exact pattern already proven for facts/modules/
procedures: a mutating call that has no interactive approver available
gets QUEUED instead of denied, a human reviews it whenever they next open
the IDE (same UI shape as accept_ai_fact/accept_domain_module), and only
on accept() does the tool actually run -- deferred execution, not
deferred permission.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallEntry:
    call_id: str
    tool_name: str
    args: Dict[str, Any]
    reason: str          # the LLM's own stated "thought" for this action, for human context
    task: str             # the originating task text
    ts: float = field(default_factory=time.time)
    status: str = "pending"   # pending | accepted | rejected
    result: Optional[Dict[str, Any]] = None   # filled in only once accept() actually runs the tool
    decided_ts: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id, "tool_name": self.tool_name, "args": self.args,
            "reason": self.reason, "task": self.task, "ts": self.ts, "status": self.status,
            "result": self.result, "decided_ts": self.decided_ts,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolCallEntry":
        return cls(
            call_id=d["call_id"], tool_name=d["tool_name"], args=dict(d.get("args", {})),
            reason=d.get("reason", ""), task=d.get("task", ""), ts=d.get("ts", 0.0),
            status=d.get("status", "pending"), result=d.get("result"),
            decided_ts=d.get("decided_ts"),
        )


@dataclass
class ToolCallQuarantine:
    entries: List[ToolCallEntry] = field(default_factory=list)

    def propose(self, tool_name: str, args: Dict[str, Any], *, reason: str, task: str) -> ToolCallEntry:
        entry = ToolCallEntry(call_id=f"call_{uuid.uuid4().hex[:8]}", tool_name=tool_name,
                               args=dict(args), reason=reason, task=task)
        self.entries.append(entry)
        return entry

    def get(self, call_id: str) -> Optional[ToolCallEntry]:
        for e in self.entries:
            if e.call_id == call_id:
                return e
        return None

    def pending(self) -> List[ToolCallEntry]:
        return [e for e in self.entries if e.status == "pending"]

    def accept(self, entry: ToolCallEntry, registry: Dict[str, Any]) -> Dict[str, Any]:
        """The ONLY path from a queued proposal to an actually-executed
        tool call -- never automatic. `registry` is an agent_tools.Tool
        registry (same shape build_registry() returns); the tool runs
        NOW, with whatever state currently exists (not a replay of state
        from when it was proposed)."""
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return {"ok": False, "error": "not_pending"}
        tool = registry.get(entry.tool_name)
        if tool is None:
            entry.status = "rejected"
            entry.decided_ts = time.time()
            return {"ok": False, "error": f"unknown_tool: {entry.tool_name}"}
        try:
            result = tool.fn(**entry.args)
        except TypeError as e:
            result = {"ok": False, "error": f"bad_args: {e}"}
        entry.result = result
        entry.status = "accepted"
        entry.decided_ts = time.time()
        return result

    def reject(self, entry: ToolCallEntry) -> bool:
        if not any(e is entry for e in self.entries) or entry.status != "pending":
            return False
        entry.status = "rejected"
        entry.decided_ts = time.time()
        return True

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps([e.as_dict() for e in self.entries], ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, path: Path) -> "ToolCallQuarantine":
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(entries=[ToolCallEntry.from_dict(d) for d in data])


def tool_call_quarantine_path(store_path: Path) -> Path:
    return store_path.parent / "tool_call_quarantine.json"
