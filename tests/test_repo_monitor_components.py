from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.repo_monitor_mcp.scheduler import RepoMonitorScheduler
from server.repo_monitor_mcp.storage import RepoMonitorStorage


class RepoMonitorStorageTests(unittest.TestCase):
    def test_storage_can_create_repo_and_logs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            storage = RepoMonitorStorage(db_path=str(Path(tmpdir) / "repo_monitor.db"))
            repo = storage.create_repo(
                repo_url="https://github.com/octo/demo.git",
                repo_type="github",
                repo_owner="octo",
                repo_name="demo",
                local_path=str(Path(tmpdir) / "repos" / "octo" / "demo"),
                monitor_interval=3600,
            )
            storage.add_sync_history(
                repo_config_id=repo["id"],
                sync_time="2026-03-31T00:00:00+00:00",
                status="success",
            )
            storage.add_change_log(
                repo_config_id=repo["id"],
                sync_time="2026-03-31T00:00:00+00:00",
                commit_hash="abc123",
                files_added=1,
                files_modified=2,
                files_deleted=0,
                commit_count=1,
                summary="demo summary",
                full_report={"ok": True},
            )

            repos = storage.list_repos()
            logs = storage.list_change_logs(repo["id"])

        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["repo_name"], "demo")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["summary"], "demo summary")


class RepoMonitorSchedulerTests(unittest.TestCase):
    def test_refresh_jobs_only_keeps_enabled_repos(self) -> None:
        with TemporaryDirectory() as tmpdir:
            storage = RepoMonitorStorage(db_path=str(Path(tmpdir) / "repo_monitor.db"))
            enabled_repo = storage.create_repo(
                repo_url="https://github.com/octo/demo.git",
                repo_type="github",
                repo_owner="octo",
                repo_name="demo",
                local_path=str(Path(tmpdir) / "repos" / "octo" / "demo"),
                monitor_interval=120,
                is_enabled=True,
            )
            disabled_repo = storage.create_repo(
                repo_url="https://github.com/octo/disabled.git",
                repo_type="github",
                repo_owner="octo",
                repo_name="disabled",
                local_path=str(Path(tmpdir) / "repos" / "octo" / "disabled"),
                monitor_interval=180,
                is_enabled=False,
            )
            scheduler = RepoMonitorScheduler(storage=storage)
            try:
                scheduler.refresh_jobs()
                jobs = scheduler.scheduler.get_jobs()
            finally:
                scheduler.stop()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, enabled_repo["id"])
        self.assertNotEqual(jobs[0].id, disabled_repo["id"])


class RepoMonitorAgentRegistrationTests(unittest.TestCase):
    def test_create_repo_monitor_agent_exposes_expected_tools(self) -> None:
        fake_agno_agent = types.ModuleType("agno.agent")
        fake_git_diff_module = types.ModuleType("tools.git_diff_toolkit")
        fake_mcp_module = types.ModuleType("tools.mcp_tools.repo_monitor_mcp_tool")

        class FakeAgent:
            def __init__(self, **kwargs) -> None:
                self.__dict__.update(kwargs)

        class FakeGitDiffToolkit:
            pass

        class FakeRepoMonitorMcpTools:
            pass

        fake_agno_agent.Agent = FakeAgent
        fake_git_diff_module.GitDiffToolkit = FakeGitDiffToolkit
        fake_mcp_module.create_repo_monitor_mcp_tools = lambda: FakeRepoMonitorMcpTools()

        with patch.dict(
            sys.modules,
            {
                "agno.agent": fake_agno_agent,
                "tools.git_diff_toolkit": fake_git_diff_module,
                "tools.mcp_tools.repo_monitor_mcp_tool": fake_mcp_module,
            },
            clear=False,
        ):
            sys.modules.pop("agent.repo_monitor_agent", None)
            from agent.repo_monitor_agent import create_repo_monitor_agent

        agent = create_repo_monitor_agent("repo_monitor_agent")
        self.assertEqual(agent.id, "repo_monitor_agent")
        self.assertEqual(agent.name, "Repo Monitor Agent")
        self.assertEqual(len(agent.tools), 2)
        self.assertIn("监控", agent.description)

    def test_create_desktop_control_agent_exposes_expected_tools(self) -> None:
        fake_agno_agent = types.ModuleType("agno.agent")
        fake_mcp_module = types.ModuleType("tools.mcp_tools.computer_mcp_tool")

        class FakeAgent:
            def __init__(self, **kwargs) -> None:
                self.__dict__.update(kwargs)

        class FakeComputerTools:
            pass

        fake_agno_agent.Agent = FakeAgent
        fake_mcp_module.create_computer_mcp_tools = lambda: FakeComputerTools()

        with patch.dict(
            sys.modules,
            {
                "agno.agent": fake_agno_agent,
                "tools.mcp_tools.computer_mcp_tool": fake_mcp_module,
            },
            clear=False,
        ):
            sys.modules.pop("agent.desktop_control_agent", None)
            from agent.desktop_control_agent import create_desktop_control_agent

        agent = create_desktop_control_agent("desktop_control_agent")
        self.assertEqual(agent.id, "desktop_control_agent")
        self.assertEqual(agent.name, "Desktop Control Agent")
        self.assertEqual(len(agent.tools), 1)
        self.assertIn("桌面", "".join(agent.instructions))

    def test_init_agent_registers_new_agents(self) -> None:
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
                "agent.desktop_control_agent": _module("create_desktop_control_agent"),
                "agent.github_reader_agent": _module("create_github_reader_agent"),
                "agent.repo_monitor_agent": _module("create_repo_monitor_agent"),
                "agent.academic_agent": _module("create_academic_agent"),
                "agent_manage.read_agent": fake_read_agent,
                "api.utils": fake_utils,
            },
            clear=False,
        ):
            sys.modules.pop("api.init_agent", None)
            init_agent = importlib.import_module("api.init_agent")

        agent_ids = [agent.id for agent in init_agent.all_agents]
        self.assertIn("desktop_control_agent", agent_ids)
        self.assertIn("repo_monitor_agent", agent_ids)


if __name__ == "__main__":
    unittest.main()
