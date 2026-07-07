# Capital SaaS HTTPS 部署

1. 将域名解析到新项目服务器。
2. 将证书放在独立路径，例如 `/etc/nginx/ssl/capital-saas/`。
3. 复制并修改 `capital-saas.conf.example` 中的域名和证书路径。
4. 安装为 `/etc/nginx/conf.d/capital-saas.conf`。
5. 执行 `nginx -t`，确认通过后再执行 `systemctl reload nginx`。

不要覆盖旧项目的 Nginx 配置或证书文件。
