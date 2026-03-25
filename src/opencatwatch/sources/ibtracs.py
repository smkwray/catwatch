from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..http import build_session, download_file
from ..utils import utcnow_iso, write_json

IBTRACS_BASE = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/csv/"
)

KIND_TO_FILE = {
    "active": "ibtracs.ACTIVE.list.v04r01.csv",
    "last3years": "ibtracs.last3years.list.v04r01.csv",
    "since1980": "ibtracs.since1980.list.v04r01.csv",
    "na": "ibtracs.NA.list.v04r01.csv",
}


def fetch_ibtracs_csv(settings: Settings, kind: str = "active") -> Path:
    filename = KIND_TO_FILE.get(kind, KIND_TO_FILE["active"])
    url = IBTRACS_BASE + filename
    session = build_session(settings)
    dest = settings.raw_dir / "ibtracs" / filename
    download_file(session, url, dest, settings)
    write_json(
        settings.processed_dir / "ibtracs" / "manifest.json",
        {
            "source": "ibtracs",
            "kind": kind,
            "filename": filename,
            "url": url,
            "retrieved_at": utcnow_iso(),
        },
    )
    return dest
