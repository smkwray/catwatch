from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..config import Settings
from ..http import build_session, request_text
from ..utils import normalize_name, utcnow_iso, write_records_bundle

BMA_DIRECTORY_URL = "https://www.bma.bm/regulated-entities/"


def normalize_bma_name(value: str | None) -> str:
    cleaned = normalize_name(value)
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"\bthe\b", " ", cleaned)
    cleaned = re.sub(
        r"\b(dac|designated activity company|sac|segregated accounts company|spi|special purpose insurer)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_bma_aliases(row: dict) -> list[str]:
    aliases: list[str] = []
    issuer_name = str(row.get("issuer_name") or "").strip()
    title = str(row.get("title") or "").strip()
    if issuer_name:
        aliases.append(issuer_name)
    elif title:
        issuer_guess = re.split(
            r"\s+-\s+series\b|\s+series\b|\s+class\b|\s+principal\b",
            title,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        issuer_guess = issuer_guess.strip(" ,.-")
        if issuer_guess:
            aliases.append(issuer_guess)

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = normalize_bma_name(alias)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(alias)
    return deduped


def infer_names_from_bsx(settings: Settings) -> list[str]:
    from ..utils import read_jsonl

    rows = read_jsonl(settings.processed_dir / "bsx" / "company_records.jsonl")
    names: list[str] = []
    for row in rows:
        names.extend(build_bma_aliases(row))
    return sorted({name for name in names if name})


def parse_bma_directory(html: str) -> list[dict]:
    """Parse the full BMA regulated-entities page into a list of entity dicts."""
    soup = BeautifulSoup(html, "lxml")
    div = soup.find(id="SearchentityData")
    if not div:
        return []
    table = div.find("table")
    if not table:
        return []
    rows = table.find_all("tr")
    entities: list[dict] = []
    for tr in rows[1:]:  # skip header row
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        company_name = tds[0].get_text(strip=True)
        if not company_name:
            continue
        sector = tds[1].get_text(strip=True)
        # License/Registration Type is in the 5th column
        license_text = tds[4].get_text(" ", strip=True)
        license_type = license_text.replace("License/Registration Type:", "").strip()
        entities.append({
            "company_name": company_name,
            "company_name_normalized": normalize_bma_name(company_name),
            "sector": sector,
            "license_type": license_type or None,
        })
    return entities


def match_bma_entities(
    names: list[str],
    directory: list[dict],
    source_url: str,
) -> list[dict]:
    """Match BSX-derived issuer names against the BMA directory.

    Returns records in the same format the registry pipeline expects.
    """
    # Build index: normalized name -> list of directory entries
    dir_by_norm: dict[str, list[dict]] = {}
    for ent in directory:
        key = ent["company_name_normalized"]
        if key:
            dir_by_norm.setdefault(key, []).append(ent)

    now = utcnow_iso()
    matches: list[dict] = []
    for query_name in names:
        if not query_name:
            continue
        query_norm = normalize_bma_name(query_name)
        if not query_norm:
            continue
        candidates = dir_by_norm.get(query_norm, [])
        for ent in candidates:
            matches.append({
                "source_name": "bma",
                "source_url": source_url,
                "query_name": query_name,
                "matched_name": ent["company_name"],
                "matched_name_normalized": ent["company_name_normalized"],
                "query_name_normalized": query_norm,
                "regulator_class": ent["license_type"],
                "registration_number": None,
                "effective_date_raw": None,
                "sector": ent["sector"],
                "snippet": f"{ent['company_name']} | {ent['sector']} | {ent['license_type'] or ''}",
                "retrieved_at": now,
            })
    return matches


def fetch_bma_for_names(settings: Settings, names: list[str]) -> list[dict]:
    session = build_session(settings)
    html = request_text(session, BMA_DIRECTORY_URL, settings)
    directory = parse_bma_directory(html)
    matches = match_bma_entities(names, directory, source_url=BMA_DIRECTORY_URL)
    write_records_bundle(settings.processed_dir / "bma" / "entity_matches", matches)
    return matches
