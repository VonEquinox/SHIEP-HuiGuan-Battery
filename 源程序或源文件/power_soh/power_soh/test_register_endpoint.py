#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试注册接口"""
import sys
sys.path.insert(0, 'backend')

from db.database import SessionLocal
from db.models import User
from utils.security import get_password_hash

# 测试创建用户
db = SessionLocal()
try:
    test_user = User(
        username="testuser123",
        email="test123@example.com",
        hashed_password=get_password_hash("test123456"),
        status=True
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)
    print(f"✓ 测试用户创建成功，ID: {test_user.id}")
    
    # 清理测试用户
    db.delete(test_user)
    db.commit()
    print("✓ 测试用户已删除")
    
except Exception as e:
    print(f"✗ 错误: {e}")
    import traceback
    traceback.print_exc()
    db.rollback()
finally:
    db.close()
