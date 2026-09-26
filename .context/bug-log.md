# Bug / 工程异常记录

> 所有会影响推进、质量、节奏或判断的异常都要记录，包括代码、环境、依赖、测试、打包和设计误判。

## Tests used system temp outside sandbox
- 现象：unittest raised PermissionError when TemporaryDirectory used AppData Local Temp
- 触发条件：Running python -m unittest test_tracker.py in workspace-write sandbox
- 影响：Tests could not reach tracker behavior assertions
- 根因：tempfile default directory is outside writable workspace
- 解决方案：Move test temporary directories under the project root
- 预防措施：Use workspace-scoped temporary directories for file-writing tests
- 状态：Resolved

## Argparse help crashed on percent signs
- 现象：python tracker.py --help raised ValueError unsupported format character O
- 触发条件：Help text contained %LOCALAPPDATA% in an argparse help string
- 影响：CLI help was unusable
- 根因：argparse expands percent formatting in help text
- 解决方案：Add regression test and escape percent signs as %%LOCALAPPDATA%%
- 预防措施：Run CLI help in verification for future command-line changes
- 状态：Resolved

## pywin32 missing event listener API wrappers
- 现象：win32gui did not expose SetWinEventHook, AddClipboardFormatListener, or RemoveClipboardFormatListener
- 触发条件：Checking event watcher Windows API availability before final verification
- 影响：Event-driven foreground and clipboard watchers would have written errors and fallen back to polling
- 根因：These user32 APIs are available on Windows but not wrapped by the installed pywin32 win32gui module
- 解决方案：Use ctypes.windll.user32 for SetWinEventHook, UnhookWinEvent, AddClipboardFormatListener, and RemoveClipboardFormatListener
- 预防措施：Keep an API availability regression test for the watcher modules
- 状态：Resolved

## UIA input capture could treat control names as values
- 现象：Focused input snapshot used read_uia_value, which falls back to Name when Value is unavailable
- 触发条件：Reviewing TEXT/AUTOFILL capture before completion
- 影响：Buttons or labels could be logged as TEXT/AUTOFILL, creating noisy or misleading logs
- 根因：URL reading and input value reading shared one helper despite different semantics
- 解决方案：Added read_input_value for real Value/ValuePattern only and updated focused input snapshots to use it
- 预防措施：Added regression test that name-only controls are ignored for input values
- 状态：Resolved
