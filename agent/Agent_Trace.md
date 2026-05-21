统一 Agent Trace 标准

统一 Trace 标准用于打通 Agent 主链路、工具执行层、Web 展示和评测平台。该标准应兼容迭代二已有的 `AgentTrace`、`TraceEvent`、`ToolCallInfo`，在此基础上补充阶段、状态、耗时、错误、文件影响范围、用户确认等字段。

### 5.1 顶层结构

```json
{
  "schema_version": "agent-trace-v1",
  "trace_id": "trace-001",
  "task_id": "task-001",
  "conversation_id": "conv-001",
  "issue_id": "github-owner-repo-123",
  "agent_version": "agent-v3",
  "repo": {
    "repo_url": "https://github.com/example/repo.git",
    "branch": "main",
    "commit": "abc123",
    "sandbox_id": "sandbox-task-001"
  },
  "user_input": "请修复这个 issue",
  "final_response": "已完成修复并通过测试",
  "status": "success",
  "started_at": "2026-05-13T12:00:00Z",
  "ended_at": "2026-05-13T12:03:20Z",
  "total_latency_ms": 200000,
  "token_usage": {
    "prompt": 12000,
    "completion": 3000,
    "total": 15000
  },
  "events": []
}
```

顶层字段说明：

| 字段 | 说明 |
| --- | --- |
| `schema_version` | Trace 数据格式版本，便于后续升级兼容。 |
| `trace_id` | 单次 Agent 执行链路 ID。 |
| `task_id` | 平台中的任务 ID。 |
| `conversation_id` | 多轮对话 ID，同一 Issue 的连续追问共享该 ID。 |
| `issue_id` | 外部 Issue 标识，可为空。 |
| `agent_version` | Agent 版本，用于优化前后对比。 |
| `repo` | 仓库、分支、commit、sandbox 信息。 |
| `status` | `running`、`success`、`failed`、`cancelled`、`waiting_confirmation`。 |
| `events` | 按发生顺序排列的事件列表。 |

### 5.2 事件通用结构

所有阶段都统一为事件。事件必须有顺序号、类型、阶段、状态、时间和来源。

```json
{
  "event_id": "event-001",
  "seq": 1,
  "parent_event_id": null,
  "timestamp": "2026-05-13T12:00:01Z",
  "event_type": "planning",
  "phase": "planning",
  "actor": "agent",
  "status": "success",
  "title": "生成修复计划",
  "content": "先定位报错相关文件，再生成最小修改方案。",
  "duration_ms": 850,
  "metadata": {}
}
```

通用字段说明：

| 字段 | 说明 |
| --- | --- |
| `event_id` | 事件唯一 ID。 |
| `seq` | 事件顺序号，从 1 递增。 |
| `parent_event_id` | 父事件 ID，用于表示某个 tool result 属于哪个 tool call。 |
| `timestamp` | 事件发生时间。 |
| `event_type` | 事件类型。 |
| `phase` | 所属执行阶段。 |
| `actor` | `user`、`agent`、`tool`、`system`。 |
| `status` | `pending`、`running`、`success`、`failed`、`skipped`、`waiting_confirmation`。 |
| `title` | 用于前端展示的短标题。 |
| `content` | 事件正文或摘要。 |
| `duration_ms` | 该事件耗时。 |
| `metadata` | 扩展字段。 |

### 5.3 事件类型枚举

| `event_type` | 含义 |
| --- | --- |
| `user_input` | 用户输入或补充约束。 |
| `issue_triage` | Issue 分诊。 |
| `skill_select` | Skill 选择。 |
| `planning` | 生成计划。 |
| `llm_generation` | Agent 思考或回复。 |
| `tool_call` | 发起工具调用。 |
| `tool_result` | 工具执行结果。 |
| `patch_proposal` | 生成待确认修改方案。 |
| `user_confirmation` | 用户确认、拒绝或要求重试。 |
| `patch_apply` | 实际应用代码修改。 |
| `test_run` | 测试或验证命令执行。 |
| `reflection` | 失败反思与策略调整。 |
| `verify` | 成功条件验证。 |
| `patch_review` | 修改后自审。 |
| `final_report` | 修复报告或 PR 描述。 |
| `error` | 异常事件。 |

### 5.4 工具调用事件

工具调用使用 `tool_call` 和 `tool_result` 两类事件表示。第二组负责补全该部分字段，第一组负责汇总进完整 Agent Trace。

```json
{
  "event_id": "event-006",
  "seq": 6,
  "timestamp": "2026-05-13T12:01:10Z",
  "event_type": "tool_result",
  "phase": "tool_execution",
  "actor": "tool",
  "status": "failed",
  "title": "工具输出：run_pytest",
  "content": "1 failed, 3 passed",
  "duration_ms": 2310,
  "tool_call": {
    "name": "run_pytest",
    "arguments": {
      "pytest_args": "tests/test_example.py",
      "working_dir": "."
    },
    "result_preview": "AssertionError: expected 200, got 500",
    "error_message": "AssertionError",
    "exit_code": 1,
    "latency_ms": 2310,
    "risk_level": "medium",
    "sandbox_id": "sandbox-task-001",
    "affected_files": []
  },
  "metadata": {}
}
```

工具事件必须至少包含：

- 工具名称和参数。
- 执行状态。
- 输出摘要。
- 错误信息。
- 耗时。
- 退出码。
- 所属沙箱。
- 影响文件列表。

### 5.5 Patch 与用户确认事件

Agent 修改仓库文件前，需要先产生 `patch_proposal` 事件，等待用户确认。用户确认后才能产生 `patch_apply` 事件。

```json
{
  "event_id": "event-008",
  "seq": 8,
  "event_type": "patch_proposal",
  "phase": "patch_confirmation",
  "actor": "agent",
  "status": "waiting_confirmation",
  "title": "等待用户确认修改",
  "content": "建议修改 src/example.py 中的异常处理逻辑。",
  "metadata": {
    "affected_files": ["src/example.py"],
    "diff_preview": "...",
    "reason": "当前异常分支未返回正确状态码",
    "risk_level": "medium"
  }
}
```

用户确认事件：

```json
{
  "event_id": "event-009",
  "seq": 9,
  "event_type": "user_confirmation",
  "phase": "patch_confirmation",
  "actor": "user",
  "status": "success",
  "title": "用户确认应用修改",
  "content": "确认应用该 patch",
  "metadata": {
    "decision": "approved",
    "target_event_id": "event-008"
  }
}
```

### 5.6 Bad Case 归因字段

当任务失败或评测命中异常模式时，可以在 Trace 顶层或最后一个 `error/verify` 事件中补充归因字段：

```json
{
  "failure_type": "agent_reasoning",
  "failure_reason": "Agent 输出成功，但没有运行测试，也没有其他验证证据。",
  "related_event_ids": ["event-011", "event-012"],
  "suggested_fix": "修改 Verify 阶段成功条件，要求存在测试结果、代码 diff 或明确验证证据。"
}
```

推荐失败类型：

| `failure_type` | 含义 |
| --- | --- |
| `agent_reasoning` | 推理链路问题，例如计划错误、过早成功、反复无效操作。 |
| `context_loss` | 上下文丢失，例如忘记用户补充约束或测试错误。 |
| `tool_error` | 工具执行问题，例如参数错误、工具返回异常。 |
| `sandbox_error` | 沙箱或环境问题，例如依赖缺失、测试命令不可用。 |
| `knowledge_gap` | 缺少仓库知识，例如不了解测试命令或框架约定。 |
| `user_rejected` | 用户拒绝修改方案。 |

### 5.7 最小必填标准

为了避免实现成本过高，迭代三第一版至少保证以下字段存在：

- 顶层：`schema_version`、`trace_id`、`task_id`、`conversation_id`、`agent_version`、`status`、`events`。
- 每个事件：`event_id`、`seq`、`timestamp`、`event_type`、`actor`、`status`、`title`。
- 工具事件：`tool_call.name`、`tool_call.arguments`、`tool_call.result_preview`、`tool_call.error_message`、`tool_call.latency_ms`。
- 修改事件：`affected_files`、`diff_preview`、`decision`。
- 失败样例：`failure_type`、`failure_reason`、`related_event_ids`。

### 5.8 三组责任边界

| 小组 | 责任 |
| --- | --- |
| 第一组 | 定义标准 Trace，负责 Agent 阶段事件、上下文事件、失败归因、Trace 汇总。 |
| 第二组 | 补全工具事件字段，包括状态、耗时、错误、退出码、影响文件和 sandbox_id。 |
| 第三组 | 消费标准 Trace，用于前端展示、评测指标计算、Bad Case 管理和优化前后对比。 |