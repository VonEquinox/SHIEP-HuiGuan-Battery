#!/usr/bin/env python3
"""
更新WorkOrder表结构脚本
用于添加新的字段到work_orders表
"""

from db.database import engine
from sqlalchemy import text


def update_workorder_table():
    """更新WorkOrder表结构"""
    print("开始更新WorkOrder表结构...")
    
    try:
        with engine.connect() as conn:
            # 检查并添加assigned_worker字段
            result = conn.execute(text("SHOW COLUMNS FROM work_orders LIKE 'assigned_worker'")).fetchall()
            if not result:
                conn.execute(text("ALTER TABLE work_orders ADD COLUMN assigned_worker VARCHAR(100) DEFAULT NULL"))
                print("✅ 成功添加assigned_worker字段")
            else:
                print("ℹ️ assigned_worker字段已存在")
            
            # 检查并添加distance_km字段
            result = conn.execute(text("SHOW COLUMNS FROM work_orders LIKE 'distance_km'")).fetchall()
            if not result:
                conn.execute(text("ALTER TABLE work_orders ADD COLUMN distance_km FLOAT DEFAULT NULL"))
                print("✅ 成功添加distance_km字段")
            else:
                print("ℹ️ distance_km字段已存在")
            
            # 检查并添加safety_instructions字段
            result = conn.execute(text("SHOW COLUMNS FROM work_orders LIKE 'safety_instructions'")).fetchall()
            if not result:
                conn.execute(text("ALTER TABLE work_orders ADD COLUMN safety_instructions TEXT DEFAULT NULL"))
                print("✅ 成功添加safety_instructions字段")
            else:
                print("ℹ️ safety_instructions字段已存在")
            
            # 检查并添加required_parts字段
            result = conn.execute(text("SHOW COLUMNS FROM work_orders LIKE 'required_parts'")).fetchall()
            if not result:
                conn.execute(text("ALTER TABLE work_orders ADD COLUMN required_parts TEXT DEFAULT NULL"))
                print("✅ 成功添加required_parts字段")
            else:
                print("ℹ️ required_parts字段已存在")
            
            conn.commit()
            print("✅ 数据库表结构更新完成！")
    except Exception as e:
        print(f"⚠️ 更新表结构时出错: {e}")


if __name__ == "__main__":
    update_workorder_table()
