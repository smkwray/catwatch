from __future__ import annotations

import csv
import hashlib
import json
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


def _derive_status(listing_status: str | None, maturity_date: str | None) -> str:
    status = _status_from_listing(listing_status)
    if maturity_date:
        try:
            if date.fromisoformat(maturity_date[:10]) < date.today():
                return "matured"
        except ValueError:
            pass
    return status


def _infer_record_type(title: str, maturity_date: str | None) -> str:
    lower = f" {title.lower()} "
    has_programme = " programme " in lower or " program " in lower
    has_tranche_marker = any(marker in lower for marker in (" series ", " class ", " tranche ", " due "))
    if has_programme and not has_tranche_marker and not maturity_date:
        return "programme"
    return "tranche"


def _load_manual_overrides(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return {
        (row["tranche_name"].strip(), row["field_name"].strip()): row["override_value"].strip()
        for row in rows
        if row.get("tranche_name") and row.get("field_name")
    }


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


def _resolve_bma_match(issuer_name: str | None, bma_by_name: dict[str, list[dict]]) -> tuple[list[dict], dict | None]:
    issuer_norm = normalize_bma_name(issuer_name)
    if not issuer_norm:
        return [], None

    candidates = bma_by_name.get(issuer_norm, [])
    if not candidates:
        return [], None

    exact_candidates = [
        row for row in candidates if (row.get("matched_name_normalized") or normalize_bma_name(row.get("matched_name"))) == issuer_norm
    ]
    preferred_candidates = exact_candidates or candidates

    distinct_matches: dict[str, dict] = {}
    for row in preferred_candidates:
        key = normalize_name(row.get("matched_name")) or row.get("matched_name_normalized") or normalize_bma_name(row.get("matched_name"))
        if key and key not in distinct_matches:
            distinct_matches[key] = row

    if len(distinct_matches) == 1:
        return preferred_candidates, next(iter(distinct_matches.values()))
    return preferred_candidates, None


def _index_sec_spv_links(rows: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        key = row.get("spv_name_normalized") or normalize_name(row.get("spv_name"))
        if key and key not in indexed:
            indexed[key] = row
    return indexed


def _resolve_sec_sponsor(issuer_name: str | None, sec_by_spv: dict[str, dict]) -> dict | None:
    if not issuer_name or not sec_by_spv:
        return None
    issuer_norm = normalize_name(issuer_name)
    if not issuer_norm:
        return None
    # Exact match first
    if issuer_norm in sec_by_spv:
        return sec_by_spv[issuer_norm]
    for spv_norm, link in sec_by_spv.items():
        if spv_norm in issuer_norm or issuer_norm in spv_norm:
            return link
    return None


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


def build_registry(settings: Settings) -> str:
    bsx_rows = read_jsonl(settings.processed_dir / "bsx" / "company_records.jsonl")
    bma_rows = read_jsonl(settings.processed_dir / "bma" / "entity_matches.jsonl")
    sec_spv_rows = read_jsonl(settings.processed_dir / "sec" / "sponsor_spv_links.jsonl")
    overrides = _load_manual_overrides(settings.manual_dir / "tranche_overrides.csv")
    sponsor_alias_rows = _load_sponsor_alias_rows(
        [settings.manual_dir / "sponsor_aliases.csv", Path("seeds/sponsor_aliases_template.csv")]
    )
    sponsor_aliases_by_name, sponsor_alias_rows_for_prefix = _index_sponsor_alias_rows(sponsor_alias_rows)
    bma_by_name = _index_bma_rows(bma_rows)
    sec_by_spv = _index_sec_spv_links(sec_spv_rows)

    tranches: list[dict] = []
    programmes: dict[str, dict] = {}

    for row in bsx_rows:
        title = row.get("title") or ""
        issuer_name = row.get("issuer_name")
        sponsor_name = row.get("sponsor_name")
        raw_sponsor_name = sponsor_name
        bma_matches, chosen_bma_match = _resolve_bma_match(issuer_name, bma_by_name)
        sec_link = _resolve_sec_sponsor(issuer_name, sec_by_spv)
        sponsor_alias = _resolve_sponsor_alias(
            issuer_name, sec_link, sponsor_aliases_by_name, sponsor_alias_rows_for_prefix
        )

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
            "issuer_name": issuer_name,
            "listing_venue": "BSX",
            "listing_status": row.get("listing_status"),
            "listed_date": listed_date,
            "maturity_date": maturity_date,
            "issue_amount": row.get("issue_amount"),
            "currency": row.get("currency"),
            "isin": row.get("isin"),
            "cusip": row.get("cusip"),
            "trigger_type": row.get("trigger_type"),
            "peril_codes": peril_codes,
            "peril_inference_method": peril_inference_method,
            "region_codes": region_codes,
            "region_inference_method": region_inference_method,
            "risk_start_date": listed_date,
            "risk_end_date": maturity_date,
            "status": _derive_status(row.get("listing_status"), maturity_date=maturity_date),
            "confidence": 0.65 if issuer_name else 0.45,
            "review_status": "needs_review",
            "source_url": row.get("source_url"),
            "extraction_method": row.get("extraction_method"),
            "retrieved_at": row.get("retrieved_at"),
            "bma_match_count": len(bma_matches),
            "bma_regulator_class": chosen_bma_match.get("regulator_class") if chosen_bma_match else None,
            "bma_registration_number": chosen_bma_match.get("registration_number") if chosen_bma_match else None,
            "sec_sponsor_name": sec_link.get("sponsor_name") if sec_link else None,
            "sec_sponsor_filing_url": sec_link.get("source_filing_url") if sec_link else None,
        }

        if sponsor_alias:
            if not tranche["region_codes"] and sponsor_alias.get("region_codes"):
                tranche["region_codes"] = sponsor_alias["region_codes"]
                tranche["region_inference_method"] = "sponsor_alias"
            if "other_property_cat" in tranche["peril_codes"] and sponsor_alias.get("peril_codes"):
                tranche["peril_codes"] = sponsor_alias["peril_codes"]
                tranche["peril_inference_method"] = "sponsor_alias"
            if not tranche["sponsor_name"]:
                tranche["sponsor_name"] = sponsor_alias["sponsor_name"]
                tranche["sponsor_source"] = "alias"
                tranche["sponsor_source_detail"] = sponsor_alias["alias"]
                tranche["sponsor_source_url"] = sponsor_alias.get("source_url")

        for field in _OVERRIDE_FIELDS:
            if (title, field) in overrides:
                _apply_override(tranche, field, overrides[(title, field)])
                if field == "region_codes":
                    tranche["region_inference_method"] = "manual_override"
                if field == "peril_codes":
                    tranche["peril_inference_method"] = "manual_override"
                if field == "sponsor_name":
                    tranche["sponsor_source"] = "manual_override"
                    tranche["sponsor_source_detail"] = "tranche_overrides.csv"
                    tranche["sponsor_source_url"] = None

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
