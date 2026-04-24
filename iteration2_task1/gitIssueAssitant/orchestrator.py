from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from .agent import Agent
from .agent_state import AgentState
from .tools.tools import AGENT_TOOLS, _git_diff_impl


EDIT_TOOL_NAMES = {"write_file", "replace_in_file", "patch_file"}


class AgentOrchestrator:
    def __init__(self, agent: Agent, tools: list = AGENT_TOOLS):
        self.agent = agent
        self.tools = tools
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("planner", self._node_planner)
        workflow.add_node("react", self._node_react)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.add_node("reflect", self._node_reflect)
        workflow.add_node("verify", self._node_verify)
        workflow.add_node("finish_success", self._node_finish_success)
        workflow.add_node("finish_failed", self._node_finish_failed)

        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "react")
        workflow.add_conditional_edges(
            "react",
            self._route_react,
            {
                "continue_tools": "tools",
                "verify": "verify",
                "reflect": "reflect",
                "end_success": "finish_success",
                "end_failed": "finish_failed",
            },
        )
        workflow.add_edge("tools", "react")
        workflow.add_edge("reflect", "react")
        workflow.add_conditional_edges(
            "verify",
            self._route_verify,
            {
                "verified": "finish_success",
                "retry": "react",
            },
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
        latest_index = self._latest_successful_edit_index(state)
        return latest_index is not None

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
                    print(f"   [{index}] {self._shorten(self._format_tool_call(call), 1200)}")

        tool_messages = self._tool_messages(state)
        if tool_messages:
            print("   最近工具输出:")
            for index, message in enumerate(tool_messages[-3:], start=1):
                tool_name = getattr(message, "name", None) or f"tool_{index}"
                content = getattr(message, "content", "") or ""
                print(f"   [{index}] {tool_name}: {self._shorten(str(content), 1500)}")

    def _print_event(self, node_name: str, payload: dict, state: dict | None = None, verbose: bool = False):
        if node_name == "planner":
            plan = payload.get("plan") or []
            print("🧭 正在规划修复步骤")
            if plan:
                print(f"   计划: {self._shorten(plan[-1], 500 if verbose else 180)}")
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
                print(f"   回复: {self._shorten(content, 800 if verbose else 220)}")
            if tool_calls:
                print(f"   工具调用数: {len(tool_calls)}")
                if verbose:
                    for idx, call in enumerate(tool_calls, start=1):
                        print(f"   [{idx}] {self._shorten(self._format_tool_call(call), 1600)}")
            return

        if node_name == "tools":
            messages = payload.get("messages") or []
            print(f"🛠️ 工具执行完成（{len(messages)} 条结果）")
            if verbose:
                for idx, message in enumerate(messages, start=1):
                    name = getattr(message, "name", None) or getattr(message, "tool_call_id", None) or f"tool_{idx}"
                    content = getattr(message, "content", "")
                    print(f"   [{idx}] {name}: {self._shorten(str(content), 1200)}")
            if any(self._is_successful_edit_message(message) for message in messages):
                repo_path = (state or {}).get("repo_path", ".")
                self._print_repo_diff(repo_path, verbose=verbose)
            return

        if node_name == "reflect":
            reflexion = payload.get("reflexion_notes", "")
            print("🪞 进入反思阶段")
            if reflexion:
                print(f"   反思: {self._shorten(reflexion, 800 if verbose else 220)}")
            return

        print(f"⚙️ Graph Step: {node_name}")

    async def _node_planner(self, state: AgentState):
        plan_text = await self.agent.generate_plan(state["issue_description"])
        return {
            "plan": [plan_text],
            "trajectory": [{"type": "plan", "content": plan_text}],
            "status": "PLANNING",
        }

    async def _node_react(self, state: AgentState):
        response = await self.agent.run_react(
            state["messages"],
            issue_description=state["issue_description"],
            repo_path=state.get("repo_path", ""),
            plan=state.get("plan", []),
            reflexion_notes=state.get("reflexion_notes", ""),
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
            "status": "RUNNING",
        }

    async def _node_reflect(self, state: AgentState):
        reflexion = await self.agent.reflect_on_failure(state["trajectory"])
        return {
            "messages": [
                HumanMessage(
                    content=(
                        "请根据这条反思调整后续策略，并优先使用工具推进。"
                        "如果上一轮没有新证据，这一轮不要重复计划或泛泛建议。\n"
                        f"{reflexion}"
                    )
                )
            ],
            "reflexion_notes": reflexion,
            "trajectory": [{"type": "reflection", "content": reflexion}],
            "status": "REFLECTING",
        }

    async def _node_finish_success(self, state: AgentState):
        return {"status": "SUCCESS"}

    async def _node_finish_failed(self, state: AgentState):
        return {"status": "FAILED"}

    def _extract_missing_file_requirements(self, issue_description: str) -> list[str]:
        patterns = [
            r"(?:missing|lack(?:ing)?|without|no)\s+[`\"']?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_+-]+)[`\"']?",
            r"(?:缺少|没有|找不到|不存在)\s*[`\"']?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_+-]+)[`\"']?",
        ]
        matches: list[str] = []
        for pattern in patterns:
            matches.extend(re.findall(pattern, issue_description, flags=re.IGNORECASE))

        normalized: list[str] = []
        seen: set[str] = set()
        for item in matches:
            candidate = item.strip().strip("`\"'").replace("\\", "/")
            if candidate and candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
        return normalized

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

    def _extract_issue_file_references(self, issue_description: str) -> list[str]:
        matches = re.findall(r"[`\"']?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_+-]+)[`\"']?", issue_description, flags=re.IGNORECASE)
        normalized: list[str] = []
        seen: set[str] = set()
        for item in matches:
            candidate = item.strip().strip("`\"'").replace("\\", "/")
            if candidate and candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
        return normalized

    def _extract_changed_files(self, repo_path: str) -> list[str]:
        try:
            diff_output = _git_diff_impl(repo_path or ".")
        except Exception:
            return []

        changed_files: list[str] = []
        seen: set[str] = set()
        for line in diff_output.splitlines():
            if not line.startswith("diff --git "):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            candidate = parts[2]
            if candidate.startswith("a/"):
                candidate = candidate[2:]
            candidate = candidate.replace("\\", "/")
            if candidate and candidate not in seen:
                seen.add(candidate)
                changed_files.append(candidate)
        return changed_files

    def _has_successful_test_signal(self, state: AgentState) -> bool:
        for message in reversed(self._tool_messages(state)):
            if getattr(message, "name", None) != "run_pytest":
                continue
            content = (getattr(message, "content", "") or "").lower()
            if content.startswith("error:"):
                return False
            success_markers = [" passed", "passed in", "no tests ran", "collected 0 items"]
            if any(marker in content for marker in success_markers):
                return True
            return False
        return False

    def _has_blocking_failure_after_last_edit(self, state: AgentState) -> bool:
        latest_edit_index = self._latest_successful_edit_index(state)
        if latest_edit_index is None:
            return False

        tool_messages = self._tool_messages(state)
        for message in tool_messages[latest_edit_index + 1 :]:
            content = (getattr(message, "content", "") or "").lower()
            if not content.startswith("error:"):
                continue
            tool_name = getattr(message, "name", None)
            if tool_name == "run_pytest" and "no module named pytest" in content:
                continue
            return True
        return False

    def _has_semantic_edit_success_signal(self, state: AgentState) -> tuple[bool, str]:
        if self._latest_successful_edit_index(state) is None:
            return False, ""
        if self._has_blocking_failure_after_last_edit(state):
            return False, ""

        issue_files = self._extract_issue_file_references(state.get("issue_description", ""))
        if not issue_files:
            return False, ""

        changed_files = self._extract_changed_files(state.get("repo_path", ""))
        if not changed_files:
            return False, ""

        changed_names = {Path(file_path).name for file_path in changed_files}
        matched_files: list[str] = []
        for issue_file in issue_files:
            normalized = issue_file.replace("\\", "/")
            issue_name = Path(normalized).name
            if normalized in changed_files or issue_name in changed_names:
                matched_files.append(normalized)

        if not matched_files:
            return False, ""

        return True, f"验证通过：已成功修改 issue 提到的文件 {', '.join(matched_files)}。"

    def _has_any_verification_evidence(self, state: AgentState) -> bool:
        if self._has_successful_test_signal(state):
            return True
        semantic_verified, _ = self._has_semantic_edit_success_signal(state)
        if semantic_verified:
            return True
        if self._latest_successful_edit_index(state) is not None and not self._has_blocking_failure_after_last_edit(state):
            return True
        return False

    def _issue_requirements_satisfied(self, state: AgentState) -> tuple[bool, str]:
        issue_description = state.get("issue_description", "")
        repo_path = state.get("repo_path", "")
        expected_files = self._extract_missing_file_requirements(issue_description)

        if expected_files:
            missing = [file_path for file_path in expected_files if not self._repo_contains_file(repo_path, file_path)]
            if missing:
                return False, f"验证未通过：仓库中仍缺少 {', '.join(missing)}。"
            return True, f"验证通过：仓库中已存在 {', '.join(expected_files)}。"

        if self._has_successful_test_signal(state):
            return True, "验证通过：检测到成功的测试信号。"

        semantic_verified, semantic_note = self._has_semantic_edit_success_signal(state)
        if semantic_verified:
            return True, semantic_note

        last_msg = state["messages"][-1]
        content = getattr(last_msg, "content", "") or ""
        if "TASK_SUCCESS" in content:
            if self._has_any_verification_evidence(state):
                return True, "验证通过：检测到 TASK_SUCCESS，且已有实际修改或测试作为佐证。"
            return False, "检测到 TASK_SUCCESS，但当前没有实际修改或测试成功的证据，不能判定为完成。"

        return False, "尚未识别到可自动验证的成功条件，请继续验证 issue 要求后再结束。"

    async def _node_verify(self, state: AgentState):
        verified, note = self._issue_requirements_satisfied(state)
        payload = {"trajectory": [{"type": "verification", "content": note}]}
        if verified:
            payload["status"] = "SUCCESS"
            return payload

        payload["status"] = "VERIFYING"
        payload["messages"] = [
            HumanMessage(
                content=(
                    f"{note}\n"
                    "请继续修改或检查仓库，并优先使用工具获取证据；确认满足 issue 要求后再输出 TASK_SUCCESS。"
                )
            )
        ]
        return payload

    def _route_react(self, state: AgentState) -> str:
        last_msg = state["messages"][-1]
        content = getattr(last_msg, "content", "") or ""

        if state["iteration_count"] >= state.get("max_iterations", 15):
            return "end_failed"

        if hasattr(last_msg, "tool_calls") and len(last_msg.tool_calls) > 0:
            return "continue_tools"

        if "TASK_SUCCESS" in content:
            return "verify"
        if "TASK_FAILED" in content:
            return "end_failed"
        if self._recent_successful_edit(state):
            return "verify"

        no_progress_turns = self._consecutive_non_tool_ai_turns(state)
        repeated_reply = self._last_two_ai_contents_match(state)
        reflection_count = self._reflection_count(state)

        if no_progress_turns >= 3:
            return "end_failed"
        if repeated_reply and reflection_count >= 2:
            return "end_failed"

        return "reflect"

    def _route_verify(self, state: AgentState) -> str:
        if state.get("status") == "SUCCESS":
            return "verified"
        return "retry"

    async def run_step(self, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            return event

    async def run_auto(self, thread_id: str, verbose: bool = False):
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            node_name = list(event.keys())[0]
            state = self.graph.get_state(config).values
            self._print_event(node_name, event[node_name], state=state, verbose=verbose)

        final_state = self.graph.get_state(config).values
        if final_state.get("status") == "FAILED":
            self._print_failure_diagnostics(final_state)
        return final_state

    async def raw_chat(self, user_input):
        return (await self.agent.chat(user_input)).content
