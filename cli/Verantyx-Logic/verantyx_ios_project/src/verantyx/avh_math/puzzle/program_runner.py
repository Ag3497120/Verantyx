import itertools

def emit_truth_table_code(ir):
    """命題論理の真理値表検証プログラムを生成する"""
    atoms = ir.atoms
    formula = ir.formula
    
    # Python演算子への変換
    expr = formula.replace("->", "<=").replace("<->", "==").replace("&", " and ").replace("|", " or ").replace("~", " not ")

    code = [
        "import itertools",
        "def run():",
        "    results = []",
        f"    atoms = {atoms}",
        "    for vals in itertools.product([True, False], repeat=len(atoms)):",
        "        env = dict(zip(atoms, vals))",
        "        try:",
        f"            res = eval(\"{expr}\", {{'__builtins__': None}}, env)",
        "            results.append(res)",
        "        except: continue",
        "    return all(results) if results else False"
    ]
    return "\n".join(code)

def run_program(code: str) -> bool:
    """生成されたコードを安全に実行する"""
    loc = {}
    try:
        exec(code, {"__builtins__": None, "itertools": itertools}, loc)
        return loc["run"]()
    except Exception as e:
        return False
