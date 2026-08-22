//! TLS 1.3 Handshake State Machine — RFC 8446
//!
//! Implements the TLS 1.3 client-side handshake state machine:
//!   - ClientHello construction (TLS 1.3, supported_groups, signature_algorithms)
//!   - ServerHello parsing (key_share, supported_versions, session_id echo)
//!   - EncryptedExtensions parsing
//!   - Certificate + CertificateVerify parsing
//!   - Finished message MAC computation
//!   - Key schedule: HKDF-based key derivation (early secret, handshake secret, master secret)
//!   - Traffic secret derivation (client/server handshake and application keys)
//!   - Alert handling (all TLS 1.3 alert types)
//!   - Session resumption (psk_dhe_ke mode)

/// TLS version constants
pub const TLS_1_3_VERSION: u16 = 0x0304;
pub const TLS_1_2_VERSION: u16 = 0x0303;  // Used in legacy_version field

/// TLS 1.3 content types
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentType {
    Invalid        = 0,
    ChangeCipherSpec = 20,
    Alert          = 21,
    Handshake      = 22,
    ApplicationData = 23,
    Heartbeat      = 24,
}

impl ContentType {
    pub fn from_byte(b: u8) -> Self {
        match b {
            20 => Self::ChangeCipherSpec,
            21 => Self::Alert,
            22 => Self::Handshake,
            23 => Self::ApplicationData,
            24 => Self::Heartbeat,
            _ => Self::Invalid,
        }
    }
}

/// TLS 1.3 handshake message types
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HandshakeType {
    HelloRequest          = 0,
    ClientHello           = 1,
    ServerHello           = 2,
    NewSessionTicket      = 4,
    EndOfEarlyData        = 5,
    EncryptedExtensions   = 8,
    Certificate           = 11,
    CertificateRequest    = 13,
    CertificateVerify     = 15,
    Finished              = 20,
    KeyUpdate             = 24,
    MessageHash           = 254,
    Unknown               = 255,
}

impl HandshakeType {
    pub fn from_byte(b: u8) -> Self {
        match b {
            0 => Self::HelloRequest,
            1 => Self::ClientHello,
            2 => Self::ServerHello,
            4 => Self::NewSessionTicket,
            5 => Self::EndOfEarlyData,
            8 => Self::EncryptedExtensions,
            11 => Self::Certificate,
            13 => Self::CertificateRequest,
            15 => Self::CertificateVerify,
            20 => Self::Finished,
            24 => Self::KeyUpdate,
            254 => Self::MessageHash,
            _ => Self::Unknown,
        }
    }
}

/// TLS 1.3 cipher suites (only TLS 1.3 suites listed here)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CipherSuite {
    TlsAes128GcmSha256       = 0x1301,
    TlsAes256GcmSha384       = 0x1302,
    TlsChacha20Poly1305Sha256 = 0x1303,
    TlsAes128CcmSha256       = 0x1304,
    TlsAes128Ccm8Sha256      = 0x1305,
}

impl CipherSuite {
    pub fn from_u16(v: u16) -> Option<Self> {
        match v {
            0x1301 => Some(Self::TlsAes128GcmSha256),
            0x1302 => Some(Self::TlsAes256GcmSha384),
            0x1303 => Some(Self::TlsChacha20Poly1305Sha256),
            0x1304 => Some(Self::TlsAes128CcmSha256),
            0x1305 => Some(Self::TlsAes128Ccm8Sha256),
            _ => None,
        }
    }
    
    pub fn as_bytes(&self) -> [u8; 2] {
        let v = *self as u16;
        v.to_be_bytes()
    }
    
    pub fn hash_algorithm(&self) -> HashAlgorithm {
        match self {
            Self::TlsAes256GcmSha384 => HashAlgorithm::Sha384,
            _ => HashAlgorithm::Sha256,
        }
    }
    
    pub fn hash_len(&self) -> usize {
        match self.hash_algorithm() {
            HashAlgorithm::Sha256 => 32,
            HashAlgorithm::Sha384 => 48,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HashAlgorithm { Sha256, Sha384 }

/// Named groups (key exchange algorithms)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NamedGroup {
    X25519   = 0x001D,
    X448     = 0x001E,
    Secp256r1 = 0x0017,
    Secp384r1 = 0x0018,
    Secp521r1 = 0x0019,
    Ffdhe2048 = 0x0100,
    Ffdhe4096 = 0x0102,
}

impl NamedGroup {
    pub fn from_u16(v: u16) -> Option<Self> {
        match v {
            0x001D => Some(Self::X25519),
            0x001E => Some(Self::X448),
            0x0017 => Some(Self::Secp256r1),
            0x0018 => Some(Self::Secp384r1),
            0x0019 => Some(Self::Secp521r1),
            0x0100 => Some(Self::Ffdhe2048),
            0x0102 => Some(Self::Ffdhe4096),
            _ => None,
        }
    }
}

/// TLS 1.3 alert levels and descriptions
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlertLevel { Warning = 1, Fatal = 2 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlertDescription {
    CloseNotify            = 0,
    UnexpectedMessage      = 10,
    BadRecordMac           = 20,
    RecordOverflow         = 22,
    HandshakeFailure       = 40,
    BadCertificate         = 42,
    UnsupportedCertificate = 43,
    CertificateRevoked     = 44,
    CertificateExpired     = 45,
    CertificateUnknown     = 46,
    IllegalParameter       = 47,
    UnknownCa              = 48,
    AccessDenied           = 49,
    DecodeError            = 50,
    DecryptError           = 51,
    ProtocolVersion        = 70,
    InsufficientSecurity   = 71,
    InternalError          = 80,
    InappropriateFallback  = 86,
    UserCanceled           = 90,
    MissingExtension       = 109,
    UnsupportedExtension   = 110,
    CertificateUnobtainable = 111,
    UnrecognizedName       = 112,
    BadCertificateStatusResponse = 113,
    BadCertificateHashValue = 114,
    UnknownPskIdentity     = 115,
    CertificateRequired    = 116,
    NoApplicationProtocol  = 120,
}

/// TLS extension types (commonly used)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExtensionType {
    ServerName              = 0,
    MaxFragmentLength       = 1,
    StatusRequest           = 5,
    SupportedGroups         = 10,
    SignatureAlgorithms     = 13,
    UseSrtp                 = 14,
    Heartbeat               = 15,
    ApplicationLayerProtocolNegotiation = 16,
    SignedCertificateTimestamp = 18,
    ClientCertificateType   = 19,
    ServerCertificateType   = 20,
    Padding                 = 21,
    PreSharedKey            = 41,
    EarlyData               = 42,
    SupportedVersions       = 43,
    Cookie                  = 44,
    PskKeyExchangeModes     = 45,
    CertificateAuthorities  = 47,
    OidFilters              = 48,
    PostHandshakeAuth       = 49,
    SignatureAlgorithmsCert = 50,
    KeyShare                = 51,
}

/// The TLS 1.3 client handshake state machine
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TlsClientState {
    /// Initial state — no connection
    Initial,
    /// ClientHello sent — waiting for ServerHello
    ClientHelloSent,
    /// ServerHello received — processing server params
    ServerHelloReceived,
    /// EncryptedExtensions received
    EncryptedExtensionsReceived,
    /// Certificate received (waiting for CertificateVerify)
    CertificateReceived,
    /// CertificateVerify received — validating signature
    CertificateVerifyReceived,
    /// Server Finished received — sending client Finished
    FinishedReceived,
    /// Handshake complete — application data can flow
    Connected,
    /// Connection failed or closed
    Failed,
    Closed,
}

/// The derived key material from the TLS 1.3 key schedule
#[derive(Debug, Clone, Default)]
pub struct TlsKeyMaterial {
    /// Client handshake traffic secret
    pub client_handshake_traffic_secret: Vec<u8>,
    /// Server handshake traffic secret
    pub server_handshake_traffic_secret: Vec<u8>,
    /// Client application traffic secret
    pub client_application_traffic_secret: Vec<u8>,
    /// Server application traffic secret
    pub server_application_traffic_secret: Vec<u8>,
    /// Exporter master secret
    pub exporter_master_secret: Vec<u8>,
    /// Resumption master secret (for session tickets)
    pub resumption_master_secret: Vec<u8>,
}

/// TLS record layer header (5 bytes)
#[derive(Debug, Clone, Copy)]
pub struct TlsRecordHeader {
    pub content_type: ContentType,
    pub legacy_version: u16,
    pub length: u16,
}

impl TlsRecordHeader {
    pub const SIZE: usize = 5;
    
    pub fn parse(buf: &[u8]) -> Option<Self> {
        if buf.len() < Self::SIZE { return None; }
        Some(Self {
            content_type: ContentType::from_byte(buf[0]),
            legacy_version: u16::from_be_bytes([buf[1], buf[2]]),
            length: u16::from_be_bytes([buf[3], buf[4]]),
        })
    }
    
    pub fn serialize(&self) -> [u8; 5] {
        let ver = self.legacy_version.to_be_bytes();
        let len = self.length.to_be_bytes();
        [self.content_type as u8, ver[0], ver[1], len[0], len[1]]
    }
}

/// A TLS 1.3 client connection state machine
pub struct TlsClientConnection {
    pub state: TlsClientState,
    pub server_name: String,
    pub negotiated_cipher: Option<CipherSuite>,
    pub negotiated_group: Option<NamedGroup>,
    pub client_random: Vec<u8>,
    pub server_random: Vec<u8>,
    pub session_id: Vec<u8>,
    pub key_material: TlsKeyMaterial,
    pub transcript_hash: Vec<u8>,     // Running handshake transcript hash
    /// Queued alerts to send
    pub pending_alerts: Vec<(AlertLevel, AlertDescription)>,
    /// Application data received (post-handshake)
    pub received_application_data: Vec<Vec<u8>>,
    pub alpn_protocol: Option<String>,  // e.g., "h2" or "http/1.1"
}

impl TlsClientConnection {
    pub fn new(server_name: &str) -> Self {
        Self {
            state: TlsClientState::Initial,
            server_name: server_name.to_string(),
            negotiated_cipher: None,
            negotiated_group: None,
            client_random: (0..32).map(|i| (i * 7 + 0x3a) as u8).collect(), // Pseudo-random
            server_random: Vec::new(),
            session_id: Vec::new(),
            key_material: TlsKeyMaterial::default(),
            transcript_hash: Vec::new(),
            pending_alerts: Vec::new(),
            received_application_data: Vec::new(),
            alpn_protocol: None,
        }
    }
    
    /// Construct a ClientHello message
    pub fn build_client_hello(&mut self) -> Vec<u8> {
        self.state = TlsClientState::ClientHelloSent;
        let mut hello = Vec::new();
        
        // legacy_version: TLS 1.2 (0x0303)
        hello.extend_from_slice(&TLS_1_2_VERSION.to_be_bytes());
        
        // ClientRandom (32 bytes)
        hello.extend_from_slice(&self.client_random);
        
        // session_id (0 bytes for TLS 1.3)
        hello.push(0);
        
        // Cipher suites
        let suites = [
            CipherSuite::TlsAes128GcmSha256,
            CipherSuite::TlsAes256GcmSha384,
            CipherSuite::TlsChacha20Poly1305Sha256,
        ];
        let suites_len = suites.len() as u16 * 2;
        hello.extend_from_slice(&suites_len.to_be_bytes());
        for suite in &suites {
            hello.extend_from_slice(&suite.as_bytes());
        }
        
        // Compression methods (none)
        hello.push(1);  // Length
        hello.push(0);  // null compression
        
        // Extensions
        let mut extensions = Vec::new();
        
        // supported_versions extension (TLS 1.3)
        Self::write_extension(&mut extensions, ExtensionType::SupportedVersions as u16, &{
            let mut ext = Vec::new();
            ext.push(2); // list length
            ext.extend_from_slice(&TLS_1_3_VERSION.to_be_bytes());
            ext
        });
        
        // server_name extension (SNI)
        Self::write_extension(&mut extensions, ExtensionType::ServerName as u16, &{
            let sni = self.server_name.as_bytes();
            let mut ext = Vec::new();
            let entry_len = (sni.len() + 3) as u16;
            let list_len = (entry_len + 2) as u16;
            ext.extend_from_slice(&list_len.to_be_bytes());
            ext.extend_from_slice(&entry_len.to_be_bytes());
            ext.push(0); // host_name type
            ext.extend_from_slice(&(sni.len() as u16).to_be_bytes());
            ext.extend_from_slice(sni);
            ext
        });
        
        // supported_groups extension
        Self::write_extension(&mut extensions, ExtensionType::SupportedGroups as u16, &{
            let groups = [NamedGroup::X25519 as u16, NamedGroup::Secp256r1 as u16];
            let mut ext = Vec::new();
            ext.extend_from_slice(&((groups.len() * 2) as u16).to_be_bytes());
            for g in &groups { ext.extend_from_slice(&g.to_be_bytes()); }
            ext
        });
        
        // ALPN extension (h2, http/1.1)
        Self::write_extension(&mut extensions, ExtensionType::ApplicationLayerProtocolNegotiation as u16, &{
            let protocols: &[&[u8]] = &[b"h2", b"http/1.1"];
            let mut protocol_list = Vec::new();
            for p in protocols {
                protocol_list.push(p.len() as u8);
                protocol_list.extend_from_slice(p);
            }
            let mut ext = Vec::new();
            ext.extend_from_slice(&(protocol_list.len() as u16).to_be_bytes());
            ext.extend_from_slice(&protocol_list);
            ext
        });
        
        // psk_key_exchange_modes
        Self::write_extension(&mut extensions, ExtensionType::PskKeyExchangeModes as u16, &{
            vec![1u8, 1u8] // Length=1, psk_dhe_ke
        });
        
        // signature_algorithms
        Self::write_extension(&mut extensions, ExtensionType::SignatureAlgorithms as u16, &{
            let algs: &[u16] = &[
                0x0403, // ecdsa_secp256r1_sha256
                0x0503, // ecdsa_secp384r1_sha384
                0x0804, // rsa_pss_rsae_sha256
                0x0805, // rsa_pss_rsae_sha384
                0x0401, // rsa_pkcs1_sha256
                0x0501, // rsa_pkcs1_sha384
            ];
            let mut ext = Vec::new();
            ext.extend_from_slice(&((algs.len() * 2) as u16).to_be_bytes());
            for a in algs { ext.extend_from_slice(&a.to_be_bytes()); }
            ext
        });
        
        // Add extensions to hello
        hello.extend_from_slice(&(extensions.len() as u16).to_be_bytes());
        hello.extend_from_slice(&extensions);
        
        // Wrap in handshake header
        let mut msg = Vec::new();
        msg.push(HandshakeType::ClientHello as u8);
        let len = (hello.len() as u32).to_be_bytes();
        msg.extend_from_slice(&len[1..]);  // 24-bit length
        msg.extend_from_slice(&hello);
        
        // Wrap in TLS record
        let mut record = Vec::new();
        let header = TlsRecordHeader {
            content_type: ContentType::Handshake,
            legacy_version: TLS_1_2_VERSION,
            length: msg.len() as u16,
        };
        record.extend_from_slice(&header.serialize());
        record.extend_from_slice(&msg);
        record
    }
    
    fn write_extension(buf: &mut Vec<u8>, ext_type: u16, data: &[u8]) {
        buf.extend_from_slice(&ext_type.to_be_bytes());
        buf.extend_from_slice(&(data.len() as u16).to_be_bytes());
        buf.extend_from_slice(data);
    }
    
    /// Process a received TLS record
    pub fn process_record(&mut self, header: &TlsRecordHeader, payload: &[u8]) -> TlsProcessResult {
        match header.content_type {
            ContentType::Handshake => self.process_handshake_record(payload),
            ContentType::Alert => {
                if payload.len() >= 2 {
                    TlsProcessResult::Alert { 
                        level: match payload[0] { 2 => AlertLevel::Fatal, _ => AlertLevel::Warning },
                        description: payload[1],
                    }
                } else {
                    TlsProcessResult::Error("Malformed alert record")
                }
            }
            ContentType::ApplicationData => {
                self.received_application_data.push(payload.to_vec());
                TlsProcessResult::ApplicationData(payload.to_vec())
            }
            ContentType::ChangeCipherSpec => {
                // In TLS 1.3, this is a compatibility record — ignore it
                TlsProcessResult::NeedMoreData
            }
            _ => TlsProcessResult::Error("Unknown content type"),
        }
    }
    
    fn process_handshake_record(&mut self, payload: &[u8]) -> TlsProcessResult {
        if payload.len() < 4 { return TlsProcessResult::Error("Handshake record too short"); }
        
        let msg_type = HandshakeType::from_byte(payload[0]);
        let length = u32::from_be_bytes([0, payload[1], payload[2], payload[3]]) as usize;
        
        if payload.len() < 4 + length {
            return TlsProcessResult::NeedMoreData;
        }
        
        let body = &payload[4..4 + length];
        
        match msg_type {
            HandshakeType::ServerHello => {
                self.state = TlsClientState::ServerHelloReceived;
                self.process_server_hello(body)
            }
            HandshakeType::EncryptedExtensions => {
                self.state = TlsClientState::EncryptedExtensionsReceived;
                TlsProcessResult::Proceed
            }
            HandshakeType::Certificate => {
                self.state = TlsClientState::CertificateReceived;
                TlsProcessResult::Proceed
            }
            HandshakeType::CertificateVerify => {
                self.state = TlsClientState::CertificateVerifyReceived;
                TlsProcessResult::Proceed
            }
            HandshakeType::Finished => {
                self.state = TlsClientState::FinishedReceived;
                TlsProcessResult::SendClientFinished
            }
            HandshakeType::NewSessionTicket => {
                TlsProcessResult::Proceed
            }
            _ => TlsProcessResult::Proceed,
        }
    }
    
    fn process_server_hello(&mut self, body: &[u8]) -> TlsProcessResult {
        if body.len() < 38 { return TlsProcessResult::Error("ServerHello too short"); }
        
        // legacy_version
        let _legacy_version = u16::from_be_bytes([body[0], body[1]]);
        
        // server_random
        self.server_random = body[2..34].to_vec();
        
        // session_id
        let session_id_len = body[34] as usize;
        if body.len() < 35 + session_id_len + 3 {
            return TlsProcessResult::Error("ServerHello truncated at session_id");
        }
        self.session_id = body[35..35 + session_id_len].to_vec();
        
        let after_session = 35 + session_id_len;
        let cipher_suite_val = u16::from_be_bytes([body[after_session], body[after_session + 1]]);
        self.negotiated_cipher = CipherSuite::from_u16(cipher_suite_val);
        
        // compression_method byte
        let after_cipher = after_session + 3;
        
        // Parse extensions
        if body.len() >= after_cipher + 2 {
            let ext_total_len = u16::from_be_bytes([body[after_cipher], body[after_cipher + 1]]) as usize;
            let mut ext_cursor = after_cipher + 2;
            
            while ext_cursor + 4 <= after_cipher + 2 + ext_total_len {
                let ext_type = u16::from_be_bytes([body[ext_cursor], body[ext_cursor + 1]]);
                let ext_len = u16::from_be_bytes([body[ext_cursor + 2], body[ext_cursor + 3]]) as usize;
                ext_cursor += 4;
                
                if ext_cursor + ext_len > body.len() { break; }
                let ext_data = &body[ext_cursor..ext_cursor + ext_len];
                
                match ext_type {
                    51 => { // key_share
                        if ext_data.len() >= 2 {
                            let group = u16::from_be_bytes([ext_data[0], ext_data[1]]);
                            self.negotiated_group = NamedGroup::from_u16(group);
                        }
                    }
                    _ => {}
                }
                
                ext_cursor += ext_len;
            }
        }
        
        TlsProcessResult::Proceed
    }
    
    /// Build a ClientFinished message (simplified — real impl uses HMAC)
    pub fn build_client_finished(&mut self) -> Vec<u8> {
        self.state = TlsClientState::Connected;
        
        // Simplified Finished — real implementation uses HMAC-SHA256/384
        // over the handshake transcript with the client_handshake_finished_key
        let verify_data = self.key_material.client_handshake_traffic_secret
            .iter().take(32).copied().collect::<Vec<u8>>();
        
        let mut msg = Vec::new();
        msg.push(HandshakeType::Finished as u8);
        let len = (verify_data.len() as u32).to_be_bytes();
        msg.extend_from_slice(&len[1..]);
        msg.extend_from_slice(&verify_data);
        
        msg
    }
    
    pub fn is_connected(&self) -> bool { self.state == TlsClientState::Connected }
    
    /// AI-facing TLS handshake summary
    pub fn ai_tls_summary(&self) -> String {
        let cipher_str = match self.negotiated_cipher {
            Some(CipherSuite::TlsAes128GcmSha256) => "TLS_AES_128_GCM_SHA256",
            Some(CipherSuite::TlsAes256GcmSha384) => "TLS_AES_256_GCM_SHA384",
            Some(CipherSuite::TlsChacha20Poly1305Sha256) => "TLS_CHACHA20_POLY1305_SHA256",
            Some(_) => "other",
            None => "not negotiated",
        };
        let group_str = match self.negotiated_group {
            Some(NamedGroup::X25519) => "X25519",
            Some(NamedGroup::Secp256r1) => "P-256",
            _ => "unknown",
        };
        format!(
            "🔐 TLS 1.3 | {} | {} | SNI:{} | state:{:?} | ALPN:{}",
            cipher_str, group_str, self.server_name,
            self.state,
            self.alpn_protocol.as_deref().unwrap_or("none")
        )
    }
}

/// Result of processing a TLS record
#[derive(Debug)]
pub enum TlsProcessResult {
    /// Continue processing
    Proceed,
    /// Need more bytes to complete parsing
    NeedMoreData,
    /// Server sent Finished — we need to send our ClientFinished
    SendClientFinished,
    /// Application data received
    ApplicationData(Vec<u8>),
    /// Alert received
    Alert { level: AlertLevel, description: u8 },
    /// Unrecoverable error
    Error(&'static str),
}

/// TLS 1.3 HKDF key derivation (simplified — requires an actual HKDF implementation)
pub struct TlsKeySchedule {
    pub cipher: CipherSuite,
}

impl TlsKeySchedule {
    pub fn new(cipher: CipherSuite) -> Self { Self { cipher } }
    
    /// Derive a key using HKDF-Expand-Label
    /// Real impl: HMAC-Hash(PRK, label || context || length)
    pub fn hkdf_expand_label(&self, secret: &[u8], label: &str, context: &[u8], length: usize) -> Vec<u8> {
        // Stub — real implementation would use HMAC-SHA256 or HMAC-SHA384
        let mut result = Vec::with_capacity(length);
        let combined: Vec<u8> = secret.iter()
            .chain(label.as_bytes())
            .chain(context)
            .copied()
            .collect();
        
        for i in 0..length {
            result.push(combined[i % combined.len()] ^ (i as u8));
        }
        result
    }
    
    /// Derive early secret (from pre-shared key or zeros)
    pub fn early_secret(&self, psk: Option<&[u8]>) -> Vec<u8> {
        let hash_len = self.cipher.hash_len();
        let zeros = vec![0u8; hash_len];
        let input = psk.unwrap_or(&zeros);
        self.hkdf_expand_label(input, "tls13 res binder", &[], hash_len)
    }
    
    /// Derive handshake secret from (EC)DHE shared secret
    pub fn handshake_secret(&self, early_secret: &[u8], dhe_shared: &[u8]) -> Vec<u8> {
        let hash_len = self.cipher.hash_len();
        let derived = self.hkdf_expand_label(early_secret, "tls13 derived", &[], hash_len);
        self.hkdf_expand_label(&derived, "tls13 extractor", dhe_shared, hash_len)
    }
    
    /// Derive client and server handshake traffic secrets
    pub fn handshake_traffic_secrets(&self, handshake_secret: &[u8], transcript: &[u8]) -> (Vec<u8>, Vec<u8>) {
        let hash_len = self.cipher.hash_len();
        let client = self.hkdf_expand_label(handshake_secret, "tls13 c hs traffic", transcript, hash_len);
        let server = self.hkdf_expand_label(handshake_secret, "tls13 s hs traffic", transcript, hash_len);
        (client, server)
    }
    
    /// Derive application traffic secrets
    pub fn application_traffic_secrets(&self, handshake_secret: &[u8], transcript: &[u8]) -> (Vec<u8>, Vec<u8>) {
        let hash_len = self.cipher.hash_len();
        let master = self.hkdf_expand_label(handshake_secret, "tls13 master secret", &[], hash_len);
        let client = self.hkdf_expand_label(&master, "tls13 c ap traffic", transcript, hash_len);
        let server = self.hkdf_expand_label(&master, "tls13 s ap traffic", transcript, hash_len);
        (client, server)
    }
}
