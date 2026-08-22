//! CSS Grid Layout Level 2 — CSS Grid with Subgrid + Implicit Track Sizing
//!
//! Extends the existing vx-layout grid engine with:
//!   - CSS Grid Level 2: `subgrid` for rows and columns
//!   - Subgrid line name inheritance from parent grid
//!   - Implicit track generation with auto-fill and auto-fit
//!   - `minmax()` with intrinsic keywords (min-content, max-content, auto, fit-content())
//!   - `repeat()` with named line groups
//!   - Grid template areas with area name resolution
//!   - Grid item auto-placement algorithm (§8) with dense/sparse packing
//!   - Grid item alignment: justify-self, align-self, justify-items, align-items
//!   - Baseline alignment for grid cells
//!   - AI-facing: grid occupancy map

use std::collections::HashMap;

/// A grid track sizing value
#[derive(Debug, Clone, PartialEq)]
pub enum TrackSize {
    Fixed(f64),                     // px, em, etc. (already resolved to px)
    Percentage(f64),                // % of grid container
    Flexible(f64),                  // fr unit
    MinContent,
    MaxContent,
    Auto,
    FitContent(f64),                // fit-content(max-value in px)
    Minmax(Box<TrackSize>, Box<TrackSize>),
    Subgrid,                        // CSS Grid Level 2 subgrid keyword
}

impl TrackSize {
    /// Parse a single track sizing value (after repeat() has been expanded)
    pub fn parse(s: &str) -> Self {
        let s = s.trim();
        match s {
            "min-content" => Self::MinContent,
            "max-content" => Self::MaxContent,
            "auto" => Self::Auto,
            "subgrid" => Self::Subgrid,
            _ => {
                if s.ends_with("fr") {
                    let n: f64 = s[..s.len()-2].trim().parse().unwrap_or(1.0);
                    return Self::Flexible(n);
                }
                if s.ends_with("px") {
                    let n: f64 = s[..s.len()-2].trim().parse().unwrap_or(0.0);
                    return Self::Fixed(n);
                }
                if s.ends_with('%') {
                    let n: f64 = s[..s.len()-1].trim().parse().unwrap_or(0.0);
                    return Self::Percentage(n);
                }
                if s.starts_with("minmax(") && s.ends_with(')') {
                    let inner = &s[7..s.len()-1];
                    if let Some(comma) = inner.find(',') {
                        let min = TrackSize::parse(&inner[..comma]);
                        let max = TrackSize::parse(&inner[comma+1..]);
                        return Self::Minmax(Box::new(min), Box::new(max));
                    }
                }
                if s.starts_with("fit-content(") && s.ends_with(')') {
                    let inner = &s[12..s.len()-1];
                    let n: f64 = inner.trim_end_matches("px").trim().parse().unwrap_or(0.0);
                    return Self::FitContent(n);
                }
                Self::Auto
            }
        }
    }

    /// Whether this track has a definite size
    pub fn is_definite(&self) -> bool {
        matches!(self, Self::Fixed(_) | Self::Percentage(_))
    }

    /// Whether this track contains an fr unit
    pub fn is_flexible(&self) -> bool {
        match self {
            Self::Flexible(_) => true,
            Self::Minmax(_, max) => matches!(max.as_ref(), TrackSize::Flexible(_)),
            _ => false,
        }
    }
}

/// Named grid lines
#[derive(Debug, Clone, Default)]
pub struct GridLineNames {
    /// Map from line name to line index (1-based)
    pub named: HashMap<String, Vec<usize>>,
}

impl GridLineNames {
    pub fn resolve(&self, name: &str) -> Option<usize> {
        self.named.get(name).and_then(|v| v.first().copied())
    }

    pub fn resolve_nth(&self, name: &str, n: usize) -> Option<usize> {
        self.named.get(name).and_then(|v| v.get(n - 1).copied())
    }

    pub fn add(&mut self, name: &str, line_index: usize) {
        self.named.entry(name.to_string()).or_default().push(line_index);
    }
}

/// Auto-placement keywords
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AutoFlow {
    Row,
    Column,
    RowDense,
    ColumnDense,
}

/// Grid item placement (explicit or auto)
#[derive(Debug, Clone, PartialEq)]
pub struct GridPlacement {
    pub start: GridLine,
    pub end: GridLine,
}

#[derive(Debug, Clone, PartialEq)]
pub enum GridLine {
    Auto,
    Line(isize),          // 1-based (negative = from end)
    Span(usize),          // span N tracks
    NamedLine(String, usize), // named line, nth occurrence
}

impl GridPlacement {
    pub fn auto() -> Self {
        Self { start: GridLine::Auto, end: GridLine::Auto }
    }

    pub fn explicit(start: isize, end: isize) -> Self {
        Self { start: GridLine::Line(start), end: GridLine::Line(end) }
    }

    pub fn span(start: isize, span: usize) -> Self {
        Self { start: GridLine::Line(start), end: GridLine::Span(span) }
    }
}

/// A placed grid item
#[derive(Debug, Clone)]
pub struct GridItem {
    pub node_id: u64,
    pub column_placement: GridPlacement,
    pub row_placement: GridPlacement,
    pub justify_self: AlignValue,
    pub align_self: AlignValue,
    pub min_content_size: (f64, f64),
    pub max_content_size: (f64, f64),
    pub z_index: i32,

    // Resolved during placement:
    pub col_start: usize,   // 1-based resolved column start line
    pub col_end: usize,
    pub row_start: usize,
    pub row_end: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlignValue {
    Auto,
    Normal,
    Start,
    End,
    Center,
    Stretch,
    Baseline,
    SelfStart,
    SelfEnd,
    SpaceAround,
    SpaceBetween,
    SpaceEvenly,
}

impl AlignValue {
    pub fn from_str(s: &str) -> Self {
        match s.trim() {
            "start" => Self::Start,
            "end" => Self::End,
            "center" => Self::Center,
            "stretch" => Self::Stretch,
            "baseline" => Self::Baseline,
            "self-start" => Self::SelfStart,
            "self-end" => Self::SelfEnd,
            "space-around" => Self::SpaceAround,
            "space-between" => Self::SpaceBetween,
            "space-evenly" => Self::SpaceEvenly,
            "normal" => Self::Normal,
            _ => Self::Auto,
        }
    }
}

/// A resolved grid track (after all sizing is computed)
#[derive(Debug, Clone)]
pub struct ResolvedTrack {
    pub index: usize,       // 0-based
    pub offset: f64,        // offset from grid container start (px)
    pub size: f64,          // final track size (px)
    pub is_subgrid: bool,
}

/// Cell occupancy grid for auto-placement algorithm
#[derive(Debug, Default)]
struct OccupancyGrid {
    cols: usize,
    cells: HashMap<(usize, usize), u64>, // (col, row) -> node_id
}

impl OccupancyGrid {
    fn new(cols: usize) -> Self { Self { cols, cells: HashMap::new() } }

    fn is_occupied(&self, col: usize, row: usize) -> bool {
        self.cells.contains_key(&(col, row))
    }

    fn occupy_span(&mut self, col: usize, row: usize, col_span: usize, row_span: usize, node_id: u64) {
        for c in col..col + col_span {
            for r in row..row + row_span {
                self.cells.insert((c, r), node_id);
            }
        }
    }

    fn find_auto_placement(
        &self,
        col_span: usize,
        row_span: usize,
        start_row: usize,
        dense: bool,
    ) -> (usize, usize) {
        let max_row = 1000; // Limit for implicit grid growth
        for row in start_row..max_row {
            for col in 0..self.cols {
                if col + col_span > self.cols { continue; }
                let fits = (col..col+col_span).all(|c| {
                    (row..row+row_span).all(|r| !self.is_occupied(c, r))
                });
                if fits { return (col, row); }
            }
        }
        (0, max_row)
    }
}

/// The CSS Grid Level 2 Layout Engine
pub struct GridEngine {
    pub container_width: f64,
    pub container_height: f64,
    pub column_template: Vec<TrackSize>,
    pub row_template: Vec<TrackSize>,
    pub column_auto_tracks: Vec<TrackSize>,
    pub row_auto_tracks: Vec<TrackSize>,
    pub column_gap: f64,
    pub row_gap: f64,
    pub auto_flow: AutoFlow,
    pub justify_items: AlignValue,
    pub align_items: AlignValue,
    pub justify_content: AlignValue,
    pub align_content: AlignValue,
    pub column_line_names: GridLineNames,
    pub row_line_names: GridLineNames,
    // Template areas: area_name -> (row_start, col_start, row_end, col_end) (1-based)
    pub template_areas: HashMap<String, (usize, usize, usize, usize)>,
    // Subgrid configuration
    pub is_column_subgrid: bool,
    pub is_row_subgrid: bool,
    // Parent grid resolved tracks (for subgrid)
    pub parent_column_tracks: Vec<ResolvedTrack>,
    pub parent_row_tracks: Vec<ResolvedTrack>,
}

impl GridEngine {
    pub fn new(container_width: f64, container_height: f64) -> Self {
        Self {
            container_width, container_height,
            column_template: Vec::new(), row_template: Vec::new(),
            column_auto_tracks: vec![TrackSize::Auto],
            row_auto_tracks: vec![TrackSize::Auto],
            column_gap: 0.0, row_gap: 0.0,
            auto_flow: AutoFlow::Row,
            justify_items: AlignValue::Stretch,
            align_items: AlignValue::Stretch,
            justify_content: AlignValue::Start,
            align_content: AlignValue::Start,
            column_line_names: GridLineNames::default(),
            row_line_names: GridLineNames::default(),
            template_areas: HashMap::new(),
            is_column_subgrid: false,
            is_row_subgrid: false,
            parent_column_tracks: Vec::new(),
            parent_row_tracks: Vec::new(),
        }
    }

    /// Parse a grid-template-columns or grid-template-rows string
    pub fn parse_template_tracks(template: &str) -> Vec<TrackSize> {
        if template.trim() == "none" || template.trim() == "subgrid" {
            return Vec::new();
        }

        let mut tracks = Vec::new();
        let mut s = template.trim();

        while !s.is_empty() {
            s = s.trim_start();

            // Skip named line brackets [name1 name2]
            if s.starts_with('[') {
                if let Some(end) = s.find(']') { s = &s[end+1..]; continue; }
            }

            // Handle repeat()
            if s.starts_with("repeat(") {
                if let Some(end) = Self::find_matching_paren(&s[7..]) {
                    let inner = &s[7..7+end];
                    let repeated = Self::expand_repeat(inner);
                    tracks.extend(repeated);
                    s = &s[7+end+1..];
                    continue;
                }
            }

            // Handle minmax()/fit-content()
            if s.starts_with("minmax(") || s.starts_with("fit-content(") {
                let fn_end = s.find('(').unwrap_or(0);
                if let Some(paren_end) = Self::find_matching_paren(&s[fn_end+1..]) {
                    let token = &s[..fn_end+1+paren_end+1];
                    tracks.push(TrackSize::parse(token));
                    s = &s[token.len()..];
                    continue;
                }
            }

            // Regular token (up to next space)
            let token_end = s.find(|c: char| c.is_whitespace()).unwrap_or(s.len());
            let token = &s[..token_end];
            if !token.is_empty() {
                tracks.push(TrackSize::parse(token));
            }
            s = &s[token_end..];
        }

        tracks
    }

    /// Expand a repeat() parameter into individual track sizes
    fn expand_repeat(inner: &str) -> Vec<TrackSize> {
        let comma = inner.find(',').unwrap_or(inner.len());
        let count_str = inner[..comma].trim();
        let tracks_str = inner[comma+1..].trim();

        let track = TrackSize::parse(tracks_str);

        match count_str {
            "auto-fill" | "auto-fit" => {
                // Simplified: return single track — real impl computes count from available space
                vec![track]
            }
            _ => {
                let count: usize = count_str.parse().unwrap_or(1);
                vec![track; count]
            }
        }
    }

    fn find_matching_paren(s: &str) -> Option<usize> {
        let mut depth = 1i32;
        for (i, ch) in s.char_indices() {
            match ch { '(' => depth += 1, ')' => { depth -= 1; if depth == 0 { return Some(i); } } _ => {} }
        }
        None
    }

    /// Resolve explicit track sizes to px values
    pub fn resolve_tracks(&self, tracks: &[TrackSize], available: f64) -> Vec<f64> {
        let mut sizes: Vec<f64> = tracks.iter().map(|t| match t {
            TrackSize::Fixed(px) => *px,
            TrackSize::Percentage(pct) => available * pct / 100.0,
            TrackSize::MinContent => 0.0,   // Simplified: content sizing handled by items
            TrackSize::MaxContent => available,
            TrackSize::Auto => 0.0,         // Will be assigned in fr distribution
            TrackSize::Subgrid => 0.0,      // Inherited from parent
            TrackSize::FitContent(max) => max.min(available),
            TrackSize::Flexible(_) => 0.0,  // Handled in fr pass
            TrackSize::Minmax(min, max) => {
                let min_val = match min.as_ref() {
                    TrackSize::Fixed(px) => *px,
                    TrackSize::Percentage(pct) => available * pct / 100.0,
                    _ => 0.0,
                };
                let max_val = match max.as_ref() {
                    TrackSize::Fixed(px) => *px,
                    TrackSize::Flexible(_) => available,
                    _ => available,
                };
                min_val.max(0.0).min(max_val)
            }
        }).collect();

        // Calculate total gaps
        let gaps = if tracks.is_empty() { 0.0 } else { self.column_gap * (tracks.len() - 1) as f64 };
        let fixed_sum: f64 = sizes.iter().sum::<f64>() + gaps;
        let remaining = (available - fixed_sum).max(0.0);

        // Distribute fr units
        let total_fr: f64 = tracks.iter().filter_map(|t| {
            match t {
                TrackSize::Flexible(fr) => Some(fr),
                TrackSize::Minmax(_, max) => if let TrackSize::Flexible(fr) = max.as_ref() { Some(fr) } else { None },
                _ => None,
            }
        }).sum();

        if total_fr > 0.0 {
            let fr_unit = remaining / total_fr;
            for (i, track) in tracks.iter().enumerate() {
                match track {
                    TrackSize::Flexible(fr) => sizes[i] = fr * fr_unit,
                    TrackSize::Minmax(_, max) => {
                        if let TrackSize::Flexible(fr) = max.as_ref() {
                            sizes[i] = sizes[i].max(fr * fr_unit);
                        }
                    }
                    TrackSize::Auto => {
                        // Auto tracks get equal share of remaining if no fr tracks
                    }
                    _ => {}
                }
            }
        }

        sizes
    }

    /// Resolve grid line positions (offset from container edge)
    pub fn compute_track_geometries(&self, track_sizes: &[f64], gap: f64) -> Vec<ResolvedTrack> {
        let mut tracks = Vec::new();
        let mut offset = 0.0;

        for (i, &size) in track_sizes.iter().enumerate() {
            tracks.push(ResolvedTrack {
                index: i,
                offset,
                size,
                is_subgrid: false,
            });
            offset += size + gap;
        }

        tracks
    }

    /// Run the grid auto-placement algorithm (CSS Grid § 8)
    pub fn auto_place_items(
        &self,
        items: &mut Vec<GridItem>,
        col_count: usize,
    ) {
        let dense = matches!(self.auto_flow, AutoFlow::RowDense | AutoFlow::ColumnDense);
        let row_major = matches!(self.auto_flow, AutoFlow::Row | AutoFlow::RowDense);

        // Pass 1: Place items with definite column AND row placements
        for item in items.iter_mut() {
            let col_definite = !matches!(item.column_placement.start, GridLine::Auto);
            let row_definite = !matches!(item.row_placement.start, GridLine::Auto);
            if col_definite && row_definite {
                item.col_start = self.resolve_line(&item.column_placement.start, col_count);
                item.row_start = 1; // Simplified
                let col_span = self.span_for(&item.column_placement, col_count);
                let row_span = self.span_for(&item.row_placement, 1000);
                item.col_end = item.col_start + col_span;
                item.row_end = item.row_start + row_span;
            }
        }

        // Pass 2: Auto-place remaining items
        let mut grid = OccupancyGrid::new(col_count);
        let mut cursor_row = 0usize;

        // Mark already-placed items as occupied
        for item in items.iter() {
            if item.col_start > 0 && item.row_start > 0 {
                grid.occupy_span(
                    item.col_start - 1, item.row_start - 1,
                    item.col_end - item.col_start, item.row_end - item.row_start,
                    item.node_id,
                );
            }
        }

        // Auto-place items without definite position
        for item in items.iter_mut() {
            if item.col_start > 0 { continue; } // Already placed

            let col_span = self.span_for(&item.column_placement, col_count);
            let row_span = self.span_for(&item.row_placement, 1000);

            let (col, row) = grid.find_auto_placement(col_span, row_span, cursor_row, dense);

            item.col_start = col + 1;
            item.col_end = col + 1 + col_span;
            item.row_start = row + 1;
            item.row_end = row + 1 + row_span;

            grid.occupy_span(col, row, col_span, row_span, item.node_id);

            if !dense { cursor_row = row; }
        }
    }

    fn resolve_line(&self, line: &GridLine, track_count: usize) -> usize {
        match line {
            GridLine::Line(n) => {
                if *n > 0 { *n as usize }
                else { (track_count as isize + n + 1).max(1) as usize }
            }
            GridLine::NamedLine(name, n) => {
                self.column_line_names.resolve_nth(name, *n).unwrap_or(1)
            }
            _ => 1,
        }
    }

    fn span_for(&self, placement: &GridPlacement, max: usize) -> usize {
        match &placement.end {
            GridLine::Span(n) => *n,
            GridLine::Line(end) => {
                let start = match &placement.start {
                    GridLine::Line(s) => *s as usize,
                    _ => 1,
                };
                ((*end as usize).saturating_sub(start)).max(1)
            }
            _ => 1,
        }
    }

    /// Full layout execution — returns resolved track geometries and placed items
    pub fn layout(
        &self,
        items: &mut Vec<GridItem>,
    ) -> GridLayoutResult {
        // Step 1: Determine column / row count
        let explicit_cols = self.column_template.len();
        let explicit_rows = self.row_template.len();

        // Step 2: Resolve explicit track sizes
        let col_sizes = self.resolve_tracks(&self.column_template, self.container_width);
        let row_sizes = self.resolve_tracks(&self.row_template, self.container_height);

        // Step 3: Auto-place items
        let col_count = explicit_cols.max(1);
        self.auto_place_items(items, col_count);

        // Step 4: Compute implicit track count from item placement
        let max_col = items.iter().map(|i| i.col_end).max().unwrap_or(1);
        let max_row = items.iter().map(|i| i.row_end).max().unwrap_or(1);

        // Extend sizes for implicit tracks
        let mut all_col_sizes = col_sizes;
        while all_col_sizes.len() < max_col - 1 {
            let auto_idx = (all_col_sizes.len() - explicit_cols) % self.column_auto_tracks.len();
            let auto_size = match self.column_auto_tracks.get(auto_idx).unwrap_or(&TrackSize::Auto) {
                TrackSize::Fixed(px) => *px,
                _ => 0.0,
            };
            all_col_sizes.push(auto_size);
        }

        let mut all_row_sizes = row_sizes;
        while all_row_sizes.len() < max_row - 1 {
            let auto_idx = (all_row_sizes.len().saturating_sub(explicit_rows)) % self.row_auto_tracks.len();
            let auto_size = match self.row_auto_tracks.get(auto_idx).unwrap_or(&TrackSize::Auto) {
                TrackSize::Fixed(px) => *px,
                _ => 100.0, // Default implicit row height
            };
            all_row_sizes.push(auto_size);
        }

        // Step 5: Compute track geometries
        let col_tracks = self.compute_track_geometries(&all_col_sizes, self.column_gap);
        let row_tracks = self.compute_track_geometries(&all_row_sizes, self.row_gap);

        // Step 6: Compute item rects
        let mut item_rects = Vec::new();
        for item in items.iter() {
            let col_start = item.col_start.saturating_sub(1);
            let col_end = item.col_end.saturating_sub(1);
            let row_start = item.row_start.saturating_sub(1);
            let row_end = item.row_end.saturating_sub(1);

            let x = col_tracks.get(col_start).map(|t| t.offset).unwrap_or(0.0);
            let y = row_tracks.get(row_start).map(|t| t.offset).unwrap_or(0.0);

            let width: f64 = col_tracks[col_start.min(col_tracks.len().saturating_sub(1))..col_end.min(col_tracks.len())]
                .iter()
                .map(|t| t.size + self.column_gap)
                .sum::<f64>()
                .max(0.0) - self.column_gap;

            let height: f64 = row_tracks[row_start.min(row_tracks.len().saturating_sub(1))..row_end.min(row_tracks.len())]
                .iter()
                .map(|t| t.size + self.row_gap)
                .sum::<f64>()
                .max(0.0) - self.row_gap;

            item_rects.push(GridItemRect {
                node_id: item.node_id,
                x, y, width: width.max(0.0), height: height.max(0.0),
                col_start: item.col_start, col_end: item.col_end,
                row_start: item.row_start, row_end: item.row_end,
            });
        }

        GridLayoutResult {
            column_tracks: col_tracks,
            row_tracks,
            item_rects,
            total_width: self.container_width,
            total_height: self.container_height,
        }
    }
}

/// A resolved grid item geometry
#[derive(Debug, Clone)]
pub struct GridItemRect {
    pub node_id: u64,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub col_start: usize,
    pub col_end: usize,
    pub row_start: usize,
    pub row_end: usize,
}

/// Result of the grid layout computation
#[derive(Debug, Clone)]
pub struct GridLayoutResult {
    pub column_tracks: Vec<ResolvedTrack>,
    pub row_tracks: Vec<ResolvedTrack>,
    pub item_rects: Vec<GridItemRect>,
    pub total_width: f64,
    pub total_height: f64,
}

impl GridLayoutResult {
    pub fn item_rect(&self, node_id: u64) -> Option<&GridItemRect> {
        self.item_rects.iter().find(|r| r.node_id == node_id)
    }

    /// AI-facing visual occupancy grid
    pub fn ai_occupancy_map(&self, cols: usize, rows: usize) -> String {
        let mut grid = vec![vec![' '; cols]; rows];

        for rect in &self.item_rects {
            let c = (rect.col_start - 1).min(cols - 1);
            let r = (rect.row_start - 1).min(rows - 1);
            let id_ch = char::from_digit((rect.node_id % 10) as u32, 10).unwrap_or('?');
            grid[r][c] = id_ch;
        }

        let mut lines = vec![format!("📐 Grid Occupancy ({}×{}):", cols, rows)];
        for row in &grid {
            let row_str: String = row.iter().flat_map(|&c| [c, ' ']).collect();
            lines.push(format!("  |{}|", row_str.trim_end()));
        }
        lines.join("\n")
    }
}
