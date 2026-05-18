"""
官方知识库管理模块

提供创建和管理官方知识库的工具方法。
官方知识库对非管理员用户为只读状态，并为所有用户提供默认知识库内容。
"""

import uuid
import hashlib
import logging
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

# 导入知识库元数据相关功能
from auth.kb_metadata import (
    create_knowledge_base,    # 创建知识库
    get_knowledge_base,       # 获取单个知识库信息
    KnowledgeBaseRecord,      # 知识库记录数据结构
    list_knowledge_bases,     # 列出所有知识库
)
# 导入数据库配置与知识库操作工具
from config.db_config import Config, create_knowledge_vector, create_knowledge, get_psycopg_db_url

# 官方知识库ID前缀
OFFICIAL_KB_PREFIX = "official_"


def generate_official_kb_id(name: str) -> str:
    """
    为官方知识库生成稳定唯一的ID

    使用名称的哈希值确保在不同部署环境中ID保持一致
    """
    # 对名称进行MD5哈希，取前8位字符
    name_hash = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"{OFFICIAL_KB_PREFIX}{name_hash}"


def create_official_knowledge_base(
    name: str,
    description: str,
    initial_documents: Optional[List[str]] = None,
    max_results: int = 10,
) -> Optional[KnowledgeBaseRecord]:
    """
    创建官方知识库

    官方知识库特性：
    - 标记为 is_official=True
    - 拥有专属的ID前缀
    - 所有已认证用户均可读取
    - 仅管理员可修改内容
    - 为系统提供默认知识库内容

    注意：文本分块策略会由文件检测器根据文件类型自动选择，
    知识库中的每个文档都会使用最优的读取器和分块器。

    参数：
        name: 官方知识库名称
        description: 知识库内容描述
        initial_documents: 用于初始化知识库的文件路径列表
        max_results: 搜索时返回的最大结果数

    返回：
        创建成功的知识库记录对象，若已存在则返回None
    """
    # 生成官方知识库唯一ID
    kb_id = generate_official_kb_id(name)

    # 检查知识库是否已存在
    existing = get_knowledge_base(kb_id)
    if existing:
        logger.info(f"官方知识库 '{name}' 已存在，ID为 {kb_id}")
        return existing

    # 生成安全的数据库表名（替换横杠为下划线）
    safe_kb_id = kb_id.replace("-", "_")
    vector_table_name = f"{safe_kb_id}_knowledge_vectors"    # 向量数据表名
    content_table_name = f"{safe_kb_id}_knowledge_contents"  # 内容数据表名

    # 创建数据库记录
    # 注意：chunking_mode 持久化存储"自动"策略选择，
    # 实际的读取器/分块器仍会在数据导入时由文件检测器按文件类型自动选择
    try:
        kb_record = create_knowledge_base(
            kb_id=kb_id,
            kb_name=name,
            kb_description=description,
            owner_id="system",  # 官方知识库归属系统用户
            is_official=True,
            is_public=True,     # 官方知识库默认公开
            vector_table_name=vector_table_name,
            chunking_mode="auto",  # 自动检测分块模式
            chunk_size=5000,    # 默认分块大小，特定分块器可覆盖
            chunk_overlap=200,  # 默认分块重叠长度，特定分块器可覆盖
            max_results=max_results,
        )
    except Exception as e:
        logger.error(f"创建官方知识库记录失败 '{name}': {e}")
        return None

    # 创建向量数据库表
    try:
        create_knowledge_vector(
            id=safe_kb_id,
            table_name=vector_table_name,
        )
    except Exception as e:
        logger.error(f"为官方知识库创建向量数据库失败 '{name}': {e}")
        # 创建失败，回滚删除知识库记录
        from auth.kb_metadata import delete_knowledge_base, drop_knowledge_tables
        delete_knowledge_base(kb_id)
        return None

    # 如果提供了初始文档，导入到知识库
    if initial_documents:
        populate_official_kb(kb_id, initial_documents)

    logger.info(f"成功创建官方知识库 '{name}'，ID为 {kb_id}")
    return kb_record


def populate_official_kb(
    kb_id: str,
    document_paths: List[str],
) -> int:
    """
    向官方知识库导入文档数据

    注意：文件检测器会根据每个文档的类型自动选择合适的读取器和分块器

    返回：
        成功处理的文档数量
    """
    safe_kb_id = kb_id.replace("-", "_")
    # 初始化知识库操作对象
    knowledge = create_knowledge(
        id=safe_kb_id,
        name=f"Official: {kb_id}",
        description="Official knowledge base",
    )

    processed_count = 0
    # 遍历所有文档路径并导入
    for doc_path in document_paths:
        try:
            path = Path(doc_path)
            if not path.exists():
                logger.warning(f"文档不存在: {doc_path}")
                continue

            # 通过文件检测器自动获取对应读取器和分块器
            from knowledge.file_detector import get_reader_and_chunker
            reader, chunker = get_reader_and_chunker(
                doc_path,
                chunk_size=5000,
                overlap=200,
            )
            logger.info(f"文档 {doc_path} 使用分块器: {type(chunker).__name__}")

            # 插入文档到知识库
            knowledge.insert(
                path=str(path),
                reader=reader,
            )
            processed_count += 1
            logger.info(f"已将文档 {doc_path} 添加到官方知识库 {kb_id}")
        except Exception as e:
            logger.error(f"向官方知识库 {kb_id} 插入文档 {doc_path} 失败: {e}")

    # 导入完成后更新知识库的分块总数
    if processed_count > 0:
        try:
            chunk_count = _count_chunks(kb_id)
            from auth.kb_metadata import update_kb_chunk_count
            update_kb_chunk_count(kb_id, increment=chunk_count)
        except Exception as e:
            logger.error(f"更新官方知识库 {kb_id} 分块数量失败: {e}")

    return processed_count


def _count_chunks(kb_id: str) -> int:
    """统计知识库向量表中的分块总数（内部工具方法）"""
    try:
        with psycopg.connect(get_psycopg_db_url(id="official-kb-counter")) as conn:
            with conn.cursor() as cur:
                safe_kb_id = kb_id.replace("-", "_")
                cur.execute(f"SELECT COUNT(*) FROM {Config.DB_NAME}.{safe_kb_id}_knowledge_vectors")
                count = cur.fetchone()[0]
                return count
    except Exception as e:
        logger.error(f"统计知识库 {kb_id} 分块数量失败: {e}")
        return 0


def ensure_default_official_kbs() -> Dict[str, Optional[KnowledgeBaseRecord]]:
    """
    确保系统默认的官方知识库已创建

    建议在应用启动时调用此方法，自动创建不存在的官方知识库

    返回：
        字典：键为知识库名称，值为对应的知识库记录
    """
    # 定义系统默认的官方知识库列表
    default_kbs = [
        {
            "name": "System Documentation",
            "description": "Official system documentation and user guides",
            "documents": [],
        },
        {
            "name": "Code Architecture",
            "description": "Code architecture and design patterns",
            "documents": [],
        },
        {
            "name": "Data and Storage",
            "description": "Data configuration and storage conventions",
            "documents": [],
        },
    ]

    # 自动查找文档目录并匹配对应知识库
    docs_dir = Path("./docs/agent_docs")
    if docs_dir.exists():
        # 知识库名称与文档文件的映射关系
        doc_mapping = {
            "System Documentation": ["01_project_overview.md"],
            "Code Architecture": ["02_code_architecture.md"],
            "Data and Storage": ["05_data_config_and_storage.md"],
        }

        for kb_config in default_kbs:
            kb_name = kb_config["name"]
            if kb_name in doc_mapping:
                for doc_file in doc_mapping[kb_name]:
                    doc_path = docs_dir / doc_file
                    if doc_path.exists():
                        kb_config["documents"].append(str(doc_path))

    # 批量创建默认官方知识库
    results = {}
    for kb_config in default_kbs:
        try:
            kb_record = create_official_knowledge_base(
                name=kb_config["name"],
                description=kb_config["description"],
                initial_documents=kb_config.get("documents", []),
            )
            results[kb_config["name"]] = kb_record
        except Exception as e:
            logger.error(f"创建官方知识库失败 '{kb_config['name']}': {e}")
            results[kb_config["name"]] = None

    return results


def list_official_knowledge_bases() -> List[KnowledgeBaseRecord]:
    """列出所有启用状态的官方知识库"""
    return list_knowledge_bases(is_official=True, is_active=True)


def copy_official_kb_to_personal(
    source_kb_id: str,
    target_kb_id: str,
) -> Dict[str, int]:
    """
    将官方知识库的所有分块数据复制到个人知识库

    参数：
        source_kb_id: 源官方知识库ID
        target_kb_id: 目标个人知识库ID

    返回：
        字典：包含复制的分块数量和错误数量
    """
    # 校验源知识库必须是官方知识库
    source_kb = get_knowledge_base(source_kb_id)
    if not source_kb or not source_kb.is_official:
        raise ValueError("源必须是官方知识库")

    # 校验目标知识库存在
    target_kb = get_knowledge_base(target_kb_id)
    if not target_kb:
        raise ValueError("目标知识库不存在")

    safe_source_id = source_kb_id.replace("-", "_")
    safe_target_id = target_kb_id.replace("-", "_")

    chunks_copied = 0
    errors = 0

    try:
        with psycopg.connect(get_psycopg_db_url(id="official-kb-copy")) as conn:
            with conn.cursor() as cur:
                # 从源知识库读取所有分块数据
                cur.execute(f"""
                    SELECT embedding, data, meta
                    FROM {Config.DB_NAME}.{safe_source_id}_knowledge_vectors
                """)

                chunks = cur.fetchall()

                # 批量插入到目标知识库
                for embedding, data, meta in chunks:
                    try:
                        cur.execute(f"""
                            INSERT INTO {Config.DB_NAME}.{safe_target_id}_knowledge_vectors
                            (embedding, data, meta)
                            VALUES (%s, %s, %s)
                        """, (embedding, data, meta))
                        chunks_copied += 1
                    except Exception as e:
                        logger.error(f"复制分块数据失败: {e}")
                        errors += 1

                conn.commit()

        # 更新目标知识库的分块总数
        from auth.knowledge_db import update_kb_chunk_count
        update_kb_chunk_count(target_kb_id, increment=chunks_copied)

        logger.info(f"从 {source_kb_id} 向 {target_kb_id} 复制了 {chunks_copied} 个分块")

    except Exception as e:
        logger.error(f"复制知识库内容失败: {e}")
        raise

    return {
        "chunks_copied": chunks_copied,
        "errors": errors,
    }


def sync_official_kb_updates(
    source_kb_id: str,
    target_kb_ids: List[str],
) -> Dict[str, Dict[str, int]]:
    """
    将官方知识库的更新内容同步到多个由它复制而来的个人知识库

    参数：
        source_kb_id: 源官方知识库ID
        target_kb_ids: 需要同步的个人知识库ID列表

    返回：
        字典：键为目标知识库ID，值为同步结果
    """
    results = {}

    for target_kb_id in target_kb_ids:
        try:
            results[target_kb_id] = copy_official_kb_to_personal(source_kb_id, target_kb_id)
        except Exception as e:
            logger.error(f"同步到知识库 {target_kb_id} 失败: {e}")
            results[target_kb_id] = {"chunks_copied": 0, "errors": 1}

    return results