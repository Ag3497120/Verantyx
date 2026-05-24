from __future__ import annotations
import json
from pathlib import Path

from avh_math.text_cross.builder import build_text_cross
from avh_math.text_cross.store import store_cross, all_crosses
from avh_math.text_cross.index import build_index, save_index


def _iter_texts_from_kb(kb_path: Path):
    if not kb_path.exists():
        return
    with kb_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            parts = [
                obj.get("title", ""),
                obj.get("statement", ""),
                " ".join(obj.get("patterns") or []),
            ]
            text = " ".join(p for p in parts if p)
            if text:
                yield text


def build_from_kb(kb_path: Path) -> int:
    count = 0
    for text in _iter_texts_from_kb(kb_path):
        cross = build_text_cross(text)
        cross.meta["source"] = "foundation_kb"
        store_cross(cross)
        count += 1
    return count


def main():
    kb_path = Path("avh_math/db/foundation_kb.jsonl")
    if not kb_path.exists():
        print("foundation_kb.jsonl not found.")
        return
    count = build_from_kb(kb_path)
    index = build_index(all_crosses())
    save_index(index)
    print(f"Text cross KB built. items={count} index={len(index)}")


if __name__ == "__main__":
    main()
