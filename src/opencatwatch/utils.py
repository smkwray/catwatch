from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

try:
    import polars as pl
except Exception:  # pragma: no cover
    pl = None  # type: ignore


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: object) -> Path:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[dict]) -> Path:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_records_bundle(base_path: Path, rows: list[dict]) -> None:
    write_jsonl(base_path.with_suffix(".jsonl"), rows)
    if pl is not None and rows:
        df = pl.from_dicts(rows, infer_schema_length=len(rows))
        df.write_parquet(base_path.with_suffix(".parquet"))


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace("&amp;", "&")
    cleaned = re.sub(r"[^a-z0-9& ]+", " ", cleaned)
    cleaned = re.sub(r"\b(ltd|limited|inc|corp|corporation|company|co|plc|llc)\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_date_maybe(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip().rstrip(".")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\bSept\b", "Sep", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text)
    for fmt in (
        "%d %b %Y",
        "%d %B %Y",
        "%d %b, %Y",
        "%d %B, %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def extract_labeled_field(lines: list[str], label: str) -> str | None:
    label_lower = label.lower().strip(":")
    for i, item in enumerate(lines):
        if item.lower().strip(":") == label_lower and i + 1 < len(lines):
            return lines[i + 1].strip()
        if item.lower().startswith(label_lower + ":"):
            return item.split(":", 1)[1].strip()
    return None


STATE_MAP = {
    "alabama": "alabama",
    "alaska": "alaska",
    "arizona": "arizona",
    "arkansas": "arkansas",
    "california": "california",
    "chile": "chile",
    "florida": "florida",
    "georgia": "georgia",
    "hawaii": "hawaii",
    "louisiana": "louisiana",
    "mississippi": "mississippi",
    "north carolina": "north_carolina",
    "south carolina": "south_carolina",
    "texas": "texas",
    "japan": "japan",
    "italy": "italy",
    "greece": "greece",
    "russia": "russia",
    "tonga": "tonga",
    "cuba": "cuba",
    "solomon islands": "solomon_islands",
    "kermadec islands": "new_zealand",
    "europe": "europe",
}

USGS_REGION_ALIASES = {
    "cuba": ("cuba",),
    "italy": ("italy",),
    "japan": ("japan",),
    "russia": ("russia",),
    "tonga": ("tonga", "tonga islands"),
    "greece": ("greece",),
    "solomon_islands": ("solomon islands",),
    "new_zealand": ("kermadec islands",),
    "alaska": ("alaska", "aleutian islands"),
}


def _normalize_region_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _contains_region_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_region_text(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in f" {normalized_text} "


def extract_region_codes(text: str | None) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    normalized = _normalize_region_text(text)
    codes: list[str] = []
    for code, phrases in USGS_REGION_ALIASES.items():
        if any(_contains_region_phrase(normalized, phrase) for phrase in phrases):
            codes.append(code)
    for key, value in STATE_MAP.items():
        if _contains_region_phrase(normalized, key):
            codes.append(value)
    if re.search(r"\b(united states|u\.s\.|u\.s|us)\b", lower):
        codes.append("us")
    if "global" in lower:
        codes.append("global")
    return sorted(set(codes))
