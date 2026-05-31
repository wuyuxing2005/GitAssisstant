# registry.py
"""
工具注册表模块 — 统一管理所有工具的元数据、硬禁用检查和调用事件记录。

职责（对应迭代三分工.md 第二组）：
  1. 为每个工具维护元数据：名称、分类、风险等级、是否默认启用、是否需要确认、参数约束
  2. 硬禁用：即使 Agent 幻觉调用了禁用工具，也必须拒绝执行
  3. 每次工具调用产生结构化 ToolCallEvent，供第一组汇总 AgentTrace、供第三组展示
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ==================== 枚举定义 ====================

class ToolCategory(str, Enum):
    """工具分类，对应分工.md 3.2.1 的 category 字段"""
    FILE = "file"            # 文件读写操作
    CODE_SEARCH = "code_search"   # 代码搜索
    SHELL = "shell"          # Shell 命令执行
    TEST = "test"            # 测试执行
    GIT = "git"              # Git 操作
    INFO = "info"            # 信息查询（只读）


class RiskLevel(str, Enum):
    """工具风险等级，对应分工.md 3.2.1 的 risk_level 字段"""
    READ = "read"            # 只读操作 — 最低风险
    MODIFY = "modify"        # 修改文件内容
    DESTRUCTIVE = "destructive"   # 可能破坏数据（当前未使用，预留）
    NETWORK = "network"      # 涉及网络访问
    EXECUTE = "execute"      # 任意命令执行 — 最高风险


# ==================== 数据类 ====================

@dataclass
class ToolMeta:
    """单个工具的元数据，对应分工.md 3.2.1 的注册表字段。

    字段说明：
      - name: 工具名称（与 @tool 装饰器中的 name 一致）
      - description: 工具说明（给 LLM 看）
      - category: 工具分类
      - risk_level: 风险等级
      - enabled_by_default: 是否默认启用
      - requires_confirmation: 是否需要用户确认后才能执行
      - sandbox_routed: True 表示该工具的 shell 命令需要经 Docker 沙箱执行
      - args_schema: JSON Schema 格式的参数约束（预留，当前未强制校验）
    """
    name: str
    description: str
    category: ToolCategory
    risk_level: RiskLevel
    enabled_by_default: bool = True
    requires_confirmation: bool = False
    sandbox_routed: bool = False
    args_schema: dict = field(default_factory=dict)


@dataclass
class ToolCallEvent:
    """单次工具调用的完整记录，对应分工.md 3.2.6 的全部字段。

    这些事件会：
      - 提供给第一组，由第一组汇总进标准 AgentTrace
      - 提供给第三组，用于工具调用记录展示和过程指标计算
    """
    tool_name: str
    arguments: dict
    status: str                     # "success" | "error" | "rejected"
    result_preview: str = ""        # 结果预览（截断至前 300 字符）
    error_message: str = ""         # 错误信息（status="error" 或 "rejected" 时）
    latency_ms: int = 0             # 执行耗时（毫秒）
    timestamp: str = ""             # ISO-8601 格式时间戳
    sandbox_id: str = ""            # 沙箱容器标识（无沙箱时为空）
    affected_files: list = field(default_factory=list)   # 受影响的文件路径列表
    exit_code: int = 0              # 命令退出码（shell 工具使用）

    def __post_init__(self):
        """自动填充时间戳（若未提供）。"""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转为可序列化的字典，供 AgentState.tool_call_events 存储。"""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.status,
            "result_preview": self.result_preview,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "sandbox_id": self.sandbox_id,
            "affected_files": self.affected_files,
            "exit_code": self.exit_code,
        }


# ==================== ToolRegistry ====================

class ToolRegistry:
    """统一工具注册表，提供元数据管理、硬禁用检查和事件记录。

    使用方式：
        registry = ToolRegistry()
        registry.register_all(AGENT_TOOLS_ALL)
        registry.hard_disable("git_push")   # 硬禁用推送工具

        # 在工具执行节点中使用
        rejection = registry.check_invocation("bash_terminal", {"command": "rm -rf /"})
        if rejection:
            return ToolMessage(content=rejection, ...)

        event = ToolCallEvent(tool_name="read_file", ...)
        registry.record_event(event)
    """

    def __init__(self):
        # 工具名 → (工具函数, ToolMeta)
        self._tools: Dict[str, tuple[Callable, ToolMeta]] = {}
        # 硬禁用集合 — 即使 Agent 幻觉调用了这些工具，也必须拒绝
        self._hard_disabled: set[str] = set()
        # 事件缓冲区 — 每次工具调用后追加，供外部轮询消费
        self._events: List[ToolCallEvent] = []

    # ---------- 注册 ----------

    def register(self, tool_func: Callable, meta: ToolMeta) -> None:
        """注册单个工具及其元数据。

        :param tool_func: LangChain @tool 装饰后的工具函数
        :param meta: 工具的元数据
        """
        self._tools[meta.name] = (tool_func, meta)

    def register_all(self, tools: list[Callable]) -> None:
        """批量注册工具。工具的元数据通过内部映射表分配。

        :param tools: 工具函数列表（如 AGENT_TOOLS_ALL）
        """
        for tool_func in tools:
            name = getattr(tool_func, "name", None) or getattr(tool_func, "__name__", "")
            if name in self._tools:
                continue  # 已注册，跳过
            meta = self._infer_meta(name, tool_func)
            self._tools[name] = (tool_func, meta)

    # ---------- 硬禁用 ----------

    def hard_disable(self, name: str) -> None:
        """硬禁用指定工具。禁用后即使 Agent 调用也会在 check_invocation 中被拒绝。

        这是最终安全边界（对应分工.md 3.2.1 的"硬禁用是最终安全边界"）。
        """
        self._hard_disabled.add(name)

    def hard_enable(self, name: str) -> None:
        """取消硬禁用。"""
        self._hard_disabled.discard(name)

    def is_hard_disabled(self, name: str) -> bool:
        """检查工具是否被硬禁用。"""
        return name in self._hard_disabled

    # ---------- 调用前检查 ----------

    def check_invocation(self, tool_name: str, tool_args: dict) -> Optional[str]:
        """执行前检查，返回 None 表示放行，返回字符串表示拒绝理由。

        检查顺序（对应分工.md 3.2.1 的全部五项）：
          1. 工具是否已注册？
          2. 当前任务是否启用该工具（硬禁用检查）？
          3. 参数是否合法（必要参数是否存在）？
          4. 路径是否位于沙箱仓库内（文件工具）？
          5. 是否触发危险命令规则（shell 工具）？

        :param tool_name: 工具名称
        :param tool_args: 工具参数
        :return: None 表示允许执行；字符串表示拒绝原因
        """
        # 1. 检查是否已注册
        if tool_name not in self._tools:
            return f"工具 '{tool_name}' 未在 ToolRegistry 中注册，拒绝执行。"

        # 2. 硬禁用检查（最终安全边界）
        if self.is_hard_disabled(tool_name):
            return (
                f"工具 '{tool_name}' 已被硬禁用。"
                "即使 Agent 计划使用该工具，也无法执行。请联系管理员或修改任务配置。"
            )

        meta = self._tools[tool_name][1]

        # 3. 参数合法性校验 — 检查必要参数是否存在
        args_error = self._validate_args(meta, tool_args)
        if args_error:
            return args_error

        # 4. 路径越界检查 — 文件工具的参数必须指向仓库内路径
        path_error = self._check_path_confinement(meta, tool_args)
        if path_error:
            return path_error

        # 5. 危险命令检测 — shell 工具的黑名单模式匹配
        danger_error = self._detect_dangerous(meta, tool_args)
        if danger_error:
            return danger_error

        return None  # 放行

    # ---------- 子检查方法 ----------

    # 文件类工具的路径参数名
    _FILE_PATH_ARGS = {"file_path", "path", "search_path", "working_dir", "repo_path", "target_dir"}

    # 危险命令正则模式（对应分工.md 3.2.1 "是否触发危险命令规则"）
    _DANGEROUS_PATTERNS: list = [
        # 递归删除根目录/家目录
        (re.compile(r"\brm\s+-rf\s+(/|/\*|~)\b"), "禁止递归删除根目录或家目录"),
        # 格式化磁盘
        (re.compile(r"\bmkfs\.\w+"), "禁止格式化磁盘操作"),
        # 直接读写块设备
        (re.compile(r"\bdd\s+if="), "禁止直接操作块设备"),
        (re.compile(r"\bdd\s+of=/dev/"), "禁止写入块设备"),
        (re.compile(r">\s*/dev/sd[a-z]"), "禁止重定向到块设备"),
        # fork 炸弹
        (re.compile(r":\(\)\s*\{.*:\|:.*\};?\s*:"), "检测到 fork 炸弹模式"),
        # 全局可写权限
        (re.compile(r"\bchmod\s+777\s+/"), "禁止对根路径设置 777 权限"),
        # 管道到 shell 执行（远程代码执行风险）
        (re.compile(r"\b(curl|wget)\s+.*\|\s*(ba)?sh\b"), "禁止从网络下载后直接管道到 shell"),
        # 覆写系统配置
        (re.compile(r">\s*/etc/"), "禁止覆写系统配置文件"),
        # 提权操作
        (re.compile(r"\bsudo\b"), "禁止使用 sudo 提权"),
    ]

    def _validate_args(self, meta: ToolMeta, tool_args: dict) -> Optional[str]:
        """检查必要参数是否存在。对 SHELL 类工具额外检查 command 非空。

        :param meta: 工具元数据
        :param tool_args: 调用参数
        :return: None 表示参数合法，str 表示错误信息
        """
        # shell 工具必须有非空 command 参数
        if meta.category == ToolCategory.SHELL:
            command = tool_args.get("command", "")
            if not command or not str(command).strip():
                return f"工具 '{meta.name}' 缺少必要参数 'command' 或参数为空，拒绝执行。"

        # 文件写入工具必须有非空 file_path 和 content
        if meta.category == ToolCategory.FILE and meta.risk_level == RiskLevel.MODIFY:
            file_path = tool_args.get("file_path", "")
            if not file_path or not str(file_path).strip():
                return f"工具 '{meta.name}' 缺少必要参数 'file_path' 或参数为空，拒绝执行。"

        return None

    def _check_path_confinement(self, meta: ToolMeta, tool_args: dict) -> Optional[str]:
        """检查文件工具的路径参数是否可能越界。

        检查策略：拒绝包含路径穿越特征（../ 向上跳出）的路径。
        注意：最终路径解析由 tools.py 的 _resolve_workspace_path() 完成，
        此处的检查是提前拦截明显的越界尝试。

        :param meta: 工具元数据
        :param tool_args: 调用参数
        :return: None 表示放行，str 表示拒绝原因
        """
        if meta.category not in (ToolCategory.FILE, ToolCategory.CODE_SEARCH):
            return None

        for arg_name in self._FILE_PATH_ARGS:
            value = tool_args.get(arg_name, "")
            if not value or not isinstance(value, str):
                continue
            value = value.strip()
            # 检测路径穿越特征
            if value.startswith("/") and meta.category == ToolCategory.FILE:
                # 绝对路径可能是合理的（如 /workspace/repo/src/main.py），
                # 但纯 Linux 绝对路径在 Windows 宿主上不适用，仅记录警告
                pass
            # 检测连续的上层引用（../../..）
            if value.count("../") >= 3:
                return (
                    f"工具 '{meta.name}' 的参数 '{arg_name}' 疑似路径穿越 ({value})，"
                    "拒绝执行。请使用仓库内相对路径。"
                )

        return None

    def _detect_dangerous(self, meta: ToolMeta, tool_args: dict) -> Optional[str]:
        """检测 shell 命令中是否包含危险模式。

        仅对 SHELL 和 TEST 分类的工具进行检查。
        对 bash_terminal 的 command 参数进行正则匹配。

        :param meta: 工具元数据
        :param tool_args: 调用参数
        :return: None 表示安全，str 表示检测到的危险及原因
        """
        if meta.category not in (ToolCategory.SHELL, ToolCategory.TEST):
            return None

        # 检查命令类参数
        for arg_name in ("command", "pytest_args"):
            command = tool_args.get(arg_name, "")
            if not command or not isinstance(command, str):
                continue
            command = str(command).strip()
            if not command:
                continue
            for pattern, reason in self._DANGEROUS_PATTERNS:
                if pattern.search(command):
                    return (
                        f"工具 '{meta.name}' 的命令包含危险操作: {reason}。\n"
                        f"匹配的命令片段: {pattern.search(command).group()[:60]}\n"
                        "该操作已被拦截，请使用更安全的替代方案。"
                    )

        return None

    # ---------- 事件记录 ----------

    def record_event(self, event: ToolCallEvent) -> None:
        """记录一次工具调用事件到内部缓冲区。

        事件会同时追加到缓冲区，供第一组和第三组消费。
        """
        self._events.append(event)

    def get_events(self, clear: bool = False) -> List[ToolCallEvent]:
        """获取所有已记录的工具调用事件。

        :param clear: True 时清空缓冲区
        :return: 事件列表（按调用时间排序）
        """
        events = list(self._events)
        if clear:
            self._events.clear()
        return events

    # ---------- 查询 ----------

    def get_tool(self, name: str) -> Optional[Callable]:
        """根据名称获取工具函数。"""
        entry = self._tools.get(name)
        return entry[0] if entry else None

    def get_meta(self, name: str) -> Optional[ToolMeta]:
        """根据名称获取工具元数据。"""
        entry = self._tools.get(name)
        return entry[1] if entry else None

    def get_all_meta(self) -> Dict[str, ToolMeta]:
        """获取所有已注册工具的元数据（不含硬禁用的工具）。"""
        return {
            name: meta
            for name, (_, meta) in self._tools.items()
            if name not in self._hard_disabled
        }

    def list_enabled_descriptions(self) -> str:
        """生成给 LLM 看的工具描述列表（排除硬禁用的工具）。

        返回格式：
            - tool_name: description（分类: xxx, 风险: xxx）
        """
        lines = []
        for name, (_, meta) in self._tools.items():
            if name in self._hard_disabled:
                continue
            lines.append(
                f"- {name}: {meta.description}"
                f"（分类: {meta.category.value}, 风险: {meta.risk_level.value}）"
            )
        return "\n".join(lines) if lines else "（无可用工具）"

    # ---------- 内部方法 ----------

    def _infer_meta(self, name: str, tool_func: Callable) -> ToolMeta:
        """根据工具名称推断元数据（用于 register_all 的默认分配）。

        如果工具名不在预定义映射中，使用保守的默认值（最高风险、需要确认）。
        """
        description = getattr(tool_func, "description", "") or ""
        # 去掉 docstring 中多余的空白，取第一行作为简短描述
        if description:
            description = " ".join(description.split())[:200]

        return DEFAULT_TOOL_META_MAP.get(name, ToolMeta(
            name=name,
            description=description or "未分类工具",
            category=ToolCategory.SHELL,
            risk_level=RiskLevel.EXECUTE,
            enabled_by_default=False,
            requires_confirmation=True,
            sandbox_routed=True,
        ))


# ==================== 默认工具元数据映射 ====================
# 对应分工.md 3.2.1 的要求，每个工具维护完整的元数据。
# 在 setup_default_registry() 中通过 register_all() 使用此映射。

DEFAULT_TOOL_META_MAP: Dict[str, ToolMeta] = {
    # ---- 文件读取 ----
    "read_file": ToolMeta(
        name="read_file",
        description="读取工作区文件内容（带行号），支持指定行范围",
        category=ToolCategory.FILE,
        risk_level=RiskLevel.READ,
    ),
    "list_files": ToolMeta(
        name="list_files",
        description="列出工作区文件，支持递归和 glob 过滤",
        category=ToolCategory.FILE,
        risk_level=RiskLevel.READ,
    ),

    # ---- 代码搜索 ----
    "search_code": ToolMeta(
        name="search_code",
        description="通过正则表达式搜索代码内容",
        category=ToolCategory.CODE_SEARCH,
        risk_level=RiskLevel.READ,
    ),

    # ---- 文件修改 ----
    "write_file": ToolMeta(
        name="write_file",
        description="创建或覆盖工作区文件",
        category=ToolCategory.FILE,
        risk_level=RiskLevel.MODIFY,
        requires_confirmation=True,
    ),
    "replace_in_file": ToolMeta(
        name="replace_in_file",
        description="精确替换文件中的文本（拒绝模糊匹配）",
        category=ToolCategory.FILE,
        risk_level=RiskLevel.MODIFY,
        requires_confirmation=True,
    ),
    "patch_file": ToolMeta(
        name="patch_file",
        description="应用 SEARCH/REPLACE 格式的 patch 到文件",
        category=ToolCategory.FILE,
        risk_level=RiskLevel.MODIFY,
        requires_confirmation=True,
    ),

    # ---- Shell 命令 ----
    "bash_terminal": ToolMeta(
        name="bash_terminal",
        description="在仓库工作区中运行 Shell 命令（构建、脚本、诊断等）",
        category=ToolCategory.SHELL,
        risk_level=RiskLevel.EXECUTE,
        requires_confirmation=True,
        sandbox_routed=True,   # 经 Docker 沙箱执行
    ),

    # ---- 测试 ----
    "run_pytest": ToolMeta(
        name="run_pytest",
        description="在仓库中运行 pytest 并返回测试输出",
        category=ToolCategory.TEST,
        risk_level=RiskLevel.EXECUTE,
        sandbox_routed=True,   # 测试在沙箱中执行，避免污染宿主环境
    ),

    # ---- Git 只读 ----
    "git_status": ToolMeta(
        name="git_status",
        description="查看仓库的 git status（--short 格式）",
        category=ToolCategory.GIT,
        risk_level=RiskLevel.READ,
    ),
    "git_diff": ToolMeta(
        name="git_diff",
        description="查看仓库的 git diff（含未跟踪文件）",
        category=ToolCategory.GIT,
        risk_level=RiskLevel.READ,
    ),

    # ---- Git 写操作 ----
    "git_clone_repo": ToolMeta(
        name="git_clone_repo",
        description="克隆 Git 仓库到本地工作区",
        category=ToolCategory.GIT,
        risk_level=RiskLevel.NETWORK,
        requires_confirmation=True,
        sandbox_routed=True,
    ),
    "git_add": ToolMeta(
        name="git_add",
        description="将文件添加到暂存区",
        category=ToolCategory.GIT,
        risk_level=RiskLevel.MODIFY,
        requires_confirmation=True,
    ),
    "git_commit": ToolMeta(
        name="git_commit",
        description="提交暂存的更改（含 commit message）",
        category=ToolCategory.GIT,
        risk_level=RiskLevel.MODIFY,
        requires_confirmation=True,
    ),
    "git_push": ToolMeta(
        name="git_push",
        description="推送本地提交到远程仓库（高风险！Agent 默认不可调用）",
        category=ToolCategory.GIT,
        risk_level=RiskLevel.NETWORK,
        requires_confirmation=True,
        sandbox_routed=True,
    ),

    # ---- 信息查询 ----
    "current_repo_info": ToolMeta(
        name="current_repo_info",
        description="返回当前仓库根路径和 assistant 根路径",
        category=ToolCategory.INFO,
        risk_level=RiskLevel.READ,
    ),
}


# ==================== 工厂函数 ====================

def setup_default_registry(tools: list) -> ToolRegistry:
    """创建 ToolRegistry 并预注册所有工具，自动分配默认元数据。

    使用方式：
        from .tools.tools import AGENT_TOOLS_ALL
        registry = setup_default_registry(AGENT_TOOLS_ALL)
        registry.hard_disable("git_push")  # Agent 不可推送

    :param tools: 工具函数列表
    :return: 已注册所有工具的 ToolRegistry 实例
    """
    registry = ToolRegistry()
    registry.register_all(tools)
    return registry
