.PHONY: install demo fetch refresh registry watchlist site audit review-queue test lint release-check snapshot-check

PYTHON ?= $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/python,$(shell command -v python3 2>/dev/null || command -v python))
ifeq ($(strip $(PYTHON)),)
  $(error python not found. Please install Python 3 and ensure python or python3 is on PATH)
endif
PIP := $(PYTHON) -m pip

PYTHONPATH := src
PYTHONPYCACHEPREFIX ?= /tmp/catwatch-pycache
PYTEST_CACHE_DIR ?= /tmp/catwatch-pytest-cache
RUFF_CACHE_DIR ?= /tmp/catwatch-ruff-cache

export PYTHONPATH
export PYTHONPYCACHEPREFIX
export RUFF_CACHE_DIR

install:
	$(PIP) install -r requirements.txt
	$(PIP) install -e '.[dev]'

demo:
	$(PYTHON) -m opencatwatch demo-site-data

fetch:
	bash scripts/fetch_all_minimal.sh

refresh:
	$(PYTHON) -m opencatwatch refresh-all

registry:
	$(PYTHON) -m opencatwatch build-registry

watchlist:
	$(PYTHON) -m opencatwatch build-watchlist

site:
	$(PYTHON) -m opencatwatch build-site

audit:
	$(PYTHON) -m opencatwatch audit-data

review-queue:
	$(PYTHON) -m opencatwatch build-review-queue

test:
	$(PYTHON) -m pytest -o cache_dir=$(PYTEST_CACHE_DIR)

lint:
	$(PYTHON) -m ruff check src/opencatwatch tests --cache-dir=$(RUFF_CACHE_DIR)

release-check:
	$(PYTHON) -m opencatwatch release-check

snapshot-check:
	$(PYTHON) -m opencatwatch validate-public-snapshot
