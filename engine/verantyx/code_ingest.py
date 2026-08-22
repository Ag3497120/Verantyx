"""Code reasoning ingest — Python repos as cross networks (deterministic AST).

Code has explicit relations (calls, files, args, classes), which map cleanly
onto crosses:

  core   fn:<name>          one cross per function
  facets file:<relpath>, class:<cls>, arg:<name>, calls:<callee>

Queries are graph walks with typed verdicts — the engine never guesses:

  who_calls(f)   reverse edges (impact surface)
  calls_of(f)    forward edges
  impact(f)      BFS over reverse edges (what may break if f changes)

No LM, no embeddings. Unknown function → UNKNOWN_NO_EVIDENCE.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .cross_store import CrossStore

FN = "fn:"


def _calls_in(node: ast.AST) -> List[str]:
    out: List[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Name):
                out.append(f.id)
            elif isinstance(f, ast.Attribute):
                out.append(f.attr)
    return out


def ingest_python_repo(
    store: CrossStore, root: Path, *, max_files: Optional[int] = None
) -> Dict[str, Any]:
    """Walk *.py under root; one cross per function (accumulating)."""
    root = Path(root)
    n_files = n_fns = n_skipped = 0
    for py in sorted(root.rglob("*.py")):
        if max_files is not None and n_files >= max_files:
            break
        try:
            tree = ast.parse(py.read_text(errors="replace"))
        except SyntaxError:
            n_skipped += 1
            continue
        n_files += 1
        rel = str(py.relative_to(root))
        # map function → enclosing class
        cls_of: Dict[ast.AST, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    cls_of[item] = node.name
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                facets = [f"file:{rel}"]
                if node in cls_of:
                    facets.append(f"class:{cls_of[node]}")
                facets += [f"arg:{a.arg}" for a in node.args.args if a.arg != "self"]
                facets += [f"calls:{c}" for c in _calls_in(node)]
                store.add(FN + node.name, facets)
                n_fns += 1
    return {"n_files": n_files, "n_functions": n_fns, "n_skipped": n_skipped}


def _known(store: CrossStore, fn: str) -> bool:
    return store.has(FN + fn.casefold())


def calls_of(store: CrossStore, fn: str) -> Dict[str, Any]:
    fn = fn.casefold()
    if not _known(store, fn):
        return {"verdict": "UNKNOWN_NO_EVIDENCE", "fn": fn, "calls": []}
    cross = store.crosses[FN + fn]
    calls = sorted(
        f[len("calls:"):] for f in cross if f.startswith("calls:")
    )
    files = sorted(f[len("file:"):] for f in cross if f.startswith("file:"))
    return {"verdict": "ANSWER", "fn": fn, "calls": calls, "files": files}


def who_calls(store: CrossStore, fn: str) -> Dict[str, Any]:
    fn = fn.casefold()
    key = f"calls:{fn}"
    callers = sorted(
        core[len(FN):]
        for core, cross in store.crosses.items()
        if core.startswith(FN) and key in cross
    )
    if not callers and not _known(store, fn):
        return {"verdict": "UNKNOWN_NO_EVIDENCE", "fn": fn, "callers": []}
    return {"verdict": "ANSWER", "fn": fn, "callers": callers}


def impact(store: CrossStore, fn: str, *, max_depth: int = 4) -> Dict[str, Any]:
    """BFS over reverse call edges: what may break if fn changes."""
    fn = fn.casefold()
    if not _known(store, fn) and who_calls(store, fn)["verdict"] != "ANSWER":
        return {"verdict": "UNKNOWN_NO_EVIDENCE", "fn": fn, "impacted": []}
    seen: Set[str] = {fn}
    frontier = [fn]
    layers: List[List[str]] = []
    for _ in range(max_depth):
        nxt: List[str] = []
        for f in frontier:
            for caller in who_calls(store, f).get("callers", []):
                if caller not in seen:
                    seen.add(caller)
                    nxt.append(caller)
        if not nxt:
            break
        layers.append(sorted(nxt))
        frontier = nxt
    return {
        "verdict": "ANSWER",
        "fn": fn,
        "impacted": sorted(seen - {fn}),
        "layers": layers,
        "depth": len(layers),
    }


def code_ask(store: CrossStore, query: str) -> Dict[str, Any]:
    """Route natural-ish code queries: who calls X / what does X call / impact of X."""
    q = (query or "").casefold().strip().rstrip("?")
    words = q.split()
    if not words:
        return {"verdict": "UNKNOWN_UNPARSED"}
    if q.startswith("who calls "):
        return who_calls(store, words[-1])
    if q.startswith("what does ") and "call" in words:
        return calls_of(store, words[2])
    if q.startswith("impact of ") or q.startswith("what breaks if "):
        return impact(store, words[-1].replace("changes", "").strip() or words[-2])
    return {"verdict": "UNKNOWN_UNPARSED", "hint": "who calls X | what does X call | impact of X"}
