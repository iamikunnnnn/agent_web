from __future__ import annotations

import atexit

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from server.repo_monitor_mcp.scheduler import RepoMonitorScheduler
from server.repo_monitor_mcp.service import RepoMonitorService

repo_monitor_service = RepoMonitorService()
repo_monitor_scheduler = RepoMonitorScheduler(service=repo_monitor_service)
repo_monitor_app = FastAPI(title="repo_monitor_mcp", version="0.1.0")


class RegisterRepoRequest(BaseModel):
    repo_url: str
    access_token: str | None = None
    monitor_interval: int | None = Field(default=None, ge=60)


class ToggleRepoRequest(BaseModel):
    enabled: bool


class SyncRepoRequest(BaseModel):
    repo_id: str


@repo_monitor_app.on_event("startup")
def startup_repo_monitor_scheduler() -> None:
    repo_monitor_scheduler.start()


@repo_monitor_app.on_event("shutdown")
def shutdown_repo_monitor_scheduler() -> None:
    repo_monitor_scheduler.stop()


atexit.register(repo_monitor_scheduler.stop)


@repo_monitor_app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "repo_monitor_mcp"}


@repo_monitor_app.post("/repo/register")
def register_repo(req: RegisterRepoRequest) -> dict:
    result = repo_monitor_service.register_repo(
        repo_url=req.repo_url,
        access_token=req.access_token,
        monitor_interval=req.monitor_interval,
    )
    repo_monitor_scheduler.refresh_jobs()
    return result


@repo_monitor_app.get("/repo/list")
def list_repos() -> list[dict]:
    return repo_monitor_service.list_repos()


@repo_monitor_app.delete("/repo/{repo_id}")
def delete_repo(repo_id: str) -> dict[str, bool]:
    deleted = repo_monitor_service.delete_repo(repo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="repo not found")
    repo_monitor_scheduler.refresh_jobs()
    return {"deleted": True}


@repo_monitor_app.post("/repo/{repo_id}/toggle")
def toggle_repo(repo_id: str, req: ToggleRepoRequest) -> dict:
    updated = repo_monitor_service.toggle_repo(repo_id, req.enabled)
    if updated is None:
        raise HTTPException(status_code=404, detail="repo not found")
    repo_monitor_scheduler.refresh_jobs()
    return updated


@repo_monitor_app.get("/repo/{repo_id}/logs")
def list_logs(repo_id: str) -> list[dict]:
    return repo_monitor_service.list_logs(repo_id)


@repo_monitor_app.post("/repo/sync")
def sync_repo(req: SyncRepoRequest) -> dict:
    try:
        return repo_monitor_service.sync_repo(req.repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


from fastmcp import FastMCP

mcp = FastMCP.from_fastapi(app=repo_monitor_app)

if __name__ == "__main__":
    import os
    import uvicorn
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8012"))
    uvicorn.run(repo_monitor_app, host=host, port=port)
