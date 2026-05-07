# Agents、Teams、Workflows 详解

## 1. 内置 Agents

### 1.1 `test_agent`

- 文件：`agent/test_agent.py`
- 工具：`test_agent_tool`
- 作用：最小示例/烟雾型 Agent
- 判断：
  - 更像脚手架或调试样例，不是业务 Agent

### 1.2 `test_agent_2`

- 文件：`agent/test_agent_2.py`
- 无工具
- 作用：更原始的占位 Agent
- 判断：
  - 主要用于验证注册、默认配置补全链路

### 1.3 `data_agent`

- 文件：`agent/data_agent.py`
- 工具：`create_data_mcp_tools()`
- pre_hook：`hook.preprocess.preprocess_hook`
- 特点：
  - 不把媒体直接发给模型。
  - 上传文件先落到本地 workspace/缓存，再写 `user_id -> data_path` SQLite 映射。
  - 之后模型通过 data MCP 工具对 CSV 做预处理或训练。

这是一个典型的“Agent 只做调度，真正数据操作在远端服务完成”的模块。

### 1.4 `docx_use_agent`

- 文件：`agent/docx_use_agent.py`
- 工具：`create_docx_use_mcp_tool()`
- 作用：专门处理 `.docx`
- 特点：
  - 显式设置了 `model`、`db`、`knowledge`
  - 允许读/改/生成 Word 文档
  - 更像“垂直领域单专家 Agent”

### 1.5 `browser_use_agent`

- 文件：`agent/browser_use_agent.py`
- 工具：`webDriverMonitorToolkit()`
- skills：本地加载 `skills/agent-browser`
- pre_hook：`clear_browser_transient_state`
- 特点：
  - 把浏览器当前轮原始 DOM/截图限制在当前轮 session state 中
  - 长期状态放在 `browser_state`
  - 强调直接调工具，不先输出抽象动作对象

这是当前浏览器主链路里最重要的 Agent。

### 1.6 `academic_agent`

- 文件：`agent/academic_agent.py`
- 工具：`AcademicSearchToolkit()`
- 作用：学术/资料检索
- 特点：
  - 指令明确要求优先用工具，不凭空补论文信息
  - 输出结构偏“可追溯资料汇总”

### 1.7 `github_reader_agent`

- 文件：`agent/github_reader_agent.py`
- 工具：`GitHubReaderToolkit()`
- 作用：把外部仓库准备到本地并做 repo-style RAG ingest
- 特点：
  - 不是通用 git 客户端，而是“仓库准备 + 分类 + 局部读取 + 入知识库”

### 1.8 office 专家 Agents

#### `office_search_agent`

- 负责外部搜索与信息整理
- 只提供情报，不负责最终文档交付

#### `office_word_agent`

- 负责 `.docx`
- 组合了 `OfficeFileToolkit + docx MCP`

#### `office_markdown_agent`

- 负责 `.md`
- 组合了 `OfficeFileToolkit + OfficeMarkdownToolkit`

#### `office_pdf_agent`

- 负责 `.pdf`
- 组合了 `OfficeFileToolkit + OfficePdfToolkit`

这四个成员形成了 `office_team` 的执行面。

## 2. Teams

### 2.1 `office_team`

- 文件：`team/office_team.py`
- 角色：办公任务总 Leader
- 成员：
  - search
  - word
  - markdown
  - pdf
- 额外工具：`OfficeFileToolkit()`

#### Leader 设计思路

它不是自己产出所有内容，而是：

1. 判断任务是否属于办公文档范围。
2. 如需外部资料，先调搜索专家。
3. 按目标格式把任务派给对应文档专家。
4. 最后校验文件是否真的生成。

这说明团队层的风格是：

- Leader 做路由和验收。
- Member 做具体产出。
- 文件系统工具贯穿前后校验。

### 2.2 `docx_use_team`

- 文件：`team/docx_use_team.py`
- 当前未在 `api/init_team.py` 注册
- 作用：更窄范围的 Word 团队

它和 `office_team` 并存，说明作者曾经在比较：

- 单格式专用 team
- 多格式办公总 team

当前主链路选择了后者。

## 3. Workflows

### 3.1 `browser_workflow`

- 文件：`workflow/browser_workflow.py`
- 当前默认未注册

#### 结构

它由一个 Loop 组成，内部四步：

1. `Observe`
2. `Decide`
3. `Execute`
4. `Verify`

#### 核心思想

- 当前轮原始 DOM 和截图只存在 `_browser_workflow_current_round`
- 跨轮持久状态存在 `browser_workflow`
- Agent 每轮只返回一个 `BrowserDecision`
- 决策结果会被规范化，避免无意义 action 或 done/action 矛盾

#### 为什么重要

虽然当前没注册，但这个文件是理解作者“浏览器状态不应无限污染上下文”的关键设计样本。后续如果要恢复 workflow 注册，必须保持这套状态隔离思路。

## 4. 共性模式

### 4.1 工厂函数风格

几乎所有对象都用 `create_xxx(...)` 返回实例，而不是模块级构造复杂对象后到处传。这样做有两个好处：

- 注册点简单。
- 以后更容易按需实例化或测试替身。

### 4.2 声明式优先

Agent/Team 文件主要写：

- 名称
- 说明
- 指令
- 工具
- 少量行为开关

更底层的实现不放在这些声明文件里。

### 4.3 统一默认配置后补

这对 agent 尤其明显。不要误以为某个 Agent 文件里没写 db/model 就是没有，它往往会在注册后被 `api/utils.py` 自动补上。

## 5. 后续扩展建议

### 5.1 新增 Agent 时

- 如果它是领域专家，参考 `academic_agent` / `docx_use_agent`
- 如果它是工具直连型 Agent，参考 `browser_use_agent`
- 如果它是团队成员型 Agent，参考 office 系列专家

### 5.2 新增 Team 时

- 先定义 Leader 的职责边界
- 明确哪些任务由成员做，哪些由 Leader 验收
- 尽量让 Leader 负责“分派、约束、验收”，不要和成员重复干活

### 5.3 新增 Workflow 时

- 只有当任务天然是多轮状态机时再上 workflow
- 浏览器 workflow 已经给出了项目内的最佳参考实现

