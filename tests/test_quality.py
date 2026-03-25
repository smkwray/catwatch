import csv
from datetime import date, timedelta
from pathlib import Path

from opencatwatch.config import Settings
from opencatwatch.pipelines.quality import (
    audit_processed_data,
    build_manual_review_queue,
    collect_audit_payload,
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
        {"kpis": {"next_12m_maturities": 1}},
    )

    output_path = Path(audit_processed_data(settings=settings))
    payload = read_json(output_path.with_suffix(".json"))

    assert payload["counts"]["watchlist_matches"] == 2
    assert payload["counts"]["watchlist_events"] == 1
    assert payload["issues"]["broad_peril_matches"] == 1
    assert payload["issues"]["unknown_region_matches"] == 1
    assert payload["dashboard_consistency"]["actual_next_12m_maturities"] == 1
    assert payload["dashboard_consistency"]["dashboard_next_12m_maturities"] == 1
    assert payload["dashboard_consistency"]["next_12m_gap"] == 0
    assert any(row["tranche_name"] == "Unresolved Tranche" for row in payload["top_review_candidates"])


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
                    "review_status": "needs_review",
                }
            ],
            "watchlist": [{"source_url": "https://example.com/event-1", "reason_text": "Possible overlap.", "matched_tranche_rows": []}],
        },
    )

    payload = collect_audit_payload(settings)

    assert payload["release_gate"]["passed"] is True
