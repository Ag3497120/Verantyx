//! Web Origins and Same-Origin Policy
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Origin { pub scheme: String, pub host: String, pub port: Option<u16> }
impl Origin {
    pub fn new(scheme: &str, host: &str, port: Option<u16>) -> Self { Self { scheme: scheme.to_string(), host: host.to_string(), port } }
    pub fn opaque() -> Self { Self { scheme: "null".to_string(), host: "".to_string(), port: None } }
    pub fn is_opaque(&self) -> bool { self.scheme == "null" }
    pub fn is_same_origin(&self, other: &Self) -> bool { self == other }
    pub fn is_same_site(&self, other: &Self) -> bool { self.host == other.host }
    pub fn serialize(&self) -> String {
        if let Some(p) = self.port { format!("{}://{}:{}", self.scheme, self.host, p) }
        else { format!("{}://{}", self.scheme, self.host) }
    }
    pub fn parse(url: &str) -> Option<Self> {
        let url = url.trim();
        let (scheme, rest) = url.split_once("://")?;
        let (host, port) = if let Some(h) = rest.split('/').next() {
            if let Some((h, p)) = h.split_once(':') { (h, p.parse().ok()) }
            else { (h, None) }
        } else { (rest, None) };
        Some(Self::new(scheme, host, port))
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SchemefulSite { pub scheme: String, pub host: String }
impl SchemefulSite {
    pub fn from_origin(o: &Origin) -> Self { Self { scheme: o.scheme.clone(), host: o.host.clone() } }
    pub fn is_same_site(&self, other: &Self) -> bool { self.scheme == other.scheme && self.host == other.host }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_origin_parse() {
        let o = Origin::parse("https://example.com").unwrap();
        assert_eq!(o.scheme, "https");
        assert_eq!(o.host, "example.com");
    }
    #[test]
    fn test_same_origin() {
        let a = Origin::parse("https://example.com").unwrap();
        let b = Origin::parse("https://example.com").unwrap();
        let c = Origin::parse("https://other.com").unwrap();
        assert!(a.is_same_origin(&b));
        assert!(!a.is_same_origin(&c));
    }
}
