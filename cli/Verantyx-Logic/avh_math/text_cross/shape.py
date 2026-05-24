def classify_shape(token: str) -> str:
    if token in {"->", "→", "<->"}:
        return "implication_arrow"
    if token in {"[]", "□"}:
        return "modal_box"
    if token in {"<>", "◇"}:
        return "modal_diamond"
    if token.isalpha():
        return "symbol"
    if token.isdigit():
        return "number"
    if token in {"&", "|", "~"}:
        return "logic_op"
    return "other"
