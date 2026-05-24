import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Set
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.puzzle.kb_gate import allow_kb_promotion, calculate_kb_signature

class LearningEngine:
    def __init__(self, kb_path: str, log_path: str):
        self.kb_path = Path(kb_path)
        self.log_path = Path(log_path)
        self.seen_signatures: Set[str] = set()
        self._initialize_seen()

    def _initialize_seen(self):
        """既存の KB から署名を読み込み、重複を回避する準備をする"""
        if not self.kb_path.exists(): return
        with self.kb_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    # 簡易的な署名再生成（またはIDから抽出）
                    sig = calculate_kb_signature(obj)
                    self.seen_signatures.add(sig)
                except: continue

    def process_result(self, cross: ReasoningCross):
        """推論結果をログに記録し、条件を満たせば KB に昇格させる"""
        if os.environ.get("AVH_READONLY_DB", "").strip() == "1":
            return
        # 1. ログの保存
        log_entry = {
            "ts": time.time(),
            "cross_id": getattr(cross, "cross_id", "unknown"),
            "verdict": cross.status.value,
            "formula": cross.core_formula,
            "assumptions": cross.assumptions,
            "confidence": cross.metadata.get("mapping_confidence", 0.5)
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        # 2. KB 昇格の検討
        if cross.status not in (ReasoningStatus.PROVED, ReasoningStatus.DISPROVED):
            return

        candidate = {
            "domain": cross.domain,
            "kind": "theorem" if cross.status == ReasoningStatus.PROVED else "counterexample_schema",
            "statement": cross.verified_formula or cross.core_formula,
            "prerequisites": cross.assumptions,
            "confidence": log_entry["confidence"],
            "yields": [cross.status.value]
        }

        sig = calculate_kb_signature(candidate)
        if sig not in self.seen_signatures and allow_kb_promotion(candidate):
            candidate["id"] = f"auto.{candidate['kind'][:3]}.{sig}"
            with self.kb_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(candidate, ensure_ascii=False) + "\n")
            self.seen_signatures.add(sig)
            cross.metadata["auto_learned"] = True
            cross.metadata["new_kb_id"] = candidate["id"]
