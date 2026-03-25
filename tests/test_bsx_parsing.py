from pathlib import Path

from opencatwatch.sources.bsx import (
    _clean_issuer_name,
    _extract_maturity_date,
    parse_company_page,
    parse_listing_links,
    parse_pagination_links,
)
from opencatwatch.utils import extract_region_codes, parse_date_maybe


def test_clean_issuer_name_strips_dollar_amounts():
    assert _clean_issuer_name("Aquila Re I Ltd. US$100,000,000") == "Aquila Re I Ltd"
    assert _clean_issuer_name("Aquila Re I Ltd. US$125,000,000") == "Aquila Re I Ltd"


def test_clean_issuer_name_strips_programme_descriptors():
    assert _clean_issuer_name("Artex Axcell Re (Bermuda) Limited ILS Note") == "Artex Axcell Re (Bermuda) Limited"
    assert _clean_issuer_name("Artex Axcell Re (Bermuda) Ltd ILS Note") == "Artex Axcell Re (Bermuda) Ltd"
    assert _clean_issuer_name("Artex Axcell Re (Bermuda) Limited ILS") == "Artex Axcell Re (Bermuda) Limited"
    assert _clean_issuer_name("Artex Axcell Re (Bermuda) Limited ILSNP II") == "Artex Axcell Re (Bermuda) Limited"
    assert _clean_issuer_name("Eclipse Re Ltd Note") == "Eclipse Re Ltd"
    assert _clean_issuer_name("Alturas Re Ltd. Participating Notes") == "Alturas Re Ltd"
    assert _clean_issuer_name("Alturas Re Ltd. Participating Notes Program") == "Alturas Re Ltd"
    assert _clean_issuer_name("Eclipse Re Ltd Note Program") == "Eclipse Re Ltd"
    assert _clean_issuer_name("Astro Re Pte Ltd Principle") == "Astro Re Pte Ltd"
    assert _clean_issuer_name("Bonanza Re Ltd") == "Bonanza Re Ltd"
    # Parentheticals, offering types, series/class suffixes
    assert _clean_issuer_name('Sabine Re Ltd. (the "Issuer")') == "Sabine Re Ltd"
    assert _clean_issuer_name("MetroCat Re Ltd., is") == "MetroCat Re Ltd"
    assert _clean_issuer_name("Torrey Pines Re Ltd. -Series 2024-1 -Class B") == "Torrey Pines Re Ltd"
    assert _clean_issuer_name("Oaktown Re VII Ltd 144A") == "Oaktown Re VII Ltd"
    assert _clean_issuer_name("MASCHPARK RE LTD. PAR VR") == "MASCHPARK RE LTD"
    assert _clean_issuer_name("Seaside Re 2025-1 Bond Due 15 April 2026") == "Seaside Re 2025-1"


def test_parse_company_page_extracts_labeled_fields():
    html = Path("tests/fixtures/bsx_company_details_sample.html").read_text(encoding="utf-8")
    row = parse_company_page(
        html,
        source_url="https://www.bsx.com/company_details.php?CompanyID=12345",
    )
    assert row["company_id"] == "12345"
    assert row["title"] == "Example Re Series 2026-1 Class A"
    assert row["listing_type"] == "Insurance Linked Security"
    assert row["listing_status"] == "Listed"
    assert row["listed_date"] == "2025-07-15"
    assert row["available_to"] == "Qualified Investors only"
    assert row["currency"] == "USD"
    assert row["cfi_code"] == "DBFNBR"
    assert row["security_kind"] == "ils_security"
    assert row["issuer_name"] == "Example Re"
    assert row["sponsor_name"] == "Example Sponsor"


def test_parse_company_page_handles_live_style_bsX_markup():
    html = Path("tests/fixtures/bsx_company_details_live_style.html").read_text(encoding="utf-8")
    row = parse_company_page(
        html,
        source_url="https://www.bsx.com/company_details.php?CompanyID=1099940992",
    )
    assert row["company_id"] == "1099940992"
    assert row["listing_type"] == "Insurance Linked Security (ILS)"
    assert row["listed_date"] == "2025-10-31"
    assert row["currency"] == "USD"
    assert row["issue_amount"] == "240000000"
    assert row["maturity_date"] == "2028-11-07"
    assert row["issuer_name"] == "Acorn Re Ltd"
    assert row["security_kind"] == "ils_security"


def test_parse_listing_links_deduplicates_relative_and_absolute_urls():
    html = """
    <html><body>
      <a href="company_details.php?CompanyID=1">One</a>
      <a href="/company_details.php?CompanyID=1">Duplicate One</a>
      <a href="https://www.bsx.com/company_details.php?CompanyID=2">Two</a>
      <a href="other.php?id=3">Ignore</a>
    </body></html>
    """
    links = parse_listing_links(html, "https://www.bsx.com/comp_insurance_linked_securities.php")
    assert links == [
        "https://www.bsx.com/company_details.php?CompanyID=1",
        "https://www.bsx.com/company_details.php?CompanyID=2",
    ]


def test_parse_pagination_links_reads_current_page_navigation():
    html = """
    <html><body>
      <a href="comp_insurance_linked_securities.php?Process=7&CompanyName=&CurrentPage=2">&gt;&gt;</a>
      <a href="/comp_insurance_linked_securities.php?Process=7&CompanyName=&CurrentPage=3">3</a>
      <a href="company_details.php?CompanyID=1">Detail</a>
    </body></html>
    """
    links = parse_pagination_links(html, "https://www.bsx.com/comp_insurance_linked_securities.php")
    assert links == [
        "https://www.bsx.com/comp_insurance_linked_securities.php?Process=7&CompanyName=&CurrentPage=2",
        "https://www.bsx.com/comp_insurance_linked_securities.php?Process=7&CompanyName=&CurrentPage=3",
    ]


def test_parse_date_maybe_handles_month_day_year_without_comma():
    assert parse_date_maybe("Jan 10 2028") == "2028-01-10"
    assert parse_date_maybe("February 4 2028") == "2028-02-04"


def test_parse_date_maybe_handles_day_month_with_comma_and_missing_space():
    assert parse_date_maybe("22 April, 2029") == "2029-04-22"
    assert parse_date_maybe("January 8,2027") == "2027-01-08"


def test_extract_region_codes_supports_chile():
    assert extract_region_codes("Protection for earthquake risks in Chile") == ["chile"]


def test_extract_maturity_date_handles_due_without_comma():
    title = "Maschpark Re Ltd. PAR VR Note $100,000,000 Series 2024-1 Class A Notes Due Jan 10 2028"
    assert _extract_maturity_date(title) == "2028-01-10"


def test_extract_maturity_date_handles_trailing_date_without_due():
    title = "Radnor Re 2021-1 Ltd Mortgage Insurance-Linked Notes December 27, 2033"
    assert _extract_maturity_date(title) == "2033-12-27"
