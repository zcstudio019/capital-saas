from notifications.mock_channel import MockChannel


class WecomChannel(MockChannel):
    channel_name="wecom_webhook"
    def send(self,db,job):
        # TODO: 仅对接企业微信群机器人 Webhook，不实现个人微信自动化。
        result=super().send(db,job);result["provider"]="wecom_webhook_mock";return result
