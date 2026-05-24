// File: models.rs
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
  _JCROSS_型_8_ : _JCROSS_核_9_,
};

use chrono::{DateTime, Utc};

#[derive(Serialize, Deserialize)]
pub struct CoreEvent {
    pub id: u64,
    pub name: String,
    pub timestamp: DateTime<Utc>, // UTC forced
}