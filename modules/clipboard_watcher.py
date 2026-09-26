from __future__ import annotations

import ctypes
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import ClipboardSnapshot, DependencyError


WM_CLIPBOARDUPDATE = 0x031D
HWND_MESSAGE = -3


def has_clipboard_listener_api() -> bool:
    user32 = ctypes.windll.user32
    return hasattr(user32, "AddClipboardFormatListener") and hasattr(user32, "RemoveClipboardFormatListener")


def summarize_clipboard(
    snapshot: ClipboardSnapshot,
    max_text_length: int = 200,
    keep_head: int | None = None,
    keep_tail: int | None = None,
) -> str:
    if snapshot.kind == "text":
        text = snapshot.text or ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace('"', '\\"')
        if len(text) > max_text_length:
            if keep_head is not None and keep_tail is not None:
                text = f"{text[:keep_head]}...{text[-keep_tail:]} ({len(text)} chars)"
            else:
                text = text[:max_text_length] + "..."
        return f'content: "{text}"'
    if snapshot.kind == "files":
        shown = "; ".join(str(path).replace("\\", "/") for path in snapshot.files[:2])
        return f"files: {len(snapshot.files)} | {shown}" if shown else "files: 0"
    return f"type: {snapshot.kind}"


def read_clipboard() -> ClipboardSnapshot | None:
    try:
        import win32clipboard
        import win32con
    except ImportError as exc:
        raise DependencyError("Missing pywin32. Run: pip install pywin32") from exc

    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return ClipboardSnapshot("text", text=win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT))
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP):
            files = [Path(item) for item in win32clipboard.GetClipboardData(win32con.CF_HDROP)]
            return ClipboardSnapshot("files", files=files)
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
            return ClipboardSnapshot("image")
        return None
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass


class ClipboardChangeWatcher(threading.Thread):
    def __init__(
        self,
        on_clipboard: Callable[[ClipboardSnapshot], None],
        read_clipboard_func: Callable[[], ClipboardSnapshot | None] = read_clipboard,
        dedupe_seconds: float = 1.0,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        super().__init__(name="ClipboardChangeWatcher")
        self.on_clipboard = on_clipboard
        self.read_clipboard_func = read_clipboard_func
        self.dedupe_seconds = dedupe_seconds
        self.on_error = on_error
        self.last_signature: tuple[str, str] | None = None
        self.last_at: datetime | None = None

    def handle_clipboard_update(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        snapshot = self.read_clipboard_func()
        if snapshot is None:
            return False
        signature = snapshot.signature()
        if (
            signature == self.last_signature
            and self.last_at is not None
            and (now - self.last_at).total_seconds() <= self.dedupe_seconds
        ):
            return False
        self.last_signature = signature
        self.last_at = now
        self.on_clipboard(snapshot)
        return True

    def run(self) -> None:
        try:
            import win32gui

            user32 = ctypes.windll.user32
            class_name = f"WorkActivityTrackerClipboardWindow{os.getpid()}"

            def wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
                if msg == WM_CLIPBOARDUPDATE:
                    self.handle_clipboard_update()
                    return 0
                return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

            wndclass = win32gui.WNDCLASS()
            wndclass.lpfnWndProc = wndproc
            wndclass.lpszClassName = class_name
            wndclass.hInstance = win32gui.GetModuleHandle(None)

            hwnd = None
            try:
                atom = win32gui.RegisterClass(wndclass)
                hwnd = win32gui.CreateWindow(
                    atom,
                    class_name,
                    0,
                    0,
                    0,
                    0,
                    0,
                    HWND_MESSAGE,
                    0,
                    wndclass.hInstance,
                    None,
                )
                if not user32.AddClipboardFormatListener(hwnd):
                    raise RuntimeError("AddClipboardFormatListener failed")
                win32gui.PumpMessages()
            finally:
                if hwnd:
                    try:
                        user32.RemoveClipboardFormatListener(hwnd)
                    except Exception:
                        pass
                    try:
                        win32gui.DestroyWindow(hwnd)
                    except Exception:
                        pass
        except Exception as exc:
            if self.on_error:
                self.on_error(exc)
