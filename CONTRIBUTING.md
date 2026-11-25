# Contributing

OpenCatWatch is intentionally conservative. Contributions should improve public evidence quality, reproducibility, or clarity without introducing unsupported claims.

This is an initial public release, not a finished data product. Favor improvements that increase defensibility, transparency, and rebuildability before chasing long-tail completeness.

## Ground Rules

- Keep the project evidence-first.
- Do not add sponsor aliases or tranche overrides without both `source_url` and `notes`.
- Do not claim confirmed triggers or losses from coarse public event overlap alone.
- Prefer normalized facts plus source links over copied source text.
- Keep CI deterministic. Do not add live-source fetches to GitHub Actions.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e '.[dev]'
cp .env.example .env
export OPENCATWATCH_USER_AGENT="OpenCatWatch/0.1 (contact contact@example.com)"
```

Use a real contact URL or email before any live fetch. The default placeholder is intentionally invalid for network use.

## Before Opening A PR

Run:

```bash
make lint
make test
make release-check
```

`make release-check` is the public-snapshot gate. It verifies lint, tests, rebuilds the local snapshot, regenerates the audit, and fails if the release thresholds are not met.

## Data And Evidence Policy

- Raw downloads belong in `data/raw/` and stay untracked.
- Normalized rebuild artifacts belong in `data/processed/` and stay untracked.
- Manual evidence tables in `data/manual/` are tracked.
- Public artifacts in `apps/site/data/` and `reports/` are tracked.
- Local operational files like `data/manual/review_queue.csv` are generated for triage but are not intended for the public repo.
- When inference is involved, keep the language coarse and explain the rule or evidence source in notes.

## Tests

- Add or update tests whenever parser logic, matching logic, audit logic, or manual-evidence validation changes.
- Prefer fixture-based tests and local sample payloads over network-dependent tests.
- If a live source changes shape, add a reduced fixture that captures the new structure.

## Scope

In scope for v0:

- public cat-bond-like BSX listings
- BMA enrichment
- SEC sponsor evidence
- NWS, NOAA Storm Events, USGS, IBTrACS, FEMA hazard/event inputs
- rule-based possible-overlap watchlists

Out of scope for v0:

- secondary-market pricing
- investor holdings
- opaque OTC or private risk-transfer inventories
