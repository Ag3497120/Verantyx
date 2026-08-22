//! CSS Parser stub (reference to cascade module)
//! Full parsing is handled by cascade::CssParser

/// Parse a CSS stylesheet string into tokens (for debugging/tooling)
pub fn tokenize(input: &str) -> Vec<CssToken> {
    let mut tokens = Vec::new();
    let mut pos = 0;
    let bytes = input.as_bytes();

    while pos < bytes.len() {
        // Skip whitespace
        if bytes[pos].is_ascii_whitespace() {
            let start = pos;
            while pos < bytes.len() && bytes[pos].is_ascii_whitespace() { pos += 1; }
            tokens.push(CssToken::Whitespace);
            continue;
        }

        // Comment
        if input[pos..].starts_with("/*") {
            if let Some(end) = input[pos+2..].find("*/") {
                let comment = &input[pos+2..pos+2+end];
                tokens.push(CssToken::Comment(comment.to_string()));
                pos += end + 4;
                continue;
            }
            break;
        }

        // String
        if bytes[pos] == b'"' || bytes[pos] == b'\'' {
            let quote = bytes[pos] as char;
            pos += 1;
            let start = pos;
            while pos < bytes.len() && bytes[pos] as char != quote { pos += 1; }
            tokens.push(CssToken::String(input[start..pos].to_string()));
            pos += 1;
            continue;
        }

        // Number
        if bytes[pos].is_ascii_digit() || (bytes[pos] == b'-' && pos + 1 < bytes.len() && bytes[pos+1].is_ascii_digit()) {
            let start = pos;
            if bytes[pos] == b'-' { pos += 1; }
            while pos < bytes.len() && (bytes[pos].is_ascii_digit() || bytes[pos] == b'.') { pos += 1; }
            let num_str = &input[start..pos];
            // Check for unit
            let unit_start = pos;
            while pos < bytes.len() && (bytes[pos].is_ascii_alphabetic() || bytes[pos] == b'%') { pos += 1; }
            let unit = &input[unit_start..pos];
            tokens.push(CssToken::Dimension(num_str.parse().unwrap_or(0.0), unit.to_string()));
            continue;
        }

        // Ident or keyword
        if bytes[pos].is_ascii_alphabetic() || bytes[pos] == b'-' || bytes[pos] == b'_' {
            let start = pos;
            while pos < bytes.len() && (bytes[pos].is_ascii_alphanumeric() || bytes[pos] == b'-' || bytes[pos] == b'_') { pos += 1; }
            let ident = &input[start..pos];
            if pos < bytes.len() && bytes[pos] == b'(' {
                tokens.push(CssToken::Function(ident.to_string()));
                pos += 1;
            } else {
                tokens.push(CssToken::Ident(ident.to_string()));
            }
            continue;
        }

        // Delimiters
        match bytes[pos] {
            b'{' => tokens.push(CssToken::LBrace),
            b'}' => tokens.push(CssToken::RBrace),
            b'(' => tokens.push(CssToken::LParen),
            b')' => tokens.push(CssToken::RParen),
            b'[' => tokens.push(CssToken::LBracket),
            b']' => tokens.push(CssToken::RBracket),
            b':' => tokens.push(CssToken::Colon),
            b';' => tokens.push(CssToken::Semicolon),
            b',' => tokens.push(CssToken::Comma),
            b'.' => tokens.push(CssToken::Dot),
            b'#' => tokens.push(CssToken::Hash),
            b'@' => tokens.push(CssToken::At),
            b'!' => tokens.push(CssToken::Bang),
            b'*' => tokens.push(CssToken::Asterisk),
            b'>' => tokens.push(CssToken::Greater),
            b'+' => tokens.push(CssToken::Plus),
            b'~' => tokens.push(CssToken::Tilde),
            b'|' => tokens.push(CssToken::Pipe),
            b'/' => tokens.push(CssToken::Slash),
            b'%' => tokens.push(CssToken::Percent),
            other => tokens.push(CssToken::Delim(other as char)),
        }
        pos += 1;
    }

    tokens
}

/// A CSS token
#[derive(Debug, Clone, PartialEq)]
pub enum CssToken {
    Ident(String),
    Function(String),
    String(String),
    Dimension(f32, String),
    Number(f32),
    Percentage(f32),
    Comment(String),
    Whitespace,
    LBrace, RBrace,
    LParen, RParen,
    LBracket, RBracket,
    Colon, Semicolon, Comma,
    Dot, Hash, At, Bang,
    Asterisk, Greater, Plus, Tilde, Pipe, Slash, Percent,
    Delim(char),
    Eof,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tokenize_simple() {
        let tokens = tokenize("div { color: red; }");
        assert!(tokens.iter().any(|t| matches!(t, CssToken::Ident(s) if s == "div")));
        assert!(tokens.iter().any(|t| matches!(t, CssToken::LBrace)));
        assert!(tokens.iter().any(|t| matches!(t, CssToken::Ident(s) if s == "color")));
    }

    #[test]
    fn test_tokenize_dimension() {
        let tokens = tokenize("16px");
        assert!(tokens.iter().any(|t| matches!(t, CssToken::Dimension(16.0, s) if s == "px")));
    }
}
