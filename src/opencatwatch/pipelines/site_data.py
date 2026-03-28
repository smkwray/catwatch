from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from ..config import Settings
from ..utils import read_jsonl, write_json

_NON_GEOGRAPHIC_PERILS = {"cyber", "mortality"}

DEMO_PAYLOAD = {
    "demo_mode": True,
    "as_of": "2026-03-18",
    "kpis": {
        "active_tranches": 3,
        "identified_sponsors": 3,
        "programmes": 3,
        "next_12m_maturities": 2,
        "watchlist_matches": 2,
        "watchlist_review_candidates": 0,
        "watchlist_broad_matches": 0,
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
            "issue_amount": 100000000,
            "issue_amount_source_type": "manual_demo",
            "issue_amount_source_url": "https://example.com/demo-re",
            "issue_amount_source_note": None,
            "currency": "USD",
            "region_codes": ["us"],
            "listing_status": "Listed",
            "status": "outstanding",
            "bma_regulator_class": "Special Purpose Insurer",
            "attribution_status": {
                "sponsor": "manual_demo",
                "peril": "manual_demo",
                "region": "manual_demo",
                "maturity": "manual_demo",
            },
            "sponsor_attribution_state": "manual_demo",
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
            "issue_amount": 125000000,
            "issue_amount_source_type": "manual_demo",
            "issue_amount_source_url": "https://example.com/golden-state-re",
            "issue_amount_source_note": None,
            "currency": "USD",
            "region_codes": ["california"],
            "listing_status": "Listed",
            "status": "outstanding",
            "bma_regulator_class": "Restricted Special Purpose Insurer",
            "attribution_status": {
                "sponsor": "manual_demo",
                "peril": "manual_demo",
                "region": "manual_demo",
                "maturity": "manual_demo",
            },
            "sponsor_attribution_state": "manual_demo",
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
            "issue_amount": 150000000,
            "issue_amount_source_type": "manual_demo",
            "issue_amount_source_url": "https://example.com/pacific-quake-re",
            "issue_amount_source_note": None,
            "currency": "USD",
            "region_codes": ["california"],
            "listing_status": "Listed",
            "status": "outstanding",
            "bma_regulator_class": "Special Purpose Insurer",
            "attribution_status": {
                "sponsor": "manual_demo",
                "peril": "manual_demo",
                "region": "manual_demo",
                "maturity": "manual_demo",
            },
            "sponsor_attribution_state": "manual_demo",
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
            "event_geo": {"latitude": 36.7783, "longitude": -119.4179, "bbox": None},
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
            "event_geo": {"latitude": 36.7783, "longitude": -119.4179, "bbox": None},
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
        "promotion_hint_counts": [],
        "top_candidate_families": [],
        "top_candidate_blockers_by_family": [],
    },
    "limitations": ["Demo mode only; real unresolved families are published in the committed audit snapshot."],
    "sponsor_peril_matrix": [
        {"sponsor_name": "Golden State Insurer", "peril_code": "ca_wildfire", "count": 1},
        {"sponsor_name": "Golden State Insurer", "peril_code": "ca_earthquake", "count": 1},
        {"sponsor_name": "Pacific Sponsor", "peril_code": "ca_earthquake", "count": 1},
        {"sponsor_name": "Demo Sponsor", "peril_code": "us_wind", "count": 1},
    ],
    "capital_summary": {
        "known_amount_rows": 3,
        "missing_amount_rows": 0,
        "non_usd_rows": 0,
        "by_peril": [
            {"group_key": "ca_earthquake", "currency": "USD", "tranche_count": 2, "total_issue_amount": 275000000},
            {"group_key": "ca_wildfire", "currency": "USD", "tranche_count": 1, "total_issue_amount": 125000000},
            {"group_key": "us_wind", "currency": "USD", "tranche_count": 1, "total_issue_amount": 100000000},
        ],
        "by_sponsor": [
            {"group_key": "Golden State Insurer", "currency": "USD", "tranche_count": 1, "total_issue_amount": 125000000}
        ],
        "by_listed_year": [
            {"group_key": "2025", "currency": "USD", "tranche_count": 3, "total_issue_amount": 375000000}
        ],
    },
    "region_detail": [
        {
            "region_code": "california",
            "display_name": "California, US",
            "tranche_count": 2,
            "outstanding_tranche_count": 2,
            "known_amount_rows": 2,
            "currency_breakdown": [{"currency": "USD", "count": 2}],
            "top_perils": [{"peril_code": "ca_earthquake", "count": 2}, {"peril_code": "ca_wildfire", "count": 1}],
        }
    ],
    "coverage_gaps": {
        "missing_issue_amount": 0,
        "missing_region": 0,
        "missing_maturity": 0,
        "missing_trigger_type": 3,
        "missing_sponsor": 0,
        "missing_region_geocoding": 0,
    },
    "trigger_summary": {
        "known_trigger_rows": 0,
        "missing_trigger_rows": 3,
        "by_trigger_type": [],
    },
    "registry_stats": {
        "total_rows": 3,
        "material_tranches": 3,
        "programme_shells": 0,
        "identified_sponsors": 3,
        "amount_present_rows": 3,
        "amount_missing_rows": 0,
        "currency_breakdown": [{"currency": "USD", "count": 3}],
        "status_breakdown": [{"status": "outstanding", "count": 3}],
        "listing_status_breakdown": [{"listing_status": "Listed", "count": 3}],
    },
    "region_map": [
        {
            "region_code": "california",
            "display_name": "California, US",
            "iso_alpha2": "US",
            "latitude": 36.77,
            "longitude": -119.42,
            "map_zoom_level": 5,
            "tranche_count": 2,
            "known_amount_rows": 2,
            "capital_by_currency": [{"currency": "USD", "total_issue_amount": 275000000}],
            "dominant_perils": [{"peril_code": "ca_earthquake", "count": 2}, {"peril_code": "ca_wildfire", "count": 1}],
        }
    ],
    "gap_spotlight": {"top_missing_issue_amount": [], "top_missing_sponsor": []},
    "story_blocks": {
        "top_sponsors_by_capital": [
            {
                "sponsor_name": "Golden State Insurer",
                "currency": "USD",
                "tranche_count": 1,
                "total_issue_amount": 125000000,
            }
        ],
        "top_regions_by_capital": [
            {
                "region_code": "california",
                "display_name": "California, US",
                "currency": "USD",
                "tranche_count": 2,
                "total_issue_amount": 275000000,
            }
        ],
        "top_perils_by_capital": [
            {
                "peril_code": "ca_earthquake",
                "currency": "USD",
                "tranche_count": 2,
                "total_issue_amount": 275000000,
            },
            {
                "peril_code": "ca_wildfire",
                "currency": "USD",
                "tranche_count": 1,
                "total_issue_amount": 125000000,
            },
        ],
        "market_timeline": [
            {"listed_year": "2025", "currency": "USD", "tranche_count": 3, "total_issue_amount": 375000000}
        ],
        "maturity_runway": [
            {"window_months": 12, "currency": "USD", "tranche_count": 1, "total_issue_amount": 100000000},
            {"window_months": 24, "currency": "USD", "tranche_count": 1, "total_issue_amount": 100000000},
            {"window_months": 36, "currency": "USD", "tranche_count": 3, "total_issue_amount": 375000000},
        ],
        "upcoming_maturities_by_region": [
            {
                "window_months": 24,
                "region_code": "california",
                "display_name": "California, US",
                "currency": "USD",
                "tranche_count": 1,
                "total_issue_amount": 100000000,
            }
        ],
        "capital_concentration": [
            {
                "currency": "USD",
                "total_known_issue_amount": 375000000,
                "top_5_sponsor_share_pct": 100.0,
                "top_3_region_share_pct": 100.0,
            }
        ],
        "coverage_scorecard": {
            "material_tranche_count": 3,
            "identified_sponsors": 3,
            "sponsor_coverage_pct": 100.0,
            "region_coverage_pct": 100.0,
            "amount_coverage_pct": 100.0,
            "trigger_coverage_pct": 0.0,
            "missing_issue_amount_rows": 0,
            "missing_trigger_rows": 3,
        },
        "unresolved_families": [],
        "candidate_blockers_summary": {
            "top_candidate_reasons": [],
            "top_promotion_hints": [],
            "top_candidate_families": [],
        },
        "watchlist_pressure": {
            "public_match_count": 2,
            "candidate_match_count": 0,
            "candidate_ratio_pct": 0.0,
            "top_promotion_hints": [],
            "top_candidate_blockers_by_family": [],
        },
    },
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


def _parse_issue_amount(value: object) -> float | int | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else round(number, 2)


def _year_group(value: str | None) -> str:
    parsed = _to_date(value)
    return str(parsed.year) if parsed else "unknown"


def _display_region_name(region_code: str, geocoding: dict[str, dict]) -> str:
    entry = geocoding.get(region_code)
    if entry and entry.get("display_name"):
        return str(entry["display_name"])
    if region_code == "us":
        return "United States"
    return region_code.replace("_", " ").title()


def _load_region_geocoding(settings: Settings) -> dict[str, dict]:
    path = settings.manual_dir / "region_geocoding.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    geocoding: dict[str, dict] = {}
    for row in rows:
        region_code = (row.get("region_code") or "").strip()
        if not region_code:
            continue
        try:
            latitude = float(row["latitude"]) if row.get("latitude") else None
            longitude = float(row["longitude"]) if row.get("longitude") else None
            map_zoom_level = int(float(row["map_zoom_level"])) if row.get("map_zoom_level") else None
        except ValueError:
            latitude = None
            longitude = None
            map_zoom_level = None
        geocoding[region_code] = {
            "region_code": region_code,
            "display_name": (row.get("display_name") or "").strip() or None,
            "iso_alpha2": (row.get("iso_alpha2") or "").strip() or None,
            "latitude": latitude,
            "longitude": longitude,
            "map_zoom_level": map_zoom_level,
            "source_url": (row.get("source_url") or "").strip() or None,
            "notes": (row.get("notes") or "").strip() or None,
        }
    return geocoding


def _sorted_counter_rows(counter: Counter[str], *, key_name: str) -> list[dict]:
    return [
        {key_name: key, "count": count}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _sorted_amount_rows(amounts: dict[tuple[str, str], dict[str, int | float]]) -> list[dict]:
    rows = []
    for (group_key, currency), values in sorted(amounts.items(), key=lambda item: (item[0][0], item[0][1])):
        rows.append(
            {
                "group_key": group_key,
                "currency": currency,
                "tranche_count": int(values["tranche_count"]),
                "total_issue_amount": values["total_issue_amount"],
            }
        )
    rows.sort(key=lambda row: (-row["total_issue_amount"], row["group_key"], row["currency"]))
    return rows


def _capital_summary(material: list[dict]) -> dict:
    by_peril: dict[tuple[str, str], dict[str, int | float]] = defaultdict(lambda: {"tranche_count": 0, "total_issue_amount": 0})
    by_sponsor: dict[tuple[str, str], dict[str, int | float]] = defaultdict(
        lambda: {"tranche_count": 0, "total_issue_amount": 0}
    )
    by_listed_year: dict[tuple[str, str], dict[str, int | float]] = defaultdict(
        lambda: {"tranche_count": 0, "total_issue_amount": 0}
    )
    known_amount_rows = 0
    missing_amount_rows = 0
    non_usd_rows = 0

    for row in material:
        amount = _parse_issue_amount(row.get("issue_amount"))
        if amount is None:
            missing_amount_rows += 1
            continue
        known_amount_rows += 1
        currency = str(row.get("currency") or "unknown")
        if currency != "USD":
            non_usd_rows += 1
        perils = row.get("peril_codes") or ["unknown"]
        for peril in perils:
            bucket = by_peril[(str(peril), currency)]
            bucket["tranche_count"] += 1
            bucket["total_issue_amount"] += amount
        sponsor = _canonical_sponsor(row) or "unknown"
        bucket = by_sponsor[(sponsor, currency)]
        bucket["tranche_count"] += 1
        bucket["total_issue_amount"] += amount
        year_bucket = by_listed_year[(_year_group(row.get("listed_date")), currency)]
        year_bucket["tranche_count"] += 1
        year_bucket["total_issue_amount"] += amount

    return {
        "known_amount_rows": known_amount_rows,
        "missing_amount_rows": missing_amount_rows,
        "non_usd_rows": non_usd_rows,
        "by_peril": _sorted_amount_rows(by_peril),
        "by_sponsor": _sorted_amount_rows(by_sponsor),
        "by_listed_year": _sorted_amount_rows(by_listed_year),
    }


def _trigger_summary(material: list[dict]) -> dict:
    trigger_counter: Counter[str] = Counter()
    known_trigger_rows = 0
    for row in material:
        trigger_type = (row.get("trigger_type") or "").strip()
        if not trigger_type:
            continue
        known_trigger_rows += 1
        trigger_counter[trigger_type] += 1
    return {
        "known_trigger_rows": known_trigger_rows,
        "missing_trigger_rows": max(0, len(material) - known_trigger_rows),
        "by_trigger_type": _sorted_counter_rows(trigger_counter, key_name="trigger_type"),
    }


def _missing_issue_amount_rows(material: list[dict], limit: int = 10) -> list[dict]:
    rows = [row for row in material if _parse_issue_amount(row.get("issue_amount")) is None]
    rows.sort(
        key=lambda row: (
            0 if row.get("status") == "outstanding" else 1,
            0 if _canonical_sponsor(row) else 1,
            -((_to_date(row.get("listed_date")) or date.min).toordinal()),
            row.get("tranche_name") or "",
        )
    )
    return [
        {
            "tranche_name": row.get("tranche_name"),
            "sponsor_name": _canonical_sponsor(row),
            "listed_date": row.get("listed_date"),
            "maturity_date": row.get("maturity_date"),
            "currency": row.get("currency"),
            "source_url": row.get("source_url"),
        }
        for row in rows[:limit]
    ]


def _missing_sponsor_rows(material: list[dict], limit: int = 10) -> list[dict]:
    rows = [row for row in material if not _canonical_sponsor(row)]
    rows.sort(
        key=lambda row: (
            0 if row.get("status") == "outstanding" else 1,
            -((_to_date(row.get("listed_date")) or date.min).toordinal()),
            row.get("tranche_name") or "",
        )
    )
    return [
        {
            "tranche_name": row.get("tranche_name"),
            "issuer_name": row.get("issuer_name"),
            "listed_date": row.get("listed_date"),
            "maturity_date": row.get("maturity_date"),
            "source_url": row.get("source_url"),
        }
        for row in rows[:limit]
    ]


def _missing_sponsor_families(material: list[dict], limit: int = 10) -> list[dict]:
    family_counter: Counter[str] = Counter()
    for row in material:
        if _canonical_sponsor(row):
            continue
        family_counter[_family_name(row)] += 1
    return [
        {"family_name": family_name, "missing_sponsor_rows": count}
        for family_name, count in family_counter.most_common(limit)
    ]


def _gap_spotlight(material: list[dict]) -> dict:
    return {
        "top_missing_issue_amount": _missing_issue_amount_rows(material),
        "top_missing_sponsor": _missing_sponsor_rows(material),
        "top_missing_sponsor_families": _missing_sponsor_families(material),
    }


def _top_sponsors_by_capital(material: list[dict], limit: int = 10) -> list[dict]:
    rows = _capital_summary(material).get("by_sponsor") or []
    return [
        {
            "sponsor_name": row.get("group_key"),
            "currency": row.get("currency"),
            "tranche_count": row.get("tranche_count"),
            "total_issue_amount": row.get("total_issue_amount"),
        }
        for row in rows[:limit]
    ]


def _top_regions_by_capital(region_map: list[dict], limit: int = 10) -> list[dict]:
    rows: list[dict] = []
    for region in region_map:
        for capital_row in region.get("capital_by_currency") or []:
            rows.append(
                {
                    "region_code": region.get("region_code"),
                    "display_name": region.get("display_name"),
                    "currency": capital_row.get("currency"),
                    "tranche_count": region.get("tranche_count"),
                    "total_issue_amount": capital_row.get("total_issue_amount"),
                }
            )
    rows.sort(key=lambda row: (-float(row.get("total_issue_amount") or 0.0), row.get("display_name") or "", row.get("currency") or ""))
    return rows[:limit]


def _top_perils_by_capital(material: list[dict], limit: int = 10) -> list[dict]:
    rows = _capital_summary(material).get("by_peril") or []
    return [
        {
            "peril_code": row.get("group_key"),
            "currency": row.get("currency"),
            "tranche_count": row.get("tranche_count"),
            "total_issue_amount": row.get("total_issue_amount"),
        }
        for row in rows[:limit]
    ]


def _market_timeline(material: list[dict]) -> list[dict]:
    rows = _capital_summary(material).get("by_listed_year") or []

    def sort_key(row: dict) -> tuple[int, int | str]:
        year = str(row.get("group_key") or "unknown")
        if year.isdigit():
            return (0, int(year))
        return (1, year)

    return [
        {
            "listed_year": row.get("group_key"),
            "currency": row.get("currency"),
            "tranche_count": row.get("tranche_count"),
            "total_issue_amount": row.get("total_issue_amount"),
        }
        for row in sorted(rows, key=sort_key)
    ]


def _maturity_runway(material: list[dict], *, as_of: date, windows: tuple[int, ...] = (12, 24, 36)) -> list[dict]:
    runway: list[dict] = []
    for months in windows:
        horizon = as_of + timedelta(days=30 * months)
        buckets: dict[str, dict[str, int | float]] = defaultdict(lambda: {"tranche_count": 0, "total_issue_amount": 0})
        for row in material:
            if row.get("status") != "outstanding":
                continue
            maturity_date = _to_date(row.get("maturity_date"))
            if not maturity_date or not (as_of <= maturity_date <= horizon):
                continue
            currency = str(row.get("currency") or "unknown")
            bucket = buckets[currency]
            bucket["tranche_count"] += 1
            amount = _parse_issue_amount(row.get("issue_amount"))
            if amount is not None:
                bucket["total_issue_amount"] += amount
        for currency, values in sorted(buckets.items(), key=lambda item: (-float(item[1]["total_issue_amount"]), item[0])):
            runway.append(
                {
                    "window_months": months,
                    "currency": currency,
                    "tranche_count": int(values["tranche_count"]),
                    "total_issue_amount": values["total_issue_amount"],
                }
            )
    return runway


def _upcoming_maturities_by_region(
    material: list[dict],
    geocoding: dict[str, dict],
    *,
    as_of: date,
    months: int = 24,
    limit: int = 10,
) -> list[dict]:
    horizon = as_of + timedelta(days=30 * months)
    rows: list[dict] = []
    buckets: dict[tuple[str, str], dict[str, int | float]] = defaultdict(
        lambda: {"tranche_count": 0, "total_issue_amount": 0}
    )
    for row in material:
        if row.get("status") != "outstanding":
            continue
        maturity_date = _to_date(row.get("maturity_date"))
        if not maturity_date or not (as_of <= maturity_date <= horizon):
            continue
        amount = _parse_issue_amount(row.get("issue_amount"))
        for region_code in row.get("region_codes") or []:
            currency = str(row.get("currency") or "unknown")
            bucket = buckets[(region_code, currency)]
            bucket["tranche_count"] += 1
            if amount is not None:
                bucket["total_issue_amount"] += amount
    for (region_code, currency), values in buckets.items():
        rows.append(
            {
                "window_months": months,
                "region_code": region_code,
                "display_name": _display_region_name(region_code, geocoding),
                "currency": currency,
                "tranche_count": int(values["tranche_count"]),
                "total_issue_amount": values["total_issue_amount"],
            }
        )
    rows.sort(
        key=lambda row: (
            -float(row.get("total_issue_amount") or 0.0),
            -(int(row.get("tranche_count") or 0)),
            row.get("display_name") or "",
            row.get("currency") or "",
        )
    )
    return rows[:limit]


def _capital_concentration(material: list[dict], region_map: list[dict]) -> list[dict]:
    sponsor_rows = _capital_summary(material).get("by_sponsor") or []
    region_rows = _top_regions_by_capital(region_map, limit=500)
    sponsor_totals: dict[str, list[float]] = defaultdict(list)
    region_totals: dict[str, list[float]] = defaultdict(list)
    total_by_currency: Counter[str] = Counter()
    for row in sponsor_rows:
        currency = str(row.get("currency") or "unknown")
        total = float(row.get("total_issue_amount") or 0.0)
        sponsor_totals[currency].append(total)
        total_by_currency[currency] += total
    for row in region_rows:
        currency = str(row.get("currency") or "unknown")
        total = float(row.get("total_issue_amount") or 0.0)
        region_totals[currency].append(total)
    concentration: list[dict] = []
    for currency, total in sorted(total_by_currency.items()):
        if total <= 0:
            continue
        top_5_sponsor = sum(sorted(sponsor_totals[currency], reverse=True)[:5])
        top_3_region = sum(sorted(region_totals[currency], reverse=True)[:3])
        sponsor_share_pct = min(round(top_5_sponsor / total * 100.0, 2), 100.0)
        # Region tags can overlap on a single tranche, so clamp the narrative share.
        region_share_pct = min(round(top_3_region / total * 100.0, 2), 100.0)
        concentration.append(
            {
                "currency": currency,
                "total_known_issue_amount": int(total) if float(total).is_integer() else round(float(total), 2),
                "top_5_sponsor_share_pct": sponsor_share_pct,
                "top_3_region_share_pct": region_share_pct,
            }
        )
    concentration.sort(key=lambda row: (-row["total_known_issue_amount"], row["currency"]))
    return concentration


def _watchlist_pressure(diagnostics: dict, *, public_count: int, candidate_count: int) -> dict:
    total = public_count + candidate_count
    return {
        "public_match_count": public_count,
        "candidate_match_count": candidate_count,
        "candidate_ratio_pct": round(candidate_count / total * 100.0, 2) if total else 0.0,
        "top_promotion_hints": (diagnostics.get("promotion_hint_counts") or [])[:5],
        "top_candidate_blockers_by_family": (diagnostics.get("top_candidate_blockers_by_family") or [])[:5],
    }


def _coverage_scorecard(material: list[dict]) -> dict:
    total_material = len(material)
    region_required_rows = [row for row in material if _requires_region_evidence(row)]
    sponsor_present_rows = [row for row in material if _canonical_sponsor(row)]
    region_present_rows = [row for row in region_required_rows if row.get("region_codes")]
    amount_present = sum(1 for row in material if _parse_issue_amount(row.get("issue_amount")) is not None)
    trigger_present = sum(1 for row in material if row.get("trigger_type"))
    return {
        "material_tranche_count": total_material,
        "identified_sponsors": len({_canonical_sponsor(row) for row in material if _canonical_sponsor(row)}),
        "sponsor_coverage_pct": round((len(sponsor_present_rows) / total_material * 100.0), 2) if total_material else 0.0,
        "region_coverage_pct": round((len(region_present_rows) / len(region_required_rows) * 100.0), 2)
        if region_required_rows
        else 100.0,
        "amount_coverage_pct": round((amount_present / total_material * 100.0), 2) if total_material else 0.0,
        "trigger_coverage_pct": round((trigger_present / total_material * 100.0), 2) if total_material else 0.0,
        "missing_issue_amount_rows": total_material - amount_present,
        "missing_trigger_rows": total_material - trigger_present,
    }


def _unresolved_families(material: list[dict], diagnostics: dict, limit: int = 8) -> list[dict]:
    missing_sponsor_counts = {
        row["family_name"]: int(row["missing_sponsor_rows"]) for row in _missing_sponsor_families(material, limit=100)
    }
    blocker_rows = diagnostics.get("top_candidate_blockers_by_family") or []
    candidate_counts = {row.get("family_name"): int(row.get("count") or 0) for row in blocker_rows}
    blocker_lookup = {row.get("family_name"): row.get("blocker_counts") or [] for row in blocker_rows}
    family_names = {
        family_name
        for family_name in set(missing_sponsor_counts) | set(candidate_counts)
        if family_name
    }
    rows: list[dict] = []
    for family_name in family_names:
        rows.append(
            {
                "family_name": family_name,
                "missing_sponsor_rows": missing_sponsor_counts.get(family_name, 0),
                "candidate_rows": candidate_counts.get(family_name, 0),
                "top_blockers": blocker_lookup.get(family_name, [])[:3],
            }
        )
    rows.sort(
        key=lambda row: (
            -(int(row.get("missing_sponsor_rows") or 0) + int(row.get("candidate_rows") or 0)),
            -int(row.get("candidate_rows") or 0),
            row.get("family_name") or "",
        )
    )
    return rows[:limit]


def _candidate_blockers_summary(diagnostics: dict) -> dict:
    return {
        "top_candidate_reasons": (diagnostics.get("candidate_reason_counts") or [])[:5],
        "top_promotion_hints": (diagnostics.get("promotion_hint_counts") or [])[:5],
        "top_candidate_families": (diagnostics.get("top_candidate_families") or [])[:5],
    }


def _story_blocks(
    material: list[dict],
    region_map: list[dict],
    geocoding: dict[str, dict],
    diagnostics: dict,
    *,
    as_of: date,
    public_count: int,
    candidate_count: int,
) -> dict:
    return {
        "top_sponsors_by_capital": _top_sponsors_by_capital(material),
        "top_regions_by_capital": _top_regions_by_capital(region_map),
        "top_perils_by_capital": _top_perils_by_capital(material),
        "market_timeline": _market_timeline(material),
        "maturity_runway": _maturity_runway(material, as_of=as_of),
        "upcoming_maturities_by_region": _upcoming_maturities_by_region(material, geocoding, as_of=as_of),
        "capital_concentration": _capital_concentration(material, region_map),
        "coverage_scorecard": _coverage_scorecard(material),
        "unresolved_families": _unresolved_families(material, diagnostics),
        "candidate_blockers_summary": _candidate_blockers_summary(diagnostics),
        "watchlist_pressure": _watchlist_pressure(
            diagnostics,
            public_count=public_count,
            candidate_count=candidate_count,
        ),
    }


def _region_summaries(material: list[dict], geocoding: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    region_rows: dict[str, dict] = {}
    for row in material:
        amount = _parse_issue_amount(row.get("issue_amount"))
        status = row.get("status")
        for region_code in row.get("region_codes") or []:
            bucket = region_rows.setdefault(
                region_code,
                {
                    "tranche_count": 0,
                    "outstanding_tranche_count": 0,
                    "known_amount_rows": 0,
                    "currency_counter": Counter(),
                    "capital_by_currency": Counter(),
                    "peril_counter": Counter(),
                },
            )
            bucket["tranche_count"] += 1
            if status == "outstanding":
                bucket["outstanding_tranche_count"] += 1
            if amount is not None:
                bucket["known_amount_rows"] += 1
                bucket["currency_counter"][str(row.get("currency") or "unknown")] += 1
                bucket["capital_by_currency"][str(row.get("currency") or "unknown")] += amount
            for peril in row.get("peril_codes") or []:
                bucket["peril_counter"][str(peril)] += 1

    region_detail: list[dict] = []
    region_map: list[dict] = []
    for region_code, bucket in sorted(region_rows.items()):
        display_name = _display_region_name(region_code, geocoding)
        top_perils = [
            {"peril_code": peril_code, "count": count}
            for peril_code, count in bucket["peril_counter"].most_common(5)
        ]
        region_detail.append(
            {
                "region_code": region_code,
                "display_name": display_name,
                "tranche_count": bucket["tranche_count"],
                "outstanding_tranche_count": bucket["outstanding_tranche_count"],
                "known_amount_rows": bucket["known_amount_rows"],
                "currency_breakdown": _sorted_counter_rows(bucket["currency_counter"], key_name="currency"),
                "top_perils": top_perils,
            }
        )

        geo = geocoding.get(region_code) or {}
        if geo.get("latitude") is None or geo.get("longitude") is None:
            continue
        capital_by_currency = [
            {"currency": currency, "total_issue_amount": total}
            for currency, total in sorted(
                bucket["capital_by_currency"].items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        region_map.append(
            {
                "region_code": region_code,
                "display_name": display_name,
                "iso_alpha2": geo.get("iso_alpha2"),
                "latitude": geo.get("latitude"),
                "longitude": geo.get("longitude"),
                "map_zoom_level": geo.get("map_zoom_level"),
                "tranche_count": bucket["tranche_count"],
                "known_amount_rows": bucket["known_amount_rows"],
                "capital_by_currency": capital_by_currency,
                "dominant_perils": top_perils[:3],
            }
        )

    return region_detail, region_map


def _coverage_gaps(material: list[dict], geocoding: dict[str, dict]) -> dict:
    missing_issue_amount = 0
    missing_region = 0
    missing_maturity = 0
    missing_trigger_type = 0
    missing_sponsor = 0
    missing_region_geocoding = 0
    for row in material:
        if _parse_issue_amount(row.get("issue_amount")) is None:
            missing_issue_amount += 1
        if _requires_region_evidence(row) and not (row.get("region_codes") or []):
            missing_region += 1
        if not row.get("maturity_date"):
            missing_maturity += 1
        if not row.get("trigger_type"):
            missing_trigger_type += 1
        if not _canonical_sponsor(row):
            missing_sponsor += 1
        if any(region_code not in geocoding for region_code in (row.get("region_codes") or [])):
            missing_region_geocoding += 1
    return {
        "missing_issue_amount": missing_issue_amount,
        "missing_region": missing_region,
        "missing_maturity": missing_maturity,
        "missing_trigger_type": missing_trigger_type,
        "missing_sponsor": missing_sponsor,
        "missing_region_geocoding": missing_region_geocoding,
    }


def _registry_stats(tranches: list[dict], material: list[dict]) -> dict:
    currencies = Counter(str(row.get("currency") or "unknown") for row in material if row.get("currency"))
    statuses = Counter(str(row.get("status") or "unknown") for row in material)
    listing_statuses = Counter(str(row.get("listing_status") or "unknown") for row in material)
    return {
        "total_rows": len(tranches),
        "material_tranches": len(material),
        "programme_shells": sum(1 for row in tranches if row.get("is_programme_shell")),
        "identified_sponsors": len({_canonical_sponsor(row) for row in material if _canonical_sponsor(row)}),
        "amount_present_rows": sum(1 for row in material if _parse_issue_amount(row.get("issue_amount")) is not None),
        "amount_missing_rows": sum(1 for row in material if _parse_issue_amount(row.get("issue_amount")) is None),
        "currency_breakdown": _sorted_counter_rows(currencies, key_name="currency"),
        "status_breakdown": _sorted_counter_rows(statuses, key_name="status"),
        "listing_status_breakdown": _sorted_counter_rows(listing_statuses, key_name="listing_status"),
    }


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
    promotion_hint_counts: Counter[str] = Counter()
    top_candidate_families: Counter[str] = Counter()
    candidate_family_blockers: dict[str, Counter[str]] = {}
    public_rows_with_blockers = 0
    for match in normalized_matches:
        blockers = list(match.get("public_blockers") or [])
        if _is_public_match(match) and blockers:
            public_rows_with_blockers += 1
        for blocker in blockers:
            public_blocker_counts[blocker] += 1
        for reason in match.get("candidate_reason_codes") or []:
            candidate_reason_counts[reason] += 1
        for hint_code in match.get("promotion_hint_codes") or []:
            promotion_hint_counts[hint_code] += 1
        confidence_band_counts[str(match.get("confidence_band") or "unknown")] += 1
        if not _is_public_match(match):
            tranche = by_tranche.get(str(match.get("tranche_id") or ""))
            family_name = _family_name(tranche or {"tranche_name": match.get("tranche_name")})
            top_candidate_families[family_name] += 1
            family_blockers = candidate_family_blockers.setdefault(family_name, Counter())
            for blocker in blockers:
                family_blockers[blocker] += 1
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
        "promotion_hint_counts": [
            {"hint_code": hint_code, "count": count}
            for hint_code, count in sorted(promotion_hint_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "top_candidate_families": [
            {"family_name": family_name, "count": count}
            for family_name, count in top_candidate_families.most_common(8)
        ],
        "top_candidate_blockers_by_family": [
            {
                "family_name": family_name,
                "count": top_candidate_families[family_name],
                "blocker_counts": [
                    {"blocker_code": blocker_code, "count": count}
                    for blocker_code, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
                ],
            }
            for family_name, counter in sorted(
                candidate_family_blockers.items(),
                key=lambda item: (-top_candidate_families[item[0]], item[0]),
            )[:8]
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
        "promotion_hint_codes": _promotion_hint_codes(public_blockers, candidate_reason_codes),
        "confidence_band": confidence_band,
        "tranche_issue_flags": tranche_issue_flags,
    }


def _match_contract(match: dict, tranche: dict | None) -> dict:
    if {
        "match_scope",
        "public_blockers",
        "candidate_reason_codes",
        "promotion_hint_codes",
        "confidence_band",
        "tranche_issue_flags",
    } <= set(match):
        return {
            "match_scope": match.get("match_scope"),
            "public_blockers": match.get("public_blockers") or [],
            "candidate_reason_codes": match.get("candidate_reason_codes") or [],
            "promotion_hint_codes": match.get("promotion_hint_codes") or [],
            "confidence_band": match.get("confidence_band"),
            "tranche_issue_flags": match.get("tranche_issue_flags") or [],
        }
    return _fallback_match_contract(match, tranche)


def _promotion_hint_texts(hint_codes: list[str]) -> list[str]:
    mapping = {
        "add_sponsor_evidence": "Add exact sponsor evidence for the tranche or family.",
        "strengthen_region_evidence": "Strengthen region evidence with explicit covered geography.",
        "replace_broad_peril_classification": "Replace broad property-cat labeling with an explicit peril.",
        "confirm_maturity_date": "Confirm the tranche maturity or risk end date.",
    }
    return [mapping[code] for code in hint_codes if code in mapping]


def _promotion_hint_codes(public_blockers: list[str], candidate_reason_codes: list[str]) -> list[str]:
    evidence_codes = set(public_blockers) | set(candidate_reason_codes)
    hints: list[str] = []
    if "missing_sponsor" in evidence_codes:
        hints.append("add_sponsor_evidence")
    if {"weak_region_evidence", "region_unknown"} & evidence_codes:
        hints.append("strengthen_region_evidence")
    if {"broad_peril", "broad_peril_match"} & evidence_codes:
        hints.append("replace_broad_peril_classification")
    if "missing_maturity" in evidence_codes:
        hints.append("confirm_maturity_date")
    return hints


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
            "promotion_hint_codes": contract["promotion_hint_codes"],
            "promotion_hints": _promotion_hint_texts(contract["promotion_hint_codes"]),
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
    promotion_hint_codes = sorted({reason for contract in contracts for reason in contract["promotion_hint_codes"]})
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
        "promotion_hint_codes": promotion_hint_codes,
        "promotion_hints": _promotion_hint_texts(promotion_hint_codes),
        "confidence_band": confidence_bands.most_common(1)[0][0] if confidence_bands else "unknown",
        "reason_text": reason_text,
        "event_geo": {
            "latitude": event.get("event_latitude"),
            "longitude": event.get("event_longitude"),
            "bbox": event.get("event_bbox"),
        },
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
    region_geocoding = _load_region_geocoding(settings)
    by_tranche = {row["tranche_id"]: row for row in material if row.get("tranche_id")}
    by_event = {row["event_id"]: row for row in events if row.get("event_id")}
    diagnostics = _watchlist_diagnostics(matches, by_tranche)
    limitations = _collect_limitations(material)
    capital_summary = _capital_summary(material)
    trigger_summary = _trigger_summary(material)
    gap_spotlight = _gap_spotlight(material)
    region_detail, region_map = _region_summaries(material, region_geocoding)
    coverage_gaps = _coverage_gaps(material, region_geocoding)
    registry_stats = _registry_stats(tranches, material)
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
    story_blocks = _story_blocks(
        material,
        region_map,
        region_geocoding,
        diagnostics,
        as_of=as_of,
        public_count=len(watchlist_cards),
        candidate_count=len(candidate_watchlist_cards),
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
                "issue_amount": _parse_issue_amount(row.get("issue_amount")),
                "issue_amount_source_type": row.get("issue_amount_source_type") or "missing",
                "issue_amount_source_url": row.get("issue_amount_source_url"),
                "issue_amount_source_note": row.get("issue_amount_source_note"),
                "currency": row.get("currency"),
                "peril_codes": row.get("peril_codes", []),
                "region_codes": row.get("region_codes", []),
                "listing_status": row.get("listing_status"),
                "status": row.get("status"),
                "bma_regulator_class": row.get("bma_regulator_class"),
                "attribution_status": row.get("attribution_status") or {},
                "sponsor_attribution_state": row.get("sponsor_attribution_state"),
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
        "capital_summary": capital_summary,
        "region_detail": region_detail,
        "coverage_gaps": coverage_gaps,
        "trigger_summary": trigger_summary,
        "registry_stats": registry_stats,
        "region_map": region_map,
        "gap_spotlight": gap_spotlight,
        "story_blocks": story_blocks,
        "notes": [
            "This is an initial public release and remains a work in progress.",
            "Public watchlist rows require exact peril/date/geography overlap plus tranche evidence strong enough for public display; lower-confidence candidates are separated.",
            "Programme shells without a maturity date are excluded from watchlist matching and maturity KPIs.",
            "The sponsor-peril matrix only counts identified sponsors; rows without sponsor attribution are omitted.",
        ],
    }
    path = write_json(settings.dashboard_path, payload)
    return str(path)
