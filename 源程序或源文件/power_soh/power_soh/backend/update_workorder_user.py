#!/usr/bin/env python3
"""
更新work_orders表，添加assigned_user_id字段
"""

from sqlalchemy import create_engine, Column, Integer, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 数据库连接字符串
DATABASE_URL = "mysql+pymysql://root:wby929@localhost/battery_soh_db"

# 创建引擎
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()

# 定义WorkOrder表模型
class WorkOrder(Base):
    __tablename__ = "work_orders"
    
    id = Column(Integer, primary_key=True, index=True)

# 获取数据库连接
db = SessionLocal()

print("开始更新work_orders表...")

# 直接尝试添加assigned_user_id字段
try:
    # 执行SQL语句添加字段
    with engine.connect() as conn:
        print("添加assigned_user_id字段...")
        # 尝试添加字段，如果已存在会失败但我们可以忽略
        try:
            conn.execute(text("ALTER TABLE work_orders ADD COLUMN assigned_user_id INT NULL"))
            print("字段添加成功！")
        except Exception as e:
            print(f"字段可能已存在: {e}")
        
        # 尝试添加外键约束
        try:
            conn.execute(text("ALTER TABLE work_orders ADD FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL"))
            print("外键约束添加成功！")
        except Exception as e:
            print(f"外键约束可能已存在: {e}")
        
        conn.commit()
    print("work_orders表更新完成！")
except Exception as e:
    print(f"更新失败: {e}")
finally:
    db.close()
