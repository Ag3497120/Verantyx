from .cross import TextDecompositionCross


def similarity(a: TextDecompositionCross, b: TextDecompositionCross) -> float:
    a_shapes = [n.content.get("shape", "") for n in a.nodes.values()]
    b_shapes = [n.content.get("shape", "") for n in b.nodes.values()]
    if not a_shapes or not b_shapes:
        return 0.0
    return len(set(a_shapes) & set(b_shapes)) / max(len(set(a_shapes)), 1)
