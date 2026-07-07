import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.backup_service import list_backups
from services.release_service import read_version

print(f"Rollback Check for version {read_version()}")
backups = list_backups()
if backups:
    print(f"最近备份：{backups[0]['name']} sha256={backups[0]['sha256']}")
else:
    print("WARNING: 暂无备份，请先手动创建备份再发布。")
print("回滚步骤参考 deploy/rollback_guide.md")
