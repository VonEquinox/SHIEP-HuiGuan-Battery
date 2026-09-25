#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
创建管理员用户脚本
使用正确的密码哈希生成方法
"""

from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import User
from utils.security import get_password_hash

def create_admin_user():
    """创建管理员用户"""
    db: Session = SessionLocal()
    try:
        # 检查用户是否已存在
        existing_user = db.query(User).filter(User.username == "admin").first()
        if existing_user:
            print("管理员用户已存在，正在更新密码...")
            # 更新密码
            existing_user.hashed_password = get_password_hash("admin123")
            db.commit()
            print("密码更新成功！")
        else:
            # 创建新用户
            hashed_password = get_password_hash("admin123")
            admin_user = User(
                username="admin",
                email="admin@example.com",
                hashed_password=hashed_password,
                status=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print("管理员用户创建成功！")
        
        print("=" * 50)
        print("登录凭据：")
        print("用户名: admin")
        print("密码: admin123")
        print("邮箱: admin@example.com")
        print("=" * 50)
        
    except Exception as e:
        print(f"创建用户时出错: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
