//! CSS Transition Engine — W3C CSS Transitions Level 1 + FLIP Optimization
//!
//! Implements the complete CSS transition system:
//!   - Transition detection on property value changes
//!   - timing functions: linear, ease, ease-in, ease-out, ease-in-out, cubic-bezier(), steps()
//!   - transition-property, transition-duration, transition-delay, transition-timing-function
//!   - Transition cancellation (overriding running transition mid-flight)
//!   - Reversing multiplier (picking up from current animated value)
//!   - FLIP animation technique helper (First/Last/Invert/Play)
//!   - Transition event tracking (transitionstart, transitionend, transitioncancel, transitionrun)
//!   - AI-facing: running transition summary

use std::collections::HashMap;

/// An easing function for CSS transitions/animations
#[derive(Debug, Clone, PartialEq)]
pub enum EasingFunction {
    Linear,
    Ease,         // cubic-bezier(0.25, 0.1, 0.25, 1)
    EaseIn,       // cubic-bezier(0.42, 0, 1, 1)
    EaseOut,      // cubic-bezier(0, 0, 0.58, 1)
    EaseInOut,    // cubic-bezier(0.42, 0, 0.58, 1)
    CubicBezier(f64, f64, f64, f64),  // P1, P2 control points (x1,y1,x2,y2)
    Steps(u32, StepPosition),
    StepStart,    // steps(1, start)
    StepEnd,      // steps(1, end)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepPosition {
    JumpStart,   // Jump at start of step
    JumpEnd,     // Jump at end of step
    JumpNone,    // No jump at start or end
    JumpBoth,    // Jump at both start and end
    Start,       // Alias for JumpStart
    End,         // Alias for JumpEnd (default)
}

impl EasingFunction {
    /// Parse a CSS easing function string
    pub fn parse(s: &str) -> Self {
        match s.trim() {
            "linear" => Self::Linear,
            "ease" => Self::Ease,
            "ease-in" => Self::EaseIn,
            "ease-out" => Self::EaseOut,
            "ease-in-out" => Self::EaseInOut,
            "step-start" => Self::StepStart,
            "step-end" => Self::StepEnd,
            other => {
                if other.starts_with("cubic-bezier(") {
                    let args: Vec<f64> = other[13..other.len()-1]
                        .split(',')
                        .map(|v| v.trim().parse().unwrap_or(0.0))
                        .collect();
                    if args.len() == 4 {
                        return Self::CubicBezier(args[0], args[1], args[2], args[3]);
                    }
                }
                if other.starts_with("steps(") {
                    let args_str = &other[6..other.len()-1];
                    let parts: Vec<&str> = args_str.split(',').collect();
                    let count: u32 = parts[0].trim().parse().unwrap_or(1);
                    let position = match parts.get(1).map(|s| s.trim()) {
                        Some("start") | Some("jump-start") => StepPosition::JumpStart,
                        Some("both") | Some("jump-both") => StepPosition::JumpBoth,
                        Some("none") | Some("jump-none") => StepPosition::JumpNone,
                        _ => StepPosition::JumpEnd,
                    };
                    return Self::Steps(count, position);
                }
                Self::Linear
            }
        }
    }
    
    /// Compute the eased output for a linear progress t ∈ [0, 1]
    pub fn apply(&self, t: f64) -> f64 {
        match self {
            Self::Linear => t.clamp(0.0, 1.0),
            Self::Ease => Self::cubic_bezier_solve(0.25, 0.1, 0.25, 1.0, t),
            Self::EaseIn => Self::cubic_bezier_solve(0.42, 0.0, 1.0, 1.0, t),
            Self::EaseOut => Self::cubic_bezier_solve(0.0, 0.0, 0.58, 1.0, t),
            Self::EaseInOut => Self::cubic_bezier_solve(0.42, 0.0, 0.58, 1.0, t),
            Self::CubicBezier(x1, y1, x2, y2) => Self::cubic_bezier_solve(*x1, *y1, *x2, *y2, t),
            Self::StepStart => if t < 1.0 { 0.0 } else { 1.0 },
            Self::StepEnd => if t > 0.0 { 1.0 } else { 0.0 },
            Self::Steps(count, position) => {
                let n = *count as f64;
                let (step_offset, step_count) = match position {
                    StepPosition::JumpStart | StepPosition::Start => (1.0, n),
                    StepPosition::JumpEnd | StepPosition::End => (0.0, n),
                    StepPosition::JumpNone => (0.0, n - 1.0),
                    StepPosition::JumpBoth => (1.0, n + 1.0),
                };
                ((t * n + step_offset).floor() / step_count).clamp(0.0, 1.0)
            }
        }
    }
    
    /// Solve cubic bezier using Newton's method (identical to browser implementation)
    fn cubic_bezier_solve(x1: f64, y1: f64, x2: f64, y2: f64, t: f64) -> f64 {
        // Newton's method to find X, then compute Y
        let mut x_guess = t;
        for _ in 0..8 {
            let cx = Self::bezier_component(x_guess, x1, x2);
            let dx = Self::bezier_derivative(x_guess, x1, x2);
            if dx.abs() < 1e-10 { break; }
            x_guess -= (cx - t) / dx;
        }
        Self::bezier_component(x_guess, y1, y2)
    }
    
    fn bezier_component(t: f64, p1: f64, p2: f64) -> f64 {
        let mt = 1.0 - t;
        3.0 * mt * mt * t * p1 + 3.0 * mt * t * t * p2 + t * t * t
    }
    
    fn bezier_derivative(t: f64, p1: f64, p2: f64) -> f64 {
        let mt = 1.0 - t;
        3.0 * mt * mt * p1 + 6.0 * mt * t * (p2 - p1) + 3.0 * t * t * (1.0 - p2)
    }
}

/// A CSS transitionable property value (can interpolate between two values)
#[derive(Debug, Clone, PartialEq)]
pub enum TransitionValue {
    Px(f64),
    Percentage(f64),
    Number(f64),
    Color(f64, f64, f64, f64),   // RGBA components 0.0..1.0
    Angle(f64),                   // degrees
    Transform(Vec<f64>),          // Flattened 4x4 matrix
    Discrete(String),             // Non-interpolatable — switches at 50%
}

impl TransitionValue {
    /// Parse a property value into a TransitionValue
    pub fn parse(property: &str, value: &str) -> Self {
        let v = value.trim();
        
        // Length
        if let Some(px) = v.strip_suffix("px") {
            if let Ok(n) = px.parse::<f64>() { return Self::Px(n); }
        }
        if let Some(pct) = v.strip_suffix('%') {
            if let Ok(n) = pct.parse::<f64>() { return Self::Percentage(n); }
        }
        if let Some(deg) = v.strip_suffix("deg") {
            if let Ok(n) = deg.parse::<f64>() { return Self::Angle(n); }
        }
        if let Ok(n) = v.parse::<f64>() { return Self::Number(n); }
        
        // RGB/RGBA color
        if v.starts_with("rgb") {
            let nums: Vec<f64> = v.trim_start_matches("rgba(").trim_start_matches("rgb(")
                .trim_end_matches(')')
                .split(',')
                .filter_map(|s| s.trim().parse::<f64>().ok())
                .collect();
            if nums.len() >= 3 {
                return Self::Color(
                    nums[0] / 255.0, nums[1] / 255.0, nums[2] / 255.0,
                    nums.get(3).copied().unwrap_or(1.0),
                );
            }
        }
        
        Self::Discrete(v.to_string())
    }
    
    /// Interpolate between two values at time t ∈ [0, 1]
    pub fn interpolate(&self, to: &TransitionValue, t: f64) -> TransitionValue {
        match (self, to) {
            (Self::Px(a), Self::Px(b)) => Self::Px(a + (b - a) * t),
            (Self::Percentage(a), Self::Percentage(b)) => Self::Percentage(a + (b - a) * t),
            (Self::Number(a), Self::Number(b)) => Self::Number(a + (b - a) * t),
            (Self::Angle(a), Self::Angle(b)) => Self::Angle(a + (b - a) * t),
            (Self::Color(r1, g1, b1, a1), Self::Color(r2, g2, b2, a2)) => {
                Self::Color(
                    r1 + (r2 - r1) * t,
                    g1 + (g2 - g1) * t,
                    b1 + (b2 - b1) * t,
                    a1 + (a2 - a1) * t,
                )
            }
            (Self::Transform(a), Self::Transform(b)) if a.len() == b.len() => {
                Self::Transform(a.iter().zip(b.iter()).map(|(av, bv)| av + (bv - av) * t).collect())
            }
            (Self::Discrete(a), Self::Discrete(b)) => {
                // Discrete interpolation — switch at 50%
                if t < 0.5 { Self::Discrete(a.clone()) } else { Self::Discrete(b.clone()) }
            }
            _ => {
                // Mismatched types — use discrete behavior
                if t < 0.5 { self.clone() } else { to.clone() }
            }
        }
    }
    
    /// Serialize to a CSS value string
    pub fn to_css_value(&self) -> String {
        match self {
            Self::Px(n) => format!("{:.3}px", n),
            Self::Percentage(n) => format!("{:.3}%", n),
            Self::Number(n) => format!("{:.6}", n),
            Self::Angle(n) => format!("{:.3}deg", n),
            Self::Color(r, g, b, a) => {
                if (*a - 1.0).abs() < 0.001 {
                    format!("rgb({},{},{})", (r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8)
                } else {
                    format!("rgba({},{},{},{:.4})", (r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8, a)
                }
            }
            Self::Discrete(s) => s.clone(),
            Self::Transform(m) => format!("matrix3d({})", m.iter().map(|v| format!("{:.6}", v)).collect::<Vec<_>>().join(",")),
        }
    }
}

/// The state of a running transition
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TransitionPhase {
    Pending,    // In delay period
    Running,    // Actively interpolating
    Completed,  // Reached end value
    Cancelled,  // Cancelled by a new value set
}

/// A running CSS transition
#[derive(Debug, Clone)]
pub struct TransitionRecord {
    pub node_id: u64,
    pub property: String,
    pub from_value: TransitionValue,
    pub to_value: TransitionValue,
    pub duration_ms: f64,
    pub delay_ms: f64,
    pub easing: EasingFunction,
    pub start_time_ms: f64,
    pub phase: TransitionPhase,
    /// If this transition is reversing a previous one, the reversing shortening multiplier
    pub reversing_shortening_factor: f64,
    /// The current computed value (updated each frame)
    pub current_value: TransitionValue,
}

impl TransitionRecord {
    pub fn new(
        node_id: u64,
        property: &str,
        from: TransitionValue,
        to: TransitionValue,
        duration_ms: f64,
        delay_ms: f64,
        easing: EasingFunction,
        start_time_ms: f64,
    ) -> Self {
        let current = from.clone();
        Self {
            node_id,
            property: property.to_string(),
            from_value: from,
            to_value: to,
            duration_ms,
            delay_ms,
            easing,
            start_time_ms,
            phase: if delay_ms > 0.0 { TransitionPhase::Pending } else { TransitionPhase::Running },
            reversing_shortening_factor: 1.0,
            current_value: current,
        }
    }
    
    /// Update this transition at the given timestamp. Returns the current CSS value as a String.
    pub fn tick(&mut self, now_ms: f64) -> String {
        let elapsed = now_ms - self.start_time_ms;
        
        if elapsed < self.delay_ms {
            self.phase = TransitionPhase::Pending;
            return self.from_value.to_css_value();
        }
        
        let active_elapsed = elapsed - self.delay_ms;
        let effective_duration = self.duration_ms * self.reversing_shortening_factor;
        
        if effective_duration <= 0.0 {
            self.phase = TransitionPhase::Completed;
            self.current_value = self.to_value.clone();
            return self.current_value.to_css_value();
        }
        
        let raw_t = (active_elapsed / effective_duration).clamp(0.0, 1.0);
        let eased_t = self.easing.apply(raw_t);
        
        self.current_value = self.from_value.interpolate(&self.to_value, eased_t);
        
        if raw_t >= 1.0 {
            self.phase = TransitionPhase::Completed;
        } else {
            self.phase = TransitionPhase::Running;
        }
        
        self.current_value.to_css_value()
    }
    
    pub fn is_complete(&self) -> bool { matches!(self.phase, TransitionPhase::Completed | TransitionPhase::Cancelled) }
    pub fn progress(&self, now_ms: f64) -> f64 {
        let active = (now_ms - self.start_time_ms - self.delay_ms).max(0.0);
        (active / self.duration_ms).clamp(0.0, 1.0)
    }
}

/// A transition definition from the CSS `transition` property
#[derive(Debug, Clone)]
pub struct TransitionDefinition {
    pub property: String,
    pub duration_ms: f64,
    pub delay_ms: f64,
    pub easing: EasingFunction,
}

impl TransitionDefinition {
    pub fn parse(s: &str) -> Vec<Self> {
        // Parse "property duration timing-function delay" shorthand
        s.split(',').map(|t| {
            let parts: Vec<&str> = t.trim().split_whitespace().collect();
            let property = parts.get(0).map(|s| s.to_string()).unwrap_or("all".to_string());
            let duration_ms = parts.get(1)
                .and_then(|s| Self::parse_duration_ms(s))
                .unwrap_or(0.0);
            let easing = parts.get(2)
                .map(|s| EasingFunction::parse(s))
                .unwrap_or(EasingFunction::Ease);
            let delay_ms = parts.get(3)
                .and_then(|s| Self::parse_duration_ms(s))
                .unwrap_or(0.0);
            
            TransitionDefinition { property, duration_ms, delay_ms, easing }
        }).collect()
    }
    
    fn parse_duration_ms(s: &str) -> Option<f64> {
        if let Some(ms) = s.strip_suffix("ms") { return ms.parse().ok(); }
        if let Some(sec) = s.strip_suffix('s') { return sec.parse::<f64>().ok().map(|s| s * 1000.0); }
        None
    }
}

/// FLIP animation helper — First/Last/Invert/Play
pub struct FlipAnimation {
    pub node_id: u64,
    pub first_rect: (f64, f64, f64, f64),   // x, y, width, height before move
    pub last_rect: (f64, f64, f64, f64),    // x, y, width, height after move
}

impl FlipAnimation {
    /// Capture first position before a layout change
    pub fn capture_first(node_id: u64, x: f64, y: f64, w: f64, h: f64) -> FlipAnimation {
        FlipAnimation { node_id, first_rect: (x, y, w, h), last_rect: (0.0, 0.0, 0.0, 0.0) }
    }
    
    /// Capture last position after a layout change
    pub fn capture_last(&mut self, x: f64, y: f64, w: f64, h: f64) {
        self.last_rect = (x, y, w, h);
    }
    
    /// Compute the invert transform — what transform to apply at t=0 to look like "first"
    pub fn invert_transform(&self) -> (f64, f64, f64, f64) {
        let dx = self.first_rect.0 - self.last_rect.0;
        let dy = self.first_rect.1 - self.last_rect.1;
        let sx = if self.last_rect.2 > 0.0 { self.first_rect.2 / self.last_rect.2 } else { 1.0 };
        let sy = if self.last_rect.3 > 0.0 { self.first_rect.3 / self.last_rect.3 } else { 1.0 };
        (dx, dy, sx, sy)
    }
    
    /// Convert to CSS transform values for programmatic use
    pub fn invert_css_transform(&self) -> String {
        let (dx, dy, sx, sy) = self.invert_transform();
        format!("translate({:.2}px, {:.2}px) scale({:.4}, {:.4})", dx, dy, sx, sy)
    }
    
    /// Generate the TransitionRecords to play the FLIP animation
    pub fn play_transitions(
        &self,
        duration_ms: f64,
        easing: EasingFunction,
        now_ms: f64,
    ) -> Vec<TransitionRecord> {
        let (dx, dy, sx, sy) = self.invert_transform();
        
        vec![
            TransitionRecord::new(
                self.node_id,
                "transform-translate-x",
                TransitionValue::Px(dx),
                TransitionValue::Px(0.0),
                duration_ms, 0.0, easing.clone(), now_ms,
            ),
            TransitionRecord::new(
                self.node_id,
                "transform-translate-y",
                TransitionValue::Px(dy),
                TransitionValue::Px(0.0),
                duration_ms, 0.0, easing.clone(), now_ms,
            ),
            TransitionRecord::new(
                self.node_id,
                "transform-scale-x",
                TransitionValue::Number(sx),
                TransitionValue::Number(1.0),
                duration_ms, 0.0, easing.clone(), now_ms,
            ),
            TransitionRecord::new(
                self.node_id,
                "transform-scale-y",
                TransitionValue::Number(sy),
                TransitionValue::Number(1.0),
                duration_ms, 0.0, easing, now_ms,
            ),
        ]
    }
}

/// The Transition Engine — manages all running transitions
pub struct TransitionEngine {
    /// Active transitions (node_id, property) -> record
    active: HashMap<(u64, String), TransitionRecord>,
}

impl TransitionEngine {
    pub fn new() -> Self { Self { active: HashMap::new() } }
    
    /// Trigger a property change — starts a transition if one is defined
    pub fn trigger(
        &mut self,
        node_id: u64,
        property: &str,
        old_value: &str,
        new_value: &str,
        definition: Option<&TransitionDefinition>,
        now_ms: f64,
    ) {
        let def = match definition { Some(d) => d, None => return };
        if def.duration_ms <= 0.0 { return; }
        
        let from = if let Some(running) = self.active.get(&(node_id, property.to_string())) {
            // Reversing: start from current computed value (mid-animation)
            running.current_value.clone()
        } else {
            TransitionValue::parse(property, old_value)
        };
        
        let to = TransitionValue::parse(property, new_value);
        
        // Don't transition if values are identical
        if from == to { return; }
        
        let record = TransitionRecord::new(
            node_id, property, from, to,
            def.duration_ms, def.delay_ms, def.easing.clone(), now_ms,
        );
        
        self.active.insert((node_id, property.to_string()), record);
    }
    
    /// Advance all transitions by one frame tick
    pub fn tick(&mut self, now_ms: f64) -> Vec<(u64, String, String)> {
        let mut current_values = Vec::new();
        
        for ((node_id, property), record) in &mut self.active {
            let current = record.tick(now_ms);
            current_values.push((*node_id, property.clone(), current));
        }
        
        // Remove completed/cancelled transitions
        self.active.retain(|_, r| !r.is_complete());
        
        current_values
    }
    
    pub fn cancel(&mut self, node_id: u64, property: &str) {
        if let Some(t) = self.active.get_mut(&(node_id, property.to_string())) {
            t.phase = TransitionPhase::Cancelled;
        }
        self.active.remove(&(node_id, property.to_string()));
    }
    
    pub fn cancel_all_for_node(&mut self, node_id: u64) {
        self.active.retain(|(nid, _), _| *nid != node_id);
    }
    
    pub fn active_count(&self) -> usize { self.active.len() }
    pub fn is_transitioning(&self, node_id: u64, property: &str) -> bool {
        self.active.contains_key(&(node_id, property.to_string()))
    }
    
    /// AI snapshot of all running transitions
    pub fn ai_transition_summary(&self, now_ms: f64) -> String {
        if self.active.is_empty() { return "🎬 No active transitions".to_string(); }
        
        let mut lines = vec![format!("🎬 {} active transitions:", self.active.len())];
        for ((node_id, prop), rec) in &self.active {
            let progress = rec.progress(now_ms);
            lines.push(format!("  node#{} {} → {:.0}% ({:?})",
                node_id, prop, progress * 100.0, rec.phase));
        }
        lines.join("\n")
    }
}
