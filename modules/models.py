from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class LogEvent:
    event_type: str
    content: str
    timestamp: datetime


@dataclass(frozen=True)
class WindowInfo:
    process: str
    title: str
    hwnd: int = 0

    def as_log_content(self) -> str:
        return f'{self.process} | "{self.title}"'


@dataclass(frozen=True)
class ClipboardSnapshot:
    kind: str
    text: str | None = None
    files: list[Path] = field(default_factory=list)

    def signature(self) -> tuple[str, str]:
        if self.kind == "text":
            return self.kind, self.text or ""
        if self.kind == "files":
            return self.kind, "|".join(str(path) for path in self.files)
        return self.kind, ""


class DependencyError(RuntimeError):
    pass
