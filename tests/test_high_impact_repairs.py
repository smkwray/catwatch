from datetime import date, timedelta
from pathlib import Path

from opencatwatch.config import Settings
from opencatwatch.matching.rules import possible_overlap
from opencatwatch.pipelines.registry import build_registry
from opencatwatch.pipelines.site_data import build_site_data
from opencatwatch.pipelines.watchlist import build_watchlist
from opencatwatch.utils import read_json, read_jsonl, write_jsonl


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "data",
    )


def test_possible_overlap_unknown_region_has_lower_confidence():
    tranche = {
        "tranche_id": "t1",
        "peril_codes": ["ca_earthquake"],
        "risk_start_date": "2025-01-01",
        "risk_end_date": "2027-01-01",
        "region_codes": [],
    }
    event = {
        "event_id": "e1",
        "peril_code": "earthquake",
        "start_time": "2026-01-10T00:00:00+00:00",
        "region_codes": ["california"],
    }
    matched, reasons, score = possible_overlap(tranche, event)
    assert matched is True
    assert "region_unknown" in reasons
    assert score < 0.9


def test_build_registry_marks_programme_shell_and_infers_region(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Nakama Re Ltd - Principal At-Risk Variable Note Programme",
                "issuer_name": "Nakama Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/nakama",
                "retrieved_at": "2026-03-20T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["record_type"] == "programme"
    assert tranche["is_programme_shell"] is True
    assert tranche["region_codes"] == ["japan"]
    assert tranche["region_inference_method"] in {"issuer_hint", "peril_hint"}


def test_build_watchlist_skips_programme_shells_and_writes_events(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_id": "programme-1",
                "tranche_name": "Shell Programme",
                "record_type": "programme",
                "is_programme_shell": True,
                "status": "outstanding",
                "peril_codes": ["ca_wildfire"],
                "region_codes": ["california"],
            },
            {
                "tranche_id": "tranche-1",
                "tranche_name": "Live Tranche",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "peril_codes": ["ca_wildfire"],
                "region_codes": ["california"],
                "risk_start_date": "2025-01-01",
                "risk_end_date": "2027-01-01",
            },
        ],
    )
    write_jsonl(
        settings.processed_dir / "nws" / "alerts_active.jsonl",
        [
            {
                "source_event_id": "nws-1",
                "event_name": "Red Flag Warning",
                "headline": "Critical fire weather conditions",
                "start_time": "2026-06-10",
                "end_time": "2026-06-11",
                "area_desc": "California",
                "source_url": "https://example.com/nws-1",
            }
        ],
    )
    write_jsonl(settings.processed_dir / "usgs" / "events.jsonl", [])

    build_watchlist(settings)
    matches = read_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl")
    events = read_jsonl(settings.processed_dir / "watchlist" / "events.jsonl")
    assert len(events) == 1
    assert len(matches) == 1
    assert matches[0]["tranche_id"] == "tranche-1"
    assert matches[0]["event_name"] == "Red Flag Warning"
    assert matches[0]["match_scope"] == "candidate"
    assert "missing_sponsor" in matches[0]["public_blockers"]


def test_build_watchlist_includes_ibtracs_events(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_id": "tranche-2",
                "tranche_name": "Live Typhoon Tranche",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "peril_codes": ["us_wind"],
                "region_codes": ["us"],
                "risk_start_date": "2025-01-01",
                "risk_end_date": "2027-01-01",
            }
        ],
    )
    write_jsonl(settings.processed_dir / "nws" / "alerts_active.jsonl", [])
    write_jsonl(settings.processed_dir / "usgs" / "events.jsonl", [])
    ibtracs_path = settings.raw_dir / "ibtracs" / "ibtracs.ACTIVE.list.v04r01.csv"
    ibtracs_path.parent.mkdir(parents=True, exist_ok=True)
    ibtracs_path.write_text(
        "\n".join(
            [
                "SID,ISO_TIME,BASIN,NAME",
                "2026003,2026-03-05 00:00:00,NA,ALPHA",
                "2026003,2026-03-06 00:00:00,NA,ALPHA",
            ]
        )
    )

    build_watchlist(settings)
    events = read_jsonl(settings.processed_dir / "watchlist" / "events.jsonl")
    matches = read_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl")

    assert any(
        row["event_id"] == "ibtracs-2026003" and row["source_name"] == "ibtracs" for row in events
    )
    assert any(
        match["event_id"] == "ibtracs-2026003"
        and match["event_name"] == "ALPHA Tropical Cyclone"
        for match in matches
    )


def test_build_watchlist_prefilter_keeps_generic_earthquake_crosswalk(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=(tmp_path / "data"),
        as_of_date=date(2026, 1, 15),
    )
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_id": "quake-1",
                "tranche_name": "California Quake Tranche",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "peril_codes": ["ca_earthquake"],
                "region_codes": ["california"],
                "risk_start_date": "2025-01-01",
                "risk_end_date": "2027-01-01",
                "sponsor_name": "Example Sponsor",
                "region_source_type": "explicit_text",
                "maturity_date": "2027-01-01",
            },
            {
                "tranche_id": "wind-1",
                "tranche_name": "Wind Tranche",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "peril_codes": ["us_wind"],
                "region_codes": ["us"],
                "risk_start_date": "2025-01-01",
                "risk_end_date": "2027-01-01",
                "sponsor_name": "Example Sponsor",
                "region_source_type": "explicit_text",
                "maturity_date": "2027-01-01",
            },
        ],
    )
    write_jsonl(settings.processed_dir / "nws" / "alerts_active.jsonl", [])
    write_jsonl(
        settings.processed_dir / "usgs" / "events.jsonl",
        [
            {
                "source_event_id": "usgs-1",
                "event_name": "M 6.1 - offshore California",
                "peril_code": "earthquake",
                "start_time": "2026-04-01T00:00:00+00:00",
                "end_time": None,
                "region_codes": ["california"],
                "source_url": "https://example.com/usgs-1",
            }
        ],
    )

    build_watchlist(settings)
    matches = read_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl")

    assert len(matches) == 1
    assert matches[0]["tranche_id"] == "quake-1"
    assert matches[0]["event_id"] == "usgs-1"
    assert matches[0]["match_scope"] == "public"
    assert matches[0]["generated_at"] == "2026-01-15T00:00:00Z"


def test_build_site_data_uses_event_metadata_and_correct_maturity_kpi(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=(tmp_path / "data"),
        as_of_date=date(2026, 1, 15),
    )
    soon = "2026-04-15"
    far = "2028-07-03"
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_id": "t1",
                "programme_id": "prog-1",
                "tranche_name": "Example Re 2026-1 Class A",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "maturity_date": soon,
                "listed_date": "2025-06-01",
                "peril_codes": ["ca_wildfire"],
                "region_codes": ["california"],
                "sponsor_name": "Example Sponsor",
                "review_status": "needs_review",
                "source_url": "https://example.com/t1",
                "sponsor_source": "alias",
                "sponsor_source_url": "https://example.com/sponsor",
            },
            {
                "tranche_id": "t2",
                "programme_id": "prog-2",
                "tranche_name": "Far Future Re 2028-1",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "maturity_date": far,
                "listed_date": "2025-06-01",
                "peril_codes": ["ca_wildfire"],
                "region_codes": ["california"],
                "sponsor_name": "Future Sponsor",
                "review_status": "needs_review",
                "source_url": "https://example.com/t2",
                "sponsor_source": "bsx",
                "sponsor_source_url": "https://example.com/t2",
            },
            {
                "tranche_id": "p1",
                "programme_id": "prog-3",
                "tranche_name": "Programme Shell",
                "record_type": "programme",
                "is_programme_shell": True,
                "status": "outstanding",
                "maturity_date": None,
                "listed_date": "2025-01-01",
                "peril_codes": ["other_property_cat"],
                "region_codes": [],
            },
        ],
    )
    write_jsonl(
        settings.processed_dir / "watchlist" / "events.jsonl",
        [
            {
                "event_id": "evt-1",
                "event_name": "California Red Flag Warning",
                "peril_code": "ca_wildfire",
                "start_time": "2026-05-20",
                "region_codes": ["california"],
                "source_name": "nws",
                "source_url": "https://example.com/event",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "watchlist" / "matches.jsonl",
        [
            {
                "match_id": "m1",
                "event_id": "evt-1",
                "event_name": "California Red Flag Warning",
                "event_peril_code": "ca_wildfire",
                "event_region_codes": ["california"],
                "tranche_id": "t1",
                "tranche_name": "Example Re 2026-1 Class A",
                "score": 0.9,
                "reasons": ["peril_match", "active_date_overlap", "region_overlap"],
            }
        ],
    )

    build_site_data(settings)
    dashboard = read_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json")
    assert dashboard["as_of"] == "2026-01-15"
    assert dashboard["kpis"]["next_12m_maturities"] == 1
    assert dashboard["watchlist"][0]["event_name"] == "California Red Flag Warning"
    assert dashboard["watchlist"][0]["matched_tranches"] == ["Example Re 2026-1 Class A"]
    assert dashboard["watchlist"][0]["source_url"] == "https://example.com/event"
    assert dashboard["watchlist"][0]["reason_text"] == "1 public peril/date/geography overlap in the public tranche registry."
    assert dashboard["watchlist"][0]["match_scope"] == "public"
    assert dashboard["watchlist"][0]["candidate_reason_codes"] == []
    assert dashboard["watchlist_diagnostics"]["public_match_count"] == 1
    assert dashboard["watchlist_diagnostics"]["candidate_match_count"] == 0
    assert dashboard["limitations"] == []
    assert dashboard["watchlist"][0]["matched_tranche_rows"][0]["source_url"] == "https://example.com/t1"
    assert dashboard["watchlist"][0]["matched_tranche_rows"][0]["sponsor_source_url"] == "https://example.com/sponsor"
    assert dashboard["watchlist"][0]["matched_tranche_rows"][0]["sponsor_source_type"] == "alias"
    assert "peril" in dashboard["watchlist"][0]["matched_tranche_rows"][0]["reason_text"]


def test_build_site_data_separates_review_candidates_from_public_watchlist(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_id": "t1",
                "programme_id": "prog-1",
                "tranche_name": "Exact Re",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "maturity_date": (date.today() + timedelta(days=90)).isoformat(),
                "listed_date": "2025-06-01",
                "peril_codes": ["ca_wildfire"],
                "region_codes": ["california"],
                "review_status": "needs_review",
                "source_url": "https://example.com/exact",
                "sponsor_source": "missing",
            },
            {
                "tranche_id": "t2",
                "programme_id": "prog-2",
                "tranche_name": "Broad Re",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "maturity_date": (date.today() + timedelta(days=120)).isoformat(),
                "listed_date": "2025-06-01",
                "peril_codes": ["other_property_cat"],
                "region_codes": [],
                "review_status": "needs_review",
                "source_url": "https://example.com/broad",
                "sponsor_source": "missing",
            },
        ],
    )
    write_jsonl(
        settings.processed_dir / "watchlist" / "events.jsonl",
        [
            {
                "event_id": "evt-1",
                "event_name": "California Red Flag Warning",
                "peril_code": "ca_wildfire",
                "start_time": "2026-05-20",
                "region_codes": ["california"],
                "source_name": "nws",
                "source_url": "https://example.com/event",
                "source_record_id": "evt-1",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "watchlist" / "matches.jsonl",
        [
            {
                "match_id": "m1",
                "event_id": "evt-1",
                "tranche_id": "t1",
                "tranche_name": "Exact Re",
                "score": 0.9,
                "reasons": ["peril_match", "active_date_overlap", "region_overlap"],
            },
            {
                "match_id": "m2",
                "event_id": "evt-1",
                "tranche_id": "t2",
                "tranche_name": "Broad Re",
                "score": 0.55,
                "reasons": ["broad_peril_match", "active_date_overlap", "region_unknown"],
            },
        ],
    )

    build_site_data(settings)
    dashboard = read_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json")

    assert dashboard["kpis"]["watchlist_matches"] == 1
    assert dashboard["kpis"]["watchlist_review_candidates"] == 1
    assert dashboard["watchlist"][0]["match_scope"] == "public"
    assert dashboard["watchlist_review_candidates"][0]["match_scope"] == "candidate"
    assert set(dashboard["watchlist_review_candidates"][0]["candidate_reason_codes"]) == {
        "broad_peril",
        "broad_peril_match",
        "missing_sponsor",
        "region_unknown",
        "weak_region_evidence",
    }
    assert dashboard["watchlist_diagnostics"]["candidate_reason_counts"][0]["reason_code"] in {
        "broad_peril",
        "broad_peril_match",
        "missing_sponsor",
        "region_unknown",
        "weak_region_evidence",
    }


def test_build_site_data_deduplicates_matched_tranche_rows(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "registry" / "tranches.jsonl",
        [
            {
                "tranche_id": "t1",
                "tranche_name": "Example Re",
                "record_type": "tranche",
                "is_programme_shell": False,
                "status": "outstanding",
                "maturity_date": "2028-01-01",
                "listed_date": "2025-01-01",
                "peril_codes": ["ca_wildfire"],
                "region_codes": ["california"],
                "sponsor_name": "Example Sponsor",
                "review_status": "needs_review",
                "source_url": "https://example.com/t1",
                "sponsor_source": "alias",
                "sponsor_source_url": "https://example.com/sponsor",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "watchlist" / "events.jsonl",
        [
            {
                "event_id": "evt-1",
                "event_name": "California Red Flag Warning",
                "peril_code": "ca_wildfire",
                "start_time": "2026-05-20",
                "region_codes": ["california"],
                "source_url": "https://example.com/event",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "watchlist" / "matches.jsonl",
        [
            {
                "match_id": "m1",
                "event_id": "evt-1",
                "tranche_id": "t1",
                "tranche_name": "Example Re",
                "score": 0.8,
                "reasons": ["peril_match", "active_date_overlap", "region_overlap"],
            },
            {
                "match_id": "m2",
                "event_id": "evt-1",
                "tranche_id": "t1",
                "tranche_name": "Example Re",
                "score": 0.9,
                "reasons": ["peril_match", "active_date_overlap", "region_overlap"],
            },
        ],
    )

    build_site_data(settings)
    dashboard = read_json(settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json")

    assert len(dashboard["watchlist"][0]["matched_tranche_rows"]) == 1
    assert dashboard["watchlist"][0]["matched_tranche_rows"][0]["score"] == 0.9
