# 项目总览

## 1. 项目定位

这个仓库不是单一 Agent，而是一套围绕 Agno 的“AgentOS 业务容器”。它把多个能力域放进同一个 Python 工程里：

- 通用 AgentOS API 服务。
- 办公文档生成与改写。
- 通过 MCP 暴露的数据预处理和机器学习训练能力。
- 基于持久化 Playwright 会话的浏览器自动化。
- 学术搜索、GitHub 仓库读取等辅助型 Agent。

主入口是根目录 `main.py`，它只负责启动 Uvicorn。真正的应用实例在 `api/main.py` 里由 `AgentOS` 装配完成。

## 2. 当前核心能力

### 2.1 AgentOS 主应用

- 入口：`main.py` -> `api.main:app`
- 监听端口：`8005`
- 核心职责：
  - 注册全部 agents、teams、workflows。
  - 为这些对象统一挂默认模型、数据库、知识库、memory。
  - 暴露管理路由 `/manage/save`。
  - 暴露 Prometheus 监控端点 `/prom-metrics`。

### 2.2 办公文档链路

当前有两条并行思路：

- `office_team`
  - 面向“Leader + 多专家”编排。
  - 能按输出格式把任务分派给 Word / Markdown / PDF / Search 子成员。
- `docx_use_agent`
  - 面向更聚焦的 `.docx` 操作。
  - 直接通过远端 `docx_use_mcp` 服务调用 Word 文档工具。

这说明作者在探索两种形态：

- 一种是多成员团队式办公自动化。
- 一种是单专家 Agent + MCP 工具的垂直型文档处理。

### 2.3 数据处理链路

- `data_agent` 不直接在本地做 pandas/sklearn 运算。
- 它通过 `tools/mcp_tools/data_mcp_tool.py` 连接 `server/data` 暴露出的 MCP 服务。
- 数据服务内部又分成两类：
  - `data_process`: CSV 级预处理。
  - `machine_learning`: 训练和保存 sklearn 模型。

这里的设计目标很明确：把重 CPU 或状态性数据操作从 Agent 本体里剥离出去，变成可复用的 MCP/HTTP 能力。

### 2.4 浏览器自动化链路

浏览器能力也分成两层：

- 直接工具层：
  - `tools/web_driver_monitor_toolkit.py`
  - 通过 HTTP 请求 `server/web_driver_monitor`
  - 执行原子 DOM 操作并返回“压缩摘要 + 当前轮原始快照”
- 工作流层：
  - `workflow/browser_workflow.py`
  - 通过 observe / decide / execute / verify 循环来做多轮浏览器任务

注意当前 `api/init_workflow.py` 里 `all_workflows = []`，也就是浏览器 workflow 已实现，但默认没有注册到主应用里。当前主链路更偏向直接工具式 browser agent。

### 2.5 学术与仓库辅助链路

- `academic_agent`
  - 聚合 DDGS、Baidu、arXiv、Semantic Scholar、GitHub、YouTube 等检索能力。
- `github_reader_agent`
  - 负责 shallow clone、本地仓库解析、分块写入知识库。

它们更像“专题工具 Agent”，不参与主业务编排，但可以作为后续通用能力库。

## 3. 运行拓扑

当前仓库默认通过 `docker-compose.yaml` 把系统拆成 4 个服务：

- `app`
  - 主 AgentOS 服务，端口 `8005`
- `data-mcp`
  - 数据 MCP 服务，端口 `8085`
- `docx-use-mcp`
  - Word 文档 MCP 服务，端口 `8008`
- `browser-mcp`
  - Playwright 持久浏览器服务，端口 `8010`

主应用通过环境变量引用其他服务：

- `DATA_MCP_URL`
- `DOCX_USE_MCP_URL`
- `WDM_URL`

这说明当前推荐的部署形态不是单进程全塞在一起，而是：

- AgentOS 负责编排。
- 能力型服务独立运行。
- Agent 通过 Toolkit 或 MCPTools 远程访问这些能力。

## 4. 代码状态判断

### 4.1 相对稳定的部分

- `api.main` 的 AgentOS 装配主线。
- `api.utils.set_default_config_to_agent` 的统一补配置逻辑。
- `team/office_team.py` 及其相关 office toolkit。
- `tools/web_driver_monitor_toolkit.py` + `server/web_driver_monitor/*`
- `tools/academic_search_toolkit.py`
- `tools/github_reader_toolkit.py`
- `server/data/*` 的数据预处理与训练分层。

### 4.2 明显在演进中的部分

- `api/registry.py`
  - 目前更像实验性 registry。
  - 还混入了硬编码 provider 配置。
- `agent_manage/save_agent.py` / `read_agent.py`
  - 已能保存/读取，但还远未形成完整的动态 agent 管理系统。
- `knowledge/add.py`
  - 逻辑非常简陋，直接写 `docs/knowledge.txt`。
- `server/data/stat_analyse/stat_analyse.py`
  - 注释明确说是后续再完成。
- `server/meta_mcp`
  - 是一个完整的外部子项目，但当前没有融入主 docker-compose 主链路。

### 4.3 有漂移迹象的部分

- 根目录存在 `tests/test_office_main_entrypoint.py`，但当前跟踪文件里并没有 `office_main.py`。
- 这类情况说明历史设计、计划文档、测试和当前源码并非完全同步。
- 后续开发不能只看测试结论，必须同时核对当前注册链路与当前源码是否一致。

## 5. 项目最重要的设计思路

如果只提炼一条，这个项目最核心的思路是：

“把 Agent 当成编排层，把真正重、专、状态化的能力下沉到 tool/server，再由统一配置函数给所有 Agent 补齐默认运行能力。”

这决定了后续开发应该优先遵循的顺序是：

1. 先明确能力应该放在本地 Toolkit 还是独立服务。
2. 再决定由哪个 Agent / Team / Workflow 使用它。
3. 最后才把它挂到 AgentOS 注册链路里。

