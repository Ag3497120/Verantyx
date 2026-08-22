use regex::Regex;

pub struct PrivacyAuditor;

impl PrivacyAuditor {
    /// Mask hardcoded paths or API keys to protect user privacy before Community Export 
    pub fn sanitize_jcross(payload: &str) -> String {
        // Obfuscate /Users/* absolute paths down to [USER_HOME]/
        let home_regex = Regex::new(r"/Users/[a-zA-Z0-9_.-]+/?").unwrap();
        let mut sanitized = home_regex.replace_all(payload, "[USER_HOME]/").to_string();

        // Obfuscate Gemini / Claude keys
        let gemini_regex = Regex::new(r"AIzaSy[A-Za-z0-9_-]{33}").unwrap();
        sanitized = gemini_regex.replace_all(&sanitized, "[REDACTED_GEMINI_KEY]").to_string();

        sanitized
    }
}
