//! Phase 11: TUI Application State and Main Loop

use anyhow::Result;
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyModifiers, MouseEventKind},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style, Stylize},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Clear, Gauge, List, ListItem, ListState, Paragraph, Scrollbar,
               ScrollbarOrientation, ScrollbarState, Tabs, Wrap},
    Frame, Terminal,
};
use std::io::{self, Stdout};
use std::time::{Duration, Instant};
use std::collections::VecDeque;
use vx_js::VxRuntime;

use super::themes::Theme;

/// Application mode
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AppMode {
    /// Normal browsing
    Normal,
    /// Editing the address bar
    EditingUrl,
    /// Element selection mode
    SelectElement,
    /// Dev console
    DevConsole,
    /// Help overlay
    Help,
    /// Loading
    Loading,
}

/// A browser tab
#[derive(Debug, Clone)]
pub struct Tab {
    pub id: u32,
    pub url: String,
    pub title: String,
    pub content: String,         // Rendered markdown/text
    pub raw_html: String,
    pub interactive_elements: Vec<InteractiveElement>,
    pub console_log: Vec<ConsoleEntry>,
    pub network_log: Vec<NetworkEntry>,
    pub loading: bool,
    pub load_progress: f64,      // 0.0..=1.0
    pub error: Option<String>,
    pub secure: bool,
    pub favicon: Option<String>,
}

#[derive(Debug, Clone)]
pub struct InteractiveElement {
    pub index: usize,
    pub element_type: ElementType,
    pub label: String,
    pub href: Option<String>,
    pub action: ElementAction,
    pub ai_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ElementType {
    Link, Button, Input, Textarea, Select, Checkbox, Radio, Form, Image, Video,
}

#[derive(Debug, Clone)]
pub enum ElementAction {
    Navigate(String),
    Click,
    TypeText(String),
    Submit,
    Toggle,
}

impl ElementType {
    pub fn icon(&self) -> &'static str {
        match self {
            Self::Link => "🔗",
            Self::Button => "▶",
            Self::Input => "📝",
            Self::Textarea => "📄",
            Self::Select => "▼",
            Self::Checkbox => "☑",
            Self::Radio => "○",
            Self::Form => "📋",
            Self::Image => "🖼",
            Self::Video => "🎬",
        }
    }
}

#[derive(Debug, Clone)]
pub struct ConsoleEntry {
    pub level: ConsoleLevel,
    pub message: String,
    pub source: Option<String>,
    pub line: Option<u32>,
    pub timestamp: Instant,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ConsoleLevel { Log, Info, Warn, Error, Debug }

impl ConsoleLevel {
    pub fn icon(&self) -> &'static str {
        match self { Self::Log => "›", Self::Info => "ℹ", Self::Warn => "⚠", Self::Error => "✖", Self::Debug => "•" }
    }
    pub fn color(&self) -> Color {
        match self { Self::Log => Color::Gray, Self::Info => Color::Cyan, Self::Warn => Color::Yellow, Self::Error => Color::Red, Self::Debug => Color::DarkGray }
    }
}

#[derive(Debug, Clone)]
pub struct NetworkEntry {
    pub method: String,
    pub url: String,
    pub status: Option<u16>,
    pub size: Option<u64>,
    pub duration_ms: Option<f64>,
    pub content_type: Option<String>,
    pub cached: bool,
    pub timestamp: Instant,
}

impl NetworkEntry {
    pub fn status_color(&self) -> Color {
        match self.status {
            Some(200..=299) => Color::Green,
            Some(300..=399) => Color::Yellow,
            Some(400..=499) => Color::Red,
            Some(500..=599) => Color::Magenta,
            _ => Color::Gray,
        }
    }
}

/// Full application state
pub struct TuiState {
    pub tabs: Vec<Tab>,
    pub active_tab: usize,
    pub js_runtime: VxRuntime,
    pub mode: AppMode,
    pub url_input: String,
    pub url_cursor: usize,
    pub selected_element: Option<usize>,
    pub element_list_state: ListState,
    pub console_scroll: usize,
    pub network_scroll: usize,
    pub page_scroll: u64,
    pub page_scroll_state: ScrollbarState,
    pub console_scroll_state: ScrollbarState,
    pub page_cols: u16,
    pub history: VecDeque<String>,
    pub history_cursor: Option<usize>,
    pub theme: Theme,
    pub show_network: bool,
    pub show_elements: bool,
    pub status_message: Option<(String, Instant)>,
    pub find_query: Option<String>,
    pub find_results: Vec<usize>,     // line numbers
    pub find_current: usize,
    pub input_text: String,            // for type-into-element
    pub pending_action: Option<ElementAction>,
    pub command_palette: bool,
    pub command_input: String,
}

impl TuiState {
    pub fn new() -> Self {
        let mut list_state = ListState::default();
        list_state.select(None);
        Self {
            tabs: vec![Tab {
                id: 1,
                url: "about:blank".into(),
                title: "New Tab".into(),
                content: String::new(),
                raw_html: String::new(),
                interactive_elements: Vec::new(),
                console_log: Vec::new(),
                network_log: Vec::new(),
                loading: false,
                load_progress: 0.0,
                error: None,
                secure: false,
                favicon: None,
            }],
            active_tab: 0,
            js_runtime: VxRuntime::new().expect("Failed to initialize JS runtime"),
            mode: AppMode::Normal,
            url_input: String::new(),
            url_cursor: 0,
            selected_element: None,
            element_list_state: list_state,
            console_scroll: 0,
            network_scroll: 0,
            page_scroll: 0,
            page_scroll_state: ScrollbarState::default(),
            console_scroll_state: ScrollbarState::default(),
            page_cols: 80,
            history: VecDeque::with_capacity(1000),
            history_cursor: None,
            theme: Theme::dark(),
            show_network: false,
            show_elements: true,
            status_message: None,
            find_query: None,
            find_results: Vec::new(),
            find_current: 0,
            input_text: String::new(),
            pending_action: None,
            command_palette: false,
            command_input: String::new(),
        }
    }

    pub fn active_tab_mut(&mut self) -> &mut Tab {
        &mut self.tabs[self.active_tab]
    }

    pub fn active_tab_ref(&self) -> &Tab {
        &self.tabs[self.active_tab]
    }

    pub fn set_status(&mut self, msg: &str) {
        self.status_message = Some((msg.to_string(), Instant::now()));
    }

    pub fn new_tab(&mut self, url: &str) {
        let id = self.tabs.len() as u32 + 1;
        self.tabs.push(Tab {
            id,
            url: url.to_string(),
            title: "New Tab".into(),
            content: String::new(),
            raw_html: String::new(),
            interactive_elements: Vec::new(),
            console_log: Vec::new(),
            network_log: Vec::new(),
            loading: false,
            load_progress: 0.0,
            error: None,
            secure: url.starts_with("https"),
            favicon: None,
        });
        self.active_tab = self.tabs.len() - 1;
    }

    pub async fn navigate(&mut self, url: &str) -> Result<()> {
        let mut tab = self.active_tab_mut();
        tab.url = url.to_string();
        tab.loading = true;
        tab.load_progress = 0.1;

        let client = vx_net::HttpClient::new();
        match client.get(url).await {
            Ok(resp) => {
                let (raw_html, tab_url) = {
                    let mut tab = self.active_tab_mut();
                    tab.raw_html = resp.body.as_ref()
                        .map(|b| String::from_utf8_lossy(b).into_owned())
                        .unwrap_or_default();
                    (tab.raw_html.clone(), tab.url.clone())
                };

                // Phase 8: Load and execute scripts
                let _ = self.js_runtime.load_scripts_from_html(&raw_html, &tab_url).await;

                // --- Real 500k-Line Engine Pipeline ---
                let doc = vx_dom::Document::parse(&raw_html);
                let layout_root = vx_layout::layout_node::LayoutNode::from_dom(&doc.arena, doc.root_id)
                    .unwrap_or_else(|| vx_layout::layout_node::LayoutNode::new(doc.root_id));

                let mut ai = vx_render::ai_renderer::AiRenderer::new();
                let page = ai.render(&doc.arena, &layout_root, "Verantyx Page", &resp.url);

                let mut tab = self.active_tab_mut();
                tab.loading = false;
                tab.load_progress = 1.0;
                
                tab.title = page.title.clone();
                tab.content = page.render_markdown();
                // Map AI Elements to TUI Elements
                tab.interactive_elements = page.interactive_elements.iter().enumerate().map(|(i, e)| {
                    crate::tui::app::InteractiveElement {
                        index: i,
                        element_type: match e.element_type {
                            vx_render::ai_renderer::ElementType::Link => crate::tui::app::ElementType::Link,
                            vx_render::ai_renderer::ElementType::Button => crate::tui::app::ElementType::Button,
                            _ => crate::tui::app::ElementType::Input,
                        },
                        label: e.label.clone(),
                        href: e.href.clone(),
                        action: crate::tui::app::ElementAction::Navigate(e.href.clone().unwrap_or_default()),
                        ai_id: Some(e.id.to_string()),
                    }
                }).collect();
                tab.secure = resp.url.starts_with("https");
                
                self.history.push_back(resp.url);
                self.url_input = url.to_string();
                self.set_status(&format!("Loaded {}", url));
            }
            Err(e) => {
                let mut tab = self.active_tab_mut();
                tab.loading = false;
                tab.error = Some(e.to_string());
                self.set_status(&format!("Error loading {}: {}", url, e));
            }
        }
        Ok(())
    }
    pub fn close_tab(&mut self) {
        if self.tabs.len() > 1 {
            self.tabs.remove(self.active_tab);
            if self.active_tab >= self.tabs.len() {
                self.active_tab = self.tabs.len() - 1;
            }
        }
    }

    pub fn page_line_count(&self) -> u64 {
        self.active_tab_ref().content.lines().count() as u64
    }

    pub fn scroll_up(&mut self, amount: u64) {
        self.page_scroll = self.page_scroll.saturating_sub(amount);
    }

    pub fn scroll_down(&mut self, amount: u64) {
        let max = self.page_line_count().saturating_sub(10);
        self.page_scroll = (self.page_scroll + amount).min(max);
    }

    pub fn select_next_element(&mut self) {
        let count = self.active_tab_ref().interactive_elements.len();
        if count == 0 { return; }
        let next = match self.element_list_state.selected() {
            Some(i) => (i + 1) % count,
            None => 0,
        };
        self.element_list_state.select(Some(next));
        self.selected_element = Some(next);
    }

    pub fn select_prev_element(&mut self) {
        let count = self.active_tab_ref().interactive_elements.len();
        if count == 0 { return; }
        let prev = match self.element_list_state.selected() {
            Some(0) | None => count - 1,
            Some(i) => i - 1,
        };
        self.element_list_state.select(Some(prev));
        self.selected_element = Some(prev);
    }
}

/// The main TUI application
pub struct TuiApp {
    pub state: TuiState,
    terminal: Terminal<CrosstermBackend<Stdout>>,
    tick_rate: Duration,
    last_tick: Instant,
}

impl TuiApp {
    pub fn new() -> Result<Self> {
        enable_raw_mode()?;
        let mut stdout = io::stdout();
        execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
        let backend = CrosstermBackend::new(stdout);
        let terminal = Terminal::new(backend)?;

        Ok(Self {
            state: TuiState::new(),
            terminal,
            tick_rate: Duration::from_millis(50),
            last_tick: Instant::now(),
        })
    }

    pub fn cleanup(&mut self) -> Result<()> {
        disable_raw_mode()?;
        execute!(
            self.terminal.backend_mut(),
            LeaveAlternateScreen,
            DisableMouseCapture
        )?;
        self.terminal.show_cursor()?;
        Ok(())
    }

    /// Run the main event loop
    pub async fn run(&mut self) -> Result<()> {
        loop {
            // Draw
            self.terminal.draw(|f| Self::render(f, &mut self.state))?;

            // Handle input
            let timeout = self.tick_rate
                .checked_sub(self.last_tick.elapsed())
                .unwrap_or(Duration::ZERO);

            if event::poll(timeout)? {
                match event::read()? {
                    Event::Key(key) => {
                        if Self::handle_key(&mut self.state, key).await? {
                            break; // Quit signal
                        }
                    }
                    Event::Mouse(mouse) => {
                        Self::handle_mouse(&mut self.state, mouse);
                    }
                    Event::Resize(w, h) => {
                        self.state.page_cols = w;
                    }
                    _ => {}
                }
            }

            // Tick
            if self.last_tick.elapsed() >= self.tick_rate {
                self.last_tick = Instant::now();
                Self::on_tick(&mut self.state);
            }
        }
        Ok(())
    }

    fn on_tick(state: &mut TuiState) {
        // Clear expired status messages (3 second timeout)
        if let Some((_, ts)) = &state.status_message {
            if ts.elapsed() > Duration::from_secs(3) {
                state.status_message = None;
            }
        }

        // Simulate load progress
        for tab in &mut state.tabs {
            if tab.loading && tab.load_progress < 1.0 {
                tab.load_progress = (tab.load_progress + 0.05).min(0.95);
            }
        }
    }

    async fn handle_key(state: &mut TuiState, key: crossterm::event::KeyEvent) -> Result<bool> {
        use KeyCode::*;
        use KeyModifiers as Mod;

        match state.mode {
            AppMode::Normal => {
                match (key.modifiers, key.code) {
                    // Quit
                    (Mod::CONTROL, Char('c')) | (Mod::NONE, Char('q')) => return Ok(true),
                    // Open URL bar
                    (Mod::CONTROL, Char('l')) | (Mod::NONE, Char('o')) => {
                        state.url_input = state.active_tab_ref().url.clone();
                        state.url_cursor = state.url_input.len();
                        state.mode = AppMode::EditingUrl;
                    }
                    // New tab
                    (Mod::CONTROL, Char('t')) => {
                        state.new_tab("about:blank");
                        state.set_status("New tab opened");
                    }
                    // Close tab
                    (Mod::CONTROL, Char('w')) => {
                        state.close_tab();
                    }
                    // Navigate tabs
                    (Mod::CONTROL, Tab) | (Mod::NONE, Char(']')) => {
                        let n = state.tabs.len();
                        state.active_tab = (state.active_tab + 1) % n;
                    }
                    (Mod::CONTROL | Mod::SHIFT, Tab) | (Mod::NONE, Char('[')) => {
                        let n = state.tabs.len();
                        state.active_tab = (state.active_tab + n - 1) % n;
                    }
                    // Scroll
                    (Mod::NONE, Down) | (Mod::NONE, Char('j')) => state.scroll_down(1),
                    (Mod::NONE, Up) | (Mod::NONE, Char('k')) => state.scroll_up(1),
                    (Mod::NONE, PageDown) | (Mod::NONE, Char('f')) => state.scroll_down(20),
                    (Mod::NONE, PageUp) | (Mod::NONE, Char('b')) => state.scroll_up(20),
                    (Mod::NONE, Home) | (Mod::NONE, Char('g')) => state.page_scroll = 0,
                    (Mod::NONE, End) | (Mod::SHIFT, Char('G')) => {
                        state.page_scroll = state.page_line_count();
                    }
                    // Element selection
                    (Mod::NONE, Tab) => state.select_next_element(),
                    (Mod::SHIFT, BackTab) => state.select_prev_element(),
                    // Enter selected element
                    (Mod::NONE, Enter) => {
                        if let Some(idx) = state.selected_element {
                            let elem = state.active_tab_ref().interactive_elements.get(idx).cloned();
                            if let Some(e) = elem {
                                match &e.action {
                                    ElementAction::Navigate(url) => {
                                        let url = url.clone();
                                        state.set_status(&format!("Navigating to {}", url));
                                        state.active_tab_mut().url = url;
                                        state.active_tab_mut().loading = true;
                                        state.active_tab_mut().load_progress = 0.0;
                                    }
                                    ElementAction::Click => state.set_status("Clicked"),
                                    ElementAction::Submit => state.set_status("Form submitted"),
                                    _ => {}
                                }
                            }
                        }
                    }
                    // Toggle panels
                    (Mod::NONE, Char('e')) => state.show_elements = !state.show_elements,
                    (Mod::NONE, Char('n')) => state.show_network = !state.show_network,
                    // Dev console
                    (Mod::NONE, Char('d')) | (Mod::NONE, F(12)) => {
                        state.mode = AppMode::DevConsole;
                    }
                    // Help
                    (Mod::NONE, Char('?')) | (Mod::NONE, F(1)) => {
                        state.mode = AppMode::Help;
                    }
                    // Reload
                    (Mod::NONE, Char('r')) | (Mod::NONE, F(5)) => {
                        state.active_tab_mut().loading = true;
                        state.active_tab_mut().load_progress = 0.0;
                        state.set_status("Reloading...");
                    }
                    _ => {}
                }
            }

            AppMode::EditingUrl => {
                match key.code {
                    Enter => {
                        let url = state.url_input.clone();
                        let url = if url.starts_with("http") { url } else { format!("https://{}", url) };
                        state.active_tab_mut().url = url.clone();
                        state.active_tab_mut().loading = true;
                        state.active_tab_mut().load_progress = 0.0;
                        state.history.push_front(url.clone());
                        state.set_status(&format!("Loading {}", url));
                        state.mode = AppMode::Normal;
                    }
                    Esc => { state.mode = AppMode::Normal; }
                    Backspace => {
                        if state.url_cursor > 0 {
                            state.url_cursor -= 1;
                            state.url_input.remove(state.url_cursor);
                        }
                    }
                    Delete => {
                        if state.url_cursor < state.url_input.len() {
                            state.url_input.remove(state.url_cursor);
                        }
                    }
                    Left => {
                        if state.url_cursor > 0 { state.url_cursor -= 1; }
                    }
                    Right => {
                        if state.url_cursor < state.url_input.len() { state.url_cursor += 1; }
                    }
                    Home => state.url_cursor = 0,
                    End => state.url_cursor = state.url_input.len(),
                    Char(c) => {
                        state.url_input.insert(state.url_cursor, c);
                        state.url_cursor += 1;
                    }
                    _ => {}
                }
            }

            AppMode::DevConsole | AppMode::Help => {
                match key.code {
                    Esc | KeyCode::Char('q') | KeyCode::F(12) | KeyCode::F(1) => {
                        state.mode = AppMode::Normal;
                    }
                    KeyCode::Down | KeyCode::Char('j') => state.console_scroll += 1,
                    KeyCode::Up | KeyCode::Char('k') => {
                        state.console_scroll = state.console_scroll.saturating_sub(1);
                    }
                    _ => {}
                }
            }

            _ => {
                if key.code == KeyCode::Esc {
                    state.mode = AppMode::Normal;
                }
            }
        }

        Ok(false)
    }

    fn handle_mouse(state: &mut TuiState, mouse: crossterm::event::MouseEvent) {
        match mouse.kind {
            MouseEventKind::ScrollDown => state.scroll_down(3),
            MouseEventKind::ScrollUp => state.scroll_up(3),
            MouseEventKind::Down(_) => {
                // click handling (simplified: captured for future use)
                let _ = (mouse.column, mouse.row);
            }
            _ => {}
        }
    }

    /// Main render function
    fn render(f: &mut Frame, state: &mut TuiState) {
        let theme = &state.theme;
        let area = f.area();

        // Outer layout
        let main_chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1),   // Tab bar
                Constraint::Length(3),   // Address bar
                Constraint::Min(8),      // Main content
                Constraint::Length(1),   // Status bar
            ])
            .split(area);

        // === Tab bar ===
        {
            let tab_titles: Vec<Line> = state.tabs.iter().map(|t| {
                let title = if t.title.len() > 18 {
                    format!("{}…", &t.title[..17])
                } else {
                    t.title.clone()
                };
                let icon = if t.secure { "🔒 " } else { "   " };
                if t.loading {
                    Line::from(format!("⟳ {}", title)).style(theme.loading_style)
                } else {
                    Line::from(format!("{}{}", icon, title))
                }
            }).collect();

            let tabs = Tabs::new(tab_titles)
                .select(state.active_tab)
                .style(theme.tab_inactive)
                .highlight_style(theme.tab_active)
                .divider("│");
            f.render_widget(tabs, main_chunks[0]);
        }

        // === Address bar ===
        {
            let tab = state.active_tab_ref();
            let (url_text, url_style) = if state.mode == AppMode::EditingUrl {
                let mut text = state.url_input.clone();
                (text, theme.address_editing)
            } else {
                let icon = if tab.secure { "🔒  " } else { "⚠   " };
                (format!("{}{}", icon, tab.url), theme.address_normal)
            };

            let progress_indicator = if tab.loading {
                format!(" ⟳ {:.0}%", tab.load_progress * 100.0)
            } else {
                String::new()
            };

            let block = Block::default()
                .borders(Borders::ALL)
                .title(format!(" Address{} ", progress_indicator))
                .border_style(if state.mode == AppMode::EditingUrl { theme.focused_border } else { theme.border_style });

            let input = Paragraph::new(url_text)
                .block(block)
                .style(url_style);
            f.render_widget(input, main_chunks[1]);

            // Show cursor in edit mode
            if state.mode == AppMode::EditingUrl {
                f.set_cursor_position((
                    main_chunks[1].x + state.url_cursor as u16 + 1,
                    main_chunks[1].y + 1,
                ));
            }

            // Loading progress bar
            if tab.loading {
                let progress_area = Rect {
                    x: main_chunks[1].x + 1,
                    y: main_chunks[1].y + 2,
                    width: (main_chunks[1].width.saturating_sub(2) as f64 * tab.load_progress) as u16,
                    height: 1,
                };
                let gauge_area = Rect {
                    x: main_chunks[1].x + 1,
                    y: main_chunks[1].y + 2,
                    width: main_chunks[1].width.saturating_sub(2),
                    height: 1,
                };
                let gauge = Gauge::default()
                    .gauge_style(theme.progress_style)
                    .ratio(tab.load_progress);
                f.render_widget(gauge, gauge_area);
            }
        }

        // === Main content area ===
        let content_area = main_chunks[2];
        let show_right_panel = state.show_elements && !state.active_tab_ref().interactive_elements.is_empty();

        let content_chunks = if show_right_panel {
            Layout::default()
                .direction(Direction::Horizontal)
                .constraints([Constraint::Min(40), Constraint::Length(38)])
                .split(content_area)
        } else {
            Layout::default()
                .direction(Direction::Horizontal)
                .constraints([Constraint::Percentage(100)])
                .split(content_area)
        };

        // Left content: Page view (upper) + Dev panel (lower)
        let show_dev = state.mode == AppMode::DevConsole;
        let left_chunks = if show_dev {
            Layout::default()
                .direction(Direction::Vertical)
                .constraints([Constraint::Min(6), Constraint::Length(12)])
                .split(content_chunks[0])
        } else {
            Layout::default()
                .direction(Direction::Vertical)
                .constraints([Constraint::Percentage(100)])
                .split(content_chunks[0])
        };

        // === Page view ===
        {
            let tab = state.active_tab_ref();
            let content = if let Some(err) = &tab.error {
                format!("⚠ Error loading page\n\n{}", err)
            } else if tab.content.is_empty() && !tab.loading {
                "Press 'o' or Ctrl+L to enter a URL".to_string()
            } else {
                tab.content.clone()
            };

            let lines: Vec<Line> = content.lines()
                .skip(state.page_scroll as usize)
                .take(left_chunks[0].height as usize)
                .map(|line| Self::render_markdown_line(line, theme))
                .collect();

            let text = Text::from(lines);
            let block = Block::default()
                .borders(Borders::ALL)
                .title(format!(" 📄 {} ", tab.title.as_str()))
                .border_style(theme.border_style);

            let paragraph = Paragraph::new(text)
                .block(block)
                .wrap(Wrap { trim: false });
            f.render_widget(paragraph, left_chunks[0]);

            // Scrollbar
            let total_lines = state.page_line_count();
            let visible = left_chunks[0].height as u64;
            if total_lines > visible {
                let mut scroll_state = ScrollbarState::new(total_lines as usize)
                    .position(state.page_scroll as usize);
                let scrollbar = Scrollbar::default()
                    .orientation(ScrollbarOrientation::VerticalRight)
                    .begin_symbol(None)
                    .end_symbol(None);
                f.render_stateful_widget(scrollbar, left_chunks[0], &mut scroll_state);
            }
        }

        // === Dev panel ===
        if show_dev && left_chunks.len() > 1 {
            let tab = state.active_tab_ref();
            let net_visible = state.show_network;

            let dev_chunks = if net_visible {
                Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
                    .split(left_chunks[1])
            } else {
                Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([Constraint::Percentage(100)])
                    .split(left_chunks[1])
            };

            // Console log
            {
                let items: Vec<ListItem> = tab.console_log.iter()
                    .skip(state.console_scroll)
                    .take(dev_chunks[0].height as usize)
                    .map(|entry| {
                        let icon = entry.level.icon();
                        let msg = format!("{} {}", icon, &entry.message[..entry.message.len().min(80)]);
                        ListItem::new(msg).style(Style::default().fg(entry.level.color()))
                    }).collect();

                let console = List::new(items)
                    .block(Block::default()
                        .borders(Borders::ALL)
                        .title(" 🖥 Console ")
                        .border_style(theme.border_style));
                f.render_widget(console, dev_chunks[0]);
            }

            // Network log
            if net_visible && dev_chunks.len() > 1 {
                let items: Vec<ListItem> = tab.network_log.iter()
                    .rev()
                    .take(dev_chunks[1].height as usize)
                    .map(|entry| {
                        let status_str = entry.status.map(|s| s.to_string()).unwrap_or("-".into());
                        let msg = format!("{} {} {}", entry.method, status_str, &entry.url[..entry.url.len().min(30)]);
                        ListItem::new(msg).style(Style::default().fg(entry.status_color()))
                    }).collect();

                let network = List::new(items)
                    .block(Block::default()
                        .borders(Borders::ALL)
                        .title(" 🌐 Network ")
                        .border_style(theme.border_style));
                f.render_widget(network, dev_chunks[1]);
            }
        }

        // === Elements panel ===
        if show_right_panel {
            let panel_area = content_chunks[1];
            let tab = state.active_tab_ref();

            let items: Vec<ListItem> = tab.interactive_elements.iter().enumerate().map(|(i, elem)| {
                let label = if elem.label.len() > 25 {
                    format!("{}…", &elem.label[..24])
                } else {
                    elem.label.clone()
                };
                let text = format!("[{}] {} {}", i + 1, elem.element_type.icon(), label);
                if Some(i) == state.selected_element {
                    ListItem::new(text).style(theme.selected_element)
                } else {
                    ListItem::new(text).style(theme.element_normal)
                }
            }).collect();

            let block = Block::default()
                .borders(Borders::ALL)
                .title(" ⚡ Elements ")
                .border_style(theme.border_style);

            let mut list_state = state.element_list_state.clone();
            f.render_stateful_widget(List::new(items).block(block).highlight_style(theme.selected_element), panel_area, &mut list_state);
        }

        // === Status bar ===
        {
            let status_text = if let Some((msg, _)) = &state.status_message {
                msg.clone()
            } else {
                let tab = state.active_tab_ref();
                let element_hint = if tab.interactive_elements.is_empty() {
                    String::new()
                } else {
                    format!(" | {} elements", tab.interactive_elements.len())
                };
                let mode_hint = match state.mode {
                    AppMode::Normal => "q:quit o:url e:elements d:console ?:help",
                    AppMode::EditingUrl => "Enter:navigate Esc:cancel",
                    AppMode::DevConsole => "Esc:close j/k:scroll n:network",
                    AppMode::Help => "Esc:close",
                    _ => "",
                };
                format!("[{}] {}{} │ {}", state.active_tab + 1, tab.url.as_str(), element_hint, mode_hint)
            };

            let status = Paragraph::new(status_text)
                .style(theme.status_bar);
            f.render_widget(status, main_chunks[3]);
        }

        // === Help overlay ===
        if state.mode == AppMode::Help {
            let popup_area = Self::centered_rect(70, 80, area);
            f.render_widget(Clear, popup_area);
            let help_text = vec![
                Line::from(" vx-browser — Keyboard Shortcuts ").bold().centered(),
                Line::from(""),
                Line::from("Navigation").bold().style(Style::default().fg(Color::Cyan)),
                Line::from("  o / Ctrl+L   Open URL bar"),
                Line::from("  Ctrl+T       New tab"),
                Line::from("  Ctrl+W       Close tab"),
                Line::from("  ]  [         Switch tabs"),
                Line::from(""),
                Line::from("Scrolling").bold().style(Style::default().fg(Color::Cyan)),
                Line::from("  j/k / ↑↓     Scroll line"),
                Line::from("  f/b / PgDn   Scroll page"),
                Line::from("  g / Home     Top of page"),
                Line::from("  G / End      Bottom of page"),
                Line::from(""),
                Line::from("Elements").bold().style(Style::default().fg(Color::Cyan)),
                Line::from("  Tab          Next element"),
                Line::from("  Shift+Tab    Prev element"),
                Line::from("  Enter        Activate element"),
                Line::from("  e            Toggle element panel"),
                Line::from(""),
                Line::from("Dev Tools").bold().style(Style::default().fg(Color::Cyan)),
                Line::from("  d / F12      Toggle DevConsole"),
                Line::from("  n            Toggle Network log"),
                Line::from("  r / F5       Reload page"),
                Line::from(""),
                Line::from("  q / Ctrl+C   Quit │ ? / F1  This help"),
            ];
            let help = Paragraph::new(help_text)
                .block(Block::default()
                    .borders(Borders::ALL)
                    .title(" Help — Press Esc to close ")
                    .border_style(Style::default().fg(Color::LightCyan)))
                .wrap(Wrap { trim: false });
            f.render_widget(help, popup_area);
        }
    }

    /// Render a Markdown-style line with inline formatting
    fn render_markdown_line<'a>(line: &'a str, theme: &'a Theme) -> Line<'a> {
        // H1
        if line.starts_with("# ") {
            return Line::from(
                Span::styled(&line[2..], Style::default().fg(theme.h1_color).add_modifier(Modifier::BOLD))
            );
        }
        // H2
        if line.starts_with("## ") {
            return Line::from(
                Span::styled(&line[3..], Style::default().fg(theme.h2_color).add_modifier(Modifier::BOLD))
            );
        }
        // H3
        if line.starts_with("### ") {
            return Line::from(
                Span::styled(&line[4..], Style::default().fg(theme.h3_color).add_modifier(Modifier::BOLD))
            );
        }
        // Code block
        if line.starts_with("    ") || line.starts_with('\t') {
            return Line::from(
                Span::styled(line, Style::default().fg(Color::Green).bg(Color::DarkGray))
            );
        }
        // Horizontal rule
        if line.starts_with("---") || line.starts_with("===") {
            return Line::from(Span::styled("─".repeat(80), Style::default().fg(Color::DarkGray)));
        }
        // Link
        if line.contains("[") && line.contains("](") {
            return Line::from(
                Span::styled(line, Style::default().fg(Color::Blue).add_modifier(Modifier::UNDERLINED))
            );
        }
        // List item
        if line.starts_with("- ") || line.starts_with("* ") || line.starts_with("+ ") {
            let mut spans = vec![Span::styled("  • ", Style::default().fg(theme.bullet_color))];
            spans.push(Span::raw(&line[2..]));
            return Line::from(spans);
        }
        // Bold/italic (simplified)
        if line.contains("**") || line.contains("__") {
            return Line::from(
                Span::styled(line, Style::default().add_modifier(Modifier::BOLD))
            );
        }
        // Default
        Line::from(Span::raw(line))
    }

    fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
        let popup_layout = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Percentage((100 - percent_y) / 2),
                Constraint::Percentage(percent_y),
                Constraint::Percentage((100 - percent_y) / 2),
            ])
            .split(area);

        Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage((100 - percent_x) / 2),
                Constraint::Percentage(percent_x),
                Constraint::Percentage((100 - percent_x) / 2),
            ])
            .split(popup_layout[1])[1]
    }
}

impl Drop for TuiApp {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
}
