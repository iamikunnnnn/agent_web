# SSL 证书配置说明

部署 HTTPS 需要提供 SSL 证书。请将证书文件放置于此目录：

## 文件要求

- `cert.pem` - SSL 证书文件
- `key.pem` - SSL 私钥文件

## 获取方式

### 1. 使用自签名证书（仅用于测试）

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

### 2. 使用 Let's Encrypt 免费证书（推荐生产环境）

```bash
# 安装 certbot
apt install certbot

# 获取证书（需要你的域名已解析到服务器）
certbot certonly --standalone -d yourdomain.com

# 复制证书到此目录
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem key.pem
```

### 3. 购买商业证书

从云服务商或 SSL 证书提供商购买，下载后将证书文件重命名放置于此。

## 注意事项

- 证书文件必须是 PEM 格式
- 私钥文件 `key.pem` 不应该有密码保护，否则 Nginx 启动时会失败
- 确保证书和私钥匹配
- 定期检查证书有效期并及时续期

## 云服务器安全组配置

确保开放以下端口：
- `80` - HTTP（自动重定向到 HTTPS）
- `443` - HTTPS