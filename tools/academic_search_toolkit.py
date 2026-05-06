"""AcademicSearchToolkit 的实现。

这个 Toolkit 是 `academic_agent` 的主要能力来源。它并不只做严格意义上的
论文检索，而是把研究资料收集过程中常用的外部来源统一包装成 Agno 工具：

- 论文库：arXiv、Semantic Scholar。
- 通用搜索/网页读取：DuckDuckGo、Baidu、Jina read/search。
- 技术资料：CSDN、GitHub 仓库与代码。
- 辅助资料：MathWorld、YouTube 元信息与字幕。

设计上保持“薄业务逻辑、厚外部适配”：每个工具负责调用一个第三方入口，
把响应压缩成结构化 JSON 或文本，再交给 Agent 做综合判断和最终表达。
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

import requests
from agno.tools import Toolkit
from agno.tools.function import ToolResult

ARXIV_API_URL = "https://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"

# Jina 的 read/search 服务能把网页或搜索结果转成适合 LLM 消费的文本。
# read_url 会拼到 r.jina.ai，search_query 会拼到 s.jina.ai。
JINA_READ_URL = "https://r.jina.ai/http://"
JINA_SEARCH_URL = "https://s.jina.ai/"

# arXiv 返回 Atom XML，解析时必须带命名空间，否则 find/findall 拿不到节点。
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class AcademicSearchToolkit(Toolkit):
    """面向学术与研究资料收集的工具集合。

    Agno 会把 `tools=[...]` 中注册的方法暴露给 Agent。这里把检索、网页读取、
    论文元数据查询、GitHub 读取等能力集中在一个 Toolkit 中，方便
    `academic_agent` 根据用户问题自动选择合适工具。
    """

    def __init__(self) -> None:
        """注册所有可被 Agent 调用的工具方法。"""
        super().__init__(
            name="academic_search_tools",
            tools=[
                # 通用网页/新闻搜索。
                self.duckduckgo_search,
                self.duckduckgo_news,
                self.baidu_search,
                self.get_baidu_hot_topics,
                self.search_csdn_articles,
                # Jina 文本化网页读取与搜索。
                self.read_url,
                self.search_query,
                self.deep_search,
                # 学术与数学资料源。
                self.arxiv_search,
                self.search_mathworld_by_keyword,
                self.get_mathworld_article,
                self.list_mathworld_topics,
                # GitHub 资料源，常用于找论文代码、示例实现或项目 README。
                self.search_github_repositories,
                self.search_github_code,
                self.get_github_repository,
                self.get_github_file_content,
                self.get_github_directory_content,
                # Semantic Scholar 论文检索与详情查询。
                self.search_semantic_scholar,
                self.get_semantic_scholar_paper_details,
                # YouTube 资料源，适合检索课程、讲座、演示视频的元信息和字幕。
                self.get_youtube_video_data,
                self.get_youtube_video_captions,
                self.get_video_timestamps,
            ],
        )

    def _json_result(self, payload: dict[str, Any]) -> ToolResult:
        """把结构化字典包装成 Agno 的 ToolResult。

        论文类工具优先返回 ToolResult，方便框架识别这是一次工具调用的正式输出。
        `ensure_ascii=False` 保留中文和非 ASCII 字符，避免 Agent 看到转义文本。
        """
        return ToolResult(content=json.dumps(payload, ensure_ascii=False, indent=2))

    def _string_result(self, payload: Any) -> str:
        """把任意对象序列化成 JSON 字符串。

        一些工具方法直接返回 `str`，这里统一 JSON 格式，避免不同来源返回散乱文本。
        """
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _requests_get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
    ) -> requests.Response:
        """统一 GET 请求入口。

        所有基于 requests 的 GET 调用都经过这里，保证超时和 HTTP 错误处理一致。
        这里会调用 `raise_for_status()`，上层工具再捕获异常并返回可读错误。
        """
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response

    def _requests_post(
        self,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
    ) -> requests.Response:
        """统一 POST 请求入口。

        当前文件里保留这个封装是为了后续接入需要 POST 的搜索/摘要 API。
        """
        response = requests.post(url, json=json_body, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response

    def _clean_html(self, text: str) -> str:
        """去掉 HTML 标签并压缩空白字符。"""
        cleaned = re.sub(r"<[^>]+>", "", text or "")
        cleaned = unescape(cleaned)
        return " ".join(cleaned.split())

    def _import_ddgs(self):
        """延迟导入 ddgs。

        这样即使环境没有安装 ddgs，也只会在调用 DuckDuckGo 工具时失败，
        不会影响整个 Toolkit 被导入和其他工具正常使用。
        """
        try:
            from ddgs import DDGS
        except Exception as exc:  # pragma: no cover - depends on env
            raise RuntimeError("ddgs is required for DuckDuckGo search") from exc
        return DDGS

    def _import_bs4(self):
        """延迟导入 BeautifulSoup，降低非网页解析工具的运行依赖。"""
        try:
            from bs4 import BeautifulSoup
        except Exception as exc:  # pragma: no cover - depends on env
            raise RuntimeError("beautifulsoup4 is required for this tool") from exc
        return BeautifulSoup

    def duckduckgo_search(self, query: str, max_results: int = 5) -> str:
        """使用 DuckDuckGo 执行通用网页搜索。

        Args:
            query: 搜索关键词或自然语言查询。
            max_results: 最多返回条数，内部限制在 1 到 10 之间，避免上下文过大。

        Returns:
            JSON 字符串，通常包含标题、摘要和链接；失败时返回 `{"error": ...}`。
        """
        try:
            DDGS = self._import_ddgs()
            with DDGS(timeout=10) as ddgs:
                results = list(ddgs.text(query=query, max_results=max(1, min(max_results, 10))))
            return self._string_result(results)
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def duckduckgo_news(self, query: str, max_results: int = 5) -> str:
        """使用 DuckDuckGo 新闻搜索获取更偏近期的信息。"""
        try:
            DDGS = self._import_ddgs()
            with DDGS(timeout=10) as ddgs:
                results = list(ddgs.news(query=query, max_results=max(1, min(max_results, 10))))
            return self._string_result(results)
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def _extract_real_baidu_url(self, url: str) -> str:
        """解析百度跳转链接，尽量还原真实目标 URL。"""
        if "baidu.com" not in url:
            return url
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5,
                allow_redirects=True,
            )
            return response.url or url
        except Exception:
            return url

    def baidu_search(self, query: str, max_results: int = 5, language: str = "zh") -> str:
        """使用百度搜索中文网页资料。

        `language` 参数保留给工具接口兼容，目前实现中不使用。
        百度结果页结构经常变化，因此这个工具更适合做补充搜索，不适合作为唯一信源。
        """
        del language
        try:
            BeautifulSoup = self._import_bs4()
            response = self._requests_get(
                "https://www.baidu.com/s",
                params={"wd": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            soup = BeautifulSoup(response.text, "html.parser")
            results: list[dict[str, str]] = []
            blocks = soup.select("div.result, div.c-container")
            for idx, block in enumerate(blocks[: max(1, min(max_results, 10))], start=1):
                title_el = block.select_one("h3")
                link_el = block.select_one("a")
                abstract_el = block.select_one(".c-abstract, .content-right_8Zs40, .c-span-last")
                if not title_el or not link_el:
                    continue
                raw_url = link_el.get("href", "")
                results.append(
                    {
                        "title": self._clean_html(title_el.get_text(" ", strip=True)),
                        "url": self._extract_real_baidu_url(raw_url),
                        "abstract": self._clean_html(abstract_el.get_text(" ", strip=True) if abstract_el else ""),
                        "rank": str(idx),
                    }
                )
            return self._string_result(results)
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def get_baidu_hot_topics(self, max_results: int = 20) -> str:
        """读取百度热榜 RSS，并整理成标题、热度、链接等字段。"""
        try:
            response = self._requests_get(
                "https://rss.aishort.top/?type=baidu",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            root = ET.fromstring(response.content)
            items = root.findall(".//item")
            results = []
            for idx, item in enumerate(items[: max(1, min(max_results, 50))], start=1):
                title_text = item.findtext("title", default="")
                # RSS 标题末尾可能带 “热度: 数字”，这里拆出来放到独立字段。
                heat_match = re.search(r"\s+热度[:：]\s*(\d+)$", title_text)
                results.append(
                    {
                        "title": title_text[: heat_match.start()].strip() if heat_match else title_text.strip(),
                        "heat": heat_match.group(1) if heat_match else "",
                        "url": item.findtext("link", default=""),
                        "description": item.findtext("description", default=""),
                        "pub_date": item.findtext("pubDate", default=""),
                        "rank": str(idx),
                    }
                )
            return self._string_result(results)
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def search_csdn_articles(self, query: str, max_results: int = 10, content_type: str = "blog") -> str:
        """调用 CSDN 搜索接口检索中文技术文章。

        Args:
            query: 搜索关键词。
            max_results: 返回条数，内部限制在 1 到 20 之间。
            content_type: CSDN 搜索类型，默认 `blog`。
        """
        try:
            response = self._requests_get(
                "https://so.csdn.net/api/v3/search",
                params={"q": query, "t": content_type, "p": 1},
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://so.csdn.net/so/search",
                },
                timeout=10,
            )
            data = response.json()
            result_vos = data.get("result_vos", [])
            results = []
            for idx, item in enumerate(result_vos[: max(1, min(max_results, 20))], start=1):
                results.append(
                    {
                        "title": self._clean_html(item.get("title", "")),
                        "author": item.get("nickname", "") or item.get("author", ""),
                        "url": item.get("url", ""),
                        "summary": self._clean_html(item.get("digest", "") or item.get("body", "")),
                        "views": str(item.get("view", "0") or item.get("view_num", "0")),
                        "likes": str(item.get("digg", "0")),
                        "comments": str(item.get("comment", "0")),
                        "publish_date": item.get("create_time_str", "") or item.get("created_at", ""),
                        "tags": item.get("search_tag", []) or [],
                        "rank": str(idx),
                    }
                )
            return self._string_result(results)
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def read_url(self, url: str) -> ToolResult:
        """通过 Jina Reader 读取网页正文。

        普通网页常包含大量导航、脚本和样式。Jina Reader 会尽量返回 Markdown/文本化
        内容，便于 Agent 摘要和引用。为了控制上下文，最多返回前 10000 个字符。
        """
        try:
            stripped = url.strip()
            # Jina read URL 的格式是 `https://r.jina.ai/http://example.com`。
            # 对 https 链接也要去掉原协议，再拼接到固定前缀后面。
            if stripped.startswith("http://"):
                target = JINA_READ_URL + stripped[len("http://") :]
            elif stripped.startswith("https://"):
                target = JINA_READ_URL + stripped[len("https://") :]
            else:
                target = JINA_READ_URL + stripped
            response = self._requests_get(target, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            return ToolResult(content=response.text[:10000])
        except Exception as exc:
            return ToolResult(content=f"读取 URL 失败: {exc}")

    def search_query(self, query: str) -> ToolResult:
        """通过 Jina Search 执行搜索并返回文本化结果。"""
        try:
            target = JINA_SEARCH_URL + urllib.parse.quote(query, safe="")
            response = self._requests_get(target, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            return ToolResult(content=response.text[:10000])
        except Exception as exc:
            return ToolResult(content=f"搜索失败: {exc}")

    def deep_search(self, query: str) -> ToolResult:
        """DeepSearch 占位工具。

        当前仓库没有接入 Jina DeepSearch 的专用 API。保留这个工具是为了让 Agent
        在被要求“深度搜索”时得到明确反馈，并引导它改用现有 `search_query/read_url`。
        """
        return ToolResult(
            content=(
                "当前仓库未配置 Jina DeepSearch 的专用 API 接入。"
                f"你可以改用 search_query/read_url 继续检索。原始问题: {query}"
            )
        )

    def arxiv_search(self, query: str, num_articles: int = 5) -> ToolResult:
        """检索 arXiv 论文并返回结构化论文列表。

        Args:
            query: arXiv 搜索关键词，会拼成 `all:{query}`。
            num_articles: 返回论文数量，内部限制在 1 到 10 之间。

        Returns:
            ToolResult，content 为 JSON，包含 success/source/query/count/papers。
        """
        limit = max(1, min(int(num_articles), 10))
        try:
            response = self._requests_get(
                ARXIV_API_URL,
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": limit,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                },
                timeout=20,
            )
            root = ET.fromstring(response.text)
            papers: list[dict[str, Any]] = []
            for entry in root.findall("atom:entry", ATOM_NS):
                # arXiv Atom 中作者、分类、PDF 链接分散在不同节点，逐项抽取后统一成 dict。
                authors = [
                    author.findtext("atom:name", default="", namespaces=ATOM_NS)
                    for author in entry.findall("atom:author", ATOM_NS)
                ]
                categories = [category.attrib.get("term", "") for category in entry.findall("atom:category", ATOM_NS)]
                pdf_url = ""
                for link in entry.findall("atom:link", ATOM_NS):
                    # PDF 链接通常通过 title="pdf" 或 type="application/pdf" 标识。
                    if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                        pdf_url = link.attrib.get("href", "")
                        break
                papers.append(
                    {
                        "title": (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip(),
                        "entry_id": (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip(),
                        "authors": [author for author in authors if author],
                        "primary_category": (
                            entry.find("arxiv:primary_category", ATOM_NS).attrib.get("term", "")
                            if entry.find("arxiv:primary_category", ATOM_NS) is not None
                            else ""
                        ),
                        "categories": [category for category in categories if category],
                        "published": (entry.findtext("atom:published", default="", namespaces=ATOM_NS) or "").strip() or None,
                        "updated": (entry.findtext("atom:updated", default="", namespaces=ATOM_NS) or "").strip() or None,
                        "pdf_url": pdf_url,
                        "summary": (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").strip(),
                    }
                )
            return self._json_result(
                {
                    "success": True,
                    "source": "arxiv",
                    "query": query,
                    "count": len(papers),
                    "papers": papers,
                }
            )
        except Exception as exc:
            return self._json_result(
                {
                    "success": False,
                    "source": "arxiv",
                    "query": query,
                    "count": 0,
                    "papers": [],
                    "error": str(exc),
                }
            )

    def _keyword_to_camelcase(self, keyword: str) -> str:
        """把自然语言关键词转换成 MathWorld 常用的 CamelCase 页面名。"""
        keyword = keyword.replace("'s", "s").replace("’s", "s")
        keyword = re.sub(r"[^\w\s]", "", keyword)
        return "".join(word.capitalize() for word in keyword.strip().split())

    def search_mathworld_by_keyword(self, keyword: str) -> str:
        """根据关键词猜测 MathWorld 页面 URL 并读取文章内容。"""
        slug = self._keyword_to_camelcase(keyword)
        url = f"https://mathworld.wolfram.com/{slug}.html"
        return self.get_mathworld_article(url)

    def get_mathworld_article(self, url: str) -> str:
        """读取指定 MathWorld 文章页面并抽取正文段落。"""
        try:
            BeautifulSoup = self._import_bs4()
            response = self._requests_get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            # MathWorld 页面正文主要在 p 标签中，截取前 20 段避免输出过长。
            paragraphs = [p.get_text(" ", strip=True) for p in soup.select("p") if p.get_text(" ", strip=True)]
            return self._string_result(
                {
                    "title": title,
                    "url": url,
                    "content": "\n\n".join(paragraphs[:20]),
                }
            )
        except Exception as exc:
            return self._string_result({"error": str(exc), "url": url})

    def list_mathworld_topics(self) -> str:
        """列出 MathWorld topics 页面中的主题链接。"""
        try:
            BeautifulSoup = self._import_bs4()
            response = self._requests_get("https://mathworld.wolfram.com/topics/", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for link in soup.find_all("a", href=True):
                href = str(link.get("href", ""))
                if href.startswith("/") and href.endswith(".html"):
                    title = link.get_text(" ", strip=True)
                    if title:
                        results.append({"title": title, "url": f"https://mathworld.wolfram.com{href}"})
            return self._string_result(results)
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def _github_headers(self) -> dict[str, str]:
        """构造 GitHub API 请求头。

        如果设置了 `GITHUB_ACCESS_TOKEN`，会自动使用 Bearer Token，提高速率限制并支持
        访问有权限的资源。
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "agent-manage-academic-agent",
        }
        token = os.getenv("GITHUB_ACCESS_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def search_github_repositories(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        page: int = 1,
        per_page: int = 5,
    ) -> str:
        """搜索 GitHub 仓库，常用于查找论文官方实现或相关开源项目。"""
        try:
            response = self._requests_get(
                "https://api.github.com/search/repositories",
                params={
                    "q": query,
                    "sort": sort,
                    "order": order,
                    "page": max(1, page),
                    "per_page": max(1, min(per_page, 10)),
                },
                headers=self._github_headers(),
                timeout=20,
            )
            items = response.json().get("items", [])
            results = [
                {
                    "full_name": item.get("full_name"),
                    "description": item.get("description"),
                    "url": item.get("html_url"),
                    "stars": item.get("stargazers_count"),
                    "forks": item.get("forks_count"),
                    "language": item.get("language"),
                }
                for item in items
            ]
            return self._string_result(results)
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def search_github_code(
        self,
        query: str,
        language: str | None = None,
        repo: str | None = None,
        user: str | None = None,
        path: str | None = None,
        filename: str | None = None,
    ) -> str:
        """搜索 GitHub 代码。

        可通过 language/repo/user/path/filename 逐步收窄范围。GitHub code search 对未认证
        请求限制较多，生产环境建议配置 `GITHUB_ACCESS_TOKEN`。
        """
        try:
            search_query = query
            # GitHub 搜索语法通过空格追加限定条件，例如 `language:Python repo:owner/name`。
            if language:
                search_query += f" language:{language}"
            if repo:
                search_query += f" repo:{repo}"
            if user:
                search_query += f" user:{user}"
            if path:
                search_query += f" path:{path}"
            if filename:
                search_query += f" filename:{filename}"
            response = self._requests_get(
                "https://api.github.com/search/code",
                params={"q": search_query, "per_page": 10},
                headers=self._github_headers(),
                timeout=20,
            )
            data = response.json()
            return self._string_result(
                {
                    "query": search_query,
                    "total_count": data.get("total_count", 0),
                    "results": [
                        {
                            "repository": item.get("repository", {}).get("full_name"),
                            "path": item.get("path"),
                            "name": item.get("name"),
                            "html_url": item.get("html_url"),
                            "sha": item.get("sha"),
                        }
                        for item in data.get("items", [])
                    ],
                }
            )
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def get_github_repository(self, repo_name: str) -> str:
        """读取单个 GitHub 仓库的基础元数据。

        Args:
            repo_name: `owner/repo` 格式的仓库名。
        """
        try:
            response = self._requests_get(
                f"https://api.github.com/repos/{repo_name}",
                headers=self._github_headers(),
                timeout=20,
            )
            repo = response.json()
            return self._string_result(
                {
                    "name": repo.get("full_name"),
                    "description": repo.get("description"),
                    "url": repo.get("html_url"),
                    "stars": repo.get("stargazers_count"),
                    "forks": repo.get("forks_count"),
                    "open_issues": repo.get("open_issues_count"),
                    "language": repo.get("language"),
                    "license": (repo.get("license") or {}).get("name"),
                    "default_branch": repo.get("default_branch"),
                }
            )
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def get_github_file_content(self, repo_name: str, path: str, ref: str | None = None) -> str:
        """读取 GitHub 仓库中的单个文件内容。

        GitHub contents API 对文件内容使用 base64 编码，本方法会自动解码为 UTF-8 文本。
        如果 path 指向目录，会返回错误信息，避免把目录误当文件处理。
        """
        try:
            params = {"ref": ref} if ref else None
            response = self._requests_get(
                f"https://api.github.com/repos/{repo_name}/contents/{path}",
                params=params,
                headers=self._github_headers(),
                timeout=20,
            )
            item = response.json()
            if isinstance(item, list):
                return self._string_result({"error": f"{path} is a directory, not a file"})
            content = item.get("content", "")
            encoding = item.get("encoding")
            # GitHub contents API 返回的文件内容通常是 base64。
            if encoding == "base64":
                import base64

                decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            else:
                decoded = content
            return self._string_result(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "sha": item.get("sha"),
                    "size": item.get("size"),
                    "type": item.get("type"),
                    "url": item.get("html_url"),
                    "content": decoded,
                }
            )
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def get_github_directory_content(self, repo_name: str, path: str = "", ref: str | None = None) -> str:
        """列出 GitHub 仓库目录内容。

        Args:
            repo_name: `owner/repo` 格式的仓库名。
            path: 仓库内目录路径，默认为根目录。
            ref: 可选分支、tag 或 commit SHA。
        """
        try:
            params = {"ref": ref} if ref else None
            response = self._requests_get(
                f"https://api.github.com/repos/{repo_name}/contents/{path}",
                params=params,
                headers=self._github_headers(),
                timeout=20,
            )
            items = response.json()
            if not isinstance(items, list):
                return self._string_result({"error": f"{path or '/'} is a file, not a directory"})
            return self._string_result(
                [
                    {
                        "name": item.get("name"),
                        "path": item.get("path"),
                        "type": item.get("type"),
                        "size": item.get("size"),
                        "url": item.get("html_url"),
                    }
                    for item in items
                ]
            )
        except Exception as exc:
            return self._string_result({"error": str(exc)})

    def _normalize_semantic_scholar_paper(self, paper: dict[str, Any]) -> dict[str, Any]:
        """把 Semantic Scholar 原始论文对象归一化成内部统一结构。

        Semantic Scholar 字段丰富但层级较深。本方法统一抽取 DOI、arXiv ID、PDF、
        作者、摘要、引用量等字段，让 Agent 不必理解第三方 API 的原始结构。
        """
        external_ids = paper.get("externalIds") or {}
        open_access_pdf = paper.get("openAccessPdf") or {}
        tldr = paper.get("tldr") or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")
        paper_id = paper.get("paperId")
        paper_url = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""
        pdf_url = (open_access_pdf.get("url") or "").strip()
        # openAccessPdf 有时返回落地页而不是 PDF。这里保守过滤掉非 .pdf 链接。
        if pdf_url and not pdf_url.lower().endswith(".pdf"):
            pdf_url = ""
        # 如果 Semantic Scholar 没给 PDF，但给了 arXiv ID，就构造 arXiv PDF 链接。
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        if doi:
            entry_id = f"https://doi.org/{doi}"
        elif arxiv_id:
            entry_id = f"https://arxiv.org/abs/{arxiv_id}"
        else:
            entry_id = paper_url
        publication_date = paper.get("publicationDate")
        year = paper.get("year")
        # 如果只有年份没有完整日期，保留年份信息，便于 Agent 做时间排序或过滤。
        published = publication_date or (f"{year}-null-null" if year else None)
        return {
            "paper_id": paper_id,
            "title": paper.get("title", ""),
            "authors": [author.get("name", "Unknown Author") for author in paper.get("authors", [])],
            "pdf_url": pdf_url,
            "paper_url": paper_url,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "entry_id": entry_id,
            "published": published,
            "venue": paper.get("venue", ""),
            "abstract": paper.get("abstract", ""),
            "tldr": tldr.get("text", ""),
            "citation_count": paper.get("citationCount"),
            "influential_citation_count": paper.get("influentialCitationCount"),
            "is_open_access": paper.get("isOpenAccess", False),
            "source": "semantic_scholar",
        }

    def _semantic_scholar_headers(self) -> dict[str, str]:
        """构造 Semantic Scholar API 请求头。

        设置 `SEMANTIC_SCHOLAR_API_KEY` 后会自动带上 `x-api-key`，提高限流额度。
        """
        headers = {"Accept": "application/json", "User-Agent": "agent-manage-academic-agent/1.0"}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    def search_semantic_scholar(
        self,
        query: str,
        year_start: int | None = None,
        year_end: int | None = None,
        num_results: int = 5,
    ) -> ToolResult:
        """使用 Semantic Scholar 搜索论文。

        Args:
            query: 搜索关键词或论文主题。
            year_start: 可选起始年份。
            year_end: 可选结束年份。只有起止年份都提供时才应用年份过滤。
            num_results: 返回数量，内部限制在 1 到 20 之间。

        Returns:
            ToolResult，content 为 JSON，包含统一后的论文列表。
        """
        limit = max(1, min(int(num_results), 20))
        params: dict[str, Any] = {
            "query": query[:300],
            "limit": limit,
            # fields 控制 Semantic Scholar 返回字段。只取需要字段，减少响应体积和上下文噪音。
            "fields": (
                "paperId,title,authors,year,publicationDate,venue,abstract,"
                "isOpenAccess,openAccessPdf,tldr,citationCount,"
                "influentialCitationCount,externalIds"
            ),
        }
        if year_start and year_end:
            params["year"] = f"{year_start}-{year_end}"
        try:
            response = self._requests_get(
                f"{SEMANTIC_SCHOLAR_API_URL}/paper/search",
                params=params,
                headers=self._semantic_scholar_headers(),
                timeout=20,
            )
            data = response.json()
            papers = [self._normalize_semantic_scholar_paper(paper) for paper in data.get("data", [])]
            return self._json_result(
                {
                    "success": True,
                    "source": "semantic_scholar",
                    "query": query,
                    "filters": {"year_range": [year_start, year_end] if year_start and year_end else None},
                    "count": len(papers),
                    "papers": papers,
                }
            )
        except Exception as exc:
            return self._json_result(
                {
                    "success": False,
                    "source": "semantic_scholar",
                    "query": query,
                    "filters": {"year_range": [year_start, year_end] if year_start and year_end else None},
                    "count": 0,
                    "papers": [],
                    "error": str(exc),
                }
            )

    def get_semantic_scholar_paper_details(self, paper_id: str) -> ToolResult:
        """按 paperId/DOI/arXiv ID 等标识读取 Semantic Scholar 论文详情。"""
        try:
            response = self._requests_get(
                f"{SEMANTIC_SCHOLAR_API_URL}/paper/{urllib.parse.quote(paper_id, safe='')}",
                params={
                    "fields": (
                        "paperId,title,authors,year,publicationDate,venue,abstract,"
                        "isOpenAccess,openAccessPdf,tldr,citationCount,"
                        "influentialCitationCount,externalIds"
                    )
                },
                headers=self._semantic_scholar_headers(),
                timeout=20,
            )
            paper = self._normalize_semantic_scholar_paper(response.json())
            return self._json_result(
                {
                    "success": True,
                    "source": "semantic_scholar",
                    "paper": paper,
                }
            )
        except Exception as exc:
            return self._json_result(
                {
                    "success": False,
                    "source": "semantic_scholar",
                    "paper": None,
                    "error": str(exc),
                }
            )

    def get_youtube_video_id(self, url: str) -> str | None:
        """从常见 YouTube URL 形式中提取 video id。"""
        try:
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname
            if hostname == "youtu.be":
                return parsed_url.path[1:]
            if hostname in ("www.youtube.com", "youtube.com"):
                if parsed_url.path == "/watch":
                    return parse_qs(parsed_url.query).get("v", [None])[0]
                if parsed_url.path.startswith("/embed/") or parsed_url.path.startswith("/v/"):
                    return parsed_url.path.split("/")[2]
        except Exception:
            return None
        return None

    def get_youtube_video_data(self, url: str) -> str:
        """通过 YouTube oEmbed 获取视频基础元信息。"""
        try:
            video_id = self.get_youtube_video_id(url)
            if not video_id:
                return "No video ID found"
            query_string = urlencode({"format": "json", "url": f"https://www.youtube.com/watch?v={video_id}"})
            with urlopen(f"https://www.youtube.com/oembed?{query_string}") as response:
                video_data = json.loads(response.read().decode())
            return self._string_result(
                {
                    "title": video_data.get("title"),
                    "author_name": video_data.get("author_name"),
                    "author_url": video_data.get("author_url"),
                    "type": video_data.get("type"),
                    "height": video_data.get("height"),
                    "width": video_data.get("width"),
                    "version": video_data.get("version"),
                    "provider_name": video_data.get("provider_name"),
                    "provider_url": video_data.get("provider_url"),
                    "thumbnail_url": video_data.get("thumbnail_url"),
                }
            )
        except Exception as exc:
            return f"Error getting video data: {exc}"

    def _fetch_youtube_captions(self, url: str):
        """拉取 YouTube 字幕对象，供字幕全文和时间戳工具复用。"""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except Exception as exc:  # pragma: no cover - depends on env
            raise RuntimeError("youtube_transcript_api is required for captions") from exc
        video_id = self.get_youtube_video_id(url)
        if not video_id:
            raise RuntimeError("No video ID found")
        return YouTubeTranscriptApi().fetch(video_id)

    def get_youtube_video_captions(self, url: str) -> str:
        """获取 YouTube 视频字幕全文。"""
        try:
            captions = self._fetch_youtube_captions(url)
            return " ".join(line.text for line in captions)
        except Exception as exc:
            return f"Error getting captions for video: {exc}"

    def get_video_timestamps(self, url: str) -> str:
        """把 YouTube 字幕转换成 `分:秒 - 文本` 的时间戳列表。"""
        try:
            captions = self._fetch_youtube_captions(url)
            timestamps = []
            for line in captions:
                start = int(line.start)
                minutes, seconds = divmod(start, 60)
                timestamps.append(f"{minutes}:{seconds:02d} - {line.text}")
            return "\n".join(timestamps)
        except Exception as exc:
            return f"Error generating timestamps: {exc}"
