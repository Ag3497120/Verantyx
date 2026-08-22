//! CSS Animations & Transitions

use crate::units::Time;
use std::fmt;

/// CSS timing function
#[derive(Debug, Clone, PartialEq)]
pub enum TimingFunction {
    /// linear
    Linear,
    /// ease (cubic-bezier(0.25, 0.1, 0.25, 1.0))
    Ease,
    /// ease-in
    EaseIn,
    /// ease-out
    EaseOut,
    /// ease-in-out
    EaseInOut,
    /// step-start
    StepStart,
    /// step-end
    StepEnd,
    /// cubic-bezier(p1x, p1y, p2x, p2y)
    CubicBezier(f32, f32, f32, f32),
    /// steps(n, jump-start|jump-end|jump-none|jump-both|start|end)
    Steps(u32, StepPosition),
    /// linear(0, 0.25, 1) — CSS linear() function
    LinearList(Vec<LinearStop>),
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum StepPosition {
    JumpStart,
    JumpEnd,
    JumpNone,
    JumpBoth,
    Start,
    End,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LinearStop {
    pub value: f32,
    pub hint: Option<f32>,
}

impl TimingFunction {
    pub fn parse(s: &str) -> Self {
        match s.trim() {
            "linear" => Self::Linear,
            "ease" => Self::Ease,
            "ease-in" => Self::EaseIn,
            "ease-out" => Self::EaseOut,
            "ease-in-out" => Self::EaseInOut,
            "step-start" => Self::StepStart,
            "step-end" => Self::StepEnd,
            s if s.starts_with("cubic-bezier(") => {
                let inner = &s[13..s.len()-1];
                let parts: Vec<f32> = inner.split(',')
                    .filter_map(|v| v.trim().parse().ok())
                    .collect();
                if parts.len() == 4 {
                    Self::CubicBezier(parts[0], parts[1], parts[2], parts[3])
                } else {
                    Self::Ease
                }
            }
            s if s.starts_with("steps(") => {
                let inner = &s[6..s.len()-1];
                let parts: Vec<&str> = inner.split(',').collect();
                let n: u32 = parts.first().and_then(|p| p.trim().parse().ok()).unwrap_or(1);
                let pos = match parts.get(1).map(|p| p.trim()) {
                    Some("jump-start") | Some("start") => StepPosition::JumpStart,
                    Some("jump-none") => StepPosition::JumpNone,
                    Some("jump-both") => StepPosition::JumpBoth,
                    _ => StepPosition::JumpEnd,
                };
                Self::Steps(n, pos)
            }
            _ => Self::Ease,
        }
    }

    /// Sample the timing function at progress t (0.0..=1.0)
    pub fn sample(&self, t: f32) -> f32 {
        let t = t.clamp(0.0, 1.0);
        match self {
            Self::Linear | Self::LinearList(_) => t,
            Self::Ease => cubic_bezier(0.25, 0.1, 0.25, 1.0, t),
            Self::EaseIn => cubic_bezier(0.42, 0.0, 1.0, 1.0, t),
            Self::EaseOut => cubic_bezier(0.0, 0.0, 0.58, 1.0, t),
            Self::EaseInOut => cubic_bezier(0.42, 0.0, 0.58, 1.0, t),
            Self::StepStart => if t > 0.0 { 1.0 } else { 0.0 },
            Self::StepEnd => if t >= 1.0 { 1.0 } else { 0.0 },
            Self::CubicBezier(p1x, p1y, p2x, p2y) => cubic_bezier(*p1x, *p1y, *p2x, *p2y, t),
            Self::Steps(n, pos) => {
                let n = *n as f32;
                let step = match pos {
                    StepPosition::JumpStart | StepPosition::Start => (t * n).ceil() / n,
                    StepPosition::JumpEnd | StepPosition::End => (t * n).floor() / n,
                    StepPosition::JumpNone => ((t * (n - 1.0)).floor()) / (n - 1.0),
                    StepPosition::JumpBoth => ((t * n).floor() + 1.0) / (n + 1.0),
                };
                step.clamp(0.0, 1.0)
            }
        }
    }
}

/// Cubic bezier approximation using numerical method
fn cubic_bezier(p1x: f32, p1y: f32, p2x: f32, p2y: f32, t: f32) -> f32 {
    // Newton's method to solve for t given x
    const ITERATIONS: u32 = 8;
    let mut guess = t;

    for _ in 0..ITERATIONS {
        let x = bezier_x(p1x, p2x, guess);
        let dx = bezier_dx(p1x, p2x, guess);
        if dx.abs() < 1e-6 { break; }
        guess -= (x - t) / dx;
    }

    bezier_y(p1y, p2y, guess)
}

fn bezier_x(p1x: f32, p2x: f32, t: f32) -> f32 {
    let cx = 3.0 * p1x;
    let bx = 3.0 * (p2x - p1x) - cx;
    let ax = 1.0 - cx - bx;
    ((ax * t + bx) * t + cx) * t
}

fn bezier_dx(p1x: f32, p2x: f32, t: f32) -> f32 {
    let cx = 3.0 * p1x;
    let bx = 3.0 * (p2x - p1x) - cx;
    let ax = 1.0 - cx - bx;
    (3.0 * ax * t + 2.0 * bx) * t + cx
}

fn bezier_y(p1y: f32, p2y: f32, t: f32) -> f32 {
    let cy = 3.0 * p1y;
    let by = 3.0 * (p2y - p1y) - cy;
    let ay = 1.0 - cy - by;
    ((ay * t + by) * t + cy) * t
}

/// Animation iteration count
#[derive(Debug, Clone, PartialEq)]
pub enum IterationCount {
    Finite(f32),
    Infinite,
}

impl IterationCount {
    pub fn parse(s: &str) -> Self {
        if s == "infinite" { Self::Infinite }
        else { s.parse::<f32>().map(Self::Finite).unwrap_or(Self::Finite(1.0)) }
    }
}

/// Animation direction
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AnimationDirection {
    Normal,
    Reverse,
    Alternate,
    AlternateReverse,
}

impl AnimationDirection {
    pub fn parse(s: &str) -> Self {
        match s {
            "reverse" => Self::Reverse,
            "alternate" => Self::Alternate,
            "alternate-reverse" => Self::AlternateReverse,
            _ => Self::Normal,
        }
    }

    pub fn is_reversed(&self, iteration: f32) -> bool {
        match self {
            Self::Normal => false,
            Self::Reverse => true,
            Self::Alternate => iteration as u32 % 2 == 1,
            Self::AlternateReverse => iteration as u32 % 2 == 0,
        }
    }
}

/// Animation fill mode
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FillMode {
    None,
    Forwards,
    Backwards,
    Both,
}

impl FillMode {
    pub fn parse(s: &str) -> Self {
        match s {
            "forwards" => Self::Forwards,
            "backwards" => Self::Backwards,
            "both" => Self::Both,
            _ => Self::None,
        }
    }
}

/// Animation play state
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PlayState {
    Running,
    Paused,
}

/// A single CSS animation
#[derive(Debug, Clone)]
pub struct Animation {
    pub name: String,
    pub duration: f32,       // ms
    pub delay: f32,          // ms
    pub timing: TimingFunction,
    pub iteration_count: IterationCount,
    pub direction: AnimationDirection,
    pub fill_mode: FillMode,
    pub play_state: PlayState,
    pub timeline: Option<String>,
    pub range: Option<(String, String)>,
    pub composition: AnimationComposition,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AnimationComposition {
    Replace,
    Add,
    Accumulate,
}

impl Default for Animation {
    fn default() -> Self {
        Self {
            name: "none".to_string(),
            duration: 0.0,
            delay: 0.0,
            timing: TimingFunction::Ease,
            iteration_count: IterationCount::Finite(1.0),
            direction: AnimationDirection::Normal,
            fill_mode: FillMode::None,
            play_state: PlayState::Running,
            timeline: None,
            range: None,
            composition: AnimationComposition::Replace,
        }
    }
}

impl Animation {
    /// Compute animation progress at a given time (ms)
    pub fn progress_at(&self, time_ms: f32) -> Option<f32> {
        if matches!(self.play_state, PlayState::Paused) {
            return None;
        }

        let elapsed = time_ms - self.delay;
        if elapsed < 0.0 {
            if matches!(self.fill_mode, FillMode::Backwards | FillMode::Both) {
                return Some(0.0);
            }
            return None;
        }

        let total = self.duration;
        if total <= 0.0 { return Some(1.0); }

        let iteration = elapsed / total;

        let completed = match &self.iteration_count {
            IterationCount::Infinite => false,
            IterationCount::Finite(n) => iteration >= *n,
        };

        if completed {
            if matches!(self.fill_mode, FillMode::Forwards | FillMode::Both) {
                return Some(1.0);
            }
            return None;
        }

        let t = iteration.fract();
        let t = if self.direction.is_reversed(iteration) { 1.0 - t } else { t };
        Some(self.timing.sample(t))
    }
}

/// A CSS transition definition
#[derive(Debug, Clone)]
pub struct Transition {
    pub property: String,
    pub duration: f32,  // ms
    pub delay: f32,     // ms
    pub timing: TimingFunction,
    pub behavior: TransitionBehavior,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TransitionBehavior {
    Normal,
    AllowDiscrete,
}

impl Default for Transition {
    fn default() -> Self {
        Self {
            property: "all".to_string(),
            duration: 0.0,
            delay: 0.0,
            timing: TimingFunction::Ease,
            behavior: TransitionBehavior::Normal,
        }
    }
}

impl Transition {
    pub fn progress_at(&self, elapsed_ms: f32) -> f32 {
        let elapsed = elapsed_ms - self.delay;
        if elapsed < 0.0 { return 0.0; }
        if self.duration <= 0.0 { return 1.0; }
        let t = (elapsed / self.duration).clamp(0.0, 1.0);
        self.timing.sample(t)
    }
}

/// Interpolate between two f32 values
pub fn interpolate_f32(from: f32, to: f32, progress: f32) -> f32 {
    from + (to - from) * progress
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_timing_function_linear() {
        let f = TimingFunction::Linear;
        assert!((f.sample(0.0) - 0.0).abs() < 0.001);
        assert!((f.sample(0.5) - 0.5).abs() < 0.001);
        assert!((f.sample(1.0) - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_timing_function_ease_in_out() {
        let f = TimingFunction::EaseInOut;
        // ease-in-out should start slow, speed up, then slow down
        assert!(f.sample(0.0) < 0.1);
        assert!(f.sample(1.0) > 0.9);
        // midpoint should be close to 0.5
        assert!((f.sample(0.5) - 0.5).abs() < 0.1);
    }

    #[test]
    fn test_step_start() {
        let f = TimingFunction::StepStart;
        assert_eq!(f.sample(0.0), 0.0);
        assert_eq!(f.sample(0.01), 1.0);
        assert_eq!(f.sample(1.0), 1.0);
    }

    #[test]
    fn test_cubic_bezier_parse() {
        let f = TimingFunction::parse("cubic-bezier(0.42, 0.0, 0.58, 1.0)");
        assert!(matches!(f, TimingFunction::CubicBezier(_, _, _, _)));
    }

    #[test]
    fn test_animation_progress() {
        let anim = Animation {
            duration: 1000.0,
            timing: TimingFunction::Linear,
            ..Default::default()
        };
        assert!((anim.progress_at(500.0).unwrap() - 0.5).abs() < 0.01);
        assert!((anim.progress_at(250.0).unwrap() - 0.25).abs() < 0.01);
    }

    #[test]
    fn test_direction_reversal() {
        assert!(!AnimationDirection::Normal.is_reversed(0.0));
        assert!(AnimationDirection::Reverse.is_reversed(0.0));
        assert!(AnimationDirection::Alternate.is_reversed(1.0));
        assert!(!AnimationDirection::Alternate.is_reversed(0.0));
    }
}
