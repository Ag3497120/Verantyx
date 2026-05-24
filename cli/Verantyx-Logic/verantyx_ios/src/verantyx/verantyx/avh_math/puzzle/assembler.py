from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from avh_math.puzzle.pieces import pieces_for_domain
from avh_math.puzzle.shape_graph import ShapeGraph
from avh_math.puzzle.axiom_resolver import resolve_axiom_immediately
from avh_math.puzzle.assumption_completion import suggest_missing_assumptions
from avh_math.puzzle.kb_template_resolver import resolve_by_kb_templates
from avh_math.puzzle.verdict_normalizer import normalize_verdict
from pathlib import Path
from modal_kripke import prove_in_bounds
from avh_math.solvers.prop_truth_table import atoms_in as prop_atoms_in, is_tautology


@dataclass
class SolvePayload:
    status: str
    answer_text: str
    evidence: Dict[str, Any]
    decomp: Dict[str, Any]


def assemble_and_solve(graph: ShapeGraph) -> SolvePayload:
    core = graph.core_formula
    if not core:
        return SolvePayload(
            status="unsupported",
            answer_text="式が抽出できませんでした。式は必ず \"...\" で囲ってください。",
            evidence={"parse_notes": graph.notes},
            decomp=graph.__dict__,
        )

    domain = graph.domain_hint
    pieces = pieces_for_domain(domain, core, graph.norm)
    assumptions = [p.name for p in pieces if p.kind == "assumption"]
    missing = suggest_missing_assumptions(core, assumptions)
    if missing:
        assumptions.extend(missing)

    def _apply_axiom_if_needed(raw: SolvePayload) -> SolvePayload:
        if raw.status in ("proved", "disproved"):
            return raw
        ax = resolve_axiom_immediately(core, domain, assumptions)
        if not ax:
            return raw
        return SolvePayload(
            status=ax.status,
            answer_text=ax.reason,
            evidence={
                "system": ax.system,
                "note": ax.note,
                "method": "axiom_immediate",
            },
            decomp={**graph.__dict__, "assumptions": assumptions},
        )

    kb_path = Path(__file__).resolve().parents[1] / "db" / "foundation_kb.jsonl"
    kb_hit = resolve_by_kb_templates(core, kb_path, domain=domain)
    if kb_hit:
        raw = SolvePayload(
            status=kb_hit["status"],
            answer_text=f"KB template resolved: {kb_hit.get('kb_id')}",
            evidence=kb_hit,
            decomp={**graph.__dict__, "assumptions": assumptions},
        )
        return _apply_axiom_if_needed(raw)

    if domain == "propositional_logic":
        atoms = prop_atoms_in(core)
        ok, cex = is_tautology(core, atoms)
        if ok:
            raw = SolvePayload(
                status="proved",
                answer_text=f"恒真（tautology）です: {core}",
                evidence={"method": "truth_table", "atoms": atoms},
                decomp={**graph.__dict__, "assumptions": assumptions},
            )
            return _apply_axiom_if_needed(raw)
        raw = SolvePayload(
            status="disproved",
            answer_text=f"恒真ではありません（反例あり）: {core}",
            evidence={"method": "truth_table", "counterexample": {"valuation": cex, "atoms": atoms}},
            decomp={**graph.__dict__, "assumptions": assumptions},
        )
        final = normalize_verdict(
            {"status": raw.status, "method": raw.evidence.get("method")},
            assumptions=assumptions,
            candidates_exist=True,
            search_exhausted=True,
        )
        raw.status = final["status"]
        raw.evidence["note"] = final.get("note")
        return _apply_axiom_if_needed(raw)

    if domain == "modal_logic":
        max_worlds = 3
        res = prove_in_bounds(core, assumptions=assumptions, max_worlds=max_worlds)
        if res["status"] == "disproved":
            raw = SolvePayload(
                status="disproved",
                answer_text=f"妥当ではありません（反例あり）: {core}",
                evidence={"method": "kripke_search", **res},
                decomp={**graph.__dict__, "assumptions": assumptions},
            )
            final = normalize_verdict(
                {"status": raw.status, "method": raw.evidence.get("method")},
                assumptions=assumptions,
                candidates_exist=True,
                search_exhausted=True,
            )
            raw.status = final["status"]
            raw.evidence["note"] = final.get("note")
            return _apply_axiom_if_needed(raw)
        raw = SolvePayload(
            status="likely_true",
            answer_text=f"探索範囲内では反例が見つかりません: {core}",
            evidence={"method": "kripke_search", **res},
            decomp={**graph.__dict__, "assumptions": assumptions},
        )
        final = normalize_verdict(
            {"status": raw.status, "method": raw.evidence.get("method")},
            assumptions=assumptions,
            candidates_exist=True,
            search_exhausted=True,
        )
        raw.status = final["status"]
        raw.evidence["note"] = final.get("note")
        return _apply_axiom_if_needed(raw)

    raw = SolvePayload(
        status="unsupported",
        answer_text=f"このドメインはまだ完全パズル対応していません: {domain}",
        evidence={"parse_notes": graph.notes, "domain": domain},
        decomp={**graph.__dict__, "assumptions": assumptions},
    )
    final = normalize_verdict(
        {"status": raw.status, "method": raw.evidence.get("domain")},
        assumptions=assumptions,
        candidates_exist=bool(core),
        search_exhausted=False,
    )
    raw.status = final["status"]
    raw.evidence["note"] = final.get("note")
    return _apply_axiom_if_needed(raw)
