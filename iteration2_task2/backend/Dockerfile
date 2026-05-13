FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY data ./data

<<<<<<< HEAD
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

RUN pip install --no-cache-dir --upgrade pip \
        -i "${PIP_INDEX_URL}" \
        --trusted-host "${PIP_TRUSTED_HOST}" && \
    pip install --no-cache-dir . \
        -i "${PIP_INDEX_URL}" \
        --trusted-host "${PIP_TRUSTED_HOST}"
=======
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn .
>>>>>>> 3238cfc15c7913ff0dd17908b8d7c5ea6b30367d

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
