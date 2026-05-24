// JCROSS_6AXIS_BEGIN
// lang:rust doc:0xF84414

use windows::Win32::UI::WindowsAndMessaging::*;
use windows::Win32::Foundation::*;
use windows::Win32::Graphics::Gdi::*;
use std::ptr;

// ── TOP-LEVEL NODES
  NODE[0x2884] kind:opaque TYPE:opaque MEM:opaque HASH:0x7dc524dd ARITY:class.standard
  NODE[0xB217] kind:opaque TYPE:opaque MEM:opaque HASH:0x5dd94051 ARITY:class.multiway
  NODE[0x656C] kind:opaque TYPE:opaque MEM:opaque HASH:0xef345b9f
  NODE[0xAAB0] kind:opaque TYPE:opaque MEM:opaque HASH:0xa7ea372c ARITY:class.reduced
  NODE[0xB9CE] kind:opaque TYPE:opaque MEM:opaque HASH:0x5fb5737a ARITY:class.reduced
  NODE[0x5E96] kind:opaque TYPE:opaque MEM:opaque HASH:0xee816f48 ARITY:class.multiway
  NODE[0x84CE] kind:opaque TYPE:opaque MEM:opaque HASH:0x22e428e1 ARITY:class.reduced
  NODE[0x2555] kind:opaque TYPE:opaque MEM:opaque HASH:0xe2b6c3f5 ARITY:class.reduced
  NODE[0xDF8D] kind:opaque TYPE:opaque MEM:opaque HASH:0x2020b2fa ARITY:class.multiway
  NODE[0xB217] kind:opaque TYPE:opaque MEM:opaque HASH:0xd9de1518 ARITY:class.multiway
  NODE[0x1CCF] kind:opaque TYPE:opaque MEM:opaque HASH:0xa1ce56a9 ARITY:class.standard
  NODE[0x91DB] kind:opaque TYPE:opaque MEM:opaque HASH:0x03486daa
  NODE[0xB217] kind:opaque TYPE:opaque MEM:opaque HASH:0x79acdb4d
  NODE[0x4DF6] kind:opaque TYPE:opaque MEM:opaque HASH:0x12f4852f ARITY:class.nullary
  NODE[0xF2BD] kind:opaque TYPE:opaque MEM:opaque HASH:0xab4f4531 ARITY:class.standard
  NODE[0xA7AC] kind:opaque TYPE:opaque MEM:opaque HASH:0x720f5335 ARITY:class.standard
  NODE[0xECDA] kind:opaque TYPE:opaque MEM:opaque HASH:0x2985ad88 ARITY:class.standard
  NODE[0x5A2A] kind:opaque TYPE:opaque MEM:opaque HASH:0x9d31a1bf ARITY:class.standard
  NODE[0x53C5] kind:opaque TYPE:opaque MEM:opaque HASH:0x83b99a9c ARITY:class.reduced
  NODE[0x2884] kind:opaque TYPE:opaque MEM:opaque HASH:0xfa4a813f ARITY:class.standard
  NODE[0x656C] kind:opaque TYPE:opaque MEM:opaque HASH:0x4c0e9dc4 ARITY:class.standard
  NODE[0x2884] kind:opaque TYPE:opaque MEM:opaque HASH:0x50700ada ARITY:class.nullary
  NODE[0xECDA] kind:opaque TYPE:opaque MEM:opaque HASH:0x878d1b08 ARITY:class.standard
  NODE[0x5A2A] kind:opaque TYPE:opaque MEM:opaque HASH:0x64b0b1e9 ARITY:class.multiway
  NODE[0x7730] kind:opaque TYPE:opaque MEM:opaque HASH:0x8fe9f03a ARITY:class.standard

pub struct WindowsWindow {
    handle: HWND,
    class_name: Vec<u16>,
    title: Vec<u16>,
    width: i32,
    height: i32,
}

impl WindowsWindow {
    pub fn new(title: &str, width: i32, height: i32) -> Result<Self, std::io::Error> {
        let class_name = "VerantyxWindow\0".encode_utf16().collect::<Vec<_>>();
        let title_utf16 = title.encode_utf16().collect::<Vec<_>>();

        let instance = unsafe { GetModuleHandleW(None) }?;

        let wc = WNDCLASSW {
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(Self::wnd_proc),
            cbClsExtra: 0,
            cbWndExtra: 0,
            hInstance: instance,
            hIcon: HICON::default(),
            hCursor: HCURSOR::default(),
            hbrBackground: HBRUSH::default(),
            lpszMenuName: PWSTR(ptr::null()),
            lpszClassName: PWSTR(class_name.as_ptr()),
        };

        unsafe {
            RegisterClassW(&wc);
        }

        let handle = unsafe {
            CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                PWSTR(class_name.as_ptr()),
                PWSTR(title_utf16.as_ptr()),
                WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                width,
                height,
                None,
                None,
                instance,
                ptr::null_mut(),
            )
        }?;

        Ok(WindowsWindow {
            handle,
            class_name,
            title: title_utf16,
            width,
            height,
        })
    }

    unsafe extern "system" fn wnd_proc(
        hwnd: HWND,
        msg: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        match msg {
            WM_DESTROY => {
                PostQuitMessage(0);
                LRESULT(0)
            }
            WM_PAINT => {
                let mut ps = PAINTSTRUCT::default();
                let _hdc = BeginPaint(hwnd, &mut ps);
                // TODO: Add custom painting logic here
                let _ = EndPaint(hwnd, &ps);
                LRESULT(0)
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }

    pub fn show(&self) {
        unsafe {
            ShowWindow(self.handle, SW_SHOW);
        }
    }

    pub fn run_message_loop(&self) {
        let mut msg = MSG::default();
        unsafe {
            while GetMessageW(&mut msg, None, 0, 0).as_bool() {
                TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
        }
    }
}

// ── ADDITIONAL NODES FROM SWIFT CONVERSION
  NODE[0xCE26] kind:opaque TYPE:opaque MEM:opaque HASH:0x6aa33491 ARITY:class.multiway
  NODE[0x2884] kind:opaque TYPE:opaque MEM:opaque HASH:0x6c45e1b5 ARITY:class.reduced
  NODE[0xCE26] kind:opaque TYPE:opaque MEM:opaque HASH:0x25093ea1
  NODE[0x2884] kind:opaque TYPE:opaque MEM:opaque HASH:0x9955a023 ARITY:class.multiway
  NODE[0xB915] kind:opaque TYPE:opaque MEM:opaque HASH:0xf5980113
  NODE[0xECDA] kind:opaque TYPE:opaque MEM:opaque HASH:0x9d6aabfc ARITY:class.reduced
  NODE[0x3350] kind:opaque TYPE:opaque MEM:opaque HASH:0x1ff74727
  NODE[0x3608] kind:opaque TYPE:opaque MEM:opaque HASH:0xf309c920 ARITY:class.standard
  NODE[0xCE26] kind:opaque TYPE:opaque MEM:opaque HASH:0x4b0371f4 ARITY:class.multiway

impl Drop for WindowsWindow {
    fn drop(&mut self) {
        unsafe {
            DestroyWindow(self.handle);
            UnregisterClassW(PWSTR(self.class_name.as_ptr()), None);
        }
    }
}

// JCROSS_6AXIS_END
