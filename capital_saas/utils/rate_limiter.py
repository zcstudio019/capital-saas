from collections import defaultdict,deque
from time import time

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import BASE_DIR,settings

PROTECTED=("/assessment/submit","/login","/client/login-token/","/payment/mock-pay/",
           "/client/documents/upload","/public/report/")

class RateLimitMiddleware(BaseHTTPMiddleware):
    buckets=defaultdict(deque);templates=Jinja2Templates(directory=str(BASE_DIR/"templates"))
    async def dispatch(self,request:Request,call_next):
        if not settings.rate_limit_enabled or not any(request.url.path.startswith(x) for x in PROTECTED):return await call_next(request)
        ip=(request.headers.get("x-forwarded-for","").split(",")[0].strip() or (request.client.host if request.client else "unknown"))
        limit=settings.login_rate_limit_per_minute if request.url.path=="/login" else settings.rate_limit_per_minute
        key=(ip,request.url.path.split("?",1)[0]);bucket=self.buckets[key];now=time()
        while bucket and bucket[0]<now-60:bucket.popleft()
        if len(bucket)>=limit:
            try:
                from db.database import SessionLocal
                from services.event_service import track_event
                with SessionLocal() as db:track_event(db,"rate_limit_blocked",data={"ip":ip,"path":request.url.path,"limit":limit})
            except Exception:pass
            return self.templates.TemplateResponse(request=request,name="error_429.html",context={"message":"请求过于频繁，请稍后再试。"},status_code=429)
        bucket.append(now);return await call_next(request)
