from __future__ import annotations

import threading
import traceback
from datetime import datetime
from pathlib import Path

from .config import WorkLogConfig


EVENT_FIELD_WIDTH = 14
CONTINUATION_INDENT = " " * 21


def format_event_line(timestamp: datetime, event_type: str, content: str) -> str:
    label = f"[{event_type}]".ljust(EVENT_FIELD_WIDTH)
    first, *rest = content.splitlines()
    line = f"{timestamp:%Y-%m-%d %H:%M:%S}  {label}{first}"
    if not rest:
        return line
    return "\n".join([line, *[f"{CONTINUATION_INDENT}{part}" for part in rest]])


class MarkdownLogger:
    def __init__(self, config: WorkLogConfig) -> None:
        self.config = config
        self._lock = threading.Lock()

    def write_event(self, event_type: str, content: str = "", now: datetime | None = None) -> Path:
        timestamp = now or datetime.now()
        path = self._active_log_path(self.config.daily_log_path(timestamp.date()))
        path.parent.mkdir(parents=True, exist_ok=True)
        line = format_event_line(timestamp, event_type, content)
        with self._lock:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
        return path

    def _active_log_path(self, base_path: Path) -> Path:
        if not base_path.exists() or base_path.stat().st_size < self.config.max_log_file_bytes:
            return base_path
        index = 2
        while True:
            candidate = base_path.with_name(f"{base_path.stem}-{index}{base_path.suffix}")
            if not candidate.exists() or candidate.stat().st_size < self.config.max_log_file_bytes:
                return candidate
            index += 1


class ErrorLogger:
    def __init__(self, log_root: Path, max_bytes: int = 5 * 1024 * 1024) -> None:
        self.log_root = Path(log_root)
        self.max_bytes = max_bytes
        self.path = self.log_root / "error.log"
        self._lock = threading.Lock()

    def write(self, message: str) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._rotate_if_needed()
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n")
                handle.flush()
        return self.path

    def write_exception(self, exc: BaseException) -> Path:
        return self.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())

    def _rotate_if_needed(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return
        backup = self.path.with_name("error.log.1")
        if backup.exists():
            backup.unlink()
        self.path.replace(backup)
