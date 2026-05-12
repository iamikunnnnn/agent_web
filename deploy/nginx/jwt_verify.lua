local cjson = require "cjson.safe"
local jwt = require "resty.jwt"

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

local function decode_token_header(token)
    local encoded = token:match("^([^.]+)")
    if not encoded then
        return nil
    end

    local normalized = encoded:gsub("-", "+"):gsub("_", "/")
    local remainder = #normalized % 4
    if remainder > 0 then
        normalized = normalized .. string.rep("=", 4 - remainder)
    end

    local decoded = ngx.decode_base64(normalized)
    if not decoded then
        return nil
    end

    return cjson.decode(decoded)
end

local function verify_with_shared_secret(token, jwt_secret)
    local jwt_obj = jwt:verify(jwt_secret, token, {
        require_exp_claim = true,
        lifetime_grace_period = 0,
    })

    if not jwt_obj.verified then
        return nil, jwt_obj.reason or "Token 校验失败"
    end

    return jwt_obj.payload, nil
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

    local supabase_url = os.getenv("SUPABASE_URL") or ""
    local payload = nil
    local jwt_secret = os.getenv("JWT_SECRET")
    local header = decode_token_header(token)
    local algorithm = header and header.alg or nil

    if algorithm == "HS256" or algorithm == "HS384" or algorithm == "HS512" then
        if not jwt_secret or jwt_secret == "" then
            ngx.log(ngx.ERR, "JWT_SECRET 环境变量未配置")
            ngx.status = 500
            ngx.header.content_type = "application/json"
            ngx.say('{"detail":"网关认证配置错误"}')
            ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
        end

        local verify_error = nil
        payload, verify_error = verify_with_shared_secret(token, jwt_secret)
        if not payload then
            ngx.log(ngx.WARN, "JWT 验证失败: ", verify_error or "unknown")
            ngx.status = 401
            ngx.header.content_type = "application/json"
            local reason = verify_error or "Token 校验失败"
            if string.find(reason, "exp") then
                reason = "Token 已过期"
            end
            ngx.say(string.format('{"detail":"%s"}', reason))
            ngx.exit(ngx.HTTP_UNAUTHORIZED)
        end
    else
        -- ES256/JWKS 等非对称算法交由应用层鉴权处理中间件校验。
        return
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
