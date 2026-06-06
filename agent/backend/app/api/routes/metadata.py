from fastapi import APIRouter

from app.schemas.task import EvaluationMetadataResponse, ToolDescriptor

router = APIRouter()


@router.get("/evaluation-options", response_model=EvaluationMetadataResponse)
def get_evaluation_options() -> EvaluationMetadataResponse:
    return EvaluationMetadataResponse(
        modes=["auto"],
        methods=["规划", "ReAct", "工具调用", "失败反思"],
        dimensions=["结果", "流程", "工具", "验证", "性能"],
        builtin_metrics=[
            "success",
            "iteration_count",
            "tool_call_count",
            "file_edit_count",
            "test_run_count",
            "duration_seconds",
        ],
        strategy_templates=["自动求解", "重置后重跑"],
        builtin_tools=[
            ToolDescriptor(name="read_file", category="文件操作", summary="读取文件并返回带行号的内容"),
            ToolDescriptor(name="write_file", category="文件操作", summary="创建或覆盖文件"),
            ToolDescriptor(name="replace_in_file", category="文件操作", summary="精确文本替换"),
            ToolDescriptor(name="patch_file", category="文件操作", summary="按 SEARCH/REPLACE 块打补丁"),
            ToolDescriptor(name="search_code", category="代码搜索", summary="按正则搜索代码"),
            ToolDescriptor(name="list_files", category="代码搜索", summary="列出目录下文件"),
            ToolDescriptor(name="bash_terminal", category="命令执行", summary="执行 shell 命令"),
            ToolDescriptor(name="run_pytest", category="命令执行", summary="运行 pytest"),
            ToolDescriptor(name="git_clone_repo", category="Git 操作", summary="克隆远程仓库"),
            ToolDescriptor(name="git_status", category="Git 操作", summary="查看工作区状态"),
            ToolDescriptor(name="git_diff", category="Git 操作", summary="查看代码差异"),
            ToolDescriptor(name="current_repo_info", category="辅助工具", summary="读取助手根目录和当前仓库信息"),
        ],
        runtime_requirements=[
            "需要配置 OPENAI_API_KEY。",
            "如使用兼容网关，可额外配置 OPENAI_BASE_URL 与 MODEL_NAME。",
            "远程仓库克隆和 GitHub issue 解析依赖网络连通性。",
            "当前运行时因依赖全局 repo_root 与 cwd，只支持串行执行一个任务。",
        ],
    )
