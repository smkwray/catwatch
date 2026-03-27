from pathlib import Path

import polars as pl

from opencatwatch.config import Settings
from opencatwatch.sources import bma, bsx, ibtracs, nws, openfema, sec
from opencatwatch.utils import read_jsonl


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_agent="OpenCatWatch test",
        timeout_seconds=5,
        polite_delay_seconds=0.0,
        sec_max_rps=1,
        data_dir=tmp_path / "data",
    )


def test_fetch_ibtracs_uses_lowercase_filename(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)
    captured: dict[str, object] = {}

    def fake_download_file(session, url, dest, settings):
        captured["url"] = url
        captured["dest"] = dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("ok", encoding="utf-8")
        return dest

    monkeypatch.setattr(ibtracs, "build_session", lambda settings: object())
    monkeypatch.setattr(ibtracs, "download_file", fake_download_file)

    path = ibtracs.fetch_ibtracs_csv(settings, kind="active")

    assert path.name == "ibtracs.ACTIVE.list.v04r01.csv"
    assert captured["url"].endswith("ibtracs.ACTIVE.list.v04r01.csv")
    assert captured["dest"] == settings.raw_dir / "ibtracs" / "ibtracs.ACTIVE.list.v04r01.csv"


def test_fetch_nws_alerts_preserves_area_desc_and_ugc_codes(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)

    monkeypatch.setattr(nws, "build_session", lambda settings: object())
    monkeypatch.setattr(
        nws,
        "request_json",
        lambda session, url, settings: {
            "features": [
                {
                    "properties": {
                        "id": "nws-1",
                        "event": "Flood Warning",
                        "headline": "Flooding possible in North Carolina and South Carolina",
                        "areaDesc": "Central and Eastern North Carolina; South Carolina",
                        "geocode": {"UGC": ["NCC001", "SCC003"]},
                        "onset": "2026-06-01T00:00:00+00:00",
                        "expires": "2026-06-02T00:00:00+00:00",
                        "@id": "https://example.com/nws-1",
                    },
                    "geometry": None,
                }
            ]
        },
    )

    rows = nws.fetch_nws_alerts(settings)

    assert rows[0]["area_desc"] == "Central and Eastern North Carolina; South Carolina"
    assert rows[0]["region_codes"] == ["NCC001", "SCC003"]
    assert rows[0]["source_event_id"] == "nws-1"


def test_fetch_fema_paginates_and_writes_parquet(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)
    pages = {
        0: [
            {
                "disasterNumber": 1,
                "state": "FL",
                "incidentType": "Hurricane",
                "declarationTitle": "HURRICANE ONE",
                "incidentBeginDate": "2026-01-01T00:00:00.000Z",
            },
            {
                "disasterNumber": 2,
                "state": "CA",
                "incidentType": "Fire",
                "declarationTitle": "FIRE TWO",
                "incidentBeginDate": "2026-01-02T00:00:00.000Z",
            },
        ],
        2: [
            {
                "disasterNumber": 3,
                "state": "TX",
                "incidentType": "Flood",
                "declarationTitle": "FLOOD THREE",
                "incidentBeginDate": "2026-01-03T00:00:00.000Z",
            }
        ],
    }
    calls: list[tuple[int, int]] = []

    def fake_request_json(session, url, settings, params=None):
        skip = int((params or {}).get("$skip", 0))
        top = int((params or {}).get("$top", 0))
        calls.append((skip, top))
        rows = pages.get(skip, [])
        return {
            "metadata": {"count": 3},
            "DisasterDeclarationsSummaries": rows,
        }

    monkeypatch.setattr(openfema, "build_session", lambda settings: object())
    monkeypatch.setattr(openfema, "request_json", fake_request_json)
    monkeypatch.setattr(openfema, "OPENFEMA_PAGE_SIZE", 2)

    path = openfema.fetch_fema_disaster_declarations(settings)

    assert path == settings.raw_dir / "openfema" / "DisasterDeclarationsSummaries.parquet"
    assert calls == [(0, 2), (2, 2)]
    df = pl.read_parquet(path)
    assert df.height == 3
    assert df.get_column("disasterNumber").to_list() == [1, 2, 3]
    assert (settings.raw_dir / "openfema" / "pages" / "DisasterDeclarationsSummaries_000000.json").exists()
    assert (settings.raw_dir / "openfema" / "pages" / "DisasterDeclarationsSummaries_000002.json").exists()


def test_select_filings_for_term_scan_prefers_relevant_forms():
    filings = [
        {"form": "4", "primary_doc": "ownership.xml", "filing_date": "2026-02-26", "accession_number": "4-1"},
        {"form": "S-8", "primary_doc": "registration.htm", "filing_date": "2026-02-25", "accession_number": "s8-1"},
        {"form": "10-K", "primary_doc": "annual.htm", "filing_date": "2026-02-24", "accession_number": "10k-1"},
        {"form": "8-K", "primary_doc": "current.htm", "filing_date": "2026-02-23", "accession_number": "8k-1"},
        {"form": "10-Q", "primary_doc": "quarterly.htm", "filing_date": "2025-11-08", "accession_number": "10q-1"},
    ]

    selected = sec.select_filings_for_term_scan(filings, max_docs=3)

    assert [row["form"] for row in selected] == ["10-K", "10-Q", "8-K"]


def test_extract_sponsor_spv_links_supports_broader_issuer_name_forms():
    term_hits = [
        {
            "sponsor_name": "Example Sponsor",
            "filing_url": "https://sec.gov/example-1",
            "term": "catastrophe bond",
            "snippet": "The company utilized collateralized protection through Orange Capital Re DAC for the transaction.",
        },
        {
            "sponsor_name": "Example Sponsor",
            "filing_url": "https://sec.gov/example-2",
            "term": "special purpose insurer",
            "snippet": "Swiss Re used the existing Matterhorn Re Ltd. special purpose insurer vehicle for the issuance.",
        },
        {
            "sponsor_name": "Example Sponsor",
            "filing_url": "https://sec.gov/example-3",
            "term": "catastrophe bond",
            "snippet": "The notes were issued by Phoenix 2 Re Pte. Ltd. in connection with the catastrophe bond transaction.",
        },
        {
            "sponsor_name": "Example Sponsor",
            "filing_url": "https://sec.gov/example-4",
            "term": "special purpose insurer",
            "snippet": "The special purpose insurer Mangrove Risk Solutions Bermuda Ltd. provided the coverage.",
        },
    ]

    links = sec.extract_sponsor_spv_links(term_hits)

    assert [row["spv_name"] for row in links] == [
        "Orange Capital Re DAC",
        "Matterhorn Re Ltd",
        "Phoenix 2 Re Pte. Ltd",
        "Mangrove Risk Solutions Bermuda Ltd",
    ]


def test_load_scan_terms_appends_targeted_family_terms(tmp_path: Path):
    extra_terms = tmp_path / "families.txt"
    extra_terms.write_text("Mangrove Risk Solutions Bermuda Ltd\ncat bond\n", encoding="utf-8")

    terms = sec.load_scan_terms(extra_terms_file=extra_terms)

    assert "Mangrove Risk Solutions Bermuda Ltd" in terms
    assert terms.count("cat bond") == 1


def test_fetch_sec_writes_scan_manifest_for_targeted_terms(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)
    sponsors_csv = tmp_path / "sponsors.csv"
    sponsors_csv.write_text("sponsor_name,cik\nExample Sponsor,1234567890\n", encoding="utf-8")
    unresolved_terms = tmp_path / "families.txt"
    unresolved_terms.write_text("Mangrove Risk Solutions Bermuda Ltd\n", encoding="utf-8")

    monkeypatch.setattr(sec, "build_session", lambda settings: object())
    monkeypatch.setattr(
        sec,
        "fetch_submissions_json",
        lambda settings, cik: {
            "cik": cik,
            "name": "Example Sponsor",
            "filings": {
                "recent": {
                    "accessionNumber": ["0001-01-01"],
                    "primaryDocument": ["annual.htm"],
                    "form": ["10-K"],
                    "filingDate": ["2026-02-01"],
                }
            },
        },
    )
    monkeypatch.setattr(sec, "request_text", lambda session, url, settings: "<html><body>No hits</body></html>")

    result = sec.fetch_sec_for_sponsors(
        settings=settings,
        sponsors_csv=sponsors_csv,
        download_docs=True,
        max_docs_per_sponsor=1,
        unresolved_terms_file=unresolved_terms,
    )

    manifest = sec.json.loads((settings.processed_dir / "sec" / "scan_manifest.json").read_text(encoding="utf-8"))
    assert result["docs_scanned"] == 1
    assert manifest["targeted_terms_file"] == str(unresolved_terms)
    assert "Mangrove Risk Solutions Bermuda Ltd" in manifest["terms"]


def test_fetch_bma_writes_ranked_review_candidates_and_manifest(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)
    directory_html = """
    <html><body>
      <div id="SearchentityData">
        <table>
          <tr><th>Company Name</th><th>Sector</th><th>Address</th><th>Contact</th><th>Details</th></tr>
          <tr>
            <td>Artex Axcell Re (Bermuda) Limited</td>
            <td>Insurance</td>
            <td></td>
            <td></td>
            <td><strong>License/Registration Type:</strong> Restricted Special Purpose Insurer</td>
          </tr>
          <tr>
            <td>Artex Axcell Holdings Limited</td>
            <td>Insurance</td>
            <td></td>
            <td></td>
            <td><strong>License/Registration Type:</strong> Class 3A</td>
          </tr>
        </table>
      </div>
    </body></html>
    """

    monkeypatch.setattr(bma, "build_session", lambda settings: object())
    monkeypatch.setattr(bma, "request_text", lambda session, url, settings: directory_html)

    result = bma.fetch_bma_for_names(settings=settings, names=["Artex Axcell Re (Bermuda) Ltd"])

    review_candidates = read_jsonl(settings.processed_dir / "bma" / "entity_review_candidates.jsonl")
    manifest = sec.json.loads((settings.processed_dir / "bma" / "manifest.json").read_text(encoding="utf-8"))

    assert result["matches"] == 1
    assert result["review_candidates"] >= 1
    assert review_candidates[0]["matched_name"] == "Artex Axcell Re (Bermuda) Limited"
    assert manifest["review_candidates"] == result["review_candidates"]


def test_rebuild_bsx_from_raw_reparses_saved_detail_pages(tmp_path: Path):
    settings = _settings(tmp_path)
    detail_html = """
    <html>
      <body>
        <h1>Foundation Re IV Limited -Series 2023-1 – Class A Principal At-Risk VRN due January 8,2027</h1>
        <div>Listing Type:</div><div>Insurance Linked Security</div>
        <div>Listing Status:</div><div>Listed</div>
        <div>Listed on BSX:</div><div>2023-01-09</div>
        <div>Currency:</div><div>USD</div>
        <div>CFI code:</div><div>DBFNBR</div>
      </body>
    </html>
    """
    raw_detail = settings.raw_dir / "bsx" / "detail_1.html"
    raw_detail.parent.mkdir(parents=True, exist_ok=True)
    raw_detail.write_text(detail_html, encoding="utf-8")
    existing_processed = settings.processed_dir / "bsx" / "company_records.jsonl"
    existing_processed.parent.mkdir(parents=True, exist_ok=True)
    existing_processed.write_text(
        '{"source_url":"https://www.bsx.com/company_details.php?CompanyID=123"}\n',
        encoding="utf-8",
    )

    rows = bsx.rebuild_bsx_from_raw(settings)

    assert rows[0]["source_url"] == "https://www.bsx.com/company_details.php?CompanyID=123"
    assert rows[0]["maturity_date"] == "2027-01-08"
