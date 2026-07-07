import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.database import SessionLocal
from services.release_service import flatten_preflight, preflight_groups, read_version


def main() -> int:
    with SessionLocal() as db:
        rows = flatten_preflight(preflight_groups(db))
        fail = [x for x in rows if x["status"] == "fail"]
        print(f"Release Check for version {read_version()}")
        if fail:
            print("发布检查未通过：")
            for item in fail:
                print(f"- {item['group']} / {item['name']}：{item['message']}")
            return 1
        print("发布检查通过。warning 项请确认负责人。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
