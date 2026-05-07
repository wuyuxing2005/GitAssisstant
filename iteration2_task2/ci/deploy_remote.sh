#!/usr/bin/env bash
set -euo pipefail

DEPLOY_ENV="${1:-staging}"
TARGET_DEPLOY_PATH="${DEPLOY_PATH}/${DEPLOY_ENV}"

: "${SSH_KEY:?SSH_KEY is required}"
: "${SSH_USER:?SSH_USER is required}"
: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${SSH_USER}@${DEPLOY_HOST}" "mkdir -p ${TARGET_DEPLOY_PATH}"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no deploy/docker-compose.yml "${SSH_USER}@${DEPLOY_HOST}:${TARGET_DEPLOY_PATH}/docker-compose.yml"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no deploy/.env.example "${SSH_USER}@${DEPLOY_HOST}:${TARGET_DEPLOY_PATH}/.env.example"

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${SSH_USER}@${DEPLOY_HOST}" "
    cd ${TARGET_DEPLOY_PATH} &&
    [ -f .env ] || cp .env.example .env &&
    export IMAGE_TAG='${IMAGE_TAG}' FRONTEND_IMAGE='${FRONTEND_IMAGE}' BACKEND_IMAGE='${BACKEND_IMAGE}' &&
    docker compose pull &&
    docker compose up -d
"
