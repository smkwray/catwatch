import csv
from datetime import date
from pathlib import Path

from opencatwatch.config import Settings
from opencatwatch.pipelines.registry import build_registry
from opencatwatch.sources.bma import (
    build_bma_aliases,
    build_bma_review_candidates,
    match_bma_entities,
    parse_bma_directory,
)
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


def test_build_bma_review_candidates_ranks_near_matches():
    directory = [
        {
            "company_name": "Artex Axcell Re (Bermuda) Limited",
            "company_name_normalized": "artex axcell re bermuda",
            "sector": "Insurance",
            "license_type": "Restricted Special Purpose Insurer",
        },
        {
            "company_name": "Artex Axcell Holdings Limited",
            "company_name_normalized": "artex axcell holdings",
            "sector": "Insurance",
            "license_type": "Class 3A",
        },
    ]
    candidates = build_bma_review_candidates(
        names=["Artex Axcell Re (Bermuda) Ltd"],
        directory=directory,
        source_url="https://example.com",
    )
    assert candidates[0]["matched_name"] == "Artex Axcell Re (Bermuda) Limited"
    assert candidates[0]["candidate_rank"] == 1
    assert candidates[0]["candidate_score"] >= candidates[1]["candidate_score"]


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
    assert tranche["bma_match_method"] == "exact"
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
    assert tranche["bma_match_method"] == "manual_review"
    assert tranche["bma_regulator_class"] is None
    assert tranche["bma_registration_number"] is None


def test_build_registry_auto_accepts_ranked_bma_candidate_when_clearly_dominant(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Artex Axcell Re (Bermuda) Ltd ILS Note Program II",
                "issuer_name": "Artex Axcell Re (Bermuda) Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/artex",
                "retrieved_at": "2026-03-26T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "bma" / "entity_review_candidates.jsonl",
        [
            {
                "query_name": "Artex Axcell Re (Bermuda) Ltd",
                "query_name_normalized": "artex axcell re bermuda",
                "matched_name": "Artex Axcell Re (Bermuda) Limited",
                "matched_name_normalized": "artex axcell re bermuda",
                "regulator_class": "Restricted Special Purpose Insurer",
                "candidate_score": 0.96,
                "candidate_rank": 1,
            },
            {
                "query_name": "Artex Axcell Re (Bermuda) Ltd",
                "query_name_normalized": "artex axcell re bermuda",
                "matched_name": "Artex Axcell Holdings Limited",
                "matched_name_normalized": "artex axcell holdings",
                "regulator_class": "Class 3A",
                "candidate_score": 0.61,
                "candidate_rank": 2,
            },
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["bma_match_method"] == "ranked_auto"
    assert tranche["bma_regulator_class"] == "Restricted Special Purpose Insurer"
    assert tranche["bma_top_candidate_name"] == "Artex Axcell Re (Bermuda) Limited"
    assert tranche["bma_top_candidate_score"] == 0.96


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
    assert tranche["sec_match_method"] == "exact"
    assert tranche["sec_sponsor_name"] == "Palomar Holdings, Inc."
    assert tranche["sec_sponsor_filing_url"] == "https://sec.gov/example"
    # SEC evidence should also fill in the tranche's sponsor_name
    assert tranche["sponsor_name"] == "Palomar Holdings, Inc."
    assert tranche["sponsor_attribution_state"] == "sec_exact_spv"


def test_build_registry_auto_accepts_ranked_sec_spv_candidate_when_clearly_dominant(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Torrey Pines Re Ltd SAC Series 2025-1 Class A",
                "issuer_name": "Torrey Pines Re Ltd SAC",
                "listing_status": "Listed",
                "source_url": "https://example.com/tp-ranked",
                "retrieved_at": "2026-03-26T00:00:00+00:00",
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
                "spv_name_normalized": "torrey pines re ltd",
                "source_filing_url": "https://sec.gov/example-ranked",
                "source_term": "catastrophe bond",
            },
            {
                "sponsor_name": "Other Sponsor",
                "spv_name": "Torrey Re Holdings",
                "spv_name_normalized": "torrey re holdings",
                "source_filing_url": "https://sec.gov/example-other",
                "source_term": "reinsurance",
            },
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sec_match_method"] == "ranked_auto"
    assert tranche["sec_sponsor_name"] == "Palomar Holdings, Inc."
    assert tranche["sponsor_name"] == "Palomar Holdings, Inc."
    assert tranche["sponsor_attribution_state"] == "sec_ranked_spv"
    assert tranche["sec_top_candidate_name"] == "Torrey Pines Re Ltd"
    assert tranche["sec_top_candidate_score"] >= 0.85


def test_build_registry_marks_ambiguous_exact_sec_spv_links_for_manual_review(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Phoenix 2 Re Pte Ltd Series 2022-1 Class A Participating Notes due January 4, 2028",
                "issuer_name": "Phoenix 2 Re Pte Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/phoenix-2",
                "retrieved_at": "2026-03-26T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    write_jsonl(
        settings.processed_dir / "sec" / "sponsor_spv_links.jsonl",
        [
            {
                "sponsor_name": "Sponsor A",
                "spv_name": "Phoenix 2 Re Pte Ltd",
                "spv_name_normalized": "phoenix 2 re pte",
                "source_filing_url": "https://sec.gov/example-a",
                "source_term": "catastrophe bond",
            },
            {
                "sponsor_name": "Sponsor B",
                "spv_name": "Phoenix 2 Re Pte Ltd",
                "spv_name_normalized": "phoenix 2 re pte",
                "source_filing_url": "https://sec.gov/example-b",
                "source_term": "catastrophe bond",
            },
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sec_match_method"] == "manual_review"
    assert tranche["sec_sponsor_name"] is None
    assert tranche["sponsor_name"] is None
    assert tranche["sec_candidate_count"] == 2
    assert tranche["sponsor_attribution_state"] == "missing"


def test_build_registry_defaults_linkage_methods_to_missing_without_optional_artifacts(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Mangrove Risk Solutions Bermuda Ltd. Series 2025-A Disc Zero Coupon Par Notes due May 15, 2026",
                "issuer_name": "Mangrove Risk Solutions Bermuda Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/mangrove",
                "retrieved_at": "2026-03-26T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["bma_match_method"] == "missing"
    assert tranche["bma_match_count"] == 0
    assert tranche["bma_candidate_count"] == 0
    assert tranche["sec_match_method"] == "missing"
    assert tranche["sec_candidate_count"] == 0


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
    assert tranche["sponsor_attribution_state"] == "alias_family"
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
        writer.writerow(["tranche_name", "field_name", "override_value", "source_url", "notes"])
        writer.writerow(
            [
                title,
                "region_codes",
                '["florida"]',
                "https://example.com/meadows-class-a",
                "class-specific geography",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "OIS Series 2 LLC"
    assert tranche["sponsor_source"] == "alias"
    assert tranche["sponsor_source_url"] == "https://example.com/meadows-source"
    assert tranche["peril_codes"] == ["us_wind"]
    assert tranche["peril_inference_method"] == "sponsor_alias"
    assert tranche["region_codes"] == ["florida"]
    assert tranche["region_inference_method"] == "manual_override"
    assert tranche["region_source_url"] == "https://example.com/meadows-class-a"
    assert tranche["region_source_note"] == "class-specific geography"


def test_build_registry_sponsor_alias_overrides_issuer_hints_when_source_is_stronger(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "PoleStar Re Ltd. Series 2026-1 Class A Principal At-Risk Variable Rate Notes due January 8, 2029",
                "issuer_name": "PoleStar Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/polestar",
                "retrieved_at": "2026-03-25T00:00:00+00:00",
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
                "PoleStar Re Ltd",
                "Beazley",
                "https://example.com/polestar-source",
                "",
                '["cyber"]',
                "family alias is more specific than issuer heuristic",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "Beazley"
    assert tranche["peril_codes"] == ["cyber"]
    assert tranche["peril_inference_method"] == "sponsor_alias"
    assert tranche["peril_source_url"] == "https://example.com/polestar-source"
    assert tranche["region_codes"] == []
    assert tranche["region_inference_method"] == "missing"


def test_build_registry_sponsor_alias_can_replace_heuristic_region_and_peril(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Veraison Re Ltd Series 2026-1 Class A Principal At-Risk Variable Rate Notes due January 8, 2031",
                "issuer_name": "Veraison Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/veraison",
                "retrieved_at": "2026-03-25T00:00:00+00:00",
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
                "Veraison Re Ltd",
                "GeoVera Insurance Holdings, Ltd.",
                "https://example.com/veraison-source",
                '["us"]',
                '["earthquake"]',
                "family alias replaces heuristic US wind / California earthquake defaults",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "GeoVera Insurance Holdings, Ltd."
    assert tranche["peril_codes"] == ["earthquake"]
    assert tranche["peril_inference_method"] == "sponsor_alias"
    assert tranche["region_codes"] == ["us"]
    assert tranche["region_inference_method"] == "sponsor_alias"
    assert tranche["region_source_url"] == "https://example.com/veraison-source"


def test_build_registry_manual_sponsor_override_preserves_provenance(tmp_path: Path):
    settings = _settings(tmp_path)
    title = "Example Re Ltd Series 2026-1 Class A"
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": title,
                "issuer_name": "Example Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/example-re",
                "retrieved_at": "2026-03-25T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )
    settings.manual_dir.mkdir(parents=True, exist_ok=True)
    with (settings.manual_dir / "tranche_overrides.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tranche_name", "field_name", "override_value", "source_url", "notes"])
        writer.writerow(
            [
                title,
                "sponsor_name",
                "Example Sponsor",
                "https://example.com/sponsor-evidence",
                "manual sponsor fix",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == "Example Sponsor"
    assert tranche["sponsor_source"] == "manual_override"
    assert tranche["sponsor_attribution_state"] == "manual_override"
    assert tranche["sponsor_source_url"] == "https://example.com/sponsor-evidence"
    assert tranche["sponsor_source_note"] == "manual sponsor fix"


def test_build_registry_blank_sponsor_override_can_clear_family_alias(tmp_path: Path):
    settings = _settings(tmp_path)
    title = "Kaith Re Ltd Li Re 2025-1 Bond due July 15, 2026"
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": title,
                "issuer_name": "Kaith Re Ltd Li Re 2025-1",
                "listing_status": "Listed",
                "source_url": "https://example.com/kaith-li-re",
                "retrieved_at": "2026-03-27T00:00:00+00:00",
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
                "Kaith Re Ltd Li Re",
                "Hannover Re",
                "https://example.com/li-re-topic",
                "",
                "",
                "platform alias that should not survive exact tranche evidence",
            ]
        )
    with (settings.manual_dir / "tranche_overrides.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tranche_name", "field_name", "override_value", "source_url", "notes"])
        writer.writerow(
            [
                title,
                "sponsor_name",
                "",
                "https://example.com/li-re-2025-1",
                "Exact tranche evidence says the sponsor is unknown.",
            ]
        )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["sponsor_name"] == ""
    assert tranche["sponsor_source"] == "manual_override"
    assert tranche["sponsor_attribution_state"] == "manual_override"
    assert tranche["sponsor_source_url"] == "https://example.com/li-re-2025-1"
    assert tranche["attribution_status"]["sponsor"] == "missing"


def test_build_registry_uses_settings_as_of_date_for_status(tmp_path: Path):
    settings = Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path,
        as_of_date=date(2027, 1, 15),
    )
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Atlas Re Ltd Series 2025-1 Class A",
                "issuer_name": "Atlas Re Ltd",
                "listing_status": "Listed",
                "maturity_date": "2027-01-01",
                "source_url": "https://example.com/atlas",
                "retrieved_at": "2026-03-18T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]

    assert tranche["status"] == "matured"


def test_build_registry_manual_overrides_can_roll_back_false_precision_hints(tmp_path: Path):
    settings = _settings(tmp_path)
    sakura_title = "Sakura Re Ltd Series 2025-1 Class A PAR VR Notes due April 5, 2029"
    eclipse_title = "Eclipse Re Ltd Series 2025-1A Notes - SAC EC0071 - due March 31, 2026"
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": sakura_title,
                "issuer_name": "Sakura Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/sakura",
                "retrieved_at": "2026-03-27T00:00:00+00:00",
                "extraction_method": "test",
            },
            {
                "title": eclipse_title,
                "issuer_name": "Eclipse Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/eclipse",
                "retrieved_at": "2026-03-27T00:00:00+00:00",
                "extraction_method": "test",
            },
        ],
    )
    settings.manual_dir.mkdir(parents=True, exist_ok=True)
    with (settings.manual_dir / "tranche_overrides.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tranche_name", "field_name", "override_value", "source_url", "notes"])
        writer.writerow(
            [
                sakura_title,
                "sponsor_name",
                "Sompo Japan Insurance and affiliates",
                "https://example.com/sakura-source",
                "Exact tranche evidence for sponsor.",
            ]
        )
        writer.writerow(
            [
                sakura_title,
                "region_codes",
                '["japan"]',
                "https://example.com/sakura-source",
                "Exact tranche evidence for region.",
            ]
        )
        writer.writerow(
            [
                sakura_title,
                "peril_codes",
                '["japan_typhoon","flood"]',
                "https://example.com/sakura-source",
                "Exact tranche evidence for peril.",
            ]
        )
        writer.writerow(
            [
                eclipse_title,
                "region_codes",
                "[]",
                "https://example.com/eclipse-source",
                "Unknown geography should stay blank.",
            ]
        )
        writer.writerow(
            [
                eclipse_title,
                "peril_codes",
                '["other_property_cat"]',
                "https://example.com/eclipse-source",
                "Unknown property-cat should not retain precise issuer hints.",
            ]
        )

    build_registry(settings)
    rows = {
        row["tranche_name"]: row
        for row in read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    }
    sakura = rows[sakura_title]
    eclipse = rows[eclipse_title]

    assert sakura["sponsor_name"] == "Sompo Japan Insurance and affiliates"
    assert sakura["sponsor_source"] == "manual_override"
    assert sakura["peril_codes"] == ["japan_typhoon", "flood"]
    assert sakura["region_codes"] == ["japan"]
    assert sakura["peril_source_type"] == "manual_override"
    assert sakura["region_source_type"] == "manual_override"

    assert eclipse["peril_codes"] == ["other_property_cat"]
    assert eclipse["region_codes"] == []
    assert eclipse["peril_source_type"] == "manual_override"
    assert eclipse["region_source_type"] == "manual_override"


def test_build_registry_manual_overrides_pin_ramble_stabilitas_and_seaside_rows(tmp_path: Path):
    settings = _settings(tmp_path)
    ramble_title = "Ramble Re Ltd Series 2024-1 Class A Principal At-Risk Variable Rate Notes due March 5, 2027"
    stabilitas_title = "Stabilitas Re Ltd. Series 2023-1- Class A Principal At-Risk Variable Rate Notes due June 5, 2026"
    seaside_title = "Seaside Re 2025-1 Bond Due 15 April 2026"
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": ramble_title,
                "issuer_name": "Ramble Re Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/ramble",
                "retrieved_at": "2026-03-27T00:00:00+00:00",
                "extraction_method": "test",
            },
            {
                "title": stabilitas_title,
                "issuer_name": "Stabilitas Re Ltd.",
                "listing_status": "Listed",
                "source_url": "https://example.com/stabilitas",
                "retrieved_at": "2026-03-27T00:00:00+00:00",
                "extraction_method": "test",
            },
            {
                "title": seaside_title,
                "issuer_name": "Seaside Re",
                "listing_status": "Listed",
                "source_url": "https://example.com/seaside",
                "retrieved_at": "2026-03-27T00:00:00+00:00",
                "extraction_method": "test",
            },
        ],
    )
    settings.manual_dir.mkdir(parents=True, exist_ok=True)
    with (settings.manual_dir / "tranche_overrides.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tranche_name", "field_name", "override_value", "source_url", "notes"])
        writer.writerows(
            [
                [
                    ramble_title,
                    "sponsor_name",
                    "Arch Capital Group Ltd.",
                    "https://example.com/ramble-source",
                    "Exact tranche evidence for sponsor.",
                ],
                [
                    ramble_title,
                    "region_codes",
                    '["us"]',
                    "https://example.com/ramble-source",
                    "Exact tranche evidence for region.",
                ],
                [
                    ramble_title,
                    "peril_codes",
                    '["us_wind","earthquake"]',
                    "https://example.com/ramble-source",
                    "Exact tranche evidence for peril.",
                ],
                [
                    stabilitas_title,
                    "sponsor_name",
                    "Conduit Re",
                    "https://example.com/stabilitas-source",
                    "Exact tranche evidence for sponsor.",
                ],
                [
                    stabilitas_title,
                    "region_codes",
                    '["us"]',
                    "https://example.com/stabilitas-source",
                    "Exact tranche evidence for region.",
                ],
                [
                    stabilitas_title,
                    "peril_codes",
                    '["us_wind","earthquake"]',
                    "https://example.com/stabilitas-source",
                    "Exact tranche evidence for peril.",
                ],
                [
                    seaside_title,
                    "region_codes",
                    '["us"]',
                    "https://example.com/seaside-source",
                    "US property-cat geography should stay coarse.",
                ],
                [
                    seaside_title,
                    "peril_codes",
                    '["other_property_cat"]',
                    "https://example.com/seaside-source",
                    "Unknown property-cat should not retain precise issuer hints.",
                ],
            ]
        )

    build_registry(settings)
    rows = {
        row["tranche_name"]: row
        for row in read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    }
    ramble = rows[ramble_title]
    stabilitas = rows[stabilitas_title]
    seaside = rows[seaside_title]

    assert ramble["sponsor_name"] == "Arch Capital Group Ltd."
    assert ramble["sponsor_source"] == "manual_override"
    assert ramble["region_codes"] == ["us"]
    assert ramble["peril_codes"] == ["us_wind", "earthquake"]
    assert ramble["region_source_type"] == "manual_override"
    assert ramble["peril_source_type"] == "manual_override"

    assert stabilitas["sponsor_name"] == "Conduit Re"
    assert stabilitas["sponsor_source"] == "manual_override"
    assert stabilitas["region_codes"] == ["us"]
    assert stabilitas["peril_codes"] == ["us_wind", "earthquake"]
    assert stabilitas["region_source_type"] == "manual_override"
    assert stabilitas["peril_source_type"] == "manual_override"

    assert seaside["sponsor_name"] is None
    assert seaside["region_codes"] == ["us"]
    assert seaside["peril_codes"] == ["other_property_cat"]
    assert seaside["region_source_type"] == "manual_override"
    assert seaside["peril_source_type"] == "manual_override"


def test_build_registry_marks_program_titles_with_trailing_punctuation_as_programmes(tmp_path: Path):
    settings = _settings(tmp_path)
    write_jsonl(
        settings.processed_dir / "bsx" / "company_records.jsonl",
        [
            {
                "title": "Aquila Re I Ltd - Principal At-Risk Variable Rate Note Program.",
                "issuer_name": "Aquila Re I Ltd",
                "listing_status": "Listed",
                "source_url": "https://example.com/aquila-program",
                "retrieved_at": "2026-03-26T00:00:00+00:00",
                "extraction_method": "test",
            }
        ],
    )

    build_registry(settings)
    tranche = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")[0]
    assert tranche["record_type"] == "programme"
    assert tranche["is_programme_shell"] is True
