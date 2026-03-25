from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..config import Settings
from ..http import build_session, request_json
from ..utils import extract_region_codes, utcnow_iso, write_records_bundle

USGS_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query.geojson"


def flatten_feature(feature: dict) -> dict:
    props = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    coords = geometry.get("coordinates", [None, None, None])
    place = props.get("place") or ""
    region_codes = extract_region_codes(place or props.get("title"))
    peril_code = "ca_earthquake" if "california" in region_codes or "california" in place.lower() else "earthquake"
    return {
        "source_name": "usgs",
        "source_event_id": feature.get("id"),
        "event_name": place or props.get("title"),
        "peril_code": peril_code,
        "magnitude": props.get("mag"),
        "severity": props.get("alert"),
        "start_time": datetime.fromtimestamp(props["time"] / 1000, tz=UTC).isoformat() if props.get("time") else None,
        "end_time": None,
        "latitude": coords[1],
        "longitude": coords[0],
        "depth_km": coords[2] if len(coords) > 2 else None,
        "region_codes": region_codes,
        "source_url": props.get("url"),
        "geometry_json": geometry,
        "retrieved_at": utcnow_iso(),
    }


def fetch_usgs_events(settings: Settings, days: int = 14, min_magnitude: float = 5.5) -> list[dict]:
    session = build_session(settings)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    payload = request_json(
        session,
        USGS_QUERY_URL,
        settings,
        params={
            "format": "geojson",
            "starttime": start.date().isoformat(),
            "endtime": end.date().isoformat(),
            "minmagnitude": min_magnitude,
            "orderby": "time",
        },
    )
    rows = [flatten_feature(feature) for feature in payload.get("features", [])]
    write_records_bundle(settings.processed_dir / "usgs" / "events", rows)
    return rows
