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
_PUBLIC_MATCH_REASONS = {"peril_match", "active_date_overlap", "region_overlap"}
_LOW_CONFIDENCE_MATCH_REASONS = {"broad_peril_match", "region_unknown"}
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
_PROMOTION_HINTS: list[tuple[set[str], str]] = [
    ({"missing_sponsor"}, "add_sponsor_evidence"),
    ({"weak_region_evidence", "region_unknown"}, "strengthen_region_evidence"),
    ({"broad_peril", "broad_peril_match"}, "replace_broad_peril_classification"),
    ({"missing_maturity"}, "confirm_maturity_date"),
]


def _tranche_issue_flags(tranche: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if not (tranche.get("sponsor_name") or tranche.get("sec_sponsor_name")):
        flags.append("missing_sponsor")
    if "other_property_cat" in set(tranche.get("peril_codes", []) or []):
        flags.append("broad_peril")
    region_source = tranche.get("region_source_type") or tranche.get("region_inference_method")
    region_codes = tranche.get("region_codes", []) or []
    if not region_codes:
        flags.append("missing_region")
    elif region_source in {"missing", "peril_hint"}:
        flags.append("weak_region_evidence")
    if tranche.get("status") == "outstanding" and not tranche.get("maturity_date"):
        flags.append("missing_maturity")
    return flags


def _public_blockers(tranche: dict[str, Any], reasons: list[str], tranche_issue_flags: list[str]) -> list[str]:
    blockers: list[str] = []
    issue_flag_set = set(tranche_issue_flags)
    if "broad_peril_match" in reasons or "broad_peril" in issue_flag_set:
        blockers.append("broad_peril")
    if "region_unknown" in reasons or "missing_region" in issue_flag_set or "weak_region_evidence" in issue_flag_set:
        blockers.append("weak_region_evidence")
    if "missing_sponsor" in issue_flag_set:
        blockers.append("missing_sponsor")
    if "missing_maturity" in issue_flag_set:
        blockers.append("missing_maturity")
    return sorted(set(blockers))


def _candidate_reason_codes(reasons: list[str], public_blockers: list[str]) -> list[str]:
    candidate_reasons = [reason for reason in reasons if reason in _LOW_CONFIDENCE_MATCH_REASONS]
    candidate_reasons.extend(public_blockers)
    return sorted(set(candidate_reasons))


def _confidence_band(score: float, match_scope: str, candidate_reason_codes: list[str]) -> str:
    if match_scope == "public":
        return "high" if score >= 0.8 else "medium"
    if any(reason in {"broad_peril", "broad_peril_match", "weak_region_evidence", "region_unknown"} for reason in candidate_reason_codes):
        return "low"
    return "medium"


def _promotion_hint_codes(public_blockers: list[str], candidate_reason_codes: list[str]) -> list[str]:
    evidence_codes = set(public_blockers) | set(candidate_reason_codes)
    hints: list[str] = []
    for trigger_codes, hint_code in _PROMOTION_HINTS:
        if evidence_codes & trigger_codes:
            hints.append(hint_code)
    return hints


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


def build_match(
    tranche: dict[str, Any],
    event: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any] | None:
    matched, reasons, score = possible_overlap(tranche=tranche, event=event)
    if not matched:
        return None
    tranche_issue_flags = _tranche_issue_flags(tranche)
    public_blockers = _public_blockers(tranche, reasons, tranche_issue_flags)
    match_scope = "public" if _PUBLIC_MATCH_REASONS <= set(reasons) and not public_blockers else "candidate"
    candidate_reason_codes = _candidate_reason_codes(reasons, public_blockers)
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
        "event_latitude": event.get("event_latitude"),
        "event_longitude": event.get("event_longitude"),
        "event_bbox": event.get("event_bbox"),
        "event_source_name": event.get("source_name"),
        "event_source_url": event.get("source_url"),
        "event_source_record_id": event.get("source_record_id"),
        "tranche_id": tranche_id,
        "tranche_name": tranche.get("tranche_name") or tranche.get("title"),
        "sponsor_name": tranche.get("sponsor_name") or tranche.get("sec_sponsor_name"),
        "tranche_peril_codes": tranche.get("peril_codes", []),
        "tranche_region_codes": tranche.get("region_codes", []),
        "match_status": "possible overlap",
        "score": round(score, 3),
        "reasons": reasons,
        "match_scope": match_scope,
        "public_blockers": public_blockers,
        "candidate_reason_codes": candidate_reason_codes,
        "promotion_hint_codes": _promotion_hint_codes(public_blockers, candidate_reason_codes),
        "confidence_band": _confidence_band(score, match_scope, candidate_reason_codes),
        "tranche_issue_flags": tranche_issue_flags,
        "generated_at": generated_at or utcnow_iso(),
    }
