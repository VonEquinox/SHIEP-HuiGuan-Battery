from __future__ import annotations
import argparse
import getpass
import os
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path
from .db import initialize, tx, one, now, audit, insert, js
from .security import create_user
from .services import seed_demo, register_frozen
from .config import RUNTIME, ROLES, APP_ROOT


def main():
    parser = argparse.ArgumentParser(description="慧管电池独立应用管理")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bootstrap")
    p.add_argument("--username", default="admin")
    p.add_argument("--password-stdin", action="store_true")
    p = sub.add_parser("user")
    p.add_argument("username")
    p.add_argument("--name", required=True)
    p.add_argument("--role", choices=ROLES, default="viewer")
    p.add_argument("--password-stdin", action="store_true")
    sub.add_parser("init")
    sub.add_parser("demo")
    sub.add_parser("backup")
    sub.add_parser("status")
    p = sub.add_parser("restore")
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    args = parser.parse_args()
    initialize()
    if args.command in ("bootstrap", "user"):
        with tx() as c:
            if args.command == "bootstrap" and one(c, "SELECT id FROM users LIMIT 1"):
                raise SystemExit(
                    "已有用户；bootstrap不会重置现有账户。使用本地 user 命令创建新用户。"
                )
        password = (
            sys.stdin.readline().rstrip("\r\n")
            if args.password_stdin
            else getpass.getpass("设置密码（至少12字符）: ")
        )
        if not args.password_stdin and password != getpass.getpass("再次输入密码: "):
            raise SystemExit("密码不一致")
        with tx() as c:
            identifier = create_user(
                c,
                args.username,
                "管理员" if args.command == "bootstrap" else args.name,
                password,
                "admin" if args.command == "bootstrap" else args.role,
            )
            audit(
                c,
                identifier,
                "local_cli_user_create",
                "user",
                identifier,
                {"command": args.command},
            )
        print(f"已创建用户 {args.username} (id={identifier})；密码不写入文档。")
    elif args.command == "demo":
        with tx() as c:
            admin = one(
                c,
                "SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1",
            )
            if not admin:
                raise SystemExit("先运行 bootstrap")
            print(seed_demo(c, admin["id"]))
            print("已注册冻结模型:", register_frozen(c, admin["id"]))
            for username, name, role in [
                ("demo-tech", "演示维修员", "technician"),
                ("demo-dispatch", "演示调度员", "dispatcher"),
                ("demo-viewer", "演示观察员", "viewer"),
            ]:
                if one(c, "SELECT id FROM users WHERE username=:u", {"u": username}):
                    continue
                password = secrets.token_urlsafe(18)
                identifier = create_user(c, username, name, password, role)
                if role == "technician":
                    insert(
                        c,
                        "personnel",
                        {
                            "user_id": identifier,
                            "skills": js(["battery", "inspection"]),
                            "on_call": 1,
                            "latitude": 31.051,
                            "longitude": 121.801,
                            "max_workload": 4,
                        },
                    )
                print(
                    f"新建演示账号：{username}   临时随机密码：{password} （仅本次显示）"
                )
        print("人员和资产均为模拟。真实数据请在页面提交导入任务；未生成任何虚构预测。")
    elif args.command == "backup":
        from .backup import create_backup

        destination = create_backup()
        print(destination)
        print("包含账号哈希与业务记录：请保护备份。模型研究原始数据另行保留。")
    elif args.command == "restore":
        from .backup import restore_backup

        print(restore_backup(args.source, args.destination))
    elif args.command == "status":
        with tx() as c:
            for table in (
                "users",
                "datasets",
                "samples",
                "models",
                "predictions",
                "alerts",
                "orders",
            ):
                print(table, one(c, f"SELECT count(*) n FROM {table}")["n"])
    else:
        print("数据库结构已初始化:", RUNTIME / "battery.db")


if __name__ == "__main__":
    main()
