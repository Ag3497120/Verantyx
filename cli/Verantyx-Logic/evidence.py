from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str


def find_spans(text: str, needles: List[str]) -> List[Span]:
    """
    超軽量: needles の出現を拾う（単純なfind）
    """
    spans: List[Span] = []
    lower_text = text.lower()
    for needle in needles:
        if not needle: continue
        needle_lower = needle.lower()
        idx = lower_text.find(needle_lower)
        # Find all occurrences? The prompt says "first occurrences" is fine for lightweight.
        # But let's try to find all for better highlighting.
        while idx >= 0:
            spans.append(Span(start=idx, end=idx + len(needle), text=text[idx:idx+len(needle)]))
            idx = lower_text.find(needle_lower, idx + 1)
    return spans


def merge_evidence_map(
    base: Dict[str, List[Span]],
    add: Dict[str, List[Span]],
) -> Dict[str, List[Span]]:
    out = {k: list(v) for k, v in base.items()}
    for k, spans in add.items():
        out.setdefault(k, [])
        out[k].extend(spans)
        # 重複除去（同一 start/end）
        seen = set()
        uniq = []
        # Sort by start then end
        for s in sorted(out[k], key=lambda x: (x.start, x.end)):
            key = (s.start, s.end)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(s)
        out[k] = uniq
    return out