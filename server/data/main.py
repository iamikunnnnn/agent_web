from fastapi import FastAPI

from server.data.data_process.router import processing_router
from server.data.machine_learning.router import ml_router

data_mcp_app = FastAPI()
data_mcp_app.include_router(processing_router)
data_mcp_app.include_router(ml_router)

from fastmcp import FastMCP

# 转换为 MCP 服务器
mcp = FastMCP.from_fastapi(app=data_mcp_app)

