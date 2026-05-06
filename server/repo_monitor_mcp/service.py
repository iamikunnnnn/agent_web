from __future__ import annotations

from typing import Any

from server.repo_monitor_mcp.git_ops import (
    build_local_repo_path,
    ensure_repo,
    get_diff_name_status,
    get_recent_commits,
    parse_repo_url,
)
from server.repo_monitor_mcp.settings import settings
from server.repo_monitor_mcp.storage import RepoMonitorStorage, utc_now_iso


class RepoMonitorService:
    def __init__(self, storage: RepoMonitorStorage | None = None) -> None:
        self.storage = storage or RepoMonitorStorage()

    def register_repo(
        self,
        *,
        repo_url: str,
        access_token: str | None = None,
        monitor_interval: int | None = None,
    ) -> dict[str, Any]:
        parsed = parse_repo_url(repo_url)
        local_path = build_local_repo_path(parsed["repo_owner"], parsed["repo_name"])
        return self.storage.create_repo(
            repo_url=repo_url,
            repo_type=parsed["repo_type"],
            repo_owner=parsed["repo_owner"],
            repo_name=parsed["repo_name"],
            local_path=str(local_path),
            access_token=access_token,
            monitor_interval=monitor_interval or settings.default_sync_interval,
        )

    def list_repos(self) -> list[dict[str, Any]]:
        return self.storage.list_repos()

    def delete_repo(self, repo_id: str) -> bool:
        return self.storage.delete_repo(repo_id)

    def toggle_repo(self, repo_id: str, enabled: bool) -> dict[str, Any] | None:
        return self.storage.set_repo_enabled(repo_id, enabled)

    def list_logs(self, repo_id: str) -> list[dict[str, Any]]:
        return self.storage.list_change_logs(repo_id)

    def sync_repo(self, repo_id: str) -> dict[str, Any]:
        repo = self.storage.get_repo(repo_id)
        if repo is None:
            raise ValueError(f"repo not found: {repo_id}")

        sync_time = utc_now_iso()
        try:
            git_state = ensure_repo(
                repo_url=repo["repo_url"],
                local_path=repo["local_path"],
                access_token=repo.get("access_token"),
            )
            current_commit = git_state["head_commit"]
            previous_commit = repo.get("last_commit_hash")
            changes = get_diff_name_status(repo["local_path"], previous_commit, current_commit)
            commits = get_recent_commits(repo["local_path"], previous_commit, current_commit)

            files_added = sum(1 for item in changes if item["status"].startswith("A"))
            files_deleted = sum(1 for item in changes if item["status"].startswith("D"))
            files_modified = len(changes) - files_added - files_deleted

            summary = self._build_summary(repo=repo, commits=commits, changes=changes)
            report = {
                "repo": {
                    "id": repo["id"],
                    "repo_url": repo["repo_url"],
                    "repo_name": repo["repo_name"],
                    "repo_owner": repo["repo_owner"],
                },
                "sync": {
                    "sync_time": sync_time,
                    "previous_commit": previous_commit,
                    "current_commit": current_commit,
                    "cloned": git_state["cloned"],
                },
                "stats": {
                    "files_added": files_added,
                    "files_modified": files_modified,
                    "files_deleted": files_deleted,
                    "commit_count": len(commits),
                },
                "commits": commits,
                "changes": changes,
            }

            self.storage.update_sync_state(repo["id"], sync_time=sync_time, commit_hash=current_commit)
            self.storage.add_sync_history(
                repo_config_id=repo["id"],
                sync_time=sync_time,
                status="success",
                retry_count=0,
            )
            self.storage.add_change_log(
                repo_config_id=repo["id"],
                sync_time=sync_time,
                commit_hash=current_commit,
                files_added=files_added,
                files_modified=files_modified,
                files_deleted=files_deleted,
                commit_count=len(commits),
                summary=summary,
                full_report=report,
            )
            return report | {"summary": summary}
        except Exception as exc:  # noqa: BLE001
            self.storage.add_sync_history(
                repo_config_id=repo["id"],
                sync_time=sync_time,
                status="failure",
                error_message=str(exc),
                retry_count=0,
            )
            raise

    def _build_summary(
        self,
        *,
        repo: dict[str, Any],
        commits: list[dict[str, str]],
        changes: list[dict[str, str]],
    ) -> str:
        if not commits and not changes:
            return f"仓库 {repo['repo_owner']}/{repo['repo_name']} 本次同步未检测到新增变更。"

        top_commit_subjects = [item["subject"] for item in commits[:3] if item.get("subject")]
        changed_paths = [item["path"] for item in changes[:5] if item.get("path")]
        parts = [
            f"仓库 {repo['repo_owner']}/{repo['repo_name']} 本次同步检测到 {len(commits)} 个提交、{len(changes)} 个文件变更。",
        ]
        if top_commit_subjects:
            parts.append("代表性提交：" + "；".join(top_commit_subjects))
        if changed_paths:
            parts.append("重点文件：" + "、".join(changed_paths))
        return " ".join(parts)
