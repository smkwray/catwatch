from __future__ import annotations

from ..config import Settings
from ..http import build_session, request_json
from ..utils import utcnow_iso, write_records_bundle

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"


def flatten_alert(feature: dict) -> dict:
    props = feature.get("properties", {})
    geometry = feature.get("geometry")
    return {
        "source_name": "nws",
        "source_event_id": props.get("id"),
        "event_name": props.get("event"),
        "headline": props.get("headline"),
        "severity": props.get("severity"),
        "urgency": props.get("urgency"),
        "certainty": props.get("certainty"),
        "area_desc": props.get("areaDesc"),
        "region_codes": props.get("geocode", {}).get("UGC", []),
        "start_time": props.get("onset") or props.get("effective"),
        "end_time": props.get("ends") or props.get("expires"),
        "source_url": props.get("@id"),
        "geometry_json": geometry,
        "retrieved_at": utcnow_iso(),
    }


def fetch_nws_alerts(settings: Settings) -> list[dict]:
    session = build_session(settings)
    payload = request_json(session, NWS_ALERTS_URL, settings)
    features = payload.get("features", [])
    rows = [flatten_alert(feature) for feature in features]
    write_records_bundle(settings.processed_dir / "nws" / "alerts_active", rows)
    return rows
