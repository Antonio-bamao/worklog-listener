import shutil
import unittest
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from importlib import import_module
from pathlib import Path

from tracker import (
    ArchiveScheduler,
    ActivityTracker,
    ClipboardSnapshot,
    ClipboardChangeWatcher,
    ErrorLogger,
    ForegroundWindowWatcher,
    InputSnapshot,
    KeyBurstAggregator,
    MarkdownLogger,
    MonthlyCompressor,
    WorkLogConfig,
    WeeklyArchiver,
    build_parser,
    format_event_line,
    session_event_type,
    summarize_clipboard,
)
from modules.models import WindowInfo


TEMP_DIR = Path(__file__).resolve().parent / "test-run"
TEMP_DIR.mkdir(exist_ok=True)


@contextmanager
def workspace_temp_dir():
    path = TEMP_DIR / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)


class WorkLogConfigTests(unittest.TestCase):
    def test_daily_log_path_uses_raw_date_markdown_file(self):
        with workspace_temp_dir() as tmp:
            config = WorkLogConfig(log_root=tmp)

            self.assertEqual(
                config.daily_log_path(date(2026, 5, 12)),
                Path(tmp) / "raw" / "2026-05-12.md",
            )

    def test_config_json_overrides_documented_runtime_settings(self):
        with workspace_temp_dir() as tmp:
            config_path = tmp / "config.json"
            config_path.write_text(
                """
{
  "log_dir": "%ROOT%\\\\logs",
  "afk_threshold_sec": 120,
  "text_truncate_length": 80,
  "key_burst_interval_sec": 10,
  "single_instance_mutex_name": "Global\\\\CustomMutex"
}
""".replace("%ROOT%", str(tmp).replace("\\", "\\\\")),
                encoding="utf-8",
            )

            config = WorkLogConfig.from_json(config_path)

            self.assertEqual(config.log_root, tmp / "logs")
            self.assertEqual(config.idle_seconds, 120)
            self.assertEqual(config.max_clip_text_length, 80)
            self.assertEqual(config.key_burst_seconds, 10)
            self.assertEqual(config.single_instance_mutex_name, "Global\\CustomMutex")


class EventFormattingTests(unittest.TestCase):
    def test_format_event_line_pads_event_type_like_documented_logs(self):
        line = format_event_line(
            datetime(2026, 5, 12, 9, 15, 3),
            "APP",
            'chrome.exe | "Meta Ads Manager - Campaigns"',
        )

        self.assertEqual(
            line,
            '2026-05-12 09:15:03  [APP]         chrome.exe | "Meta Ads Manager - Campaigns"',
        )

    def test_markdown_logger_indents_multiline_event_content(self):
        with workspace_temp_dir() as tmp:
            logger = MarkdownLogger(WorkLogConfig(log_root=tmp))

            logger.write_event(
                "CLIP_COPY",
                'from: WeChat.exe\ncontent: "budget 800"',
                now=datetime(2026, 5, 12, 9, 16, 25),
            )

            text = (Path(tmp) / "raw" / "2026-05-12.md").read_text(encoding="utf-8")
            self.assertEqual(
                text,
                '2026-05-12 09:16:25  [CLIP_COPY]   from: WeChat.exe\n'
                '                     content: "budget 800"\n',
            )

    def test_error_logger_writes_silent_error_log_and_rotates(self):
        with workspace_temp_dir() as tmp:
            logger = ErrorLogger(tmp, max_bytes=12)

            logger.write("first")
            logger.write("second")

            self.assertTrue((tmp / "error.log").exists())
            self.assertTrue((tmp / "error.log.1").exists())
            self.assertIn("second", (tmp / "error.log").read_text(encoding="utf-8"))

    def test_markdown_logger_splits_large_daily_log_file(self):
        with workspace_temp_dir() as tmp:
            config = WorkLogConfig(log_root=tmp, max_log_file_bytes=10)
            log_path = tmp / "raw" / "2026-05-13.md"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("x" * 20, encoding="utf-8")
            logger = MarkdownLogger(config)

            logger.write_event("APP", "chrome.exe", now=datetime(2026, 5, 13, 15, 50, 0))

            self.assertTrue((tmp / "raw" / "2026-05-13-2.md").exists())


class ClipboardTests(unittest.TestCase):
    def test_summarize_clipboard_truncates_long_text_without_losing_type(self):
        snapshot = ClipboardSnapshot(kind="text", text="a" * 140)

        summary = summarize_clipboard(snapshot, max_text_length=20)

        self.assertEqual(summary, 'content: "aaaaaaaaaaaaaaaaaaaa..."')

    def test_summarize_clipboard_uses_head_tail_total_length_when_configured(self):
        snapshot = ClipboardSnapshot(kind="text", text="abcdefghijklmnopqrstuvwxyz")

        summary = summarize_clipboard(snapshot, max_text_length=10, keep_head=5, keep_tail=3)

        self.assertEqual(summary, 'content: "abcde...xyz (26 chars)"')

    def test_summarize_clipboard_records_file_count_and_first_paths(self):
        snapshot = ClipboardSnapshot(
            kind="files",
            files=[Path("C:/tmp/a.txt"), Path("C:/tmp/b.txt"), Path("C:/tmp/c.txt")],
        )

        summary = summarize_clipboard(snapshot)

        self.assertEqual(summary, "files: 3 | C:/tmp/a.txt; C:/tmp/b.txt")

    def test_clipboard_watcher_deduplicates_same_signature_within_one_second(self):
        callbacks = []
        snapshot = ClipboardSnapshot(kind="text", text="same")
        watcher = ClipboardChangeWatcher(
            on_clipboard=callbacks.append,
            read_clipboard_func=lambda: snapshot,
            dedupe_seconds=1.0,
        )

        first = watcher.handle_clipboard_update(now=datetime(2026, 5, 13, 15, 30, 0))
        second = watcher.handle_clipboard_update(now=datetime(2026, 5, 13, 15, 30, 0, 500000))

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(callbacks, [snapshot])


class KeyBurstTests(unittest.TestCase):
    def test_key_burst_aggregates_keys_duration_and_hotkeys(self):
        base = datetime(2026, 5, 12, 9, 15, 0)
        burst = KeyBurstAggregator()

        burst.record_key("chrome.exe", base)
        burst.record_key("chrome.exe", base + timedelta(seconds=5))
        burst.record_hotkey("chrome.exe", "Ctrl+C", base + timedelta(seconds=10))

        event = burst.flush("chrome.exe", base + timedelta(seconds=28))

        self.assertEqual(event.event_type, "KEY_BURST")
        self.assertEqual(event.content, "chrome.exe | 3 keys / 28s | Ctrl+Cx1")


class WeeklyArchiveTests(unittest.TestCase):
    def test_weekly_archiver_builds_summary_from_raw_logs(self):
        with workspace_temp_dir() as root:
            raw = root / "raw"
            raw.mkdir(parents=True)
            (raw / "2026-05-12.md").write_text(
                "\n".join(
                    [
                        '2026-05-12 09:00:00  [APP]         chrome.exe | "Meta Ads Manager"',
                        "2026-05-12 09:00:01  [URL]         https://business.facebook.com/adsmanager",
                        '2026-05-12 10:00:00  [APP]         Code.exe | "tracker.py"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            path = WeeklyArchiver(WorkLogConfig(log_root=root)).archive_week(date(2026, 5, 12))

            text = path.read_text(encoding="utf-8")
            self.assertIn("# Week 20 (2026-05-11 ~ 2026-05-17) Summary", text)
            self.assertIn("1. chrome.exe", text)
            self.assertIn("1. business.facebook.com", text)

    def test_monthly_compressor_zips_month_without_deleting_raw_logs(self):
        with workspace_temp_dir() as root:
            raw = root / "raw"
            raw.mkdir(parents=True)
            may_log = raw / "2026-05-12.md"
            june_log = raw / "2026-06-01.md"
            may_log.write_text("may", encoding="utf-8")
            june_log.write_text("june", encoding="utf-8")

            zip_path = MonthlyCompressor(WorkLogConfig(log_root=root)).compress_month(2026, 5)

            self.assertTrue(zip_path.exists())
            self.assertTrue(may_log.exists())
            self.assertTrue(june_log.exists())

    def test_archive_scheduler_runs_weekly_and_monthly_jobs_once_per_slot(self):
        with workspace_temp_dir() as root:
            weekly_calls = []
            monthly_calls = []
            scheduler = ArchiveScheduler(
                weekly_job=lambda day: weekly_calls.append(day),
                monthly_job=lambda year, month: monthly_calls.append((year, month)),
            )

            self.assertTrue(scheduler.tick(datetime(2026, 5, 17, 3, 0, 0)))
            self.assertFalse(scheduler.tick(datetime(2026, 5, 17, 3, 0, 30)))
            self.assertTrue(scheduler.tick(datetime(2026, 6, 1, 4, 0, 0)))

            self.assertEqual(len(weekly_calls), 1)
            self.assertEqual(monthly_calls, [(2026, 5)])


class CliTests(unittest.TestCase):
    def test_help_text_formats_without_percent_placeholder_crash(self):
        help_text = build_parser().format_help()

        self.assertIn("%LOCALAPPDATA%\\WorkLog", help_text)


class SessionEventTests(unittest.TestCase):
    def test_session_event_type_maps_lock_and_unlock(self):
        self.assertEqual(session_event_type(0x7), "LOCK")
        self.assertEqual(session_event_type(0x8), "UNLOCK")
        self.assertIsNone(session_event_type(0x5))


class WindowWatcherTests(unittest.TestCase):
    def test_foreground_watcher_calls_back_only_when_window_changes(self):
        callbacks = []
        first_window = import_module("modules.models").WindowInfo("chrome.exe", "Ads", hwnd=100)
        second_window = import_module("modules.models").WindowInfo("Code.exe", "tracker.py", hwnd=200)
        windows = iter([first_window, first_window, second_window])
        watcher = ForegroundWindowWatcher(on_window=callbacks.append, get_window_func=lambda: next(windows))

        self.assertTrue(watcher.handle_foreground_event())
        self.assertFalse(watcher.handle_foreground_event())
        self.assertTrue(watcher.handle_foreground_event())
        self.assertEqual(callbacks, [first_window, second_window])


class WindowsApiAvailabilityTests(unittest.TestCase):
    def test_event_watchers_use_user32_apis_available_on_this_machine(self):
        clipboard_module = import_module("modules.clipboard_watcher")
        window_module = import_module("modules.window_watcher")

        self.assertTrue(window_module.has_foreground_event_api())
        self.assertTrue(clipboard_module.has_clipboard_listener_api())


class UiaHelperTests(unittest.TestCase):
    def test_input_value_reader_ignores_name_only_controls(self):
        uia_module = import_module("modules.uia_helper")

        class NameOnlyControl:
            Name = "Submit"

            def GetValuePattern(self):
                raise RuntimeError("no value")

        self.assertIsNone(uia_module.read_input_value(NameOnlyControl()))


class ActivityTrackerCallbackTests(unittest.TestCase):
    def test_window_callback_writes_app_event_once(self):
        with workspace_temp_dir() as tmp:
            tracker = ActivityTracker(WorkLogConfig(log_root=tmp))
            window = WindowInfo("chrome.exe", "Meta Ads", hwnd=101)

            self.assertTrue(tracker._handle_window_change(window, now=datetime(2026, 5, 13, 15, 40, 0)))
            self.assertFalse(tracker._handle_window_change(window, now=datetime(2026, 5, 13, 15, 40, 1)))

            text = (tmp / "raw" / "2026-05-13.md").read_text(encoding="utf-8")
            self.assertEqual(text.count("[APP]"), 1)

    def test_clipboard_callback_writes_copy_event_once(self):
        with workspace_temp_dir() as tmp:
            tracker = ActivityTracker(WorkLogConfig(log_root=tmp))
            tracker.last_window = WindowInfo("WeChat.exe", "客户", hwnd=101)
            snapshot = ClipboardSnapshot("text", text="budget 800")

            self.assertTrue(tracker._handle_clipboard_change(snapshot, now=datetime(2026, 5, 13, 15, 41, 0)))
            self.assertFalse(tracker._handle_clipboard_change(snapshot, now=datetime(2026, 5, 13, 15, 41, 1)))

            text = (tmp / "raw" / "2026-05-13.md").read_text(encoding="utf-8")
            self.assertEqual(text.count("[CLIP_COPY]"), 1)
            self.assertIn("from: WeChat.exe", text)

    def test_input_snapshot_after_recent_key_writes_text_event(self):
        with workspace_temp_dir() as tmp:
            tracker = ActivityTracker(WorkLogConfig(log_root=tmp))
            tracker.last_window = WindowInfo("chrome.exe", "Ads", hwnd=101)
            tracker.last_key_at = datetime(2026, 5, 13, 15, 42, 0)
            snapshot = InputSnapshot(field="campaign_name", value="Summer Sale", is_password=False)

            self.assertTrue(tracker._handle_input_snapshot(snapshot, now=datetime(2026, 5, 13, 15, 42, 1)))

            text = (tmp / "raw" / "2026-05-13.md").read_text(encoding="utf-8")
            self.assertIn("[TEXT]", text)
            self.assertIn('field=campaign_name | "Summer Sale"', text)

    def test_input_snapshot_without_recent_key_writes_autofill_event(self):
        with workspace_temp_dir() as tmp:
            tracker = ActivityTracker(WorkLogConfig(log_root=tmp))
            tracker.last_window = WindowInfo("chrome.exe", "Login", hwnd=101)
            snapshot = InputSnapshot(field="email", value="myshop@gmail.com", is_password=False)

            self.assertTrue(tracker._handle_input_snapshot(snapshot, now=datetime(2026, 5, 13, 15, 43, 0)))

            text = (tmp / "raw" / "2026-05-13.md").read_text(encoding="utf-8")
            self.assertIn("[AUTOFILL]", text)
            self.assertIn('field=email | "myshop@gmail.com"', text)

    def test_password_input_snapshot_writes_skip_without_value(self):
        with workspace_temp_dir() as tmp:
            tracker = ActivityTracker(WorkLogConfig(log_root=tmp))
            tracker.last_window = WindowInfo("chrome.exe", "Login", hwnd=101)
            snapshot = InputSnapshot(field="password", value="secret", is_password=True)

            self.assertTrue(tracker._handle_input_snapshot(snapshot, now=datetime(2026, 5, 13, 15, 44, 0)))

            text = (tmp / "raw" / "2026-05-13.md").read_text(encoding="utf-8")
            self.assertIn("[SKIP_PWD]", text)
            self.assertNotIn("secret", text)

    def test_input_snapshot_ignores_probable_browser_url_values(self):
        with workspace_temp_dir() as tmp:
            tracker = ActivityTracker(WorkLogConfig(log_root=tmp))
            tracker.last_window = WindowInfo("chrome.exe", "Chrome", hwnd=101)
            snapshot = InputSnapshot(field="address", value="https://example.com/form", is_password=False)

            self.assertFalse(tracker._handle_input_snapshot(snapshot, now=datetime(2026, 5, 14, 20, 20, 0)))
            self.assertFalse((tmp / "raw" / "2026-05-14.md").exists())


class ModuleStructureTests(unittest.TestCase):
    def test_documented_modules_are_importable(self):
        for module_name in [
            "modules.logger",
            "modules.archiver",
            "modules.uia_helper",
            "modules.idle_detector",
            "modules.window_watcher",
            "modules.clipboard_watcher",
            "modules.keyboard_watcher",
            "modules.session_watcher",
        ]:
            with self.subTest(module=module_name):
                import_module(module_name)


if __name__ == "__main__":
    unittest.main()
