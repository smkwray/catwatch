from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from ..config import Settings
from ..sources.bma import normalize_bma_name
from ..utils import (
    extract_region_codes,
    normalize_name,
    read_jsonl,
    slugify,
    write_records_bundle,
)

_ISSUER_PERIL_HINTS: dict[str, list[str]] = {
    # Florida / Gulf Coast → US named storm
    "everglades": ["us_wind"],
    "citrus": ["us_wind"],
    "pelican": ["us_wind"],
    "manatee": ["us_wind"],
    "cape lookout": ["us_wind"],
    "northshore": ["us_wind"],
    "kendall": ["us_wind"],
    "frontline": ["us_wind"],
    "metrocat": ["us_wind"],
    "seaside": ["us_wind"],
    "sanders": ["us_wind"],
    "caelus": ["us_wind"],
    "bayou": ["us_wind"],
    "nature coast": ["us_wind"],
    "first coast": ["us_wind"],
    "blue ridge": ["us_wind"],
    "longleaf pine": ["us_wind"],
    "palm re": ["us_wind"],
    "gateway": ["us_wind"],
    "mystic re": ["us_wind"],
    "four lakes": ["us_wind"],
    "east lane": ["us_wind"],
    "long point": ["us_wind"],
    "armor": ["us_wind"],
    "eden re": ["us_wind"],
    "blue sky re": ["us_wind"],
    "montoya": ["us_wind"],
    "herbie": ["us_wind"],
    "purple re": ["us_wind"],
    "charles river": ["us_wind"],
    "riverfront": ["us_wind"],
    "bridge street": ["us_wind"],
    "bluebonnet": ["us_wind"],
    "mayflower": ["us_wind"],
    # Caribbean / Puerto Rico
    "puerto rico": ["us_wind"],
    # Multi-peril property cat
    "kilimanjaro": ["us_wind", "ca_earthquake"],
    "merna": ["us_wind", "ca_earthquake"],
    "alamo": ["us_wind", "ca_earthquake"],
    "bonanza": ["us_wind", "ca_earthquake"],
    "acorn": ["us_wind", "ca_earthquake"],
    "matterhorn": ["us_wind", "ca_earthquake"],
    "integrity": ["us_wind", "ca_earthquake"],
    "3264 re": ["us_wind", "ca_earthquake"],
    "voussoir": ["us_wind", "ca_earthquake"],
    "polestar": ["us_wind", "ca_earthquake"],
    "mona lisa": ["us_wind", "ca_earthquake"],
    "hestia": ["us_wind", "ca_earthquake"],
    "titania": ["us_wind", "ca_earthquake"],
    "veraison": ["us_wind", "ca_earthquake"],
    "hexagon": ["us_wind", "ca_earthquake"],
    "chartwell": ["us_wind", "ca_earthquake"],
    "eclipse re": ["us_wind", "ca_earthquake"],
    "galileo": ["us_wind", "ca_earthquake"],
    "ursa re": ["us_wind", "ca_earthquake"],
    "fidus": ["us_wind", "ca_earthquake"],
    "ocelot": ["us_wind", "ca_earthquake"],
    "photon": ["us_wind", "ca_earthquake"],
    "sutter": ["us_wind", "ca_earthquake"],
    "commonwealth": ["us_wind", "ca_earthquake"],
    "foundation re": ["us_wind", "ca_earthquake"],
    "aquila re": ["us_wind", "ca_earthquake"],
    # California-focused
    "torrey pines": ["ca_earthquake"],
    "golden bear": ["ca_earthquake", "ca_wildfire"],
    "topanga": ["ca_wildfire"],
    "yosemite": ["ca_earthquake", "ca_wildfire"],
    # Flood-specific
    "floodsmart": ["flood"],
    # Japan-focused
    "nakama": ["japan_typhoon"],
    "sakura": ["japan_typhoon", "ca_earthquake"],
    "kizuna": ["japan_typhoon"],
    "tomoni": ["japan_typhoon"],
}


_ISSUER_REGION_HINTS: dict[str, list[str]] = {
    # Florida / Gulf
    "everglades": ["florida"],
    "citrus": ["florida"],
    "manatee": ["florida"],
    "nature coast": ["florida"],
    "first coast": ["florida"],
    "frontline": ["florida"],
    "kendall": ["florida"],
    # California
    "torrey pines": ["california"],
    "golden bear": ["california"],
    "topanga": ["california"],
    "yosemite": ["california"],
    "oaktown": ["california"],
    "sutter": ["california"],
    # Japan
    "nakama": ["japan"],
    "sakura": ["japan"],
    "kizuna": ["japan"],
    "tomoni": ["japan"],
    # Puerto Rico / US
    "puerto rico": ["us"],
    # Generic US property-cat issuers
    "floodsmart": ["us"],
}

_LIST_FIELDS = {"peril_codes", "region_codes"}
_OVERRIDE_FIELDS = {
    "issue_amount",
    "peril_codes",
    "region_codes",
    "maturity_date",
    "status",
    "record_type",
    "sponsor_name",
    "issuer_name",
    "listed_date",
    "risk_start_date",
    "risk_end_date",
}

_FIELD_PROVENANCE_KEYS = {
    "issue_amount": ("issue_amount_source_type", "issue_amount_source_url", "issue_amount_source_note"),
    "peril_codes": ("peril_source_type", "peril_source_url", "peril_source_note"),
    "region_codes": ("region_source_type", "region_source_url", "region_source_note"),
    "maturity_date": ("maturity_source_type", "maturity_source_url", "maturity_source_note"),
    "trigger_type": ("trigger_source_type", "trigger_source_url", "trigger_source_note"),
}

_BMA_AUTO_ACCEPT_SCORE = 0.88
_BMA_AUTO_ACCEPT_MARGIN = 0.12
_SEC_AUTO_ACCEPT_SCORE = 0.85
_SEC_AUTO_ACCEPT_MARGIN = 0.1


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("expected JSON list")
    return [str(item).strip() for item in parsed if str(item).strip()]


def _default_perils_with_method(
    title: str, sponsor_name: str | None = None, issuer_name: str | None = None
) -> tuple[list[str], str]:
    lower = f"{title} {sponsor_name or ''} {issuer_name or ''}".lower()
    if "wildfire" in lower:
        return ["ca_wildfire"], "title_keyword"
    if "earthquake" in lower:
        return ["ca_earthquake"], "title_keyword"
    if "hurricane" in lower or "wind" in lower or "storm" in lower:
        return ["us_wind"], "title_keyword"
    if "typhoon" in lower:
        return ["japan_typhoon"], "title_keyword"
    if "flood" in lower:
        return ["flood"], "title_keyword"
    if "mortgage" in lower:
        return ["mortgage_insurance"], "title_keyword"

    issuer_lower = (issuer_name or "").lower()
    for hint_key, perils in _ISSUER_PERIL_HINTS.items():
        if hint_key in issuer_lower:
            return perils, "issuer_hint"
    return ["other_property_cat"], "fallback_other_property_cat"


def _default_perils(title: str, sponsor_name: str | None = None, issuer_name: str | None = None) -> list[str]:
    return _default_perils_with_method(title=title, sponsor_name=sponsor_name, issuer_name=issuer_name)[0]


def _default_regions(
    title: str, sponsor_name: str | None, issuer_name: str | None, peril_codes: list[str]
) -> tuple[list[str], str]:
    explicit = extract_region_codes(f"{title} {sponsor_name or ''} {issuer_name or ''}")
    if explicit:
        return explicit, "explicit_text"

    issuer_lower = (issuer_name or "").lower()
    for hint_key, regions in _ISSUER_REGION_HINTS.items():
        if hint_key in issuer_lower:
            return sorted(set(regions)), "issuer_hint"

    inferred: list[str] = []
    if any(peril in {"ca_earthquake", "ca_wildfire"} for peril in peril_codes):
        inferred.append("california")
    if "japan_typhoon" in peril_codes:
        inferred.append("japan")
    if any(peril in {"us_wind", "flood", "severe_convective_storm", "mortgage_insurance"} for peril in peril_codes):
        inferred.append("us")
    if inferred:
        return sorted(set(inferred)), "peril_hint"
    return [], "missing"


def _status_from_listing(listing_status: str | None) -> str:
    if not listing_status:
        return "unknown"
    lower = listing_status.lower()
    if "listed" in lower:
        return "outstanding"
    if "mature" in lower or "expired" in lower:
        return "matured"
    return lower.replace(" ", "_")


def _derive_status(listing_status: str | None, maturity_date: str | None, *, as_of: date) -> str:
    status = _status_from_listing(listing_status)
    if maturity_date:
        try:
            if date.fromisoformat(maturity_date[:10]) < as_of:
                return "matured"
        except ValueError:
            pass
    return status


def _infer_record_type(title: str, maturity_date: str | None) -> str:
    lower = re.sub(r"[^a-z0-9]+", " ", title.lower())
    lower = f" {lower} "
    has_programme = " programme " in lower or " program " in lower
    has_tranche_marker = any(marker in lower for marker in (" series ", " class ", " tranche ", " due "))
    if has_programme and not has_tranche_marker and not maturity_date:
        return "programme"
    return "tranche"


def _load_manual_overrides(path: Path) -> dict[tuple[str, str], dict[str, str | None]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return {
        (row["tranche_name"].strip(), row["field_name"].strip()): {
            "override_value": (row.get("override_value") or "").strip(),
            "source_url": (row.get("source_url") or "").strip() or None,
            "notes": (row.get("notes") or "").strip() or None,
        }
        for row in rows
        if row.get("tranche_name") and row.get("field_name")
    }


def _load_trigger_overrides(path: Path) -> dict[str, dict[str, str | None]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return {
        row["tranche_name"].strip(): {
            "trigger_type": (row.get("trigger_type") or "").strip(),
            "source_url": (row.get("source_url") or "").strip() or None,
            "notes": (row.get("notes") or "").strip() or None,
        }
        for row in rows
        if row.get("tranche_name")
    }


def _normalize_trigger_type(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    if not text:
        return None
    if "parametric" in text:
        return "parametric"
    if "industry" in text and "loss" in text:
        return "industry_loss_index"
    if "index" in text or "indexed" in text:
        return "industry_loss_index"
    if "indemnity" in text:
        return "indemnity"
    return None


def _default_trigger_with_method(title: str, raw_trigger_type: str | None) -> tuple[str | None, str]:
    normalized = _normalize_trigger_type(raw_trigger_type)
    if normalized:
        return normalized, "bsx_detail"
    if "parametric" in title.lower():
        return "parametric", "title_keyword"
    return None, "missing"


def _extract_title_issue_amount(title: str) -> str | None:
    match = re.search(r"\$([0-9][0-9,]*)", title)
    if not match:
        return None
    digits = match.group(1).replace(",", "")
    return digits if digits.isdigit() else None


def _default_issue_amount_with_method(title: str, raw_issue_amount: str | None) -> tuple[str | None, str]:
    text = (raw_issue_amount or "").strip().replace(",", "")
    if text:
        return text, "bsx_detail"
    embedded = _extract_title_issue_amount(title)
    if embedded:
        return embedded, "title_embedded_amount"
    return None, "missing"


def _load_sponsor_alias_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                alias = (row.get("alias") or row.get("issuer_alias") or row.get("spv_alias") or "").strip()
                sponsor_name = (row.get("sponsor_name") or "").strip()
                if not alias or not sponsor_name:
                    continue
                normalized_alias = normalize_name(alias)
                if not normalized_alias:
                    continue
                rows.append(
                    {
                        "alias": alias,
                        "alias_normalized": normalized_alias,
                        "sponsor_name": sponsor_name,
                        "source_url": (row.get("source_url") or "").strip() or None,
                        "notes": (row.get("notes") or "").strip() or None,
                        "region_codes": _parse_json_list(row.get("region_codes")),
                        "peril_codes": _parse_json_list(row.get("peril_codes")),
                    }
                )
    return rows


def _index_sponsor_alias_rows(rows: list[dict]) -> tuple[dict[str, dict | None], list[dict]]:
    indexed: dict[str, dict | None] = {}
    for row in rows:
        key = row["alias_normalized"]
        existing = indexed.get(key)
        if existing is None and key in indexed:
            continue
        if not existing:
            indexed[key] = row
            continue
        if existing.get("sponsor_name") == row.get("sponsor_name"):
            continue
        indexed[key] = None
    unique_rows = [
        row
        for key, row in indexed.items()
        if row is not None and len(key) >= 6
    ]
    unique_rows.sort(key=lambda row: len(row["alias_normalized"]), reverse=True)
    return indexed, unique_rows


def _index_bma_rows(rows: list[dict]) -> dict[str, list[dict]]:
    indexed: dict[str, list[dict]] = {}
    for row in rows:
        for key in {
            row.get("query_name_normalized") or normalize_bma_name(row.get("query_name")),
            row.get("matched_name_normalized") or normalize_bma_name(row.get("matched_name")),
        }:
            if not key:
                continue
            indexed.setdefault(key, []).append(row)
    return indexed


def _index_bma_review_candidates(rows: list[dict]) -> dict[str, list[dict]]:
    indexed: dict[str, list[dict]] = {}
    for row in rows:
        key = row.get("query_name_normalized") or normalize_bma_name(row.get("query_name"))
        if not key:
            continue
        indexed.setdefault(key, []).append(row)
    for key, candidates in indexed.items():
        indexed[key] = sorted(
            candidates,
            key=lambda row: (
                -float(row.get("candidate_score") or 0.0),
                int(row.get("candidate_rank") or 9999),
                row.get("matched_name") or "",
            ),
        )
    return indexed


def _top_margin(candidates: list[dict], score_key: str) -> float | None:
    if len(candidates) < 2:
        return None
    top = float(candidates[0].get(score_key) or 0.0)
    second = float(candidates[1].get(score_key) or 0.0)
    return round(top - second, 3)


def _should_auto_accept_ranked_candidate(
    candidates: list[dict],
    *,
    score_key: str,
    min_score: float,
    min_margin: float,
) -> bool:
    if not candidates:
        return False
    top_score = float(candidates[0].get(score_key) or 0.0)
    if top_score < min_score:
        return False
    margin = _top_margin(candidates, score_key)
    if margin is None:
        return True
    return margin >= min_margin


def _resolve_bma_match(
    issuer_name: str | None,
    bma_by_name: dict[str, list[dict]],
    bma_review_by_name: dict[str, list[dict]],
) -> tuple[list[dict], dict | None, str, list[dict]]:
    issuer_norm = normalize_bma_name(issuer_name)
    if not issuer_norm:
        return [], None, "missing", []

    candidates = bma_by_name.get(issuer_norm, [])
    ranked_candidates = bma_review_by_name.get(issuer_norm, [])

    exact_candidates = [
        row
        for row in candidates
        if (row.get("matched_name_normalized") or normalize_bma_name(row.get("matched_name"))) == issuer_norm
    ]
    preferred_candidates = exact_candidates or candidates

    distinct_matches: dict[str, dict] = {}
    for row in preferred_candidates:
        key = (
            normalize_name(row.get("matched_name"))
            or row.get("matched_name_normalized")
            or normalize_bma_name(row.get("matched_name"))
        )
        if key and key not in distinct_matches:
            distinct_matches[key] = row

    if len(distinct_matches) == 1:
        return preferred_candidates, next(iter(distinct_matches.values())), "exact", ranked_candidates

    if _should_auto_accept_ranked_candidate(
        ranked_candidates,
        score_key="candidate_score",
        min_score=_BMA_AUTO_ACCEPT_SCORE,
        min_margin=_BMA_AUTO_ACCEPT_MARGIN,
    ):
        return candidates, ranked_candidates[0], "ranked_auto", ranked_candidates

    if preferred_candidates or ranked_candidates:
        return preferred_candidates or candidates, None, "manual_review", ranked_candidates
    return [], None, "missing", []


def _index_sec_spv_links(rows: list[dict]) -> dict[str, list[dict]]:
    indexed: dict[str, list[dict]] = {}
    for row in rows:
        key = row.get("spv_name_normalized") or normalize_name(row.get("spv_name"))
        if key:
            indexed.setdefault(key, []).append(row)
    return indexed


def _dedupe_sec_candidates(rows: list[dict]) -> list[dict]:
    deduped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (
            str(row.get("sponsor_name") or ""),
            str(row.get("spv_name") or ""),
            str(row.get("source_filing_url") or ""),
        )
        existing = deduped.get(key)
        if not existing or float(row.get("candidate_score") or 0.0) > float(existing.get("candidate_score") or 0.0):
            deduped[key] = row
    return sorted(
        deduped.values(),
        key=lambda row: (
            -float(row.get("candidate_score") or 0.0),
            row.get("spv_name") or "",
            row.get("sponsor_name") or "",
            row.get("source_filing_url") or "",
        ),
    )


def _score_sec_spv_candidate(issuer_name: str, spv_name: str) -> float:
    issuer_norm = normalize_name(issuer_name)
    spv_norm = normalize_name(spv_name)
    if not issuer_norm or not spv_norm:
        return 0.0
    if issuer_norm == spv_norm:
        return 1.0
    issuer_tokens = set(issuer_norm.split())
    spv_tokens = set(spv_norm.split())
    if not issuer_tokens or not spv_tokens:
        return 0.0
    overlap = len(issuer_tokens & spv_tokens)
    if not overlap:
        return 0.0
    coverage = overlap / len(issuer_tokens)
    precision = overlap / len(spv_tokens)
    containment_bonus = 0.1 if issuer_norm in spv_norm or spv_norm in issuer_norm else 0.0
    score = min(0.99, (0.6 * coverage) + (0.3 * precision) + containment_bonus)
    return round(score, 3)


def _resolve_sec_sponsor(issuer_name: str | None, sec_by_spv: dict[str, list[dict]]) -> tuple[dict | None, str, list[dict]]:
    if not issuer_name or not sec_by_spv:
        return None, "missing", []
    issuer_norm = normalize_name(issuer_name)
    if not issuer_norm:
        return None, "missing", []
    # Exact match first
    if issuer_norm in sec_by_spv:
        exact_rows = _dedupe_sec_candidates(sec_by_spv[issuer_norm])
        distinct_sponsors = {str(row.get("sponsor_name") or "").strip() for row in exact_rows if row.get("sponsor_name")}
        if len(distinct_sponsors) == 1:
            return exact_rows[0], "exact", exact_rows
        return None, "manual_review", exact_rows

    scored: list[dict] = []
    for spv_norm, links in sec_by_spv.items():
        score = _score_sec_spv_candidate(issuer_name, spv_norm)
        if score < 0.55:
            continue
        for link in links:
            scored.append(
                {
                    **link,
                    "candidate_score": score,
                }
            )
    scored = _dedupe_sec_candidates(scored)
    if _should_auto_accept_ranked_candidate(
        scored,
        score_key="candidate_score",
        min_score=_SEC_AUTO_ACCEPT_SCORE,
        min_margin=_SEC_AUTO_ACCEPT_MARGIN,
    ):
        return scored[0], "ranked_auto", scored
    if scored:
        return None, "manual_review", scored
    return None, "missing", []


def _resolve_sponsor_alias(
    issuer_name: str | None,
    sec_link: dict | None,
    aliases_by_name: dict[str, dict | None],
    alias_rows_for_prefix: list[dict],
) -> dict | None:
    candidates = [
        issuer_name,
        sec_link.get("spv_name") if sec_link else None,
        sec_link.get("spv_name_normalized") if sec_link else None,
    ]
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_name(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        alias_row = aliases_by_name.get(normalized)
        if alias_row:
            return alias_row
        for prefix_row in alias_rows_for_prefix:
            alias_normalized = prefix_row["alias_normalized"]
            if normalized.startswith(alias_normalized + " "):
                return prefix_row
    return None


def _apply_override(tranche: dict, field: str, value: str) -> None:
    if field in _LIST_FIELDS:
        tranche[field] = json.loads(value)
    else:
        tranche[field] = value


def _apply_field_provenance(
    tranche: dict,
    field: str,
    source_type: str,
    source_url: str | None,
    note: str | None = None,
) -> None:
    keys = _FIELD_PROVENANCE_KEYS.get(field)
    if not keys:
        return
    type_key, url_key, note_key = keys
    tranche[type_key] = source_type
    tranche[url_key] = source_url
    tranche[note_key] = note


def _should_apply_alias_region_codes(tranche: dict, sponsor_alias: dict) -> bool:
    alias_regions = sponsor_alias.get("region_codes") or []
    if not alias_regions:
        return False
    return tranche.get("region_inference_method") in {"missing", "issuer_hint", "peril_hint"}


def _should_apply_alias_peril_codes(tranche: dict, sponsor_alias: dict) -> bool:
    alias_perils = sponsor_alias.get("peril_codes") or []
    if not alias_perils:
        return False
    return tranche.get("peril_inference_method") in {"fallback_other_property_cat", "issuer_hint"}


def _refresh_region_from_current_perils(
    tranche: dict,
    *,
    title: str,
    sponsor_name: str | None,
    issuer_name: str | None,
    source_url: str | None,
) -> None:
    region_codes, region_method = _default_regions(
        title=title,
        sponsor_name=sponsor_name,
        issuer_name=issuer_name,
        peril_codes=tranche.get("peril_codes") or [],
    )
    tranche["region_codes"] = region_codes
    tranche["region_inference_method"] = region_method
    if region_codes:
        tranche["region_source_type"] = region_method
        tranche["region_source_url"] = source_url
        tranche["region_source_note"] = None
    else:
        tranche["region_source_type"] = "missing"
        tranche["region_source_url"] = None
        tranche["region_source_note"] = None


def build_registry(settings: Settings) -> str:
    bsx_rows = read_jsonl(settings.processed_dir / "bsx" / "company_records.jsonl")
    bma_rows = read_jsonl(settings.processed_dir / "bma" / "entity_matches.jsonl")
    bma_review_rows = read_jsonl(settings.processed_dir / "bma" / "entity_review_candidates.jsonl")
    sec_spv_rows = read_jsonl(settings.processed_dir / "sec" / "sponsor_spv_links.jsonl")
    overrides = _load_manual_overrides(settings.manual_dir / "tranche_overrides.csv")
    trigger_overrides = _load_trigger_overrides(settings.manual_dir / "trigger_overrides.csv")
    sponsor_alias_rows = _load_sponsor_alias_rows(
        [settings.manual_dir / "sponsor_aliases.csv", Path("seeds/sponsor_aliases_template.csv")]
    )
    sponsor_aliases_by_name, sponsor_alias_rows_for_prefix = _index_sponsor_alias_rows(sponsor_alias_rows)
    bma_by_name = _index_bma_rows(bma_rows)
    bma_review_by_name = _index_bma_review_candidates(bma_review_rows)
    sec_by_spv = _index_sec_spv_links(sec_spv_rows)

    tranches: list[dict] = []
    programmes: dict[str, dict] = {}

    for row in bsx_rows:
        title = row.get("title") or ""
        issuer_name = row.get("issuer_name")
        sponsor_name = row.get("sponsor_name")
        raw_sponsor_name = sponsor_name
        bma_matches, chosen_bma_match, bma_match_method, bma_ranked_candidates = _resolve_bma_match(
            issuer_name, bma_by_name, bma_review_by_name
        )
        sec_link, sec_match_method, sec_candidates = _resolve_sec_sponsor(issuer_name, sec_by_spv)
        sponsor_alias = _resolve_sponsor_alias(
            issuer_name, sec_link, sponsor_aliases_by_name, sponsor_alias_rows_for_prefix
        )

        sponsor_attribution_state = "missing"
        if raw_sponsor_name:
            sponsor_attribution_state = "bsx_declared"
        elif sec_link and sec_match_method == "exact":
            sponsor_attribution_state = "sec_exact_spv"
        elif sec_link and sec_match_method == "ranked_auto":
            sponsor_attribution_state = "sec_ranked_spv"
        elif sponsor_alias:
            sponsor_attribution_state = "alias_family"

        if not sponsor_name and sec_link:
            sponsor_name = sec_link.get("sponsor_name")
        if not sponsor_name and sponsor_alias:
            sponsor_name = sponsor_alias.get("sponsor_name")

        peril_codes, peril_inference_method = _default_perils_with_method(
            title=title, sponsor_name=sponsor_name, issuer_name=issuer_name
        )
        region_codes, region_inference_method = _default_regions(
            title=title, sponsor_name=sponsor_name, issuer_name=issuer_name, peril_codes=peril_codes
        )
        listed_date = row.get("listed_date")
        maturity_date = row.get("maturity_date")
        maturity_source_type = row.get("maturity_extraction_method") or ("bsx_detail" if maturity_date else "missing")
        trigger_type, trigger_source_type = _default_trigger_with_method(title=title, raw_trigger_type=row.get("trigger_type"))
        issue_amount, issue_amount_source_type = _default_issue_amount_with_method(
            title=title,
            raw_issue_amount=row.get("issue_amount"),
        )
        record_type = _infer_record_type(title=title, maturity_date=maturity_date)

        tranche = {
            "tranche_id": hashlib.sha1((row.get("source_url") or title).encode("utf-8")).hexdigest()[:16],
            "programme_id": slugify(issuer_name or title or "unknown-programme"),
            "record_type": record_type,
            "tranche_name": title,
            "sponsor_name": sponsor_name,
            "sponsor_source": "bsx"
            if raw_sponsor_name
            else ("sec_spv" if sec_link else ("alias" if sponsor_alias else "missing")),
            "sponsor_source_detail": raw_sponsor_name
            or (sec_link.get("spv_name") if sec_link else None)
            or (sponsor_alias.get("alias") if sponsor_alias else None),
            "sponsor_source_url": row.get("source_url")
            if raw_sponsor_name
            else (
                sec_link.get("source_filing_url")
                if sec_link
                else (sponsor_alias.get("source_url") if sponsor_alias else None)
            ),
            "sponsor_source_note": None
            if raw_sponsor_name
            else (
                (sec_link.get("source_term") if sec_link else None)
                or (sponsor_alias.get("notes") if sponsor_alias else None)
            ),
            "sponsor_attribution_state": sponsor_attribution_state,
            "issuer_name": issuer_name,
            "listing_venue": "BSX",
            "listing_status": row.get("listing_status"),
            "listed_date": listed_date,
            "maturity_date": maturity_date,
            "maturity_source_type": maturity_source_type,
            "maturity_source_url": row.get("source_url") if maturity_date else None,
            "maturity_source_note": None,
            "issue_amount": issue_amount,
            "issue_amount_source_type": issue_amount_source_type if issue_amount else "missing",
            "issue_amount_source_url": row.get("source_url") if issue_amount else None,
            "issue_amount_source_note": None,
            "currency": row.get("currency"),
            "isin": row.get("isin"),
            "cusip": row.get("cusip"),
            "trigger_type": trigger_type,
            "trigger_source_type": trigger_source_type if trigger_type else "missing",
            "trigger_source_url": row.get("source_url") if trigger_type else None,
            "trigger_source_note": None,
            "peril_codes": peril_codes,
            "peril_inference_method": peril_inference_method,
            "peril_source_type": peril_inference_method if peril_codes else "missing",
            "peril_source_url": row.get("source_url") if peril_codes else None,
            "peril_source_note": None,
            "region_codes": region_codes,
            "region_inference_method": region_inference_method,
            "region_source_type": region_inference_method if region_codes else "missing",
            "region_source_url": row.get("source_url") if region_codes else None,
            "region_source_note": None,
            "risk_start_date": listed_date,
            "risk_end_date": maturity_date,
            "status": _derive_status(
                row.get("listing_status"),
                maturity_date=maturity_date,
                as_of=settings.as_of_date,
            ),
            "attribution_status": {
                "sponsor": "sourced" if sponsor_name else "missing",
                "trigger": trigger_source_type if trigger_type else "missing",
                "peril": peril_inference_method if peril_codes else "missing",
                "region": region_inference_method if region_codes else "missing",
                "maturity": maturity_source_type if maturity_date else "missing",
            },
            "review_status": "needs_review",
            "source_url": row.get("source_url"),
            "extraction_method": row.get("extraction_method"),
            "retrieved_at": row.get("retrieved_at"),
            "bma_match_count": len(bma_matches),
            "bma_match_method": bma_match_method,
            "bma_regulator_class": chosen_bma_match.get("regulator_class") if chosen_bma_match else None,
            "bma_registration_number": chosen_bma_match.get("registration_number") if chosen_bma_match else None,
            "bma_candidate_count": len(bma_ranked_candidates),
            "bma_top_candidate_name": (bma_ranked_candidates[0].get("matched_name") if bma_ranked_candidates else None),
            "bma_top_candidate_score": (
                float(bma_ranked_candidates[0].get("candidate_score") or 0.0) if bma_ranked_candidates else None
            ),
            "sec_match_method": sec_match_method,
            "sec_sponsor_name": sec_link.get("sponsor_name") if sec_link else None,
            "sec_sponsor_filing_url": sec_link.get("source_filing_url") if sec_link else None,
            "sec_candidate_count": len(sec_candidates),
            "sec_top_candidate_name": (sec_candidates[0].get("spv_name") if sec_candidates else None),
            "sec_top_candidate_score": (
                float(sec_candidates[0].get("candidate_score") or 0.0) if sec_candidates else None
            ),
        }

        if sponsor_alias:
            if _should_apply_alias_region_codes(tranche, sponsor_alias):
                tranche["region_codes"] = sponsor_alias["region_codes"]
                tranche["region_inference_method"] = "sponsor_alias"
                _apply_field_provenance(
                    tranche,
                    "region_codes",
                    source_type="sponsor_alias",
                    source_url=sponsor_alias.get("source_url"),
                    note=sponsor_alias.get("notes"),
                )
            if _should_apply_alias_peril_codes(tranche, sponsor_alias):
                tranche["peril_codes"] = sponsor_alias["peril_codes"]
                tranche["peril_inference_method"] = "sponsor_alias"
                _apply_field_provenance(
                    tranche,
                    "peril_codes",
                    source_type="sponsor_alias",
                    source_url=sponsor_alias.get("source_url"),
                    note=sponsor_alias.get("notes"),
                )
                if not sponsor_alias.get("region_codes") and tranche.get("region_inference_method") in {
                    "issuer_hint",
                    "peril_hint",
                }:
                    _refresh_region_from_current_perils(
                        tranche,
                        title=title,
                        sponsor_name=tranche.get("sponsor_name") or sponsor_alias.get("sponsor_name"),
                        issuer_name=issuer_name,
                        source_url=row.get("source_url"),
                    )
            if not tranche["sponsor_name"]:
                tranche["sponsor_name"] = sponsor_alias["sponsor_name"]
                tranche["sponsor_source"] = "alias"
                tranche["sponsor_source_detail"] = sponsor_alias["alias"]
                tranche["sponsor_source_url"] = sponsor_alias.get("source_url")
                tranche["sponsor_source_note"] = sponsor_alias.get("notes")
                tranche["sponsor_attribution_state"] = "alias_family"

        original_maturity_date = tranche.get("maturity_date")
        for field in _OVERRIDE_FIELDS:
            if (title, field) in overrides:
                override = overrides[(title, field)]
                _apply_override(tranche, field, str(override.get("override_value") or ""))
                if field == "region_codes":
                    tranche["region_inference_method"] = "manual_override"
                    _apply_field_provenance(
                        tranche,
                        field,
                        source_type="manual_override",
                        source_url=override.get("source_url"),
                        note=override.get("notes"),
                    )
                if field == "peril_codes":
                    tranche["peril_inference_method"] = "manual_override"
                    _apply_field_provenance(
                        tranche,
                        field,
                        source_type="manual_override",
                        source_url=override.get("source_url"),
                        note=override.get("notes"),
                    )
                if field == "maturity_date":
                    _apply_field_provenance(
                        tranche,
                        field,
                        source_type="manual_override",
                        source_url=override.get("source_url"),
                        note=override.get("notes"),
                    )
                if field == "issue_amount":
                    _apply_field_provenance(
                        tranche,
                        field,
                        source_type="manual_override",
                        source_url=override.get("source_url"),
                        note=override.get("notes"),
                    )
                if field == "sponsor_name":
                    tranche["sponsor_source"] = "manual_override"
                    tranche["sponsor_source_detail"] = "tranche_overrides.csv"
                    tranche["sponsor_source_url"] = override.get("source_url")
                    tranche["sponsor_source_note"] = override.get("notes")
                    tranche["sponsor_attribution_state"] = "manual_override"

        trigger_override = trigger_overrides.get(title)
        if trigger_override is not None:
            tranche["trigger_type"] = _normalize_trigger_type(str(trigger_override.get("trigger_type") or ""))
            _apply_field_provenance(
                tranche,
                "trigger_type",
                source_type="manual_override",
                source_url=trigger_override.get("source_url"),
                note=trigger_override.get("notes"),
            )

        if tranche.get("maturity_date") and (
            not tranche.get("risk_end_date") or tranche.get("risk_end_date") == original_maturity_date
        ):
            tranche["risk_end_date"] = tranche.get("maturity_date")

        canonical_sponsor = tranche.get("sponsor_name") or tranche.get("sec_sponsor_name")
        tranche["attribution_status"] = {
            "sponsor": tranche.get("sponsor_attribution_state") if canonical_sponsor else "missing",
            "trigger": tranche.get("trigger_source_type") if tranche.get("trigger_type") else "missing",
            "peril": tranche.get("peril_source_type") or "missing",
            "region": tranche.get("region_source_type") or "missing",
            "maturity": tranche.get("maturity_source_type") or "missing",
        }

        tranche["is_programme_shell"] = tranche.get("record_type") == "programme" and not tranche.get(
            "maturity_date"
        )

        tranches.append(tranche)

        prog_id = tranche["programme_id"]
        if prog_id not in programmes:
            programmes[prog_id] = {
                "programme_id": prog_id,
                "programme_name": issuer_name or title,
                "sponsor_name": sponsor_name,
                "issuer_name": issuer_name,
                "status": tranche["status"],
                "source_url": tranche["source_url"],
            }

    write_records_bundle(settings.processed_dir / "registry" / "tranches", tranches)
    write_records_bundle(settings.processed_dir / "registry" / "programmes", list(programmes.values()))
    return str(settings.processed_dir / "registry" / "tranches.jsonl")
