//! Image to Block Character Renderer
//!
//! Converts image data to Unicode block characters for terminal display.
//! Uses half-block characters (▀▄█░) for 2x vertical resolution.

/// Render image bytes to terminal block characters
///
/// Returns lines of ANSI-colored text using Unicode half-block chars.
/// Each terminal cell represents 2 vertical pixels using ▀ (upper half block).
pub fn render_image_to_blocks(
    pixels: &[u8],  // RGBA or RGB pixel data
    width: u32,
    height: u32,
    channels: u32,   // 3 for RGB, 4 for RGBA
    max_width: u16,  // Max terminal columns
) -> Vec<String> {
    if width == 0 || height == 0 || pixels.is_empty() {
        return vec!["[empty image]".to_string()];
    }

    // Scale factor to fit terminal width
    let scale = if width > max_width as u32 {
        max_width as f32 / width as f32
    } else {
        1.0
    };

    let out_w = (width as f32 * scale) as usize;
    let out_h = (height as f32 * scale) as usize;

    // Round height to even (we use 2 rows per terminal line)
    let out_h = if out_h % 2 != 0 { out_h + 1 } else { out_h };

    let mut lines = Vec::new();

    // Process 2 rows at a time
    let mut y = 0;
    while y < out_h {
        let mut line = String::new();

        for x in 0..out_w {
            // Map output coordinates to source coordinates
            let src_x = ((x as f32 / scale) as u32).min(width - 1);
            let src_y_top = ((y as f32 / scale) as u32).min(height - 1);
            let src_y_bot = (((y + 1) as f32 / scale) as u32).min(height - 1);

            // Get top pixel color
            let top = get_pixel(pixels, src_x, src_y_top, width, channels);
            // Get bottom pixel color
            let bot = if y + 1 < out_h {
                get_pixel(pixels, src_x, src_y_bot, width, channels)
            } else {
                (0, 0, 0)
            };

            // Use ▀ (upper half block) with fg=top, bg=bottom
            line.push_str(&format!(
                "\x1b[38;2;{};{};{}m\x1b[48;2;{};{};{}m▀",
                top.0, top.1, top.2,
                bot.0, bot.1, bot.2,
            ));
        }

        line.push_str("\x1b[0m"); // Reset colors
        lines.push(line);
        y += 2;
    }

    lines
}

/// Get pixel at (x, y) from raw pixel buffer
fn get_pixel(pixels: &[u8], x: u32, y: u32, width: u32, channels: u32) -> (u8, u8, u8) {
    let idx = ((y * width + x) * channels) as usize;
    if idx + 2 < pixels.len() {
        (pixels[idx], pixels[idx + 1], pixels[idx + 2])
    } else {
        (0, 0, 0)
    }
}

/// Render a placeholder for images that can't be decoded
pub fn render_image_placeholder(alt: &str, width: u16) -> String {
    let border = "─".repeat(width.min(40) as usize);
    format!(
        "\x1b[90m┌{}┐\n│ 🖼 {:<width$} │\n└{}┘\x1b[0m",
        border,
        if alt.len() > 36 { &alt[..36] } else { alt },
        border,
        width = (width.min(40) as usize).saturating_sub(4)
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_small_image() {
        // 2x2 red/green/blue/white image
        let pixels: Vec<u8> = vec![
            255, 0, 0,     // red
            0, 255, 0,     // green
            0, 0, 255,     // blue
            255, 255, 255, // white
        ];
        let lines = render_image_to_blocks(&pixels, 2, 2, 3, 80);
        assert_eq!(lines.len(), 1); // 2 rows → 1 terminal line
        assert!(lines[0].contains("▀")); // Uses half-block char
    }

    #[test]
    fn test_placeholder() {
        let result = render_image_placeholder("Logo", 30);
        assert!(result.contains("Logo"));
        assert!(result.contains("🖼"));
    }

    #[test]
    fn test_empty_image() {
        let lines = render_image_to_blocks(&[], 0, 0, 3, 80);
        assert_eq!(lines[0], "[empty image]");
    }
}
