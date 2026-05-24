from typing import List

from .cross import TextDecompositionCross
from .store import all_crosses, load_cross_by_id
from .similarity import similarity
from .index import load_index


def query_similar(cross: TextDecompositionCross, top_k: int = 3) -> List[TextDecompositionCross]:
    index = load_index()
    if index:
        # Preselect by shape signature overlap.
        target = {n.content.get("shape", "") for n in cross.nodes.values()}
        scored_ids = []
        for cross_id, sig in index.items():
            shapes = set(sig.split("|")) if sig else set()
            if not shapes:
                continue
            score = len(target & shapes) / max(len(target), 1)
            if score > 0:
                scored_ids.append((score, cross_id))
        scored_ids.sort(key=lambda x: x[0], reverse=True)
        out = []
        for _, cid in scored_ids[:top_k * 4]:
            c = load_cross_by_id(cid)
            if c:
                out.append(c)
            if len(out) >= top_k:
                break
        return out

    scored = []
    for c in all_crosses():
        s = similarity(cross, c)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
