from notifications.mock_channel import MockChannel


class SmsChannel(MockChannel):
    channel_name="sms"
    def send(self,db,job):
        # TODO: 对接合规短信供应商签名、模板ID与退订机制。
        if not job.recipient_phone: raise ValueError("缺少客户手机号")
        result=super().send(db,job);result["provider"]="sms_mock";return result
