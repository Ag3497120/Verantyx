import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from avh_math.puzzle.status_types import ReasoningStatus

@dataclass
class MetaCross:
    meta_id: str
    core_pattern: List[str]      # 共通の形状シグネチャ
    preferred_strategy: str      # 推奨される推論戦略
    applicable_domains: Set[str] # 適用可能なドメイン
    confidence: float
    source_crystal_ids: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "meta_id": self.meta_id,
            "core_pattern": self.core_pattern,
            "preferred_strategy": self.preferred_strategy,
            "applicable_domains": list(self.applicable_domains),
            "confidence": self.confidence,
            "source_crystal_ids": self.source_crystal_ids
        }

class MetaManager:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.meta_knowledge: List[MetaCross] = []
        self._load_all()

    def _load_all(self):
        if not self.db_dir_exists(): return
        if not self.db_path.exists(): return
        with self.db_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    meta = MetaCross(
                        meta_id=data["meta_id"],
                        core_pattern=data["core_pattern"],
                        preferred_strategy=data["preferred_strategy"],
                        applicable_domains=set(data["applicable_domains"]),
                        confidence=data["confidence"],
                        source_crystal_ids=data.get("source_crystal_ids", [])
                    )
                    self.meta_knowledge.append(meta)
                except: continue

    def db_dir_exists(self):
        return self.db_path.parent.exists()

    def find_strategy(self, signature: List[str]) -> Optional[Dict[str, Any]]:
        """形状シグネチャから最適な推論戦略を特定する"""
        best_meta = None
        max_score = 0.0

        for meta in self.meta_knowledge:
            # シグネチャの部分一致をチェック
            # (入力シグネチャの中にメタパターンの特徴が含まれているか)
            score = self._calculate_pattern_match(signature, meta.core_pattern)
            if score > max_score and score >= 0.7:
                max_score = score
                best_meta = meta

        if best_meta:
            return {
                "strategy": best_meta.preferred_strategy,
                "confidence": best_meta.confidence * max_score,
                "meta_id": best_meta.meta_id
            }
        return None

    def _calculate_pattern_match(self, sig: List[str], pattern: List[str]) -> float:
        if not pattern: return 0.0
        # 簡易的な部分列マッチング
        pattern_str = ",".join(pattern)
        sig_str = ",".join(sig)
        if pattern_str in sig_str:
            return 1.0
        return 0.0 # 厳密な判定が必要な場合は拡張

    def synthesize_meta(self, crystals: List[Any]):
        """複数の結晶からメタ知識を合成する（定期実行を想定）"""
        # ここでは簡易的に、ドメインと結論が同じものをグループ化してメタ化
        # TODO: より高度なクラスタリングロジックの実装
        pass

    def save_meta(self, meta: MetaCross):
        if os.environ.get("AVH_READONLY_DB", "").strip() == "1":
            return
        self.meta_knowledge.append(meta)
        with self.db_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(meta.to_dict(), ensure_ascii=False) + "\n")
