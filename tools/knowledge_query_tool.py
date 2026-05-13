"""
User Knowledge Base Query Tool

Provides multi-tenant isolated knowledge base querying for agents.
Each user can only access their own knowledge bases, official KBs, and public KBs.
"""

from typing import List, Optional
from agno.tools.function import Function
from agno.utils.log import logger

from auth.kb_metadata import list_accessible_knowledge_bases
from auth.model import CurrentUser
from config.db_config import create_knowledge


def create_knowledge_query_tool() -> Function:
    """
    Create a tool for querying user-accessible knowledge bases.

    This tool enforces multi-tenant isolation by:
    1. Only returning user's own KBs
    2. Optionally including official KBs
    3. Optionally including public KBs from other users

    The tool returns relevant document chunks from the queried knowledge bases.
    """

    async def query_user_knowledge(
        query: str,
        kb_names: Optional[List[str]] = None,
        max_results: int = 10,
        current_user: CurrentUser = None,
    ) -> str:
        """
        Search across user-accessible knowledge bases.

        Args:
            query: The search query
            kb_names: Optional list of knowledge base names to search.
                      If None, searches all accessible knowledge bases.
            max_results: Maximum number of results per knowledge base (default: 10)
            current_user: The current authenticated user (injected by framework)

        Returns:
            Formatted search results with document content and metadata.
        """
        if not query or not query.strip():
            return "请提供有效的搜索查询。"

        # Get all accessible knowledge bases for the user
        accessible_kbs = list_accessible_knowledge_bases(
            user_id=current_user.user_id,
            include_official=True,
            include_public=True,
            active_only=True,
        )

        # Filter by requested KB names if provided
        if kb_names:
            accessible_kbs = [
                kb for kb in accessible_kbs
                if kb.kb_name in kb_names or kb.kb_id in kb_names
            ]

        if not accessible_kbs:
            return "没有找到可访问的知识库。"

        # Search across all accessible knowledge bases
        all_results = []
        for kb in accessible_kbs:
            try:
                # Create knowledge instance for this KB
                safe_kb_id = kb.kb_id.replace("-", "_")
                knowledge = create_knowledge(
                    id=safe_kb_id,
                    name=kb.kb_name,
                    description=kb.kb_description,
                )

                # Search in this KB
                results = knowledge.search(
                    query=query,
                    max_results=max_results,
                )

                # Format results
                for result in results:
                    all_results.append({
                        "kb_name": kb.kb_name,
                        "kb_id": kb.kb_id,
                        "content": result.data.get("content", ""),
                        "metadata": result.meta or {},
                        "score": result.score or 0.0,
                        "source": result.data.get("source", "unknown"),
                    })

            except Exception as e:
                logger.warning(f"Failed to search in KB {kb.kb_id}: {e}")
                continue

        if not all_results:
            return f"在 {len(accessible_kbs)} 个知识库中没有找到与「{query}」相关的内容。"

        # Format output
        output = [f"从 {len(accessible_kbs)} 个知识库中找到 {len(all_results)} 条相关结果：\n"]

        for i, result in enumerate(all_results[:max_results * len(accessible_kbs)], 1):
            output.append(f"\n【结果 {i}】")
            output.append(f"知识库：{result['kb_name']}")
            output.append(f"来源：{result['source']}")
            output.append(f"相关度：{result['score']:.2f}")
            output.append(f"内容：\n{result['content']}\n")

        return "\n".join(output)

    return Function(
        entrypoint=query_user_knowledge,
        description="""
        搜索用户可访问的知识库。

        可以搜索：
        - 用户自己创建的知识库
        - 官方知识库（系统提供）
        - 其他用户的公开知识库

        如果用户没有指定知识库名称，默认搜索所有可访问的知识库。
        """,
        name="query_knowledge",
    )


def create_knowledge_list_tool() -> Function:
    """Create a tool for listing user-accessible knowledge bases."""

    async def list_user_knowledge_bases(
        current_user: CurrentUser = None,
    ) -> str:
        """
        List all knowledge bases accessible to the current user.

        Args:
            current_user: The current authenticated user (injected by framework)

        Returns:
            Formatted list of accessible knowledge bases.
        """
        accessible_kbs = list_accessible_knowledge_bases(
            user_id=current_user.user_id,
            include_official=True,
            include_public=True,
            active_only=True,
        )

        if not accessible_kbs:
            return "当前用户没有可访问的知识库。"

        # Group by type
        personal_kbs = [kb for kb in accessible_kbs if not kb.is_official and kb.owner_id == current_user.user_id]
        official_kbs = [kb for kb in accessible_kbs if kb.is_official]
        public_kbs = [kb for kb in accessible_kbs if kb.is_public and kb.owner_id != current_user.user_id]

        output = []

        if personal_kbs:
            output.append(f"\n【个人知识库】({len(personal_kbs)} 个)")
            for kb in personal_kbs:
                output.append(f"- {kb.kb_name} (ID: {kb.kb_id})")
                output.append(f"  描述：{kb.kb_description}")
                output.append(f"  文件数：{kb.file_count}, 块数：{kb.total_chunks}")

        if official_kbs:
            output.append(f"\n【官方知识库】({len(official_kbs)} 个)")
            for kb in official_kbs:
                output.append(f"- {kb.kb_name} (ID: {kb.kb_id})")
                output.append(f"  描述：{kb.kb_description}")

        if public_kbs:
            output.append(f"\n【公开知识库】({len(public_kbs)} 个)")
            for kb in public_kbs:
                output.append(f"- {kb.kb_name} (拥有者：{kb.owner_id})")
                output.append(f"  描述：{kb.kb_description}")

        return "\n".join(output)

    return Function(
        entrypoint=list_user_knowledge_bases,
        description="""
        列出当前用户可访问的所有知识库。

        返回个人知识库、官方知识库和公开知识库的列表。
        """,
        name="list_knowledge_bases",
    )
