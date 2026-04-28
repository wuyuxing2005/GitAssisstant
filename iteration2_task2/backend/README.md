# Agent Evaluation Platform Backend

## Stack

- FastAPI
- Pydantic v2
- PostgreSQL + SQLAlchemy 2
- Ragas integration entrypoint

## Capabilities

- Evaluation task CRUD
- Task status management
- Metadata endpoint for modes / methods / dimensions / metrics / strategies
- Single-run result query and multi-task comparison
- PostgreSQL persistence for tasks and evaluation results
- Optional Ragas execution hook

## Local Run

```bash
  cd deploy
  docker compose up -d postgres

  cd backend
  python -m venv .venv
  .venv\Scripts\activate
  pip install -e .
  copy .env.example .env
  uvicorn app.main:app --reload --port 8000
```

## Environment Variables

- `AGENT_EVAL_DATABASE_URL`: PostgreSQL DSN
- `AGENT_EVAL_RAGAS_ENABLED`: `true` to enable real Ragas execution
- `AGENT_EVAL_RAGAS_DATASET_DIR`: JSONL dataset directory
- `AGENT_EVAL_RAGAS_LLM_MODEL`: evaluator LLM model name
- `AGENT_EVAL_RAGAS_EMBEDDING_MODEL`: evaluator embedding model name

## Ragas Dataset Convention

Store datasets under `backend/data/eval_datasets/<dataset>.jsonl`.

Recommended JSONL fields for result-oriented evaluation:

- `user_input`
- `response`
- `reference`
- `retrieved_contexts`

Recommended extra fields for process/tool evaluation:

- `reference_tool_calls`
- `tool_calls`
- `rubrics`
