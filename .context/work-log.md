# 工作日志

> 每完成一个明确步骤就追加一条记录，不写流水账。

## 2026-05-12 23:00 CST｜Initialize project context from planning documents
- 目标：Initialize project context from planning documents
- 动作：Read three planning docs; initialized .context; filled plan, status, tasks, decisions, and risks.
- 结果：Project context now reflects v0.1 tracker scope and constraints.
- 验证：Read generated context files and replaced placeholder sections.
- 下一步：Write failing tests for tracker.py pure logic.

## 2026-05-12 23:35 CST｜Implement Work Activity Tracker v0.1
- 目标：Implement Work Activity Tracker v0.1
- 动作：Added tracker.py, tests, README, requirements, gitignore; installed dependencies; fixed CLI help bug and sandbox temp test issue.
- 结果：v0.1 can format logs, aggregate key bursts, summarize clipboard, archive weekly logs, and run one Windows polling tick.
- 验证：python -m unittest test_tracker.py passed 8 tests; py_compile passed; python tracker.py --help passed; --archive-week passed; --once wrote a daily log after dependencies were installed.
- 下一步：Run long-lived pythonw/task-scheduler self-use test and add WTS lock/unlock listener.

## 2026-05-12 23:42 CST｜Add lock and unlock session event support
- 目标：Add lock and unlock session event support
- 动作：Added WTS session listener thread and regression test for session event mapping.
- 结果：Long-running tracker can write LOCK and UNLOCK events when Windows sends session change notifications.
- 验证：python -m unittest test_tracker.py passed 9 tests; py_compile passed; CLI help passed; archive-week passed; --once passed.
- 下一步：Run pythonw/task-scheduler self-use test and iterate autofill/text capture.

## 2026-05-13 14:55 CST｜Incorporate file structure and module design document
- 目标：Incorporate file structure and module design document
- 动作：Read 文件结构与模块设计.md and compared it against current single-file v0.1 implementation.
- 结果：Updated project context: missing structure doc is no longer a blocker; v0.2 route is module split plus event-listener upgrades.
- 验证：Read current status and task breakdown after applying updates.
- 下一步：If approved, refactor tracker.py into the documented module structure with tests kept green.

## 2026-05-13 15:10 CST｜Implement v0.2 module split and runtime config
- 目标：Implement v0.2 module split and runtime config
- 动作：Added failing tests for config loading, error log rotation, module imports; split tracker logic into modules; added config.json; narrowed tracker.py to main control flow; updated README and context.
- 结果：Project now matches the documented module structure for v0.2-1 while preserving existing behavior.
- 验证：Intermediate unittest run passed 12 tests after implementation.
- 下一步：Run full verification commands and clean temporary outputs.

## 2026-05-13 15:15 CST｜Complete v0.2 verification
- 目标：Complete v0.2 verification
- 动作：Ran unittest, compileall, CLI help, archive-week, once mode, context validation; cleaned temporary outputs.
- 结果：v0.2 module split and config/error logging changes are verified.
- 验证：unittest passed 12 tests; compileall exit 0; help exit 0; archive-week exit 0; once exit 0; context is valid.
- 下一步：Implement event-driven foreground window and clipboard watchers, then long-run pythonw/task-scheduler validation.

## 2026-05-13 15:35 CST｜Implement event-driven foreground and clipboard watchers
- 目标：Implement event-driven foreground and clipboard watchers
- 动作：Added ForegroundWindowWatcher and ClipboardChangeWatcher; integrated them into ActivityTracker; kept polling fallback; added tests for dedupe, window change callbacks, API availability, and ActivityTracker callback logging; switched missing pywin32 API calls to ctypes.user32.
- 结果：Foreground window and clipboard event watcher code is implemented and verified at unit/API level.
- 验证：unittest passed 17 tests; compileall passed; CLI help passed; archive-week passed; once mode passed.
- 下一步：Run long-lived pythonw/task-scheduler validation and implement TEXT/AUTOFILL UIA capture.

## 2026-05-13 15:55 CST｜Implement TEXT and AUTOFILL UIA capture
- 目标：Implement TEXT and AUTOFILL UIA capture
- 动作：Added InputSnapshot, focused input snapshot reading, input value-only helper, ActivityTracker TEXT/AUTOFILL/SKIP_PWD handling, and regression tests.
- 结果：Tracker can classify non-password input value changes as TEXT or AUTOFILL and skips password values.
- 验证：unittest passed 21 tests; compileall passed; CLI help passed; archive-week passed; once mode passed.
- 下一步：Run long-lived pythonw/task-scheduler validation against real apps and web forms.

## 2026-05-13 16:10 CST｜Finish documented archive and log retention items
- 目标：Finish documented archive and log retention items
- 动作：Added tests and implementation for daily log splitting, configured clipboard head-tail truncation, weekly archive scheduler, and monthly raw log zip compression while retaining raw markdown files.
- 结果：Code scope now matches the explicit remaining archive/logger items in 文件结构与模块设计.md.
- 验证：unittest passed 25 tests; compileall passed; CLI help passed; archive-week passed; once mode passed.
- 下一步：Run real background validation with pythonw/task scheduler; do not add undocumented features.

## 2026-05-14 20:20 CST｜Diagnose and configure autostart
- 目标：Diagnose and configure autostart
- 动作：Checked scheduled task, pythonw path, running process, raw log, and error log; found no WorkLogTracker task and no running python process; created logon scheduled task; started it; fixed URL values being misclassified as AUTOFILL; restarted task.
- 结果：WorkLogTracker scheduled task is Running under pythonw and raw log shows a fresh RESUME after restart.
- 验证：Task info LastTaskResult 267009 running; pythonw process present; raw log contains 2026-05-14 20:18:40 RESUME; unittest passed 26 tests; compileall passed.
- 下一步：User should reboot or log out/in once and verify a new RESUME appears after login.
