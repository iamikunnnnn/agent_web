# Tools 与服务边界

## 1. 本地 Toolkit 总览

### 1.1 `OfficeFileToolkit`

作用：

- 获取办公目录
- 构造输出路径
- 解析输入路径
- 校验文件是否存在
- 枚举输入/输出文件

这是 office 链路的基础设施层，所有文档型 Agent/Team 最好都通过它而不是手写路径。

### 1.2 `OfficeMarkdownToolkit`

作用：

- 将 Markdown 文本保存到 office 输出目录或当前 workspace

特点：

- 如果 run_context 里有 `workspace`，优先写到 workspace
- 否则走环境变量配置的 office 输出目录

### 1.3 `OfficePdfToolkit`

作用：

- 用 `reportlab` 生成基础 PDF

特点：

- 能满足简单 PDF 交付
- 不是复杂排版引擎
- 如果后续需要高质量分页/样式，应该增强这里，而不是直接在 Agent 指令层绕过去

### 1.4 `OfficeSearchToolkit`

作用：

- 基于 DDGS 做公开网页搜索
- 把结果压缩成简短 brief

特点：

- 明显是“轻量信息补充工具”
- 不适合高可信、带强引用要求的场景

### 1.5 `AcademicSearchToolkit`

这是本仓库功能最多的 Toolkit 之一，覆盖：

- DuckDuckGo 搜索/新闻
- Baidu 搜索/热榜
- CSDN 搜索
- Jina read/search
- arXiv
- MathWorld
- GitHub 仓库/代码/API
- Semantic Scholar
- YouTube 元信息与字幕

特点：

- 工具数量多，但实现风格统一：外部请求 -> 结构化 JSON/string 返回
- 很多方法是“对第三方 API 的轻封装”，不是复杂业务逻辑

### 1.6 `GitHubReaderToolkit`

作用分成五块：

- `prepare_repo`
- `parse_repo`
- `read_repo_file`
- `read_repo_file_lines`
- `ingest_repo_to_knowledge`

设计重点：

- 控制上下文大小
- 先返回文件元数据，不默认返回全部内容
- 支持 code/doc 分类、chunking、staging、知识库写入

这个模块工程化程度很高，是未来做“仓库级 RAG/代码理解”时最值得复用的基础件。

### 1.7 `web_driver_monitor_toolkit`

作用：

- 把 Agent 侧的浏览器操作转成对 `server/web_driver_monitor` 的 HTTP 提交
- 同时把结果压缩成 summary，并把原始截图/DOM 放入当前轮 transient state

关键状态：

- `browser_state`
  - 跨轮持久摘要
- `_browser_current_round`
  - 当前轮原始快照

这是浏览器链路中最关键的上下文控制点。

## 2. MCP 适配层

### 2.1 `tools/mcp_tools/data_mcp_tool.py`

- 使用 `MCPTools`
- 远端 URL 默认 `http://localhost:8085/mcp`
- 会通过 `header_provider` 从 `run_context.metadata` 注入 `user_id`

这说明 data MCP 的多租户/多用户隔离不是靠不同 URL，而是靠请求头 + 后端数据映射。

### 2.2 `tools/mcp_tools/docx_use_mcp_tool.py`

- 使用 `MCPTools`
- 远端 URL 完全由 `DOCX_USE_MCP_URL` 提供

这个适配层很薄，说明 docx MCP 服务端已经承担了绝大部分业务。

## 3. 独立服务

## 3.1 `server/data`

### 组成

- `main.py`
  - FastAPI -> FastMCP
- `data_process/*`
  - pandas / sklearn 预处理
- `machine_learning/*`
  - 模型训练、参数空间、进程池

### 设计特点

- I/O 与元数据依赖 SQLite：`DATA_DB_PATH`
- 预处理任务走线程池
- 训练任务走进程池
- 每个用户通过 `user_id -> CSV path` 映射定位输入数据

### 适合做的事

- CSV 级清洗
- 缺失值处理
- 采样、编码、归一化
- sklearn 训练与保存

### 不适合误判成的东西

- 它不是通用数据仓库
- 也不是在线推理系统
- 当前更偏“离线数据文件处理 + 模型训练工具服务”

## 3.2 `server/docx_use_mcp`

这是一个体量很大的 Word 文档 MCP 服务。

### 核心特点

- 使用 `FastMCP`
- 支持 `stdio` / `sse` / `streamable-http`
- 在 `docx_use_server/main.py` 中注册了 54 个工具

### 工具类别

- 文档创建/复制/读取
- 段落/标题/图片/表格
- 文本格式化
- 表格样式、合并、宽度、对齐、padding
- 评论提取
- 脚注/尾注
- 文档保护/解保护/验证
- PDF 转换
- 锚点/标题附近内容替换

### 设计判断

这里已经不是简单的 office 辅助，而是一套独立 Word 文档能力平台。后续如果要增强 `.docx` 方向，优先扩这里，不要在 Agent 层堆提示词兜底。

## 3.3 `server/web_driver_monitor`

这是浏览器链路的真正执行端。

### 组成

- `app.py`
  - FastAPI API
- `bus.py`
  - 单进程内存事件总线
- `playwright_runtime.py`
  - 长生命周期 persistent context/page
- `watchdogs/page_actions.py`
  - 原子页面动作
- `watchdogs/handles.py`
  - 组合式 handle

### 核心设计

- 只维护一个长生命周期浏览器上下文
- 所有动作通过事件总线串行执行
- 每次成功动作后立即采集：
  - interactable DOM snapshot
  - screenshot

### 支持的两类能力

- 原子 page event
  - goto/click/fill/press/hover/wait/tab 等
- handle
  - `fill_form`
  - `click_then_wait`
  - `type_and_submit`
  - `login_form`
  - `dismiss_modal_then_click`
  - `wait_and_retry_click`

这里非常适合作为“稳定执行层”，而不是把复杂浏览器逻辑放到 Agent 提示词里。

## 4. `server/meta_mcp`

这是一个完整的独立 Node 子项目：

- pnpm workspace
- backend: tRPC + drizzle
- frontend: Next.js
- 文档和国际化都很完整

当前判断：

- 它更像被拉进仓库做参考、未来集成或二次改造的上游项目
- 根目录 `main.py` 也留了 TODO，想把它纳入 docker-compose
- 但当前主链路尚未真正接入

因此：

- 若任务不点名 `meta_mcp`，不要把它当成当前 Python 主系统的一部分来扩展
- 若确实要接入，应先补运行拓扑和边界文档，再动代码

