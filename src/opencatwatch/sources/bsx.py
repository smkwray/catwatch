from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import Settings
from ..http import build_session, request_text
from ..utils import (
    extract_labeled_field,
    normalize_name,
    parse_date_maybe,
    read_jsonl,
    utcnow_iso,
    write_json,
    write_records_bundle,
)

BSX_ILS_URLS = [
    "https://www.bsx.com/comp_insurance_linked_securities.php/media/pdf/comp_international_companies.php",
    "https://www.bsx.com/comp_insurance_linked_securities.php/media/media/comp_insurance_linked_securities.php?CompanyName=&CurrentPage=1&Process=7",
    "https://www.bsx.com/comp_insurance_linked_securities.php",
    "https://www.bsx.com/comp_securities/insurance_linked_securities.php",
]


def infer_security_kind(title: str, listing_type: str | None = None) -> str:
    if listing_type and "insurance linked" in listing_type.lower():
        return "ils_security"

    lower = title.lower()
    if any(marker in lower for marker in ("cat bond", "series", "class", "program", "programme")):
        return "ils_security"
    return "listed_security"


def parse_listing_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "company_details.php?companyid=" in href.lower():
            links.append(urljoin(base_url, href))
    return sorted(set(links))


def parse_pagination_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        lower = href.lower()
        if "comp_insurance_linked_securities.php" not in lower and "insurance_linked_securities.php" not in lower:
            continue
        if "currentpage=" not in lower and "page=" not in lower:
            continue
        links.append(urljoin(base_url, href))
    return sorted(set(links))


def _extract_field(lines: list[str], *labels: str) -> str | None:
    for label in labels:
        value = extract_labeled_field(lines, label)
        if value:
            return value
    return None


def _infer_issuer_name(title: str) -> str:
    issuer_guess = re.split(
        r"\s+-\s+series\b|\s+-\s+princip(?:al|le)\b|\s+series\b|\s+class\b|\s+princip(?:al|le)\b|\s+program(?:me)?\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return issuer_guess.strip(" ,.-")


def _clean_issuer_name(raw: str) -> str:
    """Strip currency/amount suffixes and programme descriptors from an issuer name."""
    # Remove trailing currency amounts like "US$100,000,000"  or "$100,000,000"
    cleaned = re.sub(r"\s+\$[\d,]+(?:\.\d+)?", "", raw)
    cleaned = re.sub(r"\s+(?:US\$|USD|EUR|GBP|£|€)\s*[\d,]+(?:\.\d+)?", "", cleaned)
    # Remove parenthetical descriptions: (the "Issuer"), ("Issuer")
    cleaned = re.sub(r'\s*\(\s*(?:the\s+)?"[^"]*"\s*\)', "", cleaned)
    # Remove trailing ", is" fragments
    cleaned = re.sub(r",\s+is\s*$", "", cleaned)
    # Remove series/class suffixes: "-Series 2024-1 -Class B"
    cleaned = re.sub(r"\s*-\s*Series\b.*$", "", cleaned, flags=re.IGNORECASE)
    # Remove offering type suffixes: 144A, RegS, Reg S
    cleaned = re.sub(r"\s+(?:144A|Reg\s*S)\s*$", "", cleaned, flags=re.IGNORECASE)
    # Remove "PAR VR" / "PAR Variable Rate" and trailing descriptors
    cleaned = re.sub(r"\s+PAR\s+(?:VR|Variable\s+Rate)\b.*$", "", cleaned, flags=re.IGNORECASE)
    # Remove "Bond Due ..." maturity info
    cleaned = re.sub(r"\s+Bond\s+(?:Due|due)\b.*$", "", cleaned, flags=re.IGNORECASE)
    # Remove trailing programme descriptors (ILS Note, ILSNP, Note Program, Participating Notes, etc.)
    cleaned = re.sub(
        r"\s+(?:ILS(?:\s+Note)?(?:s|P)?(?:\s+\S+)*|ILSNP(?:\s+\S+)*|Participating\s+Notes?\s*(?:Program(?:me)?)?|Note(?:s)?(?:\s+Program(?:me)?)?)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Remove trailing "Principle" / "Principal" and anything after (BSX typo)
    cleaned = re.sub(r"\s+Princip(?:le|al)\b.*$", "", cleaned, flags=re.IGNORECASE)
    # Remove trailing "Bond" by itself
    cleaned = re.sub(r"\s+Bond\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ,.-–")


def _extract_issuer_name(lines: list[str], title: str) -> str:
    issuer_guess = _infer_issuer_name(title)
    issuer_norm = normalize_name(issuer_guess)
    try:
        start = lines.index("CFI code:")
        search_lines = lines[start + 2 :]
    except ValueError:
        search_lines = lines

    best_candidate: str | None = None
    for line in search_lines:
        if line.upper() == "LISTING SPONSOR":
            break
        cleaned = line.strip(" ,.;:-")
        if not cleaned or cleaned == title:
            continue
        if any(marker in cleaned.lower() for marker in (" is ", " incorporated", "registered office", "principal office")):
            continue
        if len(cleaned.split()) > 8:
            continue
        candidate_norm = normalize_name(cleaned)
        if not candidate_norm:
            continue
        if candidate_norm == issuer_norm:
            return _clean_issuer_name(cleaned)
        if issuer_norm in candidate_norm:
            # Page line is more specific — use it
            return _clean_issuer_name(cleaned)
        if candidate_norm in issuer_norm and not best_candidate:
            # Page line is a fragment; keep looking but remember it as fallback
            best_candidate = cleaned
    if best_candidate:
        # Fragment matched but title-inferred guess is longer — prefer the guess
        return _clean_issuer_name(issuer_guess)
    return _clean_issuer_name(issuer_guess)


def _extract_maturity_date(title: str) -> str | None:
    match = re.search(r"\bdue\s+(.+)$", title, flags=re.IGNORECASE)
    if match:
        parsed = parse_date_maybe(match.group(1).strip())
        if parsed:
            return parsed

    trailing_date = re.search(
        r"((?:\d{1,2}\s+[A-Za-z]{3,9},?\s*\d{4})|(?:[A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4}))\s*$",
        title,
        flags=re.IGNORECASE,
    )
    if trailing_date:
        return parse_date_maybe(trailing_date.group(1).strip())
    return None


_MATURITY_FIELD_LABELS = (
    "Maturity Date",
    "Maturity",
    "Due Date",
    "Redemption Date",
    "Final Redemption Date",
    "Scheduled Redemption Date",
    "Expected Maturity",
)


def _extract_maturity_from_structured_fields(soup: BeautifulSoup) -> tuple[str | None, str]:
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True).rstrip(":")
        if label not in _MATURITY_FIELD_LABELS:
            continue
        value = cells[1].get_text(" ", strip=True)
        parsed = parse_date_maybe(value)
        if parsed:
            return parsed, "detail_table"
    return None, "missing"


def _extract_maturity_from_lines(lines: list[str]) -> tuple[str | None, str]:
    labeled = _extract_field(lines, *_MATURITY_FIELD_LABELS)
    parsed_labeled = parse_date_maybe(labeled)
    if parsed_labeled:
        return parsed_labeled, "detail_field"

    try:
        start = lines.index("CFI code:")
        search_lines = lines[start + 2 :]
    except ValueError:
        search_lines = lines

    for line in search_lines:
        if line.upper() == "LISTING SPONSOR":
            break
        if any(label.lower() in line.lower() for label in _MATURITY_FIELD_LABELS):
            parsed = _extract_maturity_date(line)
            if parsed:
                return parsed, "detail_text"
        parsed = _extract_maturity_date(line)
        if parsed:
            return parsed, "detail_text"
    for index, line in enumerate(search_lines):
        lower = line.lower()
        if not any(marker in lower for marker in ("redemption", "preferred share", "preferred shares", "participating notes")):
            continue
        window = " ".join(search_lines[index : index + 3])
        parsed = _extract_maturity_date(window) or parse_date_maybe(window)
        if parsed:
            return parsed, "detail_context"
    return None, "missing"


def _extract_issue_amount(lines: list[str]) -> str | None:
    pattern = re.compile(r"\b(?:US\$|USD|EUR|GBP)\s*([\d,]+(?:\.\d+)?)")
    try:
        start = lines.index("CFI code:")
        search_lines = lines[start + 2 :]
    except ValueError:
        search_lines = lines

    for line in search_lines:
        if line.upper() == "LISTING SPONSOR":
            break
        match = pattern.search(line)
        if match:
            return match.group(1).replace(",", "")
    return None


def parse_company_page(html: str, source_url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.find(["h1", "h2", "h3"])
    title = title_el.get_text(" ", strip=True) if title_el else ""
    text_lines = [s.strip() for s in soup.stripped_strings if s.strip()]
    company_id_match = re.search(r"CompanyID=(\d+)", source_url, flags=re.IGNORECASE)
    company_id = company_id_match.group(1) if company_id_match else None
    listing_type = _extract_field(text_lines, "Listing Type")
    issuer_name = _extract_issuer_name(text_lines, title)
    maturity_date, maturity_extraction_method = _extract_maturity_from_structured_fields(soup)
    if not maturity_date:
        maturity_date, maturity_extraction_method = _extract_maturity_from_lines(text_lines)
    if not maturity_date:
        maturity_date = _extract_maturity_date(title)
        if maturity_date:
            maturity_extraction_method = "title_text"

    record = {
        "source_name": "bsx",
        "source_url": source_url,
        "company_id": company_id,
        "title": title,
        "listing_type": listing_type,
        "listing_status": _extract_field(text_lines, "Listing Status"),
        "listed_date": parse_date_maybe(_extract_field(text_lines, "Listed on BSX")),
        "available_to": _extract_field(text_lines, "Available to"),
        "currency": _extract_field(text_lines, "Currency", "BSX Currency"),
        "cusip": _extract_field(text_lines, "CUSIP"),
        "isin": _extract_field(text_lines, "ISIN"),
        "cfi_code": _extract_field(text_lines, "CFI code", "CFI Code"),
        "sponsor_name": _extract_field(text_lines, "Sponsor"),
        "issuer_name": issuer_name,
        "issue_amount": _extract_issue_amount(text_lines),
        "maturity_date": maturity_date,
        "maturity_extraction_method": maturity_extraction_method,
        "security_kind": infer_security_kind(title, listing_type=listing_type),
        "retrieved_at": utcnow_iso(),
        "extraction_method": "html_labeled_fields_v2",
        }

    return record


def _request_first_working_listing_page(session, settings: Settings) -> tuple[str, str]:
    errors: list[str] = []
    for url in BSX_ILS_URLS:
        try:
            return url, request_text(session, url, settings)
        except Exception as exc:  # pragma: no cover - network failure path
            errors.append(f"{url}: {exc}")
    raise RuntimeError("unable to fetch BSX ILS listings: " + " | ".join(errors))


def _detail_file_sort_key(path) -> int:
    match = re.search(r"detail_(\d+)\.html$", path.name)
    return int(match.group(1)) if match else 0


def rebuild_bsx_from_raw(settings: Settings) -> list[dict]:
    raw_dir = settings.raw_dir / "bsx"
    detail_paths = sorted(raw_dir.glob("detail_*.html"), key=_detail_file_sort_key)
    if not detail_paths:
        raise RuntimeError("no saved BSX raw detail pages available for fallback reparse")

    existing_records = read_jsonl(settings.processed_dir / "bsx" / "company_records.jsonl")
    records: list[dict] = []
    for index, detail_path in enumerate(detail_paths):
        html = detail_path.read_text(encoding="utf-8", errors="replace")
        source_url = existing_records[index].get("source_url") if index < len(existing_records) else None
        if not source_url:
            company_id_match = re.search(r"CompanyID=(\d+)", html, flags=re.IGNORECASE)
            company_id = company_id_match.group(1) if company_id_match else None
            source_url = (
                f"https://www.bsx.com/company_details.php?CompanyID={company_id}"
                if company_id
                else f"https://www.bsx.com/company_details.php?raw_index={index + 1}"
            )
        records.append(parse_company_page(html, source_url=source_url))

    processed_base = settings.processed_dir / "bsx" / "company_records"
    write_records_bundle(processed_base, records)
    write_json(
        settings.processed_dir / "bsx" / "manifest.json",
        {
            "source": "bsx",
            "record_count": len(records),
            "detail_count": len(detail_paths),
            "reparsed_from_raw": True,
            "retrieved_at": utcnow_iso(),
        },
    )
    return records


def fetch_bsx_ils(settings: Settings, max_pages: int | None = None, force: bool = False) -> list[dict]:
    session = build_session(settings)
    raw_dir = settings.raw_dir / "bsx"
    processed_base = settings.processed_dir / "bsx" / "company_records"

    try:
        first_url, first_html = _request_first_working_listing_page(session, settings)
    except RuntimeError:
        return rebuild_bsx_from_raw(settings)
    (raw_dir / "index_page_1.html").parent.mkdir(parents=True, exist_ok=True)
    (raw_dir / "index_page_1.html").write_text(first_html, encoding="utf-8")

    page_urls: list[str] = []
    pending_urls = [first_url]
    seen_page_urls: set[str] = set()
    detail_links: list[str] = []
    while pending_urls and (max_pages is None or len(page_urls) < max_pages):
        page_url = pending_urls.pop(0)
        if page_url in seen_page_urls:
            continue
        seen_page_urls.add(page_url)
        page_urls.append(page_url)
        if len(page_urls) == 1:
            html = first_html
        else:
            html = request_text(session, page_url, settings)
            (raw_dir / f"index_page_{len(page_urls)}.html").write_text(html, encoding="utf-8")
        detail_links.extend(parse_listing_links(html, page_url))
        for pagination_url in parse_pagination_links(html, page_url):
            if pagination_url not in seen_page_urls and pagination_url not in pending_urls:
                pending_urls.append(pagination_url)

    detail_links = sorted(set(detail_links))
    records: list[dict] = []
    for idx, detail_url in enumerate(detail_links, start=1):
        html = request_text(session, detail_url, settings)
        (raw_dir / f"detail_{idx}.html").write_text(html, encoding="utf-8")
        records.append(parse_company_page(html, source_url=detail_url))

    write_records_bundle(processed_base, records)
    page_limit_reached = max_pages is not None and bool(pending_urls)
    write_json(settings.processed_dir / "bsx" / "manifest.json", {
        "source": "bsx",
        "pages_requested": page_urls,
        "page_limit": max_pages,
        "page_limit_reached": page_limit_reached,
        "crawl_complete": not page_limit_reached,
        "detail_count": len(detail_links),
        "record_count": len(records),
        "retrieved_at": utcnow_iso(),
    })
    return records
