import asyncio

import uvicorn
# todo 后续可以在系统中加上用户系统，加上鉴权功能，试试 supabase
# todo 把meta_mcp加到docker-compose,然后可以把clone来的meta_mcp删掉了

# todo 思考data_agent的数据到底是用本地的还是数据库软链，还是都要？
# todo 添加pdf_agent
if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
if __name__ == '__main__':

    uvicorn.run(
        "api.main:app",  # 使用导入字符串而不是应用实例
        host="0.0.0.0",  # 允许外部访问
        port=8005,
        reload=True,
        log_level="debug",
        access_log=True,
    )

