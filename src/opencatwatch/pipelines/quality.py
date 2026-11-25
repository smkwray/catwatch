from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import Settings
from ..hygiene import validate_public_docs
from ..utils import normalize_name, read_json, read_jsonl, write_json

RELEASE_THRESHOLDS = {
    "sponsor_coverage_pct": 70.0,
    "region_coverage_pct": 95.0,
    "outstanding_missing_maturity": 40,
    "broad_peril_rows": 25,
    "dashboard_max_age_days": 14,
    "public_watchlist_rows_with_blockers": 0,
}

_NON_GEOGRAPHIC_PERILS = {"cyber", "mortality"}

_PLACEHOLDER_USER_AGENT_MARKERS = {
    "you@example.com",
    "research project",
    "set opencatwatch_user_agent",
}

_MANUAL_TABLE_SPECS = {
    "sponsor_aliases": {
        "path": "sponsor_aliases.csv",
        "required_columns": ["alias", "sponsor_name", "source_url", "notes"],
        "row_label_field": "alias",
        "duplicate_key_fields": ["alias"],
    },
    "tranche_overrides": {
        "path": "tranche_overrides.csv",
        "required_columns": ["tranche_name", "field_name", "override_value", "source_url", "notes"],
        "row_label_field": "tranche_name",
        "duplicate_key_fields": ["tranche_name", "field_name"],
    },
    "region_geocoding": {
        "path": "region_geocoding.csv",
        "required_columns": [
            "region_code",
            "display_name",
            "iso_alpha2",
            "latitude",
            "longitude",
            "map_zoom_level",
            "source_url",
            "notes",
        ],
        "row_label_field": "region_code",
        "duplicate_key_fields": ["region_code"],
    },
    "trigger_overrides": {
        "path": "trigger_overrides.csv",
        "required_columns": ["tranche_name", "trigger_type", "source_url", "notes"],
        "row_label_field": "tranche_name",
        "duplicate_key_fields": ["tranche_name"],
    },
}


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


def _load_dashboard(settings: Settings) -> dict:
    dashboard_path = settings.dashboard_path
    if not dashboard_path.exists():
        return {}
    payload = read_json(dashboard_path)
    return payload if isinstance(payload, dict) else {}


def _dashboard_age_days(dashboard: dict, *, reference_date: date) -> int | None:
    as_of = _to_date(dashboard.get("as_of"))
    if not as_of:
        return None
    return max(0, (reference_date - as_of).days)


def _has_real_user_agent(user_agent: str) -> bool:
    normalized = (user_agent or "").strip().lower()
    if not normalized:
        return False
    return all(marker not in normalized for marker in _PLACEHOLDER_USER_AGENT_MARKERS)


def _family_name(row: dict) -> str:
    issuer_name = (row.get("issuer_name") or "").strip()
    if issuer_name:
        return issuer_name
    tranche_name = (row.get("tranche_name") or "").strip()
    for separator in (" Series ", " series ", " due ", " Due ", " Class ", " class "):
        if separator in tranche_name:
            return tranche_name.split(separator, 1)[0].strip()
    return tranche_name or "unknown"


def _load_manual_table_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _load_region_geocoding_codes(settings: Settings) -> set[str]:
    _, rows = _load_manual_table_rows(settings.manual_dir / "region_geocoding.csv")
    return {(row.get("region_code") or "").strip() for row in rows if (row.get("region_code") or "").strip()}


def _validate_json_list_field(value: str | None) -> bool:
    if not value:
        return True
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, list)


def _validate_manual_tables(settings: Settings) -> dict:
    issues: list[dict[str, object]] = []
    summary: dict[str, dict[str, int]] = {}

    for table_name, spec in _MANUAL_TABLE_SPECS.items():
        path = settings.manual_dir / spec["path"]
        fieldnames, rows = _load_manual_table_rows(path)
        missing_columns = [column for column in spec["required_columns"] if column not in fieldnames]
        summary[table_name] = {"rows": len(rows), "issues": 0}
        if missing_columns:
            issues.append(
                {
                    "table": table_name,
                    "path": str(path),
                    "row_number": 1,
                    "label": table_name,
                    "issue": f"missing_required_columns:{','.join(missing_columns)}",
                }
            )
            summary[table_name]["issues"] += 1
            continue

        seen_keys: dict[tuple[str, ...], tuple[int, str]] = {}
        for index, row in enumerate(rows, start=2):
            label = (row.get(spec["row_label_field"]) or "").strip() or table_name
            duplicate_key_fields = spec.get("duplicate_key_fields") or []
            if duplicate_key_fields:
                key_parts: list[str] = []
                for field_name in duplicate_key_fields:
                    value = (row.get(field_name) or "").strip()
                    if field_name in {"alias", "tranche_name"}:
                        value = normalize_name(value)
                    else:
                        value = value.lower()
                    key_parts.append(value)
                if all(key_parts):
                    key = tuple(key_parts)
                    previous = seen_keys.get(key)
                    if previous is not None:
                        issues.append(
                            {
                                "table": table_name,
                                "path": str(path),
                                "row_number": index,
                                "label": label,
                                "issue": f"duplicate_row_key:first_seen_row_{previous[0]}:{previous[1]}",
                            }
                        )
                        summary[table_name]["issues"] += 1
                    else:
                        seen_keys[key] = (index, label)
            if not (row.get("source_url") or "").strip():
                issues.append(
                    {
                        "table": table_name,
                        "path": str(path),
                        "row_number": index,
                        "label": label,
                        "issue": "missing_source_url",
                    }
                )
                summary[table_name]["issues"] += 1
            if not (row.get("notes") or "").strip():
                issues.append(
                    {
                        "table": table_name,
                        "path": str(path),
                        "row_number": index,
                        "label": label,
                        "issue": "missing_notes",
                    }
                )
                summary[table_name]["issues"] += 1
            for json_field in ("region_codes", "peril_codes"):
                if json_field in row and not _validate_json_list_field(row.get(json_field)):
                    issues.append(
                        {
                            "table": table_name,
                            "path": str(path),
                            "row_number": index,
                            "label": label,
                            "issue": f"invalid_json_list:{json_field}",
                        }
                    )
                    summary[table_name]["issues"] += 1

    return {"summary": summary, "issues": issues}


def _watchlist_rows_have_fields(rows: list[dict]) -> bool:
    return all(
        isinstance(row, dict)
        and {
            "source_url",
            "reason_text",
            "matched_tranche_rows",
            "match_scope",
            "public_blockers",
            "candidate_reason_codes",
            "confidence_band",
        }
        <= set(row)
        for row in rows[:5]
    )


def _dashboard_has_evidence_fields(dashboard: dict) -> bool:
    maturity_rows = dashboard.get("maturity_wall") or []
    watchlist_rows = dashboard.get("watchlist") or []
    candidate_rows = dashboard.get("watchlist_review_candidates") or []

    maturity_ok = all(
        isinstance(row, dict)
        and {
            "source_url",
            "sponsor_source_url",
            "sponsor_source_type",
            "review_status",
            "issue_amount",
            "issue_amount_source_type",
            "issue_amount_source_url",
            "currency",
            "region_codes",
            "listing_status",
            "status",
            "bma_regulator_class",
            "attribution_status",
            "sponsor_attribution_state",
            "peril_source_type",
            "region_source_type",
            "maturity_source_type",
        }
        <= set(row)
        for row in maturity_rows[:5]
    )
    return maturity_ok and _watchlist_rows_have_fields(watchlist_rows) and _watchlist_rows_have_fields(candidate_rows)


def _dashboard_has_enrichment_fields(dashboard: dict) -> bool:
    capital_summary = dashboard.get("capital_summary") or {}
    coverage_gaps = dashboard.get("coverage_gaps") or {}
    trigger_summary = dashboard.get("trigger_summary") or {}
    registry_stats = dashboard.get("registry_stats") or {}
    story_blocks = dashboard.get("story_blocks") or {}
    region_detail = dashboard.get("region_detail")
    region_map = dashboard.get("region_map")

    top_level_ok = (
        isinstance(region_detail, list)
        and isinstance(region_map, list)
        and isinstance(capital_summary, dict)
        and isinstance(coverage_gaps, dict)
        and isinstance(trigger_summary, dict)
        and isinstance(registry_stats, dict)
        and isinstance(story_blocks, dict)
        and {
            "known_amount_rows",
            "missing_amount_rows",
            "non_usd_rows",
            "by_peril",
            "by_sponsor",
            "by_listed_year",
        }
        <= set(capital_summary)
        and {
            "missing_issue_amount",
            "missing_region",
            "missing_maturity",
            "missing_trigger_type",
            "missing_sponsor",
            "missing_region_geocoding",
        }
        <= set(coverage_gaps)
        and {"known_trigger_rows", "missing_trigger_rows", "by_trigger_type"} <= set(trigger_summary)
        and {
            "total_rows",
            "material_tranches",
            "programme_shells",
            "identified_sponsors",
            "amount_present_rows",
            "amount_missing_rows",
            "currency_breakdown",
            "status_breakdown",
            "listing_status_breakdown",
        }
        <= set(registry_stats)
        and {
            "top_sponsors_by_capital",
            "top_regions_by_capital",
            "top_perils_by_capital",
            "market_timeline",
            "maturity_runway",
            "upcoming_maturities_by_region",
            "capital_concentration",
            "coverage_scorecard",
            "unresolved_families",
            "candidate_blockers_summary",
            "watchlist_pressure",
        }
        <= set(story_blocks)
    )
    if not top_level_ok:
        return False

    watchlist_rows = dashboard.get("watchlist") or []
    candidate_rows = dashboard.get("watchlist_review_candidates") or []
    watchlist_ok = all("event_geo" in row for row in watchlist_rows[:5] if isinstance(row, dict))
    candidate_ok = all("event_geo" in row for row in candidate_rows[:5] if isinstance(row, dict))
    return watchlist_ok and candidate_ok


def _dashboard_watchlist_is_public_only(dashboard: dict) -> bool:
    watchlist_rows = dashboard.get("watchlist") or []
    candidate_rows = dashboard.get("watchlist_review_candidates") or []
    public_ok = all(row.get("match_scope") == "public" for row in watchlist_rows[:50])
    candidates_ok = all(row.get("match_scope") == "candidate" for row in candidate_rows[:25])
    blocker_ok = all(not (row.get("public_blockers") or []) for row in watchlist_rows[:50])
    return public_ok and candidates_ok and blocker_ok


def _dashboard_has_watchlist_diagnostics(dashboard: dict) -> bool:
    diagnostics = dashboard.get("watchlist_diagnostics") or {}
    limitations = dashboard.get("limitations")
    if not isinstance(limitations, list):
        return False
    required_keys = {
        "public_match_count",
        "candidate_match_count",
        "public_rows_with_blockers",
        "candidate_reason_counts",
        "public_blocker_counts",
        "confidence_band_counts",
        "top_candidate_families",
    }
    return isinstance(diagnostics, dict) and required_keys <= set(diagnostics)


def _dashboard_public_match_count(dashboard: dict) -> int:
    watchlist_rows = dashboard.get("watchlist") or []
    return sum(int(row.get("exact_match_count") or 0) for row in watchlist_rows if isinstance(row, dict))


def _dashboard_candidate_match_count(dashboard: dict) -> int:
    candidate_rows = dashboard.get("watchlist_review_candidates") or []
    return sum(int(row.get("matched_tranche_count") or 0) for row in candidate_rows if isinstance(row, dict))


def _dashboard_public_blocker_count(dashboard: dict) -> int:
    watchlist_rows = dashboard.get("watchlist") or []
    return sum(1 for row in watchlist_rows if isinstance(row, dict) and row.get("public_blockers"))


def _dashboard_next_12m_maturity_count(dashboard: dict) -> int | None:
    as_of = _to_date(dashboard.get("as_of"))
    if not as_of:
        return None
    horizon = as_of + timedelta(days=365)
    maturity_rows = dashboard.get("maturity_wall") or []
    return sum(
        1
        for row in maturity_rows
        if isinstance(row, dict)
        and (maturity_date := _to_date(row.get("maturity_date")))
        and as_of <= maturity_date <= horizon
    )


def _snapshot_kpi_mismatches(dashboard: dict) -> list[str]:
    kpis = dashboard.get("kpis") or {}
    diagnostics = dashboard.get("watchlist_diagnostics") or {}
    mismatches: list[str] = []
    watchlist_rows = dashboard.get("watchlist") or []
    candidate_rows = dashboard.get("watchlist_review_candidates") or []

    expected_next_12m = _dashboard_next_12m_maturity_count(dashboard)
    maturity_wall_rows = dashboard.get("maturity_wall") or []
    maturity_wall_truncated = len(maturity_wall_rows) >= 200
    if expected_next_12m is not None and (not maturity_wall_truncated) and kpis.get("next_12m_maturities") != expected_next_12m:
        mismatches.append("next_12m_maturities")

    public_match_count = diagnostics.get("public_match_count")
    if kpis.get("watchlist_matches") != public_match_count:
        mismatches.append("watchlist_matches")
    if len(watchlist_rows) < 50 and public_match_count != len(watchlist_rows):
        mismatches.append("watchlist_diagnostics.public_match_count")
    if public_match_count is not None and public_match_count < len(watchlist_rows):
        mismatches.append("watchlist_diagnostics.public_match_count")

    candidate_match_count = diagnostics.get("candidate_match_count")
    if kpis.get("watchlist_review_candidates") != candidate_match_count:
        mismatches.append("watchlist_review_candidates")
    if len(candidate_rows) < 25 and candidate_match_count != len(candidate_rows):
        mismatches.append("watchlist_diagnostics.candidate_match_count")
    if candidate_match_count is not None and candidate_match_count < len(candidate_rows):
        mismatches.append("watchlist_diagnostics.candidate_match_count")

    public_blocker_count = _dashboard_public_blocker_count(dashboard)
    if public_blocker_count and diagnostics.get("public_rows_with_blockers") != public_blocker_count:
        mismatches.append("watchlist_diagnostics.public_rows_with_blockers")

    return mismatches


def _snapshot_audit_divergences(dashboard: dict, audit_payload: dict) -> list[str]:
    kpis = dashboard.get("kpis") or {}
    diagnostics = dashboard.get("watchlist_diagnostics") or {}
    counts = audit_payload.get("counts") or {}
    consistency = audit_payload.get("dashboard_consistency") or {}
    divergences: list[str] = []

    if consistency.get("actual_next_12m_maturities") != kpis.get("next_12m_maturities"):
        divergences.append("next_12m_maturities")
    if counts.get("public_watchlist_matches") != kpis.get("watchlist_matches"):
        divergences.append("watchlist_matches")
    if counts.get("watchlist_review_candidates") != kpis.get("watchlist_review_candidates"):
        divergences.append("watchlist_review_candidates")
    if counts.get("public_watchlist_matches") != diagnostics.get("public_match_count"):
        divergences.append("watchlist_diagnostics.public_match_count")
    if counts.get("watchlist_review_candidates") != diagnostics.get("candidate_match_count"):
        divergences.append("watchlist_diagnostics.candidate_match_count")
    if consistency.get("actual_public_watchlist_blockers") != diagnostics.get("public_rows_with_blockers"):
        divergences.append("watchlist_diagnostics.public_rows_with_blockers")
    if consistency.get("dashboard_public_watchlist_matches") != kpis.get("watchlist_matches"):
        divergences.append("dashboard_public_watchlist_matches")
    if consistency.get("dashboard_review_candidates") != kpis.get("watchlist_review_candidates"):
        divergences.append("dashboard_review_candidates")
    if consistency.get("dashboard_public_watchlist_blockers") != diagnostics.get("public_rows_with_blockers"):
        divergences.append("dashboard_public_watchlist_blockers")

    return divergences


def _match_scope(match: dict) -> str:
    scope = match.get("match_scope")
    if scope in {"public", "candidate"}:
        return str(scope)
    reasons = set(match.get("reasons") or [])
    return "public" if {"peril_match", "active_date_overlap", "region_overlap"} <= reasons else "candidate"


def _public_limitations(material: list[dict]) -> list[str]:
    families: dict[str, Counter[str]] = defaultdict(Counter)
    for row in material:
        family = _family_name(row)
        if not _canonical_sponsor(row):
            families[family]["missing sponsor evidence"] += 1
        if _requires_region_evidence(row) and not row.get("region_codes"):
            families[family]["missing region evidence"] += 1
        if "other_property_cat" in (row.get("peril_codes") or []):
            families[family]["broad peril classification"] += 1
        if row.get("status") == "outstanding" and not row.get("maturity_date"):
            families[family]["missing maturity"] += 1

    ranked = sorted(
        (
            (family, counts, sum(counts.values()))
            for family, counts in families.items()
            if counts
        ),
        key=lambda item: (-item[2], item[0]),
    )

    limitations: list[str] = []
    for family, counts, _ in ranked[:8]:
        issue_text = ", ".join(f"{count} {issue}" for issue, count in counts.most_common(3))
        limitations.append(f"{family}: {issue_text}.")
    return limitations


def _build_release_checks(
    settings: Settings,
    coverage: dict,
    issues: dict,
    dashboard: dict,
    manual_tables: dict,
    public_limitations: list[str],
) -> list[dict]:
    dashboard_age_days = _dashboard_age_days(dashboard, reference_date=settings.as_of_date)
    manual_issue_count = len(manual_tables.get("issues", []))
    checks = [
        {
            "name": "explicit_as_of_date",
            "passed": settings.as_of_date_is_explicit,
            "actual": settings.as_of_date_is_explicit,
            "target": True,
            "detail": "Release builds must pin OPENCATWATCH_AS_OF_DATE for reproducible snapshots.",
        },
        {
            "name": "sponsor_coverage",
            "passed": float(coverage.get("sponsor_coverage_pct", 0.0)) >= RELEASE_THRESHOLDS["sponsor_coverage_pct"],
            "actual": coverage.get("sponsor_coverage_pct", 0.0),
            "target": f">={RELEASE_THRESHOLDS['sponsor_coverage_pct']}",
            "detail": "Sponsor coverage on material tranches.",
        },
        {
            "name": "region_coverage",
            "passed": float(coverage.get("region_coverage_pct", 0.0)) >= RELEASE_THRESHOLDS["region_coverage_pct"],
            "actual": coverage.get("region_coverage_pct", 0.0),
            "target": f">={RELEASE_THRESHOLDS['region_coverage_pct']}",
            "detail": "Region coverage on material tranches.",
        },
        {
            "name": "outstanding_missing_maturity",
            "passed": int(issues.get("outstanding_missing_maturity", 0))
            <= RELEASE_THRESHOLDS["outstanding_missing_maturity"],
            "actual": issues.get("outstanding_missing_maturity", 0),
            "target": f"<={RELEASE_THRESHOLDS['outstanding_missing_maturity']}",
            "detail": "Outstanding material rows without maturity.",
        },
        {
            "name": "broad_peril_rows",
            "passed": int(issues.get("broad_peril_rows", 0)) <= RELEASE_THRESHOLDS["broad_peril_rows"],
            "actual": issues.get("broad_peril_rows", 0),
            "target": f"<={RELEASE_THRESHOLDS['broad_peril_rows']}",
            "detail": "Registry rows still using other_property_cat.",
        },
        {
            "name": "public_watchlist_rows_with_blockers",
            "passed": int(issues.get("public_watchlist_rows_with_blockers", 0))
            <= RELEASE_THRESHOLDS["public_watchlist_rows_with_blockers"],
            "actual": issues.get("public_watchlist_rows_with_blockers", 0),
            "target": f"<={RELEASE_THRESHOLDS['public_watchlist_rows_with_blockers']}",
            "detail": "Public watchlist rows should not carry tranche-side evidence blockers.",
        },
        {
            "name": "dashboard_not_demo",
            "passed": bool(dashboard) and not bool(dashboard.get("demo_mode")),
            "actual": bool(dashboard) and not bool(dashboard.get("demo_mode")),
            "target": True,
            "detail": "Committed dashboard snapshot is present and non-demo.",
        },
        {
            "name": "dashboard_current",
            "passed": dashboard_age_days is not None and dashboard_age_days <= RELEASE_THRESHOLDS["dashboard_max_age_days"],
            "actual": dashboard_age_days,
            "target": f"<={RELEASE_THRESHOLDS['dashboard_max_age_days']} days",
            "detail": "Dashboard as_of date is recent enough for public release.",
        },
        {
            "name": "dashboard_evidence_fields",
            "passed": _dashboard_has_evidence_fields(dashboard),
            "actual": _dashboard_has_evidence_fields(dashboard),
            "target": True,
            "detail": "Dashboard payload exposes evidence-facing fields for site rendering.",
        },
        {
            "name": "dashboard_public_watchlist_only",
            "passed": _dashboard_watchlist_is_public_only(dashboard),
            "actual": _dashboard_watchlist_is_public_only(dashboard),
            "target": True,
            "detail": "Public dashboard watchlist excludes internal review candidates.",
        },
        {
            "name": "dashboard_watchlist_diagnostics",
            "passed": _dashboard_has_watchlist_diagnostics(dashboard),
            "actual": _dashboard_has_watchlist_diagnostics(dashboard),
            "target": True,
            "detail": "Dashboard payload exposes candidate diagnostics and limitations for the public watchlist split.",
        },
        {
            "name": "dashboard_enrichment_fields",
            "passed": _dashboard_has_enrichment_fields(dashboard),
            "actual": _dashboard_has_enrichment_fields(dashboard),
            "target": True,
            "detail": "Dashboard payload exposes the backend enrichment sections and event geo contract.",
        },
        {
            "name": "manual_evidence_metadata",
            "passed": manual_issue_count == 0,
            "actual": manual_issue_count,
            "target": 0,
            "detail": "Manual evidence tables include source_url and notes on every row.",
        },
        {
            "name": "non_placeholder_user_agent",
            "passed": _has_real_user_agent(settings.user_agent),
            "actual": _has_real_user_agent(settings.user_agent),
            "target": "real contact string",
            "detail": "Live fetches require a real operator contact string.",
        },
        {
            "name": "public_limitations_present",
            "passed": bool(public_limitations),
            "actual": len(public_limitations),
            "target": ">=1",
            "detail": "Remaining unresolved families are called out in public limitations text.",
        },
    ]
    return checks


def collect_audit_payload(settings: Settings) -> dict:
    tranches = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    matches = read_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl")
    events = read_jsonl(settings.processed_dir / "watchlist" / "events.jsonl")
    dashboard = _load_dashboard(settings)
    manual_tables = _validate_manual_tables(settings)
    region_geocoding_codes = _load_region_geocoding_codes(settings)

    as_of = settings.as_of_date
    horizon = as_of + timedelta(days=365)
    material = [row for row in tranches if not row.get("is_programme_shell")]
    sponsor_rows = [row for row in material if _canonical_sponsor(row)]
    region_required_rows = [row for row in material if _requires_region_evidence(row)]
    region_rows = [row for row in region_required_rows if row.get("region_codes")]
    public_matches = [row for row in matches if _match_scope(row) == "public"]
    candidate_matches = [row for row in matches if _match_scope(row) == "candidate"]
    broad_matches = [row for row in matches if "broad_peril_match" in (row.get("reasons") or [])]
    unknown_region_matches = [row for row in matches if "region_unknown" in (row.get("reasons") or [])]
    public_rows_with_blockers = sum(1 for row in public_matches if row.get("public_blockers"))
    actual_next_12m = sum(
        1
        for row in material
        if row.get("status") == "outstanding"
        and (maturity_date := _to_date(row.get("maturity_date")))
        and as_of <= maturity_date <= horizon
    )

    review_candidates = []
    for row in material:
        issues_for_row: list[str] = []
        if not _canonical_sponsor(row):
            issues_for_row.append("missing_sponsor")
        if _requires_region_evidence(row) and not row.get("region_codes"):
            issues_for_row.append("missing_region")
        if "other_property_cat" in (row.get("peril_codes") or []):
            issues_for_row.append("broad_peril")
        if row.get("status") == "outstanding" and not row.get("maturity_date"):
            issues_for_row.append("missing_maturity")
        if not issues_for_row:
            continue
        priority = (
            4 * int("missing_sponsor" in issues_for_row)
            + 3 * int("missing_region" in issues_for_row)
            + 2 * int("broad_peril" in issues_for_row)
            + 1 * int("missing_maturity" in issues_for_row)
        )
        review_candidates.append(
            {
                "tranche_name": row.get("tranche_name"),
                "issuer_name": row.get("issuer_name"),
                "family_name": _family_name(row),
                "issues": issues_for_row,
                "priority": priority,
                "source_url": row.get("source_url"),
            }
        )
    review_candidates.sort(key=lambda row: (-row.get("priority", 0), row.get("tranche_name") or ""))

    amount_gap_rows = [
        row
        for row in material
        if row.get("issue_amount") in {None, ""}
    ]
    amount_gap_rows.sort(
        key=lambda row: (
            0 if row.get("status") == "outstanding" else 1,
            0 if _canonical_sponsor(row) else 1,
            -((_to_date(row.get("listed_date")) or date.min).toordinal()),
            row.get("tranche_name") or "",
        )
    )
    sponsor_gap_rows = [row for row in material if not _canonical_sponsor(row)]
    sponsor_gap_rows.sort(
        key=lambda row: (
            0 if row.get("status") == "outstanding" else 1,
            -((_to_date(row.get("listed_date")) or date.min).toordinal()),
            row.get("tranche_name") or "",
        )
    )

    coverage = {
        "sponsor_coverage_pct": round((len(sponsor_rows) / len(material) * 100.0), 2) if material else 0.0,
        "region_coverage_pct": round((len(region_rows) / len(region_required_rows) * 100.0), 2)
        if region_required_rows
        else 100.0,
        "amount_coverage_pct": round(
            (sum(1 for row in material if row.get("issue_amount") not in {None, ""}) / len(material) * 100.0), 2
        )
        if material
        else 0.0,
        "trigger_coverage_pct": round(
            (sum(1 for row in material if row.get("trigger_type") not in {None, ""}) / len(material) * 100.0), 2
        )
        if material
        else 0.0,
        "identified_sponsors": len({_canonical_sponsor(row) for row in material if _canonical_sponsor(row)}),
        "inferred_region_rows": sum(
            1
            for row in region_required_rows
            if row.get("region_inference_method") not in {None, "missing", "explicit_text"}
        ),
        "geocoded_region_rows": sum(
            1
            for row in material
            if (row.get("region_codes") or []) and all(code in region_geocoding_codes for code in (row.get("region_codes") or []))
        ),
    }
    issue_counts = {
        "broad_peril_matches": len(broad_matches),
        "unknown_region_matches": len(unknown_region_matches),
        "watchlist_review_candidates": len(candidate_matches),
        "public_watchlist_rows_with_blockers": public_rows_with_blockers,
        "candidate_match_ratio_pct": round((len(candidate_matches) / len(matches) * 100.0), 2) if matches else 0.0,
        "outstanding_missing_maturity": sum(
            1 for row in material if row.get("status") == "outstanding" and not row.get("maturity_date")
        ),
        "broad_peril_rows": sum(1 for row in material if "other_property_cat" in (row.get("peril_codes") or [])),
        "missing_issue_amount": sum(1 for row in material if row.get("issue_amount") in {None, ""}),
        "missing_trigger_type": sum(1 for row in material if row.get("trigger_type") in {None, ""}),
        "missing_region_geocoding": sum(
            1
            for row in material
            if any(code not in region_geocoding_codes for code in (row.get("region_codes") or []))
        ),
    }
    public_limitations = _public_limitations(material)
    release_checks = _build_release_checks(
        settings=settings,
        coverage=coverage,
        issues=issue_counts,
        dashboard=dashboard,
        manual_tables=manual_tables,
        public_limitations=public_limitations,
    )

    return {
        "generated_at": settings.as_of_timestamp,
        "counts": {
            "tranches": len(tranches),
            "material_tranches": len(material),
            "programme_shells": sum(1 for row in tranches if row.get("is_programme_shell")),
            "watchlist_matches": len(matches),
            "public_watchlist_matches": len(public_matches),
            "watchlist_review_candidates": len(candidate_matches),
            "watchlist_events": len(events),
        },
        "coverage": coverage,
        "issues": issue_counts,
        "dashboard_consistency": {
            "actual_next_12m_maturities": actual_next_12m,
            "dashboard_next_12m_maturities": ((dashboard.get("kpis") or {}).get("next_12m_maturities"))
            if dashboard
            else None,
            "next_12m_gap": (((dashboard.get("kpis") or {}).get("next_12m_maturities", 0)) - actual_next_12m)
            if dashboard
            else None,
            "dashboard_public_watchlist_matches": ((dashboard.get("kpis") or {}).get("watchlist_matches"))
            if dashboard
            else None,
            "actual_public_watchlist_matches": len(public_matches),
            "dashboard_review_candidates": ((dashboard.get("kpis") or {}).get("watchlist_review_candidates"))
            if dashboard
            else None,
            "actual_review_candidates": len(candidate_matches),
            "dashboard_public_watchlist_blockers": ((dashboard.get("watchlist_diagnostics") or {}).get("public_rows_with_blockers"))
            if dashboard
            else None,
            "actual_public_watchlist_blockers": public_rows_with_blockers,
            "dashboard_demo_mode": bool(dashboard.get("demo_mode")) if dashboard else None,
            "dashboard_age_days": _dashboard_age_days(dashboard, reference_date=settings.as_of_date),
        },
        "manual_evidence": manual_tables,
        "gap_analysis": {
            "top_missing_issue_amount_rows": [
                {
                    "tranche_name": row.get("tranche_name"),
                    "sponsor_name": _canonical_sponsor(row),
                    "listed_date": row.get("listed_date"),
                    "maturity_date": row.get("maturity_date"),
                    "currency": row.get("currency"),
                    "source_url": row.get("source_url"),
                }
                for row in amount_gap_rows[:15]
            ],
            "top_missing_sponsor_rows": [
                {
                    "tranche_name": row.get("tranche_name"),
                    "issuer_name": row.get("issuer_name"),
                    "listed_date": row.get("listed_date"),
                    "maturity_date": row.get("maturity_date"),
                    "source_url": row.get("source_url"),
                }
                for row in sponsor_gap_rows[:15]
            ],
            "top_missing_sponsor_families": [
                {"family_name": family_name, "missing_sponsor_rows": count}
                for family_name, count in Counter(_family_name(row) for row in sponsor_gap_rows).most_common(15)
            ],
        },
        "public_limitations": public_limitations,
        "release_gate": {
            "passed": all(check["passed"] for check in release_checks),
            "checks": release_checks,
            "failed_checks": [check["name"] for check in release_checks if not check["passed"]],
        },
        "top_review_candidates": review_candidates[:25],
    }


def _render_markdown(payload: dict) -> str:
    counts = payload.get("counts", {})
    coverage = payload.get("coverage", {})
    issues = payload.get("issues", {})
    dashboard = payload.get("dashboard_consistency", {})
    manual_evidence = payload.get("manual_evidence", {})
    gap_analysis = payload.get("gap_analysis", {})
    lines = [
        "# OpenCatWatch data audit",
        "",
        f"Generated: {payload.get('generated_at', '')}",
        "",
        "## Release gate",
        "",
        f"- Passed: {payload.get('release_gate', {}).get('passed', False)}",
    ]
    for check in payload.get("release_gate", {}).get("checks", []):
        lines.append(
            f"- {check.get('name')}: {'pass' if check.get('passed') else 'fail'} "
            f"(actual={check.get('actual')}, target={check.get('target')})"
        )
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Tranches: {counts.get('tranches', 0)}",
            f"- Material tranches: {counts.get('material_tranches', 0)}",
            f"- Programme shells: {counts.get('programme_shells', 0)}",
            f"- Watchlist matches: {counts.get('watchlist_matches', 0)}",
            f"- Public watchlist matches: {counts.get('public_watchlist_matches', 0)}",
            f"- Watchlist review candidates: {counts.get('watchlist_review_candidates', 0)}",
            f"- Watchlist events: {counts.get('watchlist_events', 0)}",
            "",
            "## Coverage",
            "",
            f"- Sponsor coverage: {coverage.get('sponsor_coverage_pct', 0.0):.1f}%",
            f"- Region coverage: {coverage.get('region_coverage_pct', 0.0):.1f}%",
            f"- Amount coverage: {coverage.get('amount_coverage_pct', 0.0):.1f}%",
            f"- Trigger coverage: {coverage.get('trigger_coverage_pct', 0.0):.1f}%",
            f"- Identified sponsors: {coverage.get('identified_sponsors', 0)}",
            f"- Inferred regions: {coverage.get('inferred_region_rows', 0)}",
            f"- Geocoded region rows: {coverage.get('geocoded_region_rows', 0)}",
            "",
            "## Issues",
            "",
            f"- Broad peril matches: {issues.get('broad_peril_matches', 0)}",
            f"- Unknown-region matches: {issues.get('unknown_region_matches', 0)}",
            f"- Watchlist review candidates: {issues.get('watchlist_review_candidates', 0)}",
            f"- Public watchlist rows with blockers: {issues.get('public_watchlist_rows_with_blockers', 0)}",
            f"- Candidate match ratio (%): {issues.get('candidate_match_ratio_pct', 0.0)}",
            f"- Outstanding rows without maturity: {issues.get('outstanding_missing_maturity', 0)}",
            f"- Broad peril rows in registry: {issues.get('broad_peril_rows', 0)}",
            f"- Missing issue amount rows: {issues.get('missing_issue_amount', 0)}",
            f"- Missing trigger type rows: {issues.get('missing_trigger_type', 0)}",
            f"- Missing region geocoding rows: {issues.get('missing_region_geocoding', 0)}",
            "",
            "## Dashboard consistency",
            "",
            f"- Actual next 12m maturities: {dashboard.get('actual_next_12m_maturities', 0)}",
            f"- Dashboard next 12m maturities: {dashboard.get('dashboard_next_12m_maturities', 0)}",
            f"- Gap: {dashboard.get('next_12m_gap', 0)}",
            f"- Actual public watchlist matches: {dashboard.get('actual_public_watchlist_matches', 0)}",
            f"- Dashboard public watchlist matches: {dashboard.get('dashboard_public_watchlist_matches', 0)}",
            f"- Actual review candidates: {dashboard.get('actual_review_candidates', 0)}",
            f"- Dashboard review candidates: {dashboard.get('dashboard_review_candidates', 0)}",
            f"- Actual public watchlist blockers: {dashboard.get('actual_public_watchlist_blockers', 0)}",
            f"- Dashboard public watchlist blockers: {dashboard.get('dashboard_public_watchlist_blockers', 0)}",
            f"- Demo mode: {dashboard.get('dashboard_demo_mode')}",
            f"- Dashboard age (days): {dashboard.get('dashboard_age_days')}",
            "",
            "## Manual evidence",
            "",
        ]
    )
    for table_name, summary in (manual_evidence.get("summary") or {}).items():
        lines.append(f"- {table_name}: {summary.get('rows', 0)} rows, {summary.get('issues', 0)} issues")
    for issue in (manual_evidence.get("issues") or [])[:20]:
        lines.append(
            f"- {issue.get('table')} row {issue.get('row_number')}: {issue.get('label')} [{issue.get('issue')}]"
        )
    lines.extend(["", "## Gap analysis", ""])
    for row in gap_analysis.get("top_missing_issue_amount_rows", [])[:10]:
        lines.append(f"- Missing amount: {row.get('tranche_name')} ({row.get('currency')})")
    for row in gap_analysis.get("top_missing_sponsor_rows", [])[:10]:
        lines.append(f"- Missing sponsor: {row.get('tranche_name')}")
    for row in gap_analysis.get("top_missing_sponsor_families", [])[:10]:
        lines.append(f"- Missing sponsor family: {row.get('family_name')} ({row.get('missing_sponsor_rows')})")
    lines.extend(["", "## Public limitations", ""])
    for limitation in payload.get("public_limitations", []):
        lines.append(f"- {limitation}")
    lines.extend(["", "## Top review candidates", ""])
    for row in payload.get("top_review_candidates", []):
        lines.append(f"- {row.get('tranche_name', 'unknown')}: {', '.join(row.get('issues', []))}")
    lines.append("")
    return "\n".join(lines)


def audit_processed_data(settings: Settings) -> str:
    payload = collect_audit_payload(settings)
    reports_dir = settings.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    write_json(reports_dir / "data_audit.json", payload)
    (reports_dir / "data_audit.md").write_text(_render_markdown(payload), encoding="utf-8")
    return str(reports_dir / "data_audit.md")


def validate_public_snapshot(settings: Settings, *, check_freshness: bool = True) -> str:
    dashboard = _load_dashboard(settings)
    audit_path = settings.reports_dir / "data_audit.json"
    if not audit_path.exists():
        raise RuntimeError("missing committed audit snapshot: reports/data_audit.json")
    payload = read_json(audit_path)
    failed_checks = (payload.get("release_gate") or {}).get("failed_checks") or []
    snapshot_failures: list[str] = []
    if not dashboard:
        snapshot_failures.append("missing_dashboard")
    elif dashboard.get("demo_mode"):
        snapshot_failures.append("dashboard_demo_mode")
    else:
        dashboard_age_days = _dashboard_age_days(dashboard, reference_date=settings.as_of_date)
        if dashboard_age_days is None or (
            check_freshness and dashboard_age_days > RELEASE_THRESHOLDS["dashboard_max_age_days"]
        ):
            snapshot_failures.append("dashboard_current")
        if not _dashboard_has_evidence_fields(dashboard):
            snapshot_failures.append("dashboard_evidence_fields")
        if not _dashboard_watchlist_is_public_only(dashboard):
            snapshot_failures.append("dashboard_public_watchlist_only")
        if not _dashboard_has_watchlist_diagnostics(dashboard):
            snapshot_failures.append("dashboard_watchlist_diagnostics")
        if not _dashboard_has_enrichment_fields(dashboard):
            snapshot_failures.append("dashboard_enrichment_fields")
        kpi_mismatches = _snapshot_kpi_mismatches(dashboard)
        if kpi_mismatches:
            snapshot_failures.append(f"dashboard_kpi_mismatch:{','.join(kpi_mismatches)}")
        audit_divergences = _snapshot_audit_divergences(dashboard, payload)
        if audit_divergences:
            snapshot_failures.append(f"dashboard_audit_divergence:{','.join(audit_divergences)}")
    if failed_checks:
        snapshot_failures.append(f"audit_release_gate:{','.join(failed_checks)}")
    if snapshot_failures:
        raise RuntimeError("public snapshot validation failed: " + "; ".join(snapshot_failures))
    return str(audit_path)


def run_release_check(settings: Settings) -> str:
    project_root = Path(__file__).resolve().parents[3]
    public_doc_errors = validate_public_docs(project_root)
    if public_doc_errors:
        raise RuntimeError("public docs check failed: " + "; ".join(public_doc_errors))
    if not settings.as_of_date_is_explicit:
        raise RuntimeError("release check requires explicit OPENCATWATCH_AS_OF_DATE for reproducible rebuilds")
    env = dict(os.environ)
    src_path = str(project_root / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}:{existing_pythonpath}"

    subprocess.run([sys.executable, "-m", "ruff", "check", "src/opencatwatch", "tests"], check=True, cwd=project_root, env=env)
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "cache_dir=/tmp/catwatch-pytest-cache"],
        check=True,
        cwd=project_root,
        env=env,
    )

    from .registry import build_registry
    from .site_data import build_site_data
    from .watchlist import build_watchlist

    build_registry(settings=settings)
    build_watchlist(settings=settings)
    build_site_data(settings=settings)
    audit_path = audit_processed_data(settings=settings)
    build_manual_review_queue(settings=settings)
    validate_public_snapshot(settings=settings)

    payload = read_json(Path(audit_path).with_suffix(".json"))
    failed_checks = (payload.get("release_gate") or {}).get("failed_checks") or []
    if failed_checks:
        raise RuntimeError(f"release gate failed: {', '.join(failed_checks)}")
    return audit_path


def build_manual_review_queue(settings: Settings, limit: int = 250) -> str:
    tranches = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    audit_payload = collect_audit_payload(settings)
    tranche_priority_order = {
        row.get("tranche_name") or "": index
        for index, row in enumerate(audit_payload.get("top_review_candidates", []))
    }
    family_priority_order = {
        limitation.split(":", 1)[0].strip(): index
        for index, limitation in enumerate(audit_payload.get("public_limitations", []))
    }
    queue_rows: list[dict[str, str | int]] = []
    for row in tranches:
        is_programme_shell = bool(row.get("is_programme_shell"))
        family_name = _family_name(row)
        issues: list[str] = []
        actions: list[str] = []
        if is_programme_shell:
            issues.append("programme_shell")
            actions.append("verify if this should be excluded from watchlist + KPIs")
        if not _canonical_sponsor(row):
            issues.append("missing_sponsor")
            actions.append("look for sponsor in SEC/BMA/manual overrides")
        if _requires_region_evidence(row) and not row.get("region_codes"):
            issues.append("missing_region")
            actions.append("set region_codes via manual override or issuer geography")
        if "other_property_cat" in (row.get("peril_codes") or []):
            issues.append("broad_peril")
            actions.append("replace broad peril with explicit peril if evidence exists")
        if row.get("status") == "outstanding" and not row.get("maturity_date"):
            issues.append("missing_maturity")
            actions.append("confirm maturity / risk end date")
        if not issues:
            continue
        priority = (
            4 * int("missing_sponsor" in issues)
            + 3 * int("missing_region" in issues)
            + 2 * int("broad_peril" in issues)
            + 1 * int("missing_maturity" in issues)
        )
        queue_rows.append(
            {
                "priority": priority,
                "is_programme_shell": is_programme_shell,
                "tranche_name": row.get("tranche_name") or "",
                "family_name": family_name,
                "record_type": row.get("record_type") or "",
                "status": row.get("status") or "",
                "issues": "; ".join(issues),
                "recommended_actions": "; ".join(actions),
                "sponsor_name": _canonical_sponsor(row) or "",
                "issuer_name": row.get("issuer_name") or "",
                "peril_codes": ", ".join(row.get("peril_codes") or []),
                "region_codes": ", ".join(row.get("region_codes") or []),
                "maturity_date": row.get("maturity_date") or "",
                "source_url": row.get("source_url") or "",
            }
        )
    queue_rows.sort(
        key=lambda row: (
            int(bool(row["is_programme_shell"])),
            tranche_priority_order.get(str(row["tranche_name"]), 10_000),
            family_priority_order.get(str(row["family_name"]), 10_000),
            -int(row["priority"]),
            normalize_name(str(row["tranche_name"])),
        )
    )
    output_path = settings.manual_dir / "review_queue.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "priority",
                "tranche_name",
                "family_name",
                "record_type",
                "status",
                "issues",
                "recommended_actions",
                "sponsor_name",
                "issuer_name",
                "peril_codes",
                "region_codes",
                "maturity_date",
                "source_url",
            ],
        )
        writer.writeheader()
        for row in queue_rows[:limit]:
            row = dict(row)
            row.pop("is_programme_shell", None)
            writer.writerow(row)
    return str(output_path)


def _requires_region_evidence(row: dict) -> bool:
    peril_codes = set(row.get("peril_codes") or [])
    if not peril_codes:
        return True
    return not peril_codes.issubset(_NON_GEOGRAPHIC_PERILS)
