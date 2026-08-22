//! TUI color themes
use ratatui::style::{Color, Modifier, Style};

/// Application color theme
#[derive(Debug, Clone)]
pub struct Theme {
    pub name: String,

    // Text colors
    pub h1_color: Color,
    pub h2_color: Color,
    pub h3_color: Color,
    pub bullet_color: Color,
    pub link_color: Color,
    pub code_color: Color,

    // UI element styles
    pub tab_active: Style,
    pub tab_inactive: Style,
    pub address_normal: Style,
    pub address_editing: Style,
    pub border_style: Style,
    pub focused_border: Style,
    pub status_bar: Style,
    pub loading_style: Style,
    pub progress_style: Style,

    // Element panel
    pub selected_element: Style,
    pub element_normal: Style,

    // Background
    pub bg: Color,
    pub fg: Color,
}

impl Theme {
    pub fn dark() -> Self {
        Self {
            name: "dark".to_string(),
            h1_color: Color::Rgb(100, 200, 255),
            h2_color: Color::Rgb(80, 180, 220),
            h3_color: Color::Rgb(60, 160, 200),
            bullet_color: Color::Rgb(150, 150, 200),
            link_color: Color::Rgb(80, 150, 255),
            code_color: Color::Rgb(150, 255, 150),
            tab_active: Style::default()
                .fg(Color::Rgb(255, 220, 100))
                .bg(Color::Rgb(40, 40, 60))
                .add_modifier(Modifier::BOLD),
            tab_inactive: Style::default()
                .fg(Color::Rgb(140, 140, 160))
                .bg(Color::Rgb(25, 25, 35)),
            address_normal: Style::default()
                .fg(Color::Rgb(220, 220, 240))
                .bg(Color::Rgb(30, 30, 45)),
            address_editing: Style::default()
                .fg(Color::White)
                .bg(Color::Rgb(40, 40, 70))
                .add_modifier(Modifier::BOLD),
            border_style: Style::default().fg(Color::Rgb(60, 60, 90)),
            focused_border: Style::default()
                .fg(Color::Rgb(100, 180, 255))
                .add_modifier(Modifier::BOLD),
            status_bar: Style::default()
                .fg(Color::Rgb(120, 120, 150))
                .bg(Color::Rgb(20, 20, 30)),
            loading_style: Style::default()
                .fg(Color::Rgb(255, 200, 50))
                .add_modifier(Modifier::SLOW_BLINK),
            progress_style: Style::default()
                .fg(Color::Rgb(50, 200, 100))
                .bg(Color::Rgb(30, 80, 50)),
            selected_element: Style::default()
                .fg(Color::Black)
                .bg(Color::Rgb(100, 200, 255))
                .add_modifier(Modifier::BOLD),
            element_normal: Style::default()
                .fg(Color::Rgb(180, 200, 230)),
            bg: Color::Rgb(15, 15, 25),
            fg: Color::Rgb(220, 220, 240),
        }
    }

    pub fn light() -> Self {
        Self {
            name: "light".to_string(),
            h1_color: Color::Rgb(0, 80, 160),
            h2_color: Color::Rgb(0, 100, 180),
            h3_color: Color::Rgb(20, 120, 200),
            bullet_color: Color::Rgb(100, 100, 150),
            link_color: Color::Rgb(0, 80, 200),
            code_color: Color::Rgb(0, 130, 0),
            tab_active: Style::default()
                .fg(Color::Rgb(0, 0, 200))
                .bg(Color::White)
                .add_modifier(Modifier::BOLD),
            tab_inactive: Style::default()
                .fg(Color::Rgb(100, 100, 120))
                .bg(Color::Rgb(230, 230, 240)),
            address_normal: Style::default()
                .fg(Color::Rgb(30, 30, 50))
                .bg(Color::White),
            address_editing: Style::default()
                .fg(Color::Black)
                .bg(Color::Rgb(240, 240, 255))
                .add_modifier(Modifier::BOLD),
            border_style: Style::default().fg(Color::Rgb(180, 180, 200)),
            focused_border: Style::default()
                .fg(Color::Rgb(0, 100, 200))
                .add_modifier(Modifier::BOLD),
            status_bar: Style::default()
                .fg(Color::Rgb(80, 80, 100))
                .bg(Color::Rgb(220, 220, 230)),
            loading_style: Style::default().fg(Color::Rgb(200, 150, 0)),
            progress_style: Style::default()
                .fg(Color::Rgb(0, 150, 80))
                .bg(Color::Rgb(180, 230, 200)),
            selected_element: Style::default()
                .fg(Color::White)
                .bg(Color::Rgb(0, 100, 200))
                .add_modifier(Modifier::BOLD),
            element_normal: Style::default().fg(Color::Rgb(50, 50, 80)),
            bg: Color::White,
            fg: Color::Rgb(20, 20, 40),
        }
    }

    pub fn nord() -> Self {
        Self {
            name: "nord".to_string(),
            h1_color: Color::Rgb(136, 192, 208),  // Nord 8
            h2_color: Color::Rgb(129, 161, 193),  // Nord 9
            h3_color: Color::Rgb(94, 129, 172),   // Nord 10
            bullet_color: Color::Rgb(148, 165, 189), // Nord 4
            link_color: Color::Rgb(94, 129, 172),
            code_color: Color::Rgb(163, 190, 140), // Nord 14
            tab_active: Style::default()
                .fg(Color::Rgb(236, 239, 244))
                .bg(Color::Rgb(46, 52, 64))
                .add_modifier(Modifier::BOLD),
            tab_inactive: Style::default()
                .fg(Color::Rgb(76, 86, 106))
                .bg(Color::Rgb(36, 42, 54)),
            address_normal: Style::default()
                .fg(Color::Rgb(216, 222, 233))
                .bg(Color::Rgb(46, 52, 64)),
            address_editing: Style::default()
                .fg(Color::Rgb(236, 239, 244))
                .bg(Color::Rgb(59, 66, 82))
                .add_modifier(Modifier::BOLD),
            border_style: Style::default().fg(Color::Rgb(67, 76, 94)),
            focused_border: Style::default()
                .fg(Color::Rgb(136, 192, 208))
                .add_modifier(Modifier::BOLD),
            status_bar: Style::default()
                .fg(Color::Rgb(76, 86, 106))
                .bg(Color::Rgb(36, 42, 54)),
            loading_style: Style::default().fg(Color::Rgb(235, 203, 139)),
            progress_style: Style::default()
                .fg(Color::Rgb(163, 190, 140))
                .bg(Color::Rgb(59, 66, 82)),
            selected_element: Style::default()
                .fg(Color::Rgb(46, 52, 64))
                .bg(Color::Rgb(136, 192, 208))
                .add_modifier(Modifier::BOLD),
            element_normal: Style::default().fg(Color::Rgb(216, 222, 233)),
            bg: Color::Rgb(46, 52, 64),
            fg: Color::Rgb(236, 239, 244),
        }
    }
}
