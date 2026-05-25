---
name: test-failure-fix
description: 当 Issue 描述含有测试失败、pytest 报错、assertion error、CI 标红等情形时使用。重点是"先复现、看测试、再判断是测试错还是源码错"。
allowed_tools: [run_pytest, read_file, search_code, list_files, replace_in_file, patch_file, write_file, git_diff, git_status, current_repo_info]
priority_tools: [run_pytest, read_file]
---

# 测试失败修复 Skill

你正在处理一个"测试失败"类型的 Issue。这类任务有一个普通 bug 修复没有的关键问题：**到底是测试代码错了，还是源代码错了？** 你必须先回答这个问题再动手修。

## 工作流程

### 第 1 步：复现失败（必做）
- 优先调用 `run_pytest`，参数尽量精确到失败的测试文件或测试函数（例如 `tests/test_foo.py::test_bar -x -vv`）。
- 如果 Issue 没说清失败的测试名，先 `list_files path=tests` 找候选，再 `run_pytest` 跑完整测试套件定位失败项。
- 没看到失败输出之前，**不要**开始读源码、不要开始改文件。

### 第 2 步：读测试代码（在读源码之前）
- 用 `read_file` 把失败的测试函数完整读出来，理解它在断言什么、用了哪些 fixture、mock 了什么。
- 关注：测试断言的预期值、传入的入参、fixture 构造的对象状态。

### 第 3 步：判断方向
明确回答下面这个问题再继续：

**测试代码错了，还是被测代码错了？**

- 如果**测试代码错**了（断言写错、fixture 过时、mock 不匹配新签名）：修测试。
- 如果**被测代码错**了（实现 bug 导致断言失败）：修源码。
- 如果**两者都要改**（API 改了，测试也要跟着改）：明确说明并分别修。

不允许跳过这一步直接开始改。如果证据不足，回去读更多文件。

### 第 4 步：实施修改
- 改源码时，先 `read_file` 拿到被测函数当前实现，再用 `replace_in_file` 做精确替换。
- 改完一处就回到第 5 步重跑，不要一口气改多处。

### 第 5 步：重跑测试（必做）
- 每次修改后立即 `run_pytest`，参数与第 1 步一致。
- 如果原失败用例通过了，再跑一次**整个测试目录**确认没引入回归。
- 跑通整套测试前不要输出 `TASK_SUCCESS`。

## 禁忌

- 不要为了让测试通过而注释掉断言、跳过测试、改宽松断言条件——除非你能说明为什么原断言本来就错。
- 不要修改与失败测试无关的其他测试文件。
- 不要直接动 `conftest.py` 全局 fixture 除非你确定根因在那里。
- 没看到 `passed` 信号之前，不要相信"我觉得应该好了"。

## 终止条件

- `TASK_SUCCESS`：失败用例通过，且整个测试套件无新增失败。
- `TASK_FAILED`：经过排查确认是环境问题（如依赖缺失、Python 版本不兼容），无法在当前沙箱解决。
