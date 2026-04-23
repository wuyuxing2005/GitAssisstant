当前 Web 页会通过现有 backend 真实驱动 `gitIssueAssitant`。

## 通信方式

```text
浏览器按钮
  -> fetch("http://127.0.0.1:8000/api/...")
  -> backend/app/services/evaluation_service.py
  -> gitIssueAssitant SessionManager / AgentOrchestrator
  -> 返回 task.result / timeline
  -> 前端轮询刷新
```

## 启动 backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

## 启动 frontend

新开终端：

```powershell
cd frontend
npm install
npm run dev
```

访问：

`http://localhost:5173/`

## 按钮对应关系

- 准备上下文：`POST /api/tasks`
- 单步运行：`POST /api/tasks/{task_id}/run`，请求体 `{"mode":"step"}`
- 自动求解：`POST /api/tasks/{task_id}/run`，请求体 `{"mode":"auto"}`
- 重置重跑：`POST /api/tasks/{task_id}/run`，请求体 `{"reset":true}`
- 刷新状态：`GET /api/tasks`
