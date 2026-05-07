import asyncio
import os

import uvicorn
from agno.utils.log import log_info


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


if __name__ == '__main__':
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8005"))
    reload_enabled = _get_bool_env("UVICORN_RELOAD", False)
    log_level = os.getenv("UVICORN_LOG_LEVEL", "info")

    log_info(f"准备启动主应用，监听地址: {host}:{port}")
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=log_level,
        access_log=True,
    )
