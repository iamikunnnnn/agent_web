from __future__ import annotations

import json
from typing import Any

from agno.tools import Toolkit
from agno.tools.function import ToolResult


class OfficeSearchToolkit(Toolkit):
    def __init__(self) -> None:
        super().__init__(
            name="office_search_toolkit",
            tools=[self.search_web, self.compile_brief],
        )

    def _result(self, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(content=json.dumps(payload, ensure_ascii=False, indent=2))

    def search_web(self, query: str, max_results: int = 8) -> ToolResult:
        """
        Search the public web for office-research tasks and return structured results.
        """
        limit = max(1, min(int(max_results), 10))
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=limit))
            results = [
                {
                    "title": row.get("title", ""),
                    "url": row.get("href", ""),
                    "snippet": row.get("body", ""),
                }
                for row in rows
            ]
            return self._result(
                {
                    "status": True,
                    "query": query,
                    "count": len(results),
                    "results": results,
                }
            )
        except Exception as exc:
            return self._result(
                {
                    "status": False,
                    "query": query,
                    "count": 0,
                    "results": [],
                    "error": str(exc),
                }
            )

    def compile_brief(self, topic: str, search_results_json: str) -> ToolResult:
        """
        Compile a compact research brief from search results JSON returned by `search_web`.
        """
        try:
            payload = json.loads(search_results_json)
        except json.JSONDecodeError:
            payload = {"results": []}

        results = payload.get("results") or []
        highlights = []
        sources = []
        for row in results[:8]:
            title = (row.get("title") or "").strip()
            snippet = (row.get("snippet") or "").strip()
            url = (row.get("url") or "").strip()
            if title or snippet:
                highlights.append(f"{title}: {snippet}".strip(": "))
            if url:
                sources.append(url)

        return self._result(
            {
                "status": True,
                "topic": topic,
                "highlights": highlights,
                "sources": sources,
            }
        )
