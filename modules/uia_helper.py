from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from .models import WindowInfo


BROWSER_EXES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
}


@dataclass(frozen=True)
class InputSnapshot:
    field: str
    value: str
    is_password: bool = False

    def signature(self) -> tuple[str, str, bool]:
        return self.field, self.value, self.is_password


def get_browser_url(window: WindowInfo) -> str | None:
    if window.process.lower() not in BROWSER_EXES or not window.hwnd:
        return None
    try:
        import uiautomation as auto
    except ImportError:
        return None

    try:
        root = auto.ControlFromHandle(window.hwnd)
        for control in iter_uia_descendants(root, max_nodes=250):
            value = read_uia_value(control)
            if value and is_probable_url(value):
                return value
    except Exception:
        return None
    return None


def iter_uia_descendants(root: object, max_nodes: int = 250) -> Iterable[object]:
    queue = [root]
    seen = 0
    while queue and seen < max_nodes:
        current = queue.pop(0)
        seen += 1
        yield current
        try:
            queue.extend(current.GetChildren())
        except Exception:
            continue


def read_uia_value(control: object) -> str | None:
    for attr in ("Value", "Name"):
        value = getattr(control, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    try:
        pattern = control.GetValuePattern()
        value = getattr(pattern, "Value", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        return None
    return None


def is_probable_url(value: str) -> bool:
    return value.startswith(("http://", "https://")) and "." in urlparse(value).netloc


def focused_control_is_password() -> bool:
    try:
        import uiautomation as auto
    except ImportError:
        return False
    try:
        control = auto.GetFocusedControl()
    except Exception:
        return False
    for attr in ("IsPassword", "CurrentIsPassword", "IsPasswordControl"):
        value = getattr(control, attr, None)
        if isinstance(value, bool):
            return value
        if callable(value):
            try:
                return bool(value())
            except Exception:
                continue
    return False


def get_focused_input_snapshot() -> InputSnapshot | None:
    try:
        import uiautomation as auto
    except ImportError:
        return None
    try:
        control = auto.GetFocusedControl()
    except Exception:
        return None
    if control is None:
        return None

    field = read_control_field_name(control)
    is_password = control_is_password(control)
    value = "" if is_password else (read_input_value(control) or "")
    if not value and not is_password:
        return None
    return InputSnapshot(field=field, value=value, is_password=is_password)


def read_control_field_name(control: object) -> str:
    for attr in ("AutomationId", "Name", "ClassName"):
        value = getattr(control, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Edit"


def read_input_value(control: object) -> str | None:
    value = getattr(control, "Value", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    try:
        pattern = control.GetValuePattern()
        value = getattr(pattern, "Value", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        return None
    return None


def control_is_password(control: object) -> bool:
    for attr in ("IsPassword", "CurrentIsPassword", "IsPasswordControl"):
        value = getattr(control, attr, None)
        if isinstance(value, bool):
            return value
        if callable(value):
            try:
                return bool(value())
            except Exception:
                continue
    return False
