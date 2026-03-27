from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_USER_AGENT = "OpenCatWatch/0.1 (set OPENCATWATCH_USER_AGENT to a real contact URL or email)"


def _resolve_data_dir(workspace_root: Path) -> Path:
    data_dir_value = (os.getenv("OPENCATWATCH_DATA_DIR") or "").strip()
    if data_dir_value:
        return Path(data_dir_value).expanduser()

    shared_data_root = (os.getenv("PROJ_SHARED_DATA_ROOT") or "").strip()
    if shared_data_root:
        shared_root_path = Path(shared_data_root).expanduser()
        shared_workspace_root = shared_root_path.parent / workspace_root.name
        if workspace_root.resolve() == shared_workspace_root.resolve():
            return shared_root_path / workspace_root.name / "data"

    return Path("data")


@dataclass(slots=True)
class Settings:
    user_agent: str
    timeout_seconds: int
    polite_delay_seconds: float
    sec_max_rps: int
    data_dir: Path
    workspace_root: Path | None = None
    as_of_date: date = field(default_factory=date.today)
    http_retry_attempts: int = 3
    http_retry_backoff_seconds: float = 0.5
    http_retry_max_backoff_seconds: float = 8.0

    @property
    def project_root(self) -> Path:
        return (self.workspace_root or self.data_dir.parent).resolve()

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def manual_dir(self) -> Path:
        if self.workspace_root is None:
            return self.data_dir / "manual"
        return self.project_root / "data" / "manual"

    @property
    def dashboard_path(self) -> Path:
        return self.project_root / "apps" / "site" / "data" / "dashboard.json"

    @property
    def reports_dir(self) -> Path:
        return self.project_root / "reports"

    @property
    def as_of_timestamp(self) -> str:
        return datetime.combine(self.as_of_date, time.min, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def get_settings() -> Settings:
    load_dotenv()
    workspace_root = Path(__file__).resolve().parents[2]
    data_dir = _resolve_data_dir(workspace_root)
    as_of_date_value = (os.getenv("OPENCATWATCH_AS_OF_DATE") or "").strip()
    try:
        as_of_date = date.fromisoformat(as_of_date_value) if as_of_date_value else date.today()
    except ValueError as exc:
        raise ValueError("OPENCATWATCH_AS_OF_DATE must be YYYY-MM-DD") from exc
    return Settings(
        user_agent=os.getenv(
            "OPENCATWATCH_USER_AGENT",
            DEFAULT_USER_AGENT,
        ),
        timeout_seconds=int(os.getenv("OPENCATWATCH_TIMEOUT_SECONDS", "30")),
        polite_delay_seconds=float(os.getenv("OPENCATWATCH_POLITE_DELAY_SECONDS", "0.5")),
        sec_max_rps=int(os.getenv("OPENCATWATCH_SEC_MAX_RPS", "5")),
        data_dir=data_dir,
        workspace_root=workspace_root,
        as_of_date=as_of_date,
        http_retry_attempts=int(os.getenv("OPENCATWATCH_HTTP_RETRY_ATTEMPTS", "3")),
        http_retry_backoff_seconds=float(os.getenv("OPENCATWATCH_HTTP_RETRY_BACKOFF_SECONDS", "0.5")),
        http_retry_max_backoff_seconds=float(
            os.getenv("OPENCATWATCH_HTTP_RETRY_MAX_BACKOFF_SECONDS", "8.0")
        ),
    )
