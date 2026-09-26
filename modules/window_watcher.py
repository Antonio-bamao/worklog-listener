from __future__ import annotations

import ctypes
import threading
from types import TracebackType
from typing import Callable

from .models import DependencyError, WindowInfo


EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000


def has_foreground_event_api() -> bool:
    user32 = ctypes.windll.user32
    return hasattr(user32, "SetWinEventHook") and hasattr(user32, "UnhookWinEvent")


class SingleInstance:
    def __init__(self, name: str) -> None:
        self.name = name
        self.handle = None

    def __enter__(self) -> SingleInstance:
        try:
            import win32api
            import win32event
            import winerror
        except ImportError as exc:
            raise DependencyError("Missing pywin32. Run: pip install pywin32") from exc

        self.handle = win32event.CreateMutex(None, False, self.name)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            raise RuntimeError("Another tracker instance is already running")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.handle:
            try:
                import win32api

                win32api.CloseHandle(self.handle)
            except ImportError:
                pass


def get_foreground_window() -> WindowInfo | None:
    try:
        import psutil
        import win32gui
        import win32process
    except ImportError as exc:
        raise DependencyError("Missing Windows dependencies. Run: pip install pywin32 psutil") from exc

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    title = win32gui.GetWindowText(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    process = "unknown.exe"
    try:
        process = psutil.Process(pid).name()
    except psutil.Error:
        pass
    return WindowInfo(process=process, title=title, hwnd=hwnd)


class ForegroundWindowWatcher(threading.Thread):
    def __init__(
        self,
        on_window: Callable[[WindowInfo], None],
        get_window_func: Callable[[], WindowInfo | None] = get_foreground_window,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        super().__init__(name="ForegroundWindowWatcher")
        self.on_window = on_window
        self.get_window_func = get_window_func
        self.on_error = on_error
        self.last_window: WindowInfo | None = None

    def handle_foreground_event(self) -> bool:
        window = self.get_window_func()
        if not window:
            return False
        if self.last_window and (window.process, window.title, window.hwnd) == (
            self.last_window.process,
            self.last_window.title,
            self.last_window.hwnd,
        ):
            return False
        self.last_window = window
        self.on_window(window)
        return True

    def run(self) -> None:
        try:
            import win32con
            import win32gui

            user32 = ctypes.windll.user32
            wineventproc = ctypes.WINFUNCTYPE(
                None,
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_long,
                ctypes.c_long,
                ctypes.c_long,
                ctypes.c_uint,
                ctypes.c_uint,
            )

            @wineventproc
            def callback(hook, event, hwnd, id_object, id_child, event_thread, event_time) -> None:
                if id_object == win32con.OBJID_WINDOW:
                    self.handle_foreground_event()

            hook = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                0,
                callback,
                0,
                0,
                WINEVENT_OUTOFCONTEXT,
            )
            try:
                win32gui.PumpMessages()
            finally:
                user32.UnhookWinEvent(hook)
        except Exception as exc:
            if self.on_error:
                self.on_error(exc)
