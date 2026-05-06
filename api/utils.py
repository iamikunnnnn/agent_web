# todo 待agno的registry功能完善后，不必这么麻烦，可使用registry进行更完美的管理

from agno.agent import Agent
from agno.memory import MemoryManager
from agno.tools.file import FileTools
from agno.tools.python import PythonTools

from config.db_config import create_base_db, create_knowledge
from config.model_config import get_ai_model

def _process_agent_tool_entrypoints(agent: Agent):
    """Process entrypoints for all agent tools to extract descriptions from docstrings."""
    try:
        if not agent.tools:
            return
        from agno.tools import Toolkit
        from agno.tools.function import Function

        for tool in agent.tools:
            if isinstance(tool, Toolkit):
                for _, func in tool.functions.items():
                    if func.entrypoint and not func.skip_entrypoint_processing:
                        try:
                            # Only process if description is not already set
                            if not func.description:
                                func.process_entrypoint()
                        except Exception:
                            pass
            elif isinstance(tool, Function):
                if tool.entrypoint and not tool.skip_entrypoint_processing:
                    try:
                        if not tool.description:
                            tool.process_entrypoint()
                    except Exception:
                        pass
    except Exception:
        pass


def set_default_config_to_agent(agent: Agent):
    # unified config
    if isinstance(agent,Agent):
        agent.db = create_base_db(agent.id)
        # 如果 model 为 None 或是框架默认的 OpenAIChat(id="gpt-4o")，替换为系统的 get_ai_model()
        if not agent.model or (type(agent.model).__name__ == "OpenAIChat" and agent.model.id == "gpt-4o"):
            agent.model = get_ai_model()
        agent.memory_manager = agent.memory_manager or MemoryManager(model=get_ai_model(model_type="siliconflow"), db=agent.db,debug_mode=False)
        agent.knowledge = create_knowledge(id=agent.id,
                                            name=agent.id,
                                            description=f"Knowledge base for {agent.id}")

        # not default config
        agent.stream_intermediate_steps = True
        # agent.read_chat_history = True
        agent.add_history_to_context = True
        # 似乎开启这个以后，用户每轮消息都会被写入记忆。
        agent.enable_agentic_memory = True
        agent.store_history_messages=False
        # 每轮对话之后进行记忆
        # agent.enable_user_memories = True
        agent.search_knowledge = True
        agent.update_knowledge = True
        agent.markdown = True
        agent.add_datetime_to_context = True
        agent.debug_mode = True
        agent.stream = True
        agent.tools = agent.tools or []
        agent.tools.extend([FileTools(),PythonTools()])

        # Process tool entrypoints to ensure descriptions are extracted from docstrings
        _process_agent_tool_entrypoints(agent)
    else:
        return agent
