# 数据、配置与存储约定

## 1. 运行时配置来源

整个仓库的默认模式是：

- 根目录 `.env`
- `python-dotenv` 在多个入口和配置模块中读取
- Docker Compose 再把同一份 `.env` 注入容器

这意味着：

- 环境变量是第一配置层
- 代码里虽然有少量硬编码/实验配置，但长期应尽量回收为 env

## 2. 模型配置

`config/model_config.py` 当前主线是：

- 默认聊天模型：SiliconFlow 风格 `OpenAILike`
- 向量嵌入：Azure OpenAI Embedder

几个实际含义：

- 聊天模型和向量模型不是同一路 provider
- 新增 Agent 默认会共享这一套模型配置，除非显式覆盖
- 如果要引入新 provider，优先在 `config/model_config.py` 扩展，而不是在各个 Agent 文件里复制配置

## 3. 数据库与知识库存储

## 3.1 主会话库

`config/db_config.py` 使用 `PostgresDb` 创建：

- session table
- memory table
- metrics table
- eval table

命名规则基于对象 id，例如：

- `<agent_id>_sessions`
- `<agent_id>_memories`

## 3.2 知识库

每个对象默认还会获得：

- 一个 vector db
- 一个 knowledge contents db

当前 vector db 默认是 `PgVector`，表名规则：

- `<id>_knowledge_vectors`

knowledge contents 规则：

- `<id>_knowledge_contents`

## 3.3 tracing 库

主应用还会单独创建 tracing db：

- traces 表统一为 `agno_traces`
- spans 表统一为 `agno_spans`

这说明 tracing 是全局聚合的，而不是每个 agent 各自一套表。

## 4. 办公目录约定

`config/office_config.py` 定义默认路径：

- `docs/office/input`
- `docs/office/output`
- `docs/office/output/docx`
- `docs/office/output/markdown`
- `docs/office/output/pdf`
- `docs/office/output/search`

可被环境变量覆盖：

- `OFFICE_BASE_DIR`
- `OFFICE_INPUT_DIR`
- `OFFICE_OUTPUT_DIR`
- `OFFICE_DOCX_OUTPUT_DIR`
- `OFFICE_MARKDOWN_OUTPUT_DIR`
- `OFFICE_PDF_OUTPUT_DIR`
- `OFFICE_SEARCH_OUTPUT_DIR`

后续新增 office 输出类型时，最好沿用这套：

- `config/office_config.py` 增加 path 映射
- `OfficeFileToolkit` 暴露统一路径构建接口

## 5. 数据 Agent 的文件落地方式

`hook/preprocess.py` 的逻辑是：

1. 接收上传文件
2. 存到 `user_cache/workspace`
3. 把路径写入 `DATA_DB_PATH` 指向的 SQLite 中
4. 记录到 `user_data(user_id, data_path)`

当前特点：

- `user_id` 还是硬编码 `"JinDong"`
- 这是明显的临时实现
- 但它解释了为什么 data MCP 侧能只靠 `user_id` 找到当前 CSV

所以如果你要修 data_agent，多半要同时考虑：

- hook 层 user_id 来源
- SQLite 映射表结构
- MCP 请求头传递

## 6. 本地缓存目录

### 6.1 `user_cache/`

重要子目录包括：

- `workspace`
  - 上传文件和运行期工作区
- `ml_models`
  - 训练结果
- `github_repo_reader_clone`
  - repo reader staging/cache

### 6.2 `ml_models/`

根目录还有 `ml_models/`，里面已有 `joblib` 文件示例。说明训练产物在历史上既放过 `user_cache/ml_models`，也放过根级 `ml_models`，路径策略并不完全统一。

## 7. 浏览器持久化状态

`server/web_driver_monitor/config.py` 定义浏览器相关 env：

- `WDM_HOST`
- `WDM_PORT`
- `WDM_BROWSER`
- `WDM_HEADLESS`
- `WDM_BROWSER_CHANNEL`
- `WDM_USER_DATA_DIR`
- `WDM_BROWSER_PROFILE_DIR`
- `WDM_STORAGE_STATE_PATH`

关键点：

- 浏览器运行在独立 persistent profile 上
- 可以导入 Playwright storage state
- 目标是复用登录态，但避免和日常浏览器 profile 锁冲突

## 8. Docker 运行拓扑

`docker-compose.yaml` 的默认端口：

- app: `8005`
- data-mcp: `8085`
- docx-use-mcp: `8008`
- browser-mcp: `8010`

容器内主应用依赖服务名调用：

- `http://data-mcp:8085/mcp`
- `http://docx-use-mcp:8008/mcp`
- `http://browser-mcp:8010`

这说明：

- 本地开发可以走 localhost
- 容器内调用要走 service name
- 后续写文档或样例时不要把这两种地址混用

## 9. 需要特别小心的配置问题

- `api/registry.py` 里存在不应长期保留的 provider 级硬编码配置，后续重构时应改成环境变量。
- `.env` 已被 `.gitignore` 忽略，说明仓库意图是不提交真实密钥。
- 任何新增模型、服务 URL、数据库参数，都应尽量走 `config/* + env`，不要在 Agent 工厂里散落硬编码。

