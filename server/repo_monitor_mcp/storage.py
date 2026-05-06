from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from server.repo_monitor_mcp.settings import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RepoMonitorStorage:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(Path(db_path or settings.db_path).resolve())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS repo_configs (
                    id TEXT PRIMARY KEY,
                    repo_url TEXT NOT NULL,
                    repo_type TEXT NOT NULL,
                    repo_owner TEXT NOT NULL,
                    repo_name TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    access_token TEXT,
                    monitor_interval INTEGER NOT NULL,
                    last_sync_time TEXT,
                    last_commit_hash TEXT,
                    is_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS repo_change_logs (
                    id TEXT PRIMARY KEY,
                    repo_config_id TEXT NOT NULL,
                    sync_time TEXT NOT NULL,
                    commit_hash TEXT,
                    files_added INTEGER NOT NULL DEFAULT 0,
                    files_modified INTEGER NOT NULL DEFAULT 0,
                    files_deleted INTEGER NOT NULL DEFAULT 0,
                    commit_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT,
                    full_report TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS repo_sync_history (
                    id TEXT PRIMARY KEY,
                    repo_config_id TEXT NOT NULL,
                    sync_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def list_repos(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM repo_configs ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_repo(self, repo_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM repo_configs WHERE id = ?", (repo_id,)).fetchone()
        return dict(row) if row else None

    def create_repo(
        self,
        *,
        repo_url: str,
        repo_type: str,
        repo_owner: str,
        repo_name: str,
        local_path: str,
        access_token: str | None = None,
        monitor_interval: int,
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        repo_id = str(uuid.uuid4())
        record = {
            "id": repo_id,
            "repo_url": repo_url,
            "repo_type": repo_type,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "local_path": local_path,
            "access_token": access_token,
            "monitor_interval": monitor_interval,
            "last_sync_time": None,
            "last_commit_hash": None,
            "is_enabled": 1 if is_enabled else 0,
            "created_at": now,
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO repo_configs (
                    id, repo_url, repo_type, repo_owner, repo_name, local_path,
                    access_token, monitor_interval, last_sync_time, last_commit_hash,
                    is_enabled, created_at, updated_at
                ) VALUES (
                    :id, :repo_url, :repo_type, :repo_owner, :repo_name, :local_path,
                    :access_token, :monitor_interval, :last_sync_time, :last_commit_hash,
                    :is_enabled, :created_at, :updated_at
                )
                """,
                record,
            )
        return record

    def delete_repo(self, repo_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM repo_configs WHERE id = ?", (repo_id,))
        return cursor.rowcount > 0

    def set_repo_enabled(self, repo_id: str, enabled: bool) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "UPDATE repo_configs SET is_enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, repo_id),
            )
        return self.get_repo(repo_id)

    def update_sync_state(self, repo_id: str, *, sync_time: str, commit_hash: str | None) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "UPDATE repo_configs SET last_sync_time = ?, last_commit_hash = ?, updated_at = ? WHERE id = ?",
                (sync_time, commit_hash, now, repo_id),
            )
        return self.get_repo(repo_id)

    def add_change_log(
        self,
        *,
        repo_config_id: str,
        sync_time: str,
        commit_hash: str | None,
        files_added: int,
        files_modified: int,
        files_deleted: int,
        commit_count: int,
        summary: str,
        full_report: dict[str, Any],
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "repo_config_id": repo_config_id,
            "sync_time": sync_time,
            "commit_hash": commit_hash,
            "files_added": files_added,
            "files_modified": files_modified,
            "files_deleted": files_deleted,
            "commit_count": commit_count,
            "summary": summary,
            "full_report": json.dumps(full_report, ensure_ascii=False),
            "created_at": utc_now_iso(),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO repo_change_logs (
                    id, repo_config_id, sync_time, commit_hash,
                    files_added, files_modified, files_deleted, commit_count,
                    summary, full_report, created_at
                ) VALUES (
                    :id, :repo_config_id, :sync_time, :commit_hash,
                    :files_added, :files_modified, :files_deleted, :commit_count,
                    :summary, :full_report, :created_at
                )
                """,
                record,
            )
        return record

    def list_change_logs(self, repo_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM repo_change_logs WHERE repo_config_id = ? ORDER BY sync_time DESC",
                (repo_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_sync_history(
        self,
        *,
        repo_config_id: str,
        sync_time: str,
        status: str,
        error_message: str | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "repo_config_id": repo_config_id,
            "sync_time": sync_time,
            "status": status,
            "error_message": error_message,
            "retry_count": retry_count,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO repo_sync_history (
                    id, repo_config_id, sync_time, status, error_message, retry_count
                ) VALUES (
                    :id, :repo_config_id, :sync_time, :status, :error_message, :retry_count
                )
                """,
                record,
            )
        return record
