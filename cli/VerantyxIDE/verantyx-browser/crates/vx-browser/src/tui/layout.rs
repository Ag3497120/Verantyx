use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    widgets::{Block, Borders, Clear, Paragraph, Tabs, List, ListItem, Gauge},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
};
use crate::tui::app::{TuiApp, TuiState, AppMode};

/// TUI Layout Engine — Responsible for the "Verantyx Aesthetics"
pub struct TuiLayout;

impl TuiLayout {
    pub fn render(f: &mut ratatui::Frame, app: &mut TuiApp) {
        let area = f.area();
        let state = &mut app.state;
        let theme = &state.theme;

        // Main Layout: [Tabs] [Address] [Content] [Status]
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1), // Tabs
                Constraint::Length(3), // Address Bar
                Constraint::Min(10),   // Content
                Constraint::Length(1), // Status
            ])
            .split(area);

        Self::render_tabs(f, chunks[0], state);
        Self::render_address_bar(f, chunks[1], state);
        
        // Interactive Middle: [Page] [Dev/Elements]
        let middle_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(70),
                Constraint::Percentage(30),
            ])
            .split(chunks[2]);

        Self::render_page_view(f, middle_chunks[0], state);
        Self::render_side_panel(f, middle_chunks[1], state);

        Self::render_status_bar(f, chunks[3], state);

        // Overlays
        if state.mode == AppMode::Help {
            Self::render_help_overlay(f, area);
        }
    }

    fn render_tabs(f: &mut ratatui::Frame, area: Rect, state: &TuiState) {
        let titles: Vec<Line> = state.tabs.iter().enumerate().map(|(i, t)| {
            let style = if i == state.active_tab {
                Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(Color::Gray)
            };
            Line::from(vec![
                Span::styled(format!(" {} ", i + 1), style),
                Span::styled(&t.title, style),
            ])
        }).collect();

        let tabs = Tabs::new(titles)
            .select(state.active_tab)
            .divider(Span::raw("│"))
            .style(Style::default().bg(Color::Rgb(15, 15, 20)));
        f.render_widget(tabs, area);
    }

    fn render_address_bar(f: &mut ratatui::Frame, area: Rect, state: &TuiState) {
        let tab = state.active_tab_ref();
        let is_editing = state.mode == AppMode::EditingUrl;
        
        let border_color = if is_editing { Color::Yellow } else { Color::DarkGray };
        let text = if is_editing { &state.url_input } else { &tab.url };
        
        let content = Line::from(vec![
            Span::styled(if tab.secure { " 🔒 " } else { " 🌐 " }, Style::default().fg(Color::Green)),
            Span::styled(text, Style::default().fg(Color::White)),
        ]);

        let p = Paragraph::new(content)
            .block(Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(border_color))
                .title(" Address Bar "));
        
        f.render_widget(p, area);

        if tab.loading {
            let gauge_area = Rect { x: area.x + 2, y: area.y + 2, width: area.width - 4, height: 1 };
            let gauge = Gauge::default()
                .gauge_style(Style::default().fg(Color::Cyan).bg(Color::DarkGray))
                .ratio(tab.load_progress);
            f.render_widget(gauge, gauge_area);
        }
    }

    fn render_page_view(f: &mut ratatui::Frame, area: Rect, state: &TuiState) {
        let tab = state.active_tab_ref();
        
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::DarkGray))
            .title(format!(" {} ", tab.title));

        let p = Paragraph::new(tab.content.clone())
            .block(block)
            .scroll((state.page_scroll as u16, 0));
        
        f.render_widget(p, area);
    }

    fn render_side_panel(f: &mut ratatui::Frame, area: Rect, state: &mut TuiState) {
        let tab = state.active_tab_ref();
        
        let items: Vec<ListItem> = tab.interactive_elements.iter().enumerate().map(|(i, el)| {
            let style = if Some(i) == state.selected_element {
                Style::default().bg(Color::Rgb(40, 40, 60)).fg(Color::Cyan)
            } else {
                Style::default().fg(Color::Gray)
            };
            ListItem::new(format!("[{}] {} {}", i + 1, el.element_type.icon(), el.label)).style(style)
        }).collect();

        let list = List::new(items)
            .block(Block::default()
                .title(" Interactive Elements ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)));
        
        f.render_stateful_widget(list, area, &mut state.element_list_state);
    }

    fn render_status_bar(f: &mut ratatui::Frame, area: Rect, state: &TuiState) {
        let msg = state.status_message.as_ref().map(|(m, _)| m.as_str()).unwrap_or("Ready");
        let content = Line::from(vec![
            Span::styled(" [Verantyx] ", Style::default().bg(Color::Cyan).fg(Color::Black).add_modifier(Modifier::BOLD)),
            Span::styled(format!("  {}  ", msg), Style::default()),
            Span::styled("  [q]Quit [o]Goto [Tab]ScrollElements [?]Help ", Style::default().fg(Color::DarkGray)),
        ]);
        f.render_widget(Paragraph::new(content).style(Style::default().bg(Color::Rgb(20, 20, 25))), area);
    }

    fn render_help_overlay(f: &mut ratatui::Frame, area: Rect) {
        let block = Block::default()
            .title(" Help / Shortcuts ")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan));
        
        let text = Text::from(vec![
            Line::from("  q          - Quit"),
            Line::from("  o / Ctrl+L - Open URL Bar"),
            Line::from("  Tab        - Select Next Element"),
            Line::from("  Enter      - Click/Activate Element"),
            Line::from("  j/k        - Scroll Page"),
            Line::from("  r          - Reload"),
            Line::from("  [ / ]      - Previous/Next Tab"),
            Line::from(""),
            Line::from("  Wait for AI agent to browse for you..."),
        ]);

        let p = Paragraph::new(text).block(block);
        
        let popup_area = Rect {
            x: area.width / 4,
            y: area.height / 4,
            width: area.width / 2,
            height: area.height / 2,
        };
        
        f.render_widget(Clear, popup_area);
        f.render_widget(p, popup_area);
    }
}
