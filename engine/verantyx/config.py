"""User configuration — LLM choice, store path, Vera↔LLM allocation dial.

Persisted at ~/.verantyx.json. The allocation dial decides which domains
Vera answers itself and where the LLM is allowed to speak:

  math      "vera" (exact, default)      | "llm" (why would you)
  code      "vera" (default)             | "llm"
  known     "vera" | "llm_guided" (default: LLM rephrases Vera's facts)
  unknown   "refuse" (default) | "llm_free" (labeled unverified chat)

`vera setup` edits all of this with arrow keys.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_PATH = Path.home() / ".verantyx.json"

DEFAULT_ALLOCATION: Dict[str, str] = {
    "math": "vera",
    "code": "vera",
    "known": "llm_guided",
    "unknown": "refuse",
}


@dataclass
class VeraConfig:
    llm_model: str = ""              # empty = no LLM (solo)
    store: str = "vera_store.json"
    allocation: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ALLOCATION))
    hf_store_repo: str = ""          # e.g. "user/Verantyx-Vera-base-store"

    # Milestone O: "normal" (default, unchanged behavior -- no gap nodes are
    # ever created) | "experiment" (gap nodes persisted on UNKNOWN, no
    # auto-resolution) | "sleep" (experiment + heartbeat attempts quarantine-
    # gated resolution). Existing users who never touch this stay on
    # "normal" forever -- this field did not exist before Milestone O, so
    # anyone loading an old config.json gets the safe default via .get().
    cognition_mode: str = "normal"
    gap_max_depth: int = 1
    gap_max_new_nodes_per_run: int = 20
    gap_max_tool_calls_per_run: int = 20
    # Runtime capacity limits for the math domain. These exist as config
    # rather than only as math_sim constants because the capacity loop
    # (needs_more_capacity -> calibrate -> quarantine -> human accept)
    # needs somewhere durable to apply an accepted proposal. N_ARMS is
    # deliberately NOT here: six is the length of AXES, the geometry of
    # the cross itself, and everything else depends on it.
    math_solve_limit: int = 200
    math_mul_steps: int = 500
    # Consensus tuning, measured before being exposed (consensus_ab_eval).
    # Defaults reproduce historical behaviour exactly. What the measurement
    # showed on the synthetic corpus: matryoshka carry A matches flat
    # accuracy; B/C answer less and surface AMBIGUOUS instead — a
    # conservatism trade, not an upgrade. Geometry showed no effect there
    # (the corpus holds no opposed facts to make the pole matter).
    consensus_matryoshka: bool = False
    consensus_carry: str = "A"
    consensus_geometric: bool = False

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "VeraConfig":
        if not Path(path).is_file():
            return cls()
        d = json.loads(Path(path).read_text())
        alloc = dict(DEFAULT_ALLOCATION)
        alloc.update(d.get("allocation", {}))
        return cls(
            llm_model=d.get("llm_model", ""),
            store=d.get("store", "vera_store.json"),
            allocation=alloc,
            hf_store_repo=d.get("hf_store_repo", ""),
            cognition_mode=d.get("cognition_mode", "normal"),
            gap_max_depth=d.get("gap_max_depth", 1),
            gap_max_new_nodes_per_run=d.get("gap_max_new_nodes_per_run", 20),
            gap_max_tool_calls_per_run=d.get("gap_max_tool_calls_per_run", 20),
            math_solve_limit=d.get("math_solve_limit", 200),
            math_mul_steps=d.get("math_mul_steps", 500),
            consensus_matryoshka=d.get("consensus_matryoshka", False),
            consensus_carry=d.get("consensus_carry", "A"),
            consensus_geometric=d.get("consensus_geometric", False),
        )


def list_ollama_models() -> List[str]:
    import json as _json
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return [m["name"] for m in _json.loads(r.read()).get("models", [])]
    except Exception:
        return []


def run_setup_menu(cfg: Optional[VeraConfig] = None) -> VeraConfig:
    """Interactive setup: local LLM, allocation dial, store, HF repo."""
    from .tui import select

    cfg = cfg or VeraConfig.load()

    models = list_ollama_models()
    opts = ["(none — Vera solo, deterministic only)"] + models + ["(keep current: %s)" % (cfg.llm_model or "none")]
    i = select("Local LLM (Ollama):", opts, default=len(opts) - 1)
    if i is not None and i < len(opts) - 1:
        cfg.llm_model = "" if i == 0 else models[i - 1]

    dial: Dict[str, List[str]] = {
        "math": ["vera", "llm"],
        "code": ["vera", "llm"],
        "known": ["vera", "llm_guided"],
        "unknown": ["refuse", "llm_free"],
    }
    desc = {
        "math": "exact wire arithmetic vs LLM guessing",
        "code": "AST facts vs LLM recall",
        "known": "raw facet answer vs LLM phrasing Vera's facts",
        "unknown": "typed refusal vs labeled-unverified LLM chat",
    }
    for domain, choices in dial.items():
        cur = cfg.allocation.get(domain, choices[0])
        j = select(
            f"Allocation — {domain} ({desc[domain]}):",
            choices,
            default=choices.index(cur) if cur in choices else 0,
        )
        if j is not None:
            cfg.allocation[domain] = choices[j]

    cfg.save()
    print(f"saved → {CONFIG_PATH}")
    return cfg
