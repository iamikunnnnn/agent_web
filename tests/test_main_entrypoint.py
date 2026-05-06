from __future__ import annotations

import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class MainEntrypointTests(unittest.TestCase):
    def test_main_can_run_without_windows_event_loop_policy(self) -> None:
        fake_asyncio = types.ModuleType("asyncio")
        fake_asyncio.set_event_loop_policy = Mock()

        fake_uvicorn = types.ModuleType("uvicorn")
        fake_uvicorn.run = Mock()

        fake_agno = types.ModuleType("agno")

        with patch.dict(
            sys.modules,
            {
                "asyncio": fake_asyncio,
                "uvicorn": fake_uvicorn,
                "agno": fake_agno,
            },
            clear=False,
        ):
            runpy.run_module("main", run_name="__main__")

        fake_asyncio.set_event_loop_policy.assert_not_called()
        fake_uvicorn.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
