.PHONY: install demo fetch refresh registry watchlist site audit review-queue test lint release-check

install:
	pip install -r requirements.txt
	pip install -e '.[dev]'

demo:
	PYTHONPATH=src python -m opencatwatch demo-site-data

fetch:
	bash scripts/fetch_all_minimal.sh

refresh:
	PYTHONPATH=src python -m opencatwatch refresh-all

registry:
	PYTHONPATH=src python -m opencatwatch build-registry

watchlist:
	PYTHONPATH=src python -m opencatwatch build-watchlist

site:
	PYTHONPATH=src python -m opencatwatch build-site

audit:
	PYTHONPATH=src python -m opencatwatch audit-data

review-queue:
	PYTHONPATH=src python -m opencatwatch build-review-queue

test:
	PYTHONPATH=src python -m pytest -q -o cache_dir=/tmp/catwatch-pytest-cache

lint:
	PYTHONPATH=src python -m ruff check src/opencatwatch tests

release-check:
	PYTHONPATH=src python -m opencatwatch release-check
