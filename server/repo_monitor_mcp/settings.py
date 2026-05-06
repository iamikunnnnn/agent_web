from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class RepoMonitorSettings:
    db_path: str = os.getenv(
        "REPO_MONITOR_DB_PATH",
        str((Path(__file__).resolve().parents[2] / "user_cache" / "repo_monitor.db").resolve()),
    )
    clone_root: str = os.getenv(
        "REPO_CLONE_ROOT",
        str((Path(__file__).resolve().parents[2] / "user_cache" / "repos").resolve()),
    )
    default_sync_interval: int = int(os.getenv("DEFAULT_SYNC_INTERVAL", "3600"))
    max_retry_count: int = int(os.getenv("MAX_RETRY_COUNT", "3"))
    shallow_clone_depth: int = int(os.getenv("REPO_MONITOR_SHALLOW_DEPTH", "20"))
    ignore_patterns: tuple[str, ...] = (
        "__pycache__/",
        "node_modules/",
        ".git/",
        ".idea/",
        ".venv/",
    )


settings = RepoMonitorSettings()
