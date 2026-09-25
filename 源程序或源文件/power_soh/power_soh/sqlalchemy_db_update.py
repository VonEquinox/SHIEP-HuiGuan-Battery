"""
数据库更新脚本 - 使用SQLAlchemy创建数据库表
"""
import os
import sys

# 添加backend目录到Python路径
backend_path = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_path)

from sqlalchemy import create_engine, text
from backend.db.database import Base
from backend.core.config import settings


def update_database():
    """使用SQLAlchemy更新数据库"""
    print("开始更新数据库...")
    print(f"数据库URL: {settings.DATABASE_URL}")
    
    try:
        # 创建数据库引擎
        engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DB_ECHO,
            pool_pre_ping=True  # 确保连接有效
        )
        
        # 创建所有表
        print("正在创建数据库表...")
        Base.metadata.create_all(bind=engine)
        print("✓ 所有表创建成功！")
        
        # 测试连接
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("✓ 数据库连接测试成功")
        
        print("\n数据库更新完成！")
        print("创建了以下表：")
        print("- users: 用户表")
        print("- battery_data: 电池数据表")
        print("- models: 模型表")
        print("- training_records: 训练记录表")
        print("- prediction_records: 预测记录表")
        print("- datasets: 数据集表")
        print("- model_comparisons: 模型比较表")
        
        return True
        
    except Exception as e:
        print(f"数据库更新失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = update_database()
    if success:
        print("\n数据库更新成功完成！")
    else:
        print("\n数据库更新失败，请检查错误信息。")