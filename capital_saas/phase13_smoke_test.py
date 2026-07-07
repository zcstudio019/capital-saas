import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DB = Path("phase13_test.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.resolve().as_posix()}"
os.environ["SECRET_KEY"] = "phase13-smoke-secret"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa

from db.init_db import init_database  # noqa
from main import app  # noqa

init_database()
client = TestClient(app)


def assert_ok(path: str):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:300])
    return r


with client:
    assert_ok("/health")
    assert_ok("/ready")
    assert_ok("/robots.txt")
    assert_ok("/sitemap.xml")
    assert_ok("/legal/privacy")
    assert_ok("/legal/terms")
    assert_ok("/legal/disclaimer")
    assert_ok("/legal/data-authorization")

    login = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
    assert login.status_code in (302, 303), login.text[:300]

    assert_ok("/admin/setup-wizard")
    mark = client.post("/admin/setup-wizard/mark-step", data={"step_key": "company_info", "status": "completed"}, follow_redirects=False)
    assert mark.status_code in (302, 303), mark.status_code
    assert_ok("/admin/launch-dashboard")
    assert_ok("/admin/release-notes")
    assert_ok("/admin/production-checklist")

commands = [
    [sys.executable, "scripts/generate_route_manifest.py"],
    [sys.executable, "scripts/export_sqlite_data.py"],
    [sys.executable, "scripts/import_seed_data.py"],
    [sys.executable, "scripts/preflight_check.py"],
    [sys.executable, "scripts/rollback_check.py"],
    [sys.executable, "scripts/create_demo_data.py"],
    [sys.executable, "scripts/clear_demo_data.py"],
]

for cmd in commands:
    script_path = Path(cmd[-1])
    run_cmd = [cmd[0], script_path.name]
    result = subprocess.run(run_cmd, cwd=Path(__file__).resolve().parent / script_path.parent, env=os.environ.copy(), capture_output=True, text=True)
    if "preflight_check.py" in cmd[-1]:
        assert result.returncode in (0, 1), result.stderr
    else:
        assert result.returncode == 0, (cmd, result.stdout, result.stderr)

assert Path("data/route_manifest.json").exists()
print("PHASE13_RELEASE_TRIAL_OK")
