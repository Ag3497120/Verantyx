//! Address bar helpers
pub fn complete_url(partial: &str, history: &[String]) -> Option<String> {
    history.iter().find(|h| h.starts_with(partial)).cloned()
}
