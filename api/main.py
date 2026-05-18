import os
import re
from contextlib import asynccontextmanager

from agno.os import AgentOS
from agno.os.interfaces.agui import AGUI
from agno.utils.log import log_info
from dotenv import load_dotenv
from fastapi.routing import APIRoute

from api.init_agent import all_agents
from api.init_team import all_teams
from api.init_workflow import all_workflows
from api.monitor import setup_prometheus_monitoring
from config import db_config

load_dotenv()


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _setup_tracing() -> None:
    if not _get_bool_env("ENABLE_OTLP_TRACING", False):
        log_info("未启用 OTLP tracing，跳过链路追踪初始化")
        return

    otlp_endpoint = os.getenv("OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")

    try:
        from openinference.instrumentation.agno import AgnoInstrumentor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
        AgnoInstrumentor().instrument(tracer_provider=tracer_provider)
        log_info(f"OTLP tracing 已启用，目标端点: {otlp_endpoint}")
    except Exception as exc:
        log_info(f"OTLP tracing 初始化失败，已跳过: {exc}")


def _init_knowledge_db() -> None:
    try:
        import psycopg
        from auth.user_db import create_knowledge_tables
        from config.db_config import get_psycopg_db_url

        db_url = get_psycopg_db_url(id="knowledge-init")
        with psycopg.connect(db_url) as conn:
            create_knowledge_tables(conn)
        log_info("知识库表初始化完成")
    except Exception as exc:
        log_info(f"知识库表初始化已跳过，数据库暂不可用: {exc}")


def _dedupe_operation_ids() -> None:
    duplicate_routes: dict[str, list[APIRoute]] = {}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.operation_id:
            duplicate_routes.setdefault(route.operation_id, []).append(route)

    for operation_id, routes in duplicate_routes.items():
        if len(routes) <= 1:
            continue

        for route in routes[1:]:
            path_suffix = re.sub(r"[^a-zA-Z0-9_]+", "_", route.path).strip("_") or "root"
            method_suffix = "_".join(sorted(m.lower() for m in (route.methods or {"get"})))
            route.operation_id = f"{operation_id}_{method_suffix}_{path_suffix}"

        log_info(f"已修正重复 OpenAPI operationId: {operation_id} -> {len(routes)} routes")


@asynccontextmanager
async def lifespan(app):
    from knowledge.processor import start_file_processor, stop_file_processor
    from auth.official_kb import ensure_default_official_kbs

    log_info("开始启动 Agent 服务")
    _init_knowledge_db()

    # Start file processor
    try:
        await start_file_processor()
        log_info("文件处理器已启动")
    except Exception as exc:
        log_info(f"文件处理器启动失败: {exc}")

    # Initialize default official knowledge bases
    try:
        official_kbs = ensure_default_official_kbs()
        created_count = sum(1 for kb in official_kbs.values() if kb is not None)
        log_info(f"官方知识库初始化完成，共 {created_count} 个")
    except Exception as exc:
        log_info(f"官方知识库初始化失败: {exc}")

    log_info(f"已加载 Agent 数量: {len(all_agents)}")
    log_info(f"已加载 Team 数量: {len(all_teams)}")
    log_info(f"已加载 Workflow 数量: {len(all_workflows)}")
    log_info(f"已加载 AGUI 接口数量: {len(agui_interfaces)}")
    yield

    # Cleanup
    try:
        await stop_file_processor()
        log_info("文件处理器已停止")
    except Exception as exc:
        log_info(f"文件处理器停止失败: {exc}")

    log_info("Agent 服务已停止")


_setup_tracing()
tracing_db = db_config.create_tracing_db(id="tracing")
agui_interfaces = [AGUI(agent=agent, prefix=f"/agents/{agent.id}") for agent in all_agents] + [
    AGUI(team=team, prefix=f"/teams/{team.id}") for team in all_teams
]
agent_os = AgentOS(
    description="AgentOS v2.4",
    agents=all_agents,
    teams=all_teams,
    workflows=all_workflows,
    interfaces=agui_interfaces,
    lifespan=lifespan,
    db=tracing_db,
    tracing=_get_bool_env("ENABLE_OTLP_TRACING", False),
    cors_allowed_origins=["https://os.agno.com"],
)
app = agent_os.get_app()
_dedupe_operation_ids()
app.openapi_schema = None

from auth.middleware import AuthMiddleware

app.add_middleware(AuthMiddleware)
log_info("已注册网关认证中间件")

# Register knowledge base router
from api.knowledge_router import knowledge_router
app.include_router(knowledge_router)
log_info("已注册知识库管理路由")

setup_prometheus_monitoring(
    app=app,
    agent_os=agent_os,
    endpoint="/prom-metrics",
    refresh_interval_s=30,
    dbs_id=[agent.id for agent in all_agents if agent.db.id == agent.id]
    + [workflow.id for workflow in all_workflows if workflow.db.id == workflow.id]
    + [team.id for team in all_teams if team.db.id == team.id],
)
