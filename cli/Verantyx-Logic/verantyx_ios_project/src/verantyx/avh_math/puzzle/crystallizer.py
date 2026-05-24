import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus

@dataclass
class CrossFingerprint:
    domain: str
    core_shape: List[str] # 構造シグネチャ (shape_seq)
    assumptions: List[str]
    verdict: str

    def to_tuple(self):
        return (self.domain, tuple(self.core_shape), tuple(sorted(self.assumptions)), self.verdict)

class CrossCrystal:
    def __init__(self, fingerprint: CrossFingerprint):
        self.fingerprint = fingerprint
        self.count = 0
        self.confidence = 0.0
        self.source_ids: List[str] = []

    def add(self, cross: ReasoningCross):
        self.count += 1
        # メンバが増えるほど確信度を上昇させる（漸近的に1.0へ）
        self.confidence = min(1.0, self.confidence + 1.0 / (self.count + 1))
        # 元となったエビデンス（KB IDなど）を追跡
        if "kb_backflow_id" in cross.metadata:
            self.source_ids.append(cross.metadata["kb_backflow_id"])

    def to_dict(self):
        return {
            "fingerprint": {
                "domain": self.fingerprint.domain,
                "core_shape": self.fingerprint.core_shape,
                "assumptions": self.fingerprint.assumptions,
                "verdict": self.fingerprint.verdict
            },
            "count": self.count,
            "confidence": self.confidence,
            "source_ids": list(set(self.source_ids))
        }

class Crystallizer:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.crystals: Dict[tuple, CrossCrystal] = {}
        self._load_all()

    def _load_all(self):
        if not self.db_path.exists(): return
        with self.db_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    fp_data = data["fingerprint"]
                    fp = CrossFingerprint(
                        domain=fp_data["domain"],
                        core_shape=fp_data["core_shape"],
                        assumptions=fp_data["assumptions"],
                        verdict=fp_data["verdict"]
                    )
                    crystal = CrossCrystal(fp)
                    crystal.count = data["count"]
                    crystal.confidence = data["confidence"]
                    crystal.source_ids = data.get("source_ids", [])
                    self.crystals[fp.to_tuple()] = crystal
                except: continue

    def crystallize(self, cross: ReasoningCross, signature: List[str]):
        """推論結果を結晶化プロセスに投入する"""
        if cross.status not in (ReasoningStatus.PROVED, ReasoningStatus.DISPROVED):
            return

        fp = CrossFingerprint(
            domain=cross.domain,
            core_shape=signature,
            assumptions=cross.assumptions,
            verdict=cross.status.value
        )
        
        fp_tuple = fp.to_tuple()
        if fp_tuple not in self.crystals:
            self.crystals[fp_tuple] = CrossCrystal(fp)
        
        self.crystals[fp_tuple].add(cross)
        self._save_all()

    def query_crystal(self, signature: List[str], assumptions: List[str]) -> Optional[Dict[str, Any]]:
        """形状と仮定から、既存の結晶（確定知見）を照会する"""
        # 完全一致する結晶を探す（将来的に類似度検索へ拡張可能）
        for crystal in self.crystals.values():
            if crystal.fingerprint.core_shape == signature and \
               set(crystal.fingerprint.assumptions) == set(assumptions):
                return {
                    "verdict": ReasoningStatus.from_str(crystal.fingerprint.verdict),
                    "confidence": crystal.confidence,
                    "source": "cross_crystal"
                }
        return None

    def _save_all(self):
        with self.db_path.open("w", encoding="utf-8") as f:
            for crystal in self.crystals.values():
                f.write(json.dumps(crystal.to_dict(), ensure_ascii=False) + "\n")
