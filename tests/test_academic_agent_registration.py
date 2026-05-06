from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class AcademicAgentRegistrationTests(unittest.TestCase):
    def test_create_academic_agent_exposes_scholar_capabilities(self) -> None:
        fake_agno_agent = types.ModuleType("agno.agent")
        fake_toolkit_module = types.ModuleType("tools.academic_search_toolkit")

        class FakeAgent:
            def __init__(self, **kwargs) -> None:
                self.__dict__.update(kwargs)

        class FakeAcademicSearchToolkit:
            pass

        fake_agno_agent.Agent = FakeAgent
        fake_toolkit_module.AcademicSearchToolkit = FakeAcademicSearchToolkit

        with patch.dict(
            sys.modules,
            {
                "agno.agent": fake_agno_agent,
                "tools.academic_search_toolkit": fake_toolkit_module,
            },
            clear=False,
        ):
            sys.modules.pop("agent.academic_agent", None)
            from agent.academic_agent import create_academic_agent

        agent = create_academic_agent("academic_agent")

        self.assertEqual(agent.id, "academic_agent")
        self.assertEqual(agent.name, "Academic Search Agent")
        self.assertIn("学术", agent.description)
        self.assertTrue(agent.instructions)
        self.assertEqual(len(agent.tools), 1)

    def test_init_agent_registers_academic_agent(self) -> None:
        fake_agno_agent = types.ModuleType("agno.agent")

        class FakeAgent:
            def __init__(self, agent_id: str) -> None:
                self.id = agent_id

        fake_agno_agent.Agent = FakeAgent

        def _fake_factory(agent_id: str) -> FakeAgent:
            return FakeAgent(agent_id)

        def _module(factory_name: str) -> types.ModuleType:
            mod = types.ModuleType(factory_name)
            setattr(mod, factory_name, _fake_factory)
            return mod

        fake_utils = types.ModuleType("api.utils")
        fake_utils.set_default_config_to_agent = Mock()

        fake_read_agent = types.ModuleType("agent_manage.read_agent")
        fake_read_agent.read_agent = Mock(return_value=[])

        with patch.dict(
            sys.modules,
            {
                "agno.agent": fake_agno_agent,
                "agent.test_agent": _module("create_test_agent"),
                "agent.test_agent_2": _module("create_test_agent_2"),
                "agent.data_agent": _module("create_data_agent"),
                "agent.docx_use_agent": _module("create_docx_use_agent"),
                "agent.github_reader_agent": _module("create_github_reader_agent"),
                "agent.academic_agent": _module("create_academic_agent"),
                "agent_manage.read_agent": fake_read_agent,
                "api.utils": fake_utils,
            },
            clear=False,
        ):
            sys.modules.pop("api.init_agent", None)
            init_agent = importlib.import_module("api.init_agent")

        self.assertIn("academic_agent", [agent.id for agent in init_agent.all_agents])


if __name__ == "__main__":
    unittest.main()
