from notifications.mock_channel import MockChannel


class EmailChannel(MockChannel):
    channel_name="email"
    def send(self,db,job):
        # TODO: 生产环境接入 SMTP/API 邮件服务，密钥仅从环境变量读取。
        if not job.recipient_email: raise ValueError("缺少客户邮箱")
        result=super().send(db,job);result["provider"]="smtp_mock";return result
