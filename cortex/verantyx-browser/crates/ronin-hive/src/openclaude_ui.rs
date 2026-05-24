//! OpenClaude CLI Visual Identity Port
//! Implements the EXACT sunset gradient logo, box models, and colors of Gitlawb/openclaude.

use crate::config::CloudProvider;
use dialoguer::theme::Theme;
use std::fmt;

pub type Rgb = (u8, u8, u8);

pub const ACCENT: Rgb = (240, 148, 100);
pub const CREAM: Rgb = (220, 195, 170);
pub const DIMCOL: Rgb = (120, 100, 82);
pub const BORDER: Rgb = (100, 80, 65);

const SUNSET_GRAD: &[Rgb] = &[
    (255, 180, 100),
    (240, 140, 80),
    (217, 119, 87),
    (193, 95, 60),
    (160, 75, 55),
    (130, 60, 50),
];

const LOGO_VERANTYX: &[&str] = &[
    "██╗   ██╗███████╗██████╗  █████╗ ███╗   ██╗████████╗██╗   ██╗██╗  ██╗",
    "██║   ██║██╔════╝██╔══██╗██╔══██╗████╗  ██║╚══██╔══╝╚██╗ ██╔╝╚██╗██╔╝",
    "██║   ██║█████╗  ██████╔╝███████║██╔██╗ ██║   ██║    ╚████╔╝  ╚███╔╝ ",
    "╚██╗ ██╔╝██╔══╝  ██╔══██╗██╔══██║██║╚██╗██║   ██║     ╚██╔╝   ██╔██╗ ",
    " ╚████╔╝ ███████╗██║  ██║██║  ██║██║ ╚████║   ██║      ██║   ██╔╝ ██╗",
    "  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝",
];

// ─── ANSI Helper ─────────────────────────────────────────────────────────────

pub fn rgb_ansi((r, g, b): Rgb) -> String {
    format!("\x1b[38;2;{};{};{}m", r, g, b)
}

pub const RESET: &str = "\x1b[0m";
pub const DIM: &str = "\x1b[2m";

pub fn color_text(text: &str, color: Rgb) -> String {
    format!("{}{}{}", rgb_ansi(color), text, RESET)
}

pub fn dim_text(text: &str) -> String {
    format!("{}{}{}", DIM, text, RESET)
}

// ─── Gradient Math ─────────────────────────────────────────────────────────────

fn lerp(a: Rgb, b: Rgb, t: f32) -> Rgb {
    (
        (a.0 as f32 + (b.0 as f32 - a.0 as f32) * t).round() as u8,
        (a.1 as f32 + (b.1 as f32 - a.1 as f32) * t).round() as u8,
        (a.2 as f32 + (b.2 as f32 - a.2 as f32) * t).round() as u8,
    )
}

fn grad_at(stops: &[Rgb], mut t: f32) -> Rgb {
    if t < 0.0 { t = 0.0; }
    if t > 1.0 { t = 1.0; }
    let s = t * (stops.len() as f32 - 1.0);
    let i = s.floor() as usize;
    if i >= stops.len() - 1 {
        return stops[stops.len() - 1];
    }
    lerp(stops[i], stops[i + 1], s - i as f32)
}

fn paint_line(text: &str, line_t: f32) -> String {
    let chars: Vec<char> = text.chars().collect();
    let mut out = String::new();
    let len_f = chars.len() as f32;
    for (i, &c) in chars.iter().enumerate() {
        let t = if len_f > 1.0 {
            line_t * 0.5 + (i as f32 / (len_f - 1.0)) * 0.5
        } else {
            line_t
        };
        let color = grad_at(SUNSET_GRAD, t);
        out.push_str(&rgb_ansi(color));
        out.push(c);
    }
    out.push_str(RESET);
    out
}

// ─── Box Drawing ─────────────────────────────────────────────────────────────

fn box_row(content: &str, width: usize, raw_len: usize) -> String {
    let pad = if width > raw_len + 2 { width - 2 - raw_len } else { 0 };
    format!("{}│{}{}{}{}│{}", rgb_ansi(BORDER), RESET, content, " ".repeat(pad), rgb_ansi(BORDER), RESET)
}

// ─── Startup Screen ─────────────────────────────────────────────────────────────

pub fn print_startup_screen(provider: &CloudProvider, local: bool) {
    let w = 62;
    println!();
    
    // 1. Logo
    let mut all_logo = Vec::new();
    all_logo.extend_from_slice(LOGO_VERANTYX);
    
    let total = all_logo.len() as f32;
    for (i, line) in all_logo.iter().enumerate() {
        if line.is_empty() {
            println!();
        } else {
            let t = if total > 1.0 { i as f32 / (total - 1.0) } else { 0.0 };
            println!("{}", paint_line(line, t));
        }
    }
    
    println!();
    let tagline = format!("  {}✦{} {}Any model. Every tool. Zero limits.{} {}✦{}", 
        rgb_ansi(ACCENT), RESET, rgb_ansi(CREAM), RESET, rgb_ansi(ACCENT), RESET);
    println!("{}", tagline);
    println!();

    // 2. Info Box
    let (prov_name, model_alias, endpoint) = match provider {
        CloudProvider::Gemini => ("Google Gemini", "gemini-2.5-pro", "https://generativelanguage.googleapis.com"),
        CloudProvider::OpenAi => ("OpenAI", "gpt-4o", "https://api.openai.com/v1"),
        CloudProvider::Anthropic => ("Anthropic", "claude-3-5-sonnet", "https://api.anthropic.com"),
        CloudProvider::DeepSeek => ("DeepSeek", "deepseek-reasoner", "https://api.deepseek.com"),
        CloudProvider::OpenRouter => ("OpenRouter", "google/gemini-2.5-pro", "https://openrouter.ai/api/v1"),
        CloudProvider::Groq => ("Groq", "llama3-70b-8192", "https://api.groq.com/openai/v1"),
        CloudProvider::Together => ("Together AI", "meta-llama/Llama-3.3-70B", "https://api.together.xyz/v1"),
    };

    println!("{}╔{}╗{}", rgb_ansi(BORDER), "═".repeat(w - 2), RESET);

    let lbl = |k: &str, v: &str, c: Rgb| -> (String, usize) {
        let pad_k = format!("{:width$}", k, width = 9);
        let text = format!(" {}{}{}{} {}{}{}", DIM, rgb_ansi(DIMCOL), pad_k, RESET, rgb_ansi(c), v, RESET);
        let raw_len = format!(" {} {}", pad_k, v).chars().count();
        (text, raw_len)
    };

    let prov_c = if local { (130, 175, 130) } else { ACCENT };
    let (r, l) = lbl("Provider", prov_name, prov_c);
    println!("{}", box_row(&r, w, l));

    let (r, l) = lbl("Model", model_alias, CREAM);
    println!("{}", box_row(&r, w, l));

    let ep_display = if endpoint.len() > 38 { format!("{}...", &endpoint[0..35]) } else { endpoint.to_string() };
    let (r, l) = lbl("Endpoint", &ep_display, CREAM);
    println!("{}", box_row(&r, w, l));

    println!("{}╠{}╣{}", rgb_ansi(BORDER), "═".repeat(w - 2), RESET);

    let s_c = if local { (130, 175, 130) } else { ACCENT };
    let s_l = if local { "local" } else { "cloud" };
    
    let s_row = format!(" {}●{} {}{}{}{}    {}Ready — type {}Verantyx{} to begin", 
        rgb_ansi(s_c), RESET, DIM, rgb_ansi(DIMCOL), s_l, RESET, color_text("", DIMCOL), rgb_ansi(ACCENT), RESET);
    let s_len = format!(" ● {}    Ready — type Verantyx to begin", s_l).chars().count();
    println!("{}", box_row(&s_row, w, s_len));

    println!("{}╚{}╝{}", rgb_ansi(BORDER), "═".repeat(w - 2), RESET);
    println!("  {}{}verantyx {}{}{}", DIM, rgb_ansi(DIMCOL), RESET, rgb_ansi(ACCENT), "v0.1.0");
    println!();
}

// ─── Theme ───────────────────────────────────────────────────────────────────

/// Generates a perfectly matched Dialoguer Theme to fit the OpenClaude UI setup aesthetics.
pub struct OpenClaudeTheme;

impl Theme for OpenClaudeTheme {
    fn format_prompt(&self, f: &mut dyn fmt::Write, prompt: &str) -> fmt::Result {
        write!(f, "{}?{} {} ›", rgb_ansi(ACCENT), RESET, color_text(prompt, CREAM))
    }

    fn format_error(&self, f: &mut dyn fmt::Write, err: &str) -> fmt::Result {
        write!(f, "{}✖{} {}", rgb_ansi((255, 100, 100)), RESET, err)
    }

    fn format_confirm_prompt(
        &self,
        f: &mut dyn fmt::Write,
        prompt: &str,
        default: Option<bool>,
    ) -> fmt::Result {
        write!(f, "{}?{} {} ", rgb_ansi(ACCENT), RESET, color_text(prompt, CREAM))?;
        match default {
            Some(true) => write!(f, "{}Y/n{} ›", rgb_ansi(DIMCOL), RESET),
            Some(false) => write!(f, "{}y/N{} ›", rgb_ansi(DIMCOL), RESET),
            None => write!(f, "{}y/n{} ›", rgb_ansi(DIMCOL), RESET),
        }
    }

    fn format_confirm_prompt_selection(
        &self,
        f: &mut dyn fmt::Write,
        prompt: &str,
        selection: Option<bool>,
    ) -> fmt::Result {
        let text = match selection {
            Some(true) => "Yes",
            Some(false) => "No",
            None => "",
        };
        write!(f, "{}✔{} {} · {}", rgb_ansi((130, 175, 130)), RESET, color_text(prompt, DIMCOL), color_text(text, ACCENT))
    }

    fn format_input_prompt(
        &self,
        f: &mut dyn fmt::Write,
        prompt: &str,
        default: Option<&str>,
    ) -> fmt::Result {
        write!(f, "{}?{} {} ", rgb_ansi(ACCENT), RESET, color_text(prompt, CREAM))?;
        if let Some(d) = default {
            write!(f, "{}({}){} ", rgb_ansi(DIMCOL), d, RESET)?;
        }
        write!(f, "›")
    }

    fn format_input_prompt_selection(
        &self,
        f: &mut dyn fmt::Write,
        prompt: &str,
        sel: &str,
    ) -> fmt::Result {
        write!(f, "{}✔{} {} · {}", rgb_ansi((130, 175, 130)), RESET, color_text(prompt, DIMCOL), color_text(sel, ACCENT))
    }

    fn format_select_prompt(&self, f: &mut dyn fmt::Write, prompt: &str) -> fmt::Result {
        write!(f, "{}?{} {} ›", rgb_ansi(ACCENT), RESET, color_text(prompt, CREAM))
    }

    fn format_select_prompt_selection(
        &self,
        f: &mut dyn fmt::Write,
        prompt: &str,
        sel: &str,
    ) -> fmt::Result {
        write!(f, "{}✔{} {} · {}", rgb_ansi((130, 175, 130)), RESET, color_text(prompt, DIMCOL), color_text(sel, ACCENT))
    }

    fn format_select_prompt_item(
        &self,
        f: &mut dyn fmt::Write,
        text: &str,
        active: bool,
    ) -> fmt::Result {
        if active {
            write!(f, "  {}❯ {}{}", rgb_ansi(ACCENT), text, RESET)
        } else {
            write!(f, "    {}{}", color_text(text, CREAM), RESET)
        }
    }
}
