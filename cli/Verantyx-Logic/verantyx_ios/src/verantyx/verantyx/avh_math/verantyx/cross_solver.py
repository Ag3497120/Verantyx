from __future__ import annotations

from typing import Dict, Any, List, Optional

from verantyx.cross import VerantyxCross
from avh_math.verantyx.cross_pieces import extract_pieces_v2
from avh_math.verantyx.cross_assembler import assemble_tasks
from avh_math.verantyx.cross_parallel import run_tasks_parallel, run_tasks_parallel_tasks
from avh_math.verantyx.cross_patch import apply_task_results_to_cross
from avh_math.answer_engine import AnswerEngine
from avh_math.verantyx.cross_store import append_patch
from avh_math.verantyx.cross_patch import make_kb_patch, write_patches_jsonl
from pathlib import Path
import json
import re


class CrossSolver:
    """
    Verantyx Cross を唯一の真実源として解答を生成する
    """

    def __init__(self, answer_engine: AnswerEngine, db_dir: str | None = None):
        self.answer_engine = answer_engine
        self.db_dir = db_dir

    def solve_cross(self, cross: VerantyxCross) -> Dict[str, Any]:
        """
        優先順位:
        1. core_formula
        2. syntax_nodes 上位候補
        3. source_text（最終手段）
        """
        tried: List[str] = []
        results: List[Dict[str, Any]] = []

        if cross.core_formula and _looks_formula(cross.core_formula):
            tried.append(cross.core_formula)
            res = self.answer_engine.solve(cross.core_formula)
            results.append({"formula": cross.core_formula, "result": res})
            if res.get("status") in ("proved", "disproved"):
                return self._finalize(cross, results, decisive=res)

        for node in cross.syntax_nodes:
            f = (node.content or {}).get("formula")
            if not f or f in tried or not _looks_formula(f):
                continue
            tried.append(f)
            res = self.answer_engine.solve(f)
            results.append({"formula": f, "result": res})
            if res.get("status") in ("proved", "disproved"):
                return self._finalize(cross, results, decisive=res)

        if cross.source_text and cross.source_text not in tried:
            res = self.answer_engine.solve(cross.source_text)
            results.append({"formula": cross.source_text, "result": res})

        return self._finalize(cross, results)

    def solve_cross_assemble(self, cross: VerantyxCross, max_tasks: int = 24, max_workers: int = 6) -> Dict[str, Any]:
        cross_dict = cross.to_dict()
        auto_applied: List[str] = []
        attempts = 0

        context_text = (cross_dict.get("meta") or {}).get("context_text") or ""
        if not context_text:
            for n in (cross_dict.get("evidence_nodes") or []):
                c = (n.get("content") or {})
                if c.get("context_text"):
                    context_text = str(c.get("context_text"))
                    break

        def _solve_task(task: Any):
            parts = []
            if task.domain == "linear_algebra" and context_text:
                parts.append(context_text)
            if task.domain and task.domain != "unknown":
                parts.append(f"Domain: {task.domain}")
            if task.assumptions:
                parts.append("Assumptions: " + ", ".join(task.assumptions))
            parts.append(f"Formula: {task.formula}")
            return self.answer_engine.solve("\n".join(parts))

        while True:
            self._augment_cross_with_kb_patterns(cross_dict)
            pieces = extract_pieces_v2(cross_dict)
            tasks = assemble_tasks(pieces, max_tasks=max_tasks)

            results = run_tasks_parallel_tasks(tasks, _solve_task, max_workers=max_workers)
            results_dict = [r.__dict__ for r in results]
            patched = apply_task_results_to_cross(cross_dict, results_dict)

            if attempts >= 1:
                return {"cross": patched, "results": results_dict, "auto_assumptions": auto_applied}

            # Auto-apply a single missing assumption and retry once.
            try:
                from avh_math.puzzle.assumption_completion import suggest_missing_assumptions
                core_formula = (cross_dict.get("core_formula") or "")
                meta = cross_dict.get("meta") or {}
                current = meta.get("assumptions") or []
                missing = suggest_missing_assumptions(core_formula, current)
            except Exception:
                missing = []

            if not missing or len(missing) != 1:
                return {"cross": patched, "results": results_dict, "auto_assumptions": auto_applied}

            auto_applied.extend(missing)
            # Update meta and assumption nodes before retry.
            meta = cross_dict.get("meta") or {}
            meta["assumptions"] = list(sorted(set((meta.get("assumptions") or []) + missing)))
            cross_dict["meta"] = meta
            assumption_nodes = cross_dict.get("assumption_nodes") or []
            cross_id = cross_dict.get("cross_id") or "cross"
            for a in missing:
                assumption_nodes.append({
                    "id": f"{cross_id}__assume_auto_{a}",
                    "axis": "assumption",
                    "title": a,
                    "content": {"assumption": a, "source": "auto"},
                    "links": [],
                })
            cross_dict["assumption_nodes"] = assumption_nodes
            attempts += 1

    def _augment_cross_with_kb_patterns(self, cross_dict: Dict[str, Any]) -> None:
        if not self.db_dir:
            return
        kb_path = Path(self.db_dir) / "foundation_kb.jsonl"
        if not kb_path.exists():
            return

        domain = (cross_dict.get("domain") or "unknown")
        core = (cross_dict.get("core_formula") or "")
        context = ((cross_dict.get("meta") or {}).get("context_text") or "")
        tokens = _tokenize_for_kb(context + " " + core)
        if not tokens:
            return

        hits: List[str] = []
        formulas: List[str] = []
        limit = 40
        with kb_path.open("r", encoding="utf-8") as f:
            for line in f:
                if len(formulas) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("domain") != domain:
                    continue
                patterns = obj.get("patterns") or []
                statement = obj.get("statement") or ""
                text = " ".join(patterns) + " " + statement
                if not _overlap(tokens, text):
                    continue
                for p in patterns:
                    if _looks_formula(p):
                        formulas.append(p)
                if obj.get("id"):
                    hits.append(obj["id"])

        if not formulas:
            return

        syntax_nodes = cross_dict.get("syntax_nodes") or []
        start = len(syntax_nodes)
        cross_id = cross_dict.get("cross_id") or "cross"
        for i, f in enumerate(formulas[:limit]):
            syntax_nodes.append({
                "id": f"{cross_id}__kb_syn_{start + i}",
                "axis": "syntax",
                "title": "kb_pattern",
                "content": {"formula": f, "source": "kb_pattern"},
                "links": [],
            })
        cross_dict["syntax_nodes"] = syntax_nodes

        if hits:
            evidence_nodes = cross_dict.get("evidence_nodes") or []
            evidence_nodes.append({
                "id": f"{cross_id}__kb_hits",
                "axis": "evidence",
                "title": "kb_hits",
                "content": {"kb_ids": hits[:50]},
                "links": hits[:50],
            })
            cross_dict["evidence_nodes"] = evidence_nodes

    def _finalize(
        self,
        cross: VerantyxCross,
        results: List[Dict[str, Any]],
        decisive: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if decisive:
            self._record_patches(cross, decisive)
            return {
                "status": decisive.get("status"),
                "answer_text": decisive.get("answer_text"),
                "used_formula": decisive.get("payload", {}).get("formula"),
                "cross_id": cross.cross_id,
                "reasoning_path": results,
                "explanation_mode": "cross_decisive",
            }

        best = None
        for r in results:
            if r.get("result", {}).get("status") == "likely_true":
                best = r["result"]
                break

        if best:
            self._record_patches(cross, best)
            return {
                "status": "likely_true",
                "answer_text": best.get("answer_text"),
                "cross_id": cross.cross_id,
                "reasoning_path": results,
                "explanation_mode": "cross_likely",
            }

        return {
            "status": "undetermined",
            "answer_text": "検証可能な反例・証明は得られませんでしたが、境界条件は Cross に保持されています。",
            "cross_id": cross.cross_id,
            "reasoning_path": results,
            "explanation_mode": "cross_fallback",
        }

    def _record_patches(self, cross: VerantyxCross, result: Dict[str, Any]) -> None:
        if not self.db_dir:
            return
        used_kb_ids = result.get("used_kb_ids") or []
        status = result.get("status")
        if not used_kb_ids or status not in ("proved", "disproved"):
            return
        add_patterns = ["theorem_verified:true"] if status == "proved" else ["theorem_verified:false"]
        patches = [
            make_kb_patch(eid, add_patterns, f"Cross verified ({status})")
            for eid in used_kb_ids
            if eid
        ]
        if not patches:
            return
        append_patch(self.db_dir, cross.cross_id, {"kb_patches": patches})
        out_path = str(Path(self.db_dir) / "phaseX_kb_patches.jsonl")
        write_patches_jsonl(out_path, patches)


def _tokenize_for_kb(text: str) -> List[str]:
    toks = re.findall(r"[A-Za-z0-9_]+|[一-龥ぁ-んァ-ヴー]+", text or "")
    return [t.lower() for t in toks if len(t) >= 2][:128]


def _overlap(tokens: List[str], text: str) -> bool:
    t = (text or "").lower()
    return any(tok in t for tok in tokens)


def _looks_formula(s: str) -> bool:
    s = (s or "")
    return any(op in s for op in ("->", "<->", "[]", "<>", "&", "|", "~", "□", "◇"))
