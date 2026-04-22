#!/usr/bin/env bash
set -euo pipefail

cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
python -m compileall app
