#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

export PATH="${UV_PROJECT_ENVIRONMENT:-$HOME/venvs/catwatch}/bin:$PATH"

offenders=()

while IFS= read -r path; do
  [[ -n "${path}" ]] || continue
  offenders+=("${path}")
done < <(
  find "$ROOT_DIR" \
    \( -path "$ROOT_DIR/.git" -o -path "$ROOT_DIR/.git/*" \) -prune -o \
    \( -type d \
        \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".ruff_cache" -o -name ".mypy_cache" -o -name ".cache" -o -name "venv" -o -name ".venv" -o -name "env" -o -name "*.egg-info" -o -name ".___pycache__" \) \
      -o -type f \( -name "._*" -o -name ".___pycache__" \) \
      -o -type d \( -name "._*" -o -name "*.egg-info" \) \
      -o -type f \( -name "*.egg-info" \) \
    \) -print
)

if ((${#offenders[@]} > 0)); then
  printf 'Repo hygiene check failed. Remove these paths before proceeding:\n' >&2
  printf '  - %s\n' "${offenders[@]}" | LC_ALL=C sort -u >&2
  exit 1
fi

printf 'Repo hygiene check passed: no prohibited env/cache/artifact paths found.\n'
