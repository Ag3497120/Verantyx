from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import re

@dataclass
class RewriteStep:
    rid: str
    before: str
    after: str
    description: str

def apply_rewrites(text: str, rewrites_db: Dict[str, Any]) -> Tuple[str, List[RewriteStep]]:
    steps: List[RewriteStep] = []
    out = text

    for rw in rewrites_db.get("rewrites", []) or []:
        rid = rw.get("id", "rw:unknown")
        pat = rw.get("pattern", "")
        rep = rw.get("replace", "")
        desc = rw.get("description", "")

        before = out
        out = re.sub(pat, rep, out)
        if out != before:
            steps.append(RewriteStep(rid=rid, before=before, after=out, description=desc))

    return out, steps