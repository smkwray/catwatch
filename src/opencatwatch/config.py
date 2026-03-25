from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_USER_AGENT = "OpenCatWatch/0.1 (set OPENCATWATCH_USER_AGENT to a real contact URL or email)"


@dataclass(slots=True)
class Settings:
    user_agent: str
    timeout_seconds: int
    polite_delay_seconds: float
    sec_max_rps: int
    data_dir: Path
    http_retry_attempts: int = 3
    http_retry_backoff_seconds: float = 0.5
    http_retry_max_backoff_seconds: float = 8.0

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def manual_dir(self) -> Path:
        return self.data_dir / "manual"


def get_settings() -> Settings:
    load_dotenv()
    data_dir = Path(os.getenv("OPENCATWATCH_DATA_DIR", "data"))
    return Settings(
        user_agent=os.getenv(
            "OPENCATWATCH_USER_AGENT",
            DEFAULT_USER_AGENT,
        ),
        timeout_seconds=int(os.getenv("OPENCATWATCH_TIMEOUT_SECONDS", "30")),
        polite_delay_seconds=float(os.getenv("OPENCATWATCH_POLITE_DELAY_SECONDS", "0.5")),
        sec_max_rps=int(os.getenv("OPENCATWATCH_SEC_MAX_RPS", "5")),
        data_dir=data_dir,
        http_retry_attempts=int(os.getenv("OPENCATWATCH_HTTP_RETRY_ATTEMPTS", "3")),
        http_retry_backoff_seconds=float(os.getenv("OPENCATWATCH_HTTP_RETRY_BACKOFF_SECONDS", "0.5")),
        http_retry_max_backoff_seconds=float(
            os.getenv("OPENCATWATCH_HTTP_RETRY_MAX_BACKOFF_SECONDS", "8.0")
        ),
    )
