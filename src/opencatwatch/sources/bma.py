from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..config import Settings
from ..http import build_session, request_text
from ..utils import normalize_name, utcnow_iso, write_json, write_records_bundle

BMA_DIRECTORY_URL = "https://www.bma.bm/regulated-entities/"
BMA_REVIEW_CANDIDATE_LIMIT = 3


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


def _tokenize_bma_name(value: str | None) -> set[str]:
    normalized = normalize_bma_name(value)
    return {token for token in normalized.split() if token}


def _score_bma_candidate(query_name: str, company_name: str) -> float:
    query_norm = normalize_bma_name(query_name)
    company_norm = normalize_bma_name(company_name)
    if not query_norm or not company_norm:
        return 0.0
    if query_norm == company_norm:
        return 1.0
    query_tokens = _tokenize_bma_name(query_name)
    company_tokens = _tokenize_bma_name(company_name)
    if not query_tokens or not company_tokens:
        return 0.0
    overlap = len(query_tokens & company_tokens)
    if not overlap:
        return 0.0
    coverage = overlap / len(query_tokens)
    precision = overlap / len(company_tokens)
    first_token_bonus = 0.1 if next(iter(sorted(query_tokens))) == next(iter(sorted(company_tokens))) else 0.0
    containment_bonus = 0.1 if query_norm in company_norm or company_norm in query_norm else 0.0
    score = min(0.99, (0.55 * coverage) + (0.25 * precision) + first_token_bonus + containment_bonus)
    return round(score, 3)


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


def build_bma_review_candidates(
    names: list[str],
    directory: list[dict],
    source_url: str,
    limit: int = BMA_REVIEW_CANDIDATE_LIMIT,
) -> list[dict]:
    now = utcnow_iso()
    candidates: list[dict] = []
    for query_name in names:
        scored: list[tuple[float, dict]] = []
        for entity in directory:
            score = _score_bma_candidate(query_name, entity.get("company_name"))
            if score < 0.45:
                continue
            scored.append((score, entity))
        scored.sort(
            key=lambda item: (
                -item[0],
                item[1].get("company_name") or "",
            )
        )
        for rank, (score, entity) in enumerate(scored[: max(1, limit)], start=1):
            candidates.append(
                {
                    "source_name": "bma",
                    "source_url": source_url,
                    "query_name": query_name,
                    "query_name_normalized": normalize_bma_name(query_name),
                    "matched_name": entity.get("company_name"),
                    "matched_name_normalized": entity.get("company_name_normalized"),
                    "regulator_class": entity.get("license_type"),
                    "registration_number": None,
                    "sector": entity.get("sector"),
                    "candidate_score": score,
                    "candidate_rank": rank,
                    "retrieved_at": now,
                }
            )
    return candidates


def fetch_bma_for_names(settings: Settings, names: list[str]) -> dict[str, int]:
    session = build_session(settings)
    html = request_text(session, BMA_DIRECTORY_URL, settings)
    directory = parse_bma_directory(html)
    matches = match_bma_entities(names, directory, source_url=BMA_DIRECTORY_URL)
    review_candidates = build_bma_review_candidates(names, directory, source_url=BMA_DIRECTORY_URL)
    write_records_bundle(settings.processed_dir / "bma" / "entity_matches", matches)
    write_records_bundle(settings.processed_dir / "bma" / "entity_review_candidates", review_candidates)
    write_json(
        settings.processed_dir / "bma" / "manifest.json",
        {
            "source": "bma",
            "queried_names": len(names),
            "matches": len(matches),
            "review_candidates": len(review_candidates),
            "retrieved_at": utcnow_iso(),
        },
    )
    return {"matches": len(matches), "review_candidates": len(review_candidates)}
