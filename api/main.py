import os
from contextlib import asynccontextmanager

from agno.os import AgentOS
from agno.utils.log import log_info
from dotenv import load_dotenv

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


def _init_auth_db() -> None:
    try:
        import psycopg
        from auth.db import create_user_table
        from config.db_config import Config

        db_url = "{}://{}{}@{}:{}/{}".format(
            Config.DB_DRIVER,
            Config.DB_USER,
            f":{Config.DB_PASSWORD}" if Config.DB_PASSWORD else "",
            Config.DB_HOST,
            Config.DB_PORT,
            Config.DB_NAME,
        )
        with psycopg.connect(db_url) as conn:
            create_user_table(conn)
        log_info("认证用户表初始化完成")
    except Exception as exc:
        log_info(f"认证用户表初始化已跳过，数据库暂不可用: {exc}")


@asynccontextmanager
async def lifespan(app):
    from auth.config import AuthConfig

    log_info("开始启动 Agent 服务")
    AuthConfig.validate()
    log_info("Supabase 鉴权配置校验通过")
    _init_auth_db()
    log_info(f"已加载 Agent 数量: {len(all_agents)}")
    log_info(f"已加载 Team 数量: {len(all_teams)}")
    log_info(f"已加载 Workflow 数量: {len(all_workflows)}")
    yield
    log_info("Agent 服务已停止")


_setup_tracing()
tracing_db = db_config.create_tracing_db(id="tracing")
agent_os = AgentOS(
    description="AgentOS v2.4",
    agents=all_agents,
    teams=all_teams,
    workflows=all_workflows,
    lifespan=lifespan,
    db=tracing_db,
    tracing=_get_bool_env("ENABLE_OTLP_TRACING", False),
)
app = agent_os.get_app()

from auth.middleware import JWTMiddleware

app.add_middleware(JWTMiddleware)
log_info("已启用 Supabase JWT 鉴权中间件")

setup_prometheus_monitoring(
    app=app,
    agent_os=agent_os,
    endpoint="/prom-metrics",
    refresh_interval_s=30,
    dbs_id=[agent.id for agent in all_agents if agent.db.id == agent.id]
    + [workflow.id for workflow in all_workflows if workflow.db.id == workflow.id]
    + [team.id for team in all_teams if team.db.id == team.id],
)
