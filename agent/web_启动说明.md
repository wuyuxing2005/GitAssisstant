项目当前目录运行
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
uvicorn gitIssueAssitant.RESTAPIAdapter.main:app --reload --port 8000

新开终端运行
cd frontend
npm install
npm.cmd run dev
