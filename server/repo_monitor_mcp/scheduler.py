from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from server.repo_monitor_mcp.service import RepoMonitorService
from server.repo_monitor_mcp.storage import RepoMonitorStorage


class RepoMonitorScheduler:
    def __init__(
        self,
        service: RepoMonitorService | None = None,
        storage: RepoMonitorStorage | None = None,
        *,
        logger: Callable[[str], Any] | None = None,
    ) -> None:
        self.service = service or RepoMonitorService(storage=storage)
        self.storage = storage or self.service.storage
        self.logger = logger or (lambda _message: None)
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._started = False

    def start(self) -> None:
        self.refresh_jobs()
        if not self._started:
            self.scheduler.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def refresh_jobs(self) -> None:
        active_repo_ids: set[str] = set()
        for repo in self.storage.list_repos():
            if not repo.get("is_enabled"):
                continue
            repo_id = str(repo["id"])
            interval_seconds = max(int(repo.get("monitor_interval") or 60), 60)
            active_repo_ids.add(repo_id)
            self.scheduler.add_job(
                self._sync_repo_job,
                trigger="interval",
                seconds=interval_seconds,
                id=repo_id,
                replace_existing=True,
                kwargs={"repo_id": repo_id},
                max_instances=1,
                coalesce=True,
                misfire_grace_time=min(interval_seconds, 300),
            )

        for job in list(self.scheduler.get_jobs()):
            if job.id not in active_repo_ids:
                self.scheduler.remove_job(job.id)

    def _sync_repo_job(self, repo_id: str) -> None:
        try:
            self.service.sync_repo(repo_id)
        except Exception as exc:  # noqa: BLE001
            self.logger(f"repo_monitor sync failed for {repo_id}: {exc}")
