FROM openresty/openresty:alpine-fat

# 安装 lua-resty-jwt
RUN /usr/local/openresty/bin/opm get SkyLothar/lua-resty-jwt

# 避免 nginx 写文件日志时报 /var/log/nginx/error.log 不存在
RUN mkdir -p /var/log/nginx \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log