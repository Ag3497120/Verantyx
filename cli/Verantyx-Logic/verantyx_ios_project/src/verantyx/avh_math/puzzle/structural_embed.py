from typing import List, Dict, Any, Optional

def can_embed_fragment(fragment: str, target: str) -> bool:
    """
    断片（fragment）が目標式（target）の中に構文的に含まれているかを判定する。
    """
    def clean(s):
        return s.replace(" ", "").replace("→", "->")

    f_clean = clean(fragment)
    t_clean = clean(target)
    
    return f_clean in t_clean

def find_embedding_axiom(fragment: str, kb_entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    知識ベースの中から、断片を包含する公理や定理を一つ探し出す。
    """
    if not fragment or len(fragment) < 3:
        return None

    for entry in kb_entries:
        statement = entry.get("statement")
        if not statement:
            continue
            
        if can_embed_fragment(fragment, statement):
            return entry
            
    return None
