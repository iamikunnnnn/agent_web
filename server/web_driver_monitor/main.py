from __future__ import annotations

import uvicorn

from server.web_driver_monitor.config import settings


def main() -> None:
    uvicorn.run(
        "server.web_driver_monitor.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()

