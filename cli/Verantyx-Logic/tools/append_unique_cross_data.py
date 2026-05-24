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

# --- 1. Load Existing Data (for Uniqueness Check) ---
existing_texts = set()
existing_sigs = set()

def load_existing():
    if SEED_FILE.exists():
        with SEED_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    existing_texts.add(obj.get("raw_text", ""))
                except: pass
    
    if KB_FILE.exists():
        with KB_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    sig = tuple(obj.get("structure_signature", []))
                    existing_sigs.add(sig)
                except: pass
    
    print(f"Loaded {len(existing_texts)} existing texts and {len(existing_sigs)} signatures.")

# --- 2. Advanced Generator (Focus on Novelty) ---

# Expanded Vocabulary
JP_PARTS_2 = ["かつ", "または", "すべての", "存在する", "写像", "空間", "演算", "同型", "正規", "可換", "一意", "満たす", "要素"]
EN_PARTS_2 = ["forall", "exists", "map", "space", "op", "iso", "normal", "commute", "unique", "s.t.", "element", "implies", "iff"]
SYMBOLS_2 = ["X", "Y", "Z", "r1", "r2", "theta", "phi", "sum", "prod", "lim", "int", "del", "nabla"]
ARROWS_2 = ["=>", "<=", "<=>", "-->", "<--"]
MODALS_2 = ["Box", "Diamond", "[a]", "<a>", "K", "T", "S4"]
BRACKETS_2 = ["{", "}", "<", ">", "|", "||"]
OTHERS_2 = ["#", "$", "%", "&", "@", "^", "_", "`", "~", ";;", "::"]

def generate_novel_text():
    # Strategy: Vary length drastically, mix types aggressively
    length = random.choice([2, 3, 4, 15, 20, 25]) # Very short or very long
    
    parts = []
    
    # Mode selection for structural diversity
    mode = random.choice(["dense_symbol", "verbose_text", "bracket_mess", "arrow_chain", "mixed_chaos"])
    
    for _ in range(length):
        if mode == "dense_symbol":
            parts.append(random.choice(SYMBOLS_2 + ARROWS_2 + MODALS_2 + OTHERS_2))
        elif mode == "verbose_text":
            parts.append(random.choice(JP_PARTS_2 + EN_PARTS_2))
        elif mode == "bracket_mess":
            parts.append(random.choice(BRACKETS_2 + SYMBOLS_2))
        elif mode == "arrow_chain":
            parts.append(random.choice(ARROWS_2 + SYMBOLS_2))
        else: # mixed_chaos
            parts.append(random.choice(JP_PARTS_2 + EN_PARTS_2 + SYMBOLS_2 + ARROWS_2 + MODALS_2 + BRACKETS_2 + OTHERS_2))
            
    # Assemble
    text = ""
    for p in parts:
        if random.random() < 0.5: # 50% chance of no space to create weird tokens
            text += p
        else:
            text += " " + p
            
    return text.strip()

# --- 3. Decomposition Logic (Consistent with previous) ---

def classify_shape(token):
    if token in ["->", "→", "=>", "<-", "<=", "<=>", "-->", "<--"]:
        return "arrow"
    if token in ["[]", "□", "<>", "Diamond", "Box", "[a]", "<a>"]:
        return "modal"
    if token in ["(", ")", "[", "]", "{", "}", "\"", "'", "<", ">", "|", "||"]:
        return "bracket"
    
    # Symbol vs Word vs Other
    if re.match(r"^[A-Za-z0-9]$", token):
        return "symbol"
    if re.match(r"^[A-Za-z0-9_]+", token) and len(token) > 1:
        return "word"
    if any("\u3000" <= c <= "\u9faf" for c in token):
        return "word"
    
    return "other"

def decompose_text(text):
    # Regex to capture all new symbols
    # Prioritize multi-char tokens
    pattern = r"(->|=>|<->|\[\]|<>|Box|Diamond|-->|<--|\[a\]|<a>|[A-Za-z0-9_]+|[\u3000-\u9faf]+|[^\s])"
    tokens = [t for t in re.findall(pattern, text) if t.strip()]
    
    shapes = []
    for i, t in enumerate(tokens):
        shapes.append({
            "token": t,
            "shape": classify_shape(t),
            "position": i
        })
        
    # Notes
    notes = []
    shape_types = [s["shape"] for s in shapes]
    
    if "arrow" in shape_types:
        notes.append("arrow_detected")
    if "modal" in shape_types:
        notes.append("modal_detected")
    if "\"" in text or "'" in text:
        notes.append("quoted_segment")
    
    has_jp = any(any("\u3000" <= c <= "\u9faf" for c in t) for t in tokens)
    has_en = any(re.search(r"[a-zA-Z]", t) for t in tokens)
    if has_jp and has_en:
        notes.append("mixed_language")
    
    # Bracket check (extended)
    stack = []
    unbalanced = False
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}
    for t in tokens:
        if t in pairs.values():
            stack.append(t)
        elif t in pairs:
            if not stack or stack[-1] != pairs[t]:
                unbalanced = True
                break
            stack.pop()
    if stack:
        unbalanced = True
    if unbalanced:
        notes.append("unbalanced_bracket")
    
    # Formula-like check
    symbol_ratio = shape_types.count("symbol") / len(shape_types) if shape_types else 0
    if symbol_ratio > 0.3 or "arrow" in shape_types or "modal" in shape_types:
        notes.append("formula_like_sequence")

    return {
        "raw_text": text,
        "tokens": tokens,
        "shapes": shapes,
        "structure_signature": shape_types,
        "notes": notes
    }

def main():
    load_existing()
    print(f"Generating {COUNT} NEW unique entries...")
    
    generated_count = 0
    attempts = 0
    
    buffer_seed = []
    buffer_kb = []
    
    while generated_count < COUNT:
        attempts += 1
        text = generate_novel_text()
        
        # Text uniqueness check
        if text in existing_texts:
            continue
            
        # Decompose
        kb_data = decompose_text(text)
        sig = tuple(kb_data["structure_signature"])
        
        # Structure uniqueness check (Strict)
        # If this exact structure exists, we skip it to force diversity
        if sig in existing_sigs:
            continue
            
        # It's unique! Add to sets
        existing_texts.add(text)
        existing_sigs.add(sig)
        
        buffer_seed.append({"raw_text": text})
        buffer_kb.append(kb_data)
        
        generated_count += 1
        
        if generated_count % 500 == 0:
            print(f"Generated {generated_count} items (Attempts: {attempts})")
            
    print(f"Writing to files...")
    
    with SEED_FILE.open("a", encoding="utf-8") as fs:
        for item in buffer_seed:
            fs.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    with KB_FILE.open("a", encoding="utf-8") as fk:
        for item in buffer_kb:
            fk.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    print("Done.")

if __name__ == "__main__":
    main()
