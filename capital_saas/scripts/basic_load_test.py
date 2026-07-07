import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import requests
except Exception:
    requests = None
    from urllib.request import urlopen
from db.database import SessionLocal
from services.event_service import track_event

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8001")
parser.add_argument("--concurrency", type=int, default=5)
parser.add_argument("--requests", type=int, default=50)
args = parser.parse_args()

paths = ["/", "/assessment", "/lp/rongzi", "/health", "/login"]


def hit(i):
    url = args.base_url.rstrip("/") + paths[i % len(paths)]
    start = time.perf_counter()
    try:
        if requests:
            r = requests.get(url, timeout=10)
            return r.status_code < 500, time.perf_counter() - start, r.status_code, url
        with urlopen(url, timeout=10) as response:
            status = response.getcode()
        return status < 500, time.perf_counter() - start, status, url
    except Exception:
        return False, time.perf_counter() - start, 0, url


results = []
with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
    for future in as_completed([pool.submit(hit, i) for i in range(args.requests)]):
        results.append(future.result())

durations = [x[1] for x in results]
success = sum(1 for x in results if x[0])
failed = len(results) - success
p95 = sorted(durations)[max(0, int(len(durations) * 0.95) - 1)] if durations else 0
print(f"success={success} failed={failed} avg={statistics.mean(durations):.3f}s max={max(durations):.3f}s p95={p95:.3f}s")
with SessionLocal() as db:
    track_event(db, "load_test_run", data={"success": success, "failed": failed, "avg": statistics.mean(durations) if durations else 0})
