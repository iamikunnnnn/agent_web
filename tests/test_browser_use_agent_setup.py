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


class BrowserUseAgentSetupTests(unittest.TestCase):
    def test_create_browser_use_agent_uses_direct_tools_and_session_state_context(self) -> None:
        fake_agno_agent = types.ModuleType("agno.agent")
        fake_agno_skills = types.ModuleType("agno.skills")
        fake_browser_tool_module = types.ModuleType("tools.browser_use_tool")
        fake_wdm_toolkit_module = types.ModuleType("tools.web_driver_monitor_toolkit")

        class FakeAgent:
            def __init__(self, **kwargs) -> None:
                self.__dict__.update(kwargs)

        class FakeLocalSkills:
            def __init__(self, path: str) -> None:
                self.path = path

        class FakeSkills:
            def __init__(self, loaders) -> None:  # noqa: ANN001
                self.loaders = loaders

        class FakeToolkit:
            pass

        def fake_clear_browser_transient_state(**kwargs) -> None:  # noqa: ANN003
            return None

        fake_agno_agent.Agent = FakeAgent
        fake_agno_skills.LocalSkills = FakeLocalSkills
        fake_agno_skills.Skills = FakeSkills
        fake_browser_tool_module.browser_use_tool = object()
        fake_wdm_toolkit_module.webDriverMonitorToolkit = FakeToolkit
        fake_wdm_toolkit_module.clear_browser_transient_state = fake_clear_browser_transient_state

        with patch.dict(
            sys.modules,
            {
                "agno.agent": fake_agno_agent,
                "agno.skills": fake_agno_skills,
                "tools.browser_use_tool": fake_browser_tool_module,
                "tools.web_driver_monitor_toolkit": fake_wdm_toolkit_module,
            },
            clear=False,
        ):
            sys.modules.pop("agent.browser_use_agent", None)
            from agent.browser_use_agent import create_browser_use_agent

        agent = create_browser_use_agent("browser_use_agent")

        self.assertEqual(agent.id, "browser_use_agent")
        self.assertEqual(agent.name, "browser use agent")
        self.assertEqual(len(agent.tools), 1)
        self.assertIsInstance(agent.tools[0], FakeToolkit)
        self.assertTrue(agent.add_session_state_to_context)
        self.assertEqual(len(agent.pre_hooks), 1)

    def test_init_agent_registers_browser_use_agent(self) -> None:
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
                "agent.browser_use_agent": _module("create_browser_use_agent"),
                "agent.github_reader_agent": _module("create_github_reader_agent"),
                "agent.academic_agent": _module("create_academic_agent"),
                "agent_manage.read_agent": fake_read_agent,
                "api.utils": fake_utils,
            },
            clear=False,
        ):
            sys.modules.pop("api.init_agent", None)
            init_agent = importlib.import_module("api.init_agent")

        self.assertIn("browser_use_agent", [agent.id for agent in init_agent.all_agents])

    def test_init_workflow_no_longer_registers_browser_use_workflow(self) -> None:
        fake_workflow_module = types.ModuleType("workflow.browser_workflow")
        fake_workflow_module.create_browser_workflow = Mock(return_value=object())

        with patch.dict(sys.modules, {"workflow.browser_workflow": fake_workflow_module}, clear=False):
            sys.modules.pop("api.init_workflow", None)
            init_workflow = importlib.import_module("api.init_workflow")

        self.assertEqual(init_workflow.all_workflows, [])
        fake_workflow_module.create_browser_workflow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
