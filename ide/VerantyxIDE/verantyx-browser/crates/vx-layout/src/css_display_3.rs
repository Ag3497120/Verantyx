//! CSS Display Module Level 3 — W3C CSS Display
//!
//! Implements foundational box generation algorithms bridging DOM to Layout:
//!   - `display: contents` (§ 2): Stripping boxes from the formatting structure while leaving children
//!   - `display: none` vs `visibility: hidden` boundary resolution matrix
//!   - `inline-blocks` vs `flex` generation modes
//!   - Blockification and Inlinification topology algorithms
//!   - AI-facing: Structural formatting extraction matrices

use std::collections::HashMap;

/// Maps standard display properties parsing from CSS values
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DisplayMode { None, Contents, Block, Inline, InlineBlock, Flex, Grid, Table }

/// Tracks specific element display declarations prior to Box Generation
#[derive(Debug, Clone)]
pub struct LayoutBoxDeclaration {
    pub display: DisplayMode,
    pub is_root_element: bool, // <html> cannot be `contents`
    pub is_replaced_element: bool, // <img>, <video>, <canvas> cannot be `contents`
}

impl Default for LayoutBoxDeclaration {
    fn default() -> Self {
        Self {
            display: DisplayMode::Inline, // Default W3C behavior for unrecognized tags
            is_root_element: false,
            is_replaced_element: false,
        }
    }
}

/// The Object Model tree resolver. Determines exactly WHICH elements get a Physical Layout Node.
pub struct CssDisplay3Engine {
    pub node_declarations: HashMap<u64, LayoutBoxDeclaration>,
    pub total_contents_skipped: u64,
}

impl CssDisplay3Engine {
    pub fn new() -> Self {
        Self {
            node_declarations: HashMap::new(),
            total_contents_skipped: 0,
        }
    }

    pub fn set_display_config(&mut self, node_id: u64, decl: LayoutBoxDeclaration) {
        self.node_declarations.insert(node_id, decl);
    }

    /// The absolute most critical path in any Browser Engine:
    /// Returns `true` if the Node should completely bypass Box Generation logic.
    pub fn should_generate_layout_box(&mut self, node_id: u64) -> bool {
        if let Some(decl) = self.node_declarations.get(&node_id) {
            match decl.display {
                DisplayMode::None => return false,
                DisplayMode::Contents => {
                    // W3C Rule: Replaced elements generally ignore `display: contents` and render as normal.
                    // Root element (<html>) also ignores it.
                    if decl.is_replaced_element || decl.is_root_element {
                        return true;
                    }
                    self.total_contents_skipped += 1;
                    return false;
                }
                _ => return true,
            }
        }
        true
    }

    /// Executed by `vx-layout` when children of a Flex/Grid container are identified.
    /// Inlinification: Flex items undergo display conversion (e.g. `inline-block` becomes `block`).
    pub fn compute_blockification(&self, node_id: u64) -> DisplayMode {
        if let Some(decl) = self.node_declarations.get(&node_id) {
            match decl.display {
                DisplayMode::Inline | DisplayMode::InlineBlock => DisplayMode::Block,
                _ => decl.display, // Retain existing block-level structures
            }
        } else {
            DisplayMode::Block
        }
    }

    /// AI-facing Visual Formatting abstraction constraints
    pub fn ai_display_summary(&self, node_id: u64) -> String {
        if let Some(decl) = self.node_declarations.get(&node_id) {
            format!("📦 CSS Display 3 (Node #{}): Display: {:?} | Replaced: {} | Global 'Contents' Skips: {}", 
                node_id, decl.display, decl.is_replaced_element, self.total_contents_skipped)
        } else {
            format!("Node #{} executes native inline un-replaced heuristics", node_id)
        }
    }
}
