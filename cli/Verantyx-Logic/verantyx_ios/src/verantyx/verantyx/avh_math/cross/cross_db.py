import json
import os
from typing import List
from avh_math.cross.cross_core import ReasoningCross

class ReasoningCrossDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.cache: List[ReasoningCross] = []
        self._load_all()

    def _load_all(self):
        if not os.path.exists(self.db_path):
            return
        with open(self.db_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    self.cache.append(ReasoningCross.from_dict(data))
                except:
                    continue

    def add(self, cross: ReasoningCross):
        self.cache.append(cross)
        cross.save_to_jsonl(self.db_path)

    def find_all(self) -> List[ReasoningCross]:
        return self.cache
