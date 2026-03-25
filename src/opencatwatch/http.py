from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

from .config import Settings

_INVALID_USER_AGENT_MARKERS = {
    "you@example.com",
    "research project",
    "set opencatwatch_user_agent",
}


def _validate_live_user_agent(user_agent: str) -> None:
    normalized = (user_agent or "").strip().lower()
    if not normalized or any(marker in normalized for marker in _INVALID_USER_AGENT_MARKERS):
        raise ValueError(
            "OPENCATWATCH_USER_AGENT must include a real operator contact URL or email before live fetches."
        )


def build_session(settings: Settings) -> requests.Session:
    _validate_live_user_agent(settings.user_agent)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": settings.user_agent,
            "Accept": "*/*",
        }
    )
    return session


def polite_pause(settings: Settings) -> None:
    if settings.polite_delay_seconds > 0:
        time.sleep(settings.polite_delay_seconds)


def _retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _sleep_backoff(settings: Settings, attempt_number: int) -> None:
    delay = settings.http_retry_backoff_seconds * (2 ** max(0, attempt_number - 1))
    time.sleep(min(delay, settings.http_retry_max_backoff_seconds))


def _request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    settings: Settings,
    **kwargs: Any,
) -> requests.Response:
    attempts = max(1, settings.http_retry_attempts)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = session.request(method, url, timeout=settings.timeout_seconds, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            _sleep_backoff(settings, attempt)
            continue

        if _retryable_status(response.status_code):
            if attempt >= attempts:
                response.close()
                response.raise_for_status()
            response.close()
            _sleep_backoff(settings, attempt)
            continue

        response.raise_for_status()
        polite_pause(settings)
        return response

    if last_error is not None:
        raise last_error
    raise RuntimeError("request retry loop exhausted unexpectedly")


def request_text(session: requests.Session, url: str, settings: Settings) -> str:
    response = _request_with_retry(session, "GET", url, settings)
    try:
        return response.text
    finally:
        response.close()


def request_json(
    session: requests.Session,
    url: str,
    settings: Settings,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = _request_with_retry(session, "GET", url, settings, params=params or {})
    try:
        return response.json()
    finally:
        response.close()


def download_file(session: requests.Session, url: str, dest: Path, settings: Settings) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = _request_with_retry(session, "GET", url, settings, stream=True)
    try:
        with dest.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
    finally:
        response.close()
    return dest
