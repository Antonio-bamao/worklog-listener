from __future__ import annotations

import re
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from .config import WorkLogConfig, week_bounds


class WeeklyArchiver:
    def __init__(self, config: WorkLogConfig) -> None:
        self.config = config

    def archive_week(self, day: date | None = None) -> Path:
        day = day or date.today()
        start, end = week_bounds(day)
        app_counter: Counter[str] = Counter()
        url_counter: Counter[str] = Counter()

        for path in self._raw_paths(start, end):
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                event_type, content = parse_log_line(line)
                if event_type == "APP":
                    app = content.split("|", 1)[0].strip()
                    if app:
                        app_counter[app] += 1
                elif event_type == "URL":
                    host = urlparse(content.strip()).netloc
                    if host:
                        url_counter[host] += 1

        output = self.config.archive_path(day)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            build_weekly_summary(start, end, app_counter, url_counter),
            encoding="utf-8",
            newline="\n",
        )
        return output

    def _raw_paths(self, start: date, end: date) -> Iterable[Path]:
        current = start
        while current <= end:
            path = self.config.daily_log_path(current)
            if path.exists():
                yield path
            current += timedelta(days=1)


class MonthlyCompressor:
    def __init__(self, config: WorkLogConfig) -> None:
        self.config = config

    def compress_month(self, year: int, month: int) -> Path:
        output = self.config.log_root / "archive" / f"{year:04d}-{month:02d}.zip"
        output.parent.mkdir(parents=True, exist_ok=True)
        raw = self.config.log_root / "raw"
        pattern = f"{year:04d}-{month:02d}-*.md"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(raw.glob(pattern)):
                archive.write(path, arcname=path.name)
        return output


class ArchiveScheduler:
    def __init__(
        self,
        weekly_job: Callable[[date], object],
        monthly_job: Callable[[int, int], object],
    ) -> None:
        self.weekly_job = weekly_job
        self.monthly_job = monthly_job
        self._last_weekly_slot: tuple[int, int, int] | None = None
        self._last_monthly_slot: tuple[int, int] | None = None

    def tick(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        ran = False
        if now.weekday() == 6 and now.hour == 3:
            slot = (now.isocalendar().year, now.isocalendar().week, now.hour)
            if slot != self._last_weekly_slot:
                self.weekly_job(now.date() - timedelta(days=7))
                self._last_weekly_slot = slot
                ran = True
        if now.day == 1 and now.hour == 4:
            slot = (now.year, now.month)
            if slot != self._last_monthly_slot:
                previous_month = now.month - 1 or 12
                previous_year = now.year if now.month > 1 else now.year - 1
                self.monthly_job(previous_year, previous_month)
                self._last_monthly_slot = slot
                ran = True
        return ran


def parse_log_line(line: str) -> tuple[str | None, str]:
    match = re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+\[([A-Z_]+)\]\s+(.*)$", line)
    if not match:
        return None, line
    return match.group(1), match.group(2)


def build_weekly_summary(
    start: date,
    end: date,
    app_counter: Counter[str],
    url_counter: Counter[str],
) -> str:
    week_no = start.isocalendar().week
    lines = [
        f"# Week {week_no} ({start:%Y-%m-%d} ~ {end:%Y-%m-%d}) Summary",
        "",
        "## 总活跃时长",
        "待统计（v0.2 保留原始事件，后续按窗口时长和 AFK 扣除计算）",
        "",
        "## 应用 Top 10",
    ]
    lines.extend(numbered_items(app_counter))
    lines.extend(["", "## 访问 Top 10 网页"])
    lines.extend(numbered_items(url_counter))
    lines.extend(["", "## 异常空闲", "待统计"])
    return "\n".join(lines) + "\n"


def numbered_items(counter: Counter[str]) -> list[str]:
    if not counter:
        return ["无数据"]
    return [f"{index}. {name}    {count} events" for index, (name, count) in enumerate(counter.most_common(10), 1)]
