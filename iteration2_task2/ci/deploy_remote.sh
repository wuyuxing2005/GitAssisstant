#!/usr/bin/env sh
set -eu

# GitLab Runner side script. It opens SSH to the deploy host and streams
# ci/deploy.sh for execution on that host.

DEPLOY_HOST="${DEPLOY_HOST:-${SSH_HOST:-}}"
DEPLOY_USER="${DEPLOY_USER:-${SSH_USER:-}}"
DEPLOY_PASSWORD="${DEPLOY_PASSWORD:-${SSH_PASSWORD:-}}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DEPLOY_ENV="${DEPLOY_ENV:-staging}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/agent-eval}"
GIT_REPO_URL="${GIT_REPO_URL:-https://git.nju.edu.cn/2026seiii/2026seiii-045-1145.git}"
GIT_BRANCH="${GIT_BRANCH:-${CI_COMMIT_REF_NAME:-master}}"
IMAGE_TAG="${IMAGE_TAG:-${CI_COMMIT_SHORT_SHA:-latest}}"
FRONTEND_PORT="${FRONTEND_PORT:-80}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

if [ -z "$DEPLOY_HOST" ]; then
  echo "DEPLOY_HOST or SSH_HOST is required." >&2
  exit 1
fi

if [ -z "$DEPLOY_USER" ]; then
  echo "DEPLOY_USER or SSH_USER is required." >&2
  exit 1
fi

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
ssh-keyscan -p "$DEPLOY_PORT" -H "$DEPLOY_HOST" >> "$HOME/.ssh/known_hosts"

AUTH_MODE="password"
KEY_FILE=""
if [ -n "${DEPLOY_SSH_PRIVATE_KEY:-}" ]; then
  AUTH_MODE="key"
  KEY_FILE="$HOME/.ssh/deploy_key"
  printf '%s\n' "$DEPLOY_SSH_PRIVATE_KEY" | tr -d '\r' > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
elif [ -z "$DEPLOY_PASSWORD" ]; then
  echo "DEPLOY_SSH_PRIVATE_KEY or DEPLOY_PASSWORD/SSH_PASSWORD is required." >&2
  exit 1
fi

remote_ssh() {
  if [ "$AUTH_MODE" = "key" ]; then
    ssh -i "$KEY_FILE" -p "$DEPLOY_PORT" \
      -o IdentitiesOnly=yes \
      -o StrictHostKeyChecking=yes \
      "$DEPLOY_USER@$DEPLOY_HOST" "$@"
  else
    sshpass -p "$DEPLOY_PASSWORD" ssh -p "$DEPLOY_PORT" \
      -o StrictHostKeyChecking=yes \
      "$DEPLOY_USER@$DEPLOY_HOST" "$@"
  fi
}

echo "Deploying $GIT_REPO_URL branch $GIT_BRANCH to $DEPLOY_HOST:$DEPLOY_ROOT/$DEPLOY_ENV"

REMOTE_ENV="DEPLOY_ENV='$DEPLOY_ENV' DEPLOY_ROOT='$DEPLOY_ROOT' GIT_REPO_URL='$GIT_REPO_URL' GIT_BRANCH='$GIT_BRANCH' IMAGE_TAG='$IMAGE_TAG' FRONTEND_PORT='$FRONTEND_PORT' BACKEND_PORT='$BACKEND_PORT' POSTGRES_PORT='$POSTGRES_PORT'"

# shellcheck disable=SC2086
remote_ssh "$REMOTE_ENV sh -s" < ci/deploy.sh
