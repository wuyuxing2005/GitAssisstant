#!/usr/bin/env bash
set -euo pipefail

# ============================================
# 部署脚本 — 在阿里云服务器上执行
# 从 NJU GitLab Registry 拉取镜像并启动
# ============================================

COMPOSE_DIR="/opt/agent-eval/iteration2_task2/deploy"

cd "$COMPOSE_DIR"

echo "=== 拉取最新镜像 ==="
docker compose -f docker-compose.yml pull

echo "=== 启动服务 ==="
docker compose -f docker-compose.yml up -d

echo "=== 清理旧镜像 ==="
docker image prune -f

echo "=== 部署完成 ==="
docker compose -f docker-compose.yml ps
