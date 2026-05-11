#!/usr/bin/env bash
set -euo pipefail

cd backend
python3 -m compileall app
