from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from .models import LogEvent


class KeyBurstAggregator:
    def __init__(self) -> None:
        self.process: str | None = None
        self.started_at: datetime | None = None
        self.last_at: datetime | None = None
        self.key_count = 0
        self.hotkeys: Counter[str] = Counter()

    def record_key(self, process: str, at: datetime | None = None) -> None:
        self._record(process, at or datetime.now(), hotkey=None)

    def record_hotkey(self, process: str, hotkey: str, at: datetime | None = None) -> None:
        self._record(process, at or datetime.now(), hotkey=hotkey)

    def _record(self, process: str, at: datetime, hotkey: str | None) -> None:
        if self.process and process != self.process:
            self.reset()
        if self.started_at is None:
            self.started_at = at
            self.process = process
        self.last_at = at
        self.key_count += 1
        if hotkey:
            self.hotkeys[hotkey] += 1

    def should_flush(self, now: datetime | None = None, burst_seconds: int = 30) -> bool:
        if not self.started_at or self.key_count == 0:
            return False
        return (now or datetime.now()) - self.started_at >= timedelta(seconds=burst_seconds)

    def flush(self, process: str | None = None, now: datetime | None = None) -> LogEvent:
        if not self.started_at or self.key_count == 0:
            raise ValueError("No key burst to flush")
        timestamp = now or self.last_at or datetime.now()
        duration = max(0, int((timestamp - self.started_at).total_seconds()))
        proc = process or self.process or "unknown"
        parts = [f"{proc} | {self.key_count} keys / {duration}s"]
        parts.extend(f"{name}x{count}" for name, count in sorted(self.hotkeys.items()))
        event = LogEvent("KEY_BURST", " | ".join(parts), timestamp)
        self.reset()
        return event

    def reset(self) -> None:
        self.process = None
        self.started_at = None
        self.last_at = None
        self.key_count = 0
        self.hotkeys.clear()


def normalize_key_name(key: object) -> str:
    char = getattr(key, "char", None)
    if char:
        return str(char).upper()
    name = getattr(key, "name", None) or str(key).replace("Key.", "")
    mapping = {
        "ctrl": "Ctrl",
        "ctrl_l": "Ctrl",
        "ctrl_r": "Ctrl",
        "shift": "Shift",
        "shift_l": "Shift",
        "shift_r": "Shift",
        "alt": "Alt",
        "alt_l": "Alt",
        "alt_r": "Alt",
        "cmd": "Win",
        "cmd_l": "Win",
        "cmd_r": "Win",
        "enter": "Enter",
        "tab": "Tab",
        "space": "Space",
    }
    return mapping.get(str(name).lower(), str(name))


def format_hotkey(modifiers: set[str], key_name: str) -> str | None:
    if not modifiers:
        return None
    ordered = [name for name in ("Ctrl", "Alt", "Shift", "Win") if name in modifiers]
    if key_name in ordered:
        return None
    return "+".join([*ordered, key_name])
