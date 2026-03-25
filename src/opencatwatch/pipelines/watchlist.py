from __future__ import annotations

try:
    import polars as pl
except Exception:  # pragma: no cover
    pl = None  # type: ignore
from datetime import datetime
from pathlib import Path

from ..config import Settings
from ..matching.rules import build_match
from ..utils import extract_region_codes, read_json, read_jsonl, write_records_bundle

_STATE_TO_REGIONS: dict[str, list[str]] = {
    "CA": ["california"],
    "FL": ["florida"],
    "TX": ["texas"],
    "LA": ["louisiana"],
    "NC": ["north_carolina"],
    "SC": ["south_carolina"],
    "GA": ["georgia"],
    "AL": ["alabama"],
    "MS": ["mississippi"],
    "HI": ["hawaii"],
    "AK": ["alaska"],
    "PR": ["us"],
    "VI": ["us"],
}

_FEMA_TYPE_TO_PERIL: dict[str, str] = {
    "Hurricane": "us_wind",
    "Typhoon": "us_wind",
    "Severe Storm": "severe_convective_storm",
    "Tornado": "severe_convective_storm",
    "Fire": "ca_wildfire",
    "Flood": "flood",
    "Earthquake": "ca_earthquake",
    "Tsunami": "ca_earthquake",
    "Coastal Storm": "us_wind",
    "Snow": "severe_convective_storm",
    "Ice Storm": "severe_convective_storm",
}

_IBTRACS_ACTIVE_FILENAME = "ibtracs.ACTIVE.list.v04r01.csv"
_IBTRACS_BASIN_TO_PERIL: dict[str, str] = {
    "NA": "us_wind",
    "EA": "us_wind",
    "EP": "us_wind",
    "CP": "us_wind",
    "WP": "japan_typhoon",
    "SP": "tropical_cyclone",
    "SI": "tropical_cyclone",
    "MM": "tropical_cyclone",
}
_IBTRACS_BASIN_TO_REGIONS: dict[str, list[str]] = {
    "NA": ["us"],
    "EA": ["us"],
    "EP": ["us"],
    "CP": ["us"],
}


def _canonicalize_ibtracs(row: dict) -> dict | None:
    sid = (row.get("SID") or "").strip()
    if not sid:
        return None

    start_time = _normalize_ibtracs_time(row.get("ISO_TIME"))
    if not start_time:
        return None

    basin = (row.get("BASIN") or "").strip().upper()
    peril_code = _IBTRACS_BASIN_TO_PERIL.get(basin, "tropical_cyclone")
    regions = _IBTRACS_BASIN_TO_REGIONS.get(basin, [])

    name = (row.get("NAME") or "").strip()
    if name and name.upper() != "UNNAMED":
        event_name = f"{name} Tropical Cyclone"
    else:
        event_name = "Unspecified Tropical Cyclone"

    return {
        "event_id": f"ibtracs-{sid}",
        "source_name": "ibtracs",
        "peril_code": peril_code,
        "event_name": event_name,
        "start_time": start_time[:10],
        "end_time": start_time[:10],
        "region_codes": regions,
        "source_url": None,
    }


def _find_ibtracs_csv(settings: Settings) -> Path | None:
    raw_dir = settings.raw_dir / "ibtracs"
    if not raw_dir.exists():
        return None

    manifest_path = settings.processed_dir / "ibtracs" / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = read_json(manifest_path)
            filename = manifest.get("filename")
            if isinstance(filename, str):
                path = raw_dir / filename
                if path.exists():
                    return path
        except Exception:
            pass

    active_path = raw_dir / _IBTRACS_ACTIVE_FILENAME
    if active_path.exists():
        return active_path

    csv_files = sorted(raw_dir.glob("ibtracs*.list.v04r01.csv"))
    return csv_files[0] if csv_files else None


def _normalize_ibtracs_time(value: object) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _load_ibtracs_events(settings: Settings) -> list[dict]:
    path = _find_ibtracs_csv(settings)
    if not path or not path.exists():
        return []

    import csv

    storms: dict[str, dict] = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if not row:
                    continue
                canonical = _canonicalize_ibtracs(row)
                if not canonical:
                    continue
                event_id = canonical["event_id"]
                existing = storms.get(event_id)
                if not existing:
                    storms[event_id] = canonical
                    continue

                if (
                    canonical["event_name"]
                    and existing["event_name"] == "Unspecified Tropical Cyclone"
                    and canonical["event_name"] != "Unspecified Tropical Cyclone"
                ):
                    existing["event_name"] = canonical["event_name"]

                existing_start = existing.get("start_time") or ""
                if (
                    canonical["start_time"]
                    and (
                        not existing_start
                        or canonical["start_time"] < existing_start
                    )
                ):
                    existing["start_time"] = canonical["start_time"]
                existing_end = existing.get("end_time")
                if (
                    canonical["end_time"]
                    and (not existing_end or canonical["end_time"] > existing_end)
                ):
                    existing["end_time"] = canonical["end_time"]

                merged_regions = sorted(
                    set((existing.get("region_codes") or []) + (canonical.get("region_codes") or []))
                )
                if merged_regions:
                    existing["region_codes"] = merged_regions
    except Exception:
        return []

    return list(storms.values())


def _canonicalize_fema(row: dict) -> dict | None:
    incident_type = row.get("incidentType") or ""
    peril = _FEMA_TYPE_TO_PERIL.get(incident_type)
    if not peril:
        return None
    state = row.get("state") or ""
    regions = _STATE_TO_REGIONS.get(state, ["us"])
    begin = row.get("incidentBeginDate")
    begin_str = str(begin)[:10] if begin else None
    end = row.get("incidentEndDate")
    end_str = str(end)[:10] if end else None
    return {
        "event_id": f"fema-{row.get('disasterNumber', '')}-{state}",
        "source_name": "openfema",
        "peril_code": peril,
        "event_name": row.get("declarationTitle") or incident_type,
        "start_time": begin_str,
        "end_time": end_str,
        "region_codes": regions,
        "source_url": None,
    }


def _load_fema_events(settings: Settings) -> list[dict]:
    path = settings.raw_dir / "openfema" / "DisasterDeclarationsSummaries.parquet"
    if not path.exists() or pl is None:
        return []
    from datetime import date

    df = pl.read_parquet(path)
    cutoff = date(date.today().year - 2, 1, 1)
    declaration_expr = pl.col("declarationDate")
    if df.schema.get("declarationDate") == pl.String:
        declaration_expr = declaration_expr.str.slice(0, 10).str.strptime(pl.Date, strict=False)
    else:
        declaration_expr = declaration_expr.cast(pl.Date, strict=False)
    recent = df.with_columns(declaration_date=declaration_expr)
    recent = recent.filter(pl.col("declaration_date") >= pl.lit(cutoff))
    events: list[dict] = []
    seen: set[str] = set()
    for row in recent.to_dicts():
        canonical = _canonicalize_fema(row)
        if canonical and canonical["event_id"] not in seen:
            seen.add(canonical["event_id"])
            events.append(canonical)
    return events


_STORM_EVENT_TYPE_TO_PERIL: dict[str, str] = {
    # Only tropical/hurricane events — tornadoes and wildfires are too granular
    # and already covered by NWS active alerts.
    "Hurricane": "us_wind",
    "Hurricane (Typhoon)": "us_wind",
    "Marine Hurricane/Typhoon": "us_wind",
    "Tropical Storm": "us_wind",
    "Marine Tropical Storm": "us_wind",
    "Tropical Depression": "us_wind",
    "Marine Tropical Depression": "us_wind",
}


def _load_storm_events(settings: Settings) -> list[dict]:
    """Load NOAA Storm Events from raw gzipped CSVs, filtering for cat-bond-relevant types."""
    import csv
    import gzip

    raw_dir = settings.raw_dir / "noaa_stormevents"
    if not raw_dir.exists():
        return []

    events: list[dict] = []
    seen: set[str] = set()
    for gz_path in sorted(raw_dir.glob("StormEvents_details*.csv.gz")):
        try:
            with gzip.open(gz_path, "rt", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    event_type = row.get("EVENT_TYPE", "")
                    peril = _STORM_EVENT_TYPE_TO_PERIL.get(event_type)
                    if not peril:
                        continue
                    episode_id = row.get("EPISODE_ID", "")
                    event_key = f"se-{episode_id}" if episode_id else f"se-{row.get('EVENT_ID','')}"
                    if event_key in seen:
                        continue
                    seen.add(event_key)
                    state = row.get("STATE", "")
                    state_abbr = row.get("STATE_FIPS", "")[:2] if row.get("STATE_FIPS") else ""
                    regions = _STATE_TO_REGIONS.get(state_abbr, [])
                    if not regions and state:
                        regions = ["us"]
                    # Build ISO date from YEARMONTH + DAY fields (more reliable than datetime string)
                    ym = row.get("BEGIN_YEARMONTH", "")
                    day = row.get("BEGIN_DAY", "1").zfill(2)
                    begin_date = f"{ym[:4]}-{ym[4:6]}-{day}" if len(ym) >= 6 else None
                    end_ym = row.get("END_YEARMONTH", "")
                    end_day = row.get("END_DAY", "1").zfill(2)
                    end_date = f"{end_ym[:4]}-{end_ym[4:6]}-{end_day}" if len(end_ym) >= 6 else None
                    events.append({
                        "event_id": event_key,
                        "source_name": "noaa_stormevents",
                        "peril_code": peril,
                        "event_name": f"{event_type} - {state}",
                        "start_time": begin_date,
                        "end_time": end_date,
                        "region_codes": regions,
                        "source_url": None,
                    })
        except Exception:
            continue
    return events


def _map_nws_alert_to_peril(alert: dict) -> str | None:
    event_name = (alert.get("event_name") or "").lower()
    headline = (alert.get("headline") or "").lower()
    text = f"{event_name} {headline}"
    if "hurricane" in text or "tropical storm" in text:
        return "us_wind"
    if "red flag" in text or "wildfire" in text or "fire weather" in text:
        return "ca_wildfire"
    if "flood" in text:
        return "flood"
    if "severe thunderstorm" in text or "tornado" in text or "hail" in text:
        return "severe_convective_storm"
    return None


def _canonicalize_nws(alert: dict) -> dict | None:
    peril = _map_nws_alert_to_peril(alert)
    if not peril:
        return None
    area_desc = alert.get("area_desc") or ""
    regions = []
    lower = area_desc.lower()
    if "california" in lower:
        regions.append("california")
    if "florida" in lower:
        regions.append("florida")
    if "texas" in lower:
        regions.append("texas")
    if not regions:
        regions.append("us")
    return {
        "event_id": alert.get("source_event_id"),
        "source_name": "nws",
        "peril_code": peril,
        "event_name": alert.get("event_name"),
        "start_time": alert.get("start_time"),
        "end_time": alert.get("end_time"),
        "region_codes": regions,
        "source_url": alert.get("source_url"),
    }


def _canonicalize_usgs(row: dict) -> dict:
    region_codes = row.get("region_codes", []) or extract_region_codes(row.get("event_name"))
    return {
        "event_id": row.get("source_event_id"),
        "source_name": "usgs",
        "peril_code": row.get("peril_code"),
        "event_name": row.get("event_name"),
        "start_time": row.get("start_time"),
        "end_time": row.get("end_time"),
        "region_codes": region_codes,
        "source_url": row.get("source_url"),
    }


def _dedupe_events(events: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for event in events:
        event_id = event.get("event_id")
        if not event_id:
            continue
        existing = deduped.get(event_id)
        if not existing:
            deduped[event_id] = event
            continue
        merged_regions = sorted(
            set((existing.get("region_codes") or []) + (event.get("region_codes") or []))
        )
        if not existing.get("event_name") and event.get("event_name"):
            existing["event_name"] = event.get("event_name")
        if not existing.get("peril_code") and event.get("peril_code"):
            existing["peril_code"] = event.get("peril_code")
        if not existing.get("start_time") and event.get("start_time"):
            existing["start_time"] = event.get("start_time")
        if not existing.get("end_time") and event.get("end_time"):
            existing["end_time"] = event.get("end_time")
        if merged_regions:
            existing["region_codes"] = merged_regions
    return list(deduped.values())


def build_watchlist(settings: Settings) -> str:
    tranches = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    nws_rows = read_jsonl(settings.processed_dir / "nws" / "alerts_active.jsonl")
    usgs_rows = read_jsonl(settings.processed_dir / "usgs" / "events.jsonl")

    events = []
    for alert in nws_rows:
        normalized = _canonicalize_nws(alert)
        if normalized:
            events.append(normalized)

    for row in usgs_rows:
        events.append(_canonicalize_usgs(row))

    events.extend(_load_fema_events(settings))
    events.extend(_load_storm_events(settings))
    events.extend(_load_ibtracs_events(settings))
    events = _dedupe_events(events)

    candidate_tranches = [
        tranche
        for tranche in tranches
        if tranche.get("status") == "outstanding" and not tranche.get("is_programme_shell")
    ]

    matches = []
    for event in events:
        for tranche in candidate_tranches:
            match = build_match(tranche=tranche, event=event)
            if match:
                matches.append(match)

    matches.sort(
        key=lambda row: (
            -float(row.get("score") or 0.0),
            row.get("event_id") or "",
            row.get("tranche_id") or "",
        )
    )
    write_records_bundle(settings.processed_dir / "watchlist" / "events", events)
    write_records_bundle(settings.processed_dir / "watchlist" / "matches", matches)
    return str(settings.processed_dir / "watchlist" / "matches.jsonl")
