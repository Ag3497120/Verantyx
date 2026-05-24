from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from verifier import find_counterexample, VerifyConfig, VerifyResult, find_counterexample_by_templates

@dataclass
class TacticOutcome:
    tactic_id: str
    status: str  # "hit_counterexample" | "no_counterexample" | "error"
    verify_result: Optional[VerifyResult]
    audit: List[str]

def run_tactics_for_candidate(
    formula: str,
    atoms: List[str],
    assumptions: List[str],
    tactics_db: Dict[str, Any],
) -> List[TacticOutcome]:
    outcomes: List[TacticOutcome] = []

    tactics = sorted(
        tactics_db.get("tactics", []) or [],
        key=lambda t: int(t.get("priority", 0)),
        reverse=True,
    )

    for t in tactics:
        tid = t.get("id", "tac:unknown")
        ttype = t.get("type")
        params = t.get("params", {}) or {}

        audit = [f"[TACTIC] {tid} type={ttype} params={params}"]

        try:
            if ttype == "model_search":
                cfg = VerifyConfig(
                    max_worlds=int(params.get("max_worlds", 3)),
                    max_edges=int(params.get("max_edges", 4)),
                )
                vr = find_counterexample(
                    formula=formula,
                    atoms=atoms,
                    assumptions=assumptions,
                    cfg=cfg,
                )
                audit.extend(vr.audit or [])
                if vr.status == "invalid":
                    outcomes.append(TacticOutcome(
                        tactic_id=tid,
                        status="hit_counterexample",
                        verify_result=vr,
                        audit=audit
                    ))
                    # 反例が見つかった時点で“即終了”が最強（A:反例最強）
                    return outcomes
                outcomes.append(TacticOutcome(
                    tactic_id=tid,
                    status="no_counterexample",
                    verify_result=vr,
                    audit=audit
                ))

            elif ttype == "template_search":
                # Engine側で注入された templates_db を取得
                templates_db = tactics_db.get("templates_db")
                if not templates_db:
                    outcomes.append(TacticOutcome(
                        tactic_id=tid,
                        status="error",
                        verify_result=None,
                        audit=audit + ["[ERROR] templates_db is missing in tactics_db"]
                    ))
                    continue

                vr = find_counterexample_by_templates(
                    formula=formula,
                    atoms=atoms,
                    assumptions=assumptions,
                    templates_db=templates_db,
                    max_templates=int(params.get("max_templates", 6)),
                )
                audit.extend(vr.audit or [])
                if vr.status == "invalid":
                    outcomes.append(TacticOutcome(
                        tactic_id=tid,
                        status="hit_counterexample",
                        verify_result=vr,
                        audit=audit
                    ))
                    return outcomes

                outcomes.append(TacticOutcome(
                    tactic_id=tid,
                    status="no_counterexample",
                    verify_result=vr,
                    audit=audit
                ))

            else:
                outcomes.append(TacticOutcome(
                    tactic_id=tid,
                    status="error",
                    verify_result=None,
                    audit=audit + [f"[ERROR] unknown tactic type: {ttype}"]
                ))
        except Exception as e:
            outcomes.append(TacticOutcome(
                tactic_id=tid,
                status="error",
                verify_result=None,
                audit=audit + [f"[EXCEPTION] {e}"]
            ))

    return outcomes