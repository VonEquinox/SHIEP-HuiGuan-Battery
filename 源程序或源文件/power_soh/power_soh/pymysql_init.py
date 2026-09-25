"""
数据库初始化脚本 - 使用PyMySQL执行SQL
"""
import pymysql
from pathlib import Path


def init_database():
    """执行数据库初始化"""
    print("开始初始化数据库...")
    
    # 检查SQL文件是否存在
    sql_file = Path(__file__).parent / "init_database.sql"
    if not sql_file.exists():
        print(f"SQL文件不存在: {sql_file}")
        return False
    
    print(f"找到SQL文件: {sql_file}")
    
    # 从.env文件读取数据库配置
    env_file = Path(__file__).parent / ".env"
    db_config = {}
    
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    db_config[key] = value.strip('"\'')
    
    # 设置默认值
    host = db_config.get('DB_HOST', 'localhost')
    port = int(db_config.get('DB_PORT', '3306'))
    user = db_config.get('DB_USER', 'root')
    password = db_config.get('DB_PASSWORD', '')
    db_name = db_config.get('DB_NAME', 'battery_soh_backend_db')
    
    print(f"数据库配置: {host}:{port}, 用户: {user}, 数据库: {db_name}")
    
    try:
        # 首先连接到MySQL服务器（不指定数据库）
        print("连接到MySQL服务器...")
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset='utf8mb4'
        )
        
        with connection.cursor() as cursor:
            # 创建数据库（如果不存在）
            create_db_sql = f"CREATE DATABASE IF NOT EXISTS `{db_name}` " \
                         "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            cursor.execute(create_db_sql)
            print(f"✓ 数据库 '{db_name}' 已创建或已存在")
            
            # 使用该数据库
            cursor.execute(f"USE `{db_name}`;")
            
        connection.commit()
        connection.close()
        print("✓ 数据库创建完成")
        
        # 重新连接到指定数据库
        print("连接到目标数据库...")
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            charset='utf8mb4',
            autocommit=True
        )
        
        # 读取SQL文件内容
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 分割SQL语句并执行（跳过CREATE DATABASE和USE语句，因为已经执行过了）
        sql_statements = sql_content.split(';')
        
        with connection.cursor() as cursor:
            for statement in sql_statements:
                statement = statement.strip()
                # 检查是否为有效的SQL语句（跳过注释和特定语句）
                if not statement or statement.startswith('--'):
                    continue
                
                # 跳过CREATE DATABASE和USE语句，因为已经在前面执行
                is_skip_statement = (
                    statement.startswith('CREATE DATABASE') or 
                    statement.startswith('USE ') or 
                    statement.startswith('use ')
                )
                if is_skip_statement:
                    continue
                
                if statement.upper().startswith('CREATE TABLE'):
                    # 检查是否是创建表的语句
                    parts = statement.split()
                    table_name = parts[2] if len(parts) > 2 else "未知表"
                    print(f"执行创建表: {table_name}")
                elif statement.upper().startswith('INSERT'):
                    # 检查是否是插入语句
                    print("执行插入语句...")
                elif statement.upper().startswith('SHOW'):
                    # 检查是否是显示语句
                    print("执行显示语句...")
                
                try:
                    cursor.execute(statement)
                except Exception as e:
                    # 如果是注释或空语句，跳过
                    error_msg = str(e).lower()
                    if "syntax" in error_msg or "empty" in error_msg:
                        continue
                    else:
                        # 只打印非空的SQL语句错误
                        if statement.strip():
                            print(f"执行SQL语句时出错: {e}")
        
        connection.close()
        print("✓ 数据库初始化成功！")
        print("创建了以下表：")
        print("- users: 用户表")
        print("- battery_data: 电池数据表")
        print("- models: 模型表")
        print("- training_records: 训练记录表")
        print("- prediction_records: 预测记录表")
        print("- datasets: 数据集表")
        print("- model_comparisons: 模型比较表")
        print("- 插入了默认管理员用户")
        return True
        
    except pymysql.err.OperationalError as e:
        print(f"✗ 数据库连接错误: {e}")
        print("可能的原因：")
        print("1. MySQL服务器未启动")
        print("2. 用户名或密码错误")
        print("3. 端口配置错误")
        print("4. 权限不足")
        return False
    except Exception as e:
        print(f"✗ 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = init_database()
    if success:
        print("\n🎉 数据库更新成功完成！")
        print("储能电池寿命预测系统的数据库已准备就绪。")
    else:
        print("\n❌ 数据库更新失败，请检查错误信息。")
        print("如果继续遇到问题，请参考下方的手动执行说明：")
        print("\n手动执行说明：")
        print("1. 确保MySQL服务器正在运行")
        print("2. 检查您的数据库配置(.env文件)")
        print("3. 确保已正确安装PyMySQL: pip install PyMySQL")
        print("4. 按照错误信息进行故障排除")