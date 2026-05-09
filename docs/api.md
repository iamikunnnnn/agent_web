# Agent 管理 API 接口文档

## 基础信息

- **基础 URL**: `http://localhost:8005` (默认)
- **API 版本**: v1
- **认证方式**: Bearer Token (Supabase JWT)
- **内容类型**: `application/json`

## 认证

### 概述

所有受保护的接口都需要在请求头中携带有效的 Bearer Token：

```http
Authorization: Bearer <your_jwt_token>
```

### 公开接口

以下接口无需认证即可访问：

- `GET /`
- `GET /health`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`
- `GET /info`

### Token 获取

Token 需要通过 Supabase Auth 获取。前端应使用 Supabase JS SDK 进行用户登录。

```javascript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'YOUR_SUPABASE_URL',
  'YOUR_SUPABASE_ANON_KEY'
)

// 登录获取 token
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password'
})

const token = data.session.access_token
```

### 错误响应

认证失败时返回 401 状态码：

```json
{
  "detail": "缺少 Bearer Token"
}
```

或

```json
{
  "detail": "Token 已过期"
}
```

## 核心接口

### 1. Agent 运行接口

#### 调用单个 Agent

```http
POST /v1/agents/{agent_id}/run
Authorization: Bearer <token>
Content-Type: application/json
```

**路径参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_id | string | 是 | Agent ID |

**请求体:**

```json
{
  "message": "用户消息内容",
  "user_id": "user_123",  // 可选，默认从 token 中获取
  "session_id": "session_abc"  // 可选，用于会话管理
}
```

**响应:**

```json
{
  "run_id": "run_123",
  "agent_id": "data_agent",
  "message": "用户消息",
  "response": "Agent 的回复内容",
  "created_at": "2026-05-09T12:00:00Z"
}
```

#### 流式响应

```http
POST /v1/agents/{agent_id}/run/stream
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体:** 与普通运行接口相同

**响应:** Server-Sent Events (SSE) 流式数据

### 2. Team 运行接口

#### 调用 Team

```http
POST /v1/teams/{team_id}/run
Authorization: Bearer <token>
Content-Type: application/json
```

**路径参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| team_id | string | 是 | Team ID |

**请求体:**

```json
{
  "message": "团队任务描述",
  "user_id": "user_123"
}
```

**响应:**

```json
{
  "run_id": "team_run_123",
  "team_id": "office_team",
  "message": "团队任务",
  "leader_response": "Leader 的回复",
  "member_responses": [
    {
      "agent_id": "office_word_agent",
      "response": "成员的回复"
    }
  ],
  "created_at": "2026-05-09T12:00:00Z"
}
```

### 3. Workflow 运行接口

```http
POST /v1/workflows/{workflow_id}/run
Authorization: Bearer <token>
Content-Type: application/json
```

## 可用资源

### Agents

| Agent ID | 名称 | 描述 |
|----------|------|------|
| `data_agent` | Data Analyse Agent | 数据读取、预处理和分析，支持机器学习模型训练 |
| `docx_use_agent` | Word文档专家Agent | 专门处理 Word 文档的生成、改写和整理 |

### Teams

| Team ID | 名称 | 描述 | 成员 |
|---------|------|------|------|
| `office_team` | 办公Agent团队 | 办公文档处理团队，自动分派任务给对应专家 | office_search_agent, office_word_agent, office_markdown_agent, office_pdf_agent |

### Workflows

当前未注册 Workflow。

## 监控接口

### Prometheus 指标

```http
GET /prom-metrics
```

无需认证，返回 Prometheus 格式的监控指标。

**响应:** `text/plain; version=0.0.4`

包含的指标：

- `agno_daily_agent_runs` - Agent 运行次数
- `agno_daily_agent_sessions` - Agent 会话数
- `agno_daily_team_runs` - Team 运行次数
- `agno_daily_input_tokens` - 输入 token 数
- `agno_daily_output_tokens` - 输出 token 数
- `agno_exporter_refresh_success` - 导出器刷新状态
- 等更多指标...

## 健康检查

```http
GET /health
```

**响应:**

```json
{
  "status": "ok"
}
```

## 用户上下文

### 请求上下文

JWT 验证通过后，以下信息会被注入到请求上下文中：

- `request.state.user_id` - 用户 ID (来自 JWT 的 sub 字段)
- `request.state.user.email` - 用户邮箱
- `request.state.user.scopes` - 用户权限范围

### Agent 中的用户 ID 使用

在 Agent 执行过程中，`user_id` 会从认证上下文自动获取并传递给相关工具，无需手动指定。

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 401 | 未授权或 Token 无效 |
| 404 | 资源不存在 |
| 422 | 请求参数验证失败 |
| 500 | 服务器内部错误 |

## 示例

### 前端调用示例

```javascript
// 配置
const API_BASE = 'http://localhost:8005'
const TOKEN = 'your_jwt_token'

// 调用 data_agent
async function callDataAgent(message) {
  const response = await fetch(`${API_BASE}/v1/agents/data_agent/run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${TOKEN}`
    },
    body: JSON.stringify({ message })
  })

  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`)
  }

  return await response.json()
}

// 调用 office_team
async function callOfficeTeam(message) {
  const response = await fetch(`${API_BASE}/v1/teams/office_team/run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${TOKEN}`
    },
    body: JSON.stringify({ message })
  })

  return await response.json()
}

// 使用示例
const result = await callDataAgent('帮我分析这个数据集')
console.log(result.response)
```

### cURL 示例

```bash
# 调用 Agent
curl -X POST http://localhost:8005/v1/agents/data_agent/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "分析数据"}'

# 调用 Team
curl -X POST http://localhost:8005/v1/teams/office_team/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "生成一份报告"}'

# 健康检查
curl http://localhost:8005/health
```

## 环境变量配置

前端需要了解以下环境变量（由后端配置）：

| 变量 | 说明 |
|------|------|
| `SUPABASE_URL` | Supabase 项目 URL |
| `SUPABASE_ANON_KEY` | Supabase 匿名密钥（用于前端） |

## WebSocket 支持

部分接口可能支持 WebSocket 连接以实现实时通信，具体请参考 OpenAPI 文档。

## OpenAPI 文档

完整的交互式 API 文档可通过以下地址访问：

- Swagger UI: `http://localhost:8005/docs`
- ReDoc: `http://localhost:8005/redoc`
- OpenAPI JSON: `http://localhost:8005/openapi.json`

## 注意事项

1. **Token 过期**: JWT Token 有过期时间，前端需要处理过期情况并引导用户重新登录
2. **用户隔离**: 所有操作都会自动关联到当前认证用户的数据
3. **异步处理**: 部分耗时操作可能采用异步处理模式
4. **速率限制**: 请注意合理控制请求频率
5. **文件上传**: 如需上传文件，请使用 multipart/form-data 格式

## 更新日志

- 2026-05-09: 初始版本
