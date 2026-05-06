# 仓库监控 Agent 需求文档

## 1. 项目概述

### 1.1 需求背景
当前项目已有 `github_reader_agent` 用于一次性读取和解析仓库代码。但缺乏对多个仓库的持续监控能力，无法自动追踪仓库代码变化并生成变更总结。

### 1.2 目标
创建一个仓库监控 Agent，能够：
- 监听多个 Gitee、GitHub 仓库
- 定期拉取更新并记录时间戳
- 检测代码变化
- 自动生成代码变更总结
- 将变更日志持久化存储

---

## 2. 核心功能需求

### 2.1 仓库注册与配置
**描述**：支持用户注册需要监控的仓库列表。

**功能点**：
| 功能 | 说明 |
|------|------|
| 添加仓库 | 支持 GitHub 和 Gitee 仓库 URL |
| 访问令牌配置 | 支持配置 GitHub/Gitee 访问令牌（用于私有仓库） |
| 监控间隔 | 支持为每个仓库设置独立的监控间隔（默认 1 小时） |
| 监控开关 | 支持启用/禁用单个仓库的监控 |

### 2.2 定期拉取与时间记录
**描述**：后台任务定期拉取仓库更新，记录拉取时间。

**功能点**：
| 功能 | 说明 |
|------|------|
| 定时拉取 | 使用 APScheduler 或类似工具实现定时任务 |
| 时间戳记录 | 每次成功拉取后记录时间 A（ISO 8601 格式） |
| 错误重试 | 拉取失败后自动重试，最多 3 次 |
| 状态更新 | 记录每次拉取的状态（成功/失败/重试次数） |

### 2.3 代码变更检测
**描述**：检测两次拉取之间的代码变化。

**功能点**：
| 功能 | 说明 |
|------|------|
| Git Diff 分析 | 使用 `git diff` 获取两次拉取之间的差异 |
| 变更统计 | 统计新增/修改/删除的文件数量 |
| 变更分类 | 按文件类型分类（代码/文档/配置等） |
| 过滤规则 | 支持配置忽略特定目录（如 `__pycache__`, `node_modules`） |

### 2.4 变更总结生成
**描述**：Agent 分析代码变更并生成人类可读的总结。

**功能点**：
| 功能 | 说明 |
|------|------|
| 自动触发 | 检测到变更后自动触发 Agent 分析 |
| 变更摘要 | 生成本次变更的简要摘要 |
| 影响范围分析 | 分析变更影响的功能模块 |
| 风险评估 | 评估代码变更的潜在风险 |
| 格式输出 | 支持 Markdown/JSON 格式输出 |

### 2.5 日志存储
**描述**：将所有变更日志持久化存储。

**功能点**：
| 功能 | 说明 |
|------|------|
| 日志记录 | 记录每次变更的详细信息 |
| 查询接口 | 提供按仓库/时间范围查询日志的接口 |
| 日志归档 | 支持定期归档历史日志 |
| 导出功能 | 支持导出日志为 Markdown/CSV 文件 |

---

## 3. 技术架构设计

### 3.1 组件划分

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentOS 主应用                           │
│                       (api/main.py)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    repo_monitor_agent                          │
│              (agent/repo_monitor_agent.py)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  RepoMonitorMCP     │ │  GitDiffToolkit │ │  SummaryAgent   │
│  (server/repo_     │ │  (tools/git_    │ │  (agent/repo_   │
│   monitor_mcp/)     │ │   diff_toolkit) │ │   summary_agent) │
└─────────────────────┘ └─────────────────┘ └─────────────────┘
```

### 3.2 模块设计

#### 3.2.1 RepoMonitorMCP (独立服务)
**位置**: `server/repo_monitor_mcp/`

**职责**:
- 仓库注册与管理
- 定时拉取调度
- 变更检测
- 日志存储

**接口设计**:
| 端点 | 方法 | 说明 |
|------|------|------|
| `/repo/register` | POST | 注册监控仓库 |
| `/repo/list` | GET | 获取已注册仓库列表 |
| `/repo/{repo_id}` | DELETE | 删除监控仓库 |
| `/repo/{repo_id}/toggle` | POST | 启用/禁用监控 |
| `/repo/{repo_id}/logs` | GET | 获取仓库变更日志 |
| `/repo/sync` | POST | 手动触发同步 |
| `/health` | GET | 健康检查 |

#### 3.2.2 GitDiffToolkit
**位置**: `tools/git_diff_toolkit.py`

**工具方法**:
```python
class GitDiffToolkit(Toolkit):
    def get_commits_between(repo_path, since, until)
    def get_diff_summary(repo_path, since, until)
    def get_file_changes(repo_path, since, until)
    def analyze_change_impact(repo_path, commit_hash)
```

#### 3.2.3 RepoMonitorAgent
**位置**: `agent/repo_monitor_agent.py`

**职责**:
- 接收变更通知
- 调用 GitDiffToolkit 分析变更
- 生成变更总结
- 存储变更日志

---

## 4. 数据模型设计

### 4.1 仓库配置表 (`repo_configs`)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| repo_url | VARCHAR(500) | 仓库 URL |
| repo_type | VARCHAR(20) | github/gitee |
| repo_owner | VARCHAR(100) | 仓库所有者 |
| repo_name | VARCHAR(100) | 仓库名称 |
| local_path | VARCHAR(500) | 本地克隆路径 |
| access_token | VARCHAR(200) | 访问令牌（加密存储） |
| monitor_interval | INTEGER | 监控间隔（秒） |
| last_sync_time | TIMESTAMP | 上次同步时间 |
| last_commit_hash | VARCHAR(100) | 上次同步的 commit hash |
| is_enabled | BOOLEAN | 是否启用监控 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 4.2 变更日志表 (`repo_change_logs`)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| repo_config_id | UUID | 关联仓库配置 ID |
| sync_time | TIMESTAMP | 同步时间 |
| commit_hash | VARCHAR(100) | 最新的 commit hash |
| files_added | INTEGER | 新增文件数 |
| files_modified | INTEGER | 修改文件数 |
| files_deleted | INTEGER | 删除文件数 |
| commit_count | INTEGER | 本次变更的 commit 数 |
| summary | TEXT | 变更摘要 |
| full_report | TEXT | 完整变更报告（JSON） |
| created_at | TIMESTAMP | 记录创建时间 |

### 4.3 同步历史表 (`repo_sync_history`)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| repo_config_id | UUID | 关联仓库配置 ID |
| sync_time | TIMESTAMP | 同步时间 |
| status | VARCHAR(20) | success/failure/retrying |
| error_message | TEXT | 错误信息（如有） |
| retry_count | INTEGER | 重试次数 |

---

## 5. 实现步骤

### Phase 1: 基础服务搭建
1. 创建 `server/repo_monitor_mcp/` 目录结构
2. 实现仓库注册、列表、删除接口
3. 实现基础 Git 操作封装（clone、pull、log、diff）
4. 实现 SQLite 本地存储（可后续升级到 PostgreSQL）

### Phase 2: 定时任务与变更检测
1. 集成 APScheduler 实现定时拉取
2. 实现 Git diff 分析逻辑
3. 实现变更数据模型存储

### Phase 3: Agent 集成
1. 创建 `RepoMonitorAgent`
2. 创建 `GitDiffToolkit`
3. 实现 Agent 与 MCP 的交互
4. 实现变更总结生成逻辑

### Phase 4: 部署与集成
1. 在 `docker-compose.yaml` 中添加服务配置
2. 在 `api/init_agent.py` 中注册 Agent
3. 配置环境变量
4. 编写测试用例

---

## 6. 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| REPO_MONITOR_MCP_URL | http://repo-monitor-mcp:8012/mcp | MCP 服务地址 |
| REPO_MONITOR_DB_PATH | ./user_cache/repo_monitor.db | 数据库路径 |
| REPO_CLONE_ROOT | ./user_cache/repos | 仓库克隆根目录 |
| DEFAULT_SYNC_INTERVAL | 3600 | 默认同步间隔（秒） |
| MAX_RETRY_COUNT | 3 | 最大重试次数 |

---

## 7. 扩展考虑

### 7.1 短期扩展
- Webhook 支持：支持 GitHub/Gitee Webhook 实时触发
- 通知推送：变更后发送到邮件/钉钉/企业微信
- 多语言支持：支持 GitLab、Bitbucket

### 7.2 长期扩展
- 依赖分析：分析变更对依赖的影响
- 测试建议：建议需要重新运行的测试
- Code Review 辅助：为变更提供 Review 建议

---

## 8. 风险与限制

| 风险 | 缓解措施 |
|------|----------|
| 大仓库拉取时间长 | 使用 shallow clone，限制文件数量 |
| API 限流 | 实现请求频率控制，缓存结果 |
| 本地存储占用 | 定期清理旧仓库克隆，设置存储上限 |
| Token 泄露 | Token 加密存储，支持轮换 |
