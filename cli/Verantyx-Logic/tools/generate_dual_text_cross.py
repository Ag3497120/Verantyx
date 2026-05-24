import json
import random
import re
from pathlib import Path

# Config
COUNT = 2000
SEED_FILE = Path("avh_math/db/text_cross_seed.jsonl")
KB_FILE = Path("avh_math/db/text_cross_kb.jsonl")

# Ensure directories
SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
KB_FILE.parent.mkdir(parents=True, exist_ok=True)

# --- 1. Raw Text Generator ---

JP_PARTS = ["ならば", "とき", "である", "について", "仮定する", "示せ", "次の", "条件", "定義", "集合", "関数", "論理", "とは"]
EN_PARTS = ["if", "then", "suppose", "let", "assume", "prove", "check", "verify", "is", "defined", "set", "function", "logic"]
SYMBOLS = ["A", "B", "p", "q", "x", "y", "0", "1", "alpha", "beta", "f", "g"]
ARROWS = ["->", "→", "=>", "<->"]
MODALS = ["[]", "□", "<>", "Diamond", "Box"]
BRACKETS = ["(", ")", "[", "]", "{", "}", "\"", "'", "`"]
OTHERS = ["+", "-", "*", "=", "!=", ":", ";", ",", ".", "?", "!", "\\"]

def generate_raw_text():
    type_ = random.choice(["jp", "en", "mixed", "symbolic", "broken", "formula_like"])
    
    parts = []
    length = random.randint(3, 12)
    
    for _ in range(length):
        r = random.random()
        if type_ == "jp" or (type_ == "mixed" and r < 0.4):
            parts.append(random.choice(JP_PARTS))
        elif type_ == "en" or (type_ == "mixed" and r < 0.8):
            parts.append(random.choice(EN_PARTS))
        elif r < 0.9:
            parts.append(random.choice(SYMBOLS))
        else:
            # Inject symbols/arrows/modals
            rr = random.random()
            if rr < 0.3: parts.append(random.choice(ARROWS))
            elif rr < 0.6: parts.append(random.choice(MODALS))
            elif rr < 0.8: parts.append(random.choice(BRACKETS))
            else: parts.append(random.choice(OTHERS))
            
    # Assemble text
    text = ""
    for p in parts:
        # Sometimes add space, sometimes not (to simulate broken/mixed text)
        if text and random.random() < 0.8:
            text += " "
        text += p
            
    return text.strip()

# --- 2. Decomposition Logic (Strict Rules) ---

def classify_shape(token):
    if token in ["->", "→", "=>", "<->"]: return "arrow"
    if token in ["[]", "□", "<>", "Box", "Diamond"]: return "modal"
    if token in ["(", ")", "[", "]", "{", "}", "\"", "'"]: return "bracket"
    # Simple symbol heuristic: single letter/digit alphanumeric
    if re.match(r"^[A-Za-z0-9]$", token): return "symbol"
    # Word heuristic: multi-letter alpha or CJK
    if re.match(r"^[A-Za-z0-9]+$", token) and len(token) > 1: return "word"
    if any("\u3000" <= c <= "\u9faf" for c in token): return "word"
    
    return "other"

def decompose_text(text):
    # Regex based tokenization to preserve symbols
    # Pattern captures:
    # 1. Arrows/Modals (->, [], etc)
    # 2. Words (English or Alphanumeric sequence)
    # 3. Japanese sequences (simplified)
    # 4. Single characters (symbols, brackets, others)
    
    # We prioritize specific multi-char symbols
    pattern = r"(->|=>|<->|\[\]|<>|Box|Diamond|[A-Za-z0-9]+|[\u3000-\u9faf]+|[^\s])"
    tokens = [t for t in re.findall(pattern, text) if t.strip()]
    
    shapes = []
    for i, t in enumerate(tokens):
        shapes.append({
            "token": t,
            "shape": classify_shape(t),
            "position": i
        })
        
    # Notes generation
    notes = []
    shape_types = [s["shape"] for s in shapes]
    
    if "arrow" in shape_types: notes.append("arrow_detected")
    if "modal" in shape_types: notes.append("modal_detected")
    if "\"" in text or "'" in text: notes.append("quoted_segment")
    
    # Mixed language check
    has_jp = any(any("\u3000" <= c <= "\u9faf" for c in t) for t in tokens)
    has_en = any(re.search(r"[a-zA-Z]", t) for t in tokens)
    if has_jp and has_en: notes.append("mixed_language")
    
    # Bracket check
    stack = []
    unbalanced = False
    pairs = {")": "(", "]": "[", "}": "{"} 
    for t in tokens:
        if t in ["(", "[", "{"]:
            stack.append(t)
        elif t in pairs:
            if not stack or stack[-1] != pairs[t]:
                unbalanced = True
                break
            stack.pop()
    if stack: unbalanced = True
    if unbalanced: notes.append("unbalanced_bracket")
    
    # Heuristic for formula-like
    symbol_ratio = shape_types.count("symbol") / len(shape_types) if shape_types else 0
    if symbol_ratio > 0.3 or "arrow" in shape_types:
        notes.append("formula_like_sequence")

    return {
        "raw_text": text,
        "tokens": tokens,
        "shapes": shapes,
        "structure_signature": shape_types,
        "notes": notes
    }

def main():
    print(f"Generating {COUNT} entries...")
    
    # Use 'a' to append
    with SEED_FILE.open("a", encoding="utf-8") as fs, KB_FILE.open("a", encoding="utf-8") as fk:
        for _ in range(COUNT):
            text = generate_raw_text()
            
            # 1. Write Seed (Raw text only)
            seed_record = {"raw_text": text}
            fs.write(json.dumps(seed_record, ensure_ascii=False) + "\n")
            
            # 2. Write KB (Decomposed)
            kb_record = decompose_text(text)
            fk.write(json.dumps(kb_record, ensure_ascii=False) + "\n")
            
    print(f"Done. Appended {COUNT} lines to:")
    print(f"  - {SEED_FILE}")
    print(f"  - {KB_FILE}")

if __name__ == "__main__":
    main()
