// POLYMORPHIC_JCROSS_BEGIN
// schema:5A2F1C88 ver:1778349999
// ⚠️ One-time schema — expires after response

use std::collections::HashMap;
use serde::{Serialize, Deserialize};
use tokio::sync::mpsc;

// 型定義
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct _VERANTYX_霧:1.0__OPAQUE_霧_3_ {
    pub id: String,
    pub title: String,
    pub width: f64,
    pub height: f64,
    pub resizable: bool,
    pub minimizable: bool,
    pub closable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct _VERANTYX_墟:1.0__OPAQUE_墟_7_ {
    pub channel: mpsc::Sender<String>,
    pub handlers: HashMap<String, mpsc::Sender<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
    Success,
    Error(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct _VERANTYX_霧:1.0__OPAQUE_霧_25_ {
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub width: Option<f64>,
    pub height: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct _VERANTYX_墟:1.0__OPAQUE_墟_6_<T> {
    pub data: Option<T>,
    pub error: Option<String>,
}

impl<T> _VERANTYX_墟:1.0__OPAQUE_墟_6_<T> {
    pub fn ok(data: T) -> Self {
        Self { data: Some(data), error: None }
    }

    pub fn err(msg: String) -> Self {
        Self { data: None, error: Some(msg) }
    }
}

// Windowクラス
pub struct _VERANTYX_墟:1.0__OPAQUE_墟_2_ {
    pub _VERANTYX_霧:1.0__OPAQUE_霧_12_: _VERANTYX_霧:1.0__OPAQUE_霧_3_,
    _VERANTYX_霧:1.0__OPAQUE_霧_6_: _VERANTYX_墟:1.0__OPAQUE_墟_7_,
}

impl _VERANTYX_墟:1.0__OPAQUE_墟_2_ {
    pub fn new(_VERANTYX_霧:1.0__OPAQUE_霧_12_: _VERANTYX_霧:1.0__OPAQUE_霧_3_, _VERANTYX_霧:1.0__OPAQUE_霧_6_: _VERANTYX_墟:1.0__OPAQUE_墟_7_) -> Self {
        let instance = Self {
            _VERANTYX_霧:1.0__OPAQUE_霧_12_,
            _VERANTYX_霧:1.0__OPAQUE_霧_6_: _VERANTYX_霧:1.0__OPAQUE_霧_6_.clone(),
        };
        instance._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_message(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_28_",
            Some(serde_json::to_value(&instance._VERANTYX_霧:1.0__OPAQUE_霧_12_).unwrap_or_default()),
        );
        instance
    }

    pub fn _VERANTYX_霧:1.0__OPAQUE_霧_22_(&self, _VERANTYX_霧:1.0__OPAQUE_霧_4_: _VERANTYX_霧:1.0__OPAQUE_霧_3_) -> _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_message(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_34_._VERANTYX_霧:1.0__OPAQUE_霧_22_",
            Some(serde_json::json!({
                "current": self._VERANTYX_霧:1.0__OPAQUE_霧_12_,
                "new": _VERANTYX_霧:1.0__OPAQUE_霧_4_
            })),
        );
        _VERANTYX_霧:1.0__OPAQUE_霧_23_::Success
    }

    pub fn _VERANTYX_霧:1.0__OPAQUE_霧_20_(&self, _VERANTYX_霧:1.0__OPAQUE_霧_4_: _VERANTYX_霧:1.0__OPAQUE_霧_3_) -> _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_message(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_34_._VERANTYX_霧:1.0__OPAQUE_霧_20_",
            Some(serde_json::json!({
                "current": self._VERANTYX_霧:1.0__OPAQUE_霧_12_,
                "new": _VERANTYX_霧:1.0__OPAQUE_霧_4_
            })),
        );
        _VERANTYX_霧:1.0__OPAQUE_霧_23_::Success
    }

    pub fn _VERANTYX_霧:1.0__OPAQUE_霧_24_(&self) -> _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_message(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_34_._VERANTYX_霧:1.0__OPAQUE_霧_24_",
            Some(serde_json::json!({ "window": self._VERANTYX_霧:1.0__OPAQUE_霧_12_ })),
        );
        _VERANTYX_霧:1.0__OPAQUE_霧_23_::Success
    }

    pub fn _VERANTYX_霧:1.0__OPAQUE_霧_10_(&self, _VERANTYX_霧:1.0__OPAQUE_霧_33_: Option<_VERANTYX_霧:1.0__OPAQUE_霧_25_>) -> _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_message(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_34_._VERANTYX_霧:1.0__OPAQUE_霧_10_",
            Some(serde_json::json!({
                "window": self._VERANTYX_霧:1.0__OPAQUE_霧_12_,
                "options": _VERANTYX_霧:1.0__OPAQUE_霧_33_
            })),
        );
        _VERANTYX_霧:1.0__OPAQUE_霧_23_::Success
    }

    pub fn _VERANTYX_霧:1.0__OPAQUE_霧_2_(&self) -> _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_message(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_34_._VERANTYX_霧:1.0__OPAQUE_霧_2_",
            Some(serde_json::json!({ "window": self._VERANTYX_霧:1.0__OPAQUE_霧_12_ })),
        );
        _VERANTYX_霧:1.0__OPAQUE_霧_23_::Success
    }

    pub fn _VERANTYX_霧:1.0__OPAQUE_霧_11_(&self) -> _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_message(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_34_._VERANTYX_霧:1.0__OPAQUE_霧_11_",
            Some(serde_json::json!({ "window": self._VERANTYX_霧:1.0__OPAQUE_霧_12_ })),
        );
        _VERANTYX_霧:1.0__OPAQUE_霧_23_::Success
    }
}

// WindowManagerクラス
pub struct _VERANTYX_墟:1.0__OPAQUE_墟_3_ {
    _VERANTYX_霧:1.0__OPAQUE_霧_6_: _VERANTYX_墟:1.0__OPAQUE_墟_7_,
}

impl _VERANTYX_墟:1.0__OPAQUE_墟_3_ {
    pub fn new(_VERANTYX_霧:1.0__OPAQUE_霧_6_: _VERANTYX_墟:1.0__OPAQUE_墟_7_) -> Self {
        Self { _VERANTYX_霧:1.0__OPAQUE_霧_6_ }
    }

    pub fn _VERANTYX_霧:1.0__OPAQUE_霧_28_(&self, _VERANTYX_霧:1.0__OPAQUE_霧_12_: _VERANTYX_霧:1.0__OPAQUE_霧_3_) -> _VERANTYX_墟:1.0__OPAQUE_墟_2_ {
        _VERANTYX_墟:1.0__OPAQUE_墟_2_::new(_VERANTYX_霧:1.0__OPAQUE_霧_12_, self._VERANTYX_霧:1.0__OPAQUE_霧_6_.clone())
    }

    pub async fn _VERANTYX_霧:1.0__OPAQUE_霧_17_(&self, _VERANTYX_霧:1.0__OPAQUE_霧_31_: Vec<_VERANTYX_霧:1.0__OPAQUE_霧_3_>, _VERANTYX_霧:1.0__OPAQUE_霧_1_: Option<serde_json::Value>) -> _VERANTYX_墟:1.0__OPAQUE_墟_6_<serde_json::Value> {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_and_wait(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_17_",
            Some(serde_json::json!({ "windows": _VERANTYX_霧:1.0__OPAQUE_霧_31_, "options": _VERANTYX_霧:1.0__OPAQUE_霧_1_ })),
        ).await
    }

    pub async fn _VERANTYX_霧:1.0__OPAQUE_霧_27_(&self, _VERANTYX_霧:1.0__OPAQUE_霧_1_: Option<serde_json::Value>) -> _VERANTYX_墟:1.0__OPAQUE_墟_6_<_VERANTYX_霧:1.0__OPAQUE_霧_3_> {
        self._VERANTYX_霧:1.0__OPAQUE_霧_6_.send_and_wait(
            "_VERANTYX_霧:1.0__OPAQUE_霧_26_._VERANTYX_霧:1.0__OPAQUE_霧_27_",
            Some(serde_json::json!({ "options": _VERANTYX_霧:1.0__OPAQUE_霧_1_ })),
        ).await
    }
}

// IPC通信の実装
impl _VERANTYX_墟:1.0__OPAQUE_墟_7_ {
    pub fn send_message(&self, method: &str, data: Option<serde_json::Value>) -> _VERANTYX_霧:1.0__OPAQUE_霧_23_ {
        let message = serde_json::json!({
            "method": method,
            "data": data,
        });
        match self.channel.try_send(message.to_string()) {
            Ok(_) => _VERANTYX_霧:1.0__OPAQUE_霧_23_::Success,
            Err(e) => _VERANTYX_霧:1.0__OPAQUE_霧_23_::Error(format!("Failed to send message: {}", e)),
        }
    }

    pub async fn send_and_wait<T: serde::de::DeserializeOwned>(
        &self,
        method: &str,
        data: Option<serde_json::Value>,
    ) -> _VERANTYX_墟:1.0__OPAQUE_墟_6_<T> {
        let message = serde_json::json!({
            "method": method,
            "data": data,
        });
        match self.channel.send(message.to_string()).await {
            Ok(_) => _VERANTYX_墟:1.0__OPAQUE_墟_6_::<T>::err("Response not implemented yet".to_string()),
            Err(e) => _VERANTYX_墟:1.0__OPAQUE_墟_6_::<T>::err(format!("Failed to send message: {}", e)),
        }
    }
}

impl Clone for _VERANTYX_墟:1.0__OPAQUE_墟_7_ {
    fn clone(&self) -> Self {
        Self {
            channel: self.channel.clone(),
            handlers: self.handlers.clone(),
        }
    }
}

// POLYMORPHIC_JCROSS_END
