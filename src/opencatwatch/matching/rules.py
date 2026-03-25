from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from ..utils import utcnow_iso


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


# Perils that "other_property_cat" bonds are plausibly exposed to
_PROPERTY_CAT_PERILS = {"us_wind", "ca_earthquake", "ca_wildfire", "flood", "severe_convective_storm"}
_US_REGION_CODES = {
    "us",
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "florida",
    "georgia",
    "hawaii",
    "louisiana",
    "mississippi",
    "north_carolina",
    "south_carolina",
    "texas",
}


def _peril_match(tranche: dict[str, Any], event: dict[str, Any]) -> bool:
    tranche_perils = set(tranche.get("peril_codes", []) or [])
    event_peril = event.get("peril_code")
    if not tranche_perils or not event_peril:
        return False
    if event_peril in tranche_perils:
        return True
    if event_peril == "earthquake" and "ca_earthquake" in tranche_perils:
        return True
    if event_peril == "tropical_cyclone" and "us_wind" in tranche_perils:
        return True
    # Unclassified property cat bonds match major cat perils
    if "other_property_cat" in tranche_perils and event_peril in _PROPERTY_CAT_PERILS:
        return True
    return False


def _date_overlap(tranche: dict[str, Any], event: dict[str, Any]) -> bool:
    start = _to_date(tranche.get("risk_start_date") or tranche.get("listed_date"))
    end = _to_date(tranche.get("risk_end_date") or tranche.get("maturity_date"))
    event_date = _to_date(event.get("start_time"))
    if event_date is None:
        return False
    if start and event_date < start:
        return False
    if end and event_date > end:
        return False
    return True


def _region_overlap_kind(tranche: dict[str, Any], event: dict[str, Any]) -> str:
    tranche_regions = set(tranche.get("region_codes", []) or [])
    event_regions = set(event.get("region_codes", []) or [])
    if not tranche_regions or not event_regions:
        return "unknown"
    if "global" in tranche_regions or "global" in event_regions:
        return "overlap"
    if tranche_regions & event_regions:
        return "overlap"
    if "us" in tranche_regions and event_regions.issubset(_US_REGION_CODES):
        return "overlap"
    if "us" in event_regions and tranche_regions.issubset(_US_REGION_CODES):
        return "overlap"
    return "mismatch"


def possible_overlap(tranche: dict[str, Any], event: dict[str, Any]) -> tuple[bool, list[str], float]:
    reasons: list[str] = []
    score = 0.0

    if _peril_match(tranche, event):
        tranche_perils = set(tranche.get("peril_codes", []) or [])
        if "other_property_cat" in tranche_perils and event.get("peril_code") not in tranche_perils:
            reasons.append("broad_peril_match")
            score += 0.15  # lower confidence for unclassified bonds
        else:
            reasons.append("peril_match")
            score += 0.35
    else:
        return False, ["peril_mismatch"], 0.0

    if _date_overlap(tranche, event):
        reasons.append("active_date_overlap")
        score += 0.35
    else:
        return False, ["inactive_outside_risk_window"], 0.0

    region_kind = _region_overlap_kind(tranche, event)
    if region_kind == "overlap":
        reasons.append("region_overlap")
        score += 0.20
    elif region_kind == "unknown":
        reasons.append("region_unknown")
        score += 0.05
    else:
        return False, ["region_mismatch"], 0.0

    if tranche.get("sponsor_name") or tranche.get("sec_sponsor_name"):
        reasons.append("has_named_sponsor")
        score += 0.10

    return True, reasons, min(score, 1.0)


def build_match(tranche: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    matched, reasons, score = possible_overlap(tranche=tranche, event=event)
    if not matched:
        return None
    tranche_id = tranche.get("tranche_id") or tranche.get("source_url") or tranche.get("title")
    event_id = event.get("event_id") or event.get("source_event_id") or event.get("source_url")
    hash_key = f"{event_id}|{tranche_id}".encode()
    match_id = hashlib.sha1(hash_key).hexdigest()[:16]
    return {
        "match_id": match_id,
        "event_id": event_id,
        "event_name": event.get("event_name"),
        "event_peril_code": event.get("peril_code"),
        "event_region_codes": event.get("region_codes", []),
        "tranche_id": tranche_id,
        "tranche_name": tranche.get("tranche_name") or tranche.get("title"),
        "sponsor_name": tranche.get("sponsor_name") or tranche.get("sec_sponsor_name"),
        "tranche_peril_codes": tranche.get("peril_codes", []),
        "tranche_region_codes": tranche.get("region_codes", []),
        "match_status": "possible overlap",
        "score": round(score, 3),
        "reasons": reasons,
        "generated_at": utcnow_iso(),
    }
