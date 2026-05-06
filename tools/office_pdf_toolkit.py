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

            safe_name = Path(file_name).name or "office_output.pdf"
            if not safe_name.lower().endswith(".pdf"):
                safe_name = f"{safe_name}.pdf"
            return str((Path(workspace) / safe_name).resolve())
    return str(build_office_output_path(file_name, "pdf"))


class OfficePdfToolkit(Toolkit):
    def __init__(self) -> None:
        super().__init__(
            name="office_pdf_toolkit",
            tools=[self.generate_base_pdf],
        )

    def generate_base_pdf(
        self,
        file_name: str,
        content: str,
        title: str | None = None,
        *,
        run_context: RunContext | None = None,
    ) -> ToolResult:
        """
        Generate a basic PDF document in the env-backed office output directory or current workspace.
        """
        from pathlib import Path

        output_path = Path(_resolve_output_path(file_name, run_context))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas

        pdf = canvas.Canvas(str(output_path), pagesize=A4)
        width, height = A4
        y = height - 72

        if title:
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(72, y, title[:120])
            y -= 28

        pdf.setFont("Helvetica", 11)
        lines = []
        for paragraph in (content or "").splitlines() or [""]:
            paragraph = paragraph or " "
            lines.extend(simpleSplit(paragraph, "Helvetica", 11, width - 144))
            lines.append("")

        for line in lines:
            if y < 72:
                pdf.showPage()
                pdf.setFont("Helvetica", 11)
                y = height - 72
            pdf.drawString(72, y, line[:160])
            y -= 16

        pdf.save()
        return ToolResult(
            content=json.dumps(
                {"status": True, "urls": [str(output_path)]},
                ensure_ascii=False,
            )
        )
