def infer_strategy(similar_crosses):
    """
    類似した過去のCrossから最も頻出する戦略(strategy)を抽出する。
    """
    strategies = {}
    for c in similar_crosses:
        # Crossオブジェクトのmeta属性から戦略を取得
        meta = getattr(c, 'meta', {})
        strat = meta.get("strategy")
        if strat:
            strategies[strat] = strategies.get(strat, 0) + 1

    if not strategies:
        return {"strategy": "default_logic_check", "confidence": 0.0}

    # 最も頻出する戦略を選択
    best = max(strategies, key=strategies.get)
    conf = strategies[best] / sum(strategies.values())
    return {"strategy": best, "confidence": conf}
