# avh_math/solution_report.py
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Literal
import time

Status = Literal[
    "proved",          # Definitive (verified)
    "disproved",       # Definitive (refuted)
    "likely_true",     # Provisional (no counterexample in bounds)
    "likely_false",    # Provisional (heuristic suspicion)
    "tentative_answer",# Provisional (weak evidence / pattern reuse)
    "insufficient_evidence", # Evidence exists but not decisive
    "silent",          # No evidence to proceed
    "unsupported",     # Parsing failed
    "error",           # Execution error
]

@dataclass
class EvidenceItem:
    id: Optional[str] = None
    domain: str = "unknown"
    kind: str = "unknown"
    title: str = ""
    snippet: str = ""
    score: float = 0.0

@dataclass
class ProofBlock:
    method: str = ""                 # "truth_table" / "kripke_search" / "symbolic" / "library" / "engine"
    steps: List[str] = field(default_factory=list)
    formal: Optional[str] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CounterexampleBlock:
    method: str = ""
    structure: Dict[str, Any] = field(default_factory=dict)
    dropped_assumption: Optional[str] = None
    failure_point: Optional[str] = None
    minimality: Optional[str] = None
    note: Optional[str] = None

@dataclass
class BoundaryBlock:
    domain_guess: str = "unknown"
    hotspots: List[Dict[str, Any]] = field(default_factory=list)
    similar_clusters: List[Dict[str, Any]] = field(default_factory=list)
    candidate_ids: List[str] = field(default_factory=list)

@dataclass
class TraceBlock:
    stages: List[Dict[str, Any]] = field(default_factory=list)
    limits: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SolutionReport:
    status: Status
    problem_key: str
    query: str
    answer_text: str

    proof: Optional[ProofBlock] = None
    counterexample: Optional[CounterexampleBlock] = None

    evidence: List[EvidenceItem] = field(default_factory=list)
    used_kb_ids: List[str] = field(default_factory=list)

    boundary: Optional[BoundaryBlock] = None

    why: Optional[str] = None
    next_actions: List[str] = field(default_factory=list)

    trace: TraceBlock = field(default_factory=TraceBlock)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def now_ms() -> int:
    return int(time.time() * 1000)
