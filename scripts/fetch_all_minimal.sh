#!/usr/bin/env bash
set -euo pipefail

python -m opencatwatch fetch-bsx
python -m opencatwatch fetch-bma
python -m opencatwatch fetch-sec --sponsors-csv seeds/sponsor_universe_template.csv
python -m opencatwatch fetch-nws
python -m opencatwatch fetch-usgs --days 14 --min-magnitude 5.5
python -m opencatwatch fetch-ibtracs --kind active
python -m opencatwatch fetch-fema
python -m opencatwatch fetch-stormevents --year-start 2024 --year-end 2025
python -m opencatwatch build-registry
python -m opencatwatch build-watchlist
python -m opencatwatch build-site
python -m opencatwatch audit-data
python -m opencatwatch build-review-queue
