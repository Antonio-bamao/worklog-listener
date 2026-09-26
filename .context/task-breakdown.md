# 任务拆解

## 当前优先级

1. 已完成：建立测试骨架，覆盖日志格式、路径、键盘聚合、剪贴板摘要、周归档、CLI 帮助。
2. 已完成：实现 `tracker.py` 的纯逻辑层：配置、日志写入、事件格式化、聚合器、归档器。
3. 已完成：实现 Windows 采集层基础能力：前台窗口、浏览器 URL、密码框检测、剪贴板、键盘 Hook、空闲检测、锁屏/解锁 WTS 监听、单实例锁。
4. 已完成：增加 `--once`、`--archive-week`、`--log-root` 等便于验证的入口。
5. 已完成：按“文件结构与模块设计”演进到 v0.2：
   - 已增加 `config.json` 配置加载。
   - 已拆分 `modules/logger.py`、`modules/archiver.py`、`modules/uia_helper.py`、`modules/idle_detector.py`。
   - 已拆分 `window_watcher.py`、`clipboard_watcher.py`、`keyboard_watcher.py`、`session_watcher.py`。
   - 已增加 `error.log` 静默异常记录和滚动。
   - 已完成：将窗口和剪贴板从轮询升级为 WinEvent / WM_CLIPBOARDUPDATE 消息监听，并保留轮询兜底。
   - 已完成：UIA 非密码输入框 Value 捕获，按最近键盘输入区分 `[TEXT]` / `[AUTOFILL]`，密码控件写 `[SKIP_PWD]` 且不记录 value。
   - 已完成：日志 10MB 分片、周归档定时触发、上月 raw zip 压缩且保留原始 `.md`。

## 依赖关系

- Python 标准库可支持日志、归档、路径和 CLI。
- 完整后台监听依赖 `pynput`、`pywin32`、`uiautomation`、`psutil`；缺失时应输出清晰错误或降级。
- 浏览器 URL、密码框和自动填充能力依赖 UI Automation 控件可读性，准确度按文档预期约 90%-95%。
