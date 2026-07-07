from abc import ABC, abstractmethod


class BaseNotificationChannel(ABC):
    channel_name = "base"

    @abstractmethod
    def send(self, db, job) -> dict:
        raise NotImplementedError

    def payload(self, job) -> dict:
        return {"job_id": job.id, "title": job.title, "content": job.content,
                "recipient_user_id": job.recipient_user_id,
                "recipient_customer_id": job.recipient_customer_id}
