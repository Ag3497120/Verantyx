from typing import List

def detect_natural_language_assumptions(text: str) -> List[str]:
    """自然文から論理的な制約・主張を抽出し、タグとして返す"""
    assumptions = []

    # 意味理解なしのパターンマッチング
    patterns = {
        "assume:universal_logic": [
            "どんな論理体系でも",
            "すべての論理体系で",
            "あらゆる論理体系",
            "any logical system",
            "all logics",
            "regardless of the logic",
        ],
        "assume:classical": [
            "命題論理で",
            "古典論理",
            "classical logic",
        ],
        "assume:modal": [
            "様相",
            "kripke",
            "modal logic",
        ],
        "assume:transitive": [
            "推移的",
            "推移律",
            "transitive",
        ],
        "assume:reflexive": [
            "反射的",
            "反射律",
            "reflexive",
        ],
        "assume:symmetric": [
            "対称的",
            "対称律",
            "symmetric",
        ],
        "assume:serial": [
            "直列的",
            "serial",
        ],
        "assume:euclidean": [
            "ユークリッド",
            "euclidean",
        ],
    }

    for tag, phrases in patterns.items():
        for p in phrases:
            if p in text:
                assumptions.append(tag)
                break

    return assumptions
