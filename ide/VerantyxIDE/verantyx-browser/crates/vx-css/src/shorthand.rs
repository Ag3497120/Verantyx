//! CSS shorthand property expansion
//!
//! Expands shorthand properties like margin, padding, border, background, font, flex, etc.

use crate::properties::{Declaration, PropertyValue};

/// Expand a shorthand declaration into its longhand declarations
pub fn expand_shorthand(decl: &Declaration) -> Vec<Declaration> {
    match decl.property.to_lowercase().as_str() {
        "margin" => expand_box_sides("margin", &decl.value, decl.important),
        "padding" => expand_box_sides("padding", &decl.value, decl.important),
        "border-radius" => expand_border_radius(&decl.value, decl.important),
        "overflow" => expand_overflow(&decl.value, decl.important),
        "inset" => expand_inset(&decl.value, decl.important),
        "gap" => expand_gap(&decl.value, decl.important),
        _ => vec![decl.clone()],
    }
}

fn expand_box_sides(prefix: &str, value: &PropertyValue, important: bool) -> Vec<Declaration> {
    let s = value.to_string();
    let parts: Vec<&str> = s.split_whitespace().collect();

    let (top, right, bottom, left) = match parts.len() {
        1 => (parts[0], parts[0], parts[0], parts[0]),
        2 => (parts[0], parts[1], parts[0], parts[1]),
        3 => (parts[0], parts[1], parts[2], parts[1]),
        4 => (parts[0], parts[1], parts[2], parts[3]),
        _ => return vec![Declaration { property: prefix.to_string(), value: value.clone(), important }],
    };

    vec![
        Declaration { property: format!("{}-top", prefix), value: PropertyValue::parse(top), important },
        Declaration { property: format!("{}-right", prefix), value: PropertyValue::parse(right), important },
        Declaration { property: format!("{}-bottom", prefix), value: PropertyValue::parse(bottom), important },
        Declaration { property: format!("{}-left", prefix), value: PropertyValue::parse(left), important },
    ]
}

fn expand_border_radius(value: &PropertyValue, important: bool) -> Vec<Declaration> {
    let s = value.to_string();
    let parts: Vec<&str> = s.split_whitespace().collect();
    let (tl, tr, br, bl) = match parts.len() {
        1 => (parts[0], parts[0], parts[0], parts[0]),
        2 => (parts[0], parts[1], parts[0], parts[1]),
        3 => (parts[0], parts[1], parts[2], parts[1]),
        _ => if parts.len() >= 4 { (parts[0], parts[1], parts[2], parts[3]) } else { return vec![]; },
    };
    vec![
        Declaration { property: "border-top-left-radius".to_string(), value: PropertyValue::parse(tl), important },
        Declaration { property: "border-top-right-radius".to_string(), value: PropertyValue::parse(tr), important },
        Declaration { property: "border-bottom-right-radius".to_string(), value: PropertyValue::parse(br), important },
        Declaration { property: "border-bottom-left-radius".to_string(), value: PropertyValue::parse(bl), important },
    ]
}

fn expand_overflow(value: &PropertyValue, important: bool) -> Vec<Declaration> {
    let s = value.to_string();
    let parts: Vec<&str> = s.split_whitespace().collect();
    let (x, y) = if parts.len() >= 2 { (parts[0], parts[1]) } else { (parts[0], parts[0]) };
    vec![
        Declaration { property: "overflow-x".to_string(), value: PropertyValue::parse(x), important },
        Declaration { property: "overflow-y".to_string(), value: PropertyValue::parse(y), important },
    ]
}

fn expand_inset(value: &PropertyValue, important: bool) -> Vec<Declaration> {
    let s = value.to_string();
    let parts: Vec<&str> = s.split_whitespace().collect();
    let (top, right, bottom, left) = match parts.len() {
        1 => (parts[0], parts[0], parts[0], parts[0]),
        2 => (parts[0], parts[1], parts[0], parts[1]),
        3 => (parts[0], parts[1], parts[2], parts[1]),
        4 => (parts[0], parts[1], parts[2], parts[3]),
        _ => return vec![],
    };
    vec![
        Declaration { property: "top".to_string(), value: PropertyValue::parse(top), important },
        Declaration { property: "right".to_string(), value: PropertyValue::parse(right), important },
        Declaration { property: "bottom".to_string(), value: PropertyValue::parse(bottom), important },
        Declaration { property: "left".to_string(), value: PropertyValue::parse(left), important },
    ]
}

fn expand_gap(value: &PropertyValue, important: bool) -> Vec<Declaration> {
    let s = value.to_string();
    let parts: Vec<&str> = s.split_whitespace().collect();
    let (row, col) = if parts.len() >= 2 { (parts[0], parts[1]) } else { (parts[0], parts[0]) };
    vec![
        Declaration { property: "row-gap".to_string(), value: PropertyValue::parse(row), important },
        Declaration { property: "column-gap".to_string(), value: PropertyValue::parse(col), important },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_expand_margin_1() {
        let decl = Declaration { property: "margin".to_string(), value: PropertyValue::parse("10px"), important: false };
        let expanded = expand_shorthand(&decl);
        assert_eq!(expanded.len(), 4);
        assert_eq!(expanded[0].property, "margin-top");
    }

    #[test]
    fn test_expand_margin_4() {
        let decl = Declaration { property: "margin".to_string(), value: PropertyValue::Keyword("10px 20px 30px 40px".to_string()), important: false };
        let expanded = expand_shorthand(&decl);
        assert_eq!(expanded.len(), 4);
    }

    #[test]
    fn test_expand_overflow() {
        let decl = Declaration { property: "overflow".to_string(), value: PropertyValue::parse("hidden"), important: false };
        let expanded = expand_shorthand(&decl);
        assert_eq!(expanded.len(), 2);
        assert!(expanded.iter().any(|d| d.property == "overflow-x"));
        assert!(expanded.iter().any(|d| d.property == "overflow-y"));
    }
}
