---
name: patch-review
description: 当用户要求审查/review/检查当前改动是否有问题，或希望对已生成的修改做自检时使用。这是一个只读 Skill，不修改任何文件。
allowed_tools: [git_diff, git_status, read_file, search_code, list_files, current_repo_info]
priority_tools: [git_diff, read_file]
---

# 修改自审 Skill (Patch Review)

你正在做**代码审查**，不是修复。你的输出是一份结构化的 review 报告，不是新的代码改动。

## 严格约束

- **只读**。不允许调用 `write_file`、`replace_in_file`、`patch_file`、`bash_terminal`、`git_add`、`git_commit`、`git_push`、`run_pytest`。
- 即使发现明显问题，也只是**写在报告里**，不要动手修。
- 如果用户后续说"那就改了吧"，那是另一个任务。

## 工作流程

### 第 1 步：拿到 diff
- 先 `git_diff` 看当前未提交改动。如果 diff 为空，再 `git_diff staged=true` 看暂存区。
- 都为空就直接输出报告说"未检测到改动"，然后 `TASK_SUCCESS`。

### 第 2 步：理解上下文
对 diff 涉及的每个文件，至少：
- `read_file` 看修改前后的完整上下文（光看 diff 不够，看不到周围的调用、import、try/except 边界）。
- 必要时 `search_code` 找该函数/符号在仓库别处的调用方，判断改动是否破坏调用约定。

### 第 3 步：按 checklist 审查

逐项检查并形成结论：

1. **Scope 漂移**：diff 里是否混入了与 Issue 无关的改动（无关的格式化、无关文件的 import 调整、注释清理等）？
2. **边界与异常**：新增/修改的逻辑是否漏掉 None / 空集合 / 异常输入 / 边界值？原有 try/except 是否被无意吞掉？
3. **安全风险**：是否引入了 SQL 拼接、命令注入、路径穿越、未校验的用户输入、明文凭证？
4. **回归风险**：被改函数的其他调用方是否会因为签名或行为变化而出问题？
5. **测试覆盖**：这次改动是否需要新增测试？现有测试是否还能覆盖改动后的行为？（只说"应该加"，不动手加）
6. **可疑信号**：被注释掉的代码、`# TODO`、`pass # type: ignore`、突然引入的全局变量、被静默 swallow 的异常。

### 第 4 步：输出报告

最后一条消息输出严格如下格式的报告，然后 `TASK_SUCCESS`：

```
## Patch Review 报告

涉及文件: file_a.py, file_b.py

### 🔴 Critical（必须修）
- [file_a.py:42] 描述问题 + 为什么是 critical

### 🟡 Warning（建议修）
- [file_b.py:10] 描述问题

### 🔵 Note（可以保留但值得知道）
- [file_a.py:7] 描述观察

### 总体判断
通过 / 需要修改 / 拒绝合并 — 一句话理由
```

任何一类都可以为空（写"无"）。**不许编造行号**——只写你确实通过 `read_file` 看到的行号。

## 禁忌

- 不要顺手修复你发现的问题——这是 review 不是 fix。
- 不要在没读完上下文的情况下下结论。"这里好像有问题"不算 finding，必须能说出**为什么是问题**。
- 不要把代码风格偏好（缩进、命名口味）当成 finding，除非违反了仓库现有约定。

## 终止条件

- `TASK_SUCCESS`：报告已输出。
- `TASK_FAILED`：仓库没有改动可审，或无法读到 diff（沙箱问题）。
