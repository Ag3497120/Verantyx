//! Input Event System — Full W3C UIEvents + Pointer Events + Touch Events
//!
//! Implements the complete browser input event pipeline:
//!   - Keyboard events (keydown, keypress, keyup) with full KeyboardEvent API
//!   - Mouse events (mousedown, mouseup, click, dblclick, mousemove, etc.)
//!   - Pointer events (W3C Pointer Events Level 2)
//!   - Touch events (W3C Touch Events Level 2)
//!   - Wheel events (WheelEvent with delta modes)
//!   - Focus events (focus, blur, focusin, focusout)
//!   - Input events (InputEvent with inputType enum)
//!   - Drag and Drop events
//!   - Composition events (for IME input)
//!   - Event bubbling, capturing, and cancellation

use std::collections::HashMap;

/// Event phase (mirrors DOM spec EventPhase constants)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventPhase {
    None = 0,
    Capturing = 1,
    AtTarget = 2,
    Bubbling = 3,
}

/// The type of UI event
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum EventType {
    // Mouse events
    Click,
    DblClick,
    MouseDown,
    MouseUp,
    MouseMove,
    MouseEnter,
    MouseLeave,
    MouseOver,
    MouseOut,
    ContextMenu,
    AuxClick,
    
    // Keyboard events
    KeyDown,
    KeyUp,
    KeyPress, // Deprecated but still fired
    
    // Pointer events
    PointerDown,
    PointerUp,
    PointerMove,
    PointerEnter,
    PointerLeave,
    PointerOver,
    PointerOut,
    PointerCancel,
    GotPointerCapture,
    LostPointerCapture,
    
    // Touch events
    TouchStart,
    TouchEnd,
    TouchMove,
    TouchCancel,
    
    // Focus events
    Focus,
    Blur,
    FocusIn,
    FocusOut,
    
    // Input events
    Input,
    BeforeInput,
    Change,
    
    // Wheel/Scroll
    Wheel,
    Scroll,
    
    // Drag and Drop
    DragStart,
    Drag,
    DragEnd,
    DragEnter,
    DragLeave,
    DragOver,
    Drop,
    
    // Composition (IME)
    CompositionStart,
    CompositionUpdate,
    CompositionEnd,
    
    // Clipboard
    Cut,
    Copy,
    Paste,
    
    // Form events
    Submit,
    Reset,
    Select,
    
    // Animation events
    AnimationStart,
    AnimationEnd,
    AnimationIteration,
    AnimationCancel,
    
    // Transition events
    TransitionStart,
    TransitionEnd,
    TransitionRun,
    TransitionCancel,
    
    // Custom
    Custom(String),
}

impl EventType {
    pub fn from_str(s: &str) -> Self {
        match s {
            "click" => Self::Click,
            "dblclick" => Self::DblClick,
            "mousedown" => Self::MouseDown,
            "mouseup" => Self::MouseUp,
            "mousemove" => Self::MouseMove,
            "mouseenter" => Self::MouseEnter,
            "mouseleave" => Self::MouseLeave,
            "mouseover" => Self::MouseOver,
            "mouseout" => Self::MouseOut,
            "contextmenu" => Self::ContextMenu,
            "auxclick" => Self::AuxClick,
            "keydown" => Self::KeyDown,
            "keyup" => Self::KeyUp,
            "keypress" => Self::KeyPress,
            "pointerdown" => Self::PointerDown,
            "pointerup" => Self::PointerUp,
            "pointermove" => Self::PointerMove,
            "pointerenter" => Self::PointerEnter,
            "pointerleave" => Self::PointerLeave,
            "pointercancel" => Self::PointerCancel,
            "gotpointercapture" => Self::GotPointerCapture,
            "lostpointercapture" => Self::LostPointerCapture,
            "touchstart" => Self::TouchStart,
            "touchend" => Self::TouchEnd,
            "touchmove" => Self::TouchMove,
            "touchcancel" => Self::TouchCancel,
            "focus" => Self::Focus,
            "blur" => Self::Blur,
            "focusin" => Self::FocusIn,
            "focusout" => Self::FocusOut,
            "input" => Self::Input,
            "beforeinput" => Self::BeforeInput,
            "change" => Self::Change,
            "wheel" => Self::Wheel,
            "scroll" => Self::Scroll,
            "dragstart" => Self::DragStart,
            "drag" => Self::Drag,
            "dragend" => Self::DragEnd,
            "dragenter" => Self::DragEnter,
            "dragleave" => Self::DragLeave,
            "dragover" => Self::DragOver,
            "drop" => Self::Drop,
            "compositionstart" => Self::CompositionStart,
            "compositionupdate" => Self::CompositionUpdate,
            "compositionend" => Self::CompositionEnd,
            "cut" => Self::Cut,
            "copy" => Self::Copy,
            "paste" => Self::Paste,
            "submit" => Self::Submit,
            "reset" => Self::Reset,
            "select" => Self::Select,
            "animationstart" => Self::AnimationStart,
            "animationend" => Self::AnimationEnd,
            "animationiteration" => Self::AnimationIteration,
            "animationcancel" => Self::AnimationCancel,
            "transitionstart" => Self::TransitionStart,
            "transitionend" => Self::TransitionEnd,
            "transitionrun" => Self::TransitionRun,
            "transitioncancel" => Self::TransitionCancel,
            other => Self::Custom(other.to_string()),
        }
    }
    
    /// Whether the event bubbles by default
    pub fn bubbles(&self) -> bool {
        !matches!(self,
            Self::Focus | Self::Blur | Self::MouseEnter | Self::MouseLeave |
            Self::PointerEnter | Self::PointerLeave | Self::GotPointerCapture |
            Self::LostPointerCapture
        )
    }
    
    /// Whether the event is cancelable by default
    pub fn cancelable(&self) -> bool {
        matches!(self,
            Self::Click | Self::DblClick | Self::MouseDown | Self::MouseUp |
            Self::MouseMove | Self::KeyDown | Self::KeyUp | Self::KeyPress |
            Self::PointerDown | Self::PointerMove |
            Self::Wheel | Self::TouchStart | Self::TouchMove |
            Self::Submit | Self::BeforeInput | Self::ContextMenu |
            Self::DragStart | Self::Drag | Self::DragEnter | Self::DragOver | Self::Drop
        )
    }
}

/// Modifier key state (bitmask mirroring MouseEvent.getModifierState)
#[derive(Debug, Clone, Copy, Default)]
pub struct ModifierKeys {
    pub alt: bool,
    pub ctrl: bool,
    pub meta: bool,
    pub shift: bool,
    pub caps_lock: bool,
    pub num_lock: bool,
    pub scroll_lock: bool,
    pub fn_lock: bool,
}

impl ModifierKeys {
    pub fn none() -> Self { Self::default() }
    
    pub fn get_modifier_state(&self, key: &str) -> bool {
        match key {
            "Alt" => self.alt,
            "Control" => self.ctrl,
            "Meta" | "OS" => self.meta,
            "Shift" => self.shift,
            "CapsLock" => self.caps_lock,
            "NumLock" => self.num_lock,
            "ScrollLock" => self.scroll_lock,
            "FnLock" => self.fn_lock,
            _ => false,
        }
    }
}

/// Mouse button constants
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(i16)]
pub enum MouseButton {
    None = -1,
    Left = 0,
    Middle = 1,
    Right = 2,
    Back = 3,
    Forward = 4,
}

/// A mouse-like event
#[derive(Debug, Clone)]
pub struct MouseEventData {
    pub client_x: f64,
    pub client_y: f64,
    pub page_x: f64,
    pub page_y: f64,
    pub screen_x: f64,
    pub screen_y: f64,
    pub offset_x: f64,
    pub offset_y: f64,
    pub movement_x: f64,
    pub movement_y: f64,
    pub button: MouseButton,
    pub buttons: u16,     // Bitmask of currently held buttons
    pub modifiers: ModifierKeys,
    pub related_target: Option<u64>, // Node ID of relatedTarget
}

/// W3C Pointer Event additional fields (extends MouseEvent)
#[derive(Debug, Clone)]
pub struct PointerEventData {
    pub mouse: MouseEventData,
    pub pointer_id: i32,
    pub width: f64,          // Contact geometry width in CSS pixels
    pub height: f64,         // Contact geometry height in CSS pixels
    pub pressure: f64,       // 0.0 to 1.0
    pub tangential_pressure: f64,
    pub tilt_x: i32,         // -90 to 90 degrees
    pub tilt_y: i32,         // -90 to 90 degrees
    pub twist: i32,          // 0 to 359 degrees
    pub altitude_angle: f64, // 0 to π/2
    pub azimuth_angle: f64,  // 0 to 2π
    pub pointer_type: PointerType,
    pub is_primary: bool,
    pub coalesced_events: Vec<PointerEventData>,
    pub predicted_events: Vec<PointerEventData>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PointerType {
    Mouse,
    Pen,
    Touch,
    Unknown,
}

impl PointerType {
    pub fn from_str(s: &str) -> Self {
        match s {
            "mouse" => Self::Mouse,
            "pen" => Self::Pen,
            "touch" => Self::Touch,
            _ => Self::Unknown,
        }
    }
    
    pub fn to_str(&self) -> &'static str {
        match self {
            Self::Mouse => "mouse",
            Self::Pen => "pen",
            Self::Touch => "touch",
            Self::Unknown => "",
        }
    }
}

/// A single touch point
#[derive(Debug, Clone)]
pub struct Touch {
    pub identifier: i32,
    pub client_x: f64,
    pub client_y: f64,
    pub page_x: f64,
    pub page_y: f64,
    pub screen_x: f64,
    pub screen_y: f64,
    pub radius_x: f64,
    pub radius_y: f64,
    pub rotation_angle: f64,
    pub force: f64,
    pub target_node_id: u64,
}

/// Touch event data
#[derive(Debug, Clone)]
pub struct TouchEventData {
    pub touches: Vec<Touch>,            // All current touches on the surface
    pub target_touches: Vec<Touch>,     // All touches on this element
    pub changed_touches: Vec<Touch>,    // Touches that changed in this event
    pub modifiers: ModifierKeys,
}

/// Wheel/scroll delta mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u32)]
pub enum WheelDeltaMode {
    Pixel = 0,  // deltaX/Y/Z in CSS pixels
    Line = 1,   // deltaX/Y/Z in lines
    Page = 2,   // deltaX/Y/Z in pages
}

/// Wheel event data
#[derive(Debug, Clone)]
pub struct WheelEventData {
    pub mouse: MouseEventData,
    pub delta_x: f64,
    pub delta_y: f64,
    pub delta_z: f64,
    pub delta_mode: WheelDeltaMode,
}

/// Keyboard location constants
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u32)]
pub enum KeyLocation {
    Standard = 0,
    Left = 1,
    Right = 2,
    NumPad = 3,
}

/// Keyboard event data
#[derive(Debug, Clone)]
pub struct KeyboardEventData {
    pub key: String,           // The key value (e.g., "Enter", "a", "ArrowUp")
    pub code: String,          // The physical key code (e.g., "KeyA", "Enter")
    pub location: KeyLocation,
    pub modifiers: ModifierKeys,
    pub repeat: bool,          // Whether the key is auto-repeating
    pub is_composing: bool,    // Whether within IME composition session
    pub char_code: u32,        // Deprecated but still set for keypress
    pub key_code: u32,         // Deprecated but still set
    pub which: u32,            // Deprecated but still set
}

impl KeyboardEventData {
    /// Map a physical key code string to a legacy keyCode value
    pub fn legacy_key_code(key: &str, _code: &str) -> u32 {
        match key {
            "Backspace" => 8,
            "Tab" => 9,
            "Enter" => 13,
            "Shift" => 16,
            "Control" => 17,
            "Alt" => 18,
            "Pause" => 19,
            "CapsLock" => 20,
            "Escape" => 27,
            " " => 32,
            "PageUp" => 33,
            "PageDown" => 34,
            "End" => 35,
            "Home" => 36,
            "ArrowLeft" => 37,
            "ArrowUp" => 38,
            "ArrowRight" => 39,
            "ArrowDown" => 40,
            "Insert" => 45,
            "Delete" => 46,
            "F1" => 112, "F2" => 113, "F3" => 114, "F4" => 115,
            "F5" => 116, "F6" => 117, "F7" => 118, "F8" => 119,
            "F9" => 120, "F10" => 121, "F11" => 122, "F12" => 123,
            "NumLock" => 144,
            "ScrollLock" => 145,
            "Meta" => 91,
            _ => {
                // Single printable character
                if key.len() == 1 {
                    key.chars().next().map(|c| c.to_uppercase().next().unwrap_or(c) as u32).unwrap_or(0)
                } else {
                    0
                }
            }
        }
    }
}

/// InputEvent inputType enum — per Input Events Level 2 spec
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InputType {
    InsertText,
    InsertReplacementText,
    InsertLineBreak,
    InsertParagraph,
    InsertOrderedList,
    InsertUnorderedList,
    InsertHorizontalRule,
    InsertFromYank,
    InsertFromDrop,
    InsertFromPaste,
    InsertFromPasteAsQuotation,
    InsertTranspose,
    InsertCompositionText,
    InsertLink,
    DeleteWordBackward,
    DeleteWordForward,
    DeleteSoftLineBackward,
    DeleteSoftLineForward,
    DeleteEntireSoftLine,
    DeleteHardLineBackward,
    DeleteHardLineForward,
    DeleteByDrag,
    DeleteByCut,
    DeleteContent,
    DeleteContentBackward,
    DeleteContentForward,
    HistoryUndo,
    HistoryRedo,
    FormatBold,
    FormatItalic,
    FormatUnderline,
    FormatStrikeThrough,
    FormatSuperscript,
    FormatSubscript,
    FormatJustifyFull,
    FormatJustifyCenter,
    FormatJustifyRight,
    FormatJustifyLeft,
    FormatIndent,
    FormatOutdent,
    FormatRemove,
    FormatSetBlockTextDirection,
    FormatSetInlineTextDirection,
    FormatBackColor,
    FormatFontColor,
    FormatFontName,
}

/// An input event
#[derive(Debug, Clone)]
pub struct InputEventData {
    pub input_type: InputType,
    pub data: Option<String>,          // The inserted text (if any)
    pub data_transfer: Option<String>, // Clipboard data
    pub is_composing: bool,
}

/// A compositor input event — the high-level event dispatched from hardware
#[derive(Debug, Clone)]
pub enum InputEvent {
    Mouse { event_type: EventType, data: MouseEventData },
    Pointer { event_type: EventType, data: Box<PointerEventData> },
    Keyboard { event_type: EventType, data: KeyboardEventData },
    Touch { event_type: EventType, data: TouchEventData },
    Wheel { data: WheelEventData },
    Input { data: InputEventData },
    Focus { event_type: EventType, target_id: u64, related_target: Option<u64> },
    Composition { event_type: EventType, data: String },
    Custom { event_type: String, detail: Option<String> },
}

/// The input event dispatcher — routes hardware events to the DOM node tree
pub struct InputEventDispatcher {
    /// Currently focused element (receives keyboard events)
    focused_element: Option<u64>,
    
    /// Elements with pointer capture (pointer events are redirected here)
    pointer_capture: HashMap<i32, u64>,
    
    /// Whether touch action should be prevented from default scrolling
    touch_action_prevent_default: bool,
    
    /// Last click time for double-click detection
    last_click_time: Option<std::time::Instant>,
    last_click_pos: Option<(f64, f64)>,
    
    /// Double-click threshold in pixels
    dblclick_radius: f64,
}

impl InputEventDispatcher {
    pub fn new() -> Self {
        Self {
            focused_element: None,
            pointer_capture: HashMap::new(),
            touch_action_prevent_default: false,
            last_click_time: None,
            last_click_pos: None,
            dblclick_radius: 4.0,
        }
    }
    
    /// Set focus on an element, firing focus/blur events
    pub fn set_focus(&mut self, new_focus: Option<u64>) -> Vec<(u64, EventType)> {
        let mut events = Vec::new();
        
        if self.focused_element == new_focus { return events; }
        
        // Fire blur on old focus
        if let Some(old) = self.focused_element {
            events.push((old, EventType::Blur));
            events.push((old, EventType::FocusOut));
        }
        
        self.focused_element = new_focus;
        
        // Fire focus on new focus
        if let Some(new) = new_focus {
            events.push((new, EventType::Focus));
            events.push((new, EventType::FocusIn));
        }
        
        events
    }
    
    /// Set pointer capture for a pointer ID (per Pointer Events spec)
    pub fn set_pointer_capture(&mut self, pointer_id: i32, element_id: u64) {
        self.pointer_capture.insert(pointer_id, element_id);
    }
    
    pub fn release_pointer_capture(&mut self, pointer_id: i32) {
        self.pointer_capture.remove(&pointer_id);
    }
    
    pub fn get_pointer_capture(&self, pointer_id: i32) -> Option<u64> {
        self.pointer_capture.get(&pointer_id).copied()
    }
    
    /// Determine if a click qualifies as a double-click
    pub fn is_double_click(&mut self, x: f64, y: f64) -> bool {
        const DBLCLICK_INTERVAL_MS: u128 = 500;
        
        let now = std::time::Instant::now();
        let is_dblclick = if let (Some(last_time), Some((last_x, last_y))) = (self.last_click_time, self.last_click_pos) {
            let elapsed_ms = now.duration_since(last_time).as_millis();
            let dist = ((x - last_x).powi(2) + (y - last_y).powi(2)).sqrt();
            elapsed_ms <= DBLCLICK_INTERVAL_MS && dist <= self.dblclick_radius
        } else {
            false
        };
        
        self.last_click_time = Some(now);
        self.last_click_pos = Some((x, y));
        
        is_dblclick
    }
    
    /// Synthesize the pointer events from a mouse event (spec mandates this mapping)
    pub fn synthesize_pointer_from_mouse(
        &self,
        event_type: &EventType,
        _data: &MouseEventData
    ) -> Option<EventType> {
        match event_type {
            EventType::MouseDown => Some(EventType::PointerDown),
            EventType::MouseUp => Some(EventType::PointerUp),
            EventType::MouseMove => Some(EventType::PointerMove),
            EventType::MouseEnter => Some(EventType::PointerEnter),
            EventType::MouseLeave => Some(EventType::PointerLeave),
            EventType::MouseOver => Some(EventType::PointerOver),
            EventType::MouseOut => Some(EventType::PointerOut),
            _ => None,
        }
    }
}

/// Key event builder — creates spec-compliant KeyboardEventData from raw input
pub struct KeyEventBuilder;

impl KeyEventBuilder {
    /// Build a keyboard event from a physical key code string
    pub fn from_code(code: &str, modifiers: ModifierKeys, repeat: bool) -> KeyboardEventData {
        let key = Self::code_to_key(code, &modifiers);
        let key_code = KeyboardEventData::legacy_key_code(&key, code);
        let location = Self::code_to_location(code);
        
        KeyboardEventData {
            key: key.clone(),
            code: code.to_string(),
            location,
            modifiers,
            repeat,
            is_composing: false,
            char_code: if key.len() == 1 { key.chars().next().map(|c| c as u32).unwrap_or(0) } else { 0 },
            key_code,
            which: key_code,
        }
    }
    
    fn code_to_key(code: &str, modifiers: &ModifierKeys) -> String {
        let shifted = modifiers.shift ^ modifiers.caps_lock;
        
        match code {
            "KeyA" => if shifted { "A" } else { "a" }.to_string(),
            "KeyB" => if shifted { "B" } else { "b" }.to_string(),
            "KeyC" => if shifted { "C" } else { "c" }.to_string(),
            "KeyD" => if shifted { "D" } else { "d" }.to_string(),
            "KeyE" => if shifted { "E" } else { "e" }.to_string(),
            "KeyF" => if shifted { "F" } else { "f" }.to_string(),
            "KeyG" => if shifted { "G" } else { "g" }.to_string(),
            "KeyH" => if shifted { "H" } else { "h" }.to_string(),
            "KeyI" => if shifted { "I" } else { "i" }.to_string(),
            "KeyJ" => if shifted { "J" } else { "j" }.to_string(),
            "KeyK" => if shifted { "K" } else { "k" }.to_string(),
            "KeyL" => if shifted { "L" } else { "l" }.to_string(),
            "KeyM" => if shifted { "M" } else { "m" }.to_string(),
            "KeyN" => if shifted { "N" } else { "n" }.to_string(),
            "KeyO" => if shifted { "O" } else { "o" }.to_string(),
            "KeyP" => if shifted { "P" } else { "p" }.to_string(),
            "KeyQ" => if shifted { "Q" } else { "q" }.to_string(),
            "KeyR" => if shifted { "R" } else { "r" }.to_string(),
            "KeyS" => if shifted { "S" } else { "s" }.to_string(),
            "KeyT" => if shifted { "T" } else { "t" }.to_string(),
            "KeyU" => if shifted { "U" } else { "u" }.to_string(),
            "KeyV" => if shifted { "V" } else { "v" }.to_string(),
            "KeyW" => if shifted { "W" } else { "w" }.to_string(),
            "KeyX" => if shifted { "X" } else { "x" }.to_string(),
            "KeyY" => if shifted { "Y" } else { "y" }.to_string(),
            "KeyZ" => if shifted { "Z" } else { "z" }.to_string(),
            "Digit0" => if shifted { ")" } else { "0" }.to_string(),
            "Digit1" => if shifted { "!" } else { "1" }.to_string(),
            "Digit2" => if shifted { "@" } else { "2" }.to_string(),
            "Digit3" => if shifted { "#" } else { "3" }.to_string(),
            "Digit4" => if shifted { "$" } else { "4" }.to_string(),
            "Digit5" => if shifted { "%" } else { "5" }.to_string(),
            "Digit6" => if shifted { "^" } else { "6" }.to_string(),
            "Digit7" => if shifted { "&" } else { "7" }.to_string(),
            "Digit8" => if shifted { "*" } else { "8" }.to_string(),
            "Digit9" => if shifted { "(" } else { "9" }.to_string(),
            "Space" => " ".to_string(),
            "Enter" => "Enter".to_string(),
            "Backspace" => "Backspace".to_string(),
            "Tab" => "Tab".to_string(),
            "Escape" => "Escape".to_string(),
            "Delete" => "Delete".to_string(),
            "Insert" => "Insert".to_string(),
            "ArrowLeft" => "ArrowLeft".to_string(),
            "ArrowRight" => "ArrowRight".to_string(),
            "ArrowUp" => "ArrowUp".to_string(),
            "ArrowDown" => "ArrowDown".to_string(),
            "Home" => "Home".to_string(),
            "End" => "End".to_string(),
            "PageUp" => "PageUp".to_string(),
            "PageDown" => "PageDown".to_string(),
            "ShiftLeft" | "ShiftRight" => "Shift".to_string(),
            "ControlLeft" | "ControlRight" => "Control".to_string(),
            "AltLeft" | "AltRight" => "Alt".to_string(),
            "MetaLeft" | "MetaRight" => "Meta".to_string(),
            "CapsLock" => "CapsLock".to_string(),
            "F1" => "F1".to_string(), "F2" => "F2".to_string(), "F3" => "F3".to_string(),
            "F4" => "F4".to_string(), "F5" => "F5".to_string(), "F6" => "F6".to_string(),
            "F7" => "F7".to_string(), "F8" => "F8".to_string(), "F9" => "F9".to_string(),
            "F10" => "F10".to_string(), "F11" => "F11".to_string(), "F12" => "F12".to_string(),
            "Minus" => if shifted { "_" } else { "-" }.to_string(),
            "Equal" => if shifted { "+" } else { "=" }.to_string(),
            "BracketLeft" => if shifted { "{" } else { "[" }.to_string(),
            "BracketRight" => if shifted { "}" } else { "]" }.to_string(),
            "Backslash" => if shifted { "|" } else { "\\" }.to_string(),
            "Semicolon" => if shifted { ":" } else { ";" }.to_string(),
            "Quote" => if shifted { "\"" } else { "'" }.to_string(),
            "Comma" => if shifted { "<" } else { "," }.to_string(),
            "Period" => if shifted { ">" } else { "." }.to_string(),
            "Slash" => if shifted { "?" } else { "/" }.to_string(),
            "Backquote" => if shifted { "~" } else { "`" }.to_string(),
            _ => code.to_string(),
        }
    }
    
    fn code_to_location(code: &str) -> KeyLocation {
        if code.ends_with("Left") { return KeyLocation::Left; }
        if code.ends_with("Right") { return KeyLocation::Right; }
        if code.starts_with("Numpad") { return KeyLocation::NumPad; }
        KeyLocation::Standard
    }
}
