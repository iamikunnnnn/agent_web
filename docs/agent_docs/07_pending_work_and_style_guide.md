# 待开发内容、技术债与风格守则

## 1. 当前待开发/待收敛清单

以下内容是从源码 TODO、模块状态和装配关系里提炼出来的。

### 1.1 顶层主应用

- 引入用户系统与鉴权。
- 考虑接入 Supabase。
- 把 `server/meta_mcp` 纳入整体部署。
- 明确 `data_agent` 的数据源策略：
  - 本地文件
  - 数据库软链接
  - 二者并存

### 1.2 动态 Agent 管理

- `save_agent.py` 目前只保存最简 Agent，参数迁移远未完成。
- 还缺少异步存储、可控字段白名单、热加载策略、回滚策略。

### 1.3 Registry

- `api/registry.py` 当前是实验态。
- 未来如果 Agno registry 更成熟，当前自定义方式可能要收敛。

### 1.4 Knowledge

- `knowledge/add.py` 仍是非常粗糙的实现。
- `GitHubReaderToolkit` 的 staging 目录也有未清理 TODO。
- 当前知识库能力更像“能用”，不是“已收敛”。

### 1.5 数据链路

- `data_agent` 自己就注明“暂未经测试”。
- `server/data/stat_analyse` 明确是待后续功能落地后再做。
- `hook/preprocess.py` 里 `user_id` 仍是硬编码。

### 1.6 文档链路

- `office_team` 和 `docx_use_team/docx_use_agent` 有功能交叉，还没有完全收敛成单一路径。
- PDF 能力现在偏基础生成，不是成熟排版。

### 1.7 浏览器链路

- 浏览器 workflow 已写完但未注册，需要明确是否恢复。
- 当前 direct-tool browser agent 与 workflow 方案并存，需要长期架构决策。

## 2. 这个项目的代码风格，不是语法风格，而是架构风格

后续 agent 最需要保留的是下面这些“思路”。

## 2.1 编排层和执行层分离

不要把复杂执行逻辑塞进 Agent 提示词或 Agent 工厂。

正确做法：

- 重能力下沉到 `tools/` 或 `server/`
- Agent/Team 负责选择、约束、编排

## 2.2 工厂函数 + 注册文件

新增对象时尽量沿用：

- `agent/create_xxx_agent`
- `team/create_xxx_team`
- `workflow/create_xxx_workflow`
- `api/init_xxx.py` 注册

不要跳过这层，直接在 `api.main` 里写对象构造。

## 2.3 统一默认配置

除非有强理由，不要在每个 Agent 文件重复写：

- db
- model
- knowledge
- memory_manager

这些优先走 `api/utils.py` 的统一补配置。

## 2.4 环境变量优先

新增外部服务地址、数据库参数、路径规则时：

- 优先 `config/*`
- 再由 env 覆盖
- 避免硬编码散落在 Agent 文件中

## 2.5 状态要分层

浏览器模块给出的经验很重要：

- 跨轮持久状态和当前轮原始快照必须分开
- 对 LLM 暴露的是“可控摘要”，不是无限量原始数据

这个原则也适用于：

- 大文件处理
- 仓库解析
- 文档中间态

## 2.6 验收型 Leader，而不是全能 Leader

`office_team` 的 Leader 风格值得保留：

- 先判断任务
- 再分派
- 最后校验交付物

不要让 Leader 和专家成员做重复工作。

## 3. 具体开发时的 Do / Don’t

### 3.1 Do

- 先判断新能力应放 `tool` 还是 `server`
- 保持文件职责单一
- 通过 `config/*` 收敛路径、模型、数据库配置
- 对新子系统补最小装配测试
- 在返回给 Agent 的状态里做摘要与裁剪

### 3.2 Don’t

- 不要直接在 `main.py` 写业务
- 不要在 Agent system message 中弥补本该由工具完成的核心能力
- 不要把 `server/meta_mcp` 当成普通本地模块随意混进 Python 主链路
- 不要默默引入新的全局状态命名而不说明其 session state 语义
- 不要扩大 hardcoded secret/config 的范围

## 4. 最推荐的扩展模板

### 4.1 如果要新增一个垂直能力 Agent

参考：

- `agent/docx_use_agent.py`
- `agent/academic_agent.py`

### 4.2 如果要新增一个多成员团队

参考：

- `team/office_team.py`

### 4.3 如果要新增一个远端执行服务

参考：

- `server/data`
- `server/web_driver_monitor`

### 4.4 如果要新增一个工具适配层

参考：

- `tools/mcp_tools/data_mcp_tool.py`
- `tools/web_driver_monitor_toolkit.py`

## 5. 最后给后续 agent 的一句话

这个仓库最容易被改坏的地方，不是某个函数，而是“把边界改乱”。只要继续保持：

- 配置集中
- 执行下沉
- 编排上浮
- 注册清晰
- 状态分层

就基本还能延续原有风格和架构。
