from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Keep behavior consistent with the rest of this repo: allow configuring via root `.env`.
load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    host: str = os.getenv("WDM_HOST", "0.0.0.0")
    port: int = int(os.getenv("WDM_PORT", "8010"))

    browser_type: str = os.getenv("WDM_BROWSER", "chromium")  # chromium|firefox|webkit
    headless: bool = _get_bool("WDM_HEADLESS", False)
    browser_channel: str | None = os.getenv("WDM_BROWSER_CHANNEL") or None
    user_data_dir: str = os.getenv("WDM_USER_DATA_DIR", str((Path(__file__).resolve().parents[2] / "db" / "user_data" / "web_driver_monitor_profile").resolve()))
    browser_profile_directory: str | None = os.getenv("WDM_BROWSER_PROFILE_DIR") or None
    storage_state_path: str | None = os.getenv("WDM_STORAGE_STATE_PATH") or None

    # Default per-action timeout, used by watchdogs when payload omits it.
    default_timeout_ms: int = int(os.getenv("WDM_DEFAULT_TIMEOUT_MS", "25000"))

    # When clients submit with wait=true, this bounds how long the HTTP request waits.
    submit_wait_timeout_ms: int = int(os.getenv("WDM_SUBMIT_WAIT_TIMEOUT_MS", "60000"))

    # Snapshot settings appended to every successful result.
    snapshot_dom_limit: int = int(os.getenv("WDM_SNAPSHOT_DOM_LIMIT", "200"))
    snapshot_full_page: bool = _get_bool("WDM_SNAPSHOT_FULL_PAGE", False)
    snapshot_image_type: str = os.getenv("WDM_SNAPSHOT_IMAGE_TYPE", "jpeg")  # png|jpeg
    snapshot_jpeg_quality: int = int(os.getenv("WDM_SNAPSHOT_JPEG_QUALITY", "60"))


settings = Settings()
