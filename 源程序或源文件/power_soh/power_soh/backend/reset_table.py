# backend/reset_table.py
from db.database import engine
from db.models import BMSData

def reset_bms():
    print("正在连接 MySQL 数据库...")
    # 强制删除旧的 bms_data 表
    BMSData.__table__.drop(engine, checkfirst=True)
    print("✅ 旧的 bms_data 表已成功删除！")
    
    # 按照 models.py 里的新特征结构重新建表
    BMSData.__table__.create(engine, checkfirst=True)
    print("✅ 全新的高级特征 bms_data 表已创建完毕！")

if __name__ == "__main__":
    reset_bms()