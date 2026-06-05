from __future__ import annotations

import json
import time
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from .utils.compressor import ContextCompressor
from .agent import Agent
from .agent_state import AgentState
from .skills import SkillRegistry
from .tools.tools import AGENT_TOOLS, _git_diff_impl, set_active_sandbox
from .tools.registry import ToolRegistry, ToolCallEvent
from .tools.sandbox_manager import SandboxManager


EDIT_TOOL_NAMES = {"write_file", "replace_in_file", "patch_file"}
MAX_ITERATIONS_REACHED_STATUS = "MAX_ITERATIONS_REACHED"
USER_INSERT_PREFIX = "[用户插入指令]"


class AgentOrchestrator:
    def __init__(
        self,
        agent: Agent,
        tools: list = AGENT_TOOLS,
        compressor: ContextCompressor | None = None,
        skill_registry: SkillRegistry | None = None,
        registry: ToolRegistry | None = None,
        sandbox_manager: SandboxManager | None = None,
    ):
        self.agent = agent
        self.tools = tools
        self.agent.set_tools(self.tools)
        self.memory = MemorySaver()
        self.compressor = compressor or ContextCompressor()
        self.skill_registry = skill_registry or SkillRegistry()
        self.registry = registry  # 工具注册表（迭代三第二组新增）
        self.sandbox_manager = sandbox_manager  # 沙箱管理器（迭代三第二组新增）
        self._sandbox_activated = False  # 标记沙箱是否已激活
        self.state_persist_hook = None
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("h_planner", self._node_h_planner)
        workflow.add_node("react", self._node_react)
        workflow.add_node("tools", self._node_tools)
        workflow.add_node("reflect", self._node_reflect)
        workflow.add_node("finish_success", self._node_finish_success)
        workflow.add_node("finish_failed", self._node_finish_failed)
        workflow.add_node("finish_max_iterations", self._node_finish_max_iterations)
        workflow.add_node("reopen", self._node_reopen)

        workflow.set_entry_point("h_planner")
        workflow.add_conditional_edges(
            "h_planner",
            self._route_after_planner,
            {"react": "react", "finish_success": "finish_success"},
        )
        workflow.add_conditional_edges(
            "react",
            self._route_react,
            {
                "tools": "tools",
                "reflect": "reflect",
                "h_planner": "h_planner",
                "finish_success": "finish_success",
                "finish_failed": "finish_failed",
                "finish_max_iterations": "finish_max_iterations",
            },
        )
        workflow.add_edge("tools", "react")
        workflow.add_edge("reopen", "react")  # fixed edge for reopen
        workflow.add_conditional_edges(
            "reflect",
            self._route_after_reflect,
            {"h_planner": "h_planner", "react": "react"},
        )
        workflow.add_edge("finish_success", END)
        workflow.add_edge("finish_failed", END)
        workflow.add_edge("finish_max_iterations", END)
        return workflow.compile(checkpointer=self.memory)

    def _shorten(self, text: str, limit: int = 300) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    def _json_dumps(self, value) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        except TypeError:
            return str(value)

    def _is_successful_edit_message(self, message) -> bool:
        tool_name = getattr(message, "name", None)
        if tool_name not in EDIT_TOOL_NAMES:
            return False
        content = getattr(message, "content", "") or ""
        return not content.lower().startswith("error:")

    def _has_meaningful_git_output(self, output: str) -> bool:
        text = (output or "").strip()
        return bool(text and text != "Command finished with exit code 0.")

    def user_added_requirements(self, state: AgentState) -> list[str]:
        requirements: list[str] = []
        for message in state.get("messages", []):
            content = getattr(message, "content", "") or ""
            if not isinstance(content, str):
                continue
            if not content.startswith(USER_INSERT_PREFIX):
                continue
            requirement = content[len(USER_INSERT_PREFIX):].strip()
            if requirement:
                requirements.append(requirement)
        return requirements

    def effective_issue_description(self, state: AgentState) -> str:
        base = state.get("issue_description", "")
        requirements = self.user_added_requirements(state)
        if not requirements:
            return base
        appended = "\n".join(f"- {requirement}" for requirement in requirements)
        return f"{base}\n\n用户追加要求（同样必须满足，按时间顺序）：\n{appended}"

    def _tool_messages(self, state: AgentState) -> list:
        return [message for message in state.get("messages", []) if getattr(message, "name", None)]

    def _ai_trajectory(self, state: AgentState) -> list[dict]:
        return [item for item in state.get("trajectory", []) if item.get("type") == "ai"]

    def _reflection_count(self, state: AgentState) -> int:
        return sum(1 for item in state.get("trajectory", []) if item.get("type") == "reflection")

    def _latest_successful_edit_index(self, state: AgentState) -> int | None:
        tool_messages = self._tool_messages(state)
        for index in range(len(tool_messages) - 1, -1, -1):
            if self._is_successful_edit_message(tool_messages[index]):
                return index
        return None

    def _recent_successful_edit(self, state: AgentState) -> bool:
        messages = state.get("messages", [])
        for message in reversed(messages):
            if hasattr(message, "tool_calls") and getattr(message, "tool_calls", []):
                break
            if self._is_successful_edit_message(message):
                return True
        return False

    def _consecutive_non_tool_ai_turns(self, state: AgentState) -> int:
        count = 0
        for item in reversed(self._ai_trajectory(state)):
            content = (item.get("content") or "").strip()
            if item.get("tool_calls"):
                break
            if "TASK_SUCCESS" in content or "TASK_FAILED" in content:
                break
            count += 1
        return count

    def _last_two_ai_contents_match(self, state: AgentState) -> bool:
        ai_items = self._ai_trajectory(state)
        if len(ai_items) < 2:
            return False
        current = (ai_items[-1].get("content") or "").strip()
        previous = (ai_items[-2].get("content") or "").strip()
        if not current or not previous:
            return False
        if ai_items[-1].get("tool_calls") or ai_items[-2].get("tool_calls"):
            return False
        return current == previous

    def _last_message_has_tool_calls(self, state: AgentState) -> bool:
        messages = state.get("messages", [])
        if not messages:
            return False
        tool_calls = getattr(messages[-1], "tool_calls", []) or []
        return len(tool_calls) > 0

    def _format_tool_call(self, call: dict) -> str:
        name = call.get("name", "unknown_tool")
        args = call.get("args", {})
        return f"{name} args={self._json_dumps(args)}"

    def _print_repo_diff(self, repo_path: str, verbose: bool = False):
        try:
            diff_output = _git_diff_impl(repo_path or ".")
        except Exception as exc:
            print(f"   无法显示修改 diff: {exc}")
            return

        if not self._has_meaningful_git_output(diff_output):
            print("   未检测到 Git diff。")
            return

        print("   文件修改:")
        print(self._shorten(diff_output, 4000 if verbose else 1500))

    def _print_failure_diagnostics(self, state: dict):
        print("   自动展开失败诊断:")

        ai_items = self._ai_trajectory(state)
        if ai_items:
            latest_ai = ai_items[-1]
            content = latest_ai.get("content", "")
            if content:
                print(f"   最后回复: {self._shorten(content, 1200)}")

            tool_calls = latest_ai.get("tool_calls", []) or []
            if tool_calls:
                print("   最后一次请求的工具调用:")
                for index, call in enumerate(tool_calls, start=1):
                    print(
                        f"   [{index}] {self._shorten(self._format_tool_call(call), 1200)}")

        tool_messages = self._tool_messages(state)
        if tool_messages:
            print("   最近工具输出:")
            for index, message in enumerate(tool_messages[-3:], start=1):
                tool_name = getattr(message, "name", None) or f"tool_{index}"
                content = getattr(message, "content", "") or ""
                print(
                    f"   [{index}] {tool_name}: {self._shorten(str(content), 1500)}")

    def _print_event(self, node_name: str, payload: dict, state: dict | None = None, verbose: bool = False):
        if node_name == "h_planner":
            goals = payload.get("goals") or []
            plan_version = payload.get("plan_version", 1)
            selected_skill = payload.get("selected_skill", "") or (state or {}).get("selected_skill", "")
            print(f"🧭 分层规划（v{plan_version}）")
            if selected_skill:
                print(f"   🎯 选定 Skill: {selected_skill}")
            else:
                print("   🎯 未选择 Skill，使用通用流程")
            if goals and verbose:
                for idx, goal in enumerate(goals, 1):
                    print(f"   目标{idx}: {goal.get('description', '')}")
            elif goals:
                print(f"   生成 {len(goals)} 个目标")
            return

        if node_name == "react":
            messages = payload.get("messages") or []
            if not messages:
                print("🤖 Agent 完成一轮思考")
                return

            ai_msg = messages[-1]
            content = getattr(ai_msg, "content", "") or ""
            tool_calls = getattr(ai_msg, "tool_calls", []) or []
            print(f"🤖 Agent 思考完成（第 {payload.get('iteration_count', '?')} 轮）")
            if content:
                print(
                    f"   回复: {self._shorten(content, 800 if verbose else 220)}")
            if tool_calls:
                print(f"   工具调用数: {len(tool_calls)}")
                if verbose:
                    for idx, call in enumerate(tool_calls, start=1):
                        print(
                            f"   [{idx}] {self._shorten(self._format_tool_call(call), 1600)}")
            return

        if node_name == "tools":
            messages = payload.get("messages") or []
            tool_call_events = payload.get("tool_call_events") or []
            print(f"🛠️ 工具执行完成（{len(messages)} 条结果）")

            # 显示被拒绝的工具调用
            if tool_call_events:
                rejected = [e for e in tool_call_events if e.get("status") == "rejected"]
                if rejected:
                    for r in rejected:
                        print(f"   🚫 硬禁用拦截: {r.get('tool_name', '?')}")

            if verbose:
                for idx, message in enumerate(messages, start=1):
                    name = getattr(message, "name", None) or getattr(
                        message, "tool_call_id", None) or f"tool_{idx}"
                    content = getattr(message, "content", "")
                    print(
                        f"   [{idx}] {name}: {self._shorten(str(content), 1200)}")
            else:
                for idx, message in enumerate(messages, start=1):
                    name = getattr(message, "name", None) or getattr(
                        message, "tool_call_id", None) or f"tool_{idx}"
                    print(
                        f"   [{idx}] {name}")
            if any(self._is_successful_edit_message(message) for message in messages):
                repo_path = (state or {}).get("repo_path", ".")
                self._print_repo_diff(repo_path, verbose=verbose)
            return

        if node_name == "reflect":
            reflexion = payload.get("reflexion_notes", "")
            replan_trigger = payload.get("replan_trigger", "")
            print("🪞 进入反思阶段")
            if reflexion:
                print(
                    f"   反思: {self._shorten(reflexion, 800 if verbose else 220)}")
            if replan_trigger:
                print(f"   触发重规划: {replan_trigger}")
            return

        if node_name == "finish_max_iterations":
            print("⏸️ 已达到 max_iterations，等待用户决定是否延长对话。")
            return

        print(f"⚙️ Graph Step: {node_name}")

    def _accumulate_token_usage(self, state: AgentState) -> dict[str, int]:
        """从 agent.last_token_usage 累加到 state 中的 token_usage。"""
        usage = self.agent.last_token_usage
        cumulative = state.get("token_usage", {})
        return {
            "prompt_tokens": cumulative.get("prompt_tokens", 0) + usage.get("prompt_tokens", 0),
            "completion_tokens": cumulative.get("completion_tokens", 0) + usage.get("completion_tokens", 0),
            "total_tokens": cumulative.get("total_tokens", 0) + usage.get("total_tokens", 0),
        }

    async def _node_h_planner(self, state: AgentState):
        existing_goals = state.get("goals", [])
        replan_trigger = state.get("replan_trigger", "")
        plan_version = state.get("plan_version", 0)

        if not existing_goals:
            # 首次规划：同时做 Skill 选择 + 目标生成
            skills_catalog = self.skill_registry.router_catalog()
            skill_name, goals = await self.agent.select_skill_and_plan(
                self.effective_issue_description(state),
                skills_catalog,
            )

            skill = self.skill_registry.get(skill_name) if skill_name else None
            skill_state = {
                "selected_skill": skill.name if skill else "",
                "skill_instructions": skill.body if skill else "",
                "skill_priority_tools": skill.priority_tools if skill else [],
                "skill_allowed_tools": skill.allowed_tools if skill else [],
            }

            next_index = next(
                (i for i, g in enumerate(goals) if g.get("status") != "done"),
                len(goals),
            )

            trajectory_entries = [
                {"type": "plan", "content": json.dumps(
                    goals, ensure_ascii=False)}
            ]
            trajectory_entries.insert(
                0,
                {
                    "type": "skill_select",
                    "content": f"selected_skill={skill.name if skill else 'none'}",
                },
            )

            return {
                **skill_state,
                "goals": goals,
                "current_goal_index": next_index,
                "plan_version": plan_version + 1,
                "replan_trigger": "",
                "trajectory": trajectory_entries,
                "token_usage": self._accumulate_token_usage(state),
                "status": "PLANNING",
            }

        if replan_trigger:
            # 重规划：保留已选 Skill，只重新生成目标
            goals = await self.agent.generate_hierarchical_plan(
                self.effective_issue_description(state),
                existing_goals=existing_goals,
                replan_reason=replan_trigger,
            )

            completed = [g for g in existing_goals if g.get(
                "status") == "done"]
            goals = completed + goals

            next_index = next(
                (i for i, g in enumerate(goals) if g.get("status") != "done"),
                len(goals),
            )

            return {
                "goals": goals,
                "current_goal_index": next_index,
                "plan_version": plan_version + 1,
                "replan_trigger": "",
                "trajectory": [{"type": "plan", "content": json.dumps(goals, ensure_ascii=False)}],
                "token_usage": self._accumulate_token_usage(state),
                "status": "PLANNING",
            }

        next_index = next(
            (i for i, g in enumerate(existing_goals) if g.get("status") != "done"),
            len(existing_goals),
        )

        return {
            "goals": existing_goals,
            "current_goal_index": next_index,
            "plan_version": plan_version,
            "replan_trigger": "",
            "status": "PLANNING",
        }

    async def _node_react(self, state: AgentState):
        goals = state.get("goals", [])
        current_goal_index = state.get("current_goal_index", 0)
        current_goal = goals[current_goal_index] if current_goal_index < len(goals) else {
        }

        plan_lines = []
        for i, g in enumerate(goals, 1):
            status_mark = "✓" if g.get(
                "status") == "done" else "→" if i == current_goal_index + 1 else " "
            plan_lines.append(f"{status_mark} {i}. {g.get('description', '')}")

        raw_messages = state["messages"]
        compressed_messages = await self.compressor.compress(raw_messages)

        compression_stats = {
            "total_before": len(raw_messages),
            "total_after": len(compressed_messages),
            "level2_summaries": 1 if len(compressed_messages) < len(raw_messages) and len(raw_messages) > self.compressor.level0_window + self.compressor.level1_window else 0,
            **getattr(self.compressor, "last_stats", {}),
        }

        response = await self.agent.run_react(
            compressed_messages,
            issue_description=self.effective_issue_description(state),
            repo_path=state.get("repo_path", ""),
            plan=plan_lines,
            reflexion_notes=state.get("reflexion_notes", ""),
            current_goal=current_goal.get("description", ""),
            skill_instructions=state.get("skill_instructions", ""),
            skill_priority_tools=state.get("skill_priority_tools", []),
            skill_allowed_tools=state.get("skill_allowed_tools", []),
        )

        return {
            "messages": [response],
            "trajectory": [
                {
                    "type": "ai",
                    "content": response.content,
                    "tool_calls": getattr(response, "tool_calls", []),
                }
            ],
            "iteration_count": state["iteration_count"] + 1,
            "compression_stats": compression_stats,
            "token_usage": self._accumulate_token_usage(state),
            "status": "RUNNING",
        }

    async def _node_tools(self, state: AgentState):
        """自定义工具执行节点，替代 LangGraph 的 ToolNode（迭代三第二组新增）。

        职责：
          1. 遍历 AIMessage 中 LLM 请求的 tool_calls
          2. 通过 ToolRegistry 检查每次调用（硬禁用 + 参数校验）
          3. 执行工具（沙箱路由在 tools.py 层透明处理）
          4. 记录 ToolCallEvent 到 state.tool_call_events
        """
        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", []) or []

        if not tool_calls:
            return {}

        tool_messages: list = []
        events: list[ToolCallEvent] = []
        sandbox_id = state.get("sandbox_id", "")

        # 首次调用工具时激活沙箱（如果沙箱已创建但尚未激活）
        if sandbox_id and not self._sandbox_activated and self.sandbox_manager:
            sandbox = self.sandbox_manager.get(sandbox_id)
            if sandbox is not None and sandbox._started:
                set_active_sandbox(sandbox)
                self._sandbox_activated = True
                print(f"[orchestrator] 沙箱已激活，shell 命令将路由到容器: {sandbox.container_name}")

        for tc in tool_calls:
            tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
            call_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
            start_time = time.time()

            # ---- 1. 注册表检查（硬禁用 + 参数校验） ----
            if self.registry is not None:
                rejection = self.registry.check_invocation(tool_name, tool_args)
                if rejection:
                    # 被拒绝：向 LLM 返回拒绝消息，不执行工具
                    tool_messages.append(ToolMessage(
                        content=rejection,
                        tool_call_id=call_id,
                        name=tool_name,
                    ))
                    events.append(ToolCallEvent(
                        tool_name=tool_name,
                        arguments=tool_args,
                        status="rejected",
                        error_message=rejection,
                        latency_ms=int((time.time() - start_time) * 1000),
                        sandbox_id=sandbox_id,
                    ))
                    continue

            # ---- 1.5 requires_confirmation 检查（迭代三第二组） ----
            # 查询工具是否需要用户确认。CLI 模式下不阻塞执行（Agent 需要修改代码），
            # 但会打印提醒并记录到事件中，供第三组 Web 界面展示确认弹窗。
            tool_meta = self.registry.get_meta(tool_name) if self.registry else None
            if tool_meta and tool_meta.requires_confirmation:
                print(f"   ⚠️ 工具 '{tool_name}' 需要用户确认（metadata 标记），"
                      f"风险等级: {tool_meta.risk_level.value}")

            # ---- 2. 查找并执行工具 ----
            tool_func = None
            if self.registry is not None:
                tool_func = self.registry.get_tool(tool_name)
            if tool_func is None:
                # 回退：按名称在 self.tools 中查找
                for t in self.tools:
                    name = getattr(t, "name", None) or getattr(t, "__name__", "")
                    if name == tool_name:
                        tool_func = t
                        break

            if tool_func is None:
                error_content = f"工具 '{tool_name}' 未找到，无法执行。"
                tool_messages.append(ToolMessage(
                    content=error_content,
                    tool_call_id=call_id,
                    name=tool_name,
                ))
                events.append(ToolCallEvent(
                    tool_name=tool_name,
                    arguments=tool_args,
                    status="error",
                    error_message=error_content,
                    latency_ms=int((time.time() - start_time) * 1000),
                    sandbox_id=sandbox_id,
                ))
                continue

            try:
                result = await tool_func.ainvoke(tool_args)
                status = "success"
                error_msg = ""
                exit_code_val = 0
            except Exception as exc:
                result = f"Error: {exc}"
                status = "error"
                error_msg = str(exc)
                exit_code_val = -1

            latency_ms = int((time.time() - start_time) * 1000)

            # ---- 3. 提取受影响的文件 ----
            affected_files: list = []
            if status == "success" and tool_meta and tool_meta.category.value == "file":
                # 文件修改类工具：获取 git diff 涉及的文件
                try:
                    diff = _git_diff_impl(state.get("repo_path", "."))
                    if diff and diff != "Command finished with exit code 0.":
                        from .cli_utils.git import extract_modified_files_from_diff
                        affected_files = extract_modified_files_from_diff(diff)
                except Exception:
                    pass

            # ---- 4. 记录事件 ----
            events.append(ToolCallEvent(
                tool_name=tool_name,
                arguments=tool_args,
                status=status,
                result_preview=str(result)[:300] if result else "",
                error_message=error_msg,
                latency_ms=latency_ms,
                sandbox_id=sandbox_id,
                affected_files=affected_files,
                exit_code=exit_code_val,
            ))

            tool_messages.append(ToolMessage(
                content=str(result),
                tool_call_id=call_id,
                name=tool_name,
            ))

        # 将事件写入注册表缓冲区（供第一组和第三组消费）
        if self.registry is not None:
            for event in events:
                self.registry.record_event(event)

        return {
            "messages": tool_messages,
            "tool_call_events": [e.to_dict() for e in events],
        }

    async def _node_reflect(self, state: AgentState):
        reflexion = await self.agent.reflect_on_failure(state["trajectory"])

        replan_trigger = ""
        if "偏离" in reflexion or "deviation" in reflexion.lower():
            replan_trigger = "deviation"
        elif self._consecutive_non_tool_ai_turns(state) >= 3:
            replan_trigger = "stuck"

        return {
            "messages": [
                HumanMessage(
                    content=(
                        f"反思结果：{reflexion}\n"
                        "请根据反思调整策略，优先使用工具推进。"
                    )
                )
            ],
            "reflexion_notes": reflexion,
            "replan_trigger": replan_trigger,
            "trajectory": [{"type": "reflection", "content": reflexion}],
            "token_usage": self._accumulate_token_usage(state),
            "status": "REFLECTING",
        }

    async def _node_finish_success(self, state: AgentState):
        return {"status": "SUCCESS"}

    async def _node_finish_failed(self, state: AgentState):
        return {"status": "FAILED"}

    async def _node_finish_max_iterations(self, state: AgentState):
        max_iterations = state.get("max_iterations", 15)
        note = f"已达到 max_iterations={max_iterations}，等待用户决定是否延长对话。"
        return {
            "status": MAX_ITERATIONS_REACHED_STATUS,
            "trajectory": [{"type": "control", "content": note}],
        }

    async def _node_reopen(self, state: AgentState):
        return {}

    def _route_after_planner(self, state: AgentState) -> str:
        goals = state.get("goals", [])
        current_goal_index = state.get("current_goal_index", 0)

        if current_goal_index >= len(goals):
            return "finish_success"

        return "react"

    def _route_react(self, state: AgentState) -> str:
        last_msg = state["messages"][-1]
        content = getattr(last_msg, "content", "") or ""

        # Agent 主动给出的终止信号优先于 iteration 上限：
        # 即使刚好打满 max_iterations，只要它说"做完了/做不下去了"，也别强行判 FAILED。
        if "TASK_SUCCESS" in content:
            return "finish_success"
        if "TASK_FAILED" in content:
            return "finish_failed"

        if self._last_message_has_tool_calls(state):
            return "tools"

        if state["iteration_count"] >= state.get("max_iterations", 15):
            return "finish_max_iterations"

        if "GOAL_DONE" in content or self._recent_successful_edit(state):
            goals = state.get("goals", [])
            current_goal_index = state.get("current_goal_index", 0)
            if current_goal_index < len(goals):
                goals[current_goal_index]["status"] = "done"
            return "h_planner"

        no_progress_turns = self._consecutive_non_tool_ai_turns(state)
        repeated_reply = self._last_two_ai_contents_match(state)
        reflection_count = self._reflection_count(state)
        # stand for unrepairable error
        if no_progress_turns >= 3:
            return "finish_failed"
        if repeated_reply and reflection_count >= 2:
            return "finish_failed"

        return "reflect"

    def _route_after_reflect(self, state: AgentState) -> str:
        replan_trigger = state.get("replan_trigger", "")
        plan_version = state.get("plan_version", 0)

        if replan_trigger and plan_version < 3:
            return "h_planner"
        return "react"

    def inject_message(self, thread_id: str, content: str, replan: bool = False):
        """向正在运行的会话注入一条用户消息。

        replan=True 时同时设置 replan_trigger，下一次进入 reflect 会被路由回 h_planner。
        """
        config = {"configurable": {"thread_id": thread_id}}
        update: dict = {
            "messages": [HumanMessage(content=f"[用户插入指令] {content}")]
        }
        if replan:
            update["replan_trigger"] = "user_intervention"
        self.graph.update_state(config, update)
        self.persist_state(thread_id)

    def persist_state(self, thread_id: str, last_node: str | None = None) -> None:
        if self.state_persist_hook is None:
            return
        try:
            self.state_persist_hook(thread_id, last_node)
        except Exception as exc:
            print(f"[持久化] 保存会话状态失败: {exc}")

    async def run_step(self, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            node_name = list(event.keys())[0]
            self.persist_state(thread_id, node_name)
            return event

    async def run_auto(self, thread_id: str, verbose: bool = False):
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            node_name = list(event.keys())[0]
            state = self.graph.get_state(config).values
            self.persist_state(thread_id, node_name)
            self._print_event(
                node_name, event[node_name], state=state, verbose=verbose)

        final_state = self.graph.get_state(config).values
        if final_state.get("status") == "FAILED":
            self._print_failure_diagnostics(final_state)
        return final_state

    async def run_auto_interactive(self, thread_id: str, verbose: bool = False):
        """逐节点执行，每个节点结束后 yield 一次，调用方可在 yield 期间 inject_message。

        即使是终态节点（SUCCESS/FAILED）也会先 yield 再 return，
        给调用方最后一次机会把队列里的输入注入到 state。

        用法：
            async for step_info in orchestrator.run_auto_interactive(thread_id):
                # step_info = {"node": node_name, "state": state}
                # 此处可检查用户输入并调用 inject_message
                pass
        """
        config = {"configurable": {"thread_id": thread_id}}

        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            node_name = list(event.keys())[0]
            current_state = self.graph.get_state(config).values
            self.persist_state(thread_id, node_name)
            self._print_event(
                node_name, event[node_name], state=current_state, verbose=verbose)

            yield {"node": node_name, "state": current_state}

            status = current_state.get("status", "")
            if status in ("SUCCESS", "FAILED", MAX_ITERATIONS_REACHED_STATUS):
                if status == "FAILED":
                    self._print_failure_diagnostics(current_state)
                return

    def reopen_after_terminal(self, thread_id: str, extra_iterations: int = 5):
        """图已到达终态后，若用户追加了输入，把状态推回 react 继续处理。

        通过 as_node="reopen" 让 graph 走 reopen→react 固定边重新进入推理；
        同时把 max_iterations 抬高，避免立即被 iteration 上限挡掉。
        """
        config = {"configurable": {"thread_id": thread_id}}
        current_state = self.graph.get_state(config).values
        current_max = current_state.get("max_iterations", 15)
        current_count = current_state.get("iteration_count", 0)
        extra_iterations = max(int(extra_iterations or 0), 1)
        new_max = max(current_max + extra_iterations, current_count + extra_iterations)
        resume_node = "react" if self._last_message_has_tool_calls(current_state) else "reopen"
        self.graph.update_state(
            config,
            {"status": "RUNNING", "max_iterations": new_max},
            as_node=resume_node,
        )
        self.persist_state(thread_id, resume_node)

    def mark_failed_after_user_declines_extension(self, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        self.graph.update_state(
            config,
            {"status": "FAILED"},
            as_node="finish_failed",
        )
        self.persist_state(thread_id, "finish_failed")

    async def raw_chat(self, user_input):
        return (await self.agent.chat(user_input)).content
