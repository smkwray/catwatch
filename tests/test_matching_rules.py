from pathlib import Path

import polars as pl
import pytest

from opencatwatch.config import Settings
from opencatwatch.matching.rules import build_match, possible_overlap
from opencatwatch.pipelines.registry import _default_perils
from opencatwatch.pipelines.watchlist import (
    _canonicalize_fema,
    _canonicalize_ibtracs,
    _canonicalize_nws,
    _load_fema_events,
    _load_ibtracs_events,
    _load_storm_events,
)
from opencatwatch.utils import extract_region_codes


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "data",
    )


@pytest.mark.parametrize(
    ("place", "expected"),
    [
        ("5 km SSW of Havana, Cuba", ["cuba"]),
        ("5 km SE of Naples, Italy", ["italy"]),
        ("20 km W of Tokyo, Japan", ["japan"]),
        ("M 6.2 - 5 km N of Yuzhno-Sakhalinsk, Russia", ["russia"]),
        ("170 km SSE of Tonga Islands", ["tonga"]),
        ("45 km E of Athens, Greece", ["greece"]),
        ("60 km W of Solomon Islands", ["solomon_islands"]),
        ("100 km WNW of Kermadec Islands", ["new_zealand"]),
        ("M 5.9 - south of the Kermadec Islands", ["new_zealand"]),
        ("5 km NNW of Nikolski, Alaska, USA", ["alaska"]),
        ("M 6.0 - Andreanof Islands, Aleutian Islands, Alaska", ["alaska"]),
    ],
)
def test_extract_region_codes_handles_usgs_places(place: str, expected: list[str]):
    assert extract_region_codes(place) == expected


def test_possible_overlap_positive_case():
    tranche = {
        "tranche_id": "t1",
        "peril_codes": ["ca_earthquake"],
        "risk_start_date": "2025-01-01",
        "risk_end_date": "2027-01-01",
        "region_codes": ["california"],
        "sponsor_name": "Example Sponsor",
    }
    event = {
        "event_id": "e1",
        "peril_code": "earthquake",
        "start_time": "2026-01-10T00:00:00+00:00",
        "region_codes": ["california"],
    }
    matched, reasons, score = possible_overlap(tranche, event)
    assert matched is True
    assert "peril_match" in reasons
    assert score > 0.8


def test_possible_overlap_rejects_region_mismatch():
    tranche = {
        "tranche_id": "t1",
        "peril_codes": ["ca_wildfire"],
        "risk_start_date": "2025-01-01",
        "risk_end_date": "2027-01-01",
        "region_codes": ["california"],
    }
    event = {
        "event_id": "e1",
        "peril_code": "ca_wildfire",
        "start_time": "2026-01-10T00:00:00+00:00",
        "region_codes": ["florida"],
    }
    matched, reasons, score = possible_overlap(tranche, event)
    assert matched is False
    assert reasons == ["region_mismatch"]
    assert score == 0.0


def test_possible_overlap_supports_generic_earthquake_in_chile():
    tranche = {
        "tranche_id": "t2",
        "peril_codes": ["earthquake"],
        "risk_start_date": "2025-01-01",
        "risk_end_date": "2027-12-31",
        "region_codes": ["chile"],
        "sponsor_name": "Example Sponsor",
    }
    event = {
        "event_id": "e2",
        "peril_code": "earthquake",
        "start_time": "2026-01-10T00:00:00+00:00",
        "region_codes": ["chile"],
    }
    matched, reasons, score = possible_overlap(tranche, event)
    assert matched is True
    assert "peril_match" in reasons
    assert "region_overlap" in reasons
    assert score > 0.8


def test_build_match_status():
    tranche = {
        "tranche_id": "t1",
        "peril_codes": ["us_wind"],
        "risk_start_date": "2025-01-01",
        "risk_end_date": "2027-01-01",
        "region_codes": ["us"],
        "sponsor_name": "Example Sponsor",
        "region_source_type": "explicit_text",
        "status": "outstanding",
        "maturity_date": "2027-01-01",
    }
    event = {
        "event_id": "e1",
        "peril_code": "tropical_cyclone",
        "start_time": "2026-08-20T00:00:00+00:00",
        "region_codes": ["florida"],
    }
    match = build_match(tranche, event)
    assert match is not None
    assert match["match_status"] == "possible overlap"
    assert match["match_scope"] == "public"
    assert match["public_blockers"] == []
    assert match["candidate_reason_codes"] == []
    assert match["confidence_band"] == "high"


def test_build_match_marks_exact_overlap_as_candidate_when_tranche_has_public_blockers():
    tranche = {
        "tranche_id": "t1",
        "peril_codes": ["ca_wildfire"],
        "risk_start_date": "2025-01-01",
        "risk_end_date": "2027-01-01",
        "region_codes": ["california"],
        "region_source_type": "peril_hint",
        "status": "outstanding",
        "maturity_date": "",
    }
    event = {
        "event_id": "e1",
        "peril_code": "ca_wildfire",
        "start_time": "2026-08-20T00:00:00+00:00",
        "region_codes": ["california"],
    }
    match = build_match(tranche, event)
    assert match is not None
    assert match["match_scope"] == "candidate"
    assert set(match["public_blockers"]) == {"missing_sponsor", "missing_maturity", "weak_region_evidence"}
    assert set(match["candidate_reason_codes"]) == {"missing_sponsor", "missing_maturity", "weak_region_evidence"}
    assert match["confidence_band"] == "low"


def test_other_property_cat_matches_major_perils():
    tranche = {
        "tranche_id": "t1",
        "peril_codes": ["other_property_cat"],
        "risk_start_date": "2025-01-01",
        "risk_end_date": "2027-01-01",
        "region_codes": [],
    }
    # Should match us_wind
    matched, reasons, score = possible_overlap(tranche, {
        "event_id": "e1",
        "peril_code": "us_wind",
        "start_time": "2026-06-01",
        "region_codes": ["florida"],
    })
    assert matched is True
    assert "broad_peril_match" in reasons
    assert score < 0.8  # lower confidence than exact match

    # Should NOT match mortgage_insurance
    matched2, _, _ = possible_overlap(tranche, {
        "event_id": "e2",
        "peril_code": "mortgage_insurance",
        "start_time": "2026-06-01",
        "region_codes": [],
    })
    assert matched2 is False


def test_default_perils_uses_issuer_hints():
    assert _default_perils("Note Program", issuer_name="Everglades Re II Ltd") == ["us_wind"]
    assert _default_perils("Note Program", issuer_name="Torrey Pines Re Ltd") == ["ca_earthquake"]
    assert _default_perils("Note Program", issuer_name="Nakama Re Ltd") == ["japan_typhoon"]
    assert "us_wind" in _default_perils("Note Program", issuer_name="Kilimanjaro III Re Limited")
    assert "ca_earthquake" in _default_perils("Note Program", issuer_name="Kilimanjaro III Re Limited")


def test_default_perils_title_keywords_override_hints():
    # Title keywords should take priority
    assert _default_perils("Wildfire Protection Notes", issuer_name="Gateway Re Ltd") == ["ca_wildfire"]
    assert _default_perils("Earthquake Risk Notes", issuer_name="Seaside Re") == ["ca_earthquake"]


def test_default_perils_mortgage():
    assert _default_perils("Mortgage Insurance-Linked Notes", issuer_name="Eagle Re 2020-1 Ltd") == ["mortgage_insurance"]


def test_canonicalize_fema_hurricane():
    row = {
        "disasterNumber": 4000,
        "state": "FL",
        "incidentType": "Hurricane",
        "declarationTitle": "HURRICANE EXAMPLE",
        "incidentBeginDate": "2025-09-01",
        "incidentEndDate": "2025-09-10",
    }
    result = _canonicalize_fema(row)
    assert result is not None
    assert result["peril_code"] == "us_wind"
    assert result["region_codes"] == ["florida"]
    assert result["event_id"] == "fema-4000-FL"
    assert result["source_url"] is not None
    assert result["source_record_id"] == "4000"


def test_canonicalize_fema_skips_unknown_type():
    row = {
        "disasterNumber": 5000,
        "state": "CA",
        "incidentType": "Chemical",
        "declarationTitle": "CHEMICAL SPILL",
    }
    assert _canonicalize_fema(row) is None


def test_canonicalize_nws_extracts_multiple_regions_from_area_desc():
    row = {
        "source_event_id": "nws-1",
        "event_name": "Flood Warning",
        "headline": "Flooding possible",
        "area_desc": "Central and Eastern North Carolina; South Carolina",
        "start_time": "2026-06-01T00:00:00+00:00",
        "end_time": "2026-06-02T00:00:00+00:00",
        "source_url": "https://example.com/nws-1",
    }

    result = _canonicalize_nws(row)

    assert result is not None
    assert result["peril_code"] == "flood"
    assert result["region_codes"] == ["north_carolina", "south_carolina"]


def test_canonicalize_nws_defaults_to_us_when_area_desc_is_unrecognized():
    row = {
        "source_event_id": "nws-2",
        "event_name": "Flood Warning",
        "headline": "Flooding possible",
        "area_desc": "Zone 123",
        "start_time": "2026-06-01T00:00:00+00:00",
        "end_time": "2026-06-02T00:00:00+00:00",
        "source_url": "https://example.com/nws-2",
    }

    result = _canonicalize_nws(row)

    assert result is not None
    assert result["region_codes"] == ["us"]


def test_load_fema_events_handles_string_dates(tmp_path):
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "data",
    )
    df = pl.DataFrame(
        [
            {
                "disasterNumber": 1001,
                "state": "FL",
                "incidentType": "Hurricane",
                "declarationTitle": "HURRICANE TEST",
                "declarationDate": "2026-01-05T00:00:00.000Z",
                "incidentBeginDate": "2026-01-01T00:00:00.000Z",
                "incidentEndDate": "2026-01-02T00:00:00.000Z",
            }
        ]
    )
    path = settings.raw_dir / "openfema" / "DisasterDeclarationsSummaries.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)

    events = _load_fema_events(settings)

    assert len(events) == 1
    assert events[0]["event_id"] == "fema-1001-FL"
    assert events[0]["region_codes"] == ["florida"]


def test_load_storm_events_normalizes_state_names_without_collapsing_to_us(tmp_path):
    settings = _settings(tmp_path)
    raw_path = settings.raw_dir / "noaa_stormevents" / "StormEvents_details-2026.csv.gz"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    import csv
    import gzip

    with gzip.open(raw_path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "EVENT_ID",
                "EPISODE_ID",
                "EVENT_TYPE",
                "STATE",
                "STATE_FIPS",
                "BEGIN_YEARMONTH",
                "BEGIN_DAY",
                "END_YEARMONTH",
                "END_DAY",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "EVENT_ID": "1",
                "EPISODE_ID": "1001",
                "EVENT_TYPE": "Hurricane",
                "STATE": "North Carolina",
                "STATE_FIPS": "37",
                "BEGIN_YEARMONTH": "202606",
                "BEGIN_DAY": "01",
                "END_YEARMONTH": "202606",
                "END_DAY": "02",
            }
        )
        writer.writerow(
            {
                "EVENT_ID": "2",
                "EPISODE_ID": "1002",
                "EVENT_TYPE": "Tropical Storm",
                "STATE": "Texas",
                "STATE_FIPS": "48",
                "BEGIN_YEARMONTH": "202606",
                "BEGIN_DAY": "03",
                "END_YEARMONTH": "202606",
                "END_DAY": "04",
            }
        )

    events = _load_storm_events(settings)
    events_by_id = {row["event_id"]: row for row in events}

    assert events_by_id["se-1001"]["region_codes"] == ["north_carolina"]
    assert events_by_id["se-1002"]["region_codes"] == ["texas"]
    assert events_by_id["se-1001"]["region_codes"] != ["us"]


def test_canonicalize_ibtracs_tracks_tropical_cyclone():
    row = {
        "SID": "2026001",
        "ISO_TIME": "2026-03-01 12:00:00",
        "BASIN": "NA",
        "NAME": "ALPHA",
        "NATURE": "NR",
    }
    result = _canonicalize_ibtracs(row)
    assert result is not None
    assert result["event_id"] == "ibtracs-2026001"
    assert result["source_name"] == "ibtracs"
    assert result["peril_code"] == "us_wind"
    assert result["region_codes"] == ["us"]
    assert result["start_time"] == "2026-03-01"
    assert result["source_url"] is not None
    assert result["source_record_id"] == "2026001"


def test_load_ibtracs_events_collapses_storm_tracks(tmp_path):
    settings = _settings(tmp_path)
    path = settings.raw_dir / "ibtracs" / "ibtracs.ACTIVE.list.v04r01.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "SID,ISO_TIME,BASIN,NAME",
                "2026001,2026-03-02 00:00:00,NA,ALPHA",
                "2026001,2026-03-01 00:00:00,NA,ALPHA",
                "2026002,2026-03-03 00:00:00,WP,UNNAMED",
            ]
        )
    )

    events = _load_ibtracs_events(settings)
    event_ids = {row["event_id"] for row in events}
    assert event_ids == {"ibtracs-2026001", "ibtracs-2026002"}
    first = next(row for row in events if row["event_id"] == "ibtracs-2026001")
    assert first["start_time"] == "2026-03-01"
    assert first["event_name"] == "ALPHA Tropical Cyclone"
    second = next(row for row in events if row["event_id"] == "ibtracs-2026002")
    assert second["peril_code"] == "japan_typhoon"
    assert second["event_name"] == "Unspecified Tropical Cyclone"
