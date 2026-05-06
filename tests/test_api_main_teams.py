from __future__ import annotations

import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ApiMainTeamsTests(unittest.TestCase):
    def test_api_main_registers_teams_with_agent_os(self) -> None:
        fake_openinference_root = types.ModuleType("openinference")
        fake_openinference_instr_pkg = types.ModuleType("openinference.instrumentation")
        fake_openinference_agno = types.ModuleType("openinference.instrumentation.agno")

        class FakeAgnoInstrumentor:
            def instrument(self, **kwargs) -> None:
                self.instrument_kwargs = kwargs

        fake_openinference_agno.AgnoInstrumentor = FakeAgnoInstrumentor

        fake_otlp_module = types.ModuleType("opentelemetry.exporter.otlp.proto.http.trace_exporter")
        fake_otlp_module.OTLPSpanExporter = Mock(return_value="exporter")

        fake_trace_module = types.ModuleType("opentelemetry.sdk.trace")

        class FakeTracerProvider:
            def __init__(self) -> None:
                self.processors = []

            def add_span_processor(self, processor) -> None:
                self.processors.append(processor)

        fake_trace_module.TracerProvider = FakeTracerProvider

        fake_trace_export_module = types.ModuleType("opentelemetry.sdk.trace.export")
        fake_trace_export_module.SimpleSpanProcessor = Mock(side_effect=lambda exporter: ("processor", exporter))

        fake_monitor_module = types.ModuleType("api.monitor")
        fake_monitor_module.setup_prometheus_monitoring = Mock()

        fake_manage_module = types.ModuleType("api.manage")
        fake_manage_module.manage_router = object()

        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = Mock()

        fake_db_config = types.ModuleType("config.db_config")
        fake_db_config.create_tracing_db = Mock(return_value="tracing-db")

        fake_model_config = types.ModuleType("config.model_config")

        fake_registry_module = types.ModuleType("api.registry")
        fake_registry_module.registry = "registry"

        fake_init_agent = types.ModuleType("api.init_agent")
        fake_agent = types.SimpleNamespace(id="agent-a", db=types.SimpleNamespace(id="agent-a"))
        fake_init_agent.all_agents = [fake_agent]

        fake_init_workflow = types.ModuleType("api.init_workflow")
        fake_workflow = types.SimpleNamespace(id="workflow-a", db=types.SimpleNamespace(id="workflow-a"))
        fake_init_workflow.all_workflows = [fake_workflow]

        fake_init_team = types.ModuleType("api.init_team")
        fake_team = types.SimpleNamespace(id="office_team", db=types.SimpleNamespace(id="office_team"))
        fake_init_team.all_teams = [fake_team]

        fake_agno_db = types.ModuleType("agno.db")
        fake_agno_db.BaseDb = object

        fake_agno_sqlite = types.ModuleType("agno.db.sqlite")
        fake_agno_sqlite.SqliteDb = object

        fake_agno_utils_log = types.ModuleType("agno.utils.log")
        fake_agno_utils_log.log_info = Mock()

        fake_agent_os_ctor = Mock()

        class FakeAgentOS:
            def __init__(self, **kwargs) -> None:
                fake_agent_os_ctor(**kwargs)
                self.kwargs = kwargs

            def get_app(self):
                app = types.SimpleNamespace()
                app.include_router = Mock()
                return app

        fake_agno_os = types.ModuleType("agno.os")
        fake_agno_os.AgentOS = FakeAgentOS

        with patch.dict(
            sys.modules,
            {
                "openinference": fake_openinference_root,
                "openinference.instrumentation": fake_openinference_instr_pkg,
                "openinference.instrumentation.agno": fake_openinference_agno,
                "opentelemetry.exporter.otlp.proto.http.trace_exporter": fake_otlp_module,
                "opentelemetry.sdk.trace": fake_trace_module,
                "opentelemetry.sdk.trace.export": fake_trace_export_module,
                "api.monitor": fake_monitor_module,
                "api.manage": fake_manage_module,
                "dotenv": fake_dotenv,
                "config.db_config": fake_db_config,
                "config.model_config": fake_model_config,
                "api.registry": fake_registry_module,
                "api.init_agent": fake_init_agent,
                "api.init_workflow": fake_init_workflow,
                "api.init_team": fake_init_team,
                "agno.db": fake_agno_db,
                "agno.db.sqlite": fake_agno_sqlite,
                "agno.utils.log": fake_agno_utils_log,
                "agno.os": fake_agno_os,
            },
            clear=False,
        ):
            sys.modules.pop("api.main", None)
            runpy.run_module("api.main", run_name="api.main")

        fake_agent_os_ctor.assert_called_once()
        kwargs = fake_agent_os_ctor.call_args.kwargs
        self.assertEqual(kwargs["agents"], [fake_agent])
        self.assertEqual(kwargs["workflows"], [fake_workflow])
        self.assertEqual(kwargs["teams"], [fake_team])

        fake_monitor_module.setup_prometheus_monitoring.assert_called_once()
        monitoring_kwargs = fake_monitor_module.setup_prometheus_monitoring.call_args.kwargs
        self.assertEqual(
            monitoring_kwargs["dbs_id"],
            ["agent-a", "workflow-a", "office_team"],
        )


if __name__ == "__main__":
    unittest.main()
