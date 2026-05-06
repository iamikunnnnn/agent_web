"""
This cookbook demonstrates how to save an agent to the database.
"""
from contextlib import suppress

from agno.agent.agent import Agent
from agno.utils.log import logger

from config import db_config


def save_agent(id,*args):
    """
    创建agent
    :param id:
    :return:
    """
    with suppress(Exception): # 不影响实际业务，静默处理
        # todo 把agent的可用参数真正移植出来，这里先留个展示
        agent_param=Agent.__init__.__code__.co_varnames
        print("已获取Agent可设置参数",agent_param)
    try:
        # Use Postgres for persistence (aligns with read_agent.py / db_config.py)
        db = db_config.create_base_db(id=id)
        agent = Agent(
            id=id,
            name=f"Agno_Agent_{id}",
            db=db,

        )
        # agent.print_response("How many people live in Canada?")

        # Save the agent to the database
        # todo 这个存储看看能不能做成异步的
        version = agent.save()

        print(f"Saved agent as version {version}")
        return agent
    except Exception as e:
        logger.error("储存agent失败",e)
        return

