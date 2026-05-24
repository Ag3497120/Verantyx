import json
import random
import re
import hashlib
from pathlib import Path

# Config
INCREMENT_COUNT = 2000
SEED_FILE = Path("avh_math/db/text_cross_seed.jsonl")
KB_FILE = Path("avh_math/db/text_cross_kb.jsonl")

# Ensure directories
SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
KB_FILE.parent.mkdir(parents=True, exist_ok=True)

# --- 1. Load All Existing Data (Persistent Mode) ---
existing_texts = set()
existing_sigs = set()

def load_existing_data():
    print("Scanning existing data...")
    count_s = 0
    if SEED_FILE.exists():
        with SEED_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    t = obj.get("raw_text", "").strip()
                    if t: existing_texts.add(t)
                    count_s += 1
                except: pass
                
    count_k = 0
    if KB_FILE.exists():
        with KB_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    sig = tuple(obj.get("structure_signature", []))
                    if sig: existing_sigs.add(sig)
                    count_k += 1
                except: pass
                
    print(f"Loaded {len(existing_texts)} texts and {len(existing_sigs)} structural signatures.")

# --- 2. Advanced Chaos Generator (Incremental Diversity) ---

# Even larger vocabulary to ensure uniqueness
JP_VOCAB = ["仮定", "結論", "ならば", "または", "かつ", "否定", "同値", "推論", "妥当", "健全", "完全", "決定可能", "計算", "集合", "位相", "測度", "積分", "微分", "極限", "収束", "発散", "級数", "群", "環", "体", "加群", "束", "圏", "射", "関手", "自然変換", "随伴", "極小", "極大", "最大", "最小", "上限", "下限", "境界", "閉包", "内部", "外部", "近傍", "連結", "コンパクト", "分離", "正規", "距離", "ノルム", "内積", "直交", "ユニタリ", "エルミート", "固有値", "スペクトル", "トレース", "ランク", "核", "像", "次元", "基底", "生成", "独立", "従属", "凸", "凹", "アフィン", "単体", "多面体", "多様体", "接空間", "曲率", "トーション", "ホモロジー", "ホモトピー", "基本群", "被覆", "ファイバー", "束", "切断", "接続", "ゲージ", "スピン", "スピノル", "テンソル", "ウェッジ", "縮約", "共変", "反変", "計量", "測地線", "変分", "ラグランジアン", "ハミルトニアン", "作用", "保存則", "対称性", "保存", "不変", "共形", "ローレンツ", "ポアンカレ", "ガリレイ", "ユークリッド", "リーマン", "ミンコフスキー", "ケーラー", "シンプレクティック", "超弦", "ブレーン", "双対", "ミラー", "ホログラフィック", "エンタングルメント", "エントロピー", "情報", "通信", "符号", "暗号", "量子", "計算機", "アルゴリズム", "複雑性", "NP", "P", "完全性", "困難性", "還元", "近似", "確率", "統計", "分布", "推定", "検定", "回帰", "相関", "因果", "ベイズ", "マルコフ", "過程", "連鎖", "ランダム", "ウォーク", "ブラウン", "運動", "伊藤", "積分", "確率微分方程式", "ブラック", "ショールズ", "モデル", "金融", "工学", "制御", "最適", "システム", "フィードバック", "ロバスト", "適応", "学習", "ニューラル", "ネット", "深層", "強化学習", "教師あり", "教師なし", "クラスタリング", "次元削減", "主成分", "因子", "分析", "判別", "サポート", "ベクター", "マシン", "カーネル", "法", "スパース", "モデリング", "圧縮", "センシング", "画像", "処理", "音声", "認識", "自然言語", "翻訳", "生成", "対話", "エージェント", "ロボット", "自律", "協調", "マルチ", "群知能", "進化的", "遺伝的", "人工", "生命", "複雑系", "カオス", "フラクタル", "ストレンジ", "アトラクタ", "分岐", "同期", "リズム", "振動", "波", "波動", "ソリトン", "散乱", "回折", "干渉", "回折", "屈折", "反射", "透過", "吸収", "放射", "輻射", "熱", "統計力学", "相転移", "臨界", "現象", "繰り込み", "群", "スケーリング", "普遍性", "クラス", "秩序", "無秩序", "ガラス", "スピン", "液体", "結晶", "準結晶", "アモルファス", "半導体", "超伝導", "超流動", "ボース", "アインシュタイン", "凝縮", "フェルミ", "縮退", "ガス", "プラズマ", "プラズモン", "フォノン", "マグノン", "エキシトン", "ポラリトン", "光子", "電子", "陽子", "中性子", "クォーク", "グルーオン", "ニュートリノ", "ヒッグス", "ボソン", "フェルミオン", "標準", "模型", "統一", "理論", "大統一", "超対称性", "重力", "一般", "相対性", "特殊", "宇宙", "論", "インフレーション", "ビッグバン", "背景", "放射", "ダーク", "マター", "エネルギー", "ブラックホール", "事象", "地平面", "特異点", "蒸発", "ホーキング", "温度", "面積", "則", "情報", "パラドックス", "紐", "理論", "M", "理論", "行列", "模型", "非可換", "幾何", "数論", "素数", "ゼータ", "関数", "リーマン", "予想", "フェルマー", "最終", "定理", "ABC", "予想", "楕円", "曲線", "モジュラー", "形式", "保型", "形式", "ラングランズ", "プログラム", "類体論", "岩澤", "理論", "代数", "幾何", "スキーム", "スタック", "層", "コホモロジー", "エタール", "クリスタリン", "モチーフ", "周期", "ガロア", "表現", "絶対", "群", "不分岐", "拡大", "分解", "法則", "相互", "律", "類数", "単数", "イデアル", "アデール", "イデール", "大域", "局所", "体", "関数体", "数体", "p進数", "完備", "化", "付値", "順序", "位相", "ハウスドルフ", "コンパクト", "連結", "完全", "不連結", "カントール", "集合", "濃度", "連続体", "仮説", "公理", "系", "ZFC", "選択", "公理", "整列", "可能", "定理", "ツォルン", "補題", "ハメル", "基底", "超フィルタ", "非標準", "解析", "モデル", "理論", "強制", "法", "巨大", "基数", "無矛盾", "性", "証明", "論", "不完全性", "定理", "ゲーデル", "チューリング", "計算", "可能性", "帰納的", "関数", "ラムダ", "計算", "コンビネータ", "論理", "型", "システム", "カリー", "ハワード", "同型", "対応", "直観主義", "論理", "様相", "論理", "線形", "論理", "量子", "論理", "多値", "論理", "ファジィ", "論理", "非単調", "論理", "デフォルト", "推論", "アブダクション", "帰納", "演繹", "類推", "アナロジー", "メタファー", "概念", "学習", "知識", "表現", "オントロジー", "セマンティック", "ウェブ", "リンク", "データ", "グラフ", "ネットワーク", "社会", "分析", "中心", "性", "コミュニティ", "抽出", "スモール", "ワールド", "スケール", "フリー", "べき乗", "則", "ロング", "テール", "パレート", "法則", "ジップ", "法則"] # Expanded a bit
EN_VOCAB = ["axiom", "theorem", "lemma", "proof", "definition", "proposition", "corollary", "conjecture", "hypothesis", "analysis", "algebra", "geometry", "topology", "logic", "set", "category", "number", "function", "map", "operator", "space", "vector", "matrix", "tensor", "group", "ring", "field", "module", "lattice", "bundle", "manifold", "variety", "scheme", "stack", "sheaf", "cohomology", "homology", "homotopy", "curvature", "metric", "connection", "gauge", "field", "particle", "wave", "string", "brane", "duality", "mirror", "symmetry", "conservation", "energy", "momentum", "angular", "spin", "charge", "mass", "force", "interaction", "gravity", "electromagnetism", "weak", "strong", "standard", "model", "unified", "theory", "relativity", "quantum", "mechanics", "field", "theory", "statistical", "thermodynamics", "entropy", "information", "complexity", "computation", "algorithm", "data", "structure", "network", "graph", "tree", "automata", "language", "grammar", "machine", "learning", "neural", "network", "deep", "reinforcement", "supervised", "unsupervised", "cluster", "classification", "regression", "prediction", "inference", "deduction", "induction", "abduction", "reasoning", "knowledge", "representation", "ontology", "semantics", "syntax", "pragmatics", "discourse", "dialogue", "text", "speech", "image", "vision", "robotics", "control", "optimization", "game", "theory", "economics", "finance", "biology", "genetics", "evolution", "ecology", "environment", "climate", "earth", "science", "astronomy", "cosmology", "universe", "galaxy", "star", "planet", "life", "mind", "brain", "consciousness", "cognition", "perception", "emotion", "feeling", "thought", "memory", "learning", "action", "behavior", "society", "culture", "history", "politics", "law", "ethics", "philosophy", "art", "music", "literature"]
SYMBOLS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi", "Psi", "Omega", "aleph", "beth", "gimel", "daleth", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "infty", "empty", "nabla", "partial", "sum", "prod", "int", "oint", "lim", "sup", "inf", "max", "min", "sin", "cos", "tan", "log", "ln", "exp", "det", "tr", "dim", "ker", "im", "rank", "hom", "end", "aut", "iso", "obj", "mor", "id"]
ARROWS = ["->", "<-", "=>", "<= ", "<-", "<=>", "-->", "<--", "==>", "<==", "<==>", "|->", "|=>", "~>", "⇝", "↝", "maps", "to", "implies", "iff"]
MODALS = ["[]", "Box", "Diamond", "<>", "[a]", "<a>", "[i]", "<i>", "K", "B", "D", "knows", "believes", "says", "obligatory", "permitted"]
BRACKETS = ["(", ")", "[", "]", "{", "}", "<", ">", "|", "||", "\"", "'", "「", "」", "『", "』", "【", "】", "〔", "〕"]
OPS = ["+", "-", "*", "/", "^", "_", "=", "!=", "<", ">", "<=", ">=", "~", "approx", "equiv", "cong", "in", "notin", "subset", "supset", "subseteq", "supseteq", "cup", "cap", "setminus", "oplus", "otimes", "times", "circ", "bullet", "cdot", "and", "or", "not", "xor", "nand", "nor", "forall", "exists", "exists!", "top", "bot", "vdash", "models"]

def generate_chaotic_text():
    # Length: 2 to 20 tokens
    length = random.randint(2, 20)
    parts = []
    
    # Modes to ensure structural variety
    # 0: Mathematical formula (heavy symbol)
    # 1: Japanese explanation (heavy word)
    # 2: English explanation (heavy word)
    # 3: Logic symbolic (arrow/modal heavy)
    # 4: Broken/Mixed chaos
    mode = random.choices([0, 1, 2, 3, 4], weights=[0.3, 0.2, 0.2, 0.2, 0.1])[0]
    
    for _ in range(length):
        r = random.random()
        
        if mode == 0: # Formula
            if r < 0.6: parts.append(random.choice(SYMBOLS))
            elif r < 0.8: parts.append(random.choice(OPS))
            elif r < 0.9: parts.append(random.choice(BRACKETS))
            else: parts.append(random.choice(ARROWS))
            
        elif mode == 1: # JP
            if r < 0.6: parts.append(random.choice(JP_VOCAB))
            elif r < 0.8: parts.append(random.choice(SYMBOLS))
            elif r < 0.9: parts.append(random.choice(OPS)) # Use math op in text
            else: parts.append(random.choice(["は", "が", "の", "を", "に", "へ", "より", "から", "で"]))
            
        elif mode == 2: # EN
            if r < 0.6: parts.append(random.choice(EN_VOCAB))
            elif r < 0.8: parts.append(random.choice(SYMBOLS))
            elif r < 0.9: parts.append(random.choice(OPS))
            else: parts.append(random.choice(["is", "of", "to", "from", "by", "in", "on", "at", "with"]))
            
        elif mode == 3: # Logic
            if r < 0.4: parts.append(random.choice(ARROWS))
            elif r < 0.6: parts.append(random.choice(MODALS))
            elif r < 0.8: parts.append(random.choice(SYMBOLS))
            else: parts.append(random.choice(BRACKETS))
            
        else: # Chaos
            pool = JP_VOCAB + EN_VOCAB + SYMBOLS + ARROWS + MODALS + BRACKETS + OPS
            parts.append(random.choice(pool))
            
    # Assemble
    text = ""
    for p in parts:
        if text and random.random() < 0.8:
            text += " "
        text += p
        
    return text.strip()

# --- 3. Strict Decomposition (Consistent Rules) ---

def classify_shape(token):
    # Fixed Shape Rules
    if token in ARROWS: return "arrow"
    if token in MODALS: return "modal"
    if token in BRACKETS: return "bracket"
    
    # Symbol vs Word vs Other
    # Heuristic: Alphanumeric single char or specific math/greek -> symbol
    # Multi-char alpha -> word
    # CJK -> word
    # Others (operators) -> other
    
    if token in SYMBOLS: return "symbol" # Explicit list match preferred
    if token in OPS: return "other"
    
    if re.match(r"^[A-Za-z0-9]$", token): return "symbol"
    if re.match(r"^[A-Za-z0-9_]+$", token): return "word" # long identifiers usually words
    if any("\u3000" <= c <= "\u9faf" for c in token): return "word"
    
    return "other"

def decompose_text(text):
    # Improved Tokenizer to handle all the vocabulary
    # 1. Protect specific multi-char tokens (arrows, modals, ops) by regex alternation
    
    # Construct massive regex from lists (escaped)
    all_specials = ARROWS + MODALS + OPS + SYMBOLS # Symbols included to catch 'alpha' etc
    # Filter out single chars from specials to let general regex handle them, or keep?
    # Keep multi-char ones first.
    
    multi_char = sorted([x for x in all_specials if len(x) > 1], key=len, reverse=True)
    multi_char_pattern = "|".join(map(re.escape, multi_char))
    
    # Pattern: 
    # 1. Multi-char special
    # 2. CJK word
    # 3. English word
    # 4. Single char (bracket, single symbol, etc)
    
    pattern = f"({multi_char_pattern}|[\\u3000-\\u9faf]+|[A-Za-z0-9_]+|[^\\s])"
    
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
    
    if "arrow" in shape_types: notes.append("arrow_detected")
    # Broken arrow check (e.g., "-" and ">" separated? Hard to detect if already tokenized as arrow)
    # We leave broken_arrow for when tokenizer fails or raw text has " - > "
    if "-" in tokens and ">" in tokens: # Heuristic
        notes.append("broken_arrow")
        
    if "modal" in shape_types: notes.append("modal_detected")
    if "\"" in text or "'" in text: notes.append("quoted_segment")
    
    has_jp = any(any("\u3000" <= c <= "\u9faf" for c in t) for t in tokens)
    has_en = any(re.search(r"[a-zA-Z]", t) for t in tokens)
    if has_jp and has_en: notes.append("mixed_language")
    
    # Bracket check
    stack = []
    unbalanced = False
    pairs = {")": "(", "]": "[", "}": "{", ">": "<", "」": "「", "』": "『", "】": "【", "〕": "〔"}
    for t in tokens:
        if t in pairs.values():
            stack.append(t)
        elif t in pairs:
            if not stack or stack[-1] != pairs[t]:
                unbalanced = True
                break
            stack.pop()
    if stack: unbalanced = True
    if unbalanced: notes.append("unbalanced_bracket")
    
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
    load_existing_data()
    print(f"Starting Incremental Generation of {INCREMENT_COUNT} items...")
    
    buffer_seed = []
    buffer_kb = []
    
    generated = 0
    attempts = 0
    
    while generated < INCREMENT_COUNT:
        attempts += 1
        text = generate_chaotic_text()
        
        # 1. Raw Text Uniqueness
        if text in existing_texts:
            continue
            
        kb_data = decompose_text(text)
        sig = tuple(kb_data["structure_signature"])
        
        # 2. Structural Uniqueness (The core requirement)
        if sig in existing_sigs:
            continue
            
        # Unique found!
        existing_texts.add(text)
        existing_sigs.add(sig)
        
        buffer_seed.append({"raw_text": text})
        buffer_kb.append(kb_data)
        
        generated += 1
        if generated % 500 == 0:
            print(f"  Generated {generated}/{INCREMENT_COUNT} (Attempts: {attempts})")
            
    print("Writing to disk...")
    with SEED_FILE.open("a", encoding="utf-8") as fs:
        for item in buffer_seed:
            fs.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    with KB_FILE.open("a", encoding="utf-8") as fk:
        for item in buffer_kb:
            fk.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    print(f"Completed. Added {generated} items.")

if __name__ == "__main__":
    main()