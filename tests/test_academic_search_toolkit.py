from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

agno_pkg = types.ModuleType("agno")
agno_tools_pkg = types.ModuleType("agno.tools")
agno_tools_function_pkg = types.ModuleType("agno.tools.function")
httpx_pkg = types.ModuleType("httpx")


class _FakeToolkit:
    def __init__(self, name: str | None = None, tools: list | None = None, **_: object) -> None:
        self.name = name
        self.tools = tools or []


class _FakeToolResult:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, *, text: str = "", json_data: dict | None = None, content: bytes | None = None) -> None:
        self.text = text
        self._json_data = json_data or {}
        self.content = content if content is not None else text.encode("utf-8")

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_data


agno_tools_pkg.Toolkit = _FakeToolkit
agno_tools_function_pkg.ToolResult = _FakeToolResult
httpx_pkg.get = lambda *args, **kwargs: None

sys.modules.setdefault("agno", agno_pkg)
sys.modules.setdefault("agno.tools", agno_tools_pkg)
sys.modules.setdefault("agno.tools.function", agno_tools_function_pkg)
sys.modules.setdefault("httpx", httpx_pkg)

from tools.academic_search_toolkit import AcademicSearchToolkit

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <updated>2025-01-02T00:00:00Z</updated>
    <published>2025-01-01T00:00:00Z</published>
    <title>Graph Reasoning for Agents</title>
    <summary>Structured reasoning over graphs.</summary>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <arxiv:primary_category term="cs.AI" />
    <category term="cs.AI" />
    <category term="cs.LG" />
    <link rel="alternate" type="text/html" href="http://arxiv.org/abs/2501.00001v1" />
    <link title="pdf" rel="related" type="application/pdf" href="http://arxiv.org/pdf/2501.00001v1" />
  </entry>
</feed>
"""


class AcademicSearchToolkitTests(unittest.TestCase):
    def test_toolkit_exposes_reference_tool_methods(self) -> None:
        toolkit = AcademicSearchToolkit()
        tool_names = {tool.__name__ for tool in toolkit.tools}

        self.assertIn("duckduckgo_search", tool_names)
        self.assertIn("baidu_search", tool_names)
        self.assertIn("search_csdn_articles", tool_names)
        self.assertIn("read_url", tool_names)
        self.assertIn("search_github_repositories", tool_names)
        self.assertIn("get_youtube_video_data", tool_names)
        self.assertIn("arxiv_search", tool_names)
        self.assertIn("search_semantic_scholar", tool_names)

    def test_search_arxiv_returns_structured_papers(self) -> None:
        toolkit = AcademicSearchToolkit()

        with patch.object(toolkit, "_requests_get", return_value=_FakeResponse(text=ARXIV_XML)):
            result = toolkit.arxiv_search("graph reasoning", num_articles=1)

        payload = json.loads(result.content)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["source"], "arxiv")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["papers"][0]["title"], "Graph Reasoning for Agents")
        self.assertEqual(payload["papers"][0]["authors"], ["Alice", "Bob"])
        self.assertEqual(payload["papers"][0]["pdf_url"], "http://arxiv.org/pdf/2501.00001v1")

    def test_search_semantic_scholar_normalizes_response(self) -> None:
        toolkit = AcademicSearchToolkit()
        api_payload = {
            "data": [
                {
                    "paperId": "paper-1",
                    "title": "Agentic Retrieval",
                    "authors": [{"name": "Carol"}],
                    "year": 2024,
                    "publicationDate": "2024-06-01",
                    "venue": "ICML",
                    "abstract": "A paper about retrieval.",
                    "isOpenAccess": True,
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                    "tldr": {"text": "Short summary"},
                    "citationCount": 11,
                    "influentialCitationCount": 3,
                    "externalIds": {"DOI": "10.1000/test"},
                }
            ]
        }

        with patch.object(toolkit, "_requests_get", return_value=_FakeResponse(json_data=api_payload)):
            result = toolkit.search_semantic_scholar(
                "agent retrieval",
                year_start=2024,
                year_end=2024,
                num_results=1,
            )

        payload = json.loads(result.content)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["source"], "semantic_scholar")
        self.assertEqual(payload["filters"]["year_range"], [2024, 2024])
        self.assertEqual(payload["papers"][0]["title"], "Agentic Retrieval")
        self.assertEqual(payload["papers"][0]["authors"], ["Carol"])
        self.assertEqual(payload["papers"][0]["pdf_url"], "https://example.com/paper.pdf")
        self.assertEqual(payload["papers"][0]["entry_id"], "https://doi.org/10.1000/test")


if __name__ == "__main__":
    unittest.main()
