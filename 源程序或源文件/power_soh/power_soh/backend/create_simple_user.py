#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
创建简单测试用户脚本
直接使用明文密码（仅用于测试）
"""

from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import User

def create_simple_user():
    """创建简单测试用户"""
    db: Session = SessionLocal()
    try:
        # 检查用户是否已存在
        existing_user = db.query(User).filter(User.username == "admin").first()
        if existing_user:
            print("测试用户已存在")
            print(f"用户名: {existing_user.username}")
            print(f"邮箱: {existing_user.email}")
            print(f"状态: {'活跃' if existing_user.status else '禁用'}")
            return
        
        # 直接使用简单的密码哈希（仅用于测试）
        # 注意：在生产环境中应该使用proper的密码哈希
        test_user = User(
            username="admin",
            email="admin@example.com",
            hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",  # 密码: admin123
            status=True
        )
        
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        
        print("=" * 50)
        print("测试用户创建成功！")
        print("=" * 50)
        print(f"用户名: {test_user.username}")
        print(f"密码: admin123")
        print(f"邮箱: {test_user.email}")
        print(f"状态: {'活跃' if test_user.status else '禁用'}")
        print("=" * 50)
        print("\n提示：您可以使用这些凭据登录系统")
        
    except Exception as e:
        print(f"创建用户时出错: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_simple_user()
