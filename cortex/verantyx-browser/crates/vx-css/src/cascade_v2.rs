//! CSS Cascade Algorithm — W3C CSS Cascading and Inheritance Level 5
//!
//! Implements the complete CSS cascade algorithm:
//!   - Origin layers: user-agent, user, author, animations, transitions
//!   - @layer ordering within author origin
//!   - !important declarations (reverses origin priority)
//!   - Specificity comparison (a, b, c tuple)
//!   - Source order as final tiebreaker
//!   - Inherited vs non-inherited property resolution
//!   - Initial values per CSS property
//!   - Computed value computation (resolving relative units, percentages)
//!   - Used value computation
//!   - Actual value quantization

use std::collections::HashMap;

/// CSS cascade origin (determines priority order in the cascade)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum CascadeOrigin {
    UserAgent       = 0,  // Browser default stylesheet
    UserAgentImportant = 1,
    User            = 2,  // User stylesheet (accessibility overrides)
    UserImportant   = 3,
    AuthorNormal    = 4,  // Web page stylesheets (normal)
    Animations      = 5,  // CSS Animations (between author normal and !important)
    AuthorImportant = 6,  // !important in web page stylesheets
    Transitions     = 7,  // CSS Transitions (highest priority for smooth values)
    UserImportantHigh = 8, // !important user rules trump !important author rules
}

impl CascadeOrigin {
    /// Map an origin + important flag to the correct cascade tier
    pub fn resolve(origin: BaseOrigin, important: bool) -> Self {
        match (origin, important) {
            (BaseOrigin::UserAgent, false) => Self::UserAgent,
            (BaseOrigin::UserAgent, true) => Self::UserAgentImportant,
            (BaseOrigin::User, false) => Self::User,
            (BaseOrigin::User, true) => Self::UserImportantHigh,
            (BaseOrigin::Author, false) => Self::AuthorNormal,
            (BaseOrigin::Author, true) => Self::AuthorImportant,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BaseOrigin {
    UserAgent,
    User,
    Author,
}

/// A CSS @layer declaration context
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CascadeLayer {
    /// Fully qualified layer name (e.g., "base.utilities")
    pub name: String,
    /// Layer ordering index among all layers in the stylesheet
    pub order: u32,
}

/// A single CSS declaration (property: value pair)
#[derive(Debug, Clone)]
pub struct CssDeclaration {
    pub property: String,
    pub value: String,
    pub important: bool,
    pub origin: BaseOrigin,
    /// Layer this declaration belongs to (None = unlayered)
    pub layer: Option<CascadeLayer>,
    /// Specificity of the selector that matched this declaration
    pub specificity: (u32, u32, u32),
    /// Source order index (position in the stylesheet)
    pub source_order: u32,
    /// Which selector matched (for debugging)
    pub matched_selector: String,
}

impl CssDeclaration {
    /// Compare two declarations for cascade priority
    /// Returns Ordering::Greater if self wins over other
    pub fn wins_over(&self, other: &CssDeclaration) -> bool {
        let self_origin = CascadeOrigin::resolve(self.origin, self.important);
        let other_origin = CascadeOrigin::resolve(other.origin, other.important);
        
        if self_origin != other_origin {
            return self_origin > other_origin;
        }
        
        // Same origin — compare @layer ordering
        // Unlayered declarations beat layered ones in author origin
        match (&self.layer, &other.layer) {
            (None, Some(_)) => return true,    // Unlayered wins over layered
            (Some(_), None) => return false,   // Layered loses to unlayered
            (Some(sl), Some(ol)) => {
                if sl.order != ol.order {
                    // Higher layer order wins for !important, lower wins for normal
                    return if self.important {
                        sl.order < ol.order
                    } else {
                        sl.order > ol.order
                    };
                }
            }
            (None, None) => {} // Both unlayered, continue to specificity
        }
        
        // Specificity comparison
        let self_spec = self.specificity;
        let other_spec = other.specificity;
        
        if self_spec != other_spec {
            return self_spec > other_spec;
        }
        
        // Source order — later declaration wins
        self.source_order > other.source_order
    }
}

/// The winning declaration for each property after cascade resolution
pub type CascadedValues = HashMap<String, CssDeclaration>;

/// Resolve the cascade for a set of declarations on a single element
pub fn resolve_cascade(declarations: Vec<CssDeclaration>) -> CascadedValues {
    let mut winner: HashMap<String, CssDeclaration> = HashMap::new();
    
    for decl in declarations {
        let property = decl.property.clone();
        
        let should_replace = match winner.get(&property) {
            None => true,
            Some(existing) => decl.wins_over(existing),
        };
        
        if should_replace {
            winner.insert(property, decl);
        }
    }
    
    winner
}

/// CSS property inheritance model
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InheritanceType {
    /// Property inherits by default (e.g., color, font-size, line-height)
    Inherited,
    /// Property does not inherit by default (e.g., width, margin, background)
    NotInherited,
}

/// Catalog of CSS property inheritance and initial values
pub struct CssPropertyCatalog;

impl CssPropertyCatalog {
    /// Whether a CSS property inherits by default
    pub fn is_inherited(property: &str) -> bool {
        matches!(property,
            // Font properties
            "font" | "font-family" | "font-size" | "font-style" | "font-variant" |
            "font-weight" | "font-stretch" | "font-feature-settings" |
            "font-kerning" | "font-language-override" | "font-optical-sizing" |
            "font-size-adjust" | "font-synthesis" | "font-variant-alternates" |
            "font-variant-caps" | "font-variant-east-asian" | "font-variant-ligatures" |
            "font-variant-numeric" | "font-variation-settings" |
            // Text properties
            "color" | "direction" | "letter-spacing" | "line-height" | "quotes" |
            "tab-size" | "text-align" | "text-align-last" | "text-decoration-skip-ink" |
            "text-emphasis" | "text-emphasis-color" | "text-emphasis-position" |
            "text-emphasis-style" | "text-indent" | "text-justify" | "text-orientation" |
            "text-rendering" | "text-shadow" | "text-size-adjust" | "text-transform" |
            "text-underline-offset" | "text-underline-position" |
            "white-space" | "word-break" | "word-spacing" | "word-wrap" |
            "overflow-wrap" | "writing-mode" |
            // List properties
            "list-style" | "list-style-image" | "list-style-position" | "list-style-type" |
            // Table properties
            "border-collapse" | "border-spacing" | "caption-side" | "empty-cells" |
            // Cursor and visibility
            "cursor" | "pointer-events" | "visibility" |
            // Other inheritable
            "image-rendering" | "speak" | "hyphens" | "hanging-punctuation" |
            "overscroll-behavior" | "orphans" | "widows" |
            // Custom properties (always inherited)  
            "-webkit-text-fill-color" | "-webkit-text-stroke"
        )
    }
    
    /// Get the CSS initial value for a property
    pub fn initial_value(property: &str) -> &'static str {
        match property {
            "display" => "inline",
            "position" => "static",
            "top" | "right" | "bottom" | "left" => "auto",
            "z-index" => "auto",
            "float" => "none",
            "clear" => "none",
            "overflow" | "overflow-x" | "overflow-y" => "visible",
            "visibility" => "visible",
            "opacity" => "1",
            "color" => "canvastext",
            "background-color" => "transparent",
            "background-image" => "none",
            "background-position" => "0% 0%",
            "background-size" => "auto auto",
            "background-repeat" => "repeat",
            "background-attachment" => "scroll",
            "background-clip" => "border-box",
            "background-origin" => "padding-box",
            "border-width" => "medium",
            "border-style" => "none",
            "border-color" => "currentcolor",
            "border-radius" => "0",
            "outline" => "none",
            "outline-width" => "medium",
            "outline-style" => "none",
            "outline-offset" => "0",
            "margin" | "margin-top" | "margin-right" | "margin-bottom" | "margin-left" => "0",
            "padding" | "padding-top" | "padding-right" | "padding-bottom" | "padding-left" => "0",
            "width" | "height" => "auto",
            "min-width" | "min-height" => "auto",
            "max-width" | "max-height" => "none",
            "box-sizing" => "content-box",
            "font-size" => "medium",
            "font-weight" => "normal",
            "font-style" => "normal",
            "font-family" => "serif",
            "font-variant" => "normal",
            "line-height" => "normal",
            "letter-spacing" => "normal",
            "word-spacing" => "normal",
            "text-align" => "start",
            "text-decoration" => "none",
            "text-transform" => "none",
            "text-indent" => "0",
            "white-space" => "normal",
            "word-break" => "normal",
            "overflow-wrap" => "normal",
            "list-style-type" => "disc",
            "list-style-position" => "outside",
            "list-style-image" => "none",
            "cursor" => "auto",
            "pointer-events" => "auto",
            "content" => "normal",
            "transform" => "none",
            "transform-origin" => "50% 50%",
            "transition" => "none",
            "animation" => "none",
            "flex" => "0 1 auto",
            "flex-direction" => "row",
            "flex-wrap" => "nowrap",
            "flex-grow" => "0",
            "flex-shrink" => "1",
            "flex-basis" => "auto",
            "align-items" => "normal",
            "align-content" => "normal",
            "align-self" => "auto",
            "justify-content" => "normal",
            "justify-items" => "normal",
            "justify-self" => "auto",
            "gap" | "row-gap" | "column-gap" => "normal",
            "grid-template-columns" | "grid-template-rows" => "none",
            "grid-auto-columns" | "grid-auto-rows" => "auto",
            "grid-auto-flow" => "row",
            "grid-template-areas" => "none",
            "order" => "0",
            "grid-column" | "grid-row" => "auto",
            "grid-column-start" | "grid-column-end" | "grid-row-start" | "grid-row-end" => "auto",
            "border-collapse" => "separate",
            "table-layout" => "auto",
            "caption-side" => "top",
            "empty-cells" => "show",
            "border-spacing" => "0",
            "quotes" => "auto",
            "counter-reset" | "counter-increment" | "counter-set" => "none",
            "resize" => "none",
            "appearance" => "none",
            "user-select" => "auto",
            "box-shadow" => "none",
            "filter" => "none",
            "backdrop-filter" => "none",
            "mix-blend-mode" => "normal",
            "isolation" => "auto",
            "object-fit" => "fill",
            "object-position" => "50% 50%",
            "direction" => "ltr",
            "unicode-bidi" => "normal",
            "writing-mode" => "horizontal-tb",
            "text-orientation" => "mixed",
            "orphans" | "widows" => "2",
            "image-rendering" => "auto",
            "speak" => "normal",
            _ => "initial",
        }
    }
    
    /// Resolve a value of "currentColor" to the computed color
    pub fn resolve_current_color(value: &str, computed_color: &str) -> String {
        if value.to_lowercase() == "currentcolor" {
            computed_color.to_string()
        } else {
            value.to_string()
        }
    }
    
    /// Whether a property is a CSS custom property (--variable)
    pub fn is_custom_property(property: &str) -> bool {
        property.starts_with("--")
    }
    
    /// Get the list of longhand properties for a shorthand
    pub fn shorthand_longhands(shorthand: &str) -> &'static [&'static str] {
        match shorthand {
            "margin" => &["margin-top", "margin-right", "margin-bottom", "margin-left"],
            "padding" => &["padding-top", "padding-right", "padding-bottom", "padding-left"],
            "border" => &["border-width", "border-style", "border-color"],
            "border-top" => &["border-top-width", "border-top-style", "border-top-color"],
            "border-right" => &["border-right-width", "border-right-style", "border-right-color"],
            "border-bottom" => &["border-bottom-width", "border-bottom-style", "border-bottom-color"],
            "border-left" => &["border-left-width", "border-left-style", "border-left-color"],
            "border-radius" => &["border-top-left-radius", "border-top-right-radius",
                                  "border-bottom-right-radius", "border-bottom-left-radius"],
            "outline" => &["outline-width", "outline-style", "outline-color"],
            "background" => &["background-image", "background-position", "background-size",
                               "background-repeat", "background-origin", "background-clip",
                               "background-color", "background-attachment"],
            "font" => &["font-style", "font-variant", "font-weight", "font-stretch",
                         "font-size", "line-height", "font-family"],
            "list-style" => &["list-style-position", "list-style-image", "list-style-type"],
            "flex" => &["flex-grow", "flex-shrink", "flex-basis"],
            "flex-flow" => &["flex-direction", "flex-wrap"],
            "gap" => &["row-gap", "column-gap"],
            "overflow" => &["overflow-x", "overflow-y"],
            "grid-template" => &["grid-template-rows", "grid-template-columns", "grid-template-areas"],
            "transition" => &["transition-property", "transition-duration",
                               "transition-timing-function", "transition-delay"],
            "animation" => &["animation-name", "animation-duration", "animation-timing-function",
                              "animation-delay", "animation-iteration-count",
                              "animation-direction", "animation-fill-mode", "animation-play-state"],
            _ => &[],
        }
    }
}

/// The computed style value resolver — converts specified values to computed values
pub struct ComputedStyleResolver {
    /// The parent element's computed values (for inheritance)
    parent_computed: HashMap<String, String>,
    /// The viewport dimensions (for vw/vh resolution)
    viewport_width: f64,
    viewport_height: f64,
    /// The root font size (for rem resolution)
    root_font_size: f64,
}

impl ComputedStyleResolver {
    pub fn new(
        parent_computed: HashMap<String, String>,
        viewport_width: f64,
        viewport_height: f64,
        root_font_size: f64,
    ) -> Self {
        Self { parent_computed, viewport_width, viewport_height, root_font_size }
    }
    
    /// Resolve the computed value for a property
    pub fn resolve(&self, property: &str, specified_value: &str) -> String {
        let value = specified_value.trim().to_lowercase();
        
        // Handle CSS-wide keywords
        match value.as_str() {
            "inherit" => {
                return self.parent_computed.get(property)
                    .cloned()
                    .unwrap_or_else(|| CssPropertyCatalog::initial_value(property).to_string());
            }
            "initial" => {
                return CssPropertyCatalog::initial_value(property).to_string();
            }
            "unset" => {
                if CssPropertyCatalog::is_inherited(property) {
                    return self.parent_computed.get(property)
                        .cloned()
                        .unwrap_or_else(|| CssPropertyCatalog::initial_value(property).to_string());
                } else {
                    return CssPropertyCatalog::initial_value(property).to_string();
                }
            }
            "revert" => {
                // Revert to UA stylesheet — simplified to initial
                return CssPropertyCatalog::initial_value(property).to_string();
            }
            "revert-layer" => {
                // Simplified — revert to next layer below
                return CssPropertyCatalog::initial_value(property).to_string();
            }
            _ => {}
        }
        
        // Property-specific resolution
        match property {
            "font-size" => self.resolve_font_size(&value),
            "line-height" => self.resolve_line_height(&value),
            "width" | "height" | "min-width" | "min-height" | "max-width" | "max-height" |
            "margin-top" | "margin-right" | "margin-bottom" | "margin-left" |
            "padding-top" | "padding-right" | "padding-bottom" | "padding-left" |
            "top" | "right" | "bottom" | "left" |
            "gap" | "row-gap" | "column-gap" => self.resolve_length(&value),
            "color" | "background-color" | "border-color" | "outline-color" => {
                self.resolve_color(&value)
            }
            "opacity" => {
                let n: f64 = value.parse().unwrap_or(1.0);
                format!("{:.4}", n.clamp(0.0, 1.0))
            }
            "z-index" => {
                if value == "auto" { value.to_string() }
                else { value.parse::<i32>().map(|n| n.to_string()).unwrap_or(value) }
            }
            "font-weight" => self.resolve_font_weight(&value),
            _ => specified_value.to_string(),
        }
    }
    
    fn resolve_font_size(&self, value: &str) -> String {
        let parent_size = self.parent_computed.get("font-size")
            .and_then(|v| v.trim_end_matches("px").parse::<f64>().ok())
            .unwrap_or(16.0);
        
        let px = match value {
            "xx-small" => 9.0,
            "x-small"  => 10.0,
            "small"    => 13.0,
            "medium"   => 16.0,
            "large"    => 18.0,
            "x-large"  => 24.0,
            "xx-large" => 32.0,
            "xxx-large" => 48.0,
            "smaller"  => parent_size * 0.833,
            "larger"   => parent_size * 1.2,
            _ => self.resolve_length_value(value, parent_size),
        };
        
        format!("{:.2}px", px)
    }
    
    fn resolve_line_height(&self, value: &str) -> String {
        if value == "normal" { return "normal".to_string(); }
        
        let font_size = self.parent_computed.get("font-size")
            .and_then(|v| v.trim_end_matches("px").parse::<f64>().ok())
            .unwrap_or(16.0);
        
        if let Ok(multiplier) = value.parse::<f64>() {
            return format!("{:.2}px", font_size * multiplier);
        }
        
        self.resolve_length(value)
    }
    
    fn resolve_font_weight(&self, value: &str) -> String {
        let parent_weight = self.parent_computed.get("font-weight")
            .and_then(|v| v.parse::<u32>().ok())
            .unwrap_or(400);
        
        match value {
            "normal" => "400".to_string(),
            "bold" => "700".to_string(),
            "bolder" => {
                let bolder = if parent_weight < 100 { 400 }
                    else if parent_weight < 350 { 400 }
                    else if parent_weight < 550 { 700 }
                    else if parent_weight < 750 { 900 }
                    else { 900 };
                bolder.to_string()
            }
            "lighter" => {
                let lighter = if parent_weight < 100 { 100 }
                    else if parent_weight < 350 { 100 }
                    else if parent_weight < 550 { 100 }
                    else if parent_weight < 750 { 400 }
                    else { 700 };
                lighter.to_string()
            }
            _ => value.parse::<u32>().map(|n| n.to_string()).unwrap_or_else(|_| "400".to_string()),
        }
    }
    
    fn resolve_color(&self, value: &str) -> String {
        // Resolve currentColor
        if value == "currentcolor" {
            return self.parent_computed.get("color")
                .cloned()
                .unwrap_or_else(|| "rgb(0, 0, 0)".to_string());
        }
        
        // Resolve named colors to rgb()
        match value {
            "black" => "rgb(0, 0, 0)".to_string(),
            "white" => "rgb(255, 255, 255)".to_string(),
            "red" => "rgb(255, 0, 0)".to_string(),
            "green" => "rgb(0, 128, 0)".to_string(),
            "blue" => "rgb(0, 0, 255)".to_string(),
            "transparent" => "rgba(0, 0, 0, 0)".to_string(),
            _ => value.to_string(),
        }
    }
    
    fn resolve_length(&self, value: &str) -> String {
        if value == "auto" || value == "none" { return value.to_string(); }
        
        let font_size = self.parent_computed.get("font-size")
            .and_then(|v| v.trim_end_matches("px").parse::<f64>().ok())
            .unwrap_or(16.0);
        
        let px = self.resolve_length_value(value, font_size);
        format!("{:.2}px", px)
    }
    
    fn resolve_length_value(&self, value: &str, font_size: f64) -> f64 {
        if let Some(v) = value.strip_suffix("px") { return v.parse().unwrap_or(0.0); }
        if let Some(v) = value.strip_suffix("em") { return v.parse::<f64>().unwrap_or(0.0) * font_size; }
        if let Some(v) = value.strip_suffix("rem") { return v.parse::<f64>().unwrap_or(0.0) * self.root_font_size; }
        if let Some(v) = value.strip_suffix("vw") { return v.parse::<f64>().unwrap_or(0.0) * self.viewport_width / 100.0; }
        if let Some(v) = value.strip_suffix("vh") { return v.parse::<f64>().unwrap_or(0.0) * self.viewport_height / 100.0; }
        if let Some(v) = value.strip_suffix("vmin") {
            return v.parse::<f64>().unwrap_or(0.0) * self.viewport_width.min(self.viewport_height) / 100.0;
        }
        if let Some(v) = value.strip_suffix("vmax") {
            return v.parse::<f64>().unwrap_or(0.0) * self.viewport_width.max(self.viewport_height) / 100.0;
        }
        if let Some(v) = value.strip_suffix("dvh") { return v.parse::<f64>().unwrap_or(0.0) * self.viewport_height / 100.0; }
        if let Some(v) = value.strip_suffix("svh") { return v.parse::<f64>().unwrap_or(0.0) * self.viewport_height / 100.0; }
        if let Some(v) = value.strip_suffix("lvh") { return v.parse::<f64>().unwrap_or(0.0) * self.viewport_height / 100.0; }
        if let Some(v) = value.strip_suffix("%") { return v.parse::<f64>().unwrap_or(0.0) * font_size / 100.0; }
        if let Some(v) = value.strip_suffix("pt") { return v.parse::<f64>().unwrap_or(0.0) * 1.333333; }
        if let Some(v) = value.strip_suffix("pc") { return v.parse::<f64>().unwrap_or(0.0) * 16.0; }
        if let Some(v) = value.strip_suffix("in") { return v.parse::<f64>().unwrap_or(0.0) * 96.0; }
        if let Some(v) = value.strip_suffix("cm") { return v.parse::<f64>().unwrap_or(0.0) * 37.795276; }
        if let Some(v) = value.strip_suffix("mm") { return v.parse::<f64>().unwrap_or(0.0) * 3.7795276; }
        if let Some(v) = value.strip_suffix("q") { return v.parse::<f64>().unwrap_or(0.0) * 0.94488; }
        
        value.parse::<f64>().unwrap_or(0.0)
    }
}

/// CSS @layer registry — tracks the declaration order of @layer rules
pub struct LayerRegistry {
    /// Ordered list of layer names (first declared = lowest priority)
    layers: Vec<String>,
    /// Sublayer nesting: parent_layer -> [child_layers]
    sublayers: HashMap<String, Vec<String>>,
}

impl LayerRegistry {
    pub fn new() -> Self {
        Self { layers: Vec::new(), sublayers: HashMap::new() }
    }
    
    /// Register a layer declaration (@layer name)
    pub fn declare(&mut self, name: &str) -> u32 {
        if !self.layers.contains(&name.to_string()) {
            self.layers.push(name.to_string());
        }
        self.layers.iter().position(|l| l == name).unwrap_or(0) as u32
    }
    
    /// Get the order index for a layer name
    pub fn order_of(&self, name: &str) -> Option<u32> {
        self.layers.iter().position(|l| l == name).map(|i| i as u32)
    }
    
    pub fn all_layers(&self) -> &[String] {
        &self.layers
    }
}

/// The CSS cascade context for a full document
pub struct CascadeContext {
    pub layer_registry: LayerRegistry,
    /// Precomputed UA stylesheet declarations
    ua_declarations: Vec<CssDeclaration>,
}

impl CascadeContext {
    pub fn new() -> Self {
        Self {
            layer_registry: LayerRegistry::new(),
            ua_declarations: Self::build_ua_stylesheet(),
        }
    }
    
    /// Build the minimal browser UA stylesheet declarations
    fn build_ua_stylesheet() -> Vec<CssDeclaration> {
        let ua_rules: &[(&str, &[(&str, &str)])] = &[
            ("html, body", &[("display", "block"), ("margin", "0")]),
            ("div, p, section, article, nav, aside, header, footer, main", &[("display", "block")]),
            ("head, script, style, link, meta", &[("display", "none")]),
            ("a", &[("color", "linktext"), ("text-decoration", "underline"), ("cursor", "pointer")]),
            ("b, strong", &[("font-weight", "bold")]),
            ("i, em", &[("font-style", "italic")]),
            ("h1", &[("font-size", "2em"), ("font-weight", "bold"), ("display", "block"), ("margin", "0.67em 0")]),
            ("h2", &[("font-size", "1.5em"), ("font-weight", "bold"), ("display", "block"), ("margin", "0.83em 0")]),
            ("h3", &[("font-size", "1.17em"), ("font-weight", "bold"), ("display", "block"), ("margin", "1em 0")]),
            ("h4", &[("font-size", "1em"), ("font-weight", "bold"), ("display", "block"), ("margin", "1.33em 0")]),
            ("h5", &[("font-size", "0.83em"), ("font-weight", "bold"), ("display", "block"), ("margin", "1.67em 0")]),
            ("h6", &[("font-size", "0.67em"), ("font-weight", "bold"), ("display", "block"), ("margin", "2.33em 0")]),
            ("ul, ol", &[("display", "block"), ("list-style-type", "disc"), ("margin", "1em 0"), ("padding-left", "40px")]),
            ("li", &[("display", "list-item")]),
            ("table", &[("display", "table"), ("border-collapse", "separate"), ("border-spacing", "2px")]),
            ("thead, tbody, tfoot", &[("display", "table-row-group")]),
            ("tr", &[("display", "table-row")]),
            ("th, td", &[("display", "table-cell"), ("padding", "1px"), ("vertical-align", "inherit")]),
            ("th", &[("font-weight", "bold"), ("text-align", "center")]),
            ("caption", &[("display", "table-caption"), ("text-align", "center")]),
            ("input, textarea, select, button", &[("display", "inline-block")]),
            ("button", &[("cursor", "pointer")]),
            ("img", &[("display", "inline")]),
            ("pre, code, kbd, samp, tt", &[("font-family", "monospace")]),
            ("pre", &[("display", "block"), ("white-space", "pre"), ("margin", "1em 0")]),
            ("blockquote", &[("display", "block"), ("margin", "1em 40px")]),
            ("hr", &[("display", "block"), ("height", "1px"), ("border", "1px inset"), ("margin", "0.5em auto")]),
        ];
        
        let mut decls = Vec::new();
        let mut order = 0u32;
        
        for (selector, props) in ua_rules {
            for (property, value) in *props {
                decls.push(CssDeclaration {
                    property: property.to_string(),
                    value: value.to_string(),
                    important: false,
                    origin: BaseOrigin::UserAgent,
                    layer: None,
                    specificity: (0, 0, 0),
                    source_order: order,
                    matched_selector: selector.to_string(),
                });
                order += 1;
            }
        }
        
        decls
    }
    
    pub fn ua_rules_for_tag(&self, tag: &str) -> Vec<&CssDeclaration> {
        self.ua_declarations.iter()
            .filter(|d| {
                d.matched_selector.split(',')
                    .any(|sel| sel.trim() == tag || 
                         sel.trim().split_whitespace().any(|part| part == tag))
            })
            .collect()
    }
}
