from agno.agent import Agent

from agent.academic_agent import create_academic_agent
from agent.browser_use_agent import create_browser_use_agent
from agent.data_agent import create_data_agent
from agent.desktop_control_agent import create_desktop_control_agent
from agent.docx_use_agent import create_docx_use_agent
from agent.github_reader_agent import create_github_reader_agent
from agent.repo_monitor_agent import create_repo_monitor_agent
from agent.test_agent import create_test_agent
from agent.test_agent_2 import create_test_agent_2
from agent_manage.read_agent import read_agent
from api import utils

test_agent = create_test_agent(agent_id="test_agent")
test_agent_2 = create_test_agent_2(agent_id="test_agent_2")
data_agent = create_data_agent(agent_id="data_agent")
docx_use_agent = create_docx_use_agent(agent_id="docx_use_agent")
browser_use_agent = create_browser_use_agent(agent_id="browser_use_agent")
desktop_control_agent = create_desktop_control_agent(agent_id="desktop_control_agent")
academic_agent = create_academic_agent(agent_id="academic_agent")
github_reader_agent = create_github_reader_agent(agent_id="github_reader_agent")
repo_monitor_agent = create_repo_monitor_agent(agent_id="repo_monitor_agent")


all_agents = [
    test_agent,
    test_agent_2,
    data_agent,
    docx_use_agent,
    browser_use_agent,
    desktop_control_agent,
    academic_agent,
    github_reader_agent,
    repo_monitor_agent,
]

for agent in read_agent():
    all_agents.append(agent)

for agent in list(all_agents):
    if not isinstance(agent, Agent):
        all_agents.remove(agent)

if all_agents:
    for agent in all_agents:
        utils.set_default_config_to_agent(agent)
