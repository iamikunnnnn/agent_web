from openinference.instrumentation.agno import AgnoInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(
    SimpleSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
)
AgnoInstrumentor().instrument(tracer_provider=tracer_provider)


import os
from contextlib import asynccontextmanager

from agno.os import AgentOS
from agno.utils.log import log_info
from dotenv import load_dotenv

from api.init_agent import all_agents
from api.init_team import all_teams
from api.init_workflow import all_workflows
from api.manage import manage_router
from api.monitor import setup_prometheus_monitoring
from api.registry import registry
from config import db_config

load_dotenv()
db_path = os.getenv("AGENT_DB")


@asynccontextmanager
async def lifespan(app):
    log_info("--------------------Starting My FastAPI App--------------------")
    yield
    log_info("--------------------Stopping My FastAPI App--------------------")


tracing_db = db_config.create_tracing_db(id="tracing")
agent_os = AgentOS(
    description="AgentOS v2.4",
    agents=all_agents,
    teams=all_teams,
    workflows=all_workflows,
    lifespan=lifespan,
    db=tracing_db,
    registry=registry,
    tracing=True,
)
app = agent_os.get_app()

app.include_router(manage_router)

setup_prometheus_monitoring(
    app=app,
    agent_os=agent_os,
    endpoint="/prom-metrics",
    refresh_interval_s=30,
    dbs_id=[agent.id for agent in all_agents if agent.db.id == agent.id]
    + [workflow.id for workflow in all_workflows if workflow.db.id == workflow.id]
    + [team.id for team in all_teams if team.db.id == team.id],
)
