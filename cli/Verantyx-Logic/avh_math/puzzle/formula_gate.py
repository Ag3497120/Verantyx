import re

def is_well_formed_formula(expr: str) -> bool:
    """
    論理式の構造が数学的に完結しているか（壊れていないか）を判定する。
    """
    if not expr:
        return False
    
    expr = expr.replace(" ", "")
    if len(expr) < 2:
        return False

    # 1. 矢印整合性チェック
    if expr.endswith(("->", "→", "~", "&", "|", "⊕", "<", "=", ">")):
        return False
    if "->" in expr:
        parts = expr.split("->")
        if any(not p for p in parts):
            return False

    # 2. 括弧バランス
    stack = 0
    for ch in expr:
        if ch == "(":
            stack += 1
        elif ch == ")":
            stack -= 1
            if stack < 0:
                return False
    if stack != 0:
        return False

    # 3. 許可される文字のみで構成されているか (英数字 + 記号)
    if not re.match(r'^[A-Za-z0-9\(\)\-\>\<\[\]\&\|\~□◇⊕=+\*/\^%.!]+$', expr):
        return False

    # 4. 最低限の変数・定数 (数字または英字が含まれていること)
    if not any(c.isalnum() for c in expr):
        return False

    return True

def is_global_formula(candidate, text):
    """
    抽出された式候補が、文全体の中心的な問い（全体式）であるかを判定する。
    """
    span = candidate.get("span")
    if not span:
        return False

    # 0. 形式的妥当性チェック (NEW: 壊れた式は昇格させない)
    if not is_well_formed_formula(candidate["normalized"]):
        return False

    # 空白を除いた文字数で比較
    clean_text = re.sub(r"\s+", "", text)
    clean_candidate = re.sub(r"\s+", "", candidate["surface"])
    
    coverage_ratio = len(clean_candidate) / max(len(clean_text), 1)
    
    # 決定打：様相論理・特殊キーワードによる救済
    # 式が短くても、重要な論理演算子を含み、かつ文脈に論理キーワードがあれば昇格
    logical_keywords = ["transitive", "reflexive", "symmetric", "serial", "euclidean", "推移", "反射", "対称", "妥当", "恒真"]
    has_modal_op = any(m in candidate["normalized"] for m in ["[]", "□", "<>", "◇"])
    has_context_keyword = any(k in text.lower() for k in logical_keywords)
    
    if has_modal_op and has_context_keyword:
        # 様相論理の問いである可能性が高いため、カバレッジ閾値を大幅に下げる
        if coverage_ratio > 0.15:
            return True

    # 1. 通常のカバレッジ率（文の何割を占めているか）
    if coverage_ratio < 0.6:
        return False

    # 2. 開始位置の妥当性
    # 文の25%以内から始まっている必要がある
    if candidate["span"][0] > len(text) * 0.25:
        return False

    # 3. 重要なコンテキスト（モーダル等）の欠落チェック
    # 元文に [] や □ があるのに、抽出された式に含まれていない場合は文脈を破壊している
    modals = ["[]", "□", "◇", "<>"]
    for m in modals:
        if m in text and m not in candidate["normalized"]:
            # 抽出された式の中にそのモーダル記号が含まれていないなら却下
            return False

    return True

def select_core_formula(candidates, text):
    """
    候補群から全体式を選定する。
    """
    if not candidates:
        return None, "no_candidates"

    # 1. 全体式条件を満たすものをフィルタリング
    globals = [
        c for c in candidates
        if is_global_formula(c, text)
    ]

    if globals:
        # 条件を満たす中で最もスコアが高いものを採用
        return globals[0], "global"

    # 2. 全体式が見当たらない場合、最も『それらしい』断片を返す（NEW: 決定打）
    # スコア順にソートされているため、先頭を取得
    return candidates[0], "fragment_only"
