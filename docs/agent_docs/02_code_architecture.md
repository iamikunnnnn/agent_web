# 代码架构与装配链路

## 1. 顶层目录职责

### 1.1 主工程目录

- `agent/`
  - 每个文件定义一个 Agent 工厂函数 `create_*_agent`
- `team/`
  - 多 Agent 团队工厂
- `workflow/`
  - Workflow 工厂
- `api/`
  - 应用装配、注册、路由、监控
- `config/`
  - 模型、数据库、办公输出路径等统一配置
- `tools/`
  - 本地 Toolkit 和工具适配层
- `server/`
  - 独立服务实现，既有 Python MCP，也有 vendored Node 子项目
- `hook/`
  - 运行前后数据处理 hook
- `agent_manage/`
  - 动态保存/读取 agent 的实验性管理模块
- `tests/`
  - 主工程级测试

### 1.2 状态与缓存目录

- `db/`
  - 本地 SQLite、Chroma/向量库残留、浏览器 profile 目录等
- `user_cache/`
  - 运行期输出、模型缓存、GitHub reader staging、workspace
- `ml_models/`
  - 已训练模型示例
- `docs/`
  - 计划文档、知识文本、office 输入输出目录

### 1.3 特殊目录

- `server/meta_mcp/`
  - 完整独立的 TypeScript/Next.js/tRPC 子项目
  - 当前不是 Python 主链路的直接依赖
  - 除非任务明确要求，否则不要把这里当成“同一套架构”的一部分随意改动

## 2. 主应用装配链

主链路非常明确：

1. `main.py`
2. `api/main.py`
3. `api/init_agent.py`
4. `api/init_team.py`
5. `api/init_workflow.py`
6. `api/utils.py`
7. `AgentOS(...)`

### 2.1 `main.py`

这里只做三件事：

- Windows 下设置事件循环策略。
- 调用 `uvicorn.run("api.main:app", ...)`。
- 留下一些顶层 TODO。

意味着：

- 这里不应该塞业务逻辑。
- 任何应用级功能都应下沉到 `api/`。

### 2.2 `api/main.py`

这是主装配中心，职责包括：

- 初始化 OpenTelemetry / OpenInference。
- `load_dotenv()`。
- 创建 tracing db。
- 组装 `AgentOS`。
- 将 `manage_router` 挂到 app 上。
- 调用 `setup_prometheus_monitoring(...)`。

这里体现出项目的“统一组装后再暴露应用”的风格。后续新增跨系统能力时，优先在这里接线，不要绕开它直接改入口脚本。

## 3. 注册链路

### 3.1 Agents

`api/init_agent.py` 的模式是：

- 导入所有固定 Agent 工厂。
- 实例化内置 Agent。
- 从 `agent_manage.read_agent()` 读取动态 Agent。
- 过滤掉非 `Agent` 对象。
- 对每个 Agent 调用 `utils.set_default_config_to_agent(agent)`。

这最后一步非常关键。很多 Agent 工厂本身只声明少量属性，真正的一致性来自这个后置补配置函数。

### 3.2 Teams

`api/init_team.py` 当前只注册：

- `office_team`

团队注册相对克制，没有像 Agent 那样动态读取，也没有统一的 team 级补配置函数。

### 3.3 Workflows

`api/init_workflow.py` 当前为空：

- `all_workflows = []`

这不是“没有 workflow 实现”，而是“有实现但当前未接入主应用”。这是后续接手开发时非常容易误判的点。

## 4. 统一默认配置模型

`api/utils.py` 是整个项目的风格中枢。

### 4.1 它统一补了什么

- `agent.db = create_base_db(agent.id)`
- 默认 `model = get_ai_model()`
- 默认 `memory_manager`
- 默认 `knowledge = create_knowledge(...)`
- 打开 `search_knowledge` / `update_knowledge`
- 打开 `markdown`
- 打开 `stream`
- 打开 `debug_mode`
- 补充 `FileTools()` 和 `PythonTools()`

### 4.2 这意味着什么

- 新 Agent 工厂可以只写“差异化配置”。
- 但如果你显式设置了 model/db/knowledge，就要考虑会不会被这里覆盖。
- 如果某个 Agent 不应该带默认的 File/PythonTools，需要在补配置后再做裁剪，或者调整统一策略。

## 5. 配置层分工

### 5.1 `config/model_config.py`

负责：

- SiliconFlow/OpenAI-like 模型配置
- Azure embedder 配置
- `get_ai_model()`
- `get_siliconflow_embedder()`

### 5.2 `config/db_config.py`

负责：

- Postgres 会话 DB
- 知识库 contents DB
- PgVector / LightRag vector DB
- tracing DB
- 连接缓存
- `application_name` 风格的数据库 URL 生成

### 5.3 `config/office_config.py`

负责：

- 办公输入输出目录计算
- 默认 `docs/office/*` 路径体系
- `OFFICE_*` 环境变量覆盖

这三个配置文件的分工是清晰的：模型、数据库、文件路径各自独立，后续扩展最好保持这个边界。

## 6. 运行请求流

### 6.1 普通 AgentOS 请求

外部请求进入 `api.main` 创建的 FastAPI app 后，会走 AgentOS 自己的路由体系。当前仓库没有额外在 `api/` 中堆很多业务 API，而是把大多数能力放在 Agent/Team/Workflow 对象本身。

### 6.2 `/manage/save`

这是少数自定义路由之一：

- `api/manage.py`
- 调用 `agent_manage.save_agent(id)`
- 将返回的 agent append 到 `all_agents`

这个实现比较直接，说明当前动态管理能力还是原型级，不要把它误当成成熟的热更新系统。

### 6.3 `/prom-metrics`

监控链路由 `api/monitor.py` 完成：

- 使用独立 `CollectorRegistry`
- 通过 `prometheus_fastapi_instrumentator` 注入 HTTP 指标
- 通过进程内 `httpx.ASGITransport` 调用 AgentOS 自身 metrics 接口
- 为多个 `db_id` 聚合单库与全局指标

这里的实现非常重视可测试性与分层，文档、函数名、数据类都明显比项目其余模块更工程化。

## 7. 扩展推荐路径

### 7.1 新增一个工具能力

推荐顺序：

1. 判断是本地 `Toolkit` 还是远端 `MCP/HTTP service`
2. 在 `tools/` 或 `server/` 下实现
3. 在对应 Agent 工厂里挂载
4. 需要全局暴露时加入 `api/init_*`

### 7.2 新增一个 Agent

推荐模式：

1. 在 `agent/` 下新建 `create_xxx_agent`
2. 只写差异化 system/instructions/tools
3. 让 `api/utils.py` 补齐通用配置
4. 在 `api/init_agent.py` 注册

### 7.3 新增一个 Team

推荐模式：

1. 在 `team/` 下编排已有成员
2. Leader 层负责路由与交付校验
3. 在 `api/init_team.py` 注册

### 7.4 新增一个 Workflow

推荐模式：

1. 在 `workflow/` 下定义纯 workflow 逻辑
2. 先在局部测试稳定
3. 再决定是否加到 `api/init_workflow.py`

当前浏览器 workflow 就是一个典型例子：代码存在，但默认没有注册。

