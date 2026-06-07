FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY gitIssueAssitant ./gitIssueAssitant

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "gitIssueAssitant.RESTAPIAdapter.main:app", "--host", "0.0.0.0", "--port", "8000"]
