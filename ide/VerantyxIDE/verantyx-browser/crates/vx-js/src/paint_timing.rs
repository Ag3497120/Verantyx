//! Paint Timing API — W3C Paint Timing
//!
//! Implements performance metrics for screen rasterization phases:
//!   - `first-paint` (FP): The exact timestamp the browser first renders *anything* (background color)
//!   - `first-contentful-paint` (FCP): The timestamp when the first text/image/SVG is painted
//!   - PerformanceObserver Integration: Emitting `PerformancePaintTiming` entries
//!   - Cross-Origin iframe tracking (Paint metrics isolated by context)
//!   - AI-facing: Visual paint bottleneck analytics

use std::collections::HashMap;

/// Type of paint event being tracked (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PaintEventType { FirstPaint, FirstContentfulPaint }

/// Standardized W3C metric entry exposed to `performance.getEntriesByType('paint')`
#[derive(Debug, Clone)]
pub struct PerformancePaintTiming {
    pub name: String, // 'first-paint' or 'first-contentful-paint'
    pub start_time: f64, // DOMHighResTimeStamp
    pub duration: f64, // Always 0 for paint metrics
}

/// A tracking scope usually mapped to a single Document/Window context
#[derive(Debug, Clone)]
pub struct DocumentPaintContext {
    pub start_time_epoch: f64,
    pub first_paint_time: Option<f64>,
    pub first_contentful_paint_time: Option<f64>,
    pub buffer: Vec<PerformancePaintTiming>,
}

/// The global Paint Timing Engine bridging the Compositor/GPU with JavaScript
pub struct PaintTimingEngine {
    pub document_contexts: HashMap<u64, DocumentPaintContext>,
}

impl PaintTimingEngine {
    pub fn new() -> Self {
        Self { document_contexts: HashMap::new() }
    }

    pub fn register_document(&mut self, document_id: u64, current_time: f64) {
        self.document_contexts.insert(document_id, DocumentPaintContext {
            start_time_epoch: current_time,
            first_paint_time: None,
            first_contentful_paint_time: None,
            buffer: Vec::new(),
        });
    }

    /// Invoked by the Skia compositor the very first time a pixel changes from the blank white screen (§ 4)
    pub fn mark_first_paint(&mut self, document_id: u64, hardware_timestamp: f64) {
        if let Some(ctx) = self.document_contexts.get_mut(&document_id) {
            if ctx.first_paint_time.is_none() {
                ctx.first_paint_time = Some(hardware_timestamp);
                ctx.buffer.push(PerformancePaintTiming {
                    name: "first-paint".to_string(),
                    start_time: hardware_timestamp - ctx.start_time_epoch,
                    duration: 0.0,
                });
            }
        }
    }

    /// Invoked by the compositor specifically when Text, an Image, or Canvas draws (§ 4)
    pub fn mark_first_contentful_paint(&mut self, document_id: u64, hardware_timestamp: f64) {
        let mut needs_fp = false;
        if let Some(ctx) = self.document_contexts.get(&document_id) {
            if ctx.first_contentful_paint_time.is_none() && ctx.first_paint_time.is_none() {
                needs_fp = true;
            }
        }
        
        if needs_fp {
            self.mark_first_paint(document_id, hardware_timestamp);
        }

        if let Some(ctx) = self.document_contexts.get_mut(&document_id) {
            if ctx.first_contentful_paint_time.is_none() {
                ctx.first_contentful_paint_time = Some(hardware_timestamp);
                let start_time = hardware_timestamp - ctx.start_time_epoch;
                ctx.buffer.push(PerformancePaintTiming {
                    name: "first-contentful-paint".to_string(),
                    start_time,
                    duration: 0.0,
                });
            }
        }
    }

    /// AI-facing Paint Timing bottleneck metrics
    pub fn ai_paint_timing_summary(&self, document_id: u64) -> String {
        if let Some(ctx) = self.document_contexts.get(&document_id) {
            let fp = ctx.first_paint_time.map_or("Pending".into(), |t| format!("{:.1}ms", t - ctx.start_time_epoch));
            let fcp = ctx.first_contentful_paint_time.map_or("Pending".into(), |t| format!("{:.1}ms", t - ctx.start_time_epoch));
            format!("🖌️ Paint Timing API (Doc #{}): FP: {} | FCP: {}", document_id, fp, fcp)
        } else {
            format!("Document #{} paint context is unregistered", document_id)
        }
    }
}
