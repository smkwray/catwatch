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
  "pyproject.toml"
  "Makefile"
  "reports/data_audit.md"
  "reports/data_audit.json"
  "apps/site/data/dashboard.json"
  "data/manual/review_queue.csv"
  "data/manual/sponsor_aliases.csv"
  "data/manual/tranche_overrides.csv"
  "data/processed/bsx/company_records.jsonl"
  "data/processed/bma/entity_matches.jsonl"
  "data/processed/bma/entity_review_candidates.jsonl"
  "data/processed/sec/scan_manifest.json"
  "data/processed/sec/sponsor_spv_links.jsonl"
  "data/processed/registry/tranches.jsonl"
  "data/processed/watchlist/events.jsonl"
  "data/processed/watchlist/matches.jsonl"
  "src/opencatwatch/config.py"
  "src/opencatwatch/cli.py"
  "src/opencatwatch/matching/rules.py"
  "src/opencatwatch/pipelines/registry.py"
  "src/opencatwatch/pipelines/watchlist.py"
  "src/opencatwatch/pipelines/site_data.py"
  "src/opencatwatch/pipelines/quality.py"
  "src/opencatwatch/sources/bsx.py"
  "src/opencatwatch/sources/bma.py"
  "src/opencatwatch/sources/sec.py"
  "src/opencatwatch/sources/nws.py"
  "src/opencatwatch/sources/usgs.py"
  "src/opencatwatch/sources/noaa_stormevents.py"
  "src/opencatwatch/sources/ibtracs.py"
  "src/opencatwatch/sources/openfema.py"
  "tests/test_high_impact_repairs.py"
  "tests/test_quality.py"
  "tests/test_source_fetchers.py"
  "tests/test_matching_rules.py"
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
