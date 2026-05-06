from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from server.repo_monitor_mcp.settings import settings


def parse_repo_url(repo_url: str) -> dict[str, str]:
    cleaned = repo_url.strip()
    ssh_match = re.match(r"git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<name>.+?)(?:\.git)?$", cleaned)
    if ssh_match:
        host = ssh_match.group("host")
        owner = ssh_match.group("owner")
        name = ssh_match.group("name")
    else:
        parsed = urlparse(cleaned)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError(f"Unsupported repo url: {repo_url}")
        host = parsed.netloc
        owner, name = parts[0], parts[1]
    name = name.removesuffix(".git")
    repo_type = "gitee" if "gitee" in host.lower() else "github"
    return {"repo_type": repo_type, "repo_owner": owner, "repo_name": name}


def build_local_repo_path(repo_owner: str, repo_name: str) -> Path:
    root = Path(settings.clone_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    repo_dir = root / repo_owner / repo_name
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    return repo_dir


def _run_git(args: list[str], cwd: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def ensure_repo(repo_url: str, local_path: str, access_token: str | None = None) -> dict[str, Any]:
    del access_token  # token persistence is modeled, but transport injection is deferred for MVP.
    repo_path = Path(local_path)
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    cloned = False
    if not (repo_path / ".git").exists():
        clone_args = [
            "clone",
            f"--depth={settings.shallow_clone_depth}",
            repo_url,
            str(repo_path),
        ]
        _run_git(clone_args)
        cloned = True
    else:
        _run_git(["fetch", "--all", "--tags", "--prune"], cwd=str(repo_path))
        _run_git(["pull", "--ff-only"], cwd=str(repo_path))

    head = get_head_commit(str(repo_path))
    return {"local_path": str(repo_path), "cloned": cloned, "head_commit": head}


def get_head_commit(repo_path: str) -> str:
    return _run_git(["rev-parse", "HEAD"], cwd=repo_path)


def get_recent_commits(repo_path: str, previous_commit: str | None, current_commit: str) -> list[dict[str, str]]:
    if previous_commit and previous_commit != current_commit:
        revspec = f"{previous_commit}..{current_commit}"
    else:
        revspec = current_commit
    output = _run_git(["log", "--format=%H%x1f%an%x1f%s", revspec], cwd=repo_path)
    commits: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        commit_hash, author, subject = (parts + ["", ""])[:3]
        commits.append({"commit_hash": commit_hash, "author": author, "subject": subject})
    return commits


def get_diff_name_status(repo_path: str, previous_commit: str | None, current_commit: str) -> list[dict[str, str]]:
    if previous_commit and previous_commit != current_commit:
        revspec = [previous_commit, current_commit]
    else:
        revspec = [f"{current_commit}~1", current_commit]
    output = _run_git(["diff", "--name-status", *revspec], cwd=repo_path)
    changes: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        status, path = (line.split("\t", 1) + [""])[:2]
        changes.append({"status": status, "path": path})
    return changes
