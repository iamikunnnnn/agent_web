# Agent Development Index

本文档是后续 agent 接手本仓库时的入口索引。先读这里，再按顺序阅读 `agent_docs/` 下的专题文档。

## 先读结论

- 这是一个以 `Agno + FastAPI + MCP` 为核心的多 Agent 编排项目，主入口是根目录 [main.py](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/main.py)，实际应用装配在 [api/main.py](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/main.py)。
- 主工程是 Python 3.12。仓库内还内嵌了一个相对独立的 Node/Next.js 子项目 `server/meta_mcp`，它更像 vendored upstream，不是当前 Python 主链路的一部分。
- 当前“真的在跑”的核心能力主要有四条：AgentOS 装配、办公文档团队、数据处理/训练 MCP、浏览器监控服务。
- 新功能尽量沿用现有模式扩展：先做 `tool/server`，再做 `agent/team/workflow` 声明，最后在 `api/init_*` 中注册，不要直接在 `api.main` 写业务逻辑。
- 项目里存在一些实验性、半成品和待清理模块，尤其是 `registry`、动态 agent 保存/读取、`knowledge/add.py`、`server/meta_mcp` 接入、`stat_analyse`、部分测试残留。

## 推荐阅读顺序

1. [agent_docs/01_project_overview.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/01_project_overview.md)
2. [agent_docs/02_code_architecture.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/02_code_architecture.md)
3. [agent_docs/03_agents_teams_workflows.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/03_agents_teams_workflows.md)
4. [agent_docs/04_tools_and_servers.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/04_tools_and_servers.md)
5. [agent_docs/05_data_config_and_storage.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/05_data_config_and_storage.md)
6. [agent_docs/06_tests_and_dev_workflow.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/06_tests_and_dev_workflow.md)
7. [agent_docs/07_pending_work_and_style_guide.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/07_pending_work_and_style_guide.md)

## 文档说明

- [agent_docs/01_project_overview.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/01_project_overview.md): 项目目标、当前能力面、运行拓扑、模块状态总览。
- [agent_docs/02_code_architecture.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/02_code_architecture.md): 代码分层、装配链路、请求流、扩展路径。
- [agent_docs/03_agents_teams_workflows.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/03_agents_teams_workflows.md): 每个 agent/team/workflow 的职责、工具、特殊配置与协作方式。
- [agent_docs/04_tools_and_servers.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/04_tools_and_servers.md): Toolkit、MCP、浏览器服务、文档服务、数据服务、GitHub/学术工具的实现边界。
- [agent_docs/05_data_config_and_storage.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/05_data_config_and_storage.md): 环境变量、数据库、向量库、缓存、工作目录、Docker 拓扑。
- [agent_docs/06_tests_and_dev_workflow.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/06_tests_and_dev_workflow.md): 测试覆盖、验证重点、开发时的运行方式与注意事项。
- [agent_docs/07_pending_work_and_style_guide.md](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/agent_docs/07_pending_work_and_style_guide.md): 待开发内容、技术债、风格约束、推荐改法。

## 使用规则

- 如果任务只涉及 Python 主工程，默认忽略 `server/meta_mcp`，除非需求明确点名它。
- 如果任务涉及 agent 默认行为，先看 [api/utils.py](/C:/Users/WUJIEAI/PycharmProjects/my_agents_newFeatureExplore/agent_manage/api/utils.py)，因为很多统一配置是在注册后补上的。
- 如果任务涉及浏览器自动化，先区分是“直接工具调用”还是“工作流循环”，对应文档里两种不同状态模型。
- 如果任务涉及数据处理，先确认 `DATA_DB_PATH` 指向的 SQLite 元数据库是否存在，因为 `data_agent` 的很多能力都依赖 `user_id -> CSV 路径` 映射。
- 如果任务涉及文档生成，先区分是 `office_team` 路径还是 `docx_use_agent` 单 Agent 路径，它们能力重叠但定位不同。
- 如果发现测试和实际代码不一致，以“当前被跟踪的源码 + 当前注册链路”为准，同时把不一致记录到变更说明里。
- 如果发现agent的能力需要写某些工具，且这些工具非常耗资源，需要让工具server化，使用作为微服务写到./server然后作为mcp被注册，注册方式同data_mcp_main.py


## agno源码
1. 非必要无需读取，除非你发现某个需求在之前的代码中都没有提到，你需要知道agno是否存在该能力：C:\Users\WUJIEAI\PycharmProjects\my_agents_newFeatureExplore\agno_fork
2. 你可以在目录下调用`python agent_chat.py --agent_id "github_reader_agent" --message ""`，然后等待stdio输出，github_reader_agent是本地的一个源码阅读agent，它的知识库有agno源码，如果你需要了解agno的某个能力，可以尝试调用它来询问。
