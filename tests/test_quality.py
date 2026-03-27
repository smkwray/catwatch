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


def test_resolve_data_dir_uses_shared_root_project_namespace_for_shared_workspace(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENCATWATCH_DATA_DIR", raising=False)
    monkeypatch.setenv("PROJ_SHARED_DATA_ROOT", "/tmp/shared-data-root")
    workspace_root = Path("/tmp/catwatch-workspace/catwatch")

    data_dir = _resolve_data_dir(workspace_root)

    assert data_dir == Path("/tmp/shared-data-root") / "catwatch" / "data"


def test_get_settings_prefers_explicit_data_dir_over_shared_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCATWATCH_DATA_DIR", "/tmp/explicit-catwatch-data")
    monkeypatch.setenv("PROJ_SHARED_DATA_ROOT", "/tmp/shared-data-root")
    monkeypatch.delenv("OPENCATWATCH_AS_OF_DATE", raising=False)

    settings = get_settings()

    assert settings.data_dir == Path("/tmp/explicit-catwatch-data")


def test_get_settings_ignores_shared_root_for_non_shared_workspace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCATWATCH_DATA_DIR", raising=False)
    monkeypatch.setenv("PROJ_SHARED_DATA_ROOT", "/tmp/shared-data-root")
    monkeypatch.delenv("OPENCATWATCH_AS_OF_DATE", raising=False)

    settings = get_settings()

    assert settings.data_dir == Path("data")


def _write_manual_tables(
    settings: Settings,
    sponsor_rows: list[dict[str, str]] | None = None,
    override_rows: list[dict[str, str]] | None = None,
) -> None:
    sponsor_rows = sponsor_rows or []
    override_rows = override_rows or []

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
    )
    _write_manual_tables(settings)
    soon = (date.today() + timedelta(days=90)).isoformat()
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
        {
            "kpis": {"next_12m_maturities": 1, "watchlist_matches": 1, "watchlist_review_candidates": 1},
            "watchlist_diagnostics": {
                "public_match_count": 1,
                "candidate_match_count": 1,
                "public_rows_with_blockers": 0,
                "candidate_reason_counts": [],
                "public_blocker_counts": [],
                "confidence_band_counts": [],
                "top_candidate_families": [],
            },
            "limitations": ["Unresolved Tranche: 1 missing region evidence, 1 broad peril classification."],
        },
    )

    output_path = Path(audit_processed_data(settings=settings))
    payload = read_json(output_path.with_suffix(".json"))

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
    write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", {"demo_mode": False, "as_of": date.today().isoformat()})

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
    write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", {"demo_mode": False, "as_of": date.today().isoformat()})

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
    write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", {"demo_mode": False, "as_of": date.today().isoformat()})

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
    write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", {"demo_mode": False, "as_of": date.today().isoformat()})

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
    write_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json", {"demo_mode": False, "as_of": date.today().isoformat()})

    payload = collect_audit_payload(settings)

    assert "manual_evidence_metadata" in payload["release_gate"]["failed_checks"]
    issues = payload["manual_evidence"]["issues"]
    assert any(issue["issue"].startswith("duplicate_row_key:") for issue in issues)


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
        {
            "demo_mode": False,
            "as_of": date.today().isoformat(),
            "kpis": {"next_12m_maturities": 19},
                "maturity_wall": [
                    {
                        "source_url": "https://example.com/tranche-0",
                        "sponsor_source_url": "https://example.com/sponsor-0",
                        "sponsor_source_type": "alias",
                        "peril_source_type": "explicit_text",
                        "region_source_type": "explicit_text",
                        "maturity_source_type": "bsx_detail",
                        "review_status": "needs_review",
                    }
                ],
                "watchlist": [
                    {
                        "source_url": "https://example.com/event-1",
                        "reason_text": "Possible overlap.",
                        "matched_tranche_rows": [],
                        "match_scope": "public",
                        "public_blockers": [],
                        "candidate_reason_codes": [],
                        "confidence_band": "high",
                    }
                ],
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
                "limitations": ["Issuer 18: 1 broad peril classification."],
            },
        )

    payload = collect_audit_payload(settings)

    assert payload["release_gate"]["passed"] is True


def test_validate_public_snapshot_rejects_candidate_rows_in_public_watchlist(tmp_path: Path):
    settings = _settings(tmp_path / "snapshot")
    _write_manual_tables(settings)
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {
            "demo_mode": False,
            "as_of": date.today().isoformat(),
            "kpis": {"watchlist_matches": 1},
            "maturity_wall": [
                {
                    "source_url": "https://example.com/tranche-0",
                    "sponsor_source_url": "https://example.com/sponsor-0",
                    "sponsor_source_type": "alias",
                    "peril_source_type": "explicit_text",
                    "region_source_type": "explicit_text",
                    "maturity_source_type": "bsx_detail",
                    "review_status": "needs_review",
                }
            ],
            "watchlist": [
                {
                    "source_url": "https://example.com/event-1",
                    "reason_text": "Possible overlap.",
                    "matched_tranche_rows": [],
                    "match_scope": "candidate",
                    "public_blockers": ["missing_sponsor"],
                    "candidate_reason_codes": ["missing_sponsor"],
                    "confidence_band": "medium",
                }
            ],
            "watchlist_review_candidates": [],
            "watchlist_diagnostics": {
                "public_match_count": 1,
                "candidate_match_count": 0,
                "public_rows_with_blockers": 1,
                "candidate_reason_counts": [{"reason_code": "missing_sponsor", "count": 1}],
                "public_blocker_counts": [{"blocker_code": "missing_sponsor", "count": 1}],
                "confidence_band_counts": [{"confidence_band": "medium", "count": 1}],
                "top_candidate_families": [],
            },
            "limitations": ["Example Family: 1 missing sponsor evidence."],
        },
    )
    write_json(
        settings.data_dir.parent / "reports" / "data_audit.json",
        {"release_gate": {"failed_checks": []}},
    )

    with pytest.raises(RuntimeError, match="dashboard_public_watchlist_only"):
        validate_public_snapshot(settings)


def test_validate_public_snapshot_rejects_stale_dashboard_as_of(tmp_path: Path):
    settings = _settings(tmp_path / "stale")
    _write_manual_tables(settings)
    stale_as_of = (date.today() - timedelta(days=21)).isoformat()
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {
            "demo_mode": False,
            "as_of": stale_as_of,
            "kpis": {"next_12m_maturities": 0, "watchlist_matches": 0, "watchlist_review_candidates": 0},
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

    with pytest.raises(RuntimeError, match="dashboard_current"):
        validate_public_snapshot(settings)


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


def test_validate_public_snapshot_rejects_dashboard_kpi_mismatch(tmp_path: Path):
    settings = _settings(tmp_path / "kpi-mismatch")
    _write_manual_tables(settings)
    soon = (date.today() + timedelta(days=30)).isoformat()
    write_json(
        settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json",
        {
            "demo_mode": False,
            "as_of": date.today().isoformat(),
            "kpis": {"next_12m_maturities": 2, "watchlist_matches": 1, "watchlist_review_candidates": 0},
            "maturity_wall": [
                {
                    "source_url": "https://example.com/tranche-0",
                    "sponsor_source_url": "https://example.com/sponsor-0",
                    "sponsor_source_type": "alias",
                    "peril_source_type": "explicit_text",
                    "region_source_type": "explicit_text",
                    "maturity_source_type": "bsx_detail",
                    "review_status": "needs_review",
                    "maturity_date": soon,
                }
            ],
            "watchlist": [
                {
                    "source_url": "https://example.com/event-1",
                    "reason_text": "Possible overlap.",
                    "matched_tranche_rows": [{"tranche_name": "Example Tranche"}],
                    "exact_match_count": 1,
                    "match_scope": "public",
                    "public_blockers": [],
                    "candidate_reason_codes": [],
                    "confidence_band": "high",
                }
            ],
            "watchlist_review_candidates": [],
            "watchlist_diagnostics": {
                "public_match_count": 1,
                "candidate_match_count": 0,
                "public_rows_with_blockers": 0,
                "candidate_reason_counts": [],
                "public_blocker_counts": [],
                "confidence_band_counts": [{"confidence_band": "high", "count": 1}],
                "top_candidate_families": [],
            },
            "limitations": ["Example Family: 1 missing sponsor evidence."],
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
            "demo_mode": False,
            "as_of": date.today().isoformat(),
            "kpis": {"next_12m_maturities": 1, "watchlist_matches": 1, "watchlist_review_candidates": 0},
            "maturity_wall": [
                {
                    "source_url": "https://example.com/tranche-0",
                    "sponsor_source_url": "https://example.com/sponsor-0",
                    "sponsor_source_type": "alias",
                    "peril_source_type": "explicit_text",
                    "region_source_type": "explicit_text",
                    "maturity_source_type": "bsx_detail",
                    "review_status": "needs_review",
                    "maturity_date": soon,
                }
            ],
            "watchlist": [
                {
                    "source_url": "https://example.com/event-1",
                    "reason_text": "Possible overlap.",
                    "matched_tranche_rows": [{"tranche_name": "Example Tranche"}],
                    "exact_match_count": 1,
                    "match_scope": "public",
                    "public_blockers": [],
                    "candidate_reason_codes": [],
                    "confidence_band": "high",
                }
            ],
            "watchlist_review_candidates": [],
            "watchlist_diagnostics": {
                "public_match_count": 1,
                "candidate_match_count": 0,
                "public_rows_with_blockers": 0,
                "candidate_reason_counts": [],
                "public_blocker_counts": [],
                "confidence_band_counts": [{"confidence_band": "high", "count": 1}],
                "top_candidate_families": [],
            },
            "limitations": ["Example Family: 1 missing sponsor evidence."],
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
