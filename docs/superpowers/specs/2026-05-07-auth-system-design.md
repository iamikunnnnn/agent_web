# Auth System Design

## Summary

Add a user authentication system under `auth/` using Supabase Auth for JWT sign/verify and a local PostgreSQL table for business user data. All API endpoints require login via JWTMiddleware.

## Context

- Framework: FastAPI + Agno (AgentOS)
- Database: PostgreSQL with pgvector
- Current state: No auth, all endpoints are public
- Requirement: Deploy to public internet, all endpoints must require login

## Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Auth provider | Supabase Auth | Open source, self-hostable, free tier, PostgreSQL ecosystem |
| Auth mechanism | JWTMiddleware (global) | Platform-type project, most endpoints need auth |
| Role model | Single role (user) | No admin/user distinction needed yet |
| User data storage | Supabase + local user table | Supabase for auth, local table for business fields |
| Scope model | Reserved, not enforced | Single role now, `require_scope` closure ready for future RBAC |

## Architecture

```
auth/
  __init__.py        # Public API exports
  model.py           # @dataclass models (TokenPayload, CurrentUser, LocalUser)
  config.py          # Supabase connection config from env vars
  verify.py          # JWT verification via JWKS public key
  middleware.py       # JWTMiddleware (global authentication)
  permissions.py      # get_current_user, require_scope (authorization layer)
```

### Authentication Flow

```
Frontend login -> Supabase issues JWT
    |
Frontend sends Authorization: Bearer <token> on every request
    |
JWTMiddleware intercepts (excludes /health, /docs, /openapi.json, etc.)
    |
verify.py fetches Supabase JWKS public key, verifies signature
    |
Valid -> parse into TokenPayload -> convert to CurrentUser -> write to request.state
    |
First login auto-creates local user record (upsert by user_id)
```

### Separation of Concerns

- **Authentication** (who are you?): JWTMiddleware + verify.py
- **Authorization** (what can you do?): permissions.py (reserved)
- Communication via `request.state.user`

## Data Models

### TokenPayload (from Supabase JWT)

| Field | Type | Description |
|-------|------|-------------|
| sub | str | Supabase user_id (UUID) |
| email | str | User email |
| role | str | Supabase role (authenticated / anon) |
| scopes | list[str] | Permission list (reserved) |
| issued_at | int | iat timestamp |
| expires_at | int | exp timestamp |

### CurrentUser (written to request.state)

| Field | Type | Description |
|-------|------|-------------|
| user_id | str | Supabase user_id |
| email | str | User email |
| scopes | list[str] | Permission list (reserved) |

### LocalUser (PostgreSQL table: auth.users)

| Field | Type | Description |
|-------|------|-------------|
| user_id | str (PK) | Supabase user_id |
| email | str | Denormalized for query convenience |
| nickname | str | Display name |
| avatar_url | str | Avatar URL |
| created_at | str (ISO 8601) | Registration time |
| last_login_at | str (ISO 8601) | Last login time |
| is_active | bool | Account enabled flag |

No passwords stored locally. Registration/login handled entirely by Supabase.

## Integration Points

### api/main.py

Register JWTMiddleware after `agent_os.get_app()`.

### Public routes (excluded from auth)

- `/health`
- `/docs`
- `/openapi.json`
- `/redoc`
- Agno playground routes (if any)

### monitor.py

Existing `get_authentication_dependency` replaced by new middleware.

### Database

Local user table uses schema `auth`, isolated from Agno business tables. Created via migration or startup hook.

## Environment Variables

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

JWT verification uses Supabase's JWKS endpoint derived from `SUPABASE_URL`. No JWT secret needed server-side.

## Frontend Contract

### 1. Supabase JS SDK 初始化

```javascript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://your-project.supabase.co',  // 对应后端 SUPABASE_URL
  'your-anon-key'                       // 对应后端 SUPABASE_ANON_KEY
)
```

### 2. 登录 / 注册

```javascript
// 邮箱密码注册
const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: 'password123',
})

// 邮箱密码登录
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password123',
})

// OAuth 登录（如 GitHub）
const { data, error } = await supabase.auth.signInWithOAuth({
  provider: 'github',
})
```

### 3. Token 获取与请求规范

```javascript
// 每次请求前获取当前 session 的 token
const { data: { session } } = await supabase.auth.getSession()

// 所有后端 API 请求必须携带 Authorization header
const response = await fetch('http://your-server:8005/agents', {
  headers: {
    'Authorization': `Bearer ${session.access_token}`,
    'Content-Type': 'application/json',
  },
})
```

**规则：** 所有 `/health`、`/docs`、`/openapi.json`、`/redoc`、`/info` 以外的接口都必须带 token，否则返回 401。

### 4. 后端返回的错误格式

| 状态码 | 含义 | response body |
|--------|------|---------------|
| 401 | 未登录 / token 无效 / token 过期 | `{"detail": "Missing token"}` 或 `{"detail": "Token has expired"}` 或 `{"detail": "Invalid token: ..."}` |
| 403 | 权限不足（预留，当前不会触发） | `{"detail": "Requires scope: xxx"}` |

**前端处理逻辑：**
- 收到 401 → 跳转登录页或刷新 token
- 收到 403 → 提示无权限

### 5. 后端写入 request.state 的用户信息

后端中间件验证 token 后，以下信息可通过依赖注入在路由中使用（前端无需关心，仅供了解）：

```python
# 后端内部结构（CurrentUser dataclass）
{
    "user_id": "uuid-string",     # Supabase user_id
    "email": "user@example.com",
    "scopes": []                  # 预留，当前为空
}
```

### 6. 前端获取用户信息

前端直接从 Supabase SDK 获取用户资料，不需要调用后端接口：

```javascript
const { data: { user } } = await supabase.auth.getUser()

// user 对象结构
{
  id: "uuid-string",           // 与后端 user_id 对应
  email: "user@example.com",
  created_at: "2026-05-07T...",
  user_metadata: {
    full_name: "...",
    avatar_url: "...",
    // Supabase 标准字段
  },
  app_metadata: {
    provider: "email",          // 或 "github" 等
    providers: ["email"],
  }
}
```

### 7. Token 生命周期

| 阶段 | 说明 |
|------|------|
| 签发 | Supabase 在登录成功后签发 JWT，默认有效期 1 小时 |
| 刷新 | Supabase JS SDK 自动处理 token 刷新（默认 refresh_token 有效期 7 天） |
| 过期 | token 过期后后端返回 401，前端 SDK 自动刷新后重试 |
| 登出 | `await supabase.auth.signOut()` |

**前端不需要手动管理 token 刷新**，Supabase JS SDK 内置了自动刷新机制。只需确保每次 API 调用时从 `getSession()` 获取最新 token。

### 8. 公开路由列表（无需 token）

| 路径 | 说明 |
|------|------|
| `GET /` | 首页信息 |
| `GET /health` | 健康检查 |
| `GET /docs` | Swagger 文档页面 |
| `GET /redoc` | ReDoc 文档页面 |
| `GET /openapi.json` | OpenAPI schema |
| `GET /info` | OS 元数据 |

其余所有 Agno 路由（agents、teams、workflows、sessions、memory、metrics 等）均需登录。

### 9. 本地用户表字段

后端 `auth.users` 表会在用户首次请求时自动创建记录。字段供后续业务扩展使用：

| 字段 | 类型 | 说明 | 前端是否需要关注 |
|------|------|------|-----------------|
| user_id | str (PK) | Supabase user_id | 是（关联业务数据的主键） |
| email | str | 邮箱 | 否（从 Supabase SDK 直接读取） |
| nickname | str | 昵称 | 是（如果后端提供编辑接口） |
| avatar_url | str | 头像 | 是（如果后端提供编辑接口） |
| created_at | timestamptz | 注册时间 | 可选（展示用） |
| last_login_at | timestamptz | 最后登录 | 否（后端自动更新） |
| is_active | bool | 是否启用 | 否（后端管理） |

## Scope

In scope:
- JWTMiddleware with JWKS verification
- Local user table with auto upsert on first login
- `get_current_user` dependency for route handlers
- `require_scope` closure (reserved for future use)
- Environment config for Supabase

Out of scope:
- Frontend implementation
- Supabase project setup
- Admin panel
- OAuth provider configuration
- Multi-tenant / organization support
