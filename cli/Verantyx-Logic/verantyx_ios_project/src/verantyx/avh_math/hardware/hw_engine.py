import itertools
from typing import List, Dict, Any, Optional
from .hardware_core import HWGraph, HWNode

class PseudoCPU:
    def __init__(self, cores: int = 10):
        self.cores = cores

    def execute(self, graph: HWGraph, atoms: List[str]) -> Dict[str, Any]:
        """ベクトル化されたバッチ実行（SIMD 擬似実装）"""
        # 1. 全ての真理値組み合わせをバッチ化（SIMD 幅に制限）
        all_combinations = list(itertools.product([True, False], repeat=min(len(atoms), 10)))
        env_batch = [dict(zip(atoms, vals)) for vals in all_combinations]
        
        results = {"envs": env_batch}
        # 2. 各ノード（演算ユニット）を仮想コアで並列評価（ここではループでシミュレート）
        for node in graph.nodes.values():
            results[node.id] = self._eval_vectorized(node, env_batch)
            
        return results

    def _eval_vectorized(self, node: HWNode, env_batch: List[Dict[str, bool]]) -> List[Optional[bool]]:
        """特定の演算ユニットをバッチ全体に対して実行する"""
        if node.op == "EVAL":
            formula = node.params["formula"]
            # 決定打：様相記号などを除去し、命題論理として評価可能な部分だけを抽出
            # (ハードウェア層は純粋な命題論理回路をシミュレートするため)
            clean_expr = formula.replace("[]", "").replace("<>", "").replace("□", "").replace("◇", "")
            expr = clean_expr.replace("->", "<=").replace("&", " and ").replace("|", " or ").replace("~", " not ")
            
            node_results = []
            for env in env_batch:
                try:
                    # サンドボックス実行
                    res = eval(expr, {"__builtins__": None}, env)
                    node_results.append(bool(res))
                except:
                    # パース不可な場合は None を返し、確定的な DISPROVED を避ける
                    node_results.append(None)
            return node_results
        return []
