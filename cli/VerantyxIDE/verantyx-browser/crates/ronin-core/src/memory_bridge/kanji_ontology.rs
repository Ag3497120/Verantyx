use serde::{Serialize, Deserialize};
use std::collections::HashMap;

/// Defines the operational effect a single Kanji Label exerts over the spatial physics of memory nodes.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct KanjiOp {
    pub name: String,
    pub gravity_mod: f32,       // Additive modifier to core spatial gravity (e.g., Dense +0.5)
    pub decay_mod: f32,         // Multiplicative modifier to time decay (e.g., Eternal *0.0)
    pub radius_mod: f32,        // Multiplicative modifier to query radius space
    pub is_purge_flag: bool,    // If true, this operator rejects the node from safe processing (e.g. Broken)
}

impl KanjiOp {
    pub fn new(name: &str, gravity: f32, decay: f32, radius: f32, purge: bool) -> Self {
        Self {
            name: name.to_string(),
            gravity_mod: gravity,
            decay_mod: decay,
            radius_mod: radius,
            is_purge_flag: purge,
        }
    }

    /// Retrieve the standard core Kanji ontology (The rigid mathematical spatial axes)
    pub fn standard_ontology() -> HashMap<String, KanjiOp> {
        let mut map = HashMap::new();
        // ① 時間軸 (Time)
        map.insert("新".to_string(), Self::new("新", 0.3, 1.0, 1.0, false));
        map.insert("古".to_string(), Self::new("古", -0.2, 2.0, 1.0, false));
        map.insert("瞬".to_string(), Self::new("瞬", 0.5, 5.0, 0.5, false));
        map.insert("永".to_string(), Self::new("永", 0.0, 0.0, 2.0, false));
        
        // ② 空間軸 (Space)
        map.insert("近".to_string(), Self::new("近", 0.4, 1.0, 0.5, false));
        map.insert("遠".to_string(), Self::new("遠", -0.4, 1.0, 2.0, false));
        map.insert("内".to_string(), Self::new("内", 0.3, 1.0, 0.5, false));
        map.insert("外".to_string(), Self::new("外", -0.3, 1.0, 1.5, false));
        map.insert("深".to_string(), Self::new("深", 0.5, 0.5, 1.0, false));
        map.insert("浅".to_string(), Self::new("浅", -0.2, 1.5, 1.0, false));

        // ③ 抽象度 (Abstraction)
        map.insert("具".to_string(), Self::new("具", 0.5, 1.0, 0.5, false));
        map.insert("抽".to_string(), Self::new("抽", -0.2, 0.8, 1.5, false));
        map.insert("元".to_string(), Self::new("元", 0.2, 0.2, 2.0, false));
        map.insert("細".to_string(), Self::new("細", 0.3, 1.2, 0.3, false));

        // ④ 信頼・確度 (Confidence)
        map.insert("確".to_string(), Self::new("確", 0.4, 0.8, 1.0, false));
        map.insert("疑".to_string(), Self::new("疑", -0.4, 1.5, 1.0, false));
        map.insert("仮".to_string(), Self::new("仮", -0.2, 2.0, 1.0, false));
        map.insert("偽".to_string(), Self::new("偽", -1.0, 5.0, 0.0, true));

        // ⑤ 重要度 (Importance)
        map.insert("重".to_string(), Self::new("重", 0.8, 0.2, 1.5, false));
        map.insert("軽".to_string(), Self::new("軽", -0.5, 2.0, 1.0, false));
        map.insert("核".to_string(), Self::new("核", 1.0, 0.0, 2.0, false));
        map.insert("周".to_string(), Self::new("周", -0.3, 1.5, 1.0, false));

        // ⑥ 関係性 (Relationship)
        map.insert("因".to_string(), Self::new("因", 0.3, 1.0, 1.0, false));
        map.insert("果".to_string(), Self::new("果", 0.2, 1.0, 1.0, false));
        map.insert("連".to_string(), Self::new("連", 0.1, 1.0, 1.5, false));
        map.insert("断".to_string(), Self::new("断", -0.5, 2.0, 0.5, false));

        // ⑦ 状態 (State)
        map.insert("動".to_string(), Self::new("動", 0.2, 1.5, 1.0, false));
        map.insert("静".to_string(), Self::new("静", 0.3, 0.5, 1.0, false));
        map.insert("変".to_string(), Self::new("変", 0.0, 2.0, 1.0, false));
        map.insert("固".to_string(), Self::new("固", 0.5, 0.1, 1.0, false));
        map.insert("創".to_string(), Self::new("創", 0.1, 1.0, 2.5, false));
        map.insert("完".to_string(), Self::new("完", -0.3, 1.5, 1.0, false));
        map.insert("破".to_string(), Self::new("破", -1.0, 5.0, 0.0, true));

        // ⑧ 技巧・手続き (Procedural / Skill)
        map.insert("術".to_string(), Self::new("術", 0.8, 0.2, 2.0, false)); // Skills have high gravity, slow decay, wide radius

        map
    }

    /// The transparent Semantic Alias Dictionary
    /// Maps thousands of natural expressions to the Core Vector axes
    pub fn alias_ontology() -> HashMap<String, Vec<&'static str>> {
        let mut map = HashMap::new();
        
        // Time
        map.insert("昔".to_string(), vec!["古"]);
        map.insert("旧".to_string(), vec!["古"]);
        map.insert("過去".to_string(), vec!["古"]);
        map.insert("老".to_string(), vec!["古", "重"]); // Old but carries weight
        map.insert("今".to_string(), vec!["新"]);
        map.insert("最新".to_string(), vec!["新"]);
        map.insert("未来".to_string(), vec!["新", "抽"]);
        map.insert("一瞬".to_string(), vec!["瞬"]);
        map.insert("永遠".to_string(), vec!["永"]);

        // Importance
        map.insert("重要".to_string(), vec!["重"]);
        map.insert("大事".to_string(), vec!["重", "核"]);
        map.insert("コア".to_string(), vec!["核"]);
        map.insert("本質".to_string(), vec!["核", "深"]);
        map.insert("些末".to_string(), vec!["軽", "周"]);
        map.insert("周辺".to_string(), vec!["周"]);
        
        // State
        map.insert("エラー".to_string(), vec!["破", "疑"]);
        map.insert("バグ".to_string(), vec!["破", "疑"]);
        map.insert("修正".to_string(), vec!["変", "連"]);
        map.insert("完成".to_string(), vec!["完", "固"]);
        map.insert("創造".to_string(), vec!["創", "新"]);

        // Abstraction
        map.insert("メタ".to_string(), vec!["元", "抽"]);
        map.insert("全体".to_string(), vec!["抽", "巨"]);
        map.insert("詳細".to_string(), vec!["具", "細"]);
        map.insert("実装".to_string(), vec!["具", "固"]);

        // Confidence
        map.insert("確実".to_string(), vec!["確"]);
        map.insert("事実".to_string(), vec!["確"]);
        map.insert("推論".to_string(), vec!["仮", "抽"]);
        map.insert("嘘".to_string(), vec!["偽"]);

        map
    }

    /// Calculates Semantic Distance using Kanji Character Jaccard Overlap
    /// It treats each string as a bag of chars. If they share kanji, they have semantic linkage.
    pub fn kanji_distance(a: &str, b: &str) -> f64 {
        use std::collections::HashSet;
        let chars_a: HashSet<char> = a.chars().filter(|c| !c.is_ascii() && !c.is_whitespace()).collect();
        let chars_b: HashSet<char> = b.chars().filter(|c| !c.is_ascii() && !c.is_whitespace()).collect();
        
        if chars_a.is_empty() || chars_b.is_empty() {
            return 0.0;
        }

        let intersection = chars_a.intersection(&chars_b).count() as f64;
        let union = chars_a.union(&chars_b).count() as f64;
        
        intersection / union
    }

    /// Logs an unknown kanji to the dynamic evolution subsystem and clusters it if possible.
    pub fn register_unseen_kanji(word: &str) {
        let mut registry = DynamicAliasRegistry::load();
        if registry.aliases.contains_key(word) || registry.orphans.contains(&word.to_string()) {
            return; // Already processed
        }

        tracing::info!("[Kanji Engine] UNSEEN ALIAS DETECTED - Analyzing vector distance: {}", word);

        let mut best_match = None;
        let mut best_score = 0.0;

        // Compare against Core Ontology
        for (core_name, _) in Self::standard_ontology() {
            let score = Self::kanji_distance(word, &core_name);
            if score > best_score {
                best_score = score;
                best_match = Some(vec![core_name]);
            }
        }

        // Compare against Static Alias Ontology
        for (alias_name, mapped_cores) in Self::alias_ontology() {
            let score = Self::kanji_distance(word, &alias_name);
            if score > best_score {
                best_score = score;
                best_match = Some(mapped_cores.iter().map(|s| s.to_string()).collect());
            }
        }

        if best_score >= 0.5 {
            if let Some(cores) = best_match {
                tracing::info!("[Kanji Engine] Auto-Clustered '{}' -> {:?} (Score: {})", word, cores, best_score);
                registry.aliases.insert(word.to_string(), cores);
                registry.save();
            }
        } else {
            tracing::info!("[Kanji Engine] Queued '{}' as Orphan for LLM Nightwatch Evolution", word);
            registry.orphans.push(word.to_string());
            registry.save();
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Dynamic Alias Registry
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DynamicAliasRegistry {
    pub aliases: HashMap<String, Vec<String>>,
    pub orphans: Vec<String>,
}

impl DynamicAliasRegistry {
    pub fn save_path() -> std::path::PathBuf {
        let root = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
        root.join(".ronin").join("dynamic_aliases.json")
    }

    pub fn load() -> Self {
        if let Ok(data) = std::fs::read_to_string(Self::save_path()) {
            if let Ok(reg) = serde_json::from_str(&data) {
                return reg;
            }
        }
        Self::default()
    }

    pub fn save(&self) {
        if let Some(parent) = Self::save_path().parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        if let Ok(json) = serde_json::to_string_pretty(self) {
            let _ = std::fs::write(Self::save_path(), json);
        }
    }
}

/// A parsed Tag holding its internal value constraint (e.g. `[密:0.8]`)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KanjiTag {
    pub name: String,
    pub weight: f32, // The 0.0 to 1.0 coefficient for continuous operations
}

impl KanjiTag {
    /// Safely parses raw text (e.g., `[昔:0.8]`) and strictly resolves it against the Core Axis.
    /// If an Alias maps to multiple structural Cores, they are all returned inheriting the weight.
    pub fn resolve(raw: &str) -> Vec<Self> {
        let clean = raw.trim_matches(|c| c == '[' || c == ']' || c == ' ' || c == '【' || c == '】');
        if clean.is_empty() {
            return vec![];
        }
        
        let mut parsed_name = clean.to_string();
        let mut weight = 1.0;

        let parts: Vec<&str> = clean.split(':').collect();
        if parts.len() == 2 {
            parsed_name = parts[0].trim().to_string();
            weight = parts[1].parse::<f32>().unwrap_or(1.0);
        }

        let alias_map = KanjiOp::alias_ontology();
        let core_map = KanjiOp::standard_ontology();

        let dynamic_registry = DynamicAliasRegistry::load();

        let mut resolved_tags = Vec::new();

        if let Some(cores) = alias_map.get(&parsed_name) {
            for core in cores {
                resolved_tags.push(Self {
                    name: core.to_string(),
                    weight,
                });
            }
        } else if core_map.contains_key(&parsed_name) {
            // Already a valid core axis
            resolved_tags.push(Self {
                name: parsed_name,
                weight,
            });
        } else if let Some(dynamic_cores) = dynamic_registry.aliases.get(&parsed_name) {
            // Resolved via Auto-Clustering Dynamic Alias registry
            for core in dynamic_cores {
                resolved_tags.push(Self {
                    name: core.to_string(),
                    weight,
                });
            }
        } else {
            // UNSEEN WORD -> Trigger Dynamic Evolution
            KanjiOp::register_unseen_kanji(&parsed_name);
            // We temporarily store it as itself to prevent data loss until the AI catches up
            resolved_tags.push(Self {
                name: parsed_name,
                weight,
            });
        }

        resolved_tags
    }
}

/// Represents the Type and Magnitude of an edge connected to another Memory Node
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypedRelation {
    pub target_id: String,
    pub rel_type: RelationType,
    pub strength: f32, // 0.0 - 1.0 continuously
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum RelationType {
    Derived, // 派生
    Base,    // 基底
    Similar, // 類似
    Opposite,// 対立
    Prev,    // 前項
    Next,    // 次項
    Cause,   // 因果
    Fix,     // 訂正
    Context, // 補足
    Unknown(String),
}

impl RelationType {
    pub fn from_str(val: &str) -> Self {
        match val {
            "派生" | "derived" => RelationType::Derived,
            "基底" | "base" => RelationType::Base,
            "類似" | "similar" => RelationType::Similar,
            "対立" | "opposite" => RelationType::Opposite,
            "前項" | "prev" => RelationType::Prev,
            "次項" | "next" => RelationType::Next,
            "因果" | "cause" => RelationType::Cause,
            "訂正" | "fix" => RelationType::Fix,
            "補足" | "context" => RelationType::Context,
            other => RelationType::Unknown(other.to_string()),
        }
    }
}
