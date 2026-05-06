from __future__ import annotations

import json
from pathlib import Path

from agno.tools import Toolkit
from agno.tools.function import ToolResult

from config.office_config import (
    build_office_output_path,
    ensure_office_dirs,
    get_office_paths,
    resolve_office_input_path,
)


class OfficeFileToolkit(Toolkit):
    def __init__(self) -> None:
        super().__init__(
            name="office_file_toolkit",
            tools=[
                self.get_office_paths,
                self.build_output_path,
                self.resolve_input_path,
                self.file_exists,
                self.list_documents,
            ],
        )

    def get_office_paths(self) -> ToolResult:
        paths = {name: str(path) for name, path in ensure_office_dirs().items()}
        return ToolResult(content=json.dumps(paths, ensure_ascii=False, indent=2))

    def build_output_path(self, file_name: str, format: str) -> ToolResult:
        path = build_office_output_path(file_name, format)
        path.parent.mkdir(parents=True, exist_ok=True)
        return ToolResult(
            content=json.dumps({"path": str(path), "format": format}, ensure_ascii=False)
        )

    def resolve_input_path(self, file_name: str) -> ToolResult:
        path = resolve_office_input_path(file_name)
        return ToolResult(
            content=json.dumps(
                {"path": str(path), "exists": path.exists()},
                ensure_ascii=False,
            )
        )

    def file_exists(self, path: str) -> ToolResult:
        resolved = Path(path).expanduser().resolve()
        return ToolResult(
            content=json.dumps(
                {
                    "path": str(resolved),
                    "exists": resolved.exists(),
                    "is_file": resolved.is_file(),
                },
                ensure_ascii=False,
            )
        )

    def list_documents(self, format: str = "", scope: str = "output") -> ToolResult:
        paths = get_office_paths()
        if scope == "input":
            root = paths["input_dir"]
        else:
            root = paths["output_dir"]

        ext = format.lower().strip()
        if ext and not ext.startswith("."):
            ext = f".{ext}"

        files = []
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file() and (not ext or path.suffix.lower() == ext):
                    files.append(str(path.resolve()))
        return ToolResult(
            content=json.dumps(
                {"root": str(root), "count": len(files), "files": files},
                ensure_ascii=False,
                indent=2,
            )
        )
