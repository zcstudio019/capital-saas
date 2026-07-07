# Capital SaaS 回滚

1. 保留当前 `/opt/capital-saas/.env` 和数据库备份。
2. 仅在 `/opt/capital-saas` 内切换到上一个已验证版本。
3. 执行数据库兼容性检查。
4. 重启 `capital-saas-backend.service`。
5. 检查 `http://127.0.0.1:8001/health` 和应用日志。

不得停止、重启或修改旧项目服务。
