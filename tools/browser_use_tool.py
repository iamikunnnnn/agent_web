
from browser_use import Agent, ChatOpenAI

from config.model_config import Config


def _get_browser_use_LLM():
    return ChatOpenAI(
        **Config.get_browser_use_config(id="Qwen/Qwen3-VL-32B-Instruct")

    )
async def browser_use_tool(task):
    try:
        agent = Agent(
            task=task,
            llm=_get_browser_use_LLM(),
        )
        history = await agent.run(max_steps=100)
        return history
    except:
        return 0
