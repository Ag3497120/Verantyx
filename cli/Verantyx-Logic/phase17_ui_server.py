#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure local imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

MathEngine = None
try:
    from engine import MathEngine
except ImportError:
    try:
        from avh_math.engine import MathEngine
    except ImportError:
        pass

if MathEngine is None:
    print(f"Warning: engine.py not found in {current_dir} or avh_math package. /api/solve will fallback to retrieval.")

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-龥ぁ-んァ-ヴー]+")

try:
    from avh_math.input_normalize import normalize_input as normalize_input_shared
    from avh_math.input_structured import parse_structured_header as parse_structured_header_shared
except Exception:
    normalize_input_shared = None
    parse_structured_header_shared = None

try:
    from avh_math.engine_puzzle import PuzzleMathEngine
    PUZZLE_ENGINE = PuzzleMathEngine()
except Exception:
    PUZZLE_ENGINE = None

# Structured Header Parsers
_STRUCT_DOMAIN_RE = re.compile(r"(?im)^\s*Domain\s*:\s*([a-zA-Z0-9_]+)\s*$")
_STRUCT_ASSUME_RE = re.compile(r"(?im)^\s*Assumption(?:s)?\s*:\s*(.+?)\s*$")
_STRUCT_FORMULA_RE = re.compile(r"(?im)^\s*Formula\s*:\s*(.+?)\s*$")

def parse_structured_header(q: str) -> dict:
    if parse_structured_header_shared:
        hdr = parse_structured_header_shared(q)
        return {
            "domain": hdr.domain,
            "assumptions": hdr.assumptions,
            "formula": hdr.formula,
        }
    q = q or ""
    dom = None
    m = _STRUCT_DOMAIN_RE.search(q)
    if m:
        dom = m.group(1).strip().lower()

    assumptions: List[str] = []
    for m in _STRUCT_ASSUME_RE.finditer(q):
        parts = re.split(r"[,\s]+", m.group(1).strip().lower())
        assumptions.extend([p for p in parts if p])

    formula = None
    m = _STRUCT_FORMULA_RE.search(q)
    if m:
        formula = m.group(1).strip()

    return {"domain": dom, "assumptions": assumptions, "formula": formula}

# --- Formula-only extractor (UI-side) ---
_FORMULA_CHARS_REGEX = re.compile(r"(?:<->|->|[()~&|]|□|◇|[A-Za-z][A-Za-z0-9_]*|[⊤⊥TF])")

def rebuild_formula_only(s: str) -> str:
    toks = _FORMULA_CHARS_REGEX.findall(s or "")
    if not toks:
        return ""
    cand = " ".join(toks)
    cand = re.sub(r"\s+", " ", cand).strip()
    # Remove trailing articles that sometimes leak from natural language
    cand = re.sub(r"\b(a|an|the)\b\s*$", "", cand, flags=re.IGNORECASE).strip()
    return cand

def extract_logic_formula(text: str) -> Optional[str]:
    s = (text or "").strip()

    # 1. If "Formula:" line exists, prefer it
    m = _STRUCT_FORMULA_RE.search(s)
    if m:
        cand = rebuild_formula_only(m.group(1).strip())
        if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇")):
            return cand

    # 2. English: "Is the formula ... a tautology?"
    m = re.search(r"\bformula\b\s*(.+)$", s, flags=re.IGNORECASE)
    if m:
        tail = m.group(1)
        tail = re.sub(r"\b(is|are)\b.*$", "", tail, flags=re.IGNORECASE).strip()
        tail = re.sub(r"\b(tautology|valid|satisfiable|unsatisfiable)\b.*$", "", tail, flags=re.IGNORECASE).strip()
        tail = tail.rstrip(" ??.。！!").strip()
        cand = rebuild_formula_only(tail)
        if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇")):
            return cand

    # 3. Japanese: "...において <FORMULA> は恒真か"
    m = re.search(r"(?:において|にて)\s*(.+?)\s*(?:は|が)\s*(?:恒真|妥当|充足可能|充足不能|矛盾).*$", s)
    if m:
        cand = rebuild_formula_only(m.group(1).strip())
        if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇")):
            return cand

    # Fallback: Process whole string
    cand = rebuild_formula_only(s)
    if any(op in cand for op in ("->", "<->", "&", "|", "~", "□", "◇")):
        return cand

    return None

def tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    toks = _TOKEN_RE.findall(text)
    stop = {"the","a","an","of","and","or","in","on","to","is","are","for","with"}
    return [t for t in toks if t not in stop and len(t) >= 2]

class KBCache:
    def __init__(self, kb_path: Path, offsets: Dict[str, int]):
        self.kb_path = kb_path
        self.offsets = offsets

    def get_entry(self, eid: str) -> Dict[str, Any]:
        off = self.offsets.get(eid)
        if off is None:
            raise KeyError(eid)
        with self.kb_path.open("rb") as f:
            f.seek(off)
            line = f.readline().decode("utf-8", errors="ignore").strip()
            return json.loads(line)

def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def graph_to_nodes_edges(graph_obj: Any) -> Dict[str, Any]:
    # Phase 31: Use actual graph structure if available
    if isinstance(graph_obj, dict):
        if "nodes" in graph_obj and "edges" in graph_obj:
            return graph_obj
        if "canonical_clusters" in graph_obj:
            nodes = []
            edges = []
            clusters = graph_obj["canonical_clusters"]
            for cid, info in clusters.items():
                nodes.append({"id": cid, "label": cid, "size": len(info.get("members", []))})
            return {"nodes": nodes, "edges": edges}
    return {"nodes": [], "edges": []}

from phase32_explain import build_explanation
from phase33_proof_store import append_proof, search_proofs, make_problem_key, read_all
from avh_math.solvers.proof_checker import verify_proof
from avh_math.answer_engine import AnswerEngine, Budgets
from avh_math.input_pipeline import decompose_text
from avh_math.verantyx.cross_build import build_cross
from avh_math.verantyx.cross_pieces import extract_pieces_v2
from avh_math.verantyx.cross_assembler import assemble_tasks
from avh_math.verantyx.cross_parallel import run_tasks_parallel, run_tasks_parallel_tasks
from avh_math.verantyx.cross_patch import apply_task_results_to_cross
from avh_math.verantyx.cross_store import append_cross, load_cross_by_id
from avh_math.verantyx.cross_solver import CrossSolver
from avh_math.verantyx.cross import VerantyxCross
from avh_math.input_rules import ui_rule_text_ja, ui_rule_text_en
from avh_math.text_cross.builder import build_text_cross
from avh_math.text_cross.mapping_table import suggest_mapping

# Models
class SolveRequest(BaseModel):
    query: str
    text_cross_hint_min_score: float | None = None

class BoundaryNavRequest(BaseModel):
    query: str
    max_candidates: int = 50

class BoundaryNavResponse(BaseModel):
    query: str
    domain_guess: str
    hotspots: List[Dict[str, Any]]
    similar_clusters: List[Dict[str, Any]]
    candidate_ids: List[str]

class SubgraphRequest(BaseModel):
    ids: List[str]
    max_nodes: int = 200
    max_edges: int = 400

class ExplainRequest(BaseModel):
    query: str
    lang: str = "ja"
    max_evidence: int = 8

class ProofAddRequest(BaseModel):
    problem_key: str
    query: str
    title: str
    domain: str = "unknown"
    kind: str = "proof"
    text: str
    kb_links: list[str] = []
    lang: str = "ja"

class ProofSearchRequest(BaseModel):
    query: str = ""
    problem_key: str | None = None
    limit: int = 30

class ProofVerifyRequest(BaseModel):
    proof_id: str

class CrossBuildRequest(BaseModel):
    query: str
    domain_hint: str | None = None
    task_hint: str | None = None
    save: bool = True
    text_cross_hint_min_score: float | None = None

class CrossSolveRequest(BaseModel):
    cross_id: str | None = None
    query: str | None = None
    add_assumptions: List[str] | None = None
    text_cross_hint_min_score: float | None = None


class CrossAssembleRequest(BaseModel):
    query: str
    max_tasks: int = 24
    max_workers: int = 6
    text_cross_hint_min_score: float | None = None

def _simple_query_terms(q: str) -> List[str]:
    toks = re.split(r"[^A-Za-z0-9_\-\+\:\.\u3040-\u30FF\u4E00-\u9FFF]+", q)
    return [t for t in toks if len(t) >= 2][:64]

def _index_search_candidates(index: Dict[str, List[str]], terms: List[str], max_ids: int) -> List[str]:
    hits = []
    seen = set()
    for t in terms:
        ids = index.get(t, [])
        for _id in ids:
            if _id not in seen:
                seen.add(_id)
                hits.append(_id)
                if len(hits) >= max_ids:
                    return hits
    return hits

def normalize_modal_tokens(s: str) -> str:
    # Map all variants to [] and <> which are standard for many modal parsers
    s = s.replace("□", "[]").replace("◇", "<>")
    s = re.sub(r"\bbox\b", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.IGNORECASE)
    # Glue modal operators to operands and collapse chains
    s = re.sub(r"\[\]\s+(?=[A-Za-z(~\[])", "[]", s)
    s = re.sub(r"<>\s+(?=[A-Za-z(~\[])", "<>", s)
    s = re.sub(r"\[\]\s+\[\]\s*", "[][]", s)
    s = re.sub(r"<>\s+<>\s*", "<><>", s)
    return s

_QUOTED_FORMULA_RE = re.compile(r'["“”]([^"“”]+)["“”]|「([^」]+)」|『([^』]+)』')

def extract_quoted_formula(text: str) -> Optional[str]:
    for m in _QUOTED_FORMULA_RE.finditer(text or ""):
        frag = next((g for g in m.groups() if g), "")
        if any(op in frag for op in ("->", "<->", "&", "|", "~", "□", "◇", "[]", "<>")):
            return frag.strip()
    return None

def build_app(kb: Path, offsets_path: Path, index_path: Path, graph_path: Optional[Path], meta_path: Optional[Path], static_dir: Path) -> FastAPI:
    offsets = load_json(offsets_path)
    index = load_json(index_path)
    graph_obj = load_json(graph_path) if graph_path else {}
    meta = load_json(meta_path) if meta_path else {}
    graph_ne = graph_to_nodes_edges(graph_obj)

    kb_cache = KBCache(kb, offsets)
    
    # Init AnswerEngine
    ANSWER_ENGINE = AnswerEngine(
        kb_path=str(kb),
        budgets=Budgets(time_ms=120000, max_worlds=4, max_depth=5, max_steps=20000)
    )
    CROSS_SOLVER = CrossSolver(ANSWER_ENGINE, db_dir=str(Path(kb).parent))

    app = FastAPI(title="AVH-Math Phase34 UI")

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def root():
        p = static_dir / "index.html"
        if not p.exists():
            return HTMLResponse("<h1>index.html not found</h1>", status_code=500)
        return HTMLResponse(p.read_text(encoding="utf-8"))

    @app.get("/api/stats")
    def stats():
        return {
            "kb_ids": len(offsets),
            "index_tokens": len(index),
            "graph_nodes": len(graph_ne.get("nodes", [])),
        }

    @app.get("/api/entry/{eid}")
    def entry(eid: str):
        try:
            return kb_cache.get_entry(eid)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Entry {eid} not found")

    @app.get("/api/search")
    def search(q: str, topk: int = 200):
        toks = tokenize(q)
        freq: Dict[str, int] = {}
        for t in toks:
            for eid in index.get(t, []):
                freq[eid] = freq.get(eid, 0) + 1
        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:topk]
        return {"query": q, "candidates": ranked}

    @app.get("/api/graph")
    def get_graph():
        return graph_ne

    @app.get("/api/ui_rules")
    def api_ui_rules():
        return {
            "ja": ui_rule_text_ja(),
            "en": ui_rule_text_en(),
            "rule_key": "quote_formula_optional",
        }

    @app.post("/api/text_cross/mapping")
    def api_text_cross_mapping(req: SolveRequest):
        d = decompose_text(req.query or "")
        evidence = d.evidence or {}
        return JSONResponse(
            {
                "mapping": evidence.get("text_cross_mapping"),
                "signature": evidence.get("text_cross_signature"),
                "similar_ids": evidence.get("text_cross_similar_ids"),
                "similarity_max": evidence.get("text_cross_similarity_max"),
            }
        )

    @app.post("/api/text_cross/mapping_suggest")
    def api_text_cross_mapping_suggest(req: SolveRequest):
        text = req.query or ""
        text_cross = build_text_cross(text)
        signature = [
            n.content.get("shape", "")
            for n in text_cross.nodes.values()
            if isinstance(n.content, dict)
        ]
        mapping = suggest_mapping(signature)
        return JSONResponse(
            {
                "mapping": mapping,
                "signature": signature,
            }
        )

    # Phase 33.1 AnswerEngine Endpoint
    @app.post("/api/solve")
    def solve(req: SolveRequest):
        raw_query = req.query or ""
        data = {"payload": {}}  # ensure local exists for all branches
        # Use Puzzle engine only when explicitly requested to avoid unintended UNSUPPORTED.
        if PUZZLE_ENGINE and raw_query.lstrip().upper().startswith("PUZZLE:"):
            try:
                from avh_math.text_cross.pipeline import prepare_query_with_hint
                q2, info = prepare_query_with_hint(raw_query)
            except Exception:
                q2, info = raw_query, {}
            out = PUZZLE_ENGINE.solve(q2)
            if isinstance(out, dict):
                out.setdefault("payload", {})
                out["payload"]["text_cross"] = info
            return JSONResponse(out)
        d = decompose_text(
            raw_query,
            text_cross_hint_min_score=(
                req.text_cross_hint_min_score if req.text_cross_hint_min_score is not None else 0.25
            ),
        )
        if isinstance(d, dict):
            return JSONResponse(d)
            
        if not d.core_formula and d.domain != "law":
            return JSONResponse(
                {
                    "status": "unsupported",
                    "answer_text": "式らしい部分が見つかりませんでした。記号や括弧を含む式を入力してください。",
                    "payload": {
                        "decomp": d.__dict__,
                    },
                    "next_actions": [
                        '例: "((A -> B) & A) -> B"',
                        '例: "[]p -> [][]p"',
                        '例: "dim Sym(n,R)"',
                    ],
                }
            )
        assumptions = list(d.assumptions or [])
        try:
            from avh_math.puzzle.assumption_completion import suggest_missing_assumptions
            missing = suggest_missing_assumptions(d.core_formula or "", assumptions)
        except Exception:
            missing = []
        if missing and not assumptions and len(missing) == 1:
            assumptions = assumptions + missing
            d.assumptions = assumptions
        
        # 決定打：式だけを渡すと「常に〜か？」等の自然言語コンテキストが消失し、
        # エンジン側での query_type 推論（SET_ALL判定等）が誤作動するため、全文を渡す。
        q_for_engine = raw_query

        try:
            data = ANSWER_ENGINE.solve(q_for_engine)
        except Exception as e:
            return JSONResponse(
                {
                    "status": "error",
                    "answer_text": "Internal solver error.",
                    "payload": {
                        "error": str(e),
                        "decomp": d.__dict__,
                    },
                },
                status_code=500,
            )
        if data.get("status") in ("unsupported", "unknown"):
            msg = data.get("answer_text") or ""
            if not msg or "囲って" in msg:
                data["answer_text"] = (
                    "形式化に失敗しました。式らしい部分（記号・括弧・矢印）を含めて入力してください。"
                )
        data.setdefault("payload", {})
        data["payload"]["input_domain"] = d.domain
        data["payload"]["input_audit"] = d.audit
        data["payload"]["input_candidates_preview"] = d.candidates[:10]
        data["payload"]["input_core_formula"] = d.core_formula
        data["payload"]["decomp"] = {
            "domain": d.domain,
            "core_formula": d.core_formula,
            "candidates": d.candidates,
            "assumptions": d.assumptions,
            "atoms": d.atoms,
            "audit": d.audit,
        }
        try:
            if missing:
                data["payload"]["assumption_completion"] = {
                    "missing": missing,
                    "required": missing,
                    "axiom": None,
                }
                if assumptions and len(missing) == 1:
                    data["payload"]["assumption_completion"]["auto_applied"] = missing
                    data["payload"]["assumption_completion"]["note"] = "auto_applied_single_missing_assumption"
        except Exception:
            pass
        data["payload"]["cross"] = build_cross(
            req.query or "",
            {},
            domain_hint=None,
            task_hint=None,
            text_cross_hint_min_score=(
                req.text_cross_hint_min_score if req.text_cross_hint_min_score is not None else 0.25
            ),
        ).to_dict()
        # Ensure UI always has these keys (avoid missing sections)
        data.setdefault("proof", None)
        data.setdefault("counterexample", None)
        data.setdefault("trace", {"stages": [], "limits": {"max_worlds": None}})
        data.setdefault("next_actions", [])
        return JSONResponse(data)

    @app.post("/api/solve_puzzle")
    def solve_puzzle(req: SolveRequest):
        if not PUZZLE_ENGINE:
            raise HTTPException(status_code=500, detail="Puzzle engine not available")
        return JSONResponse(PUZZLE_ENGINE.solve(req.query or ""))

    @app.post("/api/cross/build")
    def api_cross_build(req: CrossBuildRequest):
        cross = build_cross(
            req.query,
            {},
            domain_hint=req.domain_hint,
            task_hint=req.task_hint,
            text_cross_hint_min_score=req.text_cross_hint_min_score,
        )
        if req.save:
            kb_dir = str(Path(kb).parent)
            append_cross(kb_dir, cross)
        return JSONResponse({"ok": True, "cross": cross.to_dict()})

    @app.post("/api/cross/view")
    def api_cross_view(payload: Dict[str, Any]):
        cross = payload.get("cross") if isinstance(payload, dict) else None
        if cross is None and isinstance(payload, dict) and payload.get("query"):
            hint_min = payload.get("text_cross_hint_min_score")
            cross = build_cross(
                payload.get("query"),
                {},
                domain_hint=None,
                task_hint=None,
                text_cross_hint_min_score=(hint_min if hint_min is not None else 0.25),
            ).to_dict()
        if cross is None:
            raise HTTPException(status_code=400, detail="cross or query is required")

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        def _add_nodes(arr: List[Dict[str, Any]] | None, axis_name: str) -> None:
            if not arr:
                return
            for i, n in enumerate(arr):
                nid = n.get("node_id") or n.get("id") or f"{axis_name}_{i}"
                label = (n.get("title") or n.get("label") or n.get("axis") or axis_name)
                content = n.get("content") or {}
                nodes.append({"id": nid, "label": label, "axis": axis_name, "content": content})

        _add_nodes(cross.get("syntax_nodes"), "syntax")
        _add_nodes(cross.get("semantic_nodes"), "semantic")
        _add_nodes(cross.get("assumption_nodes"), "assumption")
        _add_nodes(cross.get("counterexample_nodes"), "counterexample")
        _add_nodes(cross.get("evidence_nodes"), "evidence")

        if cross.get("solver_nodes"):
            for r in cross["solver_nodes"]:
                nodes.append(
                    {
                        "id": r.get("node_id", "res_unknown"),
                        "label": f"result:{r.get('content', {}).get('status', '?')}",
                        "axis": "result",
                        "content": r,
                    }
                )

        core_id = (cross.get("cross_id") or "cross") + "__core"
        core_formula = cross.get("core_formula") or ""
        nodes.append(
            {
                "id": core_id,
                "label": f"core:{core_formula[:50]}",
                "axis": "core",
                "content": {"formula": core_formula},
            }
        )

        if cross.get("edges"):
            for e in cross["edges"]:
                edges.append(
                    {
                        "source": e.get("source") or e.get("src"),
                        "target": e.get("target") or e.get("dst"),
                        "label": e.get("rel") or e.get("label", ""),
                    }
                )
        else:
            for n in nodes:
                if n["id"] != core_id:
                    edges.append({"source": core_id, "target": n["id"], "label": ""})

        return JSONResponse({"nodes": nodes, "edges": edges})

    @app.get("/api/cross/{cross_id}")
    def api_cross_get(cross_id: str):
        kb_dir = str(Path(kb).parent)
        obj = load_cross_by_id(kb_dir, cross_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Cross not found")
        return JSONResponse({"ok": True, "cross": obj})

    @app.post("/api/cross/solve")
    def api_cross_solve(req: CrossSolveRequest):
        def _pick_best(all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not all_results:
                return {}
            order = {
                "proved": 0,
                "disproved": 1,
                "likely_true": 2,
                "likely_false": 3,
                "unknown": 9,
                "unsupported": 10,
                "error": 11,
            }
            return sorted(
                all_results,
                key=lambda r: (order.get(r.get("status", "unknown"), 99), len(r.get("formula", ""))),
            )[0]

        def _extract_counterexample(best: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            payload = best.get("payload") or {}
            evidence = payload.get("evidence") or {}
            return evidence.get("counterexample") or best.get("counterexample") or payload.get("counterexample")

        def _extract_proof(best: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            payload = best.get("payload") or {}
            evidence = payload.get("evidence") or {}
            proof = evidence.get("proof")
            if proof:
                return {"proof": proof}
            proof_sketch = payload.get("proof_sketch") or best.get("proof_sketch")
            if proof_sketch:
                return {"proof_sketch": proof_sketch}
            return None

        def _normalize_cross_payload(cross_obj: Any) -> Dict[str, Any]:
            if cross_obj is None:
                return {}
            if isinstance(cross_obj, dict):
                return cross_obj
            if hasattr(cross_obj, "to_dict"):
                return cross_obj.to_dict()
            return {"_raw": str(cross_obj)}

        def _build_cross_view(cross_obj: Any) -> Optional[Dict[str, Any]]:
            try:
                from avh_math.verantyx.cross_view_schema import cross_to_view
            except Exception:
                return None
            try:
                return cross_to_view(cross_obj)
            except Exception:
                return None

        base_query = (req.query or "").strip()
        q = base_query
        if req.add_assumptions:
            add_line = "Assumptions: " + ", ".join(req.add_assumptions)
            if q:
                q = add_line + "\n" + q
            else:
                q = add_line
        if not q and not req.cross_id:
            raise HTTPException(status_code=400, detail="cross_id or query is required")

        raw_result: Dict[str, Any] = {}
        if q:
            cross_obj = build_cross(
                q,
                {},
                domain_hint=None,
                task_hint=None,
                text_cross_hint_min_score=req.text_cross_hint_min_score,
            )
            raw_result = CROSS_SOLVER.solve_cross_assemble(cross_obj)
        else:
            kb_dir = str(Path(kb).parent)
            obj = load_cross_by_id(kb_dir, req.cross_id)
            if not obj:
                raise HTTPException(status_code=404, detail="Cross not found")
            cross_obj = VerantyxCross.from_dict(obj)
            raw_result = CROSS_SOLVER.solve_cross_assemble(cross_obj)

        cross = _normalize_cross_payload(raw_result.get("cross"))
        all_results = raw_result.get("all_results") or raw_result.get("results") or []
        decomp = (
            raw_result.get("decomp")
            or (raw_result.get("payload") or {}).get("decomp")
            or (cross.get("meta") or {}).get("decomp")
            or {}
        )

        best = _pick_best(all_results)
        verdict = best.get("status") or (cross.get("meta") or {}).get("verdict") or "unknown"

        counterexample = _extract_counterexample(best)
        proof = _extract_proof(best)
        cross_view = _build_cross_view(cross)
        try:
            from avh_math.puzzle.assumption_completion import suggest_missing_assumptions
            missing = suggest_missing_assumptions(decomp.get("core_formula") or "", decomp.get("assumptions") or [])
        except Exception:
            missing = []

        if cross and not cross.get("core_formula") and decomp.get("core_formula"):
            cross["core_formula"] = decomp["core_formula"]

        if (not req.add_assumptions) and missing and len(missing) == 1 and verdict not in ("proved", "disproved"):
            add_line = "Assumptions: " + ", ".join(missing)
            q_retry = add_line + ("\n" + base_query if base_query else "")
            cross_obj = build_cross(
                q_retry,
                {},
                domain_hint=None,
                task_hint=None,
                text_cross_hint_min_score=req.text_cross_hint_min_score,
            )
            raw_result = CROSS_SOLVER.solve_cross_assemble(cross_obj)
            cross = _normalize_cross_payload(raw_result.get("cross"))
            all_results = raw_result.get("all_results") or raw_result.get("results") or []
            decomp = (
                raw_result.get("decomp")
                or (raw_result.get("payload") or {}).get("decomp")
                or (cross.get("meta") or {}).get("decomp")
                or {}
            )
            best = _pick_best(all_results)
            verdict = best.get("status") or (cross.get("meta") or {}).get("verdict") or verdict
            counterexample = _extract_counterexample(best)
            proof = _extract_proof(best)
            cross_view = _build_cross_view(cross)

        return JSONResponse(
            {
                "ok": True,
                "query": q,
                "verdict": verdict,
                "best": best,
                "counterexample": counterexample,
                "proof": proof,
                "all_results": all_results,
                "payload": {
                    "decomp": decomp,
                    "cross": cross,
                    "cross_view": cross_view,
                    "assumption_completion": {
                        "missing": missing,
                        "required": missing,
                        "axiom": None,
                        "auto_applied": missing if (not req.add_assumptions and missing and len(missing) == 1 and verdict in ("proved", "disproved", "likely_true", "likely_false")) else [],
                    } if missing else {},
                },
            }
        )

    @app.post("/api/cross/solve2")
    def api_cross_solve2(req: CrossSolveRequest):
        if not req.cross_id:
            raise HTTPException(status_code=400, detail="cross_id is required")
        kb_dir = str(Path(kb).parent)
        obj = load_cross_by_id(kb_dir, req.cross_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Cross not found")

        cross = VerantyxCross.from_dict(obj)
        result = CROSS_SOLVER.solve_cross(cross)
        return JSONResponse({"ok": True, "cross_id": cross.cross_id, "result": result})

    @app.post("/api/cross/solve_assemble")
    def api_cross_solve_assemble(req: CrossAssembleRequest):
        cross_obj = build_cross(
            req.query,
            {},
            domain_hint=None,
            task_hint=None,
            text_cross_hint_min_score=(
                req.text_cross_hint_min_score if req.text_cross_hint_min_score is not None else 0.25
            ),
        )
        cross_dict = cross_obj.to_dict()

        pieces = extract_pieces_v2(cross_dict)
        tasks = assemble_tasks(pieces, max_tasks=req.max_tasks)

        def _solve_task(task):
            parts = []
            if task.domain and task.domain != "unknown":
                parts.append(f"Domain: {task.domain}")
            if task.assumptions:
                parts.append("Assumptions: " + ", ".join(task.assumptions))
            parts.append(f"Formula: {task.formula}")
            return ANSWER_ENGINE.solve("\n".join(parts))

        results = run_tasks_parallel_tasks(tasks, _solve_task, max_workers=req.max_workers)
        results_dict = [r.__dict__ for r in results]
        patched = apply_task_results_to_cross(cross_dict, results_dict)

        return JSONResponse(
            {
                "ok": True,
                "cross": patched,
                "pieces": {
                    "domain": pieces.domain,
                    "core_formula": pieces.core_formula,
                    "atoms": pieces.atoms,
                    "assumptions": pieces.assumptions,
                    "syntax_formulas": pieces.syntax_formulas[:12],
                },
                "results": results_dict[:30],
            }
        )

    @app.post("/api/proof/add")
    def api_proof_add(req: ProofAddRequest):
        entry = append_proof({
            "problem_key": req.problem_key,
            "query": req.query,
            "title": req.title,
            "domain": req.domain,
            "kind": req.kind,
            "text": req.text,
            "kb_links": req.kb_links,
            "lang": req.lang,
            "status": "user_added",
        })
        return JSONResponse({"ok": True, "saved": entry})

    @app.post("/api/proof/search")
    def api_proof_search(req: ProofSearchRequest):
        items = search_proofs(
            query=req.query or "",
            problem_key=req.problem_key,
            limit=req.limit
        )
        return JSONResponse({"ok": True, "items": items})

    @app.post("/api/proof/verify")
    def api_proof_verify(req: ProofVerifyRequest):
        all_proofs = read_all(limit=10000)
        target = next((p for p in all_proofs if p["id"] == req.proof_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Proof not found")
        res = verify_proof(target)
        if res["status"] == "verified":
            target["status"] = "verified"
            target["verify_note"] = res["reason"]
        return JSONResponse({"ok": True, "result": res})

    @app.post("/api/boundary_nav", response_model=BoundaryNavResponse)
    def boundary_nav(req: BoundaryNavRequest):
        hdr = parse_structured_header(req.query)
        terms = _simple_query_terms(req.query)
        candidate_ids = _index_search_candidates(index, terms, req.max_candidates)
        domain_guess = "unknown"
        if hdr["domain"]:
            domain_guess = hdr["domain"]
        else:
            dom_count = {}
            for _id in candidate_ids:
                m = meta.get(_id, {})
                dom = m.get("domain", "unknown")
                dom_count[dom] = dom_count.get(dom, 0) + 1
            if dom_count:
                domain_guess = max(dom_count, key=dom_count.get)
        if domain_guess != "unknown":
            candidate_ids = [cid for cid in candidate_ids if meta.get(cid, {}).get("domain") == domain_guess]
        hotspots = graph_obj.get("hotspots", [])
        clusters = graph_obj.get("clusters", {})
        cluster_scores = []
        for cid, ids in clusters.items():
            s = len(set(ids) & set(candidate_ids))
            if s > 0:
                cluster_scores.append((cid, s, len(ids)))
        cluster_scores.sort(key=lambda x: (-x[1], x[2]))
        similar_clusters = [
            {"cluster_id": cid, "overlap": s, "cluster_size": size, "sample_ids": clusters[cid][:10]}
            for cid, s, size in cluster_scores[:10]
        ]
        return BoundaryNavResponse(
            query=req.query,
            domain_guess=domain_guess,
            hotspots=hotspots[:20],
            similar_clusters=similar_clusters,
            candidate_ids=candidate_ids,
        )

    @app.post("/api/graph/subgraph")
    def graph_subgraph(req: SubgraphRequest):
        nodes = graph_ne.get("nodes", [])
        edges = graph_ne.get("edges", [])
        idset = set(req.ids)
        sub_nodes = []
        sub_node_ids = set()
        for n in nodes:
            nid = n.get("id")
            if nid in idset:
                sub_nodes.append(n)
                sub_node_ids.add(nid)
                if len(sub_nodes) >= req.max_nodes:
                    break
        sub_edges = []
        for e in edges:
            s = e.get("source")
            t = e.get("target")
            if s in sub_node_ids and t in sub_node_ids:
                sub_edges.append(e)
                if len(sub_edges) >= req.max_edges:
                    break
        return JSONResponse({"nodes": sub_nodes, "edges": sub_edges})

    @app.post("/api/explain")
    def api_explain(req: ExplainRequest):
        terms = _simple_query_terms(req.query)
        candidate_ids = _index_search_candidates(index, terms, 200)
        domain_guess = "unknown"
        hdr = parse_structured_header(req.query)
        if hdr["domain"]:
            domain_guess = hdr["domain"]
        else:
            try:
                d = decompose_text(req.query or "")
                if d.domain and d.domain != "unknown":
                    domain_guess = d.domain
            except Exception:
                pass
            dom_count = {}
            for _id in candidate_ids:
                m = meta.get(_id, {})
                dom = m.get("domain", "unknown")
                dom_count[dom] = dom_count.get(dom, 0) + 1
            if dom_count:
                domain_guess = max(dom_count, key=dom_count.get)
        ex = build_explanation(
            query=req.query,
            domain_guess=domain_guess,
            candidate_ids=candidate_ids,
            lang=req.lang,
            max_evidence=req.max_evidence,
        )
        return JSONResponse({
            "query": ex.query,
            "lang": ex.lang,
            "domain_guess": ex.domain_guess,
            "summary": ex.summary,
            "why_steps": ex.why_steps,
            "evidence": ex.evidence,
            "next_actions": ex.next_actions,
        })

    return app

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--offsets", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--graph", default="")
    ap.add_argument("--meta", default="")
    ap.add_argument("--static-dir", required=True)
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    app = build_app(
        Path(args.kb), 
        Path(args.offsets), 
        Path(args.index), 
        Path(args.graph) if args.graph else None, 
        Path(args.meta) if args.meta else None,
        Path(args.static_dir)
    )
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()
