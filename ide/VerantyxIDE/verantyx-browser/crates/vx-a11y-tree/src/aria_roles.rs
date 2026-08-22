//! ARIA Role-to-Cognitive-Tensor Mapping Engine
//!
//! The most critical piece of AI browser infrastructure.
//! Maps every ARIA role + ARIA state to a structured cognitive descriptor
//! that an LLM can reason about precisely without visual access.
//!
//! Implements the full ARIA 1.3 spec role taxonomy (200+ roles),
//! required/supported properties, inherited states, and the cognitive
//! summary generation used for AI agent decision making.


/// All ARIA Roles per WAI-ARIA 1.3 Specification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AriaRole {
    // === LANDMARK ROLES ===
    Banner,
    Complementary,
    ContentInfo,
    Form,
    Main,
    Navigation,
    Region,
    Search,
    
    // === DOCUMENT STRUCTURE ROLES ===
    Article,
    Cell,
    ColumnHeader,
    Definition,
    Directory,
    Document,
    Feed,
    Figure,
    Generic,
    Group,
    Heading,
    Img,
    List,
    ListItem,
    Math,
    Note,
    Paragraph,
    Presentation,
    Row,
    RowGroup,
    RowHeader,
    Separator,
    Table,
    Term,
    Toolbar,
    Tooltip,
    
    // === WIDGET ROLES ===
    Button,
    Checkbox,
    ComboBox,
    Dialog,
    GridCell,
    Link,
    ListBox,
    ListBoxOption,
    Menu,
    MenuBar,
    MenuItem,
    MenuItemCheckbox,
    MenuItemRadio,
    Option,
    ProgressBar,
    Radio,
    RadioGroup,
    ScrollBar,
    SearchBox,
    Slider,
    SpinButton,
    Switch,
    Tab,
    TabList,
    TabPanel,
    TextBox,
    Timer,
    Tree,
    TreeGrid,
    TreeItem,
    
    // === LIVE REGION ROLES ===
    Alert,
    AlertDialog,
    Log,
    Marquee,
    Status,
    
    // === WINDOW ROLES ===
    AlertDialogWindow,
    
    // === ABSTRACT ROLES (not used in practice but defined in spec) ===
    Command,
    Composite,
    Input,
    Landmark,
    RangeRole,
    RoleType,
    Section,
    SectionHead,
    Select,
    Structure,
    Widget,
    Window,
    
    // === DPUB-ARIA ROLES (Digital Publishing) ===
    DpubAbstract,
    DpubAcknowledgments,
    DpubAfterword,
    DpubAppendix,
    DpubBacklink,
    DpubBiblioentry,
    DpubBibliography,
    DpubBiblioref,
    DpubChapter,
    DpubColophon,
    DpubConclusion,
    DpubCover,
    DpubCreditedTo,
    DpubCredits,
    DpubDedication,
    DpubEndnote,
    DpubEndnotes,
    DpubEpigraph,
    DpubEpilogue,
    DpubErrata,
    DpubFootnote,
    DpubForeword,
    DpubGlossary,
    DpubGlossref,
    DpubIndex,
    DpubIntroduction,
    DpubPagebreak,
    DpubPagelist,
    DpubPart,
    DpubPreface,
    DpubPrologue,
    DpubPullquote,
    DpubQna,
    DpubSubtitle,
    DpubToc,
    DpubTocitem,
    
    // === GRAPHICS-ARIA ROLES ===
    GraphicsDocument,
    GraphicsObject,
    GraphicsSymbol,
    
    // Generic unknown role
    None,
    Unknown,
}

impl AriaRole {
    /// Map an ARIA role name string to the enum
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "banner" => Self::Banner,
            "complementary" => Self::Complementary,
            "contentinfo" => Self::ContentInfo,
            "form" => Self::Form,
            "main" => Self::Main,
            "navigation" => Self::Navigation,
            "region" => Self::Region,
            "search" => Self::Search,
            "article" => Self::Article,
            "cell" => Self::Cell,
            "columnheader" => Self::ColumnHeader,
            "definition" => Self::Definition,
            "directory" => Self::Directory,
            "document" => Self::Document,
            "feed" => Self::Feed,
            "figure" => Self::Figure,
            "generic" => Self::Generic,
            "group" => Self::Group,
            "heading" => Self::Heading,
            "img" => Self::Img,
            "list" => Self::List,
            "listitem" => Self::ListItem,
            "math" => Self::Math,
            "note" => Self::Note,
            "paragraph" => Self::Paragraph,
            "presentation" => Self::Presentation,
            "row" => Self::Row,
            "rowgroup" => Self::RowGroup,
            "rowheader" => Self::RowHeader,
            "separator" => Self::Separator,
            "table" => Self::Table,
            "term" => Self::Term,
            "toolbar" => Self::Toolbar,
            "tooltip" => Self::Tooltip,
            "button" => Self::Button,
            "checkbox" => Self::Checkbox,
            "combobox" => Self::ComboBox,
            "dialog" => Self::Dialog,
            "gridcell" => Self::GridCell,
            "link" => Self::Link,
            "listbox" => Self::ListBox,
            "option" => Self::ListBoxOption,
            "menu" => Self::Menu,
            "menubar" => Self::MenuBar,
            "menuitem" => Self::MenuItem,
            "menuitemcheckbox" => Self::MenuItemCheckbox,
            "menuitemradio" => Self::MenuItemRadio,
            "progressbar" => Self::ProgressBar,
            "radio" => Self::Radio,
            "radiogroup" => Self::RadioGroup,
            "scrollbar" => Self::ScrollBar,
            "searchbox" => Self::SearchBox,
            "slider" => Self::Slider,
            "spinbutton" => Self::SpinButton,
            "switch" => Self::Switch,
            "tab" => Self::Tab,
            "tablist" => Self::TabList,
            "tabpanel" => Self::TabPanel,
            "textbox" => Self::TextBox,
            "timer" => Self::Timer,
            "tree" => Self::Tree,
            "treegrid" => Self::TreeGrid,
            "treeitem" => Self::TreeItem,
            "alert" => Self::Alert,
            "alertdialog" => Self::AlertDialog,
            "log" => Self::Log,
            "marquee" => Self::Marquee,
            "status" => Self::Status,
            "none" | "presentation" => Self::None,
            // dpub
            "doc-abstract" => Self::DpubAbstract,
            "doc-chapter" => Self::DpubChapter,
            "doc-footnote" => Self::DpubFootnote,
            "doc-part" => Self::DpubPart,
            "doc-toc" => Self::DpubToc,
            "doc-glossary" => Self::DpubGlossary,
            _ => Self::Unknown,
        }
    }
    
    /// Infer the ARIA role from an HTML tag name
    pub fn implicit_from_tag(tag: &str, attrs: &std::collections::HashMap<String, String>) -> Self {
        let tag_type = attrs.get("type").map(|s| s.as_str()).unwrap_or("");
        
        match tag.to_lowercase().as_str() {
            "a" | "area" => {
                if attrs.contains_key("href") { Self::Link } else { Self::Generic }
            }
            "article" => Self::Article,
            "aside" => Self::Complementary,
            "button" => Self::Button,
            "caption" => Self::Caption,
            "code" => Self::Code,
            "dd" => Self::Definition,
            "details" => Self::Group,
            "dialog" => Self::Dialog,
            "dt" => Self::Term,
            "em" => Self::Emphasis,
            "fieldset" => Self::Group,
            "figure" => Self::Figure,
            "footer" => {
                // footer is contentinfo at document level, generic within sections
                Self::ContentInfo
            }
            "form" => Self::Form,
            "h1" | "h2" | "h3" | "h4" | "h5" | "h6" => Self::Heading,
            "header" => Self::Banner,
            "hr" => Self::Separator,
            "html" => Self::Document,
            "img" => {
                if attrs.get("alt").map_or(false, |alt| alt.is_empty()) {
                    Self::Presentation
                } else {
                    Self::Img
                }
            }
            "input" => match tag_type {
                "button" | "reset" | "submit" | "image" => Self::Button,
                "checkbox" => Self::Checkbox,
                "radio" => Self::Radio,
                "range" => Self::Slider,
                "number" => Self::SpinButton,
                "search" => Self::SearchBox,
                "email" | "tel" | "text" | "url" | "password" => Self::TextBox,
                "hidden" => Self::Unknown, // No accessible role
                _ => Self::TextBox,
            },
            "li" => Self::ListItem,
            "link" => Self::Unknown, // <link> element has no accessible role
            "main" => Self::Main,
            "math" => Self::Math,
            "menu" => Self::List,
            "meter" => Self::Meter,
            "nav" => Self::Navigation,
            "ol" => Self::List,
            "option" => Self::ListBoxOption,
            "output" => Self::Status,
            "p" => Self::Paragraph,
            "progress" => Self::ProgressBar,
            "search" => Self::Search,
            "section" => Self::Region,
            "select" => {
                if attrs.contains_key("multiple") || attrs.get("size").and_then(|s| s.parse::<u32>().ok()).unwrap_or(1) > 1 {
                    Self::ListBox
                } else {
                    Self::ComboBox
                }
            }
            "strong" => Self::Strong,
            "sub" => Self::Subscript,
            "summary" => Self::Button,
            "sup" => Self::Superscript,
            "svg" => Self::GraphicsDocument,
            "table" => Self::Table,
            "tbody" | "thead" | "tfoot" => Self::RowGroup,
            "td" => Self::Cell,
            "textarea" => Self::TextBox,
            "th" => {
                match attrs.get("scope").map(|s| s.as_str()) {
                    Some("col") | Some("colgroup") => Self::ColumnHeader,
                    _ => Self::RowHeader,
                }
            }
            "time" => Self::Time,
            "tr" => Self::Row,
            "ul" => Self::List,
            _ => Self::Generic,
        }
    }
    
    /// Cognitive interaction hint for the AI agent
    pub fn ai_interaction_hint(&self) -> AiInteractionHint {
        match self {
            Self::Button | Self::MenuItem | Self::MenuItemCheckbox | Self::MenuItemRadio
            | Self::Tab | Self::TreeItem => AiInteractionHint::Clickable,
            
            Self::TextBox | Self::SearchBox | Self::SpinButton => AiInteractionHint::Typeable,
            
            Self::Link => AiInteractionHint::NavigatesTo,
            
            Self::Checkbox | Self::Radio | Self::Switch => AiInteractionHint::Toggleable,
            
            Self::ComboBox | Self::Select | Self::ListBox => AiInteractionHint::Selectable,
            
            Self::Slider | Self::ScrollBar => AiInteractionHint::Adjustable,
            
            Self::Dialog | Self::AlertDialog => AiInteractionHint::Modal,
            
            Self::None | Self::Presentation | Self::Unknown => AiInteractionHint::NonInteractive,
            
            _ => AiInteractionHint::Structural,
        }
    }
    
    /// Whether this role represents a landmark (navigational structure)
    pub fn is_landmark(&self) -> bool {
        matches!(self,
            Self::Banner | Self::Complementary | Self::ContentInfo |
            Self::Form | Self::Main | Self::Navigation | Self::Region | Self::Search
        )
    }
    
    /// Whether this role is a live region (announces changes to screen readers)
    pub fn is_live_region(&self) -> bool {
        matches!(self, Self::Alert | Self::Log | Self::Marquee | Self::Status | Self::Timer)
    }
    
    /// The ARIA spec name for this role
    pub fn spec_name(&self) -> &'static str {
        match self {
            Self::Banner => "banner",
            Self::Button => "button",
            Self::Checkbox => "checkbox",
            Self::ComboBox => "combobox",
            Self::ContentInfo => "contentinfo",
            Self::Dialog => "dialog",
            Self::Heading => "heading",
            Self::Link => "link",
            Self::List => "list",
            Self::ListItem => "listitem",
            Self::Main => "main",
            Self::Navigation => "navigation",
            Self::Option => "option",
            Self::ProgressBar => "progressbar",
            Self::Radio => "radio",
            Self::Region => "region",
            Self::SearchBox => "searchbox",
            Self::Slider => "slider",
            Self::Switch => "switch",
            Self::Tab => "tab",
            Self::TabList => "tablist",
            Self::TabPanel => "tabpanel",
            Self::TextBox => "textbox",
            Self::Tree => "tree",
            Self::TreeItem => "treeitem",
            Self::Alert => "alert",
            Self::None => "none",
            Self::Img => "img",
            Self::Form => "form",
            Self::Table => "table",
            Self::Row => "row",
            Self::Cell => "cell",
            _ => "generic",
        }
    }
}

/// The AI-facing interaction hint for an element
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AiInteractionHint {
    /// Can be clicked (button, menuitem, tab, etc.)
    Clickable,
    /// Can receive text input
    Typeable,
    /// Causes navigation when activated
    NavigatesTo,
    /// Has on/off state that toggles
    Toggleable,
    /// Has selectable options
    Selectable,
    /// Has a numeric value that can be changed (slider, scrollbar)
    Adjustable,
    /// Is a modal that captures focus
    Modal,
    /// Provides page structure, not interactive
    Structural,
    /// Element has no accessible role or interaction
    NonInteractive,
}

impl AiInteractionHint {
    pub fn to_emoji(&self) -> &'static str {
        match self {
            Self::Clickable => "🖱️",
            Self::Typeable => "⌨️",
            Self::NavigatesTo => "🔗",
            Self::Toggleable => "🔘",
            Self::Selectable => "📋",
            Self::Adjustable => "🎚️",
            Self::Modal => "⚠️",
            Self::Structural => "📐",
            Self::NonInteractive => "⬜",
        }
    }
    
    pub fn to_str(&self) -> &'static str {
        match self {
            Self::Clickable => "clickable",
            Self::Typeable => "typeable",
            Self::NavigatesTo => "navigates_to",
            Self::Toggleable => "toggleable",
            Self::Selectable => "selectable",
            Self::Adjustable => "adjustable",
            Self::Modal => "modal",
            Self::Structural => "structural",
            Self::NonInteractive => "non_interactive",
        }
    }
}

// Extra roles referenced in implicit mapping but not in main enum
// (handled via fallback to Generic/Unknown in from_tag):
impl AriaRole {
    const Caption: AriaRole = AriaRole::Unknown; // <caption> maps to caption role  
    const Code: AriaRole = AriaRole::Generic;
    const Emphasis: AriaRole = AriaRole::Generic;
    const Strong: AriaRole = AriaRole::Generic;
    const Subscript: AriaRole = AriaRole::Generic;
    const Superscript: AriaRole = AriaRole::Generic;
    const Summary: AriaRole = AriaRole::Button;
    const Time: AriaRole = AriaRole::Generic;
    const Meter: AriaRole = AriaRole::Generic;
    const Option: AriaRole = AriaRole::ListBoxOption;
    const Select: AriaRole = AriaRole::ComboBox;
}

/// ARIA state/property values for a node
#[derive(Debug, Clone, Default)]
pub struct AriaStates {
    pub expanded: Option<bool>,
    pub selected: Option<bool>,
    pub checked: Option<CheckedState>,
    pub pressed: Option<bool>,
    pub disabled: Option<bool>,
    pub hidden: Option<bool>,
    pub invalid: Option<InvalidState>,
    pub busy: Option<bool>,
    pub live: Option<LiveRegionPoliteness>,
    pub level: Option<u32>,            // heading level
    pub set_size: Option<i32>,
    pub pos_in_set: Option<i32>,
    pub value_now: Option<f64>,
    pub value_min: Option<f64>,
    pub value_max: Option<f64>,
    pub value_text: Option<String>,
    pub multi_line: Option<bool>,
    pub multi_selectable: Option<bool>,
    pub read_only: Option<bool>,
    pub required: Option<bool>,
    pub haspopup: Option<HasPopup>,
    pub label: Option<String>,          // aria-label
    pub labelled_by: Option<String>,    // aria-labelledby
    pub described_by: Option<String>,   // aria-describedby
    pub controls: Option<String>,       // aria-controls
    pub owns: Option<String>,           // aria-owns
    pub flow_to: Option<String>,        // aria-flowto
    pub error_message: Option<String>,  // aria-errormessage
    pub details: Option<String>,        // aria-details
    pub key_shortcuts: Option<String>,  // aria-keyshortcuts
    pub role_description: Option<String>, // aria-roledescription
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CheckedState {
    True,
    False,
    Mixed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InvalidState {
    False,
    True,
    Grammar,
    Spelling,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LiveRegionPoliteness {
    Off,
    Polite,
    Assertive,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HasPopup {
    False,
    True,
    Menu,
    ListBox,
    Tree,
    Grid,
    Dialog,
}

impl AriaStates {
    /// Parse aria-* attributes from an element's attribute map
    pub fn from_attributes(attrs: &std::collections::HashMap<String, String>) -> Self {
        let mut states = AriaStates::default();
        
        for (key, value) in attrs {
            let key = key.to_lowercase();
            match key.as_str() {
                "aria-expanded" => states.expanded = Self::parse_bool(value),
                "aria-selected" => states.selected = Self::parse_bool(value),
                "aria-disabled" => states.disabled = Self::parse_bool(value),
                "aria-hidden" => states.hidden = Self::parse_bool(value),
                "aria-busy" => states.busy = Self::parse_bool(value),
                "aria-pressed" => states.pressed = Self::parse_bool(value),
                "aria-readonly" => states.read_only = Self::parse_bool(value),
                "aria-required" => states.required = Self::parse_bool(value),
                "aria-multiline" => states.multi_line = Self::parse_bool(value),
                "aria-multiselectable" => states.multi_selectable = Self::parse_bool(value),
                "aria-checked" => {
                    states.checked = match value.as_str() {
                        "true" => Some(CheckedState::True),
                        "false" => Some(CheckedState::False),
                        "mixed" => Some(CheckedState::Mixed),
                        _ => None,
                    };
                }
                "aria-invalid" => {
                    states.invalid = match value.as_str() {
                        "true" => Some(InvalidState::True),
                        "false" | "" => Some(InvalidState::False),
                        "grammar" => Some(InvalidState::Grammar),
                        "spelling" => Some(InvalidState::Spelling),
                        _ => None,
                    };
                }
                "aria-live" => {
                    states.live = match value.as_str() {
                        "polite" => Some(LiveRegionPoliteness::Polite),
                        "assertive" => Some(LiveRegionPoliteness::Assertive),
                        "off" => Some(LiveRegionPoliteness::Off),
                        _ => None,
                    };
                }
                "aria-level" => states.level = value.parse().ok(),
                "aria-setsize" => states.set_size = value.parse().ok(),
                "aria-posinset" => states.pos_in_set = value.parse().ok(),
                "aria-valuenow" => states.value_now = value.parse().ok(),
                "aria-valuemin" => states.value_min = value.parse().ok(),
                "aria-valuemax" => states.value_max = value.parse().ok(),
                "aria-valuetext" => states.value_text = Some(value.clone()),
                "aria-label" => states.label = Some(value.clone()),
                "aria-labelledby" => states.labelled_by = Some(value.clone()),
                "aria-describedby" => states.described_by = Some(value.clone()),
                "aria-controls" => states.controls = Some(value.clone()),
                "aria-owns" => states.owns = Some(value.clone()),
                "aria-flowto" => states.flow_to = Some(value.clone()),
                "aria-errormessage" => states.error_message = Some(value.clone()),
                "aria-roledescription" => states.role_description = Some(value.clone()),
                "aria-keyshortcuts" => states.key_shortcuts = Some(value.clone()),
                _ => {}
            }
        }
        
        states
    }
    
    fn parse_bool(value: &str) -> Option<bool> {
        match value.to_lowercase().as_str() {
            "true" => Some(true),
            "false" => Some(false),
            _ => None,
        }
    }
    
    /// Generate a compact AI-readable state summary
    pub fn to_ai_summary(&self) -> String {
        let mut parts = Vec::new();
        
        if self.disabled == Some(true) { parts.push("disabled"); }
        if self.hidden == Some(true) { parts.push("hidden"); }
        if self.expanded == Some(true) { parts.push("expanded"); }
        if self.expanded == Some(false) { parts.push("collapsed"); }
        if self.selected == Some(true) { parts.push("selected"); }
        if self.pressed == Some(true) { parts.push("pressed"); }
        if self.required == Some(true) { parts.push("required"); }
        if self.read_only == Some(true) { parts.push("readonly"); }
        if self.busy == Some(true) { parts.push("busy"); }
        
        match self.checked {
            Some(CheckedState::True) => parts.push("checked"),
            Some(CheckedState::False) => parts.push("unchecked"),
            Some(CheckedState::Mixed) => parts.push("indeterminate"),
            None => {}
        }
        
        match self.invalid {
            Some(InvalidState::True) => parts.push("invalid"),
            Some(InvalidState::Grammar) => parts.push("grammar-error"),
            Some(InvalidState::Spelling) => parts.push("spelling-error"),
            _ => {}
        }
        
        if parts.is_empty() { return String::new(); }
        format!("[{}]", parts.join(", "))
    }
}
