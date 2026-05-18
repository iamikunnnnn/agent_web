local cjson = require "cjson.safe"
local jwt = require "resty.jwt-verification"
local jwks = require "resty.jwt-verification-jwks"
local jwks_cache_local = require "resty.jwt-verification-jwks-cache-local"

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

local function jwt_audience()
    local audience = os.getenv("SUPABASE_JWT_AUDIENCE")
    if audience and audience ~= "" then
        return audience
    end
    return "authenticated"
end

local function jwks_endpoint()
    local endpoint = os.getenv("SUPABASE_JWKS_URL")
    if endpoint and endpoint ~= "" then
        return endpoint
    end

    local supabase_url = os.getenv("SUPABASE_URL") or ""
    if supabase_url == "" then
        return nil
    end

    return supabase_url .. "/auth/v1/.well-known/jwks.json"
end

local function verification_options(algorithm, issuer)
    return {
        valid_signing_algorithms = {
            [algorithm] = algorithm,
        },
        issuer = issuer,
        audiences = { jwt_audience() },
        timestamp_skew_seconds = 5,
    }
end

local function verify_with_shared_secret(token, jwt_secret, algorithm, issuer)
    return jwt.verify(token, jwt_secret, verification_options(algorithm, issuer))
end

local function verify_with_jwks(token, algorithm, issuer)
    local endpoint = jwks_endpoint()
    if not endpoint then
        return nil, "SUPABASE_URL 或 SUPABASE_JWKS_URL 未配置"
    end

    return jwks.verify_jwt_with_jwks(token, endpoint, verification_options(algorithm, issuer))
end

function _M.init()
    local ok, err = jwks.init(jwks_cache_local)
    if not ok then
        error("failed to initialize JWKS cache: " .. tostring(err))
    end

    jwks.set_http_timeouts_ms(2000, 2000, 5000)
    jwks.set_http_ssl_verify(true)
    jwks.set_cache_ttl(12 * 60 * 60)
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

    local issuer = nil
    local supabase_url = os.getenv("SUPABASE_URL") or ""
    if supabase_url ~= "" then
        issuer = supabase_url .. "/auth/v1"
    end

    local decoded = nil
    local jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    local header = decode_token_header(token)
    local algorithm = header and header.alg or nil
    if not algorithm or algorithm == "" then
        ngx.status = 401
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"Token 缺少 alg 字段"}')
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
    end

    if algorithm == "HS256" or algorithm == "HS384" or algorithm == "HS512" then
        if not jwt_secret or jwt_secret == "" then
            ngx.log(ngx.ERR, "SUPABASE_JWT_SECRET 环境变量未配置")
            ngx.status = 500
            ngx.header.content_type = "application/json"
            ngx.say('{"detail":"网关认证配置错误"}')
            ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
        end

        local verify_error = nil
        decoded, verify_error = verify_with_shared_secret(token, jwt_secret, algorithm, issuer)
        if not decoded then
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
        local verify_error = nil
        decoded, verify_error = verify_with_jwks(token, algorithm, issuer)
        if not decoded then
            ngx.log(ngx.WARN, "JWKS JWT 验证失败: ", verify_error or "unknown")
            ngx.status = 401
            ngx.header.content_type = "application/json"
            ngx.say('{"detail":"Token 校验失败"}')
            ngx.exit(ngx.HTTP_UNAUTHORIZED)
        end
    end

    local payload = decoded.payload or {}

    -- 校验 aud
    local aud = payload.aud
    if aud and type(aud) ~= "string" and type(aud) ~= "table" then
        ngx.status = 401
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"Token audience 不匹配"}')
        ngx.exit(ngx.HTTP_UNAUTHORIZED)
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
    ngx.req.set_header("X-User-Scopes", type(payload.scopes) == "table" and cjson.encode(payload.scopes) or "[]")
end

return _M
