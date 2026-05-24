import json
import re
from pathlib import Path
from typing import List, Dict, Optional

def load_question_templates(path: str) -> List[Dict]:
    templates = []
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                templates.append(json.loads(line))
            except:
                continue
    return templates

def infer_task_from_text(text: str, templates: List[Dict]) -> Optional[str]:
    for t in templates:
        if re.search(t["pattern"], text):
            return t["task"]
    return None
