FROM node:20-bookworm-slim AS frontend_builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build/frontend

COPY agent-web-fronted-2/package.json agent-web-fronted-2/package-lock.json ./
COPY agent-web-fronted-2/index.html ./
COPY agent-web-fronted-2/tsconfig.json ./
COPY agent-web-fronted-2/vite.config.ts ./
COPY agent-web-fronted-2/.env ./.env
COPY agent-web-fronted-2/scripts ./scripts
COPY agent-web-fronted-2/src ./src

RUN npm ci
RUN npm run build

FROM openresty/openresty:alpine-fat

# 安装 CA 证书，供 JWKS HTTPS 拉取校验使用
RUN apk add --no-cache ca-certificates

# 安装 JWKS/JWT 校验依赖
RUN /usr/local/openresty/bin/opm get ledgetech/lua-resty-http \
    && /usr/local/openresty/bin/opm get fffonion/lua-resty-openssl \
    && /usr/local/openresty/bin/opm get anvouk/lua-resty-jwt-verification

# 避免 nginx 写文件日志时报 /var/log/nginx/error.log 不存在
RUN mkdir -p /var/log/nginx \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log

# 创建 SSL 证书目录
RUN mkdir -p /etc/nginx/ssl

COPY --from=frontend_builder /build/frontend/dist/ /usr/local/openresty/nginx/html/
