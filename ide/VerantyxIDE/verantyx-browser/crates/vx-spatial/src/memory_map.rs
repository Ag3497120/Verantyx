//! Spatial Memory Map Engine — AI Cognitive World Model
//!
//! Provides the Verantyx AI agent with a persistent, multi-scale
//! spatial understanding of web environments it has visited:
//!
//!   - Page topology graph (links between visited pages)
//!   - Element memory (which UI elements persist across pages)
//!   - Interaction history (what the AI did and what happened)
//!   - Cognitive landmark registry (memorable structural features)
//!   - Goal-progress tracking (what the current task requires)
//!   - Entity extraction and tracking (users, products, forms)

use std::collections::{HashMap, HashSet, VecDeque};
use std::time::{Duration, Instant};
use serde::{Serialize, Deserialize};

/// A visited web page in the spatial memory graph
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryPage {
    pub url: String,
    pub title: String,
    pub domain: String,
    pub first_visited: u64,      // Unix timestamp
    pub last_visited: u64,
    pub visit_count: u32,
    pub page_type: PageType,
    pub notable_elements: Vec<MemoryElement>,
    pub outgoing_links: Vec<String>,
    pub form_fields: Vec<FormFieldMemory>,
    pub page_summary: Option<String>,   // AI-generated 1-sentence summary
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PageType {
    LandingPage,
    LoginPage,
    Dashboard,
    ListingPage,        // List of items (search results, product catalog)
    DetailPage,         // Single item detail view
    FormPage,
    ErrorPage,
    CheckoutPage,
    SettingsPage,
    DocumentPage,
    Unknown,
}

impl PageType {
    pub fn infer_from_url(url: &str, title: &str) -> Self {
        let url_lower = url.to_lowercase();
        let title_lower = title.to_lowercase();
        
        if url_lower.contains("login") || url_lower.contains("signin") 
        || title_lower.contains("login") || title_lower.contains("sign in") {
            return Self::LoginPage;
        }
        if url_lower.contains("checkout") || url_lower.contains("payment") {
            return Self::CheckoutPage;
        }
        if url_lower.contains("settings") || url_lower.contains("preferences") {
            return Self::SettingsPage;
        }
        if url_lower.contains("dashboard") || url_lower.contains("home") {
            return Self::Dashboard;
        }
        if url_lower.contains("search") || url_lower.contains("results") {
            return Self::ListingPage;
        }
        if url_lower.contains("error") || url_lower.contains("404") || url_lower.contains("403") {
            return Self::ErrorPage;
        }
        Self::Unknown
    }
    
    pub fn ai_description(&self) -> &'static str {
        match self {
            Self::LandingPage => "landing/marketing page",
            Self::LoginPage => "login or authentication page",
            Self::Dashboard => "user dashboard or home screen",
            Self::ListingPage => "list of items (search results or catalog)",
            Self::DetailPage => "individual item detail view",
            Self::FormPage => "data entry form",
            Self::ErrorPage => "error page (4xx/5xx)",
            Self::CheckoutPage => "checkout or payment page",
            Self::SettingsPage => "settings or preferences page",
            Self::DocumentPage => "documentation or article",
            Self::Unknown => "unknown page type",
        }
    }
}

/// A memorable UI element that the AI has observed or interacted with
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryElement {
    pub element_id: String,       // CSS selector or AI-assigned ID
    pub role: String,             // ARIA role
    pub text: String,             // Visible text
    pub tag: String,
    pub last_seen_bounds: [f64; 4], // [x, y, width, height]
    pub interaction_count: u32,
    pub last_interaction: Option<InteractionRecord>,
    pub is_persistent: bool,      // Present across multiple page loads
}

/// A historical interaction with a UI element
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InteractionRecord {
    pub action: InteractionAction,
    pub value: Option<String>,    // Text typed, option selected, etc.
    pub timestamp: u64,
    pub outcome: InteractionOutcome,
    pub navigation_triggered: Option<String>, // URL if navigation happened
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum InteractionAction {
    Click,
    Type,
    Select,
    Scroll,
    Hover,
    Focus,
    Submit,
    Drag,
    KeyPress,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum InteractionOutcome {
    Success,
    NavigatedTo(String),
    ModalOpened,
    ErrorShown(String),
    NoChange,
    Unknown,
}

/// A memory of a form encountered on a page
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FormFieldMemory {
    pub name: String,
    pub input_type: String,       // text, password, email, select, etc.
    pub label: Option<String>,
    pub placeholder: Option<String>,
    pub last_filled_value: Option<String>,
    pub is_required: bool,
    pub validation_pattern: Option<String>,
}

/// An entity extracted from pages (user, product, order, etc.)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedEntity {
    pub entity_type: EntityType,
    pub properties: HashMap<String, String>,
    pub source_url: String,
    pub confidence: f32,  // 0.0 to 1.0
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum EntityType {
    User,
    Product,
    Order,
    Article,
    Event,
    Organization,
    Navigation,
    Alert,
    Price,
    Date,
    Contact,
    Unknown(String),
}

/// A cognitive landmark — a highly memorable structural feature of a page
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CognitiveLandmark {
    pub landmark_id: String,
    pub description: String,       // Natural language description
    pub page_url: String,
    pub element_selector: String,
    pub importance: LandmarkImportance,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum LandmarkImportance {
    Low = 0,
    Medium = 1,
    High = 2,
    Critical = 3,
}

/// Goal state tracking for the AI's current task
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GoalState {
    pub goal_description: String,
    pub sub_goals: Vec<SubGoal>,
    pub completed_steps: Vec<String>,
    pub failed_attempts: Vec<FailedAttempt>,
    pub started_at: u64,
    pub deadline_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubGoal {
    pub description: String,
    pub status: SubGoalStatus,
    pub completion_url: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SubGoalStatus {
    Pending,
    InProgress,
    Completed,
    Failed,
    Blocked,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FailedAttempt {
    pub description: String,
    pub error: String,
    pub url: String,
    pub timestamp: u64,
    pub retry_count: u32,
}

/// The master Spatial Memory Map
pub struct SpatialMemoryMap {
    /// All pages ever visited in this session: url -> page
    pub pages: HashMap<String, MemoryPage>,
    
    /// Navigation graph edges: (from_url, to_url) -> how many times
    pub nav_graph: HashMap<(String, String), u32>,
    
    /// Session interaction log (bounded ring buffer)
    pub interaction_log: VecDeque<(String, InteractionRecord)>, // (url, record)
    
    /// Current page stack (browser navigation stack)
    pub navigation_stack: Vec<String>,
    
    /// All extracted entities across the session
    pub entities: Vec<ExtractedEntity>,
    
    /// Named landmarks
    pub landmarks: Vec<CognitiveLandmark>,
    
    /// Current high-level goal
    pub current_goal: Option<GoalState>,
    
    /// Known login credentials (in-session only, never persisted)
    pub session_credentials: HashMap<String, (String, String)>, // domain -> (user, pass)
    
    /// Frequently visited URLs (with visit count)
    pub visit_counts: HashMap<String, u32>,
    
    /// Known CSRF tokens and session cookies
    pub session_tokens: HashMap<String, String>,
    
    /// Maximum interaction log entries to keep
    max_log_entries: usize,
}

impl SpatialMemoryMap {
    pub fn new() -> Self {
        Self {
            pages: HashMap::new(),
            nav_graph: HashMap::new(),
            interaction_log: VecDeque::new(),
            navigation_stack: Vec::new(),
            entities: Vec::new(),
            landmarks: Vec::new(),
            current_goal: None,
            session_credentials: HashMap::new(),
            visit_counts: HashMap::new(),
            session_tokens: HashMap::new(),
            max_log_entries: 1000,
        }
    }
    
    /// Record a page visit
    pub fn record_visit(&mut self, url: &str, title: &str) {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        
        // Record navigation edge
        if let Some(prev_url) = self.navigation_stack.last() {
            let edge = (prev_url.clone(), url.to_string());
            *self.nav_graph.entry(edge).or_insert(0) += 1;
        }
        
        self.navigation_stack.push(url.to_string());
        *self.visit_counts.entry(url.to_string()).or_insert(0) += 1;
        
        let domain = Self::extract_domain(url);
        let page_type = PageType::infer_from_url(url, title);
        
        let page = self.pages.entry(url.to_string()).or_insert_with(|| MemoryPage {
            url: url.to_string(),
            title: title.to_string(),
            domain,
            first_visited: now,
            last_visited: now,
            visit_count: 0,
            page_type,
            notable_elements: Vec::new(),
            outgoing_links: Vec::new(),
            form_fields: Vec::new(),
            page_summary: None,
        });
        
        page.last_visited = now;
        page.visit_count += 1;
        page.title = title.to_string();
    }
    
    /// Record an AI interaction with an element
    pub fn record_interaction(
        &mut self,
        url: &str,
        element_id: &str,
        record: InteractionRecord
    ) {
        // Add to interaction log (with bounded buffer)
        if self.interaction_log.len() >= self.max_log_entries {
            self.interaction_log.pop_front();
        }
        self.interaction_log.push_back((url.to_string(), record.clone()));
        
        // Update page element memory
        if let Some(page) = self.pages.get_mut(url) {
            if let Some(el) = page.notable_elements.iter_mut().find(|e| e.element_id == element_id) {
                el.interaction_count += 1;
                el.last_interaction = Some(record);
            }
        }
    }
    
    /// Store an extracted entity from a page
    pub fn store_entity(&mut self, entity: ExtractedEntity) {
        // Deduplicate by type and properties
        let existing = self.entities.iter_mut().find(|e| {
            e.entity_type == entity.entity_type
            && e.source_url == entity.source_url
        });
        
        match existing {
            Some(e) => {
                // Merge properties, update confidence
                for (k, v) in &entity.properties {
                    e.properties.insert(k.clone(), v.clone());
                }
                e.confidence = e.confidence.max(entity.confidence);
            }
            None => self.entities.push(entity),
        }
    }
    
    /// Register a cognitive landmark
    pub fn add_landmark(&mut self, landmark: CognitiveLandmark) {
        // Replace if same ID exists
        if let Some(existing) = self.landmarks.iter_mut().find(|l| l.landmark_id == landmark.landmark_id) {
            *existing = landmark;
        } else {
            self.landmarks.push(landmark);
        }
    }
    
    /// Set the current high-level goal
    pub fn set_goal(&mut self, description: String, sub_goals: Vec<String>) {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        
        self.current_goal = Some(GoalState {
            goal_description: description,
            sub_goals: sub_goals.into_iter().map(|s| SubGoal {
                description: s,
                status: SubGoalStatus::Pending,
                completion_url: None,
            }).collect(),
            completed_steps: Vec::new(),
            failed_attempts: Vec::new(),
            started_at: now,
            deadline_ms: None,
        });
    }
    
    /// Mark a sub-goal as completed
    pub fn complete_sub_goal(&mut self, index: usize, completion_url: Option<&str>) {
        if let Some(ref mut goal) = self.current_goal {
            if let Some(sub) = goal.sub_goals.get_mut(index) {
                sub.status = SubGoalStatus::Completed;
                sub.completion_url = completion_url.map(String::from);
            }
            goal.completed_steps.push(
                goal.sub_goals.get(index)
                    .map(|s| s.description.clone())
                    .unwrap_or_default()
            );
        }
    }
    
    /// Generate an AI-readable memory context dump for the current URL
    pub fn generate_context_for(&self, current_url: &str) -> MemoryContext {
        let current_page = self.pages.get(current_url);
        
        // Recent interactions (last 20)
        let recent_interactions: Vec<&(String, InteractionRecord)> = self.interaction_log.iter()
            .rev()
            .take(20)
            .collect();
        
        // Pages in the same domain
        let domain = Self::extract_domain(current_url);
        let same_domain_pages: Vec<&MemoryPage> = self.pages.values()
            .filter(|p| p.domain == domain)
            .collect();
        
        // Top landmarks (sorted by importance)
        let mut relevant_landmarks: Vec<&CognitiveLandmark> = self.landmarks.iter()
            .filter(|l| l.page_url.starts_with(&domain))
            .collect();
        relevant_landmarks.sort_by(|a, b| b.importance.cmp(&a.importance));
        
        // Goal progress
        let goal_summary = self.current_goal.as_ref().map(|g| {
            let completed = g.sub_goals.iter().filter(|s| s.status == SubGoalStatus::Completed).count();
            let total = g.sub_goals.len();
            format!("{} ({}/{} steps complete)", g.goal_description, completed, total)
        });
        
        MemoryContext {
            current_url: current_url.to_string(),
            page_type: current_page.map(|p| p.page_type).unwrap_or(PageType::Unknown),
            pages_visited_count: self.pages.len(),
            domain_pages_count: same_domain_pages.len(),
            interaction_count_this_session: self.interaction_log.len(),
            known_entities_count: self.entities.len(),
            top_landmarks: relevant_landmarks.iter()
                .take(5)
                .map(|l| l.description.clone())
                .collect(),
            goal_summary,
            last_error: self.current_goal.as_ref()
                .and_then(|g| g.failed_attempts.last())
                .map(|f| f.error.clone()),
        }
    }
    
    pub fn extract_domain(url: &str) -> String {
        if let Some(after_scheme) = url.find("://").map(|i| &url[i+3..]) {
            let end = after_scheme.find(|c| c == '/' || c == '?' || c == '#')
                .unwrap_or(after_scheme.len());
            return after_scheme[..end].to_string();
        }
        url.to_string()
    }
    
    /// Return the most frequently visited page across all visits
    pub fn most_visited_page(&self) -> Option<&MemoryPage> {
        self.pages.values().max_by_key(|p| p.visit_count)
    }
    
    /// Return the complete interaction history as an AI-readable narrative
    pub fn interaction_narrative(&self, max_entries: usize) -> String {
        let mut narrative = String::new();
        for (url, record) in self.interaction_log.iter().rev().take(max_entries) {
            let action_str = match record.action {
                InteractionAction::Click => "clicked",
                InteractionAction::Type => "typed",
                InteractionAction::Select => "selected",
                InteractionAction::Scroll => "scrolled",
                InteractionAction::Submit => "submitted form on",
                InteractionAction::Focus => "focused on",
                _ => "interacted with",
            };
            let outcome_str = match &record.outcome {
                InteractionOutcome::Success => "successfully".to_string(),
                InteractionOutcome::NavigatedTo(u) => format!("→ navigated to {}", u),
                InteractionOutcome::ErrorShown(e) => format!("→ error: {}", e),
                InteractionOutcome::ModalOpened => "→ dialog opened".to_string(),
                InteractionOutcome::NoChange => "→ no change".to_string(),
                InteractionOutcome::Unknown => String::new(),
            };
            
            narrative.push_str(&format!("• [{}] {} — {}\n", url, action_str, outcome_str));
        }
        narrative
    }
}

/// A compact AI context snapshot from the spatial memory
#[derive(Debug, Clone)]
pub struct MemoryContext {
    pub current_url: String,
    pub page_type: PageType,
    pub pages_visited_count: usize,
    pub domain_pages_count: usize,
    pub interaction_count_this_session: usize,
    pub known_entities_count: usize,
    pub top_landmarks: Vec<String>,
    pub goal_summary: Option<String>,
    pub last_error: Option<String>,
}

impl MemoryContext {
    /// Serialize to a compact AI-facing prompt injection string
    pub fn to_prompt_context(&self) -> String {
        let mut ctx = format!(
            "🗺️ SPATIAL MEMORY CONTEXT\n\
             URL: {}\nPage type: {}\n\
             Session: {} pages visited, {} interactions\n",
            self.current_url,
            self.page_type.ai_description(),
            self.pages_visited_count,
            self.interaction_count_this_session,
        );
        
        if let Some(ref goal) = self.goal_summary {
            ctx.push_str(&format!("🎯 GOAL: {}\n", goal));
        }
        
        if !self.top_landmarks.is_empty() {
            ctx.push_str("📌 KEY LANDMARKS:\n");
            for lm in &self.top_landmarks {
                ctx.push_str(&format!("  • {}\n", lm));
            }
        }
        
        if let Some(ref err) = self.last_error {
            ctx.push_str(&format!("⚠️ LAST ERROR: {}\n", err));
        }
        
        ctx
    }
}
