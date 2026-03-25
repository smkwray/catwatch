#!/usr/bin/env bash
set -euo pipefail

python -m venv "${HOME}/venvs/catwatch"
source "${HOME}/venvs/catwatch/bin/activate"
pip install -r requirements.txt
pip install -e '.[dev]'
cp -n .env.example .env || true

echo "Environment ready."
echo "Run: source ${HOME}/venvs/catwatch/bin/activate && make refresh && make site"
