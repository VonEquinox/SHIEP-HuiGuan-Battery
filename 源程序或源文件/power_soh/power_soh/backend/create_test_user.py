#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
创建测试用户脚本
用于快速创建测试用户以便登录
"""

from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import User
from utils.security import get_password_hash

def create_test_user():
    """创建测试用户"""
    db: Session = SessionLocal()
    try:
        # 检查用户是否已存在
        existing_user = db.query(User).filter(User.username == "testuser").first()
        if existing_user:
            print("测试用户已存在")
            print(f"用户名: {existing_user.username}")
            print(f"邮箱: {existing_user.email}")
            print(f"状态: {'活跃' if existing_user.status else '禁用'}")
            return
        
        # 创建测试用户
        hashed_password = get_password_hash("123456")
        test_user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=hashed_password,
            status=True
        )
        
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        
        print("=" * 50)
        print("测试用户创建成功！")
        print("=" * 50)
        print(f"用户名: {test_user.username}")
        print(f"密码: 123456")
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
    create_test_user()
