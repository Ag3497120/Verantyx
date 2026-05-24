import json
import random
import uuid
import sys
from pathlib import Path

# Goal: 100,000 unique, structurally diverse lines.
COUNT = 100000
OUT_FILE = Path("avh_math/db/text_cross_seed.jsonl")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# --- 1. HUGE VOCABULARY (Polyglot & Cross-Domain) ---

DOMAINS = {
    "logic": {
        "nouns_en": ["tautology", "contradiction", "implication", "premise", "conclusion", "axiom", "theorem", "inference", "validity"],
        "nouns_jp": ["恒真式", "矛盾", "含意", "前提", "結論", "公理", "定理", "推論", "妥当性"],
        "verbs_en": ["implies", "entails", "contradicts", "proves", "refutes", "deduces"],
        "verbs_jp": ["含意する", "矛盾する", "証明する", "反駁する", "導出する"],
        "adjs_en": ["valid", "sound", "complete", "consistent", "decidable", "recursive"],
        "adjs_jp": ["妥当な", "健全な", "完全な", "無矛盾な", "決定可能な", "再帰的な"],
    },
    "set_theory": {
        "nouns_en": ["set", "subset", "union", "intersection", "powerset", "cardinality", "ordinal", "bijection"],
        "nouns_jp": ["集合", "部分集合", "和集合", "共通部分", "べき集合", "濃度", "順序数", "全単射"],
        "verbs_en": ["contains", "includes", "maps", "corresponds"],
        "verbs_jp": ["含む", "包含する", "写像する", "対応する"],
        "adjs_en": ["finite", "infinite", "countable", "empty", "disjoint"],
        "adjs_jp": ["有限の", "無限の", "可算の", "空の", "互いに素な"],
    },
    "analysis": {
        "nouns_en": ["function", "limit", "derivative", "integral", "sequence", "series", "convergence"],
        "nouns_jp": ["関数", "極限", "導関数", "積分", "数列", "級数", "収束"],
        "verbs_en": ["converges", "diverges", "approaches", "oscillates"],
        "verbs_jp": ["収束する", "発散する", "近づく", "振動する"],
        "adjs_en": ["continuous", "differentiable", "bounded", "monotonic"],
        "adjs_jp": ["連続な", "微分可能な", "有界な", "単調な"],
    },
    "algebra": {
        "nouns_en": ["group", "ring", "field", "vector space", "matrix", "eigenvalue", "homomorphism"],
        "nouns_jp": ["群", "環", "体", "ベクトル空間", "行列", "固有値", "準同型"],
        "verbs_en": ["commutes", "generates", "spans", "is isomorphic to"],
        "verbs_jp": ["可換である", "生成する", "張る", "同型である"],
        "adjs_en": ["abelian", "normal", "orthogonal", "linear", "invertible"],
        "adjs_jp": ["可換な", "正規の", "直交の", "線形な", "可逆な"],
    }
}

# --- 2. RECURSIVE FORMULA GENERATOR (Structural Uniqueness) ---

ATOM_TYPES = ["var", "const", "greek", "func"]
VARS = ["x", "y", "z", "n", "k", "f", "g", "A", "B", "X"]
CONSTS = ["0", "1", "e", "pi", "empty"]
GREEKS = ["alpha", "beta", "gamma", "lambda", "sigma", "omega"]

OPS_UNARY = ["not", "-", "sin", "log", "det", "dim", "pow", "sqrt", "Box", "Diamond"]
OPS_BINARY = ["+", "-", "*", "/", "=", "<", ">", "in", "subset", "->", "and", "or", "iff"]
QUANTIFIERS = ["forall", "exists"]

def gen_term(depth=0):
    # Stop recursion
    if depth > 4 or (depth > 1 and random.random() < 0.4):
        t = random.choice(ATOM_TYPES)
        if t == "var": return random.choice(VARS)
        if t == "const": return random.choice(CONSTS)
        if t == "greek": return "\" + random.choice(GREEKS)
        if t == "func": return f"{random.choice(['f','g','h'])}({gen_term(depth+1)})"
    
    # Recursive step
    r = random.random()
    if r < 0.2: # Quantifier
        q = random.choice(QUANTIFIERS)
        v = random.choice(["x", "y", "z"])
        return f"{q} {v} . ({gen_term(depth+1)})"
    elif r < 0.5: # Unary
        op = random.choice(OPS_UNARY)
        return f"{op}({gen_term(depth+1)})"
    else: # Binary
        op = random.choice(OPS_BINARY)
        return f"({gen_term(depth+1)} {op} {gen_term(depth+1)})"

# --- 3. DYNAMIC SENTENCE BUILDER (Grammar Layer) ---

def get_word(domain, category, lang="en"):
    key = f"{category}_{lang}"
    return random.choice(DOMAINS[domain][key])

def gen_sentence():
    # 1. Choose Domain & Language
    domain = random.choice(list(DOMAINS.keys()))
    lang = random.choice(["en", "jp"])
    
    # 2. Choose Sentence Structure
    struct_type = random.choice([
        "QUERY", "CMD", "CONDITIONAL", "DECLARATION", "MATH_ONLY"
    ])
    
    f = gen_term()
    
    if struct_type == "MATH_ONLY":
        return f'"{f}"'
        
    noun = get_word(domain, "nouns", lang)
    adj = get_word(domain, "adjs", lang)
    verb = get_word(domain, "verbs", lang)
    
    if lang == "en":
        if struct_type == "QUERY":
            patterns = [
                f"Is the {noun} of \"{f}\" {adj}?",
                f"Does \"{f}\" {verb}?",
                f"What is the {noun} in \"{f}\"",
            ]
            return random.choice(patterns)
        elif struct_type == "CMD":
            patterns = [
                f"Prove that \"{f}\" is {adj}.",
                f"Find a {noun} such that \"{f}\'.",
                f"Calculate the {noun} of \"{f}\".",
            ]
            return random.choice(patterns)
        elif struct_type == "CONDITIONAL":
            return f"If \"{f}\" is {adj}, then it {verb}."
        elif struct_type == "DECLARATION":
            return f"Let \"{f}\" be a {adj} {noun}."
            
    else: # JP
        if struct_type == "QUERY":
            patterns = [
                f"\"{f}\" の{noun}は{adj}か？",
                f"\"{f}\" は{verb}か。",
                f"\"{f}\" における{noun}を求めよ。",
            ]
            return random.choice(patterns)
        elif struct_type == "CMD":
            patterns = [
                f"\"{f}\" が{adj}であることを示せ。",
                f"\"{f}\" を満たす{noun}を見つけよ。",
                f"\"{f}\" の{noun}を計算せよ。",
            ]
            return random.choice(patterns)
        elif struct_type == "CONDITIONAL":
            return f"もし \"{f}\" が{adj}ならば、それは{verb}。"
        elif struct_type == "DECLARATION":
            return f"\"{f}\" を{adj}{noun}とする。"

    return f'"{f}"' # Fallback

def main():
    # Using UUID to ensure absolute uniqueness of IDs conceptually, 
    # but requirement is seed_XXXXXX.
    # We rely on the huge search space of formula generation for content uniqueness.
    
    print(f"Generating {COUNT} unique lines...")
    
    seen_hashes = set()
    
    count = 0
    attempts = 0
    
    with OUT_FILE.open("w", encoding="utf-8") as f:
        while count < COUNT:
            text = gen_sentence()
            
            # Uniqueness check (simple hash)
            h = hash(text)
            if h in seen_hashes:
                attempts += 1
                continue # Skip duplicate
            
            seen_hashes.add(h)
            
            entry = {
                "id": f"seed_{count+1:06d}",
                "text": text
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
            count += 1
            if count % 10000 == 0:
                print(f"  ... {count} lines generated.")
                
    print(f"Done. Total {count} lines. (Collisions avoided: {attempts})")

if __name__ == "__main__":
    main()