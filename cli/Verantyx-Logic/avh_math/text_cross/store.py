from typing import List
import json
import os
from pathlib import Path

from .cross import TextDecompositionCross

KB_PATH = Path("avh_math/db/text_cross_kb.jsonl")


def store_cross(cross: TextDecompositionCross) -> None:
    if os.environ.get("AVH_READONLY_DB", "").strip() == "1":
        return
    KB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with KB_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(cross.to_dict(), ensure_ascii=False) + "\n")


def all_crosses(limit: int = 5000) -> List[TextDecompositionCross]:
    if not KB_PATH.exists():
        return []
    out: List[TextDecompositionCross] = []
    with KB_PATH.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            out.append(TextDecompositionCross.from_dict(obj))
    return out


def load_cross_by_id(cross_id: str, limit: int = 200000) -> TextDecompositionCross | None:
    if not KB_PATH.exists():
        return None
    with KB_PATH.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("cross_id") == cross_id:
                return TextDecompositionCross.from_dict(obj)
    return None
