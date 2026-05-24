// File: routes.rs
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
  _JCROSS_型_8_ : _JCROSS_核_9_,
};

use chrono::Utc;
use crate::models::Message;

pub fn handle_message(msg: &mut Message) {
    // Force all incoming timestamps to UTC
    msg.timestamp = Utc::now();
}