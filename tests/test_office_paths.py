from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class OfficePathsTests(unittest.TestCase):
    def test_markdown_toolkit_uses_env_output_dir_without_workspace(self) -> None:
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

        tmp = ROOT / "tmp" / "test_office_paths_markdown"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        env = {
            "OFFICE_OUTPUT_DIR": str(tmp / "office-output"),
            "OFFICE_MARKDOWN_OUTPUT_DIR": str(tmp / "office-output" / "md"),
        }
        with patch.dict(os.environ, env, clear=False), patch.dict(
            sys.modules,
            {
                "agno.tools": toolkit_base_module,
                "agno.tools.function": function_module,
                "agno.run": run_module,
                "dotenv": dotenv_module,
            },
            clear=False,
        ):
            for name in ("config.office_config", "tools.office_markdown_toolkit"):
                sys.modules.pop(name, None)
            markdown_module = importlib.import_module("tools.office_markdown_toolkit")
            toolkit = markdown_module.OfficeMarkdownToolkit()
            result = toolkit.save_markdown("weekly-report", "# report")

        payload = json.loads(result.content)
        output_path = Path(payload["urls"][0])
        self.assertEqual(output_path, Path(env["OFFICE_MARKDOWN_OUTPUT_DIR"]) / "weekly-report.md")
        self.assertTrue(output_path.exists())

    def test_office_file_toolkit_builds_env_backed_paths(self) -> None:
        toolkit_base_module = types.ModuleType("agno.tools")

        class FakeToolkit:
            def __init__(self, *, name=None, tools=None, **kwargs) -> None:
                self.name = name
                self.tools = list(tools or [])

        toolkit_base_module.Toolkit = FakeToolkit

        function_module = types.ModuleType("agno.tools.function")

        class ToolResult:
            def __init__(self, content: str) -> None:
                self.content = content

        function_module.ToolResult = ToolResult

        dotenv_module = types.ModuleType("dotenv")
        dotenv_module.load_dotenv = Mock()

        tmp = ROOT / "tmp" / "test_office_paths_file_toolkit"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        env = {
            "OFFICE_INPUT_DIR": str(tmp / "inputs"),
            "OFFICE_DOCX_OUTPUT_DIR": str(tmp / "outputs" / "docx"),
        }
        with patch.dict(os.environ, env, clear=False), patch.dict(
            sys.modules,
            {
                "agno.tools": toolkit_base_module,
                "agno.tools.function": function_module,
                "dotenv": dotenv_module,
            },
            clear=False,
        ):
            for name in ("config.office_config", "tools.office_file_toolkit"):
                sys.modules.pop(name, None)
            module = importlib.import_module("tools.office_file_toolkit")
            toolkit = module.OfficeFileToolkit()
            result = toolkit.build_output_path("contract-review", "docx")
            payload = json.loads(result.content)

        self.assertEqual(
            payload["path"],
            str(Path(env["OFFICE_DOCX_OUTPUT_DIR"]) / "contract-review.docx"),
        )


if __name__ == "__main__":
    unittest.main()
