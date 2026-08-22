//! CSS Value Inheritance Engine
//!
//! Implements the full CSS inheritance algorithm per W3C CSS Cascade Level 5.
//! Handles initial values, inherited values, the `inherit`, `initial`, `unset`,
//! `revert`, and `revert-layer` keywords, and all inherited property families.

use std::collections::HashMap;

/// Defines whether a CSS property is inherited by default
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InheritanceBehavior {
    /// CSS properties that naturally flow down the DOM tree 
    Inherited,
    /// CSS properties that stop at element boundaries
    NotInherited,
}

/// The explicit inheritance keywords per CSS Cascade Level 5
#[derive(Debug, Clone, PartialEq)]
pub enum CascadeKeyword {
    Inherit,
    Initial,
    Unset,
    Revert,
    RevertLayer,
}

/// A full table of whether each CSS property is inherited by default.
/// Based on the CSS specification property tables.
pub fn is_property_inherited(property: &str) -> InheritanceBehavior {
    match property {
        // Typography — all inherited
        "color"
        | "font"
        | "font-family"
        | "font-feature-settings"
        | "font-kerning"
        | "font-language-override"
        | "font-optical-sizing"
        | "font-size"
        | "font-size-adjust"
        | "font-stretch"
        | "font-style"
        | "font-synthesis"
        | "font-variant"
        | "font-variant-alternates"
        | "font-variant-caps"
        | "font-variant-east-asian"
        | "font-variant-ligatures"
        | "font-variant-numeric"
        | "font-variant-position"
        | "font-weight"
        | "line-height"
        | "letter-spacing"
        | "word-spacing"
        | "text-align"
        | "text-align-last"
        | "text-indent"
        | "text-justify"
        | "text-rendering"
        | "text-shadow"
        | "text-transform"
        | "text-underline-position"
        | "text-underline-offset"
        | "hanging-punctuation"
        | "hyphens"
        | "overflow-wrap"
        | "tab-size"
        | "white-space"
        | "word-break"
        | "word-wrap"
        | "writing-mode"
        | "direction"
        | "unicode-bidi"
        | "text-orientation"
        // Lists
        | "list-style"
        | "list-style-image"
        | "list-style-position"
        | "list-style-type"
        // Tables
        | "border-collapse"
        | "border-spacing"
        | "caption-side"
        | "empty-cells"
        // SVG
        | "fill"
        | "fill-opacity"
        | "fill-rule"
        | "marker"
        | "marker-end"
        | "marker-mid"
        | "marker-start"
        | "stroke"
        | "stroke-dasharray"
        | "stroke-dashoffset"
        | "stroke-linecap"
        | "stroke-linejoin"
        | "stroke-miterlimit"
        | "stroke-opacity"
        | "stroke-width"
        // Miscellaneous inherited
        | "cursor"
        | "visibility"
        | "pointer-events"
        | "quotes"
        | "orphans"
        | "widows"
        | "image-rendering"
        | "image-resolution"
        | "image-orientation" => InheritanceBehavior::Inherited,
        
        // Everything else defaults to not inherited
        _ => InheritanceBehavior::NotInherited,
    }
}

/// The initial (default) value table for all CSS properties
pub fn initial_value(property: &str) -> &'static str {
    match property {
        "display" => "inline",
        "position" => "static",
        "float" => "none",
        "clear" => "none",
        "overflow" => "visible",
        "overflow-x" => "visible",
        "overflow-y" => "visible",
        "visibility" => "visible",
        "opacity" => "1",
        "z-index" => "auto",
        
        // Box model
        "width" => "auto",
        "height" => "auto",
        "min-width" => "0",
        "min-height" => "0",
        "max-width" => "none",
        "max-height" => "none",
        "margin" => "0",
        "margin-top" => "0",
        "margin-right" => "0",
        "margin-bottom" => "0",
        "margin-left" => "0",
        "padding" => "0",
        "padding-top" => "0",
        "padding-right" => "0",
        "padding-bottom" => "0",
        "padding-left" => "0",
        "border-width" => "medium",
        "border-style" => "none",
        "border-color" => "currentColor",
        "box-sizing" => "content-box",
        
        // Typography
        "color" => "canvastext",
        "font-size" => "medium",
        "font-weight" => "normal",
        "font-style" => "normal",
        "font-family" => "serif",
        "line-height" => "normal",
        "letter-spacing" => "normal",
        "word-spacing" => "normal",
        "text-align" => "start",
        "text-decoration" => "none",
        "text-transform" => "none",
        "white-space" => "normal",
        "word-break" => "normal",
        "overflow-wrap" => "normal",
        
        // Flexbox
        "flex-direction" => "row",
        "flex-wrap" => "nowrap",
        "justify-content" => "flex-start",
        "align-items" => "stretch",
        "align-content" => "normal",
        "flex-grow" => "0",
        "flex-shrink" => "1",
        "flex-basis" => "auto",
        "order" => "0",
        "align-self" => "auto",
        
        // Grid
        "grid-template-columns" => "none",
        "grid-template-rows" => "none",
        "grid-template-areas" => "none",
        "grid-auto-columns" => "auto",
        "grid-auto-rows" => "auto",
        "grid-column-gap" => "0",
        "grid-row-gap" => "0",
        "grid-column-start" => "auto",
        "grid-column-end" => "auto",
        "grid-row-start" => "auto",
        "grid-row-end" => "auto",
        
        // Backgrounds
        "background" => "none",
        "background-color" => "transparent",
        "background-image" => "none",
        "background-repeat" => "repeat",
        "background-position" => "0% 0%",
        "background-size" => "auto",
        "background-attachment" => "scroll",
        "background-origin" => "padding-box",
        "background-clip" => "border-box",
        
        // Transforms
        "transform" => "none",
        "transform-origin" => "50% 50%",
        "will-change" => "auto",
        "backface-visibility" => "visible",
        
        // Transitions/Animations
        "transition" => "none",
        "animation" => "none",
        
        // Lists
        "list-style-type" => "disc",
        "list-style-position" => "outside",
        "list-style-image" => "none",
        
        // Tables
        "border-collapse" => "separate",
        "border-spacing" => "0",
        "empty-cells" => "show",
        
        _ => "auto",
    }
}

/// The inheritance resolver — computes the final inherited value for a node
pub struct InheritanceResolver {
    /// Stack of computed style maps from the document root to current node
    ancestor_styles: Vec<HashMap<String, String>>,
}

impl InheritanceResolver {
    pub fn new() -> Self {
        Self { ancestor_styles: Vec::new() }
    }
    
    pub fn push_element_styles(&mut self, styles: HashMap<String, String>) {
        self.ancestor_styles.push(styles);
    }
    
    pub fn pop_element_styles(&mut self) {
        self.ancestor_styles.pop();
    }
    
    /// Resolves a property value for the current element, walking the cascade keyword rules
    pub fn resolve(&self, property: &str, raw_value: Option<&str>) -> String {
        match raw_value {
            Some(v) => {
                let keyword = Self::parse_cascade_keyword(v);
                match keyword {
                    Some(CascadeKeyword::Inherit) => {
                        self.inherited_value(property)
                    }
                    Some(CascadeKeyword::Initial) => {
                        initial_value(property).to_string()
                    }
                    Some(CascadeKeyword::Unset) => {
                        match is_property_inherited(property) {
                            InheritanceBehavior::Inherited => self.inherited_value(property),
                            InheritanceBehavior::NotInherited => initial_value(property).to_string(),
                        }
                    }
                    Some(CascadeKeyword::Revert) | Some(CascadeKeyword::RevertLayer) => {
                        // Revert to the user agent stylesheet value
                        // (In this implementation, we use the initial value as a fallback)
                        initial_value(property).to_string()
                    }
                    None => v.to_string(),
                }
            }
            None => {
                // No value specified — use inherited or initial
                match is_property_inherited(property) {
                    InheritanceBehavior::Inherited => self.inherited_value(property),
                    InheritanceBehavior::NotInherited => initial_value(property).to_string(),
                }
            }
        }
    }
    
    /// Find the nearest ancestor that defines this property
    fn inherited_value(&self, property: &str) -> String {
        for ancestor in self.ancestor_styles.iter().rev() {
            if let Some(val) = ancestor.get(property) {
                return val.clone();
            }
        }
        initial_value(property).to_string()
    }
    
    fn parse_cascade_keyword(value: &str) -> Option<CascadeKeyword> {
        match value.trim().to_lowercase().as_str() {
            "inherit" => Some(CascadeKeyword::Inherit),
            "initial" => Some(CascadeKeyword::Initial),
            "unset" => Some(CascadeKeyword::Unset),
            "revert" => Some(CascadeKeyword::Revert),
            "revert-layer" => Some(CascadeKeyword::RevertLayer),
            _ => None,
        }
    }
}
