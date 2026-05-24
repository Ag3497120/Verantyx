import json
import time
from pathlib import Path
from typing import Dict, Any

def autosave_to_kb(kb_path: str, entry: Dict[str, Any]):
    """推論結果を一意のKBエントリとして永続化する"""
    p = Path(kb_path)
    # デフォルト値の補完
    entry.setdefault("id", f"auto.{int(time.time()*1000)}")
    entry.setdefault("domain", "propositional_logic")
    entry.setdefault("kind", "theorem")
    entry.setdefault("links", [])
    entry.setdefault("patterns", [])
    entry.setdefault("prerequisites", [])
    entry.setdefault("yields", [])
    entry.setdefault("refutation", None)

    # 追記保存
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
