# 阿里云 ALB 部署说明

## 目标拓扑

- 公网入口：阿里云 `ALB`
- ECS 主机：运行当前 `docker compose`
- ECS 暴露端口：仅 `80/tcp` 给 ALB 回源，`22/tcp` 给固定运维 IP
- 容器内部：`gateway -> app -> data-mcp/docx-use-mcp`

当前 compose 已按这个拓扑收口：

- `gateway` 暴露宿主机 `80`
- `app` 仅在 Docker 网络暴露 `8005`
- `data-mcp` 仅在 Docker 网络暴露 `8085`
- `docx-use-mcp` 仅在 Docker 网络暴露 `8008`

## 推荐网络规划

1. 创建一个 VPC。
2. 至少准备两个可用区的 vSwitch，供 ALB 使用。
3. ECS 与 ALB 放在同一个 VPC。
4. ECS 建议不分配公网 IP，运维通过堡垒机、跳板机或阿里云运维通道接入。

## 安全组建议

### ECS 安全组

- 入方向放行 `22/tcp`，来源限制为你的办公出口 IP。
- 入方向放行 `80/tcp`，来源优先限制为 `ALB` 所在安全组。
- 不要放行 `8005`、`8008`、`8085`。

### ALB 安全组

- 入方向放行 `80/tcp`、`443/tcp` 给公网。
- 如果需要额外限流或白名单，在 `ALB` 侧继续加安全组或访问控制。

## ALB 控制台配置

### 1. 创建 ALB

- 类型：`Internet-facing`
- 网络：选择和 ECS 相同的 `VPC`
- 可用区：至少绑定两个可用区的 `vSwitch`

### 2. 创建服务器组

- 服务器组类型：`Server`
- 后端协议：`HTTP`
- 后端端口：`80`
- 后端服务器：添加运行本项目的 ECS 实例

### 3. 配置健康检查

- 协议：`HTTP`
- 端口：使用后端服务器端口 `80`
- 路径：`/health`
- 成功状态码：保留 `http_2xx` 和 `http_3xx`

### 4. 创建监听

#### HTTPS 监听

- 监听端口：`443`
- 证书：绑定阿里云证书管理中的正式证书
- 默认转发动作：转发到上面的服务器组

#### HTTP 监听

- 监听端口：`80`
- 动作：
  - 如果只是给健康检查和临时访问用，可以直接转发到同一服务器组
  - 如果要强制 HTTPS，配置转发规则把 `80` 重定向到 `443`

### 5. 转发规则

如果当前只跑一个站点，先保留默认规则即可。

如果后续要按域名或路径拆服务，再新增规则，例如：

- `api.example.com/* -> 当前服务器组`
- `example.com/docs/* -> 文档服务器组`

## ECS 上的部署步骤

1. 准备 `.env`
   - `SUPABASE_URL`
   - `SUPABASE_JWT_SECRET`
   - 数据库连接变量
2. 启动：

```bash
docker compose build
docker compose up -d
```

3. 检查：

```bash
docker compose ps
docker compose logs -f gateway
docker compose logs -f app
```

## 健康检查与回源注意事项

- ALB 健康检查会直接探测 ECS 回源端口，因此 ECS 上的 `gateway` 必须监听 `80`。
- 如果你在 ECS 系统层额外启用了 `iptables`、`firewalld` 或第三方安全软件，不要拦截 ALB 的回源和健康检查流量。
- 阿里云新版 ALB 会使用其 `vSwitch` 的 `Local IP` 与后端通信；如果健康检查异常，先检查这些地址是否被系统层防火墙阻断。

## 本项目环境变量建议

为避免把开发机绝对路径带到云上，当前项目建议统一写相对路径或容器路径：

- `DATA_DB_PATH=./user_cache/data/data.db`
- `DATA_UPLOAD_DIR=./user_cache/workspace`
- `ML_MODEL_DIR=./user_cache/ml_models`
- `OFFICE_BASE_DIR=./user_cache/office`

在容器内，compose 已将这些路径覆盖为 `/app/user_cache/...`，并使用卷持久化。

## 验收清单

1. `ALB` 健康检查状态为 `Healthy`
2. 只允许通过 `ALB` 域名访问服务
3. ECS 公网或内网安全组中看不到 `8005/8008/8085` 放行规则
4. 登录后带 `Bearer Token` 调用 agent run，`data_agent` 可直接访问当前用户的数据工具
5. 上传的数据文件、训练模型、办公输出都写入 `user_cache` 卷
