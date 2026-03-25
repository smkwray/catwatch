from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import Settings
from ..http import build_session, download_file, request_text
from ..utils import utcnow_iso, write_json

INDEX_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"


def parse_index_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".csv.gz"):
            links.append(urljoin(base_url, href))
    return sorted(set(links))


def select_files(urls: list[str], year_start: int, year_end: int) -> list[str]:
    selected = []
    for url in urls:
        name = url.rsplit("/", 1)[-1]
        year_match = re.search(r"_d(\d{4})_", name)
        if not year_match:
            continue
        year = int(year_match.group(1))
        if year_start <= year <= year_end and "details" in name.lower():
            selected.append(url)
    return selected


def fetch_stormevents_files(settings: Settings, year_start: int, year_end: int) -> list[str]:
    session = build_session(settings)
    html = request_text(session, INDEX_URL, settings)
    (settings.raw_dir / "noaa_stormevents").mkdir(parents=True, exist_ok=True)
    (settings.raw_dir / "noaa_stormevents" / "index.html").write_text(html, encoding="utf-8")
    all_links = parse_index_links(html, INDEX_URL)
    selected = select_files(all_links, year_start=year_start, year_end=year_end)

    downloaded: list[str] = []
    for url in selected:
        filename = url.rsplit("/", 1)[-1]
        dest = settings.raw_dir / "noaa_stormevents" / filename
        download_file(session, url, dest, settings)
        downloaded.append(str(dest))

    write_json(
        settings.processed_dir / "noaa_stormevents" / "manifest.json",
        {
            "source": "noaa_stormevents",
            "year_start": year_start,
            "year_end": year_end,
            "downloaded_files": downloaded,
            "retrieved_at": utcnow_iso(),
        },
    )
    return downloaded
