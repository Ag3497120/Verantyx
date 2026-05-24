from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from avh_math.verantyx.cross_assembler import AssembledTask


def parallel_map(
    fn: Callable[[Any], Any],
    items: List[Any],
    mode: str = "thread",
    workers: int = 4,
    timeout: Optional[float] = None,
) -> List[Any]:
    if not items:
        return []
    ex_cls = ThreadPoolExecutor if mode == "thread" else ProcessPoolExecutor
    out: List[Any] = []
    with ex_cls(max_workers=workers) as ex:
        futs = [ex.submit(fn, x) for x in items]
        for fut in as_completed(futs, timeout=timeout):
            out.append(fut.result())
    return out


@dataclass
class TaskResult:
    task_id: str
    formula: str
    status: str
    answer_text: str
    payload: Dict[str, Any]


def run_tasks_parallel(
    tasks: List[AssembledTask],
    solve_fn: Callable[[str], Dict[str, Any]],
    max_workers: int = 6,
) -> List[TaskResult]:
    out: List[TaskResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {}
        for t in tasks:
            futs[ex.submit(solve_fn, t.formula)] = t
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"status": "error", "answer_text": f"solver error: {e}", "payload": {}}
            out.append(
                TaskResult(
                    task_id=t.task_id,
                    formula=t.formula,
                    status=res.get("status", "unknown"),
                    answer_text=res.get("answer_text", ""),
                    payload=res.get("payload", {}) if isinstance(res.get("payload", {}), dict) else {},
                )
            )
    rank = {
        "proved": 0,
        "disproved": 1,
        "likely_true": 2,
        "likely_false": 3,
        "unsupported": 4,
        "unknown": 5,
        "error": 6,
    }
    out.sort(key=lambda r: rank.get(r.status, 99))
    return out


def run_tasks_parallel_tasks(
    tasks: List[AssembledTask],
    solve_fn: Callable[[AssembledTask], Dict[str, Any]],
    max_workers: int = 6,
) -> List[TaskResult]:
    out: List[TaskResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {}
        for t in tasks:
            futs[ex.submit(solve_fn, t)] = t
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"status": "error", "answer_text": f"solver error: {e}", "payload": {}}
            out.append(
                TaskResult(
                    task_id=t.task_id,
                    formula=t.formula,
                    status=res.get("status", "unknown"),
                    answer_text=res.get("answer_text", ""),
                    payload=res.get("payload", {}) if isinstance(res.get("payload", {}), dict) else {},
                )
            )
    rank = {
        "proved": 0,
        "disproved": 1,
        "likely_true": 2,
        "likely_false": 3,
        "unsupported": 4,
        "unknown": 5,
        "error": 6,
    }
    out.sort(key=lambda r: rank.get(r.status, 99))
    return out
