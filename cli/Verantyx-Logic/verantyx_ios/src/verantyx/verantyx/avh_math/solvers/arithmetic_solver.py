import ast
import operator
from typing import Dict, Any, Union

from avh_math.puzzle.solver_registry import SolverRegistry, SolverMeta

@SolverRegistry.register(SolverMeta(
    id="math:arith",
    domain="arithmetic",
    description="Arbitrary precision arithmetic evaluator",
    triggers=[r"[\d\s\+\-\*\/\(\)\=\^]+"],
    cost_level=1,
    timeout_ms=100,
    required_inputs=["formula"]
))
class ArithmeticSolver:
    def __init__(self):
        # 安全な演算子のマッピング
        self.operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
            ast.Pow: operator.pow,
            ast.BitXor: operator.xor, # ^ を XOR として扱うか冪乗として扱うかは文脈によるが、Python ASTでは BitXor
        }

    def _eval(self, node):
        if isinstance(node, ast.Num):  # < 3.8
            return node.n
        elif isinstance(node, ast.Constant):  # >= 3.8
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            left = self._eval(node.left)
            right = self._eval(node.right)
            op_type = type(node.op)
            if op_type in self.operators:
                return self.operators[op_type](left, right)
            raise ValueError(f"Unsupported operator: {op_type}")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand)
            op_type = type(node.op)
            if op_type in self.operators:
                return self.operators[op_type](operand)
            raise ValueError(f"Unsupported unary operator: {op_type}")
        else:
            raise TypeError(f"Unsupported AST node: {type(node)}")

    def solve(self, formula: str) -> Dict[str, Any]:
        """
        数式または等式を評価する。
        Input: "1 + 1" -> Result: 2
        Input: "1 + 1 = 2" -> Result: True (PROVED)
        """
        # クリーニング
        clean_f = formula.replace(" ", "").strip()
        
        # 等式判定 ("=" または "==")
        if "=" in clean_f:
            parts = clean_f.split("=")
            # "==" の場合も考慮して分割
            parts = [p for p in parts if p]
            
            if len(parts) == 2:
                try:
                    left_val = self._eval(ast.parse(parts[0], mode='eval').body)
                    right_val = self._eval(ast.parse(parts[1], mode='eval').body)
                    
                    # 浮動小数点の比較はイプシロン許容すべきだが、まずは厳密一致
                    is_valid = abs(left_val - right_val) < 1e-9
                    
                    if is_valid:
                        return {
                            "status": "proved",
                            "method": "arithmetic_eval",
                            "details": f"Equality holds: {left_val} == {right_val}",
                            "confidence": 1.0
                        }
                    else:
                        return {
                            "status": "disproved",
                            "method": "arithmetic_eval",
                            "counterexample": {"left": left_val, "right": right_val},
                            "details": f"Inequality: {left_val} != {right_val}",
                            "confidence": 1.0
                        }
                except Exception as e:
                    return {"status": "error", "error": str(e)}

        # 通常の評価
        try:
            tree = ast.parse(clean_f, mode='eval')
            result = self._eval(tree.body)
            return {
                "status": "evaluated", # Verantyx用語としては PROVED に寄せるか、新設するか
                "method": "arithmetic_eval",
                "result": result,
                "details": f"Calculation result: {result}",
                "confidence": 1.0
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}