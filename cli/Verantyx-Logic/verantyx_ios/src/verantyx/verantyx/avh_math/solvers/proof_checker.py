# avh_math/solvers/proof_checker.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import json

# 既存のソルバーを利用
try:
    from avh_math.solvers.prop_truth_table import is_tautology
except ImportError:
    from avh_math.solvers.prop_truth_table import is_tautology

class ProofChecker:
    """
    証明の各ステップや、証明全体が論理的に妥当か検証する。
    """
    def __init__(self):
        pass

    def verify_proof_entry(self, proof_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        proof_library のエントリを受け取り、検証結果を返す。
        """
        kind = proof_entry.get("kind", "proof")
        text = proof_entry.get("text", "")
        query = proof_entry.get("query", "")
        domain = proof_entry.get("domain", "unknown")

        # 1. 命題論理の簡易検証 (最も確実)
        if domain == "propositional_logic" or "→" in query or "→" in text:
            return self._verify_propositional(query, text)

        # 2. その他 (現状は unknown)
        return {
            "status": "unknown",
            "reason": f"Checker for domain '{domain}' not yet implemented.",
            "evidence": None
        }

    def _verify_propositional(self, query: str, text: str) -> Dict[str, Any]:
        # クエリが恒真かチェック
        # (手書き証明の各行をパースする代わりに、まずは結論が妥当かを確認)
        try:
            res = is_tautology(query)
            if res["is_tautology"]:
                return {
                    "status": "verified",
                    "reason": "Overall claim verified via truth-table.",
                    "evidence": {"method": "truth_table"}
                }
            else:
                return {
                    "status": "refuted",
                    "reason": "Claim found to be a non-tautology (counterexample exists).",
                    "evidence": {"counterexample": res["counterexample"]}
                }
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Parse error during verification: {e}",
                "evidence": None
            }

# Global Instance
checker = ProofChecker()

def verify_proof(proof_entry: Dict[str, Any]) -> Dict[str, Any]:
    return checker.verify_proof_entry(proof_entry)
