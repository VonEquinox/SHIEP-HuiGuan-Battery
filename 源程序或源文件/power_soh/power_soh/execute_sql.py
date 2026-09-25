"""
数据库初始化脚本 - 使用Python执行SQL文件
"""
import subprocess
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
    port = db_config.get('DB_PORT', '3306')
    user = db_config.get('DB_USER', 'root')
    password = db_config.get('DB_PASSWORD', '')
    db_name = db_config.get('DB_NAME', 'battery_soh_backend_db')
    
    print(f"数据库配置: {host}:{port}, 用户: {user}, 数据库: {db_name}")
    
    try:
        # 构建mysql命令
        cmd = [
            'mysql',
            f'-h{host}',
            f'-P{port}',
            f'-u{user}',
            f'-p{password}',
            '-e',
            f'SOURCE {sql_file.absolute()};'
        ]
        
        print("执行数据库初始化命令...")
        print(f"命令: {' '.join(cmd[:-1])} '[SQL_FILE]'")
        
        # 执行命令
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
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
        else:
            print("✗ 数据库初始化失败:")
            print(f"错误: {result.stderr}")
            print("可能的原因：")
            print("1. MySQL服务器未启动")
            print("2. 用户名或密码错误")
            print("3. MySQL客户端未安装")
            print("4. 权限不足")
            return False
            
    except FileNotFoundError:
        print("✗ 未找到MySQL命令行工具")
        print("请确保MySQL已安装并添加到系统PATH中")
        print("或者您可以手动执行以下操作：")
        print("1. 启动MySQL服务器")
        print(f"2. 连接到MySQL: mysql -u{user} -p{password} -h{host} -P{port}")
        print(f"3. 在MySQL命令行中执行: SOURCE {sql_file.absolute()};")
        return False
    except Exception as e:
        print(f"执行数据库初始化时出错: {e}")
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
        print("3. 确保已安装MySQL客户端工具")
        print("4. 按照提示手动执行SQL文件")