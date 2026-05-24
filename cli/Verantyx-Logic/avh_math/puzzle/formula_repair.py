import re

LOGIC_CHARS = set("()[]¬~&|→-><>")

def looks_like_formula(s: str) -> bool:
    """文字列が論理式としての特徴を持っているか判定"""
    return any(c in s for c in LOGIC_CHARS)

def repair_partial_formula(candidate: str) -> str:
    """途中で切れた論理式を、最大限修復して数学的に完結させる"""
    if not candidate:
        return ""

    s = candidate.strip()

    # 1. 矢印で終わっている場合 (A-> ) の修復
    # とりあえずダミーの変数を補って式として成立させる（Verantyx流：形を整える）
    if s.endswith(("->", "→")):
        s = s + " q" # デフォルトの右辺を補完
    
    # 2. 演算子で終わっている場合 (A & )
    if s.endswith(("&", "|", "⊕")):
        s = s + " q"

    # 3. 括弧バランス修復
    open_paren = s.count("(")
    close_paren = s.count(")")
    if open_paren > close_paren:
        s = s + ")" * (open_paren - close_paren)
    elif close_paren > open_paren:
        # 前方に足りない分を補う（稀なケース）
        s = "(" * (close_paren - open_paren) + s

    # 4. 最低限の変数確認
    if not re.search(r"[A-Za-z]", s):
        return ""

    return s
