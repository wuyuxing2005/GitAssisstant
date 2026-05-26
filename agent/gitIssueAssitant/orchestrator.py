from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from .utils.compressor import ContextCompressor
from .agent import Agent
from .agent_state import AgentState
from .skills import SkillRegistry
from .tools.tools import AGENT_TOOLS, _git_diff_impl


EDIT_TOOL_NAMES = {"write_file", "replace_in_file", "patch_file"}


class AgentOrchestrator:
    def __init__(
        self,
        agent: Agent,
        tools: list = AGENT_TOOLS,
        compressor: ContextCompressor | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.agent = agent
        self.tools = tools
        self.memory = MemorySaver()
        self.compressor = compressor or ContextCompressor()
        self.skill_registry = skill_registry or SkillRegistry()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("h_planner", self._node_h_planner)
        workflow.add_node("react", self._node_react)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.add_node("reflect", self._node_reflect)
        workflow.add_node("verify", self._node_verify)
        workflow.add_node("finish_success", self._node_finish_success)
        workflow.add_node("finish_failed", self._node_finish_failed)

        workflow.set_entry_point("h_planner")
        workflow.add_conditional_edges(
            "h_planner",
            self._route_after_planner,
            {"react": "react", "verify": "verify"},
        )
        workflow.add_conditional_edges(
            "react",
            self._route_react,
            {
                "tools": "tools",
                "verify": "verify",
                "reflect": "reflect",
                "h_planner": "h_planner",
                "finish_success": "finish_success",
                "finish_failed": "finish_failed",
            },
        )
        workflow.add_edge("tools", "react")
        workflow.add_conditional_edges(
            "reflect",
            self._route_after_reflect,
            {"h_planner": "h_planner", "react": "react"},
        )
        workflow.add_conditional_edges(
            "verify",
            self._route_verify,
            {"verified": "finish_success", "retry": "react"},
        )
        workflow.add_edge("finish_success", END)
        workflow.add_edge("finish_failed", END)
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

        if not diff_output.strip():
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
            selected_skill = payload.get("selected_skill", "")
            print(f"🧭 分层规划（v{plan_version}）")
            if selected_skill:
                print(f"   🎯 选定 Skill: {selected_skill}")
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
            print(f"🛠️ 工具执行完成（{len(messages)} 条结果）")
            if verbose:
                for idx, message in enumerate(messages, start=1):
                    name = getattr(message, "name", None) or getattr(
                        message, "tool_call_id", None) or f"tool_{idx}"
                    content = getattr(message, "content", "")
                    print(
                        f"   [{idx}] {name}: {self._shorten(str(content), 1200)}")
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
        selected_skill = state.get("selected_skill", "")

        if not existing_goals:
            # 首次规划：同时做 Skill 选择 + 目标生成
            skills_catalog = self.skill_registry.router_catalog()
            skill_name, goals = await self.agent.select_skill_and_plan(
                state["issue_description"],
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
            if skill:
                trajectory_entries.insert(
                    0,
                    {
                        "type": "skill_select",
                        "content": f"selected_skill={skill.name}",
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
                state["issue_description"],
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
        compressed_messages = self.compressor.compress(raw_messages)

        compression_stats = {
            "total_before": len(raw_messages),
            "total_after": len(compressed_messages),
            "level2_summaries": 1 if len(compressed_messages) < len(raw_messages) and len(raw_messages) > self.compressor.level0_window + self.compressor.level1_window else 0,
        }

        response = await self.agent.run_react(
            compressed_messages,
            issue_description=state["issue_description"],
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

    def _repo_contains_file(self, repo_path: str, relative_path: str) -> bool:
        repo_root = Path(repo_path)
        candidate = Path(relative_path)
        if candidate.is_absolute():
            return candidate.exists()

        direct = (repo_root / candidate).exists()
        if direct:
            return True

        if len(candidate.parts) == 1:
            return any(path.is_file() for path in repo_root.rglob(candidate.name))
        return False

    def _has_successful_test_signal(self, state: AgentState) -> bool:
        test_tool_names = {"run_pytest", "bash_terminal"}
        test_success_markers = [" passed", "passed in", "ok",
                                "tests passed", "build successful", "success"]
        test_failure_markers = ["failed", "error", "failure"]

        for message in reversed(self._tool_messages(state)):
            tool_name = getattr(message, "name", None)
            if tool_name not in test_tool_names:
                continue
            content = (getattr(message, "content", "") or "").lower()
            if content.startswith("error:"):
                return False
            # bash_terminal 只有在内容看起来像测试输出时才算
            if tool_name == "bash_terminal":
                is_test_output = any(kw in content for kw in [
                                     "test", "pytest", "jest", "mocha", "unittest", "go test", "cargo test"])
                if not is_test_output:
                    continue
            if any(marker in content for marker in test_failure_markers):
                return False
            if any(marker in content for marker in test_success_markers):
                return True
            return False
        return False

    def _has_blocking_failure_after_last_edit(self, state: AgentState) -> bool:
        latest_edit_index = self._latest_successful_edit_index(state)
        if latest_edit_index is None:
            return False

        tool_messages = self._tool_messages(state)
        for message in tool_messages[latest_edit_index + 1:]:
            content = (getattr(message, "content", "") or "").lower()
            if not content.startswith("error:"):
                continue
            tool_name = getattr(message, "name", None)
            if tool_name == "run_pytest" and "no module named pytest" in content:
                continue
            return True
        return False

    def _issue_requirements_satisfied(self, state: AgentState) -> tuple[bool | None, str]:

        # Fast path: 测试通过信号
        if self._has_successful_test_signal(state):
            return True, "验证通过：检测到成功的测试信号。"

        # 无快速通道命中，标记需要 LLM 验证
        return None, ""

    async def _node_verify(self, state: AgentState):
        fast_result, fast_note = self._issue_requirements_satisfied(state)

        if fast_result is True:
            return {
                "trajectory": [{"type": "verification", "content": fast_note}],
                "status": "SUCCESS",
            }
        if fast_result is False:
            return {
                "trajectory": [{"type": "verification", "content": fast_note}],
                "status": "VERIFYING",
                "messages": [
                    HumanMessage(
                        content=(
                            f"{fast_note}\n"
                            "请继续修改或检查仓库，并优先使用工具获取证据；确认满足 issue 要求后再输出 TASK_SUCCESS。"
                        )
                    )
                ],
            }

        # LLM 验证：需要有实际编辑才值得调用
        has_edit = self._latest_successful_edit_index(state) is not None
        if not has_edit:
            note = "尚未检测到实际代码修改，请先完成修改再验证。"
            return {
                "trajectory": [{"type": "verification", "content": note}],
                "status": "VERIFYING",
                "messages": [HumanMessage(content=note)],
            }

        # if self._has_blocking_failure_after_last_edit(state):
        #     note = "最近编辑后存在阻塞性错误，请先修复错误。"
        #     return {
        #         "trajectory": [{"type": "verification", "content": note}],
        #         "status": "VERIFYING",
        #         "messages": [HumanMessage(content=note)],
        #     }

        repo_path = state.get("repo_path", ".")
        try:
            diff_output = _git_diff_impl(repo_path)
        except Exception:
            diff_output = ""

        if not diff_output.strip():
            note = "未检测到 git diff，无法验证修改。"
            return {
                "trajectory": [{"type": "verification", "content": note}],
                "status": "VERIFYING",
                "messages": [HumanMessage(content=note)],
            }

        verdict = await self.agent.verify_issue_resolved(
            state.get("issue_description", ""), diff_output
        )

        if verdict.get("resolved"):
            note = f"LLM 验证通过：{verdict.get('reason', '')}"
            return {
                "trajectory": [{"type": "verification", "content": note}],
                "token_usage": self._accumulate_token_usage(state),
                "status": "SUCCESS",
            }

        note = f"LLM 验证未通过：{verdict.get('reason', '')}。请继续修改。"
        return {
            "trajectory": [{"type": "verification", "content": note}],
            "token_usage": self._accumulate_token_usage(state),
            "status": "VERIFYING",
            "messages": [
                HumanMessage(
                    content=f"{note}\n请根据以上反馈继续修改代码，确认满足 issue 要求后再输出 TASK_SUCCESS。"
                )
            ],
        }

    def _route_after_planner(self, state: AgentState) -> str:
        goals = state.get("goals", [])
        current_goal_index = state.get("current_goal_index", 0)

        if current_goal_index >= len(goals):
            return "verify"

        return "react"

    def _route_react(self, state: AgentState) -> str:
        last_msg = state["messages"][-1]
        content = getattr(last_msg, "content", "") or ""

        if state["iteration_count"] >= state.get("max_iterations", 15):
            return "finish_failed"

        if hasattr(last_msg, "tool_calls") and len(last_msg.tool_calls) > 0:
            return "tools"

        if "TASK_SUCCESS" in content:
            return "verify"
        if "TASK_FAILED" in content:
            return "finish_failed"

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

    def _route_verify(self, state: AgentState) -> str:
        if state.get("status") == "SUCCESS":
            return "verified"
        return "retry"

    def inject_message(self, thread_id: str, content: str):
        """向正在运行的会话注入一条用户消息"""
        config = {"configurable": {"thread_id": thread_id}}
        self.graph.update_state(
            config,
            {"messages": [HumanMessage(content=f"[用户插入指令] {content}")]},
        )

    async def run_step(self, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            return event

    async def run_auto(self, thread_id: str, verbose: bool = False):
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            node_name = list(event.keys())[0]
            state = self.graph.get_state(config).values
            self._print_event(
                node_name, event[node_name], state=state, verbose=verbose)

        final_state = self.graph.get_state(config).values
        if final_state.get("status") == "FAILED":
            self._print_failure_diagnostics(final_state)
        return final_state

    async def run_auto_interactive(self, thread_id: str, verbose: bool = False):
        """逐步执行，每步之间 yield 控制权，允许调用方注入用户消息。

        用法：
            async for step_info in orchestrator.run_auto_interactive(thread_id):
                # step_info = {"node": node_name, "state": state}
                # 此处可检查用户输入并调用 inject_message
                pass
        """
        config = {"configurable": {"thread_id": thread_id}}

        while True:
            state = self.graph.get_state(config)
            if state.next == ():
                break

            async for event in self.graph.astream(None, config=config, stream_mode="updates"):
                node_name = list(event.keys())[0]
                current_state = self.graph.get_state(config).values
                self._print_event(
                    node_name, event[node_name], state=current_state, verbose=verbose)

            current_state = self.graph.get_state(config).values
            status = current_state.get("status", "")
            if status in ("SUCCESS", "FAILED"):
                if status == "FAILED":
                    self._print_failure_diagnostics(current_state)
                break

            yield {"node": node_name, "state": current_state}

    async def raw_chat(self, user_input):
        return (await self.agent.chat(user_input)).content
