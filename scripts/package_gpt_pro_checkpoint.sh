#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${ROOT_DIR}/reports/checkpoints"
OUT_FILE="${OUT_DIR}/gpt_pro_checkpoint_${STAMP}.zip"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

mkdir -p "${OUT_DIR}"

INCLUDE_PATHS=(
  "docs"
  "catalog/sources.yml"
  "do/gpt_pro_checkpoint_prompt.md"
  "reports/data_audit.md"
  "apps/site/data/dashboard.json"
  "data/manual/review_queue.csv"
  "data/manual/sponsor_aliases.csv"
  "data/manual/tranche_overrides.csv"
  "data/processed/bsx/company_records.jsonl"
  "data/processed/bma/entity_matches.jsonl"
  "data/processed/sec/sponsor_spv_links.jsonl"
  "data/processed/registry/tranches.jsonl"
)

cd "${ROOT_DIR}"

echo "Checkpoint contents:"
for path in "${INCLUDE_PATHS[@]}"; do
  if [[ -e "${path}" ]]; then
    echo "  ${path}"
  else
    echo "  MISSING ${path}" >&2
  fi
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo
  echo "Dry run only. Zip not created."
  exit 0
fi

zip -r "${OUT_FILE}" "${INCLUDE_PATHS[@]}" >/dev/null

echo
echo "Created ${OUT_FILE}"
