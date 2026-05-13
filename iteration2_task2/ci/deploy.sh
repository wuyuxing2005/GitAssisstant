<<<<<<< HEAD
#!/usr/bin/env sh
set -eu

# Remote host side script. It updates the mirrored repository, builds local
# Docker images, applies docker-compose.yml, and verifies the deployed service.

DEPLOY_ENV="${DEPLOY_ENV:-staging}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/agent-eval}"
GIT_REPO_URL="${GIT_REPO_URL:-https://git.nju.edu.cn/2026seiii/2026seiii-045-1145.git}"
GIT_BRANCH="${GIT_BRANCH:-master}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
FRONTEND_PORT="${FRONTEND_PORT:-80}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

PROJECT_DIR="iteration2_task2"
REPO_DIR="$DEPLOY_ROOT/repo"
RUNTIME_DIR="$DEPLOY_ROOT/$DEPLOY_ENV"
SAFE_ENV=$(printf '%s' "$DEPLOY_ENV" | tr -c 'A-Za-z0-9_-' '-')
BACKEND_IMAGE="agent-eval-backend:$IMAGE_TAG"
FRONTEND_IMAGE="agent-eval-frontend:$IMAGE_TAG"
COMPOSE_PROJECT_NAME="agent-eval-$SAFE_ENV"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command on deploy host: $1" >&2
    exit 1
  fi
}

require_command git
require_command docker

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required on deploy host." >&2
  exit 1
fi

mkdir -p "$DEPLOY_ROOT" "$RUNTIME_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "Cloning mirrored repository: $GIT_REPO_URL"
  git clone --branch "$GIT_BRANCH" "$GIT_REPO_URL" "$REPO_DIR"
fi

echo "Updating repository branch: $GIT_BRANCH"
cd "$REPO_DIR"
git remote set-url origin "$GIT_REPO_URL"
git fetch --prune origin "$GIT_BRANCH"
git checkout -B "$GIT_BRANCH" FETCH_HEAD
git reset --hard FETCH_HEAD

echo "Preparing runtime directory: $RUNTIME_DIR"
cp "$REPO_DIR/$PROJECT_DIR/deploy/docker-compose.yml" "$RUNTIME_DIR/docker-compose.yml"
cp "$REPO_DIR/$PROJECT_DIR/deploy/.env.example" "$RUNTIME_DIR/.env.example"

if [ ! -f "$RUNTIME_DIR/.env" ]; then
  cp "$RUNTIME_DIR/.env.example" "$RUNTIME_DIR/.env"
  echo "Created $RUNTIME_DIR/.env from .env.example. Fill API keys there when enabling real LLM judging."
fi

cat > "$RUNTIME_DIR/.deploy.env" <<EOF
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME
BACKEND_IMAGE=$BACKEND_IMAGE
FRONTEND_IMAGE=$FRONTEND_IMAGE
FRONTEND_PORT=$FRONTEND_PORT
BACKEND_PORT=$BACKEND_PORT
POSTGRES_PORT=$POSTGRES_PORT
EOF

echo "Building backend image: $BACKEND_IMAGE"
docker build \
  --build-arg PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
  --build-arg PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}" \
  -t "$BACKEND_IMAGE" \
  "$REPO_DIR/$PROJECT_DIR/backend"

echo "Building frontend image: $FRONTEND_IMAGE"
docker build \
  --build-arg NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}" \
  -t "$FRONTEND_IMAGE" \
  "$REPO_DIR/$PROJECT_DIR/frontend"

echo "Starting services with Docker Compose"
cd "$RUNTIME_DIR"
docker compose --env-file .deploy.env up -d --remove-orphans

echo "Waiting for backend health"
attempt=1
while [ "$attempt" -le 30 ]; do
  if docker compose --env-file .deploy.env exec -T backend \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" >/dev/null 2>&1; then
    echo "Backend health check passed."
    break
  fi

  if [ "$attempt" -eq 30 ]; then
    echo "Backend health check failed." >&2
    docker compose --env-file .deploy.env logs --tail=120 backend postgres redis worker >&2
    exit 1
  fi

  attempt=$((attempt + 1))
  sleep 2
done

echo "Waiting for frontend health"
attempt=1
while [ "$attempt" -le 20 ]; do
  if docker compose --env-file .deploy.env exec -T frontend \
    wget -q -O - http://127.0.0.1/ >/dev/null 2>&1; then
    echo "Frontend health check passed."
    break
  fi

  if [ "$attempt" -eq 20 ]; then
    echo "Frontend health check failed." >&2
    docker compose --env-file .deploy.env logs --tail=120 frontend >&2
    exit 1
  fi

  attempt=$((attempt + 1))
  sleep 2
done

echo "Deployment completed."
docker compose --env-file .deploy.env ps
docker image prune -f >/dev/null
=======
#!/usr/bin/env bash
set -euo pipefail

# ============================================
# 部署脚本 — 在阿里云服务器上执行
# ============================================

PROJECT_DIR="/opt/agent-eval"

BRANCH="${GIT_BRANCH:-master}"

echo "=== 拉取最新代码（分支：$BRANCH） ==="
cd "$PROJECT_DIR"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

echo "=== 构建后端镜像 ==="
docker build -t agent-eval-backend:latest "$PROJECT_DIR/iteration2_task2/backend"

echo "=== 构建前端镜像 ==="
docker build -t agent-eval-frontend:latest "$PROJECT_DIR/iteration2_task2/frontend"

echo "=== 启动服务 ==="
cd "$PROJECT_DIR/iteration2_task2/deploy"
docker compose -f docker-compose.yml up -d

echo "=== 清理旧镜像 ==="
docker image prune -f

echo "=== 部署完成 ==="
docker compose -f docker-compose.yml ps
>>>>>>> 3238cfc15c7913ff0dd17908b8d7c5ea6b30367d
