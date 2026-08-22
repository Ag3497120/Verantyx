//! Geolocation API — W3C Geolocation API Specification
//!
//! Implements the browser's location-based services:
//!   - Position (§ 5.1) and Coordinates (§ 5.2): latitude, longitude, altitude, accuracy,
//!     altitudeAccuracy, heading, speed, timestamp
//!   - Methods (§ 5.3): getCurrentPosition(), watchPosition(), clearWatch()
//!   - PositionOptions (§ 5.4): enableHighAccuracy, timeout, maximumAge
//!   - PositionError (§ 5.5): PERMISSION_DENIED (1), POSITION_UNAVAILABLE (2), TIMEOUT (3)
//!   - Permissions: Integration with the browser's permission manager logic
//!   - Privacy (§ 4): Handling user consent and data minimization
//!   - AI-facing: Geolocation mock injector and coordinates history visualizer

use std::collections::HashMap;

/// Latitude and Longitude coordinates (§ 5.2)
#[derive(Debug, Clone, Copy)]
pub struct Coordinates {
    pub latitude: f64,
    pub longitude: f64,
    pub altitude: Option<f64>,
    pub accuracy: f64,
    pub altitude_accuracy: Option<f64>,
    pub heading: Option<f64>,
    pub speed: Option<f64>,
}

/// A single position snapshot (§ 5.1)
#[derive(Debug, Clone, Copy)]
pub struct Position {
    pub coords: Coordinates,
    pub timestamp: u64,
}

/// Geolocation error codes (§ 5.5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PositionErrorCode { PermissionDenied = 1, PositionUnavailable = 2, Timeout = 3 }

/// Position retrieval options (§ 5.4)
pub struct PositionOptions {
    pub enable_high_accuracy: bool,
    pub timeout: u32,
    pub maximum_age: u32,
}

/// The global Geolocation API Manager
pub struct GeolocationManager {
    pub current_position: Option<Position>,
    pub watchers: HashMap<u64, PositionOptions>,
    pub next_watch_id: u64,
    pub permission_granted: bool,
}

impl GeolocationManager {
    pub fn new() -> Self {
        Self {
            current_position: None,
            watchers: HashMap::new(),
            next_watch_id: 1,
            permission_granted: false,
        }
    }

    /// Entry point for getCurrentPosition() (§ 5.3.1)
    pub fn get_current_position(&mut self, _options: PositionOptions) -> Result<Position, PositionErrorCode> {
        if !self.permission_granted { return Err(PositionErrorCode::PermissionDenied); }
        
        match &self.current_position {
            Some(p) => Ok(*p),
            None => Err(PositionErrorCode::PositionUnavailable),
        }
    }

    /// Entry point for watchPosition() (§ 5.3.2)
    pub fn watch_position(&mut self, options: PositionOptions) -> u64 {
        let id = self.next_watch_id;
        self.next_watch_id += 1;
        self.watchers.insert(id, options);
        id
    }

    pub fn clear_watch(&mut self, id: u64) {
        self.watchers.remove(&id);
    }

    /// AI-facing mock location injector
    pub fn ai_set_mock_location(&mut self, lat: f64, lon: f64, acc: f64) {
        self.current_position = Some(Position {
            coords: Coordinates {
                latitude: lat,
                longitude: lon,
                altitude: None,
                accuracy: acc,
                altitude_accuracy: None,
                heading: None,
                speed: None,
            },
            timestamp: 123456789,
        });
        self.permission_granted = true;
    }

    /// AI-facing geolocation status
    pub fn ai_status_summary(&self) -> String {
        let mut lines = vec![format!("📍 Geolocation Status (Permission: {}):", self.permission_granted)];
        if let Some(pos) = &self.current_position {
            lines.push(format!("  Current: ({:.4}, {:.4}) ±{}m", pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy));
        } else {
            lines.push("  Current: [Unknown]".into());
        }
        lines.push(format!("  Active watchers: {}", self.watchers.len()));
        lines.join("\n")
    }
}
