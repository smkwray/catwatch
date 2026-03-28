from __future__ import annotations

try:
    import polars as pl
except Exception:  # pragma: no cover
    pl = None  # type: ignore
from datetime import date, datetime
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
_IBTRACS_DATASET_URL = "https://www.ncei.noaa.gov/products/international-best-track-archive"
_OPENFEMA_DATASET_URL = "https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2"
_STORMEVENTS_DATASET_URL = "https://www.ncei.noaa.gov/stormevents/"

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
_PROPERTY_CAT_EVENT_PERILS = {"us_wind", "ca_earthquake", "ca_wildfire", "flood", "severe_convective_storm"}
_US_REGION_CODES = {
    "us",
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "florida",
    "georgia",
    "hawaii",
    "louisiana",
    "mississippi",
    "north_carolina",
    "south_carolina",
    "texas",
}

_STORM_EVENT_STATE_TO_REGION: dict[str, list[str]] = {
    "alabama": ["alabama"],
    "alaska": ["alaska"],
    "arizona": ["arizona"],
    "arkansas": ["arkansas"],
    "california": ["california"],
    "colorado": ["colorado"],
    "connecticut": ["connecticut"],
    "delaware": ["delaware"],
    "florida": ["florida"],
    "georgia": ["georgia"],
    "hawaii": ["hawaii"],
    "idaho": ["idaho"],
    "illinois": ["illinois"],
    "indiana": ["indiana"],
    "iowa": ["iowa"],
    "kansas": ["kansas"],
    "kentucky": ["kentucky"],
    "louisiana": ["louisiana"],
    "maine": ["maine"],
    "maryland": ["maryland"],
    "massachusetts": ["massachusetts"],
    "michigan": ["michigan"],
    "minnesota": ["minnesota"],
    "mississippi": ["mississippi"],
    "missouri": ["missouri"],
    "montana": ["montana"],
    "nebraska": ["nebraska"],
    "nevada": ["nevada"],
    "new hampshire": ["new_hampshire"],
    "new jersey": ["new_jersey"],
    "new mexico": ["new_mexico"],
    "new york": ["new_york"],
    "north carolina": ["north_carolina"],
    "north dakota": ["north_dakota"],
    "ohio": ["ohio"],
    "oklahoma": ["oklahoma"],
    "oregon": ["oregon"],
    "pennsylvania": ["pennsylvania"],
    "rhode island": ["rhode_island"],
    "south carolina": ["south_carolina"],
    "south dakota": ["south_dakota"],
    "tennessee": ["tennessee"],
    "texas": ["texas"],
    "utah": ["utah"],
    "vermont": ["vermont"],
    "virginia": ["virginia"],
    "washington": ["washington"],
    "west virginia": ["west_virginia"],
    "wisconsin": ["wisconsin"],
    "wyoming": ["wyoming"],
    "district of columbia": ["us"],
    "puerto rico": ["us"],
    "u.s. virgin islands": ["us"],
    "us virgin islands": ["us"],
    "virgin islands": ["us"],
    "guam": ["us"],
    "american samoa": ["us"],
    "northern mariana islands": ["us"],
}

_STORM_EVENT_ABBR_TO_REGION: dict[str, list[str]] = {
    "AL": ["alabama"],
    "AK": ["alaska"],
    "AZ": ["arizona"],
    "AR": ["arkansas"],
    "CA": ["california"],
    "CO": ["colorado"],
    "CT": ["connecticut"],
    "DE": ["delaware"],
    "FL": ["florida"],
    "GA": ["georgia"],
    "HI": ["hawaii"],
    "ID": ["idaho"],
    "IL": ["illinois"],
    "IN": ["indiana"],
    "IA": ["iowa"],
    "KS": ["kansas"],
    "KY": ["kentucky"],
    "LA": ["louisiana"],
    "ME": ["maine"],
    "MD": ["maryland"],
    "MA": ["massachusetts"],
    "MI": ["michigan"],
    "MN": ["minnesota"],
    "MS": ["mississippi"],
    "MO": ["missouri"],
    "MT": ["montana"],
    "NE": ["nebraska"],
    "NV": ["nevada"],
    "NH": ["new_hampshire"],
    "NJ": ["new_jersey"],
    "NM": ["new_mexico"],
    "NY": ["new_york"],
    "NC": ["north_carolina"],
    "ND": ["north_dakota"],
    "OH": ["ohio"],
    "OK": ["oklahoma"],
    "OR": ["oregon"],
    "PA": ["pennsylvania"],
    "RI": ["rhode_island"],
    "SC": ["south_carolina"],
    "SD": ["south_dakota"],
    "TN": ["tennessee"],
    "TX": ["texas"],
    "UT": ["utah"],
    "VT": ["vermont"],
    "VA": ["virginia"],
    "WA": ["washington"],
    "WV": ["west_virginia"],
    "WI": ["wisconsin"],
    "WY": ["wyoming"],
    "DC": ["us"],
    "PR": ["us"],
    "VI": ["us"],
    "GU": ["us"],
    "AS": ["us"],
    "MP": ["us"],
}


def _empty_event_geo_fields() -> dict[str, object]:
    return {
        "event_latitude": None,
        "event_longitude": None,
        "event_bbox": None,
    }


def _extract_geometry_points(geometry: dict | None) -> list[tuple[float, float]]:
    if not geometry:
        return []
    coordinates = geometry.get("coordinates")
    if coordinates is None:
        return []

    points: list[tuple[float, float]] = []

    def _walk(node: object) -> None:
        if not isinstance(node, list):
            return
        if len(node) >= 2 and all(isinstance(value, (int, float)) for value in node[:2]):
            points.append((float(node[1]), float(node[0])))
            return
        for value in node:
            _walk(value)

    _walk(coordinates)
    return points


def _event_geo_from_geometry(geometry: dict | None) -> dict[str, object]:
    points = _extract_geometry_points(geometry)
    if not points:
        return _empty_event_geo_fields()

    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    min_latitude = min(latitudes)
    max_latitude = max(latitudes)
    min_longitude = min(longitudes)
    max_longitude = max(longitudes)
    return {
        "event_latitude": round((min_latitude + max_latitude) / 2, 6),
        "event_longitude": round((min_longitude + max_longitude) / 2, 6),
        "event_bbox": {
            "min_latitude": round(min_latitude, 6),
            "min_longitude": round(min_longitude, 6),
            "max_latitude": round(max_latitude, 6),
            "max_longitude": round(max_longitude, 6),
        },
    }


def _merge_event_bbox(existing_bbox: dict | None, new_bbox: dict | None) -> dict | None:
    if not existing_bbox:
        return new_bbox
    if not new_bbox:
        return existing_bbox
    return {
        "min_latitude": min(float(existing_bbox["min_latitude"]), float(new_bbox["min_latitude"])),
        "min_longitude": min(float(existing_bbox["min_longitude"]), float(new_bbox["min_longitude"])),
        "max_latitude": max(float(existing_bbox["max_latitude"]), float(new_bbox["max_latitude"])),
        "max_longitude": max(float(existing_bbox["max_longitude"]), float(new_bbox["max_longitude"])),
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
        "source_url": _IBTRACS_DATASET_URL,
        "source_record_id": sid,
        **_empty_event_geo_fields(),
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
        "source_url": _OPENFEMA_DATASET_URL,
        "source_record_id": str(row.get("disasterNumber") or ""),
        **_empty_event_geo_fields(),
    }


def _storm_event_region_codes(state: object) -> list[str]:
    if not state:
        return []
    key = str(state).strip()
    if not key:
        return []
    lower = key.lower()
    if lower in _STORM_EVENT_STATE_TO_REGION:
        return _STORM_EVENT_STATE_TO_REGION[lower]
    upper = key.upper()
    if upper in _STORM_EVENT_ABBR_TO_REGION:
        return _STORM_EVENT_ABBR_TO_REGION[upper]
    return []


def _load_fema_events(settings: Settings) -> list[dict]:
    path = settings.raw_dir / "openfema" / "DisasterDeclarationsSummaries.parquet"
    if not path.exists() or pl is None:
        return []
    df = pl.read_parquet(path)
    cutoff = date(settings.as_of_date.year - 2, 1, 1)
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
                    regions = _storm_event_region_codes(state)
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
                        "source_url": _STORMEVENTS_DATASET_URL,
                        "source_record_id": row.get("EVENT_ID") or episode_id or event_key,
                        **_empty_event_geo_fields(),
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
    regions = extract_region_codes(area_desc)
    if not regions:
        regions.append("us")
    geo = _event_geo_from_geometry(alert.get("geometry_json"))
    return {
        "event_id": alert.get("source_event_id"),
        "source_name": "nws",
        "peril_code": peril,
        "event_name": alert.get("event_name"),
        "start_time": alert.get("start_time"),
        "end_time": alert.get("end_time"),
        "region_codes": regions,
        "source_url": alert.get("source_url"),
        "source_record_id": alert.get("source_event_id"),
        **geo,
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
        "source_record_id": row.get("source_event_id"),
        "event_latitude": row.get("latitude"),
        "event_longitude": row.get("longitude"),
        "event_bbox": None,
    }


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _event_peril_keys_for_tranche(tranche: dict) -> set[str]:
    keys: set[str] = set()
    for peril in tranche.get("peril_codes") or []:
        if not peril:
            continue
        keys.add(str(peril))
        if peril == "ca_earthquake":
            keys.add("earthquake")
        if peril == "us_wind":
            keys.add("tropical_cyclone")
        if peril == "other_property_cat":
            keys.update(_PROPERTY_CAT_EVENT_PERILS)
    return keys


def _build_tranche_peril_index(tranches: list[dict]) -> dict[str, list[dict]]:
    indexed: dict[str, list[dict]] = {}
    for tranche in tranches:
        for key in _event_peril_keys_for_tranche(tranche):
            indexed.setdefault(key, []).append(tranche)
    return indexed


def _event_date_overlaps_tranche_window(tranche: dict, event: dict) -> bool:
    start = _to_date(tranche.get("risk_start_date") or tranche.get("listed_date"))
    end = _to_date(tranche.get("risk_end_date") or tranche.get("maturity_date"))
    event_date = _to_date(event.get("start_time"))
    if event_date is None:
        return False
    if start and event_date < start:
        return False
    if end and event_date > end:
        return False
    return True


def _regions_could_overlap(tranche: dict, event: dict) -> bool:
    tranche_regions = set(tranche.get("region_codes", []) or [])
    event_regions = set(event.get("region_codes", []) or [])
    if not tranche_regions or not event_regions:
        return True
    if "global" in tranche_regions or "global" in event_regions:
        return True
    if tranche_regions & event_regions:
        return True
    if "us" in tranche_regions and event_regions.issubset(_US_REGION_CODES):
        return True
    if "us" in event_regions and tranche_regions.issubset(_US_REGION_CODES):
        return True
    return False


def _candidate_tranches_for_event(event: dict, tranches_by_peril: dict[str, list[dict]]) -> list[dict]:
    event_peril = str(event.get("peril_code") or "")
    if not event_peril:
        return []
    candidates = tranches_by_peril.get(event_peril, [])
    if not candidates:
        return []

    selected: list[dict] = []
    seen: set[str] = set()
    for tranche in candidates:
        tranche_id = str(tranche.get("tranche_id") or "")
        if tranche_id and tranche_id in seen:
            continue
        if not _event_date_overlaps_tranche_window(tranche, event):
            continue
        if not _regions_could_overlap(tranche, event):
            continue
        selected.append(tranche)
        if tranche_id:
            seen.add(tranche_id)
    return selected


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
        if not existing.get("source_url") and event.get("source_url"):
            existing["source_url"] = event.get("source_url")
        if not existing.get("source_record_id") and event.get("source_record_id"):
            existing["source_record_id"] = event.get("source_record_id")
        if existing.get("event_latitude") is None and event.get("event_latitude") is not None:
            existing["event_latitude"] = event.get("event_latitude")
        if existing.get("event_longitude") is None and event.get("event_longitude") is not None:
            existing["event_longitude"] = event.get("event_longitude")
        existing["event_bbox"] = _merge_event_bbox(existing.get("event_bbox"), event.get("event_bbox"))
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
    tranches_by_peril = _build_tranche_peril_index(candidate_tranches)

    matches = []
    for event in events:
        for tranche in _candidate_tranches_for_event(event, tranches_by_peril):
            match = build_match(tranche=tranche, event=event, generated_at=settings.as_of_timestamp)
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
