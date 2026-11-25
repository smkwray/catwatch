import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from opencatwatch.config import Settings, _resolve_data_dir, get_settings
from opencatwatch.pipelines.quality import (
    audit_processed_data,
    build_manual_review_queue,
    collect_audit_payload,
    run_release_check,
    validate_public_snapshot,
)
from opencatwatch.utils import read_json, write_json, write_jsonl


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path,
    )


def test_settings_dashboard_and_reports_paths_can_stay_in_workspace_when_data_dir_is_external(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "shared" / "catwatch" / "data",
        workspace_root=workspace_root,
    )

    assert settings.dashboard_path == workspace_root / "apps" / "site" / "data" / "dashboard.json"
    assert settings.reports_dir == workspace_root / "reports"
    assert settings.manual_dir == workspace_root / "data" / "manual"


def test_resolve_data_dir_uses_shared_root_project_namespace_for_shared_workspace(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENCATWATCH_DATA_DIR", raising=False)
    monkeypatch.setenv("PROJ_SHARED_DATA_ROOT", "/tmp/shared-data-root")
    workspace_root = Path("/tmp/catwatch")

    data_dir = _resolve_data_dir(workspace_root)

    assert data_dir == Path("/tmp/shared-data-root") / "catwatch" / "data"


def test_get_settings_prefers_explicit_data_dir_over_shared_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCATWATCH_DATA_DIR", "/tmp/explicit-catwatch-data")
    monkeypatch.setenv("PROJ_SHARED_DATA_ROOT", "/tmp/shared-data-root")
    monkeypatch.delenv("OPENCATWATCH_AS_OF_DATE", raising=False)

    settings = get_settings()

    assert settings.data_dir == Path("/tmp/explicit-catwatch-data")
    assert settings.as_of_date_is_explicit is False


def test_get_settings_ignores_shared_root_for_non_shared_workspace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCATWATCH_DATA_DIR", raising=False)
    monkeypatch.setenv("PROJ_SHARED_DATA_ROOT", "/tmp/shared-data-root")
    monkeypatch.delenv("OPENCATWATCH_AS_OF_DATE", raising=False)

    settings = get_settings()

    assert settings.data_dir == Path("data")
    assert settings.as_of_date_is_explicit is False


def test_get_settings_marks_explicit_as_of_date(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCATWATCH_DATA_DIR", raising=False)
    monkeypatch.delenv("PROJ_SHARED_DATA_ROOT", raising=False)
    monkeypatch.setenv("OPENCATWATCH_AS_OF_DATE", "2026-03-27")

    settings = get_settings()

    assert settings.as_of_date == date(2026, 3, 27)
    assert settings.as_of_date_is_explicit is True


def _write_manual_tables(
    settings: Settings,
    sponsor_rows: list[dict[str, str]] | None = None,
    override_rows: list[dict[str, str]] | None = None,
    region_rows: list[dict[str, str]] | None = None,
    trigger_rows: list[dict[str, str]] | None = None,
) -> None:
    sponsor_rows = sponsor_rows or []
    override_rows = override_rows or []
    trigger_rows = trigger_rows or []
    region_rows = region_rows or [
        {
            "region_code": "us",
            "display_name": "United States",
            "iso_alpha2": "US",
            "latitude": "39.8283",
            "longitude": "-98.5795",
            "map_zoom_level": "4",
            "source_url": "https://example.com/us",
            "notes": "Representative centroid.",
        },
        {
            "region_code": "california",
            "display_name": "California, US",
            "iso_alpha2": "US",
            "latitude": "36.7783",
            "longitude": "-119.4179",
            "map_zoom_level": "5",
            "source_url": "https://example.com/california",
            "notes": "Representative centroid.",
        },
        {
            "region_code": "florida",
            "display_name": "Florida, US",
            "iso_alpha2": "US",
            "latitude": "27.6648",
            "longitude": "-81.5158",
            "map_zoom_level": "5",
            "source_url": "https://example.com/florida",
            "notes": "Representative centroid.",
        },
    ]

    sponsor_path = settings.manual_dir / "sponsor_aliases.csv"
    sponsor_path.parent.mkdir(parents=True, exist_ok=True)
    with sponsor_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["alias", "sponsor_name", "source_url", "region_codes", "peril_codes", "notes"],
        )
        writer.writeheader()
        writer.writerows(sponsor_rows)

    overrides_path = settings.manual_dir / "tranche_overrides.csv"
    with overrides_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["tranche_name", "field_name", "override_value", "source_url", "notes"],
        )
        writer.writeheader()
        writer.writerows(override_rows)

    trigger_path = settings.manual_dir / "trigger_overrides.csv"
    with trigger_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["tranche_name", "trigger_type", "source_url", "notes"],
        )
        writer.writeheader()
        writer.writerows(trigger_rows)

    region_path = settings.manual_dir / "region_geocoding.csv"
    with region_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "region_code",
                "display_name",
                "iso_alpha2",
                "latitude",
                "longitude",
                "map_zoom_level",
                "source_url",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(region_rows)


def _dashboard_payload(*, as_of: str, next_12m_maturities: int = 0, watchlist_matches: int = 0, watchlist_review_candidates: int = 0, watchlist: list[dict] | None = None, watchlist_review_rows: list[dict] | None = None, maturity_wall: list[dict] | None = None, limitations: list[str] | None = None) -> dict:
    return {
        "demo_mode": False,
        "as_of": as_of,
        "kpis": {
            "next_12m_maturities": next_12m_maturities,
            "watchlist_matches": watchlist_matches,
            "watchlist_review_candidates": watchlist_review_candidates,
        },
        "maturity_wall": maturity_wall or [],
        "watchlist": watchlist or [],
        "watchlist_review_candidates": watchlist_review_rows or [],
        "watchlist_diagnostics": {
            "public_match_count": watchlist_matches,
            "candidate_match_count": watchlist_review_candidates,
            "public_rows_with_blockers": 0,
            "candidate_reason_counts": [],
            "public_blocker_counts": [],
            "confidence_band_counts": [],
            "top_candidate_families": [],
        },
        "limitations": limitations or ["Example Family: 1 missing sponsor evidence."],
        "capital_summary": {
            "known_amount_rows": 0,
            "missing_amount_rows": 0,
            "non_usd_rows": 0,
            "by_peril": [],
            "by_sponsor": [],
            "by_listed_year": [],
        },
        "region_detail": [],
        "coverage_gaps": {
            "missing_issue_amount": 0,
            "missing_region": 0,
            "missing_maturity": 0,
            "missing_trigger_type": 0,
            "missing_sponsor": 0,
            "missing_region_geocoding": 0,
        },
        "trigger_summary": {
            "known_trigger_rows": 0,
            "missing_trigger_rows": 0,
            "by_trigger_type": [],
        },
        "registry_stats": {
            "total_rows": 0,
            "material_tranches": 0,
            "programme_shells": 0,
            "identified_sponsors": 0,
            "amount_present_rows": 0,
            "amount_missing_rows": 0,
            "currency_breakdown": [],
            "status_breakdown": [],
            "listing_status_breakdown": [],
        },
        "region_map": [],
        "story_blocks": {
            "top_sponsors_by_capital": [],
            "top_regions_by_capital": [],
            "top_perils_by_capital": [],
            "market_timeline": [],
            "maturity_runway": [],
            "upcoming_maturities_by_region": [],
            "capital_concentration": [],
            "coverage_scorecard": {
                "material_tranche_count": 0,
                "identified_sponsors": 0,
                "sponsor_coverage_pct": 0.0,
                "region_coverage_pct": 100.0,
                "amount_coverage_pct": 0.0,
                "trigger_coverage_pct": 0.0,
                "missing_issue_amount_rows": 0,
                "missing_trigger_rows": 0,
            },
            "unresolved_families": [],
            "candidate_blockers_summary": {
                "top_candidate_reasons": [],
                "top_promotion_hints": [],
                "top_candidate_families": [],
            },
            "watchlist_pressure": {
                "public_match_count": watchlist_matches,
                "candidate_match_count": watchlist_review_candidates,
                "candidate_ratio_pct": 0.0,
                "top_promotion_hints": [],
                "top_candidate_blockers_by_family": [],
            },
        },
    }


def _sample_maturity_row(*, maturity_date: str | None = None) -> dict:
    return {
        "source_url": "https://example.com/tranche-0",
        "sponsor_source_url": "https://example.com/sponsor-0",
        "sponsor_source_type": "alias",
        "peril_source_type": "explicit_text",
        "region_source_type": "explicit_text",
        "maturity_source_type": "bsx_detail",
        "review_status": "needs_review",
        "issue_amount": 100000000,
        "issue_amount_source_type": "manual_override",
        "issue_amount_source_url": "https://example.com/amount-0",
        "currency": "USD",
        "region_codes": ["us"],
        "listing_status": "Listed",
        "status": "outstanding",
        "bma_regulator_class": "Special Purpose Insurer",
        "attribution_status": {
            "sponsor": "alias",
            "trigger": "manual_override",
            "peril": "explicit_text",
            "region": "explicit_text",
            "maturity": "bsx_detail",
        },
        "sponsor_attribution_state": "alias_family",
        "maturity_date": maturity_date,
    }


def _sample_watchlist_row(*, match_scope: str = "public", exact_match_count: int = 1, public_blockers: list[str] | None = None, candidate_reason_codes: list[str] | None = None, confidence_band: str = "high") -> dict:
    return {
        "source_url": "https://example.com/event-1",
        "reason_text": "Possible overlap.",
        "matched_tranche_rows": [{"tranche_name": "Example Tranche"}],
        "exact_match_count": exact_match_count,
        "match_scope": match_scope,
        "public_blockers": public_blockers or [],
        "candidate_reason_codes": candidate_reason_codes or [],
        "confidence_band": confidence_band,
        "event_geo": {"latitude": 34.0, "longitude": -118.0, "bbox": None},
    }


def test_build_manual_review_queue_prioritizes_material_tranches_over_programme_shells(tmp_path: Path):
    settings = _settings(tmp_path)
    _write_manual_tables(settings)
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_name": "Program Shell",
                "record_type": "programme",
                "status": "outstanding",
                "is_programme_shell": True,
                "issuer_name": "Program Shell Ltd",
                "peril_codes": ["other_property_cat"],
                "region_codes": [],
                "source_url": "https://example.com/programme",
            },
            {
                "tranche_name": "Material Tranche",
                "record_type": "tranche",
                "status": "outstanding",
                "is_programme_shell": False,
                "issuer_name": "Material Re Ltd",
                "maturity_date": "2028-01-01",
                "peril_codes": ["other_property_cat"],
                "region_codes": [],
                "source_url": "https://example.com/tranche",
            },
        ],
    )

    output_path = Path(build_manual_review_queue(settings=settings, limit=10))
    with output_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert rows[0]["tranche_name"] == "Material Tranche"
    assert rows[0]["issues"] == "missing_sponsor; missing_region; broad_peril"
    assert rows[1]["tranche_name"] == "Program Shell"
    assert rows[1]["issues"] == "programme_shell; missing_sponsor; missing_region; broad_peril; missing_maturity"


def test_audit_processed_data_stays_consistent_with_dashboard_counts(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "data",
        as_of_date=date(2026, 1, 15),
    )
    _write_manual_tables(settings)
    soon = "2026-04-15"
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_name": "Supported Tranche",
                "status": "outstanding",
                "is_programme_shell": False,
                "maturity_date": soon,
                "sponsor_name": "Named Sponsor",
                "region_codes": ["us"],
                "peril_codes": ["us_wind"],
                "source_url": "https://example.com/supported",
                "region_inference_method": "sponsor_alias",
            },
            {
                "tranche_name": "Unresolved Tranche",
                "status": "outstanding",
                "is_programme_shell": False,
                "maturity_date": "2028-01-01",
                "region_codes": [],
                "peril_codes": ["other_property_cat"],
                "source_url": "https://example.com/unresolved",
                "region_inference_method": "missing",
            },
        ],
    )
    write_jsonl(
        settings.processed_dir / "watchlist" / "matches.jsonl",
        [
            {"reasons": ["peril_match", "active_date_overlap", "region_overlap"]},
            {"reasons": ["broad_peril_match", "active_date_overlap", "region_unknown"]},
        ],
    )
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [{"event_id": "evt-1"}])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(
            as_of=date(2026, 1, 15).isoformat(),
            next_12m_maturities=1,
            watchlist_matches=1,
            watchlist_review_candidates=1,
            limitations=["Unresolved Tranche: 1 missing region evidence, 1 broad peril classification."],
        ),
    )

    output_path = Path(audit_processed_data(settings=settings))
    payload = read_json(output_path.with_suffix(".json"))

    assert payload["generated_at"] == "2026-01-15T00:00:00Z"
    assert payload["counts"]["watchlist_matches"] == 2
    assert payload["counts"]["public_watchlist_matches"] == 1
    assert payload["counts"]["watchlist_review_candidates"] == 1
    assert payload["counts"]["watchlist_events"] == 1
    assert payload["issues"]["broad_peril_matches"] == 1
    assert payload["issues"]["unknown_region_matches"] == 1
    assert payload["issues"]["watchlist_review_candidates"] == 1
    assert payload["issues"]["public_watchlist_rows_with_blockers"] == 0
    assert payload["dashboard_consistency"]["actual_next_12m_maturities"] == 1
    assert payload["dashboard_consistency"]["dashboard_next_12m_maturities"] == 1
    assert payload["dashboard_consistency"]["actual_public_watchlist_matches"] == 1
    assert payload["dashboard_consistency"]["dashboard_public_watchlist_matches"] == 1
    assert payload["dashboard_consistency"]["next_12m_gap"] == 0
    assert any(row["tranche_name"] == "Unresolved Tranche" for row in payload["top_review_candidates"])


def test_collect_audit_payload_excludes_non_geographic_perils_from_region_gap(tmp_path: Path):
    settings = _settings(tmp_path / "cyber")
    _write_manual_tables(settings)
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_name": "Cyber Tranche",
                "status": "outstanding",
                "is_programme_shell": False,
                "maturity_date": "2028-01-01",
                "sponsor_name": "Named Sponsor",
                "region_codes": [],
                "peril_codes": ["cyber"],
                "source_url": "https://example.com/cyber",
                "region_inference_method": "missing",
            }
        ],
    )
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert payload["coverage"]["region_coverage_pct"] == 100.0
    assert payload["coverage"]["sponsor_coverage_pct"] == 100.0
    assert payload["public_limitations"] == []
    assert payload["top_review_candidates"] == []


def test_collect_audit_payload_flags_placeholder_user_agent(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch/0.1 (set OPENCATWATCH_USER_AGENT to a real contact URL or email)",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "data",
    )
    _write_manual_tables(settings)
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert "non_placeholder_user_agent" in payload["release_gate"]["failed_checks"]


def test_collect_audit_payload_flags_missing_manual_metadata(tmp_path: Path):
    settings = _settings(tmp_path / "case")
    _write_manual_tables(
        settings,
        sponsor_rows=[
            {
                "alias": "Example Re",
                "sponsor_name": "Example Sponsor",
                "source_url": "",
                "region_codes": "",
                "peril_codes": "",
                "notes": "",
            }
        ],
    )
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert "manual_evidence_metadata" in payload["release_gate"]["failed_checks"]
    issues = payload["manual_evidence"]["issues"]
    assert any(issue["issue"] == "missing_source_url" for issue in issues)
    assert any(issue["issue"] == "missing_notes" for issue in issues)


def test_collect_audit_payload_flags_duplicate_sponsor_alias_rows(tmp_path: Path):
    settings = _settings(tmp_path / "dup-alias")
    _write_manual_tables(
        settings,
        sponsor_rows=[
            {
                "alias": "Example Re Ltd",
                "sponsor_name": "Example Sponsor",
                "source_url": "https://example.com/one",
                "region_codes": "",
                "peril_codes": "",
                "notes": "first row",
            },
            {
                "alias": "Example Re Ltd",
                "sponsor_name": "Example Sponsor Two",
                "source_url": "https://example.com/two",
                "region_codes": "",
                "peril_codes": "",
                "notes": "duplicate row",
            },
        ],
    )
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert "manual_evidence_metadata" in payload["release_gate"]["failed_checks"]
    issues = payload["manual_evidence"]["issues"]
    assert any(issue["issue"].startswith("duplicate_row_key:") for issue in issues)


def test_collect_audit_payload_flags_duplicate_tranche_override_rows(tmp_path: Path):
    settings = _settings(tmp_path / "dup-override")
    _write_manual_tables(
        settings,
        override_rows=[
            {
                "tranche_name": "Example Re Ltd Series 2026-1",
                "field_name": "sponsor_name",
                "override_value": "Example Sponsor",
                "source_url": "https://example.com/one",
                "notes": "first row",
            },
            {
                "tranche_name": "Example Re Ltd Series 2026-1",
                "field_name": "sponsor_name",
                "override_value": "Example Sponsor Two",
                "source_url": "https://example.com/two",
                "notes": "duplicate row",
            },
        ],
    )
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert "manual_evidence_metadata" in payload["release_gate"]["failed_checks"]
    issues = payload["manual_evidence"]["issues"]
    assert any(issue["issue"].startswith("duplicate_row_key:") for issue in issues)


def test_collect_audit_payload_flags_missing_region_geocoding_metadata(tmp_path: Path):
    settings = _settings(tmp_path / "bad-region-geo")
    _write_manual_tables(
        settings,
        region_rows=[
            {
                "region_code": "us",
                "display_name": "United States",
                "iso_alpha2": "US",
                "latitude": "39.8283",
                "longitude": "-98.5795",
                "map_zoom_level": "4",
                "source_url": "",
                "notes": "",
            }
        ],
    )
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert "manual_evidence_metadata" in payload["release_gate"]["failed_checks"]
    issues = payload["manual_evidence"]["issues"]
    assert any(issue["table"] == "region_geocoding" and issue["issue"] == "missing_source_url" for issue in issues)
    assert any(issue["table"] == "region_geocoding" and issue["issue"] == "missing_notes" for issue in issues)


def test_collect_audit_payload_flags_duplicate_trigger_override_rows(tmp_path: Path):
    settings = _settings(tmp_path / "dup-trigger")
    _write_manual_tables(
        settings,
        trigger_rows=[
            {
                "tranche_name": "Example Re Ltd Series 2026-1",
                "trigger_type": "indemnity",
                "source_url": "https://example.com/one",
                "notes": "first row",
            },
            {
                "tranche_name": "Example Re Ltd Series 2026-1",
                "trigger_type": "parametric",
                "source_url": "https://example.com/two",
                "notes": "duplicate row",
            },
        ],
    )
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert "manual_evidence_metadata" in payload["release_gate"]["failed_checks"]
    issues = payload["manual_evidence"]["issues"]
    assert any(issue["table"] == "trigger_overrides" and issue["issue"].startswith("duplicate_row_key:") for issue in issues)


def test_collect_audit_payload_includes_gap_analysis_rows(tmp_path: Path):
    settings = _settings(tmp_path / "gap-analysis")
    _write_manual_tables(settings)
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_name": "Known Sponsor Missing Amount",
                "issuer_name": "Known Sponsor Missing Amount Ltd",
                "status": "outstanding",
                "is_programme_shell": False,
                "maturity_date": "2028-01-01",
                "listed_date": "2026-01-01",
                "sponsor_name": "Named Sponsor",
                "region_codes": ["us"],
                "peril_codes": ["us_wind"],
                "currency": "USD",
                "source_url": "https://example.com/amount-gap",
                "region_inference_method": "explicit_text",
            },
            {
                "tranche_name": "Missing Sponsor Row",
                "issuer_name": "Missing Sponsor Row Ltd",
                "status": "outstanding",
                "is_programme_shell": False,
                "maturity_date": "2028-02-01",
                "listed_date": "2026-02-01",
                "region_codes": ["us"],
                "peril_codes": ["us_wind"],
                "currency": "USD",
                "source_url": "https://example.com/sponsor-gap",
                "region_inference_method": "explicit_text",
            },
        ],
    )
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=date.today().isoformat()),
    )

    payload = collect_audit_payload(settings)

    assert payload["gap_analysis"]["top_missing_issue_amount_rows"][0]["tranche_name"] == "Known Sponsor Missing Amount"
    assert payload["gap_analysis"]["top_missing_sponsor_rows"][0]["tranche_name"] == "Missing Sponsor Row"
    assert payload["gap_analysis"]["top_missing_sponsor_families"][0]["family_name"] == "Missing Sponsor Row Ltd"


def test_collect_audit_payload_flags_demo_dashboard(tmp_path: Path):
    settings = _settings(tmp_path / "demo")
    _write_manual_tables(settings)
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {"demo_mode": True, "as_of": date.today().isoformat()},
    )

    payload = collect_audit_payload(settings)

    assert "dashboard_not_demo" in payload["release_gate"]["failed_checks"]


def test_collect_audit_payload_release_gate_thresholds(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch/0.1 (contact contact@example.com)",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "release",
    )
    _write_manual_tables(settings)
    soon = (date.today() + timedelta(days=120)).isoformat()
    tranches = []
    for index in range(20):
        row = {
            "tranche_name": f"Tranche {index}",
            "issuer_name": f"Issuer {index}",
            "status": "outstanding",
            "is_programme_shell": False,
            "maturity_date": soon,
            "peril_codes": ["us_wind"],
            "region_codes": ["us"],
            "source_url": f"https://example.com/tranche-{index}",
            "review_status": "needs_review",
            "sponsor_source": "alias",
            "sponsor_source_url": f"https://example.com/sponsor-{index}",
            "region_inference_method": "explicit_text",
        }
        if index < 14:
            row["sponsor_name"] = f"Sponsor {index}"
        if index == 19:
            row["maturity_date"] = ""
        if index == 18:
            row["peril_codes"] = ["other_property_cat"]
        tranches.append(row)
    write_jsonl(settings.processed_dir / "registry" / "tranches.jsonl", tranches)
    write_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl", [])
    write_jsonl(settings.processed_dir / "watchlist" / "events.jsonl", [])
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(
            as_of=date.today().isoformat(),
            next_12m_maturities=19,
            maturity_wall=[_sample_maturity_row()],
            watchlist=[_sample_watchlist_row(exact_match_count=0)],
            limitations=["Issuer 18: 1 broad peril classification."],
        ),
    )

    payload = collect_audit_payload(settings)

    assert payload["release_gate"]["passed"] is True


def test_validate_public_snapshot_rejects_candidate_rows_in_public_watchlist(tmp_path: Path):
    settings = _settings(tmp_path / "snapshot")
    _write_manual_tables(settings)
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {
            **_dashboard_payload(
                as_of=date.today().isoformat(),
                watchlist_matches=1,
                maturity_wall=[_sample_maturity_row()],
                watchlist=[
                    _sample_watchlist_row(
                        match_scope="candidate",
                        public_blockers=["missing_sponsor"],
                        candidate_reason_codes=["missing_sponsor"],
                        confidence_band="medium",
                    )
                ],
            ),
            "watchlist_diagnostics": {
                "public_match_count": 1,
                "candidate_match_count": 0,
                "public_rows_with_blockers": 1,
                "candidate_reason_counts": [{"reason_code": "missing_sponsor", "count": 1}],
                "public_blocker_counts": [{"blocker_code": "missing_sponsor", "count": 1}],
                "confidence_band_counts": [{"confidence_band": "medium", "count": 1}],
                "top_candidate_families": [],
            },
        },
    )
    write_json(
        settings.data_dir.parent / "reports" / "data_audit.json",
        {
            "release_gate": {"failed_checks": []},
            "counts": {
                "public_watchlist_matches": 0,
                "watchlist_review_candidates": 0,
            },
            "dashboard_consistency": {
                "actual_next_12m_maturities": 0,
                "actual_public_watchlist_matches": 0,
                "actual_review_candidates": 0,
                "actual_public_watchlist_blockers": 0,
                "dashboard_public_watchlist_matches": 0,
                "dashboard_review_candidates": 0,
                "dashboard_public_watchlist_blockers": 0,
            },
        },
    )

    with pytest.raises(RuntimeError, match="dashboard_public_watchlist_only"):
        validate_public_snapshot(settings)


def test_validate_public_snapshot_rejects_missing_enrichment_sections(tmp_path: Path):
    settings = _settings(tmp_path / "missing-enrichment")
    _write_manual_tables(settings)
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {
            "demo_mode": False,
            "as_of": date.today().isoformat(),
            "kpis": {"watchlist_matches": 0, "watchlist_review_candidates": 0, "next_12m_maturities": 0},
            "maturity_wall": [],
            "watchlist": [],
            "watchlist_review_candidates": [],
            "watchlist_diagnostics": {
                "public_match_count": 0,
                "candidate_match_count": 0,
                "public_rows_with_blockers": 0,
                "candidate_reason_counts": [],
                "public_blocker_counts": [],
                "confidence_band_counts": [],
                "top_candidate_families": [],
            },
            "limitations": ["Example Family: 1 missing sponsor evidence."],
        },
    )
    write_json(
        settings.data_dir.parent / "reports" / "data_audit.json",
        {"release_gate": {"failed_checks": []}},
    )

    with pytest.raises(RuntimeError, match="dashboard_enrichment_fields"):
        validate_public_snapshot(settings)


def test_validate_public_snapshot_rejects_stale_dashboard_as_of(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=(tmp_path / "stale"),
        as_of_date=date(2026, 2, 1),
    )
    _write_manual_tables(settings)
    stale_as_of = "2026-01-11"
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of=stale_as_of),
    )
    write_json(
        settings.data_dir.parent / "reports" / "data_audit.json",
        {
            "release_gate": {"failed_checks": []},
            "counts": {
                "public_watchlist_matches": 0,
                "watchlist_review_candidates": 0,
            },
            "dashboard_consistency": {
                "actual_next_12m_maturities": 0,
                "actual_public_watchlist_matches": 0,
                "actual_review_candidates": 0,
                "actual_public_watchlist_blockers": 0,
                "dashboard_public_watchlist_matches": 0,
                "dashboard_review_candidates": 0,
                "dashboard_public_watchlist_blockers": 0,
            },
        },
    )

    with pytest.raises(RuntimeError, match="dashboard_current"):
        validate_public_snapshot(settings)

    # The push gate checks consistency only: an old but intact snapshot must not block
    # unrelated pushes, while the default check above still flags its age.
    assert Path(validate_public_snapshot(settings, check_freshness=False)) == settings.reports_dir / "data_audit.json"


def test_validate_public_snapshot_without_freshness_still_requires_dashboard_date(tmp_path: Path):
    settings = _settings(tmp_path / "undated")
    _write_manual_tables(settings)
    payload = _dashboard_payload(as_of="2026-01-11")
    payload.pop("as_of")
    write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", payload)
    write_json(settings.data_dir.parent / "reports" / "data_audit.json", {"release_gate": {"failed_checks": []}})

    with pytest.raises(RuntimeError, match="dashboard_current"):
        validate_public_snapshot(settings, check_freshness=False)


def test_validate_public_snapshot_uses_settings_as_of_date_for_dashboard_age(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=(tmp_path / "as-of"),
        as_of_date=date(2026, 2, 1),
    )
    _write_manual_tables(settings)
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        _dashboard_payload(as_of="2026-01-20"),
    )
    write_json(
        settings.data_dir.parent / "reports" / "data_audit.json",
        {
            "release_gate": {"failed_checks": []},
            "counts": {
                "public_watchlist_matches": 0,
                "watchlist_review_candidates": 0,
            },
            "dashboard_consistency": {
                "actual_next_12m_maturities": 0,
                "actual_public_watchlist_matches": 0,
                "actual_review_candidates": 0,
                "actual_public_watchlist_blockers": 0,
                "dashboard_public_watchlist_matches": 0,
                "dashboard_review_candidates": 0,
                "dashboard_public_watchlist_blockers": 0,
            },
        },
    )

    assert validate_public_snapshot(settings).endswith("reports/data_audit.json")


def test_run_release_check_invokes_validate_public_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch/0.1 (contact contact@example.com)",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "release-check",
    )
    reports_dir = settings.data_dir.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    audit_path = reports_dir / "data_audit.md"
    write_json(audit_path.with_suffix(".json"), {"release_gate": {"failed_checks": []}})

    monkeypatch.setattr("opencatwatch.pipelines.quality.validate_public_docs", lambda _: [])
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: None)
    monkeypatch.setattr("opencatwatch.pipelines.registry.build_registry", lambda settings: "registry")
    monkeypatch.setattr("opencatwatch.pipelines.watchlist.build_watchlist", lambda settings: "watchlist")
    monkeypatch.setattr("opencatwatch.pipelines.site_data.build_site_data", lambda settings: "site")
    monkeypatch.setattr("opencatwatch.pipelines.quality.audit_processed_data", lambda settings: str(audit_path))
    monkeypatch.setattr("opencatwatch.pipelines.quality.build_manual_review_queue", lambda settings: "queue")

    called = {"snapshot": 0}

    def _validate_snapshot(*, settings: Settings) -> str:
        called["snapshot"] += 1
        return "snapshot"

    monkeypatch.setattr("opencatwatch.pipelines.quality.validate_public_snapshot", _validate_snapshot)

    result = run_release_check(settings=settings)

    assert result == str(audit_path)
    assert called["snapshot"] == 1


def test_run_release_check_requires_explicit_as_of_date(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch/0.1 (contact contact@example.com)",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "release-check",
        as_of_date_is_explicit=False,
    )

    with pytest.raises(RuntimeError, match="OPENCATWATCH_AS_OF_DATE"):
        run_release_check(settings=settings)


def test_validate_public_snapshot_rejects_dashboard_kpi_mismatch(tmp_path: Path):
    settings = _settings(tmp_path / "kpi-mismatch")
    _write_manual_tables(settings)
    soon = (date.today() + timedelta(days=30)).isoformat()
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {
            **_dashboard_payload(
                as_of=date.today().isoformat(),
                next_12m_maturities=2,
                watchlist_matches=1,
                maturity_wall=[_sample_maturity_row(maturity_date=soon)],
                watchlist=[_sample_watchlist_row()],
            ),
            "watchlist_diagnostics": {
                "public_match_count": 1,
                "candidate_match_count": 0,
                "public_rows_with_blockers": 0,
                "candidate_reason_counts": [],
                "public_blocker_counts": [],
                "confidence_band_counts": [{"confidence_band": "high", "count": 1}],
                "top_candidate_families": [],
            },
        },
    )
    write_json(
        settings.data_dir.parent / "reports" / "data_audit.json",
        {"release_gate": {"failed_checks": []}},
    )

    with pytest.raises(RuntimeError, match="dashboard_kpi_mismatch:next_12m_maturities"):
        validate_public_snapshot(settings)


def test_validate_public_snapshot_rejects_audit_dashboard_divergence(tmp_path: Path):
    settings = _settings(tmp_path / "audit-divergence")
    _write_manual_tables(settings)
    soon = (date.today() + timedelta(days=45)).isoformat()
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {
            **_dashboard_payload(
                as_of=date.today().isoformat(),
                next_12m_maturities=1,
                watchlist_matches=1,
                maturity_wall=[_sample_maturity_row(maturity_date=soon)],
                watchlist=[_sample_watchlist_row()],
            ),
            "watchlist_diagnostics": {
                "public_match_count": 1,
                "candidate_match_count": 0,
                "public_rows_with_blockers": 0,
                "candidate_reason_counts": [],
                "public_blocker_counts": [],
                "confidence_band_counts": [{"confidence_band": "high", "count": 1}],
                "top_candidate_families": [],
            },
        },
    )
    write_json(
        settings.data_dir.parent / "reports" / "data_audit.json",
        {
            "counts": {"public_watchlist_matches": 2, "watchlist_review_candidates": 0},
            "dashboard_consistency": {
                "actual_next_12m_maturities": 1,
                "dashboard_next_12m_maturities": 1,
                "next_12m_gap": 0,
                "dashboard_public_watchlist_matches": 2,
                "actual_public_watchlist_matches": 1,
                "dashboard_review_candidates": 0,
                "actual_review_candidates": 0,
                "dashboard_public_watchlist_blockers": 0,
                "actual_public_watchlist_blockers": 0,
                "dashboard_demo_mode": False,
                "dashboard_age_days": 0,
            },
            "release_gate": {"failed_checks": []},
        },
    )

    with pytest.raises(RuntimeError, match="dashboard_audit_divergence:watchlist_matches"):
        validate_public_snapshot(settings)
