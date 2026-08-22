//! Digital Goods API — W3C Digital Goods
//!
//! Implements querying and purchasing in-app goods for web applications acting as native PWAs:
//!   - `getDigitalGoodsService(serviceProvider)`: Connecting to external stores (Play Store, App Store).
//!   - `getDetails([itemIds])`: Retrieving local pricing and descriptions.
//!   - `listPurchases()`: Checking previously acquired non-consumables/subscriptions.
//!   - `consume()`: Marking a consumable as used up.
//!   - AI-facing: Store integration backend topological mappings.

use std::collections::HashMap;

/// The type of digital asset available for purchase
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ItemType { Consumable, NonConsumable, Subscription }

/// Details about a purchasable SKU returned from the native store backend
#[derive(Debug, Clone)]
pub struct ItemDetails {
    pub item_id: String,
    pub title: String,
    pub price_currency: String,
    pub price_value: f64,
    pub item_type: ItemType,
}

/// A receipt of a verified purchase
#[derive(Debug, Clone)]
pub struct PurchaseDetails {
    pub item_id: String,
    pub purchase_token: String,
    pub acknowledged: bool,
}

/// The global Digital Goods Engine mapping PWAs to OS-level storefronts
pub struct DigitalGoodsEngine {
    // Service Provider URI -> Item Catalog
    pub mock_catalogs: HashMap<String, HashMap<String, ItemDetails>>,
    // Origin -> Purchase Tokens
    pub active_purchases: HashMap<String, Vec<PurchaseDetails>>,
    pub total_consume_calls: u64,
}

impl DigitalGoodsEngine {
    pub fn new() -> Self {
        Self {
            mock_catalogs: HashMap::new(),
            active_purchases: HashMap::new(),
            total_consume_calls: 0,
        }
    }

    /// Seed the store for testing or offline simulated development
    pub fn add_mock_inventory(&mut self, provider: &str, item: ItemDetails) {
        let catalog = self.mock_catalogs.entry(provider.to_string()).or_default();
        catalog.insert(item.item_id.clone(), item);
    }

    /// JS execution: `service.getDetails(["sword", "shield"])`
    pub fn get_details(&self, provider: &str, item_ids: Vec<&str>) -> Vec<ItemDetails> {
        let mut results = Vec::new();
        if let Some(catalog) = self.mock_catalogs.get(provider) {
            for id in item_ids {
                if let Some(detail) = catalog.get(id) {
                    results.push(detail.clone());
                }
            }
        }
        results
    }

    /// Internal integration called after a user successfully purchases via Payment Request API
    pub fn record_purchase(&mut self, origin: &str, item_id: &str, token: &str) {
        let purchases = self.active_purchases.entry(origin.to_string()).or_default();
        purchases.push(PurchaseDetails {
            item_id: item_id.to_string(),
            purchase_token: token.to_string(),
            acknowledged: false,
        });
    }

    /// JS execution: `service.consume("purchase-token-xyz")`
    pub fn consume_purchase(&mut self, origin: &str, token: &str) -> Result<(), String> {
        if let Some(purchases) = self.active_purchases.get_mut(origin) {
            let initial_len = purchases.len();
            purchases.retain(|p| p.purchase_token != token);
            if purchases.len() < initial_len {
                self.total_consume_calls += 1;
                return Ok(());
            }
        }
        Err("InvalidStateError: Purchase token not found or already consumed".into())
    }

    /// AI-facing Digital Goods tracking summary
    pub fn ai_digital_goods_summary(&self, origin: &str) -> String {
        let held_items = self.active_purchases.get(origin).map_or(0, |p| p.len());
        format!("🛍️ Digital Goods API (Origin: {}): Retains {} active purchases | Store catalogs available: {} | Consume calls: {}", 
            origin, held_items, self.mock_catalogs.len(), self.total_consume_calls)
    }
}
