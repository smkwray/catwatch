from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from ..config import Settings
from ..utils import read_jsonl, utcnow_iso, write_json

DEMO_PAYLOAD = {
    "demo_mode": True,
    "as_of": "2026-03-18",
    "kpis": {
        "active_tranches": 3,
        "sponsors": 3,
        "next_12m_maturities": 2,
        "watchlist_matches": 2,
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
        },
    ],
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
    path = write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", DEMO_PAYLOAD)
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


def _watchlist_summary_text(exact_count: int, broad_count: int) -> str:
    parts: list[str] = []
    if exact_count:
        label = "overlap" if exact_count == 1 else "overlaps"
        parts.append(f"{exact_count} exact peril/date/geography {label}")
    if broad_count:
        label = "match" if broad_count == 1 else "matches"
        parts.append(f"{broad_count} broad-peril {label}")
    if not parts:
        return "Possible overlap based on public event and tranche records."
    return ". ".join(parts).capitalize() + " in the public tranche registry."


def _compute_kpis(tranches: list[dict], matches: list[dict], as_of: date) -> dict:
    material = _material_tranches(tranches)
    sponsors = {_canonical_sponsor(row) for row in material if _canonical_sponsor(row)}
    sponsors.discard(None)
    programmes = {row.get("programme_id") for row in material if row.get("programme_id")}
    active = [row for row in material if row.get("status") == "outstanding"]
    horizon = as_of + timedelta(days=365)
    exact_matches = [m for m in matches if "peril_match" in (m.get("reasons") or [])]
    return {
        "active_tranches": len(active),
        "programmes": len(programmes),
        "identified_sponsors": len(sponsors),
        "next_12m_maturities": sum(
            1
            for row in active
            if (maturity_date := _to_date(row.get("maturity_date"))) and as_of <= maturity_date <= horizon
        ),
        "watchlist_matches": len(exact_matches),
        "watchlist_broad_matches": len(matches) - len(exact_matches),
    }


def build_site_data(settings: Settings) -> str:
    tranches = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    matches = read_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl")
    events = read_jsonl(settings.processed_dir / "watchlist" / "events.jsonl")
    if not tranches:
        return write_demo_dashboard(settings)

    as_of = date.today()
    material = _material_tranches(tranches)
    by_tranche = {row["tranche_id"]: row for row in material if row.get("tranche_id")}
    by_event = {row["event_id"]: row for row in events if row.get("event_id")}

    grouped_watchlist: dict[tuple, dict] = {}
    for match in matches:
        event_id = match.get("event_id")
        event = by_event.get(event_id, {})
        event_name = event.get("event_name") or match.get("event_name") or event_id
        peril_code = event.get("peril_code") or match.get("event_peril_code")
        region_codes = event.get("region_codes") or match.get("event_region_codes", [])
        source_name = event.get("source_name")
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
                "matches": [],
            },
        )
        group["matches"].append(match)

    watchlist_cards = []
    for group in grouped_watchlist.values():
        event_matches = group["matches"]
        tranche_names: list[str] = []
        matched_rows_by_key: dict[str, dict] = {}
        for match in event_matches:
            tranche = by_tranche.get(match.get("tranche_id"))
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
            }
            match_key = str(match.get("tranche_id") or tranche_name)
            existing_row = matched_rows_by_key.get(match_key)
            if not existing_row or float(matched_row["score"]) > float(existing_row.get("score") or 0.0):
                matched_rows_by_key[match_key] = matched_row

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
        if not tranche_names:
            continue
        matched_rows = list(matched_rows_by_key.values())
        matched_rows.sort(key=lambda row: (-float(row.get("score") or 0.0), row.get("tranche_name") or ""))
        watchlist_cards.append(
            {
                "event_id": group.get("event_id"),
                "event_name": group.get("event_name") or group.get("event_id"),
                "peril_code": group.get("peril_code"),
                "region_codes": group.get("region_codes", []),
                "source_name": group.get("source_name"),
                "source_url": by_event.get(group.get("event_id"), {}).get("source_url"),
                "start_time": group.get("start_time"),
                "matched_tranches": tranche_names[:12],
                "matched_tranche_rows": matched_rows[:5],
                "matched_tranche_count": len(tranche_names),
                "exact_match_count": len(exact_tranche_ids),
                "broad_match_count": len(broad_tranche_ids),
                "top_score": max(float(match.get("score") or 0.0) for match in event_matches),
                "reason_text": _watchlist_summary_text(
                    exact_count=len(exact_tranche_ids), broad_count=len(broad_tranche_ids)
                ),
            }
        )

    watchlist_cards.sort(
        key=lambda row: (
            -_watchlist_source_priority(row.get("source_name")),
            -((_to_date(row.get("start_time")) or date.min).toordinal()),
            -int(row.get("exact_match_count") or 0),
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
            }
        )

    payload = {
        "demo_mode": False,
        "as_of": utcnow_iso()[:10],
        "kpis": _compute_kpis(tranches, matches, as_of=as_of),
        "maturity_wall": maturity_wall,
        "watchlist": watchlist_cards[:50],
        "sponsor_peril_matrix": matrix[:500],
        "notes": [
            "This is an initial public release and remains a work in progress.",
            "Possible overlap means the event peril, date, and coarse geography align with a public tranche record.",
            "Programme shells without a maturity date are excluded from watchlist matching and maturity KPIs.",
            "The sponsor-peril matrix only counts identified sponsors; rows without sponsor attribution are omitted.",
        ],
    }
    path = write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", payload)
    return str(path)
