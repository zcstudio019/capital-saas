"""诊断相同手机号的多个客户账号；只读检查，不自动合并。"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.database import SessionLocal, engine
from db.models import CustomerAccount, Order, Report
from services.customer_portal_service import normalize_customer_phone


def main() -> None:
    if not inspect(engine).has_table("customer_accounts"):
        print("未发现客户账号表，请先完成数据库初始化或迁移。")
        return
    with SessionLocal() as db:
        groups: dict[str, list[CustomerAccount]] = defaultdict(list)
        for account in db.query(CustomerAccount).order_by(CustomerAccount.id).all():
            phone = normalize_customer_phone(account.phone or account.login_phone)
            if phone:
                groups[phone].append(account)

        duplicates = {phone: items for phone, items in groups.items() if len(items) > 1}
        print("手机号\t客户账号数量\t报告数量\t订单数量\t客户账号ID")
        for phone, accounts in sorted(duplicates.items()):
            ids = [item.id for item in accounts]
            report_count = db.query(Report).filter(Report.customer_id.in_(ids)).count()
            order_count = db.query(Order).filter(Order.customer_id.in_(ids)).count()
            print(f"{phone}\t{len(ids)}\t{report_count}\t{order_count}\t{','.join(map(str, ids))}")
        if not duplicates:
            print("未发现重复客户账号")
        else:
            print("请人工核对报告、订单和账号状态后再制定合并方案；本脚本未修改任何数据。")


if __name__ == "__main__":
    main()
