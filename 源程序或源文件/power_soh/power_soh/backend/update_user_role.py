#!/usr/bin/env python3
"""
更新用户角色脚本
用于将指定用户的角色更改为管理员
"""

from db.database import SessionLocal
from db.models import User


def update_user_role(user_id, new_role):
    """更新用户角色"""
    print(f"开始更新用户 ID {user_id} 的角色为 {new_role}...")
    
    db = SessionLocal()
    try:
        # 查找用户
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"❌ 用户 ID {user_id} 不存在")
            return
        
        # 更新角色
        user.role = new_role
        db.commit()
        db.refresh(user)
        
        print(f"✅ 成功更新用户 {user.username} 的角色为 {user.role}")
    except Exception as e:
        print(f"❌ 更新角色时出错: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    # 更新 oyx 用户（ID为1）的角色为 admin
    update_user_role(1, "admin")
    # 同时更新 admin 用户的角色为 admin
    update_user_role(11, "admin")
