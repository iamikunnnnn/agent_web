# 测试覆盖与开发流程

## 1. 现有测试大致在验证什么

当前 `tests/` 与 `server/web_driver_monitor/tests/` 主要覆盖的是“装配正确性”和“关键状态约束”，而不是端到端业务效果。

## 2. 主工程测试清单

### 2.1 `tests/test_api_main_teams.py`

验证：

- `api.main` 会把 agents / teams / workflows 传进 `AgentOS`
- Prometheus monitor 会拿到正确的 `dbs_id`

### 2.2 `tests/test_browser_use_agent_setup.py`

验证：

- `browser_use_agent` 使用 direct tools
- session state 上下文与 pre_hook 设置存在
- `api.init_agent` 会注册 browser agent
- `api.init_workflow` 当前不注册 browser workflow

### 2.3 `tests/test_office_team_setup.py`

验证：

- office 相关 toolkit 暴露预期方法
- `office_team` 组装了完整成员

### 2.4 `tests/test_office_paths.py`

验证：

- office toolkit 会优先使用环境变量驱动路径
- Markdown/PDF/文件工具不会硬编码输出目录

### 2.5 `tests/test_data_mcp_tool.py`

验证：

- `create_data_mcp_tools()` 正确读取 env URL

### 2.6 `tests/test_academic_*`

验证：

- `academic_agent` 已注册
- `AcademicSearchToolkit` 的核心接口存在
- arXiv / Semantic Scholar 的结果会被结构化归一

### 2.7 `tests/test_main_entrypoint.py`

验证：

- `main.py` 可以在没有 WindowsSelectorEventLoopPolicy 的环境里运行

## 3. 浏览器服务测试

`server/web_driver_monitor/tests/` 是项目中最像“子系统独立测试”的一组。

覆盖重点包括：

- app API
- runtime
- handle 组合逻辑
- browser workflow 状态规则

这说明作者对浏览器服务的工程要求高于项目其余部分。后续改浏览器相关代码，建议保持同等测试密度。

## 4. 测试策略风格

现有测试有几个明显特点：

- 大量使用 `patch.dict(sys.modules, ...)`
- 倾向于 mock 外部依赖
- 更重视“对象如何装配”和“状态是否正确设置”
- 较少直接连接真实数据库、真实模型、真实浏览器

这意味着后续补测试时，优先遵循：

- 先做构造/装配单测
- 再做少量子系统级真实测试
- 不要一上来只写端到端大集成测试

## 5. 当前测试缺口

### 5.1 动态 agent 管理

`agent_manage/save_agent.py` / `read_agent.py` 缺少直接测试。

### 5.2 data_agent 真实链路

缺少完整覆盖：

- 上传文件
- preprocess hook
- SQLite 映射
- data MCP 调用

### 5.3 docx MCP 集成

主工程层面对 `docx_use_agent` / `docx_use_team` 的测试很少，尤其缺少真正验证 `.docx` 交付结果的测试。

### 5.4 meta_mcp

当前基本没有纳入主工程测试语义。

### 5.5 路径漂移

存在 `tests/test_office_main_entrypoint.py` 期待 `office_main.py`，但当前源码中无此文件。说明测试资产与实现有历史漂移，需要人工判断。

## 6. 开发时建议的验证顺序

### 6.1 改配置/注册链路时

优先检查：

- `api.init_agent`
- `api.init_team`
- `api.init_workflow`
- `api.main`

### 6.2 改 office 链路时

优先检查：

- `tests/test_office_team_setup.py`
- `tests/test_office_paths.py`

### 6.3 改浏览器链路时

优先检查：

- `tests/test_browser_use_agent_setup.py`
- `tests/test_web_driver_monitor_toolkit.py`
- `server/web_driver_monitor/tests/*`

### 6.4 改学术工具时

优先检查：

- `tests/test_academic_agent_registration.py`
- `tests/test_academic_search_toolkit.py`

## 7. 开发风格建议

- 小步修改，优先保证装配链路不破。
- 新能力优先补针对性单测，而不是只改提示词。
- 如果测试与源码冲突，先确认当前生产链路，再决定是修代码还是修测试。

