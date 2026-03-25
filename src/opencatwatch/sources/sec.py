from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from pathlib import Path

from bs4 import BeautifulSoup

from ..config import Settings
from ..http import build_session, download_file, request_json, request_text
from ..utils import utcnow_iso, write_records_bundle

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik_no_zero}/{accession_no_dashes}/{primary_doc}"


def zero_pad_cik(cik: str | int) -> str:
    digits = str(cik).strip()
    digits = digits.split(".")[0]
    return digits.zfill(10)


def download_company_tickers(settings: Settings) -> Path:
    session = build_session(settings)
    dest = settings.raw_dir / "sec" / "company_tickers.json"
    return download_file(session, COMPANY_TICKERS_URL, dest, settings)


def load_company_tickers(settings: Settings) -> list[dict]:
    path = settings.raw_dir / "sec" / "company_tickers.json"
    if not path.exists():
        download_company_tickers(settings)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [payload[k] for k in sorted(payload.keys(), key=lambda x: int(x))]
    return payload


def suggest_cik(settings: Settings, sponsor_name: str) -> str | None:
    rows = load_company_tickers(settings)
    lower = sponsor_name.lower().strip()
    for row in rows:
        title = str(row.get("title", "")).lower()
        if lower == title:
            return zero_pad_cik(row["cik_str"])
    for row in rows:
        title = str(row.get("title", "")).lower()
        if lower in title or title in lower:
            return zero_pad_cik(row["cik_str"])
    return None


def fetch_submissions_json(settings: Settings, cik: str) -> dict:
    session = build_session(settings)
    url = SUBMISSIONS_URL_TEMPLATE.format(cik=zero_pad_cik(cik))
    payload = request_json(session, url, settings)
    dest = settings.raw_dir / "sec" / f"submissions_{zero_pad_cik(cik)}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def flatten_recent_filings(payload: dict, sponsor_name: str) -> list[dict]:
    recent = payload.get("filings", {}).get("recent", {})
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    company_name = payload.get("name", sponsor_name)
    cik = zero_pad_cik(payload.get("cik", ""))
    rows: list[dict] = []
    for accession, primary_doc, form, filing_date in zip(
        accession_numbers,
        primary_docs,
        forms,
        filing_dates,
        strict=False,
    ):
        accession_no_dashes = str(accession).replace("-", "")
        rows.append(
            {
                "source_name": "sec",
                "sponsor_name": sponsor_name,
                "company_name": company_name,
                "cik": cik,
                "form": form,
                "filing_date": filing_date,
                "accession_number": accession,
                "primary_doc": primary_doc,
                "filing_url": ARCHIVE_URL_TEMPLATE.format(
                    cik_no_zero=str(int(cik)) if cik else "",
                    accession_no_dashes=accession_no_dashes,
                    primary_doc=primary_doc,
                ),
                "retrieved_at": utcnow_iso(),
            }
        )
    return rows


def _filing_scan_priority(form: str | None, primary_doc: str | None) -> tuple[int, int]:
    normalized_form = (form or "").upper().strip()
    doc_lower = (primary_doc or "").lower()

    if normalized_form in {"10-K", "10-K/A", "20-F", "20-F/A"}:
        form_priority = 0
    elif normalized_form in {"10-Q", "10-Q/A", "6-K", "6-K/A"}:
        form_priority = 1
    elif normalized_form in {"8-K", "8-K/A"}:
        form_priority = 2
    elif normalized_form.startswith("DEF 14") or normalized_form.startswith("S-") or normalized_form.startswith("424"):
        form_priority = 3
    elif normalized_form in {"4", "4/A", "3", "3/A", "5", "5/A", "144"}:
        form_priority = 9
    else:
        form_priority = 5

    extension_priority = 0 if doc_lower.endswith((".htm", ".html", ".txt")) else 1
    return form_priority, extension_priority


def select_filings_for_term_scan(filings: list[dict], max_docs: int) -> list[dict]:
    ranked = sorted(
        filings,
        key=lambda filing: (
            *_filing_scan_priority(filing.get("form"), filing.get("primary_doc")),
            -(int((filing.get("filing_date") or "0000-00-00").replace("-", ""))),
            filing.get("accession_number") or "",
        ),
    )
    return ranked[: max(0, max_docs)]


def scan_terms_in_html(html: str, terms: Iterable[str]) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    hits: list[dict] = []
    for term in terms:
        for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
            start = max(0, match.start() - 140)
            end = min(len(text), match.end() + 140)
            snippet = text[start:end]
            hits.append({"term": term, "snippet": snippet})
    return hits


_LEGAL_SUFFIX_PATTERN = (
    r"(?:Ltd|Limited|Inc|Corp|Corporation|DAC|PLC|SAC|PCC(?:\s+Limited)?|Pte\.?\s+Ltd\.?)"
)
_SPV_NAME_PATTERN = (
    r"([A-Z][A-Za-z0-9&'’.,()/:-]*"
    r"(?:\s+[A-Z0-9][A-Za-z0-9&'’.,()/:-]*){0,10}"
    r"\s+(?:Re|Reinsurance|Insurance|Capital)\s+"
    + _LEGAL_SUFFIX_PATTERN
    + r"\.?)"
)
_SPV_PATTERNS = [
    re.compile(r"(?:via|through)\s+" + _SPV_NAME_PATTERN, flags=re.IGNORECASE),
    re.compile(r"(?:issued|placed|provided|sponsored)\s+(?:via|through|by)\s+" + _SPV_NAME_PATTERN, flags=re.IGNORECASE),
    re.compile(r"(?:used|using)\s+(?:the\s+existing\s+)?" + _SPV_NAME_PATTERN, flags=re.IGNORECASE),
]


def extract_sponsor_spv_links(term_hits: list[dict]) -> list[dict]:
    """Extract sponsor → SPV links from SEC term hit snippets.

    Returns deduplicated records mapping sponsors to the SPV names found in
    their filing text, suitable for joining against BSX issuer names.
    """
    from ..utils import normalize_name

    seen: set[tuple[str, str]] = set()
    links: list[dict] = []
    for hit in term_hits:
        sponsor = hit.get("sponsor_name", "")
        snippet = hit.get("snippet", "")
        for pat in _SPV_PATTERNS:
            for m in pat.finditer(snippet):
                spv_raw = m.group(1).strip(" ,.")
                spv_norm = normalize_name(spv_raw)
                if not spv_norm or len(spv_norm) < 4:
                    continue
                key = (sponsor, spv_norm)
                if key in seen:
                    continue
                seen.add(key)
                links.append({
                    "sponsor_name": sponsor,
                    "spv_name": spv_raw,
                    "spv_name_normalized": spv_norm,
                    "source_filing_url": hit.get("filing_url", ""),
                    "source_term": hit.get("term", ""),
                })
    return links


def fetch_sec_for_sponsors(
    settings: Settings,
    sponsors_csv: Path,
    download_docs: bool = False,
    max_docs_per_sponsor: int = 3,
    terms: list[str] | None = None,
) -> dict:
    terms = terms or [
        "catastrophe bond",
        "cat bond",
        "special purpose insurer",
        "parametric",
        "wildfire",
        "earthquake",
        "hurricane",
        "reinsurance",
    ]
    session = build_session(settings)
    filings_rows: list[dict] = []
    hits_rows: list[dict] = []

    with sponsors_csv.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        sponsor_rows = list(reader)

    for sponsor_row in sponsor_rows:
        sponsor_name = sponsor_row.get("sponsor_name", "").strip()
        cik = sponsor_row.get("cik", "").strip() or suggest_cik(settings, sponsor_name)
        if not sponsor_name or not cik:
            continue
        payload = fetch_submissions_json(settings, cik)
        flattened = flatten_recent_filings(payload, sponsor_name=sponsor_name)
        filings_rows.extend(flattened)
        if download_docs:
            for filing in select_filings_for_term_scan(flattened, max_docs=max_docs_per_sponsor):
                url = filing["filing_url"]
                try:
                    html = request_text(session, url, settings)
                except Exception:
                    continue
                file_dest = settings.raw_dir / "sec" / "filings" / filing["cik"] / f"{filing['accession_number']}.html"
                file_dest.parent.mkdir(parents=True, exist_ok=True)
                file_dest.write_text(html, encoding="utf-8")
                for hit in scan_terms_in_html(html, terms):
                    hits_rows.append(
                        {
                            "source_name": "sec",
                            "sponsor_name": sponsor_name,
                            "cik": filing["cik"],
                            "filing_date": filing["filing_date"],
                            "form": filing["form"],
                            "accession_number": filing["accession_number"],
                            "filing_url": url,
                            "term": hit["term"],
                            "snippet": hit["snippet"],
                            "retrieved_at": utcnow_iso(),
                        }
                    )

    spv_links = extract_sponsor_spv_links(hits_rows)
    write_records_bundle(settings.processed_dir / "sec" / "recent_filings", filings_rows)
    write_records_bundle(settings.processed_dir / "sec" / "term_hits", hits_rows)
    write_records_bundle(settings.processed_dir / "sec" / "sponsor_spv_links", spv_links)
    return {"filings": len(filings_rows), "hits": len(hits_rows), "spv_links": len(spv_links)}
