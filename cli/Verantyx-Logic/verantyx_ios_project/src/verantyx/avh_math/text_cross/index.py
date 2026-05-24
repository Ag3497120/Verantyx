import json
from pathlib import Path
from typing import Dict, List

from .cross import TextDecompositionCross

INDEX_PATH = Path("avh_math/db/text_cross_index.json")


def _shape_signature(cross: TextDecompositionCross) -> str:
    shapes = [n.content.get("shape", "") for n in cross.nodes.values()]
    uniq = sorted({s for s in shapes if s})
    return "|".join(uniq)


def build_index(crosses: List[TextDecompositionCross]) -> Dict[str, str]:
    return {c.cross_id: _shape_signature(c) for c in crosses}


def save_index(index: Dict[str, str]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def load_index() -> Dict[str, str]:
    if not INDEX_PATH.exists():
        return {}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
