import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

class MappingManager:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.mappings: List[Dict[str, Any]] = []
        self._load_all()

    def _load_all(self):
        if not self.db_path.exists():
            return
        with self.db_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    self.mappings.append(json.loads(line))
                except:
                    continue

    def find_mapping(self, signature: List[str], threshold: float = 0.9) -> Optional[Dict[str, Any]]:
        """シグネチャの完全一致または高類似度一致を探す"""
        best_match = None
        max_score = 0.0

        for m in self.mappings:
            target_sig = m.get("text_signature", [])
            if not target_sig: continue
            
            # 簡易的な位置一致スコア
            common = sum(1 for x, y in zip(signature, target_sig) if x == y)
            score = common / max(len(signature), len(target_sig))
            
            if score > max_score and score >= threshold:
                max_score = score
                best_match = m

        return best_match

    def learn(self, signature: List[str], domain: str, template: Dict[str, Any]):
        """新しいマッピングを学習し、永続化する"""
        # 重複チェック（同じシグネチャなら更新）
        for m in self.mappings:
            if m.get("text_signature") == signature:
                m["reasoning_template"] = template
                m["confidence"] = min(1.0, m.get("confidence", 0.5) + 0.1)
                self._save_all() # 本来はアペンドが望ましいが、小規模なら再書き込み
                return

        entry = {
            "text_signature": signature,
            "domain": domain,
            "reasoning_template": template,
            "confidence": 0.8
        }
        self.mappings.append(entry)
        with self.db_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _save_all(self):
        with self.db_path.open("w", encoding="utf-8") as f:
            for m in self.mappings:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
