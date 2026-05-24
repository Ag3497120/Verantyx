import os
import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from avh_math.input_normalize import normalize_input as normalize_input_shared
except Exception:
    normalize_input_shared = None

# Local imports
from decomposer import decompose_problem
from rewrite_engine import apply_rewrites
from energy import score_diffs
from proof_trace import Trace
from proof_sketch import generate_proof_sketch
from counterexample_synth import synth_cex_templates_from_kb, match_cex_template
from explainer import explain_formula
from repair import suggest_repairs
from counterexample_delta import explain_counterexample_delta
from patch_search import find_minimal_patches
from assumption_minimizer import minimize_assumptions_bfs
from patch_proof import (
    apply_patch_to_counterexample,
    check_assumption_satisfied,
    recheck_formula_with_model_search,
    model_search_wrapper
)
from search_orchestrator import run_beam_parallel
from verifier import check_model, find_counterexample, VerifyConfig

# Phase S: Solver Registry System
try:
    from solvers.registry import SolverRegistry
    from solvers.logic import PropositionalSolver
    from solvers.linear_algebra import LinearAlgebraSolver
    from solvers.backoff import BackoffSolver
    from solvers.modal_solver import ModalSolver
except ImportError:
    from avh_math.solvers.registry import SolverRegistry
    from avh_math.solvers.logic import PropositionalSolver
    from avh_math.solvers.linear_algebra import LinearAlgebraSolver
    from avh_math.solvers.backoff import BackoffSolver
    from avh_math.solvers.modal_solver import ModalSolver

# --- Phase0: Universal Input Normalizer ---
_STRUCT_DOMAIN_RE = re.compile(r"(?im)^\s*Domain\s*:\s*([a-zA-Z0-9_]+)\s*$")
_STRUCT_ASSUME_RE = re.compile(r"(?im)^\s*Assumption(?:s)?\s*:\s*(.+?)\s*$")
_STRUCT_FORMULA_RE = re.compile(r"(?im)^\s*Formula\s*:\s*(.+?)\s*$")

def _normalize_modal_words(s: str) -> str:
    s = re.sub(r"\bbox\b", "□", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "◇", s, flags=re.IGNORECASE)
    return s

def parse_structured_header(q: str) -> Dict[str, Any]:
    q = q or ""
    dom = None
    m = _STRUCT_DOMAIN_RE.search(q)
    if m:
        dom = m.group(1).strip().lower()
    assumptions: List[str] = []
    for m in _STRUCT_ASSUME_RE.finditer(q):
        parts = re.split(r"[,\\s]+", m.group(1).strip().lower())
        assumptions.extend([p for p in parts if p])
    formula = None
    m = _STRUCT_FORMULA_RE.search(q)
    if m:
        formula = m.group(1).strip()
    return {"domain": dom, "assumptions": assumptions, "formula": formula}

_FORMULA_CHARS = re.compile(r"(?:<->|->|\[\]|<>|[()~&|]|□|◇|[A-Za-z][A-Za-z0-9_]*|[⊤⊥TF])")

def rebuild_formula_only(s: str) -> str:
    toks = _FORMULA_CHARS.findall(s or "")
    if not toks: return ""
    cand = " ".join(toks)
    cand = re.sub(r"\s+", " ", cand).strip()
    # Glue modal operators to their operand: "[] p" -> "[]p", "<> p" -> "<>p"
    cand = re.sub(r"\[\]\s+(?=[A-Za-z(~\[])", "[]", cand)
    cand = re.sub(r"<>\\s+(?=[A-Za-z(~\\[])", "<>", cand)
    cand = re.sub(r"□\\s+(?=[A-Za-z(~\\[])", "□", cand)
    cand = re.sub(r"◇\\s+(?=[A-Za-z(~\\[])", "◇", cand)
    cand = re.sub(r"\[\]\s+\[\]\s*", "[][]", cand)
    cand = re.sub(r"<>\\s+<>\\s*", "<><>", cand)
    cand = re.sub(r"\b(a|an|the)\b\s*$", "", cand, flags=re.IGNORECASE).strip()
    cand = re.sub(r"\b(tautology|valid|satisfiable|unsatisfiable)\b\s*$", "", cand, flags=re.IGNORECASE).strip()
    return cand

def extract_logic_formula(text: str) -> Optional[str]:
    s = (text or "").strip()
    s = _normalize_modal_words(s)
    m = _STRUCT_FORMULA_RE.search(s)
    if m:
        cand = rebuild_formula_only(m.group(1).strip())
        if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇", "[]", "<>")): return cand
    m = re.search(r"\bformula\b\s*[:\-]?\s*(.+)", s, flags=re.IGNORECASE)
    if m:
        tail = re.sub(r"[?.!。！]+", "", m.group(1).strip()).strip()
        cand = rebuild_formula_only(tail)
        if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇", "[]", "<>")): return cand
    m = re.search(r"(?:において|にて)\s*(.+?)\s*(?:は|が)\s*(?:恒真|妥当|成立|成り立つ|反例|偽).*$", s)
    if m:
        cand = rebuild_formula_only(m.group(1).strip())
        if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇", "[]", "<>")): return cand
    cand = rebuild_formula_only(s)
    if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇", "[]", "<>")): return cand
    return None

_QUOTED_FORMULA_RE = re.compile(r'["“”]([^"“”]+)["“”]|「([^」]+)」|『([^』]+)』')

def extract_quoted_formula(text: str) -> Optional[str]:
    for m in _QUOTED_FORMULA_RE.finditer(text or ""):
        frag = next((g for g in m.groups() if g), "")
        cand = rebuild_formula_only(frag)
        if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇", "[]", "<>")):
            return cand
    return None

def coarse_domain_guess(text: str) -> str:
    s = (text or "").lower()
    if "kripke" in s or "□" in s or "◇" in s or "modal" in s: return "modal_logic"
    if any(k in s for k in ("∀","∃","forall","exists","predicate")): return "first_order_logic"
    if any(k in s for k in ("matrix","行列"," 対称行列","rank","det")): return "linear_algebra"
    if any(k in s for k in ("->","<->","&","|","~","⊤","⊥")): return "propositional_logic"
    return "unknown"

def normalize_input(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if normalize_input_shared:
        raw = normalize_input_shared(raw)
    hdr = parse_structured_header(raw)
    raw2 = _normalize_modal_words(raw)
    dom = hdr["domain"] or coarse_domain_guess(raw2)
    assumptions = hdr["assumptions"][:] if hdr["assumptions"] else []
    formula = None
    if hdr["formula"]: formula = rebuild_formula_only(hdr["formula"])
    if not formula:
        formula = extract_quoted_formula(raw2)
    if not formula:
        formula = extract_logic_formula(raw2)
    injected = []
    if dom and dom != "unknown": injected.append(f"Domain: {dom}")
    if assumptions: injected.append("Assumptions: " + ", ".join(assumptions))
    if formula:
        norm = ("\n".join(injected) + "\n" if injected else "") + f"Formula: {formula}"
    else:
        norm = ("\n".join(injected) + "\n" if injected else "") + raw2
    return {"raw": raw, "normalized": norm, "domain": dom, "assumptions": assumptions, "formula": formula}

@dataclass
class CandidateEval:
    formula: str
    status: str
    energy: int
    energy_breakdown: Dict[str, int]
    diffs: List[str]
    counterexample: Optional[Dict[str, Any]]
    audit: List[str]
    proof_sketch: Optional[Dict[str, Any]] = None
    cex_explain: Optional[Dict[str, Any]] = None
    explanation: Optional[Dict[str, Any]] = None
    repair_suggestions: Optional[List[Dict[str, Any]]] = None
    counterexample_delta: Optional[List[Dict[str, Any]]] = None
    counterexample_patch_proof: Optional[Dict[str, Any]] = None
    minimal_patches: Optional[List[Dict[str, Any]]] = None
    minimal_assumption_sets: Optional[List[List[str]]] = None

@dataclass
class SolveResult:
    ok: bool
    assumptions: List[str]
    ranked: List[CandidateEval]
    best_valid: List[str]
    trace: List[str]
    evidence_map: Optional[Dict[str, Any]] = None

class MathEngine:
    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        self.kb_path = os.path.join(db_dir, "foundation_kb.jsonl")
        self.tactics_path = os.path.join(db_dir, "tactics.json")
        self.knowledge_db_path = os.path.join(db_dir, "knowledge_db.json")
        self.tactics = self._load_json(self.tactics_path, {})
        self.knowledge_db = self._load_json(self.knowledge_db_path, {})
        
        # Initialize Solver Registry
        self.registry = SolverRegistry()
        self.registry.register(PropositionalSolver())
        self.registry.register(LinearAlgebraSolver())
        self.registry.register(ModalSolver())
        self.registry.register(BackoffSolver())

    def _load_json(self, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default

    def solve(self, text: str) -> SolveResult:
        trace = Trace()
        trace.add("[PHASE0] Universal normalizer starting.")

        # Phase 0: Normalize input
        norm = normalize_input(text)
        trace.add(f"[PHASE0] domain={norm['domain']} formula={'yes' if norm['formula'] else 'no'}")
        trace.add(f"[PHASE0] normalized='{norm['normalized'][:160]}'")

        # 1. Decomposition (Use normalized text)
        spec_obj = decompose_problem(norm["normalized"], self.knowledge_db)
        
        spec = {
            "assumptions": list(dict.fromkeys((norm["assumptions"] or []) + (getattr(spec_obj, 'assumptions', []) or []))),
            "candidates": getattr(spec_obj, 'candidates', []) or [],
            "atoms": getattr(spec_obj, 'atoms', []) or [],
            "domain": getattr(spec_obj, "domain", "unknown") or norm["domain"]
        }

        if spec.get("domain") == "modal_logic" and spec.get("candidates"):
            if os.environ.get("AVH_MODAL_INTERNAL") == "1":
                try:
                    from avh_math.solvers.modal_parse import to_internal_modal, ModalParseError
                    spec["candidates"] = [to_internal_modal(f) for f in spec["candidates"]]
                    trace.add("[PHASE1] modal surface -> internal conversion applied.")
                except ModalParseError as e:
                    trace.add(f"[PHASE1] modal parse failed: {e}")
            else:
                trace.add("[PHASE1] modal internal conversion skipped (surface syntax preserved).")

        core_formula = getattr(spec_obj, "core_formula", "") or ""
        if not spec["candidates"] and core_formula:
            spec["candidates"] = [core_formula]
            trace.add("[PHASE1] candidates were empty; injected from core_formula.")

        # If decomposer missed candidates but we have a formula, inject it
        if not spec["candidates"] and norm["formula"]:
            spec["candidates"] = [norm["formula"]]
            trace.add("[PHASE1] candidates were empty; injected from extracted formula.")

        # if decomposer missed candidates but we have an extracted formula from Phase0/Header
        if not spec["candidates"] and norm["formula"]:
            spec["candidates"] = [norm["formula"]]
            trace.add("[PHASE1] candidates were empty; injected from extracted formula.")

        # If decomposer missed candidates but we have a formula from Phase0/Header
        if not spec["candidates"] and norm["formula"]:
            spec["candidates"] = [norm["formula"]]
            trace.add("[PHASE1] candidates were empty; injected from extracted formula.")

        trace.add(f"[PHASE1] Problem decomposed. Domain hint: {spec['domain']}")

        # 2. Solver Registry Route (Phase S)
        limits = {"time_ms": 10000} # Placeholder
        solver_res = self.registry.solve(norm["normalized"], spec, limits)
        
        if solver_res.status in ("proved", "disproved", "likely_true"):
            trace.add(f"[PHASE S] Solved by {solver_res.status} logic. Answer: {solver_res.answer}")
            
            ranked = []
            # Map solver evidence back to engine format
            for f in spec["candidates"]:
                status = "unknown"
                ce = None
                audit = ["Phase S: Registry Process"]
                
                if "results" in solver_res.evidence:
                    for r in solver_res.evidence["results"]:
                        if r["formula"] == f:
                            status = "valid" if r["status"] == "proved" else "invalid"
                            ce = r["evidence"].get("counterexample")
                            break
                elif solver_res.status == "proved" and f in solver_res.answer:
                    status = "valid"
                
                ranked.append(CandidateEval(
                    formula=f,
                    status=status,
                    energy=0 if status == "valid" else 100,
                    energy_breakdown={},
                    diffs=["diff:counterexample_found"] if status == "invalid" else [],
                    counterexample=ce,
                    audit=audit
                ))
            
            best_valid = [c.formula for c in ranked if c.status == "valid"]
            
            evidence_map_serializable = {
                tag: [{"start": s.start, "end": s.end, "text": s.text} for s in spans]
                for tag, spans in getattr(spec_obj, 'evidence_map', {}).items()
            }

            return SolveResult(
                ok=True,
                assumptions=spec["assumptions"],
                ranked=ranked,
                best_valid=best_valid,
                trace=trace.lines,
                evidence_map=evidence_map_serializable
            )

        # 3. Fallback to Legacy Parallel Search
        trace.add("[PHASE1] No definitive answer from registry. Falling back to Beam Search.")
        beam_results = run_beam_parallel(
            formulas=spec["candidates"],
            atoms=spec["atoms"],
            assumptions=spec["assumptions"],
            tactics_db=self.tactics
        )

        ranked = []
        for br in beam_results:
            raw_status = br.final_status
            status = "invalid" if raw_status == "invalid" else "unknown"
            ce = br.best_counterexample
            ranked.append(CandidateEval(
                formula=br.formula,
                status=status,
                energy=0 if status == "valid" else 100,
                energy_breakdown={},
                diffs=["diff:counterexample_found"] if status == "invalid" else [],
                counterexample=ce,
                audit=[o.tactic_id for o in br.outcomes] if br.outcomes else []
            ))

        ranked = sorted(ranked, key=lambda x: (x.energy, 0 if x.status == "valid" else 1))
        best_valid = [c.formula for c in ranked if c.status == "valid"]

        evidence_map_serializable = {
            tag: [{"start": s.start, "end": s.end, "text": s.text} for s in spans]
            for tag, spans in getattr(spec_obj, 'evidence_map', {}).items()
        }

        return SolveResult(
            ok=True,
            assumptions=spec["assumptions"],
            ranked=ranked,
            best_valid=best_valid,
            trace=trace.lines,
            evidence_map=evidence_map_serializable
        )

# Alias
AVHEngine = MathEngine
