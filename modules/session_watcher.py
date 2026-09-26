from __future__ import annotations

import os
import threading

from .logger import MarkdownLogger


WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
WM_WTSSESSION_CHANGE = 0x02B1


def session_event_type(wparam: int) -> str | None:
    if wparam == WTS_SESSION_LOCK:
        return "LOCK"
    if wparam == WTS_SESSION_UNLOCK:
        return "UNLOCK"
    return None


class SessionChangeListener(threading.Thread):
    def __init__(self, logger: MarkdownLogger) -> None:
        super().__init__(name="SessionChangeListener")
        self.logger = logger

    def run(self) -> None:
        try:
            import win32gui
            import win32ts
        except ImportError:
            self.logger.write_event("GAP", "session listener unavailable: missing pywin32")
            return

        class_name = f"WorkActivityTrackerSessionWindow{os.getpid()}"

        def wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_WTSSESSION_CHANGE:
                event_type = session_event_type(wparam)
                if event_type:
                    self.logger.write_event(event_type)
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
                0,
                0,
                wndclass.hInstance,
                None,
            )
            win32ts.WTSRegisterSessionNotification(hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)
            win32gui.PumpMessages()
        except Exception as exc:
            self.logger.write_event("GAP", f"session listener stopped: {exc}")
        finally:
            try:
                if hwnd:
                    win32ts.WTSUnRegisterSessionNotification(hwnd)
            except Exception:
                pass
            try:
                if hwnd:
                    win32gui.DestroyWindow(hwnd)
            except Exception:
                pass
