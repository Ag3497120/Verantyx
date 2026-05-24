import json
import random
import sys
import hashlib
from pathlib import Path

# Usage: python3 tools/append_seed_chunk.py <start_id> <count>

if len(sys.argv) < 3:
    print("Usage: append_seed_chunk.py <start_id> <count>")
    sys.exit(1)

START_ID = int(sys.argv[1])
COUNT = int(sys.argv[2])
OUT_FILE = Path("avh_math/db/text_cross_seed.jsonl")

OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------
# HUGE VOCABULARY
# ----------------------------------------------------------------

NOUNS = [
    "matrix", "vector space", "group", "manifold", "set", "function", "operator",
    "eigenvalue", "trace", "determinant", "kernel", "image", "dimension",
    "frame", "model", "world", "valuation", "tautology", "contradiction",
    "isomorphism", "homomorphism", "automorphism", "bijection",
    "subspace", "ideal", "ring", "field", "lattice", "algebra",
    "sequence", "series", "limit", "derivative", "integral",
    "graph", "tree", "node", "edge", "path", "cycle",
    "行列", "ベクトル空間", "群", "多様体", "集合", "関数", "作用素",
    "固有値", "トレース", "行列式", "核", "像", "次元",
    "フレーム", "モデル", "世界", "評価", "恒真式", "矛盾",
    "同型", "準同型", "自己同型", "全単射",
    "部分空間", "イデアル", "環", "体", "束", "代数",
    "数列", "級数", "極限", "導関数", "積分",
    "グラフ", "木", "ノード", "エッジ", "パス", "閉路"
]

ADJECTIVES = [
    "abelian", "finite", "infinite", "countable", "uncountable",
    "compact", "connected", "hausdorff", "metric", "topological",
    "normal", "unitary", "orthogonal", "symmetric", "hermitian",
    "positive definite", "invertible", "singular",
    "transitive", "reflexive", "euclidean", "hilbert", "banach",
    "linear", "nonlinear", "continuous", "differentiable", "analytic",
    "free", "projective", "injective",
    "可換", "有限", "無限", "可算", "非可算",
    "コンパクト", "連結", "ハウスドルフ", "距離", "位相",
    "正規", "ユニタリ", "直交", "対称", "エルミート",
    "正定値", "可逆", "特異",
    "推移的", "反射的", "ユークリッド", "ヒルベルト", "バナッハ",
    "線形", "非線形", "連続", "微分可能", "解析的",
    "自由", "射影的", "単射的"
]

VERBS_EN = [
    "Verify", "Check", "Prove", "Refute", "Calculate", "Find", "Determine",
    "Show that", "Assume", "Suppose", "Let", "Consider", "Evaluate",
    "Compute", "Derive", "Construct", "Analyze"
]

VERBS_JP = [
    "検証せよ", "確認せよ", "証明せよ", "反証せよ", "計算せよ", "求めよ", "決定せよ",
    "示せ", "仮定する", "とする", "考える", "評価せよ",
    "導出せよ", "構成せよ", "解析せよ"
]

# ----------------------------------------------------------------
# FORMULA GENERATOR (RECURSIVE & RICH)
# ----------------------------------------------------------------

VARS = ["x", "y", "z", "n", "m", "k", "f", "g", "h", "A", "B", "C", "X", "Y", "v", "u", "w"]
GREEK = ["alpha", "beta", "gamma", "delta", "lambda", "sigma", "theta", "omega", "phi", "psi", "epsilon"]
CONSTS = ["0", "1", "pi", "e", "i", r"\infty", r"\emptyset", r"\mathbb{R}", r"\mathbb{C}", r"\mathbb{Z}"]

BIN_OPS = [
    "+", "-", "*", "/", "^", r"\circ", r"\cdot", r"\times", r"\otimes", r"\oplus",
    "=", "!=", "<", ">", r"\leq", r"\geq", r"\equiv", r"\approx", r"\cong",
    r"\in", r"\notin", r"\subset", r"\subseteq", r"\supset", r"\supseteq",
    r"\cup", r"\cap", r"\setminus",
    "->", "<-", r"\implies", r"\iff", r"\land", r"\lor", "&&", "||"
]

UN_OPS = [
    "-", r"\neg", "!", "not ", "~",
    "sin", "cos", "tan", "log", "ln", "exp", "det", "tr", "dim", "rank", "ker", "im",
    "sqrt", r"\sqrt", "sup", "inf", "max", "min",
    "Box", "Diamond", "[]", "<>", "K", "T"
]

QUANTIFIERS = [r"\\forall", r"\\exists", "forall", "exists"]

def gen_formula(depth=0):
    if depth > 4 or (depth > 1 and random.random() < 0.4):
        # Base case: Atom
        type_ = random.choice(["var", "greek", "const", "func_call"])
        if type_ == "var": return random.choice(VARS)
        if type_ == "greek": return "\" + random.choice(GREEK)
        if type_ == "const": return random.choice(CONSTS)
        if type_ == "func_call":
            return f"{random.choice(['f','g','h','P','Q'])}({random.choice(VARS)})"
    
    r = random.random()
    if r < 0.2:
        # Quantifier: forall x. Formula
        q = random.choice(QUANTIFIERS)
        v = random.choice(["x", "y", "z", "n"])
        return f"{q} {v}. ({gen_formula(depth+1)})"
    elif r < 0.5:
        # Unary: op(Formula)
        op = random.choice(UN_OPS)
        return f"{op}({gen_formula(depth+1)})"
    else:
        # Binary: Formula op Formula
        op = random.choice(BIN_OPS)
        return f"({gen_formula(depth+1)} {op} {gen_formula(depth+1)})"

# ----------------------------------------------------------------
# SENTENCE GENERATOR (CONTEXT FREE GRAMMAR STYLE)
# ----------------------------------------------------------------

def gen_sentence():
    f = gen_formula()
    structure = random.choice([
        "CMD_SIMPLE", "CMD_COND", "CONTEXT_DECL", "QUERY_PROP", "JP_CMD", "JP_COND", "JP_QUERY"
    ])
    
    noun = random.choice(NOUNS)
    adj = random.choice(ADJECTIVES)
    verb_en = random.choice(VERBS_EN)
    verb_jp = random.choice(VERBS_JP)
    
    if structure == "CMD_SIMPLE":
        # Check if A = B
        return f"{verb_en} if '{f}' is {adj}."
    
    elif structure == "CMD_COND":
        # If X is abelian, verify Y
        return f"If the {noun} is {adj}, {verb_en.lower()}: '{f}'."
    
    elif structure == "CONTEXT_DECL":
        # Let f(x) be continuous.
        return f"Let {noun} be {adj}. Then '{f}'."
    
    elif structure == "QUERY_PROP":
        # Is the kernel finite?
        return f"Is the {noun} of '{f}' {adj}?"
        
    elif structure == "JP_CMD":
        # Aがコンパクトであることを示せ
        return f"'{f}' が{adj}であることを{verb_jp}。"
        
    elif structure == "JP_COND":
        # Xが有限群ならば、Y
        return f"{noun}が{adj}ならば、'{f}' は成り立つか。"
        
    elif structure == "JP_QUERY":
        # 式Xのランクは？
        return f"式 '{f}' の{noun}は{adj}か？"
        
    # Fallback
    return f