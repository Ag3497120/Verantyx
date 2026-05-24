import re
from typing import List, Dict, Optional, Any

FORMULA_PATTERNS = [
    # クォートされた式（最優先）
    r'"([^"]+)"',
    r'「([^」]+)」',

    # 論理式っぽいもの
    r'[\[\]□◇()A-Za-z0-9_\s→\-&|~>]+',

    # 数式っぽいもの
    r'[A-Za-z]+\s*\([^)]*\)',
]

LOGIC_SYMBOLS = {'->', '→', '&', '|', '~', '□', '◇'}

def repair_formula(s: str) -> Optional[str]:
    """
    途中で切れた論理式を、括弧バランスを基準に修復する。
    """
    if not s:
        return None

    # 1. 括弧のバランス調整
    open_count = s.count("(")
    close_count = s.count(")")
    if open_count > close_count:
        s = s + ")" * (open_count - close_count)
    
    # 2. 致命的な欠損のチェック
    # 矢印や演算子で終わっている場合は、修復不能としてNoneを返す
    if s.strip().endswith(("->", "&", "|", "~", "⊕")):
        return None
        
    return s

def extract_formula_candidates(text: str) -> List[Dict[str, Any]]:
    """
    テキストから論理式の候補を抽出し、スコア順にソートして返す。
    スペースを含む式や、日本語に挟まれた式を強力に保護する。
    """
    if not text:
        return []

    # 決定打：スペースを許容する広域マッチング
    # 日本語文字が含まれるまで、または文末までを一つの塊として探す
    # 許容：A-Z, p-z, 0-9, (), ->, <->, &, |, ~, [], <>, □, ◇, およびスペース, バックスラッシュ(LaTeX)
    pattern = r'[\(\)[\]A-Za-z0-9\s\-\>\<&\|~□◇⊕→\\]+'
    
    raw_matches = re.finditer(pattern, text)
    candidates = []
    
    for m in raw_matches:
        s = m.group(0).strip()
        # 決定打：あまりに長い英単語（is, always, true等）が含まれる場合は式ではない可能性が高い
        # ただし、強い論理記号（[]や->）が含まれている場合は、単語が多くても式として拾う（後で正規化する）
        words = re.findall(r'[A-Za-z]{3,}', s)
        has_strong_symbol = "->" in s or "→" in s or "[]" in s or "□" in s
        
        if not has_strong_symbol and len(words) > 2:
            continue

        # 最低限、論理演算子か括弧が含まれている必要がある
        if not any(op in s for op in ("->", "→", "[]", "□", "(", ")", "&", "|", "~")):
            continue
            
        # スペースを詰め、記号を正規化して評価
        norm = s.replace(" ", "").replace("→", "->").replace("□", "[]").replace("◇", "<>")
        
        # 意味のある長さ（2文字以上）
        if len(norm) < 2:
            continue

        # スコア計算（Verantyx流：記号密度が高いほど確信度が高い）
        score = 1.0
        score += norm.count("->") * 0.5
        score += norm.count("[]") * 0.5
        score += norm.count("(") * 0.2
        # 単語が含まれる場合は減点
        score -= len(words) * 0.3
        
        candidates.append({
            "surface": s,
            "normalized": norm,
            "score": score,
            "span": m.span()
        })

    # スコア降順
    return sorted(candidates, key=lambda x: x["score"], reverse=True)

def normalize_formula(s: str) -> str:
    s = s.replace("→", "->")
    s = re.sub(r"\s+", "", s)
    return s

def score_formula_likeness(s: str) -> float:
    score = 0.0
    for sym in LOGIC_SYMBOLS:
        if sym in s:
            score += 1.0
    if "(" in s and ")" in s:
        score += 0.5
    if "[" in s or "]" in s:
        score += 0.5
    return score

def reconstruct_formula_from_shapes(shapes: List[Dict]) -> Optional[str]:
    """
    Text-Cross の分解結果（shapes）から、論理的な意味を持つトークンのみを抽出して式を再構成する。
    """
    tokens = []
    for s in shapes:
        # 推論に寄与する形状のみを採用
        if s["shape"] in ("symbol", "modal", "arrow", "bracket"):
            tokens.append(s["token"])
    
    formula = "".join(tokens).strip()
    # 最低限の長さ（例：p->q 等）を要求
    if len(formula) >= 3:
        return formula
    return None
