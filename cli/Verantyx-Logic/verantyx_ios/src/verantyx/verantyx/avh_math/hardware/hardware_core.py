from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

@dataclass
class HWNode:
    id: str
    op: str                 # EVAL (式評価), AND, OR, NOT, GATE (条件分岐)
    inputs: List[str]
    params: Dict[str, Any]

@dataclass
class HWGraph:
    nodes: Dict[str, HWNode] = field(default_factory=dict)
    outputs: List[str] = field(default_factory=list)
    simd_width: int = 1024 # 同時実行バッチ数

def cross_to_hw_graph(cross: Any) -> HWGraph:
    """ReasoningCross を並列演算グラフ（Hardware IR）へ変換する"""
    graph = HWGraph()
    
    # syntax ノードを EVAL ユニットとして配置
    syntax_nodes = getattr(cross, 'syntax_nodes', [])
    for i, formula in enumerate(syntax_nodes):
        node_id = f"unit_{i}"
        graph.nodes[node_id] = HWNode(
            id=node_id,
            op="EVAL",
            inputs=[],
            params={"formula": formula}
        )
        graph.outputs.append(node_id)
        
    # core_formula を優先出力ユニットとして配置
    if cross.core_formula:
        graph.nodes["core_unit"] = HWNode(
            id="core_unit",
            op="EVAL",
            inputs=[],
            params={"formula": cross.core_formula}
        )
        graph.outputs.insert(0, "core_unit")
        
    return graph
