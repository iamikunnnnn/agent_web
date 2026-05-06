from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agno.tools import Toolkit

from server.repo_monitor_mcp.git_ops import get_diff_name_status, get_recent_commits
from server.repo_monitor_mcp.settings import settings


class GitDiffToolkit(Toolkit):
    def __init__(self) -> None:
        super().__init__(
            name="git_diff_tools",
            tools=[
                self.get_commits_between,
                self.get_diff_summary,
                self.get_file_changes,
                self.analyze_change_impact,
            ],
        )

    def _string_result(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _normalize_repo_path(self, repo_path: str) -> str:
        path = Path(repo_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"repo_path not found: {repo_path}")
        return str(path)

    def _classify_path(self, path: str) -> str:
        normalized = path.replace('\\', '/')
        if any(pattern in normalized for pattern in settings.ignore_patterns):
            return "ignored"
        if normalized.endswith((".md", ".rst", ".txt")):
            return "docs"
        if normalized.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".env")):
            return "config"
        if normalized.endswith((".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs", ".cpp", ".c", ".h")):
            return "code"
        return "other"

    def get_commits_between(self, repo_path: str, since: str | None = None, until: str | None = None) -> str:
        normalized_repo = self._normalize_repo_path(repo_path)
        current_commit = until or "HEAD"
        commits = get_recent_commits(normalized_repo, since, current_commit)
        return self._string_result({"repo_path": normalized_repo, "commits": commits})

    def get_diff_summary(self, repo_path: str, since: str | None = None, until: str | None = None) -> str:
        normalized_repo = self._normalize_repo_path(repo_path)
        current_commit = until or "HEAD"
        changes = get_diff_name_status(normalized_repo, since, current_commit)
        stats = {"added": 0, "modified": 0, "deleted": 0, "by_category": {}}
        for change in changes:
            status = change.get("status", "")
            category = self._classify_path(change.get("path", ""))
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
            if status.startswith("A"):
                stats["added"] += 1
            elif status.startswith("D"):
                stats["deleted"] += 1
            else:
                stats["modified"] += 1
        return self._string_result({"repo_path": normalized_repo, "since": since, "until": current_commit, "stats": stats})

    def get_file_changes(self, repo_path: str, since: str | None = None, until: str | None = None) -> str:
        normalized_repo = self._normalize_repo_path(repo_path)
        current_commit = until or "HEAD"
        changes = get_diff_name_status(normalized_repo, since, current_commit)
        enriched = [change | {"category": self._classify_path(change.get("path", ""))} for change in changes]
        return self._string_result({"repo_path": normalized_repo, "changes": enriched})

    def analyze_change_impact(self, repo_path: str, commit_hash: str) -> str:
        normalized_repo = self._normalize_repo_path(repo_path)
        changes = get_diff_name_status(normalized_repo, f"{commit_hash}~1", commit_hash)
        categories: dict[str, int] = {}
        for change in changes:
            category = self._classify_path(change.get("path", ""))
            categories[category] = categories.get(category, 0) + 1
        risk_level = "low"
        if categories.get("code", 0) >= 10:
            risk_level = "high"
        elif categories.get("code", 0) >= 3 or categories.get("config", 0) >= 1:
            risk_level = "medium"
        return self._string_result(
            {
                "repo_path": normalized_repo,
                "commit_hash": commit_hash,
                "impact": {
                    "categories": categories,
                    "risk_level": risk_level,
                    "reason": "基于代码/配置文件变更数量的启发式估计。",
                },
            }
        )
