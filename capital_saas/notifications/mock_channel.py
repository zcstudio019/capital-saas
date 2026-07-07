from notifications.base_channel import BaseNotificationChannel


class MockChannel(BaseNotificationChannel):
    channel_name="mock"
    def send(self,db,job):return {"ok":True,"mock":True,"channel":job.channel}
