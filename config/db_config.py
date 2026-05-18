import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from agno.db.postgres import PostgresDb
from agno.knowledge import Knowledge
from agno.utils.log import logger
from agno.vectordb import VectorDb
from agno.vectordb.pgvector import PgVector
from agno.vectordb.search import SearchType
from dotenv import load_dotenv

from config.model_config import get_siliconflow_embedder

# 加载环境变量
load_dotenv()


class Config:
    """应用配置管理类"""

    # Vector DB 配置
    VECTOR_DB_TYPE: str = os.getenv("VECTOR_DB_TYPE", "pgvector")  # pgvector or lightrag

    # 数据库配置
    DB_DRIVER: str = os.getenv("DB_DRIVER", "postgresql+psycopg")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_USER: str = os.getenv("DB_USER", "ai")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "ai")
    DB_NAME: str = os.getenv("DB_NAME", "ai")

    # 应用程序标识符
    APPLICATION_NAME: str = os.getenv("AGNO_APPLICATION_NAME", "agno")

    @classmethod
    def validate_config(cls) -> bool:
        """验证必要的配置是否存在"""

        return True


def _build_base_db_url(driver: str) -> str:
    return "{}://{}{}@{}:{}/{}".format(
        driver,
        Config.DB_USER,
        f":{Config.DB_PASSWORD}" if Config.DB_PASSWORD else "",
        Config.DB_HOST,
        Config.DB_PORT,
        Config.DB_NAME,
    )


def _with_application_name(base_url: str, id: str | None = None) -> str:
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)

    app_name = f"{Config.APPLICATION_NAME}-{id or 'unknown'}"
    query_params["application_name"] = [app_name]

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_params, doseq=True),
            parsed.fragment,
        )
    )


def get_psycopg_db_url(id: str | None = None) -> str:
    """
    Build a psycopg-compatible PostgreSQL URL.

    psycopg accepts ``postgresql://`` URIs, but not SQLAlchemy dialect aliases
    such as ``postgresql+psycopg://``.
    """
    driver = Config.DB_DRIVER.split("+", 1)[0]
    if driver == "postgres":
        driver = "postgresql"
    return _with_application_name(_build_base_db_url(driver), id=id)


def create_knowledge_vector(id: str, **kwargs) -> VectorDb:
    """
    创建知识库VectorDB实例 (PgVector or Milvus)

    Args:
        id: Agent/Team 的唯一标识符，用于生成表名和连接名
        schema: 数据库模式 (for PgVector)
        **kwargs: 其他传递给VectorDB实例的参数

    Returns:
        VectorDb 实例 (PgVector or Milvus)
    """
    # 允许调用方显式覆盖 table_name，避免和默认命名重复传参
    table_name = kwargs.pop("table_name", f"{id}_knowledge_vectors")

    if Config.VECTOR_DB_TYPE.lower() == "lightrag":
        from agno.vectordb.lightrag import LightRag
        return LightRag(server_url=os.getenv("LIGHTRAG_SERVER_URL"), **kwargs)
    else:
        # 默认使用PgVector
        from agno.knowledge.reranker.cohere import CohereReranker
        return PgVector(table_name=table_name,
                        schema=Config.DB_NAME,
                        db_url=get_db_url(id=id),
                        search_type=SearchType.vector,
                        embedder=get_siliconflow_embedder(),
                        # 全文或混合搜索时才有用，而且需要在PostgreSQL中安装`pg_jieba`之类的中文分词扩展
                        # content_language= "chinese",
                        auto_upgrade_schema=True,
                        reranker=CohereReranker(model="rerank-v3.5"),
                        **kwargs)


def create_knowledge(id: str, name: str, description: str, max_results: int = 10) -> Knowledge:
    logger.debug(f"Creating knowledge base: id:{id} name:{name} with schema: {Config.DB_NAME}")
    vector_db = create_knowledge_vector(id=id)
    knowledge = Knowledge(
        name=name,
        description=description,
        vector_db=vector_db,
        contents_db=create_knowledge_db(id),
        max_results=max_results,
    )
    return knowledge


# 数据库实例缓存（分别缓存：基础会话DB、知识库DB、TracingDB）
_base_db_cache: dict[str, PostgresDb] = {}
_knowledge_db_cache: dict[str, PostgresDb] = {}
_tracing_db_cache: dict[str, PostgresDb] = {}


def create_base_db(id: str) -> PostgresDb:
    """
    获取数据库实例

    Args:
        id: Agent/Team 的唯一标识符

    Returns:
        PostgresDb 实例
    """

    # 复用缓存，避免重复创建连接池
    if id in _base_db_cache:
        cached_db = _base_db_cache[id]
        return cached_db

    db_instance = PostgresDb(
        id=id,
        db_schema=Config.DB_NAME,
        db_url=get_db_url(id=id),
        session_table=f"{id}_sessions",
        memory_table=f"{id}_memories",
        metrics_table=f"{id}_metrics",
        eval_table=f"{id}_eval_runs",
    )
    logger.debug(f"[DEBUG] PostgresDb created: id='{id}' -> db.id='{db_instance.id}', session_table='{db_instance.session_table_name}'")
    _base_db_cache[id] = db_instance
    return db_instance

def create_knowledge_db(id: str) -> PostgresDb:
    """
    创建数据库实例

    Args:
        id: Agent/Team 的唯一标识符

    Returns:
        PostgresDb 实例
    """

    # 复用缓存，避免重复创建连接池
    if id in _knowledge_db_cache:
        return _knowledge_db_cache[id]

    db_instance = PostgresDb(
        id=id,
        db_schema=Config.DB_NAME,
        db_url=get_db_url(id=f"{id}_knowledge"),
        knowledge_table=f"{id}_knowledge_contents",
    )
    _knowledge_db_cache[id] = db_instance
    return db_instance


def create_tracing_db(id: str = "tracing") -> PostgresDb:
    """
    创建 Tracing 专用数据库实例

    Args:
        id: Tracing 数据库的唯一标识符，默认为 "tracing"

    Returns:
        PostgresDb 实例，用于存储 traces 和 spans 数据

    Note:
        Tracing 数据使用默认表名（agno_traces, agno_spans），因为需要
        收集所有 Agent/Team 的追踪数据到同一个表中，以便全局可观测性。
    """
    # 复用缓存，避免重复创建连接池
    if id in _tracing_db_cache:
        return _tracing_db_cache[id]

    db_instance = PostgresDb(
        id=id,
        db_schema=Config.DB_NAME,
        db_url=get_db_url(id=id),
        # Tracing 表使用默认表名，不添加前缀
        # 这样所有 Agent/Team 的 traces 都存储在同一个表中
        traces_table="agno_traces",
        spans_table="agno_spans",
    )
    logger.debug(f"[DEBUG] TracingDb created: id='{id}' -> db.id='{db_instance.id}', "
                f"traces_table='{db_instance.trace_table_name}', spans_table='{db_instance.span_table_name}'")
    _tracing_db_cache[id] = db_instance
    return db_instance


def get_db_url(id: str = None) -> str:
    """
    生成数据库连接URL，包含application_name参数

    Args:
        id: Agent/Team 的唯一标识符，用于区分不同的连接来源

    Returns:
        包含application_name参数的数据库连接URL
    """
    return _with_application_name(_build_base_db_url(Config.DB_DRIVER), id=id)
