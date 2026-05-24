from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

from tactic_runner import run_tactics_for_candidate, TacticOutcome

@dataclass
class CandidateJobResult:
    formula: str
    outcomes: List[TacticOutcome]          # tactics の実行ログ
    final_status: str                      # "invalid" | "valid_or_unknown"
    best_counterexample: Optional[dict]    # 反例があればそれ

def _worker_run(formula: str, atoms: List[str], assumptions: List[str], tactics_db: Dict[str, Any]) -> CandidateJobResult:
    outs = run_tactics_for_candidate(formula, atoms, assumptions, tactics_db)
    # 反例が見つかったか
    for o in outs:
        if o.verify_result and o.verify_result.status == "invalid" and o.verify_result.counterexample:
            return CandidateJobResult(
                formula=formula,
                outcomes=outs,
                final_status="invalid",
                best_counterexample=o.verify_result.counterexample,
            )
    return CandidateJobResult(
        formula=formula,
        outcomes=outs,
        final_status="valid_or_unknown",
        best_counterexample=None,
    )

def run_beam_parallel(
    formulas: List[str],
    atoms: List[str],
    assumptions: List[str],
    tactics_db: Dict[str, Any],
) -> List[CandidateJobResult]:
    beam = tactics_db.get("beam", {}) or {}
    width = int(beam.get("width", 6))
    workers = int(beam.get("parallel_workers", 4))

    # Beam: いったん先頭から width 件（後でヒューリスティック入れる）
    targets = formulas[:width]

    results: List[CandidateJobResult] = []
    # Disable multiprocessing to avoid fork safety issues on macOS + Flask reloader
    # with ProcessPoolExecutor(max_workers=workers) as ex:
    #     futs = [ex.submit(_worker_run, f, atoms, assumptions, tactics_db) for f in targets]
    #     for fut in as_completed(futs):
    #         results.append(fut.result())
    
    # Serial execution fallback
    for f in targets:
        results.append(_worker_run(f, atoms, assumptions, tactics_db))

    # 元順に戻す（見た目用）
    results.sort(key=lambda r: targets.index(r.formula))
    return results