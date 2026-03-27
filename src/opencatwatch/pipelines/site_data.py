from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from ..config import Settings
from ..utils import read_jsonl, write_json

_NON_GEOGRAPHIC_PERILS = {"cyber", "mortality"}

DEMO_PAYLOAD = {
    "demo_mode": True,
    "as_of": "2026-03-18",
    "kpis": {
        "active_tranches": 3,
        "sponsors": 3,
        "next_12m_maturities": 2,
        "watchlist_matches": 2,
        "watchlist_review_candidates": 0,
    },
    "maturity_wall": [
        {
            "tranche_name": "Demo Re Series 2026-1 Class A",
            "sponsor_name": "Demo Sponsor",
            "listed_date": "2025-06-01",
            "maturity_date": "2026-06-01",
            "peril_codes": ["us_wind"],
            "review_status": "demo",
            "source_url": "https://example.com/demo-re",
            "sponsor_source_url": "https://example.com/demo-sponsor",
            "sponsor_source_type": "manual_demo",
            "peril_source_type": "manual_demo",
            "peril_source_url": "https://example.com/demo-re",
            "peril_source_note": None,
            "region_source_type": "manual_demo",
            "region_source_url": "https://example.com/demo-re",
            "region_source_note": None,
            "maturity_source_type": "manual_demo",
            "maturity_source_url": "https://example.com/demo-re",
            "maturity_source_note": None,
        },
        {
            "tranche_name": "Golden State Re 2026-1",
            "sponsor_name": "Golden State Insurer",
            "listed_date": "2025-07-15",
            "maturity_date": "2028-07-14",
            "peril_codes": ["ca_wildfire", "ca_earthquake"],
            "review_status": "demo",
            "source_url": "https://example.com/golden-state-re",
            "sponsor_source_url": "https://example.com/golden-state-sponsor",
            "sponsor_source_type": "manual_demo",
            "peril_source_type": "manual_demo",
            "peril_source_url": "https://example.com/golden-state-re",
            "peril_source_note": None,
            "region_source_type": "manual_demo",
            "region_source_url": "https://example.com/golden-state-re",
            "region_source_note": None,
            "maturity_source_type": "manual_demo",
            "maturity_source_url": "https://example.com/golden-state-re",
            "maturity_source_note": None,
        },
        {
            "tranche_name": "Pacific Quake Re 2025-1",
            "sponsor_name": "Pacific Sponsor",
            "listed_date": "2025-03-01",
            "maturity_date": "2027-03-01",
            "peril_codes": ["ca_earthquake"],
            "review_status": "demo",
            "source_url": "https://example.com/pacific-quake-re",
            "sponsor_source_url": "https://example.com/pacific-quake-sponsor",
            "sponsor_source_type": "manual_demo",
            "peril_source_type": "manual_demo",
            "peril_source_url": "https://example.com/pacific-quake-re",
            "peril_source_note": None,
            "region_source_type": "manual_demo",
            "region_source_url": "https://example.com/pacific-quake-re",
            "region_source_note": None,
            "maturity_source_type": "manual_demo",
            "maturity_source_url": "https://example.com/pacific-quake-re",
            "maturity_source_note": None,
        },
    ],
    "watchlist": [
        {
            "event_id": "demo-event-1",
            "event_name": "California Red Flag Warning",
            "peril_code": "ca_wildfire",
            "region_codes": ["california"],
            "matched_tranches": ["Golden State Re 2026-1"],
            "matched_tranche_rows": [
                {
                    "tranche_name": "Golden State Re 2026-1",
                    "sponsor_name": "Golden State Insurer",
                    "review_status": "demo",
                    "score": 0.9,
                    "reason_text": "Peril, date, and coarse geography overlap based on public records.",
                    "source_url": "https://example.com/golden-state-re",
                    "sponsor_source_url": "https://example.com/golden-state-sponsor",
                    "sponsor_source_type": "manual_demo",
                }
            ],
            "reason_text": "1 exact peril/date/geography overlap in the public tranche registry.",
            "source_name": "nws",
            "source_url": "https://example.com/demo-event-1",
            "source_record_id": "demo-event-1",
            "match_scope": "public",
            "public_blockers": [],
            "candidate_reason_codes": [],
            "confidence_band": "high",
        },
        {
            "event_id": "demo-event-2",
            "event_name": "M6.2 offshore California earthquake",
            "peril_code": "ca_earthquake",
            "region_codes": ["california"],
            "matched_tranches": ["Golden State Re 2026-1", "Pacific Quake Re 2025-1"],
            "matched_tranche_rows": [
                {
                    "tranche_name": "Golden State Re 2026-1",
                    "sponsor_name": "Golden State Insurer",
                    "review_status": "demo",
                    "score": 0.92,
                    "reason_text": "Peril, date, and coarse geography overlap based on public records.",
                    "source_url": "https://example.com/golden-state-re",
                    "sponsor_source_url": "https://example.com/golden-state-sponsor",
                    "sponsor_source_type": "manual_demo",
                },
                {
                    "tranche_name": "Pacific Quake Re 2025-1",
                    "sponsor_name": "Pacific Sponsor",
                    "review_status": "demo",
                    "score": 0.91,
                    "reason_text": "Peril, date, and coarse geography overlap based on public records.",
                    "source_url": "https://example.com/pacific-quake-re",
                    "sponsor_source_url": "https://example.com/pacific-quake-sponsor",
                    "sponsor_source_type": "manual_demo",
                },
            ],
            "reason_text": "2 exact peril/date/geography overlaps in the public tranche registry.",
            "source_name": "usgs",
            "source_url": "https://example.com/demo-event-2",
            "source_record_id": "demo-event-2",
            "match_scope": "public",
            "public_blockers": [],
            "candidate_reason_codes": [],
            "confidence_band": "high",
        },
    ],
    "watchlist_review_candidates": [],
    "watchlist_diagnostics": {
        "public_match_count": 2,
        "candidate_match_count": 0,
        "public_rows_with_blockers": 0,
        "candidate_reason_counts": [],
        "public_blocker_counts": [],
        "confidence_band_counts": [{"confidence_band": "high", "count": 2}],
        "top_candidate_families": [],
    },
    "limitations": ["Demo mode only; real unresolved families are published in the committed audit snapshot."],
    "sponsor_peril_matrix": [
        {"sponsor_name": "Golden State Insurer", "peril_code": "ca_wildfire", "count": 1},
        {"sponsor_name": "Golden State Insurer", "peril_code": "ca_earthquake", "count": 1},
        {"sponsor_name": "Pacific Sponsor", "peril_code": "ca_earthquake", "count": 1},
        {"sponsor_name": "Demo Sponsor", "peril_code": "us_wind", "count": 1},
    ],
    "notes": [
        "This is an initial public release and remains a work in progress.",
        "Watchlist matches are possible overlaps, not confirmed triggers.",
        "This dashboard is static and precomputed for GitHub Pages deployment.",
    ],
}


def write_demo_dashboard(settings: Settings) -> str:
    path = write_json(settings.dashboard_path, DEMO_PAYLOAD)
    return str(path)


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


def _canonical_sponsor(row: dict) -> str | None:
    return row.get("sponsor_name") or row.get("sec_sponsor_name")


def _watchlist_source_priority(source_name: str | None) -> int:
    priorities = {"nws": 4, "openfema": 3, "noaa_stormevents": 2, "usgs": 1}
    return priorities.get(source_name or "", 0)


def _material_tranches(tranches: list[dict]) -> list[dict]:
    return [row for row in tranches if not row.get("is_programme_shell")]


def _reason_text(reasons: list[str] | None) -> str:
    if not reasons:
        return "Possible overlap based on the available public tranche and event records."

    parts: list[str] = []
    if "peril_match" in reasons:
        parts.append("peril")
    if "active_date_overlap" in reasons:
        parts.append("date")
    if "region_overlap" in reasons:
        parts.append("coarse geography")
    if "region_unknown" in reasons:
        parts.append("date overlap with incomplete region evidence")
    if "broad_peril_match" in reasons:
        return "Possible overlap based on a broad property-cat peril mapping plus date and coarse geography checks."
    if parts:
        return f"{', '.join(parts)} overlap based on public records."
    return "Possible overlap based on the available public tranche and event records."


def _is_public_match(match: dict) -> bool:
    if match.get("match_scope"):
        return match.get("match_scope") == "public"
    reasons = set(match.get("reasons") or [])
    return {"peril_match", "active_date_overlap", "region_overlap"} <= reasons


def _requires_region_evidence(row: dict) -> bool:
    peril_codes = set(row.get("peril_codes") or [])
    if not peril_codes:
        return True
    return not peril_codes.issubset(_NON_GEOGRAPHIC_PERILS)


def _family_name(row: dict) -> str:
    issuer_name = (row.get("issuer_name") or "").strip()
    if issuer_name:
        return issuer_name
    tranche_name = (row.get("tranche_name") or "").strip()
    for separator in (" Series ", " series ", " due ", " Due ", " Class ", " class "):
        if separator in tranche_name:
            return tranche_name.split(separator, 1)[0].strip()
    return tranche_name or "unknown"


def _collect_limitations(material: list[dict], limit: int = 8) -> list[str]:
    families: dict[str, Counter[str]] = {}
    for row in material:
        family = _family_name(row)
        counts = families.setdefault(family, Counter())
        if not _canonical_sponsor(row):
            counts["missing sponsor evidence"] += 1
        if _requires_region_evidence(row) and not row.get("region_codes"):
            counts["missing region evidence"] += 1
        if "other_property_cat" in (row.get("peril_codes") or []):
            counts["broad peril classification"] += 1
        if row.get("status") == "outstanding" and not row.get("maturity_date"):
            counts["missing maturity"] += 1
    ranked = sorted(
        ((family, counts, sum(counts.values())) for family, counts in families.items() if counts),
        key=lambda item: (-item[2], item[0]),
    )
    limitations: list[str] = []
    for family, counts, _ in ranked[:limit]:
        issue_text = ", ".join(f"{count} {issue}" for issue, count in counts.most_common(3))
        limitations.append(f"{family}: {issue_text}.")
    return limitations


def _watchlist_diagnostics(matches: list[dict], by_tranche: dict[str, dict]) -> dict:
    normalized_matches = []
    for match in matches:
        tranche = by_tranche.get(str(match.get("tranche_id") or ""))
        contract = _match_contract(match, tranche)
        normalized_matches.append({**match, **contract})
    public_matches = [match for match in normalized_matches if _is_public_match(match)]
    candidate_matches = [match for match in normalized_matches if not _is_public_match(match)]
    candidate_reason_counts: Counter[str] = Counter()
    public_blocker_counts: Counter[str] = Counter()
    confidence_band_counts: Counter[str] = Counter()
    top_candidate_families: Counter[str] = Counter()
    public_rows_with_blockers = 0
    for match in normalized_matches:
        blockers = list(match.get("public_blockers") or [])
        if _is_public_match(match) and blockers:
            public_rows_with_blockers += 1
        for blocker in blockers:
            public_blocker_counts[blocker] += 1
        for reason in match.get("candidate_reason_codes") or []:
            candidate_reason_counts[reason] += 1
        confidence_band_counts[str(match.get("confidence_band") or "unknown")] += 1
        if not _is_public_match(match):
            tranche = by_tranche.get(str(match.get("tranche_id") or ""))
            family_name = _family_name(tranche or {"tranche_name": match.get("tranche_name")})
            top_candidate_families[family_name] += 1
    return {
        "public_match_count": len(public_matches),
        "candidate_match_count": len(candidate_matches),
        "public_rows_with_blockers": public_rows_with_blockers,
        "candidate_reason_counts": [
            {"reason_code": reason_code, "count": count}
            for reason_code, count in sorted(candidate_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "public_blocker_counts": [
            {"blocker_code": blocker_code, "count": count}
            for blocker_code, count in sorted(public_blocker_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "confidence_band_counts": [
            {"confidence_band": band, "count": count}
            for band, count in sorted(confidence_band_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "top_candidate_families": [
            {"family_name": family_name, "count": count}
            for family_name, count in top_candidate_families.most_common(8)
        ],
    }


def _watchlist_summary_text(public_count: int, candidate_count: int) -> str:
    parts: list[str] = []
    if public_count:
        label = "overlap" if public_count == 1 else "overlaps"
        parts.append(f"{public_count} public peril/date/geography {label}")
    if candidate_count:
        label = "candidate" if candidate_count == 1 else "candidates"
        parts.append(f"{candidate_count} lower-confidence review {label}")
    if not parts:
        return "Possible overlap based on public event and tranche records."
    return ". ".join(parts).capitalize() + " in the public tranche registry."


def _watchlist_candidate_summary_text(candidate_count: int, public_count: int) -> str:
    parts: list[str] = []
    if candidate_count:
        label = "candidate" if candidate_count == 1 else "candidates"
        parts.append(f"{candidate_count} review {label} with broad peril or incomplete region evidence")
    if public_count:
        label = "overlap" if public_count == 1 else "overlaps"
        parts.append(f"{public_count} separate public {label} for the same event")
    return ". ".join(parts).capitalize() + "."


def _fallback_tranche_issue_flags(tranche: dict | None) -> list[str]:
    tranche = tranche or {}
    flags: list[str] = []
    if not _canonical_sponsor(tranche):
        flags.append("missing_sponsor")
    if "other_property_cat" in set(tranche.get("peril_codes") or []):
        flags.append("broad_peril")
    region_source = tranche.get("region_source_type") or tranche.get("region_inference_method")
    region_codes = tranche.get("region_codes") or []
    if _requires_region_evidence(tranche) and not region_codes:
        flags.append("missing_region")
    elif _requires_region_evidence(tranche) and region_source in {"missing", "peril_hint"}:
        flags.append("weak_region_evidence")
    if tranche.get("status") == "outstanding" and not tranche.get("maturity_date"):
        flags.append("missing_maturity")
    return flags


def _fallback_match_contract(match: dict, tranche: dict | None) -> dict:
    reasons = list(match.get("reasons") or [])
    tranche_issue_flags = _fallback_tranche_issue_flags(tranche)
    public_blockers: list[str] = []
    if "broad_peril_match" in reasons or "broad_peril" in tranche_issue_flags:
        public_blockers.append("broad_peril")
    if "region_unknown" in reasons or "missing_region" in tranche_issue_flags or "weak_region_evidence" in tranche_issue_flags:
        public_blockers.append("weak_region_evidence")
    if "missing_sponsor" in tranche_issue_flags:
        public_blockers.append("missing_sponsor")
    if "missing_maturity" in tranche_issue_flags:
        public_blockers.append("missing_maturity")
    public_blockers = sorted(set(public_blockers))
    match_scope = (
        "public"
        if {"peril_match", "active_date_overlap", "region_overlap"} <= set(reasons) and not public_blockers
        else "candidate"
    )
    candidate_reason_codes = sorted(
        set([reason for reason in reasons if reason in {"broad_peril_match", "region_unknown"}] + public_blockers)
    )
    if match_scope == "public":
        confidence_band = "high" if float(match.get("score") or 0.0) >= 0.8 else "medium"
    elif any(
        reason in {"broad_peril", "broad_peril_match", "weak_region_evidence", "region_unknown"}
        for reason in candidate_reason_codes
    ):
        confidence_band = "low"
    else:
        confidence_band = "medium"
    return {
        "match_scope": match_scope,
        "public_blockers": public_blockers,
        "candidate_reason_codes": candidate_reason_codes,
        "confidence_band": confidence_band,
        "tranche_issue_flags": tranche_issue_flags,
    }


def _match_contract(match: dict, tranche: dict | None) -> dict:
    if {
        "match_scope",
        "public_blockers",
        "candidate_reason_codes",
        "confidence_band",
        "tranche_issue_flags",
    } <= set(match):
        return {
            "match_scope": match.get("match_scope"),
            "public_blockers": match.get("public_blockers") or [],
            "candidate_reason_codes": match.get("candidate_reason_codes") or [],
            "confidence_band": match.get("confidence_band"),
            "tranche_issue_flags": match.get("tranche_issue_flags") or [],
        }
    return _fallback_match_contract(match, tranche)


def _build_watchlist_card(
    group: dict,
    event_matches: list[dict],
    by_event: dict[str, dict],
    by_tranche: dict[str, dict],
    match_scope: str,
    related_match_count: int = 0,
) -> dict | None:
    tranche_names: list[str] = []
    matched_rows_by_key: dict[str, dict] = {}
    for match in event_matches:
        tranche = by_tranche.get(match.get("tranche_id"))
        contract = _match_contract(match, tranche)
        tranche_name = match.get("tranche_name")
        if not tranche_name:
            tranche_name = tranche.get("tranche_name") if tranche else None
        if tranche_name and tranche_name not in tranche_names:
            tranche_names.append(tranche_name)
        if not tranche_name:
            continue
        matched_row = {
            "tranche_id": match.get("tranche_id"),
            "tranche_name": tranche_name,
            "sponsor_name": match.get("sponsor_name")
            or (tranche.get("sponsor_name") if tranche else None)
            or (tranche.get("sec_sponsor_name") if tranche else None),
            "review_status": tranche.get("review_status") if tranche else None,
            "score": round(float(match.get("score") or 0.0), 3),
            "reason_text": _reason_text(match.get("reasons") or []),
            "source_url": tranche.get("source_url") if tranche else None,
            "sponsor_source_url": tranche.get("sponsor_source_url") if tranche else None,
            "sponsor_source_type": tranche.get("sponsor_source") if tranche else None,
            "peril_source_type": tranche.get("peril_source_type") if tranche else None,
            "peril_source_url": tranche.get("peril_source_url") if tranche else None,
            "peril_source_note": tranche.get("peril_source_note") if tranche else None,
            "region_source_type": tranche.get("region_source_type") if tranche else None,
            "region_source_url": tranche.get("region_source_url") if tranche else None,
            "region_source_note": tranche.get("region_source_note") if tranche else None,
            "maturity_source_type": tranche.get("maturity_source_type") if tranche else None,
            "maturity_source_url": tranche.get("maturity_source_url") if tranche else None,
            "maturity_source_note": tranche.get("maturity_source_note") if tranche else None,
            "tranche_issue_flags": contract["tranche_issue_flags"],
            "public_blockers": contract["public_blockers"],
            "candidate_reason_codes": contract["candidate_reason_codes"],
            "confidence_band": contract["confidence_band"],
        }
        match_key = str(match.get("tranche_id") or tranche_name)
        existing_row = matched_rows_by_key.get(match_key)
        if not existing_row or float(matched_row["score"]) > float(existing_row.get("score") or 0.0):
            matched_rows_by_key[match_key] = matched_row

    if not tranche_names:
        return None

    event = by_event.get(group.get("event_id"), {})
    matched_rows = list(matched_rows_by_key.values())
    matched_rows.sort(key=lambda row: (-float(row.get("score") or 0.0), row.get("tranche_name") or ""))
    exact_tranche_ids = {
        match.get("tranche_id")
        for match in event_matches
        if "peril_match" in (match.get("reasons") or []) and match.get("tranche_id")
    }
    broad_tranche_ids = {
        match.get("tranche_id")
        for match in event_matches
        if "broad_peril_match" in (match.get("reasons") or []) and match.get("tranche_id")
    }
    reason_text = (
        _watchlist_summary_text(public_count=len(exact_tranche_ids), candidate_count=related_match_count)
        if match_scope == "public"
        else _watchlist_candidate_summary_text(candidate_count=len(tranche_names), public_count=related_match_count)
    )
    contracts = [_match_contract(match, by_tranche.get(match.get("tranche_id"))) for match in event_matches]
    public_blockers = sorted({blocker for contract in contracts for blocker in contract["public_blockers"]})
    candidate_reason_codes = sorted({reason for contract in contracts for reason in contract["candidate_reason_codes"]})
    confidence_bands = Counter(str(contract.get("confidence_band") or "unknown") for contract in contracts)
    return {
        "event_id": group.get("event_id"),
        "event_name": group.get("event_name") or group.get("event_id"),
        "peril_code": group.get("peril_code"),
        "region_codes": group.get("region_codes", []),
        "source_name": group.get("source_name"),
        "source_url": event.get("source_url") or group.get("source_url"),
        "source_record_id": event.get("source_record_id") or group.get("source_record_id"),
        "start_time": group.get("start_time"),
        "matched_tranches": tranche_names[:12],
        "matched_tranche_rows": matched_rows[:5],
        "matched_tranche_count": len(tranche_names),
        "exact_match_count": len(exact_tranche_ids),
        "broad_match_count": len(broad_tranche_ids),
        "candidate_match_count": related_match_count if match_scope == "public" else len(tranche_names),
        "top_score": max(float(match.get("score") or 0.0) for match in event_matches),
        "match_scope": match_scope,
        "public_blockers": public_blockers,
        "candidate_reason_codes": candidate_reason_codes,
        "confidence_band": confidence_bands.most_common(1)[0][0] if confidence_bands else "unknown",
        "reason_text": reason_text,
    }


def _compute_kpis(tranches: list[dict], matches: list[dict], as_of: date) -> dict:
    material = _material_tranches(tranches)
    sponsors = {_canonical_sponsor(row) for row in material if _canonical_sponsor(row)}
    sponsors.discard(None)
    programmes = {row.get("programme_id") for row in material if row.get("programme_id")}
    active = [row for row in material if row.get("status") == "outstanding"]
    horizon = as_of + timedelta(days=365)
    public_matches = [m for m in matches if _is_public_match(m)]
    review_candidates = [m for m in matches if not _is_public_match(m)]
    broad_matches = [m for m in matches if "broad_peril_match" in (m.get("reasons") or [])]
    return {
        "active_tranches": len(active),
        "programmes": len(programmes),
        "identified_sponsors": len(sponsors),
        "next_12m_maturities": sum(
            1
            for row in active
            if (maturity_date := _to_date(row.get("maturity_date"))) and as_of <= maturity_date <= horizon
        ),
        "watchlist_matches": len(public_matches),
        "watchlist_review_candidates": len(review_candidates),
        "watchlist_broad_matches": len(broad_matches),
    }


def build_site_data(settings: Settings) -> str:
    tranches = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    matches = read_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl")
    events = read_jsonl(settings.processed_dir / "watchlist" / "events.jsonl")
    if not tranches:
        return write_demo_dashboard(settings)

    as_of = settings.as_of_date
    material = _material_tranches(tranches)
    by_tranche = {row["tranche_id"]: row for row in material if row.get("tranche_id")}
    by_event = {row["event_id"]: row for row in events if row.get("event_id")}
    diagnostics = _watchlist_diagnostics(matches, by_tranche)
    limitations = _collect_limitations(material)

    grouped_watchlist: dict[tuple, dict] = {}
    for match in matches:
        event_id = match.get("event_id")
        event = by_event.get(event_id, {})
        event_name = event.get("event_name") or match.get("event_name") or event_id
        peril_code = event.get("peril_code") or match.get("event_peril_code")
        region_codes = event.get("region_codes") or match.get("event_region_codes", [])
        source_name = event.get("source_name") or match.get("event_source_name")
        start_time = event.get("start_time")
        group_key = (
            event_name,
            peril_code,
            tuple(sorted(region_codes or [])),
            source_name,
            (_to_date(start_time) or date.min).isoformat(),
        )
        group = grouped_watchlist.setdefault(
            group_key,
            {
                "event_id": event_id,
                "event_name": event_name,
                "peril_code": peril_code,
                "region_codes": region_codes,
                "source_name": source_name,
                "start_time": start_time,
                "source_url": event.get("source_url") or match.get("event_source_url"),
                "source_record_id": event.get("source_record_id") or match.get("event_source_record_id"),
                "public_matches": [],
                "candidate_matches": [],
            },
        )
        if _is_public_match(match):
            group["public_matches"].append(match)
        else:
            group["candidate_matches"].append(match)

    watchlist_cards = []
    candidate_watchlist_cards = []
    for group in grouped_watchlist.values():
        if group["public_matches"]:
            public_card = _build_watchlist_card(
                group=group,
                event_matches=group["public_matches"],
                by_event=by_event,
                by_tranche=by_tranche,
                match_scope="public",
                related_match_count=len({m.get("tranche_id") for m in group["candidate_matches"] if m.get("tranche_id")}),
            )
            if public_card:
                watchlist_cards.append(public_card)
        if group["candidate_matches"]:
            candidate_card = _build_watchlist_card(
                group=group,
                event_matches=group["candidate_matches"],
                by_event=by_event,
                by_tranche=by_tranche,
                match_scope="candidate",
                related_match_count=len({m.get("tranche_id") for m in group["public_matches"] if m.get("tranche_id")}),
            )
            if candidate_card:
                candidate_watchlist_cards.append(candidate_card)

    watchlist_cards.sort(
        key=lambda row: (
            -_watchlist_source_priority(row.get("source_name")),
            -((_to_date(row.get("start_time")) or date.min).toordinal()),
            -int(row.get("exact_match_count") or 0),
            -float(row.get("top_score") or 0.0),
            row.get("event_name") or "",
        )
    )
    candidate_watchlist_cards.sort(
        key=lambda row: (
            -_watchlist_source_priority(row.get("source_name")),
            -((_to_date(row.get("start_time")) or date.min).toordinal()),
            -int(row.get("matched_tranche_count") or 0),
            -float(row.get("top_score") or 0.0),
            row.get("event_name") or "",
        )
    )

    matrix_counter: Counter[tuple[str, str]] = Counter()
    for row in material:
        sponsor = _canonical_sponsor(row)
        if not sponsor:
            continue
        for peril in row.get("peril_codes", []):
            matrix_counter[(sponsor, peril)] += 1

    matrix = [
        {"sponsor_name": sponsor, "peril_code": peril, "count": count}
        for (sponsor, peril), count in sorted(
            matrix_counter.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
    ]

    maturity_wall = []
    maturities = [row for row in material if row.get("maturity_date")]
    maturities.sort(key=lambda row: (row.get("maturity_date") or "9999-99-99", row.get("tranche_name") or ""))
    for row in maturities[:200]:
        maturity_wall.append(
            {
                "tranche_id": row.get("tranche_id"),
                "tranche_name": row.get("tranche_name"),
                "sponsor_name": _canonical_sponsor(row),
                "listed_date": row.get("listed_date"),
                "maturity_date": row.get("maturity_date"),
                "peril_codes": row.get("peril_codes", []),
                "review_status": row.get("review_status"),
                "source_url": row.get("source_url"),
                "sponsor_source_url": row.get("sponsor_source_url"),
                "sponsor_source_type": row.get("sponsor_source"),
                "peril_source_type": row.get("peril_source_type"),
                "peril_source_url": row.get("peril_source_url"),
                "peril_source_note": row.get("peril_source_note"),
                "region_source_type": row.get("region_source_type"),
                "region_source_url": row.get("region_source_url"),
                "region_source_note": row.get("region_source_note"),
                "maturity_source_type": row.get("maturity_source_type"),
                "maturity_source_url": row.get("maturity_source_url"),
                "maturity_source_note": row.get("maturity_source_note"),
            }
        )

    payload = {
        "demo_mode": False,
        "as_of": as_of.isoformat(),
        "kpis": _compute_kpis(tranches, matches, as_of=as_of),
        "maturity_wall": maturity_wall,
        "watchlist": watchlist_cards[:50],
        "watchlist_review_candidates": candidate_watchlist_cards[:25],
        "watchlist_diagnostics": diagnostics,
        "limitations": limitations,
        "sponsor_peril_matrix": matrix[:500],
        "notes": [
            "This is an initial public release and remains a work in progress.",
            "Public watchlist rows require exact peril/date/geography overlap plus tranche evidence strong enough for public display; lower-confidence candidates are separated.",
            "Programme shells without a maturity date are excluded from watchlist matching and maturity KPIs.",
            "The sponsor-peril matrix only counts identified sponsors; rows without sponsor attribution are omitted.",
        ],
    }
    path = write_json(settings.dashboard_path, payload)
    return str(path)
