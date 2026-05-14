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
