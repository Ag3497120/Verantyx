"""Domain registry — pluggable deterministic answer modules.

`router._vera_answer` used to be a hardcoded `math -> code -> knowledge`
chain. Milestone M (self-growing domain modules) needs new modules to be
addable without hand-editing router.py each time, so the chain is now a
registry: each `DomainModule` is a plain (name, ask_fn) pair, tried in
registration order before falling through to the knowledge layer
(ja consensus / consensus_over_store), which always stays last and is not
part of this registry.

`ask_fn(store, query) -> Dict[str, Any]` must return a dict with a
"verdict" key. "UNKNOWN_UNPARSED" means "not my domain, try the next one" —
every other verdict (ANSWER, AMBIGUOUS, UNKNOWN_NO_EVIDENCE, ...) is treated
as this domain's real (possibly negative) answer and stops the chain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from ..cross_store import CrossStore

AskFn = Callable[[CrossStore, str], Dict[str, Any]]

NOT_MY_DOMAIN = "UNKNOWN_UNPARSED"


@dataclass
class DomainModule:
    name: str
    ask_fn: AskFn
    source: str = "builtin"  # "builtin" | "generated"


_registry: List[DomainModule] = []


def register(module: DomainModule) -> None:
    if any(m.name == module.name for m in _registry):
        raise ValueError(f"domain already registered: {module.name}")
    _registry.append(module)


def unregister(name: str) -> bool:
    global _registry
    before = len(_registry)
    _registry = [m for m in _registry if m.name != name]
    return len(_registry) != before


def registered() -> List[DomainModule]:
    return list(_registry)


def try_all(store: CrossStore, query: str, skip: "set[str] | None" = None) -> Dict[str, Any]:
    """Try each registered domain in order; first non-NOT_MY_DOMAIN verdict
    wins. Returns a NOT_MY_DOMAIN dict if every domain passes. `skip` lets
    callers honor router.py's per-domain allocation dial (e.g. "math":
    "llm" routes math queries to the LLM instead of this registry)."""
    skip = skip or set()
    for module in _registry:
        if module.name in skip:
            continue
        out = module.ask_fn(store, query)
        if out.get("verdict") != NOT_MY_DOMAIN:
            out = dict(out)
            out["route"] = module.name
            return out
    return {"verdict": NOT_MY_DOMAIN}


def register_builtins() -> None:
    """Registers math/code as builtins, matching router.py's prior fixed
    priority. Idempotent: no-ops if already registered (e.g. re-import)."""
    if any(m.name in ("math", "code") for m in _registry):
        return
    from ..math_sim import math_ask
    from ..code_ingest import code_ask
    from ..kripke import kripke_ask

    def _math_with_config_limits(_store, q):
        # Reads VeraConfig per call so an accepted capacity proposal takes
        # effect without a restart. The file is a few hundred bytes of JSON;
        # at interactive query rates that cost is noise, and the alternative
        # — a cached value someone must remember to invalidate on accept —
        # is exactly the kind of silent staleness this codebase keeps
        # getting bitten by.
        from ..config import VeraConfig
        cfg = VeraConfig.load()
        return math_ask(q, solve_limit=cfg.math_solve_limit,
                        mul_steps=cfg.math_mul_steps)

    register(DomainModule("math", _math_with_config_limits))
    register(DomainModule("code", code_ask))
    register(DomainModule("kripke", kripke_ask))


def register_generated(pkg_dir) -> List[str]:
    """Loads previously-accepted generated modules from disk on startup —
    the registry is in-memory only, so without this a restart would silently
    lose every module `accept_domain_module` (module_ingest.py) approved in
    a prior session, even though the .py file is still on disk."""
    import importlib.util

    generated_dir = pkg_dir / "domains" / "generated"
    if not generated_dir.is_dir():
        return []
    loaded: List[str] = []
    for py_file in sorted(generated_dir.glob("*.py")):
        if py_file.stem in ("__init__",):
            continue
        name = py_file.stem
        if any(m.name == name for m in _registry):
            continue
        spec = importlib.util.spec_from_file_location(f"verantyx.domains.generated.{name}", py_file)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            ask_fn = getattr(module, "ask")
        except Exception:  # noqa: BLE001 — a corrupt generated file must not crash startup
            continue
        register(DomainModule(name, ask_fn, source="generated"))
        loaded.append(name)
    return loaded
