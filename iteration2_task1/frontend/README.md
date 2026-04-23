# GitIssueAssitant Web 操控台

## 说明

这个前端现在是 **真实驱动 Agent 的 Web 操控台**：

- 前端按钮调用现有 FastAPI backend
- backend 调用 `gitIssueAssitant` 的 `SessionManager` 和 `AgentOrchestrator`
- 页面负责收集仓库、Issue、模型和模式
- 页面展示运行状态、轨迹和结果
- 页面保留 CLI 指令作为兜底执行方式

通信链路：

```text
Frontend button
  -> HTTP /api/tasks
  -> backend EvaluationService
  -> gitIssueAssitant AgentOrchestrator
  -> task result / timeline
  -> frontend polling refresh
```

## 启动

先启动 backend：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

再启动 frontend：

```powershell
cd frontend
npm install
npm run dev
```

打开浏览器访问 `http://localhost:5173/`。

## 后续可选增强

- 增加 WebSocket 实时日志流，替代轮询
- 增加停止 / 暂停 endpoint
- 增加任务编辑和历史筛选
