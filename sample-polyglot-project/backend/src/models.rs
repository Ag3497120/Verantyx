use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct Message {
    pub id: String,
    pub user: String,
    pub content: String,
}
