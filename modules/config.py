from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def default_log_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "WorkLog"
    return Path.home() / "AppData" / "Local" / "WorkLog"


def expand_config_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


@dataclass(frozen=True)
class WorkLogConfig:
    log_root: Path | None = None
    idle_seconds: int = 300
    poll_interval: float = 1.0
    key_burst_seconds: int = 30
    max_clip_text_length: int = 200
    text_truncate_keep_head: int = 50
    text_truncate_keep_tail: int = 20
    exclude_window_titles: list[str] = field(default_factory=list)
    uia_query_timeout_ms: int = 200
    weekly_archive_cron: str = "0 3 * * 0"
    monthly_compress_cron: str = "0 4 1 * *"
    single_instance_mutex_name: str = "Global\\WorkLogTrackerMutex"
    error_log_max_bytes: int = 5 * 1024 * 1024
    max_log_file_bytes: int = 10 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.log_root is None:
            object.__setattr__(self, "log_root", default_log_root())
        else:
            object.__setattr__(self, "log_root", Path(self.log_root))

    @classmethod
    def from_json(cls, path: Path) -> WorkLogConfig:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> WorkLogConfig:
        kwargs: dict[str, Any] = {}
        if "log_dir" in data:
            kwargs["log_root"] = expand_config_path(str(data["log_dir"]))
        if "afk_threshold_sec" in data:
            kwargs["idle_seconds"] = int(data["afk_threshold_sec"])
        if "text_truncate_length" in data:
            kwargs["max_clip_text_length"] = int(data["text_truncate_length"])
        if "text_truncate_keep_head" in data:
            kwargs["text_truncate_keep_head"] = int(data["text_truncate_keep_head"])
        if "text_truncate_keep_tail" in data:
            kwargs["text_truncate_keep_tail"] = int(data["text_truncate_keep_tail"])
        if "exclude_window_titles" in data:
            kwargs["exclude_window_titles"] = list(data["exclude_window_titles"])
        if "key_burst_interval_sec" in data:
            kwargs["key_burst_seconds"] = int(data["key_burst_interval_sec"])
        if "uia_query_timeout_ms" in data:
            kwargs["uia_query_timeout_ms"] = int(data["uia_query_timeout_ms"])
        if "weekly_archive_cron" in data:
            kwargs["weekly_archive_cron"] = str(data["weekly_archive_cron"])
        if "monthly_compress_cron" in data:
            kwargs["monthly_compress_cron"] = str(data["monthly_compress_cron"])
        if "single_instance_mutex_name" in data:
            kwargs["single_instance_mutex_name"] = str(data["single_instance_mutex_name"])
        if "error_log_max_bytes" in data:
            kwargs["error_log_max_bytes"] = int(data["error_log_max_bytes"])
        if "max_log_file_bytes" in data:
            kwargs["max_log_file_bytes"] = int(data["max_log_file_bytes"])
        return cls(**kwargs)

    def daily_log_path(self, day: date | None = None) -> Path:
        day = day or date.today()
        return self.log_root / "raw" / f"{day:%Y-%m-%d}.md"

    def archive_path(self, day: date) -> Path:
        start, _ = week_bounds(day)
        return self.log_root / "archive" / f"{start:%Y}-W{start.isocalendar().week:02d}-summary.md"

    def error_log_path(self) -> Path:
        return self.log_root / "error.log"


def load_config(config_path: Path | None = None, log_root: Path | None = None, idle_seconds: int | None = None) -> WorkLogConfig:
    if config_path and config_path.exists():
        config = WorkLogConfig.from_json(config_path)
    else:
        config = WorkLogConfig()
    if log_root is not None or idle_seconds is not None:
        config = WorkLogConfig(
            log_root=log_root if log_root is not None else config.log_root,
            idle_seconds=idle_seconds if idle_seconds is not None else config.idle_seconds,
            poll_interval=config.poll_interval,
            key_burst_seconds=config.key_burst_seconds,
            max_clip_text_length=config.max_clip_text_length,
            text_truncate_keep_head=config.text_truncate_keep_head,
            text_truncate_keep_tail=config.text_truncate_keep_tail,
            exclude_window_titles=config.exclude_window_titles,
            uia_query_timeout_ms=config.uia_query_timeout_ms,
            weekly_archive_cron=config.weekly_archive_cron,
            monthly_compress_cron=config.monthly_compress_cron,
            single_instance_mutex_name=config.single_instance_mutex_name,
            error_log_max_bytes=config.error_log_max_bytes,
            max_log_file_bytes=config.max_log_file_bytes,
        )
    return config
