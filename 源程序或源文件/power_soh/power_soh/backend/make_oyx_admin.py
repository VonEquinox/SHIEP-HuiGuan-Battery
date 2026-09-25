from db.database import SessionLocal
from db.models import User

def upgrade_user():
    # 连接数据库
    db = SessionLocal()
    try:
        # 查找 oyx 账号
        user = db.query(User).filter(User.username == 'oyx').first()
        if user:
            # 强行修改角色为 admin
            user.role = 'admin'
            db.commit()
            print("✅ 成功！账号 'oyx' 已被升级为系统管理员 (admin)！")
        else:
            print("❌ 未找到用户 'oyx'，请检查用户名拼写。")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    upgrade_user()