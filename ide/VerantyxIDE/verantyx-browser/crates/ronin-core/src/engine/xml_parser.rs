use crate::domain::error::{Result, RoninError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct XmlPayload {
    pub tag: String,
    pub content: String,
}

/// A zero-copy ultra fast xml block parser.
/// Extracts content embedded between <tag> and </tag>.
pub fn extract_xml_tag(input: &str, target_tag: &str) -> Option<XmlPayload> {
    let open = format!("<{}>", target_tag);
    let close = format!("</{}>", target_tag);

    let start = input.find(&open[..])? + open.len();
    let end = input[start..].find(&close[..])? + start;
    let content = input[start..end].to_string();

    Some(XmlPayload { tag: target_tag.to_string(), content })
}

pub fn parse_llm_stream(stream: &str) -> Result<XmlPayload> {
    extract_xml_tag(stream, "action").ok_or_else(|| {
        RoninError::XmlStreamParse("Failed to locate valid <action> structure in LLM output stream".to_string())
    })
}
