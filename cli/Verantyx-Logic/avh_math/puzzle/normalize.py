from __future__ import annotations

import re
from typing import List

ARROW_MAP = {
    "→": "->", "⇒": "->", "⟶": "->", "⟹": "->",
    "←": "<-", "↔": "<->", "⇔": "<->",
    "¬": "~", "∧": "&", "∨": "|",
    "□": "[]", "◇": "<>",
}

_QUOTED_RE = re.compile(r'"([^"]+)"|“([^”]+)”|「([^」]+)」|『([^』]+)』')


def extract_quoted(text: str) -> List[str]:
    out: List[str] = []
    for m in _QUOTED_RE.finditer(text or ""):
        for g in m.groups():
            if g:
                out.append(g.strip())
                break
    return out


def normalize_text(text: str) -> str:
    t = (text or "")
    for k, v in ARROW_MAP.items():
        t = t.replace(k, v)
    t = t.replace("\u200b", "").replace("\ufeff", "")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def normalize_formula(s: str) -> str:
    s = normalize_text(s)
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\[\]\s+", "[]", s)
    s = re.sub(r"<>\s+", "<>", s)
    s = re.sub(r"\s*->\s*", "->", s)
    s = re.sub(r"\s*<->\s*", "<->", s)
    s = re.sub(r"\s*&\s*", "&", s)
    s = re.sub(r"\s*\|\s*", "|", s)
    s = re.sub(r"\s*~\s*", "~", s)
    s = s.replace("( ", "(").replace(" )", ")")
    return s


def detect_broken_arrow(formula: str) -> bool:
    f = normalize_formula(formula)
    if f.endswith(("->", "<->", "&", "|")):
        return True
    if re.search(r"\[\](\)|$)", f):
        return True
    return False
