# avh_math/answer_composer.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class AnswerReport:
    answer_text: str
    status_label: str  # "Verified Valid", "Verified Invalid", "Provisional Valid", "Undetermined"
    status_color: str  # "green", "red", "yellow", "gray"
    
    # Layer 2: Boundary Proof
    minimal_conditions: List[str] = field(default_factory=list)
    boundary_failures: List[Dict[str, str]] = field(default_factory=list) # {condition: failure_reason}
    
    # Layer 3: Search Certificate
    search_depth: int = 0
    search_worlds: int = 0
    
    # Next Actions
    next_actions: List[str] = field(default_factory=list)

class AnswerComposer:
    def compose(self, query: str, solve_result: Dict[str, Any]) -> AnswerReport:
        # solve_result is expected to be the dict returned by AnswerEngine.solve (or normalized to it)
        
        # Extract core info
        status_raw = solve_result.get("status", "unknown")
        core_payload = solve_result.get("payload", {}).get("core_result", {}) or solve_result.get("payload", {})
        
        # 1. Determine Status & Answer
        if status_raw == "proved":
            status = "Verified Valid"
            color = "#22c55e" # green
            # Prefer explicit answer text, or construct from candidates
            ans = solve_result.get("answer_text") or "結論：妥当（検証済み）"
            
        elif status_raw == "disproved":
            status = "Verified Invalid"
            color = "#ef4444" # red
            ans = solve_result.get("answer_text") or "結論：非妥当（反例あり）"
            
        elif status_raw == "likely_true":
            status = "Provisional Valid"
            color = "#f59e0b" # yellow/orange
            ans = "結論：未確定（有限探索範囲内では反例なし）"
            
        elif status_raw == "likely_false":
            status = "Suspected Invalid"
            color = "#f97316" # orange
            ans = "結論：疑義あり（類似反例またはヒューリスティックによる警告）"
            
        else: # unknown / unsupported
            status = "Undetermined"
            color = "#6b7280" # gray
            ans = solve_result.get("answer_text") or "結論：判定不能（形式化エラーまたは探索不能）"

        # 2. Boundary Proof (Why it holds/fails)
        min_conds = core_payload.get("assumptions", [])
        failures = []
        
        candidates = core_payload.get("candidates", [])
        for c in candidates:
            if c.get("status") == "invalid":
                ce = c.get("counterexample")
                reason = "反例モデルが存在"
                if ce and "Witness" in ce:
                    # Simplify witness display
                    w = ce["Witness"]
                    reason = f"反例割当: {w.get('assignment') or w}"
                elif ce:
                     # If generic countermodel
                     reason = "反例モデル（グラフ参照）"
                failures.append({"condition": c.get("formula"), "reason": reason})

        # 3. Search Certificate
        limits = solve_result.get("payload", {}).get("limits", {}).get("search_budget", {})
        depth = limits.get("max_depth", 0)
        worlds = limits.get("max_worlds", 0)

        # 4. Next Actions
        actions = solve_result.get("next_actions", [])
        if not actions:
            if status == "Provisional Valid":
                actions = ["探索深度を拡大して再検証", "証明（Proof）を手動で追加"]
            elif status == "Undetermined":
                actions = ["ドメインを明示 (Domain: ...)", "仮定を追加 (Assumption: ...)"]

        return AnswerReport(
            answer_text=ans,
            status_label=status,
            status_color=color,
            minimal_conditions=min_conds,
            boundary_failures=failures,
            search_depth=depth,
            search_worlds=worlds,
            next_actions=actions
        )