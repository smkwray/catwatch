import csv
from pathlib import Path

from opencatwatch.config import Settings
from opencatwatch.pipelines.registry import build_registry
from opencatwatch.sources.bma import build_bma_aliases, match_bma_entities, parse_bma_directory
from opencatwatch.utils import read_jsonl, write_jsonl


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path,
    )


def test_parse_bma_directory_extracts_entities():
    html = """
    <html><body>
    <div id="SearchentityData">
    <div class="main_div_tbl cms"><div class="table-responsive1">
    <table><tbody>
    <tr><th>Company Name</th><th>Sector</th><th>Address</th><th>Contact</th><th>Details</th></tr>
    <tr><td>Acorn Re Ltd.</td><td>Insurance</td><td>addr</td><td>---</td>
        <td><strong>License/Registration Type:</strong> Restricted Special Purpose Insurer</td></tr>
    <tr class="hide_show_entity"><td>Zenith Insurance Co</td><td>Insurance</td><td>addr2</td><td>---</td>
        <td><strong>License/Registration Type:</strong> Class 1</td></tr>
    </tbody></table></div></div>
    </div></body></html>
    """
    entities = parse_bma_directory(html)
    assert len(entities) == 2
    assert entities[0]["company_name"] == "Acorn Re Ltd."
    assert entities[0]["license_type"] == "Restricted Special Purpose Insurer"
    assert entities[1]["company_name"] == "Zenith Insurance Co"
    assert entities[1]["license_type"] == "Class 1"


def test_match_bma_entities_normalizes_names():
    directory = [
        {
            "company_name": "Acorn Re Ltd.",
            "company_name_normalized": "acorn re",
            "sector": "Insurance",
            "license_type": "Restricted Special Purpose Insurer",
        },
    ]
    matches = match_bma_entities(
        names=["Acorn Re Ltd"],
        directory=directory,
        source_url="https://example.com",
    )
    assert len(matches) == 1
    assert matches[0]["query_name"] == "Acorn Re Ltd"
    assert matches[0]["matched_name"] == "Acorn Re Ltd."
    assert matches[0]["regulator_class"] == "Restricted Special Purpose Insurer"


def test_build_bma_aliases_prefers_issuer_name():
    row = {
        "issuer_name": "Atlas Re Ltd SAC",
        "title": "Atlas Re Ltd SAC Series 2025-1 Class A Principal At-Risk Variable Rate Notes",
    }
    assert build_bma_aliases(row) == ["Atlas Re Ltd SAC"]


def test_build_registry_joins_bma_by_matched_name(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Atlas Re Ltd Series 2025-1 Class A",
                "issuer_name": "Atlas Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/atlas",
                "retrieved_at": "2026-03-18T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "bma" / "entity_matches.jsonl",
        [
            {
                "query_name": "Atlas Re",
                "query_name_normalized": "atlas re",
                "matched_name": "Atlas Re Ltd",
                "matched_name_normalized": "atlas re",
                "regulator_class": "Special Purpose Insurer",
                "registration_number": "12345",
            }
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["bma_match_count"] == 1
    assert tranche["bma_regulator_class"] == "Special Purpose Insurer"
    assert tranche["bma_registration_number"] == "12345"


def test_build_registry_suppresses_ambiguous_bma_matches(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Harbor Re Ltd Series 2025-1 Class A",
                "issuer_name": "Harbor Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/harbor",
                "retrieved_at": "2026-03-18T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "bma" / "entity_matches.jsonl",
        [
            {
                "query_name": "Harbor Re Ltd",
                "query_name_normalized": "harbor re",
                "matched_name": "Harbor Re Ltd",
                "matched_name_normalized": "harbor re",
                "regulator_class": "Class A",
                "registration_number": "111",
            },
            {
                "query_name": "Harbor Re Ltd",
                "query_name_normalized": "harbor re",
                "matched_name": "Harbor Re SAC",
                "matched_name_normalized": "harbor re",
                "regulator_class": "Class B",
                "registration_number": "222",
            },
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["bma_match_count"] == 2
    assert tranche["bma_regulator_class"] is None
    assert tranche["bma_registration_number"] is None


def test_build_registry_joins_sec_sponsor_via_spv_link(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Torrey Pines Re Ltd Series 2025-1 Class A",
                "issuer_name": "Torrey Pines Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/tp",
                "retrieved_at": "2026-03-19T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "sec" / "sponsor_spv_links.jsonl",
        [
            {
                "sponsor_name": "Palomar Holdings, Inc.",
                "spv_name": "Torrey Pines Re Ltd",
                "spv_name_normalized": "torrey pines re",
                "source_filing_url": "https://sec.gov/example",
                "source_term": "catastrophe bond",
            }
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sec_sponsor_name"] == "Palomar Holdings, Inc."
    assert tranche["sec_sponsor_filing_url"] == "https://sec.gov/example"
    # SEC evidence should also fill in the tranche's sponsor_name
    assert tranche["sponsor_name"] == "Palomar Holdings, Inc."


def test_build_registry_uses_curated_sponsor_alias_mapping(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Atlas Re Ltd Series 2025-1 Class A",
                "issuer_name": "Atlas Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/atlas",
                "retrieved_at": "2026-03-20T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    settings.manual_dir.mkdir(parents=True, exist_ok=True)
    with (settings.manual_dir / "sponsor_aliases.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["alias", "sponsor_name", "source_url", "region_codes", "peril_codes", "notes"])
        writer.writerow(
            [
                "Atlas Re Ltd",
                "Everest Group, Ltd.",
                "https://example.com/alias",
                '["us"]',
                '["us_wind"]',
                "curated alias",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "Everest Group, Ltd."
    assert tranche["sponsor_source"] == "alias"
    assert tranche["sponsor_source_detail"] == "Atlas Re Ltd"
    assert tranche["sponsor_source_url"] == "https://example.com/alias"
    assert tranche["region_codes"] == ["us"]
    assert tranche["peril_codes"] == ["us_wind"]


def test_build_registry_uses_curated_sponsor_alias_prefix_mapping(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Bellemeade Re 2025-1 Ltd Class B Mortgage Insurance-Linked Notes",
                "issuer_name": "Bellemeade Re 2025-1 Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/bellemeade",
                "retrieved_at": "2026-03-20T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    settings.manual_dir.mkdir(parents=True, exist_ok=True)
    with (settings.manual_dir / "sponsor_aliases.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["alias", "sponsor_name", "source_url", "region_codes", "peril_codes", "notes"])
        writer.writerow(
            [
                "Bellemeade Re",
                "Arch Capital Group Ltd.",
                "https://example.com/arch",
                '["us"]',
                '["mortgage_insurance"]',
                "family alias",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "Arch Capital Group Ltd."
    assert tranche["sponsor_source"] == "alias"
    assert tranche["sponsor_source_detail"] == "Bellemeade Re"
    assert tranche["sponsor_source_url"] == "https://example.com/arch"
    assert tranche["region_codes"] == ["us"]
    assert tranche["peril_codes"] == ["mortgage_insurance"]


def test_build_registry_sponsor_only_alias_preserves_missing_region_and_broad_peril(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "MMIFS Re Ltd Series 2025-1 Class A Principal At-Risk Variable Rate Notes",
                "issuer_name": "MMIFS Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/mmifs",
                "retrieved_at": "2026-03-24T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    settings.manual_dir.mkdir(parents=True, exist_ok=True)
    with (settings.manual_dir / "sponsor_aliases.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["alias", "sponsor_name", "source_url", "region_codes", "peril_codes", "notes"])
        writer.writerow(
            [
                "MMIFS Re Ltd",
                "TD Insurance",
                "https://example.com/mmifs-source",
                "",
                "",
                "sponsor only",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "TD Insurance"
    assert tranche["sponsor_source"] == "alias"
    assert tranche["sponsor_source_detail"] == "MMIFS Re Ltd"
    assert tranche["sponsor_source_url"] == "https://example.com/mmifs-source"
    assert tranche["peril_codes"] == ["other_property_cat"]
    assert tranche["peril_inference_method"] == "fallback_other_property_cat"
    assert tranche["region_codes"] == []
    assert tranche["region_inference_method"] == "missing"


def test_build_registry_manual_override_wins_over_family_alias_region(tmp_path: Path):
    settings = _settings(tmp_path)
    title = "Meadows Ltd Series 2025-1 Class A Principal At-Risk Variable Rate Notes due December 7, 2029"
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": title,
                "issuer_name": "Meadows Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/meadows-a",
                "retrieved_at": "2026-03-24T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    settings.manual_dir.mkdir(parents=True, exist_ok=True)
    with (settings.manual_dir / "sponsor_aliases.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["alias", "sponsor_name", "source_url", "region_codes", "peril_codes", "notes"])
        writer.writerow(
            [
                "Meadows Ltd",
                "OIS Series 2 LLC",
                "https://example.com/meadows-source",
                "",
                '["us_wind"]',
                "family alias",
            ]
        )
    with (settings.manual_dir / "tranche_overrides.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tranche_name", "field_name", "override_value", "reason"])
        writer.writerow([title, "region_codes", '["florida"]', "class-specific geography"])

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "OIS Series 2 LLC"
    assert tranche["sponsor_source"] == "alias"
    assert tranche["sponsor_source_url"] == "https://example.com/meadows-source"
    assert tranche["peril_codes"] == ["us_wind"]
    assert tranche["peril_inference_method"] == "sponsor_alias"
    assert tranche["region_codes"] == ["florida"]
    assert tranche["region_inference_method"] == "manual_override"
