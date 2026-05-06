from __future__ import annotations

import json

from agno.run import RunContext
from agno.tools import Toolkit
from agno.tools.function import ToolResult

from config.office_config import build_office_output_path


def _resolve_output_path(file_name: str, run_context: RunContext | None) -> str:
    if run_context is not None:
        session_state = getattr(run_context, "session_state", {}) or {}
        workspace = session_state.get("workspace")
        if workspace:
            from pathlib import Path

            safe_name = Path(file_name).name or "office_output.md"
            if not safe_name.lower().endswith(".md"):
                safe_name = f"{safe_name}.md"
            return str((Path(workspace) / safe_name).resolve())
    return str(build_office_output_path(file_name, "md"))


class OfficeMarkdownToolkit(Toolkit):
    def __init__(self) -> None:
        super().__init__(
            name="office_markdown_toolkit",
            tools=[self.save_markdown],
        )

    def save_markdown(
        self,
        file_name: str,
        content: str,
        *,
        run_context: RunContext | None = None,
    ) -> ToolResult:
        """
        Save markdown content into the env-backed office output directory or current workspace.
        """
        from pathlib import Path

        output_path = Path(_resolve_output_path(file_name, run_context))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content or "", encoding="utf-8")
        return ToolResult(
            content=json.dumps(
                {"status": True, "urls": [str(output_path)]},
                ensure_ascii=False,
            )
        )
