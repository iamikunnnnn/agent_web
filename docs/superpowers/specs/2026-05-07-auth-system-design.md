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

Frontend will:
1. Use Supabase JS SDK for login/signup/OAuth
2. Attach `Authorization: Bearer <token>` header on every API call
3. Read user profile from Supabase auth state
4. Read business data (usage, config) from local API

Token payload fields frontend should expect:
- `sub`: user_id (UUID string)
- `email`: user email
- `role`: "authenticated"

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
