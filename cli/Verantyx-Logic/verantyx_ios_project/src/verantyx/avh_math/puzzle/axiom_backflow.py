import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

def backflow_to_kb(
    kb_path: str,
    formula: str,
    source_ids: List[str],
    domain: str,
    proof_method: str,
    kind: str = "theorem"
) -> str:
    """
    検証に成功した式を、新しい知識として foundation_kb.jsonl に逆流（保存）させる。
    """
    kb_file = Path(kb_path)
    
    # 一意のIDを生成（自動生成であることを明示）
    entry_id = f"auto.{kind[:3]}.{uuid.uuid4().hex[:8]}"
    
    entry = {
        "id": entry_id,
        "domain": domain,
        "kind": kind,
        "title": f"auto_generated_{kind}",
        "statement": formula,
        "prerequisites": source_ids, # 合成の元となった公理ID
        "yields": ["auto_verified"],
        "refutation": None,
        "patterns": [formula],
        "links": source_ids,
        "meta": {
            "generated_by": "axiom_assembler",
            "proof_method": proof_method,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }

    # KB ファイルへ追記
    with kb_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry_id
