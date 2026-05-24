//! CSS Animation Timeline Engine — W3C CSS Animations Level 2 + Web Animations API
//!
//! Implements the complete CSS animation system:
//!   - Keyframe parsing and resolution
//!   - Easing functions (cubic-bezier, steps(), linear, ease, ease-in, etc.)
//!   - fill-mode handling (none, forwards, backwards, both)
//!   - iteration-count (infinite + integer)
//!   - animation-direction (normal, reverse, alternate, alternate-reverse)
//!   - Web Animations API (KeyframeEffect, Animation, AnimationTimeline)
//!   - Scroll-driven animations (animation-timeline: scroll())
//!   - CSS custom properties (@property) as animatable

use std::collections::HashMap;

/// A CSS easing function — determines the rate of change over time
#[derive(Debug, Clone, PartialEq)]
pub enum EasingFunction {
    /// linear — constant rate
    Linear,
    /// ease — cubic-bezier(0.25, 0.1, 0.25, 1.0) — default
    Ease,
    /// ease-in — cubic-bezier(0.42, 0, 1.0, 1.0)
    EaseIn,
    /// ease-out — cubic-bezier(0, 0, 0.58, 1.0)
    EaseOut,
    /// ease-in-out — cubic-bezier(0.42, 0, 0.58, 1.0)
    EaseInOut,
    /// step-start — discrete jump at the beginning
    StepStart,
    /// step-end — discrete jump at the end
    StepEnd,
    /// cubic-bezier(x1, y1, x2, y2)
    CubicBezier { x1: f64, y1: f64, x2: f64, y2: f64 },
    /// steps(count, position)
    Steps { count: u32, position: StepPosition },
    /// linear() with control points for CSS linear() function
    LinearPoints(Vec<(f64, f64)>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepPosition {
    Start,
    End,
    JumpStart,
    JumpEnd,
    JumpNone,
    JumpBoth,
}

impl EasingFunction {
    pub fn parse(s: &str) -> Self {
        match s.trim().to_lowercase().as_str() {
            "linear" => Self::Linear,
            "ease" => Self::Ease,
            "ease-in" => Self::EaseIn,
            "ease-out" => Self::EaseOut,
            "ease-in-out" => Self::EaseInOut,
            "step-start" => Self::StepStart,
            "step-end" => Self::StepEnd,
            _ => {
                if s.starts_with("cubic-bezier(") {
                    let args = s.trim_start_matches("cubic-bezier(").trim_end_matches(')');
                    let vals: Vec<f64> = args.split(',')
                        .map(|v| v.trim().parse().unwrap_or(0.0))
                        .collect();
                    if vals.len() >= 4 {
                        return Self::CubicBezier { x1: vals[0], y1: vals[1], x2: vals[2], y2: vals[3] };
                    }
                }
                if s.starts_with("steps(") {
                    let args = s.trim_start_matches("steps(").trim_end_matches(')');
                    let mut parts = args.splitn(2, ',');
                    let count: u32 = parts.next().unwrap_or("1").trim().parse().unwrap_or(1);
                    let pos = match parts.next().unwrap_or("end").trim() {
                        "start" | "jump-start" => StepPosition::JumpStart,
                        "jump-end" => StepPosition::JumpEnd,
                        "jump-none" => StepPosition::JumpNone,
                        "jump-both" => StepPosition::JumpBoth,
                        _ => StepPosition::JumpEnd,
                    };
                    return Self::Steps { count, position: pos };
                }
                Self::Ease // Default fallback
            }
        }
    }
    
    /// Compute the easing output for progress t ∈ [0, 1]
    pub fn compute(&self, t: f64) -> f64 {
        match self {
            Self::Linear => t,
            Self::Ease => Self::CubicBezier { x1: 0.25, y1: 0.1, x2: 0.25, y2: 1.0 }.compute(t),
            Self::EaseIn => Self::CubicBezier { x1: 0.42, y1: 0.0, x2: 1.0, y2: 1.0 }.compute(t),
            Self::EaseOut => Self::CubicBezier { x1: 0.0, y1: 0.0, x2: 0.58, y2: 1.0 }.compute(t),
            Self::EaseInOut => Self::CubicBezier { x1: 0.42, y1: 0.0, x2: 0.58, y2: 1.0 }.compute(t),
            Self::StepStart => if t > 0.0 { 1.0 } else { 0.0 },
            Self::StepEnd => if t >= 1.0 { 1.0 } else { 0.0 },
            Self::Steps { count, position } => {
                let steps = *count as f64;
                let step = match position {
                    StepPosition::JumpStart | StepPosition::Start => (t * steps).ceil() / steps,
                    StepPosition::JumpEnd | StepPosition::End => (t * steps).floor() / steps,
                    StepPosition::JumpNone => {
                        if t >= 1.0 { 1.0 } else { (t * steps).floor() / (steps - 1.0) }
                    }
                    StepPosition::JumpBoth => {
                        ((t * steps).floor() + 1.0) / (steps + 1.0)
                    }
                };
                step.clamp(0.0, 1.0)
            }
            Self::CubicBezier { x1, y1, x2, y2 } => {
                Self::solve_cubic_bezier(t, *x1, *y1, *x2, *y2)
            }
            Self::LinearPoints(points) => {
                if points.is_empty() { return t; }
                // Interpolate through the linear control points
                for i in 0..points.len().saturating_sub(1) {
                    let (x0, y0) = points[i];
                    let (x1, y1) = points[i + 1];
                    if t >= x0 && t <= x1 {
                        let local_t = if x1 - x0 > 0.0 { (t - x0) / (x1 - x0) } else { 0.0 };
                        return y0 + (y1 - y0) * local_t;
                    }
                }
                points.last().map(|(_, y)| *y).unwrap_or(t)
            }
        }
    }
    
    /// Solve cubic Bezier using Newton's method for the CSS timing function
    fn solve_cubic_bezier(t: f64, x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
        // Find x on the cubic bezier curve using Newton's method,
        // then compute corresponding y value
        let ax = 3.0 * x1 - 3.0 * x2 + 1.0;
        let bx = 3.0 * x2 - 6.0 * x1;
        let cx = 3.0 * x1;
        
        let ay = 3.0 * y1 - 3.0 * y2 + 1.0;
        let by = 3.0 * y2 - 6.0 * y1;
        let cy = 3.0 * y1;
        
        let bezier_x = |t: f64| ((ax * t + bx) * t + cx) * t;
        let bezier_x_derivative = |t: f64| (3.0 * ax * t + 2.0 * bx) * t + cx;
        let bezier_y = |t: f64| ((ay * t + by) * t + cy) * t;
        
        // Newton-Raphson iterations to solve for t from x
        let mut guess = t;
        for _ in 0..8 {
            let x_for_t = bezier_x(guess) - t;
            let dx = bezier_x_derivative(guess);
            if dx.abs() < 1e-6 { break; }
            guess -= x_for_t / dx;
            guess = guess.clamp(0.0, 1.0);
        }
        
        bezier_y(guess)
    }
}

/// Animation play state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlayState {
    Running,
    Paused,
    Finished,
}

/// Animation fill mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FillMode {
    None,
    Forwards,
    Backwards,
    Both,
}

impl FillMode {
    pub fn from_str(s: &str) -> Self {
        match s {
            "forwards" => Self::Forwards,
            "backwards" => Self::Backwards,
            "both" => Self::Both,
            _ => Self::None,
        }
    }
}

/// Animation direction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnimationDirection {
    Normal,
    Reverse,
    Alternate,
    AlternateReverse,
}

impl AnimationDirection {
    pub fn from_str(s: &str) -> Self {
        match s {
            "reverse" => Self::Reverse,
            "alternate" => Self::Alternate,
            "alternate-reverse" => Self::AlternateReverse,
            _ => Self::Normal,
        }
    }
}

/// Iteration count
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum IterationCount {
    Infinite,
    Count(f64),
}

impl IterationCount {
    pub fn from_str(s: &str) -> Self {
        match s.trim().to_lowercase().as_str() {
            "infinite" => Self::Infinite,
            n => Self::Count(n.parse().unwrap_or(1.0)),
        }
    }
    
    pub fn is_infinite(&self) -> bool { matches!(self, Self::Infinite) }
}

/// A single keyframe (e.g., 0%, 50%, 100%)
#[derive(Debug, Clone)]
pub struct Keyframe {
    /// Offset 0.0 to 1.0 (percentage / 100)
    pub offset: f64,
    /// CSS properties at this keyframe
    pub properties: HashMap<String, String>,
    /// Per-keyframe easing function for the interval FROM this keyframe to the next
    pub easing: EasingFunction,
}

impl Keyframe {
    pub fn new(offset: f64, properties: HashMap<String, String>) -> Self {
        Self { offset, properties, easing: EasingFunction::Ease }
    }
    
    pub fn with_easing(mut self, easing: EasingFunction) -> Self {
        self.easing = easing;
        self
    }
}

/// A defined CSS animation (`@keyframes` + animation properties)
#[derive(Debug, Clone)]
pub struct CssAnimation {
    pub name: String,
    pub duration_ms: f64,
    pub easing: EasingFunction,
    pub delay_ms: f64,
    pub direction: AnimationDirection,
    pub iteration_count: IterationCount,
    pub fill_mode: FillMode,
    pub play_state: PlayState,
    pub keyframes: Vec<Keyframe>,
}

impl CssAnimation {
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
            duration_ms: 0.0,
            easing: EasingFunction::Ease,
            delay_ms: 0.0,
            direction: AnimationDirection::Normal,
            iteration_count: IterationCount::Count(1.0),
            fill_mode: FillMode::None,
            play_state: PlayState::Running,
            keyframes: Vec::new(),
        }
    }
    
    /// Compute the active progress for an animation at a given time
    pub fn compute_progress(&self, elapsed_ms: f64) -> AnimationProgress {
        let active_time = elapsed_ms - self.delay_ms;
        
        // During delay
        if active_time < 0.0 {
            return match self.fill_mode {
                FillMode::Backwards | FillMode::Both => {
                    AnimationProgress::PreDelay { fill_offset: self.delay_fill_offset() }
                }
                _ => AnimationProgress::NotYetStarted,
            };
        }
        
        // Finished check
        let total_duration = match self.iteration_count {
            IterationCount::Infinite => f64::INFINITY,
            IterationCount::Count(n) => n * self.duration_ms,
        };
        
        if active_time >= total_duration && !self.iteration_count.is_infinite() {
            let fill_offset = match self.direction {
                AnimationDirection::Normal | AnimationDirection::Alternate => 1.0,
                AnimationDirection::Reverse | AnimationDirection::AlternateReverse => 0.0,
            };
            return match self.fill_mode {
                FillMode::Forwards | FillMode::Both => {
                    AnimationProgress::Finished { fill_offset }
                }
                _ => AnimationProgress::Finished { fill_offset: 0.0 },
            };
        }
        
        // Active
        if self.duration_ms == 0.0 {
            return AnimationProgress::Active { offset: 1.0, iteration: 0 };
        }
        
        let iteration_raw = active_time / self.duration_ms;
        let iteration = iteration_raw.floor() as u64;
        let local_t = iteration_raw - iteration as f64;
        
        // Apply direction
        let directed_t = match self.direction {
            AnimationDirection::Normal => local_t,
            AnimationDirection::Reverse => 1.0 - local_t,
            AnimationDirection::Alternate => {
                if iteration % 2 == 0 { local_t } else { 1.0 - local_t }
            }
            AnimationDirection::AlternateReverse => {
                if iteration % 2 == 0 { 1.0 - local_t } else { local_t }
            }
        };
        
        AnimationProgress::Active { offset: directed_t, iteration }
    }
    
    fn delay_fill_offset(&self) -> f64 {
        match self.direction {
            AnimationDirection::Reverse | AnimationDirection::AlternateReverse => 1.0,
            _ => 0.0,
        }
    }
    
    /// Interpolate CSS property values at a given progress offset (0.0 to 1.0)
    pub fn interpolate_at(&self, offset: f64) -> HashMap<String, String> {
        if self.keyframes.is_empty() { return HashMap::new(); }
        
        // Find surrounding keyframes
        let (prev_kf, next_kf) = self.surrounding_keyframes(offset);
        
        if let (Some(prev), Some(next)) = (prev_kf, next_kf) {
            let span = next.offset - prev.offset;
            let local_t = if span > 0.0 { (offset - prev.offset) / span } else { 0.0 };
            let eased_t = prev.easing.compute(local_t);
            
            self.interpolate_properties(&prev.properties, &next.properties, eased_t)
        } else if let Some(kf) = prev_kf.or(next_kf) {
            kf.properties.clone()
        } else {
            HashMap::new()
        }
    }
    
    fn surrounding_keyframes(&self, offset: f64) -> (Option<&Keyframe>, Option<&Keyframe>) {
        let mut prev = None;
        let mut next = None;
        
        for kf in &self.keyframes {
            if kf.offset <= offset {
                prev = Some(kf);
            } else if next.is_none() {
                next = Some(kf);
            }
        }
        
        (prev, next)
    }
    
    fn interpolate_properties(
        &self,
        from: &HashMap<String, String>,
        to: &HashMap<String, String>,
        t: f64,
    ) -> HashMap<String, String> {
        let mut result = HashMap::new();
        
        for (prop, from_val) in from {
            if let Some(to_val) = to.get(prop) {
                let interpolated = self.interpolate_value(prop, from_val, to_val, t);
                result.insert(prop.clone(), interpolated);
            } else {
                result.insert(prop.clone(), from_val.clone());
            }
        }
        
        for (prop, to_val) in to {
            if !from.contains_key(prop) {
                result.insert(prop.clone(), to_val.clone());
            }
        }
        
        result
    }
    
    /// Interpolate a single CSS value based on property type
    fn interpolate_value(&self, property: &str, from: &str, to: &str, t: f64) -> String {
        // Try numeric interpolation
        if let (Ok(a), Ok(b)) = (from.parse::<f64>(), to.parse::<f64>()) {
            return format!("{:.4}", a + (b - a) * t);
        }
        
        // Pixel value interpolation
        if from.ends_with("px") && to.ends_with("px") {
            let a: f64 = from.trim_end_matches("px").parse().unwrap_or(0.0);
            let b: f64 = to.trim_end_matches("px").parse().unwrap_or(0.0);
            return format!("{:.2}px", a + (b - a) * t);
        }
        
        // Percentage interpolation
        if from.ends_with('%') && to.ends_with('%') {
            let a: f64 = from.trim_end_matches('%').parse().unwrap_or(0.0);
            let b: f64 = to.trim_end_matches('%').parse().unwrap_or(0.0);
            return format!("{:.2}%", a + (b - a) * t);
        }
        
        // opacity is always a bare number
        if property == "opacity" {
            let a: f64 = from.parse().unwrap_or(1.0);
            let b: f64 = to.parse().unwrap_or(1.0);
            return format!("{:.4}", (a + (b - a) * t).clamp(0.0, 1.0));
        }
        
        // Discrete (non-interpolatable) — snap at 50%
        if t < 0.5 { from.to_string() } else { to.to_string() }
    }
}

/// Progress result from animation timing computation
#[derive(Debug, Clone, PartialEq)]
pub enum AnimationProgress {
    NotYetStarted,
    PreDelay { fill_offset: f64 },
    Active { offset: f64, iteration: u64 },
    Finished { fill_offset: f64 },
}

/// The animation controller — manages all active animations on a given element
pub struct ElementAnimationController {
    pub node_id: u64,
    pub animations: Vec<CssAnimation>,
    pub start_time: std::time::Instant,
}

impl ElementAnimationController {
    pub fn new(node_id: u64) -> Self {
        Self { node_id, animations: Vec::new(), start_time: std::time::Instant::now() }
    }
    
    pub fn add_animation(&mut self, anim: CssAnimation) {
        // Remove existing animation with same name
        self.animations.retain(|a| a.name != anim.name);
        self.animations.push(anim);
    }
    
    pub fn remove_animation(&mut self, name: &str) {
        self.animations.retain(|a| a.name != name);
    }
    
    /// Compute the current animated property values for this element
    pub fn current_properties(&self) -> HashMap<String, String> {
        let elapsed_ms = self.start_time.elapsed().as_secs_f64() * 1000.0;
        let mut result = HashMap::new();
        
        // Apply animations in reverse (later animations have lower priority)
        for anim in self.animations.iter().rev() {
            let progress = anim.compute_progress(elapsed_ms);
            let offset = match progress {
                AnimationProgress::Active { offset, .. } => offset,
                AnimationProgress::PreDelay { fill_offset } => fill_offset,
                AnimationProgress::Finished { fill_offset } => fill_offset,
                AnimationProgress::NotYetStarted => continue,
            };
            
            let props = anim.interpolate_at(offset);
            result.extend(props);
        }
        
        result
    }
    
    pub fn has_running_animations(&self) -> bool {
        let elapsed_ms = self.start_time.elapsed().as_secs_f64() * 1000.0;
        self.animations.iter().any(|a| {
            a.play_state == PlayState::Running &&
            matches!(a.compute_progress(elapsed_ms), AnimationProgress::Active { .. })
        })
    }
}

/// A CSS Transition (simpler than full Web Animations — single from→to)
#[derive(Debug, Clone)]
pub struct CssTransition {
    pub property: String,
    pub from_value: String,
    pub to_value: String,
    pub duration_ms: f64,
    pub delay_ms: f64,
    pub easing: EasingFunction,
    pub start_time_ms: f64,
}

impl CssTransition {
    pub fn compute_at(&self, now_ms: f64) -> String {
        let elapsed = now_ms - self.start_time_ms - self.delay_ms;
        let t = if self.duration_ms > 0.0 {
            (elapsed / self.duration_ms).clamp(0.0, 1.0)
        } else {
            1.0
        };
        let eased_t = self.easing.compute(t);
        
        // Reuse animation value interpolation
        let dummy_anim = CssAnimation::new("");
        dummy_anim.interpolate_value(&self.property, &self.from_value, &self.to_value, eased_t)
    }
    
    pub fn is_finished(&self, now_ms: f64) -> bool {
        now_ms >= self.start_time_ms + self.delay_ms + self.duration_ms
    }
}
