from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from modules.archiver import ArchiveScheduler, MonthlyCompressor, WeeklyArchiver
from modules.clipboard_watcher import ClipboardChangeWatcher, read_clipboard, summarize_clipboard
from modules.config import WorkLogConfig, default_log_root, load_config, week_bounds
from modules.idle_detector import get_idle_seconds
from modules.keyboard_watcher import KeyBurstAggregator, format_hotkey, normalize_key_name
from modules.logger import ErrorLogger, MarkdownLogger, format_event_line
from modules.models import ClipboardSnapshot, DependencyError, LogEvent, WindowInfo
from modules.session_watcher import SessionChangeListener, session_event_type
from modules.uia_helper import InputSnapshot, focused_control_is_password, get_browser_url, get_focused_input_snapshot, is_probable_url
from modules.window_watcher import ForegroundWindowWatcher, SingleInstance, get_foreground_window


class ActivityTracker:
    def __init__(self, config: WorkLogConfig) -> None:
        self.config = config
        self.logger = MarkdownLogger(config)
        self.error_logger = ErrorLogger(config.log_root, max_bytes=config.error_log_max_bytes)
        self.key_burst = KeyBurstAggregator()
        self.last_window: WindowInfo | None = None
        self.last_url: str | None = None
        self.last_clipboard_signature: tuple[str, str] | None = None
        self.last_clipboard: ClipboardSnapshot | None = None
        self.last_input_signature: tuple[str, str, bool] | None = None
        self.last_key_at: datetime | None = None
        self.idle = False
        self._pressed: set[str] = set()
        self.archive_scheduler = ArchiveScheduler(
            weekly_job=lambda day: WeeklyArchiver(self.config).archive_week(day),
            monthly_job=lambda year, month: MonthlyCompressor(self.config).compress_month(year, month),
        )

    def run(self) -> None:
        with SingleInstance(self.config.single_instance_mutex_name):
            self.logger.write_event("RESUME", "tracker started")
            self._start_keyboard_listener()
            self._start_session_listener()
            self._start_window_listener()
            self._start_clipboard_listener()
            while True:
                self.tick()
                time.sleep(self.config.poll_interval)

    def run_once(self) -> Path:
        self.tick()
        return self.config.daily_log_path()

    def tick(self) -> None:
        now = datetime.now()
        window = self._safe_call(get_foreground_window)
        if window:
            self._handle_window_change(window, now=now)

        if window and not self._is_excluded_window(window):
            url = self._safe_call(get_browser_url, window)
            if url and url != self.last_url:
                self.last_url = url
                self.logger.write_event("URL", url, now=now)

        self._poll_clipboard(window, now)
        self._poll_focused_input(now)
        self._poll_idle(now)
        self._safe_call(self.archive_scheduler.tick, now)
        if self.key_burst.should_flush(now, self.config.key_burst_seconds):
            event = self.key_burst.flush(now=now)
            self.logger.write_event(event.event_type, event.content, now=event.timestamp)

    def _window_changed(self, window: WindowInfo) -> bool:
        return not self.last_window or (window.process, window.title) != (self.last_window.process, self.last_window.title)

    def _is_excluded_window(self, window: WindowInfo) -> bool:
        title = window.title.lower()
        return any(pattern.lower() in title for pattern in self.config.exclude_window_titles)

    def _handle_window_change(self, window: WindowInfo, now: datetime | None = None) -> bool:
        if not self._window_changed(window):
            return False
        self.last_window = window
        if self._is_excluded_window(window):
            return False
        self.logger.write_event("APP", window.as_log_content(), now=now)
        url = self._safe_call(get_browser_url, window)
        if url and url != self.last_url:
            self.last_url = url
            self.logger.write_event("URL", url, now=now)
        return True

    def _poll_clipboard(self, window: WindowInfo | None, now: datetime) -> None:
        snapshot = self._safe_call(read_clipboard)
        if snapshot is None:
            return
        self._handle_clipboard_change(snapshot, window=window, now=now)

    def _handle_clipboard_change(
        self,
        snapshot: ClipboardSnapshot,
        window: WindowInfo | None = None,
        now: datetime | None = None,
    ) -> bool:
        signature = snapshot.signature()
        if signature == self.last_clipboard_signature:
            return False
        self.last_clipboard = snapshot
        self.last_clipboard_signature = signature
        source_window = window or self.last_window
        source = source_window.process if source_window else "unknown.exe"
        content = (
            f"from: {source}\n"
            f"{summarize_clipboard(snapshot, self.config.max_clip_text_length, self.config.text_truncate_keep_head, self.config.text_truncate_keep_tail)}"
        )
        self.logger.write_event("CLIP_COPY", content, now=now)
        return True

    def _poll_idle(self, now: datetime) -> None:
        idle_seconds = self._safe_call(get_idle_seconds)
        if idle_seconds is None:
            return
        if idle_seconds >= self.config.idle_seconds and not self.idle:
            self.idle = True
            self.logger.write_event("IDLE_START", f"no input for {self.config.idle_seconds // 60}min", now=now)
        elif idle_seconds < self.config.idle_seconds and self.idle:
            self.idle = False
            self.logger.write_event("IDLE_END", "input resumed", now=now)

    def _poll_focused_input(self, now: datetime) -> None:
        snapshot = self._safe_call(get_focused_input_snapshot)
        if snapshot is None:
            return
        self._handle_input_snapshot(snapshot, now=now)

    def _handle_input_snapshot(self, snapshot: InputSnapshot, now: datetime | None = None) -> bool:
        signature = snapshot.signature()
        if signature == self.last_input_signature:
            return False
        self.last_input_signature = signature
        now = now or datetime.now()
        process = self.last_window.process if self.last_window else "unknown.exe"
        if snapshot.is_password:
            self.logger.write_event("SKIP_PWD", f"{process} | password field", now=now)
            return True
        if is_probable_url(snapshot.value):
            return False

        event_type = "AUTOFILL"
        if self.last_key_at and (now - self.last_key_at).total_seconds() <= 2:
            event_type = "TEXT"
        value = snapshot.value.replace('"', '\\"')
        if len(value) > self.config.max_clip_text_length:
            value = value[: self.config.max_clip_text_length] + "..."
        content = f'{process} | field={snapshot.field} | "{value}"'
        self.logger.write_event(event_type, content, now=now)
        return True

    def _start_keyboard_listener(self) -> None:
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise DependencyError("Missing pynput. Run: pip install pynput") from exc

        def on_press(key: object) -> None:
            self.handle_key_press(key)

        def on_release(key: object) -> None:
            self.handle_key_release(key)

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()

    def _start_session_listener(self) -> None:
        listener = SessionChangeListener(self.logger)
        listener.daemon = True
        listener.start()

    def _start_window_listener(self) -> None:
        listener = ForegroundWindowWatcher(
            on_window=lambda window: self._handle_window_change(window),
            on_error=self.error_logger.write_exception,
        )
        listener.daemon = True
        listener.start()

    def _start_clipboard_listener(self) -> None:
        listener = ClipboardChangeWatcher(
            on_clipboard=lambda snapshot: self._handle_clipboard_change(snapshot),
            on_error=self.error_logger.write_exception,
        )
        listener.daemon = True
        listener.start()

    def handle_key_press(self, key: object) -> None:
        process = self.last_window.process if self.last_window else "unknown.exe"
        key_name = normalize_key_name(key)
        if key_name in {"Ctrl", "Shift", "Alt", "Win"}:
            self._pressed.add(key_name)
            return
        self.last_key_at = datetime.now()

        if self._safe_call(focused_control_is_password):
            self.logger.write_event("SKIP_PWD", f"{process} | password field, 1 chars typed")
            return

        hotkey = format_hotkey(self._pressed, key_name)
        if hotkey:
            self.key_burst.record_hotkey(process, hotkey)
            self.logger.write_event("HOTKEY", f"{process} | {hotkey}")
            if hotkey == "Ctrl+V" and self.last_clipboard:
                content = f"to: {process}\ncontent matched last clipboard"
                self.logger.write_event("CLIP_PASTE", content)
        else:
            self.key_burst.record_key(process)

    def handle_key_release(self, key: object) -> None:
        key_name = normalize_key_name(key)
        self._pressed.discard(key_name)

    def _safe_call(self, func, *args):
        try:
            return func(*args)
        except DependencyError:
            raise
        except Exception as exc:
            self.error_logger.write_exception(exc)
            return None


def install_exception_hooks(error_logger: ErrorLogger) -> None:
    def excepthook(exc_type, exc, tb) -> None:
        error_logger.write("".join(__import__("traceback").format_exception(exc_type, exc, tb)).rstrip())

    def threadhook(args: threading.ExceptHookArgs) -> None:
        error_logger.write(
            "".join(__import__("traceback").format_exception(args.exc_type, args.exc_value, args.exc_traceback)).rstrip()
        )

    sys.excepthook = excepthook
    threading.excepthook = threadhook


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows work activity tracker")
    parser.add_argument("--config", type=Path, default=Path("config.json"), help="Config JSON path, default .\\config.json")
    parser.add_argument("--log-root", type=Path, default=None, help="Override log root, default %%LOCALAPPDATA%%\\WorkLog")
    parser.add_argument("--once", action="store_true", help="Run one polling tick and exit")
    parser.add_argument("--archive-week", action="store_true", help="Generate the current week summary and exit")
    parser.add_argument("--idle-seconds", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config, log_root=args.log_root, idle_seconds=args.idle_seconds)
    error_logger = ErrorLogger(config.log_root, max_bytes=config.error_log_max_bytes)
    install_exception_hooks(error_logger)

    try:
        if args.archive_week:
            path = WeeklyArchiver(config).archive_week()
            print(path)
            return 0
        tracker = ActivityTracker(config)
        if args.once:
            path = tracker.run_once()
            print(path)
            return 0
        tracker.run()
        return 0
    except DependencyError as exc:
        error_logger.write(str(exc))
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        error_logger.write_exception(exc)
        return 1


__all__ = [
    "ActivityTracker",
    "ArchiveScheduler",
    "ClipboardSnapshot",
    "ClipboardChangeWatcher",
    "DependencyError",
    "ErrorLogger",
    "ForegroundWindowWatcher",
    "InputSnapshot",
    "KeyBurstAggregator",
    "LogEvent",
    "MarkdownLogger",
    "MonthlyCompressor",
    "SingleInstance",
    "WindowInfo",
    "WeeklyArchiver",
    "WorkLogConfig",
    "build_parser",
    "default_log_root",
    "format_event_line",
    "format_hotkey",
    "get_browser_url",
    "get_foreground_window",
    "get_idle_seconds",
    "load_config",
    "normalize_key_name",
    "read_clipboard",
    "session_event_type",
    "summarize_clipboard",
    "week_bounds",
]


if __name__ == "__main__":
    raise SystemExit(main())
