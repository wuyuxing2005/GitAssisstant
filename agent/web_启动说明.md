项目当前目录运行
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
uvicorn gitIssueAssitant.RESTAPIAdapter.main:app --reload --reload-dir gitIssueAssitant --port 8000

注意：不要让 uvicorn reload 监听整个项目根目录。Agent 本地执行时会修改 repos/ 下的目标仓库，
如果使用默认的 `--reload` 监听根目录，后端会被这些文件变更重启，导致 Web 端看到任务一直运行。

新开终端运行
cd frontend
npm install
npm.cmd run dev
