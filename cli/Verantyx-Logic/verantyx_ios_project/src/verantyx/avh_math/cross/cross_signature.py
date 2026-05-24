def cross_signature(cross) -> tuple:
    """
    Reasoning Crossの形状を抽象化されたシグネチャに変換する。
    """
    # 既存のCrossオブジェクトの構造に合わせて属性を取得
    syntax_nodes = getattr(cross, 'syntax_nodes', [])
    assumption_nodes = getattr(cross, 'assumption_nodes', [])
    counterexample_nodes = getattr(cross, 'counterexample_nodes', [])
    nodes = getattr(cross, 'nodes', [])

    return (
        len(syntax_nodes),
        len(assumption_nodes),
        len(counterexample_nodes),
        tuple(sorted(getattr(n, 'axis', 'unknown') for n in nodes))
    )
