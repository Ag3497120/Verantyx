import json
import random
import re
import sys
from pathlib import Path

# Config
COUNT = 2000
OUT_FILE = Path("/Users/motonishikoudai/avh_math/avh_math/db/text_cross_seed.jsonl")

# Ensure directory
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# --- 1. Raw Text Generator ---

JP_PARTS = ["ならば", "とき", "である", "について", "仮定する", "示せ", "次の", "条件", "定義", "集合", "関数", "論理"]
EN_PARTS = ["if", "then", "suppose", "let", "assume", "prove", "check", "verify", "is", "defined", "set", "function"]
SYMBOLS = ["A", "B", "p", "q", "x", "y", "0", "1", "alpha", "beta"]
ARROWS = ["->", "→", "=>", "<->"]
MODALS = ["[]", "□", "<>", "Diamond", "Box"]
BRACKETS = ["(", ")", "[", "]", "{", "}", "\"", "'", "`"]
OTHERS = ["+", "-", "*", "=", "!=", ":", ";", ",", ".", "?", "!", "\\"]

def generate_raw_text():
    # Randomly choose a structure type
    type_ = random.choice(["jp", "en", "mixed", "symbolic", "broken"])
    
    parts = []
    length = random.randint(3, 15)
    
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
            
    # Join with spaces mostly, but sometimes not
    text = ""
    for p in parts:
        if random.random() < 0.7:
            text += " " + p
        else:
            text += p
            
    return text.strip()

# --- 2. Decomposition Logic (Strict Rules) ---

def classify_shape(token):
    if token in ["->", "→"]: return "arrow"
    if token in ["[]", "□"]: return "modal"
    if token in ["(", ")", "[", "]", "{", "}"]:
        return "bracket"
    if re.match(r"^[A-Za-z0-9]+$", token) and len(token) == 1: return "symbol" # Simple heuristic
    if re.match(r"^[A-Za-z]+$", token) and len(token) > 1: return "word"
    # Japanese words detection (simple)
    if any("\u3000" <= c <= "\u303f" or "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9faf" for c in token):
        return "word"
    return "other"

def decompose_text(text):
    # Tokenization: Split by space, but also keep delimiters.
    # Simple regex to split but keep delimiters like ->, [], symbols
    # This is a basic tokenizer approximating the requirement.
    
    # Pre-process to split specific multi-char symbols we care about
    # Note: [] and -> need to be kept together if possible, or re-merged.
    # For this seed generator, we use a simple regex split.
    
    # Split by whitespace first
    raw_tokens = text.split()
    tokens = []
    
    for t in raw_tokens:
        # If it contains -> or [], split around them? 
        # For simplicity in this seed script, we treat whitespace-separated units as base,
        # but pure regex tokenization is better.
        
        # Regex to capture: ->, [], Japanese, Words, Single symbols
        sub_tokens = re.findall(r"->|→|\[\]|□|[a-zA-Z0-9]+|[^\s\w]", t)
        
        # Fallback for japanese or mixed leftovers
        if not sub_tokens:
            sub_tokens = [t]
            
        tokens.extend(sub_tokens)

    shapes = []
    for i, t in enumerate(tokens):
        shapes.append({
            "token": t,
            "shape": classify_shape(t),
            "position": i
        })
        
    # Generate notes
    notes = []
    if any(s["shape"] == "arrow" for s in shapes): notes.append("arrow_detected")
    if any(s["shape"] == "modal" for s in shapes): notes.append("modal_detected")
    if "\"" in text: notes.append("quoted_segment")
    
    # Check mixed language (heuristic)
    has_jp = any(s["shape"] == "word" and any("\u3000" <= c <= "\u303f" or "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9faf" for c in s["token"]) for s in shapes)
    has_en = any(s["shape"] == "word" and re.match(r"^[A-Za-z]+$", s["token"]) for s in shapes)
    if has_jp and has_en: notes.append("mixed_language")
    
    # Check unbalanced brackets
    brackets = [s["token"] for s in shapes if s["shape"] == "bracket"]
    stack = []
    unbalanced = False
    pairs = {")": "(", "]": "[", "}": "{"} 
    for b in brackets:
        if b in ["(", "[", "{"]:
            stack.append(b)
        elif b in pairs:
            if not stack or stack[-1] != pairs[b]:
                unbalanced = True
                break
            stack.pop()
    if stack: unbalanced = True
    if unbalanced: notes.append("unbalanced_bracket")
    
    # Structure Signature
    sig = [s["shape"] for s in shapes]
    
    return {
        "raw_text": text,
        "tokens": tokens,
        "shapes": shapes,
        "structure_signature": sig,
        "notes": notes
    }

def main():
    print(f"Generating {COUNT} decomposition entries...")
    
    with OUT_FILE.open("a", encoding="utf-8") as f:
        for _ in range(COUNT):
            raw = generate_raw_text()
            data = decompose_text(raw)
            # Add id for compatibility if needed, though schema didn't specify it strictly, 
            # text_cross usually needs it or raw_text is key.
            # We follow the schema strictly: raw_text, tokens, shapes, structure_signature, notes
            
            # Note: The prompt schema didn't ask for "id", but JSONL usually implies one record per line.
            # We output the exact schema requested.
            
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
            
    print(f"Done. Appended to {OUT_FILE}")

if __name__ == "__main__":
    main()
