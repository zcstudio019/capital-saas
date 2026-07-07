import json
from datetime import datetime

from db.models import CustomerMessage, InternalNotification
from notifications.base_channel import BaseNotificationChannel


class InAppChannel(BaseNotificationChannel):
    channel_name = "in_app"

    def send(self, db, job) -> dict:
        if job.recipient_customer_id:
            payload=json.loads(job.payload_json or "{}")
            exists=db.query(CustomerMessage).filter(CustomerMessage.customer_id==job.recipient_customer_id,
                CustomerMessage.title==job.title,CustomerMessage.content==job.content).first()
            if not exists:
                db.add(CustomerMessage(customer_id=job.recipient_customer_id,
                    lead_id=int(payload.get("lead_id") or 0),
                    message_type=job.template_key,title=job.title,content=job.content,status="unread"))
        elif job.recipient_user_id:
            db.add(InternalNotification(user_id=job.recipient_user_id,title=job.title,
                content=job.content,notification_type=job.template_key,
                related_type=job.related_type,related_id=job.related_id,status="unread"))
        else:
            raise ValueError("站内通知缺少接收人")
        return {"ok":True,"channel":"in_app","sent_at":datetime.now().isoformat()}
