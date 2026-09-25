#!/usr/bin/env python3
"""
检查数据库中的用户
"""

from db.database import SessionLocal
from db.models import User


def check_users():
    """检查数据库中的用户"""
    print("开始检查数据库中的用户...")
    
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"当前数据库中共有 {len(users)} 个用户:")
        for user in users:
            print(f"- 用户名: {user.username}, 邮箱: {user.email}, 状态: {'活跃' if user.status else '禁用'}")
    except Exception as e:
        print(f"检查用户时出错: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_users()
