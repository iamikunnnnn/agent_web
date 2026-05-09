local jwt = require "resty.jwt"
local cjson = require "cjson.safe"

local _M = {}

local PUBLIC_PATHS = {
    ["/"] = true,
    ["/health"] = true,
    ["/docs"] = true,
    ["/redoc"] = true,
    ["/openapi.json"] = true,
    ["/info"] = true,
}

local function is_public_path(path)
    if PUBLIC_PATHS[path] then
        return true
    end
    if string.sub(path, 1, 5) == "/docs" or string.sub(path, 1, 6) == "/redoc" then
        return true
    end
    return false
end

function _M.verify()
    local path = ngx.var.uri

    -- 清除外部可能伪造的内部头
    ngx.req.clear_header("X-User-Id")
    ngx.req.clear_header("X-User-Email")
    ngx.req.clear_header("X-User-Role")
    ngx.req.clear_header("X-User-Scopes")

    if is_public_path(path) then
        return
    end

    local auth_header = ngx.req.get_headers()["Authorization"]
    if not auth_header then
        ngx.status = 401
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"缺少 Bearer Token"}')
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end

    local token = string.match(auth_header, "^Bearer%s+(.+)$")
    if not token then
        ngx.status = 401
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"缺少 Bearer Token"}')
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end

    local jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret or jwt_secret == "" then
        ngx.log(ngx.ERR, "JWT_SECRET 环境变量未配置")
        ngx.status = 500
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"网关认证配置错误"}')
        ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
    end

    local supabase_url = os.getenv("SUPABASE_URL") or ""

    local jwt_obj = jwt:verify(jwt_secret, token, {
        require_exp_claim = true,
        lifetime_grace_period = 0,
    })

    if not jwt_obj.verified then
        ngx.log(ngx.WARN, "JWT 验证失败: ", jwt_obj.reason or "unknown")
        ngx.status = 401
        ngx.header.content_type = "application/json"
        local reason = jwt_obj.reason or "Token 校验失败"
        if string.find(reason, "exp") then
            reason = "Token 已过期"
        end
        ngx.say(string.format('{"detail":"%s"}', reason))
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end

    local payload = jwt_obj.payload
    if not payload then
        ngx.status = 401
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"Token payload 为空"}')
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end

    -- 校验 aud
    local aud = payload.aud
    if aud and aud ~= "authenticated" then
        ngx.status = 401
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"Token audience 不匹配"}')
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end

    -- 校验 iss
    if supabase_url ~= "" then
        local expected_iss = supabase_url .. "/auth/v1"
        local iss = payload.iss
        if iss and iss ~= expected_iss then
            ngx.status = 401
            ngx.header.content_type = "application/json"
            ngx.say('{"detail":"Token issuer 不匹配"}')
            ngx.exit(ngx.HTTP_UNAUTHORIZED)
        end
    end

    -- 校验 sub
    local sub = payload.sub
    if not sub then
        ngx.status = 401
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"Token 缺少 sub 字段"}')
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end

    -- 注入内部头传递给后端
    ngx.req.set_header("X-User-Id", sub)
    ngx.req.set_header("X-User-Email", payload.email or "")
    ngx.req.set_header("X-User-Role", payload.role or "")
    ngx.req.set_header("X-User-Scopes", payload.scopes and cjson.encode(payload.scopes) or "[]")
end

return _M
