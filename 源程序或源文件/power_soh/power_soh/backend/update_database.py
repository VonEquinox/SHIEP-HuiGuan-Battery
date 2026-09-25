#!/usr/bin/env python3
"""
数据库表结构更新脚本
用于添加缺失的字段到数据库表
"""

from db.database import engine, Base
from db.models import BMSData, User
from sqlalchemy import text


def update_database():
    """更新数据库表结构"""
    print("开始更新数据库表结构...")
    
    # 1. 首先尝试通过SQLAlchemy的自动创建功能
    try:
        print("尝试通过SQLAlchemy创建缺失的表...")
        Base.metadata.create_all(bind=engine)
        print("✅ SQLAlchemy表结构创建完成")
    except Exception as e:
        print(f"⚠️ SQLAlchemy创建表时出错: {e}")
    
    # 2. 直接执行SQL语句添加cycle_end字段到bms_data表
    try:
        print("尝试添加cycle_end字段到bms_data表...")
        # 使用SQLAlchemy执行原始SQL
        with engine.connect() as conn:
            # 检查字段是否存在
            result = conn.execute(text("SHOW COLUMNS FROM bms_data LIKE 'cycle_end'")).fetchall()
            
            if not result:
                # 添加字段
                conn.execute(text("ALTER TABLE bms_data ADD COLUMN cycle_end BOOLEAN DEFAULT FALSE"))
                conn.commit()
                print("✅ 成功添加cycle_end字段")
            else:
                print("ℹ️ cycle_end字段已存在，无需添加")
    except Exception as e:
        print(f"⚠️ 添加字段时出错: {e}")
    
    # 3. 添加role字段到users表
    try:
        print("尝试添加role字段到users表...")
        # 使用SQLAlchemy执行原始SQL
        with engine.connect() as conn:
            # 检查字段是否存在
            result = conn.execute(text("SHOW COLUMNS FROM users LIKE 'role'")).fetchall()
            
            if not result:
                # 添加字段
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user' NOT NULL"))
                conn.commit()
                print("✅ 成功添加role字段")
            else:
                print("ℹ️ role字段已存在，无需添加")
    except Exception as e:
        print(f"⚠️ 添加字段时出错: {e}")
    
    print("数据库表结构更新完成！")


if __name__ == "__main__":
    update_database()
