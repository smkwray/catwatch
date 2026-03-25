-- DuckDB helper script for local exploratory work

CREATE SCHEMA IF NOT EXISTS registry;
CREATE SCHEMA IF NOT EXISTS hazards;
CREATE SCHEMA IF NOT EXISTS watchlist;

-- Example usage after generating files:
-- INSTALL httpfs;
-- LOAD httpfs;
-- SELECT * FROM read_json_auto('data/processed/registry/tranches.jsonl');
