import re

_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_WS = re.compile(r"[ \t]+")
_MULTI_NL = re.compile(r"\n{3,}")


def _normalize_symbols(s: str) -> str:
    s = s.replace("→", "->").replace("⇒", "->").replace("⟶", "->")
    s = s.replace("↔", "<->").replace("⇔", "<->")
    s = s.replace("∧", "&").replace("∨", "|")
    s = s.replace("¬", "~")
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("【", "[").replace("】", "]")
    return s


def _normalize_modal_tokens(s: str) -> str:
    # Canonicalize to □/◇ so downstream can convert as needed.
    s = s.replace("[]", "□").replace("<>", "◇")
    s = re.sub(r"\bbox\b", "□", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "◇", s, flags=re.IGNORECASE)
    # Glue modal operator to operand where obvious.
    s = re.sub(r"□\s+(?=[A-Za-z(~\[])", "□", s)
    s = re.sub(r"◇\s+(?=[A-Za-z(~\[])", "◇", s)
    s = re.sub(r"□\s+□\s*", "□□", s)
    s = re.sub(r"◇\s+◇\s*", "◇◇", s)
    return s


def normalize_input(text: str) -> str:
    """
    Normalize common symbol and spacing variants without destroying line structure.
    - Remove zero-width characters.
    - Normalize arrows/connectives.
    - Normalize modal tokens (box/diamond/[]/<>) to □/◇.
    - Normalize excess whitespace.
    """
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = _ZERO_WIDTH.sub("", s)
    s = _normalize_symbols(s)
    s = _normalize_modal_tokens(s)
    # Avoid collapsing all newlines, but compress excessive ones.
    s = _MULTI_NL.sub("\n\n", s)
    # Normalize spaces within lines.
    s = "\n".join(_WS.sub(" ", ln).strip() for ln in s.split("\n"))
    return s.strip()
