# Capital SaaS 生产部署

## 隔离命名

- 目录：`/opt/capital-saas`
- 后端：`127.0.0.1:8001`
- 数据库：`capital_saas`
- systemd：`capital-saas-backend.service`
- Nginx：`capital-saas.conf`

## 部署检查

1. 创建独立目录、虚拟环境、数据库用户和 `.env`。
2. 从 `.env.example` 复制配置并替换全部生产密钥。
3. 安装 `requirements.txt`，执行数据库初始化或迁移。
4. 安装 systemd 与 Nginx 配置，先执行 `nginx -t`。
5. 启动新服务并检查 `/health`。

新项目不得复用旧项目端口、数据库、环境文件或服务名。
