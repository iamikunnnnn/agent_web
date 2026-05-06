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


class OfficeMainEntrypointTests(unittest.TestCase):
    def test_office_main_registers_office_team_only(self) -> None:
        fake_team = object()

        fake_init_team = types.ModuleType("api.init_team")
        fake_init_team.office_team = fake_team

        fake_agent_os_ctor = Mock()

        class FakeAgentOS:
            def __init__(self, **kwargs) -> None:
                fake_agent_os_ctor(**kwargs)

            def get_app(self):
                return object()

            def serve(self, **kwargs) -> None:
                self.serve_kwargs = kwargs

        fake_agno_os = types.ModuleType("agno.os")
        fake_agno_os.AgentOS = FakeAgentOS

        fake_office_config = types.ModuleType("config.office_config")
        fake_office_config.get_office_main_settings = Mock(
            return_value={"host": "127.0.0.1", "port": 7788, "reload": False}
        )

        with patch.dict(
            sys.modules,
            {
                "api.init_team": fake_init_team,
                "agno.os": fake_agno_os,
                "config.office_config": fake_office_config,
            },
            clear=False,
        ):
            sys.modules.pop("office_main", None)
            module_globals = runpy.run_module("office_main", run_name="office_main")

        fake_agent_os_ctor.assert_called_once()
        self.assertEqual(fake_agent_os_ctor.call_args.kwargs["teams"], [fake_team])
        self.assertIn("app", module_globals)


if __name__ == "__main__":
    unittest.main()
