//! Mouse click mapping to DOM elements
pub struct MouseMapper;
impl MouseMapper {
    pub fn col_row_to_element_index(col: u16, row: u16, element_panel_x: u16) -> Option<usize> {
        if col >= element_panel_x { Some((row as usize).saturating_sub(2)) } else { None }
    }
}
