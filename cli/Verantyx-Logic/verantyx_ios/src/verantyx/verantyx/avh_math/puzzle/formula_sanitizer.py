import re
from typing import Optional

def sanitize_formula(formula: str) -> Optional[str]:
    """
    文字列から論理式に関係のない自然文ノイズを除去し、純粋な式のみを抽出する。
    """
    if not formula:
        return None

    # 1. すでに純粋な式に近い場合はそのまま返す（効率化）
    # 2. 日本語や特定のキーワードが含まれている場合、記号と英字の塊のみを抽出
    # 許容される記号: (), ->, <->, &, |, ~, [], <>, □, ◇, ⊕, 空白、および英数字
    pattern = r'[\(\)\-\>\<\[\]\&\|\s\~□◇⊕A-Za-z0-9]+'
    matches = re.findall(pattern, formula)
    
    if not matches:
        return None

    # 最も「式らしい」長い塊を採用するか、すべて結合する
    # ここでは、含意記号 (->) を含む塊を優先的に探し、なければ結合する
    candidates = [m for m in matches if len(m) >= 2]
    if not candidates:
        return None
        
    # 含意や様相記号を含むものを優先
    for c in candidates:
        if any(op in c for op in ("->", "[]", "<>", "□", "◇")):
            return c
            
    # なければ最大の塊を返す
    return max(candidates, key=len)
