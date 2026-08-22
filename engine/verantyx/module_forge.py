"""LLM module drafting (Direction A) — asks the local LLM to write ONE
deterministic domain module for a growth candidate the boundary detector
(boundary.py) already cleared. Never runs on its own; module_verify.py must
pass the result before it ever reaches the human-approval queue.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .growth_signals import UnknownBucket
from .llm_local import ollama_generate

_STYLE_GUIDE = '''You write ONE deterministic Python function for Vera, a
knowledge engine that never hallucinates. Follow this exact style, modeled
on Vera's own math_sim.py:

  - Deterministic, trace-able, no calls to any LLM/network/subprocess.
  - Define exactly one function: `ask(store, query: str) -> dict`.
  - `store` may be ignored (pass `_store` name) if the domain does not need
    the fact graph.
  - Return {"verdict": "ANSWER", ...} on success, or a typed
    {"verdict": "UNKNOWN_UNPARSED"} when the query is not this domain's
    shape ("not my domain, try the next one" — never guess).
  - Never return generic {"verdict": "UNKNOWN"} — always a specific typed
    UNKNOWN_* string.
  - No imports beyond `re`, `math`, `dataclasses`, `typing` — nothing else.
  - No I/O, no globals mutated across calls, no randomness.

Example (do not repeat verbatim, this is style reference only):

def ask(_store, query: str) -> dict:
    q = (query or "").strip().lower()
    m = re.match(r"^(\\d+) ?km to miles$", q)
    if not m:
        return {"verdict": "UNKNOWN_UNPARSED"}
    km = int(m.group(1))
    return {"verdict": "ANSWER", "value": round(km * 0.621371, 3), "unit": "miles"}
'''


def _candidate_prompt(bucket: UnknownBucket, module_name: str) -> str:
    examples = "\n".join(f"  - {q!r}" for q in bucket.examples)
    return (
        f"{_STYLE_GUIDE}\n\n"
        f"Write a module named conceptually \"{module_name}\" that handles queries "
        f"shaped like these recurring, currently-unanswered examples:\n{examples}\n\n"
        f"Output ONLY the Python source code, no markdown fences, no explanation."
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:python)?\n", "", text)
    text = re.sub(r"\n```$", "", text)
    return text.strip()


def suggest_module_name(bucket: UnknownBucket) -> str:
    words = re.findall(r"[a-zA-Z]+", bucket.normalized)[:3]
    slug = "_".join(w.lower() for w in words) or "domain"
    return f"gen_{slug}"


def draft_module(bucket: UnknownBucket, model: str) -> Dict[str, Any]:
    """Returns {"ok": bool, "name": str, "source": str, "error": str|None}.
    Caller (mcp_server.heartbeat) is responsible for running module_verify
    on the result before it ever reaches module_ingest's approval queue."""
    name = suggest_module_name(bucket)
    prompt = _candidate_prompt(bucket, name)
    r = ollama_generate(model, prompt, num_predict=800, temperature=0.1)
    if not r.get("ok"):
        return {"ok": False, "name": name, "source": "", "error": r.get("error")}
    source = _strip_fences(r.get("text", ""))
    return {"ok": True, "name": name, "source": source, "error": None}


def build_test_queries(bucket: UnknownBucket) -> List[str]:
    return list(bucket.examples) or [bucket.normalized]
