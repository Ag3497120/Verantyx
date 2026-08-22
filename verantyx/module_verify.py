"""Verification harness for LLM-drafted domain modules (Milestone M6).

A drafted module never reaches the human-approval queue (module_ingest.py)
unless it clears all three gates here. This is the actual safety backstop,
not the human review — a static-safety failure is rejected outright,
before a human ever sees it.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from . import domains

BANNED_NAMES = frozenset({
    "subprocess", "os", "socket", "urllib", "http", "requests", "shutil",
    "sys", "importlib", "eval", "exec", "compile", "__import__", "open",
    "input", "exit", "quit",
})

REQUIRED_FN_NAME = "ask"  # the drafted module must define `ask(store, query) -> dict`


@dataclass
class VerifyReport:
    ok: bool
    stage: str  # "static" | "sandbox" | "regression" | "passed"
    details: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "stage": self.stage, "details": self.details}


def static_safety_check(source: str) -> VerifyReport:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return VerifyReport(False, "static", [f"syntax_error: {e}"])

    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED_NAMES:
                    hits.append(f"banned_import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BANNED_NAMES:
                hits.append(f"banned_import_from: {node.module}")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            hits.append(f"banned_name: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in BANNED_NAMES:
            hits.append(f"banned_attribute: {node.attr}")

    fn_names = {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
    }
    if REQUIRED_FN_NAME not in fn_names:
        hits.append(f"missing_required_function: {REQUIRED_FN_NAME}(store, query)")

    if hits:
        return VerifyReport(False, "static", hits)
    return VerifyReport(True, "static", [])


_SAFE_BUILTINS = {
    "len", "range", "min", "max", "sum", "abs", "round", "sorted",
    "enumerate", "zip", "map", "filter", "isinstance", "str", "int",
    "float", "bool", "list", "dict", "set", "tuple", "True", "False",
    "None", "print",
    # Needed for `import re` etc to work inside the restricted namespace.
    # Safe here specifically because static_safety_check() already vets
    # every import against BANNED_NAMES before sandbox_exec ever runs —
    # this isn't an independent import boundary, it relies on that gate.
    "__import__", "__build_class__", "__name__",
}


def sandbox_exec(source: str, test_queries: List[str]) -> Tuple[VerifyReport, "Callable[..., Any] | None"]:
    """Executes the drafted source in a restricted namespace and runs it
    against `test_queries`. A crash, a non-dict return, or a missing
    "verdict" key all fail this stage — the module must at minimum behave
    like every other domain module in `domains/__init__.py`."""
    import builtins as _builtins_module
    safe_builtins = {
        name: getattr(_builtins_module, name)
        for name in _SAFE_BUILTINS
        if hasattr(_builtins_module, name)
    }
    namespace: Dict[str, Any] = {"__builtins__": safe_builtins}
    try:
        exec(compile(source, "<generated_domain_module>", "exec"), namespace)
    except Exception as e:  # noqa: BLE001 — deliberately broad, this is an untrusted-code sandbox
        return VerifyReport(False, "sandbox", [f"exec_failed: {e}"]), None

    ask_fn = namespace.get(REQUIRED_FN_NAME)
    if not callable(ask_fn):
        return VerifyReport(False, "sandbox", ["ask_not_callable"]), None

    details: List[str] = []
    for q in test_queries:
        try:
            out = ask_fn(None, q)
        except Exception as e:  # noqa: BLE001
            return VerifyReport(False, "sandbox", [f"crashed_on_query({q!r}): {e}"]), None
        if not isinstance(out, dict) or "verdict" not in out:
            return VerifyReport(
                False, "sandbox",
                [f"malformed_output_for({q!r}): {out!r}"],
            ), None
        details.append(f"{q!r} -> {out['verdict']}")

    return VerifyReport(True, "sandbox", details), ask_fn


REGRESSION_QUERIES: List[Tuple[str, str]] = [
    ("2 + 3", "math"),
    ("who calls nonexistent_fn_xyz", "code"),
]


def regression_check(store: Any) -> VerifyReport:
    """Confirms the drafted module's presence doesn't shadow or break the
    existing builtin domains (name-collision / registry corruption check).
    Runs against the *live* registry, so this must be called after a
    tentative registration and before `accept_domain_module` persists it."""
    details: List[str] = []
    for query, expected_route in REGRESSION_QUERIES:
        out = domains.try_all(store, query)
        if out.get("route") != expected_route:
            return VerifyReport(
                False, "regression",
                [f"query {query!r} expected route {expected_route!r}, got {out.get('route')!r}"],
            )
        details.append(f"{query!r} -> route={out.get('route')} verdict={out.get('verdict')}")
    return VerifyReport(True, "regression", details)


def verify_module(source: str, test_queries: List[str], store: Any, module_name: str) -> Tuple[bool, List[VerifyReport]]:
    reports = [static_safety_check(source)]
    if not reports[-1].ok:
        return False, reports

    sandbox_report, ask_fn = sandbox_exec(source, test_queries)
    reports.append(sandbox_report)
    if not sandbox_report.ok:
        return False, reports

    tentatively_registered = module_name not in {m.name for m in domains.registered()}
    if tentatively_registered:
        domains.register(domains.DomainModule(module_name, ask_fn, source="generated"))
    try:
        regression_report = regression_check(store)
    finally:
        if tentatively_registered:
            domains.unregister(module_name)
    reports.append(regression_report)
    if not regression_report.ok:
        return False, reports

    return True, reports
