from __future__ import annotations

import json
import math
from pathlib import Path

import polars as pl

from ..config import Settings
from ..http import build_session, request_json
from ..utils import utcnow_iso, write_json

OPENFEMA_URL = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
OPENFEMA_PAGE_SIZE = 5000


def _fetch_disaster_declarations_page(
    session,
    settings: Settings,
    skip: int,
    top: int,
) -> dict:
    params = {
        "$format": "json",
        "$top": top,
        "$skip": skip,
        "$count": "true",
    }
    payload = request_json(session, OPENFEMA_URL, settings, params=params)
    page_path = settings.raw_dir / "openfema" / "pages" / f"DisasterDeclarationsSummaries_{skip:06d}.json"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _extract_rows(payload: dict) -> list[dict]:
    rows = payload.get("DisasterDeclarationsSummaries")
    if isinstance(rows, list):
        return rows
    return []


def fetch_fema_disaster_declarations(settings: Settings) -> Path:
    session = build_session(settings)
    dest = settings.raw_dir / "openfema" / "DisasterDeclarationsSummaries.parquet"
    rows: list[dict] = []
    skip = 0
    total_count: int | None = None

    while total_count is None or skip < total_count:
        payload = _fetch_disaster_declarations_page(
            session=session,
            settings=settings,
            skip=skip,
            top=OPENFEMA_PAGE_SIZE,
        )
        if total_count is None:
            metadata = payload.get("metadata") or {}
            count = metadata.get("count")
            total_count = int(count) if count is not None else None
        page_rows = _extract_rows(payload)
        if not page_rows:
            break
        rows.extend(page_rows)
        skip += len(page_rows)
        if len(page_rows) < OPENFEMA_PAGE_SIZE:
            break

    dest.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.from_dicts(rows, infer_schema_length=len(rows)).write_parquet(dest)
    else:
        pl.DataFrame([]).write_parquet(dest)
    write_json(
        settings.processed_dir / "openfema" / "manifest.json",
        {
            "source": "openfema",
            "url": OPENFEMA_URL,
            "page_size": OPENFEMA_PAGE_SIZE,
            "row_count": len(rows),
            "retrieved_at": utcnow_iso(),
            "page_count": math.ceil(len(rows) / OPENFEMA_PAGE_SIZE) if rows else 0,
        },
    )
    return dest
