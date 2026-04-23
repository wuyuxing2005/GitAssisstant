项目当前目录运行
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload --port 8000

新开终端运行
cd frontend
npm install
npm.cmd run dev

之后访问http://localhost:5173/