import re

TOKEN_RE = re.compile(
    r"\[\]|\(\)|->|→|□|◇|<>|<->|[A-Za-z_]+|[一-龥ぁ-んァ-ン]+|\d+|[^\s]"
)


def tokenize_text(text: str) -> list[str]:
    return TOKEN_RE.findall(text or "")
