from agno.agent import Agent

from agent.data_agent import create_data_agent
from agent.docx_use_agent import create_docx_use_agent
from api import utils

data_agent = create_data_agent(agent_id="data_agent")
docx_use_agent = create_docx_use_agent(agent_id="docx_use_agent")

all_agents = [
    data_agent,
    docx_use_agent,
]

for agent in list(all_agents):
    if not isinstance(agent, Agent):
        all_agents.remove(agent)

if all_agents:
    for agent in all_agents:
        utils.set_default_config_to_agent(agent)
