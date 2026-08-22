//! vx-css — Complete CSS Engine for Verantyx Browser
//!
//! This crate implements the full CSS specification including:
//! - CSS Selectors Level 4
//! - CSS Cascade & Inheritance (Level 5)
//! - CSS Custom Properties (Variables)
//! - CSS Media Queries Level 4
//! - CSS Animations & Transitions
//! - CSS Color (all formats)
//! - CSS Values & Units Level 4

pub mod selector;
pub mod cascade;
pub mod cascade_v2;
pub mod computed;
pub mod properties;
pub mod parser;
pub mod media;
pub mod variables;
pub mod animation;
pub mod color;
pub mod units;
pub mod specificity;
pub mod inheritance;
pub mod shorthand;
pub mod pseudo;
pub mod at_rules;
pub mod transform;
pub mod animation_timeline;
pub mod selector_engine_v2;
pub mod custom_properties;

pub use cascade_v2::{resolve_cascade, CssDeclaration, CascadeOrigin, BaseOrigin};
pub use computed::ComputedStyle;
pub use properties::{CssProperty, PropertyValue};
pub use selector::{Selector, SelectorList, SelectorComponent, Combinator};
pub use color::CssColor;
pub use units::{Length, LengthUnit, Percentage, CssValue};
pub use media::{MediaQuery, MediaFeature, MediaType};
pub use variables::{CustomProperties, CssVariableMap};
pub use animation::{Animation, Transition, TimingFunction};

/// CSS parse error
#[derive(Debug, Clone, thiserror::Error)]
pub enum CssError {
    #[error("Parse error at position {pos}: {message}")]
    ParseError { pos: usize, message: String },
    #[error("Invalid selector: {0}")]
    InvalidSelector(String),
    #[error("Unknown property: {0}")]
    UnknownProperty(String),
    #[error("Invalid value for property {property}: {value}")]
    InvalidValue { property: String, value: String },
    #[error("Circular variable reference: {0}")]
    CircularVariable(String),
}

pub type CssResult<T> = Result<T, CssError>;
pub mod media_query_v2;
pub mod transition_engine;
pub mod counter_styles;
pub mod paint_worklet;
pub mod animation_engine;
pub mod logical_properties;
pub mod selectors_level4;
pub mod fonts_level4;
pub mod scroll_snap;
pub mod view_transitions;
pub mod css_scoping;
pub mod view_transitions_2;
pub mod css_nesting_1;
pub mod css_rhythm_1;
pub mod css_fonts_5;
pub mod css_conditional_4;
pub mod css_pseudo_4;
pub mod css_viewport_1;
pub mod css_speech_1;
pub mod css_box_align_3;
pub mod css_scroll_snap_1;
pub mod css_text_3;
pub mod css_images_4;
pub mod css_color_6;
pub mod css_transforms_2;
pub mod css_borders_4;
pub mod css_shadow_parts;
pub mod css_animations_2;
pub mod css_ruby_1;
pub mod css_overscroll_1;
pub mod css_fonts_4;
pub mod css_typed_om_1;
pub mod css_anchor_1;
pub mod css_transitions_2;
pub mod css_conditional_5;
pub mod css_view_transitions_1;
pub mod css_cascade_6;
pub mod css_text_4;
pub mod css_values_4;
pub mod css_env_variables;
pub mod css_properties_and_values_1;
pub mod masking_level1;
pub mod shapes_level1;
pub mod containment_level2;
pub mod will_change;
pub mod text_decoration_level4;
pub mod scroll_animations;
pub mod round_display_level1;
pub mod grid_level3;
pub mod fill_stroke_level3;
pub mod env_variables;
pub mod spatial_navigation;
pub mod overscroll_behavior;
pub mod animations_level2;
pub mod css_paint_api;
pub mod css_typed_om;
pub mod css_highlight_api;
