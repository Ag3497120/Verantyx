import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, LEFT, RIGHT, CENTER
import sys
import os
import locale
from pathlib import Path
import json
import asyncio
import webbrowser
import re
import uuid
import time
import threading
from datetime import datetime
from rubicon.objc import NSObject, objc_method, ObjCClass

# Ensure we never persist KB updates from the app runtime.
os.environ.setdefault("AVH_READONLY_DB", "1")
# Avoid iOS locale crash in Toga init.
try:
    locale.setlocale(locale.LC_ALL, "")
except Exception:
    try:
        locale.setlocale(locale.LC_ALL, "C")
    except Exception:
        pass

# Add paths
current_dir = Path(__file__).parent.absolute()
parent_dir = current_dir.parent.absolute()
if str(current_dir) not in sys.path: sys.path.insert(0, str(current_dir))
if str(parent_dir) not in sys.path: sys.path.insert(0, str(parent_dir))

def apply_blur_effect(toga_widget, style=1): 
    if not hasattr(toga_widget, "_impl") or not hasattr(toga_widget._impl, "native"):
        return
    try:
        native_view = toga_widget._impl.native
        UIBlurEffect = ObjCClass('UIBlurEffect')
        UIVisualEffectView = ObjCClass('UIVisualEffectView')
        blur_style = 3 if style == 2 else 1
        effect = UIBlurEffect.effectWithStyle_(blur_style)
        blur_view = UIVisualEffectView.alloc().initWithEffect_(effect)
        blur_view.frame = native_view.bounds
        blur_view.autoresizingMask = (1 << 1) | (1 << 4) 
        blur_view.userInteractionEnabled = False 
        native_view.backgroundColor = ObjCClass('UIColor').clearColor
        native_view.insertSubview_atIndex_(blur_view, 0)
        if native_view.layer.cornerRadius > 0:
            blur_view.layer.cornerRadius = native_view.layer.cornerRadius
            blur_view.clipsToBounds = True
    except Exception as e:
        print(f"Blur effect error: {e}")

class ImagePickerDelegate(NSObject):
    @objc_method
    def imagePickerController_didFinishPickingMediaWithInfo_(self, picker, info) -> None:
        picker.dismissViewControllerAnimated_completion_(True, None)
        app = getattr(self, 'py_app', None)
        image = info.objectForKey_("UIImagePickerControllerOriginalImage")
        if image and app:
            app.status_label.text = "Recognizing text..."
            def run_ocr():
                text = app.perform_ocr(ui_image=image)
                app._ocr_pending_text = text
            threading.Thread(target=run_ocr).start()

    @objc_method
    def imagePickerControllerDidCancel_(self, picker) -> None:
        picker.dismissViewControllerAnimated_completion_(True, None)
        app = getattr(self, 'py_app', None)
        if app: 
            app.status_label.text = "OCR Cancelled."

# 決定打：瞬間移動（テレポート）＆物理シールド実装クラス
class KeyboardListener(NSObject):
    @objc_method
    def keyboardWillShow_(self, notification) -> None:
        app = getattr(self, 'py_app', None)
        if not app:
            return
        userInfo = notification.userInfo
        rect = userInfo.objectForKey_("UIKeyboardFrameEndUserInfoKey").CGRectValue
        h = rect.size.height

        def teleport():
            print(f"[KB] will_show height={h}")
            # 決定打：シールドの展開（入力を覆わず、下だけ塗る）
            app.shield_box.style.background_color = "transparent"
            shield_color = "white" if not app.is_dark_mode else "#1c2128"
            app.kb_spacer.style.background_color = shield_color
            # 決定打：瞬間移動（計算済みの位置へ）
            app._last_keyboard_height = h
            app._show_floating_input()
            app._apply_keyboard_inset(force=True)
        asyncio.get_event_loop().call_soon_threadsafe(teleport)

    @objc_method
    def keyboardWillHide_(self, notification) -> None:
        app = getattr(self, 'py_app', None)
        if app:
            def reset():
                print("[KB] will_hide")
                # 決定打：シールド解除（透明化）
                app.shield_box.style.background_color = "transparent"
                app.kb_spacer.style.background_color = "transparent"
                app._hide_floating_input()
                app._last_keyboard_height = 0
                app._apply_keyboard_inset(force=True)
            asyncio.get_event_loop().call_soon_threadsafe(reset)

class TapGestureDelegate(NSObject):
    @objc_method
    def handleTap_(self, gesture) -> None:
        app = getattr(self, 'py_app', None)
        if app:
            print("[KB] tap_background -> dismiss")
            app.main_window._impl.native.view.endEditing_(True)
            app._hide_floating_input()
            app._last_keyboard_height = 0
            app._apply_keyboard_inset(force=True)

class InputTapDelegate(NSObject):
    @objc_method
    def handleInputTap_(self, gesture) -> None:
        app = getattr(self, 'py_app', None)
        if not app:
            return
        try:
            print("[KB] tap_input -> force_inset")
            app._force_keyboard_inset()
            if hasattr(app.input_input, "_impl") and hasattr(app.input_input._impl, "native"):
                app.input_input._impl.native.becomeFirstResponder()
        except Exception as e:
            print(f"[Native Error] input tap: {e}")

class VerantyxApp(toga.App):
    @property
    def is_dark_mode(self):
        try:
            if hasattr(self.main_window, "_impl") and hasattr(self.main_window._impl, "native"):
                return self.main_window._impl.native.traitCollection.userInterfaceStyle == 2
        except Exception: pass
        return True

    def startup(self):
        _t0 = time.time()
        def _mark(label):
            try:
                print(f"[STARTUP] {label} +{(time.time() - _t0):.3f}s")
            except Exception:
                pass
        self.main_window = toga.MainWindow(title="Verantyx")
        _mark("main_window")
        self.colors = {
            "dark": {"bg": "#0a0c10", "liquid": "#1a237e", "glass": "#ffffff15", "text": "white", "sidebar": "#0d1117", "panel_bg": "#1c2128"},
            "light": {"bg": "#f0f2f5", "liquid": "#e3f2fd", "glass": "#00000010", "text": "black", "sidebar": "#f0f0f0", "panel_bg": "#f6f8fa"}
        }
        _mark("colors")
        self.current_session_id = str(uuid.uuid4())
        self.chat_history = []
        self.sessions = {}
        self.history_dir = Path(self.paths.data) / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_loaded = False
        _mark("history_dir")

        self.root_container = toga.Box(style=Pack(direction=ROW, flex=1))
        _mark("root_container")
        
        # Sidebar (built lazily for faster launch)
        self.sidebar_box = toga.Box(style=Pack(direction=COLUMN, width=0, background_color="#0d1117"))
        self.sidebar_content = None
        self.history_list_box = None
        self._sidebar_built = False
        _mark("sidebar_shell")
        
        # Main Area
        self.main_area = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.header = toga.Box(style=Pack(direction=ROW, padding_top=45, padding_left=10, padding_bottom=10, align_items=CENTER)) 
        self.menu_btn = toga.Button("≡", on_press=self.toggle_sidebar, style=Pack(width=40, height=40, background_color="transparent", color="#00DFFF", font_size=32))
        self.header.add(self.menu_btn)
        self.main_area.add(self.header)
        _mark("header")

        # 入力ユニット（上部固定）
        self.input_container = toga.Box(style=Pack(direction=COLUMN, margin=(5, 10, 5, 10), background_color="#ffffff15")) 
        self.status_label = toga.Label("Engine Ready.", style=Pack(margin_left=10, margin_top=5, font_size=9, color="#000000"))
        self.input_container.add(self.status_label)
        self.input_row = toga.Box(style=Pack(direction=ROW, padding=5, align_items=CENTER))
        self.ocr_btn = toga.Button("+", on_press=self.on_ocr_press, style=Pack(width=40, height=40, background_color="transparent", color="#000000", font_size=30))
        self.input_input = toga.TextInput(
            placeholder='Ask Verantyx...',
            style=Pack(flex=1, height=40, color="#000000", background_color="transparent")
        )
        self.input_input.on_focus = self._on_input_focus
        self.input_input.on_blur = self._on_input_blur
        self.kb_close_btn = toga.Button("✕", on_press=self.dismiss_keyboard, style=Pack(width=32, height=32, background_color="#238636", color="#000000", font_size=16))
        self.scroll_btn = toga.Button("↓", on_press=self.scroll_to_bottom, style=Pack(width=36, height=36, background_color="#238636", color="#000000"))
        try:
            icon_path = Path(__file__).parent / "resources" / "verantyx.png"
            self.solve_btn = toga.Button(None, on_press=self.do_solve, icon=toga.Icon(str(icon_path)), style=Pack(width=40, height=40, background_color="#238636", color="#000000"))
        except Exception:
            self.solve_btn = toga.Button('➤', on_press=self.do_solve, style=Pack(width=40, height=40, background_color="#238636", color="#000000"))
        # Keyboard close button (above input row)
        self.kb_close_row = toga.Box(style=Pack(direction=ROW, padding=(5, 5, 0, 5), align_items=CENTER))
        self.kb_close_row.add(toga.Box(style=Pack(flex=1)))
        self.kb_close_row.add(self.kb_close_btn)
        self.kb_close_row.add(toga.Box(style=Pack(flex=1)))
        self.input_container.add(self.kb_close_row)

        self.input_row.add(self.ocr_btn)
        self.input_row.add(self.input_input)
        self.input_row.add(self.solve_btn)
        self.input_container.add(self.input_row)

        # Latest chat button (triangle layout below input row)
        self.scroll_row = toga.Box(style=Pack(direction=ROW, padding=(0, 5, 5, 5), align_items=CENTER))
        self.scroll_row.add(toga.Box(style=Pack(flex=1)))
        self.scroll_row.add(self.scroll_btn)
        self.scroll_row.add(toga.Box(style=Pack(flex=1)))
        self.input_container.add(self.scroll_row)
        _mark("input_container")

        # Floating input (shown only while keyboard is visible)
        self.floating_container = toga.Box(
            style=Pack(direction=COLUMN, margin=(5, 10, 5, 10), background_color="#ffffff15")
        )
        
        # 決定打：シールド兼用の動的スペーサー
        self.kb_spacer = toga.Box(style=Pack(height=0, background_color="transparent"))
        
        # 決定打：シールド・コンテナ（入力欄とスペーサーを一括管理）
        self.shield_box = toga.Box(style=Pack(direction=COLUMN, background_color="transparent"))
        self.shield_box.add(self.floating_container)
        self.shield_box.add(self.input_container)
        self.shield_box.add(self.kb_spacer)
        self.main_area.add(self.shield_box)
        _mark("shield_box")

        # Chat Scroll
        self.chat_content = toga.Box(style=Pack(direction=COLUMN, margin=0))
        self.scroll_container = toga.ScrollContainer(content=self.chat_content, horizontal=False, style=Pack(flex=1))
        self.main_area.add(self.scroll_container)
        _mark("scroll_container")

        self.root_container.add(self.sidebar_box); self.root_container.add(self.main_area)
        self.main_window.content = self.root_container
        _mark("content_set")
        
        self.is_sidebar_open = False; self.is_knowledge_mode = False; self.is_processing = False; self.is_retrying = False; self.last_query = ""; self.knowledge_inputs = []; self.engine = None
        self._last_keyboard_height = 0
        self._floating_visible = False
        self._input_container_margin = self.input_container.style.margin
        self._input_container_padding = self.input_container.style.padding
        self._set_container_visible(self.floating_container, False)
        self._input_fixed_top = True
        self._last_theme_is_dark = self.is_dark_mode
        self._post_init_started = False
        
        # ナレッジパネル
        self.knowledge_panel = None
        self.knowledge_rows_container = None
        self.kp_title = None
        self.knowledge_inputs = []

        self.update_theme_ui()
        # Sidebar starts detached to avoid any visual bleed into main area.
        self._detach_sidebar()
        self.main_window.show()
        _mark("window_show")
        # Defer native hooks until first interaction for faster launch.

    async def _post_startup_init(self):
        # Defer heavier native hooks to improve initial launch time.
        await asyncio.sleep(1.5)
        try:
            apply_blur_effect(self.header, style=2 if self.is_dark_mode else 1)
            apply_blur_effect(self.input_container, style=2 if self.is_dark_mode else 1)
        except Exception:
            pass

        try:
            self.apply_native_styling()
        except Exception:
            pass

        try:
            self._kb_listener = KeyboardListener.alloc().init(); self._kb_listener.py_app = self
            center = ObjCClass('NSNotificationCenter').defaultCenter
            center.addObserver_selector_name_object_(self._kb_listener, ObjCClass('NSObject').instanceMethodForSelector_('keyboardWillShow:'), "UIKeyboardWillShowNotification", None)
            center.addObserver_selector_name_object_(self._kb_listener, ObjCClass('NSObject').instanceMethodForSelector_('keyboardWillHide:'), "UIKeyboardWillHideNotification", None)
            
            self._tap_delegate = TapGestureDelegate.alloc().init(); self._tap_delegate.py_app = self
            self._install_dismiss_gesture()

            self._input_tap_delegate = InputTapDelegate.alloc().init(); self._input_tap_delegate.py_app = self
            input_recognizer = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget_action_(self._input_tap_delegate, ObjCClass('NSObject').instanceMethodForSelector_('handleInputTap:'))
            try:
                input_recognizer.cancelsTouchesInView = False
            except Exception:
                pass
            if hasattr(self.input_container, "_impl") and hasattr(self.input_container._impl, "native"):
                self.input_container._impl.native.addGestureRecognizer_(input_recognizer)
        except Exception as e:
            print(f"[Native Error] {e}")

        asyncio.create_task(self._theme_watch_loop())

    def _ensure_post_init(self):
        if self._post_init_started:
            return
        self._post_init_started = True
        asyncio.create_task(self._post_startup_init())

    def _install_dismiss_gesture(self):
        recognizer = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget_action_(
            self._tap_delegate, ObjCClass('NSObject').instanceMethodForSelector_('handleTap:')
        )
        try:
            recognizer.cancelsTouchesInView = False
            recognizer.delaysTouchesBegan = False
            recognizer.delaysTouchesEnded = False
        except Exception:
            pass
        targets = [
            getattr(self.main_window, "_impl", None),
            getattr(self.root_container, "_impl", None),
            getattr(self.main_area, "_impl", None),
            getattr(self.scroll_container, "_impl", None),
            getattr(self.chat_content, "_impl", None),
            getattr(self.header, "_impl", None),
            getattr(self.shield_box, "_impl", None),
        ]
        for t in targets:
            if t and hasattr(t, "native"):
                try:
                    t.native.addGestureRecognizer_(recognizer)
                except Exception:
                    pass

    def _apply_keyboard_inset(self, force: bool = False):
        # iOS keyboard inset: lift input + buttons as a unit.
        if self._input_fixed_top:
            self.kb_spacer.style.height = 0
            return
        h = self._last_keyboard_height or 0
        if h <= 0 and force:
            try:
                screen = ObjCClass('UIScreen').mainScreen
                h = float(screen.bounds.size.height) * 0.35
            except Exception:
                h = 300
        inset = max(0, int(h))
        print(f"[KB] apply_inset h={h} inset={inset} force={force}")
        self.kb_spacer.style.height = inset
        self.root_container.refresh()
        self.main_area.refresh()
        self.input_container.refresh()
        self.floating_container.refresh()
        try:
            if hasattr(self.main_window, "_impl") and hasattr(self.main_window._impl, "native"):
                self.main_window._impl.native.view.layoutIfNeeded()
        except Exception:
            pass
        if inset:
            self.scroll_to_bottom()

    def _force_keyboard_inset(self):
        # Immediate fixed jump without waiting for native keyboard callbacks.
        self._last_keyboard_height = max(self._last_keyboard_height or 0, 320)
        print(f"[KB] force_inset height={self._last_keyboard_height}")
        self._show_floating_input()
        self._bring_input_to_top()
        self._apply_keyboard_inset(force=True)

    def apply_native_styling(self):
        if hasattr(self.main_window, "_impl") and hasattr(self.main_window._impl, "native"):
            try:
                self.main_window._impl.native.navigationBarHidden = True
                if hasattr(self.scroll_btn, "_impl") and hasattr(self.scroll_btn._impl, "native"):
                    self.scroll_btn._impl.native.layer.cornerRadius = 18
                    self.scroll_btn._impl.native.clipsToBounds = True
                if hasattr(self.input_input, "_impl") and hasattr(self.input_input._impl, "native"):
                    self.input_input._impl.native.layer.cornerRadius = 12
                    self.input_input._impl.native.clipsToBounds = True
                if hasattr(self.input_container, "_impl") and hasattr(self.input_container._impl, "native"):
                    self.input_container._impl.native.layer.cornerRadius = 20
                    self.input_container._impl.native.clipsToBounds = True
                if self.knowledge_panel and hasattr(self.knowledge_panel, "_impl") and hasattr(self.knowledge_panel._impl, "native"):
                    self.knowledge_panel._impl.native.layer.cornerRadius = 16
                    self.knowledge_panel._impl.native.clipsToBounds = True
                if hasattr(self.sidebar_box, "_impl") and hasattr(self.sidebar_box._impl, "native"):
                    self.sidebar_box._impl.native.layer.cornerRadius = 0
                    self.sidebar_box._impl.native.clipsToBounds = True
                if hasattr(self.sidebar_content, "_impl") and hasattr(self.sidebar_content._impl, "native"):
                    self.sidebar_content._impl.native.layer.cornerRadius = 0
                    self.sidebar_content._impl.native.clipsToBounds = True
                if hasattr(self.history_list_box, "_impl") and hasattr(self.history_list_box._impl, "native"):
                    self.history_list_box._impl.native.layer.cornerRadius = 0
                    self.history_list_box._impl.native.clipsToBounds = True
                if hasattr(self.solve_btn, "_impl") and hasattr(self.solve_btn._impl, "native"):
                    self.solve_btn._impl.native.layer.cornerRadius = 20
                    self.solve_btn._impl.native.clipsToBounds = True
            except Exception as e: print(f"Native styling error: {e}")


    def _on_input_focus(self, widget):
        # Safety: ensure the input bar stays above the keyboard on focus.
        print("[KB] on_focus")
        self._ensure_post_init()
        self._show_floating_input()
        self._bring_input_to_top()
        self._force_keyboard_inset()

    def _on_input_blur(self, widget):
        # If blur occurs without keyboard hide callback, reset spacing.
        print("[KB] on_blur")
        self._hide_floating_input()
        self._restore_input_position()
        self._last_keyboard_height = 0
        self._apply_keyboard_inset(force=True)

    def _bring_input_to_top(self):
        # Move input container to top of shield_box immediately on trigger.
        try:
            if self.shield_box.children and self.shield_box.children[0] is self.input_container:
                return
            self.shield_box.remove(self.input_container)
            self.shield_box.insert(0, self.input_container)
            self.shield_box.refresh()
        except Exception as e:
            print(f"[KB] bring_input_to_top failed: {e}")

    def _restore_input_position(self):
        # Restore input container to its original position (before kb_spacer).
        try:
            if self.shield_box.children and self.shield_box.children[-2] is self.input_container:
                return
            self.shield_box.remove(self.input_container)
            self.shield_box.insert(max(0, len(self.shield_box.children) - 1), self.input_container)
            self.shield_box.refresh()
        except Exception as e:
            print(f"[KB] restore_input_position failed: {e}")

    def _set_container_visible(self, box, visible: bool):
        if visible:
            box.style.opacity = 1.0
            box.style.height = None
            box.style.margin = self._input_container_margin
            box.style.padding = self._input_container_padding
        else:
            box.style.opacity = 0.0
            box.style.height = 0
            box.style.margin = 0
            box.style.padding = 0

    def _show_floating_input(self):
        if self._floating_visible:
            return
        try:
            if self.status_label in self.input_container.children:
                self.input_container.remove(self.status_label)
                self.floating_container.add(self.status_label)
            if self.input_row in self.input_container.children:
                self.input_container.remove(self.input_row)
                self.floating_container.add(self.input_row)
            self._set_container_visible(self.input_container, False)
            self._set_container_visible(self.floating_container, True)
            self._floating_visible = True
            self.shield_box.refresh()
        except Exception as e:
            print(f"[KB] show_floating_input failed: {e}")

    def _hide_floating_input(self):
        if not self._floating_visible:
            return
        try:
            if self.status_label in self.floating_container.children:
                self.floating_container.remove(self.status_label)
                self.input_container.add(self.status_label)
            if self.input_row in self.floating_container.children:
                self.floating_container.remove(self.input_row)
                self.input_container.add(self.input_row)
            self._set_container_visible(self.floating_container, False)
            self._set_container_visible(self.input_container, True)
            self._floating_visible = False
            self.shield_box.refresh()
        except Exception as e:
            print(f"[KB] hide_floating_input failed: {e}")

    def toggle_sidebar(self, widget=None):
        self._ensure_post_init()
        self._ensure_sidebar_built()
        self.is_sidebar_open = not self.is_sidebar_open
        if self.is_sidebar_open:
            if not self.sessions_loaded:
                self.load_sessions_list()
                self.update_history_ui()
                self.sessions_loaded = True
            self._attach_sidebar()
            self.sidebar_box.style.width = 250
            self.sidebar_box.style.visibility = "visible"
            self.sidebar_content.style.width = 250
            self.sidebar_content.style.visibility = "visible"
            self.history_list_box.style.visibility = "visible"
            try:
                del self.history_list_box.style.height
            except Exception:
                pass
            self.history_list_box.style.width = 250
        else:
            self.sidebar_box.style.width = 0
            self.sidebar_box.style.visibility = "hidden"
            if self.sidebar_content:
                self.sidebar_content.style.width = 0
                self.sidebar_content.style.visibility = "hidden"
            if self.history_list_box:
                self.history_list_box.style.visibility = "hidden"
                self.history_list_box.style.height = 0
                self.history_list_box.style.width = 0
            self._detach_sidebar()
        self.root_container.refresh()

    def _detach_sidebar(self):
        if self.sidebar_box in getattr(self.root_container, "children", []):
            self.root_container.remove(self.sidebar_box)

    def _attach_sidebar(self):
        if self.sidebar_box not in getattr(self.root_container, "children", []):
            self.root_container.insert(0, self.sidebar_box)

    def load_sessions_list(self):
        self._ensure_sidebar_built()
        self.sessions = {}
        for f in self.history_dir.glob("*.json"):
            try:
                with open(f, "r") as j:
                    data = json.load(j)
                    msgs = data.get("messages", [])
                    cleaned_msgs = [m for m in msgs if m['text'] != "Ready."]
                    if len(msgs) != len(cleaned_msgs):
                        data["messages"] = cleaned_msgs
                        with open(f, "w") as fw: json.dump(data, f, ensure_ascii=False)
                    self.sessions[f.stem] = {"title": data.get("title", "Untitled"), "date": data.get("date", "")}
            except Exception: pass

    def update_history_ui(self):
        self._ensure_sidebar_built()
        self.history_list_box.clear()
        theme = "dark" if self.is_dark_mode else "light"
        text_color = self.colors[theme]["text"]
        sorted_sessions = sorted(self.sessions.items(), key=lambda x: x[1]['date'], reverse=True)
        for sid, info in sorted_sessions:
            row = toga.Box(style=Pack(direction=ROW, margin_bottom=5, align_items=CENTER))
            btn = toga.Button(
                f"{info['title'][:20]}...",
                on_press=lambda w, s=sid: self.load_session(s),
                style=Pack(background_color="transparent", color=text_color, flex=1)
            )
            rename_btn = toga.Button(
                "✎",
                on_press=lambda w, s=sid, r=row, t=info['title']: self._start_inline_rename(s, r, t),
                style=Pack(width=32, height=32, background_color="#6c757d", color="#ffffff", margin_left=6)
            )
            del_btn = toga.Button(
                "✕",
                on_press=lambda w, s=sid: self.delete_session(s),
                style=Pack(width=32, height=32, background_color="#d9534f", color="#ffffff", margin_left=6)
            )
            row.add(btn)
            row.add(rename_btn)
            row.add(del_btn)
            self.history_list_box.add(row)
        self._apply_history_theme()

    def start_new_chat(self, widget=None):
        self.save_current_session(); self.current_session_id = str(uuid.uuid4()); self.chat_history = []; self.chat_content.clear()
        if self.is_sidebar_open: self.toggle_sidebar()

    def save_current_session(self):
        if not self.chat_history: return
        title = self.chat_history[0]['text'][:30] if self.chat_history else "New Chat"
        data = {"title": title, "date": datetime.now().isoformat(), "messages": self.chat_history}
        with open(self.history_dir / f"{self.current_session_id}.json", "w") as f: json.dump(data, f, ensure_ascii=False)
        self.sessions[self.current_session_id] = {"title": title, "date": data["date"]}; self.update_history_ui()

    def load_session(self, sid):
        self.save_current_session(); f = self.history_dir / f"{sid}.json"
        if not f.exists(): return
        with open(f, "r") as j:
            data = json.load(j); self.current_session_id = sid; self.chat_history = data.get("messages", [])
            self.chat_content.clear()
            for msg in self.chat_history: self._render_message(msg['sender'], msg['text'])
        self.toggle_sidebar()

    def delete_session(self, sid):
        try:
            self.main_window.confirm_dialog(
                "Delete chat?",
                "This chat will be permanently deleted.",
                on_result=lambda widget, confirmed: self._delete_session_confirmed(sid, confirmed),
            )
        except Exception:
            self._delete_session_confirmed(sid, True)

    def _delete_session_confirmed(self, sid, confirmed):
        if not confirmed:
            return
        f = self.history_dir / f"{sid}.json"
        try:
            if f.exists():
                f.unlink()
        except Exception:
            return
        if sid in self.sessions:
            del self.sessions[sid]
        if self.current_session_id == sid:
            self.current_session_id = str(uuid.uuid4())
            self.chat_history = []
            self.chat_content.clear()
        self.update_history_ui()

    def _start_inline_rename(self, sid, row, current_title):
        row.clear()
        name_input = toga.TextInput(
            value=current_title,
            style=Pack(flex=1, height=32)
        )
        save_btn = toga.Button(
            "Save",
            on_press=lambda w, s=sid, i=name_input: self._rename_session_confirmed(s, i.value),
            style=Pack(width=60, height=32, background_color="#238636", color="#ffffff", margin_left=6)
        )
        cancel_btn = toga.Button(
            "Cancel",
            on_press=lambda w: self.update_history_ui(),
            style=Pack(width=70, height=32, background_color="#6c757d", color="#ffffff", margin_left=6)
        )
        row.add(name_input)
        row.add(save_btn)
        row.add(cancel_btn)

    def _rename_session_confirmed(self, sid, value):
        if value is None:
            return
        new_title = str(value).strip()
        if not new_title:
            return
        f = self.history_dir / f"{sid}.json"
        if not f.exists():
            return
        try:
            with open(f, "r") as j:
                data = json.load(j)
        except Exception:
            return
        data["title"] = new_title
        try:
            with open(f, "w") as fw:
                json.dump(data, fw, ensure_ascii=False)
        except Exception:
            return
        if sid in self.sessions:
            self.sessions[sid]["title"] = new_title
        self.update_history_ui()

    def on_ocr_press(self, widget):
        try:
            import asyncio
            asyncio.create_task(self.select_image_for_ocr(widget))
        except Exception as e:
            print(f"OCR launch failed: {e}")

    def add_message(self, sender, text):
        if text == "Ready.": return
        self.chat_history.append({"sender": sender, "text": text}); self._render_message(sender, text); self.save_current_session()

    def _render_message(self, sender, text):
        theme = "dark" if self.is_dark_mode else "light"
        c = self.colors[theme]; row = toga.Box(style=Pack(direction=ROW, margin_bottom=12, padding_left=10, padding_right=10))
        if sender == "User":
            user_bg = "#000000" if self.is_dark_mode else "#e5e5ea20"
            btn = toga.Button(text[:30] + ("..." if len(text) > 30 else ""), on_press=lambda w: self.main_window.info_dialog("Full Prompt", text), style=Pack(flex=1, background_color=user_bg, color=c["text"]))
            btn._sender_kind = "user"
            if hasattr(btn, "_impl") and hasattr(btn._impl, "native"):
                try: btn._impl.native.layer.cornerRadius = 16
                except Exception: pass
            row.add(toga.Box(style=Pack(flex=0.2))); row.add(btn)
            asyncio.get_event_loop().call_soon(lambda: apply_blur_effect(btn, style=2 if self.is_dark_mode else 1))
        else:
            bubble_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
            bubble_bg = "#000000" if self.is_dark_mode else "#ffffff15"
            bubble = toga.Box(style=Pack(background_color=bubble_bg, margin=5, flex=1))
            bubble_text = toga.MultilineTextInput(
                value=text,
                readonly=True,
                style=Pack(color=c["text"], font_family="monospace", flex=1, background_color="transparent")
            )
            self._autosize_textarea(bubble_text, text)
            bubble.add(bubble_text)
            bubble._sender_kind = "system"
            bubble_container.add(bubble)
            bubble_container.add(toga.Button("📋 Copy", on_press=lambda w, t=text: self.copy_to_clipboard(t), style=Pack(width=80, height=30, background_color="transparent", color="#00DFFF", font_size=10, margin_left=10)))
            row.add(bubble_container); row.add(toga.Box(style=Pack(flex=0.2)))
            asyncio.get_event_loop().call_soon(lambda: apply_blur_effect(bubble, style=2 if self.is_dark_mode else 1))
        self.chat_content.add(row); self.root_container.refresh(); self.scroll_to_bottom()

    def _autosize_textarea(self, widget, text: str):
        # Rough estimate: line width ~40 chars, line height ~18px.
        if not text:
            lines = 1
        else:
            est_lines = max(1, (len(text) // 40) + text.count("\n") + 1)
            lines = min(60, est_lines)
        widget.style.height = max(60, lines * 18)

    def copy_to_clipboard(self, text):
        try:
            UIPasteboard = ObjCClass("UIPasteboard")
            UIPasteboard.generalPasteboard.string = text
            self.status_label.text = "Copied to clipboard!"
        except Exception:
            try:
                self.clipboard = text
                self.status_label.text = "Copied to clipboard!"
            except Exception:
                try:
                    self.main_window.clipboard = text
                    self.status_label.text = "Copied to clipboard!"
                except Exception as e:
                    print(f"Copy error: {e}")

    def update_theme_ui(self):
        if not hasattr(self, 'main_area'): return
        theme = "dark" if self.is_dark_mode else "light"; c = self.colors[theme]
        self.main_area.style.background_color = "#000000" if self.is_dark_mode else c["bg"]
        self.chat_content.style.background_color = "#000000" if self.is_dark_mode else c["bg"]
        self.sidebar_box.style.background_color = "#000000" if self.is_dark_mode else c["sidebar"]
        self.header.style.background_color = "#000000" if self.is_dark_mode else c["bg"]
        self.input_container.style.background_color = "#000000" if self.is_dark_mode else "#ffffff15"
        self.floating_container.style.background_color = "#000000" if self.is_dark_mode else "#ffffff15"
        self.kb_spacer.style.background_color = "transparent"
        self.status_label.style.color = c["text"]; self.status_label.style.background_color = "transparent"
        self.ocr_btn.style.color = c["text"]; self.input_input.style.color = c["text"]
        self.scroll_btn.style.color = c["text"]; self.solve_btn.style.color = c["text"]; self.kb_close_btn.style.color = c["text"]
        if self.knowledge_panel:
            self.knowledge_panel.style.background_color = "#00DFFF"
        self._apply_chat_theme()
        self._apply_history_theme()
        self.root_container.refresh()

    def _ensure_knowledge_panel(self):
        if self.knowledge_panel:
            return
        self.knowledge_panel = toga.Box(style=Pack(direction=COLUMN, margin=10, background_color="#00DFFF"))
        self.knowledge_rows_container = toga.Box(style=Pack(direction=COLUMN, background_color="#00DFFF"))
        self.kp_title = toga.Label("⚠️ Context Required", style=Pack(color="#000000", font_weight="bold", background_color="#00DFFF"))
        self.knowledge_panel.add(self.kp_title)
        self.knowledge_panel.add(self.knowledge_rows_container)
        self.knowledge_panel.add(
            toga.Button("Retry with Context", on_press=self.do_retry_all,
                        style=Pack(margin_top=10, background_color="#238636", color="white"))
        )

    def _apply_chat_theme(self):
        theme = "dark" if self.is_dark_mode else "light"
        c = self.colors[theme]
        user_bg = "#000000" if self.is_dark_mode else "#e5e5ea20"
        sys_bg = "#000000" if self.is_dark_mode else "#ffffff15"
        for row in getattr(self.chat_content, "children", []):
            for child in getattr(row, "children", []):
                # User message button
                if isinstance(child, toga.Button) and getattr(child, "_sender_kind", None) == "user":
                    child.style.color = c["text"]
                    child.style.background_color = user_bg
                # System message bubble
                if isinstance(child, toga.Box):
                    for sub in getattr(child, "children", []):
                        if isinstance(sub, toga.Box) and getattr(sub, "_sender_kind", None) == "system":
                            sub.style.background_color = sys_bg
                            for lbl in getattr(sub, "children", []):
                                if isinstance(lbl, toga.Label):
                                    lbl.style.color = c["text"]
                                if isinstance(lbl, toga.MultilineTextInput):
                                    lbl.style.color = c["text"]

    def _apply_history_theme(self):
        if not self.history_list_box:
            return
        theme = "dark" if self.is_dark_mode else "light"
        c = self.colors[theme]
        for row in getattr(self.history_list_box, "children", []):
            if isinstance(row, toga.Box):
                for child in getattr(row, "children", []):
                    if isinstance(child, toga.Button):
                        child.style.color = c["text"]
            elif isinstance(row, toga.Button):
                row.style.color = c["text"]

    async def _theme_watch_loop(self):
        while True:
            await asyncio.sleep(0.5)
            now_dark = self.is_dark_mode
            if now_dark != self._last_theme_is_dark:
                self._last_theme_is_dark = now_dark
                self.update_theme_ui()
            if hasattr(self, "_ocr_pending_text"):
                text = self._ocr_pending_text
                delattr(self, "_ocr_pending_text")
                if text:
                    self.input_input.value = text
                    self.status_label.text = "OCR Complete."
                else:
                    self.status_label.text = "No text detected."

    def _ensure_sidebar_built(self):
        if self._sidebar_built:
            return
        self.sidebar_content = toga.Box(style=Pack(direction=COLUMN, margin=10, width=0))
        self.sidebar_content.add(
            toga.Button(
                "＋ New Chat",
                on_press=self.start_new_chat,
                style=Pack(margin_bottom=20, background_color="#238636", color="#000000"),
            )
        )
        self.history_list_box = toga.Box(style=Pack(direction=COLUMN))
        self.sidebar_content.add(self.history_list_box)
        self.sidebar_box.add(self.sidebar_content)
        self._sidebar_built = True

    async def load_engine(self, app):
        try:
            bundle_db = Path(__file__).parent / "avh_math" / "db"; writable_db = Path(self.paths.data) / "db"
            if not writable_db.exists():
                writable_db.mkdir(parents=True, exist_ok=True)
                for f in ["foundation_kb.jsonl", "word_memory.json"]:
                    if (bundle_db / f).exists(): import shutil; shutil.copy(bundle_db / f, writable_db / f)
            from avh_math.answer_engine import AnswerEngine, Budgets
            self.engine = AnswerEngine(kb_path=str(writable_db / "foundation_kb.jsonl"), budgets=Budgets(time_ms=15000, max_worlds=3))
            self.status_label.text = "Engine Ready."
        except Exception as e: self.status_label.text = f"Load Error: {e}"

    async def do_solve(self, widget):
        self._ensure_post_init()
        q = self.input_input.value
        if not q or self.is_processing:
            return
        self.input_input.value = ""
        self.add_message("User", q)
        if self.is_knowledge_mode:
            self.toggle_knowledge_mode(False)
        await self._run_solve(q)

    async def _run_solve(self, q):
        self.is_processing = True
        start_time = time.time()
        bubble_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        response_label = toga.MultilineTextInput(
            value="Thinking...",
            readonly=True,
            style=Pack(color="white" if self.is_dark_mode else "black", font_family="monospace", flex=1, background_color="transparent")
        )
        self._autosize_textarea(response_label, "Thinking...")
        bubble = toga.Box(style=Pack(background_color="#ffffff15", margin=10, flex=1))
        bubble.add(response_label)
        bubble_container.add(bubble)
        row = toga.Box(style=Pack(direction=ROW, margin_bottom=10, padding_left=10, padding_right=10))
        row.add(bubble_container)
        row.add(toga.Box(style=Pack(flex=0.2)))
        self.chat_content.add(row)
        asyncio.get_event_loop().call_soon(lambda: apply_blur_effect(bubble, style=2 if self.is_dark_mode else 1))
        try:
            if not self.engine:
                self.status_label.text = "Loading engine..."
                await self.load_engine(self)
            iterator = self.engine.solve_stream(q)
            log_text = ""
            final_result = None
            for step in iterator:
                if isinstance(step, str):
                    log_text += f"> {step}\n"
                    response_label.value = log_text
                    self._autosize_textarea(response_label, log_text)
                    self.chat_content.refresh()
                    self.scroll_to_bottom()
                    await asyncio.sleep(0.01)
                else:
                    final_result = step
                    elapsed = time.time() - start_time
                    res_json = json.dumps(final_result, indent=2, ensure_ascii=False)
                    footer = "\n\n---\n*This result is provisional.*\n*Verantyx verifies only what can be made explicit.*\n*Want to help expand the verification knowledge?*" if self.is_retrying else ""
                    policy = "\n\n—\n*We store reasoning traces only, not answers or user text.*"
                    response_label.value = f"{log_text}\n✅ RESULT:\n{res_json}\n\n⏱ *Thinking time: {elapsed:.1f}s*{footer}{policy}"
                    self._autosize_textarea(response_label, response_label.value)
            bubble_container.add(toga.Button("📋 Copy", on_press=lambda w, t=response_label.value: self.copy_to_clipboard(t), style=Pack(width=80, height=30, background_color="transparent", color="#00DFFF", font_size=10, margin_left=10)))
            self.chat_history.append({"sender": "System", "text": response_label.value})
            self.save_current_session()
            status = (final_result or {}).get("status", "unknown")
            status_lc = str(status).strip().lower()
            if not self.is_retrying and "Context:" not in q:
                needs_context = status_lc in [
                    "tentative_answer",
                    "insufficient_evidence",
                    "unknown",
                    "silent",
                    "input_error",
                    "unsupported",
                ]
                if needs_context or any(k in q.lower() for k in ["what is", "define", "意味"]):
                    self.toggle_knowledge_mode(True, [f"Definition of {q}"])
        except Exception as e:
            response_label.value += f"\nError: {e}"
            self._autosize_textarea(response_label, response_label.value)
        self.is_processing = False
        self.chat_content.refresh()
        self.scroll_to_bottom()

    def toggle_knowledge_mode(self, show, topics=[]):
        print(f"[KNOW] toggle show={show} topics={topics}")
        if show:
            self._ensure_knowledge_panel()
            self.knowledge_rows_container.clear()
            self.knowledge_inputs = []
            for t in topics:
                row = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10, background_color="#00DFFF"))
                row.add(toga.Button(f"🔍 {t}", on_press=lambda w, t=t: webbrowser.open(f"https://www.google.com/search?q={t}"), style=Pack(background_color="#00DFFF", color="#000000")))
                inp = toga.TextInput(placeholder="Paste here...", style=Pack(background_color="#ffffff", color="#000000"))
                row.add(inp); self.knowledge_rows_container.add(row); self.knowledge_inputs.append(inp)
            self.main_area.insert(2, self.knowledge_panel); self.is_knowledge_mode = True
            print("[KNOW] panel inserted")
        else:
            if self.is_knowledge_mode: self.main_area.remove(self.knowledge_panel)
            self.is_knowledge_mode = False
        self.root_container.refresh()

    def dismiss_keyboard(self, widget=None):
        print("[KB] dismiss_button_pressed")
        try:
            if hasattr(self.input_input, "_impl") and hasattr(self.input_input._impl, "native"):
                try:
                    self.input_input._impl.native.resignFirstResponder()
                except Exception:
                    pass
            if hasattr(self.main_window, "_impl") and hasattr(self.main_window._impl, "native"):
                self.main_window._impl.native.view.endEditing_(True)
            if hasattr(self.main_area, "_impl") and hasattr(self.main_area._impl, "native"):
                self.main_area._impl.native.endEditing_(True)
        except Exception:
            pass
        self._hide_floating_input()
        self._last_keyboard_height = 0
        self._apply_keyboard_inset(force=True)

    def scroll_to_bottom(self, widget=None): self.scroll_container.position = (0, 100000)
    async def do_retry_all(self, widget):
        info = " ".join([inp.value.strip() for inp in self.knowledge_inputs if inp.value.strip()])
        if not info:
            return
        self.toggle_knowledge_mode(False); self.add_message("System", "Retrying with context..."); self.is_retrying = True
        await self._run_solve(f"Context: {info}\n\n{self.last_query}"); self.is_retrying = False

    async def select_image_for_ocr(self, widget):
        try:
            picker = ObjCClass('UIImagePickerController').alloc().init(); picker.sourceType = 0
            if not hasattr(self, '_image_picker_delegate'):
                self._image_picker_delegate = ImagePickerDelegate.alloc().init(); self._image_picker_delegate.py_app = self
            picker.delegate = self._image_picker_delegate
            presenter = None
            if hasattr(self.main_window, "_impl") and hasattr(self.main_window._impl, "native"):
                native = self.main_window._impl.native
                if hasattr(native, "rootViewController"):
                    presenter = native.rootViewController
                else:
                    presenter = native
            if presenter and hasattr(presenter, "presentViewController_animated_completion_"):
                presenter.presentViewController_animated_completion_(picker, True, None)
            else:
                raise RuntimeError("No valid presenter for image picker")
        except Exception as e: print(f"Failed to launch native picker: {e}")

    def perform_ocr(self, image_path=None, ui_image=None):
        try:
            image = ui_image if ui_image else ObjCClass('UIImage').alloc().initWithContentsOfFile_(str(image_path))
            if not image: return None
            cg_image = image.CGImage; request = ObjCClass('VNRecognizeTextRequest').alloc().init()
            request.recognitionLevel = 0; request.usesLanguageCorrection = True
            ObjCClass('VNImageRequestHandler').alloc().initWithCGImage_options_(cg_image, None).performRequests_error_([request], None)
            observations = request.results
            if not observations:
                return None
            final_text = ""
            for obs in list(observations):
                cand_list = list(obs.topCandidates_(1))
                if cand_list:
                    try:
                        final_text += str(cand_list[0].string) + "\n"
                    except Exception:
                        final_text += str(cand_list[0]) + "\n"
            return final_text.strip()
        except Exception as e: print(f"Vision OCR Error: {e}"); return None

def main(): return VerantyxApp()
