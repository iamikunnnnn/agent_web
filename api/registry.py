# 可供agent创建时选择的工具，暂不维护，后续反向优化时考虑人工考虑应该放哪些工具。
import os

from agno.models.azure import AzureOpenAI
from agno.models.siliconflow import Siliconflow
from agno.registry import Registry
from agno.tools.file import FileTools
from agno.tools.python import PythonTools
from dotenv import load_dotenv

from tools.github_reader_toolkit import GitHubReaderToolkit
from tools.test_agent_tool import test_agent_tool

# from tools.web_driver_monitor_toolkit import (
#     web_driver_click,
#     web_driver_click_text,
#     web_driver_event,
#     web_driver_goto,
# )
load_dotenv()
SILICONFLOW_API_KEY=os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BESE_URL=os.getenv("SILICONFLOW_BESE_URL")
SILICONFLOW_MODEL_ID=os.getenv("SILICONFLOW_MODEL_ID")

registry=Registry(
    models=[
        Siliconflow(
            id= SILICONFLOW_MODEL_ID,
            api_key= SILICONFLOW_API_KEY,
            base_url= SILICONFLOW_BESE_URL,
            provider="siliconflow"
        ),
        Siliconflow(
            id= "Pro/moonshotai/Kimi-K2.5",
            api_key= SILICONFLOW_API_KEY,
            base_url= SILICONFLOW_BESE_URL,
            provider="siliconflow"
        ),

    ],
    tools=[
        test_agent_tool,
        GitHubReaderToolkit(),
        # create_data_mcp_tools(),
        # web_driver_event,
        # web_driver_goto,
        # web_driver_click,
        # web_driver_click_text,
        FileTools(),
        PythonTools()
    ],

)
