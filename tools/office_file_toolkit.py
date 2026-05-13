from __future__ import annotations

import json
from pathlib import Path

from agno.run import RunContext
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
                self.upload_to_storage,
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

    def upload_to_storage(
        self,
        file_path: str,
        user_id: str,
        filename: str = "",
        *,
        run_context: RunContext | None = None,
    ) -> ToolResult:
        """
        Upload an office output file to Qiniu cloud storage.

        Args:
            file_path: Local path to the file to upload
            user_id: User ID for organizing storage path
            filename: Custom filename (defaults to original file name)
            run_context: Run context for resolving session data

        Returns:
            JSON with the remote URL and upload status
        """
        from pathlib import Path

        # Resolve user_id from context if not provided
        if not user_id and run_context:
            session_state = getattr(run_context, "session_state", {}) or {}
            user_id = session_state.get("user_id") or session_state.get("sub", "anonymous")

        # Resolve file path
        local_path = Path(file_path).expanduser().resolve()
        if not local_path.exists():
            return ToolResult(
                content=json.dumps(
                    {"success": False, "error": f"File not found: {file_path}"},
                    ensure_ascii=False,
                )
            )

        # Use provided filename or original
        upload_filename = filename if filename else local_path.name

        try:
            from storage import get_qiniu_storage

            storage = get_qiniu_storage()
            remote_url = storage.upload_file(
                module="office",
                user_id=user_id,
                file_path=local_path,
                filename=upload_filename,
            )

            return ToolResult(
                content=json.dumps(
                    {
                        "success": True,
                        "local_path": str(local_path),
                        "remote_url": remote_url,
                        "filename": upload_filename,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            return ToolResult(
                content=json.dumps(
                    {"success": False, "error": f"Upload failed: {str(e)}"},
                    ensure_ascii=False,
                )
            )
