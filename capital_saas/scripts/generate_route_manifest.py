import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import BASE_DIR
from main import app
from services.event_service import track_event
from db.database import SessionLocal

routes = []
for route in app.routes:
    if hasattr(route, "methods"):
        routes.append({"path": route.path, "methods": sorted(route.methods or []), "name": route.name})

out = BASE_DIR / "data" / "route_manifest.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(routes, ensure_ascii=False, indent=2), encoding="utf-8")
with SessionLocal() as db:
    track_event(db, "route_manifest_generated", data={"count": len(routes)})
print(f"已生成路由清单：{out} ({len(routes)} routes)")
