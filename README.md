# Work Activity Tracker v0.2

Windows 个人工作活动记录器。默认只写本地日志，不联网、不上传、不打包 exe。

## 项目结构

```text
tracker.py          主入口
config.json         运行配置
modules/            watcher、日志、归档、UIA、配置等模块
raw/                默认位于 %LOCALAPPDATA%\WorkLog\raw
archive/            默认位于 %LOCALAPPDATA%\WorkLog\archive
error.log           默认位于 %LOCALAPPDATA%\WorkLog\error.log
```

## 当前采集方式

- 前台窗口：优先使用 `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` 事件监听，主循环轮询兜底。
- 剪贴板：优先使用 `AddClipboardFormatListener` / `WM_CLIPBOARDUPDATE` 消息监听，主循环轮询兜底。
- 锁屏/解锁：WTS 会话事件。
- 空闲：`GetLastInputInfo`。
- 键盘：`pynput` 全局 Hook，聚合写入，不逐字记录中文。
- 输入框：UIA 读取非密码控件 Value；最近键盘输入触发 `[TEXT]`，无最近按键的值变化触发 `[AUTOFILL]`。

## 安装依赖

```powershell
pip install -r requirements.txt
```

## 试运行

```powershell
python tracker.py --once
```

后台静默运行时建议用 `pythonw.exe tracker.py`，再按方案文档配置任务计划程序。

## 配置

默认读取当前目录的 `config.json`：

```powershell
python tracker.py --config .\config.json
```

常用配置包括日志目录、AFK 阈值、剪贴板文本截断长度、排除窗口标题、键盘聚合间隔、UIA 超时和单实例互斥量名。

## 日志位置

默认写入：

```text
%LOCALAPPDATA%\WorkLog\raw\YYYY-MM-DD.md
```

也可以指定目录：

```powershell
python tracker.py --once --log-root .\WorkLog
```

## 周归档

```powershell
python tracker.py --archive-week
```

输出：

```text
%LOCALAPPDATA%\WorkLog\archive\YYYY-WXX-summary.md
```

后台运行时会在每周日 3 点生成周归档，并在每月 1 日 4 点把上月 raw 日志压缩到 `archive\YYYY-MM.zip`；原始 `.md` 不删除。

## 测试

```powershell
python -m unittest test_tracker.py
```
