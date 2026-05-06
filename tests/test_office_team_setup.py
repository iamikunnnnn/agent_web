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


class OfficeTeamSetupTests(unittest.TestCase):
    def test_office_toolkits_expose_expected_entrypoints(self) -> None:
        toolkit_base_module = types.ModuleType("agno.tools")

        class FakeToolkit:
            def __init__(self, *, name=None, tools=None, **kwargs) -> None:
                self.name = name
                self.tools = list(tools or [])
                self.kwargs = kwargs

        toolkit_base_module.Toolkit = FakeToolkit

        function_module = types.ModuleType("agno.tools.function")

        class ToolResult:
            def __init__(self, content: str) -> None:
                self.content = content

        function_module.ToolResult = ToolResult

        run_module = types.ModuleType("agno.run")
        run_module.RunContext = object

        dotenv_module = types.ModuleType("dotenv")
        dotenv_module.load_dotenv = Mock()

        with patch.dict(
            sys.modules,
            {
                "agno.tools": toolkit_base_module,
                "agno.tools.function": function_module,
                "agno.run": run_module,
                "dotenv": dotenv_module,
            },
            clear=False,
        ):
            for name in (
                "tools.office_markdown_toolkit",
                "tools.office_pdf_toolkit",
                "tools.office_search_toolkit",
            ):
                sys.modules.pop(name, None)

            markdown_module = importlib.import_module("tools.office_markdown_toolkit")
            pdf_module = importlib.import_module("tools.office_pdf_toolkit")
            search_module = importlib.import_module("tools.office_search_toolkit")

        markdown_toolkit = markdown_module.OfficeMarkdownToolkit()
        pdf_toolkit = pdf_module.OfficePdfToolkit()
        search_toolkit = search_module.OfficeSearchToolkit()

        self.assertEqual(markdown_toolkit.name, "office_markdown_toolkit")
        self.assertEqual(pdf_toolkit.name, "office_pdf_toolkit")
        self.assertEqual(search_toolkit.name, "office_search_toolkit")
        self.assertEqual([tool.__name__ for tool in markdown_toolkit.tools], ["save_markdown"])
        self.assertEqual([tool.__name__ for tool in pdf_toolkit.tools], ["generate_base_pdf"])
        self.assertEqual(
            [tool.__name__ for tool in search_toolkit.tools],
            ["search_web", "compile_brief"],
        )

    def test_create_office_team_builds_full_office_team(self) -> None:
        fake_team_module = types.ModuleType("agno.team")

        class FakeTeam:
            def __init__(self, **kwargs) -> None:
                self.__dict__.update(kwargs)

        fake_team_module.Team = FakeTeam

        fake_search_agent = types.SimpleNamespace(name="搜索专家Agent", tools=["search-tool"])
        fake_word_agent = types.SimpleNamespace(name="Word文档专家Agent", tools=["docx-tool"])
        fake_markdown_agent = types.SimpleNamespace(name="Markdown文档专家Agent", tools=["markdown-tool"])
        fake_pdf_agent = types.SimpleNamespace(name="Pdf文档专家Agent", tools=["pdf-tool"])
        fake_file_toolkit = object()

        fake_search_module = types.ModuleType("agent.office_search_agent")
        fake_search_module.create_office_search_agent = Mock(return_value=fake_search_agent)
        fake_word_module = types.ModuleType("agent.office_word_agent")
        fake_word_module.create_office_word_agent = Mock(return_value=fake_word_agent)
        fake_markdown_module = types.ModuleType("agent.office_markdown_agent")
        fake_markdown_module.create_office_markdown_agent = Mock(return_value=fake_markdown_agent)
        fake_pdf_module = types.ModuleType("agent.office_pdf_agent")
        fake_pdf_module.create_office_pdf_agent = Mock(return_value=fake_pdf_agent)

        fake_model_config = types.ModuleType("config.model_config")
        fake_model_config.get_ai_model = Mock(return_value="fake-model")

        fake_db_config = types.ModuleType("config.db_config")
        fake_db_config.create_base_db = Mock(return_value="fake-db")

        fake_file_toolkit_module = types.ModuleType("tools.office_file_toolkit")
        fake_file_toolkit_module.OfficeFileToolkit = Mock(return_value=fake_file_toolkit)

        with patch.dict(
            sys.modules,
            {
                "agno.team": fake_team_module,
                "agent.office_search_agent": fake_search_module,
                "agent.office_word_agent": fake_word_module,
                "agent.office_markdown_agent": fake_markdown_module,
                "agent.office_pdf_agent": fake_pdf_module,
                "config.model_config": fake_model_config,
                "config.db_config": fake_db_config,
                "tools.office_file_toolkit": fake_file_toolkit_module,
            },
            clear=False,
        ):
            sys.modules.pop("team.office_team", None)
            module = importlib.import_module("team.office_team")
            team = module.create_office_team("office_team")

        self.assertEqual(team.id, "office_team")
        self.assertEqual(team.name, "办公Agent团队Leader")
        self.assertEqual(team.model, "fake-model")
        self.assertEqual(team.db, "fake-db")
        self.assertEqual(team.tools, [fake_file_toolkit])
        self.assertEqual(
            team.members,
            [
                fake_search_agent,
                fake_word_agent,
                fake_markdown_agent,
                fake_pdf_agent,
            ],
        )
        self.assertEqual(team.retries, 3)
        self.assertTrue(team.instructions)


if __name__ == "__main__":
    unittest.main()
